"""T-0012: `/crew:autopilot goal` -- the goal file, the proposal, the printed
`/goal` line and the split approval.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_goals.py -q

`goal-propose` turns a proposal staged under `.work/autopilot/` into the goal
file `.work/autopilot/<slug>.json` (schema 1) and prints the `/goal <condition>`
line for the owner to paste: autopilot never runs `/goal`, and reports its
state as `printed`, never `set`. `goal-approve` answers the split approval: the
owner's `/crew:approve goal:<slug>` receipt bound to the proposal's hash, or
`autopilot.approval` re-asked on every read. Minting, `--goal` resume, backlog
and caps are L-0541's; the hook that records the owner's receipt is a separate
harness change, so here the receipt is only read. Every repository is built
under tmp_path; nothing touches the real one or ~/.claude.
"""
import json
import os
import re
import subprocess
import sys

import context  # pylint: disable=unused-import
import crew_autopilot
import crew_resume
import crew_ticket
import pytest
from scope_fixtures import make_repo

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPT = os.path.join(_ROOT, "hooks", "scripts", "crew_autopilot.py")
_COMMAND = os.path.join(_ROOT, "commands", "autopilot.md")
MISSING = object()

TICKETS = [{"title": "add the export endpoint", "risk": "low", "depends_on": []},
           {"title": "wire the export button", "risk": "low", "depends_on": [0]},
           {"title": "document the export", "risk": "low", "depends_on": [0, 1]}]
PROPOSAL = {"done_condition": "the export ships behind a flag and its tests pass",
            "findings": ["the API has no export route yet", "the UI has a menu slot"]}
GOAL = "Ship the CSV export, \"quoted\" and $literal"
SET_WORDS = ("goal is set", "goal is active")


# --- fixtures ----------------------------------------------------------------

def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _repo(tmp_path, approval="risk", allow=True, armed=True):
    root = make_repo(tmp_path, mode="off")
    scope = {"mode": "off"}
    if allow is not MISSING:
        scope["allowCliApproval"] = allow
    block = {"mode": "plan" if armed is True else (armed or "off")}
    if approval is not MISSING:
        block["approval"] = approval
    _write(root / ".crew" / "config.json", json.dumps({"scope": scope, "autopilot": block}))
    return root


def _tickets(*risks):
    return [{"title": f"ticket {n}", "risk": risk, "depends_on": [n - 1] if n else []}
            for n, risk in enumerate(risks)]


def _goal(root, tickets=None, proposal=None, goal=GOAL):
    return crew_autopilot.write_goal(str(root), goal, dict(proposal or PROPOSAL),
                                     [dict(t) for t in (tickets or TICKETS)])


def _stage(root, name="g.proposal.json", **over):
    data = {"goal": GOAL, "done_condition": PROPOSAL["done_condition"],
            "findings": PROPOSAL["findings"], "tickets": TICKETS}
    data.update(over)
    path = root / ".work" / "autopilot" / name
    _write(path, json.dumps(data))
    return path


def _receipt(root, slug, digest, via="user-prompt"):
    path = crew_autopilot.goal_receipt_path(str(root), slug)
    _write(path, json.dumps({"proposal_sha256": digest, "approved_at": "2026-10-04T00:00:00Z",
                             "approved_via": via, "session_id": "s", "prompt_id": "p"}))
    return path


def _main(root, *argv):
    return crew_autopilot.main([argv[0], "--root", str(root)] + list(argv[1:]))


def _cli(root, *argv):
    return subprocess.run([sys.executable, _SCRIPT, argv[0], "--root", str(root)]
                          + list(argv[1:]), capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)


def _files(root):
    found = {}
    walks = [str(root), os.path.join(crew_ticket.common_dir(str(root)), "crew")]
    for base, dirs, names in (entry for top in walks for entry in os.walk(top)):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            with open(os.path.join(base, name), "rb") as handle:
                found[os.path.join(base, name)] = handle.read()
    return found


# --- step 1: the goal file and the proposal ------------------------------------

@pytest.mark.parametrize("goal", [GOAL, "", "   ", "!!!", "---x---", "A" * 300,
                                  "été export", "9 lives", "-lead", "x\ny\tz"])
