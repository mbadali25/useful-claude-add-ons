"""T-0023 step 4: the route line through crew's UserPromptSubmit context hook.

Driven through both wrappers, `crew-context.sh` and `crew-context.ps1`, with
the same payload. The .ps1 cases need pwsh and run with `OS=Windows_NT` so
its flavour guard proceeds on a Linux host; without pwsh they skip and say so.
`HOME` and `USERPROFILE` point into tmp_path, so the machine-global crew
config the hook reads is one that does not exist -- never the developer's
real one, on POSIX or on Windows.
"""
import json
import os
import pathlib
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_context
import crew_fixtures
import crew_route
import crew_ticket
from context_fixtures import log_records, make_repo, payload

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "hooks" / "scripts"
PWSH = crew_fixtures.resolve_pwsh()
BASH = crew_fixtures.resolve_bash()
needs_bash = pytest.mark.skipif(BASH is None,
                                reason="bash not installed - the sh flavour was NOT run")
needs_pwsh = pytest.mark.skipif(PWSH is None,
                                reason="pwsh not installed - the .ps1 flavour was NOT run")

SUBSYSTEMS = {"review": (["src/review/core.py"], ["REVIEW-LANDMINE the verdict is cached"])}
# Recorded from the hook at origin/main 1e0706ac (before T-0023) for this
# fixture and the prompt "review T-1": the codemap slice the prompt names, and
# nothing else. `{head}` is the fixture commit's short sha.
BEFORE = ('{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": '
          '"[codemap:review anchor {head} current] .crew/codemap/review.md\\nCovers: The review '
          'subsystem.\\n- REVIEW-LANDMINE the verdict is cached."}}\n')
ROUTE = ("crew route: the user's prompt asks for review on T-1 (named in the prompt). Run the "
         "/crew:review procedure: invoke the Skill tool with skill crew:review, args T-1. Its own "
         "checks still decide; if the user plainly meant something else, ask.")


def _repo(tmp_path, armed=None, inject=True):
    config = None if armed is None else {"route": {"enabled": armed}}
    root = make_repo(tmp_path, subsystems=SUBSYSTEMS, config=config, inject=inject)
    (root / ".work" / "tickets" / "T-1").mkdir(parents=True)
    return root


def _head(root):
    return subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=root, capture_output=True,
                          text=True, check=True).stdout.strip()


def _env(tmp_path, **extra):
    # HOME alone isolates nothing on Windows: Python's expanduser reads
    # USERPROFILE there, so a real route.enabled: true in the developer's
    # %USERPROFILE%\.claude\crew\config.json would arm the "unarmed" cases
    # (review round 1). Both point at the same empty directory.
    home = str(tmp_path / "home")
    env = dict(os.environ, CREW_VAULT_OPS=str(tmp_path / "absent.py"),
               CREW_OBSIDIAN_CONFIG=str(tmp_path / "absent.json"), HOME=home, USERPROFILE=home)
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.update(extra)
    return env


def _raw(root, prompt, prompt_id="p1"):
    data = payload("UserPromptSubmit", root, prompt=prompt, prompt_id=prompt_id)
    return json.dumps(data).encode()


def _run(flavour, tmp_path, root, raw, *args):
    if flavour == "sh":
        cmd, env = [BASH, str(SCRIPTS / "crew-context.sh"), *args], _env(tmp_path)
    else:
        if PWSH is None:
            pytest.skip("pwsh not installed - the .ps1 flavour was NOT run")
        ps_args = ["-Harness", args[1]] if args else []
        cmd = [PWSH, "-NoProfile", "-File", str(SCRIPTS / "crew-context.ps1"), *ps_args]
        env = _env(tmp_path, OS="Windows_NT")
    done = subprocess.run(cmd, input=raw, cwd=root, capture_output=True, env=env, check=False,
                          timeout=60)
    out = done.stdout.decode()
    assert (done.returncode, "decision" in out) == (0, False), done.stderr
    return out


def _context(out):
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out.strip() else ""


FLAVOURS = ("sh", pytest.param("ps1", marks=needs_pwsh))


