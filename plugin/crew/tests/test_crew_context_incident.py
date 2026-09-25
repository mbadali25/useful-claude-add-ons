"""The incident banner in the context hook's SessionStart output.

crew 1.0 removed pm_brief, which was the only thing that announced an open
incident when a session started. The context hook now carries one line for an
open or expired-unclosed incident, inside the startup budget, and emits it
whether or not `memory.inject` is on.

Same isolation as test_crew_context.py: throwaway repos, never the machine's
`~/.claude`.
"""
import json
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_context
import crew_incident
from context_fixtures import make_repo, payload


@pytest.fixture(autouse=True)
def _isolated_recall(tmp_path, monkeypatch):
    monkeypatch.setenv("CREW_VAULT_OPS", str(tmp_path / "absent-vault-ops.py"))
    monkeypatch.setenv("CREW_OBSIDIAN_CONFIG", str(tmp_path / "absent-obsidian.json"))
    monkeypatch.delenv("OBSIDIAN_VAULT_PLUGIN_ROOT", raising=False)


def _start(root, source="startup"):
    data = payload("SessionStart", root, source=source)
    return crew_context.run(data, json.dumps(data).encode())


def _incident_lines(text):
    return [line for line in text.splitlines() if line.startswith("INCIDENT ")]


def test_an_active_incident_is_announced_with_its_id_time_left_and_gates(tmp_path):
    root = make_repo(tmp_path)
    # Declared 30s in the future, so "90m left" holds for the whole run.
    state = crew_incident.declare(str(root), "prod is down", ttl_minutes=90, now=time.time() + 30)

    lines = _incident_lines(_start(root))

    assert lines == [f"INCIDENT {state['id']} open: 90m left; gates stood down: verify, promote; "
                     "0 skipped so far. Close it with /crew:emergency end."]


def test_no_incident_means_no_banner(tmp_path):
    root = make_repo(tmp_path)

    text = _start(root)

    assert (text.startswith("crew context (startup)"), _incident_lines(text)) == (True, [])


def test_an_expired_unclosed_incident_is_announced_as_expired(tmp_path):
    root = make_repo(tmp_path)
    state = crew_incident.declare(str(root), "prod is down", ttl_minutes=30, now=time.time() - 3600)

    lines = _incident_lines(_start(root))

    assert lines == [f"INCIDENT {state['id']} expired and not closed: gates are back on; "
                     "0 skipped gate(s) still owed. Close it with /crew:emergency end."]


def test_an_incident_that_stands_nothing_down_gets_no_banner(tmp_path):
    root = make_repo(tmp_path, config={"emergency": {"standDown": False}})
    crew_incident.declare(str(root), "prod is down", cfg={"emergency": {"standDown": False}})

    assert _incident_lines(_start(root)) == []


@pytest.mark.parametrize("inject", [False, True, None])
def test_the_banner_is_emitted_whatever_memory_inject_says(tmp_path, inject):
    root = make_repo(tmp_path, config={}, inject=inject)
    state = crew_incident.declare(str(root), "prod is down")

    lines = _incident_lines(_start(root, source="clear"))

    assert [line.split(":")[0] for line in lines] == [f"INCIDENT {state['id']} open"]


def test_with_inject_off_the_banner_is_all_that_is_emitted(tmp_path):
    root = make_repo(tmp_path, config={}, inject=False)
    crew_incident.declare(str(root), "prod is down")

    text = _start(root)

    assert (len(text.splitlines()), text.startswith("INCIDENT ")) == (1, True)


def test_with_inject_off_and_no_incident_nothing_is_emitted(tmp_path):
    root = make_repo(tmp_path, config={}, inject=False)

    assert _start(root) == ""


def test_the_banner_rides_inside_the_startup_budget_even_when_the_codemap_is_huge(tmp_path):
    many = {f"sub{i:02d}": ([f"s{i}/a.py"], [f"mark {i}"]) for i in range(40)}
    root = make_repo(tmp_path, subsystems=many, handoff="# Handoff\n\n## Next action\n" + "x" * 2000 + "\n")
    crew_incident.declare(str(root), "prod is down")

    text = _start(root)

    assert (len(_incident_lines(text)), len(text) <= crew_context.STARTUP_CHARS,
            len(text.splitlines()) <= crew_context.STARTUP_LINES) == (1, True, True)
