#!/usr/bin/env python3
"""Generate crew's configuration reference from the code (T-0048, L-0725).

Writes two files, both whole, from `crew_config.default_config()` /
`default_global_config()` (the defaults and the key set), the ratchet tables in
`crew_guards` / `crew_config` (the layer), the guard profile table
(`crew_guards.PROFILE_MAP`) and `crew_keys.KEY_META` (the values, summaries,
families and arrival versions):

- `docs/guides/crew/src/configuration-reference.md`, the guide's reference;
- `plugin/crew/CONFIG.md`, the settings reference that ships with the plugin.
  Since L-0725 it is generated whole: nothing in it is hand-written, so a
  one-byte edit anywhere makes `--check` fail. The reasoning behind the keys
  lives in `docs/crew/config-rationale.md`.

It never reads a config FILE -- no `read_global_config`, no `load_config` --
so the output is the same on every machine, whatever `~/.claude/crew/` holds.

Usage:
    config_reference.py --write   # regenerate both
    config_reference.py --check   # exit 1 naming each stale file, 2 on any error

`--check` is what `scripts/check-marketplace.py` runs. An error is exit 2 with
the message, never 0: a check that could not import the code compared nothing,
and must not read as "current".

Standard library only.
"""
from __future__ import annotations

import json
import os
import sys

sys.dont_write_bytecode = True

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(SRC, os.pardir, os.pardir, os.pardir, os.pardir))
SCRIPTS = os.path.join(ROOT, "plugin", "crew", "hooks", "scripts")
REFERENCE = os.path.join(SRC, "configuration-reference.md")
CONFIG_MD = os.path.join(ROOT, "plugin", "crew", "CONFIG.md")
COMMAND = "python3 docs/guides/crew/src/config_reference.py --write"
RATIONALE = "docs/crew/config-rationale.md"

EXIT_STALE = 1
EXIT_ERROR = 2


def _modules():
    """The crew modules, imported from THIS tree's plugin."""
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    import crew_config  # pylint: disable=import-outside-toplevel
    import crew_dropped  # pylint: disable=import-outside-toplevel
    import crew_guards  # pylint: disable=import-outside-toplevel
    import crew_keys  # pylint: disable=import-outside-toplevel
    return crew_config, crew_guards, crew_keys, crew_dropped


def _dig(node, dotted):
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


_MISSING = object()


def _word(value):
    """One value as it is written in a config file: a bare string, else JSON."""
    return value if isinstance(value, str) else json.dumps(value)


def _code(value):
    return f"`{_word(value)}`"


def _cell(text):
    return text.replace("|", "\\|").replace("\n", " ")


def _since(since):
    if since is None:
        return "unreleased"
    if since.startswith("<="):
        return f"{since[2:]} or earlier"
    return since


