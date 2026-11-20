"""The one-way lane's command-text tripwire, REPORT-ONLY (R-34a, R-34b).

    python3 crew_oneway.py judge [--shell bash|powershell] -- "<command>"
    python3 crew_oneway.py payload          (a PreToolUse JSON payload on stdin)
    python3 crew_oneway.py shapes

The revision-3 plan's one-way list (4.3) names operations only the owner may
approve. This module recognises the first of them in the text of a command a
model runs, or in a file tool's payload, and nothing else:

- `hand-edit-terraform-state`: `terraform`, `tofu` or `terragrunt` running
  `state <write>` (anything but `list`, `show`, `pull`, `identities`),
  `import`, `taint`, `untaint`, `force-unlock` or `refresh` (R-34a); and any
  command or file tool that writes a terraform state file directly (R-34b).

A *state word* is a word whose basename (quotes, brackets and trailing
slashes stripped) ends in `.tfstate` or `.tfstate.<anything>`, any case:
`terraform.tfstate.backup` and the workspace directory `terraform.tfstate.d`
count. In `-x=v` the value `v` is read, and the word is an *option value*.
A state file is written by:

- a redirection whose operator holds `>` into a state word, whatever the
  head (`tfstate-redirect`; a target's quotes are joined as the shell joins
  them); an unexpanded write target (`$`, backtick, `%`) in a segment that
  holds a state word, a lifted input target included, is `could-not-tell`;
- a state word after a writing head: the remove, move, write and in-place
  heads, the last positional of a copy head, `aws s3 rm|mv|cp`, `gsutil
  rm|cp`, `az storage blob upload|delete`, and `git rm|mv|checkout|restore`
  after git's global options. A read head (`cat`, `jq`, `ls`, ...) or a git
  read (`status`, `diff`, `add`, `commit`, ...) is clear; any other head
  with a state word after it is `could-not-tell`. Every word after the
  command's first `--` is a positional, never an option. A terraform head is
  judged by its own table only (head precedence);
- `Write`, `Edit`, `MultiEdit` or `NotebookEdit` naming a state file, its
  paths read as `scope_guard.targets` reads them; with no readable path the
  payload is `could-not-tell`.

Later tickets add their own operations and head-keyed rows (branch and
worktree deletes, wrappers, gh); the entry points and the result shape are
already final.

REPORT-ONLY: nothing in the plugin imports this module, and a test fails if
anything does. It emits the operation name as a string and never imports the
policy table; the test binds the name to its one-way row there. A verdict
refuses nothing until a later ticket wires it.

Verdicts are `hit`, `clear` and `could-not-tell`; any `hit` wins, then any
`could-not-tell`, else `clear`: an unknown never collapses into the
safe-looking value. A finding names its rule, its operation and where it stood
(pass, command, word index) -- never a word of the command.

Reading a command:

1. plain: when `crew_gitallow.plain_commands` reads the text as simple
   commands with literal words, those words are judged and the answer is
   authoritative (`git commit -m "fix terraform state rm docs"` is clear);
2. raw: every chain, redirection and expansion. Quote-blind on purpose.
   Redirection operators are protected first (`2>&1`, `>&2`, `&>`, `&>>`,
   `>|`, `<<`, `<<-`, `<<<`, `>`, `>>`, `<`; for powershell also the
   all-streams `*>&1`, `*>`, `*>>`), then the text is cut at `&&`
   `||` `;` `|` `&` and newline, split on whitespace and stripped of quotes
   and brackets. Each redirection is lifted out of its segment before the head
   is read: an fd copy is dropped, any other operator takes the next word as
   its target. An fd copy ends where its word ends: in `>&2list` the shell's
   target is the file `2list`, so that is read as `>&` with the target
   `2list`, never as `>&2` and a word `list`. A quoted empty word is a
   target (`<<< ""`). A target is the one place quotes are followed: it
   runs to the token where every quote it opens is closed (`<<< "a b"`,
   `<<< a" b"`), an escaped quote closes nothing (`<<< "a\\" b"`; the
   escape is `\\` in bash and a backtick in powershell) and an escaped space
   joins the next token. An operator inside the quotes is put back as it
   stood (`>"a>b"` records `a>b`), and the whitespace between a target's
   tokens is kept as the command had it. The words stop at a comment, a `#`
   that starts an unquoted word: `terraform state rm x # -help` is a hit. The
   comment stops only its own segment, so `echo ok # x; terraform state rm x`
   is a known over-report (a hit). An operator
   with no target, or with a quoted one the segment never closes, makes the
   segment `could-not-tell` (`redirect-target-unseen`) unless its words are
   a hit, which wins: the shell writes somewhere the reader cannot see. A
   segment gives at most one finding. Leading digits are an fd number only at the
   start of a word (`list2>&1` keeps the word `list2`).

Each segment then has its leading `NAME=VALUE` words and `HEAD_PREFIXES`
stripped, and its head (basename, lower-cased, `.exe` dropped) is read. A
terraform head is judged by the terraform table; text after any other head
never matches it (head precedence), and is read only for state words.
Global options are skipped with `skip_options`, which also
returns every place an unknown option may have swallowed a table subcommand
or terragrunt's `exec`; every such reading is judged and the worst kept, the
earliest on a tie. terragrunt's `run`, `run-all` and `exec` are unwrapped; what
`exec` runs is judged as a new command. A command's words are read once, so
judging it takes time linear in its length.

It is a tripwire, not a boundary (plan 4.0, layer 1). It does not see
terraform behind `bash -c`, `make`, a script, `xargs`, `sudo -u <user>` or a
substitution, terragrunt's `stack run` and `graph`, a state file written by
a script or a substitution or under an unexpanded name (`rm $F`), a copy into a directory
(`cp terraform.tfstate backup/`), or a state word only in git's globals.

Exit codes: 0 for every judgement (report-only) and for `shapes`, 2 for a
usage error.
"""
import argparse
import bisect
import json
import re
import sys

