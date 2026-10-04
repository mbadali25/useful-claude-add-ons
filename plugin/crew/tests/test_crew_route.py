"""T-0023: plain-text lifecycle routing (`crew_route.py`).

Step 1 is the phrase table and whole-prompt matching; step 2 is `decide` --
route, ask or none, from files on disk; step 3 is `route.enabled`. The hook
wiring is `test_crew_route_hook.py`.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_config
import crew_context
import crew_route
import crew_ticket
from scope_fixtures import make_repo, make_ticket

_SCRIPT = os.path.join(context._ROOT, "hooks", "scripts", "crew_route.py")  # pylint: disable=protected-access

# --- step 1: the phrase table ---------------------------------------------------

# Every row's examples, and what each must produce. The ticket argument is the
# id upper-cased, or None for `it`/`this`/nothing.
EXAMPLES = {
    "brainstorm": [("brainstorm a login audit", None, "a login audit"),
                   ("Let's brainstorm Retry Budgets.", None, "Retry Budgets")],
    "spec": [("write the spec", None, None), ("write the spec for T-12", "T-12", None),
             ("spec it", None, None), ("spec t-0012", "T-0012", None),
             ("please write the spec.", None, None)],
    "plan": [("plan it", None, None), ("plan T-3", "T-3", None), ("write the plan", None, None),
             ("write the plan for this", None, None)],
    "implement": [("implement T-0012", "T-0012", None), ("implement it", None, None),
                  ("start implementing", None, None), ("start implementing T-9", "T-9", None),
                  ("now implement this!", None, None)],
    "review": [("review it", None, None), ("review T-4", "T-4", None),
               ("run the review", None, None), ("ok run the review", None, None)],
    "done": [("close it out", None, None), ("close T-5", "T-5", None),
             ("mark it done", None, None), ("mark T-5 as done", "T-5", None)],
    "continue": [("continue", None, None), ("keep going", None, None),
                 ("Carry on.", None, None), ("please continue", None, None)],
    "status": [("status", None, None), ("crew status", None, None), ("Status.", None, None)],
    # T-0057: the autopilot rows, after the lifecycle ones.
    "autopilot-status": [("autopilot status", None, None), ("autopilot status T-12", "T-12", None),
                         ("What's autopilot doing?", None, None),
                         ("what is autopilot doing", None, None), ("Autopilot status.", None, None)],
    "assign": [("please take care of the login audit.", None, "the login audit"),
               ("handle the Flaky Retry test", None, "the Flaky Retry test")],
    "goal": [("work toward zero flaky tests", None, "zero flaky tests"),
             ("work towards zero flaky tests", None, "zero flaky tests"),
             ("make it so the docs build in CI", None, "the docs build in CI")],
    "goal-resume": [("pick the goal back up", None, None), ("Resume the goal.", None, None)],
    "focus": [("focus on t-0012", "T-0012", None), ("Focus on T-3.", "T-3", None)],
}

AMBIGUOUS_PROMPTS = ["do it", "go", "go ahead", "yes", "ok", "sure", "done", "next", "ship it",
                     "Do it.", "  YES  ", "ok do it", "please go ahead!", "Done."]
APPROVE_PROMPTS = ["approve T-1", "approve it", "lgtm", "LGTM!", "/crew:approve T-1",
                   "approve", "approved", "ship it", "approve the plan", "i approve T-0023"]


def test_the_table_names_exactly_the_lifecycle_and_autopilot_intents():
    assert ([row[0] for row in crew_route.PHRASES], {len(row) for row in crew_route.PHRASES}) == \
        (list(EXAMPLES), {4})


@pytest.mark.parametrize("intent, prompt, ticket, topic",
                         [(i, p, t, top) for i, rows in EXAMPLES.items() for p, t, top in rows])
def test_every_row_matches_its_examples(intent, prompt, ticket, topic):
    got = crew_route.match(prompt)

    assert (got["intent"], got["ticket_arg"], got["topic"]) == (intent, ticket, topic)


@pytest.mark.parametrize("prompt", ["can you review it later?", "please review it and then stop",
                                    "I will implement T-1 tomorrow", "the status is fine",
                                    "why did you continue", "we should plan it better",
                                    "review it?", "status?", "implement it please"])
def test_mid_sentence_mention_is_not_a_route(prompt):
    assert crew_route.match(prompt) is None


@pytest.mark.parametrize("prompt", ["implement T-1\nand then review it", "continue\n",
                                    "status\r\n", "review it\r"])
def test_multiline_prompt_is_not_a_route(prompt):
    assert crew_route.match(prompt) is None


def test_long_prompt_is_not_a_route():
    prompt = "brainstorm " + "x" * 70

    assert (len(prompt.strip()) > crew_route.MAX_PROMPT_CHARS, crew_route.match(prompt),
            crew_route.match(prompt[:crew_route.MAX_PROMPT_CHARS])["intent"]) == \
        (True, None, "brainstorm")


@pytest.mark.parametrize("prompt", ["`implement T-1`", "`/crew:implement T-1`", "<implement T-1>",
                                    "/crew:implement T-1", "/status", "  /crew:review it"])
def test_backticked_command_is_not_a_route(prompt):
    assert crew_route.match(prompt) is None


@pytest.mark.parametrize("prompt", AMBIGUOUS_PROMPTS)
def test_ambiguous_phrases_route_nowhere(prompt):
    assert crew_route.match(prompt) is None


def test_the_ambiguous_guard_holds_against_a_row_that_claims_everything(monkeypatch):
    """The guard is the list, not the table's current shape: a later row that
    matched anything at all still cannot claim "yes"."""
    greedy = ("continue", None, "continue", (r".+",))
    monkeypatch.setattr(crew_route, "PHRASES", crew_route.PHRASES + (greedy,))
    monkeypatch.setattr(crew_route, "_COMPILED", crew_route.compile_table(crew_route.PHRASES))

    assert [crew_route.match(p) for p in AMBIGUOUS_PROMPTS] == [None] * len(AMBIGUOUS_PROMPTS)


def test_the_shape_guard_holds_against_a_row_that_claims_everything(monkeypatch):
    """Line breaks, length, and a leading `/`, `<` or backtick are refused
    before any row is tried, so a row that matched anything still gets none."""
    greedy = ("continue", None, "continue", (r".+",))
    monkeypatch.setattr(crew_route, "_COMPILED", crew_route.compile_table(
        crew_route.PHRASES + (greedy,)))
    prompts = ["a\nb", "a\r", "x" * 81, "/crew:approve T-1", "`status`", "<b>status</b>"]

    assert ([crew_route.match(p) for p in prompts], crew_route.match("anything")["intent"]) == \
        ([None] * len(prompts), "continue")


@pytest.mark.parametrize("prompt", APPROVE_PROMPTS)
def test_approve_phrasings_route_nowhere(prompt):
    assert crew_route.match(prompt) is None


@pytest.mark.parametrize("prompt", [None, 12, b"continue", ["continue"], ""])
def test_a_non_string_or_empty_prompt_is_not_a_route(prompt):
    assert crew_route.match(prompt) is None


def test_no_route_ever_names_approve():
    """Every row, every example's match, and every line `render` makes from
    it -- as a route and as an ask -- is free of `approve`."""
    rendered = []
    for intent, command, rule, patterns in crew_route.PHRASES:
        rendered += [intent, command or "", rule] + list(patterns)
    for intent, rows in EXAMPLES.items():
        for prompt, ticket, _topic in rows:
            got = crew_route.match(prompt)
            if got is None:
                continue
            rendered.append(got["command"] or "")
            command = crew_route.command_for(got, ticket or "T-1")
            for outcome in ("route", "ask"):
                rendered.append(crew_route.render({
                    "outcome": outcome, "intent": intent, "command": command,
                    "ticket": ticket or "T-1", "source": "named in the prompt",
                    "reason": "a reason", "candidates": ["T-1", "T-2"]}))

    assert [r for r in rendered if "approve" in r.lower()] == []


# --- step 2: decide -------------------------------------------------------------

def _index(root, *rows):
    path = root / ".work" / "INDEX.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{row}\n" for row in rows), encoding="utf-8")


def _folder(root, ticket):
    (root / ".work" / "tickets" / ticket).mkdir(parents=True, exist_ok=True)


def _repo(tmp_path):
    return make_repo(tmp_path, mode="off")


def test_explicit_id_routes(tmp_path):
    root = _repo(tmp_path)
    make_ticket(root, "T-7", activate=False)

    got = crew_route.decide(str(root), "implement t-7")

    assert (got["outcome"], got["command"], got["ticket"]) == \
        ("route", "/crew:implement T-7", "T-7")


def test_explicit_id_wins_over_the_active_ticket(tmp_path):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    make_ticket(root, "T-7", activate=False)

    assert crew_route.decide(str(root), "review T-7")["command"] == "/crew:review T-7"


def test_explicit_id_without_folder_asks(tmp_path):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")

    got = crew_route.decide(str(root), "implement T-99")

    assert (got["outcome"], got["ticket"], "T-99" in got["reason"]) == ("ask", None, True)


def test_it_uses_active_ticket(tmp_path):
    root = _repo(tmp_path)
    make_ticket(root, "T-1", activate=False)
    make_ticket(root, "T-2")
    _index(root, "T-1 | ready | low | r | one", "T-2 | ready | low | r | two")

    got = crew_route.decide(str(root), "review it")

    assert (got["outcome"], got["command"], got["source"]) == \
        ("route", "/crew:review T-2", "this worktree's active ticket")


def test_broken_pointer_asks(tmp_path):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    make_ticket(root, "T-2", activate=False)
    _index(root, "T-2 | ready | low | r | two")
    import shutil  # pylint: disable=import-outside-toplevel
    shutil.rmtree(root / ".work" / "tickets" / "T-1")

    got = crew_route.decide(str(root), "implement it")

    assert (got["outcome"], got["ticket"], "T-1" in got["reason"]) == ("ask", None, True)


def test_single_open_index_ticket_routes(tmp_path):
    root = _repo(tmp_path)
    make_ticket(root, "T-3", activate=False)
    _folder(root, "T-4")
    _index(root, "T-3 | ready | low | r | three", "T-4 | done | low | r | four",
           "T-5 | ready | low | r | no folder")

    got = crew_route.decide(str(root), "write the plan")

    assert (got["outcome"], got["command"], got["source"]) == \
        ("route", "/crew:plan T-3", ".work/INDEX.md (the only open ticket)")


def test_several_open_tickets_ask_and_list_them(tmp_path):
    """The first-open trap: `resolve_active`'s own INDEX fallback would answer
    T-3 here, and that is a guess."""
    root = _repo(tmp_path)
    for ticket in ("T-3", "T-4"):
        make_ticket(root, ticket, activate=False)
    _index(root, "T-3 | ready | low | r | three", "T-4 | ready | low | r | four")

    got = crew_route.decide(str(root), "implement it")

    assert (got["outcome"], got["ticket"], got["candidates"]) == ("ask", None, ["T-3", "T-4"])


def test_no_open_ticket_asks(tmp_path):
    root = _repo(tmp_path)

    got = crew_route.decide(str(root), "review it")

    assert (got["outcome"], got["candidates"], "no open ticket" in got["reason"]) == \
        ("ask", [], True)


def test_ask_lists_at_most_eight_candidates(tmp_path):
    root = _repo(tmp_path)
    tickets = [f"T-{n}" for n in range(1, 13)]
    for ticket in tickets:
        _folder(root, ticket)
    _index(root, *[f"{t} | ready | low | r | x" for t in tickets])

    line = crew_route.render(crew_route.decide(str(root), "implement it"))

    assert ("T-8," in line, "T-9" in line, "and 4 more" in line) == (True, False, True)


def test_continue_routes_to_next_phase(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    seen = []

    def fake(_top, ticket, **_):
        seen.append(ticket)
        return {"ticket": ticket, "phase": "implement", "stop": False, "reason": "approved",
                "command": f"/crew:implement {ticket}", "evidence": []}
    monkeypatch.setattr(crew_autopilot, "next_phase", fake)

    got = crew_route.decide(str(root), "keep going")

    assert (got["outcome"], got["command"], seen) == ("route", "/crew:implement T-1", ["T-1"])


def test_continue_reads_the_real_next_phase(tmp_path):
    """No monkeypatch: T-0004's reader, on a ticket with a direction and no
    spec, names `/crew:spec`."""
    root = _repo(tmp_path)
    folder = root / ".work" / "tickets" / "T-1"
    folder.mkdir(parents=True)
    (folder / "direction.md").write_text("go\n", encoding="utf-8")
    crew_ticket.activate(str(root), "T-1")
    _index(root, "T-1 | ready | high | r | one")

    got = crew_route.decide(str(root), "continue")

    assert (got["outcome"], got["command"]) == ("route", "/crew:spec T-1")


def test_continue_on_a_stop_phase_asks(tmp_path):
    root = _repo(tmp_path)
    folder = root / ".work" / "tickets" / "T-1"
    folder.mkdir(parents=True)
    crew_ticket.activate(str(root), "T-1")
    _index(root, "T-1 | ready | high | r | one")

    got = crew_route.decide(str(root), "continue")
    line = crew_route.render(got)

    assert (got["outcome"], got["intent"], line.startswith("crew route: "),
            "ask the user" in line, "/crew:brainstorm" in line,
            "invoke the Skill tool" in line) == ("ask", "continue", True, True, True, False)


def test_continue_that_names_approve_asks(tmp_path, monkeypatch):
    """Belt and braces for the exclusion: `next_phase` names the approve phase
    as a stop today, but a routed approve is never a phase's decision to make."""
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    monkeypatch.setattr(crew_autopilot, "next_phase", lambda top, ticket, **_: {
        "ticket": ticket, "phase": "approve", "stop": False, "reason": "unapproved",
        "command": f"/crew:approve {ticket}", "evidence": []})

    got = crew_route.decide(str(root), "continue")

    assert (got["outcome"], "approve" in got["reason"], "Skill" in crew_route.render(got)) == \
        ("ask", True, False)


