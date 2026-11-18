"""PreToolUse plan-approval + scope guard on Write/Edit/MultiEdit/NotebookEdit,
and the approval-forgery check on Bash/PowerShell.

crew 1.0, lane T3 (docs/review/04-redesign.md, Hooks table). The decision
lives here; `scope-guard.sh` and `scope-guard.ps1` only find a python and pipe
the payload in, so the two shells cannot disagree.

## What it decides, in order

1. `scope.mode` resolves to `off` (the default, and what a repo that never set
   the key gets), or the cwd is no work tree -> exit 0 before anything else is
   read, EXCEPT that a Write/Edit of, or a shell write to, the owner's own
   files (the machine config `~/.claude/crew/config.json` and the
   confirm-config store beside it) is still refused (crew 1.3.137): those hold
   `guards.enabled` and its receipts, and a guard that stood down with
   `scope.mode` would let an agent write both.
2. A target under `<git-common-dir>/crew/` -- approval receipts, the review
   ledger, the active-ticket pointer, the ramp count -- or crew bookkeeping
   that is not write-allowed (`crew_ticket.is_crew_write_refused`: the scope
   base `.crew/.scope-base`, the verify gate's record, marker, fingerprint,
   timings and lock, `metrics.jsonl`) is REFUSED in every mode but `off`,
   whether or not a ticket is active, whatever Touch says. Those files are
   what the guard, the Stop audit and the review gate trust, and the
   bookkeeping ones are left out of the review bundle and the audit (T-0068),
   so a write to them would be both a forgery and invisible; an Edit that
   could write them could approve its own plan or green its own gate.
3. A BROKEN active-ticket pointer (`crew_ticket.resolve_active`: it names a
   ticket with no directory, is not an id, or does not parse) is refused
   under `block` -- never read as "no active ticket".
4. No active ticket -> allowed: the guard enforces a ticket's contract and
   there is no contract to enforce.
5. Otherwise every target must be the ticket's own `.work/tickets/<id>/` files
   (always writable, so the spec and plan can be amended), or -- with an
   approval that is current AND came from the user's prompt
   (`crew_ticket.accepted`; a `cli` receipt only with
   `scope.allowCliApproval: true`) -- inside `spec.Touch`. The approval and
   the Touch it is judged against come from ONE read of spec.md
   (`crew_ticket.status`).
5b. The repo handoff note (`.work/HANDOFF.md`, `.work/HANDOFF-*.md`) is
   always writable, approval or not: session metadata, not ticket scope
   (`crew_ticket.is_handoff_path`). Real and named path must both match.
6. With that SAME approval -- current, from the user's prompt, a `cli`
   receipt only under `scope.allowCliApproval` -- the refresh-artifact paths
   are writable too: `crew_refresh_check.REFRESH_ARTIFACT_PATHS`, the code
   map (`.crew/codemap/`), the configured diagrams dir, `graph.out` and
   `.claude/rules/`. Why: `/crew:implement` step 6 runs `/crew:onboard
   --refresh`, `/crew:diagram` and graphify for every ticket whose changes
   reach them, and `/crew:done` refuses until they are current, yet no
   ticket's Touch names them -- without this, the refresh the lifecycle
   demands is the write the guard refuses (T-0008, review round 1). The
   match is whole path segments on the normalised path (`.crew/codemapX` is
   not the code map, `..` is collapsed first), and BOTH the real and the
   named path must be artifacts, so a link inside `.crew/codemap/` cannot
   carry a write anywhere else. A configured dir resolving to the repository
   root opens nothing. Config is already this guard's trust root --
   `scope.mode` lives there -- so a configured dir is not a new way round it.
5a. `crew_ticket.CREW_WRITE_ALLOWED_PATHS` -- only `.crew/metrics.md`, the
   row `/crew:review` step 6 appends with Edit -- is writable with or without
   an approval (T-0068): it is crew writing for itself, never a scope
   change, and nothing reads it as policy. BOTH the real and the named path
   must be on the list, whole segments from the root, so a link cannot carry
   a write out of `.crew/`. Nothing crew reads as a trust input is on it:
   `.crew/tfplan/`, `.crew/incident.json` and `.crew/.deploy-in-flight` are
   judged against Touch like any file, and the gate's files are refused by
   rule 2, which runs first.
   Nothing else is exempt: not the rest of `.crew/` (`config.json`,
   `verify.json`, the code map outside rule 6), not `TODO.md`, not the rest
   of `.claude/`, not crew's policy files. Put them in Touch if the ticket is
   meant to change them.

## Bash and PowerShell

A shell command is not judged against Touch (the Stop audit does that, from
the tree). It is refused, in every mode but `off`, when its text invokes
`crew_ticket.py approve`, names the approval hook script, or names
`<git-common-dir>/crew/` alongside a redirect or a writing command. Each check
reads the text as written and with its line continuations joined (bash's
backslash-newline deleted, PowerShell's backtick-newline a space), so a
continuation cannot split an approval across the newline a check stops at; a
bare newline still separates commands.

`crew_autopilot.py approve` (T-0010) is the one approval a session may run,
and only as the whole command `python3 [-B] <path>/crew_autopilot.py approve
[--root .] --ticket <ID>` -- nothing chained, piped, substituted or quoted --
and only while `crew_autopilot.approval_policy` says yes for that ticket in
this worktree (which needs `scope.allowCliApproval: true`). Any other command
naming it is refused; a policy that cannot be told refuses too.

A SUBAGENT (the payload carries a non-empty `agent_type`; T-0029 -- a
`/crew:autopilot wave` lane is one) is refused, besides, the never-list:
`review_ledger.py --accept|--reject` -- and every abbreviation argparse would
once have expanded to them, `--a` up to `--accept` and `--rej` up to
`--reject` -- and `gh pr merge ... --admin`. Accepting or rejecting a review
and an admin merge are the owner's, from the main session; with no
`agent_type` (the main thread, the owner's path) nothing here changes.

That is a
textual check, not a shell parser: it stops drift and accidental bypass, and
a session that sets out to forge local state -- a variable holding the path,
an encoded command -- still can. README "Scope and approval" states the
threat model; the Stop audit and review are the backstop.

`block` refuses (exit 2, <= 6 lines on stderr). `report` allows, logs the row
to `.crew/guard.log` (never creating `.crew/`), and prints a `systemMessage`
so the note is visible. `auto` is `report` for the first ten tickets, then
`block` (crew_ticket.effective_mode).

## Paths

Each target is judged twice, and both must pass. The REAL path follows every
symlink and junction the way the OS will when it opens the file
(`role_write_guard._resolve_real_target`, reused rather than re-derived; case
is folded on Windows by `os.path.normcase` / fnmatch). The NAMED path --
normalised lexically, `..` collapsed -- is checked too whenever it lies inside
the worktree, so a link whose name is outside Touch cannot be used to write
into Touch any more than a link inside Touch can write out of it. A real path
outside the worktree is not a repository path and is allowed, unless it is in
the common git directory, which is never in scope.

Shell-made writes are not this hook's to see; the Stop-time
`completion_audit.py` diffs the whole tree for those.

## Failure

A payload that does not parse, whenever the EFFECTIVE mode is `block`
(`auto` past its ramp included), or one that names no path under `block`, is
refused -- an unclassifiable write is not evidence the write is in scope. An
exception this file did not anticipate fails closed when the configured mode
is `block` or `auto`, and open (with a note) under `report`.
"""
import fnmatch
import json
import os
import posixpath
import re
import sys
import time

import crew_ticket
import role_write_guard
import verify_trust

TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
SHELLS = ("Bash", "PowerShell")
GUARD_LOG = os.path.join(".crew", "guard.log")
SCOPE_BASE = ".crew/.scope-base"

# One simple command's worth of text: a separator ends the span, so
# `crew_ticket.py status ... && echo approve` is not an approval.
_APPROVE_RE = re.compile(r"crew_ticket(?:\.py)?\b[^\n;&|]*\bapprove\b", re.IGNORECASE)
# T-0010: any mention of autopilot's approve, and the one bare form allowed.
_AUTOPILOT_APPROVE_RE = re.compile(r"crew_autopilot(?:\.py)?\b[^\n;&|]*\bapprove\b",
                                   re.IGNORECASE)
_AUTOPILOT_BARE_RE = re.compile(
    r"[ \t]*python3?(?:[ \t]+-B)?[ \t]+[\w./\\:~${}-]*crew_autopilot\.py[ \t]+approve"
    r"(?:[ \t]+--root[ \t]+\.)?[ \t]+--ticket[ \t]+([A-Z][A-Z0-9]*-[0-9]+)[ \t]*")
# T-0029: the never-list, refused only when the payload shows a subagent.
# L-0717: `--grant-round` is the owner's one extra review round, so it joins
# `--accept` and `--reject` here with every abbreviation back to `--g`.
_ACCEPT_RE = re.compile(r"review_ledger(?:\.py)?\b[^\n;&|]*--(?:a(?:c(?:c(?:e(?:pt?)?)?)?)?"
                        r"|rej(?:e(?:ct?)?)?"
                        r"|g(?:r(?:a(?:n(?:t(?:-(?:r(?:o(?:u(?:nd?)?)?)?)?)?)?)?)?)?)(?![\w-])",
                        re.IGNORECASE)
_ADMIN_MERGE_RE = re.compile(r"\bgh\b[^\n;&|]*\bpr\b[^\n;&|]*\bmerge\b[^\n;&|]*--admin\b",
                             re.IGNORECASE)
LANE_REFUSAL = ("a lane may not accept, reject, grant a review round or admin-merge; that is "
                "the owner's, from the main session")
_HOOK_RE = re.compile(r"approval[_-]hook(?:\.py|\.sh|\.ps1)?\b", re.IGNORECASE)
# L-0888: the verify trust store grows only by a person at a terminal. Any
# command naming verify_trust with a verb that grows or shrinks it is refused;
# `status` and `check` (read-only, bar the allowlist pin) pass.
# A verb standing as a path segment or an option value (`--root /tmp/approve`,
# `--root=approve`) is an argument, not the verb: argparse reads a positional
# only as its own word, so a verb glued to `/`, `\\`, `.`, `=`, `:` or `~` is not one.
_TRUST_RE = re.compile(r"verify[_-]trust(?:\.py)?\b[^\n;&|]*(?<![/\\.=:~])\b(?:approve|allow-owner|"
                       r"disallow-owner|revoke)\b(?![/\\])", re.IGNORECASE)
# The same verbs reached through the module instead of the script: an import, `-m`
# or runpy beside any of the verbs (or the writer itself) anywhere in the text.
_TRUST_IMPORT_RE = re.compile(r"\b(?:import|from)\s+verify[_-]trust\b|-m\s+verify[_-]trust\b|"
                              r"\brunpy\b[^\n]*verify[_-]trust", re.IGNORECASE)
_TRUST_VERB_RE = re.compile(r"\b(?:approve|allow-owner|disallow-owner|revoke|update_store|"
                            r"cmd_approve|cmd_allow_owner|cmd_revoke)\b", re.IGNORECASE)
TRUST_STORE_NAME = "verify-trust.json"
# L-0888 (round 4, runtime-built verb): the literal-verb checks above cannot read
# a verb or a path that the command assembles as it runs. These refuse the
# assembly itself, beside the name: a variable or substitution where the verb
# stands, string pieces joined, a dynamic import, a call into the module's
# writers, the store override or a session-variable unset, and a store-named
# write. A tripwire, not a sandbox: the boundary is the OS user (README).
_TRUST_NAME_RE = re.compile(r"verify[_-]trust(?:\.py)?", re.IGNORECASE)
_TRUST_READ_VERB_RE = re.compile(r"\b(?:status|check)\b")
_DYNAMIC_RE = re.compile(r"[$`*?]")
_ASSEMBLY_RE = re.compile(r"[\"']\s*\+\s*[\"']|\.join\(|\bchr\(|__import__|\bimportlib\b|"
                          r"\bgetattr\(|\bexec\(|\beval\b|base64|fromhex|\\x[0-9a-f]{2}",
                          re.IGNORECASE)
_DYNAMIC_IMPORT_RE = re.compile(r"__import__|\bimportlib\b|\bexec\(|\beval\(|\bexecfile\(",
                                re.IGNORECASE)
_SCRIPTS_DIR_RE = re.compile(r"hooks[\\/]+scripts|\bsys\.path\b|verify_|trust", re.IGNORECASE)
_TRUST_WRITER_CALL_RE = re.compile(r"\bmain\s*\(|\bcmd_\w+|\bupdate_store\b|\b_Lock\b|"
                                   r"\bsys\.argv\b|\bparse_args\b|\bbuild_parser\b")
_STORE_OVERRIDE_RE = re.compile(r"\bCREW_VERIFY_TRUST_FILE\b")
_SESSION_VAR_RE = re.compile(r"\bCLAUDECODE\b")
_STORE_DIR_RE = re.compile(r"[\\/]crew[\\/]+verify-", re.IGNORECASE)
# A line continuation: bash's backslash-newline, which the shell deletes (so it
# can split a word), and PowerShell's backtick-newline, which reads as a space.
_BASH_CONTINUATION_RE = re.compile(r"\\\r?\n")
_PS_CONTINUATION_RE = re.compile(r"`\r?\n")
_DOTGIT_CREW_RE = re.compile(r"\.git[\\/]+crew\b|git-common-dir\b.*\bcrew\b",
                             re.IGNORECASE | re.DOTALL)
# The double-confirmation store (`crew_humanonly.store_dir`): a shell command naming `confirm-config/` that WRITES
# there is refused (#679's check, restored in round 8: the merge had kept only the check of the owner's real store).
# Since round 11 (crew 1.3.137) `_store_write` judges where the command writes, as the owner's files are judged; until
# then a write verb or a redirect anywhere in the command refused it, so `cp <receipt> /tmp/` was refused.
_CONFIRM_STORE_RE = re.compile(r"confirm-config[\\/]", re.IGNORECASE)
# A redirect (not into /dev/null, $null or another descriptor), or a word
# that writes files. Reading crew's state -- `cat`, `Get-Content` -- passes.
_WRITES_RE = re.compile(
    r"(?<!>)>>?(?!>)(?!\s*(?:&\d|/dev/null\b|\$null\b))|"
    r"\b(?:tee|cp|mv|rm|ln|touch|mkdir|rmdir|install|dd|rsync|truncate|sed|perl|"
    r"python[0-9.]*|py|node|chmod|echo|printf|set-content|add-content|out-file|"
    r"new-item|copy-item|move-item|remove-item|rename-item|clear-content|set-item|ni|"
    r"sc|ac)\b", re.IGNORECASE)
# Fail-closed exemption from the word list above. The list is a deny-list on
# purpose, so a command that merely NAMES `python3`/`echo` as an argument
# (`ls <state> | grep python3`) was refused. A command is read-only, and so
# exempt, ONLY when `_read_only` parses all of it and every simple command is
# one of these programs with plain literal words AND only options on that
# program's explicit allow-list (`_OPTION_RULES`, `_FIND_*`). Anything it cannot
# parse, any other program, or any option not on the list keeps the deny-list
# verdict. Shell builtins (`test`, `[`, `printf -v`, `declare`, `let`) are never
# listed: bash evaluates their arguments itself (`test -v 'a[$(cmd)]'` runs cmd).
_READ_ONLY_PROGRAMS = frozenset((
    "ls", "cat", "head", "tail", "wc", "stat", "grep", "egrep", "fgrep", "find"))
_PLAIN_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./:=,@%+-")
_REDIRECT_WORDS = frozenset(("2>/dev/null", "2>&1"))
_NUMBER_RE = re.compile(r"^[+-]?[0-9]+$")
_GREP_RULE = ("rRinlLcvwxFEHhsqoaI", "e", ("--color=never",),
              ("--include", "--exclude", "--exclude-dir"), None, False)
# program -> (flag letters, letters taking a value, exact long flags, long options
# taking `=VALUE`, pattern a value must match, whether a bare `-NUM` is allowed).
# No option that names a file or program to write or run, pages, follows,
# decompresses or reads a config is listed; unknown options fall back to the old
# verdict (so `tail -f`, `grep --pager=...`, `grep -z` are not exempt).
_OPTION_RULES = {
    "ls": ("aAlhdR1trSFpisLnU", "", ("--all", "--almost-all", "--human-readable",
                                     "--recursive", "--directory", "--classify",
                                     "--color=never", "--reverse", "--size",
                                     "--inode", "--dereference"), (), None, False),
    "cat": ("nbsAETv", "", ("--number", "--number-nonblank", "--squeeze-blank",
                            "--show-all", "--show-ends", "--show-tabs",
                            "--show-nonprinting"), (), None, False),
    "head": ("qv", "nc", ("--quiet", "--verbose"), ("--lines", "--bytes"),
             _NUMBER_RE, True),
    "tail": ("qv", "nc", ("--quiet", "--verbose"), ("--lines", "--bytes"),
             _NUMBER_RE, True),
    "wc": ("lwcmL", "", ("--lines", "--words", "--bytes", "--chars",
                         "--max-line-length"), (), None, False),
    "stat": ("Lft", "c", ("--dereference", "--file-system", "--terse"),
             ("--format", "--printf"), None, False),
    "grep": _GREP_RULE, "egrep": _GREP_RULE, "fgrep": _GREP_RULE,
}
# find: a primary on these lists is read-only. Every other `-word` (-delete,
# -rm, -exec, -execdir, -ok, -okdir, -fprint*, -fls, -printf, -exclude, ...) is
# unknown, so find of GNU findutils, of bfs (Claude Code's own `find`) and of
# any other implementation falls back to the old verdict.
_FIND_FLAGS = frozenset((
    "-empty", "-print", "-print0", "-prune", "-o", "-a", "-and", "-or", "-not",
    "-depth", "-xdev", "-true", "-false", "-L", "-H", "-P"))
