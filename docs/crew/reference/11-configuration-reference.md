<!-- Moved verbatim from plugin/crew/README.md (11. Configuration reference) by L-0726; the README keeps an index entry. -->

## 11. Configuration reference

Everything reads `.crew/config.json`. If it goes missing or stops parsing,<!-- claim: crew-config-file:config.json -->
`platform-sync` recreates it from `templates/config.template.json` the next
time the repo is opened — see "The config heals itself" in §3; this is the
same shape that produces:

### Global config, and how it layers with the repo file

An optional machine-global file at `~/.claude/crew/config.json` sets defaults
for every crew repo on this machine, without hand-editing each one. Three
layers, lowest precedence first:

| Layer | Source | Written by |
|---|---|---|
| Built-in defaults | `hooks/scripts/crew_config.py`'s `default_config()` | Nothing — this is code, not a file |
| Global | `~/.claude/crew/config.json` | `/crew:config` — a guided walkthrough that shows the plan first and writes only after a yes. It is also the only thing in crew that writes outside the repository. Hand-editing still works. |
| Repo | `.crew/config.json` | `/crew:init` (first write); `platform-sync` (the `platform` block, and the whole file when it heals — see §3); the `/crew:config` menu (`crew_config.py --set ... --repo`, `crew_config_menu.py save`) |

Repo overrides global overrides built-in defaults, merged recursively with
`crew_state.merge_defaults` — the same policy `crew_upgrade.upgrade_config` (run by `/crew:migrate` for a pre-0.20 config) uses to bring a
v1 config's `pm` and `graph` blocks forward: a nested override wins, a scalar
where a dict belongs is discarded rather than corrupting the block under it.
`crew_config.resolve_config(root)` is the one place that computes this; every
reader that wants *effective settings* calls it rather than reading
`.crew/config.json` directly.

Two things never go through this layering, on purpose:

- **`schema`** is a fact about the repo file's own layout version, not a
  setting — it is read straight from `.crew/config.json`, never merged. The
  built-in-defaults layer always reports the current schema, so merging it
  would make an unmigrated `v1` repo (no `schema` key at all) look current
  the moment *any* global file exists on the machine.
- **The `platform` block and the heal path both write only the repo file.**
  `platform-sync` never reads or writes the global file, and recreating a
  missing or broken `.crew/config.json` always writes plain built-in
  defaults — never a merge that could smuggle a global preference into a
  file every teammate who clones the repo will also read.

A key the global filter drops (a `scope` or `emergency` block, a `tracker`) takes
effect nowhere. It is not silent:
every session start names it in its `Inert settings` line as
`key=value (global, not read)` (T-0070), and `/crew:config --show` lists it.

**In a linked git worktree.** `.crew/*` is gitignored, so a lane made with
`git worktree add` starts with no `.crew/config.json` or `.crew/crew.json`. Since
crew 1.0.69 (T-0088) such a worktree reads the **main checkout's** repo config,
found through `git rev-parse --git-common-dir` (`crew_common.repo_config_dir`).
A worktree with either file of its own reads only its own files: they win whole,
even when partial, and are **never merged** with the main checkout's. When `.git`
is a file but git cannot name the main checkout, the source is `unknown`,
nothing is inherited, and `/crew:status` and `/crew:config --explain` say so
rather than showing the config as simply absent. A submodule, or a bare common
directory, is its own repo. Inheritance is read-only: no writer (`/crew:init`,
the heal path, `platform-sync`, `/crew:migrate`, the auto-clear setup) ever
writes the main checkout's file, and the heal path no longer creates a default
config in an inheriting worktree, because that default would shadow the owner's
(nor in one where git could not tell; it asks again next session).

**A lane made before 1.0.69 still reads its own file.** Every SessionStart heal
on crew 1.0.68 or earlier wrote a default `.crew/config.json` into a lane that
had none, and that file wins whole. `/crew:status` and `/crew:config --explain`
say so (`... the main checkout's (<path>) is not read ...`); if the lane's file is
a default nobody edited, delete it (and `.crew/crew.json`) to inherit.

**Behaviour change:** every Python guard in a lane worktree now reads the owner's
settings where it read the built-in defaults before - `guards.forcePush: allow`
instead of `block`, `scope.mode`, `scope.allowCliApproval`, `roleWrites` and
`cloudGuard` the same way. Since L-0681 the verify gate does too: a lane with no
config of its own whose main checkout says `"verifyGate": false` gets no Stop
gate, and `/crew:review` reads NO_GATE there (`verify-gate --ci` still exits 2);
a lane that must be gated writes its own config. And with no usable python the
scope and completion wrappers prove `scope.mode` off only when the resolved
file is absent and git could tell: a lane whose main checkout has a config, or
whose git cannot name the main checkout, blocks writes and the Stop until
python works - except that the PowerShell wrappers (PowerShell 7) still allow
a resolved config that strictly parses as `scope.mode: off`. Ratcheted guard keys still take the narrower of repo
and machine-global. A lane that wants its own guards writes its own
`.crew/config.json`, and that file then wins whole.

**The shell and PowerShell readers (crew 1.0.330, T-0096, partly).** `_common.sh`'s
`crew_repo_config_dir` and the PowerShell `Get-CrewRepoConfigDir` (one body,
copied into each script that uses it) resolve the same directory by the same
rules, without python. Routed through them: the incident stand-down read
(`emergency.standDown`, in `_common.sh` for every bash gate and in
`promote-gate.ps1`), both cloud-guard no-python fallbacks, and `auto-clear.ps1`'s
repo veto. In the cloud guard's fallback an `unknown` source counts as armed: a
lane whose git cannot name its main checkout, with no usable python, refuses Bash
until one works. Inheritance can loosen as well as tighten: an inherited
`cloudGuard: off` applies in a lane. The session hooks (`notify`,
`handoff-read`, `handoff-write`, `context-watch`, both flavours) read the
resolved file too (crew 1.0.343, L-0680): a lane notifies with the main
checkout's `notify` settings, so several lanes ping the same channel unless one
writes its own config, and an inherited `context.handoffPath`,
`keepTranscripts` or threshold applies in the lane while the handoff path
stays inside the lane: a relative one names a file there, and one that leaves
it (absolute, `..`, a symlink out) or names a directory is the lane's
`.work/HANDOFF.md`, with a warning. The PowerShell hooks are stricter on links:
Windows PowerShell 5.1 cannot resolve one as `realpath` does, so any symlink or
junction on the way counts as leaving, even one that points back inside. What they write (transcripts, markers, the
handoff note) stays in the lane, and `context-watch` still needs a `.crew/`
directory there before it measures. The review/gate harness reads it too (crew
1.1.4, L-0681): the verify gate in both flavours (`verifyGate`,
`verify.stopBudgetSeconds` and, in `verify-gate.ps1`, `emergency.standDown`),
`review_gate.py` (in step with the gate: both read one file), the gate's
fingerprint (the first gate run in each inheriting lane after the upgrade
re-runs its commands once) and the scope and completion wrappers' no-python
proof. No shell, PowerShell or Python reader of the repo config is outside a
resolver now. `.crew/verify.json` is never inherited.

### `/crew:config` — see where a value comes from, and set the global file

```
python3 hooks/scripts/crew_config.py --root . --explain        # value + source
python3 hooks/scripts/crew_config.py --root . --check-global   # what is wrong
python3 hooks/scripts/crew_config.py --set pm.authority='"act"'          # dry run
python3 hooks/scripts/crew_config.py --set pm.authority='"act"' --apply  # write
```

`--explain` prints every globally-settable key with its effective value and
the layer that decided it. That column is the point. The reason this command
exists is a machine where the global file carried `tier`, `roles`, `qa` and
`sdp` but **no `pm` block**, so every repo on it resolved to
`pm.authority: report-only` while the user believed the 0.20 PM was autonomous.
Every file was valid; nothing surfaced the discrepancy. `/crew:config` runs
`--check-global` and reports the same findings.

Four rules the script enforces rather than documents:

- It **merges**. A key in an existing global file that the walkthrough never
  asked about survives untouched.
