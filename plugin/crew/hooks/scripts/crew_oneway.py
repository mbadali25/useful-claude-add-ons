"""The one-way lane's command-text tripwire, REPORT-ONLY (R-34a, R-34b, R-34c).

    python3 crew_oneway.py judge [--shell bash|powershell] [--cwd DIR]
        [--own-branch NAME]... [--own-worktree DIR]... -- "<command>"
    python3 crew_oneway.py payload          (a PreToolUse JSON payload on stdin)
    python3 crew_oneway.py shapes

The revision-3 plan's one-way list (4.3) names operations only the owner may
approve. This module recognises three of them in the text of a command a
model runs, or in a file tool's payload, and nothing else:

- `hand-edit-terraform-state`: `terraform`, `tofu` or `terragrunt` running
  `state <write>` (anything but `list`, `show`, `pull`, `identities`),
  `import`, `taint`, `untaint`, `force-unlock` or `refresh` (R-34a); and any
  command or file tool that writes a terraform state file directly (R-34b).

A *state word* is a word whose basename (quotes, brackets and trailing
slashes stripped) ends in `.tfstate` or `.tfstate.<anything>`, any case:
`terraform.tfstate.backup` and the workspace directory `terraform.tfstate.d`
count. The word is also read with its quote characters taken out
(`terra"form.tf"state`) and with its escapes taken out too
(`terraform.tfstat\\e`); any reading counts. In `-x=v` the value `v` is
read, and the word is an *option value*; after the command's first `--` the
whole word is read (`-name.tfstate.bak=notes.txt` is a state word there).
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

- `delete-others-branch` (R-34c): `git branch` with `-d`/`-D`/`--delete`
  (not `-r`/`--remotes`), `git push` with `--delete`/`-d` anywhere after
  `push` or a `:ref` / `+:ref` refspec, `git push --prune|--mirror`
  (`push-prune`, could-not-tell), and `git update-ref -d refs/heads/<name>`;
- `delete-others-worktree` (R-34c): `git worktree remove <path>`.

"Others" is read from the caller's context, `{cwd, own_branches,
own_worktrees}`; the module probes nothing. A target not in `own_branches`
is a hit wherever the command runs; an own name is clear only when the
command's directory (`cwd`, then each `-C`) is inside an own worktree, else
could-not-tell. A worktree path is resolved against that directory and is
clear only when it equals an own worktree. No own list, no `cwd` where one
is needed, an expanded or globbed target, an option (or the worktree
subcommand) the raw pass left holding a quote, or a repository crew cannot
see (`--git-dir`, `--work-tree`, `--namespace`, a `-C` holding `$` ` % * ?
[ or a leading `~`, a leading `GIT_DIR=`/`GIT_WORK_TREE=`/`GIT_NAMESPACE=`)
is could-not-tell, never clear. A `git branch` operand is a branch name as
spelled (`refs/heads/x` is not `x` there); push and update-ref read refs. A
value-taking `git branch` option takes the next word (`--sort -r` is no
`--remotes`). A `git` whose subcommand crew cannot read is
could-not-tell with no operation (`git-sub-unseen`); a delete subcommand
running past `GIT_WINDOW` words with no hit is could-not-tell
(`git-window-exceeded`). Paths are compared lexically (`normpath`,
`normcase`), never on the filesystem. Later tickets add wrappers and gh
(R-34d, R-34e); the entry points and the result shape are already final.

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
   that starts an unquoted word: `terraform state rm x # -help` is a hit.
   Before any of this, while every character so far is on an allow-list
   (ASCII letters, digits, space, tab, newline, `-_./:=,;&|`), a `#` at the
   start or after a space, tab or newline comments out the rest of its line,
   so `echo ok # x; terraform state rm x` is clear (F2). Past the first other
   character a comment stops only its own segment, an over-report (a hit)
   such as `echo "$(date)" # x; terraform state rm x`. An operator
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
judging it takes time linear in its length; a git head reads only a window
of the words after it, grown while its global options fill it.

It is a tripwire, not a boundary (plan 4.0, layer 1). It does not see
terraform behind `bash -c`, `make`, a script, `xargs`, `sudo -u <user>` or a
substitution, terragrunt's `stack run` and `graph`, a state file written by
a script or a substitution or under an unexpanded name (`rm $F`), a copy into a directory
(`cp terraform.tfstate backup/`), or a state word only in git's globals.
Nor does it see a branch or worktree delete behind `xargs`, `sudo -u`,
`env -C`, an earlier `cd` or `export GIT_DIR=` (R-34d), `gh` (R-34e),
`git update-ref --stdin`, or `rm -rf` of a worktree directory.

Exit codes: 0 for every judgement (report-only) and for `shapes`, 2 for a
usage error.
"""
import argparse
import bisect
import collections
import json
import os
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
BRANCH = "delete-others-branch"
WORKTREE = "delete-others-worktree"
OPERATIONS_EMITTED = (TF_STATE, BRANCH, WORKTREE)

