"""`guards.*` -- the ratchet, the resolver, and the two shell flavours.

Three directions, and the third is the one that earns its keep:

  * The KEYS exist in both layers with the right defaults, and the ratchet is a
    table rather than five copies of one rule.
  * The RESOLVER answers `block`/`ask`/`allow` correctly and reports which
    layer narrowed it -- ignoring a repo's widening attempt silently is the
    same failure as honouring it, one step later.
  * The two GUARDS actually behave that way, asserted by RUNNING `guard.sh` and
    `guard.ps1` and reading their exit codes. `guard.sh` and `guard.ps1` drift
    independently -- three bypasses fixed in #132 were open in BOTH -- so every
    behavioural case here runs in both flavours or it is not covered.

The dangerous literals are assembled from fragments (`"terra" + "form"`) for
the same reason `test_guard_bypasses.py` does it: crew's own PreToolUse guard
reads the command that writes this file, and a literal `terraform apply` in the
source blocks the write.

Nothing here reaches a network or a real config. The machine-global path is
redirected by pointing HOME and USERPROFILE at `tmp_path` for every subprocess,
because `crew_state.GLOBAL_CONFIG_PATH` is computed from `expanduser("~")` at
import time and a subprocess re-imports it. `conftest.py`'s autouse fixture
covers the in-process half.

SABOTAGE-TEST THIS FILE before trusting it: see `sabotage.py`.
"""
import json
import os
import shutil
import subprocess
import sys

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_state
import crew_upgrade
import pytest

_HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      os.pardir, "hooks", "scripts")
_GUARD_SH = os.path.join(_HOOKS, "guard.sh")
_GUARD_PS1 = os.path.join(_HOOKS, "guard.ps1")
_CREW_CONFIG = os.path.join(_HOOKS, "crew_config.py")

# Fragment-assembled: see the module docstring.
_TF = "terra" + "form"
_TOFU = "to" + "fu"
_PUSH = "git " + "push"
_GH_MERGE = "gh " + "pr merge"


def _resolve_bash():
    """Git for Windows' `bin/bash.exe` shim, never the raw MSYS binary, which
    cannot resolve its own mount table from a non-MSYS parent. Same resolver as
    `test_promote_merge_gate.py`."""
    found = shutil.which("bash")
    if not found:
        return None
    shim = os.path.join(os.path.dirname(os.path.dirname(found)), "bin",
                        "bash.exe")
    return shim if os.path.isfile(shim) else found


_BASH = _resolve_bash()
_PWSH = shutil.which("pwsh")

needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")
needs_pwsh = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="guard.ps1 is the native-Windows flavour; needs Windows + pwsh")

# The command that trips each guard, and what the guard is called. One table,
# so a case added for one flavour cannot be missing from the other.
_TRIPS = {
    "terraformApply": f"{_TF} apply",
    "forcePush": f"{_PUSH} --force origin main",
    "adminMerge": f"{_GH_MERGE} 12 --admin",
}

# Commands that trip NO guard and must stay allowed at every policy. A guard
# that fires on these is worse than one that misses: it is the guard people
# switch off.
_INNOCENT = (
    f"{_TF} plan",
    f"{_TOFU} plan",
    f"{_PUSH} origin main",
    f"{_GH_MERGE} 12 --squash",
)


def _repo(tmp_path, guards=None, schema=None):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True, exist_ok=True)
    cfg = {"schema": crew_state.SCHEMA_CURRENT if schema is None else schema}
    if guards is not None:
        cfg["guards"] = guards
    (root / ".crew" / "config.json").write_text(json.dumps(cfg), "utf-8")
    return str(root)


def _home(tmp_path, guards=None):
    """A fake HOME carrying a machine-global crew config."""
    home = tmp_path / "home"
    (home / ".claude" / "crew").mkdir(parents=True, exist_ok=True)
    body = {} if guards is None else {"guards": guards}
    (home / ".claude" / "crew" / "config.json").write_text(
        json.dumps(body), "utf-8")
    return str(home)


def _global_file(tmp_path, guards=None, install=None):
    path = tmp_path / "global.json"
    body = {}
    if guards is not None:
        body["guards"] = guards
    if install is not None:
        body["install"] = install
    path.write_text(json.dumps(body), "utf-8")
    return str(path)


