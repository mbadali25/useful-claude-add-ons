"""PreToolUse cloud/destructive guard for the Bash and PowerShell tools.

Reads the hook payload on stdin and answers with the documented PreToolUse
`permissionDecision` JSON on stdout -- `deny` or `ask`, each with a reason that
names the rule -- or prints nothing, which leaves Claude Code's own permission
system to decide. It never prints `allow`: that value skips the user's own
permission prompts, and a guard that recognises nothing has no business
granting what it did not judge.

OFF BY DEFAULT. `guards.cloudGuard` is `off` unless a config layer says
otherwise (see `crew_guards.CLOUD_GUARD_NAMES`), and at `off` this script reads
that one key and exits. CLAUDE.md's rule for a hook that can block.

WHAT IT RECOGNISES, and which existing `guards.*` key decides each:

    terraform/tofu/terragrunt apply|destroy        guards.terraformApply
    git push --force|-f|--force-with-lease|+ref     guards.forcePush
    gh pr merge --admin                             guards.adminMerge
    aws delete-*/terminate-*/purge-*, s3 rm|rb,
      s3 sync --delete; az ... delete|purge;
      Remove-Az*                                    guards.cloudDestructive
    DROP / TRUNCATE handed to psql, mysql, mariadb,
      sqlcmd, sqlite3, Invoke-Sqlcmd                guards.sqlDestructive
    a SQL client aimed at production.databases      guards.prodDatabase
    ssh/plink/scp aimed at production.hosts         guards.prodServer
    the AWS profile/region or Azure subscription
      an aws/az command will act as                 cloud.* pins (below)

IDENTITY. Every `aws` and `az` command resolves the identity it would run as --
`--profile`/`--region`/`--subscription` first, then the environment it would
inherit (an `env X=Y` or `X=Y` prefix, an earlier `export`, `$env:X = ...` in
PowerShell, then this process's own environment), then, for Azure only, the az
CLI's default subscription in `azureProfile.json`. `az account show` is never
run: it can hang on a token refresh, and a PreToolUse hook that hangs is a
session that hangs. That identity is checked against the repo's `cloud.*` pins.
A mismatch is denied. An identity crew cannot name -- nothing set, static
`AWS_ACCESS_KEY_ID` keys, an Az PowerShell context, or a destructive command in
a repo that pinned nothing -- is UNKNOWN, and unknown is never allowed
unattended: it asks when a person is there to answer and is denied when not.
That holds for READ-ONLY calls too once any `cloud.*` pin is set; only a repo
that pins nothing at all passes a read-only call with an unnamed identity, and
says so once (`identity_verdict`, `_note_unpinned`).

WHAT IT REFUSES BECAUSE IT COULD NOT READ IT, under `[cloudGuard]` whatever the
per-rule policies say: nesting past MAX_DEPTH, and hook input that is not a
readable Bash/PowerShell call. `report` mode prints no decision at all -- never
`allow` -- plus a `systemMessage` saying what `block` would have done.

WHAT IT CANNOT SEE, stated so nobody mistakes this for a sandbox: a command
named through a variable (`$TF apply`), a script file it runs (`bash x.sh`,
`psql -f x.sql`), SQL built at runtime, a hashtable splatted into a cmdlet, and
anything an MCP server does. What `xargs`/`parallel` append is not seen either,
so a destructive-capable tool behind one is judged as destructive, and one
whose executable is a placeholder is refused as unreadable. Native
permissions and restricted credentials are the boundary; this is a tripwire in
front of them.

WHY THE PARSER IS HAND-ROLLED. `shlex` knows nothing of `&&`, heredocs, `$( )`
or PowerShell, and the old command guard (removed in 0.19.52) was removed
precisely because it matched words anywhere -- inside commit messages and
comment bodies. So this reads each shell into simple commands first and judges
only the command a segment actually runs, never a word inside an argument.
"""
import base64
import collections
import fnmatch
import json
import os
import re
import sys
import time

import crew_config
import crew_state
from crew_guards import _head_name as _guards_head_name


def _head_name(token):
    """`crew_guards._head_name`, plus the two spellings it misses when the
    interpreter is not Windows' own: a backslash path
    (`C:\\tools\\terraform.exe`, which POSIX `basename` does not split) and
    the `.cmd`/`.bat`/`.ps1` shims (`az` IS `az.cmd` on Windows)."""
    head = _guards_head_name(token.replace("\\", "/"))
    for ext in (".cmd", ".bat", ".ps1"):
        if head.endswith(ext):
            return head[:-len(ext)]
    return head

# Never deeper than this into `bash -c`, `$( )`, `ssh host '...'` and friends.
# A real command line is two or three levels at most; the bound exists so a
# pathological payload cannot make a PreToolUse hook spin. Past it the command
# is REFUSED, not passed: what sits below the bound was never read, and a
# nesting depth is free for anyone to add.
MAX_DEPTH = 6

Finding = collections.namedtuple(
    "Finding", ("rule", "text", "what", "cloud", "destructive", "identity"))

IDENTITY_RULE = "cloudIdentity"

# The rule a command is refused under when crew could not READ it -- nested
# past MAX_DEPTH, or a script handed over by `xargs`. Named after the switch,
# because no per-rule policy governs "could not tell": the switch being on is
# the only consent there is, and it is consent to judging, not to guessing.
UNREADABLE_RULE = "cloudGuard"

# --- shared helpers ---------------------------------------------------------


