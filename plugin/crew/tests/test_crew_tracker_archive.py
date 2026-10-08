"""crew_tracker.py and the Complete/ archive (L-0509): ids beyond T- and the
archive move, split out of test_crew_tracker.py to keep that module under
pylint's 3,400-line cap. The shared fixtures stay there and are imported.

    python3 -m pytest plugin/crew/tests/test_crew_tracker_archive.py -q
"""
import json
import os
import pathlib
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_tracker
from crew_fixtures import make_repo
from test_crew_tracker import (CARD, ROW, _cli, _config_json, _crew_json, _files_repo, _index,
                               _make_vault, _obsidian_repo, _own, _refused, _snapshot, _symlink)


# --- ids beyond T- and the Complete/ archive (L-0509) -------------------------------

ARCHIVED = "Complete"
DONE_ROW = "T-0042 | done | low | repo | Fix token refresh on 401\n"


def _board_dir(vault):
    return vault / "Boards" / "repo"


def _archive_note(vault, ticket=CARD):
    folder = _board_dir(vault) / ARCHIVED
    folder.mkdir(exist_ok=True)
    os.rename(_board_dir(vault) / f"{ticket}.md", folder / f"{ticket}.md")


def _archived_obsidian(tmp_path, folder=True):
    """T-0042 done, its card gone from the board, its note under Complete/."""
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    (root / ".work" / "INDEX.md").write_text(DONE_ROW, encoding="utf-8", newline="\n")
    board = _board_dir(vault) / "Board.md"
    board.write_text(board.read_text(encoding="utf-8").replace(
        "- [ ] [[T-0042]] Fix token refresh on 401\n", ""), encoding="utf-8", newline="\n")
    _archive_note(vault)
    if folder:
        (root / ".work" / "tickets" / ARCHIVED / CARD).mkdir(parents=True)
    return root, vault


@pytest.mark.parametrize("ticket", ["L-0509", "W-0001"])
def test_cli_accepts_l_and_w_ids(tmp_path, ticket):
    root = _files_repo(tmp_path, f"{ticket} | spec | low | repo | x\n")

    done = _cli(root, "move", "--ticket", ticket, "--to", "planned")

    assert (done.returncode, done.stdout) == (0, "files: updated: .work/INDEX.md spec -> planned\n")


@pytest.mark.parametrize("ticket", ["Complete", "complete", "T-0042\n"])
def test_cli_refuses_complete(tmp_path, ticket):
    root = _files_repo(tmp_path, ROW)

    done = _cli(root, "read", "--ticket", ticket)

    assert (done.returncode, "like T-0042 or L-0509" in done.stderr) == (2, True)


def test_vault_paths_accepts_the_archive_subdir_only_through_the_constant(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    root = make_repo(tmp_path)
    settings = {"vaultPath": str(vault), "boardDir": "Boards/repo"}

    good, problem = crew_tracker._vault_paths(  # pylint: disable=protected-access
        str(root), settings, [("note", "T-1.md", ARCHIVED)])
    _, other = crew_tracker._vault_paths(  # pylint: disable=protected-access
        str(root), settings, [("note", "T-1.md", "Elsewhere")])
    _, nested = crew_tracker._vault_paths(  # pylint: disable=protected-access
        str(root), settings, [("board", "Complete/Board.md")])

    assert (problem, good["noteShown"], good["note"]) == (
        None, "Boards/repo/Complete/T-1.md", str(_board_dir(vault).resolve() / ARCHIVED / "T-1.md"))
    assert "only the archive folder" in other
    assert "must be a bare file name" in nested


def test_archived_note_is_confinement_checked(tmp_path):
    vault = _make_vault(tmp_path / "vault")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / f"{CARD}.md").write_text("planted\n", encoding="utf-8")
    _symlink(_board_dir(vault) / ARCHIVED, outside, is_dir=True)
    root = _obsidian_repo(tmp_path, vault)

    done, untouched = _refused(tmp_path, root, ("read", "--ticket", CARD))

    assert (done.returncode, untouched, "resolves outside the vault" in done.stdout) == (1, True, True)


