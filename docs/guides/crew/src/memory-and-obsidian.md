# Memory and Obsidian

Crew keeps durable memory in plain Markdown: your repository's contracts,
ADRs and code map stay authoritative for that repository, and an Obsidian
vault holds the lessons that cross projects. The `obsidian-vault` plugin owns
that vault. It sets it up, captures sessions into it, gardens the captures into
notes, and answers recall queries from it. Crew calls the plugin rather than
doing any of this itself.

Every command below is `vault_ops.py`, which ships with the plugin. It is
**dry-run by default**: it prints the exact change and writes nothing until you
repeat it with `--apply`. Exit 0 means done or healthy, 1 means there is
something to do or something wrong, and 2 means the command was refused or
mistyped.

Set a shorthand once per shell. It picks the newest installed version of the plugin:

```bash
# Linux / macOS / Git Bash
VO="python3 $(ls -d ~/.claude/plugins/cache/*/obsidian-vault/*/ | sort -V | tail -1)hooks/scripts/vault_ops.py"
```

```powershell
# Windows PowerShell
$VO = (Get-ChildItem "$env:USERPROFILE\.claude\plugins\cache\*\obsidian-vault\*\hooks\scripts\vault_ops.py" |
  Sort-Object { [version]$_.Directory.Parent.Parent.Name } | Select-Object -Last 1).FullName
function vo { python $VO @args }
```

On Windows, read `$VO ...` in the examples below as `vo ...`. Inside Claude
Code you do not need either: `/obsidian-vault:init` runs the same steps and
asks you before each one.

## What gets captured

When a session ends, and before the context is compacted, a hook appends one
line to the primary vault:

```
inbox/pending-reflect.<host>.md
- [ ] 2026-09-23 14:02 | SessionEnd | session=4f1c... | cwd=/repos/app | transcript=/home/you/.claude/projects/.../4f1c....jsonl
```

That is all it records: when, which session, which folder, and where the
transcript is. It never copies conversation text into the vault. Each machine
writes its own `<host>` file, so two machines syncing one vault never write the
same file. One line per session, whichever trigger fires first. The capture
hook cannot block or slow a session; if it fails it says so on stderr and moves
on.

An older version wrote a single `inbox/pending-reflect.md`. That file is no
longer written, but it is still read, so an existing backlog drains rather than
being stranded.

## How gardening works

The gardener turns queued sessions into notes. It reads each transcript,
writes or extends concept and decision notes with sources, and appends a line
to the day's daily note.

It runs **on one host, once a day, in bounded passes**:

- at most **5 items or 10 minutes** per run, whichever comes first;
- an item is acknowledged only after the note it produced exists and is
  non-empty. If the model fails, times out, or claims a file it did not write,
  the item stays queued for the next run;
- acknowledgements go to `inbox/reflected.<host>.md`, so the queue files keep
  one writer each;
- a session whose transcript lives on another machine is left for that machine
  and does not use up one of the five slots;
- only the designated host runs it (`gardener.host` in the config), and one
  run at a time;
- with `--commit`, it commits only the files that run wrote plus its own
  acknowledgement file. It never sweeps in anything else you had staged.
  Leave `--commit` off if Obsidian Git already commits the vault.

Run a pass by hand with `/obsidian-vault:garden`, or:

```bash
$VO queue                 # what is waiting
$VO garden-run            # one bounded pass (designated host only)
```

A large backlog drains in the same bounded batches:

```bash
$VO drain                         # dry run: backlog size, batch count, first batch
$VO drain --apply --batches 4     # up to 4 passes of 5, stops early if one acknowledges nothing
```

## Upkeep

| When | Do |
|---|---|
| Daily, automatically | The scheduled gardener. Check `~/.claude/obsidian/gardener.log` now and then for lines that start `left queued`. |
| After a plugin update | Re-run `$VO schedule --os <yours>` and reinstall the unit it prints. The unit names the plugin's versioned folder, which the update replaces. |
| When a vault moves or you add one | `$VO adopt` to review roles. |
| When recall seems blind | `$VO recall --query "<words you expect>"` and check which vaults it names. |
| When the bridge misbehaves | `/obsidian-vault:doctor`, then `/obsidian-vault:repair`. The bridge is optional; capture, recall, import and gardening all work on the files without it. |
| When the code changed a lot | `/crew:onboard --refresh <subsystem>` for the repository's own code map. That map lives in the repository, not the vault. |

## Setup

Every case ends in the same place: exactly one **primary** vault, which receives
captures and imports, and optionally some **recall** vaults that are read but
never written.

