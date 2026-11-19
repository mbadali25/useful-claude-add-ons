"""R-05: the machine-owned tier map, report-only (`crew_tiers`).

Acceptance (docs/plans/crew-revamp-2026-11-18.md, row R-05): the repo can only
narrow; a target the map does not list is unknown. Every fixture is a temp
directory with an explicit machine path; nothing here reads or writes real
config.

Row names follow the R-05 spec (section 5): N narrow/never widen, T-V views,
T-C case and duplicates, T-R readers, T-W writes, T-I inert and consumer
rules. The sabotage tests at the end (spec D7) patch one internal at a time
and assert the named rows then FAIL, so each property is proved red.
"""
import ast
import itertools
import json
import os
import pathlib

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_state
import crew_tiers
import crew_upgrade
from review_fixtures import git
from scope_fixtures import make_repo

REPO = pathlib.Path(context._ROOT).parent.parent  # pylint: disable=protected-access
SETTABLE = ("dev", "qa", "prod")


# --- fixtures --------------------------------------------------------------------------

def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data)
    path.write_text(text, encoding="utf-8")


def _setup(tmp, machine=None, repo=None, machine_raw=None, repo_raw=None):
    """`(root, global_path)`: a repo whose `.crew/config.json` holds `{"tiers":
    repo}` (or `repo_raw` text), and a machine file holding `{"tiers": machine}`
    (or `machine_raw`). A None layer writes no file."""
    tmp = pathlib.Path(tmp)
    root = tmp / "repo"
    (root / ".crew").mkdir(parents=True, exist_ok=True)
    gpath = tmp / "machine.json"
    if machine_raw is not None:
        _write(gpath, machine_raw)
    elif machine is not None:
        _write(gpath, {"tiers": machine})
    if repo_raw is not None:
        _write(root / ".crew" / "config.json", repo_raw)
    elif repo is not None:
        _write(root / ".crew" / "config.json", {"tiers": repo})
    return str(root), str(gpath)


def _entry(tier):
    return {"tier": tier}


def _resolve(tmp, target, **layers):
    root, gpath = _setup(tmp, **layers)
    return crew_tiers.resolve(target, root, gpath)


def _sub(tmp_path, name):
    out = tmp_path / name
    out.mkdir(parents=True, exist_ok=True)
    return out


# --- N: narrow, never widen (the acceptance criterion) ---------------------------------

N_ROWS = {
    # name: (machine tier or None, repo tier or None, expected tier, reason, repoIgnored)
    "N1": ("dev", None, "dev", "listed", False),
    "N2": ("dev", "qa", "qa", "narrowed-by-repo", False),
    "N3": ("dev", "prod", "prod", "narrowed-by-repo", False),
    "N4": ("qa", "dev", "qa", "listed", True),
    "N5": ("prod", "dev", "prod", "listed", True),
    "N6": (None, "dev", "unknown", "unlisted", True),
    "N7": (None, "prod", "unknown", "unlisted", True),
    "N8": (None, None, "unknown", "unlisted", False),
}


def _n_row(tmp, name, kind="workflow"):
    machine_tier, repo_tier, tier, reason, ignored = N_ROWS[name]
    target = f"{kind}:deploy.yml"
    machine = {target: _entry(machine_tier)} if machine_tier else {}
    repo = {target: _entry(repo_tier)} if repo_tier else {}
    root, gpath = _setup(tmp, machine=machine, repo=repo)
    got = crew_tiers.resolve(target, root, gpath)
    assert (got["tier"], got["reason"]) == (tier, reason), (name, kind, got)
    row = crew_tiers.explain_row(root, gpath)
    assert ("repoIgnored" in row and target in row["repoIgnored"]) == ignored, (name, row)
    if ignored:
        assert row["repoIgnored"][target] == _entry(repo_tier)
        assert row["heldDownBy"] == "global"