import crew_gitallow
import crew_guards

REPORT_ONLY = True

HIT = "hit"
CLEAR = "clear"
COULD_NOT_TELL = "could-not-tell"
NOT_A_COMMAND = "not-a-command"

TF_STATE = "hand-edit-terraform-state"
OPERATIONS_EMITTED = (TF_STATE,)

# --- the terraform table ---------------------------------------------------------------------

TF_HEADS = frozenset(("terraform", "tofu", "terragrunt"))
STATE_READ = frozenset(("list", "show", "pull", "identities"))
TABLE_HITS = {
    "import": "tf-import", "taint": "tf-taint",
    "untaint": "tf-untaint",
    "force-unlock": "tf-force-unlock",
    "refresh": "tf-refresh",
}
# The words whose loss to an unknown option's value changes the verdict.
TABLE_SUBS = frozenset(("state",)) | frozenset(TABLE_HITS)
UNWRAP_WORDS = frozenset(("run", "run-all", "exec"))
SWALLOWABLE_UNWRAPS = frozenset(("exec",))
AMBIGUOUS_SUBS = TABLE_SUBS | SWALLOWABLE_UNWRAPS
HELP_WORDS = frozenset(("-help", "--help", "-h"))
_UNSEEN = ("$", "`", "%")

# (shape, rule, verdict) for `shapes`.
SHAPES = (
    ("-help/--help/-h after the subcommand", "-", CLEAR),
    ("state <sub>, sub not in " + ", ".join(sorted(STATE_READ)), "tf-state-write", HIT),
    ("state with no sub, or a sub holding $ ` %", "tf-state-unseen", COULD_NOT_TELL),
) + tuple((sub, rule, HIT) for sub, rule in TABLE_HITS.items()) + (
    ("subcommand missing, or holding $ ` %", "tf-sub-unseen", COULD_NOT_TELL),
    ("terragrunt exec [opts] cmd with options and no --", "tg-exec-unseen", COULD_NOT_TELL),
    ("redirection operator with no target", "redirect-target-unseen", COULD_NOT_TELL),
    ("redirection (> >> >| &> *> ...) into a state word", "tfstate-redirect", HIT),
    ("redirection into $ ` % while the segment holds a state word", "tfstate-redirect-unseen",
     COULD_NOT_TELL),
    ("rm rmdir unlink shred truncate del erase remove-item ri, a state word", "tfstate-remove",
     HIT),
    ("mv move move-item ren, a state word", "tfstate-move", HIT),
    ("cp copy copy-item install rsync, a state word as the last positional",
     "tfstate-overwrite", HIT),
    ("sed or perl with -i (or a bundle holding i, --in-place), a state word",
     "tfstate-inplace", HIT),
    ("tee set-content add-content out-file sc, a state word", "tfstate-write", HIT),
    ("aws s3 rm|mv, aws s3 cp or gsutil cp into a state word, gsutil rm, "
     "az storage blob upload|delete", "tfstate-remote", HIT),
    ("a read head (cat jq ls ...) or git read, a state word only as an option value",
     "tfstate-option-value", COULD_NOT_TELL),
    ("any other head, a state word after it", "tfstate-head-unseen", COULD_NOT_TELL),
    ("git rm, a state word after the subcommand", "tfstate-git-remove", HIT),
    ("git mv, a state word after the subcommand", "tfstate-git-move", HIT),
    ("git checkout|restore, a state word after the subcommand", "tfstate-git-overwrite", HIT),
    ("git, another subcommand or none, a state word after it", "tfstate-git-unseen",
     COULD_NOT_TELL),
    ("Write Edit MultiEdit NotebookEdit naming a state file", "tfstate-file-tool", HIT),
    ("Write Edit MultiEdit NotebookEdit with no readable path", "file-tool-path-unseen",
     COULD_NOT_TELL),
)

# --- the head --------------------------------------------------------------------------------

# A superset of the R-33 tripwire's list (pinned by the test), plus the
# compound-command words a raw segment can start with.
HEAD_PREFIXES = frozenset(("env", "sudo", "command", "time", "then", "do", "else", "!",
                           "if", "elif", "while", "until"))
