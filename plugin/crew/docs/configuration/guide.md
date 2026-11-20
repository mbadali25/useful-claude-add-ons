# Configuring crew

How to fill in crew's two configuration files, for an owner setting crew up by hand and for an AI
model doing it for them. Hand-written. The generated files beside it hold the facts per key:
[`keys.json`](keys.json) (default, allowed values, layer, one line, the version it arrived in),
[`template.annotated.md`](template.annotated.md) (the blank template with that beside each key),
and the two copy-safe blanks [`config.blank.json`](config.blank.json) and
[`global.blank.json`](global.blank.json). The full reference is [`reference.md`](reference.md); [`CONFIG.md`](../../CONFIG.md) is the key index.

Every example file named here is checked in CI by `tests/test_config_examples.py`, and so is every
command, flag and key this guide names. If a line here and a generated file disagree, the
generated file is right; report the line.

## 1. Two files, one effective config

crew reads two JSON files and merges them into one effective config:

| File | Called here | Who writes it |
|---|---|---|
| `.crew/config.json` in the repository | the repo file | `/crew:init`, then `crew_config.py --set ... --repo` |
| `~/.claude/crew/config.json` on your machine | the machine file | `/crew:config`, or `crew_config.py --set ... --global` |

For most keys the repo value wins over the machine value. Each key has a **layer class** that says
which file may set it and how the two combine. The classes are defined in the `layers` object at
the top of `keys.json`; each key's `layer` field names its class. In short:

- `repo`: only the repo file may set it (for example `tracker`, `production.hosts`).
- `machine-only`: read from the machine file alone (for example `notify.tokenEnv`).
- `both`: either file; the repo value wins (for example `qa.order`).
- `both, ratchet`: either file; the narrower value wins, so a repo can only tighten (`tiers`).
- `both, stricter wins`: personal keys; where both files set one, the stricter value wins.
- `both, widening warned`: either file, the repo wins, and a widening write is flagged
  (`pm.authority`).
- `machine-arms`: only the machine file can turn it on with `true`; a repo may only veto it with
  `false` (for example `resume.auto`, `context.autoClear.enabled`).
- `human-only opt-out`: the protected keys of section 4.

A **blank** is a complete file for one layer with every key at its default. Copying a blank into a
layer that has no file changes no effective value. Keys whose value would override the other layer
are left out of the blank, each with its reason; `template.annotated.md` shows which and why.

## 2. Set-up for an owner

1. In the repository, run `/crew:init`. Its config phase writes the repo file.
2. Run `/crew:config` for the guided menu that writes the machine file. It shows each choice, the
   current value and where that value came from.
3. See what is in force:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py" --explain --all
   ```

   Each row shows the effective value and which layer set it.
4. Check both files. All three print findings and exit 0, so read the output:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py" --check
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py" --check-global
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py" --inert
   ```

   `--check` warns about the repo file, `--check-global` about the machine file, and `--inert`
   lists settings crew does not act on: a misspelt key, or a key in the wrong file.
5. An older repository set up by crew 0.20 needs `/crew:migrate` first. After a plugin update, run
   step 4 again: `--check-global` lists keys the machine file does not set. `/crew:help` lists more.

## 3. How an AI model should configure crew

Follow these steps in order. Do not ask the owner anything this guide or `keys.json` answers.

1. Read this guide and `keys.json`, both in `${CLAUDE_PLUGIN_ROOT}/docs/configuration/`.
2. See what is set now, and which layer set it:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py" --explain --all
   ```

3. Ask the owner only these questions, and only for values not already set the way they want:
   - Which tracker holds tickets (`tracker`: `files`, `obsidian`, `jira` or `sdp`), and for Jira
     the project (`jira.project`). Repo file. Do not ask for `jira.cloudId`: `/crew:jira-sync`
     caches it.
   - Which reviewers to try and in what order (`qa.provider`, usually `auto`, and `qa.order`), and
     any model pin (`qa.codex.model`, `qa.kimi.model`). Machine file, unless this one repo differs.
   - Which targets are dev, qa or prod (`tiers`, entries `<kind>:<name>`). Machine file.
   - Which hosts and databases are production (`production.hosts`, `production.databases`) and
     which Terraform targets are not (`environments.nonProd`). Repo file.
   - How much the PM may do on its own (`pm.authority`: `report-only`, `act` or `autonomous`).
4. Do not ask about, and do not set, keys that have not landed yet:
   - The run mode (`mode`) arrives with R-M1; do not set it yet.
   - Service accounts (`accounts`) arrive with R-A1; do not set them yet.
   - Production hours (`production.hours`) arrive with R-40; do not set them yet.
5. Write a repo key with a dry run first, show it to the owner, then apply it with both digests
   the dry run printed: `digest:` goes to `--expect` and `machine digest:` to `--expect-global`, so
   the write refuses if either file changed since the dry run:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py" --set tracker='"jira"' --repo
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py" --set tracker='"jira"' --repo --apply --expect DIGEST --expect-global MACHINE_DIGEST
   ```

