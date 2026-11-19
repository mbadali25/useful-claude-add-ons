"""The Never lane's command-text tripwire, REPORT-ONLY (R-33).

    python3 crew_never.py judge [--shell bash|powershell] -- "<command>"
    python3 crew_never.py redact            (stdin -> stdout)
    python3 crew_never.py shapes

Two Never rows of the revision-3 plan's table (4.3) are about the text of a
command a model runs. This module recognises them and nothing else:

- `skip-hooks-or-signing`: a git command that skips hooks or signing
  (`--no-verify`, `commit -n`, `--no-gpg-sign`, `core.hooksPath`, `HUSKY=0`
  and the rest of the closed SHAPES list);
- `write-secret-plaintext`: a command whose text carries a secret-shaped value
  (`crew_reference.SECRET_PATTERNS`, the `bearer-token` shape owned here, or
  the literal value of a secret-named environment variable).

It also holds `redact`, the one shared redactor later publication points
(receipts, logs, tracker posts, committed evidence) are to call.

REPORT-ONLY: nothing in the plugin imports this module, and a test fails if
anything does. It emits the operation names as strings and never imports the
policy table; the test binds each name to a Never row there. A verdict refuses
nothing until a later ticket wires it (R-33b reports it, R-35 enforces it).

Verdicts are `hit`, `clear` and `could-not-tell`; the secret scan only ever
says `hit` or `clear`. Any `hit` wins, then any `could-not-tell`, else
`clear`: an unknown never collapses into the safe-looking value. A finding
names its rule, its operation and where it stood (pass, command, word) -- never
the matched value.

Reading a command takes two passes over one word judge:

1. plain: when `crew_gitallow.plain_commands` reads the text as simple commands
   with literal words, those words are judged and the answer is authoritative
   (`git commit -m "never use --no-verify"` is clear: the flag is the message);
2. raw: every chain, pipe, heredoc and expansion. Quote-blind on purpose: cut
   at `&&` `||` `;` `|` `&` and newline, split on whitespace, strip quotes and
   brackets from each word. It over-reads (a chained commit whose message names
   a shape is a known false positive) and says `could-not-tell` when a judged
   git word holds an expansion.

It is a tripwire, not a boundary (plan 4.0, layer 1). It does not see git run
through a wrapper the command head does not list (`bash -c`, `xargs`, `ssh`,
`eval` in a plain command), a script file, an alias, a hooks path set in a
repo config file by a file write, or an MCP server; a token format not on the
list, or a bearer token with no digit outside an `Authorization` key, passes.
Crew's own coordination push runs inside crew's process (`crew_coord.run_git`)
and is never a hook payload, so it never reaches this module: that, not a
miss, is why it is unaffected.

Exit codes: 0 for every judgement (report-only) and for `redact` / `shapes`,
2 for a usage error.
"""
import argparse
import json
import os
import re
import sys

import crew_gitallow
import crew_reference
import env_guard

REPORT_ONLY = True

HIT = "hit"
CLEAR = "clear"
COULD_NOT_TELL = "could-not-tell"
NOT_A_COMMAND = "not-a-command"

# Operation names in the policy table's Never lane, by name only.
SKIP_HOOKS = "skip-hooks-or-signing"
WRITE_SECRET = "write-secret-plaintext"
OPERATIONS_EMITTED = (SKIP_HOOKS, WRITE_SECRET)

# --- the closed shape list -----------------------------------------------------------------

SHAPES = (
    ("no-verify", SKIP_HOOKS, "--no-verify (any abbreviation git accepts) on commit, push, "
                              "merge, pull, am, rebase"),
    ("commit-n", SKIP_HOOKS, "-n on commit, bundled or alone (never push -n, a dry run)"),
    ("no-gpg-sign", SKIP_HOOKS, "--no-gpg-sign on commit, merge, pull, rebase, am, cherry-pick, "
                                "revert, commit-tree"),
    ("tag-no-sign", SKIP_HOOKS, "tag --no-sign"),
    ("push-no-signed", SKIP_HOOKS, "push --no-signed or --signed=no|false"),
    ("config-hookspath", SKIP_HOOKS, "a global -c / --config-env setting core.hooksPath"),
    ("config-gpgsign-off", SKIP_HOOKS, "a global -c setting commit|tag|push.gpgSign to a false "
                                       "value"),
    ("config-write-hookspath", SKIP_HOOKS, "a git config write of core.hooksPath"),
    ("config-write-gpgsign-off", SKIP_HOOKS, "a git config write of commit|tag|push.gpgSign to a "
                                             "false value"),
    ("env-husky", SKIP_HOOKS, "HUSKY=0 before a git command"),
    ("env-husky-skip-hooks", SKIP_HOOKS, "HUSKY_SKIP_HOOKS=1 before a git command"),
    ("env-lefthook", SKIP_HOOKS, "LEFTHOOK=0 before a git command"),
    ("env-skip", SKIP_HOOKS, "SKIP=<anything> (pre-commit) before a git command"),
    ("env-git-config-key", SKIP_HOOKS, "GIT_CONFIG_KEY_<n> naming core.hooksPath or a "
                                       "*.gpgSign key"),
    ("bearer-token", WRITE_SECRET, "the word bearer, then 8+ token characters holding a digit "
                                   "(any key, or none)"),
    ("env-value", WRITE_SECRET, "the literal value (8+ chars) of a secret-named environment "
                                "variable"),
)
SHAPE_NAMES = frozenset(name for name, _, _ in SHAPES)

