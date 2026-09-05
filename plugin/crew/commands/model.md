---
description: Show or change which model backs each crew role, and probe that it actually answers
allowed-tools: Bash, Read, Edit
---

Read, validate and write the model configuration in `.crew/config.json`.

Argument: `$ARGUMENTS`. Empty means **report only** — never write on a bare
`/crew:model`. A dotted path plus a value means set that one key.

## Step 1 — report what is actually in effect, PER ROLE

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root . --models
```

One row per **role**, not one per block. `qa.roles.review` and `qa.roles.smoke`
can be different models from different families, and a block-level row hides
that completely — the same argument that already forced one row per QA
candidate rather than a single line reading `auto / (cli default)`, applied one
level down. The command reads the layered config (`~/.claude/crew/config.json`
under `.crew/config.json`), so the values it prints are the effective ones.

Read out all five things it reports, and do not summarise any of them away:

| It prints | What it means |
|---|---|
| provider, model, family per role | which CLI and which model back that role, and which family that speaks as |
| `source` — `role-pin` or `block-default` | whether the `roles` table decided it, or the block's own `provider` did |
| `fallback armed: <model>` | what that role falls back to if its pinned model has been retired |
| `BARRED — same family as the author` | the self-review guard is currently refusing that role |
| the `qa.order fall-through` block | **what reviews the diff instead**, once the bars above are applied |

**Never report the bars without the fall-through.** A barred role does not stop
`/crew:review`; it makes it walk `qa.order` for a provider whose family is not
the author's. Four `BARRED` rows and nothing else tells the reader the alarming
half and withholds the useful one. The last line of that block is the answer:
either `-> \`copilot\` answers for any role barred above`, or

> `NO INDEPENDENT REVIEWER` — every candidate is unreachable or speaks as the
> family that wrote the diff. `/crew:review` falls back to the `qa-reviewer`
> subagent and **labels the result same-family**. It runs; it does not count as
> an independent review.

Say that second one in full whenever it fires. A same-family review that nobody
flagged is indistinguishable from a real one in the log, and that is exactly
the state this design exists to make visible.

**Model names, not wire ids.** The report writes `Kimi 2.7 (kimi-k2.7-code)`;
say it that way. The id is a debugging detail, and for Kimi 2.7 the two are not
the same string — see step 2.

### The author family, and how it was decided

The report's first line names the author family and where it came from:

- **`recorded at dispatch`** — a real dispatch was recorded in
  `.work/dispatch.json`, and the guard is judging what actually ran.
- **`READ FROM CONFIG - no dispatch recorded`** — nothing has run in this
  checkout, so the report fell back to reading `dev` out of the config. Say so
  in those words. That describes the **next** dispatch, not the diff in front
  of the reviewer, and presenting it as the author family would be a guess
  dressed as a fact.

A dispatch is recorded by whatever ran the work:

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_state.py --root . \
  --record-dispatch dev --role developer --provider codex --model gpt-6-astra
```

`.work/dispatch.json` is gitignored during `/crew:init` — it describes one
checkout on one machine, and a committed copy would travel to a colleague and
claim a dispatch that never happened there.

Presence on `PATH` is not working auth. If the user is deciding anything based
on this, make one real call per configured provider — `codex exec
--skip-git-repo-check "reply OK"`, `copilot -p "reply OK" -s` — and report what
came back. A provider that fails silently turns every gate green, which is the
one failure mode this whole design exists to prevent.

## Step 2 — validate before writing

Refuse the write and say why, rather than writing something that will fail later
at the one moment it matters:

| Key | Rule |
|---|---|
| `qa.codex.reasoningEffort` | one of `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. Codex rejects anything else with a 400 |
| `qa.copilot.model` | must not start with `claude-`. Copilot's own default is `claude-sonnet-4.6`; a Claude reviewer of Claude-written code is the failure this ordering exists to avoid |
| `qa.provider` | `auto`, or a name that appears in `qa.order` |
| `dev.provider` | `claude`, `codex`, or `copilot` |
| `dev.copilot.model` | required when `dev.provider` is `copilot` — the review interlock in step 3 cannot work without knowing which family wrote the code |
| `qa.roles.<role>` / `dev.roles.<role>` | a `{"provider": ..., "model": ...}` object. Any role name is accepted, including one crew does not ship |
| `qa.fallback` / `dev.fallback` | a model name. Default `claude-sonnet-5`; configurable precisely because model names churn |
| any `model` | never validated against a hardcoded list. Model catalogs churn; a name this command has never heard of is the user's business |

That last row is deliberate. Do not add an allowlist of model names here — GPT-5
and Sonnet 4 are already retired, and a command that refuses a model because it
shipped before that model existed is worse than no validation. The display names
the report prints are a *display* map for readability, never a gate on a write.

### The one id where the name and the value differ

