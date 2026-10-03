"""crew_trailers.py (T-0066): the `git.forbiddenTrailers` list, the textual
command check the scope guard runs, and `/crew:done`'s report.

Every behaviour here has a mutation in sabotage_trailers.py that turns its
test red. Fixtures live in `tmp_path`; the global layer is always an explicit
`tmp_path` file (conftest's autouse fixture already points the default away
from the real `~/.claude`).
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_trailers
import scope_base
from review_fixtures import git, init_repo

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(CREW, "hooks", "scripts", "crew_trailers.py")
TOKENS = ("Co-Authored-By",)


def _repo_layer(root, value):
    (root / ".crew").mkdir(exist_ok=True)
    (root / ".crew" / "config.json").write_text(
        value if isinstance(value, str) else json.dumps(value), encoding="utf-8")


def _global_layer(tmp_path, value):
    path = tmp_path / "global.json"
    path.write_text(value if isinstance(value, str) else json.dumps(value),
                    encoding="utf-8")
    return str(path)


# --- forbidden(): the union of both layers -------------------------------------

def test_forbidden_is_the_union_of_both_layers(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _repo_layer(root, {"git": {"forbiddenTrailers": ["X-Foo"]}})
    glob = _global_layer(tmp_path, {"git": {"forbiddenTrailers": ["Co-Authored-By"]}})

    assert crew_trailers.forbidden(str(root), glob) == (("X-Foo", "Co-Authored-By"), None)


def test_a_repo_empty_list_does_not_disarm_the_global_list(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _repo_layer(root, {"git": {"forbiddenTrailers": []}})
    glob = _global_layer(tmp_path, {"git": {"forbiddenTrailers": ["Co-Authored-By"]}})

    assert crew_trailers.forbidden(str(root), glob) == (("Co-Authored-By",), None)


def test_forbidden_is_empty_when_both_layers_are_silent(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _repo_layer(root, {"scope": {"mode": "off"}})

    assert crew_trailers.forbidden(str(root), str(tmp_path / "absent.json")) == ((), None)


def test_forbidden_deduplicates_case_insensitively(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _repo_layer(root, {"git": {"forbiddenTrailers": ["co-authored-by"]}})
    glob = _global_layer(tmp_path, {"git": {"forbiddenTrailers": ["Co-Authored-By"]}})

    assert crew_trailers.forbidden(str(root), glob) == (("co-authored-by",), None)


@pytest.mark.parametrize("where", ["repo-json", "global-json", "repo-directory"])
def test_a_corrupt_layer_is_unknown_not_empty(tmp_path, where):
    root = tmp_path / "r"
    root.mkdir()
    glob = str(tmp_path / "absent.json")
    if where == "repo-json":
        _repo_layer(root, "{not json")
    elif where == "global-json":
        glob = _global_layer(tmp_path, "{not json")
    else:
        (root / ".crew" / "config.json").mkdir(parents=True)

    tokens, unknown = crew_trailers.forbidden(str(root), glob)

    assert tokens == () and unknown and "corrupt" in unknown


@pytest.mark.parametrize("git_block", [
    {"forbiddenTrailers": "Co-Authored-By"},
    {"forbiddenTrailers": [42]},
    {"forbiddenTrailers": ["Co Authored"]},
    {"forbiddenTrailers": ["Co-Authored-By:"]},
    None,
], ids=["string", "number", "space", "colon", "git-null"])
def test_a_malformed_value_is_unknown(tmp_path, git_block):
    root = tmp_path / "r"
    root.mkdir()
    glob = _global_layer(tmp_path, {"git": git_block})

    tokens, unknown = crew_trailers.forbidden(str(root), glob)

    assert tokens == () and unknown and "global.json" in unknown


# --- commit_refusal(): one shell command ----------------------------------------

BLOCKS = {
    "commit-m": 'git commit -m "fix: x" -m "Co-Authored-By: A <a@b>"',
    "second-m": 'git commit -m "fix" -m "body" -m "Co-Authored-By: A <a@b>"',
    "heredoc-stdin": ('git commit -F - <<\'EOF\'\nfix: x\n\nCo-Authored-By: A <a@b>\nEOF'),
    "trailer-equals": 'git commit -m fix --trailer "Co-Authored-By=A <a@b>"',
    "trailer-lowercase": 'git commit -m fix --trailer co-authored-by:A',
    "git-C": 'git -C sub commit -m "x\n\nCo-Authored-By: A"',
    "git-c": 'git -c user.name=x commit -m "x\n\nCo-Authored-By: A"',
    "commit-tree": 'git commit-tree HEAD^{tree} -m "Co-Authored-By: A"',
    "merge-m": 'git merge feature -m "Merge\n\nCo-Authored-By: A"',
    "gh-pr-merge": 'gh pr merge 12 --merge --body "Co-Authored-By: A"',
    "chained": 'cd sub && git add -A && git commit -m "Co-Authored-By: A"',
    "continuation": 'git \\\ncommit -m "Co-Authored-By: A"',
    "git-exe": 'git.exe commit -m "Co-Authored-By: A"',
}

ALLOWS = {
    "no-trailer": 'git commit -m "fix: x"',
    "log-grep": "git log --grep=Co-Authored-By",
    "grep": "grep -i co-authored-by file.txt",
    "echo": 'echo "Co-Authored-By: x"',
    "prose": 'git commit -m "docs: no Co-Authored-By trailers in this repo"',
    "gh-pr-create": 'gh pr create --title t --body "Co-Authored-By: A"',
    "written-then-committed": "cat > m.txt <<'EOF'\nfix: x\nEOF\ngit commit -F m.txt",
    "status": "git status",
}


@pytest.mark.parametrize("command", BLOCKS.values(), ids=BLOCKS.keys())
def test_refusal_blocks(tmp_path, command):
    reason = crew_trailers.commit_refusal(command, TOKENS, str(tmp_path))

    assert reason and "git.forbiddenTrailers" in reason


@pytest.mark.parametrize("command", ALLOWS.values(), ids=ALLOWS.keys())
def test_refusal_allows(tmp_path, command):
    assert crew_trailers.commit_refusal(command, TOKENS, str(tmp_path)) is None


def test_refusal_reads_a_literal_message_file(tmp_path):
    (tmp_path / "msg.txt").write_text("fix: x\n\nCo-Authored-By: A <a@b>\n", encoding="utf-8")

    reason = crew_trailers.commit_refusal("git commit -F msg.txt", TOKENS, str(tmp_path))

    assert reason and "msg.txt" in reason and "Co-Authored-By" in reason


def test_refusal_reads_a_message_file_under_git_C(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "msg.txt").write_text("x\n\nCo-Authored-By: A\n", encoding="utf-8")

    reason = crew_trailers.commit_refusal("git -C sub commit --file=msg.txt", TOKENS,
                                          str(tmp_path))

    assert reason and "msg.txt" in reason


def test_refusal_allows_a_clean_message_file(tmp_path):
    (tmp_path / "msg.txt").write_text("fix: x\n", encoding="utf-8")

    assert crew_trailers.commit_refusal("git commit -F msg.txt", TOKENS, str(tmp_path)) is None


@pytest.mark.parametrize("command", ['git commit -F "$f"', "git commit -F %TEMP%\\m.txt",
                                     "git commit -F `mktemp`"], ids=["dollar", "percent", "tick"])
def test_refusal_cannot_tell_a_variable_message_file(tmp_path, command):
    reason = crew_trailers.commit_refusal(command, TOKENS, str(tmp_path))

    assert reason and "could not tell" in reason


def test_refusal_cannot_tell_a_missing_message_file(tmp_path):
    reason = crew_trailers.commit_refusal("git commit -F gone.txt", TOKENS, str(tmp_path))

    assert reason and "could not tell" in reason


def test_refusal_with_no_tokens_is_none(tmp_path):
    assert crew_trailers.commit_refusal(BLOCKS["commit-m"], (), str(tmp_path)) is None


def test_refusal_when_unknown_blocks_commits_only(tmp_path):
    why = "global.json is unreadable"

    assert "git.forbiddenTrailers" in crew_trailers.commit_refusal(
        'git commit -m "fix"', (), str(tmp_path), unknown=why)
    assert crew_trailers.commit_refusal("git status", (), str(tmp_path), unknown=why) is None


# --- --check: /crew:done's report -----------------------------------------------

def _ticket_repo(tmp_path, messages, config=None):
    root = init_repo(tmp_path / "r")
    (root / ".gitignore").write_text(".crew/\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "ignore crew")
    if config is not None:
        _repo_layer(root, config)
    scope_base.record(str(root), "T-1")
    for i, args in enumerate(messages):
        (root / f"f{i}.txt").write_text(str(i), encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", *args)
    return root


def _check(root, global_path):
    done = subprocess.run(
        [sys.executable, SCRIPT, "--check", "--root", str(root), "--ticket", "T-1",
         "--global-path", global_path],
        capture_output=True, text=True, check=False, timeout=60)
    return done.returncode, done.stdout.splitlines()


def test_check_reports_clean(tmp_path):
    glob = _global_layer(tmp_path, {"git": {"forbiddenTrailers": ["Co-Authored-By"]}})
    root = _ticket_repo(tmp_path, [["-m", "one"], ["-m", "two"]])

    assert _check(root, glob) == (0, ["trailers: clean (2 commits)"])


def test_check_reports_every_offending_commit(tmp_path):
    glob = _global_layer(tmp_path, {"git": {"forbiddenTrailers": ["Co-Authored-By"]}})
    root = _ticket_repo(tmp_path, [
        ["-m", "one", "-m", "Co-Authored-By: A <a@b>"],
        ["-m", "two"],
        ["-m", "three", "--trailer", "co-authored-by: B <b@c>"],
    ])
    shas = git(root, "log", "--format=%h", "--abbrev=7", "-3").split()

    code, lines = _check(root, glob)

    assert code == 1
    assert lines == [f"trailers: FINDING {shas[0]} Co-Authored-By",
                     f"trailers: FINDING {shas[2]} Co-Authored-By"]


def test_check_reports_unknown_without_a_base(tmp_path):
    glob = _global_layer(tmp_path, {"git": {"forbiddenTrailers": ["Co-Authored-By"]}})
    root = init_repo(tmp_path / "r")

    code, lines = _check(root, glob)

    assert code == 2 and len(lines) == 1 and lines[0].startswith("trailers: unknown - ")


def test_check_reports_unknown_for_a_corrupt_layer(tmp_path):
    glob = _global_layer(tmp_path, "{not json")
    root = _ticket_repo(tmp_path, [["-m", "one", "-m", "Co-Authored-By: A"]])

    code, lines = _check(root, glob)

    assert code == 2 and lines[0].startswith("trailers: unknown - ") and "corrupt" in lines[0]


def test_check_with_an_empty_list_reports_clean_and_says_off(tmp_path):
    root = _ticket_repo(tmp_path, [["-m", "one", "-m", "Co-Authored-By: A"]])

    assert _check(root, str(tmp_path / "absent.json")) == (
        0, ["trailers: clean (git.forbiddenTrailers is empty - nothing forbidden)"])


# --- the documents that carry the rule ------------------------------------------

def _read(*parts):
    with open(os.path.join(CREW, *parts), encoding="utf-8") as handle:
        return handle.read()


def test_practices_md_does_not_claim_a_required_trailer():
    text = _read("skills", "crew-best-practices", "references", "practices.md")

    assert "adds `Co-Authored-By`" not in text
    assert "owner's own instructions" in text and "git.forbiddenTrailers" in text


def test_implement_md_forbids_attribution_in_dispatch_prompts():
    text = _read("commands", "implement.md")

    assert "no attribution or trailer instruction" in text
    assert "git.forbiddenTrailers" in text


def test_done_md_reports_trailers_without_refusing():
    text = _read("commands", "done.md")

    assert "crew_trailers.py --check" in text
    assert "this report never refuses done" in text and "never rewrites" in text
    assert "All four checks" in text
