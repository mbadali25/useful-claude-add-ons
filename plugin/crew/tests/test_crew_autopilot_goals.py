"""T-0012: `/crew:autopilot goal` -- the goal file, the proposal, the printed
`/goal` line and the split approval.

    python3 -m pytest plugin/crew/tests/test_crew_autopilot_goals.py -q

`goal-propose` turns a proposal staged under `.work/autopilot/` into the goal
file `.work/autopilot/<slug>.json` (schema 1) and prints the `/goal <condition>`
line for the owner to paste: autopilot never runs `/goal`, and reports its
state as `printed`, never `set`. `goal-approve` answers the split approval: the
owner's `/crew:approve goal:<slug>` receipt bound to the proposal's hash, or
`autopilot.approval` re-asked on every read. L-0541 (the last section): an
approved split is minted, the goal's tickets are picked in dependency order,
each through its own approval, inside the run's caps, and `--goal <slug>`
resumes. The hook that records the owner's receipt is a separate harness
change, so here the receipt is only read. Every repository is built under
tmp_path; nothing touches the real one or ~/.claude.
"""
import json
import os
import re
import subprocess
import sys

import context  # pylint: disable=unused-import
import crew_autopilot
import crew_autopilot_backlog
import crew_autopilot_goal
import crew_resume
import crew_ticket
import pytest
from scope_fixtures import PLAN, SPEC, make_repo

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


def _read(path):
    with open(str(path), encoding="utf-8") as handle:
        return handle.read()


def _repo(tmp_path, approval="risk", allow=True, armed=True, tracker=None, **caps):
    root = make_repo(tmp_path, mode="off")
    scope = {"mode": "off"}
    if allow is not MISSING:
        scope["allowCliApproval"] = allow
    block = {"mode": "plan" if armed is True else (armed or "off"), **caps}
    if approval is not MISSING:
        block["approval"] = approval
    config = {"scope": scope, "autopilot": block}
    if tracker:
        config["tracker"] = tracker  # L-0541: mint writes only under a files tracker
    _write(root / ".crew" / "config.json", json.dumps(config))
    return root


def _tickets(*risks):
    return [{"title": f"ticket {n}", "risk": risk, "depends_on": [n - 1] if n else []}
            for n, risk in enumerate(risks)]


def _goal(root, tickets=None, proposal=None, goal=GOAL):
    return crew_autopilot_goal.write_goal(str(root), goal, dict(proposal or PROPOSAL),
                                     [dict(t) for t in (tickets or TICKETS)])


def _stage(root, name="g.proposal.json", **over):
    data = {"goal": GOAL, "done_condition": PROPOSAL["done_condition"],
            "findings": PROPOSAL["findings"], "tickets": TICKETS}
    data.update(over)
    path = root / ".work" / "autopilot" / name
    _write(path, json.dumps(data))
    return path


def _receipt(root, slug, digest, via="user-prompt"):
    path = crew_autopilot_goal.goal_receipt_path(str(root), slug)
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

    slug = crew_autopilot_goal.slugify(str(root), goal)

    assert (bool(crew_resume._GOAL_SLUG_RE.match(slug)),  # pylint: disable=protected-access
            len(slug) <= crew_autopilot_goal.GOAL_SLUG_MAX + 3) == (True, True)


