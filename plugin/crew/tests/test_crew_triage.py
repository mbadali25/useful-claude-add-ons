"""`crew_triage.py`: size route, difficulty score, starting model (R-70), INERT.

The artifact's cases are tables here, one row per case. Each table is a
function `check_*(mod)` that returns a list of violations, so the same table
runs against the real module (must be empty) and against weakened copies of
its source (`MUTATIONS`, each must produce at least one violation). The shared
`sabotage*.py` files are review-harness paths that must land alone, and this
module blocks nothing, so the in-file form is used (the `test_crew_policy.py`
pattern).
"""
import ast
import itertools
import json
import os
import shutil
import stat
import subprocess
import sys
import types

import pytest

import context  # noqa: F401  pylint: disable=unused-import

import crew_triage as T  # noqa: E402  pylint: disable=wrong-import-position

SCRIPTS = os.path.dirname(os.path.abspath(T.__file__))
PLUGIN = os.path.dirname(os.path.dirname(SCRIPTS))
REPO = os.path.dirname(os.path.dirname(PLUGIN))  # the repo root, above plugin/
MODULE = os.path.join(SCRIPTS, "crew_triage.py")
GONE = object()  # the key is absent
SONNET, OPUS, FABLE, HAIKU = ("claude-sonnet-5-5", "claude-opus-5-5",
                              "claude-fable-5-2", "claude-haiku-5-5")
ORDER = (HAIKU, SONNET, OPUS, FABLE)


def source():
    """The module's text."""
    with open(MODULE, encoding="utf-8") as handle:
        return handle.read()


def _fac(**kw):
    """A factors dict from keywords."""
    return kw


def task(size="S", factors=None, **more):
    """A task dict; `GONE` removes a key, `factors` fills the rest with 0."""
    given = _fac(complexity=0, systems=0, risk=0, ambiguity=0)
    if isinstance(factors, dict) or factors is None:
        given.update(factors or {})
    else:
        given = factors  # GONE or a non-dict, passed through as given
    out = {"size": size, "factors": given, "legacy": False, "money": False,
           "docs_only": False, "task_type": None}
    out.update(more)
    return {k: v for k, v in out.items() if v is not GONE}


def _gone_factor(name):
    """Factors dict with one factor removed."""
    fac = _fac(complexity=0, systems=0, risk=0, ambiguity=0)
    del fac[name]
    return fac


def _summary(out):
    return (out["route"], out["model"], out["overrides"])


# --- the tables: each returns a list of violations -------------------------

def check_factor_table(mod):
    """Table 1: each factor at 0, 1, 2 with the rest 0 adds that value."""
    bad = []
    for name, value in itertools.product(mod.FACTOR_NAMES, (0, 1, 2)):
        out = mod.triage(task(factors={name: value}))
        if out["score"] != value or out["factors"][name] != value:
            bad.append(("factor", name, value, out["score"]))
    return bad


LEGACY_ROWS = (  # legacy, money, systems, points
    (False, False, 0, 0), (True, False, 0, 1), (True, True, 0, 2),
    (True, False, 1, 2), (True, True, 1, 3), (False, True, 0, 0),
    (False, False, 1, 0), (False, True, 1, 0), (True, False, 2, 2),
    (True, True, 2, 3),
)


def check_legacy_table(mod):
    """Table 2: the cumulative legacy modifiers; systems >= 1 is multi."""
    bad = []
    for legacy, money, systems, points in LEGACY_ROWS:
        out = mod.triage(task(factors={"systems": systems}, legacy=legacy,
                              money=money))
        if out["legacy_points"] != points or out["score"] != systems + points:
            bad.append(("legacy", legacy, money, systems, out["legacy_points"]))
    return bad


# score -> model, built from factors that sum to the score with risk 0
BAND_ROWS = ((0, SONNET), (2, SONNET), (3, OPUS), (5, OPUS), (6, FABLE),
             (8, FABLE))  # up to 8: the four factors at 2 and no legacy


def _factors_for(score):
    """Factors that sum to `score` <= 8, risk last (so risk is 0 up to 6)."""
    left = score
    fac = {}
    for name in ("complexity", "systems", "ambiguity", "risk"):
        fac[name] = min(2, left)
        left -= fac[name]
    return fac


def check_bands(mod):
    """Table 3: band edges, with no risk and no legacy."""
    bad = []
    for score, model in BAND_ROWS:
        out = mod.triage(task(factors=_factors_for(score)))
        if out["score"] != score or out["model"] != model:
            bad.append(("band", score, out["score"], out["model"]))
    # the top of the scale: 11 = 8 factors + 3 legacy
    top = mod.triage(task(factors=_fac(complexity=2, systems=2, risk=2,
                                       ambiguity=2), legacy=True, money=True))
    if top["score"] != 11 or top["model"] != FABLE:
        bad.append(("band", "max", top["score"], top["model"]))
    return bad