def test_read_of_an_archived_ticket_reports_it_archived(tmp_path):
    root, _vault = _archived_obsidian(tmp_path)

    got = crew_tracker.read(str(root), CARD)["results"]

    assert (got[1]["state"], got[1]["lane"], got[1]["archived"]) == ("read", "Complete/", True)
    assert _cli(root, "read", "--ticket", CARD).returncode == 0


@pytest.mark.parametrize("folder", [True, False], ids=["folder-and-note", "note-only"])
@pytest.mark.parametrize("reopen", [False, True])
def test_move_of_an_archived_ticket_refuses(tmp_path, reopen, folder):
    root, vault = _archived_obsidian(tmp_path, folder=folder)
    before = _snapshot(root, vault)

    got = crew_tracker.move(str(root), CARD, "in-progress", reopen=reopen)

    assert (crew_tracker.exit_code(got), _snapshot(root, vault) == before) == (1, True)
    assert got["results"][-1]["reason"] == (
        "T-0042 is archived in Complete/; move its folder and note back by hand to reopen it")


@pytest.mark.parametrize("reopen", [False, True])
def test_files_move_of_an_archived_ticket_refuses(tmp_path, reopen):
    root = _files_repo(tmp_path, DONE_ROW)
    (root / ".work" / "tickets" / ARCHIVED / CARD).mkdir(parents=True)

    got = crew_tracker.move(str(root), CARD, "in-progress", reopen=reopen)

    assert (crew_tracker.exit_code(got), _index(root)) == (1, DONE_ROW)
    assert "archived in Complete/" in got["results"][-1]["reason"]


def test_create_refuses_an_id_whose_note_is_archived(tmp_path):
    root, vault = _archived_obsidian(tmp_path, folder=False)
    (root / ".work" / "INDEX.md").write_text("", encoding="utf-8")
    before = _snapshot(root, vault)

    got = crew_tracker.create(str(root), CARD, "again")

    assert (crew_tracker.exit_code(got), _snapshot(root, vault) == before) == (1, True)
    assert got["results"][-1]["reason"].startswith("id taken: ")
    assert "Complete" in got["results"][-1]["reason"]


@pytest.mark.parametrize("action", ["read", "move", "create"])
def test_note_in_both_places_is_could_not_tell(tmp_path, action):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    (_board_dir(vault) / ARCHIVED).mkdir()
    _own(root, _board_dir(vault) / ARCHIVED)
    if action == "create":
        (root / ".work" / "INDEX.md").write_text("", encoding="utf-8")
    before = _snapshot(root, vault)

    got = {"read": lambda: crew_tracker.read(str(root), CARD),
           "move": lambda: crew_tracker.move(str(root), CARD, "in-progress"),
           "create": lambda: crew_tracker.create(str(root), CARD, "again")}[action]()

    assert (crew_tracker.exit_code(got), _snapshot(root, vault) == before) == (1, True)
    assert "could not tell" in got["results"][-1]["reason"]


# --- crew_tracker.py archive (L-0509) -----------------------------------------------

def _done_obsidian(tmp_path, status="done"):
    """T-0042 at `status`, its two-line card in Done, its note this repo's."""
    vault = _make_vault(tmp_path / "vault", board="board_archived.md")
    root = _obsidian_repo(tmp_path, vault)
    (root / ".work" / "INDEX.md").write_text(DONE_ROW.replace("done", status), encoding="utf-8",
                                               newline="\n")
    (root / ".work" / "tickets" / CARD).mkdir(parents=True)
    (root / ".work" / "tickets" / CARD / "spec.md").write_text("spec\n", encoding="utf-8")
    return root, vault


def _archive_cli(root, ticket=CARD):
    return _cli(root, "archive", "--ticket", ticket)