def test_slug_shape(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = [crew_autopilot_goal.slugify(str(root), text) for text in (GOAL, "", "!!", "A" * 99)]

    assert got == ["ship-the-csv-export-quoted-and-literal", "goal", "goal", "a" * 40]


def test_slug_collision_suffix(tmp_path):
    root = make_repo(tmp_path, mode="off")

    slugs = [_goal(root, goal="same words")["slug"] for _ in range(3)]

    assert slugs == ["same-words", "same-words-2", "same-words-3"]


def test_goal_round_trip(tmp_path):
    root = make_repo(tmp_path, mode="off")

    made = _goal(root)
    got = crew_autopilot_goal.read_goal(str(root), made["slug"])

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

    with pytest.raises(crew_autopilot_goal.GoalError, match="cycle"):
        _goal(root, tickets=tickets)

    assert not os.path.isdir(str(root / ".work" / "autopilot"))


@pytest.mark.parametrize("deps", [[3], [-1], ["0"], [True], [0.0], "0", None, [0, 0]],
                         ids=["past-end", "negative", "string", "bool", "float", "not-list",
                              "none", "twice"])
def test_unknown_dependency_refused(tmp_path, deps):
    root = make_repo(tmp_path, mode="off")
    tickets = [{"title": "t0", "risk": "low", "depends_on": []},
               {"title": "t1", "risk": "low", "depends_on": deps}]

    with pytest.raises(crew_autopilot_goal.GoalError, match="depends_on"):
        _goal(root, tickets=tickets)


def test_dependency_order_is_the_list_order(tmp_path):
    root = make_repo(tmp_path, mode="off")
    tickets = [{"title": "t0", "risk": "low", "depends_on": [1]},
               {"title": "t1", "risk": "low", "depends_on": []}]

    with pytest.raises(crew_autopilot_goal.GoalError, match="dependency order"):
        _goal(root, tickets=tickets)


@pytest.mark.parametrize("bad", [{"title": "a|b"}, {"title": "a\nb"}, {"title": ""},
                                 {"title": None}, {"risk": None}, {"risk": 3}],
                         ids=["bar", "newline", "empty", "none", "risk-none", "risk-int"])
def test_ticket_mint_would_refuse_is_refused_now(tmp_path, bad):
    root = make_repo(tmp_path, mode="off")
    ticket = dict({"title": "ok", "risk": "low", "depends_on": []}, **bad)

    with pytest.raises(crew_autopilot_goal.GoalError):
        _goal(root, tickets=[ticket])


@pytest.mark.parametrize("tickets", [[], "x", None, [None]], ids=["empty", "str", "none", "item"])
def test_no_usable_tickets_refused(tmp_path, tickets):
    root = make_repo(tmp_path, mode="off")

    with pytest.raises(crew_autopilot_goal.GoalError):
        crew_autopilot_goal.write_goal(str(root), GOAL, dict(PROPOSAL), tickets)


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
    assert crew_autopilot_goal.goal_risk(_tickets(*risks)) == want


@pytest.mark.parametrize("cond", [MISSING, None, "", "   ", "\n\t", "///", 7],
                         ids=["missing", "none", "empty", "blank", "control", "slashes", "int"])
def test_proposal_without_done_condition_refused(tmp_path, cond):
    root = make_repo(tmp_path, mode="off")
    proposal = dict(PROPOSAL)
    if cond is MISSING:
        del proposal["done_condition"]
    else:
        proposal["done_condition"] = cond

    with pytest.raises(crew_autopilot_goal.GoalError, match="done_condition"):
        _goal(root, proposal=proposal)

    assert not os.path.isdir(str(root / ".work" / "autopilot"))


@pytest.mark.parametrize("cond", ["ships\nand /goal clear\r\nnow", "x" * 1000,
                                  "a\x00b\x1b[31mc d\x85e", "/goal clear", "  // spaced"])
def test_goal_line_single_line_and_capped(cond):
    line = crew_autopilot_goal.goal_line({"proposal": {"done_condition": cond}})
    condition = line[len("/goal "):]

    assert (line.startswith("/goal "), len(line) <= crew_autopilot_goal.GOAL_LINE_MAX,
            len(line.splitlines()), line.isprintable(), condition[:1] not in ("/", " ")) == (
        True, True, 1, True, True)


def test_goal_line_keeps_human_stop_clause():
    for cond in ("short", "x" * 1000):
        line = crew_autopilot_goal.goal_line({"proposal": {"done_condition": cond}})
        assert line.endswith(" " + crew_autopilot_goal.GOAL_STOP_CLAUSE), line
    assert crew_autopilot_goal.GOAL_STOP_CLAUSE == (
        "- or /crew:autopilot has stopped naming a command only the owner types")


def test_goal_line_renders_the_done_condition():
    line = crew_autopilot_goal.goal_line({"proposal": {"done_condition": "  tests\n pass  "}})

    assert line == "/goal tests pass " + crew_autopilot_goal.GOAL_STOP_CLAUSE


def test_goal_line_cut_at_the_cap_cuts_only_the_condition():
    line = crew_autopilot_goal.goal_line({"proposal": {"done_condition": "y" * 1000}})

    condition = line[len("/goal "):-len(" " + crew_autopilot_goal.GOAL_STOP_CLAUSE)]
    assert (len(line), condition, condition.count("y")) == (
        crew_autopilot_goal.GOAL_LINE_MAX, "y" * len(condition),
        crew_autopilot_goal.GOAL_LINE_MAX - len("/goal  ") - len(crew_autopilot_goal.GOAL_STOP_CLAUSE))


@pytest.mark.parametrize("text", ["{", "[]", '{"schema": 2}', ""], ids=["corrupt", "list",
                                                                       "schema", "empty"])
def test_unreadable_goal_file_refused(tmp_path, text):
    root = make_repo(tmp_path, mode="off")
    _write(root / ".work" / "autopilot" / "g.json", text)

    with pytest.raises(crew_autopilot_goal.GoalError):
        crew_autopilot_goal.read_goal(str(root), "g")


@pytest.mark.parametrize("slug", ["../x", "a/b", "A", "", "-x", "a" * 65])
def test_read_goal_refuses_a_slug_outside_the_grammar(tmp_path, slug):
    root = make_repo(tmp_path, mode="off")

    with pytest.raises(crew_autopilot_goal.GoalError, match="slug"):
        crew_autopilot_goal.read_goal(str(root), slug)


# --- step 2: split approval -- the owner's receipt, or the same policy ---------

def _policy(tmp_path, risks=("low", "low"), **conf):
    root = _repo(tmp_path, **conf)
    slug = _goal(root, tickets=_tickets(*risks))["slug"]
    return root, slug, crew_autopilot_goal.split_policy(str(root), slug)


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


@pytest.mark.parametrize("armed", [False, "Plan", "Backlog", "on"])
def test_split_policy_refuses_when_unarmed(tmp_path, armed):
    _root, _slug, got = _policy(tmp_path, approval="self", armed=armed)

    assert (got["allow"], "not armed" in got["reason"]) == (False, True)


@pytest.mark.parametrize("approval", ["human", "Self", "typo", 3])
def test_split_policy_human_refuses(tmp_path, approval):
    _root, _slug, got = _policy(tmp_path, approval=approval)

    assert (got["allow"], got["policy"]) == (False, "human")


def test_split_policy_null_reads_the_default_like_approval_policy(tmp_path):
    """`approval: null` is unset since T-0050 (test_approval_null_is_silent_and_reads_the_default):
    the split reads the same default `risk` as the plan approval, never a stricter or looser one."""
    _root, _slug, got = _policy(tmp_path, approval=None)

    assert (got["allow"], got["policy"]) == (True, "risk")


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

    got = crew_autopilot_goal.split_policy(str(root), slug)

    assert (got["allow"], "could not tell" in got["reason"]) == (False, True)


def test_split_policy_that_raises_refuses(tmp_path, monkeypatch):
    root, slug, _got = _policy(tmp_path, approval="self")

    def boom(*_a, **_k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(crew_autopilot, "settings", boom)

    got = crew_autopilot_goal.split_policy(str(root), slug)

    assert (got["allow"], got["policy"], "could not tell" in got["reason"]) == (
        False, "unknown", True)


def test_split_policy_unreadable_config_refuses(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="self")
    _write(root / ".crew" / "config.json", "{")

    got = crew_autopilot_goal.split_policy(str(root), slug)

    assert (got["allow"], got["policy"]) == (False, "unknown")


def test_split_approved_under_self_records_the_policy_in_the_goal_file(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="self")
    digest = crew_autopilot_goal.goal_digest(crew_autopilot_goal.read_goal(str(root), slug))

    got = crew_autopilot_goal.split_approved(str(root), slug)

    stored = crew_autopilot_goal.read_goal(str(root), slug)["approval"]
    assert (got["approved"], got["via"], stored["via"], stored["proposal_sha256"]) == (
        True, "autopilot:self", "autopilot:self", digest)


def test_recorded_autopilot_split_is_re_asked(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="self")
    first = crew_autopilot_goal.split_approved(str(root), slug)
    _write(root / ".crew" / "config.json", json.dumps({
        "scope": {"mode": "off", "allowCliApproval": True},
        "autopilot": {"mode": "plan", "approval": "human"}}))

    again = crew_autopilot_goal.split_approved(str(root), slug)

    assert (first["approved"], crew_autopilot_goal.read_goal(str(root), slug)["approval"]["via"],
            again["approved"], again["owner"]) == (
        True, "autopilot:self", False, f"/crew:approve goal:{slug}")


def test_split_approved_by_the_owners_receipt_at_any_setting(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="human", allow=False, armed=False)
    _receipt(root, slug, crew_autopilot_goal.goal_digest(crew_autopilot_goal.read_goal(str(root), slug)))

    got = crew_autopilot_goal.split_approved(str(root), slug)

    assert (got["approved"], got["via"]) == (True, "user-prompt")


def test_the_owners_receipt_reports_the_goals_own_risk(tmp_path):
    """Port review FIX: the receipt branch read `high` for every goal."""
    root, slug, _got = _policy(tmp_path, risks=("low", "low"), approval="human")
    _receipt(root, slug,
             crew_autopilot_goal.goal_digest(crew_autopilot_goal.read_goal(str(root), slug)))

    got = crew_autopilot_goal.split_approved(str(root), slug)

    assert (got["approved"], got["risk"],
            crew_autopilot_goal.split_approved_text(slug, got).splitlines()[0]) == (
        True, "low", f"split-approved {slug} via=user-prompt risk=low")


def test_the_policy_judges_the_proposal_it_approves(tmp_path, monkeypatch):
    """Port review BLOCK: a proposal edited between the read and the policy is
    neither approved under the policy nor overwritten by the approval note."""
    root, slug, _got = _policy(tmp_path, risks=("high", "low"), approval="risk")
    path = crew_autopilot_goal.goal_path(str(root), slug)
    real = crew_autopilot_goal.read_goal
    calls = []

    def edits_after_first_read(top, name):
        got = real(top, name)
        if not calls:
            data = json.loads(_read(path))
            data["tickets"][0]["risk"] = "low"
            _write(path, json.dumps(data))
        calls.append(name)
        return got

    monkeypatch.setattr(crew_autopilot_goal, "read_goal", edits_after_first_read)
    got = crew_autopilot_goal.split_approved(str(root), slug)
    stored = real(str(root), slug)

    assert (got["approved"], got["risk"], stored["approval"], stored["tickets"][0]["risk"]) == (
        False, "high", None, "low")


def test_an_edit_before_the_note_is_never_overwritten(tmp_path, monkeypatch):
    """The policy allowed the proposal it read; the file changed before the
    note was written: no approval, and the edit stays."""
    root, slug, _got = _policy(tmp_path, risks=("low", "low"), approval="self")
    path = crew_autopilot_goal.goal_path(str(root), slug)
    real = crew_autopilot_goal.split_policy

    def policy_then_edit(top, name, goal=None):
        got = real(top, name, goal)
        data = json.loads(_read(path))
        data["proposal"]["done_condition"] += " and more"
        _write(path, json.dumps(data))
        return got

    monkeypatch.setattr(crew_autopilot_goal, "split_policy", policy_then_edit)
    got = crew_autopilot_goal.split_approved(str(root), slug)
    stored = crew_autopilot_goal.read_goal(str(root), slug)

    assert (got["approved"], "changed" in got["reason"], stored["approval"],
            stored["proposal"]["done_condition"].endswith(" and more")) == (False, True, None, True)


@pytest.mark.parametrize("edit", ["done_condition", "ticket-title", "ticket-risk",
                                  "ticket-deps", "goal", "findings"])
@pytest.mark.parametrize("approval", ["self", "human"])
def test_split_approval_void_after_proposal_edit(tmp_path, edit, approval):
    root, slug, _got = _policy(tmp_path, risks=("low", "low"), approval=approval)
    goal = crew_autopilot_goal.read_goal(str(root), slug)
    _receipt(root, slug, crew_autopilot_goal.goal_digest(goal))
    crew_autopilot_goal.split_approved(str(root), slug)
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
    goal = dict(crew_autopilot_goal.read_goal(str(root), slug), goal=goal["goal"],
                proposal=goal["proposal"], tickets=goal["tickets"])
    _write(root / ".work" / "autopilot" / f"{slug}.json", json.dumps(goal))
    _write(root / ".crew" / "config.json", json.dumps({
        "scope": {"mode": "off", "allowCliApproval": True},
        "autopilot": {"mode": "plan", "approval": "human"}}))

    got = crew_autopilot_goal.split_approved(str(root), slug)

    assert (got["approved"], "does not match" in got["reason"]) == (False, True)


def test_minting_fills_ids_without_voiding_the_receipt(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="human")
    goal = crew_autopilot_goal.read_goal(str(root), slug)
    _receipt(root, slug, crew_autopilot_goal.goal_digest(goal))
    for n, ticket in enumerate(goal["tickets"]):
        ticket["id"] = f"T-{n + 1:04d}"
    _write(root / ".work" / "autopilot" / f"{slug}.json", json.dumps(goal))

    assert crew_autopilot_goal.split_approved(str(root), slug)["approved"] is True


@pytest.mark.parametrize("receipt", ["autopilot", "corrupt", "list", "other-slug"])
def test_a_receipt_not_the_owners_grants_nothing(tmp_path, receipt):
    root, slug, _got = _policy(tmp_path, approval="human")
    digest = crew_autopilot_goal.goal_digest(crew_autopilot_goal.read_goal(str(root), slug))
    if receipt == "autopilot":
        _receipt(root, slug, digest, via="autopilot")
    elif receipt in ("corrupt", "list"):
        _write(crew_autopilot_goal.goal_receipt_path(str(root), slug),
               "{" if receipt == "corrupt" else "[]")
    else:
        _receipt(root, "other", digest)

    got = crew_autopilot_goal.split_approved(str(root), slug)

    assert (got["approved"], got["via"]) == (False, "")


def test_an_unreadable_receipt_is_named_not_read_as_absent(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="human")
    _write(crew_autopilot_goal.goal_receipt_path(str(root), slug), "{")

    got = crew_autopilot_goal.split_approved(str(root), slug)

    assert (got["approved"], "could not be read" in got["reason"]) == (False, True)


UNREADABLE = "the owner's split receipt is there but could not be read"
STALE = "does not match the current proposal"


def _bad_receipt(root, slug, how):
    """A receipt the owner's prompt did not grant for THIS proposal: `unreadable`
    (`{`), `stale` (another proposal's digest), `symlink-file` (approval.json a
    symlink to a matching receipt) or `symlink-dir` (goals/<slug> a symlink to a
    directory holding one). Returns the words the warning must carry."""
    path = crew_autopilot_goal.goal_receipt_path(str(root), slug)
    digest = crew_autopilot_goal.goal_digest(crew_autopilot_goal.read_goal(str(root), slug))
    if how == "unreadable":
        _write(path, "{")
        return UNREADABLE
    if how == "stale":
        _receipt(root, slug, "0" * 64)
        return STALE
    real = _receipt(root, "elsewhere", digest)
    if how == "symlink-file":
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.symlink(real, path)
    else:
        os.makedirs(os.path.dirname(os.path.dirname(path)), exist_ok=True)
        os.symlink(os.path.dirname(real), os.path.dirname(path))
    return "not a regular file"


@pytest.mark.parametrize("how", ["unreadable", "stale", "symlink-file", "symlink-dir"])
@pytest.mark.parametrize("approval", ["self", "risk"])
def test_a_bad_receipt_is_warned_when_the_policy_approves(tmp_path, approval, how):
    root, slug, _got = _policy(tmp_path, risks=("low", "low"), approval=approval)
    words = _bad_receipt(root, slug, how)

    got = crew_autopilot_goal.split_approved(str(root), slug)
    text = crew_autopilot_goal.split_approved_text(slug, got)

    assert (got["approved"], got["via"],
            crew_autopilot_goal.read_goal(str(root), slug)["approval"]["via"],
            any(words in w for w in got["warnings"]),
            any(line.startswith("warning: ") and words in line
                for line in text.splitlines())) == (
        True, f"autopilot:{approval}", f"autopilot:{approval}", True, True)


@pytest.mark.parametrize("how", ["symlink-file", "symlink-dir"])
def test_a_symlinked_receipt_grants_nothing_and_is_named(tmp_path, how):
    root, slug, _got = _policy(tmp_path, approval="human")
    words = _bad_receipt(root, slug, how)

    got = crew_autopilot_goal.split_approved(str(root), slug)

    assert (got["approved"], got["via"], words in got["reason"]) == (False, "", True)


def test_split_refusal_names_the_owner_line_for_this_goal_only(tmp_path):
    root, slug, _got = _policy(tmp_path, approval="human")

    got = crew_autopilot_goal.split_approved(str(root), slug)

    assert (got["approved"], got["owner"]) == (False, f"/crew:approve goal:{slug}")


def test_split_approval_writes_only_the_goal_file(tmp_path, monkeypatch):
    """Without a tracker `crew_ticket.mint` refuses before it claims anything,
    so the approval note is the one write (L-0541: the mint stop exits 2)."""
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "0")
    root, slug, _got = _policy(tmp_path, approval="self")
    before = _files(root)

    code = _main(root, "goal-approve", "--goal", slug)

    after = _files(root)
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    assert (code, changed) == (2, [str(root / ".work" / "autopilot" / f"{slug}.json")])


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


@pytest.mark.parametrize("how", ["args", "run-args"])
def test_goal_flag_routes_to_run_with_the_slug(tmp_path, how):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route_args(str(root), "--goal x" if how == "args" else "run --goal x")

    assert (got["sub"], got["stop"], got["goal"], got["ticket"]) == ("run", False, "x", "")


@pytest.mark.parametrize("text", ["--goal", "--goal Bad", "--goal a b", "run --goal",
                                  "run --goal ../x", "--goal T-1 x"])
def test_goal_flag_without_one_slug_stops(tmp_path, text):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route_args(str(root), text)

    assert (got["sub"], got["stop"], "goal slug" in got["reason"]) == ("run", True, True)


def test_goal_flag_alone_on_first_stops(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.route(str(root), "--goal")

    assert (got["sub"], got["stop"], "goal slug" in got["reason"]) == ("run", True, True)


def test_propose_cli_prints_the_line_and_says_printed(tmp_path):
    root = _repo(tmp_path)
    _stage(root)

    out = _cli(root, "goal-propose", "--proposal-file", ".work/autopilot/g.proposal.json")

    lines = out.stdout.splitlines()
    slug = re.search(r"slug=(\S+)", lines[0]).group(1)
    assert (out.returncode, "goal_status=printed" in lines[0],
            [line for line in lines if line.startswith("goal_line: ")] == [
                "goal_line: " + crew_autopilot_goal.goal_line(
                    crew_autopilot_goal.read_goal(str(root), slug))],
            crew_autopilot_goal.GOAL_UNSEEN in lines, out.stderr) == (0, True, True, True, "")


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
    monkeypatch.setattr(crew_autopilot_goal, "_resume_armed", lambda _top: (True, ""))
    monkeypatch.setattr(crew_autopilot_goal, "_typing_sender", lambda _top: (True, ""))

    got = crew_autopilot_goal.typer_offer(str(root))

    assert (got["offer"], got["missing"]) == (False, [crew_autopilot_goal.TYPER_ABSENT])


def test_typer_offer_absent_when_not_armed(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(crew_autopilot_goal, "_typing_sender", lambda _top: (True, ""))
    monkeypatch.setattr(crew_autopilot_goal, "_goal_typer", lambda: lambda _line: None)

    got = crew_autopilot_goal.typer_offer(str(root))

    assert (got["offer"], len(got["missing"]), "resume.auto" in got["missing"][0]) == (
        False, 1, True)


def test_typer_offer_absent_without_a_sender(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(crew_autopilot_goal, "_resume_armed", lambda _top: (True, ""))
    monkeypatch.setattr(crew_autopilot_goal, "_typing_sender",
                        lambda _top: (False, "no usable method"))
    monkeypatch.setattr(crew_autopilot_goal, "_goal_typer", lambda: lambda _line: None)

    got = crew_autopilot_goal.typer_offer(str(root))

    assert (got["offer"], got["missing"]) == (False, ["no typing sender: no usable method"])


def test_typer_offer_only_with_all_three(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(crew_autopilot_goal, "_resume_armed", lambda _top: (True, ""))
    monkeypatch.setattr(crew_autopilot_goal, "_typing_sender", lambda _top: (True, ""))
    monkeypatch.setattr(crew_autopilot_goal, "_goal_typer", lambda: lambda _line: None)

    got = crew_autopilot_goal.typer_offer(str(root))

    assert (got["offer"], got["missing"]) == (True, [])


def test_typer_probe_that_raises_is_named_not_offered(tmp_path, monkeypatch):
    root = _repo(tmp_path)

    def boom(_top):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(crew_autopilot_goal, "_resume_armed", boom)

    got = crew_autopilot_goal.typer_offer(str(root))

    assert (got["offer"], any("could not tell" in m for m in got["missing"])) == (False, True)


def test_typer_reason_printed_once(tmp_path, capsys):
    root = _repo(tmp_path)
    _stage(root)

    _main(root, "goal-propose", "--proposal-file", ".work/autopilot/g.proposal.json")

    out = capsys.readouterr().out
    assert (out.count("typer: "), out.count(crew_autopilot_goal.TYPER_ABSENT)) == (1, 1)


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
    monkeypatch.setattr(crew_autopilot_goal, "goal_propose", boom)

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


def test_goal_approve_cli_mints_after_the_approval(tmp_path):
    root = _repo(tmp_path, approval="self", tracker="files")
    slug = _goal(root)["slug"]

    out = _cli(root, "goal-approve", "--goal", slug)

    lines = out.stdout.splitlines()
    assert (out.returncode, lines[0].startswith(f"split-approved {slug} via=autopilot:self"),
            [line.split()[3] for line in lines[1:]]) == (0, True, ["T-0001", "T-0002", "T-0003"])


@pytest.mark.parametrize("slug", ["../x", "Goal", "a b"])
def test_goal_approve_cli_refuses_a_bad_slug(tmp_path, slug):
    root = _repo(tmp_path, approval="self")

    out = _cli(root, "goal-approve", "--goal", slug)

    assert (out.returncode, out.stdout.startswith("refused: ")) == (2, True)


def _all_goal_output(tmp_path, approval):
    root = _repo(tmp_path, approval=approval, tracker="files")
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
    start = text.index("## 7. goal")
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


def test_goal_section_runs_propose_then_approve_which_mints_then_the_goal_run():
    section = " ".join(_goal_section().split())

    assert ("crew_autopilot.py goal-propose --root . --proposal-file" in section,
            "crew_autopilot.py goal-approve --root . --goal <slug>" in section,
            section.index("goal-propose") < section.index("goal-approve"),
            "crew_ticket.py mint" in section, "`minted:`" in section,
            "`--goal <slug>`" in section, "arrives with" in section,
            "goal_status=printed" in section) == (True, True, True, False, True, True, False, True)


def test_goal_section_never_claims_the_goal_is_set():
    section = _goal_section().lower()

    assert [w for w in SET_WORDS if w in section] == []


# --- L-0541: mint, the picker, the run and its caps, `--goal` resume -----------

SESSION = "11111111-2222-3333-4444-555555555555"


def _minted(tmp_path, mode="backlog", approval="self", tickets=None, **caps):
    """A repo under a files tracker with an approved, minted goal: (root, slug, ids)."""
    root = _repo(tmp_path, approval=approval, armed=mode, tracker="files", **caps)
    slug = _goal(root, tickets=tickets)["slug"]
    assert _main(root, "goal-approve", "--goal", slug) == 0
    ids = [t["id"] for t in crew_autopilot_goal.read_goal(str(root), slug)["tickets"]]
    return root, slug, ids


def _set_status(root, ticket, status):
    index = root / ".work" / "INDEX.md"
    text = _read(index)
    new, count = re.subn(rf"^({re.escape(ticket)} \| )[^|]*( \|)", rf"\g<1>{status}\g<2>",
                         text, flags=re.MULTILINE)
    assert count == 1, text
    _write(index, new)


def _transcript(tmp_path, monkeypatch, *usages, session=SESSION, raw=None):
    """A Claude Code transcript for `session` under a temporary CLAUDE_CONFIG_DIR."""
    base = tmp_path / "claude-config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(base))
    path = base / "projects" / "-repo" / f"{session}.jsonl"
    lines = [json.dumps({"type": "assistant", "timestamp": f"2026-10-05T00:00:0{n}Z",
                         "message": {"usage": usage}}) for n, usage in enumerate(usages)]
    _write(path, "\n".join(lines + ([raw] if raw else [])) + "\n")
    return path


def _run(root, slug, session=SESSION):
    return crew_autopilot_backlog.goal_run(str(root), slug, session)


def test_mint_after_split_approval(tmp_path):
    root, slug, ids = _minted(tmp_path)

    texts = [_read(root / ".work" / "tickets" / t / "direction.md") for t in ids]
    assert (ids, [f".work/autopilot/{slug}.json" in t for t in texts],
            [f"goal-ticket: {slug} {n}/3" in t.splitlines() for n, t in enumerate(texts, 1)],
            ["risk: low" in t.splitlines() for t in texts]) == (
        ["T-0001", "T-0002", "T-0003"], [True] * 3, [True] * 3, [True] * 3)


def test_minted_ticket_status_ready(tmp_path):
    root, _slug, ids = _minted(tmp_path)

    assert [crew_autopilot._index_status(str(root), t) for t in ids] == ["ready"] * 3  # pylint: disable=protected-access


def test_mint_failure_midway_names_minted_and_unminted(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, approval="self", tracker="files")
    slug = _goal(root)["slug"]
    real, calls = crew_ticket.mint, []

    def flaky(*args, **kwargs):
        calls.append(args[1])
        if len(calls) == 2:
            raise crew_ticket.TicketError("the tracker said no")
        return real(*args, **kwargs)
    monkeypatch.setattr(crew_ticket, "mint", flaky)

    code = _main(root, "goal-approve", "--goal", slug)
    out = capsys.readouterr().out
    first = [t["id"] for t in crew_autopilot_goal.read_goal(str(root), slug)["tickets"]]
    monkeypatch.setattr(crew_ticket, "mint", real)
    again = _main(root, "goal-approve", "--goal", slug)
    ids = [t["id"] for t in crew_autopilot_goal.read_goal(str(root), slug)["tickets"]]

    assert (code, "minted: ticket 1 T-0001 - add the export endpoint" in out,
            "unminted: ticket 2 - wire the export button" in out,
            "unminted: ticket 3 - document the export" in out, "the tracker said no" in out,
            out.rstrip().splitlines()[-1], first, again, ids,
            sorted(os.listdir(root / ".work" / "tickets"))) == (
        2, True, True, True, True, f"resume: /crew:autopilot --goal {slug}",
        ["T-0001", None, None], 0, ["T-0001", "T-0002", "T-0003"],
        ["T-0001", "T-0002", "T-0003"])


def test_mint_adopts_a_ticket_whose_id_never_reached_the_goal_file(tmp_path):
    root, slug, _ids = _minted(tmp_path)
    goal = crew_autopilot_goal.read_goal(str(root), slug)
    goal["tickets"][1]["id"] = None
    _write(root / ".work" / "autopilot" / f"{slug}.json", json.dumps(goal))

    code = _main(root, "goal-approve", "--goal", slug)

    assert (code, [t["id"] for t in crew_autopilot_goal.read_goal(str(root), slug)["tickets"]],
            sorted(os.listdir(root / ".work" / "tickets"))) == (
        0, ["T-0001", "T-0002", "T-0003"], ["T-0001", "T-0002", "T-0003"])


def test_mint_refused_while_the_goal_file_is_locked(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(crew_autopilot_backlog, "LOCK_WAIT", 0.2)
    root = _repo(tmp_path, approval="self", tracker="files")
    slug = _goal(root)["slug"]
    _write(root / ".work" / "autopilot" / f"{slug}.lock", "")

    code = _main(root, "goal-approve", "--goal", slug)

    assert (code, f".work/autopilot/{slug}.lock" in capsys.readouterr().out,
            os.path.isdir(root / ".work" / "tickets")) == (2, True, False)


@pytest.mark.parametrize("mode", ["plan", "backlog"])
def test_backlog_arms_like_plan(tmp_path, mode):
    root = _repo(tmp_path, armed=mode)

    got = crew_autopilot.settings(str(root))

    assert (got["armed"], got["mode"], [w for w in got["warnings"] if "mode" in w]) == (
        True, mode, [])


@pytest.mark.parametrize("mode", ["Backlog", "backlog ", "auto", "PLAN", 1, ["backlog"]])
def test_mode_typo_still_reads_off(tmp_path, mode):
    root = _repo(tmp_path, armed=mode)

    got = crew_autopilot.settings(str(root))

    assert (got["armed"], got["mode"],
            any("only the exact strings 'plan' and 'backlog'" in w for w in got["warnings"])) == (
        False, "off", True)


@pytest.mark.parametrize("repo,machine,want", [("backlog", "plan", "plan"),
                                               ("plan", "backlog", "plan"),
                                               ("backlog", "backlog", "backlog"),
                                               ("backlog", "off", "off")])
def test_the_stricter_layer_wins_for_backlog(tmp_path, monkeypatch, repo, machine, want):
    import crew_config  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path, armed=repo)
    machine_file = tmp_path / "machine.json"
    _write(machine_file, json.dumps({"autopilot": {"mode": machine}}))
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(machine_file))

    assert crew_autopilot.settings(str(root))["mode"] == want


@pytest.mark.parametrize("value,want", [(None, 3), (5, 5), (0, 3), (True, 3), ("4", 3)])
def test_ticket_cap_setting(tmp_path, value, want):
    caps = {} if value is None else {"maxTicketsPerRun": value}
    root = _repo(tmp_path, **caps)

    got = crew_autopilot.settings(str(root))

    assert (got["maxTicketsPerRun"], got["maxTokensPerSession"],
            any("maxTicketsPerRun" in w for w in got["warnings"])) == (
        want, 2000000, value is not None and want != value)


def test_backlog_respects_dependencies(tmp_path):
    root, slug, ids = _minted(tmp_path)
    picks = [crew_autopilot_backlog.next_goal_ticket(str(root), slug)["ticket"]]
    for ticket in ids:
        _set_status(root, ticket, "done")
        picks.append(crew_autopilot_backlog.next_goal_ticket(str(root), slug))

    last = picks.pop()
    assert ([picks[0]] + [p["ticket"] for p in picks[1:]], last["done"], last["stop"]) == (
        ["T-0001", "T-0002", "T-0003"], True, True)


@pytest.mark.parametrize("status", ["cancelled", "superseded", "needs-owner"])
def test_stopped_dependency_blocks(tmp_path, status):
    root, slug, _ids = _minted(tmp_path)
    _set_status(root, "T-0001", status)

    got = crew_autopilot_backlog.next_goal_ticket(str(root), slug)

    assert (got["ticket"], got["stop"], got["done"], "T-0001" in got["reason"]) == (
        None, True, False, True)


def test_a_settled_ticket_nothing_depends_on_is_passed(tmp_path):
    tickets = [dict(t, depends_on=[]) for t in TICKETS]
    root, slug, _ids = _minted(tmp_path, tickets=tickets)
    _set_status(root, "T-0001", "cancelled")

    got = crew_autopilot_backlog.next_goal_ticket(str(root), slug)

    assert (got["ticket"], got["stop"]) == ("T-0002", False)


@pytest.mark.parametrize("how", ["no-row", "unminted", "no-goal"])
def test_a_ticket_state_that_cannot_be_told_stops(tmp_path, how):
    root, slug, _ids = _minted(tmp_path)
    if how == "no-row":
        _write(root / ".work" / "INDEX.md", "")
    elif how == "unminted":
        goal = crew_autopilot_goal.read_goal(str(root), slug)
        goal["tickets"][0]["id"] = None
        _write(root / ".work" / "autopilot" / f"{slug}.json", json.dumps(goal))
    else:
        os.remove(root / ".work" / "autopilot" / f"{slug}.json")

    got = crew_autopilot_backlog.next_goal_ticket(str(root), slug)

    assert (got["ticket"], got["stop"], got["done"]) == (None, True, False)


def _plan_ticket(root, ticket, risk="low"):
    folder = root / ".work" / "tickets" / ticket
    body = SPEC.format(ticket=ticket, touch="- `src/**`")
    first, rest = body.split("\n", 1)
    _write(folder / "spec.md", f"{first} title          status: spec   risk: {risk}\n{rest}")
    _write(folder / "plan.md", PLAN.format(files="src/app.py"))


def test_minted_ticket_self_approved_one_at_a_time(tmp_path, monkeypatch):
    root, slug, ids = _minted(tmp_path)
    for ticket in ids:
        _plan_ticket(root, ticket)
    asked = []
    real = crew_autopilot.approve
    monkeypatch.setattr(crew_autopilot, "approve",
                        lambda top, ticket: asked.append(ticket) or real(top, ticket))

    code, text = crew_autopilot_backlog.ticket_approve(str(root), slug, "T-0001")

    assert (code, text.splitlines(), asked,
            [os.path.exists(crew_ticket.approval_path(str(root), t)) for t in ids]) == (
        0, ["self-approved T-0001 under approval=self, risk=low"], ["T-0001"],
        [True, False, False])


@pytest.mark.parametrize("approval", ["human", "risk"])
def test_minted_ticket_refusal_stops_with_one_id(tmp_path, approval):
    root, slug, _ids = _minted(tmp_path, approval="self")
    _plan_ticket(root, "T-0001", risk="high")
    config = json.loads(_read(root / ".crew" / "config.json"))
    config["autopilot"]["approval"] = approval
    _write(root / ".crew" / "config.json", json.dumps(config))

    code, out = _cli_inproc(root, "goal-approve", "--goal", slug, "--ticket", "T-0001")

    lines = out.splitlines()
    named = re.findall(r"/crew:approve (\S+)", out)
    assert (code, lines[-2:], set(named), "--confirm" in out) == (
        2, ["/crew:approve T-0001", f"resume: /crew:autopilot --goal {slug}"], {"T-0001"},
        False)


def test_goal_approve_refuses_a_ticket_outside_the_goal(tmp_path):
    root, slug, _ids = _minted(tmp_path)

    code, out = _cli_inproc(root, "goal-approve", "--goal", slug, "--ticket", "T-9999")

    assert (code, out.startswith("refused: T-9999 is not a minted ticket"),
            "/crew:approve" in out) == (2, True, False)


def _cli_inproc(root, *argv):
    out = _cli(root, *argv)
    return out.returncode, out.stdout


def test_goal_run_picks_records_and_reports(tmp_path, monkeypatch):
    root, slug, _ids = _minted(tmp_path)
    _transcript(tmp_path, monkeypatch, {"input_tokens": 10, "output_tokens": 5})

    got = _run(root, slug)

    runs = crew_autopilot_goal.read_goal(str(root), slug)["runs"]
    assert (got["ticket"], got["stop"], got["activate"], got["goal"], got["run"]["tickets"],
            got["run"]["tokens"], [(r["session"], r["tickets"]) for r in runs]) == (
        "T-0001", False, True, slug, ["T-0001"], 15, [(SESSION, ["T-0001"])])


def test_plan_mode_stops_after_one(tmp_path, monkeypatch):
    root, slug, _ids = _minted(tmp_path, mode="plan")
    _transcript(tmp_path, monkeypatch, {"input_tokens": 1, "output_tokens": 1})
    first = _run(root, slug)
    again = _run(root, slug)
    _set_status(root, "T-0001", "done")
    crew_ticket.activate(str(root), "T-0001")

    second = _run(root, slug)
    config = json.loads(_read(root / ".crew" / "config.json"))
    config["autopilot"]["mode"] = "backlog"
    _write(root / ".crew" / "config.json", json.dumps(config))
    backlog = _run(root, slug)

    assert (first["ticket"], again["ticket"], second["stop"], "mode is plan" in second["reason"],
            backlog["ticket"], backlog["activate"]) == (
        "T-0001", "T-0001", True, True, "T-0002", True)


def test_ticket_cap_stops(tmp_path, monkeypatch):
    tickets = [{"title": f"ticket {n}", "risk": "low", "depends_on": []} for n in range(4)]
    root, slug, ids = _minted(tmp_path, tickets=tickets)
    _transcript(tmp_path, monkeypatch, {"input_tokens": 1, "output_tokens": 1})
    picks = []
    for ticket in ids:
        got = _run(root, slug)
        picks.append(got["ticket"] or got["reason"])
        _set_status(root, ticket, "done")

    text = crew_autopilot_backlog.goal_run_text(got)
    assert (picks[:3], "maxTicketsPerRun is 3" in picks[3],
            text.splitlines()[-1]) == (
        ["T-0001", "T-0002", "T-0003"], True, f"resume: /crew:autopilot --goal {slug}")


def test_a_new_session_is_a_new_run(tmp_path, monkeypatch):
    root, slug, _ids = _minted(tmp_path, maxTicketsPerRun=1)
    _transcript(tmp_path, monkeypatch, {"input_tokens": 1, "output_tokens": 1})
    _transcript(tmp_path, monkeypatch, {"input_tokens": 1, "output_tokens": 1}, session="other")
    _run(root, slug)
    _set_status(root, "T-0001", "done")

    same, other = _run(root, slug), _run(root, slug, session="other")

    assert (same["stop"], other["ticket"]) == (True, "T-0002")


@pytest.mark.parametrize("usage,stops", [({"input_tokens": 1_500_000, "output_tokens": 600_000}, True),
                                         ({"input_tokens": 1_000_000, "output_tokens": 1_000_000}, False),
                                         ({"input_tokens": 1, "output_tokens": 1,
                                           "cache_read_input_tokens": 9_000_000,
                                           "cache_creation_input_tokens": 9_000_000}, False)])
def test_token_cap_stops(tmp_path, monkeypatch, usage, stops):
    root, slug, _ids = _minted(tmp_path)
    _transcript(tmp_path, monkeypatch, usage)

    got = _run(root, slug)

    assert (got["stop"], "maxTokensPerSession" in got["reason"],
            crew_autopilot_goal.read_goal(str(root), slug)["runs"] == []) == (stops, stops, stops)


@pytest.mark.parametrize("how", ["no-session", "bad-session", "no-file", "two-files",
                                 "corrupt-line", "no-usage"])
def test_unreadable_transcript_stops(tmp_path, monkeypatch, how):
    root, slug, _ids = _minted(tmp_path)
    session = SESSION
    if how == "no-session":
        session = ""
    elif how == "bad-session":
        session = "../x"
    elif how == "no-file":
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "empty"))
    elif how == "two-files":
        path = _transcript(tmp_path, monkeypatch, {"input_tokens": 1, "output_tokens": 1})
        _write(path.parent.parent / "-other" / path.name, _read(path))
    elif how == "corrupt-line":
        _transcript(tmp_path, monkeypatch, {"input_tokens": 1, "output_tokens": 1}, raw="{cut")
    else:
        _transcript(tmp_path, monkeypatch, {"cache_read_input_tokens": 5})

    got = _run(root, slug, session=session)

    assert (got["ticket"], got["stop"], "could not tell" in got["reason"],
            crew_autopilot_goal.read_goal(str(root), slug)["runs"]) == (None, True, True, [])


def test_goal_run_refuses_unarmed(tmp_path, monkeypatch):
    root, slug, _ids = _minted(tmp_path)
    _transcript(tmp_path, monkeypatch, {"input_tokens": 1, "output_tokens": 1})
    config = json.loads(_read(root / ".crew" / "config.json"))
    config["autopilot"]["mode"] = "off"
    _write(root / ".crew" / "config.json", json.dumps(config))

    got = _run(root, slug)

    assert (got["stop"], "plan or backlog" in got["reason"]) == (True, True)


def test_goal_done_prints_no_resume_line(tmp_path, monkeypatch):
    root, slug, ids = _minted(tmp_path)
    _transcript(tmp_path, monkeypatch, {"input_tokens": 1, "output_tokens": 1})
    for ticket in ids:
        _set_status(root, ticket, "done")

    got = _run(root, slug)

    assert (got["stop"], got["done"], "resume:" in crew_autopilot_backlog.goal_run_text(got)) == (
        True, True, False)


def test_goal_run_cli_line(tmp_path, monkeypatch):
    root, slug, _ids = _minted(tmp_path)
    path = _transcript(tmp_path, monkeypatch, {"input_tokens": 1, "output_tokens": 1})

    out = _cli(root, "goal-run", "--goal", slug, "--transcript", str(path))

    assert (out.returncode, out.stdout.splitlines()[0].split(" reason=")[0]) == (
        0, f"ticket=T-0001 source=goal:{slug} stop=0 activate=1 goal={slug}")


def test_goal_resume_from_argument(tmp_path):
    root, slug, _ids = _minted(tmp_path)

    got = crew_autopilot.resume_target(str(root), goal=slug)

    assert (got["ticket"], got["stop"], got["goal"], got["activate"]) == (
        "T-0001", False, slug, True)


def _goal_handoff(root, slug):
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(root),
                            capture_output=True, text=True, check=True).stdout.strip()
    head = subprocess.run(["git", "rev-parse", "--short=10", "HEAD"], cwd=str(root),
                          capture_output=True, text=True, check=True).stdout.strip()
    _write(root / ".work" / "HANDOFF.md", f"# Handoff\nbranch: {branch}\nhead: {head}\n"
                                          f"resume: /crew:autopilot --goal {slug}\n")


def test_goal_resume_from_handoff(tmp_path):
    root, slug, _ids = _minted(tmp_path)
    _set_status(root, "T-0001", "done")
    crew_ticket.activate(str(root), "T-0001")
    _goal_handoff(root, slug)
    import crew_autopilot_handoff  # pylint: disable=import-outside-toplevel
    crew_autopilot_handoff.goal_mark(str(root), slug, "running", "T-0001")  # T-0056, L-0658

    got = crew_autopilot.resume_target(str(root))
    shown = crew_autopilot.status(str(root))

    assert (got["ticket"], got["source"], got["stop"], got["goal"], got["activate"],
            any(f"--goal {slug} (usable)" in str(v) for v in shown.values())) == (
        "T-0002", "handoff", False, slug, True, True)


def test_goal_resume_keeps_a_pointer_outside_the_goal(tmp_path):
    root, slug, _ids = _minted(tmp_path)
    folder = root / ".work" / "tickets" / "T-0050"
    _write(folder / "direction.md", "go\n")
    crew_ticket.activate(str(root), "T-0050")

    got = crew_autopilot.resume_target(str(root), goal=slug)

    assert (got["ticket"], got["stop"], "T-0050" in got["reason"]) == (None, True, True)


def test_goal_resume_with_an_unknown_slug_names_the_file(tmp_path):
    root = make_repo(tmp_path, mode="off")

    got = crew_autopilot.resume_target(str(root), goal="nope")

    assert (got["stop"], ".work/autopilot/nope.json" in got["reason"]) == (True, True)


def test_no_arrives_with_l0541_text_remains():
    found = []
    for base, _dirs, names in os.walk(_ROOT):
        for name in names:
            if name.endswith((".py", ".md")) and name != os.path.basename(__file__):
                path = os.path.join(base, name)
                text = _read(path)
                if "arrives with L-0541" in text or "goal resume arrives with T-0012" in text:
                    found.append(path)
    assert found == []


# --- L-0541 review round 1 -----------------------------------------------------

def test_the_approval_note_keeps_a_run_recorded_since_the_first_read(tmp_path, monkeypatch):
    root, slug, _got = _policy(tmp_path, risks=("low", "low"), approval="self")
    path = crew_autopilot_goal.goal_path(str(root), slug)
    real = crew_autopilot_goal.split_policy
    run = {"started": "2026-10-05T00:00:00Z", "session": "s", "tickets": ["T-0001"]}

    def policy_then_run(top, name, goal=None):
        got = real(top, name, goal)
        data = json.loads(_read(path))
        data["runs"].append(run)
        _write(path, json.dumps(data))
        return got

    monkeypatch.setattr(crew_autopilot_goal, "split_policy", policy_then_run)
    got = crew_autopilot_goal.split_approved(str(root), slug)
    stored = json.loads(_read(path))

    assert (got["approved"], stored["runs"], stored["approval"]["via"]) == (
        True, [run], "autopilot:self")


def test_a_ticket_minted_at_direction_stops_the_mint(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, approval="self", tracker="files")
    slug = _goal(root)["slug"]
    real = crew_ticket.mint

    def left_at_direction(*args, **kwargs):
        got = real(*args, **kwargs)
        if got["ticket"] == "T-0002":
            _set_status(root, "T-0002", "direction")
            got = dict(got, status="direction")
        return got
    monkeypatch.setattr(crew_ticket, "mint", left_at_direction)

    code = _main(root, "goal-approve", "--goal", slug)
    out = capsys.readouterr().out
    monkeypatch.setattr(crew_ticket, "mint", real)
    again = _main(root, "goal-approve", "--goal", slug)

    assert (code, "T-0002 (direction) minted but not `ready`" in out, again,
            [t["id"] for t in crew_autopilot_goal.read_goal(str(root), slug)["tickets"]]) == (
        2, True, 2, ["T-0001", "T-0002", "T-0003"])


@pytest.mark.parametrize("status", ["bogus", "todo", ""])
def test_an_index_status_crew_never_writes_is_unknown(tmp_path, status):
    root, slug, _ids = _minted(tmp_path)
    _plan_ticket(root, "T-0001")
    spec = root / ".work" / "tickets" / "T-0001" / "spec.md"
    _write(spec, _read(spec).replace("status: spec", "status: done"))
    _set_status(root, "T-0001", status)

    got = crew_autopilot_backlog.next_goal_ticket(str(root), slug)

    assert (got["ticket"], got["stop"], "T-0001" in got["reason"]) == (None, True, True)


def test_status_shows_backlog_as_armed(tmp_path):
    root = _repo(tmp_path, armed="backlog")

    text = crew_autopilot.status_text(crew_autopilot.status(str(root)))

    assert text.splitlines()[0] == "mode: backlog, maxPhases 12"


def test_a_token_count_that_raises_is_could_not_tell(tmp_path, monkeypatch):
    root, slug, _ids = _minted(tmp_path)
    _transcript(tmp_path, monkeypatch, {"input_tokens": "lots", "output_tokens": 1})

    got = _run(root, slug)

    assert (got["stop"], "could not tell" in got["reason"],
            crew_autopilot_backlog.goal_run_text(got).splitlines()[-1]) == (
        True, True, f"resume: /crew:autopilot --goal {slug}")


# --- L-0541 review round 2 -------------------------------------------------------

@pytest.mark.parametrize("phase,want", [("ship", "T-0001"), ("next-slice", "T-0001"),
                                        ("closed", "T-0002")])
def test_a_done_ticket_still_owed_its_ship_is_worked_before_the_next(tmp_path, monkeypatch,
                                                                     phase, want):
    root, slug, _ids = _minted(tmp_path)
    _set_status(root, "T-0001", "done")
    real = crew_autopilot._phase  # pylint: disable=protected-access
    monkeypatch.setattr(crew_autopilot, "_phase", lambda top, ticket, policy=True: (
        dict(real(top, ticket, policy), phase=phase) if ticket == "T-0001"
        else real(top, ticket, policy)))

    got = crew_autopilot_backlog.next_goal_ticket(str(root), slug)

    assert (got["ticket"], got["stop"]) == (want, False)


def test_a_done_check_that_raises_is_could_not_tell(tmp_path, monkeypatch):
    root, slug, _ids = _minted(tmp_path)
    _set_status(root, "T-0001", "done")

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk")
    monkeypatch.setattr(crew_autopilot, "_phase", boom)

    got = crew_autopilot_backlog.next_goal_ticket(str(root), slug)

    assert (got["ticket"], got["stop"], "could not tell" in got["reason"]) == (None, True, True)


# --- L-0541 review round 3 -------------------------------------------------------

def test_an_adopted_folder_without_an_index_row_stops_the_mint(tmp_path, capsys):
    root, slug, _ids = _minted(tmp_path)
    goal = crew_autopilot_goal.read_goal(str(root), slug)
    goal["tickets"][2]["id"] = None
    _write(root / ".work" / "autopilot" / f"{slug}.json", json.dumps(goal))
    index = root / ".work" / "INDEX.md"
    _write(index, "".join(l for l in _read(index).splitlines(True) if "T-0003" not in l))

    code = _main(root, "goal-approve", "--goal", slug)

    assert (code, "T-0003 (no INDEX row) minted but not `ready`" in capsys.readouterr().out) == (
        2, True)