# The operation each R-34c rule names (C2); every other rule names TF_STATE.
# A rule shared by both deletes is carried as a (rule, operation) pair.
RULE_OPERATION = {
    "branch-delete-other": BRANCH, "branch-own-outside": BRANCH,
    "branch-owner-unseen": BRANCH, "branch-target-unseen": BRANCH, "push-prune": BRANCH,
    "worktree-remove-other": WORKTREE, "worktree-owner-unseen": WORKTREE,
    "worktree-target-unseen": WORKTREE,
    "git-sub-unseen": None,
}

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

# (shape, rule, verdict) of the terraform rows; `SHAPES` adds each row's operation.
_TF_SHAPES = (
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

# (shape, rule, verdict, operation) for `shapes`.
SHAPES = tuple(row + (TF_STATE,) for row in _TF_SHAPES) + (
    ("git branch -d/-D/--delete, push --delete/-d or :ref, update-ref -d refs/heads/x: "
     "a target not in own_branches", "branch-delete-other", HIT, BRANCH),
    ("the same, an own branch outside every own worktree", "branch-own-outside",
     COULD_NOT_TELL, BRANCH),
    ("the same, no own_branches in the context", "branch-owner-unseen", COULD_NOT_TELL, BRANCH),
    ("the same, a target holding $ ` % * ? [ or none, or an option left holding a quote",
     "branch-target-unseen", COULD_NOT_TELL, BRANCH),
    ("git push --prune or --mirror", "push-prune", COULD_NOT_TELL, BRANCH),
    ("git worktree remove, a path that is not an own worktree", "worktree-remove-other", HIT,
     WORKTREE),
    ("the same, no cwd or no own_worktrees in the context", "worktree-owner-unseen",
     COULD_NOT_TELL, WORKTREE),
    ("the same, a path holding $ ` % * ? [, a leading ~, or none, or a subcommand or option "
     "left holding a quote", "worktree-target-unseen", COULD_NOT_TELL, WORKTREE),
    ("a branch delete in a repository crew cannot see", "git-repo-unseen", COULD_NOT_TELL,
     BRANCH),
    ("a worktree remove in a repository crew cannot see", "git-repo-unseen", COULD_NOT_TELL,
     WORKTREE),
    ("git branch|push|update-ref past the word window, no hit", "git-window-exceeded",
     COULD_NOT_TELL, BRANCH),
    ("git worktree past the word window, no hit", "git-window-exceeded", COULD_NOT_TELL,
     WORKTREE),
    ("git with a subcommand crew cannot read", "git-sub-unseen", COULD_NOT_TELL, None),
)

# --- the head --------------------------------------------------------------------------------

# A superset of the R-33 tripwire's list (pinned by the test), plus the
# compound-command words a raw segment can start with, and the shell builtin
# `exec`, which runs the command after it in place of the shell (R-34c).
HEAD_PREFIXES = frozenset(("env", "sudo", "command", "time", "then", "do", "else", "!",
                           "if", "elif", "while", "until", "exec"))
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


# F2: the characters a command may hold before a `#` for that `#` to end its
# line. An allow-list, not a deny-list: no quote, escape, `$`, bracket,
# operator character or unusual whitespace, so the reader and either shell
# cannot disagree about whether the `#` is quoted or starts a word.
_COMMENT_SAFE = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                          " \t\n-_./:=,;&|")
_COMMENT_START = " \t\n"
_LINE_END_RE = re.compile(r"[\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")


def _drop_comments(text):
    """`text` with each line comment taken out while every character before
    it is in `_COMMENT_SAFE` (F2): a `#` at the start of the text or after a
    space, tab or newline runs to the line's end, so in `echo ok # x; T` the
    `T` is comment too. The first character outside the set stops this, and
    the rest is read as before (a comment stops only its own segment). A
    comment ends at the first character any reader may take as a line end,
    so less is dropped, never more."""
    out, start, index = [], 0, 0
    while index < len(text):
        char = text[index]
        if char == "#" and (index == 0 or text[index - 1] in _COMMENT_START):
            end = _LINE_END_RE.search(text, index)
            end = end.start() if end else len(text)
            out.append(text[start:index])
            start = index = end
            continue
        if char not in _COMMENT_SAFE:
            break
        index += 1
    out.append(text[start:])
    return "".join(out)


def raw_segments(text, shell="bash"):
    """The raw pass's segments of `text`, redirections lifted: a list of
    {words, targets: [(operator, target)], dangling: [operator]}."""
    segments = []
    text = _drop_comments(text)
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
    how many `--`, stand at `i` or later. `memo` holds each start judged;
    `ctx` is the caller's context (`_Context`)."""

    def __init__(self, words, ctx=None):
        count = len(words)
        self.words = words
        self.ctx = ctx if ctx is not None else NO_CONTEXT
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
            self._state = _StateWords(self.words, self.ctx)
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


