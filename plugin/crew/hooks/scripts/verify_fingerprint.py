"""A digest of everything verify-gate's verdict depends on.

Stop fires once per TURN, and a turn that edited nothing the gate cares about
re-runs the whole map to reach the same answer it reached a minute ago. The
event is not the gate; the STATE is -- the same argument pm_pulse.py makes in
its own header, and this is the same mechanism pointed at a different verdict.

## What is in it, and why each piece has to be

* **HEAD.** A commit moves the baseline every rule is evaluated against.
* **The changed-path set AND the bytes of each path.** The paths alone are not
  enough: editing a file without adding or removing one leaves the set
  identical while changing what every check would see. Contents are hashed,
  not stat()ed. An mtime comparison is cheaper and is wrong in the direction
  that matters -- same size and a same-granularity write reads as unchanged,
  and the gate would skip a real edit. A file's absence is itself recorded, so
  deleting one moves the digest.
* **`.crew/verify.json`.** It decides which commands run at all.
* **`.crew/config.json`.** It carries `verify.stopBudgetSeconds`, so it
  decides which of them fit.

## What is deliberately NOT in it

Wall-clock time, the session id, and anything about the environment. A check
that depends on the network or on an installed tool can pass now and fail in
an hour, and no fingerprint can see that. This is the same assumption
`.crew/.verify-verified-at` has always made; it is written down here rather
than left implicit.

## The skip is only ever taken after a CLEAN run

The caller records a digest only when the gate ran EVERYTHING and everything
passed -- not after a failure, and not after the Stop budget deferred a rule.
A deferred rule was never checked, so recording it would turn "we ran out of
budget" into "this tree is verified", which is the collapse of an unknown into
a safe-looking value that this repository keeps having to fix. That rule lives
in the callers because they are the ones that know how the run went; the
comment is here because this is where somebody will come looking.

Used by BOTH flavours, for the reason scope_report.py gives: re-deriving a
hash in bash and again in PowerShell is two implementations that drift from
each other, and a gate that skips on one shell and runs on the other is worse
than either answer.
"""
import hashlib
import os
import subprocess
import sys

_VERSION = b"crew-verify-fingerprint-v1"

# Hashed alongside the changed files because they decide, respectively, WHICH
# commands run and HOW MANY of them fit in the budget.
_DECIDERS = (os.path.join(".crew", "verify.json"),
             os.path.join(".crew", "config.json"))


def _head(root):
    """The commit the checks are evaluated against, or a marker when there is
    none. A repo with no commits yet is a real state, not an error."""
    try:
        out = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=root, capture_output=True,
            text=True, check=False, stdin=subprocess.DEVNULL)
    except OSError:
        return "no-git"
    return (out.stdout or "").strip() or "no-head"


def _file_digest(path):
    """The bytes of a file, or a distinct marker for "not there".

    The marker matters: a deleted file must move the fingerprint, and reading
    a missing file as empty would make deleting an empty file invisible.
    """
    try:
        with open(path, "rb") as handle:
            return hashlib.sha1(handle.read()).hexdigest()
    except OSError:
        return "absent"


# The files THIS GATE writes, and only those. They have to come out of the
# digest because the gate updates them on the way out of a clean run, so
# including them means every run invalidates the digest it just recorded --
# measured: the skip never fired once until they were excluded.
#
# NAMED, not a `.crew/` prefix. Excluding the whole directory was wrong and
# was caught in review: a repo can legitimately MAP a path under `.crew/` to a
# check, and a blanket exclusion let a mapped `.crew/` file change its
# contents, keep the old fingerprint and skip verification entirely.
# Reproduced before the fix: a rule on `.crew/check.txt` passed, the file was
# then edited to fail, and the next Stop skipped and exited 0.
#
# Anything else under `.crew/` -- including another hook's markers -- stays IN
# the digest. That can only cause an extra run, which is the safe direction.
_GATE_OWNED_FILES = frozenset({
    ".crew/.verify-verified-at",
    ".crew/.verify-gate.fingerprint",
})
_GATE_OWNED_DIRS = (".crew/.verify-gate.lock/",)


