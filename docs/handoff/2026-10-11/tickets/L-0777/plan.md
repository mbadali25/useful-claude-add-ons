# L-0777 plan - explorer, researcher and security dispatch to Kimi K3

Spec: `spec.md`. Base `origin/main` `c972653ad` (crew 1.2.20). No HARNESS or SEAM path is edited (checked
against `scripts/check-tooling-pr.py:58-95`); `review_run` is imported only. The reviewer half is L-0778.

Viability, researched before planning:
- `review_run.py` already launches Kimi read-only with a probe, an agent file and a tree fingerprint, and its
  helpers are module-level functions with no side effects at import, so the new script reuses them.
- `kimi_fixtures.fake_kimi_bin` fakes every probe state and every write shape the must-block list needs
  (`FAKE_KIMI_WRITES`, `_CHMOD`, `_LATE`, `_PROBE_WRITE`, `FAKE_KIMI_DUMP`).
- `resolve_role` already carries the family guard; extending it to one `dev` role is a one-branch change.

## Steps

### Step 1 - the security family block and the role kinds
Files: `plugin/crew/hooks/scripts/crew_state.py`, `plugin/crew/tests/test_kimi_agent_routing.py`
Test: `test_kimi_agent_routing.py` (spec check 5), red first. `test_provider_table.py`, `test_config_menu.py`,
`test_crew_config.py` stay green.
Risk: med. `REVIEWING_DEV_ROLES = ("security",)`; `resolve_role` step 1 runs for `kind == "dev"` when the
role is in it. `DEV_ROLE_KINDS` gains `explorer`, `researcher`; tests that enumerate rows may need them.

### Step 2 - the agent file takes a tool list
Files: `plugin/crew/hooks/scripts/kimi_probe.py`, `plugin/crew/tests/test_crew_kimi_agent.py`
Test: the default output is byte-identical (spec check 4); `test_kimi_probe.py`, `test_review_run_kimi.py`
stay green.
Risk: low. Keyword arguments with the current values as defaults; a per-role file name.

### Step 3 - `crew_kimi_agent.py`, test first
Files: `plugin/crew/hooks/scripts/crew_kimi_agent.py`, `plugin/crew/tests/test_crew_kimi_agent.py`
Test: `test_crew_kimi_agent.py`: must-block, must-allow, fallback and launch tables (spec checks 1-4), with
fake-kimi fixtures and throwaway repos under tmp_path; nothing calls the real CLI.
Risk: high. Order: resolve, family, probe (with before/after fingerprints), run, survivors, fingerprint,
parse, redact, print. Every unknown is its own state, never `KIMI OK`.

### Step 4 - the agent files
Files: `plugin/crew/agents/explorer.md`, `plugin/crew/agents/researcher.md`, `plugin/crew/agents/security.md`, `plugin/crew/tests/agent_frontmatter_snapshot.json`, `plugin/crew/tests/test_crew_kimi_agent.py`
Test: spec check 6; `test_agent_examples.py`, `test_role_ladder.py`, `test_role_write_guard.py`,
`hooks/scripts/_test/validate-prompts.py`.
Risk: med. The snapshot's `captured_from` is updated with the reason. The marker text is a constant the
script and the test share.

### Step 5 - sabotage by hand
Files: `plugin/crew/hooks/scripts/crew_kimi_agent.py`, `plugin/crew/hooks/scripts/crew_state.py`
Test: spec check 7's seven mutations, each red then restored; `git diff --stat` clean after each; recorded in
`.work/tickets/L-0777/notes.md`.
Risk: low. Delete the module's `__pycache__` after each restore (stale-pyc memory).

### Step 6 - docs, config surface, code map, diagrams
Files: `plugin/crew/commands/model.md`, `plugin/crew/hooks/scripts/crew_config_menu.py`, `plugin/crew/skills/crew-providers/SKILL.md`, `plugin/crew/skills/crew-providers/alternative-providers.md`, `plugin/crew/skills/crew-setup/SKILL.md`, `plugin/crew/README.md`, `plugin/crew/CONFIG.md`, `plugin/crew/BUDGETS.md`, `plugin/PLUGINS.md`, `plugin/README.md`, `.crew/verify.json`, `docs/guides/crew/src/*.md`, `docs/guides/crew/*.html`, `docs/guides/crew/*.docx`, `docs/guides/crew/*.pdf`, `docs/diagrams/**`, `.crew/codemap/**`, `.claude/rules/**`, `graphify-out/**`, `CHANGELOG.md`, `README.md`, `SECURITY.md`
Test: `build.py` then `--check`; `config_reference.py --check`; `scripts/check-crew-docs.py`;
`scripts/check-marketplace.py`; `crew_instructions.py rules --check`; the code map re-anchored.
Risk: low. README "Agents on Kimi" section (routing, read-only controls, fallback, limits, same-family note).

