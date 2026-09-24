"""A digest of everything verify-gate's verdict depends on.

Stop fires once per TURN, and a turn that edited nothing the gate cares about
re-runs the whole map to reach the same answer it reached a minute ago. The
event is not the gate; the STATE is.

## What is in it, and why each piece has to be

* **HEAD.** A commit moves the baseline every rule is evaluated against.
* **The changed-path set AND the bytes of each path.** The paths alone are not
  enough: editing a file without adding or removing one leaves the set
  identical while changing what every check would see. Contents are hashed,
  not stat()ed. An mtime comparison is cheaper and is wrong in the direction
  that matters -- same size and a same-granularity write reads as unchanged,
  and the gate would skip a real edit. A file's absence is itself recorded, so
  deleting one moves the digest.
* **Each changed path's INDEX entry -- mode, blob id and stage.** The working
  tree is not the only thing a check reads. `git show :a.txt`, `git diff
  --cached` and every lint that runs off the index read the STAGED copy, and
  a mode is not in the bytes at all. See _index_entries for the two measured
  skips that each of those halves cost.
* **A SUBMODULE's own contents, hashed the way this module hashes any
  repository.** A gitlink is a DIRECTORY, and reading a directory as a file
  produced the "absent" marker -- so a check reading `sub/a.txt` was
  skippable by editing `sub/a.txt`, whose gitlink sha does not move. See
  _submodule_digest.

THE INVARIANT ALL OF THAT SERVES, stated once because it is the thing to test
against rather than the list above: **if `--all` would FAIL on a tree, a Stop
on that same tree must not skip on a recorded fingerprint.** Every defect
found here so far has had the identical signature -- the digest hashed
something other than what the check would actually read, so Stop exited 0
while `--all` exited 2 on one unchanged tree. test_verify_gate_fingerprint.py
asserts the invariant directly, over a table of tree states, rather than only
the individual causes; a new way to move what a check reads without moving the
digest fails there even when nobody thought to add a case for it.
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
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(newline="\n")
except (AttributeError, ValueError):
    pass

_VERSION = b"crew-verify-fingerprint-v1"

# Hashed alongside the changed files because they decide, respectively, WHICH
# commands run and HOW MANY of them fit in the budget.
_DECIDERS = (os.path.join(".crew", "verify.json"),
             os.path.join(".crew", "config.json"))

# NOT in _DECIDERS, deliberately, and NOT hashed by content at all - see
# _corrupt_cache below for why. These are the per-rule record and the
# measured-timings cache verify_record.py writes on the way OUT of a clean
# run; _GATE_OWNED_FILES already excludes them from _material's byte-hashing
# (hashing them there would self-invalidate the fingerprint the run that
# wrote them just recorded, one turn later, for a self-referential reason
# rather than a real change).
_CACHE_FILES = (os.path.join(".crew", ".verify-gate.record.json"),
                os.path.join(".crew", ".verify-gate.timings.json"))


def _corrupt_cache(root):
    """True when a per-rule record or timings file EXISTS but is not valid
    JSON. A quiet turn with one of these corrupted used to skip anyway -
    nothing in the digest depended on their bytes - so a chronic rule's
    standing notice, or a cached measurement, could be lost by a corrupted
    cache file and nobody would ever know, because the gate kept reporting
    "nothing changed" forever after. The fingerprint does not hash these
    files' CONTENT (that would self-invalidate on every normal write, see
    above); it only asks whether they PARSE. A present-and-corrupt file
    means the record cannot be trusted, so the digest is poisoned - main()
    prints an empty fingerprint, which the gate reads the same way it reads
    "no python": never skip.
    """
    for rel in _CACHE_FILES:
        full = os.path.join(root, rel)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # STRUCTURALLY wrong is corrupt too, not just invalid JSON.
            # `[]` parses fine - no exception - so a plain "did json.load
            # raise" check read it as healthy. verify_record.py's own
            # `_load` already makes this same isinstance check when READING
            # these files; this is the reused check, not a new one.
            if not isinstance(data, dict):
                return True
        except (OSError, ValueError):
            return True
    return False


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
    # The per-rule record and the measured-timings cache, both written by
    # verify_record.py on the way out of a clean run, same reason as the
    # two above: including them means every run invalidates the digest it
    # just recorded, and the skip never fires. Named, not a `.crew/` prefix
    # -- see the note above this set for why a blanket exclusion is wrong.
    ".crew/.verify-gate.record.json",
    ".crew/.verify-gate.timings.json",
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


def _index_entries(root):
    """Every tracked path's INDEX entry -- mode, blob id and stage -- as one
    `git ls-files -s` call.

    The working tree is not the only thing a check reads, and each half of
    this entry covers a measured skip of a tree that `--all` fails:

    * **The staged CONTENTS, as the blob id.** A check that reads the index --
      `git show :a.txt`, `git diff --cached`, a lint run off the staged copy
      -- sees something the file on disk does not have to match. Measured:
      with a rule on `git show :a.txt`, staging failing contents and then
      restoring the passing contents in the working tree left the digest
      byte-identical, so Stop skipped with exit 0 while `--all` exited 2 on
      that same tree. The blob id IS the staged contents, so hashing it covers
      the index exactly -- and for free, since this call was already being
      made for the mode.

    * **The MODE.** Bytes alone miss a mode flip. A committed one is caught
      already -- it moves HEAD, which is hashed -- but a staged, uncommitted
      `git update-index --chmod=+x` is not: measured, the digest was
      byte-identical across one. A check that depends on `+x` would then be
      skipped on a tree whose executable bit had just changed, which is not
      hypothetical -- a script shipped 100644 in this marketplace and failed
      with permission denied on Linux.

    EVERY stage is kept and joined, not just the last one read. A path in a
    merge conflict has three entries (stages 1, 2 and 3) and `ls-files -s`
    prints all of them; keeping only the last would let a resolution that
    rewrote the other two leave the digest where it was.

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
    entries = {}
    for record in (out.stdout or "").split(chr(0)):
        if not record:
            continue
        meta, _, path = record.partition(chr(9))
        fields = meta.split()
        # `<mode> <blob id> <stage>`. Anything shorter is a git printing a
        # shape this does not understand, and recording a partial entry would
        # be a digest that looks covered and is not -- the collapse this file
        # exists to avoid. Dropped, so the path falls back to "untracked".
        if path and len(fields) >= 3:
            entries.setdefault(path, []).append(" ".join(fields[:3]))
    # Sorted so the stage order git happened to print cannot move the answer.
    return dict((path, ",".join(sorted(vals)))
                for path, vals in entries.items())


