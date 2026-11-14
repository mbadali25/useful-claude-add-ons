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
   confirm-config store beside it) is still refused (crew 1.3.96): those hold
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
# A line continuation: bash's backslash-newline, which the shell deletes (so it
# can split a word), and PowerShell's backtick-newline, which reads as a space.
_BASH_CONTINUATION_RE = re.compile(r"\\\r?\n")
_PS_CONTINUATION_RE = re.compile(r"`\r?\n")
_DOTGIT_CREW_RE = re.compile(r"\.git[\\/]+crew\b|git-common-dir\b.*\bcrew\b",
                             re.IGNORECASE | re.DOTALL)
# A redirect (not into /dev/null, $null or another descriptor), or a word
# that writes files. Reading crew's state -- `cat`, `Get-Content` -- passes.
_WRITES_RE = re.compile(
    r"(?<!>)>>?(?!>)(?!\s*(?:&\d|/dev/null\b|\$null\b))|"
    r"\b(?:tee|cp|mv|rm|ln|touch|mkdir|rmdir|install|dd|rsync|truncate|sed|perl|"
    r"python[0-9.]*|py|node|chmod|echo|printf|set-content|add-content|out-file|"
    r"new-item|copy-item|move-item|remove-item|rename-item|clear-content|set-item|ni|"
    r"sc|ac)\b", re.IGNORECASE)


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
    stands every guard down (crew 1.3.96). Like `confirm_store`, spelled here so this guard imports no config
    module."""
    return os.path.join(os.path.expanduser("~"), ".claude", "crew", "config.json")


def _owner_path(path):
    """True for the owner's own files: the double-confirmation store and the machine config, which holds
    `guards.enabled` (crew 1.3.96)."""
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
    state = os.path.join(common, "crew") if common else None
    folded = os.path.normcase(command).replace("\\", "/")
    names_state = bool(_DOTGIT_CREW_RE.search(command)) or bool(
        state and os.path.normcase(state).replace("\\", "/") in folded)
    if names_state and _WRITES_RE.search(command):
        return "it writes under <git-common-dir>/crew/, crew's approval and ledger state"
    return _owner_command_refusal(command, top)


# --- the owner's files, through a shell (crew 1.3.96, target-based since the round-3 owner decision) ------------
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
OWNER_REASON = "it writes the owner's files"
# A write call inside inline code (`python -c`, a heredoc, `pwsh -Command`, `node -e`).
_CODE_WRITES_RE = re.compile(
    r"\.write|write_text|write_bytes|writelines|\bdump\(|\bunlink|os\.remove|os\.replace|os\.rename|\.rename\(|"
    r"shutil|rmtree|\bcopyfile|\bmove\(|writeall|writefile|appendfile|createwritestream|"
    r"\bopen\([^)]*['\"][rwax]*[wax+][rwabxt+]*['\"]|mode\s*=\s*['\"][rwax]*[wax+]|o_wronly|o_rdwr|o_creat|"
    r"set-content|add-content|out-file|new-item|copy-item|move-item|remove-item|rename-item|clear-content|"
    r"\[io\.file\]::", re.IGNORECASE)
_HOME_PART = r"(?:~|\$home|\$\{home\}|%userprofile%|\$env:userprofile|\$env:home)"
_HOME_VARS = frozenset({"home", "userprofile"})
_CODE_RUNNERS = frozenset({"python", "python3", "py", "node", "nodejs", "deno", "bun", "perl", "ruby", "php", "lua"})
_CODE_FLAGS = frozenset({"-c", "-e", "-p", "-r", "-E", "--eval", "--command"})
_POSIX_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
_PWSH = frozenset({"pwsh", "powershell"})
_WRAPPERS = frozenset({"sudo", "env", "time", "command", "nohup", "exec", "builtin", "call", "start", "&"})
_DECLARERS = frozenset({"export", "declare", "local", "typeset", "readonly", "set"})
_CD = frozenset({"cd", "chdir", "set-location", "sl", "push-location", "pushd"})
_REMOVERS = frozenset({"rm", "unlink", "shred", "del", "erase", "rd", "rmdir", "remove-item", "ri",
                       "mv", "move", "ren", "rename", "rename-item", "rni", "move-item", "mi"})
_WRITERS = frozenset({"tee", "truncate", "clear-content", "set-content", "add-content", "out-file", "new-item", "ni",
                      "set-item", "sponge", "sc", "ac", "mklink"})
_COPIERS = frozenset({"cp", "copy", "copy-item", "cpi", "xcopy", "robocopy", "rsync", "install", "ln"})
_EDITORS = frozenset({"vim", "vi", "nvim", "ex", "ed", "nano", "view"})
_GIT_WRITES = frozenset({"apply", "am", "checkout", "restore", "reset", "clean", "stash", "merge", "pull", "rebase",
                         "mv", "rm", "switch", "cherry-pick", "revert"})
_OPTION_RE = re.compile(r"^(?:-[^\s]|/[A-Za-z?]{1,2}(?::\S*)?$)")
_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.DOTALL)
_VAR_RE = re.compile(r"\$env:(\w+)|\$\{(\w+)\}|\$(\w+)|%(\w+)%", re.IGNORECASE)
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


class _Segment:  # pylint: disable=too-few-public-methods
    """One simple command: its words, the targets of its redirects, `$(...)` bodies, and heredoc bodies."""

    def __init__(self):
        self.words, self.targets, self.subs, self.bodies = [], [], [], []

    def __bool__(self):
        return bool(self.words or self.targets or self.subs or self.bodies)


def _segments(text):  # pylint: disable=too-many-branches,too-many-statements
    """The `_Segment`s of `text`, split at `;` `&&` `||` `|` `&` and newlines, outside quotes."""
    result, seg = [], _Segment()
    buf, has, mode = [], False, None   # mode: None | "target" | "skip" | "heredoc"
    delims = []
    index, size = 0, len(text)

    def flush():
        nonlocal buf, has, mode
        if not has:
            return
        word, buf, has = "".join(buf), [], False
        if mode == "heredoc":
            delims.append(word)
        elif mode == "target":
            seg.targets.append(word)
        elif mode is None:
            seg.words.append(word)
        mode = None

    def close():
        nonlocal seg
        flush()
        if seg:
            result.append(seg)
        seg = _Segment()

    while index < size:
        char = text[index]
        if char in "'\"":
            end = index + 1
            while end < size and text[end] != char:
                end += 2 if (char == '"' and text[end] == "\\" and end + 1 < size and text[end + 1] == '"') else 1
            chunk = text[index + 1:end]
            if char == '"':
                for found in re.finditer(r"\$\(", chunk):
                    inner, _ = _balanced(chunk, found.end())
                    seg.subs.append(inner)
            buf.append(chunk)
            has = True
            index = end + 1
        elif char == "$" and text[index + 1:index + 2] == "(":
            inner, index = _balanced(text, index + 2)
            seg.subs.append(inner)
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
            close()
            index += 1
            while text[index:index + 1] == char or (char == "|" and text[index:index + 1] == "&"):
                index += 1
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
                buf, has = [], False   # `2>`: the descriptor is no word
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
                buf, has = [], False
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
                mode = "skip"
        elif char in " \t\r()":
            flush()
            index += 1
        else:
            buf.append(char)
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
    if "$" in path or "%" in path:
        return None
    if not (path.startswith("/") or _DRIVE_RE.match(path)):
        if base is None:
            return None
        path = base + "/" + path
    unc = path.startswith("//") and not path.startswith("///")
    path = posixpath.normpath(re.sub(r"/{2,}", "/", path))
    if unc:
        path = "/" + path
    trimmed = path.rstrip(" .")
    return trimmed if trimmed and not trimmed.endswith(":") else path


class _Shell:  # pylint: disable=too-few-public-methods
    """What the command so far has set: variables, and the working directory (None when it cannot be told)."""

    def __init__(self, cwd):
        self.vars = {}
        self.cwd = _canon(cwd, None) if cwd else None


def _expand(word, shell):
    """`word` with `~`, `$HOME`-style and the variables the command set substituted; an unknown variable stays."""
    home = os.path.expanduser("~")

    def sub(match):
        name = next(g for g in match.groups() if g)
        value = shell.vars.get(name.lower())
        if value is not None:
            return value
        return home if name.lower() in _HOME_VARS else match.group(0)

    word = _VAR_RE.sub(sub, word)
    if word == "~" or word.startswith(("~/", "~\\")):
        word = home + word[1:]
    return word


def _hit(word, shell, mode):  # pylint: disable=too-many-return-statements
    """True when `word` names (or, for a glob, can match) the owner's files. `mode` "file" is the machine config
    and the confirm-config store; "dir" adds the folders a copy or an extraction lands in (`~/.claude/crew`,
    `~/.claude`); "destroy" adds home itself, for a delete or a move."""
    word = _expand(word, shell)
    word = re.sub(r"(?<=[^/\\:]):(?::\$\w+|[^/\\:]+)(?::\$\w+)?$", "", word)   # an NTFS stream: `f::$DATA`, `f:s`
    if not word or _IGNORED_TARGET_RE.match(word):
        return False
    path = _canon(word, shell.cwd)
    machine = _fold(machine_config())
    folder, store = posixpath.dirname(machine), _fold(confirm_store())
    if path is None:
        text = word.replace("\\", "/").lower()
        return bool(re.search(r"(?<![\w.-])crew/+config\.json$", text)
                    or re.search(r"(?:^|/)\.claude/+crew/+(?:config\.json$|confirm-config(?:/|$))", text)
                    or re.search(r"(?:^|/)confirm-config(?:/|$)", text))
    parent = posixpath.dirname(folder)
    folders = {"file": (), "dir": (folder, parent), "destroy": (folder, parent, posixpath.dirname(parent))}[mode]
    if any(ch in path for ch in "*?["):
        samples = (machine, store, store + "/cc-00000000.json") + folders
        return any(fnmatch.fnmatchcase(sample, path) for sample in samples)
    return (path == machine or path == store or path.startswith(store + "/") or path in folders
            or bool(re.search(r"(?:^|/)\.claude/crew/(?:config\.json$|confirm-config(?:/|$))", path)))


def _in_owner_folder(shell):
    """True when the working directory is the owner's folder or its receipts store."""
    if shell.cwd is None:
        return False
    folder = posixpath.dirname(_fold(machine_config()))
    return shell.cwd == folder or shell.cwd.startswith(folder + "/")


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
    if sub not in _GIT_WRITES:
        return False
    return _hit(where, shell, "dir") if where is not None else _in_owner_folder(shell)


