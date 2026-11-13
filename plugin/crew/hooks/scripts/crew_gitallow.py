"""`guards.git.allow`: the owner's switch that stops crew's command guards from
blocking or asking on git commands (crew 1.3.82).

THE VALUES.

    null / absent   off: every guard judges git exactly as before (the default)
    "off"           the same, said out loud; in the repo file it is a VETO
    "all"           no crew command guard blocks or asks on a plain git line
    ["commit", ...] an allowlist: a git command whose SUBCOMMAND is listed
                    passes; every other git command keeps today's checks

WHAT IT LOOSENS, and nothing else, for a line `line_exempt` reads as only
plain git commands:

  - the cloud guard's `guards.forcePush` rule (`git push --force`, `+ref`);
  - the promote gate (`promote_exempt`): a commit message or heredoc that
    merely contains a declared deploy's text no longer trips it. A declared
    deploy that is itself a git command (`git push prod main`) stays gated:
    that is a deploy, not a git block.

`gh` is not git: `gh pr merge --admin` and `gh api` keep their own keys.

THE LINE IS AN ALLOWLIST, FAIL-CLOSED (crew 1.3.82, PR #769 review round 4).
A line is exempt only when EVERY command on it is exactly `git` (no path, no
function, alias or `shopt` on the line -- a line holding any other command is
never exempt) followed by words that are plain literals as ONE reader
(`plain_commands`) reads them: in bash only `_BASH_SAFE` characters unquoted,
whole `'...'` runs, `"..."` runs with no `$` or backtick, backslash escapes
and git's `@{...}`; in PowerShell only `_PS_SAFE` characters, whole quoted
words with no `$`, here-strings and harmless backtick escapes. Anything else
-- `$` in any form (`"$OPT"`, `$'\\x2d...'`, `$(...)`), a backtick
substitution, a glob, a brace expansion, a leading `~`, a subshell or group,
a PowerShell `(expr)`, `@(...)`, splat, script block, `--%`, `%NAME%` or curly
quote, an assignment, a pipe into something else -- is "cannot tell", and
cannot tell is never exempt. Both the cloud guard (`line_plan`,
`finding_exempt`) and the promote gate ask this reader and nothing else.

NEVER EXEMPT even when every word is plain (`hold`): a git command that
carries config or a command line of its own -- a global `-c`, `--config-env`
or `--exec-path`, an option or subcommand that runs a command it is handed
(`rebase --exec`, `submodule foreach`, `bisect run`, `push --receive-pack`,
`send-pack --exec`, `fetch --upload-pack`, `fetch-pack --exec`, `grep -O`,
`difftool --extcmd`, `init --template`, `filter-branch`, ...), in any
abbreviation git accepts (`--exe`, `--receive=`), and a `git config` that is
not plainly a read (it may set `alias.*` or a program-valued key such as
`core.sshCommand` that a later git command on the line runs). A git command
aimed at another repository (`git -C <dir>`) is exempt only when that
repository's own file does not veto it either; one whose target crew cannot
tell (`--git-dir`, `--work-tree`) is not exempt.

WHO MAY TURN IT ON. The machine file only (`~/.claude/crew/config.json`), and
only through the double confirmation `humanOnly` uses: `crew_confirm_config.py
propose --layer machine --key guards.git.allow --value '"all"'` records the
change, and the owner types `/crew:confirm-config <change_id>` twice. A value
counts only while the newest settled receipt for this key in that file is a
WHOLE applied record (`receipt_problem`: two confirmations from two distinct
user prompts inside the proposal's window, this file's path, a value the
switch takes) for EXACTLY that value, and the machine file is still the very
file that confirmation left: its bytes, size, modification time and
metadata-change time (`file_binding`; a Windows CopyFile carries the change
time over, `_change_ns`). Any later change to the machine file by any route
but crew's own config writer (`crew_config.write_global_config`, which
re-binds the receipt when it leaves this key alone, `rebind`) reads as off.
`crew_config.py --set` and the `/crew:config` menu refuse every value but
`"off"` and null (`write_refusal`). A repo file can never turn it on; a repo
`"off"` vetoes the machine value, and so does a repo file crew cannot read.

WHAT IT CANNOT SEE. Config and hooks set EARLIER, in a file (`.git/hooks/`,
`core.hooksPath`, `alias.*`, `core.sshCommand`), run under "all" exactly as
they would with crew absent: crew reads only the command line. The receipt
store (`~/.claude/crew/confirm-config/`) is plain files; the checks here make
a forgery a deliberate act, not an accident; they are not a sandbox.

UNKNOWN IS OFF. A value that is not one of the forms above, an unreadable file
or receipt store, or a line crew cannot read whole all leave the guards
judging as before. Never an exemption by default.

Standard library only; imports nothing that imports `crew_config`, so
`crew_config` may import it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import string
import subprocess
import time

import crew_common
import crew_humanonly
import crew_state

KEY = "guards.git.allow"
OFF, ALL = "off", "all"

# A subcommand name as git spells one: lower-case letters, digits and `-`.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# git's global options that take a VALUE as the next word (`-C dir`, `-c k=v`).
_GIT_VALUE_OPTS = frozenset(("-C", "-c", "--git-dir", "--work-tree", "--namespace",
                             "--exec-path", "--config-env", "--super-prefix"))

# The cloud guard's finding scope key carrying a git finding's subcommand
# (`finding_exempt`). An `xargs git` finding carries none: the words xargs
# appends come from input crew cannot see, so it is never exempt.
SCOPE_KEY = "gitsub"
# The subcommand of a git command crew could not read: only `all` lets it
# through, and only on a line `line_exempt` reads whole.
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


# --- what a git command may never be exempted for -----------------------------------

# Global options that hand git config or a program of its own: `-c k=v` (an
# alias `!cmd`, `core.sshCommand`, `core.pager`, ...), `--config-env`, and
# `--exec-path` (where git finds its subcommands).
_INJECT_GLOBAL_RE = re.compile(r"^(?:-c.*|--config-env(?:=.*)?|--exec-path(?:=.*)?)$")
# Subcommand options that run a command line they are handed, by subcommand.
# A word matches when it IS the option, or starts with it and `=` (long) or
# with the short option's letter (`-xcmd`).
_RUNS = {
    "rebase": ("-x", "--exec"),
    "push": ("--receive-pack", "--exec"),
    # The plumbing under push and fetch takes the same program option (crew
    # 1.3.75 review round 3: both ran a handed program, measured).
    "send-pack": ("--receive-pack", "--exec"),
    "fetch-pack": ("--upload-pack", "--exec"),
    "fetch": ("--upload-pack",),
    "pull": ("--upload-pack",),
    "clone": ("--upload-pack", "-u", "-c", "--config", "--template"),
    # `git init --template=<dir>` copies that directory's hooks into the repo,
    # and a later git command on the same line runs them (round 4).
    "init": ("--template",),
    "ls-remote": ("--upload-pack",),
    "archive": ("--exec",),
    "grep": ("-O", "--open-files-in-pager"),
    "difftool": ("-x", "--extcmd"),
    "send-email": ("--to-cmd", "--cc-cmd", "--sendmail-cmd", "--smtp-server"),
    "daemon": ("--access-hook",),
}
# Subcommands that run a handed command whatever their options say.
_RUNS_ALWAYS = frozenset(("filter-branch", "instaweb"))
# (subcommand, word) pairs: `git submodule foreach <cmd>`, `git bisect run <cmd>`.
_RUNS_WORD = {"submodule": "foreach", "bisect": "run"}

# `git config` (review round 4, FIX D): a write may set an alias (`alias.p
# '!deploy-prod'`) or a program-valued key (`core.sshCommand`, `core.pager`,
# `core.editor`, `core.fsmonitor`, `core.hooksPath`, `diff.external`,
# `credential.helper`, `sequence.editor`, `gpg.program`, ...) that a later git
# command on the same line runs. Rather than list those keys, every `git
# config` that is not plainly a READ is held -- an allowlist like the rest.
# A read: only the options below, and either a read action (`--get*`, `-l`,
# `--list`, the `get` / `list` subcommands) or exactly one key.
_CONFIG_READ_ACTIONS = frozenset(("--get", "--get-all", "--get-regexp", "--get-urlmatch",
                                  "--get-color", "--get-colorbool", "-l", "--list"))
_CONFIG_READ_FLAGS = frozenset((
    "--global", "--system", "--local", "--worktree", "--show-origin", "--show-scope",
    "--null", "-z", "--name-only", "--includes", "--no-includes", "--bool", "--int",
    "--bool-or-int", "--path", "--expiry-date", "--all"))
_CONFIG_READ_VALUE_OPTS = frozenset(("-f", "--file", "--blob", "--type", "--default"))


def _config_is_read(rest):
    """True when `git config <rest>` (the words after `config`) is plainly a
    read of config, never a write or `--edit` (which runs the editor)."""
    positionals, action, index = [], False, 0
    while index < len(rest):
        word = rest[index]
        name = word.split("=", 1)[0]
        if word == "--":
            positionals.extend(rest[index + 1:])
            break
        if word.startswith("-") and word != "-":
            if name in _CONFIG_READ_ACTIONS:
                action = True
            elif name in _CONFIG_READ_VALUE_OPTS:
                index += 0 if "=" in word else 1
            elif word not in _CONFIG_READ_FLAGS:
                return False
        else:
            positionals.append(word)
        index += 1
    if positionals and positionals[0] in ("get", "list"):
        return True
    if positionals and positionals[0] in ("set", "unset", "rename-section",
                                          "remove-section", "edit"):
        return False
    return action or len(positionals) == 1


def _global_split(args):
    """`(globals, index of the subcommand)` for a git argument list."""
    index = 0
    while index < len(args) and isinstance(args[index], str) and args[index].startswith("-"):
        index += 2 if args[index] in _GIT_VALUE_OPTS else 1
    return [a for a in args[:index] if isinstance(a, str)], index


def _option_hit(word, option):
    """True when `word` is `option` or carries it: `--opt=v`, any
    abbreviation git would accept for it (`--exe`, `--receive=v`: git's
    option parser takes an unambiguous prefix of a long option, crew 1.3.75
    review round 2), or a short option bundled anywhere in a single-dash word
    (`-x`, `-xcmd`, `-ix`). Every prefix counts, ambiguous or not: over-reading
    only withholds an exemption."""
    if word == option:
        return True
    if option.startswith("--"):
        name = word.split("=", 1)[0]
        return len(name) > 2 and name.startswith("--") and option.startswith(name)
    return word.startswith("-") and not word.startswith("--") and option[1] in word[1:]


def hold(args):
    """Why a git command may never be exempted, or None. `args` are its words
    after `git`, already read as plain literals by `plain_commands` (the one
    reader both the cloud guard and the promote gate use): what is left to
    withhold is a literal option or subcommand that hands git config or a
    command line of its own."""
    words, index = _global_split(list(args))
    for word in words:
        if word != "-C" and _INJECT_GLOBAL_RE.match(word):
            return f"it hands git config or a program of its own ({word.split('=', 1)[0]})"
    sub = subcommand(args)
    rest = [a for a in args[index + 1:] if isinstance(a, str)]
    if sub in _RUNS_ALWAYS:
        return f"`git {sub}` runs a command it is handed"
    if sub in _RUNS_WORD and _RUNS_WORD[sub] in rest:
        return f"`git {sub} {_RUNS_WORD[sub]}` runs a command it is handed"
    if sub == "config" and not _config_is_read(rest):
        return ("`git config` that is not plainly a read may set an alias or a program "
                "a later git command runs")
    for word in rest:
        if word == "--":
            break
        for option in _RUNS.get(sub, ()):
            if _option_hit(word, option):
                return f"`git {sub} {option}` runs a command it is handed"
    return None


_DRIVE_RE = re.compile(r"^/([a-zA-Z])(?=/|$)")


def target_dirs(args):
    """The literal `-C` directories of a git argument list, in order, or
    `UNSEEN` when crew cannot tell which repository it acts on: a
    `--git-dir` / `--work-tree` (`=` form too), or a `-C` value that is
    built at run time (`$`, a backtick, `~`)."""
    words, _index = _global_split(list(args))
    out = []
    for position, word in enumerate(words):
        if word.split("=", 1)[0] in ("--git-dir", "--work-tree"):
            return UNSEEN
        if word == "-C":
            value = words[position + 1] if position + 1 < len(words) else None
            if not value or any(c in value for c in "$`~*?"):
                return UNSEEN
            out.append(value)
    return tuple(out)


def resolve_target(base, dirs):
    """The directory `git -C d1 -C d2 ...` runs in, from `base`: each `-C`
    relative to the one before, as git reads them. An MSYS drive path
    (`/c/x`) is read as `C:/x` on Windows."""
    where = os.path.abspath(base)
    for value in dirs:
        if os.name == "nt":
            value = _DRIVE_RE.sub(lambda m: m.group(1).upper() + ":", value)
        where = os.path.normpath(os.path.join(where, value))
    return where


# --- what is in force --------------------------------------------------------------

ABSENT, UNSET, SET, UNREADABLE = "absent", "unset", "set", "unreadable"


def read_layer(path):
    """`(state, value_or_why, binding)` for `guards.git.allow` in one config
    file, from ONE open: `ABSENT` (no file), `UNSET` (the file is fine and
    says nothing, or null), `SET` with the raw value, or `UNREADABLE` with
    why (cannot be opened or read, not UTF-8 JSON, not an object, or a
    `guards` / `guards.git` that is not an object; a link or path that does
    not resolve, `_dangles`). `binding` is the file's `file_binding` when it
    was read and its change time could be told, else None. Never raises."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
            stat = os.fstat(handle.fileno())
            change = _change_ns(handle, stat)
    except FileNotFoundError:
        if _dangles(path):
            return UNREADABLE, "is a link or path that does not resolve", None
        return ABSENT, None, None
    except OSError as exc:
        return UNREADABLE, f"cannot be read ({type(exc).__name__})", None
    binding = None if change is None else {
        "appliedDigest": hashlib.sha256(raw).hexdigest(), "appliedSize": stat.st_size,
        "appliedMtimeNs": stat.st_mtime_ns, "appliedChangeNs": change}
    try:
        cfg = json.loads(raw.decode("utf-8-sig"))
    except ValueError:
        return UNREADABLE, "does not parse as UTF-8 JSON", binding
    if not isinstance(cfg, dict):
        return UNREADABLE, "is not a JSON object", binding
    guards = cfg.get("guards")
    if guards is None:
        return UNSET, None, binding
    if not isinstance(guards, dict):
        return UNREADABLE, "has a `guards` that is not an object", binding
    block = guards.get("git")
    if block is None:
        return UNSET, None, binding
    if not isinstance(block, dict):
        return UNREADABLE, "has a `guards.git` that is not an object", binding
    if block.get("allow") is None:
        return UNSET, None, binding
    return SET, block["allow"], binding


