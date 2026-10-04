"""The three readers every crew script shares, and the repo-config resolver.

Split out of `crew_state.py` in 0.16.21 along with the endpoint ledger, which
had taken that module to pylint's `max-module-lines=3300` with five lines to
spare. These three live here rather than in either half because both halves
need them: putting them in `crew_endpoints` would make `crew_state` import a
git timeout from a module named for endpoints, and putting them in
`crew_state` would make the import run both ways.

`repo_config_dir` (T-0088) names the `.crew/` directory the repo config is read
from: the repository's own, or, in a linked worktree with no config of its
own, the main checkout's. Every Python reader of `.crew/config.json` or
`.crew/crew.json` opens `repo_config_file(root, name)` instead of joining the
path itself.

`crew_state` re-exports the three readers, so `crew_config` and
`crew_upgrade` keep reaching them as `crew_state.read_text` and friends.

`resolve_tool` / `require_tool` (L-1508) are how every crew script names an
external tool to `subprocess`: the path `shutil.which` resolves, never a bare
name. `plugin/crew/tests/test_tool_resolution.py` fails the build on a bare one.

Standard library only, and every read fails soft, for the reason `crew_state`
does: this runs from a SessionStart hook, where an exception breaks every
session opened in the repository.
"""

import errno
import os
import shutil
import subprocess

GIT_TIMEOUT = 10


# --- L-1508: run a tool the way it was found ---------------------------------------

def resolve_tool(name):
    """The executable `name` resolves to on PATH, or None when it does not.

    `shutil.which`, because it finds what bash, pwsh and the user's shell
    find. A bare name handed to subprocess on native Windows reaches
    CreateProcess, which ignores PATHEXT and tries only `name.exe`: a
    `name.cmd` earlier on PATH is skipped for a later `.exe`, so crew judged a
    different tool from the one the user runs -- T-0017's wrap-up veto read a
    clean tree through the wrong git and failed open. No cache: a lookup
    costs ~30us against ~1.8ms to spawn git (measured, Linux), and a cache
    would hide a PATH change inside one process, which the suite makes.
    """
    return shutil.which(name)


class ToolNotFound(FileNotFoundError):
    """`require_tool`'s "not on PATH": a FileNotFoundError, so every caller's
    existing `except OSError` takes the same path a bare name's ENOENT did."""


def require_tool(name):
    """`resolve_tool(name)`, or raise ToolNotFound naming the tool."""
    path = resolve_tool(name)
    if path is None:
        raise ToolNotFound(errno.ENOENT, f"{name} is not on PATH", name)
    return path


def read_text(path):
    """Return the file's text, or None if it cannot be read for any reason.

    utf-8-sig rather than utf-8: a BOM-prefixed file (Windows Notepad's
    default save) is otherwise valid utf-8 whose first character decodes as
    U+FEFF, which then makes json.loads reject an otherwise well-formed
    config as malformed. utf-8-sig strips a leading BOM when present and is
    a no-op on a plain utf-8 file, so every other reader here is unaffected.
    """
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            return handle.read()
    except (OSError, ValueError):
        # ValueError covers a path Python rejects before touching the disk (an
        # embedded NUL raises rather than returning ENOENT). Unreachable from a
        # real filesystem, but this module must never raise from a SessionStart
        # hook under any input, so the cheap catch beats the argument about
        # reachability.
        return None


