"""The CI workflow crew-setup ships: `templates/github/crew-verify.yml`.

MUST hold for the template as shipped: it runs on pull requests, reads the
repo with `contents: read` and no secrets, checks the repo out with
`actions/checkout@v4` and no persisted credentials, sets up Python 3.12 with
`actions/setup-python@v5`, fetches crew at the `__CREW_SHA__` placeholder
(never a branch) into `$RUNNER_TEMP/crew`, outside the workspace, and runs the
gate from there as `verify-gate.sh --ci < /dev/null`.

MUST-ALLOW, end to end, with every command parsed from the YAML rather than
copied here: the fetch step, pointed at this repository by a local URL,
leaves a crew whose gate exists at the fetched commit; and the gate step, run
from a fixture repo's root with crew in a `RUNNER_TEMP` outside it and
`"unmapped": "fail"`, exits 0 on a map holding a RECURSIVE command that fails
if it finds crew's files in the workspace. MUST-BLOCK: the same command with
crew inside the workspace (the old `.crew-ci/crew` layout) fails that rule,
so the layout is what the test discriminates on.
"""
import json
import os
import subprocess

import pytest
import yaml

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_REPO = os.path.dirname(os.path.dirname(_ROOT))
_TEMPLATE = os.path.join(_ROOT, "skills", "crew-setup", "templates", "github", "crew-verify.yml")
_PLACEHOLDER = "__CREW_SHA__"
_CREW_URL = "https://github.com/mbadali25/useful-claude-add-ons"
_BASH = crew_fixtures.resolve_bash()
_TIMEOUT = crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S
# A recursive map command, the shape `pytest`/`ruff .`/`eslint .` have: it
# walks the whole workspace, following links, and fails on crew's own files.
_RECURSIVE = "find -L . -name verify-gate.sh | grep -q . && exit 1 || exit 0"


def _workflow():
    with open(_TEMPLATE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _steps():
    jobs = _workflow()["jobs"]
    assert len(jobs) == 1, list(jobs)
    return next(iter(jobs.values()))["steps"]


def _uses(prefix):
    return [s for s in _steps() if str(s.get("uses", "")).split("@", maxsplit=1)[0] == prefix]


def _fetch_step():
    found = [s for s in _steps() if _CREW_URL in str(s.get("run", ""))]
    assert len(found) == 1, _steps()
    return found[0]


def _gate_run():
    found = [s["run"] for s in _steps() if "verify-gate.sh" in str(s.get("run", ""))]
    assert len(found) == 1, _steps()
    return found[0].strip()


def test_the_template_runs_on_pull_requests_with_read_only_access():
    wf = _workflow()
    # PyYAML reads a bare `on:` key as the boolean True (YAML 1.1).
    triggers = wf.get("on", wf.get(True))
    assert "pull_request" in triggers, triggers
    assert "workflow_dispatch" in triggers, triggers
    assert wf["permissions"] == {"contents": "read"}, wf["permissions"]
    assert wf["concurrency"]["cancel-in-progress"] is True
    job = next(iter(wf["jobs"].values()))
    assert job["runs-on"] == "ubuntu-latest"
    assert isinstance(job["timeout-minutes"], int) and job["timeout-minutes"] > 0


def test_the_repo_checkout_is_v4_and_persists_no_credentials():
    checkouts = _uses("actions/checkout")
    assert len(checkouts) == 1, checkouts
    step = checkouts[0]
    assert step["uses"] == "actions/checkout@v4", step
    assert (step.get("with") or {}).get("persist-credentials") is False, step
    assert "repository" not in (step.get("with") or {}), step


def test_python_is_3_12_from_setup_python_v5():
    found = _uses("actions/setup-python")
    assert len(found) == 1, found
    assert found[0]["uses"] == "actions/setup-python@v5", found[0]
    assert found[0]["with"]["python-version"] == "3.12", found[0]


def test_no_secret_is_read_and_no_credential_reaches_the_crew_fetch():
    with open(_TEMPLATE, encoding="utf-8") as fh:
        assert "secrets." not in fh.read()
    step = _fetch_step()
    assert "token" not in step["run"].lower(), step["run"]
    assert "@github.com" not in step["run"], step["run"]


def test_crew_is_pinned_to_the_placeholder_never_a_branch():
    step = _fetch_step()
    sha = step["env"]["CREW_SHA"]
    assert sha == _PLACEHOLDER, sha
    assert sha not in ("main", "master")
    run = step["run"]
    assert f'{_CREW_URL} "$CREW_SHA"' in run, run
    assert "--depth 1" in run, run
    assert 'checkout -q --detach FETCH_HEAD' in run, run


def test_crew_lives_outside_the_workspace_and_the_gate_runs_in_ci_mode():
    run = _gate_run()
    assert run == 'bash "$RUNNER_TEMP/crew/plugin/crew/hooks/scripts/verify-gate.sh" --ci < /dev/null', run
    assert '"$RUNNER_TEMP/crew"' in _fetch_step()["run"]
    assert "GITHUB_WORKSPACE" not in _fetch_step()["run"]


def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True, text=True,
                          timeout=_TIMEOUT)


