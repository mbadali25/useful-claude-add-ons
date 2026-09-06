"""The sabotage harness edits real source in place, so its restore is a gate.

`d362a2bd` shipped a live mutation in `crew_state.py`: a killed run skipped the
`finally`, the next run copied the mutated file over the good backup, and the
suite still printed PASS because nothing compared the restored bytes to
anything. Found by a human reading a diff, which is the one thing a regression
suite exists to stop being the only detector.

None of these tests touch a real crew source file. Every one builds a throwaway
target under `tmp_path`, because a test for a harness that corrupts files must
not be able to corrupt the files it is testing against.
"""
import atexit
import os
import signal

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import sabotage


@pytest.fixture(autouse=True)
def _no_live_targets():
    """`_LIVE` is module state and the handlers are process state.

    A test that leaves a name in `_LIVE` would make the NEXT test's
    `_restore_all` reach for a file under a torn-down tmp_path; a test that
    leaves crew's SIGTERM handler installed changes how the pytest process
    itself dies. `main()` installs both, so every test that calls it has to
    put both back.
    """
    handlers = {}
    for name in ("SIGTERM", "SIGINT", "SIGBREAK", "SIGHUP"):
        num = getattr(signal, name, None)
        if num is not None:
            handlers[num] = signal.getsignal(num)
    sabotage._LIVE.clear()  # pylint: disable=protected-access
    sabotage._PRISTINE.clear()  # pylint: disable=protected-access
    yield
    sabotage._LIVE.clear()  # pylint: disable=protected-access
    sabotage._PRISTINE.clear()  # pylint: disable=protected-access
    atexit.unregister(sabotage._restore_all)  # pylint: disable=protected-access
    for num, handler in handlers.items():
        if handler is not None:
            signal.signal(num, handler)


def _text(path):
    """A file's whole contents.

    A named helper rather than `open(...).read()` inline: the bare form leaves
    the handle to the garbage collector, which pylint flags as R1732 and which
    on Windows can still hold the file when the next line wants to replace it.
    """
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _target(tmp_path, text="alpha\nbeta\n"):
    path = tmp_path / "subject.py"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_digest_changes_when_one_byte_does(tmp_path):
    target = _target(tmp_path)
    before = sabotage.digest(target)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write("x")
    assert sabotage.digest(target) != before


def test_a_mutation_is_restored_byte_for_byte(tmp_path):
    target = _target(tmp_path)
    pristine = sabotage.digest(target)

    assert sabotage.apply_mutation(target, "beta", "gamma") is True
    assert "gamma" in _text(target)
    assert target in sabotage._LIVE  # pylint: disable=protected-access

    sabotage.restore(target)
    assert sabotage.digest(target) == pristine
    assert target not in sabotage._LIVE  # pylint: disable=protected-access


def test_an_anchor_that_is_not_unique_mutates_nothing(tmp_path):
    target = _target(tmp_path, "beta\nbeta\n")
    pristine = sabotage.digest(target)
    assert sabotage.apply_mutation(target, "beta", "gamma") is False
    assert sabotage.digest(target) == pristine
    assert not os.path.exists(target + ".bak")


def test_apply_mutation_refuses_to_overwrite_an_existing_backup(tmp_path):
    """Defect 2: the next run destroying the only good copy.

    The `.bak` here holds the original and the target holds the mutation --
    exactly the state a killed run leaves. A `shutil.copy` at this point would
    replace the last good copy with the mutated file, permanently.
    """
    target = _target(tmp_path, "mutated\n")
    with open(target + ".bak", "w", encoding="utf-8") as handle:
        handle.write("original\n")
    backup_before = sabotage.digest(target + ".bak")

    with pytest.raises(RuntimeError) as caught:
        sabotage.apply_mutation(target, "mutated", "worse")

    assert ".bak already exists" in str(caught.value)
    assert sabotage.digest(target + ".bak") == backup_before
    assert _text(target) == "mutated\n"


def test_restore_all_puts_back_every_live_target(tmp_path):
    """What the signal and atexit paths call. `finally` unwinds on an
    exception and on KeyboardInterrupt; a SIGTERM from an external timeout
    does not unwind at all, which is how the shipped mutation survived."""
    first = str(tmp_path / "one.py")
    second = str(tmp_path / "two.py")
    for path in (first, second):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("keep\n")
    pristine = {p: sabotage.digest(p) for p in (first, second)}

    assert sabotage.apply_mutation(first, "keep", "lose") is True
    assert sabotage.apply_mutation(second, "keep", "lose") is True

    sabotage._restore_all()  # pylint: disable=protected-access

    assert {p: sabotage.digest(p) for p in (first, second)} == pristine
    assert not sabotage._LIVE  # pylint: disable=protected-access


