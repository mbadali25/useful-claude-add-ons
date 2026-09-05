"""Tests for schema 3's per-role provider table and the self-review guard.

The interlock these protect: **the family that wrote the code may not review
it**, and the family guard is evaluated BEFORE any pin. A pin that beat the
guard would let a model review its own family's diff, which is the one thing
this design exists to prevent -- so the ordering is asserted here rather than
described in a docstring and hoped for.

Everything asserts on `crew_state.resolve_role`'s returned dict rather than on
printed text. A report that says the right thing while the resolver decided
the wrong one is exactly the failure mode a stdout assertion cannot see.
"""
import threading
import time
import copy
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_fixtures
import crew_state


@pytest.fixture(autouse=True)
def _no_machine_global(tmp_path, monkeypatch):
    """Every test here resolves against the fixture config and nothing else.

    `model_report` goes through `resolve_config`, which reads the machine's
    real `~/.claude/crew/config.json`. Without this the suite passes on a
    developer's laptop and fails on a machine whose global file pins a model
    these fixtures do not set -- a failure that looks like a code bug and is
    not one.
    """
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH",
                        str(tmp_path / "absent-global.json"))


# The table the user asked for, 2026-09-05. Verified model ids: `gpt-6-astra`,
# `gpt-5.6-sol` and `gpt-5.6-luna` on codex; `kimi-k2.7-code` and `kimi-k3` on
# copilot. `kimi-k2.7` WITHOUT the `-code` suffix is rejected by the Copilot
# CLI, which is why the suffixed id is the one that appears in every fixture.
PINNED = {
    "schema": crew_state.SCHEMA_CURRENT,
    "dev": {
        "provider": "claude",
        "fallback": "claude-sonnet-5",
        "codex": {"model": None, "reasoningEffort": None},
        "copilot": {"model": None},
        "roles": {
            "developer": {"provider": "codex", "model": "gpt-6-astra"},
            "security": {"provider": "codex", "model": "gpt-6-astra"},
            "infrastructure-architect": {"provider": "codex",
                                         "model": "gpt-6-astra"},
            "planner": {
                "provider": "claude",
                "model": None,
                "alternate": {"provider": "codex", "model": "gpt-5.6-sol"},
            },
        },
    },
    "qa": {
        "provider": "auto",
        "order": ["codex", "copilot", "claude"],
        "fallback": "claude-sonnet-5",
        "codex": {"model": None, "reasoningEffort": None},
        "copilot": {"model": "kimi-k2.7-code"},
        "roles": {
            "phase1": {"provider": "codex", "model": "gpt-5.6-sol"},
            "smoke": {"provider": "codex", "model": "gpt-5.6-sol"},
            "review": {"provider": "codex", "model": "gpt-5.6-luna"},
            "gate": {"provider": "codex", "model": "gpt-5.6-luna"},
        },
    },
}


# --- family() ---------------------------------------------------------------


def test_family_derives_gpt_for_every_codex_id():
    """No id is special-cased. `split("-")[0]` already yields `gpt` for all
    three, which is what makes the derivation survive the next rename."""
    for model in ("gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-luna"):
        assert crew_state.family("codex", model) == "gpt", model


def test_family_derives_kimi_for_every_copilot_id():
    for model in ("kimi-k2.7-code", "kimi-k3"):
        assert crew_state.family("copilot", model) == "kimi", model


def test_family_of_an_unset_copilot_model_is_none_not_a_placeholder():
    """Two unset Copilot models must not compare equal to each other and
    report BARRED when the real reason is "unset"."""
    assert crew_state.family("copilot", None) is None
    assert crew_state.family("copilot", "") is None


def test_family_of_an_unpinned_codex_is_gpt():
    assert crew_state.family("codex", None) == "gpt"


def test_family_of_claude_is_claude_whatever_it_is_pinned_to():
    assert crew_state.family("claude", "kimi-k3") == "claude"


def test_display_model_names_the_model_and_shows_the_wire_id():
    assert crew_state.display_model("kimi-k2.7-code") == "Kimi 2.7 (kimi-k2.7-code)"
    assert crew_state.display_model("gpt-5.6-luna") == "GPT-5.6 Luna (gpt-5.6-luna)"


def test_display_model_passes_an_unknown_id_through_unchanged():
    """A DISPLAY map, never an allowlist. A model this release has never heard
    of must render, not vanish -- catalogs churn, and `/crew:model`'s standing
    rule is that no hardcoded list may gate a pin."""
    assert crew_state.display_model("some-model-9") == "some-model-9"


# --- each pin resolves per role --------------------------------------------


def test_every_dev_role_resolves_to_its_own_pin():
    for role in ("developer", "security", "infrastructure-architect"):
        got = crew_state.resolve_role(PINNED, "dev", role)
        assert got["provider"] == "codex", role
        assert got["model"] == "gpt-6-astra", role
        assert got["family"] == "gpt", role
        assert got["source"] == "role-pin", role


def test_the_planner_pin_stays_claude_and_keeps_its_alternate():
    """The planner works from an abstracted brief; the codex entry is an
    ALTERNATE, not a replacement, and nothing here promotes it."""
    got = crew_state.resolve_role(PINNED, "dev", "planner")
    assert got["provider"] == "claude"
    assert got["family"] == "claude"
    alternate = PINNED["dev"]["roles"]["planner"]["alternate"]
    assert alternate == {"provider": "codex", "model": "gpt-5.6-sol"}