def check_overrides(mod):
    """Table 4: docs, risk floor, epic."""
    bad = []
    rows = (
        # label, task, route, model, overrides
        ("docs only with a high score",
         task(factors=_fac(complexity=2, systems=1, ambiguity=2, risk=1),
              legacy=True, money=True, docs_only=True),
         "docs", SONNET, ["docs"]),
        ("risk 2 total 2 floors to Opus", task(factors={"risk": 2}),
         "workflow", OPUS, ["risk-floor"]),
        ("risk 2 total 6 stays Fable (floor not cap)",
         task(factors=_fac(risk=2, complexity=2, systems=2)),
         "workflow", FABLE, []),
        ("docs only with risk 2 is a normal ticket, rejection recorded",
         task(factors={"risk": 2}, docs_only=True),
         "workflow", OPUS, ["docs-rejected-risk", "risk-floor"]),
        ("docs only with risk 2 and a high score keeps Fable, recorded",
         task(factors=_fac(risk=2, complexity=2, systems=2), docs_only=True),
         "workflow", FABLE, ["docs-rejected-risk"]),
        ("docs only at score 8 (risk 0) is Sonnet",
         task(factors=_fac(complexity=2, systems=1, ambiguity=2, risk=0),
              legacy=True, money=True, docs_only=True),
         "docs", SONNET, ["docs"]),
        ("S runs", task(size="S"), "workflow", SONNET, []),
        ("M runs", task(size="M"), "workflow", SONNET, []),
        ("L is an epic", task(size="L"), "epic", None, ["epic"]),
        ("XL is an epic", task(size="XL"), "epic", None, ["epic"]),
        ("docs only L is an epic", task(size="L", docs_only=True),
         "epic", None, ["epic"]),
    )
    for label, given, route, model, overrides in rows:
        out = mod.triage(given)
        if _summary(out) != (route, model, overrides):
            bad.append((label, _summary(out)))
    eight = mod.triage(next(r[1] for r in rows if "score 8" in r[0]))
    if eight["score"] != 8:
        bad.append(("docs-only score 8 case", eight["score"]))
    plain = mod.triage(task(factors={"risk": 2}))
    if "rejected" in plain["post"]:
        bad.append(("rejection recorded without docs_only", plain["post"]))
    rejected = mod.triage(task(factors={"risk": 2}, docs_only=True))
    if "docs route rejected: risk 2" not in rejected["post"]:
        bad.append(("rejection not in post", rejected["post"]))
    return bad


def _stops(out, breakdown):
    """An epic or needs-size result stops: no model, parked, notify."""
    return (out["model"] is None and out["model_name"] is None
            and out["effort"] is None and out["ticket_status"] == "Blocked or Parked"
            and out["notify"] is True and out["suggest_breakdown"] is breakdown)


def check_size_table(mod):
    """Table 5: S, M run; L, XL epic; anything else needs-size."""
    bad = []
    for size in ("S", "M"):
        out = mod.triage(task(size=size))
        if out["route"] != "workflow" or out["ticket_status"] != "Backlog":
            bad.append(("size", size, out["route"]))
    for size in ("L", "XL"):
        out = mod.triage(task(size=size))
        if out["route"] != "epic" or not _stops(out, True):
            bad.append(("size", size, out["route"]))
    for size in (GONE, None, "s", "xl", "XXL", "", 1, True, ["S"]):
        out = mod.triage(task(size=size))
        if (out["route"] != "needs-size" or not _stops(out, False)
                or out["size"] is not None or "size" not in out["unknown"]):
            bad.append(("size", repr(size), out["route"]))
    return bad


MECHANICAL_KINDS = (  # literal, so removing a member from the module fails
    "ticket-update", "jira-status", "evidence-link", "file-scan",
    "find-references", "relay", "scripted-check", "log-extract", "rename",
    "format", "boilerplate", "commit-message", "changelog",
)


class _Booby(dict):
    """A factors object that must never be read."""

    def get(self, *_a, **_k):
        raise AssertionError("factors were read on the mechanical route")

    __getitem__ = get


def _booby_task(kind):
    """A task whose factors object raises when read (`task()` would copy it)."""
    given = task(task_type=kind)
    given["factors"] = _Booby(complexity=0, systems=0, risk=0, ambiguity=0)
    return given


def check_mechanical(mod):
    """Table 6: the mechanical set goes to Haiku; size beats type."""
    bad = []
    if set(mod.MECHANICAL) != set(MECHANICAL_KINDS):
        bad.append(("mechanical set", sorted(set(mod.MECHANICAL) ^ set(
            MECHANICAL_KINDS))))
    for kind in MECHANICAL_KINDS:
        try:
            out = mod.triage(_booby_task(kind))
        except Exception as err:  # pylint: disable=broad-except
            bad.append(("mechanical evaluated factors", kind, repr(err)))
        else:
            if out["route"] != "mechanical":
                bad.append(("mechanical booby", kind, out["route"]))
        for size in ("S", "M"):
            out = mod.triage(task(size=size, task_type=kind))
            if (_summary(out) != ("mechanical", HAIKU, ["mechanical"])
                    or out["effort"] != "low" or out["score"] is not None
                    or out["factors"] is not None
                    or out["legacy_points"] is not None):
                bad.append(("mechanical", kind, size, _summary(out)))
        for size in ("L", "XL"):
            out = mod.triage(task(size=size, task_type=kind))
            if _summary(out) != ("epic", None, ["epic"]):
                bad.append(("size beats type", kind, size, _summary(out)))
        for size in (GONE, "XXL"):
            out = mod.triage(task(size=size, task_type=kind))
            want = ("needs-size", None, ["needs-size", "mechanical-deferred"])
            if _summary(out) != want:
                bad.append(("unsized mechanical", kind, size, _summary(out)))
    for kind in ("ticket update", "design", None, "Rename", "RENAME",
                 "rename-all", "xrename", " rename", "", 3):
        out = mod.triage(task(task_type=kind))
        if out["route"] != "workflow" or out["score"] is None:
            bad.append(("not mechanical", kind, out["route"]))
    # a mechanical route does not read the factors, so does not name them
    out = mod.triage({"size": "S", "task_type": "rename"})
    if out["unknown"] != ["legacy", "money", "docs_only"]:
        bad.append(("mechanical unknown", out["unknown"]))
    return bad


