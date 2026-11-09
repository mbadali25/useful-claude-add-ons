"""`environments.preProduction` mutations, in `sabotage.py`'s tuple shape.

CLAUDE.md: a change that loosens a guard that can block needs a committed
must-block / must-allow suite (`test_preproduction.py`), sabotage-tested --
reintroduce each bug it should catch and confirm the suite goes red.

UNWIRED, as `ghdeploy_mutations.py` was before L-0650: `sabotage*.py` is in the
review harness (`HARNESS` in `scripts/check-tooling-pr.py`), and a harness
change lands alone, so the one-line registration in `sabotage.py` is a
harness-only follow-up. Until then run this family on its own with
`sabotage.py`'s own machinery:

    cd plugin/crew/tests && python3 -c "import sabotage, preproduction_mutations as m; \
        sabotage.MUTATIONS = m.PREPRODUCTION_MUTATIONS; raise SystemExit(sabotage.main())"

Each entry names the case that has to go red.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_S = os.path.join(CREW, "hooks", "scripts")
PRE = os.path.join(_S, "crew_preprod.py")
CFG = os.path.join(_S, "crew_config.py")
GUARD = os.path.join(_S, "cloud_guard.py")
_T = "tests/test_preproduction.py::"

PREPRODUCTION_MUTATIONS = (
    ("preProduction: one unlisted target no longer refuses the line", PRE,
     "        if entry is None:\n            return None\n        owners.append(entry)",
     "        if entry is None:\n            continue\n        owners.append(entry)",
     _T + "test_an_unlisted_production_target_is_still_refused[psql-listed-host-plus-unlisted-conn]"),
    ("preProduction: only the first matched target is checked", CFG,
     "crew_preprod.covers(matched, table)", "crew_preprod.covers(matched[:1], table)",
     _T + "test_an_unlisted_production_target_is_still_refused[psql-listed-host-plus-unlisted-conn]"),
    ("preProduction: only the last matched target is checked", CFG,
     "crew_preprod.covers(matched, table)", "crew_preprod.covers(matched[-1:], table)",
     _T + "test_an_unlisted_production_target_is_still_refused[ssh-listed-jump-through-unlisted]"),
    ("preProduction: a name matches by prefix, not exactly", PRE,
     "if key == lowered or key in entry[\"targets\"]:",
     "if key.startswith(lowered) or key in entry[\"targets\"]:",
     _T + "test_an_unlisted_production_target_is_still_refused[ssh-prefix-of-listed]"),
    ("preProduction: a listed host matches by prefix", PRE,
     "if key == lowered or key in entry[\"targets\"]:",
     "if key == lowered or any(key.startswith(t) for t in entry[\"targets\"]):",
     _T + "test_an_unlisted_production_target_is_still_refused[ssh-extension-of-listed]"),
    ("preProduction: a one-word reason is accepted", PRE,
     "len(reason.strip()) < MIN_REASON", "len(reason.strip()) < 0",
     _T + "test_a_malformed_entry_is_never_read_as_a_listing[short-reason]"),
    ("preProduction: a blank reason is accepted", PRE,
     "not isinstance(reason, str) or len(reason.strip())",
     "not isinstance(reason, str) and len(reason.strip())",
     _T + "test_a_malformed_entry_is_never_read_as_a_listing[reason-not-a-string]"),
    ("preProduction: a wildcard target is a valid name", PRE,
     'r"[*?\\[\\]\\s]"', 'r"[\\s]"',
     _T + "test_a_malformed_entry_is_never_read_as_a_listing[bare-star-target]"),
    ("preProduction: entries() trusts a block problem() rejects", PRE,
     "if not isinstance(block, dict) or problem(block):\n        return {}",
     "if not isinstance(block, dict):\n        return {}",
     _T + "test_a_malformed_entry_is_never_read_as_a_listing[short-reason]"),
    ("preProduction: a malformed entry no longer poisons the environments block", CFG,
     "        if pre_problem:\n            return pre_problem\n",
     "        if pre_problem:\n            pass\n",
     _T + "test_a_malformed_entry_makes_every_environment_unknown[wildcard-name]"),
    ("preProduction: a destroy rides the exemption", GUARD,
     '    if destroy != "no":\n        return "ask", (f"{head}, and this is a destroy',
     '    if destroy != "no" and klass != ENV_NONPROD:\n        return "ask", (f"{head}, and this is a destroy',
     _T + "test_terraform_beyond_the_listing_is_still_refused[destroy-listed]"),
    ("preProduction: the exemption is read from the machine file", CFG,
     'covers nothing."""\n    path = crew_common.repo_config_file(root, "config.json")',
     'covers nothing."""\n    path = GLOBAL_CONFIG_PATH',
     _T + "test_the_machine_file_cannot_supply_the_list"),
    ("preProduction: a refused line still reports an exemption", GUARD,
     'audits = audits if worst == "allow" else []', 'audits = audits',
     _T + "test_an_unlisted_production_target_is_still_refused[ssh-listed-plus-unlisted-same-line]"),
    ("preProduction: a nonProd glob's allow is claimed as an exemption", PRE,
     "    if entry is None or any(fnmatch.fnmatch(value.lower(), g.lower())\n                            for g in declared):",
     "    if entry is None:",
     _T + "test_a_name_the_nonprod_globs_already_cover_is_not_claimed"),
    # --- must-allow non-vacuity: an allow path broken the cases must catch
    ("preProduction: a listed name is no longer nonProd for terraform", PRE,
     'e["name"] for e in table.values()]', 'e["name"] for e in []]',
     _T + "test_a_listed_environment_applies_unattended_like_nonprod"),
    ("preProduction: a listed exact target is no longer covered", PRE,
     'key == lowered or key in entry["targets"]', 'key == lowered',
     _T + "test_a_listed_target_is_not_refused_as_production[psql-listed-db]"),
    ("preProduction: the use leaves no guard.log policy", GUARD,
     'crew_preprod.POLICY_PREFIX + ",".join(out["preProduction"]["names"])',
     '"none"',
     _T + "test_a_listed_target_is_not_refused_as_production[ssh-listed-target]"),
)
