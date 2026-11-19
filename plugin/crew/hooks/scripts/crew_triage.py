#!/usr/bin/env python3
"""crew_triage.py: size route, difficulty score and starting model for one task.

INERT. Nothing in the plugin imports or invokes this module, and the test
file holds that (`test_nothing_under_plugin_mentions_the_module`). It answers
one question for a person or a test: "what would triage say for this task?"
Role defaults, escalation by round (R-71), the phase state machine (R-73) and
posting to Jira (R-72) are later tickets.

Input: one dict (see `FIELDS`).

    size        S | M | L | XL; anything else, or absent, is unknown
    factors     {complexity, systems, risk, ambiguity}, each an int 0..2
    legacy      True/False: the work touches legacy code
    money       True/False: the work touches money or billing
    docs_only   True/False: the work is documentation or internal only
    task_type   a free label; only the exact members of `MECHANICAL` matter

The scoring is the owner's dev-workflow artifact, "Triage: difficulty score"
and "Triage: T-shirt size": four factors 0..2, three cumulative legacy
modifiers, bands 0-2 Sonnet 5.5, 3-5 Opus 5.5, 6+ Fable 5.2, and L or XL
becomes an epic. Mechanical task types go straight to Haiku 5.5.

Unknown never takes the cheaper branch: a missing or invalid factor scores 2,
a missing or non-bool `legacy` or `money` counts as true, a missing `docs_only`
counts as false, and a missing or invalid size is `needs-size`, never S. Each
such field is named in `unknown`.

Override order, first match wins, size before task type:
  epic (size L or XL), needs-size, mechanical, docs, then the band with a
  risk floor (risk 2 is at least Opus; a floor, never a cap).
The mechanical route is taken before scoring and never reads or evaluates the
factors. A docs_only task with risk 2 is a normal ticket and says so: the
override `docs-rejected-risk` and a note in `post`. The CLI accepts standard
JSON only (NaN and Infinity are refused).

Output: `triage` returns a dict with every key of `OUTPUT_KEYS` on every route.
Pure: standard library only, no file, environment, git or network access.
"""
import json
import sys

REPORT_ONLY = True

FIELDS = ("size", "factors", "legacy", "money", "docs_only", "task_type")
FACTOR_NAMES = ("complexity", "systems", "risk", "ambiguity")
SIZES = ("S", "M", "L", "XL")
RUNNABLE = ("S", "M")
EPIC_SIZES = ("L", "XL")

# Band edges: the artifact's "starting guesses". One place to tune.
OPUS_AT = 3
FABLE_AT = 6

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
OPUS = "claude-opus-5-5"
FABLE = "claude-fable-5-2"
# Ordered cheapest first; a higher index is a stronger model.
MODELS = (
    (HAIKU, "Haiku 5.5", "low"),
    (SONNET, "Sonnet 5.5", "medium"),
    (OPUS, "Opus 5.5", "high"),
    (FABLE, "Fable 5.2", "high"),
)
RANK = {m[0]: i for i, m in enumerate(MODELS)}
NAME = {m[0]: m[1] for m in MODELS}
EFFORT = {m[0]: m[2] for m in MODELS}

MECHANICAL = frozenset((
    "ticket-update", "jira-status", "evidence-link", "file-scan",
    "find-references", "relay", "scripted-check", "log-extract", "rename",
    "format", "boilerplate", "commit-message", "changelog",
))

ROUTES = ("workflow", "docs", "mechanical", "epic", "needs-size")
OUTPUT_KEYS = (
    "route", "size", "factors", "legacy_points", "score", "model",
    "model_name", "effort", "overrides", "unknown", "ignored",
    "ticket_status", "notify", "suggest_breakdown", "post",
)
BACKLOG = "Backlog"
PARKED = "Blocked or Parked"


def _field(task, name):
    """One input field, or None when absent."""
    return task.get(name)


def _factor(value):
    """(effective value, known): only a real int 0..2 is known; else 2."""
    if type(value) is int and 0 <= value <= 2:  # pylint: disable=unidiomatic-typecheck
        return value, True
    return 2, False


def _flag(value, unknown_as):
    """(effective bool, known): only a real bool is known."""
    if type(value) is bool:  # pylint: disable=unidiomatic-typecheck
        return value, True
    return unknown_as, False


def _size(value):
    """The size when it is one of `SIZES` exactly, else None."""
    if isinstance(value, str) and value in SIZES:
        return value
    return None


def _factors(raw):
    """({name: effective}, [unknown names]) for the four factors."""
    given = raw if isinstance(raw, dict) else {}
    effective, unknown = {}, []
    for name in FACTOR_NAMES:
        value, known = _factor(_field(given, name))
        effective[name] = value
        if not known:
            unknown.append(name)
    return effective, unknown


def legacy_points(legacy, money, systems):
    """The cumulative legacy modifiers: 0..3."""
    if not legacy:
        return 0
    return 1 + (1 if money else 0) + (1 if systems >= 1 else 0)