def _run_sh(root, home, command):
    payload = json.dumps({"tool_input": {"command": command}})
    return subprocess.run(
        [_BASH, _GUARD_SH.replace("\\", "/")], input=payload,
        capture_output=True, text=True, check=False, timeout=120,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=root, HOME=home,
                 USERPROFILE=home))


def _run_ps1(root, home, command):
    payload = json.dumps({"tool_name": "PowerShell",
                          "tool_input": {"command": command}})
    return subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _GUARD_PS1],
        input=payload, capture_output=True, text=True, check=False,
        timeout=120,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=root, HOME=home,
                 USERPROFILE=home, PSModulePath=""))


# ---- the keys themselves ---------------------------------------------------


def test_the_four_guards_are_declared_in_both_layers_and_default_to_block():
    """A key present in only one layer is the failure that makes the ratchet
    unreachable. A repo-only key cannot be narrowed by the machine owner; a
    global-only key fails `is_global_path`'s rule that every globally-settable
    key is a real repo key, and `filter_global` prunes it, so it takes effect
    nowhere while looking configured."""
    repo = crew_config.default_config()
    glob = crew_config.default_global_config()

    assert set(repo["guards"]) == set(crew_state.GUARD_NAMES)
    assert repo["guards"] == glob["guards"]
    for name in crew_state.GUARD_NAMES:
        assert repo["guards"][name] == "block", name
        assert crew_config.is_global_path(f"guards.{name}"), name


def test_github_merge_gate_is_declared_in_both_layers_without_a_preset():
    """`preset`'s ABSENCE is the decision, not an omission.
    `bitbucket.mergeGate.preset` binds to nothing -- CONFIG.md §8 records why it
    stays unwired -- so copying it here would ship that defect a second time,
    on purpose. Asserted negatively because a `preset` arriving later would
    otherwise pass every other test in this file."""
    repo = crew_config.default_config()
    glob = crew_config.default_global_config()

    assert repo["github"] == crew_upgrade.GITHUB_BLOCK
    assert glob["github"] == crew_upgrade.GITHUB_BLOCK
    assert set(repo["github"]["mergeGate"]) == {"enabled", "branch"}
    assert "preset" not in repo["github"]["mergeGate"]
    assert repo["github"]["mergeGate"]["enabled"] is False
    assert repo["github"]["mergeGate"]["branch"] is None
    for dotted in ("github.mergeGate.enabled", "github.mergeGate.branch"):
        assert crew_config.is_global_path(dotted), dotted


def test_the_guards_and_github_blocks_are_carried_by_an_upgrade():
    """A top-level block absent from `CONFIG_BLOCKS` is never written into an
    already-initialised repo -- the whole of the 0.16.0 qa/dev bug. Without
    this the keys ship to fresh repos only, and every existing one reads the
    built-in default forever while its config file says nothing."""
    carried = {key for key, _block in crew_upgrade.CONFIG_BLOCKS}
    for key in ("guards", "github"):
        assert key in carried, key


def test_the_schema_6_bump_reaches_a_repo_at_schema_5(tmp_path):
    """The delivery mechanism, not the transformation, and asserted through
    `run()` rather than `upgrade_config()`.

    `run()` returns "already current" for any config at or above
    SCHEMA_CURRENT without ever calling `upgrade_config`. Add a migration and
    forget the bump and it reaches only repos that were ALREADY behind --
    nobody it was written for, since every existing config sits at the
    then-current number. A fresh clone looks correct while every installed
    machine keeps the old defaults forever. Caught in review by Codex once
    already, by running it: status `already current`, value unchanged.

    A LITERAL 5, not `SCHEMA_CURRENT - 1`. Deriving the fixture from the
    constant under test makes the test move with the mutation: revert the bump
    and `SCHEMA_CURRENT - 1` becomes 4, which is behind either way, so the repo
    still migrates and the test still passes. That is exactly how
    `test_install_policy.py`'s schema-4 sibling went vacuous when this bump
    landed -- it stays correct about a schema-4 repo and can no longer detect a
    missing bump. Bump this literal deliberately when the schema moves; that
    edit is the point, not an inconvenience.
    """
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"schema": 5, "tier": 0}), "utf-8")

    result = crew_upgrade.run(str(root), {})

    assert result["status"] != "already current"
    written = json.loads(
        (root / ".crew" / "config.json").read_text("utf-8"))
    assert written["schema"] == crew_state.SCHEMA_CURRENT
    assert written["guards"] == {name: "block"
                                 for name in crew_state.GUARD_NAMES}
    assert written["github"] == {"mergeGate": {"enabled": False,
                                               "branch": None}}
    # The keys are NAMED in the notes, or the report cannot say what it added.
    assert set(result["notes"]["guardKeysAdded"]) == set(
        crew_upgrade.SCHEMA_6_KEYS)


