"""The ticket's scope base: a commit on the ticket's own branch stays in the
evidence for the whole ticket.

THE DEFECT (T-0003). `/crew:work` printed its changed-file list as
`git diff --name-only $BASE` with the gate's own base, `.crew/.verify-verified-at`,
which verify-gate.sh writes at HEAD on every clean pass. Measured with the
real gate: a developer commits on its branch, the Stop passes, the marker
moves to that commit, and the next turn's evidence lists none of the ticket's
files while the branch still carries every one. `developer.md`'s blanket ban
on committing was the workaround -- keep everything in the working tree where
a moving base cannot lose it -- and every brief in this repository then told
the developer to commit anyway.

These cases run against real git repositories, because the questions are
about what git answers: ancestry, merge-bases, a sha the repository no longer
contains, a clone with no local `main`. The bug's own reproduction is
`test_a_commit_the_gate_verified_stays_in_the_ticket_evidence`, which asserts
BOTH halves -- the marker-based diff loses the file, the ticket-based diff
keeps it -- so the test documents the defect it guards against rather than
only the fix.

Every fallback is asserted to show MORE (the merge-base), never the verified
marker, and to say "(fallback)" on every line derived from it: an unknown
collapsing into the narrower, reassuring answer is this repository's named
recurring defect, and a scope base is exactly the place it would land.

Round 1 of Codex review found four ways the first cut collapsed anyway, each
with a case below: re-recording after the commit went missing overwrote the
start with HEAD; a single-value record lost T-1's base when T-2 started; the
fallback tried only a local `main`, which a `git clone -b <branch>` does not
have; and the bare `outside-scope:` line read as clean when the caveat was on
the next line.

The seed repository is built ONCE per module and copied per test. Measured on
the machine this was written on, one git invocation costs ~0.2-0.7s, and the
six that build a repository made every case here 4-8s for setup alone.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import

import scope_base

_ROOT = context._ROOT  # pylint: disable=protected-access
_REPO_ROOT = os.path.dirname(os.path.dirname(_ROOT))
_SCOPE_BASE_PY = os.path.join(_ROOT, "hooks", "scripts", "scope_base.py")
_SCOPE_REPORT_PY = os.path.join(_ROOT, "hooks", "scripts", "scope_report.py")


def _git(root, *args):
    return subprocess.run(
        ("git",) + args, cwd=root, check=True, capture_output=True,
        text=True, stdin=subprocess.DEVNULL).stdout.strip()


@pytest.fixture(scope="module", name="template")
def _template(tmp_path_factory):
    """One seed commit on `main`, a `work` branch checked out -- where a
    ticket's base is normally recorded. Built once; see the module header."""
    root = tmp_path_factory.mktemp("template") / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    _git(root, "checkout", "-q", "-b", "work")
    return root


@pytest.fixture(name="repo")
def _repo(tmp_path, template):
    root = tmp_path / "r"
    shutil.copytree(template, root)
    return root


def _commit(root, name, text="x\n"):
    (root / name).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", f"add {name}")
    return _git(root, "rev-parse", "HEAD")


def _head(root):
    return _git(root, "rev-parse", "HEAD")


def _record_file(root):
    return json.loads((root / ".crew" / ".scope-base").read_text(encoding="utf-8"))


def _cli(root, *args, ticket="T-1"):
    return subprocess.run(
        [sys.executable, _SCOPE_BASE_PY, "--root", str(root)] + list(args) + [ticket],
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)


def _clone(repo, tmp_path, branch="work"):
    """`git clone -b <branch>`: origin/HEAD -> origin/main, NO local main.
    The shape a second machine picks a ticket branch up in."""
    dst = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "-b", branch, str(repo), str(dst)],
                   check=True, capture_output=True, text=True)
    _git(dst, "config", "user.email", "t@example.com")
    _git(dst, "config", "user.name", "t")
    # A clone of a local repo points origin/HEAD at whatever the SOURCE has
    # checked out (`work` here); a hosted remote points it at the default
    # branch. Make the fixture say what a real remote says.
    _git(dst, "remote", "set-head", "origin", "main")
    return dst


# --- the record -----------------------------------------------------------

def test_record_writes_head_keyed_by_the_ticket(repo):
    sha, status = scope_base.record(str(repo), "T-1")
    assert sha == _head(repo)
    assert status == "recorded"
    data = _record_file(repo)
    assert data["T-1"]["base"] == sha
    assert data["T-1"]["from"] == "HEAD"


