---
title: Confirming recall reaches your sessions
guide: crew 1.0, Memory and Obsidian (companion)
date: 2026-09-23
---

# Confirming recall reaches your sessions

crew's context hook (`plugin/crew/hooks/scripts/crew_context.py`) puts two kinds of memory into a
session: **code-map slices** from `.crew/codemap/`, and **vault recall** from the Obsidian vaults
`obsidian-vault` manages. This page shows how to prove, on your own machine, that recall reaches the
main session *and* the subagents it dispatches, and that the model actually uses it.

## Which channel reaches which agent

Measured on Claude Code 2.1.281 on 2026-09-23 with a canary per hook event (one `claude -p` run,
Haiku, a `general-purpose` subagent told to report what was in its context without using tools):

| Hook event | Reaches the main agent | Reaches a subagent |
|---|---|---|
| `SessionStart` | yes | **no** |
| `UserPromptSubmit` | yes | **no** |
| `SubagentStart` | n/a | **yes** |

The subagent's verbatim answer in that run: `Harbour colour: UNKNOWN`, `Orchard number: UNKNOWN`,
`Lighthouse keeper name: OSWIN-TARRANT-92`, where only the last came from `SubagentStart`. So crew
registers the hook on `SubagentStart` as well. That event's payload names the agent (`agent_id`,
`agent_type`) but does not include the task, so the hook reads the task back from the parent
transcript's latest `Agent` tool call. Commands that write a subagent prompt themselves can also
paste in a slice:

```bash
python3 "<crew plugin root>/hooks/scripts/crew_context.py" --slice-for-subagent \
  --query "<the task text>" --paths <files the task touches>
```

## Where recall comes from

- The vaults and their roles come from `~/.claude/obsidian/config.json`. Each vault has a `role`:
  `primary`, `recall` or `ignore`. A vault with no role is `primary` if it is the default and
  `recall` otherwise. crew **never** asks an `ignore` vault, even if the repo lists it.
- A repo can set its own order in its crew config: `memory.recall.vaults` (an ordered list of names)
  and `memory.recall.maxChars` (default 800). Snippets come back in that vault order first, then in
  the order the search ranked them.
- crew calls obsidian-vault's read-only CLI:
  `vault_ops.py recall --query ... --vaults a,b --max-chars N --json`. If the plugin is missing, or
  the CLI fails, times out or prints something other than JSON, the session goes on without recall
  and the log records a miss with the reason.
- Every recall line starts with the vault's name: `- [vault:<name>] <note path>: <text>`. Any snippet
  the CLI returns without a vault name is dropped.

## The seeded-note proof

1. Make a scratch vault holding one note whose wording appears nowhere else, for example
   `notes/tidewater-ledger.md`: "The Tidewater ledger reconciliation cutoff is 03:17 Kestrel time,
   and the approving steward is Marisol Quennell-Vantage."
2. Add that vault to your obsidian config with `"role": "recall"`. For a dry run that leaves the real
   config alone, write a copy and point `CREW_OBSIDIAN_CONFIG` at it.
3. In a scratch project that has a `.crew/` directory, register crew's hook in
   `.claude/settings.json` for `SessionStart`, `UserPromptSubmit` and `SubagentStart`. Use the
   command `bash "<crew plugin root>/hooks/scripts/crew-context.sh"`. `crew_instructions.py
   claude-hooks` prints the full set of entries.
4. Start a fresh session and ask for a subagent that may not use tools:

   ```bash
   claude -p --model haiku --output-format stream-json --verbose --include-hook-events \
     "Use the Task tool once with exactly this prompt: 'Without using any tools, answer only from \
   your context: what is the Tidewater ledger reconciliation cutoff, and who is the approving \
   steward? If it is not in your context, answer UNKNOWN. Name the source label.' Then reply with \
   the subagent's answer verbatim."
   ```

**What success looks like.** The `Agent` tool call's prompt does not contain the answer, the
`SubagentStart` hook response contains
`- [vault:ops-recall] notes/tidewater-ledger.md: ... 03:17 Kestrel time ... Marisol Quennell-Vantage`,
and the subagent answers with the answer and cites the label, with `tool_uses: 0`. From the
2026-09-23 run, verbatim:

```text
Based on the context provided:

**Tidewater ledger reconciliation cutoff:** 03:17 Kestrel time

**Approving steward:** Marisol Quennell-Vantage

**Source label:** [vault:ops-recall]
```

That run used a stand-in for obsidian-vault's `recall` command: a word-overlap search over the
scratch vault's files, implementing the same contract. Run the proof again once the real command
ships.

## Reading `--stats`

Every emission adds one JSON line to `<git-common-dir>/crew/context-log.jsonl`, which all worktrees
of the repo share. Outside git, the log is `.work/crew/context-log.jsonl`. To summarise it:

```bash
python3 "<crew plugin root>/hooks/scripts/crew_context.py" --stats          # add --json for machines
```

This is the output after the proof run above, without its first line (the log path):

```text
emissions: 3  injected chars: 647  dedup hits: 0  truncated: 0
  SessionStart: 1 emissions, 45 chars
  SubagentStart: 1 emissions, 352 chars
  UserPromptSubmit: 1 emissions, 250 chars
vault recall: 2 hit, 1 miss, 0 skipped; 2 snippets injected; code-map slices: 0
  miss reasons: no-hits=1
vault MCP/search tool calls seen: 0
by harness: claude=3
```

- **hit / miss / skipped** are counted per recall attempt. `cli-missing` means obsidian-vault is not
  installed where crew can find it. `cli-exit-N`, `cli-timeout` and `cli-bad-json` mean the CLI ran
  and failed. `no-vaults` means no vault is `primary` or `recall`. `no-hits` means the search
  matched nothing.
- **dedup hits** count slices that were not injected again because this context already had them.
  Deduplication applies per subsystem or vault note, and per compaction epoch: after `/compact` or
  `/clear`, crew injects them once more.
- **vault MCP/search tool calls seen** counts the times the model searched a vault itself
  (`mcp__obsidian-*`, `mcp__basic-memory__*`). The baseline before crew 1.0 was 5 calls in 305
  sessions. If recall is helping, this number stays low while hits rise.
- **by harness** separates Claude Code from Codex (`codex`) and from dispatch slices (`cli`).