def test_a_three_part_key_does_not_crash_the_keys_added_walk():
    """`github.mergeGate.enabled` has three parts. The old loop unpacked
    exactly two (`block_key, leaf = dotted.split(".")`) and would have raised
    `ValueError` inside `upgrade_config` -- before `run()` writes anything, so
    loud rather than silent, but still a migration that dies at its first
    nested block."""
    _out, notes = crew_upgrade.upgrade_config({"schema": 5})
    assert "github.mergeGate.enabled" in notes["guardKeysAdded"]
    # A config that already carries the key is not reported as having just
    # gained it -- computed from the incoming file, not from the version.
    _out, notes = crew_upgrade.upgrade_config(
        {"schema": 5, "github": {"mergeGate": {"enabled": True}}})
    assert "github.mergeGate.enabled" not in notes["guardKeysAdded"]
    assert "github.mergeGate.branch" in notes["guardKeysAdded"]


def test_the_cli_prints_every_key_list_the_report_does():
    """The filed defect, not repeated. Schema 5 added `install.policy`, wrote
    its paragraph into UPGRADE.md and printed NOTHING at the CLI -- so a repo
    with no `.crew/codemap/` (which is where UPGRADE.md is written) gained a
    key governing whether crew may run commands on the machine and said so
    nowhere the user would see.

    Asserted over the note keys rather than by grepping `main`'s source, so a
    THIRD list added later and forgotten at the CLI fails here too."""
    import inspect  # pylint: disable=import-outside-toplevel
    source = inspect.getsource(crew_upgrade.main)
    for key in ("providerKeysAdded", "installKeysAdded", "guardKeysAdded"):
        assert f'notes["{key}"]' in source, key


def test_the_migration_report_does_not_claim_a_neutrality_it_lacks():
    """`terraformApply` and `forcePush` at `block` are what the guard already
    did; `adminMerge` and `tofu` are NEW refusals. A report that said "the
    default is block, so nothing changed" would be an unknown wearing the
    label of a check that happened -- and the user meeting a command that ran
    yesterday being refused today would go looking for a bug in their
    tooling."""
    _out, notes = crew_upgrade.upgrade_config({"schema": 5})
    body = "\n".join(crew_upgrade._config_lines(notes))  # pylint: disable=protected-access

    assert "NOT entirely behaviour-neutral" in body
    assert "adminMerge" in body
    assert "tofu" in body


def test_an_unknown_guard_value_fails_closed_to_block():
    """Authority's rule and install policy's rule, for the third time: a guard
    policy buys a capability, so a typo must cost capability rather than grant
    it. `allowed`, `ALLOW ` and a non-string all have to land on `block`."""
    for value in ("allowed", "yes", "", None, True, 1, [], {"a": 1}):
        assert crew_state.normalise_guard_policy(value) == "block", value
    # ...and the spellings that ARE the value still work, whitespace and case
    # included, or the fail-closed rule becomes a fail-always rule.
    assert crew_state.normalise_guard_policy(" ALLOW ") == "allow"
    assert crew_state.normalise_guard_policy("Ask") == "ask"


def test_guard_policy_rank_orders_block_below_ask_below_allow():
    """The ONE function permitted to know the order. Every comparison in the
    ratchet is built on it, so an unknown ranking above `block` would make the
    whole thing fail open."""
    rank = crew_state.guard_policy_rank
    assert rank("block") < rank("ask") < rank("allow")
    assert rank("nonsense") == rank("block") == 0


# ---- the ratchet -----------------------------------------------------------


