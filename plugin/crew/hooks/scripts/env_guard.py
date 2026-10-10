"""PreToolUse environment-dump guard for the Bash and PowerShell tools (L-0772).

Refuses a command whose OWN TEXT prints the whole process environment, or a
credential-named variable, into the agent's context -- `env`, `printenv`, bare
`set`, `export -p`, `declare -p`, `cat /proc/self/environ`, `ps eww`,
`python -c 'print(os.environ)'`, `Get-ChildItem env:`,
`[Environment]::GetEnvironmentVariables()`, `cmd /c set`, `echo "$API_TOKEN"`,
and the same inside `bash -c`, `eval`, `$( )`, pipelines, loops and the usual
wrappers. A refusal names a fixed label -- `env-dump:<form>`,
`secret-read:<form>` or `could-not-tell:<why>` -- and never a value, a
variable's name or the command text. The same holds for the row it writes to
`.crew/guard.log`.

OFF BY DEFAULT. `guards.envGuard` is `off` unless a config layer says
otherwise (`crew_guards.ENV_GUARD_NAMES`); at `off` this script reads that one
key and exits. `report` logs what `block` would refuse and refuses nothing.
CLAUDE.md's rule for a hook that can block.

COULD NOT TELL never allows in `block` mode: text the reader cannot parse,
nesting deeper than `MAX_DEPTH`, a program name or `eval`/`-c`/
`Invoke-Expression` code that is not fully literal, an indirect expansion,
malformed hook input, an unreadable config, an internal error.

DIRECT USE ONLY. The guard judges the text it is handed: a script the command
runs, an alias or function defined outside the command, `source` of a file,
and a binary renamed out of sight are not seen (README, "Environment guard").
Like any denylist it cannot be complete; keeping credentials out of the
agent's environment is the stronger control (L-0776).

This module imports nothing from crew at the top level, so `crew_guards` can
import it lazily for its production read check without an import cycle. The
config readers are imported inside `resolve_mode`.

Decisions travel as PreToolUse JSON on stdout with exit 0 (`deny`, or nothing).
"""

import fnmatch
import json
import os
import re
import sys
import time

RULE = "envGuard"
MAX_DEPTH = 8
# Python recursion bound for the readers themselves, far above MAX_DEPTH: a
# deeper text is could-not-tell, never a RecursionError.
_PARSE_NEST_LIMIT = 40

# Set by each wrapper for the call it makes: `bash` from env-guard.sh,
# `powershell` from env-guard.ps1. Unset (the module run directly) judges
# every call.
FLAVOUR_VAR = "CREW_ENV_GUARD_FLAVOUR"
_PS1_TWIN = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "env-guard.ps1")

GUARD_LOG = os.path.join(".crew", "guard.log")


class Unparsed(Exception):
    """The reader could not read the text; `args[0]` is a fixed reason."""


# --- credential names ---------------------------------------------------------

_SECRET_NAME_RE = re.compile(
    r"TOKEN|SECRET|PASSWORD|PASSWD|PASSPHRASE|CREDENTIAL|API_?KEY|ACCESS_KEY|"
    r"PRIVATE_KEY|_KEY$|AUTH|COOKIE|SESSION|DSN|CONNECTION_STRING|"
    r"DATABASE_URL|WEBHOOK|SIGNING|_PAT$", re.IGNORECASE)
_SECRET_EXEMPT = frozenset(("SSH_AUTH_SOCK", "XAUTHORITY", "GPG_AGENT_INFO",
                            "DBUS_SESSION_BUS_ADDRESS"))
_SECRET_EXEMPT_PREFIXES = ("GIT_AUTHOR_", "GIT_COMMITTER_", "XDG_SESSION_")


def is_secret_name(name):
    """True when `name` looks like it holds a credential. A fixed pattern,
    case-insensitive; a few known non-secret families are exempt."""
    if not name:
        return False
    if name.lower().startswith("env:"):
        name = name[4:]
    upper = name.upper()
    if upper in _SECRET_EXEMPT or upper.startswith(_SECRET_EXEMPT_PREFIXES):
        return False
    return bool(_SECRET_NAME_RE.search(upper))


# --- /proc/<pid>/environ --------------------------------------------------------

_PROC_RE = re.compile(r"/proc/[^/\s]*/(?:task/[^/\s]*/)?([^/\s]*)$")


def _is_environ_path(glob_text):
    """`glob_text` names a `/proc/<pid>/environ` (or a task's), with the last
    segment matched as a glob so `env*`, `e?viron` and `*` count."""
    if not glob_text or "/proc/" not in glob_text:
        return False
    at = glob_text.find("/proc/")
    while at != -1:
        match = _PROC_RE.match(glob_text[at:])
        if match and fnmatch.fnmatchcase("environ", match.group(1) or ""):
            return True
        at = glob_text.find("/proc/", at + 1)
    return False


# --- interpreter code -----------------------------------------------------------

_Q = r"""['"]([^'"]+)['"]"""
_LANG_RULES = {
    "python": (
        (re.compile(r"\bos\s*\.\s*environb?\b(?!\s*(?:\[|\.\s*get\s*\())"),
         re.compile(r"\bdict\s*\(\s*os\s*\.\s*environ")),
        (re.compile(r"\bos\s*\.\s*environb?\s*(?:\[\s*|\.\s*get\s*\(\s*)" + _Q),
         re.compile(r"\bos\s*\.\s*getenvb?\s*\(\s*" + _Q)),
    ),
    "node": (
        (re.compile(r"\bprocess\s*\.\s*env\b(?!\s*(?:\.\s*[A-Za-z_$]|\[))"),
         re.compile(r"\bBun\s*\.\s*env\b(?!\s*(?:\.\s*[A-Za-z_$]|\[))"),
         re.compile(r"\bDeno\s*\.\s*env\s*\.\s*toObject\s*\(")),
        (re.compile(r"\b(?:process|Bun)\s*\.\s*env\s*\.\s*([A-Za-z_$][\w$]*)"),
         re.compile(r"\b(?:process|Bun)\s*\.\s*env\s*\[\s*" + _Q),
         re.compile(r"\bDeno\s*\.\s*env\s*\.\s*get\s*\(\s*" + _Q)),
    ),
    "perl": (
        (re.compile(r"%ENV\b"),),
        (re.compile(r"\$ENV\s*\{\s*['\"]?(\w+)"),),
    ),
    "ruby": (
        (re.compile(r"(?<![\w$:.])ENV\b(?!\s*(?:\[|\.\s*fetch\s*\())"),),
        (re.compile(r"(?<![\w$:.])ENV\s*\[\s*" + _Q),
         re.compile(r"(?<![\w$:.])ENV\s*\.\s*fetch\s*\(\s*" + _Q)),
    ),
    "php": (
        (re.compile(r"\bgetenv\s*\(\s*\)"),
         re.compile(r"\$_ENV\b(?!\s*\[)"),
         re.compile(r"\$_SERVER\b(?!\s*\[)")),
        (re.compile(r"\bgetenv\s*\(\s*" + _Q),
         re.compile(r"\$_(?:ENV|SERVER)\s*\[\s*" + _Q)),
    ),
    "awk": (
        (re.compile(r"\bENVIRON\b(?!\s*\[)"),),
        (re.compile(r"\bENVIRON\s*\[\s*\"([^\"]+)\""),),
    ),
    "jq": (
        (re.compile(r"\$ENV\b(?!\s*\.\s*[A-Za-z_])"),
         re.compile(r"(?<![\w$.])env\b(?!\s*\.\s*[A-Za-z_])")),
        (re.compile(r"\$?(?<![\w.])(?:ENV|env)\s*\.\s*([A-Za-z_]\w*)"),),
    ),
}


def _scan_code(code, lang, ctx):
    """Inline interpreter code: a whole-environment read, or a credential
    name read. `lang` "any" applies every language's rules (a program named
    by a variable)."""
    langs = tuple(_LANG_RULES) if lang == "any" else (lang,)
    for name in langs:
        dumps, reads = _LANG_RULES[name]
        if any(rule.search(code) for rule in dumps):
            ctx.add(f"env-dump:{name}")
        for rule in reads:
            for match in rule.finditer(code):
                if is_secret_name(match.group(match.lastindex or 1)):
                    ctx.add(f"secret-read:{name}")


