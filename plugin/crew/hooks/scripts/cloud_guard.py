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
    terraform/tofu/terragrunt workspace delete,
      a destroy in every armed state; new|
      select -or-create once `environments`
      is configured                                 guards.terraformApply
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

ENVIRONMENTS (T-0005, crew 1.0.41). A terraform finding is also judged by its
target environment and by whether it destroys, both read without running
terraform (the hook has 15 seconds). The environment is `nonProd` (a name
matching a repo-only `environments.nonProd` glob), `prod` (a name matching
none) or `unknown` -- no signal, a signal that is not a literal, signals that
classify differently, or an `environments` block crew cannot read. The names
come from `TF_WORKSPACE`, a literal `workspace select|new X` earlier in the
same command, the `.terraform/environment` file under the payload's `cwd`
(never when the command changes directory or switches workspace anywhere,
and a missing file is unknown, not `default`), `-var environment=X` /
`TF_VAR_environment`, and a saved plan's sidecar. A destroy is `yes`
(`destroy`, `apply -destroy`, `apply -replace`, `workspace delete`, a saved
plan whose sidecar lists a delete), `no` (a saved plan whose sha256-bound
sidecar lists none, `workspace new`, `select -or-create`) or `unknown` (no
saved plan, terragrunt, a missing/stale/malformed sidecar), and unknown counts
as yes. The sidecar is `.crew/tfplan/<sha256>.json`, written OUTSIDE the hook
by `crew_tfplan.py summarize`. Under `terraformApply: ask`, a non-destroying
nonProd target runs unattended and is logged; production does too only when
`environments.prodUnattended` is true in BOTH config layers, and says so on
screen; every other case asks. Under `allow` a destroy -- yes or unknown --
now ASKS (BREAKING in 1.0.41), and so is denied unattended. `block` is never
loosened. An unknown environment is narrower than production: nothing allows
it unattended. See `_terraform_verdict`.