def _judge_words(words, start=0, ctx=None):
    """(verdict, rule, word index) of the command that starts at `start`,
    `ctx` the caller's context (`_Context`, R-34c).

    Head precedence first: a command whose head is not terraform's is clear
    before anything after it is read. An `exec` unwrap judges the command
    after it from a later index, so each such index is judged first, latest
    first, and remembered: a chain of any length (`terragrunt exec -- `
    repeated) then needs no deep recursion. The words are read once
    (`_Scan`), so a long command costs time linear in its length."""
    if _tf_head(words, start) is None:
        return _state_head(_StateWords(words, ctx), start)
    scan = _Scan(words, ctx)
    starts = {scan.end[at + 1] for at in range(start, len(words)) if words[at] == "exec"}
    for later in sorted(starts, reverse=True):
        if later > start:
            scan.memo[later] = _judge_from(scan, later)
    return _judge_from(scan, start)


def _prefix_ends(words):
    """`ends[i]`: the first index at or after `i` that is not a head prefix
    or a `NAME=VALUE` word, so every start strips its prefixes in constant
    time (`exec exec ... git`, an `exec` start at each word, stays linear)."""
    ends = list(range(len(words) + 1))
    for i in range(len(words) - 1, -1, -1):
        if words[i] in HEAD_PREFIXES or _ASSIGN_RE.match(words[i]):
            ends[i] = ends[i + 1]
    return ends


def _head(words, start, ends=None):
    """(index, head) of the command at `start`, prefixes stripped, or None.
    `ends` is `_prefix_ends(words)` when the caller holds it."""
    index = start if ends is None else ends[start]
    while index < len(words) and (words[index] in HEAD_PREFIXES or _ASSIGN_RE.match(words[index])):
        index += 1
    if index >= len(words):
        return None
    return index, _head_name(words[index])


def _tf_head(words, start, ends=None):
    """(index, head) of the terraform head of the command at `start`, or None."""
    found = _head(words, start, ends)
    return found if found is not None and found[1] in TF_HEADS else None


def _judge_from(scan, start):
    if start not in scan.memo:
        found = _tf_head(scan.words, start, scan.state_words().prefix_end)
        scan.memo[start] = (_state_head(scan.state_words(), start) if found is None
                            else _judge_tf(scan, found[1], found[0] + 1))
    return scan.memo[start]


# --- state-file writes under any other head (R-34b) ------------------------------------------

def _readings(text):
    """`text` as written, with its quote characters taken out (the shell
    joins `terra"form.tf"state`), and with that and each escape (`\\` or a
    backtick) taken out too (bash writes `terraform.tfstat\\e` as
    `terraform.tfstate`). Any reading that names a state file counts: the
    shell is not known here, so the reader errs toward the state file."""
    joined = text.replace('"', "").replace("'", "")
    return (text, joined, re.sub(r"[\\`](.)", r"\1", joined, flags=re.S))


def _state_base(text):
    base = text.strip(_STRIP).rstrip("/\\")
    return bool(_STATE_RE.search(re.split(r"[\\/]", base)[-1]))


def _state_path(text):
    """Whether `text` names a terraform state file: in any of its
    `_readings`, its basename, quotes, brackets and trailing slashes
    stripped, ends in `.tfstate` or `.tfstate.<anything>` (the backup, the
    workspace directory), any case."""
    return any(_state_base(reading) for reading in _readings(text))


def _state_kind(word):
    """"word" when `word` is a state word, "option" when it is one only as
    an option (`-x=<state>`, or a word that starts with `-`), else None.
    After the command's first `--` the whole word is read instead
    (`_StateWords.whole`)."""
    if word.startswith("-") and "=" in word:
        return "option" if _state_path(word.partition("=")[2]) else None
    if not _state_path(word):
        return None
    return "option" if word.startswith("-") else "word"


