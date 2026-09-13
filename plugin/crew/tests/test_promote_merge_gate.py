"""`/crew:promote` is the first consumer of `bitbucket.mergeGate`, and it is
prose. Nothing parses `commands/promote.md` at runtime -- an agent reads it and
acts -- so a test is the only thing that can keep it honest about a script it
does not import, in another marketplace entry it does not bundle.

Same two directions as `test_docs_routing.py`, and the second is again the one
that earns its keep:

  * The command SAYS the things the design decided -- `merge_gate.sh` is
    routed, `enabled: false` means do nothing *at all*, `branch: null` means
    the script resolves the branch, `preset` binds to nothing, and no live
    write happens without a yes at that moment.
  * The interface it names actually EXISTS. The flags are asserted by RUNNING
    `merge_gate.sh` and reading how its own argument loop answers, never by
    grepping for the strings -- the usage block is a `sed` of the script's own
    header comment, so a grep "confirms" a flag whether or not it is wired.
    The load-bearing case is the negative one: `--preset` must be REJECTED,
    because the whole reason `bitbucket.mergeGate.preset` stays unwired is that
    no such flag exists.

Every run here is offline. `BB_CMD` is pointed at `false`, which cannot make a
network call, and the `--preset` cases are answered by the argument loop before
any transport is reached at all. Nothing in this file may be pointed at a real
workspace.
"""
import os
import shutil
import subprocess

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_state
import pytest

import crew_fixtures

_PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
_PROMOTE = os.path.join(_PLUGIN, "commands", "promote.md")
_CONFIG_MD = os.path.join(_PLUGIN, "CONFIG.md")

# Outside the crew plugin on purpose, exactly as `test_docs_routing.py` reaches
# into doc-builder. The claim under test is "crew's prose describes another
# marketplace entry's real interface", and it cannot be checked without looking
# at that entry.
_REPO = os.path.join(_PLUGIN, os.pardir, os.pardir)
_MERGE_GATE = os.path.join(
    _REPO, "skills", "bitbucket", "scripts", "merge_gate.sh")

# Renamed from `## The Bitbucket merge gate` when GitHub got a twin. The
# heading is the section's only handle, so the rename has to be made here
# deliberately rather than by widening the split until something matches -- and
# `test_the_gate_section_is_named_for_both_providers` below asserts the new
# name covers both, so a silent revert to the Bitbucket-only heading fails
# rather than quietly shrinking the section's scope back.
_SECTION = "## The merge gate"

# Exit code 2 in merge_gate.sh -- `E_USAGE`, at :33.
_E_USAGE = 2

_BASH = crew_fixtures.resolve_bash()


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _flat(text):
    """One line, single-spaced.

    Every phrase assertion below runs against this rather than the raw file.
    Both documents are hard-wrapped, so a sentence that reads as one phrase is
    split by a newline at an arbitrary word -- and an assertion that happens to
    sit inside one line today starts failing when the paragraph reflows, which
    is a test breaking on formatting rather than on meaning. Structural
    assertions (list items, bullet splitting) still use the raw text, because
    there the line IS the thing under test.
    """
    return " ".join(text.split())


def _gate_section():
    """The `## The Bitbucket merge gate` section on its own.

    Bounded at the next top-level heading rather than read to end of file: the
    `## What is enforced` section further down also mentions the merge gate, so
    an unbounded read would let an assertion pass on a sentence from a
    different section than the one under test.
    """
    text = _read(_PROMOTE)
    parts = text.split("\n" + _SECTION + "\n")
    assert len(parts) == 2, f"expected exactly one `{_SECTION}` heading"
    return parts[1].split("\n## ", 1)[0]


def _requires_the_bitbucket_skill():
    if not os.path.isfile(_MERGE_GATE):
        pytest.skip(
            "the bitbucket skill is not in this checkout at "
            f"{os.path.normpath(_MERGE_GATE)} -- crew's tests are running "
            "outside the marketplace repo, so the cross-entry claim cannot be "
            "checked here"
        )
    if _BASH is None:
        pytest.skip("needs bash to run merge_gate.sh")
    if shutil.which("jq") is None:
        pytest.skip(
            "merge_gate.sh refuses to start without jq (`command -v jq` at "
            "merge_gate.sh:78), so its argument loop cannot be reached here")


