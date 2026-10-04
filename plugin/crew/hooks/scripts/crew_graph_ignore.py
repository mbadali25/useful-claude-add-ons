"""Would a graph build read a secrets-denylisted file? Read-only unless --write.

    python3 crew_graph_ignore.py --root . --check [--json]
    python3 crew_graph_ignore.py --root . --write

T-0064. graphify reads every file its ignore rules do not exclude, and for a
file git tracks only `.graphifyignore` (and `--exclude`) can exclude it:
graphify 0.9.65 skips `.gitignore` rules for any path in `git ls-files
--cached` (`detect.py` `_is_scan_ignored`). So a tracked `config/env.php`
listed in `.gitignore` alone is read, and its symbols land in `graph.json`.
This module lists every file on disk the secrets denylist matches that the
root `.graphifyignore` does not exclude. `crew_refresh_check.py` refuses to
name a graph refresh while that list is non-empty, `crew_status.py` prints it
as the `graph-ignore` line, and crew-graph's Build runs `--check` first.

## The denylist

The union, in this order, of:

  built-in   BUILTIN_PATTERNS -- `.env`, `.env.*` but not `.env.example`,
             private keys and certificate bundles.
  file       `.claude/secrets-denylist`, optional, tracked, gitignore syntax.
             The place for repo-specific paths (`config/`, `/init.php`), and a
             file a repo's own secrets guard can read as well.
  settings   every `Read(<pattern>)` in `permissions.deny` of
             `.claude/settings.json` and `.claude/settings.local.json`.

## Read(...) rules, per the Claude Code permissions documentation

Source: https://code.claude.com/docs/en/permissions, "Read and Edit", read
2026-09-27. Rules use gitignore syntax with four anchors: `//path` is
absolute from the filesystem root; `~/path` is from the home directory;
`/path` is "relative to the settings source", which for project settings
(`.claude/settings.json`) and local settings (`.claude/settings.local.json`)
is `<primary working directory>/path` -- NOT the `.claude/` directory; and
`path` / `./path` is relative to the current directory. As a deny rule, a
single directory segment such as `secrets/**` matches that directory at any
depth. So, taking the session's directory to be the repository root:

  `/x`         -> `/x`
  `./x`, `x`   -> `x`, plus `**/<seg>/**` for the single-segment `<seg>/**`
  `//abs`      -> `/<rest>` when `abs` is inside the repository, `**/<rest>`
                  for `//**/<rest>`, else skipped by name
  `~/p`        -> as `//abs` after expanding the home directory
  `.\\x`, `x\\y`  -> as `./x`, `x/y`: `\\` is read as `/` first, since in
                  a git pattern it escapes and would silently match nothing
  `!p`         -> skipped by name: a carve-out only shrinks the denylist, and
                  ignoring one can only require more coverage
  `Read`, `Read(*)`, `Read(**)`  -> unknown: no ignore file can express
                  "deny every read" usefully

## What is judged, and by what

Candidates are every path `git ls-files -z --cached --others` lists (no
`--exclude-standard`, so a file `.gitignore` ignores is still one -- graphify
reads those under `--no-gitignore`) that exists on disk. Matching is git's
own: the patterns go into a scratch repository's `.git/info/exclude` and
`git check-ignore --no-index --stdin -z -v -n` answers per path, so
negation, directory rules, anchoring and the parent-exclusion rule (a `!`
cannot re-include a file whose directory is excluded -- graphify's
`_is_ignored` walks ancestors the same way) are git's, not a copy of them.
The scratch repository lives in a temporary directory outside the repo, and
`core.excludesFile` is pointed at an empty file so the user's global
excludes can never make a path look excluded.

uncovered = denylisted(candidates) - excluded by the root `.graphifyignore`.

The denylist match folds case (`.ENV` and `Prod.PEM` are secrets too); the
`.graphifyignore` match does not, as graphify's does not on a case-sensitive
disk. `--write` closes that gap with the flagged path itself (below).

A directory git lists without its files (`sub/`: a nested repository or a
submodule) is `unknown` unless `.graphifyignore` excludes it. A symlink
`.graphifyignore` does not exclude by its own name is judged by that name and
by its target's repo-relative path (`dir/` for a directory); a target that
does not resolve, or resolves outside the repository, is `unknown`.

## An unknown stays unknown

Git missing or failing, a settings file that does not parse or has the wrong
shape, an unreadable denylist file or `.graphifyignore`, a nested
`.graphifyignore` (which could re-include with `!`; only the root one is
evaluated), a deny-all Read rule: each makes the status `unknown` with its
reason, exit 2. None of them reads as covered.

Accepted risk, not checked: graphify's line parser strips inline comments
and leading whitespace where git does not (git then reports "not excluded",
which fails closed); a nested `.gitignore` whose `!` re-includes a file for
graphify's walk; a Read rule written for a session started below the root.

## --write

Appends every denylisted pattern not already a line of `.graphifyignore`
(negations are never written: they could only re-include), then each path
still uncovered as an anchored literal (`/.ENV`), under one marked block,
then checks again. The full text is built before anything is opened, written
to a temporary file beside the target in the file's own line ending, given
the target's permission bits (a new file: 0666 less the umask), then moved
over it with `os.replace`, so a failed build leaves the file as it was. A
symlinked `.graphifyignore` is written through to the file it names.

Exit codes: `--check` 0 covered, 1 uncovered, 2 unknown. `--write` 0 covered
after the write, 1 still uncovered, 2 unknown or the write failed.
"""

