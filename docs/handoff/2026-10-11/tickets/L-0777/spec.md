# L-0777: crew's explorer, researcher and security subagents dispatch to Kimi K3 through a thin dispatcher          status: spec   risk: med
Written against origin/main `c972653ad` (crew 1.2.20), 2026-10-11. Direction: `direction.md`.
Owner decision (Matthew, 2026-10-11, relayed by the lead): option A, the thin dispatcher. This is an explicit
exception to the 2026-10 crew feature freeze. The reviewer half is HARNESS and is L-0778.

## Intent
Claude Code's subagent `model` field takes only Claude models, so an agent cannot be pointed at Kimi by
frontmatter. Instead each of `explorer`, `researcher` and `security` becomes a thin dispatcher. It is a
Claude subagent whose first and only Bash call hands the task to a new script,
`plugin/crew/hooks/scripts/crew_kimi_agent.py`. The script runs the Kimi Code CLI read-only and prints the
answer. The dispatcher relays that answer verbatim. When Kimi cannot run, the dispatcher does the task itself
on Claude with the same role instructions and says so on its first line.

**`crew_kimi_agent.py --role explorer|researcher|security|reviewer --root DIR [--authors "fam ..."]
[--timeout S]`**, task text on stdin. The output is a contract, and its first line is machine-readable:
- exit 0: `KIMI OK: <role> ran on kimi <alias>`, then Kimi's final message with secrets redacted
  (`kimi_probe.redact`).
