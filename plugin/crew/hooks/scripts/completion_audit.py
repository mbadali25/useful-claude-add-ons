"""Stop-time completion scope audit, and `/crew:done`'s scope check.

crew 1.0, lane T3 (docs/review/04-redesign.md, Hooks table: "diffs the whole
tree against the scope base, catching shell-made writes too, and refuses
`done` on out-of-scope paths").

The edit guard (`scope_guard.py`) sees only Write/Edit/MultiEdit/NotebookEdit.
A `sed -i`, a redirect, a formatter or a `git mv` never reaches it. This audit
reads the result instead of the tool call: every path that differs from the
ticket's scope base (`scope_base.resolve` -- the commit the ticket started
from, falling back to MORE, never less) across committed, staged, unstaged
and untracked changes. PATHS: `git diff-index --raw -z -M <base>` (the base
tree against the working tree, which folds in committed, staged and
unstaged) plus `git ls-files --others --exclude-standard -z`. A Stop costs a
path listing, not the review bundle. Renames arrive with both ends and BOTH
must be in scope: a rename moves a file out of one path as much as into
another.

MERGED MAIN (T-0100). After the ticket merges its integration branch, the
files main changed in between differ from the recorded start too, and are not
the ticket's. `merged_main.resolve` names the merged commit
(`git merge-base HEAD <ref>`) and `merged_main.keep` leaves out every path
byte-identical to it in the working state -- the same rule, from the same
module, that `review_patch.compute` applies to the bundle, so the reviewer and
this audit judge the same changed set. An untracked merged-in path (taken out of
the index by `git rm --cached`) is identical only when its bytes AND the mode
`git add` would record match the merged entry; that mode carries the execute
bit only when `core.fileMode` is not false, as the bundle's `add -A` does. A ticket edit on top of main's edit to
the same file stays, and so does any edit after the merge. The verdict names
the merged commit and how many paths it did not count. When the merged commit
cannot be told (no integration ref, detached HEAD, git gave no answer) nothing
is left out and the verdict says `merged main: could not tell`. Only `audit`
narrows: `changed_paths` without `merged` still answers "what did this branch
change" for `crew_refresh_check.ticket_freshness`.

The user's index is never rewritten. `git diff` -- the porcelain this used
until T-0008 -- refreshes the index's stat cache and WRITES `.git/index`
whenever a tracked file is stat-dirty but unchanged, and neither
`GIT_OPTIONAL_LOCKS=0` nor `--no-optional-locks` stops it (measured, git
2.53). `diff-index` is plumbing and never refreshes, so it reports such a
file as modified with a null worktree id; `worktree_changes` hashes exactly
those files (`git hash-object`, no `-w`, filters applied as `git add` would)
and drops the ones whose content and mode match the base. That is the only
file content read, and it is what `git diff` read to decide the same thing.

What it cannot see, stated rather than implied: files git ignores (`.crew/*`
among them) and `.work/`, which is excluded on purpose (as the review bundle
excludes it).

Paths are printed with control characters escaped (`\n` in a filename would
otherwise add lines), and the whole message is capped at six PHYSICAL lines.

A path passes when it is inside the active ticket's `spec.md ## Touch`, read
from the same bytes the approval hash was checked against -- or, for that
same approved ticket, one of the refresh-artifact paths
(`crew_refresh_check.REFRESH_ARTIFACT_PATHS`: the code map, the diagrams
dir, `graph.out`, `.claude/rules/`), which `/crew:implement` step 6's
refreshes write and no Touch names. When the ticket's
approval is not current or did not come from the user's prompt
(`crew_ticket.accepted`: stale, none, or a `cli` receipt without
`scope.allowCliApproval`), Touch itself is unapproved, so every changed path
fails -- a refresh artifact included, since the allowance is gated on the
same approval: an edited spec cannot widen what the audit accepts until the
user approves it again. A broken active-ticket pointer fails the audit too.

## As a Stop hook

stdin is the Stop payload. `stop_hook_active` true -> exit 0, silent: the
audit blocks a turn once and never re-blocks the continuation it caused.
`scope.mode` off, or no active ticket -> exit 0, silent. Pass -> exit 0 and
no output. Fail under `block` -> exit 2 and at most six lines on stderr; under
`report` -> exit 0 and one `systemMessage`. An audit that could not run (git
failed, no base) is a failure, never a pass.

## As `/crew:done`'s check

`completion_audit.py --check --ticket <id> [--root <dir>]` runs the same audit
whatever `scope.mode` says, prints the verdict, and exits 0 only on a pass.
"""
import argparse
import json
import os
import stat
import subprocess
import sys