def test_recording_the_same_ticket_again_does_not_move_the_base(repo):
    """MUST NOT ADVANCE. `/crew:work` is re-run after a `/clear`, with commits
    on the branch by then. A base that moved to the new HEAD would drop every
    commit before it -- the same defect the record exists to close."""
    start, _ = scope_base.record(str(repo), "T-1")
    _commit(repo, "mid.py")
    again, status = scope_base.record(str(repo), "T-1")
    assert again == start, "the base moved on a re-run for the same ticket"
    assert status == "kept"


def test_a_second_ticket_does_not_lose_the_firsts_base(repo):
    """Codex round 1. Record T-1, commit, record T-2, resume T-1: with a
    single-value record T-1's base advanced to HEAD. The record is a mapping
    keyed by ticket, so both survive. T-2 starts past the fork, so its own
    entry is a labelled fallback at the merge-base (round 2 removed the
    "some earlier entry is an ancestor" exemption; see the next case)."""
    start, _ = scope_base.record(str(repo), "T-1")
    _commit(repo, "done.py")
    second, status = scope_base.record(str(repo), "T-2")
    assert (second, status) == (start, "recorded-fallback")
    resumed, status = scope_base.record(str(repo), "T-1")
    assert (resumed, status) == (start, "kept"), "T-1's base was lost when T-2 started"
    assert set(_record_file(repo)) == {"T-1", "T-2"}


def test_another_tickets_entry_never_stands_in_for_this_tickets_start(repo):
    """Codex round 2. T-1 recorded on main is an ancestor of every branch.
    Round 1's exemption read that as "this checkout has been working this
    branch" and recorded T-2 at HEAD, unlabelled, hiding the commits T-2's
    branch already carried. Only this ticket's own entry is evidence."""
    _git(repo, "checkout", "-q", "main")
    fork = _head(repo)
    scope_base.record(str(repo), "T-1")
    _git(repo, "checkout", "-q", "-b", "t2")
    _commit(repo, "made-elsewhere.py")

    done = _cli(repo, "--record", ticket="T-2")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == fork, "T-2 was recorded at HEAD, past its own commit"
    assert done.stderr.startswith("scope-base: (fallback) recorded"), done.stderr
    listed = _cli(repo, "--changed", ticket="T-2")
    assert "made-elsewhere.py" in listed.stdout.split(), listed.stdout
    assert "(fallback)" in listed.stderr


def test_re_recording_a_fallback_entry_keeps_saying_fallback(repo, tmp_path):
    """Codex round 2. First `--record` in a fresh clone says fallback; the
    second, after `/clear`, said "kept ... as the start" with no caveat --
    the guess had been upgraded to a known start by being read twice.
    Provenance is part of the entry, on every read and every re-record."""
    _commit(repo, "ahead.py")
    clone = _clone(repo, tmp_path)
    first = _cli(clone, "--record")
    assert first.stderr.startswith("scope-base: (fallback) recorded"), first.stderr
    again = _cli(clone, "--record")
    assert again.returncode == 0
    assert again.stdout == first.stdout
    assert again.stderr.startswith("scope-base: (fallback) kept"), again.stderr
    assert scope_base.record(str(clone), "T-1")[1] == "kept-fallback"
    assert scope_base.resolve(str(clone), "T-1")[1] == "record-fallback"
    assert _record_file(clone)["T-1"]["from"] == "merge-base with origin/main"


def test_a_record_whose_commit_is_missing_is_kept_not_replaced(repo):
    """Codex round 1. The recorded commit is gone from this clone (a squash,
    a rebase). Re-recording used to write HEAD in its place -- silently, and
    labelled "recorded". The entry is kept, the CLI says exactly what the
    evidence is now against, and resolve falls back with the fallback named."""
    scope_base.record(str(repo), "T-1")
    _commit(repo, "a.py")
    data = _record_file(repo)
    data["T-1"]["base"] = "0" * 40
    (repo / ".crew" / ".scope-base").write_text(json.dumps(data), encoding="utf-8")

    sha, status = scope_base.record(str(repo), "T-1")
    assert (sha, status) == ("0" * 40, "kept-missing")
    assert _record_file(repo)["T-1"]["base"] == "0" * 40, "the record was overwritten"

    done = _cli(repo, "--record")
    assert done.returncode == 0
    fork = _git(repo, "merge-base", "HEAD", "main")
    assert (f"start commit {'0' * 12} not in this clone; evidence is against "
            f"merge-base {fork[:12]} (fallback)") in done.stderr, done.stderr

    base, source, reason = scope_base.resolve(str(repo), "T-1")
    assert (base, source) == (fork, "merge-base")
    assert "(fallback)" in reason