def check_unknowns(mod):
    """Table 7: unknown never takes the cheaper branch, and is named."""
    bad = []
    for name in mod.FACTOR_NAMES:
        given = task()
        given["factors"] = _gone_factor(name)
        out = mod.triage(given)
        if out["factors"][name] != 2 or name not in out["unknown"]:
            bad.append(("missing factor", name, out["factors"][name]))
        for value in (True, False, 3, -1, "1", 1.0, None, [1]):
            fac = _fac(complexity=0, systems=0, risk=0, ambiguity=0)
            fac[name] = value
            out = mod.triage(task(factors=fac))
            if out["factors"][name] != 2 or name not in out["unknown"]:
                bad.append(("bad factor", name, repr(value)))
    for whole in (GONE, "x", [1], 5, "none"):
        out = mod.triage(task(factors=whole))
        if (list(out["factors"].values()) != [2, 2, 2, 2]
                or out["unknown"][:4] != list(mod.FACTOR_NAMES)):
            bad.append(("factors not a dict", repr(whole)))
    for flag in ("legacy", "money"):
        for value in (GONE, None, 1, "true", "false", 0):
            out = mod.triage(task(**{flag: value}))
            if flag not in out["unknown"]:
                bad.append(("flag unnamed", flag, repr(value)))
    # a malformed flag counts as TRUE (the dearer branch), never as false
    for value in (None, 1, 0, "true", "false", "", [], {}):
        out = mod.triage(task(legacy=value))  # money False
        if out["legacy_points"] != 1:
            bad.append(("malformed legacy is not true", repr(value),
                        out["legacy_points"]))
        out = mod.triage(task(legacy=True, money=value))  # systems 0
        if out["legacy_points"] != 2:
            bad.append(("malformed money is not true", repr(value),
                        out["legacy_points"]))
    out = mod.triage(task(legacy=GONE, money=GONE))
    if out["legacy_points"] != 2:  # legacy and money both count, systems 0
        bad.append(("missing legacy/money", out["legacy_points"]))
    out = mod.triage(task(legacy=GONE))
    if out["legacy_points"] != 1 or "legacy" not in out["unknown"]:
        bad.append(("missing legacy", out["legacy_points"]))
    for value in (GONE, None, "true", 1):
        out = mod.triage(task(docs_only=value))
        if out["route"] != "workflow" or "docs_only" not in out["unknown"]:
            bad.append(("docs_only unknown", repr(value), out["route"]))
    out = mod.triage(task(extra=1, zzz=2))
    if out["ignored"] != ["extra", "zzz"]:
        bad.append(("ignored", out["ignored"]))
    return bad


BOOLS = (False, True)
LEVELS = (0, 1, 2)
SIZE_GRID = ("S", "M", "L", "XL", GONE)
TYPE_GRID = (None, "rename")


def _grid(mod):
    """Every grid cell as (size, kind, docs, factors tuple, legacy, money, out)."""
    for size, kind, docs in itertools.product(SIZE_GRID, TYPE_GRID, BOOLS):
        for fac in itertools.product(LEVELS, repeat=4):
            for legacy, money in itertools.product(BOOLS, BOOLS):
                given = task(size=size, factors=dict(zip(mod.FACTOR_NAMES, fac)),
                             legacy=legacy, money=money, docs_only=docs,
                             task_type=kind)
                yield size, kind, docs, fac, legacy, money, mod.triage(given)


def _rank(model):
    return ORDER.index(model) if model else -1


def check_grid(mod):
    """Table 8: invariants (i) to (iii) over the whole grid."""
    bad = []
    cells = {}
    for size, kind, docs, fac, legacy, money, out in _grid(mod):
        cells[(size, kind, docs, fac, legacy, money)] = _rank(out["model"])
        if size in ("L", "XL") and out["route"] != "epic":
            bad.append(("L/XL not epic", size, kind))
        if size is GONE and out["route"] != "needs-size":
            bad.append(("missing size not needs-size", kind))
        if out["route"] in ("epic", "needs-size") and (
                out["model"] or out["effort"] or out["ticket_status"] == "Backlog"):
            bad.append(("stop carries a model", out["route"]))
        if out["route"] == "docs" and fac[mod.FACTOR_NAMES.index("risk")] == 2:
            bad.append(("docs at risk 2",))
        if (out["route"] == "workflow" and fac[2] == 2
                and _rank(out["model"]) < _rank(OPUS)):
            bad.append(("risk 2 below Opus", size, kind, docs, fac))
    # (iii) monotonic over the score inputs, size/docs/type fixed
    for (size, kind, docs, fac, legacy, money), rank in cells.items():
        steps = [(size, kind, docs, fac[:i] + (fac[i] + 1,) + fac[i + 1:],
                  legacy, money) for i in range(4) if fac[i] < 2]
        if not legacy:
            steps.append((size, kind, docs, fac, True, money))
        if not money:
            steps.append((size, kind, docs, fac, legacy, True))
        for nxt in steps:
            if cells[nxt] < rank:
                bad.append(("model went down", (size, kind, docs, fac, legacy, money), nxt))
    return bad


