---
name: crew-diagrams
description: Author architecture, process, sequence, ER and data-flow diagrams as Mermaid, render them to PNG or SVG, and produce Visio files when Visio is installed. Use when the user says draw a diagram, make an architecture diagram, show the data flow, diagram this process, export to PNG, or asks for a Visio version.
---

# Diagrams

Diagrams live as **Mermaid source in git**, rendered to images on demand. Text is
the artifact; the PNG is a build output.

The reason is maintenance. A PNG someone drew in a tool is unreviewable in a pull
request and un-updatable by anyone who lacks the source file, so it drifts from
the code within about a quarter and then actively misleads. Mermaid diffs, and
the person who changes the code can change the diagram in the same commit.

## Where things go

```
docs/diagrams/
  architecture.mmd        # source, committed
  data-flow-orders.mmd
  process-refund.mmd
  out/                    # rendered, gitignored unless a doc embeds it
    architecture.png
```

Every source file starts with a provenance comment:

```
%% Generated from <repo>@<short-sha> on <date>. Verify before trusting.
%% Anchors: src/api/orders.ts, src/domain/refund.ts
```

Anchors are the same idea as the code map: a diagram nobody can re-verify is a
diagram that rots into confident inaccuracy.

## Picking the diagram type

| Need | Mermaid type |
|---|---|
| Components and what talks to what | `flowchart LR` or `graph TD` |
| A request through the system over time | `sequenceDiagram` |
| Business or approval process | `flowchart TD` with decision nodes |
| Data model | `erDiagram` |
| Object or state lifecycle | `stateDiagram-v2` |
| Deployment topology | `flowchart` with `subgraph` per environment |
| Delivery timeline | `gantt` — rarely worth it, prefer a table |

Data-flow diagrams are `flowchart` with edge labels naming **what** moves, not
just that something does: `-->|order id, line items|` beats `-->`.

## Rules that keep them readable

- **One screen, one idea.** Over roughly 12 nodes, split by subsystem and link
  the diagrams instead. A diagram nobody can read is documentation theatre.
- `subgraph` for boundaries — service, network zone, team ownership.
- Label every edge in a data-flow or sequence diagram. Unlabelled arrows carry
  no information beyond "these things are connected," which the reader assumed.
- Direction: `LR` for pipelines and flows, `TD` for hierarchies and decisions.
- Style sparingly, and only to carry meaning (e.g. red for the failure path).
  Decoration makes diffs noisy without making the diagram clearer.
- Quote labels containing spaces, brackets, or punctuation: `A["Order API (v2)"]`.

## Rendering to PNG and SVG

Mermaid CLI:

```bash
npm install -g @mermaid-js/mermaid-cli     # provides mmdc
```

Render:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-diagrams/scripts/render.sh docs/diagrams
```

That script renders every `.mmd` to `out/*.png` and `out/*.svg`, skipping files
whose source has not changed.

Notes that will otherwise cost you time:

- `mmdc` drives headless Chromium via Puppeteer. In containers and CI it needs
  `--no-sandbox`; the render script passes a puppeteer config that sets it.
- Use `-b transparent` for embedding, `-b white` for anything that might be
  printed or pasted into Teams — transparent PNGs become unreadable on dark mode.
- `-s 2` or `-w 2400` for slide and print resolution. The default is too small
  the moment anyone projects it.
- **SVG is the better default** for docs: it stays sharp, and the text inside is
  searchable and selectable. Render PNG when the destination cannot take SVG
  (Teams messages, some wikis, PowerPoint).

Markdown files can also just embed the fenced ```mermaid block — GitHub, GitLab,
and many wikis render it natively, and then there is no build step at all. Only
render to image when the destination cannot do that.

## Visio

Visio is Windows-only and needs an installed licence. Detect before promising:

```powershell
& '${CLAUDE_PLUGIN_ROOT}/skills/crew-diagrams/scripts/visio.ps1' -Detect
```

If Visio is present, `visio.ps1` builds a `.vsdx` from a small JSON node/edge
description via COM automation. Be honest about what that produces: real Visio
shapes and connectors, laid out on a grid, that a human can then arrange and
restyle. It is a starting point, not a finished deliverable, and it will not
match a hand-drawn corporate template.

If Visio is **not** installed, do not fake it. Say so and offer the alternatives:

1. Render SVG and import it into Visio — shapes arrive grouped and editable
   enough to rearrange, which covers most "I need it in Visio" requests.
2. Keep Mermaid and export PNG for the document, if the ask was really "a
   picture for the architecture deck."
3. draw.io / diagrams.net imports Mermaid directly and exports `.vsdx`, which is
   often the shortest path to a Visio file on a machine without Visio.

Ask which of the three they want rather than guessing — "I need Visio" usually
means "the architecture review board expects a Visio file," and option 3 solves
that without a licence.

## What not to diagram

Anything the code answers faster. A three-box diagram of a three-file service is
overhead. Diagram the things that are genuinely hard to hold in your head: cross
service call paths, retry and failure behaviour, data lineage, and the process
where the approval rules are not obvious from any single file.
