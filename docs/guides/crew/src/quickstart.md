---
title: crew quickstart
subtitle: From install to your first ticket in ten minutes, on Windows or Linux
guide: 1 of 5
produced-by: T2 (this page), T4 (first-ticket commands), T8 (size budgets)
status: draft - steps marked "(arrives in T4)" do not exist yet
---

# crew quickstart

This guide takes you from nothing installed to a first ticket worked in one
repository. It assumes a machine with network access and a Git repository you
can write to. Every step says how to check that it worked before you move on.

Steps marked **(arrives in T4)** name commands that the crew 1.0 build has not
shipped yet. Until they land, use the 0.20 command named beside them.

## The ten-minute checklist

| # | Step | Check | Minutes |
|---|---|---|---|
| 1 | Install Claude Code and the marketplace | `claude --version` prints a version | 3 |
| 2 | Install the `crew` plugin | `/crew:status` answers | 1 |
| 3 | Set up the repository with `/crew:init` | `/crew:status` shows a `config` line | 3 |
| 4 | Existing 0.20 repos only: `/crew:migrate` | `/crew:status` shows `crew.json schema 1` | 1 |
| 5 | First ticket | a ticket directory under `.work/tickets/` | 2 |

## 1. Install Claude Code and the marketplace

### Windows

Open PowerShell. Administrator is recommended, not required.

```powershell
git clone git@github.com:mbadali25/useful-claude-add-ons.git
cd useful-claude-add-ons
.\scripts\install-prerequisites.ps1
```

Tick **This repo** in the menu. When the script finishes, open a **new**
PowerShell window so the `PATH` change applies, then run `claude --version`.

Hooks run under PowerShell on Windows. `python3` is often missing from Git
Bash: if a crew command reports it cannot find Python, install Python 3 and
make sure `python` or `py -3` works in the shell you use.

### Linux

```bash
git clone git@github.com:mbadali25/useful-claude-add-ons.git
cd useful-claude-add-ons
./scripts/install-prerequisites.sh
```

Tick **This repo** in the menu. Run `source ~/.bashrc` (or open a new shell),
then `claude --version`.

### Already have Claude Code?

Skip the scripts and add the marketplace directly:

```bash
claude plugin marketplace add mbadali25/useful-claude-add-ons
```

## 2. Install the crew plugin

```bash
claude plugin install crew@useful-claude-add-ons
```

crew registers hooks, so it is off in the install menu by default. Start
`claude` in your repository and run `/crew:status`. Before step 3 it reads
`config   none - run /crew:init`. That is the expected answer.

## 3. Set up the repository

```text
/crew:init
```

Init is phased and resumable: it detects the platform, writes the config, and
asks before each change. Stop after the config phase if you are short on time;
`/crew:init` picks up where it left off.

Check: `/crew:status` now shows a `config` line naming a schema.

Today `/crew:init` still writes the 0.20 `.crew/config.json`. Run step 4
straight after it until init writes `.crew/crew.json` itself.

## 4. Existing repositories: migrate once

If the repository already used crew 0.20, or you just ran `/crew:init`:

```text
/crew:migrate
```

It previews first and writes nothing until you agree. The preview lists:

- the files it will create (`.crew/crew.json`, `.crew/metrics.jsonl`, one
  directory per ticket under `.work/tickets/`);
- any config key it did not recognise, which is kept under `unmapped`, never
  dropped;
- the originals it leaves in place and you may retire later.

Say yes, and it backs up to `.crew/backups/migrate-<time>/`, then applies. The
line it ends with is your undo:

```text
/crew:migrate --rollback .crew/backups/migrate-<time>
```

Your code map in `.crew/codemap/` and its anchors are not touched.

Check: `/crew:status` shows `config   .crew/crew.json schema 1`.

## 5. Your first ticket

In crew 1.0 one interactive session owns a ticket from start to finish:
brainstorm, spec, plan, implement, tests, docs, review, done.

For a small first change use the light path:

```text
/crew:fix <one sentence: what is wrong and where>
```

**(arrives in T4)** `/crew:fix` is not shipped yet. Until it is, use
`/crew:ticket <what needs doing>` followed by `/crew:work T-0001`.

The light path runs every phase in short form: a one-line direction, a short
spec, a one-step plan, and your approval before any edit. Review runs after
tests and docs, and has a budget of two rounds.

Check: `.work/tickets/<id>/` exists and `/crew:status` lists it under `open`.

## If something goes wrong

| Symptom | Do |
|---|---|
| `/crew:status` is not a known command | `claude plugin update crew@useful-claude-add-ons`, then restart `claude` |
| `migrate` reports a `CONFLICT` | read the path it names; apply refuses until it is resolved |
| `migrate` reports an interrupted apply | `/crew:migrate --rollback <dir>` first |
| a crew command cannot find Python | install Python 3; on Windows make `python` or `py -3` work |

The full troubleshooting guide arrives in T10.
