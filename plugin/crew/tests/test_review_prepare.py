"""`review_run.py --prepare`, `--resolve-run` and the `next:` line (L-0726).

`/crew:review` used to be 230 lines of shell the model copied. The mechanics
live in `review_run.py` now, and these tests hold them to what the snippets
did: the seven scenarios of `golden/prepare/` were captured from the snippets
as they were at 1e1db88a3 (`capture_prepare_goldens.py`) and `--prepare` has to
reproduce every file byte for byte, apart from the contract block, whose
producer (`review_prompt.py`) is unchanged and is checked against a direct run.
"""
import hashlib
import re
import json
import os
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import capture_prepare_goldens as cap
import review_fixtures as fx
import review_ledger
import review_run

SCRIPT = os.path.join(fx._SCRIPTS_DIR, "review_run.py")  # pylint: disable=protected-access
REVIEW_MD = os.path.join(fx.PLUGIN_ROOT, "commands", "review.md")


def _golden(scenario, name):
    path = os.path.join(cap.GOLDEN, scenario, name)
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _prepare(root, env, *extra, scratch=fx.PREPARE_SCRATCH):
    argv = [sys.executable, SCRIPT, "--root", ".", "--prepare"]
    if scratch:
        argv += ["--scratch", scratch]
    return subprocess.run(argv + list(extra), cwd=root, env=env, capture_output=True, text=True,
                          encoding="utf-8", stdin=subprocess.DEVNULL, check=False, timeout=120)


def _keys(stdout):
    out = {}
    for line in stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.isupper() or key in ("SPECIALIST",):
            out.setdefault(key, []).append(value)
    return out


def _next_lines(stdout):
    return [line for line in stdout.splitlines() if line.startswith("next:")]


@pytest.fixture(name="env")
def _env(tmp_path):
    return fx.prepare_env(tmp_path / "fakes", tmp_path / "home")


def _repo(tmp_path, scenario):
    return fx.build_prepare_repo(tmp_path / "repo", scenario)


@pytest.mark.parametrize("scenario", [s for s in fx.PREPARE_SCENARIOS if s != "empty-diff"])
def test_prepare_matches_pre_cut_goldens(tmp_path, env, scenario):
    root = _repo(tmp_path, scenario)

    done = _prepare(root, env)

    assert done.returncode == 0, done.stderr
    scratch = root / fx.PREPARE_SCRATCH
    def norm(text):
        return fx.normalise_root(text, root)

    assert _read(scratch / "changed.txt") == _golden(scenario, "changed.txt")
    assert _read(scratch / "context.txt") == _golden(scenario, "context.txt")
    assert norm(_read(scratch / "manifest.json")) == _golden(scenario, "manifest.json")
    assert norm(done.stderr) == _golden(scenario, "stderr.txt")
    contract = _read(scratch / "contract.txt").rstrip("\n")
    assert norm(_read(scratch / "prompt.txt").replace(contract, cap.CONTRACT_MARK, 1)) \
        == _golden(scenario, "prompt.txt")


@pytest.mark.parametrize("scenario", [s for s in fx.PREPARE_SCENARIOS if s != "empty-diff"])
def test_prepare_bundle_parts_match_pre_cut_hashes(tmp_path, env, scenario):
    root = _repo(tmp_path, scenario)

    _prepare(root, env)

    rows = []
    parts = root / fx.PREPARE_SCRATCH / "diff.txt.parts"
    for name in sorted(os.listdir(parts)):
        rows.append(f"{hashlib.sha256((parts / name).read_bytes()).hexdigest()}  {name}\n")
    assert "".join(rows) == _golden(scenario, "parts.sha256")


def test_prepare_split_bundle_really_splits(tmp_path, env):
    root = _repo(tmp_path, "split-bundle")

    _prepare(root, env)

    parts = os.listdir(root / fx.PREPARE_SCRATCH / "diff.txt.parts")
    assert len(parts) == 2