def test_every_qa_role_resolves_to_its_own_pin():
    expected = {"phase1": "gpt-5.6-sol", "smoke": "gpt-5.6-sol",
                "review": "gpt-5.6-luna", "gate": "gpt-5.6-luna"}
    for role, model in expected.items():
        got = crew_state.resolve_role(PINNED, "qa", role)
        assert got["provider"] == "codex", role
        assert got["model"] == model, role
        assert got["source"] == "role-pin", role


def test_two_qa_roles_can_run_different_models():
    """The whole point of a per-role table: a block-level row would report one
    model for four roles and hide that `review` and `smoke` differ."""
    assert (crew_state.resolve_role(PINNED, "qa", "smoke")["model"]
            != crew_state.resolve_role(PINNED, "qa", "review")["model"])


def test_a_role_with_no_pin_falls_to_the_blocks_own_provider():
    """"Absent role block = claude" is only true because the block default is.
    What an unpinned role must NOT do is invent a provider of its own."""
    cfg = {"dev": {"provider": "claude", "roles": {}}}
    got = crew_state.resolve_role(cfg, "dev", "developer")
    assert got["provider"] == "claude"
    assert got["source"] == "block-default"


def test_a_role_crew_has_never_heard_of_still_resolves():
    cfg = {"dev": {"provider": "claude",
                   "roles": {"house-style-cop": {"provider": "codex",
                                                 "model": "gpt-6-astra"}}}}
    got = crew_state.resolve_role(cfg, "dev", "house-style-cop")
    assert got["provider"] == "codex" and got["model"] == "gpt-6-astra"


def test_a_copilot_role_pin_is_selectable_as_a_dev_provider():
    """`kimi-k2.7-code` must be selectable for dev, not only for QA."""
    cfg = {"dev": {"provider": "claude",
                   "roles": {"developer": {"provider": "copilot",
                                           "model": "kimi-k2.7-code"}}}}
    got = crew_state.resolve_role(cfg, "dev", "developer")
    assert got["provider"] == "copilot"
    assert got["model"] == "kimi-k2.7-code"
    assert got["family"] == "kimi"


# --- the family guard beats the pin ----------------------------------------


def test_the_family_guard_beats_the_pin_on_a_codex_authored_diff():
    """The precedence rule, asserted rather than described.

    `gpt-5.6-luna` is pinned to `qa.roles.review` and is the SAME `gpt` family
    as the `gpt-6-astra` that wrote the diff. The pin must not save it.
    """
    got = crew_state.resolve_role(PINNED, "qa", "review", author="gpt")

    assert got["source"] == "role-pin", "the pin was found"
    assert got["barred"] is True, "and the guard beat it anyway"
    assert got["barredBy"] == "gpt"
    assert any("BARRED" in line for line in got["announce"])


def test_every_gpt_qa_pin_is_barred_by_a_codex_author():
    """Sol and Luna are the same family as Astra. Pinning the senior developer
    to codex therefore means most dev work is codex-authored, so these pins
    fire on claude-authored work and comparatively rarely elsewhere."""
    for role in ("phase1", "smoke", "review", "gate"):
        assert crew_state.resolve_role(
            PINNED, "qa", role, author="gpt")["barred"] is True, role


def test_a_kimi_pin_survives_a_codex_author():
    """QA falls to claude or kimi on a codex-written diff -- a different
    family is exactly what the guard is protecting."""
    cfg = {"qa": {"provider": "auto",
                  "roles": {"review": {"provider": "copilot",
                                       "model": "kimi-k2.7-code"}}}}
    got = crew_state.resolve_role(cfg, "qa", "review", author="gpt")
    assert got["barred"] is False
    assert got["family"] == "kimi"


def test_a_claude_authored_diff_bars_the_claude_reviewer():
    cfg = {"qa": {"provider": "claude", "roles": {}}}
    got = crew_state.resolve_role(cfg, "qa", "review", author="claude")
    assert got["barred"] is True and got["barredBy"] == "claude"


def test_an_unknown_author_family_bars_nothing():
    """None, never a guess. Barring on an unknown author would take a real
    reviewer off a diff on the strength of a value nobody established.

    The negative half alone proves nothing -- `barred` is initialised False,
    so deleting the guard outright would leave it green. The paired positive
    assertion is what makes this a test of the guard rather than of the
    initialiser: the SAME role and config must bar once a real author is
    supplied.
    """
    for role in ("phase1", "review"):
        unknown = crew_state.resolve_role(PINNED, "qa", role, author=None)
        assert unknown["barred"] is False, role
        known = crew_state.resolve_role(PINNED, "qa", role,
                                        author=unknown["family"])
        assert known["barred"] is True, role
        assert known["barredBy"] == unknown["family"], role


def test_author_family_honours_a_per_role_dev_pin_over_the_block_default():
    """The under-bar the role table would otherwise have introduced.

    `dev.provider` is only the default; `dev.roles.developer` overrides it.
    Reading the block alone reported `claude` for a repo whose developer is
    pinned to codex, which struck claude and cleared CODEX to review a diff
    codex wrote -- the same-family review the guard exists to prevent,
    introduced by the very feature that added the pins.
    """
    cfg = {"dev": {"provider": "claude",
                   "roles": {"developer": {"provider": "codex",
                                           "model": "gpt-6-astra"}}}}
    assert crew_state.author_families(".", cfg) == (frozenset({"gpt"}),
                                                    "config")
    # And the pin must not invent an author where the block default rules.
    assert crew_state.author_families(
        ".", {"dev": {"provider": "claude"}}) == (frozenset({"claude"}),
                                                  "config")


