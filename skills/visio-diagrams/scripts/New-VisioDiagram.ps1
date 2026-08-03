<#
.SYNOPSIS
    Build a Visio diagram by driving the Visio COM object model.

.DESCRIPTION
    Use this path (instead of the Python vsdx_writer) when the diagram must use
    real stencil masters -- Cisco/network shapes, AWS/Azure icon sets, or a
    corporate stencil -- or when the output has to be indistinguishable from
    something a person drew by hand. Requires Windows with Visio installed.

    Consumes the SAME JSON spec as diagram_from_spec.py, so a diagram can be
    prototyped cross-platform and then re-rendered with proper masters here.

.PARAMETER SpecPath
    JSON spec file. (Convert YAML to JSON first: this script does not parse YAML.)

.PARAMETER OutputPath
    Destination .vsdx. Must be a full path -- Visio's SaveAs does not resolve
    relative paths against PowerShell's working directory.

.PARAMETER Stencil
    Stencil to pull masters from. Defaults to the built-in basic shapes stencil.
    Examples: BASIC_U.VSSX, PERIPH_U.VSSX, or a full path to a corporate .vssx.

.PARAMETER AutoLayout
    Let Visio lay the diagram out itself instead of using spec coordinates.
    Visio's layout engine is genuinely better than the Python one -- prefer this
    when node positions were not deliberately chosen.

.PARAMETER Visible
    Show the Visio window while building. Useful for debugging, slower.

.EXAMPLE
    .\New-VisioDiagram.ps1 -SpecPath .\net.json -OutputPath C:\temp\net.vsdx -AutoLayout

.NOTES
    Master names differ between Visio versions and locales. If ItemU() throws,
    run: $stencil.Masters | Select NameU  to list what is actually available.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SpecPath,
    [Parameter(Mandatory)][string]$OutputPath,
    [string]$Stencil = "BASIC_U.VSSX",
    [switch]$AutoLayout,
    [switch]$Visible
)

$ErrorActionPreference = 'Stop'

function ConvertTo-Rgb([string]$hex) {
    $h = $hex.TrimStart('#')
    "$([Convert]::ToInt32($h.Substring(0,2),16)),$([Convert]::ToInt32($h.Substring(2,2),16)),$([Convert]::ToInt32($h.Substring(4,2),16))"
}

# Map spec 'kind' values onto stencil master names.
$KindToMaster = @{
    box           = 'Rectangle'
    rounded       = 'Rounded Rectangle'
    ellipse       = 'Ellipse'
    diamond       = 'Diamond'
    hexagon       = 'Hexagon'
    triangle      = 'Triangle'
    parallelogram = 'Parallelogram'
}

# visOpenRO(2) + visOpenDocked(4) + visOpenHidden(64)
$OPEN_FLAGS = 2 + 4 + 64

if (-not (Test-Path $SpecPath)) { throw "Spec not found: $SpecPath" }
$spec = Get-Content $SpecPath -Raw | ConvertFrom-Json

$visio = $null
$doc   = $null
try {
    $visio = New-Object -ComObject Visio.Application
    $visio.Visible = [bool]$Visible
    $visio.AlertResponse = 7   # suppress modal dialogs that would hang automation

    $doc  = $visio.Documents.Add("")
    $page = $doc.Pages.Item(1)
    if ($spec.title) { $page.Name = $spec.title }

    $stencilDoc = $visio.Documents.OpenEx($Stencil, $OPEN_FLAGS)
    $connStencil = $visio.Documents.OpenEx("CONNEC_U.VSSX", $OPEN_FLAGS)
    $connMaster  = $connStencil.Masters.ItemU("Dynamic connector")

    $shapes = @{}
    $i = 0
    foreach ($node in $spec.nodes) {
        $kind = if ($node.kind) { $node.kind }
                elseif ($node.style -and $spec.styles.($node.style).kind) { $spec.styles.($node.style).kind }
                else { 'box' }
        $masterName = if ($KindToMaster.ContainsKey($kind)) { $KindToMaster[$kind] } else { 'Rectangle' }

        try   { $master = $stencilDoc.Masters.ItemU($masterName) }
        catch { throw "Master '$masterName' not in $Stencil. List available names with: `$stencilDoc.Masters | Select NameU" }

        # Placeholder grid; overwritten by AutoLayout or by explicit spec coords.
        $x = if ($null -ne $node.x) { [double]$node.x } else { 2 + ($i % 4) * 2.5 }
        $y = if ($null -ne $node.y) { [double]$node.y } else { 9 - [math]::Floor($i / 4) * 2.0 }

        $shp = $page.Drop($master, $x, $y)
        $shp.Text = if ($node.label) { $node.label } else { $node.id }

        $fill = if ($node.fill) { $node.fill }
                elseif ($node.style -and $spec.styles.($node.style).fill) { $spec.styles.($node.style).fill }
                else { $null }
        if ($fill) { $shp.CellsU("FillForegnd").FormulaU = "RGB($(ConvertTo-Rgb $fill))" }

        $shapes[$node.id] = $shp
        $i++
    }

    foreach ($edge in $spec.edges) {
        $from = $shapes[$edge.from]; $to = $shapes[$edge.to]
        if (-not $from -or -not $to) { Write-Warning "Skipping edge $($edge.from)->$($edge.to): unknown node"; continue }

        $conn = $page.Drop($connMaster, 0, 0)
        # Glue to PinX (not a specific connection point) so Visio reroutes freely.
        $conn.CellsU("BeginX").GlueTo($from.CellsU("PinX")) | Out-Null
        $conn.CellsU("EndX").GlueTo($to.CellsU("PinX"))     | Out-Null
        if ($edge.label)  { $conn.Text = $edge.label }
        if ($edge.dashed) { $conn.CellsU("LinePattern").FormulaU = "2" }
    }

    if ($AutoLayout) {
        $page.Layout() | Out-Null
        $page.ResizeToFitContents() | Out-Null
    }

    $doc.SaveAs($OutputPath)
    Write-Host "Wrote $OutputPath ($($shapes.Count) shapes, $($spec.edges.Count) connectors)"
}
finally {
    if ($doc)   { $doc.Close()  | Out-Null }
    if ($visio) { $visio.Quit() | Out-Null }
    # Without this, an orphaned VISIO.EXE keeps running and holds a file lock.
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($visio) | Out-Null
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
}

