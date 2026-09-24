"""Tests for `crew_autoclear_setup`, the one helper `/crew:init`,
`/crew:migrate` and `/crew:onboard` share for `context.autoClear` decisions.

Every sabotage below is a manual revert -> red -> restore in-session (Edit the
source, run the one test, Edit it back), never `git stash` and never a
committed broken state.
"""
import json
import os

import context  # noqa: F401  pylint: disable=unused-import
import crew_autoclear_setup as setup
import crew_config


def _global(tmp_path):
    return str(tmp_path / "global-config.json")


# --------------------------------------------------------------- init: fresh


def test_plan_windows_default_proposes_notify_on_a_fresh_machine(tmp_path):
    plan = setup.plan_windows_notify_default(path=_global(tmp_path))
    assert plan["status"] == "proposed"
    assert plan["updates"] == {"context.autoClear.method": "notify"}
    assert "notify" in plan["message"]


def test_apply_windows_default_writes_and_prints_it(tmp_path):
    path = _global(tmp_path)
    plan = setup.plan_windows_notify_default(path=path)
    merged, changes = setup.write_autoclear_method(
        plan["updates"]["context.autoClear.method"], consent=True, path=path)
    assert merged["context"]["autoClear"]["method"] == "notify"
    assert changes and changes[0]["after"] == "notify"
    with open(path, encoding="utf-8") as handle:
        on_disk = json.load(handle)
    assert on_disk["context"]["autoClear"]["method"] == "notify"


# --------------------------------------------------------------- idempotence


def test_init_idempotent_already_configured_no_file_change(tmp_path):
    path = _global(tmp_path)
    setup.write_autoclear_method("notify", consent=True, path=path)
    with open(path, "rb") as handle:
        before = handle.read()

    plan = setup.plan_windows_notify_default(path=path)
    assert plan["status"] == "already-configured"
    assert "notify" in plan["message"]

    with open(path, "rb") as handle:
        after = handle.read()
    assert before == after


def test_migrate_idempotent_no_windows_literal_no_duplication_no_notes():
    context_block = {"autoClear": {"method": "notify", "enabled": False}}
    plan = setup.plan_migrate_context(context_block, {}, "/tmp/repo")
    assert plan["notes"] == []
    assert plan["context"] == context_block


def test_onboard_reports_already_configured_same_helper_as_init(tmp_path):
    path = _global(tmp_path)
    setup.write_autoclear_method("notify", consent=True, path=path)
    # /crew:onboard asks the identical question /crew:init does; both must
    # agree it is already answered.
    assert setup.already_configured_global(path) is not None
    assert setup.plan_windows_notify_default(path=path)["status"] == "already-configured"


# --------------------------------------------------------------- migrate: (a)


def test_migrate_converts_windows_method_to_notify_with_note():
    context_block = {"autoClear": {"method": "windows", "enabled": True}}
    plan = setup.plan_migrate_context(context_block, {}, "/tmp/repo")
    assert plan["context"]["autoClear"]["method"] == "notify"
    assert any("windows" in n and "notify" in n for n in plan["notes"])
    assert any("sendkeys" in n for n in plan["notes"])


# --------------------------------------------------------------- migrate: (b)


def test_migrate_removes_repo_duplicate_block_keeps_enabled_false():
    context_block = {"autoClear": {
        "enabled": True, "method": "auto", "onlyRepos": None, "onlySessions": None,
    }}
    new_context, notes = setup.strip_repo_duplication(context_block, "aws-managed-services")
    assert "enabled" not in new_context["autoClear"]
    assert "onlyRepos" not in new_context["autoClear"]
    assert "onlySessions" not in new_context["autoClear"]
    assert new_context["autoClear"]["method"] == "auto"
    assert len(notes) == 3  # enabled, onlyRepos, onlySessions


def test_migrate_keeps_a_legit_repo_opt_out():
    context_block = {"autoClear": {"enabled": False, "method": "tmux"}}
    new_context, notes = setup.strip_repo_duplication(context_block)
    assert new_context["autoClear"]["enabled"] is False
    assert new_context["autoClear"]["method"] == "tmux"
    assert notes == []


# --------------------------------------------------------------- migrate: (c)


def test_migrate_detects_onlyRepos_widening_and_proposes_this_repo():
    global_cfg = {"context": {"autoClear": {"enabled": True, "onlyRepos": None}}}
    result = setup.detect_onlyRepos_widening(global_cfg, "/repos/my-repo", True)
    assert result["widening"] is True
    assert result["proposedOnlyRepos"] == [os.path.realpath("/repos/my-repo")]


