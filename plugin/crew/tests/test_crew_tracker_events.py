"""R-72: durable event ids, so a timed-out tracker post is never duplicated.

    python3 -m pytest plugin/crew/tests/test_crew_tracker_events.py -q

The acceptance, stated as tests: after a timeout the next step is always a
marker search, never a blind post. A fake remote (a list of comments with a
call counter) drives the procedure `commands/jira-sync.md` "Posting once"
documents. Every repo is a throwaway under tmp_path; the ledger sits in its own
git common dir. The in-test mutants at the end each patch one guard out in this
process and assert that the paired case goes red.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import threading
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_tracker
import crew_tracker_events as events
from crew_fixtures import make_repo

SCRIPT = os.path.join(os.path.dirname(crew_tracker.__file__), "crew_tracker.py")
_ROOT = context._ROOT  # pylint: disable=protected-access
COMMANDS = os.path.join(_ROOT, "commands")
KEY = "ABC-12"


def _repo(tmp_path, kind="jira"):
    root = make_repo(tmp_path)
    (root / ".crew" / "crew.json").write_text(json.dumps({"schema": 1, "tracker": {"kind": kind}}),
                                              encoding="utf-8")
    return root


def _event(root, *args, ticket=KEY):
    """crew_tracker.main in this process (so a mutant reaches it): (exit, stdout)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = crew_tracker.main([*args, "--root", str(root), "--ticket", ticket])
    return code, out.getvalue()


def _begin(root, event="done", disc=None, ticket=KEY):
    extra = ["--disc", disc] if disc else []
    code, out = _event(root, "event", "begin", "--event", event, *extra, ticket=ticket)
    assert code == 0, out
    answer, eid = out.strip().split(": ", 1)
    return answer, eid


def _record(root, state, event="done", ref=None, ticket=KEY):
    extra = ["--ref", ref] if ref else []
    code, out = _event(root, "event", "record", "--event", event, "--state", state, *extra, ticket=ticket)
    assert code == 0, out
    return out


def _ledger(root, ticket=KEY):
    common = crew_tracker._common_dir(str(root))  # pylint: disable=protected-access
    return events.ledger_dir(common, ticket)


def _cli(root, *args):
    return subprocess.run([sys.executable, SCRIPT, *args, "--root", str(root)],
                          capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)


# --- ids --------------------------------------------------------------------------

def test_same_inputs_in_two_processes_give_the_same_id(tmp_path):
    root = _repo(tmp_path)

    first = _cli(root, "event", "begin", "--ticket", KEY, "--event", "done")
    second = _cli(root, "event", "begin", "--ticket", KEY, "--event", "done")

    assert (first.returncode, second.returncode) == (0, 0)
    assert first.stdout.split(": ")[0] == "post"
    assert first.stdout.split(": ")[1] == second.stdout.split(": ")[1]
    assert first.stdout.split(": ")[1].startswith("crew-evt-")


def test_each_part_of_the_id_matters():
    base = events.event_id("repo", KEY, "review-round", "1")

    assert len(base) == len("crew-evt-") + 20
    assert base == events.event_id("repo", KEY, "review-round", "1")
    assert base not in {events.event_id("repo", KEY, "review-round", "2"),
                        events.event_id("repo", KEY, "fix", "1"),
                        events.event_id("repo", "ABC-13", "review-round", "1"),
                        events.event_id("other", KEY, "review-round", "1")}


def test_different_discriminator_gives_a_different_id():
    assert events.event_id("repo", KEY, "progress", "abc123") != events.event_id("repo", KEY, "progress", "def456")


def test_a_repeating_kind_without_a_discriminator_is_usage(tmp_path):
    root = _repo(tmp_path)

    done = _cli(root, "event", "begin", "--ticket", KEY, "--event", "review-round")
    unknown = _cli(root, "event", "begin", "--ticket", KEY, "--event", "comment")

    assert (done.returncode, "needs --disc" in done.stdout) == (2, True)
    assert unknown.returncode == 2


