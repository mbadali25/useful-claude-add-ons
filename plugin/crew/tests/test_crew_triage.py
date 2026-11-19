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
import subprocess
import sys
import types

import pytest

import context  # noqa: F401  pylint: disable=unused-import

import crew_triage as T  # noqa: E402  pylint: disable=wrong-import-position

SCRIPTS = os.path.dirname(os.path.abspath(T.__file__))
PLUGIN = os.path.dirname(os.path.dirname(SCRIPTS))
REPO = os.path.dirname(PLUGIN)
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
             (8, FABLE))


def _factors_for(score):
    """Factors (risk 0) that sum to `score` <= 6; the rest comes from legacy."""
    left = min(score, 6)
    fac = {}
    for name in ("complexity", "systems", "ambiguity"):
        fac[name] = min(2, left)
        left -= fac[name]
    return fac


def check_bands(mod):
    """Table 3: band edges, with no risk and no legacy."""
    bad = []
    for score, model in BAND_ROWS:
        out = mod.triage(task(factors=_factors_for(score)))
        if out["score"] != min(score, 6) or (
                score <= 6 and out["model"] != model):
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
        ("docs only with risk 2 is a normal ticket",
         task(factors={"risk": 2}, docs_only=True),
         "workflow", OPUS, ["risk-floor"]),
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


def check_mechanical(mod):
    """Table 6: the mechanical set goes to Haiku; size beats type."""
    bad = []
    for kind in sorted(mod.MECHANICAL):
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


ROUTE_FACTS = {  # route -> (ticket_status, notify, suggest_breakdown)
    "workflow": ("Backlog", False, False), "docs": ("Backlog", False, False),
    "mechanical": ("Backlog", False, False),
    "epic": ("Blocked or Parked", True, True),
    "needs-size": ("Blocked or Parked", True, False),
}
NULL_ON = {  # key -> routes where it is null (and only there)
    "size": {"needs-size"},
    "factors": {"mechanical"}, "legacy_points": {"mechanical"},
    "score": {"mechanical"},
    "model": {"epic", "needs-size"}, "model_name": {"epic", "needs-size"},
    "effort": {"epic", "needs-size"},
}
LISTS = ("overrides", "unknown", "ignored")


def check_output_shape(mod):
    """Table 8 (iv): every key present, typed per the route table."""
    bad = []
    for _s, _k, _d, _f, _l, _m, out in _grid(mod):
        route = out["route"]
        if list(out) != list(mod.OUTPUT_KEYS):
            bad.append(("keys", route, list(out)))
            continue
        for key, routes in NULL_ON.items():
            if (out[key] is None) != (route in routes):
                bad.append(("null", key, route))
        for key in LISTS:
            if not isinstance(out[key], list):
                bad.append(("list", key, route))
        status, notify, breakdown = ROUTE_FACTS[route]
        if (out["ticket_status"], out["notify"], out["suggest_breakdown"]) != (
                status, notify, breakdown):
            bad.append(("route facts", route))
        if not isinstance(out["post"], str) or not out["post"]:
            bad.append(("post", route))
        if route == "workflow" and out["effort"] not in ("medium", "high"):
            bad.append(("effort", out["effort"]))
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
    return bad


TABLES = {fn.__name__: fn for fn in (
    check_factor_table, check_legacy_table, check_bands, check_overrides,
    check_size_table, check_mechanical, check_unknowns, check_grid,
    check_output_shape, check_post)}


def violations(mod):
    """Every table's violations against `mod`."""
    out = []
    for fn in TABLES.values():
        out.extend(fn(mod))
    return out