def _download_hits(name, args, shell):
    """True when a downloader's output file (or, for wget -P, folder) is the owner's."""
    if name.startswith("wget"):
        out = _option_value(args, "-O", "--output-document")
        if out is not None:
            return _hit(out, shell, "file")
        folder = _option_value(args, "-P", "--directory-prefix")
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
        if outdir is not None and (remote_name or (out is not None and not os.path.isabs(out)))                 and _hit(outdir, shell, "dir"):
            return True
    if out is not None:
        return _hit(out, shell, "file")
    return name.startswith("curl") and remote_name and _in_owner_folder(shell)


def _archive_hits(name, args, shell):
    """True when an extraction lands in the owner's folder (or an archive is created as one of its files)."""
    if name in ("unzip", "7z", "7za"):
        attached = next((a[2:] for a in args if a.startswith("-o") and len(a) > 2), None)   # 7z x a.7z -o<dir>
        where = _option_value(args, "-d") or attached
        return _hit(where, shell, "dir") if where else (name == "unzip" and _in_owner_folder(shell))
    if name == "expand-archive":
        where = _option_value(args, "-DestinationPath", "-Dest")
        return where is not None and _hit(where, shell, "dir")
    # the mode letters are a bundle (`xf`, `-xzf`) wherever the options put it: `-C dir -xf a.tar` too
    bundles = [a for position, a in enumerate(args) if re.match(r"^-[A-Za-z]+$", a) or (position == 0 and a[:1].isalpha())]
    extracting = "--extract" in args or any("x" in b for b in bundles)
    creating = "--create" in args or any("c" in b for b in bundles)
    if extracting:
        where = _option_value(args, "-C", "--directory")
        return _hit(where, shell, "dir") if where else _in_owner_folder(shell)
    if creating:
        target = _option_value(args, "-f", "--file")
        return target is not None and _hit(target, shell, "file")
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


