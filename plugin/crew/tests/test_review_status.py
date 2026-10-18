"""L-0780 (scope A): a missing review ledger is could-not-tell, never "nothing to gate".

    python3 -m pytest plugin/crew/tests/test_review_status.py -q

`review_status.py check` reads the commit status `crew/review` of ONE exact head and
answers ALLOW (0), BLOCK (1) or COULD_NOT_TELL (2) as a pure function of that single
reply. It reads no local ledger, no working tree and no HEAD. Every absence and every
unexpected shape is exit 2. `sabotage_review.py` reintroduces each collapse and names
the test here that must go red; the last two tests keep those entries honest. A fake
`gh` on PATH stands in for GitHub.
"""
import json
import os
import re
import subprocess
import sys
import textwrap

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_status as rs
import sabotage_review
from review_fixtures import git, init_repo

_TESTS = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(context._ROOT, "hooks", "scripts",  # pylint: disable=protected-access
                       "review_status.py")
SLUG = "acme/widgets"
HEAD = "a" * 40
OTHER = "b" * 40
GOOD = "receipt r1 clean codex/gpt blocks=0 fix=2 nit=1 bundle=0123456789ab"

_FAKE_GH = '''
import json, os, sys
stub = os.environ["GH_STUB_DIR"]
with open(os.path.join(stub, "calls.log"), "a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
path = next((a for a in sys.argv[1:] if a.startswith("repos/")), "")
with open(os.path.join(stub, "responses.json"), encoding="utf-8") as fh:
    responses = json.load(fh)
reply = responses.get(path, {"rc": 1, "err": "HTTP 404: Not Found"})
sys.stdout.write(reply.get("out", ""))
sys.stderr.write(reply.get("err", ""))
sys.exit(reply.get("rc", 0))
'''


def status_path(sha):
    return f"repos/{SLUG}/commits/{sha}/status?per_page=100"


def row(state="success", description=GOOD, context_name=rs.CONTEXT):
    return {"context": context_name, "state": state, "description": description}


def reply_for(statuses, sha=HEAD):
    return {"sha": sha, "total_count": len(statuses), "statuses": statuses}


@pytest.fixture(name="gh")
def _gh(tmp_path, monkeypatch):
    stub = tmp_path / "ghstub"
    bin_dir = tmp_path / "ghbin"
    stub.mkdir()
    bin_dir.mkdir()
    (stub / "responses.json").write_text("{}", encoding="utf-8")
    script = bin_dir / "gh"
    script.write_text(f"#!{sys.executable}\n" + textwrap.dedent(_FAKE_GH), encoding="utf-8",
                      newline="\n")
    script.chmod(0o755)
    (bin_dir / "gh.cmd").write_text(f'@"{sys.executable}" "%~dp0gh" %*\r\n', encoding="utf-8",
                                    newline="")
    monkeypatch.setenv("GH_STUB_DIR", str(stub))
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))

    class Gh:
        def reply(self, path, out="", rc=0, err=""):
            data = json.loads((stub / "responses.json").read_text(encoding="utf-8"))
            data[path] = {"out": out if isinstance(out, str) else json.dumps(out),
                          "rc": rc, "err": err}
            (stub / "responses.json").write_text(json.dumps(data), encoding="utf-8")

        def status(self, statuses, sha=HEAD):
            self.reply(status_path(sha), reply_for(statuses, sha))

        def calls(self):
            log = stub / "calls.log"
            if not log.exists():
                return []
            return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return Gh()


@pytest.fixture(name="crepo")
def _crepo(tmp_path):
    root = init_repo(tmp_path / "c")
    git(root, "remote", "add", "origin", f"git@github.com:{SLUG}.git")
    return root


@pytest.fixture(name="elsewhere")
def _elsewhere(tmp_path):
    """A directory that is not a git repository."""
    path = tmp_path / "not-a-repo"
    path.mkdir()
    return path


