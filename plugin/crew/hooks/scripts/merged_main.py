"""Which commit of the integration branch a ticket branch has merged, and the
one rule the review bundle and the completion audit share for it (T-0100).

THE DEFECT. Both `review_patch.compute` and `completion_audit.audit` diff from
the ticket's recorded start (`scope_base.resolve`). After the ticket merges
main, that diff carries every file main changed in between: the reviewer
re-reviews work that already landed (T-0092's round-2 bundle held T-0076,
T-0089 and T-0091's files), and `/crew:done` check 3 flags those files as
outside the ticket's Touch (16 paths for T-0092, 89 for T-0075, all waived by
hand as merge artifacts).

THE RULE. Keep diffing from the recorded start, then leave out every path
whose content and mode in the working state are byte-identical to the latest
merged integration commit -- `git merge-base HEAD <ref>`, which after a merge
of `<ref>` is the merged commit, and after a second merge the newer one.
`keep(since_base, since_merged)` is that rule: a path stays when it differs
from the start AND differs from the merged commit. So a ticket edit on top of
main's edit to the same file stays, as does any edit after the merge.

`<ref>` is the ticket base branch, `scope_base.base_branch` (T-0061:
`tickets.baseBranch` in `.crew/config.json` when set, else origin/HEAD's target,
origin/main, main), read through that one helper so both consumers measure
against the same branch the scope base does. A configured branch that names no
commit is could-not-tell with T-0061's own reason, never a fall back.

It never applies -- behaviour is exactly the recorded-start diff -- when:
  * HEAD's branch IS `<ref>` (or `<ref>` without `origin/`): there
    `merge-base HEAD <ref>` is HEAD and every commit since the start is the
    ticket's own (the `scope_base.py` docstring's on-main case);
  * the merged commit is an ancestor of the start: no merge of `<ref>` past
    the start is reachable from HEAD.

COULD NOT TELL. No base branch names a commit (or the configured one does
not), HEAD is detached, or git gives no answer: `resolve` returns `commit None`, `applies False` and a reason that
starts "could not tell". Nothing is dropped, and every line derived from it
(manifest, review-patch stderr, the prompt's bundle block, the audit verdict,
the receipt check) says so -- an unknown never reads as "nothing merged".

Corners, stated rather than special-cased: a fast-forward "merge" of main
makes HEAD the merged commit, so everything committed drops and only
working-tree edits remain (the ticket committed nothing of its own). A branch
already merged into main drops everything committed for the same reason. The
same fix landing on main and on the ticket, byte-identical, drops too. A
ticket that reverts a merged-in path to its start content is invisible here,
as it is to the recorded-start diff alone.
"""
import subprocess

import crew_common
import scope_base

UNKNOWN = "could not tell"


def _is_ancestor(root, older, newer):
    """True, False, or None when git could not answer."""
    try:
        done = subprocess.run(
            [crew_common.require_tool("git"), "merge-base", "--is-ancestor", older, newer], cwd=root,
            capture_output=True, timeout=crew_common.GIT_TIMEOUT, check=False,
            stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return {0: True, 1: False}.get(done.returncode)


def resolve(root, base_sha):
    """{"ref", "commit", "applies", "reason"} for the ticket that started at
    `base_sha`. `commit` is None only on could-not-tell."""
    ref, problem = scope_base.base_branch(root)
    if problem:
        return {"ref": None, "commit": None, "applies": False,
                "reason": f"{UNKNOWN}: {problem}; nothing dropped"}
    if not ref:
        return {"ref": None, "commit": None, "applies": False,
                "reason": f"{UNKNOWN}: no integration ref (origin/HEAD, origin/main, main) "
                          "names a commit here; nothing dropped"}
    branch = crew_common.git_out(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    if not branch:
        return {"ref": ref, "commit": None, "applies": False,
                "reason": f"{UNKNOWN}: HEAD is detached, so which commits since the start "
                          f"are {ref}'s cannot be told; nothing dropped"}
    if branch in (ref, ref.removeprefix("origin/")):
        return {"ref": ref, "commit": crew_common.git_out(root, "rev-parse", "HEAD"),
                "applies": False,
                "reason": f"HEAD is on {branch} itself; every commit since the start is "
                          "this ticket's; nothing dropped"}
    commit = crew_common.git_out(root, "merge-base", "HEAD", ref)
    if not commit:
        return {"ref": ref, "commit": None, "applies": False,
                "reason": f"{UNKNOWN}: git merge-base HEAD {ref} gave no answer; "
                          "nothing dropped"}
    before = _is_ancestor(root, commit, base_sha)
    if before is None:
        return {"ref": ref, "commit": None, "applies": False,
                "reason": f"{UNKNOWN}: git merge-base --is-ancestor {commit[:12]} "
                          f"{str(base_sha)[:12]} gave no answer; nothing dropped"}
    if before:
        return {"ref": ref, "commit": commit, "applies": False,
                "reason": f"no merge of {ref} past the ticket start {base_sha[:12]}; "
                          "nothing dropped"}
    return {"ref": ref, "commit": commit, "applies": True,
            "reason": f"merged {ref} at {commit[:12]}; paths identical to it are left out"}


def keep(since_base, since_merged):
    """The paths of `since_base` that also differ from the merged commit:
    a path drops only when it is in the base diff AND identical to the merged
    commit (absent from `since_merged`). Sorted."""
    return sorted(set(since_base) & set(since_merged))


def bare_reason(merged):
    """`merged["reason"]` without its "could not tell: " lead and its
    "; nothing dropped" tail, for a line that states both in its own words."""
    reason = str((merged or {}).get("reason") or "")
    return reason.removeprefix(UNKNOWN + ": ").removesuffix("; nothing dropped")
