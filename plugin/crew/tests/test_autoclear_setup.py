"""Tests for `crew_autoclear_setup`, the one helper `/crew:init`,
`/crew:migrate` and `/crew:onboard` share for `context.autoClear` decisions.

Every sabotage below is a manual revert -> red -> restore in-session (Edit the
source, run the one test, Edit it back), never `git stash` and never a
committed broken state.
"""
import json
import os

import pytest

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


# ------------------------------------ apply_migrate_to_repo: divergent files
# PM decision (Codex review, BLOCK): config.json is what every autoClear
# sender reads and crew.json is never read for behaviour, but a single plan
# computed from whichever file happened to be read first and then copied
# onto BOTH used to destroy whatever the OTHER file had settled on if the
# two had genuinely diverged (a hand-edit to one after migration, or two
# repos merged). Each file must convert from and write back only its OWN
# prior content.


def test_apply_migrate_to_repo_never_copies_one_files_context_onto_the_other(tmp_path):
    root = str(tmp_path / "repo")
    _write_config_json(root, {"autoClear": {"method": "windows", "enabled": True}})
    _write_crew_json(root, {"autoClear": {"method": "auto",
                                          "windowTitle": "My Custom Title"}})
    crew_json_path = os.path.join(root, ".crew", "crew.json")
    with open(crew_json_path, "rb") as handle:
        crew_before = handle.read()

    plan = setup.apply_migrate_to_repo(root, global_path=str(tmp_path / "g.json"))

    with open(os.path.join(root, ".crew", "config.json"), encoding="utf-8") as handle:
        config_on_disk = json.load(handle)
    assert config_on_disk["context"]["autoClear"]["method"] == "notify"
    assert "enabled" not in config_on_disk["context"]["autoClear"]

    # crew.json had NOTHING of its own to convert (method is "auto", not
    # "windows"; no enabled/onlyRepos/onlySessions to strip) -- it must be
    # byte-identical to before, never overwritten with config.json's
    # unrelated post-migration context.
    with open(crew_json_path, "rb") as handle:
        crew_after = handle.read()
    assert crew_after == crew_before
    assert plan["alreadyConfigured"] is False
    assert plan["perFile"]["config.json"]["autoClear"]["method"] == "notify"
    assert plan["perFile"]["crew.json"]["autoClear"]["method"] == "auto"


def test_apply_migrate_to_repo_converts_each_divergent_file_from_its_own_content(tmp_path):
    """The other direction: BOTH files need converting, but from DIFFERENT
    starting points -- config.json has a repo-local `enabled: true` to
    strip, crew.json does not. Each file's own result must reflect only
    its own prior content."""
    root = str(tmp_path / "repo")
    _write_config_json(root, {"autoClear": {"method": "windows", "enabled": True}})
    _write_crew_json(root, {"autoClear": {"method": "windows"}})

    setup.apply_migrate_to_repo(root, global_path=str(tmp_path / "g.json"))

    with open(os.path.join(root, ".crew", "config.json"), encoding="utf-8") as handle:
        config_on_disk = json.load(handle)
    with open(os.path.join(root, ".crew", "crew.json"), encoding="utf-8") as handle:
        crew_on_disk = json.load(handle)
    assert config_on_disk["context"]["autoClear"]["method"] == "notify"
    assert "enabled" not in config_on_disk["context"]["autoClear"]
    assert crew_on_disk["context"]["autoClear"]["method"] == "notify"
    assert "enabled" not in crew_on_disk["context"]["autoClear"]  # never had one


# --------------------------------- apply_migrate_to_repo: staging is batched
# BLOCK: the two repo writes are not one transaction. Both new payloads must
# be staged into temp files before EITHER real file is replaced, so a
# failure while staging leaves BOTH real files untouched; and a retry must
# detect and repair a pair left half-migrated by a crash BETWEEN the two
# os.replace calls (POSIX has no atomic rename of two files at once).