_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=", re.S)

# --- state-file writes (R-34b) ---------------------------------------------------------------

_STATE_RE = re.compile(r"\.tfstate(?:\..*)?$", re.I | re.S)
REMOVE_HEADS = frozenset(("rm", "rmdir", "unlink", "shred", "truncate", "del", "erase",
                          "remove-item", "ri"))
MOVE_HEADS = frozenset(("mv", "move", "move-item", "ren"))
COPY_HEADS = frozenset(("cp", "copy", "copy-item", "install", "rsync"))
INPLACE_HEADS = frozenset(("sed", "perl"))
WRITE_HEADS = frozenset(("tee", "set-content", "add-content", "out-file", "sc"))
READ_HEADS = frozenset(("cat", "type", "less", "more", "head", "tail", "jq", "grep", "rg",
                        "get-content", "gc", "ls", "dir", "stat", "file", "wc", "sha256sum",
                        "echo", "printf", "write-output", "write-host"))
GIT_READ_SUBS = frozenset(("status", "log", "diff", "show", "ls-files", "add", "blame"))
GIT_WRITE_SUBS = {"rm": "tfstate-git-remove", "mv": "tfstate-git-move",
                  "checkout": "tfstate-git-overwrite", "restore": "tfstate-git-overwrite"}
_INPLACE_RE = re.compile(r"^(?:-[A-Za-z]*i.*|--in-place(?:=.*)?)$", re.S)
FILE_TOOLS = frozenset(("Write", "Edit", "MultiEdit", "NotebookEdit"))

# --- the raw reader --------------------------------------------------------------------------

# Longest first: fd copies, &> and &>>, >|, here-documents and here-strings,
# > and >>, <. Leading digits are an fd number only at the start of a word:
# in `list2>&1` the shell's word is `list2` and the operator is `>&1`.
# PowerShell also names every stream `*` (`*>&1`, `*>`, `*>>`); in bash a
# `*` there is a glob word, so only the powershell reader takes it.
# An fd copy's operand is a whole word: `>&2list` writes the file `2list`, so
# `>&2` matches only where the word ends (closing quotes may stand between).
# Anywhere else a `>&` glued to its word takes that word as its target.
_FD = r"(?:(?<![^\s;&|(){}])[0-9]+)?"
_GLUED = r"[<>]&(?=[^\s;&|()<>])"
_WORD_END = r"(?=[\"']*(?:$|[\s;&|()<>`]))"
_PS_FD = r"(?:(?<![^\s;&|(){}])(?:[0-9]+|\*))?"


def _redirect_re(fd):
    return re.compile(fd + r"[<>]&(?:[0-9]+|-)" + _WORD_END + "|" + fd + _GLUED + r"|&>>?|" + fd + r">\||" + fd
                      + r"<<[<-]?|" + fd + r">>?|" + fd + r"<")


_REDIRECT_RE = {"bash": _redirect_re(_FD), "powershell": _redirect_re(_PS_FD)}
_FD_COPY_RE = re.compile(r"(?:[0-9]*|\*)[<>]&(?:[0-9]+|-)")
_SEPARATORS_RE = re.compile(r"&&|\|\||[;|&\n\r]")
_STRIP = "\"'(){}"
_QUOTES = "\"'"
_MARK = "\x01"
_ESCAPE = {"bash": "\\", "powershell": "`"}
_HIDE = str.maketrans({"&": "\x02", "|": "\x03"})
_SHOW = str.maketrans({"\x02": "&", "\x03": "|"})
# The marker characters in the command itself are replaced first, so no word
# of the command can pass for a lifted operator.
_UNMARK = str.maketrans({_MARK: "�", "\x02": "�", "\x03": "�"})


def _protect(text, shell="bash"):
    """`text` with each redirection operator turned into a word of its own
    that no separator cuts: the marker, a digit, the operator. The digit
    says where the operator was glued to its neighbour (1 left, 2 right, 3
    both), so a quoted target can put it back as it stood."""
    text = text.translate(_UNMARK)

    def mark(match):
        glue = (match.start() > 0 and not text[match.start() - 1].isspace()) + 2 * (
            match.end() < len(text) and not text[match.end()].isspace())
        return f" {_MARK}{glue}{match.group(0).translate(_HIDE)} "
    return _REDIRECT_RE[shell].sub(mark, text)


def _comment(token):
    """Whether the unquoted `token` starts a comment: a `#` that starts a
    word, in bash and in PowerShell."""
    return token.lstrip("()").startswith("#")


def _quotes(text, quote, skip, escape):
    """(quote, skip) after `text`: the quote left open (or None) and
    whether the last character escapes the next one. Nothing is escaped
    inside single quotes."""
    for char in text:
        if skip:
            skip = False
        elif quote == "'":
            quote = None if char == "'" else quote
        elif char == escape:
            skip = True
        elif quote:
            quote = None if char == quote else quote
        elif char in _QUOTES:
            quote = char
    return quote, skip