class Model:  # pylint: disable=too-few-public-methods
    """Every fact the two renderers print, computed once."""

    def __init__(self):
        self.config, self.guards, self.keys, self.dropped = _modules()
        problems = self.keys.problems()
        if problems:
            raise RuntimeError("crew_keys disagrees with the code: " + "; ".join(problems))
        self.repo_defaults = self.config.default_config()
        self.global_defaults = self.config.default_global_config()
        self.leaves = self.keys.all_leaves()

    def default(self, key):
        repo = _dig(self.repo_defaults, key)
        machine = _dig(self.global_defaults, key)
        if repo is _MISSING:
            return f"`{json.dumps(machine)}`"
        if machine is _MISSING or machine == repo:
            return f"`{json.dumps(repo)}`"
        return f"`{json.dumps(repo)}` (repo), `{json.dumps(machine)}` (machine)"

    def values(self, key, prefix=""):
        """The allowed-values cell. `prefix` turns a plugin-relative source
        into a repo-relative one for the docs copy. A personal key
        (`crew_guards.PERSONAL_KEYS`, T-0050) lists its values strictest
        first, the order its stricter-wins rule ranks them in, and says so."""
        text = self._values(key, prefix)
        personal = self.guards.PERSONAL_KEYS.get(key)
        if personal is None:
            return text
        if personal[0] == "int-min":
            return f"{text}; personal: the smaller wins"
        return f"{text}; personal: listed strictest first, the stricter wins"

    def _values(self, key, prefix):
        row = self.keys.KEY_META[key]
        kind = row["kind"]
        src = f"`{prefix}{row['source']}`" if row["source"] else ""
        vals = self.keys.values_of(key)
        personal = self.guards.PERSONAL_KEYS.get(key)
        if vals is not None and personal is not None and personal[0] == "tiers":
            # The reader's tuple, in rank order (`test_crew_keys` holds the
            # two to the same values).
            vals = sorted(vals, key=personal[1].index)
        listed = " | ".join(_code(v) for v in vals) if vals is not None else ""
        if kind == "ratchet":
            return f"{listed} (ratchet: narrower layer wins; listed narrowest first)"
        if kind == "tuple":
            text = f"list of: {listed}" if row["type"] == "list of" else listed
            by_os = row["values_by_os"]
            if by_os:
                text += "; per OS: " + "; ".join(
                    f"{os_name}: {', '.join(by_os[os_name])}" for os_name in by_os)
            return text
        if kind == "branch":
            shown = listed or row["type"]
            return f"{shown} (checked in {src})"
        if kind == "type":
            return f"{row['type']} (coerced in {src})"
        if kind == "open-table":
            return f"{row['type']} (checked in {src})"
        if kind == "prose":
            return f"{listed} (listed in {src}; not validated)"
        return f"not validated - read by {src} (expects {row['type']})"

    def counts(self):
        total = len(self.leaves)
        machine = sum(1 for k in self.leaves if self.config.is_global_path(k))
        return total, machine, total - machine


LAYER_TERMS = (
    ("repo", "only `.crew/config.json` may set it; the global file's value is "
     "pruned on read and refused on write."),
    ("both", "either file may set it; the repo value wins over the machine one."),
    ("both, ratchet", "either file may set it, and the NARROWER of the two wins "
     "(`crew_guards.RATCHETED_KEYS`). A repo can tighten what the machine allows, "
     "never loosen it."),
    ("both, widening warned", "either file may set it and the repo wins, but a "
     "write that widens it is flagged (`crew_config._RATCHETED`)."),
    ("both, stricter wins", "a personal key (`crew_guards.PERSONAL_KEYS`): either "
     "file may set it, and where both do the STRICTER value wins; a layer that is "
     "silent (absent or `null`) imposes nothing, so a machine value is your default "
     "for every repo and a repo may only narrow it."),
    ("machine-arms", "only the global file can turn it on (exactly `true`); a "
     "repo may only veto it with `false` (`crew_config.REPO_VETO_ONLY`)."),
    ("machine-only", "read from the global file alone; a repo's own value is "
     "never consulted."),
    ("human-only opt-out", "a `humanOnly` key (`crew_humanonly`): `false` opts "
     "out only from the machine file or an untracked repo file, only after the "
     "owner types `/crew:confirm-config <change_id>` twice, and a `true` in "
     "either layer vetoes it. Not acted on by any hook yet (see the section "
     "below)."),
)

