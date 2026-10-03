"""crew-qa-standards' environment (E*) and gate (G*) items (L-0618): one
must-GAP and one must-PASS case per item, plus the N/A and UNKNOWN cases that
keep "could not tell" from reading as a pass. Every repo is a throwaway
directory under tmp_path; the only process started is git, in that directory."""
import datetime
import json
import os
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import qa_audit
import qa_audit_env


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _map(root, **vmap):
    vmap.setdefault("rules", [])
    _write(root, ".crew/verify.json", json.dumps(vmap))


def _row(root, rule):
    return next(r for r in qa_audit.audit(str(root)) if r["rule"] == rule)


def _rule(**over):
    rule = {"paths": ["src/**"], "run": ["pytest -q"], "reach": "local", "seconds": 5}
    rule.update(over)
    return rule


def _git_init(root):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=a@b", "-c", "user.name=a", "-c", "commit.gpgsign=false",
                  "commit", "-qm", "init", "--allow-empty"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, env=env, capture_output=True)


def _deny(monkeypatch, suffix):
    """Make qa_audit_env's open() raise PermissionError for paths ending in
    suffix. chmod 000 cannot do it: the container runs as root."""
    real = open

    def fake(path, *args, **kwargs):
        if str(path).endswith(suffix):
            raise PermissionError(13, "Permission denied", str(path))
        return real(path, *args, **kwargs)
    monkeypatch.setattr(qa_audit_env, "open", fake, raising=False)


def test_read_text_tells_absent_from_unreadable(tmp_path, monkeypatch):
    assert qa_audit_env.read_text(str(tmp_path / "missing.md")) is None
    _write(tmp_path, "x.md", "x")
    _deny(monkeypatch, "x.md")
    try:
        qa_audit_env.read_text(str(tmp_path / "x.md"))
    except PermissionError:
        pass
    else:
        raise AssertionError("an unreadable file read as absent")


def test_every_new_item_is_in_the_report(tmp_path):
    rules = {r["rule"] for r in qa_audit.audit(str(tmp_path))}
    assert {"G1", "G2", "G3", "G4", "G5", "E1", "E2", "E3", "E4", "E5", "E6", "E7"} <= rules


def test_an_unreadable_map_is_unknown_not_na(tmp_path):
    _write(tmp_path, ".crew/verify.json", "{not json")
    for rule in ("G1", "G2", "E1", "E2", "E7"):
        assert _row(tmp_path, rule)["status"] == qa_audit.UNKNOWN, rule


def test_no_map_is_na(tmp_path):
    for rule in ("G1", "G2", "E1", "E2", "E7"):
        assert _row(tmp_path, rule)["status"] == qa_audit.NA, rule


# --- G1 reach (D10) ------------------------------------------------------------------------

def _undeclared(run):
    rule = _rule(run=run)
    del rule["reach"]
    return rule


def test_g1_a_rule_the_stop_gate_defers_is_named_skipped(tmp_path):
    _map(tmp_path, rules=[_rule(), _undeclared(["curl -fsS https://x/health"])])
    row = _row(tmp_path, "G1")
    assert row["status"] == qa_audit.GAP
    assert "1 rule(s) SKIPPED on every Stop" in row["evidence"] and "rules[1] verb: curl" in row["evidence"]


def test_g1_an_undeclared_local_rule_runs_and_is_not_called_skipped(tmp_path):
    """CONFIG.md §19: a plain local command runs on Stop without `reach`. It is
    still a GAP (the standard wants it declared) but never reads as skipped."""
    _map(tmp_path, rules=[_undeclared(["python3 -m pytest tests -q"])])
    row = _row(tmp_path, "G1")
    assert row["status"] == qa_audit.GAP
    assert "SKIPPED" not in row["evidence"] and "run but declare no `reach`" in row["evidence"]


def test_g1_without_the_gate_classifier_is_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(qa_audit_env, "verify_record", None)
    _map(tmp_path, rules=[_undeclared(["pytest -q"])])
    assert _row(tmp_path, "G1")["status"] == qa_audit.UNKNOWN


