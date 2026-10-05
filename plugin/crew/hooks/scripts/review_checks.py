"""Pre-review checks (L-0574): no new linter findings in the bundle, decided
before a review round is reserved.

    python3 review_checks.py --root . --manifest <scratch>/manifest.json

WHAT IS CHECKED. Exactly the files the review bundle changes (the manifest's
`entries`), with the linters `.crew/verify.json` lists under `preReview`:

    "preReview": {"linters": [
      {"tool": "ruff", "args": ["--extend-select", "S110,S112,BLE001"]},
      {"tool": "shellcheck", "command": ["uvx", "--from", "shellcheck-py==0.11.0.1",
                                          "shellcheck"], "args": ["-S", "warning"]},
      {"tool": "psscriptanalyzer", "rules": ["PSAvoidUsingEmptyCatchBlock"]},
      {"tool": "actionlint"}]}

Per linter, optional: `command` (argv; the default is the tool by name, ruff
through this Python), `args` (extra argv), `paths` (globs replacing the
tool's default file globs), `timeout` (seconds, default 300) and, for
psscriptanalyzer only, `rules` (the allowlist passed as `-IncludeRule`; the
default is PSScriptAnalyzer's own default set). No `preReview` key means no
checks are configured, and the caller says so.

NO NEW FINDINGS, AGAINST THE BUNDLE'S OWN BASE. Each changed file is linted
twice: its blob at the manifest's `base` (the old path for a rename; nothing
for an added file) and its blob in the bundle (`new_id`, the content the
reviewer is shown). Both copies sit at the same relative path in two
throwaway trees, beside a copy of the repo-root linter config, so the two runs
differ only in the file; that config is read from the bundle (its blob, or the
base blob when the bundle leaves it alone), never from the live working tree.
A finding is keyed by (path, rule, message) and
counted. Line numbers are left out, so a moved line is not new. A key whose
count went up is a NEW finding. The baseline is the committed base tree, so
it never needs regenerating and cannot go stale.

FOUR OUTCOMES, AND AN UNKNOWN IS NEVER A PASS. `pass` (ran, nothing new),
`fail` (ran, something new), `n/a` (no changed file matches this linter, so
the tool is not even looked for), and `could-not-check`. That last one covers
a tool that is not on PATH or will not start, a timeout, an exit status the
tool does not use for "ran", output that does not parse, a blob git cannot
read, a config entry this module does not understand, and a file the tool
could not parse on either side (ShellCheck SC1072, ruff `invalid-syntax`,
PSScriptAnalyzer `ParseError`, actionlint `syntax-check`), because then that
file was not checked, and a broken base would baseline new findings away.
`review_run.py` refuses a round on `fail` and on `could-not-check` (exit 9,
nothing reserved). `--allow-unverified` overrides only `could-not-check`, and
review.json records the override.

Exit codes of the CLI: 0 pass (or nothing configured or applicable), 1 new
findings, 3 could not check, 2 usage.
"""
import argparse
import collections
import errno
import json
import os
import re
import shutil
import secrets
import signal
import stat
import subprocess
import sys
import tempfile

import crew_ticket

PASS, FAIL, COULD_NOT, NA = "pass", "fail", "could-not-check", "n/a"
NOT_CONFIGURED, NOT_RECORDED = "not-configured", "not-recorded"
CONFIG_KEY = "preReview"
VERIFY_MAP = os.path.join(".crew", "verify.json")
# Class d (round-7 sweep): a record is per run, then per round. record()
# stages `prereview.run-<random>.json`; once `reserve` hands the run its round,
# bind_record() moves it to `prereview-<ticket>-r<N>.json` with the ticket and round
# inside, and finish reads the record of ITS round. Two runs sharing a scratch
# directory never overwrite each other (review round 6 FIX :788).
RESULT_FILE = "prereview-<ticket>-r<N>.json"
DEFAULT_TIMEOUT = 300
GIT_TIMEOUT = 60
# Never handed to a linter: it needs none of them (PYTHON-08).
_SECRET_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY", "APIKEY", "CREDENTIAL")
SHOWN = 40
EXIT_PASS, EXIT_NEW, EXIT_USAGE, EXIT_COULD_NOT = 0, 1, 2, 3

# Linter config the tools find by walking up from the file. Copied, as the
# bundle has it, into BOTH throwaway trees, so base and bundle are judged by
# the same rules - the ones this change ships with.
CONFIG_FILES = ("ruff.toml", ".ruff.toml", "pyproject.toml", ".shellcheckrc",
                os.path.join(".github", "actionlint.yaml"),
                os.path.join(".github", "actionlint.yml"))
SKIPPED_MODES = ("120000", "160000")  # a symlink's blob is its target; a submodule has none
_ZERO = "0" * 40
# Positions only, never other numbers (review round 2): "line 3", "lines
# 3-4", "column 9", "col 9", and a "L:C:" pair such as actionlint's
# "SC2086:info:2:28:". "requires 2 approvals" keeps its 2.
_POSITIONS = (
    (re.compile(r"\b(lines?|columns?|col)\s+\d+(?:\s*-\s*\d+)?", re.IGNORECASE), r"\1 N"),
    # Only a ShellCheck position FIELD, `SC2086:info:2:28:` as actionlint
    # quotes it (review round 8 BLOCK :97): any other `N:N:` is a value - a
    # time `12:30:00`, a port pair `8080:80:`, a ratio `16:9:` - and a
    # changed value is a new finding.
    (re.compile(r"\b(SC\d{4}:(?:error|warning|info|style):)\d+:\d+(?=:)"), r"\1N:N"),
)

TOOLS = {
    "ruff": {"globs": ("**/*.py",)},
    "shellcheck": {"globs": ("**/*.sh", "**/*.bash")},
    "psscriptanalyzer": {"globs": ("**/*.ps1", "**/*.psm1", "**/*.psd1")},
    "actionlint": {"globs": (".github/workflows/*.yml", ".github/workflows/*.yaml")},
}
# Class c (round-7 sweep): the keys each tool's runner actually reads. A key
# a runner would ignore (psscriptanalyzer has no `args`) is rejected, never
# accepted and dropped; `test_class_c_every_accepted_key_is_honoured` proves
# every key listed here reaches the run.
_COMMON_KEYS = {"tool", "command", "paths", "timeout"}
TOOL_KEYS = {"ruff": _COMMON_KEYS | {"args"}, "shellcheck": _COMMON_KEYS | {"args"},
             "actionlint": _COMMON_KEYS | {"args"},
             "psscriptanalyzer": _COMMON_KEYS | {"rules"}}
LINTER_KEYS = set().union(*TOOL_KEYS.values())
BLOCK_KEYS = {"linters"}  # nothing else, not even a `_note`: an unknown key fails closed

