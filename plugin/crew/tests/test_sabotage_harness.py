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
import importlib.util
import os
import shutil
import signal
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import sabotage
import sabotage_platform


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


def _report(passed=0, failed=0, errored=0, skipped=0, names=None):
    names = names if names is not None else [
        f"t{i}" for i in range(passed + failed + errored + skipped)]
    return {"names": names, "passed": passed, "failed": failed,
            "errored": errored, "skipped": skipped,
            "skip_reason": "off this host" if skipped else ""}


def _caught(_test):
    """A run_test stub: the target test failed for real (RED)."""
    return (sabotage._REAL_TEST_FAILURE, "", _report(failed=1), ["t0"], 0.1,
            False)


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
                        _caught)

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
                        _caught)

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
                        _caught)

    assert sabotage.main() == 0
    assert "SABOTAGE SUITE: PASS" in capsys.readouterr().out
    assert sabotage.digest(target) == pristine
    assert not os.path.exists(target + ".bak")


def test_every_shipped_anchor_is_present_in_its_target_exactly_once():
    """The one test here that reads real crew sources -- read-only, never written.

    `apply_mutation` returns False when an anchor is missing or ambiguous, and
    `main` reports that as ANCHOR LOST. But nothing reports it until somebody
    pays for a full mutation run, and a full run is minutes per mutation. So an
    ordinary edit that deletes the line a mutation aims at leaves the table
    silently pointing at nothing: the mutation stops testing anything and the
    suite stops being able to say so. That happened in this change -- an edit
    removed `cfg = crew_state.load_config(root) or {}` from `crew_config.py`
    and orphaned the mutation anchored to it.

    This is the cheap standing check for it. Anchors are `find` strings, so the
    same drift also breaks a mutation that is now ambiguous (two hits), which
    `apply_mutation` refuses just as hard as zero.
    """
    seen = {}
    orphans = []
    for label, target, find, _replace, _test in sabotage.MUTATIONS:
        if target not in seen:
            seen[target] = sabotage.read(target)
        hits = seen[target].count(find)
        if hits != 1:
            orphans.append(f"{hits} hit(s) for {label} in "
                           f"{os.path.basename(target)}")
    assert not orphans, "\n".join(orphans)
    assert len(sabotage.MUTATIONS) > 100, (
        "the table shrank -- a mutation was deleted rather than re-anchored")


# --- T-0080: the per-entry bound ---------------------------------------------

def test_main_reports_a_timed_out_entry_as_unproven_and_fails(tmp_path, monkeypatch,
                                                              capsys):
    """A timeout is could-not-tell: it fails the suite and never reads as RED."""
    target = _target(tmp_path)
    pristine = sabotage.digest(target)
    monkeypatch.delenv("CREW_SABOTAGE_TIMEOUT_S", raising=False)
    monkeypatch.setattr(sabotage, "MUTATIONS", (
        ("a label", target, "beta", "gamma", "test_nothing"),
    ))
    # L-0608's runner: code None and timed_out True for an overrun.
    monkeypatch.setattr(sabotage, "run_test",
                        lambda _test: (None, "", None, None, 600.0, True))

    assert sabotage.main() == 1
    printed = capsys.readouterr().out
    assert "COULD-NOT-TELL -- timed out after 600s" in printed
    assert "RED (good)" not in printed
    assert "SABOTAGE SUITE: FAIL" in printed
    assert sabotage.digest(target) == pristine


@pytest.mark.parametrize("name, value", [("CREW_SABOTAGE_MEM_MB", "lots"),
                                         ("CREW_SABOTAGE_TIMEOUT_S", "0")])
def test_main_refuses_an_unreadable_limit_before_any_mutation(tmp_path, monkeypatch,
                                                              capsys, name, value):
    target = _target(tmp_path)
    pristine = sabotage.digest(target)
    monkeypatch.setenv(name, value)
    monkeypatch.setattr(sabotage, "MUTATIONS", (
        ("a label", target, "beta", "gamma", "test_nothing"),
    ))

    def _never(*_args):
        raise AssertionError("a refused run must not mutate or run a test")

    monkeypatch.setattr(sabotage, "run_test", _never)
    monkeypatch.setattr(sabotage, "apply_mutation", _never)

    assert sabotage.main() == 2
    printed = capsys.readouterr().out
    assert "REFUSING TO RUN" in printed
    assert name in printed
    assert sabotage.digest(target) == pristine


