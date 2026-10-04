#!/usr/bin/env python3
"""The fan-in for crew's sharded Windows CI: pass only when nothing was lost.

    python3 scripts/check-windows-shards.py --shards 6 --artifacts <dir> \
        --decide-result <result> --run <true|false> --event <event_name> \
        --job default=<result> --job slow=<result> --job wallclock=<result>

`.github/workflows/pytest-crew.yml` splits the Windows half of
`crew-shell-matrix` into parallel jobs: the default set in `--shards` groups
(pytest-split), the `slow` set, and the `wallclock` set. Branch protection
requires ONE check, `crew-shell-matrix (windows-latest)`, and that check is the
job that runs this script. So this script is the only thing standing between a
lost test and a green required check, and it fails closed: anything it cannot
read, find or match is a failure, never a pass.

It passes when either

- the decide job succeeded and said `run=false` on a `pull_request` (a PR
  that changes nothing under plugin/crew/ or the workflow), and every Windows
  job was skipped; or
- the decide job succeeded and said `run=true`, every Windows job's result is
  `success`, `crew-windows-slow/` and `crew-windows-wallclock/` each hold a
  `collected.txt` and a `junit.xml` naming exactly what was collected, and the
  default shards together ran exactly the default set:

  * each `<artifacts>/crew-windows-default-<k>/` (k = 1..shards) holds
    `collected.txt` (that shard's `pytest --collect-only -q` of the WHOLE
    default set, before splitting) and `junit.xml` (what the shard ran);
  * every shard collected the same node ids, in the same order (pytest-split
    assumes it), and the count matches pytest's own "N tests collected" line;
  * every collected test appears in exactly one shard's JUnit, exactly once
    (a testcase recorded twice is a failure), and no shard's
    JUnit names a test the collection does not have.

JUnit records (classname, name), not node ids. A node id is mapped the way
pytest's junitxml does it (`_pytest.junitxml.mangle_test_address`): the file
path loses `.py` and its separators become dots, `::` parts join with dots,
and the last part (with any `[params]`) is the name. Two node ids that map to
the same pair make the run fail as ambiguous rather than be counted once.

Exit 0: pass. Exit 1: a failure, one `::error::` line per problem. Exit 2: usage.
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import sys
import xml.etree.ElementTree as ET

SET_PREFIX = "crew-windows-"
ARTIFACT_PREFIX = SET_PREFIX + "default-"
COLLECTED = "collected.txt"
JUNIT = "junit.xml"
_COUNT_RE = re.compile(r"^(?:(\d+)/)?(\d+) tests? collected")
_NO_TESTS_RE = re.compile(r"^no tests collected")
# Every Windows job the workflow runs. One the call does not report is a
# failure: a job dropped from the fan-in's `needs` must not pass unseen.
REQUIRED_JOBS = ("default", "slow", "wallclock")
# The unsplit sets, each one artifact `crew-windows-<name>/`.
WHOLE_SETS = ("slow", "wallclock")


def escape_annotation(text: str) -> str:
    """GitHub's workflow-command data encoding: a test name holding a line
    break must not start a command line of its own."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def mangle(nodeid: str) -> tuple:
    """(classname, name) as pytest's junitxml writes them for `nodeid`."""
    path, bracket, params = nodeid.partition("[")
    names = path.split("::")
    names[0] = re.sub(r"\.py$", "", names[0].replace("/", "."))
    names[-1] += bracket + params
    return ".".join(names[:-1]), names[-1]