def _run_gate(*args):
    """Run `merge_gate.sh` offline and return the completed process.

    `BB_CMD=false` is the safety rail: `false` is a real program that exits 1
    and cannot reach the network, so a run that gets past argument parsing
    fails at the transport instead of touching a workspace. The workspace and
    repository names are deliberately not resolvable.
    """
    env = dict(os.environ, BB_CMD="false")
    return subprocess.run(
        [_BASH, _MERGE_GATE, *args],
        capture_output=True, text=True, check=False, timeout=120,
        stdin=subprocess.DEVNULL, env=env)


# ------------------------------------------------- what the command SAYS --


def test_promote_routes_merge_gate_sh_and_stops_when_it_is_absent():
    """The call site. Before this, `bitbucket.mergeGate` configured a gate no
    crew command mentioned -- `commands/promote.md` said "bitbucket" nowhere --
    so there was nothing for the three keys to attach to.

    The script is asserted by its repo-relative path, because "reference, do
    not bundle" is the rule: crew must send the reader to the bitbucket
    entry's own script rather than describe an API call it could make itself.
    """
    flat = _flat(_gate_section())

    assert "skills/bitbucket/scripts/merge_gate.sh" in flat

    # Not installed is a STOP, and it must name that it is one. "Could not
    # check" collapsing into "checked, and fine" is the failure this repo
    # keeps rediscovering, so the absence of the skill has to be visible.
    assert "not installed" in flat
    assert "stop" in flat.lower()

    # And it must forbid improvising the call, which is the tempting repair.
    assert "branch-restrictions" in flat


def test_enabled_false_means_do_nothing_at_all():
    """The binding rule with an opposite: `false` may not be read as "apply the
    disabled state". `disable` DELETES branch restrictions, so that reading
    would make a shipped default strip protections from every repo that never
    asked crew for a gate -- the opposite action against a live repo from the
    one a `false` in a config file expresses.

    Its own test function on purpose. Sharing one with the routing assertion
    would let a mutation of this claim trip the earlier line, print RED, and
    leave the claim itself unchecked -- the vacuous-assertion trap written up
    in `sabotage.py`'s header."""
    flat = _flat(_gate_section())

    assert "`enabled: false`" in flat
    assert "do nothing at all" in flat

    # The prohibition itself, not merely the absence of the wrong words. The
    # sentence exists in order to forbid the opposite reading, so asserting
    # that the forbidding is still there is what catches its deletion.
    assert "apply the disabled preset" in flat

    # `export` is read-only against the file system and a real API call
    # against Bitbucket, so "do nothing" has to rule it out by name.
    assert "not even `export`" in flat


def test_branch_null_is_resolved_by_the_script_never_guessed_by_promote():
    """`null` means "ask the API which branch this repo calls main", and the
    only thing entitled to answer is `merge_gate.sh`. A promote that
    substituted `main` would be wrong silently on a `master` or Gitflow
    `develop` repo: the gate would look configured and watch a branch nobody
    merges into."""
    flat = _flat(_gate_section())

    assert "`null` (the default)" in flat
    assert ".mainbranch.name" in flat

    # The guess is named and forbidden. Without this the table above reads as
    # advice rather than a rule, and `main` is the obvious improvisation.
    assert "Never substitute `main`" in flat

    # A set value binds to the flag verbatim -- the other half of the key.
    assert "--branch" in flat


def test_preset_is_named_in_order_to_say_it_binds_to_nothing():
    """The key had nothing to bind to, and the failure mode is quiet: letting
    `"standard"` mean "whatever `PRESET` holds" makes the word read as a value
    that was honoured, and it would go on reading that way after `PRESET`
    changed underneath it.

    So the command must state the absence, and state where the applied preset
    really comes from."""
    flat = _flat(_gate_section())

    assert "no `--preset` flag" in flat
    assert "`PRESET`" in flat
    assert "hardcoded" in flat


