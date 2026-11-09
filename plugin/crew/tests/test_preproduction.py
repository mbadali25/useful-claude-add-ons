"""`environments.preProduction` (crew 1.3.19): an environment LABELLED
production that is not live yet.

The must-block / must-allow suite CLAUDE.md requires for a change that
LOOSENS a guard that can block. Every must-block case is built so the bug it
guards against -- a wildcard reaching an unlisted environment, a mixed command
read as covered, a malformed entry read as "nothing listed", a destroy riding
the exemption, the machine file supplying the list -- would ALLOW; a case whose
broken value also denies could not go red under its mutation. The mutations
are in `sabotage_preproduction.py`, each naming the case it must turn red.

Nothing here runs terraform, ssh or psql: the guard judges the command text,
and the plan files are a few bytes of fixture text.
"""
import copy

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_preprod
import test_cloud_guard as tcg
import test_cloud_guard_environments as tce

import cloud_guard  # noqa: E402  pylint: disable=wrong-import-position

REASON = "stood up in November, no customer traffic yet"
PRE = {"acme-new": {"reason": REASON,
                    "targets": ["acme-new-web1", "acme-new-db1"]}}
HOSTS = {"production": {"hosts": ["acme-*"], "databases": ["acme-*"]}}
SERVER = {"guards": {"cloudGuard": "block"}}
TFW = tce.TFW
PLAN = tce.PLAN


def _tf(name):
    return f"{TFW}={name} terraform apply {PLAN}"


def _repo(pre=PRE, **extra):
    cfg = copy.deepcopy(HOSTS)
    cfg["environments"] = {"nonProd": [], "preProduction": copy.deepcopy(pre)}
    cfg.update(copy.deepcopy(extra))
    return cfg


def _ssh(tmp_path, command, repo_cfg=None, global_cfg=None, driver="python"):
    tcg._fixture(tmp_path, {**SERVER, **(repo_cfg or _repo())},  # pylint: disable=protected-access
                 global_cfg if global_cfg is not None else SERVER)
    return tcg.run_hook(driver, tmp_path, "Bash", command, extra_env={})


def _guard_log(tmp_path):
    path = tmp_path / "repo" / ".crew" / "guard.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# --- must allow: a listed environment, and nothing else ---------------------

ALLOW_COMMANDS = [
    ("ssh-listed-target", "ssh acme-new-web1 uptime"),
    ("ssh-listed-target-user", "ssh deploy@acme-new-web1 uptime"),
    ("ssh-the-env-name-itself", "ssh acme-new uptime"),
    ("psql-listed-db", "psql -h acme-new-db1 -c 'select 1'"),
]


@pytest.mark.parametrize("name,command", ALLOW_COMMANDS,
                         ids=[c[0] for c in ALLOW_COMMANDS])
def test_a_listed_target_is_not_refused_as_production(tmp_path, name, command):
    decision, said, code, err = _ssh(tmp_path, command)
    assert (decision, code) == ("allow", 0), (name, said, err)
    # The use is never silent: on screen, on stderr, in guard.log.
    for where in (said, err):
        assert "PRE-PRODUCTION EXEMPTION" in where, (name, where)
        assert REASON in where, where
    assert "env:preProduction:acme-new" in _guard_log(tmp_path), \
        _guard_log(tmp_path)


def test_the_exemption_is_allowed_for_powershell_text_too(tmp_path):
    tcg._fixture(tmp_path, {**SERVER, **_repo()}, SERVER)  # pylint: disable=protected-access
    decision, _said, code, err = tcg.run_hook(
        "python", tmp_path, "PowerShell", "ssh acme-new-web1 uptime",
        extra_env={})
    assert (decision, code) == ("allow", 0), err


def test_a_listed_environment_applies_unattended_like_nonprod(tmp_path):
    case = ("pre-saved-plan", "Bash", _tf("acme-new"),
            tce._o(repo={"environments": {"preProduction": PRE}},  # pylint: disable=protected-access
                   sidecar={"workspace": "acme-new"}))
    repo, (decision, said, code, err) = tce._run("python", tmp_path, case)  # pylint: disable=protected-access
    assert (decision, code) == ("allow", 0), (said, err)
    assert "PRE-PRODUCTION EXEMPTION" in said and REASON in said, said
    assert "PRE-PRODUCTION EXEMPTION" in err, err
    rows = [r for r in tce._log_rows(repo) if r[1] == "terraformApply"]  # pylint: disable=protected-access
    assert any(r[2] == "env:preProduction:acme-new" for r in rows), rows


def test_a_name_the_nonprod_globs_already_cover_is_not_claimed(tmp_path):
    """No exemption is reported for what `environments.nonProd` already allows:
    the audit line must not claim an effect the entry did not have."""
    case = ("pre-and-nonprod", "Bash", _tf("staging"),
            tce._o(repo={"environments": {"preProduction": {
                "staging": {"reason": REASON}}}},  # pylint: disable=protected-access
                sidecar={"workspace": "staging"}))
    repo, (decision, said, _code, err) = tce._run("python", tmp_path, case)  # pylint: disable=protected-access
    assert decision == "allow" and "PRE-PRODUCTION" not in said + err
    rows = [r for r in tce._log_rows(repo) if r[1] == "terraformApply"]  # pylint: disable=protected-access
    assert any(r[2] == "env:nonProd:staging" for r in rows), rows


