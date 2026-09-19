---
type: tool_used
tool: Bash
input_match: '"run_in_background"\s*:\s*true|"command"\s*:\s*"(?:[^"\\]|\\.)*?((?<![&>])&(?![&>])|\bnohup\b|\bstart\s*/[Bb]\b|\bStart-Job\b|\bStart-Process\b|\bsetsid\b)'
min: 0
max: 0
---

The command was never launched in the background, through any of: the
`run_in_background` parameter, a shell-level trick (`sleep 5 & echo done`,
`nohup`, `setsid`, `start /b`), a PowerShell background job (`Start-Job`),
or spawning a genuinely detached process (`Start-Process`). Every trigger
except `run_in_background` is scoped to inside the `command` argument's own
value (matched from `"command":"` forward, consuming escaped characters
correctly so an internal `\"` doesn't end the scope early) — never the
`description` field, which is free-text metadata a model can phrase however
it likes ("Run integration check & report output" is not a shell command
and was never being executed). The bare-`&` check also excludes both `&&`
and any `&` adjacent to `>` via lookarounds on both sides.