def test_family_normalises_case_separator_and_namespace():
    """A QA hunt found the guard bypassable by SPELLING alone.

    `family` was `model.split("-")[0]` verbatim, so `GPT-5` -- the same family
    as `gpt-6-astra`, differing only in case -- produced `GPT`, compared
    unequal to `gpt`, and was cleared to review GPT-authored work. `gpt5` and
    `openai/gpt-5` did the same thing by separator and by namespace. A guard
    that a capital letter walks past is not a guard.
    """
    for model in ("gpt-6-astra", "GPT-5", "gpt5", "GPT5",
                  "openai/gpt-5", "  gpt-5.6-luna  ", "gpt_5"):
        assert crew_state.family("copilot", model) == "gpt", model
    for model in ("kimi-k2.7-code", "KIMI-K3", "moonshot/kimi-k3"):
        assert crew_state.family("copilot", model) == "kimi", model


def test_a_differently_spelled_same_family_model_is_still_barred():
    """The consequence, asserted where it matters rather than on the helper."""
    for model in ("GPT-5", "gpt5", "openai/gpt-5"):
        cfg = {"qa": {"provider": "copilot", "copilot": {"model": model}}}
        got = crew_state.resolve_role(cfg, "qa", "review",
                                      author=frozenset({"gpt"}))
        assert got["barred"] is True, model


def test_an_unset_copilot_model_is_not_barred_against_another_unset_one():
    cfg = {"dev": {"provider": "copilot", "copilot": {"model": None}},
           "qa": {"provider": "copilot", "copilot": {"model": None}}}
    authors, _ = crew_state.author_families(".", cfg)
    # Unknown, not "some family called None": an unset Copilot model has no
    # knowable family, so there is nothing to strike.
    assert authors == frozenset()
    assert crew_state.resolve_role(
        cfg, "qa", "review", author=None)["barred"] is False


# --- the fallback fires, and announces -------------------------------------


def _gone(_provider, _model):
    """Every pinned model has been retired."""
    return False


def test_a_retired_pinned_model_falls_back_and_says_so():
    got = crew_state.resolve_role(PINNED, "qa", "review", available=_gone)

    assert got["fellBack"] is True
    assert got["model"] == "claude-sonnet-5"
    assert got["provider"] == "claude"
    announced = " ".join(got["announce"])
    assert "FELL BACK" in announced
    assert "gpt-5.6-luna" in announced, "names the pin it could not use"
    assert "claude-sonnet-5" in announced, "and the model it used instead"


def test_the_fallback_value_is_configurable_not_hardcoded():
    """The whole reason this requirement exists is that model names churn, so
    the fallback name must be one of the things that can change."""
    cfg = json.loads(json.dumps(PINNED))
    cfg["qa"]["fallback"] = "claude-opus-9"
    got = crew_state.resolve_role(cfg, "qa", "review", available=_gone)
    assert got["model"] == "claude-opus-9"


def test_a_fallback_that_lands_on_the_authors_own_family_says_that_too():
    """The fallback is family-checked. A claude fallback on claude-authored
    work is the same-family review the guard exists to prevent, and a silent
    one is indistinguishable from an independent review."""
    cfg = {"qa": {"provider": "auto", "fallback": "claude-sonnet-5",
                  "roles": {"review": {"provider": "copilot",
                                       "model": "kimi-k3"}}}}
    got = crew_state.resolve_role(cfg, "qa", "review", author="claude",
                                  available=_gone)
    assert got["fellBack"] is True
    assert got["fallbackBarred"] is True
    assert any("not an independent review" in line for line in got["announce"])


def test_nothing_falls_back_when_no_probe_is_supplied():
    """`available=None` means "not checked", not "assumed dead".

    Both asserted values are the pre-fallback initial state, so this half
    would survive deleting the fallback branch outright. The probed control
    below is what pins the difference: same config, same role, and the ONLY
    change is that a probe was supplied.
    """
    got = crew_state.resolve_role(PINNED, "qa", "review")
    assert got["fellBack"] is False
    assert got["model"] == "gpt-5.6-luna"

    probed = crew_state.resolve_role(PINNED, "qa", "review", available=_gone)
    assert probed["fellBack"] is True
    assert probed["model"] != got["model"]


def test_the_guard_is_evaluated_before_the_fallback():
    """A barred role must report BARRED, not a fallback: falling back would
    describe a review that the guard has already refused to allow."""
    got = crew_state.resolve_role(PINNED, "qa", "review", author="gpt",
                                  available=_gone)
    assert got["barred"] is True
    assert got["fellBack"] is False


# --- family() reads recorded dispatch state --------------------------------


def test_author_family_reads_the_recorded_dispatch(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")

    authors, source = crew_state.author_families(str(root), PINNED)

    assert authors == frozenset({"gpt"})
    assert source == "dispatch"


def test_a_recorded_dispatch_beats_what_the_config_now_says(tmp_path):
    """The point of recording it. A config read after the fact describes the
    NEXT dispatch, not the one that produced the diff being reviewed."""
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "copilot",
                               "kimi-k3")

    authors, source = crew_state.author_families(str(root), PINNED)

    assert authors == frozenset({"kimi"}), "the config default did not win"
    assert source == "dispatch"


def test_with_no_dispatch_recorded_the_fallback_is_labelled_as_such(tmp_path):
    """/crew:model on a clean tree still has to report honestly: the config
    read is a statement about the next run, and saying so is the difference
    between a fact and a guess."""
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)

    authors, source = crew_state.author_families(str(root), PINNED)

    assert source == "config"
    # PINNED pins `developer` to codex/gpt-6-astra, so `gpt` -- NOT the
    # `claude` its dev.provider names. This assertion read "claude" until
    # 0.16.0 and was wrong in the one direction that matters: it is the
    # under-bar that would clear codex to review a codex-written diff.
    assert authors == frozenset({"gpt"}), \
        "dev.roles.developer overrides dev.provider"

    # A repo with no role pins still reports the block default, so the fix
    # narrows nothing for a config that never used the role table.
    plain = dict(PINNED, dev={"provider": "claude"})
    assert crew_state.author_families(str(root), plain) == (
        frozenset({"claude"}), "config")


