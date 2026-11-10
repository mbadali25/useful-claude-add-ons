"""The repo handoff note is session metadata, not ticket scope. With an active,
approved ticket the scope guard refused a Write to `.work/HANDOFF.md` ("outside
spec ## Touch"), so `/crew:handoff --wrap-up` could not write the real note
through the Write tool (the only route that records an author), auto-resume
refused the PreCompact skeleton, and handoffs were dead for any session with an
active ticket.

A BLOCKING hook, so must-allow and must-block cases both. The fix is a narrow
allowlist (`crew_ticket.is_handoff_path`): `.work/HANDOFF.md` and
`.work/HANDOFF-*.md`, on the real and the named path both. Every other
out-of-Touch path stays refused and listed by the completion audit.
"""
import os

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_ticket
from scope_fixtures import FLAVOURS, edit, make_repo, make_ticket, ready, run_hook, stop

HANDOFFS = [".work/HANDOFF.md", ".work/HANDOFF-archive-20261017T1120Z.md"]
NOT_HANDOFFS = [".work/HANDOFF.md.bak", ".work/HANDOFFX.md", ".work/notes/HANDOFF.md",
                "docs/HANDOFF.md", "HANDOFF.md", ".work/INDEX.md", "other/keep.py"]


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


@pytest.mark.parametrize("rel", HANDOFFS)
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_approved_ticket_may_write_the_handoff(flavour, repo, rel):
    ready(repo)
    code, _, err = run_hook(flavour, "scope_guard", edit(repo, repo / rel), repo)
    assert (code, err) == (0, "")


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_an_unapproved_ticket_may_still_write_the_handoff(flavour, repo):
    make_ticket(repo)
    code, _, err = run_hook(flavour, "scope_guard", edit(repo, repo / ".work/HANDOFF.md"), repo)
    assert (code, err) == (0, "")


@pytest.mark.parametrize("tool", ["Edit", "MultiEdit"])
def test_edit_and_multiedit_may_write_the_handoff(repo, tool):
    ready(repo)
    code, _, _ = run_hook("module", "scope_guard", edit(repo, repo / ".work/HANDOFF.md", tool), repo)
    assert code == 0


@pytest.mark.parametrize("rel", NOT_HANDOFFS)
@pytest.mark.parametrize("flavour", FLAVOURS)
def test_every_other_out_of_touch_path_is_still_refused(flavour, repo, rel):
    ready(repo)
    code, _, err = run_hook(flavour, "scope_guard", edit(repo, repo / rel), repo)
    assert (code, "outside T-1's spec ## Touch" in err) == (2, True)


def test_a_handoff_symlink_to_an_out_of_touch_file_is_refused(repo):
    ready(repo)
    link = repo / ".work" / "HANDOFF.md"
    os.symlink(repo / "secret" / "x.py", link)
    code, _, err = run_hook("module", "scope_guard", edit(repo, link), repo)
    assert (code, "outside T-1's spec ## Touch" in err) == (2, True)


def test_a_dotdot_path_into_the_handoff_name_does_not_widen_scope(repo):
    ready(repo)
    sneaky = repo / ".work" / ".." / "other" / "keep.py"
    code, _, _ = run_hook("module", "scope_guard", edit(repo, sneaky), repo)
    assert code == 2


def test_is_handoff_path_matches_whole_names_only():
    assert all(crew_ticket.is_handoff_path(p) for p in HANDOFFS)
    assert not any(crew_ticket.is_handoff_path(p) for p in NOT_HANDOFFS)
    assert not crew_ticket.is_handoff_path(".work/../HANDOFF.md")


@pytest.mark.parametrize("flavour", FLAVOURS)
def test_audit_lists_other_changes_but_not_the_handoff(flavour, repo):
    ready(repo)
    (repo / ".work" / "HANDOFF.md").write_text("resume: /crew:status\n", encoding="utf-8")
    code, _, err = run_hook(flavour, "completion_audit", stop(repo), repo)
    assert (code, err) == (0, "")
    (repo / "other" / "keep.py").write_text("x = 2\n", encoding="utf-8")
    code, _, err = run_hook(flavour, "completion_audit", stop(repo), repo)
    assert code == 2 and "other/keep.py" in err and "HANDOFF" not in err