def _archived_paths(root, vault, ticket=CARD):
    return ((root / ".work" / "tickets" / ARCHIVED / ticket / "spec.md").is_file(),
            (root / ".work" / "tickets" / ticket).exists(),
            (_board_dir(vault) / ARCHIVED / f"{ticket}.md").is_file(),
            (_board_dir(vault) / f"{ticket}.md").exists())


@pytest.mark.parametrize("status", ["in-progress", "review", "spec"])
def test_archive_refuses_a_ticket_not_done(tmp_path, status):
    root, vault = _done_obsidian(tmp_path, status)
    before = _snapshot(root, vault)

    done = _archive_cli(root)

    assert (done.returncode, _snapshot(root, vault) == before, done.stdout) == (
        1, True, f"files: could not update: T-0042 is {status}; only a done or merged ticket is archived\n")


@pytest.mark.parametrize("status", ["done", "merged"])
def test_archive_accepts_done_and_merged(tmp_path, status):
    root, vault = _done_obsidian(tmp_path, status)

    done = _archive_cli(root)

    assert (done.returncode, _archived_paths(root, vault)) == (0, (True, False, True, False))


def _point(root, mapping):
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    path = pathlib.Path(common) / "crew" / "active-ticket"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mapping if isinstance(mapping, str) else json.dumps(mapping), encoding="utf-8")


def test_archive_refuses_a_ticket_an_active_pointer_names(tmp_path):
    root, vault = _done_obsidian(tmp_path)
    _point(root, {"/somewhere/else": CARD, str(root): "T-0001"})
    before = _snapshot(root, vault)

    done = _archive_cli(root)

    assert (done.returncode, _snapshot(root, vault) == before) == (1, True)
    assert "T-0042 is the active ticket of the worktree at /somewhere/else" in done.stdout


def test_archive_refuses_when_the_pointer_map_is_unreadable(tmp_path):
    root, vault = _done_obsidian(tmp_path)
    _point(root, "{")
    before = _snapshot(root, vault)

    done = _archive_cli(root)

    assert (done.returncode, _snapshot(root, vault) == before) == (1, True)
    assert "could not tell whether a worktree has T-0042 active" in done.stdout


def test_archive_moves_the_folder_and_creates_complete(tmp_path):
    root = _files_repo(tmp_path, DONE_ROW)
    (root / ".work" / "tickets" / CARD).mkdir(parents=True)
    (root / ".work" / "tickets" / CARD / "plan.md").write_text("plan\n", encoding="utf-8")

    done = _archive_cli(root)

    assert (done.returncode, done.stdout,
            (root / ".work" / "tickets" / ARCHIVED / CARD / "plan.md").read_text(encoding="utf-8")) == (
        0, "folder: updated: .work/tickets/T-0042 -> .work/tickets/Complete/T-0042\n", "plan\n")


@pytest.mark.parametrize("which", ["folder", "note"])
def test_archive_refuses_an_existing_destination(tmp_path, which):
    root, vault = _done_obsidian(tmp_path)
    if which == "folder":
        (root / ".work" / "tickets" / ARCHIVED / CARD).mkdir(parents=True)
    else:
        (_board_dir(vault) / ARCHIVED).mkdir()
        (_board_dir(vault) / ARCHIVED / f"{CARD}.md").write_text("someone's\n", encoding="utf-8")
    before = _snapshot(root, vault)

    done = _archive_cli(root)

    assert (done.returncode, _snapshot(root, vault) == before) == (1, True)
    assert "could not tell" in done.stdout


def test_archive_never_renames_over_a_destination_that_appears(tmp_path, monkeypatch):
    """The folder half checks the destination, then renames: a destination that
    appears between the two is not overwritten (a non-empty directory refuses)."""
    root, vault = _done_obsidian(tmp_path)
    real = crew_tracker.crew_common.locate_ticket

    def appear(top, ticket):
        got = real(top, ticket)
        dest = root / ".work" / "tickets" / ARCHIVED / CARD
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "theirs.md").write_text("theirs\n", encoding="utf-8")
        return got
    monkeypatch.setattr(crew_tracker.crew_common, "locate_ticket", appear)

    got = crew_tracker.archive(str(root), CARD)

    assert crew_tracker.exit_code(got) == 1
    assert (root / ".work" / "tickets" / ARCHIVED / CARD / "theirs.md").is_file()
    assert (root / ".work" / "tickets" / CARD / "spec.md").is_file()
    assert (_board_dir(vault) / f"{CARD}.md").is_file()


