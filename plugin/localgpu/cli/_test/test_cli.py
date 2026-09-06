"""The `localgpu` command itself: argument parsing, preflight, and the child
environment that decides which model the launched session actually talks to.

The environment tests are the reason this file exists. `localgpu shell` points
a **real** Claude Code at a loopback proxy, and Anthropic's credential
resolution puts `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_PROFILE` above
`ANTHROPIC_API_KEY`. If either survives into the child, the session goes back
to the real API while the banner says "local 7B" - a failure with no error
message and no symptom other than a bill.

Nothing here needs Ollama, a GPU, a network, or a `claude` binary, and no test
in this file ever starts a process.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import pytest

# Set up inline rather than in a conftest.py. Both _test directories would
# import as the top-level module `conftest`, and mcp/_test/conftest.py exports
# fixtures its tests import by name - a second file of that name silently wins
# and breaks them. See cli/_test/README.md.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import localgpu_cli as cli  # noqa: E402

ollama_client = cli.ollama_client

# The credentials that outrank ANTHROPIC_API_KEY. Listed here as well as in the
# source so a deletion there has to be a deliberate edit in two places.
OUTRANKS_API_KEY = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE")

PROXY_URL = "http://127.0.0.1:54321"


# -- _child_env: which API the child session actually reaches ---------------


def test_child_env_points_at_the_local_proxy():
    env = cli._child_env(PROXY_URL)
    assert env["ANTHROPIC_BASE_URL"] == PROXY_URL
    assert env["LOCALGPU_SHELL"] == "1"


def test_child_env_credentials_that_outrank_the_api_key_are_dropped(monkeypatch):
    """The one that matters: set in the parent, gone in the child."""
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-ant-oat01-real-token")
    monkeypatch.setenv("ANTHROPIC_PROFILE", "work")

    env = cli._child_env(PROXY_URL)

    for name in OUTRANKS_API_KEY:
        assert name not in env, (
            f"{name} survived into the child environment - it outranks "
            "ANTHROPIC_API_KEY, so the 'local' session would talk to the real API"
        )


def test_child_env_drops_them_even_when_they_are_empty(monkeypatch):
    """An empty string is still a set variable, and still outranks the key."""
    for name in OUTRANKS_API_KEY:
        monkeypatch.setenv(name, "")

    env = cli._child_env(PROXY_URL)

    assert not any(name in env for name in OUTRANKS_API_KEY)


def test_child_env_drops_them_when_the_parent_never_had_them(monkeypatch):
    """Popping an absent key must not raise - the common case has neither set."""
    for name in OUTRANKS_API_KEY:
        monkeypatch.delenv(name, raising=False)

    env = cli._child_env(PROXY_URL)

    assert not any(name in env for name in OUTRANKS_API_KEY)


def test_child_env_replaces_a_real_api_key_with_the_placeholder(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-a-real-paid-key")

    env = cli._child_env(PROXY_URL)

    assert env["ANTHROPIC_API_KEY"] == "localgpu-local"
    assert "sk-ant" not in env["ANTHROPIC_API_KEY"]


def test_child_env_keeps_the_rest_of_the_parent_environment(monkeypatch):
    """It is an override, not a scrub: the child still needs PATH and friends."""
    monkeypatch.setenv("LOCALGPU_TEST_MARKER", "kept")

    env = cli._child_env(PROXY_URL)

    assert env["LOCALGPU_TEST_MARKER"] == "kept"
    assert "PATH" in env


def test_child_env_does_not_mutate_the_parent_environment(monkeypatch):
    """The current session must be untouched - that is the plugin's promise."""
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-ant-oat01-real-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

    cli._child_env(PROXY_URL)

    import os

    assert os.environ["ANTHROPIC_AUTH_TOKEN"] == "sk-ant-oat01-real-token"
    assert os.environ["ANTHROPIC_BASE_URL"] == "https://api.anthropic.com"


# -- cmd_shell: the env above actually reaching the child -------------------


