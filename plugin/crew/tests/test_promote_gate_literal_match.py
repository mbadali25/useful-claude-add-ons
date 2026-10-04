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
  so are `environments`, `requires`, `rollback`, `rollbackReason` and
  `requireHuman` - the .sh read them case-sensitively, so `"RequireHuman":
  true` demanded a human on PowerShell and nobody on bash;
- `"deploy": null` in the working map is a malformed entry and refuses the
  map in both (the .ps1 skipped it, the .sh refused it);
- when more than one environment matches, the union of their requirements
  applies - every `requires`, every `rollback`, every `requireHuman` - and the
  environments are named together (`staging,prod`) in the block message and
  the in-flight marker. Strictly stricter than the old first-match pick, which
  gated prod's command as staging, without locking out a short command that
  sits inside two deploys (`git push` in `git push staging main` and
  `git push prod main`);
- a duplicate key - exactly the same, or differing only by case - refuses the
  map; so does a `requireHuman` that is a list or an object;
- an environment name that is empty, holds a control character (a newline
  split one name into two environments on the .sh) or holds `,` (the union's
  join character) refuses the map;
- PowerShell-only JSON - a comment, a single-quoted or bare key - refuses
  the map on the .ps1 as python's json refuses it on the .sh;
- `"deploy": []` and `[""]` declare nothing and pass (the .ps1 read `[]` as
  null and refused every command in the repo);
- a comparison that throws blocks rather than skipping the environment.

This is a guard that can BLOCK, so both directions are here (repo CLAUDE.md,
"Adding a hook"), plus an agreement table run through both real gates. Every
repository is built under `tmp_path`; `CLAUDE_PROJECT_DIR` points at it, never
at this repo. The .ps1 runs wherever PowerShell 7 resolves, with
`OS=Windows_NT` in the child only, as in test_promote_gate_effective_tree.py.

Rule time: every .ps1 case is marked `slow` except the first agreement map,
which runs both real gates by default; every .sh case runs by default, so the
default run keeps each must-block and must-allow case on bash. conftest
deselects `slow` unless `-m slow` or `--run-slow`; CI runs it in
`crew-shell-matrix (ubuntu-latest)` and `crew-windows-slow`
(`pytest plugin/crew/tests -m slow`, .github/workflows/pytest-crew.yml).
"""
import json
import os
import pathlib
import re
import subprocess
import sys

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
# Every .ps1 case is `slow` (see the module docstring); the .sh runs by default.
_MARKS = {"sh": [needs_bash], "ps1": [needs_pwsh, pytest.mark.slow]}

# The repro from the ticket, verbatim.
_JQ = "./deploy.sh && curl -s https://x/status | jq .items[0]"

# Patterns `-like` cannot parse: each threw WildcardPatternException.
_UNPARSEABLE = ["ship [", "ship []", "ship [z-a]", "ship [!-[]"]

def _cases(values):
    """(flavour, value) params, marked per flavour by `_MARKS`."""
    return [pytest.param(flavour, value, marks=_MARKS[flavour],
                         id=f"{flavour}-{value!r}")
            for flavour in ("sh", "ps1") for value in values]


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


def run_gate(flavour, repo, command, path_prefix=None):
    """One flavour, as Claude Code runs it: payload on stdin, project dir in
    the environment. `command` is sent as given, so a non-string reaches the
    gate as JSON would carry it. `path_prefix` goes in front of PATH."""
    payload = {"tool_name": "Bash" if flavour == "sh" else "PowerShell",
               "tool_input": {"command": command}, "cwd": str(repo.root)}
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo.root))
    if path_prefix:
        env["PATH"] = str(path_prefix) + os.pathsep + env["PATH"]
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
def test_two_matching_environments_apply_the_union_of_their_requirements(
        flavour, tmp_path):
    """#489 FIX1/F1. qa `target=Prod` and production `target=prod` both match
    case-insensitively. First-match picked a different one per flavour; now
    both apply, so production's requireHuman holds until approved."""
    repo = Repo(tmp_path / "r", {
        "qa": _env("deploy target=Prod"),
        "production": _env("deploy target=prod", human=True)})
    code, err = run_gate(flavour, repo, "deploy target=prod")
    _blocked_as(code, err, "qa,production")
    assert "requires explicit human approval" in err, err
    assert repo.in_flight() is None
    repo.approve("production")
    code, err = run_gate(flavour, repo, "deploy target=prod")
    assert code == 0, err
    assert repo.in_flight() == f"qa,production {repo.sha}"