class _StateWords:  # pylint: disable=too-few-public-methods
    """One command's words read once for state words, so every start judged
    in it costs constant time past the head (`_Scan`'s linear rule).

    `kind[i]` is `_state_kind`; `whole[i]` whether the whole word, read as
    a positional, names a state file; `next_state[i]` / `next_word[i]` /
    `next_whole[i]` are the first index at or after `i` holding a state
    word of any kind / a positional one / a whole-word one (`len(words)`
    when none); `next_plain[i]` the first word there not starting with
    `-`; `next_dashdash[i]` the first `--`; `next_inplace[i]` the first
    in-place option; `last_plain` the last word not starting with `-` (-1
    when none).

    These read each word alone. Every word after the command's first `--`
    is a positional (B5), whatever it starts with, so it is read whole:
    `-name.tfstate.bak=notes.txt` there is a state word, not an option
    value. That `--` depends on where the command starts, so the methods
    below take the head."""

    def __init__(self, words, ctx=None):
        count = len(words)
        self.words = words
        self.ctx = ctx if ctx is not None else NO_CONTEXT
        self.prefix_end = _prefix_ends(words)
        # the first index at or after `i` assigning GIT_DIR, GIT_WORK_TREE
        # or GIT_NAMESPACE (C5), so a start reads its assignments at once.
        self.repo_assign = [count] * (count + 1)
        for i in range(count - 1, -1, -1):
            sets_repo = (_ASSIGN_RE.match(words[i]) is not None
                         and words[i].split("=", 1)[0] in _REPO_VARS)
            self.repo_assign[i] = i if sets_repo else self.repo_assign[i + 1]
        self.kind =[_state_kind(word) for word in words]
        self.whole = [_state_path(word) for word in words]
        self.next_state = [count] * (count + 1)
        self.next_whole = [count] * (count + 1)
        self.next_word = [count] * (count + 1)
        self.next_plain = [count] * (count + 1)
        self.next_dashdash = [count] * (count + 1)
        self.next_inplace = [count] * (count + 1)
        self.last_plain = -1
        for i in range(count - 1, -1, -1):
            word, kind = words[i], self.kind[i]
            plain = not word.startswith("-")
            self.next_state[i] = i if kind else self.next_state[i + 1]
            self.next_whole[i] = i if self.whole[i] else self.next_whole[i + 1]
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
        return (self.next_word[after] < len(self.words)
                or self.first_after_dashdash(after) < len(self.words))

    def first_after_dashdash(self, after):
        """The first whole-word state word after the first `--` at or after
        `after` (`len(words)` when none)."""
        count = len(self.words)
        return self.next_whole[min(self.next_dashdash[after] + 1, count)]

    def first_state(self, after):
        """The first state word at or after `after`, read as an option
        before the first `--` and whole after it (`len(words)` when none)."""
        return min(self.next_state[after], self.first_after_dashdash(after))

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
    if last is not None and (info.kind[last] or (
            info.whole[last] and info.next_dashdash[head + 1] < last)):
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
            return (HIT, "tfstate-remote", info.first_state(head + 1))
        if sub == "cp":
            return _destination(info, head, "tfstate-remote")
    if name == "gsutil" and first == "rm":
        return (HIT, "tfstate-remote", info.first_state(head + 1))
    if name == "gsutil" and first == "cp":
        return _destination(info, head, "tfstate-remote")
    if name == "az" and first == "storage" and _positional(info, head + 1, 1) == "blob" and (
            _positional(info, head + 1, 2) in ("upload", "delete")):
        return (HIT, "tfstate-remote", info.first_state(head + 1))
    return None


def _git_args(info, head):
    """(args, index of the subcommand) of the git command whose head is at
    `head`. git's globals are a prefix, so a window of the words after the
    head is read, grown only while the globals fill it: each start costs
    the length of its globals, not of the rest of the command."""
    # pylint: disable=protected-access
    size = 8
    while True:
        args = info.words[head + 1:head + 1 + size]
        split = crew_gitallow._global_split(args)[1]
        if split < len(args) or head + 1 + size >= len(info.words):
            return args, split
        size *= 4


def _git_state(info, head):
    """git: only state words after the subcommand are read (git's globals
    are not, B6)."""
    args, split = _git_args(info, head)
    sub = crew_gitallow.subcommand(args)
    after = min(head + 1 + split + 1, len(info.words))
    git_first = info.first_state(after)
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


# --- branch and worktree deletes (R-34c) -----------------------------------------------------

# C1: the caller's context, read once in `judge`. None is "not given" (an
# unknown), never "empty"; an empty own list is a known empty list.
_Context = collections.namedtuple("_Context", ("cwd", "own_branches", "own_worktrees"))
NO_CONTEXT = _Context(None, None, None)
# C6: every path function is called through this one attribute, so the test
# can run each path row under `ntpath` and under `posixpath`.
_PATH = os.path

GIT_WINDOW = 256
DELETE_SUBS = {"branch": BRANCH, "push": BRANCH, "update-ref": BRANCH, "worktree": WORKTREE}
_REPO_VARS = frozenset(("GIT_DIR", "GIT_WORK_TREE", "GIT_NAMESPACE"))
_TARGET_UNSEEN = ("$", "`", "%", "*", "?", "[")
# C10: push options that take the next word when written without `=`. git
# also takes any unambiguous prefix of a long option (`--receiv`), so a
# prefix is read against git push's other long options too.
_PUSH_VALUE_OPTS = frozenset(("-o", "--push-option", "--receive-pack", "--exec", "--repo",
                              "--recurse-submodules"))
