"""T-0059: a plan's `## PR slices` ship as ordered slice PRs, split out of
`crew_autopilot.py` (pylint's module-length limit). `crew_autopilot` reads
`context` in `_phase` and `ship`, appends `WAITING`, and dispatches the
`slice`, `slice-done` and `next-slice` actions here.

    python3 crew_autopilot.py slice|slice-done|next-slice --root . --ticket <id>

A plan with a `## PR slices` section (`crew_split.parse_slices`) runs one
slice at a time: implement, review, done and ship, as its own PR. Where the
run stands is `<git-common-dir>/crew/tickets/<id>/slices.json`:

    {"current": n, "done": [k, ...], "shipped": [{"slice", "pr", "branch",
     "base", "merge_sha"}]}

Absent means slice 1 with nothing done; anything else unreadable or out of
shape is a stop, never slice 1. `ship` opens one PR per slice: `gh pr create
--head <slice branch> --base <slice_base> --title "<id> slice n/m: <name>"
--body ...` instead of `--fill`, refuses (nothing pushed) unless slice n-1
shipped and is merged, or open under `ship: pr`, and slice n >= 2 ships only
from `<slice 1's branch>-s<n>`. The merge is still `crew_ship.merge_argv`
only. The PR (and merge commit) is recorded in slices.json. `slice-done`
records a non-final slice done after `/crew:done` set its header
`in-progress`; `next-slice` creates the next branch off `slice_base` and
opens its review budget through `review_ledger.open_slice`, refusing with
nothing written until that harness function lands (T-0087).

Writes: slices.json (`ship` for a slice, `slice-done`, `next-slice`) and, for
`next-slice`, the new slice branch. `crew_autopilot` is imported lazily
(`_ap`), so importing this module never imports it back.
"""
import importlib
import json
import os
import sys

import crew_ship
import crew_ticket
import review_ledger
from crew_common import git_out, read_text

SLICES_FILE = "slices.json"
# Phases `status` reports as waiting on the owner (crew_autopilot.WAITING).
WAITING = ("slices", "next-slice")
ACTIONS = ("slice", "slice-done", "next-slice")


def _ap():
    """crew_autopilot, imported when first needed (it imports this module)."""
    return importlib.import_module("crew_autopilot")


def slices_path(root, ticket):
    state = crew_ticket.state_dir(root)
    if not state:
        raise crew_ticket.TicketError(f"{root} is not a git repository; there is nowhere "
                                      "to keep the slice state")
    return os.path.join(state, "tickets", crew_ticket.check_ticket(ticket), SLICES_FILE)


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _slice_state(top, ticket, count):
    """The slice state for a plan of `count` slices, or (None, why)."""
    path = slices_path(top, ticket)
    if not os.path.lexists(path):
        return {"current": 1, "done": [], "shipped": []}, ""
    data = _ap()._read_json(path)  # pylint: disable=protected-access
    shipped = data.get("shipped") if isinstance(data, dict) else None
    done = data.get("done") if isinstance(data, dict) else None
    current = data.get("current") if isinstance(data, dict) else None
    lists = (isinstance(done, list) and all(is_int(k) for k in done)
             and isinstance(shipped, list)
             and all(isinstance(e, dict) and is_int(e.get("slice")) for e in shipped))
    if not lists or not is_int(current) or not 1 <= current <= count:
        return None, (f"{_ap()._rel(top, path)} is unreadable or out of shape "  # pylint: disable=protected-access
                      f"(current 1-{count}, done and shipped lists): cannot tell which "
                      "slice is current - a human looks")
    return data, ""


def _write_slice_state(top, ticket, data):
    """Temp file then os.replace: a crash leaves the old state or the new."""
    path = slices_path(top, ticket)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(data, indent=2) + "\n"
    temp = f"{path}.{os.getpid()}.tmp"
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temp, path)