### Case 1: Obsidian is not installed

**Linux**

```bash
$VO detect-obsidian
```

It checks snap (`/snap/bin/obsidian`), Flatpak (`md.obsidian.Obsidian`), the
`obsidian` deb, AppImage locations and `PATH`, and answers `INSTALLED`,
`MISSING` or `UNKNOWN`. `UNKNOWN` means none of those checks could run. It is
not the same as missing, and install refuses it.

```bash
$VO install-obsidian              # prints e.g.: Planned install (snap): sudo snap install obsidian --classic
$VO install-obsidian --apply      # runs exactly that command
```

Without snap it offers `flatpak install -y flathub md.obsidian.Obsidian`. For a
deb or AppImage it tells you what to download from obsidian.md and does not
fetch anything. Choose one with `--method snap|flatpak|deb|appimage`.

**Windows**

```powershell
vo detect-obsidian
vo install-obsidian               # Planned install (winget): winget install --id Obsidian.Obsidian -e ...
vo install-obsidian --apply
```

Then create the vault:

```bash
$VO create-vault --name memory --path ~/vaults/memory
$VO create-vault --name memory --path ~/vaults/memory --apply
$VO adopt --role memory=primary --apply
```

On Windows use a path such as `C:\vaults\memory`. Open the folder once in
Obsidian (**Open folder as vault**) so Obsidian registers it too.

**Success looks like:** `detect-obsidian` prints `INSTALLED`, a second
`create-vault ... --apply` prints `Nothing to do`, and `$VO adopt` lists
`memory  primary`.

### Case 2: Obsidian with one vault

```bash
$VO adopt
```

```
1 vault(s). Ask for a role for each: primary (exactly one; receives captures and imports), recall (read for injection), ignore.

  notes                    unassigned /home/you/notes
```

```bash
$VO adopt --role notes=primary            # dry run: shows role and default changes
$VO adopt --role notes=primary --apply
```

**Success looks like:** running the same `--apply` again prints `Every
requested role is already set. Nothing to change.` and exits 0.

### Case 3: Several vaults

`adopt` lists every vault in the config and every vault Obsidian itself knows
about. Decide on each one separately:

- `primary`: this vault receives captures and imports. Choose exactly one.
- `recall`: this vault is searched for context but never written.
- `ignore`: leave this vault alone. The answer is stored so a re-run does not
  ask again.

Then write every answer in one call:

```bash
$VO adopt --role memory=primary --role work-notes=recall --role journal=ignore
$VO adopt --role memory=primary --role work-notes=recall --role journal=ignore --apply
```

The command refuses any result with no primary or with two, and writes nothing
when it does. To move the primary later, demote the old one in the same call:
`--role memory=recall --role new-memory=primary`.

**Success looks like:** `$VO adopt` lists each vault with its role and no
`[FAIL]` line.

### Case 4: Importing a folder

Bring notes from a plain Markdown folder, or from another vault by name, into
the primary vault:

```bash
$VO import --source ~/old-notes                 # dry run: counts and collisions
$VO import --source ~/old-notes --apply
```

On Windows, for example: `vo import --source C:\Users\you\Documents\old-notes --apply`.

Notes land under `imported/<folder name>/` with the same sub-folders. Each one
gets two frontmatter keys: `imported_from` (the absolute source path) and
`imported_at` (the UTC date). Line endings become LF. The import never
overwrites a file. If a file already exists at the destination, the import
skips it and reports it as a `COLLISION`. With `--suffix-collisions` it writes
the new file beside it as `<name> (imported).md`. Files that are not Markdown
are counted and left behind. Use `--dest-subdir <folder>` to choose another
destination inside the vault.

**Success looks like:** `Imported N note(s)`; running it again reports
`already-imported: N` and writes nothing.

### Scheduling the gardener

On the one machine that should garden, run:

```bash
$VO schedule --os cron --designate            # Linux without a systemd user session (root, containers)
$VO schedule --os systemd --designate         # Linux desktop with systemd --user
```

```powershell
vo schedule --os windows --designate
```

Each command prints the unit, the install commands, a verify command and a
remove command. It installs nothing. Add `--apply` to make this machine the
designated gardener, then run the printed install commands yourself. The
default time is 02:23; change it with `--time HH:MM`.

**Success looks like:** after the first scheduled run,
`~/.claude/obsidian/gardener.log` has `acked <session>` lines, and `$VO queue`
shows fewer items.

## Confirming recall reaches your sessions

(written by the context-hook ticket)