def _match_close(text, start, open_ch="(", close_ch=")", ps=False):
    """Index of the bracket closing `text[start]`, quote-aware; len-1 if none."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c == "'":
            j = i + 1
            while j < n:
                if text[j] == "'":
                    if ps and text[j + 1:j + 2] == "'":
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
            continue
        if c == '"':
            j = i + 1
            esc = "`" if ps else "\\"
            while j < n and text[j] != '"':
                j += 2 if text[j] == esc else 1
            i = j + 1
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n - 1


class _Cmd:
    """One simple command: its words, what reaches its stdin, and the
    substitutions (`$( )`, backticks, PowerShell subexpressions) seen while
    reading it, which are scanned as commands in their own right."""

    def __init__(self, pipe_from=None):
        self.words = []
        self.stdin = None
        self.pipe_from = pipe_from

    def has_content(self):
        return bool(self.words) or self.stdin is not None


# --- bash -------------------------------------------------------------------

# Reserved words that can open a simple command. `time` is NOT here: it takes
# options (`time -p terraform destroy`), so it is unwrapped as a wrapper.
_BASH_RESERVED = frozenset(("{", "}", "!", "if", "then", "else", "elif", "fi",
                            "do", "done", "while", "until", "case", "esac",
                            "coproc"))


def _read_bash_double(text, i, subs):
    """A "..." word starting at `text[i]`; returns (value, next index)."""
    buf, j, n = [], i + 1, len(text)
    while j < n and text[j] != '"':
        c = text[j]
        if c == "\\" and j + 1 < n and text[j + 1] in '"\\$`\n':
            if text[j + 1] != "\n":
                buf.append(text[j + 1])
            j += 2
            continue
        if text.startswith("$(", j):
            k = _match_close(text, j + 1)
            subs.append(text[j + 2:k])
            buf.append(text[j:k + 1])
            j = k + 1
            continue
        if c == "`":
            k = text.find("`", j + 1)
            k = n - 1 if k < 0 else k
            subs.append(text[j + 1:k])
            buf.append(text[j:k + 1])
            j = k + 1
            continue
        buf.append(c)
        j += 1
    return "".join(buf), j + 1


def _read_ansi_c(text, i):
    """A $'...' word starting at `text[i]` (the `$`)."""
    buf, j, n = [], i + 2, len(text)
    simple = {"n": "\n", "t": "\t", "r": "\r", "'": "'", "\\": "\\", '"': '"'}
    while j < n and text[j] != "'":
        if text[j] == "\\" and j + 1 < n:
            buf.append(simple.get(text[j + 1], text[j + 1]))
            j += 2
            continue
        buf.append(text[j])
        j += 1
    return "".join(buf), j + 1


def _read_heredocs(text, i, pending):
    """Consume heredoc bodies starting at `text[i]`; attach each to its command."""
    n = len(text)
    for delim, strip_tabs, cmd in pending:
        lines = []
        while i < n:
            end = text.find("\n", i)
            end = n if end < 0 else end
            line = text[i:end]
            i = end + 1
            check = line.lstrip("\t") if strip_tabs else line
            if check.rstrip("\r") == delim:
                break
            lines.append(line)
        body = "\n".join(lines)
        cmd.stdin = body if cmd.stdin is None else cmd.stdin + "\n" + body
    return i


def _lex_bash(text):
    """`text` as a list of `_Cmd`, plus every substitution found in it."""
    cmds, subs, pending = [], [], []
    state = {"cur": _Cmd(), "word": None, "redirect": None}

    def end_word():
        word = state["word"]
        if word is None:
            return
        value = "".join(word)
        state["word"] = None
        redirect = state["redirect"]
        if redirect is not None:
            # The word after a redirection operator is its target, never an
            # argument -- except that a heredoc's is its delimiter and a
            # here-string's is the command's stdin.
            state["redirect"] = None
            if redirect == "<<<":
                state["cur"].stdin = value
            elif redirect in ("<<", "<<-"):
                pending.append((value, redirect == "<<-", state["cur"]))
            return
        state["cur"].words.append(value)

    def finish(pipe=False):
        end_word()
        cur = state["cur"]
        if cur.has_content():
            cmds.append(cur)
        state["cur"] = _Cmd(pipe_from=cur if pipe else None)

    def add(chars):
        if state["word"] is None:
            state["word"] = []
        state["word"].append(chars)

    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            if text[i + 1:i + 2] == "\n":
                i += 2
                continue
            add(text[i + 1:i + 2])
            i += 2
            continue
        if c == "'":
            j = text.find("'", i + 1)
            j = n if j < 0 else j
            add(text[i + 1:j])
            i = j + 1
            continue
        if text.startswith("$'", i):
            value, i = _read_ansi_c(text, i)
            add(value)
            continue
        if c == '"':
            value, i = _read_bash_double(text, i, subs)
            add(value)
            continue
        if text.startswith("$(", i) or text.startswith("<(", i) \
                or text.startswith(">(", i):
            k = _match_close(text, i + 1)
            inner = text[i + 2:k]
            if not inner.startswith("("):
                subs.append(inner)
            add(text[i:k + 1])
            i = k + 1
            continue
        if text.startswith("${", i):
            k = _match_close(text, i + 1, "{", "}")
            add(text[i:k + 1])
            i = k + 1
            continue
        if c == "`":
            k = text.find("`", i + 1)
            k = n - 1 if k < 0 else k
            subs.append(text[i + 1:k])
            add(text[i:k + 1])
            i = k + 1
            continue
        if c == "#" and state["word"] is None:
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "\n":
            finish()
            i += 1
            if pending:
                i = _read_heredocs(text, i, pending)
                pending.clear()
            continue
        if c in " \t\r":
            end_word()
            i += 1
            continue
        if c in "<>":
            if state["word"] and "".join(state["word"]).isdigit():
                # `2>`: the digits are the fd, not an argument.
                state["word"] = None
            end_word()
            op = re.match(r"<<<|<<-|<<|>>|>&|<&|<>|>\||>|<", text[i:]).group(0)
            if op in ("<&", ">&"):
                # `2>&1`, `>&2`: an fd duplication, no target word to drop
                # beyond the digit that follows.
                state["word"] = None
                i += len(op)
                while i < n and text[i].isdigit():
                    i += 1
                if text[i:i + 1] == "-":
                    i += 1
                continue
            state["word"] = None
            state["redirect"] = op if op in ("<<<", "<<", "<<-") else ">"
            i += len(op)
            continue
        if c == "&" and text[i + 1:i + 2] == ">":
            end_word()
            op = ">>" if text[i + 2:i + 3] == ">" else ">"
            state["redirect"] = ">"
            i += 1 + len(op)
            continue
        if c in ";&|()":
            two = text[i:i + 2]
            if two in ("&&", "||", ";;"):
                finish()
                i += 2
                continue
            if two == "|&":
                finish(pipe=True)
                i += 2
                continue
            finish(pipe=c == "|")
            i += 1
            continue
        add(c)
        i += 1
    finish()
    return cmds, subs


# --- PowerShell -------------------------------------------------------------


class _Bare(str):
    """A PowerShell word typed out in full with no quote, escape, group or
    variable in it -- the only spelling PowerShell can bind as a PARAMETER.
    `'-WhatIf'`, `` `-WhatIf `` and `$w` holding "-WhatIf" are all a string
    argument. Every other word is a plain `str`, so anything that rebuilds a
    word (a substitution, a split) loses the mark, and "not known to be bare"
    is the default."""

    __slots__ = ()


_PS_REDIRECT_RE = re.compile(r"^(?:\d|\*)?>>?(?:&\d)?$|^\d?>&\d$")


def _ps_group_value(inner):
    """A parenthesised PowerShell expression as the string it most plausibly
    evaluates to: its literal pieces joined, `+` dropped. `("DROP " + "TABLE")`
    is `DROP TABLE`; anything more dynamic is the text itself."""
    cmds, _subs = _lex_ps(inner)
    words = [w for cmd in cmds for w in cmd.words if w != "+"]
    return "".join(words) if words else inner


def _read_ps_double(text, i, subs):
    buf, j, n = [], i + 1, len(text)
    while j < n:
        c = text[j]
        if c == "`" and j + 1 < n:
            buf.append({"n": "\n", "t": "\t", "r": "\r"}.get(text[j + 1],
                                                             text[j + 1]))
            j += 2
            continue
        if c == '"':
            if text[j + 1:j + 2] == '"':
                buf.append('"')
                j += 2
                continue
            break
        if text.startswith("$(", j):
            k = _match_close(text, j + 1, ps=True)
            subs.append(text[j + 2:k])
            buf.append(text[j:k + 1])
            j = k + 1
            continue
        buf.append(c)
        j += 1
    return "".join(buf), j + 1


def _read_ps_single(text, i):
    buf, j, n = [], i + 1, len(text)
    while j < n:
        if text[j] == "'":
            if text[j + 1:j + 2] == "'":
                buf.append("'")
                j += 2
                continue
            break
        buf.append(text[j])
        j += 1
    return "".join(buf), j + 1


def _read_ps_herestring(text, i, subs):
    """`@'...'@` / `@"..."@` starting at `text[i]`; None if it is not one."""
    quote = text[i + 1]
    eol = text.find("\n", i + 2)
    if eol < 0 or text[i + 2:eol].strip():
        return None
    close = text.find("\n" + quote + "@", eol)
    end = len(text) if close < 0 else close
    body = text[eol + 1:end]
    if quote == '"':
        for match in re.finditer(r"\$\(", body):
            k = _match_close(body, match.start() + 1, ps=True)
            subs.append(body[match.start() + 2:k])
    return body, (len(text) if close < 0 else close + 3)


