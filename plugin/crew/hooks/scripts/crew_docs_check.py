"""Which documents does this ticket's change owe, and were they written? Read-only.

    python3 crew_docs_check.py --root . --ticket <id> [--json] [--explain]

T-0022. `/crew:docs <id>` decides, per document, whether this ticket touches
it, and records each `not needed` reason and each deferral in
`.work/tickets/<id>/docs.json`. This check reads that record and the tree and
prints one line per document:

  updated                 the document changed in this ticket
  not needed (<reason>)   nothing triggers it, or docs.json says why not
  MISSING                 a trigger fired and neither an edit nor a reason
  not applicable          the repo has no such document
  unknown                 git could not read the document at the base, so what
                          this ticket added cannot be told (never `updated`)

plus `adr, runbooks: not measured` -- those stay `/crew:docs` judgement.
Exit 0 only when no line is MISSING and nothing was unknown; 1 otherwise; 2
usage. It never writes: git is asked through plumbing only (`diff-index`,
`ls-tree`, `cat-file`, `ls-files`), never `git diff`, which can rewrite `.git/index`.

## The changed set

`scope_base.resolve` then `completion_audit.changed_paths` -- the base against
the working tree plus untracked files, the set `/crew:done`'s completion audit
judges and T-0008's refresh check reads -- minus `.work/**` and minus T-0008's
`crew_refresh_check.RELEASE_BOOKKEEPING` (a version bump, a CHANGELOG or TODO
line, PLUGINS.md, the manifests, BUDGETS.md), imported, not restated. No scope
base, or one T-0008's check would not trust (a fallback equal to HEAD; any
other fallback on the default branch or with a commit behind it naming the
ticket; a recorded base with such a commit behind it), is `unknown`: nothing
here is confirmed, and `unknown` refuses like MISSING.

## CHANGELOG.md -- mechanical, never waived

For each `.claude-plugin/marketplace.json` entry whose `source` directory
holds a changed path, the lines this ticket ADDED to CHANGELOG.md (the base
blob against the working tree, in Python) inside `## [Unreleased]` must name
`` `<name>` `` and the entry's current `version`. Else MISSING, whatever
docs.json says: a reason cannot waive it. No entry changed: `not needed`. No
marketplace.json: the repo is one unit and CHANGELOG is judgement -- edited,
or a recorded reason, or MISSING. No CHANGELOG.md: `not applicable`.

## README.md, SECURITY.md, TODO.md -- judgement with a recorded reason

- An entry's README when the entry's `README_TRIGGERS` changed; the root
  README when the set of marketplace entry names differs from the base's.
- SECURITY.md when a `SECURITY_PATHS` path changed; none changed is `not
  needed (no security-relevant path changed)` with no reason asked for.
- A triggered document is `updated` when it changed, `not needed (<reason>)`
  with a docs.json reason, else MISSING.
- TODO.md: every docs.json `deferred[].key` must appear in TODO.md's added
  lines; nothing deferred is `not needed (nothing deferred)`.

Both glob lists are judgement (spec Unknowns) and `--explain` prints them.

## docs.json

`{"reasons": {"<document>": "<why not>"}, "deferred": [{"key", "why",
"unblock"}]}`, written once by `/crew:docs <id>`. Absent is no reasons and no
deferrals. Present but unparseable, or of another shape, is `unknown` --
never read as "no reasons", which would turn a recorded decision into a
silent MISSING or, worse, into nothing at all.
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys

if __name__ == "__main__":
    sys.dont_write_bytecode = True

import completion_audit
import crew_refresh_check
import crew_ticket
import scope_base

OK = "ok"
MISSING_STATUS = "missing"
UNKNOWN = "unknown"
UPDATED = "updated"
NOT_NEEDED = "not needed"
MISSING = "MISSING"
NOT_APPLICABLE = "not applicable"
NOT_MEASURED = ["adr", "runbooks"]

CHANGELOG = "CHANGELOG.md"
SECURITY = "SECURITY.md"
TODO = "TODO.md"
README = "README.md"
MARKETPLACE = ".claude-plugin/marketplace.json"
UNRELEASED = "## [Unreleased]"

# T-0008's list, imported so the two can never drift apart.
RELEASE_PATHS = crew_refresh_check.RELEASE_BOOKKEEPING
# Under an entry's source: a change here is one its README shows.
README_TRIGGERS = ("commands/**", "agents/**", "skills/*/SKILL.md", "hooks/hooks.json",
                   "CONFIG.md")
# Repo-relative; a change here makes SECURITY.md a decision with a reason.
SECURITY_PATHS = ("**/hooks/scripts/*guard*", "**/approval_hook.py", "**/promote-gate.*",
                  "**/hooks.json", "scripts/install-prerequisites.*", ".github/workflows/**",
                  SECURITY)

GIT_TIMEOUT = 30


def docs_json_path(top, ticket):
    return os.path.join(crew_ticket.ticket_dir(top, ticket), "docs.json")


def read_docs_json(top, ticket):
    """`(record, problem)`. Absent -> ({"reasons": {}, "deferred": []}, None);
    unreadable, unparseable or misshapen -> (None, why). Never "no reasons"
    for a file that exists and cannot be read."""
    path = docs_json_path(top, ticket)
    if not os.path.lexists(path):
        return {"reasons": {}, "deferred": []}, None
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, f"docs.json could not be read: {exc}"
    if not isinstance(data, dict):
        return None, "docs.json is not a JSON object"
    reasons = data.get("reasons", {})
    deferred = data.get("deferred", [])
    if not isinstance(reasons, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in reasons.items()):
        return None, "docs.json `reasons` is not an object of document -> reason strings"
    if not isinstance(deferred, list) or not all(
            isinstance(d, dict) and isinstance(d.get("key"), str) and d["key"].strip()
            for d in deferred):
        return None, "docs.json `deferred` is not a list of objects with a `key` string"
    return {"reasons": {k: v.strip() for k, v in reasons.items() if v.strip()},
            "deferred": deferred}, None


class GitFailed(RuntimeError):
    """git could not answer (error, timeout, not runnable): never "absent"."""


def _git_bytes(top, *args):
    """stdout bytes, or None when git fails for any reason."""
    try:
        done = subprocess.run(["git", "-C", top] + list(args), capture_output=True,
                              env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"),
                              timeout=GIT_TIMEOUT, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _base_text(top, base, rel):
    """`rel`'s text at `base`, or None when `base` has no such file. Raises
    GitFailed when git cannot say which: a None there would read every line
    of the file as added (review round 1 FIX), so the row is `unknown`."""
    listing = _git_bytes(top, "ls-tree", "-z", base, "--", rel)
    if listing is None:
        raise GitFailed(f"git could not list {rel} at {base[:12]}")
    if not listing.strip(b"\0"):
        return None
    data = _git_bytes(top, "cat-file", "blob", f"{base}:{rel}")
    if data is None:
        raise GitFailed(f"git could not read {rel} at {base[:12]}")
    return data.decode("utf-8", errors="replace")


def _unknown_row(doc, exc):
    return _row(doc, UNKNOWN, f"{exc} - could not tell what this ticket added")


def _disk_text(top, rel):
    path = os.path.join(top, rel)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8-sig", errors="replace")


def added_lines(old, new):
    """`[(index, line)]` of the lines in `new` that `old` does not have, as a
    line diff sees them; `old` None means every line is added."""
    new_lines = (new or "").splitlines()
    if old is None:
        return list(enumerate(new_lines))
    matcher = difflib.SequenceMatcher(a=old.splitlines(), b=new_lines, autojunk=False)
    return [(j, new_lines[j]) for tag, _i1, _i2, j1, j2 in matcher.get_opcodes()
            if tag in ("insert", "replace") for j in range(j1, j2)]


def unreleased_range(text):
    """`(start, end)` line indexes of the `## [Unreleased]` section's body, or None."""
    lines = (text or "").splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.strip().lower().startswith(UNRELEASED.lower())), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r"^##\s", lines[i])), len(lines))
    return start + 1, end