OUTPUT_KEYS = (  # literal: the contract, not read back from the module
    "route", "size", "factors", "legacy_points", "score", "model",
    "model_name", "effort", "overrides", "unknown", "ignored",
    "ticket_status", "notify", "suggest_breakdown", "post",
)
ROUTE_FACTS = {  # route -> (ticket_status, notify, suggest_breakdown)
    "workflow": ("Backlog", False, False), "docs": ("Backlog", False, False),
    "mechanical": ("Backlog", False, False),
    "epic": ("Blocked or Parked", True, True),
    "needs-size": ("Blocked or Parked", True, False),
}
MODEL_FACTS = {  # model -> (model_name, effort)
    HAIKU: ("Haiku 5.5", "low"), SONNET: ("Sonnet 5.5", "medium"),
    OPUS: ("Opus 5.5", "high"), FABLE: ("Fable 5.2", "high"),
}
NULL_ON = {  # key -> routes where it is null (and only there)
    "size": {"needs-size"},
    "factors": {"mechanical"}, "legacy_points": {"mechanical"},
    "score": {"mechanical"},
    "model": {"epic", "needs-size"}, "model_name": {"epic", "needs-size"},
    "effort": {"epic", "needs-size"},
}
LISTS = ("overrides", "unknown", "ignored")
ROUTE_MODELS = {  # route -> the models it may carry
    "workflow": (SONNET, OPUS, FABLE), "docs": (SONNET,),
    "mechanical": (HAIKU,), "epic": (None,), "needs-size": (None,),
}
POST_START = {"workflow": "size ", "docs": "size ", "mechanical": "size ",
              "epic": "size ", "needs-size": "size missing; score "}


def _is_int(value):
    return type(value) is int  # pylint: disable=unidiomatic-typecheck


def check_output_shape(mod):
    """Table 8 (iv): every key present, typed and valued per the route table."""
    bad = []
    for size, _k, _d, _f, _l, _m, out in _grid(mod):
        route = out["route"]
        if list(out) != list(OUTPUT_KEYS):
            bad.append(("keys", route, list(out)))
            continue
        if route not in ROUTE_FACTS:
            bad.append(("route", route))
            continue
        for key, routes in NULL_ON.items():
            if (out[key] is None) != (route in routes):
                bad.append(("null", key, route))
        for key in LISTS:
            if not isinstance(out[key], list):
                bad.append(("list", key, route))
        status, notify, breakdown = ROUTE_FACTS[route]
        if out["ticket_status"] != status or out["notify"] is not notify or (
                out["suggest_breakdown"] is not breakdown):
            bad.append(("route facts", route))
        if out["model"] not in ROUTE_MODELS[route]:
            bad.append(("route model", route, out["model"]))
        if out["model"] is not None and (
                (out["model_name"], out["effort"]) != MODEL_FACTS[out["model"]]):
            bad.append(("model facts", out["model"], out["model_name"],
                        out["effort"]))
        if route != "mechanical":
            if not _is_int(out["score"]) or not 0 <= out["score"] <= 11:
                bad.append(("score type", route, out["score"]))
            if not _is_int(out["legacy_points"]) or not (
                    0 <= out["legacy_points"] <= 3):
                bad.append(("legacy_points type", route, out["legacy_points"]))
            if not isinstance(out["factors"], dict) or not all(
                    _is_int(out["factors"].get(n)) and 0 <= out["factors"][n] <= 2
                    for n in ("complexity", "systems", "risk", "ambiguity")):
                bad.append(("factors type", route, out["factors"]))
            elif out["score"] != sum(out["factors"].values()) + (
                    out["legacy_points"]):
                bad.append(("score sum", route, out["score"]))
        if route == "needs-size" and out["size"] is not None:
            bad.append(("needs-size carries a size", out["size"]))
        if route != "needs-size" and out["size"] != size:
            bad.append(("size is not the input size", route, size, out["size"]))
        if not isinstance(out["post"], str) or not out["post"].startswith(
                POST_START[route]):
            bad.append(("post", route, out["post"]))
        elif route != "mechanical":
            fac = out["factors"]
            if isinstance(fac, dict):
                want = (f"score {out['score']} (complexity "
                        f"{fac.get('complexity')}, systems {fac.get('systems')}, "
                        f"risk {fac.get('risk')}, ambiguity "
                        f"{fac.get('ambiguity')})")
                if want not in out["post"]:
                    bad.append(("post breakdown", route, out["post"]))
        if out["model"] in MODEL_FACTS and isinstance(out["post"], str) and (
                f"model {MODEL_FACTS[out['model']][0]}" not in out["post"]):
            bad.append(("post model", route, out["model"], out["post"]))
    return bad


def check_post(mod):
    """The post line names the size, the score with factors, and the model."""
    out = mod.triage(task(size="M", factors=_fac(complexity=1, risk=2)))
    want = ("size M; score 3 (complexity 1, systems 0, risk 2, ambiguity 0); "
            "model Opus 5.5")
    bad = [] if out["post"] == want else [("post", out["post"])]
    out = mod.triage(task(size="L"))
    if "epic: break down" not in out["post"]:
        bad.append(("epic post", out["post"]))
    for size, kind in (("S", "rename"), ("M", "jira-status")):
        out = mod.triage(task(size=size, task_type=kind))
        want = f"size {size}; mechanical: {kind}; model Haiku 5.5"
        if out["post"] != want:
            bad.append(("mechanical post", size, kind, out["post"]))
    return bad


