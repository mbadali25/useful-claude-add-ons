"""`/crew:gate` is prose, and prose is the only thing holding this workflow.

Nothing parses `commands/gate.md` at runtime -- an agent reads it and acts --
so a test is what keeps it honest about two marketplace entries crew does not
bundle, and about an ORDER whose whole risk is the order.

Same two directions as `test_docs_routing.py` and `test_promote_merge_gate.py`:

  * The command SAYS the things the design decided -- `guards.mergeGate` is
    read first, `block` refuses, a missing skill is a STOP, and the only
    restore is `--from-export`.
  * The interface it names EXISTS. Bitbucket's `merge_gate.sh` is on disk and
    its argument loop is asked directly, never grepped: `usage()` is a `sed` of
    the script's own header comment, so a grep "confirms" a flag whether or not
    it is wired. `skills/github/scripts/merge_gate.sh` is built in a parallel
    stream, so its presence is a SKIP and its absence is not a failure -- but
    the reference to it in the prose is asserted unconditionally, because that
    reference is what the parallel stream is being written against.

Every run here is offline. `BB_CMD=false` cannot reach a network.
"""
import os
import shutil
import subprocess

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_state
import pytest

_PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
_GATE = os.path.join(_PLUGIN, "commands", "gate.md")
_PROMOTE = os.path.join(_PLUGIN, "commands", "promote.md")
_REPO = os.path.join(_PLUGIN, os.pardir, os.pardir)
_BB_GATE = os.path.join(_REPO, "skills", "bitbucket", "scripts",
                        "merge_gate.sh")
_GH_GATE = os.path.join(_REPO, "skills", "github", "scripts", "merge_gate.sh")

_E_USAGE = 2


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _flat(text):
    """Whitespace-collapsed, for phrase assertions. The docs are hard-wrapped,
    so a phrase that spans a line break is absent from the raw text."""
    return " ".join(text.split())


def _resolve_bash():
    found = shutil.which("bash")
    if not found:
        return None
    shim = os.path.join(os.path.dirname(os.path.dirname(found)), "bin",
                        "bash.exe")
    return shim if os.path.isfile(shim) else found


_BASH = _resolve_bash()


def _requires_bitbucket():
    if not os.path.isfile(_BB_GATE):
        pytest.skip("the bitbucket skill is not in this checkout")
    if _BASH is None:
        pytest.skip("no MSYS/POSIX bash")
    if shutil.which("jq") is None:
        pytest.skip("merge_gate.sh needs jq before its argument loop")


def _run_bb(*args):
    return subprocess.run(
        [_BASH, _BB_GATE.replace("\\", "/"), *args], capture_output=True,
        text=True, check=False, timeout=120, stdin=subprocess.DEVNULL,
        env=dict(os.environ, BB_CMD="false"))


# ---- what the command SAYS -------------------------------------------------


def test_the_command_file_exists_and_declares_its_two_arguments():
    """The frontmatter is what puts the command in `/help` with a usable hint.
    A command whose `argument-hint` omits the provider is one users invoke with
    half an invocation."""
    text = _read(_GATE)
    assert text.startswith("---\n")
    head = text.split("---", 2)[1]
    assert "argument-hint:" in head
    assert "disable" in head and "enable" in head and "status" in head
    assert "github" in head and "bitbucket" in head


def test_guards_merge_gate_is_read_first_and_by_name():
    """FIRST, and that is the assertion. Resolving the provider or finding the
    script before reading the policy means a refused run has already made a
    real API call -- `export` needs admin scope exactly as a write does -- and
    "I only looked" is not a thing a refusal gets to do."""
    text = _read(_GATE)
    flat = _flat(text)

    assert "guards.mergeGate" in flat
    # Section 0, ahead of every other numbered section. Asserted on the
    # ORDER of the headings rather than on mere presence, because a step
    # that is present and third is the bug.
    headings = [ln for ln in text.split("\n") if ln.startswith("## ")]
    assert headings, text[:200]
    assert "guards.mergeGate" in headings[0], headings
    assert "first" in headings[0].lower(), headings
    # Read through crew_config, not out of .crew/config.json: the effective
    # value is the narrower of two layers and the repo file shows one of them.
    assert "crew_config.py" in flat
    assert "--guard mergeGate" in flat


