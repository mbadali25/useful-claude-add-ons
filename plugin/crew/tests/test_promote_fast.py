"""crew 1.2.115: promote-gate.sh's allow fast path, _promote_fast.py.

It may only ever say "allow" (exit 99) where the full gate would have allowed;
anything else falls through to the full gate, unchanged. So every case here is
either a must-allow (the fast path proves it) or a must-fall-through (it must
NOT prove it, and the full gate decides). The gate-level must-block twins - a
declared deploy, a dirty map - are in test_guard_spawns.py and the existing
promote-gate suites, which now run with the fast path in front of them.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import _promote_fast

_MAP = {"environments": {"prod": {"deploy": "deploy-prod", "rollback": "none",
                                  "rollbackReason": "fixture"}}}
_DISPATCH_MAP = {"environments": {"prod": {
    "deploy": "gh workflow run deploy.yml -f environment=prod",
    "rollback": "none", "rollbackReason": "fixture"}}}


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "T")
    _git(root, "config", "core.autocrlf", "false")
    monkeypatch.chdir(root)
    monkeypatch.delenv("CREW_GATE_DEADLINE", raising=False)
    monkeypatch.delenv("CREW_MAP_DIRTY", raising=False)
    monkeypatch.delenv("CREW_HEAD_MAP", raising=False)
    return root


def _commit_map(root, doc):
    (root / ".crew" / "verify.json").write_bytes(json.dumps(doc, indent=2).encode())
    _git(root, "add", "-A", "-f")
    _git(root, "commit", "-q", "-m", "map")


def _payload(command, **extra):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, **extra}).encode()


# --- MUST ALLOW --------------------------------------------------------------


def test_must_allow_an_unrelated_command_with_a_clean_map(repo):
    _commit_map(repo, _MAP)
    assert _promote_fast.allowed(_payload("echo hi"))


def test_must_allow_a_crlf_checkout_of_the_committed_map(repo):
    """core.autocrlf=true writes CRLF while HEAD's blob is LF: the same map."""
    _commit_map(repo, _MAP)
    path = repo / ".crew" / "verify.json"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert _promote_fast.allowed(_payload("git status\nls -la"))


def test_must_allow_through_main_with_exit_99(repo):
    _commit_map(repo, _MAP)
    proc = subprocess.run([sys.executable, _promote_fast.__file__], input=_payload("echo hi"),
                          cwd=repo, capture_output=True, check=False, timeout=60)
    assert proc.returncode == _promote_fast.ALLOW == 99, proc.stderr


# --- MUST FALL THROUGH (the full gate decides) -------------------------------


@pytest.mark.parametrize("command", [
    "deploy-prod",                       # the containment match names prod
    "cd sub && DEPLOY-PROD --now",       # ... ignoring case, wrapped
], ids=["declared", "declared-wrapped"])
def test_must_fall_through_on_a_declared_deploy(repo, command):
    _commit_map(repo, _MAP)
    assert not _promote_fast.allowed(_payload(command))


def test_must_fall_through_on_a_dispatch_of_a_declared_workflow(repo):
    _commit_map(repo, _DISPATCH_MAP)
    # Inputs reordered, so the containment match does not see the declared
    # text: only the dispatch read names prod here.
    assert not _promote_fast.allowed(_payload("gh workflow run deploy.yml -f x=1 -f environment=prod"))


def test_must_fall_through_on_a_dispatch_it_cannot_read(repo):
    """A substitution in the dispatched workflow is could-not-tell: the full gate's to say."""
    _commit_map(repo, _DISPATCH_MAP)
    # decide() raises Block here; main() turns any raise into "not proved".
    with pytest.raises(Exception, match="could not tell"):
        _promote_fast.allowed(_payload("gh workflow run $(echo deploy.yml)"))


def test_must_fall_through_on_an_uncommitted_map_edit(repo):
    _commit_map(repo, _MAP)
    (repo / ".crew" / "verify.json").write_text(json.dumps({"environments": {}}), encoding="utf-8")
    assert not _promote_fast.allowed(_payload("echo hi"))


