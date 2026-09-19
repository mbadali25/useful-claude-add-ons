"""verify-gate --price / /crew:verify --price.

Operator-only tool: times every rule in a verify.json-shaped map (no budget)
and writes `seconds` for the rules that do not have one. NEVER invoked from
the Stop hook -- verify-gate.sh/.ps1 only reach this module when the FIRST
argument is literally "--price", and the Stop hook (hooks.json) never passes
that. .crew/verify.json in THIS repo is tracked (`git ls-files .crew/` lists
it), so a --price that ran unattended would dirty a committed file on every
Stop; this file exists specifically so that can never happen by accident.

REACH. A rule cannot be timed here unless its reach is `local`:
  - a DECLARED `reach` of anything but `local` is SKIPPED, never run --
    "price it by hand" is the point, not a suggestion.
  - an UNDECLARED `reach` whose command matches a reach verb (ssm, ssh,
    `curl `, `aws `, `az `, `gh `, psql, mysql) is REFUSED outright, in both
    directions (never priced even with --force) -- a hit with no `reach` is
    a correctness problem in the map, not something this tool works around
    by running the command anyway.

NEVER WRITES 0. A rule that ran in under a second still costs 1, because 0
reads as "free" to the Stop budget's deferral arithmetic, and free is never
true of a command that actually ran.
"""
import json
import math
import os
import shutil
import subprocess
import sys
import time

REACH_VERBS = ["ssm", "ssh", "curl ", "aws ", "az ", "gh ", "psql", "mysql"]


def _looks_remote(run):
    for cmd in run or []:
        if not isinstance(cmd, str):
            continue
        for verb in REACH_VERBS:
            if verb in cmd:
                return verb
    return None


def _bash():
    for cand in ("bash", "bash.exe"):
        p = shutil.which(cand)
        if p:
            return p
    for cand in (r"C:\Program Files\Git\bin\bash.exe",
                 r"C:\Program Files\Git\usr\bin\bash.exe"):
        if os.path.exists(cand):
            return cand
    return None


def _time_rule(run):
    bash = _bash()
    start = time.monotonic()
    ok = True
    for cmd in run or []:
        if bash:
            p = subprocess.run([bash, "-c", cmd], capture_output=True, check=False)
        else:
            p = subprocess.run(cmd, shell=True, capture_output=True, check=False)
        if p.returncode != 0:
            ok = False
    elapsed = time.monotonic() - start
    return max(1, math.ceil(elapsed)), ok


def main(argv):
    if len(argv) < 2:
        print("usage: verify_price.py <verify.json path> [--force]", file=sys.stderr)
        return 2
    target = argv[1]
    force = "--force" in argv[2:]

    try:
        with open(target, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as e:
        print(f"PRICE: could not read {target}: {e}", file=sys.stderr)
        return 3

    rules = cfg.get("rules")
    if not isinstance(rules, list):
        print(f"PRICE: {target} has no `rules` array", file=sys.stderr)
        return 3

    changed = False
    rows = []
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        reach = rule.get("reach")
        has_seconds = (isinstance(rule.get("seconds"), (int, float))
                       and not isinstance(rule.get("seconds"), bool))

        if isinstance(reach, str) and reach != "local":
            rows.append((i, "SKIPPED", f"reach: {reach}, price it by hand"))
            continue

        if reach is None:
            verb = _looks_remote(rule.get("run"))
            if verb:
                rows.append((i, "REFUSED",
                             f"undeclared reach, command matches {verb!r} - "
                             f"declare `reach` or price by hand"))
                continue

        if has_seconds and not force:
            rows.append((i, "SKIP",
                         f"already priced {int(rule['seconds'])}s "
                         f"(use --force to re-time)"))
            continue

        secs, ok = _time_rule(rule.get("run"))
        rule["seconds"] = secs
        changed = True
        status = "PRICED" if ok else "PRICED (a command failed - timed anyway)"
        rows.append((i, status, f"{secs}s"))

    for i, status, detail in rows:
        print(f"rules[{i}]: {status:<8} {detail}")

    if changed:
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
            fh.write("\n")
        print(f"PRICE: wrote {target}")
    else:
        print("PRICE: nothing to write (no rule was timed)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