@pytest.mark.skipif(os.name == "nt", reason="Windows' rename never replaces a directory")
@pytest.mark.parametrize("renameat2", [True, False], ids=["renameat2", "mkdir-claim"])
def test_archive_never_replaces_an_empty_destination_that_appears(tmp_path, monkeypatch,
                                                                   renameat2):
    """Port review of L-0509: POSIX rename replaces an EMPTY directory, so a
    destination created after the check must still not be renamed over."""
    if not renameat2:
        monkeypatch.setattr(crew_tracker, "_renameat2_noreplace", lambda *_a, **_k: False)
    root, _vault = _done_obsidian(tmp_path)
    real = crew_tracker.crew_common.locate_ticket
    dest = root / ".work" / "tickets" / ARCHIVED / CARD

    def appear(top, ticket):
        got = real(top, ticket)
        dest.mkdir(parents=True, exist_ok=True)
        return got
    monkeypatch.setattr(crew_tracker.crew_common, "locate_ticket", appear)

    got = crew_tracker.archive(str(root), CARD)

    assert crew_tracker.exit_code(got) == 1
    assert (dest.is_dir(), list(dest.iterdir()),
            (root / ".work" / "tickets" / CARD / "spec.md").is_file()) == (True, [], True)


def test_rename_note_never_replaces_a_note_that_appears_after_the_check(tmp_path, monkeypatch):
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    paths, _problem = crew_tracker._vault_paths(  # pylint: disable=protected-access
        str(root), crew_tracker.resolve(str(root))["settings"],
        crew_tracker._note_names({"board": "Board.md"}, CARD))  # pylint: disable=protected-access
    (_board_dir(vault) / ARCHIVED).mkdir()
    theirs = _board_dir(vault) / ARCHIVED / f"{CARD}.md"
    real_exists, real_lexists = crew_tracker._exists_at, os.path.lexists  # pylint: disable=protected-access

    def appear():
        theirs.write_text("theirs\n", encoding="utf-8")

    def exists_at(name, dir_fd):
        found = real_exists(name, dir_fd)
        appear()
        return found

    def lexists(path):
        found = real_lexists(path)
        if str(path) == str(paths["archivedNote"]):
            appear()
        return found
    monkeypatch.setattr(crew_tracker, "_exists_at", exists_at)
    monkeypatch.setattr(crew_tracker.os.path, "lexists", lexists)
    live = (_board_dir(vault) / f"{CARD}.md").read_bytes()

    got = crew_tracker._rename_note(paths)  # pylint: disable=protected-access

    assert (got["state"], (_board_dir(vault) / f"{CARD}.md").read_bytes(),
            theirs.read_text(encoding="utf-8")) == ("could not update", live, "theirs\n")


@pytest.mark.skipif(os.name == "nt", reason="Windows' rename never replaces")
def test_rename_note_refuses_where_hard_links_are_unavailable(tmp_path, monkeypatch):
    """Review round 2: no check-then-rename fallback; refusing beats a window."""
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    paths, _problem = crew_tracker._vault_paths(  # pylint: disable=protected-access
        str(root), crew_tracker.resolve(str(root))["settings"],
        crew_tracker._note_names({"board": "Board.md"}, CARD))  # pylint: disable=protected-access

    def no_link(*_args, **_kwargs):
        raise PermissionError(1, "Operation not permitted")
    monkeypatch.setattr(crew_tracker, "_renameat2_noreplace", lambda *_a, **_k: False)
    monkeypatch.setattr(crew_tracker.os, "link", no_link)

    got = crew_tracker._rename_note(paths)  # pylint: disable=protected-access

    assert (got["state"], (_board_dir(vault) / f"{CARD}.md").is_file(),
            (_board_dir(vault) / ARCHIVED / f"{CARD}.md").exists()) == ("could not update", True, False)


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_archive_refuses_a_complete_folder_that_is_a_link(tmp_path):
    root, _vault = _done_obsidian(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, root / ".work" / "tickets" / ARCHIVED)

    got = crew_tracker.archive(str(root), CARD)

    assert (crew_tracker.exit_code(got), list(outside.iterdir()),
            (root / ".work" / "tickets" / CARD / "spec.md").is_file()) == (1, [], True), got