def test_g1_unpriced_rule_is_a_gap(tmp_path):
    _map(tmp_path, rules=[_rule(seconds=True)])
    assert _row(tmp_path, "G1")["status"] == qa_audit.GAP


def test_g1_declared_rules_pass(tmp_path):
    _map(tmp_path, rules=[_rule(), _rule()])
    assert _row(tmp_path, "G1")["status"] == qa_audit.PASS


# --- G2 fire-and-forget (D2) ---------------------------------------------------------------

def test_g2_each_shape_that_cannot_fail_is_named():
    for cmd in ("curl -s https://x/health", "gh workflow run deploy.yml",
                "aws ssm send-command --document-name x", "./deploy.sh || true",
                "Copy-Item a b | Out-Null", "./deploy.sh | tee log", "./check.sh | grep -v ERROR"):
        assert qa_audit_env._fire_and_forget(cmd), cmd  # pylint: disable=protected-access


def test_g2_commands_that_can_fail_are_not_named():
    for cmd in ("curl -fsS https://x/health", "curl --fail https://x",
                "curl -sSf https://x/health | grep -q '\"ok\"'",
                "gh workflow run deploy.yml && gh run watch --exit-status",
                "set -o pipefail; ./deploy.sh | tee log", "pytest -q", "curl -F a=b -f https://x"):
        assert qa_audit_env._fire_and_forget(cmd) is None, cmd  # pylint: disable=protected-access


def test_g2_reads_environment_commands_too(tmp_path):
    _map(tmp_path, rules=[_rule()], environments={"qa": {"verify": ["curl https://qa/health"]}})
    row = _row(tmp_path, "G2")
    assert row["status"] == qa_audit.GAP and "environments.qa.verify" in row["evidence"]


def test_g2_a_clean_map_passes(tmp_path):
    _map(tmp_path, rules=[_rule(run=["curl -fsS https://x"])], default=["bash _verify/smoke.sh"])
    assert _row(tmp_path, "G2")["status"] == qa_audit.PASS


# --- G3 _verify scripts (D1) ---------------------------------------------------------------

def test_g3_the_shipped_template_is_a_gap(tmp_path):
    template = os.path.join(context._ROOT, "skills", "crew-setup", "templates",  # pylint: disable=protected-access
                            "_verify", "smoke.sh")
    with open(template, encoding="utf-8") as fh:
        _write(tmp_path, "_verify/smoke.sh", fh.read())
    row = _row(tmp_path, "G3")
    assert row["status"] == qa_audit.GAP
    for words in ("inherited ENV", "drops unknown flags", "zero checks"):
        assert words in row["evidence"], words


def test_g3_a_strict_script_passes(tmp_path):
    _write(tmp_path, "_verify/smoke.sh",
           'ENV=""\nwhile [ $# -gt 0 ]; do case "$1" in --env) ENV="$2"; shift 2 ;;\n'
           '  *) echo "unknown flag $1" >&2; exit 2 ;; esac; done\n'
           '[ -n "$ENV" ] || { echo "--env required" >&2; exit 2; }\n'
           'check() { local n="$1"; shift; "$@" || FAIL=$((FAIL+1)); }\n'
           'check "boots" curl -fsS "$BASE/health"\n')
    assert _row(tmp_path, "G3")["status"] == qa_audit.PASS


def test_g3_commented_out_checks_count_as_zero(tmp_path):
    _write(tmp_path, "_verify/smoke.sh", 'check() { "$@"; }\n# check "boots" curl -f x\n')
    assert "zero checks" in _row(tmp_path, "G3")["evidence"]


# --- G4 generated directories ----------------------------------------------------------------

def test_g4_an_unignored_untracked_build_dir_is_a_gap(tmp_path):
    _write(tmp_path, "README", "x")
    _git_init(tmp_path)
    _write(tmp_path, "node_modules/x.js", "x")
    row = _row(tmp_path, "G4")
    assert row["status"] == qa_audit.GAP and "node_modules/" in row["evidence"]


def test_g4_an_ignored_build_dir_passes(tmp_path):
    _write(tmp_path, ".gitignore", "node_modules/\n")
    _git_init(tmp_path)
    _write(tmp_path, "node_modules/x.js", "x")
    assert _row(tmp_path, "G4")["status"] == qa_audit.PASS


