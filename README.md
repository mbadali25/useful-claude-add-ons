# useful-claude-add-ons

An internal repository of [Claude Code](https://docs.claude.com/en/docs/claude-code) Skills, and eventually plugins, built for easy distribution to the team. It also doubles as a Claude Code **plugin marketplace** ([`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)) — see [`MARKETPLACE.md`](MARKETPLACE.md) to add it and install skills directly.

## Get started

New machine? Run the prerequisite installer for your OS, then install the skills you need:

```bash
git clone git@github.com:mbadali25/useful-claude-add-ons.git
cd useful-claude-add-ons

# Windows (elevated PowerShell)
.\scripts\install-prerequisites.ps1

# Linux
./scripts/install-prerequisites.sh
```

Full walkthrough, verification steps, and troubleshooting: [`INSTALLATION.md`](INSTALLATION.md).

## Documentation

| Doc | What's in it |
|---|---|
| [`INSTALLATION.md`](INSTALLATION.md) | Prerequisite install scripts (Windows/Linux), installing skills, verification, troubleshooting. |
| [`MARKETPLACE.md`](MARKETPLACE.md) | Adding this repo (and the team's other marketplaces) to Claude Code, installing/updating/removing plugins. |
| [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md) | Required structure, frontmatter, and style for any skill in this repo. |
| [`Skill-Pipeline.md`](Skill-Pipeline.md) | Author → validate → review → merge → release → distribute lifecycle for a skill change. |
| [`SECURITY.md`](SECURITY.md) | Reporting a vulnerability, credential-handling policy, install-script trust boundary. |
| [`CHANGELOG.md`](CHANGELOG.md) | Notable changes to this repo, dated. |

## Skills

The canonical, always-current version of this section lives in [`skills/README.md`](skills/README.md) — it's reproduced here so it's visible without an extra click.

<!-- BEGIN skills/README.md -->

Each subdirectory in [`skills/`](skills/) is a self-contained [Claude Code Skill](https://docs.claude.com/en/docs/claude-code/skills) — a `SKILL.md` plus any `references/`, `scripts/`, or `assets/` it needs. Claude auto-discovers a skill's `SKILL.md` frontmatter (`name` + `description`) and decides when to invoke it; you don't call these directly.

See [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md) for how a skill in this repo must be structured, and [`Skill-Pipeline.md`](Skill-Pipeline.md) for how a new or changed skill gets from a draft to something your team can install.

### Overview

| Skill | Category | What it does | Invocation |
|---|---|---|---|
| [`aws-opensearch`](skills/aws-opensearch) | Cloud / Infra | Diagnose and remediate an Amazon OpenSearch Service managed domain over SigV4 — cluster health, unassigned shards, reindex, ISM/ILM, snapshots — with dry-run guards on destructive calls. | Automatic |
| [`bitbucket`](skills/bitbucket) | SCM / DevOps | Git over HTTPS with Atlassian API tokens plus the Bitbucket Cloud REST API — PRs, pipelines, comments, branches. | Automatic |
| [`checkpoint-email`](skills/checkpoint-email) | Security | Check Point Email Security (Harmony Email & Collaboration / Avanan) — search entities, triage phishing/malware/DLP/BEC, remediate with a dry-run gate. | Automatic |
| [`cloudflare`](skills/cloudflare) | Cloud / Networking | Cloudflare v4 API — DNS, zones, cache purge, WAF/rulesets, page rules, SSL/TLS, Workers/KV/R2, Zero Trust, analytics. | Automatic |
| [`drata`](skills/drata) | Compliance | Drata Public API — controls, monitoring tests, evidence, personnel, policies, frameworks, risks, vendors, assets across US/EU/APAC regions. | Automatic |
| [`i-have-adhd`](skills/i-have-adhd) | Productivity | Reshapes Claude's output for ADHD-friendly reading — leads with the next action, numbers steps, suppresses tangents. Persists for the session once invoked. | Manual — `/i-have-adhd` |
| [`intune-graph`](skills/intune-graph) | Endpoint Mgmt | Microsoft Intune via Microsoft Graph — device lookup/troubleshooting, compliance and configuration profiles, Win32/LOB app deployment, bulk report exports. | Automatic |
| [`mermaid-svg-bitbucket`](skills/mermaid-svg-bitbucket) | Docs / DevOps | Pre-renders Mermaid diagrams to committed SVG so they display in Bitbucket Cloud, which never adopted native ```mermaid``` fences. | Automatic |
| [`sophos-central`](skills/sophos-central) | Security | Sophos Central API — endpoint management (isolate, scan, tamper protection), alert triage, SIEM export, XDR/Live Discover, firewall management. | Automatic |
| [`wazuh-onprem`](skills/wazuh-onprem) | Security / SIEM | Self-hosted Wazuh across all four surfaces — Server API, Indexer API, Dashboard saved-objects API, and `ossec.conf` over SSH. | Automatic |

"Automatic" means Claude decides to invoke the skill on its own when the conversation matches the skill's `description` trigger — no slash command needed. "Manual" means the skill sets `disable-model-invocation: true` and must be invoked explicitly (e.g. `/i-have-adhd`).

### Adding a new skill

1. Read [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md).
2. Create `skills/<skill-name>/SKILL.md` (kebab-case directory name matching the `name:` frontmatter field exactly).
3. Follow [`Skill-Pipeline.md`](Skill-Pipeline.md) to validate, review, and register the skill in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) so the team can install it.
4. Add a row to the table above **and** to [`skills/README.md`](skills/README.md) — keep both in sync.

<!-- END skills/README.md -->

## License

See [`LICENSE`](LICENSE).
