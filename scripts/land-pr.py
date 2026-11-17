#!/usr/bin/env python3
"""Land-prep one pull request: the version bump and every generated file, as
ONE commit, made at merge time instead of on the open branch.

    python3 scripts/land-pr.py <PR> [--push] [--keep] [--report FILE]
                               [--trailer "Key: value"]... [--skip-check NAME]...
                               [--accept-skip NAME]... [--title TEXT] [--kind WORD]
                               [--in-place DIR] [--repo DIR] [--remote NAME]
                               [--scratch DIR] [--pr-json FILE]

WHY. Every open branch used to carry its own version bump and about a dozen
generated files (README "What's new", the standards exports, .claude/rules/,
the built guides, the opt-in inventory, the BUDGETS.md count, CHANGELOG
re-bump lines), so every PR conflicted with every other and each re-bump owed
a changelog line (scripts/check-changelog.py). A draft PR already passes
version drift as "pending at land" (check-marketplace.py --pending-bump); this
script is the land half. docs/landing-prs.md is the contributor text.

WHAT IT DOES, in a throwaway LF checkout (never the caller's worktree):
  1. fetches <base> (default main), the PR head and every other open PR head;
  2. merges origin/<base> into the PR branch (a merge commit, never a rebase).
     A conflict is resolved only where the file is generated or the two sides
     differ in nothing but a version or a count (POLICY below); anything else
     stops the run with the paths named;
  3. for every marketplace entry whose source the PR changes, sets the version
     one patch above <base> AND above every other open PR head, in
     marketplace.json, the plugin's plugin.json and each
     `<!-- claim: plugin-version:<name> -->` row;
  4. re-numbers `<name> <old version>` and `<name> NEXT` on the Markdown lines
     the PR itself added, folds changelog.d/*.md fragments into CHANGELOG.md,
     writes an entry from the PR title when the PR has none, and one
     `re-bump only` line per interim number the branch already set;
  5. runs the generators (GENERATORS below) and re-measures BUDGETS.md;
  6. commits the result as one commit, then runs the checks (CHECKS below);
  7. with --push, and only when every check passed, pushes that commit to the
     PR branch with a plain `git push` (no force, so a moved branch rejects).

WHAT IT NEVER DOES. It never merges the pull request (the owner merges), never
pushes to <base>, never force-pushes, never marks a draft ready, and never
re-runs `graphify update .` (CLAUDE.md "Memory": that command owns its pair).

REFUSALS (exit 2, nothing changed): the PR is not open, comes from a fork, or
its head branch is the base branch or main/master; the fetched head is not the
head GitHub reported; an open PR's head could not be read (its version is then
unknown, and an unknown is never treated as "lower"); <base> moved between the
merge and the push. --in-place also refuses a dirty tree, a checkout on
another branch, and a CRLF checkout (core.autocrlf), where generated files
would not be the bytes CI compares.

Exit 0: landed (--push), or a clean dry run (the default: nothing is pushed).
Exit 1: a conflict needs a person, a generator failed, a check failed, or the
push was rejected. Exit 2: refused. Exit 3: could not tell -- a check was
skipped (exit 77), timed out or did not run, or the DOCX/PDF pass was skipped;
nothing is pushed unless each such step is named with --accept-skip.

--pr-json FILE replaces the two `gh` calls with {"pr": {...}, "open": [...]}
(the suite uses it; so can a host without gh).
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MARKETPLACE = ".claude-plugin/marketplace.json"
CHANGELOG = "CHANGELOG.md"
FRAGMENTS = "changelog.d"
PLACEHOLDER = "NEXT"
PROTECTED = ("main", "master")
EXIT_OK, EXIT_FAIL, EXIT_REFUSED, EXIT_CNT, EXIT_SKIP = 0, 1, 2, 3, 77
PASS, FAIL, SKIP, CNT = "PASS", "FAIL", "SKIP", "COULD-NOT-TELL"
PY = "{python}"

VERSION_JSON = re.compile(r'"version"\s*:\s*"[^"]*"')
VERSION_ROW = re.compile(r"^\|\s*\*\*Version\*\*\s*\|\s*([0-9][0-9.]*)")
LINES_CLAIM = re.compile(r"totals [\d,]+ lines across \d+ files")
CLAIM_WINDOW = 12  # check-marketplace.py BIND_WINDOW

# How a conflicted path is resolved when origin/<base> is merged in. "theirs"
# is <base>'s side. Anything not listed, or a hunk a rule does not cover, is a
# real conflict: the run stops and a person resolves it.
#   file    the whole file is generated (or owned by another tool): take
#           <base>'s, the generators rewrite it afterwards;
#   masked  a hunk is taken from <base> only when its two sides are equal once
#           the pattern is blanked (a version or a count, re-set afterwards);
#   block   a hunk is taken from <base> only inside the generated block;
#   union   both sides are kept, the PR's lines first (CHANGELOG.md: both
#           sides add entries at the same place).
POLICY = (
    (".claude/rules/*", "file", None),
    ("REVIEW.md", "file", None),
    (".cursor/BUGBOT.md", "file", None),
    ("docs/review-rules/*", "file", None),
    ("docs/guides/crew/*.html", "file", None),
    ("docs/guides/crew/*.docx", "file", None),
    ("docs/guides/crew/*.pdf", "file", None),
    ("plugin/crew/tests/data/optin_inventory.json", "file", None),
    ("graphify-out/*", "file", None),
    (MARKETPLACE, "masked", VERSION_JSON),
    ("plugin/*/.claude-plugin/plugin.json", "masked", VERSION_JSON),
    ("plugin/PLUGINS.md", "masked", re.compile(r"\*\*Version\*\*\s*\|\s*[0-9][0-9.]*")),
    ("plugin/crew/BUDGETS.md", "masked", LINES_CLAIM),
    ("README.md", "block", (re.compile(r"<!-- BEGIN CHANGELOG\.md -->"),
                            re.compile(r"<!-- END CHANGELOG\.md -->"))),
    ("AGENTS.md", "block", (re.compile(r"<!-- crew-standards-export start\b"),
                            re.compile(r"<!-- crew-standards-export end\b"))),
    (CHANGELOG, "union", None),
)

# (name, write argv, check argv or None). With a check argv the write runs only
# when the check exits 1 (stale); any other non-zero check exit is a failure,
# never "current". build.py exits 3 when it rebuilt the HTML but had no Word or
# LibreOffice for the DOCX/PDF pass: recorded as COULD-NOT-TELL (GUIDE_PARTIAL).
GENERATORS = (
    ("config-reference", (PY, "docs/guides/crew/src/config_reference.py", "--write"),
     (PY, "docs/guides/crew/src/config_reference.py", "--check")),
    ("crew-guides", (PY, "docs/guides/crew/src/build.py"),
     (PY, "docs/guides/crew/src/build.py", "--check")),
    ("crew-rules", (PY, "plugin/crew/hooks/scripts/crew_instructions.py", "rules", "--root", "."),
     None),
    ("standards-export",
     (PY, "plugin/crew/hooks/scripts/crew_standards.py", "export", "--write", "--root", "."), None),
    ("optin-inventory", (PY, "plugin/crew/tests/optin_inventory.py", "--write"), None),
    ("budgets", None, None),  # internal: remeasure_budgets()
    ("readme-blocks", (PY, "scripts/sync-updates.py"), None),
)
GUIDE_PARTIAL = 3

# (name, argv, timeout seconds, exit codes that mean "the check did not run").
CHECKS = (
    ("check-instructions", (PY, "scripts/check_instructions.py"), 300, ()),
    ("check-marketplace", (PY, "scripts/check-marketplace.py"), 600, ()),
    ("check-crew-docs", (PY, "scripts/check-crew-docs.py", "--pr-body-file", "{pr_body}"), 300, ()),
    ("check-changelog", (PY, "scripts/check-changelog.py"), 300, ()),
    ("crew-guides-fresh", (PY, "docs/guides/crew/src/build.py", "--check"), 600, (2,)),
    ("config-reference-fresh", (PY, "docs/guides/crew/src/config_reference.py", "--check"), 300,
     (2,)),
    ("standards-export-fresh",
     (PY, "plugin/crew/hooks/scripts/crew_standards.py", "export", "--check", "--root", "."), 300,
     ()),
    ("readme-blocks-fresh", (PY, "scripts/sync-updates.py", "--check"), 300, (2,)),
    ("crew-rules-fresh",
     (PY, "plugin/crew/hooks/scripts/crew_instructions.py", "rules", "--root", ".", "--check"),
     300, ()),
    ("optin-inventory-fresh", (PY, "plugin/crew/tests/optin_inventory.py", "--check"), 600, ()),
    ("check-tooling-pr", (PY, "scripts/check-tooling-pr.py"), 300, ()),
    ("pylint", (PY, "scripts/run-pylint.py"), 2400, ()),
)
GENERATOR_TIMEOUT = 1800
HIGHEST = {}  # entry name -> "#<pr> at <version>", when an open PR head is above <base>


class Refusal(Exception):
    """The run must not start or must not push: exit 2."""


class Failure(Exception):
    """A step failed or a conflict needs a person: exit 1."""


# ---- processes ----------------------------------------------------------------

def run(argv, cwd, timeout=600, env=None):
    """(rc or None on timeout / cannot start, combined output)."""
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, env=env, check=False,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout:g}s"
    except OSError as exc:
        return None, f"could not start: {exc}"
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def git(cwd, *args, check=True, timeout=600):
    """git's stdout. check=True raises Failure on a non-zero exit."""
    rc, out = run(["git", *args], cwd, timeout=timeout)
    if check and rc != 0:
        raise Failure(f"git {' '.join(args)} -> {rc}: {out.strip()}")
    return out if rc == 0 else ""