@pytest.mark.parametrize("kind", crew_tiers.KINDS)
@pytest.mark.parametrize("name", sorted(N_ROWS))
def test_narrow_never_widen(tmp_path, name, kind):
    _n_row(tmp_path, name, kind)


def _property(tmp_path):
    """Every machine value (dev, qa, prod, unlisted) x every repo value (dev,
    qa, prod, none): the effective tier is never wider than the machine's."""
    target = "host:api.example.com"
    for index, (m, r) in enumerate(itertools.product(SETTABLE + (None,), SETTABLE + (None,))):
        got = _resolve(_sub(tmp_path, f"p{index}"), target,
                       machine={target: _entry(m)} if m else {},
                       repo={target: _entry(r)} if r else {})
        floor = m or "unknown"
        assert crew_tiers.RANK[got["tier"]] >= crew_tiers.RANK[floor], (m, r, got)
        if r is not None and m is not None:
            assert got["tier"] == max(m, r, key=crew_tiers.RANK.get), (m, r, got)


def test_property_never_wider_than_the_machine(tmp_path):
    _property(tmp_path)


def test_absent_files_mean_unlisted_and_no_repo(tmp_path):
    got = crew_tiers.resolve("workflow:x", str(tmp_path / "nowhere"),
                             str(tmp_path / "absent.json"))
    assert (got["tier"], got["reason"]) == ("unknown", "unlisted")


# --- T-V: views never show a widened tier ----------------------------------------------

def _t_v1(tmp, monkeypatch):
    target = "workflow:deploy.yml"
    root, gpath = _setup(tmp, machine={target: _entry("qa")}, repo={target: _entry("dev")})
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", gpath)
    row = next(r for r in crew_config.explain_config(root, gpath) if r["path"] == "tiers")
    assert row["value"] == {target: "qa"}
    assert row["heldDownBy"] == "global"
    assert row["repoIgnored"] == {target: _entry("dev")}
    assert crew_config.resolve_config(root)["tiers"][target]["tier"] == "qa"
    return root, gpath


def test_t_v1_explain_and_resolve_config_hold_the_machine_value(tmp_path, monkeypatch):
    _t_v1(tmp_path, monkeypatch)


def test_t_v2_narrowing_shows_in_explain_and_merged_is_a_lower_bound(tmp_path, monkeypatch):
    target = "workflow:deploy.yml"
    root, gpath = _setup(tmp_path, machine={target: _entry("dev")},
                         repo={target: _entry("prod")})
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", gpath)
    row = next(r for r in crew_config.explain_config(root, gpath) if r["path"] == "tiers")
    assert (row["value"], row["source"]) == ({target: "prod"}, "repo+global")
    assert crew_config.resolve_config(root)["tiers"][target]["tier"] == "dev"
    assert crew_tiers.resolve(target, root, gpath)["tier"] == "prod"


def test_t_v2_merged_never_wider_than_crew_tiers_on_the_grid(tmp_path, monkeypatch):
    target = "database:orders"
    for index, (m, r) in enumerate(itertools.product(SETTABLE + (None,), SETTABLE + (None,))):
        root, gpath = _setup(_sub(tmp_path, f"g{index}"),
                             machine={target: _entry(m)} if m else {},
                             repo={target: _entry(r)} if r else {})
        monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", gpath)
        merged = crew_config.resolve_config(root)["tiers"].get(target, {}).get("tier", "unknown")
        effective = crew_tiers.resolve(target, root, gpath)["tier"]
        assert crew_tiers.RANK[merged] <= crew_tiers.RANK[effective], (m, r, merged, effective)
        assert merged == (m or "unknown"), (m, r, merged)


def test_t_v3_explain_text_prints_the_effective_tier(tmp_path, monkeypatch, capsys):
    root, gpath = _t_v1(tmp_path, monkeypatch)
    assert crew_config.main(["--root", root, "--global-path", gpath, "--explain"]) == 0
    out = capsys.readouterr().out
    assert "workflow:deploy.yml  qa  (listed)" in out
    assert "workflow:deploy.yml  dev" not in out