def test_prepare_contract_is_what_review_prompt_writes_for_the_same_inputs(tmp_path, env):
    root = _repo(tmp_path, "mixed-worktree")
    _prepare(root, env)
    scratch = root / fx.PREPARE_SCRATCH

    subprocess.run([sys.executable, os.path.join(fx._SCRIPTS_DIR, "review_prompt.py"),  # pylint: disable=protected-access
                    "--root", ".", "--ticket", fx.PREPARE_TICKET, "--manifest",
                    f"{fx.PREPARE_SCRATCH}/manifest.json", "--out",
                    str(tmp_path / "direct.txt")], cwd=root, env=env, check=True,
                   capture_output=True, stdin=subprocess.DEVNULL)

    assert _read(scratch / "contract.txt") == _read(tmp_path / "direct.txt")


def test_prepare_empty_diff_exits_before_changed_or_prompt_exist(tmp_path, env):
    root = _repo(tmp_path, "empty-diff")

    done = _prepare(root, env)

    scratch = root / fx.PREPARE_SCRATCH
    assert done.returncode == 0
    assert not (scratch / "changed.txt").exists()
    assert not (scratch / "prompt.txt").exists()
    base = _golden("empty-diff", "stdout.txt").split("nothing to review since ")[1].split(":")[0]
    assert f"nothing to review since {base}: review-patch's line above says why" in done.stdout
    assert fx.normalise_root(done.stderr, root) == _golden("empty-diff", "stderr.txt")
    assert _keys(done.stdout)["NOTHING_TO_REVIEW"] == ["1"]


@pytest.mark.parametrize("scenario", fx.PREPARE_SCENARIOS)
def test_prepare_facts_equal_what_the_snippets_echoed(tmp_path, env, scenario):
    root = _repo(tmp_path, scenario)
    facts = json.loads(_golden(scenario, "facts.json"))

    keys = _keys(_prepare(root, env).stdout)

    assert keys["AUTHORS"] == [facts["authors"]]
    assert keys["AUTHOR_SOURCE"] == [facts["author_source"]]
    assert keys["ELIGIBLE"] == [facts["eligible"]]
    assert keys["RECORD"] == [f"record={facts['record']} base={facts['base_at']} "
                              f"branch={facts['branch']}"]
    assert keys["BASE"][0].startswith(facts["base"])


# --- AC3: --prepare's own behaviour --------------------------------------------


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "absent"