def _entries(text):
    """`[{"name", "source", "version"}]` from marketplace.json text, or None."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, list):
        return None
    found = []
    for item in plugins:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        source = item.get("source")
        source = source if isinstance(source, str) else ""
        found.append({"name": item["name"], "version": str(item.get("version") or ""),
                      "source": source[2:] if source.startswith("./") else source.strip("/")})
    return found


def _under(path, prefix):
    prefix = prefix.strip("/")
    return bool(prefix) and (path == prefix or path.startswith(prefix + "/"))


def _matches(path, globs):
    return any(crew_ticket.glob_match(path, glob) for glob in globs)


def _row(doc, verdict, reason=""):
    return {"doc": doc, "verdict": verdict, "reason": reason}


def _judged(doc, changed_raw, reasons, why_triggered):
    """A judgement document whose trigger fired: edited, or a reason, or MISSING."""
    if doc in changed_raw:
        return _row(doc, UPDATED, why_triggered)
    if reasons.get(doc):
        return _row(doc, NOT_NEEDED, reasons[doc])
    return _row(doc, MISSING, f"{why_triggered}; no edit and no docs.json reason")


def _names_version(line, name, version):
    return (f"`{name}`" in line and bool(version)
            and re.search(r"(?<![0-9A-Za-z.])" + re.escape(version) + r"(?![0-9A-Za-z])",
                          line) is not None)


def _changelog_rows(top, base, changed, changed_raw, entries, reasons):
    now = _disk_text(top, CHANGELOG)
    if now is None:
        return [_row(CHANGELOG, NOT_APPLICABLE, "no CHANGELOG.md in this repo")]
    if entries is None:
        if not changed:
            return [_row(CHANGELOG, NOT_NEEDED, "nothing outside .work/ and release "
                         "bookkeeping changed")]
        return [_judged(CHANGELOG, changed_raw, reasons,
                        "no marketplace.json: the repo is one unit")]
    touched = [e for e in entries if any(_under(p, e["source"]) for p in changed)]
    if not touched:
        return [_row(CHANGELOG, NOT_NEEDED, "no marketplace entry's source changed")]
    span = unreleased_range(now)
    try:
        old = _base_text(top, base, CHANGELOG)
    except GitFailed as exc:
        return [_unknown_row(f"{CHANGELOG} ({e['name']} {e['version']})", exc) for e in touched]
    added = [line for index, line in added_lines(old, now)
             if span and span[0] <= index < span[1]]
    rows = []
    for entry in touched:
        doc = f"{CHANGELOG} ({entry['name']} {entry['version']})"
        if any(_names_version(line, entry["name"], entry["version"]) for line in added):
            rows.append(_row(doc, UPDATED, f"an added [Unreleased] line names "
                             f"`{entry['name']}` {entry['version']}"))
        else:
            # Never waived by docs.json: a changed plugin owes its entry.
            rows.append(_row(doc, MISSING, f"{entry['source']}/ changed and no line added "
                             f"under {UNRELEASED} names `{entry['name']}` "
                             f"{entry['version'] or '(no version)'}"))
    return rows


def _readme_rows(top, base, changed, changed_raw, entries, reasons):
    rows = []
    units = entries if entries is not None else [{"name": "(repo)", "source": ""}]
    for entry in units:
        source = entry["source"].strip("/")
        doc = f"{source}/{README}" if source else README
        hits = sorted(p for p in changed
                      if (not source or _under(p, source))
                      and _matches(p[len(source) + 1:] if source else p, README_TRIGGERS))
        if not hits:
            continue
        if not os.path.isfile(os.path.join(top, doc)):
            rows.append(_row(doc, NOT_APPLICABLE, f"no {doc}"))
            continue
        rows.append(_judged(doc, changed_raw, reasons, f"{hits[0]} changed"
                            + (f" (+{len(hits) - 1} more)" if len(hits) > 1 else "")))
    if entries is not None:
        try:
            old = _base_text(top, base, MARKETPLACE)
        except GitFailed as exc:
            return rows + [_unknown_row(README, exc)]
        old_entries = _entries(old) if old is not None else []
        if old_entries is None:
            # Present but unparseable is not "no entries": every current one
            # would read as added (review round 2 FIX).
            return rows + [_unknown_row(README, f"{MARKETPLACE} at {base[:12]} does not parse")]
        before = {e["name"] for e in old_entries}
        after = {e["name"] for e in entries}
        if before != after and not any(r["doc"] == README for r in rows):
            if not os.path.isfile(os.path.join(top, README)):
                rows.append(_row(README, NOT_APPLICABLE, "no README.md"))
            else:
                moved = sorted(before ^ after)
                rows.append(_judged(README, changed_raw, reasons,
                                    "marketplace entries added or removed: " + ", ".join(moved)))
    if not rows:
        rows.append(_row(README, NOT_NEEDED, "no README trigger changed"))
    return rows


def _security_rows(top, changed, changed_raw, reasons):
    if not os.path.isfile(os.path.join(top, SECURITY)) and SECURITY not in changed_raw:
        return [_row(SECURITY, NOT_APPLICABLE, "no SECURITY.md in this repo")]
    hits = sorted(p for p in changed_raw if _matches(p, SECURITY_PATHS))
    if not hits:
        return [_row(SECURITY, NOT_NEEDED, "no security-relevant path changed")]
    return [_judged(SECURITY, changed_raw, reasons, f"security-relevant {hits[0]} changed"
                    + (f" (+{len(hits) - 1} more)" if len(hits) > 1 else ""))]


def _todo_rows(top, base, deferred):
    keys = [d["key"].strip() for d in deferred]
    if not keys:
        return [_row(TODO, NOT_NEEDED, "nothing deferred")]
    now = _disk_text(top, TODO)
    try:
        old = _base_text(top, base, TODO)
    except GitFailed as exc:
        return [_unknown_row(TODO, exc)]
    added = "\n".join(line for _i, line in added_lines(old, now))
    absent = [k for k in keys if now is None or k not in added]
    if absent:
        return [_row(TODO, MISSING, "deferred in docs.json but not added to TODO.md: "
                     + ", ".join(absent))]
    return [_row(TODO, UPDATED, f"{len(keys)} deferred item(s) added")]


def _base_doubt(top, base, source, ticket):
    """Why `base` cannot be trusted to show this ticket's change, or None --
    T-0008's rules, called rather than restated: a fallback equal to HEAD
    hides every committed change; any other fallback is used only off the
    default branch with no commit behind it naming the ticket; a recorded
    base is doubted when a commit behind it names the ticket."""
    # pylint: disable=protected-access
    if source == scope_base.RECORDED:
        doubt = crew_refresh_check._named_behind(top, base, ticket)
        return f"recorded base {base[:12]} may hide {ticket}'s commits: {doubt}" if doubt else None
    head = _git_bytes(top, "rev-parse", "HEAD")
    if head is None or head.decode().strip() == base:
        return f"scope base {base[:12]} is a fallback that hides the change"
    doubt = crew_refresh_check._fallback_hides(top, base, ticket)
    return f"fallback base {base[:12]} may hide {ticket}'s commits: {doubt}" if doubt else None


def _result(status, reason, documents, base_source=None):
    return {"status": status, "reason": reason, "documents": documents,
            "not_measured": list(NOT_MEASURED), "base_source": base_source}


def ticket_docs(root, ticket):
    """`{"status": ok|missing|unknown, "reason", "documents": [{"doc",
    "verdict", "reason"}], "not_measured", "base_source"}` (module docstring).
    Writes nothing."""
    crew_ticket.check_ticket(ticket)
    top = crew_ticket.toplevel(root)
    if not top:
        return _result(UNKNOWN, f"{root} is not a git work tree", [])
    base, source, why = scope_base.resolve(top, ticket)
    if not base:
        return _result(UNKNOWN, f"no scope base for {ticket} ({why})", [], source)
    doubt = _base_doubt(top, base, source, ticket)
    if doubt:
        return _result(UNKNOWN, f"{doubt} ({why})", [], source)
    record, problem = read_docs_json(top, ticket)
    if record is None:
        return _result(UNKNOWN, problem, [], source)
    try:
        every = completion_audit.changed_paths(top, base)
    except RuntimeError as exc:
        return _result(UNKNOWN, f"could not list {ticket}'s changes: {exc}", [], source)
    changed_raw = {p for p in every if not _under(p, ".work")}
    changed = {p for p in changed_raw if not _matches(p, RELEASE_PATHS)}
    market = _disk_text(top, MARKETPLACE)
    entries = _entries(market) if market is not None else None
    if market is not None and entries is None:
        return _result(UNKNOWN, f"{MARKETPLACE} could not be parsed", [], source)
    reasons = record["reasons"]
    documents = (_changelog_rows(top, base, changed, changed_raw, entries, reasons)
                 + _readme_rows(top, base, changed, changed_raw, entries, reasons)
                 + _security_rows(top, changed, changed_raw, reasons)
                 + _todo_rows(top, base, record["deferred"]))
    verdicts = {d["verdict"] for d in documents}
    status = (UNKNOWN if UNKNOWN in verdicts else MISSING_STATUS if MISSING in verdicts else OK)
    return _result(status, f"scope base {base[:12]} ({why})", documents, source)


def missing_documents(result):
    """The documents a docs run still owes, as short names."""
    return [d["doc"] for d in result.get("documents") or [] if d.get("verdict") == MISSING]


def line(row):
    if row["verdict"] == NOT_NEEDED:
        return f"{row['doc']}: not needed ({row['reason']})"
    return f"{row['doc']}: {row['verdict']}" + (f" - {row['reason']}" if row["reason"] else "")


def render(ticket, result):
    lines = [f"docs-check {ticket}: {result['status']} - {result['reason']}"]
    lines += [line(row) for row in result["documents"]]
    lines.append(", ".join(result["not_measured"]) + ": not measured")
    return "\n".join(lines)


def explain():
    return "\n".join([
        "changed set: scope base vs working tree + untracked, minus .work/** and "
        "RELEASE_PATHS: " + ", ".join(RELEASE_PATHS),
        "CHANGELOG: each marketplace entry whose source changed needs an added "
        f"{UNRELEASED} line naming `<name>` and its version (never waived)",
        "README triggers (under an entry's source): " + ", ".join(README_TRIGGERS)
        + "; root README.md when the entry names differ from the base's",
        "SECURITY_PATHS: " + ", ".join(SECURITY_PATHS),
        "TODO.md: every docs.json deferred[].key in TODO.md's added lines",
    ])


def exit_code(result):
    return 0 if result["status"] == OK else 1


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--explain", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = ticket_docs(args.root, args.ticket)
    except crew_ticket.TicketError as exc:
        sys.stderr.write(f"usage: {exc}\n")
        return 2
    except Exception as exc:  # pylint: disable=broad-except
        # A crash cannot tell: unknown, which refuses -- never silence.
        result = _result(UNKNOWN, f"the docs check raised {type(exc).__name__}: {exc}", [])
    text = json.dumps(result, indent=2) if args.json else render(args.ticket, result)
    if args.explain and not args.json:
        text += "\n" + explain()
    sys.stdout.write(text + "\n")
    return exit_code(result)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