_FIND_VALUES = frozenset((
    "-name", "-iname", "-path", "-ipath", "-wholename", "-regex", "-iregex",
    "-type", "-maxdepth", "-mindepth", "-mtime", "-mmin", "-newer", "-size",
    "-perm", "-user", "-group"))


def _simple_commands(command):
    """`command` split into simple commands, each an (argv, redirects) pair, or
    None when any of it cannot be read here. `argv` is the list of (word, quoted)
    pairs bash hands the program; `redirects` is the list of the words
    `2>/dev/null` and `2>&1` that bash removes from the line BEFORE the program
    runs (a redirect is parsed out wherever it stands: before the program, between
    an option and its value, after `--`), so no option check may ever count one as
    an argument. Only an UNQUOTED word is a redirect; a quoted look-alike contains
    `>` and is refused below. Reads only plain words,
    plain '...' and "..." strings, the separators `;` `&&` `||` `|` and the
    words `2>/dev/null` and `2>&1`; everything else (a `$` or backtick anywhere,
    even inside single quotes, `\\`, glob, brace, paren, `#`, `~`, `!`, `<`, a
    lone `&`, a newline, an unterminated quote, an empty command) is None. A
    `$` in single quotes is inert to the shell, but a builtin may evaluate its
    argument (`test -v 'a[$(cmd)]'`), so it is refused here too."""
    commands, words, redirects, word = [], [], [], None
    quoted, i, n = False, 0, len(command)

    def end_word():
        nonlocal word, quoted
        if word is not None:
            if not quoted and word in _REDIRECT_WORDS:
                redirects.append(word)
            else:
                words.append((word, quoted))
        word, quoted = None, False

    def end_command():
        nonlocal words, redirects
        end_word()
        if not words:
            return False
        commands.append((words, redirects))
        words, redirects = [], []
        return True

    while i < n:
        ch = command[i]
        if ch in "\n\r\0":
            return None
        if ch in " \t":
            end_word()
            i += 1
        elif ch in "'\"":
            close = command.find(ch, i + 1)
            if close < 0:
                return None
            body = command[i + 1:close]
            if any(c in body for c in "\n\r\0$`") or (
                    ch == '"' and any(c in body for c in "\\!")):
                return None
            word = (word or "") + body
            quoted = True
            i = close + 1
        elif ch in ";|&":
            pair = command[i:i + 2]
            if ch == "&" and word is not None and word.endswith(">"):
                word += ch
                i += 1
                continue
            if pair in ("&&", "||"):
                step = 2
            elif ch in ";|" and pair not in ("|&", ";;", ";&"):
                step = 1
            else:
                return None
            if not end_command():
                return None
            i += step
        elif ch == ">" and not quoted and word == "2":
            word += ch
            i += 1
        elif ch in _PLAIN_CHARS:
            if quoted:
                word += ch
            else:
                word = (word or "") + ch
            i += 1
        else:
            return None
    if not end_command():
        return None
    # A redirect word never reaches argv (`end_word` moved it out), so any `<`, `>`
    # or `&` left in argv is something this reader does not know. The
    # `text not in _REDIRECT_WORDS` clause is a second line of defence: should
    # one ever be kept in argv, it is still refused as soon as it is quoted.
    for argv, _ in commands:
        for text, was_quoted in argv:
            if any(c in text for c in "<>&") and (was_quoted or text not in _REDIRECT_WORDS):
                return None
    return commands


def _options_ok(rule, args, plus_is_operand=True):
    """True when every option word in `args` is on `rule`'s allow-list (see
    `_OPTION_RULES`). A word that is not an option, or `-` alone, is an operand;
    `--` ends the options. With `plus_is_operand` False (`tail`), a word starting
    with `+` is refused wherever it stands: `tail +f` and `tail +1f` are the legacy
    `+N[bcl][f]` form and follow the file forever (GNU, uutils), though they look
    like operands. The value of an option (`-n +3`) is consumed as a value, not seen
    here."""
    flags, value_letters, longs, long_values, valid, numeric = rule
    i = 0
    while i < len(args):
        word = args[i]
        i += 1
        if word == "--":
            return plus_is_operand or not any(w.startswith("+") for w in args[i:])
        if word.startswith("+") and not plus_is_operand:
            return False
        if word == "-" or not word.startswith("-"):
            continue
        if word.startswith("--"):
            name, equals, value = word.partition("=")
            if word in longs:
                continue
            if name in long_values and equals and (valid is None or valid.match(value)):
                continue
            return False
        body = word[1:]
        if numeric and body.isdigit():
            continue
        for j, letter in enumerate(body):
            if letter in flags:
                continue
            if letter not in value_letters:
                return False
            value = body[j + 1:]
            if not value:
                if i >= len(args):
                    return False
                value, i = args[i], i + 1
            if valid is not None and not valid.match(value):
                return False
            break
    return True


def _find_ok(args):
    """True when every `-word` of a find command line is a primary on the
    read-only lists. A value primary consumes the next word whatever it looks
    like; a word not starting with `-` is a start path (or a quoted `!`/`(`)."""
    i = 0
    while i < len(args):
        word = args[i]
        i += 1
        if word in _FIND_VALUES:
            if i >= len(args):
                return False
            i += 1
        elif word in _FIND_FLAGS or word == "-" or not word.startswith("-"):
            continue
        else:
            return False
    return True


def _plain_args_ok(program, args):
    """No option of a listed program writes a file, runs another program,
    follows a file forever or is unknown to its allow-list. `uniq`, `sort`,
    `file`, `test` and the other programs that are shell builtins or whose
    operands or options can write are deliberately NOT listed."""
    if program == "find":
        return _find_ok(args)
    return _options_ok(_OPTION_RULES[program], args, program != "tail")


def _read_only(command):
    """True only when `command` is wholly a pipeline or list of the listed
    read-only programs with plain literal words (see `_READ_ONLY_PROGRAMS`)."""
    parsed = _simple_commands(command)
    if not parsed:
        return False
    for argv, _redirects in parsed:
        (program, was_quoted), args = argv[0], [t for t, _ in argv[1:]]
        if was_quoted or program not in _READ_ONLY_PROGRAMS:
            return False
        if not _plain_args_ok(program, args):
            return False
    return True


def _read_payload():
    try:
        raw = sys.stdin.buffer.read()
    except (OSError, ValueError):
        return None
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    try:
        data = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    except (UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def targets(data):
    """Every path a Write/Edit/MultiEdit/NotebookEdit call names."""
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    found = [tool_input.get(key) for key in ("file_path", "notebook_path")]
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            found.append(edit.get("file_path"))
    return [p for p in dict.fromkeys(found) if isinstance(p, str) and p]


def _under(path, directory):
    path, directory = os.path.normcase(path), os.path.normcase(directory)
    return path == directory or path.startswith(directory.rstrip(os.sep) + os.sep)


def _rel(path, top):
    """`path` relative to `top` with `/` separators, or None when outside."""
    try:
        rel = os.path.relpath(path, top)
    except ValueError:
        return None
    rel = rel.replace(os.sep, "/")
    return None if rel == ".." or rel.startswith("../") else rel


def classify(top, common, ticket, touch, approval, target, base):
    """(ok, reason) for one target path."""
    absolute = target if os.path.isabs(target) else os.path.join(base, target)
    real = role_write_guard._resolve_real_target(absolute)  # pylint: disable=protected-access
    named = os.path.normpath(absolute)
    real_rel, named_rel = _rel(real, top), _rel(named, top)
    if common and (_under(real, common) or _under(named, common)):
        return False, f"{target} is inside the git directory; never in scope"
    own = f".work/tickets/{ticket}/"
    checks = [r for r in (real_rel, named_rel) if r is not None]
    if not checks:
        return True, "outside the worktree"
    if all(os.path.normcase(r).startswith(os.path.normcase(own)) for r in checks):
        return True, "the ticket's own files"
    if real_rel is not None and all(crew_ticket.is_crew_write_allowed(r) for r in checks):
        return True, "crew bookkeeping"
    if real_rel is not None and all(crew_ticket.is_handoff_path(r) for r in checks):
        return True, "the session handoff note"
    if _refresh_artifact(top, real_rel, checks, approval):
        return True, "a refresh artifact of an approved ticket"
    if approval["status"] != "approved":
        return False, (f"{ticket}: {approval['why']}"
                       if approval["status"] in ("stale", "unaccepted")
                       else f"{ticket} has no approved plan")
    outside = [r for r in checks if not crew_ticket.in_touch(r, touch)]
    if real_rel is None and named_rel is not None:
        outside.append(f"{named_rel} -> {real} (outside the worktree)")
    if outside:
        return False, f"{outside[0]} is outside {ticket}'s spec ## Touch"
    return True, "in Touch"


def _refresh_artifact(top, real_rel, checks, approval):
    """Every judged path is a refresh artifact
    (`crew_refresh_check.REFRESH_ARTIFACT_PATHS`) AND the approval is current
    and from the user's prompt (module docstring, rule 6). A real path
    outside the worktree is never one, whatever the name says."""
    if approval["status"] != "approved":
        return False
    if real_rel is None:
        return False
    import crew_refresh_check  # pylint: disable=import-outside-toplevel
    dirs = crew_refresh_check.refresh_artifact_paths(top)
    return all(crew_refresh_check.is_refresh_artifact(r, dirs) for r in checks)


def confirm_store():
    """The double-confirmation receipts store, beside the machine config
    (`crew_humanonly.store_dir()` for the default config path). Spelled here
    so this guard imports neither `crew_state` nor `crew_humanonly`."""
    return os.path.join(os.path.expanduser("~"), ".claude", "crew", "confirm-config")


def machine_config():
    """The machine config file (`~/.claude/crew/config.json`), which holds `guards.enabled`, the switch that
    stands every guard down (crew 1.3.137). Like `confirm_store`, spelled here so this guard imports no config
    module."""
    return os.path.join(os.path.expanduser("~"), ".claude", "crew", "config.json")


def _owner_path(path):
    """True for the owner's own files: the double-confirmation store and the machine config, which holds
    `guards.enabled` (crew 1.3.137)."""
    return _under(path, confirm_store()) or os.path.normcase(path) == os.path.normcase(machine_config())


def protected(top, state, target, base):
    """True when `target` names crew's approval/ledger state, or bookkeeping
    a Write/Edit may never touch (module docstring, rule 2)."""
    absolute = _plain_spelling(target if os.path.isabs(target) else os.path.join(base, target))
    real = _plain_spelling(role_write_guard._resolve_real_target(absolute))  # pylint: disable=protected-access
    named = os.path.normpath(absolute)
    for path in (real, named):
        if state and _under(path, state):
            return True
        if _owner_path(path):
            return True
        rel = _rel(path, top)
        if rel is not None and os.path.normcase(rel) == os.path.normcase(SCOPE_BASE):
            return True
        if rel is not None and crew_ticket.is_crew_write_refused(rel):
            return True
    return False


def _autopilot_refusal(command, top):
    """Why a command naming `crew_autopilot.py approve` is refused, or None
    for the bare form while `approval_policy` allows it (module docstring)."""
    bare = _AUTOPILOT_BARE_RE.fullmatch(command)
    if not bare:
        return ("autopilot approval must be the bare command `python3 <path>/"
                "crew_autopilot.py approve --root . --ticket <id>`, nothing chained")
    ticket = bare.group(1)
    try:
        import crew_autopilot  # pylint: disable=import-outside-toplevel
        decision = crew_autopilot.approval_policy(top, ticket) if top else None
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-except
        return (f"could not tell whether autopilot.approval allows {ticket} "
                f"({type(exc).__name__}); only the user's /crew:approve approves")
    if isinstance(decision, dict) and decision.get("allow") is True:
        return None
    reason = decision.get("reason") if isinstance(decision, dict) else "could not tell"
    return f"autopilot.approval does not allow {ticket}: {reason}"


def _joined(command):
    """`command` as written, as bash joins its continuations, and as
    PowerShell does -- every check runs on all three, so a newline that only
    continues the line never ends the span a check reads."""
    bash = _BASH_CONTINUATION_RE.sub("", command)
    return command, bash, _PS_CONTINUATION_RE.sub(" ", command)


_QUOTE_RE = re.compile(r"[\"'\\]")


def _assembled_trust_refusal(text):
    """Why `text` (one reading of a shell command) is refused for building a
    trust-store change at run time, or None."""
    names = list(_TRUST_NAME_RE.finditer(text))
    for hit in names:
        span = re.split(r"[\n;&|]", text[hit.end():], maxsplit=1)[0]
        dynamic = _DYNAMIC_RE.search(span)
        if dynamic:
            verb = _TRUST_READ_VERB_RE.search(span)
            if not verb or verb.start() > dynamic.start():
                return ("a variable, substitution or wildcard stands where the verify_trust verb "
                        "goes; only a literal `status` or `check` is run from a model")
    if names and _ASSEMBLY_RE.search(text):
        return "it builds a verify_trust call at run time; only a person at a terminal trusts a repo"
    if names and _TRUST_IMPORT_RE.search(text) and _TRUST_WRITER_CALL_RE.search(text):
        return "it calls the verify trust store's writers; only a person at a terminal trusts a repo"
    if _DYNAMIC_IMPORT_RE.search(text) and _SCRIPTS_DIR_RE.search(text):
        return ("it imports from the plugin scripts directory at run time, which can reach the "
                "verify trust store; only a person at a terminal trusts a repo")
    if _STORE_OVERRIDE_RE.search(text):
        return "it names CREW_VERIFY_TRUST_FILE, the verify trust store's test seam"
    if names and _SESSION_VAR_RE.search(text):
        return "it names CLAUDECODE beside verify_trust; the session variable is not the model's"
    if _STORE_DIR_RE.search(text) and _WRITES_RE.search(text):
        return "it writes a verify-* file under crew's config directory, the verify trust store"
    return None


_TRUST_VERBS = frozenset({"approve", "allow-owner", "disallow-owner", "revoke"})
_INTERPRETER_RE = re.compile(r"(?:^|[/\\])(?:python[0-9.]*|py|pypy[0-9.]*|(?:ba|z|da|k|a)?sh)(?:\.exe)?$",
                             re.IGNORECASE)
_SCRIPT_TOKEN_RE = re.compile(r"\.pyw?$|[*?\[]", re.IGNORECASE)
_GLOB_SCRIPT_RE = re.compile(r"[*?\[]")


_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = frozenset({"env", "sudo", "command", "exec", "nohup", "time", "nice", "builtin"})
# Scripts with a guard and an `approve` verb of their own (judged above, by
# `_autopilot_refusal` and the `crew_ticket` approve rule): not a trust verb.
_OWN_APPROVER_RE = re.compile(r"crew_(?:autopilot|ticket)(?:\.py)?$")
_WRAPPER_VALUE_OPTIONS = {
    "env": ("-u", "-C", "-S"),
    "sudo": ("-u", "-g", "-h", "-p", "-C", "-D", "-R", "-T", "-U"),
    "nice": ("-n",),
    "time": ("-f", "-o"),
}
_PROGRAM_OPTIONS = frozenset({"-m"})
_MODULE_EXPANSION_RE = re.compile(r"[$`*?\[]")
_VALUE_OPTIONS = frozenset({"-W", "-X", "-Q"})


def _basename(token):
    return re.split(r"[\\/]", token)[-1].lower()


def _first_word_index(tokens):
    """Index of the command word of one segment: past leading `NAME=value`
    assignments, a wrapper such as `env` or `sudo` and the options it was given,
    or None. Only this word is the interpreter; a later token that merely looks
    like one (`git commit -m "python3 fix, now approve"`) is prose."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if _ASSIGNMENT_RE.match(token):
            index += 1
        elif token in _WRAPPERS:
            index += 1
            takes_value = _WRAPPER_VALUE_OPTIONS.get(token, ())
            while index < len(tokens) and (tokens[index].startswith("-")
                                           or _ASSIGNMENT_RE.match(tokens[index])):
                # `env -u CLAUDECODE python3 ...`: the option's value is not the command.
                index += 2 if tokens[index] in takes_value else 1
        else:
            return index
    return None


def _segment_verb(tokens):
    """True when one command segment hands a trust verb to a script. The command
    word (past assignments and a wrapper) is either an interpreter or shell,
    whose script operand is `-` (the script on stdin) or the first word that is
    not an option, with `-c` reading its program as a fresh command and `-m`
    ending the scan (a module named like the trust script is judged by the other
    checks); or it is itself a path, an executable copy run directly
    (`/tmp/x approve`). So `python3 -m pytest -k "approve and not revoke"` reads
    no verb."""
    first = _first_word_index(tokens)
    if first is None:
        return False
    command, rest = tokens[first], tokens[first + 1:]
    if _OWN_APPROVER_RE.search(_basename(command)):
        return False
    if not _INTERPRETER_RE.search(command):
        return bool(re.search(r"[/\\]", command)) and bool(rest) and rest[0].lower() in _TRUST_VERBS
    index = 0
    while index < len(rest):
        token = rest[index]
        if token == "-":
            return index + 1 < len(rest) and rest[index + 1].lower() in _TRUST_VERBS
        if token == "-c":
            return _segment_verb(rest[index + 1:])
        if token in _PROGRAM_OPTIONS:
            # A module word a shell will expand (`verify_tru${X}`, `$MOD`, a backtick,
            # a wildcard) may become verify_trust at run time (round 10): refused when a
            # trust verb follows. A literal module name is judged by the other checks.
            expanded = index + 1 < len(rest) and _MODULE_EXPANSION_RE.search(rest[index + 1])
            return bool(expanded) and any(t.lower() in _TRUST_VERBS for t in rest[index + 2:])
        if token in _VALUE_OPTIONS:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        if _OWN_APPROVER_RE.search(_basename(token)):
            return False
        return index + 1 < len(rest) and rest[index + 1].lower() in _TRUST_VERBS
    return False


def _script_verb_refusal(text):
    """Why a reading is refused for a trust verb standing as the first word
    after a script, wherever that script is read from, or None. Independent of
    the script's name: the verb word is the signal. A verb after `-`
    (`python3 - approve < verify_trust.py`, `cat verify_trust.py | python3 -
    approve`), after a script token (a copy under another name, a glob such as
    `verify_t*st.py`) or after anything else an interpreter was handed, is
    refused; a verb after an option (`--root approve`, `-k approve`), glued to
    a path (`/tmp/approve`) or in a command with no interpreter or script
    token (`grep -n approve`, `echo approve`) is an argument, not the verb."""
    for segment in re.split(r"[\n;&|]", text):
        tokens = [t.strip("()\"'`{}") for t in segment.split()]
        tokens = [t for t in tokens if t]
        if _segment_verb(tokens):
            return ("it hands a verify trust verb to a script read from stdin, a copy or a "
                    "wildcard path; only a person at a terminal trusts a repo")
        for before, after in zip(tokens, tokens[1:]):
            verb = after.lower() in _TRUST_VERBS
            if verb and not before.startswith("-") and _SCRIPT_TOKEN_RE.search(before) \
                    and not _OWN_APPROVER_RE.search(_basename(before)):
                return ("it hands a verify trust verb to a script read from stdin, a copy or a "
                        "wildcard path; only a person at a terminal trusts a repo")
            if _GLOB_SCRIPT_RE.search(before) and ".p" in before.lower() \
                    and after.startswith(("$", "`")):
                return ("a wildcard script path is given a variable where the verify trust verb "
                        "goes; only a person at a terminal trusts a repo")
    return None


def _trust_reading_refusal(command):
    """Why one reading of a shell command is refused for the verify trust
    store, or None. Judged on the reading as written AND with every quote and
    backslash deleted, so `ap''prove`, `"approve"` and `app\\rove` (which a
    shell joins into the verb) read as the verb."""
    for text in (command, _QUOTE_RE.sub("", command)):
        if _TRUST_RE.search(text):
            return ("it changes the verify trust store (`verify_trust.py approve`, `allow-owner`, "
                    "`disallow-owner` or `revoke`); only a person at a terminal trusts a repo")
        if _TRUST_IMPORT_RE.search(text) and _TRUST_VERB_RE.search(text):
            return ("it drives the verify trust store through the module; only a person at a "
                    "terminal trusts a repo")
        if TRUST_STORE_NAME in text.lower() and _WRITES_RE.search(text):
            return "it writes the verify trust store, which only a person at a terminal may change"
        assembled = _assembled_trust_refusal(text)
        if assembled:
            return assembled
        scripted = _script_verb_refusal(text)
        if scripted:
            return scripted
    return None


def trust_refusal(data):
    """Why a tool payload is refused for the verify trust store ALONE, or None.
    Judged before the scope mode is read and whether or not the directory is a
    git repo: a mode of `off` (a config key a session can write) switches the
    scope guard off, and must not switch off the one rule that keeps a model
    from trusting a repo for itself. A payload this check fails on is refused
    (crew 1.3.146): `main` allows what it could not judge when the mode is
    off or report, and "could not tell" is not "does not touch the store"."""
    try:
        return _trust_refusal(data)
    except Exception as exc:  # noqa: BLE001  pylint: disable=broad-except
        return ("the guard could not tell whether it changes the verify trust store "
                f"({type(exc).__name__}), which only a person at a terminal may change")


def _trust_refusal(data):
    """`trust_refusal`'s answer; it may raise."""
    tool = data.get("tool_name")
    tool_input = data.get("tool_input")
    if tool in SHELLS:
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str):
            return None
        for reading in _joined(command):
            reason = _trust_reading_refusal(reading)
            if reason:
                return reason
        return None
    try:
        store = os.path.normcase(os.path.abspath(verify_trust.store_path()))
    except verify_trust.TrustError:
        # A store location a repo can author (relative, from settings env) is
        # UNKNOWN to the trust check; the guard still refuses the store's names.
        store = None
    for target in targets(data):
        absolute = os.path.abspath(target)
        real = role_write_guard._resolve_real_target(absolute)  # pylint: disable=protected-access
        for path in (absolute, real):
            if os.path.basename(path).lower() in (TRUST_STORE_NAME, TRUST_STORE_NAME + ".lock") \
                    or (store and os.path.normcase(path) in (store, store + ".lock")):
                return ("it writes the verify trust store, which only a person at a terminal "
                        "may change")
    return None


