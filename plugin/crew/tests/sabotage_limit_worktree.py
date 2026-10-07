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
     ('    line = review_limit.limit_line(error or "", stderr)\n    if line:\n'
     "        return PROBE_LIMITED, line\n"),
     ('    line = review_limit.limit_line(error or "", stderr) or (error or "failed")\n'
     "    if line:\n        return PROBE_LIMITED, line\n"),
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
     "        return main, SOURCE_MAIN, main_root\n",
     '        return own, SOURCE_OWN, ""\n',
     _W + "test_linked_worktree_reads_main_checkout_config"),
    ("the main checkout wins over the worktree's own files", COMMON,
     _OWN_FIND,
     '    if False:\n        return own, SOURCE_OWN, ""\n',
     _W + "test_worktree_own_config_wins_and_is_never_merged"),
    ("own-ness checks config.json only", COMMON,
     _OWN_FIND,
     ('    if any(os.path.lexists(os.path.join(own, name)) for name in ("config.json",)):\n'
     '        return own, SOURCE_OWN, ""\n'),
     _W + "test_worktree_with_only_crew_json_does_not_inherit_config_json"),
    ("a git failure collapses to own", COMMON,
     "        return own, SOURCE_UNKNOWN, problem\n",
     "        return own, SOURCE_OWN, problem\n",
     _W + "test_git_failure_in_a_linked_worktree_is_unknown_not_own"),
    ("heal_config writes a default that shadows the inherited config", PLATFORM,
     "    if source == crew_common.SOURCE_MAIN:\n        return None, (",
     "    if False:\n        return None, (",
     _W + "test_heal_config_creates_nothing_in_an_inheriting_worktree"),
    ("configured_mode reads the raw path again", TICKET,
     '    path = crew_common.repo_config_file(top, "config.json")\n    data, state = _read_json(path)\n',
     '    path = os.path.join(top, ".crew", "config.json")\n    data, state = _read_json(path)\n',
     _W + "test_scope_mode_block_in_main_checkout_blocks_in_worktree"),
    # Review round 1 (T-0088): each FIX, then its neighbouring case.
    ("heal_config writes a default when git could not tell", PLATFORM,
     "    if source == crew_common.SOURCE_UNKNOWN:\n        return None, (",
     "    if False:\n        return None, (",
     _W + "test_heal_config_creates_nothing_when_git_could_not_tell"),
    ("the resolver passes --path-format again", COMMON,
     '    out = git_out(root, "rev-parse", "--git-dir", "--git-common-dir")\n',
     ('    out = git_out(root, "rev-parse", "--path-format=absolute", "--git-dir", '
     '"--git-common-dir")\n'),
     _W + "test_resolver_works_on_a_git_without_path_format"),
    ("an unwritable marker escapes the round", RUN,
     "        except OSError as exc:\n            then = (",
     "        except ValueError as exc:\n            then = (",
     _L + "test_unwritable_limit_marker_still_finishes_the_round"),
    ("the marker goes back beside the ledgers", LIMIT,
     ('    return os.path.join(review_ledger.common_dir(root), "crew", MARKER_DIR,\n'
     '                        review_ledger.check_ticket(ticket) + ".json")\n'),
     ('    return os.path.join(review_ledger.common_dir(root), "crew", "review",\n'
     '                        review_ledger.check_ticket(ticket) + ".limit.json")\n'),
     _L + "test_limit_marker_is_not_listed_as_a_review_ledger"),
    ("the marker overwrites a dotted ticket's ledger", LIMIT,
     ('    return os.path.join(review_ledger.common_dir(root), "crew", MARKER_DIR,\n'
     '                        review_ledger.check_ticket(ticket) + ".json")\n'),
     ('    return os.path.join(review_ledger.common_dir(root), "crew", "review",\n'
     '                        review_ledger.check_ticket(ticket) + ".limit.json")\n'),
     _L + "test_a_ticket_named_like_a_marker_keeps_its_own_ledger"),
    ("the marker's shape check is dropped", LIMIT,
     ("    if not isinstance(number, int) or isinstance(number, bool) \\\n"
     "            or not isinstance(error, str) or not error.strip():\n"),
     "    if False:\n",
     _L + "test_malformed_limit_marker_falls_back_to_a_live_probe"),
    ("a round of true passes for round 1", LIMIT,
     "    if not isinstance(number, int) or isinstance(number, bool) \\\n",
     "    if not isinstance(number, int) \\\n",
     _L + "test_malformed_limit_marker_falls_back_to_a_live_probe[round-true]"),
    ("status says nothing about a shadowed main config", COMMON,
     ("    shadowed = shadowed_main_config(root)\n    if shadowed:\n"
     "        return shadow_note(shadowed)\n"),
     "",
     _W + "test_status_names_the_main_config_a_worktree_own_config_shadows"),
    ("a shadow is reported when the main checkout has no config", COMMON,
     ("    if any(os.path.lexists(os.path.join(main, name)) for name in CONFIG_NAMES):\n"
     "        return main\n"),
     "    if True:\n        return main\n",
     _W + "test_status_has_no_shadow_line_when_nothing_is_shadowed[worktree-main-has-none]"),
)

