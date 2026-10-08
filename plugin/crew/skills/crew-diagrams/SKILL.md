---
name: crew-diagrams
description: Author architecture, process, sequence, ER and data-flow diagrams as Mermaid that pass a measured readability check (no crossing lines, nothing drawn through a box, at most 15 boxes), embed them in a generated Markdown and HTML page, render them to PNG or SVG, and produce Visio files when Visio is installed. Use when the user says draw a diagram, make an architecture diagram, show the data flow, diagram this process, export to PNG, or asks for a Visio version.
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
  README.md               # generated: every diagram embedded with its purpose (diagram_doc.py)
  index.html              # generated: the same page as HTML
  out/                    # rendered, gitignored unless a doc embeds it
    architecture.svg
```

These are the standard locations, for every diagram crew draws. A topic page
that explains a process (`docs/qa/README.md`, say) embeds its diagrams as
fenced `mermaid` blocks and keeps their sources here, so one directory holds
every diagram the repo has and one page shows them all. The README of the code
a diagram describes gets it too, generated (see "Embedded in the READMEs it
describes").

Every source file starts with a provenance comment and a purpose line:

```
%% Generated from <repo>@<short-sha> on <date>. Verify before trusting.
%% Anchors: src/api/orders.ts, src/domain/refund.ts
%% Purpose: How a refund moves from request to ledger, and where it can be refused.
```

`%% Purpose:` is what the generated page prints above the diagram. One or two
plain sentences: what a reader learns from it.

Anchors are the same idea as the code map: a diagram nobody can re-verify is a
diagram that rots into confident inaccuracy.

**The header is machine-read, so its shape matters.** `crew_state.read_diagrams`
parses the short sha out of that first line to decide whether a diagram is
current, and `/crew:status` and the context hook report the answer. A source file with no parseable
provenance counts as *behind*, not as *unknown* — unknown resolving to stale is
the honest direction, and it is the same call `_read_graph` makes about a graph
with no `built_at_commit`. The cost of being wrong that way is one unnecessary
redraw; the cost of the other way is a diagram that lies and looks fresh.

## The PM refreshes these on its own

Diagrams are the one documentation artifact the crew regenerates without being
asked. That is not a general licence to rewrite documentation — it is specific
to artifacts with a machine-checkable anchor, where "is this still true" has a
real answer rather than a judgement call. Prose docs keep `crew-docs`'s
deliberate *do not touch* default for exactly that reason.

Two triggers drive it, and they mean different things:

- `diagramsStale` — a source's anchor is not HEAD. The picture exists and the
  code under it moved. Re-verify, then update.
- `diagramsMissing` — one of architecture / data-flow / process has no file at
  all, in a repo whose subsystems are already mapped. Draw it. This one stays
  quiet until there is a code map, because a repo that has not decided what its
  subsystems are has nothing to draw from yet.

**Always re-verify before redrawing.** Send `crew:explorer` first and check its
anchors against HEAD. A diagram regenerated from a code map that is itself
behind is stale output wearing a fresh anchor — strictly worse than the stale
diagram it replaced, because that one at least advertised its age. This is why
`graphStale` and `knowledgeBehind` sort above `diagramsStale` in the trigger
order: fix the input before regenerating the output.

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

## The readability standard: measured, not hoped for

A diagram is done when `diagram_check.py` says PASS on its render. It measures
the drawing Mermaid actually produced, so a layout that looked fine in the
source and crossed in the picture is caught:

| Measured | Limit |
|---|---|
| Lines crossing outside a box | 0 |
| A line drawn through a box that is not one of its ends | 0 |
| An edge label covering a box or another label | 0 |
| Boxes | 15 |

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-diagrams/scripts/render.sh docs/diagrams
python3 ${CLAUDE_PLUGIN_ROOT}/skills/crew-diagrams/scripts/diagram_check.py docs/diagrams/out
python3 ${CLAUDE_PLUGIN_ROOT}/skills/crew-diagrams/scripts/diagram_doc.py --dir docs/diagrams --write
```

Only flowcharts are measured; a sequence, state or ER diagram is reported NOT
CHECKED, never PASS. Without `mmdc` nothing is rendered, so nothing is
measured: say NOT VERIFIED and give the install line, never "looks fine".
A drawing the checker cannot fully read (no box measured, a line outside the
boxes that is not a recognised edge, a scale/rotate transform, path data it
cannot parse) is UNKNOWN, also never PASS.

The page trusts a render only when it came from the current source:
`render.sh` writes `out/<name>.svg.src`, the sha256 of the `.mmd` it rendered,
and `diagram_doc.py` compares it with the `.mmd` now. A different hash reads
"render out of date (run render.sh ...)". A render with no `.src` (made by
hand, or where neither `sha256sum` nor `shasum` exists) falls back to file
times, and its verdict says "(freshness by mtime only)".

**How a FAIL is usually fixed:**

- **A loop back to an earlier step** (a red check returning to the gate) is the
  commonest crossing. End the red branch in its own box instead: "fix, then the
  gate runs again". The reader understands the loop; the layout stops crossing.
- **Over 15 boxes**: split along the `subgraph` boundaries. Keep the original
  file name for a short overview whose boxes are the parts, so links still
  work, and name the parts `<name>-<part>.mmd`.
- **Long labels**: break them with `<br/>`, three lines at most.

## Rules that keep them readable

- **One screen, one idea.** Over 15 boxes the checker fails it: split by
  subsystem and link the diagrams instead. A diagram nobody can read is
  documentation theatre.
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
whose source has not changed: for an SVG, whose recorded `out/<name>.svg.src`
hash still matches the `.mmd` (file times only when there is no `.src`).

Notes that will otherwise cost you time:

- `mmdc` drives headless Chromium via Puppeteer. In containers and CI it needs
  `--no-sandbox`; the render script passes a puppeteer config that sets it. A
  repo's `_verify/` check uses crew-setup's `templates/cases/diagrams-render.sh`,
  which passes the same config, never a bare `mmdc` call.
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

## Embedded in the READMEs it describes

Never hand-copy a diagram into a README. After rendering:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_diagrams.py embed --root .
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_diagrams.py check --root .
```

`embed` writes each diagram into the README nearest its `%% Anchors:` paths,
between `<!-- crew-diagrams:begin -->` and `<!-- crew-diagrams:end -->`: a
`## Diagrams` heading, then per diagram the title, the `%% Purpose:` text, the
fenced block (the source without its `%%` lines, as on the diagrams page) and a
source link. Outside the markers nothing changes, and a second run changes no
byte. Never a target: the repo-root README, a `SKILL.md` (it is loaded into
context), a README inside the diagrams dir, or one another generator owns (a
`<!-- generated by` line at the top, e.g. `docs/qa/README.md`). No README is
created; a diagram reaching none is on the diagrams page only. Override in the
source with `%% Embed: plugin/x/README.md` or `%% Embed: none`. On a Bitbucket
`origin` the block becomes `out/<name>.svg` as an image plus the source in a
`<details>`, and `embed` warns when git ignores that SVG.

`check` is what keeps them honest: drift (a hand edit, a source changed and not
re-embedded, a section no diagram targets any more), malformed markers and an
unreadable source each exit 1. A README that has never been embedded is
`pending`, not a failure. `crew_refresh_check.py` prints drift as a
`diagram-embeds` line whose refresh is `embed`, so `/crew:implement` step 6
fixes it and `/crew:done` check 4 refuses until it is fixed.

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
