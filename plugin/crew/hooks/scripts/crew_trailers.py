"""`git.forbiddenTrailers` (T-0066): commit trailers crew refuses to commit
and reports over a ticket's commits.

The key is a list of trailer tokens (`["Co-Authored-By"]`), declared in BOTH
config layers with `[]` as the default, and the list is the switch: empty in
both layers means nothing is forbidden and nothing here refuses. Three uses:

* `forbidden(root)` -- the list in force: the UNION of the repo's
  `.crew/config.json` and the machine-global `~/.claude/crew/config.json`,
  each read raw (the `crew_config.resolve_ratcheted` pattern), never by
  precedence. A cloned repo can add a trailer to the list and can never
  remove the machine owner's: under precedence a repo `[]` would silently
  disarm the owner. A layer `crew_config.layer_state` calls corrupt, or a
  value that is not a list of trailer tokens, is "could not tell" -- its own
  value, never read as `[]`.
* `commit_refusal(command, tokens, cwd)` -- why one Bash/PowerShell command
  is refused, or None. Written for `scope_guard.decide` to call in EVERY
  `scope.mode`, including `off`, with the `[]` default keeping it inert. That
  wiring touches review/gate harness paths (`HARNESS` in
  `scripts/check-tooling-pr.py`), so it lands in its own change; until then
  nothing calls this function and nothing refuses.
* `--check --root DIR --ticket ID` -- `/crew:done`'s report over the
  ticket's commits: `git log --first-parent <scope base>..HEAD`. The spec
  says `<scope base>..HEAD`; `--first-parent` is a deliberate refinement of
  it. A ticket branch merges origin/main, and the plain range then holds
  every commit that merge brought in -- other people's, many carrying the
  trailer. Following first parents keeps the ticket's own commits, a merge
  commit made on the ticket branch included, and drops what it merged in.
  It REPORTS and never refuses: a refusal would be curable only by a
  history rewrite, which is the owner's decision and stales the review
  receipt. Any unexpected exception, an import failure included, is
  `trailers: unknown - <Type>: <msg>` and exit 2, never 1 (the FINDING
  code).

## What the command check judges

A command "writes a commit" when one of its simple commands (split on
newline, `;`, `&`, `&&`, `||`, `|`, with heredoc and here-string bodies kept
out of the split) runs `git` -- after any of `-C <dir>`, `-c <k=v>`,
`--git-dir`, `--work-tree`, `--no-pager` -- with the subcommand `commit`,
`commit-tree` or `merge`, or runs `gh pr merge`. For such a command the whole
text, and the content of every literal `-F`/`--file`/`--body-file` message
file, is searched with `(?i)\\b<Token>\\s*[:=]` -- case-insensitive, as git
treats trailer keys. So prose saying "no Co-Authored-By trailers" passes and
prose "Co-Authored-By: lines" is refused: conservative on purpose.

A `-F -` (stdin) message is judged from the command text, where its heredoc
is. A `-F` path holding `$`, `%` or a backtick, or a literal path that is
missing and is not written earlier in the same command, is "could not tell"
and refused.

## What it cannot see (stated, not implied)

A commit that REUSES an existing message (`--amend --no-edit`, `-C`/`-c
<commit>`, `cherry-pick`, `revert`, `rebase`), a message built by an
interpreter or a script, and anything run outside Claude's Bash/PowerShell
tools. `gh pr create --body` is not checked: a PR body is not a commit, and
the owner's instructions ask for a session link there. The `--check` report
is the backstop for all of these. This is a textual check, not a shell
parser.
"""
import json
import os
import re
import subprocess
import sys

KEY = "git.forbiddenTrailers"
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
GIT_TIMEOUT = 60

_BASH_CONTINUATION_RE = re.compile(r"\\\r?\n")
_PS_CONTINUATION_RE = re.compile(r"`\r?\n")
_HEREDOC_RE = re.compile(r"<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
_HERESTRING_RE = re.compile(r"@(['\"])\r?\n.*?\r?\n\1@", re.DOTALL)
_SEPARATOR_RE = re.compile(r"\|\||&&|[;\n|&]")
_WORD_RE = re.compile(r"\"(?:\\.|[^\"\\])*\"|'[^']*'|[^\s\"']+(?:[\"'][^\"']*[\"'][^\s\"']*)*")
# git's global options that take the NEXT word as their value.
_GIT_VALUE_OPTS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace",
                   "--exec-path", "--config-env")
