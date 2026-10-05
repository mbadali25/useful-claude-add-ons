"""T-0058: autopilot's size check after spec and after plan, and
`/crew:autopilot split`, split out of `crew_autopilot.py` (pylint's
module-length limit). `crew_autopilot._phase` calls `gate` once the spec
validates (stage `spec`) and once the plan does (stage `plan`), appends
`FIXED_STOPS` to its own and `WAITING` to status's table, and dispatches the
`split` action here.

    python3 crew_autopilot.py split --root . --ticket <id> [--check|--apply]

`gate` runs T-0052's `crew_split.triggers` on `measure`. Nothing fired
continues. A measure whose source is there and cannot be read stops as
`split-check-unknown`; a source the repo does not have at all
(`crew_split.absent_sources`: no codemap, no review recorded) is named
`unmeasured` and does not stop. A fired trigger with no current `split.md`
(it fails the rulebook, or its `answered:` misses a fired trigger) is
`split-check` (not a stop: autopilot looks, `/crew:autopilot split <id>`).
`not-too-big` continues; `slices` continues at spec and, at plan, only when
T-0059's `crew_split.parse_slices` passes (absent: `split-check-unknown`);
`split` is `split-approval` (a stop; `split --apply` passes it only under
`crew_split.ticket_split_policy`, never in Jira mode) until the parent is
`superseded`, which reads `closed`. `split` prints the measures, `--check`
runs `crew_split.check` plus the `answered:` rule, `--apply` runs
`crew_split.apply(..., via="autopilot")`; a refusal ends `owner: the human
types /crew:split <id>`.

`split --check` writes `crew_split.check`'s record and `split --apply`
writes what `crew_split.apply` writes (the children, the parent's pre-split
copy and status), only under `crew_split.ticket_split_policy`. The gate
writes nothing. `crew_autopilot` is imported lazily (`_ap`), so importing
this module never imports it back.
"""
import importlib
import os
import sys

import crew_split
import crew_ticket
from crew_common import read_text

SLICES_ARRIVE = "T-0059"
FIXED_STOPS = (
    ("split-approval", "split.md decides split: autopilot applies it only under "
                       "autopilot.approval, never in Jira mode; else the owner runs "
                       "/crew:split <id>"),
    ("split-check-unknown", "a size measure whose source is there could not be read, or a "
                            "slices decision whose ## PR slices cannot be checked yet"),
)
# Phases `status` reports as waiting on the owner (crew_autopilot.WAITING);
# `split-check` waits on autopilot itself.
WAITING = ("split-approval", "split-check-unknown")


def _ap():
    """crew_autopilot, imported when first needed (it imports this module)."""
    return importlib.import_module("crew_autopilot")


def _size_check(top, ticket, stage):
    """`{"fired", "unknown", "unmeasured", "measures"}` from T-0052's rulebook.
    `unknown`: `unknown:<name>` whose source is there and could not be read;
    `unmeasured`: `{name: why}` for a source this repo does not have
    (`crew_split.absent_sources`) -- named, never read as "not fired"."""
    measures = crew_split.measure(top, ticket)
    names = crew_split.triggers(measures, stage)
    absent = crew_split.absent_sources(top)
    blank = [n.split(":", 1)[1] for n in names if n.startswith("unknown:")]
    return {"measures": measures, "fired": [n for n in names if ":" not in n],
            "unknown": [n for n in blank if n not in absent],
            "unmeasured": {n: absent[n] for n in blank if n in absent}}


def _unmeasured_words(size):
    return "".join(f"; unmeasured: {name} ({why})" for name, why in size["unmeasured"].items())


def _decision_state(top, ticket, fired):
    """`(decision, why_not_current)`: split.md's decision, current only when it
    passes the rulebook and its `answered:` names every fired trigger."""
    folder = crew_ticket.ticket_dir(top, ticket)
    text = read_text(os.path.join(folder, crew_split.PROPOSAL))
    if text is None:
        return None, f"no {crew_split.PROPOSAL} decision yet"
    criteria = crew_split.parent_criteria(read_text(os.path.join(folder, "spec.md")))
    decision, problems = crew_split.check_proposal(criteria, text)
    missing = [f for f in fired if f not in crew_split.parse_proposal(text)["answered"]]
    if missing:
        problems = problems + [f"answered: does not name {', '.join(missing)}"]
    if problems:
        return decision, f"{crew_split.PROPOSAL} is not current: " + "; ".join(problems)
    return decision, ""


