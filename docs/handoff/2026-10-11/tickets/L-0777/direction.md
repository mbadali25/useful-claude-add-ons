# L-0777: move the four crew subagents from Claude to Kimi K3

Status: direction. Research and design by lane D, 2026-10-11.

**Owner decision (Matthew, 2026-10-11, relayed by the lead): option A, the thin dispatcher. This is an
explicit, logged exception to the 2026-10 crew feature freeze.**
Owner decision 2026-10-11: explorer, reviewer, researcher and security move from Claude to Kimi K3.
Their model is set today in `plugin/crew/agents/*.md` frontmatter (explorer `opus`, reviewer `opus`,
researcher `sonnet`, security `sonnet`).

**Freeze.** The 2026-10 crew feature freeze is in effect (no new crew features until review Phase 1,
L-0709..L-0713, lands and main is green 7 days). This is a new crew feature. It needs an explicit,
logged owner exception (as L-0765 / L-0768 / L-0772 got), or it waits.

## Findings

1. **Frontmatter cannot name Kimi.** Claude Code's subagent `model` field accepts `sonnet`, `opus`,
   `haiku`, `fable`, a full Claude model ID, or `inherit`; values are checked against
   `availableModels` and a blocked value falls back to the inherited model. Resolution order:
   per-invocation `model` parameter, then frontmatter, then `CLAUDE_CODE_SUBAGENT_MODEL`, then the
   main conversation's model. The frontmatter table has no provider or base-URL field.
   Source: https://code.claude.com/docs/en/sub-agents ("Choose a model", "Overriding the subagent
   model"). A mod's `agent.spawn` hook can replace the model, but only with another model value.
2. **Gateways are session-wide and unsupported for non-Claude models.** `ANTHROPIC_BASE_URL` points
   the whole Claude Code process at a gateway; there is no per-subagent endpoint. The docs state
   Anthropic "doesn't support routing Claude Code to non-Claude models through any gateway", and a
   gateway credential replaces the claude.ai subscription for every request.
   Source: https://code.claude.com/docs/en/llm-gateway.
3. **Plugin subagents ignore `hooks`, `mcpServers` and `permissionMode`** (same sub-agents page), so a
   plugin agent cannot narrow its own Bash; only `tools` and the plugin's `hooks/hooks.json` apply.
