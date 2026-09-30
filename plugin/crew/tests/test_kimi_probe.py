"""kimi_probe.py: five distinct states, and only `ok` launches (T-0028).

Every case runs against a fake `kimi` from kimi_fixtures.fake_kimi_bin and a
fixture KIMI_CODE_HOME under tmp_path. No test here calls the real Kimi CLI or
reads the real `~/.kimi-code`.
"""
import json
import os
import subprocess
import sys
import threading
import time

import pytest
import yaml

import context  # noqa: F401  pylint: disable=unused-import
import kimi_probe
from kimi_fixtures import fake_kimi_bin, kimi_home

_PROBE = os.path.join(context._ROOT, "hooks", "scripts",  # pylint: disable=protected-access
                      "kimi_probe.py")


@pytest.fixture(name="fake")
def _fake(tmp_path):
    return str(fake_kimi_bin(tmp_path / "bin") / "kimi")


@pytest.fixture(name="home")
def _home(tmp_path):
    return str(kimi_home(tmp_path / "kimi-home"))


def _which(path):
    return lambda name: path if name == "kimi" else None


def _probe(fake, home, monkeypatch, answer="ok", model="k3", **kwargs):
    monkeypatch.setenv("FAKE_KIMI_PROBE", answer)
    return kimi_probe.probe(model, which=_which(fake), home=home, **kwargs)


def test_probe_no_binary_is_not_installed(home):
    result = kimi_probe.probe("k3", which=lambda _n: None, home=home)

    assert result["state"] == "not-installed"


def test_probe_no_config_is_not_authenticated(fake, tmp_path, monkeypatch):
    home = str(kimi_home(tmp_path / "empty-home", config=False))

    assert _probe(fake, home, monkeypatch)["state"] == "not-authenticated"


def test_probe_no_credential_is_not_authenticated(fake, tmp_path, monkeypatch):
    home = str(kimi_home(tmp_path / "no-cred", credential=False))

    assert _probe(fake, home, monkeypatch)["state"] == "not-authenticated"


def test_probe_api_key_alone_is_a_credential(fake, tmp_path, monkeypatch):
    home = str(kimi_home(tmp_path / "key", credential=False, api_key="sk-placeholder"))

    assert _probe(fake, home, monkeypatch)["state"] == "ok"


def test_probe_401_is_not_authenticated(fake, home, monkeypatch):
    assert _probe(fake, home, monkeypatch, "401")["state"] == "not-authenticated"


def test_probe_no_model_configured_is_not_authenticated(fake, home, monkeypatch):
    assert _probe(fake, home, monkeypatch, "nomodel")["state"] == "not-authenticated"


def test_probe_no_default_model_and_no_id_is_not_authenticated(fake, tmp_path,
                                                                monkeypatch):
    home = str(kimi_home(tmp_path / "nodefault", default_model=None))

    assert _probe(fake, home, monkeypatch, model=None)["state"] == "not-authenticated"


@pytest.mark.parametrize("marker", [
    "exceeded_current_quota_error", "rate_limit_reached_error",
    "engine_overloaded_error", "insufficient balance",
    "You have exceeded your current quota"])
def test_probe_quota_is_rate_limited(fake, home, monkeypatch, marker):
    assert _probe(fake, home, monkeypatch, "quota:" + marker)["state"] == "rate-limited"


def test_probe_unrecognised_output_is_unknown(fake, home, monkeypatch):
    assert _probe(fake, home, monkeypatch, "garbage")["state"] == "unknown"


def test_probe_exit0_without_marker_is_unknown(fake, home, monkeypatch):
    assert _probe(fake, home, monkeypatch, "nomarker")["state"] == "unknown"


def test_probe_timeout_is_unknown(fake, home, monkeypatch):
    result = _probe(fake, home, monkeypatch, "hang", timeout=2)

    assert result["state"] == "unknown" and "2s" in result["reason"]


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
        return fh.read().split(")")[-1].split()[0] != "Z"


@pytest.mark.skipif(os.name == "nt" or not os.path.isdir("/proc"),
                    reason="process-group kill and /proc are POSIX")
