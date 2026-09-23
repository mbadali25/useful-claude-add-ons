"""`/crew:change` is mostly prose, and prose is what holds the workflow.

Same two directions as `test_gate_command.py` and `test_docs_routing.py`:

  * The command file SAYS the things the design decided -- the backend comes
    from `tracker`, missing tooling is a STOP rather than a fall-through to
    `local`, the gate is run rather than judged by eye, and `close` refuses
    without the post-change validation results.
  * The interfaces it names EXIST. `crew_change.py` is on disk with the
    functions and exit codes the command branches on, and the skill it defers
    to carries all ten questions.

Plus the config half, which is not prose: the `change` block is in both
layers, `change.requireForProduction` is in the one ratchet table, and the
schema 6 -> 7 bump actually reaches a repo sitting at 6 -- asserted through
`crew_upgrade.run()`, because `upgrade_config()` alone cannot tell you whether
the bump was delivered.

Every run here is offline. Nothing in this file touches a live SDP or Jira.
"""
import json
import os

import context  # noqa: F401  pylint: disable=unused-import
import crew_change
import crew_config
import crew_state
import crew_upgrade

_PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
_CHANGE = os.path.join(_PLUGIN, "commands", "change.md")
_PROMOTE = os.path.join(_PLUGIN, "commands", "promote.md")
_SKILL = os.path.join(_PLUGIN, "skills", "crew-change", "SKILL.md")
_CONFIG_MD = os.path.join(_PLUGIN, "CONFIG.md")
_SCRIPT = os.path.join(_PLUGIN, "hooks", "scripts", "crew_change.py")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _flat(text):
    """Whitespace-collapsed, for phrase assertions. The docs are hard-wrapped,
    so a phrase that spans a line break is absent from the raw text."""
    return " ".join(text.split())


# ---- what the command SAYS -------------------------------------------------


def test_the_command_file_exists_and_declares_its_four_subcommands():
    """The frontmatter is what puts the command in `/help` with a usable hint.
    A command whose `argument-hint` omits a subcommand is one users invoke with
    half an invocation."""
    text = _read(_CHANGE)
    assert text.startswith("---\n")
    head = text.split("---", 2)[1]
    assert "argument-hint:" in head
    for word in ("new", "status", "close", "list"):
        assert word in head, word


def test_the_backend_comes_from_tracker_and_all_three_are_named():
    """One process, three backends. A command that named only SDP would send
    every Jira repo into the fallback this file spends a paragraph
    forbidding."""
    flat = _flat(_read(_CHANGE))

    assert "`tracker`" in flat
    assert "change.sdpTemplate" in flat
    assert "change.jiraIssueType" in flat
    assert ".work/changes/<id>.md" in flat


def test_missing_tooling_is_a_stop_and_never_a_fallback_to_local():
    """The invariant from the design note, and its own test function: folding
    it in with the routing assertion would let a mutation of this claim trip an
    earlier line, print RED, and leave the claim unchecked -- the vacuous
    assertion trap in `sabotage.py`'s header.

    What a fallback costs is the reason it is banned: a change sitting in a
    file, looking filed, that nobody on the change board can see."""
    flat = _flat(_read(_CHANGE))

    assert "**stop**" in flat
    assert "Never fall through to `local`" in flat
    assert "splits the source of truth" in flat
    assert "looking filed" in flat


def test_the_gate_is_run_as_a_program_not_judged_by_reading():
    """The whole feature. An agent that reads nine answers and forms an opinion
    is the "I checked" claim wearing the label of a check that happened -- and
    what it waves through here is a change request a board will deny."""
    flat = _flat(_read(_CHANGE))

    assert "crew_change.py" in flat
    assert "--mode new" in flat
    assert "--mode close" in flat
    # Exit 0 is the ONLY authorisation, stated as such.
    assert "Exit 0 is the only thing that authorises filing" in flat
    assert "Do not read the answers and decide for yourself" in flat
    # And the refusal is relayed, not summarised.
    assert "relay stderr verbatim" in flat