4. **Crew already drives Kimi as a process, for review only.** `review_run.py` launches
   `kimi -p ... -m <alias> --output-format stream-json --agent-file <scratch>/kimi-reviewer.md
   --skills-dir <scratch>/kimi-no-skills` (`plugin/crew/hooks/scripts/review_run.py:17`,
   `LAUNCHED = ("codex", "copilot", "kimi")` at `:263`), with `kimi_probe.py` run before the round
   (`ok`/`not-installed`/`not-authenticated`/`rate-limited`/`unknown`), `kimi_env()` stripping
   `KIMI_CODE_INFINITE_RETRY` and `KIMI_MODEL_*`, and `write_agent_file()` writing a
   Read/Grep/Glob-only agent with Write/Edit/Bash disallowed (`kimi_probe.py:205-241`). Because
   `kimi -p` forces permission mode `auto` (Kimi Code docs: "`--prompt` cannot be used with
   `--yolo`, `--auto`, or `--plan`"), the read-only controls are the tool allowlist plus a
   working-tree fingerprint before the probe and after the run (`/crew:review` step 2e,
   `commands/review.md:432`). A write outside the repo is caught by neither.
5. **Config and family already know Kimi.** `crew_state.DEV_PROVIDERS`/`QA_PROVIDERS` include
   `kimi`; `family("kimi", any)` is `kimi` (`crew_state.py:1400-1451`); `resolve_role` applies the
   family guard before a pin (`crew_state.py:1502`). Role kinds today: `QA_ROLE_KINDS = (phase1,
   smoke, review, gate)`, `DEV_ROLE_KINDS = (developer, security)`. `/crew:model` lists the offered
   Kimi pins (`commands/model.md:215`) - none for explorer/researcher.
6. **Kimi Code agent files** take `name`, `description`, `tools`, `disallowedTools`, `subagents`; no
   per-agent `model` (the model is `-m`). Built-in tools include `Read`, `Grep`, `Glob`, `Bash`,
   `WebSearch`, `FetchURL`; MCP tools match as `mcp__server__*` globs. This machine's
   `~/.kimi-code/config.toml` has `kimi-code/k3` and the `moonshot_search` / `moonshot_fetch`
   services (needed for researcher's web tools). No MCP servers are configured for Kimi, so
   explorer's `mcp__localgpu__*` and researcher's `mcp__context7__*` do not exist there.
   Source: https://moonshotai.github.io/kimi-code/en/customization/agents, llms-full.txt (Web Tools,
   Shell). Local: `kimi` 2.1.1 at `/root/.kimi-code/bin/kimi`. `/root/crew-tmp/kimi` is an empty
   directory.
7. **Stale doc found:** `skills/crew-providers/SKILL.md` "Kimi Code" section still says
   "`/crew:review` does not launch Kimi yet ... lands as L-0527", but `review_run.LAUNCHED` includes
   `kimi` and `review.md` step 2e launches it. Fix in this ticket's doc pass.

## Recommended design (option A): thin Claude dispatcher, Kimi does the work

Each of the four agent files stays (roster of 4 unchanged, same `crew:<name>` entry points, same
descriptions so proactive dispatch still works) but its body becomes a dispatcher:

- **Frontmatter:** `model: haiku` (or `sonnet`, see fallback), `tools: Bash, Read`. The dispatcher's
  only job is to write the task to a file and run
  `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_kimi_agent.py --role <name> --root . --task-file <f>`,
  then return the script's stdout verbatim.
- **New script `crew_kimi_agent.py`** (reuses `kimi_probe` - one parser, one env, one agent-file
  writer, extended to take a per-role tool list): resolve the role through `crew_state.resolve_role`
  (`dev.roles.explorer|researcher|security`, `qa.roles.review` for the reviewer); run
  `kimi_probe.probe` first; launch `kimi -p` with stdin closed, its own process group, a timeout,
  `kimi_env()`, `-m <k3 alias>`, an agent file holding the role's original instructions and tool
  allowlist, an empty `--skills-dir`; fingerprint the tree before and after (reuse
  `review_run.tree_fingerprint` / `reviewer_changes`) and report any change as a failed run naming
  the paths; read the final message via `kimi_probe.final_message`; redact before printing.
- **Per-role Kimi tool lists** (Bash dropped everywhere, because no Kimi flag makes Bash read-only
  and plugin agents cannot hook-narrow it):
  explorer `Read, Grep, Glob`; researcher `Read, Glob, WebSearch, FetchURL`;
  security `Read, Grep, Glob`; reviewer `Read, Grep, Glob` (as step 2e today).
  `disallowedTools: [Write, Edit, Bash]` on all four. Loses: explorer's localgpu semantic search and
  researcher's context7 (unless registered as Kimi MCP servers - a follow-up), and security's/
  reviewer's ability to run read-only commands (`git log`, `rg` with flags). The prompt must carry
  any git context the role needs (the review bundle already does).
- **Config, not hardcode:** routing lives in the role pins so `/crew:model` shows it and the family
  guard applies. Add `explorer` and `researcher` to `DEV_ROLE_KINDS` (security is there already).
  Ship defaults unchanged (`claude`); the owner's machine layer pins the four to `kimi` / `k3`. A
  default flip would route every installer's agents to a CLI they may not have.
- **Fallback when Kimi is unavailable** (probe not `ok`, exit non-zero, timeout, tree changed): the
  script prints one `KIMI UNAVAILABLE: <state> - <reason>` line and exits non-zero. The dispatcher
  then does the task itself on Claude with the original instructions, and its first line says
  `ran on claude (kimi: <state>)`. For that to be useful the dispatcher keeps the original tool set
  and runs on `sonnet`, not `haiku` - the price is a Sonnet turn per dispatch even when Kimi works
  (small: one Bash call and a relay). For the reviewer, the Claude fallback is the existing
  same-family path and must be announced and recorded as such (never auto-accept-eligible).
- **Reviewer and "never reviews its own session":** Kimi runs as a separate process with no access to
  the session's context, so session isolation is stronger than a subagent's. But a reviewer round
  must be recorded with its real provider, or the ledger, the metrics row and auto-accept
  (`review.md:507`, "reviewed by Codex or Kimi") are wrong. So the reviewer dispatcher must not run
  its own `kimi` call; it calls `review_run.py --provider kimi` (step 2e), which already reserves,
  probes, fingerprints and records. In practice "move the reviewer to Kimi" is: make Kimi the
  reviewer pin (`qa.roles.review` -> kimi `k3`, or put `kimi` first in `qa.order`), and redefine
  `crew:reviewer` as "step 2e's dispatcher, Claude only on fallback". Step 2c's wording changes.
- **Review-family logic:** with `family("kimi") == "kimi"`, a Kimi reviewer is BARRED on any diff a
  Kimi author wrote (`dev.roles.developer` on kimi, or a Kimi lane). `security` is today unguarded
  (it is a `dev` kind); it must become family-guarded the same way, or a Kimi security review of a
  Kimi-authored change is silently same-family.

## Note for the ticket: cross-family review after the move

Once moved, `crew:reviewer` and `crew:security` are same-family with any Kimi-authored work. For
those diffs cross-family review needs Codex (gpt) or Claude. With Claude authoring (the usual main
session), Kimi review is cross-family and auto-accept-eligible, which is an improvement over today's
Claude-on-Claude fallback. The memory rule "on a Codex limit prefer Kimi; Claude only with --authors
+ explicit --same-family" stays correct, but its Claude leg is now the only fallback for Kimi-authored
work when Codex is limited.

## Options for the owner

- **A (recommended): thin dispatcher + `crew_kimi_agent.py`, config-pinned, Claude fallback in the
  dispatcher, reviewer through step 2e.** Works on today's Claude Code; read-only enforced by Kimi's
  allowlist + tree fingerprint. Trade-off: drops Bash and the MCP tools from the four roles on Kimi;
  one Sonnet relay turn per dispatch; two PRs (feature: explorer/researcher/security + script;
  harness: reviewer.md + review.md, which are in `HARNESS` and must land alone).
- **B: script-only, no subagent.** Crew commands and the main session call `crew_kimi_agent.py`
  directly via Bash; the four agent files stay Claude as the fallback. Trade-off: smallest code and
  no relay turn, but the proactive `crew:explorer` etc. entry points keep running on Claude, so most
  real dispatches do not move - it does not deliver the owner's decision.
- **C: session-wide gateway** (`ANTHROPIC_BASE_URL` to a Kimi Anthropic-compatible endpoint). No crew
  code. Trade-off: moves the whole session, not four agents; explicitly unsupported by Anthropic for
  non-Claude models; replaces the subscription credential. Not viable.
- **D: defer to after the freeze.** File stays at direction. Trade-off: nothing moves now; no risk to
  the Phase 1 review work.

## Touch (if A is chosen)

`plugin/crew/agents/{explorer,researcher,security,reviewer}.md`; new
`plugin/crew/hooks/scripts/crew_kimi_agent.py`; `kimi_probe.py` (agent file takes a tool list);
`crew_state.py` (`DEV_ROLE_KINDS`, family guard for `security`); `commands/review.md` step 2c/2e;
`commands/model.md`; `skills/crew-providers/SKILL.md` (incl. the stale L-0527 line); README,
CONFIG, `plugin/PLUGINS.md` row, `docs/guides/crew/src/*` + rebuilt outputs, `.crew/codemap/`,
diagrams; both version files.

Tests: `plugin/crew/tests/agent_frontmatter_snapshot.json` (records model + tools for all four),
`test_agent_examples.py`, `test_role_ladder.py`, `test_review_fallback_bundle.py`,
`evals/qa-reviewer-stays-read-only/`; new `test_crew_kimi_agent.py` with fake-`kimi` fixtures
(`kimi_fixtures.py`) covering probe states, timeout, tree-changed, redaction, fallback line;
sabotage entries (drop the fingerprint, allow Bash in the agent file, skip the probe) that must go
red. Harness rule: the reviewer half runs `check-tooling-pr.py`, its suite, the golden replay and
the canary review.
