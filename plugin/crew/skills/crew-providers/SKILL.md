---
name: crew-providers
description: Set up, verify, and invoke external model providers - Codex for QA review and Gemini for design second opinions. Use when the user says set up codex, set up gemini, add a reviewer, add a design partner, configure providers, wire up the API key, or asks about free tiers, rate limits, which model to use for a role, or why a provider call is failing.
---

# Providers

Two external roles, deliberately different in what they are allowed to see.

| Role | Provider | Sees your code? | Why |
|---|---|---|---|
| QA review | Codex | Yes — the diff | Review is worthless without the actual change |
| Design opinion | Gemini | **No** — brief only | Free tiers train on prompts |

That asymmetry is the whole design. Do not collapse it for convenience.

---

## Codex (QA review)

### Check

```bash
command -v codex && codex --version
```

### Set up

Install the Codex CLI and authenticate per its own docs — the flow changes, so
follow the current instructions rather than anything written here. Then verify
with a real call before trusting it:

```bash
echo "print hello world in python" > /tmp/crew-probe.txt
codex exec --skip-git-repo-check "Read /tmp/crew-probe.txt and reply with one line of code only"
```

If that returns code, the wiring works. If it hangs, prompts for login, or
returns an auth error, fix that now — a QA gate that silently fails is worse
than no gate, because everything goes green.

### Invocation

`/crew:review` handles this. The pattern: write the diff to a file, have Codex
return one line per defect, read back only the findings. The diff never
re-enters your context.

### Costs

Codex is not free. This is the one place worth paying, because review is where
defects get caught and a different model family is what makes the review
independent. If the budget is zero, the `qa-reviewer` agent is the fallback and
`/crew:review` will tell you every time it runs.

---

## Gemini (design second opinion)

### Two paths

**Gemini CLI** — simpler if you already have it. Check with `command -v gemini`.
Confirm the non-interactive flag with `gemini --help` rather than assuming; the
CLI's flags have changed between versions, and a wrong flag drops you into an
interactive session that hangs the turn.

**Direct API** — get a key from Google AI Studio, no card required. Store it as
`GEMINI_API_KEY` in your shell profile, never in the repo, never in
`.crew/config.json`.

```bash
curl -sS "https://generativelanguage.googleapis.com/v1beta/models/${CREW_GEMINI_MODEL}:generateContent" \
  -H "x-goog-api-key: ${GEMINI_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d @.work/briefs/request.json > .work/briefs/reply.json
```

### Do not hardcode the model name

Free catalogs churn, and models get retired without much notice. Keep the model
in `.crew/config.json` as `secondOpinion.model` and read it at call time. When a
call fails with a model-not-found error, that is the cause — list current models
and update the config rather than debugging the request.

### Free tier reality

Generous for this use case: design questions are a handful of calls a week, not
a hot path. Rate limits are per-minute and per-day and will not bite you here.

The cost is data. Free tiers are funded by prompts and generally train on them.
That is acceptable for an abstracted brief and unacceptable for source code,
which is why `planner` works from a brief and shows it to you before sending.

If your organisation prohibits sending anything to an unpaid third party, set
`secondOpinion.provider` to `local` and point it at Ollama, or to `none` and
accept single-opinion planning. Both are legitimate. Say which one is in effect.

---

## Local models (private second opinion)

If the code must stay on the machine but you still want an independent voice:

```bash
ollama pull qwen3-coder     # or devstral, or whatever is current
ollama run qwen3-coder "..." 
```

Weaker than a frontier model, but genuinely independent and nothing leaves the
box. This is the honest answer for a free *security* reviewer, where the payload
would otherwise be your diff plus a list of your exploitable weaknesses.

---

## Configuration

```json
"secondOpinion": {
  "provider": "gemini",
  "mode": "cli",
  "model": "gemini-2.5-flash",
  "keyEnv": "GEMINI_API_KEY",
  "sendsCode": false
}
```

`provider`: `gemini`, `local`, or `none`.
`mode`: `cli` or `api`.
`sendsCode`: must stay `false` for any provider on a free tier. If someone sets
it true, the `planner` agent still refuses — the brief is the interface.

---

## Verification

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/providers.sh
```

Reports what is installed, what authenticates, and what a real round-trip call
returns. Run it during setup and again whenever a provider starts behaving
strangely. Presence on `PATH` is not the same as working auth, and the
difference shows up as a silently-passing gate.