6. Write a machine key only through `/crew:config`, or as a `--set ... --global` dry run that you
   show the owner and apply only on the owner's yes:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py" --set qa.order='["kimi","codex","claude"]' --global
   ```

7. Never hand-edit either file. Never write a `machine-only` key into the repo file. Never write a
   key from section 4 at all: route it to the owner as section 4 says.
8. Never put a secret in either file. Store a reference instead: `notify.tokenEnv` holds the name
   of an environment variable, never the token itself.
9. Finish with `--check` and `--check-global` (step 4 of section 2) and read every finding.
10. Report to the owner what you set, in which file, and what you left at its default.

## 4. Keys only the owner can confirm

Three keys are never written by a model or by `--set`. Each is proposed, and the owner confirms it
by typing a command twice, in two prompts:

- `humanOnly.approve`: opting out of human-only approval (only ever proposed as `false`).
- `humanOnly.promoteMarker`: opting out of the human-only promotion marker (only `false`).
- `guards.git.allow`: letting git commands past the command guards (`"all"` or a list of git
  subcommand names), machine file only.

The route, the same for all three:

1. The model runs `crew_confirm_config.py propose --layer machine --key <key>` (`python3`, script
   in `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/`), adding `--value '"all"'` (or a JSON list) for the
   git key. For a protected key in an untracked repo file, the layer is `repo` with `--root`.
2. The model relays what `propose` prints to the owner word for word. For a `humanOnly` key that
   is the two indented lines after "Relay the next two lines"; for the git key it is all three
   lines, the last of which says what the guards stop doing once it applies.
3. The owner types `/crew:confirm-config <change_id>` twice, in two separate prompts.

The model never confirms, never writes the confirmation store, and never sets these keys any other
way: a value written without the two confirmations reads as not set. Turning the git key off needs
no confirmation; [`reference.md`](reference.md), "Git commands", says how.

## 5. Worked examples

Each file is a partial config: it holds only the keys it shows, every other key stays at its
default, and it passes the checks in CI. A `repo-` file is a repo file; a `machine-` file is a
machine file. To use one, copy it into a layer that has no file yet, or apply its keys one at a time
with `--set` as in section 3. `schema` is the exception: the repo writer refuses it, and
`/crew:init` sets it.

- [`examples/repo-minimal.json`](examples/repo-minimal.json): the smallest repo file, the schema
  version and a tracker.
- [`examples/repo-production.json`](examples/repo-production.json): production hosts and
  databases as globs, and the Terraform targets that are not production.
- [`examples/machine-reviewers-kimi-first.json`](examples/machine-reviewers-kimi-first.json):
  reviewers chosen automatically, Kimi tried first.
- [`examples/machine-reviewers-codex-first.json`](examples/machine-reviewers-codex-first.json):
  Codex first, Claude last, and the Codex review model pinned.
- [`examples/machine-tiers.json`](examples/machine-tiers.json): a tier map with one dev, one qa
  and one prod target. The names are placeholders. Tiers are report-only until R-01 lands, and a
  target the map does not list resolves to `unknown`.

More examples arrive with the keys they need (R-M1, R-A1, R-40).

## 6. Where each key family is explained

Every key belongs to one family; `keys.json` gives each key's `family`. For each family,
[`reference.md`](reference.md) has the reference table, `keys.json` the per-key facts and `template.annotated.md` the
key in its place in a blank file.

- `core`: the schema version and the few keys every repo has.
- `providers`: who reviews and who develops, their models and fallbacks.
- `guards`: the command guards, their profile and overrides, and the git switch of section 4.
- `cloud`: production hosts and databases, environments, tiers and unattended cloud access.
- `trackers`: where tickets live (files, Obsidian, Jira, SDP).
- `autopilot`: what an unattended run may do, its limits and its sleep schedule.
- `context`: the context-window warning and the auto-clear hand-off.
- `notify`: where crew sends notices, and the name of the variable holding the token.
- `memory`: where crew keeps its memory.
- `platform`: the operating system, WSL and shell crew runs on.

The generator of the reference files is `docs/guides/crew/src/config_reference.py` (repo-only tool,
not in an installed copy).