def test_apply_migrate_to_repo_leaves_both_files_untouched_if_staging_either_fails(
        tmp_path, monkeypatch):
    root = str(tmp_path / "repo")
    context_block = {"autoClear": {"method": "windows", "enabled": True}}
    _write_config_json(root, context_block)
    _write_crew_json(root, context_block)
    config_path = os.path.join(root, ".crew", "config.json")
    crew_json_path = os.path.join(root, ".crew", "crew.json")
    with open(config_path, "rb") as handle:
        config_before = handle.read()
    with open(crew_json_path, "rb") as handle:
        crew_before = handle.read()

    real_stage = setup._stage_json

    def _boom(path, obj):
        if path == crew_json_path:
            raise OSError("simulated: disk full staging crew.json")
        return real_stage(path, obj)

    monkeypatch.setattr(setup, "_stage_json", _boom)

    try:
        setup.apply_migrate_to_repo(root, global_path=str(tmp_path / "g.json"))
        assert False, "expected the simulated staging failure to propagate"
    except OSError:
        pass

    with open(config_path, "rb") as handle:
        assert handle.read() == config_before, (
            "config.json must stay untouched when crew.json's staging fails")
    with open(crew_json_path, "rb") as handle:
        assert handle.read() == crew_before
    leftovers = [n for n in os.listdir(os.path.join(root, ".crew"))
                if n.endswith(".tmp")]
    assert leftovers == [], f"orphaned temp file(s) after a failed batch: {leftovers}"


def test_apply_migrate_to_repo_retry_repairs_a_half_migrated_pair(tmp_path, monkeypatch):
    root = str(tmp_path / "repo")
    context_block = {"autoClear": {"method": "windows", "enabled": True}}
    _write_config_json(root, context_block)
    _write_crew_json(root, context_block)
    config_path = os.path.join(root, ".crew", "config.json")
    crew_json_path = os.path.join(root, ".crew", "crew.json")
    global_path = str(tmp_path / "g.json")

    real_replace = os.replace
    calls = []

    def _flaky_replace(src, dst):
        calls.append(dst)
        if dst == crew_json_path and len(calls) == 2:
            raise OSError("simulated: crash between the two replace calls")
        return real_replace(src, dst)

    monkeypatch.setattr(setup.os, "replace", _flaky_replace)
    try:
        setup.apply_migrate_to_repo(root, global_path=global_path)
        assert False, "expected the simulated mid-batch crash to propagate"
    except OSError:
        pass
    monkeypatch.setattr(setup.os, "replace", real_replace)

    with open(config_path, encoding="utf-8") as handle:
        config_mid = json.load(handle)
    with open(crew_json_path, encoding="utf-8") as handle:
        crew_mid = json.load(handle)
    assert config_mid["context"]["autoClear"]["method"] == "notify"  # made it
    assert crew_mid["context"]["autoClear"]["method"] == "windows"  # did not

    plan = setup.apply_migrate_to_repo(root, global_path=global_path)
    assert plan["alreadyConfigured"] is False

    with open(config_path, encoding="utf-8") as handle:
        config_after = json.load(handle)
    with open(crew_json_path, encoding="utf-8") as handle:
        crew_after = json.load(handle)
    assert config_after["context"]["autoClear"]["method"] == "notify"
    assert crew_after["context"]["autoClear"]["method"] == "notify"
    assert "enabled" not in crew_after["context"]["autoClear"]


def test_apply_migrate_to_repo_commit_failure_leaves_no_orphaned_temp_file(
        tmp_path, monkeypatch):
    """FIX: an `os.replace` failure during the COMMIT loop (both files
    already staged) used to leave every unconsumed staged temp file
    behind -- the staging loop's own `except BaseException` cleanup only
    covers a failure to STAGE, not a failure to commit what was already
    staged. Monkeypatches the FIRST `os.replace` call to raise, so
    neither file has been committed yet, and asserts no `.tmp` file
    remains under `.crew/` afterwards."""
    root = str(tmp_path / "repo")
    context_block = {"autoClear": {"method": "windows", "enabled": True}}
    _write_config_json(root, context_block)
    _write_crew_json(root, context_block)
    config_path = os.path.join(root, ".crew", "config.json")
    crew_json_path = os.path.join(root, ".crew", "crew.json")
    with open(config_path, "rb") as handle:
        config_before = handle.read()
    with open(crew_json_path, "rb") as handle:
        crew_before = handle.read()

    real_replace = os.replace

    def _boom_first(src, dst):
        raise OSError("simulated: disk full committing the first file")

    monkeypatch.setattr(setup.os, "replace", _boom_first)
    try:
        setup.apply_migrate_to_repo(root, global_path=str(tmp_path / "g.json"))
        assert False, "expected the simulated commit failure to propagate"
    except OSError:
        pass
    monkeypatch.setattr(setup.os, "replace", real_replace)

    with open(config_path, "rb") as handle:
        assert handle.read() == config_before, (
            "config.json must stay untouched when the first commit fails")
    with open(crew_json_path, "rb") as handle:
        assert handle.read() == crew_before
    leftovers = [n for n in os.listdir(os.path.join(root, ".crew"))
                if n.endswith(".tmp")]
    assert leftovers == [], (
        f"orphaned temp file(s) after a failed commit: {leftovers}")


