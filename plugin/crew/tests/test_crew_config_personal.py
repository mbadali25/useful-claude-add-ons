"""T-0050: the owner's personal keys, combined per key across both layers.

`crew_state.PERSONAL_KEYS` names them and `effective_personal` combines them:
the stricter of the layers that SET a key wins, a silent layer (absent or
`null`) imposes nothing, and an unrecognised value ranks below the floor.
These tests drive the rule three ways: the pure function, `resolve_config`
(what every reader sees) and `crew_autopilot.settings` (the reader that acts
on it). Must-block cases are the ones where a wrong rank would WIDEN what
autopilot may do; must-allow cases are the ones where a silent layer read as
the floor would make the feature inert.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_config
import crew_fixtures
import crew_platform
import crew_state

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, os.pardir, "hooks", "scripts")
CREW_CONFIG = os.path.join(SCRIPTS, "crew_config.py")
TEMPLATE = os.path.join(HERE, os.pardir, "templates", "config.template.json")
GLOBAL_TEMPLATE = os.path.join(HERE, os.pardir, "templates", "global.template.json")
SKILL_MD = os.path.join(HERE, os.pardir, "skills", "crew-setup", "SKILL.md")
CONFIG_MD = os.path.join(HERE, os.pardir, "commands", "config.md")


def _global(tmp_path, monkeypatch, contents=None, raw=None):
    """Point both GLOBAL_CONFIG_PATH names at a scratch file for this test."""
    path = tmp_path / "global" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
    elif contents is not None:
        path.write_text(json.dumps(contents), encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(path))
    return path


def _repo(tmp_path, config):
    return str(crew_fixtures.make_repo(tmp_path, config=config, git=False))


def _layers(tmp_path, monkeypatch, repo_autopilot, global_autopilot):
    """A repo whose file is the template plus `repo_autopilot`, and a global
    file holding `global_autopilot`; either may be None (no block at all)."""
    cfg = crew_config.template_config()
    if repo_autopilot is not None:
        cfg["autopilot"] = repo_autopilot
    _global(tmp_path, monkeypatch,
            None if global_autopilot is None else {"autopilot": global_autopilot})
    return _repo(tmp_path, cfg)


# --- The pure rule -----------------------------------------------------------

EP = crew_state.effective_personal


@pytest.mark.parametrize("repo,glob,want,held", [
    ("human", "self", "human", "repo"),          # global-self-repo-human
    ("risk", "self", "risk", "repo"),            # global-self-repo-risk
    ("self", "human", "human", "global"),        # repo-self-global-human
    (None, "self", "self", None),                # global-self-repo-silent
    ("self", None, "self", None),                # repo alone
    (None, None, "risk", None),                  # neither: default
    ("risk", "risk", "risk", None),              # a tie: the repo's
    (None, "slef", "slef", None),                # a typo is returned raw
    ("self", "slef", "slef", "global"),          # ... and ranks below the floor
    ("slef", "human", "slef", "repo"),
])
def test_effective_personal_tiers_table(repo, glob, want, held):
    assert EP("autopilot.approval", repo, glob, "risk") == (want, held)


def test_effective_personal_mode_and_deploy():
    assert EP("autopilot.mode", "off", "plan", "off") == ("off", "repo")
    assert EP("autopilot.mode", None, "plan", "off") == ("plan", None)
    assert EP("autopilot.mode", True, "plan", "off") == (True, "repo")
    assert EP("autopilot.deploy", "nonprod", "all", "none") == ("nonprod", "repo")
    assert EP("autopilot.deploy", "all", "none", "none") == ("none", "global")


@pytest.mark.parametrize("repo,glob,want", [
    (20, 5, 5),          # global-maxphases-smaller-wins
    (5, 20, 5),
    (None, 7, 7),
    ("x", 7, 7),         # an invalid layer is ignored when the other is valid
    (7, True, 7),        # a bool is not an int here
    (0, 7, 7),
    ("x", "y", "x"),     # neither valid: the repo's raw value, the reader warns
    (None, None, 12),
])
def test_effective_personal_int_min(repo, glob, want):
    assert EP("autopilot.maxPhases", repo, glob, 12)[0] == want


def test_effective_personal_unknown_path_raises():
    with pytest.raises(KeyError):
        EP("autopilot.nope", "a", "b", None)
    with pytest.raises(KeyError):
        EP("guards.forcePush", "allow", "block", "block")


def test_no_key_is_both_personal_and_ratcheted():
    assert not set(crew_state.PERSONAL_KEYS) & set(crew_state.RATCHETED_KEYS)


def test_every_autopilot_key_has_a_personal_row_or_is_repo_only():
    """A later autopilot key (T-0011's `ship`, T-0029's `maxLanes`, ...) fails
    here until its ticket decides how its two layers combine."""
    for key in crew_state.AUTOPILOT_DEFAULTS:
        dotted = f"autopilot.{key}"
        assert (dotted in crew_state.PERSONAL_KEYS) != (
            dotted in crew_state.REPO_ONLY_AUTOPILOT), dotted


def test_every_personal_tier_tuple_is_its_readers():
    """The order is the reader's own vocabulary: a tier the reader does not
    accept would rank as a real tier here and as the floor there."""
    assert crew_state.PERSONAL_KEYS["autopilot.approval"][1] == tuple(
        sorted(crew_autopilot.POLICIES, key=("human", "risk", "self").index))
    assert set(crew_state.PERSONAL_KEYS["autopilot.deploy"][1]) == set(
        crew_autopilot.DEPLOY_VALUES)


# --- Through resolve_config and crew_autopilot.settings ----------------------


def _resolved(root):
    return crew_config.resolve_config(root)["autopilot"]


def test_global_self_repo_human_resolves_human(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, {"approval": "human"}, {"approval": "self"})
    assert _resolved(root)["approval"] == "human"
    assert crew_autopilot.settings(root)["approval"] == "human"


def test_global_self_repo_risk_resolves_risk(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, {"approval": "risk"}, {"approval": "self"})
    assert _resolved(root)["approval"] == "risk"
    assert crew_autopilot.settings(root)["approval"] == "risk"


def test_repo_self_global_human_is_held_down(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, {"approval": "self"}, {"approval": "human"})
    assert _resolved(root)["approval"] == "human"
    assert crew_autopilot.settings(root)["approval"] == "human"
    row = crew_config.resolve_personal(root, "autopilot.approval")
    assert row["heldDownBy"] == "global"
    explained = {r["path"]: r for r in crew_config.explain_config(root)}
    assert explained["autopilot.approval"]["heldDownBy"] == "global"
    assert explained["autopilot.approval"]["value"] == "human"


def test_global_plan_repo_off_resolves_off(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, {"mode": "off"}, {"mode": "plan"})
    assert _resolved(root)["mode"] == "off"
    assert crew_autopilot.settings(root)["armed"] is False


def test_global_typo_reads_human_with_warning(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, None, {"approval": "slef"})
    assert _resolved(root)["approval"] == "slef"
    got = crew_autopilot.settings(root)
    assert got["approval"] == "human"
    assert any("autopilot.approval is 'slef'" in w for w in got["warnings"])


def test_global_typo_over_repo_self_still_reads_human(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, {"approval": "self"}, {"approval": "slef"})
    assert crew_autopilot.settings(root)["approval"] == "human"


def test_global_maxphases_smaller_wins(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, {"maxPhases": 20}, {"maxPhases": 5})
    assert _resolved(root)["maxPhases"] == 5
    assert crew_autopilot.settings(root)["maxPhases"] == 5


def test_global_deploy_all_repo_nonprod_resolves_nonprod(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, {"deploy": "nonprod"}, {"deploy": "all"})
    assert crew_autopilot.settings(root)["deploy"] == "nonprod"


def test_global_self_repo_silent_resolves_self(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, None, {"approval": "self", "mode": "plan"})
    assert _resolved(root)["approval"] == "self"
    got = crew_autopilot.settings(root)
    assert got["approval"] == "self"
    assert got["armed"] is True


def test_global_self_repo_null_resolves_self(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, {"approval": None}, {"approval": "self"})
    assert _resolved(root)["approval"] == "self"
    assert crew_autopilot.settings(root)["approval"] == "self"


def test_global_maxphases_over_silent_repo_is_inherited(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, None, {"maxPhases": 30})
    assert crew_autopilot.settings(root)["maxPhases"] == 30


def test_an_unreadable_repo_file_still_reads_could_not_tell(tmp_path, monkeypatch):
    """A global `self` must not leak through a repo file crew cannot read:
    `settings` keeps its could-not-tell answer, never the global value."""
    _global(tmp_path, monkeypatch, {"autopilot": {"approval": "self", "mode": "plan"}})
    root = crew_fixtures.make_repo(tmp_path, config=None, git=False)
    (root / ".crew" / "config.json").write_text("{ nope", encoding="utf-8")
    got = crew_autopilot.settings(str(root))
    assert got["approval"] == crew_autopilot.UNKNOWN
    assert got["armed"] is False


def test_global_knownfailures_and_scope_mode_refused(tmp_path, monkeypatch):
    """`scope.mode` is the scope guard's trust root and stays repo-only; a
    global `autopilot.<unknown>` is not a key. Refused on write, dropped on
    read."""
    path = _global(tmp_path, monkeypatch, {})
    for dotted, value in (("scope.mode", "off"),
                          ("autopilot.knownFailures", ["t"]),
                          ("scope.allowCliApproval", True)):
        with pytest.raises(crew_config.GlobalWriteRefused):
            crew_config.plan_global_write({dotted: value}, str(path))
        top, rest = dotted.split(".")
        kept, ignored = crew_config.filter_global({top: {rest: value}})
        assert dotted in ignored or top in ignored
        assert rest not in kept.get(top, {})


def test_global_set_of_a_personal_key_marks_its_widening(tmp_path, monkeypatch):
    path = _global(tmp_path, monkeypatch, {})
    _merged, changes = crew_config.plan_global_write(
        {"autopilot.approval": "self", "autopilot.maxPhases": 30,
         "autopilot.questions": "human"}, str(path))
    widens = {c["path"]: c["widens"] for c in changes}
    assert widens == {"autopilot.approval": True, "autopilot.maxPhases": True,
                      "autopilot.questions": False}
    with pytest.raises(crew_config.GlobalWriteRefused):
        crew_config.plan_global_write({"autopilot.approval": "slef"}, str(path))


def test_repo_set_under_a_stricter_global_is_held_down(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, None, {"approval": "human"})
    _merged, changes = crew_config.plan_repo_write(root, {"autopilot.approval": "self"})
    assert changes[0]["heldDownBy"] == "global"
    assert changes[0]["widens"] is False


def test_non_personal_keys_resolve_as_before(tmp_path, monkeypatch):
    """Every key outside `PERSONAL_PATHS` still resolves exactly by the old
    rule -- prune, null shadows, defaults <- global <- repo -- checked against
    that rule computed independently over layered fixtures."""
    fixtures = [
        (crew_config.default_config(), {}),
        (crew_config.template_config(), {"pm": {"authority": "act"},
                                         "memory": {"vaultPath": "/v"},
                                         "autopilot": {"approval": "self"}}),
        ({"tracker": "jira", "autopilot": {"mode": "plan"}, "scope": {"mode": "block"}},
         {"tracker": "files", "qa": {"order": ["claude"]}, "route": {"enabled": True},
          "autopilot": {"mode": "off", "maxPhases": 3}}),
    ]
    for index, (repo, glob) in enumerate(fixtures):
        sub = tmp_path / str(index)
        sub.mkdir()
        _global(sub, monkeypatch, glob)
        root = _repo(sub, repo)
        got = crew_config.resolve_config(root)
        kept, _ = crew_config.filter_global(glob)
        old = crew_state.merge_defaults(
            crew_state.merge_defaults(crew_config.default_config(), kept),
            crew_config.without_null_shadows(repo, kept))
        if "schema" in repo:
            old["schema"] = repo["schema"]
        else:
            old.pop("schema", None)
        for dotted in crew_config.leaf_paths(crew_config.default_config()):
            if dotted in crew_config.PERSONAL_PATHS or dotted == "schema":
                continue
            parts = tuple(dotted.split("."))
            assert crew_config._dig(got, parts) == crew_config._dig(old, parts), dotted


# --- Templates ---------------------------------------------------------------


def _skill_inline_copy():
    import re  # pylint: disable=import-outside-toplevel
    with open(SKILL_MD, encoding="utf-8") as handle:
        fences = re.findall(r"```json\n(.*?)\n```", handle.read(), re.DOTALL)
    return json.loads(fences[0])


def test_no_template_spells_a_personal_key():
    with open(TEMPLATE, encoding="utf-8") as handle:
        repo_template = json.load(handle)
    with open(GLOBAL_TEMPLATE, encoding="utf-8") as handle:
        global_template = json.load(handle)
    for name, cfg in (("template_config", crew_config.template_config()),
                      ("global_template_config", crew_config.global_template_config()),
                      ("config.template.json", repo_template),
                      ("global.template.json", global_template),
                      ("crew-setup inline copy", _skill_inline_copy())):
        spelled = [p for p in crew_config.leaf_paths(cfg) if p in crew_state.PERSONAL_KEYS]
        assert not spelled, f"{name} spells {spelled}"
    assert crew_config.PERSONAL_PATHS, "no personal key is a path: the test is vacuous"


def test_defaults_layer_still_carries_the_personal_keys():
    assert crew_config.default_config()["autopilot"] == crew_state.AUTOPILOT_DEFAULTS
    for dotted in crew_config.PERSONAL_PATHS:
        assert crew_config.is_global_path(dotted), dotted


def test_heal_config_writes_the_template(tmp_path):
    root = tmp_path / "r"
    (root / ".crew").mkdir(parents=True)
    healed, message = crew_platform.heal_config(str(root))
    assert healed == crew_config.template_config()
    with open(root / ".crew" / "config.json", encoding="utf-8") as handle:
        assert json.load(handle) == crew_config.template_config()
    assert "/crew:config --rebuild --repo" in message


def test_a_healed_repo_inherits_the_global_personal_values(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, {"autopilot": {"mode": "plan", "approval": "self"}})
    root = tmp_path / "r"
    (root / ".crew").mkdir(parents=True)
    crew_platform.heal_config(str(root))
    got = crew_autopilot.settings(str(root))
    assert got["armed"] is True and got["approval"] == "self"


# --- --explain --all (Step 6) ------------------------------------------------


def test_explain_all_lists_every_default_config_leaf(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, None, None)
    rows = crew_config.explain_config(root, all_keys=True)
    assert [r["path"] for r in rows] == crew_config.leaf_paths(crew_config.default_config())


def test_explain_all_marks_repo_only(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, None, None)
    rows = {r["path"]: r for r in crew_config.explain_config(root, all_keys=True)}
    assert rows["tracker"]["repoOnly"] is True
    assert rows["tracker"]["source"] == "repo"
    assert rows["scope.mode"]["repoOnly"] is True
    assert "repoOnly" not in rows["pm.authority"]
    assert rows["autopilot.mode"].get("personal") is True


def test_explain_personal_row_matches_resolve_config(tmp_path, monkeypatch):
    cases = [({"approval": "self"}, {"approval": "human"}),
             (None, {"approval": "self", "maxPhases": 4}),
             ({"mode": "off", "maxPhases": 30}, {"mode": "plan", "maxPhases": 9}),
             ({"deploy": None}, {"deploy": "nonprod"}),
             (None, None)]
    for index, (repo, glob) in enumerate(cases):
        sub = tmp_path / str(index)
        sub.mkdir()
        root = _layers(sub, monkeypatch, repo, glob)
        resolved = crew_config.resolve_config(root)
        for row in crew_config.explain_config(root, all_keys=True):
            if row["path"] in crew_config.PERSONAL_PATHS:
                parts = tuple(row["path"].split("."))
                assert row["value"] == crew_config._dig(resolved, parts), row


def test_explain_names_held_down_layer(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, {"approval": "self"}, {"approval": "human"})
    out = subprocess.run([sys.executable, CREW_CONFIG, "--root", root,
                          "--global-path", crew_config.GLOBAL_CONFIG_PATH,
                          "--explain", "--all"], capture_output=True, text=True,
                         check=False)
    assert out.returncode == 0, out.stderr
    line = next(l for l in out.stdout.splitlines() if l.startswith("autopilot.approval"))
    assert "held down by global" in line
    assert any(l.startswith("tracker") and "repo-only" in l for l in out.stdout.splitlines())


def test_shadow_finding_names_key_and_unset_command(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, {"mode": "off", "approval": "risk"},
                   {"mode": "plan", "approval": "self"})
    findings = crew_config.explain_findings(root)
    shadows = {f["path"] for f in findings if f["kind"] == "shadow"}
    assert shadows == {"autopilot.mode", "autopilot.approval"}
    text = next(f["detail"] for f in findings if f["path"] == "autopilot.mode")
    assert "/crew:config --unset autopilot.mode --repo --apply" in text


def test_no_shadow_when_global_silent(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, {"mode": "off"}, None)
    assert not [f for f in crew_config.explain_findings(root) if f["kind"] == "shadow"]
    root2 = _layers(tmp_path / "b", monkeypatch, {"mode": "off"}, {"mode": "off"})
    assert not [f for f in crew_config.explain_findings(root2) if f["kind"] == "shadow"]


def test_explain_all_writes_nothing(tmp_path, monkeypatch):
    root = _layers(tmp_path, monkeypatch, {"approval": "self"}, {"approval": "human"})
    before = _tree(tmp_path)
    out = subprocess.run([sys.executable, CREW_CONFIG, "--root", root,
                          "--global-path", crew_config.GLOBAL_CONFIG_PATH,
                          "--explain", "--all"], capture_output=True, text=True,
                         check=False, env=dict(os.environ))
    assert out.returncode == 0, out.stderr
    assert _tree(tmp_path) == before


def _tree(base):
    out = {}
    for dirpath, _dirs, files in os.walk(base):
        for name in files:
            full = os.path.join(dirpath, name)
            with open(full, "rb") as handle:
                out[full] = (handle.read(), os.stat(full).st_mtime_ns)
    return out


# --- The docs (Step 7) -------------------------------------------------------


def test_config_md_names_every_new_flag():
    with open(CONFIG_MD, encoding="utf-8") as handle:
        text = handle.read()
    for flag in ("--rebuild", "--restore", "--backups", "--unset", "--repo",
                 "--save-profile", "--apply", "--no-profile"):
        assert flag in text, flag


def test_config_md_no_longer_says_it_never_writes_repo_file():
    with open(CONFIG_MD, encoding="utf-8") as handle:
        text = handle.read()
    assert "never writes `.crew/config.json`" not in text
    assert "does not write `.crew/config.json`" not in text


def test_heal_message_names_rebuild(tmp_path):
    root = tmp_path / "r"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text("{ broken", encoding="utf-8")
    _healed, message = crew_platform.heal_config(str(root))
    assert "/crew:config --rebuild --repo" in message


def test_menu_post_heal_rows_read_the_template(tmp_path, monkeypatch):
    """The delete preview says what the heal leaves; heal writes the template,
    so a global personal value is what is in force after it."""
    import crew_config_menu  # pylint: disable=import-outside-toplevel
    _global(tmp_path, monkeypatch, {"autopilot": {"mode": "plan"}})
    root = _repo(tmp_path, crew_config.default_config())
    rows = crew_config_menu._post_heal_rows(root, crew_config.GLOBAL_CONFIG_PATH)
    assert rows["autopilot.mode"]["value"] == "plan"