def test_prepare_infers_one_active_ticket(tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    _write(root / ".work" / "INDEX.md",
           "T0 | done | x\nT1 | in progress | y\nT2 | planned | z\n")

    keys = _keys(_prepare(root, env).stdout)

    assert keys["TICKET"] == ["T1"]


@pytest.mark.parametrize("index,reason", [
    (None, "does not exist"),
    ("T0 | done | x\nT2 | planned | z\n", "no active row"),
    ("T1 | open | x\nT2 | review | z\n", "several active rows"),
])
def test_prepare_refuses_zero_or_two_active(tmp_path, env, index, reason):
    root = _repo(tmp_path, "committed-only")
    if index is None:
        os.unlink(root / ".work" / "INDEX.md")
    else:
        _write(root / ".work" / "INDEX.md", index)

    done = _prepare(root, env)

    assert (done.returncode, reason in done.stderr, "TICKET" in _keys(done.stdout)) == (
        2, True, False), done.stderr
    assert len(_next_lines(done.stdout)) == 1


def test_prepare_takes_an_explicit_ticket_over_the_index(tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    _write(root / ".work" / "INDEX.md", "T1 | open | x\nT2 | review | z\n")

    keys = _keys(_prepare(root, env, "--ticket", "T2").stdout)

    assert keys["TICKET"] == ["T2"]


def _break_index(root):
    os.unlink(root / ".work" / "INDEX.md")
    (root / ".work" / "INDEX.md").mkdir()


def _break_ledger(root):
    path = review_ledger.ledger_path(str(root), "T1")
    _write(__import__("pathlib").Path(path), "{not json")


def _break_verify_map(root):
    _write(root / ".crew" / "verify.json", "{not json")


def _break_dispatch(root):
    os.symlink("dispatch.d", root / ".work" / "dispatch.d")


def _break_models(root):
    _write(root / ".crew" / "config.json", "{not json")


@pytest.mark.skipif(os.name == "nt", reason="needs a symlink loop")
@pytest.mark.parametrize("break_it,what", [
    (_break_index, "which ticket is active"),
    (_break_ledger, "the review ledger"),
    (_break_verify_map, "the specialists"),
    (_break_dispatch, "the dispatch record"),
], ids=["index", "ledger", "verify-map", "dispatch-record"])
def test_prepare_unknown_is_not_empty(tmp_path, env, break_it, what):
    root = _repo(tmp_path, "committed-only")
    break_it(root)

    done = _prepare(root, env)

    keys = _keys(done.stdout)
    assert (done.returncode, f"could not tell {what}" in done.stderr) == (11, True), done.stderr
    assert keys.get("ELIGIBLE") != [""]
    assert len(_next_lines(done.stdout)) == 1 and "next: a review input could not be read" \
        in done.stdout


def test_prepare_an_unreadable_models_report_is_not_an_empty_eligible(tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    env = dict(env, PATH=os.path.dirname(sys.executable))
    _break_models(root)

    done = _prepare(root, env)

    assert "ELIGIBLE" not in _keys(done.stdout) or done.returncode == 11


@pytest.mark.parametrize("map_text,expect_state,expect_count", [
    (None, "absent", "0"),
    ('{"rules": []}', "read", "0"),
    ('{"rules": [{"paths": ["docs/**"], "agents": ["zz-docs"]}]}', "read", "0"),
])
def test_prepare_absent_valid_empty_and_unmatched_maps_are_three_outputs(
        tmp_path, env, map_text, expect_state, expect_count):
    root = _repo(tmp_path, "committed-only")
    if map_text is not None:
        _write(root / ".crew" / "verify.json", map_text)

    keys = _keys(_prepare(root, env).stdout)

    assert (keys["VERIFY_MAP"], keys["SPECIALISTS"]) == ([expect_state], [expect_count])


def test_prepare_specialists_and_gaps(tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    _write(root / "sql" / "m.sql", "select 1;\n")
    _write(root / ".crew" / "verify.json", json.dumps({"rules": [
        {"paths": ["sql/**"], "agents": ["zz-installed", "zz-missing"]},
        {"paths": ["docs/**"], "agents": ["zz-not-matched"]},
        {"paths": ["src/*.py", "sql/**"], "agents": ["zz-installed"]}]}))
    _write(root / ".claude" / "agents" / "zz-installed.md",
           "---\nname: zz-installed\n---\nbody\n")

    keys = _keys(_prepare(root, env).stdout)

    assert keys["SPECIALISTS"] == ["2"]
    assert keys["SPECIALIST"] == ["zz-installed installed files=sql/m.sql,src/a.py",
                                  "zz-missing MISSING files=sql/m.sql"]


@pytest.mark.parametrize("stamp,stale", [(None, "0"), (1767225600, "0"), (1767225599, "1")])
def test_prepare_staleness_uses_resolved_base(tmp_path, env, stamp, stale):
    root = _repo(tmp_path, "recorded-start")
    if stamp is not None:
        record = root / ".work" / "dispatch.json"
        _write(record, "{}")
        os.utime(record, (stamp, stamp))

    keys = _keys(_prepare(root, env).stdout)

    # the ticket started at 1767225600; main's tip (the merge-base) is one
    # second later, so a record at 1767225600 is fresh only against the start
    assert keys["STALE"] == [stale]
    assert keys["RECORD"] == [f"record={stamp or 0} base=1767225600 branch=t1"]


def test_prepare_eligible_order_matches_models(tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    _write(root / ".crew" / "config.json", json.dumps({"qa": {"order": ["kimi", "codex"]}}))
    report = subprocess.run([sys.executable, os.path.join(fx._SCRIPTS_DIR, "crew_config.py"),  # pylint: disable=protected-access
                             "--root", ".", "--models", "--json"], cwd=root, env=env,
                            capture_output=True, text=True, check=True).stdout

    keys = _keys(_prepare(root, env).stdout)

    expected = [c["provider"] for c in json.loads(report)["qaFallThrough"] if c["eligible"]]
    assert expected[:2] == ["kimi", "codex"]
    assert keys["ELIGIBLE"] == [" ".join(expected)]


def test_eligible_drops_a_provider_review_run_cannot_launch():
    said = []
    report = {"qaFallThrough": [{"provider": "gemini", "eligible": True},
                                {"provider": "kimi", "eligible": True},
                                {"provider": "codex", "eligible": False},
                                {"provider": "claude", "eligible": True}]}

    result = review_run.eligible(report, said.append)

    assert result == ["kimi", "claude"]
    assert said == ["review: gemini is eligible but has no review runner - skipped\n"]


def test_prepare_strikes_the_authors_family(tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    _write(root / ".crew" / "config.json", json.dumps({"dev": {"provider": "codex"}}))

    keys = _keys(_prepare(root, env).stdout)

    assert keys["AUTHORS"] == ["gpt"]
    assert "codex" not in keys["ELIGIBLE"][0].split()


def test_prepare_reserves_nothing(tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    ok, number, _ = review_ledger.reserve(str(root), "T1", "codex", "")
    assert (ok, number) == (True, 1)
    ledger = __import__("pathlib").Path(review_ledger.ledger_path(str(root), "T1"))
    before = _digest(ledger)

    done = _prepare(root, env)

    assert done.returncode == 0
    assert _digest(ledger) == before
    assert _keys(done.stdout)["ROUNDS_LEFT"] == ["1"]


def test_prepare_claims_a_branch_scoped_scratch_when_none_is_given(tmp_path, env):
    root = _repo(tmp_path, "committed-only")

    keys = _keys(_prepare(root, env, scratch=None).stdout)

    shown = keys["SCRATCH"][0]
    assert shown.startswith(".work/review/t1--") and (root / shown).is_dir()


def test_prepare_launches_no_reviewer(tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    calls = tmp_path / "calls.txt"
    env = dict(env, FAKE_REVIEWER_STATE=str(calls), FAKE_REVIEWER_MODE="a,b")

    _prepare(root, env)

    assert not calls.exists()


def test_prepare_next_walks_eligible_in_order(tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    _write(root / ".crew" / "config.json", json.dumps({"qa": {"order": ["kimi", "codex"]}}))

    out = _prepare(root, env).stdout

    assert _next_lines(out)[0].startswith("next: run python3 ")
    assert "--provider kimi" in _next_lines(out)[0]


def test_prepare_next_names_the_specialists_step_first(tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    _write(root / ".crew" / "verify.json", json.dumps(
        {"rules": [{"paths": ["src/**"], "agents": ["zz-missing"]}]}))

    out = _prepare(root, env).stdout

    assert _next_lines(out)[0].startswith("next: step 1: dispatch the SPECIALISTS agents")


# --- --resolve-run: the Codex probe's answer becomes FALLBACK / RUN_PROVIDER --


def _resolve(root, env, status, *extra):
    done = _prepare(root, env)
    keys = _keys(done.stdout)
    argv = [sys.executable, SCRIPT, "--root", ".", "--ticket", "T1", "--scratch", fx.PREPARE_SCRATCH,
            "--resolve-run", "--probe-status", str(status), "--authors", keys["AUTHORS"][0],
            "--author-source", keys["AUTHOR_SOURCE"][0]] + list(extra)
    return subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False, timeout=120)


def test_resolve_run_ok_probe_runs_codex(tmp_path, env):
    root = _repo(tmp_path, "committed-only")

    done = _resolve(root, env, 0, "--model", "gpt-5")

    keys = _keys(done.stdout)
    assert (keys["RUN_PROVIDER"], keys["RUN_MODEL"]) == (["codex"], ["gpt-5"])
    assert "FALLBACK" not in keys


@pytest.mark.parametrize("status", [5, 6, 7])
def test_resolve_run_failed_probe_does_not_launch_codex_unpinned(tmp_path, env, status):
    root = _repo(tmp_path, "committed-only")

    done = _resolve(root, env, status)

    keys = _keys(done.stdout)
    assert keys["RUN_PROVIDER"] != ["codex"]
    assert len(_next_lines(done.stdout)) == 1
    assert f"codex probe exit {status}" in done.stdout or "FALLBACK" in done.stdout


# --- AC4: every exit path ends with exactly one `next:` line -------------------


def _main_in_process(argv, capsys):
    code = review_run.main(argv)
    out = capsys.readouterr().out
    return code, out


def _lines(out):
    return [line for line in out.split("\n") if line]


def _assert_one_next_last(out, needle):
    lines = _lines(out)
    nexts = [line for line in lines if line.startswith("next:")]
    assert len(nexts) == 1 and lines[-1] == nexts[0], out
    assert needle in nexts[0], nexts[0]


@pytest.fixture(name="paths")
def _paths(tmp_path, monkeypatch):
    repo = fx.init_repo(tmp_path / "r")
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    fx.bundle(repo, scratch)
    (scratch / "models.json").write_text(json.dumps({"qaFallThrough": [
        {"provider": "codex", "eligible": True}, {"provider": "kimi", "eligible": True},
        {"provider": "claude", "eligible": True}]}), encoding="utf-8")
    fakes = fx.fake_reviewer_bin(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(fakes) + os.pathsep + os.environ["PATH"])
    monkeypatch.chdir(repo)
    return repo, scratch


def _argv(paths, *extra, provider="codex", authors="claude"):
    repo, scratch = paths
    return ["--root", str(repo), "--ticket", "T1", "--scratch", str(scratch), "--provider",
            provider, "--authors", authors, "--author-source", "config"] + list(extra)


@pytest.mark.parametrize("mode,args,needle", [
    ("clean", (), "step 2d"),
    ("findings", (), "step 3: report every BLOCK"),
    ("fail", (), "step 3: report INCOMPLETE"),
], ids=["run-0-clean", "run-1-findings", "run-3-incomplete"])
def test_every_exit_path_prints_one_next_line_run(paths, capsys, monkeypatch, mode, args, needle):
    monkeypatch.setenv("FAKE_REVIEWER_MODE", mode)
    monkeypatch.setenv("FAKE_REVIEWER_STATE", str(paths[1] / "calls.txt"))
    monkeypatch.setattr(review_run, "RETRY_BACKOFF_SECONDS", 0)

    code, out = _main_in_process(_argv(paths), capsys)

    assert code in (0, 1, 3)
    _assert_one_next_last(out, needle)


@pytest.mark.parametrize("mode,exit_code,needle", [
    ("clean", 0, "run python3"),
    ("limit", 5, "--resolve-run"),
    ("fail", 6, "--resolve-run"),
], ids=["probe-0", "probe-5", "probe-6"])
def test_every_exit_path_prints_one_next_line_probe(paths, capsys, monkeypatch, mode, exit_code,
                                                    needle):
    monkeypatch.setenv("FAKE_REVIEWER_MODE", mode)

    code, out = _main_in_process(_argv(paths, "--probe"), capsys)

    assert code == exit_code
    _assert_one_next_last(out, needle)


def test_every_exit_path_prints_one_next_line_probe_7(paths, capsys, monkeypatch):
    monkeypatch.setenv("FAKE_REVIEWER_MODE", "hang")

    code, out = _main_in_process(_argv(paths, "--probe", "--probe-timeout", "1"), capsys)

    assert code == 7
    _assert_one_next_last(out, "--resolve-run")


def test_every_exit_path_prints_one_next_line_probe_refused(paths, capsys):
    code, out = _main_in_process(_argv(paths, "--probe", authors="gpt"), capsys)

    assert code == 2
    _assert_one_next_last(out, "walk to the next provider")


def test_every_exit_path_prints_one_next_line_reserve_only_and_round(paths, capsys):
    code, out = _main_in_process(
        _argv(paths, "--reserve-only", provider="claude", authors="gpt"), capsys)
    assert code == 0 and "ROUND=1" in out
    _assert_one_next_last(out, "dispatch crew:reviewer")

    (paths[1] / "out.txt").write_text("CLEAN\n", encoding="utf-8")
    code, out = _main_in_process(
        _argv(paths, "--round", "1", "--output", str(paths[1] / "out.txt"), "--exit-code", "0",
              provider="claude", authors="gpt"), capsys)
    _assert_one_next_last(out, "step")


def test_every_exit_path_prints_one_next_line_argparse_error(capsys):
    with pytest.raises(SystemExit) as stopped:
        review_run.main(["--root", ".", "--provider", "nonsense"])

    out = capsys.readouterr().out
    assert stopped.value.code == 2
    _assert_one_next_last(out, "fix the arguments")


def test_a_run_without_ticket_scratch_or_provider_is_an_argparse_error(capsys):
    with pytest.raises(SystemExit) as stopped:
        review_run.main(["--root", "."])

    out, err = capsys.readouterr()
    assert stopped.value.code == 2
    assert "--ticket, --scratch, --provider" in err
    _assert_one_next_last(out, "fix the arguments")


def _says(monkeypatch, code, *lines):
    """Make `run` print `lines` on stderr, as the gate that refuses would, and exit `code`."""
    def fake(args):  # pylint: disable=unused-argument
        for line in lines:
            review_run._err(line)  # pylint: disable=protected-access
        return code
    monkeypatch.setattr(review_run, "run", fake)


@pytest.mark.parametrize("code,said,needle", [
    (2, "review-run: codex is not on PATH (not-installed); nothing launched, no round spent",
     "codex is not installed here"),
    (2, "review-run: self-check: standards self-check missing", "answer .work/tickets"),
    (2, "review-run: " + review_ledger.GATE_CHANGED, "run the same command again"),
    (2, "review-run: pre-review gate could not run: OSError: x; nothing launched",
     "repair what the line above names"),
    (2, "review-run: same-family: codex speaks as the `claude` family", "the author's family"),
    (2, "review-run: kimi probe: rate-limited - x; nothing launched, no round spent",
     "Kimi is not ok"),
    (4, "review-run: no round left", "no round left"),
    (8, review_run.KIMI_PROBE_CHANGED, "do not walk to the next provider"),
    (9, "review-run: gate UNVERIFIED: x. No round reserved.", "run the verify gate"),
    (9, "review-run: pre-review checks: ruff FAIL", "fix the linter finding"),
    (9, "review-run: the bundle adds linter findings its base did not have. No round reserved.",
     "fix the linter finding"),
    (9, "review-run: a pre-review check could not run, so this tree is not known clean.",
     "install or repair the tool"),
    (10, "review-run: train: waiting behind T2", "wait for the merge train"),
], ids=["2-not-on-path", "2-self-check", "2-ledger-changed", "2-gate-could-not-run",
        "2-same-family", "2-kimi-probe", "4", "8", "9-gate-red", "9-pre-review-checks",
        "9-new-finding", "9-check-could-not-run", "10"])
def test_every_exit_path_prints_one_next_line_by_reason(paths, capsys, monkeypatch, code, said,
                                                        needle):
    _says(monkeypatch, code, said)

    got, out = _main_in_process(_argv(paths), capsys)

    assert got == code
    _assert_one_next_last(out, needle)


def test_the_next_line_for_a_provider_that_cannot_run_names_the_one_after_it(paths, capsys,
                                                                             monkeypatch):
    _says(monkeypatch, 2, "review-run: codex is not on PATH (not-installed); nothing launched")

    _, out = _main_in_process(_argv(paths), capsys)

    assert "--provider kimi" in _lines(out)[-1]


def test_a_next_line_is_always_the_last_stdout_line_even_after_a_reviewer_line(paths, capsys,
                                                                                monkeypatch):
    monkeypatch.setenv("FAKE_REVIEWER_MODE", "findings")

    _, out = _main_in_process(_argv(paths), capsys)

    assert _lines(out)[-1].startswith("next: ") and sum(
        1 for line in _lines(out) if line.startswith("next:")) == 1


def test_every_exit_path_prints_one_next_line_prepare(tmp_path, env):
    root = _repo(tmp_path, "committed-only")

    ok = _prepare(root, env)
    unknown = _prepare(root, env, "--ticket", "../x")

    for done in (ok, unknown):
        assert len(_next_lines(done.stdout)) == 1
        assert done.stdout.rstrip("\n").split("\n")[-1].startswith("next: ")


# --- AC1: review.md holds the part that needs the model, not shell -------------


def _review_text():
    with open(REVIEW_MD, encoding="utf-8", newline="") as fh:
        return fh.read().replace("\r\n", "\n")


def test_review_md_holds_no_transcribed_shell():
    text = _review_text()
    lines = text.split("\n")
    fences, longest, inside, size = [], 0, False, 0
    for line in lines:
        if line.startswith("```"):
            if inside:
                longest = max(longest, size)
            inside, size = not inside, 0
        elif inside:
            size += 1
    fences = [line for line in lines if line.startswith("```")]

    assert len(text.rstrip("\n").split("\n")) <= 120
    assert len(text.encode("utf-8")) <= 12288
    assert longest <= 6 and len(fences) % 2 == 0
    for banned in ("awk ", "<<EOF", "<<'EOF'", "python3 -c", "mktemp", "$ELIGIBLE", "$STALE_FLAG",
                   "$PROBE_STATUS", "$RUN_PROVIDER", "$RUN_MODEL", "$FALLBACK", "qm()"):
        assert banned not in text, banned


def test_cited_step_labels_exist():
    text = _review_text()
    headings = re.findall(r"^(?:\d+\. )?\*\*(?:Step )?(\d[a-z]?(?:\.\d)?)\b", text, re.M)

    for label in ("2a", "2b", "2c", "2d", "2e", "3.2", "3.3", "3.4", "3.5"):
        assert label in headings, (label, headings)
    assert len(headings) == len(set(headings))


def test_review_md_keeps_the_reasoning_effort_values_line():
    text = _review_text()

    assert "`reasoningEffort` accepts `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`;" \
        in text


def test_every_step_label_other_files_cite_is_in_review_md():
    base = os.path.join(fx.PLUGIN_ROOT, "hooks", "scripts")
    cites = {"crew_kimi_agent.py": "2e", "review_metrics.py": "2c"}
    text = _review_text()

    for name, label in cites.items():
        with open(os.path.join(base, name), encoding="utf-8") as fh:
            assert f"step {label}" in fh.read().lower(), name
        assert re.search(rf"^\*\*Step {label}\b", text, re.M), (name, label)
    with open(os.path.join(fx.PLUGIN_ROOT, "commands", "autopilot.md"), encoding="utf-8") as fh:
        autopilot = fh.read()
    assert "step 2d" in autopilot and "step 3.3" in autopilot
    assert "`review.md` step 3.5's notification" in autopilot


# --- the inputs --prepare reads are shape-checked, and no wait is unbounded ------


@pytest.mark.parametrize("report", [
    {"authorFamilies": "claude"},
    {"authorFamilies": [1]},
    {"authorSource": 5},
    {"qaFallThrough": [3]},
    {"qa": ["x"]},
    {"qaProviders": []},
])
def test_report_problem_names_a_misshaped_models_report(report):
    assert review_run.report_problem(report)


def test_report_problem_accepts_the_shape_crew_config_writes():
    report = {"authorFamilies": ["claude"], "authorSource": "config",
              "qa": [{"role": "review"}],
              "qaFallThrough": [{"provider": "codex", "eligible": True}],
              "qaProviders": {"codex": {"model": None}}}

    assert review_run.report_problem(report) is None


def test_a_misshaped_models_report_is_could_not_tell_not_an_empty_list(tmp_path):
    (tmp_path / "models.json").write_text('{"qaFallThrough": [3]}', encoding="utf-8")

    report, problem = review_run.load_report(str(tmp_path))

    assert report is None and "well-formed rows" in problem


def test_a_child_that_gives_no_answer_is_exit_124_never_a_pass():
    code, out = review_run._bounded(  # pylint: disable=protected-access
        [sys.executable, "-c", "import time; time.sleep(30)"], None, None, 1)

    assert (code, out) == (124, b"")


@pytest.mark.skipif(os.name == "nt", reason="Windows closes an inherited pipe on its own schedule")
def test_a_descendant_holding_the_pipe_open_cannot_hold_the_wait_open(monkeypatch):
    monkeypatch.setattr(review_run, "POST_KILL_TIMEOUT", 1)
    script = ("import subprocess, sys, time\n"
              "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(8)'])\n"
              "time.sleep(30)\n")
    started = time.monotonic()

    code, _ = review_run._bounded([sys.executable, "-c", script], None, None, 1)  # pylint: disable=protected-access

    assert code == 124 and time.monotonic() - started < 6


def test_a_scope_base_that_gives_no_answer_stops_the_review_base(monkeypatch):
    monkeypatch.setattr(review_run, "_run_tool", lambda *a, **k: (124, b""))

    base, refused = review_run.review_base(".", "/nowhere", "T1")

    assert (base, refused) == (None, review_run.EXIT_UNKNOWN)


def test_git_that_gives_no_answer_is_124(monkeypatch):
    monkeypatch.setattr(review_run, "_bounded", lambda *a, **k: (124, b""))

    assert review_run._git(".", "status") == (124, "")  # pylint: disable=protected-access


# --- review round 1: pinned provider, malformed rows, unreadable inputs ---------


def _pin(root, config):
    _write(root / ".crew" / "config.json", json.dumps(config))


def test_prepare_follows_a_pinned_provider_not_qa_order(tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    _pin(root, {"qa": {"provider": "kimi", "order": ["codex", "kimi"]}})

    out = _prepare(root, env).stdout

    assert _keys(out)["PINNED"] == ["kimi"]
    assert _next_lines(out)[0].startswith("next: run python3 ")
    assert "--provider kimi" in _next_lines(out)[0] and "--provider codex" not in out


def test_prepare_a_pinned_provider_that_may_not_run_is_an_error_not_a_fallback(tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    _pin(root, {"qa": {"provider": "claude"}})

    out = _prepare(root, env).stdout

    assert "qa.provider pins claude, which is not eligible" in _next_lines(out)[0]
    assert "not a cue to fall back" in _next_lines(out)[0]


def test_a_pinned_provider_that_fails_is_not_walked_past(paths, capsys, monkeypatch):
    repo, scratch = paths
    report = json.loads((scratch / "models.json").read_text(encoding="utf-8"))
    report["qa"] = [{"role": "review", "provider": "codex"}]
    (scratch / "models.json").write_text(json.dumps(report), encoding="utf-8")
    _says(monkeypatch, 2, "review-run: codex is not on PATH (not-installed); nothing launched")

    _, out = _main_in_process(_argv((repo, scratch)), capsys)

    assert "qa.provider pins codex" in _lines(out)[-1] and "--provider kimi" not in out


@pytest.mark.parametrize("report", [
    {"qaFallThrough": [{"provider": "codex", "eligible": "false"}]},
    {"qaFallThrough": [{"eligible": True}]},
    {"qaFallThrough": [{"provider": 3, "eligible": True}]},
    {"qa": [{"provider": "codex"}]},
])
def test_a_models_row_that_is_not_well_formed_is_not_eligible_and_not_a_crash(report):
    assert review_run.report_problem(report)
    assert review_run.eligible(report) == []


def test_prepare_a_verify_rule_that_is_not_an_object_is_could_not_tell(tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    _write(root / ".crew" / "verify.json", '{"rules": [42]}')

    done = _prepare(root, env)

    assert (done.returncode, "could not tell the specialists" in done.stderr) == (11, True)


@pytest.mark.skipif(os.name == "nt", reason="needs a symlink")
def test_prepare_a_dispatch_record_that_cannot_be_read_as_a_regular_file_is_could_not_tell(
        tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    _write(tmp_path / "elsewhere.json", "{}")
    os.symlink(tmp_path / "elsewhere.json", root / ".work" / "dispatch.json")

    done = _prepare(root, env)

    assert (done.returncode, "could not tell the dispatch record" in done.stderr) == (11, True)


def test_prepare_a_codemap_that_cannot_be_listed_is_could_not_tell_not_no_landmines(
        tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    _write(root / ".crew" / "codemap", "not a directory")

    done = _prepare(root, env)

    assert (done.returncode, "could not tell the changed files or the codemap" in done.stderr) \
        == (11, True)


def test_a_failed_scope_base_with_an_answer_is_not_a_base(monkeypatch):
    monkeypatch.setattr(review_run, "_run_tool", lambda *a, **k: (1, b"deadbeef\n"))

    base, refused = review_run.review_base(".", "/nowhere", "T1")

    assert (base, refused) == (None, review_run.EXIT_UNKNOWN)


def test_prepare_a_scratch_that_cannot_be_created_is_could_not_tell_not_a_traceback(
        tmp_path, env):
    root = _repo(tmp_path, "committed-only")
    _write(root / ".work" / "review", "a file where the directory should be")

    done = _prepare(root, env, scratch=None)

    assert (done.returncode, "could not tell the scratch directory" in done.stderr) == (11, True)
    assert "Traceback" not in done.stderr and len(_next_lines(done.stdout)) == 1


def test_review_md_quotes_the_plugin_root_everywhere():
    text = _review_text()
    bare = [m.start() for m in re.finditer(r"\$\{CLAUDE_PLUGIN_ROOT\}", text)
            if text[m.start() - 1] != '"']

    assert bare == []
