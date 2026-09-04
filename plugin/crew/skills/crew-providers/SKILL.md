---
name: crew-providers
description: Set up, verify, and invoke external model providers - Codex or GitHub Copilot for QA review, Gemini for design second opinions. Use when the user says set up codex, set up copilot, set up gemini, add a reviewer, add a design partner, configure providers, wire up the API key, or asks about free tiers, rate limits, model families, which model to use for a role, or why a provider call is failing.
---

# Providers

Two external roles, deliberately different in what they are allowed to see.

| Role | Provider | Sees your code? | Why |
|---|---|---|---|
| QA review | Codex **or** Copilot | Yes — the diff | Review is worthless without the actual change |
| Design opinion | Gemini | **No** — brief only | Free tiers train on prompts |

That asymmetry is the whole design. Do not collapse it for convenience.

## The one rule that decides every QA provider question

**A reviewer is only worth having if it is a different model family from the
author.** Crew's code is written by Claude. A Claude reviewer shares its blind
spots, so it agrees with itself and the gate goes green on defects nobody saw.

This is why `qa.order` exists and why every provider block carries its own
`model` key read at call time. It is also why a provider that *can* be pointed at
Claude — Copilot — is refused unless you pin it away from Claude. The danger is
not that such a review is bad; it is that it looks exactly like a good one.

| Family | Reached via |
|---|---|
| Anthropic | the `qa-reviewer` fallback, or Copilot pinned to `claude-*` |
| OpenAI | Codex, or Copilot pinned to `gpt-*` |
| **Google** | Copilot pinned to `gemini-*` |
| **Microsoft MAI** | Copilot pinned to `mai-*` |

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

## GitHub Copilot (QA review, alternative to Codex)

Copilot CLI is not a fourth model — it is a **gateway to four families** on one
subscription. That is its entire value here: it is the only way to put a Google
or Microsoft model on your diff without a second vendor account.

### Check

```bash
command -v copilot && copilot --version
```

### Set up

```bash
npm install -g @github/copilot
copilot login
```

Copilot will silently borrow a `gh` token if one exists (precedence:
`COPILOT_GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN`). A `gh` token minted without
Copilot entitlement authenticates fine and then fails at the policy check, which
reads like a billing problem and is not one — run `copilot login` so the CLI holds
its own token.

Then make one real call before trusting it:

```bash
copilot -p "reply with exactly: PROBE_OK" -s
```

### Pin the model, always

`qa.copilot.model` is **required**. `/crew:review` skips Copilot entirely when it
is unset, because the CLI's own default is `claude-sonnet-4.6` — the author's
family. Pin a family neither the author nor Codex provides:

| Model | Family | Credit multiplier |
|---|---|---|
| `gemini-3.1-pro-preview` | Google | 1x |
| `mai-code-1-flash` | Microsoft MAI | low |
| `gemini-3-flash` | Google | 0.33x |

Do not hardcode any of these in a command. Model strings churn — GPT-5 and Sonnet
4 are already retired — so keep the value in `.crew/config.json` and read it at
call time. A call failing with a model-not-found error means the catalog moved;
list current models with `copilot help` and update the config rather than
debugging the request.

### Costs

Copilot bills in **AI Credits**, pooled across the org, and the multiplier is per
model. Included base models (GPT-5 mini, GPT-4.1) are 0x — unmetered. A 1x model
at a Business seat's 1,900 credits/month is roughly 1,900 reviews; a 30x model is
roughly 63. Pinning the model is therefore a cost control as well as an
independence control.

Paid overage is **off by default** on Copilot Business: when credits run out,
calls fall back to base models rather than billing. Confirm that before running a
review loop — an org that has opted into overage has no such brake.

### When it fails

| Symptom | Cause |
|---|---|
| `Access denied by policy settings` | Copilot CLI policy is off. If the org's toggle is greyed out, the org is under an enterprise and the policy is set at **enterprise** level — fix it at `github.com/settings/enterprises`, not org settings |
| Authenticates then refuses | A borrowed `gh` token without Copilot scope — run `copilot login` |
| Reviews agree with Claude suspiciously often | `qa.copilot.model` is a `claude-*` string; you have a same-family reviewer |

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

## Kimi through Codex (a fifth family, no new provider)

Moonshot's API is OpenAI-compatible, and the Codex CLI reads custom providers from
its own `~/.codex/config.toml`. So Kimi reaches crew through the **existing** `codex`
provider — a config recipe, not a code path. Nothing in `/crew:review` changes.

