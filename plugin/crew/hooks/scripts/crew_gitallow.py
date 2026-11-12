"""`guards.git.allow`: the owner's switch that stops crew's command guards from
blocking or asking on git commands (crew 1.3.67).

THE VALUES.

    null / absent   off: every guard judges git exactly as before (the default)
    "off"           the same, said out loud; in the repo file it is a VETO
    "all"           no crew command guard blocks or asks on a git command
    ["commit", ...] an allowlist: a git command whose SUBCOMMAND is listed
                    passes; every other git command keeps today's checks

WHAT IT LOOSENS, and nothing else. Only the parts of a guard that judge a git
command (a simple command whose program is `git`):

  - the cloud guard's `guards.forcePush` rule (`git push --force`, `+ref`, and
    `xargs git ...` whose subcommand crew cannot see);
  - the mass guard's git counts (`git commit`, `git push`, `git clean -f`,
    `git rm`, `git reset --hard`, `git checkout -f` / `-- <paths>`,
    `git restore`);
  - the promote gate, for a command line that is ONLY git commands
    (`promote_exempt`): a commit message or heredoc that merely contains a
    declared deploy's text no longer trips it. A declared deploy that is
    itself a git command (`git push prod main`) stays gated: that is a deploy,
    not a git block.

Every other finding on the same line is judged as before (`git push -f && rm
-rf x` still meets the mass guard for the `rm`). `gh` is not git: `gh pr
create`'s mass count and `gh pr merge --admin` keep their own keys.

WHO MAY TURN IT ON. The machine file only (`~/.claude/crew/config.json`), and
only through the double confirmation `humanOnly` uses: `crew_confirm_config.py
propose --layer machine --key guards.git.allow --value '"all"'` records the
change, and the owner types `/crew:confirm-config <change_id>` twice. A value
counts only while the newest settled receipt for this key in that file is an
applied change to EXACTLY that value (`settings`); a value written any other
way (a hand edit, an agent's Edit) reads as off. `crew_config.py --set` and the
`/crew:config` menu refuse every value but `"off"` and null (`write_refusal`).
A repo file can never turn it on (a cloned repository must not loosen a guard
on someone else's machine); a repo `"off"` vetoes the machine value.

UNKNOWN IS OFF. A value that is not one of the forms above, an unreadable file
or receipt store, a line crew cannot split, or a subcommand it cannot read all
leave the guards judging as before. Never an exemption by default.

Standard library only; imports nothing that imports `crew_config`, so
`crew_config` may import it.
"""
from __future__ import annotations

import json
import os
import re

import crew_common
import crew_config_files
import crew_humanonly
import crew_state

KEY = "guards.git.allow"
OFF, ALL = "off", "all"

# A subcommand name as git spells one: lower-case letters, digits and `-`.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# git's global options that take a VALUE as the next word (`-C dir`, `-c k=v`).
_GIT_VALUE_OPTS = frozenset(("-C", "-c", "--git-dir", "--work-tree", "--namespace",
                             "--exec-path", "--config-env", "--super-prefix"))

# The cloud guard's finding scope key carrying a git finding's subcommand.
SCOPE_KEY = "gitsub"
# The subcommand of a git command crew could not read (`xargs git` with the
# subcommand on stdin, a variable): only `all` lets it through.
UNSEEN = None

_REFUSAL = ("lets every git command past crew's command guards, so it needs the "
            "owner's double confirmation: `crew_confirm_config.py propose --layer "
            "machine --key guards.git.allow --value <json>` records it and prints a "
            "change id, and the owner types /crew:confirm-config <change_id> twice. "
            "A crew writer may only set it to \"off\" or null.")
_REPO_REFUSAL = ("a repo file can never turn guards.git.allow on (a cloned repository "
                 "must not loosen a guard on someone else's machine); a repo may only "
                 "say \"off\", which vetoes the machine value")


# --- the value ---------------------------------------------------------------------

