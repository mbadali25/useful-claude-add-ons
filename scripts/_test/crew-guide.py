#!/usr/bin/env python3
"""Checks for crew's full guide and the guides' built HTML (T-0048).

`docs/guides/crew/src/guide.md` is hand-written, so this checks the claims a
script can check:

(a) every backticked token that looks like a path in THIS repository (it holds
    a `/` and ends in a known extension or in `/`) exists at HEAD, tracked or
    as a directory. Tokens with a placeholder (`<id>`, `*`, `$`, `~`) are not
    paths, nor are the files crew writes in YOUR repository (`RUNTIME`), nor
    anything inside a fenced block marked `text`;
(b) every `/crew:<name>` has `plugin/crew/commands/<name>.md`, unless its line
    names a ticket (`T-0025` style), which marks a command not landed yet;
(c) every ticket id the guide names is in `crew_keys.COMING` or in the
    guide's own "What is coming" table, so no promise goes unlisted;
(d) no line states a key count (`\\d+ keys` / `\\d+ settings`): counts belong to
    the generated reference, whose staleness check covers them;
(e) in "## Autopilot today", a sentence naming `scope.allowCliApproval` ties it
    to plan approval only: it says "approval" outside the key, and if it names
    an open question it says the question does not need it.
    `crew_autopilot.question_policy` has no `allowCliApproval` rule; only
    `approval_policy` checks it.

It also runs `docs/guides/crew/src/build.py --check`: exit 0 on the tree, 1 for
a temp copy whose guide changed by one character (naming `crew-guide.html`),
and pins every guide's built files at their version-free `crew-<name>.*`
names with no `crew-1.<n>-*` file left (C-0006), and 2 when `markdown`
cannot be imported (never 0: a check that compared nothing is not current).

Each rule has must-block and must-allow cases on temp copies of the guide.
Run: python3 scripts/_test/crew-guide.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(REPO, "docs", "guides", "crew", "src")
GUIDE = os.path.join(SRC, "guide.md")
COMMANDS = os.path.join(REPO, "plugin", "crew", "commands")
BUILD = os.path.join(SRC, "build.py")

EXTENSIONS = (".md", ".py", ".sh", ".ps1", ".json", ".jsonl", ".html", ".docx", ".pdf",
              ".yml", ".yaml", ".txt", ".log", ".toml")
# Files crew creates in the repository it manages; this repository need not
# hold them, so they are not checked against HEAD.
RUNTIME = (".crew/config.json", ".crew/crew.json", ".crew/guard.log", ".crew/metrics.md",
           ".crew/metrics.jsonl", ".work/INDEX.md", ".work/HANDOFF.md")
RUNTIME_DIRS = (".work/",)
PLACEHOLDER = re.compile(r"[<>*$~{}\s]")
TICKET = re.compile(r"\bT-\d{4}\b")
COMMAND = re.compile(r"/crew:([a-z][a-z-]*)")
COUNT = re.compile(r"\b\d+ (keys|settings)\b")
FENCE = re.compile(r"^\s*(```|~~~)(\S*)")


def tracked():
    out = subprocess.run(["git", "-C", REPO, "ls-files"], capture_output=True, text=True,
                         check=True).stdout.split("\n")
    return {p for p in out if p}


def coming_tickets():
    sys.dont_write_bytecode = True
    path = os.path.join(REPO, "plugin", "crew", "hooks", "scripts")
    if path not in sys.path:
        sys.path.insert(0, path)
    import crew_keys  # pylint: disable=import-outside-toplevel
    return {row["ticket"] for row in crew_keys.COMING}


def lines_outside_text_fences(text):
    """`(lineno, line, in_fence, fence_lang)` for every line."""
    out, fence, lang = [], None, ""
    for n, line in enumerate(text.split("\n"), 1):
        m = FENCE.match(line)
        if m:
            if fence is None:
                fence, lang = m.group(1), m.group(2)
                out.append((n, line, True, lang))
                continue
            if m.group(1) == fence:
                out.append((n, line, True, lang))
                fence, lang = None, ""
                continue
        out.append((n, line, fence is not None, lang))
    return out


def coming_table(text):
    """Ticket ids in the table rows of the guide's own "What is coming"
    section; prose there lists nothing."""
    m = re.search(r"^## What is coming\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    rows = [line for line in (m.group(1) if m else "").split("\n") if line.startswith("|")]
    return set(TICKET.findall("\n".join(rows)))


def cli_approval_claims(text):
    """Rule (e): sentences in "## Autopilot today" that tie
    `scope.allowCliApproval` to anything but plan approval."""
    m = re.search(r"^## Autopilot today\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    body = " ".join((m.group(1) if m else "").split())
    found = []
    for sentence in re.split(r"(?<=[.;])\s+", body):
        if "allowCliApproval" not in sentence:
            continue
        rest = re.sub(r"`[^`]*allowCliApproval[^`]*`", "", sentence).lower()
        if "approval" not in rest or ("question" in rest and "does not" not in rest):
            found.append(f"Autopilot today: '{sentence}' ties scope.allowCliApproval to "
                         "more than plan approval (question_policy has no such rule)")
    return found


def problems(text, files, coming, commands_dir=COMMANDS):
    found = []
    listed = coming | coming_table(text)
    for n, line, in_fence, lang in lines_outside_text_fences(text):
        for name in COMMAND.findall(line):
            if not os.path.isfile(os.path.join(commands_dir, f"{name}.md")) \
                    and not TICKET.search(line):
                found.append(f"line {n}: /crew:{name} has no command file and names no ticket")
        for ticket in TICKET.findall(line):
            if ticket not in listed:
                found.append(f"line {n}: {ticket} is in neither crew_keys.COMING nor "
                             "the guide's What is coming table")
        if COUNT.search(line):
            found.append(f"line {n}: states a key count ({COUNT.search(line).group(0)})")
        if in_fence and lang == "text":
            continue
        for token in re.findall(r"`([^`\n]+)`", line):
            if "/" not in token or PLACEHOLDER.search(token) or token.startswith("/"):
                continue
            if not (token.endswith("/") or token.endswith(EXTENSIONS)):
                continue
            if token in RUNTIME or token.startswith(RUNTIME_DIRS):
                continue
            path = token.rstrip("/")
            if path in files or any(f.startswith(path + "/") for f in files):
                continue
            found.append(f"line {n}: `{token}` is not a path at HEAD")
    return found + cli_approval_claims(text)


def run_build_check(src_dir, extra=None):
    cmd = [sys.executable, "-I", os.path.join(src_dir, "build.py"), "--check"]
    if extra is not None:
        cmd = [sys.executable, "-I", "-c", extra, os.path.join(src_dir, "build.py")]
    done = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return done.returncode, done.stdout + done.stderr


# Runs build.py --check with every `markdown` import refused.
_HIDE_MARKDOWN = (
    "import builtins, runpy, sys\n"
    "real = builtins.__import__\n"
    "def refuse(name, *a, **k):\n"
    "    if name == 'markdown' or name.startswith('markdown.'):\n"
    "        raise ImportError('markdown hidden by the test')\n"
    "    return real(name, *a, **k)\n"
    "builtins.__import__ = refuse\n"
    "sys.argv = [sys.argv[1], '--check']\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n"
)


def guide_names():
    """The guide names build.py builds, read from its GUIDES table."""
    with open(BUILD, encoding="utf-8") as fh:
        text = fh.read()
    block = text[text.index("GUIDES = {"):]
    block = block[:block.index("}")]
    return re.findall(r'^\s+"([a-z-]+)":', block, re.MULTILINE)


def copy_guides(tmp):
    """docs/guides/crew (sources and built HTML) plus doc-builder, at the
    same relative paths, so the copy's build.py resolves its own tree."""
    shutil.copytree(os.path.join(REPO, "docs", "guides", "crew"),
                    os.path.join(tmp, "docs", "guides", "crew"),
                    ignore=shutil.ignore_patterns("*.docx", "*.pdf", "archive", "__pycache__"))
    shutil.copytree(os.path.join(REPO, "skills", "doc-builder"),
                    os.path.join(tmp, "skills", "doc-builder"),
                    ignore=shutil.ignore_patterns("__pycache__", "_test"))
    return os.path.join(tmp, "docs", "guides", "crew", "src")


