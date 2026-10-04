"""Both promote gates choose an environment by ONE shared rule (L-1503).

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
  another.

Review of the first fix (#489) then found the two gates still chose
differently: the .sh was case-sensitive and read only a lower-case `deploy`
key, and both took the FIRST matching environment, so qa `target=Prod` and
production `target=prod` resolved to different environments per flavour. The
rule both now share, on the working map and the committed map alike:

- the command is normalised the same way: every CR removed, trailing newlines
  removed; a command that is then empty or whitespace deploys nothing;
- a declared command matches when either one contains the other, literally,
  ignoring case (`*`, `?`, `[` are text);
- the `deploy` key is read ignoring case, and a map with two keys that differ
  only by case is refused (PowerShell's ConvertFrom-Json refuses it anyway);
- more than one matching environment is ambiguous and blocks, naming them all;
- a comparison that throws blocks rather than skipping the environment.

This is a guard that can BLOCK, so both directions are here (repo CLAUDE.md,
"Adding a hook"), plus an agreement table run through both real gates. Every
repository is built under `tmp_path`; `CLAUDE_PROJECT_DIR` points at it, never
at this repo. The .ps1 runs wherever PowerShell 7 resolves, with
`OS=Windows_NT` in the child only, as in test_promote_gate_effective_tree.py.

Rule time: one case per behaviour runs by default; the rest of the pwsh-heavy
matrix is marked `slow` (conftest deselects it unless `-m slow` or
`--run-slow`).
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
_MARKS = {"sh": [needs_bash], "ps1": [needs_pwsh]}

# The repro from the ticket, verbatim.
_JQ = "./deploy.sh && curl -s https://x/status | jq .items[0]"

# Patterns `-like` cannot parse: each threw WildcardPatternException.
_UNPARSEABLE = ["ship [", "ship []", "ship [z-a]", "ship [!-[]"]

_AMBIGUOUS = "matches more than one environment"


def _cases(values, *, smoke_ps1=1):
    """(flavour, value) params. Every sh case runs by default; only the first
    `smoke_ps1` ps1 cases do, the rest are `slow`."""
    out = []
    for flavour in ("sh", "ps1"):
        for i, value in enumerate(values):
            marks = list(_MARKS[flavour])
            if flavour == "ps1" and i >= smoke_ps1:
                marks.append(pytest.mark.slow)
            out.append(pytest.param(flavour, value, marks=marks,
                                    id=f"{flavour}-{value!r}"))
    return out


FLAVOURS = [pytest.param(f, marks=_MARKS[f]) for f in ("sh", "ps1")]


def _git(cwd, *args):
    return subprocess.run(("git",) + args, cwd=cwd, check=True,
                          capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout.strip()


def _env(deploy, human=False, key="deploy"):
    cfg = {key: deploy, "rollback": "none", "rollbackReason": "fixture"}
    if human:
        cfg["requireHuman"] = True
    return cfg


class Repo:
    """A clean, committed checkout gated on the given environments. `envs`
    may also be raw JSON text, for maps a dict cannot hold."""

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
        """Write `.crew/verify.json` (committed only by the constructor)."""
        text = envs if isinstance(envs, str) else (
            json.dumps({"environments": envs}, indent=2) + "\n")
        (self.root / ".crew" / "verify.json").write_text(text, encoding="utf-8")

    def approve(self, env):
        """Write the requireHuman marker for `env` at HEAD."""
        (self.root / ".crew" / f".approved-{env}-{self.sha}").write_text(
            "", encoding="utf-8")

    def in_flight(self):
        """The in-flight marker's text, or None."""
        path = self.root / ".crew" / ".deploy-in-flight"
        return path.read_text(encoding="utf-8").strip() if path.exists() else None

    def clear_in_flight(self):
        """Remove the in-flight marker between runs."""
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