def test_the_ratchet_is_one_table_covering_install_policy_and_all_four_guards():
    """The generalisation itself. Five bespoke pairs of
    `effective_*`/`resolve_*` would be five mechanisms for one rule, and
    CLAUDE.md's lesson is that one mechanism can be wrong while two can
    disagree -- and then only one of them gets fixed.

    `pm.authority` is asserted ABSENT on purpose. It ratchets for the widening
    WARNING only; its two layers still resolve by ordinary precedence, and
    sweeping it in here would silently change how every repo's PM authority
    resolves."""
    assert set(crew_state.RATCHETED_KEYS) == {
        "install.policy", "guards.terraformApply", "guards.forcePush",
        "guards.adminMerge", "guards.mergeGate"}
    assert "pm.authority" not in crew_state.RATCHETED_KEYS
    assert crew_state.ratchet_spec("tracker") is None


def test_every_ratcheted_key_has_a_widening_note_for_every_one_of_its_tiers():
    """`plan_global_write`'s `! widens` line does `notes[granted]`, so a
    missing entry is a KeyError at the point of use. That is deliberate -- a
    warning that silently describes the wrong tier is worse than a crash -- and
    this is what keeps the crash from ever being reached."""
    for dotted, (tiers, _normalise, _rank) in \
            crew_state.RATCHETED_KEYS.items():
        _rank_fn, _norm, notes = crew_config._RATCHETED[dotted]  # pylint: disable=protected-access
        for tier in tiers:
            assert tier in notes, (dotted, tier)
            assert notes[tier], (dotted, tier)


@pytest.mark.parametrize("dotted", sorted(crew_state.RATCHETED_KEYS))
def test_the_effective_value_is_the_lower_rank_of_the_two_layers(dotted):
    """Narrowing-only, in both directions. The repo may ask for LESS than the
    machine allows and be obeyed; it may ask for more and be refused."""
    tiers, _normalise, _rank = crew_state.RATCHETED_KEYS[dotted]
    lowest, middle, highest = tiers
    eff = crew_state.effective_ratcheted

    assert eff(dotted, highest, lowest) == lowest     # repo widening refused
    assert eff(dotted, lowest, highest) == lowest     # repo narrowing obeyed
    assert eff(dotted, middle, highest) == middle
    assert eff(dotted, highest, middle) == middle
    assert eff(dotted, highest, highest) == highest
    # Absent on either side is the default, and the default is the floor.
    assert eff(dotted, None, highest) == lowest
    assert eff(dotted, highest, None) == lowest
    # An unknown ranks 0 on whichever layer carries it, so it can only narrow.
    assert eff(dotted, "nonsense", highest) == lowest


def test_a_key_that_does_not_ratchet_raises_rather_than_falling_back():
    """Silently resolving a ratcheted key by precedence is the exact failure
    the ratchet exists to prevent, and it would look like a working feature
    while a cloned repo widened what the machine allows. So a name that is not
    in the table is an error, not a default."""
    with pytest.raises(KeyError):
        crew_state.effective_ratcheted("tracker", "files", "files")


def test_a_repos_widening_attempt_is_ignored_AND_reported(tmp_path):
    """Both halves, and the second is the one that gets dropped. A value that
    quietly does nothing is worse than one refused out loud: a user who sets
    `allow` in a repo and watches crew keep refusing has no way to learn that
    their machine-global `block` is why, and the next step is to go looking for
    a bug in crew."""
    root = _repo(tmp_path, guards={"forcePush": "allow"})
    path = _global_file(tmp_path, guards={"forcePush": "ask"})

    row = crew_config.resolve_guard(root, "forcePush", path)

    assert row["effective"] == "ask"          # ignored
    assert row["repo"] == "allow"
    assert row["global"] == "ask"
    assert row["heldDownBy"] == "global"      # reported


def test_the_repo_may_narrow_and_is_named_as_the_one_doing_it(tmp_path):
    """The mirror case. `heldDownBy` has to name the REPO when the repo is the
    narrower layer, or the field reads as "the global file is in your way"
    whatever actually happened."""
    root = _repo(tmp_path, guards={"forcePush": "block"})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})

    row = crew_config.resolve_guard(root, "forcePush", path)

    assert row["effective"] == "block"
    assert row["heldDownBy"] == "repo"


def test_resolve_install_policy_still_answers_in_its_old_shape(tmp_path):
    """The wrapper's contract. `install_plan_for` and every existing test read
    exactly four keys off this; generalising the body must not change them, and
    the extra `path` key `resolve_ratcheted` returns has to be dropped."""
    root = _repo(tmp_path)
    path = _global_file(tmp_path, install={"policy": "ask"})

    row = crew_config.resolve_install_policy(root, path)

    assert set(row) == {"effective", "repo", "global", "heldDownBy"}
    assert row["effective"] == "manual"      # repo silent -> the floor
    assert row["global"] == "ask"
    assert row["heldDownBy"] == "repo"