def test_the_two_write_subcommands_preview_differently():
    """`disable` takes `--dry-run`; `enable` does not. Collapsing them into one
    "use --dry-run" line is this repo's named recurring bug -- an unknown
    wearing the label of a check that happened -- because the reader would take
    the yes as confirming a dry run that never ran.

    Asserted as two separate bullets, the way `test_docs_routing.py` splits the
    two degraded paths: checking the section for "--dry-run" somewhere survives
    rewriting the `enable` bullet into a copy of the `disable` one, and that
    rewrite is exactly the defect."""
    section = _gate_section()

    marker = "- **`"
    # Each bullet is truncated at the blank line that ends it. Without that
    # the LAST bullet runs to the end of the section and swallows every
    # paragraph after it -- including the one about promote's own `--dry-run`
    # -- so `"--dry-run" in enable` would be satisfied by text belonging to
    # neither bullet, which is the conflation these two assertions exist to
    # catch.
    bullets = [b.split("\n\n", 1)[0] for b in section.split(marker)
               if b.startswith("disable`**") or b.startswith("enable`**")]
    assert len(bullets) == 2, section

    disable = _flat(next(b for b in bullets if b.startswith("disable`**")))
    enable = _flat(next(b for b in bullets if b.startswith("enable`**")))

    # The bounding is itself asserted, so a reflow that merges the bullets
    # into one paragraph fails here rather than quietly restoring the
    # swallowing this split exists to prevent.
    assert "runs **nothing**" not in enable, enable

    assert "--dry-run" in disable
    assert "destructive" in disable

    assert "no `--dry-run`" in enable
    assert "entire preview" in enable


def test_no_live_write_happens_without_a_yes_at_that_moment():
    """The standing rule, and the sentence that stops config from being read as
    permission. `enabled: true` authorises promote to look; it authorises no
    write."""
    flat = _flat(_gate_section())

    assert "Config is intent" in flat
    assert "not consent" in flat
    assert "Do not proceed on silence" in flat

    # promote's own --dry-run runs nothing -- `export` included, since it is a
    # real API call needing repository:admin exactly as a write does.
    assert "runs **nothing**" in flat
    assert "repository:admin" in flat


def test_disable_then_a_bare_enable_is_forbidden():
    """`disable` removes more kinds than `PRESET` creates, so the pair silently
    drops whatever `restrict_merges` and `require_no_changes_requested` were.
    Only `enable --from-export` puts back what was there
    (`skills/bitbucket/SKILL.md:123-126`)."""
    flat = _flat(_gate_section())

    assert "Never `disable` and then a bare `enable`" in flat
    assert "--from-export" in flat
    assert "restrict_merges" in flat


def test_the_scripts_three_non_failure_outcomes_are_relayed_separately():
    """Exit 3, exit 4 and `not-available-on-this-plan` are three different
    answers and flattening them loses the part the reader needs. Exit 4 is the
    expensive one: the live repo is PARTIALLY changed, and reporting it as
    "failed" reads as "nothing happened", which is false."""
    flat = _flat(_gate_section())

    assert "exit 3" in flat
    assert "nothing was deleted" in flat

    assert "exit 4" in flat
    assert "partially" in flat.lower()

    assert "not-available-on-this-plan" in flat


def test_the_merge_gate_is_listed_as_not_enforced():
    """No hook fires on `merge_gate.sh`, and `promote-gate.sh` does not read
    `bitbucket.mergeGate` at all. A section that reads like a gate while
    nothing enforces it is the gap that part of promote.md exists to state."""
    not_enforced = _read(_PROMOTE).split("**NOT enforced", 1)
    assert len(not_enforced) == 2

    tail = _flat(not_enforced[1])
    assert "merge_gate.sh" in tail
    assert "promote-gate.sh" in tail


# ------------------------------------------------------ the config half --