def context(top, ticket, plan_text=None):
    """None for a plan with no `## PR slices`; else {"slices", "state", "piece",
    "m", "error"}: `piece` is the current slice, `error` a reason to stop."""
    import crew_split  # pylint: disable=import-outside-toplevel
    if plan_text is None:
        plan_text = read_text(os.path.join(crew_ticket.ticket_dir(top, ticket), "plan.md"))
    slices, problems = crew_split.parse_slices(plan_text or "")
    if not slices and not problems:
        return None
    if problems:
        return {"error": "PR slices: " + "; ".join(problems), "slices": slices}
    state, why = _slice_state(top, ticket, len(slices))
    if state is None:
        return {"error": why, "slices": slices}
    return {"error": "", "slices": slices, "state": state, "m": len(slices),
            "piece": slices[state["current"] - 1]}


def steps_text(steps):
    return (f"{steps[0]}-{steps[-1]}" if len(steps) > 1 else str(steps[0])) if steps else "none"


def label(ctx):
    piece = ctx["piece"]
    return f"slice {piece['n']} of {ctx['m']} ({piece['name']})"


def with_slice(ctx, found):
    """`found` carrying the current slice's number on a sliced ticket."""
    return dict(found, slice=ctx["piece"]["n"]) if ctx and not ctx.get("error") else found


def slice_base(n, slices, merged, branches, default):
    """The branch slice `n`'s PR is based on: `default` for slice 1, for a
    `Base: main` slice, and once every earlier slice is merged; otherwise the
    branch of the latest unmerged slice down its `Base: slice <k>` chain
    (stacked). `merged` is the set of merged slice numbers, `branches` maps
    a slice number to its branch."""
    if n == 1 or all(k in merged for k in range(1, n)):
        return default
    by_n = {s["n"]: s for s in slices}
    base = by_n[n]["base"]
    while base != "main" and base is not None:
        if base not in merged:
            return branches[base]
        base = by_n[base]["base"]
    return default


def slice_branches(ctx):
    """{slice: branch}: slice 1's is the branch it shipped from, slice n's
    `<that>-s<n>`; empty when slice 1 has not shipped."""
    first = next((e.get("branch") for e in ctx["state"]["shipped"] if e.get("slice") == 1),
                 None)
    if not isinstance(first, str) or not first:
        return {}
    return {s["n"]: first if s["n"] == 1 else f"{first}-s{s['n']}" for s in ctx["slices"]}


def _shipped_entry(ctx, n):
    return next((e for e in ctx["state"]["shipped"] if e.get("slice") == n), None)


def merged_slices(top, ctx, upto):
    """(set of merged slice numbers below `upto`, {slice: PR state}), or
    (None, why) when a shipped slice's state, merge destination or chain
    cannot be read, or it merged anywhere its plan does not allow. A recorded
    `merge_sha` goes through the same verified-base decision
    (`_verified_merged`) as a PR read as MERGED: never trusted alone."""
    merged, states = set(), {}
    for k in range(1, upto):
        entry = _shipped_entry(ctx, k)
        if entry is None:
            continue
        done, why, _allowed = _verified_merged(top, ctx, k, 0)
        if done is None:
            return None, why
        if done:
            merged.add(k)
            states[k] = "MERGED"
            continue
        pr = crew_ship.read_pr(top, entry.get("branch") or "")
        if pr is None:
            return None, (f"could not read slice {k}'s PR state ({entry.get('branch')}) - a "
                          "human looks")
        states[k] = pr["state"]
    return merged, states


