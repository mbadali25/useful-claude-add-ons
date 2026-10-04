"""The ticket base branch: a repository that cuts ticket branches from an
integration branch measures each ticket against that branch (T-0061).

THE DEFECT. `scope_base._default_ref` tried `origin/HEAD`, then `origin/main`,
then `main`. TheSelectSource cuts every branch from `development`, so the
first `--record` on a fresh ticket branch took the merge-base with `main`:
for TSS-510, 492 files instead of 19, and the review bundle, the completion
audit and the refresh check all saw the whole integration branch. The repo
key `tickets.baseBranch` names the branch, and a value that names no commit
is "could not tell" -- no base -- never a silent fall back to `origin/HEAD`.

The fixture is the TSS-510 repro: upstream `main` at `seed.txt`,
`development` three commits ahead, and a clone whose origin/HEAD is `main`
with `fix/t-1` checked out from `origin/development` and no ticket commit.
Built once per module and copied per test, as `test_scope_base.py` does.
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import

import completion_audit
import crew_refresh_check
import scope_base
import webtest_guard

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCOPE_BASE_PY = os.path.join(_ROOT, "hooks", "scripts", "scope_base.py")
_CREW_TICKET_PY = os.path.join(_ROOT, "hooks", "scripts", "crew_ticket.py")


def _git(root, *args):
    return subprocess.run(
        ("git",) + args, cwd=root, check=True, capture_output=True,
        text=True, stdin=subprocess.DEVNULL).stdout.strip()


def _identity(root):
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")


def _commit(root, name, text="x\n"):
    (root / name).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", f"add {name}")
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture(scope="module", name="template")
def _template(tmp_path_factory):
    base = tmp_path_factory.mktemp("template")
    upstream = base / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-q", "-b", "main")
    _identity(upstream)
    _commit(upstream, "seed.txt", "seed\n")
    _git(upstream, "checkout", "-q", "-b", "development")
    for name in ("d1.txt", "d2.txt", "d3.txt"):
        _commit(upstream, name)
    _git(upstream, "checkout", "-q", "main")
    clone = base / "clone"
    subprocess.run(["git", "clone", "-q", str(upstream), str(clone)],
                   check=True, capture_output=True, text=True)
    _identity(clone)
    _git(clone, "remote", "set-head", "origin", "main")
    _git(clone, "checkout", "-q", "-b", "fix/t-1", "origin/development")
    # Machine-local, as a crew repo's .gitignore makes them: the config and
    # the record are not part of the ticket's change set.
    (clone / ".git" / "info" / "exclude").write_text(".crew/\n.work/\n",
                                                     encoding="utf-8")
    return base


@pytest.fixture(name="clone")
def _clone(tmp_path, template):
    dst = tmp_path / "w"
    shutil.copytree(template, dst)
    return dst / "clone"


def _config(root, value):
    (root / ".crew").mkdir(exist_ok=True)
    (root / ".crew" / "config.json").write_text(
        json.dumps({"tickets": {"baseBranch": value}}), encoding="utf-8")


def _head(root):
    return _git(root, "rev-parse", "HEAD")


def _record_path(root):
    return root / ".crew" / ".scope-base"


def _record_file(root):
    return json.loads(_record_path(root).read_text(encoding="utf-8"))


def _cli(root, *args, ticket="T-1"):
    return subprocess.run(
        [sys.executable, _SCOPE_BASE_PY, "--root", str(root)] + list(args) + [ticket],
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)


def _ticket_cli(root, *args):
    return subprocess.run(
        [sys.executable, _CREW_TICKET_PY] + list(args) + ["--root", str(root)],
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)


def _plant(root, base, source):
    (root / ".crew").mkdir(exist_ok=True)
    payload = json.dumps({"T-1": {"base": base, "from": source,
                                  "recordedAt": "2026-09-27T04:05:15+00:00"}})
    _record_path(root).write_text(payload, encoding="utf-8")


# --- the base branch --------------------------------------------------------

def test_a_branch_cut_from_the_configured_base_records_exact(clone):
    """TSS-510. origin/HEAD is main, the branch is cut from development, and
    the key names development: the record is HEAD, exact, and the change set
    is the ticket's file alone."""
    _config(clone, "development")
    done = _cli(clone, "--record")
    assert done.returncode == 0, done.stderr
    assert "recorded" in done.stderr and "(fallback)" not in done.stderr, done.stderr
    assert _record_file(clone)["T-1"]["from"] == "HEAD"
    _commit(clone, "t.txt")
    listed = _cli(clone, "--changed")
    assert listed.returncode == 0, listed.stderr
    assert listed.stdout.split() == ["t.txt"], listed.stdout