_COMMIT_SUBCOMMANDS = ("commit", "commit-tree", "merge")
_FILE_OPTS = ("-F", "--file", "--body-file")
_UNRESOLVABLE = ("$", "%", "`")


# Sibling modules are imported where they are used, not at the top: an import
# failure must reach `main`'s catch-all and be "unknown" (exit 2), not a
# traceback, whose exit 1 is the FINDING code.
def _common():
    import crew_common  # pylint: disable=import-outside-toplevel
    return crew_common


def _config():
    import crew_config  # pylint: disable=import-outside-toplevel
    return crew_config


def _layers(root, global_path=None):
    """`([(path, tokens), ...], unknown)` for the repo then the global layer.
    The repo layer is the `.crew/` `crew_common.repo_config_dir` resolves (a
    linked worktree with none reads the main checkout's). `unknown` is a
    sentence naming the file and key, or None."""
    config, common = _config(), _common()
    crew_dir, source, detail = common.repo_config_dir(root)
    if source == common.SOURCE_UNKNOWN:
        return [], f"which repo config is in force could not be told ({detail})"
    paths = (os.path.join(crew_dir, "config.json"),
             config.GLOBAL_CONFIG_PATH if global_path is None else global_path)
    out = []
    for path in paths:
        state = config.layer_state(path)
        if state == "absent":
            out.append((path, ()))
            continue
        if state != "ok":
            return out, f"{path} is unreadable or not a JSON object ({state})"
        try:
            with open(path, encoding="utf-8") as handle:
                parsed = json.load(handle)
        except (OSError, ValueError) as exc:
            return out, f"{path} could not be read ({type(exc).__name__})"
        if "git" not in parsed:
            out.append((path, ()))
            continue
        block = parsed["git"]
        if not isinstance(block, dict):
            return out, f"{path}: `git` is not an object, so {KEY} cannot be read"
        value = block.get("forbiddenTrailers", [])
        if not isinstance(value, list) or not all(
                isinstance(item, str) and TOKEN_RE.match(item) for item in value):
            return out, (f"{path}: {KEY} is not a list of trailer tokens "
                         "(letters, digits and '-', no ':')")
        out.append((path, tuple(value)))
    return out, None


def forbidden(root, global_path=None):
    """`(tokens, unknown)`: the union of both layers' lists, deduplicated
    case-insensitively in first-seen order, or `((), reason)` when either
    layer could not be read. Never raises for a bad config file."""
    layers, unknown = _layers(root, global_path)
    if unknown:
        return (), unknown
    seen, tokens = set(), []
    for _label, values in layers:
        for token in values:
            if token.casefold() not in seen:
                seen.add(token.casefold())
                tokens.append(token)
    return tuple(tokens), None


def set_by(root, global_path=None):
    """The config files whose list is non-empty, for the refusal message."""
    layers, _ = _layers(root, global_path)
    return [path for path, values in layers if values]


def _trailer_re(token):
    return re.compile(r"(?i)\b" + re.escape(token) + r"\s*[:=]")


def _strip_bodies(command):
    """`command` with heredoc and PowerShell here-string bodies removed, so a
    body line is never read as a command of its own."""
    command = _HERESTRING_RE.sub(" ", command)
    lines = command.split("\n")
    out, pending = [], []
    for line in lines:
        if pending:
            strip, word = pending[0]
            if (line.lstrip("\t") if strip else line).rstrip("\r") == word:
                pending.pop(0)
            continue
        out.append(line)
        for match in _HEREDOC_RE.finditer(line):
            pending.append((match.group(1) == "-", match.group(3)))
    return "\n".join(out)


def _words(span):
    return [w[1:-1] if len(w) > 1 and w[0] == w[-1] and w[0] in "\"'" else w
            for w in _WORD_RE.findall(span)]


