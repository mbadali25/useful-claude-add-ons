"""Builds synthetic crew repositories for tests.

A fixture is a real git repository with a real commit, because the code under
test asks git for HEAD and comparing against a mocked sha would test the mock.
"""
import json
import os
import subprocess


def _git(root, *args):
    subprocess.run(
        ("git",) + args, cwd=root, check=True,
        capture_output=True, text=True,
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
        (out / "graph.json").write_text('{"nodes": [], "edges": []}',
                                        encoding="utf-8")
        # graph_sha: "head" stamps the sidecar with the real HEAD (a fresh
        # graph), a literal sha stamps that (a stale one), None writes no
        # sidecar (a graph built outside crew).
        if graph_sha == "head" and git:
            (out / ".crew-graph-sha").write_text(head_sha(root) + "\n",
                                                 encoding="utf-8")
        elif graph_sha and graph_sha != "head":
            (out / ".crew-graph-sha").write_text(graph_sha + "\n",
                                                 encoding="utf-8")

    return root


def head_sha(root, length=7):
    """Short HEAD sha of a fixture repo."""
    done = subprocess.run(
        ("git", "rev-parse", f"--short={length}", "HEAD"),
        cwd=root, check=True, capture_output=True, text=True,
    )
    return done.stdout.strip()


def commit_with_date(root, path, iso_date):
    """Commit one file with both dates forced, simulating a pulled commit.

    A pull lands commits authored earlier than now, which is what breaks any
    freshness check based on timestamps rather than a recorded sha.
    """
    env = dict(os.environ,
               GIT_AUTHOR_DATE=iso_date, GIT_COMMITTER_DATE=iso_date)
    subprocess.run(("git", "add", path), cwd=root, check=True,
                   capture_output=True, text=True)
    subprocess.run(("git", "commit", "-q", "-m", f"backdated {path}"),
                   cwd=root, check=True, capture_output=True, text=True,
                   env=env)