def test_a_branchless_record_in_a_git_checkout_fails_closed(tmp_path):
    """Codex round 2, first BLOCK.

    A record written before the `branch` field existed proves nothing about
    which branch it came from, and trusting it struck only ITS family --
    leaving the configured family clear to review its own diff. Unknown
    provenance is not good provenance.
    """
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=True)
    (root / ".work").mkdir(exist_ok=True)
    (root / ".work" / "dispatch.json").write_text(
        json.dumps({"dev": {"role": "developer", "provider": "codex",
                            "model": "gpt-6-astra"}}), encoding="utf-8")

    authors, source = crew_state.author_families(str(root), PINNED)

    assert source == "stale"
    # Both: the recorded gpt AND the configured developer's family.
    assert "gpt" in authors
    assert len(authors) >= 1


def test_a_record_written_while_detached_is_not_trusted_by_another(tmp_path):
    """Codex round 4.

    A dispatch recorded while HEAD is already detached stores `branch: null`.
    Reading it from any other detached state then gave None == None and read
    as proof, so the guard trusted provenance that was never established --
    the second wrong answer in a row from comparing branch values alone.
    Repository PRESENCE is what separates the harmless missing branch (a
    directory with no branches at all) from the dangerous unreadable one.
    """
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=True)
    subprocess.run(["git", "checkout", "--detach", "HEAD"], cwd=str(root),
                   capture_output=True, check=True)
    assert crew_state.in_git_repo(str(root)) is True, "fixture precondition"

    (root / ".work").mkdir(exist_ok=True)
    (root / ".work" / "dispatch.json").write_text(
        json.dumps({"dev": {"role": "developer", "provider": "codex",
                            "model": "gpt-6-astra", "branch": None}}),
        encoding="utf-8")

    _authors, source = crew_state.author_families(str(root), PINNED)
    assert source == "stale", "a null branch inside a repo proves nothing"


def test_a_broken_git_probe_is_unknown_not_proof(tmp_path, monkeypatch):
    """Codex round 5.

    `in_git_repo` returned a bool, so git being absent, timing out, or
    failing to spawn collapsed to False -- which the rule reads as the SAFE
    "no repository here" case and therefore as PROOF of provenance. A guard
    that fails open when its probe breaks is worse than one with no probe,
    because it looks like it checked.
    """
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")
    assert crew_state.author_families(str(root), PINNED)[1] == "dispatch"

    def no_git(*_args, **_kwargs):
        raise OSError("git is not installed")

    monkeypatch.setattr(crew_state.subprocess, "run", no_git)
    assert crew_state.in_git_repo(str(root)) is None, "unknown, not False"
    assert crew_state.author_families(str(root), PINNED)[1] == "stale"


def test_git_answering_no_is_an_answer_not_a_failure(tmp_path):
    """The other half: a non-zero exit means git RAN and said this is not a
    work tree. Treating that as unknown would bar every non-git checkout
    forever, which is the over-bar two earlier rounds already rejected."""
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    assert crew_state.in_git_repo(str(root)) is False


def test_a_non_git_directory_with_a_branchless_record_is_still_trusted(
        tmp_path):
    """The counterweight: the fix above must not bar every non-git checkout.

    No repository means no branches to switch between, so a record naming
    none is the expected shape rather than a gap in the evidence.
    """
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    assert crew_state.in_git_repo(str(root)) is False, "fixture precondition"
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")

    _authors, source = crew_state.author_families(str(root), PINNED)
    assert source == "dispatch"


def test_a_detached_head_does_not_trust_a_record_naming_a_branch(tmp_path):
    """Codex round 3.

    `current_branch` returns None for a detached HEAD -- which is also the
    normal state during a rebase. An earlier guard read that as "no branches
    here" and trusted the record, so a dispatch made on main and then read
    from a detached HEAD struck only the recorded family and left the
    configured one clear to review its own diff. Absence of a readable branch
    is not evidence that the record belongs to this one.
    """
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=True)
    (root / ".work").mkdir(exist_ok=True)
    (root / ".work" / "dispatch.json").write_text(
        json.dumps({"dev": {"role": "developer", "provider": "codex",
                            "model": "gpt-6-astra", "branch": "main"}}),
        encoding="utf-8")

    subprocess.run(["git", "checkout", "--detach", "HEAD"], cwd=str(root),
                   capture_output=True, check=True)
    assert crew_state.current_branch(str(root)) is None, "fixture precondition"

    _authors, source = crew_state.author_families(str(root), PINNED)
    assert source == "stale"


def test_a_non_git_checkout_is_not_stale_merely_for_lacking_branches(tmp_path):
    """The other side of the same rule, and the reason it is not simply
    "no branch means stale": a checkout with nothing to switch between
    carries none of the cross-branch risk, and failing closed there would
    over-bar it forever rather than once."""
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")

    authors, source = crew_state.author_families(str(root), PINNED)

    assert source == "dispatch"
    assert authors == frozenset({"gpt"})