def shell_refusal(command, common, top=None, agent_type=None):
    """Why a Bash/PowerShell `command` is refused, or None (module docstring,
    "Bash and PowerShell"). Textual on purpose, and conservative: a benign
    command that names crew's state beside a writing word is refused too.
    `top` is the worktree whose autopilot policy judges `crew_autopilot.py
    approve`; without it that command is refused. `agent_type`, when a
    non-empty string, is a subagent: the never-list is refused too. Every
    distinct reading `_joined` gives is judged, in its order; the first
    refusal wins. A command with no continuation reads the same three ways,
    and judging it once matters (A-0013): an autopilot approve runs
    `approval_policy`, about fourteen git calls in a lane, and three of those
    ran past crew_hook's 15 s limit, so the guard failed closed."""
    if not isinstance(command, str):
        return None
    for reading in dict.fromkeys(_joined(command)):
        reason = _reading_refusal(reading, command, common, top, agent_type)
        if reason:
            return reason
    return None


def _reading_refusal(command, written, common, top, agent_type=None):
    """Why one reading (`_joined`) of the shell command `written` is refused,
    or None. The autopilot bare-command rule judges `written` as written, so
    a line continuation never makes an approve bare."""
    if isinstance(agent_type, str) and agent_type.strip() and (
            _ACCEPT_RE.search(command) or _ADMIN_MERGE_RE.search(command)):
        return LANE_REFUSAL
    if _APPROVE_RE.search(command):
        return "it runs `crew_ticket.py approve`; approval comes from the user's own prompt"
    if _AUTOPILOT_APPROVE_RE.search(command):
        return _autopilot_refusal(written, top)
    if _HOOK_RE.search(command):
        return "it names the approval hook, which only the user's prompt may drive"
    trust = _trust_reading_refusal(command)
    if trust:
        return trust
    state = os.path.join(common, "crew") if common else None
    folded = os.path.normcase(command).replace("\\", "/")
    names_state = bool(_DOTGIT_CREW_RE.search(command)) or bool(
        state and os.path.normcase(state).replace("\\", "/") in folded)
    if names_state and _WRITES_RE.search(command) and not _read_only(command):
        return "it writes under <git-common-dir>/crew/, crew's approval and ledger state"
    store = os.path.normcase(confirm_store()).replace("\\", "/")
    if ((_CONFIRM_STORE_RE.search(command) or store in folded)
            and not _read_only(command) and _store_write(command, top)):
        return ("it writes under the confirm-config store, the receipts of the owner's "
                "double confirmation")
    return _owner_command_refusal(command, top)


# --- the owner's files, through a shell (crew 1.3.137, target-based since the round-3 owner decision) ------------
# A command is refused when something in it WRITES TO the owner's files: a redirect, or the argument a write verb
# aims at (`tee`, `cp`, `mv`, `rm`, `sed -i`, `Set-Content`, `curl -o`, `tar -C`, `git apply` ...), or inline code
# (`python -c`, a heredoc) that names them beside a write call. A command that merely MENTIONS them -- a commit
# message, a PR body, `ls ~/.claude/crew/ > /tmp/ls.txt`, `cat config.json | tee out.json`, a read -- passes, and so
# does an unrelated write in the same line. The command is cut into segments at `;` `&&` `||` `|` and newlines,
# quotes are honoured (a `>` in a quoted word is text), `cd`/`Set-Location` and `NAME=value` are followed, and
# `bash -c`, `pwsh -Command`, `$(...)` and shell heredocs are read as commands too.
# This is a guardrail against an agent's accident or drift, NOT a boundary against a hostile one running as the same
# user: a helper script behind `cd`, `pytest`/`uv`/`make`/`python -m` launchers, an 8.3 short name, base64 or a path
# built by arithmetic still write the file, and CONFIG.md says so. No script is opened or sized (an unreadable or
# huge file refuses nothing): the owner's order is that the crew runs every normal command.
# Round 10 (crew 1.3.137) names the rest of that tail, also in CONFIG.md: an alias (`Set-Alias w Set-Content`), a
# splatted hashtable (`@a`), `[scriptblock]::Create(...)`, the content of a script file (`bash script.sh`), a string
# built by concatenation and handed to `iex`, and `touch`/`chmod` (metadata only) are not read.
OWNER_REASON = "it writes the owner's files"
# A write call inside inline code (`python -c`, a heredoc, `pwsh -Command`, `node -e`).
_CODE_WRITES_RE = re.compile(
    r"\.write|write_text|write_bytes|writelines|\bdump\(|\bunlink|os\.remove|os\.replace|os\.rename|\.rename\(|"
    r"shutil|rmtree|\bcopyfile|\bmove\(|writeall|writefile|appendfile|createwritestream|"
    r"\bopen\([^)]*['\"][rwax]*[wax+][rwabxt+]*['\"]|mode\s*=\s*['\"][rwax]*[wax+]|o_wronly|o_rdwr|o_creat|"
    r"set-content|add-content|out-file|new-item|copy-item|move-item|remove-item|rename-item|clear-content|"
    r"\[(?:system\.)?io\.file\]::(?:write|append|copy|move|delete|create|replace|setattributes|openwrite|"
    r"open\w*\([^)]*(?:create|append|truncate|write))", re.IGNORECASE)
_HOME_PART = r"(?:~|\$home|\$\{home\}|%userprofile%|\$env:userprofile|\$env:home)"
_HOME_VARS = frozenset({"home", "userprofile"})
_CODE_RUNNERS = frozenset({"python", "python3", "py", "node", "nodejs", "deno", "bun", "perl", "ruby", "php", "lua"})
_CODE_FLAGS = frozenset({"-c", "-e", "-p", "-r", "-E", "--eval", "--command"})
_POSIX_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
_PWSH = frozenset({"pwsh", "powershell"})
# The words that only run another command (crew 1.3.137: `.`, `timeout`, `nice`, `stdbuf`, `ionice`, `setsid`,
# `busybox`, `wsl`). Named apart from the trust check's `_WRAPPERS` above: until round 10 this set carried that name
# too, replaced it for the whole module, and so dropped `nice` from the trust check (`nice /tmp/x approve`).
_OWNER_WRAPPERS = frozenset({"sudo", "env", "time", "command", "nohup", "exec", "builtin", "call", "start", "&", ".",
                             "timeout", "nice", "stdbuf", "ionice", "setsid", "busybox", "wsl"})
# the options of a wrapper that take a value of their own: the word after one is not the command
_OWNER_WRAPPER_VALUES = {
    "timeout": frozenset({"-s", "--signal", "-k", "--kill-after"}),
    "nice": frozenset({"-n", "--adjustment"}),
    "stdbuf": frozenset({"-i", "-o", "-e"}),
    "ionice": frozenset({"-c", "-n", "-p"}),
    "sudo": frozenset({"-u", "-g", "-h", "-p", "-C"}),
    "env": frozenset({"-u", "--unset", "-C", "--chdir"}),
    "wsl": frozenset({"-d", "--distribution", "-u", "--user", "--cd"}),
}
_XARGS_VALUES = frozenset({"-I", "-n", "-P", "-L", "-s", "-d", "-E", "-a", "--max-args", "--max-procs",
                           "--delimiter", "--arg-file", "--max-lines", "--max-chars", "--eof"})
_DECLARERS = frozenset({"export", "declare", "local", "typeset", "readonly", "set"})
_CD = frozenset({"cd", "chdir", "set-location", "sl", "push-location", "pushd"})
_PUSHD = frozenset({"pushd", "push-location"})
_POPD = frozenset({"popd", "pop-location"})
_REMOVERS = frozenset({"rm", "unlink", "shred", "del", "erase", "rd", "rmdir", "remove-item", "ri",
                       "mv", "move", "ren", "rename", "rename-item", "rni", "move-item", "mi"})
_WRITERS = frozenset({"tee", "truncate", "clear-content", "set-content", "add-content", "out-file", "new-item", "ni",
                      "set-item", "sponge", "sc", "ac", "mklink", "clc", "tee-object", "export-csv", "epcsv",
                      "export-clixml"})
# The programs that only READ what they are given (crew 1.3.137). The owner's file as an operand of one is a read, so
# it does not make the command one that "names the owner's folder" (`_owner_hint`): `cat <owner file> > "$OUT"` writes
# `$OUT`, not the owner's file. `echo` and `printf` are not here: they hand the name on (`echo <it> | xargs rm`).
_READERS = frozenset({
    "cat", "ls", "dir", "head", "tail", "wc", "stat", "file", "grep", "egrep", "fgrep", "rg", "ag", "less", "more",
    "type", "diff", "cmp", "jq", "sort", "uniq", "cut", "od", "xxd", "hexdump", "strings", "md5sum", "sha1sum",
    "sha256sum", "cksum", "test", "[", "[[", "realpath", "readlink", "basename", "dirname", "du", "tree", "bat", "nl",
    "tac", "findstr", "where", "which", "get-content", "gc", "get-item", "gi", "get-childitem", "gci", "test-path",
    "select-string", "sls", "resolve-path", "rvpa", "get-filehash", "get-acl", "measure-object", "get-itemproperty"})
# The PowerShell cmdlets that bind their path from the pipeline when none is given (`Get-Item <f> | Remove-Item`).
_PIPE_BOUND = frozenset({"remove-item", "ri", "rm", "del", "erase", "rd", "rmdir", "clear-content", "clc",
                         "set-content", "sc", "add-content", "ac", "move-item", "mi", "rename-item", "rni"})
_COPIERS = frozenset({"cp", "copy", "copy-item", "cpi", "xcopy", "robocopy", "rsync", "install", "ln"})
_EDITORS = frozenset({"vim", "vi", "nvim", "ex", "ed", "nano", "view"})
_GIT_WRITES = frozenset({"apply", "am", "checkout", "restore", "reset", "clean", "stash", "merge", "pull", "rebase",
                         "mv", "rm", "switch", "cherry-pick", "revert"})
_OPTION_RE = re.compile(r"^(?:-[^\s]|/[A-Za-z?]{1,2}(?::\S*)?$)")
_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.DOTALL)
_VAR_RE = re.compile(r"\$env:(\w+)|\$\{(\w+)\}|\$(\w+)|%(\w+)%", re.IGNORECASE)
# What is left of a variable once `_expand` has put in every value it knows: PowerShell's `${env:X}` and `$env:X`,
# bash's `${X:-y}`. Its value is unknown, and its colon is no NTFS stream (`c${env:X}nfig.json`, crew 1.3.137).
_UNREAD_VAR_RE = re.compile(r"\$\{[^}]*\}|\$env:\w+", re.IGNORECASE)
_DRIVE_RE = re.compile(r"^[a-z]:/")
_IGNORED_TARGET_RE = re.compile(r"^(?:/dev/\w+|\$null|nul|&\d|-)$", re.IGNORECASE)


def _fold(text):
    folded = os.path.normcase(text).replace("\\", "/").lower()
    return re.sub(r"/{2,}", "/", folded)


def _names_owner(code):
    """Why inline `code` names the owner's files (the machine config, its folder, the confirm-config store), or
    None. Text only: it sees a path spelled out, in pieces or through a glob, never one built by arithmetic."""
    text = _fold(code)
    machine = _fold(machine_config())
    if re.search(r"(?<![:\w-])confirm-config(?![\w-]|\.md)", text):
        return "the confirm-config store, the receipts of the owner's double confirmation"
    named = (machine in text or _fold(os.path.dirname(machine)) in text
             or re.search(r"\.claude/+crew\b", text) or re.search(r"(?<![\w.-])crew/+config\.json\b", text)
             # a path built from its pieces: `.claude`, a bare `crew` and `config` in one program
             or (re.search(r"(?<![\w])\.claude(?![\w-])", text) and re.search(r"(?<![\w.-])crew(?![\w-])", text)
                 and "config" in text)
             # a glob under `.claude/`, or under a dot-folder of home
             or re.search(r"\.claude/+[^\s;&|]*[*?\[]", text)
             or re.search(_HOME_PART + r"/+\.[^/\s;&|]*[*?\[]", text))
    return "the machine config (~/.claude/crew/config.json)" if named else None


def _code_refusal(code):
    """Why inline program text writes the owner's files (names them beside a write call), or None."""
    if _names_owner(code) and _CODE_WRITES_RE.search(code):
        return f"{OWNER_REASON}: its inline code names them and writes"
    return None


# --- cutting a command into segments -------------------------------------------------------------------------

def _balanced(text, start):
    """`(inner, next index)` of the `$(` ... `)` whose body starts at `start`."""
    depth, index = 1, start
    while index < len(text):
        char = text[index]
        if char in "'\"":
            end = text.find(char, index + 1)
            index = end if end != -1 else len(text)
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start:index], index + 1
        index += 1
    return text[start:], len(text)


_QUOTE_OPEN, _QUOTE_CLOSE = "\x01", "\x02"
# What the splitter cannot read as text (crew 1.3.137, round 9): `_DYN` stands where a `$(...)` / `$'...'` produced
# characters, `_PAREN` starts a word that sits inside a parenthesised expression (`(Join-Path $HOME "x")`).
_DYN, _PAREN = "\x03", "\x04"
# `_TAINT` (crew 1.3.137, round 10) is a `_DYN` whose source spells pieces of the owner's path (`_plausible`):
# `$(echo ~/.claude/crew)`, a word of `(Join-Path $HOME ".claude/crew/config.json")`, a variable assigned from either.
# A write target the guard cannot resolve fails closed when it carries one, whatever else the command says.
_TAINT = "\x05"
_MARKS = _DYN + _PAREN + _TAINT

