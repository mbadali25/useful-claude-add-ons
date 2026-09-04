---
description: Show or change which model backs each crew role, and probe that it actually answers
allowed-tools: Bash, Read, Edit
---

Read, validate and write the model configuration in `.crew/config.json`.

Argument: `$ARGUMENTS`. Empty means **report only** — never write on a bare
`/crew:model`. A dotted path plus a value means set that one key.

## Step 1 — report what is actually in effect

Read `.crew/config.json`. Print the effective configuration as a table, and
probe each provider rather than reporting what the file claims:

```bash
CFG=.crew/config.json
python3 - "$CFG" <<'PY'
import json, shutil, subprocess, sys
cfg = json.load(open(sys.argv[1]))
qa, dev = cfg.get("qa", {}), cfg.get("dev", {})
print(f"{'role':<22}{'provider':<12}{'model':<28}{'effort'}")
print(f"{'-'*22}{'-'*12}{'-'*28}{'-'*8}")
for label, blk in (("qa (review)", qa), ("dev (implement)", dev)):
    p = blk.get("provider", "?")
    sub = blk.get(p, {}) if isinstance(blk.get(p), dict) else {}
    print(f"{label:<22}{p:<12}{str(sub.get('model') or '(cli default)'):<28}"
          f"{sub.get('reasoningEffort') or '-'}")
print(f"\nqa.order: {qa.get('order')}")
for tool in ("codex", "copilot"):
    print(f"{tool:<10}{'on PATH' if shutil.which(tool) else 'NOT FOUND'}")
PY
```

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
| any `model` | never validated against a hardcoded list. Model catalogs churn; a name this command has never heard of is the user's business |

That last row is deliberate. Do not add an allowlist of model names here — GPT-5
and Sonnet 4 are already retired, and a command that refuses a model because it
shipped before that model existed is worse than no validation.

## Step 3 — the interlock, whenever `dev.provider` is not `claude`

**The family that wrote the code may not review it.** After any change to
`dev.provider`, say plainly which QA rungs it just disqualified:

| `dev.provider` | Disqualified from QA | What review drops to |
|---|---|---|
| `claude` | `claude` (the `qa-reviewer` fallback) | unchanged — Codex or Copilot |
| `codex` | `codex` | Copilot pinned off Claude, else `qa-reviewer` |
| `copilot` | whichever family `dev.copilot.model` names | the next family in `qa.order` |

Do not silently rewrite `qa.order` to enforce this. Tell the user what the
consequence is and let them decide — a config that quietly reorders itself is
one nobody can reason about later. `/crew:review` applies the exclusion at
review time regardless of what the file says.

If setting `dev.provider` to something that leaves no independent reviewer at
all, say so in those words before writing.

## Step 4 — write, then prove it

Edit only the named key. Preserve every sibling — this file carries tracker,
notify, obsidian and platform blocks that have nothing to do with models.

Then re-run step 1 and show the new state. A config change nobody verified is
a claim, not a change.

## Examples

```
/crew:model                                      # report only
/crew:model qa.codex.reasoningEffort high        # harder reviews
/crew:model qa.copilot.model gemini-3.1-pro-preview
/crew:model dev.provider codex                   # then read step 3 out loud
/crew:model dev.codex.model gpt-5.6-sol
```