# Read by pwsh with -File: the list of files and the rule allowlist arrive as
# files, so no path or rule name is ever quoted into a command line.
_PSSA_SCRIPT = r"""param([string]$ListFile, [string]$RulesFile)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    Import-Module PSScriptAnalyzer -ErrorAction Stop
    # Both lists are JSON (review round 7 BLOCK :679): a newline in a file
    # name split the old one-name-per-line list into names of clean files.
    $rules = @(Get-Content -Raw -Encoding utf8 -LiteralPath $RulesFile | ConvertFrom-Json)
    $known = @(Get-ScriptAnalyzerRule | ForEach-Object { $_.RuleName })
    $unknown = @($rules | Where-Object { $known -notcontains $_ })
    if ($unknown.Count -gt 0) {
        # -IncludeRule ignores a name it does not know: a rule that silently never runs.
        [Console]::Error.WriteLine("psscriptanalyzer: unknown rule(s): " + ($unknown -join ', '))
        exit 3
    }
    $rows = foreach ($path in @(Get-Content -Raw -Encoding utf8 -LiteralPath $ListFile | ConvertFrom-Json)) {
        # -Path takes wildcards: a name with [ ] would match nothing and
        # read as clean, so the name is escaped to match only itself.
        $params = @{ Path = [System.Management.Automation.WildcardPattern]::Escape($path) }
        if ($rules.Count -gt 0) { $params.IncludeRule = $rules }
        foreach ($r in @(Invoke-ScriptAnalyzer @params)) {
            [pscustomobject]@{ file = $path; rule = [string]$r.RuleName;
                               severity = [string]$r.Severity; message = [string]$r.Message }
        }
    }
    [Console]::Out.WriteLine((ConvertTo-Json -InputObject @($rows) -Depth 3 -Compress))
    exit 0
} catch {
    [Console]::Error.WriteLine("psscriptanalyzer: " + $_.Exception.Message)
    exit 3
}
"""


# C0, DEL, C1 and the Unicode line/paragraph separators: anything that can
# start a new line on a terminal or in a log (review round 7 FIX :847).
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029\ud800-\udfff]")


def one_line(text):
    """`text` with every control character escaped, so a path, rule, message
    or error the tool or the repo chose can never print a line of its own.
    A lone surrogate is escaped too (review round 9 FIX :165), so a strict
    UTF-8 stream never raises on it."""
    return _CONTROL.sub(lambda m: f"\\x{ord(m.group()):02x}" if ord(m.group()) < 0x100
                        else f"\\u{ord(m.group()):04x}", str(text))


class CouldNotCheck(Exception):
    """The check did not run to a result. Never read as a pass."""


class NotRegularFile(OSError):
    """A path that exists but is not a regular file: a symlink, FIFO, device
    or directory. Every caller reads it as could-not-check."""