import crew_common
import crew_ticket
import merged_main
import scope_base

MAX_LINES = 6
GIT_TIMEOUT = 60
# The review bundle's `.work` exclusion: crew's scratch space is never a changed path.
# `review_patch._EXCLUDE_SPEC` also drops generated `graphify-out/`; this audit keeps it.
_ONLY = ["--", ".", ":(exclude).work"]


_NULL_OID = frozenset("0")
# Blob modes `git hash-object` can re-derive from a file on disk. A symlink
# or a submodule stat-dirty entry is left reported as changed (MORE).
_FILE_MODES = ("100644", "100755")


def _git_fields(top, args, data=None, literal=False):
    """`git -C top <args>` NUL-split. Raises RuntimeError with git's stderr.
    `data` is fed on stdin; `literal` turns pathspec magic off."""
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    if literal:
        env["GIT_LITERAL_PATHSPECS"] = "1"
    try:
        done = subprocess.run(["git", "-C", top] + args, capture_output=True, env=env,
                              timeout=GIT_TIMEOUT, check=False, input=data,
                              stdin=None if data is not None else subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"git {args[0]} could not run: {exc}") from exc
    if done.returncode != 0:
        err = done.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {args[0]} failed ({done.returncode}): {err}")
    return done.stdout.decode("utf-8", errors="surrogateescape").split("\0")


def _stdin_path(path):
    """`path` as one `--stdin-paths` line. git C-unquotes a line that starts
    with `"` and fails the whole call on one that is not valid C quoting, so
    such a name is quoted to unquote back to itself (review round 3)."""
    if not path.startswith('"'):
        return path
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _unchanged(top, suspects):
    """The `{path: base blob id}` entries whose file on disk hashes to that
    id -- stat-dirty, content-identical. Hashed through `--stdin-paths`
    (no `-w`: nothing is written to the object store); a name holding a
    newline cannot travel that way and stays reported as changed."""
    names = [p for p in sorted(suspects) if "\n" not in p and "\r" not in p
             and os.path.isfile(os.path.join(top, p))
             and not os.path.islink(os.path.join(top, p))]
    if not names:
        return set()
    listing = "".join(_stdin_path(p) + "\n" for p in names).encode(
        "utf-8", errors="surrogateescape")
    hashes = _git_fields(top, ["hash-object", "--stdin-paths"], data=listing)[0].split()
    return {p for p, oid in zip(names, hashes) if oid == suspects[p]}


def worktree_changes(top, sha, pathspec, literal=False):
    """Every path that differs between commit `sha` and the working tree --
    committed, staged or not -- both ends of a rename or copy, and never a
    write to the index (module docstring). `pathspec` is everything after
    `--`; `literal` reads it without pathspec magic."""
    fields = _git_fields(top, ["diff-index", "--raw", "-z", "-M", sha, "--"] + pathspec,
                         literal=literal)
    paths, suspects, i = set(), {}, 0
    while i < len(fields):
        head = fields[i]
        if not head.startswith(":"):
            i += 1
            continue
        src_mode, dst_mode, src_oid, dst_oid, status = head[1:].split()[:5]
        width = 2 if status[:1] in ("R", "C") else 1
        names = [p for p in fields[i + 1:i + 1 + width] if p]
        i += 1 + width
        if (status == "M" and src_mode == dst_mode and src_mode in _FILE_MODES
                and set(dst_oid) <= _NULL_OID and len(names) == 1):
            suspects[names[0]] = src_oid
        else:
            paths.update(names)
    return paths | (set(suspects) - _unchanged(top, suspects))


def changed_paths(top, base, merged=None):
    """Every path the tree changed since `base`, both ends of a rename or
    copy. Names, plus the hash of a stat-dirty file -- never the review
    bundle, and never a write to the index."""
    # `merged` is `merged_main.resolve`'s answer or None (T-0100): only an
    # applying one narrows. An untracked path is re-added on both sides, except
    # one whose bytes on disk, and the mode `git add` would record for it
    # (core.fileMode decides whether the execute bit counts), ARE the merged
    # commit's entry (a merged-in path taken out of the index by `git rm --cached`):
    # the review bundle's `add -A` stages it back identical and drops it, so the
    # audit does too.
    sha = _git_fields(top, ["rev-parse", "--verify", base + "^{commit}"])[0].strip()
    untracked = {p for p in _git_fields(top, ["ls-files", "--others", "--exclude-standard",
                                              "-z"] + _ONLY) if p}
    paths = worktree_changes(top, sha, _ONLY[1:]) | untracked
    if not (merged and merged.get("applies")):
        return sorted(paths)
    since_merged = worktree_changes(top, merged["commit"], _ONLY[1:]) | untracked
    return merged_main.keep(paths, since_merged - _as_merged(top, merged["commit"], untracked))