# --- words ------------------------------------------------------------------------


class Word:
    """One shell word: a list of parts.

    ("lit", text)    literal text, quotes removed
    ("var", name)    a parameter expansion (`$NAME`, `${NAME...}`, `$env:NAME`)
    ("sub", nested)  a command substitution / subexpression; `nested` is the
                     reader's parse of it, judged by the caller
    ("indirect",)    `${!name}`
    ("arith",)       `$(( ))`
    """

    __slots__ = ("parts", "quoted", "raw")

    def __init__(self, parts=None, quoted=False, raw=""):
        self.parts = parts if parts is not None else []
        self.quoted = quoted
        self.raw = raw

    @classmethod
    def lit(cls, text):
        return cls([("lit", text)])

    @property
    def literal(self):
        """The word's text when every part is literal, else None."""
        if all(part[0] == "lit" for part in self.parts):
            return "".join(part[1] for part in self.parts)
        return None

    @property
    def glob(self):
        """The text with every non-literal part as `*`."""
        return "".join(part[1] if part[0] == "lit" else "*"
                       for part in self.parts)

    @property
    def dollar(self):
        """The text with variables written back as `${NAME}` (for a command
        line another shell will parse, e.g. ssh's remote command)."""
        out = []
        for part in self.parts:
            if part[0] == "lit":
                out.append(part[1])
            elif part[0] == "var":
                out.append("${" + part[1] + "}")
            else:
                out.append("__SUB__")
        return "".join(out)

    @property
    def vars(self):
        return [part[1] for part in self.parts if part[0] == "var"]

    @property
    def simple_var(self):
        """The name when the word is exactly one variable, else None."""
        parts = [p for p in self.parts if not (p[0] == "lit" and p[1] == "")]
        if len(parts) == 1 and parts[0][0] == "var":
            return parts[0][1]
        return None

    def nested(self):
        return [part[1] for part in self.parts if part[0] == "sub"]

    def has(self, kind):
        return any(part[0] == kind for part in self.parts)


class _Cmd:
    __slots__ = ("words", "redirects", "heredocs")

    def __init__(self):
        self.words = []
        self.redirects = []   # (op, Word)
        self.heredocs = []    # (body text, delimiter was quoted)

    def empty(self):
        return not (self.words or self.redirects or self.heredocs)


# --- the bash reader -----------------------------------------------------------------

_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SPECIAL_PARAM = "@*#?$!-0123456789"
_REDIRECT_RE = re.compile(r"(\d*)(<<<|<<-|<<|<>|<&|>&|>>|>\||&>>|&>|<|>)")
_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?\+?=")
_ANSI_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b",
                 "e": "\x1b", "E": "\x1b", "f": "\f", "v": "\v", "\\": "\\",
                 "'": "'", '"': '"', "?": "?"}