def _allowed_bases(top, ctx, k, depth=0):
    """`(allowed, why)`: the ONE set of branches slice `k`'s PR may have merged
    into, from its declared base and the verified chain under it, or
    `(None, why)` -- a stop -- when anything it rests on is unknown or
    malformed. `Base: main` is the default branch alone. `Base: slice <j>` is
    slice j's branch, plus whatever slice j's own PR could merge into once
    slice j is verified merged INTO one of those (GitHub retargets a stacked
    PR when its base merges). A recorded base is never trusted on its own."""
    by_n = {s["n"]: s for s in ctx["slices"]}
    entry = _shipped_entry(ctx, k) or {}
    recorded = entry.get("base")
    if recorded is not None and not (isinstance(recorded, str) and recorded):
        return None, (f"slices.json records slice {k}'s base as {recorded!r}, not a branch "
                      "name - a human looks")
    default = crew_ship._default_branch(top)  # pylint: disable=protected-access
    if not default:
        return None, "could not read the default branch"
    base = by_n[k]["base"]
    if base == "main":
        return {default}, ""
    if not is_int(base) or base not in by_n or base >= k or depth > len(by_n):
        return None, f"slice {k}'s Base: is not an earlier slice - a human looks"
    below = (slice_branches(ctx) or {}).get(base)
    if not below:
        return None, f"slice {base}'s branch is not recorded, so slice {k}'s base is unknown"
    merged, why, under = _verified_merged(top, ctx, base, depth + 1)
    if merged is None:
        return None, why
    return ({below} | under) if merged else {below}, ""


def _verified_merged(top, ctx, j, depth):
    """`(merged, why, allowed_j)`: True only when slice j's PR merged INTO a
    base its own chain allows; False when it has not shipped or merged yet;
    None (a stop, `why` set) when its state, its destination or its chain
    cannot be read, or it merged anywhere else."""
    entry = _shipped_entry(ctx, j)
    if entry is None:
        return False, "", set()
    branch = entry.get("branch")
    if not isinstance(branch, str) or not branch:
        return None, f"slices.json records no branch for slice {j} - a human looks", set()
    if not crew_ship._full_sha(entry.get("merge_sha")):  # pylint: disable=protected-access
        pr = crew_ship.read_pr(top, branch)
        if pr is None:
            return None, f"could not read slice {j}'s PR state ({branch}) - a human looks", set()
        if pr.get("state") != "MERGED":
            return False, "", set()
    allowed, why = _allowed_bases(top, ctx, j, depth)
    if allowed is None:
        return None, why, set()
    view = crew_ship._gh(top, ["pr", "view", branch, "--json", "baseRefName"])  # pylint: disable=protected-access
    found = view.get("baseRefName") if isinstance(view, dict) else None
    if not isinstance(found, str) or not found:
        return None, f"could not read where slice {j}'s PR ({branch}) was merged", set()
    if found not in allowed:
        return None, (f"slice {j}'s PR ({branch}) merged into {found}, not a base the plan "
                      f"names ({', '.join(sorted(allowed))}) - the chain did not reach its "
                      "base; a person looks"), set()
    return True, "", allowed


def _merged_into_stop(top, ctx, k, branch):
    """The reason slice `k`'s merged PR (on `branch`) did not reach a base the
    plan names, or ""; anything unknown or malformed is a stop."""
    allowed, why = _allowed_bases(top, ctx, k)
    if allowed is None:
        return why
    view = crew_ship._gh(top, ["pr", "view", branch, "--json", "baseRefName"])  # pylint: disable=protected-access
    found = view.get("baseRefName") if isinstance(view, dict) else None
    if not isinstance(found, str) or not found:
        return f"could not read where {branch}'s merged PR was merged"
    if found not in allowed:
        return (f"{branch}'s PR merged into {found}, not a base the plan names "
                f"({', '.join(sorted(allowed))}) - slice {k} did not reach its base; a "
                "person looks")
    return ""


def order_stop(top, ctx, branch, policy):
    """The reason slice n may not ship from `branch` yet, or "": slice n-1 must
    have shipped and be merged (or open, under `ship: pr`), and slice n >= 2
    ships only from `<slice 1's branch>-s<n>`."""
    n = ctx["piece"]["n"]
    if n == 1:
        return ""
    if _shipped_entry(ctx, n - 1) is None:
        return (f"slice {n - 1} has not shipped: slice {n} never ships before it - run "
                f"slice {n - 1} first")
    merged, states = merged_slices(top, ctx, n)
    if merged is None:
        return states
    prior = states.get(n - 1)
    if prior != "MERGED" and not (policy == "pr" and prior == "OPEN"):
        return (f"slice {n - 1}'s PR is {prior}, not merged" + (
            "" if policy == "pr" else " (autopilot.ship is merge, so it must merge first)")
            + f": slice {n} never ships before it")
    return branch_stop(ctx, branch)