_PS_CMDLETS = frozenset({"clear-content", "set-content", "add-content", "out-file", "new-item", "ni", "set-item",
                         "sc", "ac"})
_PS_SWITCHES = frozenset({"force", "nonewline", "append", "noclobber", "whatif", "confirm", "passthru", "wait",
                          "asbytestream", "usetransaction"})
_PS_PATH_PARAMS = frozenset({"path", "literalpath", "lp", "pspath", "filepath", "destination"})


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
            param = param.lower()
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
    if name is not None:
        found = [base.rstrip("/\\") + "/" + name for base in found] or [name]
    return found


def _verb_hits(name, args, shell):  # pylint: disable=too-many-return-statements
    """True when the command `name args` writes the owner's files (what it is aimed at, per verb)."""
    lowered = [a.lower() for a in args]
    operands = [w for w in _operands(args) if w]
    if name in _REMOVERS:
        return any(_hit(w, shell, "destroy") for w in operands)
    if name == "fsutil":
        return "hardlink" in lowered and any(_hit(w, shell, "dir") for w in operands)
    if name in _WRITERS:
        mode = "dir" if name == "mklink" or any(x in lowered for x in ("junction", "symboliclink", "hardlink")) \
            else "file"
        written = _ps_destinations(args) if name in _PS_CMDLETS and mode == "file" else operands
        return any(_hit(w, shell, mode) for w in written if w)
    if name in _COPIERS:
        return _copy_hits(name, args, shell) or (name == "ln" and any(_hit(w, shell, "file") for w in operands))
    if name in ("sed", "perl", "ruby", "awk", "gawk"):
        inplace = any(re.match(r"^-[A-Za-z]*i", a) or a.startswith("--in-place") for a in args) or (
            name in ("awk", "gawk") and "inplace" in lowered)
        return inplace and any(_hit(w, shell, "file") for w in operands)
    if name in _EDITORS:
        return any(_hit(w, shell, "file") for w in operands)
    if name == "dd":
        return any(a.startswith("of=") and _hit(a[3:], shell, "file") for a in args)
    if name == "patch":
        where = _option_value(args, "-d", "--directory")
        return any(_hit(w, shell, "file") for w in operands) or (
            _hit(where, shell, "dir") if where else _in_owner_folder(shell))
    if name in ("curl", "wget", "iwr", "irm", "invoke-webrequest", "invoke-restmethod"):
        return _download_hits(name, args, shell)
    if name in ("tar", "bsdtar", "unzip", "7z", "7za", "expand-archive"):
        return _archive_hits(name, args, shell)
    return name == "git" and _git_hits(args, shell)


