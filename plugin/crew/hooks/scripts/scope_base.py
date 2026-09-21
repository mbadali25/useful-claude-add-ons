"""The commit a ticket STARTED from: the base its scope evidence diffs against.

Two questions used to share one answer. "What has not been verified yet" is
the Stop gate's question, and `.crew/.verify-verified-at` answers it: written
on every clean pass, it advances so the gate never re-runs what it has already
checked (verify-gate.sh, `record_verified`). "What has this ticket changed" is
the scope evidence's question -- the changed-file list `/crew:work` prints at
the end of an implementation turn and the list `scope_report.py` compares
against the ticket's declared paths -- and until crew 0.19.95 it was diffed
from that same marker. Measured with the real gate in a scratch repository: a
developer commits on its branch, the Stop passes and writes the marker at that
commit, and on the next turn `git diff --name-only <marker>` lists none of the
ticket's files while the branch still carries them. The evidence was whole for
exactly one turn.

The workaround was `developer.md`'s blanket ban on committing at all, which
kept every change in the working tree where a moving base could not lose it,
and which every brief in this repository then contradicted (T-0003). This
module is the fix underneath: a base that answers the second question only.

## The record

`.crew/.scope-base`, JSON, machine-local -- `.crew/*` is ignored and the
un-ignore list (`codemap/`, `endpoints.json`, `verify.json`) does not name it,
for the same reason the gate's marker is not tracked: where a ticket started
in THIS checkout is a fact about this checkout. A MAPPING keyed by ticket id,
one entry per ticket ever started here, so starting T-2 cannot lose T-1's
base and resuming T-1 later finds it (Codex, round 1: a single-value record
advanced T-1 to HEAD on resume).

**An existing entry is never overwritten with HEAD.** `record` is re-run
after a `/clear` with commits on the branch by then; a base that moved to
wherever HEAD had reached would drop every commit before it -- the same
defect in a different costume. That holds even when the recorded commit is
missing from this clone (a squash, a rebase): the entry is kept, `--record`
says so, and `resolve` falls back with the fallback named.

**A first record on a branch that already carries commits is itself a
fallback.** A fresh clone of a ticket branch has no record, and HEAD there is
past every commit the ticket made; recording HEAD would hide all of them
under a line labelled "recorded". So when HEAD is already past the
merge-base with the default branch, the merge-base is recorded instead,
marked `from: merge-base`, and every line derived from it -- `resolve`'s
source and reason, `--record`'s own line on every later re-record,
`scope_report`'s `outside-scope:` line -- carries the fallback marker.
Provenance is part of the entry and a second `--record` never upgrades it.
That over-reports on a branch carrying two tickets -- the safe direction,
and stated as such. Another ticket's entry is never evidence about this
one's start: T-1 recorded on `main` is an ancestor of every branch, and
letting it stand in for T-2's start hid T-2's commits (Codex, round 2).

## Unknown resolves to MORE, and says so on every derived line

When the entry is missing, names a commit this repository no longer contains,
or names one that is no longer an ancestor of HEAD, `resolve` falls back to
the merge-base with the default branch: everything on the branch, a superset
of anything the ticket did. It never falls back to the verification marker,
which is the narrower base this module exists to replace. The default branch
is resolved as `origin/HEAD`, then `origin/main`, then `main`, in that
order -- a clone made with `git clone -b <ticket-branch>` has no local `main`
at all, and trying only that name fell through to HEAD, the narrowest answer
(Codex, round 1). The reason names which ref was used. On the default branch
itself the merge-base IS HEAD, so the last resort is the working tree alone,
stated rather than silent.

`source` tells a caller mechanically what the reason tells a human:
`"record"` is the one non-fallback value. Everything else --
`"record-fallback"`, `"merge-base"`, `"head"`, None -- is a fallback, and a
caller printing a line derived from the base must mark that line, not only
some other line nearby: an unknown has to survive into every line derived
from it, or the reassuring line and the uninformative one look the same.
"""
import datetime
import json
import os
import sys

import crew_common

RECORD = os.path.join(".crew", ".scope-base")

# The only source that is not a fallback.
RECORDED = "record"

_REASON_RECORDED = "the commit {ticket} started from, recorded by /crew:work"
_REASON_RECORDED_FALLBACK = (
    "(fallback) recorded as the merge-base with {ref} because HEAD was "
    "already past it when {ticket} was first recorded here, so the true "
    "start is unknown and this shows MORE")
_REASON_NO_RECORD = "no scope base recorded for {ticket}"
_REASON_GONE = "start commit {sha} not in this clone"
_REASON_NOT_ANCESTOR = ("start commit {sha} is no longer an ancestor of HEAD "
                        "(rebased?)")
_FALLBACK = "; evidence is against merge-base {base} with {ref} (fallback)"
_LAST_RESORT = ("; no default branch to take a merge-base with, so the working "
                "tree alone (fallback)")
_NO_GIT = "; and git could not answer for this directory (fallback)"