# What spells the owner's folder: `.claude/crew` (not its `worktrees/` folder, where crew keeps ordinary checkouts),
# `crew/config.json`, the confirm-config store. `.claude` alone does not: every repo has one.
_HINT_RES = (re.compile(r"(?<![\w-])\.claude/+crew(?![\w.-])(?!/+worktrees(?![\w.-]))"),
             re.compile(r"(?<![\w:-])confirm-config(?![\w-]|\.md)"),
             re.compile(r"(?<![\w.-])crew/+config\.json\b"))
# The same folder spelled in pieces, as an expression joins them: `.claude` and a `crew` folder in one expression.
_PIECE_RES = (re.compile(r"(?<![\w-])\.claude(?![\w-])(?!/+(?:crew/+)?worktrees(?![\w.-]))"),
              re.compile(r"(?<![\w.-])crew(?![\w.-])"))


def _spells_owner(text, pieces=False):
    """True when `text` spells the owner's folder (`_HINT_RES`), read plainly and again with its escape characters,
    quotes and markers taken out; with `pieces`, also when it holds `.claude` and a `crew` folder apart."""
    for reading in (text, re.sub(r"[\\`^'\"\x01-\x05]", "", text)):
        folded = _win32_names(_fold(reading))   # `crew./config.json` is `crew/config.json`
        if any(found.search(folded) for found in _HINT_RES):
            return True
        if pieces and all(found.search(folded) for found in _PIECE_RES):
            return True
    return False


def _plausible(text):
    """True when `text`, an expression or a substitution the guard cannot evaluate, could build the owner's path: it
    spells the owner's folder, whole or in pieces."""
    return _spells_owner(text, pieces=True)


def _mark(inner):
    """The marker that stands for a substitution whose body is `inner`."""
    return _TAINT if _plausible(inner) else _DYN


class _Segment:  # pylint: disable=too-few-public-methods
    """One simple command: its words, the targets of its redirects, `$(...)` bodies, and heredoc bodies (a
    here-string is a body too). `piped` is True when a `|` feeds it."""

    def __init__(self):
        self.words, self.targets, self.subs, self.bodies = [], [], [], []
        self.raws = []   # each word again, with a quoted part wrapped in _QUOTE_OPEN ... _QUOTE_CLOSE
        self.piped = False
        self.opens = self.closes = 0   # the subshells this command starts (`(cd x && ...`) and ends (`... )`)

    def __bool__(self):
        return bool(self.words or self.targets or self.subs or self.bodies)


# the text between two backticks that is a COMMAND (bash) and not a character escaped twice (PowerShell): it holds a
# space or a shell character and does not start with a space
_BACKTICK_COMMAND_RE = re.compile(r"(?!\s)[^`]*[\s;|&<>()][^`]*")
_ANSI_ESCAPE_RE = re.compile(r"\\(?:x[0-9a-fA-F]{1,2}|u[0-9a-fA-F]{1,4}|U[0-9a-fA-F]{1,8}|[0-7]{1,3}|c.)")


def _dq_substitutions(chunk, seg):
    """The text of a double-quoted `chunk` with each `$(...)` replaced by `_DYN` (its body is `seg.subs`'s)."""
    out, index = [], 0
    for found in re.finditer(r"\$\(", chunk):
        if found.start() < index:
            continue
        inner, after = _balanced(chunk, found.end())
        seg.subs.append(inner)
        out += [chunk[index:found.start()], _mark(inner)]
        index = after
    rest = "".join(out) + chunk[index:]
    for found in re.finditer(r"`([^`]*)`", rest):   # bash runs a backtick pair inside double quotes too
        if _BACKTICK_COMMAND_RE.fullmatch(found.group(1)):
            seg.subs.append(found.group(1))
    return re.sub(r"`([^`]*)`",
                  lambda m: _mark(m.group(1)) if _BACKTICK_COMMAND_RE.fullmatch(m.group(1)) else m.group(0), rest)


def _segments(text):  # pylint: disable=too-many-branches,too-many-statements
    """The `_Segment`s of `text`, split at `;` `&&` `||` `|` `&` and newlines, outside quotes."""
    result, seg = [], _Segment()
    buf, raw, has, mode = [], [], False, None   # mode: None | "target" | "skip" | "heredoc"
    delims = []
    index, size = 0, len(text)

    ansi = False   # the next quoted part is `$'...'`
    parens = 0   # how deep the command is inside a parenthesised expression (not a statement-initial subshell)
    group = (0, 0)   # where the words and the targets of the outermost open parenthesised expression start

    def flush():
        nonlocal buf, raw, has, mode
        if not has:
            return
        word, spelled, buf, raw, has = "".join(buf), "".join(raw), [], [], False
        if parens and mode in (None, "target"):
            word = _PAREN + word
        if mode == "heredoc":
            delims.append(word)
        elif mode == "herestring":
            seg.bodies.append(word)   # `bash <<< "..."`: the text the command reads
        elif mode == "target":
            seg.targets.append(word)
        elif mode is None:
            seg.words.append(word)
            seg.raws.append(spelled)
        mode = None

    def close(piped=False):
        nonlocal seg, group
        flush()
        piped = piped or (seg.piped and not seg)   # `a |` then a newline: the pipe still feeds the next command
        if seg:
            result.append(seg)
        seg = _Segment()
        seg.piped = piped
        group = (0, 0)

    def end_group():
        """The outermost parenthesised expression closed: when its words spell pieces of the owner's path
        (`(Join-Path $HOME ".claude/crew/config.json")`), every one of them is marked `_TAINT`."""
        if _plausible(" ".join(seg.words[group[0]:] + seg.targets[group[1]:])):
            for words, start in ((seg.words, group[0]), (seg.targets, group[1])):
                words[start:] = [_PAREN + _TAINT + word.lstrip(_PAREN) for word in words[start:]]

    while index < size:
        char = text[index]
        if char in "'\"":
            end = index + 1
            while end < size and text[end] != char:
                end += 2 if (char == '"' and text[end] == "\\" and end + 1 < size and text[end + 1] == '"') else 1
            chunk = text[index + 1:end]
            if char == '"':
                chunk = _dq_substitutions(chunk, seg)
            elif ansi:
                chunk = _ANSI_ESCAPE_RE.sub(_DYN, chunk)   # `$'conf\x69g'`: the shell makes those characters
            ansi = False
            buf.append(chunk)
            raw.append(_QUOTE_OPEN + chunk + _QUOTE_CLOSE)
            has = True
            index = end + 1
        elif char == "$" and text[index + 1:index + 2] == "(":
            inner, index = _balanced(text, index + 2)
            seg.subs.append(inner)
            buf.append(_mark(inner))
            raw.append(_DYN)
            has = True
        elif char == "$" and text[index + 1:index + 2] in ("'", '"'):
            ansi = text[index + 1] == "'"
            index += 1
        elif char == "`":
            end = text.find("`", index + 1)
            inner = text[index + 1:end] if end != -1 else ""
            if _BACKTICK_COMMAND_RE.fullmatch(inner):   # bash runs a command here; PowerShell's escape is one character
                seg.subs.append(inner)
                buf.append(_mark(inner))
                raw.append(_DYN)
                index = end + 1
            else:
                buf.append(char)
                raw.append(char)
                index += 1
            has = True
        elif char == "#" and not has:
            while index < size and text[index] != "\n":
                index += 1
        elif char == "\n":
            flush()
            index += 1
            for delim in delims:
                body = []
                while index < size:
                    stop = text.find("\n", index)
                    stop = size if stop == -1 else stop
                    line = text[index:stop]
                    index = stop + 1
                    if line.strip() == delim:
                        break
                    body.append(line)
                seg.bodies.append("\n".join(body))
            delims.clear()
            close()
        elif char in ";|":
            start = index
            index += 1
            while text[index:index + 1] == char or (char == "|" and text[index:index + 1] == "&"):
                index += 1
            close(piped=text[start:index] in ("|", "|&"))   # a pipe feeds the next command; `||` and `;` do not
        elif char == "&":
            if text[index + 1:index + 2] == ">":
                flush()
                index += 1   # `&>` is a redirect: the `>` below takes it
            else:
                close()
                index += 1
                while text[index:index + 1] == "&":
                    index += 1
        elif char == ">":
            if has and "".join(buf).isdigit():
                buf, raw, has = [], [], False   # `2>`: the descriptor is no word
            flush()
            index += 1
            if text[index:index + 1] == ">":
                index += 1
            if text[index:index + 1] == "&":
                index += 1
                if text[index:index + 1].isdigit() or text[index:index + 1] == "-":
                    mode = "skip"
                    continue
            elif text[index:index + 1] == "|":
                index += 1
            mode = "target"
        elif char == "<":
            if has and "".join(buf).isdigit():
                buf, raw, has = [], [], False
            flush()
            count = 0
            while text[index:index + 1] == "<":
                count += 1
                index += 1
            if count == 2:
                if text[index:index + 1] == "-":
                    index += 1
                mode = "heredoc"
            else:
                mode = "herestring" if count == 3 else "skip"
        elif char in " \t\r()":
            prior = "".join(buf)
            flush()
            if char == "(" and (seg.words or seg.targets or mode == "target") and not re.search(r"::\w+$", prior):
                if not parens:
                    group = (len(seg.words), len(seg.targets))
                parens += 1
            elif char == "(":
                seg.opens += 1   # statement-initial: a subshell, whose `cd` ends with it
            elif char == ")" and parens:
                parens -= 1
                if not parens:
                    end_group()
            elif char == ")":
                ended = seg if seg else (result[-1] if result else seg)   # `(cd x; ls; )`: the command before it
                ended.closes += 1
                close()   # an unmatched `)` ends a `case` pattern (`a) rm x;;`) or a subshell
            index += 1
        else:
            buf.append(char)
            raw.append(char)
            has = True
            index += 1
    close()
    return result


# --- following the shell: variables, the working directory, the target a word names ---------------------------

def _canon(word, base):
    """`word` as a folded absolute path (joined to `base` when relative), or None when it cannot be told: a
    variable is still in it, or it is relative and there is no `base`."""
    path = word.replace("\\", "/")
    path = re.sub(r"^//[?.]/(unc/)?", lambda m: "//" if m.group(1) else "", path, flags=re.IGNORECASE).lower()
    if any(mark in path for mark in ("$", "%", _DYN, _PAREN, _TAINT)) or re.search(r"`[^`]*`", path):
        return None
    # Git Bash, Cygwin and WSL spell a drive as a folder: `/c/Users/...`, `/cygdrive/c/...`, `/mnt/c/...`
    path = re.sub(r"^/(?:(?:cygdrive|mnt)/)?([a-z])(?=/|$)", r"\1:", path)
    if not (path.startswith("/") or _DRIVE_RE.match(path)):
        if base is None:
            return None
        path = base + "/" + path
    path = _win32_names(path)
    unc = path.startswith("//") and not path.startswith("///")
    path = posixpath.normpath(re.sub(r"/{2,}", "/", path))
    if unc:
        path = "/" + path
    return path


def _win32_names(path):
    """`path` (forward slashes) with what Win32 strips from every component removed: trailing dots and spaces
    (`crew./config.json` is `crew/config.json`) and an NTFS directory stream (`crew::$INDEX_ALLOCATION`). A component
    of only dots (`.`, `..`) is a dot-segment, not a name, and stays."""
    names = path.split("/")
    parts = []
    for index, part in enumerate(names):
        if index < len(names) - 1:   # the last word's stream is `_hit`'s to strip, with the named ones (`f:s`)
            part = re.sub(r"::\$\w+$", "", part)
        parts.append(part.rstrip(" .") or part)
    return "/".join(parts)


# How much of one command the guard reads (crew 1.3.146). Each limit used to end the reading in silence, which let
# the write past: text nested more than `_DEPTH_LIMIT` commands deep was not read at all, and a command that took
# longer than the hook is given was killed by the dispatcher, which allows a guard it killed in a repo that is not
# armed. Past `_DEPTH_LIMIT` the text is now judged unread (`_unread`); past any other limit `_Unread` is raised and
# the two entry points (`_owner_command_refusal`, `_store_write`) refuse.
_DEPTH_LIMIT = 3
_COMMAND_LIMIT = 131072   # characters: the longest single argument Linux hands a program (MAX_ARG_STRLEN)
_STEP_LIMIT = 20000       # simple commands judged for one command, every reading and nesting level counted
_WORD_LIMIT = _COMMAND_LIMIT   # characters of one word after its variables are filled in (`A=$A$A` doubles it)


class _Unread(Exception):
    """The command is more than the guard reads in the time a hook has: the caller fails closed."""


class _Shell:  # pylint: disable=too-few-public-methods
    """What the command so far has set: variables, and the working directory (None when it cannot be told)."""

    def __init__(self, cwd):
        self.vars = {}
        self.cwd = _canon(cwd, None) if cwd else None
        self.hint = False        # the command names the owner's folder: a target it cannot resolve may be theirs
        self.cwd_lost = False    # a `cd` aimed somewhere that cannot be told: a relative target is then unknown
        self.variant = False     # judging an escape-stripped reading: a plain relative word is not judged by its tail
        self.cwd_taint = False   # that `cd` was aimed at something that spells pieces of the owner's path
        self.pipeline = []       # the words of the commands that feed this one through a pipe
        self.aliases = {}        # the aliases the command made: `Set-Alias w Set-Content`, `alias w=tee`
        self.dirs = []           # (kind, folder) frames: "dir" a `pushd` left, "sub" a subshell started in, "case"
        self.posh = False        # the command spells a cmdlet: its `( ... )` is an expression, no subshell
        self.once = None         # the folder to go back to after this one command (`env -C <folder> <command>`)
        self.store = None        # judging the confirm-config store rule: True when the store is spelled relatively
        self.deep = False        # the command spells the owner's folder anywhere, whole or in pieces (`_unread`)
        self.work = [0]          # the simple commands judged so far, shared with every `fork` (`_STEP_LIMIT`)

    def where(self):
        """The working directory as `back` restores it."""
        return self.cwd, self.cwd_lost, self.cwd_taint

    def back(self, state):
        """Stand in the folder `where` recorded; with nothing recorded (`popd` on an empty stack) the folder is one
        nobody can tell, so a relative target fails closed there in a command that names the owner's folder."""
        self.cwd, self.cwd_lost, self.cwd_taint = state or (None, True, self.cwd_taint)

    def popd(self):
        """Back to the folder the last `pushd` left (a subshell's start and a `case` are not what `popd` undoes)."""
        for index in range(len(self.dirs) - 1, -1, -1):
            if self.dirs[index][0] == "dir":
                return self.back(self.dirs.pop(index)[1])
        return self.back(None)

    def close(self):
        """A `)`: the end of the innermost subshell, whose `cd` and `pushd` end with it. Inside a `case` that has
        not reached its `esac`, and with no subshell open, it is a pattern's (`a) ls;;`) and nothing ends."""
        kinds = [kind for kind, _ in self.dirs]
        last = max((index for index, kind in enumerate(kinds) if kind != "dir"), default=-1)
        if last != -1 and kinds[last] == "sub":
            self.back(self.dirs[last][1])
            del self.dirs[last:]

    def esac(self):
        """The end of the innermost `case`: the `)` after it is a subshell's again."""
        for index in range(len(self.dirs) - 1, -1, -1):
            if self.dirs[index][0] == "case":
                del self.dirs[index:]
                return

    def fork(self):
        """A copy to judge one reading of a segment with, so the original's variables and folder stay as they are."""
        clone = _Shell(None)
        clone.vars, clone.cwd, clone.cwd_lost, clone.hint = dict(self.vars), self.cwd, self.cwd_lost, self.hint
        clone.cwd_taint, clone.pipeline, clone.aliases = self.cwd_taint, list(self.pipeline), dict(self.aliases)
        clone.dirs, clone.once, clone.store, clone.posh = list(self.dirs), self.once, self.store, self.posh
        clone.deep, clone.work = self.deep, self.work
        clone.variant = True
        return clone


def _expand(word, shell):
    """`word` with `~`, `$HOME`-style and the variables the command set substituted; an unknown variable stays.
    bash's `~+` is the working directory; `~name` and `~-` are folders the guard cannot tell (`_DYN`)."""
    home = os.path.expanduser("~")

    def sub(match):
        name = next(g for g in match.groups() if g)
        value = shell.vars.get(name.lower())
        if value is not None:
            return value
        return home if name.lower() in _HOME_VARS else match.group(0)

    word = _VAR_RE.sub(sub, word)
    if len(word) > _WORD_LIMIT:   # `A=$A$A; A=$A$A; ...` doubles the value with every command
        raise _Unread("a word grows past what a command line can hold")
    if word == "~" or word.startswith(("~/", "~\\")):
        word = home + word[1:]
    elif word.startswith(("~+/", "~+\\")):
        word = "." + word[2:]
    else:
        word = re.sub(r"^~[\w.-]+(?=[/\\])", _DYN, word)
    return word


