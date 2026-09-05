# Plugin updates

New capability added under `plugin/`, newest first. Each entry names the version
it landed in, so a reader can tell what their installed copy actually has. For
fixes and internal changes, see [`CHANGELOG.md`](../CHANGELOG.md); this file is
only what is newly *possible*.

Mirrored into [`plugin/README.md`](README.md) and the root
[`README.md`](../README.md) by `scripts/sync-updates.py`. Edit here, then run it.

## obsidian-vault 0.3.0

**Vault profiles.** A vault is either authored, where a person reads it, or
generated, where only Claude greps it, and the right plugin set differs. One
definition in `hooks/scripts/vault_profiles.py` now decides both what to
install and what to strip — two lists would have drifted. `vault_ops.py
profile` reports the detected kind **with the evidence behind it**, never a
config flag you have to set, and always overridable.

The sets, read off working vaults rather than invented: `bridge` is
`obsidian-local-rest-api` alone, the floor for any vault Claude must reach at
all. `graph` adds `code-graph` and nothing else — omnisearch, dataview,
backlinks and text-extractor are the index-building cost, and nothing reads
their output in a vault only Claude greps. `authored` is the fuller human set,
with omnisearch and text-extractor only below 50,000 notes.

Two rules the profile work does not bend. A plugin is confirmed **one at a
time**, because any of them can be load-bearing for hundreds of notes through
a Dataview query, a Templater template or a Breadcrumbs edge — so a bare
`enable-plugin --apply` writes only the bridge floor and every other plugin
needs naming. And **splitting a vault is the last resort, not the first**: the
real limit is index-building plugins rather than note count, a split
permanently breaks every wikilink crossing it, and where one is genuinely
warranted the seam is provenance, not size. The report names the seam and
counts the wikilinks that would break; nothing moves without a yes.

**Note templates, because the contract was enforced but not served.**
`vault_guard.py` blocks a write that violates the six-key frontmatter
contract, and it is right to. But the plugin shipped no templates, so every
conforming note was written by hand and fixed afterwards — a wall with no
door. `templates/` now holds `memory`, `concept`, `decision`, `session`,
`source` and `design`, each verified to pass the guard on the first write, and
`/obsidian-vault:note` creates one. `design` ships as a `type: concept`
variant rather than a new type: the guard has no type enum, so a new type
would have passed while being invisible to the contract's own type keys and to
any Dataview query keyed on them.

**The bridge status tells four states apart.** A dead Obsidian window and a
misconfigured server both produce a silent port, and until now both rendered
as one line: down. They are now `NOT OPEN`, `NO SERVER`, `NOT ANSWERING YET`
and `UP`, plus an explicit `DOWN, CAUSE NOT DETERMINED`. The third matters
most on a large vault, where a socket that accepts but does not answer means
indexing is still running — not a fault to chase.

That last verdict is the point of the change. The previous diagnostic named a
cause with confidence and was wrong, which sent its reader to a file that was
already correct. Guidance is now derived only from evidence the script
actually checked, and where two causes cannot be separated it says so and
names the check that would separate them. Process attribution is honest about
its limits: window titles name a vault on Windows, and on macOS and Linux the
script reports presence and says attribution is undetermined rather than
guessing.

## obsidian-vault 0.2.0

The plugin can now **repair a vault bridge**, where before it could only
describe how. `hooks/scripts/vault_ops.py` is the action layer, dry-run by
default and writing only under `--apply`:

| Subcommand | Does |
|---|---|
| `scan` | Every vault on the machine — path, real ports, whether the REST plugin is installed, whether it is registered |
| `diagnose` | Health verdict per vault, port collisions named first |
| `fix-ports` | Assigns non-colliding ports and writes `data.json` |
| `reload` | `app:reload` over the REST API, so a `data.json` edit actually takes effect |
| `register` | Adds or refreshes each vault's MCP server registration |
| `enable-plugin` | Enables a plugin whose files are already on disk. It does not download one, and no longer claims to |
| `add-vault` | Names a vault in config so `--vault <name>` resolves - the first step of setting one up, not a record of it afterwards |
| `graph-health` | The codegraphs vault's `<org>/<repo>` layout, coverage and staleness |

