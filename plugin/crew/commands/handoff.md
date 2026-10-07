---
description: Write the handoff note for the next session
argument-hint: [--clear | --wrap-up]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

Write `.work/HANDOFF.md` following the `crew-context` skill.

Build it from the repository, not from recollection:

1. `git status --short` and `git diff --stat` — what actually changed
2. The ticket file, if one is in flight
3. The last verification result — did the gate pass or fail, and on what
4. The most recent `.work/review/*/out.txt` if a review ran (review scratch
   directories are ticket- and session-scoped, so there may be several - use
   the newest by mtime)
5. Write `resume:` in the header block: the one allowlisted command that is
   the next action (`resume: /crew:done T-0001`), otherwise `resume: none`.
   When the plugin ships autopilot, first run `python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py handoff-resume --root .`
   (with `--ticket <id>` for the ticket in flight): a goal line it prints wins over the next command,
   and its `resume: none` with `kind=unknown` (it could not tell which goal runs) is written as is.
   The allowlist, including the autopilot forms for a plugin that ships an
   autopilot command, is in the `crew-context` skill. Also write `branch:`
   and `head:` as their own lines. Write the note with the Write tool, not
   Bash: auto-resume binds a note to the session that wrote it, and a note
   written by Bash or by hand has no author record, so it waits

Then add the two things only you know: the **next action** in one concrete
sentence, and any **dead ends** already tried so the next session does not repeat
them.

Keep it under 40 lines. Pointers, not narrative. If you find yourself writing
paragraphs of what happened, you are producing the least reliable part of the
note — a session this deep into its context remembers worse than the diff does.

Be explicit about uncertainty. Anything you are not sure survived compaction goes
under **Verify first** rather than being asserted as done.

With `--wrap-up` (the one wrap-up procedure: context-watch's armed warning and
`/crew:autopilot` both run it), commit only if the step's `Test:` passes, then:
1. Run `git status --porcelain --untracked-files=no` first.
2. Clean: take `branch:` and `head:` from `git rev-parse` now, after the commit,
   and write `resume:` per step 5 (`/crew:autopilot <ticket>` when autopilot drives).
3. Dirty: write `resume: none` (a goal line step 5's `handoff-resume` prints still wins: T-0056), list
   the modified files under **Verify first** with why the step could not be finished. Do not commit them.
4. Keep the note under 40 lines, then end the turn. Do not tell the user to
   `/clear`: auto-clear does it when its four conditions hold, or says why not.

With `--clear`: after writing, remind me to run `/clear` (or `/compact` to keep
the summary). Say plainly that you cannot do it yourself — a hook runs as a child
of this session and cannot reset its parent.

Then stop. Do not start new work.
