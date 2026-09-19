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


def _material(changed):
    """The changed paths that can move the verdict.

    `.crew/` is EXCLUDED, and it has to be: the gate writes its own markers
    there -- `.verify-verified-at`, `.verify-gate.fingerprint`, the lock --
    so every run changes that directory and the next fingerprint would never
    match the last. Measured: with `.crew/` included the skip never fired
    once, because the run that recorded the digest invalidated it on the way
    out.

    Nothing is lost by dropping it. The only two files under `.crew/` that
    decide anything -- verify.json and config.json -- are hashed explicitly
    as deciders above, by content, whether or not git calls them changed.
    """
    out = []
    for path in changed:
        if not path:
            continue
        norm = path.replace(os.sep, "/")
        if norm == ".crew" or norm.startswith(".crew/"):
            continue
        out.append(path)
    return out


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
    for rel in sorted(set(p for p in changed if p)):
        digest.update(b"\0path=")
        digest.update(rel.encode("utf-8", "replace"))
        digest.update(b":")
        digest.update(_file_digest(os.path.join(root, rel)).encode("ascii"))

    return digest.hexdigest()[:16]


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    changed = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]
    sys.stdout.write(fingerprint(root, changed) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