def test_without_the_key_the_default_is_origin_heads_target(clone):
    """Today's behaviour, unchanged: no key is origin/HEAD's target, and the
    first record on a development branch is the labelled fallback that shows
    the whole integration branch."""
    done = _cli(clone, "--record")
    assert done.returncode == 0, done.stderr
    assert "(fallback)" in done.stderr and "origin/main" in done.stderr, done.stderr
    listed = _cli(clone, "--changed")
    assert {"d1.txt", "d2.txt", "d3.txt"} <= set(listed.stdout.split()), listed.stdout


def test_head_equal_to_the_merge_base_records_exact_and_says_so(clone):
    """The direction's second defect: a record at branch cut, HEAD equal to
    the merge-base, must say "recorded" with no fallback label."""
    _config(clone, "development")
    assert _head(clone) == _git(clone, "rev-parse", "origin/development")
    done = _cli(clone, "--record")
    assert done.returncode == 0, done.stderr
    assert re.match(r"^scope-base: recorded [0-9a-f]{12} as the start of T-1 ",
                    done.stderr), done.stderr
    assert "(fallback)" not in done.stderr
    assert scope_base.resolve(str(clone), "T-1")[1] == "record"


@pytest.mark.parametrize("text", ["{", '{"tickets": {"baseBranch": 5}}'])
def test_a_corrupt_config_could_not_tell(clone, text):
    (clone / ".crew").mkdir()
    (clone / ".crew" / "config.json").write_text(text, encoding="utf-8")
    base, source, reason = scope_base.resolve(str(clone), "T-1")
    assert (base, source) == (None, "unknown"), reason
    assert "could not tell" in reason
    assert os.path.join(".crew", "config.json") in reason


# --- could not tell ---------------------------------------------------------

def test_a_configured_base_that_names_no_commit_could_not_tell(clone):
    _config(clone, "develop")
    base, source, reason = scope_base.resolve(str(clone), "T-1")
    assert (base, source) == (None, "unknown"), reason
    assert "tickets.baseBranch" in reason and "'develop'" in reason
    shown = _cli(clone, "--base")
    assert (shown.returncode, shown.stdout) == (3, ""), shown
    assert shown.stderr.startswith("scope-base: could not tell"), shown.stderr
    listed = _cli(clone, "--changed")
    assert (listed.returncode, listed.stdout) == (3, ""), listed
    done = _cli(clone, "--record")
    assert done.returncode == 1, done.stderr
    assert "could not tell" in done.stderr
    assert not _record_path(clone).exists(), "a could-not-tell record was written"


def test_could_not_tell_never_falls_back_to_origin_head(clone):
    """The neighbour case: origin/HEAD and origin/main both resolve, and a
    fix that fell through to the old chain would answer with them."""
    _config(clone, "develop")
    assert _git(clone, "rev-parse", "origin/HEAD")
    assert _git(clone, "rev-parse", "origin/main")
    assert scope_base.resolve(str(clone), "T-1")[0] is None
    assert scope_base.base_branch(str(clone))[0] is None
    assert scope_base.record(str(clone), "T-1") == (None, "unknown")