# (long option, shape, the subcommands it skips a hook or signing on)
LONG_SHAPES = (
    ("--no-verify", "no-verify", ("commit", "push", "merge", "pull", "am", "rebase")),
    ("--no-gpg-sign", "no-gpg-sign", ("commit", "merge", "pull", "rebase", "am", "cherry-pick",
                                      "revert", "commit-tree")),
    ("--no-sign", "tag-no-sign", ("tag",)),
    ("--no-signed", "push-no-signed", ("push",)),
)


class _Sub:  # pylint: disable=too-few-public-methods
    """A subcommand's value-taking options: the word after one is its value
    and is never judged. `ends` are short letters with an optional attached
    value: they end a bundle without taking the next word."""

    def __init__(self, short="", long=(), ends=""):
        self.short = frozenset(short)
        self.long = frozenset(long)
        self.ends = frozenset(ends)


_NO_VALUES = _Sub()
SUBCOMMANDS = {
    "commit": _Sub("mFCct", ("--message", "--file", "--reuse-message", "--reedit-message",
                             "--template", "--author", "--date", "--fixup", "--squash",
                             "--cleanup", "--trailer", "--pathspec-from-file"), ends="Su"),
    "push": _Sub("o", ("--push-option", "--repo", "--receive-pack", "--exec")),
    "merge": _Sub("mFsX", ("--message", "--file", "--strategy", "--strategy-option",
                           "--cleanup", "--into-name"), ends="S"),
    "pull": _Sub("sX", ("--strategy", "--strategy-option", "--depth", "--upload-pack"),
                 ends="S"),
    "rebase": _Sub("sXx", ("--onto", "--strategy", "--strategy-option", "--exec"), ends="S"),
    "am": _Sub("", ("--directory", "--exclude", "--include"), ends="S"),
    "cherry-pick": _Sub("mX", ("--mainline", "--strategy", "--strategy-option"), ends="S"),
    "revert": _Sub("mX", ("--mainline", "--strategy", "--strategy-option"), ends="S"),
    "tag": _Sub("mFu", ("--message", "--file", "--local-user", "--cleanup")),
    "commit-tree": _Sub("pmF", (), ends="S"),
}

GPG_KEYS = frozenset(("commit.gpgsign", "tag.gpgsign", "push.gpgsign"))
FALSE_VALUES = frozenset(("false", "no", "off", "0", ""))
_CONFIG_VALUE_OPTS = frozenset(("-f", "--file", "--blob", "--type", "--default", "--comment",
                                "--value"))

# (name, the values that skip, shape); None = any non-empty value.
ENV_SHAPES = (
    ("HUSKY", ("0",), "env-husky"),
    ("HUSKY_SKIP_HOOKS", ("1",), "env-husky-skip-hooks"),
    ("LEFTHOOK", ("0",), "env-lefthook"),
    ("SKIP", None, "env-skip"),
)
_ENV_NAMES = frozenset(name for name, _, _ in ENV_SHAPES)
_GIT_CONFIG_KEY_RE = re.compile(r"^GIT_CONFIG_KEY_\d+$")