def _assign(raw, shell):
    """Record one `NAME=value` word; True when `raw` was one."""
    match = _ASSIGN_RE.match(raw)
    if not match:
        return False
    shell.vars[match.group(1).lower()] = _expand(match.group(2), shell)
    return True


def _leading(words, shell):
    """`words` without the assignments, wrappers and declarations before the command itself (recording the
    variables they set)."""
    words = list(words)
    while words:
        head = words[0]
        lowered = head.lower()
        if _assign(head, shell):
            words.pop(0)
        elif lowered.startswith("$") and len(words) >= 3 and words[1] == "=":
            name = head[5:] if lowered.startswith("$env:") else head[1:]
            shell.vars[name.lower()] = _expand(words[2], shell)
            words = words[3:]
        elif lowered in _DECLARERS:
            words.pop(0)
            while words and (words[0].startswith("-") or _assign(words[0], shell)):
                words.pop(0)
        elif lowered in _WRAPPERS:
            words.pop(0)
            while words and (words[0].startswith("-") or _ASSIGN_RE.match(words[0])):
                if _ASSIGN_RE.match(words[0]):
                    _assign(words[0], shell)
                words.pop(0)
        else:
            break
    return words


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
                    refusal = _analyze(code, shell, depth + 1)
                if refusal:
                    return refusal
                break
    if name in _POSIX_SHELLS:
        for position, arg in enumerate(args):
            if re.match(r"^-[a-z]*c$", arg) and position + 1 < len(args):
                return _analyze(args[position + 1], shell, depth + 1)
    if name == "eval":
        return _analyze(" ".join(args), shell, depth + 1)
    if name == "cmd":
        for position, arg in enumerate(lowered):
            if arg in ("/c", "/k", "/r"):
                return _analyze(" ".join(args[position + 1:]), shell, depth + 1)
    return None