```toml
# ~/.codex/config.toml
[model_providers.moonshot]
name = "Moonshot"
base_url = "https://api.moonshot.ai/v1"
env_key = "MOONSHOT_API_KEY"
wire_api = "responses"
```

**`wire_api = "responses"` is load-bearing, and `"chat"` is not a fallback — it is a
hard parse error.** Codex deprecated the `chat/completions` protocol in December 2025
and removed it in early 2026; on 0.146.0 the string `wire_api = "chat"` fails config
loading outright, naming the line and telling you to use `responses`. That is the good
failure — it stops before the run rather than mid-review.

This is the one fact that decides whether the route exists at all, because Moonshot is
usually described as a *chat/completions* API. It serves both:

```
POST https://api.moonshot.ai/v1/responses        -> 401   (endpoint exists, needs auth)
POST https://api.moonshot.ai/v1/chat/completions -> 401   (endpoint exists, needs auth)
POST https://api.moonshot.ai/v1/models           -> 404   (control: a route that is absent)
```

The 404 control matters. Without it, a 401 on `/v1/responses` proves nothing — you
cannot tell "exists but unauthenticated" from a gateway that 401s everything.

```json
"qa": { "provider": "codex", "codex": { "model": "kimi-k2.7-code" } }
```

Verify with a real call before trusting it, the same as any other provider:

```bash
export MOONSHOT_API_KEY=...
codex exec --skip-git-repo-check -c model_provider=moonshot \
  --model kimi-k2.7-code "reply with exactly: PROBE_OK"
```

Expect `warning: Model metadata for <name> not found. Defaulting to fallback metadata`
on any model Codex does not ship a profile for. That is not an error and the call still
runs, but it does mean Codex is guessing context window and token limits — so confirm
the model name against Moonshot's current catalog rather than trusting that the command
returned. **Model names move; a wrong one warns rather than fails**, which is exactly
the shape of failure this skill exists to catch.

**Why bother.** Review independence is a function of model *family*, not leaderboard
rank. Moonshot is a lineage that is neither the author's nor Codex's default, and
`kimi-k2.7-code` runs about $0.95 per million input tokens — $0.19 cached — which
makes a per-diff review effectively free. A cheaper, slightly weaker reviewer from a
genuinely different lineage catches defects a stronger same-family one will not.

**What to be honest about.** Moonshot's published coding numbers come from its own
benchmark suites with no independent SWE-bench Verified or Terminal-Bench run behind
them. Treat them as vendor claims. That matters less here than it would for a
*writing* role — you are buying a different set of blind spots, not a higher score —
but do not repeat the figures as though someone neutral produced them.

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

Kimi's coding model ships **open weights** (Modified MIT), so the same family that
option one reaches over the API can also run entirely on your own hardware — the
only listed route that is both a different family *and* keeps the diff on the box:

```bash
ollama pull kimi-k2.7-code   # confirm the current tag; names move
ollama run kimi-k2.7-code "..."
```

It is a 1T-parameter MoE with 32B active. Quantised community builds run on serious
consumer hardware; the full-precision weights do not. Check what your machine can
actually hold before planning a gate around it, and fall back to a smaller local
coder rather than letting the gate silently stop running.

---

## An external implementer (`dev.provider`)

Codex or Copilot can write the code, not just review it. `dev.provider` ships as
`claude` and only moves when someone asks:

```json
"dev": {
  "provider": "codex",
  "codex": { "model": "gpt-5.6-sol", "reasoningEffort": "high" },
  "copilot": { "model": null }
}
```

Reach for this when the work plays to a different model's shape rather than
because a change felt hard. The published split is consistent enough to plan
around: GPT-5.6 Sol leads on short single-shot tasks, Kimi K3 on long-horizon
multi-session work, Claude on multi-file refactors in a large existing codebase.

**The interlock is the whole cost of this feature.** The family that wrote the
diff is struck from the QA walk — `/crew:review` does it from `dev.provider` at
review time, without consulting `qa.order`. So setting `dev.provider` to `codex`
on a machine with no Copilot and no Gemini leaves only the `qa-reviewer`
fallback, and setting it to `copilot` with a `claude-*` model leaves the review
to Codex or to nothing. Check what is left *before* you switch, with
`/crew:model`, which prints exactly that.

`dev.copilot.model` is required when `dev.provider` is `copilot`. Without it the
interlock cannot tell which family wrote the code, and it would have to either
strike nothing or strike everything — both wrong.

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