- It **refuses** any key outside `default_global_config()`, by name, exit 2.
  That keeps repo facts (`tracker`, `jira.project`, `graph.out`, `platform`,
  `tier`, `roles`) out of a file every repo reads — and it is what makes
  `graph.obsidian.confirmed` un-grantable from a guided flow: it is consent to
  write into your own notes outside the repo, not a capability.
- It is a **dry run by default**. `--apply` is a second, deliberate call.
- It marks a **widening** with a `!` line, on both the dry run and the write,
  naming the tier being granted and what that tier buys. `pm.authority`,
  `install.policy` and all six `guards.*` are the values a user cannot recover
  from by noticing.

`--explain` also names the **narrowing source** for the seven keys that ratchet.
Those do not resolve by precedence, so the merged value is the wrong thing to
print for them: before this was fixed, a repo `install.policy: auto` over a
machine-global `manual` printed `install.policy  repo  "auto"` while crew
behaved as `manual` — a report contradicting the run, in the direction that
reads as "you have it". It now prints the effective value and, underneath, the
line that says which layer is holding it down and what each layer asked for.

`templates/global.template.json` is the shape, and a committed test asserts it
equals `global_template_config()` (`default_global_config()` minus the personal
keys) byte-for-byte — the same drift gate the repo template has. It is deliberately not a copy of the repo template: it carries
only what is a property of the machine or the person (`pm.authority`, `qa`,
`dev`, `secondOpinion`, `notify`, `memory.vaultPath`), and no `schema`.

A global file that is missing, empty, or fails to parse is treated exactly
like an absent one — the same reasoning `_read_config_strict` documents for
the repo side — so a typo in your global config degrades one repo's settings
to defaults rather than breaking every session on the machine.

### Personal defaults, backups, and rebuilding a lost config (T-0050)

```
python3 hooks/scripts/crew_config.py --set autopilot.approval='"self"' --apply  # global default
python3 hooks/scripts/crew_config.py --root . --explain --all       # every key, layer, shadows
python3 hooks/scripts/crew_config.py --root . --unset autopilot.mode --repo --apply
python3 hooks/scripts/crew_config.py --root . --rebuild --repo      # dry run; then --apply
python3 hooks/scripts/crew_config.py --root . --backups --repo      # stamps, newest first
python3 hooks/scripts/crew_config.py --root . --restore <stamp> --repo --apply
```

- **Global defaults for the personal keys.** `autopilot.mode`, `maxPhases`,
  `deploy`, `approval` and `questions` can be set once in
  `~/.claude/crew/config.json` for every repo on the machine. They combine per
  key: the stricter of the layers that set the key wins, and a silent layer
  imposes nothing — so a global value is a default a repo may narrow, never a
  grant it cannot refuse (CONFIG.md §20a). New repos no longer spell these
  keys; a repo set up before this spells `autopilot.mode: "off"`, which holds a
  global `plan` down — `--explain --all` names each such `shadow:`, and
  `--unset <key> --repo --apply` removes it on your yes.
- **Every crew script write is backed up first** to `~/.claude/crew/backups/`
  (newest 20 per file; a hand edit is not), and a failed backup refuses the write. `--backups` lists them
  and `--restore <stamp>` puts one back, backing up the current file first.
- **The profile.** `--set`/`--unset --apply`, the menu's Save and
  `--save-profile --apply` keep your non-default values in
  `~/.claude/crew/profile.json` (and `<memory.vaultPath>/crew/profile.json`
  when you keep a vault, so it syncs). `--rebuild --repo|--global` regenerates
  a lost or corrupt config from the template plus that profile; a dry run
  until `--apply`, exit 3 when the profile is there and unreadable.
  SessionStart's heal still writes crew's defaults, never the profile — it
  names the rebuild instead.

### The `/crew:config` menu — set either layer, or delete the repo config

`/crew:config` with no argument, and its alias `/crew:config-setup`, open a
menu (`skills/crew-setup/config-menu.md`, backed by
`hooks/scripts/crew_config_menu.py`). Pick the **layer** — this machine's
`~/.claude/crew/config.json` or this repo's `.crew/config.json` — then an
**area** (models, autopilot, guards, notify, memory and tracker, auto-clear,
other), then a **setting**, then a **value from a list**. Each value shows the
current effective value, the layer that decided it, and the recommendation
first; the owner never has to type one.

- **Data-driven.** The rows are `crew_config.py`'s own key lists
  (`default_global_config()` for the machine layer, `default_config()` for the
  repo), so a key added to crew appears with no menu edit, and a committed test
  runs every offered value through the writer. The machine layer also lists
  `platform.*` and `schema` read-only, and an absent or unparseable
  `.crew/config.json` makes every repo row read-only with the writer's own
  refusal as the reason.
- **Offered means accepted.** Every candidate value is probed through the
  layer's own planner on the file Save would produce, the pending set
  included (`spec --pending`). A row no value can pass — a bad value already
  in the file, such as an unknown `qa.provider` — is read-only with the
  planner's reason, which names the key to fix first.
- **Selection only, Save once per layer.** Picks collect in a pending set that
  spans areas and both layers. Save validates **both** layers before writing
  either, shows the dry-run diff with `!` widening lines and "held down by the
  machine-global layer" lines, then writes each changed layer once. A write
  that fails or is refused after validation (the file changed underneath)
  reports which layer landed and which did not. The dry run prints each
  changed layer's `digest:`, and the machine digest whenever anything
  changes, since a repo value's widening marks are judged against the
  machine file (as this Save leaves it); `absent` names a file that does not
  exist. `--apply --expect-machine/--expect-repo` checks both before either
  write and binds each writer to them, the repo write to the machine digest
  too, so a file another session changed or created since the dry run is
  refused, never merged over. Discard writes nothing.
- **One validated repo writer.** `crew_config.py --set PATH=JSON --repo
  [--apply]` (`plan_repo_write` / `write_repo_config`) merges, refuses unknown
  keys, takes a whole-block value leaf by leaf (as the machine writer does),
  checks enum values, validates providers, writes
  atomically and keeps the file's line ending and BOM. It refuses `platform.*`
  (platform-sync owns it), `schema`, and `context.autoClear.onlyRepos` /
  `.onlySessions` (read from the machine file only), and takes only a veto
  (`false`) or `null` for `context.autoClear.enabled` and `resume.auto` —
  exactly those, by identity, so `0` is refused.
- **Both writers judge per leaf, write per leaf, and judge the whole file.**
  Each update is expanded to its leaves, so a whole-block value such as
  `context={"autoClear": {"unsafeFocus": true}}` cannot carry a refused key
  past the machine writer, and each leaf is written on its own: the block's
  untouched siblings (unknown keys included) survive, and a widening is
  marked on the leaf that widens. A role-table value (`qa.roles`) is written
  one whole pin per role, the other pins kept. `null` is accepted only where
  the layer gives it a meaning: at the repo layer it inherits the machine
  value for a machine-settable key, or clears a veto; an open key is unset;
  an enum key at the machine layer refuses it. Then the merged file is
  checked, every known leaf: a bad enum value, a consent key in the machine
  file, or an armed veto-only key in the repo file already there refuses an
  unrelated write, naming the key to fix first. Nothing goes under a leaf
  and no object sits at one; `qa.roles` / `dev.roles` and their entries are
  objects or `null`, so `qa.roles=1` is refused rather than wiping every pin.
- **Both writers are compare-and-swap.** Read, merge and replace happen inside
  an `O_CREAT|O_EXCL` lock file beside the config (`config.json.lock`, 3 s
  wait, then a refusal naming the lock and its PID), so two sessions never
  merge against stale snapshots; `--set` prints `digest:` (`absent` for no
  file) and `--apply --expect <digest|absent>` refuses a file that changed,
  or appeared, since; `--set --repo` also prints `machine digest:` and takes
  `--expect-global`. A malformed machine file is refused rather than
  overwritten from `{}`. An OS error (a lock, the machine directory, the
  write) is a refusal with exit 2, never a traceback.