# --- must block: everything the entry does not name -------------------------

BLOCK_COMMANDS = [
    # Every one aims at a host NOT named by the entry. A wildcard-reading bug
    # (acme-new* matching acme-new-eu) or a prefix-reading one would allow.
    ("ssh-unlisted-prod-host", "ssh acme-prod-web9 uptime"),
    ("ssh-prefix-of-listed", "ssh acme-new-web uptime"),
    ("ssh-extension-of-listed", "ssh acme-new-web10 uptime"),
    ("ssh-listed-plus-unlisted-same-line",
     "ssh acme-new-web1 uptime && ssh acme-prod-web9 uptime"),
    ("ssh-listed-jump-through-unlisted", "ssh -J acme-prod-web9 acme-new-web1"),
    ("psql-unlisted-db", "psql -h acme-prod-db3 -c 'select 1'"),
    ("psql-listed-host-plus-unlisted-conn",
     "psql -h acme-new-db1 postgres://u@acme-prod-db3/app"),
]


@pytest.mark.parametrize("name,command", BLOCK_COMMANDS,
                         ids=[c[0] for c in BLOCK_COMMANDS])
def test_an_unlisted_production_target_is_still_refused(tmp_path, name,
                                                        command):
    decision, reason, code, err = _ssh(tmp_path, command)
    assert (decision, code) == ("deny", 0), (name, reason, err)
    assert "permits no access" in reason, reason
    assert "PRE-PRODUCTION" not in err, err


@pytest.mark.parametrize("name,command", [ALLOW_COMMANDS[0], BLOCK_COMMANDS[0]],
                         ids=["listed", "unlisted"])
def test_the_default_config_is_unchanged(tmp_path, name, command):
    """No entry, no change: both are refused exactly as before this key."""
    repo = {"production": {"hosts": ["acme-*"]}}
    decision, reason, code, err = _ssh(tmp_path, command, repo_cfg=repo)
    assert (decision, code) == ("deny", 0), (name, reason, err)
    assert "PRE-PRODUCTION" not in reason + err


MALFORMED = {
    "no-reason": {"acme-new": {"targets": ["acme-new-web1"]}},
    "short-reason": {"acme-new": {"reason": "later", "targets":
                                  ["acme-new-web1"]}},
    "blank-reason": {"acme-new": {"reason": "            "}},
    "reason-not-a-string": {"acme-new": {"reason": 12345678901234}},
    "wildcard-name": {"acme-*": {"reason": REASON,
                                 "targets": ["acme-new-web1"]}},
    "wildcard-target": {"acme-new": {"reason": REASON, "targets": ["acme-*"]}},
    "bare-star-target": {"acme-new": {"reason": REASON, "targets": ["*"]}},
    "target-with-space": {"acme-new": {"reason": REASON,
                                       "targets": ["acme-new-web1 x"]}},
    "targets-a-string": {"acme-new": {"reason": REASON,
                                      "targets": "acme-new-web1"}},
    "entry-a-string": {"acme-new": REASON},
    "unknown-field": {"acme-new": {"reason": REASON, "ttl": 5,
                                   "targets": ["acme-new-web1"]}},
    "block-a-list": ["acme-new"],
}


@pytest.mark.parametrize("name", MALFORMED, ids=list(MALFORMED))
def test_a_malformed_entry_is_never_read_as_a_listing(tmp_path, name):
    """The listed host is the one the entry would exempt, so a malformed entry
    read as "listed anyway" would ALLOW it. It is refused, and says why."""
    repo = _repo(pre=MALFORMED[name])
    decision, reason, code, err = _ssh(tmp_path, "ssh acme-new-web1 uptime",
                                       repo_cfg=repo)
    assert (decision, code) == ("deny", 0), (name, reason, err)
    assert "PRE-PRODUCTION" not in reason + err
    assert crew_preprod.problem(MALFORMED[name]), name


@pytest.mark.parametrize("name", ["wildcard-name", "no-reason", "block-a-list"])
def test_a_malformed_entry_makes_every_environment_unknown(tmp_path, name):
    case = ("pre-malformed", "Bash", _tf("staging"),
            tce._o(environments={"nonProd": ["staging"],  # pylint: disable=protected-access
                                 "preProduction": MALFORMED[name]},
                   sidecar={"workspace": "staging"}))
    _repo_dir, (decision, reason, _code, err) = tce._run("python", tmp_path, case)  # pylint: disable=protected-access
    assert decision == "deny", (reason, err)


def test_the_machine_file_cannot_supply_the_list(tmp_path):
    """The list is a fact about one checkout. The same entry in the machine
    file reaches no repo (`filter_global` prunes it)."""
    repo = {**HOSTS}
    glob = {**SERVER, "environments": {"preProduction": PRE}}
    decision, reason, code, err = _ssh(tmp_path, "ssh acme-new-web1 uptime",
                                       repo_cfg=repo, global_cfg=glob)
    assert (decision, code) == ("deny", 0), (reason, err)
    assert "PRE-PRODUCTION" not in reason + err


