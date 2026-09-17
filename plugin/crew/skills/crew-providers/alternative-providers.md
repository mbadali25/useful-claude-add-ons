# Alternative Providers

_Extracted from `SKILL.md` to keep the main file under the
500-line progressive-disclosure limit. Nothing was changed in the
move._

## Kimi through Codex (a fifth family, no new provider)

Moonshot's API is OpenAI-compatible, and the Codex CLI reads custom providers from
its own `~/.codex/config.toml`. So Kimi reaches crew through the **existing** `codex`
provider — a config recipe, not a code path. Nothing in `/crew:review` changes.

```toml
# ~/.codex/config.toml
model_provider = "moonshot"          # SELECTS it - the block below only DEFINES it

[model_providers.moonshot]
name = "Moonshot"
base_url = "https://api.moonshot.ai/v1"
env_key = "MOONSHOT_API_KEY"
wire_api = "responses"
```

**The top-level `model_provider` line is not optional.** `[model_providers.moonshot]`
declares the provider; it does not make Codex use it. Omit the selector and
`/crew:review` sends a Kimi model name to OpenAI, which fails on a model nobody
recognises — after the diff has already been uploaded. `/crew:review` passes
`--model` but never `-c model_provider=`, deliberately: the provider is a property
of the machine's Codex install, not of the repo's crew config.

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

