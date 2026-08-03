# .vsdx internals (MS-VSDX)

Read this when `vsdx_writer.py` needs extending — new shape types, fills,
gradients, layers, multi-page linking, or when Visio reports a repair prompt.

## Contents
1. Package layout
2. Coordinate system and units
3. The Cell model
4. Geometry sections
5. Connectors and glue
6. Colors, fills, text
7. Failure modes and how to diagnose them

---

## 1. Package layout

A `.vsdx` is a ZIP (OPC package). Minimum viable set:

| Part | Purpose |
|---|---|
| `[Content_Types].xml` | Declares a content type for every part. **Must be the first ZIP entry.** |
| `_rels/.rels` | Package root → `visio/document.xml` |
| `visio/document.xml` | Stylesheets, face names, document settings |
| `visio/_rels/document.xml.rels` | Document → pages, windows |
| `visio/pages/pages.xml` | Page list + PageSheet (size, scale) |
| `visio/pages/_rels/pages.xml.rels` | Each page → its `pageN.xml` |
| `visio/pages/pageN.xml` | `<PageContents>` — the actual shapes |
| `visio/windows.xml` | View state. Optional but Visio expects it. |

Namespaces:
- main: `http://schemas.microsoft.com/office/visio/2012/main`
- relationships: `http://schemas.microsoft.com/visio/2010/relationships/{document,pages,page,windows,masters}`

Masters (`visio/masters/`) are **optional**. Shapes carrying inline `<Section N="Geometry">`
need no master. That is what makes from-scratch generation tractable — skipping
masters removes the single largest chunk of the format.

## 2. Coordinate system and units

- Internal unit is **inches**, always, regardless of the user's UI setting.
- Origin is **bottom-left**. Y increases upward. Anything converting to SVG,
  PNG, or screen coordinates must flip Y — this is the most common visual bug.
- `PinX`/`PinY` are the shape's position *on the page*.
- `LocPinX`/`LocPinY` are the rotation/placement origin *within* the shape.
  Setting them to `Width*0.5` / `Height*0.5` makes PinX/PinY mean "centre",
  which is far easier to reason about than Visio's default corner behaviour.
- Font `Size` is in inches: 10pt = `10/72` = `0.138889`. Passing `10` yields
  a 720pt font and a diagram that looks broken.

## 3. The Cell model

Everything is a `<Cell N="name" V="value" F="formula"/>`.

- `V` is the cached computed value. `F` is the ShapeSheet formula.
- If `F` is present Visio recalculates and overwrites `V` on open.
- Prefer `F` for anything that should survive a resize:
  `<Cell N="LocPinX" V="0.875" F="Width*0.5"/>`
- Omitting `F` is fine for static values (PinX, FillForegnd).

Cells worth knowing:

| Cell | Meaning |
|---|---|
| `PinX` `PinY` | Page position |
| `Width` `Height` | Size |
| `Angle` | Rotation in **radians** |
| `FillForegnd` `FillPattern` | Fill colour; pattern 0 = none, 1 = solid |
| `LineColor` `LineWeight` `LinePattern` | Stroke; pattern 1 = solid, 2 = dashed, 0 = none |
| `Rounding` | Corner radius in inches |
| `VerticalAlign` | 0 top, 1 middle, 2 bottom |
| `ObjType` | 2 marks a shape as a connector (1-D) |
| `EndArrow` `BeginArrow` | Arrowhead style; 0 none, 4 filled |

## 4. Geometry sections

```xml
<Section N="Geometry" IX="0">
  <Cell N="NoFill" V="0"/><Cell N="NoLine" V="0"/>
  <Row T="MoveTo" IX="1"><Cell N="X" V="0" F="Width*0"/><Cell N="Y" V="0" F="Height*0"/></Row>
  <Row T="LineTo" IX="2"><Cell N="X" V="1.75" F="Width*1"/><Cell N="Y" V="0" F="Height*0"/></Row>
  ...
</Section>
```

Row types: `MoveTo`, `LineTo`, `ArcTo`, `Ellipse`, `EllipticalArcTo`, `NURBSTo`,
`PolylineTo`, `SplineStart`/`SplineKnot`, `InfiniteLine`, `RelMoveTo`, `RelLineTo`.

- Close a filled polygon by repeating the first point as the final `LineTo`.
  An unclosed path fills unpredictably.
- `Ellipse` is a single row taking `X Y A B C D` — centre, plus two points on
  the perimeter. It is not a sequence of curves.
- Express coordinates as `F="Width*0.25"` rather than a literal so the shape
  survives being dragged bigger.

To add a new shape kind, append a fraction-coordinate point list to the
`GEOMETRY` dict in `vsdx_writer.py`. Nothing else needs to change.

## 5. Connectors and glue

A connector is a 1-D shape:
- `Width` = length of the line, `Height` = 0
- `Angle` = `atan2(dy, dx)` in radians
- `PinX`/`PinY` = midpoint
- `BeginX/BeginY/EndX/EndY` = the actual endpoints in page coordinates
- Geometry is `MoveTo(0,0)` → `LineTo(Width, 0)`; rotation does the rest

Glue lives in a page-level `<Connects>` block **after** `<Shapes>`:

```xml
<Connect FromSheet="7" FromCell="BeginX" FromPart="9"  ToSheet="1" ToCell="PinX" ToPart="3"/>
<Connect FromSheet="7" FromCell="EndX"   FromPart="12" ToSheet="4" ToCell="PinX" ToPart="3"/>
```

| Value | Meaning |
|---|---|
| `FromPart` 9 | begin point |
| `FromPart` 12 | end point |
| `ToPart` 3 | **dynamic** glue to the whole shape |
| `ToPart` 100+ | static glue to connection point N-100 |

Dynamic glue (`ToPart="3"`) is almost always what you want: Visio then reroutes
the connector when the user drags a shape. Static glue pins the line to one spot
and looks wrong after any edit. Glue is the single reason to emit Visio rather
than an image — do not skip the `<Connects>` block.

## 6. Colors, fills, text

- Colours are `#rrggbb` strings in `V`, or an index into `<Colors>`. Literal hex
  is simpler and avoids maintaining a palette table.
- `FillPattern` must be `1` or the fill colour is ignored.
- Text is a plain `<Text>` child of `<Shape>`. XML-escape it.
- Runs are formatted via `<Section N="Character">` rows; `<Section N="Paragraph">`
  handles alignment (`HorzAlign`: 0 left, 1 centre, 2 right).
- Visio does **not** word-wrap on the geometry outline, only on the text block
  width. Long labels overflow diamonds and triangles — widen the shape or
  insert an explicit newline.

## 7. Failure modes

| Symptom | Cause |
|---|---|
| "Visio found unreadable content" | A part is missing from `[Content_Types].xml`, or a relationship Id does not resolve |
| Opens blank | `pages.xml` `<Rel r:id>` does not match an Id in `pages/_rels/pages.xml.rels` |
| Shapes stacked at origin | `PinX`/`PinY` missing; Visio defaults them to 0 |
| Shapes invisible but selectable | `FillPattern="0"` and `LinePattern="0"` |
| Text enormous | Font `Size` given in points instead of inches |
| Diagram vertically mirrored | Forgot Y-flip when converting to/from screen coordinates |
| Connectors do not follow shapes | `<Connects>` missing, or `ToPart` set to static glue |

Diagnosing: unzip the file and read the XML — it is plain text. Then round-trip
it through the `vsdx` PyPI package (`VisioFile(path)`), which parses real Visio
files and will fail loudly on a structurally broken one. That catches most
errors without needing a Visio install, though it cannot prove Visio itself is
happy — only opening it on Windows does that.
