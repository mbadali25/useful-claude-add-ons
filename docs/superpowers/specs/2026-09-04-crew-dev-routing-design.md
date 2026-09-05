# crew: complexity-based dev routing

**Status: DRAFT — design presented, not yet approved. Deferred behind the agent upgrade.**

Date: 2026-09-04
Schema: 2 -> 3

## Problem

`dev` has exactly one provider and one model. There is no way to send a simple
one-file ticket to a cheap coding-tuned model and an architectural change to a
stronger one. `secondOpinion.provider` accepts only `gemini|local|none`, so a
Copilot-hosted model cannot serve as the design partner either.

## Decisions taken

| Question | Answer |
|---|---|
| How is complexity decided? | Explicit ticket field wins; PM classifies when absent |
| How does `family()` find the author family? | Read the tier actually recorded at dispatch |
| Default for existing repos | Routing off; behaviour byte-identical until enabled |

## Config shape

```json
"dev": {
  "provider": "claude",
  "routing": {
    "enabled": false,
    "default": "standard",
    "tiers": {
      "simple":   { "provider": null, "model": null },
      "standard": { "provider": null, "model": null },
      "complex":  { "provider": null, "model": null }
    }
  },
  "codex":   { "model": null, "reasoningEffort": null },
  "copilot": { "model": null }
}
```

A `null` in a tier falls back to `dev.provider` / `dev.<provider>.model`.

Nested tier blocks are safe: `crew_state.merge_defaults` is **fully recursive**
(it calls itself whenever both sides are dicts, `crew_state.py:499`). Its
docstring claims "Recurses one level" and is wrong — fix the docstring as part
of this work.

## Tier resolution

In order, first hit wins:

1. The ticket's explicit `complexity` field (`simple|standard|complex`)
2. The PM's classification at dispatch
3. `routing.default`

## Self-review guard

At dispatch, crew records `work.dev.{tier,provider,model}` in work state.
`family()` reads that instead of `dev.copilot.model`. With no dispatch recorded,
fall back to the current read and label the result as such, so `/crew:model` on
a clean tree still reports honestly.

Consequence to accept: when the `standard` tier runs `kimi-k3` and
`qa.copilot.model` is also `kimi-k3`, the guard correctly bars it and review
falls through to codex. The Kimi QA pin only fires on tickets built by claude or
codex.

## Migration (2 -> 3)

In `crew_upgrade.upgrade_config`: add the `routing` block with
`enabled: false`, and copy the existing `dev.provider` + `dev.<provider>.model`
into `tiers.standard`. `enabled: false` bypasses the tier path entirely and
`family()` uses the old read, so every existing repo behaves identically until
someone opts in.

Note `crew_state.py:558` — `upgradeNeeded = schema < SCHEMA_CURRENT`. Bumping
`SCHEMA_CURRENT` makes every existing crew repo report "upgrade needed" at
session start. The migration is mandatory, not optional.

## Setup guidance

- `skills/crew-setup/phases.md` — a new phase offering routing during `/crew:init`
- `commands/upgrade.md` — prompt after the migration runs

## Blast radius

Code: `crew_state.py`, `crew_config.py`, `crew_upgrade.py`,
`templates/config.template.json`.
Prose: `commands/model.md`, `commands/review.md`, `commands/work.md`,
`agents/pm.md`, `skills/crew-setup/phases.md`, `skills/crew-providers/SKILL.md`.
Docs: `plugin/crew/README.md`, `plugin/PLUGINS.md`, `CHANGELOG.md`.
Version: bump in **both** `plugin/crew/.claude-plugin/plugin.json` and
`.claude-plugin/marketplace.json`, to the same value, in the last commit.

## Related requirement: crew owns the Copilot model, and sets it up

The Copilot CLI writes `.github/copilot/settings.json` (e.g.
`{"model": "kimi-k3"}`) whenever `--model` is passed, and that file then pins
the model for anyone running `copilot` in the repo. That shadows crew's own
`qa.copilot.model` / `dev.copilot.model` silently — two sources of truth for
one decision, and the file wins because crew passes `--model` per call.

Required:

- crew is the single source of truth for the Copilot model. `.github/copilot/`
  is gitignored so a stray write cannot shadow it.
- `/crew:init` and `/crew:upgrade` guide the model choice rather than leaving
  the user to discover the config key. That means naming which models are
  actually available on this machine, not a hardcoded list — model ids churn,
  and `crew-providers/SKILL.md` already records two that died that way.
- The probe is cheap and should be mechanised: `copilot -p "say ok" --model <id>`
  returns `Model "<id>" from --model flag is not available` before it bills
  anything. An empty prompt short-circuits before validation, so the probe needs
  a real one.
- Verified on this machine 2026-09-04: `kimi-k3` and `kimi-k2.7-code` are
  available; bare `kimi-k2.7`, `kimi-k2`, `kimi-k3-thinking` and `kimi-k3-code`
  are not.

## Related requirement: fallbacks, per-role Codex models, and a Codex advisor

Requested 2026-09-04, for the version after 0.15.0. Same config surface as the
routing work above, so it should land with it rather than as a separate schema
change.

**1. Every role that speaks through a non-Claude provider needs a declared
fallback.** Today a provider that is missing, unauthorised, or pinned to a model
name that has since been retired fails at the call site, and `crew-providers`
already records two model names that died exactly that way
(`gemini-3.1-pro-preview`, `mai-code-1-flash`). The fallback is
**`claude-sonnet-5`** for now. Make the value configurable rather than hardcoding
it — the whole reason this requirement exists is that model names churn.

The fallback must be *announced*, never silent. A review that quietly ran on the
fallback looks identical to one that ran on the pinned model, and the difference
matters most exactly when the pin was chosen to get an independent family onto
the diff. Note that `qa.order` already provides fallback *between providers*;
this is fallback *within* a provider whose model is unavailable, which is a
different failure and is currently unhandled.

**2. Codex model must be configurable per role, not once globally.**
`qa.codex.model` and `dev.codex.model` already exist as separate keys, so the
shape is there; what is missing is that nothing else can name a Codex model, and
`reasoningEffort` is not exposed everywhere it applies.

**3. A higher-end Codex as advisor.** `secondOpinion.provider` currently accepts
only `gemini`, `local` or `none`, so Codex cannot serve as the design partner at
all. Adding `codex` there is the change. Two constraints that are not optional:

- `secondOpinion.sendsCode` is `false` by design and the `planner` agent refuses
  to send source regardless. A paid Codex seat is not a free tier training on
  prompts, so `sendsCode: true` is *arguable* here in a way it is not for Gemini
  — but it is a deliberate decision, not a default to drift into.
- The self-review guard reads the author family from `family()`. Codex resolves
  to the `gpt` family, so a Codex advisor and a Codex QA reviewer are the same
  family reviewing the same work. The guard must cover the advisor slot too, or
  the independence it protects is lost for the design opinion.

## Tests

- `tests/test_upgrade.py` — a v2 config migrates to v3 with identical effective behaviour
- `tests/test_crew_config.py` — template still equals `default_config()` byte-for-byte
- New: tier resolution precedence (explicit > PM > default)
- New: `family()` from recorded work state, and its no-dispatch fallback
- `scripts/check-marketplace.py` green
