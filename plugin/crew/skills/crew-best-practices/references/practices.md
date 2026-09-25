# The full rule set, by area

Source: <https://rosmur.github.io/claudecode-best-practices/>. Quotations are
the document's; the **crew:** notes are this repository's position, and are not
part of the source.

## Test-driven development

- Write tests **before** implementation.
- Confirm the test fails before writing the fix. A test that has never failed
  has not been shown to be able to fail.
- Commit tests separately from implementation.
- **Do not modify tests during implementation.** Changing the test to match the
  code deletes the reason the test existed.

Anti-pattern: mock implementations that pass without testing anything real.

**crew:** the implementing session writes checks, before review; `sabotage.py` in
this repo is the stronger form of "confirm it fails" — it applies a mutation
and requires the suite to go red, which catches a test that passes for the
wrong reason.

## Continuous quality gates

- Enforce type/lint checks after every edit.
- Validate builds before commits.
- Use hooks so an error cannot persist unnoticed.

**Caveat the document raises itself:** automatic *formatting* hooks consume
excessive tokens — it cites 160k over three rounds. Format manually between
sessions instead.

**crew:** `verify-gate` on Stop is this, driven by `.crew/verify.json`.

## Code review, including the model's own work

Three layers: self-review in a fresh context, human verification, and a second
instance that did not write the code.

> "I believe I'm ultimately responsible for the code in a PR with my name on
> it, regardless of how it was produced."

Focus areas it names: spaghetti code, API and backend changes, unnecessary
imports, missing error handling, security vulnerabilities.

**crew:** `/crew:review` prefers a different model *family* (Codex, then
Copilot, then Claude). A clone shares the author's blind spots; a different
family does not.

## Commits

- Commit early and often, with meaningful messages.
- Conventional Commits format.
- Each commit must compile and pass tests.
- Tie commits to plan or task checkpoints.
- **"Avoid references to 'Claude' or 'AI-generated' in messages."**

**crew:** that last rule conflicts with this repository's own attribution
requirement, which adds `Co-Authored-By` and a session link. The repository's
instruction wins; the document is describing a different team's convention.

## Context management

The document's highest-priority area.

- **Clear at 60k tokens or 30%** — do not wait for the limit.
- `/clear` + re-read, or the "Document & Clear" workflow: write progress to a
  file, clear, start fresh from that file.
- **Avoid `/compact`.** "Automatic compaction is opaque, error-prone, and
  poorly optimized."
- Three files per task: `<task>-plan.md`, `<task>-context.md`, `<task>-tasks.md`.
- Keep plans living: update them during implementation.

**crew:** the hooks implement this — `context-watch` warns at the threshold,
`handoff-write` fires on PreCompact, the context hook injects the note at
SessionStart. Since 0.19.52 `autoWrapUp` and `autoClear` default
on, so the loop runs without being asked. The 60k figure does not transfer to a
1M window; crew uses a fraction and auto-detects the window.

## Planning

- Planning mode before production work, every time.
- Ask for 2–3 alternative approaches with trade-offs.
- Progressive deepening: "think", "think hard", "think harder", "ultrathink".
- Then **start a fresh context** with the plan, and implement 1–2 sections at a
  time.

The four-phase workflow: **Explore → Plan → Code → Commit**, with "DON'T code
yet" said explicitly during exploration.

> "Steps #1-#2 are crucial—without them, Claude tends to jump straight to
> coding."

**crew:** `/crew:plan`, whose optional second opinion works from an abstracted
brief rather than source, so it cannot pattern-match the existing code.

## Skills

- Main `SKILL.md` **under 500 lines**, with progressive disclosure into
  reference files. It reports 40–60% token savings from restructuring 1,500-line
  files into a 300–400 line main plus 10–11 references.
- **"Manual skills are ignored ~90% of the time."** Its fix is a
  `UserPromptSubmit` hook that injects a skill-activation reminder, driven by a
  `skill-rules.json` of keyword and file-path triggers.