def test_t_v4_repo_tiers_without_a_machine_file_resolves_empty(tmp_path, monkeypatch):
    root, gpath = _setup(tmp_path, repo={"workflow:x": _entry("prod")})
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", gpath)
    assert crew_config.resolve_config(root)["tiers"] == {}


# --- T-C: case and duplicates ----------------------------------------------------------

def _t_c4(tmp):
    root, gpath = _setup(tmp, machine={"workflow:Deploy.yml": _entry("dev")})
    got = crew_tiers.resolve("workflow:deploy.yml", root, gpath)
    assert (got["tier"], got["reason"]) == ("unknown", "unlisted"), got
    assert "case-mismatch: workflow:Deploy.yml" in got["notes"]
    folded_kind = crew_tiers.resolve("WORKFLOW:Deploy.yml", root, gpath)
    assert (folded_kind["tier"], folded_kind["reason"]) == ("dev", "listed")


def test_t_c1_exact_duplicate_key_is_conflicting(tmp_path):
    got = _resolve(tmp_path, "workflow:X", machine_raw=(
        '{"tiers": {"workflow:X": {"tier": "dev"}, "workflow:X": {"tier": "prod"}}}'))
    assert (got["tier"], got["reason"]) == ("unknown", "conflicting")
    assert got["notes"][0].startswith("machine:")


def test_t_c2_case_twins_conflict_and_leave_others_alone(tmp_path):
    root, gpath = _setup(tmp_path, machine={"workflow:Deploy.yml": _entry("dev"),
                                            "workflow:deploy.yml": _entry("dev"),
                                            "host:a": _entry("qa")})
    for target in ("workflow:Deploy.yml", "workflow:deploy.yml"):
        got = crew_tiers.resolve(target, root, gpath)
        assert (got["tier"], got["reason"]) == ("unknown", "conflicting"), got
    assert crew_tiers.resolve("host:a", root, gpath)["reason"] == "listed"


def test_t_c3_twins_after_kind_normalisation(tmp_path):
    got = _resolve(tmp_path, "workflow:X", machine={"workflow:X": _entry("dev"),
                                                    "WORKFLOW:X": _entry("dev")})
    assert (got["tier"], got["reason"]) == ("unknown", "conflicting")


def test_t_c4_name_lookup_is_case_exact_kind_folds(tmp_path):
    _t_c4(tmp_path)


def test_t_c5_repo_case_twins_over_machine_dev(tmp_path):
    got = _resolve(tmp_path, "workflow:x", machine={"workflow:x": _entry("dev")},
                   repo={"workflow:x": _entry("qa"), "workflow:X": _entry("qa")})
    assert (got["tier"], got["reason"]) == ("unknown", "conflicting")
    assert got["notes"][0].startswith("repo:")


@pytest.mark.parametrize("second", ["tiers", "Tiers"])
def test_t_c6_two_top_level_tiers_keys(tmp_path, second):
    raw = ('{"tiers": {"host:a": {"tier": "dev"}}, "%s": {"host:a": {"tier": "dev"}}}'
           % second)
    root, gpath = _setup(tmp_path, machine_raw=raw)
    for target in ("host:a", "host:b"):
        got = crew_tiers.resolve(target, root, gpath)
        assert (got["tier"], got["reason"]) == ("unknown", "conflicting"), got


def test_t_c7_twins_elsewhere_in_the_file_change_no_tier(tmp_path):
    raw = ('{"guards": {}, "guards": {"profile": "off"}, '
           '"pm": {"authority": "act", "Authority": "x"}, '
           '"tiers": {"host:a": {"tier": "dev"}}}')
    got = _resolve(tmp_path, "host:a", machine_raw=raw)
    assert (got["tier"], got["reason"]) == ("dev", "listed")