_READ_FLAGS = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
               | getattr(os, "O_BINARY", 0))
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_WALK_BY_FD = (os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd
               and hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW"))


def _not_plain(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def read_regular(path, base):
    """The bytes of `path`, which must be a regular file inside `base`, the
    directory the caller trusts (the repo root, or the scratch directory):
    the ONLY file read in this module and in review_run.py (class b).

    FileNotFoundError when it, or a directory on the way, is absent.
    NotRegularFile when it lies outside `base`, when ANY component between
    `base` and it is a symlink or reparse point (review round 7 BLOCK :172:
    a symlinked `.crew` led to another directory's map), or when it is a
    symlink, FIFO, device or directory itself. Where the OS has dir_fd, each
    directory is opened O_NOFOLLOW from the one before, so no component can
    be swapped for a link between the check and the open; elsewhere
    (Windows) each component is lstat-ed. The file itself is lstat-ed, opened
    O_NOFOLLOW|O_NONBLOCK and re-checked by fstat against the same inode, so
    it is never followed and a FIFO never blocks. `base` itself is taken as
    given: it is where the operator chose to work."""
    base = os.path.abspath(base)
    rel = os.path.relpath(os.path.abspath(path), base)
    parts = rel.split(os.sep)
    if rel in (os.curdir, os.pardir) or os.path.isabs(rel) or parts[0] == os.pardir:
        raise NotRegularFile(errno.EINVAL, f"not inside {base}", path)
    if _WALK_BY_FD:
        fd = _walk_to_parent(base, parts[:-1], path)
        try:
            before = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
            _regular_or_raise(before, path)
            leaf = os.open(parts[-1], _READ_FLAGS, dir_fd=fd)
        finally:
            os.close(fd)
    else:
        current = base
        for part in parts[:-1]:
            current = os.path.join(current, part)
            info = os.lstat(current)
            if _not_plain(info) or not stat.S_ISDIR(info.st_mode):
                raise NotRegularFile(errno.EINVAL, f"{current} is a link or not a directory",
                                     path)
        before = os.lstat(path)
        _regular_or_raise(before, path)
        leaf = os.open(path, _READ_FLAGS)
    return _read_fd(leaf, before, path)


def _walk_to_parent(base, dirs, path):
    """An fd for the directory holding `path`, every step opened O_NOFOLLOW."""
    fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in dirs:
            try:
                step = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise NotRegularFile(errno.EINVAL, f"{part} is a symlink or not a "
                                                       "directory", path) from exc
                raise
            os.close(fd)
            fd = step
    except BaseException:
        os.close(fd)
        raise
    return fd


def _regular_or_raise(info, path):
    if not stat.S_ISREG(info.st_mode) or _not_plain(info):
        raise NotRegularFile(errno.EINVAL, "not a regular file", path)


def _read_fd(fd, before, path):
    try:
        after = os.fstat(fd)
        if not stat.S_ISREG(after.st_mode) or (after.st_dev, after.st_ino) != (
                before.st_dev, before.st_ino):
            raise NotRegularFile(errno.EINVAL, "changed while being opened", path)
        chunks = []
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(fd)


def resolve_executable(name):
    """The absolute path of an executable (class a, round-7 sweep): the ONLY
    way this module and review_run.py find a program. An absolute `name` must
    be a regular file; a bare name is looked up on the ABSOLUTE PATH entries
    only. Never the current directory: shutil.which searches it first on
    Windows, and a relative PATH entry (`.`) does the same anywhere. A relative
    path such as `./tool` is refused. None when not found."""
    if os.path.isabs(name):
        return name if os.path.isfile(name) else None
    if os.sep in name or (os.altsep and os.altsep in name):
        return None
    dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d and os.path.isabs(d)]
    if os.name != "nt":
        return shutil.which(name, path=os.pathsep.join(dirs)) if dirs else None
    exts = [e for e in (os.environ.get("PATHEXT") or ".COM;.EXE").split(";") if e]
    has_ext = os.path.splitext(name)[1].upper() in (e.upper() for e in exts)
    candidates = [name] if has_ext else [name + ext for ext in exts]
    for folder in dirs:
        for candidate in candidates:
            path = os.path.join(folder, candidate)
            if os.path.isfile(path):
                return path
    return None


def taskkill():
    """%SystemRoot%\\System32\\taskkill.exe through the resolver, or None: no
    absolute SystemRoot, no taskkill (never a bare name)."""
    root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
    if not root or not os.path.isabs(root):
        return None
    return resolve_executable(os.path.join(root, "System32", "taskkill.exe"))


def _base_modes(root, base, rels):
    """{relative path: git mode} for those of `rels` the base commit has."""
    if _git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode != 0:
        raise CouldNotCheck(f"the manifest's base {base[:12]} is not a commit git can read")
    listing = _git(root, "ls-tree", "-z", base, "--", *rels)
    if listing.returncode != 0:
        raise CouldNotCheck(f"git cannot list the base tree: "
                            f"{listing.stderr.decode('utf-8', 'replace').strip()}")
    modes = {}
    for record in listing.stdout.decode("utf-8", "surrogateescape").split("\0"):
        if record:
            meta, _, name = record.partition("\t")
            modes[name] = meta.split(" ", 1)[0]
    return modes


def _map_bytes(root, manifest):
    """The verify map AS THE BUNDLE HAS IT (review round 5): the bundle's
    blob when the bundle adds, changes, deletes or renames it away, else the
    base commit's. Only a map git does not track at all (an ignored
    `.crew/`) is read from the working tree, because no bundle can carry it.
    None when the bundle has no map."""
    rel = VERIFY_MAP.replace(os.sep, "/")
    entries = manifest.get("entries") or []
    for entry in entries:
        if entry.get("path") == rel:
            if entry.get("status") == "D":
                return None
            if entry.get("new_mode") in SKIPPED_MODES:
                raise CouldNotCheck(f"{rel} is a symlink or submodule in the bundle")
            return _git_blob(root, entry["new_id"])
    if any(e.get("status") == "R" and e.get("old_path") == rel for e in entries):
        return None
    mode = _base_modes(root, manifest["base"], [rel]).get(rel)
    if mode in SKIPPED_MODES:
        raise CouldNotCheck(f"{rel} is a symlink or submodule in the base commit")
    if mode is not None:
        return _git_blob(root, f"{manifest['base']}:{rel}")
    try:
        return read_regular(os.path.join(root, VERIFY_MAP), root)
    except FileNotFoundError:
        return None
    except OSError as exc:  # NotRegularFile included: never "none configured"
        raise CouldNotCheck(f"cannot read the untracked map: {exc}") from exc


def load_config(root, manifest):
    """(linters, None), (None, None) when nothing is configured, or
    (None, problem) when the map or its `preReview` key cannot be read.
    The map is the bundle's (`_map_bytes`), never a later working tree."""
    try:
        raw = _map_bytes(root, manifest)
    except CouldNotCheck as exc:
        return None, f"{VERIFY_MAP} could not be read: {exc}"
    if raw is None:
        return None, None
    try:
        data = strict_json(raw.decode("utf-8"))
    except ValueError as exc:  # UnicodeDecodeError is a ValueError
        return None, f"{VERIFY_MAP} could not be read: {exc}"
    if not isinstance(data, dict):
        # Valid JSON that is not an object is a broken map, not an absent key.
        return None, f"{VERIFY_MAP} is not a JSON object (it holds {type(data).__name__})"
    if CONFIG_KEY not in data:
        return None, None
    block = data[CONFIG_KEY]
    linters = block.get("linters") if isinstance(block, dict) else None
    if not isinstance(linters, list) or not linters:
        return None, f'{VERIFY_MAP} "{CONFIG_KEY}" needs a non-empty "linters" list'
    problems = []
    unknown_block = sorted(set(block) - BLOCK_KEYS)
    if unknown_block:
        problems.append(f"{CONFIG_KEY}: unknown key(s) {', '.join(unknown_block)}")
    for index, spec in enumerate(linters):
        where = f'{CONFIG_KEY}.linters[{index}]'
        if not isinstance(spec, dict) or not isinstance(spec.get("tool"), str) \
                or spec["tool"] not in TOOLS:
            problems.append(f"{where}: tool must be one of {', '.join(sorted(TOOLS))}")
            continue
        unknown = sorted(set(spec) - LINTER_KEYS)
        if unknown:
            problems.append(f"{where}: unknown key(s) {', '.join(unknown)}")
        unused = sorted((set(spec) & LINTER_KEYS) - TOOL_KEYS[spec["tool"]])
        if unused:
            problems.append(f"{where}: {spec['tool']} does not use {', '.join(unused)}")
        # A key that is PRESENT is checked, so an explicit null is a problem,
        # never "use the default" (review round 6 FIX :225).
        for key in ("command", "args", "paths", "rules"):
            if key in spec and not (isinstance(spec[key], list) and spec[key]
                                    and all(isinstance(v, str) and v for v in spec[key])):
                problems.append(f"{where}: {key} must be a non-empty list of strings")
            elif key == "rules" and key in spec and any(_CONTROL.search(v) for v in spec[key]):
                # Neighbour of review round 7 BLOCK :679: a rule name is one name.
                problems.append(f"{where}: rules must not hold a control character")
        if "timeout" in spec and not (isinstance(spec["timeout"], int)
                                      and not isinstance(spec["timeout"], bool)
                                      and spec["timeout"] > 0):
            problems.append(f"{where}: timeout must be a positive integer")
    if problems:
        return None, "; ".join(problems)
    return linters, None


def _name(spec):
    return spec["tool"]


def _git(root, *args):
    git = resolve_executable("git")
    if not git:
        raise CouldNotCheck("git is not on an absolute PATH entry")
    try:
        return subprocess.run([git, *args], cwd=root, capture_output=True,
                              stdin=subprocess.DEVNULL, timeout=GIT_TIMEOUT, check=False)
    except subprocess.TimeoutExpired as exc:
        raise CouldNotCheck(f"git {args[0]} timed out after {GIT_TIMEOUT}s") from exc
    except OSError as exc:
        raise CouldNotCheck(f"could not start git: {exc}") from exc


def _git_blob(root, blob):
    proc = _git(root, "cat-file", "blob", blob)
    if proc.returncode != 0:
        raise CouldNotCheck(f"git cannot read blob {blob[:12]}: "
                            f"{proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout


def changed_files(manifest):
    """The bundle's entries a linter could read: not deleted, not a symlink
    (its blob is a link target, not a script) and not a submodule."""
    rows = []
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("its entries are not a list")
    for entry in entries:
        if not (isinstance(entry, dict) and all(
                isinstance(entry.get(k), str) and entry.get(k)
                for k in ("status", "path", "new_id"))):
            raise ValueError(f"an entry is not the shape review_patch writes: {entry!r:.200}")
        # A file git calls binary is still linted (a UTF-16 .ps1 is one): the
        # tool, not git's heuristic, decides whether it can read it.
        # Judged by the NEW mode only: a submodule or symlink the bundle turns
        # into a regular file is a file to lint (review round 5).
        if entry.get("status") == "D":
            continue
        if entry.get("new_mode") in SKIPPED_MODES:
            continue
        rows.append(entry)
    return rows


def _selected(spec, entries):
    globs = spec.get("paths") or TOOLS[spec["tool"]]["globs"]
    return [e for e in entries if any(crew_ticket.path_matches(e["path"], g) for g in globs)]


def _inside(tmp, side, rel):
    """tmp/side/rel, refused when rel would land outside tmp/side (an absolute
    path or `..` in a tampered manifest)."""
    root = os.path.realpath(os.path.join(tmp, side))
    target = os.path.realpath(os.path.join(root, rel))
    if os.path.isabs(rel) or os.path.commonpath([root, target]) != root:
        raise CouldNotCheck(f"the manifest names a path outside the tree: {rel!r}")
    return target


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def _config_blobs(root, manifest):
    """{relative config path: bytes} as the BUNDLE has them: the entry's
    bundle blob when the bundle changes the file, else the base blob (then
    identical to the bundle's). Never the live working tree, which may have
    moved on since the bundle was built."""
    entries = manifest.get("entries") or []
    changed = {e.get("path"): e for e in entries}
    # A rename removes its old path from the bundle: a config renamed away is
    # gone, and its base blob must not come back to suppress a new finding.
    renamed_away = {e.get("old_path") for e in entries if e.get("status") == "R"}
    base = manifest["base"]
    at_base = _base_modes(root, base, [name.replace(os.sep, "/") for name in CONFIG_FILES])
    found = {}
    for name in CONFIG_FILES:
        rel = name.replace(os.sep, "/")
        entry = changed.get(rel)
        if entry is not None:
            if entry.get("status") != "D":
                # A symlink's blob is its target text, never a config (round 5).
                if entry.get("new_mode") in SKIPPED_MODES:
                    raise CouldNotCheck(f"the linter config {rel} is a symlink or submodule "
                                        "in the bundle")
                found[rel] = _git_blob(root, entry["new_id"])
            continue
        if rel in at_base and rel not in renamed_away:
            if at_base[rel] in SKIPPED_MODES:
                raise CouldNotCheck(f"the linter config {rel} is a symlink or submodule "
                                    "in the base commit")
            found[rel] = _git_blob(root, f"{base}:{rel}")
    return found


def _materialise(root, entries, configs, tmp):
    """Write each entry's base and bundle blobs under tmp/base and tmp/head at
    the entry's (new) path, and the bundle's linter config into both. Returns
    the relative paths that have a base."""
    with_base = set()
    for side in ("base", "head"):
        for rel, data in configs.items():
            _write(_inside(tmp, side, rel), data)
    for entry in entries:
        rel = entry["path"]
        _write(_inside(tmp, "head", rel), _git_blob(root, entry["new_id"]))
        old = entry.get("old_id") or _ZERO
        # A symlink's or gitlink's old blob is not this file's base text:
        # the file then has no base, as if added (review round 5).
        if entry.get("status") != "A" and old != _ZERO \
                and entry.get("old_mode") not in SKIPPED_MODES:
            _write(_inside(tmp, "base", rel), _git_blob(root, old))
            with_base.add(rel)
    return with_base


def _command(spec):
    argv = list(spec.get("command") or [])
    if not argv:
        argv = {"ruff": [sys.executable, "-m", "ruff"],
                "psscriptanalyzer": ["pwsh"]}.get(spec["tool"], [spec["tool"]])
    exe = resolve_executable(argv[0])
    if not exe:
        raise CouldNotCheck(f"{argv[0]} is not on PATH (absolute entries only, never the "
                            f"current directory; command: {' '.join(argv)})")
    if os.path.splitext(exe)[1].lower() in (".cmd", ".bat"):
        # cmd.exe would re-parse every file name argument (PYTHON-06).
        raise CouldNotCheck(f"{exe} is a batch-file shim; name the real executable in `command`")
    return [os.path.abspath(exe)] + argv[1:]


def _child_env(tmp):
    """The linter's environment: a copy with secrets dropped, and an empty
    XDG_CONFIG_HOME so a user-level ruff or ShellCheck config cannot judge one
    machine's bundle differently from another's (PYTHON-08). HOME is kept:
    uvx's cache and PowerShell's user module path live under it."""
    env = {k: v for k, v in os.environ.items()
           if not any(marker in k.upper() for marker in _SECRET_MARKERS)}
    config = os.path.join(tmp, "xdg-config")
    os.makedirs(config, exist_ok=True)
    env["XDG_CONFIG_HOME"] = config
    return env


_REAP_SECONDS = 5
_WINDOWS = os.name == "nt"
_CREATE_SUSPENDED = 0x00000004
_KILL_ON_JOB_CLOSE = 0x00002000
_EXTENDED_LIMIT_INFORMATION = 9
_BASIC_ACCOUNTING_INFORMATION = 1


class WindowsJob:
    """A Windows job object holding a process and everything it starts
    (review round 8 FIX :574): `taskkill /T /PID` walks parent pids, so it
    cannot reach a child whose parent already exited, and that child kept
    the output pipe open. A job holds the child whatever its parent does.

    The process is started suspended and resumed only once it is in the job,
    so nothing it starts can be born outside it. kill_on_close also ends the
    job when its last handle closes (this process dying included)."""

    def __init__(self, kill_on_close):
        import ctypes  # pylint: disable=import-outside-toplevel
        from ctypes import wintypes  # pylint: disable=import-outside-toplevel
        self._ctypes = ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._ntdll = ctypes.WinDLL("ntdll")
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                  ctypes.c_void_p, wintypes.DWORD,
                                                  ctypes.c_void_p]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
        self._k32 = k32
        self._handle = k32.CreateJobObjectW(None, None)
        if not self._handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        if kill_on_close:
            class _Basic(ctypes.Structure):  # JOBOBJECT_BASIC_LIMIT_INFORMATION
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                            ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD),
                            ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t),
                            ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t),
                            ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class _Extended(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
                _fields_ = [("BasicLimitInformation", _Basic),
                            ("IoInfo", ctypes.c_uint64 * 6),
                            ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]
            info = _Extended()
            info.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(self._handle, _EXTENDED_LIMIT_INFORMATION,
                                               ctypes.byref(info), ctypes.sizeof(info)):
                error = ctypes.get_last_error()
                self.close()
                raise OSError(error, "SetInformationJobObject failed")

    def adopt(self, proc):
        """Put the suspended `proc` in the job, then let it run."""
        handle = int(proc._handle)  # pylint: disable=protected-access
        if not self._k32.AssignProcessToJobObject(self._handle, handle):
            raise OSError(self._ctypes.get_last_error(), "AssignProcessToJobObject failed")
        if self._ntdll.NtResumeProcess(handle) != 0:
            raise OSError(errno.EIO, "NtResumeProcess failed")

    def terminate(self):
        self._k32.TerminateJobObject(self._handle, 1)

    def active_processes(self):
        """How many processes are in the job now (L-0527 group review: Kimi
        waits for its job to empty); OSError when Windows will not say."""
        ctypes = self._ctypes
        from ctypes import wintypes  # pylint: disable=import-outside-toplevel

        class _Accounting(ctypes.Structure):  # JOBOBJECT_BASIC_ACCOUNTING_INFORMATION
            _fields_ = [("TotalUserTime", ctypes.c_int64),
                        ("TotalKernelTime", ctypes.c_int64),
                        ("ThisPeriodTotalUserTime", ctypes.c_int64),
                        ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                        ("TotalPageFaultCount", wintypes.DWORD),
                        ("TotalProcesses", wintypes.DWORD),
                        ("ActiveProcesses", wintypes.DWORD),
                        ("TotalTerminatedProcesses", wintypes.DWORD)]
        info = _Accounting()
        if not self._handle or not self._k32.QueryInformationJobObject(
                self._handle, _BASIC_ACCOUNTING_INFORMATION, ctypes.byref(info),
                ctypes.sizeof(info), None):
            raise OSError(ctypes.get_last_error(), "QueryInformationJobObject failed")
        return info.ActiveProcesses

    def close(self):
        if self._handle:
            self._k32.CloseHandle(self._handle)
            self._handle = None


def new_job(kill_on_close):
    """A WindowsJob; a seam the tests replace on POSIX."""
    return WindowsJob(kill_on_close)


def _group_flags():
    """Popen keywords that put the linter in a group of its own: suspended in
    a new process group on Windows (resumed by WindowsJob.adopt), a new
    session elsewhere."""
    if _WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | _CREATE_SUSPENDED}
    return {"start_new_session": True}