def test_g4_a_failed_ls_files_is_unknown_not_untracked(tmp_path, monkeypatch):
    _write(tmp_path, ".gitignore", "node_modules/\n")
    _git_init(tmp_path)
    _write(tmp_path, "node_modules/x.js", "x")
    real = qa_audit_env._git  # pylint: disable=protected-access

    def fake(root, *args):
        if args[0] == "ls-files":
            return subprocess.CompletedProcess(args, 128, "", "fatal: index file corrupt")
        return real(root, *args)
    monkeypatch.setattr(qa_audit_env, "_git", fake)
    assert _row(tmp_path, "G4")["status"] == qa_audit.UNKNOWN


def test_g4_outside_git_is_unknown(tmp_path):
    _write(tmp_path, "node_modules/x.js", "x")
    assert _row(tmp_path, "G4")["status"] == qa_audit.UNKNOWN


# --- G5 crew ignore block (D9) ---------------------------------------------------------------

def test_g5_a_bare_crew_dir_line_is_a_gap(tmp_path):
    _write(tmp_path, ".crew/config.json", "{}")
    _write(tmp_path, ".gitignore", ".crew/\n.work/\n")
    row = _row(tmp_path, "G5")
    assert row["status"] == qa_audit.GAP and "negation" in row["evidence"]


def test_g5_an_unreadable_gitignore_is_unknown_not_missing(tmp_path, monkeypatch):
    _write(tmp_path, ".crew/config.json", "{}")
    _write(tmp_path, ".gitignore", ".crew/*\n.crew/.approved-*\n.work/\n")
    _deny(monkeypatch, ".gitignore")
    row = _row(tmp_path, "G5")
    assert row["status"] == qa_audit.UNKNOWN and "could not read" in row["evidence"]


def test_g5_the_full_block_passes(tmp_path):
    _write(tmp_path, ".crew/config.json", "{}")
    _write(tmp_path, ".gitignore", ".crew/*\n!.crew/verify.json\n.crew/.approved-*\n.work/\n")
    assert _row(tmp_path, "G5")["status"] == qa_audit.PASS


# --- E1 data provenance (D4) -----------------------------------------------------------------

def test_e1_restored_without_scrub_is_a_gap(tmp_path):
    _map(tmp_path, environments={"qa": {"dataProvenance": "restored-from-prod"},
                                 "production": {"requireHuman": True}})
    row = _row(tmp_path, "E1")
    assert row["status"] == qa_audit.GAP and "scrub" in row["evidence"]


def test_e1_undeclared_is_a_gap_and_production_is_exempt(tmp_path):
    _map(tmp_path, environments={"dev": {}, "prod": {}})
    row = _row(tmp_path, "E1")
    assert row["status"] == qa_audit.GAP and "dev:" in row["evidence"] and "prod:" not in row["evidence"]


def test_e1_declared_provenance_passes(tmp_path):
    _map(tmp_path, environments={"dev": {"dataProvenance": "seeded"},
                                 "qa": {"dataProvenance": "restored-from-prod", "scrub": ["./scrub.sh"]}})
    assert _row(tmp_path, "E1")["status"] == qa_audit.PASS


# --- E2 rollback (D3) ------------------------------------------------------------------------

def test_e2_never_rehearsed_and_missing_keys_are_gaps(tmp_path):
    _write(tmp_path, "docs/rb.md", "last verified: never\n")
    _map(tmp_path, environments={"qa": {"rollback": "docs/rb.md"}, "dev": {},
                                 "x": {"rollback": "none"}})
    row = _row(tmp_path, "E2")
    assert row["status"] == qa_audit.GAP
    for words in ("never been rehearsed", "dev: no `rollback`", "no rollbackReason"):
        assert words in row["evidence"], words


def test_e2_a_stale_rehearsal_is_a_gap(tmp_path):
    old = (datetime.date.today() - datetime.timedelta(days=91)).isoformat()
    _write(tmp_path, "docs/rb.md", f"last verified: {old}\n")
    _map(tmp_path, environments={"production": {"rollback": "docs/rb.md"}})
    assert "91 days" in _row(tmp_path, "E2")["evidence"]