# --------------------------------------- _read_json_if_present: type safety
# FIX: a repo config file that parses as valid JSON but is not an OBJECT
# ([], a bare string, ...) must fail in a controlled way, not crash with an
# uncaught AttributeError/TypeError once this module tries `.get("context")`
# on it.


def test_apply_migrate_to_repo_refuses_a_non_object_config_json(tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(os.path.join(root, ".crew"))
    with open(os.path.join(root, ".crew", "config.json"), "w", encoding="utf-8") as handle:
        json.dump([1, 2, 3], handle)

    try:
        setup.apply_migrate_to_repo(root, global_path=str(tmp_path / "g.json"))
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "not an object" in str(exc)


# ------------------------------------------- global file: invalid UTF-8 bytes
# FIX: bytes that are not valid UTF-8 must read as the unreadable-config
# result (a string reason), not raise an uncaught UnicodeDecodeError out of
# a helper every caller expects to return `None` or a string.


def test_global_file_problem_reports_invalid_utf8_instead_of_raising(tmp_path):
    path = _global(tmp_path)
    with open(path, "wb") as handle:
        handle.write(b"\xff\xfe\x00\x80not valid utf-8")

    problem = setup._global_file_problem(path)  # pylint: disable=protected-access

    assert problem is not None and "utf-8" in problem.lower()

    try:
        setup.write_autoclear_method("notify", consent=True, path=path)
        assert False, "expected GlobalConfigUnreadable, not a raw exception"
    except setup.GlobalConfigUnreadable:
        pass


# ------------------------------------------- apply-migrate --scan-root (T-0106)
# Every repo below is built under tmp_path; nothing reads a real config.


def _widening_global(tmp_path):
    """A machine file with enabled: true and onlyRepos: null -- the widening."""
    path = str(tmp_path / "g.json")
    setup.write_autoclear_method("auto", consent=True, path=path)
    setup.write_autoclear_enabled(True, consent=True, path=path)
    return path


def _repo(path, name="config.json", enabled=True, raw=None):
    os.makedirs(os.path.join(path, ".crew"), exist_ok=True)
    with open(os.path.join(path, ".crew", name), "w", encoding="utf-8") as handle:
        if raw is not None:
            handle.write(raw)
        else:
            json.dump({"context": {"autoClear": {"method": "auto", "enabled": enabled}}},
                      handle)
    return os.path.realpath(path)


def _snapshot(top):
    out = {}
    for base, _dirs, files in os.walk(top):
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as handle:
                out[path] = handle.read()
    return out


def _read(path):
    with open(path, "rb") as handle:
        return handle.read()


def test_scan_root_adds_every_opted_in_repo_to_the_proposal(tmp_path):
    scan = tmp_path / "src"
    here = _repo(str(scan / "here"))
    via_config = _repo(str(scan / "a"))
    via_crew_json = _repo(str(scan / "b"), name="crew.json")
    _repo(str(scan / "c"), enabled=False)

    plan = setup.apply_migrate_to_repo(here, global_path=_widening_global(tmp_path),
                                       scan_roots=[str(scan)])

    widening = plan["widening"]
    assert widening["proposedOnlyRepos"] == sorted([here, via_config, via_crew_json])
    assert widening["scan"]["found"] == sorted([via_config, via_crew_json])
    assert widening["scan"]["unreadable"] == []
    assert "found 2 other" in widening["message"]


def test_scan_root_proposes_other_repos_when_this_repo_never_opted_in(tmp_path):
    scan = tmp_path / "src"
    here = _repo(str(tmp_path / "here"), enabled=False)
    other = _repo(str(scan / "other"))

    plan = setup.apply_migrate_to_repo(here, global_path=_widening_global(tmp_path),
                                       scan_roots=[str(scan)])

    assert plan["widening"]["proposedOnlyRepos"] == [other]


def test_no_scan_without_scan_root(tmp_path, monkeypatch):
    here = _repo(str(tmp_path / "here"))
    _repo(str(tmp_path / "other"))
    walked = []
    monkeypatch.setattr(setup, "scan_opted_in_repos", lambda *a, **k: walked.append(a))

    plan = setup.apply_migrate_to_repo(here, global_path=_widening_global(tmp_path))

    assert "scan" not in plan["widening"]
    assert plan["widening"]["proposedOnlyRepos"] == [here]
    assert "--scan-root" in plan["widening"]["message"]
    assert walked == []


def test_scan_depth_limits_the_walk(tmp_path):
    scan = tmp_path / "src"
    here = _repo(str(tmp_path / "here"))
    deep = _repo(str(scan / "a" / "b" / "c" / "deep"))
    global_path = _widening_global(tmp_path)

    shallow = setup.detect_onlyRepos_widening(
        crew_config.read_global_config(global_path), here, True,
        scan_roots=[str(scan)], scan_depth=3)
    assert shallow["scan"]["found"] == []

    raised = setup.detect_onlyRepos_widening(
        crew_config.read_global_config(global_path), here, True,
        scan_roots=[str(scan)], scan_depth=4)
    assert raised["scan"]["found"] == [deep]


def test_scan_skips_nested_hidden_vendored_and_symlinked_directories(tmp_path):
    scan = tmp_path / "src"
    here = _repo(str(tmp_path / "here"))
    outer = _repo(str(scan / "outer"), enabled=False)
    _repo(str(scan / "outer" / "nested"))
    _repo(str(scan / ".hidden" / "repo"))
    _repo(str(scan / "node_modules" / "repo"))
    target = _repo(str(tmp_path / "elsewhere" / "linked"))
    try:
        os.symlink(os.path.dirname(target), str(scan / "link"), target_is_directory=True)
    except (OSError, NotImplementedError):
        pass  # the platform cannot create one; the other cases still run

    plan = setup.apply_migrate_to_repo(here, global_path=_widening_global(tmp_path),
                                       scan_roots=[str(scan)])

    assert plan["widening"]["scan"]["found"] == []
    assert plan["widening"]["proposedOnlyRepos"] == [here]
    assert outer not in plan["widening"]["proposedOnlyRepos"]


def test_scan_does_not_list_the_current_repo_twice(tmp_path):
    scan = tmp_path / "src"
    here = _repo(str(scan / "here"))

    plan = setup.apply_migrate_to_repo(here, global_path=_widening_global(tmp_path),
                                       scan_roots=[str(scan)])

    assert plan["widening"]["proposedOnlyRepos"] == [here]
    assert plan["widening"]["scan"]["found"] == []


def test_overlapping_scan_roots_deduplicate(tmp_path):
    scan = tmp_path / "src"
    here = _repo(str(tmp_path / "here"))
    other = _repo(str(scan / "team" / "other"))

    plan = setup.apply_migrate_to_repo(
        here, global_path=_widening_global(tmp_path),
        scan_roots=[str(scan), str(scan / "team"), str(scan)])

    assert plan["widening"]["scan"]["found"] == [other]
    assert plan["widening"]["proposedOnlyRepos"] == sorted([here, other])


def test_unreadable_candidate_is_reported_not_treated_as_not_opted_in(tmp_path):
    scan = tmp_path / "src"
    here = _repo(str(tmp_path / "here"))
    broken = _repo(str(scan / "broken"), raw="{not json")
    listed = _repo(str(scan / "listed"), raw="[1, 2]")

    plan = setup.apply_migrate_to_repo(here, global_path=_widening_global(tmp_path),
                                       scan_roots=[str(scan)])

    unreadable = plan["widening"]["scan"]["unreadable"]
    assert [item["path"] for item in unreadable] == sorted([broken, listed])
    assert all(item["reason"] for item in unreadable)
    assert plan["widening"]["proposedOnlyRepos"] == [here]
    assert broken in plan["widening"]["message"] and listed in plan["widening"]["message"]


def test_an_unreadable_file_is_not_masked_by_an_opted_in_sibling(tmp_path):
    scan = tmp_path / "src"
    here = _repo(str(tmp_path / "here"))
    mixed = _repo(str(scan / "mixed"))
    _repo(str(scan / "mixed"), name="crew.json", raw="{not json")
    global_path = _widening_global(tmp_path)

    plan = setup.apply_migrate_to_repo(here, global_path=global_path,
                                       scan_roots=[str(scan)])

    assert [item["path"] for item in plan["widening"]["scan"]["unreadable"]] == [mixed]
    assert plan["widening"]["scan"]["found"] == []
    assert setup.main(["--root", here, "--global-path", global_path, "apply-migrate",
                       "--scan-root", str(scan), "--yes-widen"]) == 1


def test_a_crew_directory_that_cannot_be_listed_is_unreadable(tmp_path, monkeypatch):
    scan = tmp_path / "src"
    here = _repo(str(tmp_path / "here"))
    locked = _repo(str(scan / "locked"))
    real_listdir = os.listdir

    def _listdir(path):
        if os.path.realpath(path) == os.path.join(locked, ".crew"):
            raise PermissionError(13, "Permission denied", path)
        return real_listdir(path)
    monkeypatch.setattr(setup.os, "listdir", _listdir)

    plan = setup.apply_migrate_to_repo(here, global_path=_widening_global(tmp_path),
                                       scan_roots=[str(scan)])

    assert [item["path"] for item in plan["widening"]["scan"]["unreadable"]] == [locked]
    assert plan["widening"]["proposedOnlyRepos"] == [here]


def test_an_entry_whose_type_cannot_be_read_is_unreadable(tmp_path, monkeypatch):
    scan = tmp_path / "src"
    here = _repo(str(tmp_path / "here"))
    os.makedirs(str(scan / "opaque"))
    real_scandir = os.scandir

    class _Entry:
        def __init__(self, entry):
            self._entry, self.name, self.path = entry, entry.name, entry.path

        def is_symlink(self):
            return self._entry.is_symlink()

        def is_dir(self, follow_symlinks=True):
            if self.name == "opaque":
                raise PermissionError(13, "Permission denied", self.path)
            return self._entry.is_dir(follow_symlinks=follow_symlinks)

    class _Scan:
        def __init__(self, path):
            self._it = real_scandir(path)

        def __enter__(self):
            return (_Entry(e) for e in self._it)

        def __exit__(self, *exc):
            self._it.close()

    monkeypatch.setattr(setup.os, "scandir", _Scan)

    plan = setup.apply_migrate_to_repo(here, global_path=_widening_global(tmp_path),
                                       scan_roots=[str(scan)])

    unreadable = plan["widening"]["scan"]["unreadable"]
    assert [item["path"] for item in unreadable] == [os.path.join(os.path.realpath(scan),
                                                                  "opaque")]
    assert setup.widening_refusal(plan["widening"])


def test_a_symlinked_crew_directory_is_not_followed(tmp_path):
    scan = tmp_path / "src"
    here = _repo(str(tmp_path / "here"))
    outside = _repo(str(tmp_path / "outside"))
    linked = scan / "linked"
    os.makedirs(str(linked))
    try:
        os.symlink(os.path.join(outside, ".crew"), str(linked / ".crew"),
                   target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform cannot create a symlink")

    plan = setup.apply_migrate_to_repo(here, global_path=_widening_global(tmp_path),
                                       scan_roots=[str(scan)])

    scan_result = plan["widening"]["scan"]
    assert scan_result["found"] == []
    assert [item["path"] for item in scan_result["unreadable"]] == [os.path.realpath(linked)]
    assert outside not in plan["widening"]["proposedOnlyRepos"]


def test_yes_widen_refuses_when_a_candidate_could_not_be_read(tmp_path, capsys):
    scan = tmp_path / "src"
    here = _repo(str(tmp_path / "here"))
    _repo(str(scan / "ok"))
    broken = _repo(str(scan / "broken"), raw="{not json")
    global_path = _widening_global(tmp_path)
    before = (_read(global_path), _read(os.path.join(here, ".crew", "config.json")))

    code = setup.main(["--root", here, "--global-path", global_path, "apply-migrate",
                       "--scan-root", str(scan), "--yes-widen"])

    assert code == 1
    assert broken in capsys.readouterr().err
    assert (_read(global_path), _read(os.path.join(here, ".crew", "config.json"))) == before


def test_yes_widen_refuses_an_empty_proposal(tmp_path, capsys):
    here = _repo(str(tmp_path / "here"), enabled=False)
    _repo(str(tmp_path / "here"), name="crew.json", enabled=False)
    global_path = _widening_global(tmp_path)
    repo_files = [os.path.join(here, ".crew", n) for n in ("config.json", "crew.json")]
    before = [_read(p) for p in repo_files]

    code = setup.main(["--root", here, "--global-path", global_path, "apply-migrate",
                       "--yes-widen"])

    assert code == 1
    assert "--scan-root" in capsys.readouterr().err
    on_disk = crew_config.read_global_config(global_path)
    assert on_disk["context"]["autoClear"].get("onlyRepos") is None
    assert [_read(p) for p in repo_files] == before


def test_yes_widen_with_scan_root_writes_the_scanned_list(tmp_path):
    scan = tmp_path / "src"
    here = _repo(str(tmp_path / "here"))
    other = _repo(str(scan / "other"))
    global_path = _widening_global(tmp_path)

    plan = setup.apply_migrate_to_repo(here, global_path=global_path, yes_widen=True,
                                       scan_roots=[str(scan)])

    assert plan["wideningApplied"] is True
    on_disk = crew_config.read_global_config(global_path)
    assert on_disk["context"]["autoClear"]["onlyRepos"] == sorted([here, other])


def test_scan_never_writes_to_a_scanned_repo(tmp_path):
    scan = tmp_path / "src"
    here = _repo(str(scan / "here"))
    _repo(str(scan / "a"))
    _repo(str(scan / "b"), name="crew.json")
    _repo(str(scan / "c"), enabled=False)
    before = {p: b for p, b in _snapshot(str(scan)).items()
              if not p.startswith(os.path.join(here, ""))}

    setup.apply_migrate_to_repo(here, global_path=_widening_global(tmp_path),
                                yes_widen=True, scan_roots=[str(scan)])

    after = {p: b for p, b in _snapshot(str(scan)).items()
             if not p.startswith(os.path.join(here, ""))}
    assert after == before


def test_scan_root_and_depth_usage_errors(tmp_path, capsys):
    here = _repo(str(tmp_path / "here"))
    global_path = _widening_global(tmp_path)
    before = (_read(global_path), _read(os.path.join(here, ".crew", "config.json")))
    missing = str(tmp_path / "missing")

    assert setup.main(["--root", here, "--global-path", global_path, "apply-migrate",
                       "--scan-root", missing, "--yes-widen"]) == 1
    assert missing in capsys.readouterr().err
    assert (_read(global_path), _read(os.path.join(here, ".crew", "config.json"))) == before

    for argv in (["--scan-root", str(tmp_path), "--scan-depth", "0"], ["--scan-depth", "2"]):
        try:
            setup.main(["--root", here, "--global-path", global_path, "apply-migrate"]
                       + argv)
            assert False, "expected a usage error"
        except SystemExit as exc:
            assert exc.code == 2
    assert (_read(global_path), _read(os.path.join(here, ".crew", "config.json"))) == before


def test_scan_skipped_when_there_is_no_widening(tmp_path):
    scan = tmp_path / "src"
    here = _repo(str(tmp_path / "here"))
    _repo(str(scan / "other"))
    global_path = _widening_global(tmp_path)
    setup.apply_onlyRepos_narrowing(["/x"], consent=True, path=global_path)

    plan = setup.apply_migrate_to_repo(here, global_path=global_path,
                                       scan_roots=[str(scan)])

    assert plan["widening"]["widening"] is False
    assert "scan" not in plan["widening"]


def test_apply_migrate_notes_name_their_file(tmp_path):
    root = str(tmp_path / "repo")
    block = {"autoClear": {"method": "windows", "enabled": True, "onlyRepos": []}}
    _write_config_json(root, block)
    _write_crew_json(root, block)

    plan = setup.apply_migrate_to_repo(root, global_path=str(tmp_path / "g.json"))

    assert plan["notes"]
    assert all(note.startswith((".crew/config.json: ", ".crew/crew.json: "))
               for note in plan["notes"])
    assert len(set(plan["notes"])) == len(plan["notes"])


def test_forbidden_words_check_covers_a_scan_with_found_and_unreadable():
    samples = setup.forbidden_word_samples()
    assert any("Could not read 1" in s and "found 1 other" in s for s in samples)
    assert any("refused --yes-widen" in s and "empty" in s for s in samples)
    assert any("refused --yes-widen" in s and "could not be read" in s for s in samples)