def branch_stop(ctx, branch):
    """The reason `branch` is not the current slice's, or "". Slice 1 ships
    from the ticket's branch; slice n >= 2 only from `<slice 1's>-s<n>`."""
    n = ctx["piece"]["n"]
    expected = slice_branches(ctx).get(n) if n > 1 else branch
    if branch != expected:
        return (f"slice {n} ships from {expected or '(unknown: slice 1 recorded no branch)'}, "
                f"not {branch} - run crew_autopilot.py next-slice to open it")
    return ""


def record_shipped(top, ticket, ctx, branch, base):
    """Record slice n's PR (and merge commit, when gh reports one)."""
    n = ctx["piece"]["n"]
    pr = crew_ship.read_pr(top, branch) or {}
    view = crew_ship._gh(top, ["pr", "view", branch, "--json", "mergeCommit"])  # pylint: disable=protected-access
    commit = view.get("mergeCommit") if isinstance(view, dict) else None
    sha = crew_ship._full_sha(commit.get("oid")) if isinstance(commit, dict) else None  # pylint: disable=protected-access
    state = dict(ctx["state"])
    state["shipped"] = [e for e in state["shipped"] if e.get("slice") != n] + [{
        "slice": n, "pr": pr.get("number"), "branch": branch, "base": base,
        "merge_sha": sha if pr.get("state") == "MERGED" else None}]
    _write_slice_state(top, ticket, state)


def create_argv(ticket, ctx, branch, base):
    """`gh pr create` for one slice: its base, a `<id> slice n/m:` title and
    a body naming the steps and the PR it stacks on."""
    piece = ctx["piece"]
    below = next((e for e in ctx["state"]["shipped"] if e.get("branch") == base), None)
    body = (f"{ticket} slice {piece['n']} of {ctx['m']} ({piece['name']}): plan steps "
            f"{steps_text(piece['steps'])}."
            + (f" Stacked on #{below.get('pr')} ({base}): merge that first." if below else ""))
    return ["pr", "create", "--head", branch, "--base", base, "--title",
            f"{ticket} slice {piece['n']}/{ctx['m']}: {piece['name']}", "--body", body]


def ship_slice(top, ticket, ctx, branch, default, ship_from):
    """`ship` for a sliced ticket: the order and branch checks, the slice's
    base and PR, then `ship_from(create_argv)`; a slice that opened or merged
    is recorded. Nothing is pushed when a check refuses."""
    ap = _ap()
    if ctx["error"]:
        return ap._ship_result(ticket, "stop", True, ctx["error"])  # pylint: disable=protected-access
    order = order_stop(top, ctx, branch, ap.settings(top)["ship"])
    merged, _ = merged_slices(top, ctx, ctx["piece"]["n"])
    branches = slice_branches(ctx) or {1: branch}
    if order or merged is None:
        return ap._ship_result(ticket, "stop", True, (  # pylint: disable=protected-access
            order or "could not read an earlier slice's PR state") + " - nothing pushed")
    base = slice_base(ctx["piece"]["n"], ctx["slices"], merged, branches, default)
    wrong = pr_base_stop(top, branch, base)
    if wrong:
        return ap._ship_result(ticket, "stop", True, wrong + " - nothing pushed")  # pylint: disable=protected-access
    result = ship_from(create_argv(ticket, ctx, branch, base), base)
    # Any PR this run left behind is recorded -- one created before a stop
    # (checks failed or timed out, or the follow-up read failed) included -- so
    # a person merging it later still leaves the slice's branch on record.
    after = crew_ship.read_pr(top, branch) if not result.get("pr") else None
    if result["action"] in ("open-pr", "merged") or result.get("pr") or (
            isinstance(after, dict) and after.get("state") in ("OPEN", "MERGED")):
        record_shipped(top, ticket, ctx, branch, base)
    return result