def _tokens(piece):
    """(tokens, gaps) of one raw segment: `gaps[i]` is the whitespace the
    command had before `tokens[i]`, the one space `_protect` pads a lifted
    operator with on each side taken off (F1). Every token is kept, one that
    is only brackets too, so a quoted target keeps a literal `(`; `_lift`
    drops such a token as a word and `_target` skips it before a target."""
    tokens, gaps, after_mark = [], [], False
    for match in re.finditer(r"(\s*)(\S+)", piece):
        gap, token = match.groups()
        mark = token.startswith(_MARK)
        gaps.append(gap[after_mark:len(gap) - mark])
        tokens.append(token)
        after_mark = mark
    return tokens, gaps


def _bare(token):
    """Whether `token` is only brackets (no quote): not a word."""
    return not token.strip(_STRIP) and not any(quote in token for quote in _QUOTES)


def _target(tokens, gaps, index, escape="\\"):
    """(target, next index) of the operator that stands before `index`;
    the target is None when the reader cannot see one.

    A quoted empty word is a target (`<<< ""`), so the word after it is not.
    The target runs to the token where every quote it opens is closed
    (`<<< "a b"`, `<<< a" b"`); an escaped quote closes nothing and an
    escaped space joins the next token. An operator lifted from inside the
    quotes is put back as it stood, and the whitespace between the target's
    tokens is the command's own (`gaps`). When nothing in the segment closes
    the quote, the rest of the segment is the unseen target. Tokens that
    are only brackets before the target are not it."""
    while index < len(tokens) and _bare(tokens[index]):
        index += 1
    if index >= len(tokens) or tokens[index].startswith(_MARK) or _comment(tokens[index]):
        return None, index
    parts, quote, skip = [], None, False
    while True:
        text, right = tokens[index], False
        if text.startswith(_MARK):
            text, right = text[2:].translate(_SHOW), text[1] in "23"
        piece = text if not parts else gaps[index] + text
        parts.append(piece)
        quote, skip = _quotes(piece, quote, skip, escape)
        glued = right
        index += 1
        if quote is None and not skip and not glued:
            break
        if index == len(tokens):
            if quote:
                return None, index
            break
        if quote is None and tokens[index].startswith(_MARK) and tokens[index][1] in "02":
            break  # the escaped space ends the word; the operator stands alone
    return "".join(parts).strip(_STRIP), index


def _lift(piece, escape="\\"):
    """One raw segment: {words, targets, dangling}, or None when empty.

    A token that is only brackets is dropped. A token that is only quotes is
    an empty word: dropped as a word, kept as an operator's target. The
    words stop at a comment (`# -help` is not an argument)."""
    tokens, gaps = _tokens(piece)
    out, targets, dangling = [], [], []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith(_MARK):
            if _comment(token):
                break
            if token.strip(_STRIP):
                out.append(token.strip(_STRIP))
            index += 1
            continue
        operator = token[2:].translate(_SHOW)
        index += 1
        if _FD_COPY_RE.fullmatch(operator):
            continue
        target, index = _target(tokens, gaps, index, escape)
        if target is None:
            dangling.append(operator)
        else:
            targets.append((operator, target))
    if not (out or targets or dangling):
        return None
    return {"words": out, "targets": targets, "dangling": dangling}


def raw_segments(text, shell="bash"):
    """The raw pass's segments of `text`, redirections lifted: a list of
    {words, targets: [(operator, target)], dangling: [operator]}."""
    segments = []
    for piece in _SEPARATORS_RE.split(_protect(text, shell)):
        segment = _lift(piece, _ESCAPE[shell])
        if segment is not None:
            segments.append(segment)
    return segments


# --- judging one command ---------------------------------------------------------------------

_RANK = {CLEAR: 0, COULD_NOT_TELL: 1, HIT: 2}
_CLEAR = (CLEAR, None, None)


def _first_worst(readings):
    """The first reading with the worst verdict (A14)."""
    kept = readings[0]
    for reading in readings[1:]:
        if _RANK[reading[0]] > _RANK[kept[0]]:
            kept = reading
    return kept


def _head_name(word):
    head = re.split(r"[\\/]", word)[-1].lower()
    return head[:-4] if head.endswith(".exe") else head


def _unseen(word):
    return any(mark in word for mark in _UNSEEN)


def _takes_value(args, index):
    """Whether the option at `index` takes the next word as its value, read
    exactly as `crew_guards.tf_skip_options` reads one step (pinned by the
    test on every index of every row it holds)."""
    # pylint: disable=protected-access
    name, sep, _value = args[index].lstrip("-").partition("=")
    nxt = args[index + 1] if index + 1 < len(args) else None
    return not sep and nxt is not None and name not in crew_guards._TF_GLOBAL_FLAG_OPTS and (
        name in crew_guards._TF_GLOBAL_VALUE_OPTS or nxt not in crew_guards._TF_OPS
        and not nxt.startswith("-") and crew_guards._HOLE not in nxt)


