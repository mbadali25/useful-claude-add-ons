# Kimi Code 2.1.1 stream-json fixtures

**`placeholder-ok.jsonl` is SYNTHESISED, not captured.** It was written by hand
from the shape `PromptJsonWriter` emits in the Kimi Code 2.1.1 bundle, read as
source text on 2026-09-25: one JSON object per line, `{"role": "assistant",
"content": "<text>"}` for assistant text, `{"role": "tool", ...}` for tool
results, and `{"role": "meta", "type": "system.version" | "turn.step.retrying" |
"session.resume_hint", ...}` for everything else. No Kimi request was made to
produce it. `review_verdict.kimi_final_message` is tested against it only until
the captured run below lands.

The captured fixture is `ok.jsonl` (plus `ok.stderr.txt` and `ok.exit`), taken
by the owner from ONE real run of the command in T-0028's plan, step 3, and
committed only after `api_key`, `sk-`, `eyJ` and the credential filename all
grep empty in it. When it lands, point
`test_kimi_final_message_parses_the_placeholder_fixture` at `ok.jsonl` and
delete this placeholder.

A failed turn was not observed: in 2.1.1 a non-completed turn is thrown
(`formatNativeTurnFailure`), which is expected to reach stderr and a non-zero
exit rather than a stdout record. The fake `kimi`'s `turnfail` mode emits a
`{"role": "meta", "type": "turn.failed", "error": {...}}` record; that record
is SYNTHESISED too.