@needs_bash
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_armed_matching_prompt_puts_the_route_line_first(tmp_path, flavour):
    root = _repo(tmp_path, armed=True)

    out = _run(flavour, tmp_path, root, _raw(root, "review T-1"))
    before = _context(BEFORE.replace("{head}", _head(root)))

    assert _context(out) == ROUTE + "\n" + before


# T-0057: `/crew:autopilot status` runs on main, so its row routes.
STATUS_ROUTE = ("crew route: the user's prompt asks for autopilot-status. Run the /crew:autopilot "
                "procedure: invoke the Skill tool with skill crew:autopilot, args status. Its own "
                "checks still decide; if the user plainly meant something else, ask.")


@needs_bash
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_armed_autopilot_status_puts_the_route_line_first(tmp_path, flavour):
    root = _repo(tmp_path, armed=True)

    out = _context(_run(flavour, tmp_path, root, _raw(root, "autopilot status")))

    assert out.split("\n")[0] == STATUS_ROUTE


@needs_bash
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_armed_reserved_autopilot_phrase_asks_softly(tmp_path, flavour):
    """`assign` is not in crew_autopilot.AVAILABLE on main: the line runs
    nothing and leaves the prompt to be answered as written."""
    root = _repo(tmp_path, armed=True)

    out = _context(_run(flavour, tmp_path, root, _raw(root, "take care of the login audit")))
    first = out.split("\n")[0]

    assert (first.startswith("crew route: "), "arrives with" in first,
            first.endswith("otherwise answer the prompt as written."), "which ticket" in out) == \
        (True, True, True, False)


@needs_bash
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_unarmed_autopilot_phrase_has_no_route_line(tmp_path, flavour):
    root = _repo(tmp_path)

    out = _run(flavour, tmp_path, root, _raw(root, "autopilot status"))

    assert "crew route" not in out


@needs_bash
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_unarmed_output_is_byte_identical_to_before(tmp_path, flavour):
    root = _repo(tmp_path)

    out = _run(flavour, tmp_path, root, _raw(root, "review T-1"))

    assert out == BEFORE.replace("{head}", _head(root))


@needs_bash
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_explicitly_off_output_is_byte_identical_to_before(tmp_path, flavour):
    root = _repo(tmp_path, armed=False)

    out = _run(flavour, tmp_path, root, _raw(root, "review T-1"))

    assert out == BEFORE.replace("{head}", _head(root))


@needs_bash
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_armed_non_matching_prompt_has_no_route_line(tmp_path, flavour):
    root = _repo(tmp_path, armed=True)

    out = _run(flavour, tmp_path, root, _raw(root, "what does the review subsystem do"))

    assert (out.strip() != "", "crew route" in out) == (True, False)


@needs_bash
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_codex_harness_never_routes(tmp_path, flavour):
    root = _repo(tmp_path, armed=True)

    out = _run(flavour, tmp_path, root, _raw(root, "review T-1"), "--harness", "codex")

    assert out == BEFORE.replace("{head}", _head(root))


@needs_bash
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_inject_false_emits_nothing_even_armed(tmp_path, flavour):
    root = _repo(tmp_path, armed=True, inject=False)

    out = _run(flavour, tmp_path, root, _raw(root, "review T-1"))

    assert out == ""


@needs_bash
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_ask_is_emitted_alone_when_nothing_else_is(tmp_path, flavour):
    """A route item is its own source kind, so the all-header drop does not
    swallow it on a prompt that names no subsystem."""
    root = _repo(tmp_path, armed=True)

    out = _context(_run(flavour, tmp_path, root, _raw(root, "implement T-99")))

    assert (out.startswith("crew route: "), "T-99" in out, "ask the user" in out) == \
        (True, True, True)


@needs_bash
@needs_pwsh
def test_both_flavours_same_payload_only_one_emits(tmp_path):
    root = _repo(tmp_path, armed=True)
    raw = _raw(root, "review T-1")

    ps = _run("ps1", tmp_path, root, raw)
    sh = _run("sh", tmp_path, root, raw)

    assert (_context(ps).startswith(ROUTE), sh) == (True, "")


@needs_bash
def test_the_log_records_the_route(tmp_path):
    root = _repo(tmp_path, armed=True)

    _run("sh", tmp_path, root, _raw(root, "review T-1"))

    assert log_records(root)[-1]["route"] == {"outcome": "route", "intent": "review",
                                              "ticket": "T-1"}