def test_e2_an_unreadable_runbook_is_unknown_not_missing(tmp_path, monkeypatch):
    _write(tmp_path, "docs/rb.md", f"last verified: {datetime.date.today().isoformat()}\n")
    _map(tmp_path, environments={"production": {"rollback": "docs/rb.md"}})
    _deny(monkeypatch, "rb.md")
    row = _row(tmp_path, "E2")
    assert row["status"] == qa_audit.UNKNOWN and "could not read runbook" in row["evidence"]


def test_e2_fresh_rehearsal_and_reasoned_none_pass(tmp_path):
    _write(tmp_path, "docs/rb.md", f"last verified: {datetime.date.today().isoformat()}\n")
    _map(tmp_path, environments={"production": {"rollback": "docs/rb.md"},
                                 "dev": {"rollback": "none", "rollbackReason": "rebuilt on push"}})
    assert _row(tmp_path, "E2")["status"] == qa_audit.PASS


# --- E3 deploy ref, E4 deploy workflows (D2) -------------------------------------------------

def test_e3_rev_parse_head_in_a_deploy_is_a_gap(tmp_path):
    _map(tmp_path, environments={"qa": {"deploy": ["gh workflow run d.yml -f ref=$(git rev-parse HEAD)"]}})
    assert _row(tmp_path, "E3")["status"] == qa_audit.GAP


def test_e3_an_explicit_sha_passes(tmp_path):
    _map(tmp_path, environments={"qa": {"deploy": ["./deploy.sh qa \"$PROMOTE_SHA\""]}})
    assert _row(tmp_path, "E3")["status"] == qa_audit.PASS


def test_e4_swallowed_exit_and_no_concurrency_are_gaps(tmp_path):
    _write(tmp_path, ".github/workflows/deploy.yml",
           "name: deploy\njobs:\n  d:\n    steps:\n    - run: robocopy a b || true\n")
    row = _row(tmp_path, "E4")
    assert row["status"] == qa_audit.GAP and "swallows" in row["evidence"] and "concurrency" in row["evidence"]


def test_e4_a_windows_built_ci_path_is_still_checked_for_concurrency(tmp_path):
    """On Windows, ci_files() builds `.github\\workflows\\deploy.yml`; E4 must still
    see it as a GitHub workflow (crew-windows-default found it skipped)."""
    text = "name: deploy\njobs:\n  d:\n    steps:\n    - run: ./deploy.sh\n"
    row = qa_audit_env.check_deploy_workflows(str(tmp_path), [(".github\\workflows\\deploy.yml", text)], [])
    assert row["status"] == qa_audit.GAP and ".github/workflows/deploy.yml: no `concurrency:`" in row["evidence"]


def test_e4_a_loud_deploy_workflow_passes(tmp_path):
    _write(tmp_path, ".github/workflows/deploy.yml",
           "name: deploy\nconcurrency: deploy-${{ inputs.env }}\njobs:\n  d:\n    steps:\n"
           "    - run: ./deploy.sh\n")
    assert _row(tmp_path, "E4")["status"] == qa_audit.PASS


def test_e4_no_ci_is_unknown(tmp_path):
    assert _row(tmp_path, "E4")["status"] == qa_audit.UNKNOWN


# --- E5 credential inventory (D4) ------------------------------------------------------------

def test_e5_environments_without_an_inventory_is_a_gap(tmp_path):
    _map(tmp_path, environments={"qa": {}})
    assert _row(tmp_path, "E5")["status"] == qa_audit.GAP


def test_e5_a_live_credential_reaching_qa_unaccepted_is_a_gap(tmp_path):
    _write(tmp_path, ".crew/secrets.md",
           "| Name | Reaches | Live | Accepted |\n|---|---|---|---|\n| PAY_KEY | qa, production | yes | |\n")
    row = _row(tmp_path, "E5")
    assert row["status"] == qa_audit.GAP and "PAY_KEY" in row["evidence"]


