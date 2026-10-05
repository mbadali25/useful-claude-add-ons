"""T-0064: with the real graphify, a denylisted file's symbols never reach the graph.

    python3 -m pytest plugin/crew/tests/test_graph_ignore_graphify.py -q

`test_graph_ignore.py` proves what git's matcher answers. This file proves the
thing that matters: that graphify, fed the `.graphifyignore` that
`crew_graph_ignore.py --write` produces, reads none of the denylisted files.
The canaries are function names defined only in denylisted files, so finding
one anywhere under `graphify-out/` means graphify read that file.

The control runs first and must see the canaries WITHOUT the ignore. If a
graphify release stops recording them, the control fails loudly instead of
the leak test passing over a graph that could never have shown a leak.

Both tests skip, saying the proof did not run, when graphify is not on PATH.
"""
import os
import shutil
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import

import crew_graph_ignore

pytestmark = pytest.mark.skipif(
    shutil.which("graphify") is None,
    reason="graphify not on PATH - the denylist-never-reaches-the-graph proof DID NOT RUN")

CANARIES = ("canary_t0064_secret", "canary_t0064_php")
DENIED_FILES = ("config/secrets.py", "init.php", "keys/k.pem")
FILES = {
    "app.py": "def main():\n    pass\n",
    "config/secrets.py": "def canary_t0064_secret():\n    return 1\n",
    "init.php": "<?php function canary_t0064_php() {}\n",
    "keys/k.pem": "-----BEGIN PRIVATE KEY-----\nnot-a-key\n-----END PRIVATE KEY-----\n",
    ".claude/secrets-denylist": "config/\n/init.php\nkeys/\n",
}
BUILDS = {
    "update": ["graphify", "update", "."],
    "code-only": ["graphify", ".", "--no-viz", "--code-only"],
}


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                   stdin=subprocess.DEVNULL, timeout=30)


@pytest.fixture(name="fixture_repo")
def _fixture_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    for rel, text in FILES.items():
        path = root.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _build(root, tmp_path, command):
    """Run graphify from `root` with HOME in a temporary directory, so it
    writes no user state, and return every file it wrote as one string."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    shutil.rmtree(root / "graphify-out", ignore_errors=True)
    done = subprocess.run(command, cwd=root, capture_output=True, timeout=300, check=False,
                          stdin=subprocess.DEVNULL,
                          env=dict(os.environ, HOME=str(home), USERPROFILE=str(home)))
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")[-2000:]
    out = []
    for base, _dirs, names in os.walk(root / "graphify-out"):
        for name in names:
            with open(os.path.join(base, name), "rb") as handle:
                out.append(handle.read().decode("utf-8", "replace"))
    assert out, f"{' '.join(command)} wrote nothing under graphify-out/"
    return "\n".join(out)


@pytest.mark.parametrize("build", sorted(BUILDS))
def test_canary_reaches_the_graph_without_the_ignore(fixture_repo, tmp_path, build):
    text = _build(fixture_repo, tmp_path, BUILDS[build])

    missing = [c for c in CANARIES if c not in text]

    assert not missing, ("graphify no longer records the canary; the leak test below "
                         f"proves nothing until the canary is changed: {missing}")


@pytest.mark.parametrize("build", sorted(BUILDS))
def test_denylisted_symbols_never_reach_the_graph(fixture_repo, tmp_path, capsys, build):
    assert crew_graph_ignore.main(["--root", str(fixture_repo), "--write"]) == 0
    assert crew_graph_ignore.main(["--root", str(fixture_repo), "--check"]) == 0
    capsys.readouterr()

    text = _build(fixture_repo, tmp_path, BUILDS[build])
    leaked = [s for s in CANARIES + DENIED_FILES if s in text]

    assert (leaked, "app.py" in text, "main" in text) == ([], True, True), leaked
