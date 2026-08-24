"""Smoke tests for the fixture builder that every later crew test depends on.

These aren't testing crew's own scripts -- there's nothing under
hooks/scripts or skills/crew-graph/scripts yet for later tasks to add. They
exist so make_repo/head_sha/commit_with_date are proven to work before five
later tasks build on them, and so this harness lands with a green pytest run
instead of "no tests collected" (pytest exit code 5).
"""
import re

import context  # noqa: F401  pylint: disable=unused-import
import helpers

SHA_RE = re.compile(r"^[0-9a-f]{7}$")


def test_context_puts_script_dirs_on_sys_path():
    import sys  # pylint: disable=import-outside-toplevel
    assert any(p.endswith("hooks\\scripts") or p.endswith("hooks/scripts")
               for p in sys.path)
    assert any(p.endswith("crew-graph\\scripts")
               or p.endswith("crew-graph/scripts") for p in sys.path)


def test_make_repo_default_is_a_real_git_repo(tmp_path):
    root = helpers.make_repo(tmp_path)
    assert (root / ".crew").is_dir()
    assert (root / ".work").is_dir()
    assert (root / ".git").is_dir()
    assert SHA_RE.match(helpers.head_sha(root))


def test_make_repo_git_false_skips_commit(tmp_path):
    root = helpers.make_repo(tmp_path, git=False)
    assert not (root / ".git").exists()


def test_make_repo_writes_config(tmp_path):
    root = helpers.make_repo(tmp_path, config={"provider": "jira"})
    assert '"provider"' in (root / ".crew" / "config.json").read_text(
        encoding="utf-8")


def test_make_repo_omits_config_file_when_none(tmp_path):
    root = helpers.make_repo(tmp_path, config=None)
    assert not (root / ".crew" / "config.json").exists()


def test_make_repo_writes_metrics_rows(tmp_path):
    root = helpers.make_repo(
        tmp_path, metrics=[("ABC-1", 2, 3), ("ABC-2", 0, 1)])
    text = (root / ".crew" / "metrics.md").read_text(encoding="utf-8")
    assert "ABC-1" in text and "2" in text and "3" in text
    assert "ABC-2" in text


def test_make_repo_writes_codemap_files(tmp_path):
    root = helpers.make_repo(
        tmp_path, codemap={"auth": "# Auth\n", "billing": "# Billing\n"})
    mapdir = root / ".crew" / "codemap"
    assert (mapdir / "auth.md").read_text(encoding="utf-8") == "# Auth\n"
    assert (mapdir / "billing.md").read_text(encoding="utf-8") == "# Billing\n"


def test_make_repo_writes_work_ticket(tmp_path):
    root = helpers.make_repo(tmp_path, work_ticket="ABC-9")
    assert "ABC-9" in (root / ".work" / "INDEX.md").read_text(
        encoding="utf-8")


def test_make_repo_writes_handoff(tmp_path):
    root = helpers.make_repo(tmp_path, handoff=True)
    assert (root / ".work" / "HANDOFF.md").exists()


def test_make_repo_no_handoff_by_default(tmp_path):
    root = helpers.make_repo(tmp_path)
    assert not (root / ".work" / "HANDOFF.md").exists()


def test_make_repo_graph_sha_head_matches_real_head(tmp_path):
    root = helpers.make_repo(tmp_path, graph=True, graph_sha="head")
    sidecar = root / "graphify-out" / ".crew-graph-sha"
    assert sidecar.read_text(encoding="utf-8").strip() == helpers.head_sha(
        root)


def test_make_repo_graph_sha_literal_is_stamped_verbatim(tmp_path):
    root = helpers.make_repo(tmp_path, graph=True, graph_sha="deadbee")
    sidecar = root / "graphify-out" / ".crew-graph-sha"
    assert sidecar.read_text(encoding="utf-8").strip() == "deadbee"


def test_make_repo_graph_sha_none_writes_no_sidecar(tmp_path):
    root = helpers.make_repo(tmp_path, graph=True, graph_sha=None)
    assert (root / "graphify-out" / "graph.json").exists()
    assert not (root / "graphify-out" / ".crew-graph-sha").exists()


def test_make_repo_graph_without_git_writes_no_sidecar(tmp_path):
    # graph_sha defaults to "head", but with git=False there is no HEAD to
    # stamp -- the "head" branch requires git, so no sidecar is written at
    # all. A test for a fresh, stamped graph must pass git=True (the
    # default) alongside graph=True.
    root = helpers.make_repo(tmp_path, graph=True, git=False)
    assert not (root / "graphify-out" / ".crew-graph-sha").exists()


def test_head_sha_length(tmp_path):
    root = helpers.make_repo(tmp_path)
    assert len(helpers.head_sha(root, length=12)) == 12


def test_commit_with_date_backdates_author_and_committer(tmp_path):
    root = helpers.make_repo(tmp_path)
    (root / "later.txt").write_text("x\n", encoding="utf-8")
    helpers.commit_with_date(root, "later.txt", "2020-01-01T00:00:00")
    import subprocess  # pylint: disable=import-outside-toplevel
    done = subprocess.run(
        ("git", "log", "-1", "--format=%ad", "--date=short"),
        cwd=root, check=True, capture_output=True, text=True,
    )
    assert done.stdout.strip() == "2020-01-01"
