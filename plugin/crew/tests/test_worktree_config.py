"""A linked git worktree with no crew config of its own reads the main
checkout's repo config (T-0088).

Measured on T-0072's gate, 2026-09-28: in a lane worktree (no
`.crew/config.json`, since `.crew/*` is ignored) `cli_approval_allowed` was
False while the owner's main checkout set `scope.allowCliApproval: true`.
The worktree's own files always win, whole, and are never merged with the
main checkout's; when git cannot say where the main checkout is, the source
is `unknown` and nothing is inherited.

Every case builds a throwaway repository under tmp_path and adds a linked
worktree to it with `git worktree add`; nothing here reads the real
repository's config.
"""
import ast
import json
import os
import subprocess
import sys

import pytest

# isort: split
import cloud_guard
import context  # pylint: disable=unused-import
import crew_common
import crew_config
import crew_platform
import crew_state
import crew_status
import crew_ticket
from review_fixtures import git, init_repo
from scope_fixtures import edit, make_repo, ready, run_hook

SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access


def _lane(tmp_path, main_cfg):
    """A main checkout whose `.crew/config.json` is `main_cfg` (not written
    when None), and a linked worktree of it with no `.crew/` config."""
    main = make_repo(tmp_path, mode=None, name="main")
    if main_cfg is not None:
        (main / ".crew" / "config.json").write_text(json.dumps(main_cfg), encoding="utf-8")
    git(main, "worktree", "add", "-q", "-b", "lane", str(tmp_path / "wt"))
    return main, tmp_path / "wt"


def _own(wt, name, data):
    (wt / ".crew").mkdir(exist_ok=True)
    (wt / ".crew" / name).write_text(json.dumps(data) if not isinstance(data, str) else data,
                                     encoding="utf-8")


# --- the resolver -----------------------------------------------------------------------

def test_linked_worktree_reads_main_checkout_config(tmp_path):
    _main, wt = _lane(tmp_path, {"scope": {"allowCliApproval": True}})

    assert crew_ticket.cli_approval_allowed(str(wt)) is True


def test_linked_worktree_resolve_config_is_the_main_checkouts(tmp_path):
    _main, wt = _lane(tmp_path, {"qa": {"provider": "copilot",
                                        "copilot": {"model": "gemini-3.7-flash"}}})

    assert crew_config.resolve_config(str(wt))["qa"]["provider"] == "copilot"


def test_worktree_own_config_wins_and_is_never_merged(tmp_path):
    _main, wt = _lane(tmp_path, {"scope": {"allowCliApproval": True}, "tracker": "local"})
    _own(wt, "config.json", {"scope": {"mode": "off"}})

    assert crew_ticket.cli_approval_allowed(str(wt)) is False
    assert "tracker" not in crew_state.load_config(str(wt))


def test_worktree_with_only_crew_json_does_not_inherit_config_json(tmp_path):
    _main, wt = _lane(tmp_path, {"scope": {"allowCliApproval": True}})
    _own(wt, "crew.json", {"schema": 1})

    assert crew_common.repo_config_dir(str(wt))[1] == crew_common.SOURCE_OWN
    assert crew_state.load_config(str(wt)) == {}


def test_main_checkout_without_config_stays_absent(tmp_path):
    repo = init_repo(tmp_path / "r")

    assert crew_common.repo_config_dir(str(repo))[1] == crew_common.SOURCE_OWN
    assert crew_state.load_config(str(repo)) == {}


def test_plain_clone_is_own_with_no_git_call(tmp_path, monkeypatch):
    main, _wt = _lane(tmp_path, {"scope": {"allowCliApproval": True}})
    (main / ".crew" / "config.json").unlink()

    def _no_git(*_args):
        raise AssertionError("a plain checkout must not run git to resolve its config")

    monkeypatch.setattr(crew_common, "git_out", _no_git)

    assert crew_common.repo_config_dir(str(main))[1] == crew_common.SOURCE_OWN