class _BashReader:
    """A quote-aware reader for the bash a hook is handed. It does not run
    anything and does not expand anything; it records what is literal."""

    def __init__(self, text):
        self.s = text
        self.i = 0
        self.n = len(text)
        self.pending = []  # (cmd, delimiter, strip_tabs)
        self.nest = 0

    def _peek(self, k=0):
        j = self.i + k
        return self.s[j] if j < self.n else ""

    def parse(self, stop=None):
        """A list of `_Cmd`, to the end of the text or to `stop` (`)`)."""
        self.nest += 1
        if self.nest > _PARSE_NEST_LIMIT:
            raise Unparsed("nesting")
        cmds = []
        cur = _Cmd()

        def finish():
            nonlocal cur
            if not cur.empty():
                cmds.append(cur)
            cur = _Cmd()

        while True:
            if self.i >= self.n:
                if stop:
                    raise Unparsed("unterminated-substitution")
                if self.pending:
                    raise Unparsed("unterminated-heredoc")
                break
            c = self.s[self.i]
            if stop == ")" and c == ")":
                self.i += 1
                break
            if c in " \t\r":
                self.i += 1
                continue
            if c == "\\" and self._peek(1) == "\n":
                self.i += 2
                continue
            if c == "\n":
                finish()
                self.i += 1
                self._read_heredocs()
                continue
            if c == "#":
                while self.i < self.n and self.s[self.i] != "\n":
                    self.i += 1
                continue
            if c == "(" and self._peek(1) == "(" and not cur.words:
                self._skip_arith_command()
                continue
            if c in "<>" and self._peek(1) == "(":
                cur.words.append(self._word(stop))
                continue
            if c in "<>" or (c == "&" and self._peek(1) == ">") or (
                    c.isdigit() and _REDIRECT_RE.match(self.s, self.i)
                    and self._digits_then_redirect()):
                self._redirect(cur, stop)
                continue
            if c in ";&|()":
                finish()
                self.i += 1
                while self.i < self.n and self.s[self.i] in ";&|" and \
                        self.s[self.i - 1] == self.s[self.i]:
                    self.i += 1
                if self.i < self.n and self.s[self.i - 1] == "|" and \
                        self.s[self.i] == "&":
                    self.i += 1
                continue
            cur.words.append(self._word(stop))
        finish()
        self.nest -= 1
        return cmds

    def _digits_then_redirect(self):
        j = self.i
        while j < self.n and self.s[j].isdigit():
            j += 1
        return j < self.n and self.s[j] in "<>" and not (
            j + 1 < self.n and self.s[j + 1] == "(")

    def _skip_arith_command(self):
        depth = 0
        while self.i < self.n:
            c = self.s[self.i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    self.i += 1
                    return
            self.i += 1
        raise Unparsed("unterminated-arithmetic")

    def _redirect(self, cur, stop):
        match = _REDIRECT_RE.match(self.s, self.i)
        if self.s[self.i] == "&":
            op = "&>>" if self.s.startswith("&>>", self.i) else "&>"
            self.i += len(op)
        else:
            op = match.group(2)
            self.i = match.end()
        while self.i < self.n and self.s[self.i] in " \t":
            self.i += 1
        if self.i >= self.n or self.s[self.i] in "\n;&|()<>":
            raise Unparsed("redirect-without-target")
        target = self._word(stop)
        if op in ("<<", "<<-"):
            delim = target.literal if target.literal is not None else target.glob
            self.pending.append((cur, delim, op == "<<-", target.quoted))
        else:
            cur.redirects.append((op, target))

    def _read_heredocs(self):
        while self.pending:
            cmd, delim, strip_tabs, quoted = self.pending.pop(0)
            body = []
            while True:
                if self.i >= self.n:
                    raise Unparsed("unterminated-heredoc")
                end = self.s.find("\n", self.i)
                line = self.s[self.i:] if end == -1 else self.s[self.i:end]
                self.i = self.n if end == -1 else end + 1
                check = line.lstrip("\t") if strip_tabs else line
                if check.rstrip("\r") == delim:
                    break
                body.append(line)
            cmd.heredocs.append(("\n".join(body), quoted))

    def _word(self, stop):
        word = Word()
        start = self.i
        lit = []

        def flush():
            if lit:
                word.parts.append(("lit", "".join(lit)))
                lit.clear()

        while self.i < self.n:
            c = self.s[self.i]
            if c in " \t\r\n;&|()":
                break
            if c in "<>":
                if self._peek(1) == "(":
                    flush()
                    self.i += 2
                    word.parts.append(("sub", self.parse(stop=")")))
                    continue
                break
            if c == "'":
                end = self.s.find("'", self.i + 1)
                if end == -1:
                    raise Unparsed("unbalanced-quote")
                lit.append(self.s[self.i + 1:end])
                word.quoted = True
                self.i = end + 1
                continue
            if c == "$" and self._peek(1) == "'":
                lit.append(self._ansi_c())
                word.quoted = True
                continue
            if c == "$" and self._peek(1) == '"':
                self.i += 1
                continue
            if c == '"':
                flush()
                word.quoted = True
                self.i += 1
                self._dq(word, lit, flush)
                continue
            if c == "\\":
                if self.i + 1 >= self.n:
                    self.i += 1
                    continue
                nxt = self.s[self.i + 1]
                word.quoted = True
                if nxt != "\n":
                    lit.append(nxt)
                self.i += 2
                continue
            if c == "$":
                flush()
                self._dollar(word, lit)
                continue
            if c == "`":
                flush()
                word.parts.append(("sub", self._backtick()))
                continue
            lit.append(c)
            self.i += 1
        flush()
        word.raw = self.s[start:self.i]
        if not word.parts:
            word.parts.append(("lit", ""))
        return word

    def _ansi_c(self):
        self.i += 2
        out = []
        while True:
            if self.i >= self.n:
                raise Unparsed("unbalanced-quote")
            c = self.s[self.i]
            if c == "'":
                self.i += 1
                return "".join(out)
            if c == "\\" and self.i + 1 < self.n:
                nxt = self.s[self.i + 1]
                if nxt in _ANSI_ESCAPES:
                    out.append(_ANSI_ESCAPES[nxt])
                    self.i += 2
                    continue
                if nxt == "x":
                    match = re.match(r"[0-9A-Fa-f]{1,2}", self.s[self.i + 2:])
                    if match:
                        out.append(chr(int(match.group(0), 16)))
                        self.i += 2 + len(match.group(0))
                        continue
                if nxt in "01234567":
                    match = re.match(r"[0-7]{1,3}", self.s[self.i + 1:])
                    out.append(chr(int(match.group(0), 8)))
                    self.i += 1 + len(match.group(0))
                    continue
                out.append(c + nxt)
                self.i += 2
                continue
            out.append(c)
            self.i += 1

    def _dq(self, word, lit, flush):
        """Inside double quotes, after the opening `"`."""
        while True:
            if self.i >= self.n:
                raise Unparsed("unbalanced-quote")
            c = self.s[self.i]
            if c == '"':
                self.i += 1
                return
            if c == "\\" and self.i + 1 < self.n:
                nxt = self.s[self.i + 1]
                if nxt in '$`"\\':
                    lit.append(nxt)
                elif nxt != "\n":
                    lit.append(c + nxt)
                self.i += 2
                continue
            if c == "$":
                flush()
                self._dollar(word, lit)
                continue
            if c == "`":
                flush()
                word.parts.append(("sub", self._backtick()))
                continue
            lit.append(c)
            self.i += 1

    def _dollar(self, word, lit):
        nxt = self._peek(1)
        if nxt == "(" and self._peek(2) == "(":
            self.i += 3
            depth = 2
            while self.i < self.n and depth:
                if self.s[self.i] == "(":
                    depth += 1
                elif self.s[self.i] == ")":
                    depth -= 1
                self.i += 1
            if depth:
                raise Unparsed("unterminated-arithmetic")
            word.parts.append(("arith",))
            return
        if nxt == "(":
            self.i += 2
            word.parts.append(("sub", self.parse(stop=")")))
            return
        if nxt == "{":
            self.i += 2
            content = self._braced()
            if content.startswith("!") and len(content) > 1:
                word.parts.append(("indirect",))
                return
            body = content[1:] if content.startswith("#") and len(content) > 1 \
                else content
            match = _NAME_RE.match(body)
            if match:
                name, rest = match.group(0), body[match.end():]
            elif body[:1] and body[0] in _SPECIAL_PARAM:
                name, rest = body[0], body[1:]
            else:
                raise Unparsed("bad-substitution")
            word.parts.append(("var", name))
            if rest and ("$" in rest or "`" in rest):
                inner = _BashReader('"' + rest.replace('"', '\\"') + '"')
                inner.nest = self.nest
                sub = inner._word(None)
                word.parts.extend(p for p in sub.parts if p[0] != "lit")
            return
        match = _NAME_RE.match(self.s, self.i + 1)
        if match:
            word.parts.append(("var", match.group(0)))
            self.i = match.end()
            return
        if nxt and nxt in _SPECIAL_PARAM:
            word.parts.append(("var", nxt))
            self.i += 2
            return
        lit.append("$")
        self.i += 1

    def _braced(self):
        """After `${`: the content up to the matching `}`."""
        start = self.i
        depth = 1
        while self.i < self.n:
            c = self.s[self.i]
            if c == "\\":
                self.i += 2
                continue
            if c == "'":
                end = self.s.find("'", self.i + 1)
                if end == -1:
                    raise Unparsed("unbalanced-quote")
                self.i = end + 1
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    content = self.s[start:self.i]
                    self.i += 1
                    return content
            self.i += 1
        raise Unparsed("unterminated-substitution")

    def _backtick(self):
        self.i += 1
        out = []
        while True:
            if self.i >= self.n:
                raise Unparsed("unterminated-substitution")
            c = self.s[self.i]
            if c == "`":
                self.i += 1
                break
            if c == "\\" and self.i + 1 < self.n and self.s[self.i + 1] in "`$\\":
                out.append(self.s[self.i + 1])
                self.i += 2
                continue
            out.append(c)
            self.i += 1
        inner = _BashReader("".join(out))
        inner.nest = self.nest
        return inner.parse()


# --- the PowerShell reader -----------------------------------------------------------

_PS_VAR_RE = re.compile(r"(?:[A-Za-z_][\w]*:)?[A-Za-z_?][\w]*|[$?^_]")


class _PsReader:
    """A quote-aware reader for PowerShell: statements of pipeline elements of
    words. `code` collects the text outside single-quoted strings and
    comments, for the member-access rules."""

    def __init__(self, text):
        self.s = text
        self.i = 0
        self.n = len(text)
        self.code = []
        self.nest = 0

    def _peek(self, k=0):
        j = self.i + k
        return self.s[j] if j < self.n else ""

    def parse(self, stop=None):
        """A list of statements; a statement is a list of elements; an
        element is a list of `Word`."""
        self.nest += 1
        if self.nest > _PARSE_NEST_LIMIT:
            raise Unparsed("nesting")
        stmts, elems, cur = [], [], []

        def end_elem():
            nonlocal cur
            if cur:
                elems.append(cur)
            cur = []

        def end_stmt():
            nonlocal elems
            end_elem()
            if elems:
                stmts.append(elems)
            elems = []

        while True:
            if self.i >= self.n:
                if stop:
                    raise Unparsed("unterminated-substitution")
                break
            c = self.s[self.i]
            if stop and c == stop:
                self.i += 1
                self.code.append(c)
                break
            if c in ")}":
                raise Unparsed("unbalanced-bracket")
            if c in " \t\r":
                self.i += 1
                self.code.append(" ")
                continue
            if c == "`" and self._peek(1) == "\n":
                self.i += 2
                continue
            if c in "\n;":
                end_stmt()
                self.i += 1
                self.code.append("\n")
                continue
            if c == "<" and self._peek(1) == "#":
                end = self.s.find("#>", self.i + 2)
                if end == -1:
                    raise Unparsed("unterminated-comment")
                self.i = end + 2
                continue
            if c == "#":
                while self.i < self.n and self.s[self.i] != "\n":
                    self.i += 1
                continue
            if c in "&|" and self._peek(1) == c:
                end_stmt()
                self.i += 2
                continue
            if c == "|":
                end_elem()
                self.i += 1
                self.code.append("|")
                continue
            if c == "&":
                cur.append(Word.lit("&"))
                self.i += 1
                self.code.append("&")
                continue
            cur.append(self._word(stop))
        end_stmt()
        self.nest -= 1
        return stmts

    def _word(self, stop):
        word = Word()
        start = self.i
        lit = []

        def flush():
            if lit:
                word.parts.append(("lit", "".join(lit)))
                lit.clear()

        while self.i < self.n:
            c = self.s[self.i]
            if c in " \t\r\n;|" or (stop and c == stop) or c in ")}":
                break
            if c == "&" and self._peek(1) == "&":
                break
            if c == "`":
                if self.i + 1 < self.n:
                    lit.append(self.s[self.i + 1])
                    self.code.append(self.s[self.i:self.i + 2])
                self.i += 2
                word.quoted = True
                continue
            if c == "@" and self._peek(1) in "'\"" and self._here_start():
                flush()
                self._here_string(word, lit, flush)
                continue
            if c == "'":
                lit.append(self._sq())
                word.quoted = True
                continue
            if c == '"':
                flush()
                word.quoted = True
                self.i += 1
                self.code.append('"')
                self._dq(word, lit, flush, '"')
                continue
            if c == "$":
                flush()
                self._dollar(word, lit)
                continue
            if c in "(" or (c in "@$" and self._peek(1) == "("):
                flush()
                self.i += 2 if c in "@$" else 1
                self.code.append("(")
                word.parts.append(("sub", self.parse(stop=")")))
                continue
            if c == "{" or (c == "@" and self._peek(1) == "{"):
                flush()
                self.i += 2 if c == "@" else 1
                self.code.append("{")
                word.parts.append(("sub", self.parse(stop="}")))
                continue
            lit.append(c)
            self.code.append(c)
            self.i += 1
        flush()
        word.raw = self.s[start:self.i]
        if not word.parts:
            word.parts.append(("lit", ""))
        return word

    def _here_start(self):
        j = self.i + 2
        while j < self.n and self.s[j] in " \t":
            j += 1
        return j < self.n and self.s[j] in "\r\n"

    def _here_string(self, word, lit, flush):
        quote = self.s[self.i + 1]
        nl = self.s.find("\n", self.i)
        close = re.compile(r"\n[ \t]*" + re.escape(quote) + "@")
        match = close.search(self.s, nl)
        if not match:
            raise Unparsed("unterminated-here-string")
        body = self.s[nl + 1:match.start()]
        self.i = match.end()
        if quote == "'":
            lit.append(body)
            self.code.append("''")
            return
        inner = _PsReader('"' + body.replace('"', '`"') + '"')
        inner.nest = self.nest
        sub = inner._word(None)
        word.parts.extend(sub.parts)
        self.code.extend(inner.code)

    def _sq(self):
        out = []
        self.i += 1
        while True:
            if self.i >= self.n:
                raise Unparsed("unbalanced-quote")
            c = self.s[self.i]
            if c == "'":
                if self._peek(1) == "'":
                    out.append("'")
                    self.i += 2
                    continue
                self.i += 1
                self.code.append("''")
                return "".join(out)
            out.append(c)
            self.i += 1

    def _dq(self, word, lit, flush, quote):
        while True:
            if self.i >= self.n:
                raise Unparsed("unbalanced-quote")
            c = self.s[self.i]
            if c == quote:
                if self._peek(1) == quote:
                    lit.append(quote)
                    self.i += 2
                    continue
                self.i += 1
                self.code.append(quote)
                return
            if c == "`" and self.i + 1 < self.n:
                lit.append(self.s[self.i + 1])
                self.i += 2
                continue
            if c == "$":
                flush()
                self._dollar(word, lit)
                continue
            lit.append(c)
            self.code.append(c)
            self.i += 1

    def _dollar(self, word, lit):
        nxt = self._peek(1)
        if nxt == "(":
            self.i += 2
            self.code.append("$(")
            word.parts.append(("sub", self.parse(stop=")")))
            return
        if nxt == "{":
            end = self.s.find("}", self.i + 2)
            if end == -1:
                raise Unparsed("unterminated-substitution")
            name = self.s[self.i + 2:end]
            self.code.append(self.s[self.i:end + 1])
            self.i = end + 1
            word.parts.append(("var", name))
            return
        match = _PS_VAR_RE.match(self.s, self.i + 1)
        if match:
            self.code.append(self.s[self.i:match.end()])
            word.parts.append(("var", match.group(0)))
            self.i = match.end()
            return
        lit.append("$")
        self.code.append("$")
        self.i += 1


# --- judging ---------------------------------------------------------------------------


class _Ctx:
    """What one judgement found, and the names the command assigned."""

    def __init__(self):
        self.found = []
        self.assigned = {}  # name -> literal value, or None (not literal)

    def add(self, label):
        if label not in self.found:
            self.found.append(label)


def _deeper(depth, ctx):
    if depth + 1 > MAX_DEPTH:
        ctx.add("could-not-tell:nesting")
        return False
    return True


def _bash_text(text, depth, ctx):
    """Judge bash `text` at nesting `depth`."""
    try:
        cmds = _BashReader(text).parse()
    except Unparsed as exc:
        ctx.add(f"could-not-tell:{exc.args[0]}")
        return
    except RecursionError:
        ctx.add("could-not-tell:nesting")
        return
    _bash_cmds(cmds, depth, ctx)


def _bash_cmds(cmds, depth, ctx):
    for cmd in cmds:
        _bash_cmd(cmd, depth, ctx)


def _nested_parts(words, depth, ctx, shell="bash"):
    for word in words:
        if word.has("indirect"):
            ctx.add("could-not-tell:indirect-expansion")
        for nested in word.nested():
            if not _deeper(depth, ctx):
                continue
            if shell == "bash":
                _bash_cmds(nested, depth + 1, ctx)
            else:
                _ps_stmts(nested, depth + 1, ctx)


def _bash_cmd(cmd, depth, ctx):
    _nested_parts(cmd.words + [w for _, w in cmd.redirects], depth, ctx)
    for op, target in cmd.redirects:
        if op in ("<", "<>") and _is_environ_path(target.glob):
            ctx.add("env-dump:proc-environ")
    for body, quoted in cmd.heredocs:
        # An unquoted heredoc's substitutions run in the outer shell.
        if not quoted and ("$(" in body or "`" in body):
            try:
                inner = _BashReader('"' + body.replace("\\", "\\\\")
                                    .replace('"', '\\"') + '"')
                _nested_parts([inner._word(None)], depth, ctx)
            except Unparsed:
                pass
    _argv(cmd.words, cmd, depth, ctx)


_RESERVED = frozenset(("!", "{", "}", "do", "then", "else", "elif", "if",
                       "while", "until", "done", "fi", "esac", "in", "[[", "]]",
                       "coproc"))
_SHELLS = frozenset(("bash", "sh", "zsh", "dash", "ksh", "mksh", "ash",
                     "busybox-sh"))
_PY_RE = re.compile(r"^(?:python[0-9.]*|pypy[0-9.]*|py)$")
_PRINTERS = frozenset(("echo", "printf", "print"))
_GREPS = frozenset(("grep", "egrep", "fgrep", "zgrep", "rg", "ag"))


def _head_name(text):
    name = text.replace("\\", "/").rsplit("/", 1)[-1]
    lower = name.lower()
    if lower.endswith(".exe"):
        name = name[:-4]
    return name


def _record_assignment(word, ctx):
    raw = word.literal if word.literal is not None else word.glob
    name = re.match(r"[A-Za-z_][A-Za-z0-9_]*", raw).group(0)
    eq = raw.index("=")
    value = word.literal[eq + 1:] if word.literal is not None else None
    ctx.assigned[name] = value


def _is_assignment(word):
    first = word.parts[0] if word.parts else None
    return bool(first and first[0] == "lit" and _ASSIGN_RE.match(first[1]))


def _lits(words):
    """Every word's literal text, or None when any is not literal."""
    out = []
    for word in words:
        if word.literal is None:
            return None
        out.append(word.literal)
    return out


def _skip_options(words, with_arg, start=1, stop_at_operand=True):
    """Index of the first operand after options; options in `with_arg` take
    the next word."""
    i = start
    while i < len(words):
        text = words[i].literal
        if text is None:
            return i
        if text == "--":
            return i + 1
        if not text.startswith("-") or text == "-":
            return i
        if "=" not in text and text in with_arg:
            i += 2
            continue
        i += 1
    return i


def _stdin_bodies(cmd):
    """Herestring and heredoc bodies fed to this command: (text or None)."""
    if cmd is None:
        return []
    out = [w.literal for op, w in cmd.redirects if op == "<<<"]
    out.extend(body for body, _ in cmd.heredocs)
    return out


def _argv(words, cmd, depth, ctx, shell="bash"):
    """Judge one simple command's words."""
    while words and _is_assignment(words[0]):
        _record_assignment(words[0], ctx)
        words = words[1:]
    while words and words[0].literal in _RESERVED:
        words = words[1:]
    if not words:
        return
    head = words[0]
    if head.literal in ("for", "select"):
        if len(words) > 1 and words[1].literal:
            ctx.assigned[words[1].literal] = None
        return
    if head.literal == "case":
        return
    if head.literal == "function":
        _argv(words[2:], cmd, depth, ctx, shell)
        return
    if head.literal == "time":
        _argv(words[2:] if len(words) > 1 and words[1].literal == "-p"
              else words[1:], cmd, depth, ctx, shell)
        return
    if head.literal is None:
        _program_from_variable(words, cmd, depth, ctx)
        return
    name = _head_name(head.literal)
    lower = name.lower()
    handler = _HANDLERS.get(name) or _HANDLERS.get(lower)
    if handler is None and _PY_RE.match(lower):
        handler = _interp("python", ("-c",), cluster="c")
    if handler is not None:
        if handler(words, cmd, depth, ctx) is not False:
            return
    _operands_check(name, words, ctx)


def _program_from_variable(words, cmd, depth, ctx):
    head = words[0]
    var = head.simple_var
    if var is None:
        ctx.add("could-not-tell:program")
        return
    if var in ctx.assigned:
        value = ctx.assigned[var]
        if value is None or not value.strip():
            ctx.add("could-not-tell:program")
            return
        _argv([Word.lit(value)] + words[1:], cmd, depth, ctx)
        return
    # From the session's environment: the program is not judged, inline code
    # handed to it is.
    if var.upper() in ("SHELL", "BASH", "SH"):
        _shell(words, cmd, depth, ctx)
        return
    flags = ("-c", "-e", "-E", "-r", "--eval", "-p", "--print")
    for i, word in enumerate(words[1:-1], start=1):
        if word.literal in flags:
            code = words[i + 1].literal
            if code is None:
                ctx.add("could-not-tell:code")
            else:
                _scan_code(code, "any", ctx)
    _operands_check(var, words, ctx)


def _operands_check(name, words, ctx):
    """A `/proc/<pid>/environ` operand of a program that is not mention-only."""
    mention = set()
    lower = name.lower()
    if lower in _PRINTERS or lower in ("write-output", "write-host"):
        return
    if lower == "git" and len(words) > 1:
        sub = words[1].literal
        if sub == "commit":
            for i, word in enumerate(words):
                text = word.literal or ""
                if text in ("-m", "--message") and i + 1 < len(words):
                    mention.add(i + 1)
                elif text.startswith("-m") or text.startswith("--message="):
                    mention.add(i)
        elif sub == "grep":
            mention |= _grep_pattern(words, 2)
    elif lower in _GREPS:
        mention |= _grep_pattern(words, 1)
    for i, word in enumerate(words[1:], start=1):
        if i not in mention and _is_environ_path(word.glob):
            ctx.add("env-dump:proc-environ")


def _grep_pattern(words, start):
    """Indexes of grep's pattern operand(s)."""
    out = set()
    explicit = False
    for i in range(start, len(words)):
        text = words[i].literal or ""
        if text in ("-e", "--regexp") and i + 1 < len(words):
            out.add(i + 1)
            explicit = True
        elif text.startswith("--regexp="):
            out.add(i)
            explicit = True
        elif text in ("-f", "--file"):
            explicit = True
    if explicit:
        return out
    with_arg = {"-A", "-B", "-C", "-m", "--max-count", "-d", "-D", "-t",
                "--type", "-g", "--glob", "--include", "--exclude"}
    i = _skip_options(words, with_arg, start)
    if i < len(words):
        out.add(i)
    return out


# --- handlers ------------------------------------------------------------------------


def _h_env(words, cmd, depth, ctx):
    i = 1
    ignore = False
    while i < len(words):
        word = words[i]
        text = word.literal
        if _is_assignment(word):
            _record_assignment(word, ctx)
            i += 1
            continue
        if text is None:
            break
        if text in ("-i", "--ignore-environment", "-"):
            ignore = True
            i += 1
        elif text in ("-u", "--unset", "-C", "--chdir"):
            i += 2
        elif text.startswith(("--unset=", "--chdir=")):
            i += 1
        elif text in ("-S", "--split-string") or text.startswith(
                "--split-string=") or (text.startswith("-S") and len(text) > 2):
            if text.startswith("--split-string="):
                code = text.split("=", 1)[1]
            elif len(text) > 2 and not text.startswith("--"):
                code = text[2:]
            else:
                code = words[i + 1].literal if i + 1 < len(words) else None
            if code is None:
                ctx.add("could-not-tell:code")
            elif _deeper(depth, ctx):
                _bash_text(code, depth + 1, ctx)
            return True
        elif text == "--":
            i += 1
            break
        elif text.startswith("-") and len(text) > 1:
            if not text.startswith("--") and "i" in text.split("u")[0]:
                ignore = True
            i += 1
        else:
            break
    while i < len(words) and _is_assignment(words[i]):
        _record_assignment(words[i], ctx)
        i += 1
    rest = words[i:]
    if not rest:
        if not ignore:
            ctx.add("env-dump:env")
        return True
    _argv(rest, cmd, depth, ctx)
    return True


def _h_printenv(words, cmd, depth, ctx):
    del cmd, depth
    operands = [w for w in words[1:] if not (w.literal or "x").startswith("-")]
    if not operands:
        ctx.add("env-dump:printenv")
    for word in operands:
        if word.literal is None:
            ctx.add("could-not-tell:printenv-name")
        elif is_secret_name(word.literal):
            ctx.add("secret-read:printenv")
    return True


def _h_set(words, cmd, depth, ctx):
    del cmd, depth
    if len(words) == 1:
        ctx.add("env-dump:set")
    return True


def _declare_like(form, words, ctx, functions_ok=True):
    opts, operands = [], []
    for word in words[1:]:
        text = word.literal
        if text is not None and text[:1] in "-+" and len(text) > 1 \
                and not operands:
            opts.append(text)
        else:
            operands.append(word)
    letters = "".join(o[1:] for o in opts)
    if not operands:
        if functions_ok and ("f" in letters or "F" in letters):
            return True
        ctx.add(f"env-dump:{form}")
        return True
    for word in operands:
        if _is_assignment(word):
            _record_assignment(word, ctx)
            continue
        if "p" in letters:
            if word.literal is None:
                ctx.add("could-not-tell:declare-name")
            elif is_secret_name(word.literal):
                ctx.add(f"secret-read:{form}")
    return True


def _h_declare(words, cmd, depth, ctx):
    del cmd, depth
    return _declare_like(_head_name(words[0].literal), words, ctx)


def _h_export(words, cmd, depth, ctx):
    del cmd, depth
    return _declare_like("export", words, ctx)


def _h_readonly(words, cmd, depth, ctx):
    del cmd, depth
    return _declare_like("readonly", words, ctx)


def _h_local(words, cmd, depth, ctx):
    del cmd, depth
    for word in words[1:]:
        if _is_assignment(word):
            _record_assignment(word, ctx)
    return True


def _h_systemctl(words, cmd, depth, ctx):
    del cmd, depth
    if any(w.literal == "show-environment" for w in words[1:]):
        ctx.add("env-dump:systemctl")
    return False


def _h_tmux(words, cmd, depth, ctx):
    del cmd, depth
    for i, word in enumerate(words):
        if word.literal in ("show-environment", "showenv"):
            j = _skip_options(words, {"-t"}, i + 1)
            names = words[j:]
            if not names:
                ctx.add("env-dump:tmux")
            for name in names:
                if name.literal is None or is_secret_name(name.literal):
                    ctx.add("secret-read:tmux")
            return True
    return False


_PS_WITH_ARG = set("-o -O -p -u -U -g -G -t -C -q --format --pid --sort "
                   "--ppid --user --group --tty".split())


def _h_ps(words, cmd, depth, ctx):
    del cmd, depth
    i = 1
    while i < len(words):
        text = words[i].literal
        if text is None:
            i += 1
            continue
        if text.startswith("-"):
            if text in _PS_WITH_ARG or (len(text) > 1 and not text.startswith(
                    "--") and text[-1] in "oOpuUgGtCq"):
                i += 2
                continue
            i += 1
            continue
        if text.isalpha():
            if "e" in text:
                ctx.add("env-dump:ps")
                return True
            if any(ch in text for ch in "oOpUtk"):
                i += 2
                continue
        i += 1
    return False


def _h_printer(words, cmd, depth, ctx):
    del cmd, depth
    if _head_name(words[0].literal) == "printf" and any(
            (w.literal or "").startswith("-v") for w in words[1:2]):
        return True
    for word in words[1:]:
        if any(is_secret_name(v) for v in word.vars):
            ctx.add(f"secret-read:{_head_name(words[0].literal)}")
    return True


def _h_eval(words, cmd, depth, ctx):
    del cmd
    texts = _lits(words[1:])
    if texts is None:
        ctx.add("could-not-tell:eval")
        return True
    if _deeper(depth, ctx):
        _bash_text(" ".join(texts), depth + 1, ctx)
    return True


def _h_alias(words, cmd, depth, ctx):
    del cmd
    for word in words[1:]:
        text = word.literal
        if text is None:
            ctx.add("could-not-tell:alias")
            continue
        if "=" in text and _deeper(depth, ctx):
            _bash_text(text.split("=", 1)[1], depth + 1, ctx)
    return True


def _h_source(words, cmd, depth, ctx):
    del words, cmd, depth, ctx
    return True


def _shell(words, cmd, depth, ctx):
    i = 1
    code_mode = False
    operand = None
    while i < len(words):
        text = words[i].literal
        if text is None:
            operand = i
            break
        if text == "--":
            operand = i + 1 if i + 1 < len(words) else None
            break
        if text in ("-o", "+o", "-O", "+O"):
            i += 2
            continue
        if text.startswith("-") and len(text) > 1 and not text.startswith("--"):
            if "c" in text[1:]:
                code_mode = True
            i += 1
            continue
        if text.startswith("--"):
            i += 1
            continue
        operand = i
        break
    if code_mode:
        if operand is None or operand >= len(words):
            return True
        code = words[operand].literal
        if code is None:
            ctx.add("could-not-tell:code")
        elif _deeper(depth, ctx):
            _bash_text(code, depth + 1, ctx)
        return True
    if operand is None:
        for body in _stdin_bodies(cmd):
            if body is None:
                ctx.add("could-not-tell:code")
            elif _deeper(depth, ctx):
                _bash_text(body, depth + 1, ctx)
    return True


def _h_shell(words, cmd, depth, ctx):
    return _shell(words, cmd, depth, ctx)


def _interp(lang, flags, cluster="", program_operand=False, with_arg=(),
            subcommand=None):
    """A handler for an interpreter: inline code after one of `flags` (or a
    single-dash cluster ending in a letter of `cluster`), the first operand
    when `program_operand` (awk, jq), and stdin bodies when no script."""
    with_arg = set(with_arg)

    def handler(words, cmd, depth, ctx):
        del depth
        codes = []
        i = 1
        operand = None
        explicit_file = False
        while i < len(words):
            word = words[i]
            text = word.literal
            if text is None:
                if program_operand and operand is None:
                    codes.append(None)
                    operand = i
                i += 1
                continue
            if subcommand and text == subcommand and operand is None:
                if i + 1 < len(words):
                    codes.append(words[i + 1].literal)
                operand = i
                break
            matched = False
            for flag in flags:
                if text == flag:
                    codes.append(words[i + 1].literal if i + 1 < len(words)
                                 else "")
                    i += 2
                    matched = True
                    break
                if flag.startswith("--") and text.startswith(flag + "="):
                    codes.append(text[len(flag) + 1:])
                    i += 1
                    matched = True
                    break
            if matched:
                continue
            if cluster and text.startswith("-") and not text.startswith("--") \
                    and len(text) > 2 and text[-1] in cluster:
                codes.append(words[i + 1].literal if i + 1 < len(words) else "")
                i += 2
                continue
            if text in ("-f", "--from-file"):
                explicit_file = True
                i += 2
                continue
            if text in with_arg:
                i += 3 if text in ("--arg", "--argjson", "--slurpfile",
                                   "--rawfile") else 2
                continue
            if text.startswith("-") and text != "-":
                i += 1
                continue
            if operand is None:
                operand = i
                if program_operand and not explicit_file and not codes:
                    codes.append(text)
            if not program_operand:
                break
            i += 1
        if not codes and (operand is None or words[operand].literal == "-"):
            codes.extend(_stdin_bodies(cmd))
        for code in codes:
            if code is None:
                ctx.add("could-not-tell:code")
            else:
                _scan_code(code, lang, ctx)
        _operands_check(_head_name(words[0].literal), words, ctx)
        return True

    return handler


def _h_cmd(words, cmd, depth, ctx):
    del cmd, depth
    for i, word in enumerate(words[1:], start=1):
        text = (word.literal or "").lower()
        if text in ("/c", "/k", "/r"):
            rest = _lits(words[i + 1:])
            if rest is None:
                ctx.add("could-not-tell:code")
            else:
                _cmd_text(" ".join(rest), ctx)
            return True
    return False


def _cmd_text(text, ctx):
    """A cmd.exe command line: `set` listing, `echo %SECRET%`."""
    for part in re.split(r"&&|\|\||&|\|", text.strip().strip('"')):
        part = part.strip().lstrip("@").strip().strip('"').strip()
        match = re.match(r"(\S+)\s*(.*)$", part, re.S)
        if not match:
            continue
        verb, rest = match.group(1).lower(), match.group(2)
        if verb == "set" and "=" not in rest and not rest.lower().startswith(
                ("/a", "/p")):
            ctx.add("env-dump:cmd-set")
        elif verb == "echo" or verb.startswith("echo."):
            for name in re.findall(r"%([^%\s]+)%", rest):
                if is_secret_name(name.split(":", 1)[0]):
                    ctx.add("secret-read:cmd-echo")


def _h_pwsh(words, cmd, depth, ctx):
    del cmd
    for i, word in enumerate(words[1:], start=1):
        text = (word.literal or "").lower()
        if text in ("-encodedcommand", "-enc", "-ec", "-e", "-en", "-encoded"):
            ctx.add("could-not-tell:encoded-command")
            return True
        if text.startswith("-") and len(text) > 1 and "-command".startswith(text):
            rest = _lits(words[i + 1:])
            if rest is None:
                ctx.add("could-not-tell:code")
            elif _deeper(depth, ctx):
                _ps_text(" ".join(rest), depth + 1, ctx)
            return True
        if text in ("-file", "-f"):
            return True
    return True


def _h_ssh(words, cmd, depth, ctx):
    del cmd
    with_arg = set("-b -c -D -E -e -F -I -i -J -L -l -m -O -o -p -Q -R -S -W "
                   "-w -B -P".split())
    i = _skip_options(words, with_arg)
    rest = words[i + 1:]
    if not rest:
        return True
    if _deeper(depth, ctx):
        _bash_text(" ".join(w.dollar for w in rest), depth + 1, ctx)
    return True


def _h_container(words, cmd, depth, ctx):
    if len(words) < 2 or words[1].literal != "exec":
        return False
    with_arg = set("-e --env -u --user -w --workdir --env-file --detach-keys "
                   "-c --container".split())
    i = _skip_options(words, with_arg, 2)
    _argv(words[i + 1:], cmd, depth, ctx)
    return True


def _h_kubectl(words, cmd, depth, ctx):
    if not any(w.literal == "exec" for w in words[1:]):
        return False
    for i, word in enumerate(words):
        if word.literal == "--":
            _argv(words[i + 1:], cmd, depth, ctx)
            return True
    return True


def _h_wsl(words, cmd, depth, ctx):
    i = 1
    exec_mode = False
    while i < len(words):
        text = words[i].literal
        if text in ("-d", "--distribution", "-u", "--user", "--cd"):
            i += 2
            continue
        if text in ("-e", "--exec"):
            exec_mode = True
            i += 1
            break
        if text == "--":
            i += 1
            break
        if text and text.startswith("-"):
            i += 1
            continue
        break
    rest = words[i:]
    if not rest:
        return True
    if exec_mode:
        _argv(rest, cmd, depth, ctx)
    elif _deeper(depth, ctx):
        _bash_text(" ".join(w.dollar for w in rest), depth + 1, ctx)
    return True


def _h_find(words, cmd, depth, ctx):
    i = 1
    found = False
    while i < len(words):
        if words[i].literal in ("-exec", "-execdir", "-ok", "-okdir"):
            found = True
            j = i + 1
            while j < len(words) and words[j].literal not in (";", "+"):
                j += 1
            _argv(words[i + 1:j], cmd, depth, ctx)
            i = j + 1
            continue
        i += 1
    if not found:
        return False
    return True


def _wrapper(with_arg=(), positional=0, lookup=()):
    """A wrapper that runs the rest of its words as a command."""
    with_arg = set(with_arg)

    def handler(words, cmd, depth, ctx):
        i = 1
        while i < len(words):
            text = words[i].literal
            if text is None:
                break
            if text in lookup:
                return True
            if text == "--":
                i += 1
                break
            if text.startswith("-") and len(text) > 1:
                i += 2 if text in with_arg else 1
                continue
            break
        while i < len(words) and _is_assignment(words[i]):
            _record_assignment(words[i], ctx)
            i += 1
        i += positional
        _argv(words[i:], cmd, depth, ctx)
        return True

    return handler


def _h_watch(words, cmd, depth, ctx):
    i = 1
    exec_mode = False
    while i < len(words):
        text = words[i].literal
        if text in ("-n", "--interval", "-q", "--equexit"):
            i += 2
            continue
        if text in ("-x", "--exec"):
            exec_mode = True
            i += 1
            continue
        if text and text.startswith("-"):
            i += 1
            continue
        break
    rest = words[i:]
    if not rest:
        return True
    if exec_mode:
        _argv(rest, cmd, depth, ctx)
        return True
    texts = _lits(rest)
    if texts is None:
        ctx.add("could-not-tell:code")
    elif _deeper(depth, ctx):
        _bash_text(" ".join(texts), depth + 1, ctx)
    return True


_HANDLERS = {
    "env": _h_env,
    "printenv": _h_printenv,
    "set": _h_set,
    "export": _h_export,
    "declare": _h_declare,
    "typeset": _h_declare,
    "readonly": _h_readonly,
    "local": _h_local,
    "systemctl": _h_systemctl,
    "tmux": _h_tmux,
    "ps": _h_ps,
    "echo": _h_printer,
    "printf": _h_printer,
    "print": _h_printer,
    "eval": _h_eval,
    "alias": _h_alias,
    "source": _h_source,
    ".": _h_source,
    "cmd": _h_cmd,
    "pwsh": _h_pwsh,
    "powershell": _h_pwsh,
    "ssh": _h_ssh,
    "docker": _h_container,
    "podman": _h_container,
    "kubectl": _h_kubectl,
    "wsl": _h_wsl,
    "find": _h_find,
    "watch": _h_watch,
    "sudo": _wrapper(("-u", "-g", "-C", "-h", "-p", "-r", "-t", "-U", "-D",
                      "-R", "--user", "--group")),
    "doas": _wrapper(("-u", "-C")),
    "command": _wrapper(lookup=("-v", "-V")),
    "builtin": _wrapper(),
    "exec": _wrapper(("-a",)),
    "nohup": _wrapper(),
    "nice": _wrapper(("-n", "--adjustment")),
    "timeout": _wrapper(("-s", "--signal", "-k", "--kill-after"), positional=1),
    "stdbuf": _wrapper(("-i", "-o", "-e")),
    "setsid": _wrapper(),
    "xargs": _wrapper(("-I", "-n", "-P", "-d", "-E", "-L", "-s", "-a",
                       "--max-args", "--max-procs", "--delimiter",
                       "--arg-file", "--max-lines", "--max-chars")),
    "node": _interp("node", ("-e", "--eval", "-p", "--print")),
    "bun": _interp("node", ("-e", "--eval", "-p", "--print")),
    "deno": _interp("node", ("--eval",), subcommand="eval"),
    "perl": _interp("perl", ("-e", "-E"), cluster="eE"),
    "ruby": _interp("ruby", ("-e",), cluster="e"),
    "php": _interp("php", ("-r",)),
    "awk": _interp("awk", (), program_operand=True, with_arg=("-F", "-v")),
    "gawk": _interp("awk", (), program_operand=True, with_arg=("-F", "-v")),
    "mawk": _interp("awk", (), program_operand=True, with_arg=("-F", "-v")),
    "nawk": _interp("awk", (), program_operand=True, with_arg=("-F", "-v")),
    "jq": _interp("jq", (), program_operand=True,
                  with_arg=("--arg", "--argjson", "--slurpfile", "--rawfile",
                            "--indent", "-L")),
}
for _shell_name in _SHELLS:
    _HANDLERS[_shell_name] = _h_shell


# --- PowerShell judging ---------------------------------------------------------------

_PS_DRIVE_RE = re.compile(
    r"^(?:Microsoft\.PowerShell\.Core\\)?(?:(?P<env>env:|Environment::)|"
    r"(?P<var>variable:))[\\/]?(?P<rest>.*)$", re.IGNORECASE)
_PS_WRITE_CMDLETS = frozenset((
    "set-item", "si", "new-item", "ni", "remove-item", "ri", "rm", "del",
    "erase", "rd", "rmdir", "clear-item", "cli", "rename-item", "rni", "ren",
    "set-variable", "sv", "new-variable", "nv", "remove-variable", "rv",
    "clear-variable", "clv"))
_PS_READ_CMDLETS = frozenset((
    "get-item", "gi", "get-childitem", "gci", "dir", "ls", "get-content", "gc",
    "cat", "type", "get-itemproperty", "gp", "get-itempropertyvalue", "gpv"))
_PS_PRINTERS = frozenset((
    "write-output", "echo", "write", "write-host", "write-information",
    "out-host", "out-string", "out-default"))
_PS_GETENVS_RE = re.compile(
    r"\[\s*(?:System\s*\.\s*)?Environment\s*\]\s*::\s*GetEnvironmentVariables\b",
    re.IGNORECASE)
_PS_GETENV_RE = re.compile(
    r"\[\s*(?:System\s*\.\s*)?Environment\s*\]\s*::\s*GetEnvironmentVariable\s*"
    r"\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
_PS_STARTINFO_RE = re.compile(r"\.\s*StartInfo\s*\.\s*Environment(?:Variables)?\b",
                              re.IGNORECASE)
_PS_ASSIGN_OPS = frozenset(("=", "+=", "-=", "*=", "/=", "%=", "??="))


def _ps_text(text, depth, ctx):
    """Judge PowerShell `text` at nesting `depth`."""
    reader = _PsReader(text)
    try:
        stmts = reader.parse()
    except Unparsed as exc:
        ctx.add(f"could-not-tell:{exc.args[0]}")
        return
    except RecursionError:
        ctx.add("could-not-tell:nesting")
        return
    code = "".join(reader.code)
    if _PS_GETENVS_RE.search(code):
        ctx.add("env-dump:GetEnvironmentVariables")
    if _PS_STARTINFO_RE.search(code):
        ctx.add("env-dump:StartInfo")
    _ps_stmts(stmts, depth, ctx)


def _ps_stmts(stmts, depth, ctx):
    for elems in stmts:
        for index, words in enumerate(elems):
            _ps_elem(words, index == 0, depth, ctx)


def _ps_word_secrets(word):
    names = [v for v in word.vars if v.lower().startswith("env:")]
    names.extend(_PS_GETENV_RE.findall(word.raw))
    return any(is_secret_name(n) for n in names)


def _ps_elem(words, first, depth, ctx):
    _nested_parts(words, depth, ctx, shell="powershell")
    assigned = False
    if len(words) > 1 and words[1].literal in _PS_ASSIGN_OPS and \
            words[0].raw.startswith("$"):
        words = words[2:]
        assigned = True
    elif words and re.match(r"^\$[\w:{}]+\s*[+\-*/%?]?=", words[0].raw):
        return
    if not words:
        return
    head = words[0]
    raw = head.raw
    if raw.startswith(("$", "[", "(", '"', "'", "@")) or raw[:1].isdigit():
        if first and not assigned and any(_ps_word_secrets(w) for w in words):
            ctx.add("secret-read:env-var")
        return
    if head.literal in ("&", "."):
        rest = words[1:]
        if not rest:
            return
        target = rest[0]
        if target.has("sub") and target.literal is None and \
                not target.vars and len(target.parts) == 1:
            return
        if target.literal is None:
            ctx.add("could-not-tell:program")
            return
        words = rest
        head = target
    if head.literal is None:
        ctx.add("could-not-tell:program")
        return
    name = _head_name(head.literal)
    lower = name.lower()
    if lower not in _PS_WRITE_CMDLETS:
        for word in words[1:]:
            text = word.literal if word.literal is not None else word.glob
            if text.startswith("-") and ":" in text:
                text = text.split(":", 1)[1]
            match = _PS_DRIVE_RE.match(text)
            if not match:
                continue
            rest = match.group("rest")
            if match.group("var"):
                if rest == "" or any(ch in rest for ch in "*?["):
                    ctx.add("env-dump:variable-drive")
                continue
            if rest == "" or any(ch in rest for ch in "*?["):
                ctx.add("env-dump:env-drive")
            elif lower in _PS_READ_CMDLETS and is_secret_name(rest):
                ctx.add("secret-read:env-drive")
    if lower in ("get-variable", "gv"):
        operands = [w for w in words[1:]
                    if not (w.literal or "").startswith("-")]
        if not operands or any("*" in w.glob for w in operands):
            ctx.add("env-dump:Get-Variable")
        return
    if lower in ("invoke-expression", "iex"):
        rest = words[1:]
        if rest and rest[0].literal and rest[0].literal.lower() == "-command":
            rest = rest[1:]
        texts = _lits(rest)
        if texts is None or not rest:
            ctx.add("could-not-tell:iex")
        elif _deeper(depth, ctx):
            _ps_text(" ".join(texts), depth + 1, ctx)
        return
    if lower in _PS_PRINTERS:
        if any(_ps_word_secrets(w) for w in words[1:]):
            ctx.add("secret-read:env-var")
        return
    if lower in ("set", "export", "declare", "typeset", "readonly", "local",
                 "print", "printf"):
        # PowerShell aliases (`set` is Set-Variable) or not commands at all
        # here; the bash rules for these words do not apply.
        _operands_check(name, words, ctx)
        return
    _argv(words, None, depth, ctx, shell="powershell")


# --- the entry points --------------------------------------------------------------------


def findings(text, shell="bash"):
    """Every label the guard finds in `text`, read as `shell` (`bash` or
    `powershell`). Empty means nothing to refuse. Never raises for any
    input: an internal error is could-not-tell."""
    ctx = _Ctx()
    try:
        if shell == "powershell":
            _ps_text(text, 0, ctx)
        else:
            _bash_text(text, 0, ctx)
    except Exception as exc:  # pylint: disable=broad-except
        ctx.add(f"could-not-tell:internal-error:{type(exc).__name__}")
    return list(ctx.found)


def resolve_mode(root):
    """`(mode, note)`: `off`, `report` or `block`. A config layer that exists
    and cannot be read forces `block` -- `cloudGuard`'s rule."""
    import crew_common  # pylint: disable=import-outside-toplevel
    import crew_config  # pylint: disable=import-outside-toplevel
    mode = crew_config.resolve_guard(root, RULE)["effective"]
    repo_path = crew_common.repo_config_file(root, "config.json")
    states = (crew_config.layer_state(repo_path),
              crew_config.layer_state(crew_config.GLOBAL_CONFIG_PATH))
    if "corrupt" in states:
        return "block", "a config layer could not be read; failing closed"
    return mode, ""


def _crude_armed(root):
    """Whether a config file arms the guard, read without crew's readers --
    for when those readers themselves failed. Any `envGuard` value other
    than "off" counts as armed, so a value this cannot parse fails closed.
    The twin of env-guard.sh's `_env_guard_armed`."""
    home = os.path.expanduser("~")
    for path in (os.path.join(root, ".crew", "config.json"),
                 os.path.join(home, ".claude", "crew", "config.json")):
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        match = re.search(r'"envGuard"\s*:\s*([^,}]*)', text)
        if match and match.group(1).strip().strip('"').strip() != "off":
            return True
    return False


def _log(root, row):
    """One row to `.crew/guard.log`. Never raises, never creates `.crew/`.
    Rows carry the rule, mode, decision and label -- never the command."""
    try:
        path = os.path.join(root, GUARD_LOG)
        if not os.path.isdir(os.path.dirname(path)):
            return
        flat = ["-" if not f else str(f).replace("\t", " ").replace(
            "\r", " ").replace("\n", " ") for f in row]
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\t".join(flat) + "\n")
    except OSError:
        pass


def _emit_deny(reason):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}) + "\n")


