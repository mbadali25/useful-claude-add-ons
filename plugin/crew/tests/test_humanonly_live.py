"""crew 1.3.33: the human-only opt-out goes live (harness half).

`crew_ticket.cli_approval_allowed` now reads `crew_humanonly.resolve(..,
"approve")`; `approval_hook.py` records `/crew:confirm-config <id>` (the double
confirmation) and `/crew:approve-mass <id>` (the owner's yes to one blocked mass
operation); `scope_guard.py` keeps the session out of the confirmation store.

Must-allow: the opt-out the owner asked for takes effect when, and only when,
every rule in `crew_humanonly.resolve` holds. Must-block: every other state
reads as human-only, and the session can write none of the receipts. Each rule
has a mutation in `humanonly_mutations.py` (wired into `sabotage.py`) that must
turn one of these red.

Nothing here touches the real machine config: `crew_state.GLOBAL_CONFIG_PATH`
and HOME point under `tmp_path`.
"""
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import approval_hook
import crew_confirm_config
import crew_fixtures
import crew_humanonly
import crew_state
import crew_ticket
import scope_guard
from scope_fixtures import SCRIPTS, common_dir, make_repo, make_ticket, prompt


@pytest.fixture(name="home")
def _home(tmp_path, monkeypatch):
    """A machine config location under tmp_path, for every reader."""
    folder = tmp_path / "home" / ".claude" / "crew"
    folder.mkdir(parents=True)
    path = folder / "config.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(path))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    return path


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


def _typed(root, text, prompt_id):
    data = prompt(root, text)
    data["prompt_id"] = prompt_id
    return data


def _opt_out(root, home, key="humanOnly.approve", layer="machine"):
    """Propose the change and confirm it twice, as the owner would."""
    record = crew_confirm_config.propose(layer, key, root=str(root))
    for index in (1, 2):
        code = approval_hook.handle(
            _typed(root, f"/crew:confirm-config {record['change_id']}", f"p-{index}"))
        assert code == 0
    return record["change_id"]


def _machine_value(home, key="approve"):
    return json.loads(home.read_text(encoding="utf-8")).get("humanOnly", {}).get(key)


# --- cli_approval_allowed: must-allow ------------------------------------------------

def test_a_double_confirmed_machine_false_lets_a_cli_approval_count(repo, home):
    assert crew_ticket.cli_approval_allowed(str(repo)) is False

    _opt_out(repo, home)

    assert _machine_value(home) is False
    assert crew_ticket.cli_approval_allowed(str(repo)) is True


def test_a_cli_receipt_is_accepted_under_the_opt_out_and_not_before(repo, home):
    make_ticket(repo)
    crew_ticket.approve(str(repo), "T-1", via=crew_ticket.CLI)
    assert crew_ticket.accepted(str(repo), "T-1")["status"] == "unaccepted"

    _opt_out(repo, home)

    assert crew_ticket.accepted(str(repo), "T-1")["status"] == "approved"


def test_an_untracked_repo_false_with_a_receipt_opts_out(repo, home):
    _opt_out(repo, home, layer="repo")

    assert crew_ticket.cli_approval_allowed(str(repo)) is True


# --- cli_approval_allowed: must-block ------------------------------------------------

def test_the_default_keeps_a_cli_approval_human_only(repo, home):
    assert crew_ticket.cli_approval_allowed(str(repo)) is False


def test_a_hand_written_false_with_no_receipt_is_human_only(repo, home):
    home.write_text(json.dumps({"humanOnly": {"approve": False}}), encoding="utf-8")

    assert crew_ticket.cli_approval_allowed(str(repo)) is False


def test_a_repo_true_vetoes_a_confirmed_machine_false(repo, home):
    _opt_out(repo, home)
    (repo / ".crew" / "config.json").write_text(
        json.dumps({"humanOnly": {"approve": True}}), encoding="utf-8")

    assert crew_ticket.cli_approval_allowed(str(repo)) is False


def test_a_confirmed_promote_marker_opt_out_does_not_relax_approve(repo, home):
    _opt_out(repo, home, key="humanOnly.promoteMarker")

    assert crew_ticket.cli_approval_allowed(str(repo)) is False


def test_a_tracked_repo_false_never_opts_out(repo, home):
    (repo / ".crew" / "config.json").write_text(
        json.dumps({"humanOnly": {"approve": False}}), encoding="utf-8")
    crew_ticket._git(repo, "add", "-f", ".crew/config.json")  # pylint: disable=protected-access

    assert crew_ticket.cli_approval_allowed(str(repo)) is False


@pytest.mark.parametrize("answer", [RuntimeError("boom"), None, "no", {"humanOnly": "no"},
                                    {"humanOnly": None}, {}, {"humanOnly": 0}])
