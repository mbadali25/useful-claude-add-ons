"""T-0012: `/crew:autopilot goal` -- the goal file, the printed /goal line and
the split approval, split out of `crew_autopilot.py` (pylint's module-length
limit). `crew_autopilot.py goal-propose`, `goal-approve` and `goal-run`
dispatch here; route's goal constant (`GOAL_ROUTE_FIRST`) stays in
`crew_autopilot`, which imports this module only when a goal action runs.

Minting the approved split, the picker, `goal-run` (`mode: backlog` and the
caps), `--goal` resume and the per-ticket approval are L-0541's, in
crew_autopilot_backlog.py. The hook that records the owner's
`/crew:approve goal:<slug>` is a review-harness change
(scripts/check-tooling-pr.py) that lands on its own; until it does,
`split_approved` only reads that receipt. This module writes only the
working file `.work/autopilot/<slug>.json`, never a receipt.

    python3 crew_autopilot.py goal-propose --root . --proposal-file <f> [--json]
    python3 crew_autopilot.py goal-approve --root . --goal <slug> [--ticket <id>] [--json]
    python3 crew_autopilot.py goal-run --root . --goal <slug> [--session <id>]
                                       [--transcript <path>] [--json]

Two writers of one working file, `.work/autopilot/<slug>.json` (schema 1),
never of a receipt. `goal-propose` reads a proposal staged under
`.work/autopilot/` (`goal`, a one-line `done_condition`, `findings`, `tickets`
with `title`, `risk` and `depends_on`, earlier indexes only), writes the goal
file and prints `goal_status=printed` with the `/goal <condition>` line for
the owner to paste: Claude Code's `/goal` is the owner's to type, and
autopilot cannot observe it, so it never reports it set. `goal-approve`
answers the split: the owner's receipt under
`<git-common-dir>/crew/goals/<slug>/approval.json` matching `goal_digest`, at
any setting, or `split_policy` (T-0010's rules, the goal risk the highest
ticket risk) re-asked on every call; a yes is noted in the goal file and the
note grants nothing, and then mints the proposed tickets
(`crew_autopilot_backlog.mint_goal`). With `--ticket <id>` it is the
per-ticket approval of one minted ticket instead. Recording the owner's
receipt is approval_hook.py's.
"""
import hashlib
import importlib
import json
import os
import re
import stat
import sys

import crew_autopilot as ap
import crew_ticket
from crew_common import read_text

GOAL_SCHEMA = 1
GOAL_SLUG_MAX = 40
GOAL_LINE_MAX = 300
GOAL_MAX_TICKETS = 20
GOAL_TEXT_MAX = 2000
GOAL_FILE_MAX = 256 * 1024
GOAL_STOP_CLAUSE = "- or /crew:autopilot has stopped naming a command only the owner types"
GOAL_STATUS = "printed"
GOAL_UNSEEN = ("autopilot cannot see Claude Code's /goal state - paste the line if you "
               "want Claude Code to keep going")
OWNER_SPLIT = "/crew:approve goal:{slug}"
OWNER_HOOK_PENDING = ("approval_hook.py records it once its goal: token lands (a review-harness "
                      "change, landing separately); until then the hook refuses it")
# The entry point T-0013 would expose to type an allowlisted `/goal` line. As
# specced it types only `decide`'s prompt, so the probe finds nothing today.
GOAL_TYPER = ("crew_resume", "type_goal_line")
TYPER_ABSENT = (f"no /goal typing entry point ({GOAL_TYPER[0]}.{GOAL_TYPER[1]}, T-0013's, "
                "is not there)")
RISK_ORDER = ("low", "med", "high")


class GoalError(ValueError):
    """A goal proposal or goal file that is refused or cannot be read."""


def _goal_slug_ok(slug):
    """T-0006's grammar, the one a `resume: /crew:autopilot --goal` line takes."""
    resume = importlib.import_module("crew_resume")
    pattern = resume._GOAL_SLUG_RE  # pylint: disable=protected-access
    return isinstance(slug, str) and bool(pattern.match(slug)) and "\n" not in slug