def _read_input():
    """`(data, command, problem)`. `data` None means not ours to judge."""
    try:
        raw = sys.stdin.buffer.read()
        if raw[:3] == b"\xef\xbb\xbf":
            raw = raw[3:]
        if not raw.strip():
            return {}, None, "malformed-input"
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return {}, None, "malformed-input"
    if not isinstance(data, dict):
        return {}, None, "malformed-input"
    if data.get("tool_name") not in ("Bash", "PowerShell"):
        return None, None, ""
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) \
        else None
    if not isinstance(command, str):
        return data, None, "malformed-input"
    if not command.strip():
        return None, None, ""
    return data, command, ""


def stands_down(tool_name, environ=None):
    """True when the OTHER flavour judges this call. By the TOOL, never the
    OS: `bash` judges every Bash call and a PowerShell call unless the .ps1
    twin will run (Windows, twin present); `powershell` judges PowerShell
    calls only. `cloud_guard.stands_down`'s rule."""
    environ = os.environ if environ is None else environ
    flavour = environ.get(FLAVOUR_VAR, "")
    if flavour == "powershell":
        return tool_name == "Bash"
    if flavour == "bash":
        return tool_name == "PowerShell" \
            and environ.get("OS") == "Windows_NT" \
            and os.path.isfile(_PS1_TWIN)
    return False