def test_an_unreadable_or_odd_resolver_answer_is_human_only(repo, home, monkeypatch, answer):
    def fake(*_args, **_kwargs):
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(crew_humanonly, "resolve", fake)

    assert crew_ticket.cli_approval_allowed(str(repo)) is False


def test_the_scope_guard_still_refuses_the_session_running_approve(repo, home):
    _opt_out(repo, home)
    common = common_dir(repo)

    reason = scope_guard.shell_refusal("python3 crew_ticket.py approve --ticket T-1", common,
                                       str(repo))

    assert reason and "approve" in reason


# --- /crew:confirm-config through the hook --------------------------------------------

def test_one_confirmation_is_pending_and_changes_nothing(repo, home, capsys):
    record = crew_confirm_config.propose("machine", "humanOnly.approve", root=str(repo))

    code = approval_hook.handle(_typed(repo, f"/crew:confirm-config {record['change_id']}", "p-1"))

    assert code == 0
    assert "once" in capsys.readouterr().out
    assert _machine_value(home) is None


def test_the_same_prompt_cannot_confirm_twice(repo, home, capsys):
    record = crew_confirm_config.propose("machine", "humanOnly.approve", root=str(repo))
    text = f"/crew:confirm-config {record['change_id']}"
    approval_hook.handle(_typed(repo, text, "p-1"))
    capsys.readouterr()

    code = approval_hook.handle(_typed(repo, text, "p-1"))

    assert code == 2
    assert "NOT recorded" in capsys.readouterr().err
    assert _machine_value(home) is None


def test_a_confirmation_with_no_prompt_id_is_refused(repo, home, capsys):
    record = crew_confirm_config.propose("machine", "humanOnly.approve", root=str(repo))
    data = prompt(repo, f"/crew:confirm-config {record['change_id']}")
    data.pop("prompt_id")

    assert approval_hook.handle(data) == 2
    assert "NOT recorded" in capsys.readouterr().err


@pytest.mark.parametrize("text", [
    "please run /crew:confirm-config cc-0123abcd for me",
    "no /crew:confirm-config cc-0123abcd\n/crew:confirm-config cc-0123abcd",
    "<command-name>/crew:confirm-config</command-name>\n<command-args>cc-0123abcd</command-args>"
    "\nand then a second thing",
])
def test_a_quoted_or_padded_confirmation_records_nothing(repo, home, capsys, text):
    record = crew_confirm_config.propose("machine", "humanOnly.approve", root=str(repo))

    code = approval_hook.handle(_typed(repo, text.replace("cc-0123abcd", record["change_id"]),
                                       "p-9"))

    assert code in (0, 2)
    assert crew_confirm_config.crew_humanonly.read_record(
        crew_humanonly.store_dir(), record["change_id"])["confirmations"] == []
    capsys.readouterr()


@pytest.mark.parametrize("arg", ["", "cc-1", "../x", "cc-zzzzzzzz", "cc-0123abcd extra"])
def test_a_malformed_change_id_is_refused(repo, home, capsys, arg):
    code = approval_hook.handle(_typed(repo, f"/crew:confirm-config {arg}", "p-1"))

    assert code == 2
    assert "usage" in capsys.readouterr().err


def test_the_expanded_confirmation_form_counts(repo, home, capsys):
    record = crew_confirm_config.propose("machine", "humanOnly.approve", root=str(repo))
    text = ("<command-name>/crew:confirm-config</command-name>\n"
            f"<command-args>{record['change_id']}</command-args>")

    assert approval_hook.handle(_typed(repo, text, "p-1")) == 0
    assert "once" in capsys.readouterr().out


def test_the_wrapper_passes_a_confirm_config_prompt_to_python(repo, home):
    bash = crew_fixtures.resolve_bash()
    if bash is None:
        pytest.skip("no working bash on PATH - the sh flavour was NOT run")
    record = crew_confirm_config.propose("machine", "humanOnly.approve", root=str(repo))
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo), HOME=str(home.parent.parent.parent),
               USERPROFILE=str(home.parent.parent.parent))
    payload = json.dumps(_typed(repo, f"/crew:confirm-config {record['change_id']}", "p-1"))

    done = subprocess.run([bash, os.path.join(SCRIPTS, "approval-hook.sh")],
                          input=payload.encode(), cwd=str(repo), capture_output=True, env=env,
                          check=False, timeout=120)

    assert done.returncode == 0, done.stderr
    stored = crew_humanonly.read_record(crew_humanonly.store_dir(), record["change_id"])
    assert len(stored["confirmations"]) == 1


# --- /crew:approve-mass through the hook ------------------------------------------------

MASS_ID = "0123456789ab"