def test_must_fall_through_on_an_untracked_map(repo):
    (repo / "seed").write_text("x", encoding="utf-8")
    _git(repo, "add", "seed")
    _git(repo, "commit", "-q", "-m", "seed")
    (repo / ".crew" / "verify.json").write_text(json.dumps(_MAP), encoding="utf-8")
    assert not _promote_fast.allowed(_payload("echo hi"))


def test_must_fall_through_on_a_map_the_match_refuses(repo):
    """A committed map whose environment is not an object: the full gate's
    strict read exits 4 and blocks. The fast path runs that same read."""
    _commit_map(repo, {"environments": {"prod": "deploy-prod"}})
    assert not _promote_fast.allowed(_payload("echo hi"))


@pytest.mark.parametrize("command", [
    "/usr/bin/env true",       # Git Bash rewrites a leading /x into C:/...
    "X=/opt/y run",            # ... and x=/y
    "./deploy.sh",             # any / in the first word is a doubt
    "echo caf\u00e9",          # not plain ASCII
    "echo a\rb",               # a CR the full gate strips
    "   \n",                   # blank: the full gate's to pass
], ids=["leading-slash", "assign-slash", "dot-slash", "non-ascii", "cr", "blank"])
def test_must_fall_through_on_a_command_it_cannot_read_identically(repo, command):
    _commit_map(repo, _MAP)
    assert not _promote_fast.allowed(_payload(command))


@pytest.mark.parametrize("raw", [b"not json", b'{"tool_input": "x"}', b'{"tool_input": {"command": 5}}',
                                 b"\xef\xbb\xbf" + _payload("echo hi")],
                         ids=["not-json", "input-not-object", "command-not-string", "bom"])
def test_must_fall_through_on_a_payload_it_cannot_read(repo, raw):
    """allowed() may answer False or raise; main() turns a raise into 0."""
    _commit_map(repo, _MAP)
    try:
        proved = _promote_fast.allowed(raw)
    except ValueError:
        proved = False
    assert not proved


def test_must_fall_through_when_a_project_file_shadows_an_import(repo):
    """The full gate runs the match as `python -`, cwd first on the path."""
    _commit_map(repo, _MAP)
    (repo / "json.py").write_text("raise SystemExit(7)\n", encoding="utf-8")
    assert not _promote_fast.allowed(_payload("echo hi"))


def test_must_fall_through_when_the_match_cannot_be_found(repo, monkeypatch, tmp_path):
    _commit_map(repo, _MAP)
    fake = tmp_path / "promote-gate.sh"
    fake.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    monkeypatch.setattr(_promote_fast, "_GATE", str(fake))
    assert not _promote_fast.allowed(_payload("echo hi"))


def test_must_fall_through_with_no_time_left(repo, monkeypatch):
    _commit_map(repo, _MAP)
    monkeypatch.setenv("CREW_GATE_DEADLINE", "1")
    assert not _promote_fast.allowed(_payload("echo hi"))


@pytest.mark.parametrize("raw", [b"{", b"\xef\xbb\xbf{}", b'{"tool_input": "x"}'])
def test_main_never_exits_99_on_a_doubt(repo, raw):
    proc = subprocess.run([sys.executable, _promote_fast.__file__], input=raw,
                          cwd=repo, capture_output=True, check=False, timeout=60)
    assert proc.returncode == 0, proc.stderr


def test_the_match_source_is_the_gates_own_heredoc():
    """Read out of promote-gate.sh, never copied: it must be found, compile,
    and be the block the full gate runs with `"$PY" - "$CMD"`."""
    source = _promote_fast._match_source()  # pylint: disable=protected-access
    assert source is not None
    assert "def matching(envs, strict):" in source
    assert source.rstrip().endswith("pick(matching(envs, strict=True))")
    compile(source, "heredoc", "exec")
    with open(_promote_fast._GATE, encoding="utf-8") as handle:  # pylint: disable=protected-access
        assert handle.read().count(_promote_fast._MATCH_START) == 1  # pylint: disable=protected-access
    assert os.path.basename(_promote_fast._GATE) == "promote-gate.sh"  # pylint: disable=protected-access
