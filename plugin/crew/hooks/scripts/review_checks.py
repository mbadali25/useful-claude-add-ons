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
`review_run.py` refuses a round on `fail` and on `could-not-check` (exit 5,
nothing reserved). `--allow-unverified` overrides only `could-not-check`, and
review.json records the override.

Exit codes of the CLI: 0 pass (or nothing configured or applicable), 1 new
findings, 3 could not check, 2 usage.
"""
import argparse
import collections
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile

import crew_ticket

PASS, FAIL, COULD_NOT, NA = "pass", "fail", "could-not-check", "n/a"
NOT_CONFIGURED, NOT_RECORDED = "not-configured", "not-recorded"
CONFIG_KEY = "preReview"
VERIFY_MAP = os.path.join(".crew", "verify.json")
RESULT_FILE = "prereview.json"
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
    (re.compile(r"(?<![\w.])\d+:\d+(?=:)"), "N:N"),
)

TOOLS = {
    "ruff": {"globs": ("**/*.py",)},
    "shellcheck": {"globs": ("**/*.sh", "**/*.bash")},
    "psscriptanalyzer": {"globs": ("**/*.ps1", "**/*.psm1", "**/*.psd1")},
    "actionlint": {"globs": (".github/workflows/*.yml", ".github/workflows/*.yaml")},
}
LINTER_KEYS = {"tool", "command", "args", "paths", "timeout", "rules"}
BLOCK_KEYS = {"linters"}  # nothing else, not even a `_note`: an unknown key fails closed

# Read by pwsh with -File: the list of files and the rule allowlist arrive as
# files, so no path or rule name is ever quoted into a command line.
_PSSA_SCRIPT = r"""param([string]$ListFile, [string]$RulesFile)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    Import-Module PSScriptAnalyzer -ErrorAction Stop
    $rules = @(Get-Content -LiteralPath $RulesFile | Where-Object { $_ })
    $known = @(Get-ScriptAnalyzerRule | ForEach-Object { $_.RuleName })
    $unknown = @($rules | Where-Object { $known -notcontains $_ })
    if ($unknown.Count -gt 0) {
        # -IncludeRule ignores a name it does not know: a rule that silently never runs.
        [Console]::Error.WriteLine("psscriptanalyzer: unknown rule(s): " + ($unknown -join ', '))
        exit 3
    }
    $rows = foreach ($path in @(Get-Content -LiteralPath $ListFile | Where-Object { $_ })) {
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


class CouldNotCheck(Exception):
    """The check did not run to a result. Never read as a pass."""


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
    path = os.path.join(root, VERIFY_MAP)
    if not os.path.lexists(path):
        return None
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError as exc:
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
        data = json.loads(raw.decode("utf-8"))
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
        for key in ("command", "args", "paths", "rules"):
            value = spec.get(key)
            if value is not None and not (isinstance(value, list) and value
                                          and all(isinstance(v, str) and v for v in value)):
                problems.append(f"{where}: {key} must be a non-empty list of strings")
        if spec.get("rules") is not None and spec["tool"] != "psscriptanalyzer":
            problems.append(f"{where}: rules is for psscriptanalyzer only")
        timeout = spec.get("timeout")
        if timeout is not None and (not isinstance(timeout, int) or isinstance(timeout, bool)
                                    or timeout <= 0):
            problems.append(f"{where}: timeout must be a positive integer")
    if problems:
        return None, "; ".join(problems)
    return linters, None


def _name(spec):
    return spec["tool"]


def _git(root, *args):
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True,
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


def _which(name):
    """`name` from the ABSOLUTE PATH entries only. shutil.which on Windows
    searches the current directory first, so a repository could plant the
    linter it is judged by (review round 5); it is not used there."""
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


def _command(spec):
    argv = list(spec.get("command") or [])
    if not argv:
        argv = {"ruff": [sys.executable, "-m", "ruff"],
                "psscriptanalyzer": ["pwsh"]}.get(spec["tool"], [spec["tool"]])
    exe = argv[0] if os.path.isabs(argv[0]) else _which(argv[0])
    if not exe:
        raise CouldNotCheck(f"{argv[0]} is not on PATH (command: {' '.join(argv)})")
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


def _kill_tree(proc):
    """Kill the linter and everything it started. subprocess.run kills only
    the direct child, and on Windows then waits for EOF on pipes a
    grandchild may hold open forever (review round 4)."""
    try:
        if os.name == "nt":
            # By absolute path: a bare name would let a taskkill.exe in the
            # current directory run (review round 5). No SystemRoot, no taskkill.
            system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
            if system_root and os.path.isabs(system_root):
                subprocess.run([os.path.join(system_root, "System32", "taskkill.exe"),
                                "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True, stdin=subprocess.DEVNULL, check=False,
                               timeout=_REAP_SECONDS)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass  # already gone, or taskkill missing: proc.kill() below still runs
    try:
        proc.kill()
    except OSError:
        pass  # already exited


def _spawn(argv, cwd, timeout):
    env = _child_env(cwd)
    group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
             else {"start_new_session": True})
    try:
        # surrogateescape: tool output carries paths, which must round-trip.
        # Not a `with` block: on a timeout the group is killed before any wait.
        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="surrogateescape",
            stdin=subprocess.DEVNULL, env=env, **group)
    except OSError as exc:
        raise CouldNotCheck(f"could not start {argv[0]}: {exc}") from exc
    try:
        # The timeout covers EOF too: a child left holding stdout after the
        # linter exits is a timeout, never a wait without end.
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=_REAP_SECONDS)
        except subprocess.TimeoutExpired:
            for pipe in (proc.stdout, proc.stderr):
                pipe.close()
        raise CouldNotCheck(f"timed out after {timeout}s") from exc
    # A linter that exited cleanly may still have left children behind.
    if os.name != "nt":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass  # the group is empty: nothing was left behind
    return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)