def test_a_failed_restore_stays_registered_for_the_next_attempt(tmp_path):
    """`_restore_all` must not clear `_LIVE` wholesale.

    A signal-path restore that fails is the case the atexit pass exists for.
    Clearing every name regardless would forget it, and the only symptom is a
    file left mutated after a signal -- no error, no output, nothing to see.
    """
    target = _target(tmp_path)
    assert sabotage.apply_mutation(target, "beta", "gamma") is True

    def _restore_that_raises(_path):
        raise OSError("read-only target")

    original = sabotage.restore
    sabotage.restore = _restore_that_raises
    try:
        assert sabotage._restore_all() is False  # pylint: disable=protected-access
    finally:
        sabotage.restore = original

    assert target in sabotage._LIVE, (  # pylint: disable=protected-access
        "a restore that raised must stay registered so atexit tries again")
    # And the second pass, with a working restore, actually gets it back.
    assert sabotage._restore_all() is True  # pylint: disable=protected-access
    assert "beta" in _text(target)


def test_restore_all_verifies_and_does_not_raise_from_signal_context(tmp_path):
    """The signal and atexit paths verify too, not just the loop's `finally`.

    Verifying on one path and claiming it on all four is the exact shape this
    harness exists to catch, so the claim is checked here rather than trusted.
    `_verify` must also never raise: it runs where an exception would replace
    the reason the process is exiting with a traceback about the cleanup.
    """
    target = _target(tmp_path)
    assert sabotage.apply_mutation(target, "beta", "gamma") is True
    # Record a digest that the restored file will NOT match.
    sabotage._PRISTINE[target] = "0" * 64  # pylint: disable=protected-access

    assert sabotage._restore_all() is False  # pylint: disable=protected-access
    assert target not in sabotage._LIVE  # pylint: disable=protected-access


def test_verify_is_silent_about_a_target_it_has_no_answer_key_for(tmp_path):
    target = _target(tmp_path)
    assert sabotage._verify(target) is True  # pylint: disable=protected-access


def test_a_backup_is_never_left_partial(tmp_path):
    """Defect 4. The startup guard treats any `.bak` as the only good copy and
    tells the user to move it over the target, so a half-written one turns that
    instruction into the thing that destroys the intact source. The backup is
    built under `.bak.partial` and renamed, so it is complete or absent."""
    target = _target(tmp_path)
    pristine = sabotage.digest(target)

    def _copy_that_dies_midway(_src, dst):
        with open(dst, "w", encoding="utf-8") as handle:
            handle.write("half")
        raise KeyboardInterrupt

    original = sabotage.shutil.copy
    sabotage.shutil.copy = _copy_that_dies_midway
    try:
        with pytest.raises(KeyboardInterrupt):
            sabotage.apply_mutation(target, "beta", "gamma")
    finally:
        sabotage.shutil.copy = original

    assert not os.path.exists(target + ".bak"), (
        "a partial backup must never appear under the name the startup guard "
        "trusts")
    assert not os.path.exists(target + ".bak.partial")
    assert sabotage.digest(target) == pristine


def test_main_discards_an_interrupted_backup_before_it_mutates(tmp_path,
                                                               monkeypatch,
                                                               capsys):
    """A `.bak.partial` is litter, not evidence: the target was never touched,
    which is the whole reason the backup is built under a second name. Removing
    it is safe where removing a `.bak` never is.

    The observation point matters. Asserting the partial is gone AFTER the run
    proves nothing -- `apply_mutation` writes its own backup to that same name
    and renames it away, so the file vanishes whether or not the sweep exists.
    The first draft of this test asserted exactly that and stayed green with
    the sweep deleted; the sabotage run caught it. What is checked instead is
    the state at the moment the first mutation is applied, which only the sweep
    can produce.
    """
    target = _target(tmp_path)
    pristine = sabotage.digest(target)
    with open(target + ".bak.partial", "w", encoding="utf-8") as handle:
        handle.write("half")

    monkeypatch.setattr(sabotage, "MUTATIONS", (
        ("a label", target, "beta", "gamma", "test_nothing"),
    ))
    monkeypatch.setattr(sabotage, "run_test",
                        lambda _test: (sabotage._REAL_TEST_FAILURE, ""))

    seen = {}
    real_apply = sabotage.apply_mutation

    def _watched(path, find, replace):
        seen["partial"] = os.path.exists(path + ".bak.partial")
        return real_apply(path, find, replace)

    monkeypatch.setattr(sabotage, "apply_mutation", _watched)

    assert sabotage.main() == 0
    assert seen["partial"] is False, (
        "the sweep must have run before the first mutation")
    assert "discarding an interrupted backup" in capsys.readouterr().out
    assert sabotage.digest(target) == pristine


