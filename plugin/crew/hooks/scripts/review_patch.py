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

CLI: --root <repo> --base <sha> --out <patch-file> --manifest <json-file>

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
import json
import os
import shutil
import subprocess
import sys
import tempfile

GIT_TIMEOUT = 30

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOTHING_TO_REVIEW = 2


def _run(root, args, env=None):
    """Run `git -C root <args>`, raising RuntimeError with git's own stderr
    on a nonzero exit. Unlike `crew_common.git_out`, this never fails soft --
    a caller building the review input needs to know WHY it could not, not a
    silent None that a downstream `if` turns into "clean"."""
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    try:
        done = subprocess.run(
            ["git", "-C", root] + list(args),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=GIT_TIMEOUT, env=full_env, check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"git {' '.join(args)} could not run: {exc}") from exc
    if done.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({done.returncode}): {done.stderr.strip()}"
        )
    return done.stdout


def _lines(root, args, env=None):
    out = _run(root, args, env=env)
    return sorted({line for line in out.splitlines() if line.strip()})


def build(root, base, out_path, manifest_path):
    """Returns (manifest_dict, exit_code). Writes --out and --manifest only
    on EXIT_OK or EXIT_NOTHING_TO_REVIEW; raises RuntimeError on EXIT_ERROR
    so the caller can print the message and exit without half-written
    output."""
    root = os.path.abspath(root)

    head = _run(root, ["rev-parse", "HEAD"]).strip()
    try:
        base_sha = _run(root, ["rev-parse", "--verify", base + "^{commit}"]).strip()
    except RuntimeError as exc:
        raise RuntimeError(f"--base {base!r} does not resolve to a commit: {exc}") from exc
    branch = _run(root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()

    committed_files = _lines(root, ["diff", "--name-only", base_sha, head])
    staged_files = _lines(root, ["diff", "--cached", "--name-only"])
    unstaged_files = _lines(root, ["diff", "--name-only"])
    untracked_files = _lines(root, ["ls-files", "--others", "--exclude-standard"])
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
        _run(root, ["add", "-A"], env=env)
        working_tree = _run(root, ["write-tree"], env=env).strip()

        # ONE diff: base -> the full working state (committed range, staged,
        # unstaged and untracked all folded into the tree `write-tree` just
        # produced). Binary files get git's own "Binary files ... differ"
        # marker by default -- no `--binary` flag, so this never tries to
        # emit a binary patch body and crash on one.
        patch_text = _run(root, ["diff", base_sha, working_tree])
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    patch_bytes = patch_text.encode("utf-8", errors="replace")

    manifest = {
        "base": base_sha,
        "head": head,
        "branch": branch,
        "dirty": dirty,
        "committed_files": committed_files,
        "staged_files": staged_files,
        "unstaged_files": unstaged_files,
        "untracked_files": untracked_files,
        "patch_bytes": len(patch_bytes),
        "patch_path": out_path,
    }

    if not patch_bytes:
        if dirty or committed_files:
            # The bug this script exists to prevent: something was detected
            # as changed and the patch is still empty. Never write output
            # that would let a caller mistake this for a clean tree.
            raise RuntimeError(
                "empty patch despite detected changes "
                f"(dirty={dirty}, committed={len(committed_files)} files) -- "
                "this is a defect in review_patch.py, not a clean diff"
            )
        manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(manifest_text)
        # --out is still written, empty, so a caller that unconditionally
        # `cat`s it does not hit a missing file.
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("")
        return manifest, EXIT_NOTHING_TO_REVIEW

    # Both payloads computed above, in full, before either file is opened.
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(patch_text)
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(manifest_text)
    return manifest, EXIT_OK


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)

    try:
        manifest, code = build(args.root, args.base, args.out, args.manifest)
    except RuntimeError as exc:
        sys.stderr.write(f"review-patch: {exc}\n")
        return EXIT_ERROR

    if code == EXIT_NOTHING_TO_REVIEW:
        sys.stderr.write(
            f"review-patch: nothing to review -- {manifest['head'][:12]} "
            f"matches {manifest['base'][:12]} and the tree is clean\n"
        )
    else:
        sys.stderr.write(
            f"review-patch: {manifest['patch_bytes']} bytes, "
            f"base={manifest['base'][:12]} head={manifest['head'][:12]} "
            f"branch={manifest['branch']} dirty={manifest['dirty']}\n"
        )
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
