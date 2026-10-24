param([string]$Wt, [string]$Tag, [int]$CapSeconds = 700)
$ErrorActionPreference = 'Continue'
$out = "D:\temp\claude\stop-$Tag.out"
$err = "D:\temp\claude\stop-$Tag.err"
$meta = "D:\temp\claude\stop-$Tag.meta"
$cpu0 = (Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 1 -MaxSamples 1).CounterSamples[0].CookedValue
$load0 = (Get-Process | Measure-Object).Count
$start = Get-Date
$p = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', 'D:\temp\claude\run-stop-gate.cmd', $Wt) `
  -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow -PassThru
$killed = 'no'
if (-not $p.WaitForExit($CapSeconds * 1000)) {
  $killed = "yes-capped-at-${CapSeconds}s"
  taskkill.exe /PID $p.Id /T /F | Out-Null
  $p.WaitForExit(30000) | Out-Null
}
$end = Get-Date
$cpu1 = (Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 1 -MaxSamples 1).CounterSamples[0].CookedValue
$wall = ($end - $start).TotalSeconds
@(
  "tag=$Tag"
  "worktree=$Wt"
  "head=$(git.exe -C $Wt rev-parse HEAD)"
  "started=$($start.ToString('yyyy-MM-ddTHH:mm:ss.fffK'))"
  "ended=$($end.ToString('yyyy-MM-ddTHH:mm:ss.fffK'))"
  "wall_seconds=$([math]::Round($wall,3))"
  "exit_code=$($p.ExitCode)"
  "capped=$killed"
  "cap_seconds=$CapSeconds"
  "cpu_total_pct_before=$([math]::Round($cpu0,1))"
  "cpu_total_pct_after=$([math]::Round($cpu1,1))"
  "process_count_before=$load0"
  "logical_processors=$([Environment]::ProcessorCount)"
) | Set-Content -LiteralPath $meta -Encoding utf8
"DONE $Tag wall=$([math]::Round($wall,1))s exit=$($p.ExitCode) capped=$killed"
