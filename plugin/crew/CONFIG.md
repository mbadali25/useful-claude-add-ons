# crew configuration reference

Generated from the code by `python3 docs/guides/crew/src/config_reference.py --write`. Do not edit by hand: `python3 scripts/check-marketplace.py` fails when this file is stale.
The reasoning behind the keys is in `docs/crew/config-rationale.md`.

103 keys: 64 settable in the machine-global file, 39 repo-only.

## The two layers

crew reads `~/.claude/crew/config.json` (the machine-global file: your
defaults for every repo on this machine) and `.crew/config.json` (the repo file:
facts about one checkout). The repo value wins over the machine value, which wins
over crew's built-in default, with these exceptions, each named in the Layer
column:

- A repo-only key in the machine file takes effect nowhere (pruned on read,
  refused on write).
- A ratcheted key resolves to the NARROWER of the two layers, so a cloned repo
  can tighten what your machine allows and never loosen it.
- A machine-arms key (`resume.auto`, `context.autoClear.enabled`,
  `context.autoClear.wrapUp`) is turned on only in the machine file; a repo can
  only veto it with `false`.
- A personal key (`crew_guards.PERSONAL_KEYS`) resolves per key to the stricter
  of the layers that set it; a layer that says nothing imposes nothing.
- A human-only opt-out key (`humanOnly.*`) has its own rules, below.
- A `null` in the repo file over a machine value inherits the machine value.
- In a linked git worktree with no config of its own, the main checkout's repo
  config is the one read.

## The human-only opt-out (`humanOnly`)

`humanOnly.approve` and `humanOnly.promoteMarker` are the owner's opt-out of
two human-only rules: `/crew:approve`, and the production promote marker
`.crew/.approved-<env>-<sha>`. `null` and `true` mean human-only. A `false`
takes effect only when all of these hold (`crew_humanonly.resolve`):