def _dangles(path):
    """True when `path` could not be opened as missing although it is not
    simply absent: the nearest part of it that exists is a link that does not
    resolve, or is not a directory (a dangling `.crew/config.json` symlink, a
    `.crew` that is a file or a dead link). Such a file is unreadable, never
    absent: a repo file that cannot be read vetoes (crew 1.3.75 review round 2)."""
    probe = os.path.abspath(path)
    while not os.path.lexists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return False
        probe = parent
    return probe == os.path.abspath(path) or not os.path.isdir(probe)


def _change_ns(handle, stat):
    """The open file's metadata-change time, or None when it cannot be read.
    POSIX `st_ctime_ns`: every write and every `utime` moves it, and only the
    clock can set it, so a copy put back with `cp -p` (bytes and modification
    time restored) still reads as a change. Windows' `st_ctime` is the
    creation time, so there it is the NTFS ChangeTime
    (`GetFileInformationByHandleEx`). A Windows CopyFile (`Copy-Item`,
    Explorer, `shutil.copy2`) carries ChangeTime over with the bytes, so on
    Windows a copy of the confirmed file put back that way is NOT told apart
    (CONFIG.md says so)."""
    if os.name != "nt":
        return stat.st_ctime_ns
    try:
        import ctypes  # pylint: disable=import-outside-toplevel
        import msvcrt  # pylint: disable=import-outside-toplevel,import-error
        from ctypes import wintypes  # pylint: disable=import-outside-toplevel

        class _BasicInfo(ctypes.Structure):  # FILE_BASIC_INFO
            _fields_ = [("creation", ctypes.c_longlong), ("access", ctypes.c_longlong),
                        ("write", ctypes.c_longlong), ("change", ctypes.c_longlong),
                        ("attributes", wintypes.DWORD)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        query = kernel32.GetFileInformationByHandleEx
        query.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        query.restype = wintypes.BOOL
        info = _BasicInfo()
        if not query(msvcrt.get_osfhandle(handle.fileno()), 0,  # 0: FileBasicInfo
                     ctypes.byref(info), ctypes.sizeof(info)):
            return None
        return int(info.change) * 100
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return None


def file_binding(path):
    """`{"appliedDigest", "appliedSize", "appliedMtimeNs", "appliedChangeNs"}`
    of the file at `path` now, or None when it cannot be read. A confirmed receipt carries
    the one its write left; the switch counts only while they are equal."""
    return read_layer(path)[2]


def _canonical(value):
    return json.dumps(value, sort_keys=True)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def receipt_problem(record, machine_path):
    """Why an `applied` record is NOT a whole double confirmation of
    `guards.git.allow` in the file at `machine_path`, or None. The shape is
    exactly what `crew_confirm_config.confirm` leaves (and `rebind` copies):
    nothing a record merely claims is taken on trust."""
    target = crew_humanonly.target_key(machine_path)
    if record.get("layer") != "machine" or record.get("key") != KEY:
        return "it is not a machine-file guards.git.allow record"
    path = record.get("path")
    if not isinstance(path, str) or record.get("target") != target \
            or crew_humanonly.target_key(path) != target:
        return "it names another file"
    if normalise(record.get("value")) in (None, OFF):
        return "its value is not one the switch is confirmed to"
    created, expires, settled = (record.get(k) for k in ("created", "expires", "settled"))
    if not (_number(created) and _number(expires) and _number(settled)) \
            or not created <= expires <= created + crew_humanonly.PROPOSAL_TTL_SECONDS:
        return "its proposal window is missing or longer than a proposal's"
    confirmations = record.get("confirmations")
    if not isinstance(confirmations, list) or len(confirmations) != 2 \
            or not all(isinstance(c, dict) for c in confirmations):
        return "it does not carry exactly two confirmations"
    prompts, stamps = set(), []
    for confirmation in confirmations:
        prompt, stamp = confirmation.get("prompt"), confirmation.get("at")
        if confirmation.get("via") != crew_humanonly.USER_PROMPT \
                or not isinstance(prompt, str) or not prompt.strip() or not _number(stamp):
            return "a confirmation is not from a prompt the user typed"
        if not created <= stamp <= expires:
            return "a confirmation falls outside the proposal's window"
        prompts.add(prompt)
        stamps.append(stamp)
    if len(prompts) != 2:
        return "both confirmations came from one prompt"
    if settled < max(stamps):
        return "it was settled before its second confirmation"
    binding = record.get("binding")
    if not isinstance(binding, dict) or not all(
            isinstance(binding.get(k), (str if k == "appliedDigest" else int))
            for k in ("appliedDigest", "appliedSize", "appliedMtimeNs", "appliedChangeNs")):
        return "it does not record the file its write left"
    return None


def newest_receipt(store, machine_path):
    """`(record, why)`: the NEWEST settled record for guards.git.allow at the
    machine file when it is a whole applied double confirmation, else
    `(None, why)`. A later revocation, a newer record that is not whole, or a
    store that cannot be read whole backs nothing."""
    records, problems = crew_humanonly.all_records(store)
    if problems:
        return None, "the confirmation store could not be read: " + "; ".join(problems)
    target = crew_humanonly.target_key(machine_path)
    settled = [r for r in records
               if r.get("layer") == "machine" and r.get("target") == target
               and r.get("key") == KEY and r.get("state") in (crew_humanonly.APPLIED, "revoked")
               and _number(r.get("settled"))]
    if not settled:
        return None, "no double-confirmed change set it"
    newest = max(settled, key=lambda r: r["settled"])
    if newest.get("state") != crew_humanonly.APPLIED:
        return None, f"the last confirmed change ({newest.get('change_id')}) was revoked"
    problem = receipt_problem(newest, machine_path)
    if problem:
        return None, f"the last applied record ({newest.get('change_id')}) is not whole: {problem}"
    return newest, f"double-confirmed by {newest.get('change_id')}"


def _repo_veto(top, label_):
    """Why the repo file at top-level `top` vetoes the switch, or None. "off",
    a malformed value, and a file crew cannot read or parse all veto; a file
    that is absent, or silent (null), does not. When git cannot tell which
    `.crew/` a linked worktree reads, that is a veto too."""
    crew_dir, source, detail = crew_common.repo_config_dir(top)
    if source == crew_common.SOURCE_UNKNOWN:
        return f"which .crew/ {label_} reads could not be told ({detail}); read as a veto"
    state, value, _binding = read_layer(os.path.join(crew_dir, "config.json"))
    if state == UNREADABLE:
        return f"{label_}'s config {value}; read as a veto"
    if state != SET:
        return None
    repo_setting = normalise(value)
    if repo_setting == OFF:
        return f"vetoed by \"off\" in {label_}'s file"
    if repo_setting is None:
        return f"{label_}'s {KEY} = {value!r} is malformed; read as a veto"
    # A repo "all" or list never widens: ignored.
    return None


def _toplevel(directory):
    """git's top level for `directory`, or None when git cannot tell (git
    not on PATH included: resolved with `crew_common.resolve_tool`, never a
    bare name, L-1508)."""
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")}
    git = crew_common.resolve_tool("git")
    if git is None:
        return None
    try:
        proc = subprocess.run([git, "-C", directory, "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=10, check=False, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    top = proc.stdout.strip() if proc.returncode == 0 else ""
    return os.path.realpath(top) if top else None


def settings(root, global_path=None, store=None, targets=()):
    """`{"allow": OFF|ALL|frozenset, "why": str}` for `root`, and for every
    directory in `targets` a git command acts on (`git -C <dir>`): each one's
    repo file may veto too. `targets=None` means crew could not tell where a
    git command acts, which is `OFF`. Never raises: anything that cannot be
    told is `OFF` (the guards judge as before)."""
    try:
        if targets is None:
            return {"allow": OFF, "why": "which repository the git command acts on could "
                                         "not be told; read as off"}
        machine_path = global_path or crew_state.GLOBAL_CONFIG_PATH
        state, value, binding = read_layer(machine_path)
        if state == UNREADABLE:
            return {"allow": OFF, "why": f"the machine file {value}; read as off"}
        if state != SET:
            return {"allow": OFF, "why": "not set in the machine file"}
        setting = normalise(value)
        if setting is None:
            return {"allow": OFF, "why": f"{KEY} = {value!r} is not null, \"off\", \"all\" "
                                         "or a list of git subcommand names; read as off"}
        if setting == OFF:
            return {"allow": OFF, "why": "\"off\" in the machine file"}
        record, why = newest_receipt(store or crew_humanonly.store_dir(global_path),
                                     machine_path)
        detail = why
        if record is not None and _canonical(record.get("value")) != _canonical(value):
            detail = f"the last confirmed value was {_canonical(record.get('value'))}"
            record = None
        if record is not None and record.get("binding") != binding:
            detail = ("the machine file changed since that confirmation by a route other "
                      "than crew's config writer; confirm it again")
            record = None
        if record is None:
            return {"allow": OFF, "why": f"{KEY} = {json.dumps(value)} in the machine file, "
                                         f"not honoured: {detail}"}
        project = os.path.abspath(root)
        veto = _repo_veto(project, "the repo")
        if veto:
            return {"allow": OFF, "why": veto}
        seen = {os.path.normcase(os.path.realpath(project))}
        for target in targets:
            top = _toplevel(target)
            if top is None:
                return {"allow": OFF, "why": f"{target} is not a git work tree crew can read; "
                                             "read as off"}
            if os.path.normcase(top) in seen:
                continue
            seen.add(os.path.normcase(top))
            veto = _repo_veto(top, f"the target repo {top}")
            if veto:
                return {"allow": OFF, "why": veto}
        return {"allow": setting, "why": f"{label(setting)} in the machine file, {why}"}
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return {"allow": OFF, "why": f"could not be read ({type(exc).__name__}); read as off"}


def rebind(machine_path, before, global_path=None, now=None):
    """After crew's own config writer changed the machine file WITHOUT
    touching this key: when `before` (the receipt that backed the file as it
    was, `newest_receipt` read under the writer's lock) is not None, record a
    copy bound to the file as the write left it, so the owner's confirmation
    survives crew's own unrelated writes. Best effort; a failure leaves the
    switch off until it is confirmed again, never on."""
    if before is None:
        return False
    binding = file_binding(machine_path)
    if binding is None:
        return False
    stamp = time.time() if now is None else now
    record = dict(before, change_id=crew_humanonly.new_change_id(), settled=stamp,
                  binding=binding, reboundFrom=before.get("change_id"),
                  reason="re-bound after a crew config write that left guards.git.allow alone")
    try:
        crew_humanonly.write_record(crew_humanonly.store_dir(global_path), record)
    except OSError:
        return False
    return True


def backing(machine_path, global_path=None, store=None):
    """The receipt that backs the machine file's `guards.git.allow` as it
    is NOW (value and binding both), or None. `crew_config.write_global_config`
    reads it under its lock, before it writes, for `rebind`."""
    try:
        state, value, binding = read_layer(machine_path)
        if state != SET or normalise(value) in (None, OFF):
            return None
        record, _why = newest_receipt(store or crew_humanonly.store_dir(global_path),
                                      machine_path)
        if record is None or _canonical(record.get("value")) != _canonical(value) \
                or record.get("binding") != binding:
            return None
        return record
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return None


# --- the one reader: is a whole line only plain git ----------------------------------
#
# A FAIL-CLOSED ALLOWLIST (crew 1.3.82, PR #769 review round 4). Four review
# rounds each found a new way to build a git word at run time (`"$OPT"`, a
# brace expansion, `$'\x2d...'`, a PowerShell `(expr)`), so the reader no
# longer lists what is dangerous: it lists what is plain, and anything else is
# "cannot tell", which is never exempt. A line is exempt only when EVERY
# command on it is exactly `git` followed by words that are plain literals,
# joined by nothing but `;`, `&&`, `||`, a newline (and in bash `|` and `&`).
# The cloud guard (`cloud_guard.evaluate`, through `line_plan`) and the promote
# gate (`promote_exempt`) both ask this reader and nothing else, so they cannot
# read a line two ways again.

# Characters an UNQUOTED bash word may hold and still be the literal it looks
# like. Not `$` or a backtick (expansion), `*?[` (glob), `{}` (brace
# expansion; `@{...}` is let through below), `()<>|&;` (operators, split
# before here), `!`, `#`, `"`/`'` (handled), `\\` (handled) or non-ASCII.
_BASH_SAFE = frozenset(string.ascii_letters + string.digits + "_-./:=+,@%^")
# git's reflog / upstream spelling: `HEAD@{1}`, `@{u}`, `@{-1}`, with no `,`
# or `..` inside, so bash's brace expansion leaves it alone.
_REFLOG_RE = re.compile(r"@\{[A-Za-z0-9_.:+-]*\}")
# The operators that may join the commands of an exempt bash line.
_BASH_OPS = frozenset((None, "\n", ";", "&&", "||", "|", "&"))


def _bash_plain_word(raw):
    """Raw bash word `raw` (quotes kept, as `crew_guards._CommandSplitter`
    leaves it) as the literal bash passes, or None when it is not plainly
    one: any `$` (a variable, `$(...)`, `$'...'`, `$"..."`), a backtick
    outside single quotes, a glob, a brace expansion, a leading `~` (or one
    after `=` or `:`), or a character outside `_BASH_SAFE`. A single-quoted
    run is literal; a double-quoted run is literal when it holds no `$` or
    backtick; a backslash escapes one character."""
    out, pos, n = [], 0, len(raw)
    while pos < n:
        char = raw[pos]
        if char == "'":
            end = raw.find("'", pos + 1)
            if end == -1:
                return None
            out.append(raw[pos + 1:end])
            pos = end + 1
        elif char == '"':
            end, buf = pos + 1, []
            while end < n and raw[end] != '"':
                here = raw[end]
                if here == "\\" and raw[end + 1:end + 2] in ("$", "`", '"', "\\"):
                    buf.append(raw[end + 1])
                    end += 2
                elif here == "\\" and raw[end + 1:end + 2] == "\n":
                    end += 2
                elif here in "$`":
                    return None
                else:
                    buf.append(here)
                    end += 1
            if end >= n:
                return None
            out.append("".join(buf))
            pos = end + 1
        elif char == "\\":
            if pos + 1 >= n or raw[pos + 1] == "\n":
                return None
            out.append(raw[pos + 1])
            pos += 2
        elif char == "@" and raw.startswith("@{", pos):
            match = _REFLOG_RE.match(raw, pos)
            if not match or ".." in match.group(0):
                return None
            out.append(match.group(0))
            pos = match.end()
        elif char == "~":
            if pos == 0 or raw[pos - 1] in "=:":
                return None
            out.append(char)
            pos += 1
        elif char in _BASH_SAFE:
            out.append(char)
            pos += 1
        else:
            return None
    return "".join(out)


def _bash_commands(text):
    """Every simple command of bash `text` as plain literal words, or None
    when crew cannot read the line as only such commands: it does not split
    whole, it has a substitution anywhere (`$(...)`, a backtick, `<(...)`,
    one in an unquoted heredoc body), a subshell or group, an operator outside
    `_BASH_OPS`, an unquoted heredoc body with `$`, a backtick or `\\`, or a
    word or here-string that is not plain (`_bash_plain_word`)."""
    import crew_guards  # pylint: disable=import-outside-toplevel
    splitter = crew_guards._CommandSplitter(text)  # pylint: disable=protected-access
    try:
        commands, subs = splitter.split()
    except crew_guards._Unsure:  # pylint: disable=protected-access
        return None
    if subs:
        return None
    out = []
    for raw_words, meta in zip(commands, splitter.metas):
        if meta.get("nest") != 1 or meta.get("before") not in _BASH_OPS \
                or meta.get("after") not in _BASH_OPS:
            return None
        for body, quoted in meta.get("bodies", ()):
            if not quoted and any(c in body for c in "$`\\"):
                return None
        if any(_bash_plain_word(w) is None for w in meta.get("here", ())):
            return None
        words = [_bash_plain_word(w) for w in raw_words]
        if any(w is None for w in words):
            return None
        if any(_bash_redirect_problem(r, words) for r in meta.get("redirs", ())):
            return None
        out.append(words)
    if splitter.metas and (splitter.metas[0].get("before") not in (None, "\n")
                           or splitter.metas[-1].get("after") in ("&&", "||", "|")):
        return None  # `&& git x`, `git x &&`: bash refuses the line, so it runs nothing
    for left, right in zip(splitter.metas, splitter.metas[1:]):
        if left.get("after") in ("&&", "||", "|") and \
                right.get("before") not in (left.get("after"), "\n"):
            return None  # `git x ||& git y`: an empty command after `||`, a syntax error
    return out


def _subcommand_at(words):
    """The index in `words` (`git` first) of the subcommand word."""
    return 1 + _global_split(list(words[1:]))[1]


def _bash_redirect_problem(redir, words):
    """Why a bash redirection keeps a git line from being exempt, or None.
    A FAIL-CLOSED allowlist (PR #769 review round 5: `>&-` closes stdout and
    hands the rest of its word to git as an argument, and an fd prefix before
    the subcommand hid `-c`): only, AFTER the subcommand, `>` / `>>` to a
    plain literal file not starting with `-`, `N>&M` between plain digit
    descriptors, and a heredoc or here-string (whose body the reader checks).
    Anything else -- `<`, `<&`, `<>`, `>|`, `&>`, `>&-`, `>& file`, a `{var}`
    descriptor, a redirection with no target, or any redirection between
    `git` and the subcommand -- is "cannot tell"."""
    fd, op, target = redir.get("fd") or "", redir.get("op"), redir.get("target")
    if redir.get("at", 0) <= _subcommand_at(words):
        return "a redirection before the subcommand"
    if fd and not (fd.isdigit() and fd.isascii()):
        return "a {var} descriptor"
    if op in ("<<", "<<-"):
        return None
    if target is None:
        return "a redirection with no target"
    if op == "<<<":
        return None
    if op in (">", ">>"):
        plain = _bash_plain_word(target)
        return None if plain and not plain.startswith("-") else "a target that is not plain"
    if op == ">&" and target.isdigit() and target.isascii():
        return None
    return f"a {op} redirection"


# Characters an UNQUOTED PowerShell word may hold. Not `$` (a variable or
# `$(...)`), `@` at a word's start (a splat, `@(...)`, `@{...}`), `(){}[]`
# (an expression, a script block, a type or glob), `*?` (a glob on Linux and
# macOS), `,` (an array), `<>|&;#!"'` (handled or operators), a backtick
# (handled) or non-ASCII (PowerShell reads curly quotes as quotes and en and
# em dashes as dashes).
_PS_SAFE = frozenset(string.ascii_letters + string.digits + "_-./:=+\\^%~@")
# Curly quotes, which PowerShell reads as `'` and `"` (measured, pwsh 7): a
# reader that took them as text would see one word where PowerShell sees three.
_PS_CURLY = "‘’‚‛“”„"
# `%NAME%`: expanded at run time after `--%`, and by cmd.exe when git is a
# `.cmd` shim -- quoted or not (crew 1.3.75 review round 3).
_PS_PERCENT_RE = re.compile(r"%[^%\s]+%")
# A redirection at a word's start: `>out`, `2>>log`, `2>&1`, `*>&1`. Only
# `n>&1` merges: `1>&2` / `2>&2` are "reserved for future use", a parse error
# (measured, pwsh 7; review round 5), so they do not match and the `&` is
# then refused.
_PS_REDIRECT_RE = re.compile(r"(?:[1-6*])?>>?(?:&1)?")


def _ps_commands(text):  # pylint: disable=too-many-branches,too-many-statements
    """Every statement of PowerShell `text` as plain literal words, or None
    when crew cannot read the line as only such statements. Plain: a bare
    word of `_PS_SAFE` characters (no leading `~`, `@` only alone or inside a
    word), a whole `'...'` or `"..."` word (a double-quoted one holding no
    `$`; a quote may not start or end mid-word), a here-string, or a
    backtick escaping a character that is not a letter or digit (`` `u{2d} ``
    is a `-`). Joined only by `;`, a newline, `&&` or `||`; a redirection
    (`2>&1`, `> out`) is dropped with its target. Anything else -- a pipe, a
    single `&`, `(`, `$(`, `@(`, a script block, a curly quote, `--%` or a
    `%NAME%` -- is None."""
    if any(c in text for c in _PS_CURLY):
        return None
    statements, words, word, redirs, at = [], [], [], [], []
    state = {"started": False, "target": False, "closed": False, "join": False}
    i, n = 0, len(text)

    def end_word():
        if state["started"]:
            if state["target"]:
                state["target"] = False
            else:
                words.append("".join(word))
        word.clear()
        state["started"] = state["closed"] = False

    def end_statement():
        end_word()
        if state["target"]:
            return False
        if words:
            statements.append(list(words))
            at.append(list(redirs))
            state["join"] = False
        words.clear()
        redirs.clear()
        return True

    while i < n:
        c = text[i]
        if state["closed"] and c not in " \t;\n&|":
            return None  # `'a'b`: a quote ending mid-word
        if text.startswith("@'", i) or text.startswith('@"', i):
            quote = text[i + 1]
            if state["started"] or not words or text[i + 2:i + 3] != "\n":
                return None
            close = text.find("\n" + quote + "@", i + 2)
            if close == -1:
                return None
            body = text[i + 3:close]
            if quote == '"' and ("$" in body or "`" in body):
                return None
            word.append(body)
            state["started"] = state["closed"] = True
            i = close + 3
            continue
        if c in "'\"":
            if state["started"]:
                return None  # `a'b'`: a quote starting mid-word
            if not words:
                return None  # `"git" status`: a quoted first word is a string, not a command
            end, buf = i + 1, []
            while True:
                if end >= n:
                    return None
                here = text[end]
                if here == c and text[end + 1:end + 2] == c:
                    buf.append(c)
                    end += 2
                elif here == c:
                    break
                elif c == '"' and here == "$":
                    return None
                elif c == '"' and here == "`":
                    if end + 1 >= n or text[end + 1].isalnum():
                        return None
                    buf.append(text[end + 1])
                    end += 2
                else:
                    buf.append(here)
                    end += 1
            word.append("".join(buf))
            state["started"] = state["closed"] = True
            i = end + 1
            continue
        if c == "`":
            if text[i + 1:i + 2] == "\n":
                if state["started"]:
                    return None  # `a`<newline>b`: one word holding a newline (measured, pwsh 7)
                end_word()
                i += 2
                continue
            if i + 1 >= n or text[i + 1].isalnum():
                return None
            word.append(text[i + 1])
            state["started"] = True
            i += 2
            continue
        if c in " \t":
            end_word()
            i += 1
            continue
        if c in ";\n" or text.startswith("&&", i) or text.startswith("||", i):
            chain = text.startswith(("&&", "||"), i)
            count = len(statements)
            if not end_statement() or (chain and len(statements) == count):
                return None  # `&& git x`, `git x; && ...`: a parse error, runs nothing
            state["join"] = state["join"] or chain
            i += 2 if chain else 1
            continue
        if c == "#" and not state["started"]:
            while i < n and text[i] != "\n":
                i += 1
            continue
        if not state["started"]:
            match = _PS_REDIRECT_RE.match(text, i)
            if match and ">" in match.group(0):
                if state["target"]:
                    return None
                state["target"] = "&" not in match.group(0)
                redirs.append(len(words))
                i = match.end()
                continue
            if c == "~":
                return None
            if c == "@":
                return None  # a splat, `@(...)`, `@{...}`; a bare `@` is a parse error
        if c in _PS_SAFE:
            word.append(c)
            state["started"] = True
            i += 1
            continue
        return None
    if not end_statement() or state["join"]:
        return None  # `git x &&`: a parse error, runs nothing
    for statement, places in zip(statements, at):
        for item in statement:
            if item == "--%" or _PS_PERCENT_RE.search(item):
                return None
        # Review round 5: a redirection between `git` and its subcommand is
        # never exempt, in PowerShell as in bash (fail closed; PowerShell
        # drops it, but crew does not lean on that).
        if any(place <= _subcommand_at(statement) for place in places):
            return None
    return statements


def plain_commands(command, shell):
    """The simple commands of `command` read as `shell`, every word a plain
    literal, or None (cannot tell: never exempt)."""
    if not isinstance(command, str) or not command.strip():
        return None
    if shell == "powershell":
        return _ps_commands(command.replace("\r\n", "\n"))
    return _bash_commands(command)


def line_git_commands(command, shell):
    """The argument lists (words after `git`) of `command` when EVERY command
    it runs is exactly `git` with plain literal words and nothing `hold`
    withholds, else None."""
    commands = plain_commands(command, shell)
    if not commands:
        return None
    out = []
    for words in commands:
        if not words or words[0] != "git":
            return None
        if hold(words[1:]) is not None:
            return None
        out.append(words[1:])
    return out


def line_targets(git_commands, base):
    """Every `-C` target of a line's git commands, resolved from `base` (the
    directory the line runs in), or None when one cannot be told."""
    out = []
    for args in git_commands:
        dirs = target_dirs(args)
        if dirs is UNSEEN:
            return None
        if dirs:
            out.append(resolve_target(base, dirs))
    return tuple(out)


def line_exempt(command, shell, setting):
    """True when EVERY command `command` runs is a plain git command
    (`line_git_commands`) whose subcommand `setting` lets through."""
    if setting == OFF or setting is None:
        return False
    commands = line_git_commands(command, shell)
    if not commands:
        return False
    for args in commands:
        if not allows(setting, subcommand(args)):
            return False
    return True


def line_plan(command, shell, root, base, global_path=None, store=None):
    """`{"allow": setting, "subs": frozenset}` for the cloud guard: the
    setting in force for `command`'s line (its `-C` targets' repo files read
    too, from `base`) and the subcommands of its git commands, when the line
    is `line_exempt`; else `{"allow": OFF, "subs": frozenset()}`. Never
    raises."""
    none = {"allow": OFF, "subs": frozenset()}
    try:
        commands = line_git_commands(command, shell)
        if not commands:
            return none
        setting = settings(root, global_path, store, line_targets(commands, base))["allow"]
        if not line_exempt(command, shell, setting):
            return none
        return {"allow": setting, "subs": frozenset(subcommand(a) for a in commands)}
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return none


def finding_exempt(plan, scope):
    """True when the cloud-guard git finding with scope dict `scope` is let
    through by `plan` (`line_plan`): its subcommand is one of the line's
    plain git commands and the setting allows it. A finding with no
    `SCOPE_KEY` (an `xargs git` finding carries none) never is."""
    if not isinstance(plan, dict) or not isinstance(scope, dict) or SCOPE_KEY not in scope:
        return False
    sub = scope[SCOPE_KEY]
    return sub in plan.get("subs", ()) and allows(plan.get("allow"), sub)


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
        commands = line_git_commands(command, shell)
        if not commands:
            return False
        setting = settings(root, global_path, store, line_targets(commands, root))["allow"]
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
