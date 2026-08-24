# Note on bundling find-skills

This is a third-party skill from the open skills ecosystem, vendored here at the
user's request rather than installed with `npx skills add`.

## What that costs you

- **No updates.** `npx skills check` will not see this copy. Upstream fixes have
  to be pulled in by hand.
- **You own it now.** If its guidance goes stale — a CLI flag changes, the
  leaderboard moves — that is your bug to notice.

Installing it separately (`npx skills add -g`) keeps it updatable and lets you
disable it without touching crew. Vendoring is the right call only if you need
it to travel with the plugin to machines that will not run the skills CLI.

## The trigger-breadth problem (narrowed)

The upstream description fired on *"asks how do I do X"*, which is close to
"any question." In a crew session that competed with `crew-setup`,
`crew-verification`, and the rest for ordinary requests, and skill selection got
noticeably worse as more broadly-scoped skills loaded.

Original upstream description, kept here for comparison:

```
description: Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extending capabilities. This skill should be used when the user is looking for functionality that might exist as an installable skill.
```

The `description:` line in `SKILL.md` has been replaced with the narrowed
version below. Only that one line changed; the rest of the body is still
upstream's, untouched. Do not apply this narrowing again — it is already in
place.

```
description: Discover and install agent skills from the open skills ecosystem via the skills CLI. Use only when the user explicitly asks to find, search for, browse, or install a skill or plugin - not for general "how do I" questions, which should be answered directly.
```

The two other copies of this skill (the global `~/.claude/skills/find-skills`
install and a project-scoped copy) were removed from this machine during the
crew rollout; this vendored copy under `plugin/crew/skills/find-skills/` is
the only one that ships with crew. A global copy can still exist on someone
else's machine — that is what `crew-setup`'s detection step (`detect.sh`)
checks for and reports on.