def _is_commit(root, sha):
    if not sha or not isinstance(sha, str):
        return False
    return crew_common.git_out(root, "cat-file", "-e", f"{sha}^{{commit}}") is not None


def _is_ancestor(root, sha):
    # `git_out` is None for "git said no" and for "git could not run" alike.
    # Both fall back, and falling back shows more, so the collapse is safe here.
    return crew_common.git_out(
        root, "merge-base", "--is-ancestor", sha, "HEAD") is not None


def _default_ref(root):
    """The first of `origin/HEAD` (as the ref it points at), `origin/main`,
    `main` that names a commit here, or None. Named in every reason, since
    which one answered decides what the merge-base is."""
    sym = crew_common.git_out(root, "symbolic-ref", "--short",
                              "refs/remotes/origin/HEAD")
    candidates = [sym, "origin/main", "main"]
    for ref in candidates:
        if ref and _is_commit(root, ref):
            return ref
    return None


def _merge_base(root):
    """`(ref, sha)` for the merge-base with the default branch, or
    `(None, None)`."""
    ref = _default_ref(root)
    if not ref:
        return None, None
    base = crew_common.git_out(root, "merge-base", "HEAD", ref)
    return (ref, base) if base else (None, None)


def read_record(root):
    """The mapping `{ticket: {"base": sha, "from": ..., "recordedAt": ...}}`,
    or None when absent or unreadable.

    Unreadable is the SAME answer as absent on purpose: both fall back to
    showing more. The single-entry shape crew 0.19.95's first cut wrote
    (`{"ticket": ..., "base": ...}`) is read as a one-entry mapping rather
    than as "no record", so a checkout that recorded under it keeps its base.
    """
    text = crew_common.read_text(os.path.join(root, RECORD))
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("ticket"), str) and "base" in data:
        return {data["ticket"]: {k: v for k, v in data.items() if k != "ticket"}}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _entry(rec, ticket):
    entry = (rec or {}).get(ticket)
    if isinstance(entry, dict) and isinstance(entry.get("base"), str) and entry["base"]:
        return entry
    return None


def _is_fallback_entry(entry):
    """`from: merge-base with <ref>` -- recorded as a guess, read as one."""
    return str(entry.get("from", "HEAD")).startswith("merge-base")


def _fallback_ref(entry):
    return str(entry["from"]).split(" ", 2)[-1]


def _write(root, mapping):
    # The whole payload is built BEFORE the file is opened. `open(p, "w")`
    # truncates at open time, so an expression raising inside the write call
    # would leave a zero-byte record behind -- root CLAUDE.md's landmine.
    payload = json.dumps(mapping, indent=2, sort_keys=True) + "\n"
    path = os.path.join(root, RECORD)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)