def expected_base_stop(top, ctx, branch):
    """`next`'s check of an existing slice PR's base (T-0059): the reason it
    is not the plan's, or "". Could not read is a stop too."""
    if ctx.get("error"):
        return ctx["error"]
    default = crew_ship._default_branch(top)  # pylint: disable=protected-access
    merged, why = merged_slices(top, ctx, ctx["piece"]["n"])
    if not default or merged is None:
        return why if merged is None else "could not read the default branch"
    base = slice_base(ctx["piece"]["n"], ctx["slices"], merged,
                      slice_branches(ctx) or {1: branch}, default)
    return pr_base_stop(top, branch, base)


def merged_base_stop(top, ctx, branch):
    """A merged slice PR counts as shipped only when it merged into a base the
    plan names for that slice (`_allowed_bases`). The reason it did not, or
    "" ; could not read is a stop too."""
    if ctx.get("error"):
        return ctx["error"]
    return _merged_into_stop(top, ctx, ctx["piece"]["n"], branch)


def pr_base_stop(top, branch, base):
    """The reason an existing PR for `branch` may not ship, or "": its base
    must be the plan's (`slice_base`). A retargeted or hand-opened PR would
    merge into some other branch. Could not read is a stop too."""
    pr = crew_ship.read_pr(top, branch)
    if pr is None:
        return f"could not read the PR state for {branch}"
    if pr.get("state") == "NONE":
        return ""
    view = crew_ship._gh(top, ["pr", "view", branch, "--json", "baseRefName"])  # pylint: disable=protected-access
    found = view.get("baseRefName") if isinstance(view, dict) else None
    if not isinstance(found, str) or not found:
        return f"could not read the base branch of {branch}'s PR #{pr.get('number')}"
    if found != base:
        return (f"{branch}'s PR #{pr.get('number')} is based on {found}, not {base} (the "
                "plan's base for this slice) - a person retargets it")
    return ""


def slice_command(ticket):
    return f"crew_autopilot.py next-slice --ticket {ticket}"


def _result(ok, reason):
    return {"ok": ok, "reason": reason}


