# L-0709 direction - Hermetic tests, then a green main

Review plan item 1.1 (Phase 1 - Stop the leaks, effort S). Filed 2026-10-08 by the lead session ff540b63 on the owner's order; reserved in `.work/HANDOFF.md` (2026-10-08T05:08Z). Crew feature freeze applies until Phase 1 is merged and main is green for 7 days.

Artifact: [crew 1.2.0 review](https://claude.ai/artifact/Y7MZ712TKdtGvY6MRBMYsH) - "How we fix it", item 1.1. Local copy: `/tmp/claude-0/-repos-personal-useful-claude-add-ons/ff540b63-da69-4c5f-a510-94a4187fc844/scratchpad/crew-review.html`. Evidence reports: `scratchpad/eval/opus-eval.md`, `scratchpad/eval/codex-eval.md` (same scratchpad). Code citations are at origin/main `c25ef990`.

## Intent

Merge PR #545 (L-0704). Then add an autouse fixture to conftest.py that points HOME, XDG_*, CLAUDE_CONFIG_DIR and CLAUDE_PROJECT_DIR at tmp_path, and a meta-test that fails any test opening the real home directory. Quarantine timing flakes, each with a named owner.

## Why

- `plugin/crew/tests/test_crew_autopilot_status.py:228-230` (`_lines`) runs `crew_autopilot.py status` as a subprocess with the caller's real HOME, so it reads `~/.claude/crew/config.json` (`autopilot.mode=plan` on this host) and `test_status_mode_line_reads_off_by_default` fails (`.work/HANDOFF.md:36`; the review cites `:225`).
- `plugin/crew/tests/conftest.py:30-54` isolates the global config only in-process (`monkeypatch.setattr(crew_config/crew_state, "GLOBAL_CONFIG_PATH", ...)`); a spawned script re-derives the path from HOME.
- `plugin/crew/tests/test_review_checks.py:2245-2261` (`test_a_clean_linter_s_detached_leftover_is_ended`) is the timing flake that failed main's last red pytest-crew run; 3 of the last 6 pytest-crew runs on main failed (`scratchpad/eval/opus-eval.md:159-162`).
- The Stop hook is the most expensive place to find a non-hermetic test (`scratchpad/eval/opus-eval.md:123-125`).

## Files (from the plan)

plugin/crew/tests/conftest.py, test_crew_autopilot_status.py, test_review_checks.py:2261

## Done when

The Stop hook stops failing on this machine's config, and main's pytest-crew is green for 7 days.

## Dependencies and ownership

Depends on L-0704 / PR #545 (hermetic autopilot status test) merging first; this ticket is the suite-wide follow-through. Owned by the crew [8102fe] session.
