"""L-0780: a missing review ledger is could-not-tell, never "nothing to gate".

    python3 -m pytest plugin/crew/tests/test_review_status.py -q

`review_status.py post` publishes an accepted receipt as the commit status
`crew/review` on the exact head sha; `check` answers ALLOW (0), BLOCK (1) or
COULD_NOT_TELL (2) from the local ledger when it covers the head, else from
that status. Every absence and every failed lookup is exit 2. `sabotage_review.py`
reintroduces each collapse and names the test here that must go red. A fake
`gh` on PATH stands in for GitHub; every repository is built under tmp_path.
"""
import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_ledger as rl
import review_patch
import review_status as rs
from review_fixtures import git, init_repo

_SCRIPT = os.path.join(context._ROOT, "hooks", "scripts",  # pylint: disable=protected-access
                       "review_status.py")
T = "T1"
SLUG = "acme/widgets"

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

        def status(self, sha, statuses, reply_sha=None):
            self.reply(f"repos/{SLUG}/commits/{sha}/status",
                       {"sha": reply_sha or sha, "statuses": statuses})

        def calls(self):
            log = stub / "calls.log"
            if not log.exists():
                return []
            return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return Gh()


@pytest.fixture(name="repo")
def _repo(tmp_path):
    root = init_repo(tmp_path / "r")
    git(root, "remote", "add", "origin", f"git@github.com:{SLUG}.git")
    (root / "feature.txt").write_text("feature v1\n", encoding="utf-8")
    return root


@pytest.fixture(name="crepo")
def _crepo(tmp_path):
    """A clean checkout: no uncommitted change, so a status-only check is meaningful."""
    root = init_repo(tmp_path / "c")
    git(root, "remote", "add", "origin", f"git@github.com:{SLUG}.git")
    return root


def _review(repo, verdict="CLEAN", counts=None):
    base = git(repo, "rev-parse", "HEAD")
    manifest, _, _ = review_patch.compute(str(repo), base)
    ok, number, message = rl.reserve(str(repo), T, "codex")
    assert ok, message
    rl.record(str(repo), T, number, {
        "verdict": verdict, "counts": counts if counts is not None else {},
        "bundle_sha256": manifest["bundle_sha256"], "base": base, "head": manifest["head"],
        "provider": "codex", "model": None, "model_family": "gpt"})


def _name_head(repo, head, receipt=True):
    """Make the ledger's latest round name `head` (a review run at that head)."""
    path = rl.ledger_path(str(repo), T)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data["rounds"][-1]["head"] = head
    if not receipt:
        data["receipt"] = None
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def _commit_feature(repo):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "feature")
    return git(repo, "rev-parse", "HEAD")


CREATED = {"state": "success", "context": "crew/review"}


def created(head):
    return {**CREATED, "url": f"https://api.github.com/repos/{SLUG}/statuses/{head}"}


def _success(blocks=0):
    return {"context": rs.CONTEXT, "state": "success",
            "description": f"receipt r1 clean codex/gpt blocks={blocks} fix=0 nit=0 bundle=abc"}


def _cli(repo, *args):
    return subprocess.run([sys.executable, _SCRIPT, *args, "--root", str(repo)],
                          capture_output=True, text=True, encoding="utf-8",
                          stdin=subprocess.DEVNULL, check=False)


def test_check_no_ledger_no_status_is_could_not_tell(repo, gh):
    head = git(repo, "rev-parse", "HEAD")
    gh.status(head, [])

    code, lines = rs.check(str(repo), ticket=T)

    assert code == 2
    assert lines[0].startswith(f"REVIEW_GATE COULD_NOT_TELL head={head}")


@pytest.mark.parametrize("reply", [
    {"rc": 1, "err": "HTTP 403: API rate limit exceeded"},
    {"rc": 1, "err": "gh: To get started with GitHub CLI, please run: gh auth login"},
    {"out": "not json"},
    {"out": []},
    {"out": {"sha": "x", "statuses": "nope"}},
    {"out": {"statuses": []}},
])
def test_check_lookup_failures_are_could_not_tell(crepo, gh, reply):
    head = git(crepo, "rev-parse", "HEAD")
    gh.reply(f"repos/{SLUG}/commits/{head}/status", **reply)

    code, _ = rs.check(str(crepo))

    assert code == 2