def test_continue_that_raises_asks(tmp_path, monkeypatch):
    """A reader that crashes is "could not tell", never a route."""
    root = _repo(tmp_path)
    make_ticket(root, "T-1")

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(crew_autopilot, "next_phase", boom)

    got = crew_route.decide(str(root), "continue")

    assert (got["outcome"], "disk on fire" in got["reason"]) == ("ask", True)


def test_continue_with_a_refresh_command_routes_as_a_plain_command(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    monkeypatch.setattr(crew_autopilot, "next_phase", lambda top, ticket, **_: {
        "ticket": ticket, "phase": "refresh", "stop": False, "reason": "stale",
        "command": "graphify update .", "evidence": []})

    got = crew_route.decide(str(root), "continue")
    line = crew_route.render(got)

    assert (got["outcome"], "graphify update ." in line, "Skill tool" in line) == \
        ("route", True, False)


def test_brainstorm_routes_with_the_users_words(tmp_path):
    root = _repo(tmp_path)

    got = crew_route.decide(str(root), "brainstorm A Login Audit")
    line = crew_route.render(got)

    assert (got["outcome"], got["command"], "args A Login Audit" in line) == \
        ("route", "/crew:brainstorm A Login Audit", True)


def test_status_needs_no_ticket(tmp_path):
    root = _repo(tmp_path)

    got = crew_route.decide(str(root), "crew status")

    assert (got["outcome"], got["command"], got["ticket"]) == ("route", "/crew:status", None)


def test_unmatched_prompt_is_none(tmp_path):
    root = _repo(tmp_path)

    assert crew_route.decide(str(root), "what is this repo")["outcome"] == "none"


def test_render_route_names_the_skill_and_args(tmp_path):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")

    line = crew_route.render(crew_route.decide(str(root), "implement it"))

    assert line == ("crew route: the user's prompt asks for implement on T-1 (this worktree's "
                    "active ticket). Run the /crew:implement procedure: invoke the Skill tool "
                    "with skill crew:implement, args T-1. Its own checks still decide; if the "
                    "user plainly meant something else, ask.")


def test_render_none_is_empty():
    assert crew_route.render({"outcome": "none"}) == ""


def _snapshot(root):
    """Every file in the worktree and crew's state under the git common dir,
    as (mtime_ns, bytes)."""
    found = {}
    walks = [str(root), os.path.join(crew_ticket.common_dir(str(root)), "crew")]
    for base, dirs, files in (entry for top in walks for entry in os.walk(top)):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as handle:
                found[path] = (os.stat(path).st_mtime_ns, handle.read())
    return found


def test_decide_writes_nothing(tmp_path):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    make_ticket(root, "T-2", activate=False)
    _index(root, "T-1 | ready | low | r | one", "T-2 | ready | low | r | two")
    before = _snapshot(root)

    for prompt in ["implement it", "continue", "review T-2", "status", "brainstorm x",
                   "implement T-99", "what is this"]:
        crew_route.decide(str(root), prompt)

    assert _snapshot(root) == before


# --- step 3: route.enabled ------------------------------------------------------

def _global(tmp_path, monkeypatch, contents):
    path = tmp_path / "global-config.json"
    path.write_text(json.dumps(contents), encoding="utf-8")
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    import crew_state  # pylint: disable=import-outside-toplevel
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(path))