# ---- --explain -------------------------------------------------------------


def test_explain_prints_the_ratcheted_value_not_the_merged_one(tmp_path):
    """Measured before it was fixed, not reasoned about: with a repo
    `install.policy: auto` over a machine-global `manual`, `--explain` printed
    `install.policy  repo  "auto"` while crew behaved as `manual`. A report
    that contradicts the run, in the direction that reads as "you have it" --
    the worst direction for a key that decides what crew may run."""
    root = _repo(tmp_path, guards={"forcePush": "allow"})
    path = _global_file(tmp_path, guards={"forcePush": "block"},
                        install={"policy": "manual"})
    os.makedirs(os.path.join(root, ".crew"), exist_ok=True)
    with open(os.path.join(root, ".crew", "config.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"schema": crew_state.SCHEMA_CURRENT,
                   "guards": {"forcePush": "allow"},
                   "install": {"policy": "auto"}}, handle)

    rows = {r["path"]: r for r in crew_config.explain_config(root, path)}

    assert rows["install.policy"]["value"] == "manual"
    assert rows["install.policy"]["source"] == "global"
    assert rows["guards.forcePush"]["value"] == "block"
    assert rows["guards.forcePush"]["source"] == "global"
    # The narrowing SOURCE, carried into the row rather than left implicit.
    assert rows["guards.forcePush"]["heldDownBy"] == "global"
    assert rows["guards.forcePush"]["repo"] == "allow"


def test_explain_names_the_narrowing_layer_in_its_printed_output(capsys,
                                                                 tmp_path):
    """The `source` column has one slot and there are two facts: which layer
    decided, and which layer is holding the key down. A table that prints only
    the first tells a user who set `allow` and got `block` nothing at all about
    why -- which is the state `heldDownBy` was added to prevent and which this
    report then reproduced by not printing it."""
    root = _repo(tmp_path, guards={"forcePush": "allow"})
    path = _global_file(tmp_path, guards={"forcePush": "block"})

    crew_config.main(["--root", root, "--global-path", path, "--explain"])
    out = capsys.readouterr().out

    assert "guards.forcePush" in out
    assert "holding this down" in out
    assert "repo asks `allow`" in out
    assert "machine-global asks `block`" in out


# ---- the decision the hooks read ------------------------------------------


@pytest.mark.parametrize("policy,expected", [("block", "block"),
                                             ("ask", "ask"),
                                             ("allow", "allow")])
def test_guard_decision_maps_each_policy_to_a_decision(tmp_path, policy,
                                                       expected):
    root = _repo(tmp_path, guards={"forcePush": policy})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})

    out = crew_config.guard_decision(root, "forcePush", _TRIPS["forcePush"],
                                     path)

    assert out["policy"] == policy
    assert out["decision"] == expected


def test_an_ask_marker_approves_one_command_and_not_the_next(tmp_path):
    """The whole `ask` design. A marker naming only the guard would be a
    standing grant -- approve one force push and every later one runs unasked,
    which is `allow` wearing `ask`'s label. Keyed on a digest of the command,
    so a second, different command asks again."""
    root = _repo(tmp_path, guards={"forcePush": "ask"})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})
    first = _TRIPS["forcePush"]
    second = f"{_PUSH} --force origin release"

    out = crew_config.guard_decision(root, "forcePush", first, path)
    assert out["decision"] == "ask"
    open(out["marker"], "w", encoding="utf-8").close()

    assert crew_config.guard_decision(
        root, "forcePush", first, path)["decision"] == "allow"
    assert crew_config.guard_decision(
        root, "forcePush", second, path)["decision"] == "ask"