def _mass_file(repo, mass_id=MASS_ID):
    return os.path.join(common_dir(repo), "crew", "mass-approvals", mass_id + ".json")


def test_the_users_prompt_records_a_mass_approval(repo, home, capsys):
    code = approval_hook.handle(_typed(repo, f"/crew:approve-mass {MASS_ID}", "p-5"))

    assert code == 0
    assert "approved mass operation" in capsys.readouterr().out
    with open(_mass_file(repo), encoding="utf-8") as handle:
        record = json.load(handle)
    assert (record["id"], record["approved_via"], record["prompt_id"]) == \
        (MASS_ID, "user-prompt", "p-5")
    assert 0 < record["expires"] - record["approved_at"] <= approval_hook.MASS_APPROVAL_TTL


def test_the_expanded_mass_approval_form_counts(repo, home, capsys):
    text = (f"<command-name>/crew:approve-mass</command-name>\n"
            f"<command-args>{MASS_ID}</command-args>")

    assert approval_hook.handle(_typed(repo, text, "p-5")) == 0
    assert os.path.isfile(_mass_file(repo))
    capsys.readouterr()


@pytest.mark.parametrize("text", [
    "I think /crew:approve-mass 0123456789ab is what you want",
    "so run /crew:approve-mass 0123456789ab",
    "> /crew:approve-mass 0123456789ab",
    "/crew:approve-mass 0123456789ab\n/crew:approve-mass 0123456789ab",
])
def test_a_quoted_or_pasted_mass_approval_records_nothing(repo, home, capsys, text):
    approval_hook.handle(_typed(repo, text, "p-5"))

    assert not os.path.exists(_mass_file(repo))
    capsys.readouterr()


@pytest.mark.parametrize("arg", ["", "xyz", "0123456789a", "0123456789abc", "../../evil",
                                 "0123456789AB", "0123456789ab 0123456789ab"])
def test_a_malformed_mass_id_is_refused_and_writes_nothing(repo, home, capsys, arg):
    code = approval_hook.handle(_typed(repo, f"/crew:approve-mass {arg}", "p-5"))

    assert code == 2
    assert "usage" in capsys.readouterr().err
    assert not os.path.isdir(os.path.join(common_dir(repo), "crew", "mass-approvals")) \
        or os.listdir(os.path.join(common_dir(repo), "crew", "mass-approvals")) == []


def test_a_mass_approval_outside_git_is_refused(tmp_path, home, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()

    code = approval_hook.handle(_typed(plain, f"/crew:approve-mass {MASS_ID}", "p-5"))

    assert code == 2
    assert "not a git repository" in capsys.readouterr().err


def test_approve_mass_is_not_a_plan_approval(repo, home, capsys):
    make_ticket(repo)

    approval_hook.handle(_typed(repo, f"/crew:approve-mass {MASS_ID}", "p-5"))

    assert crew_ticket.accepted(str(repo), "T-1")["status"] != "approved"
    capsys.readouterr()


# --- the session cannot write any of the receipts ----------------------------------------

def test_the_session_cannot_write_a_mass_approval(repo, home):
    common = common_dir(repo)
    target = os.path.join(common, "crew", "mass-approvals", MASS_ID + ".json")

    assert scope_guard.protected(str(repo), os.path.join(common, "crew"), target, str(repo))
    assert scope_guard.shell_refusal(f"echo {{}} > {target}", common, str(repo))


def test_the_session_cannot_write_the_confirmation_store(repo, home):
    common = common_dir(repo)
    target = os.path.join(crew_humanonly.store_dir(), "cc-0123abcd.json")

    assert scope_guard.protected(str(repo), os.path.join(common, "crew"), target, str(repo))
    assert scope_guard.shell_refusal(f"echo {{}} > {target}", common, str(repo))
    assert scope_guard.shell_refusal(
        "cp forged.json ~/.claude/crew/confirm-config/cc-0123abcd.json", common, str(repo))


def test_the_session_may_read_the_confirmation_store(repo, home):
    common = common_dir(repo)

    assert scope_guard.shell_refusal("cat ~/.claude/crew/confirm-config/cc-0123abcd.json",
                                     common, str(repo)) is None
    assert scope_guard.shell_refusal("python3 crew_confirm_config.py list", common,
                                     str(repo)) is None


def test_the_session_may_still_propose(repo, home):
    common = common_dir(repo)

    assert scope_guard.shell_refusal(
        "python3 crew_confirm_config.py propose --layer machine --key humanOnly.approve",
        common, str(repo)) is None


@pytest.mark.parametrize("name", ["approval-hook.sh", "approval_hook.py", "scope_guard.py"])
def test_every_changed_file_is_lf_only(name):
    with open(os.path.join(SCRIPTS, name), "rb") as fh:
        assert b"\r" not in fh.read()