def test_the_listing_does_not_touch_the_other_guards(tmp_path):
    """cloudDestructive, sqlDestructive and forcePush name no environment, so
    a listed one changes none of them."""
    for command in ("aws ec2 terminate-instances --instance-ids i-1",
                    "psql -h acme-new-db1 -c 'drop table users'",
                    "git push --force origin main"):
        decision, reason, code, err = _ssh(tmp_path, command)
        assert (decision, code) == ("deny", 0), (command, reason, err)
        assert "PRE-PRODUCTION EXEMPTION" not in err, (command, err)


TF_BLOCK = [
    # A destroy never rides the exemption: the destroy rule is not
    # environment-scoped.
    ("destroy-listed", "Bash", f"{TFW}=acme-new terraform destroy -auto-approve",
     tce._o(sidecar={"workspace": "acme-new"})),  # pylint: disable=protected-access
    ("apply-without-a-plan-listed", "Bash",
     f"{TFW}=acme-new terraform apply -auto-approve",
     tce._o(sidecar={"workspace": "acme-new"})),  # pylint: disable=protected-access
    ("plan-that-deletes-listed", "Bash", _tf("acme-new"),
     tce._o(sidecar={"workspace": "acme-new", "deletes": ["aws_db_instance.x"]})),  # pylint: disable=protected-access
    # Another production workspace, with a listing for a different one.
    ("unlisted-production", "Bash", _tf("production"),
     tce._o(sidecar={"workspace": "production"})),  # pylint: disable=protected-access
    ("prefix-of-listed", "Bash", _tf("acme-new-eu"),
     tce._o(sidecar={"workspace": "acme-new-eu"})),  # pylint: disable=protected-access
    # The workspace says listed, the plan itself is bound to production: the
    # signals disagree, which is unknown, never the listed one.
    ("listed-workspace-production-plan", "Bash", _tf("acme-new"),
     tce._o(sidecar={"workspace": "production"})),  # pylint: disable=protected-access
    ("listed-workspace-new-then-prod", "Bash",
     f"terraform workspace new acme-new && {TFW}=production terraform apply {PLAN}",
     tce._o(sidecar={"workspace": "production"})),  # pylint: disable=protected-access
    ("block-policy-wins", "Bash", _tf("acme-new"),
     tce._o(repo={"guards": {"terraformApply": "block"}},  # pylint: disable=protected-access
            global_={"guards": {"terraformApply": "block"}},
            sidecar={"workspace": "acme-new"})),
]


@pytest.mark.parametrize("case", TF_BLOCK, ids=[c[0] for c in TF_BLOCK])
def test_terraform_beyond_the_listing_is_still_refused(tmp_path, case):
    opts = dict(case[3])
    glob = opts.pop("global_", None)
    if glob:
        opts["global"] = glob
    opts.setdefault("repo", {})
    opts["repo"] = {**opts["repo"], "environments": {"preProduction": PRE}}
    case = (case[0], case[1], case[2], opts)
    _repo_dir, (decision, reason, code, err) = tce._run("python", tmp_path, case)  # pylint: disable=protected-access
    assert (decision, code) == ("deny", 0), (case[0], reason, err)
    assert "[terraformApply]" in reason, reason
    assert "PRE-PRODUCTION EXEMPTION" not in err, err


@tcg.needs_bash
@pytest.mark.parametrize("name,command", [ALLOW_COMMANDS[0], ALLOW_COMMANDS[3]],
                         ids=["ssh", "psql"])
def test_the_bash_wrapper_agrees(tmp_path, name, command):
    decision, said, code, err = _ssh(tmp_path, command, driver="bash")
    assert (decision, code) == ("allow", 0), (name, said, err)
    assert "PRE-PRODUCTION EXEMPTION" in err, err


# --- the pieces, unit by unit -----------------------------------------------


def test_cloud_guard_reads_the_entries_from_the_repo_layer_only(tmp_path):
    tcg._fixture(tmp_path, {"environments": {"preProduction": PRE}},  # pylint: disable=protected-access
                 {"environments": {"preProduction": {
                     "other": {"reason": REASON}}}})
    cfg = cloud_guard.environments_config(str(tmp_path / "repo"))
    assert list(cfg["preProduction"]) == ["acme-new"], cfg
    assert cfg["engaged"] is True


def test_no_entries_means_the_nonprod_list_is_untouched():
    envs = crew_preprod.arm({"nonProd": ["dev"], "preProduction": {}})
    assert envs["nonProd"] == ["dev"] and "declaredNonProd" not in envs


def test_covers_needs_every_matched_target():
    table = crew_preprod.entries(PRE)
    assert crew_preprod.covers(["acme-new-web1"], table)
    assert crew_preprod.covers(["acme-new-web1", "acme-x"], table) is None
    assert crew_preprod.covers([], table) is None
    assert crew_preprod.covers(["acme-new-web1"], {}) is None