def test_an_empty_claim_a_crash_left_is_named_never_removed(tmp_path):
    """An empty Complete/<ID> may be an interrupted archive's claim or someone
    else's folder: which cannot be told, so it is kept and the fix is named."""
    root, _vault = _done_obsidian(tmp_path)
    (root / ".work" / "tickets" / ARCHIVED / CARD).mkdir(parents=True)

    got = crew_tracker.archive(str(root), CARD)

    assert (crew_tracker.exit_code(got), (root / ".work" / "tickets" / ARCHIVED / CARD).is_dir(),
            any("remove it and rerun" in (r.get("reason") or "") for r in got["results"])) == (
        1, True, True), got


@pytest.mark.skipif(os.name == "nt", reason="the link-then-unlink move is POSIX only")
def test_archive_completes_a_note_left_under_both_names(tmp_path):
    root, vault = _done_obsidian(tmp_path)
    (_board_dir(vault) / ARCHIVED).mkdir()
    os.link(_board_dir(vault) / f"{CARD}.md", _board_dir(vault) / ARCHIVED / f"{CARD}.md")

    got = crew_tracker.archive(str(root), CARD)

    assert (crew_tracker.exit_code(got), (_board_dir(vault) / f"{CARD}.md").exists(),
            (_board_dir(vault) / ARCHIVED / f"{CARD}.md").is_file()) == (0, False, True), got


def test_archive_refuses_a_done_lane_card_above_complete(tmp_path):
    root, vault = _done_obsidian(tmp_path)
    board = _board_dir(vault) / "Board.md"
    text = board.read_text(encoding="utf-8")
    card = "- [x] [[T-0042]] Fix token refresh on 401\n\ta continuation line the card carries\n"
    text = text.replace(card, "").replace("## Done\n\n**Complete**\n",
                                         "## Done\n\n" + card.replace("[x]", "[ ]") + "\n**Complete**\n")
    board.write_text(text, encoding="utf-8", newline="\n")
    before = _snapshot(root, vault)

    got = crew_tracker.archive(str(root), CARD)

    assert (crew_tracker.exit_code(got), _snapshot(root, vault) == before) == (1, True), got
    assert any("above **Complete**" in (r.get("reason") or "") for r in got["results"]), got


def test_a_partly_archived_ticket_reads_as_disagreeing(tmp_path):
    root, vault = _done_obsidian(tmp_path)
    _archive_note(vault)

    got = crew_tracker.read(str(root), CARD)["results"][1]

    assert (got["disagree"], "partly archived" in (got["reason"] or "")) == (True, True), got


@pytest.mark.skipif(os.name == "nt", reason="the link-then-unlink move is POSIX only")
def test_a_note_under_both_names_is_kept_when_a_later_check_refuses(tmp_path):
    root, vault = _done_obsidian(tmp_path)
    (_board_dir(vault) / ARCHIVED).mkdir()
    os.link(_board_dir(vault) / f"{CARD}.md", _board_dir(vault) / ARCHIVED / f"{CARD}.md")
    (_board_dir(vault) / "Board.md").write_text("not a board\n", encoding="utf-8")

    got = crew_tracker.archive(str(root), CARD)

    assert (crew_tracker.exit_code(got), (_board_dir(vault) / f"{CARD}.md").is_file()) == (1, True)