def test_submodule_is_own(tmp_path):
    other = init_repo(tmp_path / "other")
    main = make_repo(tmp_path, mode=None, name="main")
    (main / ".crew" / "config.json").write_text(
        json.dumps({"scope": {"allowCliApproval": True}}), encoding="utf-8")
    git(main, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(other), "sub")

    assert crew_common.repo_config_dir(str(main / "sub"))[1] == crew_common.SOURCE_OWN


def test_git_failure_in_a_linked_worktree_is_unknown_not_own(tmp_path, monkeypatch):
    _main, wt = _lane(tmp_path, {"scope": {"allowCliApproval": True}})
    monkeypatch.setattr(crew_common, "git_out", lambda *a: None)

    _crew_dir, source, detail = crew_common.repo_config_dir(str(wt))

    assert (source, bool(detail)) == (crew_common.SOURCE_UNKNOWN, True)
    assert crew_ticket.cli_approval_allowed(str(wt)) is False



def test_resolver_works_on_a_git_without_path_format(tmp_path, monkeypatch):
    """git before 2.31 has no `--path-format`, and rev-parse echoes an
    argument it does not know as a line of its own."""
    _main, wt = _lane(tmp_path, {"scope": {"allowCliApproval": True}})
    real = crew_common.git_out

    def old_git(root, *args):
        known = [a for a in args if not a.startswith("--path-format")]
        out = real(root, *known)
        if len(known) != len(args) and out is not None:
            return "--path-format=absolute\n" + out
        return out

    monkeypatch.setattr(crew_common, "git_out", old_git)

    assert crew_common.repo_config_dir(str(wt))[1] == crew_common.SOURCE_MAIN

# --- guard input, must-block and must-allow ---------------------------------------------
# The scope guard judges a write only for an active ticket, so each case has one
# (approved, Touch `src/**`) and writes `other/keep.py`, outside it.

def test_scope_mode_block_in_main_checkout_blocks_in_worktree(tmp_path):
    _main, wt = _lane(tmp_path, {"scope": {"mode": "block"}})
    ready(wt)

    assert crew_ticket.configured_mode(str(wt))[0] == "block"
    assert run_hook("module", "scope_guard", edit(wt, wt / "other" / "keep.py"), wt)[0] == 2


def test_worktree_own_scope_off_is_not_overridden_by_main_block(tmp_path):
    _main, wt = _lane(tmp_path, {"scope": {"mode": "block"}})
    ready(wt)
    _own(wt, "config.json", {"scope": {"mode": "off"}})

    assert crew_ticket.configured_mode(str(wt))[0] == "off"
    assert run_hook("module", "scope_guard", edit(wt, wt / "other" / "keep.py"), wt)[0] == 0


def _role_write(tmp_path, wt):
    home = tmp_path / "home"
    (home / ".claude" / "crew").mkdir(parents=True, exist_ok=True)
    payload = {"tool_name": "Write", "cwd": str(wt), "agent_type": "pm",
               "tool_input": {"file_path": str(wt / "src" / "app.py")}}
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "role_write_guard.py")],
        input=json.dumps(payload), capture_output=True, text=True, check=False, cwd=str(wt),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(wt), HOME=str(home),
                 USERPROFILE=str(home)), timeout=120)


def test_role_write_guard_reads_the_inherited_layer(tmp_path):
    main, wt = _lane(tmp_path, None)
    (main / ".crew" / "config.json").write_text("{", encoding="utf-8")

    assert _role_write(tmp_path, wt).returncode == 2


def test_cloud_guard_reads_the_inherited_layer(tmp_path, monkeypatch):
    _main, wt = _lane(tmp_path, {"guards": {"cloudGuard": "block"}})
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(tmp_path / "absent.json"))

    assert cloud_guard.resolve_mode(str(wt))[0] == "block"


# --- every reader is routed -------------------------------------------------------------

CONFIG_NAMES = {"config.json", "crew.json"}
LABELS = {".crew/config.json", ".crew/crew.json"}