THE LITERAL-WORD ALLOWLIST (T-0005 Steps 8-10). A line that RUNS terraform,
terragrunt or tofu -- a command word, dequoted, after assignments and
`_unwrap`'s wrappers, or a command inside `bash -c`/`eval`/`pwsh -c`/a
substitution (`crew_guards.command_trigger`, its own reader; PowerShell:
`ps_trigger`, the same rule) -- is judged only when every word on it is a
plain literal (`_PLAIN_WORD_RE`, joined by `_PLAIN_OPS`). Anything else on
such a line is "could not tell": asked when attended, denied unattended and
under `block`, never allowed. So is a plain line that runs terraform where the
lexer does not look (an alias, a binary the line copies and runs by its new
name, zsh's `=terraform`, `flock`/`ssh`, `Start-Process`: `unseen`). A
read-only subcommand is not gated. The check reads the raw text first
(`_literal_gate`), so no lexer bug turns a shape it misread into an allow.
Direct use only (Step 10): a disguise -- a rename crew does not see made, `env
-S`, BusyBox, git `!` aliases, an interpreter, a script, an unlisted wrapper
-- is out of scope (README, "What the guard does not catch"; T-0044).

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
anything an MCP server does -- and for the terraform name, one built from
parts crew never sees whole (`$TF`, `$(printf te)$(printf rraform)`, a
PowerShell concatenation), a wildcard keeping fewer than three of its
letters (`t*`) on a line naming no verb, or another name for terraform made
outside the line (a profile `alias`, a `ln -s` link, a container's entrypoint).
What `xargs`/`parallel` append is not seen either,
so a destructive-capable tool behind one is judged as destructive, and one
whose executable is a placeholder is refused as unreadable. For terraform it
does not read `-var-file` or `*.tfvars`, an HCL `cloud {}`/`backend` block's
workspace name, terragrunt layouts, or a TFC/HCP workspace or run driven by
`curl` or `gh api` -- those are unknown or unseen. Native permissions and
restricted credentials are the boundary; this is a tripwire in front of them.

WHY THE PARSER IS HAND-ROLLED. `shlex` knows nothing of `&&`, heredocs, `$( )`
or PowerShell, and the old command guard (removed in 0.19.52) was removed
precisely because it matched words anywhere -- inside commit messages and
comment bodies. So this reads each shell into simple commands first and judges
only the command a segment actually runs, never a word inside an argument.
"""
import base64
import collections
import fnmatch
import hashlib
import json
import os
import re
import stat
import sys
import time

import crew_config
import crew_state
from crew_guards import _head_name as _guards_head_name
from crew_guards import command_trigger, first_non_literal, ps_trigger, \
    skip_wrapper_options, tf_skip_options as _tf_skip_options


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

# `scope` is None for every finding except terraform's, where it carries what
# `_tf_environment` and `_tf_destroy` need once the WHOLE command has been read
# (a `cd` anywhere in it turns the workspace-file fallback off, so the answer
# cannot be settled while the scan is still going). A default, so every
# constructor written before it existed stays valid.
Finding = collections.namedtuple(
    "Finding", ("rule", "text", "what", "cloud", "destructive", "identity",
                "scope"), defaults=(None,))

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
        # An output redirect to anything but the null device. It runs before
        # terraform reads its plan, so it could be rewriting that plan.
        self.writes = False
        # Followed by `||`: the next command runs only if this one FAILS,
        # which no in-sequence reading of this one can account for.
        self.or_next = False

    def has_content(self):
        return bool(self.words) or self.stdin is not None or self.writes


# --- bash -------------------------------------------------------------------

# Reserved words that can open a simple command. `time` is NOT here: it takes
# options (`time -p terraform destroy`), so it is unwrapped as a wrapper.
_BASH_RESERVED = frozenset(("{", "}", "!", "if", "then", "else", "elif", "fi",
                            "do", "done", "while", "until", "case", "esac",
                            "coproc"))

# Redirection operators that open their target for writing. `<>` opens it
# read-write, so it is one.
_BASH_WRITES = frozenset((">", ">>", ">|", "<>"))


# --- reading bash the way bash reads it, and saying when it cannot ----------
#
# Round 3 of T-0005's review: a lexer that disagrees with bash about where a
# quote or a substitution ends does not merely misread one word -- the
# disagreement swallows everything after it, commands included. So three
# things, not one:
#
#   * `_bash_close` finds the end of `${ }` / `$( )` as bash does, nested
#     quoting, `$'...'`, backslashes and comments included;
#   * wherever crew still cannot be sure it split the line as bash will --
#     quoting inside `${...}`, a quote or substitution that never closes, a
#     heredoc or `case` inside `$( )`, a control character, `\r#` -- the
#     lexer DOUBTS, and `scan` counts one command more for it, so the saved
#     plan's apply is never "the only command" (fail closed);
#   * the first doubt in each reading also hands the text after it to
#     `subs`, read again from scratch -- the other way the shell might split
#     it -- so a command bash would run is judged under either reading.

# Control characters other than tab and newline. Bash reads them as word
# characters; crew reads `\r` as a blank (a shell that drops CR sees
# `destroy\r` as `destroy`). The readings differ, and crew cannot tell which
# shell will run the line.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# Inside `${...}`: quoting whose meaning bash decides by the operator, the
# quoting context around it and posix mode.
_PARAM_HARD_RE = re.compile(r"['\"\\`]")
# Inside `$( )` or backticks: what `_bash_close` does not model -- a heredoc
# body, whose `)` bash does not count, and `case` patterns -- and, in
# backticks, backslash escaping, which bash applies twice there.
_SUBST_HARD_RE = re.compile(r"<<|\bcase\b")
# Nesting deeper than this inside one `${ }` / `$( )` is not followed (it is
# reported as unclosed, so it doubts and fails closed) -- the bound keeps a
# hostile payload from exhausting the stack.
_CLOSE_MAX_NEST = 64


def _skip_ansi_c(text, i):
    """The index after the $'...' starting at `text[i]`, or None if open."""
    j, n = i + 2, len(text)
    while j < n:
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == "'":
            return j + 1
        j += 1
    return None


def _skip_backtick(text, i):
    """The index after the backtick string at `text[i]`, or None if open."""
    j, n = i + 1, len(text)
    while j < n:
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == "`":
            return j + 1
        j += 1
    return None


def _skip_bash_double(text, i, nest=0):
    """The index after the "..." at `text[i]`, or None if it never closes.
    Inside it only `\\`, `$( )`, `${ }` and backticks are special."""
    j, n = i + 1, len(text)
    while j < n:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == '"':
            return j + 1
        if text.startswith("$(", j) or text.startswith("${", j):
            k, closed = _bash_close(text, j + 1, nest=nest + 1)
            if not closed:
                return None
            j = k + 1
            continue
        if c == "`":
            j = _skip_backtick(text, j)
            if j is None:
                return None
            continue
        j += 1
    return None


def _bash_close(text, start, nest=0):
    """`(index, closed)` for the bracket closing the `(` or `{` at
    `text[start]`, read as bash reads it: `\\x`, '...', $'...', "..." with
    its own substitutions, backticks, nested `${ }` and `$( )`, and -- in
    parentheses -- a `#` comment at the start of a word. Unclosed, or nested
    past `_CLOSE_MAX_NEST`: `(len(text), False)`."""
    n = len(text)
    if nest > _CLOSE_MAX_NEST:
        return n, False
    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else ")"
    depth, i = 0, start
    while i < n:
        c = text[i]
        skip = None
        if c == "\\":
            skip = i + 2
        elif text.startswith("$'", i):
            skip = _skip_ansi_c(text, i)
        elif c == "'":
            end = text.find("'", i + 1)
            skip = end + 1 if end >= 0 else None
        elif c == '"':
            skip = _skip_bash_double(text, i, nest)
        elif c == "`":
            skip = _skip_backtick(text, i)
        elif text.startswith("${", i) or text.startswith("$(", i):
            k, closed = _bash_close(text, i + 1, nest + 1)
            skip = k + 1 if closed else None
        elif open_ch == "(" and c == "#" and text[i - 1] in " \t\n;&|()<>":
            end = text.find("\n", i)
            skip = end if end >= 0 else None
        else:
            if c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return i, True
            i += 1
            continue
        if skip is None:
            return n, False
        i = skip
    return n, False


def _read_bash_double(text, i, subs, doubt=None):
    """A "..." word starting at `text[i]`; returns (value, next index).
    `doubt(reason, alt)` is told wherever this cannot be sure it reads the
    string as bash will."""
    doubt = doubt or (lambda reason, alt=None: None)
    buf, j, n = [], i + 1, len(text)
    while j < n and text[j] != '"':
        c = text[j]
        if c == "\\" and j + 1 < n and text[j + 1] in '"\\$`\n':
            if text[j + 1] != "\n":
                buf.append(text[j + 1])
            j += 2
            continue
        if text.startswith("$(", j):
            k, closed = _bash_close(text, j + 1)
            subs.append(text[j + 2:k])
            if not closed or _SUBST_HARD_RE.search(text[j + 2:k]):
                # Unclosed, the substitution already IS the rest.
                doubt("a `$( )` crew cannot delimit as bash does",
                      text[j + 2:] if closed else None)
            buf.append(text[j:k + 1])
            j = k + 1
            continue
        if text.startswith("${", j):
            # Its own quotes do not end the string: `"${x:-"'"}"` is ONE
            # word to bash, and the `'` inside quotes nothing.
            k, closed = _bash_close(text, j + 1)
            _expansion_subs(text[j + 2:k], subs)
            if not closed or _PARAM_HARD_RE.search(text[j + 2:k]):
                doubt("quoting inside `${...}`", text[j + 2:])
            buf.append(text[j:k + 1])
            j = k + 1
            continue
        if c == "`":
            end = _skip_backtick(text, j)
            k = n if end is None else end - 1
            subs.append(text[j + 1:k])
            if end is None or "\\" in text[j + 1:k]:
                doubt("a backtick substitution crew cannot delimit",
                      None if end is None else text[j + 1:])
            buf.append(text[j:k + 1])
            j = k + 1
            continue
        buf.append(c)
        j += 1
    if j >= n:
        doubt("a double quote that never closes", text[i + 1:])
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


def _expansion_subs(text, subs):
    """Append to `subs` every command substitution the shell runs while it
    expands `text` -- an unquoted heredoc body, or the inside of `${...}` or
    `$((...))`: `$( )` and backticks, at any depth of `${ }` or arithmetic.
    A backslash escapes `$`, `` ` `` and itself, as it does there."""
    j, n = 0, len(text)
    while j < n:
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if text.startswith("$((", j) and _is_arith(text, j):
            j += 3
            continue
        if text.startswith("$(", j):
            close, _closed = _bash_close(text, j + 1)
            subs.append(text[j + 2:close])
            j = close + 1
            continue
        if c == "`":
            end = _skip_backtick(text, j)
            close = n if end is None else end - 1
            subs.append(text[j + 1:close])
            j = close + 1
            continue
        j += 1


def _is_arith(text, i):
    """True when the `$((` at `text[i]` is arithmetic. Bash reads it as
    `$( (subshell) ... )` -- a command -- unless the inner `(` closes
    straight onto the outer `)`: `$((echo a); (echo b))` runs both echoes."""
    m, _closed = _bash_close(text, i + 2)
    return text[m + 1:m + 2] == ")"


def _heredoc_line(text, i, joins):
    """The logical line starting at `text[i]` and the index after it. With
    `joins` (an unquoted delimiter) bash drops each backslash-newline before
    comparing the line with the delimiter, so `E\\<newline>OF` ends a heredoc
    delimited by `EOF`; an escaped backslash (`\\\\`) does not join."""
    n, parts = len(text), []
    while True:
        end = text.find("\n", i)
        end = n if end < 0 else end
        line = text[i:end]
        i = end + 1
        trailing = len(line) - len(line.rstrip("\\"))
        if joins and trailing % 2 and i < n:
            parts.append(line[:-1])
            continue
        parts.append(line)
        return "".join(parts), i


def _read_heredocs(text, i, pending, subs):
    """Consume heredoc bodies starting at `text[i]`; attach each to its
    command. An unquoted delimiter leaves the body open to expansion, so its
    substitutions go to `subs` and are judged -- and counted -- as commands.

    A line that is the delimiter only once a trailing CR is dropped ends the
    heredoc under a shell that ignores CR and not under one that does not,
    and crew cannot tell which will run it. It is read both ways: here as
    the end, and -- through `subs` -- the body and the text after the next
    exact delimiter line as the other shell reads them."""
    n = len(text)
    for delim, strip_tabs, cmd, quoted in pending:
        lines = []
        while i < n:
            line, i = _heredoc_line(text, i, not quoted)
            check = line.lstrip("\t") if strip_tabs else line
            if check == delim:
                break
            if check.rstrip("\r") == delim:
                alt, j = [line], i
                while j < n:
                    other, j = _heredoc_line(text, j, not quoted)
                    if (other.lstrip("\t") if strip_tabs else other) == delim:
                        subs.append(text[j:])
                        break
                    alt.append(other)
                if not quoted:
                    _expansion_subs("\n".join(alt), subs)
                break
            lines.append(line)
        body = "\n".join(lines)
        if not quoted:
            _expansion_subs(body, subs)
        cmd.stdin = body if cmd.stdin is None else cmd.stdin + "\n" + body
    return i


def _lex_bash(text, unsure=None):
    """`text` as a list of `_Cmd`, plus every substitution found in it.
    Every place it cannot be sure it reads `text` as bash will is appended
    to `unsure` (see `_bash_close`'s section)."""
    cmds, subs, pending = [], [], []
    unsure = [] if unsure is None else unsure
    state = {"cur": _Cmd(), "word": None, "redirect": None, "quoted": False,
             "reread": False}

    def doubt(reason, alt=None):
        unsure.append(reason)
        # One re-read per reading: it covers everything after the doubt,
        # later doubts included, and a hostile line cannot fan it out.
        if alt and alt.strip() and not state["reread"]:
            state["reread"] = True
            subs.append(alt)

    def end_word():
        word = state["word"]
        if word is None:
            return
        value = "".join(word)
        state["word"] = None
        quoted, state["quoted"] = state["quoted"], False
        redirect = state["redirect"]
        if redirect is not None:
            # The word after a redirection operator is its target, never an
            # argument -- except that a heredoc's is its delimiter and a
            # here-string's is the command's stdin.
            state["redirect"] = None
            if redirect == "<<<":
                state["cur"].stdin = value
            elif redirect in ("<<", "<<-"):
                # Any quoting in the delimiter keeps the body literal.
                pending.append((value, redirect == "<<-", state["cur"],
                                quoted))
            elif redirect in _BASH_WRITES and value != "/dev/null":
                state["cur"].writes = True
            return
        state["cur"].words.append(value)

    def finish(pipe=False):
        end_word()
        if state["redirect"] is not None:
            # A redirection with no target: bash found a word here that
            # crew did not (`<<<\r;`). Left pending, the NEXT command's
            # head would be taken as its target and the command never read.
            doubt("a redirection with no target")
            state["redirect"] = None
        cur = state["cur"]
        if cur.has_content():
            cmds.append(cur)
        state["cur"] = _Cmd(pipe_from=cur if pipe else None)

    def add(chars, quoted=False):
        if state["word"] is None:
            state["word"] = []
        state["word"].append(chars)
        state["quoted"] = state["quoted"] or quoted

    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            if text[i + 1:i + 2] == "\n":
                i += 2
                continue
            add(text[i + 1:i + 2], quoted=True)
            i += 2
            continue
        if c == "'":
            j = text.find("'", i + 1)
            if j < 0:
                doubt("a single quote that never closes", text[i + 1:])
                j = n
            add(text[i + 1:j], quoted=True)
            i = j + 1
            continue
        if text.startswith("$'", i):
            if _skip_ansi_c(text, i) is None:
                doubt("a $'...' that never closes", text[i + 2:])
            value, i = _read_ansi_c(text, i)
            add(value, quoted=True)
            continue
        if c == '"':
            value, i = _read_bash_double(text, i, subs, doubt)
            add(value, quoted=True)
            continue
        if text.startswith("$((", i) and _is_arith(text, i):
            # Arithmetic runs nothing itself, but a substitution inside it
            # does: `$(( $(cp evil p.tfplan) 10 ))`.
            k, _closed = _bash_close(text, i + 1)
            _expansion_subs(text[i + 3:k], subs)
            add(text[i:k + 1])
            i = k + 1
            continue
        if text.startswith("$(", i) or text.startswith("<(", i) \
                or text.startswith(">(", i):
            # `$((cp a b) )` and `<((cmd))` are a subshell inside, not
            # arithmetic: the whole inside is a command.
            k, closed = _bash_close(text, i + 1)
            subs.append(text[i + 2:k])
            if not closed or _SUBST_HARD_RE.search(text[i + 2:k]):
                # Unclosed, the substitution already IS the rest.
                doubt("a `$( )` crew cannot delimit as bash does",
                      text[i + 2:] if closed else None)
            add(text[i:k + 1])
            i = k + 1
            continue
        if text.startswith("${", i):
            k, closed = _bash_close(text, i + 1)
            _expansion_subs(text[i + 2:k], subs)
            if not closed or _PARAM_HARD_RE.search(text[i + 2:k]):
                doubt("quoting inside `${...}`", text[i + 2:])
            add(text[i:k + 1])
            i = k + 1
            continue
        if c == "`":
            end = _skip_backtick(text, i)
            k = n if end is None else end - 1
            subs.append(text[i + 1:k])
            if end is None or "\\" in text[i + 1:k]:
                doubt("a backtick substitution crew cannot delimit",
                      None if end is None else text[i + 1:])
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
                i = _read_heredocs(text, i, pending, subs)
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
                # beyond the digit that follows. `>&file` (no digit) is
                # bash's `&>file`: stdout and stderr both written to a file.
                state["word"] = None
                i += len(op)
                j = i
                while i < n and text[i].isdigit():
                    i += 1
                if text[i:i + 1] == "-":
                    i += 1
                elif i == j and op == ">&":
                    state["redirect"] = ">"
                continue
            state["word"] = None
            state["redirect"] = op
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
                if two == "||":
                    state["cur"].or_next = True
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
_PS_REDIRECT_TO_RE = re.compile(r"^(?:\d|\*)?>>?([^&>].*)$", re.DOTALL)
# A bare word that, with `&N` after it, is a stream merge (`2>&1`, `*>&1`).
_PS_MERGE_RE = re.compile(r"^(?:\d|\*)?>$")


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


# What PowerShell's tokenizer reads as a quote or a line end and crew's
# ASCII lexer would not: the typographic quotes (any single-quote character
# opens or closes a '...' string, any double one a "..." string) and a bare
# CR, which ends a line -- and a `#` comment -- exactly as LF does.
_PS_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201a": "'",
                            "\u201b": "'", "\u201c": '"', "\u201d": '"',
                            "\u201e": '"'})


