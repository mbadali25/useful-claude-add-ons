"""A fixed train base for the promote-gate fixtures (SRL-3312).

`requireReview: false` waives review only when the map's `reviewWaiverSha`
equals the promotion's train base (`_promote_review.train_base_sha`: the
merge-base of the promoted sha with the base branch). A commit cannot name its
own sha, and a fixture map is committed AFTER the base it names, so every
fixture seeds one empty-tree commit with a fixed author, date and message -
its sha is therefore the same everywhere, `TRAIN_BASE` - makes it the first
commit and points `refs/remotes/origin/main` at it. A fixture map then names
`TRAIN_BASE` in `reviewWaiverSha`, exactly as a real map names the commit its
train was cut from.
"""
import hashlib
import subprocess

_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_BODY = (f"tree {_EMPTY_TREE}\n"
         "author Train Base <train-base@example.invalid> 1700000000 +0000\n"
         "committer Train Base <train-base@example.invalid> 1700000000 +0000\n"
         "\ntrain base\n").encode()
TRAIN_BASE = hashlib.sha1(b"commit %d\0" % len(_BODY) + _BODY).hexdigest()  # noqa: S324


def seed_train_base(root):
    """Make TRAIN_BASE the first commit of the fresh repository at `root` (no
    commits yet) and point origin/main at it; returns TRAIN_BASE."""
    def git(*args, data=None):
        return subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                              input=data, stdin=None if data else subprocess.DEVNULL).stdout
    made = git("hash-object", "-w", "-t", "commit", "--stdin", data=_BODY).decode().strip()
    assert made == TRAIN_BASE, made
    git("update-ref", "HEAD", TRAIN_BASE)
    git("update-ref", "refs/remotes/origin/main", TRAIN_BASE)
    git("reset", "-q", "--hard", "HEAD")
    return TRAIN_BASE