# L-0681: the T-0096 family's mutations (the bash resolver, the cloud guard's
# no-python fallback) and this slice's readers (the verify gate in both
# flavours, the review gate's twin, the fingerprint, the scope wrappers'
# no-python proof). Each is a way a lane reads the wrong layer.
COMMON_SH = os.path.join(SCRIPTS, "_common.sh")
CLOUD_SH = os.path.join(SCRIPTS, "cloud-guard.sh")
GATE_SH = os.path.join(SCRIPTS, "verify-gate.sh")
GATE_PS1 = os.path.join(SCRIPTS, "verify-gate.ps1")
SCOPE_SH = os.path.join(SCRIPTS, "scope-guard.sh")
SCOPE_PS1 = os.path.join(SCRIPTS, "scope-guard.ps1")
AUDIT_SH = os.path.join(SCRIPTS, "completion-audit.sh")
REVIEW_GATE = os.path.join(SCRIPTS, "review_gate.py")
FINGERPRINT = os.path.join(SCRIPTS, "verify_fingerprint.py")
_S = "tests/test_worktree_config_shell.py::"
_G = "tests/test_review_gate.py::"
_UNKNOWN_IS_PROOF = ('  [ "$CREW_CFG_SOURCE" = unknown ] && return 1\n'
                     '  local cfg="$CREW_CFG_DIR/config.json"\n')

L0681_MUTATIONS = (
    ("the bash resolver reads a .git file as own", COMMON_SH,
     '  [ -f "$root/.git" ] || return 0\n  CREW_CFG_SOURCE=unknown\n',
     "  return 0\n  CREW_CFG_SOURCE=unknown\n",
     _S + "test_bash_resolver_agrees_with_python[lane-no-config]"),
    ("the bash resolver prefers the main checkout over own", COMMON_SH,
     '  for n in crew.json config.json; do\n'
     '    { [ -e "$root/.crew/$n" ] || [ -L "$root/.crew/$n" ]; } && return 0\n  done\n',
     "",
     _S + "test_bash_resolver_agrees_with_python[lane-own-config]"),
    ("the cloud guard reads unknown as not armed", CLOUD_SH,
     '  [ "$CREW_CFG_SOURCE" = unknown ] && return 0\n',
     "",
     _S + "test_cloud_guard_without_python_is_armed_when_git_cannot_tell[sh]"),
    ("scope-guard.sh reads unknown as provably off", SCOPE_SH,
     _UNKNOWN_IS_PROOF, '  local cfg="$CREW_CFG_DIR/config.json"\n',
     _S + "test_scope_wrapper_without_python_blocks_when_git_cannot_tell[scope-guard.sh]"),
    ("completion-audit.sh reads unknown as provably off", AUDIT_SH,
     _UNKNOWN_IS_PROOF, '  local cfg="$CREW_CFG_DIR/config.json"\n',
     _S + "test_scope_wrapper_without_python_blocks_when_git_cannot_tell"
     "[completion-audit.sh]"),
    ("scope-guard.sh proves off from the own file again", SCOPE_SH,
     '  crew_repo_config_dir "${CLAUDE_PROJECT_DIR:-$PWD}"\n',
     '  CREW_CFG_DIR="${CLAUDE_PROJECT_DIR:-$PWD}/.crew" CREW_CFG_SOURCE=own\n',
     _S + "test_scope_wrapper_without_python_blocks_in_a_lane_whose_main_checkout_has_a"
     "_config[scope-guard.sh]"),
    ("scope-guard.ps1 reads unknown as provably off", SCOPE_PS1,
     "  if ($repoCfg.Source -eq 'unknown') { return $false }\n",
     "",
     _S + "test_scope_wrapper_without_python_blocks_when_git_cannot_tell[scope-guard.ps1]"),
    # The pair split: review_gate.py routed, verify-gate.sh back on its own file.
    ("verify-gate.sh reads its own stand-down while review_gate.py is routed", GATE_SH,
     'CREW_REPO_CONFIG="$CREW_CFG_DIR/config.json"\n',
     'CREW_REPO_CONFIG=".crew/config.json"\n',
     _G + "test_a_lane_inherits_the_main_checkouts_stand_down[sh]"),
    ("review_gate.py reads its own stand-down while the gate is routed", REVIEW_GATE,
     '        config = _read(crew_common.repo_config_file(root, "config.json"))\n',
     '        config = _read(os.path.join(root, ".crew", "config.json"))\n',
     _G + "test_a_lane_inherits_the_main_checkouts_stand_down[sh]"),
    ("verify-gate.ps1 reads its own config", GATE_PS1,
     "$repoConfig = Join-Path (Get-CrewRepoConfigDir $root).Dir 'config.json'\n",
     "$repoConfig = Join-Path $root '.crew/config.json'\n",
     _G + "test_a_lane_inherits_the_main_checkouts_stand_down[ps1]"),
    ("the fingerprint hashes the own config", FINGERPRINT,
     '        path = (crew_common.repo_config_file(root, "config.json") if rel == _CONFIG\n',
     '        path = (os.path.join(root, ".crew", "config" + ".json") if rel == _CONFIG\n',
     _S + "test_fingerprint_follows_the_resolved_config"),
)

LIMIT_WORKTREE_MUTATIONS += L0681_MUTATIONS