def _slice_problems(top, ticket):
    """T-0059's `parse_slices` on plan.md: its problems, or None when it is
    absent or its answer cannot be read."""
    parse = getattr(crew_split, "parse_slices", None)
    if not callable(parse):
        return None
    plan = read_text(os.path.join(crew_ticket.ticket_dir(top, ticket), "plan.md")) or ""
    got = parse(plan)  # pylint: disable=not-callable
    problems = got[1] if isinstance(got, tuple) and len(got) == 2 else (
        got.get("problems") if isinstance(got, dict) else None)
    if not isinstance(problems, (list, tuple)):
        return None
    if not problems and isinstance(got, tuple) and not got[0]:
        # No section at all is a valid unsliced plan, but not a `slices` one.
        return ["plan.md has no ## PR slices section, which a slices decision needs"]
    return list(problems)


def gate(top, ticket, stage, answer, policy=True):
    """None to continue, or `next`'s answer for the size check at `stage`
    (module docstring). A trigger means look, never split."""
    look = f"/crew:autopilot split {ticket}"
    try:
        size = _size_check(top, ticket, stage)
        if size["unknown"] or not size["fired"]:
            decision, why = None, ""
        else:
            decision, why = _decision_state(top, ticket, size["fired"])
        slices = (_slice_problems(top, ticket)
                  if not why and decision == "slices" and stage == "plan" else [])
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return answer("split-check-unknown", True, f"the size check after {stage} could not "
                      f"run ({type(exc).__name__}: {exc}) - a person looks", look)
    if size["unknown"]:
        return answer("split-check-unknown", True, _unknown_words(stage, size["unknown"]), look)
    if not size["fired"]:
        return None
    fired = f"after {stage}: {', '.join(size['fired'])} fired (a trigger means look, never split)"
    if why:
        return answer("split-check", False, f"{fired}; {why}{_unmeasured_words(size)}", look)
    if decision == "split":
        hint = ""
        if policy:
            rule = crew_split.ticket_split_policy(top, ticket)
            hint = (f"; autopilot may apply it: crew_autopilot.py split --apply "
                    f"({rule['reason']})" if rule["allow"] else f"; {rule['reason']}")
        return answer("split-approval", True, f"{fired}; {crew_split.PROPOSAL} decides split, "
                      f"not yet applied{hint}", f"/crew:split {ticket}")
    if slices is None:
        return answer("split-check-unknown", True, f"{fired}; the slices decision needs the "
                      f"plan's ## PR slices checked, which arrives with {SLICES_ARRIVE}",
                      f"/crew:plan {ticket}")
    if slices:
        return answer("plan", True, f"{fired}; the plan's ## PR slices fail: "
                      + "; ".join(str(p) for p in slices), f"/crew:plan {ticket}")
    return None


def split_report(root, ticket):
    """`split`'s bare lines: the measures, the fired triggers, the unmeasured
    and unknown ones, the tracker, the current decision and the policy."""
    top = crew_ticket.toplevel(root) or os.path.abspath(root)
    stage = _gate_stage(top, ticket)
    size = _size_check(top, ticket, stage)
    decision, why = _decision_state(top, ticket, size["fired"])
    rule = crew_split.ticket_split_policy(top, ticket)
    lines = [" ".join(f"{k}={crew_split._fmt(v)}"  # pylint: disable=protected-access
                      for k, v in size["measures"].items()),
             f"stage={stage} triggers: {', '.join(size['fired']) or 'none'}"]
    lines += [f"unknown: {name} (its source is there and could not be read)"
              for name in size["unknown"]]
    lines += [f"unmeasured: {name} ({w})" for name, w in size["unmeasured"].items()]
    lines += [f"tracker={crew_split.tracker_mode(top)}",
              f"decision={decision or 'none'} current={int(not why)}"
              + (f" ({why})" if why else ""),
              f"policy: {'allow' if rule['allow'] else 'refuse'} - {rule['reason']}"]
    return [_ap()._one_line(line) for line in lines]  # pylint: disable=protected-access


