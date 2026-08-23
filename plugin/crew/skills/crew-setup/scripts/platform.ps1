# Native Windows equivalent of platform.sh. Read-only. Emits the same JSON shape.
function Have($n) { if (Get-Command $n -ErrorAction SilentlyContinue) { "true" } else { "false" } }

$os = "windows"
$wsl = if (Get-Command wsl -ErrorAction SilentlyContinue) { "available" } else { "no" }
$distros = ""
if ($wsl -eq "available") {
  $distros = (wsl --list --quiet 2>$null) -join "," -replace "`0",""
}

$crlf = "false"
foreach ($f in @("scripts/smoke.sh")) {
  if (Test-Path $f) {
    $bytes = [IO.File]::ReadAllBytes((Resolve-Path $f))
    if ($bytes -contains 13) { $crlf = "true" }
  }
}

@"
{
  "os": "$os",
  "wsl": "$wsl",
  "wslDistros": "$distros",
  "repoFilesystem": "native",
  "shell": "powershell",
  "tools": {
    "git": $(Have git), "docker": $(Have docker), "python": $(Have python),
    "node": $(Have node), "npx": $(Have npx), "dotnet": $(Have dotnet),
    "php": $(Have php), "composer": $(Have composer), "terraform": $(Have terraform),
    "aws": $(Have aws), "az": $(Have az), "psql": $(Have psql),
    "codex": $(Have codex), "bash": $(Have bash)
  },
  "crlfDetected": $crlf
}
"@