def test_new_refuses_on_one_to_nine_and_does_not_ask_for_ten():
    """The asymmetry, in the command file rather than only in the validator.
    Asking for question 10 at filing time makes the gate unsatisfiable, and the
    natural repair is to type a placeholder."""
    flat = _flat(_read(_CHANGE))

    assert "questions 1-9" in flat or "questions 1–9" in flat
    assert "Question 10 is **not** required here" in flat


def test_close_refuses_without_the_validation_results():
    """Deployed and validated are two claims. A change closed without the
    second one leaves a record saying it was fine."""
    flat = _flat(_read(_CHANGE))

    assert "post-change validation results" in flat
    assert "do not close" in flat.lower()
    assert "before** transitioning it" in flat


def test_status_reads_the_backend_and_never_the_cache():
    """The local file records what was FILED. Only the backend knows what a
    change board did afterwards."""
    flat = _flat(_read(_CHANGE))

    assert "Read the change from the **backend**" in flat
    assert "could not read the state" in flat
    assert "never from the local cache" in _flat(_read(_PROMOTE))


# ---- promote's half --------------------------------------------------------


def test_promote_gate_one_requires_an_approved_change_for_this_sha():
    """Not "a change exists" and not "a change was filed for this work": a
    change whose record names the sha being deployed and whose state the
    backend currently reports as approved."""
    flat = _flat(_read(_PROMOTE))

    assert "change.requireForProduction" in flat
    assert "APPROVED" in flat
    assert "for THIS sha" in flat
    # Read at that moment, from the backend. Not from a cache, and not from
    # this session's memory of having looked.
    assert "Read the state from the backend, every time" in flat
    assert "A cached `approved` is a claim about the past" in flat


def test_promote_treats_an_unreadable_state_as_a_stop():
    """The collapse this repo keeps rediscovering, at its most expensive:
    "could not check" becoming "checked, and fine" in front of a production
    deploy."""
    flat = _flat(_read(_PROMOTE))

    assert "\"Could not read the state\" is a STOP, not a pass" in flat
    assert "not checked" in flat


def test_promote_refuses_outside_the_scheduled_window():
    """A change board approved a change at a time. Deploying at another time is
    deploying something they did not approve."""
    flat = _flat(_read(_PROMOTE))

    assert "Outside the window is a stop" in flat
    assert "Scheduled Start Time" in flat and "Scheduled End Time" in flat


def test_promote_says_the_default_changes_nothing_and_that_this_is_prose():
    """Two claims that must both be in the file. The first is what stops a
    reader believing schema 7 turned change control on for them; the second is
    what stops the section reading as enforced when no hook fires on any of
    it."""
    flat = _flat(_read(_PROMOTE))

    assert "`false` is the shipped default and means this section does not " \
           "exist" in flat
    assert "The change-request section is prose in exactly the same way" in flat
    assert "promote-gate.sh` does not read `change.requireForProduction`" in flat


# ---- the skill holds the wording -------------------------------------------


def test_the_skill_carries_all_ten_questions_and_the_command_defers_to_it():
    """One copy of the wording. The command file routes to the skill rather
    than restating ten questions that would then drift -- and drift shorter,
    which is the direction that lets a request through."""
    skill = _flat(_read(_SKILL))
    command = _flat(_read(_CHANGE))

    assert "crew-change" in command
    for number, question in crew_change.QUESTIONS:
        # The skill hard-wraps, so compare against the flattened text; the
        # question text itself is the contract, not its line breaks.
        assert _flat(question) in skill, number
    # And the template's own rule, verbatim, because it is why the gate exists.
    assert "ALL THE BELOW QUESTIONS MUST BE ANSWERED" in skill