### Step 7 - gates, live smoke, review, version last
Files: `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `CHANGELOG.md`
Test: `python3 scripts/gate-runner.py` (heavy suites through heavy-run, `free -g` first); the live smoke
(spec check 9); `/crew:review` cross-family with `--authors claude` (Codex first, Kimi acceptable), at most 3
rounds; `/crew:done`.
Risk: med. Version: next free on origin/main right before merge (1.2.25 placeholder behind #584/#597/#598/
#599). Merge with `gh pr merge <n> --merge`, after #584 and #599 where they conflict.

## Successor plan after review round 2 (owner 3-round cap; coded budget 2)

Round 2 (Codex, last coded round) returned 4 BLOCK and 4 FIX; it is rejected for its BLOCKs. Lead decision
2026-10-11, relayed by the coordinator, under the owner's standing 3-round cap (memory review-round-cap-3):
one more round only, round 3 of 3 in total. Any BLOCK after it parks the ticket; an edge-case-only round is
accepted with follow-ups.

### Step 8 - round 2 BLOCKs, each with a committed must-block test and a hand sabotage
Files: `plugin/crew/agents/security.md`, `plugin/crew/hooks/scripts/crew_kimi_agent.py`, `plugin/crew/tests/test_crew_kimi_agent.py`, `plugin/crew/tests/kimi_fixtures.py`
Test: `test_crew_kimi_agent.py` new cases, red with each fix reverted.
Risk: med. (a) security.md quotes the base range (`git diff "$BASE...HEAD"` with BASE assigned in a
quoted literal), no bare `<base>` placeholder in shell. (b) the security dispatch feeds the working tree:
`git diff "$BASE"` (committed + unstaged) plus `git diff --cached` and the untracked file list, as
`/crew:review`'s bundle covers committed, staged, unstaged and untracked. (c) `--authors` names are
validated against the known families and lower-cased; an unknown name is a usage error (exit 2). (d) a
descendant that leaves the process group: after `KIMI OK` would print, the script waits a short settle and
fingerprints again, refusing on any change (exit 8); the remaining limit (a write later than the settle,
shared with `/crew:review` step 2e) is declared in the README and filed as a follow-up.

### Step 9 - round 2 FIXes
Files: `plugin/crew/hooks/scripts/crew_kimi_agent.py`, `plugin/crew/tests/test_crew_kimi_agent.py`
Test: new cases in `test_crew_kimi_agent.py`.
Risk: low. Unpinned reviewing role reports `not-routed` before `author-unknown`; the
config is read once (the checked text is the one resolved, or a nested pin type error is exit 2) where small,
else a follow-up; stdin is read with a bound (cap + 1 bytes, then `too-large`).

### Step 10 - docs, version, gates, round 3
Files: `plugin/crew/README.md`, `CHANGELOG.md`, `README.md`, `.crew/codemap/**`, `.claude/rules/**`, `plugin/crew/BUDGETS.md`, `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md`
Test: check-marketplace, check-crew-docs, gate-runner via heavy-run, round 3 (Codex), /crew:done.
Risk: low.

## Successor plan after review round 3 (owner grant 2026-10-11, past the 3-round cap)

Round 3 (Codex) returned 3 BLOCK, 4 FIX, 1 NIT and is rejected for its BLOCKs. Owner decision (Matthew, via
the lead): one more round only, round 4, final. Any BLOCK after it parks the ticket.

### Step 11 - round 3 BLOCKs, each with a committed must-block test and a hand sabotage
Files: `plugin/crew/agents/security.md`, `plugin/crew/hooks/scripts/crew_kimi_agent.py`, `plugin/crew/tests/test_crew_kimi_agent.py`, `plugin/crew/tests/kimi_fixtures.py`
Test: new cases in `test_crew_kimi_agent.py`, each red with its fix reverted.
Risk: med. (a) `--diff-base` accepts only a strict git-ref charset (letters, digits, `/ . _ -`, no leading
`-`, no `..`), checked before any git call; security.md tells the dispatcher to refuse to dispatch a base
outside that set (an apostrophe included) before the shell sees it. (b) every exit after the probe settles
and re-fingerprints before it prints, the probe-failure exit 3 included. (c) `--authors` takes only known
families (`KNOWN_FAMILIES`), an unknown name is exit 2.

### Step 12 - round 3 FIXes and NIT
Files: `plugin/crew/hooks/scripts/crew_kimi_agent.py`, `plugin/crew/tests/test_crew_kimi_agent.py`, `docs/diagrams/**`, `.crew/codemap/**`, `.claude/rules/**`, `plugin/crew/README.md`, `CHANGELOG.md`, `README.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md`
Test: new cases in `test_crew_kimi_agent.py`; diagram readability check.
Risk: low. An unreadable config path (a failed `stat`, not only a broken file) is exit 2; an `OSError` from
`review_patch.compute` is exit 2; the task keeps its leading indentation (only trailing newlines trimmed);
a scratch directory that cannot be removed is reported (exit 3 `failed`, never `KIMI OK`); the diagram
citations re-derived.