import sys

sys.dont_write_bytecode = True

# Imported after the bytecode switch above, so no __pycache__ is written.
import argparse  # noqa: E402  pylint: disable=wrong-import-position
import json  # noqa: E402  pylint: disable=wrong-import-position
import os  # noqa: E402  pylint: disable=wrong-import-position
import re  # noqa: E402  pylint: disable=wrong-import-position
import subprocess  # noqa: E402  pylint: disable=wrong-import-position
import tempfile  # noqa: E402  pylint: disable=wrong-import-position

COVERED = "covered"
UNCOVERED = "uncovered"
UNKNOWN = "unknown"

BUILTIN_PATTERNS = (".env", ".env.*", "!.env.example", "*.pem", "*.key", "*.p12",
                    "*.pfx", "id_rsa*", "id_ed25519*")
DENYLIST_FILE = ".claude/secrets-denylist"
SETTINGS_FILES = (".claude/settings.json", ".claude/settings.local.json")
IGNORE_FILE = ".graphifyignore"
BLOCK_HEADER = "# crew: secrets denylist (crew_graph_ignore.py --write)"
FIX = "crew_graph_ignore.py --write"
SHOWN = 10
_DENY_ALL = {"*", "**", "/*", "/**", "**/*", "/**/*"}
_READ_RULE = re.compile(r"^Read(?:\((.*)\))?$", re.DOTALL)
_GIT_ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
_TIMEOUT = 60


class _Unknown(Exception):
    """A question this module could not answer; its message is the reason."""


def _run_git(git, cwd, args, stdin=None):
    try:
        done = subprocess.run([git, "-c", "core.fsmonitor=false"] + list(args), cwd=cwd,
                              input=stdin, capture_output=True, timeout=_TIMEOUT,
                              check=False, env=_GIT_ENV)
    except (OSError, subprocess.SubprocessError) as exc:
        raise _Unknown(f"git could not run ({type(exc).__name__}: {exc})") from exc
    return done


def _read(root, rel):
    """The file's text, None when it does not exist, or _Unknown when it
    exists and cannot be read -- absent and unreadable are different
    answers."""
    path = os.path.join(root, *rel.split("/"))
    if not os.path.lexists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return handle.read()
    except (OSError, ValueError) as exc:
        raise _Unknown(f"{rel} could not be read ({type(exc).__name__})") from exc


def _posix(path):
    path = os.path.abspath(path).replace("\\", "/")
    if re.match(r"^[A-Za-z]:", path):
        path = "/" + path[0].lower() + path[2:]
    return path.rstrip("/")


def _inside(absolute, root):
    """`absolute` (POSIX, from `//` or `~/`) as a root-anchored pattern, or
    None when it is outside the repository."""
    if absolute.startswith("**/") or absolute == "**":
        return absolute
    base = _posix(root)
    if absolute == base:
        return "/**"
    if absolute.startswith(base + "/"):
        return absolute[len(base):]
    return None