Two new commands drive it: `/obsidian-vault:repair` acts, and
`/obsidian-vault:install` sets up a vault that has no REST plugin at all.
`/obsidian-vault:doctor` stays read-only and now enforces that with its tool
list rather than asserting it in prose.

**The diagnostic was wrong, and the fix is the point of this release.** Two
vaults declaring the same HTTPS port is not a partial failure: the loser's
plugin fails to start its server at all, which takes its HTTP listener down
with it. That produced three symptoms with one cause — the HTTP port never
listened, the HTTPS port answered with the *other* vault's API key, and it
served the *other* vault's files. The shipped hook blamed
`enableInsecureServer`, which was already on. It now compares ports across
every vault before it blames any flag, and reports a vault with no plugin and
a wrong-vault-answering server as distinct verdicts.

The hook also stopped deriving the HTTPS port as the HTTP port plus one. That
assumption is false in practice — one vault on this machine runs HTTPS *below*
its HTTP port. Both ports are read from the vault's own `data.json`, where
`port` is HTTPS and `insecurePort` is HTTP. The same correction was applied to
`init`, the setup skill and the README, which all taught the plus-one rule.

Two facts worth knowing before touching any of it: `curl -k` reaches the HTTPS
port where Claude Code's Node MCP client rejects the self-signed certificate,
and the plugin reads `data.json` only at load, so a stale instance disagrees
with disk on both the port and the API key until the window is reloaded.

## crew 0.15.1

Three new agents and a skill, taking crew to 14 agents and 17 bundled skills.

| Added | What it does |
|---|---|
| `infrastructure-architect` | Designs and reviews AWS network and account architecture — VPCs, routing, connectivity, DNS, ingress, landing zones. Returns the design with its tradeoffs. Never applies anything to a live account. |
| `scribe` | Keeps the durable record: ADRs, CHANGELOG entries, handoff notes, and what was tried and rejected. ADRs are append-only — a correction is a new ADR, never an edit to the old one. |
| `researcher` | External research only — library and SDK docs at the version actually pinned, API behaviour, vendor limits, standards. Every claim carries its source; it refuses to answer a version, a limit, or an API surface from memory. |
| `crew-house-style` skill | House style for documents a human will read: format choice, headings, capitalization, palette. Routes to the office and diagram skills rather than reimplementing generation. |

Also in 0.15.0:

- **`docs-writer` exports for humans.** Documentation a person will consume ships
  as HTML, DOCX or PDF, not raw markdown. The markdown under `docs/` stays the
  source of truth — the export is an additional artifact, so anything reading
  those paths keeps working. Repo-native files (`CHANGELOG.md`, `README.md`,
  `CLAUDE.md`, ADRs) stay markdown, because exporting one breaks the tool that
  reads it. `docs-writer` also gained the return contract it never had.
- **`dba` covers DynamoDB as its own model**, not as a row in a relational
  checklist — access-pattern-first, single-table design, partition-key
  cardinality, GSI backfill cost, the creation-time-only nature of LSIs, and the
  400KB item limit. Relational review is now split by engine, because lock
  behaviour under `ALTER TABLE` differs across Postgres, MySQL/InnoDB and SQL
  Server, and the old text applied Postgres vocabulary to all three.
- **`planner` asks what a decision forecloses** — whether it is one-way, what
  undoing it costs later, and the cheapest experiment that would settle it before
  committing.
- **Agents can now load the skills they cite.** Eight agents referenced a crew
  skill without declaring `skills:` frontmatter, so the reference was decoration:
  naming a skill does not load it. `browser-tester`, `docs-writer`,
  `infrastructure-architect`, `planner`, `pm`, `qa-reviewer`, `scribe` and
  `smoke-author` now declare what they cite.
- **`explorer` no longer orders a write it cannot perform.** It held
  `Read, Grep, Glob` and was told to append findings to memory; it now returns a
  `**Durable:**` block for its caller to persist.
- **The PM's guards apply on every path.** Removal needing an explicit yes was
  previously gated to `authority: act`, which switched it off exactly when a user
  told a `report-only` PM to go ahead.