def read_collected(path: str) -> tuple:
    """(node ids, problems) from a `pytest --collect-only -q` transcript.

    The ids are the leading lines up to the first blank one; every one must be
    a node id. The summary line further down must state the same count."""
    try:
        # Written on Windows by a redirected python: CRLF line ends, which
        # newline=None (universal newlines) reads as "\n". Strict decoding: a
        # transcript that is not UTF-8 is a failure, not a guess.
        # Split on "\n" only: str.splitlines() also breaks on U+2028, U+0085
        # and other characters a node id may legally hold.
        with open(path, encoding="utf-8", errors="strict", newline=None) as fh:
            lines = fh.read().split("\n")
    except (OSError, UnicodeDecodeError) as exc:
        return [], [f"{path}: cannot read: {exc}"]
    ids = []
    i = 0
    while i < len(lines) and lines[i].strip():
        line = lines[i].strip()
        if "::" not in line:
            return [], [f"{path}:{i + 1}: not a node id: {line!r}"]
        ids.append(line)
        i += 1
    stated = None
    for line in lines[i:]:
        text = line.strip().strip("=").strip()
        match = _COUNT_RE.match(text)
        if match:
            stated = int(match.group(1) or match.group(2))
            break
        if _NO_TESTS_RE.match(text):
            stated = 0
            break
    problems = []
    if stated is None:
        problems.append(f"{path}: no 'N tests collected' line; the collection did not finish")
    elif stated != len(ids):
        problems.append(f"{path}: pytest says {stated} tests collected, the list has {len(ids)}")
    if not ids:
        problems.append(f"{path}: collected no tests")
    return ids, problems


