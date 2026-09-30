"""kimi_probe.py: five distinct states, and only `ok` launches (T-0028).

Every case runs against a fake `kimi` from kimi_fixtures.fake_kimi_bin and a
fixture KIMI_CODE_HOME under tmp_path. No test here calls the real Kimi CLI or
reads the real `~/.kimi-code`.
"""
import json
import os
import subprocess
import sys

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
    """Round 5 of T-0028: only a missing credentials directory proves there
    is no stored OAuth credential; one that cannot be listed is could-not-tell."""
    real_listdir = os.listdir

    def listdir(path):
        if os.path.basename(path) == "credentials":
            raise PermissionError(13, "Permission denied", path)
        return real_listdir(path)
    monkeypatch.setattr(kimi_probe.os, "listdir", listdir)

    result = _probe(fake, home, monkeypatch)

    assert (result["state"], "credentials directory" in result["reason"]) == ("unknown", True)


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
    real_stat = os.stat

    def failing_stat(path, *args, **kwargs):
        if os.path.basename(str(path)) == "config.toml":
            raise PermissionError(13, "Permission denied", str(path))
        return real_stat(path, *args, **kwargs)
    monkeypatch.setattr(kimi_probe.os, "stat", failing_stat)

    assert _probe(fake, home, monkeypatch)["state"] == "unknown"


def test_probe_that_cannot_create_its_scratch_directory_is_unknown(fake, home, monkeypatch):
    def no_scratch(*_args, **_kwargs):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(kimi_probe.tempfile, "mkdtemp", no_scratch)

    result = _probe(fake, home, monkeypatch)

    assert (result["state"], "scratch directory" in result["reason"]) == ("unknown", True)