def _lex_ps(text):
    """PowerShell `text` as a list of `_Cmd`, plus every subexpression."""
    cmds, subs = [], []
    state = {"cur": _Cmd(), "word": None, "bare": True}

    def end_word():
        if state["word"] is not None:
            value = "".join(state["word"])
            state["cur"].words.append(_Bare(value) if state["bare"] else value)
            state["word"] = None

    def finish(pipe=False):
        end_word()
        cur = state["cur"]
        if cur.has_content():
            cmds.append(cur)
        state["cur"] = _Cmd(pipe_from=cur if pipe else None)

    def add(chars, bare=False):
        if state["word"] is None:
            state["word"] = []
            state["bare"] = True
        state["word"].append(chars)
        state["bare"] = state["bare"] and bare

    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "`":
            if text[i + 1:i + 2] in ("\n", "\r"):
                i += 3 if text[i + 1:i + 3] == "\r\n" else 2
                continue
            add(text[i + 1:i + 2])
            i += 2
            continue
        if text.startswith("<#", i):
            j = text.find("#>", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == "#" and state["word"] is None:
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "@" and text[i + 1:i + 2] in ("'", '"'):
            here = _read_ps_herestring(text, i, subs)
            if here is not None:
                add(here[0])
                i = here[1]
                continue
        if c == "'":
            value, i = _read_ps_single(text, i)
            add(value)
            continue
        if c == '"':
            value, i = _read_ps_double(text, i, subs)
            add(value)
            continue
        if text.startswith("$(", i) or text.startswith("@(", i) or c == "(":
            start = i + 1 if c in "$@" else i
            k = _match_close(text, start, ps=True)
            inner = text[start + 1:k]
            subs.append(inner)
            add(_ps_group_value(inner))
            i = k + 1
            continue
        if c in "{}":
            finish()
            i += 1
            continue
        if c in ";\n":
            finish()
            i += 1
            continue
        if c == "|":
            if text[i + 1:i + 2] == "|":
                finish()
                i += 2
                continue
            finish(pipe=True)
            i += 1
            continue
        if c == "&":
            if text[i + 1:i + 2] == "&":
                finish()
                i += 2
                continue
            if state["word"] is None and not state["cur"].words:
                # The call operator: `& 'C:\tools\terraform.exe' apply`.
                i += 1
                continue
            finish()
            i += 1
            continue
        if c in " \t\r":
            end_word()
            i += 1
            continue
        add(c, bare=True)
        i += 1
    finish()
    for cmd in cmds:
        cleaned, skip = [], False
        for word in cmd.words:
            if skip:
                skip = False
                continue
            if _PS_REDIRECT_RE.match(word):
                skip = not word.endswith(("1", "2", "3", "4", "5", "6"))
                continue
            cleaned.append(word)
        cmd.words = cleaned
    return cmds, subs


# --- SQL --------------------------------------------------------------------

_SQL_WORDS_RE = re.compile(r"\b(drop|truncate)\b", re.IGNORECASE)


def _strip_sql(sql, dialect):
    """`sql` with every string literal and comment removed, read the way
    `dialect` reads it: `standard`, `postgres`, `postgres-escapes`, `tsql`,
    `mysql` or `mysql-no-escapes`. They disagree in ways that HIDE
    statements: standard SQL treats `\\'` as a backslash then a closing
    quote, MySQL as an escaped quote, and PostgreSQL does too inside an
    `E'...'` string; standard `--` always comments, MySQL's needs a space
    after it (`1--1; DROP TABLE t` runs the DROP there); and MySQL EXECUTES
    `/*! ... */` (MariaDB `/*M! ... */` too). The two `-escapes` readings are
    server MODES, not other products: MySQL under `NO_BACKSLASH_ESCAPES`, and
    PostgreSQL with `standard_conforming_strings` off, where a backslash
    escapes inside every `'...'`. `sql_is_destructive` reads a payload under
    every reading its client could be running with."""
    mysql = dialect.startswith("mysql")
    out, i, n = [], 0, len(sql)
    while i < n:
        c = sql[i]
        if c in "'\"":
            escapes = dialect == "mysql" or (
                dialect == "postgres-escapes" and c == "'") or (
                dialect.startswith("postgres") and c == "'" and i > 0
                and sql[i - 1] in "eE"
                and not (i > 1 and (sql[i - 2].isalnum() or sql[i - 2] == "_")))
            j = i + 1
            while j < n:
                if escapes and sql[j] == "\\":
                    j += 2
                    continue
                if sql[j] == c:
                    if sql[j + 1:j + 2] == c:
                        j += 2
                        continue
                    break
                j += 1
            out.append(" ")
            i = j + 1
            continue
        if sql.startswith("--", i) and (
                not mysql or i + 2 >= n or sql[i + 2] in " \t\r\n"):
            j = sql.find("\n", i)
            i = n if j < 0 else j
            continue
        if mysql and c == "#":
            j = sql.find("\n", i)
            i = n if j < 0 else j
            continue
        if sql.startswith("/*", i) and not (
                mysql and sql.startswith(("/*!", "/*M!"), i)):
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
            continue
        out.append(c)
        i += 1
    return "".join(out)


def sql_is_destructive(sql, dialect=None):
    """True when `sql` holds DROP or TRUNCATE outside every literal and comment
    under ANY of the readings `dialect` names -- one reading, a tuple of
    them, or, when the client is not known (`None`), the standard and both
    MySQL readings. A keyword counts as inside a string or a comment only
    when EVERY reading agrees it is; one reading that sees it live is
    enough, because which mode the server runs in is not on the command
    line."""
    if not isinstance(sql, str) or not sql.strip():
        return False
    if isinstance(dialect, str):
        readings = (dialect,)
    else:
        readings = tuple(dialect or ("standard", "mysql", "mysql-no-escapes"))
    return any(_SQL_WORDS_RE.search(_strip_sql(sql, reading))
               for reading in readings)


# Per client: the flags whose value is SQL. Written per client rather than
# shared because they collide -- `-e` is psql's echo-queries (no value) and
# mysql's execute (SQL), so one table read `psql -e -c 'DROP ...'` as a
# payload of `-c` and never saw the DROP.
_SQL_FLAGS = {
    "psql": ("-c", "--command"),
    "mysql": ("-e", "--execute"),
    "mariadb": ("-e", "--execute"),
    "sqlcmd": ("-q", "-Q", "--query"),
    "sqlite3": ("-cmd",),
}
SQL_CLIENTS = frozenset(_SQL_FLAGS) | {"invoke-sqlcmd"}

# Per client: every reading the server it talks to could apply. Not every
# dialect for every client -- T-SQL and SQLite never read a backslash as an
# escape, so `sqlcmd -Q "SELECT 'C:\\' AS p, 'drop' AS s"` is two plain
# strings. But not ONE reading per client either: a MySQL server under
# NO_BACKSLASH_ESCAPES, or a PostgreSQL one with standard_conforming_strings
# off, reads the same text differently from its default, and the mode is
# not on the command line. A DROP any of the client's readings sees counts.
_SQL_DIALECT = {"psql": ("postgres", "postgres-escapes"),
                "mysql": ("mysql", "mysql-no-escapes"),
                "mariadb": ("mysql", "mysql-no-escapes"),
                "sqlcmd": ("tsql",), "invoke-sqlcmd": ("tsql",),
                "sqlite3": ("standard",)}


def _sql_payloads(head, args, stdin):
    """Every SQL text `head` was handed on its command line or stdin."""
    out = [stdin] if stdin else []
    if head == "invoke-sqlcmd":
        positional = []
        index = 0
        while index < len(args):
            arg = args[index]
            name, _sep, inline = arg.partition(":")
            low = name.lower()
            if low.startswith("-") and len(low) > 2 and "-query".startswith(low):
                out.append(inline if _sep else (
                    args[index + 1] if index + 1 < len(args) else ""))
                index += 1 if _sep else 2
                continue
            if low.startswith("-"):
                index += 2 if not _sep else 1
                continue
            positional.append(arg)
            index += 1
        out.extend(positional[:1])
        return out
    flags = _SQL_FLAGS.get(head, ())
    positional = []
    index = 0
    while index < len(args):
        arg = args[index]
        name, sep, inline = arg.partition("=")
        if name in flags:
            if sep:
                out.append(inline)
            elif index + 1 < len(args):
                out.append(args[index + 1])
                index += 1
            index += 1
            continue
        attached = [f for f in flags if len(f) == 2 and arg.startswith(f)
                    and len(arg) > 2]
        if attached:
            out.append(arg[2:])
        elif not arg.startswith("-"):
            positional.append(arg)
        index += 1
    if head == "sqlite3" and len(positional) > 1:
        out.extend(positional[1:])
    return out


# --- per-command classification ---------------------------------------------

_WRAPPER_VALUE_OPTS = {
    "sudo": frozenset(("-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U",
                       "--user", "--group", "--host", "--prompt",
                       "--close-from", "--chdir", "--role", "--type",
                       "--other-user")),
    "doas": frozenset(("-u", "-C")),
    "nice": frozenset(("-n", "--adjustment")),
    "timeout": frozenset(("-s", "-k", "--signal", "--kill-after")),
    "stdbuf": frozenset(("-i", "-o", "-e")),
    "xargs": frozenset(("-I", "-J", "-R", "-n", "-P", "-d", "-L", "-s", "-E",
                        "-a", "--max-args", "--max-procs", "--delimiter",
                        "--arg-file", "--max-lines", "--max-chars")),
    "parallel": frozenset(("-j", "-P", "-S", "-a", "-d", "-n", "-N", "-E",
                           "-I", "--jobs", "--sshlogin", "--arg-file",
                           "--delimiter", "--max-args", "--joblog",
                           "--results", "--tmpdir", "--colsep")),
    "exec": frozenset(("-a",)),
    "time": frozenset(("-f", "-o", "--format", "--output")),
    "nohup": frozenset(),
    "command": frozenset(),
    "builtin": frozenset(),
}
_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\+?=(.*)$", re.DOTALL)
_SHELLS = frozenset(("bash", "sh", "zsh", "dash", "ksh", "ash", "busybox"))
_PWSH = frozenset(("pwsh", "powershell", "pwsh-preview"))

# Wrappers that append arguments crew cannot see -- read from stdin, a file or
# a `:::` list -- to the command they run.
_ARGV_FEEDERS = frozenset(("xargs", "parallel"))


def _replace_strings(head, args):
    """Every placeholder an `xargs`/`parallel` invocation substitutes into
    the command it runs: `{}` always, plus whatever `-I R`, `-IR`, `-iR`,
    `--replace=R` or BSD's `-J R` names. The options are walked the way
    `_unwrap` walks them, value-taking ones skipping their value -- stopping
    at the first word that is not an option lost `-I` behind `-a file`."""
    found = ["{}"]
    takes = _WRAPPER_VALUE_OPTS.get(head, frozenset())
    index = 0
    while index < len(args):
        arg = args[index]
        if not arg.startswith("-") or arg in ("-", "--"):
            break
        if arg in ("-I", "-J") and index + 1 < len(args):
            found.append(args[index + 1])
        elif arg.startswith("--replace="):
            found.append(arg.partition("=")[2] or "{}")
        elif arg[:2] in ("-I", "-i", "-J") and len(arg) > 2:
            found.append(arg[2:])
        index += 2 if arg in takes else 1
    return tuple(p for p in found if p)


def _unwrap(words, env, fed=None):
    """Strip assignments and wrappers off `words`; returns the argv that runs.

    `env` is the per-command override dict, updated in place: `X=Y cmd` and
    `env X=Y cmd` set `X`, `env -u X` and `env -i` unset. `fed`, when a list,
    collects every `_ARGV_FEEDERS` wrapper stripped on the way: the argv
    returned is then NOT the whole argv that runs.
    """
    words = list(words)
    while words:
        match = _ASSIGN_RE.match(words[0])
        if match and len(words) > 1:
            env[match.group(1)] = match.group(2)
            words = words[1:]
            continue
        head = _head_name(words[0])
        if words[0] in _BASH_RESERVED:
            words = words[1:]
            continue
        if head == "env":
            rest = words[1:]
            while rest:
                if rest[0] in ("-i", "--ignore-environment", "-"):
                    for key in _IDENTITY_VARS:
                        env[key] = None
                    rest = rest[1:]
                elif rest[0] in ("-u", "--unset") and len(rest) > 1:
                    env[rest[1]] = None
                    rest = rest[2:]
                elif rest[0] in ("-C", "--chdir") and len(rest) > 1:
                    rest = rest[2:]
                elif rest[0] in ("-S", "--split-string") and len(rest) > 1:
                    rest = rest[1].split() + rest[2:]
                elif rest[0].startswith("-"):
                    rest = rest[1:]
                elif _ASSIGN_RE.match(rest[0]):
                    match = _ASSIGN_RE.match(rest[0])
                    env[match.group(1)] = match.group(2)
                    rest = rest[1:]
                else:
                    break
            words = rest
            continue
        if head in _WRAPPER_VALUE_OPTS:
            takes = _WRAPPER_VALUE_OPTS[head]
            rest = words[1:]
            while rest and rest[0].startswith("-") and rest[0] != "-":
                if rest[0] == "--":
                    rest = rest[1:]
                    break
                rest = rest[2:] if rest[0] in takes else rest[1:]
            if head == "timeout" and rest:
                rest = rest[1:]
            if head in _ARGV_FEEDERS:
                if fed is not None:
                    fed.append((head, _replace_strings(head, words[1:])))
                # `parallel 'terraform {}' ::: destroy`: the command is one
                # quoted word.
                if rest and len(rest[0].split()) > 1:
                    rest = rest[0].split() + rest[1:]
            words = rest
            continue
        return words
    return words


def _flag_value(args, names):
    """The value of the LAST `--name value` / `--name=value` in `args`."""
    found = None
    for index, arg in enumerate(args):
        name, sep, inline = arg.partition("=")
        if name in names:
            if sep:
                found = inline
            elif index + 1 < len(args):
                found = args[index + 1]
    return found


_AWS_VALUE_OPTS = frozenset((
    "--profile", "--region", "--output", "--endpoint-url", "--query",
    "--color", "--ca-bundle", "--cli-read-timeout", "--cli-connect-timeout",
    "--cli-binary-format"))
_AWS_DESTRUCTIVE_PREFIXES = ("delete-", "terminate-", "purge-")


def _aws_words(args):
    words, index = [], 0
    while index < len(args):
        arg = args[index]
        if arg.split("=", 1)[0] in _AWS_VALUE_OPTS and "=" not in arg:
            index += 2
            continue
        if arg.startswith("-"):
            index += 1
            continue
        words.append(arg)
        index += 1
    return words


def _aws_destructive(args):
    words = _aws_words(args)
    if len(words) < 2:
        return None
    # `--dry-run` (EC2 and friends) and `--dryrun` (the s3 commands) check
    # permissions and print what would happen; nothing is deleted. The CLI
    # takes the LAST of a flag and its `--no-` negation, so
    # `--dry-run --no-dry-run` is the real thing.
    dry = [a for a in args if a in ("--dry-run", "--no-dry-run", "--dryrun",
                                    "--no-dryrun")]
    if dry and dry[-1] in ("--dry-run", "--dryrun"):
        return None
    service, verb = words[0].lower(), words[1].lower()
    if verb.startswith(_AWS_DESTRUCTIVE_PREFIXES) or verb in ("delete",
                                                             "terminate"):
        return f"aws {service} {verb}"
    if service == "s3" and verb in ("rm", "rb"):
        return f"aws s3 {verb}"
    if service == "s3" and verb == "sync" and "--delete" in args:
        return "aws s3 sync --delete"
    return None


def _az_verb(word):
    word = word.lower()
    return word in ("delete", "purge") or word.startswith(("delete-", "purge-"))


def _az_destructive(args):
    """`az ... delete|purge`, the verb found in ANY positional position.

    The az CLI accepts options between the words of a command path
    (`az group --subscription prod delete -n rg`), and whether a word after
    an option is that option's value or the next path word depends on a
    per-command table crew does not carry. So every positional word is a
    candidate verb: a resource NAMED `delete` is refused too, which is the
    direction a guard may be wrong in."""
    path = []
    for arg in args:
        if arg.startswith("-"):
            continue
        path.append(arg.lower())
        if _az_verb(arg):
            return "az " + " ".join(path)
    return None


_HELP_FLAGS = frozenset(("-help", "--help", "-h"))

# Terraform/OpenTofu options that take the NEXT word as their value when
# written without `=` -- Go's flag package does that even when the word
# starts with a dash, so `-var-file --help` names a file called `--help`.
_TF_VALUE_OPTS = frozenset((
    "var", "var-file", "target", "replace", "exclude", "state", "state-out",
    "backup", "out", "lock-timeout", "parallelism", "chdir", "plugin-dir",
    "backend-config", "generate-config-out", "from-module", "config",
    "test-directory", "filter"))
# ...and the ones known to take none. An option in neither set might take a
# value, so a help flag after it proves nothing.
_TF_BOOL_OPTS = frozenset((
    "auto-approve", "input", "lock", "refresh", "refresh-only", "destroy",
    "compact-warnings", "json", "no-color", "upgrade", "reconfigure",
    "migrate-state", "force-copy", "backend", "get", "recursive", "check",
    "diff", "write", "list", "raw", "detailed-exitcode", "verbose"))


def _tf_help_requested(args):
    """True only when a help flag stands on its own, where no preceding option
    could be taking it as its value. When unsure -- an option this does not
    know, `--` included -- it is not help, and the apply is real."""
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in _HELP_FLAGS:
            return True
        if arg.startswith("-") and "=" not in arg:
            name = arg.lstrip("-")
            if name in _TF_VALUE_OPTS:
                index += 2
                continue
            if name not in _TF_BOOL_OPTS:
                return False
        index += 1
    return False


def _terraform_destructive(head, args):
    words = [a for a in args if not a.startswith("-")]
    if not words:
        return None
    # `terraform apply -help` prints usage; the CLI runs nothing else.
    if _tf_help_requested(args):
        return None
    if words[0] in ("apply", "destroy"):
        return f"{head} {words[0]}"
    if words[0] in ("run-all", "run") and len(words) > 1 \
            and words[1] in ("apply", "destroy"):
        return f"{head} {words[0]} {words[1]}"
    return None


_GIT_VALUE_OPTS = frozenset(("-C", "-c", "--git-dir", "--work-tree",
                             "--namespace", "--exec-path", "--config-env"))


def _git_force_push(args):
    index = 0
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in _GIT_VALUE_OPTS else 1
    if index >= len(args) or args[index] != "push":
        return None
    rest = args[index + 1:]
    for arg in rest:
        if arg in ("--force", "-f", "--force-with-lease") \
                or arg.startswith("--force-with-lease="):
            return f"git push {arg}"
        if re.match(r"^-[a-zA-Z]*f[a-zA-Z]*$", arg):
            return f"git push {arg}"
    # A leading `+` on any refspec forces that ref. Every positional is
    # checked, not only those after the remote: an option's value (`-o x`)
    # shifts the count, and no remote is spelled with a leading `+`.
    for ref in (a for a in rest if not a.startswith("-")):
        if ref.startswith("+"):
            return f"git push {ref}"
    return None


def _ssh_remote(args):
    """The remote command an `ssh`/`plink` invocation runs, or None."""
    takes = ("-i", "-p", "-o", "-l", "-F", "-b", "-c", "-D", "-e", "-I", "-J",
             "-L", "-m", "-O", "-Q", "-R", "-S", "-W", "-w", "-P", "-pw")
    index = 0
    while index < len(args):
        if args[index] in takes:
            index += 2
            continue
        if args[index].startswith("-"):
            index += 1
            continue
        break
    rest = args[index + 1:]
    return " ".join(rest) if rest else None


_SHELL_VALUE_OPTS = frozenset(("-o", "+o", "-O", "+O", "--rcfile",
                               "--init-file"))


def _shell_args(args):
    """`(has_c, positional)` for a POSIX shell's argv. Options end at the
    first non-option or at `--`, and `-c` is a FLAG, not an option taking the
    script: the script is the first positional after the options, so
    `bash -c -- 'x'` and `bash -c -e 'x'` both run `x`."""
    has_c, index = False, 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            index += 1
            break
        if arg in _SHELL_VALUE_OPTS:
            index += 2
            continue
        if arg.startswith("--"):
            index += 1
            continue
        if len(arg) > 1 and arg[0] in "-+":
            has_c = has_c or (arg[0] == "-" and "c" in arg[1:])
            index += 1
            continue
        break
    return has_c, args[index:]


def _pwsh_payload(args):
    """The script a `pwsh`/`powershell` invocation runs inline, or None."""
    for index, arg in enumerate(args):
        low = arg.lower()
        if low in ("-c", "-command", "/c", "-com", "-comm", "-comma",
                   "-comman"):
            return " ".join(args[index + 1:])
        if low in ("-e", "-ec", "-enc", "-encodedcommand", "-encoded"):
            if index + 1 < len(args):
                try:
                    return base64.b64decode(args[index + 1]).decode(
                        "utf-16-le", "replace")
                except (ValueError, TypeError):
                    return None
        if low in ("-f", "-file"):
            return None
    positional = [a for a in args if not a.startswith("-")]
    # `pwsh 'terraform destroy'`: with no parameter at all the first
    # positional argument is `-Command`'s.
    return " ".join(positional) if positional and positional == args else None


def _classify(argv, stdin, env, shell, depth):
    """Findings for one unwrapped simple command, recursing into anything it
    runs inline (`bash -c`, `pwsh -c`, `ssh host cmd`, `cmd /c`, `wsl`)."""
    head = _head_name(argv[0])
    args = argv[1:]
    text = " ".join(argv)
    out = []

    if head in _SHELLS:
        # `-c`, and every cluster carrying it: `bash -lc`, `sh -ec`. With no
        # `-c` at all, a heredoc or pipe on stdin is the script.
        if head == "busybox" and args and _head_name(args[0]) in _SHELLS:
            args = args[1:]
        has_c, positional = _shell_args(args)
        payload = None
        if has_c:
            payload = positional[0] if positional else ""
        elif not positional:
            payload = stdin
        if payload:
            out.extend(scan("bash", payload, env, depth + 1))
        return out
    if head in _PWSH:
        payload = _pwsh_payload(args)
        if payload in (None, "-") and stdin:
            payload = stdin
        if payload:
            out.extend(scan("powershell", payload, env, depth + 1))
        return out
    if head == "cmd" and args and args[0].lower() in ("/c", "/k"):
        out.extend(scan("bash", " ".join(args[1:]), env, depth + 1))
        return out
    if head == "wsl":
        rest = list(args)
        while rest and rest[0].startswith("-"):
            flag = rest[0]
            rest = rest[1:]
            if flag in ("-e", "--exec", "--"):
                if rest:
                    out.extend(_classify(rest, stdin, env, shell, depth + 1))
                return out
            if flag in ("-d", "--distribution", "-u", "--user", "--cd"):
                rest = rest[1:]
        if rest:
            out.extend(scan("bash", " ".join(rest), env, depth + 1))
        return out
    if head in ("eval",):
        out.extend(scan("bash", " ".join(args), env, depth + 1))
        return out

    if head in ("terraform", "tofu", "terragrunt"):
        what = _terraform_destructive(head, args)
        if what:
            out.append(Finding("terraformApply", text, what, None, True, None))
        return out
    if head == "git":
        what = _git_force_push(args)
        if what:
            out.append(Finding("forcePush", text, what, None, True, None))
        return out
    if head == "gh":
        words = [a for a in args if not a.startswith("-")]
        pairs = list(zip(words, words[1:]))
        if ("pr", "merge") in pairs and "--admin" in args:
            out.append(Finding("adminMerge", text, "gh pr merge --admin",
                               None, True, None))
        return out
    if head == "aws":
        what = _aws_destructive(args)
        identity = _aws_identity(args, env)
        out.append(Finding("cloudDestructive" if what else IDENTITY_RULE,
                           text, what or "aws " + " ".join(_aws_words(args)[:2]),
                           "aws", bool(what), identity))
        return out
    if head == "az":
        what = _az_destructive(args)
        identity = _az_identity(args, env)
        out.append(Finding("cloudDestructive" if what else IDENTITY_RULE,
                           text, what or "az " + " ".join(
                               a for a in args[:2] if not a.startswith("-")),
                           "az", bool(what), identity))
        return out
    if head.startswith("remove-az"):
        if _whatif_requested(args):
            return out
        out.append(Finding("cloudDestructive", text, argv[0], "azps", True,
                           {"name": None,
                            "unknown": "Az PowerShell acts as its own saved "
                                       "context, which this guard does not "
                                       "read"}))
        return out
    if head in SQL_CLIENTS:
        payloads = _sql_payloads(head, args, stdin)
        if any(sql_is_destructive(p, _SQL_DIALECT[head]) for p in payloads):
            out.append(Finding("sqlDestructive", text,
                               f"DROP/TRUNCATE via {head}", None, True, None))
        out.append(Finding("prodDatabase", text, head, None, False, None))
        return out
    if head in ("ssh", "plink", "scp", "sftp"):
        out.append(Finding("prodServer", text, head, None, False, None))
        remote = _ssh_remote(args) if head in ("ssh", "plink") else None
        if remote:
            out.extend(scan("bash", remote, env, depth + 1))
        return out
    return out


# Switch parameters a Remove-Az* cmdlet or PowerShell itself takes: none of
# them consumes the word after it.
_AZPS_SWITCHES = frozenset(("-force", "-asjob", "-passthru", "-confirm",
                            "-verbose", "-debug"))


def _whatif_requested(args):
    """True only when `-WhatIf` (or `-WhatIf:$true`) is a PARAMETER: a bare
    word (`_Bare` -- not quoted, escaped or substituted) that no preceding
    parameter can be taking as its value. `-WhatIf` reports what would be
    removed and removes nothing; `-Name '-WhatIf'` removes a resource group
    named `-WhatIf`, and `-WhatIf:$false` is the real thing. A preceding
    parameter this does not know to be a switch might take the word as its
    value, so it is not an exemption: when unsure, the removal is real."""
    for index, arg in enumerate(args):
        if not isinstance(arg, _Bare) \
                or arg.lower() not in ("-whatif", "-whatif:$true"):
            continue
        prev = args[index - 1] if index else None
        if prev is None:
            return True
        if prev.endswith(","):
            # `-Name rg, -WhatIf`: an array still being written.
            continue
        if not isinstance(prev, _Bare) or not prev.startswith("-"):
            return True
        if ":" in prev or prev.lower() in _AZPS_SWITCHES:
            return True
    return False


_TF_READ_ONLY = frozenset(("plan", "init", "validate", "fmt", "show", "output",
                           "providers", "version", "graph", "get", "console",
                           "workspace", "state", "test", "login", "logout"))


# What a literal executable name looks like: a bare name or a path. Anything
# else in the executable position under `xargs`/`parallel` -- `%`, a quote-
# built word, a variable -- is not known to name a harmless command.
_LITERAL_EXE_RE = re.compile(r"^[A-Za-z0-9_./~\\][A-Za-z0-9_.+:/\\~-]*$")


def _fed_finding(argv, env, via, placeholders):
    """The finding for a destructive-capable tool run by `xargs`/`parallel`,
    whose argv ends in words crew cannot see -- or None when the words it CAN
    see already fix the operation as one the guard does not govern.

    `echo destroy | xargs terraform` runs `terraform destroy`; judging only
    `terraform` let it through. A subcommand counts as seen only when it is
    literal: a word carrying a placeholder is filled in from stdin too. So is
    the EXECUTABLE when it carries one: `xargs -I CMD CMD destroy` runs
    whatever the input names, which is refused as unreadable.
    """
    head = _head_name(argv[0])
    args = argv[1:]
    text = " ".join(argv)
    what = (f"{text} (via {via}, which appends arguments crew cannot see, "
            "so the operation is not known)")

    def carries(word):
        return "{" in word or any(p in word for p in placeholders)

    def seen(words):
        return [w for w in words if not w.startswith("-") and not carries(w)]

    if carries(argv[0]) or "$" in argv[0] or "`" in argv[0] \
            or not _LITERAL_EXE_RE.match(argv[0]):
        return Finding(UNREADABLE_RULE, text,
                       f"{text} (via {via}, whose executable is filled in "
                       "from input crew cannot see)", None, True, None)

    if head in ("terraform", "tofu", "terragrunt"):
        words = [w for w in args if not w.startswith("-")]
        if words and seen(words[:1]) and words[0] in _TF_READ_ONLY:
            return None
        return Finding("terraformApply", text, what, None, True, None)
    if head == "git":
        index = 0
        while index < len(args) and args[index].startswith("-"):
            index += 2 if args[index] in _GIT_VALUE_OPTS else 1
        sub = args[index] if index < len(args) else ""
        if sub and seen([sub]) and sub != "push":
            return None
        return Finding("forcePush", text, what, None, True, None)
    if head in ("aws", "az"):
        words = _aws_words(args) if head == "aws" else [
            a for a in args if not a.startswith("-")]
        if head == "aws" and len(words) >= 2 and seen(words[:2]) == words[:2] \
                and not (words[0].lower() == "s3" and words[1].lower()
                         == "sync"):
            return None
        if head == "az" and seen(words) == words and any(
                w.lower() in ("list", "show") or w.lower().startswith(
                    ("list-", "show-")) for w in words):
            return None
        identity = (_aws_identity if head == "aws" else _az_identity)(args,
                                                                      env)
        return Finding("cloudDestructive", text, what, head, True, identity)
    if head in SQL_CLIENTS:
        return Finding("sqlDestructive", text, what, None, True, None)
    if head in _SHELLS or head in _PWSH:
        # The appended words are the script's `$1..`, harmless -- unless there
        # is no inline script (it then comes from stdin or a file) or the
        # script itself carries the placeholder.
        if head in _SHELLS:
            has_c, positional = _shell_args(args)
            script = positional[0] if has_c and positional else None
        else:
            script = _pwsh_payload(args)
        if script and not any(p in script for p in placeholders) and not (
                via == "parallel" and "{" in script):
            return None
        return Finding(UNREADABLE_RULE, text, what, None, True, None)
    return None


# --- identity ---------------------------------------------------------------

_IDENTITY_VARS = ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_REGION",
                  "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID",
                  "AZURE_SUBSCRIPTION_ID", "AZURE_CONFIG_DIR")


