---
description: List every crew role - which are active in this repo, what model backs each, and what is available but off
allowed-tools: Bash, Read
---

Answer "who is actually on this crew, and who could be" — for this repo, right
now. Report only; never enable or disable a role. That is `/crew:scale`.

## Step 1 — read both sides

`.crew/config.json` -> `roles` is who is **active here**. The agent files in the
plugin are who **exists at all**. The gap between them is the useful part of
this report, and it is invisible from either source alone.

```bash
CFG=.crew/config.json
python3 - "$CFG" "${CLAUDE_PLUGIN_ROOT}/agents" <<'PY'
import json, os, re, shutil, sys
cfg = json.load(open(sys.argv[1]))
active = set(cfg.get("roles", []))
qa, dev = cfg.get("qa", {}), cfg.get("dev", {})

rows = []
for fn in sorted(os.listdir(sys.argv[2])):
    if not fn.endswith(".md"):
        continue
    name = fn[:-3]
    head = open(os.path.join(sys.argv[2], fn), encoding="utf-8").read(1200)
    model = (re.search(r"^model:\s*(\S+)", head, re.M) or [None, "?"])[1]
    desc = (re.search(r"^description:\s*(.+)", head, re.M) or [None, ""])[1]
    rows.append((name, model, name in active, desc[:60]))

print(f"{'role':<16}{'model':<10}{'active':<9}what it does")
print("-" * 78)
for name, model, on, desc in rows:
    print(f"{name:<16}{model:<10}{'yes' if on else 'no':<9}{desc}")

print(f"\ntier: {cfg.get('tier')}   active: {len(active)} of {len(rows)}")
print(f"qa  -> {qa.get('provider')}  order {qa.get('order')}")
print(f"dev -> {dev.get('provider')}")
for tool in ("codex", "copilot"):
    print(f"{tool:<10}{'on PATH' if shutil.which(tool) else 'NOT FOUND'}")
PY
```

## Step 2 — say what the gaps mean

A bare list is not the answer. For each of these, say it in one line:

- **Inactive roles that this repo's code would exercise.** A repo with
  migrations and no `dba`, or a web UI and no `browser-tester`, has a hole. Name
  it; do not enable it.
- **Tier 2 roles.** `dba` and `docs-writer` are off by default and are enabled
  through `/crew:scale`, not by hand-editing `roles`.
- **Roles that are not Claude agents at all.** QA review and, when configured,
  implementation run through external providers. They will not appear in the
  agents table above, and someone reading only that table would conclude this
  crew has no reviewer. Print them explicitly from the config.
- **A provider that is configured but not on `PATH`.** That role is not staffed,
  whatever the config says. This is the report's most important line when it
  fires, because everything downstream still looks green.

## Step 3 — point at the next command

End with the one that fits what you found, and nothing else:

| If | Say |
|---|---|
| a role is missing that the code needs | `/crew:scale` to review crew size |
| the model backing a role is wrong | `/crew:model` to change it |
| a provider is configured but absent | `/crew:model` to see it probe, then install or repoint it |
| nothing is wrong | say that plainly and stop |

Do not recommend all four. A report that ends in a menu is a report that made
no judgement.