def _braces(word, limit=64):
    """The words a bash brace expansion makes of `word` (`cc-{1,2}*.json`, `{a..c}`), at most `limit`; `word` itself
    when it has none. Every alternative is judged, because the shell writes every one."""
    match = re.search(r"\{([^{}]*)\}", word)
    if not match or limit < 2:
        return [word]
    inner = match.group(1)
    seq = re.fullmatch(r"(\w)\.\.(\w)", inner)
    if seq and len(seq.group(1)) == 1 and len(seq.group(2)) == 1:
        low, high = sorted((ord(seq.group(1)), ord(seq.group(2))))
        options = [chr(c) for c in range(low, min(high, low + 63) + 1)]
    elif "," in inner:
        options = inner.split(",")
    else:
        return [word]
    out = []
    for option in options:
        out.extend(_braces(word[:match.start()] + option + word[match.end():], limit // len(options) or 1))
    return out[:limit]


def _globify(component):
    """A path component as an fnmatch pattern: bash's `[^x]` is `[!x]`, and an 8.3 short name (`CREW~1`,
    `CONFIG~1.JSO`, `CONFIR~1`) stands for any name that starts with its stem, so it is read as a glob."""
    component = component.replace("[^", "[!")
    short = re.fullmatch(r"([^~*?\[]+)~\d+(?:\.[^.]*)?", component)
    return "*" + short.group(1).lstrip(".") + "*" if short else component


def _comp_match(pattern, name):
    """True when the path component `pattern` (a name or a glob) can be the component `name`."""
    return pattern == name or (re.search(r"[*?\[~]", pattern) is not None
                               and fnmatch.fnmatchcase(name, _globify(pattern)))


def _glob_match(pattern, target, under):
    """True when the component list `pattern` (globs allowed; `**` spans any number of folders) names `target`, or,
    with `under`, anything below it."""
    if not target:
        return not pattern or under or all(part == "**" for part in pattern)
    if not pattern:
        return False
    if pattern[0] == "**":
        return _glob_match(pattern[1:], target, under) or _glob_match(pattern, target[1:], under)
    return _comp_match(pattern[0], target[0]) and _glob_match(pattern[1:], target[1:], under)


def _owner_targets(mode):
    """The (component list, under) pairs a path must not name: the machine config, the confirm-config store and
    everything in it (`under`: receipts are `cc-<hex>.json`, but a temp or lock file there is as much the owner's),
    and, by `mode`, the folders a copy lands in. Spelled as the path is and as the file system resolves it."""
    pairs = []
    for spelled in (machine_config(), os.path.realpath(machine_config())):
        machine = _canon(spelled, None)
        if machine is None:
            continue
        folder = posixpath.dirname(machine)
        parent = posixpath.dirname(folder)
        found = [(machine, False), (folder + "/confirm-config", True)]
        if mode in ("dir", "destroy"):
            found += [(folder, False), (parent, False)]
        if mode == "destroy":
            found.append((posixpath.dirname(parent), False))
        pairs += [(path.split("/"), under) for path, under in found]
    return pairs


def _tail_hits(parts):
    """The word is not a path we can resolve (a variable is still in it, or it is relative to an unknown folder): it
    still names the owner's files when it ENDS the way they do, component by component."""
    tails = (("crew", "config.json"), (".claude", "crew", "config.json"), (".claude", "crew", "confirm-config"),
             ("confirm-config",))
    for tail in tails:
        for start in range(len(parts) - len(tail) + 1):
            window = parts[start:start + len(tail)]
            if all(_comp_match(w, t) for w, t in zip(window, tail)):
                if tail[-1] == "confirm-config" or start + len(tail) == len(parts):
                    return True
    return False


def _hit(word, shell, mode):
    """True when `word` names (or, for a glob, can match) the owner's files. `mode` "file" is the machine config
    and the confirm-config store; "dir" adds the folders a copy or an extraction lands in (`~/.claude/crew`,
    `~/.claude`); "destroy" adds home itself, for a delete or a move. The word is judged against the owner's REAL
    path (this machine's home), not a suffix of it, so a file elsewhere named `.claude/crew/config.json` is not the
    owner's; and every spelling Win32, the MSYS drive letters and a brace expansion give one path is read as that
    path."""
    forced = _PAREN in word   # inside a parenthesised expression: its value is whatever the expression gives
    tainted = word.startswith(_PAREN + _TAINT)   # ... and that expression spells pieces of the owner's path
    word = _expand(word.replace(_PAREN, "")[1 if tainted else 0:], shell)
    word = _UNREAD_VAR_RE.sub(_DYN, word)   # `${env:X}`, `$env:X`: a value nobody can tell, and no stream
    # an NTFS stream: `f::$DATA`, `f:s`
    word = re.sub(r"(?<=[^/\\:]):(?::\$\w+|[^/\\:]+)(?::\$\w+)?$", "", word)
    if not word or _IGNORED_TARGET_RE.match(word):
        return False
    if _PIPE_ITEM_RE.match(word):   # `Get-ChildItem <folder> | % { Set-Content $_.FullName x }`
        return _fed_hits(shell)
    if shell.store is not None:
        return any(_store_word(one, shell, forced) for one in _braces(word))
    return any(_hit_word(one, shell, mode, forced, tainted) for one in _braces(word))


def _names_store(word):
    """True when a component of the path `word` is (or, for a glob, can be) a `confirm-config` folder."""
    return any(_comp_match(part, "confirm-config") for part in _win32_names(_fold(word)).split("/"))


def _store_word(word, shell, forced=False):
    """`_hit` for the confirm-config store rule (crew 1.3.137, round 11), which is about ANY folder spelled
    `confirm-config/`, not only the owner's real one: True when `word` names such a folder or something in it, and,
    failing closed, when it is a target nobody can resolve -- a variable, a substitution, a parenthesised expression,
    a relative word with no known working directory -- or a relative word in a command that spells the store
    relatively (`ls confirm-config/ > x` stands beside the store, in the owner's folder). A target that resolves to
    a path elsewhere (`> /tmp/out.txt`, `cp <receipt> /tmp/`) is not a write to the store."""
    if forced or _names_store(word):
        return True
    if _SPAN_RE.search(word) or any(mark in word for mark in _MARKS + "$%"):
        return True
    path = _canon(word, shell.cwd)
    if path is not None and _names_store(path):   # a relative word, from a folder in the store
        return True
    if _canon(word, None) is not None:
        return False
    return bool(shell.store) or path is None


# PowerShell's name for what the pipeline hands a script block: `$_`, `$PSItem` (and a property of it)
_PIPE_ITEM_RE = re.compile(r"^\$(?:_|psitem)(?!\w)", re.IGNORECASE)
# the parts of a word the shell fills in and the guard cannot read: a substitution, a variable that is still unknown,
# a backtick (bash runs it, PowerShell escapes with it)
_SPAN_RE = re.compile(r"[\x03\x05]|\$\{[^}]*\}|\$env:\w+|\$\w+|\$[?!@*#$-]|%[A-Za-z_][^%\s/\\]*%|`[^`/\\]*`")


def _could_be_suffix(parts, mode):
    """True when the path components `parts` (globs allowed) could END one of the owner's paths, or lie below the
    confirm-config store, were an unknown folder put in front of them."""
    for target, under in _owner_targets(mode):
        for start in range(len(target)):
            if _glob_match(parts, target[start:], under):
                return True
    return False


def _suspect(word, shell, tainted=False):
    """True when a write target the guard cannot resolve may be the owner's (crew 1.3.137, round 10; narrowed from
    "the command mentions `.claude`"): the command names the owner's folder outside a read (`shell.hint`), the target
    or the `cd` before it was built from pieces of the owner's path (`_TAINT`), or the command stands in the owner's
    folder."""
    return bool(shell.hint or tainted or _TAINT in word or shell.cwd_taint or _in_owner_folder(shell))


def _dynamic_hit(word, shell, mode, forced, tainted=False):  # pylint: disable=too-many-return-statements
    """Fail closed (crew 1.3.137, round 9) on a write target the guard cannot resolve to one concrete path: a
    substitution, an unknown variable, a backtick, a word in a parenthesised expression. It names the owner's files
    when what is spelled of it can only be theirs (`~/.claude/crew/$X`), or when it could be theirs and it is
    `_suspect`. A target in a command that never names the owner's folder as something to write stays allowed."""
    if not (forced or _SPAN_RE.search(word)):
        return False
    suspect = _suspect(word, shell, tainted)
    text = word.replace("\\", "/")
    if forced or not _SPAN_RE.sub("", text).strip("/. "):   # nothing literal is left of it
        return suspect
    parts = ["**" if _SPAN_RE.fullmatch(part) else _SPAN_RE.sub("*", part) for part in text.split("/")]
    if parts[0] == "**":   # the unknown part is the whole front of the path
        rest = [_win32_names(part.lower()) for part in parts[1:] if part]
        while ".." in rest:   # `~root/../<user>/.claude/crew/config.json`: what follows the last `..` is the path
            rest = rest[rest.index("..") + 1:]
        return suspect and _could_be_suffix(rest, mode)
    path = _canon("/".join(parts), shell.cwd)
    if path is None:   # relative, from a folder a `cd` made unknown
        return suspect and shell.cwd_lost and _could_be_suffix([part.lower() for part in parts if part], mode)
    return any(_glob_match(path.split("/"), target, under) for target, under in _owner_targets(mode))


def _hit_word(word, shell, mode, forced=False, tainted=False):
    """`_hit` for one word with no brace expansion left."""
    path = _canon(word, shell.cwd)
    if path is None:
        # an escape-stripped reading of a plain relative word is often a garbled Windows path: only a word with a
        # variable in it is judged by its tail there
        return (((not shell.variant or _SPAN_RE.search(word))
                 and _tail_hits(_win32_names(word.replace("\\", "/").lower()).split("/")))
                or _dynamic_hit(word, shell, mode, forced, tainted)
                or _relative_unknown(word, shell, mode))
    spellings = [path]
    if not any(ch in path for ch in "*?[~"):
        real = _canon(os.path.realpath(path), None)   # a link, a junction or an 8.3 name that exists
        if real and real != path:
            spellings.append(real)
    targets = _owner_targets(mode)
    return any(_glob_match(spelled.split("/"), target, under)
               for spelled in spellings for target, under in targets) or bool(forced and _suspect(word, shell, tainted))


def _relative_unknown(word, shell, mode):
    """True when a relative `word` is judged from a folder a dynamic `cd` made unknown, in a command that names the
    owner's folder, and the word could end one of the owner's paths (`config.json`, not `out.txt`)."""
    if not (shell.cwd_lost and (shell.hint or shell.cwd_taint)) or _SPAN_RE.search(word):
        return False
    folded = word.replace("\\", "/").lower()
    if folded.startswith(("/", "~")) or _DRIVE_RE.match(folded):
        return False
    return _could_be_suffix([part for part in _win32_names(folded).split("/") if part not in ("", ".")], mode)


def _in_owner_folder(shell):
    """True when the working directory is the owner's folder itself or its receipts store. A folder further down
    (`~/.claude/crew/worktrees/<repo>/<lane>`, where crew keeps ordinary checkouts) is not the owner's files."""
    if shell.cwd is None:
        return False
    if shell.store is not None:
        return _names_store(shell.cwd)
    folder = posixpath.dirname(_fold(machine_config()))
    store = folder + "/confirm-config"
    return shell.cwd in (folder, store) or shell.cwd.startswith(store + "/")


# --- what each command does to the paths it is given -------------------------------------------------------------

def _operands(args):
    """The non-option words of `args`, plus the value of each `--opt=value` / `-Param:value` / `of=value`."""
    found = []
    for arg in args:
        if _OPTION_RE.match(arg):
            if "=" in arg and arg.startswith("--"):
                found.append(arg.split("=", 1)[1])
            elif ":" in arg and arg.startswith("-") and not arg.startswith("--"):
                found.append(arg.split(":", 1)[1])
        elif arg.startswith("of="):
            found.append(arg[3:])
        else:
            found.append(arg)
    return found


def _option_value(args, *names):
    """The word after the first of `names` in `args` (case-insensitively), or the value of `name=value`."""
    for name in names:
        fold = len(name) > 2   # `-o` and `-O` differ; `-OutFile` and `-outfile` do not
        for position, arg in enumerate(args):
            same, head = (arg.lower(), name.lower()) if fold else (arg, name)
            if same == head and position + 1 < len(args):
                return args[position + 1]
            if same.startswith(head + "=") or same.startswith(head + ":"):
                return arg[len(name) + 1:]
    return None


def _git_hits(args, shell):
    """True when a `git` call may rewrite the owner's folder: a work-tree-changing subcommand run in it, or aimed
    at it with `-C` / `--work-tree`."""
    where = _option_value(args, "-C", "--work-tree")
    sub = next((a for a in args if not a.startswith("-") and a != where), "")
    if sub == "archive":   # `git archive -o <file>`, `--output=<file>`: the archive it writes
        out = _option_value(args, "-o", "--output")
        return out is not None and _hit(out, shell, "file")
    if sub not in _GIT_WRITES:
        return False
    return _hit(where, shell, "dir") if where is not None else _in_owner_folder(shell)


# the short options of wget and of sort that take a value: in a bundle, what follows one is its value, not a flag
_WGET_VALUES = "oaeitTwUlARDIXBQOP"
_SORT_VALUES = "kSTto"


def _bundled_value(args, letter, values):
    """The value of the short option `letter` where it ends a bundle of flags (`wget -qO <file>`, `sort -uo <file>`,
    `-qO<file>`): the rest of the word, or the next word. None when no bundle carries it. A bundle in which an
    option that takes a value (`values`) comes first is that option and its value, and is not read."""
    for position, arg in enumerate(args):
        bundle = re.match(r"^-([A-Za-z0-9]*?)" + letter + r"(.*)$", arg, re.DOTALL)
        if bundle and not arg.startswith("--") and not any(flag in values for flag in bundle.group(1)):
            return bundle.group(2) or (args[position + 1] if position + 1 < len(args) else None)
    return None


def _download_hits(name, args, shell):
    """True when a downloader's output file (or, for wget -P, folder) is the owner's."""
    if name.startswith("wget"):
        out = _option_value(args, "-O", "--output-document") or _bundled_value(args, "O", _WGET_VALUES)
        if out is not None:
            return _hit(out, shell, "file")
        log = _option_value(args, "-o", "--output-file", "-a", "--append-output")   # the log it writes
        if log is not None and _hit(log, shell, "file"):
            return True
        folder = _option_value(args, "-P", "--directory-prefix") or _bundled_value(args, "P", _WGET_VALUES)
        return folder is not None and _hit(folder, shell, "dir")
    out = _option_value(args, "-o", "--output", "-OutFile")
    remote_name = "-O" in args or "--remote-name" in args
    if name.startswith("curl"):
        for position, arg in enumerate(args):   # a bundle of short flags: `-sSo file`, `-sSO`, `-sSofile`
            bundle = re.match(r"^-[sSLkvfiIgGJNZ#]*([oO])(.*)$", arg)
            if bundle and not arg.startswith("--"):
                if bundle.group(1) == "O":
                    remote_name = True
                elif out is None:
                    out = bundle.group(2) or (args[position + 1] if position + 1 < len(args) else None)
        outdir = _option_value(args, "--output-dir")
        lands_there = remote_name or (out is not None and not os.path.isabs(out))
        if outdir is not None and lands_there and _hit(outdir, shell, "dir"):
            return True
    if out is not None:
        return _hit(out, shell, "file")
    return name.startswith("curl") and remote_name and _in_owner_folder(shell)


# tar's short options that take a value (in a bundle each takes a word, in the order of the letters), and the long
# options that say what it does, as the mode letter of each
_TAR_VALUES = "fCbFgHIKLNTVX"
_TAR_MODES = {"create": "c", "extract": "x", "get": "x", "append": "r", "update": "u", "catenate": "A",
              "concatenate": "A", "delete": "D"}


def _tar_options(args):
    """`(the mode and flag letters, the archive file, the -C folder)` of a tar command line, however its options are
    bundled (crew 1.3.137, round 11): `-cf <file>`, `-czf <file>`, old style `cf <file>` and `xfC <file> <folder>`,
    `-xC <folder> -f <file>`, `-f<file>`, `--file=<file>`, `--directory <folder>`. A letter that takes a value takes
    the rest of a dashed bundle, or the next word."""
    letters, found, position = "", {}, 0
    while position < len(args):
        arg = args[position]
        position += 1
        if arg.startswith("--"):
            option, sign, value = arg[2:].partition("=")
            letters += _TAR_MODES.get(option, "")
            if option in ("file", "directory"):
                if not sign and position < len(args):
                    value, position = args[position], position + 1
                found["f" if option == "file" else "C"] = value
        elif (arg.startswith("-") and len(arg) > 1) or (position == 1 and arg[:1].isalpha()):
            dashed = arg.startswith("-")
            bundle = arg.lstrip("-")
            for index, letter in enumerate(bundle):
                if letter not in _TAR_VALUES:
                    letters += letter
                    continue
                rest = bundle[index + 1:] if dashed else ""
                value = rest or (args[position] if position < len(args) else "")
                position += 0 if rest else 1
                if letter in "fC":
                    found[letter] = value
                if rest:
                    break
    return letters, found.get("f"), found.get("C")


def _compress_destination(args):
    """Where `Compress-Archive` writes its archive: `-DestinationPath` (any abbreviation), or the second positional
    word (the first when `-Path`/`-LiteralPath` is named). None when it gives none."""
    plain, named, position = [], False, 0
    while position < len(args):
        arg = args[position]
        position += 1
        if arg.startswith("-") and len(arg) > 1:
            param, _, attached = arg[1:].partition(":")
            param = param.lower()
            if "destinationpath".startswith(param):
                return attached or (args[position] if position < len(args) else None)
            if any(switch.startswith(param) for switch in ("update", "force", "passthru", "whatif", "confirm",
                                                           "verbose", "debug")):
                continue
            named = named or "path".startswith(param) or "literalpath".startswith(param)
            position += 0 if attached else 1
            while position < len(args) and args[position - 1].endswith(","):   # `-Path a, b`: one list
                position += 1
        elif plain and plain[-1].endswith(","):
            plain[-1] += arg   # `a, b`: one list
        else:
            plain.append(arg)
    index = 0 if named else 1
    return plain[index] if len(plain) > index else None


def _archive_hits(name, args, shell):
    """True when an extraction lands in the owner's folder, or an archive is created as (appended to, updated as)
    one of its files."""
    if name in _SEVEN_ZIP:
        plain = [a for a in args if not a.startswith("-")]
        if plain and plain[0].lower() in ("a", "u", "d", "rn"):   # add, update, delete, rename: it is rewritten
            return len(plain) > 1 and _hit(plain[1], shell, "file")
    if name == "unzip" or name in _SEVEN_ZIP:
        # 7z x a.7z -o<dir>; for unzip `-o` is the overwrite switch (`-oq`), never a destination
        attached = None if name == "unzip" else next((a[2:] for a in args if a.startswith("-o") and len(a) > 2), None)
        where = _option_value(args, "-d") or attached
        return _hit(where, shell, "dir") if where else (name == "unzip" and _in_owner_folder(shell))
    if name == "expand-archive":
        where = _option_value(args, "-DestinationPath", "-Dest")
        return where is not None and _hit(where, shell, "dir")
    if name == "compress-archive":
        where = _compress_destination(args)
        return where is not None and _hit(where, shell, "file")
    letters, archive, folder = _tar_options(args)
    if "x" in letters:
        return _hit(folder, shell, "dir") if folder else _in_owner_folder(shell)
    if any(mode in letters for mode in "cruAD"):   # create, append, update, catenate, delete: the archive is written
        return bool(archive) and _hit(archive, shell, "file")
    return False


def _copy_hits(name, args, shell):
    """True when the destination of a copy is the owner's file or one of the folders it lands in."""
    dest = _option_value(args, "-t", "--target-directory", "-Destination")
    if dest is None:
        plain = [a for a in args if not _OPTION_RE.match(a)]
        if not plain:
            return False
        dest = plain[1] if name == "robocopy" and len(plain) > 1 else plain[-1]
    return _hit(dest, shell, "dir")


_SEVEN_ZIP = frozenset({"7z", "7za", "7zz", "7zr"})
_PS_CMDLETS = frozenset({"clear-content", "set-content", "add-content", "out-file", "new-item", "ni", "set-item",
                         "sc", "ac"})
# the switch parameters of the write cmdlets (own and common): they take no value, so the word after one is not theirs
_PS_SWITCHES = frozenset({"force", "nonewline", "append", "noclobber", "whatif", "confirm", "passthru", "wait",
                          "asbytestream", "usetransaction", "verbose", "debug", "recurse"})
_PS_PATH_PARAMS = frozenset({"path", "literalpath", "lp", "pspath", "filepath", "destination"})
# the value parameters, so an abbreviation (`-fo`, `-lit`) resolves the way PowerShell does: only when it is unique
_PS_VALUE_PARAMS = frozenset({"value", "encoding", "name", "itemtype", "stream", "inputobject", "include", "exclude",
                              "filter", "credential", "width", "target", "delimiter", "erroraction", "warningaction",
                              "informationaction", "errorvariable", "warningvariable", "informationvariable",
                              "outvariable", "outbuffer", "pipelinevariable", "ea", "wa", "infa", "ev", "wv", "iv",
                              "ov", "ob", "pv"})


def _ps_param(param):
    """The full name an abbreviated PowerShell parameter stands for, or `param` itself when it is exact, unknown
    or ambiguous (PowerShell refuses an ambiguous one, so nothing is written)."""
    known = _PS_SWITCHES | _PS_PATH_PARAMS | _PS_VALUE_PARAMS
    if param in known:
        return param
    matches = [name for name in known if name.startswith(param)]
    return matches[0] if len(matches) == 1 else param


def _ps_destinations(args):
    """The words a PowerShell write cmdlet WRITES TO: `-Path`/`-LiteralPath`/`-FilePath`/`-Destination`, the first
    positional word, and `-Name` joined to the path. `-Value`, `-InputObject` and the other parameter values are
    the text written, not where, and naming the owner's file there is not a write to it."""
    found, name, positional, position = [], None, 0, 0
    while position < len(args):
        arg = args[position]
        position += 1
        if arg.startswith("-") and len(arg) > 1 and not arg[1].isdigit():
            param, _, attached = arg[1:].partition(":")
            param = _ps_param(param.lower())
            if param in _PS_SWITCHES:
                continue
            value = attached or (args[position] if position < len(args) else "")
            position += 0 if attached else 1
            if param in _PS_PATH_PARAMS:
                found.append(value)
                positional += 1
            elif param == "name":
                name = value
        elif positional == 0:
            found.append(arg)
            positional = 1
    found = [piece for word in found for piece in ([word, *word.split(",")] if "," in word else [word])]
    if name is not None:
        found = [base.rstrip("/\\") + "/" + name for base in found] or [name]
    return found


# A `w` command in a sed or ex script (`w file`, `1w file`, `s/a/b/w file`, `w! file`): the file is the rest of the
# line.
_SCRIPT_WRITE_RE = re.compile(r"(?:^|[;{\s\d$!]|/[gpIiMme\d]*)w!?[ \t]*([^\n;}|]+)")
# what `find` hands each file to after `-exec`: a verb that writes or deletes, or a shell whose text is not read here
_FIND_EXEC = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
_FIND_NAMES = ("config.json", "cc-0a1b2c3d.json", "confirm-config", "crew", ".claude")
# the file an awk program redirects its output to: `print > "<file>"`, `print >> "<file>"` (inside a double-quoted
# program the quotes are escaped, `\"<file>\"`: the escape-stripped reading of the segment is the one that matches)
_AWK_WRITE_RE = re.compile(r">>?\s*\"([^\"]+)\"")


def _scripts(name, args):
    """The words of `args` that may be a sed or ex SCRIPT: for sed every word that is no option (its script, its
    `-e` values; a file name is read too and gives nothing); for an editor its `-c` values and `+command` words."""
    if name == "sed":
        return [arg for arg in args if not arg.startswith("-")]
    scripts = [args[position + 1] for position, arg in enumerate(args[:-1]) if re.fullmatch(r"-[A-Za-z]*c", arg)]
    return scripts + [arg for arg in args if arg.startswith("+")]


def _script_writes(name, args):
    """The files the `w` commands of a sed or ex script in `args` write."""
    return [found.group(1).strip() for script in _scripts(name, args)
            for found in _SCRIPT_WRITE_RE.finditer(script.lstrip("+"))]


def _write_verb(name, args):
    """True when `name` deletes, writes or copies onto the operands it is given (what `xargs` and `find -exec` hand
    it): a remover, a writer, a copier, an in-place `sed`/`perl`, or a shell, whose text is not read here."""
    inplace = any(re.match(r"^-[A-Za-z]*i", a) or a.startswith("--in-place") for a in args)
    return (name in _REMOVERS or name in _WRITERS or name in _COPIERS or name in _POSIX_SHELLS or name in _PWSH
            or (name in ("sed", "perl", "ruby") and inplace))


def _covers_owner(start, shell):
    """True when the folder `start` holds the owner's files, or lies inside their receipts store: what a `find`
    that starts there walks."""
    path = _canon(start, shell.cwd)
    if path is None or shell.store is not None:
        return _hit(start, shell, "destroy")
    parts = path.split("/")
    return any(_glob_match(parts, target[:len(parts)], False) or (under and _glob_match(parts, target, True))
               for target, under in _owner_targets("file"))


def _find_hits(args, shell):
    """True when a `find` deletes what it finds (`-delete`), or hands it to a write verb (`-exec rm {} +`), and
    what it finds may be the owner's files: it starts at a folder that holds them, with no `-name` that rules their
    names out."""
    args = [a.lstrip(_MARKS) for a in args]
    first = next((position for position, a in enumerate(args) if a.startswith("-")), len(args))
    starts, tests = args[:first], args[first:]
    hands_on = any(test in _FIND_EXEC and position + 1 < len(tests)
                   and _write_verb(_command_name(tests[position + 1]), tests[position + 2:])
                   for position, test in enumerate(tests))
    if "-delete" not in tests and not hands_on:
        return False
    names = [tests[position + 1].lower() for position, test in enumerate(tests[:-1]) if test in ("-name", "-iname")]
    if shell.store is None and names and not any(name.startswith("cc-") or fnmatch.fnmatchcase(sample, _globify(name))
                                                 for name in names for sample in _FIND_NAMES):
        return False   # (the store rule reads on: any name may be a file of a store that is not the owner's own)
    return any(_covers_owner(start, shell) for start in (starts or ["."]))


def _fed_hits(shell):
    """True when what a pipeline hands the command may be the owner's files: a word of the commands before it names
    them (`Get-ChildItem <it> |`, `echo <it> |`, `find <folder> |`), or the command stands in the owner's folder
    (`ls | xargs rm`). What the pipe really carries is not known, so the names said before it stand for it."""
    return _in_owner_folder(shell) or any(
        _hit(word, shell, "destroy") for word in shell.pipeline
        if word and not _OPTION_RE.match(word) and not _PIPE_ITEM_RE.match(word.lstrip(_MARKS)))


def _piped_hits(name, args, shell):
    """True when a PowerShell cmdlet with no path of its own writes or deletes what the pipeline hands it
    (`Get-ChildItem <owner file> | Remove-Item`, `Get-Item <it> | Set-Content -Value x`)."""
    if name not in _PIPE_BOUND:
        return False
    if name in _PS_CMDLETS:
        own = _ps_destinations(args)
    else:   # where a move or a rename puts the item is not the item: `Get-Item <f> | Move-Item -Destination out.txt`
        there = (_option_value(args, "-Destination"), _option_value(args, "-NewName"))
        own = [w for w in args if w and not _OPTION_RE.match(w) and w not in there]
    return not own and _fed_hits(shell)


def _verb_hits(name, args, shell):  # pylint: disable=too-many-return-statements,too-many-branches
    """True when the command `name args` writes the owner's files (what it is aimed at, per verb)."""
    lowered = [a.lower() for a in args]
    operands = [w for w in _operands(args) if w]
    if name in _REMOVERS:
        return any(_hit(w, shell, "destroy") for w in operands)
    if name == "fsutil":   # `fsutil hardlink create <new link> <existing file>`, `fsutil file createNew <file> <size>`
        return (lowered[:2] in (["hardlink", "create"], ["file", "createnew"]) and len(operands) > 2
                and _hit(operands[2], shell, "file"))
    if name == "sort":   # `sort -o <file>`, `-uo <file>`, `-o<file>`, `--output=<file>` (and its abbreviations)
        out = _bundled_value(args, "o", _SORT_VALUES)
        for position, arg in enumerate(args):
            long = re.fullmatch(r"--o(?:u(?:t(?:p(?:ut?)?)?)?)?(?:=(.*))?", arg, re.DOTALL)
            if long and out is None:
                out = long.group(1) if long.group(1) is not None else "".join(args[position + 1:position + 2])
        return bool(out) and _hit(out, shell, "file")
    if name in _WRITERS:
        mode = "dir" if name == "mklink" or any(x in lowered for x in ("junction", "symboliclink", "hardlink")) \
            else "file"
        written = _ps_destinations(args) if name in _PS_CMDLETS and mode == "file" else operands
        return any(_hit(w, shell, mode) for w in written if w)
    if name in _COPIERS:
        return _copy_hits(name, args, shell) or (name == "ln" and any(_hit(w, shell, "file") for w in operands))
    if name in ("sed", "perl", "ruby", "awk", "gawk"):
        if name == "sed" and any(_hit(w, shell, "file") for w in _script_writes(name, args)):
            return True   # `sed -n "w <file>"`: the script's own write command
        if name in ("awk", "gawk") and any(_hit(found.group(1), shell, "file")
                                           for a in args for found in _AWK_WRITE_RE.finditer(a)):
            return True   # `awk '{print > "<file>"}'`
        inplace = any(re.match(r"^-[A-Za-z]*i", a) or a.startswith("--in-place") for a in args) or (
            name in ("awk", "gawk") and "inplace" in lowered)
        return inplace and any(_hit(w, shell, "file") for w in operands)
    if name in _EDITORS:
        scripts = _scripts(name, args)
        return any(_hit(w, shell, "file") for w in [w for w in operands if w not in scripts]
                   + _script_writes(name, args))
    if name == "find":
        return _find_hits(args, shell)
    if name == "dd":
        return any(a.startswith("of=") and _hit(a[3:], shell, "file") for a in args)
    if name == "patch":
        if any(a in ("-C", "--check", "--dry-run") for a in args):   # GNU patch: report what would apply, write nothing
            return False
        where = _option_value(args, "-d", "--directory")
        return any(_hit(w, shell, "file") for w in operands) or (
            _hit(where, shell, "dir") if where else _in_owner_folder(shell))
    if name in ("curl", "wget", "iwr", "irm", "invoke-webrequest", "invoke-restmethod"):
        return _download_hits(name, args, shell)
    if name in ("tar", "bsdtar", "unzip", "expand-archive", "compress-archive") or name in _SEVEN_ZIP:
        return _archive_hits(name, args, shell)
    return name == "git" and _git_hits(args, shell)


def _assign(raw, shell):
    """Record one `NAME=value` word; True when `raw` was one."""
    match = _ASSIGN_RE.match(raw)
    if not match:
        return False
    shell.vars[match.group(1).lower()] = _expand(match.group(2), shell)
    return True


# the words that only introduce a command: `do rm x`, `then rm x`, `if rm x`, `try { rm x }` (crew 1.3.137)
_CONTROL = frozenset({"do", "then", "else", "elif", "if", "while", "until", "!", "{", "try", "finally"})
_PS_ASSIGN_RE = re.compile(r"^\$(?:\w+:)?(\w+)(=?)(.*)$", re.DOTALL)


def _ps_assignment(words):
    """`(name, the words of the right-hand side)` when `words` start a PowerShell assignment (`$p = ...`, `$p=...`,
    `$env:P = ...`), else None."""
    match = _PS_ASSIGN_RE.match(words[0])
    if not match:
        return None
    name, sign, rest = match.groups()
    if sign:
        return name, ([rest] if rest else []) + words[1:]
    if rest or len(words) < 2 or not words[1].startswith("="):
        return None
    return name, ([words[1][1:]] if len(words[1]) > 1 else []) + words[2:]


def _assigned(rhs, shell):
    """The value a PowerShell assignment gives its variable: the one literal word, or, for anything that is not one
    plain word (a command, a concatenation, a parenthesised expression: `Join-Path $HOME ".claude/crew/config.json"`,
    `$HOME + "\\.claude\\crew\\config.json"`), a mark that the value cannot be told -- `_TAINT` when the expression
    spells pieces of the owner's path, so a write aimed at the variable fails closed."""
    if len(rhs) == 1:
        return _expand(rhs[0], shell)
    text = " ".join(_expand(word, shell) for word in rhs)   # a variable in it may carry a taint of its own
    return _TAINT if _TAINT in text or _plausible(text) else _DYN


def _after_options(words, values=()):
    """`words` past the options at their front; an option in `values` takes the next word with it."""
    position = 0
    while position < len(words) and words[position].startswith("-") and len(words[position]) > 1:
        position += 2 if words[position] in values else 1
    return words[position:]


def _leading(words, shell):
    """`words` without the assignments, wrappers, declarations and control words before the command itself
    (recording the variables they set); a `{` glued to the command (`{Set-Content`) is cut off it. The right-hand
    side of a PowerShell assignment stays: it is a command too (`$r = Set-Content <file> x` runs it)."""
    words = list(words)
    while words:
        head = words[0]
        lowered = head.lower()
        assignment = _ps_assignment(words)
        if _assign(head, shell):
            words.pop(0)
        elif assignment:
            shell.vars[assignment[0].lower()] = _assigned(assignment[1], shell)
            words = assignment[1]
        elif lowered in _CONTROL:
            words.pop(0)
        elif head.startswith("{") and len(head) > 1:
            words[0] = head[1:]
        elif lowered in _DECLARERS:
            words.pop(0)
            while words and (words[0].startswith("-") or _assign(words[0], shell)):
                words.pop(0)
        elif _command_name(head) in _OWNER_WRAPPERS:
            wrapper = _command_name(words.pop(0))
            values = _OWNER_WRAPPER_VALUES.get(wrapper, ())
            while words and (words[0].startswith("-") or _ASSIGN_RE.match(words[0])):
                if _ASSIGN_RE.match(words[0]):
                    _assign(words[0], shell)
                option = words.pop(0)
                folder = option[8:] if option.startswith("--chdir=") else None
                if option in values and words:
                    folder = words.pop(0)   # `nice -n 10 tee`, `timeout -s KILL 5 tee`: the option's value
                if wrapper == "env" and folder is not None and option.startswith(("-C", "--chdir")):
                    _stand_in(_expand(folder, shell), shell, once=True)   # `env -C <folder> tee config.json`
            if wrapper == "timeout" and words:
                words.pop(0)   # the duration
        else:
            break
    return words


def _stand_in(aimed, shell, once=False):
    """Move `shell` into the folder `aimed` as a `cd` does; with `once`, for the one command being read."""
    if once and shell.once is None:
        shell.once = shell.where()
    shell.cwd = _canon(aimed, shell.cwd)
    shell.cwd_lost = shell.cwd_lost or shell.cwd is None
    shell.cwd_taint = shell.cwd is None and (shell.cwd_taint or _TAINT in aimed)


def _command_name(word):
    base = os.path.basename(word.replace("\\", "/")).lower()
    return base[:-4] if base.endswith(".exe") else base


def _nested(name, args, shell, depth):
    """The refusal of a command a shell or interpreter is handed as text (`bash -c`, `pwsh -Command`, `cmd /c`,
    `eval`, `python -c`), or None."""
    lowered = [a.lower() for a in args]
    if name in _CODE_RUNNERS or name in _PWSH:
        for position, arg in enumerate(args):
            if arg in _CODE_FLAGS or (name in _PWSH and lowered[position] in ("-c", "-command")):
                code = " ".join(args[position + 1:]) if name in _PWSH else " ".join(args[position + 1:position + 2])
                refusal = _code_refusal(code) if code else None
                if not refusal and code and name in _PWSH:
                    refusal = _child(code, shell, depth)
                if refusal:
                    return refusal
                break
    if name in _POSIX_SHELLS:
        for position, arg in enumerate(args):
            if re.match(r"^-[a-z]*c$", arg) and position + 1 < len(args):
                return _child(args[position + 1], shell, depth)
    if name in ("eval", "iex", "invoke-expression"):   # `iex "..."` runs its text as `eval` does (crew 1.3.137)
        plain = [a.lstrip(_MARKS) for a in args if a.lower() != "-command"]
        return _analyze(" ".join(plain), shell, depth + 1)
    if name.startswith("[scriptblock]::create"):   # `$sb = [scriptblock]::Create("<command>")`
        return _analyze(" ".join(a.lstrip(_MARKS) for a in args), shell, depth + 1)
    if name == "trap":   # `trap "<command>" EXIT`
        plain = _after_options(args)
        return _analyze(plain[0], shell, depth + 1) if plain else None
    if name in ("start-process", "saps"):   # the program and its `-ArgumentList`, read as one command line
        plain = [a.lstrip(_MARKS).replace(",", " ") for a in args if not re.fullmatch(r"-[A-Za-z]+", a)]
        return _analyze(" ".join(plain), shell, depth + 1)   # the shell it starts is read as a child there
    if name == "cmd":
        for position, arg in enumerate(lowered):
            if arg in ("/c", "/k", "/r"):
                return _child(" ".join(args[position + 1:]), shell, depth)
    if name == "xargs":
        return _xargs_refusal(_after_options(args, _XARGS_VALUES), shell, depth)
    if name == "find":   # `find . -exec cp x <owner file> ;`: the command it runs is judged as written
        for position, arg in enumerate(args):
            if arg in _FIND_EXEC:
                refusal = _exec_refusal(args[position + 1:], shell, depth)
                if refusal:
                    return refusal
    return None


def _exec_refusal(words, shell, depth):
    """Why the command `find -exec` runs (`words`, up to its `;` or `+`) writes the owner's files, or None. `{}` is
    whatever find found, which `_find_hits` judges; here the words spelled out are (`cp x <owner file>`, `sh -c
    "..."`)."""
    inner = _Segment()
    for word in words:
        if word.lstrip(_MARKS) in (";", "\\;", "\\", "+"):
            break
        inner.words.append(word)
    inner.raws = list(inner.words)
    return _deeper(inner, shell, depth) if inner.words else None


def _alias(name, args, shell):
    """Record the alias a command makes: PowerShell's `Set-Alias w Set-Content` (`New-Alias`, `sal`, `nal`, with or
    without `-Name`/`-Value`) and bash's `alias w=tee`."""
    if name == "alias":
        for match in filter(None, map(_ASSIGN_RE.match, args)):
            shell.aliases[match.group(1).lower()] = match.group(2)
        return
    plain = [a for a in args if not a.startswith("-")]
    if len(plain) >= 2:
        shell.aliases[plain[0].lower()] = plain[1]


def _bind(name, args, seg, shell):
    """Record the variable a loop fills: `for f in <one word>` is that word; `for f in <several>` and `read f` (fed
    by a pipeline or a here-string) are values nobody can tell -- `_TAINT` when what feeds them spells pieces of the
    owner's path (`ls <owner folder>/*.json | while read f; do echo x > "$f"; done`)."""
    if name == "for":
        items = args[2:]
        if len(items) == 1:
            shell.vars[args[0].lower()] = items[0]
            return
        fed, names = " ".join(items), args[:1]
    else:
        fed, names = " ".join(shell.pipeline + seg.bodies), args
    for each in names:
        shell.vars[each.lower()] = _TAINT if _TAINT in fed or _plausible(fed) else _DYN


def _handed(name, shell, depth):
    """The refusal of a script a pipeline hands a shell (`echo "<command>" | bash`, `"<command>" | iex`), or None:
    every quoted word said before the pipe that holds a space is read as the commands it may be."""
    if not (name in _POSIX_SHELLS or name in _PWSH or name in ("iex", "invoke-expression")):
        return None
    for word in shell.pipeline:
        if re.search(r"\s", word):
            refusal = _analyze(word.lstrip(_MARKS), shell, depth + 1)
            if refusal:
                return refusal
    return None


def _xargs_refusal(words, shell, depth):
    """Why `xargs <command>` writes the owner's files, or None: the command is judged as written (`xargs tee <owner
    file>`), and a write verb is also judged against what the pipeline hands it (`echo <it> | xargs rm`,
    `ls | xargs rm` in the owner's folder)."""
    if not words:
        return None
    inner = _Segment()
    inner.words = inner.raws = list(words)
    refusal = _segment_refusal(inner, shell, depth + 1)
    if refusal:
        return refusal
    name = _command_name(words[0])
    if _write_verb(name, words[1:]) and _fed_hits(shell):
        return f"{OWNER_REASON}: `xargs {name}` is handed them"
    return None


_DOTNET_CALL_RE = re.compile(r"^\[(?:system\.)?io\.file\]::(\w+)\s*\(?(.*)$",
                             re.IGNORECASE | re.DOTALL)
# the arguments of a `[IO.File]::Member(...)` that are written to, by position (a destination, not the text written)
_DOTNET_DESTINATIONS = (("openread", ()), ("opentext", ()), ("copy", (1,)), ("move", (0, 1)),
                        ("replace", (0, 1, 2)), ("write", (0,)), ("append", (0,)), ("create", (0,)),
                        ("delete", (0,)), ("openwrite", (0,)), ("setattributes", (0,)), ("open", (0,)))


_WRITE_MODE_RE = re.compile(r"\b(?:create|createnew|append|truncate|write|readwrite|openorcreate)\b", re.IGNORECASE)
_DOTNET_ARGUMENT_LIMIT = 4   # the last destination is argument 3 (`Replace`); the rest of a long list is never read


def _dotnet_arguments(text):
    """The top-level comma-separated arguments in `text` (the part of a call after its opening parenthesis), as
    `(text without quote marks, True when the whole argument is one quoted literal)`. A comma inside a quoted
    part, or inside brackets, does not split. Only the first few are split out: no later one is ever read."""
    found, depth, current, quoted = [], 0, "", False
    for char in text:
        if char == _QUOTE_OPEN:
            quoted = True
        elif char == _QUOTE_CLOSE:
            quoted = False
        elif not quoted and char in "([{":
            depth += 1
        elif not quoted and char in ")]}":
            depth -= 1
            if depth < 0:
                break
        if char == "," and depth == 0 and not quoted:
            found.append(current)
            current = ""
            if len(found) >= _DOTNET_ARGUMENT_LIMIT:
                return [_dotnet_argument(each) for each in found]
        else:
            current += char
    return [_dotnet_argument(each) for each in [*found, current]]


def _dotnet_argument(raw):
    """`(plain text, whether it was one quoted literal)` for an argument spelled with quote marks."""
    stripped = raw.strip()
    literal = (stripped.startswith(_QUOTE_OPEN) and stripped.endswith(_QUOTE_CLOSE)
               and stripped.count(_QUOTE_OPEN) == 1)
    return stripped.replace(_QUOTE_OPEN, "").replace(_QUOTE_CLOSE, ""), literal


def _dotnet_refusal(raw, shell):
    """Why a statement-initial `[IO.File]::Member(...)` (`raw`: the words with quote marks) writes the owner's
    files, or None. Only a WRITE member counts (`ReadAllText`, `Exists` read), and only its destination argument:
    the owner's file as the text written is not a write to it. `Open` counts when a later argument names a write
    mode (Create, CreateNew, Append, Truncate, Write, ReadWrite). A destination that is an expression, not a
    literal path, falls back to naming the owner."""
    match = _DOTNET_CALL_RE.match(raw)
    if not match:
        return None
    member = match.group(1).lower()
    positions = next((where for prefix, where in _DOTNET_DESTINATIONS if member.startswith(prefix)), None)
    if positions is None:
        return None
    arguments = _dotnet_arguments(match.group(2))   # the shell word splitter has dropped the parentheses
    if member == "open" and not any(_WRITE_MODE_RE.search(text) for text, _ in arguments[1:]):
        return None
    for position in positions:
        word, literal = arguments[position] if position < len(arguments) else ("", False)
        word = word if literal else word.rstrip(")").strip("'\"")
        if not literal and re.search(r"[(\[{\s]", word):
            return _code_refusal(raw.replace(_QUOTE_OPEN, "").replace(_QUOTE_CLOSE, ""))
        if _hit(word, shell, "file"):
            return f"{OWNER_REASON}: a .NET file write is aimed at them"
    return None


def _split_block_end(words):
    """`(words up to the one that closes a script block, the words after it)`: a `}` word, or a word ending in an
    unmatched `}`, ends the command (`& {Set-Content x} ...`); a balanced `${x}` does not."""
    for position, word in enumerate(words):
        if word == "}":
            return words[:position], words[position + 1:]
        if word.endswith("}") and word.count("}") > word.count("{"):
            return [*words[:position], word[:-1]], words[position + 1:]
    return list(words), []


def _unbrace(word):
    """`word` without the `}` that closes a script block it ends (`& {Set-Content x}`); a balanced `${x}` stays."""
    return word[:-1] if word.endswith("}") and word.count("}") > word.count("{") else word


def _tainted(seg):
    """A copy of `seg` with every word of its parenthesised expressions marked `_TAINT`."""
    copy = _Segment()
    copy.subs, copy.bodies, copy.raws, copy.piped = seg.subs, seg.bodies, seg.raws, seg.piped
    copy.words, copy.targets = ([_PAREN + _TAINT + word.lstrip(_MARKS) if _PAREN in word else word for word in words]
                                for words in (seg.words, seg.targets))
    return copy


def _segment_refusal(seg, shell, depth):  # pylint: disable=too-many-return-statements,too-many-branches
    """Why one simple command writes the owner's files, or None."""
    shell.work[0] += 1
    if shell.work[0] > _STEP_LIMIT:
        raise _Unread(f"it holds more than {_STEP_LIMIT} commands to judge")
    if any(_PAREN in word and _TAINT in _expand(word, shell) for word in seg.words + seg.targets):
        seg = _tainted(seg)   # `(Join-Path $d "config.json")` where `$d` was built from pieces of the owner's path
    for target in seg.targets:
        if _hit(_unbrace(target), shell, "file"):
            return f"{OWNER_REASON}: a redirect aims at them"
    spelled = _braces(seg.words[0]) if seg.words else []
    if len(spelled) > 1:   # a brace expansion where the command stands: `{rm,x}` is the command `rm x`
        spelled += seg.words[1:]
    words, after = _split_block_end(_leading(spelled if len(spelled) > 1 else seg.words, shell))
    if after:   # `try { rm x } catch { ... }`: what follows the block's `}` is a command of its own
        tail = _Segment()
        tail.words = tail.raws = after
        refusal = _deeper(tail, shell, depth)
        if refusal:
            return refusal
    if not words:
        return None
    for position in range(1, len(words)):   # a script block: `foreach (...) { Set-Content x }`, `& { rm x }`
        word = words[position].lstrip(_MARKS)
        if word.startswith("{"):
            inner = _Segment()
            inner.words = ([word[1:]] if len(word) > 1 else []) + words[position + 1:]
            inner.raws = list(inner.words)
            refusal = _deeper(inner, shell, depth)
            if refusal:
                return refusal
    if words[0].lower().startswith(("[io.file]::", "[system.io.file]::")):   # a .NET write with the path spelled out
        return _dotnet_refusal(" ".join(seg.raws[len(seg.words) - len(words):]), shell)
    name = _command_name(_expand(words[0], shell))
    args = [_expand(w, shell) for w in words[1:]]
    if name.startswith("-"):   # the rest of a `find` after an escaped `;`: `... -exec true \\; -exec rm <file> \\;`
        return _nested("find", [name] + args, shell, depth)
    stands = shell.aliases[name].split() if name in shell.aliases else None
    if stands and _command_name(_expand(stands[0], shell)) == name:
        args = [_expand(w, shell) for w in stands[1:]] + args   # `alias ls='ls --color'`: a name is expanded once
    elif stands is not None:   # an alias the command made is the command it stands for
        named = _Segment()
        named.words = named.raws = stands + list(words[1:])
        return _deeper(named, shell, depth)
    if name in ("alias", "set-alias", "new-alias", "sal", "nal"):
        _alias(name, args, shell)
        return None
    if name == "read" or (name == "for" and args[1:2] == ["in"]):
        _bind(name, args, seg, shell)
        return None
    if name in _POPD:   # back to the folder the matching `pushd` left
        shell.popd()
        return None
    if name in _CD:
        plain = [a for a in args if not a.startswith("-")]
        if len(plain) > 1 and plain[0].lower() == "/d":   # cmd's `cd /d <folder>`: the switch is not the folder
            plain = plain[1:]
        if name in _PUSHD:
            shell.dirs.append(("dir", shell.where()))
        _stand_in(plain[0] if plain else os.path.expanduser("~"), shell)
        return None
    for body in seg.bodies:
        if name in _CODE_RUNNERS or name in _PWSH:
            refusal = _code_refusal(body)
            if refusal:
                return refusal
        if name in _POSIX_SHELLS or name in _PWSH:
            refusal = _child(body, shell, depth)
            if refusal:
                return refusal
    refusal = _nested(name, args, shell, depth) or _handed(name, shell, depth)
    if refusal:
        return refusal
    if _verb_hits(name, args, shell):
        return f"{OWNER_REASON}: `{name}` is aimed at them"
    if shell.store is not None and _STORE_BLIND_RE.fullmatch(name) and any(_names_store(a) for a in args):
        return f"{OWNER_REASON}: `{name}` is given a path in the store"
    if _piped_hits(name, args, shell):
        return f"{OWNER_REASON}: `{name}` is handed them by the pipeline"
    return None


# What an unread text holds when the shell, not the guard, decides what it names: a substitution, a variable, a
# backtick (`_SPAN_RE`), a wildcard, or one of the guard's own markers for those.
_UNREAD_RE = re.compile(_SPAN_RE.pattern + r"|\$\(|[*?\[\x03-\x05]")


def _unread(text, shell):
    """Why `text`, nested more than `_DEPTH_LIMIT` commands deep and so never read, is refused, or None (crew
    1.3.146). It used to pass whatever it held: `bash -c` four deep around a redirect to the machine config, five
    `$(...)`, a sixth script block, a chain of aliases. Unread text passes only when it cannot be the owner's: the
    command spells nothing of their folder (`shell.deep`, `shell.hint`), stands nowhere near it, and the text is
    plain words, with no wildcard and nothing the shell fills in. A read counts too: nobody read it to tell."""
    if not text.strip():
        return None
    named = shell.deep or shell.hint or _plausible(text)
    near = shell.store is not None or shell.cwd_taint or _in_owner_folder(shell)
    if named or near or _UNREAD_RE.search(text):
        return (f"{OWNER_REASON}: what it nests more than {_DEPTH_LIMIT} commands deep is not read, and it "
                "names their folder or holds a part only the shell can fill in")
    return None


def _deeper(seg, shell, depth):
    """`_segment_refusal` for a command found inside another (a script block, what follows one, an alias, a `find
    -exec`), one level down; past `_DEPTH_LIMIT` it is `_unread`."""
    if depth > _DEPTH_LIMIT:
        return _unread(" ".join(seg.words), shell)
    return _segment_refusal(seg, shell, depth + 1)


def _analyze(text, shell, depth=0):
    """The first refusal in `text` read as shell commands, or None. `shell.pipeline` holds, for a command a `|`
    feeds, the words of the commands before it; the caller's is put back when `text` has been read."""
    if not isinstance(text, str):
        return None
    if depth > _DEPTH_LIMIT:
        return _unread(text, shell)
    outer = shell.pipeline
    try:
        return _analyze_segments(text, shell, depth)
    finally:
        shell.pipeline = outer


def _child(text, shell, depth):
    """`_analyze` for the text a child process or a subshell runs (`bash -c "..."`, `pwsh -Command`, `cmd /c`, a
    `$(...)`, a heredoc fed to a shell): it starts in the folder the command stands in, and its own `cd` ends with
    it (crew 1.3.137). `eval` and `iex` run in the shell itself, so they are read by `_analyze` and their `cd`
    stays."""
    before, stack, once = shell.where(), list(shell.dirs), shell.once
    shell.once = None   # `env -C <folder> sh -c "..."`: the folder is the child's for all of its commands
    try:
        return _analyze(text, shell, depth + 1)
    finally:
        shell.back(before)
        shell.dirs, shell.once = stack, once


def _analyze_segments(text, shell, depth):
    """`_analyze`, one segment after the other."""
    for seg in _segments(text):
        if not seg.piped:
            shell.pipeline = []
        if not shell.posh:   # a subshell starts: its `cd` ends with it (PowerShell's `( ... )` runs in the shell)
            shell.dirs += [("sub", shell.where())] * seg.opens
        for sub in seg.subs:
            refusal = _child(sub, shell, depth)
            if refusal:
                return refusal
        for variant in _escape_variants(seg):
            refusal = _segment_refusal(variant, shell.fork(), depth)
            if refusal:
                return refusal
        refusal = _segment_refusal(seg, shell, depth)
        if refusal:
            return refusal
        if shell.once is not None:   # `env -C <folder> <command>` stood there for that command only
            shell.back(shell.once)
            shell.once = None
        plain = [word.lstrip(_MARKS).lower() for word in seg.words]
        if any(word == "case" and plain[position + 2:position + 3] == ["in"] for position, word in enumerate(plain)):
            shell.dirs.append(("case", None))   # `case <word> in a) ...`: each `)` up to `esac` is a pattern's
        if "esac" in plain:
            shell.esac()
        for _ in range(seg.closes):
            shell.close()
        shell.pipeline = shell.pipeline + [_expand(word, shell) for word in seg.words]
    return None


# Each shell strips its own escape character before it uses a word: bash a backslash, PowerShell a backtick, cmd a
# caret. `confi\g.json`, ``confi`g.json`` and `confi^g.json` are `config.json`. The splitter cannot tell which shell a
# word is for (a backslash is also a Windows separator), so every segment with such a character is judged again as
# each shell would read it, and a hit in any reading refuses.
_ESCAPES = (re.compile(r"\\(.)", re.DOTALL), re.compile(r"`(.)", re.DOTALL), re.compile(r"\^(.)", re.DOTALL))
_ESCAPE_READINGS = ((0,), (1,), (2,), (0, 1, 2))


def _unescape(word, reading):
    """`word` with the escape characters of the shells in `reading` (indexes into `_ESCAPES`) taken out."""
    for which in reading:
        word = _ESCAPES[which].sub(r"\1", word)
    return word


def _escape_variants(seg):
    """The `_Segment`s `seg` is when a shell strips its escape characters (none when there is nothing to strip)."""
    seen = {(tuple(seg.words), tuple(seg.targets))}
    found = []
    for reading in _ESCAPE_READINGS:
        words = [_unescape(w, reading) for w in seg.words]
        targets = [_unescape(t, reading) for t in seg.targets]
        if (tuple(words), tuple(targets)) in seen:
            continue
        seen.add((tuple(words), tuple(targets)))
        variant = _Segment()
        variant.words, variant.targets = words, targets
        variant.raws = [_unescape(r, reading) for r in seg.raws]
        found.append(variant)
    return found


def _said_words(words):
    """`(the words of one simple command that could aim a write, True when the command only reads)`. What a
    read-only program is given (`cat <file>`, `Get-Content <file>`) and what a copy reads from (`cp <file>
    "$BACKUP"`) are reads: they are left out."""
    lead = _leading(words, _Shell(None))
    if not lead:
        return list(words), False
    before = list(words[:len(words) - len(lead)])
    name = _command_name(lead[0].lstrip(_MARKS))
    if name in _READERS:
        return before, True
    if name in _COPIERS and name != "robocopy" and _option_value(lead[1:], "-t", "--target-directory",
                                                                 "-Destination") is None:
        plain = [position for position, word in enumerate(lead) if position and not _OPTION_RE.match(word)]
        return before + [word for position, word in enumerate(lead) if position not in plain[:-1]], False
    return list(words), False


def _command_text(text, depth=0):
    """What the command SAYS it may write: the words (`_said_words`), redirect targets, `$(...)` bodies and
    heredocs of `text` as one string, without its comments. A quoted word that holds a command of its own (`bash -c
    "cat <file>"`) is read as one. A heredoc a read-only program is fed (`cat <<EOF > "$OUT"`) is text it copies,
    not something it says."""
    if depth > 3:
        return ""
    pieces = []
    for seg in _segments(text):
        words, reads = _said_words(seg.words)
        pieces += [_command_text(word, depth + 1) if re.search(r"\s", word) else word for word in words]
        pieces += seg.targets + ([] if reads else seg.bodies)
        pieces += [_command_text(sub, depth + 1) for sub in seg.subs]
    return "\n".join(pieces)


def _owner_hint(command):
    """True when the command names the owner's folder as something it may write (crew 1.3.137, round 10):
    `.claude/crew`, the confirm-config store or `crew/config.json` (`_HINT_RES`), spelled plainly or with its escape
    characters, quotes and markers taken out, anywhere but in a read (`_said_words`). `.claude` alone, crew's
    `worktrees/` folder, and the owner's file handed to `cat` do not count. A write target the guard cannot resolve
    is the owner's only in such a command, or when it is built from pieces of their path (`_suspect`)."""
    return _spells_owner(_command_text(command))


# What only PowerShell spells: a cmdlet (`Set-Location`, `Get-ChildItem`), `$env:`, `$_`, a .NET call. The splitter
# cannot tell which shell a command is for; with one of these in it, `( ... )` is read as PowerShell's expression,
# which runs in the shell itself, so a `cd` inside it stays (crew 1.3.137).
_POSH_RE = re.compile(
    r"(?<![\w./\\-])(?:get|set|new|remove|add|clear|copy|move|rename|out|push|pop|invoke|start|stop|test|select|"
    r"foreach|where|write|read|import|export|compress|expand|tee|join|split|resolve|convertto|convertfrom|measure|"
    r"format)-[a-z]+\b|\$env:|\$_(?!\w)|\$psitem\b|\[[\w.]+\]::|(?<![\w./\\-])(?:sl|gci)\s", re.IGNORECASE)


_TOO_LONG = (f"{OWNER_REASON}: at more than {_COMMAND_LIMIT} characters it is longer than the guard reads, so it "
             "cannot tell that it does not (put the script in a file and run that)")


def _owner_command_refusal(command, cwd=None):
    """Why a shell command may not write the owner's files (`_owner_path`), or None. A command the guard cannot
    finish reading (`_Unread`), or one its own reading fails on, is refused (crew 1.3.146): "could not tell" is
    not "does not write them", and outside `scope.mode` block nothing downstream would refuse it."""
    if len(command) > _COMMAND_LIMIT:
        return _TOO_LONG
    try:
        shell = _Shell(cwd)
        shell.hint = _owner_hint(command)
        shell.deep = _plausible(command)
        shell.posh = bool(_POSH_RE.search(command))
        if shell.deep and "\\'" in command:
            # `echo 'it'\''s' > <owner file>`: bash ends the quote, takes `\'` as a quote mark and starts a new
            # quote. The splitter (frozen until it is replaced) keeps a backslash as a Windows separator, pairs
            # the marks differently and loses the redirect, so the words it hands on are not the command's.
            return (f"{OWNER_REASON}: it names their folder and quotes with `\\'`, which the guard does not read "
                    "the way bash does")
        return _analyze(command, shell)
    except _Unread as exc:
        return f"{OWNER_REASON}: the guard cannot read all of it ({exc}), so it cannot tell that it does not"
    except Exception as exc:  # noqa: BLE001  pylint: disable=broad-except
        return (f"{OWNER_REASON}: the guard could not judge it ({type(exc).__name__}), so it cannot tell that it "
                "does not")


# The write verbs of the store rule that name no target the guard can single out (`echo`, `python3 x.py`, `touch`,
# `sed` without -i): given a path in the store, they are refused as before round 11.
_STORE_BLIND_RE = re.compile(r"touch|mkdir|chmod|echo|printf|python[0-9.]*|py|node|sed|perl", re.IGNORECASE)
_STORE_SPELLED_RE = re.compile(r"[^\s'\"`;|&<>()=,]*confirm-config[\\/]", re.IGNORECASE)


def _store_write(command, cwd=None):
    """True when `command` WRITES TO a confirm-config store (crew 1.3.137, round 11): the same reading as the
    owner's files get (`_analyze`: redirect targets, the argument each write verb aims at, `cd`, nested shells,
    `xargs`, `find -exec`, script blocks), with `_store_word` as the judge of each target. A verb in a file name
    (`Get-Content <store>/echo.txt`) or a search term (`grep echo <store>/x.json`) is no command, so no write."""
    if len(command) > _COMMAND_LIMIT:
        return True
    try:
        shell = _Shell(cwd)
        shell.posh = bool(_POSH_RE.search(command))
        blank = _Shell(None)
        shell.store = any(_canon(_expand(spelled, blank), None) is None
                          for spelled in _STORE_SPELLED_RE.findall(command))
        return _analyze(command, shell) is not None
    except Exception:  # noqa: BLE001  pylint: disable=broad-except
        return True   # unread (`_Unread`) or unjudged: a command that names the store and writes is refused


def _plain_spelling(path):
    """`path` in the spelling `_under` compares. On Windows that drops an extended-length (`\\\\?\\`) or device
    (`\\\\.\\`) prefix (`\\\\?\\UNC\\host\\share` becomes `\\\\host\\share`) and the trailing dots and spaces Win32
    strips from every component, so a file that does not exist yet is judged as the file it would become."""
    if re.match(r"^[\\/]{2}[?.][\\/]", path):
        rest = path[4:]
        path = "\\\\" + rest[4:] if rest[:4].lower() in ("unc\\", "unc/") else rest
    if os.name == "nt":
        path = re.sub(r"(?<=[^\\/.\s])[. ]+(?=[\\/]|$)", "", path)
    return path


def _owner_target(absolute):
    """True when a Write/Edit `absolute` path is, or resolves to, one of the owner's files."""
    try:
        absolute = _plain_spelling(absolute)
        real = role_write_guard._resolve_real_target(absolute)  # pylint: disable=protected-access
        return any(_owner_path(p) for p in (_plain_spelling(real), os.path.normpath(absolute)))
    except Exception:  # noqa: BLE001  pylint: disable=broad-except
        return True   # a path that cannot be resolved cannot be shown not to be theirs (crew 1.3.146)


def _owner_lines(what):
    """The refusal text for the owner's files: they are not approval state, so no `/crew:approve` is offered."""
    return [f"SCOPE GUARD: {what}.",
            "  The owner edits these files, or /crew:config and /crew:confirm-config do; /crew:approve has nothing "
            "to do with them."]


def _owner_files_only(tool, data, root):
    """What the guard still decides where it otherwise does nothing: `scope.mode` off (the default) or no work
    tree (crew 1.3.137). The owner's own files (`_owner_path`) are refused in EVERY mode, because the receipts
    and the master switch are what make an owner-only change the owner's: a guard that stood down with
    `scope.mode` would let an agent write both the `false` and its receipt. A call this check fails on is
    refused (crew 1.3.146): `main` allows what it could not judge in this mode, and this is the one rule left."""
    try:
        return _owner_files_decision(tool, data, root)
    except Exception as exc:  # noqa: BLE001  pylint: disable=broad-except
        return _deny(_owner_lines(f"could not tell whether this {tool} call writes the owner's files "
                                  f"({type(exc).__name__}), so it is refused"))


def _owner_files_decision(tool, data, root):
    """`_owner_files_only`'s decision; it may raise."""
    if tool in SHELLS:
        tool_input = data.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        readings = dict.fromkeys(_joined(command)) if isinstance(command, str) else ()
        reason = next((r for r in (_owner_command_refusal(c, data.get("cwd") or root) for c in readings) if r), None)
        if reason:
            return _deny(_owner_lines(f"refused this {tool} command -- {reason}"))
        return 0
    base = os.path.abspath(root)
    for path in targets(data):
        if _owner_target(path if os.path.isabs(path) else os.path.join(base, path)):
            return _deny(_owner_lines(f"{path} is the owner's file (the machine config or the confirm-config "
                                      "receipts) and is never written by Write/Edit"))
    return 0


def _log(top, mode, decision, ticket, path, reason):
    row = "\t".join(str(c).replace("\t", " ").replace("\n", " ") for c in (
        int(time.time()), "scope", mode, decision, ticket or "-", path or "-", reason))
    try:
        log = os.path.join(top, GUARD_LOG)
        if os.path.isdir(os.path.dirname(log)):
            with open(log, "a", encoding="utf-8") as handle:
                handle.write(row + "\n")
    except OSError:
        pass


def _deny(lines):
    sys.stderr.write("".join(line + "\n" for line in lines[:6]))
    return 2


def _note(text):
    sys.stdout.write(json.dumps({"systemMessage": text}) + "\n")
    return 0


def _broken_pointer(top, root, source):
    """A broken active-ticket pointer: refused under `block`, noted under
    `report`. Never the same as no active ticket."""
    mode, why = crew_ticket.effective_mode(root, None)
    reason = f"the active-ticket pointer is broken ({source})"
    _log(top, mode, "block" if mode == "block" else "report", None, "-", reason)
    if mode == "block":
        return _deny([f"SCOPE GUARD: refused -- {reason}.",
                      "  Point it at a real ticket: `crew_ticket.py activate --ticket <id>`,",
                      f"  or clear it: `crew_ticket.py deactivate`. ({why})"])
    return _note(f"scope-guard (report, would block): {reason}. ({why})")


def decide(data):
    """The exit code for one payload. Writes its own stderr/stdout."""
    if data is None:
        return None
    tool = data.get("tool_name")
    if tool not in TOOLS and tool not in SHELLS:
        return 0
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if tool in SHELLS and isinstance(tool_input, dict) else None
    if isinstance(command, str) and len(command) > _COMMAND_LIMIT:   # before anything reads it: reading is the cost
        return _deny(_owner_lines(f"refused this {tool} command -- {_TOO_LONG}"))
    trust = trust_refusal(data)
    if trust:
        return _deny([f"SCOPE GUARD: refused this {tool} call -- {trust}.",
                      "  Trust is given by the owner in a terminal: "
                      "`python3 verify_trust.py approve --root <repo>`."])
    root = data.get("cwd") if isinstance(data.get("cwd"), str) else None
    root = root or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    top = crew_ticket.toplevel(root)
    if not top:
        return _owner_files_only(tool, data, root)
    configured, why = crew_ticket.configured_mode(top)
    if configured == "off":
        return _owner_files_only(tool, data, root)
    common = crew_ticket.common_dir(root)
    if tool in SHELLS:
        tool_input = data.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        reason = shell_refusal(command, common, top, data.get("agent_type"))
        if reason is None:
            return 0
        if reason == LANE_REFUSAL:
            _log(top, configured, "block", None, "-", "lane-never-list")
            return _deny([f"SCOPE GUARD: refused this {tool} command -- {reason}.",
                          "  Write it as a question for the owner and stop the lane."])
        _log(top, configured, "block", None, "-", f"{tool}: {reason}")
        if reason.startswith(OWNER_REASON):
            return _deny(_owner_lines(f"refused this {tool} command -- {reason}"))
        return _deny([f"SCOPE GUARD: refused this {tool} command -- {reason}.",
                      "  Approval is recorded when the USER types `/crew:approve <id>`;",
                      "  ask them to, rather than running it for them."])
    state = os.path.join(common, "crew") if common else None
    paths = targets(data)
    base = os.path.abspath(root)
    for path in paths:
        if _owner_target(path if os.path.isabs(path) else os.path.join(base, path)):
            _log(top, configured, "block", None, path, "the owner's file")
            return _deny(_owner_lines(f"{path} is the owner's file (the machine config or the confirm-config "
                                      "receipts) and is never written by Write/Edit"))
        if protected(top, state, path, base):
            _log(top, configured, "block", None, path, "crew approval/ledger state")
            return _deny([f"SCOPE GUARD: {path} is crew's approval/ledger state (or a record "
                          "it trusts) and is never written by Write/Edit.",
                          "  Approval is recorded when the USER types `/crew:approve <id>`."])
    ticket, source, broken = crew_ticket.resolve_active(root)
    if broken:
        return _broken_pointer(top, root, source)
    if not ticket:
        return 0
    mode, why = crew_ticket.effective_mode(root, ticket)
    if not paths:
        reason = "the call names no file path, so its scope cannot be judged"
        verdicts = [("-", False, reason)]
    else:
        # ONE read of spec.md: the approval's hash check and the Touch judged
        # below come from the same bytes (crew_ticket.status).
        approval = crew_ticket.accepted(root, ticket)
        verdicts = [(p,) + classify(top, common, ticket, approval["touch"], approval, p, base)
                    for p in paths]
    bad = [(p, reason) for p, ok, reason in verdicts if not ok]
    if not bad:
        return 0
    path, reason = bad[0]
    _log(top, mode, "block" if mode == "block" else "report", ticket, path, reason)
    if mode == "block":
        return _deny([f"SCOPE GUARD: refused {data.get('tool_name')} on {path}.",
                       f"  Reason: {reason}.",
                       f"  To widen scope: amend .work/tickets/{ticket}/spec.md ## Touch "
                       "(and plan.md), then ask the user to type",
                       f"  `/crew:approve {ticket}`. ({why})"])
    return _note(f"scope-guard (report, would block): {path} - {reason}. ({why})")


def main():
    # One process judges one call: remember git's answers for it (see
    # crew_ticket.memoize_git) instead of asking again at every step.
    crew_ticket.memoize_git()
    data = _read_payload()
    try:
        code = decide(data)
    except Exception as exc:  # pylint: disable=broad-except
        root = (data or {}).get("cwd") if isinstance((data or {}).get("cwd"), str) else "."
        try:
            configured, _ = crew_ticket.configured_mode(crew_ticket.toplevel(root) or root)
        except Exception:  # pylint: disable=broad-except
            configured = "block"
        if configured in ("block", "auto"):
            return _deny([f"SCOPE GUARD: could not judge this write ({type(exc).__name__}: "
                          f"{exc}); failing closed under scope.mode {configured}."])
        sys.stderr.write(f"scope-guard: could not judge this write ({type(exc).__name__}); "
                         "allowed.\n")
        return 0
    if code is None:
        try:
            mode = unjudged_mode(os.environ.get("CLAUDE_PROJECT_DIR") or ".")
        except Exception:  # pylint: disable=broad-except
            mode = "block"
        if mode == "block":
            return _deny(["SCOPE GUARD: the hook payload did not parse; failing closed "
                          "because the effective scope mode is block."])
        sys.stderr.write("scope-guard: hook payload did not parse; allowed unjudged.\n")
        return 0
    return code


def unjudged_mode(root):
    """The EFFECTIVE mode for a payload that could not be read: `auto` is
    resolved against the active ticket (a broken pointer is `block`), so an
    `auto` repo past its ramp fails closed exactly like a `block` one."""
    top = crew_ticket.toplevel(root)
    if not top:
        return "off"
    configured, _ = crew_ticket.configured_mode(top)
    if configured != "auto":
        return configured
    ticket, _source, broken = crew_ticket.resolve_active(root)
    if broken:
        return "block"
    return crew_ticket.effective_mode(root, ticket)[0]


if __name__ == "__main__":
    sys.exit(main())
