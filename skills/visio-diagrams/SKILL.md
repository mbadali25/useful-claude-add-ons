---
name: visio-diagrams
description: Create, edit, and generate Microsoft Visio diagrams (.vsdx) — network topologies, architecture diagrams, rack layouts, process/swimlane flows, DR runbooks, org charts. Use this skill whenever the user mentions Visio, .vsdx, .vsdm, .vssx stencils, "network diagram", "architecture diagram", "topology diagram", or asks for a diagram that someone else will need to EDIT (as opposed to just view) — for example "make a Visio of our prod network", "turn this subnet list into a diagram", "we need a CAB/audit diagram", "convert this Mermaid to Visio", or "read the shapes out of this .vsdx". Also use it when a diagram must go into change-management, compliance, or as-built documentation, since those workflows almost always mandate Visio. Do NOT reach for a screenshot, a static image, or raw Mermaid when the request implies Visio.
---

# Visio diagrams

Generate native `.vsdx` files without needing Visio installed, or drive Visio
directly via COM when real stencil masters matter.

## Step 0 — dependencies

Run this once per session, before anything else:

```bash
python scripts/ensure_deps.py
```

It installs only what is missing and never fails the task if pip is blocked.

**Generating a `.vsdx` needs no third-party packages at all** — `vsdx_writer.py`
is stdlib-only on purpose, so this works on an air-gapped or proxied box. The
packages below only add capability around the edges:

| Package | Unlocks | If unavailable |
|---|---|---|
| `vsdx` | Verification round-trip; reading/editing existing `.vsdx` | Report output as **UNVERIFIED**. Do not imply it was validated. |
| `pyyaml` | YAML specs | Write the spec as JSON — identical schema |
| `cairosvg` | Rendering the SVG preview to PNG | SVG is still written; open it directly |

`scripts/verify_vsdx.py` installs `vsdx` on demand, so verification is never
skipped merely because a package was absent.

To check without installing: `python scripts/ensure_deps.py --check` (exit 1 if
anything is missing).

Note on `vsdx`: it is a **verification and editing** library. It cannot create a
diagram. Installing it does not change the answer in the table below.

## Critical: what does NOT work

Do not waste a turn on these — they are the obvious wrong answers:

| Approach | Reality |
|---|---|
| `pip install vsdx` then create a diagram | The `vsdx` package **only opens existing files** (`VisioFile(path)`). It cannot create one. It is a template-mutation and read library. |
| `python-docx`-style library for Visio | Does not exist. Nothing on PyPI generates `.vsdx` from nothing. |
| Microsoft Graph API | Exposes the file as an opaque blob in OneDrive/SharePoint. There is no Graph surface for Visio *drawing content*. |
| Save as `.vdx` (2003 XML) | Visio 2013+ dropped it. Modern Visio refuses or mangles it. |
| Rename an SVG/PDF to `.vsdx` | Produces an unreadable-content error. |

The working answers are the two paths below.

## Step 1 — challenge the requirement first

Before generating anything, check that Visio is actually the right output. It
often is (change management, audit, as-built docs, and handoff to people who
only have Visio), but it often is not, and picking wrong costs a rework cycle.

| Ask | If yes |
|---|---|
| Will a human edit it after you hand it over? | Visio. This is the real justification — no other format gives editable, glued shapes. |
| Is it going in a repo, PR, or wiki? | Mermaid or Graphviz. Diffable in git; Visio binaries are not reviewable. |
| Is it just to look at once? | SVG/PNG. Faster, no licence needed. |
| Does the org mandate a Visio stencil/template? | Visio, via the COM path with that stencil. |
| Does it need Cisco/AWS/Azure icon sets? | Visio, COM path. The Python path draws generic shapes only. |
| Does it regenerate in CI from source data? | `vsdx_writer.py`. COM cannot run reliably headless. |

Say this out loud to the user in one or two lines. Do not silently pick.

## Step 2 — pick the path

| | Path A: `vsdx_writer.py` | Path B: COM automation |
|---|---|---|
| Needs Visio installed | No | Yes (Windows desktop) |
| Runs in CI / on Linux / here | Yes | No |
| Shape vocabulary | Generic (box, ellipse, diamond, hexagon, triangle, parallelogram, rounded) | Any stencil: Cisco, AWS, Azure, corporate |
| Auto-layout quality | Decent layered layout | Visio's own engine — better |
| Themes, containers, swimlanes | No | Yes |
| Speed | Instant | Seconds, plus COM cleanup risk |

**Default to Path A.** Escalate to Path B only for real stencil masters,
themes, containers/swimlanes, or when the file must be indistinguishable from
hand-drawn. Both consume the same spec, so prototyping in A and re-rendering in
B is a supported workflow.

## Step 3 — write a spec, not code

Write a YAML spec and run the generator. Do not hand-place coordinates unless
the user asked for a specific arrangement — the layout engine handles it.

