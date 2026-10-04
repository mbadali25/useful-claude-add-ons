"""promote-gate.ps1 picks an environment by a LITERAL substring test (L-1503).

The PowerShell flavour matched each declared `deploy` with
`$cmd -like "*$dep*" -or $dep -like "*$cmd*"`. `-like` reads `*`, `?` and
`[set]` inside a deploy string as wildcards, so on the PowerShell tool:

- a deploy whose own literal text holds `[...]` (`jq .items[0]`) never matched
  itself, and a `requireHuman` environment exited 0 with no in-flight marker
  where promote-gate.sh exits 2;
- a pattern `-like` cannot read (`[`, `[]`, `[z-a]`, `[!-[]`) threw
  WildcardPatternException, the statement failed, the loop moved on and the
  gate exited 0;
- a `*` or `?` in one environment's deploy claimed a command that belongs to
  another, so the wrong environment's preconditions were checked.

promote-gate.sh has always used `d in cmd or cmd in d`. The .ps1 now does the
same test, literally, kept case-insensitive as it was, on the command with its
CRs removed (the .sh runs `crew_strip_cr` first), and blocks when the
comparison itself throws instead of skipping that environment.

This is a guard that can BLOCK, so both directions are here (repo CLAUDE.md,
"Adding a hook"), plus an agreement table: on every map, both flavours choose
the same environment. Every repository is built under `tmp_path`;
`CLAUDE_PROJECT_DIR` points at it, never at this repo. The .ps1 runs wherever
PowerShell 7 resolves, with `OS=Windows_NT` in the child only, as in
test_promote_gate_effective_tree.py.
"""
import json
import os
import pathlib
import subprocess

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "hooks" / "scripts"
_SH = _SCRIPTS / "promote-gate.sh"
_PS1 = _SCRIPTS / "promote-gate.ps1"

_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()

needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")
needs_pwsh = pytest.mark.skipif(_PWSH is None,
                                reason="no PowerShell 7 on this machine")

FLAVOURS = [pytest.param("sh", marks=needs_bash),
            pytest.param("ps1", marks=needs_pwsh)]

# The repro from the ticket, verbatim.
_JQ = "./deploy.sh && curl -s https://x/status | jq .items[0]"

# Patterns `-like` cannot parse: each threw WildcardPatternException.
_UNPARSEABLE = ["ship [", "ship []", "ship [z-a]", "ship [!-[]"]


def _git(cwd, *args):
    return subprocess.run(("git",) + args, cwd=cwd, check=True,
                          capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout.strip()


def _env(deploy, human=False):
    cfg = {"deploy": deploy, "rollback": "none", "rollbackReason": "fixture"}
    if human:
        cfg["requireHuman"] = True
    return cfg


class Repo:
    """A clean, committed checkout gated on the given environments."""

    def __init__(self, root, envs):
        self.root = root
        root.mkdir(parents=True)
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "t@example.invalid")
        _git(root, "config", "user.name", "T")
        _git(root, "config", "commit.gpgsign", "false")
        (root / ".gitignore").write_text(
            ".crew/*\n!.crew/verify.json\n.work/\n", encoding="utf-8")
        (root / ".crew").mkdir()
        (root / ".work").mkdir()
        self.write_map(envs)
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "fixture")
        self.sha = _git(root, "rev-parse", "--short", "HEAD")

    def write_map(self, envs):
        (self.root / ".crew" / "verify.json").write_text(
            json.dumps({"environments": envs}, indent=2) + "\n",
            encoding="utf-8")

    def approve(self, env):
        (self.root / ".crew" / f".approved-{env}-{self.sha}").write_text(
            "", encoding="utf-8")

    def in_flight(self):
        path = self.root / ".crew" / ".deploy-in-flight"
        return path.read_text(encoding="utf-8").strip() if path.exists() else None

    def clear_in_flight(self):
        path = self.root / ".crew" / ".deploy-in-flight"
        if path.exists():
            path.unlink()