HUMAN_ONLY_SECTION = """\
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

## Git commands (`guards.git.allow`, crew 1.3.75)

The owner's switch that stops crew's command guards from blocking or asking on
git commands, destructive ones included. Off by default (`null`, or `"off"`).

| Value | What passes |
|---|---|
| `null` / `"off"` | nothing changes: every guard judges git as before |
| `"all"` | every git command |
| `["commit", "push", ...]` | a git command whose subcommand is listed; every other git command keeps today's checks |

A listed subcommand passes with every option it takes: listing `push` also lets
`git push --force` and `git push origin +main` through, because the force-push
rule is a finding on the `push` subcommand. To keep force pushes stopped, leave
`push` out of the list.

What it loosens, and nothing else: the cloud guard's `guards.forcePush` rule
(`git push --force`, `+ref`; not `xargs git`, whose appended arguments crew
cannot see); the mass stop's git counts (`git commit`, `git push`,
`git clean -f`, `git rm`, `git reset --hard`, `git checkout -f` / `-- <paths>`,
`git restore`); and the promote gate for a command line made ONLY of covered
git commands, so a commit message or heredoc that merely mentions a declared
deploy no longer trips it. Everything else on the same line is judged as
before (`git commit && rm -rf big/` still meets the mass stop for the `rm`). A
declared deploy that is itself a git command (`git push prod main`) stays
gated: that is a deploy, not a git block. `gh` is not git: `gh pr merge
--admin` (`guards.adminMerge`), `gh pr create`'s mass count, workflow
dispatches and `gh api` calls are untouched.

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
a line it cannot split, a subcommand it cannot see - is off.

Never exempt, whatever the value: a git command that hands git config or a
command of its own - a global `-c` (an alias `!cmd`, `core.sshCommand`,
`core.pager`), `--config-env` or `--exec-path`, a `GIT_*` environment variable
set on the line (or assigned and then exported by name, `X=v; export X`), one
git or what it starts reads a program or config from (`HOME`,
`XDG_CONFIG_HOME`, `PATH`, `EDITOR`, `PAGER`, `SSH_ASKPASS`, `LD_PRELOAD`,
...), or an option or subcommand that runs a command it is given
(`rebase --exec`/`-x`, `submodule foreach`, `bisect run`, `push`/`send-pack
--receive-pack`/`--exec`, `fetch-pack --upload-pack`/`--exec`,
`fetch`/`pull`/`clone`/`ls-remote --upload-pack`, `clone
-u`/`-c`/`--template`, `grep -O`, `difftool --extcmd`, `filter-branch`,
`instaweb`, `send-email --*-cmd`, `daemon --access-hook`), in any
abbreviation git accepts (`--exe`, `--receive=...`: git takes an unambiguous
prefix of a long option). Nor a git command crew cannot read whole: a word
built when it runs (`"$OPT"`, `${X:-...}`, `$env:X`, a backtick or `$(...)`
substitution, a PowerShell `@splat`; in bash an unquoted brace expansion
(`--rece{ive-pack,}=x`), glob (`*`, `?`, `[`) or leading `~`; in PowerShell
`--%`, a `%NAME%`, a glob character or a leading `~`) - so `git commit -m "$(git rev-parse
HEAD)"` is judged as before - or a git command `xargs` / `parallel` runs,
whose appended arguments come from input crew cannot see. In PowerShell a
single `&` (the background or call operator) makes the line unreadable for the
promote gate; `2>&1` and a quoted `&` do not. A git command aimed at another
repository (`git -C <dir>`) passes only when that repository's own file does
not veto it either; one whose repository crew cannot tell (`--git-dir`,
`--work-tree`, a `-C` built from a variable, or any `cd` on the line) is
judged as before.

What a receipt cannot prove: the store (`~/.claude/crew/confirm-config/`) is
plain files. It is protected from an agent's writes ONLY while `scope.mode` is
on: then the scope guard refuses a Write/Edit into it, and a shell command
naming it beside a writing word. With `scope.mode` off nothing stops an agent
writing a receipt, and even with it on a process that runs arbitrary code as
you can write a whole, well-formed record. And `"all"` does not stop what git
runs from its own persistent configuration: hooks (`.git/hooks/`,
`core.hooksPath`), aliases (`alias.*` set in a config file earlier), and
`core.sshCommand`, `core.pager`, `core.editor`, filters and the like all run
under `"all"` exactly as they would with crew absent. crew reads only the
command line, never git's config files or hooks.

`python3 hooks/scripts/crew_gitallow.py --root .` prints what is in force.
Each pass is logged to `.crew/guard.log` with the policy `gitAllow:<value>`.
"""