def _config(root, data):
    (root / ".crew" / "config.json").write_text(json.dumps(data), encoding="utf-8")


def test_off_by_default(tmp_path):
    root = _repo(tmp_path)

    assert crew_route.settings(str(root)) == {"enabled": False, "saw": False, "warnings": []}


def test_route_is_declared_false_in_both_defaults():
    assert (crew_config.default_config()["route"],
            crew_config.default_global_config()["route"]) == \
        ({"enabled": False}, {"enabled": False})


def test_repo_true_arms(tmp_path):
    root = _repo(tmp_path)
    _config(root, {"route": {"enabled": True}})

    assert crew_route.settings(str(root))["enabled"] is True


@pytest.mark.parametrize("value", ["true", "True", 1, "yes", "on", [True], {"x": 1}])
def test_string_true_is_off(tmp_path, value):
    root = _repo(tmp_path)
    _config(root, {"route": {"enabled": value}})

    got = crew_route.settings(str(root))

    assert (got["enabled"], got["saw"], len(got["warnings"])) == (False, value, 1)


def test_a_route_block_that_is_not_an_object_is_off_and_reported(tmp_path):
    root = _repo(tmp_path)
    _config(root, {"route": True})

    got = crew_route.settings(str(root))

    assert (got["enabled"], len(got["warnings"])) == (False, 1)