def _goal_dir(top):
    return os.path.join(top, *crew_ticket.STAGING.split("/"))


def goal_path(root, slug):
    """`.work/autopilot/<slug>.json`; GoalError for a slug outside T-0006's grammar."""
    if not _goal_slug_ok(slug):
        raise GoalError(f"goal slug {slug!r} is not [a-z0-9][a-z0-9-]{{0,63}}")
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    return os.path.join(_goal_dir(top), f"{slug}.json")


def goal_receipt_path(root, slug):
    """`<git-common-dir>/crew/goals/<slug>/approval.json`: where the owner's
    split approval is recorded (by approval_hook.py, never by this module)."""
    if not _goal_slug_ok(slug):
        raise GoalError(f"goal slug {slug!r} is not [a-z0-9][a-z0-9-]{{0,63}}")
    state = crew_ticket.state_dir(root)
    if not state:
        raise GoalError(f"{root} is not a git repository; there is no receipt to read")
    return os.path.join(state, "goals", slug, "approval.json")


def slugify(root, goal):
    """Lower-case, every run of characters outside `[a-z0-9]` one `-`, trimmed
    to GOAL_SLUG_MAX, `goal` when nothing is left; `-2`, `-3`... past a goal
    file that exists. Always inside T-0006's slug grammar."""
    base = re.sub(r"[^a-z0-9]+", "-", (goal if isinstance(goal, str) else "").lower())
    base = base.strip("-")[:GOAL_SLUG_MAX].strip("-") or "goal"
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    folder = _goal_dir(top)
    slug, n = base, 1
    while os.path.lexists(os.path.join(folder, f"{slug}.json")):
        n += 1
        slug = f"{base}-{n}"
    if not _goal_slug_ok(slug):
        raise GoalError(f"could not derive a goal slug from {goal!r}")
    return slug


def _clean_line(text):
    """One line: every non-printable character (control, line and paragraph
    separators, format) a space, whitespace runs one space, stripped."""
    return " ".join("".join(c if c.isprintable() else " " for c in text).split())


def _condition(proposal):
    """The done-condition as `/goal` will carry it, or GoalError: one line,
    never starting with `/` (so `/goal /goal clear` cannot be rendered)."""
    cond = proposal.get("done_condition") if isinstance(proposal, dict) else None
    cond = _clean_line(cond) if isinstance(cond, str) else ""
    while cond[:1] in ("/", " ") and cond:
        cond = cond[1:]
    if not cond:
        raise GoalError("the proposal has no done_condition (one sentence that says when the "
                        "goal is met); nothing was written")
    return cond


def goal_line(goal):
    """`/goal <done-condition> <GOAL_STOP_CLAUSE>`, one line, at most
    GOAL_LINE_MAX characters: the condition is cut, never the clause."""
    cond = _condition(goal.get("proposal") if isinstance(goal, dict) else None)
    room = GOAL_LINE_MAX - len("/goal  ") - len(GOAL_STOP_CLAUSE)
    return f"/goal {cond[:room].rstrip()} {GOAL_STOP_CLAUSE}"


def goal_risk(tickets):
    """`{"risk", "known"}`: the highest proposed risk. A risk that is not
    exactly low|med|high, or no tickets at all, reads `high` with `known`
    False -- never `low`."""
    risks = [t.get("risk") if isinstance(t, dict) else None for t in tickets or []]
    if not risks or any(r not in RISK_ORDER for r in risks):
        return {"risk": "high", "known": False}
    return {"risk": max(risks, key=RISK_ORDER.index), "known": True}