def _assert_could_not_tell_everywhere(root, *needles):
    """No base from any entry point, and nothing written: `--base` and
    `--changed` exit 3 with empty stdout, `--record` exits 1."""
    base, source, reason = scope_base.resolve(str(root), "T-1")
    assert (base, source) == (None, "unknown"), reason
    for needle in needles:
        assert needle in reason, reason
    for action in ("--base", "--changed"):
        done = _cli(root, action)
        assert (done.returncode, done.stdout) == (3, ""), (action, done)
        assert done.stderr.startswith("scope-base: could not tell"), done.stderr
    done = _cli(root, "--record")
    assert done.returncode == 1, done.stderr
    assert "could not tell" in done.stderr, done.stderr
    assert not _record_path(root).exists(), "an empty merge-base wrote a record"


def test_an_orphan_branch_with_the_key_could_not_tell(clone):
    """QA F1. `origin/development` resolves, but HEAD shares no history with
    it, so `git merge-base` is empty. That once fell to HEAD: `--base`
    printed it with exit 0 and `--record` wrote an EXACT entry, never moved
    again, hiding every commit on the branch."""
    _config(clone, "development")
    _git(clone, "checkout", "-q", "--orphan", "unrelated")
    _commit(clone, "orphan.txt")
    _assert_could_not_tell_everywhere(
        clone, "tickets.baseBranch 'development'", "no merge-base")


def test_an_orphan_branch_without_the_key_could_not_tell(clone):
    """The unset-key chain gets the same answer, deliberately: an empty
    merge-base with origin/main is just as unknown a start."""
    _git(clone, "checkout", "-q", "--orphan", "unrelated")
    _commit(clone, "orphan.txt")
    _assert_could_not_tell_everywhere(
        clone, "the default branch origin/main", "no merge-base")


def test_a_shallow_clone_could_not_tell(clone):
    """`--depth 1` of every branch: both tips are shallow boundaries, so
    `development` and `main` share no merge-base here, with or without the
    key."""
    upstream = clone.parent / "upstream"
    shallow = clone.parent / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--no-single-branch",
                    "-b", "development", upstream.as_uri(), str(shallow)],
                   check=True, capture_output=True, text=True)
    _git(shallow, "remote", "set-head", "origin", "main")
    (shallow / ".git" / "info" / "exclude").write_text(".crew/\n", encoding="utf-8")
    assert _git(shallow, "rev-parse", "--is-shallow-repository") == "true"
    _assert_could_not_tell_everywhere(shallow, "the default branch origin/main", "shallow")
    _config(shallow, "main")
    _assert_could_not_tell_everywhere(shallow, "tickets.baseBranch 'main'", "shallow")


def test_a_not_ancestor_record_says_could_not_tell_and_shows_more(clone):
    _config(clone, "development")
    scope_base.record(str(clone), "T-1")
    _git(clone, "checkout", "-q", "-B", "fix/t-1", "origin/main")
    _commit(clone, "elsewhere.txt")
    base, source, reason = scope_base.resolve(str(clone), "T-1")
    assert source == "merge-base", reason
    assert base == _git(clone, "merge-base", "HEAD", "origin/development")
    assert reason.startswith("could not tell where T-1 started:"), reason
    assert "(fallback)" in reason


# --- re-derivation ----------------------------------------------------------

def test_a_fallback_recorded_against_another_ref_is_rederived(clone):
    """TSS-510's poisoned entry: a merge-base guess against origin/main,
    written before the key named development."""
    old = _git(clone, "merge-base", "HEAD", "origin/main")
    _plant(clone, old, "merge-base with origin/main")
    _config(clone, "development")
    base, source, reason = scope_base.resolve(str(clone), "T-1")
    assert source == "merge-base", reason
    assert base == _git(clone, "merge-base", "HEAD", "origin/development")
    assert "origin/main" in reason and "origin/development" in reason
    assert "(fallback)" in reason
    done = _cli(clone, "--record")
    assert done.returncode == 0, done.stderr
    assert "re-derived" in done.stderr and "origin/main" in done.stderr, done.stderr
    entry = _record_file(clone)["T-1"]
    assert entry["from"] == "HEAD" and entry["base"] == _head(clone)
    assert scope_base.resolve(str(clone), "T-1")[1] == "record"