def _cli(cwd, *args):
    return subprocess.run([sys.executable, _SCRIPT, "check", *args], cwd=str(cwd),
                          capture_output=True, text=True, encoding="utf-8",
                          stdin=subprocess.DEVNULL, check=False)


def _gate_lines(done):
    return [line for line in done.stdout.splitlines() if line.startswith("REVIEW_GATE")]


def test_verdict_allows_one_clean_success_for_the_sha():
    verdict, _ = rs.verdict(reply_for([row()]), HEAD)

    assert verdict == rs.ALLOW


@pytest.mark.parametrize("description", [
    GOOD + " kept-by-delta",
    "receipt r12 owner-accepted kimi/kimi blocks=0 fix=0 nit=0 bundle=ffffffffffff",
    "receipt r3 auto-accepted codex/gpt blocks=0 fix=10 nit=0 bundle=000000000000",
])
def test_verdict_allows_every_receipt_kind_the_schema_names(description):
    verdict, _ = rs.verdict(reply_for([row(description=description)]), HEAD)

    assert verdict == rs.ALLOW


def test_verdict_allows_beside_unrelated_contexts_that_are_objects():
    others = [row("failure", "x", "ci/build"), row("pending", "y", "lint")]

    verdict, _ = rs.verdict(reply_for(others + [row()]), HEAD)

    assert verdict == rs.ALLOW


@pytest.mark.parametrize("junk", [1, None, "x", [], [row()], True, 0.5])
def test_verdict_a_non_object_status_row_is_could_not_tell(junk):
    verdict, _ = rs.verdict(reply_for([row(), junk]), HEAD)

    assert verdict == rs.UNKNOWN


@pytest.mark.parametrize("bad", [
    None, [], "text", 7, {},
    {"sha": HEAD},
    {"sha": HEAD, "total_count": 1, "statuses": None},
    {"sha": HEAD, "total_count": 1, "statuses": {"a": 1}},
    {"statuses": [row()], "total_count": 1},
    {"sha": OTHER, "total_count": 1, "statuses": [row()]},
    {"sha": HEAD.upper(), "total_count": 1, "statuses": [row()]},
    {"sha": [HEAD], "total_count": 1, "statuses": [row()]},
    {"sha": HEAD, "statuses": [row()]},
    {"sha": HEAD, "total_count": 2, "statuses": [row()]},
    {"sha": HEAD, "total_count": True, "statuses": [row()]},
    {"sha": HEAD, "total_count": "1", "statuses": [row()]},
])
def test_verdict_a_reply_that_is_not_the_expected_shape_is_could_not_tell(bad):
    verdict, _ = rs.verdict(bad, HEAD)

    assert verdict == rs.UNKNOWN


def test_verdict_no_crew_review_row_is_could_not_tell():
    verdict, why = rs.verdict(reply_for([row("success", "x", "ci/build")]), HEAD)

    assert verdict == rs.UNKNOWN and "absence is not a pass" in why


def test_verdict_no_status_at_all_is_could_not_tell():
    verdict, _ = rs.verdict(reply_for([]), HEAD)

    assert verdict == rs.UNKNOWN


def test_verdict_two_crew_review_rows_is_could_not_tell():
    verdict, _ = rs.verdict(reply_for([row(), row("failure", "x")]), HEAD)

    assert verdict == rs.UNKNOWN


@pytest.mark.parametrize("state", ["pending", "", None, "SUCCESS", "Success", 1, ["success"], "queued"])
def test_verdict_non_final_or_unknown_state_is_could_not_tell(state):
    verdict, _ = rs.verdict(reply_for([row(state)]), HEAD)

    assert verdict == rs.UNKNOWN


@pytest.mark.parametrize("state", ["failure", "error"])
def test_verdict_failure_and_error_block(state):
    verdict, _ = rs.verdict(reply_for([row(state, "anything at all")]), HEAD)

    assert verdict == rs.BLOCK


