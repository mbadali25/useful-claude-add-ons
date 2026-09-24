"""The crew 1.0 web-testing (lane A) mutations, appended to `sabotage.py`'s
MUTATIONS. Kept apart for the reason the other `sabotage_*.py` files give:
`sabotage.py` sits near `.pylintrc`'s max-module-lines. Run that file, not
this one.

Each was also run by hand against the tracked file, restored from a scratch
copy with `cp` and confirmed with `diff`. The auth-leak and visual mutations
were additionally run against `_test/run-tests.sh` and `_test/webtest-guard.ps1`
(through `test_webtest_guard_pwsh.py`), and both drivers went red.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.join(CREW, "hooks", "scripts")
GUARD = os.path.join(_SCRIPTS, "webtest_guard.py")
SCAFFOLD = os.path.join(_SCRIPTS, "webtest_scaffold.py")
PROMPT = os.path.join(_SCRIPTS, "review_prompt.py")
PATCH = os.path.join(_SCRIPTS, "review_patch.py")
RUN = os.path.join(_SCRIPTS, "review_run.py")
MIGRATE = os.path.join(_SCRIPTS, "crew_migrate.py")
_T = "tests/test_webtest_guard.py::"
_S = "tests/test_webtest_scaffold.py::"

WEBTEST_MUTATIONS = (
    ("webtest: .fixme( is no longer a skip", GUARD,
     "    re.compile(r\"\\.(?:skip|fixme)\\s*\\(\"),\n",
     "    re.compile(r\"\\.(?:skip)\\s*\\(\"),\n",
     _T + "test_skips_blocks_a_skip_added_since_the_base"),
    ("webtest: an exclusion's text qualifier is ignored", GUARD,
     "    return any(path == rpath and (want is None or want in text) for rpath, want in rules)\n",
     "    return any(path == rpath for rpath, want in rules)\n",
     _T + "test_skips_blocks_when_the_exclusion_names_something_else"),
    ("webtest: an exclusion anywhere in the spec counts", GUARD,
     "for m in _EXCLUSION_RE.finditer(_section(text, \"Exclusions\"))]\n",
     "for m in _EXCLUSION_RE.finditer(text)]\n",
     _T + "test_skips_exclusion_outside_the_exclusions_section_does_not_count"),
    ("webtest: untracked spec files are not scanned", GUARD,
     "    for rel in untracked.splitlines():\n",
     "    for rel in []:\n",
     _T + "test_skips_blocks_a_skip_in_a_new_untracked_spec_file"),
    ("webtest: a git failure in skips collapses to no skips", GUARD,
     "    if diff is None or untracked is None:\n        return None\n",
     "    if diff is None or untracked is None:\n        return []\n",
     _T + "test_skips_outside_a_repository_is_unknown_not_a_pass"),
    ("webtest: a tracked .auth segment is not a leak", GUARD,
     "             if p and (\".auth\" in p.split(\"/\") or p in named)]\n",
     "             if p and p in named]\n",
     _T + "test_auth_leak_blocks_a_tracked_auth_file"),
    ("webtest: auth-leak's could-not-tell reads as a pass", GUARD,
     "        return EXIT_UNKNOWN, [\"webtest auth-leak: UNKNOWN",
     "        return EXIT_OK, [\"webtest auth-leak: UNKNOWN",
     _T + "test_auth_leak_outside_a_repository_is_unknown_not_a_pass"),
    ("webtest: visual off the pinned image reads as PASS", GUARD,
     "        return EXIT_SKIP, [f\"webtest visual: UNVERIFIED",
     "        return EXIT_OK, [f\"webtest visual: UNVERIFIED",
     _T + "test_visual_off_the_pinned_image_is_skipped_as_unverified"),
    ("webtest: a real visual run's 77 passes through as SKIP", GUARD,
     "    code = EXIT_OK if rc == 0 else EXIT_FINDING\n",
     "    code = rc\n",
     _T + "test_visual_inside_the_pinned_image_runs_and_reports_its_exit"),
    ("webtest: the review prompt hands skips over as excluded", PROMPT,
     "        tag = \"EXCLUDED\" if row.get(\"excluded\") else \"FINDING\"\n",
     "        tag = \"EXCLUDED\"\n",
     _T + "test_review_prompt_hands_open_skips_to_the_reviewer_as_findings"),
    ("webtest: review.json carries excluded rows as open", RUN,
     "    return [r for r in rows if isinstance(r, dict) and not r.get(\"excluded\")]\n",
     "    return [r for r in rows if isinstance(r, dict)]\n",
     _T + "test_review_json_carries_only_the_open_skip_rows"),
    ("webtest: the review manifest drops the artefact listing", PATCH,
     "        manifest[\"webtest\"] = listing\n",
     "        pass\n",
     _T + "test_review_patch_manifest_lists_the_web_artifacts"),
    ("webtest scaffold: an existing MCP server is overwritten", SCAFFOLD,
     "    added = [n for n in servers if n not in existing]\n",
     "    added = list(servers)\n",
     _S + "test_existing_files_and_servers_are_never_overwritten"),
    ("webtest scaffold: the dry run writes", SCAFFOLD,
     "        if args.apply:\n            _write(root, rel, text)\n",
     "        _write(root, rel, text)\n",
     _S + "test_dry_run_is_the_default_and_writes_nothing"),
    ("webtest scaffold: init-agents' .mcp.json rewrite is kept", SCAFFOLD,
     "    if before is not None and after != before:\n",
     "    if False:\n",
     _S + "test_init_agents_rewriting_mcp_json_is_undone_keeping_its_new_server"),
    ("webtest scaffold: agents regenerate over an existing planner", SCAFFOLD,
     "    if os.path.exists(os.path.join(root, AGENT_MARKER)):\n        return",
     "    if False:\n        return",
     _S + "test_agents_are_skipped_when_the_planner_exists"),
    ("migrate: pm.authority autonomous is dropped silently", MIGRATE,
     "    if isinstance(pm, dict) and pm.get(\"authority\") == \"autonomous\":\n",
     "    if False:\n",
     "tests/test_migrate.py::test_autonomous_pm_authority_is_noted_in_report_and_crew_json"),
    ("migrate: the autopilot note never reaches the report", MIGRATE,
     "        plan[\"notes\"].extend(crew.get(\"notes\", []))\n",
     "",
     "tests/test_migrate.py::test_autonomous_pm_authority_is_noted_in_report_and_crew_json"),
)