def test_slug_matches_resume_grammar(tmp_path, goal):
    root = make_repo(tmp_path, mode="off")

    slug = crew_autopilot.slugify(str(root), goal)

    assert (bool(crew_resume._GOAL_SLUG_RE.match(slug)),  # pylint: disable=protected-access
            len(slug) <= crew_autopilot.GOAL_SLUG_MAX + 3) == (True, True)


def test_slug_shape(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = [crew_autopilot.slugify(str(root), text) for text in (GOAL, "", "!!", "A" * 99)]

    assert got == ["ship-the-csv-export-quoted-and-literal", "goal", "goal", "a" * 40]


def test_slug_collision_suffix(tmp_path):
    root = make_repo(tmp_path, mode="off")

    slugs = [_goal(root, goal="same words")["slug"] for _ in range(3)]

    assert slugs == ["same-words", "same-words-2", "same-words-3"]


def test_goal_round_trip(tmp_path):
    root = make_repo(tmp_path, mode="off")

    made = _goal(root)
    got = crew_autopilot.read_goal(str(root), made["slug"])

    assert (made["path"] == os.path.join(str(root), ".work", "autopilot", made["slug"] + ".json"),
            got["schema"], got["goal"], got["slug"], got["proposal"],
            [{k: t[k] for k in ("title", "risk", "depends_on")} for t in got["tickets"]],
            [t["id"] for t in got["tickets"]], got["approval"], got["caps"], got["runs"]) == (
        True, 1, GOAL, made["slug"], PROPOSAL, TICKETS, [None] * 3, None, None, [])


def test_goal_file_written_through_a_temp_file(tmp_path, monkeypatch):
    root = make_repo(tmp_path, mode="off")
    seen = []
    real = os.replace
    monkeypatch.setattr(crew_autopilot.os, "replace",
                        lambda src, dst: (seen.append((src, dst)), real(src, dst))[1])

    made = _goal(root)

    assert ([dst for _src, dst in seen] == [made["path"]],
            os.listdir(os.path.dirname(made["path"]))) == (True, [made["slug"] + ".json"])


@pytest.mark.parametrize("deps", [[[1], [0]], [[0]], [[], [2], [1]]],
                         ids=["two-cycle", "self", "three-with-cycle"])
def test_dependency_cycle_refused(tmp_path, deps):
    root = make_repo(tmp_path, mode="off")
    tickets = [{"title": f"t{n}", "risk": "low", "depends_on": d} for n, d in enumerate(deps)]

    with pytest.raises(crew_autopilot.GoalError, match="cycle"):
        _goal(root, tickets=tickets)

    assert not os.path.isdir(str(root / ".work" / "autopilot"))


@pytest.mark.parametrize("deps", [[3], [-1], ["0"], [True], [0.0], "0", None, [0, 0]],
                         ids=["past-end", "negative", "string", "bool", "float", "not-list",
                              "none", "twice"])
def test_unknown_dependency_refused(tmp_path, deps):
    root = make_repo(tmp_path, mode="off")
    tickets = [{"title": "t0", "risk": "low", "depends_on": []},
               {"title": "t1", "risk": "low", "depends_on": deps}]

    with pytest.raises(crew_autopilot.GoalError, match="depends_on"):
        _goal(root, tickets=tickets)


def test_dependency_order_is_the_list_order(tmp_path):
    root = make_repo(tmp_path, mode="off")
    tickets = [{"title": "t0", "risk": "low", "depends_on": [1]},
               {"title": "t1", "risk": "low", "depends_on": []}]

    with pytest.raises(crew_autopilot.GoalError, match="dependency order"):
        _goal(root, tickets=tickets)


@pytest.mark.parametrize("bad", [{"title": "a|b"}, {"title": "a\nb"}, {"title": ""},
                                 {"title": None}, {"risk": None}, {"risk": 3}],
                         ids=["bar", "newline", "empty", "none", "risk-none", "risk-int"])
def test_ticket_mint_would_refuse_is_refused_now(tmp_path, bad):
    root = make_repo(tmp_path, mode="off")
    ticket = dict({"title": "ok", "risk": "low", "depends_on": []}, **bad)

    with pytest.raises(crew_autopilot.GoalError):
        _goal(root, tickets=[ticket])


@pytest.mark.parametrize("tickets", [[], "x", None, [None]], ids=["empty", "str", "none", "item"])
def test_no_usable_tickets_refused(tmp_path, tickets):
    root = make_repo(tmp_path, mode="off")

    with pytest.raises(crew_autopilot.GoalError):
        crew_autopilot.write_goal(str(root), GOAL, dict(PROPOSAL), tickets)


@pytest.mark.parametrize("risks,want", [
    (("low", "low"), {"risk": "low", "known": True}),
    (("low", "med"), {"risk": "med", "known": True}),
    (("med", "high", "low"), {"risk": "high", "known": True}),
    (("low", "LOW"), {"risk": "high", "known": False}),
    (("low", "lo"), {"risk": "high", "known": False}),
    (("low", ""), {"risk": "high", "known": False}),
    ((), {"risk": "high", "known": False}),
])
def test_goal_risk_is_highest(risks, want):
    assert crew_autopilot.goal_risk(_tickets(*risks)) == want


@pytest.mark.parametrize("cond", [MISSING, None, "", "   ", "\n\t", "///", 7],
                         ids=["missing", "none", "empty", "blank", "control", "slashes", "int"])
def test_proposal_without_done_condition_refused(tmp_path, cond):
    root = make_repo(tmp_path, mode="off")
    proposal = dict(PROPOSAL)
    if cond is MISSING:
        del proposal["done_condition"]
    else:
        proposal["done_condition"] = cond

    with pytest.raises(crew_autopilot.GoalError, match="done_condition"):
        _goal(root, proposal=proposal)

    assert not os.path.isdir(str(root / ".work" / "autopilot"))


@pytest.mark.parametrize("cond", ["ships\nand /goal clear\r\nnow", "x" * 1000,
                                  "a\x00b\x1b[31mc d\x85e", "/goal clear", "  // spaced"])
def test_goal_line_single_line_and_capped(cond):
    line = crew_autopilot.goal_line({"proposal": {"done_condition": cond}})
    condition = line[len("/goal "):]

    assert (line.startswith("/goal "), len(line) <= crew_autopilot.GOAL_LINE_MAX,
            len(line.splitlines()), line.isprintable(), condition[:1] not in ("/", " ")) == (
        True, True, 1, True, True)


def test_goal_line_keeps_human_stop_clause():
    for cond in ("short", "x" * 1000):
        line = crew_autopilot.goal_line({"proposal": {"done_condition": cond}})
        assert line.endswith(" " + crew_autopilot.GOAL_STOP_CLAUSE), line
    assert crew_autopilot.GOAL_STOP_CLAUSE == (
        "- or /crew:autopilot has stopped naming a command only the owner types")


def test_goal_line_renders_the_done_condition():
    line = crew_autopilot.goal_line({"proposal": {"done_condition": "  tests\n pass  "}})

    assert line == "/goal tests pass " + crew_autopilot.GOAL_STOP_CLAUSE


def test_goal_line_cut_at_the_cap_cuts_only_the_condition():
    line = crew_autopilot.goal_line({"proposal": {"done_condition": "y" * 1000}})

    condition = line[len("/goal "):-len(" " + crew_autopilot.GOAL_STOP_CLAUSE)]
    assert (len(line), condition, condition.count("y")) == (
        crew_autopilot.GOAL_LINE_MAX, "y" * len(condition),
        crew_autopilot.GOAL_LINE_MAX - len("/goal  ") - len(crew_autopilot.GOAL_STOP_CLAUSE))


@pytest.mark.parametrize("text", ["{", "[]", '{"schema": 2}', ""], ids=["corrupt", "list",
                                                                       "schema", "empty"])
def test_unreadable_goal_file_refused(tmp_path, text):
    root = make_repo(tmp_path, mode="off")
    _write(root / ".work" / "autopilot" / "g.json", text)

    with pytest.raises(crew_autopilot.GoalError):
        crew_autopilot.read_goal(str(root), "g")


@pytest.mark.parametrize("slug", ["../x", "a/b", "A", "", "-x", "a" * 65])
def test_read_goal_refuses_a_slug_outside_the_grammar(tmp_path, slug):
    root = make_repo(tmp_path, mode="off")

    with pytest.raises(crew_autopilot.GoalError, match="slug"):
        crew_autopilot.read_goal(str(root), slug)


# --- step 2: split approval -- the owner's receipt, or the same policy ---------

def _policy(tmp_path, risks=("low", "low"), **conf):
    root = _repo(tmp_path, **conf)
    slug = _goal(root, tickets=_tickets(*risks))["slug"]
    return root, slug, crew_autopilot.split_policy(str(root), slug)


def test_split_policy_self_allows(tmp_path):
    _root, _slug, got = _policy(tmp_path, risks=("low", "high"), approval="self")

    assert (got["allow"], got["policy"], got["risk"], got["known"]) == (
        True, "self", "high", True)


def test_split_policy_risk_all_low_allows(tmp_path):
    _root, _slug, got = _policy(tmp_path, risks=("low", "low", "low"), approval="risk")

    assert (got["allow"], got["policy"], got["risk"]) == (True, "risk", "low")


@pytest.mark.parametrize("risks", [("low", "med"), ("high", "low"), ("low", "low", "lo")],
                         ids=["second-med", "first-high", "third-unknown"])
def test_split_policy_risk_refuses_one_non_low_ticket(tmp_path, risks):
    _root, _slug, got = _policy(tmp_path, risks=risks, approval="risk")

    assert (got["allow"], "risk" in got["reason"]) == (False, True)


@pytest.mark.parametrize("allow", [False, "true", 1, None, MISSING],
                         ids=["false", "string", "one", "null", "absent"])
@pytest.mark.parametrize("approval", ["self", "risk"])
def test_split_policy_refuses_without_allow_cli_approval(tmp_path, allow, approval):
    _root, _slug, got = _policy(tmp_path, approval=approval, allow=allow)

    assert (got["allow"], "allowCliApproval" in got["reason"]) == (False, True)


@pytest.mark.parametrize("armed", [False, "Plan", "backlog", "on"])
def test_split_policy_refuses_when_unarmed(tmp_path, armed):
    _root, _slug, got = _policy(tmp_path, approval="self", armed=armed)

    assert (got["allow"], "not armed" in got["reason"]) == (False, True)


@pytest.mark.parametrize("approval", ["human", "Self", "typo", 3, None])
def test_split_policy_human_refuses(tmp_path, approval):
    _root, _slug, got = _policy(tmp_path, approval=approval)

    assert (got["allow"], got["policy"]) == (False, "human")


@pytest.mark.parametrize("how", ["corrupt", "missing", "bad-slug"])
def test_split_policy_unreadable_goal_refuses(tmp_path, how):
    root, slug, _got = _policy(tmp_path, approval="self")
    path = root / ".work" / "autopilot" / f"{slug}.json"
    if how == "corrupt":
        _write(path, "{")
    elif how == "missing":
        os.remove(str(path))
    else:
        slug = "../" + slug

    got = crew_autopilot.split_policy(str(root), slug)

    assert (got["allow"], "could not tell" in got["reason"]) == (False, True)


def test_split_policy_that_raises_refuses(tmp_path, monkeypatch):
    root, slug, _got = _policy(tmp_path, approval="self")

    def boom(*_a, **_k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(crew_autopilot, "settings", boom)

    got = crew_autopilot.split_policy(str(root), slug)

    assert (got["allow"], got["policy"], "could not tell" in got["reason"]) == (
        False, "unknown", True)


def test_split_policy_unreadable_config_refuses(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="self")
    _write(root / ".crew" / "config.json", "{")

    got = crew_autopilot.split_policy(str(root), slug)

    assert (got["allow"], got["policy"]) == (False, "unknown")


def test_split_approved_under_self_records_the_policy_in_the_goal_file(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="self")
    digest = crew_autopilot.goal_digest(crew_autopilot.read_goal(str(root), slug))

    got = crew_autopilot.split_approved(str(root), slug)

    stored = crew_autopilot.read_goal(str(root), slug)["approval"]
    assert (got["approved"], got["via"], stored["via"], stored["proposal_sha256"]) == (
        True, "autopilot:self", "autopilot:self", digest)


def test_recorded_autopilot_split_is_re_asked(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="self")
    first = crew_autopilot.split_approved(str(root), slug)
    _write(root / ".crew" / "config.json", json.dumps({
        "scope": {"mode": "off", "allowCliApproval": True},
        "autopilot": {"mode": "plan", "approval": "human"}}))

    again = crew_autopilot.split_approved(str(root), slug)

    assert (first["approved"], crew_autopilot.read_goal(str(root), slug)["approval"]["via"],
            again["approved"], again["owner"]) == (
        True, "autopilot:self", False, f"/crew:approve goal:{slug}")


def test_split_approved_by_the_owners_receipt_at_any_setting(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="human", allow=False, armed=False)
    _receipt(root, slug, crew_autopilot.goal_digest(crew_autopilot.read_goal(str(root), slug)))

    got = crew_autopilot.split_approved(str(root), slug)

    assert (got["approved"], got["via"]) == (True, "user-prompt")


@pytest.mark.parametrize("edit", ["done_condition", "ticket-title", "ticket-risk",
                                  "ticket-deps", "goal", "findings"])
@pytest.mark.parametrize("approval", ["self", "human"])
def test_split_approval_void_after_proposal_edit(tmp_path, edit, approval):
    root, slug, _got = _policy(tmp_path, risks=("low", "low"), approval=approval)
    goal = crew_autopilot.read_goal(str(root), slug)
    _receipt(root, slug, crew_autopilot.goal_digest(goal))
    crew_autopilot.split_approved(str(root), slug)
    if edit == "done_condition":
        goal["proposal"]["done_condition"] += " and more"
    elif edit == "findings":
        goal["proposal"]["findings"].append("one more")
    elif edit == "goal":
        goal["goal"] += "!"
    elif edit == "ticket-title":
        goal["tickets"][0]["title"] += " too"
    elif edit == "ticket-risk":
        goal["tickets"][1]["risk"] = "high"
    else:
        goal["tickets"][1]["depends_on"] = []
    goal = dict(crew_autopilot.read_goal(str(root), slug), goal=goal["goal"],
                proposal=goal["proposal"], tickets=goal["tickets"])
    _write(root / ".work" / "autopilot" / f"{slug}.json", json.dumps(goal))
    _write(root / ".crew" / "config.json", json.dumps({
        "scope": {"mode": "off", "allowCliApproval": True},
        "autopilot": {"mode": "plan", "approval": "human"}}))

    got = crew_autopilot.split_approved(str(root), slug)

    assert (got["approved"], "does not match" in got["reason"]) == (False, True)


def test_minting_fills_ids_without_voiding_the_receipt(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="human")
    goal = crew_autopilot.read_goal(str(root), slug)
    _receipt(root, slug, crew_autopilot.goal_digest(goal))
    for n, ticket in enumerate(goal["tickets"]):
        ticket["id"] = f"T-{n + 1:04d}"
    _write(root / ".work" / "autopilot" / f"{slug}.json", json.dumps(goal))

    assert crew_autopilot.split_approved(str(root), slug)["approved"] is True


@pytest.mark.parametrize("receipt", ["autopilot", "corrupt", "list", "other-slug"])
def test_a_receipt_not_the_owners_grants_nothing(tmp_path, receipt):
    root, slug, _got = _policy(tmp_path, approval="human")
    digest = crew_autopilot.goal_digest(crew_autopilot.read_goal(str(root), slug))
    if receipt == "autopilot":
        _receipt(root, slug, digest, via="autopilot")
    elif receipt in ("corrupt", "list"):
        _write(crew_autopilot.goal_receipt_path(str(root), slug),
               "{" if receipt == "corrupt" else "[]")
    else:
        _receipt(root, "other", digest)

    got = crew_autopilot.split_approved(str(root), slug)

    assert (got["approved"], got["via"]) == (False, "")


def test_an_unreadable_receipt_is_named_not_read_as_absent(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="human")
    _write(crew_autopilot.goal_receipt_path(str(root), slug), "{")

    got = crew_autopilot.split_approved(str(root), slug)

    assert (got["approved"], "could not be read" in got["reason"]) == (False, True)


def test_split_refusal_names_the_owner_line_for_this_goal_only(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="human")

    got = crew_autopilot.split_approved(str(root), slug)

    assert (got["approved"], got["owner"]) == (False, f"/crew:approve goal:{slug}")


def test_split_approval_writes_only_the_goal_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "0")
    root, slug, _got = _policy(tmp_path, approval="self")
    before = _files(root)

    code = _main(root, "goal-approve", "--goal", slug)

    after = _files(root)
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    assert (code, changed) == (0, [str(root / ".work" / "autopilot" / f"{slug}.json")])


def test_split_refused_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "0")
    root, slug, _got = _policy(tmp_path, approval="human")
    before = _files(root)

    code = _main(root, "goal-approve", "--goal", slug)

    assert (code, _files(root) == before) == (2, True)