def test_the_force_push_target_branch_is_named_or_said_to_be_unknown(tmp_path):
    """The design note left open whether `forcePush: allow` still refuses
    `main`. Settled: it honours the value everywhere -- the user chose it --
    with the compensating requirement that the target is NAMED. `unknown` is
    its own answer and never collapses into a plausible-looking `main`, which
    would be the "unknown wearing the label of a check that happened" failure
    this repo keeps rediscovering."""
    assert crew_config.push_target(f"{_PUSH} --force origin main") == "main"
    assert crew_config.push_target(
        f"{_PUSH} --force origin +release/1.2") == "release/1.2"
    assert crew_config.push_target(
        f"{_PUSH} --force origin HEAD:main") == "main"
    # No refspec: the branch comes from the upstream config and crew cannot
    # read it from the command line.
    assert crew_config.push_target(f"{_PUSH} --force") == "unknown"
    assert crew_config.push_target(f"{_PUSH} --force origin") == "unknown"
    # Not a push at all.
    assert crew_config.push_target(f"{_TF} apply") == "unknown"

    root = _repo(tmp_path, guards={"forcePush": "allow"})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})
    out = crew_config.guard_decision(root, "forcePush",
                                     f"{_PUSH} --force origin main", path)
    assert out["target"] == "main"


def test_under_allow_nothing_is_silent(tmp_path):
    """`allow` removes the question, not the record. Without the row there is
    no way to learn afterwards that crew force-pushed -- the stderr line is
    gone with the session, and the whole point of a machine owner choosing
    `allow` is that they were not asked at the time."""
    root = _repo(tmp_path, guards={"forcePush": "allow"})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})
    log = os.path.join(root, crew_state.GUARD_LOG_PATH)

    crew_config.guard_decision(root, "forcePush", _TRIPS["forcePush"], path,
                              record=True)

    assert os.path.isfile(log)
    row = open(log, encoding="utf-8").read().strip().split("\t")
    assert row[1:5] == ["forcePush", "allow", "allow", "main"]
    assert row[5] == _TRIPS["forcePush"]


def test_a_logged_command_cannot_forge_a_row(tmp_path):
    """The log is tab-separated and line-oriented and the command is arbitrary
    text off a hook payload. A tab or a newline in it would write a row that
    reads as a different decision. `crew_incident_log` normalises the same way
    and for the same reason."""
    root = _repo(tmp_path, guards={"forcePush": "allow"})
    path = _global_file(tmp_path, guards={"forcePush": "allow"})
    nasty = f"{_PUSH} --force\torigin\nblock\tblock\tfaked"

    crew_config.guard_decision(root, "forcePush", nasty, path, record=True)

    body = open(os.path.join(root, crew_state.GUARD_LOG_PATH),
                encoding="utf-8").read()
    assert body.count("\n") == 1
    assert len(body.strip().split("\t")) == 6


def test_the_cli_refuses_an_unknown_guard_name_rather_than_blocking_quietly(
        tmp_path, capsys):
    """Fail-closed is the CALLER's job, and both shells do it by treating any
    non-zero exit as `block`. Returning `block` quietly HERE would make a
    typo'd guard name look like a deliberate setting forever."""
    root = _repo(tmp_path)

    code = crew_config.main(["--root", root, "--guard", "forcepush",
                             "--command", "x"])

    assert code == 2
    assert "unknown guard" in capsys.readouterr().err


def test_the_cli_line_never_emits_an_empty_field(tmp_path, capsys):
    """TAB is IFS WHITESPACE in bash, so `IFS=$'\\t' read -r a b c` collapses a
    run of tabs and every field after an empty one shifts left by a slot.
    Measured: `guards.terraformApply` has no target branch, and guard.sh
    printed the REASON in the target's slot while guard.ps1 -- whose `-split`
    does not collapse -- printed it correctly. Two flavours disagreeing about a
    line they read from the same producer is the drift this shared CLI exists
    to prevent."""
    root = _repo(tmp_path)

    crew_config.main(["--root", root, "--guard", "terraformApply",
                      "--command", f"{_TF} apply"])
    line = capsys.readouterr().out.rstrip("\n")

    fields = line.split("\t")
    assert len(fields) == 5, fields
    assert all(fields), fields
    assert fields[3] == "-"      # no target branch for this guard


# ---- both shell flavours ---------------------------------------------------
#
# Every case below runs in BOTH. `guard.sh` and `guard.ps1` drift
# independently, and three of the bypasses fixed in #132 were open in both, so
# a case that runs in one flavour covers half of what it claims to.


