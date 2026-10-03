#!/usr/bin/env python3
"""Regression suite: every own-line `# shellcheck` comment in a tracked *.sh parses.

ShellCheck reads any comment starting `# shellcheck` as a directive. One it
cannot parse is not a local error: it reports SC1073 and stops checking the
whole file, so every finding after it goes unreported. L-0587 found two:
`scripts/install-prerequisites.sh` carried `# shellcheck disable=SC2059 - reason`
(the ` - reason` tail is not the documented trailing-comment form) and
`scripts/_test/lsp-stack-tools.sh` began a line of header prose with the word
`shellcheck/...`. Both files had been unchecked since those lines landed.

The grammar check needs nothing but Python. It reads only files git tracks, and
it checks own-line comments only. A directive trailing a code line is covered by
the real-ShellCheck cross-check instead, which runs when `shellcheck` is on PATH
(it is on GitHub's ubuntu image) and prints a visible SKIPPED line when it is
not. The cross-check writes its fixtures under `tempfile.mkdtemp` and nowhere
else.

The grammar checks each key's value, not only its shape: a directive that
parses but whose value ShellCheck rejects (`shell=bogus` is SC1103,
`disable=bogus` is SC1073) is malformed too, and the cross-check flags every
directive error code measured below, not SC1073 alone.

Known over-match, in the failing direction: the grammar reads lines, not shell
syntax, so heredoc or multi-line string text that starts `# shellcheck` is
checked as if it were a comment. ShellCheck would ignore it and this suite
fails on it; reword the line. No tracked file has such a line today.

The must-block cases are the defects this was written for; the must-allow cases
keep the grammar from failing correct lines. An empty extraction - no shell file
or no directive read - is a failure, not a pass.

Run: python3 scripts/_test/shellcheck-directives.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKERS = 4

# The in-script directive keys ShellCheck documents
# (https://github.com/koalaman/shellcheck/wiki/Directive), each with the values
# both 0.9.0 (the CI runner image's) and 0.11.0 accept without a directive
# error, measured 2026-10-02. Left out on purpose: `extended-analysis` (SC1107
# "unknown" on 0.9.0), `external-sources` (SC1144: valid only in .shellcheckrc),
# `shell=busybox` (SC1103 on 0.9.0), `enable=SC2250` (SC1125: enable takes check
# names), lowercase `sc2034` and a space after a comma (both SC1073).
_CODE = r"(?:SC)?\d+(?:-(?:SC)?\d+)?"
_VALUES = {
    "disable": rf"(?:{_CODE}|all)(?:,(?:{_CODE}|all))*",
    "enable": r"[a-z][a-z0-9-]*(?:,[a-z][a-z0-9-]*)*",
    "source": r"[^\s#]+",
    "source-path": r"[^\s#]+",
    "shell": r"(?:sh|bash|dash|ksh)",
}
KEYS = tuple(_VALUES)

TRIGGER = re.compile(r"^\s*#\s*shellcheck\b")
_PAIR = "(?:" + "|".join(f"{re.escape(k)}={v}" for k, v in _VALUES.items()) + ")"
VALID = re.compile(r"^\s*#\s*shellcheck(?:\s+" + _PAIR + r")+\s*(?:#.*)?$")

# (line, the code real ShellCheck reports for it), measured under 0.11.0 and 0.9.0.
MUST_BLOCK = (
    ("    # shellcheck disable=SC2059 - the template is ours, from GROUP_LABEL.", "SC1073"),
    ("# shellcheck/PSScriptAnalyzer equivalents in scripts/install-prerequisites.ps1.", "SC1073"),
    ("# shellcheck disable SC2059", "SC1073"),
    ("# shellcheck", "SC1073"),
    ("#shellcheck disable=SC2034 - x", "SC1073"),
    ("# shellcheck frobnicate=1", "SC1107"),
    ("# shellcheck disable=bogus", "SC1073"),
    ("# shellcheck disable=sc2034", "SC1073"),
    ("# shellcheck disable=SC2034, SC2016", "SC1073"),
    ("# shellcheck shell=bogus", "SC1103"),
    ("# shellcheck enable=SC2250", "SC1125"),
    ("# shellcheck external-sources=true", "SC1144"),
    ("# shellcheck external-sources=maybe", "SC1145"),
)

MUST_ALLOW = (
    "# shellcheck disable=SC2059 # the template is ours.",
    "# shellcheck disable=SC2034,SC2016",
    "# shellcheck source=/dev/null",
    "# shellcheck disable=SC1090 source=lib.sh",
    "  # shellcheck shell=bash",
    "# shellcheck shell=sh",
    "# shellcheck disable=all",
    "# shellcheck disable=2034",
    "# shellcheck disable=SC2034-SC2040",
    "# shellcheck enable=require-variable-braces",
    "# shellcheck source-path=SCRIPTDIR",
    "# ShellCheck/PSScriptAnalyzer equivalents in scripts/install-prerequisites.ps1.",
    "#!/usr/bin/env bash",
    'echo "# shellcheck - in a string"',
    "# a comment mentioning shellcheck later",
)

# Every code ShellCheck reported for a bad directive in the measurements above.
DIRECTIVE_CODES = ("[SC1073]", "[SC1103]", "[SC1107]", "[SC1125]", "[SC1144]", "[SC1145]")


def malformed(text: str) -> list[tuple[int, str]]:
    """(lineno, line) for every own-line `# shellcheck` comment the grammar rejects."""
    return [(n, line) for n, line in enumerate(text.splitlines(), 1)
            if TRIGGER.match(line) and not VALID.match(line)]


def tracked_shell_files() -> list[str]:
    git = shutil.which("git")
    if git is None:
        raise SystemExit("FAIL  git not on PATH - cannot list tracked shell files")
    out = subprocess.run([git, "-C", str(ROOT), "ls-files", "-z", "--", "*.sh"],
                         capture_output=True, check=True, timeout=60, env=os.environ.copy())
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


def check_cases() -> list[str]:
    failures = []
    for line, _code in MUST_BLOCK:
        if len(malformed(line)) != 1:
            failures.append(f"must-block not blocked: {line!r}")
    for line in MUST_ALLOW:
        if malformed(line):
            failures.append(f"must-allow blocked: {line!r}")
    return failures


def scan_repo(files: list[str]) -> tuple[int, list[str]]:
    directives = 0
    hits = []
    for rel in files:
        text = (ROOT / rel).read_text(encoding="utf-8", errors="strict")
        directives += sum(1 for line in text.splitlines() if TRIGGER.match(line))
        hits.extend(f"{rel}:{n}: {line.strip()}" for n, line in malformed(text))
    return directives, hits


def _shellcheck(sc: str, args: list[str], cwd: str) -> tuple[int, str]:
    """(exit status, output). ShellCheck exits 0 clean and 1 with findings; 2 and
    above mean it could not check at all, which the callers report as a failure."""
    out = subprocess.run([sc, "-f", "gcc", *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", cwd=cwd, timeout=300,
                         env=os.environ.copy(), check=False)
    return out.returncode, out.stdout + out.stderr


def cross_check(sc: str, files: list[str]) -> list[str]:
    failures = []
    version = subprocess.run([sc, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60,
                             env=os.environ.copy(), check=False).stdout
    print("shellcheck cross-check: "
          + next((v for v in version.splitlines() if v.startswith("version")), "version unknown"))
    tmp = tempfile.mkdtemp(prefix="shellcheck-directives-")
    try:
        cases = list(MUST_BLOCK) + [(line, None) for line in MUST_ALLOW]
        for i, (line, code) in enumerate(cases):
            fixture = Path(tmp, f"case{i}.sh")
            fixture.write_text(f"#!/usr/bin/env bash\n{line}\ntrue\n", encoding="utf-8",
                               newline="\n")
            status, report = _shellcheck(sc, [fixture.name], tmp)
            if status not in (0, 1):
                failures.append(f"real shellcheck could not check fixture {line!r} "
                                f"(exit {status}): {report.strip()}")
            elif code is not None and f"[{code}]" not in report:
                failures.append(f"real shellcheck did not report {code} for must-block {line!r}")
            elif code is None and any(c in report for c in DIRECTIVE_CODES):
                failures.append(f"real shellcheck rejected must-allow {line!r}: {report.strip()}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # One file per process, WORKERS at a time: on 2026-10-02, shellcheck 0.9.0,
    # one process over every tracked *.sh took 16s and the whole suite takes 7s.
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        reports = pool.map(lambda rel: _shellcheck(sc, [rel], str(ROOT)), files)
        for rel, (status, report) in zip(files, reports):
            if status not in (0, 1):
                failures.append(f"real shellcheck could not check {rel} (exit {status}): "
                                f"{report.strip()}")
            failures.extend(f"real shellcheck: {line}" for line in report.splitlines()
                            if any(c in line for c in DIRECTIVE_CODES))
    return failures


def main() -> int:
    failures = check_cases()
    files = tracked_shell_files()
    if not files:
        failures.append("no tracked *.sh file was read - an empty extraction is not a pass")
    directives, hits = scan_repo(files)
    if files and directives == 0:
        failures.append("no `# shellcheck` line was read across the tracked files - "
                        "an empty extraction is not a pass")
    failures.extend(f"malformed directive: {hit}" for hit in hits)
    sc = shutil.which("shellcheck")
    if sc is not None:
        # Absolute, because the fixture runs use the temp directory as cwd and a
        # relative PATH entry (`./bin`) would resolve against that instead.
        sc = os.path.abspath(sc)
    if sc is None:
        print("SKIPPED: shellcheck not on PATH - grammar check only, no real-ShellCheck cross-check")
    else:
        failures.extend(cross_check(sc, files))
    for failure in failures:
        print(f"FAIL  {failure}")
    cases = len(MUST_BLOCK) + len(MUST_ALLOW)
    print(f"shellcheck-directives: {cases} cases, {len(files)} files, {directives} directives, "
          f"{len(hits)} malformed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