def test_t_c8_twins_of_tier_inside_an_entry(tmp_path):
    got = _resolve(tmp_path, "host:a", machine_raw=(
        '{"tiers": {"host:a": {"tier": "dev", "Tier": "prod"}}}'))
    assert (got["tier"], got["reason"]) == ("unknown", "conflicting")


def test_t_c9_globs_are_literal(tmp_path):
    root, gpath = _setup(tmp_path, machine={"workflow:*": _entry("dev")})
    got = crew_tiers.resolve("workflow:deploy.yml", root, gpath)
    assert (got["tier"], got["reason"]) == ("unknown", "unlisted")
    assert crew_tiers.resolve("workflow:*", root, gpath)["tier"] == "dev"


# --- shape -----------------------------------------------------------------------------

@pytest.mark.parametrize("entry", [{"tier": "staging"}, {"tier": "unknown"}, "dev",
                                   {"tier": None}, {}, ["dev"]])
def test_bad_machine_entry_is_invalid(tmp_path, entry):
    got = _resolve(tmp_path, "host:a", machine={"host:a": entry})
    assert (got["tier"], got["reason"]) == ("unknown", "invalid")


def test_unknown_kind_is_invalid(tmp_path):
    root, gpath = _setup(tmp_path, machine={"server:a": _entry("dev")})
    got = crew_tiers.resolve("server:a", root, gpath)
    assert (got["tier"], got["reason"]) == ("unknown", "invalid")
    assert [r["reason"] for r in crew_tiers.resolve_all(root, gpath)] == ["invalid"]


def test_repo_invalid_entry_over_machine_dev(tmp_path):
    got = _resolve(tmp_path, "host:a", machine={"host:a": _entry("dev")},
                   repo={"host:a": {"tier": "staging"}})
    assert (got["tier"], got["reason"]) == ("unknown", "repo-invalid-entry")


def test_extra_and_later_fields_are_notes(tmp_path):
    got = _resolve(tmp_path, "account:123", machine={"account:123": {
        "tier": "qa", "application": "billing", "accounts": ["1"], "owner": "me"}})
    assert (got["tier"], got["reason"]) == ("qa", "listed")
    assert "machine: application: not read until R-A1" in got["notes"]
    assert "machine: accounts: not read until R-A1" in got["notes"]
    assert any("unknown field 'owner'" in note for note in got["notes"])


# --- T-R: readers ----------------------------------------------------------------------

def _t_r2(tmp):
    for index, raw in enumerate(("{not json", "[]", '{"tiers": "dev"}')):
        root, gpath = _setup(_sub(tmp, f"r{index}"), machine_raw=raw,
                             repo={"host:a": _entry("prod")})
        for target in ("host:a", "workflow:b"):
            got = crew_tiers.resolve(target, root, gpath)
            assert (got["tier"], got["reason"]) == ("unknown", "machine-unreadable"), (raw, got)


def test_t_r1_no_machine_file_is_unlisted(tmp_path):
    got = _resolve(tmp_path, "host:a", repo={"host:a": _entry("prod")})
    assert (got["tier"], got["reason"]) == ("unknown", "unlisted")


def test_t_r2_malformed_machine_file_is_machine_unreadable(tmp_path):
    _t_r2(tmp_path)


def test_a_null_map_is_no_map(tmp_path):
    """`tiers: null` is what `--set tiers=null` writes and `null_means` calls
    unset: no map, so every target is unlisted (still `unknown`)."""
    got = _resolve(tmp_path, "host:a", machine_raw='{"tiers": null}',
                   repo={"host:a": _entry("dev")})
    assert (got["tier"], got["reason"]) == ("unknown", "unlisted")


def test_t_r3_malformed_repo_file_and_absent_repo_file(tmp_path):
    got = _resolve(_sub(tmp_path, "a"), "host:a", machine={"host:a": _entry("dev")},
                   repo_raw="{oops")
    assert (got["tier"], got["reason"]) == ("unknown", "repo-unreadable")
    got = _resolve(_sub(tmp_path, "b"), "host:a", machine={"host:a": _entry("dev")})
    assert (got["tier"], got["reason"]) == ("dev", "listed")