@pytest.mark.parametrize("command", [
    f"{_GH_MERGE} 12 --admin --squash",
    f"{_GH_MERGE} --admin 12",
    f"{_TOFU} apply -auto-approve",
    f"{_TOFU} -chdir=infra destroy",
])
@needs_bash
def test_sh_blocks_the_refusals_schema_6_adds(tmp_path, command):
    """NEW refusals, run RED against `origin/main` before the fix: both
    flavours exited 0 for all four. The schema-6 migration note says so out
    loud rather than letting "the default is block, so nothing changed" cover
    it -- a command that ran yesterday is refused today, and a user told
    otherwise goes looking for a bug in their tooling."""
    root, home = _repo(tmp_path), _home(tmp_path)
    assert _run_sh(root, home, command).returncode == 2


@pytest.mark.parametrize("command", [
    f"{_GH_MERGE} 12 --admin --squash",
    f"{_GH_MERGE} --admin 12",
    f"{_TOFU} apply -auto-approve",
    f"{_TOFU} -chdir=infra destroy",
])
@needs_pwsh
def test_ps1_blocks_the_refusals_schema_6_adds(tmp_path, command):
    root, home = _repo(tmp_path), _home(tmp_path)
    assert _run_ps1(root, home, command).returncode == 2


@pytest.mark.parametrize("command", _INNOCENT)
@needs_bash
def test_sh_leaves_innocent_commands_alone(tmp_path, command):
    """A guard that fires on `plan`, an ordinary push or a normal merge is the
    guard people switch off, and then none of the others fire either."""
    root, home = _repo(tmp_path), _home(tmp_path)
    proc = _run_sh(root, home, command)
    assert proc.returncode == 0, (command, proc.stderr[-600:])


@pytest.mark.parametrize("command", _INNOCENT)
@needs_pwsh
def test_ps1_leaves_innocent_commands_alone(tmp_path, command):
    root, home = _repo(tmp_path), _home(tmp_path)
    proc = _run_ps1(root, home, command)
    assert proc.returncode == 0, (command, proc.stderr[-600:])


@pytest.mark.parametrize("guard", sorted(_TRIPS))
@needs_bash
def test_sh_honours_each_policy(tmp_path, guard):
    """block refuses, ask refuses while naming the command and the marker,
    allow lets it through and says so. The global layer is pinned to `allow`
    (the ceiling) so the REPO value is what varies -- with it left at the
    default the ratchet correctly holds every repo value down to `block`, which
    is its own test above."""
    command = _TRIPS[guard]
    home = _home(tmp_path, guards={name: "allow"
                                   for name in crew_state.GUARD_NAMES})

    root = _repo(tmp_path, guards={guard: "block"})
    proc = _run_sh(root, home, command)
    assert proc.returncode == 2
    assert "BLOCKED" in proc.stderr
    assert "= ask" not in proc.stderr

    root = _repo(tmp_path, guards={guard: "ask"})
    proc = _run_sh(root, home, command)
    assert proc.returncode == 2
    assert f"guards.{guard} = ask" in proc.stderr
    assert command in proc.stderr          # the EXACT command, printed
    marker = [ln for ln in proc.stderr.splitlines()
              if ".approved-guard-" in ln][-1].split(None, 1)[1].strip()
    open(marker, "w", encoding="utf-8").close()
    assert _run_sh(root, home, command).returncode == 0
    os.remove(marker)

    root = _repo(tmp_path, guards={guard: "allow"})
    proc = _run_sh(root, home, command)
    assert proc.returncode == 0
    # Under `allow` nothing is silent: said now, and written down.
    assert "ALLOWED" in proc.stderr
    assert command in proc.stderr
    assert os.path.isfile(os.path.join(root, crew_state.GUARD_LOG_PATH))


@pytest.mark.parametrize("guard", sorted(_TRIPS))
@needs_pwsh
def test_ps1_honours_each_policy(tmp_path, guard):
    """The identical assertions, in the other flavour. Written out rather than
    shared with the bash version through a helper: the two scripts are what is
    under test, and a helper that abstracted over them would be free to hide a
    difference in how each is invoked."""
    command = _TRIPS[guard]
    home = _home(tmp_path, guards={name: "allow"
                                   for name in crew_state.GUARD_NAMES})

    root = _repo(tmp_path, guards={guard: "block"})
    proc = _run_ps1(root, home, command)
    assert proc.returncode == 2
    assert "BLOCKED" in proc.stderr
    assert "= ask" not in proc.stderr

    root = _repo(tmp_path, guards={guard: "ask"})
    proc = _run_ps1(root, home, command)
    assert proc.returncode == 2
    assert f"guards.{guard} = ask" in proc.stderr
    assert command in proc.stderr
    marker = [ln for ln in proc.stderr.splitlines()
              if ".approved-guard-" in ln][-1].split("File ", 1)[1].strip()
    open(marker, "w", encoding="utf-8").close()
    assert _run_ps1(root, home, command).returncode == 0
    os.remove(marker)

    root = _repo(tmp_path, guards={guard: "allow"})
    proc = _run_ps1(root, home, command)
    assert proc.returncode == 0
    assert "ALLOWED" in proc.stderr
    assert command in proc.stderr
    assert os.path.isfile(os.path.join(root, crew_state.GUARD_LOG_PATH))