def test_probe_timeout_kills_a_descendant_that_holds_the_pipe(fake, home, monkeypatch, tmp_path):
    """PYTHON-07: a timed-out probe's whole process group is killed, so a
    descendant still holding stdout neither survives nor hangs the read."""
    pidfile = tmp_path / "child.pid"

    started = time.monotonic()
    result = _probe(fake, home, monkeypatch, f"hang-child:{pidfile}", timeout=2)
    elapsed = time.monotonic() - started
    time.sleep(0.5)

    assert result["state"] == "unknown" and elapsed < 2 + kimi_probe.POST_KILL_TIMEOUT
    assert not _alive(int(pidfile.read_text(encoding="utf-8")))


def test_probe_id_with_no_kimi_alias_is_unknown(fake, home, monkeypatch):
    assert _probe(fake, home, monkeypatch, model="kimi-k9")["state"] == "unknown"


def test_probe_alias_on_non_kimi_provider_is_unknown(fake, tmp_path, monkeypatch):
    home = str(kimi_home(tmp_path / "openai", provider_type="openai"))

    result = _probe(fake, home, monkeypatch)

    assert result["state"] == "unknown" and "openai" in result["reason"]


def test_probe_without_tomllib_is_unknown(fake, home, monkeypatch):
    monkeypatch.setattr(kimi_probe, "_tomllib", None)

    assert _probe(fake, home, monkeypatch)["state"] == "unknown"


def test_probe_unparseable_config_is_unknown(fake, tmp_path, monkeypatch):
    home = tmp_path / "bad"
    home.mkdir()
    (home / "config.toml").write_text("this is [not toml\n", encoding="utf-8")

    assert _probe(fake, str(home), monkeypatch)["state"] == "unknown"


def test_probe_runner_error_is_unknown(fake, home, monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("exec format error")

    assert _probe(fake, home, monkeypatch, runner=boom)["state"] == "unknown"


def test_probe_ok(fake, home, monkeypatch):
    result = _probe(fake, home, monkeypatch)

    assert (result["state"], result["alias"], result["exe"]) == ("ok", "kimi-code/k3", fake)


def test_classify_the_captured_run_is_ok():
    """The owner's real 2.1.1 run, stdout, stderr and exit status as captured:
    its trailing resume-hint text must not trip an auth or quota marker."""
    fixtures = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "fixtures", "kimi-stream-2.1.1")
    captured = {}
    for name in ("ok.jsonl", "ok.stderr.txt", "ok.exit"):
        with open(os.path.join(fixtures, name), encoding="utf-8") as fh:
            captured[name] = fh.read()

    state, _reason = kimi_probe.classify(captured["ok.jsonl"], captured["ok.stderr.txt"],
                                         int(captured["ok.exit"]), False)

    assert state == "ok"


def test_probe_resolves_the_default_model_when_no_id_is_given(fake, home, monkeypatch):
    assert _probe(fake, home, monkeypatch, model=None)["alias"] == "kimi-code/kimi-for-coding"


@pytest.mark.parametrize("model,alias", [
    ("k3", "kimi-code/k3"), ("kimi-for-coding", "kimi-code/kimi-for-coding"),
    ("kimi-for-coding-highspeed", "kimi-code/kimi-for-coding-highspeed")])
def test_probe_resolves_each_owner_id_to_its_alias(fake, home, monkeypatch, model, alias):
    assert _probe(fake, home, monkeypatch, model=model)["alias"] == alias


def test_only_ok_is_launchable():
    assert [s for s in kimi_probe.STATES if kimi_probe.launchable(s)] == ["ok"]
    assert kimi_probe.launchable("anything-else") is False


def test_probe_launches_with_stdin_closed_and_a_scrubbed_env(fake, home, monkeypatch,
                                                              tmp_path):
    dump = tmp_path / "dump.jsonl"
    monkeypatch.setenv("FAKE_KIMI_DUMP", str(dump))
    monkeypatch.setenv("KIMI_CODE_INFINITE_RETRY", "1")
    monkeypatch.setenv("KIMI_MODEL_THINKING_EFFORT", "max")

    _probe(fake, home, monkeypatch)
    record = json.loads(dump.read_text(encoding="utf-8").splitlines()[0])

    assert record["argv"][:6] == ["-p", "Reply with exactly: PROBE_OK", "-m", "kimi-code/k3",
                                  "--output-format", "stream-json"]
    assert record["stdin"] == ""
    assert not [k for k in record["env"]
                if k == "KIMI_CODE_INFINITE_RETRY" or k.startswith("KIMI_MODEL_")]
    assert record["env"].get("KIMI_CODE_NO_AUTO_UPDATE") == "1"