def test_e5_accepted_or_production_only_passes(tmp_path):
    _write(tmp_path, ".crew/secrets.md",
           "| Name | Reaches | Live | Accepted |\n|---|---|---|---|\n"
           "| PAY_KEY | production | yes | |\n| MAIL_KEY | qa | yes | accepted by Matthew 2026-10-01 |\n")
    assert _row(tmp_path, "E5")["status"] == qa_audit.PASS


def test_e5_an_inventory_without_the_columns_is_a_gap(tmp_path):
    _write(tmp_path, ".crew/secrets.md", "| Name | Where |\n|---|---|\n| K | vault |\n")
    assert "live" in _row(tmp_path, "E5")["evidence"]


_SECRETS_HEAD = "| Name | Reaches | Live | Accepted |\n|---|---|---|---|\n"


def _e5(root, *rows):
    _write(root, ".crew/secrets.md", _SECRETS_HEAD + "".join(r + "\n" for r in rows))
    return _row(root, "E5")


def test_e5_row_a_a_no_in_the_accepted_column_is_not_an_acceptance(tmp_path):
    row = _e5(tmp_path, "| A | prod, staging | yes | no |")
    assert row["status"] == qa_audit.GAP and "`A`" in row["evidence"] and "staging" in row["evidence"]


def test_e5_row_b_an_unknown_live_cell_is_unknown_not_pass(tmp_path):
    row = _e5(tmp_path, "| B | staging | ? | |")
    assert row["status"] == qa_audit.UNKNOWN and "`B`" in row["evidence"]


def test_e5_row_c_a_live_credential_with_a_blank_reach_is_unknown(tmp_path):
    row = _e5(tmp_path, "| C | | yes | |")
    assert row["status"] == qa_audit.UNKNOWN and "`C`" in row["evidence"]


def test_e5_row_d_tbd_live_is_unknown(tmp_path):
    row = _e5(tmp_path, "| D | staging | TBD | |")
    assert row["status"] == qa_audit.UNKNOWN and "`D`" in row["evidence"]


def test_e5_row_e_pending_is_not_an_acceptance(tmp_path):
    row = _e5(tmp_path, "| E | staging | yes | pending |")
    assert row["status"] == qa_audit.GAP and "`E`" in row["evidence"]


def test_e5_all_five_review_rows_together_are_a_gap_naming_the_unknowns(tmp_path):
    row = _e5(tmp_path, "| A | prod, staging | yes | no |", "| B | staging | ? | |", "| C | | yes | |",
              "| D | staging | TBD | |", "| E | staging | yes | pending |")
    assert row["status"] == qa_audit.GAP
    for name in ("`A`", "`B`", "`C`", "`D`", "`E`"):
        assert name in row["evidence"], name


def test_e5_affirmative_acceptances_and_explicit_no_pass(tmp_path):
    row = _e5(tmp_path, "| K1 | qa | yes | 2026-10-01 |", "| K2 | staging | y | accepted |",
              "| K3 | dev / qa | true | accepted by Matthew |", "| K4 | qa | Yes (rotated) | yes |",
              "| K5 | staging | no | |", "| K6 | production only | ? | |")
    assert row["status"] == qa_audit.PASS, row["evidence"]


def test_e5_a_live_reach_naming_no_environment_is_unknown(tmp_path):
    row = _e5(tmp_path, "| K | the vault | yes | |")
    assert row["status"] == qa_audit.UNKNOWN and "the vault" in row["evidence"]


def test_e5_a_declared_environment_name_is_read_as_nonproduction(tmp_path):
    _map(tmp_path, environments={"blue": {}, "green": {"requireHuman": True}})
    assert _e5(tmp_path, "| K | green | yes | |")["status"] == qa_audit.PASS
    assert _e5(tmp_path, "| K | blue | yes | |")["status"] == qa_audit.GAP


def test_e5_a_delivered_column_is_not_the_live_column(tmp_path):
    _write(tmp_path, ".crew/secrets.md", "| Name | Delivered | Reaches |\n|---|---|---|\n| K | yes | qa |\n")
    row = _row(tmp_path, "E5")
    assert row["status"] == qa_audit.GAP and "no live column" in row["evidence"]


def test_e5_production_only_is_production(tmp_path):
    assert qa_audit_env.parse_reach("production only", {}) == (["production"], [])
    assert qa_audit_env.parse_reach("`qa`/staging", {}) == (["qa", "staging"], [])


