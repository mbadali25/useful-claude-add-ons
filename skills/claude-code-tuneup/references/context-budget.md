# What is loaded before the user's first message

Everything here is resident from the moment the session starts. It is the budget you are
working against, and most of it is a consequence of what got installed rather than a
setting anyone chose.

| Source | Loaded | Cost driver | Lever |
|---|---|---|---|
| `~/.claude/CLAUDE.md` | always | file size | keep under ~200 lines; move path-specific rules out |
| Project `CLAUDE.md` | when in that project | file size | same |
| `.claude/rules/*.md` | when a `paths:` glob matches (always, if no `paths:`) | file size × matching files | add a `paths:` glob to every rule |
| Skill `description` (frontmatter) | always, per installed skill | number of installed skills | uninstall what you don't use |
| Skill body (`SKILL.md` after frontmatter) | only when the skill is invoked | — | free until used |
| `references/*.md` | only when the skill reads them | — | free until used; this is why long content belongs there |
| Subagent name + description | always, per registered agent | number of agents | uninstall agent packs you never dispatch to |
| MCP tool schemas | always, unless the harness defers them | number of tools × schema size | fewer servers; scope to project `.mcp.json` |
| `SessionStart` hook output | always, per hook that prints | what the hook prints | drop hooks whose output you don't read |
| Output styles | when active | file size | — |

## The two counts that surprise people

**Skill descriptions are not free.** A description is the only thing the model sees when
deciding whether to invoke a skill, so every installed skill's description is in the system
prompt on every turn. A dense, well-written description is 100–200 tokens. Eighty installed
skills is therefore 8k–16k tokens before anything happens — and if half of them are
installed twice, you are paying for the duplicate too.

**Agent packs are heavy.** A pack advertising 150 subagents puts 150 names and descriptions
in front of the model. If every one of them is disabled, you are paying nothing — but if
they're enabled and never dispatched to, that's the worst case: full cost, zero use.

## Measuring rather than estimating

The audit's byte counts use a ~4 bytes/token approximation, which is fine for *comparing*
sources. For the real number, `/context` in a live session gives the actual breakdown, and
its "Memory files" section lists which `CLAUDE.md` and rules files were actually picked up —
which is how you catch a rules file whose glob never matches, or a project `CLAUDE.md`
Claude Code didn't find.

## Shrinking it, in order of payoff

1. **Delete duplicate installs.** Pure waste, no functionality lost.
2. **Uninstall plugins already disabled.** The user has already decided; the cost is still
   being paid in marketplace refresh and disk, and re-enabling is one command away.
3. **Scope rules files.** A rule with no `paths:` frontmatter loads in every project on the
   machine. Adding `paths: ["**/*.tf"]` makes it free everywhere else.
4. **Split `CLAUDE.md`.** Anything that only matters in part of the tree belongs in
   `.claude/rules/` with a glob.
5. **Move MCP servers to project scope.** A server defined in the project's `.mcp.json`
   costs nothing in the ten other repos you work in.
6. **Uninstall skills for systems you don't touch.** The honest one. A skill for a product
   you evaluated once still costs its description every session.

## What *not* to do

- Don't shorten skill descriptions to save tokens. The description is what makes the skill
  fire on the right conversation; a vague one either never triggers or triggers on the wrong
  thing, which costs far more than the tokens saved.
- Don't move content out of `SKILL.md` into `references/` purely for budget — the body only
  loads on invocation anyway. Do it for readability.
- Don't set `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` low to "avoid running out". It makes
  compaction more frequent, not less; each compaction loses detail.
