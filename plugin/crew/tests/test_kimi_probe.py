"""kimi_probe.py: five distinct states, and only `ok` launches (T-0028).

Every case runs against a fake `kimi` from review_fixtures.fake_kimi_bin and a
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
from review_fixtures import fake_kimi_bin, kimi_home

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


def test_every_kimi_sabotage_anchor_is_present_exactly_once():
    """The cheap standing check for sabotage_kimi.py's table: an edit that
    moves a line a mutation aims at would otherwise leave that mutation
    testing nothing until somebody paid for a full sabotage run."""
    import sabotage_kimi  # pylint: disable=import-outside-toplevel

    lost = []
    for label, target, find, _replace, _test in sabotage_kimi.KIMI_MUTATIONS:
        with open(target, encoding="utf-8", newline="") as handle:
            if handle.read().count(find) != 1:
                lost.append(label)

    assert sabotage_kimi.KIMI_MUTATIONS and not lost, lost


# --- round 2 NIT kimi_probe.py:223: PROBE_OK is read before the rate limit ------

_RETRY_429 = json.dumps({"role": "meta", "type": "turn.step.retrying", "status_code": 429,
                         "error_message": "rate_limit_reached_error"})


def test_classify_a_retried_429_that_completed_is_ok():
    """The CLI retried a transient 429 and then finished the turn: the same
    stream review_verdict.kimi_final_message reads as a clean answer."""
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
