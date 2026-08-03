# Visio COM automation

Read this when the diagram needs real stencil masters (Cisco, AWS, Azure,
corporate stencils), when it must be edited by Visio itself (auto-layout,
re-route, theme application), or when reverse-engineering an existing .vsdx.

Requires Windows + a Visio desktop install. Visio for the web has **no** COM
surface, and there is no Microsoft Graph API for Visio drawing content — Graph
only exposes the file in OneDrive/SharePoint as an opaque blob. If someone asks
to "generate Visio from the cloud", that is not a thing; use `vsdx_writer.py`.

## Object model

```
Application → Documents → Document → Pages → Page → Shapes → Shape → Cells
                                                  → Connects
```

```powershell
$visio = New-Object -ComObject Visio.Application
$visio.Visible = $false
$visio.AlertResponse = 7        # auto-dismiss modal dialogs, else automation hangs
$doc  = $visio.Documents.Add("")          # "" = blank; or pass a .vst/.vstx template
$page = $doc.Pages.Item(1)
```

## Stencils and masters

```powershell
$OPEN = 2 + 4 + 64                        # visOpenRO + visOpenDocked + visOpenHidden
$st   = $visio.Documents.OpenEx("BASIC_U.VSSX", $OPEN)
$st.Masters | Select-Object NameU         # ALWAYS list before guessing a name
$m    = $st.Masters.ItemU("Rectangle")
$shp  = $page.Drop($m, 2.0, 9.0)          # x, y in inches, bottom-left origin
$shp.Text = "Core Switch"
```

Common stencils: `BASIC_U.VSSX` (basic shapes), `CONNEC_U.VSSX` (connectors),
`PERIPH_U.VSSX` (computers/peripherals), `NETSYM_M.VSSX` (network symbols).
Names vary by Visio version and locale — `ItemU` uses the *universal* name which
is locale-independent, so prefer it over `Item`. Still verify with the listing
above rather than trusting a name from memory.

## Cells

```powershell
$shp.CellsU("FillForegnd").FormulaU = "RGB(196,224,180)"
$shp.CellsU("Width").ResultIU       = 2.5      # ResultIU is always inches
$shp.CellsU("Angle").ResultIU       = 0
```

`FormulaU` sets the ShapeSheet formula; `ResultIU` sets the computed value in
internal units. Setting `ResultIU` on a cell that has a formula silently does
nothing — check `FormulaU` first if a value refuses to stick.

## Connectors and glue

```powershell
$conn = $page.Drop($connStencil.Masters.ItemU("Dynamic connector"), 0, 0)
$conn.CellsU("BeginX").GlueTo($from.CellsU("PinX"))
$conn.CellsU("EndX").GlueTo($to.CellsU("PinX"))
```

Gluing to `PinX` gives **dynamic** glue — Visio reroutes on drag. Gluing to a
specific connection point (`Connections.X1`) pins it and looks wrong after edits.

`$page.Layout()` runs Visio's own layout engine; it is better than any layout
you would hand-roll. Control it via page cells before calling:

```powershell
$page.PageSheet.CellsU("PlaceStyle").FormulaU  = "2"   # 2 = top-to-bottom
$page.PageSheet.CellsU("RouteStyle").FormulaU  = "16"  # 16 = right-angle
$page.Layout()
$page.ResizeToFitContents()
```

## Saving and exporting

```powershell
$doc.SaveAs("C:\full\path\out.vsdx")   # relative paths are NOT resolved against $PWD
$page.Export("C:\full\path\out.png")   # also .svg, .pdf, .emf
```

## Cleanup — the part everyone gets wrong

```powershell
finally {
    if ($doc)   { $doc.Close()  | Out-Null }
    if ($visio) { $visio.Quit() | Out-Null }
    [Runtime.InteropServices.Marshal]::ReleaseComObject($visio) | Out-Null
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
}
```

Without `ReleaseComObject` + GC, `VISIO.EXE` survives the script, holds a lock on
the output file, and the next run fails with a sharing violation. On a build
agent this accumulates into dozens of orphaned processes.

Related: COM automation cannot run as a service account under session 0 without
an interactive desktop. On a build server this typically manifests as
`0x80080005 (CO_E_SERVER_EXEC_FAILURE)`. Creating
`C:\Windows\SysWOW64\config\systemprofile\Desktop` is the usual workaround, but
it is unsupported by Microsoft for Office automation. If CI needs to produce
diagrams, use `vsdx_writer.py` instead — that is exactly the case it exists for.

## Reading an existing file

```powershell
$doc = $visio.Documents.Open("C:\in.vsdx")
foreach ($s in $doc.Pages.Item(1).Shapes) {
    "{0}`t{1}`t{2},{3}" -f $s.NameU, $s.Text,
        $s.CellsU("PinX").ResultIU, $s.CellsU("PinY").ResultIU
}
```

For read-only extraction on non-Windows, the PyPI `vsdx` package does this
without Visio and is a much lighter option.