def test_an_mtime_stale_verdict_reaches_the_report(tmp_path):
    """Codex round 2, second BLOCK.

    Only /crew:review can compare the record against the diff's merge-base,
    so it has to be able to TELL the resolver. Without this the report kept
    saying `dispatch` with one family while the command's own prose said to
    strike two -- and the resolved data is what every later step reads.
    """
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")

    fresh, fresh_src = crew_state.author_families(str(root), PINNED)
    stale, stale_src = crew_state.author_families(str(root), PINNED,
                                                  stale=True)

    assert fresh_src == "dispatch" and fresh == frozenset({"gpt"})
    assert stale_src == "stale"
    assert stale >= fresh, "striking must only ever widen"


def test_every_family_dispatched_on_this_branch_is_struck(tmp_path):
    """QA finding 1, Critical.

    `dispatch.json` held ONE dev slot. Codex writes the diff; a Claude
    developer dispatch later runs on the same branch for something unrelated
    and overwrites the slot; review then reads a matching branch, declares
    CLAUDE the author, bars Claude -- and clears Codex to review the diff
    Codex wrote.

    It was invisible by construction: the record is newer than the merge-base,
    so the staleness check cannot disprove it, and the report says "recorded
    at dispatch", which reads as verified rather than guessed.

    Nothing binds a dispatch to the commits it produced, so the honest answer
    is that ANY family dispatched on this branch may have written this diff.
    Strike all of them. Over-barring costs a rung; under-barring costs the
    entire point of the guard.
    """
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=True)
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")
    crew_state.record_dispatch(str(root), "dev", "developer", "claude", None)

    authors, source = crew_state.author_families(str(root), PINNED)

    assert authors == frozenset({"gpt", "claude"}), \
        "the earlier codex dispatch must not be forgotten"
    assert source == "dispatch"


def test_a_stale_record_does_not_forget_this_branch_history(tmp_path):
    """The half of finding 1 that survived the first fix.

    Filtering history on the LAST RECORD's branch is not the same as
    filtering on the branch in front of the reviewer, and in the stale path
    they diverge: codex writes the diff on this branch, a claude dispatch on
    `main` overwrites the slot, and review back on this branch reads
    `here != there` -> stale. Filtering on `there` then keeps only the claude
    record and drops codex entirely -- the exact clearance the whole finding
    is about, restored by the fix for it.
    """
    # A config whose own dev family is neither of the dispatched ones, so
    # the stale path's config strike cannot mask a missing history strike.
    cfg = copy.deepcopy(PINNED)
    cfg["dev"]["roles"]["developer"] = {"provider": "copilot",
                                        "model": "kimi-k3"}
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=True)
    here = crew_state.current_branch(str(root))
    assert here, "fixture must have a branch for this to mean anything"

    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra", branch=here)
    crew_state.record_dispatch(str(root), "dev", "developer", "claude", None,
                               branch="main-elsewhere")

    authors, source = crew_state.author_families(str(root), cfg)

    assert source == "stale"
    assert "gpt" in authors,         "codex dispatched on THIS branch and must still be struck"
    assert "claude" in authors


def test_one_family_dispatched_twice_is_still_one_family(tmp_path):
    """The control: striking every dispatch must not widen a repo that only
    ever used one provider."""
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=True)
    for _ in range(3):
        crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                                   "gpt-6-astra")

    authors, _source = crew_state.author_families(str(root), PINNED)
    assert authors == frozenset({"gpt"})


def test_a_dispatch_on_another_branch_is_not_added_to_the_strike(tmp_path):
    """History is per branch. A family that only ever dispatched elsewhere
    did not write this diff, and barring it would over-bar permanently
    rather than by a rung."""
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=True)
    crew_state.record_dispatch(str(root), "dev", "developer", "copilot",
                               "kimi-k3", branch="some-other-branch")
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")

    authors, _source = crew_state.author_families(str(root), PINNED)
    assert "kimi" not in authors


def test_the_dispatch_write_is_atomic(tmp_path):
    """QA finding 2, Critical. The writer truncated the live file before the
    JSON was complete, and `read_dispatch` collapses malformed JSON to `{}` --
    so a concurrent reader saw no dispatch at all and fell back to reading
    the CONFIG, which describes the next run rather than the one under review.
    That is the guard failing open during an ordinary race.
    """
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")
    path = os.path.join(str(root), *crew_state.DISPATCH_PATH)

    with open(path, encoding="utf-8") as handle:
        assert json.load(handle)["dev"]["provider"] == "codex"
    leftovers = [n for n in os.listdir(os.path.dirname(path))
                 if n.endswith(".tmp")]
    assert leftovers == [], leftovers