def _unknown_words(stage, unknown):
    """The split-check-unknown reason: the gate's, `--check`'s and `--apply`'s."""
    return (f"the size check after {stage} could not read {', '.join(unknown)} (its source "
            "is there): could not tell is not \"small\" - a person fixes the source "
            "(Acceptance checks as `- [ ]` bullets, `### Step` plan headings, every Touch "
            "entry under a codemap subsystem, a readable .crew/metrics.md)")


def _gate_stage(top, ticket):
    """The stage `_phase` last ran the size check at: `plan` once plan.md
    passes crew_ticket.validate, else `spec` (a plan that fails it stops at
    `plan` before the plan-stage check)."""
    contract = crew_ticket.read_contract(top, ticket)
    if contract["plan.md"] is None or crew_ticket.validate(top, ticket, contract):
        return "spec"
    return "plan"


def _not_current(top, ticket):
    """What the gate would still stop or look at, for `--check` and `--apply`:
    the split-check-unknown reason while a measure is unknown, else
    `answered: does not name <triggers>` for triggers firing now at the
    gate's stage that split.md misses; [] when neither."""
    folder = crew_ticket.ticket_dir(top, ticket)
    stage = _gate_stage(top, ticket)
    size = _size_check(top, ticket, stage)
    if size["unknown"]:
        return [_unknown_words(stage, size["unknown"])]
    proposal = crew_split.parse_proposal(
        read_text(os.path.join(folder, crew_split.PROPOSAL)) or "")
    missing = [f for f in size["fired"] if f not in proposal["answered"]]
    if missing:
        return [f"answered: does not name {', '.join(missing)}"]
    if stage == "plan" and size["fired"] and proposal.get("decision") == "slices":
        # The gate's slices rule: at plan, `slices` stands only on a plan
        # whose `## PR slices` passes parse_slices.
        slices = _slice_problems(top, ticket)
        if slices is None:
            return [f"the slices decision needs the plan's ## PR slices checked, which "
                    f"arrives with {SLICES_ARRIVE}"]
        if slices:
            return ["the plan's ## PR slices fail: " + "; ".join(str(p) for p in slices)]
    return []


def add_parsers(sub):
    """`split` on crew_autopilot.py's subparsers."""
    split = sub.add_parser("split")
    split.add_argument("--root", default=".")
    split.add_argument("--ticket", required=True)
    given = split.add_mutually_exclusive_group()
    given.add_argument("--check", action="store_true")
    given.add_argument("--apply", action="store_true")


def main(args):
    """`split` (exit 0), `split --check` (0 pass, 1 problems) and `split
    --apply` (0 applied, 1 refused, the owner's /crew:split last). A crash is
    a refusal, exit 1."""
    ap = _ap()
    lines, code = [], 0
    try:
        top = crew_ticket.toplevel(args.root) or os.path.abspath(args.root)
        crew_ticket.check_ticket(args.ticket)
        if args.check:
            decision, problems = crew_split.check(top, args.ticket)
            stale = _not_current(top, args.ticket)
            if stale and not problems:
                # check recorded a pass the gate does not grant: never leave
                # it for confirm to trust.
                crew_split._drop(crew_split.check_record_path(top, args.ticket))  # pylint: disable=protected-access
            problems = problems + stale
            lines = [f"problem: {p}" for p in problems] or [f"ok decision={decision}"]
            code = 1 if problems else 0
        elif args.apply:
            # The gate's rules: nothing applies while a measure is unknown, nor
            # a decision taken before a trigger now firing.
            stale = _not_current(top, args.ticket)
            if stale:
                raise crew_split.SplitError(f"{crew_split.PROPOSAL} cannot be applied: "
                                            + "; ".join(stale) + "; nothing was written")
            got = crew_split.apply(top, args.ticket, "autopilot")
            lines = ([f"child={kid}" for kid in got["children"]]
                     + [f"parent={args.ticket} status={got['parent']}"]
                     + [f"warning: {w}" for w in got["warnings"]])
        else:
            lines = split_report(top, args.ticket)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        lines, code = [f"refused: {ap._failure(exc)}"], 1  # pylint: disable=protected-access
        if args.apply:
            lines.append(f"owner: the human types /crew:split {args.ticket}")
    sys.stdout.write("\n".join(ap._one_line(line)  # pylint: disable=protected-access
                               for line in lines) + "\n")
    return code