_PUSH_LONG_FLAGS = ("--all", "--branches", "--mirror", "--delete", "--tags", "--dry-run",
                    "--porcelain", "--force", "--force-with-lease", "--force-if-includes",
                    "--thin", "--set-upstream", "--progress", "--prune", "--verify",
                    "--follow-tags", "--signed", "--atomic", "--ipv4", "--ipv6", "--quiet",
                    "--verbose", "--no-")
# git branch options that take the next word when written without `=`
# (`--sort -r` sorts by `-r`, it is not `--remotes`), read the same way.
_BRANCH_VALUE_OPTS = frozenset(("-u", "--set-upstream-to", "--sort", "--format", "--points-at",
                                "--contains", "--no-contains", "--merged", "--no-merged"))
_BRANCH_LONG_FLAGS = ("--delete", "--create-reflog", "--force", "--move", "--copy", "--color",
                      "--verbose", "--quiet", "--abbrev", "--track", "--unset-upstream",
                      "--edit-description", "--list", "--show-current", "--remotes", "--all",
                      "--ignore-case", "--omit-empty", "--column", "--recurse-submodules",
                      "--no-")
# Quotes the raw pass leaves inside a word (`re"move"`, `--del"ete"`): the
# shell reads such a word differently from its spelling.
_QUOTE_MARKS = ('"', "'")


def _own_list(value):
    """A tuple of the own names or paths, or None when `value` is not a
    list of strings (absent, C1)."""
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return None


def _read_context(context):
    """`context` as a `_Context` (C1): anything malformed counts as absent."""
    if not isinstance(context, dict):
        return NO_CONTEXT
    cwd = context.get("cwd")
    return _Context(cwd if isinstance(cwd, str) and cwd else None,
                    _own_list(context.get("own_branches")),
                    _own_list(context.get("own_worktrees")))


def _norm(path):
    return _PATH.normcase(_PATH.normpath(path))


def _inside(eff, own_worktrees):
    """C7: whether `eff` is an own worktree or below one, by whole path
    components. An unknown `eff` or no own list is never inside."""
    if eff is None or not own_worktrees:
        return False
    here = _norm(eff)
    for entry in own_worktrees:
        entry = _norm(entry)
        if here == entry or here.startswith(entry.rstrip(_PATH.sep) + _PATH.sep):
            return True
    return False


def _short(word, stop):
    """A single-dash bundle read only up to its first value-taking letter
    `stop` (C9): `-ostuffd` is `-` for push, `-uorigin/dev` is `-` for
    branch. Any other word comes back whole."""
    if not word.startswith("-") or word.startswith("--") or stop not in word[1:]:
        return word
    return word[:1 + word[1:].index(stop)]


def _repo_unseen(globals_, dirs, assigned):
    """C5: whether crew cannot tell which repository git acts on;
    `assigned` is whether the segment's leading words set a `_REPO_VARS`."""
    if dirs is crew_gitallow.UNSEEN or assigned:
        return True
    if any(word.split("=", 1)[0] == "--namespace" for word in globals_):
        return True
    return any(value.startswith("~") or any(mark in value for mark in _TARGET_UNSEEN)
               for value in dirs)


def _effective(cwd, dirs):
    """C6: the directory git runs in, `cwd` then each `-C`; None when no
    `cwd` is known."""
    if cwd is None:
        return None
    eff = cwd
    for value in dirs:
        eff = _PATH.normpath(_PATH.join(eff, value))
    return eff


def _positionals(rest):
    """The indexes in `rest` of words that are not options: every word after
    the first `--`, and before it each word not starting with `-`."""
    out, dashdash = [], False
    for index, word in enumerate(rest):
        if dashdash:
            out.append(index)
        elif word == "--":
            dashdash = True
        elif not word.startswith("-"):
            out.append(index)
    return out


def _options(rest):
    """The words of `rest` before its first `--` that start with `-`."""
    out = []
    for word in rest:
        if word == "--":
            break
        if word.startswith("-"):
            out.append(word)
    return out


def _git_takes_value(word, cut, letter, value_opts, long_flags):
    """Whether option `word` (`cut`: its bundle read up to the value-taking
    short `letter`) takes the next word: `-<letter>` last in its bundle
    (`-fo x`; `-ofoo` holds its own value), or a long value option or an
    unambiguous prefix of one."""
    if cut != word:
        return cut + letter == word
    if word in value_opts:
        return True
    if not word.startswith("--") or "=" in word or len(word) < 3:
        return False
    if any(flag.startswith(word) for flag in long_flags):
        return False
    return any(opt.startswith(word) for opt in value_opts)