def test_a_folder_only_archive_reads_as_partly_archived(tmp_path):
    root, _vault = _done_obsidian(tmp_path)
    tickets = root / ".work" / "tickets"
    (tickets / ARCHIVED).mkdir()
    os.rename(tickets / CARD, tickets / ARCHIVED / CARD)

    got = crew_tracker.read(str(root), CARD)["results"][1]

    assert (got["disagree"], "the ticket folder is in" in (got["reason"] or "")) == (True, True), got


@pytest.mark.skipif(os.name == "nt", reason="the pinned move is POSIX only")
def test_a_complete_folder_swapped_during_the_move_is_reported(tmp_path, monkeypatch):
    root, _vault = _done_obsidian(tmp_path)
    tickets = root / ".work" / "tickets"
    real = crew_tracker._rename_dir_no_replace  # pylint: disable=protected-access

    def swap(src, dst, dst_dir_fd=None):
        real(src, dst, dst_dir_fd=dst_dir_fd)
        os.rename(tickets / ARCHIVED, tickets / "elsewhere")
        (tickets / ARCHIVED).mkdir()
    monkeypatch.setattr(crew_tracker, "_rename_dir_no_replace", swap)

    got = crew_tracker.archive(str(root), CARD)

    assert crew_tracker.exit_code(got) == 1
    assert any("moved or replaced during the move" in (r.get("reason") or "") for r in got["results"])


@pytest.mark.skipif(os.name == "nt", reason="the link-then-unlink move is POSIX only")
def test_a_two_name_note_replaced_after_the_check_is_not_removed(tmp_path, monkeypatch):
    root, vault = _done_obsidian(tmp_path)
    (_board_dir(vault) / ARCHIVED).mkdir()
    os.link(_board_dir(vault) / f"{CARD}.md", _board_dir(vault) / ARCHIVED / f"{CARD}.md")
    answers = iter([True, False])
    monkeypatch.setattr(crew_tracker, "_one_note_two_names", lambda _paths: next(answers, False))

    got = crew_tracker.archive(str(root), CARD)

    assert (crew_tracker.exit_code(got), (_board_dir(vault) / f"{CARD}.md").is_file()) == (1, True), got


@pytest.mark.parametrize("archived_note", [False, True])
def test_a_read_surfaces_a_ticket_folder_in_both_places(tmp_path, archived_note):
    if archived_note:
        root, _vault = _archived_obsidian(tmp_path)
        (root / ".work" / "tickets" / CARD).mkdir(parents=True)
    else:
        root, _vault = _done_obsidian(tmp_path)
        (root / ".work" / "tickets" / ARCHIVED / CARD).mkdir(parents=True)

    got = crew_tracker.read(str(root), CARD)["results"][1]

    assert (got["disagree"], "folder lives" in (got["reason"] or "")) == (True, True), got


def test_an_archived_done_read_with_folders_in_both_places_never_calls_done_open(tmp_path):
    """Coordinator review: the folder doubt sets disagree, but the message
    about INDEX comes from the status check alone -- `done` is closed."""
    root, _vault = _archived_obsidian(tmp_path)
    (root / ".work" / "tickets" / CARD).mkdir(parents=True)
    _, _, why = crew_tracker.crew_common.locate_ticket(str(root), CARD)

    got = crew_tracker.read(str(root), CARD)["results"][1]

    assert (got["disagree"], got["reason"]) == (
        True, f"archived; INDEX status done; could not tell where {CARD}'s folder lives: {why}"), got


def test_a_live_read_keeps_the_first_probe_unknown(tmp_path, monkeypatch):
    """Coordinator review: one probe per read; a later probe answering LIVE
    must not replace the first one's could-not-tell."""
    root, _vault = _done_obsidian(tmp_path)
    real = crew_tracker.crew_common.locate_ticket
    calls = []

    def flaky(top, ticket):
        calls.append(ticket)
        if len(calls) == 1:
            return None, crew_tracker.crew_common.COULD_NOT_TELL, "probe failed: EIO"
        return real(top, ticket)
    monkeypatch.setattr(crew_tracker.crew_common, "locate_ticket", flaky)

    got = crew_tracker.read(str(root), CARD)["results"][1]

    assert (got["disagree"], "probe failed: EIO" in (got["reason"] or "")) == (True, True), got