def translate_rule(rule, root):
    """`(patterns, skipped_reason, unknown_reason)` for one deny entry. A
    non-Read entry gives ([], None, None)."""
    if not isinstance(rule, str):
        return [], None, f"a permissions.deny entry is not a string: {rule!r}"
    match = _READ_RULE.match(rule.strip())
    if not match:
        return [], None, None
    # A Windows separator is an escape in a git pattern: `\x` would match
    # `x`, silently. `Read(.\\secrets\\**)` means `./secrets/**`.
    inner = (match.group(1) or "").strip().replace("\\", "/")
    if not inner or "\n" in inner:
        return [], None, f"{rule} denies every read, which no ignore file can express"
    if inner.startswith("!"):
        return [], "a carve-out only shrinks the denylist; ignored", None
    if inner.startswith("//"):
        rest = inner[2:]
        pattern = _inside(rest if rest.startswith("**") else "/" + rest.lstrip("/"), root)
        if pattern is None:
            return [], "outside the repository", None
        patterns = [pattern]
    elif inner == "~" or inner.startswith("~/"):
        pattern = _inside(_posix(os.path.expanduser(inner)), root)
        if pattern is None:
            return [], "outside the repository", None
        patterns = [pattern]
    elif inner.startswith("/"):
        patterns = [inner]
    else:
        rel = inner[2:] if inner.startswith("./") else inner
        patterns = [rel]
        if re.fullmatch(r"[^/*]+/\*\*", rel):
            patterns.append("**/" + rel)
    if any(p in _DENY_ALL for p in patterns):
        return [], None, f"{rule} denies every read, which no ignore file can express"
    return patterns, None, None


def _settings_patterns(root, rel):
    text = _read(root, rel)
    if text is None:
        return [], []
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise _Unknown(f"{rel} is not valid JSON") from exc
    if not isinstance(data, dict):
        raise _Unknown(f"{rel} is not a JSON object")
    perms = data.get("permissions", {})
    if not isinstance(perms, dict):
        raise _Unknown(f"{rel}: permissions is not an object")
    deny = perms.get("deny", [])
    if not isinstance(deny, list):
        raise _Unknown(f"{rel}: permissions.deny is not a list")
    patterns, skipped = [], []
    for rule in deny:
        found, skip, unknown = translate_rule(rule, root)
        if unknown:
            raise _Unknown(f"{rel}: {unknown}")
        if skip:
            skipped.append({"source": rel, "rule": rule, "reason": skip})
        patterns += found
    return patterns, skipped


def denylist(root):
    """`(patterns, sources, skipped, unknown)`. Never raises: a failure is
    the `unknown` reason, and `patterns` is then not to be trusted."""
    patterns, sources, skipped = list(BUILTIN_PATTERNS), ["built-in"], []
    try:
        text = _read(root, DENYLIST_FILE)
        if text is not None:
            patterns += [line for line in text.splitlines() if line.strip()]
            sources.append(DENYLIST_FILE)
        for rel in SETTINGS_FILES:
            found, skip = _settings_patterns(root, rel)
            if found or skip:
                sources.append(rel)
            patterns += found
            skipped += skip
    except _Unknown as exc:
        return patterns, sources, skipped, str(exc)
    return patterns, sources, skipped, None


def _toplevel(root, git):
    done = _run_git(git, root, ["rev-parse", "--show-toplevel"])
    if done.returncode != 0:
        raise _Unknown(f"{root} is not a git repository git can read")
    return done.stdout.decode("utf-8", "replace").strip()


def candidates(root, git="git"):
    """`(paths, nested_ignore_files)`: every tracked, untracked and ignored
    path on disk, and each `.graphifyignore` other than the root one.
    Raises _Unknown when git cannot list them."""
    done = _run_git(git, root, ["-c", "core.quotePath=false", "ls-files", "-z",
                                "--cached", "--others"])
    if done.returncode != 0:
        raise _Unknown("git could not list the repository's files")
    paths = sorted({p for p in done.stdout.decode("utf-8", "surrogateescape").split("\0")
                    if p and os.path.lexists(os.path.join(root, p.rstrip("/")))})
    nested = [p for p in paths if p != IGNORE_FILE and p.rsplit("/", 1)[-1] == IGNORE_FILE]
    return paths, nested