# A gitlink nested inside a gitlink is legal, and git alone cannot build a
# cycle -- but a symlink can, and an unbounded recursion inside a Stop hook is
# a hung turn rather than a wrong answer. The limit is a BOUND, not a
# judgement about how deep a real tree goes. Exceeding it hashes a DISTINCT
# marker rather than the "absent" constant, so a too-deep submodule can never
# be mistaken for one that is not there.
_MAX_SUBMODULE_DEPTH = 4


def _sub_changed(root):
    """What git says has changed inside a repository -- the same two listings
    verify-gate takes for the top level, so a submodule is measured by the
    same rule as its parent."""
    out = []
    for args in (("diff", "--name-only", "HEAD"),
                 ("ls-files", "--others", "--exclude-standard")):
        try:
            done = subprocess.run(
                ("git", "-c", "core.quotePath=false") + args, cwd=root,
                capture_output=True, text=True, check=False,
                stdin=subprocess.DEVNULL)
        except OSError:
            continue
        out.extend(line for line in (done.stdout or "").split(chr(10))
                   if line.strip())
    return out


def _submodule_digest(full, depth):
    """A submodule is a repository, so hash it as one -- recursively, through
    this same function.

    WHY THE GITLINK SHA IS NOT ENOUGH, given it is in the digest already
    through _index_entries: a submodule whose working tree is dirty carries
    contents that recorded sha does not describe. Measured -- a rule on `sub`
    running `grep -q good sub/a.txt` passed, `sub/a.txt` was then edited from
    `good` to `bad` with the gitlink left at `160000 4a179f05...`, and the
    next Stop skipped with exit 0 while --all exited 2. Third instance of one
    class: the digest hashing something other than what the check reads.

    `open()` on a directory raises, so before this a gitlink hashed to the
    "absent" constant -- the same value a DELETED file gets, which is why
    nothing about it looked wrong.

    Recursion rather than a bespoke walk, deliberately: a submodule needs
    exactly the coverage its parent needs -- HEAD, the changed paths, their
    bytes AND their index entries -- and a second implementation of that is a
    second thing to keep in step. Nested submodules fall out for free.

    The two `_DECIDERS` are hashed inside the submodule too, and will almost
    always be absent there. That is a constant: a few bytes of hash input and
    no answer changed. Not worth a special case that would stop this being
    the same function.
    """
    if depth >= _MAX_SUBMODULE_DEPTH:
        return "submodule-depth-limit"
    return "submodule:" + fingerprint(full, _sub_changed(full), depth + 1)


def fingerprint(root, changed, _depth=0):
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
    index = _index_entries(root)
    for rel in sorted(set(p for p in changed if p)):
        full = os.path.join(root, rel)
        # "untracked" is its own value rather than an empty string, so a file
        # becoming tracked moves the digest too.
        entry = index.get(rel.replace(os.sep, "/"), "untracked")
        digest.update(b"\0path=")
        digest.update(rel.encode("utf-8", "replace"))
        digest.update(b":")
        # Mode 160000 is a GITLINK, and a gitlink is a directory: `open()` on
        # it raises, so it used to hash as "absent". Dispatched on the INDEX
        # MODE rather than on os.path.isdir, because a directory also reaches
        # this list as git's collapsed entry for a wholly untracked one, and
        # that is not a repository to recurse into. Any stage counts -- a
        # conflicted gitlink is still a gitlink.
        if any(e.startswith("160000") for e in entry.split(",")):
            digest.update(_submodule_digest(full, _depth).encode("ascii"))
        else:
            digest.update(_file_digest(full).encode("ascii"))
        digest.update(b":index=")
        # The WORKING-TREE side above and the INDEX entry here, both, and
        # deliberately both: where the two differ they are two different
        # things a check can read, and hashing one leaves the other free to
        # move.
        digest.update(entry.encode("ascii", "replace"))

    return digest.hexdigest()[:16]


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    # NOT stripped. Leading and trailing whitespace is part of a filename, and
    # stripping it hashed a DIFFERENT path -- measured: a rule mapped to
    # " leading.txt" passed, the file's contents were then edited to fail, and
    # the next Stop skipped with exit 0 while --all exited 2 on that tree. The
    # matcher inside verify-gate.sh splits its own copy of this same list the
    # same way -- on the newline alone, keeping the line verbatim -- so the
    # digest now covers the path string the rules are matched against rather
    # than a trimmed lookalike of it.
    changed = [l for l in sys.stdin.read().split(chr(10)) if l.strip()]
    if _corrupt_cache(root):
        # Empty output, not a raised error: the caller's guard is
        # `[ -n "$FINGERPRINT" ]` (sh) / `if ($fingerprint)` (ps1), the same
        # "no python -> no fingerprint -> no skip" fail-safe already used
        # when the interpreter itself is missing.
        sys.stdout.write("\n")
        return 0
    sys.stdout.write(fingerprint(root, changed) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