def normalise(value):
    """`OFF`, `ALL` or a frozenset of subcommand names for a config value, or
    None when it is malformed. null and absent are `OFF`."""
    if value is None or value == OFF:
        return OFF
    if value == ALL:
        return ALL
    if isinstance(value, list) and value and all(
            isinstance(name, str) and _NAME_RE.match(name) for name in value):
        return frozenset(value)
    return None


def label(setting):
    """A short spelling of a normalised setting for guard.log and messages."""
    if isinstance(setting, frozenset):
        return "allowlist:" + ",".join(sorted(setting))
    return str(setting)


def write_refusal(dotted, layer, value):
    """Why a crew WRITER (`crew_config.py --set`, the menu) may not set
    `dotted` to `value` at `layer`, or None. Only the double confirmation
    turns the switch on; a writer may turn it off (machine `"off"` / null /
    removal) or veto it (repo `"off"`)."""
    if dotted != KEY:
        return None
    if layer == "machine":
        return None if value is None or value == OFF else _REFUSAL
    return None if value == OFF else _REPO_REFUSAL


# --- the subcommand ----------------------------------------------------------------

def subcommand(args):
    """The subcommand of a git argument list (the words after `git`), lower
    case, or `UNSEEN` when there is none or it is not a plain name."""
    index = 0
    while index < len(args) and isinstance(args[index], str) and args[index].startswith("-"):
        word = args[index]
        if word in _GIT_VALUE_OPTS:
            index += 2
        else:
            index += 1
    if index >= len(args) or not isinstance(args[index], str):
        return UNSEEN
    sub = args[index].lower()
    return sub if _NAME_RE.match(sub) else UNSEEN


def allows(setting, sub):
    """True when `setting` (normalised) lets a git command with subcommand
    `sub` through. `UNSEEN` passes only under `ALL`."""
    if setting == ALL:
        return True
    if isinstance(setting, frozenset):
        return sub is not UNSEEN and sub in setting
    return False


# --- what is in force --------------------------------------------------------------

def _layer_value(path):
    """`(present, raw value)` of `guards.git.allow` in one config file."""
    cfg, _digest = crew_config_files.read_tolerant(path)
    guards = cfg.get("guards") if isinstance(cfg, dict) else None
    block = guards.get("git") if isinstance(guards, dict) else None
    if not isinstance(block, dict) or "allow" not in block:
        return False, None
    return True, block["allow"]


def _canonical(value):
    return json.dumps(value, sort_keys=True)


def receipt_value(store, layer, path, dotted=KEY):
    """`(backed_value_json, why)`: the canonical JSON of the value the NEWEST
    settled receipt for (layer, file, key) applied, or None with the reason.
    A later revocation, or a store that cannot be read whole, backs nothing."""
    records, problems = crew_humanonly.all_records(store)
    if problems:
        return None, "the confirmation store could not be read: " + "; ".join(problems)
    target = crew_humanonly.target_key(path)
    settled = [r for r in records
               if r.get("layer") == layer and r.get("target") == target
               and r.get("key") == dotted and r.get("state") in (crew_humanonly.APPLIED, "revoked")
               and isinstance(r.get("settled"), (int, float))]
    if not settled:
        return None, "no double-confirmed change set it"
    newest = max(settled, key=lambda r: r["settled"])
    if newest.get("state") != crew_humanonly.APPLIED:
        return None, f"the last confirmed change ({newest.get('change_id')}) was revoked"
    return _canonical(newest.get("value")), f"double-confirmed by {newest.get('change_id')}"


