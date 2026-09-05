"""The role ladder has one definition in code and two descriptions in prose.

`crew_state.ROLE_TIERS` is what `/crew:upgrade` computes a tier from.
`skills/crew-scaling/SKILL.md` and `skills/crew-pm/onboarding.md` are what a
human reads. Neither markdown table is parsed at runtime -- doing that would
make a heading in a skill file decide what an upgrade writes -- so a test is
the only thing keeping the three honest. A row added to one table and not the
dict (or the reverse) fails here rather than shipping as a `/crew:scale` that
proposes a role no upgrade recognises.

The third thing checked here is that every ladder role has an agent definition
behind it: a name in `config.json.roles` with no `agents/<role>.md` dispatches
nothing and fails silently, which `crew-pm/onboarding.md` says in as many words.
"""
import os
import re

import context  # noqa: F401  pylint: disable=unused-import
import crew_state

_PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
_SCALING = os.path.join(_PLUGIN, "skills", "crew-scaling", "SKILL.md")
_ONBOARDING = os.path.join(_PLUGIN, "skills", "crew-pm", "onboarding.md")
_AGENTS = os.path.join(_PLUGIN, "agents")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _onboarding_ladder():
    """`| `role` | closes | tier |` rows from the roster table."""
    rows = re.findall(r"^\|\s*`([a-z-]+)`\s*\|[^|]*\|\s*(\d+)\s*\|\s*$",
                      _read(_ONBOARDING), re.MULTILINE)
    return {name: int(tier) for name, tier in rows}


def _scaling_ladder():
    """`| tier | + role, role | when |` rows from the tier table.

    A leading `+` is the table's own "added at this tier" marker. The tier-3
    row lists parallelism, not roles, and contributes nothing: no role lives
    at `TIER_PARALLEL`, which is why `tier_for_roles` can never return it.
    """
    ladder = {}
    for tier, cell in re.findall(r"^\|\s*(\d+)\s*\|([^|]+)\|", _read(_SCALING),
                                 re.MULTILINE):
        if int(tier) == crew_state.TIER_PARALLEL:
            # This row lists parallelism, not roles -- no role lives at this
            # tier, which is why tier_for_roles can never return it. Skipping
            # the row is a claim about the table; skipping unrecognised NAMES
            # would be using the code as the answer key for its own docs.
            continue
        for name in cell.replace("+", "").split(","):
            name = name.strip()
            # Deliberately NOT filtered through crew_state.ROLE_TIERS. Doing
            # that used the production dict as a sieve for the documentation
            # it is supposed to be checked against, so a table listing
            # `securty`, or a role crew does not have, was dropped before the
            # comparison and the equality below still passed. This parser has
            # to represent the table as written, wrong entries included.
            if name and not name.startswith("`"):
                ladder[name] = int(tier)
    return ladder


def test_onboarding_roster_matches_the_code_ladder():
    assert _onboarding_ladder() == crew_state.ROLE_TIERS


def test_crew_scaling_tier_table_matches_the_code_ladder():
    assert _scaling_ladder() == crew_state.ROLE_TIERS


def test_the_three_roles_added_in_0_15_x_are_on_the_ladder():
    """They shipped as definitions with no tier row, so `/crew:scale` would
    not propose them and `/crew:pm` would not onboard them from evidence."""
    for name in ("infrastructure-architect", "scribe", "researcher"):
        assert crew_state.ROLE_TIERS[name] == 2, name
        assert name in _scaling_ladder(), name


def test_every_ladder_role_has_an_agent_definition():
    for name in crew_state.ROLE_TIERS:
        assert os.path.isfile(os.path.join(_AGENTS, f"{name}.md")), name


def test_pm_is_not_on_the_ladder():
    """It is not sized in or out by /crew:scale -- it is the thing sizing."""
    assert "pm" not in crew_state.ROLE_TIERS


def test_no_role_sits_at_the_parallelism_tier():
    assert crew_state.TIER_PARALLEL not in crew_state.ROLE_TIERS.values()
    assert crew_state.tier_for_roles(list(crew_state.ROLE_TIERS)) < \
        crew_state.TIER_PARALLEL


def test_roles_for_tier_is_cumulative_and_in_ladder_order():
    assert crew_state.roles_for_tier(0) == ["explorer", "qa-reviewer"]
    tier_one = crew_state.roles_for_tier(1)
    assert tier_one[:2] == ["explorer", "qa-reviewer"]
    assert set(crew_state.roles_for_tier(0)) < set(tier_one)
    assert set(tier_one) < set(crew_state.roles_for_tier(2))


def test_tier_for_roles_ignores_a_name_it_does_not_know():
    assert crew_state.tier_for_roles(["explorer", "not-a-real-role"]) == 0
    assert crew_state.tier_for_roles([]) == 0
    assert crew_state.tier_for_roles(["planner"]) == 2


# --- domain specialists ----------------------------------------------------
#
# Off the ladder ON PURPOSE, which is the opposite of the 0.15.x bug directly
# above: those three were general-purpose roles that had simply been forgotten,
# and being unreachable was the defect. These are domain-specific, and being
# unreachable-by-default is the feature.


def test_specialists_are_not_on_the_tier_ladder():
    """The whole point. `roles_for_tier` grants every rung up to the declared
    tier, so putting a SharePoint developer on the ladder would hand one to
    every tier-2 repo on the machine -- including the ones with no SharePoint.
    That is already visible with `dba`: this repo has no database and was
    granted one anyway."""
    for name in crew_state.SPECIALIST_ROLES:
        assert name not in crew_state.ROLE_TIERS, name


def test_no_tier_ever_auto_grants_a_specialist():
    """The rule stated against the function that would break it, rather than
    against the data. A specialist added to ROLE_TIERS by mistake fails here
    even if the set above is edited to match."""
    for tier in range(0, crew_state.TIER_PARALLEL + 2):
        granted = set(crew_state.roles_for_tier(tier))
        assert not (granted & crew_state.SPECIALIST_ROLES), tier


def test_every_specialist_has_an_agent_definition():
    for name in crew_state.SPECIALIST_ROLES:
        assert os.path.isfile(os.path.join(_AGENTS, f"{name}.md")), name


def test_a_specialist_is_a_known_role_even_though_it_has_no_tier():
    """`known_role` is what separates "off the ladder deliberately" from
    "a name this release has never heard of". Without it a repo that onboards
    a specialist gets it reported as unrecognised on every upgrade."""
    for name in crew_state.SPECIALIST_ROLES:
        assert crew_state.known_role(name) is True, name
    for name in crew_state.ROLE_TIERS:
        assert crew_state.known_role(name) is True, name
    assert crew_state.known_role("wharrgarbl") is False


def test_a_specialist_contributes_no_tier():
    """It carries no evidence about how much crew a repo needs, so it must not
    move the tier -- in either direction."""
    assert crew_state.tier_for_roles(["node-developer"]) == 0
    assert crew_state.tier_for_roles(["dba", "node-developer"]) == 2