def test_bom_is_read(tmp_path):
    root, gpath = _setup(tmp_path)
    pathlib.Path(gpath).write_bytes(b"\xef\xbb\xbf" + json.dumps(
        {"tiers": {"host:a": _entry("qa")}}).encode())
    assert crew_tiers.resolve("host:a", root, gpath)["tier"] == "qa"


def test_t_r4_linked_worktree_reads_the_main_checkouts_repo_file(tmp_path):
    main = make_repo(tmp_path, mode=None, name="main")
    (main / ".crew" / "config.json").write_text(
        json.dumps({"tiers": {"host:a": _entry("prod")}}), encoding="utf-8")
    git(main, "worktree", "add", "-q", "-b", "lane", str(tmp_path / "wt"))
    gpath = tmp_path / "machine.json"
    _write(gpath, {"tiers": {"host:a": _entry("dev")}})
    got = crew_tiers.resolve("host:a", str(tmp_path / "wt"), str(gpath))
    assert (got["tier"], got["reason"]) == ("prod", "narrowed-by-repo")


# --- T-W: writes -----------------------------------------------------------------------

DOTTED_MAP = {"workflow:deploy.yml": _entry("qa"), "host:api.example.com": _entry("prod")}


def _t_w1(tmp):
    path = pathlib.Path(tmp) / "machine.json"
    crew_config.write_global_config({"tiers": DOTTED_MAP}, path=str(path))
    assert json.loads(path.read_text(encoding="utf-8"))["tiers"] == DOTTED_MAP
    for target, tier in (("workflow:deploy.yml", "qa"), ("host:api.example.com", "prod")):
        got = crew_tiers.resolve(target, None, str(path))
        assert (got["tier"], got["reason"]) == (tier, "listed")


def test_t_w1_global_write_keeps_dotted_targets(tmp_path):
    _t_w1(tmp_path)


def test_t_w2_repo_write_keeps_dotted_targets_and_narrows(tmp_path):
    root, gpath = _setup(tmp_path, machine={"workflow:deploy.yml": _entry("dev")},
                         repo_raw=json.dumps({"tracker": "files"}))
    crew_config.write_repo_config(root, {"tiers": {"workflow:deploy.yml": _entry("qa")}},
                                  gpath)
    written = json.loads((pathlib.Path(root) / ".crew" / "config.json").read_text("utf-8"))
    assert written["tiers"] == {"workflow:deploy.yml": _entry("qa")}
    got = crew_tiers.resolve("workflow:deploy.yml", root, gpath)
    assert (got["tier"], got["reason"]) == ("qa", "narrowed-by-repo")


def test_t_w3_cli_set_round_trips(tmp_path):
    root, gpath = _setup(tmp_path)
    assert crew_config.main(["--root", root, "--global-path", gpath, "--set",
                             "tiers=" + json.dumps(DOTTED_MAP), "--apply"]) == 0
    assert json.loads(pathlib.Path(gpath).read_text("utf-8"))["tiers"] == DOTTED_MAP
    assert crew_tiers.resolve("host:api.example.com", root, gpath)["tier"] == "prod"
    # The profile the write refreshed holds the map whole, never split on `.`.
    profile = json.loads(pathlib.Path(crew_config.profile_path(gpath)).read_text("utf-8"))
    assert profile["global"]["values"] == {"tiers": DOTTED_MAP}


def test_rebuild_from_the_profile_restores_a_dotted_map(tmp_path):
    root, gpath = _setup(tmp_path)
    assert crew_config.main(["--root", root, "--global-path", gpath, "--set",
                             "tiers=" + json.dumps(DOTTED_MAP), "--apply"]) == 0
    text, _changes, _notes = crew_config.plan_rebuild(root, "machine", global_path=gpath)
    assert json.loads(text)["tiers"] == DOTTED_MAP


