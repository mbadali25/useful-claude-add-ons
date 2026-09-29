"""Throwaway repositories, tickets and hook runners for the crew 1.0 T3 suites
(test_crew_ticket.py, test_scope_guard.py, test_completion_audit.py).

Everything is built under pytest's tmp_path. Nothing here touches the real
repository, its git directory, or ~/.claude. The `.ps1` flavour runs under
pwsh with `OS=Windows_NT` so its flavour guard proceeds on this Linux host;
without pwsh those cases skip and say so.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_ticket
from review_fixtures import git, init_repo

SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
PWSH = crew_fixtures.resolve_pwsh()
# FLAVOURS runs all three by default: the per-shell parity sample uses it.
# FLAVOUR_MATRIX runs the module by default and `sh`/`ps1` as `slow`
# (conftest.py) -- every other flavoured test uses it. The ids are the same.
FLAVOURS = ("module", "sh", "ps1")
FLAVOUR_MATRIX = ("module", pytest.param("sh", marks=crew_fixtures.SLOW),
                  pytest.param("ps1", marks=crew_fixtures.SLOW))

needs_pwsh = pytest.mark.skipif(PWSH is None, reason="pwsh not installed - the .ps1 "
                                "flavour was NOT run")

SPEC = """# {ticket}

## Intent
Change the widget.

## Exclusions
Nothing else.

## Evidence
- src/app.py:1

## Unknowns
None.

## Touch
{touch}

## Acceptance checks
- tests pass
"""

PLAN = """# Plan

## Step 1
Files: {files}
Test: pytest
Risk: low
"""


def make_repo(tmp_path, mode="block", name="r"):
    """A git repo with `.crew/config.json` carrying `scope.mode`, a tracked
    `src/app.py` and `other/keep.py`, and `.work/` ignored."""
    root = init_repo(tmp_path / name)
    (root / ".crew").mkdir()
    if mode is not None:
        (root / ".crew" / "config.json").write_text(
            json.dumps({"scope": {"mode": mode}}), encoding="utf-8")
    (root / ".gitignore").write_text(".work/\n.crew/\n", encoding="utf-8")
    for rel in ("src/app.py", "other/keep.py", "secret/x.py"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x = 1\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    return root


def make_ticket(root, ticket="T-1", touch=("src/**",), files=None, activate=True):
    folder = root / ".work" / "tickets" / ticket
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "direction.md").write_text("go\n", encoding="utf-8")
    (folder / "spec.md").write_text(
        SPEC.format(ticket=ticket, touch="\n".join(f"- `{t}`" for t in touch)),
        encoding="utf-8")
    (folder / "plan.md").write_text(
        PLAN.format(files=", ".join(files or ["src/app.py"])), encoding="utf-8")
    if activate:
        crew_ticket.activate(str(root), ticket)
    return folder


def approve_as_user(root, ticket="T-1"):
    """Approve the way the user does: a `/crew:approve <id>` prompt through
    approval_hook.py's module entry point (the receipt says `user-prompt`)."""
    import approval_hook  # pylint: disable=import-outside-toplevel
    code = approval_hook.handle(prompt(root, f"/crew:approve {ticket}"))
    assert code == 0, f"approval_hook refused {ticket}"


def accepted_ledger(root, ticket="T-1", kind="clean"):
    """`ticket`'s review ledger ACCEPTED through review_ledger's own writers:
    one reserved round recorded CLEAN (`kind="clean"`), or recorded FINDINGS
    and then owner-accepted (`kind="owner-accepted"`). The recorded bundle hash
    is "0"*64, which no tree rebuilds -- a merged ticket's shape (T-0504)."""
    import review_ledger  # pylint: disable=import-outside-toplevel
    ok, number, message = review_ledger.reserve(str(root), ticket, "claude")
    assert ok, message
    review_ledger.record(str(root), ticket, number, {
        "verdict": "CLEAN" if kind == "clean" else "FINDINGS", "provider": "claude",
        "model": None, "bundle_sha256": "0" * 64, "base": "HEAD", "head": "HEAD"})
    if kind == "owner-accepted":
        saved = review_ledger._current_hash  # pylint: disable=protected-access
        review_ledger._current_hash = lambda _root, _base: "0" * 64  # pylint: disable=protected-access
        try:
            review_ledger.accept(str(root), ticket, by="owner")
        finally:
            review_ledger._current_hash = saved  # pylint: disable=protected-access


def corrupt_ledger(root, ticket="T-1"):
    """`ticket`'s review ledger present and unreadable (state UNKNOWN)."""
    import review_ledger  # pylint: disable=import-outside-toplevel
    path = review_ledger.ledger_path(str(root), ticket)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("{")


def index(root, rows):
    """Write `.work/INDEX.md` with one `id | status | ...` row per (id, status)."""
    text = "".join(f"{ticket} | {status} | low | r | title\n" for ticket, status in rows)
    path = root / ".work" / "INDEX.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def spec_done(root, ticket="T-1"):
    """Rewrite `ticket`'s spec header to say `status: done`."""
    path = root / ".work" / "tickets" / ticket / "spec.md"
    first, rest = path.read_text(encoding="utf-8").split("\n", 1)
    path.write_text(f"{first} title          status: done   risk: low\n{rest}",
                    encoding="utf-8")


def prompt(root, text, session="sess-1"):
    return {"hook_event_name": "UserPromptSubmit", "prompt": text, "cwd": str(root),
            "session_id": session, "prompt_id": "p-1"}


def ready(root, ticket="T-1", touch=("src/**",), record_base=True):
    """A ticket made, activated, approved and with its scope base recorded."""
    make_ticket(root, ticket, touch)
    approve_as_user(root, ticket)
    if record_base:
        subprocess.run([sys.executable, os.path.join(SCRIPTS, "scope_base.py"),
                        "--root", str(root), "--record", ticket],
                       check=True, capture_output=True, stdin=subprocess.DEVNULL)


def env_for(root, **extra):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(root)
    env.update(extra)
    return env


def run_hook(flavour, stem, payload, root):
    """Run one hook flavour. `stem` is `scope_guard` or `completion_audit`.
    Returns (code, stdout, stderr) as text."""
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    dashed = stem.replace("_", "-")
    if flavour == "module":
        cmd = [sys.executable, os.path.join(SCRIPTS, stem + ".py")]
        env = env_for(root)
    elif flavour == "sh":
        cmd = [crew_fixtures.resolve_bash() or "bash", os.path.join(SCRIPTS, dashed + ".sh")]
        env = env_for(root)
    else:
        if PWSH is None:
            pytest.skip("pwsh not installed - the .ps1 flavour was NOT run")
        cmd = [PWSH, "-NoProfile", "-File", os.path.join(SCRIPTS, dashed + ".ps1")]
        env = env_for(root, OS="Windows_NT")
    done = subprocess.run(cmd, input=data, cwd=str(root), capture_output=True, env=env,
                          check=False, timeout=120)
    return (done.returncode, done.stdout.decode("utf-8", "replace"),
            done.stderr.decode("utf-8", "replace"))


def edit(root, path, tool="Write"):
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    tool_input = {key: str(path)}
    if tool == "MultiEdit":
        tool_input["edits"] = [{"old_string": "x", "new_string": "y"}]
    return {"hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": tool_input, "cwd": str(root)}


def stop(root, active=False):
    return {"hook_event_name": "Stop", "stop_hook_active": active, "cwd": str(root)}


def common_dir(root):
    return crew_ticket.common_dir(str(root))
