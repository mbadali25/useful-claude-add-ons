---
description: Create or refresh diagrams from the actual code
argument-hint: <architecture | data-flow <area> | process <name> | sequence <flow> | refresh>
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
---

Diagram: $ARGUMENTS

1. Use `crew:explorer` to establish what is actually true. Never diagram from
   the code map alone — check its anchors against HEAD first. A diagram inherits
   the staleness of whatever it was drawn from.
2. Pick the type per the `crew-diagrams` skill. Ask me if the request is
   ambiguous — "architecture diagram" means components to some people and
   deployment topology to others, and drawing the wrong one wastes both our time.
3. Write Mermaid source to `docs/diagrams/<name>.mmd`, with the provenance
   comment and anchor list at the top.
4. Render: `bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-diagrams/scripts/render.sh docs/diagrams`
5. Show me the source. If `mmdc` is not installed, say so and give me the install
   line rather than silently skipping the render.

With `refresh`: for each existing `.mmd`, diff its anchor files against HEAD.
Re-verify and update only the ones whose anchors moved. Report which diagrams you
left alone and which you could not verify.

If I ask for Visio, follow the Visio section of `crew-diagrams` — detect first,
and if it is absent offer the three alternatives rather than producing something
that is not a Visio file.

Anything you could not confirm from code goes in the diagram as a dashed edge
with a `?` label, not as a confident solid line. A diagram that quietly guesses
is worse than one that admits a gap.