@pytest.mark.parametrize("flavour,command", _cases(["git push", "git push prod"]))
def test_a_short_command_inside_two_deploys_is_gated_not_locked_out(
        flavour, command, tmp_path):
    """F1. `git push` sits inside both deploys. Blocking it as ambiguous
    blocked it forever; the union gates it on prod's approval instead.
    `git push prod` sits only inside prod's."""
    repo = Repo(tmp_path / "r", {
        "staging": _env("git push staging main"),
        "prod": _env("git push prod main", human=True)})
    code, err = run_gate(flavour, repo, command)
    assert code == 2, err
    assert "requires explicit human approval" in err, err
    repo.approve("prod")
    code, err = run_gate(flavour, repo, command)
    assert code == 0, err
    expect = "staging,prod" if command == "git push" else "prod"
    assert repo.in_flight() == f"{expect} {repo.sha}"


@pytest.mark.parametrize("flavour,command", _cases(["./deploy.sh", "./deploy.sh --prod"]))
def test_a_deploy_that_prefixes_another_carries_its_requirements(
        flavour, command, tmp_path):
    """F1. `./deploy.sh` is inside `./deploy.sh --prod`, so each command
    matches both environments, and prod's `requires` applies to both."""
    repo = Repo(tmp_path / "r", {
        "qa": _env("./deploy.sh"),
        "prod": dict(_env("./deploy.sh --prod"), requires=["qa"])})
    code, err = run_gate(flavour, repo, command)
    _blocked_as(code, err, "qa,prod")
    assert "'qa' has no all-pass row" in err, err
    (repo.root / ".work" / "PROMOTIONS.md").write_text(
        "| when | env | sha | smoke | regression | verify | by |\n|---|---|---|---|---|---|---|\n"
        f"| 2026-10-04 | qa | {repo.sha} | pass | pass | pass | t |\n", encoding="utf-8")
    code, err = run_gate(flavour, repo, command)
    assert code == 0, err
    assert repo.in_flight() == f"qa,prod {repo.sha}"


@pytest.mark.parametrize("flavour,deploys", _cases([[], [""]]))
def test_an_empty_deploy_list_declares_nothing(flavour, deploys, tmp_path):
    """#489 B1. The .ps1 unrolled `[]` to null in an if-expression and refused
    the map, blocking every PowerShell command in the repo."""
    repo = Repo(tmp_path / "r", {"empty": _env(deploys),
                                 "prod": _env("./deploy.sh prod", human=True)})
    code, err = run_gate(flavour, repo, "echo hi")
    assert code == 0, err
    assert repo.in_flight() is None
    code, err = run_gate(flavour, repo, "./deploy.sh prod")
    _blocked_as(code, err, "prod")


@pytest.mark.parametrize("flavour,text", _cases([
    '{"environments": {"prod": {"deploy": "deploy-prod", "rollback": "none", '
    '"rollbackReason": "f", "requireHuman": true, "requireHuman": false}}}\n',
    '{"environments": {"prod": {"deploy": "deploy-prod", "rollback": "none", '
    '"rollbackReason": "f", "requireHuman": true}, "prod": {"deploy": "x", '
    '"rollback": "none", "rollbackReason": "f"}}}\n']))
