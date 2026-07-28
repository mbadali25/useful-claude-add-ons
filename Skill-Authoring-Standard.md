# Skill Authoring Standard

This is the structural and style contract every skill in [`skills/`](skills/) must meet before it moves through the [Skill Pipeline](Skill-Pipeline.md). It's derived from the conventions already in use across this repo's skills (`bitbucket`, `cloudflare`, `wazuh-onprem`, etc.) — follow the existing skills as worked examples alongside this document.

## 1. Directory layout

```
skills/<skill-name>/
├── SKILL.md            # required — the only file Claude reads to decide whether to invoke the skill
├── references/          # optional — deep-dive docs Claude reads on demand, not preloaded
│   └── auth.md
├── scripts/              # optional — helper scripts/clients the skill shells out to
│   └── client.py
└── assets/               # optional — templates, config files, fixtures the skill needs
    └── config.json
```

Rules:

- **`<skill-name>` is kebab-case** and matches the `name:` field in `SKILL.md` exactly. No nesting — `skills/foo/SKILL.md`, never `skills/foo/foo/SKILL.md`. Marketplace tooling and Claude's own discovery both assume this shape.
- Put anything long, reference-only, or rarely needed in `references/` rather than inline in `SKILL.md`. `SKILL.md` should be readable in one sitting; `references/*.md` are pulled in only when the task needs that specific detail.
- Scripts in `scripts/` should be self-contained (stdlib-only Python, or a thin curl/bash wrapper) so they run without a separate install step. If a script needs third-party packages, say so at the top of `SKILL.md` and in the script's own header comment.
- Never commit credentials, tokens, or real tenant/account identifiers in `assets/` or anywhere else — see [`SECURITY.md`](SECURITY.md).

## 2. Frontmatter

```yaml
---
name: skill-name
description: >
  What this skill does, then when to invoke it. See section 3.
---
```

| Field | Required | Notes |
|---|---|---|
| `name` | Yes | Kebab-case, matches the directory name. |
| `description` | Yes | Single most important field — see section 3. Plain string or YAML `>` block; both are used in this repo. |
| `disable-model-invocation` | No | Set to `true` only when the skill should never trigger automatically (e.g. an output-style skill like `i-have-adhd` that must be invoked with `/skill-name`). Default is automatic invocation. |
| `license` | No | Set when a skill's content carries its own license distinct from the repo `LICENSE`. |
| `metadata` | No | Free-form; used today for tagging (`hermes.tags`, `category`, `related_skills`) in `i-have-adhd`. Don't invent new metadata schemas without updating this document. |

## 3. Writing the `description`

The `description` is the *only* thing Claude sees before deciding to invoke a skill — get this wrong and the skill either never fires or fires on the wrong conversations. Every skill in this repo follows the same two-part shape:

1. **What it does** — one or two sentences, naming the concrete system/API/product and the concrete operations covered (list them; don't say "manage things").
2. **When to use it** — "Use this skill whenever the user mentions X, Y, Z — even if they don't say 'API'" plus 2-4 concrete phrasings a real user would type, including ones that don't name the product directly (symptom-based: "why is this laptop non-compliant", not just "Intune"). Where relevant, name the error codes or symptoms that should also trigger it (401/403/429, specific HTTP codes, specific error strings).

Bad: `description: Helps with AWS OpenSearch stuff.`

Good (trimmed from `aws-opensearch/SKILL.md`):
> Connect to and work with an Amazon OpenSearch Service managed domain over its public HTTPS endpoint using SigV4 (IAM) request signing. Covers read/inspect ... and remediation ... with dry-run safety rails on anything destructive. Use this skill whenever the user mentions AWS OpenSearch, Amazon OpenSearch Service, an OpenSearch/Elasticsearch domain on AWS, an es.amazonaws.com endpoint ... or wants to query, diagnose, fix, or automate anything on their managed OpenSearch estate — even if they don't say "API" or "SigV4". Also use it when troubleshooting 403s from an OpenSearch domain or writing scripts against an es.amazonaws.com host.

Keep it dense — every clause should add a trigger phrase or a disambiguator, not restate the previous clause.

## 4. Body structure

Recommended section order (skip sections that don't apply; don't force a section that has nothing to say):

1. **Title + one-paragraph summary.** What the skill talks to and how (protocol, base URL, host pattern).
2. **Disambiguation callout**, if this skill is easily confused with a sibling (e.g. `aws-opensearch` vs. `wazuh-onprem`'s indexer, or `wazuh-onprem`'s three separate APIs). A short table or blockquote is enough.
3. **Quick start / connection setup.** The exact first commands to run — get a token, verify a credential, resolve a region/tenant/zone. Every skill in this repo front-loads this because auth setup is where automation actually dies.
4. **Reference map.** If `references/` has more than one file, a table of "task → which reference file" so the skill doesn't have to inline everything.
5. **Common tasks, end to end.** 2-4 worked examples in "user says X → do Y then Z" form, using real endpoint paths and payload shapes, not placeholders.
6. **Safety rails.** Explicit call-outs for anything destructive, irreversible, or credential-adjacent: dry-run flags, confirm-before-mutating rules, "never echo this token," "never force-push," etc. Required for any skill that can mutate remote state.

## 5. Style rules

- Write in second person imperative to the model ("Get a token", "Never hardcode credentials"), not narrative prose.
- Use real endpoint paths, real header names, real env var names. No `<placeholder>` where a concrete example is possible — use `{zone_id}`-style path templates only for the part that's genuinely per-call.
- Prefer a runnable helper script over inline curl repeated five times. If a script exists, `SKILL.md` should show 3-6 example invocations, not reproduce the script's internals.
- No marketing language, no "this powerful skill", no restating what the reader can already see in the frontmatter description.
- Tables over prose whenever comparing more than two things (regions, auth modes, API surfaces).

## 6. Before merging a new or changed skill

Run through this checklist (also enforced by the [Skill Pipeline](Skill-Pipeline.md)):

- [ ] Directory is `skills/<kebab-case-name>/SKILL.md`, no double-nesting.
- [ ] `name:` matches the directory name exactly.
- [ ] `description` covers what + when, with concrete trigger phrases, per section 3.
- [ ] No secrets, tokens, real hostnames/tenant IDs, or customer data anywhere in the skill's files.
- [ ] Any mutating operation has a documented dry-run path or an explicit confirm-before-acting rule.
- [ ] `references/` used for anything long enough to not need preloading; `SKILL.md` stays skimmable.
- [ ] Added to the table in [`skills/README.md`](skills/README.md).
- [ ] Registered as a plugin entry in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json).
- [ ] `CHANGELOG.md` updated under `Unreleased`.
