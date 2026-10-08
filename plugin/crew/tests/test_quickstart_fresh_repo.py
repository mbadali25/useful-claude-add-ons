"""L-0713: the quickstart, followed on a fresh repo, ends with `/crew:status` clean.

`docs/guides/crew/src/quickstart.md` is replayed step by step in a throwaway
repo under `tmp_path`, with `HOME` pointed at a throwaway directory too, so the
machine-global `~/.claude/crew/config.json` of whoever runs the suite is never
read or written. The model-driven parts of `/crew:init` cannot run here; its
Phase 1 writes are the ones `skills/crew-setup/phases.md` prescribes, made with
the same files and scripts it names: the shipped template copied to
`.crew/config.json` with `scope.mode` set to `auto` (a hand edit: `crew_config.py`
refuses that key at the repo layer, as the scope guard's trust root), the
`SKILL.md` section 3c ignore block, and `crew_gitignore.py apply`.
"""
import json
import os
import re
import subprocess
import sys

import context  # noqa: F401  pylint: disable=unused-import

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
TEMPLATE = os.path.join(CREW, "templates", "config.template.json")
SETUP_SKILL = os.path.join(CREW, "skills", "crew-setup", "SKILL.md")


def _env(home):
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               GIT_CONFIG_NOSYSTEM="1")
    env.pop("CLAUDE_PROJECT_DIR", None)
    return env


def _run(env, script, *args):
    done = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                          capture_output=True, text=True, check=False, env=env)
    assert done.returncode == 0, (script, done.stdout, done.stderr)
    return done.stdout.splitlines()


def _git(env, root, *args):
    subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True)


def _ignore_block():
    with open(SETUP_SKILL, encoding="utf-8") as fh:
        text = fh.read()
    section = text.split("## 3c.", 1)[1]
    return re.search(r"```gitignore\n(.*?)```", section, re.S).group(1)


def test_following_the_quickstart_ends_with_status_clean(tmp_path):
    home, root = tmp_path / "home", tmp_path / "repo"
    home.mkdir()
    root.mkdir()
    env = _env(home)
    _git(env, root, "init", "-q")
    _git(env, root, "-c", "user.email=t@example.invalid", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "fresh")

    before = _run(env, "crew_status.py", "--root", str(root))
    assert before[1] == "config   none - run /crew:init"

    (root / ".crew").mkdir()
    (root / ".work").mkdir()
    with open(TEMPLATE, encoding="utf-8") as fh:
        config = json.load(fh)
    config["scope"]["mode"] = "auto"
    (root / ".crew" / "config.json").write_text(json.dumps(config, indent=2) + "\n",
                                                encoding="utf-8")
    (root / ".gitignore").write_text(_ignore_block(), encoding="utf-8")
    _run(env, "crew_gitignore.py", "apply", "--root", str(root))

    after = _run(env, "crew_status.py", "--root", str(root))

    assert after[1:3] == ["config   .crew/config.json schema 7",
                          "roster   explorer, reviewer (1.0 roster: explorer, reviewer, security, researcher)"]
    assert "gitignore current" in after
    assert not [line for line in after
                if "migrate" in line or line.startswith("inert") or "unreadable" in line]
    assert not (root / ".crew" / "crew.json").exists()