def _kill_tree(proc, job):
    """Kill the linter and everything it started. subprocess.run kills only
    the direct child, and on Windows then waits for EOF on pipes a
    grandchild may hold open forever (review round 4). On Windows the job
    ends every process in it, a child whose parent already exited included
    (review round 8)."""
    try:
        if job is not None:
            job.terminate()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass  # already gone: proc.kill() below still runs
    try:
        proc.kill()
    except OSError:
        pass  # already exited


def _spawn(argv, cwd, timeout):
    env = _child_env(cwd)
    job = None
    if _WINDOWS:
        try:
            job = new_job(kill_on_close=True)
        except OSError as exc:
            # Without a job a timeout cannot promise to end the whole tree.
            raise CouldNotCheck(f"could not make a job object for {argv[0]}: {exc}") from exc
    try:
        return _run_in(job, argv, cwd, timeout, env)
    finally:
        if job is not None:
            job.close()


def _run_in(job, argv, cwd, timeout, env):
    try:
        # surrogateescape: tool output carries paths, which must round-trip.
        # Not a `with` block: on a timeout the group is killed before any wait.
        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="surrogateescape",
            stdin=subprocess.DEVNULL, env=env, **_group_flags())
    except OSError as exc:
        raise CouldNotCheck(f"could not start {argv[0]}: {exc}") from exc
    if job is not None:
        try:
            job.adopt(proc)
        except OSError as exc:
            proc.kill()
            proc.communicate()
            raise CouldNotCheck(f"could not put {argv[0]} in its job object: {exc}") from exc
    try:
        # The timeout covers EOF too: a child left holding stdout after the
        # linter exits is a timeout, never a wait without end.
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _kill_tree(proc, job)
        try:
            proc.communicate(timeout=_REAP_SECONDS)
        except subprocess.TimeoutExpired:
            for pipe in (proc.stdout, proc.stderr):
                pipe.close()
        raise CouldNotCheck(f"timed out after {timeout}s") from exc
    # A linter that exited cleanly may still have left children behind. On
    # Windows the job ends them by handle. On POSIX its group is signalled
    # only while the leader is unreaped (review round 9 FIX :727, review_run's
    # guard): communicate() has reaped it here, so its group id may already
    # belong to an unrelated process, and nothing is signalled.
    if job is not None:
        job.terminate()
    elif proc.returncode is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass  # the group is empty: nothing was left behind
    return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)