def _env(env, name):
    """`name` as the command would inherit it: override first, then ours."""
    if name in env:
        return env[name] or None
    return os.environ.get(name) or None


def _aws_identity(args, env):
    profile_flag = _flag_value(args, ("--profile",))
    region = (_flag_value(args, ("--region",)) or _env(env, "AWS_REGION")
              or _env(env, "AWS_DEFAULT_REGION"))
    if not profile_flag and _env(env, "AWS_ACCESS_KEY_ID"):
        return {"name": None, "region": region,
                "unknown": "AWS_ACCESS_KEY_ID is set, and static keys take "
                           "precedence over any profile, so the account is "
                           "unnamed"}
    profile = (profile_flag or _env(env, "AWS_PROFILE")
               or _env(env, "AWS_DEFAULT_PROFILE"))
    if not profile:
        return {"name": None, "region": region,
                "unknown": "no --profile, AWS_PROFILE or AWS_DEFAULT_PROFILE "
                           "is set, so the CLI would use whatever the "
                           "machine's default credentials are"}
    return {"name": profile, "region": region, "unknown": ""}


def _az_default_subscription(env):
    """(id, name) of the az CLI's default subscription, or (None, None)."""
    config_dir = _env(env, "AZURE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".azure")
    path = os.path.join(config_dir, "azureProfile.json")
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None, None
    subs = data.get("subscriptions") if isinstance(data, dict) else None
    for sub in subs if isinstance(subs, list) else ():
        if isinstance(sub, dict) and sub.get("isDefault") is True:
            return sub.get("id"), sub.get("name")
    return None, None


def _az_identity(args, env):
    flag = _flag_value(args, ("--subscription",))
    if flag:
        return {"name": flag, "alt": None, "unknown": ""}
    from_env = _env(env, "AZURE_SUBSCRIPTION_ID")
    if from_env:
        return {"name": from_env, "alt": None, "unknown": ""}
    sub_id, sub_name = _az_default_subscription(env)
    if sub_id or sub_name:
        return {"name": sub_id or sub_name, "alt": sub_name, "unknown": ""}
    return {"name": None, "alt": None,
            "unknown": "no --subscription, no AZURE_SUBSCRIPTION_ID, and no "
                       "default subscription in azureProfile.json"}


def cloud_pins(root):
    """`(pins, problem)`: the repo's `cloud.*` lists, REPO LAYER ONLY.

    `problem` is non-empty when the block is there and cannot be read as lists
    of globs -- which is NOT "nothing pinned". Nothing pinned lets a read-only
    command through; a pin crew cannot read makes every cloud identity unknown.
    """
    empty = {key: [] for key in crew_state.CLOUD_DEFAULTS}
    path = os.path.join(root, ".crew", "config.json")
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            raw = handle.read()
    except (FileNotFoundError, NotADirectoryError):
        return empty, ""
    except (OSError, ValueError) as exc:
        return empty, f".crew/config.json could not be read ({type(exc).__name__})"
    try:
        cfg = json.loads(raw)
    except ValueError:
        return empty, ".crew/config.json does not parse as JSON"
    if not isinstance(cfg, dict) or "cloud" not in cfg:
        return empty, "" if isinstance(cfg, dict) else \
            ".crew/config.json is not a JSON object"
    block = cfg["cloud"]
    problem = crew_config.cloud_block_problem(block)
    if problem:
        return empty, problem
    return {key: [v.strip() for v in block.get(key, [])] for key in empty}, ""


def _matches(value, patterns):
    return any(fnmatch.fnmatch(str(value).lower(), p.lower()) for p in patterns)


UNPINNED = "unpinned"


def identity_verdict(finding, pins, problem):
    """`("ok"|"deny"|"unknown"|"unpinned", reason)` for one cloud finding.

    The rule for an identity crew cannot name: it is UNKNOWN, and unknown is
    never allowed unattended, whenever this repo pins ANY cloud identity --
    a read-only `aws s3 ls` included, since which account it lists is the
    thing the pins exist to settle. Only a repo that pins nothing at all
    lets a read-only call with an unnamed identity through, as `unpinned`:
    there is nothing to check it against, and refusing would make arming
    the guard on an unpinned repo refuse every `aws s3 ls` in CI. `unpinned`
    is reported (once, see `main`), never silent. A DESTRUCTIVE call with
    nothing pinned for its cloud stays unknown either way.
    """
    ident = finding.identity or {}
    if problem:
        return "unknown", f"crew could not read the identity pins: {problem}"
    if finding.cloud == "azps":
        return "unknown", ident.get("unknown", "")
    pinned_any = any(pins[key] for key in pins)
    if ident.get("unknown") and not finding.destructive:
        if pinned_any:
            return "unknown", ident["unknown"]
        return UNPINNED, ident["unknown"]
    if finding.cloud == "aws":
        profiles, regions = pins["awsProfiles"], pins["awsRegions"]
        if not profiles and not regions:
            if finding.destructive:
                return "unknown", ("nothing is pinned in cloud.awsProfiles, "
                                   "so no identity was vouched for")
            return "ok", ""
        if profiles:
            if ident.get("unknown"):
                return "unknown", ident["unknown"]
            if not _matches(ident["name"], profiles):
                return "deny", (f"AWS profile `{ident['name']}` is not pinned "
                                f"(cloud.awsProfiles: {', '.join(profiles)})")
        elif finding.destructive:
            return "unknown", ("only regions are pinned; cloud.awsProfiles is "
                               "empty, so the account is not")
        if regions:
            if not ident.get("region"):
                return "unknown", ("no --region, AWS_REGION or "
                                   "AWS_DEFAULT_REGION is set, and a region "
                                   "is pinned")
            if not _matches(ident["region"], regions):
                return "deny", (f"AWS region `{ident['region']}` is not pinned "
                                f"(cloud.awsRegions: {', '.join(regions)})")
        return "ok", ""
    subs = pins["azureSubscriptions"]
    if not subs:
        if finding.destructive:
            return "unknown", ("nothing is pinned in cloud.azureSubscriptions, "
                               "so no identity was vouched for")
        return "ok", ""
    if ident.get("unknown"):
        return "unknown", ident["unknown"]
    if _matches(ident["name"], subs) or (
            ident.get("alt") and _matches(ident["alt"], subs)):
        return "ok", ""
    return "deny", (f"Azure subscription `{ident['name']}` is not pinned "
                    f"(cloud.azureSubscriptions: {', '.join(subs)})")


# --- scanning ---------------------------------------------------------------


def _stdout_literal(cmd):
    """What a pipeline stage feeds the next one, as far as crew can tell.

    A literal producer (`echo`, `printf`, `Write-Output`) feeds its words.
    Every OTHER stage is assumed to pass its own stdin through: `tee`, `cat`,
    `sort`, `grep`, a `sed` that happens not to touch the keyword. That reads
    a filter that removes a DROP as one that kept it, and that is the
    direction to be wrong in -- reading only the stage next door let
    `echo 'DROP TABLE t;' | tee q | psql` through."""
    if cmd is None:
        return None
    if cmd.words:
        head = _head_name(cmd.words[0])
        if head in ("echo", "printf", "write-output", "write-host"):
            return " ".join(w for w in cmd.words[1:] if not w.startswith("-"))
    return cmd.stdin


def _substitute(word, variables):
    """`$NAME` / `${NAME}` in `word` replaced from this script's own
    assignments -- never from the environment, which the guard cannot see
    change between here and the command running."""
    def repl(match):
        name = match.group(1) or match.group(2)
        return variables.get(name.lower(), match.group(0))
    out = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)",
                 repl, word)
    # The same object when nothing changed, so a `_Bare` word stays marked.
    return word if out == word else out


