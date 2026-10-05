"""T-0052: `crew_split.py`, the one split rulebook behind `/crew:split`.

    python3 -m pytest plugin/crew/tests/test_crew_split.py -q

`measure` and `triggers` say whether a ticket is worth a look (an unreadable
measure is `None` and reported as `unknown:<name>`, never as "not fired");
`check_proposal` holds a `split.md` to the rules `/crew:split` states (2-5
children, every parent criterion placed verbatim exactly once, exclusions,
`separable-criteria`); `confirm` refuses unless a human prompt has arrived
since `check` passed on an unchanged proposal; `apply --via command` keeps the
parent's spec as `spec.pre-split.md`, mints each child through
`crew_ticket.mint`, and only then marks the parent `superseded`.

`split_fixtures/t0004_spec_pre_split.md` is RECONSTRUCTED, not a byte copy:
`.work/tickets/T-0004/spec.pre-split.md` is gitignored and was not in the
cloud container this was built in. It keeps the measured shape the spec
records (12 acceptance checks, 18 Touch entries, one subsystem, four groups:
next/resume staying on the parent, the approval and question policies
(T-0010), ship (T-0011) and goal minting (T-0012)). Replace it with the real
file's bytes when one is to hand; the counts the tests assert are the spec's.

Every repository is built under tmp_path; nothing touches the real one,
a real vault or ~/.claude.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

import context  # noqa: F401  pylint: disable=unused-import
import crew_context
import crew_split
import crew_ticket
import crew_tracker
import pytest
from crew_fixtures import make_repo
from test_crew_tracker import _lane_of, _make_vault

SCRIPTS = os.path.dirname(os.path.abspath(crew_split.__file__))
SCRIPT = os.path.join(SCRIPTS, "crew_split.py")
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "split_fixtures",
                       "t0004_spec_pre_split.md")
COMMAND = os.path.join(os.path.dirname(SCRIPTS), os.pardir, "commands", "split.md")
SESSION = "sess-split-1"


def _fixture_text():
    with open(FIXTURE, encoding="utf-8") as handle:
        return handle.read()


def _criteria(text=None):
    return crew_split.parent_criteria(text if text is not None else _fixture_text())


# --- the T-0004 three-way split (must-allow) ----------------------------------------

def _t0004_proposal(crit=None, drop=None, extra_child=None, children=None, evidence=None,
                    stays=None):
    """A `split.md` placing the fixture's twelve criteria as T-0004's split
    did: approval and questions (T-0010), ship (T-0011), goal minting
    (T-0012), and next/resume plus bookkeeping staying on the parent."""
    crit = list(crit or _criteria())
    groups = children or [
        ("autopilot approval and question policies", "high", crit[4:7]),
        ("autopilot ship policy", "high", crit[7:10]),
        ("autopilot goal: tickets from a goal file", "med", crit[10:11]),
    ]
    if extra_child:
        groups = groups + extra_child
    stay = stays if stays is not None else crit[0:4] + crit[11:12]
    lines = ["# T-0004 split          decision: split",
             "answered: acceptance-count, plan-steps", "", "## Evidence"]
    lines += [f"- {e}" for e in (evidence or [
        "acceptance-count: 12 checks, at ACCEPTANCE_LOOK",
        "separable-criteria: approval, ship and goal minting are verified apart from next/resume"])]
    lines += ["", "## Children"]
    for number, (title, risk, items) in enumerate(groups, 1):
        lines += [f"### Child {number}: {title}", f"risk: {risk}", "subsystem: crew", "Criteria:"]
        lines += [f"- {c}" for c in items if c != drop]
        lines += ["Excludes:", "- next/resume, which stays on T-0004", ""]
    lines += ["## Stays on parent"] + [f"- {c}" for c in stay if c != drop]
    return "\n".join(lines) + "\n"


def test_t0004_three_way_split_ok():
    decision, problems = crew_split.check_proposal(_criteria(), _t0004_proposal())

    assert (decision, problems) == ("split", [])


def test_not_too_big_with_evidence_ok():
    text = ("# T-0004 split          decision: not-too-big\nanswered: acceptance-count\n\n"
            "## Evidence\n- acceptance-count: 12, but every check is verified by one suite\n")

    assert crew_split.check_proposal(_criteria(), text) == ("not-too-big", [])


def test_jira_criteria_file_ok(tmp_path):
    root = _files_repo(tmp_path)
    criteria = root / "crit.md"
    criteria.write_text("- [ ] one thing works\n- [x] another thing works\n- third thing\n",
                        encoding="utf-8")
    proposal = root / ".work" / "tickets" / "PROJ-12" / "split.md"
    proposal.parent.mkdir(parents=True)
    proposal.write_text(_proposal_two(["one thing works"], ["another thing works"],
                                      ["third thing"]), encoding="utf-8")

    got = crew_split.check(str(root), "PROJ-12", criteria_file=str(criteria), session=SESSION)

    assert got == ("split", [])


def _proposal_two(first, second, stays, decision="split"):
    lines = [f"# X split          decision: {decision}", "", "## Evidence",
             "- separable-criteria: the two halves share no files", "", "## Children"]
    for number, items in enumerate((first, second), 1):
        lines += [f"### Child {number}: part {number}", "risk: low", "subsystem: crew",
                  "Criteria:"] + [f"- {c}" for c in items] + ["Excludes:", "- the other part", ""]
    lines += ["## Stays on parent"] + ([f"- {c}" for c in stays] or ["- none"])
    return "\n".join(lines) + "\n"


# --- the proposal check (must-block) -------------------------------------------------

def test_one_child_refused():
    crit = _criteria()
    text = _t0004_proposal(children=[("everything", "high", crit[4:11])])

    _, problems = crew_split.check_proposal(crit, text)

    assert any("1 child" in p and "2-5" in p for p in problems), problems


def test_six_children_refused():
    crit = _criteria()
    groups = [(f"part {i}", "low", crit[4 + i:5 + i]) for i in range(6)]
    text = _t0004_proposal(children=groups, stays=crit[0:4] + crit[10:12])

    _, problems = crew_split.check_proposal(crit, text)

    assert any("6 children" in p and "2-5" in p for p in problems), problems


def test_five_children_allowed():
    crit = _criteria()
    groups = [(f"part {i}", "low", crit[4 + i:5 + i]) for i in range(5)]
    text = _t0004_proposal(children=groups, stays=crit[0:4] + crit[9:12])

    assert crew_split.check_proposal(crit, text) == ("split", [])


def test_paraphrased_criterion_refused():
    crit = _criteria()
    changed = list(crit)
    changed[7] = crit[7] + " and says so"
    text = _t0004_proposal(crit=changed)

    _, problems = crew_split.check_proposal(crit, text)

    assert any("not placed" in p and crit[7] in p for p in problems), problems


def test_whitespace_only_difference_is_verbatim():
    crit = _criteria()
    spaced = [c.replace(" ", "  ", 1) for c in crit]

    assert crew_split.check_proposal(crit, _t0004_proposal(crit=spaced)) == ("split", [])


def test_dropped_criterion_refused_and_named():
    crit = _criteria()

    _, problems = crew_split.check_proposal(crit, _t0004_proposal(drop=crit[8]))

    assert problems == [f"criterion not placed in any child or on the parent: {crit[8]}"]


def test_duplicate_placement_refused():
    crit = _criteria()
    stays = crit[0:4] + crit[11:12] + crit[7:8]

    _, problems = crew_split.check_proposal(crit, _t0004_proposal(stays=stays))

    assert problems == [f"criterion placed 2 times (exactly once is the rule): {crit[7]}"]


def test_child_without_exclusions_refused():
    text = _t0004_proposal().replace("Excludes:\n- next/resume, which stays on T-0004\n\n"
                                     "### Child 2", "\n### Child 2", 1)

    _, problems = crew_split.check_proposal(_criteria(), text)

    assert problems == ["child 1 (autopilot approval and question policies) states no "
                        "exclusion (an Excludes: bullet)"]


def test_child_missing_title_risk_subsystem_refused():
    text = (_t0004_proposal().replace("### Child 1: autopilot approval and question policies",
                                      "### Child 1:", 1)
            .replace("risk: high", "risk: huge", 1).replace("subsystem: crew\n", "", 1))

    _, problems = crew_split.check_proposal(_criteria(), text)

    assert problems == [
        "child 1 has no title", "child 1 has no risk: low|med|high (got 'huge')",
        "child 1 names no subsystem"]


def test_split_without_separable_evidence_refused():
    text = _t0004_proposal(evidence=["acceptance-count: 12 checks"])

    _, problems = crew_split.check_proposal(_criteria(), text)

    assert problems == ["a split needs a separable-criteria evidence line: criteria that "
                        "cannot be verified together"]


def test_unknown_evidence_key_only_refused():
    text = ("# T-0004 split          decision: not-too-big\n\n## Evidence\n"
            "- gut-feeling: it looks big\n")

    _, problems = crew_split.check_proposal(_criteria(), text)

    assert problems == [
        "evidence key 'gut-feeling' is not one of " + ", ".join(crew_split.EVIDENCE_KEYS),
        "## Evidence names no known evidence key (" + ", ".join(crew_split.EVIDENCE_KEYS) + ")"]


def test_invented_criterion_refused():
    crit = _criteria()
    stays = crit[0:4] + crit[11:12] + ["a criterion the parent never had"]

    _, problems = crew_split.check_proposal(crit, _t0004_proposal(stays=stays))

    assert problems == ["placed text is not a parent criterion: a criterion the parent never had"]


def test_unreadable_parent_refused():
    _, problems = crew_split.check_proposal(None, _t0004_proposal())

    assert problems == ["the parent's acceptance criteria could not be read; nothing can be "
                        "checked as placed"]


def test_unknown_decision_refused():
    text = _t0004_proposal().replace("decision: split", "decision: maybe", 1)

    decision, problems = crew_split.check_proposal(_criteria(), text)

    assert (decision, problems[0]) == (None, "decision: 'maybe' is not one of split, slices, "
                                       "not-too-big (on the # header line)")


def test_not_too_big_with_children_refused():
    text = _t0004_proposal().replace("decision: split", "decision: not-too-big", 1)

    _, problems = crew_split.check_proposal(_criteria(), text)

    assert problems == ["decision not-too-big takes no ## Children section"]


def test_minted_section_is_not_a_placement():
    text = _t0004_proposal() + "\n## Minted\n- Child 1: T-0099\n"

    assert crew_split.check_proposal(_criteria(), text) == ("split", [])


# --- measures and triggers ----------------------------------------------------------

def _ticket(root, ticket, spec, plan=None):
    folder = root / ".work" / "tickets" / ticket
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "spec.md").write_text(spec, encoding="utf-8", newline="\n")
    if plan is not None:
        (folder / "plan.md").write_text(plan, encoding="utf-8", newline="\n")
    return folder


def _plan(steps):
    return "# plan\n\n" + "".join(f"### Step {i}: s\nFiles: a\n\n" for i in range(1, steps + 1))


def _codemap(root, subs):
    folder = root / ".crew" / "codemap"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "INDEX.md").write_text("# index\n", encoding="utf-8")
    for name, path in subs.items():
        (folder / f"{name}.md").write_text(f"anchor: x@abc1234\npaths: {path}**\n\n# {name}\n",
                                           encoding="utf-8")


def test_measure_counts_acceptance_steps_touch(tmp_path):
    root = make_repo(tmp_path)
    spec = ("# T-0001 x          status: spec   risk: low\n## Touch\n- `src/a.py`\n- `doc/b.md`\n"
            "## Acceptance checks\n- [ ] one\n- [x] two\n- not a checkbox\n")
    _ticket(root, "T-0001", spec, _plan(3))

    got = crew_split.measure(str(root), "T-0001")

    assert {k: got[k] for k in ("plan_steps", "acceptance", "touch")} == {
        "plan_steps": 3, "acceptance": 2, "touch": 2}


def test_measure_pre_split_t0004_fixture(tmp_path):
    root = make_repo(tmp_path)
    _ticket(root, "T-0004", _fixture_text())

    got = crew_split.measure(str(root), "T-0004")

    assert (got["acceptance"], got["touch"]) == (12, 18)
    assert "acceptance-count" in crew_split.triggers(got, "spec")


def test_measure_subsystems_from_codemap(tmp_path):
    root = make_repo(tmp_path)
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("x\n", encoding="utf-8")
    (root / "doc").mkdir()
    (root / "doc" / "b.md").write_text("x\n", encoding="utf-8")
    _codemap(root, {"code": "src/", "docs": "doc/"})
    spec = "# T-0001 x\n## Touch\n- `src/a.py`\n- `doc/b.md`\n## Acceptance checks\n- [ ] one\n"
    _ticket(root, "T-0001", spec)

    got = crew_split.measure(str(root), "T-0001")

    assert got["subsystems"] == 2
    assert "subsystems" in crew_split.triggers(got, "spec")


def test_unreadable_spec_measures_none(tmp_path):
    root = make_repo(tmp_path)
    (root / ".work" / "tickets" / "T-0001").mkdir(parents=True)

    got = crew_split.measure(str(root), "T-0001")

    assert {k: got[k] for k in ("acceptance", "touch", "subsystems", "plan_steps")} == {
        "acceptance": None, "touch": None, "subsystems": None, "plan_steps": None}


def test_missing_codemap_subsystems_none(tmp_path):
    root = make_repo(tmp_path)
    _ticket(root, "T-0001", "# T-0001 x\n## Touch\n- `src/a.py`\n## Acceptance checks\n- [ ] a\n")

    assert crew_split.measure(str(root), "T-0001")["subsystems"] is None


def test_no_metrics_reads_none_never_zero(tmp_path):
    root = make_repo(tmp_path)
    _ticket(root, "T-0001", "# T-0001 x\n## Touch\n- `a`\n## Acceptance checks\n- [ ] a\n")

    got = crew_split.measure(str(root), "T-0001")

    assert (got["findings_rate"], got["tickets_too_large"]) == (None, None)


def test_high_findings_rate_fires_both_repo_triggers(tmp_path):
    root = make_repo(tmp_path, metrics=[("T-1", 3, 2), ("T-2", 2, 1)])
    _ticket(root, "T-0001", "# T-0001 x\n## Touch\n- `a`\n## Acceptance checks\n- [ ] a\n")

    got = crew_split.measure(str(root), "T-0001")

    assert (got["findings_rate"], got["tickets_too_large"]) == (4.0, True)
    assert {"findings-rate", "tickets-too-large"} <= set(crew_split.triggers(got, "spec"))


def test_none_measure_reports_unknown_not_quiet():
    measures = dict.fromkeys(crew_split.MEASURES)

    assert crew_split.triggers(measures, "plan") == [
        "unknown:acceptance-count", "unknown:subsystems", "unknown:findings-rate",
        "unknown:tickets-too-large", "unknown:plan-steps"]


def test_quiet_measures_fire_nothing():
    measures = {"plan_steps": 8, "acceptance": 11, "touch": 40, "subsystems": 1,
                "findings_rate": 2.0, "tickets_too_large": False}

    assert crew_split.triggers(measures, "plan") == []


def test_plan_steps_only_at_plan_stage():
    measures = {"plan_steps": 9, "acceptance": 1, "touch": 1, "subsystems": 1,
                "findings_rate": 0.5, "tickets_too_large": False}

    assert (crew_split.triggers(measures, "spec"), crew_split.triggers(measures, "plan")) == (
        [], ["plan-steps"])


def test_thresholds_have_evidence_comments():
    with open(SCRIPT, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    for name in ("PLAN_STEPS_LOOK", "ACCEPTANCE_LOOK", "SUBSYSTEMS_LOOK", "CHILDREN_MIN"):
        at = next(i for i, line in enumerate(lines) if line.startswith(f"{name} ") or
                  line.startswith(f"{name},"))
        above = []
        for line in reversed(lines[:at]):
            if not line.startswith("#"):
                break
            above.append(line)
        assert re.search(r"T-\d{4}|split\.md", " ".join(above)), name


def test_bad_stage_refused():
    with pytest.raises(crew_split.SplitError):
        crew_split.triggers(dict.fromkeys(crew_split.MEASURES), "implement")


# --- tracker mode -------------------------------------------------------------------

def _files_repo(tmp_path, tracker="files"):
    root = make_repo(tmp_path)
    (root / ".crew" / "config.json").write_text(json.dumps({"tracker": tracker}),
                                                encoding="utf-8")
    return root


@pytest.mark.parametrize("tracker", ["files", "jira", "sdp"])
def test_tracker_mode_reads_config(tmp_path, tracker):
    assert crew_split.tracker_mode(str(_files_repo(tmp_path, tracker))) == tracker


def test_tracker_mode_default_files(tmp_path):
    assert crew_split.tracker_mode(str(make_repo(tmp_path))) == "files"


def test_tracker_mode_unreadable_is_unknown(tmp_path):
    root = make_repo(tmp_path)
    (root / ".crew" / "config.json").write_text("{not json", encoding="utf-8")

    assert crew_split.tracker_mode(str(root)) == "unknown"


# --- confirm and apply --------------------------------------------------------------

def _turn(root, turn_id, session=SESSION, prompt=True):
    """The context hook's per-session record after a typed prompt (its
    `lastPrompt` distinct per turn); `prompt=None` leaves `lastPrompt` out."""
    path = crew_context._session_file(str(root), session)  # pylint: disable=protected-access
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"epoch": 0, "seen": {}, "turn": {"id": turn_id, "used": 0}}
    if prompt is not None:
        data["lastPrompt"] = f"typed for {turn_id}" if prompt is True else prompt
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data))
    return path


def _parent(root):
    """Mint T-0004's stand-in through the real tracker, give it the fixture
    spec, and move it to `spec`. Returns its id."""
    got = crew_ticket.mint(str(root), "crew autopilot", status="ready", direction="go")
    ticket = got["ticket"]
    folder = root / ".work" / "tickets" / ticket
    (folder / "spec.md").write_text(_fixture_text().replace("T-0004", ticket),
                                    encoding="utf-8", newline="\n")
    report = crew_tracker.move(str(root), ticket, "spec")
    assert crew_tracker.exit_code(report) == 0, report
    return ticket


def _staged(root, ticket, text=None):
    path = root / ".work" / "tickets" / ticket / "split.md"
    path.write_text(text if text is not None else _t0004_proposal(), encoding="utf-8",
                    newline="\n")
    return path


def _checked(root, ticket, turn="turn-1"):
    _turn(root, turn)
    _staged(root, ticket)
    assert crew_split.check(str(root), ticket, session=SESSION) == ("split", [])
    _turn(root, "turn-2")


def _index_status(root, ticket):
    for line in (root / ".work" / "INDEX.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")]
        if cells and cells[0] == ticket:
            return cells[1]
    return None


def test_confirm_after_new_human_turn(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)

    assert crew_split.confirm(str(root), ticket, session=SESSION)["ok"] is True


def test_confirm_refuses_same_turn(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    _turn(root, "turn-1")

    got = crew_split.confirm(str(root), ticket, session=SESSION)

    assert (got["ok"], "no human prompt has arrived since" in got["reason"]) == (False, True)


def test_confirm_refuses_without_turn_record(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    os.remove(crew_context._session_file(str(root), SESSION))  # pylint: disable=protected-access

    got = crew_split.confirm(str(root), ticket, session=SESSION)

    assert (got["ok"], "no turn record" in got["reason"]) == (False, True)


def test_confirm_refuses_without_session(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    monkeypatch.delenv(crew_split.SESSION_ENV, raising=False)

    got = crew_split.confirm(str(root), ticket)

    assert (got["ok"], crew_split.SESSION_ENV in got["reason"]) == (False, True)


def test_confirm_refuses_unreadable_turn_record(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    path = crew_context._session_file(str(root), SESSION)  # pylint: disable=protected-access
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{torn")

    got = crew_split.confirm(str(root), ticket, session=SESSION)

    assert (got["ok"], "could not be read" in got["reason"]) == (False, True)


def test_confirm_refuses_empty_turn_id(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    _turn(root, "")

    assert crew_split.confirm(str(root), ticket, session=SESSION)["ok"] is False


def test_confirm_refuses_when_check_saw_no_turn(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _staged(root, ticket)
    assert crew_split.check(str(root), ticket, session=SESSION) == ("split", [])
    _turn(root, "turn-2")

    got = crew_split.confirm(str(root), ticket, session=SESSION)

    assert (got["ok"], "check recorded no turn" in got["reason"]) == (False, True)


def test_confirm_refuses_edited_proposal(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    path = root / ".work" / "tickets" / ticket / "split.md"
    path.write_text(path.read_text(encoding="utf-8") + "- one more line\n", encoding="utf-8")

    got = crew_split.confirm(str(root), ticket, session=SESSION)

    assert (got["ok"], "changed since check" in got["reason"]) == (False, True)


def test_confirm_refuses_without_check(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _staged(root, ticket)
    _turn(root, "turn-2")

    got = crew_split.confirm(str(root), ticket, session=SESSION)

    assert (got["ok"], "no passing check" in got["reason"]) == (False, True)


def test_confirm_refuses_other_session(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    _turn(root, "turn-9", session="sess-other")

    got = crew_split.confirm(str(root), ticket, session="sess-other")

    assert (got["ok"], "another session" in got["reason"]) == (False, True)


def test_failed_check_writes_no_record(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _turn(root, "turn-1")
    _staged(root, ticket, _t0004_proposal(drop=_criteria()[8]))

    decision, problems = crew_split.check(str(root), ticket, session=SESSION)

    assert (decision, len(problems), os.path.exists(crew_split.check_record_path(str(root), ticket))
            ) == ("split", 1, False)


def _spec_bytes(root, ticket):
    return (root / ".work" / "tickets" / ticket / "spec.md").read_bytes()


def test_apply_via_command_files_mode_mints_children(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    before = _spec_bytes(root, ticket)
    _checked(root, ticket)

    got = crew_split.apply(str(root), ticket, "command", session=SESSION)

    kids = got["children"]
    assert len(kids) == 3
    spec = _spec_bytes(root, ticket).decode("utf-8").splitlines()
    assert re.search(r"status: superseded(\s|$)", spec[0]), spec[0]
    assert spec[1] == "split-into: " + ", ".join(kids)
    assert _index_status(root, ticket) == "superseded"
    pre = root / ".work" / "tickets" / ticket / "spec.pre-split.md"
    assert pre.read_bytes() == before
    crit = _criteria()
    for kid, items in zip(kids, (crit[4:7], crit[7:10], crit[10:11])):
        direction = (root / ".work" / "tickets" / kid / "direction.md").read_text(encoding="utf-8")
        assert f"origin: split of {ticket}" in direction
        assert f".work/tickets/{ticket}/spec.pre-split.md" in direction
        assert all(f"- {c}" in direction for c in items)
        assert "- next/resume, which stays on T-0004" in direction
        assert _index_status(root, kid) == "ready"
    minted = (root / ".work" / "tickets" / ticket / "split.md").read_text(encoding="utf-8")
    assert all(f"- Child {n}: {kid}" in minted for n, kid in enumerate(kids, 1))


def test_apply_cli_prints_children(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    env = dict(os.environ, **{crew_split.SESSION_ENV: SESSION})

    run = subprocess.run([sys.executable, SCRIPT, "apply", "--root", str(root), "--ticket", ticket,
                          "--via", "command"], capture_output=True, text=True, env=env,
                         check=False)

    assert run.returncode == 0, run.stdout + run.stderr
    assert len(re.findall(r"^child=T-\d{4}$", run.stdout, re.M)) == 3, run.stdout
    assert f"parent={ticket} status=superseded" in run.stdout


def test_apply_via_command_obsidian_mode(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = make_repo(tmp_path)
    (root / ".crew" / "crew.json").write_text(json.dumps({"tracker": {
        "kind": "obsidian", "obsidian": {"vaultPath": str(vault), "boardDir": "Boards/repo",
                                         "board": "Board.md"}}}), encoding="utf-8")
    (root / ".work" / "INDEX.md").write_text("T-0059 | done | - | r | old\n", encoding="utf-8")
    ticket = _parent(root)
    _checked(root, ticket)

    got = crew_split.apply(str(root), ticket, "command", session=SESSION)

    board = (vault / "Boards" / "repo" / "Board.md").read_text(encoding="utf-8")
    assert len(got["children"]) == 3
    assert all(_index_status(root, kid) == "ready" for kid in got["children"])
    assert _index_status(root, ticket) == "superseded"
    assert _lane_of(board, ticket) == "Done"


def test_pre_split_byte_identical(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    spec = root / ".work" / "tickets" / ticket / "spec.md"
    spec.write_bytes(spec.read_bytes().replace(b"\n", b"\r\n") + b"\xef\xbb\xbftrailing")
    before = spec.read_bytes()
    _checked(root, ticket)

    crew_split.apply(str(root), ticket, "command", session=SESSION)

    assert (root / ".work" / "tickets" / ticket / "spec.pre-split.md").read_bytes() == before


@pytest.mark.parametrize("tracker,word", [("sdp", "service desk"), ("jira", "MCP")])
def test_apply_refuses_tracker(tmp_path, tracker, word):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    (root / ".crew" / "config.json").write_text(json.dumps({"tracker": tracker}),
                                                encoding="utf-8")

    with pytest.raises(crew_split.SplitError, match=word):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    assert not (root / ".work" / "tickets" / ticket / "spec.pre-split.md").exists()


def test_apply_refuses_sdp(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    (root / ".crew" / "config.json").write_text(json.dumps({"tracker": "sdp"}), encoding="utf-8")
    minted = []
    monkeypatch.setattr(crew_ticket, "mint", lambda *a, **k: minted.append(a))

    with pytest.raises(crew_split.SplitError, match=crew_split.SDP_STOP):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    assert (minted, (root / ".work" / "tickets" / ticket / "spec.pre-split.md").exists()) == (
        [], False)


def test_apply_refuses_jira(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    (root / ".crew" / "config.json").write_text(json.dumps({"tracker": "jira"}), encoding="utf-8")

    with pytest.raises(crew_split.SplitError, match="jira"):
        crew_split.apply(str(root), ticket, "command", session=SESSION)


def test_apply_refuses_unknown_tracker(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    (root / ".crew" / "config.json").write_text("{torn", encoding="utf-8")

    with pytest.raises(crew_split.SplitError, match="could not be told"):
        crew_split.apply(str(root), ticket, "command", session=SESSION)


def test_apply_refuses_via_other_than_command(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)

    with pytest.raises(crew_split.SplitError, match="via robot is not one of command|autopilot"):
        crew_split.apply(str(root), ticket, "robot", session=SESSION)


def test_apply_refuses_when_confirm_refuses(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    _turn(root, "turn-1")

    with pytest.raises(crew_split.SplitError, match="confirm refused"):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    assert not (root / ".work" / "tickets" / ticket / "spec.pre-split.md").exists()


def test_apply_refuses_failing_proposal(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    _staged(root, ticket, _t0004_proposal(drop=_criteria()[8]))

    with pytest.raises(crew_split.SplitError, match="not placed"):
        crew_split.apply(str(root), ticket, "command", session=SESSION)


def test_apply_refuses_not_too_big(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _turn(root, "turn-1")
    _staged(root, ticket, "# x split          decision: not-too-big\n\n## Evidence\n"
                          "- acceptance-count: fine\n")
    assert crew_split.check(str(root), ticket, session=SESSION)[1] == []
    _turn(root, "turn-2")

    with pytest.raises(crew_split.SplitError, match="decision is not-too-big"):
        crew_split.apply(str(root), ticket, "command", session=SESSION)


def test_apply_refuses_existing_different_pre_split(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    (root / ".work" / "tickets" / ticket / "spec.pre-split.md").write_text("other\n",
                                                                          encoding="utf-8")

    with pytest.raises(crew_split.SplitError, match="differs"):
        crew_split.apply(str(root), ticket, "command", session=SESSION)


def test_apply_refuses_already_superseded(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    crew_split.apply(str(root), ticket, "command", session=SESSION)
    _turn(root, "turn-3")

    with pytest.raises(crew_split.SplitError, match="already superseded"):
        crew_split.apply(str(root), ticket, "command", session=SESSION)


def test_pre_split_written_before_first_mint(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    real, seen = crew_ticket.mint, []
    pre = root / ".work" / "tickets" / ticket / "spec.pre-split.md"

    def spy(*args, **kwargs):
        seen.append(pre.exists())
        return real(*args, **kwargs)

    monkeypatch.setattr(crew_ticket, "mint", spy)
    crew_split.apply(str(root), ticket, "command", session=SESSION)

    assert seen == [True, True, True]


def test_mint_failure_leaves_parent_status(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    before = _spec_bytes(root, ticket)
    _checked(root, ticket)
    real, calls = crew_ticket.mint, []

    def flaky(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise crew_ticket.TicketError("disk full")
        return real(*args, **kwargs)

    monkeypatch.setattr(crew_ticket, "mint", flaky)
    with pytest.raises(crew_split.SplitError) as raised:
        crew_split.apply(str(root), ticket, "command", session=SESSION)

    message = str(raised.value)
    assert "disk full" in message and "minted: Child 1" in message
    assert "not minted: Child 2, Child 3" in message
    assert _spec_bytes(root, ticket) == before
    assert _index_status(root, ticket) == "spec"


def test_rerun_after_mint_failure_skips_minted_children(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    real, calls = crew_ticket.mint, []

    def flaky(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise crew_ticket.TicketError("disk full")
        return real(*args, **kwargs)

    monkeypatch.setattr(crew_ticket, "mint", flaky)
    with pytest.raises(crew_split.SplitError):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    _turn(root, "turn-3")
    assert crew_split.check(str(root), ticket, session=SESSION)[1] == []
    _turn(root, "turn-4")
    got = crew_split.apply(str(root), ticket, "command", session=SESSION)

    assert (len(calls), len(got["children"]), len(set(got["children"]))) == (4, 3, 3)


# --- /crew:split's prose ------------------------------------------------------------

def _command():
    with open(COMMAND, encoding="utf-8") as handle:
        return handle.read()


def _frontmatter(text):
    return text.split("---", 2)[1]


def test_split_command_model_invocable():
    assert "disable-model-invocation" not in _frontmatter(_command())


def test_split_command_description_not_jira_only():
    front = _frontmatter(_command())
    assert "Jira" not in re.search(r"^description:(.*)$", front, re.M).group(1)
    assert "argument-hint: <ticket-id-or-ISSUE-KEY> [--dry-run]" in front


def test_split_command_runs_confirm_before_create():
    text = _command()
    confirm = text.index("crew_split.py confirm --root . --ticket <KEY>")
    create = text.index("Create each child")
    assert confirm < create


def test_split_command_names_rulebook_check():
    text = _command()
    assert "crew_split.py check --root . --ticket <id>" in text
    assert "crew_split.py apply --root . --ticket <id> --via command" in text
    assert "HEALTHY_HIGH" not in text  # the evidence table is the rulebook's now


def test_split_command_no_jira_only_precondition():
    assert "Jira only, on purpose" not in _command()


def test_split_command_sdp_stops():
    text = _command()
    assert crew_split.SDP_STOP in text


def test_split_command_stops_under_autopilot():
    assert "/crew:autopilot split <id>" in _command()


def test_split_command_keeps_jira_steps():
    text = _command()
    for line in ("Prefer real sub-tasks", "Comment once on the parent",
                 ".work/cache/<KEY>.md", "Never fall back to files mode",
                 "Do not transition the parent", "jira.cloudId"):
        assert line in text, line


def test_check_record_holds_sha_and_turn(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _turn(root, "turn-1")
    path = _staged(root, ticket)
    crew_split.check(str(root), ticket, session=SESSION)

    with open(crew_split.check_record_path(str(root), ticket), encoding="utf-8") as handle:
        record = json.load(handle)

    assert (record["proposal_sha256"], record["turn"], record["session"]) == (
        hashlib.sha256(path.read_bytes().rstrip()).hexdigest(), "turn-1", SESSION)


# --- review round 1 (#364 at e3a572c6) ----------------------------------------------

def _turn_prompt(root, turn_id, prompt, session=SESSION):
    _turn(root, turn_id, session=session, prompt=prompt)


def test_minted_heading_early_does_not_hide_an_edit(tmp_path):
    """BLOCK 1: a `## Minted` heading before `## Evidence` must not take the
    rest of the proposal out of the hash (or past check)."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _turn(root, "turn-1")
    text = _t0004_proposal().replace("## Evidence", "## Minted\n## Evidence", 1)
    _staged(root, ticket, text)

    decision, problems = crew_split.check(str(root), ticket, session=SESSION)

    assert problems and any("## Minted" in p for p in problems), (decision, problems)