def test_a_raising_router_costs_only_the_route_line(tmp_path, monkeypatch):
    root = _repo(tmp_path, armed=True)
    monkeypatch.setenv("CREW_VAULT_OPS", str(tmp_path / "absent.py"))
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(tmp_path / "absent.json"))

    def boom(*_args, **_kwargs):
        raise RuntimeError("router on fire")
    monkeypatch.setattr(crew_route, "decide", boom)
    data = payload("UserPromptSubmit", root, prompt="review T-1", prompt_id="p1")

    text = crew_context.run(data, json.dumps(data).encode())

    assert (text, log_records(root)[-1]["route"]) == \
        (_context(BEFORE.replace("{head}", _head(root))), "error")


def test_a_raising_settings_reader_costs_only_the_route_line(tmp_path, monkeypatch):
    root = _repo(tmp_path, armed=True)
    monkeypatch.setenv("CREW_VAULT_OPS", str(tmp_path / "absent.py"))
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(tmp_path / "absent.json"))

    def boom(*_args, **_kwargs):
        raise ValueError("config on fire")
    monkeypatch.setattr(crew_route, "settings", boom)
    data = payload("UserPromptSubmit", root, prompt="review T-1", prompt_id="p2")

    text = crew_context.run(data, json.dumps(data).encode())

    assert text == _context(BEFORE.replace("{head}", _head(root)))


def test_a_task_notification_is_never_routed(tmp_path, monkeypatch):
    root = _repo(tmp_path, armed=True)
    calls = []
    monkeypatch.setattr(crew_route, "decide", lambda *a: calls.append(a) or {"outcome": "none"})
    data = payload("UserPromptSubmit", root, prompt="<task-notification>continue", prompt_id="p3")

    crew_context.run(data, json.dumps(data).encode())

    assert not calls


def test_a_raising_router_is_logged_even_when_nothing_is_emitted(tmp_path, monkeypatch):
    root = _repo(tmp_path, armed=True)
    monkeypatch.setenv("CREW_VAULT_OPS", str(tmp_path / "absent.py"))
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(tmp_path / "absent.json"))

    def boom(*_args, **_kwargs):
        raise RuntimeError("router on fire")
    monkeypatch.setattr(crew_route, "decide", boom)
    data = payload("UserPromptSubmit", root, prompt="implement it", prompt_id="p4")

    text = crew_context.run(data, json.dumps(data).encode())

    assert (text, log_records(root)[-1]["route"]) == ("", "error")


def _stopped_on_a_long_open_question(tmp_path, chars):
    root = _repo(tmp_path, armed=True)
    folder = root / ".work" / "tickets" / "T-1"
    (folder / "direction.md").write_text(
        "go\n\n## Open questions\n\n- " + "q" * chars + "\n", encoding="utf-8")
    (root / ".work" / "INDEX.md").write_text("T-1 | ready | high | r | one\n", encoding="utf-8")
    crew_ticket.activate(str(root), "T-1")
    return root


def test_an_over_long_stop_reason_never_drops_the_ask_line(tmp_path, monkeypatch):
    """Review round 1: a 2,100-character open question made the ask line
    longer than TURN_CHARS, and `fit` dropped it whole. The reason is clipped
    instead, so the ask survives and still ends by telling Claude to ask."""
    root = _stopped_on_a_long_open_question(tmp_path, 2100)
    monkeypatch.setenv("CREW_VAULT_OPS", str(tmp_path / "absent.py"))
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(tmp_path / "absent.json"))
    data = payload("UserPromptSubmit", root, prompt="continue", prompt_id="p5")

    text = crew_context.run(data, json.dumps(data).encode())

    assert (text.startswith("crew route: "), "\n" in text,
            text.endswith("ask the user before running anything.")) == (True, False, True)


def test_the_hook_child_gets_an_empty_home_on_every_platform(tmp_path):
    """Review round 1: HOME alone left Windows reading the real config."""
    env = _env(tmp_path)

    assert (env["HOME"], env["USERPROFILE"]) == (str(tmp_path / "home"),) * 2