**crew:** the size rule is adopted — every `SKILL.md` here is under 500 lines.
The auto-activation hook is **not**, and the reason is this repository's own
rule: a hook runs whether or not Claude agrees with it, so a plugin registering
one defaults to OFF, and one that can block needs a committed regression suite.
An activation nag on every prompt is a high-frequency hook for a low-severity
problem.

## Hooks

Three kinds, and the ordering rule matters most:

1. **Block-at-submit** — e.g. a `PreToolUse` hook on `git commit` that requires
   a pass marker.
2. **Hint hooks** — non-blocking guidance.
3. **"Don't block at write time—let the agent finish its plan, then check the
   final result."**

**crew:** rule 3 is why 0.19.52 removed the `PreToolUse` command guard and kept
the Stop-time `verify-gate`. The guard inspected every command as it was typed;
the gate checks the result once the work is done.

## Subagents

Two positions, which the document leaves unresolved in §5.2:

- **A:** custom specialised subagents, better for narrow tasks.
- **B (its preference):** put context in CLAUDE.md and spawn *clones* of the
  main agent, avoiding "gatekeeping context".

**crew:** departs, deliberately — see
`docs/adr/0003-crew-departs-from-three-community-best-practices.md`. The short
reason: a clone inherits the context whose blind spots a review exists to find.

## Slash commands

> "If you have a long list of complex custom slash commands, you've created an
> anti-pattern."

Its recommended set is about eight: `/dev-docs`, `/catchup`, `/code-review`,
`/build-and-fix`, `/test-route`, `/pr`.

**crew:** departs — 34 commands.<!-- claim: plugin-commands:crew --> See the ADR. The short reason: crew's commands
are gated workflows whose steps must not vary, not shortcuts.

## MCP

> "If you're using more than 20k tokens of MCPs, you're crippling Claude."

- **Anti-pattern:** dozens of tools mirroring a REST API.
- **Good:** a few powerful gateways — `download_raw_data(filters)`,
  `execute_code_in_environment(code)` — with the agent scripting against the
  data.
- **Rule: Skills > MCP for most uses.** Stateless tools should be CLIs
  documented in a skill. MCP is for stateful environments, e.g. Playwright.

**crew:** registers no MCP server of its own.

## Search over RAG

Claude Code uses ripgrep, jq and find rather than retrieval. The document's
argument is failure modes: a RAG pipeline hides its similarity function,
reranker and chunking strategy, and an LLM reading ten lines and then ten more
behaves like a human and has fewer moving parts.

> "This is the Camera vs Lidar of the LLM era."

## Workflow

- **Specificity.** Name the route, the sections, the component pattern, the
  tests — not "add a settings page".
- **Visual references.** Paste a mock, implement, screenshot, compare, iterate.
  Typically 2–3 rounds.
- **Course correction:** ask for a plan first; Escape to interrupt; double-Escape
  to edit an earlier prompt; ask to undo.
- **Git worktrees** for parallel independent work, one terminal per tree.

## Testing standards

Its eleven-point checklist, compressed to the points that change behaviour:

- Parameterise inputs; no unexplained literals.
- Add a test only if it can fail for a real defect.
- The description must match what the assertion checks.
- Compare against an **independent** expectation, not the function's own output.
- Use strong assertions (`toEqual` over `toBeGreaterThanOrEqual`).
- Test edge cases and boundaries; don't test what the type checker catches.
- Express invariants with property-based tests where they exist.

## Headless mode

`claude -p` for CI, pre-commit hooks, issue triage. Two shapes: fanning out
across a large migration, and pipelining output into another command.

## Practices it says to avoid

- Auto-formatting hooks (token cost).
- Heavy MCP usage (>20k tokens).
- Complex multi-agent systems (debuggability).
- RAG for code search.
- Vague instructions.
- Skipping planning.
- Letting context fill to the limit.