def _may_swallow(args, j):
    """Whether the word at `j` is an unknown option whose next word would
    change the verdict (`AMBIGUOUS_SUBS`, or a word crew cannot read)."""
    # pylint: disable=protected-access
    word = args[j]
    if not word.startswith("-") or word == "--" or "=" in word:
        return False
    name = word.lstrip("-")
    if name in crew_guards._TF_GLOBAL_VALUE_OPTS or name in crew_guards._TF_GLOBAL_FLAG_OPTS:
        return False
    return args[j + 1] in AMBIGUOUS_SUBS or _unseen(args[j + 1])


class _Scan:  # pylint: disable=too-few-public-methods
    """One command's words, read once so judging it is linear in its length.

    `end[i]` is where the global options from `i` stop (`tf_skip_options`);
    `swallowed` is every index an unknown option may have taken as its value
    (sorted); `help_from[i]` and `dashdash[i]` say whether a help word, and
    how many `--`, stand at `i` or later. `memo` holds each start judged."""

    def __init__(self, words):
        count = len(words)
        self.words = words
        self.end = list(range(count + 1))
        self.help_from = [False] * (count + 1)
        self.dashdash = [0] * (count + 1)
        for i in range(count - 1, -1, -1):
            word = words[i]
            self.help_from[i] = self.help_from[i + 1] or word in HELP_WORDS
            self.dashdash[i] = self.dashdash[i + 1] + (word == "--")
            if word == "--":
                self.end[i] = i + 1
            elif word.startswith("-"):
                self.end[i] = self.end[i + (2 if _takes_value(words, i) else 1)]
        self.swallowed = [j + 1 for j in range(count - 1) if _may_swallow(words, j)]
        self.memo = {}
        self._state = None

    def state_words(self):
        """The same words read for state words (`_StateWords`), once."""
        if self._state is None:
            self._state = _StateWords(self.words)
        return self._state


def skip_options(args, index, scan=None):
    """(end, alternates): `end` is the first word from `index` that is not a
    global option or its value, as crew_guards reads it; `alternates` is each
    index an unknown option took as its value although it is a word that would
    change the verdict (`AMBIGUOUS_SUBS`, or one holding `$`, a backtick or
    `%`). Crew cannot know whether that option
    takes a value, so both readings are judged. `scan` is `args` already read
    (`_Scan`), so a long command costs one read, not one per call."""
    scan = scan if scan is not None else _Scan(args)
    end = scan.end[index]
    alternates = scan.swallowed[bisect.bisect_left(scan.swallowed, index + 1):
                                bisect.bisect_left(scan.swallowed, end)]
    return end, alternates


def _table(scan, at):
    """(verdict, rule, word index) of the subcommand at `at`."""
    words = scan.words
    if at >= len(words):
        return (COULD_NOT_TELL, "tf-sub-unseen", None)
    if scan.help_from[at + 1]:
        return _CLEAR
    sub = words[at]
    if _unseen(sub):
        return (COULD_NOT_TELL, "tf-sub-unseen", at)
    if sub == "state":
        if at + 1 >= len(words) or _unseen(words[at + 1]):
            return (COULD_NOT_TELL, "tf-state-unseen", at)
        if words[at + 1] in STATE_READ:
            return _CLEAR
        return (HIT, "tf-state-write", at + 1)
    if sub in TABLE_HITS:
        return (HIT, TABLE_HITS[sub], at)
    return _CLEAR


def _unwrap(scan, at):
    """terragrunt's `exec`, `run` or `run-all` at `at`."""
    if scan.words[at] == "exec":
        end = scan.end[at + 1]
        readings = []
        if end > at + 1 and scan.dashdash[at + 1] == scan.dashdash[end]:
            readings.append((COULD_NOT_TELL, "tg-exec-unseen", at))
        readings.append(_judge_from(scan, end))
        return _first_worst(readings)
    end, alternates = skip_options(scan.words, at + 1, scan)
    return _first_worst([_table(scan, start) for start in sorted([end] + alternates)])


def _reading(scan, head, at):
    if head == "terragrunt" and at < len(scan.words) and scan.words[at] in UNWRAP_WORDS:
        return _unwrap(scan, at)
    return _table(scan, at)


def _judge_tf(scan, head, index):
    end, alternates = skip_options(scan.words, index, scan)
    readings = {end: _reading(scan, head, end)}
    for at in alternates:
        readings[at] = _reading(scan, head, at)
    return _first_worst([readings[at] for at in sorted(readings)])


def _judge_words(words, start=0):
    """(verdict, rule, word index) of the command that starts at `start`.

    Head precedence first: a command whose head is not terraform's is clear
    before anything after it is read. An `exec` unwrap judges the command
    after it from a later index, so each such index is judged first, latest
    first, and remembered: a chain of any length (`terragrunt exec -- `
    repeated) then needs no deep recursion. The words are read once
    (`_Scan`), so a long command costs time linear in its length."""
    if _tf_head(words, start) is None:
        return _state_head(_StateWords(words), start)
    scan = _Scan(words)
    starts = {scan.end[at + 1] for at in range(start, len(words)) if words[at] == "exec"}
    for later in sorted(starts, reverse=True):
        if later > start:
            scan.memo[later] = _judge_from(scan, later)
    return _judge_from(scan, start)