def _check_tickets(tickets):
    """The proposed tickets as `[{"title", "risk", "depends_on", "id"}]`, or
    GoalError. `depends_on` holds indexes of earlier tickets: an unknown one,
    a cycle, or one later in the list (not dependency order) is refused. A
    title `crew_ticket.mint` would refuse is refused now."""
    if not isinstance(tickets, list) or not tickets:
        raise GoalError("the proposal has no tickets (a non-empty list)")
    if len(tickets) > GOAL_MAX_TICKETS:
        raise GoalError(f"the proposal has {len(tickets)} tickets, over {GOAL_MAX_TICKETS}")
    out = []
    for n, ticket in enumerate(tickets, 1):
        if not isinstance(ticket, dict):
            raise GoalError(f"ticket {n} is not an object")
        problem = crew_ticket._mint_title_problem(  # pylint: disable=protected-access
            ticket.get("title"))
        if problem:
            raise GoalError(f"ticket {n}: {problem}")
        if not isinstance(ticket.get("risk"), str):
            raise GoalError(f"ticket {n}: risk must be low|med|high")
        deps = ticket.get("depends_on")
        if not isinstance(deps, list) or any(
                isinstance(d, bool) or not isinstance(d, int) or not 0 <= d < len(tickets)
                for d in deps) or len(set(deps)) != len(deps):
            raise GoalError(f"ticket {n}: depends_on must list other tickets' indexes "
                            f"(0..{len(tickets) - 1}), each once; it is {deps!r}")
        out.append({"title": ticket["title"], "risk": ticket["risk"],
                    "depends_on": list(deps), "id": None})
    state = {}

    def visit(i):
        state[i] = "open"
        for dep in out[i]["depends_on"]:
            if state.get(dep) == "open" or (dep not in state and visit(dep)):
                return True
        state[i] = "done"
        return False
    if any(i not in state and visit(i) for i in range(len(out))):
        raise GoalError("the tickets' depends_on form a cycle")
    late = [n for n, t in enumerate(out) if any(d >= n for d in t["depends_on"])]
    if late:
        raise GoalError(f"ticket {late[0] + 1} depends on a later one: list the tickets in "
                        "dependency order")
    return out


def _check_proposal(goal, proposal):
    if not isinstance(goal, str) or not goal.strip():
        raise GoalError("the proposal has no goal text")
    if len(goal) > GOAL_TEXT_MAX:
        raise GoalError(f"the goal is {len(goal)} characters, over {GOAL_TEXT_MAX}")
    if not isinstance(proposal, dict):
        raise GoalError("the proposal is not an object")
    _condition(proposal)
    findings = proposal.get("findings")
    if isinstance(findings, str):
        findings = [findings]
    if not isinstance(findings, list) or not all(isinstance(f, str) for f in findings):
        raise GoalError("findings must be text or a list of text")
    return {"done_condition": proposal["done_condition"], "findings": findings}


def goal_digest(goal):
    """sha256 over the canonical JSON of what the split approval approves:
    the goal text, the proposal, and each ticket's title, risk and
    depends_on. A minted id is left out, so minting does not void it."""
    body = {"goal": goal["goal"], "proposal": goal["proposal"],
            "tickets": [{k: t[k] for k in ("title", "risk", "depends_on")}
                        for t in goal["tickets"]]}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def _write_json_atomic(path, data):
    """The whole text first, then a temp file beside `path`, then os.replace."""
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.lexists(tmp):
            os.remove(tmp)


def write_goal(root, goal, proposal, tickets):
    """Write a new goal file, schema 1: `{"slug", "path", "goal"}`. Refused
    (GoalError, nothing written) for no goal text, no done_condition, or
    tickets `_check_tickets` refuses. The slug is claimed with an exclusive
    create, then the full text replaces the claim from a temp file."""
    proposal = _check_proposal(goal, proposal)
    checked = _check_tickets(tickets)
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    os.makedirs(_goal_dir(top), exist_ok=True)
    for _ in range(GOAL_MAX_TICKETS * 5):
        slug = slugify(top, goal)
        path = goal_path(top, slug)
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue
        data = {"schema": GOAL_SCHEMA, "goal": goal, "slug": slug, "proposal": proposal,
                "tickets": checked, "approval": None, "caps": None, "runs": []}
        try:
            _write_json_atomic(path, data)
        except BaseException:
            os.remove(path)
            raise
        return {"slug": slug, "path": path, "goal": data}
    raise GoalError("no free goal slug; nothing was written")