@pytest.mark.parametrize("flavour,deploy", _cases(_UNPARSEABLE))
def test_a_pattern_like_cannot_read_still_gates(flavour, deploy, tmp_path):
    """(b) `-like` threw on these, the iteration was skipped, exit 0."""
    repo = Repo(tmp_path / "r", {"prod": _env(deploy, human=True)})
    code, err = run_gate(flavour, repo, deploy + " --now")
    _blocked_as(code, err, "prod")
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour,wild", _cases(["deploy-*", "deploy-pro?"]))
def test_a_wildcard_deploy_does_not_claim_another_environments_command(
        flavour, wild, tmp_path):
    """On the .ps1, stage's `*`/`?` matched `deploy-prod` too."""
    repo = Repo(tmp_path / "r", {"stage": _env(wild),
                                 "prod": _env("deploy-prod", human=True)})
    code, err = run_gate(flavour, repo, "deploy-prod")
    _blocked_as(code, err, "prod")
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_two_environments_matching_one_command_is_ambiguous(flavour, tmp_path):
    """#489 FIX1. qa `target=Prod` and production `target=prod` both match
    case-insensitively; first-match picked a different one per flavour. Now
    neither guesses, and both names are reported."""
    repo = Repo(tmp_path / "r", {
        "qa": _env("deploy target=Prod"),
        "production": _env("deploy target=prod", human=True)})
    code, err = run_gate(flavour, repo, "deploy target=prod")
    assert code == 2, err
    assert _AMBIGUOUS in err, err
    assert "qa" in err and "production" in err, err
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_capitalised_deploy_key_still_gates(flavour, tmp_path):
    """#489 FIX2. The .ps1's property access ignores case, the .sh read only
    `deploy`, so `"Deploy"` gated PowerShell and not bash."""
    repo = Repo(tmp_path / "r", {"prod": _env("deploy-prod", human=True,
                                              key="Deploy")})
    code, err = run_gate(flavour, repo, "deploy-prod")
    _blocked_as(code, err, "prod")


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_keys_differing_only_by_case_refuse_the_map(flavour, tmp_path):
    """Which of `deploy` / `Deploy` is policy cannot be told; ConvertFrom-Json
    refuses the map, and the .sh now refuses it too."""
    text = ('{"environments": {"prod": {"deploy": "deploy-prod", '
            '"Deploy": "other", "rollback": "none", "rollbackReason": "f"}}}\n')
    repo = Repo(tmp_path / "r", text)
    code, err = run_gate(flavour, repo, "deploy-prod")
    assert code == 2, err
    assert "PROMOTION BLOCKED" in err and "casing" in err, err
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_comparison_that_throws_blocks_instead_of_skipping(flavour, tmp_path):
    """Fail closed. On the .ps1 a command that is not a string has no
    IndexOf, so the comparison throws. The .sh reads the same payload as the
    text `12345`, so the map here names that text: both must block."""
    repo = Repo(tmp_path / "r", {"prod": _env("12345", human=True)})
    code, err = run_gate(flavour, repo, 12345)
    assert code == 2, err
    if flavour == "ps1":
        assert "could not compare" in err, err
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour,deploy", _cases(["Deploy-Prod", "ship [z-a]"]))
def test_the_committed_map_uses_the_same_rule(flavour, deploy, tmp_path):
    """NIT3. With the working map dirty, the committed map is matched too; an
    uncommitted rename must not let the old command match nothing."""
    repo = Repo(tmp_path / "r", {"prod": _env(deploy, human=True)})
    repo.write_map({"prod": _env("renamed-in-an-uncommitted-edit")})
    code, err = run_gate(flavour, repo, deploy.lower())
    _blocked_as(code, err, "prod")
    assert "uncommitted changes" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_the_committed_map_is_ambiguous_too(flavour, tmp_path):
    repo = Repo(tmp_path / "r", {"qa": _env("deploy target=Prod"),
                                 "production": _env("deploy target=prod")})
    repo.write_map({"qa": _env("x-renamed")})
    code, err = run_gate(flavour, repo, "deploy target=prod")
    assert code == 2, err
    assert _AMBIGUOUS in err, err


# --- must-allow -------------------------------------------------------------

@pytest.mark.parametrize("flavour,deploy", _cases([_JQ] + _UNPARSEABLE))
def test_an_approved_literal_deploy_allows_and_records_its_environment(
        flavour, deploy, tmp_path):
    """Once approved, the same deploys pass and the in-flight marker names the
    right environment, so the fix is not 'block all'."""
    repo = Repo(tmp_path / "r", {"prod": _env(deploy, human=True)})
    repo.approve("prod")
    code, err = run_gate(flavour, repo, deploy)
    assert code == 0, err
    assert repo.in_flight() == f"prod {repo.sha}"


@pytest.mark.parametrize("flavour,command", _cases(
    ["DEPLOY-PROD --now", "./Deploy-Prod", "deploy"]))
def test_a_single_case_insensitive_match_allows_once_approved(
        flavour, command, tmp_path):
    """Both gates ignore case, in both directions (`deploy` is inside
    `Deploy-Prod`): on Windows `./Deploy.ps1` and `./deploy.ps1` are one
    file, so a case-sensitive gate fails open there."""
    repo = Repo(tmp_path / "r", {"prod": _env("Deploy-Prod", human=True)})
    code, err = run_gate(flavour, repo, command)
    _blocked_as(code, err, "prod")
    repo.approve("prod")
    code, err = run_gate(flavour, repo, command)
    assert code == 0, err
    assert repo.in_flight() == f"prod {repo.sha}"