def test_a_fixed_kind_refuses_another_discriminator():
    with pytest.raises(events.UsageError):
        events.discriminator("done", "2")
    assert (events.discriminator("done", None), events.discriminator("clean-up", "1")) == ("1", "1")


# --- states -----------------------------------------------------------------------

def test_first_begin_claims_in_state_intent(tmp_path):
    root = _repo(tmp_path)

    answer, eid = _begin(root)

    with open(os.path.join(_ledger(root), eid + ".json"), encoding="utf-8") as handle:
        record = json.load(handle)
    assert (answer, record["state"], record["kind"], record["discriminator"], record["ticket"]) == (
        "post", "intent", "done", "1", KEY)
    assert set(record) == {"id", "kind", "discriminator", "ticket", "state", "time", "attempts", "ref"}


def test_after_a_timeout_begin_says_check_remote_never_post(tmp_path):
    """The acceptance: a timed-out post is never posted blind."""
    root = _repo(tmp_path)

    _begin(root)
    _record(root, "unknown")
    answer, _ = _begin(root)

    assert answer == "check-remote"


def test_marker_found_after_unknown_is_skip(tmp_path):
    root = _repo(tmp_path)
    _begin(root)
    _record(root, "unknown")
    assert _begin(root)[0] == "check-remote"

    _record(root, "posted", ref="10001")

    assert _begin(root)[0] == "skip"


def test_failed_is_check_remote(tmp_path):
    root = _repo(tmp_path)
    _begin(root)

    _record(root, "failed")

    assert _begin(root)[0] == "check-remote"


def test_a_stale_intent_is_check_remote(tmp_path):
    root = _repo(tmp_path)
    _, eid = _begin(root)
    path = os.path.join(_ledger(root), eid + ".json")
    old = time.time() - events.IN_FLIGHT_SECONDS - 5
    os.utime(path, (old, old))

    assert _begin(root)[0] == "check-remote"