@pytest.mark.parametrize("argv", [
    ["--set", 'tiers.workflow:deploy.yml.tier="qa"'],
    ["--set", 'tiers.host.tier="qa"'],
    ["--unset", "tiers.x"],
])
def test_t_w4_paths_under_tiers_are_refused(tmp_path, capsys, argv):
    root, gpath = _setup(tmp_path, machine={"host:a": _entry("dev")})
    before = pathlib.Path(gpath).read_bytes()
    assert crew_config.main(["--root", root, "--global-path", gpath] + argv
                            + ["--apply"]) == 2
    assert crew_config.OPAQUE_REFUSAL in capsys.readouterr().err
    assert pathlib.Path(gpath).read_bytes() == before


def test_t_w4_planner_refuses_a_path_under_tiers(tmp_path):
    with pytest.raises(crew_config.GlobalWriteRefused, match="written whole"):
        crew_config.plan_global_write({"tiers.host:a": _entry("qa")},
                                      str(tmp_path / "m.json"))


def test_t_w4_unset_tiers_removes_the_map(tmp_path):
    root, gpath = _setup(tmp_path, machine_raw=json.dumps(
        {"tiers": DOTTED_MAP, "pm": {"authority": "act"}}))
    assert crew_config.main(["--root", root, "--global-path", gpath, "--unset", "tiers",
                             "--apply"]) == 0
    assert json.loads(pathlib.Path(gpath).read_text("utf-8")) == {"pm": {"authority": "act"}}


def test_t_w4_set_tiers_to_a_non_object_is_refused(tmp_path):
    with pytest.raises(crew_config.GlobalWriteRefused, match="whole map"):
        crew_config.plan_global_write({"tiers": "dev"}, str(tmp_path / "m.json"))


def test_t_w4_readers_and_mergers_keep_a_dotted_map_verbatim():
    cfg = {"tiers": DOTTED_MAP}
    assert crew_config.filter_global(cfg)[0]["tiers"] == DOTTED_MAP
    discarded = []
    merged = crew_state.merge_defaults(crew_config.default_config(), cfg, discarded)
    assert (merged["tiers"], discarded) == (DOTTED_MAP, [])
    out, _notes = crew_upgrade.upgrade_config(
        dict(crew_config.default_config(), tiers=DOTTED_MAP))
    assert out["tiers"] == DOTTED_MAP


def _t_w5():
    for fn in (crew_config.assignments, crew_config.leaf_updates):
        assert fn({"tiers": DOTTED_MAP}) == [("tiers", DOTTED_MAP)], fn.__name__


def test_t_w5_one_unit_path_tiers():
    _t_w5()


# --- upgrade ---------------------------------------------------------------------------

def test_upgrade_keeps_a_map_and_writes_no_empty_block():
    """`tiers` is in `CONFIG_BLOCKS`, so a map is carried through the merge
    verbatim and a non-object is reported, not discarded. An ABSENT `tiers`
    stays absent: `upgrade_config` never writes a block that comes back empty
    for a key the file did not mention (crew_upgrade.py, "A block the repo
    never mentioned"), and absent and `{}` resolve the same (every target
    unknown). Deviation from the R-05 spec's "gains `tiers: {}`", recorded on
    CLDDEV-19."""
    bare = crew_config.default_config()
    bare.pop("tiers")
    out, _notes = crew_upgrade.upgrade_config(bare)
    assert "tiers" not in out
    out, _notes = crew_upgrade.upgrade_config(dict(bare, tiers={}))
    assert out["tiers"] == {}
    out, _notes = crew_upgrade.upgrade_config(dict(bare, tiers=DOTTED_MAP))
    assert out["tiers"] == DOTTED_MAP
    out, notes = crew_upgrade.upgrade_config(dict(bare, tiers="dev"))
    assert (out["tiers"], "tiers" in notes["unmigrated"]) == ("dev", True)