def main():
    failures = []

    def report(ok, label, detail=""):
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            failures.append(f"{label}: {detail}")

    files = tracked()
    coming = coming_tickets()
    with open(GUIDE, encoding="utf-8") as fh:
        guide = fh.read()

    found = problems(guide, files, coming)
    report(not found, "guide.md passes every rule", "; ".join(found))
    for heading in ("## What crew is", "## Install and update", "## Init and migrate",
                    "## The lifecycle", "## Review, the ledger and acceptance",
                    "## Refresh artifacts", "## The guards", "## Autopilot today",
                    "## Trackers", "## Multi-session work", "## Windows",
                    "## Troubleshooting", "## What is coming", "## Where the settings are"):
        report(heading in guide, f"guide.md has '{heading}'")

    base = "# Guide\n\n## What is coming\n\n| Ticket | What |\n|---|---|\n| T-0011 | x |\n"
    blocks = [
        ("a missing path", base + "\nSee `plugin/crew/commands/nosuch.md`.\n"),
        ("/crew:nosuch", base + "\nRun /crew:nosuch now.\n"),
        ("an orphan ticket id", base + "\nThis arrives with T-9998.\n"),
        ("a key count", base + "\ncrew has 129 keys.\n"),
        ("a missing directory", base + "\nLook in `docs/guides/nosuch/`.\n"),
        ("questions tied to allowCliApproval (Both)", base
         + "\n## Autopilot today\n\nPlan approval and open questions stop too, unless\n"
           "`autopilot.approval` and `autopilot.questions` allow otherwise. Both also need\n"
           "`scope.allowCliApproval: true`. Autopilot never merges.\n"),
        ("questions tied to allowCliApproval (named)", base
         + "\n## Autopilot today\n\nPlan approval and open questions also need\n"
           "`scope.allowCliApproval: true`.\n"),
    ]
    for label, text in blocks:
        got = problems(text, files, set())
        report(bool(got), f"must-block: {label}", "no problem reported")
    allows = [
        ("/crew:help (T-0011)", base + "\n`/crew:help` (T-0011) lists commands.\n"),
        ("a path in a text fence", base + "\n```text\n`plugin/crew/nosuch.md`\n```\n"),
        ("a real path and command", base + "\n`plugin/crew/CONFIG.md` and /crew:review.\n"),
        ("a runtime path", base + "\nIt writes `.crew/config.json` and `.work/tickets/`.\n"),
        ("a placeholder path", base + "\nUnder `.crew/codemap/<subsystem>.md`.\n"),
        ("a ticket in COMING", base + "\nShipping arrives with T-0011.\n"),
        ("allowCliApproval for plan approval only", base
         + "\n## Autopilot today\n\nPlan approval also needs\n"
           "`scope.allowCliApproval: true`; an open question does not. Autopilot never.\n"),
    ]
    for label, text in allows:
        got = problems(text, files, coming)
        report(not got, f"must-allow: {label}", "; ".join(got))

    code, out = run_build_check(SRC)
    report(code == 0, "build.py --check exits 0 on the tree", f"exit {code}: {out}")
    # C-0006: built guides carry no version in their names, so no release
    # ever renames them. Every guide's three files exist as crew-<name>.*,
    # and no crew-1.<n>-* file remains beside them.
    guides_dir = os.path.dirname(SRC)
    for name in guide_names():
        for ext in ("html", "docx", "pdf"):
            report(os.path.isfile(os.path.join(guides_dir, f"crew-{name}.{ext}")),
                   f"crew-{name}.{ext} is committed")
    versioned = sorted(f for f in os.listdir(guides_dir)
                       if re.match(r"crew-\d+\.\d+-", f))
    report(not versioned, "no versioned crew-<major>.<minor>-* guide file remains",
           ", ".join(versioned))
    with tempfile.TemporaryDirectory() as tmp:
        src = copy_guides(tmp)
        path = os.path.join(src, "guide.md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.replace("crew is a workflow", "crew is a workfloW", 1))
        code, out = run_build_check(src)
        report(code == 1 and "crew-guide.html" in out,
               "build.py --check exits 1 naming a changed guide", f"exit {code}: {out}")
    code, out = run_build_check(SRC, extra=_HIDE_MARKDOWN)
    report(code == 2 and "DID NOT RUN" in out,
           "build.py --check exits 2 when markdown cannot be imported", f"exit {code}: {out}")

    if failures:
        print("\ncrew-guide suite FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("crew-guide suite: all cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
