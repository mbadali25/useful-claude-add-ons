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
every shell command that WRITES TO that store. Since crew 1.3.130 the command is read the way the check of
your machine config reads it, and the write's TARGET is judged: `cp ~/.claude/crew/confirm-config/cc-ab12.json
/tmp/`, `cat <receipt> | jq .x > /tmp/x` and `ls <receipt> && echo ok > /tmp/ok` pass (until then a redirect or
a write verb anywhere in a command that named the store refused it). A verb's spelling inside a file name,
`Get-Content C:\\tmp\\confirm-config\\echo.txt`, is a read, and so is a search term,
`grep echo ~/.claude/crew/confirm-config/x.json`: the verb must be the command a shell runs, also behind a
wrapper, `xargs`, `find -exec` or `bash -c`. Still refused beside the store: a target nobody can resolve
(`ls <store>/ > $OUT`), a relative target when the store itself is spelled relatively (`ls confirm-config/ > x`),
and `echo`, `printf`, `touch`, `mkdir`, `chmod`, `sed`, `perl`, `python` or `node` given a path in the store.
That is a
textual tripwire, not a sandbox: a session that sets out to forge a receipt
(`python -c`, an encoded command, a variable holding the path) still can, and
`scope.mode: off` has no tripwire at all. Treat `humanOnly` opt-outs as
meaningful only with `scope.mode` `block`.
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
## The guards master switch

`guards.enabled: false` (crew 1.3.130) turns EVERY guard hook off: the promote
gate, the role-write, cloud, environment and scope guards, the verify gate, the
completion audit and the context-watch Stop hook. None of them starts, so nothing
is judged, refused, asked, warned or logged: with the switch off, nothing blocks. It
beats every per-guard setting (`guards.profile`, `guards.overrides.*`, `scope.mode`,
`verifyGate`). Three things must all hold for it to count (crew 1.3.130):

- It is in the MACHINE layer (`~/.claude/crew/config.json`). A `false` in
  `.crew/config.json`, tracked or not, is ignored and the guards stay on (a
  checkout must not be able to turn every guard off), and a repo `true` cannot
  switch a machine `false` back on.
- It is the OWNER's. Like the `humanOnly.*` opt-out, a `false` counts only when an
  applied `/crew:confirm-config` double confirmation backs it: two confirmations
  from two prompts the owner typed, and the digest of the machine file as the
  owner left it: its content (canonical JSON) AND its modification time (crew
  1.3.130). An agent's Write or Edit, a hook-side write, a hand edit, a bare
  hand-written receipt, or ANY later write to the file (a restore, a rebuild, an
  unrelated edit, or a hand edit that sets the key `true` and a later one that
  writes the identical `false` back) leaves the guards ON; so does a missing,
  revoked or unreadable receipt. The modification time is what ends that
  round trip, because no hand edit writes a revoke and the hook may not write
  one; a copy that puts the old time back (`cp -p`, an archive extract,
  `os.utime`) replays it, an accepted limit (below). The scope guard refuses an
  agent's Write or Edit of the machine config file and the receipts beside it
  (every spelling: case, `..`, a trailing dot or space, a junction, a UNC path,
  the `\\\\?\\` prefix), and a shell command that WRITES TO them: a redirect, `tee`,
  `cp`, `mv`, `rm`, `sed -i`, `Set-Content`, `Out-File`, `Add-Content`, `copy`,
  `move`, `xcopy`, `robocopy`, `curl -o` (also `-sSo` and `-O --output-dir`), `wget -O`,
  `-OutFile`, `tar -C` (before or after `-xf`), `unzip -d` (or `unzip` run in that folder; its `-o` is the overwrite switch), `7z -o<dir>`,
  `Expand-Archive`, `patch`, `git apply`, `mklink /J`, `fsutil hardlink create`, `awk -i
  inplace`, a `[IO.File]::WriteAllText` (or `[System.IO.File]::`, any write member: `AppendAll*`, `Copy`, `Move`, `Delete`, `Create`, `Replace`, and `Open` with a write mode such as `Create`, `Append` or `ReadWrite`) with the path spelled out, aimed at them (spelled out, or through `cd`, a variable,
  a glob or a path built from `.claude`, `crew` and `config.json`), or inline
  code (`python -c`, a heredoc, `pwsh -Command`) that names them beside a write
  call, in every `scope.mode` (`off`, the default, included). A shell word is judged against the owner's REAL
  path (this machine's home), never a suffix of it, so `C:/other/.claude/crew/config.json` is another file. Every
  spelling of one path is read as that path: trailing dots and spaces on any folder (`crew.\\config.json`), an NTFS
  stream (`::$DATA`, `::$INDEX_ALLOCATION`), `/c/`, `/mnt/c/` and `/cygdrive/c/` drive folders, `\\\\?\\`, an 8.3 short name (`CREW~1`), a link or junction, a brace expansion, and ANY glob that can
  match a receipt (`cc-1*.json`, `cc-?*`, `cc-[0-9]*`) or anything else below the store. `patch --dry-run` (`--check`,
  `-C`) writes nothing and passes. A word the shell cannot resolve (an unset variable, a `$` share) is judged by
  how it ENDS, component by component. Escape characters are read the way each shell reads them (crew
  1.3.130): a bash backslash (`confi\\g.json`), a PowerShell backtick (``confi`g.json``) and a cmd caret
  (`confi^g.json`) are stripped before the path is judged, in the command name and its options too (`r\\m`,
  ``Set-Cont`ent``), and a backtick command (`` `echo ~/.claude/crew`/config.json ``) is read as a command.
  A write target the guard cannot resolve to one path FAILS CLOSED when it could be the owner's: a `$(...)`
  or backtick substitution, a `$'...'` string with escapes, an unset variable, a `%VAR%`, `$env:` or `${{env:X}}`
  name (crew 1.3.130: `c${{env:X}}nfig.json` was read as an NTFS stream and passed), a bash `~name/` or `~-/`, a
  word in a parenthesised expression (`Set-Content -Path (Join-Path $HOME ".claude/crew/config.json")`), or a
  variable the command assigned from anything but one literal word (crew 1.3.130: `$p = Join-Path $HOME
  ".claude/crew/config.json"; Set-Content $p x` and `$p = $HOME + "\\.claude\\crew\\config.json"` passed; a loop
  variable and `read` count the same way). It is refused when what is spelled of it can only be the owner's
  (`~/.claude/crew/$NAME`, `~/$A/config.json`), and otherwise only when it is SUSPECT (narrowed in crew 1.3.130,
  owner decision 2026-11-15, "narrow overblocks"): the command names `.claude/crew`, the confirm-config store or
  `crew/config.json` as something it may write; or the target, the variable or the `cd` before it was built from
  pieces of that path (`.claude` and a `crew` folder in one expression or substitution); or the command stands in
  the owner's folder. Then a lone `$D`, `$(cat p)`, a parenthesised path, `$D/config.json`, and, after a `cd`
  aimed at a variable, a relative name that could end one of the owner's paths are refused.
  What does NOT make a target suspect any more: `.claude` alone (every repo has one: `cd .claude && echo x > $F`
  and `Set-Content -Path (Join-Path $wt ".claude/x.json")` pass); crew's own worktrees folder,
  `~/.claude/crew/worktrees/...`, where a checkout is an ordinary checkout (`git checkout`, `patch`, `unzip`
  there pass); and a READ of the owner's file. The operand of `cat`, `grep`, `ls`, `jq`, `Get-Content` and the
  like, and the source of a copy, are not writes, so `cat ~/.claude/crew/config.json > "$OUT"`,
  `cat ~/.claude/crew/config.json | tee "$OUT"` and `cp ~/.claude/crew/config.json "$BACKUP"` pass. A name such
  as `$D/out.txt` that cannot end one of the owner's paths passes in any command, and so does `mv x y` after
  `cd $D`. Comments do not count as naming the folder. cmd's `cd /d <folder>` is followed to the folder (crew
  1.3.130: the switch was read as the folder, so `cd /d %USERPROFILE%\\.claude\\crew && echo x > config.json`
  passed).
  Also read as writes since crew 1.3.130: `Tee-Object`, `Export-Csv`, `Export-Clixml`, `clc`; a PowerShell
  cmdlet that takes its path from the pipeline (`Get-ChildItem <it> | Remove-Item`, `| Clear-Content`,
  `Get-Item <it> | Set-Content -Value x`, `| % {{ Set-Content $_.FullName x }}`); `xargs <write verb>` fed a name
  of theirs or run in their folder (`ls | xargs rm`); `find <a folder that holds them> -delete` or
  `-exec <write verb>` (a `-name` that rules their names out passes); sed's and ex's own `w <file>` command and
  awk's `print > "<file>"`; a command behind `timeout`, `nice`, `stdbuf`, `ionice`, `setsid`, `busybox`, `wsl`,
  a dot call (`. Set-Content`) or an alias the command itself made (`Set-Alias w Set-Content; w <it> x`); and
  text run as a command by `iex` / `Invoke-Expression`, `trap`, `Start-Process <shell> -ArgumentList`,
  `[scriptblock]::Create("...")`, a here-string (`bash <<< "..."`) or a pipe into a shell (`echo "..." | bash`).
  The right-hand side of a PowerShell assignment is read as the command it runs (`$r = Set-Content <it> x`).
  Also read as writes since crew 1.3.130 (round 11): `tar` however its options are bundled (`tar -cf <it> src`,
  `-czf`, old-style `tar cf <it> src`, `-rf`, `-uf`, `--delete -f`, and an extraction into the folder,
  `tar -xC <folder> -f a.tar`); `wget -qO <it>` (an output option at the end of a bundle of flags) and wget's
  log file (`-o`, `-a`); `sort -o <it>` and `--output=<it>`; the archive `7z a|u|d|rn <it>`, `Compress-Archive`
  (`-DestinationPath <it>` or the second positional word) and `git archive -o <it>` / `--output=<it>` create;
  the command `find -exec` runs, as written (`find . -exec cp x <it> \\;`, a second `-exec` too);
  `env -C <folder> <command>`; and `fsutil file createNew <it> <size>`. A tar, 7z or sort that only READS the
  file (`tar -tf`, `7z l`, `sort <it>`, `tar -cf /tmp/a.tar <it>`) passes.
  A `cd` ends where the shell ends it (crew 1.3.130): inside `( ... )`, a `$(...)`, `bash -c "..."`,
  `pwsh -Command`, `cmd /c` or a heredoc fed to a shell it lasts until that closes, and a `pushd` lasts until its
  `popd`, so `(cd ~/.claude/crew && ls); echo x > config.json` and `pushd ~/.claude/crew && ls && popd && echo b >
  config.json` write the working directory's own `config.json` and pass (both were refused before). A `popd`
  with no `pushd` before it leaves a folder nobody can tell: a relative target is refused there only in a command
  that names your folder. A `)` that ends a `case` pattern ends no subshell. PowerShell's `( ... )` is an
  expression that runs in the shell itself, so in a command that spells a cmdlet, `$env:` or `$_`
  (`(Set-Location ~/.claude/crew); Set-Content config.json x`) the folder stays and the write is refused.
  A write inside a script block, a loop, a condition, a `try` or a `case` arm is read as the
  command it is (`foreach ($f in 1) {{ Set-Content ... }}`, `for f in a; do rm ...; done`). A command that only
  MENTIONS them (a commit message, a PR body, `ls ~/.claude/crew/ > out.txt`,
  `cat config.json | tee out.json`) passes, and so does an unrelated write in the
  same line; reading them (`cat`, `jq`, `stat`, `crew_config.py --show`) passes.
  The crew runs every normal command: no script is opened or sized, so one that
  cannot be read or is large refuses nothing. Only the word a verb WRITES TO
  counts: `Set-Content -Path out.txt -Value '<the machine config path>'` passes, as do
  `[IO.File]::ReadAllText('<it>')` and `fsutil hardlink list <it>`. The PowerShell switches
  (`-Verbose`, `-Debug`, `-Force`, `-WhatIf` and the rest, abbreviated or not) take no value, and a
  comma-separated `-Path` list is read item by item. PowerShell's `--%` stop-parsing token, an
  ambiguous parameter abbreviation and a .NET call whose destination is an expression, not a
  literal path, are read by their text only. A comma or a space inside a quoted .NET path is part of the path; inside a quoted cmdlet
  path (`Set-Content -LiteralPath 'a,b'`) a comma still splits it (accepted limit).
  Accepted limits, by the owner's decisions ("fix the overblock, add the plain
  verbs, stop there"; 2026-11-15 "fail closed on dynamic paths", then "fix BLOCKs, narrow overblocks, document
  tail"). THE TAIL: these still write the file and are NOT refused. A path built by arithmetic or by joining
  quoted pieces (`'.cl' + 'aude'`), also when the joined string is handed to `iex`; a splatted hashtable
  (`Set-Content @a`); the content of a script file (`bash script.sh`, `pwsh -File x.ps1`, a script written first
  and run after) and encoded code (`pwsh -EncodedCommand`); a launcher (`pytest`, `uv`, `make`, `python -m`);
  inline code whose write is not a write call the guard knows (`os.system(...)`, perl's `open`); a .NET type other
  than `[IO.File]` (`New-Object IO.StreamWriter`); a program the verb table does not know (`gtee`, `scp`,
  `git config --file`); cmd's delayed expansion (`!P!`); a link made earlier in the same command; a pipe or
  `xargs` fed from a file the command only reads (`cat list | xargs rm`); an 8.3 short name that does not start
  with the name it stands for (the stem is what is read); and `touch`, `chmod`, `attrib` and `icacls`, which
  change the file's metadata or permissions, not its content. Named by the round-11 review and left here: an
  in-place editor the verb table does not know (`yq -i`, also `zip <it> src` and `uniq <in> <it>`); .NET's
  `[IO.Directory]::Delete` and `[IO.File]` siblings outside `[IO.File]`; a `find -exec` that hands what it found
  to a script (`find . -exec python3 helper.py {{}} +`), since no script is opened; and a parenthesised `cd` run by
  PowerShell in a command that spells nothing only PowerShell spells (`(cd <folder>) ; echo x > config.json` is
  read as bash's subshell). The other way round, refused though it writes nothing, by design: the guard does not
  read `-WhatIf`, so `Get-ChildItem ~/.claude/crew | Remove-Item -WhatIf` fails closed. The switch is a guardrail against
  accidents and agent drift, not a boundary against a hostile agent of the same
  user.
- It is unambiguous. Only the JSON literal `false` counts: an absent key, `null`,
  `true`, a string, a corrupt file, a `guards` that is not an object, a file
  with a duplicate key (`{{"enabled": true, "enabled": false}}` is read differently
  by different parsers) all leave the guards on. A machine config path inside the
  project or the working directory (a HOME redirected into a checkout, or a
  working directory equal to, or above, your home) never counts, even with a
  confirmation; `--explain` and `/crew:status` say that ("the file lies inside the
  working directory or the project"), not "unconfirmed". Two notes: `/crew:migrate`
  rolling back does not restore a receipt it revoked (it fails safe: the guards
  stay on until the owner confirms again), and a revocation that cannot be written (a receipts store
  that cannot be written) is reported on stderr (`crew: WARNING: could not record the revocation ...`),
  not skipped in silence (the receipt backs nothing anyway: it binds the file's
  content and modification time).

It takes effect on the next hook call, with no reinstall. To turn it off, ask crew to propose it (`/crew:config`, which runs `crew_confirm_config.py propose --layer machine --key guards.enabled` and relays the change id), then type `/crew:confirm-config <change_id>` yourself, twice, in two separate prompts, within 15 minutes. `--set guards.enabled=false` is refused (crew 1.3.134). `approval-hook.sh` keeps
running, so `/crew:approve` and `/crew:confirm-config` keep working and the
`humanOnly.*` opt-out still works with the guards off. It needs python: with
none, the bash launcher still fails closed in an armed repo (known limitation).
To go back, delete the key or set it to `true` in the machine file.

**What this is, and is not.** The master switch is a guardrail against accidents
and agent drift, not a security boundary against a hostile agent running as the
same user. The receipt and the machine file are files that user can write, and the
scope guard reads command text: an agent that builds a path in a way the text
never shows (`'.cl' + 'aude'`, a command fetched at run time) can forge the whole
receipt and the `false` together, and nothing here stops it. Accepted limits, by
the owner's decision (the guard stays out of the way of normal commands): a helper
script that writes the file (written first, then run behind `cd`), a launcher such
as `pytest`, `uv`, `make` or `python -m` that runs one, an 8.3 short name used
through a shell, base64 or other encoded code, and a file copied back with its
modification time kept all still write the file or replay a receipt. The
last one includes a filesystem with coarse timestamps (FAT, some network
shares): the same confirmed bytes written back within one timestamp tick still
match the receipt's `<sha256>@<mtime_ns>` digest (inferred, not reproduced on a
fine-grained one). Keep an
untrusted agent out of the account rather than behind this key. A working
directory equal to your home, or an ancestor of it, makes an owner-confirmed
switch do nothing (the guards stay on, as for a HOME redirected into the project).
What crew tells you matches what dispatch does (crew 1.3.134): `crew_confirm_config.py propose` refuses a
machine file that is a symbolic link (the confirmation would name the target's path while the write
replaces the link) and one inside the working directory or the project, and says why; a confirmation is
reported `applied` only when the dispatcher's own reader honours its receipt, else `refused`; and
`--explain` and `/crew:status` report a machine file the dispatcher cannot read as strict JSON (a duplicate
key at any depth, malformed text, not an object, unreadable) as exactly that, not as "unconfirmed" and not
as the default.

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

## Verify gate trust (a store, not a config key)

The Stop gate runs `.crew/verify.json` `run` strings (and, with no verify.json,
`_verify/smoke.sh` or `scripts/smoke.sh`) only for a repo this machine trusts.
Trust lives in `${{CLAUDE_CONFIG_DIR:-~/.claude}}/crew/verify-trust.json`, written
by `python3 plugin/crew/hooks/scripts/verify_trust.py` (`approve`, `revoke`,
`status`, `allow-owner`, `disallow-owner`) at a terminal. It is not a config key:
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