def test_block_refuses_and_does_not_even_export():
    """`block` is the shipped default, so this is what the command does on
    almost every machine. Its own test function: sharing one with the routing
    assertion would let a mutation of this claim trip an earlier line, print
    RED, and leave the claim itself unchecked -- the vacuous-assertion trap in
    `sabotage.py`'s header."""
    flat = _flat(_read(_GATE))

    assert "Refuse, and say why" in flat
    # The prohibition on the read-only path specifically. `export` is a real
    # API call needing admin scope, so "do nothing" has to rule it out by name
    # or a refusal quietly does the most dangerous read available to it.
    assert "Do not run `status`" in flat
    assert "Do not run `export`" in flat


def test_a_missing_skill_is_a_stop_not_a_warning():
    """The collapse this repo keeps rediscovering: "could not check" becoming
    "checked, and fine". Here it would report a gate as down when nothing was
    read at all."""
    flat = _flat(_read(_GATE))

    assert "**stop**" in flat
    assert "crew bundles neither" in flat.lower()
    assert "could not check" in flat
    assert "checked, and fine" in flat
    # Never reimplement another entry's interface.
    assert "Do not hand-roll" in flat


def test_both_provider_scripts_are_named_by_their_real_paths():
    """The reference the parallel GitHub stream is being written against.
    Asserted unconditionally -- the path has to be in the prose whether or not
    the file is in this checkout yet, because the prose is the contract."""
    flat = _flat(_read(_GATE))

    assert "skills/bitbucket/scripts/merge_gate.sh" in flat
    assert "skills/github/scripts/merge_gate.sh" in flat


def test_the_only_restore_is_from_the_export():
    """`disable` removes more kinds than a preset creates, so `disable` then a
    bare `enable` leaves a gate that looks restored and is weaker than the one
    its owner built. The export is not a convenience; it is the only path
    back."""
    flat = _flat(_read(_GATE))

    assert "--from-export" in flat
    assert "Never `disable` and then a bare `enable`" in flat
    assert "The only restore is" in flat
    # And the export has to be taken by the SAME invocation that deletes, or
    # the backup and the delete can come apart.
    assert "--export-to" in flat
    assert "one invocation, not two" in flat


def test_the_two_scripts_differences_are_stated_rather_than_assumed():
    """The interface mismatch this test exists to prevent. GitHub's `export` is
    branch-scoped, its `enable` REQUIRES `--from-export`, and `--branch` on its
    `enable` is a usage error -- three ways a Bitbucket-shaped command fails
    against it, each silently if the prose does not say so."""
    flat = _flat(_read(_GATE))

    assert "branch-scoped" in flat
    assert "`--from-export` is REQUIRED" in flat
    assert "usage error" in flat
    assert "no preset" in flat.lower()


def test_the_four_exit_codes_are_relayed_as_themselves():
    """Three of the four are not "failed", and flattening them loses the part
    the reader needs. Exit 4 is the sharpest: "failed" on its own reads as
    "nothing happened", which is false and is the reading that gets someone to
    re-run it against a partially-changed repository."""
    flat = _flat(_read(_GATE))

    assert "exit 3" in flat
    assert "nothing was deleted" in flat.lower()
    assert "exit 4" in flat
    assert "partially" in flat
    assert "--allow-inherited" in flat
    assert "not-available-on-this-plan" in flat


def test_unreadable_never_collapses_into_none_configured():
    """The load-bearing case on GitHub: a classic-protection read without admin
    answers 404 `Not Found`, the same status as an unprotected branch. Only the
    exact message `Branch not protected` means absent."""
    flat = _flat(_read(_GATE))

    assert "unreadable" in flat
    assert "Branch not protected" in flat
    assert "404" in flat


# ---- promote routes through it --------------------------------------------