def _push_takes_value(word, cut):
    """git push (C10): `-o` and `_PUSH_VALUE_OPTS` take the next word."""
    return _git_takes_value(word, cut, "o", _PUSH_VALUE_OPTS, _PUSH_LONG_FLAGS)


def _branch_remotes(rest):
    """git branch: whether `-r`/`--remotes` stands before `--` as an option,
    not as the value of the option before it (`--sort -r`)."""
    # pylint: disable=protected-access
    hit = crew_gitallow._option_hit
    taken = False
    for word in rest:
        if word == "--":
            break
        if taken or not word.startswith("-"):
            taken = False
            continue
        cut = _short(word, "u")
        if hit(cut, "-r") or hit(cut, "--remotes"):
            return True
        taken = _git_takes_value(word, cut, "u", _BRANCH_VALUE_OPTS, _BRANCH_LONG_FLAGS)
    return False


def _branch_targets(rest):
    """git branch: the delete targets as (index, name), or None when this is
    not a branch delete (no delete option, or `-r`/`--remotes`). A delete
    option is read in every option-shaped word, an option's value too, and a
    value is still read as a target: both can only over-report."""
    # pylint: disable=protected-access
    hit = crew_gitallow._option_hit
    options = _options(rest)
    cut = [_short(word, "u") for word in options]
    if not any(hit(word, "-d") or hit(word, "-D") or hit(word, "--delete") for word in cut):
        return None
    if _branch_remotes(rest):
        return None
    return [(index, rest[index]) for index in _positionals(rest)]


def _push_targets(rest):
    """git push (C10): (targets as (index, refspec target), deleting, pruning).
    `deleting` is whether `--delete`/`-d` stands anywhere after `push`."""
    # pylint: disable=protected-access
    hit = crew_gitallow._option_hit
    positional, deleting, pruning, dashdash, index = [], False, False, False, 0
    while index < len(rest):
        word = rest[index]
        if dashdash or not word.startswith("-"):
            positional.append(index)
        elif word == "--":
            dashdash = True
        else:
            cut = _short(word, "o")
            deleting = deleting or hit(cut, "-d") or hit(cut, "--delete")
            pruning = pruning or hit(word, "--prune") or hit(word, "--mirror")
            if _push_takes_value(word, cut):
                index += 1  # its value is the next word
        index += 1
    targets = []
    for at in positional[1:]:  # the first positional is the remote
        spec = rest[at]
        if deleting:
            targets.append((at, spec.lstrip("+").rpartition(":")[2]))
        elif spec.startswith((":", "+:")):
            targets.append((at, spec.partition(":")[2]))
    return targets, deleting, pruning


def _update_ref_target(rest):
    """git update-ref (C11): (deleting, (index, ref) or None). git reads its
    options anywhere before `--`, so `update-ref refs/heads/x -d` deletes;
    `-m` takes the next word as its reason."""
    # pylint: disable=protected-access
    deleting, ref, dashdash, index = False, None, False, 0
    while index < len(rest):
        word = rest[index]
        if dashdash or not word.startswith("-"):
            ref = ref if ref is not None else (index, word)
        elif word == "--":
            dashdash = True
        else:
            cut = _short(word, "m")
            deleting = deleting or crew_gitallow._option_hit(cut, "-d")
            if cut != word and cut + "m" == word:
                index += 1  # `-m` last in its bundle: the reason is the next word
        index += 1
    return deleting, ref


def _branch_verdict(name, ctx, offset, own_inside):
    """C8: one branch target (`refs/heads/` stripped already)."""
    if any(mark in name for mark in _TARGET_UNSEEN):
        return (COULD_NOT_TELL, "branch-target-unseen", offset)
    if ctx.own_branches is None:
        return (COULD_NOT_TELL, "branch-owner-unseen", offset)
    if name not in ctx.own_branches:
        return (HIT, "branch-delete-other", offset)
    if own_inside:
        return _CLEAR
    return (COULD_NOT_TELL, "branch-own-outside", offset)


def _branch_delete(targets, where, eff, ctx, repo_unseen, refs=True):
    """C8 over every target of a branch delete; `targets` None is no delete,
    [] a delete with no readable target. Any hit wins. `refs` is whether a
    target is a ref (push, update-ref: `refs/tags/` skipped, `refs/heads/`
    stripped); a `git branch` operand is a branch name, spelled as it stands."""
    if targets is None:
        return _CLEAR
    if repo_unseen:
        return (COULD_NOT_TELL, ("git-repo-unseen", BRANCH), where)
    named = []
    for index, target in targets:
        if not refs:
            named.append((where + index, target))
            continue
        if target.startswith("refs/tags/"):
            continue
        name = target[len("refs/heads/"):] if target.startswith("refs/heads/") else target
        named.append((where + index, name))
    if not targets:
        named = [(where, None)]
    if not named:
        return _CLEAR
    readings = []
    own_inside = _inside(eff, ctx.own_worktrees)
    for offset, name in named:
        if not name:
            reading = (COULD_NOT_TELL, "branch-target-unseen", offset)
        else:
            reading = _branch_verdict(name, ctx, offset, own_inside)
        if reading[0] == HIT or ctx.own_branches is None:
            return reading  # with no own list no target can be a hit
        readings.append(reading)
    return _first_worst(readings)