def test_an_archived_read_with_an_open_index_row_disagrees(tmp_path):
    root, _vault = _archived_obsidian(tmp_path)
    (root / ".work" / "INDEX.md").write_text(DONE_ROW.replace("done", "review"), encoding="utf-8",
                                             newline="\n")

    got = crew_tracker.read(str(root), CARD)["results"][1]

    assert (got["disagree"], "is not closed" in got["reason"]) == (True, True), got


@pytest.mark.parametrize("kind,key", [("jira", "ABC-12"), ("sdp", "SDP-40219")])
def test_a_synced_tracker_refuses_to_move_or_create_an_archived_ticket(tmp_path, kind, key):
    root = make_repo(tmp_path)
    _config_json(root, kind)
    (root / ".work" / "tickets" / ARCHIVED / key).mkdir(parents=True)

    moved = crew_tracker.move(str(root), key, "in-progress")
    made = crew_tracker.create(str(root), key, "again")

    assert (crew_tracker.exit_code(moved), "archived in Complete/" in moved["results"][-1]["reason"],
            crew_tracker.exit_code(made), made["results"][-1]["reason"].startswith("id taken: ")) == (
        1, True, 1, True)


def test_an_archived_read_keeps_an_unknown_note_owner(tmp_path):
    root, vault = _archived_obsidian(tmp_path)
    (_board_dir(vault) / ARCHIVED / f"{CARD}.md").write_text("# T-0042\n", encoding="utf-8")

    got = crew_tracker.read(str(root), CARD)["results"][1]

    assert (got["state"], "could not tell" in (got["reason"] or "")) == ("read", True), got


@pytest.mark.parametrize("owner", ["foreign", "unknown"])
def test_archive_moves_a_note_only_when_ours(tmp_path, owner):
    root, vault = _done_obsidian(tmp_path)
    note = _board_dir(vault) / f"{CARD}.md"
    note.write_text("# T-0042\n\n- repo-id: someone-else\n" if owner == "foreign" else "# T-0042\n",
                    encoding="utf-8")
    before = _snapshot(root, vault)

    done = _archive_cli(root)

    assert (done.returncode, _snapshot(root, vault) == before) == (1, True)


def test_archive_removes_the_whole_card_from_done(tmp_path):
    root, vault = _done_obsidian(tmp_path)
    board = _board_dir(vault) / "Board.md"
    old = board.read_text(encoding="utf-8")

    done = _archive_cli(root)

    assert (done.returncode, board.read_text(encoding="utf-8")) == (0, old.replace(
        "- [x] [[T-0042]] Fix token refresh on 401\n\ta continuation line the card carries\n", ""))
    assert done.stdout.splitlines() == [
        "folder: updated: .work/tickets/T-0042 -> .work/tickets/Complete/T-0042",
        "obsidian-note: updated: Boards/repo/T-0042.md -> Boards/repo/Complete/T-0042.md",
        "obsidian: updated: Boards/repo/Board.md card removed from Done"]


def test_archive_refuses_a_card_outside_done(tmp_path):
    root, vault = _done_obsidian(tmp_path)
    board = _board_dir(vault) / "Board.md"
    board.write_text(board.read_text(encoding="utf-8").replace("[[T-0043]]", "[[T-0042]]", 1).replace(
        "- [x] [[T-0042]] Fix token refresh on 401\n\ta continuation line the card carries\n", ""),
        encoding="utf-8")
    before = _snapshot(root, vault)

    done = _archive_cli(root)

    assert (done.returncode, _snapshot(root, vault) == before) == (1, True)
    assert "card is in Ready, not Done" in done.stdout


def test_archive_leaves_index_byte_identical(tmp_path):
    root, _vault = _done_obsidian(tmp_path)
    index = (root / ".work" / "INDEX.md").read_bytes()

    assert _archive_cli(root).returncode == 0
    assert (root / ".work" / "INDEX.md").read_bytes() == index