def _program(word):
    name = re.split(r"[\\/]", word)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _git_commit_at(words, i):
    """`(True, dir_or_None, rest)` when `words[i]` is git running a commit
    subcommand, else `(False, None, None)`."""
    j, where = i + 1, None
    while j < len(words) and words[j].startswith("-"):
        if words[j] in _GIT_VALUE_OPTS:
            if words[j] == "-C" and j + 1 < len(words):
                where = words[j + 1]
            j += 2
        else:
            j += 1
    if j < len(words) and words[j] in _COMMIT_SUBCOMMANDS:
        return True, where, words[j + 1:]
    return False, None, None


def _gh_merge_at(words, i):
    rest = list(words[i + 1:])
    plain, skip = [], False
    for word in rest:
        if skip:
            skip = False
            continue
        if word in ("-R", "--repo"):
            skip = True
            continue
        if word.startswith("-"):
            continue
        plain.append(word)
    if plain[:2] == ["pr", "merge"]:
        return True, None, rest
    return False, None, None


def _commits(command):
    """Every `(dir_or_None, args, span_start)` a commit-writing invocation in
    `command` carries, across the three readings of its continuations."""
    found = []
    readings = (command, _BASH_CONTINUATION_RE.sub("", command),
                _PS_CONTINUATION_RE.sub(" ", command))
    for reading in readings:
        text = _strip_bodies(reading)
        start = 0
        for piece in _SEPARATOR_RE.split(text):
            words = _words(piece)
            for i, word in enumerate(words):
                program = _program(word)
                if program == "git":
                    hit, where, rest = _git_commit_at(words, i)
                elif program == "gh":
                    hit, where, rest = _gh_merge_at(words, i)
                else:
                    continue
                if hit:
                    found.append((where, rest, start))
                    break
            start += len(piece) + 1
        if found:
            return found, text
    return found, command


def writes_commit(command):
    """True when `command` runs a commit-writing git or gh invocation."""
    if not isinstance(command, str):
        return False
    return bool(_commits(command)[0])


def _message_files(args):
    """The literal values of every message-file option in `args`."""
    files = []
    for i, word in enumerate(args):
        for opt in _FILE_OPTS:
            if word == opt and i + 1 < len(args):
                files.append(args[i + 1])
            elif word.startswith(opt + "=") and opt.startswith("--"):
                files.append(word[len(opt) + 1:])
            elif opt == "-F" and word.startswith("-F") and len(word) > 2:
                files.append(word[2:])
    return files


def _written_earlier(path, before):
    """True when the text before the commit writes `path`: a redirect, `tee`,
    `Out-File` or `Set-Content` naming it."""
    name = re.escape(path)
    pattern = (r"(?:>>?\s*|\btee\s+(?:-a\s+)?|\b(?:out-file|set-content)\s+(?:-(?:file)?path\s+)?)"
               r"[\"']?" + name + r"[\"']?(?=\s|$|[;|&)])")
    return re.search(pattern, before, re.IGNORECASE) is not None


def commit_refusal(command, tokens, cwd, unknown=None):
    """Why `command` is refused under `git.forbiddenTrailers`, or None.

    None when the command writes no commit, or when `tokens` is empty and
    the list was readable. `unknown` (the list could not be read) refuses a
    commit-writing command and nothing else. Every reason names the key."""
    if not isinstance(command, str):
        return None
    commits, text = _commits(command)
    if not commits:
        return None
    if unknown:
        return f"{KEY} could not be read ({unknown}), so this commit cannot be judged"
    if not tokens:
        return None
    for token in tokens:
        if _trailer_re(token).search(command):
            return f"its message carries the `{token}` trailer, which {KEY} forbids"
    base = cwd or "."
    for where, args, start in commits:
        for path in _message_files(args):
            if path == "-":
                continue
            if any(mark in path for mark in _UNRESOLVABLE):
                return (f"could not tell whether the message file `{path}` carries a "
                        f"trailer {KEY} forbids ({', '.join(tokens)})")
            full = os.path.join(base, where or "", os.path.expanduser(path))
            if not os.path.isfile(full):
                if _written_earlier(path, text[:start]):
                    continue
                return (f"could not tell whether the message file `{path}` carries a "
                        f"trailer {KEY} forbids ({', '.join(tokens)}): it does not exist yet")
            try:
                with open(full, encoding="utf-8", errors="replace") as handle:
                    body = handle.read()
            except OSError:
                return (f"could not tell whether the message file `{path}` carries a "
                        f"trailer {KEY} forbids ({', '.join(tokens)}): it cannot be read")
            for token in tokens:
                if _trailer_re(token).search(body):
                    return (f"its message file `{path}` carries the `{token}` trailer, "
                            f"which {KEY} forbids")
    return None