def test_probe_runs_with_the_review_read_only_controls_outside_the_cwd(fake, home, monkeypatch,
                                                                      tmp_path):
    """Round 1 FIX (kimi_probe.py:219): the probe was the one unrestricted
    Kimi call -- default agent (Write, Edit, Bash), auto-discovered skills,
    in the repository under review. It now gets the review's agent file and
    empty skills dir, in a throwaway directory that is gone afterwards."""
    dump = tmp_path / "dump.jsonl"
    monkeypatch.setenv("FAKE_KIMI_DUMP", str(dump))

    _probe(fake, home, monkeypatch)
    record = json.loads(dump.read_text(encoding="utf-8").splitlines()[0])
    front = yaml.safe_load(record["agent_file"].split("---\n")[1])
    argv = record["argv"]

    assert (front["tools"], front["disallowedTools"], record["skills"]) == (
        ["Read", "Grep", "Glob"], ["Write", "Edit", "Bash"], [])
    assert os.path.dirname(argv[argv.index("--agent-file") + 1]) == record["cwd"]
    assert os.path.realpath(record["cwd"]) != os.path.realpath(os.getcwd())
    assert not os.path.exists(record["cwd"])


def test_kimi_env_drops_retry_and_model_overrides():
    env = kimi_probe.kimi_env({"PATH": "/bin", "KIMI_CODE_INFINITE_RETRY": "1",
                               "KIMI_MODEL_API_KEY": "x", "KIMI_CODE_HOME": "/h"})

    assert env == {"PATH": "/bin", "KIMI_CODE_HOME": "/h", "KIMI_CODE_NO_AUTO_UPDATE": "1"}


def test_redact_masks_key_and_jwt_shapes():
    text = kimi_probe.redact("key sk-abcdefghijklmnop and eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl")

    assert "sk-abcdefghijklmnop" not in text and "eyJhbGciOi" not in text


def test_probe_never_echoes_an_api_key_value(fake, tmp_path, monkeypatch):
    home = str(kimi_home(tmp_path / "k", credential=False, api_key="sk-SECRETSECRET123"))

    result = _probe(fake, home, monkeypatch, "garbage")

    assert "SECRETSECRET" not in repr(result)


@pytest.mark.parametrize("answer,code", [("ok", 0), ("quota:insufficient balance", 1)])
def test_cli_exit_status_is_zero_only_for_ok(tmp_path, answer, code):
    fakes = fake_kimi_bin(tmp_path / "bin")
    home = kimi_home(tmp_path / "home")
    env = dict(os.environ, PATH=str(fakes) + os.pathsep + os.environ.get("PATH", ""),
               KIMI_CODE_HOME=str(home), FAKE_KIMI_PROBE=answer)

    result = subprocess.run([sys.executable, _PROBE, "--model", "k3"], env=env,
                            capture_output=True, text=True, check=False,
                            stdin=subprocess.DEVNULL, timeout=60)

    assert result.returncode == code and result.stdout.startswith("kimi: ")


# --- round 2 NIT kimi_probe.py:223: PROBE_OK is read before the rate limit ------

_RETRY_429 = json.dumps({"role": "meta", "type": "turn.step.retrying", "status_code": 429,
                         "error_message": "rate_limit_reached_error"})


def test_classify_a_retried_429_that_completed_is_ok():
    """The CLI retried a transient 429 and then finished the turn: the same
    stream kimi_probe.final_message reads as a clean answer."""
    stdout = _RETRY_429 + "\n" + json.dumps({"role": "assistant", "content": "PROBE_OK"}) + "\n"

    assert kimi_probe.classify(stdout, "retrying after 429\n", 0, False)[0] == "ok"


def test_classify_a_final_429_after_retries_is_rate_limited():
    stderr = "Error: 429 rate_limit_reached_error\n"

    assert kimi_probe.classify(_RETRY_429 + "\n", stderr, 1, False)[0] == "rate-limited"


def test_classify_probe_ok_beside_a_failed_turn_is_not_ok():
    """PROBE_OK is read first only from a turn that did not fail: an assistant
    line followed by a failure record is not a working reviewer."""
    stdout = "\n".join(json.dumps(e) for e in (
        {"role": "assistant", "content": "PROBE_OK"},
        {"role": "meta", "type": "turn.failed",
         "error": {"code": "provider.error", "message": "429 rate_limit_reached_error"}}))

    assert kimi_probe.classify(stdout, "", 0, False)[0] == "rate-limited"