@pytest.mark.parametrize("flavour,command", _cases(
    ["deploy-prod\n\r", "deploy-prod\r", "deploy-prod\n", "deploy-prod\r\n\n"]))
def test_crs_and_trailing_newlines_are_normalised_alike(flavour, command, tmp_path):
    """NIT1. `deploy-prod\\n\\r` kept a newline on the .sh (the command
    substitution strips trailing newlines before the CR is removed)."""
    repo = Repo(tmp_path / "r", {"prod": _env("deploy-prod --force",
                                              human=True)})
    code, err = run_gate(flavour, repo, command)
    _blocked_as(code, err, "prod")


@pytest.mark.parametrize("flavour,command", _cases([" ", "\t\n", "\r\n "]))
def test_a_whitespace_only_command_deploys_nothing(flavour, command, tmp_path):
    """NIT2. The .ps1 exited 0 on whitespace; the .sh's `" " in "deploy
    prod"` matched it."""
    repo = Repo(tmp_path / "r", {"prod": _env("deploy prod", human=True)})
    code, err = run_gate(flavour, repo, command)
    assert code == 0, err
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_unrelated_command_passes_untouched(flavour, tmp_path):
    repo = Repo(tmp_path / "r", {"prod": _env(_JQ, human=True),
                                 "x": _env("ship [z-a]", human=True)})
    code, err = run_gate(flavour, repo, "git status")
    assert code == 0, err
    assert repo.in_flight() is None


# --- agreement --------------------------------------------------------------

def _cfg(value):
    return value if isinstance(value, dict) else _env(value)


_AGREEMENT = [
    # case-only (FIX1); first, so it is the map that runs by default
    ({"qa": "deploy target=Prod", "production": "deploy target=prod",
      "win": "./deploy.ps1"},
     ["deploy target=prod", "DEPLOY TARGET=PROD", "./Deploy.ps1",
      "deploy target=staging"]),
    ({"dev": "deploy-dev", "prod": "deploy-prod"},
     ["deploy-prod", "deploy-dev --force", "deploy", "echo hi",
      "deploy-prod-eu"]),
    ({"stage": "deploy-*", "prod": "deploy-prod"},
     ["deploy-prod", "deploy-*", "deploy-x"]),
    ({"a": "release?", "b": "release1"}, ["release1", "release?", "release"]),
    ({"jq": _JQ, "plain": "./deploy.sh --plain"},
     [_JQ, "./deploy.sh", "./deploy.sh --plain", "jq .items[1]"]),
    ({"w": "ship [!-[]", "x": "ship [z-a]", "y": "ship []", "z": "ship ["},
     ["ship [z-a]", "ship []", "ship [!-[] now", "ship z", "ship"]),
    ({"multi": ["a-cmd [0]", "b-cmd *"], "other": "c-cmd"},
     ["b-cmd *", "a-cmd [0] -v", "b-cmd x", "c-cmd"]),
    # Deploy-key (FIX2)
    ({"prod": _env("deploy-prod", key="Deploy"),
      "qa": _env("deploy-qa", key="DEPLOY")},
     ["deploy-prod", "deploy-qa", "deploy-"]),
    # trailing newline / CR / whitespace (NIT1, NIT2)
    ({"prod": "deploy prod --force"},
     ["deploy prod\n", "deploy prod\r\n", "deploy prod\n\r", " ", "\n\t",
      "deploy prod\r\r\n\n"]),
]


def _chosen(flavour, repo, command):
    repo.clear_in_flight()
    code, err = run_gate(flavour, repo, command)
    if code == 2 and _AMBIGUOUS in err:
        return "AMBIGUOUS"
    assert code == 0, f"{flavour} blocked {command!r}: {err}"
    marker = repo.in_flight()
    return marker.split()[0] if marker else None


def _agreement_params():
    out = []
    for i in range(len(_AGREEMENT)):
        marks = [needs_bash, needs_pwsh] + ([pytest.mark.slow] if i else [])
        out.append(pytest.param(i, marks=marks, id=f"map{i}"))
    return out


@pytest.mark.parametrize("index", _agreement_params())
def test_both_flavours_pick_the_same_environment(index, tmp_path):
    """Every map through both real gates; the choice must be identical."""
    deploys, commands = _AGREEMENT[index]
    repo = Repo(tmp_path / "r", {n: _cfg(d) for n, d in deploys.items()})
    for command in commands:
        sh = _chosen("sh", repo, command)
        ps1 = _chosen("ps1", repo, command)
        assert sh == ps1, (f"{command!r}: promote-gate.sh chose {sh}, "
                           f"promote-gate.ps1 chose {ps1}")