def test_global_true_arms(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, {"route": {"enabled": True}})
    root = _repo(tmp_path)

    assert crew_route.settings(str(root))["enabled"] is True


def test_repo_false_overrides_global_true(tmp_path, monkeypatch):
    _global(tmp_path, monkeypatch, {"route": {"enabled": True}})
    root = _repo(tmp_path)
    _config(root, {"route": {"enabled": False}})

    assert crew_route.settings(str(root))["enabled"] is False


def test_route_only_in_crew_json_is_reported(tmp_path):
    root = _repo(tmp_path)
    (root / ".crew" / "crew.json").write_text(json.dumps({"route": {"enabled": True}}),
                                              encoding="utf-8")

    got = crew_route.settings(str(root))

    assert (got["enabled"], got["warnings"]) == (False, [
        "route is set in .crew/crew.json, which crew does not read for this key; move it "
        "to .crew/config.json"])


def test_route_enabled_is_global_settable():
    kept, ignored = crew_config.filter_global({"route": {"enabled": True}})

    assert (kept, ignored, crew_config.is_global_path("route.enabled")) == \
        ({"route": {"enabled": True}}, [], True)


def _cli(tmp_path, *args):
    # A subprocess does not see conftest's GLOBAL_CONFIG_PATH monkeypatch, so the
    # child resolves `~` itself: point HOME (POSIX) and USERPROFILE (Windows) at
    # an empty directory, or a real `route.enabled: true` in the developer's
    # ~/.claude/crew/config.json leaks into the assertion below.
    return subprocess.run([sys.executable, _SCRIPT, *args], capture_output=True, text=True,
                          check=False, timeout=60, env=_cli_env(tmp_path))


def _cli_env(tmp_path):
    home = str(tmp_path / "home")
    return dict(os.environ, HOME=home, USERPROFILE=home)


def test_the_cli_child_gets_an_empty_home_on_every_platform(tmp_path):
    """POSIX expanduser reads HOME, Windows reads USERPROFILE: a child that
    inherits either one reads the developer's real global config."""
    env = _cli_env(tmp_path)

    assert (env["HOME"], env["USERPROFILE"]) == (str(tmp_path / "home"),) * 2


def test_cli_settings_and_decide_exit_zero(tmp_path):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")

    settings = _cli(tmp_path, "settings", "--root", str(root), "--json")
    decided = _cli(tmp_path, "decide", "--root", str(root), "--prompt", "implement it", "--json")
    text = _cli(tmp_path, "decide", "--root", str(root), "--prompt", "implement it")
    none = _cli(tmp_path, "decide", "--root", str(root), "--prompt", "hello there")

    assert (settings.returncode, json.loads(settings.stdout)["enabled"],
            decided.returncode, json.loads(decided.stdout)["command"],
            text.stdout.startswith("crew route: "), none.returncode, none.stdout) == \
        (0, False, 0, "/crew:implement T-1", True, 0, "outcome=none\n")