def _rows(proc, ok_codes, tool, extract):
    """(rows, bad): the rows `extract` reads from the tool's output and, when
    the exit status is not one the tool promises, a bad row naming it.

    Rows printed beside an unexpected exit are KEPT (review round 7 BLOCK
    :630), so a NEW finding among them still FAILs, which --allow-unverified
    never overrides; with nothing new the exit makes it could-not-check.
    Output that does not parse is CouldNotCheck, naming the exit too."""
    odd = None
    if proc.returncode not in ok_codes:
        tail = " ".join((proc.stderr or proc.stdout or "").strip().splitlines()[-3:])
        odd = f"{tool} exited {proc.returncode}: {tail[:400] or 'no output'}"
    try:
        rows = extract(proc.stdout or "")
    except CouldNotCheck as exc:
        if odd:
            raise CouldNotCheck(f"{odd}; {exc}") from exc
        raise
    return rows, ([_BadRow(None, odd, "exit")] if odd else [])


def _text(row, key, tool):
    """A non-empty string field of a row (review round 7 BLOCK :664): a
    missing kind, rule or code is never filled with a default."""
    value = row.get(key) if isinstance(row, dict) else None
    if not isinstance(value, str) or not value:
        raise CouldNotCheck(f"{tool} reported a row with no {key}")
    return value


def _message(row, tool):
    """The row's message, which every format above carries: a row without
    one is a partial answer, never an empty-message finding."""
    message = row.get("message") if isinstance(row, dict) else None
    if not isinstance(message, str):
        raise CouldNotCheck(f"{tool} reported a row with no message: {row!r:.200}")
    return message


class _BadRow:
    """A row the checks could not read. Yielded in place of raising, so the
    rows already read are kept (review round 4). `where` is (side, rel) when
    the row names a file inside the trees, else None."""
    __slots__ = ("where", "reason", "kind")

    def __init__(self, where, reason, kind="row"):
        self.where, self.reason, self.kind = where, reason, kind


_ROW_ERRORS = (CouldNotCheck, KeyError, TypeError, AttributeError, ValueError)


def _each(rows, tool, tmp, locate, parse):
    for row in rows:
        try:
            yield parse(row)
        except _ROW_ERRORS as exc:
            try:
                where = _split(tmp, locate(row))
            except _ROW_ERRORS:
                where = None
            yield _BadRow(where, f"{tool} reported a row it could not read "
                                 f"({_detail(exc)}): {row!r:.200}")


def _consistent(proc, rows, tool):
    """Exit 1 is the tool's own "findings" status and 0 its "none": output
    that contradicts the status is a partial answer, not a clean one. It is
    yielded as a bad row naming no file, so the rows the tool did print are
    still read and a NEW finding among them still FAILs (review round 4)."""
    if (proc.returncode == 1) != bool(rows):
        yield _BadRow(None, f"{tool} exited {proc.returncode} but reported {len(rows)} "
                            "finding(s); the status and the output disagree")


def _unique_keys(pairs):
    keys = [key for key, _ in pairs]
    repeated = sorted({key for key in keys if keys.count(key) > 1})
    if repeated:
        raise ValueError(f"duplicate key(s) {', '.join(map(repr, repeated))}")
    return dict(pairs)


