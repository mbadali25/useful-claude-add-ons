# Security Policy

This repo distributes Claude Code Skills and installation tooling internally to the team. Several skills talk to production security/compliance/infrastructure systems (Cloudflare, AWS OpenSearch, Sophos Central, Wazuh, Check Point, Drata, Intune, Bitbucket) and the install scripts execute third-party code (Chocolatey packages, `npx` packages, plugin marketplaces). Treat this repo with the same care as any other internal automation tooling.

## Scope

Covered by this policy:

- Everything under `skills/` — `SKILL.md` files, `references/`, `scripts/`, `assets/`.
- `scripts/install-prerequisites.ps1` and `scripts/install-prerequisites.sh`.
- `.claude-plugin/marketplace.json`.

Not covered: the Claude Code CLI itself, or the third-party services each skill talks to (Cloudflare, AWS, Sophos, etc.) — report issues with those to their respective vendors.

## Supported versions

This is an internally maintained tooling repo, not a versioned software product — there is no LTS/EOL schedule. The `main` branch is the only supported line; always pull the latest before reporting an issue, since skills are corrected in place rather than backported.

## Reporting a vulnerability or security concern

Do **not** open a public GitHub issue for a credential leak, an unsafe destructive action in a skill, or a supply-chain concern in the install scripts.

Instead, email **badalim@anewbiz.net** with:

- Which skill, script, or file.
- What the concern is (leaked secret, missing dry-run gate, unsafe default, malicious/unexpected behavior in a third-party dependency pulled by the install scripts, etc.).
- Reproduction steps if applicable.

Expect an acknowledgement within 2 business days. If a reported issue involves a credential that may have been exposed (e.g. committed by accident), treat it as compromised immediately — rotate it at the source system before waiting on a response here.

## What counts as a security issue in this repo

- **Leaked credentials or real tenant data** in any `SKILL.md`, `references/*.md`, `scripts/*`, or example payload. See [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md) section 6 — this must never happen and is a blocking finding in review.
- **A skill performing a destructive or state-changing action without a dry-run path or explicit confirmation.** Every skill that can mutate a remote system (delete an index, quarantine an email, isolate an endpoint, push a firewall change, force-push git) must gate that action. This is enforced at the [Skill Pipeline](Skill-Pipeline.md) review stage, but report it immediately if you find a gap in a merged skill.
- **Prompt-injection surface** — a skill or reference doc that would cause Claude to execute attacker-controlled instructions found in fetched data (an API response, an email body, a file) without treating it as untrusted content.
- **Supply-chain risk in the install scripts** — the prerequisite scripts run `choco install`, `npx -y <package>`, and `claude plugin install` against several third-party sources (Chocolatey community repo, npm registry, GitHub-hosted plugin marketplaces). If any of those sources is compromised or a package name is typo-squatted, report it — see the pinned-source notes in [`INSTALLATION.md`](INSTALLATION.md).

## Credential handling policy (applies to every skill)

- Credentials are read from environment variables or the OS credential store — never hardcoded, never committed, never logged.
- Scoped/least-privilege credentials (API tokens with narrow scopes, IAM roles with SigV4, OAuth2 client credentials) are preferred over account-wide keys wherever the vendor offers them. Each skill's `references/auth.md` documents which options exist and which is recommended.
- Any script under `scripts/` that accepts a credential must accept it via env var or a credential-store lookup, not as a CLI argument (CLI args land in shell history and process lists).

## Install-script trust boundary

`scripts/install-prerequisites.ps1` and `scripts/install-prerequisites.sh` are run with elevated privileges (they install system packages and a CLI with filesystem/network access). Before running either on a machine you don't fully control:

- Read the script — it's short and unobfuscated by design; don't pipe an unreviewed remote script straight into a shell.
- Know that it will install and run `npx`-fetched packages (`skills`, `claude-mem`, and — only if you tick them — `ctx7`, `@playwright/cli`, `skillui`), fetch and run a third-party shell installer if you tick Strix (`curl -sSL https://strix.ai/install | bash`), and add third-party Claude Code plugin marketplaces (Superpowers, `anthropics/claude-code`, `excalidraw-generator`) — see [`MARKETPLACE.md`](MARKETPLACE.md) section 3 for exactly what each one is and does.
- Know that if you tick the `notify` skill and accept its setup prompt, the script writes a starter `~/.config/notify/config.json` (an existing one is left alone). That file holds a chat id and the *name* of the env var to read the Telegram bot token from — never the token itself, which stays in your environment.
- If your environment has stricter supply-chain requirements (air-gapped, regulated), mirror/vet those packages first rather than running the script as-is.