def _head(words, start):
    """(index, head) of the command at `start`, prefixes stripped, or None."""
    index = start
    while index < len(words) and (words[index] in HEAD_PREFIXES or _ASSIGN_RE.match(words[index])):
        index += 1
    if index >= len(words):
        return None
    return index, _head_name(words[index])


def _tf_head(words, start):
    """(index, head) of the terraform head of the command at `start`, or None."""
    found = _head(words, start)
    return found if found is not None and found[1] in TF_HEADS else None


def _judge_from(scan, start):
    if start not in scan.memo:
        found = _tf_head(scan.words, start)
        scan.memo[start] = (_state_head(scan.state_words(), start) if found is None
                            else _judge_tf(scan, found[1], found[0] + 1))
    return scan.memo[start]


# --- state-file writes under any other head (R-34b) ------------------------------------------

def _state_path(text):
    """Whether `text` names a terraform state file: its basename, quotes,
    brackets and trailing slashes stripped, ends in `.tfstate` or
    `.tfstate.<anything>` (the backup, the workspace directory), any case."""
    base = text.strip(_STRIP).rstrip("/\\")
    return bool(_STATE_RE.search(re.split(r"[\\/]", base)[-1]))


def _state_kind(word):
    """"word" when `word` is a state word, "option" when it is one only as
    an option (`-x=<state>`, or a word that starts with `-`), else None."""
    if word.startswith("-") and "=" in word:
        return "option" if _state_path(word.partition("=")[2]) else None
    if not _state_path(word):
        return None
    return "option" if word.startswith("-") else "word"


class _StateWords:  # pylint: disable=too-few-public-methods
    """One command's words read once for state words, so every start judged
    in it costs constant time past the head (`_Scan`'s linear rule).

    `kind[i]` is `_state_kind`; `next_state[i]` / `next_word[i]` are the
    first index at or after `i` holding a state word of any kind / a
    positional one (`len(words)` when none); `next_plain[i]` the first word
    there not starting with `-`; `next_dashdash[i]` the first `--`;
    `next_inplace[i]` the first in-place option; `last_plain` the last word
    not starting with `-` (-1 when none).

    These read each word alone. Every word after the command's first `--`
    is a positional (B5), whatever it starts with; that `--` depends on
    where the command starts, so the methods below take the head."""

    def __init__(self, words):
        count = len(words)
        self.words = words
        self.kind = [_state_kind(word) for word in words]
        self.next_state = [count] * (count + 1)
        self.next_word = [count] * (count + 1)
        self.next_plain = [count] * (count + 1)
        self.next_dashdash = [count] * (count + 1)
        self.next_inplace = [count] * (count + 1)
        self.last_plain = -1
        for i in range(count - 1, -1, -1):
            word, kind = words[i], self.kind[i]
            plain = not word.startswith("-")
            self.next_state[i] = i if kind else self.next_state[i + 1]
            self.next_word[i] = i if kind == "word" else self.next_word[i + 1]
            self.next_plain[i] = i if plain else self.next_plain[i + 1]
            self.next_dashdash[i] = i if word == "--" else self.next_dashdash[i + 1]
            self.next_inplace[i] = i if _INPLACE_RE.match(word) else self.next_inplace[i + 1]
            if plain and self.last_plain < 0:
                self.last_plain = i

    def positional_state(self, after):
        """Whether a state word stands at `after` or later as a positional:
        a word not starting with `-`, or any state word after the first
        `--` at or after `after` (B5)."""
        dashdash = self.next_dashdash[after]
        return (self.next_word[after] < len(self.words)
                or self.next_state[min(dashdash + 1, len(self.words))] < len(self.words))

    def inplace(self, after):
        """Whether an in-place option stands at `after` or later, before
        the first `--` (after it, `-i` is an operand)."""
        return self.next_inplace[after] < self.next_dashdash[after]

    def plain(self, index, dashdash):
        """The first positional at `index` or later, `dashdash` being the
        command's first `--` (`len(words)` when none)."""
        if index > dashdash:
            return index
        return min(self.next_plain[index], dashdash + 1, len(self.words))


def _last_positional(info, head):
    """The index of the last positional word after `head`, or None: the last
    word when a `--` stands before it, else the last word not starting with
    `-`."""
    count = len(info.words)
    if info.next_dashdash[head + 1] < count - 1:
        return count - 1
    return info.last_plain if info.last_plain > head else None


def _destination(info, head, rule):
    """A copy writes its last positional: a hit when that is a state word."""
    last = _last_positional(info, head)
    if last is not None and info.kind[last]:
        return (HIT, rule, last)
    return _CLEAR


