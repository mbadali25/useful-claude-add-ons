"""The writers, `explain` and `status` for `guards.profile` and
`guards.overrides` (L-0725).

A legacy `guards.<name>` is still READ (until `/crew:migrate`) and never
WRITTEN; a profile change that widens a guard says so once per guard; the
unmigrated state is reported rather than guessed at.
"""
import json

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_state
import crew_status

NAMES = crew_state.ALL_GUARD_NAMES


def _repo(tmp_path, cfg=None):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    body = {"schema": crew_state.SCHEMA_CURRENT}
    body.update(cfg or {})
    (root / ".crew" / "config.json").write_text(json.dumps(body), encoding="utf-8")
    return str(root)


def _machine(tmp_path, cfg=None):
    path = tmp_path / "global.json"
    if cfg is not None:
        path.write_text(json.dumps(cfg), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("layer", ["machine", "repo"])
@pytest.mark.parametrize("name", NAMES)
def test_value_allowed_refuses_a_legacy_guard_key_and_names_the_override(layer, name):
    reason = crew_config.value_allowed(f"guards.{name}", layer, "block")

    assert reason is not None
    assert f"guards.overrides.{name}" in reason


@pytest.mark.parametrize("layer", ["machine", "repo"])
@pytest.mark.parametrize("profile", ["off", "standard", "strict"])
def test_value_allowed_accepts_every_profile(layer, profile):
    assert crew_config.value_allowed("guards.profile", layer, profile) is None


@pytest.mark.parametrize("layer", ["machine", "repo"])
@pytest.mark.parametrize("bad", ["loud", "", 1, ["strict"]])
def test_value_allowed_refuses_a_bad_profile(layer, bad):
    assert crew_config.value_allowed("guards.profile", layer, bad) is not None


@pytest.mark.parametrize("layer", ["machine", "repo"])
@pytest.mark.parametrize("name,good,bad", [
    ("forcePush", "ask", "report"), ("prodDatabase", "read", "ask"),
    ("roleWrites", "report", "ask"), ("cloudGuard", "off", "allow"),
    ("envGuard", "block", "full")])
def test_value_allowed_checks_an_override_against_that_guards_tiers(layer, name, good, bad):
    assert crew_config.value_allowed(f"guards.overrides.{name}", layer, good) is None
    assert crew_config.value_allowed(f"guards.overrides.{name}", layer, bad) is not None


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_value_allowed_refuses_an_override_for_a_name_that_is_not_a_guard(layer):
    reason = crew_config.value_allowed("guards.overrides.bogus", layer, "block")

    assert reason is not None and "not a guard" in reason


def test_a_legacy_write_is_refused_by_the_repo_planner(tmp_path):
    root = _repo(tmp_path)

    with pytest.raises(crew_config.RepoWriteRefused) as caught:
        crew_config.plan_repo_write(root, {"guards.forcePush": "block"},
                                    _machine(tmp_path))

    assert "guards.overrides.forcePush" in str(caught.value)


def test_a_legacy_write_is_refused_by_the_machine_planner(tmp_path):
    with pytest.raises(crew_config.GlobalWriteRefused) as caught:
        crew_config.plan_global_write({"guards.adminMerge": "allow"},
                                      _machine(tmp_path))

    assert "guards.overrides.adminMerge" in str(caught.value)


def test_a_legacy_key_riding_in_a_block_is_refused(tmp_path):
    with pytest.raises(crew_config.GlobalWriteRefused):
        crew_config.plan_global_write({"guards": {"forcePush": "allow"}},
                                      _machine(tmp_path))


def test_a_legacy_key_already_in_the_file_does_not_block_an_unrelated_write(tmp_path):
    gpath = _machine(tmp_path, {"guards": {"forcePush": "block"}})

    _, changes = crew_config.plan_global_write({"notify.chatId": "1"}, gpath)

    assert [c["path"] for c in changes] == ["notify.chatId"]


def test_machine_profile_standard_widens_only_the_guard_it_widens(tmp_path):
    _, changes = crew_config.plan_global_write({"guards.profile": "standard"},
                                               _machine(tmp_path))

    widening = {c["path"] for c in changes if c.get("widens")}
    assert widening == {"guards.adminMerge"}
    assert all(c.get("derived") for c in changes if c["path"] != "guards.profile")


def test_machine_profile_standard_prints_one_note_per_widened_guard(tmp_path, capsys):
    crew_config.main(["--global-path", _machine(tmp_path), "--set",
                      'guards.profile="standard"'])

    out = capsys.readouterr().out
    assert out.count("widens to") == 1
    assert "! guards.adminMerge widens to `ask`" in out


def test_narrowing_profile_prints_no_widening(tmp_path):
    gpath = _machine(tmp_path, {"guards": {"profile": "standard"}})

    _, changes = crew_config.plan_global_write({"guards.profile": "strict"}, gpath)

    assert not any(c.get("widens") for c in changes)


def test_machine_override_carries_its_own_widening(tmp_path):
    _, changes = crew_config.plan_global_write(
        {"guards.overrides.forcePush": "allow"}, _machine(tmp_path))

    assert [(c["path"], c["widens"], c["widensTo"]) for c in changes] == [
        ("guards.overrides.forcePush", True, "allow")]


def test_repo_override_widening_is_held_down_by_the_machine(tmp_path, capsys):
    root = _repo(tmp_path)
    gpath = _machine(tmp_path, {"guards": {"profile": "strict"}})

    _, changes = crew_config.plan_repo_write(
        root, {"guards.overrides.adminMerge": "allow"}, gpath)

    assert [(c["widens"], c.get("heldDownBy")) for c in changes] == [(False, "global")]


def test_repo_profile_off_to_standard_marks_the_widened_guard(tmp_path):
    root = _repo(tmp_path, {"guards": {"profile": "off"}})
    gpath = _machine(tmp_path, {"guards": {"profile": "standard"}})

    _, changes = crew_config.plan_repo_write(root, {"guards.profile": "standard"},
                                             gpath)

    assert {c["path"] for c in changes if c.get("widens")} == {"guards.adminMerge"}


def test_explain_lists_profile_overrides_and_each_guard_in_force(tmp_path):
    root = _repo(tmp_path, {"guards": {"profile": "standard",
                                       "overrides": {"adminMerge": "block"}}})

    rows = {r["path"]: r for r in crew_config.explain_config(root, _machine(tmp_path))}

    assert rows["guards.profile"]["value"] == "standard"
    assert rows["guards.overrides"]["value"] == {"adminMerge": "block"}
    assert rows["guards.adminMerge"]["value"] == "block"
    assert rows["guards.roleWrites"]["value"] == "report"
    assert rows["guards.forcePush"]["unmigrated"] == []


def test_explain_prints_unmigrated_when_a_layer_holds_a_legacy_key(tmp_path, capsys):
    root = _repo(tmp_path, {"guards": {"forcePush": "block"}})
    gpath = _machine(tmp_path)

    crew_config.main(["--root", root, "--global-path", gpath, "--explain"])

    out = capsys.readouterr().out
    assert "unmigrated: run /crew:migrate" in out
    assert "repo layer" in out


def test_explain_prints_nothing_about_unmigrated_for_a_migrated_layer(tmp_path, capsys):
    root = _repo(tmp_path, {"guards": {"profile": "standard"}})

    crew_config.main(["--root", root, "--global-path", _machine(tmp_path), "--explain"])

    assert "unmigrated" not in capsys.readouterr().out


def test_status_has_no_guards_line_when_nothing_is_set(tmp_path):
    root = _repo(tmp_path)

    assert crew_status._guards_line(root) is None  # pylint: disable=protected-access


def test_status_prints_profile_and_overrides(tmp_path):
    root = _repo(tmp_path, {"guards": {"profile": "standard",
                                       "overrides": {"adminMerge": "block"}}})

    line = crew_status._guards_line(root)  # pylint: disable=protected-access

    assert line.startswith("guards   profile standard, overrides ")
    assert '"adminMerge": "block"' in line
    assert "unmigrated" not in line


def test_status_says_unmigrated_for_a_legacy_key(tmp_path):
    root = _repo(tmp_path, {"guards": {"forcePush": "block"}})

    line = crew_status._guards_line(root)  # pylint: disable=protected-access

    assert "unmigrated: run /crew:migrate" in line


def test_filter_global_keeps_a_legacy_guard_key_and_does_not_report_it(tmp_path):
    kept, ignored = crew_config.filter_global({"guards": {"forcePush": "allow"}})

    assert kept == {"guards": {"forcePush": "allow"}}
    assert ignored == []


def test_the_menu_offers_the_profile_first_and_an_override_per_guard(tmp_path):
    import crew_config_menu as menu  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path)

    spec = menu.menu_spec(root, "repo", _machine(tmp_path), None)

    rows = [r["path"] for a in spec["areas"] if a["id"] == "guards" for r in a["rows"]
            if r["path"].startswith("guards.")]
    assert rows[0] == "guards.profile"
    assert rows[1:] == [f"guards.overrides.{n}" for n in NAMES]