def settings(root, global_path=None, store=None):
    """`{"allow": OFF|ALL|frozenset, "why": str}` for `root`. Never raises:
    anything that cannot be told is `OFF` (the guards judge as before)."""
    try:
        machine_path = global_path or crew_state.GLOBAL_CONFIG_PATH
        present, value = _layer_value(machine_path)
        if not present or value is None:
            return {"allow": OFF, "why": "not set in the machine file"}
        setting = normalise(value)
        if setting is None:
            return {"allow": OFF, "why": f"{KEY} = {value!r} is not null, \"off\", \"all\" "
                                         "or a list of git subcommand names; read as off"}
        if setting == OFF:
            return {"allow": OFF, "why": "\"off\" in the machine file"}
        backed, why = receipt_value(store or crew_humanonly.store_dir(global_path),
                                    "machine", machine_path)
        if backed != _canonical(value):
            detail = why if backed is None else f"the last confirmed value was {backed}"
            return {"allow": OFF, "why": f"{KEY} = {json.dumps(value)} in the machine file, "
                                         f"not honoured: {detail}"}
        repo_present, repo_value = _layer_value(crew_common.repo_config_file(root, "config.json"))
        if repo_present and repo_value is not None:
            # A repo value never widens: "off" vetoes, a malformed one is read
            # as the veto (unknown is off), and "all" or a list is ignored.
            repo_setting = normalise(repo_value)
            if repo_setting == OFF:
                return {"allow": OFF, "why": "vetoed by \"off\" in the repo file"}
            if repo_setting is None:
                return {"allow": OFF, "why": f"the repo file's {KEY} = {repo_value!r} is "
                                             "malformed; read as a veto"}
        return {"allow": setting, "why": f"{label(setting)} in the machine file, {why}"}
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return {"allow": OFF, "why": f"could not be read ({type(exc).__name__}); read as off"}


# --- is a whole line only git ------------------------------------------------------

_GIT_HEAD_RE = re.compile(r"^(?:.*[/\\])?git(?:\.exe)?$", re.IGNORECASE)


def _is_git_word(word):
    return bool(word) and "$" not in word and "`" not in word and bool(_GIT_HEAD_RE.match(word))


def _bash_commands(text, depth=0):
    """Every simple command of bash `text` as dequoted words, its substitutions'
    commands included, or None when crew cannot split it whole."""
    import crew_guards  # pylint: disable=import-outside-toplevel
    if depth > 4:
        return None
    splitter = crew_guards._CommandSplitter(text)  # pylint: disable=protected-access
    try:
        commands, subs = splitter.split()
    except crew_guards._Unsure:  # pylint: disable=protected-access
        return None
    out = []
    for words in commands:
        out.append([crew_guards._dequote(w) for w in words])  # pylint: disable=protected-access
    for sub in subs:
        inner = _bash_commands(sub, depth + 1)
        if inner is None:
            return None
        out.extend(inner)
    return out


def _ps_commands(text):
    """Every pipeline-free statement of PowerShell `text` as dequoted words, or
    None when crew will not read it: a pipe, a subexpression (`$(`, `@(`), a
    script block, or a quote or here-string left open."""
    statements, words, word = [], [], []
    i, n = 0, len(text)

    def end_word():
        if word:
            words.append("".join(word))
            word.clear()

    def end_statement():
        end_word()
        if words:
            statements.append(list(words))
        words.clear()

    while i < n:
        c = text[i]
        if text.startswith("@'", i) or text.startswith('@"', i):
            quote = text[i + 1]
            start = text.find("\n", i)
            close = text.find("\n" + quote + "@", start if start != -1 else n)
            if start == -1 or close == -1:
                return None
            body = text[start + 1:close]
            if quote == '"' and ("$(" in body or "@(" in body):
                return None
            word.append(body)
            i = close + 2
            continue
        if c == "'":
            end = i + 1
            while True:
                end = text.find("'", end)
                if end == -1:
                    return None
                if text.startswith("''", end):
                    end += 2
                    continue
                break
            word.append(text[i + 1:end].replace("''", "'"))
            i = end + 1
            continue
        if c == '"':
            end = i + 1
            buf = []
            while end < n and text[end] != '"':
                if text[end] == "`" and end + 1 < n:
                    buf.append(text[end + 1])
                    end += 2
                    continue
                if text.startswith("$(", end) or text.startswith("@(", end):
                    return None
                buf.append(text[end])
                end += 1
            if end >= n:
                return None
            word.append("".join(buf))
            i = end + 1
            continue
        if c == "`":
            if i + 1 < n and text[i + 1] == "\n":
                i += 2
                continue
            if i + 1 < n:
                word.append(text[i + 1])
            i += 2
            continue
        if text.startswith("$(", i) or text.startswith("@(", i) or c in "{}()|":
            if c == "|" and text.startswith("||", i):
                end_statement()
                i += 2
                continue
            return None
        if c in " \t":
            end_word()
            i += 1
            continue
        if c in ";\n\r" or text.startswith("&&", i):
            end_statement()
            i += 2 if text.startswith("&&", i) else 1
            continue
        if c == "#" and not word:
            while i < n and text[i] != "\n":
                i += 1
            continue
        word.append(c)
        i += 1
    end_statement()
    return statements