def _positional(info, index, nth):
    """The `nth` word not starting with `-` from `index` (0 is the first),
    or None."""
    count = len(info.words)
    dashdash = info.next_dashdash[min(index, count)]
    index = info.plain(min(index, count), dashdash)
    for _ in range(nth):
        if index >= count:
            return None
        index = info.plain(index + 1, dashdash)
    return info.words[index] if index < count else None


def _remote(info, head, name):
    """aws, gsutil and az: (verdict, rule, index), or None for any other
    subcommand (could-not-tell, as for any other head)."""
    first = _positional(info, head + 1, 0)
    if name == "aws" and first == "s3":
        sub = _positional(info, head + 1, 1)
        if sub in ("rm", "mv"):
            return (HIT, "tfstate-remote", info.next_state[head + 1])
        if sub == "cp":
            return _destination(info, head, "tfstate-remote")
    if name == "gsutil" and first == "rm":
        return (HIT, "tfstate-remote", info.next_state[head + 1])
    if name == "gsutil" and first == "cp":
        return _destination(info, head, "tfstate-remote")
    if name == "az" and first == "storage" and _positional(info, head + 1, 1) == "blob" and (
            _positional(info, head + 1, 2) in ("upload", "delete")):
        return (HIT, "tfstate-remote", info.next_state[head + 1])
    return None


def _git_state(info, head):
    """git: only state words after the subcommand are read (git's globals
    are not, B6)."""
    # pylint: disable=protected-access
    args = info.words[head + 1:]
    sub = crew_gitallow.subcommand(args)
    after = min(head + 1 + crew_gitallow._global_split(args)[1] + 1, len(info.words))
    git_first = info.next_state[after]
    if git_first >= len(info.words):
        return _CLEAR
    if sub in GIT_READ_SUBS:
        if info.positional_state(after):
            return _CLEAR
        return (COULD_NOT_TELL, "tfstate-option-value", git_first)
    if sub == "commit":
        return _CLEAR
    if sub in GIT_WRITE_SUBS:
        return (HIT, GIT_WRITE_SUBS[sub], git_first)
    return (COULD_NOT_TELL, "tfstate-git-unseen", git_first)


def _state_head(info, start):
    """(verdict, rule, word index) of a command at `start` whose head is not
    terraform's: clear unless a state word stands after the head."""
    found = _head(info.words, start)
    if found is None:
        return _CLEAR
    index, head = found
    first = info.next_state[index + 1]
    if first >= len(info.words):
        return _CLEAR
    if head == "git":
        return _git_state(info, index)
    if head in REMOVE_HEADS:
        return (HIT, "tfstate-remove", first)
    if head in MOVE_HEADS:
        return (HIT, "tfstate-move", first)
    if head in COPY_HEADS:
        return _destination(info, index, "tfstate-overwrite")
    if head in INPLACE_HEADS and info.inplace(index + 1):
        return (HIT, "tfstate-inplace", first)
    if head in WRITE_HEADS:
        return (HIT, "tfstate-write", first)
    if head in ("aws", "gsutil", "az"):
        remote = _remote(info, index, head)
        if remote is not None:
            return remote
    if head in READ_HEADS:
        if info.positional_state(index + 1):
            return _CLEAR
        return (COULD_NOT_TELL, "tfstate-option-value", first)
    return (COULD_NOT_TELL, "tfstate-head-unseen", first)


def _unquoted(target):
    """`target` with its quote characters taken out, as the shell joins a
    word built from quoted and unquoted parts (`terra"form.tf"state`)."""
    return target.replace('"', "").replace("'", "")


def _write_reading(operator, target, held):
    """A lifted redirection: a write when its operator holds `>` (fd copies
    are already dropped). The state-word test runs before the expansion
    test, so `> "$D/terraform.tfstate"` is a hit (B3)."""
    if ">" not in operator:
        return _CLEAR
    if _state_path(_unquoted(target)):
        return (HIT, "tfstate-redirect", None)
    if held and _unseen(target):
        return (COULD_NOT_TELL, "tfstate-redirect-unseen", None)
    return _CLEAR


# --- the two passes --------------------------------------------------------------------------

def _finding(verdict, rule, operation, **where):
    out = {"verdict": verdict, "rule": rule, "operation": operation}
    out.update(where)
    return out


def _judged(words, out, where):
    verdict, rule, word = _judge_words(words)
    if verdict != CLEAR:
        out.append(_finding(verdict, rule, TF_STATE, word=word, **where))


def _plain_pass(commands):
    out = []
    for number, words in enumerate(commands):
        _judged(words, out, {"pass": "plain", "command": number})
    return out


def _raw_pass(text, shell):
    """One finding per segment (A14): the head's reading and each write
    target's (B3) are combined, the first worst kept. A dangling operator
    makes the segment could-not-tell unless that reading is a hit, which
    wins (A7)."""
    out = []
    for number, segment in enumerate(raw_segments(text, shell)):
        where = {"pass": "raw", "command": number}
        readings = [_judge_words(segment["words"])]
        # A lifted target is part of the segment too (B3): in
        # `cat < terraform.tfstate > $OUT` the state word is the input's.
        held = any(_state_kind(word) for word in segment["words"]) or any(
            _state_path(_unquoted(target)) for _op, target in segment["targets"])
        readings += [_write_reading(op, target, held) for op, target in segment["targets"]]
        verdict, rule, word = _first_worst(readings)
        if segment["dangling"] and verdict != HIT:
            verdict, rule, word = COULD_NOT_TELL, "redirect-target-unseen", None
        if verdict != CLEAR:
            out.append(_finding(verdict, rule, TF_STATE, word=word, **where))
    return out