def test_proposal_sha_covers_everything_but_a_trailing_minted_block():
    base = _t0004_proposal().encode("utf-8")
    trailing = base + b"\n## Minted\n- Child 1: T-0061\n"
    tampered = base.replace(b"Excludes:", b"Excludes:\n- tampered", 1) + b"\n## Minted\n"
    early = base.replace(b"## Evidence", b"## Minted\n## Evidence", 1)
    sha = crew_split._proposal_sha  # pylint: disable=protected-access

    assert sha(trailing) == sha(base)
    assert sha(tampered) != sha(base)
    assert sha(early) != sha(base)
    assert sha(base + b"\n## Minted\n- Child 1: T-0061\n- tampered\n") != sha(base)


def test_preseeded_minted_refused(tmp_path, monkeypatch):
    """BLOCK 2: a `## Minted` section before any apply (no apply record) is
    refused by check and by apply -- even naming a folder that carries this
    split's provenance -- and nothing is minted or superseded."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    before = _spec_bytes(root, ticket)
    fake = root / ".work" / "tickets" / "T-0050"
    fake.mkdir()
    (fake / "direction.md").write_text(f"# T-0050 direction\norigin: split of {ticket}\n"
                                       "split-child: 1\n", encoding="utf-8")
    _turn(root, "turn-1")
    _staged(root, ticket, _t0004_proposal() + "\n## Minted\n- Child 1: T-0050\n")
    _, problems = crew_split.check(str(root), ticket, session=SESSION)
    _turn(root, "turn-2")
    minted = []
    monkeypatch.setattr(crew_ticket, "mint", lambda *a, **k: minted.append(a))

    assert any("no apply has run" in p for p in problems), problems
    with pytest.raises(crew_split.SplitError, match="no apply has run"):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    assert (minted, _spec_bytes(root, ticket), _index_status(root, ticket)) == (
        [], before, "spec")


def test_preseeded_minted_without_provenance_refused(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _turn(root, "turn-1")
    _staged(root, ticket, _t0004_proposal() + "\n## Minted\n- Child 1: T-9999\n")
    crew_split.check(str(root), ticket, session=SESSION)
    _turn(root, "turn-2")

    with pytest.raises(crew_split.SplitError, match="Minted"):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    assert _index_status(root, ticket) == "spec"


def test_minted_entry_without_provenance_refused(tmp_path, monkeypatch):
    """BLOCK 2: after a failed apply, a hand-edited Minted entry naming a
    ticket that is not this split's child is refused."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    real, calls = crew_ticket.mint, []

    def flaky(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise crew_ticket.TicketError("disk full")
        return real(*args, **kwargs)

    monkeypatch.setattr(crew_ticket, "mint", flaky)
    with pytest.raises(crew_split.SplitError):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    path = root / ".work" / "tickets" / ticket / "split.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r"- Child 1: T-\d+", f"- Child 1: {ticket}", text), encoding="utf-8")
    _turn(root, "turn-3")
    crew_split.check(str(root), ticket, session=SESSION)
    _turn(root, "turn-4")

    with pytest.raises(crew_split.SplitError, match="provenance"):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    assert _index_status(root, ticket) == "spec"


def test_crash_between_mint_and_record_adopts_orphan(tmp_path, monkeypatch):
    """FIX 4: a child minted whose id never reached split.md is found by its
    provenance on re-run, not minted twice."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    real_record, calls = crew_split._record_minted, []  # pylint: disable=protected-access

    def crash(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise OSError("killed")
        return real_record(*args, **kwargs)

    monkeypatch.setattr(crew_split, "_record_minted", crash)
    with pytest.raises((crew_split.SplitError, OSError)):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    monkeypatch.setattr(crew_split, "_record_minted", real_record)
    _turn(root, "turn-3")
    crew_split.check(str(root), ticket, session=SESSION)
    _turn(root, "turn-4")
    got = crew_split.apply(str(root), ticket, "command", session=SESSION)

    children = [n for n in os.listdir(root / ".work" / "tickets") if n != ticket]
    assert (len(got["children"]), sorted(children)) == (3, sorted(got["children"]))


def test_non_utf8_spec_refused_before_any_mint(tmp_path, monkeypatch):
    """FIX 4: the spec is decoded strictly before the first mint."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    spec = root / ".work" / "tickets" / ticket / "spec.md"
    spec.write_bytes(spec.read_bytes() + b"\nbad byte \xff\n")
    _checked(root, ticket)
    minted = []
    monkeypatch.setattr(crew_ticket, "mint", lambda *a, **k: minted.append(a))

    with pytest.raises(crew_split.SplitError, match="UTF-8"):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    assert minted == []


@pytest.mark.parametrize("prompt", [
    "<task-notification><task-id>b1</task-id> done</task-notification>",
    "<wake reason=\"external-event\"> ci failed </wake>",
    "<webhook-payload>{}</webhook-payload>",
])
def test_confirm_refuses_machine_prompt(tmp_path, prompt):
    """BLOCK 3: a turn id moved by a task notification, wake or webhook is
    not a human's yes."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _turn_prompt(root, "turn-1", "/crew:split T-1")
    _staged(root, ticket)
    crew_split.check(str(root), ticket, session=SESSION)
    _turn_prompt(root, "turn-2", prompt)

    got = crew_split.confirm(str(root), ticket, session=SESSION)

    assert (got["ok"], "not a human" in got["reason"]) == (False, True), got


def test_confirm_refuses_repeated_prompt(tmp_path):
    """BLOCK 3: a loop re-sending the prompt check ran under is not a yes."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _turn_prompt(root, "turn-1", "split T-1 please")
    _staged(root, ticket)
    crew_split.check(str(root), ticket, session=SESSION)
    _turn_prompt(root, "turn-2", "split T-1 please")

    got = crew_split.confirm(str(root), ticket, session=SESSION)

    assert (got["ok"], "typed the same words" in got["reason"]) == (False, True), got


def test_confirm_refuses_unknown_prompt(tmp_path):
    """BLOCK 3: a turn record with no lastPrompt cannot tell who moved it."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    _turn(root, "turn-3", prompt=None)

    got = crew_split.confirm(str(root), ticket, session=SESSION)

    assert (got["ok"], "cannot tell" in got["reason"]) == (False, True), got


def test_confirm_allows_typed_yes(tmp_path):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _turn_prompt(root, "turn-1", "/crew:split T-1")
    _staged(root, ticket)
    crew_split.check(str(root), ticket, session=SESSION)
    _turn_prompt(root, "turn-2", "yes, go")

    assert crew_split.confirm(str(root), ticket, session=SESSION)["ok"] is True


def test_acceptance_without_checkboxes_is_none(tmp_path):
    """FIX 1: a readable section that yields no items is unknown, not 0."""
    root = make_repo(tmp_path)
    _ticket(root, "T-0001", "# T-0001 x\n## Acceptance checks\n- one\n- two\n## Touch\n- `a`\n",
            "# plan\nno steps\n")

    got = crew_split.measure(str(root), "T-0001")

    assert (got["acceptance"], got["plan_steps"]) == (None, None)
    assert {"unknown:acceptance-count", "unknown:plan-steps"} <= set(
        crew_split.triggers(got, "plan"))


def test_unmatched_touch_entry_makes_subsystems_none(tmp_path):
    """FIX 2: a Touch entry no codemap subsystem covers is unknown, not 0."""
    root = make_repo(tmp_path)
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("x\n", encoding="utf-8")
    _codemap(root, {"code": "src/"})
    _ticket(root, "T-0001", "# T-0001 x\n## Touch\n- `src/a.py`\n- `nowhere/b.py`\n"
                            "## Acceptance checks\n- [ ] a\n")

    assert crew_split.measure(str(root), "T-0001")["subsystems"] is None


def test_check_record_removed_after_apply(tmp_path):
    """NIT: a successful apply spends the yes."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)

    crew_split.apply(str(root), ticket, "command", session=SESSION)

    assert not os.path.exists(crew_split.check_record_path(str(root), ticket))


def test_failed_mint_invalidates_check(tmp_path, monkeypatch):
    """NIT: after a failed mint a re-run needs a fresh check and yes."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    monkeypatch.setattr(crew_ticket, "mint", lambda *a, **k: (_ for _ in ()).throw(
        crew_ticket.TicketError("disk full")))

    with pytest.raises(crew_split.SplitError):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    assert not os.path.exists(crew_split.check_record_path(str(root), ticket))


def test_minted_record_keeps_crlf(tmp_path, monkeypatch):
    """NIT: a CRLF split.md stays CRLF when apply records a child."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _turn(root, "turn-1")
    path = _staged(root, ticket)
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert crew_split.check(str(root), ticket, session=SESSION)[1] == []
    _turn(root, "turn-2")

    crew_split.apply(str(root), ticket, "command", session=SESSION)

    data = path.read_bytes()
    assert b"\n" not in data.replace(b"\r\n", b""), data[-80:]


# --- review round 2 (#364 at 687d1edd) ----------------------------------------------

def _fail_second_mint(monkeypatch):
    real, calls = crew_ticket.mint, []

    def flaky(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise crew_ticket.TicketError("disk full")
        return real(*args, **kwargs)

    monkeypatch.setattr(crew_ticket, "mint", flaky)
    return real


def test_minted_child_from_an_edited_proposal_refused(tmp_path, monkeypatch):
    """BLOCK: after a failed apply, an edited proposal that swaps children
    must not reuse Child 1's ticket (minted with the OLD criteria)."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    real = _fail_second_mint(monkeypatch)
    with pytest.raises(crew_split.SplitError):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    monkeypatch.setattr(crew_ticket, "mint", real)
    crit = _criteria()
    swapped = _t0004_proposal(children=[
        ("autopilot ship policy", "high", crit[7:10]),
        ("autopilot approval and question policies", "high", crit[4:7]),
        ("autopilot goal: tickets from a goal file", "med", crit[10:11])])
    path = root / ".work" / "tickets" / ticket / "split.md"
    old = path.read_text(encoding="utf-8")
    path.write_text(swapped + "\n" + old[old.index("## Minted"):], encoding="utf-8")
    _turn(root, "turn-3")
    assert crew_split.check(str(root), ticket, session=SESSION)[1] == []
    _turn(root, "turn-4")
    before = sorted(os.listdir(root / ".work" / "tickets"))

    with pytest.raises(crew_split.SplitError, match="different proposal"):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    assert sorted(os.listdir(root / ".work" / "tickets")) == before
    assert _index_status(root, ticket) == "spec"


def test_stale_orphan_from_an_edited_proposal_refused(tmp_path, monkeypatch):
    """BLOCK: an orphan (minted, id never recorded) whose direction no longer
    matches the current Child N is refused, never adopted or duplicated."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    real_record = crew_split._record_minted  # pylint: disable=protected-access
    monkeypatch.setattr(crew_split, "_record_minted",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("killed")))
    with pytest.raises((crew_split.SplitError, OSError)):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    monkeypatch.setattr(crew_split, "_record_minted", real_record)
    path = root / ".work" / "tickets" / ticket / "split.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "- next/resume, which stays on T-0004", "- next/resume, kept on the parent", 1),
        encoding="utf-8")
    _turn(root, "turn-3")
    assert crew_split.check(str(root), ticket, session=SESSION)[1] == []
    _turn(root, "turn-4")
    before = sorted(os.listdir(root / ".work" / "tickets"))

    with pytest.raises(crew_split.SplitError, match="different proposal"):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    assert sorted(os.listdir(root / ".work" / "tickets")) == before