def test_promote_routes_through_crew_gate_and_covers_github():
    """The section used to be Bitbucket-only and composed `merge_gate.sh`
    commands itself. Two implementations of a sequence whose whole risk is the
    order of its steps is how the two come to disagree about that order."""
    flat = _flat(_read(_PROMOTE))

    assert "/crew:gate" in flat
    assert "github.mergeGate.enabled" in flat
    assert "guards.mergeGate" in flat
    # And it says what `block` means for promote's own report: not checked,
    # never checked-and-fine.
    assert "not checked" in flat


# ---- the config half -------------------------------------------------------


def test_guards_merge_gate_resolves_and_ratchets_like_the_others():
    """`mergeGate` is read by this command rather than by the command guard,
    which is exactly why it could have ended up with its own layering rule.
    It does not: it is in the one ratchet table with the other four keys."""
    assert "guards.mergeGate" in crew_state.RATCHETED_KEYS
    assert crew_config.is_global_path("guards.mergeGate")
    assert crew_state.effective_ratcheted(
        "guards.mergeGate", "allow", "block") == "block"


# ---- what the scripts actually accept, by running --------------------------


@pytest.mark.parametrize("subcommand,flags", [
    ("disable", ["--branch", "release/*", "--dry-run"]),
    ("disable", ["--export-to", "backup.json", "--dry-run"]),
    ("enable", ["--from-export", "no-such-export.json"]),
])
def test_bitbucket_merge_gate_sh_accepts_every_flag_gate_md_passes(
        subcommand, flags):
    """The direction a grep cannot check. `usage()` is a `sed` of the script's
    own header comment, so grepping either the script or crew's prose for
    `--dry-run` "confirms" it whether or not the argument loop handles it.

    An accepted flag is asserted NEGATIVELY -- not a usage error -- because
    these runs go on to fail at the transport on purpose: `BB_CMD=false` cannot
    reach the network, so the only exits available are the argument loop's and
    a failure below it."""
    _requires_bitbucket()

    proc = _run_bb(subcommand, "no-such-workspace", "no-such-repo", *flags)

    assert "unknown option" not in proc.stderr, proc.stderr[-600:]
    assert proc.returncode != _E_USAGE, (proc.returncode, proc.stderr[-600:])
    # jq vanishing mid-suite would exit 1 before the argument loop and make the
    # assertions above vacuously true.
    assert "jq is required" not in proc.stderr, proc.stderr[-600:]


def test_bitbucket_merge_gate_sh_has_no_status_subcommand():
    """Which is why `gate.md` tells a Bitbucket `status` to use `export` and to
    SAY it made a real API call. If a `status` subcommand ever lands, this goes
    red in the same run as the paragraph describing its absence."""
    _requires_bitbucket()

    proc = _run_bb("status", "no-such-workspace", "no-such-repo")

    assert proc.returncode == _E_USAGE, (proc.returncode, proc.stderr[-600:])
    assert "unknown subcommand: status" in proc.stderr, proc.stderr[-600:]


@pytest.mark.skipif(not os.path.isfile(_GH_GATE),
                    reason="skills/github/scripts/merge_gate.sh is being "
                           "built in a parallel stream")
def test_github_merge_gate_sh_matches_the_interface_gate_md_documents():
    """A SKIP while the parallel stream is in flight, and a real check the
    moment the file lands -- so the interface `gate.md` documents is verified
    against the script rather than against a message about the script.

    Deliberately NOT a `pytest.xfail` and not deleted: a skip that names the
    reason is the honest state, and it becomes coverage on its own the day the
    file appears."""
    proc = subprocess.run(
        [_BASH, _GH_GATE.replace("\\", "/"), "enable", "o", "r",
         "--branch", "main"],
        capture_output=True, text=True, check=False, timeout=120,
        stdin=subprocess.DEVNULL, env=dict(os.environ, GH_CMD="false"))

    # `--branch` on `enable` is a usage error, which is the difference from
    # Bitbucket that `gate.md` states and that a Bitbucket-shaped command
    # would otherwise hit silently.
    assert proc.returncode == _E_USAGE, (proc.returncode, proc.stderr[-600:])