def test_the_placeholder_list_lives_in_one_place():
    """`PLACEHOLDERS` is defined in `crew_change.py`. A second copy in prose is
    a copy that drifts, and a shorter list lets requests through -- so both
    docs CITE the module rather than restating it.

    Asserted by measuring what the docs do NOT contain: more than a couple of
    the tokens appearing in either file would mean somebody had started to
    write the list out."""
    for path in (_CHANGE, _SKILL):
        text = _flat(_read(path))
        assert "crew_change.PLACEHOLDERS" in text, path
        spelled = [token for token in sorted(crew_change.PLACEHOLDERS)
                   if f" {token} " in text.lower()]
        assert len(spelled) <= 2, (path, spelled)


def test_the_skill_maps_every_template_field_to_all_three_backends():
    """The content is identical in all three; only the transport differs. A
    field with no mapping is a field that silently does not travel."""
    skill = _flat(_read(_SKILL))

    for field in crew_change.TEMPLATE_FIELDS:
        assert field in skill, field
    assert "sdp_create module=change" in skill
    assert "getJiraIssueTypeMetaWithFields" in skill
    assert "sdp_list_metadata" in skill


# ---- the config half, which is not prose -----------------------------------


def test_the_change_block_is_declared_in_both_layers():
    """Both, for the same two reasons `install` and `guards` are: the ratchet
    needs a value on each side, and `is_global_path` refuses any path that is
    not also a real repo key."""
    repo = set(crew_config.leaf_paths(crew_config.default_config()))
    glob = set(crew_config.leaf_paths(crew_config.default_global_config()))

    for dotted in crew_upgrade.SCHEMA_7_KEYS:
        assert dotted in repo, dotted
        assert dotted in glob, dotted
        assert crew_config.is_global_path(dotted), dotted


def test_require_for_production_ratchets_and_true_is_the_narrower_value():
    """The one design decision that could have needed a second mechanism and
    does not. `True` ranks below `False`, so `effective_ratcheted`'s existing
    `min` means "a repo may turn the requirement ON and never off"."""
    dotted = "change.requireForProduction"
    assert dotted in crew_state.RATCHETED_KEYS
    tiers, _normalise, rank = crew_state.RATCHETED_KEYS[dotted]
    assert tiers == (True, False)
    assert rank(True) < rank(False)

    eff = crew_state.effective_ratcheted
    # The machine requires it; a cloned repo saying false cannot defeat that.
    assert eff(dotted, False, True) is True
    # The repo requires it; a machine that said nothing does not defeat it.
    assert eff(dotted, True, None) is True
    assert eff(dotted, True, False) is True
    # Nobody asked for it -> off, which is what every repo already did.
    assert eff(dotted, None, None) is False
    assert eff(dotted, False, False) is False


def test_absent_means_false_and_unreadable_means_true():
    """The one ratcheted key where "absent" and "malformed" differ, and both
    halves are load-bearing. Absent must be `false` or schema 7 switches a
    production requirement on for every repo that upgraded; malformed must be
    `true` or "could not tell" wears the label of "not required"."""
    norm = crew_state.normalise_require_for_production

    assert norm(None) is False
    assert norm(False) is False
    assert norm(True) is True
    for garbage in ("yes", "false", "true", 1, 0, [], {}, 0.0):
        assert norm(garbage) is True, garbage


def test_a_zero_is_not_read_as_not_required():
    """`True` and `False` are `int` subclasses in Python, so an
    `isinstance(value, int)` check would have accepted `0` as "not required" --
    the one direction this function must never fail in. Its own test because it
    is the assertion a refactor is most likely to break while every other test
    here stays green."""
    assert crew_state.normalise_require_for_production(0) is True
    assert crew_state.normalise_require_for_production(1) is True


def test_the_widening_note_exists_for_both_values():
    """`plan_global_write`'s `! widens` line does `notes[granted]`, and this is
    the first ratcheted key whose tiers are bools rather than strings."""
    _rank, normalise, notes = crew_config._RATCHETED[  # pylint: disable=protected-access
        "change.requireForProduction"]
    for tier in (True, False):
        assert tier in notes, tier
        assert notes[tier], tier
    assert normalise(None) is False
    # Turning the requirement OFF is the widening direction.
    assert "widening" in notes[False].lower()