class FakeServer:
    """Stands in for anthropic_proxy.make_server - binds nothing."""

    def __init__(self, address=("127.0.0.1", 54321)):
        self.server_address = address
        self.serve_forever_calls = 0
        self.shutdown_calls = 0
        self.close_calls = 0

    def serve_forever(self):
        self.serve_forever_calls += 1

    def shutdown(self):
        self.shutdown_calls += 1

    def server_close(self):
        self.close_calls += 1


class Completed:
    def __init__(self, returncode):
        self.returncode = returncode


@pytest.fixture
def shell_harness(monkeypatch):
    """cmd_shell with every outside edge stubbed. Records the subprocess call."""
    server = FakeServer()
    calls: dict = {}

    monkeypatch.setattr(
        cli.localgpu_config,
        "load_config",
        lambda *a, **k: {
            "chat_model": "qwen2.5-coder:7b-instruct-q4_K_M",
            "ollama_url": "http://127.0.0.1:11434",
        },
    )
    monkeypatch.setattr(cli, "_preflight", lambda cfg: calls.setdefault("cfg", cfg))
    monkeypatch.setattr(cli, "_find_claude", lambda: "/fake/bin/claude")
    monkeypatch.setattr(cli.anthropic_proxy, "make_server", lambda *a, **k: server)
    monkeypatch.setattr(cli.threading, "Thread", _NoopThread)

    def fake_run(argv, env=None, **kwargs):
        calls["argv"] = argv
        calls["env"] = env
        return Completed(0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    calls["server"] = server
    return calls


class _NoopThread:
    """Never actually serves - cmd_shell only needs .start() to return."""

    def __init__(self, target=None, daemon=None):
        self.target = target
        self.daemon = daemon

    def start(self):
        pass


def _shell_args(**overrides):
    args = argparse.Namespace(
        model=None,
        port=0,
        keep_alive="5m",
        verbose=False,
        claude_args=[],
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def test_shell_launches_claude_with_the_sanitised_environment(shell_harness, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-ant-oat01-real-token")
    monkeypatch.setenv("ANTHROPIC_PROFILE", "work")

    assert cli.cmd_shell(_shell_args()) == 0

    env = shell_harness["env"]
    assert env is not None, "cmd_shell passed no env, so the child inherits the real one"
    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:54321"
    assert env["ANTHROPIC_API_KEY"] == "localgpu-local"
    assert env["LOCALGPU_SHELL"] == "1"
    for name in OUTRANKS_API_KEY:
        assert name not in env


def test_shell_passes_claude_args_through_and_returns_its_code(shell_harness, monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run", lambda argv, **kw: Completed(3))

    # By the time cmd_shell sees claude_args, parse_args() has already
    # stripped any separator - this is what a real "-p hello" forward looks
    # like on the way in.
    assert cli.cmd_shell(_shell_args(claude_args=["-p", "hello"])) == 3


def test_shell_uses_the_model_override(shell_harness):
    cli.cmd_shell(_shell_args(model="llama3.1:8b"))

    assert shell_harness["cfg"]["chat_model"] == "llama3.1:8b"


def test_shell_shuts_the_proxy_down_on_ctrl_c(shell_harness, monkeypatch):
    def interrupted(argv, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.subprocess, "run", interrupted)

    assert cli.cmd_shell(_shell_args()) == 130
    server = shell_harness["server"]
    assert server.shutdown_calls == 1
    assert server.close_calls == 1


def test_shell_shuts_the_proxy_down_on_a_normal_exit(shell_harness):
    cli.cmd_shell(_shell_args())

    server = shell_harness["server"]
    assert server.shutdown_calls == 1
    assert server.close_calls == 1


# -- cmd_proxy: shutdown() must not be called from serve_forever()'s own
# thread ------------------------------------------------------------------
#
# cmd_shell runs serve_forever() on a background thread and shutdown() on the
# main thread afterwards - the one arrangement Python's docs say is safe.
# cmd_proxy runs serve_forever() directly on the main thread, so by the time
# Ctrl+C (or any exit) reaches the `finally`, serve_forever() has already
# returned on *this* thread and shutdown() has nothing left to signal.
# https://docs.python.org/3/library/socketserver.html#socketserver.BaseServer.shutdown
# says calling it in that situation "will deadlock".


class DeadlockProneServer(FakeServer):
    """Stands in for a real ThreadingHTTPServer whose shutdown() would hang
    forever if called from serve_forever()'s own thread. Raising instead of
    blocking is what turns that into a fast, loud test failure rather than a
    hung test suite."""

    def shutdown(self):
        raise AssertionError(
            "cmd_proxy must not call shutdown() - serve_forever() runs on "
            "this same thread, so shutdown() would wait forever on a signal "
            "only a *different* thread's serve_forever() loop ever sets"
        )


def _proxy_args(**overrides):
    args = argparse.Namespace(model=None, host="127.0.0.1", port=8817, keep_alive="5m")
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


@pytest.fixture
def proxy_harness(monkeypatch):
    server = DeadlockProneServer()

    monkeypatch.setattr(
        cli.localgpu_config,
        "load_config",
        lambda *a, **k: {
            "chat_model": "qwen2.5-coder:7b-instruct-q4_K_M",
            "ollama_url": "http://127.0.0.1:11434",
        },
    )
    monkeypatch.setattr(cli, "_preflight", lambda cfg: None)
    monkeypatch.setattr(cli.anthropic_proxy, "make_server", lambda *a, **k: server)
    return {"server": server}


def test_proxy_does_not_call_shutdown_on_ctrl_c(proxy_harness, monkeypatch):
    server = proxy_harness["server"]

    def interrupted():
        raise KeyboardInterrupt

    monkeypatch.setattr(server, "serve_forever", interrupted)

    assert cli.cmd_proxy(_proxy_args()) == 0
    assert server.close_calls == 1


def test_proxy_does_not_call_shutdown_on_a_normal_exit(proxy_harness):
    assert cli.cmd_proxy(_proxy_args()) == 0

    server = proxy_harness["server"]
    assert server.close_calls == 1


# -- _find_claude -----------------------------------------------------------


def test_find_claude_returns_what_which_found(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/local/bin/{name}")

    assert cli._find_claude() == "/usr/local/bin/claude"


def test_find_claude_without_claude_says_what_to_do(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    with pytest.raises(SystemExit) as exc:
        cli._find_claude()

    message = str(exc.value)
    assert "not on PATH" in message
    assert "localgpu proxy" in message, "the message must name the fallback that still works"


# -- _preflight -------------------------------------------------------------


class StubOllama:
    """Records what it was asked for; raises whatever the test parked on it."""

    raises = None
    # Annotated rather than bare `= None`: pylint infers the class attribute's
    # type from the assignment, then reports E1137 on `StubOllama.last["models"]`
    # below because None is not subscriptable. __init__ replaces it with a dict
    # before any test reads it, so the annotation states what is already true.
    last: dict | None = None

    def __init__(self, url):
        StubOllama.last = {"url": url, "models": None}

    def require_models(self, models):
        # Asserted rather than assumed: `last` is None until __init__ runs, so
        # reaching here with it unset means the code under test called
        # require_models on a class it never constructed. Failing loudly on
        # that beats a TypeError three frames deeper.
        #
        # The assert above is the guarantee; pylint cannot see it. It does not
        # narrow `dict | None` on an `assert x is not None` - not for the class
        # attribute and not for a local bound from it either, both tried - so
        # the subscript reads as a possible None and raises E1137. Disabled
        # here rather than dropping the annotation, because the annotation is
        # what makes the None case explicit to a human reading the fixture
        # reset below.
        # pylint: disable=unsupported-assignment-operation
        assert StubOllama.last is not None
        StubOllama.last["models"] = list(models)
        if StubOllama.raises is not None:
            raise StubOllama.raises


@pytest.fixture
def stub_ollama(monkeypatch):
    StubOllama.raises = None
    StubOllama.last = None
    monkeypatch.setattr(ollama_client, "OllamaClient", StubOllama)
    return StubOllama


CFG = {"chat_model": "qwen2.5-coder:7b-instruct-q4_K_M", "ollama_url": "http://127.0.0.1:11434"}


def test_preflight_checks_the_configured_model_on_the_configured_host(stub_ollama):
    cli._preflight(dict(CFG))

    assert stub_ollama.last["url"] == CFG["ollama_url"]
    assert stub_ollama.last["models"] == [CFG["chat_model"]]


def test_preflight_turns_a_missing_model_into_an_exit_naming_the_pull(stub_ollama):
    stub_ollama.raises = ollama_client.ModelNotPulled(
        "Ollama does not have the model 'x'.\nPull it with:  ollama pull x"
    )

    with pytest.raises(SystemExit) as exc:
        cli._preflight(dict(CFG))

    message = str(exc.value)
    assert message.startswith("localgpu: ")
    assert "ollama pull x" in message, "the exit text must carry the fix, not just the failure"


def test_preflight_turns_an_unreachable_ollama_into_an_exit_naming_the_fix(stub_ollama):
    stub_ollama.raises = ollama_client.OllamaUnavailable(
        "Cannot reach Ollama at http://127.0.0.1:11434 (refused).\nStart it with:  ollama serve"
    )

    with pytest.raises(SystemExit) as exc:
        cli._preflight(dict(CFG))

    assert "ollama serve" in str(exc.value)


def test_preflight_does_not_swallow_unrelated_errors(stub_ollama):
    """Only OllamaError becomes a tidy exit; a bug must keep its traceback."""
    stub_ollama.raises = ValueError("something else entirely")

    with pytest.raises(ValueError):
        cli._preflight(dict(CFG))


# -- build_parser -----------------------------------------------------------


def test_shell_defaults():
    args = cli.build_parser().parse_args(["shell"])

    assert args.command == "shell"
    assert args.func is cli.cmd_shell
    assert args.model is None
    assert args.port == 0, "0 means 'pick a free port', which is what keeps two shells apart"
    assert args.keep_alive == cli.anthropic_proxy.DEFAULT_KEEP_ALIVE
    assert args.verbose is False
    assert args.claude_args == []


def test_proxy_defaults():
    args = cli.build_parser().parse_args(["proxy"])

    assert args.command == "proxy"
    assert args.func is cli.cmd_proxy
    assert args.host == "127.0.0.1", "a non-loopback default would expose an unauthenticated proxy"
    assert args.port == 8817
    assert args.keep_alive == cli.anthropic_proxy.DEFAULT_KEEP_ALIVE


def test_shell_options_parse():
    args = cli.build_parser().parse_args(
        ["shell", "--model", "llama3.1:8b", "--port", "9000", "--keep-alive", "30m", "--verbose"]
    )

    assert (args.model, args.port, args.keep_alive, args.verbose) == (
        "llama3.1:8b",
        9000,
        "30m",
        True,
    )


def test_claude_args_after_a_double_dash_are_passed_through():
    args = cli.parse_args(["shell", "--verbose", "--", "-p", "hi"])

    assert args.verbose is True
    # The separator is consumed here, not forwarded - `claude` is invoked as
    # `claude -p hi`, not `claude -- -p hi`.
    assert args.claude_args == ["-p", "hi"]


def test_a_bare_subcommand_word_starts_the_remainder():
    args = cli.parse_args(["shell", "doctor", "--foo"])

    assert args.claude_args == ["doctor", "--foo"]


def test_a_claude_flag_without_the_separator_is_forwarded():
    """The fix: `localgpu shell -p hi` now forwards straight to `claude`,
    instead of argparse rejecting `-p` as an unknown option to `localgpu`."""
    args = cli.parse_args(["shell", "-p", "hi"])

    assert args.claude_args == ["-p", "hi"]


def test_no_extra_args_is_an_empty_passthrough():
    args = cli.parse_args(["shell"])

    assert args.claude_args == []


def test_a_bare_separator_with_nothing_after_it_is_an_empty_passthrough():
    args = cli.parse_args(["shell", "--"])

    assert args.claude_args == []


def test_a_flag_with_spaces_in_its_value_survives_as_one_token():
    args = cli.parse_args(["shell", "--", "-p", "hi there, multiple words"])

    assert args.claude_args == ["-p", "hi there, multiple words"]


def test_a_second_separator_is_forwarded_literally():
    """Only the first `--` is localgpu's own; a second one is claude's problem."""
    args = cli.parse_args(["shell", "--", "--", "-p", "hi"])

    assert args.claude_args == ["--", "-p", "hi"]


def test_a_flag_colliding_with_localgpus_own_option_is_claimed_by_localgpu():
    """Without the separator, an option name localgpu also defines is
    ambiguous, and argparse resolves it in localgpu's favour - `--verbose`
    here never reaches claude_args at all."""
    args = cli.parse_args(["shell", "--verbose", "extra-word"])

    assert args.verbose is True
    assert args.claude_args == ["extra-word"]


def test_a_flag_colliding_with_localgpus_own_option_can_be_forced_through():
    """The separator is the escape hatch: put `--verbose` after it and it goes
    to `claude` untouched, instead of being claimed by localgpu's own flag."""
    args = cli.parse_args(["shell", "--", "--verbose"])

    assert args.verbose is False
    assert args.claude_args == ["--verbose"]


def test_an_unrecognized_flag_on_a_non_shell_command_still_errors():
    """The passthrough is specific to `shell` - `proxy` keeps the normal
    argparse behaviour of rejecting anything it does not recognize."""
    with pytest.raises(SystemExit) as exc:
        cli.parse_args(["proxy", "--not-a-real-flag"])

    assert exc.value.code == 2


def test_no_subcommand_is_an_error():
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args([])

    assert exc.value.code == 2


def test_version_prints_and_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--version"])

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"localgpu {cli.__version__}"


def test_main_dispatches_to_the_subcommand_and_returns_its_code(monkeypatch):
    seen = {}

    def fake_shell(args):
        seen["args"] = args
        return 7

    # build_parser() runs inside main(), and set_defaults reads the module
    # global at that moment, so patching here is enough - and it is what keeps
    # this test from launching anything.
    monkeypatch.setattr(cli, "cmd_shell", fake_shell)

    assert cli.main(["shell", "--verbose"]) == 7
    assert seen["args"].verbose is True


# -- the banner -------------------------------------------------------------


def test_banner_states_the_thing_nothing_enforces():
    text = cli.BANNER.format(model="m", base_url="u", ollama_url="o")

    assert "/crew:*" in text, "the warning about gate commands is the point of the banner"


# -- prompt / models --------------------------------------------------------
#
# The success path is stubbed here because it cannot be exercised for real on
# every machine - and on this one, at the time of writing, not at all: Ollama
# answers /api/generate with "CUDA error: a PTX JIT compilation failed", which
# a raw curl reproduces identically, so it is the server's problem and not the
# CLI's. That is exactly why these tests assert on the request that was built
# and the error that came back, rather than on any model output.

PROMPT_CFG = {
    "chat_model": "qwen2.5-coder:7b-instruct-q4_K_M",
    "embed_model": "nomic-embed-text",
    "ollama_url": "http://127.0.0.1:11434",
}


class StubGenerator:
    """Enough of OllamaClient for `prompt` and `models`, recording every call."""

    answer = "stub answer"
    models: list[str] = ["qwen2.5-coder:7b-instruct-q4_K_M", "nomic-embed-text:latest"]
    raises = None
    last: dict | None = None

    def __init__(self, url, keep_alive=None):
        StubGenerator.last = {"url": url, "keep_alive": keep_alive}

    def require_models(self, models):
        # pylint: disable=unsupported-assignment-operation
        assert StubGenerator.last is not None
        StubGenerator.last["required"] = list(models)
        if StubGenerator.raises is not None:
            raise StubGenerator.raises

    def generate(self, prompt, model, system=None, options=None, timeout=None):
        # pylint: disable=unsupported-assignment-operation
        assert StubGenerator.last is not None
        StubGenerator.last["generate"] = {
            "prompt": prompt, "model": model, "system": system,
            "options": options, "timeout": timeout,
        }
        if StubGenerator.raises is not None:
            raise StubGenerator.raises
        return StubGenerator.answer

    def list_models(self):
        if StubGenerator.raises is not None:
            raise StubGenerator.raises
        return list(StubGenerator.models)


@pytest.fixture
def stub_generator(monkeypatch):
    StubGenerator.raises = None
    StubGenerator.last = None
    StubGenerator.answer = "stub answer"
    StubGenerator.models = ["qwen2.5-coder:7b-instruct-q4_K_M", "nomic-embed-text:latest"]
    monkeypatch.setattr(ollama_client, "OllamaClient", StubGenerator)
    monkeypatch.setattr(cli.localgpu_config, "load_config", lambda: dict(PROMPT_CFG))
    return StubGenerator


def _prompt_args(**over):
    base = {"prompt": "hello", "model": None, "system": None, "temperature": None,
            "num_predict": None, "timeout": 300.0,
            "keep_alive": ollama_client.DEFAULT_KEEP_ALIVE, "json": False}
    base.update(over)
    return argparse.Namespace(**base)


def test_prompt_sends_the_configured_model_and_returns_zero(stub_generator, capsys):
    assert cli.cmd_prompt(_prompt_args()) == 0

    sent = stub_generator.last["generate"]
    assert sent["model"] == PROMPT_CFG["chat_model"]
    assert sent["prompt"] == "hello"
    assert stub_generator.last["url"] == PROMPT_CFG["ollama_url"]
    assert "stub answer" in capsys.readouterr().out


def test_prompt_does_not_take_the_shells_five_minute_lease(stub_generator):
    """A one-shot that pins the model for 5m costs the next index run a reload."""
    cli.cmd_prompt(_prompt_args())

    assert stub_generator.last["keep_alive"] == "30s"
    assert ollama_client.DEFAULT_KEEP_ALIVE == "30s"


def test_prompt_labels_the_answer_with_the_model_on_stderr(stub_generator, capsys):
    cli.cmd_prompt(_prompt_args())

    captured = capsys.readouterr()
    assert captured.out.strip() == "stub answer", "stdout is the answer alone, for pipes"
    assert PROMPT_CFG["chat_model"] in captured.err
    assert "ungrounded" in captured.err, "the missing retrieval is the caveat that matters"


def test_prompt_model_override_is_the_one_checked_and_used(stub_generator):
    cli.cmd_prompt(_prompt_args(model="llama3.2:3b"))

    assert stub_generator.last["required"] == ["llama3.2:3b"]
    assert stub_generator.last["generate"]["model"] == "llama3.2:3b"


def test_prompt_passes_system_and_options_through(stub_generator):
    cli.cmd_prompt(_prompt_args(system="be terse", temperature=0.1, num_predict=64))

    sent = stub_generator.last["generate"]
    assert sent["system"] == "be terse"
    assert sent["options"] == {"temperature": 0.1, "num_predict": 64}


def test_prompt_sends_no_options_block_when_none_were_asked_for(stub_generator):
    """`options: {}` is not the same as no options - it overrides the modelfile."""
    cli.cmd_prompt(_prompt_args())

    assert stub_generator.last["generate"]["options"] is None


def test_prompt_json_carries_the_model_and_says_it_is_ungrounded(stub_generator, capsys):
    cli.cmd_prompt(_prompt_args(json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload["model"] == PROMPT_CFG["chat_model"]
    assert payload["response"] == "stub answer"
    assert payload["grounded"] is False, "a consumer must not mistake this for /localgpu:ask"


def test_prompt_missing_model_exits_naming_the_pull(stub_generator):
    stub_generator.raises = ollama_client.ModelNotPulled(
        "Ollama does not have the model 'x'.\nPull it with:  ollama pull x")

    with pytest.raises(SystemExit) as excinfo:
        cli.cmd_prompt(_prompt_args(model="x"))

    assert "ollama pull x" in str(excinfo.value)


def test_prompt_a_generate_failure_is_reported_not_swallowed(stub_generator, monkeypatch):
    """The live failure this was written against: HTTP 500 out of /api/generate."""

    class OnlyGenerateFails(StubGenerator):
        def require_models(self, models):
            pass

        def generate(self, prompt, model, system=None, options=None, timeout=None):
            raise ollama_client.OllamaError(
                "Ollama returned HTTP 500 from /api/generate: CUDA error")

    monkeypatch.setattr(ollama_client, "OllamaClient", OnlyGenerateFails)

    with pytest.raises(SystemExit) as excinfo:
        cli.cmd_prompt(_prompt_args())

    assert "HTTP 500" in str(excinfo.value)


def test_read_prompt_prefers_the_argument():
    assert cli._read_prompt("from argv") == "from argv"


def test_read_prompt_reads_stdin_on_a_dash(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("from stdin"))

    assert cli._read_prompt("-") == "from stdin"


def test_read_prompt_reads_a_pipe_with_no_argument(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("piped in"))

    assert cli._read_prompt(None) == "piped in"


def test_read_prompt_on_a_bare_terminal_says_what_to_do_instead_of_hanging(monkeypatch):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(cli.sys, "stdin", Tty(""))

    with pytest.raises(SystemExit) as excinfo:
        cli._read_prompt(None)

    assert "no prompt" in str(excinfo.value)


def test_read_prompt_rejects_an_empty_pipe(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("   \n"))

    with pytest.raises(SystemExit) as excinfo:
        cli._read_prompt("-")

    assert "empty" in str(excinfo.value)


def test_models_marks_which_pulled_model_is_configured_for_what(stub_generator, capsys):
    assert cli.cmd_models(argparse.Namespace(json=False)) == 0

    out = capsys.readouterr().out
    assert "chat_model" in out and "embed_model" in out


def test_models_reports_a_configured_model_that_was_never_pulled(stub_generator, capsys):
    stub_generator.models = ["nomic-embed-text:latest"]

    cli.cmd_models(argparse.Namespace(json=False))

    err = capsys.readouterr().err
    assert PROMPT_CFG["chat_model"] in err
    assert "ollama pull" in err, "naming the fix is the point of the warning"


def test_models_json_lists_what_is_on_disk(stub_generator, capsys):
    cli.cmd_models(argparse.Namespace(json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload["models"] == stub_generator.models
    assert payload["chat_model"] == PROMPT_CFG["chat_model"]


def test_models_unreachable_ollama_exits_naming_the_fix(stub_generator):
    stub_generator.raises = ollama_client.OllamaUnavailable(
        "Cannot reach Ollama at http://127.0.0.1:11434 (refused).\nStart it with:  ollama serve")

    with pytest.raises(SystemExit) as excinfo:
        cli.cmd_models(argparse.Namespace(json=False))

    assert "ollama serve" in str(excinfo.value)


# -- prompt / models argument parsing ---------------------------------------


def test_prompt_defaults():
    args = cli.build_parser().parse_args(["prompt", "why is the sky blue"])

    assert args.prompt == "why is the sky blue"
    assert args.model is None
    assert args.json is False
    assert args.keep_alive == ollama_client.DEFAULT_KEEP_ALIVE
    assert args.timeout == ollama_client.DEFAULT_GENERATE_TIMEOUT
    assert args.func is cli.cmd_prompt


def test_prompt_options_parse():
    args = cli.build_parser().parse_args(
        ["prompt", "-", "--model", "llama3.2:3b", "--system", "be terse",
         "--temperature", "0.2", "--num-predict", "128", "--timeout", "45",
         "--keep-alive", "0", "--json"])

    assert (args.prompt, args.model, args.system) == ("-", "llama3.2:3b", "be terse")
    assert (args.temperature, args.num_predict) == (0.2, 128)
    assert (args.timeout, args.keep_alive, args.json) == (45.0, "0", True)


def test_prompt_with_no_positional_parses_for_the_pipe_case():
    args = cli.build_parser().parse_args(["prompt"])

    assert args.prompt is None


def test_models_defaults():
    args = cli.build_parser().parse_args(["models"])

    assert args.json is False
    assert args.func is cli.cmd_models


def test_an_unrecognized_flag_on_prompt_is_an_error():
    """Only `shell` forwards leftovers; a typo here must not be sent as a prompt."""
    with pytest.raises(SystemExit):
        cli.parse_args(["prompt", "hi", "--not-a-real-flag"])