- exit 3: `KIMI UNAVAILABLE: <state> - <reason>`. Nothing was changed. States: `not-routed` (the role's pin
  is not `kimi`), `barred` (Kimi is the author's family), `author-unknown` (a reviewing role with no author
  family known), `not-installed`, `not-authenticated`, `rate-limited`, `unknown` (the probe's states),
  `timed-out`, `failed` (non-zero exit, a failed turn, or no final message), `too-large` (task over the cap).
  The dispatcher falls back to Claude.
- exit 8: `KIMI CHANGED THE TREE: <paths>`, or `KIMI TREE UNKNOWN: <reason>` when the tree could not be
  fingerprinted or a process Kimi left could not be stopped. The tree may no longer be what the caller
  handed over, so the dispatcher must stop and report, and must not fall back.
- exit 2: usage error (unknown role, stdin empty, unreadable config).

**Routing is config, not code.** The role is resolved through `crew_state.resolve_role` against
`crew_config.resolve_config(root)`: `dev.roles.explorer`, `dev.roles.researcher`, `dev.roles.security`, and
`qa.roles.review` for `reviewer` (used by L-0778). Only a resolved provider of `kimi` dispatches; the model
is the pin's (`k3`) or `dev.kimi.model` / `qa.kimi.model`. Shipped defaults are unchanged (no pin), so a
fresh install keeps all four on Claude and nobody without the Kimi CLI is routed to it. `/crew:model` offers
the pins. `crew_state.DEV_ROLE_KINDS` gains `explorer` and `researcher` so the report lists them.

**The security family block.** `security` and `reviewer` review code, so the guard that bars an author's
family applies to them. `crew_state.resolve_role` applies its step-1 family guard to `dev` roles named in a
new `REVIEWING_DEV_ROLES = ("security",)`, exactly as it does for `qa`. The script computes the author set as
`--authors` united with `crew_state.author_families(root, cfg)` (the dispatch record or the config). An
empty set for a reviewing role is `author-unknown`, never "no conflict". `barred` names the family.

**Read-only on Kimi.** `kimi -p` forces permission mode `auto`, so no flag makes it read-only. The same two
controls as `/crew:review` step 2e stand in, reused, not copied:
- an agent file per role (`kimi_probe.write_agent_file` gains `tools`/`disallowed` arguments; its default
  output stays byte-identical): explorer `Read, Grep, Glob`; researcher `Read, Glob, WebSearch, FetchURL`;
  security and reviewer `Read, Grep, Glob`; `disallowedTools: [Write, Edit, Bash]` on all four; an empty
  `--skills-dir`; and
- `review_run.tree_fingerprint` before the probe, after the probe and after the run, judged by
  `review_run.reviewer_changes` (graph.out and ignored IDE/crew-log paths set aside, as in a review), with
  `review_run.stop_survivors` run first.
The probe is `kimi_probe.probe` with `review_run._probe_runner`, before the run. stdin is closed,
the environment is `kimi_probe.kimi_env()`, the call has its own process group and a timeout (default
900 s), and it runs with cwd = the repo root. The scratch directory (agent file, prompt file) is a temp
directory outside the repo, removed afterwards.

**The prompt** is the role's instructions followed by the task. The instructions are the agent file's body
after the line `<!-- crew-kimi: role instructions -->`, so the Kimi prompt and the Claude fallback read the
same text. The task is capped at 64,000 characters. A prompt over `review_run.INLINE_PROMPT_LIMIT` is written
to the scratch directory and passed by pointer with `--add-dir <scratch>`, as `prompt_argument` does.

**The agent files.** `explorer.md`, `researcher.md`, `security.md` keep their models (`opus`, `sonnet`,
`sonnet`: `validate-prompts.py`'s `MODEL_TIER` is a design decision, and the fallback's quality is the
model's), and explorer and researcher gain `Bash` (needed to run the script). The body opens with a dispatch section: pass
the caller's task on stdin through a quoted heredoc, pass `--authors` for security, relay the output on exit
0, fall back on exit 3 and say `ran on claude (kimi: <state>)` on line 1, stop on exit 8 or 2. After the
marker comes the role's existing instructions. Explorer and researcher may use Bash for nothing else, on
either path; security's one dispatch call is its only Bash on the Kimi path, and on the Claude fallback it keeps
the read-only Bash it had before (amended after review round 1). Security's routing paragraph is rewritten for the new guard.

## Exclusions
- `plugin/crew/agents/reviewer.md`, `plugin/crew/commands/review.md` and the committed sabotage entries
  (`plugin/crew/tests/sabotage*.py`) are HARNESS (`scripts/check-tooling-pr.py`). They are L-0778, which lands
  alone after this. This PR sabotages by hand and records each mutation in `notes.md`.
- No `review_*.py` change: `review_run` is imported, never edited.
- No new hook. Narrowing the dispatchers' Bash to the one command is instruction-only here (plugin agents
  ignore `hooks`/`permissionMode`); an enforced guard would be a new blocking hook and is a follow-up.
- No Kimi MCP servers: explorer's `mcp__localgpu__*` and researcher's `mcp__context7__*` are Claude-path only.
- No shipped default changes; no pins written to any config by this PR.
- The stale `crew-providers/SKILL.md` "does not launch Kimi yet" line is PR #588's (L-0743), not this one.
- A session-wide gateway (`ANTHROPIC_BASE_URL`) is rejected (direction.md option C).

## Evidence
- https://code.claude.com/docs/en/sub-agents: `model` accepts `sonnet`, `opus`, `haiku`, `fable`, a full
  Claude model ID or `inherit`; plugin subagents ignore `hooks`, `mcpServers`, `permissionMode`.
- https://code.claude.com/docs/en/llm-gateway: `ANTHROPIC_BASE_URL` is session-wide; non-Claude routing
  unsupported.
- Kimi Code docs (llms-full.txt): `--prompt` cannot be used with `--yolo`, `--auto` or `--plan`; agent-file
  fields `tools`, `disallowedTools`; built-in `WebSearch`, `FetchURL`, `Bash`.
- `plugin/crew/hooks/scripts/review_run.py:17-44` (the Kimi launch and its controls), `:572`
  `tree_fingerprint`, `:732` `reviewer_changes`, `:824` `launch`, `:1046` `stop_survivors`, `:1352`
  `_probe_runner`, `:1368` `_probe_kimi`, `:1412` `_run_kimi`.
- `plugin/crew/hooks/scripts/kimi_probe.py:205-241` (`kimi_env`, `write_agent_file`, `read_only_flags`).
- `plugin/crew/hooks/scripts/crew_state.py:1195-1196` (role kinds), `:1400` `family`, `:1502` `resolve_role`,
  `:2564` `author_families`.
- `plugin/crew/agents/security.md` "You are not the family-independence check": the dev table resolves
  without the author family today.
- `plugin/crew/tests/agent_frontmatter_snapshot.json`: records `model` and `tools` for all four agents.

## Unknowns
- U1: whether Kimi's `WebSearch`/`FetchURL` are present in `-p` mode on this host (they need the host's
  search service; `~/.kimi-code/config.toml` has `moonshot_search`/`moonshot_fetch`). Answered by the live
  smoke check; if absent, researcher on Kimi answers without them and must say so.
- U2: Kimi K3's latency for an explorer question. Measured once in the live smoke check. The 900 s timeout
  is the backstop.