# The command head: assignments split off, this closed prefix list skipped.
HEAD_PREFIXES = frozenset(("env", "sudo", "command", "time", "then", "do", "else", "!"))
_GIT_WORDS = frozenset(("git", "git.exe"))
_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
_PS_ASSIGN_RE = re.compile(r"^\$env:([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S | re.I)
_PS_NAME_RE = re.compile(r"^\$env:([A-Za-z_][A-Za-z0-9_]*)$", re.I)
_EVAL_WORDS = frozenset(("eval", "iex", "invoke-expression"))

# The raw pass: separators wherever they stand, quotes and brackets stripped.
_SEPARATORS_RE = re.compile(r"&&|\|\||[;|&\n\r]")
_STRIP = "\"'(){}"

# --- the secret shapes -----------------------------------------------------------------------

# A bearer token whose key is not `Authorization`, or that has no key at all
# (`curl --oauth2-bearer <t>`). Placeholders (`$TOKEN`, `<token>`, `%TOKEN%`,
# `${TOKEN}`) are clear because those characters are not token characters; the
# digit lookahead keeps prose (`a Bearer credential`) and masks clear.
BEARER_RE = re.compile(r"(?i)\bbearer\s+(?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{8,}")
ENV_VALUE_MIN = 8


def _patterns():
    """(name, pattern) for every secret shape the text is scanned for."""
    return tuple(crew_reference.SECRET_PATTERNS) + (("bearer-token", BEARER_RE),)


def _env_values(env):
    """(name, value) for each secret-named variable of `env` worth matching,
    longest value first."""
    source = os.environ if env is None else env
    pairs = [(name, value) for name, value in source.items()
             if isinstance(name, str) and isinstance(value, str)
             and len(value) >= ENV_VALUE_MIN and env_guard.is_secret_name(name)]
    return sorted(pairs, key=lambda pair: (-len(pair[1]), pair[0]))


# --- findings --------------------------------------------------------------------------------

def _finding(verdict, rule, operation, **where):
    out = {"verdict": verdict, "rule": rule, "operation": operation}
    out.update(where)
    return out


def _overall(findings):
    verdicts = {f["verdict"] for f in findings}
    if HIT in verdicts:
        return HIT
    if COULD_NOT_TELL in verdicts:
        return COULD_NOT_TELL
    return CLEAR


# --- the word judge --------------------------------------------------------------------------

def _long_hit(word, option):
    """Any abbreviation git accepts for a long option (`--no-ver`)."""
    return crew_gitallow._option_hit(word, option)  # pylint: disable=protected-access


def _short_letters(word, spec):
    """(the bundle carries `n`, the next word is this bundle's value) for a
    single-dash word, read left to right: a value-taking letter takes the rest
    of the word, or the next word when nothing is left; an `ends` letter stops
    the read. So `-anm x` carries n, and `-mno`, `-Sn` do not."""
    carries_n = False
    for index, letter in enumerate(word[1:], 1):
        if letter in spec.short:
            return carries_n, index == len(word) - 1
        if letter in spec.ends:
            break
        if letter == "n":
            carries_n = True
    return carries_n, False


def _judge_env(pairs, out, where):
    """The env-prefix check over (name, value) assignments."""
    for name, value in pairs:
        upper = name.upper()
        value = value.strip(_STRIP)
        if upper in _ENV_NAMES or upper.startswith("GIT_CONFIG_"):
            if "$" in value or "`" in value:
                out.append(_finding(COULD_NOT_TELL, "env-expansion", SKIP_HOOKS, **where))
                continue
        for env_name, values, shape in ENV_SHAPES:
            if upper == env_name and (value in values if values else value != ""):
                out.append(_finding(HIT, shape, SKIP_HOOKS, **where))
        if _GIT_CONFIG_KEY_RE.match(upper):
            key = value.lower()
            if key == "core.hookspath" or key.endswith(".gpgsign"):
                out.append(_finding(HIT, "env-git-config-key", SKIP_HOOKS, **where))


def _judge_config_pair(option, value, out, where):
    """A global `-c key=value` or `--config-env key=ENVVAR`."""
    key, sep, setting = value.partition("=")
    key = key.lower()
    if key == "core.hookspath":
        out.append(_finding(HIT, "config-hookspath", SKIP_HOOKS, **where))
    elif key in GPG_KEYS and option == "--config-env":
        # The value comes from an environment variable: unknown, not clear.
        out.append(_finding(COULD_NOT_TELL, "config-gpgsign-off", SKIP_HOOKS, **where))
    elif key in GPG_KEYS and sep and setting.lower() in FALSE_VALUES:
        out.append(_finding(HIT, "config-gpgsign-off", SKIP_HOOKS, **where))


def _judge_globals(words, out, where):
    """The judged global words: every `-c` / `--config-env` value."""
    judged, index = [], 0
    while index < len(words):
        word = words[index]
        if word.startswith("--config-env="):
            value = word.split("=", 1)[1]
            judged.append(value)
            _judge_config_pair("--config-env", value, out, dict(where, word=index))
        elif word in ("-c", "--config-env") and index + 1 < len(words):
            value = words[index + 1]
            judged.append(value)
            _judge_config_pair(word, value, out, dict(where, word=index + 1))
        index += 2 if word in crew_gitallow._GIT_VALUE_OPTS else 1  # pylint: disable=protected-access
    return judged


def _config_write(rest, out, where):
    """`git config <rest>`: a write of core.hooksPath, or of a gpgSign key to
    a false value. A read is clear; so is an unset (it restores the default)."""
    if crew_gitallow._config_is_read(rest):  # pylint: disable=protected-access
        return
    positionals, unset, index = [], False, 0
    while index < len(rest):
        word = rest[index]
        if word == "--":
            positionals.extend(rest[index + 1:])
            break
        if word.startswith("-") and word != "-":
            name = word.split("=", 1)[0]
            unset = unset or name in ("--unset", "--unset-all")
            if name in _CONFIG_VALUE_OPTS and "=" not in word:
                index += 1
        else:
            positionals.append(word)
        index += 1
    if positionals and positionals[0] in ("set", "unset"):
        unset = unset or positionals[0] == "unset"
        positionals = positionals[1:]
    if unset or not positionals:
        return
    key = positionals[0].lower()
    if key == "core.hookspath":
        out.append(_finding(HIT, "config-write-hookspath", SKIP_HOOKS, **where))
    elif key in GPG_KEYS and len(positionals) > 1 and positionals[1].lower() in FALSE_VALUES:
        out.append(_finding(HIT, "config-write-gpgsign-off", SKIP_HOOKS, **where))


def _judge_git(git_words, out, where):
    """Judge the words after `git`; return the words it judged (option words,
    positionals, global config values -- never a skipped option value)."""
    globals_, sub_index = crew_gitallow._global_split(git_words)  # pylint: disable=protected-access
    judged = _judge_globals(globals_, out, where)
    if sub_index >= len(git_words):
        return judged
    sub = git_words[sub_index]
    judged.append(sub)
    rest = git_words[sub_index + 1:]
    base = sub_index + 1
    if sub == "config":
        judged.extend(rest)
        _config_write(rest, out, dict(where, word=sub_index))
        return judged
    spec = SUBCOMMANDS.get(sub, _NO_VALUES)
    index = 0
    while index < len(rest):
        word = rest[index]
        if word == "--":
            break
        skip = False
        at = dict(where, word=base + index)
        if word.startswith("--"):
            name = word.split("=", 1)[0]
            skip = "=" not in word and name in spec.long
            for option, shape, subs in LONG_SHAPES:
                if sub in subs and _long_hit(word, option):
                    out.append(_finding(HIT, shape, SKIP_HOOKS, **at))
            if sub == "push" and "=" in word and _long_hit(name, "--signed") \
                    and word.split("=", 1)[1].lower() in ("no", "false"):
                out.append(_finding(HIT, "push-no-signed", SKIP_HOOKS, **at))
        elif word.startswith("-") and word != "-":
            carries_n, skip = _short_letters(word, spec)
            if sub == "commit" and carries_n:
                out.append(_finding(HIT, "commit-n", SKIP_HOOKS, **at))
        judged.append(word)
        index += 2 if skip else 1
    return judged


def _command_head(words):
    """(assignments, the git words, or None when it is not a git command)."""
    pairs, index = [], 0
    while index < len(words):
        word = words[index]
        match = _ASSIGN_RE.match(word)
        if match:
            pairs.append((match.group(1), match.group(2)))
            index += 1
            continue
        if word in HEAD_PREFIXES:
            index += 1
            continue
        break
    if index < len(words) and words[index] in _GIT_WORDS:
        return pairs, words[index + 1:]
    return pairs, None


# --- the two passes --------------------------------------------------------------------------

def _plain_pass(commands):
    out = []
    heads = [_command_head(words) for words in commands]
    if any(git is not None for _, git in heads):
        for number, (pairs, _) in enumerate(heads):
            _judge_env(pairs, out, {"pass": "plain", "command": number})
    for number, (_, git) in enumerate(heads):
        if git is not None:
            _judge_git(git, out, {"pass": "plain", "command": number})
    return out


def _raw_segments(text):
    for segment in _SEPARATORS_RE.split(text):
        words = [word.strip(_STRIP) for word in segment.split()]
        words = [word for word in words if word]
        if words:
            yield words


def _assignment_segment(words):
    """(name, value) pairs when the segment only assigns, else None."""
    if len(words) >= 2 and words[1] == "=" and _PS_NAME_RE.match(words[0]):
        return [(_PS_NAME_RE.match(words[0]).group(1), " ".join(words[2:]))]
    body = words[1:] if words[0] == "export" else words
    pairs = []
    for word in body:
        match = _ASSIGN_RE.match(word) or _PS_ASSIGN_RE.match(word)
        if not match:
            return None
        pairs.append((match.group(1), match.group(2)))
    return pairs or None


def _raw_pass(text):
    out = []
    segments = list(_raw_segments(text))
    heads = [_command_head(words) for words in segments]
    if any(git is not None for _, git in heads):
        for number, (words, (pairs, git)) in enumerate(zip(segments, heads)):
            where = {"pass": "raw", "command": number}
            if git is not None:
                _judge_env(pairs, out, where)
            else:
                _judge_env(_assignment_segment(words) or [], out, where)
    expansion = False
    for number, (_, git) in enumerate(heads):
        if git is not None:
            judged = _judge_git(git, out, {"pass": "raw", "command": number})
            expansion = expansion or any("$" in word or "`" in word for word in judged)
    every = [word.lower() for words in segments for word in words]
    if any(word in _GIT_WORDS for word in every) and any(word in _EVAL_WORDS for word in every):
        expansion = True
    if expansion and not any(f["verdict"] == HIT for f in out):
        out.append(_finding(COULD_NOT_TELL, "expansion", SKIP_HOOKS, **{"pass": "raw"}))
    return out


def _hook_findings(command, shell):
    commands = crew_gitallow.plain_commands(command, shell)
    if commands is None:
        return _raw_pass(command)
    return _plain_pass(commands)


def _secret_findings(text, env):
    out = []
    for name, pattern in _patterns():
        match = pattern.search(text)
        if match:
            out.append(_finding(HIT, name, WRITE_SECRET))
    if any(value in text for _, value in _env_values(env)):
        out.append(_finding(HIT, "env-value", WRITE_SECRET))
    return out


# --- the entry points ------------------------------------------------------------------------

def _result(findings):
    return {"verdict": _overall(findings), "report_only": True,
            "operations": sorted({f["operation"] for f in findings
                                  if f["verdict"] != CLEAR}),
            "findings": findings}


def judge(command, shell="bash", env=None):
    """Judge one command text as `shell` (`bash` or `powershell`). `env` is
    the environment whose secret values are looked for (default: this
    process's). Returns {verdict, report_only, operations, findings}."""
    if not isinstance(command, str) or shell not in ("bash", "powershell"):
        return _result([_finding(COULD_NOT_TELL, "unreadable-input", SKIP_HOOKS)])
    return _result(_hook_findings(command, shell) + _secret_findings(command, env))


_SHELLS = {"Bash": "bash", "PowerShell": "powershell"}


def judge_payload(payload, env=None):
    """Judge a PreToolUse-shaped payload. A tool other than Bash or
    PowerShell is `not-a-command`; a command payload without a command string
    is `could-not-tell`."""
    payload = payload if isinstance(payload, dict) else {}
    shell = _SHELLS.get(payload.get("tool_name"))
    if shell is None:
        return {"verdict": NOT_A_COMMAND, "report_only": True, "operations": [],
                "findings": []}
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    return judge(command, shell, env)


def redact(text, env=None):
    """(text, count): every secret-shaped match replaced with
    `[redacted:<rule>]` and every secret-named variable's value with
    `[redacted:env:<NAME>]`, longest value first. Idempotent; a secret NAME
    (`$GITHUB_TOKEN`) is left alone. None or empty input is ("", 0)."""
    if not isinstance(text, str) or not text:
        return "", 0
    count = 0
    for name, value in _env_values(env):
        found = text.count(value)
        if found:
            text = text.replace(value, f"[redacted:env:{name}]")
            count += found
    for name, pattern in _patterns():
        text, found = pattern.subn(f"[redacted:{name}]", text)
        count += found
    return text, count


def _main(argv):
    parser = argparse.ArgumentParser(prog="crew_never.py", description=__doc__.split("\n\n", maxsplit=1)[0])
    sub = parser.add_subparsers(dest="action", required=True)
    one = sub.add_parser("judge")
    one.add_argument("--shell", choices=("bash", "powershell"), default="bash")
    one.add_argument("command", nargs="+")
    sub.add_parser("redact")
    sub.add_parser("shapes")
    args = parser.parse_args(argv)
    if args.action == "judge":
        print(json.dumps(judge(" ".join(args.command), args.shell), indent=2))
    elif args.action == "redact":
        print(redact(sys.stdin.read())[0], end="")
    else:
        for name, operation, what in SHAPES:
            print(f"{name}\t{operation}\t{what}")
        for name, _ in crew_reference.SECRET_PATTERNS:
            print(f"{name}\t{WRITE_SECRET}\tcrew_reference.SECRET_PATTERNS")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