Probed 2026-09-05: **Kimi 2.7's wire id is `kimi-k2.7-code`.** Bare
`kimi-k2.7` is rejected — `Model "kimi-k2.7" from --model flag is not
available` — while `kimi-k2.7-code` answers. Kimi 3 is `kimi-k3`, where the
name and id happen to match, which is exactly why the 2.7 mismatch has to be
stated rather than assumed. Write the display name in prose to the user; write
the suffixed id into the config.

### `fallback` is not the same thing as `qa.order`

`qa.order` already handles a provider that is **missing or unauthorised**.
`fallback` handles a provider that answers fine while the **model** it was
pinned to has been retired — `crew-providers` records two names that died
exactly that way. That failure was unhandled before schema 3.

**A fallback that fires is announced, never silent.** A review that quietly ran
on the fallback looks identical to one that ran on the pin, and the difference
matters most exactly when the pin was chosen to get an independent family onto
the diff. If the fallback lands on the author's own family, say that too — it
runs, and it does not count as an independent review.

### Setting `qa.copilot.model` turns Copilot ON — check it works first

This key is the switch. While it is `null`, `/crew:review` skips the Copilot rung
and says so cleanly once per review. Setting it makes every review *attempt*
Copilot, so setting it before Copilot actually works converts one clean skip
message into a recurring error on a path the user believes is now covered.

Copilot has three gates and installing the CLI clears only the first. Before
writing this key, confirm all three and report which you actually checked:

| Gate | Check | Failure |
|---|---|---|
| 1. Policy allows the CLI | `gh api orgs/<org>/copilot/billing --jq '.cli'` → `enabled` | account setting, no API can write it; enterprise policy overrides the org's |
| 2. CLI holds its own token | `~/.copilot/config.json` has `lastLoggedInUser` | run `copilot login`; a set `GH_TOKEN`/`GITHUB_TOKEN`/`COPILOT_GITHUB_TOKEN` silently overrides it |
| 3. A real call returns | `copilot -p "reply OK" -s; echo $?` → exit 0 | check the exit code, never a pipe's |

Gates 1 and 2 produce the **same** error text, so check 1 before concluding 2.
`bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/providers.sh` reports gate 2
and both override hazards without making a call.

If the user asks for Copilot and a gate fails, say which one and what unblocks it,
then leave `qa.copilot.model` unset. A skipped provider that announces itself is
strictly better than a configured one that errors — write the key when it works,
not when it is wanted.

## Step 3 — the interlock: guard FIRST, pin SECOND

**The family that wrote the code may not review it.** The order of evaluation
is not an implementation detail and must be described in this order everywhere:
evaluate the family guard, *then* apply the pin to whatever survives. A pin
that beat the guard would let a model review its own family's diff, which is
the one thing this interlock exists to prevent.

After any change to `dev.provider` or to a `dev.roles` pin, say plainly which
QA rungs it just disqualified:

| Author family | Disqualified from QA | What review drops to |
|---|---|---|
| `claude` | `claude` (the `qa-reviewer` fallback) | unchanged — Codex or Copilot |
| `gpt` (any codex model) | every codex pin, whichever model | Copilot pinned off Claude, else `qa-reviewer` |
| `kimi` (a Kimi Copilot pin) | that Copilot pin | the next family in `qa.order` |

The family comes from `model.split("-")[0]`. That is why **`gpt-5.6-sol` and
`gpt-5.6-luna` are the same `gpt` family as `gpt-6-astra`**: a diff written by
codex bars all three, and QA falls to claude or kimi. Codex QA pins therefore
apply to work codex did **not** write.

Say this consequence out loud whenever the QA pins are named:

> Pinning the senior developer to `codex` means most dev work is
> codex-authored, so the Sol and Luna QA pins fire on claude-authored work and
> comparatively rarely elsewhere. That may be exactly what you want. It should
> not be something you discover from a review log.

Do not silently rewrite `qa.order` or a `roles` pin to enforce this. Tell the
user what the consequence is and let them decide — a config that quietly
reorders itself is one nobody can reason about later. `/crew:review` applies
the exclusion at review time regardless of what the file says.

If a change leaves no independent reviewer at all, say so in those words before
writing.

## Step 4 — write, then prove it

Edit only the named key. Preserve every sibling — this file carries tracker,
notify, obsidian and platform blocks that have nothing to do with models.

Then re-run step 1 and show the new state. A config change nobody verified is
a claim, not a change.

## Examples

```
/crew:model                                      # report only, per role
/crew:model qa.codex.reasoningEffort high        # harder reviews
/crew:model qa.copilot.model kimi-k2.7-code      # Kimi 2.7 - the suffix is required
/crew:model dev.provider codex                   # then read step 3 out loud
/crew:model dev.roles.developer '{"provider": "codex", "model": "gpt-6-astra"}'
/crew:model qa.roles.review '{"provider": "codex", "model": "gpt-5.6-luna"}'
/crew:model dev.fallback claude-sonnet-5
```

A per-role pin belongs in `.crew/config.json` when it is a decision about this
project, and in `~/.claude/crew/config.json` when it is a decision about this
person or this machine — which is the usual case for a model table.
`/crew:config` is the guided walkthrough for the second, and the repo layer
still overrides it.