- U3: a dispatcher that ignores its instructions and does the work itself on Claude. Not enforceable by a
  plugin agent; the output's first line (`KIMI OK` relayed, or `ran on claude`) makes it visible.

## Touch
- `plugin/crew/hooks/scripts/crew_kimi_agent.py`
- `plugin/crew/hooks/scripts/kimi_probe.py`
- `plugin/crew/hooks/scripts/crew_state.py`
- `plugin/crew/hooks/scripts/crew_config.py`
- `plugin/crew/hooks/scripts/crew_config_menu.py`
- `plugin/crew/agents/explorer.md`
- `plugin/crew/agents/researcher.md`
- `plugin/crew/agents/security.md`
- `plugin/crew/tests/**`
- `plugin/crew/hooks/scripts/_test/**`
- `plugin/crew/commands/model.md`
- `plugin/crew/skills/crew-providers/SKILL.md`
- `plugin/crew/skills/crew-providers/alternative-providers.md`
- `plugin/crew/skills/crew-setup/SKILL.md`
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/PLUGINS.md`
- `plugin/README.md`
- `.crew/verify.json`
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
- `SECURITY.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

## Acceptance checks
- [ ] 1. must-block, tree check (fake kimi, exit 8, first line `KIMI CHANGED THE TREE` naming the path, no
  `KIMI OK` and no Kimi answer on stdout): a run that appends to a tracked file, writes an untracked file,
  chmods a tracked file, stages a change, commits, leaves a process that writes after it answered, and a
  probe that writes. A tree that cannot be fingerprinted is `KIMI TREE UNKNOWN`, exit 8.
- [ ] 2. must-allow (exit 0, `KIMI OK: <role> ran on kimi k3`, the answer relayed): a read-only run for each
  of the four roles; a write under graph.out and an ignored `.idea/` write are set aside.
- [ ] 3. KIMI UNAVAILABLE fallback (exit 3, the tree untouched, no answer): no `kimi` on PATH, probe 401,
  probe quota, probe garbage, run timeout, run exit 1, a failed turn, an empty final message, no pin
  (`not-routed`), a `codex` pin (`not-routed`), author family `kimi` (`barred`), a reviewing role with no
  author family (`author-unknown`), and a task over the cap (`too-large`). The reason never carries a
  secret (a bearer token in the error is redacted).
- [ ] 4. The launch: `-p`, `-m k3`, `--output-format stream-json`, the role's agent file with the exact
  allowlist and `disallowedTools: [Write, Edit, Bash]`, an empty skills dir, stdin closed, no `KIMI_MODEL_*`
  in the child's environment, cwd = root, the scratch directory removed afterwards. The default
  `write_agent_file` output is byte-identical to before (the review path is unchanged).
- [ ] 5. Family guard: `resolve_role(cfg, "dev", "security", author="kimi")` with a kimi pin is barred;
  `author="claude"` is not; `dev.roles.developer` is never barred by author; the `/crew:model` report lists
  `explorer` and `researcher` rows.
- [ ] 6. Agent files: the snapshot is updated deliberately (the new `Bash` grants); each of the
  three carries the marker once, the script extracts the text after it, and that text is non-empty;
  `test_agent_examples.py`, `test_role_ladder.py`, `test_role_write_guard.py`, `validate-prompts.py` green.
- [ ] 7. Sabotage by hand, each restored byte-identical and recorded in `notes.md` for L-0778: (i) the after-
  run tree comparison skipped; (ii) `Bash` in the explorer allowlist; (iii) the probe skipped; (iv)
  `REVIEWING_DEV_ROLES` emptied; (v) an unavailable state exiting 0; (vi) an empty author set read as no
  conflict; (vii) a probe-changed tree reported as unavailable instead of exit 8. Each turns at least one
  case red; one that stays green fails the ticket.
- [ ] 8. Gates: `python3 scripts/check-marketplace.py`, `scripts/check-tooling-pr.py` (no HARNESS path),
  `scripts/check-crew-docs.py`, `docs/guides/crew/src/build.py --check`, `config_reference.py --check`, the
  ruff no-new-findings check and pylint on the new script, and `python3 scripts/gate-runner.py`.
- [ ] 9. Live smoke, by hand, not CI: one real `crew_kimi_agent.py --role explorer` call on this repo with a
  machine pin to kimi `k3` answers `KIMI OK`, and the tree is unchanged. Its latency and whether WebSearch
  appeared for researcher are recorded in `notes.md`.
