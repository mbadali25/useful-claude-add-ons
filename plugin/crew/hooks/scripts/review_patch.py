"""Build the ONE patch `/crew:review` actually hands to a reviewer.

THE DEFECT (found by Codex, `docs/review/03-codex-review.md`). `review.md`
built its review input with `git diff "$BASE"...HEAD` -- the three-dot,
committed-range form. On a dirty working tree that produced a 0-byte patch
while `git diff HEAD` showed ~100 KB of real, uncommitted change, and
untracked files never entered the patch at all (only their NAMES reached the
landmine-matching step, never their content). A reviewer handed that empty
file read nothing and reported CLEAN on nothing it had read.

THE FIX. One patch = the committed range `<base>...HEAD` PLUS staged PLUS
unstaged PLUS untracked (non-ignored) changes, all diffed against `<base>` in
a single pass. That is done by staging everything -- `git add -A` -- into a
TEMPORARY index (`GIT_INDEX_FILE` pointed at a copy of the real one) and
diffing `<base>` against the tree that index produces. The real index is
never opened for writing; only the temp copy is. This is the same shape as
diffing base -> HEAD, except "HEAD" here is the full working state rather
than the last commit, so one `git diff` call produces one patch with no risk
of the three ranges' hunks overlapping or reordering the way concatenating
three separate diffs could.

Never opens an output file before its content is fully computed: `open(p,
"w")` truncates at open time, and a raising expression between that open and
the write leaves a zero-byte file where a real one belongs -- this repo's own
CLAUDE.md landmine, with a real casualty
(`plugin/gizmoduck/commands/scan.md`) to prove it. Both the patch text and the
manifest JSON are built into local variables before either `open(..., "w")`
call runs.

COMPLETENESS (0.20.17, T1). The manifest also carries one `entries` row per
changed path, from `git diff --raw -z -M`: its status (A/M/D/R/C/T), both
paths of a rename, both file modes (so a mode-only change is visible), and
flags for binary files (with both blob ids and sizes -- the patch itself only
carries git's "Binary files ... differ" marker, never a binary body) and for
submodules (mode 160000, with both commit ids). The diff runs with
`--full-index`, so even a binary file's `index <old>..<new>` line names its
full blob id and a changed binary always changes the patch bytes.

SPLITTING. A bundle larger than `--max-part-bytes` is written as ordered parts
under `--parts-dir` (default: `<out>.parts`), cut at `diff --git` file
boundaries where possible, then at line boundaries, then -- only for a single
line longer than the limit -- at the byte limit. The parts concatenated are
byte-identical to `--out`; nothing is truncated. The manifest lists every part
with its size and sha256, and `bundle_sha256` is the sha256 over the parts in
manifest order (which, because they concatenate to the whole, is also the
sha256 of `--out`). `review_ledger.py --check-receipt` recomputes it to tell
whether the tree still matches what a reviewer accepted.

`.work/` is excluded from the bundle and the manifest says so
(`excluded`): it is crew's own scratch space, and the review's scratch files
landing in the bundle would change the hash between building it and checking
the receipt. The exclusion is NOT a pathspec on `git add`: `git add -A -- .
':(exclude).work'` exits 1 with "paths are ignored by one of your .gitignore
files" in every repository that gitignores `.work/` -- this one included --
so no bundle could be built there at all. Instead `add -A` runs unrestricted
and every diff and listing carries the exclude pathspec. That is also what
keeps out `.work` entries the copied index already held (force-added, or
committed at the base): they are in the temp tree, and on both sides of the
range, but no diff reads them.

Generated `graphify-out/` (graphify's `graph.json` and `GRAPH_REPORT.md`,
rebuilt by a command and never hand-edited, 24 MB in this repository) is
excluded the same way since crew 1.0.54 (T-0092), and `excluded` names it:
a Claude review of a bundle carrying it came back INCOMPLETE on 77 of 80
parts. The pathspec is root-anchored, so a look-alike such as
`docs/graphify-out/` or `graphify-out-notes/` stays in the bundle.

MERGED MAIN (T-0100). `--base` is the ticket's recorded start, so after the
ticket merges its integration branch every file main changed in between used
to reach the bundle too: T-0092's round-2 reviewer re-read three landed
tickets. The bundle now diffs from a SYNTHETIC base tree -- the start commit's
tree with each path that is byte-identical, in the working state, to the
merged commit (`merged_main.resolve` / `merged_main.keep`, the rule the
completion audit shares) set to its working-state entry -- so those paths
drop out of the patch, `entries` and every file list. A ticket edit on top of
main's edit to the same file stays, diffed from the MERGED commit's version of
that file (main's lines are context, only the ticket's are `+`/`-`); every
path main did not change since the ticket forked from it is diffed from the
start. The manifest records `merged_main` (ref, commit, applies, reason,
fork, dropped, diffed_from_merged) and `bundle_base_tree`; `base` stays the
start. `fork` is that merge-base, or null when git gave no answer: then every
path main also changed is diffed from the start (more shown, never less), and
`fork_reason`, the stderr field `diffed-from-merged=could-not-tell`, the
prompt and the receipt note all say main's lines there may read as the
ticket's. Could-not-tell drops nothing and says so. The synthetic tree, not a pathspec of the kept paths: that pathspec
can run past Windows' ~32 KB command line, and `git diff` has no
`--pathspec-from-file`. It is built in a second temporary index, never the
real one.

CLI: --root <repo> --base <sha> --out <patch-file> --manifest <json-file>
     [--parts-dir <dir>] [--max-part-bytes N]

Exit codes:
  0  a non-empty patch was written; --out and --manifest both exist.
  1  an error, OR an empty patch even though something was detected as
     changed -- that combination is the bug this script exists to prevent,
     never a legitimate outcome.
  2  "nothing to review" -- HEAD matches --base and the tree is clean. Also
     a non-zero exit, on purpose: an empty patch must never look identical
     to a successful review.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

import crew_common
import merged_main
import webtest_guard

GIT_TIMEOUT = 30

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOTHING_TO_REVIEW = 2

# 200 KiB: comfortably inside what every reviewer CLI reads in one file read,
# and small enough that a reviewer acknowledging each part is meaningful.
DEFAULT_MAX_PART_BYTES = 200 * 1024

# Pathspecs excluding crew's scratch space and the generated graph from every
# diff and listing. Never passed to `git add`: there it fails outright when
# `.work` is gitignored.
EXCLUDED = (".work/", "graphify-out/")
_EXCLUDE_SPEC = [":(exclude).work", ":(exclude)graphify-out"]

# Flags every diff here runs with, so a user's own git config cannot change
# the bytes: no colour codes, no external diff driver, no textconv filter,
# renames detected whatever `diff.renames` says, full blob ids.
_DIFF_FLAGS = ["--no-color", "--no-ext-diff", "--no-textconv", "-M", "--full-index"]

SUBMODULE_MODE = "160000"


def _run_raw(root, args, env=None, data=None):
    """Run `git -C root <args>` and return stdout as BYTES, raising
    RuntimeError with git's own stderr on a nonzero exit. Unlike
    `crew_common.git_out`, this never fails soft -- a caller building the
    review input needs to know WHY it could not, not a silent None that a
    downstream `if` turns into "clean". Bytes, because a patch is not
    necessarily UTF-8 and decoding it lossily would change what the
    reviewer reads and what the bundle hash covers. `data` is fed on
    stdin; without it stdin is closed."""
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    try:
        done = subprocess.run(
            ["git", "-C", root] + list(args),
            capture_output=True, timeout=GIT_TIMEOUT, env=full_env, check=False,
            input=data, stdin=None if data is not None else subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"git {' '.join(args)} could not run: {exc}") from exc
    if done.returncode != 0:
        err = done.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed ({done.returncode}): {err}")
    return done.stdout


def _run(root, args, env=None):
    return _run_raw(root, args, env=env).decode("utf-8", errors="replace")


def _lines(root, args, env=None):
    out = _run(root, args, env=env)
    return sorted({line for line in out.splitlines() if line.strip()})


def _blob_size(root, blob):
    if not blob or set(blob) == {"0"}:
        return None
    try:
        return int(_run(root, ["cat-file", "-s", blob]).strip())
    except (RuntimeError, ValueError):
        return None


def _parse_raw(raw):
    """`git diff --raw -z -M` -> list of dicts. Each record is
    `:<old mode> <new mode> <old id> <new id> <status>\0<path>\0` with a
    second path for a rename or copy."""
    fields = raw.decode("utf-8", errors="surrogateescape").split("\0")
    entries = []
    i = 0
    while i < len(fields):
        head = fields[i]
        if not head.startswith(":"):
            i += 1
            continue
        old_mode, new_mode, old_id, new_id, status = head[1:].split(" ", 4)
        letter = status[:1]
        if letter in ("R", "C"):
            old_path, new_path = fields[i + 1], fields[i + 2]
            i += 3
        else:
            old_path = new_path = fields[i + 1]
            i += 2
        entries.append({
            "status": letter, "score": status[1:] or None,
            "old_path": old_path, "path": new_path,
            "old_mode": old_mode, "new_mode": new_mode,
            "old_id": old_id, "new_id": new_id,
        })
    return entries


def _binary_paths(numstat):
    """Paths git reports as binary: `-\t-\t` in `--numstat -z` output. A
    rename record is `-\t-\t\0<old>\0<new>\0`; otherwise `-\t-\t<path>\0`."""
    fields = numstat.decode("utf-8", errors="surrogateescape").split("\0")
    binary = set()
    i = 0
    while i < len(fields):
        rec = fields[i]
        if not rec:
            i += 1
            continue
        added, deleted, path = rec.split("\t", 2)
        if path == "":
            path = fields[i + 2]
            i += 3
        else:
            i += 1
        if added == "-" and deleted == "-":
            binary.add(path)
    return binary


def _entries(root, base_sha, tree):
    raw = _run_raw(root, ["diff", "--raw", "-z", "-M", "--no-abbrev", base_sha, tree,
                          "--", "."] + _EXCLUDE_SPEC)
    numstat = _run_raw(root, ["diff", "--numstat", "-z", "-M", base_sha, tree,
                              "--", "."] + _EXCLUDE_SPEC)
    binary = _binary_paths(numstat)
    entries = _parse_raw(raw)
    for entry in entries:
        entry["mode_changed"] = (entry["old_mode"] != entry["new_mode"]
                                 and "000000" not in (entry["old_mode"], entry["new_mode"]))
        entry["submodule"] = SUBMODULE_MODE in (entry["old_mode"], entry["new_mode"])
        entry["binary"] = entry["path"] in binary and not entry["submodule"]
        if entry["binary"]:
            entry["old_size"] = _blob_size(root, entry["old_id"])
            entry["new_size"] = _blob_size(root, entry["new_id"])
    return entries


def _ticket_base_tree(root, base_sha, working_tree, tmp_dir):
    """`(tree, merged, dropped, against)`: the tree the bundle diffs from. The
    start commit's tree, unless a merge of main applies; then that tree with
    each path identical to the merged commit in the working state set to its
    `working_tree` entry (absent when the working state has none), and each
    path main changed since the ticket forked from it that the working state
    changes again set to the merged commit's entry -- so main's lines read as
    context and only the ticket's as `+`/`-`. Written from a second temporary
    index. `dropped` and `against` are those `--raw` entries, sorted by path."""
    merged = merged_main.resolve(root, base_sha)
    base_tree = _run(root, ["rev-parse", base_sha + "^{tree}"]).strip()
    if not merged["applies"]:
        return base_tree, merged, [], []
    only = ["--", "."] + _EXCLUDE_SPEC
    raw = ["diff", "--raw", "-z", "--no-renames", "--no-abbrev"]
    since_base = _parse_raw(_run_raw(root, raw + [base_sha, working_tree] + only))
    since_merged = [e["path"] for e in
                    _parse_raw(_run_raw(root, raw + [merged["commit"], working_tree] + only))]
    kept = set(merged_main.keep([e["path"] for e in since_base], since_merged))
    dropped = sorted((e for e in since_base if e["path"] not in kept),
                     key=lambda e: e["path"])
    # What main changed since the ticket forked from it: the merge-base of the
    # start and the merged commit (the start itself when the ticket was cut
    # from main), so a ticket commit before a later-recorded start never reads
    # as main's. No fork, no rewrite: the start's entry shows more, never less.
    fork = crew_common.git_out(root, "merge-base", base_sha, merged["commit"])
    merged = dict(merged, fork=fork or None)
    if not fork:
        # The more-inclusive bundle stays (the start's entry shows more), but the
        # unknown is said wherever the answer reaches: manifest, stderr, prompt,
        # receipt note -- never an empty `diffed_from_merged` passing as "none".
        merged["fork_reason"] = (
            f"could not tell: git merge-base {base_sha[:12]} {merged['commit'][:12]} gave no "
            "answer; paths main also changed are diffed from the start, so main's lines "
            "there read as the ticket's")
    by_main = ({e["path"]: e for e in
                _parse_raw(_run_raw(root, raw + [fork, merged["commit"]] + only))}
               if fork else {})
    against = sorted((by_main[p] for p in kept if p in by_main), key=lambda e: e["path"])
    if not dropped and not against:
        return base_tree, merged, [], []
    env = {"GIT_INDEX_FILE": os.path.join(tmp_dir, "index2")}
    _run(root, ["read-tree", base_sha], env=env)
    # One `--index-info` record per rewritten path: the new side's mode and
    # blob, or mode 0 (remove) when that side has no such path.
    info = "".join(f"{e['new_mode']} {e['new_id']}\t{e['path']}\0" if e["new_mode"] != "000000"
                   else f"0 {e['new_id']}\t{e['path']}\0" for e in dropped + against)
    _run_raw(root, ["update-index", "-z", "--index-info"], env=env,
             data=info.encode("utf-8", errors="surrogateescape"))
    return _run(root, ["write-tree"], env=env).strip(), merged, dropped, against


def split_parts(data, max_bytes):
    """Split `data` (bytes) into ordered chunks of at most `max_bytes`,
    preferring `diff --git` file boundaries, then line boundaries, then the
    byte limit itself. `b"".join(result) == data` always holds -- this is a
    split, never a truncation."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    if not data:
        return []
    # File-level pieces: every `diff --git` header starts a new piece.
    pieces, start = [], 0
    marker = b"\ndiff --git "
    while True:
        nxt = data.find(marker, start)
        if nxt < 0:
            pieces.append(data[start:])
            break
        pieces.append(data[start:nxt + 1])
        start = nxt + 1
    # Anything still too big is cut at line ends, then at the byte limit.
    units = []
    for piece in pieces:
        if len(piece) <= max_bytes:
            units.append(piece)
            continue
        for line in piece.splitlines(keepends=True):
            while len(line) > max_bytes:
                units.append(line[:max_bytes])
                line = line[max_bytes:]
            if line:
                units.append(line)
    parts, current = [], b""
    for unit in units:
        if current and len(current) + len(unit) > max_bytes:
            parts.append(current)
            current = b""
        current += unit
    if current:
        parts.append(current)
    return parts