def test_main_prints_the_bound_before_the_first_mutation(tmp_path, monkeypatch, capsys):
    target = _target(tmp_path)
    monkeypatch.setenv("CREW_SABOTAGE_MEM_MB", "0")
    monkeypatch.setenv("CREW_SABOTAGE_TIMEOUT_S", "42")
    monkeypatch.setattr(sabotage, "MUTATIONS", (
        ("a label", target, "beta", "gamma", "test_nothing"),
    ))
    report = {"names": ["test_nothing"], "failed": 1, "errored": 0, "skipped": 0,
              "passed": 0, "skip_reason": ""}
    monkeypatch.setattr(sabotage, "run_test", lambda _test: (
        sabotage._REAL_TEST_FAILURE, "", report, ["test_nothing"], 0.1, False))

    assert sabotage.main() == 0
    printed = capsys.readouterr().out
    assert "bound: memory cap absent (CREW_SABOTAGE_MEM_MB=0), 42 s per entry" in printed
    assert printed.index("bound:") < printed.index("RED (good)")


def test_run_test_hands_the_limits_to_the_runner(monkeypatch):
    """L-0608 merge: sabotage.py runs each entry through
    sabotage_platform.run_target, handed T-0080's limits."""
    seen = {}

    def _runner(target, timeout=None, mem_mib=None):
        seen.update(target=target, timeout=timeout, mem=mem_mib)
        return 1, "out", None, None, 0.0, False

    monkeypatch.setenv("CREW_SABOTAGE_MEM_MB", "1234")
    monkeypatch.setenv("CREW_SABOTAGE_TIMEOUT_S", "56")
    monkeypatch.setattr(sabotage.sabotage_platform, "run_target", _runner)

    assert sabotage.run_test("tests/test_x.py::test_y")[0] == 1
    assert seen == {"target": "tests/test_x.py::test_y", "timeout": 56, "mem": 1234}


_CAP_PROBE = (
    "import resource\n"
    "def test_cap():\n"
    "    assert resource.getrlimit(resource.RLIMIT_DATA)[0] == 1234 << 20\n")


@pytest.mark.skipif(sabotage.sabotage_bound._absent(1234) is not None,  # pylint: disable=protected-access
                    reason="the memory cap is enforced on Linux 4.7+ only")
def test_run_target_runs_the_entry_under_the_memory_cap(tmp_path):
    """T-0080's cap reaches the entry's pytest through L-0608's runner."""
    code, _, report, _, _, timed_out = sabotage_platform.run_target(
        _write_probe(tmp_path, _CAP_PROBE), timeout=120, cwd=str(tmp_path), extra=(),
        mem_mib=1234)

    assert (code, timed_out, report["passed"]) == (0, False, 1)


def test_run_target_reads_its_default_limits_from_the_environment(monkeypatch):
    monkeypatch.setenv("CREW_SABOTAGE_TIMEOUT_S", "never")

    with pytest.raises(ValueError):
        sabotage_platform.run_target("tests/test_x.py::test_y")


# --- review round 2 N7: the three standalone runners are bounded too --------

_STANDALONE = ("sabotage_event_claim", "sabotage_autocycle", "sabotage_resume")


@pytest.mark.parametrize("name", _STANDALONE)
def test_a_standalone_runner_hands_pytest_to_the_bounded_runner(name, monkeypatch):
    module = __import__(name)
    seen = {}

    def _bounded(argv, cwd, env, mem_mib, timeout_s):
        seen.update(argv=argv, cwd=cwd, env=env, mem=mem_mib, timeout=timeout_s)
        return 1, ""

    monkeypatch.setenv("CREW_SABOTAGE_MEM_MB", "1234")
    monkeypatch.setenv("CREW_SABOTAGE_TIMEOUT_S", "56")
    monkeypatch.setattr(sabotage.sabotage_bound, "run", _bounded)

    result = module.run_test("tests/test_x.py::test_y")

    assert (result[0] if isinstance(result, tuple) else result) == 1
    assert "tests/test_x.py::test_y" in seen["argv"]
    assert seen["cwd"] == module.CREW
    assert (seen["mem"], seen["timeout"]) == (1234, 56)