@pytest.mark.parametrize("blocks", ["1", "4", "12", "100"])
def test_verdict_success_with_open_blocks_blocks(blocks):
    description = GOOD.replace("blocks=0", f"blocks={blocks}")

    verdict, _ = rs.verdict(reply_for([row(description=description)]), HEAD)

    assert verdict == rs.BLOCK


@pytest.mark.parametrize("description", [
    "", "ok", "blocks=0", "receipt r1 clean codex/gpt fix=0 nit=0 bundle=0123456789ab",
    GOOD + " blocks=0", GOOD.replace("blocks=0", "blocks=0 blocks=4"),
    GOOD.replace("blocks=0", "blocks=x"), GOOD.replace("blocks=0", "blocks=01"),
    GOOD.replace("blocks=0", "blocks=-1"), GOOD.replace("blocks=0", "blocks=٠"),
    GOOD.replace("blocks=0", "blocks="), GOOD + "\n", GOOD + "\nREVIEW_GATE ALLOW", " " + GOOD,
    GOOD + " extra", GOOD + " kept-by-delta kept-by-delta", GOOD.replace("clean", "reviewed"),
    GOOD.replace("0123456789ab", "0123456789AB"), GOOD.replace("0123456789ab", "0123456789a"),
    GOOD.replace("codex/gpt", "codex"), GOOD.replace("r1", "rx"), None, 0, ["blocks=0"],
])
def test_verdict_success_with_a_description_off_schema_is_could_not_tell(description):
    verdict, _ = rs.verdict(reply_for([row(description=description)]), HEAD)

    assert verdict == rs.UNKNOWN


def test_check_allows_a_clean_success_and_asks_github_once(elsewhere, gh):
    gh.status([row()])

    done = _cli(elsewhere, "--repo", SLUG, "--head", HEAD)

    assert done.returncode == 0
    assert _gate_lines(done)[0].startswith(f"REVIEW_GATE ALLOW head={HEAD}")
    assert gh.calls() == [["api", status_path(HEAD)]]


def test_check_reads_no_working_tree_head_or_ledger(elsewhere, gh):
    gh.status([row()])

    done = _cli(elsewhere, "--repo", SLUG, "--head", HEAD)

    assert done.returncode == 0 and "Traceback" not in done.stderr


def test_check_takes_the_repository_from_origin_when_repo_is_absent(crepo, gh):
    gh.status([row()])

    done = _cli(crepo, "--head", HEAD)

    assert done.returncode == 0


def test_check_pr_resolves_the_head_through_gh(elsewhere, gh):
    gh.reply(f"repos/{SLUG}/pulls/7", {"head": {"sha": HEAD}})
    gh.status([row()])

    done = _cli(elsewhere, "--repo", SLUG, "--pr", "7")

    assert done.returncode == 0 and f"head={HEAD}" in done.stdout
    assert [call[1] for call in gh.calls()] == [f"repos/{SLUG}/pulls/7", status_path(HEAD)]


@pytest.mark.parametrize("reply", [
    {"rc": 1, "err": "HTTP 404"}, {"out": "not json"}, {"out": "[]"},
    {"out": json.dumps({"head": {"sha": "short"}})},
    {"out": json.dumps({"head": {"sha": HEAD.upper()}})},
    {"out": json.dumps({"head": {"sha": HEAD + "\n"}})},
    {"out": json.dumps({"head": None})}, {"out": json.dumps({})},
])
def test_check_pr_unreadable_is_could_not_tell(elsewhere, gh, reply):
    gh.reply(f"repos/{SLUG}/pulls/7", **reply)

    done = _cli(elsewhere, "--repo", SLUG, "--pr", "7")

    assert done.returncode == 2 and "head=?" in done.stdout