# --- step 4: the subcommand, the printed line, the typer offer ------------------

def test_goal_subcommand_routes(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route(str(root), "goal")

    assert (got["sub"], got["stop"], "goal" in crew_autopilot.AVAILABLE,
            "goal" in crew_autopilot.ARRIVES) == ("goal", False, True, False)


@pytest.mark.parametrize("text", ["goal", "goal ship it", 'goal "ship it"', "goal T-1"])
def test_route_args_goal_with_text_refuses(tmp_path, text):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route_args(str(root), text)

    assert (got["sub"], got["stop"], got["ticket"], "route --root . --first goal" in
            got["reason"]) == ("goal", True, "", True)


@pytest.mark.parametrize("how", ["first", "args", "run-args"])
def test_goal_flag_resume_still_stops_naming_l0541(tmp_path, how):
    root = make_repo(tmp_path, mode="off")

    if how == "first":
        got = crew_autopilot.route(str(root), "--goal")
    else:
        got = crew_autopilot.route_args(str(root), "--goal x" if how == "args" else "run --goal x")

    assert (got["sub"], got["stop"], "arrives with L-0541" in got["reason"]) == (
        "run", True, True)


def test_propose_cli_prints_the_line_and_says_printed(tmp_path):
    root = _repo(tmp_path)
    _stage(root)

    out = _cli(root, "goal-propose", "--proposal-file", ".work/autopilot/g.proposal.json")

    lines = out.stdout.splitlines()
    slug = re.search(r"slug=(\S+)", lines[0]).group(1)
    assert (out.returncode, "goal_status=printed" in lines[0],
            [line for line in lines if line.startswith("goal_line: ")] == [
                "goal_line: " + crew_autopilot.goal_line(
                    crew_autopilot.read_goal(str(root), slug))],
            crew_autopilot.GOAL_UNSEEN in lines, out.stderr) == (0, True, True, True, "")


def test_goal_status_is_printed_never_set(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, approval="self")
    _stage(root)
    outs = []
    for argv in (["goal-propose", "--proposal-file", ".work/autopilot/g.proposal.json"],
                 ["goal-propose", "--proposal-file", ".work/autopilot/g.proposal.json",
                  "--json"]):
        _main(root, *argv)
        outs.append(capsys.readouterr().out)
    slug = re.search(r"slug=(\S+)", outs[0]).group(1)
    for argv in (["goal-approve", "--goal", slug], ["goal-approve", "--goal", slug, "--json"]):
        _main(root, *argv)
        outs.append(capsys.readouterr().out)

    flat = "\n".join(outs).lower()
    assert ([w for w in SET_WORDS if w in flat], flat.count("goal_status=printed"),
            json.loads(outs[1])["goal_status"], "goal_status=set" in flat) == (
        [], 1, "printed", False)


def test_typer_offer_absent_without_t0013_entry(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(crew_autopilot, "_resume_armed", lambda _top: (True, ""))
    monkeypatch.setattr(crew_autopilot, "_typing_sender", lambda _top: (True, ""))

    got = crew_autopilot.typer_offer(str(root))

    assert (got["offer"], got["missing"]) == (False, [crew_autopilot.TYPER_ABSENT])


def test_typer_offer_absent_when_not_armed(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(crew_autopilot, "_typing_sender", lambda _top: (True, ""))
    monkeypatch.setattr(crew_autopilot, "_goal_typer", lambda: lambda _line: None)

    got = crew_autopilot.typer_offer(str(root))

    assert (got["offer"], len(got["missing"]), "resume.auto" in got["missing"][0]) == (
        False, 1, True)


def test_typer_offer_absent_without_a_sender(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(crew_autopilot, "_resume_armed", lambda _top: (True, ""))
    monkeypatch.setattr(crew_autopilot, "_typing_sender",
                        lambda _top: (False, "no usable method"))
    monkeypatch.setattr(crew_autopilot, "_goal_typer", lambda: lambda _line: None)

    got = crew_autopilot.typer_offer(str(root))

    assert (got["offer"], got["missing"]) == (False, ["no typing sender: no usable method"])


def test_typer_offer_only_with_all_three(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(crew_autopilot, "_resume_armed", lambda _top: (True, ""))
    monkeypatch.setattr(crew_autopilot, "_typing_sender", lambda _top: (True, ""))
    monkeypatch.setattr(crew_autopilot, "_goal_typer", lambda: lambda _line: None)

    got = crew_autopilot.typer_offer(str(root))

    assert (got["offer"], got["missing"]) == (True, [])


def test_typer_probe_that_raises_is_named_not_offered(tmp_path, monkeypatch):
    root = _repo(tmp_path)

    def boom(_top):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(crew_autopilot, "_resume_armed", boom)

    got = crew_autopilot.typer_offer(str(root))

    assert (got["offer"], any("could not tell" in m for m in got["missing"])) == (False, True)


def test_typer_reason_printed_once(tmp_path, capsys):
    root = _repo(tmp_path)
    _stage(root)

    _main(root, "goal-propose", "--proposal-file", ".work/autopilot/g.proposal.json")

    out = capsys.readouterr().out
    assert (out.count("typer: "), out.count(crew_autopilot.TYPER_ABSENT)) == (1, 1)


@pytest.mark.parametrize("where", ["outside", "symlink-out", "fifo", "missing"])
def test_propose_refuses_a_file_not_staged_under_work_autopilot(tmp_path, where):
    root = _repo(tmp_path)
    staged = _stage(root)
    target = staged
    if where == "outside":
        target = root / "p.json"
        _write(target, staged.read_text(encoding="utf-8"))
    elif where == "symlink-out":
        outside = tmp_path / "p.json"
        _write(outside, staged.read_text(encoding="utf-8"))
        target = root / ".work" / "autopilot" / "link.json"
        try:
            os.symlink(str(outside), str(target))
        except (OSError, NotImplementedError):
            pytest.skip("no symlinks here")
    elif where == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("no FIFOs here")
        target = root / ".work" / "autopilot" / "pipe.json"
        os.mkfifo(str(target))
    else:
        target = root / ".work" / "autopilot" / "nope.json"

    out = _cli(root, "goal-propose", "--proposal-file", str(target))

    goals = [n for n in os.listdir(str(root / ".work" / "autopilot"))
             if n.endswith(".json") and not n.endswith(".proposal.json")
             and n not in ("link.json", "pipe.json")]
    assert (out.returncode, out.stdout.startswith("refused: "), goals) == (2, True, [])


@pytest.mark.parametrize("over", [{"goal": ""}, {"goal": None}, {"findings": 3},
                                  {"findings": [1]}, {"tickets": []}],
                         ids=["empty-goal", "no-goal", "findings-int", "findings-item",
                              "no-tickets"])
def test_propose_refuses_a_malformed_proposal(tmp_path, over):
    root = _repo(tmp_path)
    _stage(root, **over)

    out = _cli(root, "goal-propose", "--proposal-file", ".work/autopilot/g.proposal.json")

    assert (out.returncode, out.stdout.startswith("refused: ")) == (2, True)


def test_propose_writes_only_the_goal_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "0")
    root = _repo(tmp_path)
    _stage(root)
    before = _files(root)

    code = _main(root, "goal-propose", "--proposal-file", ".work/autopilot/g.proposal.json")

    after = _files(root)
    added = sorted(set(after) - set(before))
    assert (code, [os.path.basename(p) for p in added],
            {p: v for p, v in after.items() if p in before} == before) == (
        0, ["ship-the-csv-export-quoted-and-literal.json"], True)


def test_propose_crash_is_a_refusal_not_silence(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _stage(root)

    def boom(*_a, **_k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(crew_autopilot, "goal_propose", boom)

    code = _main(root, "goal-propose", "--proposal-file", ".work/autopilot/g.proposal.json")

    out = capsys.readouterr().out
    assert (code, out.startswith("refused: "), "disk on fire" in out) == (1, True, True)


def test_goal_approve_cli_lines(tmp_path):
    root = _repo(tmp_path, approval="human")
    slug = _goal(root)["slug"]

    out = _cli(root, "goal-approve", "--goal", slug)

    lines = out.stdout.splitlines()
    assert (out.returncode, lines[0].startswith("refused: "),
            lines[-1] == f"owner: the human types /crew:approve goal:{slug}") == (2, True, True)


def test_goal_approve_cli_says_minting_is_l0541s(tmp_path):
    root = _repo(tmp_path, approval="self")
    slug = _goal(root)["slug"]

    out = _cli(root, "goal-approve", "--goal", slug)

    assert (out.returncode, out.stdout.startswith(f"split-approved {slug} via=autopilot:self"),
            "L-0541" in out.stdout, "crew_ticket.py mint" in out.stdout) == (0, True, True, True)


@pytest.mark.parametrize("slug", ["../x", "Goal", "a b"])
def test_goal_approve_cli_refuses_a_bad_slug(tmp_path, slug):
    root = _repo(tmp_path, approval="self")

    out = _cli(root, "goal-approve", "--goal", slug)

    assert (out.returncode, out.stdout.startswith("refused: ")) == (2, True)


def _all_goal_output(tmp_path, approval):
    root = _repo(tmp_path, approval=approval)
    _stage(root)
    outs = [_cli(root, "goal-propose", "--proposal-file", ".work/autopilot/g.proposal.json")]
    slug = re.search(r"slug=(\S+)", outs[0].stdout).group(1)
    outs.append(_cli(root, "goal-approve", "--goal", slug))
    return slug, "\n".join(o.stdout + o.stderr for o in outs)


@pytest.mark.parametrize("approval", ["human", "self", "risk"])
def test_goal_output_never_prints_a_group_approve(tmp_path, approval):
    slug, text = _all_goal_output(tmp_path, approval)

    approves = [line[line.index("/crew:approve"):] for line in text.splitlines()
                if "/crew:approve" in line]
    assert ([a for a in approves if a != f"/crew:approve goal:{slug}"],
            "--confirm" in text, ".." in " ".join(approves)) == ([], False, False)


# --- step 4: the command -------------------------------------------------------

def _command_text():
    with open(_COMMAND, encoding="utf-8") as handle:
        return handle.read()


def _goal_section():
    text = _command_text()
    start = text.index("## 6. goal")
    end = text.find("\n## ", start + 1)
    return text[start:end if end >= 0 else len(text)]


def test_goal_section_at_most_6_lines():
    body = [line for line in _goal_section().splitlines()[1:] if line.strip()]

    assert (1 <= len(body) <= 6, len(body)) == (True, len(body))


def test_goal_section_never_puts_arguments_on_a_shell_line():
    text = _command_text()
    route = text[text.index("## 0. Route"):text.index("## 1. status")]
    goal_rule = next(line for line in route.splitlines() if "`goal`" in line)
    section = _goal_section()

    assert ("route --root . --first goal" in goal_rule, "$ARGUMENTS" in goal_rule,
            "never `--args`" in goal_rule, "$ARGUMENTS" in section, "$1" in section,
            route.index(goal_rule) < route.index("If the arguments hold a quote")) == (
        True, False, True, False, False, True)


def test_goal_section_runs_propose_then_approve_and_mints_nothing():
    section = " ".join(_goal_section().split())

    assert ("crew_autopilot.py goal-propose --root . --proposal-file" in section,
            "crew_autopilot.py goal-approve --root . --goal <slug>" in section,
            section.index("goal-propose") < section.index("goal-approve"),
            "crew_ticket.py mint" in section, "L-0541" in section,
            "goal_status=printed" in section) == (True, True, True, False, True, True)


def test_goal_section_never_claims_the_goal_is_set():
    section = _goal_section().lower()

    assert [w for w in SET_WORDS if w in section] == []