def _expect(proc, ok_codes, tool):
    if proc.returncode not in ok_codes:
        tail = " ".join((proc.stderr or proc.stdout or "").strip().splitlines()[-3:])
        raise CouldNotCheck(f"{tool} exited {proc.returncode}: {tail[:400] or 'no output'}")


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
    __slots__ = ("where", "reason")

    def __init__(self, where, reason):
        self.where, self.reason = where, reason


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


def _loads(text, tool):
    try:
        return json.loads(text)
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
    _expect(proc, (0,), "ruff")
    rows = _loads(proc.stdout, "ruff")
    if not isinstance(rows, list):
        raise CouldNotCheck("ruff output is not a list")
    def parse(row):
        code = row.get("code") or "invalid-syntax"
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
    _expect(proc, (0, 1), "shellcheck")
    data = _loads(proc.stdout, "shellcheck")
    rows = data.get("comments") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise CouldNotCheck("shellcheck json1 output has no comments list")
    yield from _consistent(proc, rows, "shellcheck")
    def parse(row):
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
    _expect(proc, (0, 1), "actionlint")
    rows = _loads(proc.stdout, "actionlint")
    if not isinstance(rows, list):
        raise CouldNotCheck("actionlint output is not a list")
    yield from _consistent(proc, rows, "actionlint")
    def parse(row):
        kind = row.get("kind") or "?"
        return _split(tmp, os.path.join(tmp, row["filepath"])) + (
            kind, _message(row, "actionlint"), kind == "syntax-check")
    yield from _each(rows, "actionlint", tmp, lambda row: os.path.join(tmp, row["filepath"]),
                     parse)


def _run_pssa(argv, spec, tmp, files, timeout):
    script = os.path.join(tmp, "pssa.ps1")
    listing = os.path.join(tmp, "pssa-files.txt")
    rules = os.path.join(tmp, "pssa-rules.txt")
    for path, lines in ((script, [_PSSA_SCRIPT]),
                        (listing, [os.path.join(tmp, f) for f in files]),
                        (rules, list(spec.get("rules") or []))):
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
    proc = _spawn(argv + ["-NoProfile", "-NonInteractive", "-File", script, listing, rules],
                  tmp, timeout)
    _expect(proc, (0,), "psscriptanalyzer")
    rows = _loads((proc.stdout or "").strip(), "psscriptanalyzer")
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        raise CouldNotCheck("psscriptanalyzer output is not a list")
    def parse(row):
        return _split(tmp, row["file"]) + (row.get("rule") or "?",
                                           _message(row, "psscriptanalyzer"),
                                           row.get("severity") == "ParseError")
    yield from _each(rows, "psscriptanalyzer", tmp, lambda row: row["file"], parse)


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
            aborted, aborted_files, unparsed, bad = [], set(), set(), []
            rows = RUNNERS[spec["tool"]](argv, spec, tmp, files,
                                         spec.get("timeout") or DEFAULT_TIMEOUT)
            for row in rows:
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
    parts = []
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