def _consumer(tmp_path):
    """A consumer repo whose every TRACKED file is mapped, with one local rule
    that walks the workspace the way a recursive linter or test runner does."""
    root = tmp_path / "consumer"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    rule = {"paths": ["a.py", ".crew/verify.json"], "seconds": 1, "reach": "local",
            "why": "fixture: a recursive map command", "run": [_RECURSIVE]}
    (root / ".crew" / "verify.json").write_text(json.dumps(
        {"version": 1, "rules": [rule], "default": [], "unmapped": "fail"}), encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _runner_temp(where):
    """`where/crew` holding this repo's plugin, as the fetch step leaves it."""
    crew = where / "crew"
    crew.mkdir(parents=True)
    try:
        os.symlink(os.path.join(_REPO, "plugin"), crew / "plugin", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("cannot create a directory symlink here")
    return where


def _env(runner_temp):
    env = dict(os.environ, RUNNER_TEMP=str(runner_temp))
    # A CI runner sets neither: the gate must find the project from its cwd.
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    return env


def _gate(root, runner_temp):
    return crew_fixtures.run_gate([_BASH, "-c", _gate_run()], cwd=str(root), env=_env(runner_temp),
                                  capture_output=True, text=True, check=False, timeout=_TIMEOUT)


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_the_shipped_command_passes_with_crew_outside_the_workspace(tmp_path):
    root = _consumer(tmp_path)
    runner_temp = _runner_temp(tmp_path / "runner-temp")

    done = _gate(root, runner_temp)

    assert done.returncode == 0, done.stderr
    assert "UNMAPPED CHANGES" not in done.stderr
    assert "VERIFY FAILED" not in done.stderr
    assert "verify-gate --ci: passed" in done.stderr


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_crew_inside_the_workspace_trips_a_recursive_map_command(tmp_path):
    """The contrast that makes the test above mean something: the old layout
    (crew checked out at `.crew-ci/crew` in the workspace) is collected by the
    same recursive rule, and the same gate command fails."""
    root = _consumer(tmp_path)
    runner_temp = _runner_temp(root / ".crew-ci")

    done = _gate(root, runner_temp)

    assert done.returncode == 2, done.stderr
    assert "VERIFY FAILED: " + _RECURSIVE in done.stderr


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_the_fetch_step_checks_out_crew_at_the_commit(tmp_path):
    """The fetch script, verbatim from the YAML except for the URL (this
    repository, by path), fetches a full SHA into $RUNNER_TEMP/crew and leaves
    the gate where the gate step runs it from."""
    try:
        sha = _git(_REPO, "rev-parse", "HEAD").stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        pytest.skip("this copy of crew is not a git checkout")
    step = _fetch_step()
    script = step["run"].replace(_CREW_URL, "file://" + _REPO.replace(os.sep, "/"))
    assert script != step["run"]
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    env = dict(_env(runner_temp), CREW_SHA=sha)

    done = crew_fixtures.run_gate([_BASH, "-c", script], cwd=str(tmp_path), env=env,
                                  capture_output=True, text=True, check=False, timeout=_TIMEOUT)

    assert done.returncode == 0, done.stderr
    crew = runner_temp / "crew"
    assert _git(crew, "rev-parse", "HEAD").stdout.strip() == sha
    assert (crew / "plugin" / "crew" / "hooks" / "scripts" / "verify-gate.sh").is_file()