def strict_json(text):
    """json.loads that refuses a duplicate key (review round 9 BLOCK :810):
    `{"comments": [finding], "comments": []}` keeps only the empty list, so
    whichever copy came last would silently win."""
    return json.loads(text, object_pairs_hook=_unique_keys)


def _loads(text, tool):
    try:
        return strict_json(text)
    except ValueError as exc:
        raise CouldNotCheck(f"{tool} output is not the JSON it promises: {exc}; "
                            f"output began {text[:120]!r}") from exc


def _split(tmp, path):
    """(side, relative path) for a file inside one of the two trees."""
    rel = os.path.relpath(os.path.abspath(path), tmp).replace(os.sep, "/")
    side, _, rest = rel.partition("/")
    if side not in ("base", "head") or not rest:
        raise CouldNotCheck(f"the tool reported a file outside the checked trees: {path}")
    return side, rest


def _run_ruff(argv, spec, tmp, files, timeout):
    # E902 (the file could not be read) is selected whatever the config says,
    # or an unreadable file would be reported as nothing at all.
    proc = _spawn(argv + ["check", "--output-format", "json", "--exit-zero", "--no-cache",
                          "--extend-select", "E902"]
                  + list(spec.get("args") or []) + files, tmp, timeout)
    def extract(text):
        rows = _loads(text, "ruff")
        if not isinstance(rows, list):
            raise CouldNotCheck("ruff output is not a list")
        return rows
    rows, odd = _rows(proc, (0,), "ruff", extract)
    yield from odd
    def parse(row):
        # A null code is ruff's own spelling of a syntax error; a MISSING code
        # is a row it did not finish (review round 7 BLOCK :664).
        if row["code"] is None:
            code = "invalid-syntax"
        else:
            code = _text(row, "code", "ruff")
        # invalid-syntax: parsing stopped; E902: the file could not be read.
        return _split(tmp, row["filename"]) + (code, _message(row, "ruff"),
                                                code in ("invalid-syntax", "E902"))
    yield from _each(rows, "ruff", tmp, lambda row: row["filename"], parse)


def _run_shellcheck(argv, spec, tmp, files, timeout):
    # One rc file for both trees, the bundle's, or none: never one found by
    # walking up past the throwaway tree, or the user's ~/.shellcheckrc.
    rcfile = os.path.join(tmp, "head", ".shellcheckrc")
    rc_args = ["--rcfile", rcfile] if os.path.isfile(rcfile) else ["--norc"]
    proc = _spawn(argv + ["-f", "json1"] + rc_args + list(spec.get("args") or []) + files, tmp,
                  timeout)
    def extract(text):
        data = _loads(text, "shellcheck")
        rows = data.get("comments") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise CouldNotCheck("shellcheck json1 output has no comments list")
        return rows
    rows, odd = _rows(proc, (0, 1), "shellcheck", extract)
    yield from odd or _consistent(proc, rows, "shellcheck")
    def parse(row):
        if not isinstance(row["code"], int) or isinstance(row["code"], bool):
            raise CouldNotCheck(f"shellcheck reported a code that is not a number: {row['code']!r}")
        code = f"SC{row['code']}"
        # SC1072: parsing stopped; SC1071: a shell ShellCheck does not check.
        return _split(tmp, os.path.join(tmp, row["file"])) + (
            code, _message(row, "shellcheck"), code in ("SC1072", "SC1071"))
    yield from _each(rows, "shellcheck", tmp, lambda row: os.path.join(tmp, row["file"]),
                     parse)


def _run_actionlint(argv, spec, tmp, files, timeout):
    # actionlint 1.7.12 discovers only `.github/actionlint.yaml` by itself,
    # so the bundle's config is named explicitly, whichever spelling it uses.
    config = [os.path.join(tmp, "head", ".github", name)
              for name in ("actionlint.yaml", "actionlint.yml")]
    config = [c for c in config if os.path.isfile(c)][:1]
    # Its embedded shellcheck and pyflakes passes are switched off by name:
    # actionlint silently skips them when the binaries are not on PATH, so
    # leaving them on would make the same bundle's answer depend on the host.
    # `run:` scripts are therefore NOT checked here (documented, not hidden).
    proc = _spawn(argv + ["-format", "{{json .}}", "-no-color", "-shellcheck=", "-pyflakes="]
                  + (["-config-file", config[0]] if config else [])
                  + list(spec.get("args") or []) + files, tmp, timeout)
    def extract(text):
        rows = _loads(text, "actionlint")
        if not isinstance(rows, list):
            raise CouldNotCheck("actionlint output is not a list")
        return rows
    rows, odd = _rows(proc, (0, 1), "actionlint", extract)
    yield from odd or _consistent(proc, rows, "actionlint")
    def parse(row):
        kind = _text(row, "kind", "actionlint")
        return _split(tmp, os.path.join(tmp, row["filepath"])) + (
            kind, _message(row, "actionlint"), kind == "syntax-check")
    yield from _each(rows, "actionlint", tmp, lambda row: os.path.join(tmp, row["filepath"]),
                     parse)


def _run_pssa(argv, spec, tmp, files, timeout):
    script = os.path.join(tmp, "pssa.ps1")
    listing = os.path.join(tmp, "pssa-files.txt")
    rules = os.path.join(tmp, "pssa-rules.txt")
    for path, text in ((script, _PSSA_SCRIPT),
                       (listing, json.dumps([os.path.join(tmp, f) for f in files])),
                       (rules, json.dumps(list(spec.get("rules") or [])))):
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
    proc = _spawn(argv + ["-NoProfile", "-NonInteractive", "-File", script, listing, rules],
                  tmp, timeout)
    def extract(text):
        rows = _loads(text.strip(), "psscriptanalyzer")
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            raise CouldNotCheck("psscriptanalyzer output is not a list")
        return rows
    rows, odd = _rows(proc, (0,), "psscriptanalyzer", extract)
    yield from odd
    def parse(row):
        severity = row.get("severity") if isinstance(row, dict) else None
        if severity not in PSSA_SEVERITIES:
            raise CouldNotCheck(f"psscriptanalyzer reported a severity it does not have: "
                                f"{severity!r}")
        # A parse error may carry no rule name; any other row must.
        rule = (row.get("rule") or "ParseError") if severity == "ParseError" and isinstance(
            row.get("rule"), str) else _text(row, "rule", "psscriptanalyzer")
        return _split(tmp, row["file"]) + (rule, _message(row, "psscriptanalyzer"),
                                           severity == "ParseError")
    yield from _each(rows, "psscriptanalyzer", tmp, lambda row: row["file"], parse)


# DiagnosticSeverity, the values `[string]$r.Severity` can take.
PSSA_SEVERITIES = ("Information", "Warning", "Error", "ParseError")

RUNNERS = {"ruff": _run_ruff, "shellcheck": _run_shellcheck,
           "psscriptanalyzer": _run_pssa, "actionlint": _run_actionlint}