def _as_merged(top, commit, untracked):
    """The `untracked` paths whose file on disk is byte- and mode-identical to
    `commit`'s entry for it, the mode being the one `git add` would record
    (`_disk_mode`). Hashed through `--stdin-paths` without `-w`, as
    `_unchanged` does; a symlink, or a name `--stdin-paths` cannot carry, is
    never identical."""
    names = sorted(p for p in untracked if "\n" not in p and "\r" not in p
                   and os.path.isfile(os.path.join(top, p))
                   and not os.path.islink(os.path.join(top, p)))
    if not names:
        return set()
    # The whole tree, filtered here: no pathspec of N names on the command line.
    wanted, entries = set(names), {}
    for field in _git_fields(top, ["ls-tree", "-r", "-z", "--full-tree", commit]):
        meta, _, path = field.partition("\t")
        if path in wanted and len(meta.split()) == 3:
            mode, kind, oid = meta.split()
            if kind == "blob":
                entries[path] = (mode, oid)
    names = [p for p in names if p in entries]
    if not names:
        return set()
    listing = "".join(_stdin_path(p) + "\n" for p in names).encode(
        "utf-8", errors="surrogateescape")
    hashes = _git_fields(top, ["hash-object", "--stdin-paths"], data=listing)[0].split()
    file_mode = _file_mode(top)
    return {p for p, oid in zip(names, hashes)
            if (oid, _disk_mode(top, p, file_mode)) == (entries[p][1], entries[p][0])}


def _file_mode(top):
    """`core.fileMode` as git reads it: unset, unreadable or anything but `false`
    reads true -- the conservative side, where an execute-bit mismatch is
    counted, never dropped."""
    return crew_common.git_out(top, "config", "--type=bool", "--get", "core.fileMode") != "false"


def _disk_mode(top, path, file_mode):
    """The blob mode `git add` records for the regular file at `path` when the
    index has no entry for it: 100755 only when the owner's execute bit is set
    AND `core.fileMode` is not false (`file_mode`, read once per audit by
    `_file_mode`; measured, git 2.53: 100644 under false whatever the bit).
    NTFS has no execute bit git can see: always 100644."""
    if os.name == "nt" or not file_mode:
        return "100644"
    return "100755" if os.stat(os.path.join(top, path)).st_mode & stat.S_IXUSR else "100644"


def shown(path):
    """`path` with every non-printable character escaped, so a filename can
    never add a line to a hook message."""
    return "".join(c if c.isprintable() else
                   (f"\\x{ord(c):02x}" if ord(c) < 0x100 else f"\\u{ord(c):04x}")
                   for c in path)


def physical(lines):
    """`lines` as at most MAX_LINES physical lines, whatever they contain."""
    return "\n".join(lines).splitlines()[:MAX_LINES]


def _outside_refresh_artifacts(top, paths, approval):
    """`paths` minus the refresh artifacts (`crew_refresh_check.
    REFRESH_ARTIFACT_PATHS`) -- only when the ticket holds a current approval
    from the user's prompt, the condition that gates Touch
    (`crew_ticket.accepted`: a `cli` receipt only with
    `scope.allowCliApproval`). Without that approval nothing is exempt."""
    if approval["status"] != "approved":
        return paths
    import crew_refresh_check  # pylint: disable=import-outside-toplevel
    dirs = crew_refresh_check.refresh_artifact_paths(top)
    return [p for p in paths if not crew_refresh_check.is_refresh_artifact(p, dirs)]


