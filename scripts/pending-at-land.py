#!/usr/bin/env python3
"""On a DRAFT pull request, report a stale generated file as "pending at land"
instead of failing the step.

    python3 scripts/pending-at-land.py --when <regex> [--never <regex>] -- <command...>

WHY. A build branch carries no version bump and no regenerated file until it
lands; scripts/land-pr.py writes both in one commit at merge time
(docs/landing-prs.md). check-marketplace.py --pending-bump already passes
version drift on a draft; this is the same relaxation for the generated-file
checks, so a draft is not red for something only the lander is meant to fix.

WHAT COUNTS AS PENDING. All four must hold, or the command's own exit code is
returned unchanged:
  1. this is a pull_request run and the event says `draft: true`
     (GITHUB_EVENT_NAME, GITHUB_EVENT_PATH). An event that cannot be read is
     not a draft: the step fails as the plain command would;
  2. the command exited 1 -- the exit every wrapped check uses for "stale".
     Any other non-zero exit (2 = did not run, 77 = could not tell, a signal)
     stays red: an unknown is never relaxed;
  3. at least one output line matches --when, the text that check prints for
     a stale file;
  4. no output line matches --never. crew_standards.py exits 1 for a STALE
     export and for a REFUSED one alike, so the exit code alone cannot tell
     them apart; the text can.

It never runs on a ready pull request's path to the required `check` context:
the workflow gives the draft run its own step (`if: draft == true`) beside the
unchanged plain step, and scripts/_test/pending-at-land.py holds that shape.

Exit 0: the command passed, or its failure is pending at land. Otherwise the
command's exit code; 2 for a usage error or a command that could not start.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

EXIT_USAGE = 2
STALE_RC = 1


def is_draft(environ) -> bool:
    """True only when the event file says this pull request is a draft."""
    if environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return False
    try:
        with open(environ.get("GITHUB_EVENT_PATH", ""), encoding="utf-8") as fh:
            event = json.load(fh)
    except (OSError, ValueError):
        return False
    pull = event.get("pull_request") if isinstance(event, dict) else None
    return isinstance(pull, dict) and pull.get("draft") is True


def pending(code: int, output: str, when, never, draft: bool) -> bool:
    """Whether a failed check is "pending at land" (the four conditions)."""
    if not draft or code != STALE_RC:
        return False
    lines = output.splitlines()
    if not any(when.search(line) for line in lines):
        return False
    return never is None or not any(never.search(line) for line in lines)


def parse(argv):
    """(when, never, command) or None on a usage error."""
    if "--" not in argv:
        return None
    cut = argv.index("--")
    opts, command = argv[:cut], argv[cut + 1:]
    when = never = None
    try:
        while opts:
            flag, value = opts[0], opts[1]
            if flag == "--when" and when is None:
                when = re.compile(value)
            elif flag == "--never" and never is None:
                never = re.compile(value)
            else:
                return None
            opts = opts[2:]
    except (IndexError, re.error):
        return None
    if when is None or not command:
        return None
    return when, never, command


def main(argv=None, environ=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    environ = os.environ if environ is None else environ
    parsed = parse(argv)
    if parsed is None:
        print(__doc__, file=sys.stderr)
        return EXIT_USAGE
    when, never, command = parsed
    try:
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", check=False, stdin=subprocess.DEVNULL)
    except OSError as exc:
        print(f"pending-at-land: could not start {command[0]}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    output = (done.stdout or "") + (done.stderr or "")
    sys.stdout.write(done.stdout or "")
    sys.stderr.write(done.stderr or "")
    sys.stdout.flush()
    if done.returncode == 0:
        return 0
    if pending(done.returncode, output, when, never, is_draft(environ)):
        print("pending at land: the check above is stale on this draft pull request; "
              "scripts/land-pr.py regenerates it in the land commit. A ready pull request "
              "runs the plain check and fails on it.")
        return 0
    return done.returncode if done.returncode > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