def test_cli_exits_zero_on_bad_arguments(tmp_path):
    assert _cli(tmp_path, "frobnicate").returncode == 0


# --- step 5: sabotage anchors ---------------------------------------------------

def test_every_route_sabotage_anchor_is_present_exactly_once():
    from sabotage_route import ROUTE_MUTATIONS  # pylint: disable=import-outside-toplevel
    for label, target, find, _replace, test in ROUTE_MUTATIONS:
        with open(target, encoding="utf-8") as handle:
            assert handle.read().count(find) == 1, label
        assert test.startswith(("tests/test_crew_route.py::",
                                "tests/test_crew_route_hook.py::")), label


# --- review round 1: every variable-length field is bounded --------------------

_HUGE = "x" * 5000
_ASK_TAIL = "before running anything."
_ROUTE_TAIL = "if the user plainly meant something else, ask."


@pytest.mark.parametrize("decision, tail", [
    ({"outcome": "ask", "intent": "continue", "ticket": "T-1", "reason": _HUGE}, _ASK_TAIL),
    ({"outcome": "ask", "intent": "continue", "ticket": "T-1",
      "reason": "line one\nline two " + _HUGE}, _ASK_TAIL),
    ({"outcome": "ask", "intent": "implement", "ticket": None, "reason": "several",
      "candidates": [_HUGE] * 20}, _ASK_TAIL),
    ({"outcome": "ask", "intent": "implement", "ticket": _HUGE, "reason": "r"}, _ASK_TAIL),
    ({"outcome": "ask", "intent": _HUGE, "ticket": _HUGE, "reason": _HUGE,
      "candidates": [_HUGE] * 20}, _ASK_TAIL),
    ({"outcome": "route", "intent": "continue", "ticket": _HUGE, "source": _HUGE,
      "phase": _HUGE, "command": "/crew:implement " + _HUGE}, _ROUTE_TAIL),
    ({"outcome": "route", "intent": "review", "ticket": _HUGE, "source": _HUGE,
      "command": "/crew:" + _HUGE}, _ROUTE_TAIL),
    ({"outcome": "route", "intent": "brainstorm", "ticket": None,
      "command": "not a crew command " + _HUGE}, _ROUTE_TAIL),
    # T-0057: the soft not-available ask and the goal route's undo sentence.
    ({"outcome": "ask", "intent": _HUGE, "ticket": _HUGE, "reason": _HUGE, "unavailable": True,
      "candidates": [_HUGE] * 20}, "otherwise answer the prompt as written."),
    ({"outcome": "ask", "intent": "assign", "reason": "line one\nline two " + _HUGE,
      "unavailable": True}, "otherwise answer the prompt as written."),
    ({"outcome": "route", "intent": "goal", "ticket": None,
      "command": "/crew:autopilot goal " + _HUGE}, "what changed and how to undo it."),
    ({"outcome": "route", "intent": "autopilot-status", "ticket": _HUGE, "source": _HUGE,
      "command": "/crew:autopilot status " + _HUGE}, _ROUTE_TAIL),
    ({"outcome": "route", "intent": "assign", "ticket": None,
      "command": "/crew:autopilot assign " + _HUGE}, _ROUTE_TAIL),
])
def test_render_is_one_bounded_line_whatever_the_fields(decision, tail):
    line = crew_route.render(decision)

    assert (line.startswith(crew_route.PREFIX), "\n" in line, line.endswith(tail),
            len(line) <= crew_route.MAX_LINE_CHARS) == (True, False, True, True)


def test_the_line_bound_fits_the_turn_budget():
    assert crew_route.MAX_LINE_CHARS < crew_context.TURN_CHARS


# --- T-0010: the policy subcommands are crew_autopilot.py's, not the command's --

def test_policy_subcommands_are_not_command_subcommands(tmp_path):
    root = make_repo(tmp_path, mode="off")
    make_ticket(root)

    got = [crew_autopilot.route_args(str(root), text)["stop"]
           for text in ("approve T-1", "questions-check T-1")]

    assert (crew_autopilot.SUBCOMMANDS, got) == (
        ("status", "run", "assign", "goal", "focus"), [True, True])


# --- T-0057: plain-text routing for the autopilot commands the router knows -----

_RESERVED = ["take care of the login audit", "work toward zero flaky tests", "focus on T-1",
             "pick the goal back up"]
_NEW_ROWS = ["autopilot status", "take care of the login audit",
             "work toward zero flaky tests", "focus on T-1", "pick the goal back up"]
_UNDO = "After it runs, tell the user in one line what changed and how to undo it."


def _all_available(monkeypatch):
    monkeypatch.setattr(crew_autopilot, "AVAILABLE", frozenset(crew_autopilot.SUBCOMMANDS))


def test_autopilot_status_routes(tmp_path):
    root = _repo(tmp_path)
    make_ticket(root, "T-12", activate=False)

    got = [crew_route.decide(str(root), p) for p in
           ("autopilot status", "What's autopilot doing?", "autopilot status t-12",
            "autopilot status T-99")]

    assert [(g["outcome"], g["command"], g["ticket"], g["unavailable"]) for g in got] == [
        ("route", "/crew:autopilot status", None, False),
        ("route", "/crew:autopilot status", None, False),
        ("route", "/crew:autopilot status T-12", "T-12", False),
        ("ask", None, None, False)]


