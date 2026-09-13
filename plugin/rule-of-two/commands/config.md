---
description: Show which two models the Rule of Two will use, where that came from, and whether both can actually run
allowed-tools: Bash, Read
---

Show the resolved Rule of Two configuration.

```bash
PY=""
for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || { echo "no python3/python/py on PATH" >&2; exit 1; }
"$PY" "${CLAUDE_PLUGIN_ROOT}/scripts/rule_of_two.py" --repo-root . config
```

Report four things, in this order:

1. **The two models**, and which family each resolves to. Read them from
   `dispatch_order_claude` (pin first, then fallback) and `config.codex.pin` -
   those are the values a review actually dispatches on. A family of `UNKNOWN`
   is not a problem with the report; it means the cross-family check cannot be
   made, and any review run in that state will say "could not tell" rather
   than claiming independence.

   Note the two Claude spellings, which are different namespaces and are not
   interchangeable. `pin` and `fallback` are dispatch aliases - what the Agent
   tool and agent frontmatter accept. `pin_model_id` and `fallback_model_id`
   are the full ids a CLI `--model` flag takes, recorded so the report can
   name the model that was asked for. Changing one without the other is a
   config that says one thing and does another.

2. **Where the config came from** - `built-in defaults`, a repo-level
   `.rule-of-two.json`, or `~/.claude/rule-of-two/config.json`. Name the file.
   A setting argued about without naming which layer it came from can only be
   believed, not checked.

3. **Whether a `codex` executable was found** - and nothing more than that.
   Report `codex_found` as discovery, never as readiness. It is `shutil.which`
   and nothing else: authentication, whether the configured model still
   exists, and account entitlement all fail at dispatch, not here. Say so,
   and quote `codex_readiness` rather than paraphrasing it into a claim it
   does not make.

   If `codex_found` is false, say plainly that a review right now would
   produce a one-reviewer report, and that the report would say so itself. If
   it is true, say a reviewer *may* run - the first thing that actually
   establishes it is the review.

4. **What this config is not.** It is this plugin's own. It never reads
   crew's `qa.order`, `author_families`, or provider list, and changing
   crew's config changes nothing here.

To change it, write `.rule-of-two.json` at the repo root:

```json
{
  "claude": {
    "pin": "fable",
    "fallback": "opus",
    "pin_model_id": "claude-fable-5-1",
    "fallback_model_id": "claude-opus-5"
  },
  "codex": { "pin": "gpt-6-astra", "timeout_seconds": 900 }
}
```

Only the keys present are overridden; the rest fall back to the built-in
defaults. If the user wants a machine-wide setting instead of a per-repo one,
that is `~/.claude/rule-of-two/config.json`, and the repo file wins over it.
