---
description: Update the documents this change should touch — and only those
argument-hint: [--audit]
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

## `--audit`

Report only, change nothing:

- Generated blocks that are stale (regenerate and diff, do not commit)
- Diagram anchors whose files moved since the recorded sha
- `[Unreleased]` in the CHANGELOG older than the last release tag
- ADRs referencing files that no longer exist
- TODO entries whose stated unblock condition has already happened
- README commands that no longer match `.crew/verify.json` or the build files

Present as a list with a suggested action each. Do not fix in bulk — a large
documentation diff is unreviewable, which means it gets approved unread.
