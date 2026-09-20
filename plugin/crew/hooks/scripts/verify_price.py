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
  - an UNDECLARED `reach` is scanned by verify_record.scan_reach - the SAME
    scanner the Stop gate uses (imported in-process here, not reimplemented;
    see its module docstring for the round-6 redesign, which stopped trying
    to model shell at all). A VERB match, a SYNTAX match (any shell
    metacharacter present, unconditionally), or a WRAPPER match (an
    interpreter's inline-code/script flag, or a token resolving to an
    existing repo file) is REFUSED outright, in all three cases, never
    priced even with --force. Round 2: this used to scan only the outer
    command STRING with a bare substring check, so `bash wrapper.sh` where
    wrapper.sh itself called ssh passed the scan and was TIMED - which
    means RUN - exactly the command Stop would have refused.

EXIT 77 IS SKIP, same convention the gate follows (_verify/smoke.sh, GNU
automake): "skipped, environment absent" is not a measurement of the work,
it is a measurement of an environment that had nothing to check. Pricing it
anyway wrote a `seconds` for a command that never actually ran, which then
UNDERPRICES the real cost the next time the environment IS present and the
command actually executes.

ENV PINNING, shared with the gates via verify_record.pinned_env: a rule
declaring `env` is timed under exactly those values; the five variables the
gate always pins (ENV, AWS_PROFILE, AWS_DEFAULT_REGION, KUBECONFIG,
TF_WORKSPACE) are otherwise unset. Without this, an operator's own
AWS_PROFILE=prod rode straight into a `seconds` measurement meant to be
reusable by everyone who reads the map afterward - not by the person who
happened to run --price.

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_record  # noqa: E402  pylint: disable=wrong-import-position


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


def _time_rule(run, env):
    """Returns (seconds_or_None, status) where status is "ok", "failed" or
    "skip77". seconds is None for skip77 - a SKIP measures nothing."""
    bash = _bash()
    start = time.monotonic()
    status = "ok"
    for cmd in run or []:
        if bash:
            p = subprocess.run([bash, "-c", cmd], capture_output=True,
                               check=False, env=env)
        else:
            p = subprocess.run(cmd, shell=True, capture_output=True,
                               check=False, env=env)
        if p.returncode == 77:
            # A rule is priced as ONE unit; the first command to report
            # "environment absent" makes the whole rule a SKIP, the same
            # whole-rule contract the budget itself uses elsewhere.
            return (None, "skip77")
        if p.returncode != 0 and status == "ok":
            status = "failed"
    elapsed = time.monotonic() - start
    return (max(1, math.ceil(elapsed)), status)


def main(argv):
    if len(argv) < 2:
        print("usage: verify_price.py <verify.json path> [--force]", file=sys.stderr)
        return 2
    target = argv[1]
    force = "--force" in argv[2:]
    repo_root = os.getcwd()

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
            status, detail = verify_record.scan_reach(rule.get("run"), repo_root)
            if status == "verb":
                rows.append((i, "REFUSED",
                             f"remote verb {detail!r} - "
                             f"declare `reach` or price by hand"))
                continue
            # Codex round 6: a command containing ANY shell metacharacter is
            # refused unconditionally, same as the gate - see
            # verify_record.py's module docstring.
            if status == "syntax":
                rows.append((i, "REFUSED",
                             "shell syntax in an undeclared rule - "
                             'declare "reach": "local" (or network/host) or price by hand'))
                continue
            if status == "wrapper":
                rows.append((i, "REFUSED",
                             f"wrapper or inline shell ({detail}) - "
                             f'declare "reach": "local" (or network/host) or price by hand'))
                continue

        if has_seconds and not force:
            rows.append((i, "SKIP",
                         f"already priced {int(rule['seconds'])}s "
                         f"(use --force to re-time)"))
            continue

        rule_env = verify_record.pinned_env(rule.get("env"))
        secs, status = _time_rule(rule.get("run"), rule_env)
        if status == "skip77":
            # No timing written: a SKIP measures nothing, and writing one
            # anyway would price a command that never actually ran,
            # underpricing the real cost for the next Stop that hits it
            # with the environment present.
            rows.append((i, "SKIP",
                         "rc 77 (environment absent) - no seconds written"))
            continue
        rule["seconds"] = secs
        changed = True
        row_status = "PRICED" if status == "ok" else "PRICED (a command failed - timed anyway)"
        rows.append((i, row_status, f"{secs}s"))

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