# --- review round 4 FIX kimi_probe.py:179: a provider reference that is not a name --


def _odd_provider_home(tmp_path, value):
    home = kimi_home(tmp_path / "odd")
    text = (home / "config.toml").read_text(encoding="utf-8")
    text = text.replace('[models."kimi-code/k3"]\nprovider = "managed:kimi-code"',
                        f'[models."kimi-code/k3"]\nprovider = {value}')
    assert f"provider = {value}" in text
    (home / "config.toml").write_text(text, encoding="utf-8", newline="\n")
    return str(home)


@pytest.mark.parametrize("value", ['["x"]', "{ x = 1 }"], ids=["array", "inline-table"])
def test_probe_a_provider_reference_that_is_not_a_name_is_unknown(fake, tmp_path, monkeypatch,
                                                                  value):
    result = _probe(fake, _odd_provider_home(tmp_path, value), monkeypatch)

    assert result["state"] == "unknown"
    assert "provider reference is not a name" in result["reason"]


@pytest.mark.parametrize("value", [["x"], {"x": 1}, 7], ids=["list", "dict", "int"])
def test_resolve_alias_and_the_credential_check_refuse_a_non_string_provider(value):
    config = {"models": {"a": {"provider": value, "model": "k3"}},
              "providers": {"p": {"type": "kimi", "api_key": "k"}}}

    assert kimi_probe.resolve_alias(config, "k3") == (
        None, ("unknown", "the model's provider reference is not a name"))
    assert kimi_probe._credential_present(config, "a", "/nonexistent") is None  # pylint: disable=protected-access


def test_resolve_alias_a_string_provider_of_type_kimi_still_resolves():
    config = {"models": {"a": {"provider": "p", "model": "k3"}},
              "providers": {"p": {"type": "kimi", "api_key": "k"}}}

    assert kimi_probe.resolve_alias(config, "k3") == ("a", None)


# --- review round 4 FIX kimi_probe.py:269: a relative PATH entry --------------------


@pytest.mark.skipif(os.name == "nt", reason="the POSIX fake kimi is run by its shebang")
def test_probe_through_a_relative_path_entry_launches_the_absolute_exe(tmp_path, home,
                                                                       monkeypatch):
    fake_kimi_bin(tmp_path / "bin")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "bin" + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("FAKE_KIMI_PROBE", "ok")

    result = kimi_probe.probe("k3", home=home)

    assert (result["state"], result["exe"]) == ("ok", str(tmp_path / "bin" / "kimi"))


def test_probe_an_absolute_path_entry_is_unchanged(fake, home, monkeypatch):
    assert _probe(fake, home, monkeypatch)["exe"] == fake


# --- review round 4 FIX (the parser): a non-string text part -----------------------


def test_classify_a_non_string_text_part_is_unknown():
    stdout = json.dumps({"role": "assistant", "content": [{"type": "text", "text": 1}]}) + "\n"

    assert kimi_probe.classify(stdout, "", 0, False)[0] == "unknown"


def test_probe_an_unreadable_credentials_directory_is_unknown(fake, home, monkeypatch):
    """Round 5 of T-0028 (retargeted in round 7, when the check became the provider's
    own credential file): only a missing credential proves there is none; one that
    cannot be checked is could-not-tell."""
    real_lstat = os.lstat

    def lstat(path, *args, **kwargs):
        if os.path.basename(os.path.dirname(str(path))) == "credentials":
            raise PermissionError(13, "Permission denied", str(path))
        return real_lstat(path, *args, **kwargs)
    monkeypatch.setattr(kimi_probe.os, "lstat", lstat)

    result = _probe(fake, home, monkeypatch)

    assert (result["state"], "could not be checked" in result["reason"]) == ("unknown", True)


def test_classify_an_answer_that_only_contains_the_marker_is_not_ok():
    """Round 5 of T-0028: the probe asks for exactly PROBE_OK; a refusal that
    merely contains it must not authorise a launch."""
    stdout = json.dumps({"role": "assistant", "content": "not PROBE_OK"})

    assert kimi_probe.classify(stdout, "", 0, False)[0] == "unknown"