def _gate_owned(norm):
    # Bare `.crew` / `.crew/` is the COLLAPSED DIRECTORY entry git emits when
    # the whole directory is untracked. It is not a file -- it hashes to the
    # same "absent" constant whatever is inside it -- so it can neither carry
    # content coverage nor self-invalidate, and it stands for a directory
    # dominated by this gate's own markers. Excluded so it cannot imply
    # coverage it does not provide. A repo that maps a real FILE under
    # `.crew/` still gets that file hashed individually.
    if norm.endswith("/"):
        norm = norm[:-1]
    return (norm in _GATE_OWNED_FILES
            or norm in (".crew", ".crew/.verify-gate.lock")
            or norm.startswith(_GATE_OWNED_DIRS))


def _material(changed):
    """The changed paths that can move the verdict, minus this gate's own
    markers. See _GATE_OWNED_FILES for why the exclusion is by name."""
    out = []
    for path in changed:
        if not path:
            continue
        if _gate_owned(path.replace(os.sep, "/")):
            continue
        out.append(path)
    return out


def _modes(root):
    """Every tracked path's staged file mode, as one `git ls-files` call.

    In the digest because BYTES ALONE MISS A MODE FLIP. A committed one is
    caught already -- it moves HEAD, which is hashed -- but a staged,
    uncommitted `git update-index --chmod=+x` is not: measured, the digest was
    byte-identical across one. A check that depends on `+x` would then be
    skipped on a tree whose executable bit had just changed, which is not
    hypothetical -- a script shipped 100644 in this marketplace and failed
    with permission denied on Linux.

    No pathspec, so this cannot hit the argument-length limit the gate works
    around elsewhere; the repo is walked once and the result looked up.

    `-z` is what guarantees unquoted paths here -- measured: with `-z`, git
    prints the raw name whatever `core.quotePath` says, and without it the
    same call returns the escaped, double-quoted form. The explicit
    `core.quotePath=false` is therefore REDUNDANT on this call and is kept
    only to state the intent beside the gate's own listings, which are not
    `-z` and genuinely need it. Sabotage confirmed the redundancy: removing
    the flag here changes nothing, so do not read its presence as the thing
    doing the work.
    """
    try:
        out = subprocess.run(
            ("git", "-c", "core.quotePath=false", "ls-files", "-s", "-z"),
            cwd=root, capture_output=True, text=True, check=False,
            stdin=subprocess.DEVNULL)
    except OSError:
        return {}
    modes = {}
    for record in (out.stdout or "").split(chr(0)):
        if not record:
            continue
        meta, _, path = record.partition(chr(9))
        fields = meta.split()
        if path and fields:
            modes[path] = fields[0]
    return modes


def fingerprint(root, changed):
    """A stable digest of the material verify-gate's verdict depends on."""
    changed = _material(changed)
    digest = hashlib.sha1()
    digest.update(_VERSION)
    digest.update(b"\0head=")
    digest.update(_head(root).encode("utf-8", "replace"))

    for rel in _DECIDERS:
        digest.update(b"\0decider=")
        digest.update(rel.encode("utf-8", "replace"))
        digest.update(b":")
        digest.update(_file_digest(os.path.join(root, rel)).encode("ascii"))

    # Sorted so the shell's ordering cannot move the answer on its own.
    modes = _modes(root)
    for rel in sorted(set(p for p in changed if p)):
        digest.update(b"\0path=")
        digest.update(rel.encode("utf-8", "replace"))
        digest.update(b":")
        digest.update(_file_digest(os.path.join(root, rel)).encode("ascii"))
        digest.update(b":mode=")
        # "untracked" is its own value rather than an empty string, so a
        # file becoming tracked moves the digest too.
        digest.update(modes.get(rel.replace(os.sep, "/"), "untracked")
                      .encode("ascii", "replace"))

    return digest.hexdigest()[:16]


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    changed = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]
    sys.stdout.write(fingerprint(root, changed) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