def read_goal(root, slug):
    """The goal file as a dict, or GoalError: a bad slug, a file that is not
    there or cannot be read, not schema 1, or a proposal or tickets that would
    not be written today."""
    path = goal_path(root, slug)
    text = read_text(path)
    if text is None:
        raise GoalError(f"the goal file .work/autopilot/{slug}.json is not there or could not "
                        "be read")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise GoalError(f"the goal file .work/autopilot/{slug}.json is not JSON") from exc
    if not isinstance(data, dict) or data.get("schema") != GOAL_SCHEMA \
            or data.get("slug") != slug:
        raise GoalError(f"the goal file .work/autopilot/{slug}.json is not a schema "
                        f"{GOAL_SCHEMA} goal for {slug}")
    _check_proposal(data.get("goal"), data.get("proposal"))
    ids = [t.get("id") if isinstance(t, dict) else None for t in data.get("tickets") or []]
    _check_tickets(data.get("tickets"))
    data["tickets"] = [dict(t, id=i) for t, i in zip(data["tickets"], ids)]
    return data


def _read_proposal_file(top, proposal_file):
    """The staged proposal's JSON object. Like `crew_ticket.assign`'s staging
    file: under `.work/autopilot/` once symlinks are resolved, and regular."""
    staging = os.path.realpath(_goal_dir(top))
    path = proposal_file if os.path.isabs(proposal_file) else os.path.join(top, proposal_file)
    real = os.path.realpath(path)
    if not real.startswith(staging + os.sep):
        raise GoalError(f"{proposal_file} is not under {crew_ticket.STAGING}/ (it resolves to "
                        f"{real}); nothing was written")
    try:
        if os.path.getsize(real) > GOAL_FILE_MAX:
            raise GoalError(f"{proposal_file} is over {GOAL_FILE_MAX} bytes")
        text = crew_ticket._read_regular(real)  # pylint: disable=protected-access
        data = json.loads(text)
    except crew_ticket.TicketError as exc:
        raise GoalError(f"{exc}; nothing was written") from exc
    except (OSError, ValueError) as exc:
        raise GoalError(f"{proposal_file} could not be read as JSON ({type(exc).__name__}: "
                        f"{exc}); nothing was written") from exc
    if not isinstance(data, dict):
        raise GoalError(f"{proposal_file} is not a JSON object; nothing was written")
    return data


def _resume_armed(top):
    got = importlib.import_module("crew_resume").settings(top)
    return bool(got.get("armed") is True), got.get("reason") or ""


def _typing_sender(top):
    autocycle = importlib.import_module("crew_autocycle")
    got = autocycle.resolve_method(autocycle.settings(top))
    if got.get("ok") and got.get("method") not in (None, "notify", "none"):
        return True, ""
    return False, got.get("reason") or f"method {got.get('method')} types nothing"


def _goal_typer():
    try:
        module = importlib.import_module(GOAL_TYPER[0])
    except ImportError:
        return None
    found = getattr(module, GOAL_TYPER[1], None)
    return found if callable(found) else None


_TYPER_MISSING = {"resume": "resume not armed: {why}", "sender": "no typing sender: {why}",
                  "typer": "{why}"}


