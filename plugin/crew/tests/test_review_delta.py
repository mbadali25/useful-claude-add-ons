"""The delta gate (L-0522): a catch-up merge that adds none of the ticket's own
code keeps the review receipt; anything the gate cannot prove reads stale.

Every case builds a real repository: `main` (the integration branch, held as
the merge train's base) and a lane worktree on `lane` holding the train for
T-1. A real CLEAN (or owner-accepted) round is recorded through
`review_ledger.record` from a real `review_patch.compute` bundle, and the
verdict is read from `review_ledger.py --check-receipt` (exit code and line).
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_refresh_check
import crew_train
import review_delta
import review_ledger as rl
import review_patch
from review_fixtures import git, init_repo

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_LEDGER = os.path.join(_SCRIPTS, "review_ledger.py")
_RUN = os.path.join(_SCRIPTS, "review_run.py")
_REPO_ROOT = pathlib.Path(context._ROOT).parents[1]  # pylint: disable=protected-access
TICKET = "T-1"
KEPT = "review-ledger: receipt kept by delta gate:"
STALE = "review-ledger: receipt is stale"

CODEMAP = "anchor: proj@{a}\nverified: 2026-10-01\n\n# sub\n\n{body}\n"
RULES = ("---\npaths:\n  - \"src/**\"\n---\n<!-- crew:generated source=.crew/codemap/sub.md "
         "sha256={d} -- do not hand-edit; regenerate with crew_instructions.py rules -->\n# sub\n"
         "Code map anchor `{a}`; if it is behind HEAD, re-check with `git diff --name-only "
         "{a}..HEAD -- <cited paths>`.\n{extra}Full note: `.crew/codemap/sub.md`.\n")
DIAGRAM = "%% anchor: proj@{a}\nflowchart LR\n  a --> b\n"
GENERATED = "%% Generated from proj@{a} on {date}. Verify before trusting.\nflowchart LR\n  a --> b\n"
PLUGIN = '{{\n  "name": "{name}",\n  "version": "{v}",\n  "description": "d",\n  "flag": true\n}}\n'
MARKET = ('{{\n  "name": "m",\n  "plugins": [\n    {{"name": "p", "source": "./plugin/p", '
          '"version": "{p}"}},\n    {{"name": "q", "source": "./plugin/q", "version": "{q}"}}\n'
          '  ]\n}}\n')


@pytest.fixture(autouse=True)
def _isolated_git(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    glob = home / ".gitconfig"
    glob.write_text("[user]\n\tname = t\n\temail = t@example.com\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(glob))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _write(root, rel, text):
    path = pathlib.Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)


def _commit(root, files=None, message="c"):
    for rel, text in (files or {}).items():
        _write(root, rel, text)
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def _seed():
    return {
        ".gitignore": ".work/\n",
        "app.py": "def app():\n    return 1\n",
        "lib.py": "def lib():\n    return 1\n",
        "plugin/p/.claude-plugin/plugin.json": PLUGIN.format(name="p", v="1.0.0"),
        "plugin/q/.claude-plugin/plugin.json": PLUGIN.format(name="q", v="2.0.0"),
        ".claude-plugin/marketplace.json": MARKET.format(p="1.0.0", q="2.0.0"),
        "CHANGELOG.md": "# Changelog\n\n## 1.0.0\n\n- first\n",
        "TODO.md": "# TODO\n",
        "plugin/PLUGINS.md": "| p | 1.0.0 |\n",
        "plugin/p/BUDGETS.md": "# Budgets\n\n10 lines\n",
        ".crew/codemap/sub.md": CODEMAP.format(a="aaaaaaa", body="body line"),
        ".claude/rules/sub.md": RULES.format(d="1" * 16, a="aaaaaaa", extra=""),
        "docs/diagrams/flow.mmd": DIAGRAM.format(a="aaaaaaa"),
        "docs/diagrams/gen.mmd": GENERATED.format(a="aaaaaaa", date="2026-10-01"),
        "graphify-out/graph.json": '{"nodes": 1}\n',
        "graphify-out/GRAPH_REPORT.md": "# Graph\n\n1 node\n",
    }


class World:  # pylint: disable=too-few-public-methods
    def __init__(self, repo, lane, start):
        self.repo, self.lane, self.start = repo, lane, start


def _make_world(tmp_path, extra=None):
    repo = init_repo(tmp_path / "r")
    start = _commit(repo, dict(_seed(), **(extra or {})), "seed the world")
    lane = tmp_path / "lane"
    git(repo, "worktree", "add", "-q", "-b", "lane", str(lane), "main")
    spec = lane / ".work" / "tickets" / TICKET / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(f"# {TICKET}\n\n## Intent\n\nx\n\n## Touch\n\n- `app.py`\n", encoding="utf-8")
    assert crew_train.main(["--root", str(repo), "arm"]) == 0
    assert crew_train.main(["--root", str(lane), "acquire", "--ticket", TICKET,
                            "--base", "main"]) == 0
    _commit(lane, {"app.py": "def app():\n    return 2  # the ticket's change\n"}, "ticket")
    return World(repo, lane, start)


@pytest.fixture(name="world")
def _world(tmp_path):
    return _make_world(tmp_path)


def _review(world, verdict="CLEAN"):
    manifest, _, _ = review_patch.compute(str(world.lane), world.start)
    ok, number, _ = rl.reserve(str(world.lane), TICKET, "codex")
    assert ok
    rl.record(str(world.lane), TICKET, number, {
        "verdict": verdict, "counts": {}, "bundle_sha256": manifest["bundle_sha256"],
        "base": world.start, "head": manifest["head"], "provider": "codex", "model": None,
        "model_family": "gpt"})
    return manifest


def _main(world, files, message="main moved"):
    return _commit(world.repo, files, message)


def _catch_up(world):
    git(world.lane, "merge", "--no-edit", "-q", "main")


def _check(world):
    done = subprocess.run([sys.executable, _LEDGER, "--root", str(world.lane), "--ticket",
                           TICKET, "--check-receipt"], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False)
    return done.returncode, done.stdout + done.stderr


def _kept(world):
    code, out = _check(world)
    assert code == 0 and out.startswith(KEPT), out
    return out


def _stale(world, *needles):
    code, out = _check(world)
    assert code == 1 and out.startswith(STALE), out
    assert "delta gate:" in out or "excluded path" in out or "base_sha" in out, out
    for needle in needles:
        assert needle in out, out
    return out


def _bump(world, version, plugin="p"):
    """Bump plugin p in its plugin.json, its marketplace entry and CHANGELOG."""
    lane = world.lane
    market = (lane / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
    old = re.search(rf'"name": "{plugin}", "source": "[^"]+", "version": "([^"]+)"', market)
    market = market.replace(old.group(0), old.group(0).replace(old.group(1), version))
    pj = lane / f"plugin/{plugin}/.claude-plugin/plugin.json"
    text = re.sub(r'"version": "[^"]+"', f'"version": "{version}"', pj.read_text(encoding="utf-8"))
    log = (lane / "CHANGELOG.md").read_text(encoding="utf-8") + f"\n## {version}\n\n- bump\n"
    return {".claude-plugin/marketplace.json": market,
            f"plugin/{plugin}/.claude-plugin/plugin.json": text, "CHANGELOG.md": log}


def _bump_plugin(world, text):
    """A version bump of plugin p alone (no marketplace entry), so a stale
    reason can only name plugin.json."""
    log = (world.lane / "CHANGELOG.md").read_text(encoding="utf-8") + "\n## 1.0.1\n\n- bump\n"
    return {"plugin/p/.claude-plugin/plugin.json": text, "CHANGELOG.md": log}


# ---------------------------------------------------------------- must keep

def test_catch_up_merge_disjoint_from_the_ticket_keeps_the_receipt(world):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)

    out = _kept(world)

    assert "1 paths identical" in out and "via main" in out, out


def test_catch_up_then_version_bump_and_changelog_keeps_the_receipt(world):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    files = _bump(world, "1.0.1")
    files["plugin/PLUGINS.md"] = "| p | 1.0.1 |\n"
    files["plugin/p/BUDGETS.md"] = "# Budgets\n\n11 lines\n"
    _commit(world.lane, files, "bump")

    out = _kept(world)

    for name in ("CHANGELOG.md", "plugin/PLUGINS.md", "plugin/p/BUDGETS.md",
                 "plugin/p/.claude-plugin/plugin.json", ".claude-plugin/marketplace.json"):
        assert name in out, out


def test_catch_up_then_version_bump_of_the_real_crew_manifests_keeps_the_receipt(tmp_path):
    """Copies of the real marketplace.json and crew plugin.json, bumped the way
    a lane bumps them."""
    market = (_REPO_ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
    crew = (_REPO_ROOT / "plugin/crew/.claude-plugin/plugin.json").read_text(encoding="utf-8")
    world = _make_world(tmp_path, {".claude-plugin/marketplace.json": market,
                                   "plugin/crew/.claude-plugin/plugin.json": crew})
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    version = json.loads(crew)["version"]
    head, last = version.rsplit(".", 1)
    bumped = f"{head}.{int(last) + 1}"
    token = f'"version": "{version}"'
    at = market.index(token, market.index('"name": "crew"'))
    market2 = market[:at] + f'"version": "{bumped}"' + market[at + len(token):]
    crew2 = crew.replace(token, f'"version": "{bumped}"', 1)
    _commit(world.lane, {".claude-plugin/marketplace.json": market2,
                         "plugin/crew/.claude-plugin/plugin.json": crew2}, "bump crew")

    _kept(world)


def test_catch_up_then_anchor_only_refresh_keeps_the_receipt(world):
    _review(world)
    # Another lane's re-anchor with provenance prose lands on main first.
    _main(world, {".crew/codemap/sub.md": CODEMAP.format(a="bbbbbbb", body="body line\n\nmain's "
                                                         "provenance"),
                  ".claude/rules/sub.md": RULES.format(d="2" * 16, a="bbbbbbb", extra=""),
                  "lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    # This lane's refresh: the anchor sha only, rules regenerated from it.
    _commit(world.lane, {
        ".crew/codemap/sub.md": CODEMAP.format(a="ccccccc", body="body line\n\nmain's provenance"),
        ".claude/rules/sub.md": RULES.format(d="3" * 16, a="ccccccc", extra=""),
        "docs/diagrams/flow.mmd": DIAGRAM.format(a="ccccccc"),
        "docs/diagrams/gen.mmd": GENERATED.format(a="ccccccc", date="2026-10-01"),
    }, "re-anchor")

    out = _kept(world)

    assert "anchor-only" in out, out


def test_catch_up_with_rebuilt_graph_keeps_the_receipt(world):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    _commit(world.lane, {"graphify-out/graph.json": '{"nodes": 2}\n',
                         "graphify-out/GRAPH_REPORT.md": "# Graph\n\n2 nodes\n"}, "graph")

    _kept(world)


def test_bump_only_without_a_merge_keeps_the_receipt(world):
    _review(world)
    _commit(world.lane, _bump(world, "1.0.1"), "bump")

    out = _kept(world)

    assert f"base {world.start[:12]}" in out, out


def test_two_successive_catch_ups_keep_the_receipt(world):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    _main(world, {"lib.py": "def lib():\n    return 3\n"})
    _catch_up(world)

    _kept(world)


def test_owner_accepted_findings_survive_a_catch_up(world):
    _review(world, "FINDINGS")
    rl.accept(str(world.lane), TICKET, "owner")
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)

    out = _kept(world)

    assert "owner-accepted" in out, out


def test_unchanged_tree_still_takes_the_fast_path(world):
    manifest = _review(world)

    code, out = _check(world)

    assert code == 0, out
    assert out == (f"review-ledger: receipt current: round 1 clean, bundle "
                   f"{str(manifest['bundle_sha256'])[:12]}\n"), out


def test_unchanged_bundle_with_rebuilt_graph_keeps_the_fast_path(world):
    _review(world)
    _commit(world.lane, {"graphify-out/graph.json": '{"nodes": 2}\n',
                         "graphify-out/GRAPH_REPORT.md": "# Graph\n\n2 nodes\n"}, "graph")

    code, out = _check(world)

    assert code == 0 and out.startswith("review-ledger: receipt current:"), out


def test_marketplace_bump_of_the_bumped_plugin_keeps_the_receipt(world):
    _review(world)
    _commit(world.lane, _bump(world, "1.0.7"), "bump")

    out = _kept(world)

    assert ".claude-plugin/marketplace.json" in out, out


def test_untracked_metrics_file_written_by_the_review_keeps_the_fast_path(world):
    """review_run appends .crew/metrics.md after every round; in a repository
    that does not gitignore it, an untracked file never lands, so check E's
    third range (the index) does not see it."""
    _review(world)
    _write(world.lane, ".crew/metrics.md", "| a review row |\n")

    code, out = _check(world)

    assert code == 0 and out.startswith("review-ledger: receipt current:"), out


# --------------------------------------------------------------- must stale

def test_ticket_file_edited_after_review_committed_is_stale(world):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    _commit(world.lane, {"app.py": "def app():\n    return 3\n"}, "unreviewed")

    _stale(world, "app.py")


def test_ticket_file_edited_after_review_uncommitted_is_stale(world):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    _write(world.lane, "app.py", "def app():\n    return 3\n")

    _stale(world, "not clean")


def test_main_changed_a_ticket_file_merged_cleanly_is_stale(world):
    _commit(world.lane, {"app.py": "def app():\n    return 2  # the ticket's change\n\n\n\n"
                                   "# tail\n"}, "longer")
    _review(world)
    _main(world, {"app.py": "# main's header\ndef app():\n    return 1\n"})
    _catch_up(world)

    _stale(world, "app.py")


def test_merge_resolution_that_changed_a_ticket_file_is_stale(world):
    _review(world)
    _main(world, {"app.py": "def app():\n    return 9\n"})
    code = subprocess.run(["git", "merge", "--no-edit", "-q", "main"], cwd=world.lane,
                          capture_output=True, check=False).returncode
    assert code != 0
    _commit(world.lane, {"app.py": "def app():\n    return 29  # resolved\n"}, "resolve")

    _stale(world, "app.py")


def test_merge_resolved_to_the_reviewed_bytes_over_mains_edit_is_stale(world):
    """new_id equal, old_id moved: only the old-blob identity stales it."""
    _review(world)
    _main(world, {"app.py": "def app():\n    return 9\n", "lib.py": "def lib():\n    return 2\n"})
    subprocess.run(["git", "merge", "--no-edit", "-q", "main"], cwd=world.lane,
                   capture_output=True, check=False)
    _commit(world.lane, {"app.py": "def app():\n    return 2  # the ticket's change\n"}, "ours")

    _stale(world, "app.py differs")


def test_new_non_exempt_file_after_review_is_stale(world):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    _commit(world.lane, {"extra.py": "x = 1\n"}, "extra")

    _stale(world, "extra.py is not in the reviewed delta")


def test_reviewed_change_reverted_is_stale(world):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    _commit(world.lane, {"app.py": "def app():\n    return 1\n"}, "revert")

    _stale(world, "app.py is reviewed but gone")


@pytest.mark.parametrize("files, needle", [
    ({"plugin/p/.claude-plugin/plugin.json":
      PLUGIN.format(name="p", v="1.0.1").replace('"flag": true', '"flag": true,\n  "hooks": 1')},
     "plugin.json"),
    ({"plugin/p/.claude-plugin/plugin.json": PLUGIN.format(name="p", v="1.0.x")}, "plugin.json"),
    ({".claude-plugin/marketplace.json": MARKET.format(p="1.0.0", q="2.0.0").replace(
        "\n  ]", ',\n    {"name": "r", "source": "./r", "version": "1.0.0"}\n  ]')},
     "marketplace.json"),
])
def test_manifest_change_beyond_version_is_stale(world, files, needle):
    _review(world)
    _commit(world.lane, files, "manifest")

    _stale(world, needle)


@pytest.mark.parametrize("old, new", [
    ('"flag": true', '"flag": 1'),
    ('"flag": true', '"flag": true, "n": 1.0'),
])
def test_manifest_type_changes_are_stale(world, old, new):
    files = _bump_plugin(world, PLUGIN.format(name="p", v="1.0.1").replace(old, new))
    _review(world)
    _commit(world.lane, files, "bump plus a type change")

    _stale(world, "plugin.json")


@pytest.mark.parametrize("before, after", [("1", "1.0"), ("1", "1e0")])
def test_manifest_int_to_float_is_stale(world, before, after):
    _commit(world.lane, {"plugin/p/.claude-plugin/plugin.json":
                         PLUGIN.format(name="p", v="1.0.0").replace('"flag": true',
                                                                    f'"n": {before}')}, "n")
    _review(world)
    text = PLUGIN.format(name="p", v="1.0.1").replace('"flag": true', f'"n": {after}')
    _commit(world.lane, _bump_plugin(world, text), "bump")

    _stale(world, "plugin.json")


@pytest.mark.parametrize("edit", ["whitespace", "escape", "reorder", "escaped-version", "nan"])
def test_manifest_raw_byte_changes_are_stale(world, edit):
    _review(world)
    path = "plugin/p/.claude-plugin/plugin.json"
    files = _bump_plugin(world, PLUGIN.format(name="p", v="1.0.1"))
    text = files[path]
    text = {
        "whitespace": text.replace('"description": "d"', '"description":  "d"'),
        "escape": text.replace('"description": "d"', '"description": "\\u0064"'),
        "reorder": text.replace('  "description": "d",\n  "flag": true',
                                '  "flag": true,\n  "description": "d"'),
        "escaped-version": text.replace('"version": "1.0.1"', '"version": "1.0.\\u0031"'),
        "nan": text.replace('"flag": true', '"flag": NaN'),
    }[edit]
    files[path] = text
    _commit(world.lane, files, "raw")

    _stale(world, "plugin.json")


def test_manifest_duplicate_key_is_stale(world):
    _review(world)
    files = _bump_plugin(world, PLUGIN.format(name="p", v="1.0.1").replace(
        '"flag": true', '"flag": true,\n  "flag": false'))
    _commit(world.lane, files, "dupe")

    _stale(world, "plugin.json")


def test_nested_version_key_change_is_stale(world):
    _commit(world.lane, {"plugin/p/.claude-plugin/plugin.json": PLUGIN.format(
        name="p", v="1.0.0").replace('"flag": true', '"hooks": {"x": {"version": "1.0.0"}}')}, "n")
    _review(world)
    files = _bump_plugin(world, PLUGIN.format(name="p", v="1.0.1").replace(
        '"flag": true', '"hooks": {"x": {"version": "9.9.9"}}'))
    _commit(world.lane, files, "nested")

    _stale(world, "plugin.json")


@pytest.mark.parametrize("market", [
    MARKET.format(p="1.0.0", q="2.0.1"),           # another plugin's version
    MARKET.format(p="1.0.2", q="2.0.0"),           # not its plugin.json's new version
    MARKET.format(p="1.0.1", q="2.0.0").replace(   # reordered plugins list
        '{"name": "p", "source": "./plugin/p", "version": "1.0.1"},\n    '
        '{"name": "q", "source": "./plugin/q", "version": "2.0.0"}',
        '{"name": "q", "source": "./plugin/q", "version": "2.0.0"},\n    '
        '{"name": "p", "source": "./plugin/p", "version": "1.0.1"}'),
])
def test_marketplace_change_not_bound_to_the_bumped_plugin_is_stale(world, market):
    _review(world)
    files = _bump(world, "1.0.1")
    files[".claude-plugin/marketplace.json"] = market
    _commit(world.lane, files, "market")

    _stale(world, "marketplace.json")


@pytest.mark.parametrize("files", [
    {".crew/codemap/sub.md": CODEMAP.format(a="ccccccc", body="body line edited")},
    {".crew/codemap/sub.md": CODEMAP.format(a="ccccccc", body="body line\n\nre-anchored to "
                                                               "ccccccc (L-0522)")},
    {".crew/codemap/sub.md": CODEMAP.format(a="ccccccc", body="body line\nanchor: proj@ddddddd")},
    {".claude/rules/sub.md": RULES.format(d="1" * 16, a="aaaaaaa", extra="Run ./x first.\n")},
    {"docs/diagrams/flow.mmd": DIAGRAM.format(a="ccccccc").replace("a --> b", "a --> c")},
])
def test_anchored_artifact_changed_beyond_its_anchor_is_stale(world, files):
    _review(world)
    _commit(world.lane, files, "refresh plus more")

    _stale(world, review_delta.ANCHORED_BEYOND)


def test_rules_whose_source_map_changed_beyond_its_anchor_is_stale(world):
    """R5-4: the map's body change arrives through the integration base, so the
    map has no delta entry of its own; only the rules-source check stales."""
    _review(world)
    _main(world, {".crew/codemap/sub.md": CODEMAP.format(a="aaaaaaa", body="main edited body")})
    _catch_up(world)
    _commit(world.lane, {".claude/rules/sub.md": RULES.format(d="4" * 16, a="aaaaaaa",
                                                              extra="")}, "rules only")

    _stale(world, review_delta.ANCHORED_BEYOND, ".claude/rules/sub.md")


def test_diagram_anchor_line_suffix_append_is_stale(world):
    _review(world)
    _commit(world.lane, {"docs/diagrams/flow.mmd": DIAGRAM.format(a="ccccccc").replace(
        "@ccccccc\n", "@ccccccc run ./x\n")}, "append")

    _stale(world, review_delta.ANCHORED_BEYOND)


def test_diagram_generated_from_date_change_is_stale(world):
    _review(world)
    _commit(world.lane, {"docs/diagrams/gen.mmd": GENERATED.format(a="ccccccc",
                                                                   date="2026-10-03")}, "date")

    _stale(world, review_delta.ANCHORED_BEYOND)


def test_diagram_invalid_header_form_is_stale(world):
    bad = "%% anchor: proj@{a} extra\nflowchart LR\n  a --> b\n"
    _commit(world.lane, {"docs/diagrams/flow.mmd": bad.format(a="aaaaaaa")}, "odd header")
    _review(world)
    _commit(world.lane, {"docs/diagrams/flow.mmd": bad.format(a="ccccccc")}, "sha only")

    _stale(world, review_delta.ANCHORED_BEYOND)


@pytest.mark.parametrize("files", [
    {"docs/diagrams/gen.mmd": GENERATED.format(a="ccccccc", date="2026-10-01").replace(
        "proj@", "other@")},
    {"docs/diagrams/flow.mmd": DIAGRAM.format(a="ccccccc") + "%% anchor: proj@ddddddd\n"},
])
def test_diagram_repo_change_or_two_headers_is_stale(world, files):
    _review(world)
    _commit(world.lane, files, "diagram")

    _stale(world, review_delta.ANCHORED_BEYOND)


@pytest.mark.parametrize("rel", [".crew/codemap/x.py", ".claude/rules/x.json",
                                 "docs/diagrams/x.sh", "docs/diagrams-x/a.md",
                                 ".crew/codemapX/a.md", "plugin/crew/commands/CHANGELOG.md",
                                 "plugin/crew/hooks/hooks.json", ".Crew/codemap/a.md",
                                 "changelog.md", "plugin/crew/budgets.md"])
def test_non_allowlisted_or_look_alike_path_is_stale(world, rel):
    _review(world)
    _commit(world.lane, {rel: "anchor: proj@ccccccc\n"}, "look-alike")

    _stale(world, rel)


def test_crew_config_cannot_widen_the_allowlist(world):
    _write(world.lane, ".crew/config.json", '{"docs": {"diagramsDir": "plugin/crew/hooks"}}\n')
    git(world.lane, "add", "-f", ".crew/config.json")
    git(world.lane, "commit", "-qm", "config")
    _review(world)
    _commit(world.lane, {"plugin/crew/hooks/x.py": "anchor: proj@ccccccc\n"}, "x")

    _stale(world, "plugin/crew/hooks/x.py")


@pytest.mark.parametrize("change", ["delete", "rename", "mode", "binary"])
def test_exempt_path_deleted_renamed_mode_changed_or_binary_is_stale(world, change):
    _review(world)
    if change == "delete":
        git(world.lane, "rm", "-q", "CHANGELOG.md")
    elif change == "rename":
        git(world.lane, "mv", "TODO.md", "plugin/TODO.md")
    elif change == "mode":
        (world.lane / "CHANGELOG.md").chmod(0o755)
        git(world.lane, "update-index", "--chmod=+x", "CHANGELOG.md")
    else:
        _write(world.lane, "CHANGELOG.md", b"\x00\x01binary\x00")
        git(world.lane, "add", "CHANGELOG.md")
    git(world.lane, "commit", "-qm", change)

    _stale(world)


def test_excluded_file_added_before_review_is_stale(world):
    _write(world.lane, ".work/run.py", "print('not reviewed')\n")
    git(world.lane, "add", "-f", ".work/run.py")
    git(world.lane, "commit", "-qm", "force-added before review")
    _review(world)

    _stale(world, "excluded path changed: .work/run.py (receipt base -> reviewed head)")
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    _stale(world, ".work/run.py")


@pytest.mark.parametrize("how", ["committed", "staged"])
def test_excluded_only_change_stales_the_fast_path(world, how):
    _review(world)
    _write(world.lane, ".work/run.py", "print('not reviewed')\n")
    git(world.lane, "add", "-f", ".work/run.py")
    if how == "committed":
        git(world.lane, "commit", "-qm", "force-added after review")

    _stale(world, "excluded path changed: .work/run.py")


@pytest.mark.parametrize("files", [
    {".crew/metrics.md": "| row |\n"},
    {"graphify-out/cache.json": "{}\n"},
])
def test_excluded_paths_force_added_on_the_delta_path_are_stale(world, files):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    for rel, text in files.items():
        _write(world.lane, rel, text)
        git(world.lane, "add", "-f", rel)
    git(world.lane, "commit", "-qm", "excluded")

    _stale(world, "excluded path changed")


def test_non_excepted_graph_file_present_before_review_modified_after_is_stale(world):
    """R5-1: an existing, non-excepted file under graphify-out/ modified after
    review (status M), so only the whole-path exception list stales it."""
    _write(world.lane, "graphify-out/cache.json", "{}\n")
    git(world.lane, "add", "-f", "graphify-out/cache.json")
    git(world.lane, "commit", "-qm", "cache")
    _review(world)
    _write(world.lane, "graphify-out/cache.json", '{"x": 1}\n')
    git(world.lane, "commit", "-qam", "cache moved")

    _stale(world, "excluded path changed: graphify-out/cache.json")


@pytest.mark.parametrize("change", ["delete", "mode"])
def test_graph_file_deleted_or_made_executable_is_stale(world, change):
    _review(world)
    if change == "delete":
        git(world.lane, "rm", "-q", "graphify-out/graph.json")
    else:
        (world.lane / "graphify-out/graph.json").chmod(0o755)
        git(world.lane, "update-index", "--chmod=+x", "graphify-out/graph.json")
    git(world.lane, "commit", "-qm", change)

    _stale(world, "excluded path changed: graphify-out/graph.json")


def test_binary_graph_file_change_is_stale(world):
    _review(world)
    _write(world.lane, "graphify-out/graph.json", b"\x00\x01\x02binary graph\x00")
    git(world.lane, "commit", "-qam", "binary graph")

    _stale(world, "excluded path changed: graphify-out/graph.json")


@pytest.mark.parametrize("dirt", ["unstaged", "staged", "untracked"])
def test_dirty_checkout_after_a_catch_up_is_stale(world, dirt):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    if dirt == "untracked":
        _write(world.lane, "notes.txt", "scratch\n")
    else:
        _write(world.lane, "lib.py", "def lib():\n    return 5\n")
        if dirt == "staged":
            git(world.lane, "add", "lib.py")

    _stale(world, "not clean")


def test_committed_edit_restored_only_in_the_working_tree_is_stale(world):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    _commit(world.lane, {"app.py": "def app():\n    return 666  # unreviewed\n"}, "sneak")
    _write(world.lane, "app.py", "def app():\n    return 2  # the ticket's change\n")

    _stale(world)


@pytest.mark.parametrize("flag", ["--skip-worktree", "--assume-unchanged"])
def test_hidden_index_flag_edit_is_stale(world, flag):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    git(world.lane, "update-index", flag, "lib.py")
    _write(world.lane, "lib.py", "def lib():\n    return 77\n")
    assert git(world.lane, "status", "--porcelain") == ""

    _stale(world, "skip-worktree or assume-unchanged")


def test_submodule_gitlink_is_stale(world):
    sub = init_repo(world.repo.parent / "sub")
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    git(world.lane, "clone", "-q", str(sub), "vendor/sub")
    git(world.lane, "add", "vendor/sub")
    git(world.lane, "commit", "-qm", "gitlink")
    assert git(world.lane, "status", "--porcelain") == ""

    _stale(world, "gitlink")


def test_dirty_review_whose_edit_was_discarded_is_stale(world):
    """Reviewed with an uncommitted edit, the edit discarded, then a catch-up:
    every delta check alone would pass; only step 2 stales it."""
    _write(world.lane, "lib.py", "def lib():\n    return 'reviewed but never committed'\n")
    _review(world)
    git(world.lane, "checkout", "--", "lib.py")
    _main(world, {"TODO.md": "# TODO\n\n- main\n"})
    _catch_up(world)

    _stale(world, "does not rebuild the reviewed bundle")


def test_review_head_missing_or_not_an_ancestor_is_stale(world):
    _review(world)
    git(world.lane, "reset", "-q", "--hard", world.start)
    _commit(world.lane, {"app.py": "def app():\n    return 2  # the ticket's change\n"}, "redo")
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)

    _stale(world, "not an ancestor of HEAD")


def test_round_row_without_a_head_is_stale(world):
    _review(world)
    path = rl.ledger_path(str(world.lane), TICKET)
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    data["rounds"][-1]["head"] = None
    pathlib.Path(path).write_text(json.dumps(data), encoding="utf-8")

    _stale(world, "reviewed head")


@pytest.mark.parametrize("problem", ["no-train", "other-worktree"])
def test_no_train_entry_binding_the_ref_is_stale(world, problem):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    state_path = os.path.join(crew_train.train_dir(str(world.lane)), "state.json")
    if problem == "no-train":
        os.remove(state_path)
    else:
        data = json.loads(pathlib.Path(state_path).read_text(encoding="utf-8"))
        data["entries"][0]["worktree"] = str(world.repo)
        pathlib.Path(state_path).write_text(json.dumps(data), encoding="utf-8")

    _stale(world, "no train entry binds the integration ref")


def test_criss_cross_merge_bases_are_stale(world):
    _review(world)
    git(world.repo, "branch", "side", "main")
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    side = world.repo.parent / "side"
    git(world.repo, "worktree", "add", "-q", str(side), "side")
    _commit(side, {"TODO.md": "# TODO\n\n- side\n"}, "side")
    git(world.repo, "merge", "--no-edit", "-q", "side")
    git(side, "merge", "--no-edit", "-q", "main~1")
    git(world.lane, "merge", "--no-edit", "-q", "side")

    _stale(world)


def test_git_failing_inside_the_gate_reads_could_not_tell(world, tmp_path):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    fake = tmp_path / "fakebin"
    fake.mkdir()
    real = shutil.which("git")
    (fake / "git").write_text(
        f"#!/bin/sh\ncase \"$*\" in *merge-base*--all*) exit 128;; esac\nexec {real} \"$@\"\n",
        encoding="utf-8")
    (fake / "git").chmod(0o755)
    env = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ['PATH']}")
    done = subprocess.run([sys.executable, _LEDGER, "--root", str(world.lane), "--ticket",
                           TICKET, "--check-receipt"], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False, env=env)

    assert done.returncode == 1 and "could not tell" in done.stdout, done.stdout + done.stderr


def test_needs_replan_and_later_rounds_are_refused_before_the_gate(world):
    _review(world)
    ok, _number, _ = rl.reserve(str(world.lane), TICKET, "codex")
    assert ok
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)

    code, out = _check(world)

    assert code == 1 and "delta gate" not in out, out


# ------------------------------------- named controls for the sabotage step
# Each is the fixture where the named check is the ONLY one that can stale the
# receipt, so removing that check alone turns stale into an unsafe KEEP.

def test_manifest_bool_to_int_is_stale(world):
    _review(world)
    _commit(world.lane, _bump_plugin(world, PLUGIN.format(name="p", v="1.0.1").replace(
        '"flag": true', '"flag": 1')), "true -> 1")

    _stale(world, "plugin.json")


def test_marketplace_other_plugin_version_change_is_stale(world):
    _review(world)
    files = _bump(world, "1.0.1")
    files[".claude-plugin/marketplace.json"] = MARKET.format(p="1.0.1", q="2.0.1")
    _commit(world.lane, files, "q moved too")

    _stale(world, "marketplace.json")


def test_look_alike_dir_with_an_anchor_only_change_is_stale(tmp_path):
    world = _make_world(tmp_path, {".crew/codemapX/a.md": CODEMAP.format(a="aaaaaaa",
                                                                         body="x")})
    _review(world)
    _commit(world.lane, {".crew/codemapX/a.md": CODEMAP.format(a="ccccccc", body="x")}, "sha")

    _stale(world, ".crew/codemapX/a.md")


def test_non_md_file_under_codemap_with_anchor_only_change_is_stale(tmp_path):
    world = _make_world(tmp_path, {".crew/codemap/x.py": CODEMAP.format(a="aaaaaaa", body="x")})
    _review(world)
    _commit(world.lane, {".crew/codemap/x.py": CODEMAP.format(a="ccccccc", body="x")}, "sha")

    _stale(world, ".crew/codemap/x.py")


def test_code_map_body_edited_after_review_is_stale(world):
    _review(world)
    _commit(world.lane, {".crew/codemap/sub.md": CODEMAP.format(a="aaaaaaa",
                                                                body="body line edited")}, "b")

    _stale(world, review_delta.ANCHORED_BEYOND)


def test_exempt_path_deleted_is_stale(world):
    _review(world)
    git(world.lane, "rm", "-q", "CHANGELOG.md")
    git(world.lane, "commit", "-qm", "delete")

    _stale(world, "CHANGELOG.md")


def test_skip_worktree_edit_is_stale(world):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    git(world.lane, "update-index", "--skip-worktree", "lib.py")
    _write(world.lane, "lib.py", "def lib():\n    return 77\n")

    _stale(world, "skip-worktree or assume-unchanged")


def test_reviewed_gitlink_unchanged_since_is_still_stale(world):
    sub = init_repo(world.repo.parent / "sub")
    git(world.lane, "clone", "-q", str(sub), "vendor/sub")
    git(world.lane, "add", "vendor/sub")
    git(world.lane, "commit", "-qm", "gitlink, reviewed")
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)

    _stale(world, "gitlink")


def test_no_train_state_is_stale(world):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    os.remove(os.path.join(crew_train.train_dir(str(world.lane)), "state.json"))

    _stale(world, "no train entry binds the integration ref")


def test_untracked_file_after_a_catch_up_is_stale(world):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    _write(world.lane, "notes.txt", "scratch\n")

    _stale(world, "not clean")


# ------------------------------------------------------------ base pinning

def _pinned(world, base_sha):
    return rl.check_receipt(str(world.lane), TICKET, base_sha=base_sha)


def test_check_receipt_judges_the_passed_base_sha(world):
    _review(world)
    pin = _main(world, {"TODO.md": "# TODO\n\n- one\n"})
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)

    assert _pinned(world, None)[0] is True
    ok, message = _pinned(world, pin)

    assert ok is False and "lib.py" in message, message


@pytest.mark.parametrize("pin", ["abc", "f" * 40])
def test_invalid_base_sha_stales_the_fast_path(world, pin):
    _review(world)

    ok, message = _pinned(world, pin)

    assert ok is False and "base_sha" in message, message


@pytest.mark.parametrize("pin", ["abc", "f" * 40])
def test_invalid_base_sha_stales_the_delta_path(world, pin):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)

    ok, message = _pinned(world, pin)

    assert ok is False and "base_sha" in message, message


# ------------------------------------------------------- scanner and matcher

@pytest.mark.parametrize("prefix", ["é", "日本", "\U0001F600"])
def test_json_spans_are_raw_byte_offsets_past_multibyte_text(prefix):
    raw = ('{"description": "%s", "version": "1.2.3"}' % prefix).encode("utf-8")

    spans = review_delta._json_spans(raw)  # pylint: disable=protected-access

    start, end = spans[("version",)][0]
    assert raw[start:end] == b'"1.2.3"'


def test_a_byte_where_char_offsets_would_land_is_still_compared(world):
    """R5-2: a non-version byte at the offset a str-indexed span would
    displace to, changed, stales the receipt."""
    _commit(world.lane, {"plugin/p/.claude-plugin/plugin.json": PLUGIN.format(
        name="p", v="1.0.0").replace('"description": "d"', '"description": "日本日本"')}, "mb")
    _review(world)
    files = _bump_plugin(world, PLUGIN.format(name="p", v="1.0.1").replace(
        '"description": "d"', '"description": "日本日X"'))
    _commit(world.lane, files, "bump plus a multibyte edit")

    _stale(world, "plugin.json")


def test_matcher_is_case_sensitive(monkeypatch):
    monkeypatch.setattr(os.path, "normcase", lambda p: p.lower())

    assert review_delta._match(".crew/codemap/a.md", ".crew/codemap/**/*.md")  # pylint: disable=protected-access
    assert not review_delta._match(".Crew/codemap/a.md", ".crew/codemap/**/*.md")  # pylint: disable=protected-access
    assert not review_delta._match("changelog.md", "CHANGELOG.md")  # pylint: disable=protected-access


def test_exempt_is_a_subset_of_release_bookkeeping_and_refresh_dirs():
    bookkeeping = crew_refresh_check.RELEASE_BOOKKEEPING
    refresh_roots = (".crew/codemap", ".claude/rules", "docs/diagrams")
    for pattern in review_delta.EXEMPT_PROSE + review_delta.EXEMPT_MANIFEST:
        assert pattern in bookkeeping or (pattern.endswith(".claude-plugin/plugin.json")
                                          and "**/.claude-plugin/plugin.json" in bookkeeping), pattern
    for patterns in review_delta.EXEMPT_ANCHORED.values():
        for pattern in patterns:
            assert pattern.startswith(refresh_roots), pattern


def test_bundle_bytes_unchanged_by_the_delta_gate(world):
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    before = review_patch.compute(str(world.lane), world.start)

    _kept(world)

    after = review_patch.compute(str(world.lane), world.start)
    assert before[1] == after[1] and before[0]["bundle_sha256"] == after[0]["bundle_sha256"]


# ---------------------------------------------------------------- preflight

def _preflight(world, monkeypatch, gate):
    import argparse  # pylint: disable=import-outside-toplevel
    import review_gate  # pylint: disable=import-outside-toplevel
    import review_run  # pylint: disable=import-outside-toplevel
    monkeypatch.setattr(review_gate, "gate_state", lambda root: (gate, "fixture"))
    args = argparse.Namespace(root=str(world.lane), ticket=TICKET, provider="codex",
                              allow_unverified=False)
    return review_run, args


def test_preflight_names_a_delta_kept_receipt(world, monkeypatch, capsys):
    import review_gate  # pylint: disable=import-outside-toplevel
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    review_run, args = _preflight(world, monkeypatch, review_gate.VERIFIED)

    code = review_run.preflight(args)

    out = capsys.readouterr().out
    assert code == review_run.EXIT_CLEAN, out
    assert "kept by the delta gate" in out and "nothing in the bundle changed" not in out, out


def test_preflight_delta_kept_on_an_unverified_tree_does_not_short_circuit(world, monkeypatch,
                                                                           capsys):
    import review_gate  # pylint: disable=import-outside-toplevel
    _review(world)
    _main(world, {"lib.py": "def lib():\n    return 2\n"})
    _catch_up(world)
    review_run, args = _preflight(world, monkeypatch, review_gate.UNVERIFIED)

    code = review_run.preflight(args)

    captured = capsys.readouterr()
    assert code != review_run.EXIT_CLEAN, captured.out
    assert "ALREADY_CLEAN=1" not in captured.out and "CLEAN from" not in captured.out


def test_preflight_fast_path_clean_unchanged(world, monkeypatch, capsys):
    import review_gate  # pylint: disable=import-outside-toplevel
    manifest = _review(world)
    review_run, args = _preflight(world, monkeypatch, review_gate.UNVERIFIED)

    code = review_run.preflight(args)

    out = capsys.readouterr().out
    assert code == review_run.EXIT_CLEAN
    assert out.startswith(f"review: CLEAN from the existing receipt (receipt current: round 1 "
                          f"clean, bundle {str(manifest['bundle_sha256'])[:12]}) - nothing in the "
                          "bundle changed since that clean round, so no round was spent"), out