@pytest.mark.skipif(os.name == "nt", reason="needs a symlink to git")
def test_check_gh_missing_is_could_not_tell(crepo, tmp_path, monkeypatch):
    only_git = tmp_path / "onlygit"
    only_git.mkdir()
    os.symlink(shutil.which("git"), only_git / "git")
    monkeypatch.setenv("PATH", str(only_git))

    code, lines = rs.check(str(crepo), head="a" * 40, repo=SLUG)

    assert code == 2
    assert "gh is not on PATH" in lines[0]


def test_check_status_reply_for_another_sha_is_could_not_tell(crepo, gh):
    head = git(crepo, "rev-parse", "HEAD")
    gh.status(head, [_success()], reply_sha="b" * 40)

    code, _ = rs.check(str(crepo))

    assert code == 2


@pytest.mark.parametrize("state", ["pending", "weird"])
def test_check_non_final_status_is_could_not_tell(crepo, gh, state):
    head = git(crepo, "rev-parse", "HEAD")
    gh.status(head, [{**_success(), "state": state}])

    code, _ = rs.check(str(crepo))

    assert code == 2


def test_check_status_is_bound_to_the_head(repo, gh):
    old = git(repo, "rev-parse", "HEAD")
    gh.status(old, [_success()])
    (repo / "later.txt").write_text("later\n", encoding="utf-8")
    new = _commit_feature(repo)
    gh.status(new, [])

    code, lines = rs.check(str(repo))

    assert code == 2 and f"head={new}" in lines[0]


@pytest.mark.parametrize("state", ["failure", "error"])
def test_check_failure_status_blocks(crepo, gh, state):
    head = git(crepo, "rev-parse", "HEAD")
    gh.status(head, [{**_success(), "state": state}])

    code, _ = rs.check(str(crepo))

    assert code == 1


def test_check_success_with_open_blocks_blocks(crepo, gh):
    head = git(crepo, "rev-parse", "HEAD")
    gh.status(head, [_success(blocks=4)])

    code, lines = rs.check(str(crepo))

    assert code == 1 and "4 BLOCK" in lines[0]


def test_check_success_without_readable_blocks_is_could_not_tell(crepo, gh):
    head = git(crepo, "rev-parse", "HEAD")
    gh.status(head, [{"context": rs.CONTEXT, "state": "success", "description": "ok"}])

    code, _ = rs.check(str(crepo))

    assert code == 2


def test_check_status_alone_allows_on_a_host_without_a_ledger(repo, gh):
    head = git(repo, "rev-parse", "HEAD")
    gh.status(head, [{"context": "ci/build", "state": "failure"}, _success()])

    code, lines = rs.check(str(repo), ticket=T)

    assert code == 0 and lines[0].startswith(f"REVIEW_GATE ALLOW head={head}")


def test_check_pr_reads_the_pull_requests_head(crepo, gh):
    head = git(crepo, "rev-parse", "HEAD")
    gh.reply(f"repos/{SLUG}/pulls/7", {"head": {"sha": head}})
    gh.status(head, [_success()])

    code, lines = rs.check(str(crepo), pr=7)

    assert code == 0 and f"head={head}" in lines[0]


def test_check_pr_unreadable_is_could_not_tell(crepo, gh):
    code, _ = rs.check(str(crepo), pr=7)

    assert code == 2


def test_check_local_ledger_allows_a_standing_receipt(repo, gh):
    _review(repo)

    code, lines = rs.check(str(repo), ticket=T)

    assert code == 0 and "local receipt" in lines[0]
    assert gh.calls() == []


def test_check_local_ledger_is_authoritative_for_its_head(repo, gh):
    _review(repo)
    (repo / "feature.txt").write_text("edited after the review\n", encoding="utf-8")
    head = git(repo, "rev-parse", "HEAD")
    gh.status(head, [_success()])

    code, lines = rs.check(str(repo), ticket=T)

    assert code == 1 and "stale" in lines[0]


def test_check_local_ledger_for_another_head_falls_back_to_the_status(repo, gh):
    _review(repo)
    other = "c" * 40
    gh.status(other, [])

    code, lines = rs.check(str(repo), ticket=T, head=other)

    assert code == 2 and "COULD_NOT_TELL" in lines[0]


