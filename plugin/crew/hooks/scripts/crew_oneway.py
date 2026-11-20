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
   `>|`, `<<`, `<<-`, `<<<`, `>`, `>>`, `<`), then the text is cut at `&&`
   `||` `;` `|` `&` and newline, split on whitespace and stripped of quotes
   and brackets. Each redirection is lifted out of its segment before the head
   is read: an fd copy is dropped, any other operator takes the next word as
   its target. An operator with no target makes the segment
   `could-not-tell` (`redirect-target-unseen`) unless its words are a hit,
   which wins: the shell writes somewhere the reader cannot see. A segment
   gives at most one finding. Leading digits are an fd number only at the
   start of a word (`list2>&1` keeps the word `list2`).

Each segment then has its leading `NAME=VALUE` words and `HEAD_PREFIXES`
stripped, and its head (basename, lower-cased, `.exe` dropped) is read. Only a
terraform head is judged; text after any other head never matches (head
precedence). Global options are skipped with `skip_options`, which also
returns every place an unknown option may have swallowed a table subcommand
or terragrunt's `exec`; every such reading is judged and the worst kept, the
earliest on a tie. terragrunt's `run`, `run-all` and `exec` are unwrapped; what
`exec` runs is judged as a new command.

It is a tripwire, not a boundary (plan 4.0, layer 1). It does not see
terraform behind `bash -c`, `make`, a script, `xargs`, `sudo -u <user>` or a
substitution, terragrunt's `stack run` and `graph`, or a state file written
by any other program.

Exit codes: 0 for every judgement (report-only) and for `shapes`, 2 for a
usage error.
"""
import argparse
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
_FD = r"(?:(?<![^\s;&|(){}])[0-9]+)?"
_REDIRECT_RE = re.compile(_FD + r"[<>]&(?:[0-9]+|-)|&>>?|" + _FD + r">\||" + _FD
                          + r"<<[<-]?|" + _FD + r">>?|" + _FD + r"<")
_FD_COPY_RE = re.compile(r"[0-9]*[<>]&(?:[0-9]+|-)")
_SEPARATORS_RE = re.compile(r"&&|\|\||[;|&\n\r]")
_STRIP = "\"'(){}"
_MARK = "\x01"
_HIDE = str.maketrans({"&": "\x02", "|": "\x03"})
_SHOW = str.maketrans({"\x02": "&", "\x03": "|"})
# The marker characters in the command itself are replaced first, so no word
# of the command can pass for a lifted operator.
_UNMARK = str.maketrans({_MARK: "�", "\x02": "�", "\x03": "�"})


def _protect(text):
    """`text` with each redirection operator turned into a word of its own
    that no separator cuts."""
    text = text.translate(_UNMARK)
    return _REDIRECT_RE.sub(lambda m: f" {_MARK}{m.group(0).translate(_HIDE)} ", text)


def _lift(piece):
    """One raw segment: {words, targets, dangling}, or None when empty."""
    words = [word.strip(_STRIP) for word in piece.split()]
    words = [word for word in words if word]
    out, targets, dangling = [], [], []
    index = 0
    while index < len(words):
        word = words[index]
        if not word.startswith(_MARK):
            out.append(word)
            index += 1
            continue
        operator = word[1:].translate(_SHOW)
        index += 1
        if _FD_COPY_RE.fullmatch(operator):
            continue
        if index < len(words) and not words[index].startswith(_MARK):
            targets.append((operator, words[index]))
            index += 1
        else:
            dangling.append(operator)
    if not (out or targets or dangling):
        return None
    return {"words": out, "targets": targets, "dangling": dangling}


def raw_segments(text):
    """The raw pass's segments of `text`, redirections lifted: a list of
    {words, targets: [(operator, target)], dangling: [operator]}."""
    segments = []
    for piece in _SEPARATORS_RE.split(_protect(text)):
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


def skip_options(args, index):
    """(end, alternates): `end` is the first word from `index` that is not a
    global option or its value, as crew_guards reads it; `alternates` is each
    index an unknown option took as its value although it is a word that would
    change the verdict (`AMBIGUOUS_SUBS`). Crew cannot know whether that option
    takes a value, so both readings are judged."""
    end = crew_guards.tf_skip_options(args, index)
    alternates = []
    for j in range(index, end - 1):
        word = args[j]
        if not word.startswith("-") or word == "--" or "=" in word:
            continue
        name = word.lstrip("-")
        if name in crew_guards._TF_GLOBAL_VALUE_OPTS:  # pylint: disable=protected-access
            continue
        if name in crew_guards._TF_GLOBAL_FLAG_OPTS:  # pylint: disable=protected-access
            continue
        if args[j + 1] in AMBIGUOUS_SUBS:
            alternates.append(j + 1)
    return end, alternates


def _table(words, at):
    """(verdict, rule, word index) of the subcommand at `at`."""
    if at >= len(words):
        return (COULD_NOT_TELL, "tf-sub-unseen", None)
    if any(word in HELP_WORDS for word in words[at + 1:]):
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


def _unwrap(words, at, memo):
    """terragrunt's `exec`, `run` or `run-all` at `at`."""
    if words[at] == "exec":
        end, _ = skip_options(words, at + 1)
        readings = []
        if end > at + 1 and "--" not in words[at + 1:end]:
            readings.append((COULD_NOT_TELL, "tg-exec-unseen", at))
        readings.append(_judge_from(words, end, memo))
        return _first_worst(readings)
    end, alternates = skip_options(words, at + 1)
    return _first_worst([_table(words, start) for start in sorted([end] + alternates)])


def _reading(words, head, at, memo):
    if head == "terragrunt" and at < len(words) and words[at] in UNWRAP_WORDS:
        return _unwrap(words, at, memo)
    return _table(words, at)


def _judge_tf(words, head, index, memo):
    end, alternates = skip_options(words, index)
    readings = {end: _reading(words, head, end, memo)}
    for at in alternates:
        readings[at] = _reading(words, head, at, memo)
    return _first_worst([readings[at] for at in sorted(readings)])


def _judge_words(words, start=0):
    """(verdict, rule, word index) of the command that starts at `start`.

    An `exec` unwrap judges the command after it from a later index, so each
    such index is judged first, latest first, and remembered: a chain of any
    length (`terragrunt exec -- ` repeated) then needs no deep recursion."""
    memo = {}
    starts = {skip_options(words, at + 1)[0] for at in range(start, len(words))
              if words[at] == "exec"}
    for later in sorted(starts, reverse=True):
        if later > start:
            memo[later] = _judge_from(words, later, memo)
    return _judge_from(words, start, memo)


def _judge_from(words, start, memo):
    if start in memo:
        return memo[start]
    index = start
    while index < len(words) and (words[index] in HEAD_PREFIXES or _ASSIGN_RE.match(words[index])):
        index += 1
    if index >= len(words):
        return _CLEAR
    head = _head_name(words[index])
    if head not in TF_HEADS:
        return _CLEAR
    return _judge_tf(words, head, index + 1, memo)


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


def _raw_pass(text):
    """One finding per segment (A14). A dangling operator makes the segment
    could-not-tell unless its words are a hit, which wins (A7)."""
    out = []
    for number, segment in enumerate(raw_segments(text)):
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
        return _raw_pass(command)
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
            payload = json.loads(sys.stdin.read())
        except ValueError:
            print("crew_oneway.py payload: stdin is not JSON", file=sys.stderr)
            return 2
        print(json.dumps(judge_payload(payload), indent=2))
    else:
        for shape, rule, verdict in SHAPES:
            print(f"{shape}\t{rule}\t{verdict}\t{TF_STATE}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