_PS_ENV_RE = re.compile(r"^\$env:([A-Za-z_][A-Za-z0-9_]*)(?:=(.*))?$",
                        re.IGNORECASE | re.DOTALL)
_PS_VAR_RE = re.compile(r"^\$([A-Za-z_][A-Za-z0-9_]*)(?:=(.*))?$", re.DOTALL)


def _ps_statement_assignment(words, env, variables):
    """Handle `$env:X = v`, `$x = v` and `Remove-Item env:X`; True if handled."""
    head = words[0]
    match = _PS_ENV_RE.match(head)
    if match:
        value = match.group(2)
        if value is None and len(words) > 2 and words[1] == "=":
            value = words[2]
        elif value is None and len(words) > 1 and words[1].startswith("="):
            value = words[1][1:]
        if value is not None:
            env[match.group(1).upper()] = value
            return True
    match = _PS_VAR_RE.match(head)
    if match and match.group(1).lower() != "env":
        value = match.group(2)
        if value is None and len(words) > 2 and words[1] == "=":
            value = words[2]
        if value is not None:
            variables[match.group(1).lower()] = value
            return True
    if head.lower() in ("remove-item", "ri", "del", "rm") and len(words) > 1:
        target = words[-1]
        if target.lower().startswith("env:"):
            env[target[4:].lstrip("\\/").upper()] = None
            return True
    return False


