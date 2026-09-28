"""An upstream repository and a ticket clone that merges its main, for the
T-0100 suites (test_merged_main.py, test_completion_audit.py,
test_review_patch.py, test_review_receipt.py).

The shape is the one T-0092's review and gate tripped on: a ticket branch cut
from `origin/main`, main moving on underneath it, and the ticket merging main
back in. Everything is built under pytest's tmp_path; nothing here touches the
real repository, its git directory, or ~/.claude.

Every content edit changes the byte length of the file it edits, so a
same-second index write can never hide an edit behind a matching stat.
"""
from review_fixtures import git, init_repo

# The upstream seed, beside `init_repo`'s own `seed.txt`.
SEED = {
    "m.txt": "m v1\n",
    "gone.txt": "gone soon\n",
    "r_old.txt": "renamed by main, not by the ticket\n",
    "src/shared.py": "shared = 1\n",
    "other/x.py": "x = 1\n",
}

# What main does after the ticket starts: an edit, an add, a delete, a rename
# and an edit to a file the ticket edits again on top.
MAIN_EDITS = (
    ("write", "m.txt", "m v2, a longer line from main\n"),
    ("write", "m2.txt", "added by main\n"),
    ("delete", "gone.txt"),
    ("rename", "r_old.txt", "r_new.txt"),
    ("write", "src/shared.py", "shared = 1\nmain_line = 2\n"),
)

# The five paths MAIN_EDITS leaves byte-identical to the merged commit when
# the ticket does not edit `src/shared.py` again.
DROPPED = ["gone.txt", "m.txt", "m2.txt", "r_new.txt", "r_old.txt"]


def configure(root):
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "core.autocrlf", "false")


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def seed_upstream(tmp_path, files=None, name="upstream"):
    """`init_repo`'s repository on `main` plus `files` (default SEED), committed."""
    upstream = init_repo(tmp_path / name)
    for rel, text in (SEED if files is None else files).items():
        write(upstream, rel, text)
    git(upstream, "add", "-A")
    git(upstream, "commit", "-qm", "upstream seed")
    return upstream


def clone(upstream, tmp_path, branch="T-1", name="clone"):
    """A clone of `upstream` with `branch` cut from `origin/main`."""
    root = tmp_path / name
    git(tmp_path, "clone", "-q", str(upstream), str(root))
    configure(root)
    git(root, "checkout", "-q", "-b", branch, "origin/main")
    return root


def build(tmp_path, branch="T-1"):
    """`(clone, upstream, sha)`: the upstream seeded, the clone on `branch`,
    and `sha["base"]` the commit the ticket starts from (C0)."""
    upstream = seed_upstream(tmp_path)
    root = clone(upstream, tmp_path, branch)
    return root, upstream, {"base": git(root, "rev-parse", "HEAD")}


def advance_main(upstream, *edits):
    """Commit `edits` (default MAIN_EDITS) on the upstream's `main`. Each is
    `("write", path, text)`, `("delete", path)` or `("rename", old, new)`.
    Returns the new main commit."""
    for edit in edits or MAIN_EDITS:
        if edit[0] == "write":
            write(upstream, edit[1], edit[2])
            git(upstream, "add", "--", edit[1])
        elif edit[0] == "delete":
            git(upstream, "rm", "-q", "--", edit[1])
        elif edit[0] == "rename":
            git(upstream, "mv", "--", edit[1], edit[2])
        else:
            raise ValueError(f"unknown edit {edit!r}")
    git(upstream, "commit", "-qm", "main moves on")
    return git(upstream, "rev-parse", "HEAD")


def merge_main(root):
    """Fetch and merge `origin/main` (a merge commit unless it fast-forwards).
    Returns the merged commit, `origin/main`'s sha."""
    git(root, "fetch", "-q", "origin")
    git(root, "merge", "-q", "--no-edit", "origin/main")
    return git(root, "rev-parse", "origin/main")


def ticket_commit(root, rel, text, message="ticket work"):
    write(root, rel, text)
    git(root, "add", "--", rel)
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")