def test_forged_orphan_without_apply_record_ignored(tmp_path):
    """FIX 2: a hand-made folder with apply's exact direction and an INDEX
    row, but no apply record, is never adopted as a child."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    child = (crew_split.parse_proposal(_t0004_proposal())["children"] or [])[0]
    fake = root / ".work" / "tickets" / "T-0077"
    fake.mkdir()
    (fake / "direction.md").write_text(  # exact provenance and direction, and a row
        "# T-0077 direction\n" + crew_split._direction(ticket, child),  # pylint: disable=protected-access
        encoding="utf-8")
    with open(root / ".work" / "INDEX.md", "a", encoding="utf-8") as handle:
        handle.write("T-0077 | ready | - | r | forged\n")

    got = crew_split.apply(str(root), ticket, "command", session=SESSION)

    assert "T-0077" not in got["children"]


def test_orphan_without_index_row_not_adopted(tmp_path, monkeypatch):
    """FIX 2: even with an apply record and a matching direction, a folder
    with no INDEX row (mint never finished) is not a child."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    _fail_second_mint(monkeypatch)
    with pytest.raises(crew_split.SplitError):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    proposal = crew_split.parse_proposal(
        (root / ".work" / "tickets" / ticket / "split.md").read_text(encoding="utf-8"))
    child = (proposal["children"] or [])[1]
    fake = root / ".work" / "tickets" / "T-0080"
    fake.mkdir()
    (fake / "direction.md").write_text(
        "# T-0080 direction\n" + crew_split._direction(ticket, child),  # pylint: disable=protected-access
        encoding="utf-8")

    monkeypatch.undo()
    _turn(root, "turn-3")
    assert crew_split.check(str(root), ticket, session=SESSION)[1] == []
    _turn(root, "turn-4")

    got = crew_split.apply(str(root), ticket, "command", session=SESSION)

    assert "T-0080" not in got["children"] and len(set(got["children"])) == 3