def test_a_malformed_dispatch_file_reads_as_no_dispatch(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    (root / ".work" / "dispatch.json").write_text("{ half-written",
                                                  encoding="utf-8")
    assert crew_state.read_dispatch(str(root)) == {}
    assert crew_state.author_families(str(root), PINNED)[1] == "config"


def test_recording_a_kind_nothing_reads_is_refused(tmp_path):
    """A writer with no reader is an inert feature that looks like coverage.

    `qa` was recordable until 0.16.0 and nothing ever read the slot, so a
    `qa` record could only mislead someone inspecting dispatch.json. Adding a
    reader means adding its kind to DISPATCH_KINDS in the same change.
    """
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    try:
        crew_state.record_dispatch(str(root), "qa", "review", "codex",
                                   "gpt-5.6-luna")
        raise AssertionError("recording an unread kind should have raised")
    except ValueError as exc:
        assert "no reader for dispatch kind" in str(exc)

    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")
    got = crew_state.read_dispatch(str(root))
    assert "qa" not in got
    assert got["dev"]["model"] == "gpt-6-astra"


def test_the_dispatch_cli_records_and_refuses_an_incomplete_call(
        tmp_path, capsys):
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    assert crew_state.main([
        "--root", str(root), "--record-dispatch", "dev",
        "--role", "developer", "--provider", "codex",
        "--model", "gpt-6-astra"]) == 0
    capsys.readouterr()
    assert crew_state.author_families(str(root), PINNED) == (
        frozenset({"gpt"}), "dispatch")

    # A record with no provider would make author_families answer empty while
    # claiming `dispatch` -- worse than the honest config read it displaced.
    assert crew_state.main([
        "--root", str(root), "--record-dispatch", "dev",
        "--role", "developer"]) == 2
    assert "needs --role and --provider" in capsys.readouterr().err


# --- the report /crew:model prints -----------------------------------------


def _no_cli(_name):
    return None


def test_the_report_names_every_role_with_its_family_and_fallback(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")

    report = crew_config.model_report(str(root), which=_no_cli)

    assert report["authorFamily"] == "gpt"
    assert report["authorSource"] == "dispatch"
    assert {r["role"] for r in report["dev"]} >= set(crew_state.DEV_ROLE_KINDS)
    assert {r["role"] for r in report["qa"]} == set(crew_state.QA_ROLE_KINDS)
    # Guard applied to QA, not to dev: the guard governs who may REVIEW.
    assert all(r["barred"] for r in report["qa"])
    assert not any(r["barred"] for r in report["dev"])
    assert all(r["fallback"] == "claude-sonnet-5" for r in report["qa"])


def test_the_report_shows_the_display_name_not_the_bare_wire_id(tmp_path):
    cfg = json.loads(json.dumps(PINNED))
    cfg["qa"]["roles"]["review"] = {"provider": "copilot",
                                    "model": "kimi-k2.7-code"}
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)

    report = crew_config.model_report(str(root), which=_no_cli)
    review = next(r for r in report["qa"] if r["role"] == "review")

    assert review["display"] == "Kimi 2.7 (kimi-k2.7-code)"


def test_the_report_labels_a_config_read_when_no_dispatch_exists(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    report = crew_config.model_report(str(root), which=_no_cli)
    assert report["authorSource"] == "config"
    assert report["dispatch"] is None


def test_the_report_includes_a_role_the_user_pinned_that_crew_does_not_name(
        tmp_path):
    cfg = json.loads(json.dumps(PINNED))
    cfg["dev"]["roles"]["house-style-cop"] = {"provider": "codex",
                                              "model": "gpt-6-astra"}
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    report = crew_config.model_report(str(root), which=_no_cli)
    assert "house-style-cop" in {r["role"] for r in report["dev"]}


def test_the_printed_report_names_the_guard_and_the_fallback(tmp_path, capsys):
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")
    assert crew_config.main(["--root", str(root), "--models"]) == 0
    out = capsys.readouterr().out
    assert "BARRED" in out
    assert "fallback armed: claude-sonnet-5" in out
    assert "recorded at dispatch" in out


def test_the_printed_report_says_a_config_read_is_not_a_dispatch(
        tmp_path, capsys):
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    assert crew_config.main(["--root", str(root), "--models"]) == 0
    assert "no dispatch recorded" in capsys.readouterr().out


# --- what runs when every pin is barred ------------------------------------
#
# The bar is only half the answer. `/crew:review` walks `qa.order` rather than
# stopping, so a report that prints four BARRED rows and says nothing else has
# withheld the half the reader can act on. The pre-0.16.0 command printed a
# `NO INDEPENDENT REVIEWER` line; these keep it from being lost to the table
# that replaced it.


def _all_cli(name):
    return f"/usr/bin/{name}"


def test_the_fall_through_names_who_reviews_a_codex_authored_diff(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")

    report = crew_config.model_report(str(root), which=_all_cli)

    assert all(row["barred"] for row in report["qa"])
    assert report["independentReviewer"] is True
    by_provider = {c["provider"]: c for c in report["qaFallThrough"]}
    assert by_provider["codex"]["eligible"] is False
    assert "wrote this diff" in by_provider["codex"]["why"]
    # Kimi is a different family from the gpt author, so it answers.
    assert by_provider["copilot"]["eligible"] is True
    assert by_provider["copilot"]["family"] == "kimi"
    assert by_provider["claude"]["eligible"] is True


def test_an_unpinned_copilot_has_no_knowable_family_and_cannot_review(tmp_path):
    cfg = json.loads(json.dumps(PINNED))
    cfg["qa"]["copilot"]["model"] = None
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)

    report = crew_config.model_report(str(root), which=_all_cli)
    copilot = next(c for c in report["qaFallThrough"]
                   if c["provider"] == "copilot")

    assert copilot["eligible"] is False
    assert "qa.copilot.model" in copilot["why"]


def test_a_provider_missing_from_path_is_not_a_candidate(tmp_path):
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")
    report = crew_config.model_report(str(root), which=_no_cli)
    assert [c["provider"] for c in report["qaFallThrough"] if c["eligible"]] \
        == ["claude"]
    assert next(c for c in report["qaFallThrough"]
                if c["provider"] == "copilot")["why"] == "not on PATH"


def test_no_independent_reviewer_is_stated_when_nothing_can_review(tmp_path):
    # Claude authored it and claude is the only reachable candidate: the one
    # state /crew:review cannot fix by trying harder.
    cfg = json.loads(json.dumps(PINNED))
    cfg["dev"]["roles"]["developer"] = {"provider": "claude", "model": None}
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "claude", None)

    report = crew_config.model_report(str(root), which=_no_cli)

    assert report["authorFamily"] == "claude"
    assert report["independentReviewer"] is False


def test_the_printed_report_states_the_fall_through_beside_the_bars(
        tmp_path, capsys):
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")
    assert crew_config.main(["--root", str(root), "--models"]) == 0
    out = capsys.readouterr().out
    assert "BARRED" in out
    assert "fall-through" in out
    # The conclusion, not just the evidence.
    assert "answers for any role barred above" in out


def test_the_printed_report_says_no_independent_reviewer_when_there_is_none(
        tmp_path, capsys, monkeypatch):
    cfg = json.loads(json.dumps(PINNED))
    cfg["dev"]["roles"]["developer"] = {"provider": "claude", "model": None}
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "claude", None)
    monkeypatch.setattr(crew_config.shutil, "which", _no_cli)

    assert crew_config.main(["--root", str(root), "--models"]) == 0
    out = capsys.readouterr().out

    assert "NO INDEPENDENT REVIEWER" in out
    assert "does not count as an independent review" in out