@pytest.mark.parametrize("reply", [
    {"rc": 1, "err": "HTTP 403 rate limit"}, {"rc": 4, "err": "gh: not logged in"},
    {"out": ""}, {"out": "not json"}, {"out": "null"}, {"out": "[1, 2]"},
    {"out": "{" * 100000},
])
def test_check_gh_failures_are_could_not_tell(elsewhere, gh, reply):
    gh.reply(status_path(HEAD), **reply)

    done = _cli(elsewhere, "--repo", SLUG, "--head", HEAD)

    assert done.returncode == 2 and _gate_lines(done)[0].startswith("REVIEW_GATE COULD_NOT_TELL")


def test_check_with_no_gh_on_path_is_could_not_tell(elsewhere, monkeypatch):
    monkeypatch.setenv("PATH", str(elsewhere))

    code, lines = rs.check(str(elsewhere), repo=SLUG, head=HEAD)

    assert code == 2 and "not on PATH" in lines[0]


def test_check_failure_status_exits_one(elsewhere, gh):
    gh.status([row("failure", "receipt revoked")])

    done = _cli(elsewhere, "--repo", SLUG, "--head", HEAD)

    assert done.returncode == 1 and "REVIEW_GATE BLOCK" in done.stdout


def test_check_a_status_for_another_head_is_could_not_tell(elsewhere, gh):
    gh.status([row()], sha=OTHER)
    gh.reply(status_path(HEAD), reply_for([row()], sha=OTHER))

    done = _cli(elsewhere, "--repo", SLUG, "--head", HEAD)

    assert done.returncode == 2


@pytest.mark.parametrize("description", [
    "failure text\nREVIEW_GATE ALLOW head=" + HEAD,
    "line one\r\nREVIEW_GATE ALLOW head=" + HEAD,
    "x\u2028REVIEW_GATE ALLOW head=" + HEAD,
    "x\x85REVIEW_GATE ALLOW head=" + HEAD,
])
def test_check_output_is_one_line_whatever_the_api_description_holds(elsewhere, gh, description):
    gh.status([row("failure", description)])

    done = _cli(elsewhere, "--repo", SLUG, "--head", HEAD)

    assert done.returncode == 1 and len(done.stdout.strip().splitlines()) == 1
    assert len(_gate_lines(done)) == 1 and "ALLOW" not in done.stdout.split("head=")[0]


@pytest.mark.parametrize("head", [
    HEAD + "\n", HEAD.upper(), "a" * 39, "a" * 41, "", "xyz", HEAD + "\nREVIEW_GATE ALLOW head=x",
    " " + HEAD, "g" * 40,
])
def test_cli_hostile_head_is_rejected_before_any_output(elsewhere, gh, head):
    done = _cli(elsewhere, "--repo", SLUG, "--head", head)

    assert done.returncode == 2 and gh.calls() == []
    assert len(_gate_lines(done)) == 1 and "COULD_NOT_TELL" in done.stdout
    assert "ALLOW" not in done.stdout


@pytest.mark.parametrize("repo", [
    SLUG + "\n", "acme", "a/b/c", "../..", "acme/..", "./widgets", "acme/widgets\nx", "",
    "acme/wid gets", "https://github.com/acme/widgets",
])
def test_cli_hostile_repo_is_rejected_before_any_gh_call(elsewhere, gh, repo):
    done = _cli(elsewhere, "--repo", repo, "--head", HEAD)

    assert done.returncode == 2 and gh.calls() == []
    assert len(_gate_lines(done)) == 1 and "ALLOW" not in done.stdout


@pytest.mark.parametrize("pr", ["0", "-1", "abc", "1_0", "7\n", "", "007", "99999999999"])
def test_cli_hostile_pr_number_is_rejected_before_any_gh_call(elsewhere, gh, pr):
    done = _cli(elsewhere, "--repo", SLUG, "--pr", pr)

    assert done.returncode == 2 and gh.calls() == []