def test_classify_the_exact_marker_with_surrounding_whitespace_is_ok():
    stdout = json.dumps({"role": "assistant", "content": "\nPROBE_OK\n"})

    assert kimi_probe.classify(stdout, "", 0, False)[0] == "ok"


def test_probe_a_config_toml_that_is_a_directory_is_unknown(fake, tmp_path, monkeypatch):
    home = tmp_path / "dir-config"
    (home / "config.toml").mkdir(parents=True)

    result = _probe(fake, str(home), monkeypatch)

    assert (result["state"], result["reason"]) == ("unknown", "config.toml is not a regular file")


def test_probe_a_config_toml_lookup_that_fails_is_unknown(fake, home, monkeypatch):
    """Round 5 of T-0028: a stat that fails other than ENOENT (an unreadable
    parent) is not proof that there is no config."""
    real_open = os.open

    def failing_open(path, *args, **kwargs):
        if os.path.basename(str(path)) == "config.toml":
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(kimi_probe.os, "open", failing_open)

    assert _probe(fake, home, monkeypatch)["state"] == "unknown"


def test_probe_that_cannot_create_its_scratch_directory_is_unknown(fake, home, monkeypatch):
    def no_scratch(*_args, **_kwargs):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(kimi_probe.tempfile, "mkdtemp", no_scratch)

    result = _probe(fake, home, monkeypatch)

    assert (result["state"], "scratch directory" in result["reason"]) == ("unknown", True)


# --- review round 6 (T-0028) ------------------------------------------------------


@pytest.mark.parametrize("api_key,oauth", [("1", 'storage = "file"'), ('""', None)],
                         ids=["api-key-not-a-string", "oauth-not-a-table"])
def test_probe_a_wrong_shaped_credential_field_is_unknown(fake, tmp_path, monkeypatch,
                                                          api_key, oauth):
    """Round 6 FIX 2: api_key = 1 or oauth = "file" is malformed config, not proven
    absence of a credential."""
    home = kimi_home(tmp_path / "shape", credential=False)
    text = (home / "config.toml").read_text(encoding="utf-8")
    text = text.replace('api_key = ""', f"api_key = {api_key}")
    if oauth is None:
        text = text.replace('[providers."managed:kimi-code".oauth]\nstorage = "file"\n'
                            'key = "oauth/kimi-code"', "")
        text = text.replace(f"api_key = {api_key}", f"api_key = {api_key}\noauth = \"file\"")
    (home / "config.toml").write_text(text, encoding="utf-8")

    result = _probe(fake, str(home), monkeypatch)

    assert result["state"] == "unknown", result


def test_probe_an_empty_api_key_and_no_oauth_is_still_not_authenticated(fake, tmp_path,
                                                                        monkeypatch):
    """must-allow: an empty api_key and no oauth block is a known absence."""
    home = kimi_home(tmp_path / "none", credential=False)
    text = (home / "config.toml").read_text(encoding="utf-8")
    text = text.replace('[providers."managed:kimi-code".oauth]\nstorage = "file"\n'
                        'key = "oauth/kimi-code"', "")
    (home / "config.toml").write_text(text, encoding="utf-8")

    assert _probe(fake, str(home), monkeypatch)["state"] == "not-authenticated"