@pytest.mark.parametrize("guard", sorted(_TRIPS))
@needs_bash
def test_sh_a_repo_cannot_widen_past_the_machine(tmp_path, guard):
    """The ratchet, end to end, through the hook that actually runs. The
    in-process test above proves `effective_ratcheted`; this proves the guard
    reads the RESOLVED value rather than the repo's raw one -- which is the
    shape of bug that would make every unit test here pass while a cloned repo
    granted itself force-push rights on a stranger's machine."""
    root = _repo(tmp_path, guards={guard: "allow"})
    home = _home(tmp_path)          # no guards block: the floor, `block`
    assert _run_sh(root, home, _TRIPS[guard]).returncode == 2


@pytest.mark.parametrize("guard", sorted(_TRIPS))
@needs_pwsh
def test_ps1_a_repo_cannot_widen_past_the_machine(tmp_path, guard):
    root = _repo(tmp_path, guards={guard: "allow"})
    home = _home(tmp_path)
    assert _run_ps1(root, home, _TRIPS[guard]).returncode == 2


def _crippled_hooks(tmp_path):
    """A copy of the hook directory with `crew_config.py` removed.

    The resolver then exits non-zero for a reason neither script can talk its
    way around, which is the only way to reach the fail-closed branch without
    hiding python from a shell that needs it on PATH to start. A config file
    that merely parses badly is NOT this case -- `load_config` collapses
    malformed to absent on purpose, so the resolver still answers, correctly,
    with the floor.
    """
    dst = tmp_path / "crippled"
    dst.mkdir(exist_ok=True)
    for name in os.listdir(_HOOKS):
        src = os.path.join(_HOOKS, name)
        if os.path.isfile(src) and name != "crew_config.py":
            shutil.copyfile(src, dst / name)
    return str(dst)


@needs_bash
def test_sh_fails_closed_and_says_so_when_the_resolver_cannot_answer(tmp_path):
    """"Could not check" is its own outcome and never collapses into "checked,
    and fine". The `prod` rule further down has a cruder regex to fall back on;
    config layering has no cruder form, so the only honest answer is `block` --
    with the REASON said out loud, or the refusal reads as a policy the user
    chose and they will go looking for it in their config."""
    root = _repo(tmp_path, guards={"forcePush": "allow"})
    home = _home(tmp_path, guards={"forcePush": "allow"})
    crippled = _crippled_hooks(tmp_path)

    proc = subprocess.run(
        [_BASH, os.path.join(crippled, "guard.sh").replace("\\", "/")],
        input=json.dumps({"tool_input": {"command": _TRIPS["forcePush"]}}),
        capture_output=True, text=True, check=False, timeout=120,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=root, HOME=home,
                 USERPROFILE=home))

    assert proc.returncode == 2, proc.stderr[-600:]
    assert "could not read it" in proc.stderr, proc.stderr[-600:]


@needs_pwsh
def test_ps1_fails_closed_and_says_so_when_the_resolver_cannot_answer(
        tmp_path):
    root = _repo(tmp_path, guards={"forcePush": "allow"})
    home = _home(tmp_path, guards={"forcePush": "allow"})
    crippled = _crippled_hooks(tmp_path)

    proc = subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File",
         os.path.join(crippled, "guard.ps1")],
        input=json.dumps({"tool_name": "PowerShell",
                          "tool_input": {"command": _TRIPS["forcePush"]}}),
        capture_output=True, text=True, check=False, timeout=120,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=root, HOME=home,
                 USERPROFILE=home, PSModulePath=""))

    assert proc.returncode == 2, proc.stderr[-600:]
    assert "could not read it" in proc.stderr, proc.stderr[-600:]