INTRO = """\
# crew 1.0 - configuration reference

This document has two parts. The first is short and hand-written: how crew's two
config files combine, how to see what is in force, and the common setups. The
second is generated from the code and lists every key.

## How the two files combine

crew reads two JSON files:

- `~/.claude/crew/config.json` - the **machine-global** file. Your personal
  defaults for every repo on this machine: providers and models, notifications,
  auto-clear, the guards, how far autopilot may go.
- `.crew/config.json` - the **repo** file. Facts about one checkout: the
  tracker, the board, scope enforcement, production declarations.

The repo file wins over the machine file, which wins over crew's defaults. Four
exceptions, each named in the Layer column below:

- A **repo-only** key in the machine file takes effect nowhere. It is pruned on
  read and refused on write.
- A **ratcheted** key (`install.policy`, each guard `guards.profile` and
  `guards.overrides` expand to, `change.requireForProduction`,
  `environments.prodUnattended`) resolves to the narrower of the two values, so
  a cloned repo cannot widen what your machine allows.
- A **machine-armed** key (`resume.auto`, `context.autoClear.enabled`) can be
  turned on only in the machine file. A repo can only switch it off.
- A **personal** key (the five `autopilot.*` keys) resolves per key to the
  stricter of the layers that set it; a layer that says nothing imposes
  nothing. A machine value is your default for every repo, which a repo may
  narrow and never widen.

A `null` in the repo file over a machine value inherits the machine value. The
`/crew:init` template writes every key except the personal ones, so it does not
shadow your machine defaults for those; a repo `/crew:init` set up before that
still spells `autopilot.mode: "off"`, which holds a machine `plan` down until
you remove it (`--explain --all` names it as a `shadow:`).

## Seeing what is in force

- `/crew:config --show` prints every machine-settable key, its value and the
  layer it came from, and names any key that takes effect nowhere.
- `/crew:config` with no argument is a menu that writes either file through the
  validated path. It shows a dry run first, refuses unknown keys and
  out-of-range values, and marks a widening with `!`.
- From a shell:
  `python3 plugin/crew/hooks/scripts/crew_config.py --explain` is the same
  table, `--explain --all` adds every repo-only key and names each shadowing
  repo value, and `--models` is the per-role provider table.

## Backups and rebuilding a lost config

Every write a crew script makes to either file first copies the old bytes to
`~/.claude/crew/backups/` (the newest 20 per file kept) and is refused when
that copy fails; a hand edit is not backed up. `crew_config.py --backups`
lists the machine file's (add `--repo` for the repo file's) and
`--restore <stamp> --apply` puts one back. Your non-default values are kept in
`~/.claude/crew/profile.json` (and in your vault when `memory.vaultPath` is
set), so `--rebuild --repo` or `--rebuild --global` regenerates a lost or
corrupt file from the template plus that profile, as a dry run until
`--apply`.

## Common setups

- **Personal defaults once, for every repo.** Put providers, models,
  `notify.*`, the guards and the `autopilot.*` keys in
  `~/.claude/crew/config.json`. Leave repo files to repo facts.
- **Self-approval under autopilot.** Set `autopilot.mode: "plan"` and choose
  `autopilot.approval` (`human`, `self` or `risk`) in either file, and set
  `scope.allowCliApproval: true` in the repo file, which is the only file
  that key is read from. Review acceptance and production deploys still stop
  for you.
- **Notifications.** In the machine file, set `notify.provider` and the name
  of the environment variable holding the token in `notify.tokenEnv`. The
  secret stays in your environment, never in the file. `tokenEnv` is
  machine-only: a repo file's value is ignored with a notice.

The key list is `plugin/crew/CONFIG.md`, which ships with the plugin; the
reasoning behind the keys is in `docs/crew/config-rationale.md`.
"""