@pytest.mark.parametrize("name", sorted(TABLES))
def test_the_table_holds(name):
    assert TABLES[name](T) == []


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
     "if size in EPIC_SIZES:", "if size in EPIC_SIZES and not is_mech:"),
    ("mechanical before needs-size",
     "elif size is None:", "elif size is None and not is_mech:"),
    ("mechanical returns a computed score",
     "out.update(factors=None, legacy_points=None, score=None)", "pass"),
    ("epic is not parked", "ticket_status=PARKED, notify=True, "
     "suggest_breakdown=True,", "ticket_status=BACKLOG, notify=True, "
     "suggest_breakdown=True,"),
    ("a missing docs_only counts as true",
     '_flag(_field(task, "docs_only"), False)', '_flag(_field(task, "docs_only"), True)'),
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
                          text=True, check=False)


def test_the_cli_prints_the_triage():
    done = _cli("triage", json.dumps(task(size="M", factors={"risk": 2})))
    assert done.returncode == 0
    assert json.loads(done.stdout)["model"] == OPUS


@pytest.mark.parametrize("arg", ["{not json", "[1, 2]", "3", "null", '"x"'])
def test_the_cli_refuses_a_non_object(arg):
    done = _cli("triage", arg)
    assert done.returncode == 2 and done.stdout == ""


def test_the_cli_refuses_no_arguments():
    done = _cli()
    assert done.returncode == 2 and done.stdout == ""


def test_the_cli_prints_the_tables():
    done = _cli("tables")
    assert done.returncode == 0
    for text in ("Sonnet 5.5", "Opus 5.5", "Fable 5.2", "Haiku 5.5", "XL",
                 "needs-size", "rename"):
        assert text in done.stdout


def test_triage_refuses_a_non_dict():
    with pytest.raises(TypeError):
        T.triage([1])


# --- purity and inertness -----------------------------------------------------

THIS = "plugin/crew/tests/test_crew_triage.py"
ITSELF = "plugin/crew/hooks/scripts/crew_triage.py"
NAME = "crew_triage"


def _plugin_files(root, use_git=True):
    """Repo-relative POSIX paths of every file under `plugin/` in `root`."""
    if use_git:
        done = subprocess.run(["git", "ls-files", "plugin/"], cwd=root,
                              capture_output=True, text=True, check=False)
        if done.returncode == 0 and done.stdout.strip():
            return sorted(done.stdout.split("\n")[:-1] if done.stdout.endswith(
                "\n") else done.stdout.split("\n"))
    found = []
    for base, dirs, files in os.walk(os.path.join(root, "plugin")):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__")]
        for fname in files:
            rel = os.path.relpath(os.path.join(base, fname), root)
            found.append(rel.replace(os.sep, "/"))
    return sorted(found)


def mentions(root, use_git=True):
    """Files under `plugin/` that name the module, bar the two exact paths."""
    hits = []
    for rel in _plugin_files(root, use_git):
        if rel in (ITSELF, THIS):
            continue
        try:
            with open(os.path.join(root, rel), encoding="utf-8",
                      errors="replace") as handle:
                if NAME in handle.read():
                    hits.append(rel)
        except OSError:
            continue
    return hits


def test_nothing_under_plugin_mentions_the_module():
    assert mentions(REPO) == [], "inert until R-71/R-73 wire it"


def test_the_scan_sees_a_mention_in_the_plugin_row(tmp_path):
    plugin = tmp_path / "plugin"
    (plugin / "crew" / "hooks" / "scripts").mkdir(parents=True)
    (plugin / "PLUGINS.md").write_text("row mentions crew_triage here\n",
                                       encoding="utf-8")
    (plugin / "crew" / "hooks" / "scripts" / "crew_triage.py").write_text(
        "crew_triage\n", encoding="utf-8")
    assert mentions(str(tmp_path), use_git=False) == ["plugin/PLUGINS.md"]


def test_the_scan_sees_a_mention_in_a_hook(tmp_path):
    hooks = tmp_path / "plugin" / "crew" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hooks.json").write_text('{"command": "crew_triage"}\n',
                                      encoding="utf-8")
    assert mentions(str(tmp_path), use_git=False) == [
        "plugin/crew/hooks/hooks.json"]


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