def slice_done(root, ticket):
    """`/crew:done` on a non-final slice: records slice n done, so `next`
    names its ship. Refuses an unsliced plan, the last slice (that one sets
    `status: done`), a header that is not `in-progress`, and a receipt that
    no longer stands. Writes nothing on refusal."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    crew_ticket.check_ticket(ticket)
    ctx = context(top, ticket)
    if ctx is None:
        return _result(False, "no ## PR slices in plan.md: /crew:done sets "
                       "`status: done` and closes the ticket")
    if ctx["error"]:
        return _result(False, ctx["error"])
    n, m = ctx["piece"]["n"], ctx["m"]
    if n >= m:
        return _result(False, f"slice {n} is the last slice: /crew:done sets "
                       "`status: done` and closes the ticket")
    header = _ap()._header_status(read_text(  # pylint: disable=protected-access
        os.path.join(crew_ticket.ticket_dir(top, ticket), "spec.md")) or "")
    if header != "in-progress":
        return _result(False, f"spec.md's header is `status: {header}`: a non-final "
                       "slice sets it to `in-progress` (which keeps the approval) "
                       "before this")
    ok, message = review_ledger.check_receipt(top, ticket)
    if not ok:
        return _result(False, f"the review receipt does not stand ({message})")
    state = dict(ctx["state"])
    state["done"] = sorted(set(state["done"]) | {n})
    _write_slice_state(top, ticket, state)
    return _result(True, f"slice {n} of {m} done; the ticket stays open at "
                   f"`in-progress` and slice {n} ships next")


def next_slice(root, ticket):
    """Open slice n+1 once slice n shipped: its branch off `slice_base`, then
    a fresh review budget (`review_ledger.open_slice`), then the state. A
    branch made before a refusing `open_slice` is removed again."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    phase = _ap().next_phase(top, ticket)
    if phase["phase"] != "next-slice" or phase["stop"]:
        return _result(False, f"next names {phase['phase']}"
                       f"{' (stop)' if phase['stop'] else ''}, not next-slice: "
                       f"{phase['reason']}")
    opener = getattr(review_ledger, "open_slice", None)
    if not callable(opener):
        return _result(False, "review_ledger.open_slice is not landed (a harness "
                       "change, T-0087): the next slice would be reviewed on this "
                       "slice's spent budget - nothing written, a human looks")
    ctx = context(top, ticket)
    n = ctx["piece"]["n"] + 1
    tree = crew_ship._tree_stop(top)  # pylint: disable=protected-access
    default = crew_ship._default_branch(top)  # pylint: disable=protected-access
    merged, states = merged_slices(top, ctx, n)
    branches = slice_branches(ctx)
    if tree or not default or merged is None or not branches:
        return _result(False, tree or (states if merged is None else
                                       "could not read the default branch or slice "
                                       "1's branch") + " - nothing written")
    base = slice_base(n, ctx["slices"], merged, branches, default)
    start = base
    if base == default:
        if git_out(top, "fetch", "-q", "origin", default) is None:
            return _result(False, f"git fetch origin {default} failed - nothing written")
        start = f"origin/{default}"
    previous, new = crew_ship._branch(top), branches[n]  # pylint: disable=protected-access
    if git_out(top, "checkout", "-q", "-b", new, start) is None:
        return _result(False, f"git checkout -b {new} {start} failed - nothing written")
    try:
        opener(top, ticket, n)  # pylint: disable=not-callable
    except Exception as exc:  # pylint: disable=broad-except
        git_out(top, "checkout", "-q", previous or "-")
        git_out(top, "branch", "-q", "-D", new)
        return _result(False, f"review_ledger.open_slice refused slice {n}: {exc} - "
                       f"{new} removed, nothing else written")
    state = dict(ctx["state"])
    state["current"] = n
    _write_slice_state(top, ticket, state)
    return _result(True, f"slice {n} of {ctx['m']} opened on {new} (base {base}) with "
                   "a fresh review budget")


def slice_text(top, ticket):
    """`slice` CLI: one line for /crew:implement and /crew:done."""
    ctx = context(top, ticket)
    if ctx is None:
        return 0, "slice=none"
    if ctx["error"]:
        return 1, _ap()._one_line(f"slice=unknown reason={ctx['error']}")  # pylint: disable=protected-access
    piece = ctx["piece"]
    return 0, (f"slice={piece['n']} of={ctx['m']} "
               f"final={'yes' if piece['n'] == ctx['m'] else 'no'} "
               f"steps={steps_text(piece['steps'])} name={piece['name']}")


def add_parsers(sub):
    """`slice`, `slice-done` and `next-slice` on crew_autopilot.py's subparsers."""
    for name in ACTIONS:
        action = sub.add_parser(name)
        action.add_argument("--root", default=".")
        action.add_argument("--ticket", required=True)


def main(args):
    """`slice`, `slice-done` and `next-slice`: exit 0 ok, 1 refused or could
    not tell."""
    ap = _ap()
    try:
        if args.action == "slice":
            code, text = slice_text(crew_ticket.toplevel(args.root) or
                                    os.path.abspath(args.root), args.ticket)
        else:
            result = (slice_done if args.action == "slice-done" else next_slice)(
                args.root, args.ticket)
            code, text = (0 if result["ok"] else 1), ap._one_line(  # pylint: disable=protected-access
                ap._line(ok=int(result["ok"]), reason=result["reason"]))  # pylint: disable=protected-access
    except Exception as exc:  # pylint: disable=broad-except
        # A crash cannot tell where the slices stand: a refusal, never silence.
        code, text = 1, ap._one_line(ap._line(ok=0, reason=ap._failure(exc)))  # pylint: disable=protected-access
    sys.stdout.write(text + "\n")
    return code