def bundle_sha256(parts):
    """sha256 over the parts in manifest order."""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part)
    return digest.hexdigest()


def compute(root, base, max_part_bytes=DEFAULT_MAX_PART_BYTES):
    """Build the bundle in memory: (manifest_dict, patch_bytes, parts).
    Writes nothing. Raises RuntimeError on any git failure, and on an empty
    patch despite detected changes."""
    root = os.path.abspath(root)

    head = _run(root, ["rev-parse", "HEAD"]).strip()
    try:
        base_sha = _run(root, ["rev-parse", "--verify", base + "^{commit}"]).strip()
    except RuntimeError as exc:
        raise RuntimeError(f"--base {base!r} does not resolve to a commit: {exc}") from exc
    branch = _run(root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()

    only = ["--", "."] + _EXCLUDE_SPEC
    staged_files = _lines(root, ["diff", "--cached", "--name-only"] + only)
    unstaged_files = _lines(root, ["diff", "--name-only"] + only)
    untracked_files = _lines(root, ["ls-files", "--others", "--exclude-standard"] + only)
    dirty = bool(staged_files or unstaged_files or untracked_files)

    real_index = _run(root, ["rev-parse", "--git-path", "index"]).strip()
    if not os.path.isabs(real_index):
        real_index = os.path.join(root, real_index)

    tmp_dir = tempfile.mkdtemp(prefix="review-patch-")
    tmp_index = os.path.join(tmp_dir, "index")
    try:
        if os.path.exists(real_index):
            shutil.copy2(real_index, tmp_index)
        env = {"GIT_INDEX_FILE": tmp_index}
        # Stage every working-tree change and every non-ignored untracked
        # file into the TEMPORARY index. `GIT_INDEX_FILE` redirects both the
        # read and the write here, so the real index -- and anything the
        # developer staged there for their own next commit -- is never
        # touched by this call. `test_review_patch.py` asserts
        # `git diff --cached --name-only` is byte-identical before and after.
        #
        # No exclude pathspec here (see the module docstring): it fails when
        # `.work` is gitignored. The diffs below exclude it instead.
        _run(root, ["add", "-A", "--", "."], env=env)
        working_tree = _run(root, ["write-tree"], env=env).strip()
        # T-0100: the start's tree, with every path identical to merged main
        # already at its working-state content and every path main also
        # changed at the merged commit's (module docstring).
        tree, merged, dropped, against = _ticket_base_tree(root, base_sha, working_tree,
                                                           tmp_dir)

        # ONE diff: base -> the full working state (committed range, staged,
        # unstaged and untracked all folded into the tree `write-tree` just
        # produced). Binary files get git's own "Binary files ... differ"
        # marker -- no `--binary` flag -- and `--full-index` puts both full
        # blob ids on the `index` line, so the bytes still change with them.
        patch = _run_raw(root, ["diff"] + _DIFF_FLAGS + [tree, working_tree] + only)
        entries = _entries(root, tree, working_tree)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # No list names a path the bundle left out as identical to merged main.
    gone = {e["path"] for e in dropped}
    committed_files = [p for p in _lines(root, ["diff", "--name-only", tree, head] + only)
                       if p not in gone]
    staged_files, unstaged_files, untracked_files = (
        [p for p in files if p not in gone]
        for files in (staged_files, unstaged_files, untracked_files))
    if not patch and (staged_files or unstaged_files or untracked_files or committed_files):
        # The bug this script exists to prevent: something was detected as
        # changed and the patch is still empty.
        raise RuntimeError(
            "empty patch despite detected changes "
            f"(dirty={dirty}, committed={len(committed_files)} files, "
            f"{len(gone)} identical to merged main left out) -- "
            "this is a defect in review_patch.py, not a clean diff"
        )

    parts = split_parts(patch, max_part_bytes)
    manifest = {
        "base": base_sha,
        "head": head,
        "branch": branch,
        "dirty": dirty,
        "committed_files": committed_files,
        "staged_files": staged_files,
        "unstaged_files": unstaged_files,
        "untracked_files": untracked_files,
        "entries": entries,
        "renames": [e["path"] for e in entries if e["status"] == "R"],
        "mode_changes": [e["path"] for e in entries if e["mode_changed"]],
        "binary_files": [e["path"] for e in entries if e["binary"]],
        "submodules": [e["path"] for e in entries if e["submodule"]],
        "excluded": list(EXCLUDED),
        "merged_main": dict(merged, dropped=sorted(gone),
                            diffed_from_merged=[e["path"] for e in against]),
        "bundle_base_tree": tree,
        "patch_bytes": len(patch),
        "max_part_bytes": max_part_bytes,
        "bundle_sha256": bundle_sha256(parts) if parts else None,
    }
    # Playwright repositories only: the trace zips and axe results the
    # reviewer opens beside the patch, bounded by webtest_guard.MAX_ARTIFACTS.
    listing = webtest_guard.artifacts(root)
    if listing is not None:
        manifest["webtest"] = listing
    return manifest, patch, parts


def part_name(index, total):
    return f"part-{index:03d}-of-{total:03d}.patch"


def build(root, base, out_path, manifest_path, parts_dir=None,
          max_part_bytes=DEFAULT_MAX_PART_BYTES):
    """Returns (manifest_dict, exit_code). Writes --out, the parts and
    --manifest only on EXIT_OK or EXIT_NOTHING_TO_REVIEW; raises
    RuntimeError on EXIT_ERROR so the caller can print the message and exit
    without half-written output."""
    manifest, patch, parts = compute(root, base, max_part_bytes)
    parts_dir = os.path.abspath(parts_dir or (out_path + ".parts"))
    manifest["patch_path"] = out_path
    manifest["parts_dir"] = parts_dir
    manifest["parts"] = [
        {"name": part_name(i, len(parts)), "path": os.path.join(parts_dir, part_name(i, len(parts))),
         "bytes": len(part), "sha256": hashlib.sha256(part).hexdigest()}
        for i, part in enumerate(parts, 1)
    ]
    # Every payload is computed above, in full, before any file is opened.
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    os.makedirs(parts_dir, exist_ok=True)
    for stale in os.listdir(parts_dir):
        if stale.startswith("part-") and stale.endswith(".patch"):
            os.remove(os.path.join(parts_dir, stale))
    for row, part in zip(manifest["parts"], parts):
        with open(row["path"], "wb") as fh:
            fh.write(part)
    # --out is written even when empty, so a caller that unconditionally
    # `cat`s it does not hit a missing file.
    with open(out_path, "wb") as fh:
        fh.write(patch)
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(manifest_text)
    return manifest, (EXIT_OK if patch else EXIT_NOTHING_TO_REVIEW)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--parts-dir")
    parser.add_argument("--max-part-bytes", type=int, default=DEFAULT_MAX_PART_BYTES)
    args = parser.parse_args(argv)
    if args.max_part_bytes < 1:
        parser.error("--max-part-bytes must be positive")

    try:
        manifest, code = build(args.root, args.base, args.out, args.manifest,
                               args.parts_dir, args.max_part_bytes)
    except RuntimeError as exc:
        sys.stderr.write(f"review-patch: {exc}\n")
        return EXIT_ERROR

    merged = manifest["merged_main"]
    if code == EXIT_NOTHING_TO_REVIEW and merged["dropped"]:
        sys.stderr.write(
            f"review-patch: nothing of this ticket's to review -- every change since "
            f"{manifest['base'][:12]} is identical to merged {merged['ref']} "
            f"{(merged['commit'] or '')[:12]}\n"
        )
    elif code == EXIT_NOTHING_TO_REVIEW:
        sys.stderr.write(
            f"review-patch: nothing to review -- {manifest['head'][:12]} "
            f"matches {manifest['base'][:12]} and the tree is clean\n"
        )
    else:
        sys.stderr.write(
            f"review-patch: {manifest['patch_bytes']} bytes in "
            f"{len(manifest['parts'])} part(s), "
            f"bundle={(manifest['bundle_sha256'] or '')[:12]} "
            f"base={manifest['base'][:12]} head={manifest['head'][:12]} "
            f"branch={manifest['branch']} dirty={manifest['dirty']}"
            f"{_merged_field(merged)}\n"
        )
    return code


def _merged_field(merged):
    """The summary line's `merged-main=` field."""
    if merged["applies"]:
        against = ("could-not-tell" if merged.get("fork", "") is None
                   else len(merged.get("diffed_from_merged") or []))
        return (f" merged-main={merged['commit'][:12]} dropped={len(merged['dropped'])}"
                f" diffed-from-merged={against}")
    return " merged-main=could-not-tell" if merged["commit"] is None else " merged-main=none"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