def _log_messages(root, base):
    """`[(sha, message), ...]` for the ticket's own commits in `base..HEAD`
    (first parents only, module docstring), or None when git failed."""
    try:
        done = subprocess.run(
            ("git", "log", "--first-parent", "--format=%H%x00%B%x1e", f"{base}..HEAD"),
            cwd=root,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=GIT_TIMEOUT, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    out = []
    for record in done.stdout.split("\x1e"):
        record = record.strip("\n")
        if "\x00" in record:
            sha, message = record.split("\x00", 1)
            out.append((sha.strip(), message))
    return out


def check(root, ticket, global_path=None):
    """`(exit_code, lines)` for `/crew:done`'s report (module docstring)."""
    tokens, unknown = forbidden(root, global_path)
    if unknown:
        return 2, [f"trailers: unknown - {unknown}"]
    if not tokens:
        return 0, [f"trailers: clean ({KEY} is empty - nothing forbidden)"]
    import scope_base  # pylint: disable=import-outside-toplevel
    base, source, reason = scope_base.resolve(root, ticket)
    if not base:
        # No base at all. scope_base's `head` last resort (HEAD..HEAD) reads
        # no commit and is caught below with every such fallback.
        return 2, [f"trailers: unknown - no base for {ticket}: {reason}"]
    messages = _log_messages(root, base)
    if messages is None:
        return 2, [f"trailers: unknown - git log {base[:12]}..HEAD failed"]
    recorded = source == scope_base.RECORDED
    if not messages and not recorded:
        # A fallback base that IS HEAD (a merge-base on the default branch)
        # reads nothing either: unknown, not "clean (0 commits)".
        return 2, [f"trailers: unknown - no base for {ticket}: {reason}"]
    # A fallback base is named on every line derived from it (scope_base's
    # header): the reassuring line must not look like the recorded one.
    note = "" if recorded else f" - base is a fallback: {reason}"
    lines = []
    for sha, message in messages:
        for token in tokens:
            if _trailer_re(token).search(message):
                lines.append(f"trailers: FINDING {sha[:7]} {token}{note}")
    if lines:
        return 1, lines
    return 0, [f"trailers: clean ({len(messages)} commits){note}"]


def main(argv):
    """`--check --root DIR --ticket ID [--global-path P]`: exit 0 clean,
    1 a finding, 2 unknown or a usage error. An unexpected exception is
    unknown: it prints `trailers: unknown - <Type>: <msg>` and exits 2."""
    try:
        return _main(argv)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        sys.stdout.write(f"trailers: unknown - {type(exc).__name__}: {exc}\n")
        return 2


def _main(argv):
    args = list(argv)
    opts = {"--root": ".", "--ticket": None, "--global-path": None}
    if "--check" not in args:
        sys.stderr.write("usage: crew_trailers.py --check --root DIR --ticket ID "
                         "[--global-path P]\n")
        return 2
    args.remove("--check")
    while args:
        flag = args.pop(0)
        if flag not in opts or not args:
            sys.stderr.write(f"crew_trailers.py: bad argument {flag!r}\n")
            return 2
        opts[flag] = args.pop(0)
    if not opts["--ticket"]:
        sys.stderr.write("crew_trailers.py: --ticket is required\n")
        return 2
    code, lines = check(opts["--root"], opts["--ticket"], opts["--global-path"])
    sys.stdout.write("".join(line + "\n" for line in lines))
    return code


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main(sys.argv[1:]))