def test_repeated_prompt_reason_names_typed_words():
    """NIT 1: the refusal says the owner may have typed the same words and
    that only the first 500 characters are compared."""
    with open(SCRIPT, encoding="utf-8") as handle:
        text = handle.read()
    assert "typed the same words" in text and "first 500 characters" in text


# --- review round 3 (#364 at 91ec7d6c) ----------------------------------------------

def _partial_then_swap(root, ticket, monkeypatch, keep_minted):
    """Apply fails after Child 1 is minted; the owner then swaps the
    children (Child 1 now takes the ship criteria). Returns Child 1's id."""
    _checked(root, ticket)
    real = _fail_second_mint(monkeypatch)
    with pytest.raises(crew_split.SplitError):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    monkeypatch.setattr(crew_ticket, "mint", real)
    path = root / ".work" / "tickets" / ticket / "split.md"
    old = path.read_text(encoding="utf-8")
    first = re.search(r"- Child 1: (T-\d+)", old).group(1)
    crit = _criteria()
    swapped = _t0004_proposal(children=[
        ("autopilot ship policy", "high", crit[7:10]),
        ("autopilot approval and question policies", "high", crit[4:7]),
        ("autopilot goal: tickets from a goal file", "med", crit[10:11])])
    path.write_text(swapped + ("\n" + old[old.index("## Minted"):] if keep_minted else ""),
                    encoding="utf-8")
    return first