@pytest.mark.parametrize("value", [
    "no", "not accepted", "never", "denied", "rejected 2026-10-01", "declined", "pending", "TBD",
    "todo", "Nobody", "none", "n/a", "unknown", "awaiting owner", "waiting", "revoked", "expired",
    "withdrawn", "refused", "accepted but expired", "2026-10-01 not accepted", "-", "?", "",
    "accepted maybe", "accepted tentatively", "accepted conditionally", "accepted by Nobody",
    "accepted by Matthew Revoked", "Accepted, superseded", "accepted (lapsed)", "yes, disputed"])
def test_e5_a_refusal_anywhere_is_not_an_acceptance(tmp_path, value):
    row = _e5(tmp_path, f"| X | staging | yes | {value} |")
    assert row["status"] == qa_audit.GAP and "`X`" in row["evidence"], (value, row["evidence"])


@pytest.mark.parametrize("value", [
    "accepted unless rotated", "accepted if approved", "accepted until prod", "accepted soon",
    "yes eventually", "accepted (verbally)", "accepted by the owner on 2026-10-01", "\u2705", "approved",
    "ok", "y", "accepted?", "Matthew", "owner 2026-10-01", "accepted 2026-13-45",
    "accepted 2026-10-01 2026-10-02", "accepted by Ann Bea Cee Dee", "yes, ok-ish!",
    "accepted Matthew", "accepted, Matthew", "accepted 2026-10-01 Matthew Badali", "accepted O'Neil",
    "accepted Under Review", "accepted Re-voked", "accepted by Jos\u00e9", "accepted by matthew"])
def test_e5_an_unrecognised_acceptance_is_unknown_not_accepted(tmp_path, value):
    row = _e5(tmp_path, f"| X | staging | yes | {value} |")
    assert row["status"] == qa_audit.UNKNOWN and "`X`" in row["evidence"], (value, row["evidence"])


@pytest.mark.parametrize("value, want", [
    ("accepted Maybe", "GAP"), ("accepted Cancelled", "GAP"), ("accepted Rescinded", "GAP"),
    ("accepted Void", "GAP"), ("accepted Under Review", "UNKNOWN"), ("yes Draft", "GAP"),
    ("accepted Reject", "GAP"), ("accepted Revoke", "GAP"), ("accepted Expire", "GAP"),
    ("accepted by Nobody", "GAP"), ("accepted by Matthew Revoked", "GAP"),
    ("accepted Re-voked", "UNKNOWN")])
def test_e5_round_four_capitalised_qualifiers_never_pass(tmp_path, value, want):
    assert _e5(tmp_path, f"| X | staging | yes | {value} |")["status"] == want, value


@pytest.mark.parametrize("value", ["revoked", "withdrawn", "expired", "refused"])
def test_e5_accepted_followed_by_a_refusal_word_is_a_gap(tmp_path, value):
    row = _e5(tmp_path, f"| X | staging | yes | accepted {value} |")
    assert row["status"] == qa_audit.GAP, (value, row["evidence"])


@pytest.mark.parametrize("value", ["accepted", "yes", "ACCEPTED", "2026-10-01", "yes 2026-10-01",
                                   "accepted by Matthew", "Accepted by Matthew", "accepted. By Matthew",
                                   "Accepted by Matthew Badali 2026-10-01",
                                   "accepted 2026-10-01 by Matthew Badali", "yes, by Ann Lee",
                                   "accepted by O'Neil", "Accepted by Jean-Luc Picard",
                                   "**accepted** 2026-10-01", "accepted by Noah"])
def test_e5_the_affirmative_acceptance_forms_pass(tmp_path, value):
    row = _e5(tmp_path, f"| X | staging | yes | {value} |")
    assert row["status"] == qa_audit.PASS, (value, row["evidence"])


@pytest.mark.parametrize("value", [
    "accepted by Denise", "accepted by Denis Smith", "accepted by Deniz Yilmaz", "accepted by Staley",
    "accepted by Todorov", "accepted by Waite", "accepted by Lapsley", "accepted by Maybee",
    "accepted by Neverson", "accepted by Draftson", "accepted by Matthew N Badali",
    "accepted by Na-Young Kim", "accepted 2026-10-01 by Denise"])