- it is in the machine file, or in a repo `.crew/config.json` that git does
  not track (a tracked or committed repo file can never opt out; "could not
  tell" counts as tracked);
- neither layer says `true` (a `true` anywhere vetoes, the stricter wins);
- it was written by a double confirmation: `crew_confirm_config.py propose`
  records the change and prints an id with two lines the agent relays to you
  word for word (the change, and the exact command; crew 1.3.70), and the
  owner types
  `/crew:confirm-config <change_id>` twice, in two prompts, within 15 minutes.
  `crew_config.py --set` and `/crew:config` refuse a `false` (and a repo
  `null` or removal, which drops a veto); a `false` written by hand reads as
  human-only.

**What is live (crew 1.3.33).** The prompt hook (`approval_hook.py`) now
records `/crew:confirm-config <change_id>` from a prompt you typed, so a
double confirmation can complete, and `humanOnly.approve: false` takes effect
through ONE decision point, `crew_ticket.cli_approval_allowed`: with an opt-out
in force a `cli`-recorded approval receipt counts as if `scope.allowCliApproval`
were `true`, for the scope guard, the Stop audit and every autopilot reader at
once. It does NOT let the session run `crew_ticket.py approve` (the scope guard
still refuses that text); the session's route is `crew_autopilot.py approve`,
which still needs `autopilot.approval` `self` or `risk` and `autopilot.mode`
`plan` or `backlog`. Anything unclear - the module missing, the resolver
raising or answering anything but exactly `humanOnly: false` - reads as
human-only.

**Finding the change id (crew 1.3.69).** Type `/crew:confirm-config` with no
id (or with an id that is wrong, expired or already used) and the hook refuses
it, records nothing, and lists the proposals in this machine's store
(`~/.claude/crew/confirm-config/`): each pending one's id, key, current value
-> `false`, layer and file, age, time left and confirmations so far, then up
to five from the last day that can no longer be confirmed. With none pending
it says so, and why one may be missing: none was made, it expired, it was
already applied, cancelled or refused, or it was proposed under another home
directory (WSL rather than Windows has its own store). The store is per
machine and home directory, not per repository, so a proposal made in one repo
or worktree is listed from any other. The listing never confirms: even with
exactly one pending proposal a bare `/crew:confirm-config` records nothing,
because "the only pending one" is a choice whoever ran `propose` makes, and the
id you type is what binds the change. A store crew cannot read is reported as
"could not tell", never as none pending.

**Still human-only (crew 1.3.33).** No hook reads `humanOnly.promoteMarker`:
the promote marker is human-only by instruction alone, and no hook checks who
created it. `crew_confirm_config.py resolve` shows what each key would
resolve to.

**Who can write the receipts.** The double confirmation is recorded only by
the prompt hook, from your own prompt. The scope guard (when `scope.mode` is
not `off`) refuses every Write/Edit under `~/.claude/crew/confirm-config/` and
every shell command that names that store beside a writing word. That is a
textual tripwire, not a sandbox: a session that sets out to forge a receipt
(`python -c`, an encoded command, a variable holding the path) still can, and
`scope.mode: off` has no tripwire at all. Treat `humanOnly` opt-outs as
meaningful only with `scope.mode` `block`.

## Git commands (`guards.git.allow`, crew 1.3.153)

The owner's switch that stops crew's command guards from blocking or asking on
git commands, destructive ones included. Off by default (`null`, or `"off"`).

| Value | What passes |
|---|---|
| `null` / `"off"` | nothing changes: every guard judges git as before |
| `"all"` | a line made only of plain git commands |
| `["commit", "push", ...]` | such a line whose every git command's subcommand is listed; every other line keeps today's checks |

A listed subcommand passes with every option it takes: listing `push` also lets
`git push --force` and `git push origin +main` through, because the force-push
rule is a finding on the `push` subcommand. To keep force pushes stopped, leave
`push` out of the list. The cloud guard reads git's abbreviated long options (`--force-with-leas`, `--mirr`) as the force pushes they are, and `--mirror`, `--delete`/`-d` and `--prune` as force pushes too, and a refspec with a leading `:` (`git push origin :topic`, which deletes the remote branch) the same way, with the switch on or off. The cloud guard skips the global options that take a value (`-C`, `-c`, `--git-dir`, `--work-tree`, `--namespace`, `--exec-path`, `--config-env`, `--super-prefix`, `--attr-source`) when it finds the subcommand, the same set the switch reads. `--force-if-includes` alone is not one (git 2.56 leaves a non-fast-forward push rejected without a lease; with `--force-with-lease` the lease is the finding), and an option's value is not read as a refspec: `git push -o +ticket=1 origin main` forces nothing (`-o` and `--push-option` take the next word, `-ofoo` carries it attached; `-fo x` is still `-f`; in an attached value such as `-ofoo` only the letters before the `o` are flags, so `-ofoo` is no `-f` while `-fofoo` is). A digit is a short flag too (`-4` and `-6` are the IPv4/IPv6 options), so `-4f`, `-f4`, `-6f`, `-46f` and `-u4f` are force pushes: the finding was missed before, with the switch off as well as on, and only real force pushes are newly reported (`-4`, `-46`, `-u4` and `-4u` are not). Residual: a force that git reads from configuration the guard does not read (`git -c remote.origin.mirror=true push origin`, `git -c remote.origin.push=+HEAD:refs/heads/main push origin`) gives no force finding; `guards.git.allow` still never exempts such a line, because any `-c` is held, and no cheap read of git's config for this exists.

What it loosens, and nothing else: the cloud guard's `guards.forcePush` rule
(`git push --force`, `+ref`) and the promote gate, so a commit message or
that merely mentions a declared deploy no longer trips it. A declared
deploy that is itself a git command (`git push prod main`) stays gated: that
is a deploy, not a git block. A declared deploy that computes its ref with a read-only value (`-f ref=$(git rev-parse HEAD)`, also `--short[=N]` or `--abbrev-ref`, as the last part of a word) is not read as hiding git, so the switch still works in that repo; any other substitution, a backtick, a redirection, a second line or a code-running git option in a declared deploy still exempts nothing there. `gh` is not git: `gh pr merge --admin`
(`guards.adminMerge`), workflow dispatches and `gh api` calls are untouched.

**The line is ONE plain git command, fail-closed (crew 1.3.153).** A command
line is exempt only when it is a single simple command: exactly `git` - not a
path (`/usr/bin/git`, `./git`, `git.exe`), not preceded by `command`, an
assignment, `cd` or a function, alias or `shopt` that redefines git - followed
by plain literal words, read by ONE reader that both the cloud guard and the
promote gate use. Nothing else is read at all:

- NO separator: `;`, `&`, `&&`, `||`, `|`, or a second line. A newline counts
  only inside a quoted word (a multi-line commit message).
- NO redirection of any kind (`>`, `>>`, `<`, `2>&1`, `&>`, `{v}>`), no
  heredoc, no here-string, no line continuation, no comment, no subshell
  `( )`, group `{ }` or command with only a redirection.
- bash words: unquoted letters, digits and `_ - . / : = + , @ % ^`, a `~`
  that is not at the start (`HEAD~3`), git's `@{...}` (`@{u}`, `HEAD@{1}`) with
  no `,` or `..` inside; whole `'...'` runs; `"..."` runs with no `$` or
  backtick; a backslash escaping one character.
- PowerShell words: unquoted letters, digits and `_ - . / : = + \ ^ % ~ @` (no
  leading `~`, `@` only inside a word); a whole `'...'` or `"..."` word (a
  double-quoted one holding no `$`); a backtick only before one of
  `- . / : = _ +` (never before a letter or digit, `` `u{2d} `` is a `-`, and
  never before `*`, `?` or `[`, which PowerShell still expands as a wildcard
  for a native command's arguments); an unquoted first word.

Anything else is "cannot tell", and cannot tell is never exempt: the guards
judge that line exactly as they did before the switch. That includes `$` in
any form (`"$OPT"`, `${X:-...}`, `$'...'`, `$"..."`, `$env:X`, `$(...)`), a
backtick substitution, a glob (`*`, `?`, `[`), a brace expansion, a leading
`~`, a PowerShell `(expr)`, `@(...)`, `@splat`, `{ }` or `[type]`, `--%`, a
`%NAME%` (or two `%` in a line with text between them, even across words), a curly quote, and every chain such as `git add -A && git commit -m
x`. Six review rounds each found a new shape of redirect, heredoc,
continuation or expansion for a reader that tried to follow them (a command
made only of redirects such as `> $((_))`, a heredoc delimiter ending in a
backslash, a continuation splitting `2>&1`, a backtick before `*`); the reader
now follows none of them, so a form nobody has thought of yet is judged, not
exempt. The convenience cost is that a chain, a redirect or a heredoc commit
message is judged as before (run the commands as separate calls, and pass a
message with `-m '...'`). A differential test
(`tests/test_git_allow_differential.py`) runs every line of a generated
corpus that the allowlist accepts under real bash and PowerShell 7 with a
shim `git` that logs its argv, and fails when git is handed anything other
than the argv crew read.

Never exempt even when every word is plain: a git command that hands git
config or a command of its own - a global `-c` (an alias `!cmd`,
`core.sshCommand`, `core.pager`), `--config-env` or `--exec-path`; an option or
subcommand that runs a command it is given (`rebase --exec`/`-x`,
`submodule foreach`, `bisect run`, `push`/`send-pack --receive-pack`/`--exec`,
`fetch-pack --upload-pack`/`--exec`, `fetch`/`pull`/`clone`/`ls-remote
--upload-pack`, `clone -u`/`-c`/`--template`, `init`/`init-db --template`, `grep -O`,
`difftool --extcmd`, `filter-branch`, `instaweb`, `for-each-repo`,
`web--browse`, `merge-index` (it runs the program it is handed, once per unmerged path), `send-email --*-cmd`, `daemon --access-hook`), in any abbreviation git accepts (`--exe`,
`--receive=...`); an option that launches a helper program (`--paginate` and a leading `-p`, `--ext-diff`,
`--textconv`, `--help`, `--open-files-in-pager`), `git help`, `git difftool`, `git mergetool`,
`git bisect visualize`/`view` (gitk), `git maintenance start`/`stop` (the scheduler program)
and `git credential` and `git cat-file --filters` (each runs a configured program), a remote-helper URL wherever it sits (`ext::<command>`, `fd::3`, `foo::bar`, which runs `git-remote-foo` from PATH; also after `--` and behind `--opt=`), a URL of any scheme but `file`, `git`, `ssh`, `git+ssh`, `ssh+git`, `http` and `https` (`zzz://host/x` runs `git-remote-zzz` from PATH), and `merge`/`pull`/`rebase` `-s`/`--strategy` and `cherry-pick`/`revert --strategy`
(git runs `git-merge-<strategy>` from PATH; `-X`/`--strategy-option` only passes a string and is not held);
and a `git config` that is not plainly a read (`--get*`,
`-l`/`--list`, `get`, `list`, or one key alone, with only read options): a
write may set `alias.*` or a program-valued key (`core.sshCommand`,
`core.pager`, `core.editor`, `core.fsmonitor`, `core.hooksPath`,
`diff.external`, `credential.helper`, `sequence.editor`, `gpg.program`, ...)
that a later git command on the same line runs. A git command aimed at another
repository (`git -C <dir>`) passes only when that repository's own file does
not veto it either, and a git command with no `-C` runs in the directory the hook
reports as its cwd (the promote gate: the project directory), so that repository's
file is read too: a veto there, or a cwd that is not a git work tree crew can read,
reads as off; one whose repository crew cannot tell (`--git-dir`,
`--work-tree`, or a `-C ..` that follows a link, which git and Windows read
differently) is judged as before. A subcommand is matched exactly as written:
`git STATUS` is not `status`. A word after `git` that is not one of git's own built-ins
(`git zzz`, `git svn`, `git p4`, `git gui`, `git citool`, an alias such as `git co`) is held too:
git runs an alias, or a `git-<word>` program it finds on PATH. A built-in this version of crew
does not list is only held, never let through. A `deploy` in `.crew/verify.json` that is not a
command or a list of commands (or an environment that is not an object) makes the promote gate
exempt nothing, the same map the gate itself refuses to read. A map or config that repeats a key, or holds two keys that differ only by case, is refused rather than read last-wins (`.crew/verify.json` for the promote exemption and the dispatch reader, the config files for `guards.git.allow`, the `cloud`/`environments` blocks and the saved-plan summary): the promote exemption then exempts nothing and the config reads as off. The value of a value-taking global option is not an option (`git -C -p status` runs in a directory named `-p`, `git -C -c status` in one named `-c`), and a `~` inside a `-C` value (`foo~bar`, `PROGRA~1`) is a name. An unquoted word that starts with `~` expands and exempts nothing; a QUOTED one (`git -C '~repo' status`) is a literal directory name and is read as one. A push option's value (`git push -o --receive-pack=x origin main`, `-o ext::echo`, `--push-option <v>`, `-ofoo`) is a string the remote reads, not an option or a URL, so it is not held. A declared deploy that reads as git only once its backslashes, quotes or backticks are dropped (`g\it push prod main`) exempts nothing: crew does not compare the two spellings, it fails closed. That holds whether or not the raw text already matches `git` (round 15: `"git" push prod main`, `$'git' push prod main`, `${x}it push prod main`, `$(echo git) push prod main` and `g$@it push prod main` all exempt nothing), and a declared deploy whose command word (past `NAME=value` words and `sudo`/`env`-style wrappers) holds a `$` or backtick exempts nothing either; a plain declared `git push prod main` exempts what it does not contain, as before. When the hook's own environment sets `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`, `GIT_OBJECT_DIRECTORY`, `GIT_INDEX_FILE` or `GIT_NAMESPACE` to a non-empty value, a plain `git` the hook runs would act on the repository those name, not the working directory's, so crew cannot tell whose veto applies and reads `guards.git.allow` as off for that line (an env prefix on the line itself was already refused). A built-in that only newer gits have (`backfill`, `diff-pairs`, `format-rev`, `history`, `last-modified`, `replay`, `repo`, `survey`, `url-parse`) is held unless the installed git lists it in `git --list-cmds=builtins` (an older git runs a `git-<name>` from PATH instead); `git submodule` is a script in git's own exec directory, which git searches before PATH, so it is not held.

Accepted residuals: a literal `git` is read as the git program, so a shell function named `git`
that the shell inherited or exported (`export -f git`) would run instead of it, and crew cannot see
that from the command line (verified: with `git() { echo hijacked; }` exported, `git status` in a
child bash prints `hijacked`).

What stays exempt, for example: `git commit -m "fix: x"`, `git push
--force-with-lease origin topic`, `git push -f origin topic`, `git rebase -i
HEAD~3`, `git -C <path> status`, `git log --format=%H`, `git log @{u}..HEAD`
and `git config user.name`. What no longer is: `git commit -m "$(...)"` (a
substitution), a line with anything but one git command on it (`git push -f &&
rm x`, `git add -A && git commit`, `FOO=1 git push`, `git status 2>&1`, `git
commit -F - <<'EOF' ... EOF`), `/usr/bin/git ...`, and `git config <key>
<value>`.

Who can turn it on: the machine file only, and only through the double
confirmation. `crew_confirm_config.py propose --layer machine --key
guards.git.allow --value '"all"'` (or `'["commit","push"]'`) records the change
and prints an id; you type `/crew:confirm-config <change_id>` twice, in two
prompts, within 15 minutes. A value counts only while the newest settled
receipt for that file is a whole double confirmation (two confirmations from
two distinct prompts you typed, inside the proposal's window, for that file)
of exactly that value, AND the machine file is still the file that
confirmation left: the same bytes, size, modification time and change time
(the metadata-change time: POSIX `ctime`, NTFS ChangeTime on Windows). crew's own
config writer (`crew_config.py --set`, `/crew:config`, a confirmed `humanOnly`
change) carries the receipt over when it changes another key. Any other change
to the machine file turns the switch off until you confirm it again: a hand
edit, an agent's Edit, a restore from backup, even setting `"off"` by hand and
then the same `"all"` back, or putting a copy of the confirmed file back with
`cp -p` (bytes and modification time restored; the change time still moves).
One gap, on Windows only: a copy made AND put back with a Windows file copy
(`Copy-Item`, Explorer, `shutil.copy2`) carries the change time over with the
bytes, so crew cannot tell it from the confirmed file. `crew_config.py --set` and `/crew:config` refuse
every value but `"off"` and null, and a crew write back to `"off"` revokes the
receipt. A repo file can never turn it on; a repo `"off"`, a malformed repo
value, or a repo `.crew/config.json` crew cannot read or parse (a link that
does not resolve, or a `.crew` that is a file, included) vetoes it.
Anything crew cannot read - a value outside the table, a store it cannot read,
a line it cannot read whole - is off.

What a receipt cannot prove: the store (`~/.claude/crew/confirm-config/`) is
plain files. It is protected from an agent's writes ONLY while `scope.mode` is
on: then the scope guard refuses a Write/Edit into it, and a shell command
naming it beside a writing word. With `scope.mode` off nothing stops an agent
writing a receipt, and even with it on a process that runs arbitrary code as
you can write a whole, well-formed record. And `"all"` does not stop what git
runs from its own persistent configuration: hooks (`.git/hooks/`,
`core.hooksPath`), aliases (`alias.*` set in a config file earlier, by an
earlier command line), and `core.sshCommand`, `core.pager`, `core.editor`,
filters and the like all run under `"all"` exactly as they would with crew
absent. That includes the editor git opens for `commit`, `rebase -i`, `tag -a`,
`notes edit` and `replace --edit` (from `core.editor`, `GIT_EDITOR` or `$EDITOR`):
those subcommands are not held, so a program set in config or the environment
runs when they do (inferred from git's documented behaviour, not measured here). crew reads only the command line, never git's config files or hooks.

`python3 hooks/scripts/crew_gitallow.py --root .` prints what is in force.
Each pass is logged to `.crew/guard.log` with the policy `gitAllow:<value>`.

## The owner-typed run approval (`approvals.run`, crew 1.3.161)

A few commands are the owner's alone. Until crew 1.3.161 the only way to run
one was a person at a terminal. With this route on, an agent can ASK and only
the owner can answer: the refused command becomes a request, you type
`/crew:allow-run <id>` in your own prompt, and the agent re-runs the exact
command once with ` --receipt <id>`. First class, and the only one in this
version: `verify-trust` (`verify_trust.py approve`, and `revoke`,
`allow-owner`, `disallow-owner` when you open them).

**The keys are read from the machine file only, and are off by default.**
`crew_runapproval.settings` reads `~/.claude/crew/config.json` and nothing
else: a repo file cannot turn the route on, a file with a duplicate key or a
value of the wrong type is off, and a home directory inside the project is not
the machine's. This version is the harness half only: the keys are not in the
key registry, and the `/crew:allow-run` command file is not shipped yet (both
are the next change, which may not ride with a harness change). So today you
set the keys by hand in that file, `/crew:config` does not list them, a crew
tool that lists unknown keys may name them (not checked for every tool), and
whether Claude Code passes a slash command that has no command file to the
prompt hook was not measured: treat the route as not usable from a prompt
until the command file lands.

| Key | Default | Values | What it does |
|---|---|---|---|
| `approvals.run.classes` | `[]` (off) | list holding `"verify-trust"` | Which command classes may use the route. Empty or absent: no request is recorded, `/crew:allow-run` gives no receipt, `--receipt` spends nothing, and every refusal reads as before. A name this version does not know is ignored. |
| `approvals.run.ttlSeconds` | `900` | integer 60 to 3600 | How long a receipt lasts after you type the id. One use whatever the value. Out of range reads as 900. |
| `approvals.run.verbs.verifyTrust` | `["approve"]` | subset of `approve`, `revoke`, `allow-owner`, `disallow-owner` | Which trust verbs may be requested. `allow-owner` trusts every repo of an owner, so it is not in the default. An unknown verb in the list reads as the default. |

**What a receipt is bound to.** The exact command text (its sha256), the
class, what the command does (the verb, the real `--root` or the owner, each
`--under`), the worktree the session stands in, and the session that raised
the request. For `approve` it also pins the digest of what the gate would run
(the `.crew/verify.json` bytes): read when the request is raised, when you
type the id and when the receipt is spent, so a map edited after you were
asked ends the approval. A request waits 15 minutes; an unanswered one is a
"no". A receipt is spent by its first use, matching or not, and a retry needs
a new answer. Each request, receipt and use writes one line to
`~/.claude/crew/run-approvals/audit.log`.

**Only the plain form can be requested.** One line, every word a plain
literal, this plugin's own script:
`python3 <plugin>/hooks/scripts/verify_trust.py approve [--root DIR]` (and
the other verbs with their own arguments). A command with a quote, a variable,
a substitution, a redirect, a pipe, `&&`, `;`, `--yes`, a line break anywhere
(its end included), or a copy of the script is refused as before and gets no
request id.

**The id is the one you type.** `/crew:allow-run` with no id, a mistyped id or
two ids gives no receipt and lists the requests waiting in this session; even
with exactly one waiting it never picks it, because a request is recorded on
an agent's command. It is answered only in the session whose command was
refused, so a prompt submitted in another session (a plain child
`claude -p "/crew:allow-run <id>"` started by the agent) gets nothing. A
child that resumes this session is NOT another session: measured on Claude
Code 2.1.326 (Windows), the prompt hook of `claude -p --resume <sid>`, prompt
as an argument or on stdin, is handed `<sid>` itself, also while another
process was mid-turn on the same session. The session binding does not stop
that child; only the guard's refusals below stand in front of it.

**What stops a session answering for you, and what does not.** Only while
a class is on: with `approvals.run.classes` empty or absent (the default) the
scope guard judges none of this and refuses nothing new, because no receipt
is honoured then. With a class on, in every `scope.mode`, `off` included, it
refuses a Write/Edit under `~/.claude/crew/run-approvals/`, a shell command
that names that store and is not a plain read, a command carrying
`/crew:allow-run` with an id or a variable after it, code run beside
`crew_runapproval`, a command naming the prompt hook or the hook launcher,
and one starting Claude on an existing session (`--resume`, `-r`,
`--continue`, `-c`, `--session-id`, `--fork-session`, or arguments held in a
variable). `verify_trust.py --receipt` spends the receipt itself, so getting
past the guard alone changes nothing.

**Globs and variables beside the store (class on only).** The store's name
need not be spelled for a shell to reach it, so the guard also refuses a
command that is not a plain read and holds a word a shell could expand to the
store: a glob (`*`, `?`, `[...]`, a brace list) or an unexpanded variable or
substitution standing where the name goes, together with one thing that puts
it at the store. That is four or more of the name's own characters (`run-*`,
`run-appro[v]als`, `run-approva?s`, `${d}-approvals`), a store child after it
(`$X/receipts/a.json`), `.claude/crew` before it (`~/.claude/crew/*`, or a
relative glob run from that directory), or `.claude/crew` named anywhere else
in the command. Unknown is read as the store, so with a class on this
over-refuses near it: `rm -rf run-*` in any directory, and a command that
names `~/.claude/crew` and also holds a variable. Run those yourself. A glob
or a variable nowhere near the store (`rm -f *.pyc`, `git add
plugin/crew/*`, `cp $SRC $DST`) is not touched. If the store check itself
fails while a class is on, the call is refused in every `scope.mode`; only a
plain read still passes.

These are tripwires against drift, not a sandbox: the store and the hook
payload are a file and a process of the same OS user, so a session that sets
out to forge a receipt by a route the guard cannot read (a whole path held in
a variable set by an earlier command, an encoded or concatenated string, a
script file it wrote, Claude resumed through a launcher the guard does not
know, keys typed into your own terminal) is not stopped here. Nor is a
receipt file written by hand while the class was off: it must name the
session, the worktree and the command, and it lasts an hour at most, but its
writer picks the hour. So delete `~/.claude/crew/run-approvals/` just before
you turn a class on (keep `audit.log` if you want the history). Not measured:
a resume against an interactive (not `-p`) session, and a receipt minted end
to end by a resumed child. Keep the class off on a machine where that matters
more than the convenience.

## Guard profiles

`guards.profile` is one word for all twelve guards; `guards.overrides.<guard>`
replaces the profile's value for one guard. Each layer expands to a value per
guard, and the per-guard ratchet then takes the narrower layer. A malformed
profile or override reads as the guard's floor (`block`, or `none` for the
production guards), never as `off`. The per-guard keys of earlier versions
(`guards.<guard>`) are still READ as aliases for `guards.overrides.<guard>`
until `/crew:migrate` rewrites them, and are never written. For `envGuard` an
explicit `null` (`"guards": {"envGuard": null}`) is malformed and reads as `block`; only an
absent key is `off`. The other guards still read a legacy `null` as absent.

| Guard | `off` | `standard` | `strict` |
|---|---|---|---|
| `terraformApply` | `block` | `block` | `block` |
| `forcePush` | `block` | `block` | `block` |
| `adminMerge` | `block` | `ask` | `block` |
| `mergeGate` | `block` | `block` | `block` |
| `cloudDestructive` | `block` | `block` | `block` |
| `sqlDestructive` | `block` | `block` | `block` |
| `deployWorkflow` | `block` | `block` | `block` |
| `prodDatabase` | `none` | `none` | `none` |
| `prodServer` | `none` | `none` | `none` |
| `roleWrites` | `off` | `report` | `block` |
| `cloudGuard` | `off` | `block` | `block` |
| `envGuard` | `off` | `off` | `block` |

## Verify gate trust (a store, not a config key)

The Stop gate runs `.crew/verify.json` `run` strings (and, with no verify.json,
`_verify/smoke.sh` or `scripts/smoke.sh`) only for a repo this machine trusts.
Trust lives in `${CLAUDE_CONFIG_DIR:-~/.claude}/crew/verify-trust.json`, written
by `python3 plugin/crew/hooks/scripts/verify_trust.py` (`approve`, `revoke`,
`status`, `allow-owner`, `disallow-owner`) at a terminal, or by an agent with your typed `/crew:allow-run <id>` receipt (`--receipt`, above; off by default). It is not a config key:
no repo file can widen it. When the gate reaches its trust decision for a repo it does not trust, it prints `UNTRUSTED, not run`, runs
nothing and records no pass. A turn can end before that decision, and then no repo rule ran either way and no
UNTRUSTED line is printed: the default Stop with no changed files (`nothing changed since the last verified
commit`), a fingerprint that matches the last clean run, a Stop hook that is already active, `"verifyGate": false`
and a fresh lock each exit 0 first. Do not read a quiet Stop as proof the repo is trusted. `--ci` is exempt by design: it never calls the trust check at all (a CI job's checkout is its own pipeline's trust and has no home store), so it runs the repo's rules whether or not the trust helper is present or working, and says `trust check exempt` first. A store location a repo can author is
refused as UNKNOWN: a project's `.claude/settings.json` `env` block reaches hook processes
(measured 2026-10-25, claude 2.1.304), so `CREW_VERIFY_TRUST_FILE`, `CLAUDE_CONFIG_DIR` and
`HOME` must name an absolute path outside the repo being checked.

Accepted residuals: `--price` opens its map, and `bash` reopens the smoke script, after the trust
check, so a process running as you that swaps the file in that interval runs the swapped bytes (you can
edit the store too). The scope guard is a textual tripwire, not a sandbox: the boundary is the OS user.

Round 8 (crew 1.3.89): before the trust decision the gate runs only a proved interpreter found on a PATH
stripped of repo entries, with `CREW_PYTHON` and every `PYTHON*` variable ignored and the script run as
`python -E -s`; it never executes a python it found inside the repo, even to probe it, and where none
qualifies the fingerprint, scope and record helpers are skipped and `--price` says there is no python. A
submodule is judged like a linked worktree, so a hash-approved submodule runs. A store lock is not broken
while the holder named in it still runs on this host, however old it is. Two more accepted residuals, both
pre-existing: the Stop launcher (`crew-hook.sh`, `hooks.json`) takes the first `python3` on the PATH it
is started with, and `BASH_ENV` is sourced by bash before the launcher can scrub it; both run before any gate
code and are properties of how the hook is started.

Round 9 (crew 1.3.89): the gate sweeps its inherited shell functions (`BASH_FUNC_git%%`, `BASH_FUNC_dirname%%`; the sweep's boundary is stated under round 10) and removes every inherited `GATE_*` variable before anything else is called, and sets its once-per-run cache variables itself, so a repo's settings `env` block cannot pre-seed the interpreter the trust decision uses. The proving probe runs with the user site off (`PYTHONNOUSERSITE=1`), so a user-site customization module under a repo-set `HOME` cannot run in it. A trust check that cannot run (status 14) exits 2 at once, before any interpreter lookup that `CREW_PYTHON` could point into the repo. A store inside a submodule's superproject is refused, and owner trust is refused for a `.git` file whose gitdir does not name its directory back (a hand-written `gitdir:` line borrowing a trusted repo's remotes; round 10 applies the same test to a hash approval). The store lock is published with its holder note already inside (one atomic rename), and a holder note with an absurd pid is ignored instead of raising. Accepted residuals, not changed here: a lock whose note names another host is judged by age alone; a symlinked python inside an allowed absolute PATH dir is not resolved (INFERRED by the reviewer, not run); a symlinked store path is not resolved for the scope guard's Write/Edit targets (INFERRED, not run).

Round 10 (crew 1.3.89), the boundary. The gate defends against what a hostile repository supplies as FILES: its verify.json and smoke script, a `.git` file, repo config (including `core.fsmonitor`), a trust-store file, repo-local python and tools, and `.crew/*`. It does not, and cannot, defend against code that already controls the environment the gate is launched in: a project settings `env` block that sets `PATH`, `BASH_ENV`, `HOME`, `LD_PRELOAD`, `LD_LIBRARY_PATH` or an exported function runs repo code before any line of the script executes. Those are documented residuals, listed exactly below. Fixed (a file the repo supplies, or cheap): a hash approval is judged under a repository identity only when the `.git` file names this directory back (round 11 replaces that test with a confirmation from the other side), so a hand-written `gitdir:` line no longer borrows an approved repo's bytes approval (verified; a real linked worktree and a real submodule still share theirs); before the trust decision the gate's own commands (git, grep, tr, sed, wc, cut, head, date) are found on the user's PATH minus every relative entry and every directory inside the repo, and the user's PATH is put back once the repo is trusted, so rules run as before; the trust check and `--price` call no external `dirname`, `basename`, `uname` (fixed PATH) or `tr`; the emergency-lane check asks the proved interpreter on that PATH, never `CREW_PYTHON` (verified: a repo python ran from it); every git call before the decision runs with `core.fsmonitor` off (verified: the command named in `.git/config` ran from `git diff` and `git ls-files`); an inherited `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` or `GIT_COMMON_DIR` is removed so the changed-file scan cannot be pointed at a clean repository; the scope guard refuses a `python -m` module word that a shell will expand (an assembled name, a variable, a backtick or a wildcard) when a trust verb follows, and reads the value of `env -u NAME` as a value rather than as the command. Residuals, not fixed, each stated for what it is: (1) the function sweep's own two command words, `compgen` and `unset`, are looked up as functions before the sweep can remove anything, so an exported `BASH_FUNC_compgen%%` or `BASH_FUNC_unset%%` runs repo code first (verified); no script can avoid this, because every command word, `builtin` and `command` included, is itself looked up as a function; every other name the gate calls is swept first (the tests export 43 of them, and `builtin`, `command` and `declare`); (2) `BASH_ENV` is sourced before line 1, and `LD_PRELOAD`, `LD_LIBRARY_PATH` and `DYLD_*` load into bash itself (the trust check's python runs with them removed, the shell does not); (3) an absolute PATH entry outside the repo that an attacker controls, a symlinked python inside an allowed PATH directory, and the first `python3` the Stop launcher (`crew-hook.sh`, `hooks.json`) finds on the PATH it was started with; (4) a symlinked store path is not resolved for the scope guard's Write/Edit targets; (5) `"verifyGate": false` in the repo's `.crew/config.json` (matched with grep, not parsed as JSON, so a nested key counts) and a fresh `.crew/.verify-gate.lock` with no owner file each stand the gate down with exit 0 before the trust check: nothing runs, and the lock case says `NOTHING WAS VERIFIED this turn` (both verified), so a repo can switch its own gate off but cannot make it run; (6) a lock note naming another host is judged by age alone (a missing, empty or foreign-host note older than 30 s is broken), as before.

Round 11 (crew 1.3.89), the repository identity. Round 10 closed only the literal hand-written `gitdir:` line: a hostile directory could still write its OWN git layout and make git report an approved repo's identity (verified for five layouts: a `.git` directory, or a `.git` symlink, or a gitfile to an admin directory the directory wrote, each with a `commondir` naming the approved repo, plus the `core.worktree` and config variants). The identity is now accepted only when the directory cannot have written the record that confirms it: (1) a plain repository, whose `.git` is a real directory, never a symlink, junction or other reparse point, and is git's own git directory; (2) a linked worktree, where the main repository's own `worktrees/<name>/gitdir` record names this directory's `.git` and the gitfile names that admin directory; (3) a submodule, whose git directory sits under a `.git/modules/` tree, names this directory as `core.worktree` and has no `commondir`. Anything else is judged by its own path alone, like a directory that is not a git repository, so approving it by hash covers it alone. Paths are compared as the same filesystem object, so case, trailing slash, `..` and dot segments cannot make a forged path match. The gate checks the identity again right before it runs the rules (the second trust check); the interval between that check and the command starting is the accepted same-user residual above.

Round 12 (crew 1.3.92), hardlinks and a reused path. (1) A hardlink counted as the recorded file: `samefile` compares inodes, so `ln <worktree>/.git <other>/.git` (same filesystem, same user; a hardlink cannot cross filesystems, so it needs local access to the machine) made an unrelated directory with its own verify map report an approved repository's identity and, with that repository's remote owner allowlisted, print `trusted by remote owner` (verified). A gitfile, the worktree admin directory's `gitdir` record and its `commondir` file must now each be a regular file with exactly one name (link count 1), so a hardlinked copy is refused and a genuine worktree, whose files have one name, is not. (2) A removed worktree's path (verified): the main repository keeps `worktrees/<name>` after the directory is removed without `git worktree prune`, so another directory at that path, or a symlink put there, with a copy of the `.git` file, matched the inode test. The recorded `gitdir` path is now compared as a spelling too: it must equal this directory's own real path plus `/.git`, so a symlink alias, a moved or copied tree and a symlink put at the old path are refused (on Windows the recorded path's real path is also accepted, for a spelling difference such as an 8.3 short name, and only when neither the recorded path nor any directory above it is a symlink, junction or other reparse point; round 13). Residual, documented and not closed: a NEW real directory created at exactly the removed worktree's path, with a copied `.git` file, cannot be told from the original by a path and an inode alone, and `git worktree list` does not mark it prunable (its gitfile exists), so it needs state the gate does not keep; this is the same-user, stale-record case. Run `git worktree prune` after removing a worktree directory, and remove the stale entry before allowlisting an owner. (3) INFERRED, not reproduced: a submodule checkout replaced at the path named by a surviving `core.worktree`, or a plain repository replaced at the same path, cannot be told apart from the original by a path key, and the check and the run open the path separately, so a window exists between them; the same-user part is the accepted residual above. (4) A plain repository carries its own `.git/config`, and remote-owner trust reads that file (verified): a repository whose config names an allowlisted remote is owner-trusted, which is how owner trust works, and an archive (zip, tarball) can ship a `.git/` directory with such a config. Use `allow-owner HOST/OWNER --under <dir>` so only repositories you cloned below one directory are trusted by owner, and approve an unpacked archive by hash after reading its verify map, never by owner.

Round 13 (crew 1.3.94), Windows junctions. INFERRED by the reviewer, not reproduced here (no Windows host; the cases mock the `lstat` attribute word and run on Linux): on Windows `.git` can be an NTFS junction to an approved repository's `.git` directory, which `os.path.islink` does not report and which every inode comparison follows, so a directory whose `.git` was a junction passed the plain-repository test. The test is now whether the path is a reparse point at all: a symlink, `os.path.isjunction` where Python has it (3.12 and later), or `FILE_ATTRIBUTE_REPARSE_POINT` in the `lstat` attributes. It is applied to `.git` (directory or gitfile), the linked worktree's admin directory, its `gitdir` record and its `commondir`; any of them being a reparse point makes the directory judged by its own path alone. The Windows real-path fallback of round 12 is accepted only when no component of the recorded path is a reparse point, so a symlink or junction left at a removed worktree's old path no longer satisfies it. Only the paths above are tested, not every parent of the directory: a plain repository reached through a junctioned parent directory stays trusted (its identity does not run through its parents), and a linked worktree is refused only when its recorded path runs through a reparse point and so differs from its real path (it fails closed and needs its own `approve`). Residual, unchanged: a process that controls the launch environment is out of scope (round 10).

## Migrating and removed keys

`/crew:migrate` upgrades a repo file; `python3 plugin/crew/hooks/scripts/crew_migrate.py --global`
does the same for the machine file (preview, apply and rollback). It rewrites
`guards.*` into the profile with the fewest overrides and removes removed keys
that hold their default. A removed key holding another value stops the migration
until it is deleted or accepted with `--accept-dropped <key>`. 60 keys were
removed (ticket L-0725) and are now constants in `crew_state`
(`crew_dropped.DROPPED` lists each with its constant); a config still carrying
one is reported as having no effect (`crew_config.py --inert`, `/crew:status`, and the
SessionStart notice).

## Counts by family

| Family | Keys |
|---|---|
| `core` | 27 |
| `providers` | 18 |
| `guards` | 3 |
| `cloud` | 14 |
| `trackers` | 5 |
| `autopilot` | 15 |
| `context` | 11 |
| `notify` | 4 |
| `memory` | 2 |
| `platform` | 4 |

## `core` keys (27)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `schema` | repo | `8` | not validated - read by `hooks/scripts/crew_state.py` (expects integer) | Config schema version; `/crew:migrate` upgrades an older one. |
| `verifyGate` | repo | `true` | not validated - read by `hooks/scripts/verify-gate.sh` (expects boolean) | Run the Stop verify gate. |
| `humanOnly.approve` | human-only opt-out | `null` | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_humanonly.py`) | The owner's opt-out of `/crew:approve` being human-only. null or `true` keeps it human-only; `false` opts out only from the machine file or an untracked repo file, only after `/crew:confirm-config` twice, and a `true` in either layer vetoes. crew 1.3.27: with an opt-out in force a cli-recorded approval counts (`crew_ticket.cli_approval_allowed`). |
| `humanOnly.promoteMarker` | human-only opt-out | `null` | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_humanonly.py`) | The same opt-out for the production promote marker `.crew/.approved-<env>-<sha>`, under the same rules. crew 1.3.9: no hook acts on it yet, and no hook today checks who created the marker. |
| `worktrees.root` | both | `null` | absolute path or null (coerced in `hooks/scripts/crew_worktrees.py`) | The base directory for this repo's git worktrees, OUTSIDE the repo: they go in `<root>/<repo>-<digest>/<name>`. null is `~/.claude/crew/worktrees`; `~` is expanded, a relative path or one inside the repo is refused (never replaced by the default). It places the worktrees crew places (`/crew:emergency`, `crew_worktrees.py path`) and, once the owner registers the opt-in `WorktreeCreate` hook, the ones Claude Code creates; without the hook Claude Code keeps using `.claude/worktrees/`. |
| `promote.deadlineSeconds` | both | `null` | number of seconds, or null (coerced in `hooks/scripts/_promote_gate.py`) | How many seconds the promote gate (`promote-gate.sh`) may run, counted from the moment its shell began, before it gives up and blocks (a hook that times out is not a block, so the gate stops itself first). null derives it from the guard's hook timeout less a 4 s margin: 16 s of the 20 s row. A number above the timeout less 2 s (18 s of 20) is clamped to that, so the setting can never let the gate outlive its hook; zero, a negative, a string or a boolean reads as null. The hook timeout is the guard's row in the dispatcher's table, not a setting. |
| `verify.stopBudgetSeconds` | repo | `60` | whole number of seconds, 1 to 540, or null (coerced in `hooks/scripts/verify-gate.sh`) | How many seconds the Stop row of the verify gate (`verify-gate.sh`) may spend running rules, cheapest first, before it defers the rest to CI and names them. Default 60, which is what the gate used before the key was settable. A write must be a whole number from 1 to 540 (the Stop hook's timeout less the gate's 60 s margin); anything else is refused, never stored as a value the gate would quietly replace with 60. null removes the setting. Repo file only: what a rule costs is a fact about the checkout. `--all` and `--ci` ignore it. A hand-edited string, boolean or negative reads as 60, never as no limit (a number the writer would refuse, such as 0 or 1e9, is still taken as written). |
| `reaper.enabled` | both | `false` | boolean (coerced in `hooks/scripts/crew_reaper.py`) | Whether scheduled and session-start passes of the orphan reaper (`crew_reaper.py --scheduled`) do anything. false by default; a manual `crew_reaper.py` run always works and is a dry run unless given `--apply`. Read from the machine file only: a repo value is ignored, because the reaper ends processes on this machine. |
| `reaper.dryRun` | both | `true` | boolean (coerced in `hooks/scripts/crew_reaper.py`) | When true (the default) a scheduled or session-start pass only logs what it would end to `~/.claude/crew/reaper.log`; set false to let it end processes. Only a scheduled pass reads it; a manual run ends processes only with `--apply`. |
| `reaper.spinCpuPct` | both | `50` | percent of one core (coerced in `hooks/scripts/crew_reaper.py`) | An orphan is SPINNING when it used at least this percentage of one core over the reaper's short sample (5 s) and is older than `spinMinAgeMin`. A number above 0; anything else reads as 50. |
| `reaper.spinMinAgeMin` | both | `15` | number of minutes (coerced in `hooks/scripts/crew_reaper.py`) | Minutes an orphan must be running before the spinning rule (and the self-matching `until pgrep -f` watcher rule) may end it. A number above 0; anything else reads as 15. |
| `reaper.blockedMinAgeHours` | both | `2` | number of hours (coerced in `hooks/scripts/crew_reaper.py`) | Hours an orphan using under 1% of a core must be running before it counts as BLOCKED and may be ended. A number above 0; anything else reads as 2. |
| `reaper.protectedRegex` | both | `null` | regular expression, or null (coerced in `hooks/scripts/crew_reaper.py`) | A regular expression; a process whose image name or command line matches is never ended, it REPLACES the built-in list (claude, node, MCP servers, ai-connect, psmux/tmux, tailscale, language servers, obsidian, perplexity, vscode, wsl/docker/vm, Defender, ssh). null keeps the built-in list; an invalid expression reads as null. |
| `reaper.intervalMin` | both | `10` | whole number of minutes (coerced in `hooks/scripts/crew_reaper.py`) | Minutes between runs of the scheduled task `crew_reaper.py --install-task` creates, and the least gap between two session-start passes. A whole number from 1; anything else reads as 10. The task is never installed by default. |
| `reaper.onSessionStart` | both | `false` | boolean (coerced in `hooks/scripts/crew_reaper.py`) | When true and `reaper.enabled` is true, the SessionStart context hook starts one detached reaper pass (at most one per `intervalMin`) and does not wait for it. false by default. |
| `emergency.standDown` | repo | `true` | not validated - read by `hooks/scripts/_common.sh` (expects boolean) | Whether a declared incident may stand gates down; `false` forbids it. |
| `emergency.maxTtlMinutes` | repo | `480` | integer (coerced in `hooks/scripts/crew_incident.py`) | Longest incident lifetime; never below `ttlMinutes`. |
| `pm.authority` | both, widening warned | `"report-only"` | `report-only` \| `act` \| `autonomous` | How much the PM may do unasked. A widening is warned about; the two layers combine by precedence. |
| `pm.maxDispatches` | both | `3` | integer (coerced in `hooks/scripts/crew_state.py`) | Roles the PM may dispatch in one pass. |
| `graph.out` | repo | `"graphify-out"` | not validated - read by `hooks/scripts/crew_state.py` (expects path) | Where the code graph is written. |
| `install.policy` | both, ratchet | `"manual"` | `manual` \| `ask` \| `auto` (ratchet: narrower layer wins; listed narrowest first) | Whether crew may install a missing prerequisite. |
| `change.requireForProduction` | both, ratchet | `false` | `true` \| `false` (ratchet: narrower layer wins; listed narrowest first) | Require an approved change request before `/crew:promote production`: a repo may turn it on, never off. |
| `git.forbiddenTrailers` | both | `[]` | list of trailer tokens (letters, digits and `-`, no `:`) (checked in `hooks/scripts/crew_trailers.py`) | Commit trailer tokens the owner forbids, reported by `/crew:done`. The two layers combine by union, so a repo can add a token and never remove the machine owner's; a value that is not a list of tokens makes the list unknown, never empty (docs/crew/config-rationale.md). |
| `scope.mode` | repo | `"off"` | `off` \| `report` \| `block` \| `auto` | Whether the scope guard enforces a ticket's Touch list; a value outside these fails closed to `block`. |
| `scope.allowCliApproval` | repo | `false` | `false` \| `true` (checked in `hooks/scripts/crew_ticket.py`) | Whether a CLI-written approval receipt counts; only exactly `true` allows it. `autopilot.approval: self` or `risk` needs it, and `autopilot.mode: plan` or `backlog`, to approve anything. A hand edit by the owner in the repo's `.crew/config.json` (`"scope": {"allowCliApproval": true}`); `crew_config.py --set` refuses it. |
| `tickets.baseBranch` | repo | `null` | branch name or null (checked in `hooks/scripts/scope_base.py`) | The branch ticket branches are cut from; null tries origin/HEAD's target, then origin/main, then main. A value that is not a branch name, or names no commit, makes the scope base could not tell. |
| `route.enabled` | both | `false` | `false` \| `true` (checked in `hooks/scripts/crew_route.py`) | Route plain-text prompts to `/crew:` commands; only the JSON value `true` arms it. |

## `providers` keys (18)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `qa.provider` | both | `"auto"` | `auto` \| `claude` \| `codex` \| `copilot` \| `kimi` | Who reviews: `auto` walks `qa.order`; a named provider is used as-is. |
| `qa.order` | both | `["codex", "kimi", "copilot", "claude"]` | list of: `claude` \| `codex` \| `copilot` \| `kimi` | The reviewers `auto` tries, in order. A list is one leaf, replaced wholesale. |
| `qa.fallback` | both | `"claude-sonnet-5"` | not validated - read by `commands/review.md` (expects model id) | Model a gone pin falls back to, on its family's provider (L-0712). |
| `qa.codex.model` | both | `"gpt-6.2-sol"` | not validated - read by `commands/review.md` (expects string or null) | Codex model for review; defaults to `gpt-6.2-sol` (1.3.166), null passes no flag. |
| `qa.codex.reasoningEffort` | both | `null` | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `commands/review.md`; not validated) | Codex reasoning effort for review; null passes no flag. |
| `qa.copilot.model` | both | `null` | not validated - read by `commands/review.md` (expects string or null) | Copilot model for review; null uses the CLI default. |
| `qa.kimi.model` | both | `null` | not validated - read by `commands/review.md` (expects string or null) | Kimi Code model id for review (`k3`, `kimi-for-coding`, ...); null uses the CLI's own default. |
| `qa.roles` | both | `{}` | object of role pins; each pin's provider is checked (checked in `hooks/scripts/crew_config.py`) | Per-role reviewer pins, `qa.roles.<role>.provider` / `.model`; a pin beats the provider block for that role. |
| `dev.provider` | both | `"claude"` | `claude` \| `codex` \| `copilot` \| `kimi` | Who implements. |
| `dev.fallback` | both | `"claude-sonnet-5"` | not validated - read by `skills/crew-providers/SKILL.md` (expects model id) | Model a gone dev pin falls back to, on its family's provider. |
| `dev.codex.model` | both | `null` | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | Codex model for implementation. |
| `dev.codex.reasoningEffort` | both | `null` | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `commands/review.md`; not validated) | Codex reasoning effort for implementation. |
| `dev.copilot.model` | both | `null` | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | Copilot model for implementation. |
| `dev.kimi.model` | both | `null` | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | Kimi Code model id for implementation, as `qa.kimi.model`. |
| `dev.roles` | both | `{}` | object of role pins; each pin's provider is checked (checked in `hooks/scripts/crew_config.py`) | Per-role dev pins, as `qa.roles`. |
| `secondOpinion.provider` | both | `"none"` | not validated - read by `commands/plan.md` (expects string) | Second-opinion provider for plans; `none` is off. |
| `secondOpinion.mode` | both | `"cli"` | not validated - read by `skills/crew-providers/SKILL.md` (expects string) | How the second opinion is reached. |
| `secondOpinion.model` | both | `null` | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | Second-opinion model. |