def test_an_exact_record_is_never_rederived(clone):
    seed = _git(clone, "rev-parse", "origin/main")
    _plant(clone, seed, "HEAD")
    before = _record_path(clone).read_bytes()
    _config(clone, "development")
    done = _cli(clone, "--record")
    assert done.returncode == 0, done.stderr
    assert done.stderr.startswith("scope-base: kept"), done.stderr
    assert _record_path(clone).read_bytes() == before


def test_a_fallback_recorded_against_the_same_ref_is_kept(clone):
    """TSS's current TSS-510 entry: `merge-base with origin/development` and
    the key `development`. The candidate tried first is `origin/development`,
    so the refs are equal and the entry stands."""
    _commit(clone, "t.txt")
    mb = _git(clone, "merge-base", "HEAD", "origin/development")
    _plant(clone, mb, "merge-base with origin/development")
    before = _record_path(clone).read_bytes()
    _config(clone, "development")
    done = _cli(clone, "--record")
    assert done.returncode == 0, done.stderr
    assert done.stderr.startswith("scope-base: (fallback) kept"), done.stderr
    assert _record_path(clone).read_bytes() == before


# --- activate ---------------------------------------------------------------

def _ticket_folder(root):
    (root / ".work" / "tickets" / "T-1").mkdir(parents=True)


def test_activate_records_the_scope_base(clone):
    _ticket_folder(clone)
    _config(clone, "development")
    done = _ticket_cli(clone, "activate", "--ticket", "T-1")
    assert done.returncode == 0, done.stderr
    entry = _record_file(clone)["T-1"]
    assert (entry["from"], entry["base"]) == ("HEAD", _head(clone))
    assert "scope-base: recorded" in done.stderr, done.stderr


def test_activate_never_moves_an_existing_record(clone):
    _ticket_folder(clone)
    _config(clone, "development")
    scope_base.record(str(clone), "T-1")
    before = _record_path(clone).read_bytes()
    _commit(clone, "t.txt")
    done = _ticket_cli(clone, "activate", "--ticket", "T-1")
    assert done.returncode == 0, done.stderr
    assert "kept" in done.stderr, done.stderr
    assert _record_path(clone).read_bytes() == before


def test_activate_sets_the_pointer_even_when_the_base_could_not_tell(clone):
    _ticket_folder(clone)
    _config(clone, "develop")
    done = _ticket_cli(clone, "activate", "--ticket", "T-1")
    assert done.returncode == 0, done.stderr
    assert "could not tell" in done.stderr, done.stderr
    shown = _ticket_cli(clone, "active")
    assert shown.stdout.strip().startswith("T-1"), shown


# --- consumers --------------------------------------------------------------

def test_completion_audit_fails_closed_when_it_could_not_tell(clone):
    _config(clone, "develop")
    _commit(clone, "t.txt")
    ok, lines = completion_audit.audit(str(clone), "T-1")
    assert ok is False
    assert "no scope base for T-1" in lines[0] and "could not tell" in lines[0], lines


def test_refresh_default_branch_follows_the_key(clone):
    _git(clone, "checkout", "-q", "-b", "development", "origin/development")
    sha = _head(clone)
    without = crew_refresh_check._fallback_hides(  # pylint: disable=protected-access
        str(clone), sha, "T-1")
    assert without is None or "development" not in without, without
    _config(clone, "development")
    assert crew_refresh_check._fallback_hides(  # pylint: disable=protected-access
        str(clone), sha, "T-1") == "HEAD is on the default branch development"


def test_webtest_guard_is_unknown_when_it_could_not_tell(clone):
    _config(clone, "develop")
    code, lines = webtest_guard.check_skips(str(clone), "T-1")
    assert code == webtest_guard.EXIT_UNKNOWN
    assert any("could not tell" in line for line in lines), lines