def test_e5_a_name_that_starts_like_a_refusal_is_still_a_name(tmp_path, value):
    row = _e5(tmp_path, f"| X | staging | yes | {value} |")
    assert row["status"] == qa_audit.PASS, (value, row["evidence"])


@pytest.mark.parametrize("value, word", [
    ("accepted by Nobody", "nobody"), ("accepted by Pending", "pending"),
    ("accepted by Matthew Revoked", "revoked"), ("accepted by Ann Reject", "reject"),
    ("accepted Cancelled", "cancelled"), ("accepted by Denise, expired", "expired")])
def test_e5_a_refusal_names_the_word_that_refused(tmp_path, value, word):
    row = _e5(tmp_path, f"| X | staging | yes | {value} |")
    assert row["status"] == qa_audit.GAP, (value, row["evidence"])
    assert f"`X` acceptance refused by the word `{word}`" in row["evidence"], row["evidence"]


@pytest.mark.parametrize("value, word", [
    ("accepted by No One", "no"), ("accepted by No-one", "no"), ("yes by No", "no"),
    ("yes by No 2026-10-01", "no"), ("accepted by Noone", "noone"),
    ("accepted by Bob by Denise Revoked", "revoked"), ("accepted by Ann Retract", "retract"),
    ("accepted by Matthew Revoking", "revoking"), ("accepted by Ann Expires", "expires"),
    ("accepted by Bob Withdrew", "withdrew"), ("accepted by Ann Voided", "voided"),
    ("accepted by Terminated", "terminated"), ("accepted by Ann Revocation", "revocation"),
    ("accepted by Bob Lapses", "lapses"), ("accepted by Ann Denial", "denial")])
def test_e5_a_refusal_form_in_a_by_name_is_named(tmp_path, value, word):
    row = _e5(tmp_path, f"| X | staging | yes | {value} |")
    assert row["status"] == qa_audit.GAP, (value, row["evidence"])
    assert f"refused by the word `{word}`" in row["evidence"], row["evidence"]


@pytest.mark.parametrize("value", ["accepted by Matthew N Badali", "accepted by Na-Young Kim",
                                   "accepted by Noel", "accepted by Nora", "accepted by Denise",
                                   "accepted by Waite", "accepted by Staley", "accepted by Lapsley",
                                   "accepted by Draftson"])
def test_e5_names_near_the_new_forms_still_pass(tmp_path, value):
    row = _e5(tmp_path, f"| X | staging | yes | {value} |")
    assert row["status"] == qa_audit.PASS, (value, row["evidence"])


def test_e5_a_declared_hyphenated_environment_is_read(tmp_path):
    _map(tmp_path, environments={"staging-eu": {}})
    row = _e5(tmp_path, "| K | staging-eu | yes | |")
    assert row["status"] == qa_audit.GAP and "staging-eu" in row["evidence"]
    assert qa_audit_env.parse_reach("staging-eu", {}) == ([], ["staging-eu"])


@pytest.mark.parametrize("reach", ["not production", "not prod", "all but prod", "prod replica",
                                   "non-production", "prod except qa", "prod mirror", "like prod"])
def test_e5_a_qualified_reach_is_unknown_not_production(tmp_path, reach):
    row = _e5(tmp_path, f"| X | {reach} | yes | |")
    assert row["status"] == qa_audit.UNKNOWN and "`X`" in row["evidence"], (reach, row["evidence"])


@pytest.mark.parametrize("reach, names", [("production only", ["production"]),
                                          ("prod/staging", ["prod", "staging"]),
                                          ("prod + dev", ["prod", "dev"]),
                                          ("qa and staging", ["qa", "staging"])])
def test_e5_plain_reaches_still_parse(reach, names):
    assert qa_audit_env.parse_reach(reach, {}) == (names, [])


def test_e5_an_unparseable_map_is_unknown_not_na(tmp_path):
    _write(tmp_path, ".crew/verify.json", "{bad")
    row = _row(tmp_path, "E5")
    assert row["status"] == qa_audit.UNKNOWN and "environments map" in row["evidence"]