def _recheck(root, ticket, turn):
    _turn(root, f"{turn}-a")
    assert crew_split.check(str(root), ticket, session=SESSION)[1] == []
    _turn(root, f"{turn}-b")


@pytest.mark.parametrize("keep_minted", [False, True])
def test_stale_child_refusal_names_the_exits_and_cancel_unblocks(tmp_path, monkeypatch,
                                                                 keep_minted):
    """FIX 1: a stale child is refused naming how to get out (restore it, or
    cancel it), and once it is cancelled apply proceeds with a fresh child."""
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    stale = _partial_then_swap(root, ticket, monkeypatch, keep_minted)
    _recheck(root, ticket, "t3")

    with pytest.raises(crew_split.SplitError) as raised:
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    assert "--to cancelled" in str(raised.value) and "restore" in str(raised.value)

    report = crew_tracker.move(str(root), stale, "cancelled")
    assert crew_tracker.exit_code(report) == 0, report
    _recheck(root, ticket, "t5")
    got = crew_split.apply(str(root), ticket, "command", session=SESSION)

    assert stale not in got["children"] and len(set(got["children"])) == 3
    assert _index_status(root, ticket) == "superseded"
    tail = crew_split.minted_tail(
        (root / ".work" / "tickets" / ticket / "split.md").read_text(encoding="utf-8"))[1]
    assert tail == dict(enumerate(got["children"], 1))


