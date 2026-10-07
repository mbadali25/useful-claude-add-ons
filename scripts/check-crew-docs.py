#!/usr/bin/env python3
"""A crew code change touches a narrative crew doc, or says why not.

    python3 scripts/check-crew-docs.py [--root <repo>] [--pr-body-file <path>] [--base <ref>]

THE RULE (owner, 2026-09-26; CLAUDE.md "Scope discipline"). A change to
`plugin/crew/` updates every document that describes it, in the same PR, or
says why not with a line `Docs: none - <reason>`. This check enforces the
decision, not the prose: it fails a branch that changes crew CODE and neither
changes a narrative DOC nor carries a valid declaration. Whether the prose is
right stays with review.

CODE is a changed path under `plugin/crew/` that is not a Markdown file, a
test, a `_test` suite, an eval or `plugin.json`. DOCS are the narrative docs:
crew's README and CONFIG, its command, agent and SKILL.md files, its `docs/`,
and the guide sources under `docs/guides/crew/src/`. Files every crew PR
changes mechanically (`plugin/PLUGINS.md`, `CHANGELOG.md`, `BUDGETS.md`, the
code maps, the diagrams, the graph, the built guides) count neither way:
counting them would have passed 31 of 31 measured crew PRs
(docs/claude-md-evidence.md, "From Scope discipline").

WHAT COUNTS AS CHANGED. The branch's own changes, exactly as
`scripts/check-tooling-pr.py` reads them: `git diff --name-status -z
<base>...HEAD` (both sides of a rename; from the merge base, so what a merge
of the base brought in is the base's), plus every path `git status` reports.
<base> is the PR's own base branch: `--base`, else `origin/$GITHUB_BASE_REF`
(set on a pull_request run, e.g. a PR into a release branch), else
`origin/main`. Diffing a release-branch PR against main would count docs the
release branch changed, not this PR.

THE DECLARATION. `Docs: none - <reason>` (hyphen, en dash or em dash), from a
commit trailer on any commit in `<base>..HEAD`, or from the PR body when
`--pr-body-file` is given or `GITHUB_EVENT_NAME` is `pull_request` (the body is
read from the JSON at `GITHUB_EVENT_PATH`). In a body the line must start a
line. A reason that is empty or still the `<why>` placeholder is not a
declaration. A local run sees trailers only.

Exit 0: no crew code changed, a doc changed, or a valid declaration exists.
Exit 1: crew code changed with neither. Exit 77: the check could not tell -
the base is not a ref, a git call failed, or a PR body that should have
been readable was not. 77 is never a pass.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "plugin", "crew", "hooks", "scripts"))
import crew_ticket  # noqa: E402  pylint: disable=wrong-import-position

EXIT_MISSING = 77
TRAILER = "Docs"

CREW = "plugin/crew/**"
NOT_CODE = (
    "plugin/crew/**/*.md",
    "plugin/crew/tests/**",
    "plugin/crew/**/_test/**",
    "plugin/crew/evals/**",
    "plugin/crew/.claude-plugin/plugin.json",
)
DOCS = (
    "plugin/crew/README.md",
    "plugin/crew/CONFIG.md",
    "plugin/crew/commands/*.md",
    "plugin/crew/agents/*.md",
    "plugin/crew/skills/*/SKILL.md",
    "plugin/crew/docs/**",
    "docs/guides/crew/src/*.md",
)
# Never counted either way; listed so the failure message can say so.
MECHANICAL = (
    "plugin/PLUGINS.md", "CHANGELOG.md", "plugin/crew/BUDGETS.md", ".crew/codemap/**",
    "docs/diagrams/**", "graphify-out/**", "docs/guides/crew/* (built guides)",
)

# `Docs: none - reason`: the value after `Docs:` in a trailer, or a whole line
# (leading spaces allowed) in a PR body.
_VALUE = re.compile(r"^none\s*[-–—](.*)$", re.IGNORECASE)
_BODY_LINE = re.compile(r"^[ \t]*Docs:[ \t]*(.*)$", re.MULTILINE)


class CouldNotTell(Exception):
    """The input the verdict needs could not be read."""


def _git(root: str, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, check=False)
    except OSError as exc:  # git missing or not startable: could not tell, never exit 1
        raise CouldNotTell(f"git could not start ({exc})") from exc


def base_ref(environ, base: str | None = None) -> str:
    """The ref the branch is diffed against: `--base`, else the PR's base
    branch (`origin/$GITHUB_BASE_REF`), else origin/main."""
    if base:
        return base
    pr_base = (environ.get("GITHUB_BASE_REF") or "").strip()
    return f"origin/{pr_base}" if pr_base else "origin/main"


def changed_paths(root: str, base: str = "origin/main") -> list[str]:
    """The branch's own changed paths: merge base to HEAD, plus the working tree.
    The same reading as scripts/check-tooling-pr.py's changed_paths (copied, not
    imported: that file is harness and is not edited for this)."""
    paths: set[str] = set()
    diff = _git(root, "diff", "--name-status", "-z", f"{base}...HEAD")
    if diff.returncode != 0:
        raise CouldNotTell(f"git diff {base}...HEAD failed: {diff.stderr.strip()}")
    fields = [f for f in diff.stdout.split("\0") if f]
    i = 0
    while i < len(fields):
        status = fields[i]
        width = 2 if status[:1] in ("R", "C") else 1
        paths.update(fields[i + 1:i + 1 + width])
        i += 1 + width
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status.returncode != 0:
        raise CouldNotTell(f"git status failed: {status.stderr.strip()}")
    entries = status.stdout.split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.add(entry[3:])
        if set(entry[:2]) & {"R", "C"} and i < len(entries):
            paths.add(entries[i])
            i += 1
    return sorted(paths)


def trailer_values(root: str, base: str = "origin/main") -> list[str]:
    """Every `Docs:` trailer value on the branch's own commits."""
    log = _git(root, "log", f"--format=%(trailers:key={TRAILER},valueonly)", f"{base}..HEAD")
    if log.returncode != 0:
        raise CouldNotTell(f"git log {base}..HEAD failed: {log.stderr.strip()}")
    return [line.strip() for line in log.stdout.splitlines() if line.strip()]