## `guards` keys (3)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `guards.profile` | both, ratchet | `"off"` | `off` \| `standard` \| `strict` | One word for the twelve guards: `off` (today's defaults), `standard` or `strict`. Expands per layer; each guard's ratchet then runs on the expanded values. |
| `guards.overrides` | both, ratchet | `{}` | object of guard name to tier (checked in `hooks/scripts/crew_guards.py`) | `guards.overrides.<guard>`: one guard's tier, replacing the profile's value for it. Each entry is checked against that guard's own tiers; a bad one reads as the floor. |
| `guards.git.allow` | both | `null` | null, `"off"`, `"all"` or a list of git subcommand names (coerced in `hooks/scripts/crew_gitallow.py`) | The owner's switch that stops crew's command guards blocking or asking on git commands: `"all"` lets a line of only plain git commands past the force-push rule and the promote gate (unless a declared deploy is itself a git command); a list of subcommands (`["commit", "push"]`) lets only those through, with every option they take (listing `push` lets `push --force` through). null or `"off"` changes nothing. Machine file only, and only after `/crew:confirm-config` twice (`crew_confirm_config.py propose --key guards.git.allow --value ...`); a value written any other way, or any later change to the machine file outside crew's config writer, reads as off, and a repo `"off"` or unreadable repo file vetoes it. FAIL-CLOSED ALLOWLIST: a line is exempt only when it is ONE command, exactly `git` with plain literal words (no `$`, backtick, glob, brace, leading `~`, parenthesis, PowerShell expression or `%NAME%`; no separator, redirection, heredoc, continuation or comment, so a chain is judged as before); a git command carrying `-c`, a command to run (`rebase --exec`, `push --receive-pack`, `submodule foreach`, ...) or a `git config` write is never exempt. |