```yaml
title: Prod Network
page: {direction: TB}          # TB (top-down) or LR (left-right)
defaults: {width: 1.9, height: 0.9}
styles:
  db:   {kind: ellipse, fill: "#C5E0B4"}
  gate: {kind: diamond, fill: "#FFE699", height: 1.1}
  ext:  {fill: "#F4B183"}
nodes:
  - {id: fw,  label: Perimeter FW, style: ext}
  - {id: sw,  label: Core Switch}
  - {id: sql, label: SQL AG Primary, style: db}
  - {id: cab, label: "CAB approved?", style: gate}
edges:
  - {from: fw,  to: sw,  label: 10Gb}
  - {from: sw,  to: sql, label: "TDS 1433"}
  - {from: sw,  to: cab, dashed: true}
```

```bash
python scripts/diagram_from_spec.py spec.yaml -o network.vsdx
# writes network.vsdx AND network.svg (preview)
```

Then **look at the SVG preview before handing anything over.** It is the only
way to catch overlapping shapes, overflowing labels, or an upside-down layout
without a Visio install. Rendering it to PNG and viewing it takes one command:

```bash
python -c "import cairosvg; cairosvg.svg2png(url='network.svg', write_to='p.png', output_width=900)"
```

### Spec fields

| Key | Notes |
|---|---|
| `page.direction` | `TB` or `LR`. Ranks flow along this axis. |
| `page.width` / `height` | Inches. Omit — it auto-sizes to content. |
| `styles` | Named bundles of `kind`/`fill`/`line`/`width`/`height`/`font_size`. |
| `nodes[].kind` | `box` `rounded` `ellipse` `diamond` `hexagon` `triangle` `parallelogram` |
| `nodes[].x` / `y` | Inches, **bottom-left origin**. Overrides layout. |
| `edges[]` | `from` `to` `label` `dashed` `arrow` `color` |

### Path B invocation

Convert the spec to JSON first (the PowerShell script does not parse YAML):

```powershell
.\scripts\New-VisioDiagram.ps1 -SpecPath .\spec.json `
    -OutputPath C:\temp\net.vsdx -Stencil PERIPH_U.VSSX -AutoLayout
```

## Step 4 — verify before delivering

Never hand over a `.vsdx` you have not checked:

```bash
python scripts/verify_vsdx.py network.vsdx
```

This checks OPC structure (parts present, `[Content_Types].xml` ordering) with
stdlib only, then installs `vsdx` if needed and round-trips the file through the
real Visio parser, listing every shape with its text and coordinates.

| Exit | Meaning |
|---|---|
| 0 | Parses cleanly |
| 1 | Broken — see `references/vsdx-format.md` §7 for symptom → cause |
| 2 | Could not verify (no `vsdx`, or bad arguments) |

**Be honest about the residual risk.** Exit 0 proves the file parses; it does
not prove Visio opens it, because Visio is stricter than any third-party parser
and is not available here. Ask the user to open it once and report back rather
than calling it verified. On exit 2, say **unverified** explicitly.

## Gotchas that will bite

| Gotcha | Fix |
|---|---|
| Y axis runs **upward** from bottom-left | Flip Y for any screen/SVG conversion. Most common visual bug. |
| Font size is in **inches**, not points | 10pt = `10/72`. The writer handles this; hand-written XML must too. |
| YAML labels containing `?`, `:`, `#` | Quote them: `label: "CAB approved?"`. Unquoted breaks the parse. |
| `[Content_Types].xml` must be the first ZIP entry | The writer enforces it. Do not rebuild the zip naively. |
| Long labels overflow diamonds/triangles | Widen the shape or add a newline — Visio wraps to the text block, not the outline. |
| Orphaned `VISIO.EXE` after COM runs | `ReleaseComObject` + `[GC]::Collect()` in a `finally`. Otherwise the output file stays locked. |
| COM under a service account | Fails `0x80080005`. Use Path A for anything automated. |

## Reading or editing an existing .vsdx

For extraction, or for the template + data pattern (a corporate-stencil template
whose shapes get retitled), the `vsdx` package is the right tool (`python scripts/ensure_deps.py vsdx`) — that is what
it is genuinely good at:

```python
from vsdx import VisioFile
with VisioFile('template.vsdx') as v:
    page = v.get_page(0)
    page.find_shape_by_text('HOSTNAME').text = 'sql-prod-01'
    v.save_vsdx('out.vsdx')
```

This preserves corporate stencils and themes that Path A cannot reproduce. If
the user has an approved template, prefer this over generating from scratch.

## References

Load these only when needed — they are detailed:

- `references/vsdx-format.md` — OOXML part layout, the Cell model, geometry
  sections, glue semantics, and a symptom→cause table. Read before adding a new
  shape type, gradients, layers, or debugging an "unreadable content" error.
- `references/com-automation.md` — Visio COM object model, stencil/master
  lookup, glue, layout cells, export, and COM cleanup. Read before touching
  Path B.