def test_superseded_child_is_not_reused(tmp_path, monkeypatch):
    root = _files_repo(tmp_path)
    ticket = _parent(root)
    _checked(root, ticket)
    real = _fail_second_mint(monkeypatch)
    with pytest.raises(crew_split.SplitError):
        crew_split.apply(str(root), ticket, "command", session=SESSION)
    monkeypatch.setattr(crew_ticket, "mint", real)
    first = re.search(r"- Child 1: (T-\d+)", (root / ".work" / "tickets" / ticket /
                                              "split.md").read_text(encoding="utf-8")).group(1)
    assert crew_tracker.exit_code(crew_tracker.move(str(root), first, "superseded")) == 0
    _recheck(root, ticket, "t3")

    got = crew_split.apply(str(root), ticket, "command", session=SESSION)

    assert first not in got["children"]


# --- T-0058: the ticket split policy and apply --via autopilot ----------------------
#
# `ticket_split_policy` is T-0012's split rule (crew_autopilot_goal._split_rule)
# applied to the parent's spec risk, refused outright in jira and sdp mode.
# `apply --via autopilot` asks it at apply time and needs no human turn;
# `--via command` needs no policy.

def _policy_repo(tmp_path, approval="self", allow=True, mode="plan", tracker="files",
                 risk="high"):
    root = make_repo(tmp_path)
    config = {"tracker": tracker, "autopilot": {"mode": mode, "approval": approval}}
    if allow is not None:
        config["scope"] = {"allowCliApproval": allow}
    (root / ".crew" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    ticket = _parent(root) if tracker in ("files", "obsidian") else None
    if ticket and risk != "high":
        spec = root / ".work" / "tickets" / ticket / "spec.md"
        text = spec.read_text(encoding="utf-8")
        spec.write_text(text.replace("risk: high", risk, 1), encoding="utf-8", newline="\n")
    _staged(root, ticket)
    return root, ticket


def _set_config(root, **changes):
    path = root / ".crew" / "config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if key == "approval":
            config["autopilot"]["approval"] = value
        else:
            config[key] = value
    path.write_text(json.dumps(config), encoding="utf-8")


def test_policy_refuses_jira_even_under_self(tmp_path):
    root, ticket = _policy_repo(tmp_path)
    _set_config(root, tracker="jira")

    got = crew_split.ticket_split_policy(str(root), ticket)

    assert (got["allow"], "/crew:split <KEY>" in got["reason"]) == (False, True), got


def test_policy_refuses_sdp(tmp_path):
    root, ticket = _policy_repo(tmp_path)
    _set_config(root, tracker="sdp")

    got = crew_split.ticket_split_policy(str(root), ticket)

    assert (got["allow"], crew_split.SDP_STOP in got["reason"]) == (False, True), got


def test_policy_refuses_unknown_tracker(tmp_path):
    root, ticket = _policy_repo(tmp_path)
    (root / ".crew" / "crew.json").write_text("{torn", encoding="utf-8")

    got = crew_split.ticket_split_policy(str(root), ticket)

    assert got["allow"] is False, got


def test_policy_refuses_human(tmp_path):
    root, ticket = _policy_repo(tmp_path, approval="human", risk="risk: low")

    got = crew_split.ticket_split_policy(str(root), ticket)

    assert (got["allow"], got["policy"], "owner" in got["reason"]) == (False, "human", True)


@pytest.mark.parametrize("risk", ["risk: med", "risk: high", "risk: maybe", ""])
def test_policy_refuses_risk_not_low(tmp_path, risk):
    root, ticket = _policy_repo(tmp_path, approval="risk", risk=risk)

    got = crew_split.ticket_split_policy(str(root), ticket)

    assert (got["allow"], got["policy"]) == (False, "risk"), got
    assert got["risk"] != "low" or got["known"] is False, got


@pytest.mark.parametrize("allow", [None, False, "true", 1])
def test_policy_refuses_without_allow_cli_approval(tmp_path, allow):
    root, ticket = _policy_repo(tmp_path, allow=allow)

    got = crew_split.ticket_split_policy(str(root), ticket)

    assert (got["allow"], "allowCliApproval" in got["reason"]) == (False, True), got


@pytest.mark.parametrize("mode", ["off", "Plan", None])
def test_policy_refuses_unarmed(tmp_path, mode):
    root, ticket = _policy_repo(tmp_path, mode=mode)

    got = crew_split.ticket_split_policy(str(root), ticket)

    assert (got["allow"], "not armed" in got["reason"]) == (False, True), got


def test_policy_allows_self_any_risk(tmp_path):
    root, ticket = _policy_repo(tmp_path)

    got = crew_split.ticket_split_policy(str(root), ticket)

    assert (got["allow"], got["policy"], got["risk"]) == (True, "self", "high"), got


def test_policy_allows_risk_low(tmp_path):
    root, ticket = _policy_repo(tmp_path, approval="risk", risk="risk: low")

    got = crew_split.ticket_split_policy(str(root), ticket)

    assert (got["allow"], got["risk"], got["known"]) == (True, "low", True), got


def test_policy_reasked_at_apply(tmp_path):
    root, ticket = _policy_repo(tmp_path)
    assert crew_split.check(str(root), ticket)[1] == []
    assert crew_split.ticket_split_policy(str(root), ticket)["allow"] is True
    _set_config(root, approval="human")

    with pytest.raises(crew_split.SplitError, match="autopilot.approval is human"):
        crew_split.apply(str(root), ticket, "autopilot")
    assert not (root / ".work" / "tickets" / ticket / "spec.pre-split.md").exists()
    assert _index_status(root, ticket) == "spec"


def test_apply_via_autopilot_refuses_jira_before_anything(tmp_path, monkeypatch):
    root, ticket = _policy_repo(tmp_path)
    _set_config(root, tracker="jira")
    minted = []
    monkeypatch.setattr(crew_ticket, "mint", lambda *a, **k: minted.append(a))

    with pytest.raises(crew_split.SplitError, match="/crew:split <KEY>"):
        crew_split.apply(str(root), ticket, "autopilot")
    assert minted == []


def test_apply_self_files_mode_mints_children(tmp_path):
    root, ticket = _policy_repo(tmp_path)
    before = _spec_bytes(root, ticket)

    got = crew_split.apply(str(root), ticket, "autopilot")

    kids = got["children"]
    assert len(kids) == 3
    spec = _spec_bytes(root, ticket).decode("utf-8").splitlines()
    assert re.search(r"status: superseded(\s|$)", spec[0]), spec[0]
    assert spec[1] == "split-into: " + ", ".join(kids)
    assert _index_status(root, ticket) == "superseded"
    assert (root / ".work" / "tickets" / ticket / "spec.pre-split.md").read_bytes() == before
    crit = _criteria()
    for kid, items in zip(kids, (crit[4:7], crit[7:10], crit[10:11])):
        direction = (root / ".work" / "tickets" / kid / "direction.md").read_text(encoding="utf-8")
        assert all(f"- {c}" in direction for c in items)
        assert _index_status(root, kid) == "ready"


def test_apply_risk_low_obsidian_mode(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = make_repo(tmp_path)
    (root / ".crew" / "crew.json").write_text(json.dumps({"tracker": {
        "kind": "obsidian", "obsidian": {"vaultPath": str(vault), "boardDir": "Boards/repo",
                                         "board": "Board.md"}}}), encoding="utf-8")
    (root / ".crew" / "config.json").write_text(json.dumps({
        "autopilot": {"mode": "plan", "approval": "risk"},
        "scope": {"allowCliApproval": True}}), encoding="utf-8")
    (root / ".work" / "INDEX.md").write_text("T-0059 | done | - | r | old\n", encoding="utf-8")
    ticket = _parent(root)
    spec = root / ".work" / "tickets" / ticket / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace("risk: high", "risk: low", 1),
                    encoding="utf-8", newline="\n")
    _staged(root, ticket)

    got = crew_split.apply(str(root), ticket, "autopilot")

    board = (vault / "Boards" / "repo" / "Board.md").read_text(encoding="utf-8")
    assert len(got["children"]) == 3
    assert all(_index_status(root, kid) == "ready" for kid in got["children"])
    assert (_index_status(root, ticket), _lane_of(board, ticket)) == ("superseded", "Done")


def test_apply_via_command_needs_no_policy(tmp_path):
    root, ticket = _policy_repo(tmp_path, approval="human", allow=None, mode="off")
    _checked(root, ticket)

    got = crew_split.apply(str(root), ticket, "command", session=SESSION)

    assert len(got["children"]) == 3


def test_apply_via_autopilot_needs_no_human_turn(tmp_path, monkeypatch):
    root, ticket = _policy_repo(tmp_path)
    monkeypatch.delenv(crew_split.SESSION_ENV, raising=False)
    monkeypatch.setattr(crew_split, "confirm", lambda *a, **k: {"ok": False, "reason": "x"})

    assert len(crew_split.apply(str(root), ticket, "autopilot")["children"]) == 3


def test_apply_cli_via_autopilot_refused_names_crew_split(tmp_path):
    root, ticket = _policy_repo(tmp_path, approval="human")

    run = subprocess.run([sys.executable, SCRIPT, "apply", "--root", str(root), "--ticket", ticket,
                          "--via", "autopilot"], capture_output=True, text=True, check=False)

    assert run.returncode == 1, run.stdout + run.stderr
    assert "refused:" in run.stdout and "autopilot.approval is human" in run.stdout


def test_split_policy_for_goals_unchanged_by_the_factored_rule():
    """T-0012's goal split_policy and the ticket policy share one rule."""
    import crew_autopilot_goal  # pylint: disable=import-outside-toplevel
    assert callable(crew_autopilot_goal._split_rule)  # pylint: disable=protected-access


# --- T-0058 x T-0052 round 3: --via autopilot keeps the existing-children checks ----

def test_apply_via_autopilot_refuses_preseeded_minted(tmp_path, monkeypatch):
    root, ticket = _policy_repo(tmp_path)
    before = _spec_bytes(root, ticket)
    _staged(root, ticket, _t0004_proposal() + "\n## Minted\n- Child 1: T-9999\n")
    minted = []
    monkeypatch.setattr(crew_ticket, "mint", lambda *a, **k: minted.append(a))

    with pytest.raises(crew_split.SplitError, match="Minted|no apply has run"):
        crew_split.apply(str(root), ticket, "autopilot")
    assert (minted, _spec_bytes(root, ticket), _index_status(root, ticket)) == (
        [], before, "spec")


def test_apply_via_autopilot_refuses_minted_entry_without_provenance(tmp_path, monkeypatch):
    root, ticket = _policy_repo(tmp_path)
    real, calls = crew_ticket.mint, []

    def flaky(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise crew_ticket.TicketError("disk full")
        return real(*args, **kwargs)

    monkeypatch.setattr(crew_ticket, "mint", flaky)
    with pytest.raises(crew_split.SplitError):
        crew_split.apply(str(root), ticket, "autopilot")
    path = root / ".work" / "tickets" / ticket / "split.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r"- Child 1: T-\d+", f"- Child 1: {ticket}", text), encoding="utf-8")

    with pytest.raises(crew_split.SplitError, match="provenance"):
        crew_split.apply(str(root), ticket, "autopilot")
    assert _index_status(root, ticket) == "spec"


def test_apply_via_autopilot_rerun_skips_verified_children(tmp_path, monkeypatch):
    root, ticket = _policy_repo(tmp_path)
    real, calls = crew_ticket.mint, []

    def flaky(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise crew_ticket.TicketError("disk full")
        return real(*args, **kwargs)

    monkeypatch.setattr(crew_ticket, "mint", flaky)
    with pytest.raises(crew_split.SplitError):
        crew_split.apply(str(root), ticket, "autopilot")
    got = crew_split.apply(str(root), ticket, "autopilot")

    assert (len(calls), len(got["children"]), len(set(got["children"]))) == (4, 3, 3)


# --- #365 review of 20718c87 -------------------------------------------------------

def test_policy_crash_refuses_and_apply_writes_nothing(tmp_path, monkeypatch):
    """FIX 1: anything ticket_split_policy cannot read is could-not-tell, never allow."""
    import crew_autopilot  # pylint: disable=import-outside-toplevel
    root, ticket = _policy_repo(tmp_path)
    before = _spec_bytes(root, ticket)

    def boom(*_a, **_k):
        raise RuntimeError("settings unreadable")

    monkeypatch.setattr(crew_autopilot, "settings", boom)
    minted = []
    monkeypatch.setattr(crew_ticket, "mint", lambda *a, **k: minted.append(a))

    got = crew_split.ticket_split_policy(str(root), ticket)
    assert (got["allow"], "could not tell" in got["reason"]) == (False, True), got
    with pytest.raises(crew_split.SplitError, match="could not tell"):
        crew_split.apply(str(root), ticket, "autopilot")
    assert (minted, _spec_bytes(root, ticket), _index_status(root, ticket)) == (
        [], before, "spec")
    assert not (root / ".work" / "tickets" / ticket / "spec.pre-split.md").exists()


@pytest.mark.parametrize("target", ["_split_rule", "_ticket_risk"])
def test_policy_rule_crash_refuses_never_raises(tmp_path, monkeypatch, target):
    """NIT 2: the rule and the risk read sit inside the could-not-tell boundary."""
    # pylint: disable=import-outside-toplevel
    import crew_autopilot
    import crew_autopilot_goal
    root, ticket = _policy_repo(tmp_path)

    def boom(*_a, **_k):
        raise KeyError("approval")

    monkeypatch.setattr(crew_autopilot_goal if target == "_split_rule" else crew_autopilot,
                        target, boom)

    got = crew_split.ticket_split_policy(str(root), ticket)

    assert (got["allow"], "could not tell" in got["reason"]) == (False, True), got


def test_policy_with_a_settings_answer_missing_a_key_refuses(tmp_path, monkeypatch):
    import crew_autopilot  # pylint: disable=import-outside-toplevel
    root, ticket = _policy_repo(tmp_path)
    monkeypatch.setattr(crew_autopilot, "settings", lambda top: {"warnings": []})

    got = crew_split.ticket_split_policy(str(root), ticket)

    assert (got["allow"], "could not tell" in got["reason"]) == (False, True), got


def _swap_after_partial(root, ticket):
    path = root / ".work" / "tickets" / ticket / "split.md"
    old = path.read_text(encoding="utf-8")
    first = re.search(r"- Child 1: (T-\d+)", old).group(1)
    crit = _criteria()
    swapped = _t0004_proposal(children=[
        ("autopilot ship policy", "high", crit[7:10]),
        ("autopilot approval and question policies", "high", crit[4:7]),
        ("autopilot goal: tickets from a goal file", "med", crit[10:11])])
    path.write_text(swapped + "\n" + old[old.index("## Minted"):], encoding="utf-8")
    return first


def test_apply_via_autopilot_refuses_a_stale_child_from_an_edited_proposal(tmp_path,
                                                                           monkeypatch):
    """NIT 4 (T-0052 round 2 on the autopilot path): a child minted for an older
    proposal is refused, never reused, and nothing new is written."""
    root, ticket = _policy_repo(tmp_path)
    real = _fail_second_mint(monkeypatch)
    with pytest.raises(crew_split.SplitError):
        crew_split.apply(str(root), ticket, "autopilot")
    monkeypatch.setattr(crew_ticket, "mint", real)
    _swap_after_partial(root, ticket)
    before = sorted(os.listdir(root / ".work" / "tickets"))

    with pytest.raises(crew_split.SplitError, match="different proposal"):
        crew_split.apply(str(root), ticket, "autopilot")
    assert sorted(os.listdir(root / ".work" / "tickets")) == before
    assert _index_status(root, ticket) == "spec"


@pytest.mark.parametrize("closed", ["cancelled", "superseded"])
def test_apply_via_autopilot_remints_a_closed_child(tmp_path, monkeypatch, closed):
    """NIT 4 (T-0052 round 3 on the autopilot path): a cancelled or superseded
    child is re-minted, never reused."""
    root, ticket = _policy_repo(tmp_path)
    real = _fail_second_mint(monkeypatch)
    with pytest.raises(crew_split.SplitError):
        crew_split.apply(str(root), ticket, "autopilot")
    monkeypatch.setattr(crew_ticket, "mint", real)
    first = re.search(r"- Child 1: (T-\d+)", (root / ".work" / "tickets" / ticket /
                                              "split.md").read_text(encoding="utf-8")).group(1)
    assert crew_tracker.exit_code(crew_tracker.move(str(root), first, closed)) == 0

    got = crew_split.apply(str(root), ticket, "autopilot")

    assert first not in got["children"] and len(set(got["children"])) == 3
    assert _index_status(root, ticket) == "superseded"


# --- T-0059: the plan's `## PR slices` section (parse_slices) ------------------------

def _plan_with_slices(slices, files=None):
    """A five-step plan (step N touches `src/sN.py` unless `files` says
    otherwise) followed by `slices`, the `## PR slices` body verbatim."""
    files = files or {}
    steps = "".join(f"### Step {n}: step {n}\nFiles: {files.get(n, f'src/s{n}.py')}\n"
                    f"Test: pytest\nRisk: low\n- [ ] do {n}\n\n" for n in range(1, 6))
    tail = f"## PR slices\n\n{slices}" if slices is not None else ""
    return f"# T-1 plan\n\n{steps}{tail}"


def _slice(n, steps, base="main", name=None):
    return f"### Slice {n}: {name or f'part {n}'}\nSteps: {steps}\nBase: {base}\n\n"


GOOD_SLICES = _slice(1, "1, 2") + _slice(2, "3-4") + _slice(3, "5", base="slice 2")


def test_slice_bounds_match_the_child_bounds():
    assert (crew_split.SLICES_MIN, crew_split.SLICES_MAX) == (
        crew_split.CHILDREN_MIN, crew_split.CHILDREN_MAX)


def test_no_slices_section_valid():
    assert crew_split.parse_slices(_plan_with_slices(None)) == ([], [])


def test_slices_partition_ok():
    slices, problems = crew_split.parse_slices(_plan_with_slices(GOOD_SLICES))

    assert (problems, [(s["n"], s["name"], s["steps"], s["base"]) for s in slices]) == (
        [], [(1, "part 1", [1, 2], "main"), (2, "part 2", [3, 4], "main"),
             (3, "part 3", [5], 2)])


def test_slices_carry_each_slices_files():
    slices, _ = crew_split.parse_slices(_plan_with_slices(GOOD_SLICES))

    assert slices[1]["files"] == ["src/s3.py", "src/s4.py"]


def test_step_in_two_slices_refused():
    _, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 2, 3") + _slice(2, "3, 4, 5")))

    assert any("step 3 is in slices 1 and 2" in p for p in problems), problems


def test_step_in_no_slice_refused():
    _, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 2") + _slice(2, "3, 4")))

    assert any("step 5 is in no slice" in p for p in problems), problems


def test_unknown_step_refused():
    _, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 2") + _slice(2, "3-6")))

    assert any("step 6" in p and "no such step" in p for p in problems), problems


def test_non_contiguous_slice_refused():
    _, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 3") + _slice(2, "2, 4, 5")))

    assert any("slice 1" in p and "not one contiguous run" in p for p in problems), problems


def test_slices_out_of_order_refused():
    _, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "3-5") + _slice(2, "1, 2")))

    assert any("out of order" in p for p in problems), problems