# The files allowed to name a repo config path outside the resolver, with the
# exact count of occurrences and why. A reader added beside an allowed label
# changes the count, so it is still caught. A join of `.crew` with a variable
# is counted too (a loop over config names reads that way), so the three
# variable joins that are not config reads are listed here by name.
ALLOWED = {
    "crew_platform.py": (1, "the writer: CONFIG_PATH, which never follows the main checkout"),
    # crew_autoclear_setup.py: the writer's own two files, plus the T-0106
    # --scan-root walk, which reads (never writes) each candidate's two files.
    "crew_autoclear_setup.py": (3, "the writer's own two files, the read-only scan"),
    "crew_migrate.py": (9, "the writer and its labels, plus the PM journal archive join; T-0038 "
                        "adds CONFIG_REL, the upgrade stage's own in-place target, and the "
                        "re-run's read of the crew.json it wrote"),
    "verify_fingerprint.py": (1, "a fingerprint input list, not a read of the config"),
    "webtest_rules.py": (1, "a secret-file glob, not a read of the config"),
    "crew_route.py": (1, "a message label naming the repo layer"),
    "role_write_guard.py": (1, "a message label naming the corrupt layer"),
    "crew_autocycle.py": (1, "the wrap-up marker `.crew/<prefix><key>`, not the config"),
    # crew_config.py, one reason per site:
    # - the guard approval marker `.crew/<prefix><name>-<digest>`, not the config;
    # - repo_config_path: the repo writer's own ./.crew/config.json target and label;
    # - the `.crew/crew.json` legacy-file notice after a repo write, not a config read.
    "crew_config.py": (3, "approval marker, the repo writer's own path, crew.json notice"),
    # crew_config_menu.py, one reason per site:
    # - `crewJson`: whether the legacy `.crew/crew.json` exists, shown as a label;
    # - the same crew.json notice after a menu Save, not a config read;
    # - the delete path's backup file name `.crew/<BACKUP_PREFIX><stamp>`, own path;
    # - the scratch repo's config.json written to preview the post-heal rows.
    "crew_config_menu.py": (4, "crew.json label and notice, own backup path, scratch heal"),
    # review_gate.py reads the stand-down flag exactly where verify-gate.sh does,
    # the worktree's own file, until T-0096 routes the shell gate; pinned by
    # test_review_gate.py's lane test.
    "review_gate.py": (1, "mirrors verify-gate.sh's own-file stand-down read (T-0096)"),
}


