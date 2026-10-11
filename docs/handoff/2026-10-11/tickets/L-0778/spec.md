# L-0778: crew:reviewer as a Kimi dispatcher outside a reserved /crew:review round, and committed sabotage for L-0777          status: spec   risk: med
Written against origin/main after L-0777 (#600) merges. Direction: `direction.md`. Source: L-0777 (owner decision
2026-10-11, option A, an explicit exception to the 2026-10 crew feature freeze). Every path here except docs and tests
is HARNESS (`scripts/check-tooling-pr.py`), so this lands alone, with no feature work.

## Intent
L-0777 made `explorer`, `researcher` and `security` thin dispatchers to `crew_kimi_agent.py`. The reviewer follows
here. Dispatched ad hoc, `crew:reviewer` hands its review to `crew_kimi_agent.py --role reviewer` (routed by
`qa.roles.review`, family-guarded, with `--diff-base` for the bundle) and relays the answer on the same contract
(`KIMI OK` relay, `KIMI UNAVAILABLE` review itself and say `ran on claude (kimi: <state>)`, exit 8 or a
`crew-kimi-agent:` line stop). Inside a reserved `/crew:review` step 2c round it never dispatches: the round is
reserved as provider `claude`, so the ledger, the metrics row and auto-accept must see the provider that ran.
`/crew:review` step 2c tells it so with one fixed line, `CREW-REVIEW: reserved claude round - review this yourself;
do not dispatch to Kimi.`, sent before the byte-identical `prompt.txt` content (the line is the dispatch wrapper, not
part of the shared prompt, so the cross-provider invariant holds). L-0777's hand sabotage becomes committed entries
in a new `plugin/crew/tests/sabotage_kimi_agent.py`, registered in `sabotage.py`'s `MUTATIONS`.

## Exclusions
- No change to `crew_kimi_agent.py` behaviour (L-0787 owns its round-4 FIXes; L-0785, L-0786 their limits).
- No change to `review_run.py` / `review_ledger.py` (the coded BUDGET is L-0781's).
- No reviewer model or tool change in frontmatter (`opus`; `Read, Grep, Glob, Bash, Skill` already has Bash).
- No default pin: `qa.roles.review` stays unpinned in shipped config.

## Evidence
- `plugin/crew/hooks/scripts/crew_kimi_agent.py` `ROLE_PINS`/`REVIEWING` already route `reviewer` through
  `qa.roles.review` with the family guard (L-0777, tests `test_a_read_only_run_relays_the_answer[reviewer]`).
- `plugin/crew/commands/review.md` "Step 2c - Claude reviewer": reserve, dispatch `crew:reviewer`, parse.
- `plugin/crew/tests/sabotage_kimi.py` (`KIMI_MUTATIONS`) and `sabotage.py:215`/`:3079` (`MUTATIONS` sum): the
  committed sabotage shape `(label, target, find, replace, test)`.
- `.work/tickets/L-0777/notes.md`: the hand-sabotage tables for rounds 0-3.

## Unknowns
- U1: whether a Claude subagent reliably honours the `CREW-REVIEW:` line. Instruction-only, like L-0777's
  dispatchers (plugin agents ignore hooks); visible because a dispatched round would print `KIMI OK` first.

## Touch
- `plugin/crew/agents/reviewer.md`
- `plugin/crew/commands/review.md`
- `plugin/crew/tests/sabotage_kimi_agent.py`
- `plugin/crew/tests/sabotage.py`
- `plugin/crew/tests/**`
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/skills/crew-providers/alternative-providers.md`
- `plugin/PLUGINS.md`
- `docs/guides/crew/src/*.md`
- `docs/guides/crew/*.html`
- `docs/guides/crew/*.docx`
- `docs/guides/crew/*.pdf`
- `docs/diagrams/**`
- `.crew/codemap/**`
- `.claude/rules/**`
- `graphify-out/**`
- `CHANGELOG.md`
- `README.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

## Acceptance checks
- [ ] 1. `reviewer.md` carries the dispatch section and the L-0777 marker once; `crew_kimi_agent.role_instructions
  ("reviewer")` is the existing reviewer instructions, non-empty; the dispatch block uses the fresh-delimiter
  heredoc, quoted `--diff-base`/`--authors`, the exit-2 stop, and the `CREW-REVIEW:` rule (never dispatch).
- [ ] 2. `review.md` step 2c sends the `CREW-REVIEW:` line before the prompt and says it is outside `prompt.txt`.
- [ ] 3. `sabotage_kimi_agent.py` holds one entry per L-0777 guard (tree check after the run, explorer allowlist,
  probe skipped, `REVIEWING_DEV_ROLES` emptied, unavailable exit 0, empty authors as no conflict, probe-changed
  tree, unknown author source, unreadable config, one-line contract, base charset, known-family allowlist,
  settle after a failed probe, settle after the run, scratch cleanup), each anchor present exactly once
  (`test_every_shipped_anchor_is_present_in_its_target_exactly_once`), each naming a test that goes red.
- [ ] 4. Each new entry run through `sabotage.py`'s own runner turns its named test red (recorded).
- [ ] 5. Harness rule: `check-tooling-pr.py`, `scripts/_test/tooling-pr.py`, the golden replay, contracts,
  canary and the rest of `.crew/verify.json`'s harness rule green; `check-marketplace.py`, `check-crew-docs.py`.
