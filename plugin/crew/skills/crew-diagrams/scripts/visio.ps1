<#
  Builds a .vsdx from a simple JSON node/edge description using Visio COM.
  Requires Microsoft Visio installed and licensed on this Windows machine.

    .\visio.ps1 -Detect
    .\visio.ps1 -InputJson docs/diagrams/architecture.json -Output docs/diagrams/out/architecture.vsdx

  JSON shape:
  { "title": "Orders",
    "nodes": [ {"id":"api","label":"Order API"}, {"id":"db","label":"Orders DB"} ],
    "edges": [ {"from":"api","to":"db","label":"writes order"} ] }

  What this produces: real Visio shapes and connectors on a grid layout.
  It is a starting point a human then arranges - not a finished, templated diagram.
#>
param(
  [switch]$Detect,
  [string]$InputJson,
  [string]$Output
)

function Test-Visio {
  try { $v = New-Object -ComObject Visio.Application; $ver = $v.Version; $v.Quit(); return $ver }
  catch { return $null }
}

if ($Detect) {
  $ver = Test-Visio
  if ($ver) { Write-Output "visio: installed (version $ver)" }
  else { Write-Output "visio: NOT installed - use SVG import or draw.io vsdx export instead" }
  exit 0
}

if (-not $InputJson -or -not (Test-Path $InputJson)) { Write-Error "InputJson not found"; exit 1 }
if (-not (Test-Visio)) { Write-Error "Visio is not installed on this machine."; exit 1 }
if (-not $Output) { $Output = [IO.Path]::ChangeExtension($InputJson, ".vsdx") }

$spec = Get-Content $InputJson -Raw | ConvertFrom-Json
$app = New-Object -ComObject Visio.Application
$app.Visible = $false
$doc = $app.Documents.Add("")
$page = $doc.Pages.Item(1)
if ($spec.title) { $page.Name = $spec.title }

# Basic shapes stencil
$stencil = $app.Documents.OpenEx("BASIC_U.VSSX", 4)  # 4 = visOpenDocked/hidden
$rect = $stencil.Masters.ItemU("Rectangle")

$placed = @{}
$i = 0
foreach ($n in $spec.nodes) {
  $col = $i % 3; $row = [math]::Floor($i / 3)
  $x = 2.0 + ($col * 3.0); $y = 9.0 - ($row * 2.0)
  $shape = $page.Drop($rect, $x, $y)
  $shape.Text = $n.label
  $shape.Cells("Width").FormulaU  = "2.2 in"
  $shape.Cells("Height").FormulaU = "0.9 in"
  $placed[$n.id] = $shape
  $i++
}

foreach ($e in $spec.edges) {
  if (-not $placed.ContainsKey($e.from) -or -not $placed.ContainsKey($e.to)) { continue }
  $conn = $page.Drop($app.ConnectorToolDataObject, 0, 0)
  $conn.Cells("BeginX").GlueTo($placed[$e.from].Cells("PinX"))
  $conn.Cells("EndX").GlueTo($placed[$e.to].Cells("PinX"))
  if ($e.label) { $conn.Text = $e.label }
}

$dir = Split-Path $Output -Parent
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
$doc.SaveAs((Resolve-Path -LiteralPath $dir).Path + "\" + (Split-Path $Output -Leaf))
$doc.Close(); $app.Quit()
Write-Output "wrote $Output ($($spec.nodes.Count) nodes, $($spec.edges.Count) edges)"
Write-Output "This is a grid layout starting point. Rearrange in Visio before sharing."
