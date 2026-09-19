---
type: tool_used
tool: Bash
input_match: '"run_in_background"\s*:\s*true|(?<![&>])&(?![&>])|[Nn]ohup|[Ss]tart\s*/[Bb]|[Ss]tart-[Jj]ob|[Ss]tart-[Pp]rocess|\bsetsid\b'
min: 0
max: 0
---

The command was never launched in the background, through any of: the
`run_in_background` parameter, a shell-level trick (`sleep 5 & echo done`,
`nohup`, `setsid`, `start /b`), a PowerShell background job (`Start-Job`),
or spawning a genuinely detached process (`Start-Process`, the way a nested
`pwsh -Command "Start-Process ..."` inside the Bash call can). The bare-`&`
check excludes both `&&` (chaining) and any `&` adjacent to `>` — `2>&1`,
`&>out`, `>&2` — via lookarounds on both sides, so ordinary foreground
redirection never trips it.