@pytest.mark.parametrize("name", _STANDALONE)
def test_a_standalone_runner_refuses_an_unreadable_limit_before_any_mutation(
        name, monkeypatch, capsys, tmp_path):
    module = __import__(name)
    monkeypatch.setenv("CREW_SABOTAGE_TIMEOUT_S", "soon")

    def _never(*_args):
        raise AssertionError("a refused run must not run a test")

    monkeypatch.setattr(module, "run_test", _never)
    real_open = open

    def _no_write(path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        assert "w" not in mode, f"a refused run must not write {path}"
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", _no_write)

    assert module.main(["--scratch", str(tmp_path)]) == 2
    assert "CREW_SABOTAGE_TIMEOUT_S" in capsys.readouterr().out
# --- L-0608: verdicts from the junit report, platform declarations, timeout --

_V = sabotage_platform.verdict


@pytest.mark.parametrize("code,report,collected,timed_out,want,ok", [
    (None, None, None, True, "COULD-NOT-TELL -- timed out", False),
    (1, None, None, False, "COULD-NOT-TELL -- no test report", False),
    (0, None, None, False, "COULD-NOT-TELL -- no test report", False),
    (0, _report(skipped=2), ["t0", "t1"], False,
     "COULD-NOT-TELL -- target skipped (off this host)", False),
    (0, _report(), [], False, "COULD-NOT-TELL -- target skipped (no case ran)",
     False),
    (0, _report(passed=1, skipped=1), ["t0", "t1"], False, "STILL GREEN", False),
    (1, _report(errored=1), ["t0"], False, "RED BUT UNPROVEN -- exit 1, 1 errored",
     False),
    (1, _report(failed=1, skipped=1), ["t0", "t1"], False,
     "RED BUT UNPROVEN -- exit 1, partial: 1 skipped", False),
    (1, _report(failed=1), ["t0", "t1"], False,
     "RED BUT UNPROVEN -- exit 1, partial: 1 unrun", False),
    (1, _report(failed=1), None, False,
     "RED BUT UNPROVEN -- exit 1, collection not recorded", False),
    (1, _report(passed=1), ["t0"], False,
     "RED BUT UNPROVEN -- exit 1, no failing case", False),
    (4, _report(), [], False, "RED BUT UNPROVEN -- exit 4", False),
    (1, _report(failed=1), ["t0"], False, "RED (good)", True),
    (1, _report(failed=1, passed=2), ["t0", "t1", "t2"], False, "RED (good)",
     True),
], ids=["timeout", "exit1-no-report", "exit0-no-report", "all-skipped",
        "none-collected", "pass-beside-skip", "error", "fail-beside-skip",
        "fail-with-unrun", "no-collection", "exit1-no-failure", "exit4",
        "red", "red-with-passing-siblings"])
def test_a_verdict_is_red_only_when_the_report_proves_it(
        code, report, collected, timed_out, want, ok):
    """must-block / must-allow. A skipped, errored, partial or unreported run
    never reads as caught; only a complete report with a failure does."""
    text, good = _V(code, report, collected, timed_out, 1.0)
    assert text.startswith(want), text
    assert good is ok


def test_junit_outcome_counts_each_kind_of_case(tmp_path):
    report = tmp_path / "r.xml"
    report.write_text(
        '<testsuites><testsuite>'
        '<testcase name="a[1]"/>'
        '<testcase name="a[2]"><failure message="x"/></testcase>'
        '<testcase name="a[3]"><error message="y"/></testcase>'
        '<testcase name="a[4]"><skipped message="needs Windows"/></testcase>'
        '</testsuite></testsuites>', encoding="utf-8")
    got = sabotage_platform.junit_outcome(str(report))
    assert got == {"names": ["a[1]", "a[2]", "a[3]", "a[4]"], "passed": 1,
                   "failed": 1, "errored": 1, "skipped": 1,
                   "skip_reason": "needs Windows"}
    assert sabotage_platform.junit_outcome(str(tmp_path / "absent.xml")) is None


def test_an_entry_declared_for_another_platform_is_not_applied(
        tmp_path, monkeypatch, capsys):
    """must-allow. Declared and not this host: the source is never touched,
    no test runs, the suite still passes, and the summary counts it."""
    target = _target(tmp_path)
    pristine = sabotage.digest(target)
    monkeypatch.setattr(sabotage, "MUTATIONS", (
        ("a windows label", target, "beta", "gamma", "test_nothing"),
        ("a plain label", target, "alpha", "omega", "test_nothing"),
    ))
    monkeypatch.setitem(sabotage_platform.PLATFORM_ONLY, "a windows label",
                        (frozenset({"elsewhere"}), "test"))
    ran = []

    def _run(test):
        ran.append(test)
        return _caught(test)

    monkeypatch.setattr(sabotage, "run_test", _run)

    assert sabotage.main() == 0
    printed = capsys.readouterr().out
    assert "PLATFORM-ONLY, NOT EXERCISED (elsewhere)" in printed
    assert "(1 platform-only, not exercised on" in printed
    assert "SABOTAGE SUITE: PASS" in printed
    assert ran == ["test_nothing"]
    assert sabotage.digest(target) == pristine


def test_a_declared_entry_that_skips_on_its_own_platform_fails(
        tmp_path, monkeypatch, capsys):
    """must-block. On its own platform a declared entry is applied, and its
    skip means the test could not run where it was supposed to."""
    target = _target(tmp_path)
    host = sabotage_platform.host_platform()
    monkeypatch.setattr(sabotage, "MUTATIONS", (
        ("a here label", target, "beta", "gamma", "test_nothing"),
    ))
    monkeypatch.setitem(sabotage_platform.PLATFORM_ONLY, "a here label",
                        (frozenset({host}), "test"))
    monkeypatch.setattr(sabotage, "run_test", lambda _t: (
        0, "", _report(skipped=1), ["t0"], 0.1, False))

    assert sabotage.main() == 1
    printed = capsys.readouterr().out
    assert "COULD-NOT-TELL -- target skipped" in printed
    assert "SABOTAGE SUITE: FAIL (0 platform-only" in printed


def _labels_with_pwsh(monkeypatch, present):
    """`sabotage.MUTATIONS` labels as a host with or without pwsh builds them.

    `sabotage_tooling` appends its .ps1 entries only `if shutil.which("pwsh")`,
    so the shipped list depends on the host. Fresh copies are loaded under
    their own names with `shutil.which` patched; the imported modules every
    other test uses are not reloaded, and `sys.modules` is put back after.
    """
    real_which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: (
        ("/fake/pwsh" if present else None) if cmd == "pwsh"
        else real_which(cmd, *a, **k)))
    fresh = {}
    for name in ("sabotage_tooling", "sabotage"):
        spec = importlib.util.spec_from_file_location(
            f"_fresh_{name}", os.path.join(os.path.dirname(sabotage.__file__),
                                           name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setitem(sys.modules, name, module)
        fresh[name] = module
    monkeypatch.setattr(shutil, "which", real_which)
    return [m[0] for m in fresh["sabotage"].MUTATIONS]


def test_every_platform_only_label_names_exactly_one_shipped_mutation(
        monkeypatch):
    """must-block: a host WITH pwsh ships every entry, so there each label
    must name exactly one -- a typo'd label counts 0 and fails on every host,
    pwsh or not. Without pwsh the .ps1 entries are absent, so a label may
    count 0 there, never 2; that is checked on the simulated host and on
    this one."""
    with_pwsh = _labels_with_pwsh(monkeypatch, present=True)
    for label in sabotage_platform.PLATFORM_ONLY:
        assert with_pwsh.count(label) == 1, label
    without_pwsh = _labels_with_pwsh(monkeypatch, present=False)
    here = [m[0] for m in sabotage.MUTATIONS]
    for label in sabotage_platform.PLATFORM_ONLY:
        assert without_pwsh.count(label) <= 1, label
        assert here.count(label) <= 1, label
    # The pwsh branch was really taken: some declared label exists only there.
    assert any(without_pwsh.count(label) == 0
               for label in sabotage_platform.PLATFORM_ONLY)


def test_a_typod_platform_only_label_fails_on_a_host_with_pwsh(monkeypatch):
    """must-block for the check above: an unknown label must not collapse
    into a pass because pwsh-gated labels are allowed to be missing."""
    monkeypatch.setitem(sabotage_platform.PLATFORM_ONLY,
                        "the PowerShell gate lets a dearer measurment replace",
                        (frozenset({"win"}), "test"))
    with pytest.raises(AssertionError):
        test_every_platform_only_label_names_exactly_one_shipped_mutation(
            monkeypatch)


def _write_probe(tmp_path, body):
    (tmp_path / "test_probe.py").write_text(body, encoding="utf-8")
    return str(tmp_path / "test_probe.py")


_PARAMS = (
    "import pytest\n"
    "@pytest.mark.parametrize('n', [1, 2, 3])\n"
    "def test_p(n):\n"
    "    assert n != 1\n")


@pytest.mark.parametrize("addopts", [None, "-x"])
def test_every_case_of_a_parametrized_target_runs(tmp_path, monkeypatch,
                                                  addopts):
    """A failing first case must not stop the rest: no `-x` of our own, and an
    inherited PYTEST_ADDOPTS=-x is dropped from the child's environment."""
    if addopts:
        monkeypatch.setenv("PYTEST_ADDOPTS", addopts)
    code, _, report, collected, seconds, timed_out = sabotage_platform.run_target(
        _write_probe(tmp_path, _PARAMS), timeout=120, cwd=str(tmp_path),
        extra=())
    assert report["names"] == ["test_p[1]", "test_p[2]", "test_p[3]"]
    assert collected == report["names"]
    assert _V(code, report, collected, timed_out, seconds) == ("RED (good)",
                                                               True)


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _gone_within(pid, seconds=10.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return False


_SPAWN = (
    "import os, subprocess, sys, time\n"
    "def test_spawn():\n"
    "    child = subprocess.Popen([sys.executable, '-c',"
    " 'import time; time.sleep(120)'])\n"
    "    with open(os.environ['PROBE_PIDS'], 'w') as h:\n"
    "        h.write(f'{os.getpid()} {child.pid}')\n"
    "    {tail}\n")


@pytest.mark.skipif(os.name == "nt", reason="the Windows job-object path is "
                    "exercised on a Windows host (win-repo-2)")
@pytest.mark.parametrize("tail,timeout,overrun", [
    ("time.sleep(120)", 3, True),
    ("pass", 60, False),
], ids=["overrun", "parent-exited"])
def test_an_entry_leaves_no_process_behind(tmp_path, monkeypatch, tail,
                                           timeout, overrun):
    """An overrun is COULD-NOT-TELL and its whole tree is killed; and a
    grandchild that outlives a finished pytest is killed too, so nothing an
    entry started can contend with the next one."""
    pids = tmp_path / "pids"
    monkeypatch.setenv("PROBE_PIDS", str(pids))
    result = sabotage_platform.run_target(
        _write_probe(tmp_path, _SPAWN.replace("{tail}", tail)),
        timeout=timeout, cwd=str(tmp_path), extra=())
    assert result[5] is overrun
    if overrun:
        assert _V(*[result[i] for i in (0, 2, 3, 5, 4)])[0].startswith(
            "COULD-NOT-TELL -- timed out")
    for pid in map(int, pids.read_text(encoding="utf-8").split()):
        assert _gone_within(pid), pid


def test_an_entry_no_job_object_could_hold_is_could_not_tell(tmp_path, monkeypatch):
    """Review of d0b7fd8e (L-0608 port), FIX: on Windows taskkill /T cannot reach
    a grandchild once pytest has exited, so without a job object the entry is
    could-not-tell, never a verdict."""
    monkeypatch.setattr(sabotage_platform, "_NEEDS_JOB", True)
    monkeypatch.setattr(sabotage_platform, "_new_job", lambda _proc: None)
    result = sabotage_platform.run_target(
        _write_probe(tmp_path, "def test_red():\n    assert False\n"),
        timeout=120, cwd=str(tmp_path), extra=())

    assert _V(*[result[i] for i in (0, 2, 3, 5, 4)]) == (
        "COULD-NOT-TELL -- no job object held the entry's tree", False)


def test_the_summary_names_the_platform_only_count():
    assert sabotage_platform.summary(True, 3, "linux") == (
        "\nSABOTAGE SUITE: PASS (3 platform-only, not exercised on linux)")
    assert sabotage_platform.summary(False, 0, "win").startswith(
        "\nSABOTAGE SUITE: FAIL (0 platform-only")