def _findings(command, shell):
    commands = crew_gitallow.plain_commands(command, shell)
    if commands is None:
        return _raw_pass(command, shell)
    return _plain_pass(commands)


# --- the entry points ------------------------------------------------------------------------

def _overall(findings):
    verdicts = {f["verdict"] for f in findings}
    if HIT in verdicts:
        return HIT
    if COULD_NOT_TELL in verdicts:
        return COULD_NOT_TELL
    return CLEAR


def _result(findings):
    return {"verdict": _overall(findings), "report_only": True,
            "operations": sorted({f["operation"] for f in findings
                                  if f["verdict"] != CLEAR and f["operation"]}),
            "findings": findings}


def judge(command, shell="bash", context=None):
    """Judge one command text as `shell` (`bash` or `powershell`). `context`
    (ownership and the like) is accepted for the later rows that need it;
    no terraform row depends on it. Returns {verdict, report_only,
    operations, findings}."""
    del context  # accepted and ignored by every terraform row (A4)
    if not isinstance(command, str) or shell not in ("bash", "powershell"):
        return _result([_finding(COULD_NOT_TELL, "unreadable-input", None,
                                 **{"pass": None, "command": None, "word": None})])
    return _result(_findings(command, shell))


_SHELLS = {"Bash": "bash", "PowerShell": "powershell"}


def _tool_paths(tool_input):
    """Every path a file tool's input names, read as `scope_guard.targets`
    reads them (pinned by the test), except that an `edits` that is not a
    list is ignored and an unhashable value is skipped, never raised on."""
    if not isinstance(tool_input, dict):
        return []
    edits = tool_input.get("edits")
    found = [tool_input.get(key) for key in ("file_path", "notebook_path")] + (
        [edit.get("file_path") for edit in edits if isinstance(edit, dict)]
        if isinstance(edits, list) else [])
    return list(dict.fromkeys(path for path in found if isinstance(path, str) and path))


def _file_tool(payload):
    """`Write`, `Edit`, `MultiEdit`, `NotebookEdit`: a hit when any path is
    a state file, could-not-tell when there is no path. No path is ever put
    in the result."""
    paths = _tool_paths(payload.get("tool_input"))
    where = {"pass": "file-tool", "command": None, "word": None}
    if not paths:
        return _result([_finding(COULD_NOT_TELL, "file-tool-path-unseen", TF_STATE, **where)])
    if any(_state_path(path) for path in paths):
        return _result([_finding(HIT, "tfstate-file-tool", TF_STATE, **where)])
    return _result([])


def judge_payload(payload, context=None):
    """Judge a PreToolUse-shaped payload. A file tool is judged on its paths
    (`_file_tool`); a tool other than those and Bash or PowerShell is
    `not-a-command`; a command payload without a command string is
    `could-not-tell` (`unreadable-input`)."""
    payload = payload if isinstance(payload, dict) else {}
    tool = payload.get("tool_name")
    if isinstance(tool, str) and tool in FILE_TOOLS:
        return _file_tool(payload)
    shell = _SHELLS.get(tool) if isinstance(tool, str) else None
    if shell is None:
        return {"verdict": NOT_A_COMMAND, "report_only": True, "operations": [],
                "findings": []}
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    return judge(command, shell, context)


def _main(argv):
    parser = argparse.ArgumentParser(prog="crew_oneway.py",
                                     description=__doc__.split("\n\n", maxsplit=1)[0])
    sub = parser.add_subparsers(dest="action", required=True)
    one = sub.add_parser("judge")
    one.add_argument("--shell", choices=("bash", "powershell"), default="bash")
    one.add_argument("command", nargs="+")
    sub.add_parser("payload")
    sub.add_parser("shapes")
    args = parser.parse_args(argv)
    if args.action == "judge":
        print(json.dumps(judge(" ".join(args.command), args.shell), indent=2))
    elif args.action == "payload":
        try:
            # parse_int: an integer too long for this Python's int() is
            # still JSON, and no field the judgement reads is a number.
            payload = json.loads(sys.stdin.read(), parse_int=float)
        except ValueError:
            print("crew_oneway.py payload: stdin is not JSON", file=sys.stderr)
            return 2
        except RecursionError:
            # JSON nested too deep for this Python to read: no verdict is
            # known, and report-only still exits 0.
            payload = {"tool_name": "Bash"}
        print(json.dumps(judge_payload(payload), indent=2))
    else:
        for shape, rule, verdict in SHAPES:
            print(f"{shape}\t{rule}\t{verdict}\t{TF_STATE}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