def test_an_exact_duplicate_key_refuses_the_map(flavour, text, tmp_path):
    """N3. `"requireHuman": true, "requireHuman": false` reads as gated and
    applied as not gated (both parsers keep the last)."""
    repo = Repo(tmp_path / "r", text)
    code, err = run_gate(flavour, repo, "deploy-prod")
    assert code == 2, err
    assert "PROMOTION BLOCKED" in err and "duplicate" in err, err
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour,human", _cases([[0], {}, [], ["yes"]]))
def test_a_non_scalar_require_human_refuses_the_map(flavour, human, tmp_path):
    """N2. `[0]` is truthy to python and falsy to PowerShell; `{}` the
    reverse. Neither is a yes or a no."""
    cfg = _env("deploy-prod")
    cfg["requireHuman"] = human
    repo = Repo(tmp_path / "r", {"prod": cfg})
    code, err = run_gate(flavour, repo, "deploy-prod")
    assert code == 2, err
    assert "requireHuman" in err, err
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
def test_the_committed_map_applies_the_union_too(flavour, tmp_path):
    """The union rule holds on the committed-map path as well: an uncommitted
    edit that drops one environment does not drop its requirements."""
    repo = Repo(tmp_path / "r", {"qa": _env("deploy target=Prod"),
                                 "production": _env("deploy target=prod")})
    repo.write_map({"qa": _env("x-renamed")})
    code, err = run_gate(flavour, repo, "deploy target=prod")
    _blocked_as(code, err, "qa,production")
    assert "uncommitted changes" in err, err


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_capitalised_require_human_still_requires_a_human(flavour, tmp_path):
    """The .sh read `cfg.get("requireHuman")`, so `"RequireHuman": true`
    deployed unapproved on bash while PowerShell refused it."""
    cfg = _env("deploy-prod")
    cfg["RequireHuman"] = True
    repo = Repo(tmp_path / "r", {"prod": cfg})
    code, err = run_gate(flavour, repo, "deploy-prod")
    _blocked_as(code, err, "prod")
    assert "requires explicit human approval" in err, err
    assert repo.in_flight() is None


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_a_null_deploy_refuses_the_map(flavour, tmp_path):
    """`"deploy": null` is neither a command nor a list of them. The .ps1
    skipped the environment and let `deploy-qa` through; both refuse now."""
    repo = Repo(tmp_path / "r", {"prod": _env(None, human=True),
                                 "qa": _env("deploy-qa")})
    code, err = run_gate(flavour, repo, "deploy-qa")
    assert code == 2, err
    assert "not a command or a list of commands" in err, err
    assert repo.in_flight() is None


_BAD_NAMES = ["a\nb", "a\tb", "", "a,b"]


@pytest.mark.parametrize("flavour,name", _cases(_BAD_NAMES))
def test_a_bad_environment_name_refuses_the_map(flavour, name, tmp_path):
    """#489 F1. The .sh printed matched names one per line and split them
    back on lines, so `"a\nb"` became the lax environments `a` and `b` and
    its requireHuman never applied. `""` passed as nothing matched, and `,`
    is the union's join character. Both gates now refuse such a map."""
    repo = Repo(tmp_path / "r", {"a": _env("deploy-a"), "b": _env("deploy-b"),
                                 name: _env("./deploy.sh prod", human=True)})
    for command in ("./deploy.sh prod", "echo hi"):
        code, err = run_gate(flavour, repo, command)
        assert code == 2, (command, err)
        # ConvertFrom-Json itself refuses an empty property name, first.
        empty_on_ps1 = flavour == "ps1" and name == ""
        assert ("could not be read or parsed" if empty_on_ps1
                else "environment name") in err, err
        assert repo.in_flight() is None


@pytest.mark.parametrize("flavour,name", _cases(["my-env_1.0", "prod.eu-west_2"]))
def test_an_ordinary_environment_name_still_gates(flavour, name, tmp_path):
    """Must-allow: `-`, `_` and `.` in a name are fine."""
    repo = Repo(tmp_path / "r", {name: _env("./deploy.sh prod", human=True)})
    code, err = run_gate(flavour, repo, "./deploy.sh prod")
    _blocked_as(code, err, name)
    repo.approve(name)
    code, err = run_gate(flavour, repo, "./deploy.sh prod")
    assert code == 0, err
    assert repo.in_flight() == f"{name} {repo.sha}"