def test_a_first_record_on_a_branch_already_past_the_fork_is_a_marked_fallback(
        repo, tmp_path):
    """Codex round 1. A fresh clone of a ticket branch has no record and HEAD
    is past every commit the ticket made. Recording HEAD hid them all under a
    line labelled "recorded". The merge-base is recorded instead, marked as
    a fallback in the file, the CLI line, resolve's source and reason."""
    fork = _head(repo)
    _commit(repo, "committed-elsewhere.py")
    clone = _clone(repo, tmp_path)

    done = _cli(clone, "--record")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == fork
    assert done.stderr.startswith("scope-base: (fallback) recorded"), done.stderr
    assert _record_file(clone)["T-1"]["from"] == "merge-base with origin/main"

    base, source, reason = scope_base.resolve(str(clone), "T-1")
    assert (base, source) == (fork, "record-fallback")
    assert reason.startswith("(fallback)")
    assert "committed-elsewhere.py" in scope_base.changed(str(clone), base)


def test_record_outside_a_repository_writes_nothing(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert scope_base.record(str(plain), "T-1") == (None, None)
    assert not (plain / ".crew" / ".scope-base").exists()


def test_the_single_entry_shape_of_the_first_cut_is_still_read(repo):
    """0.19.95's first cut wrote `{"ticket":..., "base":...}`. A checkout that
    recorded under that shape keeps its base rather than reading as none."""
    start = _head(repo)
    (repo / ".crew").mkdir()
    (repo / ".crew" / ".scope-base").write_text(
        json.dumps({"ticket": "T-1", "base": start}), encoding="utf-8")
    _commit(repo, "later.py")
    assert scope_base.record(str(repo), "T-1") == (start, "kept")
    assert scope_base.resolve(str(repo), "T-1")[:2] == (start, "record")


def test_the_record_is_ignored_by_this_repositorys_gitignore():
    """Machine-local, like the gate's marker: `.crew/*` is ignored and the
    named un-ignore list does not include it. Asked of git, not of the
    .gitignore text, because git is what decides."""
    done = subprocess.run(
        ["git", "check-ignore", "-q", scope_base.RECORD], cwd=_REPO_ROOT,
        capture_output=True, text=True, check=False)
    assert done.returncode == 0, (
        f"{scope_base.RECORD} is not ignored; a clone would inherit where a "
        "ticket started on someone else's machine")


# --- resolve --------------------------------------------------------------

def test_a_valid_record_is_the_base(repo):
    start, _ = scope_base.record(str(repo), "T-1")
    _commit(repo, "later.py")
    base, source, reason = scope_base.resolve(str(repo), "T-1")
    assert (base, source) == (start, scope_base.RECORDED)
    assert "T-1" in reason
    assert "fallback" not in reason


@pytest.mark.parametrize("spoil", [
    "absent", "other-ticket", "unreadable", "gone", "not-an-ancestor"])
def test_every_bad_record_falls_back_to_the_merge_base_and_says_why(repo, spoil):
    """Unknown resolves to MORE. The base is recorded one commit past the
    fork, so a fallback to the merge-base is observable as a DIFFERENT sha
    from both the record and HEAD. Each spoiled record falls back there --
    everything on the branch -- and never to the verified marker, planted at
    HEAD so that a fallback reading it is caught as the narrower answer."""
    fork = _head(repo)
    past = _commit(repo, "a.py")
    # Planted, not recorded: `record` on a fresh checkout already past the
    # fork would (correctly) write the merge-base as a marked fallback, and
    # the premise here is an entry that names a commit past it.
    (repo / ".crew").mkdir()
    record_path = repo / ".crew" / ".scope-base"
    record_path.write_text(json.dumps({"T-1": {"base": past, "from": "HEAD"}}),
                           encoding="utf-8")
    if spoil == "absent":
        record_path.unlink()
    elif spoil == "other-ticket":
        record_path.write_text(json.dumps({"T-0": {"base": _head(repo)}}),
                               encoding="utf-8")
    elif spoil == "unreadable":
        record_path.write_text("{not json", encoding="utf-8")
    elif spoil == "gone":
        record_path.write_text(json.dumps({"T-1": {"base": "0" * 40}}),
                               encoding="utf-8")
    elif spoil == "not-an-ancestor":
        # Amend: the recorded commit is replaced by one not descended from it.
        _git(repo, "commit", "-q", "--amend", "-m", "rewritten")
    (repo / ".crew" / ".verify-verified-at").write_text(
        _head(repo) + "\n", encoding="utf-8")
    base, source, reason = scope_base.resolve(str(repo), "T-1")
    assert source == "merge-base", reason
    assert base == fork
    assert base != _head(repo), "fell back to the narrower answer"
    assert "(fallback)" in reason and "with main" in reason


def test_the_fallback_uses_the_remote_default_when_there_is_no_local_main(
        repo, tmp_path):
    """Codex round 1. `git clone -b work` has origin/main and no local main.
    Trying only `main` failed, and the fallback became HEAD -- the narrowest
    answer -- while a merge-base with origin/main was there to be had.
    origin/HEAD is deleted here so the SECOND candidate is what answers."""
    fork = _head(repo)
    _commit(repo, "a.py")
    clone = _clone(repo, tmp_path)
    _git(clone, "remote", "set-head", "origin", "-d")
    base, source, reason = scope_base.resolve(str(clone), "T-1")
    assert (base, source) == (fork, "merge-base"), reason
    assert "with origin/main" in reason


def test_on_the_default_branch_with_no_record_the_base_is_head(repo):
    """merge-base(HEAD, main) IS HEAD there, so the working tree alone is
    the most that exists -- and the reason says so rather than staying quiet."""
    _git(repo, "checkout", "-q", "main")
    base, source, reason = scope_base.resolve(str(repo), "T-1")
    assert source in ("merge-base", "head")
    assert base == _head(repo)
    assert "no scope base recorded" in reason and "(fallback)" in reason


def test_outside_a_repository_resolve_answers_none_not_a_guess(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    base, source, reason = scope_base.resolve(str(plain), "T-1")
    assert (base, source) == (None, None)
    assert "git could not answer" in reason and "(fallback)" in reason


# --- the bug --------------------------------------------------------------

def test_a_commit_the_gate_verified_stays_in_the_ticket_evidence(repo):
    """THE BUG, both halves.

    The marker is planted exactly where verify-gate.sh's `record_verified`
    puts it after a clean pass -- at HEAD, after the developer's commit
    (test_verify_gate_baseline.py asserts that contract). The marker-based
    diff then lists nothing of the ticket; the ticket-based one lists the
    committed file, the dirty file and the untracked file alike."""
    scope_base.record(str(repo), "T-1")
    _commit(repo, "committed.py")
    marker = _head(repo)
    (repo / ".crew" / ".verify-verified-at").write_text(marker + "\n",
                                                        encoding="utf-8")
    (repo / "seed.txt").write_text("dirty\n", encoding="utf-8")
    (repo / "untracked.py").write_text("new\n", encoding="utf-8")

    from_marker = scope_base.changed(str(repo), marker)
    assert "committed.py" not in from_marker, (
        "the marker-based diff still shows the commit; the defect this test "
        "documents has changed shape, re-read verify-gate.sh's record_verified")

    base, source, _reason = scope_base.resolve(str(repo), "T-1")
    assert source == scope_base.RECORDED
    from_ticket = scope_base.changed(str(repo), base)
    assert {"committed.py", "seed.txt", "untracked.py"} <= set(from_ticket), from_ticket
    assert ".crew/.scope-base" in from_ticket, (
        "the record is untracked in a fixture with no .gitignore, so it must "
        "surface here; scope_report excludes it as bookkeeping, not this")


def test_changed_outside_a_repository_is_none_not_empty(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert scope_base.changed(str(plain), "HEAD") is None


# --- the command line -----------------------------------------------------

def test_cli_record_prints_the_sha_and_exits_zero(repo):
    done = _cli(repo, "--record")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == _head(repo)
    assert done.stderr.startswith("scope-base: recorded")
    again = _cli(repo, "--record")
    assert again.returncode == 0
    assert again.stderr.startswith("scope-base: kept")


def test_cli_record_outside_a_repository_exits_one_loudly(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    done = _cli(plain, "--record")
    assert done.returncode == 1
    assert "could not record" in done.stderr
    assert done.stdout == ""


def test_cli_base_prints_the_base_the_evidence_command_diffs_from(repo):
    start = _head(repo)
    _cli(repo, "--record")
    _commit(repo, "later.py")
    done = _cli(repo, "--base")
    assert done.returncode == 0
    assert done.stdout.strip() == start
    assert done.stderr.startswith("scope-base: " + start[:12])


def test_cli_changed_lists_the_ticket_wide_change_set(repo):
    _cli(repo, "--record")
    _commit(repo, "later.py")
    (repo / "untracked.py").write_text("new\n", encoding="utf-8")
    done = _cli(repo, "--changed")
    assert done.returncode == 0
    assert set(done.stdout.split()) >= {"later.py", "untracked.py"}


def test_cli_with_no_action_exits_two_with_usage(tmp_path):
    done = subprocess.run(
        [sys.executable, _SCOPE_BASE_PY, "--root", str(tmp_path)],
        capture_output=True, text=True, check=False)
    assert done.returncode == 2
    assert "usage" in done.stderr


# --- scope_report reads it -----------------------------------------------

def _ticketed(root, ticket="T-1", touch="- touch: src/"):
    (root / ".work" / "tickets").mkdir(parents=True)
    (root / ".work" / "INDEX.md").write_text(
        "| " + ticket + " | in progress |", encoding="utf-8")
    (root / ".work" / "tickets" / (ticket + ".md")).write_text(
        "## Scope\n" + touch + "\n", encoding="utf-8")


def _report(root, changed):
    return subprocess.run(
        [sys.executable, _SCOPE_REPORT_PY, str(root)],
        input="\n".join(changed), capture_output=True, text=True, check=False)


def test_scope_report_names_a_committed_file_the_gate_no_longer_sees(repo):
    """End to end. stdin is EMPTY -- the gate's list after the marker moved
    past the commit -- and the report still names the out-of-scope file,
    because it diffs the ticket's own base as well. A recorded base carries
    no marker on the line. Exit 0 throughout: the report is still report-only."""
    _ticketed(repo)
    scope_base.record(str(repo), "T-1")
    _commit(repo, "guide.md")
    done = _report(repo, [])
    assert done.returncode == 0, done.stderr
    first = done.stderr.splitlines()[0]
    assert first == "outside-scope: guide.md", done.stderr
    assert "scope-base: " + scope_base.resolve(str(repo), "T-1")[0][:12] in done.stderr


def test_scope_report_unions_rather_than_replaces_the_gates_list(repo):
    """Never less than the gate saw. A path the gate hands over that the
    ticket-wide diff does not contain (here, one the fixture never created)
    is still reported."""
    _ticketed(repo)
    scope_base.record(str(repo), "T-1")
    done = _report(repo, ["gate-only.md"])
    assert done.returncode == 0
    assert done.stderr.splitlines()[0] == "outside-scope: gate-only.md", done.stderr


def test_scope_report_marks_the_outside_scope_line_itself_on_a_fallback(repo):
    """Codex round 1. The caveat was on the scope-base line only, so the
    first line -- the one a reader or a grep takes -- read as a checked,
    clean result when it was a fallback. The marker is on the same line."""
    _ticketed(repo)
    _commit(repo, "guide.md")
    done = _report(repo, [])
    assert done.returncode == 0
    first = done.stderr.splitlines()[0]
    assert first.startswith("outside-scope: guide.md (fallback: no scope base recorded"), first


def test_scope_report_says_when_the_ticket_wide_diff_was_unavailable(tmp_path):
    """Outside a repository the gate's list still stands, and the FIRST line
    says the list is this turn's only rather than looking whole and clean."""
    root = tmp_path / "plain"
    root.mkdir()
    _ticketed(root)
    done = _report(root, ["src/a.py"])
    assert done.returncode == 0
    first = done.stderr.splitlines()[0]
    assert first.startswith("outside-scope: (this turn only:"), done.stderr
    assert "ticket-wide diff unavailable" in done.stderr
