#!/usr/bin/env python3
"""Suite for scripts/check-windows-shards.py, the fail-closed fan-in behind the
required `crew-shell-matrix (windows-latest)` check.

Every case builds shard artifacts in a temp directory and runs the checker as
a subprocess. The failing cases are the point: each is one way a test could be
lost, or a Windows job not run, while the required check still went green.

Run: python3 scripts/_test/windows-shards.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from xml.sax.saxutils import quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(os.path.dirname(HERE), "check-windows-shards.py")

IDS = [
    "plugin/crew/tests/test_a.py::test_one",
    "plugin/crew/tests/test_a.py::test_two[ps1]",
    "plugin/crew/tests/test_a.py::test_two[sh]",
    "plugin/crew/tests/test_b.py::TestThing::test_x[a-b]",
    "plugin/crew/tests/test_b.py::TestThing::test_y",
    "plugin/crew/tests/sub/test_c.py::test_z[x::y]",
]
SLOW_IDS = ["plugin/crew/tests/test_a.py::test_matrix[sh-case1]",
            "plugin/crew/tests/test_a.py::test_matrix[ps1-case1]"]
WALL_IDS = ["plugin/crew/tests/test_w.py::test_bound"]
# A checker that hangs is a failed case, not a hung CI job.
CHECKER_TIMEOUT = 60
JOBS_OK = ["--job", "default=success", "--job", "slow=success", "--job", "wallclock=success"]


def mangle(nodeid):
    path, bracket, params = nodeid.partition("[")
    names = path.split("::")
    names[0] = names[0].replace("/", ".")[:-3]
    names[-1] += bracket + params
    return ".".join(names[:-1]), names[-1]


def collected_text(ids, stated=None, deselected=0):
    count = len(ids) if stated is None else stated
    summary = (f"{count}/{count + deselected} tests collected ({deselected} deselected) in 1.0s"
               if deselected else f"{count} tests collected in 1.0s")
    return "\n".join(ids) + "\n\n" + summary + "\n"


def junit_text(ids):
    cases = "".join(f"<testcase classname={quoteattr(c)} name={quoteattr(n)} time=\"0.1\"/>"
                    for c, n in (mangle(i) for i in ids))
    return ('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" '
            f'tests="{len(ids)}">{cases}</testsuite></testsuites>')


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def build(root, groups, collected=None, shards=3, whole=True):
    """groups: one list of node ids per shard (what its JUnit names). `whole`
    also writes complete slow and wallclock artifacts."""
    if whole:
        for name, ids in (("slow", SLOW_IDS), ("wallclock", WALL_IDS)):
            d = os.path.join(root, f"crew-windows-{name}")
            write(os.path.join(d, "collected.txt"), collected_text(ids, deselected=9))
            write(os.path.join(d, "junit.xml"), junit_text(ids))
    for k, ran in enumerate(groups, start=1):
        if ran is None:
            continue
        d = os.path.join(root, f"crew-windows-default-{k}")
        write(os.path.join(d, "collected.txt"),
              collected[k - 1] if collected else collected_text(IDS, deselected=3))
        write(os.path.join(d, "junit.xml"), junit_text(ran))
    return shards


def good_groups():
    return [IDS[0::3], IDS[1::3], IDS[2::3]]


def run(root, extra=None, run_flag="true", decide="success", jobs=None, shards=3,
        event="pull_request"):
    argv = [sys.executable, CHECKER, "--shards", str(shards), "--artifacts", root,
            "--decide-result", decide, "--run", run_flag, "--event", event] + (JOBS_OK if jobs is None else jobs)
    try:
        proc = subprocess.run(argv + (extra or []), capture_output=True, text=True, check=False,
                              stdin=subprocess.DEVNULL, timeout=CHECKER_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, f"checker did not finish within {CHECKER_TIMEOUT}s"
    return proc.returncode, proc.stdout + proc.stderr


def case_complete_partition_passes(root):
    build(root, good_groups())
    return run(root), (0, "each ran exactly once")


def case_skip_decision_passes_with_notice(root):
    jobs = ["--job", "default=skipped", "--job", "slow=skipped", "--job", "wallclock=skipped"]
    return run(root, run_flag="false", jobs=jobs), (0, "SKIPPED, not passed")


def case_skip_decision_on_a_push_fails(root):
    jobs = ["--job", "default=skipped", "--job", "slow=skipped", "--job", "wallclock=skipped"]
    return run(root, run_flag="false", jobs=jobs, event="push"), (1, "only a pull_request may skip")


def case_slow_artifact_missing_fails(root):
    build(root, good_groups())
    shutil.rmtree(os.path.join(root, "crew-windows-slow"))
    return run(root), (1, "slow: no artifact directory")


def case_slow_ran_nothing_fails(root):
    build(root, good_groups())
    write(os.path.join(root, "crew-windows-slow", "junit.xml"), junit_text([]))
    return run(root), (1, f"slow: {SLOW_IDS[0]} was collected but did not run")


def case_wallclock_collected_nothing_fails(root):
    build(root, good_groups())
    write(os.path.join(root, "crew-windows-wallclock", "collected.txt"),
          "\nno tests collected (40 deselected) in 0.5s\n")
    write(os.path.join(root, "crew-windows-wallclock", "junit.xml"), junit_text([]))
    return run(root), (1, "wallclock: ")


def case_wallclock_ran_an_uncollected_test_fails(root):
    build(root, good_groups())
    write(os.path.join(root, "crew-windows-wallclock", "junit.xml"),
          junit_text(WALL_IDS + ["plugin/crew/tests/test_w.py::test_other"]))
    return run(root), (1, "which it did not collect")


def case_skip_decision_but_a_job_ran_fails(root):
    jobs = ["--job", "default=skipped", "--job", "slow=failure", "--job", "wallclock=skipped"]
    return run(root, run_flag="false", jobs=jobs), (1, "did not skip: slow=failure")


def case_decide_job_failed_fails(root):
    build(root, good_groups())
    return run(root, decide="failure"), (1, "whether the Windows jobs had to run is unknown")


def case_decide_output_empty_fails(root):
    build(root, good_groups())
    return run(root, run_flag=""), (1, "not true or false")


def case_crlf_collection_from_windows_passes(root):
    crlf = collected_text(IDS, deselected=3).replace("\n", "\r\n")
    build(root, good_groups(), collected=[crlf, crlf, crlf])
    return run(root), (0, "each ran exactly once")


def case_unicode_line_separator_in_an_id_passes(root):
    # U+2028 and U+0085 are line breaks to str.splitlines() but not to pytest:
    # an id holding one is one record, not two.
    ids = IDS + ["plugin/crew/tests/test_u.py::test_sep[a\u2028b]",
                 "plugin/crew/tests/test_u.py::test_sep[c\x85d]"]
    text = collected_text(ids, deselected=3)
    build(root, [ids[0::3], ids[1::3], ids[2::3]], collected=[text, text, text])
    return run(root), (0, "8 tests collected by each of 3 shards")


def case_annotation_text_cannot_forge_a_workflow_command(root):
    groups = good_groups()
    groups[0].append("plugin/crew/tests/test_x.py::test_bad[a\n::warning::forged]")
    build(root, groups)
    rc, text = run(root)
    if any(line.startswith("::warning::forged") for line in text.splitlines()):
        rc = 99
    return (rc, text), (1, "%0A::warning::forged")


def case_shard_job_failed_fails(root):
    build(root, good_groups())
    jobs = ["--job", "default=failure", "--job", "slow=success", "--job", "wallclock=success"]
    return run(root, jobs=jobs), (1, "Windows job default: result 'failure'")


def case_slow_job_cancelled_fails(root):
    build(root, good_groups())
    jobs = ["--job", "default=success", "--job", "slow=cancelled", "--job", "wallclock=success"]
    return run(root, jobs=jobs), (1, "Windows job slow: result 'cancelled'")


def case_wallclock_job_not_reported_fails(root):
    build(root, good_groups())
    jobs = ["--job", "default=success", "--job", "slow=success"]
    return run(root, jobs=jobs), (1, "no result given for Windows job wallclock")


def case_job_reported_twice_fails(root):
    build(root, good_groups())
    return run(root, jobs=JOBS_OK + ["--job", "slow=failure"]), (1, "result given more than once")


def case_missing_shard_artifact_fails(root):
    groups = good_groups()
    groups[2] = None
    build(root, groups)
    return run(root), (1, "shard 3: no artifact directory")


def case_missing_junit_fails(root):
    build(root, good_groups())
    os.remove(os.path.join(root, "crew-windows-default-2", "junit.xml"))
    return run(root), (1, "shard 2:")


def case_missing_collection_fails(root):
    build(root, good_groups())
    os.remove(os.path.join(root, "crew-windows-default-1", "collected.txt"))
    return run(root), (1, "shard 1:")


def case_test_in_no_shard_fails(root):
    groups = good_groups()
    lost = groups[1].pop()
    build(root, groups)
    return run(root), (1, f"{lost} was collected but ran in no shard")


def case_test_twice_in_one_shard_fails(root):
    groups = good_groups()
    groups[0].append(groups[0][0])
    build(root, groups)
    return run(root), (1, "shard 1: plugin.crew.tests.test_a::test_one ran 2 times")


def case_slow_test_ran_twice_fails(root):
    build(root, good_groups())
    write(os.path.join(root, "crew-windows-slow", "junit.xml"),
          junit_text(SLOW_IDS + SLOW_IDS[:1]))
    return run(root), (1, "slow: plugin.crew.tests.test_a::test_matrix[sh-case1] ran 2 times")


def case_test_in_two_shards_fails(root):
    groups = good_groups()
    groups[0].append(groups[1][0])
    build(root, groups)
    return run(root), (1, f"{groups[1][0]} ran in shard 1 and shard 2")


def case_extra_test_fails(root):
    groups = good_groups()
    groups[2].append("plugin/crew/tests/test_d.py::test_new")
    build(root, groups)
    return run(root), (1, "which the default set does not collect")


def case_shards_collected_differently_fails(root):
    other = collected_text(IDS[:-1], deselected=3)
    same = collected_text(IDS, deselected=3)
    build(root, good_groups(), collected=[same, other, same])
    return run(root), (1, "shard 2 collected a different default set")


def case_same_set_other_order_fails(root):
    reordered = collected_text(list(reversed(IDS)), deselected=3)
    same = collected_text(IDS, deselected=3)
    build(root, good_groups(), collected=[same, reordered, same])
    return run(root), (1, "shard 2 collected a different default set")


def case_count_line_disagrees_fails(root):
    bad = collected_text(IDS, stated=len(IDS) + 1)
    same = collected_text(IDS)
    build(root, good_groups(), collected=[bad, same, same])
    return run(root), (1, "pytest says 7 tests collected, the list has 6")


def case_unfinished_collection_fails(root):
    cut = "\n".join(IDS) + "\n"
    same = collected_text(IDS)
    build(root, good_groups(), collected=[same, same, cut])
    return run(root), (1, "no 'N tests collected' line")


def case_empty_collection_fails(root):
    empty = "\nno tests collected (6 deselected) in 0.5s\n"
    build(root, [[], [], []], collected=[empty, empty, empty])
    return run(root), (1, "collected no tests")


def case_garbage_in_collection_fails(root):
    junk = "plugin/crew/tests/test_a.py: 3\n" + collected_text(IDS)
    same = collected_text(IDS)
    build(root, good_groups(), collected=[junk, same, same])
    return run(root), (1, "not a node id")


def case_unreadable_junit_fails(root):
    build(root, good_groups())
    write(os.path.join(root, "crew-windows-default-1", "junit.xml"), "<testsuites><testsuite>")
    return run(root), (1, "shard 1:")


def case_extra_shard_artifact_fails(root):
    build(root, good_groups() + [[]], collected=None)
    return run(root), (1, "unexpected shard artifact crew-windows-default-4")


def case_four_shards_complete_passes(root):
    groups = [IDS[0::4], IDS[1::4], IDS[2::4], IDS[3::4]]
    build(root, groups)
    return run(root, shards=4), (0, "each ran exactly once")


def case_no_artifacts_at_all_fails(root):
    return run(root), (1, "no shard produced a usable collection")


CASES = [(name[len("case_"):], fn) for name, fn in sorted(globals().items())
         if name.startswith("case_")]


def main() -> int:
    passed = failed = 0
    for name, fn in CASES:
        with tempfile.TemporaryDirectory() as root:
            got, want = fn(root)
        rc, text = got
        want_rc, needle = want
        if rc == want_rc and needle in text:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}\n       expected rc {want_rc} with {needle!r}\n"
                  f"       got rc {rc}:\n" + "\n".join("         " + l for l in text.splitlines()))
    print(f"\nwindows-shards: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