_LAX_JSON = [
    '{// a note\n"environments": {"prod": {"deploy": "deploy-prod", '
    '"rollback": "none", "rollbackReason": "f"}}}\n',
    '{"environments": /* c */ {"prod": {"deploy": "deploy-prod", '
    '"rollback": "none", "rollbackReason": "f"}}}\n',
    "{'environments': {\"prod\": {\"deploy\": \"deploy-prod\", "
    '"rollback": "none", "rollbackReason": "f"}}}\n',
    '{environments: {"prod": {"deploy": "deploy-prod", '
    '"rollback": "none", "rollbackReason": "f"}}}\n',
]


@pytest.mark.parametrize("flavour,text", _cases(_LAX_JSON))
def test_json_only_powershell_reads_refuses_the_map(flavour, text, tmp_path):
    """#489 N2. ConvertFrom-Json reads comments and single-quoted or bare
    keys; python's json refuses them. Both refuse now."""
    repo = Repo(tmp_path / "r", text)
    code, err = run_gate(flavour, repo, "deploy-prod")
    assert code == 2, err
    assert "PROMOTION BLOCKED" in err, err
    assert repo.in_flight() is None


def _crlf_python(tmp_path):
    """A `python3`/`python` that writes what Windows python writes to a pipe:
    every newline but the last as CRLF (Git Bash's command substitution drops
    the final CRLF, and Linux bash only the final LF, so the last one is left
    alone to keep every other single-line read in the gate as it is)."""
    real = sys.executable
    shim = tmp_path / "crlf-bin"
    shim.mkdir()
    body = ("#!/usr/bin/env bash\nset -o pipefail\n"
            f"'{real}' \"$@\" | '{real}' -c 'import sys; d = sys.stdin.buffer.read(); "
            "t = d.endswith(b\"\\n\"); d = d[:-1] if t else d; "
            "sys.stdout.buffer.write(d.replace(b\"\\n\", b\"\\r\\n\")"
            " + (b\"\\n\" if t else b\"\"))'\n")
    for name in ("python3", "python"):
        (shim / name).write_text(body, encoding="utf-8", newline="\n")
        (shim / name).chmod(0o755)
    return shim


@needs_bash
@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="Windows python already writes CRLF; the agreement "
                           "maps there are this case for real")