def _docstring_ids(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(
                    getattr(body[0], "value", None), ast.Constant):
                ids.add(id(body[0].value))
    return ids


def _const(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _repo_config_sites(tree):
    """Each `os.path.join(..., ".crew", <config name or any expression>)` and
    each whole-string `.crew/config.json`/`.crew/crew.json` constant."""
    docstrings = _docstring_ids(tree)
    sites, in_join = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "join":
            args = node.args
            for index, arg in enumerate(args[:-1]):
                if _const(arg) == ".crew":
                    nxt = args[index + 1]
                    if _const(nxt) is None or _const(nxt) in CONFIG_NAMES:
                        sites.append(node.lineno)
                        in_join.update(id(a) for a in args)
    for node in ast.walk(tree):
        if _const(node) in LABELS and id(node) not in docstrings and id(node) not in in_join:
            sites.append(node.lineno)
    return sites


def test_no_module_reads_repo_config_outside_the_resolver():
    found = {}
    for name in sorted(os.listdir(SCRIPTS)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(SCRIPTS, name), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        sites = _repo_config_sites(tree)
        if sites or name in ALLOWED:
            found[name] = sites

    unrouted = {name: lines for name, lines in found.items()
                if len(lines) != ALLOWED.get(name, (0, ""))[0]}

    assert unrouted == {}


# --- heal never shadows, and the source is shown ----------------------------------------

def test_heal_config_creates_nothing_in_an_inheriting_worktree(tmp_path):
    main, wt = _lane(tmp_path, {"scope": {"allowCliApproval": True}})
    (wt / ".crew").mkdir()

    cfg, message = crew_platform.heal_config(str(wt))

    assert cfg is None and str(main / ".crew" / "config.json") in message
    assert not (wt / ".crew" / "config.json").exists()



def test_heal_config_creates_nothing_when_git_could_not_tell(tmp_path, monkeypatch):
    _main, wt = _lane(tmp_path, {"scope": {"allowCliApproval": True}})
    (wt / ".crew").mkdir()
    monkeypatch.setattr(crew_common, "git_out", lambda *a: None)

    cfg, message = crew_platform.heal_config(str(wt))

    assert cfg is None and "could not tell" in message
    assert not (wt / ".crew" / "config.json").exists()


def test_heal_config_still_heals_a_worktree_whose_main_checkout_has_none(tmp_path):
    _main, wt = _lane(tmp_path, None)
    (wt / ".crew").mkdir()

    cfg, _message = crew_platform.heal_config(str(wt))

    assert cfg is not None and (wt / ".crew" / "config.json").exists()

def test_heal_config_still_heals_a_main_checkout(tmp_path):
    main = make_repo(tmp_path, mode=None, name="main")

    cfg, _message = crew_platform.heal_config(str(main))

    assert cfg is not None and (main / ".crew" / "config.json").exists()


def test_status_config_line_names_the_main_checkout_source(tmp_path):
    main, wt = _lane(tmp_path, {"scope": {"allowCliApproval": True}})

    text = "\n".join(crew_status._config_lines(str(wt))[0])  # pylint: disable=protected-access

    assert "inherited from the main checkout" in text
    assert str(main / ".crew" / "config.json") in text


def test_status_config_line_says_when_git_could_not_tell(tmp_path, monkeypatch):
    _main, wt = _lane(tmp_path, {"scope": {"allowCliApproval": True}})
    monkeypatch.setattr(crew_common, "git_out", lambda *a: None)

    text = "\n".join(crew_status._config_lines(str(wt))[0])  # pylint: disable=protected-access

    assert "could not tell" in text



def test_status_names_the_main_config_a_worktree_own_config_shadows(tmp_path):
    main, wt = _lane(tmp_path, {"scope": {"allowCliApproval": True}})
    _own(wt, "config.json", {"scope": {"mode": "off"}})

    text = "\n".join(crew_status._config_lines(str(wt))[0])  # pylint: disable=protected-access

    assert "not read" in text and str(main / ".crew") in text


@pytest.mark.parametrize("case", ["main-checkout", "worktree-main-has-none"])
def test_status_has_no_shadow_line_when_nothing_is_shadowed(tmp_path, case):
    main, wt = _lane(tmp_path, None if case == "worktree-main-has-none"
                     else {"scope": {"allowCliApproval": True}})
    _own(wt, "config.json", {"scope": {"mode": "off"}})

    root = main if case == "main-checkout" else wt
    text = "\n".join(crew_status._config_lines(str(root))[0])  # pylint: disable=protected-access

    assert "not read" not in text

def _explain(root, *extra):
    home = root.parent / "home"
    home.mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "crew_config.py"), "--root", str(root)]
        + list(extra), capture_output=True, text=True, check=False, timeout=120,
        env=dict(os.environ, HOME=str(home), USERPROFILE=str(home)))


def test_explain_prints_the_repo_layer_path_and_source(tmp_path):
    main, wt = _lane(tmp_path, {"scope": {"allowCliApproval": True}})

    in_wt = _explain(wt, "--explain").stdout
    in_main = _explain(main, "--explain").stdout
    as_json = _explain(wt, "--json").stdout

    assert "repo layer:" in in_wt and str(main / ".crew" / "config.json") in in_wt
    assert "(own)" in in_main
    assert isinstance(json.loads(as_json), list)


def test_explain_names_the_main_config_a_worktree_own_config_shadows(tmp_path):
    main, wt = _lane(tmp_path, {"scope": {"allowCliApproval": True}})
    _own(wt, "config.json", {"scope": {"mode": "off"}})

    in_wt = _explain(wt, "--explain").stdout

    assert "not read" in in_wt and str(main / ".crew") in in_wt