def band(score):
    """The model the score alone picks."""
    if score >= FABLE_AT:
        return FABLE
    if score >= OPUS_AT:
        return OPUS
    return SONNET


def _describe(factors):
    return ", ".join(f"{n} {factors[n]}" for n in FACTOR_NAMES)


def triage(task):
    """The triage of one task dict; every key of `OUTPUT_KEYS` is present."""
    if not isinstance(task, dict):
        raise TypeError("task must be a dict")
    ignored = sorted(str(k) for k in task if k not in FIELDS)
    size = _size(_field(task, "size"))
    task_type = _field(task, "task_type")
    is_mech = isinstance(task_type, str) and task_type in MECHANICAL
    legacy, legacy_known = _flag(_field(task, "legacy"), True)
    money, money_known = _flag(_field(task, "money"), True)
    docs_only, docs_known = _flag(_field(task, "docs_only"), False)
    extra = [n for n, ok in (("legacy", legacy_known), ("money", money_known),
                             ("docs_only", docs_known)) if not ok]

    out = {k: None for k in OUTPUT_KEYS}
    out.update(ignored=ignored, overrides=[], notify=False,
               suggest_breakdown=False, ticket_status=BACKLOG, size=size)

    def pick(model, route, overrides, unknown_list):
        out.update(route=route, model=model, model_name=NAME[model],
                   effort=EFFORT[model], overrides=overrides,
                   unknown=unknown_list)

    if size in RUNNABLE and is_mech:
        # The mechanical route skips scoring: factors are neither read nor
        # evaluated, so they are not named in `unknown` either.
        pick(HAIKU, "mechanical", ["mechanical"], extra)
        out["post"] = (f"size {size}; mechanical: {task_type}; "
                       f"model {NAME[HAIKU]}")
        return out

    factors, unknown = _factors(_field(task, "factors"))
    points = legacy_points(legacy, money, factors["systems"])
    score = sum(factors.values()) + points
    out.update(factors=factors, legacy_points=points, score=score)
    scored = f"score {score} ({_describe(factors)})"
    if size in EPIC_SIZES:
        out.update(route="epic", overrides=["epic"], unknown=unknown + extra,
                   ticket_status=PARKED, notify=True, suggest_breakdown=True,
                   post=f"size {size}; {scored}; epic: break down")
    elif size is None:
        deferred = ["mechanical-deferred"] if is_mech else []
        out.update(route="needs-size", overrides=["needs-size"] + deferred,
                   unknown=unknown + ["size"] + extra, ticket_status=PARKED,
                   notify=True, post=f"size missing; {scored}")
    elif docs_only and factors["risk"] < 2:
        pick(SONNET, "docs", ["docs"], unknown + extra)
        out["post"] = f"size {size}; {scored}; model {NAME[SONNET]}"
    else:
        model, overrides = band(score), []
        note = ""
        if docs_only:  # risk 2: the docs route was considered and rejected
            overrides.append("docs-rejected-risk")
            note = "; docs route rejected: risk 2"
        if factors["risk"] == 2 and RANK[model] < RANK[OPUS]:
            model = OPUS
            overrides.append("risk-floor")
        pick(model, "workflow", overrides, unknown + extra)
        out["post"] = f"size {size}; {scored}; model {NAME[model]}{note}"
    return out

def tables():
    """The artifact tables this module encodes, as text."""
    rows = ["Triage: T-shirt size",
            "  S, M   run through the workflow",
            "  L, XL  epic: break down, ticket Blocked or Parked, notify",
            "  other  needs-size: ticket Blocked or Parked, notify",
            "Triage: difficulty score (factors 0..2: "
            + ", ".join(FACTOR_NAMES) + ")",
            "  legacy                        +1",
            "  legacy and money              +1 more",
            "  legacy and 2+ systems         +1 more",
            f"  score 0-{OPUS_AT - 1}                   Sonnet 5.5",
            f"  score {OPUS_AT}-{FABLE_AT - 1}                   Opus 5.5",
            f"  score {FABLE_AT}+                    Fable 5.2",
            "  risk 2                        Opus 5.5 at least",
            "  docs only, risk below 2       Sonnet 5.5",
            "Mechanical task types (size S or M): Haiku 5.5",
            "  " + ", ".join(sorted(MECHANICAL))]
    return "\n".join(rows)


def _reject_constant(name):
    """NaN and Infinity are not JSON: refuse them."""
    raise ValueError(name)


def _main(argv):
    if len(argv) == 2 and argv[1] == "tables":
        print(tables())
        return 0
    if len(argv) == 3 and argv[1] == "triage":
        try:
            task = json.loads(argv[2], parse_constant=_reject_constant)
        except (ValueError, RecursionError):
            task = None
        if isinstance(task, dict):
            print(json.dumps(triage(task), indent=2))
            return 0
        print("crew_triage: expected one JSON object", file=sys.stderr)
        return 2
    print("usage: crew_triage.py triage '<json>' | tables", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