def test_archive_twice_is_unchanged(tmp_path):
    root, vault = _done_obsidian(tmp_path)
    _archive_cli(root)
    before = _snapshot(root, vault)

    done = _archive_cli(root)

    assert (done.returncode, _snapshot(root, vault) == before, [line.split(":")[1].strip()
                                                               for line in done.stdout.splitlines()]) == (
        0, True, ["unchanged", "unchanged", "unchanged"])


@pytest.mark.parametrize("crash", ["after-folder", "after-note"])
def test_archive_completes_after_a_crash_between_halves(tmp_path, crash):
    root, vault = _done_obsidian(tmp_path)
    os.makedirs(root / ".work" / "tickets" / ARCHIVED)
    os.rename(root / ".work" / "tickets" / CARD, root / ".work" / "tickets" / ARCHIVED / CARD)
    if crash == "after-note":
        _archive_note(vault)

    done = _archive_cli(root)
    board = (_board_dir(vault) / "Board.md").read_text(encoding="utf-8")

    assert (done.returncode, _archived_paths(root, vault), "T-0042" in board) == (
        0, (True, False, True, False), False)
    assert done.stdout.splitlines()[0].startswith("folder: unchanged")


def test_archive_under_jira_moves_the_folder_only(tmp_path):
    root = make_repo(tmp_path)
    _crew_json(root, {"kind": "jira"})
    (root / ".work" / "INDEX.md").write_text(DONE_ROW, encoding="utf-8")
    (root / ".work" / "tickets" / CARD).mkdir(parents=True)

    done = _archive_cli(root)

    assert (done.returncode, done.stdout.splitlines()) == (0, [
        "folder: updated: .work/tickets/T-0042 -> .work/tickets/Complete/T-0042",
        "tracker: not applicable: jira has no board to archive from; the folder only"])


def test_archive_exit_codes_match_move(tmp_path):
    root = _files_repo(tmp_path, DONE_ROW)

    missing = _archive_cli(root)
    usage = _cli(root, "archive")

    assert (missing.returncode, usage.returncode, missing.stdout) == (
        1, 2, "folder: could not update: no folder for T-0042 at .work/tickets/T-0042\n")


def test_create_refuses_an_id_whose_folder_is_archived(tmp_path):
    root = _files_repo(tmp_path, "")
    (root / ".work" / "INDEX.md").write_text("", encoding="utf-8")
    (root / ".work" / "tickets" / ARCHIVED / CARD).mkdir(parents=True)

    got = crew_tracker.create(str(root), CARD, "again")

    assert (crew_tracker.exit_code(got), _index(root)) == (1, "")
    assert got["results"][0]["reason"] == "id taken: T-0042 is archived in Complete/"


def test_rename_note_refuses_an_existing_destination(tmp_path):
    """Belt to `_note_where`'s braces: a destination that appears after the
    check is never renamed over."""
    vault = _make_vault(tmp_path / "vault")
    root = _obsidian_repo(tmp_path, vault)
    paths, problem = crew_tracker._vault_paths(  # pylint: disable=protected-access
        str(root), crew_tracker.resolve(str(root))["settings"],
        crew_tracker._note_names({"board": "Board.md"}, CARD))  # pylint: disable=protected-access
    (_board_dir(vault) / ARCHIVED).mkdir()
    (_board_dir(vault) / ARCHIVED / f"{CARD}.md").write_text("theirs\n", encoding="utf-8")
    live = (_board_dir(vault) / f"{CARD}.md").read_bytes()

    got = crew_tracker._rename_note(paths)  # pylint: disable=protected-access

    assert (problem, got["state"], (_board_dir(vault) / f"{CARD}.md").read_bytes(),
            (_board_dir(vault) / ARCHIVED / f"{CARD}.md").read_text(encoding="utf-8")) == (
        None, "could not update", live, "theirs\n")
