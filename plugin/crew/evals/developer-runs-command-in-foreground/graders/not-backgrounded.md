---
type: tool_used
tool: Bash
input_match: '"run_in_background"\s*:\s*true|(?<!&)&(?!&)|[Nn]ohup|[Ss]tart\s*/[Bb]|[Ss]tart-[Jj]ob'
min: 0
max: 0
---

The command was never launched in the background — not just "never with
`run_in_background: true`", which a shell-level trick (`sleep 5 & echo done`,
`nohup ...`, `start /b ...`, `Start-Job ...`) sails past untouched, since none
of those set that field. The bare-`&` check excludes `&&` (a negative
lookaround on both sides) so the ordinary `sleep 5 && echo done` foreground
form the prompt itself suggests still passes.
