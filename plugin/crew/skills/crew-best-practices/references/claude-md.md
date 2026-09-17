# CLAUDE.md: structure, size, and the four anti-patterns

Source: <https://rosmur.github.io/claudecode-best-practices/> §4.1.1. The
**crew:** notes are this repository's position.

## Size

| File | Target |
|---|---|
| Root `CLAUDE.md` | 100–200 lines |
| Subdirectory `CLAUDE.md` | 50–100 lines each |
| Total, all CLAUDE.md | under ~2000 tokens |
| Baseline session context | under 20k tokens (10% of a 200k window) |

## What belongs where

**Root:** critical universal rules, a quick command reference, testing
instructions, repository etiquette, and pointers to more detailed files.

**Subdirectory:** project-specific context, local commands and quirks, and
pointers to the architecture.

## The four anti-patterns

These are the useful part of the section — each has a concrete replacement.

### 1. Do not `@`-file entire documents

An `@`-referenced file is embedded on **every** run. A 400-line design document
referenced from CLAUDE.md is 400 lines in every session, whether or not the
session touches that subsystem.

**Instead:** use a relative path with context — "For complex usage, see
`path/to/docs.md`". The model reads it when the task needs it.

### 2. Do not write absolute prohibitions

> "Never use `--foo-bar` flag"

leaves the model with a hole and no route through it, so it either stops or
invents one.

**Instead:** provide the alternative — "Never use `--foo-bar`; prefer `--baz`."

### 3. Do not write a comprehensive manual

CLAUDE.md is not documentation. It is the set of things the model gets wrong
here.

**Instead:** document what Claude specifically gets wrong in **this** repository.
If a rule has never prevented a mistake, it is costing tokens on every run for
nothing.

### 4. Do not let it grow unreviewed

The document's suggested rhythm: audit context usage mid-session, then prune.

## Where crew departs

**This repository's own `CLAUDE.md` is far longer than 200 lines, and that is
correct.** Its length comes from a landmine list where every entry cost real
debugging time — `pwsh` not being on Git Bash's PATH, `MSYS_NO_PATHCONV`
mangling paths in two opposite directions, `pathlib.write_text` turning a `.sh`
into CRLF, `open(p, "w")` truncating before the payload exists.

The document's rule and this file's practice differ on **the metric**. Line
count is a proxy; the real question is whether each line changes a decision.
Every landmine entry does: it names a defect that has already shipped, and
carries the evidence that earned it.

Where the document's advice **does** apply here:

- The anti-patterns hold regardless of length. No `@`-file embedding, no bare
  prohibitions without an alternative, no restating what the code already says.
- "Document what Claude gets wrong specifically" is exactly what the landmine
  list is. The length is a consequence of the repository's age, not a violation
  of the rule.

## Applying this to a repo crew onboards

`/crew:init` and the `crew-setup` skill write a CLAUDE.md into the target
repository. For a **fresh** repo the document's numbers are the right starting
point — 100–200 lines, pointers rather than embedded content, and no rule that
has not yet prevented a mistake.

A rule earns its place by catching something. Start small and let the file grow
from defects, not from imagination.
