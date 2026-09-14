"""A `production` block crew cannot read must not read as "nothing declared".

`production_patterns` answered `[]` for four different states -- absent, an
empty list, a wrong-shaped value, and a config file it could not read at all --
and `crew_guards.prod_decision` treats an empty pattern list as "no declared
production target matches", which is an ALLOW that says so. So
`"hosts": "prod-web-*"` -- a string where a list belongs, the likeliest way to
write this key wrong -- silently disabled the host restriction completely, at
every level including `prodServer: none`, while the config still read as though
production had been declared. An unknown wearing the label of a check that
happened, in the guard whose entire job is to refuse.

The must-ALLOW cases carry as much weight as the must-block ones here: absent
and empty are the states the shipped default is in (`production: {"databases":
[], "hosts": []}`), so a fix that refused those would refuse every `ssh` in
every repo on the machine, which is the guard people switch off.

Both flavours run, and that is not ceremony. `guard.sh`'s `prod_guarded` and
`guard.ps1`'s `Invoke-ProdGuard` both `return` silently when the decision's
TARGET field is empty, before they look at the decision itself -- so a refusal
carrying no target is one both shells swallow on their way to exit 0. Nothing
in-process can show that; only running the hooks can.

SABOTAGE-TEST THIS FILE before trusting it: see `sabotage.py`.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_fixtures

_HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      os.pardir, "hooks", "scripts")
_GUARD_SH = os.path.join(_HOOKS, "guard.sh")
_GUARD_PS1 = os.path.join(_HOOKS, "guard.ps1")

_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")
needs_pwsh = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="guard.ps1 is the native-Windows flavour; needs Windows + pwsh")

# A write against a host that a declared `prod-web-*` would match. Assembled
# from fragments for the same reason test_guards.py does it: crew's own guard
# reads the command that writes this file.
_HOST = "prod-web-1"
_WRITE = "ssh root@" + _HOST + " systemctl restart nginx"
_READ = "ssh root@" + _HOST + " cat /etc/hostname"


def _repo(tmp_path, production, level="none", name="repo"):
    """A repo whose `production` block is exactly `production`.

    `production=None` writes no block at all, which is a different state from
    `{}` and from `{"hosts": []}` -- keeping the three separate is the point of
    the whole change, so the fixture must be able to build each one.
    """
    root = tmp_path / name
    (root / ".crew").mkdir(parents=True, exist_ok=True)
    cfg = {"guards": {"prodServer": level, "prodDatabase": level}}
    if production is not None:
        cfg["production"] = production
    (root / ".crew" / "config.json").write_text(json.dumps(cfg), "utf-8")
    return str(root)


def _ceiling(tmp_path, level, name="ceiling.json"):
    """The machine-global file, at `level`.

    Never omitted. The ratchet takes the NARROWER of the two layers, so a repo
    asking for `full` against the default-`none` global resolves to `none`: a
    version of this file without it reported every level as `none` and would
    have "passed" against a fix that blocked at `full` too.
    """
    path = tmp_path / name
    path.write_text(json.dumps(
        {"guards": {"prodServer": level, "prodDatabase": level}}), "utf-8")
    return str(path)


# --- the five states, named ------------------------------------------------


@pytest.mark.parametrize("production,expected", [
    (None, crew_config.PROD_DECL_ABSENT),
    ({}, crew_config.PROD_DECL_ABSENT),
    ({"databases": ["db-prod-*"]}, crew_config.PROD_DECL_ABSENT),
    ({"hosts": []}, crew_config.PROD_DECL_EMPTY),
    ({"hosts": ["prod-web-*"]}, crew_config.PROD_DECL_DECLARED),
    ({"hosts": "prod-web-*"}, crew_config.PROD_DECL_MALFORMED),
    ({"hosts": {"0": "prod-web-*"}}, crew_config.PROD_DECL_MALFORMED),
    ({"hosts": ["prod-web-*", 7]}, crew_config.PROD_DECL_MALFORMED),
    ({"hosts": [""]}, crew_config.PROD_DECL_MALFORMED),
])
def test_each_shape_gets_its_own_state(tmp_path, production, expected):
    """The four states the ticket names, plus `declared`, each distinct.

    The third case is the one that would survive a lazy fix: `databases` IS
    declared, so the file has a `production` block and a list in it -- but for
    the OTHER guard. For `prodServer` that is absent, not malformed.
    """
    root = _repo(tmp_path, production)
    declared = crew_config.production_declaration(root, "prodServer")
    assert declared.state == expected, declared


def test_an_unreadable_config_is_not_an_absent_one(tmp_path):
    """A directory where `.crew/config.json` should be. `FileNotFoundError` is
    split from every other OSError precisely so this cannot answer `absent`:
    the errno differs by platform (PermissionError on Windows,
    IsADirectoryError on POSIX) and neither is "it is not there"."""
    root = tmp_path / "unreadable"
    (root / ".crew" / "config.json").mkdir(parents=True)

    declared = crew_config.production_declaration(str(root), "prodServer")

    assert declared.state == crew_config.PROD_DECL_UNREADABLE
    assert declared.patterns == []
    assert "could not be read" in declared.detail


def test_a_config_that_does_not_parse_is_malformed_not_absent(tmp_path):
    """The stray comma. `crew_state.load_config` returns `{}` here, which is
    why this function does its own read: built on that helper, an unparseable
    config and a repo with no config would be one answer."""
    root = tmp_path / "comma"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text(
        '{"production": {"hosts": ["prod-web-*"]},}', "utf-8")

    declared = crew_config.production_declaration(str(root), "prodServer")

    assert declared.state == crew_config.PROD_DECL_MALFORMED
    assert "does not parse" in declared.detail


def test_the_readable_entries_of_a_partly_broken_list_are_kept(tmp_path):
    """Malformed does not mean "discard what was readable". The three good
    globs are still returned -- a caller matching on them matches all three --
    and the state still says an entry could not be read."""
    root = _repo(tmp_path, {"hosts": ["prod-web-*", 7, "prod-db-*"]})

    declared = crew_config.production_declaration(root, "prodServer")

    assert declared.patterns == ["prod-web-*", "prod-db-*"]
    assert declared.state == crew_config.PROD_DECL_MALFORMED
    assert crew_config.production_patterns(root, "prodServer") == declared.patterns


# --- what the guard DOES about each state ---------------------------------


@pytest.mark.parametrize("production", [
    {"hosts": "prod-web-*"},                 # a string where a list belongs
    {"hosts": ["prod-web-*", 7]},            # partly globs
    "prod-web-*",                            # the whole block is a string
])
@pytest.mark.parametrize("level", ["none", "read"])
def test_a_declaration_crew_cannot_read_blocks_a_write(tmp_path, production,
                                                       level):
    """The regression, in-process. Every one of these used to be `allow` with
    the reason "no declared production target matches" -- a sentence about a
    file crew had not read."""
    root = _repo(tmp_path, production, level)

    out = crew_config.guard_decision(root, "prodServer", _WRITE,
                                     _ceiling(tmp_path, level))

    assert out["decision"] == "block", out
    assert out["declaration"] in (crew_config.PROD_DECL_MALFORMED,
                                  crew_config.PROD_DECL_UNREADABLE)
    assert "could not read what production is" in out["reason"]
    # Non-empty, and this is the assertion the two shell tests below exist to
    # back up: both hooks return silently when the target field is empty.
    assert out["target"], "a refusal both shells would swallow"


def test_a_config_crew_cannot_open_blocks_a_write_too(tmp_path):
    """The neighbour of the case above, which is where this repo's own lessons
    say the next defect is. `unreadable` reaches the same refusal as
    `malformed` -- through a different branch, on a state the guard can only get
    from the filesystem -- and the two are separate values all the way into the
    row so a reader can tell which happened."""
    root = tmp_path / "unreadable-repo"
    (root / ".crew" / "config.json").mkdir(parents=True)

    out = crew_config.guard_decision(str(root), "prodServer", _WRITE,
                                     _ceiling(tmp_path, "none"))

    assert out["decision"] == "block", out
    assert out["declaration"] == crew_config.PROD_DECL_UNREADABLE
    assert out["target"]


@pytest.mark.parametrize("production,level,command", [
    # `full` permits every access to every declared target, so a target crew
    # failed to read would have been allowed had it read it. Nothing turns on
    # the unknown, so nothing changes.
    ({"hosts": "prod-web-*"}, "full", _WRITE),
    # `read` permits anything classified read-only whether or not it matches,
    # so again the unknown decides nothing.
    ({"hosts": "prod-web-*"}, "read", _READ),
])
def test_where_the_unknown_decides_nothing_the_answer_is_unchanged(
        tmp_path, production, level, command):
    """A fix that blocked here would be "refuse whenever the config is odd",
    which is a different and worse rule than "refuse what you cannot check".

    The target stays EMPTY on these two, deliberately: an empty target is what
    keeps an ordinary `ssh` silent, and in `guard.sh` a non-empty one also sets
    `PROD_HIT=1`, which suppresses the crude `prod`-as-an-argument fallback
    further down that script. Filling it on an allow would remove a check that
    still works, in exactly the repo whose config crew could not read.
    """
    root = _repo(tmp_path, production, level)

    out = crew_config.guard_decision(root, "prodServer", command,
                                     _ceiling(tmp_path, level))

    assert out["decision"] == "allow", out
    assert out["target"] == ""
    # Still SAID, on the allow path too: the state survives into every value
    # derived from it, rather than into only the ones that refuse.
    assert out["declaration"] == crew_config.PROD_DECL_MALFORMED
    assert "could not read what production is" in out["reason"]


@pytest.mark.parametrize("production", [None, {}, {"hosts": []}])
@pytest.mark.parametrize("level", ["none", "read", "full"])
def test_nothing_declared_still_permits_everything(tmp_path, production,
                                                   level):
    """The must-allow half, at every level. `production: {"hosts": []}` is what
    `default_config()` ships, so if this went red every repo on the machine
    would have every `ssh` refused."""
    root = _repo(tmp_path, production, level)

    out = crew_config.guard_decision(root, "prodServer", _WRITE,
                                     _ceiling(tmp_path, level))

    assert out["decision"] == "allow", out
    assert out["target"] == ""
    assert out["declaration"] in (crew_config.PROD_DECL_ABSENT,
                                 crew_config.PROD_DECL_EMPTY)


def test_a_valid_declaration_still_names_the_pattern_it_matched(tmp_path):
    """Control. The ordinary refusal must keep reporting the real glob, not the
    "crew could not read it" placeholder."""
    root = _repo(tmp_path, {"hosts": ["prod-web-*"]}, "none")

    out = crew_config.guard_decision(root, "prodServer", _WRITE,
                                     _ceiling(tmp_path, "none"))

    assert out["decision"] == "block"
    assert out["target"] == "prod-web-*"
    assert out["declaration"] == crew_config.PROD_DECL_DECLARED


def test_the_non_production_guards_report_no_declaration_state(tmp_path):
    """`declaration` is set on BOTH branches of `guard_decision`, like
    `access`. A key one branch defines and the other does not is how a caller
    comes to read a missing one."""
    root = _repo(tmp_path, {"hosts": "prod-web-*"})

    out = crew_config.guard_decision(root, "forcePush", "git " + "push --force")

    assert out["declaration"] == ""


# --- through the hooks that actually run ----------------------------------


def _home(tmp_path, level):
    """A fake HOME carrying the machine-global ceiling, for a subprocess.

    `crew_state.GLOBAL_CONFIG_PATH` is computed from `expanduser("~")` at
    import time and a subprocess re-imports it, so conftest's in-process
    isolation does not reach these runs. Same approach as test_guards.py.
    """
    home = tmp_path / f"home-{level}"
    (home / ".claude" / "crew").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "crew" / "config.json").write_text(json.dumps(
        {"guards": {"prodServer": level, "prodDatabase": level}}), "utf-8")
    return str(home)


def _sh(root, home, command):
    payload = json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": command}})
    return subprocess.run(
        [_BASH, _GUARD_SH.replace("\\", "/")], input=payload,
        capture_output=True, text=True, check=False, cwd=root,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=root, HOME=home,
                 USERPROFILE=home))


def _ps1(root, home, command):
    payload = json.dumps({"tool_name": "PowerShell",
                          "tool_input": {"command": command}})
    return subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _GUARD_PS1],
        input=payload, capture_output=True, text=True, check=False, cwd=root,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=root, HOME=home,
                 USERPROFILE=home))


@needs_bash
def test_sh_refuses_a_write_when_it_cannot_read_the_declaration(tmp_path):
    """End to end through the UNMODIFIED guard.sh. This is the case an
    in-process test cannot reach: `prod_guarded` does `[ -z "$target" ] &&
    return 0` BEFORE the `case` that acts on the decision, so a `block`
    carrying an empty target exits 0 here with nothing printed."""
    home = _home(tmp_path, "none")
    root = _repo(tmp_path, {"hosts": "prod-web-*"}, "none", name="sh-bad")

    proc = _sh(root, home, _WRITE)

    assert proc.returncode == 2, f"exit {proc.returncode}: {proc.stderr}"
    assert "BLOCKED" in proc.stderr
    assert "could not read what production is" in proc.stderr


@needs_bash
def test_sh_still_says_nothing_when_nothing_is_declared(tmp_path):
    """The must-allow control, in the flavour that matters most for noise: a
    banner above every remote shell is how a guard becomes one people switch
    off."""
    home = _home(tmp_path, "none")
    root = _repo(tmp_path, {"hosts": []}, "none", name="sh-empty")

    proc = _sh(root, home, _WRITE)

    assert proc.returncode == 0, proc.stderr
    assert "production" not in proc.stderr


@needs_pwsh
def test_ps1_refuses_a_write_when_it_cannot_read_the_declaration(tmp_path):
    """The identical claim in the other flavour, written out rather than shared
    through a helper: the two scripts are what is under test, and
    `Invoke-ProdGuard` has its own `if (-not $target) { return }`."""
    home = _home(tmp_path, "none")
    root = _repo(tmp_path, {"hosts": "prod-web-*"}, "none", name="ps-bad")

    proc = _ps1(root, home, _WRITE)

    assert proc.returncode == 2, f"exit {proc.returncode}: {proc.stderr}"
    assert "BLOCKED" in proc.stderr
    assert "could not read what production is" in proc.stderr


@needs_pwsh
def test_ps1_still_says_nothing_when_nothing_is_declared(tmp_path):
    home = _home(tmp_path, "none")
    root = _repo(tmp_path, {"hosts": []}, "none", name="ps-empty")

    proc = _ps1(root, home, _WRITE)

    assert proc.returncode == 0, proc.stderr
    assert "production" not in proc.stderr
