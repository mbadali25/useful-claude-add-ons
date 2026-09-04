---
description: Show or change which model backs each crew role, and probe that it actually answers
allowed-tools: Bash, Read, Edit
---

Read, validate and write the model configuration in `.crew/config.json`.

Argument: `$ARGUMENTS`. Empty means **report only** — never write on a bare
`/crew:model`. A dotted path plus a value means set that one key.

## Step 1 — report what is actually in effect

Read `.crew/config.json`. Report **one row per QA candidate**, not one row for
`qa`. `auto` is not a provider — it is an instruction to walk `qa.order` — so a
single row reading `auto / (cli default)` names neither the model that would run
nor the candidates that would be passed over, which is the one thing the reader
came here to learn.

```bash
CFG=.crew/config.json
python3 - "$CFG" <<'PY'
import json, shutil, sys
cfg = json.load(open(sys.argv[1]))
qa, dev = cfg.get("qa", {}), cfg.get("dev", {})
dev_p = dev.get("provider", "claude")

def family(provider, blk):
    """Which model family this provider would speak as. codex and a gpt-* Copilot
    are one family, which is why dev.provider=codex bars both."""
    if provider == "claude": return "claude"
    if provider == "codex":  return "gpt"
    m = (blk.get("copilot") or {}).get("model") or ""
    return m.split("-")[0] if m else "?"

barred = family(dev_p, dev)

def describe(p, blk):
    sub = blk.get(p) if isinstance(blk.get(p), dict) else {}
    model = sub.get("model") or ("n/a (subagent)" if p == "claude" else "(cli default)")
    effort = sub.get("reasoningEffort") or "-"
    if family(p, blk) == barred:
        why = f"BARRED: dev.provider is {dev_p}, same family - cannot review itself"
    elif p == "claude":
        why = "eligible (in-session subagent, not a separate process)"
    elif not shutil.which(p):
        why = "NOT on PATH - would be skipped"
    elif p == "copilot" and not sub.get("model"):
        why = "SKIPPED: qa.copilot.model unset, and unpinned Copilot is claude-*"
    else:
        why = "eligible"
    return model, effort, why

pinned = qa.get("provider", "auto")
cands = qa.get("order", []) if pinned == "auto" else [pinned]
print(f"{'qa candidate':<14}{'model':<26}{'effort':<8}status")
print("-" * 92)
ran = False
for p in cands:
    model, effort, why = describe(p, qa)
    mark = ""
    if not ran and why.startswith("eligible"):
        mark, ran = "   <== would run", True
    print(f"{p:<14}{model:<26}{effort:<8}{why}{mark}")

if pinned != "auto":
    print(f"\nqa.provider is PINNED to {pinned}. A failed probe here is an error, not a fallback.")
if not ran:
    print("\nNO ELIGIBLE REVIEWER - /crew:review will stop rather than let the author's "
          "own family review it.")

dsub = dev.get(dev_p) if isinstance(dev.get(dev_p), dict) else {}
dmodel = dsub.get("model") or ("n/a (subagent)" if dev_p == "claude" else "(cli default)")
print(f"\ndev (implement): {dev_p}  model={dmodel}  effort={dsub.get('reasoningEffort') or '-'}")
print(f"author family = {barred}  (this is what is struck from qa above)")
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
