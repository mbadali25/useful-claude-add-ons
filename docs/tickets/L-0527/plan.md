# L-0527 plan (rush/h3-review)

Source: `d4f1e5bc` (reachable from main; `git diff 524da6a4 524da6a4^` is the split-out patch).
1. review_run.py: re-apply hunk by hunk onto main (main's `_err`, `resolve_executable`, job-object
   `launch`/`_launch`, L-0514's retry loop, L-0518's gated reserve, L-0522's preflight): kimi doc
   block, `EXIT_PROBE_CHANGED = 8`, fingerprint constants and functions, `graph_out`,
   `reviewer_changes`, `stop_survivors`, `launch(env=, started=)`, `model_launched`,
   `_probe_kimi`/`_run_kimi` (parser: `kimi_probe.final_message`, not a review_verdict copy), the
   probe before preflight in `run`, and `kimi` in LAUNCHED/PROVIDERS. A Kimi round returns before
   the retry loop: its probe and "before" fingerprint belong to one launch.
2. review_verdict.py unchanged: the parser stays in kimi_probe (no second copy).
3. review.md: the source's Kimi rows, re-based on main's text (exit 9, L-0514/L-0518 lines); 550 of
   551 lines.
4. Tests: test_review_run_kimi.py from the source (fake kimi from kimi_fixtures), test_kimi_docs
   review.md checks, test_worktree_config graph_out cases, test_provider_table's launch gate
   rewritten with kimi taken out of LAUNCHED as the stand-in.
5. sabotage_kimi.py from the source, re-anchored onto main (preflight `_err`, kimi_probe's round
   6/7 code; review_verdict entries retargeted to kimi_probe.final_message and test_kimi_stream);
   the SKILL.md entry dropped (SKILL.md is the follow-up feature PR); 8 owed entries added;
   registered in sabotage.py (+1 line, 3382 of 3400).
6. verify.json's Kimi rule widened; docs: README, TODO, code maps, kimi_fixtures/test_kimi_stream
   comments, external-tool-formats citations re-mapped.