def pr_body(pr_body_file: str | None, environ) -> str | None:
    """The PR body, None when there is none to read, CouldNotTell when there
    should be one and it cannot be read."""
    if pr_body_file is not None:
        try:
            with open(pr_body_file, encoding="utf-8") as fh:
                return fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise CouldNotTell(f"--pr-body-file {pr_body_file}: {exc}") from exc
    if environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return None
    event_path = environ.get("GITHUB_EVENT_PATH", "")
    try:
        with open(event_path, encoding="utf-8") as fh:
            event = json.load(fh)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise CouldNotTell(f"the pull_request event at GITHUB_EVENT_PATH={event_path!r} "
                           f"could not be read: {exc}") from exc
    pull = event.get("pull_request") if isinstance(event, dict) else None
    if not isinstance(pull, dict):
        raise CouldNotTell("the pull_request event has no pull_request object")
    body = pull.get("body")
    if body is None:  # GitHub sends null for an empty description
        return ""
    if not isinstance(body, str):
        raise CouldNotTell(f"the pull_request event's body is a {type(body).__name__}, not text")
    return body


def declaration(value: str) -> tuple[bool, str]:
    """(valid, reason) for one `Docs:` value. (False, "") when it is not a
    `none` declaration at all."""
    match = _VALUE.match(value.strip())
    if not match:
        return False, ""
    reason = match.group(1).strip()
    return bool(reason) and not reason.startswith("<"), reason


def find_declaration(trailers: list[str], body: str | None) -> tuple[str | None, str, list[str]]:
    """(source or None, reason, invalid declarations seen)."""
    invalid: list[str] = []
    sources = [("commit trailer", v) for v in trailers]
    if body:
        sources += [("PR body", m.group(1)) for m in _BODY_LINE.finditer(body)]
    for source, value in sources:
        valid, reason = declaration(value)
        if valid:
            return source, reason, invalid
        if _VALUE.match(value.strip()) or value.strip().lower() == "none":
            invalid.append(f"{source}: `Docs: {value.strip()}`")
    return None, "", invalid


def _matches(path: str, globs) -> bool:
    return any(crew_ticket.path_matches(path, glob) for glob in globs)


def check(root: str, pr_body_file: str | None = None, environ=None,
          base: str | None = None) -> tuple[int, list[str]]:
    """(exit code, output lines) for the branch checked out at `root`."""
    environ = os.environ if environ is None else environ
    base = base_ref(environ, base)
    try:
        if _git(root, "rev-parse", "--verify", "-q", f"{base}^{{commit}}").returncode != 0:
            return EXIT_MISSING, [f"TOOL MISSING: {base} is not a ref here, so the crew-docs "
                                  "check DID NOT RUN. This is a missing ref, not a pass."]
        paths = changed_paths(root, base)
        code = [p for p in paths if _matches(p, (CREW,)) and not _matches(p, NOT_CODE)]
        if not code:
            return 0, ["crew-docs: no crew code changed"]
        docs = [p for p in paths if _matches(p, DOCS)]
        if docs:
            return 0, [f"crew-docs: OK - {len(code)} crew code path(s), "
                       f"{len(docs)} narrative doc(s) changed"]
        trailers = trailer_values(root, base)
        source, reason, invalid = find_declaration(trailers, None)
        if not source:
            # Read only when a trailer did not settle it: an unreadable body
            # is "could not tell", never "no declaration".
            source, reason, invalid = find_declaration(trailers, pr_body(pr_body_file, environ))
    except CouldNotTell as exc:
        return EXIT_MISSING, [f"TOOL MISSING: {exc}; the crew-docs check DID NOT RUN."]
    if source:
        return 0, [f"crew-docs: OK - no narrative doc changed, declared in the {source}: "
                   f"Docs: none - {reason}"]
    lines = ["crew-docs: FAIL - crew code changed and no narrative crew doc did:"]
    lines += [f"  {p}" for p in code]
    lines += ["Update one of these, if the change alters what they describe:"]
    lines += [f"  {g}" for g in DOCS]
    lines += ["(not counted either way: " + ", ".join(MECHANICAL) + ")",
              "Or declare why none applies, with the line",
              "  Docs: none - <the reason>",
              "either at the start of a line in the PR body (CI reads it), or as a",
              "commit trailer on any commit of the branch (the only form a local run sees):",
              "  git commit --allow-empty -m 'docs: none needed' -m 'Docs: none - <the reason>'"]
    if invalid:
        lines += ["Declarations seen but not valid (no reason, or the <placeholder> left in):"]
        lines += [f"  {d}" for d in invalid]
    return 1, lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--pr-body-file")
    parser.add_argument("--base", help="ref to diff against (default: origin/$GITHUB_BASE_REF, "
                                       "else origin/main)")
    args = parser.parse_args(argv)
    code, lines = check(os.path.abspath(args.root), args.pr_body_file, base=args.base)
    stream = sys.stderr if code == EXIT_MISSING else sys.stdout
    for line in lines:
        print(line, file=stream)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
