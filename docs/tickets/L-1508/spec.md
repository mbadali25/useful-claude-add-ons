# L-1508: a tool is run the way it was found (no bare-name subprocess)          status: spec   risk: med
Written against origin/main `f1cace4a`. Owner-requested 2026-10-04 after two Windows bugs (T-0016 `_tmux_pane_pid`, T-0017 `_git_out`, the second fail-open).

## Intent
Every subprocess call in crew's hook scripts runs the executable that `shutil.which` resolves, so the program crew judges is the one the user's shell would run, on every OS. A tool that does not resolve is "could not tell" at a guard (refuse or block, never pass) and a named error elsewhere. A test fails the build when a new bare-name call appears.

## Slices
- **PR A (feature, `L-1508-build`):** the shared resolver, every non-harness call site in `plugin/crew/hooks/scripts/`, the lint test, and per-site Windows stub tests. The lint test's allowlist names the five harness files with "L-1508 PR B" as the reason.
- **PR B (harness-only, its own ticket id at build time):** the same swap in `completion_audit.py`, `crew_ticket.py`, `review_gate.py`, `review_prompt.py`, `verify_record.py`; removes their allowlist entries; sabotage entries for any guard whose answer changes. Lands alone (T-0087). `scripts/check-tooling-pr.py` must print `tooling-pr: OK`.

## Exclusions
- No change to *what* any tool is asked, only to which binary runs.
- No `shell=True` anywhere.
- Outside crew's hook scripts (owner decided 2026-10-04: option 1, see direction.md): the three `plugin/crew/skills/crew-qa-standards/scripts/` git sites (`qa_audit.py:331`, `qa_audit_env.py:273`, `qa_doc.py:45`) ARE fixed in PR A (same crew bump). `plugin/obsidian-vault/hooks/scripts/obsidian_common.py:857` (`ps`, macOS-only function) and `skills/notify/scripts/notifyd.py:264` (`tasklist.exe`, Windows-only) are allowlisted with those reasons, unchanged. `skills/repo-docs/scripts/git_changelog.py:71` is follow-up ticket L-1509 (its own bump). `skills/intune-graph/scripts/auth.py` already does it right (`_find_az`).
- Not the Windows test-skip audit (#399 F-A, native Python probing `/proc` to skip tests). That is its own concern; note it in the done report.

## Evidence (origin/main `f1cace4a`, read 2026-10-04)
Bare-name calls in `plugin/crew/hooks/scripts/`:
- git: `ci_receipt.py:128`, `:142`; `crew_instructions.py:292`; `crew_refresh_check.py:546`; `crew_status.py:49`; `crew_tracker.py:540`, `:979`; `event_claim.py:98`. Harness (PR B): `completion_audit.py:112`; `crew_ticket.py:204`; `review_gate.py:62`; `review_prompt.py:199`; `verify_record.py:585`, `:594`, `:634`.
- ps: `crew_autocycle.py:489` (inside `_proc`, which returns early when `os.name == "nt"`), `:682`.
- xdotool: `crew_autocycle.py:828` (`_xdotool`).
- ip: `crew_platform.py:126` (WSL2 default-route read).
- Already fixed on unmerged branches, land first: `crew_autocycle._tmux_pane_pid` (T-0016, merged in #396 as `cdb7b508`), `crew_autocycle._git_out` (T-0017, `9a34b335`, #356).
- Precedent: `skills/intune-graph/scripts/auth.py` `_find_az` docstring: "CreateProcess does not apply PATHEXT ... shutil.which does apply PATHEXT".
- `crew_status.py` is a `SEAM` path in `scripts/check-tooling-pr.py:89-95`: it may ride in PR A only with a `Tooling-seam: plugin/crew/hooks/scripts/crew_status.py` trailer, or move to PR B. Decide at plan time.

## Unknowns
- Whether `ps:682`, `xdotool:828` and `ip:126` are reachable on native Windows. Read each caller. Gated off Windows: allowlist with the gate's `path:line`. Reachable: resolve like git.
- Cost: `shutil.which` walks PATH on every call. Cache per process (a dict keyed by name), but never cache a miss across a PATH change within one process; tests that swap PATH must still see the stub.
- Whether any caller relies on `FileNotFoundError` from a missing tool. Each such site keeps an equivalent named error.

## Touch (PR A)
- `plugin/crew/hooks/scripts/crew_common.py` (resolver)
- the non-harness call sites listed above, plus the three crew-qa-standards scripts
- `plugin/crew/tests/test_tool_resolution.py` (new: the AST lint plus resolver unit tests)
- per-site tests where a guard reads the tool's answer (stub as `<name>` plus `<name>.cmd`, failing; must-block on every OS, the way `test_check_runs_the_git_which_resolves` does in #356)
- `plugin/crew/README.md` or CONFIG troubleshooting note, `CHANGELOG.md`, `.crew/verify.json` (rule for the new test, measured `seconds`), `.crew/codemap/**`, `.claude/rules/**`, version files

## Acceptance checks
1. `test_tool_resolution.py` scans every plugin and skill script. It fails on origin/main (lists every bare-name site), and passes after PR A with only the 5 harness files, justified POSIX- or Windows-gated sites (obsidian-vault `ps`, notify `tasklist`) and the repo-docs follow-up allowlisted, each with its reason.
2. Sabotage: add a bare `subprocess.run(["git", "status"])` to any non-allowlisted hook script and the lint goes red; remove an allowlist reason and it goes red.
3. Each guard that reads a tool (wrap-up veto, ci_receipt, crew_status, crew_tracker) has a test where the only failing tool is reachable through `shutil.which` but not by a bare name, and the guard refuses on every OS.
4. Windows CI green on PR A's own head (crew-windows-default, crew-windows-slow, crew-shell-matrix (windows-latest)) before it joins a landing batch.
5. `check-marketplace.py`, `crew_instructions.py rules --check`, `check-tooling-pr.py` (PR A: no harness path changed; PR B: `tooling-pr: OK`).