def run_checks_bound(root, manifest_path):
    """(results, configured, bundle_sha256): the hash comes from the same read
    of the manifest as the entries the linters checked, so a manifest replaced
    mid-run cannot have these results recorded against it (review round 4).
    bundle_sha256 is None when the manifest could not be read."""
    manifest, manifest_problem = None, None
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
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
    return [check_one(root, spec, entries, manifest) for spec in linters], True


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
        out.append(f"pre-review checks: {r['name']} {label} - {r['detail']}")
        for row in r["new"][:SHOWN]:
            out.append(f"  NEW x{row['count']} {row['path']}: {row['rule']} {row['message']}")
        if len(r["new"]) > SHOWN:
            out.append(f"  ... and {len(r['new']) - SHOWN} more")
    return out


def record(scratch, bundle_sha256, results, overridden, stood_down, configured=True):
    """Write <scratch>/prereview.json, bound to the bundle it judged."""
    payload = {"bundle_sha256": bundle_sha256, "result": overall(results, configured),
               "overridden": overridden, "stood_down": stood_down, "checks": results}
    path = os.path.join(scratch, RESULT_FILE)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    # A temp name of its own per writer, so two runs sharing a scratch
    # directory never write or replace each other's staging file.
    handle, tmp = tempfile.mkstemp(prefix=RESULT_FILE + ".", suffix=".tmp", dir=scratch)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def recorded(scratch, bundle_sha256):
    """The record for exactly this bundle. Otherwise a `not-recorded` dict
    saying why, never None: an absent record must not read as a clean one."""
    if not isinstance(bundle_sha256, str) or not bundle_sha256:
        return {"result": NOT_RECORDED, "reason": "the bundle has no bundle_sha256 to match"}
    path = os.path.join(scratch, RESULT_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        return {"result": NOT_RECORDED, "reason": f"no {RESULT_FILE} in the scratch directory"}
    except (OSError, ValueError) as exc:
        return {"result": NOT_RECORDED, "reason": f"{RESULT_FILE} could not be read: {exc}"}
    if not isinstance(payload, dict) or payload.get("bundle_sha256") != bundle_sha256:
        return {"result": NOT_RECORDED,
                "reason": f"{RESULT_FILE} was written for another bundle"}
    if not (payload.get("result") in (PASS, FAIL, COULD_NOT, NOT_CONFIGURED)
            and isinstance(payload.get("checks"), list)
            and all(_is_check_row(c) for c in payload["checks"])
            and isinstance(payload.get("overridden"), bool)
            and isinstance(payload.get("stood_down"), bool)):
        return {"result": NOT_RECORDED,
                "reason": f"{RESULT_FILE} is not the shape record() writes"}
    configured = payload["result"] != NOT_CONFIGURED
    if (not configured and payload["checks"]) or \
            payload["result"] != overall(payload["checks"], configured) or \
            not _flags_fit(payload):
        return {"result": NOT_RECORDED,
                "reason": f"{RESULT_FILE} states a result its checks do not add up to"}
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
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        results, configured = run_checks(os.path.abspath(args.root), args.manifest)
    except Exception as exc:  # noqa: BLE001 - boundary, see below  pylint: disable=broad-exception-caught
        # The CLI's boundary: exit 1 means "new findings", so a crash must not
        # leave through the default traceback status.
        print(f"pre-review checks: COULD NOT CHECK - {type(exc).__name__}: {exc}")
        return EXIT_COULD_NOT
    if not configured:
        print(f"pre-review checks: none configured ({VERIFY_MAP} has no {CONFIG_KEY})")
        return EXIT_PASS
    for line in lines(results):
        print(line)
    return {PASS: EXIT_PASS, FAIL: EXIT_NEW, COULD_NOT: EXIT_COULD_NOT}[overall(results)]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
