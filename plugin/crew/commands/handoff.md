---
description: Write the handoff note for the next session
argument-hint: [--clear]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

Write `.work/HANDOFF.md` following the `crew-context` skill.

Build it from the repository, not from recollection:

1. `git status --short` and `git diff --stat` — what actually changed
2. The ticket file, if one is in flight
3. The last verification result — did the gate pass or fail, and on what
4. `.work/review-out.txt` if a review ran

Then add the two things only you know: the **next action** in one concrete
sentence, and any **dead ends** already tried so the next session does not repeat
them.

Keep it under 40 lines. Pointers, not narrative. If you find yourself writing
paragraphs of what happened, you are producing the least reliable part of the
note — a session this deep into its context remembers worse than the diff does.

Be explicit about uncertainty. Anything you are not sure survived compaction goes
under **Verify first** rather than being asserted as done.

With `--clear`: after writing, remind me to run `/clear` (or `/compact` to keep
the summary). Say plainly that you cannot do it yourself — a hook runs as a child
of this session and cannot reset its parent.

Then stop. Do not start new work.