## `cloud` keys (14)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `production.databases` | repo | `[]` | not validated - read by `hooks/scripts/crew_config.py` (expects list of globs) | Globs naming production databases. |
| `production.hosts` | repo | `[]` | not validated - read by `hooks/scripts/crew_config.py` (expects list of globs) | Globs naming production hosts. |
| `cloud.awsProfiles` | repo | `[]` | not validated - read by `hooks/scripts/cloud_guard.py` (expects list of names) | AWS profiles this repo may use. |
| `cloud.awsRegions` | repo | `[]` | not validated - read by `hooks/scripts/cloud_guard.py` (expects list of names) | AWS regions this repo may use. |
| `cloud.azureSubscriptions` | repo | `[]` | not validated - read by `hooks/scripts/cloud_guard.py` (expects list of names) | Azure subscriptions this repo may use. |
| `environments.nonProd` | repo | `[]` | not validated - read by `hooks/scripts/crew_config.py` (expects list of globs) | Terraform targets that are not production and may run unattended. |
| `environments.prodUnattended` | both, ratchet | `false` | `false` \| `true` (ratchet: narrower layer wins; listed narrowest first) | Whether production terraform may run unattended; `true` only when both layers say so. |
| `environments.workflows` | repo | `{}` | not validated - read by `hooks/scripts/crew_config.py` (expects object of glob to string) | Deploy workflow globs, each mapped to its environment or `input:<name>`. |
| `environments.preProduction` | repo | `{}` | not validated - read by `hooks/scripts/crew_preprod.py` (expects object of exact name to {reason, targets}) | Environments labelled production that are not live yet: exact name -> `reason` (+ optional exact `targets`); judged non-production by the cloud guard, with an audit line. |
| `tiers` | both, ratchet | `{}` | object of `<kind>:<name>` to {tier} (checked in `hooks/scripts/crew_tiers.py`) | Machine-owned tier per target (`<kind>:<name>` -> `{"tier": "dev"\|"qa"\|"prod"}`); dev < qa < prod < unknown, an unlisted target is `unknown`, and a repo entry may only narrow. Written whole (`--set tiers=<map>`). Read through `crew_tiers` only, never the merged value; report-only until R-01. |
| `unattendedCloud.aws.readOnly.profile` | machine-only | `null` | profile name, or null (coerced in `hooks/scripts/crew_unattended.py`) | The AWS profile an unattended run exports credentials from (`aws configure export-credentials`); it must yield temporary credentials. Machine file only. |
| `unattendedCloud.aws.readOnly.identity` | machine-only | `null` | ARN prefix ending in `/`, or null (coerced in `hooks/scripts/crew_unattended.py`) | The assumed-role ARN prefix STS must report for that profile, ending in `/`; null refuses every launch. Machine file only. |
| `unattendedCloud.aws.readOnly.region` | machine-only | `null` | region, or null (coerced in `hooks/scripts/crew_unattended.py`) | The AWS region the unattended run gets; null is `us-east-1`. Machine file only. |
| `unattendedCloud.aws.nonProd` | machine-only | `{}` | object: environment name -> {profile, identity, region?} (checked in `hooks/scripts/crew_unattended.py`) | Environment name -> `{profile, identity, region?}` (region optional, default `us-east-1`) for `launch --environment NAME`; usable only where the repo's `environments.nonProd` agrees. Machine file only. |