STOP_ROWS = (  # label, task, route, factors, legacy_points, score
    ("epic L, every input counted",
     task(size="L", factors=_fac(complexity=1, systems=1, risk=2, ambiguity=0),
          legacy=True, money=True),
     "epic", _fac(complexity=1, systems=1, risk=2, ambiguity=0), 3, 7),
    ("epic XL, legacy without money or systems",
     task(size="XL", factors=_fac(complexity=2, systems=0, risk=0, ambiguity=1),
          legacy=True),
     "epic", _fac(complexity=2, systems=0, risk=0, ambiguity=1), 1, 4),
    ("epic L with a mechanical type is still scored",
     task(size="L", factors=_fac(complexity=0, systems=2, risk=1, ambiguity=1),
          legacy=True, task_type="rename"),
     "epic", _fac(complexity=0, systems=2, risk=1, ambiguity=1), 2, 6),
    ("epic L docs only is still scored",
     task(size="L", factors=_fac(complexity=1, systems=0, risk=0, ambiguity=0),
          docs_only=True),
     "epic", _fac(complexity=1, systems=0, risk=0, ambiguity=0), 0, 1),
    ("needs-size missing, legacy and systems",
     task(size=GONE, factors=_fac(complexity=1, systems=2, risk=1, ambiguity=0),
          legacy=True),
     "needs-size", _fac(complexity=1, systems=2, risk=1, ambiguity=0), 2, 6),
    ("needs-size invalid, every input unknown",
     task(size="XXL", factors=GONE, legacy=GONE, money=GONE),
     "needs-size", _fac(complexity=2, systems=2, risk=2, ambiguity=2), 3, 11),
    ("needs-size with a mechanical type is still scored",
     task(size=None, factors=_fac(complexity=0, systems=0, risk=2, ambiguity=1),
          task_type="rename"),
     "needs-size", _fac(complexity=0, systems=0, risk=2, ambiguity=1), 0, 3),
)


def check_stop_scores(mod):
    """Decision 12: epic and needs-size still compute score, factors, points."""
    bad = []
    for label, given, route, factors, points, score in STOP_ROWS:
        out = mod.triage(given)
        got = (out["route"], out["factors"], out["legacy_points"], out["score"])
        if got != (route, factors, points, score):
            bad.append((label, got))
    return bad


TABLES = {fn.__name__: fn for fn in (
    check_factor_table, check_legacy_table, check_bands, check_overrides,
    check_size_table, check_mechanical, check_unknowns, check_grid,
    check_output_shape, check_post, check_stop_scores)}


def violations(mod):
    """Every table's violations against `mod`."""
    out = []
    for fn in TABLES.values():
        out.extend(fn(mod))
    return out


@pytest.mark.parametrize("name", sorted(TABLES))
def test_the_table_holds(name):
    assert TABLES[name](T) == []


@pytest.mark.parametrize("name,value", list(itertools.product(
    ("complexity", "systems", "risk", "ambiguity"), (0, 1, 2))),
    ids=str)
def test_one_factor_case(name, value):
    out = T.triage(task(factors={name: value}))
    assert out["score"] == value and out["factors"][name] == value


@pytest.mark.parametrize("legacy,money,systems,points", LEGACY_ROWS)
def test_one_legacy_row(legacy, money, systems, points):
    out = T.triage(task(factors={"systems": systems}, legacy=legacy,
                        money=money))
    assert out["legacy_points"] == points and out["score"] == systems + points


@pytest.mark.parametrize("score,model", BAND_ROWS)
def test_one_band_row(score, model):
    out = T.triage(task(factors=_factors_for(score)))
    assert out["score"] == score and out["model"] == model


def test_a_raising_factors_object_is_never_read_on_the_mechanical_route():
    out = T.triage(_booby_task("rename"))
    assert out["route"] == "mechanical" and out["model"] == HAIKU


# --- sabotage: each weakened copy must fail a table -------------------------

