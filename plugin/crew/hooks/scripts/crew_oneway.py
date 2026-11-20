"""The one-way lane's command-text tripwire, REPORT-ONLY (R-34a).

    python3 crew_oneway.py judge [--shell bash|powershell] -- "<command>"
    python3 crew_oneway.py payload          (a PreToolUse JSON payload on stdin)
    python3 crew_oneway.py shapes

The revision-3 plan's one-way list (4.3) names operations only the owner may
approve. This module recognises the first of them in the text of a command a
model runs, and nothing else:

- `hand-edit-terraform-state`: `terraform`, `tofu` or `terragrunt` running
  `state <write>` (anything but `list`, `show`, `pull`, `identities`),
  `import`, `taint`, `untaint`, `force-unlock` or `refresh`.

Later tickets add their own operations and head-keyed rows (state-file writes
and file tools, branch and worktree deletes, wrappers, gh); the entry points
and the result shape are already final.

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
   target (`<<< ""`), and a target that opens a quote runs to the token that
   closes it (`<<< "a b"`). The words stop at a comment, a `#` that starts
   an unquoted word: `terraform state rm x # -help` is a hit. An operator
   with no target, or with a quoted one the segment never closes, makes the
   segment `could-not-tell` (`redirect-target-unseen`) unless its words are
   a hit, which wins: the shell writes somewhere the reader cannot see. A
   segment gives at most one finding. Leading digits are an fd number only at the
   start of a word (`list2>&1` keeps the word `list2`).

Each segment then has its leading `NAME=VALUE` words and `HEAD_PREFIXES`
stripped, and its head (basename, lower-cased, `.exe` dropped) is read. Only a
terraform head is judged; text after any other head never matches (head
precedence). Global options are skipped with `skip_options`, which also
returns every place an unknown option may have swallowed a table subcommand
or terragrunt's `exec`; every such reading is judged and the worst kept, the
earliest on a tie. terragrunt's `run`, `run-all` and `exec` are unwrapped; what
`exec` runs is judged as a new command. A command's words are read once, so
judging it takes time linear in its length.

It is a tripwire, not a boundary (plan 4.0, layer 1). It does not see
terraform behind `bash -c`, `make`, a script, `xargs`, `sudo -u <user>` or a
substitution, terragrunt's `stack run` and `graph`, or a state file written
by any other program.

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
)

# --- the head --------------------------------------------------------------------------------

# A superset of the R-33 tripwire's list (pinned by the test), plus the
# compound-command words a raw segment can start with.
HEAD_PREFIXES = frozenset(("env", "sudo", "command", "time", "then", "do", "else", "!",
                           "if", "elif", "while", "until"))
_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=", re.S)

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
_HIDE = str.maketrans({"&": "\x02", "|": "\x03"})
_SHOW = str.maketrans({"\x02": "&", "\x03": "|"})
# The marker characters in the command itself are replaced first, so no word
# of the command can pass for a lifted operator.
_UNMARK = str.maketrans({_MARK: "�", "\x02": "�", "\x03": "�"})


def _protect(text, shell="bash"):
    """`text` with each redirection operator turned into a word of its own
    that no separator cuts."""
    text = text.translate(_UNMARK)
    return _REDIRECT_RE[shell].sub(lambda m: f" {_MARK}{m.group(0).translate(_HIDE)} ", text)


def _comment(token):
    """Whether the unquoted `token` starts a comment: a `#` that starts a
    word, in bash and in PowerShell."""
    return token.lstrip("()").startswith("#")


def _target(tokens, index):
    """(target, next index) of the operator that stands before `index`;
    the target is None when the reader cannot see one.

    A quoted empty word is a target (`<<< ""`), so the word after it is not.
    A target that opens a quote takes every token up to the one that closes
    it (`<<< "a b"`); when nothing in the segment closes it, the rest of the
    segment is the unseen target."""
    if index >= len(tokens) or tokens[index].startswith(_MARK) or _comment(tokens[index]):
        return None, index
    quote = tokens[index][0]
    end = index
    if quote in _QUOTES and tokens[index].count(quote) % 2:
        end += 1
        while end < len(tokens) and not tokens[end].count(quote) % 2:
            end += 1
        if end == len(tokens):
            return None, end
    return " ".join(tokens[index:end + 1]).strip(_STRIP), end + 1


def _lift(piece):
    """One raw segment: {words, targets, dangling}, or None when empty.

    A token that is only brackets is dropped. A token that is only quotes is
    an empty word: dropped as a word, kept as an operator's target. The
    words stop at a comment (`# -help` is not an argument)."""
    tokens = [token for token in piece.split()
              if token.strip(_STRIP) or any(quote in token for quote in _QUOTES)]
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
        operator = token[1:].translate(_SHOW)
        index += 1
        if _FD_COPY_RE.fullmatch(operator):
            continue
        target, index = _target(tokens, index)
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
        segment = _lift(piece)
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
        return _CLEAR
    scan = _Scan(words)
    starts = {scan.end[at + 1] for at in range(start, len(words)) if words[at] == "exec"}
    for later in sorted(starts, reverse=True):
        if later > start:
            scan.memo[later] = _judge_from(scan, later)
    return _judge_from(scan, start)


def _tf_head(words, start):
    """(index, head) of the terraform head of the command at `start`, or None."""
    index = start
    while index < len(words) and (words[index] in HEAD_PREFIXES or _ASSIGN_RE.match(words[index])):
        index += 1
    if index >= len(words):
        return None
    head = _head_name(words[index])
    return (index, head) if head in TF_HEADS else None


def _judge_from(scan, start):
    if start not in scan.memo:
        found = _tf_head(scan.words, start)
        scan.memo[start] = _CLEAR if found is None else _judge_tf(scan, found[1], found[0] + 1)
    return scan.memo[start]


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
    """One finding per segment (A14). A dangling operator makes the segment
    could-not-tell unless its words are a hit, which wins (A7)."""
    out = []
    for number, segment in enumerate(raw_segments(text, shell)):
        where = {"pass": "raw", "command": number}
        if segment["dangling"]:
            verdict, rule, word = _judge_words(segment["words"])
            if verdict != HIT:
                verdict, rule, word = COULD_NOT_TELL, "redirect-target-unseen", None
            out.append(_finding(verdict, rule, TF_STATE, word=word, **where))
            continue
        _judged(segment["words"], out, where)
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


def judge_payload(payload, context=None):
    """Judge a PreToolUse-shaped payload. A tool other than Bash or
    PowerShell is `not-a-command`; a command payload without a command string
    is `could-not-tell` (`unreadable-input`)."""
    payload = payload if isinstance(payload, dict) else {}
    tool = payload.get("tool_name")
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