def _ps_normalise(text):
    """`text` with PowerShell's other quote and newline spellings mapped to
    the ones `_lex_ps` reads, and whether anything was mapped."""
    out = text.replace("\r\n", "\n").replace("\r", "\n").translate(_PS_QUOTES)
    return out, out != text


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
                state["cur"].or_next = True
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
            if state["word"] is not None and state["bare"] \
                    and _PS_MERGE_RE.match("".join(state["word"])) \
                    and text[i + 1:i + 2].isdigit():
                # `2>&1`, `*>&1`: a stream merged into another, one
                # redirection token -- not the `&` that starts a command.
                add(text[i:i + 2], bare=True)
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
                if word.lower() != "$null":
                    cmd.writes = True
                continue
            if _PS_REDIRECT_RE.match(word):
                skip = not word.endswith(("1", "2", "3", "4", "5", "6"))
                continue
            attached = _PS_REDIRECT_TO_RE.match(word)
            if attached:
                # `>p.tfplan`, `2>>log`: the operator and its target in one
                # word, which is still a redirect and never an argument.
                if attached.group(1).lower() != "$null":
                    cmd.writes = True
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

# `sudo`, `env`, `su`/`runuser` and `_PLAIN_WRAPPERS` are walked by
# `_getopt` in `_unwrap`, not by this table.
_WRAPPER_VALUE_OPTS = {
    "doas": frozenset(("-u", "-C")),
    "nice": frozenset(("-n", "--adjustment")),
    "timeout": frozenset(("-s", "-k", "--signal", "--kill-after")),
    "stdbuf": frozenset(("-i", "-o", "-e", "--input", "--output", "--error")),
    "xargs": frozenset(("-I", "-J", "-R", "-n", "-P", "-d", "-L", "-s", "-E",
                        "-a", "--max-args", "--max-procs", "--delimiter",
                        "--arg-file", "--max-lines", "--max-chars",
                        "--process-slot-var")),
    "parallel": frozenset(("-j", "-P", "-S", "-a", "-d", "-n", "-N", "-E",
                           "-I", "--jobs", "--sshlogin", "--arg-file",
                           "--delimiter", "--max-args", "--joblog",
                           "--results", "--tmpdir", "--colsep", "--wd",
                           "--workdir", "--slf", "--sshloginfile")),
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


def _getopt(words, shorts, longs, stop=()):
    """Walk the options at the front of `words` as GNU `getopt_long` does
    with a leading `+` (stop at the first operand, or after `--`):
    `-abVALUE`, `-b VALUE`, `--name=VALUE`, `--name VALUE`, and any unique
    abbreviation of a long name. `shorts` and `longs` map an option to
    "req" (takes a value, attached or as the next word) or "opt" (a value
    only when attached); an option absent from both takes none.

    Returns `(opts, rest)`: `opts` is `[(name, value)]` with long names
    resolved in full, `rest` the words after the options. Parsing stops
    right after an option named in `stop`, so the caller can splice words
    in where it stood (`env -S`)."""
    opts, index = [], 0
    while index < len(words):
        word = words[index]
        if word == "--":
            return opts, words[index + 1:]
        if not word.startswith("-") or word == "-":
            break
        index += 1
        if word.startswith("--"):
            name, sep, value = word[2:].partition("=")
            hits = [full for full in longs if full.startswith(name)]
            if name not in longs and len(hits) == 1:
                name = hits[0]
            if not sep:
                value = None
                if longs.get(name) == "req" and index < len(words):
                    value = words[index]
                    index += 1
            opts.append((name, value))
        else:
            for pos in range(1, len(word)):
                letter, kind = word[pos], shorts.get(word[pos])
                if kind:
                    value = word[pos + 1:] or None
                    if value is None and kind == "req" and index < len(words):
                        value = words[index]
                        index += 1
                    opts.append((letter, value))
                    break
                opts.append((letter, None))
        if opts and opts[-1][0] in stop:
            break
    return opts, words[index:]


_ENV_SHORT = {"C": "req", "S": "req", "u": "req", "a": "req",
              # BSD env: -P altpath, -L/-U user[/class].
              "P": "req", "L": "req", "U": "req"}
_ENV_LONG = {"chdir": "req", "split-string": "req", "unset": "req",
             "argv0": "req", "ignore-environment": None, "null": None,
             "debug": None, "help": None, "version": None,
             "block-signal": "opt", "default-signal": "opt",
             "ignore-signal": "opt", "list-signal-handling": None}

# `sudo`'s getopt string is `+Aa:BbC:c:D:Eeg:Hh::iKklNnPp:R:r:SsT:t:U:u:Vv`.
_SUDO_SHORT = dict({letter: "req" for letter in "aCcDgpRrTtUu"}, h="opt")
_SUDO_LONG = {"close-from": "req", "chdir": "req", "group": "req",
              "host": "req", "prompt": "req", "chroot": "req", "role": "req",
              "type": "req", "command-timeout": "req", "other-user": "req",
              "user": "req", "preserve-env": "opt", "askpass": None,
              "background": None, "bell": None, "edit": None,
              "set-home": None, "help": None, "login": None,
              "remove-timestamp": None, "reset-timestamp": None,
              "list": None, "non-interactive": None, "preserve-groups": None,
              "stdin": None, "shell": None, "version": None, "validate": None}
# `-D`/`--chdir` and `-R`/`--chroot` move it outright; `-i`/`--login` runs
# the command through the target user's login shell, in that user's home.
_SUDO_MOVES = frozenset(("D", "chdir", "R", "chroot", "i", "login"))

# Wrappers that run the command they are given unchanged, each as
# `(shorts, longs, moves, operands)`: its options, the options that change
# the directory the command runs in ("*" when the wrapper always does), and
# how many operands stand between its options and the command. They used to
# be unknown heads, and a command behind an unknown head is never read:
# `setsid terraform destroy` ran unjudged.
_PLAIN_WRAPPERS = {
    "setsid": ({}, {"ctty": None, "fork": None, "wait": None}, (), 0),
    "ionice": ({"c": "req", "n": "req", "p": "req", "P": "req", "u": "req"},
               {"class": "req", "classdata": "req", "pid": "req",
                "pgid": "req", "uid": "req", "ignore": None}, (), 0),
    "chroot": ({}, {"userspec": "req", "groups": "req", "skip-chdir": None},
               ("*",), 1),
    "taskset": ({}, {"all-tasks": None, "pid": None, "cpu-list": None}, (),
                1),
    "chrt": ({"T": "req", "P": "req", "D": "req"},
             {"sched-runtime": "req", "sched-period": "req",
              "sched-deadline": "req"}, (), 1),
    "unshare": (dict({"S": "req", "G": "req", "R": "req", "w": "req"},
                     **{letter: "opt" for letter in "muinpUCT"}),
                {"setuid": "req", "setgid": "req", "root": "req",
                 "wd": "req", "map-user": "req", "map-group": "req",
                 "map-users": "req", "map-groups": "req",
                 "propagation": "req", "setgroups": "req",
                 "monotonic": "req", "boottime": "req", "mount": "opt",
                 "uts": "opt", "ipc": "opt", "net": "opt", "pid": "opt",
                 "user": "opt", "cgroup": "opt", "time": "opt",
                 "kill-child": "opt", "mount-proc": "opt",
                 "mount-binfmt": "opt"}, ("R", "root", "w", "wd"), 0),
    "nsenter": (dict({"t": "req", "S": "req", "G": "req"},
                     **{letter: "opt" for letter in "muinpUCTrw"}),
                {"target": "req", "setuid": "req", "setgid": "req",
                 "root": "opt", "wd": "opt", "mount": "opt", "uts": "opt",
                 "ipc": "opt", "net": "opt", "pid": "opt", "user": "opt",
                 "cgroup": "opt", "time": "opt"},
                ("r", "root", "w", "wd"), 0),
    "watch": ({"n": "req", "d": "opt", "q": "req"},
              {"interval": "req", "differences": "opt", "equexit": "req",
               "errexit": None, "exec": None}, (), 0),
}

# `su`/`runuser`: the command is `-c`'s value, run by the target user's
# shell; `-`, `-l`, `--login` start in that user's home.
_SU_SHORT = {"c": "req", "g": "req", "G": "req", "s": "req", "w": "req",
             "u": "req"}
_SU_LONG = {"command": "req", "session-command": "req", "group": "req",
            "supp-group": "req", "shell": "req",
            "whitelist-environment": "req", "user": "req", "login": None,
            "preserve-environment": None, "pty": None, "fast": None}


def _moved(ctx):
    if ctx is not None:
        ctx["cd"] = True


def _clear_env(env):
    """`env -i`: the command starts with nothing inherited, ours included."""
    for key in set(os.environ) | set(env) | set(_IDENTITY_VARS) | {
            "TF_WORKSPACE", "TF_DATA_DIR", "TF_VAR_environment"}:
        env[key] = None


def _unwrap_su(head, words, ctx):
    """`su`/`runuser` as the argv it runs: `sh -c <command>` for `-c`, the
    command itself for `runuser -u USER cmd`, else the user's shell."""
    command, user, index, login = None, None, 0, False
    # GNU getopt PERMUTES here: `su - root -c 'x'` puts -c after the user.
    while index < len(words):
        opts, rest = _getopt(words[index:], _SU_SHORT, _SU_LONG)
        for name, value in opts:
            if name in ("c", "command", "session-command"):
                command = value
            elif name in ("u", "user"):
                user = value
            elif name in ("l", "login"):
                login = True
        if not rest:
            break
        if rest[0] == "-":
            login = True
        elif user is not None and head == "runuser":
            if login:
                _moved(ctx)
            return rest
        index = len(words) - len(rest) + 1
    if login:
        _moved(ctx)
    return ["sh", "-c", command] if command is not None else []


def _unwrap(words, env, fed=None, ctx=None):
    """Strip assignments and wrappers off `words`; returns the argv that runs.

    `env` is the per-command override dict, updated in place: `X=Y cmd` and
    `env X=Y cmd` set `X`, `env -u X` and `env -i` unset. `fed`, when a list,
    collects every `_ARGV_FEEDERS` wrapper stripped on the way: the argv
    returned is then NOT the whole argv that runs. `ctx`, when a dict, has
    `cd` set by every wrapper option that changes the directory the command
    runs in (`env -C`, `sudo -D`, `parallel --wd`, `chroot`, ...), in every
    spelling getopt accepts: `-CDIR`, `--chdir=DIR`, an abbreviation, a
    cluster.
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
            opts, rest = _getopt(words[1:], _ENV_SHORT, _ENV_LONG,
                                 stop=("S", "split-string"))
            split = None
            for name, value in opts:
                if name in ("i", "ignore-environment"):
                    _clear_env(env)
                elif name in ("u", "unset") and value is not None:
                    env[value] = None
                elif name in ("C", "chdir"):
                    _moved(ctx)
                elif name in ("S", "split-string"):
                    split = (value or "").split()
            if split is not None:
                # `env -S'-i terraform destroy'`: the string's words are read
                # again as env's own arguments, options included.
                words = [words[0]] + split + rest
                continue
            if rest and rest[0] == "-":
                _clear_env(env)
                rest = rest[1:]
            while rest and _ASSIGN_RE.match(rest[0]):
                match = _ASSIGN_RE.match(rest[0])
                env[match.group(1)] = match.group(2)
                rest = rest[1:]
            words = rest
            continue
        if head == "sudo":
            opts, rest = _getopt(words[1:], _SUDO_SHORT, _SUDO_LONG)
            if any(name in _SUDO_MOVES for name, _value in opts):
                _moved(ctx)
            words = rest
            continue
        if head in ("su", "runuser"):
            words = _unwrap_su(head, words[1:], ctx)
            continue
        if head in _PLAIN_WRAPPERS:
            shorts, longs, moves, operands = _PLAIN_WRAPPERS[head]
            opts, rest = _getopt(words[1:], shorts, longs)
            if "*" in moves or any(name in moves for name, _value in opts):
                _moved(ctx)
            words = rest[operands:]
            continue
        if head in _WRAPPER_VALUE_OPTS:
            rest = skip_wrapper_options(words[1:], _WRAPPER_VALUE_OPTS[head])
            opts = words[1:len(words) - len(rest)]
            if head == "parallel" and any(
                    o.split("=", 1)[0] in ("--wd", "--workdir") for o in opts):
                _moved(ctx)
            if head == "command" and any(  # `command -v|-V`: a lookup only
                    o[:2] != "--" and set(o[1:]) & set("vV") for o in opts):
                return []
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

_TF_HEADS = frozenset(("terraform", "tofu", "terragrunt"))


def _terraform_destructive(head, args):
    # `terraform apply -help` prints usage; the CLI runs nothing else.
    if _tf_help_requested(args):
        return None
    index = _tf_skip_options(args, 0)
    sub = args[index] if index < len(args) else None
    if sub in ("apply", "destroy"):
        return f"{head} {sub}"
    if sub in ("run-all", "run"):
        index = _tf_skip_options(args, index + 1)
        if index < len(args) and args[index] in ("apply", "destroy"):
            return f"{head} {sub} {args[index]}"
    return None


# --- terraform: which operation, which environment, does it destroy ----------
#
# T-0005. Environment is three values, never two: `nonProd` (a resolved name
# matching an `environments.nonProd` glob), `prod` (a resolved name matching
# none), and `unknown` -- no signal, a signal that is not a literal, signals
# that classify differently, or an `environments` block crew cannot read.
# `unknown` is narrower than `prod`: `prodUnattended` allows `prod`, and
# nothing allows `unknown` unattended.
#
# Destroy is three values too, and `unknown` is handled as `yes`: a plan crew
# cannot read might delete anything.

ENV_NONPROD, ENV_PROD, ENV_UNKNOWN = "nonProd", "prod", "unknown"
DESTROY_YES, DESTROY_NO, DESTROY_UNKNOWN = "yes", "no", "unknown"

# A saved plan bigger than this is not hashed: the hook has 15 seconds
# (hooks.json) and a hash it cannot finish is a plan it cannot read.
PLAN_MAX_BYTES = 64 * 1024 * 1024

# An in-sequence workspace switch whose name is not a literal. Not a string a
# workspace could be called, so it can never classify as either class.
_UNKNOWN_WS = "\0unknown"

# Anything a shell would still expand, glob or split: the word is not the
# value the command will see.
_NON_LITERAL_RE = re.compile(r"[$`*?\[\]{}()<>|;&\s'\"\0]")

# What moves the shell to another directory, which makes "the directory the
# hook payload names" stop being the directory terraform runs in.
_CD_HEADS = frozenset(("cd", "pushd", "popd", "chdir", "set-location", "sl",
                       "push-location", "pop-location"))


def _literal(value):
    return isinstance(value, str) and bool(value) \
        and not _NON_LITERAL_RE.search(value)


def _tf_split(args):
    """`(chdir, sub, rest)`: the global `-chdir=` value (or None), the
    subcommand, and the words after it. Terraform takes global options only
    before the subcommand, and `-chdir` only with an `=`."""
    chdir, index = None, 0
    while index < len(args) and args[index].startswith("-"):
        name, sep, value = args[index].lstrip("-").partition("=")
        if name == "chdir" and sep:
            chdir = value
        index += 1
    sub = args[index] if index < len(args) else None
    return chdir, sub, list(args[index + 1:])


def _tf_operands(rest):
    """The positional words of a subcommand, option values skipped."""
    out, index = [], 0
    while index < len(rest):
        arg = rest[index]
        if arg == "--":
            out.extend(rest[index + 1:])
            break
        if arg.startswith("-") and len(arg) > 1:
            name, sep, _value = arg.lstrip("-").partition("=")
            index += 2 if not sep and name in _TF_VALUE_OPTS else 1
            continue
        out.append(arg)
        index += 1
    return out


def _tf_flags(rest):
    """`{name: value-or-True}` for every option a subcommand was given."""
    flags = {}
    for arg in rest:
        if arg.startswith("-") and len(arg) > 1 and arg != "--":
            name, sep, value = arg.lstrip("-").partition("=")
            flags[name] = value if sep else True
    return flags


def _tf_workspace(args, head=None):
    """`(op, name)` for a `workspace` subcommand that can change something or
    select a workspace: `ws-new`, `ws-delete`, `ws-create` (`select
    -or-create`) or `select`; `(None, None)` for anything else.

    Terragrunt hands what follows `run-all`, `run --` and `run --all --` to
    terraform in every module, as `_terraform_destructive` reads them, and
    its own options may take a value (`--working-dir infra`), so for it --
    and behind either wrapper -- any `workspace` word may be the
    subcommand, and the most destructive reading wins."""
    _chdir, sub, rest = _tf_split(args)
    if "workspace" in args and (
            head == "terragrunt" or sub in ("run-all", "run")):
        # An option VALUE may be the word `workspace` too (`--working-dir
        # workspace`), and which words are values crew cannot know for
        # every terragrunt option. Read every `workspace` as the subcommand
        # and keep the worst: a delete over a create over the rest.
        found = [_tf_workspace_rest(args[index + 1:])
                 for index, word in enumerate(args) if word == "workspace"]
        return min(found, key=lambda got: _WS_RANK.get(got[0], 9))
    if sub != "workspace":
        return None, None
    return _tf_workspace_rest(rest)


# Which `workspace` reading `_tf_workspace` keeps when a terragrunt line
# has several: the one that would do the most.
_WS_RANK = {"ws-delete": 0, "ws-create": 1, "ws-new": 2, "select": 3}


def _tf_workspace_rest(rest):
    """`_tf_workspace` for the words after `workspace`."""
    if not rest or _tf_help_requested(rest[1:]):
        return None, None
    wsub, wrest = rest[0], rest[1:]
    names = _tf_operands(wrest)
    name = names[0] if names else None
    if wsub == "new":
        return "ws-new", name
    if wsub == "delete":
        return "ws-delete", name
    if wsub == "select":
        create = _tf_flags(wrest).get("or-create")
        creates = create is not None and str(create) not in (
            "0", "f", "F", "false", "FALSE", "False")
        return ("ws-create" if creates else "select"), name
    return None, None


def _tf_op(head, what):
    """The operation `_terraform_destructive` recognised, as a scope op."""
    if what.endswith("destroy"):
        return "run-destroy" if " run" in what else "destroy"
    if head == "terragrunt" or " run" in what:
        return "run-apply"
    return "apply"


def _tf_scope(head, args, env, op, seq, fed, name=None):
    """The `scope` of a terraform finding: a snapshot, never a live view."""
    return {"op": op, "head": head, "args": list(args), "env": dict(env),
            "workspace": (seq or {}).get("workspace"), "fed": bool(fed),
            "name": name}


def _tf_workdir(chdir, cwd, state):
    """`(directory, why)`: where terraform runs, or `(None, why)` when crew
    cannot tell. The hook payload's `cwd` is the Bash tool's directory; a
    `cd` anywhere in the command moves the shell away from it."""
    if state.get("cd"):
        return None, ("a cd/pushd/Set-Location in this command moves the "
                      "shell, so which directory terraform runs in is not "
                      "known")
    if not cwd:
        return None, "the hook payload carries no cwd"
    if chdir is None:
        return cwd, ""
    if not _literal(chdir):
        return None, f"-chdir={chdir} is not a literal path"
    return os.path.join(cwd, chdir), ""


class NotRegularFile(OSError):
    """A path that is there but is not a regular file: a FIFO, a device, a
    directory, a socket. Reading one can block (a FIFO with no writer) or
    never end (`/dev/zero`), and a hook past its 15 seconds is a
    NON-blocking error to Claude Code -- the command runs. So crew never
    reads one: the file is unreadable, and what it would have said is
    unknown."""


def _is_regular(mode):
    return stat.S_ISREG(mode)


def _open_regular(path):
    """`(binary handle, size)` for `path`, opened only when it is a regular
    file -- checked with `stat` before the open and again with `fstat` on
    the descriptor actually opened, so a file swapped for a FIFO in between
    is caught too. The open is non-blocking where the platform has it, so
    that swap cannot hang the open itself. Raises `NotRegularFile` (an
    `OSError`) otherwise, and every other `OSError` as `open` would."""
    if not _is_regular(os.stat(path).st_mode):
        raise NotRegularFile(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
                 | getattr(os, "O_BINARY", 0))
    try:
        info = os.fstat(fd)
        if not _is_regular(info.st_mode):
            raise NotRegularFile(path)
        return os.fdopen(fd, "rb"), info.st_size
    except BaseException:
        os.close(fd)
        raise


def _read_small(path, limit):
    """The bytes of the regular file `path`, or `ValueError` past `limit`."""
    handle, size = _open_regular(path)
    with handle:
        if size > limit:
            raise ValueError(f"{path} is over {limit} bytes")
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{path} is over {limit} bytes")
    return data


# A plan summary or a workspace file bigger than this is not one.
_SIDECAR_MAX_BYTES = 1024 * 1024
_WSFILE_MAX_BYTES = 4096
_AZ_PROFILE_MAX_BYTES = 16 * 1024 * 1024


def sidecar_problem(doc):
    """Why a plan summary cannot be trusted, or `""`."""
    if not isinstance(doc, dict):
        return "it is not a JSON object"
    deletes = doc.get("deletes")
    if not isinstance(deletes, list) or not all(
            isinstance(d, str) for d in deletes):
        return "`deletes` is not a list of resource addresses"
    for key in ("workspace", "environment"):
        if doc.get(key) is not None and not isinstance(doc[key], str):
            return f"`{key}` is not a string or null"
    return ""


def _tf_destroy(scope, cwd, root, state):
    """`(destroy, why, sidecar)` for one terraform finding. `destroy` is
    `yes`, `no` or `unknown`, and the caller treats `unknown` as `yes`.

    Reads the plan's bytes and the sidecar JSON, nothing else: running
    `terraform show` here would not fit the hook's 15 seconds."""
    op = scope["op"]
    if op == "ws-delete":
        return DESTROY_YES, "`workspace delete` removes a workspace", None
    if op in ("destroy", "run-destroy"):
        return DESTROY_YES, "it is a destroy", None
    if op in ("ws-new", "ws-create"):
        return DESTROY_NO, "", None
    if scope.get("fed"):
        return DESTROY_UNKNOWN, ("xargs/parallel appends arguments crew "
                                 "cannot see, so what it applies is not "
                                 "known"), None
    if op != "apply":
        return DESTROY_UNKNOWN, ("a terragrunt or run-all apply plans inside "
                                 "each module, where crew cannot read the "
                                 "plan"), None
    chdir, _sub, rest = _tf_split(scope["args"])
    flags = _tf_flags(rest)
    if "destroy" in flags:
        return DESTROY_YES, "`apply -destroy` destroys the workspace", None
    if "replace" in flags:
        return DESTROY_YES, ("`apply -replace` destroys a resource before "
                             "recreating it"), None
    operands = _tf_operands(rest)
    if not operands:
        return DESTROY_UNKNOWN, ("no saved plan: an apply without one plans "
                                 "afresh, and crew cannot see whether that "
                                 "plan deletes anything"), None
    if len(operands) > 1 or not _literal(operands[0]):
        return DESTROY_UNKNOWN, (f"the plan operand `{' '.join(operands)}` "
                                 "is not one literal path"), None
    plan = operands[0]
    # The plan is hashed NOW, before the command runs. Anything else in the
    # same invocation -- `terraform plan -out`, `cp`, `mv`, `tee`, a nested
    # shell, a redirect -- may replace the plan or its summary before
    # terraform reads it, and then the clean summary vouches for bytes that
    # are gone. Which of them could is not something crew can prove, so a
    # saved plan is trusted only when its apply is the ONE command here and
    # nothing writes output anywhere but the null device.
    if state.get("commands", 0) != 1 or state.get("writes"):
        doubts = state.get("unsure")
        read = (f"; crew could not read it as bash will ({doubts[0]}), so "
                "it counts one command more") if doubts else ""
        return DESTROY_UNKNOWN, (
            "this invocation runs more than the apply, or redirects output "
            "to a file, and either could rewrite the saved plan or its "
            "summary after crew hashes it -- a saved plan is trusted only "
            "when its apply is the only command (run the plan and summarize "
            f"steps first, then the apply on its own){read}"), None
    workdir, why = _tf_workdir(chdir, cwd, state)
    if workdir is None:
        return DESTROY_UNKNOWN, f"the saved plan cannot be located: {why}", None
    path = os.path.join(workdir, plan)
    try:
        handle, size = _open_regular(path)
        with handle:
            if size > PLAN_MAX_BYTES:
                return DESTROY_UNKNOWN, (f"the saved plan `{plan}` is over "
                                         "64 MiB, too big to hash inside the "
                                         "hook's time budget"), None
            digest = hashlib.sha256()
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
            digest = digest.hexdigest()
    except NotRegularFile:
        return DESTROY_UNKNOWN, (f"the saved plan `{plan}` is not a regular "
                                 "file, and crew never reads one"), None
    except OSError as exc:
        return DESTROY_UNKNOWN, (f"the saved plan `{plan}` could not be read "
                                 f"({type(exc).__name__})"), None
    sidecar_path = os.path.join(root, ".crew", "tfplan", digest + ".json")
    try:
        sidecar = json.loads(_read_small(sidecar_path, _SIDECAR_MAX_BYTES)
                             .decode("utf-8"))
    except FileNotFoundError:
        return DESTROY_UNKNOWN, (f"no summary exists for these exact plan "
                                 f"bytes (sha256 {digest[:12]}): run "
                                 f"`crew_tfplan.py summarize {plan}` -- a "
                                 "plan changed after it was summarised has no "
                                 "summary"), None
    except (OSError, ValueError) as exc:
        return DESTROY_UNKNOWN, (f"the plan summary {sidecar_path} could not "
                                 f"be read ({type(exc).__name__})"), None
    problem = sidecar_problem(sidecar)
    if problem:
        return DESTROY_UNKNOWN, (f"the plan summary {sidecar_path} is "
                                 f"malformed: {problem}"), None
    if sidecar["deletes"]:
        shown = ", ".join(sidecar["deletes"][:3])
        more = len(sidecar["deletes"]) - 3
        return DESTROY_YES, (f"the saved plan deletes {shown}"
                             + (f" and {more} more" if more > 0 else "")), \
            sidecar
    return DESTROY_NO, "", sidecar


def _env_class(value, globs):
    return ENV_NONPROD if _matches(value, globs) else ENV_PROD


def _tf_workspace_signal(scope, cwd, state):
    """`(source, value, why)` for the workspace terraform will use; `value`
    None means unknown, and `why` says what crew could not tell."""
    if state.get("opaque"):
        return "TF_WORKSPACE", None, (
            "this command changes the environment in a way crew does not "
            "read (a sourced file, a dynamic export or eval, an env: drive "
            "write, or an `||` chain), so TF_WORKSPACE is not known")
    env = scope["env"]
    named = _env(env, "TF_WORKSPACE")
    if named is not None:
        if _literal(named):
            return "TF_WORKSPACE", named, ""
        return "TF_WORKSPACE", None, f"TF_WORKSPACE is `{named}`, not a literal"
    earlier = scope.get("workspace")
    if earlier is not None:
        if earlier == _UNKNOWN_WS:
            return "workspace switch", None, ("an earlier workspace switch in "
                                              "this command names no literal "
                                              "workspace")
        return "workspace switch", earlier, ""
    if state.get("switch"):
        return "workspace file", None, ("a workspace switch elsewhere in this "
                                        "command changes the selected "
                                        "workspace on disk")
    chdir, _sub, _rest = _tf_split(scope["args"])
    workdir, why = _tf_workdir(chdir, cwd, state)
    if workdir is None:
        return "workspace file", None, why
    data_dir = _env(env, "TF_DATA_DIR") or ".terraform"
    if not _literal(data_dir):
        return "workspace file", None, f"TF_DATA_DIR is `{data_dir}`, not a literal"
    path = os.path.join(workdir, data_dir, "environment")
    try:
        name = _read_small(path, _WSFILE_MAX_BYTES).decode(
            "utf-8", "replace").strip()
    except FileNotFoundError:
        return "workspace file", None, (f"{path} does not exist, and crew "
                                        "does not read a missing file as "
                                        "`default`")
    except NotRegularFile:
        return "workspace file", None, f"{path} is not a regular file"
    except ValueError:
        return "workspace file", None, f"{path} is too big to be one"
    except OSError as exc:
        return "workspace file", None, (f"{path} could not be read "
                                        f"({type(exc).__name__})")
    if not _literal(name):
        return "workspace file", None, f"{path} names no literal workspace"
    return "workspace file", name, ""


def _tf_var_signal(scope):
    """`(source, value, why)` for the `environment` variable, or None when
    nothing sets it on the command line or in the environment. `-var-file`
    and `*.tfvars` are not read, so their absence here is no signal."""
    _chdir, _sub, rest = _tf_split(scope["args"])
    found, index = None, 0
    while index < len(rest):
        arg = rest[index]
        name, sep, value = arg.lstrip("-").partition("=")
        if arg.startswith("-") and name == "var":
            if not sep:
                value = rest[index + 1] if index + 1 < len(rest) else ""
                index += 1
            key, equals, assigned = value.partition("=")
            if key.strip() == "environment" and equals:
                found = assigned
        index += 1
    source = "-var environment"
    if found is None:
        found, source = _env(scope["env"], "TF_VAR_environment"), \
            "TF_VAR_environment"
    if found is None:
        return None
    if _literal(found):
        return source, found, ""
    return source, None, f"{source} is `{found}`, not a literal"


def _tf_environment(scope, cwd, state, cfg, sidecar=None):
    """`(class, value, why)`: `nonProd`, `prod` or `unknown`, the name that
    decided it, and -- for `unknown` -- what crew could not tell.

    Every signal must agree after classification: two different production
    names are production, a nonProd name and a production one are unknown."""
    if cfg.get("problem"):
        return ENV_UNKNOWN, None, (f"the environments block cannot be read: "
                                   f"{cfg['problem']}")
    if scope.get("fed"):
        return ENV_UNKNOWN, None, ("xargs/parallel appends arguments crew "
                                   "cannot see, so the target is not known")
    op = scope["op"]
    if op in ("run-apply", "run-destroy") or scope["head"] == "terragrunt":
        return ENV_UNKNOWN, None, "terragrunt layouts are not read"
    if op in ("ws-new", "ws-create", "ws-delete"):
        name = scope.get("name")
        if name is None:
            signals = [("workspace name", None, "no workspace name is given")]
        elif _literal(name):
            signals = [("workspace name", name, "")]
        else:
            signals = [("workspace name", None,
                        f"the workspace name `{name}` is not a literal")]
    else:
        signals = [_tf_workspace_signal(scope, cwd, state)]
        var = _tf_var_signal(scope)
        if var is not None:
            signals.append(var)
        if sidecar is not None:
            # The workspace crew_tfplan read out of the plan itself, which
            # terraform refuses to apply anywhere else. Missing or not a
            # literal, it vouches for nothing: unknown, never "no signal".
            bound = sidecar.get("workspace")
            if _literal(bound):
                signals.append(("the saved plan's workspace", bound, ""))
            else:
                signals.append(("the saved plan's workspace", None,
                                "the plan summary names no workspace the "
                                "plan is bound to"))
            if sidecar.get("environment") is not None:
                signals.append(("the saved plan's environment",
                                sidecar["environment"], ""))
    unknown = [why for _source, value, why in signals if value is None]
    if unknown:
        return ENV_UNKNOWN, None, "; ".join(unknown)
    classes = {}
    for source, value, _why in signals:
        classes.setdefault(_env_class(value, cfg.get("nonProd", [])),
                           []).append(f"{source} `{value}`")
    if len(classes) > 1:
        return ENV_UNKNOWN, None, ("the signals disagree -- " + "; ".join(
            f"{klass}: {', '.join(names)}" for klass, names in
            sorted(classes.items())))
    return next(iter(classes)), signals[0][1], ""


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


def _pwsh_moves(args):
    """True when a `pwsh`/`powershell` command line sets its own starting
    directory: `-WorkingDirectory DIR` or any abbreviation PowerShell binds
    to it (`-wo`, `-work`, ...), its alias `-wd`, with `-`, `--` or `/`."""
    for arg in args:
        if not arg[:1] in ("-", "/"):
            continue
        name = arg.lstrip("-/").split(":", 1)[0].lower()
        if name == "wd" or (len(name) >= 2
                            and "workingdirectory".startswith(name)):
            return True
    return False


def _classify(argv, stdin, env, shell, depth, ctx=None, seq=None, fed=False):
    """Findings for one unwrapped simple command, recursing into anything it
    runs inline (`bash -c`, `pwsh -c`, `ssh host cmd`, `cmd /c`, `wsl`).

    `ctx` is the whole command's shared state (`scan`'s), `seq` this scope's
    in-sequence workspace, and `fed` True when `xargs`/`parallel` append
    words to `argv` that crew cannot see."""
    kw = {"ctx": ctx, "seq": seq}
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
            out.extend(scan("bash", payload, env, depth + 1, **kw))
        return out
    if head in _PWSH:
        if ctx is not None and _pwsh_moves(args):
            ctx["cd"] = True
        payload = _pwsh_payload(args)
        if payload in (None, "-") and stdin:
            payload = stdin
        if payload:
            out.extend(scan("powershell", payload, env, depth + 1, **kw))
        return out
    if head == "cmd" and args and args[0].lower() in ("/c", "/k"):
        out.extend(scan("bash", " ".join(args[1:]), env, depth + 1, **kw))
        return out
    if head == "wsl":
        rest = list(args)
        while rest and (rest[0].startswith("-") or rest[0] == "~"):
            flag = rest[0]
            rest = rest[1:]
            if flag == "~" or flag.split("=", 1)[0] == "--cd":
                # `wsl --cd DIR`, and `wsl ~` (start in the home directory).
                if ctx is not None:
                    ctx["cd"] = True
                if flag == "--cd":
                    rest = rest[1:]
                continue
            if flag in ("-e", "--exec", "--"):
                if rest:
                    out.extend(_classify(rest, stdin, env, shell, depth + 1,
                                         **kw))
                return out
            if flag in ("-d", "--distribution", "-u", "--user",
                        "--shell-type", "--distribution-id"):
                rest = rest[1:]
        if rest:
            out.extend(scan("bash", " ".join(rest), env, depth + 1, **kw))
        return out
    if head in ("eval",):
        args = args[1:] if args[:1] == ["--"] else args  # `eval -- ...`
        if ctx is not None and any("$" in a or "`" in a for a in args):
            # What it evaluates is built at run time: it may export, cd,
            # anything, and crew reads only the text it can see.
            ctx["opaque"] = ctx["cd"] = True
        out.extend(scan("bash", " ".join(args), env, depth + 1, **kw))
        return out
    if head in ("iex", "invoke-expression"):
        # PowerShell's eval: `iex 'terraform destroy'` was never read.
        payload = " ".join(a for a in args if not a.startswith("-"))
        if not payload.strip():
            # `Get-Content prod.ps1 | iex`: the text arrives on the pipeline.
            # A literal crew can see is read; anything else is not.
            payload = stdin or ""
            if ctx is not None and not payload.strip():
                ctx["opaque"] = ctx["cd"] = True
        if ctx is not None and ("$" in payload or "`" in payload):
            ctx["opaque"] = ctx["cd"] = True
        out.extend(scan("powershell", payload, env, depth + 1, **kw))
        return out

    if head in _TF_HEADS:
        what = _terraform_destructive(head, args)
        if what:
            out.append(Finding("terraformApply", text, what, None, True, None,
                               _tf_scope(head, args, env, _tf_op(head, what),
                                         seq, fed)))
            return out
        # `workspace delete` is a destroy, judged in every armed state.
        # `workspace new|select -or-create` are judged only while the
        # environment layer is engaged, so a repo that never configured it
        # passes them exactly as before. Behind xargs they are
        # `_fed_finding`'s, which knows the name is not visible.
        op, name = _tf_workspace(args, head)
        engaged = ctx is not None and ctx.get("engaged")
        if op in ("ws-new", "ws-delete", "ws-create") and not fed \
                and (op == "ws-delete" or engaged):
            verb = {"ws-new": "new", "ws-delete": "delete",
                    "ws-create": "select -or-create"}[op]
            out.append(Finding("terraformApply", text,
                               f"{head} workspace {verb} {name or ''}".strip(),
                               None, True, None,
                               _tf_scope(head, args, env, op, seq, fed, name)))
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
            if ctx is not None:
                # The remote shell's directory is not the payload's `cwd`.
                ctx["cd"] = True
            out.extend(scan("bash", remote, env, depth + 1, **kw))
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


# `workspace` is NOT here (T-0005): `new`, `delete` and `select -or-create`
# change something, and `_fed_finding` reads the subcommand itself.
_TF_READ_ONLY = frozenset(("plan", "init", "validate", "fmt", "show", "output",
                           "providers", "version", "graph", "get", "console",
                           "state", "test", "login", "logout"))
_TF_WORKSPACE_READS = frozenset(("list", "show"))


# What a literal executable name looks like: a bare name or a path. Anything
# else in the executable position under `xargs`/`parallel` -- `%`, a quote-
# built word, a variable -- is not known to name a harmless command.
_LITERAL_EXE_RE = re.compile(r"^[A-Za-z0-9_./~\\][A-Za-z0-9_.+:/\\~-]*$")


def _fed_finding(argv, env, via, placeholders, ctx=None):
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

    if head in _TF_HEADS:
        words = [w for w in args if not w.startswith("-")]
        if words and seen(words[:1]) and words[0] in _TF_READ_ONLY:
            return None
        op = "fed"
        if words and seen(words[:1]) and words[0] == "workspace":
            wsub = words[1] if len(words) > 1 and seen(words[1:2]) else None
            creates = _tf_workspace(
                [w for w in args if not carries(w)])[0] == "ws-create"
            if wsub in _TF_WORKSPACE_READS or (wsub == "select"
                                               and not creates):
                return None
            if wsub in ("new", "select") and not (ctx or {}).get("engaged"):
                # Creation, with the environment layer not configured: as
                # before T-0005. A delete -- or a subcommand crew cannot
                # see, which may be one -- is a destroy at every setting.
                return None
            op = {"new": "ws-new", "delete": "ws-delete",
                  "select": "ws-create"}.get(wsub, "fed")
        return Finding("terraformApply", text, what, None, True, None,
                       _tf_scope(head, args, env, op, None, True))
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
        # A path the command itself can choose (`AZURE_CONFIG_DIR=...`), so
        # a FIFO or device there must read as unknown, never as a hang.
        data = json.loads(_read_small(path, _AZ_PROFILE_MAX_BYTES)
                          .decode("utf-8-sig"))
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


def environments_config(root):
    """`{"nonProd", "prodUnattended", "problem", "engaged"}` for the repo.

    `nonProd` is read from the REPO LAYER ONLY, as `cloud_pins` reads
    `cloud.*`. `problem` is non-empty when the block is there and cannot be
    read -- which is NOT "nothing is nonProd": it makes every environment
    unknown. `prodUnattended` comes through the ratchet, so it is true only
    when both config layers say `true`. `engaged` says whether the
    environment layer is configured at all: while it is not, `workspace`
    commands are not judged, exactly as before T-0005.
    """
    out = {"nonProd": [], "problem": ""}
    path = os.path.join(root, ".crew", "config.json")
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            raw = handle.read()
        cfg = json.loads(raw)
    except (FileNotFoundError, NotADirectoryError):
        cfg = {}
    except OSError as exc:
        out["problem"] = (f".crew/config.json could not be read "
                          f"({type(exc).__name__})")
        cfg = {}
    except ValueError:
        out["problem"] = ".crew/config.json does not parse as JSON"
        cfg = {}
    if not isinstance(cfg, dict):
        out["problem"] = ".crew/config.json is not a JSON object"
    elif "environments" in cfg:
        problem = crew_config.environments_block_problem(cfg["environments"])
        if problem:
            out = {"nonProd": [], "problem": problem}
        else:
            out["nonProd"] = [v.strip() for v in
                              cfg["environments"].get("nonProd", [])]
    out["prodUnattended"] = crew_config.resolve_ratcheted(
        root, "environments.prodUnattended")["effective"] is True
    out["engaged"] = bool(out["nonProd"] or out["prodUnattended"]
                          or out["problem"])
    return out


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


def _note_cmd(cmd, ctx):
    """Count one simple command toward `ctx["commands"]` -- every depth,
    redirect-only commands and assignment statements included -- and record
    an output redirect (`ctx["writes"]`) and an `||` (`ctx["opaque"]`)."""
    if ctx is None:
        return
    ctx["commands"] = ctx.get("commands", 0) + 1
    if cmd.writes:
        ctx["writes"] = True
    if cmd.or_next:
        ctx["opaque"] = True


# Commands that set a shell variable from input crew cannot see. A variable
# that is already exported reaches terraform with the new value.
_READ_HEADS = frozenset(("read", "mapfile", "readarray", "getopts"))


def _env_opaque(argv, shell):
    """True when `argv` changes the environment in a way crew does not
    read: `set -a`, `read`, `printf -v`, and in PowerShell any write
    through the `env:` drive (`Set-Item env:X`, `New-Item -Path env:X`,
    `${env:X} = ...`, `$env:X += ...`) or `SetEnvironmentVariable`."""
    head = argv[0].lower()
    if head == "set" and any(
            a in ("-a", "allexport") or (a.startswith("-") and "a" in a[1:]
                                         and not a.startswith("--"))
            for a in argv[1:]):
        return True
    if head in _READ_HEADS or (head == "printf" and "-v" in argv[1:]):
        return True
    low = " ".join(argv).lower()
    if "setenvironmentvariable" in low:
        return True
    return shell == "powershell" and any(
        w.lower().lstrip("${").startswith("env:") for w in argv)


def _track(argv, ctx, seq, fed, shell="bash"):
    """Record what `argv` does to where terraform will run: a directory
    change anywhere (`ctx["cd"]`), an environment change crew cannot read
    (`ctx["opaque"]`), a workspace switch anywhere (`ctx["switch"]`), and --
    for the commands after it in this scope -- the workspace a literal
    switch selected (`seq["workspace"]`)."""
    if ctx is None:
        return
    head = _head_name(argv[0])
    low = " ".join(argv).lower()
    if head in _CD_HEADS or "currentdirectory" in low:
        # `[IO.Directory]::SetCurrentDirectory(...)`,
        # `[Environment]::CurrentDirectory = ...` move PowerShell too.
        ctx["cd"] = True
        return
    if argv[0] in ("source", ".") or (shell == "powershell"
                                      and argv[0].lower().endswith(".ps1")):
        # A sourced file -- or, in PowerShell, any script, which shares the
        # session's location and `env:` -- may cd and export anything.
        ctx["cd"] = ctx["opaque"] = True
        return
    if _env_opaque(argv, shell):
        ctx["opaque"] = True
    if head in ("terraform", "tofu"):
        op, name = _tf_workspace(argv[1:])
        if op in ("select", "ws-new", "ws-create"):
            ctx["switch"] = True
            seq["workspace"] = name if name and not fed and _literal(name) \
                else _UNKNOWN_WS


# A could-not-tell finding's scope `op`; `_terraform_verdict` answers it
# before reading any plan, workspace or environment.
OP_UNREADABLE_LINE = "line-not-literal"


_GATE_HELPERS = (_unwrap, _shell_args, _pwsh_payload, _ps_normalise,
                 _head_name, _lex_ps)


def _literal_gate(shell, text):
    """A could-not-tell `terraformApply` finding for `text`, or None when it
    runs no terraform/terragrunt/tofu, or runs it only in ways the lexer
    reads and every word on it is plain (the lexer then judges it as
    before). A word that is not plain comes first; else a command the lexer
    is not known to read (`unseen`, review round 5) -- an alias, a copied
    binary, `Start-Process` -- is could-not-tell on a line of plain words
    too. PowerShell has the same command-word rule (`ps_trigger`)."""
    if shell == "powershell":
        found = ps_trigger(_ps_normalise(text)[0], _GATE_HELPERS)
    else:
        found = command_trigger(text, _GATE_HELPERS)
    if found is None:
        return None
    named, unseen = found
    word = first_non_literal(text, shell)
    if word is not None:
        shown = word if len(word) <= 40 else word[:37] + "..."
        what = ("a terraform-family line with a word that is not a plain "
                f"literal: {shown!r}")
    elif unseen:
        what = ("a terraform-family line that runs "
                f"{named!r} in a way crew does not follow")
    else:
        return None
    return Finding("terraformApply", text, what, None, True, None,
                   {"op": OP_UNREADABLE_LINE, "named": named, "word": word,
                    "unseen": word is None})


def scan(shell, text, env=None, depth=0, ctx=None, seq=None):
    """Every finding in `text`, read as `shell` ("bash" or "powershell").

    `env` is the override dict inherited from an enclosing command (`env X=Y
    bash -c '...'`); it is copied, never mutated, so a nested scope cannot
    leak into its parent. `seq` (the in-sequence workspace) is copied the same
    way; `ctx` is shared by every scope of one command, because a `cd`
    anywhere in it matters to every terraform in it.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    if depth > MAX_DEPTH:
        return [Finding(UNREADABLE_RULE, text,
                        f"nested more than {MAX_DEPTH} shells or "
                        "substitutions deep, so the innermost command was "
                        "never read", None, True, None)]
    # The allowlist first, on the raw text, before the lexer reads it -- once,
    # at the top: the trigger reads nested scripts itself, and a nested text
    # here is the lexer's own (sometimes deliberately widened) extraction.
    gated = _literal_gate(shell, text) if depth == 0 else None
    env = dict(env or {})
    seq = dict(seq or {})
    variables = {}
    exported = set()
    unsure = []
    if shell == "powershell":
        normal, mapped = _ps_normalise(text)
        if mapped:
            unsure.append("PowerShell's typographic quotes or a bare CR")
        cmds, subs = _lex_ps(normal)
    else:
        cmds, subs = _lex_bash(text, unsure)
        if "\r" in text:
            # The lexer reads CR as a blank. Bash without igncr reads it as
            # a word character (`\r#` is a word, not a comment, and `X=\r`
            # is one assignment); a shell that drops CR reads it as nothing.
            # Read the whole text both of those ways too. `\x01` is a word
            # character to the lexer and to bash, and not a CR, so neither
            # re-read recurses.
            subs.extend((text.replace("\r", "\x01"), text.replace("\r", "")))
    if _CONTROL_RE.search(text):
        unsure.append("a control character")
    if unsure and ctx is not None:
        # Fail closed. Crew could not be sure it split this text as the
        # shell will, so it does not know how many commands it holds: count
        # one more than it saw, and the saved plan's apply is never the only
        # command (`_tf_destroy`).
        ctx["commands"] = 1 + ctx.get("commands", 0)
        ctx.setdefault("unsure", []).extend(unsure)
    findings = [gated] if gated is not None else []
    for sub in subs:
        findings.extend(scan(shell, sub, env, depth + 1, ctx, seq))
    for cmd in cmds:
        _note_cmd(cmd, ctx)
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
            if words[0] == "." and len(words) > 1 and _head_name(words[1]) in _TF_HEADS:
                words = words[1:]  # `. terraform destroy` runs it, as `&`
        else:
            head = words[0]
            if head in ("export", "declare", "typeset", "local", "readonly"):
                for word in words[1:]:
                    if ctx is not None and ("$" in word or "`" in word):
                        # `export $(cat prod.env)`: names and values built at
                        # run time, which crew cannot read.
                        ctx["opaque"] = True
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
        argv = _unwrap(words, local_env, fed, ctx)
        if fed and argv and argv[0] == ":::":
            # `parallel ::: 'terraform destroy' ls`: every argument is a
            # command of its own.
            for job in argv[1:]:
                findings.extend(scan("bash", job, local_env, depth + 1, ctx,
                                     seq))
            continue
        if not argv:
            continue
        found = _classify(argv, None if fed else cmd.stdin, local_env, shell,
                          depth, ctx, seq, bool(fed))
        extra = _fed_finding(argv, local_env, *fed[-1], ctx=ctx) if fed \
            else None
        _track(argv, ctx, seq, bool(fed), shell)
        if extra is not None and not any(
                f.destructive and (f.scope or {}).get("op")
                != OP_UNREADABLE_LINE for f in found):
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


def _terraform_verdict(root, finding, out, envs):
    """`(decision, reason, policy, marker)` for one terraform finding: the
    T-0005 table, applied after `guard_decision` has resolved the ratcheted
    `guards.terraformApply` policy and read the one-shot marker.

        block   deny, whatever the environment
        ask     live marker: allow. Else a destroy (yes or unknown) asks; a
                non-destroying nonProd target is allowed and logged; production
                is allowed only under `prodUnattended` in both layers (logged,
                and said on screen); otherwise it asks
        allow   a destroy (yes or unknown) ASKS -- BREAKING in 1.0.41 --
                unless a live marker approves this one command

    `ask` stays `deny` when nobody is attending (`evaluate`). `policy` is the
    guard.log column: `env:nonProd:<name>`, `env:prod-unattended:<name>`,
    `env:prod:<name>`, `env:unknown` or `destroy:ask`.
    """
    base = f"[{finding.rule}] {finding.what}"
    policy, marker = out["policy"], out["marker"]
    if out["policy"] == "block":
        return "deny", f"{base}: {out['reason']}", "block", marker
    if finding.scope.get("op") == OP_UNREADABLE_LINE:
        # Step 8: nothing below may read a plan or an environment for this
        # line -- crew does not know what it runs. Asked about, or denied
        # when nobody attends (`evaluate`); a live marker is the person's
        # own approval of this exact text.
        if _approval_is_live(marker):
            return "allow", f"{base}: approved for this command: {marker}", \
                "could-not-tell", marker
        # The wording avoids the words other rows' reasons are checked
        # for (destroy, unknown, rewrite, ...), so this finding can never
        # stand in for the one a test expects the lexer to make.
        if finding.scope.get("unseen"):
            return "ask", (f"{base} -- crew does not follow how this line "
                           "runs terraform (an alias, a wrapper it does not "
                           "strip, another name for the binary), so it could "
                           "not tell what the line would change. Such a line "
                           "is asked about and never allowed unattended; run "
                           "terraform by its own name to have it judged"), \
                "could-not-tell", marker
        return "ask", (f"{base} -- crew judges a terraform-family line only "
                       "when every word on it is a plain literal, so it "
                       "could not tell what this line would change. Unusual "
                       "quoting on such a line is asked about and never "
                       "allowed unattended; spell it with plain words to "
                       "have it judged"), "could-not-tell", marker
    cwd, state = envs.get("cwd"), envs.get("ctx") or {}
    destroy, destroy_why, sidecar = _tf_destroy(finding.scope, cwd, root,
                                                state)
    klass, value, env_why = _tf_environment(finding.scope, cwd, state, envs,
                                            sidecar)
    if _approval_is_live(marker):
        return "allow", f"{base}: approved for this command: {marker}", \
            policy, marker
    if policy == "allow":
        if destroy in ("yes", "unknown"):
            return "ask", (f"{base}: guards.terraformApply is `allow`, but a "
                           f"destroy is never applied unattended -- "
                           f"destroy {destroy}: {destroy_why}"), \
                "destroy:ask", marker
        return "allow", f"{base}: {out['reason']}", policy, marker
    head = f"{base}: guards.terraformApply is `ask`"
    if destroy != "no":
        return "ask", (f"{head}, and this is a destroy (destroy {destroy}: "
                       f"{destroy_why}) -- a destroy is never applied "
                       "unattended"), "destroy:ask", marker
    if klass == ENV_NONPROD:
        return "allow", f"{head}; environment `{value}` is nonProd", \
            f"env:nonProd:{value}", marker
    if klass == ENV_PROD and envs.get("prodUnattended"):
        return "allow", (f"{head}; environment `{value}` is production and "
                         "environments.prodUnattended is true in both config "
                         "layers"), f"env:prod-unattended:{value}", marker
    if klass == ENV_PROD:
        return "ask", (f"{head}: environment `{value}` is production -- it "
                       "matches no environments.nonProd glob, and "
                       "environments.prodUnattended is not true in both "
                       "config layers"), f"env:prod:{value}", marker
    return "ask", (f"{head}: environment unknown -- {env_why}. An "
                   "environment crew cannot identify is never allowed "
                   "unattended"), "env:unknown", marker


def _judge_one(root, finding, pins, problem, envs=None):
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
        if finding.scope is not None and envs is not None:
            return _terraform_verdict(root, finding, out, envs) + (True,)
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
    envs = environments_config(root)
    ctx = {"cd": False, "switch": False, "engaged": envs["engaged"]}
    findings = scan(shell, command, ctx=ctx)
    cwd = (data or {}).get("cwd")
    envs["cwd"] = cwd if isinstance(cwd, str) and cwd else None
    envs["ctx"] = ctx
    pins, problem = cloud_pins(root)
    worst, reasons, rows, unpinned = "allow", [], [], []
    said = []
    alone = unattended(data or {})
    for finding in findings:
        decision, reason, policy, marker, applies = _judge_one(
            root, finding, pins, problem, envs)
        if not applies:
            continue
        if policy == UNPINNED:
            unpinned.append(finding.what)
            continue
        if policy.startswith("env:prod-unattended:") and decision == "allow":
            said.append(f"crew cloud guard: `{finding.what}` targets "
                        f"production environment `{policy.split(':', 2)[2]}` "
                        "and runs with nobody asked, because "
                        "environments.prodUnattended is true in both config "
                        "layers")
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
    note = " | ".join(said)
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
    if mode != "off" and crew_config.layer_state(
            repo_path, environments=True) == "corrupt":
        return "block", ("the repo's `environments` block is malformed, so "
                         "that layer is invalid; failing closed")
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