MUTATIONS = (
    ("six is not Fable (>= 6 to > 6)",
     "if score >= FABLE_AT:", "if score > FABLE_AT:"),
    ("three is not Opus (>= 3 to > 3)",
     "if score >= OPUS_AT:", "if score > OPUS_AT:"),
    ("no risk floor",
     'if factors["risk"] == 2 and RANK[model] < RANK[OPUS]:',
     'if False and RANK[model] < RANK[OPUS]:'),
    ("risk floor as a cap",
     "RANK[model] < RANK[OPUS]:", "RANK[model] > RANK[OPUS]:"),
    ("legacy and money adds nothing",
     "return 1 + (1 if money else 0) + ", "return 1 + "),
    ("legacy and multi-system adds nothing",
     "+ (1 if systems >= 1 else 0)", "+ 0"),
    ("multi-system needs two or more besides",
     "systems >= 1", "systems >= 2"),
    ("a missing factor scores 0", "return 2, False", "return 0, False"),
    ("a missing legacy counts as false",
     '_flag(_field(task, "legacy"), True)', '_flag(_field(task, "legacy"), False)'),
    ("a missing money counts as false",
     '_flag(_field(task, "money"), True)', '_flag(_field(task, "money"), False)'),
    ("an unknown size is S",
     'size = _size(_field(task, "size"))',
     'size = _size(_field(task, "size")) or "S"'),
    ("docs beats risk 2",
     'elif docs_only and factors["risk"] < 2:', "elif docs_only:"),
    ("L is runnable", 'EPIC_SIZES = ("L", "XL")', 'EPIC_SIZES = ("XL",)'),
    ("mechanical match is case-insensitive",
     "and task_type in MECHANICAL", "and task_type.lower() in MECHANICAL"),
    ("mechanical match is a substring",
     "and task_type in MECHANICAL",
     "and any(m in task_type for m in MECHANICAL)"),
    ("mechanical before epic",
     "if size in RUNNABLE and is_mech:",
     "if (size in RUNNABLE or size in EPIC_SIZES) and is_mech:"),
    ("mechanical before needs-size",
     "if size in RUNNABLE and is_mech:",
     "if (size in RUNNABLE or size is None) and is_mech:"),
    ("mechanical ignores the size",
     "if size in RUNNABLE and is_mech:", "if is_mech:"),
    ("mechanical returns a computed score",
     'pick(HAIKU, "mechanical", ["mechanical"], extra)',
     'pick(HAIKU, "mechanical", ["mechanical"], extra)\n'
     '        out.update(score=0, factors={}, legacy_points=0)'),
    ("a malformed flag counts as false",
     "    return unknown_as, False", "    return bool(value), False"),
    ("a sized route reports a fixed size",
     "ticket_status=BACKLOG, size=size)", 'ticket_status=BACKLOG, size="L")'),
    ("the epic post drops the factor breakdown",
     'post=f"size {size}; {scored}; epic: break down")',
     'post=f"size {size}; epic: break down")'),
    ("mechanical route is never taken",
     "if size in RUNNABLE and is_mech:",
     "if size in RUNNABLE and is_mech and False:"),
    ("epic is not parked", "ticket_status=PARKED, notify=True, "
     "suggest_breakdown=True,", "ticket_status=BACKLOG, notify=True, "
     "suggest_breakdown=True,"),
    ("docs rejection is not recorded",
     'overrides.append("docs-rejected-risk")', "pass"),
    ("a mechanical type is dropped from the set",
     '"ticket-update", ', ""),
    ("mechanical scores the factors first",
     "    if size in RUNNABLE and is_mech:",
     '    _factors(_field(task, "factors"))\n    if size in RUNNABLE and is_mech:'),
    ("score is a string",
     "out.update(factors=factors, legacy_points=points, score=score)",
     "out.update(factors=factors, legacy_points=points, score=str(score))"),
    ("model name is wrong", "model_name=NAME[model],", 'model_name="Opus",'),
    ("the docs post drops the model",
     'out["post"] = f"size {size}; {scored}; model {NAME[SONNET]}"',
     'out["post"] = f"size {size}; {scored}"'),
    ("the workflow post drops the model",
     'out["post"] = f"size {size}; {scored}; model {NAME[model]}{note}"',
     'out["post"] = f"size {size}; {scored}{note}"'),
    ("the mechanical post drops the model",
     'f"model {NAME[HAIKU]}")', 'f"model")'),
    ("needs-size does not notify",
     'unknown=unknown + ["size"] + extra, ticket_status=PARKED,\n'
     '                   notify=True,',
     'unknown=unknown + ["size"] + extra, ticket_status=PARKED,\n'
     '                   notify=False,'),
    ("a missing docs_only counts as true",
     '_flag(_field(task, "docs_only"), False)', '_flag(_field(task, "docs_only"), True)'),
    ("the mechanical post drops the task type",
     'f"size {size}; mechanical: {task_type}; "', 'f"size {size}; "'),
    # zeroed before scoring, so score, factors, points and post stay
    # consistent with each other and only the input tables can tell
    ("epic does not score its inputs",
     '    points = legacy_points(legacy, money, factors["systems"])',
     '    if size in EPIC_SIZES:\n'
     '        factors, legacy = dict.fromkeys(FACTOR_NAMES, 0), False\n'
     '    points = legacy_points(legacy, money, factors["systems"])'),
    ("needs-size does not score its inputs",
     '    points = legacy_points(legacy, money, factors["systems"])',
     '    if size is None:\n'
     '        factors, legacy = dict.fromkeys(FACTOR_NAMES, 0), False\n'
     '    points = legacy_points(legacy, money, factors["systems"])'),
)


def _variant(old, new):
    text = source()
    assert text.count(old) == 1, f"mutation target moved or repeated: {old!r}"
    mutated = text.replace(old, new)
    assert mutated != text, "a no-op mutation proves nothing"
    name = "crew_triage_mutant"
    module = types.ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(mutated, name, "exec"), module.__dict__)  # pylint: disable=exec-used
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.mark.parametrize("label,old,new", MUTATIONS,
                         ids=[m[0] for m in MUTATIONS])
def test_a_weakened_rule_is_caught(label, old, new):
    assert violations(_variant(old, new)), "nothing caught: " + label


# --- CLI ----------------------------------------------------------------------