def test_the_schema_7_bump_reaches_a_repo_at_schema_6(tmp_path):
    """The delivery mechanism, not the transformation, and asserted through
    `run()` rather than `upgrade_config()`.

    `run()` returns "already current" for any config at or above
    SCHEMA_CURRENT without ever calling `upgrade_config`. Add a migration and
    forget the bump and it reaches only repos that were ALREADY behind --
    nobody it was written for, since every existing config sits at the
    then-current number.

    A LITERAL 6, not `SCHEMA_CURRENT - 1`, for the reason
    `test_the_schema_6_bump_reaches_a_repo_at_schema_5` writes out: deriving
    the fixture from the constant under test makes the test move with the
    mutation. Bump this literal deliberately when the schema moves."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"schema": 6, "tier": 0}), "utf-8")

    result = crew_upgrade.run(str(root), {})

    assert result["status"] != "already current"
    written = json.loads((root / ".crew" / "config.json").read_text("utf-8"))
    assert written["schema"] == crew_state.SCHEMA_CURRENT
    # `change` is entirely globally-settable, so as of this ticket's fix it
    # is no longer WRITTEN into a repo that never named it (see
    # `crew_upgrade._prune_unsupplied_global_leaves`) -- the literal-block
    # check this test used to make is gone with it. `notes` is what proves
    # the schema-7 migration itself ran, same reasoning as
    # `test_guards.py`'s schema-6 sibling. Behaviour-neutral on arrival
    # either way: `CHANGE_REQUIREMENT_DEFAULT` -- what an absent
    # `requireForProduction` normalises to -- IS `False`, the value this
    # migration used to write literally, so promotion still asks for no
    # change request.
    assert "change" not in written
    assert crew_state.CHANGE_REQUIREMENT_DEFAULT is False
    # The keys are NAMED in the notes, or the report cannot say what it added.
    assert set(result["notes"]["changeKeysAdded"]) == set(
        crew_upgrade.SCHEMA_7_KEYS)


def test_the_migration_is_reported_in_both_places_it_is_reported():
    """UPGRADE.md and the terminal. `install.policy` reached UPGRADE.md and
    never the CLI, so a repo with no `.crew/codemap/` gained a key governing
    what crew may run and said so nowhere the user would see. Same class of key
    here, so the same two outputs."""
    _out, notes = crew_upgrade.upgrade_config({"schema": 6, "tier": 0})
    said = "\n".join(crew_upgrade._config_lines(notes))  # pylint: disable=protected-access

    assert "change" in said
    assert "requireForProduction" in said
    assert "never off" in said
    # The CLI print is driven off the same note list, so an empty one would
    # print nothing at all.
    assert notes["changeKeysAdded"]


def test_config_md_documents_the_block_and_the_reversed_ratchet():
    """A ratchet that runs the opposite way from every other ratcheted key is
    exactly the thing a reader will assume rather than check."""
    flat = _flat(_read(_CONFIG_MD))

    assert "## 17. `change`" in flat
    assert "a repo may turn the requirement ON, and may never turn it off" \
        in flat
    for dotted in crew_upgrade.SCHEMA_7_KEYS:
        assert dotted in flat, dotted


def test_the_templates_carry_the_block_at_the_current_schema():
    """`templates/config.template.json` is what `/crew:init` copies down, and
    a template that lagged the module would hand every new repo a config the
    session brief immediately reports as needing an upgrade."""
    for name, builder in (("config.template.json", crew_config.default_config),
                          ("global.template.json",
                           crew_config.default_global_config)):
        path = os.path.join(_PLUGIN, "templates", name)
        with open(path, encoding="utf-8") as handle:
            written = json.load(handle)
        assert written["change"] == crew_upgrade.CHANGE_BLOCK, name
        assert written == builder(), name


def test_the_validator_script_is_where_the_docs_say_it_is():
    """The direction a grep over the prose cannot check: the command file names
    a path, and the path has to resolve."""
    assert os.path.isfile(_SCRIPT)
    flat = _flat(_read(_CHANGE))
    assert "hooks/scripts/crew_change.py" in flat