def _segment_refusal(seg, shell, depth):  # pylint: disable=too-many-return-statements
    """Why one simple command writes the owner's files, or None."""
    for target in seg.targets:
        if _hit(target, shell, "file"):
            return f"{OWNER_REASON}: a redirect aims at them"
    words = _leading(seg.words, shell)
    if not words:
        return None
    if words[0].lower().startswith(("[io.file]::", "[system.io.file]::")):   # a .NET write with the path spelled out
        return _code_refusal(" ".join(words))
    name = _command_name(_expand(words[0], shell))
    args = [_expand(w, shell) for w in words[1:]]
    if name in _CD:
        plain = [a for a in args if not a.startswith("-")]
        shell.cwd = _canon(plain[0] if plain else os.path.expanduser("~"), shell.cwd)
        return None
    for body in seg.bodies:
        if name in _CODE_RUNNERS or name in _PWSH:
            refusal = _code_refusal(body)
            if refusal:
                return refusal
        if name in _POSIX_SHELLS or name in _PWSH:
            refusal = _analyze(body, shell, depth + 1)
            if refusal:
                return refusal
    refusal = _nested(name, args, shell, depth)
    if refusal:
        return refusal
    if _verb_hits(name, args, shell):
        return f"{OWNER_REASON}: `{name}` is aimed at them"
    return None


def _analyze(text, shell, depth=0):
    """The first refusal in `text` read as shell commands, or None."""
    if depth > 3 or not isinstance(text, str):
        return None
    for seg in _segments(text):
        for sub in seg.subs:
            refusal = _analyze(sub, shell, depth + 1)
            if refusal:
                return refusal
        refusal = _segment_refusal(seg, shell, depth)
        if refusal:
            return refusal
    return None


def _owner_command_refusal(command, cwd=None):
    """Why a shell command may not write the owner's files (`_owner_path`), or None."""
    return _analyze(command, _Shell(cwd))


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
    absolute = _plain_spelling(absolute)
    real = role_write_guard._resolve_real_target(absolute)  # pylint: disable=protected-access
    return any(_owner_path(p) for p in (_plain_spelling(real), os.path.normpath(absolute)))


def _owner_lines(what):
    """The refusal text for the owner's files: they are not approval state, so no `/crew:approve` is offered."""
    return [f"SCOPE GUARD: {what}.",
            "  The owner edits these files, or /crew:config and /crew:confirm-config do; /crew:approve has nothing "
            "to do with them."]


def _owner_files_only(tool, data, root):
    """What the guard still decides where it otherwise does nothing: `scope.mode` off (the default) or no work
    tree (crew 1.3.96). The owner's own files (`_owner_path`) are refused in EVERY mode, because the receipts
    and the master switch are what make an owner-only change the owner's: a guard that stood down with
    `scope.mode` would let an agent write both the `false` and its receipt."""
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