def run_gate(flavour, repo, command):
    """One flavour, as Claude Code runs it: payload on stdin, project dir in
    the environment. `command` is sent as given, so a non-string reaches the
    gate as JSON would carry it."""
    payload = {"tool_name": "Bash" if flavour == "sh" else "PowerShell",
               "tool_input": {"command": command}, "cwd": str(repo.root)}
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo.root))
    if flavour == "sh":
        argv = [_BASH, _SH.as_posix()]
    else:
        env["OS"] = "Windows_NT"
        argv = [_PWSH, "-NoProfile", "-NonInteractive", "-File", str(_PS1)]
    proc = subprocess.run(argv, input=json.dumps(payload), capture_output=True,
                          text=True, check=False, env=env, cwd=str(repo.root),
                          timeout=120)
    return proc.returncode, proc.stderr


def _blocked_as(code, err, env):
    assert code == 2, f"expected a block as {env}, got exit {code}: {err}"
    assert f"PROMOTION BLOCKED ({env}" in err, err


# --- must-block -------------------------------------------------------------

@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_deploy_holding_brackets_matches_itself_and_blocks(flavour, tmp_path):
    """(a) The ticket's repro. On the .ps1, `jq .items[0]` read `[0]` as a
    set, the environment never matched itself, and the gate exited 0."""
    repo = Repo(tmp_path / "r", {"prod": _env([_JQ], human=True)})
    code, err = run_gate(flavour, repo, _JQ)
    _blocked_as(code, err, "prod")
    assert "requires explicit human approval" in err, err
    assert repo.in_flight() is None


@pytest.mark.parametrize("deploy", _UNPARSEABLE)
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_pattern_like_cannot_read_still_gates(flavour, deploy, tmp_path):
    """(b) `-like` threw on these, the iteration was skipped, exit 0."""
    repo = Repo(tmp_path / "r", {"prod": _env(deploy, human=True)})
    code, err = run_gate(flavour, repo, deploy + " --now")
    _blocked_as(code, err, "prod")
    assert repo.in_flight() is None


@pytest.mark.parametrize("wild", ["deploy-*", "deploy-pro?"])
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_wildcard_deploy_does_not_claim_another_environments_command(
        flavour, wild, tmp_path):
    """`stage` is listed first; on the .ps1 its `*`/`?` matched `deploy-prod`
    and the deploy ran under stage's preconditions, skipping prod's."""
    repo = Repo(tmp_path / "r", {"stage": _env(wild),
                                 "prod": _env("deploy-prod", human=True)})
    code, err = run_gate(flavour, repo, "deploy-prod")
    _blocked_as(code, err, "prod")
    assert repo.in_flight() is None


@needs_pwsh
def test_a_comparison_that_throws_blocks_instead_of_skipping(tmp_path):
    """Fail closed. A command that is not a string has no IndexOf, so the
    comparison throws; that environment cannot be ruled out, and skipping it
    is exactly the (b) failure. The sh flavour reads the same payload as the
    text `12345`, which this map does not name, so this row is .ps1-only."""
    repo = Repo(tmp_path / "r", {"prod": _env("deploy-prod", human=True)})
    code, err = run_gate("ps1", repo, 12345)
    assert code == 2, err
    assert "could not compare" in err, err
    assert repo.in_flight() is None


@needs_pwsh
def test_the_committed_map_matches_case_insensitively_too(tmp_path):
    """The committed-map path (dirty working map) used `.Contains`, which is
    case-sensitive, while the working-map path was not. A working-map edit
    that renames the deploy then let `deploy-prod` match nothing and exit 0
    on the .ps1. Both paths now share one matcher."""
    repo = Repo(tmp_path / "r", {"prod": _env("Deploy-Prod", human=True)})
    repo.write_map({"prod": _env("renamed-in-an-uncommitted-edit")})
    code, err = run_gate("ps1", repo, "deploy-prod")
    _blocked_as(code, err, "prod")
    assert "uncommitted changes" in err, err


@needs_pwsh
def test_the_committed_map_matches_brackets_literally(tmp_path):
    repo = Repo(tmp_path / "r", {"prod": _env("ship [z-a]", human=True)})
    repo.write_map({"prod": _env("renamed-in-an-uncommitted-edit")})
    code, err = run_gate("ps1", repo, "ship [z-a]")
    _blocked_as(code, err, "prod")
    assert "uncommitted changes" in err, err