def _imports(path):
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_crew_upgrade_still_does_not_import_crew_config():
    assert "crew_config" not in _imports(crew_upgrade.__file__)


# --- T-I: inert, and the consumer rule -------------------------------------------------

def _is_test(path):
    parts = path.relative_to(REPO).parts
    return ("tests" in parts or "_test" in parts or path.name.startswith("test_")
            or path.name in ("conftest.py",))


def _python_files():
    for top in ("plugin", "scripts"):
        for path in sorted((REPO / top).rglob("*.py")):
            if not _is_test(path):
                yield path


def _tiers_imports(tree):
    """`(node, enclosing function names)` for each import of crew_tiers."""
    found = []

    def visit(node, stack):
        hit = (isinstance(node, ast.Import)
               and any(a.name == "crew_tiers" for a in node.names)) or (
                   isinstance(node, ast.ImportFrom) and node.module == "crew_tiers") or (
                   isinstance(node, ast.Call) and any(
                       isinstance(arg, ast.Constant) and arg.value == "crew_tiers"
                       for arg in node.args) and (
                       getattr(node.func, "attr", None) == "import_module"
                       or getattr(node.func, "id", None) in ("__import__", "import_module")))
        if hit:
            found.append((node, tuple(stack)))
        here = stack + [node.name] if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else stack
        for child in ast.iter_child_nodes(node):
            visit(child, here)

    visit(tree, [])
    return found


def _t_i1():
    bad = []
    for path in _python_files():
        if path.name == "crew_tiers.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node, stack in _tiers_imports(tree):
            if path.name == "crew_config.py" and stack == ("explain_config",):
                continue
            bad.append(f"{path.relative_to(REPO)}:{node.lineno} in {stack or 'module'}")
    texts = []
    for pattern in ("plugin/**/hooks.json", "plugin/**/*.sh", "plugin/**/*.ps1",
                    "plugin/crew/commands/*.md", "plugin/**/SKILL.md"):
        texts.extend(p for p in REPO.glob(pattern) if not _is_test(p))
    for path in texts:
        if "crew_tiers" in path.read_text(encoding="utf-8", errors="replace"):
            bad.append(f"{path.relative_to(REPO)} names crew_tiers")
    assert bad == [], bad


def test_t_i1_nothing_that_decides_imports_or_invokes_crew_tiers():
    _t_i1()


def test_t_i1_the_one_import_is_inside_explain_config():
    tree = ast.parse(pathlib.Path(crew_config.__file__).read_text(encoding="utf-8"))
    assert [stack for _n, stack in _tiers_imports(tree)] == [("explain_config",)]


_T_I2_ALLOWED = ("crew_tiers.py", "crew_config.py", "crew_keys.py", "crew_state.py",
                 "crew_upgrade.py", "config_reference.py")


def _reads_tiers(node):
    def is_tiers(value):
        return isinstance(value, ast.Constant) and value.value == "tiers"
    if isinstance(node, ast.Subscript) and is_tiers(node.slice):
        return True
    if isinstance(node, ast.Call) and node.args:
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if name in ("get", "pop", "setdefault") and isinstance(node.func, ast.Attribute):
            return is_tiers(node.args[0])
        if name == "_dig" and len(node.args) > 1 and isinstance(node.args[1], ast.Tuple):
            elts = node.args[1].elts
            return bool(elts) and is_tiers(elts[0])
    return False


def test_t_i2_no_consumer_reads_a_merged_tiers_value():
    bad = []
    for path in _python_files():
        if path.name in _T_I2_ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bad.extend(f"{path.relative_to(REPO)}:{n.lineno}"
                   for n in ast.walk(tree) if _reads_tiers(n))
    assert bad == [], bad