def record(root, ticket):
    """Record where `ticket` starts, once. Returns `(sha, status)`.

    `status` is `"kept"` (an entry existed and was left alone),
    `"kept-fallback"` (left alone, and it was a merge-base guess when
    written, so it still is), `"kept-missing"` (left alone although its
    commit is not in this clone -- `resolve` will fall back and say so),
    `"recorded"` (HEAD written),
    `"recorded-fallback"` (the merge-base written because HEAD was already
    past it; see the module header), or `None` with `sha` None when nothing
    could be recorded -- not a repository, or no commit yet -- and nothing
    was written.
    """
    rec = read_record(root) or {}
    entry = _entry(rec, ticket)
    if entry:
        # NEVER overwritten, whatever state the commit is in -- and never
        # upgraded either: an entry recorded as a fallback stays a fallback
        # on every later read and re-record. Provenance is part of the entry
        # (Codex round 2: a second `--record` after `/clear` said "kept ...
        # as the start" over a merge-base guess).
        if not _is_commit(root, entry["base"]):
            return entry["base"], "kept-missing"
        if _is_fallback_entry(entry):
            return entry["base"], "kept-fallback"
        return entry["base"], "kept"
    head = crew_common.git_out(root, "rev-parse", "HEAD")
    if not head:
        return None, None
    # HEAD past the fork is an unknown start, full stop. Round 1 of review
    # suppressed the fallback when ANY earlier entry was an ancestor of HEAD
    # ("this checkout has been working this branch, so a second ticket
    # starting at HEAD is a known start"); round 2 found the hole -- T-1's
    # entry on main is an ancestor of every branch, so T-2 checked out with
    # commits made elsewhere recorded HEAD, unlabelled, and hid them. Only
    # THIS ticket's own entry could justify skipping the fallback, and when
    # one exists this function has already returned above. So a branch that
    # carries two tickets over-reports the first's commits as the second's,
    # labelled as a fallback on every derived line: the safe direction.
    ref, merge_base = _merge_base(root)
    if merge_base and merge_base != head:
        base, source = merge_base, f"merge-base with {ref}"
        status = "recorded-fallback"
    else:
        base, source, status = head, "HEAD", "recorded"
    updated = dict(rec)
    updated[ticket] = {
        "base": base,
        "from": source,
        "recordedAt": datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    _write(root, updated)
    return base, status


def resolve(root, ticket):
    """`(base, source, reason)` -- the commit the ticket's evidence diffs from.

    `source` is `"record"` for a start recorded at HEAD, and otherwise one of
    the fallbacks named in the module header, or None when git could not
    answer at all (not a repository), in which case `base` is None too. The
    reason is a sentence for a human and carries "(fallback)" whenever the
    source is not `"record"`.
    """
    entry = _entry(read_record(root), ticket)
    if entry is None:
        why = _REASON_NO_RECORD.format(ticket=ticket)
    elif not _is_commit(root, entry["base"]):
        why = _REASON_GONE.format(sha=entry["base"][:12])
    elif not _is_ancestor(root, entry["base"]):
        why = _REASON_NOT_ANCESTOR.format(sha=entry["base"][:12])
    elif _is_fallback_entry(entry):
        return entry["base"], "record-fallback", _REASON_RECORDED_FALLBACK.format(
            ref=_fallback_ref(entry), ticket=ticket)
    else:
        return entry["base"], RECORDED, _REASON_RECORDED.format(ticket=ticket)

    head = crew_common.git_out(root, "rev-parse", "HEAD")
    if not head:
        return None, None, why + _NO_GIT
    ref, base = _merge_base(root)
    if base:
        return base, "merge-base", why + _FALLBACK.format(base=base[:12], ref=ref)
    return head, "head", why + _LAST_RESORT


def changed(root, base):
    """Tracked paths that differ from `base` plus untracked ones, sorted and
    unique -- the two commands `/crew:work` prints, and the gate's own shape
    (`-c core.quotePath=false`, for the reason verify-gate.sh gives at its
    CHANGED= line). None when git could not answer."""
    tracked = crew_common.git_out(
        root, "-c", "core.quotePath=false", "diff", "--name-only", base)
    untracked = crew_common.git_out(
        root, "-c", "core.quotePath=false", "ls-files", "--others",
        "--exclude-standard")
    if tracked is None or untracked is None:
        return None
    return sorted({line.strip() for line in (tracked + "\n" + untracked).splitlines()
                   if line.strip()})


def _usage():
    return ("usage: scope_base.py --root <repo> (--record | --base | --changed) "
            "<ticket>\n")


def _record_message(root, ticket, sha, status):
    if status == "kept-missing":
        _ref, merge_base = _merge_base(root)
        against = (f"merge-base {merge_base[:12]}" if merge_base
                   else "the working tree alone")
        return (f"scope-base: start commit {sha[:12]} not in this clone; "
                f"evidence is against {against} (fallback); the record for "
                f"{ticket} is kept\n")
    if status in ("recorded-fallback", "kept-fallback"):
        verb = "kept" if status == "kept-fallback" else "recorded"
        return (f"scope-base: (fallback) {verb} {sha[:12]} as the start of "
                f"{ticket} - the merge-base with the default branch, because "
                f"HEAD was already past it when first recorded, so the true "
                f"start is unknown and this shows MORE ({RECORD})\n")
    verb = "kept" if status == "kept" else "recorded"
    return f"scope-base: {verb} {sha[:12]} as the start of {ticket} ({RECORD})\n"


def main(argv):
    """`--record` exits 1 when nothing could be recorded, because it is run
    once by a person at the start of work and a silent no-op there is the
    moving-base defect waiting to happen again. `--base` and `--changed`
    always exit 0: they always have an answer, and the reason on stderr says
    how good it is."""
    root = os.getcwd()
    action = None
    ticket = None
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--root" and args:
            root = args.pop(0)
        elif arg in ("--record", "--base", "--changed") and args:
            action = arg
            ticket = args.pop(0)
        else:
            sys.stderr.write(_usage())
            return 2
    if not action or not ticket:
        sys.stderr.write(_usage())
        return 2

    if action == "--record":
        sha, status = record(root, ticket)
        if not sha:
            sys.stderr.write(
                f"scope-base: could not record a start for {ticket} - "
                f"{root} is not a git repository or has no commit yet\n")
            return 1
        sys.stderr.write(_record_message(root, ticket, sha, status))
        sys.stdout.write(sha + "\n")
        return 0

    base, _source, reason = resolve(root, ticket)
    if base is None:
        sys.stderr.write(f"scope-base: ({reason})\n")
        # Something a shell can still hand to `git diff` and get a loud error
        # from, rather than an empty string that diffs against nothing.
        sys.stdout.write("HEAD\n" if action == "--base" else "")
        return 0
    sys.stderr.write(f"scope-base: {base[:12]} ({reason})\n")
    if action == "--base":
        sys.stdout.write(base + "\n")
        return 0
    paths = changed(root, base)
    if paths is None:
        sys.stderr.write("scope-base: (git could not list the changes)\n")
        return 0
    sys.stdout.write("".join(p + "\n" for p in paths))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