def test_base_main_with_shared_files_refused():
    _, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 2") + _slice(2, "3-5"), files={4: "src/s1.py"}))

    assert any("slice 2" in p and "Base: main" in p and "src/s1.py" in p
               for p in problems), problems


def test_base_main_with_a_glob_overlap_refused():
    _, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 2") + _slice(2, "3-5"), files={1: "src/**"}))

    assert any("slice 2" in p and "Base: main" in p for p in problems), problems


def test_base_slice_with_shared_files_allowed():
    slices, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 2") + _slice(2, "3-5", base="slice 1"), files={4: "src/s1.py"}))

    assert (problems, slices[1]["base"]) == ([], 1)


def test_base_later_slice_refused():
    _, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 2", base="slice 2") + _slice(2, "3-5")))

    assert any("slice 1" in p and "Base: slice 2" in p for p in problems), problems


def test_base_unreadable_refused():
    _, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 2") + _slice(2, "3-5", base="develop")))

    assert any("slice 2" in p and "Base:" in p for p in problems), problems


def test_one_slice_refused():
    _, problems = crew_split.parse_slices(_plan_with_slices(_slice(1, "1-5")))

    assert any("1 slice" in p and "2-5" in p for p in problems), problems


def test_six_slices_refused():
    many = "".join(_slice(n, str(n)) for n in range(1, 6)) + _slice(6, "5")
    _, problems = crew_split.parse_slices(_plan_with_slices(many))

    assert any("6 slices" in p for p in problems), problems


def test_slices_numbered_out_of_sequence_refused():
    _, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 2") + _slice(3, "3-5")))

    assert any("numbered" in p for p in problems), problems


def test_slice_without_steps_line_refused():
    _, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 2") + "### Slice 2: rest\nBase: main\n"))

    assert any("slice 2" in p and "Steps:" in p for p in problems), problems


def test_base_main_with_a_step_of_unknown_files_refused():
    """Could not tell is not "shares nothing": a step whose Files line is
    missing cannot prove slice 2 independent."""
    plan = _plan_with_slices(_slice(1, "1, 2") + _slice(2, "3-5"))
    plan = plan.replace("Files: src/s4.py\n", "")

    _, problems = crew_split.parse_slices(plan)

    assert any("slice 2" in p and "cannot tell" in p for p in problems), problems


# --- review of #366: a step after the section, glob-vs-glob overlap, `## Step` -----

def test_step_heading_after_the_slices_section_is_uncovered():
    """A `### Step 5` written after `## PR slices` is still a plan step, so a
    partition that leaves it out is refused, never silently short a step."""
    plan = _plan_with_slices(_slice(1, "1, 2") + _slice(2, "3, 4"))
    plan = plan.replace("### Step 5: step 5\n", "").replace("Files: src/s5.py\n", "")
    plan += "\n### Step 5: late\nFiles: src/s5.py\nTest: pytest\nRisk: low\n"

    _, problems = crew_split.parse_slices(plan)

    assert any("step 5 is in no slice" in p for p in problems), problems


def test_base_main_with_two_overlapping_globs_cannot_tell():
    _, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 2") + _slice(2, "3-5"),
        files={1: "plugin/crew/hooks/scripts/*.py", 3: "plugin/**/crew_split.py"}))

    assert any("slice 2" in p and "Base: main" in p and "cannot tell" in p
               for p in problems), problems