def typer_offer(root):
    """`{"offer", "missing"}`: T-0013's typer is offered for the `/goal` line
    only when T-0006's `resume.auto` is armed, `crew_autocycle.resolve_method`
    names a sender, and T-0013 exposes GOAL_TYPER. Each one missing is named
    once; a probe that raises is could-not-tell, never armed."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    missing = []
    for name, probe in (("resume", lambda: _resume_armed(top)),
                        ("sender", lambda: _typing_sender(top)),
                        ("typer", lambda: (_goal_typer() is not None, TYPER_ABSENT))):
        try:
            ok, why = probe()
        except Exception as exc:  # pylint: disable=broad-except
            missing.append(f"could not tell the {name} ({type(exc).__name__}: {exc})")
            continue
        if not ok:
            missing.append(_TYPER_MISSING[name].format(why=why))
    return {"offer": not missing, "missing": missing}


def goal_propose(root, proposal_file):
    """Write the goal file from a staged proposal and render what the command
    shows: `{"slug", "path", "goal_line", "goal_status", "risk", "known",
    "tickets", "typer"}`. `goal_status` is GOAL_STATUS, always: autopilot
    cannot observe Claude Code's /goal state, so it never reports it set."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    data = _read_proposal_file(top, proposal_file)
    made = write_goal(top, data.get("goal"), {"done_condition": data.get("done_condition"),
                                              "findings": data.get("findings")},
                      data.get("tickets"))
    risk = goal_risk(made["goal"]["tickets"])
    return {"slug": made["slug"], "path": ap._rel(top, made["path"]),
            "goal_line": goal_line(made["goal"]), "goal_status": GOAL_STATUS,
            "risk": risk["risk"], "known": risk["known"], "tickets": made["goal"]["tickets"],
            "typer": typer_offer(top)}


def goal_propose_text(result):
    risk = result["risk"] if result["known"] else "high(unknown)"
    lines = [ap._line(slug=result["slug"], goal_status=result["goal_status"], risk=risk,
                   tickets=len(result["tickets"]), file=result["path"]),
             f"goal_line: {result['goal_line']}", GOAL_UNSEEN]
    for n, ticket in enumerate(result["tickets"]):
        after = ",".join(str(d + 1) for d in ticket["depends_on"]) or "-"
        lines.append(ap._one_line(f"ticket {n + 1}: {ticket['title']} (risk: {ticket['risk']}; "
                               f"after: {after})"))
    typer = result["typer"]
    lines.append("typer: offered - T-0013 can type the /goal line on the owner's yes"
                 if typer["offer"] else
                 ap._one_line("typer: not offered - " + "; ".join(typer["missing"])))
    return "\n".join(lines)


