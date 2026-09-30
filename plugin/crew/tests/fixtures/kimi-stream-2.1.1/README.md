# Kimi Code 2.1.1 stream-json fixtures

`ok.jsonl`, `ok.stderr.txt` and `ok.exit` are CAPTURED: the owner's one real
run of the command in T-0028's plan, step 3, on 2026-09-25 -

    kimi -p "Reply with exactly: PROBE_OK" -m kimi-code/k3 --output-format stream-json

Stdout is `ok.jsonl`, stderr `ok.stderr.txt` (empty), and the exit status
`ok.exit` (`0`). The owner replaced the run's real session id, everywhere it
appeared, with the placeholder `00000000-0000-0000-0000-fixture00001`. It was
committed only after `api_key`, `sk-`, `eyJ`,
`bearer` and `authorization` all grep empty, case-insensitively, in the three
captured files (this README names them, so it matches).

The captured stream is three lines: a `{"role": "meta", "type":
"system.version"}` record, the `{"role": "assistant", "content": "PROBE_OK"}`
answer, then a `{"role": "meta", "type": "session.resume_hint"}` record whose
`content` is a string too. `kimi_probe.final_message` reads only the
`role: assistant` line; `kimi_probe.classify` is tested against all three
files.

NOT captured: tool-call and tool-result lines, `turn.step.retrying`, a 401, a
quota error, and a failed turn. Those shapes come from the 2.1.1 bundle's
`PromptJsonWriter`, read as source text. In 2.1.1 a non-completed turn is
thrown (`formatNativeTurnFailure`), which is expected to reach stderr and a
non-zero exit rather than a stdout record; the fake `kimi`'s `turnfail` mode
emits a `{"role": "meta", "type": "turn.failed", "error": {...}}` record,
and that record is SYNTHESISED.