def test_migrate_widening_not_applied_without_yes(tmp_path):
    path = _global(tmp_path)
    setup.write_autoclear_method("auto", consent=True, path=path)
    setup.write_autoclear_enabled(True, consent=True, path=path)
    with open(path, "rb") as handle:
        before = handle.read()

    global_cfg = crew_config.read_global_config(path)
    result = setup.detect_onlyRepos_widening(global_cfg, "/repos/my-repo", True)
    assert result["widening"] is True

    try:
        setup.apply_onlyRepos_narrowing(
            result["proposedOnlyRepos"], consent=False, path=path)
        assert False, "expected PermissionError without consent"
    except PermissionError:
        pass

    with open(path, "rb") as handle:
        after = handle.read()
    assert before == after


def test_migrate_widening_applied_with_yes(tmp_path):
    path = _global(tmp_path)
    setup.write_autoclear_method("auto", consent=True, path=path)
    setup.write_autoclear_enabled(True, consent=True, path=path)
    merged, changes = setup.apply_onlyRepos_narrowing(
        ["/repos/my-repo"], consent=True, path=path)
    assert merged["context"]["autoClear"]["onlyRepos"] == ["/repos/my-repo"]
    assert changes


def test_no_widening_when_onlyRepos_already_narrowed():
    global_cfg = {"context": {"autoClear": {"enabled": True, "onlyRepos": ["/x"]}}}
    result = setup.detect_onlyRepos_widening(global_cfg, "/repos/my-repo", True)
    assert result["widening"] is False


# --------------------------------------------------------------- wording


def test_no_forbidden_words_anywhere():
    offenders = setup.check_no_forbidden_words()
    assert offenders == []


# --------------------------------------------------------------- sendkeys consent


def test_sendkeys_never_written_without_consent(tmp_path):
    path = _global(tmp_path)
    try:
        setup.write_autoclear_method("sendkeys", consent=False, path=path)
        assert False, "expected PermissionError"
    except PermissionError:
        pass
    assert not os.path.exists(path)


def test_sendkeys_written_with_explicit_consent(tmp_path):
    path = _global(tmp_path)
    merged, changes = setup.write_autoclear_method("sendkeys", consent=True, path=path)
    assert merged["context"]["autoClear"]["method"] == "sendkeys"
    assert changes


def test_enabling_never_written_without_consent(tmp_path):
    path = _global(tmp_path)
    try:
        setup.write_autoclear_enabled(True, consent=False, path=path)
        assert False, "expected PermissionError"
    except PermissionError:
        pass
    assert not os.path.exists(path)


def test_disabling_needs_no_consent(tmp_path):
    path = _global(tmp_path)
    merged, changes = setup.write_autoclear_enabled(False, consent=False, path=path)
    assert merged["context"]["autoClear"]["enabled"] is False
    assert changes


# --------------------------------------------------------------- apply_migrate_to_repo


def _write_crew_json(root, context_block):
    crew_dir = os.path.join(root, ".crew")
    os.makedirs(crew_dir, exist_ok=True)
    with open(os.path.join(crew_dir, "crew.json"), "w", encoding="utf-8") as handle:
        json.dump({"schema": 1, "context": context_block}, handle)


def test_apply_migrate_to_repo_rewrites_crew_json_in_place(tmp_path):
    root = str(tmp_path / "repo")
    _write_crew_json(root, {"autoClear": {"method": "windows", "enabled": True}})
    plan = setup.apply_migrate_to_repo(root, global_path=str(tmp_path / "g.json"))
    with open(os.path.join(root, ".crew", "crew.json"), encoding="utf-8") as handle:
        on_disk = json.load(handle)
    assert on_disk["context"]["autoClear"]["method"] == "notify"
    assert "enabled" not in on_disk["context"]["autoClear"]
    assert on_disk["schema"] == 1  # the rest of the file survives untouched
    assert plan["wideningApplied"] is False
    assert plan["alreadyConfigured"] is False


def test_apply_migrate_to_repo_is_a_noop_on_a_repo_with_nothing_to_convert(tmp_path):
    root = str(tmp_path / "repo")
    _write_crew_json(root, {"autoClear": {"method": "notify", "enabled": False}})
    crew_json_path = os.path.join(root, ".crew", "crew.json")
    with open(crew_json_path, "rb") as handle:
        before = handle.read()

    plan = setup.apply_migrate_to_repo(root, global_path=str(tmp_path / "g.json"))
    assert plan["alreadyConfigured"] is True

    with open(crew_json_path, "rb") as handle:
        after = handle.read()
    assert before == after


