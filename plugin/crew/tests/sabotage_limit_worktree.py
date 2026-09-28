"""The T-0088 mutations: the Codex limit fallback (`review_limit.py`,
`review_run.py --probe` and the mid-round marker) and the linked-worktree
config resolver (`crew_common.repo_config_dir` and the readers it feeds).
Same tuple shape as `sabotage.py`'s MUTATIONS -- (label, target, find,
replace, test) -- and appended to it there. Run `sabotage.py`, not this file.

Each one is a way the fallback could send a genuine failure to the
same-family reviewer (or keep spending rounds on a limited Codex), or a way a
lane worktree could read the wrong config: none, a merged one, or the main
checkout's over its own.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(CREW, "hooks", "scripts")
LIMIT = os.path.join(SCRIPTS, "review_limit.py")
RUN = os.path.join(SCRIPTS, "review_run.py")
COMMON = os.path.join(SCRIPTS, "crew_common.py")
PLATFORM = os.path.join(SCRIPTS, "crew_platform.py")
TICKET = os.path.join(SCRIPTS, "crew_ticket.py")
_L = "tests/test_review_limit.py::"
_W = "tests/test_worktree_config.py::"
_OWN_FIND = ('    if any(os.path.lexists(os.path.join(own, name)) for name in CONFIG_NAMES):\n'
             '        return own, SOURCE_OWN, ""\n')

LIMIT_WORKTREE_MUTATIONS = (
    ("limit_line never matches a limit", LIMIT,
     "            if _LIMIT_RE.search(line):\n",
     "            if False:\n",
     _L + "test_probe_limit_error_is_limited_and_reserves_nothing"),
    ("the 429 retry-limit pattern is dropped", LIMIT,
     '    r"exceeded retry limit, last status: 429",  # error.rs:661-673 (RetryLimit, 429)\n',
     "",
     _L + "test_limit_line_matches_every_cited_codex_limit_message[retry-429]"),
    ("the probe answers ok on a timeout", RUN,
     '        return PROBE_UNKNOWN, f"no answer within {timeout}s"\n',
     '        return PROBE_OK, "timed out"\n',
     _L + "test_probe_timeout_is_unknown_not_ok"),
    ("any probe failure is classed limited", RUN,
     '    line = review_limit.limit_line(error or "", stderr)\n    if line:\n'
     "        return PROBE_LIMITED, line\n",
     '    line = review_limit.limit_line(error or "", stderr) or (error or "failed")\n'
     "    if line:\n        return PROBE_LIMITED, line\n",
     _L + "test_probe_other_failure_is_failed_not_limited"),
    ("a mid-round limit is not recorded", RUN,
     '            review_limit.record(args.root, args.ticket, number, "codex", args.model, limit)\n',
     "            pass\n",
     _L + "test_limit_mid_round_is_recorded_and_next_probe_says_limited"),
    ("the marker's round check is dropped", LIMIT,
     '    if mark.get("round") != used:\n        return None\n',
     "    if False:\n        return None\n",
     _L + "test_recorded_limit_applies_to_the_next_round_only"),
    ("the resolver never inherits", COMMON,
     "        return main, SOURCE_MAIN, os.path.dirname(real_common)\n",
     '        return own, SOURCE_OWN, ""\n',
     _W + "test_linked_worktree_reads_main_checkout_config"),
    ("the main checkout wins over the worktree's own files", COMMON,
     _OWN_FIND,
     '    if False:\n        return own, SOURCE_OWN, ""\n',
     _W + "test_worktree_own_config_wins_and_is_never_merged"),
    ("own-ness checks config.json only", COMMON,
     _OWN_FIND,
     '    if any(os.path.lexists(os.path.join(own, name)) for name in ("config.json",)):\n'
     '        return own, SOURCE_OWN, ""\n',
     _W + "test_worktree_with_only_crew_json_does_not_inherit_config_json"),
    ("a git failure collapses to own", COMMON,
     "        return own, SOURCE_UNKNOWN, (\n",
     "        return own, SOURCE_OWN, (\n",
     _W + "test_git_failure_in_a_linked_worktree_is_unknown_not_own"),
    ("heal_config writes a default that shadows the inherited config", PLATFORM,
     "    if source == crew_common.SOURCE_MAIN:\n        return None, (",
     "    if False:\n        return None, (",
     _W + "test_heal_config_creates_nothing_in_an_inheriting_worktree"),
    ("configured_mode reads the raw path again", TICKET,
     '    path = crew_common.repo_config_file(top, "config.json")\n    data, state = _read_json(path)\n',
     '    path = os.path.join(top, ".crew", "config.json")\n    data, state = _read_json(path)\n',
     _W + "test_scope_mode_block_in_main_checkout_blocks_in_worktree"),
)