def test_autopilot_status_route_line_names_the_skill(tmp_path):
    root = _repo(tmp_path)

    line = crew_route.render(crew_route.decide(str(root), "autopilot status"))

    assert line == ("crew route: the user's prompt asks for autopilot-status. Run the "
                    "/crew:autopilot procedure: invoke the Skill tool with skill crew:autopilot, "
                    "args status. Its own checks still decide; if the user plainly meant "
                    "something else, ask.")


@pytest.mark.parametrize("prompt", _RESERVED)
def test_a_reserved_subcommand_asks_softly(tmp_path, prompt):
    """origin/main's AVAILABLE is status and run: every other row asks, says
    the command is not available yet, and leaves the prompt to be answered."""
    root = _repo(tmp_path)
    make_ticket(root, "T-1")

    got = crew_route.decide(str(root), prompt)
    line = crew_route.render(got)

    assert (got["outcome"], got["unavailable"], got["command"], "arrives with" in got["reason"],
            "answer the prompt as written" in line, "which ticket" in line,
            "do not run it" in line, "\n" in line) == \
        ("ask", True, None, True, True, False, True, False)


def test_an_available_subcommand_routes(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    _all_available(monkeypatch)

    got = [crew_route.decide(str(root), p) for p in
           ("take care of the login audit", "work toward zero flaky tests", "focus on t-1",
            "focus on T-9")]

    assert [(g["outcome"], g["command"], g["unavailable"]) for g in got] == [
        ("route", "/crew:autopilot assign the login audit", False),
        ("route", "/crew:autopilot goal zero flaky tests", False),
        ("route", "/crew:autopilot focus T-1", False),
        ("ask", None, False)]


def test_a_subcommand_the_router_does_not_know_is_none(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    monkeypatch.setattr(crew_autopilot, "SUBCOMMANDS", ("status", "run", "assign", "goal"))

    got = crew_route.decide(str(root), "focus on T-1")

    assert (got["outcome"], crew_route.render(got)) == ("none", "")


def _raise(*_args, **_kwargs):
    raise RuntimeError("router on fire")


@pytest.mark.parametrize("fake", [_raise, lambda *_a, **_k: None,
                                  lambda *_a, **_k: {"sub": "assign"},
                                  lambda *_a, **_k: ["assign", False, ""]])
@pytest.mark.parametrize("prompt", _NEW_ROWS)
def test_an_unreadable_router_asks(tmp_path, monkeypatch, prompt, fake):
    """"Could not tell" is its own value: a router that raises or answers in a
    shape this module does not know is an ask, never a route and never none."""
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    monkeypatch.setattr(crew_autopilot, "route", fake)

    got = crew_route.decide(str(root), prompt)

    assert (got["outcome"], got["command"], "could not be read" in got["reason"]) == \
        ("ask", None, True)


def test_goal_resume_never_picks_a_slug(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    _all_available(monkeypatch)
    monkeypatch.setattr(crew_autopilot, "route",
                        lambda _top, first: {"sub": "run", "stop": False, "reason": ""})

    got = [crew_route.decide(str(root), p) for p in ("pick the goal back up", "resume the goal")]

    assert [(g["outcome"], g["command"], g["ticket"], "--goal <slug>" in g["reason"])
            for g in got] == [("ask", None, None, True)] * 2


@pytest.mark.parametrize("prompt", [
    "take care of it", "handle this", "handle that.", "Handle Them", "take care of everything",
    "work toward it", "make it so", "make it so.", "can you take care of the login audit?",
    "take care of the login audit?", "I will handle the login audit later", "focus on this",
    "focus on the tests", "focus on T-1?", "autopilot status please tell me", "work toward",
    "is autopilot status working?", "autopilot status?", "pick the goal back up?",
    "handle " + "x" * 90, "handle the login\naudit", "`handle the login audit`",
    "/crew:autopilot assign x", "autopilot T-3", "run autopilot", "approve T-1 via autopilot",
    "handle approve T-1", "take care of the Approve step", "work toward approve all"])
def test_autopilot_phrases_that_must_not_route(tmp_path, monkeypatch, prompt):
    """With every subcommand available, so a match would be a route."""
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    _all_available(monkeypatch)

    assert crew_route.decide(str(root), prompt)["outcome"] == "none"


@pytest.mark.parametrize("prompt", ["handle the O'Brien ticket", 'handle the "retry" bug',
                                    "take care of $HOME", "handle the x`y` bug",
                                    "handle C:\\temp", "work toward 'zero' flakes"])
def test_free_text_with_shell_characters_asks(tmp_path, monkeypatch, prompt):
    root = _repo(tmp_path)
    _all_available(monkeypatch)

    got = crew_route.decide(str(root), prompt)

    assert (got["outcome"], got["command"], got["unavailable"]) == ("ask", None, False)


def test_goal_route_line_names_the_undo(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    _all_available(monkeypatch)

    lines = {p: crew_route.render(crew_route.decide(str(root), p)) for p in
             ("work toward zero flaky tests", "take care of the login audit", "focus on T-1",
              "autopilot status", "implement T-1", "status")}

    assert {p: line.endswith(_UNDO) for p, line in lines.items()} == {
        "work toward zero flaky tests": True, "take care of the login audit": False,
        "focus on T-1": False, "autopilot status": False, "implement T-1": False,
        "status": False}


def test_every_decision_has_every_key(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    prompts = ["hello", "implement T-1", "implement T-99", "status", "continue",
               "autopilot status", "take care of the login audit", "focus on T-1",
               "pick the goal back up", "handle the O'Brien ticket"]
    got = [crew_route.decide(str(root), p) for p in prompts]
    _all_available(monkeypatch)
    got += [crew_route.decide(str(root), p) for p in prompts]

    assert ({frozenset(g) for g in got}, {g["unavailable"] for g in got}) == (
        {frozenset({"outcome", "intent", "command", "ticket", "source", "reason", "candidates",
                    "phase", "unavailable"})}, {True, False})


def test_autopilot_decide_writes_nothing(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    before = _snapshot(root)

    for available in (False, True):
        if available:
            _all_available(monkeypatch)
        for prompt in _NEW_ROWS + ["autopilot status T-1", "handle $x"]:
            crew_route.decide(str(root), prompt)

    assert _snapshot(root) == before


@pytest.mark.parametrize("prompt", ["handle the O'Brien ticket", "pick the goal back up"])
def test_an_autopilot_ask_that_is_not_about_a_ticket_never_says_which_ticket(
        tmp_path, monkeypatch, prompt):
    root = _repo(tmp_path)
    monkeypatch.setattr(crew_autopilot, "route",
                        lambda _top, first: {"sub": "run", "stop": False, "reason": ""})

    got = crew_route.decide(str(root), prompt)
    line = crew_route.render(got)

    assert (got["outcome"], "which ticket" in line, line.endswith("before running anything.")) \
        == ("ask", False, True)


# --- T-0057 review round 1: one structural rule for free text ------------------
# Every case runs with every subcommand available, so a miss would be a route.

def _decide_live(tmp_path, monkeypatch, prompt):
    root = _repo(tmp_path)
    make_ticket(root, "T-1")
    make_ticket(root, "T-12", activate=False)
    _all_available(monkeypatch)
    return crew_route.decide(str(root), prompt)


@pytest.mark.parametrize("prompt", [
    "handle the approval for T-12", "handle approving T-12", "take care of approvals",
    "work toward approval of T-12", "handle approv T-12", "handle a p p r o v e T-12",
    "handle \u0430pprove T-12", "handle the \u0430pproval for T-12",
    "handle \uff41\uff50\uff50\uff52\uff4f\uff56\uff45 T-12", "take care of \uff21PPROVALS",
    "handle the a\u200bpproval for T-12", "handle the audit then /crew:\u0430pprove T-12"])
def test_free_text_naming_approval_never_routes(tmp_path, monkeypatch, prompt):
    """B1: the stem and a letters-only collapse; lookalikes, fullwidth and
    hidden characters are outside the allowlist and ask first."""
    got = _decide_live(tmp_path, monkeypatch, prompt)

    assert (got["outcome"] != "route", got["command"],
            "approv" in crew_route.render(got).casefold()) == (True, None, False)


@pytest.mark.parametrize("prompt", [
    "handle it,", "handle it for me", "take care of that;", "handle this one", "handle them all",
    "handle everything else", "make it so it works", "take care of nothing much",
    "work toward something better"])
def test_free_text_that_starts_with_a_nothing_word_is_none(tmp_path, monkeypatch, prompt):
    """F1: the FIRST token, not only a whole-topic pronoun."""
    assert _decide_live(tmp_path, monkeypatch, prompt)["outcome"] == "none"


@pytest.mark.parametrize("prompt, answer", [
    ("take care of the login audit", {"sub": "status", "stop": False, "reason": ""}),
    ("take care of the login audit", {"sub": None, "stop": False, "reason": ""}),
    ("take care of the login audit", {"sub": 5, "stop": False, "reason": ""}),
    ("take care of the login audit", {"sub": ["assign"], "stop": False, "reason": ""}),
    ("focus on T-1", {"sub": "run", "stop": False, "reason": ""}),
    ("work toward zero flaky tests", {"sub": "assign", "stop": True, "reason": "x"}),
    ("pick the goal back up", {"sub": "goal", "stop": False, "reason": ""}),
    ("pick the goal back up", {"sub": None, "stop": True, "reason": "x"}),
])
def test_a_router_answering_another_subcommand_asks(tmp_path, monkeypatch, prompt, answer):
    """F2: `sub` must be a string naming the subcommand asked about (`run`
    for `--goal`); only the empty string is none."""
    monkeypatch.setattr(crew_autopilot, "route", lambda _top, _first: dict(answer))

    got = _decide_live(tmp_path, monkeypatch, prompt)

    assert (got["outcome"], got["command"], "could not be read" in got["reason"]) == \
        ("ask", None, True)


def test_an_empty_sub_is_none_for_every_new_row(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_autopilot, "route",
                        lambda _top, _first: {"sub": "", "stop": True, "reason": "unknown"})

    got = [_decide_live(tmp_path / str(n), monkeypatch, p)["outcome"]
           for n, p in enumerate(_NEW_ROWS)]

    assert got == ["none"] * len(_NEW_ROWS)


@pytest.mark.parametrize("prompt", ["focus on T-\u0661", "implement T-\u0661", "review t-\uff11",
                                    "autopilot status T-\u0967"])
def test_a_ticket_id_is_ascii_digits_only(prompt):
    """N1: `\\d` is any Unicode digit; an id is [0-9]."""
    assert crew_route.match(prompt) is None


@pytest.mark.parametrize("prompt", ["handle the audit\u2028and the docs",
                                    "take care of the audit\u2029then the docs",
                                    "work toward zero\x85flaky tests", "focus on T-1\u2029",
                                    "handle the audit\x0band the docs"])
def test_a_unicode_line_break_never_routes(tmp_path, monkeypatch, prompt):
    """N2: U+2028, U+2029, U+0085 (and VT/FF) break a line as surely as \\n."""
    assert _decide_live(tmp_path, monkeypatch, prompt)["outcome"] == "none"


@pytest.mark.parametrize("prompt", ["handle the docs/build failure", "take care of /tmp cleanup",
                                    "work toward green ci/cd", "handle the audit then /crew:x"])
def test_free_text_with_a_slash_asks(tmp_path, monkeypatch, prompt):
    """N3: a `/` anywhere in the text could be a command; ask."""
    got = _decide_live(tmp_path, monkeypatch, prompt)

    assert (got["outcome"], got["command"]) == ("ask", None)


@pytest.mark.parametrize("prompt", ["handle the login audit, do not", "take care of the release not",
                                    "handle the deploy, don't", "work toward zero flakes. not!",
                                    "handle the deploy dont", "handle the deploy, never mind",
                                    "handle the deploy nevermind", "take care of the release, no",
                                    "handle the audit nah", "handle the audit, cancel",
                                    "handle the audit, not now."])
def test_free_text_ending_in_a_negation_asks(tmp_path, monkeypatch, prompt):
    """N4: "handle the deploy, don't" says the opposite of the command."""
    got = _decide_live(tmp_path, monkeypatch, prompt)

    assert (got["outcome"], got["command"], "negation" in got["reason"]) == ("ask", None, True)


@pytest.mark.parametrize("prompt", ["handle the l\u043egin audit", "handle the \u0131ssue",
                                    "make \u0131t so the docs build", "focu\u017f on T-1",
                                    "work toward z\u00e9ro flaky tests"])
def test_a_non_ascii_letter_asks(tmp_path, monkeypatch, prompt):
    """Any non-ASCII letter in an assign, goal or focus prompt asks: Cyrillic,
    dotless i, long s (a Kelvin-sign id no longer matches at all)."""
    got = _decide_live(tmp_path, monkeypatch, prompt)

    assert (got["outcome"], got["command"], "non-ASCII" in got["reason"]) == ("ask", None, True)


@pytest.mark.parametrize("prompt, command", [
    ("handle the login audit", "/crew:autopilot assign the login audit"),
    ("handle the audit (part 2)", "/crew:autopilot assign the audit (part 2)"),
    ("take care of issue #12: retry_budget, part-2.",
     "/crew:autopilot assign issue #12: retry_budget, part-2"),
    ("work toward green CI; then docs", "/crew:autopilot goal green CI; then docs"),
    ("Let's handle the login audit!", "/crew:autopilot assign the login audit")])
def test_plain_ascii_work_still_routes(tmp_path, monkeypatch, prompt, command):
    """Must-allow for the allowlist: letters, digits, space and .,:;_#()'-."""
    got = _decide_live(tmp_path, monkeypatch, prompt)

    assert (got["outcome"], got["command"]) == ("route", command)


@pytest.mark.parametrize("prompt", [
    "handle \u0130t", "handle t\u0301his", "handle th\u0300at one",
    "handle the docs\uff0fbuild", "handle the audit\uff1f", "handle the \uff02retry\uff02 bug",
    "handle the docs\u2215build", "handle the docs\u29f8build", "handle the docs\u2044build",
    "handle the audit\x1cand the docs", "handle the audit\x1dand the docs",
    "handle the audit\x1eand the docs", "handle the audit\u202e", "handle the au\u200bdit",
    "handle the soft\u00adware audit", "handle the \uff4cogin audit", "handle i\u200bt",
    "handle the audit | tee x", "handle a & b", "handle the <b> tag", "handle *.log files",
    "work toward zero\tflaky tests"])
def test_a_character_outside_plain_ascii_asks(tmp_path, monkeypatch, prompt):
    """Review round 2: an allowlist, not a fold. Combining marks, fullwidth
    and lookalike slashes, the \\x1c-\\x1e separators, format characters and
    shell metacharacters all ask; none rides into a command."""
    got = _decide_live(tmp_path, monkeypatch, prompt)

    assert (got["outcome"], got["command"]) == ("ask", None)


@pytest.mark.parametrize("prompt", ["implement \u017f-12", "focus on \u212a-12", "review \u0131-1",
                                    "autopilot status \u017f-12", "plan t\u017f-1"])
def test_a_ticket_id_is_ascii_letters_only(prompt):
    """NIT-1: IGNORECASE lets [a-z] match a long s, a Kelvin sign or a
    dotless i; an id's letters are ASCII."""
    assert crew_route.match(prompt) is None


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_a_null_stop_reason_renders_not_available_yet(tmp_path, monkeypatch, reason):
    """N5: never "but None;"."""
    monkeypatch.setattr(crew_autopilot, "route",
                        lambda _top, first: {"sub": first, "stop": True, "reason": reason})

    line = crew_route.render(_decide_live(tmp_path, monkeypatch, "take care of the login audit"))

    assert ("None" in line, "not available yet" in line, "but ;" in line) == (False, True, False)