def test_apply_migrate_to_repo_second_call_does_not_reapply_or_corrupt(tmp_path):
    """The double-invocation hazard the function's own docstring warns
    about: after the FIRST call has already stripped the local opt-in
    signal, a SECOND call must not touch the file again (byte-identical),
    even though it can no longer see that this repo used to be opted in."""
    root = str(tmp_path / "repo")
    _write_crew_json(root, {"autoClear": {"method": "windows", "enabled": True}})
    global_path = str(tmp_path / "g.json")

    setup.apply_migrate_to_repo(root, global_path=global_path)
    crew_json_path = os.path.join(root, ".crew", "crew.json")
    with open(crew_json_path, "rb") as handle:
        after_first = handle.read()

    plan_two = setup.apply_migrate_to_repo(root, global_path=global_path)
    assert plan_two["alreadyConfigured"] is True

    with open(crew_json_path, "rb") as handle:
        after_second = handle.read()
    assert after_first == after_second


def test_apply_migrate_to_repo_does_not_widen_without_yes_widen(tmp_path):
    root = str(tmp_path / "repo")
    _write_crew_json(root, {"autoClear": {"method": "auto", "enabled": True}})
    global_path = str(tmp_path / "g.json")
    setup.write_autoclear_method("auto", consent=True, path=global_path)
    setup.write_autoclear_enabled(True, consent=True, path=global_path)
    with open(global_path, "rb") as handle:
        before = handle.read()

    plan = setup.apply_migrate_to_repo(root, global_path=global_path)
    assert plan["widening"]["widening"] is True
    assert plan["wideningApplied"] is False

    with open(global_path, "rb") as handle:
        after = handle.read()
    assert before == after


def test_apply_migrate_to_repo_widens_with_yes_widen(tmp_path):
    root = str(tmp_path / "repo")
    _write_crew_json(root, {"autoClear": {"method": "auto", "enabled": True}})
    global_path = str(tmp_path / "g.json")
    setup.write_autoclear_method("auto", consent=True, path=global_path)
    setup.write_autoclear_enabled(True, consent=True, path=global_path)

    plan = setup.apply_migrate_to_repo(root, global_path=global_path, yes_widen=True)
    assert plan["wideningApplied"] is True
    with open(global_path, encoding="utf-8") as handle:
        on_disk = json.load(handle)
    assert on_disk["context"]["autoClear"]["onlyRepos"] == [os.path.realpath(root)]


# ------------------------------------------ apply_migrate_to_repo: config.json
# Codex review (gpt-5.6-sol) finding #1: config.json is what the senders read


def _write_config_json(root, context_block):
    crew_dir = os.path.join(root, ".crew")
    os.makedirs(crew_dir, exist_ok=True)
    with open(os.path.join(crew_dir, "config.json"), "w", encoding="utf-8") as handle:
        json.dump({"schema": 7, "context": context_block}, handle)


def test_apply_migrate_to_repo_converts_config_json_the_senders_actually_read(tmp_path):
    """Reproduces the review finding directly: `crew_migrate.py --apply`
    copies config.json's `context` into a new crew.json UNCONVERTED and
    keeps config.json (`commands/migrate.md`'s own table marks it
    "retireable", never deleted). Every autoClear sender -- auto-clear.sh,
    auto-clear.ps1, crew_autocycle.py's `_load` -- reads `.crew/config.json`
    only, never crew.json. Before this fix, converting crew.json alone left
    a retained legacy "windows" method live in config.json, where every
    sender still read it and refused it as unsupported."""
    root = str(tmp_path / "repo")
    context_block = {"autoClear": {"method": "windows", "enabled": True}}
    _write_config_json(root, context_block)
    _write_crew_json(root, context_block)

    plan = setup.apply_migrate_to_repo(root, global_path=str(tmp_path / "g.json"))

    with open(os.path.join(root, ".crew", "config.json"), encoding="utf-8") as handle:
        config_on_disk = json.load(handle)
    with open(os.path.join(root, ".crew", "crew.json"), encoding="utf-8") as handle:
        crew_on_disk = json.load(handle)
    assert config_on_disk["context"]["autoClear"]["method"] == "notify"
    assert crew_on_disk["context"]["autoClear"]["method"] == "notify"
    assert "enabled" not in config_on_disk["context"]["autoClear"]
    assert "enabled" not in crew_on_disk["context"]["autoClear"]
    assert config_on_disk["schema"] == 7  # the rest of the file survives untouched
    assert crew_on_disk["schema"] == 1
    assert plan["alreadyConfigured"] is False