def test_the_signal_handler_restores_then_exits_128_plus_signum(tmp_path):
    target = _target(tmp_path)
    pristine = sabotage.digest(target)
    assert sabotage.apply_mutation(target, "beta", "gamma") is True

    with pytest.raises(SystemExit) as caught:
        sabotage._on_signal(  # pylint: disable=protected-access
            signal.SIGTERM, None)

    assert caught.value.code == 128 + int(signal.SIGTERM)
    assert sabotage.digest(target) == pristine


def test_install_exit_handlers_takes_sigterm_and_survives_this_platform():
    """The names are looked up rather than referenced: `signal.SIGBREAK` is
    Windows-only and `SIGHUP` POSIX-only, so naming either directly is an
    AttributeError on the other -- at import time, taking the suite with it."""
    previous = {}
    for name in ("SIGTERM", "SIGINT", "SIGBREAK", "SIGHUP"):
        num = getattr(signal, name, None)
        if num is not None:
            previous[num] = signal.getsignal(num)
    try:
        sabotage.install_exit_handlers()
        term = signal.getsignal(signal.SIGTERM)
        assert term is sabotage._on_signal  # pylint: disable=protected-access
    finally:
        atexit.unregister(sabotage._restore_all)  # pylint: disable=protected-access
        for num, handler in previous.items():
            if handler is not None:
                signal.signal(num, handler)


def test_stale_backups_names_only_the_targets_that_have_one(tmp_path):
    clean = str(tmp_path / "clean.py")
    dirty = str(tmp_path / "dirty.py")
    for path in (clean, dirty):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("x\n")
    with open(dirty + ".bak", "w", encoding="utf-8") as handle:
        handle.write("x\n")

    assert sabotage.stale_backups([clean, dirty]) == [dirty]
    assert sabotage.stale_backups([clean]) == []


def test_main_refuses_to_start_when_a_backup_is_present(tmp_path, monkeypatch,
                                                       capsys):
    """Defect 1 and 2 together, at the level a user meets them: the run that
    would have destroyed the original stops instead, names the file, and says
    how to undo the mutation still sitting in the tree."""
    target = _target(tmp_path, "mutated\n")
    with open(target + ".bak", "w", encoding="utf-8") as handle:
        handle.write("original\n")
    backup_before = sabotage.digest(target + ".bak")

    monkeypatch.setattr(sabotage, "MUTATIONS", (
        ("a label", target, "mutated", "worse", "test_nothing"),
    ))

    def _never(_test):
        raise AssertionError("a refused run must not execute a test")

    monkeypatch.setattr(sabotage, "run_test", _never)

    assert sabotage.main() == 2
    printed = capsys.readouterr().out
    assert "REFUSING TO RUN" in printed
    assert f"mv {target}.bak {target}" in printed
    assert sabotage.digest(target + ".bak") == backup_before
    assert _text(target) == "mutated\n"


def test_main_reports_a_restore_that_did_not_take(tmp_path, monkeypatch,
                                                  capsys):
    """Defect 3. The mutation goes red as it should, so `ok` from the mutation
    alone is True -- this run must still FAIL, because the source it was
    supposed to put back is not what it found."""
    target = _target(tmp_path)
    monkeypatch.setattr(sabotage, "MUTATIONS", (
        ("a label", target, "beta", "gamma", "test_nothing"),
    ))
    monkeypatch.setattr(sabotage, "run_test",
                        lambda _test: (sabotage._REAL_TEST_FAILURE, ""))

    def _restore_that_does_nothing(path):
        sabotage._LIVE.discard(path)  # pylint: disable=protected-access

    monkeypatch.setattr(sabotage, "restore", _restore_that_does_nothing)

    assert sabotage.main() == 1
    printed = capsys.readouterr().out
    assert "RESTORE FAILED" in printed
    assert "SABOTAGE SUITE: FAIL" in printed
    # The mutation itself is still in the tree -- the suite says so rather
    # than reporting PASS over it, which is the whole point.
    assert "gamma" in _text(target)
    os.replace(target + ".bak", target)


def test_a_clean_run_reports_pass_and_leaves_no_backup(tmp_path, monkeypatch,
                                                       capsys):
    """must-allow. A guard that only ever refuses is not a guard."""
    target = _target(tmp_path)
    pristine = sabotage.digest(target)
    monkeypatch.setattr(sabotage, "MUTATIONS", (
        ("a label", target, "beta", "gamma", "test_nothing"),
    ))
    monkeypatch.setattr(sabotage, "run_test",
                        lambda _test: (sabotage._REAL_TEST_FAILURE, ""))

    assert sabotage.main() == 0
    assert "SABOTAGE SUITE: PASS" in capsys.readouterr().out
    assert sabotage.digest(target) == pristine
    assert not os.path.exists(target + ".bak")
