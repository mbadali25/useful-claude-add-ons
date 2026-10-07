---
description: Update the documents this change should touch — and only those
argument-hint: "[ticket id] [--audit]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

$ARGUMENTS

## Default (no argument)

1. Establish what changed: `git diff --stat`, the ticket, the verification result.
2. Walk the trigger table in the `crew-docs` skill and decide, per document,
   whether its condition is met. State the decision for each — including the
   ones you are skipping and why.
3. Update only those. **Check for generated blocks first** — if the target sits
   between `BEGIN_TF_DOCS`/`END_TF_DOCS` or similar markers, edit the source
   instead and say which source you edited.
4. If Terraform changed, run `terraform-docs .` rather than hand-writing the
   module reference.
5. Show me the doc diff separately from the code diff.

"None of them" is a valid and common answer. Say it plainly rather than finding
something to write.

## With a ticket id - record the decisions, then check them (T-0022)

Do steps 1-5 for ticket `$1`, then write `.work/tickets/$1/docs.json` once, computed in full first:
`{"reasons": {"<document>": "<why not>"}, "deferred": [{"key", "why", "unblock"}]}`. A reason
per document you decided not to touch (`README.md`, `plugin/<n>/README.md`, `SECURITY.md`); a
`deferred` item per piece of work left for later, each also added to `TODO.md` as its own entry (a bullet opening with its key) with its why and
unblock. Then run the read-only check:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_docs_check.py --root . --ticket $1
```

Act on each `MISSING` line and re-run it. A changed plugin's CHANGELOG line (`` `<name>` `` and its
new version, under `## [Unreleased]`) has no reason that waives it. `unknown` is a stop: report it.

## `--audit`

Report only, change nothing:

- Generated blocks that are stale (regenerate and diff, do not commit)
- Diagram anchors whose files moved since the recorded sha
- `[Unreleased]` in the CHANGELOG older than the last release tag
- ADRs referencing files that no longer exist
- TODO entries whose stated unblock condition has already happened
- README commands that no longer match `.crew/verify.json` or the build files
- **CLAUDE.md drift.** Run
  `bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/claude-md-audit.sh` and
  report any missing template section, any remaining placeholder, and any breach
  of the 60-line ceiling. The template gains sections over time and nothing
  propagates them into a repo automatically, so this is the only place the drift
  is ever caught. Report it; do not silently append - which sections a repo wants
  is the user's call.

Present as a list with a suggested action each. Do not fix in bulk — a large
documentation diff is unreviewable, which means it gets approved unread.