@pytest.mark.parametrize("command", ["deploy target=prod", "./deploy.sh"])
def test_a_union_survives_python_writing_crlf(command, tmp_path):
    """The Windows pre-flight on 9dba8652: python's text-mode stdout wrote the
    matched names as `qa\r\nprod`, the .sh split them on LF, and `qa\r`
    named no environment - every multi-environment match blocked as a
    malformed map on Windows. The .sh now strips CRs from the names."""
    repo = Repo(tmp_path / "r", {"qa": _env(command), "prod": _env(command + " --x")})
    code, err = run_gate("sh", repo, command, path_prefix=_crlf_python(tmp_path))
    assert code == 0, err
    assert repo.in_flight() == f"qa,prod {repo.sha}"


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
    """Must-allow: a command no deploy names passes and leaves no marker."""
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
    # per-environment keys in any case; `Environments` itself; null deploy
    ({"prod": {"deploy": "deploy-prod", "rollback": "none",
               "rollbackReason": "f", "RequireHuman": True},
      "qa": {"deploy": "deploy-qa", "ROLLBACK": "none", "RollbackReason": "f"},
      "eu": {"deploy": "deploy-eu", "Rollback": "none", "rollbackReason": "f",
             "Requires": ["qa"]}},
     ["deploy-prod", "deploy-qa", "deploy-eu"]),
    ('{"Environments": {"prod": {"Deploy": "deploy-prod", '
     '"Rollback": "none", "RollbackReason": "f"}}}\n',
     ["deploy-prod", "deploy-qa"]),
    ({"prod": {"deploy": None, "rollback": "none", "rollbackReason": "f"},
      "qa": "deploy-qa"},
     ["deploy-qa", "git status"]),
    ('{"environments": {"prod": {"deploy": "deploy-prod", '
     '"rollback": "none", "rollbackReason": "f", '
     '"requireHuman": false, "RequireHuman": true}}}\n',
     ["deploy-prod"]),
    # union (F1), empty deploys (B1), duplicates (N3), requireHuman shape (N2)
    ({"staging": "git push staging main", "prod": _env("git push prod main", human=True),
      "dev": "./deploy.sh", "live": dict(_env("./deploy.sh --prod"), requires=["dev"])},
     ["git push", "git push staging", "git push prod main", "./deploy.sh",
      "./deploy.sh --prod", "make"]),
    ({"empty": _env([]), "blank": _env([""]), "prod": "./deploy.sh prod"},
     ["echo hi", "./deploy.sh prod", "Get-ChildItem"]),
    ('{"environments": {"prod": {"deploy": "deploy-prod", "rollback": "none", '
     '"rollbackReason": "f", "requireHuman": true, "requireHuman": false}}}\n',
     ["deploy-prod", "echo hi"]),
    ('{"environments": {"a": {"deploy": "x-a", "rollback": "none", '
     '"rollbackReason": "f"}, "a": {"deploy": "x-b", "rollback": "none", '
     '"rollbackReason": "f"}}}\n',
     ["x-a", "x-b"]),
    ({"prod": dict(_env("deploy-prod"), requireHuman=[0]),
      "qa": dict(_env("deploy-qa"), requireHuman={})},
     ["deploy-prod", "deploy-qa"]),
    # environment names (F1) and PowerShell-only JSON (N2)
    ({"a": "deploy-a", "b": "deploy-b", "a\nb": _env("./deploy.sh prod", human=True)},
     ["./deploy.sh prod", "echo hi"]),
    ({"a\tb": "deploy-x"}, ["deploy-x"]),
    ({"": "deploy-x"}, ["deploy-x", "echo hi"]),
    ({"a,b": "deploy-x", "a": "deploy-y"}, ["deploy-x"]),
    ({"my-env_1.0": "deploy-x", "prod.eu": "deploy-y"}, ["deploy-x", "deploy-y", "deploy-"]),
    (_LAX_JSON[0], ["deploy-prod", "echo hi"]),
    (_LAX_JSON[2], ["deploy-prod"]),
    (_LAX_JSON[3], ["deploy-prod"]),
    # trailing newline / CR / whitespace (NIT1, NIT2)
    ({"prod": "deploy prod --force"},
     ["deploy prod\n", "deploy prod\r\n", "deploy prod\n\r", " ", "\n\t",
      "deploy prod\r\r\n\n"]),
]


def _chosen(flavour, repo, command):
    """What one gate decided for `command`: an environment list, None for no
    match, or the block it gave (`BLOCKED <envs>` / `BLOCKED: map`)."""
    repo.clear_in_flight()
    code, err = run_gate(flavour, repo, command)
    if code == 2:
        # Which environments, or that the map was refused, is the comparison.
        named = re.search(r"PROMOTION BLOCKED \((.+?)(?:, sha |\):)", err)
        return f"BLOCKED {named.group(1)}" if named else "BLOCKED: map"
    assert code == 0, f"{flavour} exited {code} on {command!r}: {err}"
    marker = repo.in_flight()
    return marker.split()[0] if marker else None


def _agreement_params():
    """One param per agreement map; all but the first are `slow`."""
    out = []
    for i in range(len(_AGREEMENT)):
        marks = [needs_bash, needs_pwsh] + ([pytest.mark.slow] if i else [])
        out.append(pytest.param(i, marks=marks, id=f"map{i}"))
    return out


@pytest.mark.parametrize("index", _agreement_params())
def test_both_flavours_pick_the_same_environment(index, tmp_path):
    """Every map through both real gates; the choice must be identical."""
    deploys, commands = _AGREEMENT[index]
    # A str entry is raw map text, for maps a dict cannot hold.
    repo = Repo(tmp_path / "r", deploys if isinstance(deploys, str) else
                {n: _cfg(d) for n, d in deploys.items()})
    for command in commands:
        sh = _chosen("sh", repo, command)
        ps1 = _chosen("ps1", repo, command)
        assert sh == ps1, (f"{command!r}: promote-gate.sh chose {sh}, "
                           f"promote-gate.ps1 chose {ps1}")
