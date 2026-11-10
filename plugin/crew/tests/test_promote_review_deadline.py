"""train_base_sha honours the gate deadline (SRL-3312 Codex finding).

Base-branch discovery runs several git probes; once the deadline is past no
further probe may run and the answer is None (review stays required)."""
import os
import subprocess
import time

import context  # noqa: F401  pylint: disable=unused-import
import _promote_review
import scope_base
from _train_base import seed_train_base

_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.invalid"}


def _repo(tmp_path):
    root = str(tmp_path)
    subprocess.run(("git", "init", "-q"), cwd=root, check=True)
    return root, seed_train_base(root)


def test_slow_git_probes_stop_at_deadline(tmp_path, monkeypatch):
    """Control: git_out slowed to 0.2s and a 0.05s deadline. The old code ran
    all four probes (~0.8s); now no probe runs past the deadline."""
    root, _ = _repo(tmp_path)
    calls = []

    def slow_git_out(*_args):
        calls.append(1)
        time.sleep(0.2)

    monkeypatch.setattr(scope_base.crew_common, "git_out", slow_git_out)
    start = time.time()
    assert _promote_review.train_base_sha(root, "a" * 40, time.time() + 0.05) is None
    assert time.time() - start < 0.3
    assert len(calls) <= 1


def test_generous_deadline_still_finds_base(tmp_path):
    """Not over-fixed: a generous deadline still finds the merge-base."""
    root, base = _repo(tmp_path)
    subprocess.run(("git", "commit", "-q", "--allow-empty", "-m", "x"), cwd=root, check=True,
                   env=_ENV)
    head = subprocess.run(("git", "rev-parse", "HEAD"), cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()
    assert _promote_review.train_base_sha(root, head, time.time() + 10) == base
