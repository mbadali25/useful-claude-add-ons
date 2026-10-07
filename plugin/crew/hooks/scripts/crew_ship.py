"""T-0011's ship phase, the part with no review ledger in it: the pure merge
rule (`ship_decision`) and the gh/git adapter `crew_autopilot.ship` drives.

Split out of `crew_autopilot.py` in batch 7, when T-0020, T-0011 and T-0063
together took that module past pylint's 3400-line cap. What reads the review
ledger -- the gate re-read on every poll, the receipt check, the ship action
itself -- stays in `crew_autopilot.py`, which `scripts/check-tooling-pr.py`
lists in `SEAM`; nothing here reads a harness format.

`_run_gh` is the only code that runs gh and `_push` the only push; both run
the tool `crew_common.require_tool` resolves (L-1508), and a tool that is not
on PATH takes the same failure path as one that could not start. gh 2.46's
`gh pr checks` has no --json, so `read_checks` parses its text rows, names and
buckets verbatim, and a row that is not exactly five fields makes the whole
read unreadable. Standard library only, plus `crew_common`.

The rule, moved here from crew_autopilot.py's docstring (T-0012's port, the same
3400-line cap): `ship_decision` is the rule, with no I/O: `autopilot.ship` anything but
exactly `merge` opens the PR and stops. `merge` needs every required check
`pass`, or `fail` named EXACTLY in `autopilot.knownFailures`; pending or none
reported yet waits (stopping at `ciTimeoutMinutes`); an unreadable or unknown
state, `skipping` or an unlisted failure stops. A `high` or unknown risk whose
completed rounds are all `claude` or carry no `model_family` stops before CI
is read. `ship` refuses a dirty working tree (before the push and again before
the merge), takes HEAD once right after the push and holds the PR's head and
this checkout's HEAD to it before and after every poll and right before the
merge, re-reads the settings, risk and review families (with the hash of the
ledger bytes they came from) on every poll, stops on a green that lands past
the deadline, re-checks the review receipt after CI against that same ledger
hash, refuses a base branch with a merge queue (or one it cannot read), binds
the merge to the HEAD it checked, and dequeues a PR gh queued anyway.
The rule and the gh/git adapter (`_run_gh`, the only code that runs gh, and
`read_checks`, which parses gh 2.46's text rows) are here; `crew_autopilot.ship` drives them.
"""
import json
import re
import subprocess

import crew_common
from crew_common import git_out

# A review is same-family when its `model_family` is `claude` or absent: the
# session's own family is recorded nowhere, so an unknown one counts as the
# author's -- the refusing direction.
SAME_FAMILY = ("claude", None)
# Only these risks may merge on same-family reviews; anything else, an
# unknown or misspelt risk included, is treated as `high`.
LOW_RISKS = ("low", "med")
CHECK_STATES = ("pass", "fail", "pending", "skipping")


def _family(value):
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return None