def test_base_main_with_disjoint_glob_prefixes_allowed():
    """Two globs under different literal directories are provably disjoint."""
    slices, problems = crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 2") + _slice(2, "3-5"),
        files={1: "docs/**", 2: "docs/b.md", 3: "src/**"}))

    assert (problems, slices[1]["base"]) == ([], "main")


def test_level_two_step_heading_refused():
    """measure counts only `### Step`; a `## Step` would be counted by one
    reader and not the other, so parse_slices refuses it."""
    plan = _plan_with_slices(_slice(1, "1, 2") + _slice(2, "3-5"))
    plan = plan.replace("### Step 3: step 3", "## Step 3: step 3")

    _, problems = crew_split.parse_slices(plan)

    assert any("## Step 3" in p and "### Step" in p for p in problems), problems


# --- re-review of #366: one conservative overlap rule for every Files pair ---------

def _two_slice_problems(first, second):
    return crew_split.parse_slices(_plan_with_slices(
        _slice(1, "1, 2") + _slice(2, "3-5"),
        files={1: first, 2: "zz/one.md", 3: second, 4: "yy/a.md", 5: "yy/b.md"}))[1]


@pytest.mark.parametrize("first, second", [
    ("./src/*.py", "src/**/x.py"),        # FIX A: `./` not normalised
    ("src/a", "src/*/x.py"),              # FIX B: a literal is a directory
    ("src/a/", "src/*/x.py"),
    ("src", "**/x.py"),
    ("Src/*.py", "src/**/x.py"),          # NIT C: fnmatch case-folds on Windows
])
def test_base_main_pair_not_provably_disjoint_refused(first, second):
    problems = _two_slice_problems(first, second)

    assert any("slice 2" in p and "Base: main" in p for p in problems), problems


@pytest.mark.parametrize("first, second", [
    ("src/a/*.py", "docs/*.md"),
    ("src/a", "docs"),
])
def test_base_main_pair_provably_disjoint_allowed(first, second):
    assert _two_slice_problems(first, second) == []


def test_step_heading_case_follows_measure():
    """`measure` counts `### Step` case-sensitively; a `### step 5` is not a
    step to either reader, so it does not join the partition."""
    plan = _plan_with_slices(_slice(1, "1, 2") + _slice(2, "3-5"))
    plan += "\n### step 6: lower-case\nFiles: src/s6.py\n"

    slices, problems = crew_split.parse_slices(plan)

    assert (problems, slices[1]["steps"]) == ([], [3, 4, 5])


def test_level_two_step_check_does_not_cross_a_line():
    plan = _plan_with_slices(_slice(1, "1, 2") + _slice(2, "3-5"))
    plan = plan.replace("## PR slices\n", "## Step\n6 notes\n\n## PR slices\n")

    _, problems = crew_split.parse_slices(plan)

    assert not any("## Step 6" in p for p in problems), problems
