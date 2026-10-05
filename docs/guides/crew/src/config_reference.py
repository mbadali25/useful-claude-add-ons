#!/usr/bin/env python3
"""Generate crew's configuration reference from the code (T-0048).

Writes two things, both from `crew_config.default_config()` /
`default_global_config()` (the defaults and the key set), the ratchet tables
in `crew_guards` / `crew_config` (the layer), and `crew_keys.KEY_META` (the
values, summaries and arrival versions):

- `docs/guides/crew/src/configuration-reference.md`, the whole reference;
- the two generated tables inside `plugin/crew/CONFIG.md` (sections 10 and
  11), between `<!-- generated:config-keys-<global|repo> begin -->` and its
  `end` marker. The prose around them stays hand-written.

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
BLOCKS = ("global", "repo")

EXIT_STALE = 1
EXIT_ERROR = 2


def _marker(block, edge):
    return f"<!-- generated:config-keys-{block} {edge} -->"


def _modules():
    """The crew modules, imported from THIS tree's plugin."""
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    import crew_config  # pylint: disable=import-outside-toplevel
    import crew_guards  # pylint: disable=import-outside-toplevel
    import crew_keys  # pylint: disable=import-outside-toplevel
    return crew_config, crew_guards, crew_keys


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
        self.config, self.guards, self.keys = _modules()
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
)

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
- A **ratcheted** key (`install.policy`, every `guards.*`,
  `change.requireForProduction`, `environments.prodUnattended`) resolves to
  the narrower of the two values, so a cloned repo cannot widen what your
  machine allows.
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
- **Notifications.** In the machine file, set `notify.provider` and the
  environment variable names in `notify.urlEnv` / `notify.tokenEnv`. The
  secret stays in your environment, never in the file.

The reasoning behind each key is in `plugin/crew/CONFIG.md`, which ships with
the plugin.
"""


def render_reference(model=None):
    model = model or Model()
    keys = model.keys
    total, machine, repo_only = model.counts()
    out = [INTRO, "## Reference (generated)", "",
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


def render_config_block(block, model=None):
    """The compact table for one CONFIG.md section, markers excluded."""
    model = model or Model()
    keys = model.keys
    total, machine, repo_only = model.counts()
    if block == "global":
        members = [k for k in model.leaves if model.config.is_global_path(k)]
        head = (f"{machine} of {total} keys are settable in the machine-global file "
                f"(generated; {repo_only} are repo-only, section 11).")
    else:
        members = [k for k in model.leaves if not model.config.is_global_path(k)]
        head = (f"{repo_only} of {total} keys are repo-only (generated; {machine} are "
                "global-settable, section 10).")
    out = [head,
           f"Regenerate with `{COMMAND}` from the marketplace repository, whose",
           "`docs/guides/crew/src/configuration-reference.md` is the full reference",
           "(summaries and arrival versions). Do not edit the table by hand.",
           "",
           "| Key | Layer | Values | Default |",
           "|---|---|---|---|"]
    for key in members:
        out.append("| " + " | ".join(_cell(c) for c in (
            f"`{key}`", keys.layer_of(key), model.values(key), model.default(key))) + " |")
    return "\n".join(out) + "\n"


def splice(text, block, body):
    """`text` with `block`'s generated region replaced by `body`. Raises
    ValueError when a marker is missing, repeated or out of order: a region
    that cannot be found is never treated as current."""
    begin, end = _marker(block, "begin"), _marker(block, "end")
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError(f"CONFIG.md must hold exactly one {begin} and one {end}")
    head, rest = text.split(begin, 1)
    if end not in rest:
        raise ValueError(f"CONFIG.md's {end} comes before its {begin}")
    _old, tail = rest.split(end, 1)
    return f"{head}{begin}\n{body}{end}{tail}"


def expected():
    """`{path: full expected text}` for both files."""
    model = Model()
    with open(CONFIG_MD, encoding="utf-8", newline="") as fh:
        config_md = fh.read()
    for block in BLOCKS:
        config_md = splice(config_md, block, render_config_block(block, model))
    return {REFERENCE: render_reference(model), CONFIG_MD: config_md}


def _read(path):
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return fh.read()
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
