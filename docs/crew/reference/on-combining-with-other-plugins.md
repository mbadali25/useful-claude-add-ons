<!-- Moved verbatim from plugin/crew/README.md (On combining with other plugins) by L-0726; the README keeps an index entry. -->

## On combining with other plugins

Keep `crew` separate from general skill libraries like `superpowers`. They
compose fine — plugin skills are namespaced, so nothing collides — and they solve
different problems: `superpowers` is broad methodology (TDD, debugging,
brainstorming) applied everywhere, while `crew` is a narrow gated workflow for a
specific kind of repo.

Install both if you want both. Do not merge them: bundling someone else's
20+ skills into this plugin means you inherit their update cadence, their
triggering behaviour, and their context cost, with no way to take one without the
other. Two plugins you can enable and disable independently is strictly more
control than one you cannot.

Watch for one interaction. Both libraries auto-trigger on natural language, and
more standing skills means more competition for the same request — if
`crew-setup` stops firing on "set up crew," a broadly-scoped skill from another
plugin is the first thing to check.