# --- must-allow -------------------------------------------------------------

@pytest.mark.parametrize("deploy", [_JQ] + _UNPARSEABLE)
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_approved_literal_deploy_allows_and_records_its_environment(
        flavour, deploy, tmp_path):
    """The other half: once approved, the same deploys pass and the in-flight
    marker names the right environment, so the fix is not 'block all'."""
    repo = Repo(tmp_path / "r", {"prod": _env(deploy, human=True)})
    repo.approve("prod")
    code, err = run_gate(flavour, repo, deploy)
    assert code == 0, err
    assert repo.in_flight() == f"prod {repo.sha}"


@needs_pwsh
@pytest.mark.parametrize("command", ["DEPLOY-PROD", "Deploy-Prod --force",
                                     "deploy"])
def test_the_ps1_still_matches_case_insensitively(command, tmp_path):
    """The .ps1 matched case-insensitively before, and still does - in both
    directions (`deploy` is inside `Deploy-Prod`)."""
    repo = Repo(tmp_path / "r", {"prod": _env("Deploy-Prod", human=True)})
    code, err = run_gate("ps1", repo, command)
    _blocked_as(code, err, "prod")


@needs_pwsh
def test_a_trailing_cr_is_stripped_before_matching_like_the_sh(tmp_path):
    """promote-gate.sh runs `crew_strip_cr` on the command before matching,
    so `deploy-prod\\r` is inside `deploy-prod --force` there. The .ps1 kept
    the CR and matched nothing."""
    repo = Repo(tmp_path / "r", {"prod": _env("deploy-prod --force",
                                              human=True)})
    code, err = run_gate("ps1", repo, "deploy-prod\r")
    _blocked_as(code, err, "prod")


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_unrelated_command_passes_untouched(flavour, tmp_path):
    repo = Repo(tmp_path / "r", {"prod": _env(_JQ, human=True),
                                 "x": _env("ship [z-a]", human=True)})
    code, err = run_gate(flavour, repo, "git status")
    assert code == 0, err
    assert repo.in_flight() is None


# --- agreement --------------------------------------------------------------

_AGREEMENT = [
    ({"dev": "deploy-dev", "prod": "deploy-prod"},
     ["deploy-prod", "deploy-dev --force", "deploy", "echo hi",
      "deploy-prod-eu"]),
    ({"stage": "deploy-*", "prod": "deploy-prod"},
     ["deploy-prod", "deploy-*", "deploy-x"]),
    ({"a": "release?", "b": "release1"}, ["release1", "release?", "release"]),
    ({"jq": _JQ, "plain": "./deploy.sh --plain"},
     [_JQ, "./deploy.sh", "./deploy.sh --plain", "jq .items[1]"]),
    ({"w": "ship [!-[]", "x": "ship [z-a]", "y": "ship []", "z": "ship ["},
     ["ship [z-a]", "ship []", "ship [", "ship [!-[] now", "ship z", "ship"]),
    ({"multi": ["a-cmd [0]", "b-cmd *"], "other": "c-cmd"},
     ["b-cmd *", "a-cmd [0] -v", "b-cmd x", "c-cmd"]),
]


def _chosen(flavour, repo, command):
    repo.clear_in_flight()
    code, err = run_gate(flavour, repo, command)
    assert code == 0, f"{flavour} blocked {command!r}: {err}"
    marker = repo.in_flight()
    return marker.split()[0] if marker else None


@needs_bash
@needs_pwsh
@pytest.mark.parametrize("index", range(len(_AGREEMENT)))
def test_both_flavours_pick_the_same_environment(index, tmp_path):
    deploys, commands = _AGREEMENT[index]
    repo = Repo(tmp_path / "r", {n: _env(d) for n, d in deploys.items()})
    for command in commands:
        sh = _chosen("sh", repo, command)
        ps1 = _chosen("ps1", repo, command)
        assert sh == ps1, (f"{command!r}: promote-gate.sh chose {sh}, "
                           f"promote-gate.ps1 chose {ps1}")