def _worktree_remove(rest, where, eff, ctx, repo_unseen):
    """C12: `git worktree remove [-f|--force]... <path>`."""
    if not rest:
        return _CLEAR
    if _unseen(rest[0]):
        return (COULD_NOT_TELL, "worktree-target-unseen", where)
    if rest[0] != "remove":
        return _CLEAR
    if repo_unseen:
        return (COULD_NOT_TELL, ("git-repo-unseen", WORKTREE), where)
    found = _positionals(rest[1:])
    if not found:
        return (COULD_NOT_TELL, "worktree-target-unseen", where)
    at = where + 1 + found[0]
    path = rest[1 + found[0]]
    if not path or any(mark in path for mark in _TARGET_UNSEEN) or path.startswith("~"):
        return (COULD_NOT_TELL, "worktree-target-unseen", at)
    if eff is None or ctx.own_worktrees is None:
        return (COULD_NOT_TELL, "worktree-owner-unseen", at)
    removed = _norm(_PATH.join(eff, path))
    if any(removed == _norm(entry) for entry in ctx.own_worktrees):
        return _CLEAR
    return (HIT, "worktree-remove-other", at)


def _git_delete(info, start, head):
    """(verdict, rule, word index) of the branch and worktree deletes of the
    git command whose head is at `head` (C4-C14); `start` is where its
    segment's leading assignments begin."""
    args, split = _git_args(info, head)
    if split >= len(args):
        return _CLEAR  # nothing after git's globals (`git --version`)
    sub = crew_gitallow.subcommand(args)
    sub_at = head + 1 + split
    if sub is crew_gitallow.UNSEEN:
        return (COULD_NOT_TELL, "git-sub-unseen", sub_at)
    if sub not in DELETE_SUBS:
        return _CLEAR
    ctx = info.ctx
    globals_ = args[:split]
    dirs = crew_gitallow.target_dirs(globals_)
    repo_unseen = _repo_unseen(globals_, dirs, info.repo_assign[start] < head)
    eff = None if repo_unseen else _effective(ctx.cwd, dirs)
    where = sub_at + 1
    rest = info.words[where:where + GIT_WINDOW]
    if sub == "worktree":
        reading = _worktree_remove(rest, where, eff, ctx, repo_unseen)
    elif sub == "branch":
        reading = _branch_delete(_branch_targets(rest), where, eff, ctx, repo_unseen,
                                 refs=False)
    elif sub == "push":
        targets, deleting, pruning = _push_targets(rest)
        reading = _branch_delete(targets if deleting or targets else None, where, eff, ctx,
                                 repo_unseen)
        if pruning and repo_unseen:
            reading = (COULD_NOT_TELL, ("git-repo-unseen", BRANCH), where)
        elif pruning:
            reading = _first_worst([reading, (COULD_NOT_TELL, "push-prune", sub_at)])
    else:
        deleting, ref = _update_ref_target(rest)
        if not deleting:
            reading = _CLEAR
        elif repo_unseen:
            reading = (COULD_NOT_TELL, ("git-repo-unseen", BRANCH), where)
        elif ref is None or _unseen(ref[1]):
            reading = (COULD_NOT_TELL, "branch-target-unseen", where)
        elif ref[1].startswith("refs/heads/"):
            reading = _branch_delete([ref], where, eff, ctx, repo_unseen)
        else:
            reading = _CLEAR
    if reading[0] != HIT and len(info.words) > where + GIT_WINDOW:
        return (COULD_NOT_TELL, ("git-window-exceeded", DELETE_SUBS[sub]), sub_at)
    if reading[0] != HIT and _quoted_option(rest, sub == "worktree"):
        rule = "worktree-target-unseen" if sub == "worktree" else "branch-target-unseen"
        return (COULD_NOT_TELL, rule, where)
    return reading


def _quoted_option(rest, worktree):
    """Whether an option word of `rest`, or the worktree subcommand, still
    holds a quote (the raw pass keeps one inside a word: `--del"ete"`,
    `re"move"`), so its meaning cannot be read from its spelling."""
    words = [word for word in rest if word.startswith("-")] + rest[:1 if worktree else 0]
    return any(mark in word for word in words for mark in _QUOTE_MARKS)


