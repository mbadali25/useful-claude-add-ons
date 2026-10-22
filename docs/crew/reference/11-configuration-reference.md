<!-- Moved verbatim from plugin/crew/README.md (11. Configuration reference) by L-0726; shortened to an index by L-0725. The cloud-guard, unattended-run and environment-guard sections below are kept whole: they describe guard behaviour, not settings. -->

## 11. Configuration reference

Every setting, with its type, default and layer, is in the generated [`plugin/crew/CONFIG.md`](../../../plugin/crew/CONFIG.md). Why a key sits where it does, and how each guard decides, is in [`docs/crew/config-rationale.md`](../config-rationale.md). This page is the index to both.

### How the two files combine

- Two optional files: the repo's `.crew/config.json` and the machine's `~/.claude/crew/config.json`. Built-in defaults sit under both.
- The repo wins over the machine, which wins over the default, merged per key by `crew_config.resolve_config(root)`. Read effective settings through it, never from the file.
- `install.policy`, the twelve guards and `change.requireForProduction` do not follow that rule: the **narrower** of the two layers wins, so a cloned repo cannot widen what the machine owner allowed.
- Some keys are machine-only or repo-only: a repo-only key in the machine file is pruned and reported, and `schema` is never merged.
- A repo `null` on a key the machine file sets is dropped on read, so the machine value applies.

### See what is in force

- `/crew:config` shows where each value comes from and sets the machine or repo file from a menu. It prints the plan first and writes only after a yes.
- `python3 plugin/crew/hooks/scripts/crew_config.py --explain` prints every key with the layer that supplies it; `--explain --all` includes the defaults, and `--guard <name>` shows one guard with both layers and which one holds it down.
- Every writer backs up the file it replaces; `--rebuild` and `--restore <stamp>` recover a lost config.

### Common setups

- Turn the guards on: set `guards.profile` to `standard` (cloud guard blocking, role writes reported) or `strict` in the machine file. Narrow one guard with `guards.overrides.<guard>`. A repo can only narrow further.
- Try the cloud guard without refusing anything: `guards.overrides.cloudGuard` set to `report`, then read `.crew/guard.log`.
- Declare what is production: `production.databases` and `production.hosts` in the repo file (the guard matches nothing until you do).
- Arm autopilot: `autopilot.mode` set to `plan`, plus `scope.allowCliApproval` true in the repo.
- Pick reviewers: `qa.provider`, `qa.order`, `qa.fallback`, and role pins in `qa.roles` / `dev.roles`.
- Keep a machine-wide preference out of every repo: set it in the machine file and leave the key out of `.crew/config.json`.

### Removed settings

Sixty settings were removed and are now fixed values; the table is `plugin/crew/hooks/scripts/crew_dropped.py`. `/crew:migrate` (and `crew_migrate.py --global` for the machine file) moves a config to the current schema and refuses while a removed key holds a non-default value, until you drop it or pass `--accept-dropped <key>`. `crew_config.py --check` names any removed key still in a file.

### Cloud guard

A `PreToolUse` hook on the **Bash and PowerShell** tools
(`hooks/scripts/cloud-guard.sh`, delegating to `cloud_guard.py`; its
PowerShell twin was deleted in L-0727 slice 3, so a `PowerShell` call is judged by the `.sh`). **It ships off** — `guards.overrides.cloudGuard: "off"` — because a
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
| `terraform`/`tofu` `apply`, `destroy` (`-auto-approve`, `-chdir=` included) | `guards.overrides.terraformApply` |
| `terraform`/`tofu`/`terragrunt` `workspace delete` — a destroy, in every armed state; `workspace new`/`select -or-create` once `environments` is configured | `guards.overrides.terraformApply` |
| `git push --force`, `-f`, `--force-with-lease`, `+ref` | `guards.overrides.forcePush` |
| `gh pr merge --admin` | `guards.overrides.adminMerge` |
| `gh workflow run <wf>` and `gh api -X POST repos/<o>/<r>/actions/workflows/<wf>/dispatches`, when `<wf>` matches an `environments.workflows` key | `guards.overrides.deployWorkflow` |
| `aws … delete-*/terminate-*/purge-*`, `aws s3 rm/rb`, `az … delete/purge`, `Remove-Az*` | `guards.overrides.cloudDestructive` |
| `DROP`/`TRUNCATE` via `-c`/`-e`/`-Q`, heredoc, pipe or `Invoke-Sqlcmd -Query` | `guards.overrides.sqlDestructive` |
| a SQL client or `ssh` aimed at a declared `production.*` pattern | `guards.overrides.prodDatabase` / `guards.overrides.prodServer` |
| the AWS profile/region or Azure subscription of every `aws`/`az` command | `cloud.awsProfiles`, `cloud.awsRegions`, `cloud.azureSubscriptions` |

`block` answers `permissionDecision: "deny"`, `ask` answers `"ask"`, and `allow`
prints nothing — the guard never answers `"allow"`, which would skip your own
permission prompt. `report` mode answers with no decision at all and a
`systemMessage` saying what `block` would have done. Every refusal names its
rule, e.g. `[terraformApply] terraform destroy: guards.overrides.terraformApply is block`.
A command it could not read — nested more than six shells deep, or hook input
that is not a readable Bash/PowerShell call — is refused as `[cloudGuard]`; a
destructive-capable tool behind `xargs`/`parallel` is judged as destructive
under its own rule. `--dry-run`, `-WhatIf` and `-help` are not destructive.

**Environments and destroys (crew 1.0.42).** A terraform command is also
judged by its target environment and by whether it destroys, both read without
running terraform. Under `guards.overrides.terraformApply: ask`, an `apply` of a saved
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

A `gh workflow run <wf>` whose `<wf>` matches a key is a `guards.overrides.deployWorkflow`
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
Details: [config-rationale.md](../config-rationale.md), "guards", `environments.*`.

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
file `~/.claude/crew/config.json` only (config-rationale.md, "`unattendedCloud`"); a
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
(`hooks/scripts/env-guard.sh`, delegating to `env_guard.py`; L-0772; its
PowerShell twin was deleted in L-0727 slice 3, so a `PowerShell` call is judged by the `.sh`). It exists because a command that prints the process
environment puts every credential in it into the agent's context, and from
there into the session transcript on disk and the conversation sent to the
model provider. **It ships off** — `guards.overrides.envGuard: "off"` — because a hook
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
longer reads at `guards.overrides.prodServer: read` (**BREAKING**, by narrowing).

**Limits.** It is a denylist over the text it is handed, so it cannot be
complete: a script or program the command runs (`./x.sh`, `python x.py`,
`make`), an alias or function defined outside the command, `source` of a file,
a renamed binary and `docker inspect` are not seen. Known false positives are
refusals somebody notices, never silent allows: a `/proc/*/environ` mention
outside the mention-only positions (a `sed` script, `find -name`). The
stronger control — keeping credentials out of the agent's environment, or
redacting tool output — is L-0776.

