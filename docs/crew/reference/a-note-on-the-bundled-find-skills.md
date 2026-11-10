<!-- Moved verbatim from plugin/crew/README.md (A note on the bundled find-skills) by L-0726; the README keeps an index entry. -->

## A note on the bundled find-skills

`skills/find-skills/` is a third-party skill from the open skills ecosystem,
vendored here rather than installed with `npx skills add`. That means no
updates — `npx skills check` won't see this copy, and upstream fixes have to be
pulled in by hand.

Installing it separately keeps it updatable and lets you disable it without
touching crew. Vendoring is right only if it needs to travel with the plugin to
machines that won't run the skills CLI.

Worth knowing: its upstream description fires on *"asks how do I do X"*, which is
close to "any question." That competes with crew's own skills for ordinary
requests, and selection gets worse as more broadly-scoped skills load. If
`crew-setup` stops firing on "set up crew," disable this for one session and see
whether the problem goes away. `BUNDLING-NOTE.md` beside it has a narrowed
description you can swap in that keeps the capability and removes the collision.

This is now checked for you, not just documented. The `repo-plugins` install
step detects a **separate**, globally-installed copy at
`~/.claude/skills/find-skills` — the one `find-skills` (menu item 5) or
`npx skills add vercel-labs/skills --skill find-skills` puts there — and warns
that two active copies can both trigger on the same prompt. The check is
detection-only: it never deletes anything, it just prints the collision and
the manual `rm -rf` to remove the global copy if you want crew's vendored one
to be the only one loaded.