def ship_decision(policy, risk, checks, families, known_failures):
    """`{"action": "open-pr"|"merge"|"wait"|"stop", "reason"}` -- the whole
    rule that lets autopilot merge unattended, with no I/O.

    `checks` is the required checks, `[{"name", "state"}]` with state one of
    CHECK_STATES, or None when they could not be read. `families` is the
    `model_family` of every completed review round. Any policy but exactly
    `merge` opens a PR and stops. A merge needs every required check `pass`,
    or `fail` with its name EXACTLY in `known_failures`; `skipping` is not
    `pass`. No check reported yet waits, as pending does; the caller's
    timeout turns a wait into a stop."""
    if policy != "merge":
        return {"action": "open-pr", "reason": f"autopilot.ship is {policy!r}: the PR is "
                "opened and a person merges it"}
    if risk not in LOW_RISKS and all(_family(f) in SAME_FAMILY for f in families or ()):
        return {"action": "stop", "reason": (
            f"same-family review only on a {risk or 'unknown'}-risk ticket: every completed "
            f"round is claude or has no model_family ({list(families or ())}), so a "
            "cross-family review or a person merges it")}
    if not isinstance(checks, list):
        return {"action": "stop", "reason": "the required checks could not be read - "
                "never merged on a state that could not be read"}
    if not checks:
        return {"action": "wait", "reason": "no required check reported yet"}
    known = [k for k in (known_failures if isinstance(known_failures, (list, tuple)) else ())
             if isinstance(k, str)]
    rows = [(c.get("name"), c.get("state")) if isinstance(c, dict) else (None, None)
            for c in checks]
    unread = [str(n) for n, s in rows if not isinstance(n, str) or s not in CHECK_STATES]
    if unread:
        return {"action": "stop", "reason": "could not read the state of required check(s) "
                + ", ".join(unread) + " - never merged on a state that could not be read"}
    failed = [n for n, s in rows if s == "fail" and n not in known]
    if failed:
        return {"action": "stop", "reason": "required check(s) failed: " + ", ".join(failed)
                + " (not in autopilot.knownFailures)"}
    skipped = [n for n, s in rows if s == "skipping"]
    if skipped:
        return {"action": "stop", "reason": "required check(s) skipped: " + ", ".join(skipped)
                + " - skipped is not pass, so a person merges"}
    pending = [n for n, s in rows if s == "pending"]
    if pending:
        return {"action": "wait", "reason": "required check(s) pending: " + ", ".join(pending)}
    allowed = sorted({n for n, s in rows if s == "fail"})
    return {"action": "merge", "reason": "every required check passed" + (
        " except known failure(s) " + ", ".join(allowed) if allowed else "")}


# `gh pr checks` (gh 2.46 has no --json for it) prints, off a TTY, one row per
# check and exits 0 (all passed), 1 (a failure) or 8 (pending). The row is
# `name<TAB>bucket<TAB>elapsed<TAB>link<TAB>description`: exactly
# _CHECK_FIELDS fields, the last empty when the check has no description, and
# no trailing tab. Measured from gh v2.46.0's source, not a live PR (review
# round 2's port, 2026-10-03: the cloud host has gh 2.89 and no GraphQL, so a
# real 2.46 run could not be taken there) - `pkg/cmd/pr/checks/output.go`'s
# non-TTY `addRow` adds those five fields, and go-gh v2.6.0's tsv printer
# joins a row's fields with one tab and ends it with "\n". gh prints the name
# and the description unescaped, so a tab inside either shifts every field
# after it, and no parser can tell such a row apart: any other field count
# makes the whole read unreadable, and `ship` stops. `cancel` is printed as
# `fail` by gh itself; it is mapped here too, never to a pass.
_CHECK_FIELDS = 5
_BUCKETS = {"pass": "pass", "fail": "fail", "pending": "pending", "skipping": "skipping",
            "cancel": "fail"}
_CHECK_EXITS = {0: ("pass", "skipping"), 1: ("fail",), 8: ("pending",)}
_NO_CHECKS = ("no required checks reported", "no checks reported")
GH_TIMEOUT = 120
PUSH_TIMEOUT = 300
DIRTY = "the working tree differs from HEAD - commit or discard first"


def merge_argv(number, head):
    """The one merge `ship` runs, after `gh`: a merge commit (D-028 - a squash or
    rebase rewrites the commits refresh anchors name), never `--admin`, and
    bound to `head` - the commit whose checks and receipt were read - so a
    push that lands after the last read is refused by GitHub, not merged."""
    return ["pr", "merge", str(number), "--merge", "--match-head-commit", head]


_DEQUEUE = "mutation($id:ID!){dequeuePullRequest(input:{id:$id}){clientMutationId}}"