def check_one(root, spec, entries, manifest):
    """One linter over the bundle: a result dict, never an exception."""
    name = _name(spec)
    selected = _selected(spec, entries)
    result = {"name": name, "status": NA, "files": len(selected), "new": [], "detail": ""}
    if not selected:
        result["detail"] = "no changed file matches this linter"
        return result
    try:
        argv = _command(spec)
        with tempfile.TemporaryDirectory(prefix="crew-prereview-") as tmp:
            with_base = _materialise(root, selected, _config_blobs(root, manifest), tmp)
            files = [f"head/{e['path']}" for e in selected]
            files += [f"base/{rel}" for rel in sorted(with_base)]
            counts = {"base": collections.Counter(), "head": collections.Counter()}
            aborted, aborted_files, unparsed, bad, exits = [], set(), set(), [], []
            rows = RUNNERS[spec["tool"]](argv, spec, tmp, files,
                                         spec.get("timeout") or DEFAULT_TIMEOUT)
            for row in rows:
                if isinstance(row, _BadRow) and row.kind == "exit":
                    exits.append(row.reason)
                    continue
                if isinstance(row, _BadRow):
                    # A bad BASE row leaves that file's base count short, so
                    # its head findings may not be new: unchecked, like a base
                    # parse abort. A bad head row, or one naming no file,
                    # leaves the rows read so far standing as they are.
                    bad.append(row.reason)
                    if row.where is not None and row.where[0] == "base":
                        unparsed.add(row.where[1])
                    continue
                side, rel, rule, message, abort = row
                if abort:
                    unparsed.add(rel)
                    aborted_files.add(rel)
                    aborted.append(f"{rel} ({'bundle' if side == 'head' else 'base'}: "
                                   f"{rule} {message})")
                counts[side][(rel, rule, _normalise(message))] += 1
    except (CouldNotCheck, KeyError, TypeError, AttributeError, ValueError, OSError) as exc:
        result.update(status=COULD_NOT, detail=_detail(exc))
        return result
    # A file the tool could not parse is unchecked, but only that file: a
    # NEW finding in any other file still refuses (FAIL), which
    # --allow-unverified never overrides (review round 2).
    new = []
    for key, n in sorted(counts["head"].items()):
        added = n - counts["base"][key]
        if added > 0 and key[0] not in unparsed:
            new.append({"path": key[0], "rule": key[1], "message": key[2], "count": added})
    parts = list(exits)
    if aborted:
        parts.append(f"{name} could not parse {len(aborted_files)} "
                     "file(s), so they were not checked: " + "; ".join(sorted(set(aborted))))
    if bad:
        parts.append(f"{len(bad)} output row(s) could not be read: " + "; ".join(bad[:3])
                     + (f"; and {len(bad) - 3} more" if len(bad) > 3 else ""))
    unchecked = "; ".join(parts)
    if new:
        detail = f"{sum(r['count'] for r in new)} new finding(s)"
        result.update(status=FAIL, new=new,
                      detail=detail + (f"; also {unchecked}" if unchecked else ""))
    elif unchecked:
        result.update(status=COULD_NOT, detail=unchecked)
    else:
        result.update(status=PASS, detail=f"no new findings in {len(selected)} file(s)")
    return result


def _normalise(message):
    """Whitespace collapsed and line/column positions read as N: messages
    that quote one ("from line 3", "SC2086:info:2:28") would otherwise make a
    moved finding look new. Every other digit is kept, so a changed value
    ("requires 2" -> "requires 3") is a different finding."""
    text = " ".join(str(message).split())
    for pattern, replacement in _POSITIONS:
        text = pattern.sub(replacement, text)
    return text


def _detail(exc):
    if isinstance(exc, KeyError):
        return f"tool output is missing the field {exc}"
    return str(exc) or type(exc).__name__


def run_checks(root, manifest_path):
    """(results, configured). results is a list of check_one dicts; a config
    or manifest problem is one could-not-check row named `config`/`manifest`."""
    results, configured, _ = run_checks_bound(root, manifest_path)
    return results, configured


def run_checks_bound(root, manifest_path, scratch=None):
    """(results, configured, bundle_sha256): the hash comes from the same read
    of the manifest as the entries the linters checked, so a manifest replaced
    mid-run cannot have these results recorded against it (review round 4).
    bundle_sha256 is None when the manifest could not be read. The manifest
    is read inside `scratch` (review_run passes its scratch directory); with
    none, inside the manifest's own directory."""
    manifest, manifest_problem = None, None
    base = scratch or os.path.dirname(os.path.abspath(manifest_path))
    try:
        manifest = strict_json(read_regular(manifest_path, base).decode("utf-8"))
    except (OSError, ValueError) as exc:
        manifest_problem = exc
    bundle = _bundle_hash(manifest)
    results, configured = _run_checks(root, manifest, manifest_problem)
    return results, configured, bundle


def _run_checks(root, manifest, manifest_problem):
    # The manifest first: the config is read from the bundle it describes,
    # so without it not even "nothing configured" can be said (round 5).
    try:
        if manifest_problem is not None:
            raise manifest_problem
        entries = changed_files(manifest)
        if not isinstance(manifest.get("base"), str) or not manifest["base"]:
            raise ValueError("it names no base commit")
        if not _bundle_hash(manifest):
            raise ValueError("it has no bundle_sha256 to bind a record to")
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        return [{"name": "manifest", "status": COULD_NOT, "files": 0, "new": [],
                 "detail": f"the bundle manifest could not be read: {exc}"}], True
    linters, problem = load_config(root, manifest)
    if problem:
        return [{"name": "config", "status": COULD_NOT, "files": 0, "new": [],
                 "detail": problem}], True
    if linters is None:
        return [], False
    return [_isolated(root, spec, entries, manifest) for spec in linters], True


def _isolated(root, spec, entries, manifest):
    """check_one, with anything it raises kept in this linter's own row
    (review round 9 BLOCK :948): a glob that makes matching raise
    RecursionError, or a runner bug, never discards another linter's NEW
    result, and overall() puts any FAIL ahead of COULD NOT CHECK."""
    try:
        return check_one(root, spec, entries, manifest)
    except Exception as exc:  # noqa: BLE001 - a boundary per linter  pylint: disable=broad-exception-caught
        return {"name": _name(spec), "status": COULD_NOT, "files": 0, "new": [],
                "detail": f"the check itself failed: {type(exc).__name__}: {exc}"}


def _bundle_hash(manifest):
    value = manifest.get("bundle_sha256") if isinstance(manifest, dict) else None
    return value if isinstance(value, str) and value else None


def overall(results, configured=True):
    if not configured:
        return NOT_CONFIGURED
    statuses = {r["status"] for r in results}
    if FAIL in statuses:
        return FAIL
    if COULD_NOT in statuses:
        return COULD_NOT
    return PASS