@pytest.mark.parametrize("cell, want", [("no", "no"), ("No.", "no"), ("no (live soon)", "unknown"),
                                        ("no, but real", "unknown"), ("yes (rotated)", "yes")])
def test_e5_a_no_with_trailing_text_is_unknown(cell, want):
    assert qa_audit_env.parse_live(cell.lower()) == want


def test_e5_an_unreadable_inventory_is_unknown(tmp_path, monkeypatch):
    _write(tmp_path, ".crew/secrets.md", _SECRETS_HEAD + "| K | qa | no | |\n")
    _deny(monkeypatch, "secrets.md")
    assert _row(tmp_path, "E5")["status"] == qa_audit.UNKNOWN


# --- E6 served verifiers, E7 CI parity (D5, D9) ----------------------------------------------

def test_e6_a_verifier_under_the_web_root_is_a_gap(tmp_path):
    _write(tmp_path, "public/verify_db.php", "<?php")
    _write(tmp_path, "public/index.php", "<?php")
    row = _row(tmp_path, "E6")
    assert row["status"] == qa_audit.GAP and "verify_db.php" in row["evidence"] and "index" not in row["evidence"]


def test_e6_a_clean_web_root_passes(tmp_path):
    _write(tmp_path, "public/index.php", "<?php")
    assert _row(tmp_path, "E6")["status"] == qa_audit.PASS


def test_e7_a_local_only_script_is_a_gap_until_declared(tmp_path):
    _write(tmp_path, ".github/workflows/ci.yml", "jobs:\n  t:\n    steps:\n    - run: pytest\n")
    _map(tmp_path, rules=[_rule(run=["bash _verify/smoke.sh"])])
    assert _row(tmp_path, "E7")["status"] == qa_audit.GAP
    _map(tmp_path, rules=[_rule(run=["bash _verify/smoke.sh"], localOnly=True)])
    assert _row(tmp_path, "E7")["status"] == qa_audit.NA


def test_e7_ci_running_the_script_passes_and_no_ci_is_unknown(tmp_path):
    _map(tmp_path, rules=[_rule(run=["bash _verify/smoke.sh"])])
    assert _row(tmp_path, "E7")["status"] == qa_audit.UNKNOWN
    _write(tmp_path, ".github/workflows/ci.yml", "jobs:\n  t:\n    steps:\n    - run: bash _verify/smoke.sh\n")
    assert _row(tmp_path, "E7")["status"] == qa_audit.PASS


# --- stamp and fleet -------------------------------------------------------------------------

def test_stamp_writes_head_and_refuses_without_crew(tmp_path):
    _write(tmp_path, "README", "x")
    _git_init(tmp_path)
    assert qa_audit.stamp(str(tmp_path)) is None
    _write(tmp_path, ".crew/config.json", "{}")
    sha = qa_audit.stamp(str(tmp_path))
    assert sha and (tmp_path / ".crew" / ".qa-audit-at").read_text(encoding="utf-8") == sha + "\n"


def test_stamp_outside_git_is_none(tmp_path):
    _write(tmp_path, ".crew/config.json", "{}")
    assert qa_audit.stamp(str(tmp_path)) is None
    assert not (tmp_path / ".crew" / ".qa-audit-at").exists()


def test_fleet_names_each_checkout_and_d10(tmp_path):
    a, b = tmp_path / "a", tmp_path / "group" / "b"
    _map(a, rules=[_undeclared(["bash -c 'make test'"])])
    _map(b, rules=[_rule(), _undeclared(["pytest -q"])])
    _write(b, ".crew/STATUS.md", "| Phase | State |\n|---|---|\n| 1 | done |\n| 5 | done |\n| 8 | todo |\n")
    out = qa_audit.fleet(str(tmp_path))
    line_a = next(ln for ln in out.splitlines() if ln.startswith("| a |"))
    line_b = next(ln for ln in out.splitlines() if "group" in ln)
    assert "YES" in line_a and "unknown" in line_a
    assert "| phase 5 |" in line_b and line_b.endswith("| no |")