def test_probe_refuses_a_scratch_directory_inside_a_repository(fake, home, monkeypatch,
                                                               tmp_path):
    """Round 6 FIX 3: with TMPDIR inside a repository the throwaway directory would sit
    under it, where the CLI can discover that repository's instructions."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "tmp").mkdir()
    monkeypatch.setattr(kimi_probe.tempfile, "tempdir", str(repo / "tmp"))
    calls = []

    result = _probe(fake, home, monkeypatch, runner=lambda *a, **k: calls.append(a))

    assert (result["state"], calls) == ("unknown", [])
    assert "inside a repository" in result["reason"]
    assert list((repo / "tmp").iterdir()) == []


# --- review round 7 (T-0028); their mutations are L-0527's (sabotage*.py is harness) ----


@pytest.mark.parametrize("value", ["1", "[\"k3\"]", "{ a = 1 }"],
                         ids=["int", "array", "table"])
def test_probe_a_non_string_default_model_is_unknown(fake, tmp_path, monkeypatch, value):
    """Round 7 FIX 1: a malformed default_model is could-not-tell, not "no default"."""
    home = kimi_home(tmp_path / "dm", default_model=None)
    text = (home / "config.toml").read_text(encoding="utf-8")
    (home / "config.toml").write_text(f"default_model = {value}\n" + text, encoding="utf-8")

    result = _probe(fake, str(home), monkeypatch, model=None)

    assert result["state"] == "unknown", result


def test_probe_an_empty_default_model_is_still_not_authenticated(fake, tmp_path, monkeypatch):
    """must-allow: an empty default_model is a known absence."""
    home = kimi_home(tmp_path / "dm-empty", default_model="")

    assert _probe(fake, str(home), monkeypatch, model=None)["state"] == "not-authenticated"


def test_probe_another_providers_credential_is_not_a_login(fake, tmp_path, monkeypatch):
    """Round 7 FIX 2: only this provider's own credential file counts. Kimi Code 2.1.1 stores
    oauth `key = "oauth/<name>"` at `credentials/<name>.json` (measured on the installed CLI)."""
    home = kimi_home(tmp_path / "other", credential=False)
    (home / "credentials").mkdir()
    (home / "credentials" / "unrelated-provider.json").write_text("{}\n", encoding="utf-8")

    assert _probe(fake, str(home), monkeypatch)["state"] == "not-authenticated"


def test_probe_the_providers_own_credential_is_a_login(fake, home, monkeypatch):
    """must-allow: `oauth/kimi-code` with `credentials/kimi-code.json` present."""
    assert _probe(fake, home, monkeypatch)["state"] == "ok"


@pytest.mark.parametrize("oauth_body", ['storage = "keyring"\nkey = "oauth/kimi-code"',
                                        'storage = "file"', 'storage = "file"\nkey = 7'],
                         ids=["not-file-storage", "no-key", "key-not-a-string"])
def test_probe_an_oauth_credential_it_cannot_locate_is_unknown(fake, tmp_path, monkeypatch,
                                                               oauth_body):
    home = kimi_home(tmp_path / "loc")
    text = (home / "config.toml").read_text(encoding="utf-8")
    text = text.replace('storage = "file"\nkey = "oauth/kimi-code"', oauth_body)
    (home / "config.toml").write_text(text, encoding="utf-8")

    assert _probe(fake, str(home), monkeypatch)["state"] == "unknown"


def test_probe_output_past_the_cap_is_unknown_and_not_kept(fake, home, monkeypatch):
    """Round 7 FIX 3: the capture is size-capped; a flood is could-not-tell, and nothing
    past the cap is held in memory."""
    monkeypatch.setattr(kimi_probe, "OUTPUT_CAP", 4096)
    seen = []
    real_classify = kimi_probe.classify

    def spy(stdout, stderr, *rest, **kw):
        seen.append(len(stdout) + len(stderr))
        return real_classify(stdout, stderr, *rest, **kw)
    monkeypatch.setattr(kimi_probe, "classify", spy)

    result = _probe(fake, home, monkeypatch, "flood:200000")

    assert (result["state"], "exceeded" in result["reason"]) == ("unknown", True), result
    assert all(n <= 2 * 4096 for n in seen)


def test_probe_output_under_the_cap_still_classifies(fake, home, monkeypatch):
    """must-allow: output below the cap reads as before."""
    monkeypatch.setattr(kimi_probe, "OUTPUT_CAP", 4096)

    assert _probe(fake, home, monkeypatch)["state"] == "ok"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs are POSIX")
def test_probe_a_fifo_swapped_in_after_the_check_does_not_block(fake, tmp_path, monkeypatch):
    """Round 7 FIX 4: the config is read from the handle it opened (no reopen by path),
    and the open cannot block. A stat that still reports a regular file (the race window)
    must not lead to a blocking open of a FIFO."""
    home = tmp_path / "fifo-home"
    home.mkdir()
    os.mkfifo(home / "config.toml")
    regular = os.stat(__file__)
    real_stat = os.stat
    monkeypatch.setattr(kimi_probe.os, "stat",
                        lambda p, *a, **k: regular if str(p).endswith("config.toml")
                        else real_stat(p, *a, **k))
    out = {}
    worker = threading.Thread(target=lambda: out.update(_probe(fake, str(home), monkeypatch)),
                              daemon=True)

    worker.start()
    worker.join(5)

    assert (worker.is_alive(), out.get("state")) == (False, "unknown")
