"""crew-qa-standards' environment (E*) and gate (G*) items (L-0618): one
must-GAP and one must-PASS case per item, plus the N/A and UNKNOWN cases that
keep "could not tell" from reading as a pass. Every repo is a throwaway
directory under tmp_path; the only process started is git, in that directory."""
import datetime
import json
import os
import subprocess

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

def test_g1_a_rule_without_reach_is_a_gap(tmp_path):
    rule = _rule()
    del rule["reach"]
    _map(tmp_path, rules=[_rule(), rule])
    row = _row(tmp_path, "G1")
    assert row["status"] == qa_audit.GAP and "SKIPPED" in row["evidence"] and "rules 1" in row["evidence"]


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


def test_g4_outside_git_is_unknown(tmp_path):
    _write(tmp_path, "node_modules/x.js", "x")
    assert _row(tmp_path, "G4")["status"] == qa_audit.UNKNOWN


# --- G5 crew ignore block (D9) ---------------------------------------------------------------

def test_g5_a_bare_crew_dir_line_is_a_gap(tmp_path):
    _write(tmp_path, ".crew/config.json", "{}")
    _write(tmp_path, ".gitignore", ".crew/\n.work/\n")
    row = _row(tmp_path, "G5")
    assert row["status"] == qa_audit.GAP and "negation" in row["evidence"]


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
           "| PAY_KEY | production | yes | |\n| MAIL_KEY | qa | yes | owner 2026-10-01 |\n")
    assert _row(tmp_path, "E5")["status"] == qa_audit.PASS


def test_e5_an_inventory_without_the_columns_is_a_gap(tmp_path):
    _write(tmp_path, ".crew/secrets.md", "| Name | Where |\n|---|---|\n| K | vault |\n")
    assert "live" in _row(tmp_path, "E5")["evidence"]


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
    rule = _rule()
    del rule["reach"]
    _map(a, rules=[rule])
    _map(b, rules=[_rule()])
    _write(b, ".crew/STATUS.md", "| Phase | State |\n|---|---|\n| 1 | done |\n| 5 | done |\n| 8 | todo |\n")
    out = qa_audit.fleet(str(tmp_path))
    line_a = next(ln for ln in out.splitlines() if ln.startswith("| a |"))
    line_b = next(ln for ln in out.splitlines() if "group" in ln)
    assert "YES" in line_a and "unknown" in line_a
    assert "| phase 5 |" in line_b and line_b.endswith("| no |")