def audit(root, ticket):
    """(ok, lines). `lines` explains a failure; on a pass it is the merged-main
    line when paths identical to merged main were not counted, else empty."""
    top = crew_ticket.toplevel(root)
    if not top:
        return False, [f"completion audit: {root} is not a git repository; cannot audit"]
    base, source, reason = scope_base.resolve(top, ticket)
    if not base:
        return False, [f"completion audit: no scope base for {ticket} ({reason})"]
    merged = merged_main.resolve(top, base)
    try:
        paths = changed_paths(top, base, merged)
        # One more listing, only when a merge applies, to count what it left out.
        dropped = len(changed_paths(top, base)) - len(paths) if merged["applies"] else 0
    except RuntimeError as exc:
        return False, [f"completion audit: could not diff the tree: {shown(str(exc))}"]
    extra = _merged_lines(merged, dropped)
    # A pass states the answer too: the count when a merge applied, and
    # could-not-tell always (review round 1: a silent pass hid the unknown).
    passed = extra if (merged["applies"] and dropped) or merged["commit"] is None else []
    # ONE read of spec.md: the hash check, the Touch below and the refresh
    # allowance all share the bytes.
    approval = crew_ticket.accepted(top, ticket)
    paths = _outside_refresh_artifacts(top, paths, approval)
    if not paths:
        return True, passed
    note = "" if source == scope_base.RECORDED else " (base is a fallback: shows MORE)"
    if approval["status"] != "approved":
        return False, [f"COMPLETION AUDIT: {ticket}'s Touch is not approved "
                       f"({approval['why']}), so no change can be judged in scope.",
                       f"  Changed since {base[:12]}{note}: "
                       + " ".join(shown(p) for p in paths[:8])
                       + (" ..." if len(paths) > 8 else ""),
                       *extra,
                       f"  Ask the user to type `/crew:approve {ticket}`."]
    outside = [p for p in paths if not crew_ticket.in_touch(p, approval["touch"])]
    if not outside:
        return True, passed
    listed = " ".join(shown(p) for p in outside[:8]) + (
        f" (+{len(outside) - 8} more)" if len(outside) > 8 else "")
    return False, [f"COMPLETION AUDIT: {len(outside)} changed path(s) outside {ticket}'s "
                   f"spec ## Touch{note}:",
                   f"  {listed}",
                   *extra,
                   "  Revert them, or amend spec.md ## Touch and have the user type",
                   f"  `/crew:approve {ticket}`. Shell-made writes count."]


def _merged_lines(merged, dropped):
    """The verdict's `merged main` line: the commit and what it did not count,
    or could-not-tell. Empty when there was no merge to account for."""
    if merged["applies"]:
        return [(f"  merged main {merged['commit'][:12]} ({merged['ref']}): {dropped} path(s) "
                 "identical to it not counted")]
    if merged["commit"] is None:
        return [(f"  merged main: {merged_main.UNKNOWN} - "
                 f"{shown(merged_main.bare_reason(merged))}; every changed path counted")]
    return []


def _payload():
    try:
        raw = sys.stdin.buffer.read()
    except (OSError, ValueError):
        return {}
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    try:
        data = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    except (UnicodeDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def stop_hook(data):
    if data.get("stop_hook_active") is True:
        return 0
    root = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    root = root or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    top = crew_ticket.toplevel(root)
    if not top:
        return 0
    configured, _why = crew_ticket.configured_mode(top)
    if configured == "off":
        return 0
    ticket, source, broken = crew_ticket.resolve_active(root)
    if broken:
        mode, why = crew_ticket.effective_mode(root, None)
        ok, lines = False, [f"COMPLETION AUDIT: the active-ticket pointer is broken "
                            f"({shown(source)}); nothing can be audited against a ticket.",
                            "  Fix it with `crew_ticket.py activate --ticket <id>` or "
                            "`crew_ticket.py deactivate`."]
    elif not ticket:
        return 0
    else:
        mode, why = crew_ticket.effective_mode(root, ticket)
        try:
            ok, lines = audit(root, ticket)
        except Exception as exc:  # pylint: disable=broad-except
            ok, lines = False, [f"completion audit: failed ({type(exc).__name__}: "
                                f"{shown(str(exc))}); nothing was audited"]
    if ok:
        return 0
    if mode == "block":
        sys.stderr.write("".join(line + "\n" for line in physical(lines)))
        return 2
    sys.stdout.write(json.dumps({"systemMessage": "completion audit (report, would block): "
                                 + " ".join(l.strip() for l in lines[:2]) + f" ({why})"})
                     + "\n")
    return 0


def main(argv):
    if not argv:
        return stop_hook(_payload())
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    try:
        crew_ticket.check_ticket(args.ticket)
        ok, lines = audit(os.path.abspath(args.root), args.ticket)
    except crew_ticket.TicketError as exc:
        ok, lines = False, [f"completion audit: {exc}"]
    if ok:
        print(f"completion audit: every change is inside {args.ticket}'s spec ## Touch")
        print("".join(line + "\n" for line in physical(lines)), end="")
        return 0
    print("\n".join(physical(lines)))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