- **`crew_config_files.py` is the one file layer** under both writers, delete
  and restore: the lock, the strict read, the `restorable` predicate and the
  regular-file read delete and restore share, the digest, the atomic
  replace, and the no-clobber move: a rename that never replaces an existing
  destination, by the rename itself rather than a check before it.
- **`scope.*` is refused on purpose.** `scope.mode` and
  `scope.allowCliApproval` are the scope guard's trust root, and
  `.crew/config.json` is untracked, so the completion audit (which diffs
  tracked files) would never see a one-command write that disarmed it. They
  stay a hand edit by the owner or `/crew:init`, shown read-only in the menu.
- **Delete the repo config.** Two phases. The preview reads and holds the
  file's bytes and walks its own leaves: a `!` on anything that widens
  (`scope.mode` returning to `off` included), `-> (removed)` for a key crew
  does not know, a `stays` line for a ratcheted key the repo narrowed under a
  wider machine value (deleting does not widen it), and the `platform.*`
  keys platform-sync writes (`crew_platform.DERIVED_KEYS`) in a "re-detected
  by platform-sync" group, which promises no value: a key it finds none for on
  this machine is left unset. Any other `platform.*` key is `-> (removed)`.
  Then the `repo digest:` and
  `machine digest:` it was built from. A file a restore could not take back
  (unparsable, empty, `{}`, not an object, or not a regular file, such as a
  symlink) is refused: that is platform-sync's to heal, or the owner's to
  remove by hand. The delete requires the typed repo name (the checkout's
  `git rev-parse --show-toplevel` basename) and both preview digests
  (`--expect-repo`, `--expect-machine`), so it is the delete the preview
  showed; then, under the machine lock and then the repo config lock (crew's
  one nesting order), it reads the machine digest again (a machine write since
  the preview refuses, exit 2, nothing deleted),
  moves the file to `.crew/config.json.bak-<UTC timestamp>` in one rename —
  the backup is the original, never a copy — and compares the moved bytes
  with the held ones: a file that changed since the preview is moved straight
  back, never over a file saved in between, and nothing is deleted. A file
  another writer puts at `.crew/config.json` during the rename is never
  unlinked: it keeps a second name, `*.moving`, and the command exits 1
  naming the backup, the config and that name — nothing is lost. An OS error after the move
  (a failed fsync or read-back, or a failed move back) exits 1 and names where the file is (both
  paths when it cannot tell), never "left in place"; it exits 2 when the file is back at its path,
  or the error came before the move (a lock, the machine file). It prints the restore command three ways,
  `restore (sh):`, `restore (cmd):` and `restore (PowerShell):`
  (`crew_config_menu.py restore-repo --from <backup> --apply`); each form is
  executed by a test, and restore accepts exactly what delete does, exiting 1
  the same way when another writer interleaves with its move-aside. Until the next
  SessionStart there is no config, so `isCrew` is false and every hook that
  gates on it stands down; then platform-sync's heal recreates the built-in
  defaults. `.crew/crew.json`, `verify.json`, backups and ticket state are
  untouched.
- **Headless.** With no way to ask, `crew_config_menu.py spec --layer
  <layer>` prints the plan and a write needs the explicit
  `save --changes '<json>' --apply --expect-machine/--expect-repo <digest>` or
  `delete-repo --confirm <name> --apply --expect-repo <digest>
  --expect-machine <digest>`.

Both writers now refuse a value outside the key's own tier or provider list
(`pm.authority`, `pm.ticketGranularity`, `qa.provider`, `dev.provider` and every
ratcheted key), refuse `null` for one of those at the machine layer, and refuse
a `--set` value that is not JSON. Before T-0075 a global `--set
pm.authority=bogus` was written and then read as `report-only`.

### §11b. `guards` — the guardrails you can turn down, per machine