def render_reference(model=None):
    model = model or Model()
    keys = model.keys
    total, machine, repo_only = model.counts()
    out = [INTRO, HUMAN_ONLY_SECTION, "## Reference (generated)", "",
           f"Generated from the code by `{COMMAND}`. Do not edit by hand:",
           "`python3 scripts/check-marketplace.py` fails when this file is stale.",
           "",
           f"**{total} keys**: {machine} settable in the machine-global file, "
           f"{repo_only} repo-only.",
           "",
           "Columns:",
           "",
           "- **Layer**: which file may set the key.",
           "- **Default**: what `default_config()` returns. Where the machine "
           "default differs, both are shown.",
           "- **Values**: the values crew accepts, read from the same tuple the "
           "validator reads. \"not validated\" means crew checks nothing and names the "
           "file that reads the key.",
           "- **Since**: the first crew version whose template declared the key. "
           "Keys in the first template (crew 0.11.0) read \"0.11.0 or earlier\".",
           "",
           "### Layers", ""]
    out += [f"- **{term}**: {text}" for term, text in LAYER_TERMS]
    out.append("")
    groups = {}
    for key in model.leaves:
        head = key.split(".", 1)[0] if "." in key else "(top level)"
        groups.setdefault(head, []).append(key)
    for head, members in groups.items():
        out += [f"### `{head}`" if head != "(top level)" else "### Top-level keys", "",
                "| Setting | Layer | Default | Values | Since | Summary |",
                "|---|---|---|---|---|---|"]
        for key in members:
            row = keys.KEY_META[key]
            out.append("| " + " | ".join(_cell(c) for c in (
                f"`{key}`", keys.layer_of(key), model.default(key),
                model.values(key, prefix="plugin/crew/"), _since(row["since"]),
                row["summary"])) + " |")
        out.append("")
    out += ["## Coming (not in code yet)", "",
            "Keys from approved tickets that have not landed. Each moves into the "
            "table above when its ticket lands, because it is then in the code; a "
            "test fails until it does (`test_no_coming_key_is_in_code`).", ""]
    tickets = {}
    for row in keys.COMING:
        tickets.setdefault(row["ticket"], []).append(row)
    for ticket in sorted(tickets):
        out += [f"### {ticket}", "",
                "| Setting | Change | Layer | Default | Values | Summary |",
                "|---|---|---|---|---|---|"]
        for row in tickets[ticket]:
            vals = " | ".join(_code(v) for v in row["values"]) if row["values"] else ""
            out.append("| " + " | ".join(_cell(c) for c in (
                f"`{row['key']}`", row["change"], row["layer"], row["default"], vals,
                row["summary"])) + " |")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


CONFIG_PREAMBLE = """\
# crew configuration reference

Generated from the code by `{command}`. Do not edit by hand:
`python3 scripts/check-marketplace.py` fails when this file is stale. The
reasoning behind the keys is in `{rationale}`.

{total} keys: {machine} settable in the machine-global file, {repo_only} repo-only.

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

{human_only}
## Guard profiles

`guards.profile` is one word for all twelve guards; `guards.overrides.<guard>`
replaces the profile's value for one guard. Each layer expands to a value per
guard, and the per-guard ratchet then takes the narrower layer. A malformed
profile or override reads as the guard's floor (`block`, or `none` for the
production guards), never as `off`. The per-guard keys of earlier versions
(`guards.<guard>`) are still READ as aliases for `guards.overrides.<guard>`
until `/crew:migrate` rewrites them, and are never written. For `envGuard` an
explicit `null` (`"guards": {{"envGuard": null}}`) is malformed and reads as `block`; only an
absent key is `off`. The other guards still read a legacy `null` as absent.

{profile_table}

## Migrating and removed keys

`/crew:migrate` upgrades a repo file; `python3 plugin/crew/hooks/scripts/crew_migrate.py --global`
does the same for the machine file (preview, apply and rollback). It rewrites
`guards.*` into the profile with the fewest overrides and removes removed keys
that hold their default. A removed key holding another value stops the migration
until it is deleted or accepted with `--accept-dropped <key>`. {dropped} keys were
removed (ticket L-0725) and are now constants in `crew_state`
(`crew_dropped.DROPPED` lists each with its constant); a config still carrying
one is reported as having no effect (`crew_config.py --inert`, `/crew:status`, and the
SessionStart notice).

## Counts by family

{family_table}
"""