def test_t_i2_scan_sees_each_read_shape():
    for text in ('cfg["tiers"]', 'cfg.get("tiers", {})', 'cfg.pop("tiers")',
                 'cfg.setdefault("tiers", {})', '_dig(cfg, ("tiers", "x"))'):
        assert any(_reads_tiers(n) for n in ast.walk(ast.parse(text))), text


def test_t_i3_crew_tiers_calls_no_lenient_reader():
    tree = ast.parse(pathlib.Path(crew_tiers.__file__).read_text(encoding="utf-8"))
    called = {getattr(n.func, "attr", None) or getattr(n.func, "id", None)
              for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert called.isdisjoint({"read_global_config", "load_config", "strict_pairs"})
    assert "crew_config" not in {a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                                 and n.col_offset == 0 for a in n.names}


def test_resolve_config_does_not_load_crew_tiers(tmp_path):
    """D6: the SessionStart path (`resolve_config`) never imports crew_tiers."""
    import subprocess  # pylint: disable=import-outside-toplevel
    import sys  # pylint: disable=import-outside-toplevel
    code = ("import sys, crew_config; crew_config.resolve_config(sys.argv[1]); "
            "print('crew_tiers' in sys.modules)")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        [os.path.join(context._ROOT, "hooks", "scripts"),  # pylint: disable=protected-access
         os.path.join(context._ROOT, "skills", "crew-graph", "scripts")]))  # pylint: disable=protected-access
    out = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True,
                         text=True, env=env, check=True, timeout=60)
    assert out.stdout.strip() == "False"


# --- CLI -------------------------------------------------------------------------------

def test_cli_explain_and_list(tmp_path, capsys):
    root, gpath = _setup(tmp_path, machine=DOTTED_MAP)
    assert crew_tiers.main(["explain", "workflow:deploy.yml", "--root", root,
                            "--global-path", gpath]) == 0
    assert "workflow:deploy.yml  qa  (listed)" in capsys.readouterr().out
    assert crew_tiers.main(["list", "--json", "--root", root, "--global-path", gpath]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [r["target"] for r in listed] == sorted(DOTTED_MAP)
    with pytest.raises(SystemExit) as exc:
        crew_tiers.main(["nonsense"])
    assert exc.value.code == 2


# --- sabotage (D7): each patch turns the named rows red --------------------------------

def _fails(row, *args):
    with pytest.raises(AssertionError):
        row(*args)


def test_sabotage_combine_returns_the_repo_value(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_tiers, "_combine", lambda m, r: m if r is None else r)
    _fails(_property, _sub(tmp_path, "prop"))
    _fails(_n_row, _sub(tmp_path, "n4"), "N4")


def test_sabotage_machine_value_dev_for_unlisted(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_tiers, "_machine_value",
                        lambda found: "dev" if found is None else found[1]["tier"])
    _fails(_n_row, tmp_path, "N8")


def test_sabotage_lenient_reader(tmp_path, monkeypatch):
    real = crew_tiers._read_layer  # pylint: disable=protected-access

    def lenient(path):
        status, parsed = real(path)
        return ("ok", crew_tiers._pairs([])) if status == "unreadable" else (status, parsed)  # pylint: disable=protected-access
    monkeypatch.setattr(crew_tiers, "_read_layer", lenient)
    _fails(_t_r2, tmp_path)


def test_sabotage_lookup_folds_names(tmp_path, monkeypatch):
    def folding(layer, target):
        for key, entry in layer["map"].items():
            if key.lower() == target.lower():
                return key, entry
        return None
    monkeypatch.setattr(crew_tiers, "_lookup", folding)
    _fails(_t_c4, tmp_path)


def test_sabotage_without_repo_tiers_is_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_config, "_without_repo_tiers", lambda cfg: cfg)
    _fails(_t_v1, tmp_path, monkeypatch)


def test_sabotage_opaque_table_removed(monkeypatch):
    monkeypatch.setattr(crew_config, "_OPAQUE_TABLES", ())
    _fails(_t_w5)
