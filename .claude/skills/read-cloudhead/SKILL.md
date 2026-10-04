---
name: read-cloudhead
description: Resume the owner's cloud PR-landing session. Use when the user says "read Cloudhead", "read cloud head", "read the cloud handoff", or asks to pick up where the last cloud session stopped.
---

# Read Cloudhead - resume the cloud landing session

The cloud sessions that land this repo's PRs keep their state on the notes
branch `ccr-b039f2bb-6jks7g` (PR #391, docs-only, merges last), not on main.

1. `git fetch origin ccr-b039f2bb-6jks7g` and add a worktree for it, e.g.
   `git worktree add /home/user/notes origin/ccr-b039f2bb-6jks7g -B ccr-b039f2bb-6jks7g`.
2. Read `cloud-handoff-notes.md`, section **">>> RESUME HERE"**, in full. It
   holds the owner's standing rules, the state of main, what was in flight and
   what to do first.
3. Read `CLOUD-SESSION-TICKETS.md` (same branch, repo root): every merged,
   open, blocked and newly minted ticket, and the owner's recorded decisions.
4. Copy `docs/handoff/cloud/procedures/` (BUILD.md, LANDPREP.md, note.sh)
   into your scratchpad and follow them. Log every action with `note.sh`
   (set `NOTES_DIR` to the worktree from step 1).
5. Verify the "In flight at handoff" table against GitHub before acting:
   heads may have moved since the notes were written.
6. Tell the owner, in a short table, where things stand and what you will do
   first, then continue.

`CLAUDE.md` still wins on any conflict. This skill only says where the state is.