def _split(top, paths):
    """`(plain, opaque, links)`: files git lists, directories it lists
    without their files (a nested repository or a submodule, as `sub/`),
    and symlinks ({path: absolute path of the link})."""
    plain, opaque, links = [], [], {}
    for path in paths:
        full = os.path.join(top, *path.rstrip("/").split("/"))
        if os.path.islink(full):
            links[path.rstrip("/")] = full
        elif path.endswith("/") or os.path.isdir(full):
            opaque.append(path.rstrip("/") + "/")
        else:
            plain.append(path)
    return plain, opaque, links


def _link_target(top, path, full):
    """The repo-relative query for a symlink's target (`dir/` for a
    directory), or _Unknown when it does not resolve inside the repo."""
    real = os.path.realpath(full)
    if not os.path.exists(real):
        raise _Unknown(f"symlink {path} does not resolve, so what graphify would "
                       f"read through it is not known")
    rel = os.path.relpath(real, os.path.realpath(top)).replace(os.sep, "/")
    if rel == "." or rel == ".." or rel.startswith("../") or os.path.isabs(rel):
        raise _Unknown(f"symlink {path} resolves outside the repository, so what "
                       f"graphify would read through it is not known")
    return rel + "/" if os.path.isdir(real) else rel


def _judge(top, paths, patterns, lines, git):
    """`(denied, uncovered)` for the candidates `paths` under the denylist
    `patterns` and the `.graphifyignore` `lines`. Raises _Unknown."""
    plain, opaque, links = _split(top, paths)
    own = {p: p + "/" if os.path.isdir(full) else p for p, full in links.items()}
    excluded = _ignored(sorted(opaque + list(own.values())), lines, git)
    blind = [d for d in opaque if d not in excluded]
    if blind:
        raise _Unknown(f"{IGNORE_FILE} does not exclude {', '.join(blind[:SHOWN])}, a "
                       f"directory git lists without its files (a nested repository "
                       f"or submodule), so what graphify would read there is not known")
    # An unexcluded link is judged by its own name and by its target's.
    judged = {path: (query, _link_target(top, path, links[path]))
              for path, query in own.items() if query not in excluded}
    queries = set(plain).union(*judged.values())
    hits = _ignored(sorted(queries), patterns, git, fold_case=True)
    files = sorted(hits.intersection(plain))
    through = {path for path, pair in judged.items() if hits.intersection(pair)}
    uncovered = (set(files) - _ignored(files, lines, git)) | through
    return set(files) | through, sorted(uncovered)


def _ignored(paths, patterns, git, fold_case=False):
    """The subset of `paths` git's matcher excludes under `patterns`."""
    if not paths or not patterns:
        return set()
    with tempfile.TemporaryDirectory(prefix="crew-graph-ignore-") as scratch:
        if _run_git(git, scratch, ["init", "-q", "."]).returncode != 0:
            raise _Unknown("git could not create its scratch repository")
        empty = os.path.join(scratch, "empty-excludes")
        with open(os.path.join(scratch, ".git", "info", "exclude"), "w",
                  encoding="utf-8", newline="\n") as handle:
            handle.write("".join(p + "\n" for p in patterns))
        with open(empty, "w", encoding="utf-8", newline="\n"):
            pass
        stdin = "".join(p + "\0" for p in paths).encode("utf-8", "surrogateescape")
        done = _run_git(git, scratch, ["-c", f"core.excludesFile={empty}",
                                       "-c", f"core.ignoreCase={str(fold_case).lower()}",
                                       "check-ignore", "--no-index", "--stdin", "-z",
                                       "-v", "-n"], stdin=stdin)
    if done.returncode not in (0, 1):
        raise _Unknown("git check-ignore failed: "
                       + done.stderr.decode("utf-8", "replace").strip()[:200])
    fields = done.stdout.decode("utf-8", "surrogateescape").split("\0")
    out = set()
    for i in range(0, len(fields) - 3, 4):
        pattern, path = fields[i + 2], fields[i + 3]
        if pattern and not pattern.startswith("!"):
            out.add(path)
    return out


def _ignore_lines(root):
    text = _read(root, IGNORE_FILE)
    if text is None:
        return []
    return [line for line in text.splitlines() if line.strip()]