def scan(shell, text, env=None, depth=0):
    """Every finding in `text`, read as `shell` ("bash" or "powershell").

    `env` is the override dict inherited from an enclosing command (`env X=Y
    bash -c '...'`); it is copied, never mutated, so a nested scope cannot
    leak into its parent.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    if depth > MAX_DEPTH:
        return [Finding(UNREADABLE_RULE, text,
                        f"nested more than {MAX_DEPTH} shells or "
                        "substitutions deep, so the innermost command was "
                        "never read", None, True, None)]
    env = dict(env or {})
    variables = {}
    exported = set()
    lexer = _lex_ps if shell == "powershell" else _lex_bash
    cmds, subs = lexer(text)
    findings = []
    for sub in subs:
        findings.extend(scan(shell, sub, env, depth + 1))
    for cmd in cmds:
        if cmd.pipe_from is not None and cmd.stdin is None:
            cmd.stdin = _stdout_literal(cmd.pipe_from)
        words = [_substitute(w, variables) for w in cmd.words]
        if not words:
            continue
        if shell == "powershell":
            if _ps_statement_assignment(words, env, variables):
                continue
            words = [variables.get(w[1:].lower(), w)
                     if w.startswith("$") else w for w in words]
        else:
            head = words[0]
            if head in ("export", "declare", "typeset", "local", "readonly"):
                for word in words[1:]:
                    match = _ASSIGN_RE.match(word)
                    if match:
                        env[match.group(1)] = match.group(2)
                        variables[match.group(1).lower()] = match.group(2)
                        exported.add(match.group(1))
                    elif not word.startswith("-"):
                        exported.add(word)
                continue
            if head == "unset":
                for word in words[1:]:
                    env[word] = None
                continue
            if all(_ASSIGN_RE.match(w) for w in words):
                for word in words:
                    match = _ASSIGN_RE.match(word)
                    name, value = match.group(1), match.group(2)
                    variables[name.lower()] = value
                    # A bare assignment reaches a child process only when the
                    # name is already exported -- by this script or by the
                    # environment the shell was started with.
                    if name in exported or name in os.environ or name in env:
                        env[name] = value
                continue
        local_env = dict(env)
        fed = []
        argv = _unwrap(words, local_env, fed)
        if fed and argv and argv[0] == ":::":
            # `parallel ::: 'terraform destroy' ls`: every argument is a
            # command of its own.
            for job in argv[1:]:
                findings.extend(scan("bash", job, local_env, depth + 1))
            continue
        if not argv:
            continue
        found = _classify(argv, None if fed else cmd.stdin, local_env, shell,
                          depth)
        extra = _fed_finding(argv, local_env, *fed[-1]) if fed else None
        if extra is not None and not any(f.destructive for f in found):
            # The fed finding carries the identity too, so the read-only
            # identity row it replaces would only say the same thing twice.
            found = [f for f in found if f.rule != IDENTITY_RULE] + [extra]
        findings.extend(found)
    return findings


# --- deciding ---------------------------------------------------------------

_RANK = {"allow": 0, "ask": 1, "deny": 2}


def _approval_is_live(marker):
    """An approval marker from the last `GUARD_APPROVAL_TTL` seconds.

    `crew_config._approval_is_live`'s rule, restated rather than reached into:
    a marker that cannot be dated, or is dated in the future, is not one."""
    try:
        age = time.time() - os.path.getmtime(marker)
    except OSError:
        return False
    return abs(age) <= crew_state.GUARD_APPROVAL_TTL


def unattended(data, environ=None):
    """True when nobody is there to answer an `ask`.

    `CREW_UNATTENDED` decides when set (`0`/`false` forces attended). Else a
    truthy `CI`, or a session in `bypassPermissions` / `dontAsk` mode, counts as
    unattended: whether Claude Code surfaces a hook's `ask` in those modes is
    not something this hook can observe, and "could not tell" must not become
    permission to proceed.
    """
    environ = os.environ if environ is None else environ
    flag = (environ.get("CREW_UNATTENDED") or "").strip().lower()
    if flag:
        return flag not in ("0", "false", "no", "off")
    ci_flag = (environ.get("CI") or "").strip().lower()
    if ci_flag and ci_flag not in ("0", "false", "no"):
        return True
    mode = data.get("permission_mode") if isinstance(data, dict) else None
    return mode in ("bypassPermissions", "dontAsk")


def _judge_one(root, finding, pins, problem):
    """`(decision, reason, policy, marker, applies)` for one finding.

    `applies` is False for the findings that turned out to concern nothing:
    a SQL client or `ssh` aimed at no declared production target, or a
    read-only cloud command whose identity checked out. Those are not
    logged -- a row for every `psql` in a repo that declared no production
    would bury the rows that matter.
    """
    applies = True
    if finding.rule == UNREADABLE_RULE:
        return ("deny", f"[{UNREADABLE_RULE}] {finding.what}: crew could not "
                        "read this command, and a command it cannot read is "
                        "refused rather than passed unjudged.",
                "unreadable", "", True)
    if finding.rule in crew_state.GUARD_NAMES or \
            finding.rule in crew_state.PROD_GUARD_NAMES:
        out = crew_config.guard_decision(root, finding.rule, finding.text)
        decision = {"block": "deny"}.get(out["decision"], out["decision"])
        reason = f"[{finding.rule}] {finding.what}: {out['reason']}"
        verdict = (decision, reason, out["policy"], out["marker"])
        if finding.rule in crew_state.PROD_GUARD_NAMES:
            applies = bool(out["target"])
    else:
        verdict = ("allow", "", "", "")
        applies = False
    if finding.cloud is None:
        return verdict + (applies,)
    state, why = identity_verdict(finding, pins, problem)
    if state == "ok":
        return verdict + (applies,)
    if state == UNPINNED:
        # Passed, and said so: the row is what `main` turns into the one-time
        # note, so it applies even where the rule's own verdict did not.
        return verdict[:2] + (UNPINNED, "", True)
    if state == "deny":
        return ("deny", f"[{IDENTITY_RULE}] {finding.what}: {why}",
                "pinned", "", True)
    marker = crew_config.guard_marker(root, IDENTITY_RULE, finding.text)
    if _approval_is_live(marker):
        return verdict + (True,)
    ask = ("ask", f"[{IDENTITY_RULE}] {finding.what}: unknown identity -- "
                  f"{why}", "unknown", marker)
    return (ask if _RANK[ask[0]] > _RANK[verdict[0]] else verdict) + (True,)


def evaluate(root, tool_name, command, data=None, mode="block"):
    """The whole judgement for one tool call, as a dict. Pure apart from
    reading config and approval markers; `main` does the printing and logging.

    Returns `{"decision": allow|ask|deny|None, "reason", "rows", "unpinned",
    "note"}` where `rows` is one `(rule, policy, decision, target)` per
    finding for `.crew/guard.log` and `unpinned` names every read-only cloud
    call let through with nobody's identity pinned (`main` reports those
    once). In `report` mode `decision` is None -- NO decision, so Claude
    Code's own permission flow runs exactly as it would without this hook --
    and `note` says what `block` would have done. Never `allow`: that would
    skip the user's own prompt, and report mode judged nothing.
    """
    shell = "powershell" if tool_name == "PowerShell" else "bash"
    findings = scan(shell, command)
    pins, problem = cloud_pins(root)
    worst, reasons, rows, unpinned = "allow", [], [], []
    alone = unattended(data or {})
    for finding in findings:
        decision, reason, policy, marker, applies = _judge_one(
            root, finding, pins, problem)
        if not applies:
            continue
        if policy == UNPINNED:
            unpinned.append(finding.what)
            continue
        if decision == "ask" and alone:
            decision = "deny"
            reason += (" -- and nobody is attending to answer. To approve "
                       f"THIS command once, create {marker} and re-run "
                       f"(good for {crew_state.GUARD_APPROVAL_TTL // 60} "
                       "minutes)." if marker else
                       " -- and nobody is attending to answer.")
        rows.append((finding.rule, policy or "-", decision, finding.what))
        if decision != "allow":
            reasons.append(reason)
        if _RANK[decision] > _RANK[worst]:
            worst = decision
    reason = "crew cloud guard: " + " | ".join(reasons) if reasons else ""
    note = ""
    if mode == "report":
        rows = [(r, p, "report:" + d, t) for r, p, d, t in rows]
        if worst != "allow":
            note = (f"crew cloud guard (report mode, nothing enforced): block "
                    f"mode would {worst} this -- " + " | ".join(reasons))
        worst, reason = None, ""
    return {"decision": worst, "reason": reason, "rows": rows,
            "unpinned": unpinned, "note": note}


def resolve_mode(root):
    """`(mode, note)`: `off`, `report` or `block`. A config layer that exists
    and cannot be read forces `block` -- `roleWrites`' rule, for its reason.

    So does an ARMED guard over a repo layer whose `cloud` block is malformed
    (`"cloud": null`, a string where a list of globs belongs): that layer is
    invalid, not unpinned. An unarmed one stays off -- unlike unparseable
    JSON, a bad `cloud` block cannot be hiding the switch, which parsed."""
    mode = crew_config.resolve_guard(root, "cloudGuard")["effective"]
    repo_path = os.path.join(root, ".crew", "config.json")
    repo_state = crew_config.layer_state(repo_path)
    global_state = crew_config.layer_state(crew_config.GLOBAL_CONFIG_PATH)
    if "corrupt" in (repo_state, global_state):
        return "block", "a config layer could not be read; failing closed"
    if mode != "off" and crew_config.layer_state(repo_path, cloud=True) \
            == "corrupt":
        return "block", ("the repo's `cloud` block is malformed, so that "
                         "layer is invalid; failing closed")
    return mode, ""


def _log(root, row):
    """One row to `.crew/guard.log`. Never raises, never creates `.crew/` --
    `crew_config._log_guard`'s two rules, for its two reasons."""
    try:
        path = os.path.join(root, crew_state.GUARD_LOG_PATH)
        if not os.path.isdir(os.path.dirname(path)):
            return
        flat = ["-" if not f else str(f).replace("\t", " ").replace(
            "\r", " ").replace("\n", " ") for f in row]
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\t".join(flat) + "\n")
    except OSError:
        pass