# --- what /crew:model's status column is allowed to claim -------------------


def _row(**kw):
    base = {"kind": "qa", "role": "review", "provider": "copilot",
            "model": None, "family": None, "barred": False, "barredBy": None,
            "providerOnPath": True}
    base.update(kw)
    return base


def test_an_unknown_family_is_not_reported_as_eligible():
    """QA sweep, 2026-09-05. An unpinned `copilot` has no knowable family --
    Copilot hosts several and an unset model does not say which, so it may be
    serving the author's own. `order_candidates` has always refused it for
    exactly that reason; the human-facing table printed the bare word
    `eligible` at the same config. The gate was right and the report was
    optimistic, which is the worse half to get wrong: a reader acts on the
    table."""
    status = crew_config.role_status(_row())
    assert "eligible" != status
    assert "CANNOT PROVE INDEPENDENCE" in status
    assert "qa.copilot.model" in status


def test_a_known_different_family_is_eligible():
    status = crew_config.role_status(
        _row(provider="codex", model="gpt-6-astra", family="gpt"))
    assert status == "eligible"


def test_a_barred_row_says_which_family_barred_it():
    status = crew_config.role_status(
        _row(provider="codex", model="gpt-6-astra", family="gpt",
             barred=True, barredBy="gpt"))
    assert status.startswith("BARRED")
    assert "gpt" in status


def test_auto_says_it_walks_the_order():
    assert crew_config.role_status(
        _row(provider="auto")) == "walks qa.order"


def test_a_dev_row_never_borrows_the_reviewer_verdict():
    """`model_report` resolves dev rows with no author, so `barred` is False
    on every one of them. Printing `eligible` there implied they passed a
    check that was never run."""
    status = crew_config.role_status(
        _row(kind="dev", role="developer", provider="codex",
             model="gpt-6-astra", family="gpt"))
    assert "eligible" not in status
    assert "implements" in status


def test_an_unknown_family_dev_row_is_not_flagged_either():
    """The guard does not govern authorship, so an unpinned dev provider is
    not an independence problem and must not be reported as one."""
    status = crew_config.role_status(_row(kind="dev", role="developer"))
    assert "CANNOT PROVE" not in status


# --- Codex round 1 on PR #66 ------------------------------------------------


def test_an_unreadable_branch_keeps_the_named_branch_history(tmp_path):
    """Codex finding 1, Critical.

    The history filter is `item["branch"] == here`. When `here` is None --
    a detached HEAD, a rebase in progress, or git simply failing to answer --
    that keeps only branchless records and DISCARDS every named-branch one.
    So: codex dispatches on `feature` and writes the diff, claude dispatches
    later on `main` and takes the slot, the reviewer looks at the feature
    commit in detached HEAD, and the whole codex history is thrown away. The
    stale path then strikes claude and the config family, and codex is clear
    to review its own diff.

    `here is None` is not evidence that nothing named a branch. It is the
    absence of evidence, which is the state this guard is supposed to fail
    closed on -- so every record is kept and every family struck.
    """
    cfg = copy.deepcopy(PINNED)
    cfg["dev"]["roles"]["developer"] = {"provider": "copilot",
                                        "model": "kimi-k3"}
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=True)
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra", branch="feature")
    crew_state.record_dispatch(str(root), "dev", "developer", "claude", None,
                               branch="main")

    real = crew_state.current_branch
    try:
        crew_state.current_branch = lambda _root: None
        authors, source = crew_state.author_families(str(root), cfg)
    finally:
        crew_state.current_branch = real

    assert source == "stale"
    assert "gpt" in authors, "an unreadable branch must not drop history"
    assert "claude" in authors


def test_a_non_git_directory_still_only_keeps_its_own_records(tmp_path):
    """The control for the fix above. A directory that is PROVABLY not a
    repository has no branches to confuse, which is the one case where a
    None `here` is evidence rather than the absence of it -- so it keeps its
    branchless records and does not widen to everything ever recorded."""
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=False)
    crew_state.record_dispatch(str(root), "dev", "developer", "copilot",
                               "kimi-k3", branch="left-over-branch")
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")

    authors, source = crew_state.author_families(str(root), PINNED)

    assert source == "dispatch"
    assert authors == frozenset({"gpt"})