def git_out(root, *args):
    """Stripped stdout of a git command, or None on any failure.

    Failure includes git being absent and root not being a repository. Both
    are ordinary: the hook runs wherever the user opens a session.
    """
    try:
        done = subprocess.run(
            (require_tool("git"),) + args, cwd=root, capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=GIT_TIMEOUT, check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    # Without an explicit encoding, `text=True` decodes with the platform's
    # default (cp1252 on a Windows console) -- a diff containing one
    # undecodable byte then raises UnicodeDecodeError out of subprocess.run
    # itself, and this function's never-raises contract is what every
    # SessionStart caller relies on. utf-8/errors="replace" never raises and
    # never returns None for `done.stdout` (unlike the cp1252 path, which
    # left it None and made the `.strip()` below an AttributeError instead
    # of the intended "no diff" result).
    return done.stdout.strip()


def dict_or_empty(value):
    """`value` when it is genuinely a dict, else `{}`.

    `(cfg.get(k) or {})` is the tempting idiom and it is wrong: it guards a
    MISSING or falsy value but hands a wrong-typed truthy one straight through,
    so `"graph": "oops"` reaches `.get()` on a str and raises AttributeError.
    From a SessionStart hook that breaks every session opened in the repo.
    """
    return value if isinstance(value, dict) else {}


# --- the repo config's directory (T-0088) ---------------------------------------------

CONFIG_NAMES = ("crew.json", "config.json")
SOURCE_OWN, SOURCE_MAIN, SOURCE_UNKNOWN = "own", "main checkout", "unknown"


def repo_config_dir(root):
    """(crew_dir, source, detail): the `.crew/` directory the repo config is read
    from. Own files win whole; a linked worktree with neither file reads the main
    checkout's; never merged; `unknown` when git cannot tell (see T-0088).

    `.crew/*` is gitignored, so a lane made with `git worktree add` starts with
    no config and, before this, read the defaults instead of the owner's
    settings (T-0072's gate: `scope.allowCliApproval` read False).

    `root` is a top-level: `.git` is looked for at `root` itself, so a
    subdirectory reads as `own` and inherits nothing. `.git` a directory, or
    missing, is `own` with no subprocess. `.git` a file is a linked worktree or
    a submodule; git names the common directory, and a submodule (git-dir ==
    common-dir) or a bare common directory (not named `.git`) has no main
    checkout, so it is `own` too. When git cannot answer, the source is
    `unknown`: nothing is inherited, and `detail` says why, so a caller shows
    that rather than an absent config. `detail` is the main checkout's path
    when the source is `main checkout`.
    """
    own = os.path.join(root, ".crew")
    if any(os.path.lexists(os.path.join(own, name)) for name in CONFIG_NAMES):
        return own, SOURCE_OWN, ""
    main_root, problem = _main_checkout(root)
    if problem:
        return own, SOURCE_UNKNOWN, problem
    if main_root is None:
        return own, SOURCE_OWN, ""
    main = os.path.join(main_root, ".crew")
    if any(os.path.lexists(os.path.join(main, name)) for name in CONFIG_NAMES):
        return main, SOURCE_MAIN, main_root
    return own, SOURCE_OWN, ""


def _main_checkout(root):
    """(main_root, problem): the main checkout of the linked worktree at `root`,
    or None when `root` is not one; `problem` is non-empty only when git could
    not tell.

    `.git` a directory, or missing, is not a linked worktree, with no
    subprocess. No `--path-format`: git before 2.31 does not know it and
    rev-parse echoes an unknown argument back as a line of its own, which read
    as "git could not tell" on every such git. Both paths are joined to `root`
    instead, git's cwd here, which leaves an absolute one unchanged.
    """
    if not os.path.isfile(os.path.join(root, ".git")):
        return None, ""
    out = git_out(root, "rev-parse", "--git-dir", "--git-common-dir")
    lines = (out or "").splitlines()
    if len(lines) != 2:
        return None, "this looks like a linked worktree, but git could not name its main checkout"
    real_git, real_common = (os.path.realpath(os.path.join(root, p)) for p in lines)
    if os.path.normcase(real_git) == os.path.normcase(real_common) \
            or os.path.basename(real_common) != ".git":
        return None, ""
    return os.path.dirname(real_common), ""


def shadowed_main_config(root):
    """The main checkout's `.crew/` when `root` is a linked worktree whose OWN
    config is in force while the main checkout has one too; else "".

    Own wins whole, by design, so this is not an error -- but it is invisible.
    Every crew <= 1.0.68 SessionStart heal wrote a default `.crew/config.json`
    into a lane that had none, and that default now shadows the owner's
    settings with nothing saying so (T-0088 review round 1). Status and config
    name it, so the owner can tell a chosen config from a heal-written one.
    """
    own = os.path.join(root, ".crew")
    if not any(os.path.lexists(os.path.join(own, name)) for name in CONFIG_NAMES):
        return ""
    main_root, _problem = _main_checkout(root)
    if main_root is None:
        return ""
    main = os.path.join(main_root, ".crew")
    if any(os.path.lexists(os.path.join(main, name)) for name in CONFIG_NAMES):
        return main
    return ""


def repo_config_file(root, name="config.json"):
    """`<the resolved .crew/>/<name>`: the path every repo-config reader opens."""
    return os.path.join(repo_config_dir(root)[0], name)


def repo_config_source_line(root):
    """One line for /crew:status and /crew:config naming the file in force;
    empty when the repo reads its own `.crew/` and that shadows nothing."""
    crew_dir, source, detail = repo_config_dir(root)
    if source == SOURCE_MAIN:
        path = os.path.join(crew_dir, "config.json")
        return (f"inherited from the main checkout ({path}) - this worktree has no crew "
                "config of its own; never merged")
    if source == SOURCE_UNKNOWN:
        return f"could not tell ({detail}) - read only this worktree's own .crew/"
    shadowed = shadowed_main_config(root)
    if shadowed:
        return shadow_note(shadowed)
    return ""


def shadow_note(main_crew_dir):
    """The one wording, for status and config, of an own config shadowing the
    main checkout's."""
    return (f"this worktree's own .crew/ is in force; the main checkout's ({main_crew_dir}) "
            "is not read (own wins whole, never merged). A default written by a crew <= 1.0.68 "
            "SessionStart heal shadows it too: delete this worktree's .crew/config.json "
            "(and .crew/crew.json) to inherit")