def _reason(labels):
    head = labels[0]
    kind = head.split(":", 1)[0]
    if kind == "could-not-tell":
        why = ("it could not read this command well enough to tell whether it "
               "prints the environment")
    elif kind == "secret-read":
        why = "this command would print a credential-named variable"
    else:
        why = "this command would print the process environment"
    return (f"crew env guard: refused ({', '.join(labels)}): {why} into the "
            "agent's context, where credentials end up in the transcript. "
            "Read the one non-secret variable you need by name, or use the "
            "credential without printing it. guards.envGuard decides this "
            "(plugin/crew/README.md, \"Environment guard\").")


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
        if not _crude_armed(root):
            sys.stderr.write(f"env-guard: could not read guards.envGuard "
                             f"({type(exc).__name__}); no config arms it, "
                             "so this command is not judged.\n")
            return 0
        mode, note = "block", "the config could not be read; failing closed"
    if mode == "off":
        return 0
    now = str(int(time.time()))
    if problem:
        labels = [f"could-not-tell:{problem}"]
    else:
        shell = "powershell" if data.get("tool_name") == "PowerShell" \
            else "bash"
        labels = findings(command, shell)
    if not labels:
        return 0
    decision = "deny" if mode == "block" else "report:deny"
    for label in labels:
        _log(root, (now, RULE, mode, decision, label, "-"))
    if mode == "block":
        reason = _reason(labels)
        if note:
            reason += f" ({note})"
        _emit_deny(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