def _cli(*args):
    return subprocess.run([sys.executable, MODULE, *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=60, check=False)


def test_the_cli_prints_the_triage():
    done = _cli("triage", json.dumps(task(size="M", factors={"risk": 2})))
    assert done.returncode == 0
    assert json.loads(done.stdout)["model"] == OPUS
    assert done.stdout == json.dumps(json.loads(done.stdout), indent=2) + "\n"


@pytest.mark.parametrize("arg", [
    "{not json", "[1, 2]", "3", "null", '"x"', '{"size":"S","unused":NaN}',
    '{"size":"S","unused":Infinity}', '{"size":"S","unused":-Infinity}',
    "[" * 20000])
def test_the_cli_refuses_a_non_object(arg):
    done = _cli("triage", arg)
    assert done.returncode == 2 and done.stdout == ""


def test_the_cli_refuses_no_arguments():
    done = _cli()
    assert done.returncode == 2 and done.stdout == ""


def test_the_cli_prints_the_tables():
    done = _cli("tables")
    assert done.returncode == 0
    lines = done.stdout.splitlines()
    for line in (  # the artifact's rows, literally
            "  S, M   run through the workflow",
            "  L, XL  epic: break down, ticket Blocked or Parked, notify",
            "  other  needs-size: ticket Blocked or Parked, notify",
            "  legacy                        +1",
            "  legacy and money              +1 more",
            "  legacy and 2+ systems         +1 more",
            "  score 0-2                   Sonnet 5.5",
            "  score 3-5                   Opus 5.5",
            "  score 6+                    Fable 5.2",
            "  risk 2                        Opus 5.5 at least",
            "  docs only, risk below 2       Sonnet 5.5",
            "Mechanical task types (size S or M): Haiku 5.5"):
        assert line in lines, line
    assert "  " + ", ".join(sorted(MECHANICAL_KINDS)) in lines


def test_triage_refuses_a_non_dict():
    with pytest.raises(TypeError):
        T.triage([1])


# --- purity and inertness -----------------------------------------------------

THIS = "plugin/crew/tests/test_crew_triage.py"
ITSELF = "plugin/crew/hooks/scripts/crew_triage.py"
NAME = "crew_triage"


GIT = shutil.which("git")


def _walk(root):
    """Every file under `root/plugin`, nothing pruned."""
    found = []

    def fail(error):
        raise error  # an unreadable directory is not an empty one

    for base, _dirs, files in os.walk(os.path.join(root, "plugin"),
                                      onerror=fail):
        for fname in files:
            rel = os.path.relpath(os.path.join(base, fname), root)
            found.append(rel.replace(os.sep, "/"))
    return sorted(found)


def _git_env():
    """The environment without GIT_*: an inherited GIT_DIR or GIT_WORK_TREE
    would point the listing at some other repository."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _plugin_files(root, git=GIT):
    """Repo-relative POSIX paths of every file under `plugin/` in `root`.

    `git ls-files -z --cached --others --exclude-standard` (tracked plus
    untracked-not-ignored, NUL-separated so a non-ASCII or odd name is not
    quoted), else a plain walk when git is absent or `root` is not a work tree.
    """
    if git:
        try:
            done = subprocess.run(
                [git, "ls-files", "-z", "--cached", "--others",
                 "--exclude-standard", "plugin/"], cwd=root, env=_git_env(),
                capture_output=True, timeout=120, check=False)
        except (OSError, subprocess.SubprocessError):
            done = None
        if done is not None and done.returncode == 0 and done.stdout:
            names = [n.decode("utf-8", "surrogateescape")
                     for n in done.stdout.split(b"\0") if n]
            return sorted(names)
    return _walk(root)


def _is_regular(path):
    """True for a regular file; a FIFO or device would block a read.

    A stat error propagates: a scan that could not look is not a scan.
    """
    return stat.S_ISREG(os.stat(path).st_mode)


def _own_bytecode(rel):
    """True for the compiled copy of the module or this file (the walk sees
    `__pycache__`, and a .pyc names its own source)."""
    folder, _sep, fname = rel.rpartition("/")
    if not folder.endswith("__pycache__") or not fname.endswith(".pyc"):
        return False
    parent = folder[:-len("__pycache__")]
    stem = fname.split(".", 1)[0]
    return any(parent + stem + ".py" == own for own in (ITSELF, THIS))


def mentions(root, git=GIT):
    """Files under `plugin/` that name the module, bar the two exact paths."""
    hits = []
    for rel in _plugin_files(root, git):
        if rel in (ITSELF, THIS) or _own_bytecode(rel):
            continue
        path = os.path.join(root, rel)
        if not _is_regular(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            if NAME in handle.read():
                hits.append(rel)
    return hits


def test_the_scan_root_is_the_repo_root():
    assert os.path.isdir(os.path.join(REPO, "plugin", "crew"))
    files = _plugin_files(REPO)
    assert ITSELF in files and THIS in files and len(files) > 100
    assert ITSELF in _plugin_files(REPO, git=None)


def test_nothing_under_plugin_mentions_the_module():
    assert mentions(REPO) == [], "inert until R-71/R-73 wire it"


def test_the_scan_sees_a_mention_in_the_plugin_row(tmp_path):
    plugin = tmp_path / "plugin"
    (plugin / "crew" / "hooks" / "scripts").mkdir(parents=True)
    (plugin / "PLUGINS.md").write_text("row mentions crew_triage here\n",
                                       encoding="utf-8")
    (plugin / "crew" / "hooks" / "scripts" / "crew_triage.py").write_text(
        "crew_triage\n", encoding="utf-8")
    assert mentions(str(tmp_path), git=None) == ["plugin/PLUGINS.md"]


def test_the_scan_sees_a_mention_in_a_hook(tmp_path):
    hooks = tmp_path / "plugin" / "crew" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hooks.json").write_text('{"command": "crew_triage"}\n',
                                      encoding="utf-8")
    assert mentions(str(tmp_path), git=None) == [
        "plugin/crew/hooks/hooks.json"]


def test_the_walk_prunes_nothing(tmp_path):
    for part in ("node_modules", "__pycache__"):
        folder = tmp_path / "plugin" / part
        folder.mkdir(parents=True)
        (folder / "x.md").write_text("crew_triage\n", encoding="utf-8")
    assert mentions(str(tmp_path), git=None) == [
        "plugin/__pycache__/x.md", "plugin/node_modules/x.md"]


def test_a_failed_directory_scan_is_an_error_not_a_clean_result(
        tmp_path, monkeypatch):
    (tmp_path / "plugin" / "sub").mkdir(parents=True)
    (tmp_path / "plugin" / "sub" / "a.md").write_text("crew_triage\n",
                                                      encoding="utf-8")
    real = os.scandir

    def denied(path="."):
        if os.fspath(path).endswith("sub"):
            raise PermissionError("denied")
        return real(path)

    monkeypatch.setattr(os, "scandir", denied)
    with pytest.raises(PermissionError):
        mentions(str(tmp_path), git=None)


def test_a_missing_plugin_dir_is_an_error_not_a_clean_result(tmp_path):
    with pytest.raises(OSError):
        mentions(str(tmp_path), git=None)


def test_a_missing_git_falls_back_to_the_walk(tmp_path):
    (tmp_path / "plugin").mkdir()
    (tmp_path / "plugin" / "a.md").write_text("crew_triage\n", encoding="utf-8")
    missing = str(tmp_path / "no-such-git")
    assert _plugin_files(str(tmp_path), git=missing) == ["plugin/a.md"]
    assert mentions(str(tmp_path), git=missing) == ["plugin/a.md"]


def test_a_non_ascii_name_is_scanned_by_git(tmp_path):
    if not GIT:
        pytest.skip("git is not installed")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    (tmp_path / "plugin").mkdir()
    (tmp_path / "plugin" / "caf\u00e9 \u65e5\u672c.md").write_text(
        "crew_triage\n", encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"]):
        done = subprocess.run([GIT, *args], cwd=tmp_path, env=env, timeout=120,
                              capture_output=True, check=False)
        assert done.returncode == 0, done.stderr
    assert mentions(str(tmp_path)) == ["plugin/caf\u00e9 \u65e5\u672c.md"]


def _git_repo(tmp_path):
    """A throwaway repo in `tmp_path`, isolated from the real git config."""
    if not GIT:
        pytest.skip("git is not installed")
    env = _git_env()
    env.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    done = subprocess.run([GIT, "init", "-q"], cwd=tmp_path, env=env,
                          timeout=120, capture_output=True, check=False)
    assert done.returncode == 0, done.stderr
    return env


def test_an_untracked_file_is_scanned_by_git(tmp_path):
    env = _git_repo(tmp_path)
    (tmp_path / "plugin").mkdir()
    (tmp_path / "plugin" / "tracked.md").write_text("x\n", encoding="utf-8")
    done = subprocess.run([GIT, "add", "-A"], cwd=tmp_path, env=env,
                          timeout=120, capture_output=True, check=False)
    assert done.returncode == 0, done.stderr
    (tmp_path / "plugin" / "new.md").write_text("crew_triage\n",
                                                encoding="utf-8")
    assert mentions(str(tmp_path)) == ["plugin/new.md"]


def test_an_inherited_git_dir_does_not_redirect_the_scan(tmp_path,
                                                          monkeypatch):
    here, other = tmp_path / "here", tmp_path / "other"
    for root, fname in ((here, "a.md"), (other, "b.md")):
        root.mkdir()
        env = _git_repo(root)
        (root / "plugin").mkdir()
        (root / "plugin" / fname).write_text("x\n", encoding="utf-8")
        done = subprocess.run([GIT, "add", "-A"], cwd=root, env=env,
                              timeout=120, capture_output=True, check=False)
        assert done.returncode == 0, done.stderr
    # a real second repository, so a leaked GIT_DIR lists ITS files rather
    # than failing into the walk (which would hide the leak)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    assert _plugin_files(str(here)) == ["plugin/a.md"]


def test_the_walk_skips_only_the_own_bytecode(tmp_path):
    cache = tmp_path / "plugin" / "crew" / "hooks" / "scripts" / "__pycache__"
    cache.mkdir(parents=True)
    tests = tmp_path / "plugin" / "crew" / "tests" / "__pycache__"
    tests.mkdir(parents=True)
    for folder, fname in ((cache, "crew_triage.cpython-312.pyc"),
                          (tests, "test_crew_triage.cpython-312-pytest-8.pyc"),
                          (cache, "other.cpython-312.pyc")):
        (folder / fname).write_bytes(b"\0crew_triage\0")
    assert mentions(str(tmp_path), git=None) == [
        "plugin/crew/hooks/scripts/__pycache__/other.cpython-312.pyc"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs here")
def test_a_fifo_is_not_read(tmp_path):
    (tmp_path / "plugin").mkdir()
    getattr(os, "mkfifo")(str(tmp_path / "plugin" / "pipe.md"))
    (tmp_path / "plugin" / "a.md").write_text("crew_triage\n", encoding="utf-8")
    assert mentions(str(tmp_path), git=None) == ["plugin/a.md"]


def test_a_stat_error_fails_the_scan(tmp_path, monkeypatch):
    (tmp_path / "plugin").mkdir()
    (tmp_path / "plugin" / "a.md").write_text("x\n", encoding="utf-8")

    def refuse(_path, *_a, **_k):
        raise PermissionError("simulated")
    monkeypatch.setattr(os, "stat", refuse)
    with pytest.raises(PermissionError):
        mentions(str(tmp_path), git=None)


def test_a_read_error_fails_the_scan(tmp_path, monkeypatch):
    (tmp_path / "plugin").mkdir()
    (tmp_path / "plugin" / "a.md").write_text("x\n", encoding="utf-8")
    real = open

    def refuse(path, *a, **k):
        if str(path).endswith("a.md"):
            raise PermissionError("simulated")
        return real(path, *a, **k)
    monkeypatch.setattr("builtins.open", refuse)
    with pytest.raises(PermissionError):
        mentions(str(tmp_path), git=None)


def test_the_module_is_pure():
    text = source()
    names = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names <= {"json", "sys"}, names
    for banned in ("open(", "subprocess", "os.environ", "urllib", "socket"):
        assert banned not in text, banned


def test_the_module_declares_itself_report_only():
    assert T.REPORT_ONLY is True
    assert "INERT" in source()