def test_check_corrupt_ledger_is_could_not_tell(repo, gh):
    _review(repo)
    with open(rl.ledger_path(str(repo), T), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    head = git(repo, "rev-parse", "HEAD")
    gh.status(head, [_success()])

    code, _ = rs.check(str(repo), ticket=T)

    assert code == 2


def test_check_owner_accepted_round_with_blocks_blocks_locally(repo, gh):
    _review(repo, "FINDINGS", {"BLOCK": 4, "FIX": 5, "NIT": 2})
    rl.accept(str(repo), T, "the owner")

    code, lines = rs.check(str(repo), ticket=T)

    assert code == 1 and "4 BLOCK" in lines[0]


def test_post_publishes_success_for_an_accepted_clean_receipt(repo, gh):
    _review(repo)
    _commit_feature(repo)
    head = git(repo, "rev-parse", "HEAD")
    gh.reply(f"repos/{SLUG}/statuses/{head}", created(head))

    code, lines = rs.post(str(repo), T)

    posted = [c for c in gh.calls() if "POST" in c]
    assert code == 0 and len(posted) == 1 and f"repos/{SLUG}/statuses/{head}" in posted[0]
    assert "state=success" in posted[0] and f"context={rs.CONTEXT}" in posted[0]
    description = next(a for a in posted[0] if a.startswith("description="))
    assert "blocks=0" in description and "r1 clean codex/gpt" in description
    assert len(description) - len("description=") <= rs.DESCRIPTION_MAX
    assert "posted" in lines[0]


def test_post_refuses_without_a_ledger(crepo, gh):
    code, lines = rs.post(str(crepo), T)

    assert code == 1 and "not posted" in lines[0]
    assert gh.calls() == []


def test_post_refuses_a_stale_receipt(repo, gh):
    _review(repo)
    (repo / "feature.txt").write_text("edited after the review\n", encoding="utf-8")
    git(repo, "add", "-A")

    code, _ = rs.post(str(repo), T)

    assert code == 1
    assert gh.calls() == []


def test_post_refuses_an_owner_accepted_receipt_with_blocks(repo, gh):
    _review(repo, "FINDINGS", {"BLOCK": 4, "FIX": 5, "NIT": 2})
    rl.accept(str(repo), T, "the owner")

    _commit_feature(repo)

    code, lines = rs.post(str(repo), T)

    assert code == 1 and "4 BLOCK" in lines[0]
    assert gh.calls() == []


@pytest.mark.parametrize("counts", [{}, {"BLOCK": 0}, {"BLOCK": "0", "FIX": 0, "NIT": 0},
                                    {"BLOCK": True, "FIX": 0, "NIT": 0}])
def test_post_refuses_unreadable_counts(repo, gh, counts):
    _review(repo, "FINDINGS", counts)
    rl.accept(str(repo), T, "the owner")

    code, _ = rs.post(str(repo), T)

    assert code == 1
    assert gh.calls() == []


@pytest.mark.parametrize("latest", [{"verdict": "FINDINGS", "counts": None},
                                    {"verdict": "FINDINGS", "counts": [0, 0, 0]},
                                    {"verdict": "FINDINGS"}, None])
def test_counts_that_are_not_a_dict_are_unreadable_never_zero(latest):
    assert rs._counts(latest) is None  # pylint: disable=protected-access


def test_post_refuses_a_dirty_working_tree(repo, gh):
    _review(repo)

    code, lines = rs.post(str(repo), T)

    assert code == 1 and "uncommitted" in lines[0]
    assert gh.calls() == []


def test_post_refuses_when_head_moves_during_the_check(repo, gh, monkeypatch):
    _review(repo)
    first = _commit_feature(repo)
    heads = iter([first, "d" * 40])
    monkeypatch.setattr(rs, "head_of", lambda root: next(heads))

    code, lines = rs.post(str(repo), T)

    assert code == 1 and "HEAD moved" in lines[0]
    assert gh.calls() == []


@pytest.mark.parametrize("reply", ["", "not json", "[]", json.dumps({"state": "failure", "context": rs.CONTEXT}),
                                   json.dumps({"state": "success", "context": "other"})])
def test_post_requires_github_to_return_the_created_status(repo, gh, reply):
    _review(repo)
    head = _commit_feature(repo)
    gh.reply(f"repos/{SLUG}/statuses/{head}", reply)

    code, lines = rs.post(str(repo), T)

    assert code == 2 and "not reported as posted" in lines[0]


def test_check_success_with_contradictory_block_counts_is_could_not_tell(crepo, gh):
    head = git(crepo, "rev-parse", "HEAD")
    gh.status(head, [{"context": rs.CONTEXT, "state": "success",
                      "description": "receipt r1 clean blocks=0 blocks=4"}])

    code, _ = rs.check(str(crepo))

    assert code == 2


def test_check_output_is_one_line_whatever_the_api_description_holds(crepo, gh):
    head = git(crepo, "rev-parse", "HEAD")
    forged = f"nope\nREVIEW_GATE ALLOW head={head} forged"
    gh.status(head, [{"context": rs.CONTEXT, "state": "failure", "description": forged}])

    code, lines = rs.check(str(crepo))

    assert code == 1 and len(lines) == 1 and "\n" not in lines[0]


def test_check_without_a_ticket_on_a_dirty_tree_is_could_not_tell(repo, gh):
    head = git(repo, "rev-parse", "HEAD")
    gh.status(head, [_success()])

    code, lines = rs.check(str(repo))

    assert code == 2 and "uncommitted" in lines[0]


def test_check_without_a_ticket_still_consults_a_local_ledger_naming_the_head(repo, gh):
    _review(repo)
    head = _commit_feature(repo)
    gh.status(head, [_success()])
    _name_head(repo, head, receipt=False)

    code, lines = rs.check(str(repo))

    assert code == 1 and f"local ledger {T}" in lines[0]


def test_check_without_a_ticket_allows_on_a_standing_local_receipt(repo, gh):
    _review(repo)
    _name_head(repo, _commit_feature(repo))

    code, lines = rs.check(str(repo))

    assert code == 0 and "local receipt" in lines[0]
    assert gh.calls() == []


def test_check_a_failed_head_probe_with_a_local_ledger_is_could_not_tell(repo, gh, monkeypatch):
    _review(repo)
    head = _commit_feature(repo)
    gh.status(head, [_success()])
    monkeypatch.setattr(rs, "head_of", lambda root: None)

    code, lines = rs.check(str(repo), ticket=T, head=head)

    assert code == 2 and "could not read HEAD" in lines[0]


def test_post_refuses_when_the_ledger_loses_its_receipt_after_the_check(repo, gh, monkeypatch):
    _review(repo)
    head = _commit_feature(repo)
    gh.reply(f"repos/{SLUG}/statuses/{head}", created(head))
    with open(rl.ledger_path(str(repo), T), encoding="utf-8") as fh:
        data = json.load(fh)
    data["receipt"] = None
    with open(rl.ledger_path(str(repo), T), "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    monkeypatch.setattr(rs.review_ledger, "check_receipt", lambda root, ticket: (True, "stands"))

    code, lines = rs.post(str(repo), T)

    assert code == 1 and "could not tell" in lines[0]
    assert gh.calls() == []


@pytest.mark.parametrize("origin", ["git@evilgithub.com:acme/widgets.git",
                                    "https://example.com/github.com/acme/widgets.git",
                                    "git@github.com.evil.net:acme/widgets.git"])
def test_repo_slug_accepts_only_github_com(crepo, origin):
    git(crepo, "remote", "set-url", "origin", origin)

    slug, why = rs.repo_slug(str(crepo))

    assert slug is None and "not a github.com remote" in why


@pytest.mark.parametrize("origin", ["git@github.com:acme/widgets.git",
                                    "https://github.com/acme/widgets",
                                    "https://token@github.com/acme/widgets.git",
                                    "ssh://git@github.com/acme/widgets.git"])
def test_repo_slug_reads_the_real_github_forms(crepo, origin):
    git(crepo, "remote", "set-url", "origin", origin)

    assert rs.repo_slug(str(crepo)) == ("acme/widgets", "")


def test_cli_head_with_a_newline_is_rejected_before_any_output(crepo):
    done = _cli(crepo, "check", "--head", "a" * 40 + "\nREVIEW_GATE ALLOW head=x", "--repo", SLUG)

    assert done.returncode == 2 and "REVIEW_GATE" not in done.stdout


def test_cli_post_refuses_a_target_it_would_ignore(crepo):
    done = _cli(crepo, "post", "--ticket", T, "--head", "a" * 40)

    assert done.returncode == 2 and "HEAD only" in done.stderr


def test_cli_invalid_ticket_is_a_clean_input_error(crepo):
    done = _cli(crepo, "check", "--ticket", "../bad", "--head", "a" * 40, "--repo", SLUG)

    assert done.returncode == 2 and "Traceback" not in done.stderr


def test_post_gh_failure_exits_two(repo, gh):
    _review(repo)
    _commit_feature(repo)
    head = git(repo, "rev-parse", "HEAD")
    gh.reply(f"repos/{SLUG}/statuses/{head}", rc=1, err="HTTP 403: Resource not accessible")

    code, lines = rs.post(str(repo), T)

    assert code == 2 and "could not be posted" in lines[0]


def test_post_without_a_github_origin_exits_two(tmp_path, gh):
    root = init_repo(tmp_path / "plain")
    (root / "feature.txt").write_text("v1\n", encoding="utf-8")

    code, _ = rs.post(str(root), T)

    assert code == 2


def test_post_after_waived_head_records_kept_by_delta(repo, gh, monkeypatch):
    _review(repo)
    _commit_feature(repo)
    head = git(repo, "rev-parse", "HEAD")
    gh.reply(f"repos/{SLUG}/statuses/{head}", created(head))
    monkeypatch.setattr(rs.review_ledger, "check_receipt", lambda root, ticket: (
        True, "receipt kept by delta gate: round 1 clean, reviewed head abc"))

    code, _ = rs.post(str(repo), T)

    posted = [c for c in gh.calls() if "POST" in c][0]
    description = next(a for a in posted if a.startswith("description="))
    assert code == 0 and description.endswith(" kept-by-delta")


def test_cli_check_exits_two_when_nothing_can_be_told(repo, gh):
    head = git(repo, "rev-parse", "HEAD")
    gh.status(head, [])

    done = _cli(repo, "check", "--ticket", T)

    assert done.returncode == 2
    assert done.stdout.startswith(f"REVIEW_GATE COULD_NOT_TELL head={head}")


def test_cli_check_exits_zero_on_a_success_status(crepo, gh):
    head = git(crepo, "rev-parse", "HEAD")
    gh.status(head, [_success()])

    done = _cli(crepo, "check", "--head", head)

    assert done.returncode == 0 and done.stdout.startswith("REVIEW_GATE ALLOW")


@pytest.mark.parametrize("counts", [None, [], "x"])
def test_counts_of_a_clean_round_that_are_not_a_dict_are_unreadable(counts):
    assert rs._counts({"verdict": "CLEAN", "counts": counts}) is None  # pylint: disable=protected-access


@pytest.mark.parametrize("mutate", [lambda row: row.pop("head"), lambda row: row.update(head=None)])
def test_check_without_a_ticket_a_round_with_no_head_is_could_not_tell(crepo, gh, mutate):
    _review(crepo)
    head = git(crepo, "rev-parse", "HEAD")
    gh.status(head, [_success()])
    path = rl.ledger_path(str(crepo), T)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    mutate(data["rounds"][-1])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)

    code, lines = rs.check(str(crepo))

    assert code == 2 and "no readable head" in lines[0]


def test_post_requires_the_created_status_to_belong_to_the_head(repo, gh):
    _review(repo)
    head = _commit_feature(repo)
    gh.reply(f"repos/{SLUG}/statuses/{head}", created("e" * 40))

    code, lines = rs.post(str(repo), T)

    assert code == 2 and "not reported as posted" in lines[0]


def test_main_rejects_a_head_with_a_trailing_newline(crepo, capsys):
    code = rs.main(["check", "--root", str(crepo), "--head", "a" * 40 + "\n"])

    assert code == 2
    assert "REVIEW_GATE" not in capsys.readouterr().out


@pytest.mark.skipif(os.name == "nt", reason="process groups are POSIX")
def test_run_returns_when_a_child_holds_stdout_past_the_timeout(tmp_path, monkeypatch):
    script = tmp_path / "slow"
    script.write_text("#!/bin/sh\nsleep 30 &\nsleep 30\n", encoding="utf-8", newline="\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(rs, "GH_TIMEOUT", 1)

    code, _, err = rs._run(["slow"], str(tmp_path))  # pylint: disable=protected-access

    assert code == 124 and "timed out" in err