## `trackers` keys (5)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `tracker` | repo | `"files"` | `files` \| `obsidian` \| `jira` \| `sdp` | Where tickets live; `crew_tracker.resolve` answers `could not tell` when two configs disagree. |
| `jira.project` | repo | `null` | not validated - read by `commands/jira-sync.md` (expects string or null) | Jira project key. No consumer found (docs/crew/config-rationale.md). |
| `jira.cloudId` | repo | `null` | not validated - read by `commands/jira-sync.md` (expects string or null) | Jira cloud id, cached by `/crew:jira-sync`; read by nothing. |
| `obsidian.vaultPath` | repo | `null` | not validated - read by `hooks/scripts/crew_tracker.py` (expects path or null) | Vault holding the board; falls back to `memory.vaultPath` and must hold `.obsidian/`. |
| `obsidian.boardDir` | repo | `null` | not validated - read by `hooks/scripts/crew_tracker.py` (expects path or null) | Board folder inside the vault (relative, no `..`). |

## `autopilot` keys (15)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `autopilot.mode` | both, stricter wins | `"off"` | `off` \| `plan` \| `backlog` (checked in `hooks/scripts/crew_autopilot.py`); personal: listed strictest first, the stricter wins | Only the exact strings `plan` (one ticket per run) and `backlog` (L-0541: a goal's tickets in dependency order, inside the caps) arm `/crew:autopilot`; anything else reads as off, with a warning. |
| `autopilot.maxPhases` | both, stricter wins | `12` | positive integer (checked in `hooks/scripts/crew_autopilot.py`); personal: the smaller wins | Phases one run may take; anything but a positive integer reads as 12, with a warning. |
| `autopilot.deploy` | both, stricter wins | `"none"` | `none` \| `nonprod` \| `all`; personal: listed strictest first, the stricter wins | Where a deploy may run without asking; anything else reads as `none`. |
| `autopilot.approval` | both, stricter wins | `"risk"` | `human` \| `risk` \| `self`; personal: listed strictest first, the stricter wins | Who approves a ticket under autopilot; anything else reads as `human`. `risk` and `self` also need `autopilot.mode: plan` (or `backlog`) and `scope.allowCliApproval: true` (a hand edit of the repo's `.crew/config.json`); a refused `approve` lists each unmet one, with its value as written, the file that holds it and, under `risk`, the spec risk that blocks. |
| `autopilot.questions` | both, stricter wins | `"risk"` | `human` \| `risk` \| `self`; personal: listed strictest first, the stricter wins | Who answers a ticket's open questions under autopilot; anything else reads as `human`. |
| `autopilot.maxAutoReplans` | repo | `0` | non-negative integer (checked in `hooks/scripts/crew_autopilot.py`) | Successor plans autopilot may start by rejecting an out-of-rounds BLOCK review itself; 0 is off, and anything but a non-negative integer reads as 0, and above 5 as 5, with a warning. |
| `autopilot.ship` | repo | `"merge"` | `pr` \| `merge` | After `/crew:done`: `pr` pushes and opens the PR; `merge` also merges it (a merge commit) once the required checks allow. Anything else reads as `pr`, with a warning. |
| `autopilot.sleep.schedule` | repo | `null` | HH:MM-HH:MM or null (checked in `hooks/scripts/crew_sleep.py`) | A nightly window, `HH:MM-HH:MM` in machine local time (may cross midnight); inside it the two sleep overrides apply. Anything else is could not tell: only a stricter override applies. |
| `autopilot.sleep.approval` | repo | `null` | `null` \| `human` \| `self` \| `risk` (checked in `hooks/scripts/crew_sleep.py`) | `autopilot.approval` inside the sleep window; null keeps the day value; anything else counts as human, the strictest, with a warning. |
| `autopilot.sleep.questions` | repo | `null` | `null` \| `human` \| `self` \| `risk` (checked in `hooks/scripts/crew_sleep.py`) | `autopilot.questions` inside the sleep window; null keeps the day value; anything else counts as human, the strictest, with a warning. |
| `autopilot.sleep.deploy` | repo | `null` | `null` \| `nonprod` \| `none` (checked in `hooks/scripts/crew_sleep.py`) | `autopilot.deploy` inside the sleep window (L-0654): null keeps the day value, `nonprod` or `none` replaces it; anything else, `all` included, is refused with a warning. Asleep, an effective `all` reads as `nonprod`: production never runs unattended asleep. |
| `autopilot.maxTicketsPerRun` | repo | `3` | positive integer (checked in `hooks/scripts/crew_autopilot_backlog.py`) | Tickets one goal run (one session) may start; the next one stops the run. Anything but a positive integer reads as 3, with a warning. |
| `autopilot.maxTokensPerSession` | repo | `2000000` | positive integer (checked in `hooks/scripts/crew_autopilot_backlog.py`) | Input plus output tokens one goal session may spend, each assistant message counted once, before the run stops; a transcript that cannot be read stops too. Anything but a positive integer reads as 2000000, with a warning. |
| `autopilot.maxLanes` | repo | `null` | positive integer or null (checked in `hooks/scripts/crew_wave.py`) | Lanes one `/crew:autopilot wave` runs at once; null is the resolved `pm.maxDispatches`, a larger value is capped to it and anything but a positive integer reads as it, each with a warning. |
| `autopilot.reviewPolicy` | repo | `"stop"` | `stop` \| `clean-only` \| `fix-and-rereview` | What autopilot does with a review verdict. A wave lane: `stop` ends at the first verdict, `clean-only` takes a CLEAN round on to the done checks, `fix-and-rereview` fixes within the ledger's rounds. A single-ticket run (T-0067): only `fix-and-rereview` acts, fixing a non-final FINDINGS round's BLOCK and FIX lines itself (the `fix` phase) and re-reviewing. Anything else reads as `stop`, with a warning; no setting accepts a review. |

## `context` keys (11)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `context.enabled` | repo | `true` | not validated - read by `hooks/scripts/context-watch.sh` (expects boolean) | Run the context watcher. |
| `context.warnAt` | repo | `0.4` | not validated - read by `hooks/scripts/context-watch.sh` (expects number) | Fraction of the budget at which the watcher warns, wraps up and auto-clears; default 0.4 since 1.2.40 (was 0.5), an explicit value is kept. |
| `context.reserveTokens` | repo | `0` | not validated - read by `hooks/scripts/context-watch.sh` (expects integer or null) | Tokens held back from the budget; `null` means off. |
| `context.autoClear.enabled` | machine-arms | `null` | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_autocycle.py`) | Auto-clear after a wrap-up. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |
| `context.autoClear.method` | both | `"auto"` | `auto` \| `none` \| `notify` \| `tmux` \| `xdotool` \| `wtype`; per OS: linux: auto, none, notify, tmux, xdotool, wtype; macos: auto, none, notify, tmux; windows: auto, none, notify; windows-bash: auto, none, notify, tmux | How `/clear` is typed. `auto` picks per platform; a method this OS lacks stands auto-clear down. |
| `context.autoClear.delaySeconds` | both | `3` | number (coerced in `hooks/scripts/crew_autocycle.py`) | Delay before typing; an unusable value warns and reads as 3. |
| `context.autoClear.minHandoffLines` | both | `5` | number (coerced in `hooks/scripts/crew_autocycle.py`) | Shortest handoff that may be cleared after; a non-number reads as 5. |
| `context.autoClear.onlyRepos` | machine-only | `null` | list of absolute repo paths, or null (coerced in `hooks/scripts/crew_autocycle.py`) | Narrowing only, machine file only: null narrows nothing, a list arms only those repos, `[]` or a non-list arms nothing. |
| `context.autoClear.onlySessions` | machine-only | `null` | list of session ids, or null (coerced in `hooks/scripts/crew_autocycle.py`) | As `onlyRepos`, for session ids; with both set, both must match. |
| `context.autoClear.wrapUp` | machine-arms | `null` | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_autocycle.py`) | Auto wrap-up before auto-clear (T-0017): the warning becomes the wrap-up procedure and the clear waits for its results. Only the machine file arms it (exactly `true`), only where `enabled` is armed; a repo `false` vetoes it. |
| `resume.auto` | machine-arms | `null` | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_resume.py`) | Auto-resume after `/clear` or a manual `/compact`. Only the machine file can arm it (exactly `true`); a repo `false` vetoes it. |

## `notify` keys (4)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `notify.provider` | both | `null` | telegram, teams, none or null; any other value sends nothing (coerced in `hooks/scripts/crew_notify.py`) | Where notifications go: `telegram`, `teams` or `none` (off). A repo null inherits the machine provider; a repo `none` opts this repo out. |
| `notify.tokenEnv` | machine-only | `null` | not validated - read by `hooks/scripts/crew_notify.py` (expects string or null) | Name of the environment variable holding the Telegram bot token; null may be filled from the notify skill's `bot_token_env`. Honoured from the machine file only. |
| `notify.chatId` | both | `null` | not validated - read by `hooks/scripts/crew_notify.py` (expects string or null) | Telegram chat id; null may be filled from the notify skill's `chat_id`, and the skill's example value counts as unset. |
| `notify.events` | both | `["blocker", "deploy", "question"]` | list of event names; an unknown name is dropped with a notice (coerced in `hooks/scripts/crew_notify.py`) | Events that notify: `deploy`, `question`, and `blocker` (T-0060's four blocker reasons). The pre-1.0 names `gate`, `waiting`, `phase`, `review` and `done` are mapped with a notice. A list is one leaf. |

## `memory` keys (2)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `memory.mode` | both | `"repo"` | not validated - read by `skills/crew-memory/SKILL.md` (expects string) | Where memory lives (`repo`, or a vault). |
| `memory.vaultPath` | both | `null` | not validated - read by `hooks/scripts/crew_recall.py` (expects path or null) | The Obsidian vault used for memory. |

## `platform` keys (4)

| Key | Layer | Default | Values | Summary |
|---|---|---|---|---|
| `platform.os` | repo | `null` | not validated - read by `hooks/scripts/crew_platform.py` (expects string or null) | Detected OS, stamped by platform-sync. |
| `platform.wsl` | repo | `null` | not validated - read by `hooks/scripts/crew_platform.py` (expects boolean or null) | Detected WSL, stamped by platform-sync. |
| `platform.shell` | repo | `null` | not validated - read by `hooks/scripts/crew_platform.py` (expects string or null) | Detected shell, stamped by platform-sync. |
| `platform.windowsHostIp` | repo | `null` | not validated - read by `hooks/scripts/crew_platform.py` (expects string or null) | Windows host IP seen from WSL. |
