"""Builds synthetic crew repositories for tests.

A fixture is a real git repository with a real commit, because the code under
test asks git for HEAD and comparing against a mocked sha would test the mock.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

# Sentinel exit code for the bash probe. Any value a failing-to-launch bash
# would not produce on its own: 127 is "command not found", 126 is "found but
# not executable", 1 and 2 are ordinary script failures.
_PROBE_EXIT = 37
_BASH = "unprobed"


def _usable(candidate):
    """Does this bash actually run a script living at a Windows path?

    This is the whole point of the module-level probe. `shutil.which("bash")`
    answers "is there a file called bash", which is not the question. Under
    PowerShell on Windows it returns `C:\\WINDOWS\\system32\\bash.EXE` -- WSL's
    -- which cannot open a Windows path at all: handed one it exits 127 with
    "No such file or directory" for a file that demonstrably exists.
    """
    tmp = tempfile.mkdtemp()
    try:
        script = os.path.join(tmp, "probe.sh")
        # newline="\n": a CRLF script dies on its shebang as `bad interpreter`.
        with open(script, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(f"exit {_PROBE_EXIT}\n")
        try:
            done = subprocess.run(
                [candidate, script.replace("\\", "/")],
                capture_output=True, text=True, timeout=30,
                stdin=subprocess.DEVNULL, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return done.returncode == _PROBE_EXIT
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def resolve_bash():
    """A bash that can run a script at a Windows path, or None.

    Returns None rather than a path that will not work, so a caller can SKIP the
    `sh` flavour instead of parametrizing it in and collecting failures. The
    previous version of this logic lived copied in six test modules and treated
    "a bash was found" as "a working bash was found"; under PowerShell that made
    `_HAS_BASH` True against WSL's bash and 52 tests failed with `assert 127 ==
    2`. Two agents independently reported that as pre-existing breakage on main
    -- a harness assumption wearing the label of a regression.

    Every candidate is PROVED by running one, because the failure mode here is
    precisely that a plausible-looking path does not work.
    """
    global _BASH  # pylint: disable=global-statement
    if _BASH != "unprobed":
        return _BASH

    candidates = []
    found = shutil.which("bash")
    if found:
        parts = pathlib.Path(found).parts
        lower = [p.lower() for p in parts]
        # Git for Windows ships two bashes. usr/bin/bash.exe is the raw MSYS
        # binary and cannot resolve its own mount table when launched from
        # python.exe; bin/bash.exe is the shim that bootstraps MSYS first.
        if "usr" in lower and "bin" in lower:
            shim = pathlib.Path(*parts[:lower.index("usr")]) / "bin" / "bash.exe"
            if shim.exists():
                candidates.append(str(shim))
        candidates.append(found)
    # Named last, never by editing PATH. Prepending Git's bin/ to PATH is what
    # makes `check-marketplace.py` hang -- it moves `git` to a build that never
    # returns for that script -- so the two gates would want opposite
    # environments. Resolving the interpreter here leaves PATH alone.
    for guess in (r"C:\Program Files\Git\bin\bash.exe",
                  r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if guess not in candidates and os.path.isfile(guess):
            candidates.append(guess)

    for candidate in candidates:
        if _usable(candidate):
            _BASH = candidate
            return _BASH

    print(
        "crew tests: no usable bash - the 'sh' flavour is SKIPPED, not failed. "
        + (f"Found {found!r} but it cannot run a script at a Windows path."
           if found else "No bash on PATH.")
        + " Install Git for Windows, or run the suite from Git Bash.",
        file=sys.stderr,
    )
    _BASH = None
    return _BASH


def _git(root, *args):
    subprocess.run(
        ("git",) + args, cwd=root, check=True,
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )


def make_repo(tmp_path, config=None, metrics=None, codemap=None,
              work_ticket=None, handoff=False, graph=False, git=True,
              graph_sha="head"):
    """Write a synthetic crew repo under tmp_path and return its root."""
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".work").mkdir(parents=True)

    if git:
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "test@example.invalid")
        _git(root, "config", "user.name", "Test")
        (root / "README.md").write_text("fixture\n", encoding="utf-8")
        _git(root, "add", "README.md")
        _git(root, "commit", "-q", "-m", "fixture")

    if config is not None:
        (root / ".crew" / "config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )

    if metrics is not None:
        lines = ["date | ticket | reviewer | BLOCK | FIX",
                 "--- | --- | --- | --- | ---"]
        for ticket, block, fix in metrics:
            lines.append(f"2026-08-01 | {ticket} | codex | {block} | {fix}")
        (root / ".crew" / "metrics.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    if codemap is not None:
        mapdir = root / ".crew" / "codemap"
        mapdir.mkdir()
        for name, body in codemap.items():
            (mapdir / f"{name}.md").write_text(body, encoding="utf-8")

    if work_ticket:
        (root / ".work" / "INDEX.md").write_text(
            f"# Work\n\n- {work_ticket} — in progress\n", encoding="utf-8"
        )

    if handoff:
        (root / ".work" / "HANDOFF.md").write_text(
            "# Handoff\n\n## Next action\nSomething.\n", encoding="utf-8"
        )

    if graph:
        out = root / "graphify-out"
        out.mkdir()
        # graph_sha: "head" stamps built_at_commit with the real, full HEAD
        # sha (a fresh graph) -- graphify records the full sha, not a short
        # one. A literal sha stamps that verbatim (a stale graph). None omits
        # the field entirely (a graph built outside crew, unknown provenance).
        body = {"nodes": [], "links": []}
        if graph_sha == "head" and git:
            body["built_at_commit"] = head_sha(root, length=40)
        elif graph_sha and graph_sha != "head":
            body["built_at_commit"] = graph_sha
        (out / "graph.json").write_text(json.dumps(body), encoding="utf-8")

    return root


def head_sha(root, length=7):
    """Short HEAD sha of a fixture repo."""
    done = subprocess.run(
        ("git", "rev-parse", f"--short={length}", "HEAD"),
        cwd=root, check=True, capture_output=True, text=True,
        stdin=subprocess.DEVNULL,
    )
    return done.stdout.strip()


def commit_file(root, path, message=None):
    """Stage and commit one path at the current time. The ordinary case.

    commit_with_date() exists for the backdated-pull regression; this is the
    plain one, used by the tests that ask which PATHS a commit touched rather
    than when it happened.
    """
    _git(root, "add", path)
    _git(root, "commit", "-q", "-m", message or ("add " + path))


def commit_with_date(root, path, iso_date):
    """Commit one file with both dates forced, simulating a pulled commit.

    A pull lands commits authored earlier than now, which is what breaks any
    freshness check based on timestamps rather than a recorded sha.
    """
    env = dict(os.environ,
               GIT_AUTHOR_DATE=iso_date, GIT_COMMITTER_DATE=iso_date)
    subprocess.run(("git", "add", path), cwd=root, check=True,
                   capture_output=True, text=True,
                   stdin=subprocess.DEVNULL)
    subprocess.run(("git", "commit", "-q", "-m", f"backdated {path}"),
                   cwd=root, check=True, capture_output=True, text=True,
                   env=env, stdin=subprocess.DEVNULL)