def _emit(decision, reason, message=""):
    """ONE JSON object on stdout, or nothing. `allow` and None both print no
    decision; `message` is a `systemMessage` the user sees, which carries no
    permission decision of its own."""
    out = {}
    if decision not in ("allow", None):
        out["hookSpecificOutput"] = {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    if message:
        out["systemMessage"] = message
    if out:
        sys.stdout.write(json.dumps(out) + "\n")


UNPINNED_NOTED = os.path.join(".crew", ".cloud-guard-unpinned-noted")


def _note_unpinned(root, whats, command):
    """Say ONCE per repo that read-only cloud calls are passing unchecked
    because nothing is pinned -- a row in `.crew/guard.log` and a visible
    message -- then stay quiet. Once, because the alternative is a row per
    `aws s3 ls`; said at all, because a pass nobody reports looks exactly
    like a check that happened. Delete the marker to hear it again.

    A repo with no `.crew/` (armed from the machine-global layer) has nowhere
    to record that it was said, and `.crew/` is never created here -- so it
    is said EVERY time there, rather than never."""
    marker = os.path.join(root, UNPINNED_NOTED)
    if not whats or os.path.exists(marker):
        return ""
    said = (f"crew cloud guard: `{whats[0]}` runs as an identity crew cannot "
            "name, and nothing is pinned in cloud.* to check it against. "
            "Read-only cloud calls pass unchecked until cloud.awsProfiles / "
            "cloud.awsRegions / cloud.azureSubscriptions pin something; ")
    if not os.path.isdir(os.path.dirname(marker)):
        return said + ("this repo has no .crew/ to record having said so, "
                       "so it is said every time.")
    _log(root, (str(int(time.time())), IDENTITY_RULE, UNPINNED, "allow",
                whats[0], command))
    try:
        with open(marker, "a", encoding="utf-8"):
            pass
    except OSError:
        pass
    return said + f"this is said once ({UNPINNED_NOTED})."


def _read_input():
    """`(data, command, problem)`. `data` None means not ours to judge.

    `problem` is non-empty when the input could not be read as a Bash or
    PowerShell call at all -- undecodable, not JSON, not an object, or a
    Bash/PowerShell call with no string `tool_input.command`. The hook is
    registered on those two tools only, so input it cannot read is a call
    it cannot judge, and an armed guard refuses it."""
    try:
        raw = sys.stdin.buffer.read()
        if raw[:3] == b"\xef\xbb\xbf":
            raw = raw[3:]
        if not raw.strip():
            return {}, None, "the hook input was empty"
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return {}, None, "the hook input did not parse as UTF-8 JSON"
    if not isinstance(data, dict):
        return {}, None, "the hook input is not a JSON object"
    if data.get("tool_name") not in ("Bash", "PowerShell"):
        return None, None, ""
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) \
        else None
    if not isinstance(command, str):
        return data, None, "the hook input carries no string tool_input.command"
    if not command.strip():
        return None, None, ""
    return data, command, ""