def dequeue_argv(node_id):
    """The one GraphQL mutation `ship` ever runs: taking a PR gh queued back
    out of its merge queue, used only to undo ship's own merge call."""
    return ["api", "graphql", "-f", "query=" + _DEQUEUE, "-f", f"id={node_id}"]


def push_argv(branch):
    """The one push `ship` runs: never `--force`."""
    return ["git", "push", "-u", "origin", branch]


def _run_gh(top, args):
    """(returncode, stdout, stderr) of `gh <args>` in `top`, or None when gh
    could not run at all (gh not on PATH included). The only code here that
    runs `gh`, through the path `shutil.which` finds (L-1508)."""
    try:
        done = subprocess.run([crew_common.require_tool("gh")] + list(args), cwd=top,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=GH_TIMEOUT,
                              check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.returncode, done.stdout or "", done.stderr or ""


def _gh(top, args):
    """`gh <args>`'s stdout parsed as JSON, or None on any failure."""
    got = _run_gh(top, args)
    if got is None or got[0] != 0:
        return None
    try:
        return json.loads(got[1])
    except ValueError:
        return None


def _push(top, branch):
    """(ok, detail) of `git push -u origin <branch>`, run as the git
    `shutil.which` finds (L-1508); git not on PATH is a failed push."""
    try:
        argv = push_argv(branch)
        argv[0] = crew_common.require_tool(argv[0])
        done = subprocess.run(argv, cwd=top, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=PUSH_TIMEOUT,
                              check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    return done.returncode == 0, (done.stderr or "").strip()[-400:]


def read_pr(top, branch):
    """`{"number", "state", "url", "headRefOid", "id"}` for `branch`'s PR,
    `{"state": "NONE"}` when gh says exactly that the branch has none, or
    None when the state could not be read."""
    got = _run_gh(top, ["pr", "view", branch, "--json", "number,state,url,headRefOid,id"])
    if got is None:
        return None
    code, out, err = got
    if code != 0:
        none = f'no pull requests found for branch "{branch}"'
        return {"state": "NONE"} if err.strip() == none else None
    try:
        data = json.loads(out)
    except ValueError:
        return None
    if not isinstance(data, dict) or isinstance(data.get("number"), bool) \
            or not isinstance(data.get("number"), int) or not isinstance(data.get("state"), str):
        return None
    return data


def read_checks(top, number):
    """`[{"name", "state"}]` for PR `number`'s required checks, `[]` when gh
    reports none yet, or None when they could not be read -- gh failed, an
    exit code outside 0/1/8, a row that is not exactly _CHECK_FIELDS fields,
    anything on stderr beside the rows, or an exit code that disagrees with
    the rows (0 with a pending one, 1 with no failure, 8 with none pending).
    Names and buckets are read verbatim: `knownFailures` matches a name
    exactly, so a padded or re-cased one is a different check, and a bucket
    gh did not print exactly reads `unknown`."""
    got = _run_gh(top, ["pr", "checks", str(number), "--required"])
    if got is None or got[0] not in _CHECK_EXITS:
        return None
    code, out, err = got
    lines = [line for line in out.splitlines() if line.strip()]
    if not lines:
        return [] if code == 1 and err.strip().startswith(_NO_CHECKS) else None
    if err.strip():
        return None
    checks = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) != _CHECK_FIELDS or not parts[0].strip():
            return None
        checks.append({"name": parts[0],
                       "state": _BUCKETS.get(parts[1], "unknown")})
    states = {c["state"] for c in checks}
    if code == 0 and not states <= set(_CHECK_EXITS[0]):
        return None
    if code == 1 and "fail" not in states:
        return None
    if code == 8 and "pending" not in states:
        return None
    return checks


_QUEUE_QUERY = ("query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,"
                "name:$repo){pullRequest(number:$number){isMergeQueueEnabled isInMergeQueue}}}")


def read_merge_queue(top, number):
    """True when PR `number`'s base branch has a merge queue or the PR is in
    one, False when GitHub says exactly neither, None when it could not be
    read. A queue applies its own merge method - a squash or rebase whatever
    `--merge` asks (D-028) - and keeps merging after `ship` has stopped, so
    `ship` never hands a PR to one. gh 2.46's `pr view --json` has no queue
    field, hence the GraphQL read."""
    data = _gh(top, ["api", "graphql", "-F", "owner={owner}", "-F", "repo={repo}",
                     "-F", f"number={number}", "-f", "query=" + _QUEUE_QUERY])
    try:
        pull = data["data"]["repository"]["pullRequest"]
    except (TypeError, KeyError):
        return None
    if not isinstance(pull, dict):
        return None
    flags = [pull.get("isMergeQueueEnabled"), pull.get("isInMergeQueue")]
    if not all(isinstance(flag, bool) for flag in flags):
        return None
    return any(flags)


def _dequeue(top, pr):
    """What became of taking `pr` back out of a merge queue, as text."""
    node = pr.get("id") if isinstance(pr, dict) else None
    if not isinstance(node, str) or not node:
        return "not attempted: the PR's node id could not be read"
    got = _run_gh(top, dequeue_argv(node))
    if got is None:
        return "failed: gh could not run"
    if got[0] != 0:
        return "failed: " + ((got[2] or got[1]).strip() or f"exit {got[0]}")
    return "succeeded"


def _branch(top):
    branch = git_out(top, "rev-parse", "--abbrev-ref", "HEAD")
    return branch if branch and branch != "HEAD" else None


def _default_branch(top):
    data = _gh(top, ["repo", "view", "--json", "defaultBranchRef"])
    ref = data.get("defaultBranchRef") if isinstance(data, dict) else None
    name = ref.get("name") if isinstance(ref, dict) else None
    return name if isinstance(name, str) and name else None


def _clean_tree(top):
    """True when the working tree is HEAD (ignored files aside), False when it
    differs, None when git could not tell -- which is a stop too. A receipt
    can cover uncommitted edits that `git push` does not carry."""
    out = git_out(top, "status", "--porcelain", "--untracked-files=all")
    return None if out is None else out == ""


def _tree_stop(top):
    """The reason to stop on the working tree, or ""."""
    clean = _clean_tree(top)
    if clean is None:
        return "could not tell whether the working tree differs from HEAD (git status failed)"
    return "" if clean else DIRTY




_SHA = re.compile(r"[0-9a-f]{40}")


def _full_sha(value):
    """`value` lower-cased when it is a full 40-hex SHA, else None."""
    value = value.strip().lower() if isinstance(value, str) else ""
    return value if _SHA.fullmatch(value) else None


def merged_phase(top, branch, pr, answer, finished=None):
    """A MERGED PR closes the ticket only when it merged this checkout's HEAD
    (full SHAs). A later commit on the branch, or a head either side cannot
    read, stops: autopilot never ships a merged branch again, and "could not
    tell" never reads `closed`. `finished(reason)`, when given, answers the
    merged-at-HEAD case instead (T-0059: a non-final slice opens the next)."""
    merged = _full_sha(pr.get("headRefOid"))
    local = _full_sha(git_out(top, "rev-parse", "HEAD"))
    if merged and local and merged == local:
        why = f"PR #{pr['number']} is merged ({pr.get('url')})"
        return finished(why) if finished else answer("closed", True, why)
    if merged and local:
        return answer("ship", True, f"{branch} has commits after PR #{pr['number']} merged "
                      f"(merged head {merged}, HEAD {local}) - ship them on a new branch "
                      "and PR; autopilot never opens a second PR on a merged branch")
    return answer("ship", True, f"PR #{pr['number']} for {branch} is merged, but its "
                  f"merged head ({merged or 'unreadable'}) or this checkout's HEAD "
                  f"({local or 'unreadable'}) could not be read, so whether commits after "
                  "the merge remain cannot be told - a human looks")