def read_junit(path: str) -> tuple:
    """(set of (classname, name), problems) for every testcase in a JUnit file.

    pytest writes one testcase per test, so a name recorded twice means the
    test ran twice: that is reported, not folded into the set."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        return set(), [f"{path}: cannot read: {exc}"]
    counts = collections.Counter(
        (case.get("classname", ""), case.get("name", "")) for case in root.iter("testcase"))
    problems = [f"{c}::{n} ran {k} times" for (c, n), k in sorted(counts.items()) if k > 1]
    return set(counts), problems[:20]


def check_partition(artifacts: str, shards: int) -> list:
    problems = []
    collections = {}
    ran = {}
    for k in range(1, shards + 1):
        shard_dir = os.path.join(artifacts, f"{ARTIFACT_PREFIX}{k}")
        if not os.path.isdir(shard_dir):
            problems.append(f"shard {k}: no artifact directory {shard_dir}")
            continue
        ids, found = read_collected(os.path.join(shard_dir, COLLECTED))
        problems += [f"shard {k}: {p}" for p in found]
        if ids:
            collections[k] = ids
        keys, found = read_junit(os.path.join(shard_dir, JUNIT))
        problems += [f"shard {k}: {p}" for p in found]
        if keys or not found:
            ran[k] = keys
    extra_dirs = sorted(
        name for name in (os.listdir(artifacts) if os.path.isdir(artifacts) else [])
        if name.startswith(ARTIFACT_PREFIX)
        and name[len(ARTIFACT_PREFIX):] not in {str(k) for k in range(1, shards + 1)})
    problems += [f"unexpected shard artifact {name} (expected {shards} shards)" for name in extra_dirs]
    if not collections:
        return problems + ["no shard produced a usable collection; nothing to check against"]
    reference_shard = min(collections)
    reference = collections[reference_shard]
    for k, ids in sorted(collections.items()):
        if ids != reference:
            only_here = sorted(set(ids) - set(reference))[:5]
            only_there = sorted(set(reference) - set(ids))[:5]
            problems.append(
                f"shard {k} collected a different default set than shard {reference_shard} "
                f"({len(ids)} vs {len(reference)}; only in {k}: {only_here}; "
                f"only in {reference_shard}: {only_there})")
    expected = {}
    for nodeid in reference:
        key = mangle(nodeid)
        if key in expected:
            problems.append(f"ambiguous JUnit name {key}: {expected[key]} and {nodeid}")
        expected[key] = nodeid
    seen = {}
    for k, keys in sorted(ran.items()):
        for key in sorted(keys - expected.keys())[:20]:
            problems.append(f"shard {k} ran {key[0]}::{key[1]}, which the default set does not collect")
        for key in keys & expected.keys():
            if key in seen:
                problems.append(f"{expected[key]} ran in shard {seen[key]} and shard {k}")
            else:
                seen[key] = k
    if len(ran) == shards:
        missing = [nodeid for key, nodeid in expected.items() if key not in seen]
        for nodeid in missing[:20]:
            problems.append(f"{nodeid} was collected but ran in no shard")
        if len(missing) > 20:
            problems.append(f"... and {len(missing) - 20} more tests ran in no shard")
    if not problems:
        per_shard = ", ".join(f"shard {k}: {len(ran[k])}" for k in sorted(ran))
        print(f"default set: {len(reference)} tests collected by each of {shards} shards; "
              f"{per_shard}; each ran exactly once")
    return problems


def check_whole_set(artifacts: str, name: str) -> list:
    """An unsplit set (slow, wallclock): its JUnit names exactly what it collected."""
    set_dir = os.path.join(artifacts, f"{SET_PREFIX}{name}")
    if not os.path.isdir(set_dir):
        return [f"{name}: no artifact directory {set_dir}"]
    ids, problems = read_collected(os.path.join(set_dir, COLLECTED))
    keys, found = read_junit(os.path.join(set_dir, JUNIT))
    problems = [f"{name}: {p}" for p in problems + found]
    if problems:
        return problems
    expected = {}
    for nodeid in ids:
        key = mangle(nodeid)
        if key in expected:
            problems.append(f"{name}: ambiguous JUnit name {key}: {expected[key]} and {nodeid}")
        expected[key] = nodeid
    missing = [nodeid for key, nodeid in expected.items() if key not in keys]
    extra = sorted(keys - expected.keys())
    problems += [f"{name}: {nodeid} was collected but did not run" for nodeid in missing[:20]]
    problems += [f"{name}: ran {c}::{n}, which it did not collect" for c, n in extra[:20]]
    if len(missing) + len(extra) > 40:
        problems.append(f"{name}: {len(missing)} missing and {len(extra)} extra in all")
    if not problems:
        print(f"{name} set: {len(ids)} tests collected, all ran")
    return problems


def _job(text: str) -> tuple:
    name, sep, result = text.partition("=")
    if not sep or not name:
        raise argparse.ArgumentTypeError(f"{text!r} is not NAME=RESULT")
    return name, result


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--shards", type=int, required=True)
    ap.add_argument("--artifacts", required=True)
    ap.add_argument("--decide-result", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--event", required=True, help="github.event_name")
    ap.add_argument("--job", type=_job, action="append", required=True,
                    help="NAME=RESULT for every Windows job; repeat")
    args = ap.parse_args(argv)
    if args.shards < 1:
        ap.error("--shards must be >= 1")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    problems = []
    named = [name for name, _ in args.job]
    for name in REQUIRED_JOBS:
        if name not in named:
            problems.append(f"no result given for Windows job {name}")
    for name in sorted({n for n in named if named.count(n) > 1}):
        problems.append(f"Windows job {name}: result given more than once")
    if args.decide_result != "success":
        problems.append(f"the decide job's result is {args.decide_result!r}, so whether the "
                        "Windows jobs had to run is unknown")
    elif args.run not in ("true", "false"):
        problems.append(f"the decide job's run output is {args.run!r}, not true or false")
    elif args.run == "false" and args.event != "pull_request":
        problems.append(f"the decide job said skip on a {args.event!r} event; only a "
                        "pull_request may skip the Windows jobs")
    elif args.run == "false":
        ran = [f"{name}={result}" for name, result in args.job if result != "skipped"]
        if ran:
            problems.append("the decide job said skip, but these jobs did not skip: "
                            + ", ".join(ran))
        else:
            print("::notice::crew-shell-matrix (windows-latest) SKIPPED, not passed: this PR "
                  "changes nothing under plugin/crew/ or .github/workflows/pytest-crew.yml. "
                  "It runs on push to main, the nightly schedule and workflow_dispatch.")
    else:
        for name, result in args.job:
            if result != "success":
                problems.append(f"Windows job {name}: result {result!r}")
        problems += check_partition(args.artifacts, args.shards)
        for name in WHOLE_SETS:
            problems += check_whole_set(args.artifacts, name)
    for problem in problems:
        print(f"::error::{escape_annotation(problem)}")
    if problems:
        print(f"crew-shell-matrix (windows-latest): FAIL, {len(problems)} problem(s)")
        return 1
    print("crew-shell-matrix (windows-latest): PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