def test_two_concurrent_begins_give_one_post(tmp_path):
    ledger = str(tmp_path / "ledger")
    eid = events.event_id("repo", KEY, "done", "1")
    barrier, answers = threading.Barrier(2), []

    def claim():
        barrier.wait()
        answers.append(events.begin(ledger, eid, KEY, "done", "1")[0])
    threads = [threading.Thread(target=claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(answers) == ["in-flight", "post"]


def test_a_corrupt_ledger_is_could_not_tell_never_post(tmp_path):
    root = _repo(tmp_path)
    _, eid = _begin(root)
    path = os.path.join(_ledger(root), eid + ".json")
    with open(path, "wb") as handle:
        handle.write(b"{not json")

    code, out = _event(root, "event", "begin", "--event", "done")

    assert (code, out.startswith("could not tell: "), "post" in out.split(": ")[0]) == (1, True, False)


@pytest.mark.skipif(os.name == "nt", reason="a symlink needs privileges on Windows; O_NOFOLLOW is POSIX")
def test_a_symlink_at_the_ledger_name_is_refused(tmp_path):
    root = _repo(tmp_path)
    eid = events.event_id(crew_tracker.repo_id(str(root)), KEY, "done", "1")
    os.makedirs(_ledger(root))
    target = tmp_path / "elsewhere.json"
    target.write_text(json.dumps({"state": "posted"}), encoding="utf-8")
    os.symlink(str(target), os.path.join(_ledger(root), eid + ".json"))

    code, out = _event(root, "event", "begin", "--event", "done")

    assert (code, "not a regular file" in out) == (1, True)


def test_record_with_no_claim_is_could_not_tell(tmp_path):
    root = _repo(tmp_path)

    code, out = _event(root, "event", "record", "--event", "done", "--state", "posted")

    assert (code, "run event begin first" in out) == (1, True)


@pytest.mark.parametrize("kind", ["files", "obsidian"])
def test_local_event_post_twice_is_unchanged_and_writes_no_tracker_file(tmp_path, kind):
    root = _repo(tmp_path, kind)
    (root / ".work" / "INDEX.md").write_text("T-0042 | review | - | repo | t\n", encoding="utf-8")
    before = (root / ".work" / "INDEX.md").read_bytes()

    first = _event(root, "event", "post", "--event", "done", ticket="T-0042")
    second = _event(root, "event", "post", "--event", "done", ticket="T-0042")

    assert (first[0], first[1].startswith("posted: crew-evt-")) == (0, True)
    assert (second[0], second[1].startswith("unchanged: crew-evt-")) == (0, True)
    assert (root / ".work" / "INDEX.md").read_bytes() == before
    assert sorted(os.listdir(root / ".work")) == ["INDEX.md"]


def test_event_post_on_jira_and_begin_on_files_are_usage(tmp_path):
    jira = _repo(tmp_path / "j")
    files = _repo(tmp_path / "f", "files")

    assert _event(jira, "event", "post", "--event", "done")[0] == 2
    assert _event(files, "event", "begin", "--event", "done", ticket="T-0042")[0] == 2


def test_events_lists_every_record_and_writes_nothing(tmp_path):
    root = _repo(tmp_path)
    _begin(root)
    _record(root, "posted", ref="1")
    _begin(root, "review-round", "1")
    ledger = _ledger(root)
    before = {n: os.path.getmtime(os.path.join(ledger, n)) for n in os.listdir(ledger)}

    done = _cli(root, "events", "--ticket", KEY, "--json")

    listed = json.loads(done.stdout)
    assert (done.returncode, sorted(e["state"] for e in listed["events"]), listed["problems"]) == (
        0, ["intent", "posted"], [])
    assert {n: os.path.getmtime(os.path.join(ledger, n)) for n in os.listdir(ledger)} == before


def test_events_with_none_is_report_only(tmp_path):
    root = _repo(tmp_path)

    done = _cli(root, "events", "--ticket", KEY)

    assert (done.returncode, done.stdout) == (0, "no events\n")


# --- the documented procedure, against a fake remote ---------------------------------

class Timeout(Exception):
    """The post call gave no answer."""


class FakeRemote:
    """Comments with a call counter. `plan` says what each post does: `ok`,
    `lost` (times out, never lands), `landed` (times out after landing), or
    `late:<n>` (times out; lands just before call number n runs)."""

    def __init__(self, plan, status="In Progress"):
        self.plan, self.status, self.comments, self.calls, self.pending = list(plan), status, [], 0, None

    def _call(self):
        self.calls += 1
        if self.pending and self.pending[0] == self.calls:
            self.comments.append(self.pending[1])
            self.pending = None

    def read_status(self):
        self._call()
        return self.status

    def transition(self, name):
        self._call()
        self.status = name

    def search(self, mark):
        self._call()
        return any(c.splitlines()[-1] == mark for c in self.comments)

    def post(self, body):
        self._call()
        what = self.plan.pop(0)
        if what == "ok":
            self.comments.append(body)
            return str(len(self.comments))
        if what == "landed":
            self.comments.append(body)
        elif what.startswith("late:"):
            self.pending = (int(what.split(":")[1]), body)
        raise Timeout()


def _last_search(remote, mark):
    """Step 3 of `Posting once`: the last search right before the repost."""
    return remote.search(mark)


def post_once(root, remote, event="done", disc=None, ticket=KEY):
    """`Posting once`, as `commands/jira-sync.md` writes it."""
    answer, eid = _begin(root, event, disc, ticket=ticket)
    mark = events.marker(eid)
    if answer == "skip":
        return "skip"
    if answer not in ("post", "check-remote"):
        return answer
    for attempt in range(2):
        if remote.search(mark) or (answer == "check-remote" and _last_search(remote, mark)):
            _record(root, "posted", event, ticket=ticket)
            return "found"
        try:
            ref = remote.post("files touched ...; Two sentences.\n" + mark)
        except Timeout:
            _record(root, "unknown", event, ticket=ticket)
            if attempt:
                return f"tracker not updated: event {eid} not posted"
            answer, _ = _begin(root, event, disc, ticket=ticket)
            assert answer == "check-remote"
            continue
        _record(root, "posted", event, ref=ref, ticket=ticket)
        return "posted"
    return "unreachable"


def jira_done_push(root, remote):
    seen = remote.read_status()
    code, line = crew_tracker.transition(str(root), KEY, "done", seen)
    assert code == 0, line
    if line.startswith("go: "):
        remote.transition(line[len("go: "):])
    elif line.startswith("refused"):
        return line
    return post_once(root, remote)


def _marked(remote):
    return [c for c in remote.comments if c.splitlines()[-1].startswith(events.MARKER)]


def test_clean_done_push_is_four_calls(tmp_path):
    root, remote = _repo(tmp_path), FakeRemote(["ok"])

    assert jira_done_push(root, remote) == "posted"
    assert (remote.calls, len(_marked(remote)), remote.status) == (4, 1, "Complete")


def test_a_post_that_landed_then_timed_out_is_found_not_reposted(tmp_path):
    root, remote = _repo(tmp_path), FakeRemote(["landed"])

    assert jira_done_push(root, remote) == "found"
    assert len(_marked(remote)) == 1


def test_a_post_that_never_landed_is_posted_once_more_within_seven_calls(tmp_path):
    root, remote = _repo(tmp_path), FakeRemote(["lost", "ok"])

    assert jira_done_push(root, remote) == "posted"
    assert (len(_marked(remote)), remote.calls <= 7) == (1, True)
    assert remote.calls == 7


def test_a_late_landing_before_the_last_search_is_found(tmp_path):
    """Calls: 1 read, 2 transition, 3 search, 4 post (times out), 5 check-remote
    search, 6 the last search: the post lands just before call 6."""
    root, remote = _repo(tmp_path), FakeRemote(["late:6", "ok"])

    assert jira_done_push(root, remote) == "found"
    assert (len(_marked(remote)), remote.calls) == (1, 6)


def test_a_late_landing_after_the_last_search_is_the_visible_residual(tmp_path):
    """The window crew cannot close: it lands just before the repost (call 7).
    Both copies carry the same marker, so the duplicate stays visible."""
    root, remote = _repo(tmp_path), FakeRemote(["late:7", "ok"])

    jira_done_push(root, remote)

    marks = [c.splitlines()[-1] for c in _marked(remote)]
    assert (len(marks), len(set(marks))) == (2, 1)


def test_a_second_timeout_posts_nothing_more(tmp_path):
    root, remote = _repo(tmp_path), FakeRemote(["lost", "lost"])

    assert jira_done_push(root, remote).startswith("tracker not updated: event crew-evt-")
    assert (remote.calls, _marked(remote)) == (7, [])
    assert _begin(root)[0] == "check-remote"


def test_a_rerun_after_success_posts_nothing(tmp_path):
    root, remote = _repo(tmp_path), FakeRemote(["ok"])
    jira_done_push(root, remote)

    assert post_once(root, remote) == "skip"
    assert len(_marked(remote)) == 1


# --- SDP: desk names are never checked against crew words -----------------------------

class FakeDesk(FakeRemote):
    """sdp_get answers a desk status; the metadata call lists the desk's names."""

    def list_metadata(self):
        self._call()
        return ["Open", "Assigned", "In Progress", "Resolved", "Closed"]

    def sdp_transition(self, name):
        self.transition(name)


@pytest.mark.parametrize("desk_status", ["Open", "Assigned", "Resolved"])
def test_sdp_pushes_are_never_refused_by_a_desk_status(tmp_path, desk_status):
    root = _repo(tmp_path, "sdp")
    desk = FakeDesk(["ok"], status=desk_status)
    ticket = "SDP-40219"
    transitions = 0
    for word, budget in (("in-progress", 2), ("done", 4)):
        moved = _cli(root, "move", "--ticket", ticket, "--to", word)
        assert (moved.returncode, "refused" in moved.stdout, "could not tell" in moved.stdout) == (3, False, False)
        start = desk.calls
        names = desk.list_metadata()
        desk.sdp_transition(names[2] if word == "in-progress" else names[3])
        transitions += 1
        if word == "done":
            assert post_once(root, desk, ticket=ticket) == "posted"
        assert desk.calls - start <= budget

    assert (transitions, len(_marked(desk))) == (2, 1)


# --- the command files: one copy of the procedure, inside the line budget -------------

def _command(name):
    with open(os.path.join(COMMANDS, name), encoding="utf-8") as handle:
        return handle.read()


def test_sdp_sync_never_calls_transition_and_jira_sync_once():
    assert _command("sdp-sync.md").count("crew_tracker.py transition") == 0
    assert _command("jira-sync.md").count("crew_tracker.py transition") == 1


@pytest.mark.parametrize("name", ["jira-sync.md", "sdp-sync.md"])
def test_sync_files_fit_the_command_budget_without_an_allowance(name):
    with open(os.path.join(_ROOT, ".budget-allowance.json"), encoding="utf-8") as handle:
        allowance = handle.read()

    assert (len(_command(name).splitlines()) <= 120, name in allowance) == (True, False)


def test_posting_once_has_one_copy():
    jira, sdp = _command("jira-sync.md"), _command("sdp-sync.md")

    assert jira.count("\n## Posting once\n") == 1
    assert "## Posting once" not in sdp
    assert ("event begin" in sdp, "event record" in sdp) == (False, False)


def test_sdp_sync_points_at_posting_once():
    sdp = _command("sdp-sync.md")

    assert all(part in sdp for part in ("commands/jira-sync.md", "Posting once", "sdp_list_notes", "sdp_add_note"))


@pytest.mark.parametrize("name", ["jira-sync.md", "sdp-sync.md"])
def test_sync_files_still_resolve_the_tracker(name):
    assert "crew_tracker.py resolve" in _command(name)


# --- in-test mutants (D15): each must turn its paired case red ------------------------

def _red(case, *args):
    with pytest.raises(AssertionError):
        case(*args)


def test_mutant_unknown_reads_as_post(tmp_path, monkeypatch):
    real = events._answer  # pylint: disable=protected-access
    monkeypatch.setattr(events, "_answer",
                        lambda record, age: "post" if record.get("state") == "unknown" else real(record, age))

    _red(test_after_a_timeout_begin_says_check_remote_never_post, tmp_path)


def test_mutant_claim_without_o_excl(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "_CLAIM_FLAGS", events._CLAIM_FLAGS & ~os.O_EXCL)  # pylint: disable=protected-access

    _red(test_two_concurrent_begins_give_one_post, tmp_path)


def test_mutant_discriminator_left_out_of_the_hash(monkeypatch):
    real = events.event_id
    monkeypatch.setattr(events, "event_id", lambda repo, ticket, kind, disc: real(repo, ticket, kind, ""))

    _red(test_different_discriminator_gives_a_different_id)


def test_mutant_corrupt_ledger_reads_as_absent(tmp_path, monkeypatch):
    real = events._load  # pylint: disable=protected-access

    def lenient(path):
        record, problem = real(path)
        return (None, None) if problem else (record, problem)
    monkeypatch.setattr(events, "_load", lenient)

    _red(test_a_corrupt_ledger_is_could_not_tell_never_post, tmp_path)


def test_mutant_last_search_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules[__name__], "_last_search", lambda remote, mark: False)

    _red(test_a_late_landing_before_the_last_search_is_found, tmp_path)
