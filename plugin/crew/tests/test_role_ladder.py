"""The crew 1.0 roster has one definition in code and one description in prose.

`crew_state.ROLE_TIERS` is what `/crew:upgrade` computes a tier from and what
`crew_upgrade` checks a config's `roles` against. `README.md`'s agent table is
what a human reads. No markdown table is parsed at runtime, so a test is the
only thing keeping the two honest -- and every `agents/*.md` is checked back
against the code, because an agent file nobody registered dispatches nothing
and fails silently.

crew 1.0 cut the roster to four (`docs/review/04-redesign.md`, "Roster: 54
agents -> 4"). The skill tables this file used to check (`crew-scaling`,
`crew-pm/onboarding.md`) were deleted with the PM, and `SPECIALIST_ROLES` is
empty: stack knowledge became the `stack-*` skills.
"""
import os
import re

import context  # noqa: F401  pylint: disable=unused-import
import crew_state

_PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
_AGENTS = os.path.join(_PLUGIN, "agents")
_README = os.path.join(_PLUGIN, "README.md")

ROSTER_1_0 = {"explorer": 0, "reviewer": 0, "security": 1, "researcher": 2}


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _agent_files():
    return {entry[:-len(".md")] for entry in os.listdir(_AGENTS)
            if entry.endswith(".md")}


def test_the_code_ladder_is_the_1_0_roster():
    assert crew_state.ROLE_TIERS == ROSTER_1_0


def test_every_ladder_role_has_an_agent_definition():
    for name in crew_state.ROLE_TIERS:
        assert os.path.isfile(os.path.join(_AGENTS, f"{name}.md")), name


def test_every_agent_definition_is_a_role_crew_knows():
    """The file -> code direction. An `agents/<name>.md` nobody registered
    dispatches nothing, and `/crew:upgrade` would call it unrecognised."""
    for name in sorted(_agent_files()):
        assert crew_state.known_role(name) is True, (
            f"agents/{name}.md is not in ROLE_TIERS, so nothing dispatches it")


def test_the_agent_files_are_exactly_the_roster():
    assert _agent_files() == set(ROSTER_1_0)


def test_there_are_no_specialists_in_1_0():
    assert crew_state.SPECIALIST_ROLES == frozenset()


def test_pm_is_not_a_role():
    assert "pm" not in crew_state.ROLE_TIERS
    assert crew_state.known_role("pm") is False


def test_qa_reviewer_is_not_a_role_any_more():
    """Renamed to `reviewer`. A 0.20 config naming it is carried forward by
    `/crew:migrate` (crew_migrate.RENAMED), not recognised here."""
    assert crew_state.known_role("qa-reviewer") is False
    assert crew_state.known_role("reviewer") is True


def test_no_role_sits_at_the_parallelism_tier():
    assert crew_state.TIER_PARALLEL not in crew_state.ROLE_TIERS.values()
    assert crew_state.tier_for_roles(list(crew_state.ROLE_TIERS)) < \
        crew_state.TIER_PARALLEL


def test_roles_for_tier_is_cumulative_and_in_ladder_order():
    assert crew_state.roles_for_tier(0) == ["explorer", "reviewer"]
    assert crew_state.roles_for_tier(1) == ["explorer", "reviewer", "security"]
    assert crew_state.roles_for_tier(2) == ["explorer", "reviewer", "security",
                                            "researcher"]


def test_tier_for_roles_ignores_a_name_it_does_not_know():
    """A retired 0.20 role contributes nothing: its tier is genuinely unknown
    to this release, and guessing one would move a crew up the ladder on the
    strength of a string nobody recognises."""
    assert crew_state.tier_for_roles(["explorer", "not-a-real-role"]) == 0
    assert crew_state.tier_for_roles([]) == 0
    assert crew_state.tier_for_roles(["planner", "dba"]) == 0
    assert crew_state.tier_for_roles(["researcher"]) == 2


def test_known_role_rejects_a_typo():
    assert crew_state.known_role("wharrgarbl") is False


def _readme_roster():
    """`| `role` | tools | model | tier | what it closes |` rows from the README."""
    return {name: int(tier) for name, tier in re.findall(
        r"^\|\s*`([a-z0-9.-]+)`\s*\|[^|]*\|[^|]*\|\s*(\d+)\s*\|",
        _read(_README), re.MULTILINE)}


def test_the_readme_roster_table_matches_the_code():
    """The copy of the roster a user reads first, and it drifts the same way."""
    assert _readme_roster() == crew_state.ROLE_TIERS