# Set by each wrapper for the call it makes, never read from anywhere else:
# `bash` from cloud-guard.sh, `powershell` from cloud-guard.ps1. Unset (the
# module run directly) judges every call.
FLAVOUR_VAR = "CREW_CLOUD_GUARD_FLAVOUR"
_PS1_TWIN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "cloud-guard.ps1")


def stands_down(tool_name, environ=None):
    """True when the OTHER flavour judges this call, so this one must not.

    Both flavours are registered, and on Windows both run. Which one judges
    is decided by the TOOL, never by what this host looks like:

    - `bash` judges every `Bash` call, always. A Bash call is running in
      the very bash this flavour runs in, so no host condition can mean
      "bash is not here to judge it" -- and so nothing the environment says
      (an `OS` value, a same-named executable on PATH) can stand it down.
    - `bash` stands down for a `PowerShell` call only when the `.ps1` twin
      will run past its own first line: `OS` is `Windows_NT` (the exact test
      that twin makes, read from the same environment both inherit) and the
      twin is beside this file. Off Windows the twin exits at once, so bash
      judges PowerShell calls there.
    - `powershell` judges every `PowerShell` call and stands down for every
      `Bash` call, which the rule above guarantees bash judges.
    """
    environ = os.environ if environ is None else environ
    flavour = environ.get(FLAVOUR_VAR, "")
    if flavour == "powershell":
        return tool_name == "Bash"
    if flavour == "bash":
        return tool_name == "PowerShell" \
            and environ.get("OS") == "Windows_NT" \
            and os.path.isfile(_PS1_TWIN)
    return False


def main():
    data, command, problem = _read_input()
    if data is None:
        return 0
    if not problem and stands_down(data.get("tool_name")):
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
    root = root if isinstance(root, str) else "."
    try:
        mode, note = resolve_mode(root)
    except Exception as exc:  # pylint: disable=broad-except
        # Whether the guard is even ON is unknown here. It is opt-in, so an
        # unreadable switch is reported rather than turned into a refusal of
        # every command on every machine -- the failure that removed the last
        # command guard. `resolve_mode` already fails closed on a config file
        # it can see and cannot read.
        sys.stderr.write(f"cloud-guard: could not read guards.cloudGuard "
                         f"({type(exc).__name__}); not judged.\n")
        return 0
    if mode == "off":
        return 0
    if problem:
        # Armed, and handed something it cannot read as a command. Refuse in
        # every armed mode: report mode's promise is "nothing refused that
        # was judged", and this was not judged.
        _log(root, (str(int(time.time())), UNREADABLE_RULE, mode, "deny",
                    "malformed-input", "-"))
        _emit("deny", f"crew cloud guard: {problem}; refusing rather than "
                      "letting a command through unjudged.")
        return 0
    try:
        result = evaluate(root, data["tool_name"], command, data, mode)
    except Exception as exc:  # pylint: disable=broad-except
        # The guard IS on and could not finish. Refuse: a check that could not
        # run is not a check that passed.
        _log(root, (str(int(time.time())), "cloudGuard", mode, "deny",
                    f"internal-error:{type(exc).__name__}", command))
        _emit("deny", f"crew cloud guard: internal error "
                      f"({type(exc).__name__}) while judging this command; "
                      "refusing rather than letting it through unjudged.")
        return 0
    now = str(int(time.time()))
    for rule, policy, decision, target in result["rows"]:
        _log(root, (now, rule, policy, decision, target, command))
    reason = result["reason"]
    if note and reason:
        reason += f" ({note})"
    message = result["note"] or _note_unpinned(root, result["unpinned"],
                                               command)
    _emit(result["decision"], reason, message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
