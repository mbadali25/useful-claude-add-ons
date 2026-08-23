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

## The trigger-breadth problem

The upstream description fires on *"asks how do I do X"*, which is close to
"any question." In a crew session that competes with `crew-setup`,
`crew-verification`, and the rest for ordinary requests, and skill selection gets
noticeably worse as more broadly-scoped skills load.

If crew's own skills stop firing reliably, this is the first thing to test —
disable it for one session and see whether the problem goes away.

To narrow it without touching the body, replace the `description:` line with:

```
description: Discover and install agent skills from the open skills ecosystem via the skills CLI. Use only when the user explicitly asks to find, search for, browse, or install a skill or plugin - not for general "how do I" questions, which should be answered directly.
```

That keeps the capability and removes the collision.