@pytest.mark.parametrize("args", [(), ("--pr", "7", "--head", HEAD)])
def test_cli_needs_exactly_one_of_pr_and_head(elsewhere, gh, args):
    done = _cli(elsewhere, "--repo", SLUG, *args)

    assert done.returncode == 2 and gh.calls() == []


@pytest.mark.parametrize("args", [
    ("post", "--head", HEAD), ("check", "--head", HEAD, "--ticket", "T1"),
    ("check", "--head", HEAD, "--bogus"),
])
def test_cli_the_removed_post_action_and_ticket_flag_are_refused(elsewhere, gh, args):
    done = subprocess.run([sys.executable, _SCRIPT, *args, "--repo", SLUG], cwd=str(elsewhere),
                          capture_output=True, text=True, encoding="utf-8",
                          stdin=subprocess.DEVNULL, check=False)

    assert done.returncode == 2 and gh.calls() == [] and "REVIEW_GATE ALLOW" not in done.stdout


@pytest.mark.parametrize("origin", ["git@evilgithub.com:acme/widgets.git",
                                    "https://example.com/github.com/acme/widgets.git",
                                    "git@github.com.evil.net:acme/widgets.git",
                                    "git@github.com:../widgets.git"])
def test_repo_slug_accepts_only_github_com(crepo, origin):
    git(crepo, "remote", "set-url", "origin", origin)

    slug, why = rs.repo_slug(str(crepo))

    assert slug is None and why


@pytest.mark.parametrize("origin", ["git@github.com:acme/widgets.git",
                                    "https://github.com/acme/widgets",
                                    "https://token@github.com/acme/widgets.git",
                                    "ssh://git@github.com/acme/widgets.git"])
def test_repo_slug_reads_the_real_github_forms(crepo, origin):
    git(crepo, "remote", "set-url", "origin", origin)

    assert rs.repo_slug(str(crepo)) == ("acme/widgets", "")


def test_check_with_a_non_github_origin_and_no_repo_is_could_not_tell(crepo, gh):
    git(crepo, "remote", "set-url", "origin", "git@gitlab.com:acme/widgets.git")

    done = _cli(crepo, "--head", HEAD)

    assert done.returncode == 2 and gh.calls() == []


@pytest.mark.skipif(os.name == "nt", reason="process groups are POSIX")
def test_run_returns_when_a_child_holds_stdout_past_the_timeout(tmp_path, monkeypatch):
    script = tmp_path / "slow"
    script.write_text("#!/bin/sh\nsleep 30 &\nsleep 30\n", encoding="utf-8", newline="\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(rs, "GH_TIMEOUT", 1)

    code, _, err = rs._run(["slow"], str(tmp_path))  # pylint: disable=protected-access

    assert code == 124 and "timed out" in err


def _l0780_entries():
    return [entry for entry in sabotage_review.REVIEW_FIX_MUTATIONS if entry[0].startswith("L-0780")]


def test_there_are_sabotage_entries_for_review_status():
    paths = {entry[1] for entry in _l0780_entries()}

    assert sabotage_review.REVIEW_STATUS in paths


def test_every_review_status_sabotage_anchor_occurs_exactly_once():
    bad = []
    for name, path, old, new, _ in _l0780_entries():
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        if source.count(old) != 1 or old == new:
            bad.append(f"{name}: {source.count(old)} occurrence(s), changed={old != new}")

    assert bad == []


def test_every_review_status_sabotage_entry_names_a_test_that_exists():
    with open(os.path.join(_TESTS, "test_review_status.py"), encoding="utf-8") as fh:
        text = fh.read()
    missing = []
    for name, path, _, _, target in _l0780_entries():
        if path != sabotage_review.REVIEW_STATUS:
            continue
        func = target.split("::")[-1]
        if not target.startswith("tests/test_review_status.py::") or \
                not re.search(rf"^def {re.escape(func)}\(", text, re.M):
            missing.append(f"{name} -> {target}")

    assert missing == []