def _git(info, start, head):
    """C3: the delete reading first, then the R-34b state reading, the first
    worst kept. A subcommand crew cannot read is `git-sub-unseen` with no
    operation (C13), even beside a state word."""
    deleted, stated = _git_delete(info, start, head), _git_state(info, head)
    return _first_worst([deleted, stated])


def _state_head(info, start):
    """(verdict, rule, word index) of a command at `start` whose head is not
    terraform's: clear unless a state word stands after the head."""
    found = _head(info.words, start, info.prefix_end)
    if found is None:
        return _CLEAR
    index, head = found
    if head == "git":
        return _git(info, start, index)
    first = info.first_state(index + 1)
    if first >= len(info.words):
        return _CLEAR
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


def _write_reading(operator, target, held):
    """A lifted redirection: a write when its operator holds `>` (fd copies
    are already dropped). The state-word test runs before the expansion
    test, so `> "$D/terraform.tfstate"` is a hit (B3). The target is read
    in each of its `_readings` (quotes joined, escapes taken out)."""
    if ">" not in operator:
        return _CLEAR
    if _state_path(target):
        return (HIT, "tfstate-redirect", None)
    if held and _unseen(target):
        return (COULD_NOT_TELL, "tfstate-redirect-unseen", None)
    return _CLEAR


# --- the two passes --------------------------------------------------------------------------

def _finding(verdict, rule, operation, **where):
    out = {"verdict": verdict, "rule": rule, "operation": operation}
    out.update(where)
    return out


def _named(rule):
    """(rule, operation) of a reading's rule (C2): a pair as it stands, else
    the operation `RULE_OPERATION` names, `TF_STATE` when it names none."""
    if isinstance(rule, tuple):
        return rule
    return rule, RULE_OPERATION.get(rule, TF_STATE)


def _judged(words, out, where, ctx):
    verdict, rule, word = _judge_words(words, 0, ctx)
    if verdict != CLEAR:
        rule, operation = _named(rule)
        out.append(_finding(verdict, rule, operation, word=word, **where))


def _plain_pass(commands, ctx):
    out = []
    for number, words in enumerate(commands):
        _judged(words, out, {"pass": "plain", "command": number}, ctx)
    return out


def _raw_pass(text, shell, ctx=NO_CONTEXT):
    """One finding per segment (A14): the head's reading and each write
    target's (B3) are combined, the first worst kept. A dangling operator
    makes the segment could-not-tell unless that reading is a hit, which
    wins (A7)."""
    out = []
    for number, segment in enumerate(raw_segments(text, shell)):
        where = {"pass": "raw", "command": number}
        readings = [_judge_words(segment["words"], 0, ctx)]
        # A lifted target is part of the segment too (B3): in
        # `cat < terraform.tfstate > $OUT` the state word is the input's.
        held = any(_state_kind(word) for word in segment["words"]) or any(
            _state_path(target) for _op, target in segment["targets"])
        readings += [_write_reading(op, target, held) for op, target in segment["targets"]]
        verdict, rule, word = _first_worst(readings)
        if segment["dangling"] and verdict != HIT:
            verdict, rule, word = COULD_NOT_TELL, "redirect-target-unseen", None
        if verdict != CLEAR:
            rule, operation = _named(rule)
            out.append(_finding(verdict, rule, operation, word=word, **where))
    return out


def _findings(command, shell, ctx=NO_CONTEXT):
    commands = crew_gitallow.plain_commands(command, shell)
    if commands is None:
        return _raw_pass(command, shell, ctx)
    return _plain_pass(commands, ctx)


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
    """Judge one command text as `shell` (`bash` or `powershell`).
    `context` is `{cwd, own_branches, own_worktrees}` (R-34c), read once
    (`_read_context`); a missing or malformed part is unknown, so a branch
    or worktree delete it would decide is could-not-tell. No terraform row
    depends on it. Returns {verdict, report_only, operations, findings}."""
    ctx = _read_context(context)
    if not isinstance(command, str) or shell not in ("bash", "powershell"):
        return _result([_finding(COULD_NOT_TELL, "unreadable-input", None,
                                 **{"pass": None, "command": None, "word": None})])
    return _result(_findings(command, shell, ctx))


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
    one.add_argument("--cwd")
    one.add_argument("--own-branch", action="append", dest="own_branches")
    one.add_argument("--own-worktree", action="append", dest="own_worktrees")
    one.add_argument("command", nargs="+")
    sub.add_parser("payload")
    sub.add_parser("shapes")
    args = parser.parse_args(argv)
    if args.action == "judge":
        context = {key: getattr(args, key) for key in ("cwd", "own_branches", "own_worktrees")
                   if getattr(args, key) is not None}
        print(json.dumps(judge(" ".join(args.command), args.shell, context or None), indent=2))
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
        for shape, rule, verdict, operation in SHAPES:
            print(f"{shape}\t{rule}\t{verdict}\t{operation or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