def split_policy(root, slug, goal=None):
    """`{"allow", "policy", "risk", "known", "reason", "warnings"}` -- whether
    autopilot may approve the goal's split itself, with T-0010's rules and
    settings: never without `scope.allowCliApproval` exactly true, never
    unarmed, `human` never, `self` at any goal risk, `risk` only when every
    proposed ticket is a known `low`. A goal file that cannot be read, or
    anything that raises, refuses as could-not-tell. `goal`: the read the
    caller already holds, so the policy judges the very proposal it approves."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    try:
        goal = read_goal(top, slug) if goal is None else goal
        conf = ap.settings(top)
        allowed = crew_ticket.cli_approval_allowed(top)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return {"allow": False, "policy": ap.UNKNOWN, "risk": "high", "known": False,
                "warnings": [], "reason": (f"could not tell whether autopilot may approve the "
                                           f"split ({type(exc).__name__}: {exc})")}
    risk = goal_risk(goal["tickets"])
    policy = conf["approval"]
    warnings = [w for w in conf["warnings"] if "autopilot.approval " in w
                or "autopilot.mode " in w]
    result = {"allow": False, "policy": policy, "risk": risk["risk"], "known": risk["known"],
              "warnings": warnings}
    words = (f"goal risk: {risk['risk']}" if risk["known"]
             else "a proposed ticket's risk is not low|med|high (reads as high)")
    all_low = risk["known"] and risk["risk"] == "low"
    why = _split_rule(conf, warnings, allowed, all_low,
                      f"autopilot.approval is risk and the {words}, not every ticket low")
    if why:
        return dict(result, reason=why)
    return dict(result, allow=True, reason=(
        f"autopilot.approval is self ({words})" if policy == ap.SELF
        else "autopilot.approval is risk and every proposed ticket is risk: low"))


def _split_rule(conf, warnings, allowed, low, risk_refusal):
    """T-0012's split rule, slug-free (T-0058 applies it to a ticket's split
    too, through `crew_split.ticket_split_policy`): the first refusal's
    reason, or "" when autopilot may approve. `conf` is `settings`'s answer,
    `allowed` `crew_ticket.cli_approval_allowed`'s, `low` whether the risk is
    a KNOWN `low`; `risk_refusal` names the risk under `risk`. Only `self`,
    or `risk` with a known `low`, is left."""
    policy = conf["approval"]
    refusals = (
        (policy == ap.UNKNOWN, f"could not tell the approval policy "
                               f"({'; '.join(warnings) or 'unreadable'}); the human approves "
                               "the split"),
        (allowed is not True, f"{ap.ALLOW_CLI} is not exactly true in .crew/config.json, so no "
                              "split approval but the human's counts"),
        (conf["armed"] is not True, "autopilot is not armed (autopilot.mode is not plan or backlog), so "
                                    "it approves no split"),
        # `human`, and anything settings did not map to a policy: never approves.
        (policy not in (ap.SELF, ap.RISK), f"autopilot.approval is {policy}: the split waits "
                                           "for the owner"),
        (policy == ap.RISK and low is not True, risk_refusal),
    )
    return next((why for refused, why in refusals if refused), "")


def _owner_receipt(top, slug, digest):
    """`(state, why)`: `match` (the owner's prompt approved THIS proposal),
    `absent`, `stale` (approved, then the proposal changed) or `unknown` (a
    receipt is there and cannot be read) -- never read as absent. The
    `goals/<slug>` directory must be a real one and approval.json a regular
    file (lstat): a symlink, or anything else, is `unknown`."""
    path = goal_receipt_path(top, slug)
    for where, test in ((os.path.dirname(path), stat.S_ISDIR), (path, stat.S_ISREG)):
        try:
            mode = os.lstat(where).st_mode
        except FileNotFoundError:
            return "absent", ""
        if not test(mode):
            return "unknown", (f"the owner's split receipt at {where} is not a regular "
                               "file or directory (a symlink?), so it is not read")
    data = ap._read_json(path)
    if not isinstance(data, dict):
        return "unknown", "the owner's split receipt is there but could not be read"
    if data.get("approved_via") != "user-prompt":
        return "unknown", "the split receipt is not the owner's prompt's"
    if data.get("proposal_sha256") != digest:
        return "stale", ("the owner's split receipt does not match the current proposal "
                         "(it changed after the approval)")
    return "match", ""


def split_approved(root, slug):
    """`{"approved", "via", "policy", "risk", "reason", "owner", "warnings"}`.
    Yes when the owner's receipt matches the current proposal's digest, at any
    setting; else when `split_policy` allows, re-asked on every call. That yes
    is noted in the goal file as `approval: {via: "autopilot:<policy>",
    proposal_sha256}` for the report, and the note is never read back as a
    grant. Else no, naming the owner's `/crew:approve goal:<slug>`."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    owner = OWNER_SPLIT.format(slug=slug)
    no = {"approved": False, "via": "", "policy": ap.UNKNOWN, "risk": "high", "warnings": [],
          "owner": owner}
    try:
        goal = read_goal(top, slug)
        digest = goal_digest(goal)
        state, why = _owner_receipt(top, slug, digest)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return dict(no, reason=f"could not tell whether the split is approved "
                               f"({type(exc).__name__}: {exc})")
    if state == "match":
        return dict(no, approved=True, via="user-prompt", owner="",
                    risk=goal_risk(goal["tickets"])["risk"],
                    reason="the owner approved this proposal")
    policy = split_policy(top, slug, goal)
    base = dict(no, policy=policy["policy"], risk=policy["risk"], warnings=policy["warnings"])
    if not policy["allow"]:
        return dict(base, reason="; ".join(r for r in (policy["reason"], why) if r))
    via = f"autopilot:{policy['policy']}"
    # A receipt that is there but unusable is named on the allow path too.
    warnings = list(policy["warnings"]) + ([why] if why else [])
    # The note goes onto the proposal the policy judged, and only while the
    # file still holds it: an edit since the read is never approved or overwritten.
    try:
        same = goal_digest(read_goal(top, slug)) == digest
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return dict(base, reason=f"could not re-read the goal file before noting the approval "
                                 f"({type(exc).__name__}: {exc})")
    if not same:
        return dict(base, reason="the proposal changed while its split was being approved; "
                                 "nothing was written - ask again")
    try:
        _write_json_atomic(goal_path(top, slug), dict(goal, approval={
            "via": via, "proposal_sha256": digest}))
    except OSError as exc:
        warnings.append(f"the approval note was not written to the goal file ({exc})")
    return dict(base, approved=True, via=via, owner="", warnings=warnings,
                reason=policy["reason"])


def split_approved_text(slug, result):
    if result["approved"]:
        lines = [f"split-approved {slug} via={result['via']} risk={result['risk']}"]
    else:
        lines = [ap._one_line(f"refused: {result['reason']}"),
                 ap._one_line(f"note: {OWNER_HOOK_PENDING}")]
    lines += [ap._one_line(f"warning: {w}") for w in result["warnings"]]
    if not result["approved"]:
        lines.append(f"owner: the human types {result['owner']}")
    return "\n".join(lines)


def main(args):
    """`goal-propose` (exit 0 written, 2 refused), `goal-approve` (0 approved
    and every ticket minted, 2 not) and `goal-run` (exit 0, the answer in
    `stop=`). A crash is a refusal, exit 1, never silence."""
    backlog = importlib.import_module("crew_autopilot_backlog")
    try:
        if args.action == "goal-propose":
            result = goal_propose(args.root, args.proposal_file)
            code, text = 0, goal_propose_text(result)
        elif not _goal_slug_ok(args.goal):
            raise GoalError(f"--goal {args.goal!r} is not a goal slug "
                            "([a-z0-9][a-z0-9-]{0,63})")
        elif args.action == "goal-run":
            result = backlog.goal_run(args.root, args.goal, args.session or None,
                                      args.transcript or None)
            code, text = 0, backlog.goal_run_text(result)
        elif args.ticket:
            code, text = backlog.ticket_approve(args.root, args.goal, args.ticket)
            result = {"code": code, "text": text}
        else:
            result = split_approved(args.root, args.goal)
            code, text = (0 if result["approved"] else 2), split_approved_text(args.goal, result)
            if result["approved"]:
                minted = backlog.mint_goal(args.root, args.goal)
                result["mint"] = minted
                code = 2 if minted["stop"] else 0
                text = "\n".join([text] + backlog.mint_text(minted)
                                 + ([backlog.RESUME.format(slug=args.goal)]
                                    if minted["stop"] else []))
    except (GoalError, crew_ticket.TicketError) as exc:
        result, code, text = {"refused": str(exc)}, 2, ap._one_line(f"refused: {exc}")
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        result, code = {"refused": ap._failure(exc)}, 1
        text = ap._one_line(f"refused: {ap._failure(exc)}")
    sys.stdout.write((json.dumps(result, indent=2) if args.json else text) + "\n")
    return code


def add_parsers(sub):
    """`goal-propose`, `goal-approve` and `goal-run` on crew_autopilot.py's subparsers."""
    for name in ("goal-propose", "goal-approve", "goal-run"):
        action = sub.add_parser(name)
        action.add_argument("--json", action="store_true")
        action.add_argument("--root", default=".")
    sub.choices["goal-propose"].add_argument("--proposal-file", required=True)
    for name in ("goal-approve", "goal-run"):
        sub.choices[name].add_argument("--goal", required=True)
    sub.choices["goal-approve"].add_argument("--ticket", default="")
    sub.choices["goal-run"].add_argument("--session", default="")
    sub.choices["goal-run"].add_argument("--transcript", default="")