def coverage(root, git="git"):
    """`{"status", "uncovered", "denied", "reason", "sources", "skipped"}`.
    `status` is covered, uncovered or unknown; unknown whenever any step
    could not answer, never covered."""
    root = os.path.abspath(root)
    patterns, sources, skipped, why = denylist(root)
    result = {"status": UNKNOWN, "uncovered": [], "denied": 0, "reason": why,
              "sources": sources, "skipped": skipped}
    if why:
        return result
    try:
        top = _toplevel(root, git)
        paths, nested = candidates(top, git)
        if nested:
            result["reason"] = (f"nested {IGNORE_FILE} can re-include what the root one "
                                f"excludes, and only the root one is evaluated: "
                                f"{', '.join(nested[:SHOWN])}")
            return result
        denied, uncovered = _judge(top, paths, patterns, _ignore_lines(top), git)
    except _Unknown as exc:
        result["reason"] = str(exc)
        return result
    result.update(status=UNCOVERED if uncovered else COVERED, uncovered=uncovered,
                  denied=len(denied), reason=None)
    return result


def _block(patterns, eol="\n"):
    return BLOCK_HEADER + eol + "".join(p + eol for p in patterns)


def _literals(top, git, patterns, lines):
    """Each path still uncovered once `lines` are in place, as an anchored
    literal: the denylist folds case and coverage does not, so `.ENV` needs
    `/.ENV`. A path git would read as a pattern (`*?[\\`, a trailing space)
    is left out, so the check after the write still names it."""
    try:
        _denied, uncovered = _judge(top, candidates(top, git)[0], patterns, lines, git)
    except _Unknown:
        return []
    return ["/" + p for p in uncovered
            if not re.search(r"[*?\[\\]|\s$", p) and "/" + p not in lines]


def _mode(path):
    if os.path.exists(path):
        return os.stat(path).st_mode & 0o7777
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


def write(root, git="git"):
    """Append the missing positive patterns. Returns the patterns added.
    Raises _Unknown when the denylist cannot be built."""
    root = os.path.abspath(root)
    patterns, _sources, _skipped, why = denylist(root)
    if why:
        raise _Unknown(why)
    top = _toplevel(root, git)
    # A symlinked .graphifyignore is written through: replacing the link
    # with a regular file would leave the file it names untouched.
    target = os.path.realpath(os.path.join(top, IGNORE_FILE))
    lines = _ignore_lines(top)
    present = {line.strip() for line in lines}
    missing = []
    for pattern in patterns:
        if pattern.startswith("!") or pattern.strip() in present or pattern in missing:
            continue
        missing.append(pattern)
    missing += _literals(top, git, patterns, lines + missing)
    if not missing:
        return []
    before = b""
    if os.path.lexists(target):
        with open(target, "rb") as handle:
            before = handle.read()
    eol = b"\r\n" if b"\r\n" in before else b"\n"
    text = _block(missing, eol.decode())
    sep = b"" if not before or before.endswith(b"\n") else eol
    payload = before + sep + text.encode("utf-8")
    mode = _mode(target)
    handle, temp = tempfile.mkstemp(prefix=".graphifyignore.", dir=os.path.dirname(target))
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(payload)
        os.chmod(temp, mode)
        os.replace(temp, target)
    except OSError:
        if os.path.lexists(temp):
            os.unlink(temp)
        raise
    return missing


def render(result):
    """One line, `graph-ignore: ...`, naming paths only, never content."""
    if result["status"] == COVERED:
        return (f"graph-ignore: covered - {result['denied']} denylisted path(s) on disk, "
                f"all excluded by {IGNORE_FILE}")
    if result["status"] == UNCOVERED:
        paths = result["uncovered"]
        shown = ", ".join(paths[:SHOWN])
        if len(paths) > SHOWN:
            shown += f" (+{len(paths) - SHOWN} more)"
        return (f"graph-ignore: UNCOVERED - graphify would read {len(paths)} "
                f"secrets-denylisted path(s) {IGNORE_FILE} does not exclude: {shown}; "
                f"run {FIX}")
    return f"graph-ignore: unknown - {result['reason']}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--git", default="git", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.write:
        try:
            added = write(args.root, args.git)
        except (_Unknown, OSError, ValueError) as exc:
            print(f"graph-ignore: unknown - write failed, {IGNORE_FILE} unchanged: {exc}")
            return 2
        print(f"graph-ignore: added {len(added)} pattern(s) to {IGNORE_FILE}"
              + (f": {', '.join(added)}" if added else ""))
    result = coverage(args.root, args.git)
    print(json.dumps(result, indent=2) if args.json else render(result))
    return {COVERED: 0, UNCOVERED: 1}.get(result["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