def lines(results):
    """Human-readable lines, one per check plus one per NEW finding (bounded)."""
    out = []
    for r in results:
        label = {PASS: "pass", FAIL: "FAIL", COULD_NOT: "COULD NOT CHECK", NA: "n/a"}[r["status"]]
        out.append(f"pre-review checks: {one_line(r['name'])} {label} - {one_line(r['detail'])}")
        for row in r["new"][:SHOWN]:
            out.append(f"  NEW x{row['count']} {one_line(row['path'])}: {one_line(row['rule'])} "
                       f"{one_line(row['message'])}")
        if len(r["new"]) > SHOWN:
            out.append(f"  ... and {len(r['new']) - SHOWN} more")
    return out


def _write_json(scratch, path, payload):
    """Atomically, through a temp name of this writer's own in `scratch`."""
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    handle, tmp = tempfile.mkstemp(prefix=".prereview.", suffix=".tmp", dir=scratch)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


_TICKET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def round_record_path(scratch, ticket, number):
    """`prereview-<ticket>-r<N>.json` (review round 7 FIX :870: two tickets
    sharing a scratch directory each keep round 1). ValueError for a ticket
    that is not a plain file-name part, so it can never name another path."""
    if not isinstance(ticket, str) or not _TICKET_NAME.match(ticket):
        raise ValueError(f"ticket {ticket!r} is not a plain name")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise ValueError(f"round {number!r} is not a positive integer")
    return os.path.join(scratch, f"prereview-{ticket}-r{number}.json")


def record(scratch, bundle_sha256, results, overridden, stood_down, configured=True):
    """Stage this run's record, bound to the bundle it judged, under a name no
    other run uses. Returns its path, for bind_record once a round is held."""
    payload = {"bundle_sha256": bundle_sha256, "result": overall(results, configured),
               "overridden": overridden, "stood_down": stood_down, "checks": results}
    path = os.path.join(scratch, f"prereview.run-{secrets.token_hex(8)}.json")
    _write_json(scratch, path, payload)
    return path


def bind_record(staged, scratch, ticket, number):
    """The staged record becomes round `number`'s, ticket and round written
    inside so a file moved or copied between rounds does not match."""
    target = round_record_path(scratch, ticket, number)
    payload = strict_json(read_regular(staged, scratch).decode("utf-8"))
    payload.update(ticket=ticket, round=number)
    _write_json(scratch, target, payload)
    os.remove(staged)


def recorded(scratch, bundle_sha256, ticket, number):
    """Round `number`'s record for exactly this bundle and ticket. Otherwise a
    `not-recorded` dict saying why, never None: an absent record must not read
    as a clean one."""
    if not isinstance(bundle_sha256, str) or not bundle_sha256:
        return {"result": NOT_RECORDED, "reason": "the bundle has no bundle_sha256 to match"}
    try:
        path = round_record_path(scratch, ticket, number)
    except ValueError as exc:
        return {"result": NOT_RECORDED, "reason": str(exc)}
    name = os.path.basename(path)
    try:
        payload = strict_json(read_regular(path, scratch).decode("utf-8"))
    except FileNotFoundError:
        return {"result": NOT_RECORDED, "reason": f"no {name} in the scratch directory"}
    except (OSError, ValueError) as exc:
        return {"result": NOT_RECORDED, "reason": f"{name} could not be read: {exc}"}
    if not isinstance(payload, dict) or payload.get("bundle_sha256") != bundle_sha256:
        return {"result": NOT_RECORDED,
                "reason": f"{name} was written for another bundle"}
    if payload.get("ticket") != ticket or payload.get("round") != number \
            or isinstance(payload.get("round"), bool):
        return {"result": NOT_RECORDED,
                "reason": f"{name} was bound to another ticket or round"}
    if not (payload.get("result") in (PASS, FAIL, COULD_NOT, NOT_CONFIGURED)
            and isinstance(payload.get("checks"), list)
            and all(_is_check_row(c) for c in payload["checks"])
            and isinstance(payload.get("overridden"), bool)
            and isinstance(payload.get("stood_down"), bool)):
        return {"result": NOT_RECORDED,
                "reason": f"{name} is not the shape record() writes"}
    configured = payload["result"] != NOT_CONFIGURED
    if (not configured and payload["checks"]) or \
            payload["result"] != overall(payload["checks"], configured) or \
            not _flags_fit(payload):
        return {"result": NOT_RECORDED,
                "reason": f"{name} states a result its checks do not add up to"}
    return payload


def _flags_fit(payload):
    """An override exists only for COULD NOT CHECK, a stand-down only for a
    result that would otherwise refuse, and never both (prereview_gate)."""
    overridden, stood_down, result = payload["overridden"], payload["stood_down"], payload["result"]
    if overridden and (stood_down or result != COULD_NOT):
        return False
    return not stood_down or result in (FAIL, COULD_NOT)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_check_row(row):
    """A check row exactly as check_one / run_checks build it: findings only
    on a FAIL row and a FAIL row only with findings, and an n/a row checked
    no file (review round 4)."""
    if not (isinstance(row, dict) and isinstance(row.get("new"), list)):
        return False
    if (row.get("status") == FAIL) != bool(row["new"]) or (
            row.get("status") == NA and row.get("files") != 0):
        return False
    return (isinstance(row, dict)
            and isinstance(row.get("name"), str)
            and row.get("status") in (PASS, FAIL, COULD_NOT, NA)
            and _is_int(row.get("files"))
            and isinstance(row.get("detail"), str)
            and isinstance(row.get("new"), list)
            and all(isinstance(n, dict) and _is_int(n.get("count")) and n["count"] > 0
                    and all(isinstance(n.get(k), str) for k in ("path", "rule", "message"))
                    for n in row["new"]))


def main(argv):
    """Exit 1 only for a real new finding: any crash, the printing included,
    is EXIT_COULD_NOT (review round 9 FIX :165)."""
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):
        pass  # a replaced stdout (tests): one_line already escapes what matters
    try:
        return _main(argv)
    except Exception as exc:  # noqa: BLE001 - the CLI's boundary  pylint: disable=broad-exception-caught
        sys.stderr.write(f"pre-review checks: COULD NOT CHECK - {type(exc).__name__}: "
                         f"{one_line(exc)}\n")
        return EXIT_COULD_NOT


def _main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        results, configured = run_checks(os.path.abspath(args.root), args.manifest)
    except Exception as exc:  # noqa: BLE001 - boundary, see below  pylint: disable=broad-exception-caught
        # The CLI's boundary: exit 1 means "new findings", so a crash must not
        # leave through the default traceback status.
        print(f"pre-review checks: COULD NOT CHECK - {type(exc).__name__}: {one_line(exc)}")
        return EXIT_COULD_NOT
    if not configured:
        print(f"pre-review checks: none configured ({VERIFY_MAP} has no {CONFIG_KEY})")
        return EXIT_PASS
    for line in lines(results):
        print(line)
    return {PASS: EXIT_PASS, FAIL: EXIT_NEW, COULD_NOT: EXIT_COULD_NOT}[overall(results)]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