def test_config_md_says_what_each_default_means():
    """§9's rule: whoever writes the first consumer decides what the default
    *means*, and must say so in the same change. That is the step `docs.theme`
    skipped, and undoing it cost a one-shot migration."""
    section = _read(_CONFIG_MD).split("## 8. `bitbucket.mergeGate`", 1)[1]
    flat = _flat(section.split("\n## ", 1)[0])

    assert "`enabled: false` means promote does nothing at all" in flat
    assert "`branch: null` means promote passes no `--branch`" in flat
    assert "`preset: \"standard\"` means nothing today" in flat

    # The reason `preset` waits, which is the part a later reader will want:
    # adding the flag is a change to another marketplace entry.
    assert "separate marketplace entry" in flat

    # And the still-true sentence this subsection replaced must survive: the
    # SCRIPT reads no crew config. The command does the reading.
    assert "does not read crew config" in flat


def test_the_three_keys_still_resolve_independently():
    """The config half of the same claim. All three are settable in both
    layers and merge independently -- a collapse would make the rules above
    undeliverable however clearly promote.md states them."""
    for dotted in ("bitbucket.mergeGate.enabled",
                   "bitbucket.mergeGate.branch",
                   "bitbucket.mergeGate.preset"):
        assert crew_config.is_global_path(dotted), dotted

    defaults = crew_config.default_config()["bitbucket"]["mergeGate"]
    assert defaults == {"enabled": False, "branch": None, "preset": "standard"}

    merged = crew_state.merge_defaults(
        crew_config.default_config(),
        {"bitbucket": {"mergeGate": {"enabled": True, "branch": "release/*"}}})
    gate = merged["bitbucket"]["mergeGate"]

    assert gate["enabled"] is True
    assert gate["branch"] == "release/*"
    # Untouched by the override, which is what makes "a value means
    # `--branch <value>`" a different case from the default.
    assert gate["preset"] == "standard"


# ------------------------------- what the script actually accepts, by running --


@pytest.mark.parametrize("subcommand,flags", [
    ("disable", ["--branch", "release/*", "--dry-run"]),
    ("enable", ["--branch", "release/*"]),
    ("enable", ["--from-export", "no-such-export.json"]),
])
def test_merge_gate_sh_accepts_every_flag_promote_passes(subcommand, flags):
    """The direction a grep cannot check. `usage()` is a `sed` of the script's
    own header comment (`merge_gate.sh:70-73`), so grepping either the script
    or crew's prose for `--dry-run` "confirms" it whether or not the argument
    loop handles it. The loop's own answer is the evidence.

    An accepted flag is asserted negatively -- NOT a usage error -- because
    these runs go on to fail at the transport on purpose. `BB_CMD=false`
    cannot reach the network, so the only exits available are the argument
    loop's and a failure below it."""
    _requires_the_bitbucket_skill()

    proc = _run_gate(subcommand, "no-such-workspace", "no-such-repo", *flags)

    assert "unknown option" not in proc.stderr, proc.stderr[-600:]
    assert proc.returncode != _E_USAGE, (proc.returncode, proc.stderr[-600:])
    # jq vanishing mid-suite would exit 1 before the argument loop and make the
    # assertions above vacuously true, so rule that failure out by name rather
    # than letting it masquerade as a pass.
    assert "jq is required" not in proc.stderr, proc.stderr[-600:]


@pytest.mark.parametrize("subcommand", ["disable", "enable"])
def test_merge_gate_sh_rejects_preset_which_is_why_the_key_stays_unwired(
        subcommand):
    """The assertion the whole `preset` decision rests on. If a `--preset` flag
    ever appears, this test goes red and CONFIG.md §8's reason for leaving the
    key unbound stops being true in the same run -- which is the only way that
    reason gets re-examined rather than inherited.

    Reached before any transport: both argument loops answer an unknown option
    with `usage` (`merge_gate.sh:318` and `:438`) before the first `bb_call`."""
    _requires_the_bitbucket_skill()

    proc = _run_gate(subcommand, "no-such-workspace", "no-such-repo",
                     "--preset", "standard")

    assert proc.returncode == _E_USAGE, (proc.returncode, proc.stderr[-600:])
    assert "unknown option: --preset" in proc.stderr, proc.stderr[-600:]