def _profile_table(model):
    profiles = model.guards.GUARD_PROFILES
    rows = ["| Guard | " + " | ".join(f"`{p}`" for p in profiles) + " |",
            "|---|" + "---|" * len(profiles)]
    for name in model.guards.ALL_GUARD_NAMES:
        rows.append(f"| `{name}` | " + " | ".join(
            f"`{model.guards.PROFILE_MAP[p][name]}`" for p in profiles) + " |")
    return "\n".join(rows)


def render_config_md(model=None):
    """The whole of `plugin/crew/CONFIG.md`."""
    model = model or Model()
    keys = model.keys
    total, machine, repo_only = model.counts()
    by_family = {family: [] for family in keys.FAMILIES}
    for key in model.leaves:
        by_family[keys.KEY_META[key]["family"]].append(key)
    family_table = "\n".join(
        ["| Family | Keys |", "|---|---|"]
        + [f"| `{family}` | {len(by_family[family])} |" for family in keys.FAMILIES])
    out = [CONFIG_PREAMBLE.format(
        command=COMMAND, rationale=RATIONALE, total=total, machine=machine,
        repo_only=repo_only, profile_table=_profile_table(model),
        human_only=HUMAN_ONLY_SECTION,
        dropped=len(model.dropped.DROPPED), family_table=family_table)]
    for family in keys.FAMILIES:
        members = by_family[family]
        if not members:
            continue
        out += [f"## `{family}` keys ({len(members)})", "",
                "| Key | Layer | Default | Values | Summary |", "|---|---|---|---|---|"]
        for key in members:
            out.append("| " + " | ".join(_cell(c) for c in (
                f"`{key}`", keys.layer_of(key), model.default(key),
                model.values(key), keys.KEY_META[key]["summary"])) + " |")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def expected():
    """`{path: full expected text}` for both files."""
    model = Model()
    return {REFERENCE: render_reference(model), CONFIG_MD: render_config_md(model)}


def _read(path):
    """The file's text with CRLF folded to LF, or None when it is missing.

    The committed blobs are LF and every text here is rendered with LF, but a
    `core.autocrlf=true` checkout (Git for Windows' default) hands the same blob
    back with CRLF. Compared byte for byte, both files then read as stale on
    every Windows checkout while CI on Linux stays green. Only the CRLF pair is
    folded, so any other difference - one byte included - still fails."""
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return fh.read().replace("\r\n", "\n")
    except FileNotFoundError:
        return None


def stale():
    """Repo-relative paths whose committed text differs from the generated."""
    return [os.path.relpath(path, ROOT).replace(os.sep, "/")
            for path, text in expected().items() if _read(path) != text]


def write():
    # Every text is computed in full before any file is opened: `open(p, "w")`
    # truncates at open time (root CLAUDE.md, Landmines).
    texts = expected()
    for path, text in texts.items():
        if _read(path) == text:
            continue
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
        print(f"wrote {os.path.relpath(path, ROOT)}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv not in (["--write"], ["--check"]):
        print(__doc__, file=sys.stderr)
        return EXIT_ERROR
    try:
        if argv == ["--write"]:
            write()
            return 0
        found = stale()
    except Exception as exc:  # pylint: disable=broad-except
        print(f"config_reference: the check DID NOT RUN: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return EXIT_ERROR
    for rel in found:
        print(f"stale: {rel} - regenerate with {COMMAND}")
    return EXIT_STALE if found else 0


if __name__ == "__main__":
    sys.exit(main())