Six keys added by schema 6, in **two vocabularies**: four are
`block` | `ask` | `allow`, shipping as `block`; the two production-access keys
are `none` | `read` | `full`, shipping as `none`. Since then `guards.roleWrites`
(see §18 of CONFIG.md) and, with the cloud guard, `guards.cloudDestructive`,
`guards.sqlDestructive`, `guards.deployWorkflow` and the `guards.cloudGuard`
switch. The command keys
below govern something **only while `guards.cloudGuard` is `report` or
`block`** — it ships `off`; see [Cloud guard](#cloud-guard).

| Key | Governs | Read by |
|---|---|---|
| `guards.terraformApply` | `terraform`/`tofu`/`terragrunt` `apply` and `destroy` | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.forcePush` | `git push --force` / `-f` / `--force-with-lease` / a `+ref` | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.adminMerge` | `gh pr merge --admin` | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.mergeGate` | whether `/crew:gate` may take a live repo's merge gate down | `commands/gate.md`, `commands/promote.md` |
| `guards.prodDatabase` | a SQL client aimed at a `production.databases` pattern | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.prodServer` | `ssh`/`plink`/`scp` aimed at a `production.hosts` pattern | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.cloudDestructive` | `aws … delete-*/terminate-*/purge-*`, `s3 rm/rb`, `s3 sync --delete`, `az … delete/purge`, `Remove-Az*` | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.sqlDestructive` | `DROP`/`TRUNCATE` sent to `psql`, `mysql`, `mariadb`, `sqlcmd`, `sqlite3`, `Invoke-Sqlcmd` | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.deployWorkflow` | `gh workflow run` / `gh api .../dispatches` of a workflow listed in `environments.workflows`; `allow` covers nonProd only | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `guards.cloudGuard` | whether the cloud guard judges commands at all: `off` (default) / `report` / `block` | `hooks/scripts/cloud_guard.py` |
| `guards.envGuard` | whether the environment guard refuses a command that prints the environment or a credential-named variable: `off` (default) / `report` / `block` (L-0772) | `hooks/scripts/env_guard.py` |
| `environments.nonProd` | **repo-only** globs naming the terraform workspaces/environments that may run unattended (default `[]`) | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `environments.prodUnattended` | whether production may too — true only when **both** layers say `true` (default `false`) | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |
| `environments.workflows` | **repo-only** map of workflow globs to `input:<name>` or a fixed environment, naming the deploy workflows `guards.deployWorkflow` judges (default `{}`) | `hooks/scripts/cloud_guard.py`, when `cloudGuard` is on |

- **`block`** refuses, exactly as the guard did before these keys existed.
- **`ask`** refuses, prints the **exact** command, and names the one file that
  approves **that** command:
  `.crew/.approved-guard-<name>-<sha256(command)[:16]>`. Create it, re-run, and
  it goes through; the next command asks again. It is a marker rather than a
  prompt because a `PreToolUse` hook has no interactive stdin — an `ask`
  implemented as a question would have been `block` under another name.
- **`allow`** runs it, says so, and appends a row to `.crew/guard.log`. **Under
  `allow` nothing is silent.** The stderr line goes with the session; the row
  is the durable half, and it is written for every decision rather than only
  the permissive ones. Since 1.2.35 a `crew_config.py --record` row holds the
  time, guard, policy, decision and target, and `-` for the command; the
  command line is written only with the opt-in `--record-command` (CONFIG.md,
  "What a `--record` row holds").

**The two production guards are `none` | `read` | `full`.** `none` refuses
every command aimed at a declared target; `read` permits only what crew can
**positively classify** as read-only, so an interactive `psql`, an unrecognised
binary over `ssh` and anything it cannot parse are refused as writes; `full`
permits everything and logs each one. Since L-0772 an environment dump is not a
read either: `ssh prod printenv`, `ssh prod env`, `ssh prod cat /proc/1/environ`
and anything else the [Environment guard](#environment-guard) recognises print
that host's credentials, so `read` refuses them (**BREAKING**, by narrowing). `ask` is not a value here — these answer
"how much of production may crew reach", a standing posture rather than a
per-command question.

**The level is a machine fact; what is production is not.** The two levels
ratchet across both layers. `production.databases` and `production.hosts` — the
glob lists they match against — are **repo-only**: `prod-db-*` names one
cluster in one repo and something else in the next, so a machine-global list
would describe the wrong estate everywhere else. **With no patterns declared
the guard matches nothing**, which is how the strictest level can be the
default and still change nobody's behaviour on upgrade.

**A repo may only narrow.** Every `guards.*` key and `install.policy` resolve to the
**narrower** of the repo and machine-global layers, not by precedence. crew
reads config out of cloned repositories: under precedence, a repo shipping
`guards.forcePush: allow` would grant itself force-push rights on the machine
of anyone who cloned it. So `allow` needs **both** layers to say `allow`, and
`--explain` names the layer holding a key down when they disagree.

### Cloud guard

A `PreToolUse` hook on the **Bash and PowerShell** tools
(`hooks/scripts/cloud-guard.sh` / `cloud-guard.ps1`, both delegating to
`cloud_guard.py`). **It ships off** — `guards.cloudGuard: "off"` — because a
hook that can block defaults off. Set it to `report` first: every decision it
*would* make goes to `.crew/guard.log` and nothing is refused. `block` enforces.
A repo cannot turn off a machine-global `block`.

When on, it reads each command into the simple commands it actually runs —
through `&&`, `;`, `|`, `sudo`, `env X=Y`, `bash -c`, `pwsh -Command`, `$( )`,
heredocs and PowerShell script blocks — and judges only those. A word inside an
argument is never a finding of the rule it names: `psql -c "SELECT 'DROP TABLE
x'"` passes. That is the difference from the command guard removed in 0.19.52,
which matched words anywhere. A quoted terraform word is the one exception,
below: it makes the line one crew could not tell.

| It recognises | Decided by |
|---|---|
| `terraform`/`tofu` `apply`, `destroy` (`-auto-approve`, `-chdir=` included) | `guards.terraformApply` |
| `terraform`/`tofu`/`terragrunt` `workspace delete` — a destroy, in every armed state; `workspace new`/`select -or-create` once `environments` is configured | `guards.terraformApply` |
| `git push --force`, `-f`, `--force-with-lease`, `+ref` | `guards.forcePush` |
| `gh pr merge --admin` | `guards.adminMerge` |
| `gh workflow run <wf>` and `gh api -X POST repos/<o>/<r>/actions/workflows/<wf>/dispatches`, when `<wf>` matches an `environments.workflows` key | `guards.deployWorkflow` |
| `aws … delete-*/terminate-*/purge-*`, `aws s3 rm/rb`, `az … delete/purge`, `Remove-Az*` | `guards.cloudDestructive` |
| `DROP`/`TRUNCATE` via `-c`/`-e`/`-Q`, heredoc, pipe or `Invoke-Sqlcmd -Query` | `guards.sqlDestructive` |
| a SQL client or `ssh` aimed at a declared `production.*` pattern | `guards.prodDatabase` / `guards.prodServer` |
| the AWS profile/region or Azure subscription of every `aws`/`az` command | `cloud.awsProfiles`, `cloud.awsRegions`, `cloud.azureSubscriptions` |

`block` answers `permissionDecision: "deny"`, `ask` answers `"ask"`, and `allow`
prints nothing — the guard never answers `"allow"`, which would skip your own
permission prompt. `report` mode answers with no decision at all and a
`systemMessage` saying what `block` would have done. Every refusal names its
rule, e.g. `[terraformApply] terraform destroy: guards.terraformApply is block`.
A command it could not read — nested more than six shells deep, or hook input
that is not a readable Bash/PowerShell call — is refused as `[cloudGuard]`; a
destructive-capable tool behind `xargs`/`parallel` is judged as destructive
under its own rule. `--dry-run`, `-WhatIf` and `-help` are not destructive.

**Environments and destroys (crew 1.0.42).** A terraform command is also
judged by its target environment and by whether it destroys, both read without
running terraform. Under `guards.terraformApply: ask`, an `apply` of a saved
plan that deletes nothing, and `workspace new` / `select -or-create`, aimed at
a workspace matching a repo-only `environments.nonProd` glob **runs
unattended** and is logged as `env:nonProd:<name>`. Production does too only
when `environments.prodUnattended` is `true` in **both** config layers, and it
says so on screen. An environment crew cannot identify — no signal, a
non-literal `TF_WORKSPACE=$WS`, signals that disagree, a `cd` in the command,
no `.terraform/environment` (which is not read as `default`) — is **unknown**,
and nothing allows unknown unattended. A saved plan is readable only through
its sidecar, written outside the hook:

```bash
terraform plan -out p.tfplan
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tfplan.py" summarize p.tfplan
TF_WORKSPACE=staging terraform apply p.tfplan
```

Three separate commands: a saved-plan apply is trusted only when it is the
only command in its invocation, since anything beside it could rewrite the
plan after the hook hashed it. The sidecar records the workspace the plan is
bound to, read from the plan file, and any directory or environment change
the hook cannot read makes the environment unknown.

**Terraform lines are judged word by word, or not at all (crew 1.0.42).** A
command line that RUNS `terraform`, `terragrunt` or `tofu` — its command word,
after assignments and wrappers such as `env`, `sudo`, `timeout` or `xargs`,
read with quotes and escapes taken out, so `"terraform"`, `t'erraform'`,
`$'\x74erraform'` and `terr\aform` all count, or a command inside `bash -c`,
`eval`, `pwsh -c`, `$(...)` or backquotes — is judged only
when every word on it is a plain literal (`^[A-Za-z0-9_./:=@%+,-]+$`) joined by
`;`, `&&`, `||`, `|`, `&` or a plain `>`/`>>`/`<` redirection. Anything else on
such a line — a quote, `$`, a backquote, a backslash, a glob or brace, `<(`, a
heredoc or here-string, a comment, a control character — makes it **could not
tell**: asked about when someone is attending, **refused unattended** (and
under `block`), never allowed, logged as `could-not-tell`. The check reads the
raw text before the parser does, so no parser mistake can turn a shape it
misread into an allow. Unusual quoting on a terraform line is asked about, not
allowed; spell the line with plain words to have it judged. The rule is about
the command being run: mentioning terraform in a commit message, a search or a
file name (`git commit -m "fix terraform apply"`, `grep 'terraform apply' .`,
`vim terraform.tf`) is not gated. A command word made at run time (`$1`,
`"$@"`, `$0`, `$SHELL`, `$(...)`, a variable crew cannot resolve) is judged as
crew 1.2.35 judged it, whatever follows it. A line crew cannot split with
certainty (a `case` arm, an array, `$((...))` with a `$` inside), or one whose
only run-time word is an assignment (`W=$S/x`), is could not tell only when a
COMMAND WORD on the line could run terraform, terragrunt or tofu (crew 1.2.36,
SRL-2308): directly or by path, behind a wrapper (`env`, `npx`, `sudo`,
`timeout`, `xargs`, ...), or as a variable whose value names one
(`x=terraform; $x destroy` is refused). A variable is a program only when
every way the line sets it is a plain `NAME=path` (or a `for NAME in` list of
them) standing alone, run unconditionally before it is used, outside any
block, subshell or pipeline, naming a program that runs nothing else; a bare
name (`T=ls`, an inherited function may shadow it), `T=$X`, `T=$1`,
`T=/opt/tf/t*`, `T+=x`, `read T`, `T=x cmd` or a `source` on the line leave it
run-time, so `$T apply` is refused. Interpreter code (`python3 -c`, `node -e`,
`perl -e`, a heredoc or here-string fed to one) that can start a process is
refused when the line names terraform or the code builds its command
(`"terra"+"form"`, `sys.argv`); so is an awk program that can start one
(`system()`, `print | "cmd"`, `"cmd" | getline`, `|&`) and a sed script with
the `e` command or the `s///e` flag. A program by path under a run-time
directory (`$T/stub`) keeps its literal name only when no operand is a
changing verb and the line writes nothing into that directory or at that
name; otherwise 1.2.35's rule decides, so `T=$(mktemp -d); printf ... >
"$T/stub"; "$T/stub" apply` is refused. A mere mention no longer counts there:
`W=$S/wt; python3 - <<'EOF'` with "apply" in the Python, a `sed` range or
`python3 -c` script on a line with a `$VAR`, a heredoc writing notes, and
`$T/stub --check` all pass, and so does `$EDITOR notes.md`. A line that hands text to shell code (`bash`, `eval`, `ssh`,
`source`, `parallel`, a function or alias definition) keeps the older, wider
rule over the whole line: any word naming terraform.

**A terraform command crew cannot follow is could not tell even in plain
words.** An alias (`alias tf=terraform`, `hash -p`, PowerShell's `Set-Alias`
and `alias:` drive), a binary the same line copies or links to another name
and then runs by that name with `destroy`, `apply` or `workspace`, zsh's
`=terraform`, a script runner crew does not split (`flock`, `ssh`, `source`)
and PowerShell's `Start-Process terraform` are asked about and refused
unattended: the parser would not see terraform in them. Run terraform by its
own name to have it judged. Options before the subcommand are read the way
terraform and terragrunt read them, so `terragrunt --working-dir infra
destroy` is a destroy; an option crew does not know, followed by `apply` or
`destroy`, is read as that operation. Two things are not gated for their
quoting: a read-only subcommand (`plan`, `show`, `output`, `fmt`, `validate`,
`init`, `workspace list`, ...) spelled where it cannot be another one, so
`terraform plan -var 'environment=staging'` runs as before; and the arguments
of any program that is not terraform (`cp -r terraform "$BACKUP_DIR"`, `rg
terraform "$file"`). A PowerShell line follows the same command-word rule:
`&`, `.`, `terraform.exe`, a path and `Start-Process terraform` run terraform,
`git commit -m "fix terraform apply"` and `Select-String terraform *.md` do
not.

**Workflow dispatches (T-0009).** `environments.workflows` is a repo-only map
from a workflow glob (fnmatch, case-insensitive, against the argument as
written) to where its environment comes from: `input:<name>` (the dispatch
input) or a fixed environment name.

```json
"environments": {
  "nonProd": ["dev", "qa", "staging"],
  "workflows": {"deploy.yml": "input:environment", "deploy-prod.yml": "production"}
}
```

A `gh workflow run <wf>` whose `<wf>` matches a key is a `guards.deployWorkflow`
finding, and so is the REST call it makes, `gh api` with method POST (`-X
POST`, `--method POST`, `-XPOST`, or fields/`--input` with no method) on
`repos/<o>/<r>/actions/workflows/<wf>/dispatches` — both go through one
classifier. The input comes from `-f`/`-F`/`--raw-field`/`--field` (`<name>=v`
for `gh workflow run`, `inputs[<name>]=v` for the REST form, whose top-level
`ref` is the branch and never an input), and every occurrence must agree.
Under `ask` (in **both** layers — the ratchet), a nonProd environment runs
unattended and is logged as `env:nonProd:<name>`; production runs unattended
only with `environments.prodUnattended` true in both layers, and says so on
screen. **`allow` covers nonProd only**: production without `prodUnattended`,
and an environment crew cannot identify, still ask when attended and are
refused unattended. Unknown is: no input given (the workflow's default is not
read), conflicting values, a second workflow argument, and no workflow named
(gh prompts). A workflow matching no key is **not judged**, as before; so with
`workflows` at `{}` no `gh` line is judged at all. `environments.workflows`
does not engage the terraform layer. A deploy command also declared in
`.crew/verify.json` still passes through `promote-gate.sh`, whose
`requireHuman` is independent of `prodUnattended`.

**The dispatch grammar.** A line that sends a dispatch is judged only when
every word on it is a plain literal (letters, digits and `_./:=@%+,-`) or one
whole single-quoted word, and its only operators are `;`, `&&`, `||`, `&`, a
newline, `>`/`>>`/`&>`/`&>>` to a plain word, and `2>&1`. Anything else on it
is **could not tell**: asked about when someone is attending, refused
unattended at every setting, and approved one command at a time by the marker
the refusal names, which covers those exact bytes and nothing else. So is a
dispatch the guard does not follow — inside `bash -c`, `eval` or `pwsh -c`,
behind `xargs`, `parallel` or `find -exec`, through an alias or a copy of `gh`
made on the line, or a command word made at run time — and gh reading its
inputs from stdin or a file. Crew never reads stdin. A command word made at run
time is judged by the shape of what follows it, not by what the line mentions:
`$X $Y run deploy.yml`, `$C` alone (bash may split it into a whole dispatch),
`xargs -I CMD CMD workflow run ...`, `Start-Process $x -ArgumentList
'workflow run ...'` and an alias pointed at a run-time value all ask, while
`$X pr create` does not. So does every dispatch while the machine-global
config's `environments` block is malformed. A PowerShell launcher or alias
line (`Start-Process`, `saps`, `Set-Alias`, `New-Alias`, an `alias:` path)
holding gh, `workflow` or a word made at run time is could not tell unless
every parameter on it is a full, value-taking name: a switch (`-NoNewWindow`,
`-Wait`, `-Force`), an abbreviation (`-Fi`) or a parameter alias (`-Args`)
refuses it, even on a line that sends nothing (`Start-Process $exe -Wait`).
gh and `workflow` must be in the same command to count, so `alias g=gh; echo
workflow` is not judged, while an `alias` or `hash -p` pointing at gh makes
that name gh for the rest of the line — the commands after it, or the whole
line when a loop, a function or a `trap` on it can run earlier text later.
An alias counts only when its value's last command runs gh (`alias g='env
gh'` does, `alias g='echo gh'` does not). In PowerShell a comma inside one
whole single-quoted word is text (`-f 'environment=staging,west'`); a bare
comma makes an array and is refused. Refused, and how to write it instead:

| Refused | Write instead |
|---|---|
| `--json` / `--input -` with a body on stdin, `-F name=@file` | `-f name=value` fields |
| `"Deploy Staging"` (double quotes) | `'Deploy Staging'` |
| `repos/{owner}/{repo}/...` unquoted, `-f inputs[environment]=x` | quote the word: `'repos/{owner}/{repo}/...'`, `-f 'inputs[environment]=x'` |
| `... \| tee log`, `echo x \| gh ...` | `... > log` |
| `-f environment=$ENV`, `${ENV}`, `$(...)` | the literal value |
| `bash -c 'gh workflow run ...'` | the `gh` command itself |
| `Start-Process -NoNewWindow $x ...`, `-Fi`, `-Args`, `Set-Alias -Force g gh` | full parameter names and no switches, or `gh workflow run ...` directly |

A literal `gh workflow run ... --help` (or `-h`) prints help and dispatches
nothing, so it is not judged; `-f environment=--help` is a value, and after
`--` a `--help` is a second workflow argument. Other `gh` commands (`gh pr
create --title "..."`) are never gated. `crew_dispatch.dispatch_answer` is the
one entry point a caller (autopilot, the promote path) uses, and it answers
`nonProd`, `prod`, `unknown` or `unlisted`.

**The always-stops.** A destroy is never applied unattended, at any setting:
`destroy`, `apply -destroy`, `apply -replace`, `workspace delete`, a saved plan
that deletes, and any apply whose plan crew cannot read — including
`terraform apply -auto-approve` with no saved plan. **BREAKING in 1.0.42:**
under `terraformApply: allow` these now ask (and are denied unattended) where
they used to run; approve one command with the marker the refusal names.
`prodUnattended` does not stand down `promote-gate.sh`'s `requireHuman`, nor
its review-evidence check (L-0703).
Details: [CONFIG.md §16](CONFIG.md), `environments.*`.

**Identity.** The repo-only `cloud` block pins which AWS profiles/regions and
Azure subscriptions this checkout may act as. A command resolving to anything
else is denied. One whose identity the guard cannot name — no profile set,
static `AWS_ACCESS_KEY_ID` keys, an Az PowerShell context, or any destructive
command in a repo that pinned nothing — is **unknown**, and unknown is never
allowed unattended: it asks when a person is there, and is denied under
`CREW_UNATTENDED=1`, `CI`, or a `bypassPermissions`/`dontAsk` session, with the
one-shot approval file (`.crew/.approved-guard-<rule>-<hash>`, 15 minutes, that
command only) named in the refusal. Once **any** pin is set, a read-only call
with an unnamed identity is unknown too; only a repo that pins nothing lets it
through, reported once. `az account show` is never run; the default
subscription is read from `azureProfile.json`. Details and examples:
`skills/crew-cloud/SKILL.md`.

**It fails closed only when it knows it is armed.** A config file that exists
and will not parse forces `block`; so does a malformed `cloud` block under an
armed guard. With no usable python, each wrapper greps both config files for
`cloudGuard` and refuses (exit 2) if either arms it. The bash wrapper judges
every Bash call and the `.ps1` wrapper judges every PowerShell call — the
split is by tool, not by OS, decided in `cloud_guard.py`'s `stands_down` from
which flavour set `CREW_CLOUD_GUARD_FLAVOUR`, so the guard runs once per call
on any platform, never twice and never zero times.

**What it cannot see:** a command named through a variable, a script file it
runs, SQL built at runtime, Terraform's provider credentials, and MCP tool
calls. For the terraform name specifically: a name built at run time from
parts crew never sees whole (`$TF`, `$(printf te)$(printf rraform)`, a
PowerShell string concatenation) and a wildcard that keeps fewer than three
letters of it (`t*`) are not read as terraform. For workflow dispatches: a
spelling of a deploy workflow not listed as a key (its display name or numeric
id — list every spelling you use), the workflow YAML (`environment:` keys,
`${{ inputs.* }}`), `gh run rerun`, and a dispatch sent with `curl`. Tests: `tests/test_cloud_guard.py` (every case through python, bash and
pwsh), `tests/test_cloud_guard_environments.py` and `tests/test_crew_tfplan.py`
(the environment layer and the sidecar), `tests/test_cloud_guard_deploy.py`
(workflow dispatches), and the `cloud-guard.sh` section of
`hooks/scripts/_test/run-tests.sh`.

#### What the guard does not catch

The guard is a tripwire for an agent's accidental or direct destructive
command, not a sandbox against deliberate evasion (owner decision,
2026-09-26). It catches `terraform`, `terragrunt` and `tofu` written directly:
bare or path-qualified, behind the listed wrappers (`env`, `sudo`, `doas`,
`nice`, `ionice`, `timeout`, `stdbuf`, `nohup`, `command`, `exec`, `time`,
`xargs`, `parallel`, `sem`, `watch`, `flock`, `chroot`, `nsenter`, `wsl`,
`pwsh -c`, `aws-vault exec`, `unbuffer`), inside `bash|sh|zsh -c` and `eval` strings, with global options before the
subcommand (`-chdir=`, terragrunt's `--working-dir`), and PowerShell's `&`,
`.`, `terraform.exe` and `Start-Process`. PowerShell strips the same listed
wrappers. An option a listed `xargs`, `parallel`, `sem`, `aws-vault` or
`unbuffer` does not know makes a line that names terraform could-not-tell:
crew cannot tell where the command starts. So does an `Invoke-Expression`
whose script is not a literal string. terragrunt's `apply-all`,
`destroy-all`, `stack run`, `graph` and `backend delete` are read as the
apply or destroy they run, and `terragrunt exec -- cmd` is unwrapped like any
listed wrapper. On a PowerShell line, every mention of terraform, tofu or
terragrunt must be one crew accounts for -- the command word of a command it
judged, a literal script given to `Invoke-Expression`, or, when nothing on the
line can run a value made at run time, a literal argument of a plainly named
command (`git commit -m "terraform destroy"`) or a string it only prints or
assigns -- or the line is could-not-tell (`return terraform destroy`,
`$t="terraform"; Start-Process $t destroy`,
`[Diagnostics.Process]::Start("terraform","destroy")`). A mention inside a
comment is dropped before counting; a name built at run time from parts is
still not read (above). It does not try to catch a program renamed or
started some other way. Each of these runs unjudged:

- a rename by alias, function, symlink or copy, unless the same line makes a
  plain copy or link and runs it by that name: `env ln -sf /usr/bin/terraform ./ls && PATH=.:/usr/bin ls destroy -auto-approve`,
  `X=1 cp /usr/bin/terraform ./ls && PATH=.:/usr/bin ls destroy -auto-approve`,
  `sudo ln -s /usr/bin/terraform /usr/local/bin/tf; tf destroy -auto-approve`
- `env -S` escape strings: `env -S 'terraform\_destroy\_-auto-approve'`
- BusyBox applets: `busybox env terraform destroy -auto-approve`,
  `busybox timeout 60 terraform destroy -auto-approve`
- git `!` aliases: `git -c alias.tf='!terraform' tf destroy -auto-approve`
- an interpreter whose code names the tool only at run time or from a file:
  `python3 -c "import os; os.system(os.environ['TF'] + ' destroy')"`,
  `python3 deploy.py`. Since crew 1.2.36 (SRL-2308) code on the command line,
  or fed by a heredoc or here-string, that names terraform and does more than
  print is refused: `python3 -c 'import os; os.system("terraform destroy")'`
- awk and sed on a line crew reads cleanly: `awk 'BEGIN{system("terraform
  destroy")}'`, `echo terraform destroy | sed e` (as in 1.2.35; on a line crew
  cannot read, or after a run-time assignment, they are refused since crew
  1.2.36), and a sed script made at run time whose value adds an `e` flag on
  a line that does not name terraform
- a script file: `bash deploy.sh`, or a literal path such as `/tmp/x/stub
  destroy` on a line crew reads cleanly (as in 1.2.35)
- a wrapper not in the list above: `strace -f terraform destroy`,
  `strace -f terraform $'\x64estroy' -auto-approve`, `strace =terraform destroy`,
  `systemd-run terraform destroy`
- a program that runs another it is handed: `git bisect run terraform destroy`,
  `git -C infra bisect run terraform destroy`,
  `git -C add bisect run terraform destroy`, `rg --pre terraform destroy .`
- a container's entrypoint: `docker run --rm hashicorp/terraform:1.9 destroy -auto-approve`

No command-line guard can close these: unattended work has to run
interpreters, scripts and build tools, and any of them can start terraform
under another name, so a guard that refused them would refuse the work
itself. The real boundary is the credentials an unattended run holds — scope
them so the run cannot destroy what it must not. That is
`crew_unattended.py launch`, next.

#### Unattended runs: sealed cloud credentials

`hooks/scripts/crew_unattended.py` (T-0044) starts an unattended Claude
session holding short-lived credentials for ONE identity the machine owner
named, with the machine's credential stores unreadable to it, or refuses and
starts nothing. It holds whatever the command line says, because it decides
what the process can authenticate as and what it can read.

```bash
python3 plugin/crew/hooks/scripts/crew_unattended.py check  --root . [--environment dev] [--json]
python3 plugin/crew/hooks/scripts/crew_unattended.py launch --root . [--environment dev] -- claude [args...]
```

The owner (or the owner's scheduler) runs it. Crew never starts an unattended
session by itself, and a hook cannot change the environment of a session that
is already running, so `/crew:autopilot` touching the cloud unattended is
started this way. The identity comes from `unattendedCloud` in the machine
file `~/.claude/crew/config.json` only (CONFIG.md, "`unattendedCloud`"); a
repo copy is ignored and reported. Seven checks run in order, and the first that
is not `ready` refuses with its reason printed verbatim. `unknown` ("could not
tell") refuses exactly like `refuse` and keeps its own label:

1. **platform** -- native Windows refuses: `sandbox probe not implemented for native Windows`.
2. **config** -- no identity or profile named, a provider other than `aws`, or
   `--environment NAME` without both a machine `nonProd` entry and the repo's
   `environments.nonProd` classifying `NAME` as nonProd. There is no
   production entry.
3. **settings** -- the launch passes `--setting-sources user`, so the repo's
   `.claude/settings.json` and `.claude/settings.local.json` do not load
   (their `excludedCommands`, `allowRead`, hooks and `env` never reach the
   sealed session). It fails closed anyway: a repo file with any `sandbox`
   key or a `Read` allow rule refuses. Your own `~/.claude/settings.json`
   (or `$CLAUDE_CONFIG_DIR/settings.json`) does load and its lists merge with
   the sealed ones, so `sandbox.excludedCommands` (those commands run
   unsandboxed), a `sandbox.filesystem.allowRead` entry at or under a store or
   holding a glob, or `sandbox.filesystem.disabled: true` refuses. A settings
   file that exists but is not a JSON object is `unknown`. In a linked git
   worktree Claude Code reads `.claude/settings.local.json` from the MAIN
   checkout's root, so that file is checked too; a `.git` file whose main
   checkout cannot be found is `unknown`.
4. **version** -- `<claude> --version`, the same file the probe and the
   launch use, must print a version (`2.1.289 (Claude Code)`) at or above
   2.1.246: below it `--setting-sources` does not keep an excluded source's
   `sandbox.filesystem` entries, `Edit` rules and `Read` denies out of the
   sandbox. An older version, output that does not parse (a pre-release tag
   included), a non-zero exit or a timeout is `unknown`.
5. **export** -- `aws configure export-credentials --format process`, read
   into memory only. No `SessionToken` or `Expiration` (static keys), under 15
   minutes of lifetime, a non-zero exit, a timeout or non-JSON output refuses.
6. **identity** -- `aws sts get-caller-identity` in the sealed environment
   must print an ARN that starts with the named prefix (an assumed role ending
   in `/`); a `:user/` ARN or any other role refuses.
7. **sandbox** -- one headless `claude -p` call, made by the same `claude`
   file the launch will exec, from `--root`, with the same leading flags,
   runs a probe that tries `head -c1`/`ls` and `python3 open()` on every store
   root that exists plus a bounded sample of files inside each (two per
   directory, twelve per store: the sandbox denies a path and all under it, so
   the root is the test and the sample catches a deny that stopped at the
   directory). The output carries an index per store, the nonce first and an
   end marker last, so it stays far under the Bash tool's output limit. The
   verdict is read from the stream-json tool results, never the model's
   prose: any `OPEN` refuses; a missing nonce, a missing end marker (output
   cut short), a store not reported, an `ERR` or no tool call is `unknown`.

The launched session is exec'd as
`<claude> --settings <sealed> --setting-sources user [your args]`, in `--root`
(whatever directory the launcher was started from), and gets: no inherited
cloud or forge credential variable (`AWS_*`, `AZURE_*`, `ARM_*`, `CLOUDSDK_*`,
`GOOGLE_*`, `TF_TOKEN_*`, `KUBECONFIG`, `GITHUB_TOKEN`, `GH_TOKEN`,
`GH_ENTERPRISE_TOKEN`, `GITHUB_ENTERPRISE_TOKEN`, `DOCKER_CONFIG`,
`DOCKER_AUTH_CONFIG`, `TF_CLI_CONFIG_FILE`, `TFE_TOKEN`, `GITLAB_TOKEN`, and git's and
ssh's credential pointers `GIT_ASKPASS`, `SSH_ASKPASS`, `SSH_AUTH_SOCK`,
`GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_*`/`GIT_CONFIG_VALUE_*`,
`GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`, `GIT_SSH`, `GIT_SSH_COMMAND`, `TERRAFORM_CONFIG`,
`GH_CONFIG_DIR`, `XDG_CONFIG_HOME`);
git's `credential.helper` reset to empty through `GIT_CONFIG_COUNT` (so no helper your
`~/.gitconfig` names answers git); the exported
temporary credentials; `AWS_EC2_METADATA_DISABLED=true`; `CREW_UNATTENDED=1`
(so T-0005's guard judges it unattended); `AWS_CONFIG_FILE` at a region-only
file and `AWS_SHARED_CREDENTIALS_FILE` at a path that does not exist, both in a
mode-0700 `crew-sealed-<pid>-*` temp directory that holds no credential; and
`--settings` with `sandbox.enabled`, `failIfUnavailable: true`,
`allowUnsandboxedCommands: false` (which also makes the sandbox admin-required,
so Claude Code itself ignores a repo's loosening settings), filesystem
isolation pinned on, and every store -- `~/.aws` whole, `~/.azure`,
`~/.terraform.d/credentials.tfrc.json`, `~/.config/gcloud`, `~/.kube`,
`~/.config/gh`, `~/.docker/config.json`, `~/.claude/crew/config.json`, `~/.ssh`,
`~/.git-credentials`, `~/.config/git/credentials`, `~/.terraformrc`, from
both `$HOME` and the account's real home -- in `sandbox.filesystem.denyRead`
and `denyWrite` and as `Read(...)` and `Edit(...)` denies. The sealed
directory and the user settings file are write-denied too, so the session
cannot rewrite its identity or its settings mid-run. A command other than
`claude`, one that is not an executable file or on `PATH`, or one passing its
own `--settings`/`--setting-sources`, refuses. It prints the checks and the
ARN, never a credential. `exec` leaves no process to clean up, so the next
`check` or `launch` removes any `crew-sealed-<pid>-*` directory you own whose
process has exited, and leaves one whose process is alive.

Because the session cannot read `~/.config/gh`, `~/.docker/config.json` or
`~/.kube` and holds no `GH_TOKEN`, `gh`, registry pushes and `kubectl` have no
credentials in an unattended run. That is deliberate: the run holds the one
cloud identity it was handed and nothing else. Claude Code itself configured
to run on Bedrock or Vertex through those variables is not supported by the
launcher, for the same reason.

**Host requirement.** Claude Code's sandbox has to run commands on the host.
Where it starts but cannot run anything -- measured on a host with
`kernel.apparmor_restrict_unprivileged_userns = 1`, every Bash call failing with
`apply-seccomp: write /proc/self/setgroups (nested userns is capability-restricted; caller must provide CAP_SYS_ADMIN): Permission denied`
-- the probe finds no nonce and every launch refuses with `sandbox: unavailable`
and that line. Making it usable (or running unattended work as a separate OS
user or container) is the host owner's call.

**Accepted risks.** Credentials that expire mid-run fail closed. Git's credential helpers
are reset for the session, but a key file `~/.gitconfig` names elsewhere
(`core.sshCommand -i <path>`) is outside the denies. A failing `aws` command's stderr is never printed (it may hold a
secret): the check names the command and its exit code, and you run it by hand. Claude Code
applies `Read(...)` denies to Grep and Glob "best-effort" (its own words); a
gap there is unmeasured. `/proc/<pid>/environ` of other root processes is
outside the session. The probe nonce is in the prompt, so a model that chose
to fake the probe's output could; the probe guards against an unusable or
leaky sandbox, not against an adversarial probe session. The probe tries
`head`, `ls` and `python3` only: a store that one of those can read is
refused, and the settings check -- not the probe -- is what keeps an excluded
or unsandboxed command out. Managed (organisation) settings always load and
are not inspected; an `excludedCommands` there is the administrator's. Hooks
and MCP servers run outside the sandbox: the user settings' ones are yours and
load; a repo's `.claude/settings.json` hooks do not load, and a repo's
`.mcp.json` servers are not inspected by the launcher. `--setting-sources`
excluding project settings from the sandbox build needs Claude Code 2.1.246 or
later, which the version check enforces; the admin-required behaviour needs
2.1.285 or later and is not checked, since the settings check already refuses
what it would ignore. The stale-directory sweep asks `kill(pid, 0)` in its own
PID namespace: a process in another namespace sharing the same `/tmp` is
invisible to it, so a sealed directory still in use there can be removed (its
settings file is already loaded; the session keeps running). Azure and TFC/HCP
are a provider seam only: any key other than `aws` refuses as not implemented.

### Environment guard

A `PreToolUse` hook on the **Bash and PowerShell** tools
(`hooks/scripts/env-guard.sh` / `env-guard.ps1`, both delegating to
`env_guard.py`; L-0772). It exists because a command that prints the process
environment puts every credential in it into the agent's context, and from
there into the session transcript on disk and the conversation sent to the
model provider. **It ships off** — `guards.envGuard: "off"` — because a hook
that can block defaults off. **Start with `report`:** every refusal it *would*
make goes to `.crew/guard.log` and nothing is refused; read the log, then set
`block`. A malformed value reads as `block`; the two layers ratchet, so a repo
cannot turn off a machine-global `block`.

It judges the command's own text, read the way the shell will read it —
through `bash -c`, `eval`, `$( )`, backticks, `<( )`, pipelines, lists, loops,
function bodies and heredocs fed to a shell or an interpreter; behind `sudo`,
`doas`, `command`, `exec`, `nohup`, `nice`, `time`, `timeout`, `stdbuf`,
`setsid`, `xargs`, `watch`, `env NAME=value`, `find -exec`, `ssh host`,
`docker`/`podman exec`, `kubectl exec --` and `wsl`; and in PowerShell through
`pwsh -Command`, `Invoke-Expression` of a literal and `& { }`.

| Refused | Label |
|---|---|
| `env` with nothing to run (bare, `-0`, `-u NAME` only, assignments only), `printenv` with no operand, bare `set`, `export`/`export -p`, `declare`/`typeset`/`readonly` with no name (`-f`/`-F` excepted), `systemctl show-environment`, `tmux show-environment` with no name, `ps` with a BSD `e` flag (`ps eww`) | `env-dump:<form>` |
| a `/proc/<pid>/environ` (or a task's) as an operand or a `<` source; the last segment is a glob, so `env*` counts. A `git commit -m` message, a `grep`/`rg` pattern and `echo`/`printf` text are mentions, not reads | `env-dump:proc-environ` |
| inline interpreter code reading the whole environment: python `os.environ`, node `process.env`, `Deno.env.toObject()`, perl `%ENV`, ruby `ENV`, php `getenv()`/`$_ENV`/`$_SERVER`, awk `ENVIRON`, jq `env`/`$ENV` — each not followed by one name | `env-dump:<language>` |
| PowerShell: the `env:` drive as a whole or by wildcard (`Get-ChildItem env:`, `gci -Path Env:\`, `Get-Item env:*`, `Set-Location env:`) under any command but the write cmdlets, `[Environment]::GetEnvironmentVariables(...)`, `.StartInfo.EnvironmentVariables`, bare `Get-Variable` and the `variable:` drive, `cmd /c set` | `env-dump:<form>` |
| a credential-named variable in a printing form: `printenv NAME`, `declare -p NAME`, `$NAME` in `echo`/`printf` arguments, `$env:NAME` as a bare statement or a `Write-Output`/`Write-Host` argument, `Get-Item env:NAME`, `cmd /c echo %NAME%`, inline code naming one. Piping one into a login (`echo "$GITHUB_TOKEN" \| gh auth login --with-token`) counts: the guard does not try to prove where the pipe ends | `secret-read:<form>` |
| what it could not read: an unbalanced quote or unterminated substitution or heredoc, nesting deeper than 8, `eval`/`-c`/`Invoke-Expression` code or a program name that is not fully literal (`eval "$X"`, `bash -c "$CMD"`, `eval "$(ssh-agent -s)"`, `iex $s`, `& $cmd`), an indirect `${!name}`, malformed hook input, an unreadable config, an internal error | `could-not-tell:<why>` |

A credential-named variable matches a fixed, case-insensitive pattern
(`TOKEN`, `SECRET`, `PASSWORD`, `PASSPHRASE`, `CREDENTIAL`, `API_KEY`,
`ACCESS_KEY`, `PRIVATE_KEY`, a trailing `_KEY`, `AUTH`, `COOKIE`, `SESSION`,
`DSN`, `CONNECTION_STRING`, `DATABASE_URL`, `WEBHOOK`, `SIGNING`, a trailing
`_PAT`); `SSH_AUTH_SOCK`, `XAUTHORITY`, `GPG_AGENT_INFO`, `GIT_AUTHOR_*`,
`GIT_COMMITTER_*`, `XDG_SESSION_*` and `DBUS_SESSION_BUS_ADDRESS` are exempt.
A **use** stays allowed: `curl -H "Authorization: Bearer $GITHUB_TOKEN"`,
`$t = $env:GITHUB_TOKEN`, `docker login --password-stdin <<< "$PW"`. So do
`printenv PATH`, `echo $HOME`, `env FOO=bar cmd` (the wrapped command is judged
on its own), `env -i`, `set -euo pipefail`, `export FOO=bar`, `ps aux`,
`cat /proc/self/status` and `Remove-Item env:FOO`.

A refusal is a `deny` naming the labels and nothing else — never a value, a
variable's name or the command — and so is its `guard.log` row (time, rule,
mode, decision, label, `-`). Without a usable python both wrappers refuse
(exit 2) when a config file arms the guard, and stay out of the way when none
does. `crew_guards`' production read check asks this guard too, so
`ssh prod printenv`, `ssh prod env` and `ssh prod cat /proc/1/environ` are no
longer reads at `guards.prodServer: read` (**BREAKING**, by narrowing).

**Limits.** It is a denylist over the text it is handed, so it cannot be
complete: a script or program the command runs (`./x.sh`, `python x.py`,
`make`), an alias or function defined outside the command, `source` of a file,
a renamed binary and `docker inspect` are not seen. Known false positives are
refusals somebody notices, never silent allows: a `/proc/*/environ` mention
outside the mention-only positions (a `sed` script, `find -name`). The
stronger control — keeping credentials out of the agent's environment, or
redacting tool output — is L-0776.

### §11c. `change` — change requests, added by schema 7

Six keys, all settable in **either** layer. `change.requester` and
`change.implementor` are facts about a person and belong in the machine-global
file; `change.sdpTemplate` (`"Change Management Request"`),
`change.jiraIssueType` (`"Change"`) and `change.category` name what the desk
expects; `change.requireForProduction` ships `false`. §24b is what they do.

`change.requireForProduction` uses the same ratchet as the six `guards.*` keys
and **runs the other way round**: the narrower value is `true`, because
requiring a change request takes a capability away from a promotion. So a repo
may turn the requirement **on** and never off — a machine-global `true` is not
defeated by a `false` in a repo somebody cloned. Absent or `null` means
`false`, so upgrading changed nobody's promotions; a value that is neither
`true` nor `false` means `true`, so a typo stops a promotion and names the key
instead of quietly waving it through. CONFIG.md §17.

**Two of these are new refusals, not preserved ones.** `guards.adminMerge`
refuses `gh pr merge --admin`, which no crew guard refused before — measured
against the previous release, both flavours exited 0 — and
`guards.terraformApply` now covers `tofu` as well as `terraform`. Both were
bypasses rather than features. The migrate report's upgrade lines say so out loud,
because a user told only "the default is `block`, so nothing changed" will meet
a command that ran yesterday being refused today and go looking for a bug in
their tooling.

Both shell flavours resolve the value through `crew_config.py --guard`; neither
implements the layering itself. `guard.sh` and `guard.ps1` drift independently
— three of the bypasses fixed in #132 were open in both — and the rule whose
entire point is that a repo cannot widen it must not have two implementations.
Any failure of that resolver is `block`, with the reason on stderr: "could not
check" never becomes "checked, and fine".

The full key reference is **[`CONFIG.md`](CONFIG.md)** — every key in both
layers with its type, its default, which layer may set it, and a `path:line`
for the code that reads it. It is derived by executing `default_config()` and
`default_global_config()` rather than by reading comments, and it marks the
keys for which no consumer could be found instead of assuming one exists.

A sample `.crew/config.json` used to sit here, and a table of selected keys
under it. Both are **deleted rather than corrected**, deliberately. The sample
had drifted to 59 leaves against the real 85: twelve keys it showed no longer
existed, and twenty-eight that did were missing, including the whole `dev`
block. It drifted because it was a second copy of something derived elsewhere,
which is the same failure as the `UPDATE.md` mirrors and the stale schema
numbers — and like those, it passed every green check the repo had. A duplicate
that agrees today is a duplicate that disagrees later, so correcting it would
only have reset the clock.

`CONFIG.md` is derived by executing `default_config()` and
`default_global_config()`, and `tests/test_crew_config.py` holds drift gates
that compare both committed templates and `crew-setup/SKILL.md`'s inline copy
against those functions byte-for-byte. That is why there is no third copy here.

The promotion sequence lives in `.crew/verify.json`, not here — see §23. Config
holds preferences; `verify.json` holds the checks, so that one file answers "what
runs when" for both a working tree and a deployed environment.