def test_the_history_bound_is_spent_per_family_not_per_model(tmp_path):
    """Codex finding 2, High.

    The dedup key was `(provider, model, branch)` and the bound is ten. One
    provider cycling through ten model ids on the same branch therefore fills
    the entire history and evicts the family that actually wrote the diff --
    and the guard consumes FAMILIES, so those ten entries carry one bit of
    information between them. Deduplicating on the family is what makes the
    bound mean "ten families deep" rather than "ten model strings deep".
    """
    cfg = copy.deepcopy(PINNED)
    cfg["dev"]["roles"]["developer"] = {"provider": "claude", "model": None}
    root = crew_fixtures.make_repo(tmp_path, config=cfg, git=True)
    here = crew_state.current_branch(str(root))

    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra", branch=here)
    for n in range(crew_state.DISPATCH_HISTORY_MAX + 4):
        crew_state.record_dispatch(str(root), "dev", "developer", "copilot",
                                   f"kimi-k{n}", branch=here)

    authors, _source = crew_state.author_families(str(root), cfg)
    assert "gpt" in authors, "one provider's model churn evicted the author"
    assert "kimi" in authors


def test_two_unknown_families_are_not_deduplicated_into_one(tmp_path):
    """Deduplicating on the family must not collapse the case where the
    family is genuinely unknown: two unpinned providers are two candidates,
    not one, and `family()` answers None for both."""
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=True)
    here = crew_state.current_branch(str(root))
    crew_state.record_dispatch(str(root), "dev", "developer", "copilot", None,
                               branch=here)
    crew_state.record_dispatch(str(root), "dev", "developer", "windsurf", None,
                               branch=here)

    history = crew_state.read_dispatch(str(root))["devHistory"]
    providers = {item["provider"] for item in history}
    assert providers == {"copilot", "windsurf"}


def test_the_dispatch_read_happens_inside_the_lock(tmp_path):
    """Codex finding 3, High.

    Writing the file atomically stops a torn READ and does nothing about the
    read-modify-write: two dispatches both read history H, both append their
    own entry, and whichever replaces last publishes `H + itself`. The other
    dispatch is gone, and if it was the one that wrote the diff its family is
    never struck. The PM dispatches up to three roles in parallel, so this is
    the ordinary case rather than a contrived one.

    The property that closes it is not "the write is atomic" -- it already
    was -- but "the READ is inside the lock too". That is what this asserts,
    deterministically: with the lock held, a concurrent `record_dispatch` must
    not have read anything yet, and must finish once it is released. Racing
    two threads and hoping to catch the window would be a flaky test of a
    guard, which is worse than no test at all.
    """
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=True)
    crew_state.record_dispatch(str(root), "dev", "developer", "codex",
                               "gpt-6-astra")
    reads = []
    real_read = crew_state.read_dispatch

    def counting_read(target):
        reads.append(target)
        return real_read(target)

    def dispatch():
        crew_state.record_dispatch(str(root), "dev", "developer", "copilot",
                                   "kimi-k3")

    worker = threading.Thread(target=dispatch)
    try:
        crew_state.read_dispatch = counting_read
        with crew_state._dispatch_lock(str(root)) as held:  # pylint: disable=protected-access
            assert held, "the lock must be free in a fresh fixture"
            worker.start()
            time.sleep(0.3)
            assert not reads, "the read ran outside the lock"
            assert worker.is_alive(), "the writer did not wait for the lock"
        worker.join(timeout=20)
        assert not worker.is_alive(), "the writer never got the lock"
    finally:
        crew_state.read_dispatch = real_read

    assert reads, "the writer must proceed once the lock is released"
    families = {crew_state.family(item["provider"], item["model"])
                for item in crew_state.read_dispatch(str(root))["devHistory"]}
    assert families == {"gpt", "kimi"}, "a concurrent dispatch was lost"


def test_a_stale_lock_does_not_wedge_dispatch_forever(tmp_path):
    """A lock with no expiry is a new way to break: a killed dispatch leaves
    the file behind and every later one blocks on a holder that is gone. The
    lock is reclaimed once it is older than its TTL, the same rule
    `verify-gate` already applies to its own."""
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=True)
    lock = os.path.join(str(root), *crew_state.DISPATCH_LOCK_PATH)
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    with open(lock, "w", encoding="utf-8") as handle:
        handle.write("held by a process that died\n")
    old = time.time() - crew_state.DISPATCH_LOCK_TTL - 5
    os.utime(lock, (old, old))

    record = crew_state.record_dispatch(str(root), "dev", "developer",
                                        "codex", "gpt-6-astra")
    assert record["dev"]["provider"] == "codex"
    assert not os.path.exists(lock), "the lock must be released on exit"


# --- finding 4: the report must not outrank the gate ------------------------


def test_a_role_whose_cli_is_absent_is_not_reported_eligible():
    """Codex finding 4, Medium. `order_candidates` refuses a provider that is
    not on PATH; `role_status` said `eligible` at the same config because it
    only looked at the family. The report outranking the gate is the exact
    bug this pass was fixing, so getting it wrong in the other direction is
    not an improvement."""
    status = crew_config.role_status(
        _row(provider="codex", model="gpt-6-astra", family="gpt",
             providerOnPath=False))
    assert "eligible" != status
    assert "NOT ON PATH" in status


def test_on_path_is_still_not_claimed_as_working_auth():
    status = crew_config.role_status(
        _row(provider="codex", model="gpt-6-astra", family="gpt",
             providerOnPath=True))
    assert status == "eligible"


def test_model_report_records_whether_each_role_provider_resolves(tmp_path):
    """`role_status` cannot answer the PATH question on its own -- the row has
    to carry it, or the printer would be back to guessing."""
    root = crew_fixtures.make_repo(tmp_path, config=PINNED, git=True)
    report = crew_config.model_report(str(root), which=lambda _t: None)
    for row in report["qa"] + report["dev"]:
        assert "providerOnPath" in row
        if row["provider"] == "claude":
            assert row["providerOnPath"] is True
        elif row["provider"] != "auto":
            assert row["providerOnPath"] is False