def test_apply_migrate_to_repo_config_json_only_before_crew_migrate_has_run(tmp_path):
    """A repo that has not yet run `crew_migrate.py --apply` (only
    config.json exists, no crew.json yet) is still converted -- this is
    the same helper `/crew:init` and `/crew:onboard` share, and neither
    ever creates crew.json."""
    root = str(tmp_path / "repo")
    _write_config_json(root, {"autoClear": {"method": "windows", "enabled": True}})

    plan = setup.apply_migrate_to_repo(root, global_path=str(tmp_path / "g.json"))

    with open(os.path.join(root, ".crew", "config.json"), encoding="utf-8") as handle:
        on_disk = json.load(handle)
    assert on_disk["context"]["autoClear"]["method"] == "notify"
    assert not os.path.exists(os.path.join(root, ".crew", "crew.json"))
    assert plan["alreadyConfigured"] is False


def test_apply_migrate_to_repo_neither_config_file_present_raises(tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(os.path.join(root, ".crew"))
    try:
        setup.apply_migrate_to_repo(root, global_path=str(tmp_path / "g.json"))
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


# --------------------------------------------- apply_migrate_to_repo: ordering
# Codex review finding #2: the global write must land before either repo file
# is touched, so a failed global write leaves the repo untouched too.


def test_apply_migrate_to_repo_writes_global_narrowing_before_repo_files(tmp_path, monkeypatch):
    root = str(tmp_path / "repo")
    context_block = {"autoClear": {"method": "auto", "enabled": True}}
    _write_config_json(root, context_block)
    _write_crew_json(root, context_block)
    config_path = os.path.join(root, ".crew", "config.json")
    crew_json_path = os.path.join(root, ".crew", "crew.json")
    with open(config_path, "rb") as handle:
        config_before = handle.read()
    with open(crew_json_path, "rb") as handle:
        crew_before = handle.read()

    global_path = str(tmp_path / "g.json")
    setup.write_autoclear_method("auto", consent=True, path=global_path)
    setup.write_autoclear_enabled(True, consent=True, path=global_path)
    with open(global_path, "rb") as handle:
        global_before = handle.read()

    def _boom(updates, path=None):
        raise OSError("simulated: the machine-global config directory is unwritable")

    monkeypatch.setattr(setup.crew_config, "write_global_config", _boom)

    try:
        setup.apply_migrate_to_repo(root, global_path=global_path, yes_widen=True)
        assert False, "expected the simulated global write failure to propagate"
    except OSError:
        pass

    # Neither repo file was rewritten, and the global file is untouched too --
    # the failure happened before ANY write in this call, not partway through.
    with open(config_path, "rb") as handle:
        assert handle.read() == config_before
    with open(crew_json_path, "rb") as handle:
        assert handle.read() == crew_before
    with open(global_path, "rb") as handle:
        assert handle.read() == global_before


# ------------------------------------------------- global file: malformed JSON
# Codex review finding #3: unparseable is its own state, and never gets
# collapsed into "nothing configured yet, propose and write the default".


def test_plan_windows_default_reports_unreadable_for_malformed_global_json(tmp_path):
    path = _global(tmp_path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{not valid json")

    plan = setup.plan_windows_notify_default(path=path)

    assert plan["status"] == "unreadable"
    assert plan["updates"] == {}
    with open(path, encoding="utf-8") as handle:
        assert handle.read() == "{not valid json"


def test_apply_method_refuses_to_write_over_malformed_global_json(tmp_path):
    path = _global(tmp_path)
    original = "{not valid json"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(original)

    try:
        setup.write_autoclear_method("notify", consent=True, path=path)
        assert False, "expected GlobalConfigUnreadable"
    except setup.GlobalConfigUnreadable:
        pass

    with open(path, encoding="utf-8") as handle:
        assert handle.read() == original, "a malformed file must never be overwritten"


def test_apply_enabled_refuses_to_write_over_a_global_file_that_is_not_an_object(tmp_path):
    path = _global(tmp_path)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump([1, 2, 3], handle)

    try:
        setup.write_autoclear_enabled(True, consent=True, path=path)
        assert False, "expected GlobalConfigUnreadable"
    except setup.GlobalConfigUnreadable:
        pass


# ---------------------------------- global file: retained "windows" literal
# Codex review finding #4: a machine-global legacy "windows" method must be
# proposed for conversion, not reported as already-configured.


def test_plan_windows_default_converts_a_retained_global_windows_method(tmp_path):
    path = _global(tmp_path)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"context": {"autoClear": {"method": "windows"}}}, handle)

    assert setup.already_configured_global(path) is None

    plan = setup.plan_windows_notify_default(path=path)

    assert plan["status"] == "proposed"
    assert plan["updates"] == {"context.autoClear.method": "notify"}
    assert "windows" in plan["message"] and "notify" in plan["message"]