def git_rc(cwd, *args, timeout=600):
    return run(["git", *args], cwd, timeout=timeout)


def read_text(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def write_text(path, text):
    """Temp file + os.replace, LF kept as written (CLAUDE.md landmines)."""
    tmp = f"{path}.land-pr.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)


def remove_tree(path):
    """rmtree that survives git's read-only object files on Windows."""
    for base, _dirs, files in os.walk(path):
        for name in files:
            try:
                os.chmod(os.path.join(base, name), stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
    shutil.rmtree(path)


# ---- versions -------------------------------------------------------------------

def parse_version(text):
    if not isinstance(text, str) or not re.fullmatch(r"\d+(\.\d+)*", text):
        raise Refusal(f"version {text!r} is not dotted numbers; refusing to guess the next one")
    return tuple(int(p) for p in text.split("."))


def bump_patch(text):
    parts = list(parse_version(text))
    parts[-1] += 1
    return ".".join(str(p) for p in parts)


def next_version(base, own, others):
    """One patch above the highest of <base>'s version, the PR's own and every
    OTHER open PR head's. `others` holds strings; None in it is refused by the
    caller before this is reached."""
    highest = max([base, own, *others], key=parse_version)
    return bump_patch(highest)


def entries_at(root, rev):
    """{name: entry dict} from marketplace.json at `rev`; None when it is absent
    or does not parse there (could not tell, never "no entries")."""
    rc, out = git_rc(root, "show", f"{rev}:{MARKETPLACE}")
    if rc != 0:
        return None
    try:
        return {p["name"]: p for p in json.loads(out)["plugins"]}
    except (ValueError, KeyError, TypeError):
        return None


def source_dir(entry):
    source = entry.get("source")
    if not isinstance(source, str) or not source.startswith("./"):
        return None
    return source[2:].rstrip("/")


def version_set_at(root, name, version):
    """The commit on HEAD's first-parent line that set `name` to `version`."""
    revs = git(root, "log", "--first-parent", "--format=%H", "-n", "400", "HEAD").split()
    found = None
    for rev in revs:
        entries = entries_at(root, rev)
        if entries is None or name not in entries or entries[name].get("version") != version:
            break
        found = rev
    return found


def plan_versions(root, base_ref, pr_head, fork_point, other_heads):
    """[(name, source, base version, the PR head's version, new version or
    None, whether the branch itself set the PR head's version)] for every entry
    whose source the PR changes. new is None when the PR's own number already
    stands above everything and nothing changed since it was set. `pr_head` is
    the PR's head before the merge (a conflict may have reset the merged
    file to the base's number); `fork_point` is where the branch left <base>."""
    base_entries = entries_at(root, base_ref)
    if base_entries is None:
        raise Refusal(f"{MARKETPLACE} at {base_ref} is absent or does not parse")
    pre_entries = entries_at(root, pr_head) or {}
    fork_entries = entries_at(root, fork_point) or {}
    HIGHEST.clear()
    try:
        head_entries = {p["name"]: p for p in
                        json.loads(read_text(os.path.join(root, MARKETPLACE)))["plugins"]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Failure(f"{MARKETPLACE} on the merged branch does not parse: {exc}") from exc
    plan = []
    for name, entry in head_entries.items():
        source = source_dir(entry)
        if source is None or name not in base_entries:
            continue  # a remote source, or a new entry: it keeps the version it declares
        rc, out = git_rc(root, "diff", "--quiet", base_ref, "HEAD", "--", source)
        if rc == 0:
            continue
        if rc != 1:
            raise Failure(f"git diff {base_ref} HEAD -- {source} -> {rc}: {out.strip()}")
        base, merged = base_entries[name].get("version"), entry.get("version")
        own = pre_entries.get(name, {}).get("version", merged)
        branch_set = own != fork_entries.get(name, {}).get("version", own)
        others, holder = [], None
        for number, entries in other_heads.items():
            if entries is None:
                raise Refusal(f"open PR #{number}: {MARKETPLACE} at its head is absent or does "
                              f"not parse, so {name}'s version there is unknown")
            if name in entries and "version" in entries[name]:
                others.append(entries[name]["version"])
                if parse_version(others[-1]) == max(parse_version(v) for v in others):
                    holder = number
        floor = max([base, *others], key=parse_version)
        if others and parse_version(floor) > parse_version(base):
            HIGHEST[name] = f"#{holder} at {floor}"
        new = next_version(base, own, others)
        if merged == own and parse_version(own) > parse_version(floor):
            set_at = version_set_at(root, name, own)
            if set_at and git_rc(root, "diff", "--quiet", set_at, "HEAD", "--", source)[0] == 0:
                new = None
        plan.append((name, source, base, own, new, branch_set))
    return plan


def set_marketplace_version(root, name, new):
    path = os.path.join(root, MARKETPLACE)
    text = read_text(path)
    before = json.loads(text)
    at = re.search(r'"name"\s*:\s*' + re.escape(json.dumps(name)), text)
    if not at:
        raise Failure(f"{MARKETPLACE}: no entry named {name!r} to bump")
    nxt = re.compile(r'"name"\s*:').search(text, at.end())
    span = VERSION_JSON.search(text, at.end(), nxt.start() if nxt else len(text))
    if not span:
        raise Failure(f"{MARKETPLACE}: entry {name!r} has no version line to bump")
    text = text[:span.start()] + f'"version": "{new}"' + text[span.end():]
    after = json.loads(text)
    for entry in before["plugins"]:
        if entry["name"] == name:
            entry["version"] = new
    if after != before:
        raise Failure(f"{MARKETPLACE}: bumping {name!r} would change something else; not written")
    write_text(path, text)


def set_plugin_json_version(root, source, new):
    """True when <source>/.claude-plugin/plugin.json exists and was bumped."""
    path = os.path.join(root, source, ".claude-plugin", "plugin.json")
    if not os.path.isfile(path):
        return False
    text = read_text(path)
    span = VERSION_JSON.search(text)
    if not span:
        raise Failure(f"{source}/.claude-plugin/plugin.json has no version line to bump")
    text = text[:span.start()] + f'"version": "{new}"' + text[span.end():]
    if json.loads(text).get("version") != new:
        raise Failure(f"{source}/.claude-plugin/plugin.json: the first version line is not the "
                      "plugin's own; not written")
    write_text(path, text)
    return True


def set_claim_rows(root, name, new):
    """Every `| **Version** |` row bound to a plugin-version:<name> marker."""
    rc, out = git_rc(root, "grep", "-l", "-F", f"claim: plugin-version:{name}", "--", "*.md")
    changed = []
    for rel in (out.split("\n") if rc == 0 else []):
        rel = rel.strip()
        if not rel:
            continue
        path = os.path.join(root, rel)
        lines = read_text(path).split("\n")
        dirty = False
        for i, line in enumerate(lines):
            if not re.search(r"<!--\s*claim:\s*plugin-version:" + re.escape(name) + r"\s*-->", line):
                continue
            for j in range(i, min(i + CLAIM_WINDOW + 1, len(lines))):
                row = VERSION_ROW.match(lines[j])
                if row:
                    if row.group(1) != new:
                        lines[j] = lines[j][:row.start(1)] + new + lines[j][row.end(1):]
                        dirty = True
                    break
        if dirty:
            write_text(path, "\n".join(lines))
            changed.append(rel)
    return changed


# ---- merge conflicts --------------------------------------------------------------

def policy_for(rel):
    for pattern, kind, arg in POLICY:
        if fnmatch.fnmatchcase(rel, pattern):
            return kind, arg
    return None, None


def split_conflicts(text):
    """[("text", str) | ("conflict", ours, theirs)] from a file with merge
    markers (conflictStyle=merge), or None when the markers do not pair up."""
    out, buf, ours, theirs, state = [], [], [], [], "text"
    for line in text.splitlines(keepends=True):
        if line.startswith("<<<<<<< ") and state == "text":
            out.append(("text", "".join(buf)))
            buf, ours, theirs, state = [], [], [], "ours"
        elif line.startswith("=======") and line.strip() == "=======" and state == "ours":
            state = "theirs"
        elif line.startswith(">>>>>>> ") and state == "theirs":
            out.append(("conflict", "".join(ours), "".join(theirs)))
            state = "text"
        elif state == "ours":
            ours.append(line)
        elif state == "theirs":
            theirs.append(line)
        else:
            buf.append(line)
    if state != "text":
        return None
    out.append(("text", "".join(buf)))
    return out


def _block_side_ok(side, inside, start, end):
    """(ok, inside afterwards) for one side of a hunk under a block rule."""
    lines = side.splitlines()
    first = next((ln for ln in lines if ln.strip()), "")
    if not inside and not start.search(first):
        return False, inside
    for i, line in enumerate(lines):
        if end.search(line):
            return not any(ln.strip() for ln in lines[i + 1:]), False
    return True, True


def resolve_text(text, kind, arg):
    """The resolved text, or None when a hunk is not one the rule covers."""
    parts = split_conflicts(text)
    if parts is None:
        return None
    out, inside = [], False
    for part in parts:
        if part[0] == "text":
            out.append(part[1])
            if kind == "block":
                for line in part[1].splitlines():
                    if arg[0].search(line):
                        inside = True
                    if arg[1].search(line):
                        inside = False
            continue
        _, ours, theirs = part
        if kind == "union":
            # A heading needs a blank line above it once the PR's lines sit there.
            gap = "\n" if (ours and not ours.endswith("\n\n") and theirs.startswith("#")) else ""
            out.append(ours + gap + theirs)
        elif kind == "masked":
            if arg.sub("", ours) != arg.sub("", theirs):
                return None
            out.append(theirs)
        elif kind == "block":
            ok_ours, _ = _block_side_ok(ours, inside, arg[0], arg[1])
            ok_theirs, inside = _block_side_ok(theirs, inside, arg[0], arg[1])
            if not (ok_ours and ok_theirs):
                return None
            out.append(theirs)
        else:
            return None
    return "".join(out)


def resolve_conflicts(root):
    """Resolve what POLICY covers. Returns (resolved notes, unresolved paths)."""
    listed = git(root, "diff", "--name-only", "--diff-filter=U", "-z").split("\0")
    resolved, unresolved = [], []
    for rel in [p for p in listed if p]:
        kind, arg = policy_for(rel)
        if kind is None:
            unresolved.append(rel)
            continue
        if kind == "file":
            if git_rc(root, "cat-file", "-e", f":3:{rel}")[0] == 0:
                git(root, "checkout", "--theirs", "--", rel)
                git(root, "add", "--", rel)
            else:
                git(root, "rm", "-q", "--", rel)
            resolved.append(f"{rel}: took the base branch's copy (generated; rewritten below)")
            continue
        path = os.path.join(root, rel)
        try:
            text = read_text(path)
        except (OSError, UnicodeError):
            unresolved.append(rel)
            continue
        fixed = resolve_text(text, kind, arg)
        if fixed is None:
            unresolved.append(rel)
            continue
        write_text(path, fixed)
        git(root, "add", "--", rel)
        resolved.append(f"{rel}: {kind} rule")
    return resolved, unresolved


def merge_base_branch(root, base_ref, head_branch):
    """Merge base_ref into the checked-out PR branch. Returns notes."""
    before = git(root, "rev-parse", "HEAD").strip()
    short = git(root, "rev-parse", "--short", base_ref).strip()
    message = f"Merge {base_ref} {short} into {head_branch} (land-pr)"
    rc, out = git_rc(root, "-c", "rerere.enabled=false", "-c", "merge.conflictStyle=merge",
                     "merge", "--no-edit", "-m", message, base_ref)
    if rc == 0:
        moved = git(root, "rev-parse", "HEAD").strip() != before
        return [f"merged {base_ref} {short}" if moved else f"already contains {base_ref} {short}"]
    resolved, unresolved = resolve_conflicts(root)
    if unresolved:
        git_rc(root, "merge", "--abort")
        raise Failure("merging " + base_ref + " conflicts in files this script does not resolve; "
                      "a person merges these and re-runs:\n  " + "\n  ".join(sorted(unresolved))
                      + ("\n(resolvable by rule: " + ", ".join(r.split(":")[0] for r in resolved)
                         + ")" if resolved else ""))
    if not resolved:
        git_rc(root, "merge", "--abort")
        raise Failure(f"git merge {base_ref} -> {rc}: {out.strip()}")
    git(root, "commit", "--no-edit", "-q")
    return [f"merged {base_ref} {short}; conflicts resolved by rule:"] + ["  " + r for r in resolved]


# ---- changelog and prose ------------------------------------------------------------

def token_re(name, old):
    return re.compile(r"(?<![\w.-])(`?" + re.escape(name) + r"`?[\s:]*v?)" + re.escape(old)
                      + r"(?![\w]|\.\d)")


def added_lines(root, base_ref):
    """{path: set of 1-based line numbers the PR adds} for tracked *.md files."""
    out = git(root, "diff", "-U0", "--no-color", "--no-renames", base_ref, "HEAD", "--", "*.md")
    found, current = {}, None
    for line in out.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@") and current:
            hunk = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", line)
            if hunk:
                start, count = int(hunk.group(1)), int(hunk.group(2) or "1")
                found.setdefault(current, set()).update(range(start, start + count))
    return found


def renumber(root, base_ref, name, olds, new):
    """Rewrite `<name> <old>` to `<name> <new>` on lines the PR added."""
    changed = []
    patterns = [token_re(name, old) for old in olds]
    for rel, numbers in sorted(added_lines(root, base_ref).items()):
        if policy_for(rel)[0] == "file":
            continue  # generated: rewritten by its generator
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        lines = read_text(path).split("\n")
        dirty = False
        for number in numbers:
            if number > len(lines):
                continue
            line = lines[number - 1]
            for pattern in patterns:
                line = pattern.sub(lambda m: m.group(1) + new, line)
            if line != lines[number - 1]:
                lines[number - 1], dirty = line, True
        if dirty:
            write_text(path, "\n".join(lines))
            changed.append(rel)
    return changed


def _unreleased(lines):
    """(index of the `## [Unreleased]` heading, index of its first `###` or the
    next `## ` heading / end)."""
    try:
        top = next(i for i, ln in enumerate(lines) if ln.startswith("## [Unreleased]"))
    except StopIteration as exc:
        raise Failure(f"{CHANGELOG} has no `## [Unreleased]` heading to add to") from exc
    first = next((i for i in range(top + 1, len(lines))
                  if lines[i].startswith("### ") or lines[i].startswith("## ")), len(lines))
    return top, first


def insert_entry(text, entry):
    """`entry` (a `###` block) as the first entry under `## [Unreleased]`."""
    lines = text.split("\n")
    _, first = _unreleased(lines)
    block = entry.strip("\n").split("\n") + [""]
    return "\n".join(lines[:first] + block + lines[first:])


def insert_ledger(text, ledger_lines):
    """Re-number lines directly under `## [Unreleased]`, before its first `###`."""
    lines = text.split("\n")
    top, _ = _unreleased(lines)
    at = top + 1
    while at < len(lines) and not lines[at].strip():
        at += 1
    pad = [] if at < len(lines) and lines[at].startswith("- ") else [""]
    return "\n".join(lines[:top + 1] + [""] + list(ledger_lines) + pad + lines[at:])


def clean_title(title):
    title = re.sub(r"^[a-z]+(\([^)]*\))?!?:\s*", "", title.strip())
    title = re.sub(r"\s*\((?:crew\s+)?v?\d+(?:\.\d+)+[^()]*\)\s*$", "", title)
    return title.rstrip(".") or "untitled change"


def load_changelog_checker():
    spec = importlib.util.spec_from_file_location("check_changelog_for_land",
                                                  os.path.join(HERE, "check-changelog.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fold_fragments(root, bumps):
    """changelog.d/*.md -> CHANGELOG.md entries; the fragments are removed."""
    folder = os.path.join(root, FRAGMENTS)
    if not os.path.isdir(folder):
        return []
    names = sorted(n for n in os.listdir(folder) if n.endswith(".md") and n.lower() != "readme.md")
    path = os.path.join(root, CHANGELOG)
    text = read_text(path)
    for fragment in reversed(names):
        body = read_text(os.path.join(folder, fragment)).replace("\r\n", "\n")
        for name, new in bumps.items():
            body = token_re(name, PLACEHOLDER).sub(lambda m, n=new: m.group(1) + n, body)
        if not body.lstrip().startswith("### "):
            raise Failure(f"{FRAGMENTS}/{fragment} does not start with a `### ` entry heading")
        text = insert_entry(text, body)
        os.remove(os.path.join(folder, fragment))
    if names:
        write_text(path, text)
    return [f"{FRAGMENTS}/{n}" for n in names]


def write_changelog(root, base_ref, pr, bumps, kind, title, interim):
    """The entry and the re-bump lines this land owes. `interim` is the
    {(name, version)} the branch set before this commit (check-changelog's
    own reading). Returns notes."""
    checker = load_changelog_checker()
    path = os.path.join(root, CHANGELOG)
    if not os.path.isfile(path):
        raise Failure(f"no {CHANGELOG} to add the entry to")
    notes = [f"folded {n}" for n in fold_fragments(root, bumps)]
    text = read_text(path).replace("\r\n", "\n")
    for name, new in bumps.items():
        if not checker.covered(text, name, new):
            entry = (f"### {kind} — {name} {new}: {title} (#{pr['number']})\n\n"
                     f"- **Summary.** `{name}` {new}: {title}.\n")
            text = insert_entry(text, entry)
            notes.append(f"wrote a {CHANGELOG} entry for {name} {new} from the PR title "
                         "(the PR carried none)")
    ledger = []
    for name, version in sorted(interim):
        if bumps.get(name) in (None, version) or checker.covered(text, name, version):
            continue
        ledger.append(f"- {name} {version}: re-bump only - interim number on the "
                      f"{pr['headRefName']} branch (#{pr['number']}), never on {base_ref}; "
                      f"the change is recorded under {name} {bumps[name]}")
    if ledger:
        text = insert_ledger(text, ledger)
        notes.append(f"wrote {len(ledger)} re-bump line(s): "
                     + ", ".join(ln.split(":")[0][2:] for ln in ledger))
    write_text(path, text)
    return notes


def remeasure_budgets(root):
    """plugin/crew/BUDGETS.md's `crew-markdown-lines` claim, re-counted the way
    check-marketplace.py counts it (tracked plugin/crew/*.md, splitlines)."""
    rel = "plugin/crew/BUDGETS.md"
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        return "absent"
    rc, out = git_rc(root, "-c", "core.quotepath=off", "ls-files", "-z", "plugin/crew/*.md")
    if rc != 0:
        raise Failure(f"git ls-files plugin/crew/*.md -> {rc}: {out.strip()}")
    files = [p for p in out.split("\0") if p]
    total = sum(len(read_text(os.path.join(root, p)).splitlines()) for p in files)
    text = read_text(path)
    claim = f"totals {total:,} lines across {len(files)} files"
    if not LINES_CLAIM.search(text):
        raise Failure(f"{rel}: no `totals N lines across M files` line to re-measure")
    fixed = LINES_CLAIM.sub(claim, text, count=1)
    if fixed == text:
        return "current"
    write_text(path, fixed)
    return claim


# ---- generators and checks ----------------------------------------------------------

def step_env():
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    for name in ("GITHUB_EVENT_NAME", "GITHUB_EVENT_PATH", "GITHUB_BASE_REF"):
        env.pop(name, None)
    return env


def fill(argv, **values):
    out = []
    for arg in argv:
        arg = arg.replace("{python}", sys.executable)
        for key, value in values.items():
            arg = arg.replace("{" + key + "}", value)
        out.append(arg)
    return out


def tail(text, limit=40):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join("    " + ln for ln in lines[-limit:])


def run_generators(root, say):
    """[(name, state, note)]. A failed generator raises Failure."""
    results = []
    env = step_env()
    for name, write, check in GENERATORS:
        if write is None:
            results.append((name, PASS, remeasure_budgets(root)))
            say(f"  generator {name}: {results[-1][2]}")
            continue
        script = os.path.join(root, write[1])
        if not os.path.isfile(script):
            raise Failure(f"generator {name}: {write[1]} is not in the checkout; a generator "
                          "that is missing is a failure, never a skip")
        if check is not None:
            rc, out = run(fill(check), root, GENERATOR_TIMEOUT, env)
            if rc == 0:
                results.append((name, PASS, "current"))
                say(f"  generator {name}: current")
                continue
            if rc != 1:
                raise Failure(f"generator {name}: its --check did not run (exit {rc}):\n{tail(out)}")
        rc, out = run(fill(write), root, GENERATOR_TIMEOUT, env)
        if name == "crew-guides" and rc == GUIDE_PARTIAL:
            results.append((name, CNT, "HTML rebuilt; DOCX/PDF NOT rebuilt (no Word/LibreOffice "
                                       "here), so the committed DOCX/PDF are stale"))
        elif rc != 0:
            raise Failure(f"generator {name}: exit {rc}:\n{tail(out)}")
        else:
            results.append((name, PASS, "rewritten"))
        say(f"  generator {name}: {results[-1][2]}")
    return results


def classify(rc, did_not_run):
    if rc is None:
        return CNT
    if rc == 0:
        return PASS
    if rc == EXIT_SKIP:
        return SKIP
    return CNT if rc in did_not_run else FAIL


def run_checks(root, pr_body_file, skip, say):
    """[(name, state, rc, output tail)] for every CHECKS row."""
    results = []
    env = step_env()
    for name, argv, timeout, did_not_run in CHECKS:
        if name in skip:
            results.append((name, SKIP, None, "skipped by --skip-check: NOT VERIFIED"))
        elif not os.path.isfile(os.path.join(root, argv[1])):
            results.append((name, CNT, None, f"{argv[1]} is not in the checkout"))
        else:
            rc, out = run(fill(argv, pr_body=pr_body_file), root, timeout, env)
            state = classify(rc, did_not_run)
            results.append((name, state, rc, "" if state == PASS else tail(out)))
        say(f"  check {name}: {results[-1][1]}"
            + (f" (exit {results[-1][2]})" if results[-1][2] not in (None, 0) else ""))
    return results


# ---- pull request data ----------------------------------------------------------------

PR_FIELDS = "number,headRefName,headRefOid,baseRefName,title,body,isDraft,state,isCrossRepository"


def load_pr(number, repo, pr_json):
    """(pr dict, [open PR dicts])."""
    if pr_json:
        try:
            data = json.loads(read_text(pr_json))
            return data["pr"], list(data["open"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise Refusal(f"--pr-json {pr_json}: {exc}") from exc
    rc, out = run(["gh", "pr", "view", str(number), "--json", PR_FIELDS], repo, 180)
    if rc != 0:
        raise Refusal(f"gh pr view {number} -> {rc}: {out.strip()}")
    rc2, out2 = run(["gh", "pr", "list", "--state", "open", "--limit", "300", "--json",
                     "number,headRefName,headRefOid"], repo, 180)
    if rc2 != 0:
        raise Refusal(f"gh pr list -> {rc2}: {out2.strip()}")
    try:
        return json.loads(out), json.loads(out2)
    except ValueError as exc:
        raise Refusal(f"gh returned JSON that does not parse: {exc}") from exc


def refuse_unlandable(pr, base):
    """The refusals that need only the PR's own data."""
    head = pr.get("headRefName") or ""
    if pr.get("state") != "OPEN":
        raise Refusal(f"PR #{pr.get('number')} is {pr.get('state')}, not OPEN")
    if pr.get("isCrossRepository"):
        raise Refusal(f"PR #{pr['number']} comes from a fork; this script pushes only to a "
                      "branch of this repository")
    if not head or head == base or head in PROTECTED:
        raise Refusal(f"PR #{pr['number']}'s head branch is {head!r}: this script never commits "
                      f"on or pushes to {base} or {'/'.join(PROTECTED)}")
    if (pr.get("baseRefName") or base) != base:
        raise Refusal(f"PR #{pr['number']} targets {pr.get('baseRefName')!r}, not {base!r} "
                      "(pass --base to land against another branch)")


def push_argv(remote, branch, base):
    """The one push this script makes: plain, to the PR branch, never forced."""
    if not branch or branch == base or branch in PROTECTED:
        raise Refusal(f"refusing to push to {branch!r}")
    return ["push", remote, f"HEAD:refs/heads/{branch}"]


# ---- checkout ---------------------------------------------------------------------------

def prepare_scratch(repo, remote, scratch, base, head):
    """A throwaway LF clone holding only <base> and the PR head."""
    url = git(repo, "remote", "get-url", remote).strip()
    if os.path.exists(scratch) and os.listdir(scratch):
        raise Refusal(f"--scratch {scratch} exists and is not empty")
    # The common git dir, not the worktree: `clone --reference` refuses a linked worktree.
    objects = os.path.abspath(os.path.join(repo, git(repo, "rev-parse", "--git-common-dir").strip()))
    git(repo, "clone", "--quiet", "--no-checkout", "--no-tags", "--single-branch", "--branch",
        base, "--reference", objects, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
        "--origin", "origin", url, scratch, timeout=1800)
    for key in ("user.name", "user.email"):
        value = git(repo, "config", "--get", key, check=False).strip()
        if value:
            git(scratch, "config", key, value)
    git(scratch, "fetch", "--quiet", "--no-tags", "origin",
        f"+refs/heads/{head}:refs/remotes/origin/{head}", timeout=1800)
    git(scratch, "checkout", "--quiet", "-B", head, f"refs/remotes/origin/{head}", timeout=1800)
    return scratch


def prepare_in_place(root, remote, base, head):
    if git(root, "config", "--get", "core.autocrlf", check=False).strip().lower() in ("true", "input"):
        raise Refusal("--in-place: core.autocrlf is set here, so the tree may not be the LF bytes "
                      "CI compares; run without --in-place (the scratch clone is LF)")
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch in PROTECTED or branch == base:
        raise Refusal(f"--in-place: the checkout is on {branch}; this script never commits there")
    if branch != head:
        raise Refusal(f"--in-place: the checkout is on {branch}, not the PR's branch {head}")
    if git(root, "status", "--porcelain").strip():
        raise Refusal("--in-place: the worktree is dirty (commit or stash first); nothing changed")
    if remote != "origin":
        raise Refusal("--in-place needs the remote to be named origin (the checks read origin/main)")
    git(root, "fetch", "--quiet", "--no-tags", "origin",
        f"+refs/heads/{base}:refs/remotes/origin/{base}",
        f"+refs/heads/{head}:refs/remotes/origin/{head}", timeout=1800)
    return root


def fetch_open_heads(root, open_prs, own_number):
    """{PR number: marketplace entries at its head, or None when unreadable}."""
    others = [p for p in open_prs if p.get("number") != own_number]
    heads = {}
    # One fetch for all of them; if any ref is refused, each is tried alone.
    batch_rc = git_rc(root, "fetch", "--quiet", "--no-tags", "origin",
                      *[f"+refs/pull/{p.get('number')}/head:refs/remotes/pr/{p.get('number')}"
                        for p in others], timeout=1800)[0] if others else 0
    for pull in others:
        number, oid = pull.get("number"), pull.get("headRefOid") or ""
        ref = f"refs/remotes/pr/{number}"
        rc = batch_rc
        if rc != 0:
            rc, _ = git_rc(root, "fetch", "--quiet", "--no-tags", "origin",
                           f"+refs/pull/{number}/head:{ref}", timeout=600)
        if rc != 0 and pull.get("headRefName"):
            rc, _ = git_rc(root, "fetch", "--quiet", "--no-tags", "origin",
                           f"+refs/heads/{pull['headRefName']}:{ref}", timeout=600)
        got = git(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}", check=False).strip()
        if rc != 0 or not got or (oid and got != oid):
            heads[number] = None
            continue
        heads[number] = entries_at(root, got)
    return heads


# ---- the run ------------------------------------------------------------------------------

def commit_land(root, pr, bumps, trailers):
    """Commit everything as the land commit. Returns its sha, or None when
    there is nothing to commit."""
    git(root, "add", "-A")
    if git_rc(root, "diff", "--cached", "--quiet")[0] == 0:
        return None
    what = ", ".join(f"{n} {v}" for n, v in sorted(bumps.items()))
    subject = (f"{what}: land #{pr['number']} (version bump and generated files)" if what
               else f"land #{pr['number']}: generated files")
    body = ("Made by scripts/land-pr.py: the version bump above the base branch and every open "
            "PR head, the changelog lines it owes, and the regenerated files. The pull request "
            "is not merged by this commit.")
    message = subject + "\n\n" + body + ("\n\n" + "\n".join(trailers) if trailers else "") + "\n"
    msg_file = os.path.join(root, ".git", "LAND_PR_MSG") if os.path.isdir(
        os.path.join(root, ".git")) else os.path.join(tempfile.gettempdir(), "LAND_PR_MSG")
    write_text(msg_file, message)
    try:
        git(root, "commit", "-q", "-F", msg_file)
    finally:
        os.remove(msg_file)
    return git(root, "rev-parse", "HEAD").strip()


def verdict(generators, checks, accepted):
    """(exit code, [reasons]) from the step results. FAIL beats everything;
    a SKIP or COULD-NOT-TELL blocks unless it was named with --accept-skip."""
    failed = [n for n, state, *_ in checks if state == FAIL]
    if failed:
        return EXIT_FAIL, [f"check {n} FAILED" for n in failed]
    unknown = [n for n, state, *_ in [*generators, *checks]
               if state in (SKIP, CNT) and n not in accepted]
    if unknown:
        return EXIT_CNT, [f"{n} did not give a verdict (NOT VERIFIED); name it with "
                          "--accept-skip to push anyway" for n in unknown]
    return EXIT_OK, []


def land(args, say):
    """The whole run. Returns (exit code, report dict)."""
    repo = git(os.path.abspath(args.repo), "rev-parse", "--show-toplevel").strip()
    pr, open_prs = load_pr(args.pr, repo, args.pr_json)
    base, head = args.base, pr.get("headRefName") or ""
    refuse_unlandable(pr, base)
    base_ref = f"origin/{base}"
    report = {"pr": pr["number"], "branch": head, "base": base, "pushed": False, "notes": []}
    scratch = None
    if args.in_place:
        root = prepare_in_place(os.path.abspath(args.in_place), args.remote, base, head)
    else:
        scratch = args.scratch or tempfile.mkdtemp(prefix=f"land-pr-{pr['number']}-")
        say(f"scratch checkout: {scratch}")
        root = prepare_scratch(repo, args.remote, scratch, base, head)
    try:
        code = _land_in(root, args, pr, open_prs, base_ref, report, say)
    finally:
        if scratch and not args.keep:
            remove_tree(scratch)
            say(f"removed {scratch}")
        elif scratch:
            say(f"kept {scratch} (--keep)")
    return code, report


def _land_in(root, args, pr, open_prs, base_ref, report, say):
    base, head = args.base, pr["headRefName"]
    fetched = git(root, "rev-parse", f"refs/remotes/origin/{head}").strip()
    if pr.get("headRefOid") and fetched != pr["headRefOid"]:
        raise Refusal(f"PR #{pr['number']}'s head is {fetched[:12]} on the remote, not the "
                      f"{pr['headRefOid'][:12]} GitHub reported: it moved; re-run")
    if args.in_place and git(root, "rev-parse", "HEAD").strip() != fetched:
        raise Refusal(f"--in-place: the checkout is not at the PR head {fetched[:12]}")
    merged_base = git(root, "rev-parse", base_ref).strip()
    report.update(head_before=fetched, base_sha=merged_base)
    other_heads = fetch_open_heads(root, open_prs, pr["number"])
    checker = load_changelog_checker()
    fork_point = git(root, "merge-base", base_ref, fetched).strip()
    for note in merge_base_branch(root, base_ref, head):
        say(note)
        report["notes"].append(note)
    interim = set(checker.introduced(root, base_ref))
    plan = plan_versions(root, base_ref, fetched, fork_point, other_heads)
    bumps = {}
    for name, source, base_version, own, new, branch_set in plan:
        if new is None:
            say(f"version {name}: {own} already stands above {base} ({base_version}) and every "
                "open PR head, and nothing changed since it was set: kept")
            continue
        set_marketplace_version(root, name, new)
        set_plugin_json_version(root, source, new)
        set_claim_rows(root, name, new)
        olds = [PLACEHOLDER] + ([own] if branch_set else [])
        touched = renumber(root, base_ref, name, olds, new)
        bumps[name] = new
        note = (f"version {name}: {own} -> {new} ({base} has {base_version}; "
                f"{len(other_heads)} other open PR head(s) read"
                + (f", the highest {HIGHEST[name]}" if name in HIGHEST else "") + ")"
                + (f"; re-numbered in {', '.join(touched)}" if touched else ""))
        say(note)
        report["notes"].append(note)
    report["versions"] = bumps
    if bumps or os.path.isdir(os.path.join(root, FRAGMENTS)):
        for note in write_changelog(root, base, pr, bumps, args.kind,
                                    args.title or clean_title(pr.get("title") or ""), interim):
            say(note)
            report["notes"].append(note)
    say("generators:")
    generators = run_generators(root, say)
    sha = commit_land(root, pr, bumps, args.trailer or [])
    head_now = git(root, "rev-parse", "HEAD").strip()
    report.update(land_commit=sha, head_after=head_now,
                  generators=[list(g) for g in generators])
    changed = [p for p in git(root, "diff", "--name-only", f"{sha}^", sha).split("\n") if p] \
        if sha else []
    report["changed"] = changed
    if head_now == fetched:
        say(f"nothing to land: #{pr['number']} at {fetched[:12]} is already merged with "
            f"{base_ref}, bumped and regenerated")
    else:
        commits = git(root, "rev-list", "--count", "--first-parent", f"{fetched}..{head_now}").strip()
        say(f"{head}: {fetched[:12]} -> {head_now[:12]}, {commits} new commit(s) on the branch"
            + ("" if sha else f" (the merge of {base_ref} only; nothing to bump or regenerate)"))
        if sha:
            say(f"the land commit {sha[:12]} changes {len(changed)} file(s):")
            for rel in changed:
                say("  " + rel)
    body_file = os.path.join(tempfile.gettempdir(), f"land-pr-body-{os.getpid()}.md")
    write_text(body_file, pr.get("body") or "")
    try:
        say("checks:")
        checks = run_checks(root, body_file, set(args.skip_check or ()), say)
    finally:
        os.remove(body_file)
    report["checks"] = [[n, s, rc] for n, s, rc, _ in checks]
    for name, state, _rc, output in checks:
        if state != PASS and output:
            say(f"--- {name} ({state}) ---\n{output}")
    code, reasons = verdict(generators, checks, set(args.accept_skip or ()))
    for reason in reasons:
        say("NOT PUSHED: " + reason)
    report["reasons"] = reasons
    if code != EXIT_OK or head_now == fetched:
        return code
    if not args.push:
        say(f"dry run: would push {head_now[:12]} to {head} (re-run with --push)")
        return code
    git(root, "fetch", "--quiet", "--no-tags", "origin",
        f"+refs/heads/{base}:refs/remotes/origin/{base}", timeout=1800)
    if git(root, "rev-parse", base_ref).strip() != merged_base:
        raise Refusal(f"{base_ref} moved since it was merged ({merged_base[:12]}); nothing "
                      "pushed; re-run so the version and generated files match the new base")
    rc, out = git_rc(root, *push_argv("origin", head, base), timeout=1800)
    if rc != 0:
        raise Failure(f"the push to {head} was rejected (it is never forced):\n{tail(out)}")
    report["pushed"] = True
    say(f"pushed {head_now[:12]} to {head}. The pull request is NOT merged: the owner merges it.")
    return EXIT_OK


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    ap.add_argument("pr", type=int, help="pull request number")
    ap.add_argument("--push", action="store_true", help="push the land commit to the PR branch")
    ap.add_argument("--repo", default=ROOT, help="a clone of the repository (default: this one)")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--base", default="main")
    ap.add_argument("--scratch", help="empty directory for the throwaway checkout")
    ap.add_argument("--keep", action="store_true", help="keep the scratch checkout")
    ap.add_argument("--in-place", metavar="DIR", help="land in this clean LF checkout of the PR branch")
    ap.add_argument("--pr-json", help="PR data file instead of calling gh")
    ap.add_argument("--report", help="write a JSON report here")
    ap.add_argument("--trailer", action="append", help="a trailer line for the land commit")
    ap.add_argument("--skip-check", action="append", metavar="NAME", help="do not run this check")
    ap.add_argument("--accept-skip", action="append", metavar="NAME",
                    help="push although this step gave no verdict")
    ap.add_argument("--title", help="changelog title when the PR has no entry (default: PR title)")
    ap.add_argument("--kind", default="Changed",
                    choices=("Added", "Changed", "Fixed", "Removed", "Deprecated", "Security"))
    args = ap.parse_args(argv)
    names = {c[0] for c in CHECKS} | {g[0] for g in GENERATORS}
    unknown = sorted(set((args.skip_check or []) + (args.accept_skip or [])) - names)
    if unknown:
        ap.error(f"unknown step name(s): {', '.join(unknown)}")
    return args


def main(argv=None):
    args = parse_args(argv)

    def say(line):
        print(line, flush=True)

    report = {}
    try:
        code, report = land(args, say)
    except Refusal as exc:
        print(f"land-pr: REFUSED: {exc}", file=sys.stderr)
        code = EXIT_REFUSED
    except Failure as exc:
        print(f"land-pr: FAILED: {exc}", file=sys.stderr)
        code = EXIT_FAIL
    report["exit"] = code
    if args.report:
        write_text(args.report, json.dumps(report, indent=2) + "\n")
    print(f"land-pr: exit {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