def line_commands(command, shell):
    """The simple commands of `command` read as `shell`, or None (cannot tell)."""
    if not isinstance(command, str) or not command.strip():
        return None
    if shell == "powershell":
        return _ps_commands(command.replace("\r\n", "\n"))
    return _bash_commands(command)


def line_exempt(command, shell, setting):
    """True when EVERY command `command` runs is a git command `setting` lets
    through: nothing else on the line, no substitution running anything but
    such a git command. Anything crew cannot split is False."""
    if setting == OFF or setting is None:
        return False
    commands = line_commands(command, shell)
    if not commands:
        return False
    for words in commands:
        if not words or not _is_git_word(words[0]):
            return False
        if not allows(setting, subcommand(words[1:])):
            return False
    return True


# --- the promote gate --------------------------------------------------------------

_GIT_IN_DEPLOY_RE = re.compile(r"(?:^|[\s;&|(`'\"/\\])git(?:\.exe)?(?=[\s'\"]|$)",
                               re.IGNORECASE)


def _declared_deploys():
    """Every declared `deploy` string in the working map and, when the map is
    dirty, the committed one (the maps the gates read). Raises on a map that
    cannot be read: the caller then exempts nothing."""
    import _promote_dispatch  # pylint: disable=import-outside-toplevel
    out = []
    for envs in (_promote_dispatch.committed_envs(), _promote_dispatch.working_envs()):
        if envs is None:
            continue
        if not isinstance(envs, dict):
            raise ValueError("environments is not an object")
        for cfg in envs.values():
            if not isinstance(cfg, dict):
                continue
            deploys = _promote_dispatch.get_ci(cfg, "deploy", [])
            deploys = [deploys] if isinstance(deploys, str) else deploys
            if isinstance(deploys, list):
                out.extend(d for d in deploys if isinstance(d, str) and d.strip())
    return out


def promote_exempt(command, shell, root=".", global_path=None, store=None):
    """True when the promote gate should let `command` through untouched
    because `guards.git.allow` covers it: the switch is on, the line is only
    allowed git commands, and no declared deploy that is itself a git command
    is contained in it. Run with the project dir as cwd and the gate's
    CREW_HEAD_MAP / CREW_MAP_DIRTY set. Never raises; anything unclear is
    False, and the gate judges the command as before."""
    try:
        setting = settings(root, global_path, store)["allow"]
        if not line_exempt(command, shell, setting):
            return False
        import _promote_dispatch  # pylint: disable=import-outside-toplevel
        folded = _promote_dispatch.fold(command)
        for declared in _declared_deploys():
            if _GIT_IN_DEPLOY_RE.search(declared) and _promote_dispatch.fold(declared) in folded:
                return False
        return True
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return False


def main(argv=None):
    """`crew_gitallow.py [--root R]`: print what `guards.git.allow` resolves to."""
    import argparse  # pylint: disable=import-outside-toplevel
    parser = argparse.ArgumentParser(prog="crew_gitallow.py")
    parser.add_argument("--root", default=".")
    parser.add_argument("--global-path", default=None)
    args = parser.parse_args(argv)
    got = settings(os.path.abspath(args.root), args.global_path)
    print(f"{KEY}: {label(got['allow'])} - {got['why']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
