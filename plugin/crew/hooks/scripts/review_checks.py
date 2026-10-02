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
import shutil
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

TOOLS = {
    "ruff": {"globs": ("**/*.py",)},
    "shellcheck": {"globs": ("**/*.sh", "**/*.bash")},
    "psscriptanalyzer": {"globs": ("**/*.ps1", "**/*.psm1", "**/*.psd1")},
    "actionlint": {"globs": (".github/workflows/*.yml", ".github/workflows/*.yaml")},
}
LINTER_KEYS = {"tool", "command", "args", "paths", "timeout", "rules"}

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
        $params = @{ Path = $path }
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


def load_config(root):
    """(linters, None), (None, None) when nothing is configured, or
    (None, problem) when the map or its `preReview` key cannot be read."""
    path = os.path.join(root, VERIFY_MAP)
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, f"{VERIFY_MAP} could not be read: {exc}"
    if not isinstance(data, dict) or CONFIG_KEY not in data:
        return None, None
    block = data[CONFIG_KEY]
    linters = block.get("linters") if isinstance(block, dict) else None
    if not isinstance(linters, list) or not linters:
        return None, f'{VERIFY_MAP} "{CONFIG_KEY}" needs a non-empty "linters" list'
    problems = []
    for index, spec in enumerate(linters):
        where = f'{CONFIG_KEY}.linters[{index}]'
        if not isinstance(spec, dict) or spec.get("tool") not in TOOLS:
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
    """The bundle's entries a linter could read: not deleted, not a symlink,
    submodule or binary."""
    rows = []
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("its entries are not a list")
    for entry in entries:
        if not (isinstance(entry, dict) and all(
                isinstance(entry.get(k), str) and entry.get(k)
                for k in ("status", "path", "new_id"))):
            raise ValueError(f"an entry is not the shape review_patch writes: {entry!r:.200}")
        if entry.get("status") == "D" or entry.get("binary") or entry.get("submodule"):
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
    changed = {e.get("path"): e for e in manifest.get("entries") or []}
    found = {}
    for name in CONFIG_FILES:
        rel = name.replace(os.sep, "/")
        entry = changed.get(rel)
        if entry is not None:
            if entry.get("status") != "D":
                found[rel] = _git_blob(root, entry["new_id"])
            continue
        if _git(root, "cat-file", "-e", f"{manifest['base']}:{rel}").returncode == 0:
            found[rel] = _git_blob(root, f"{manifest['base']}:{rel}")
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
        if entry.get("status") != "A" and old != _ZERO:
            _write(_inside(tmp, "base", rel), _git_blob(root, old))
            with_base.add(rel)
    return with_base


def _command(spec):
    argv = list(spec.get("command") or [])
    if not argv:
        argv = {"ruff": [sys.executable, "-m", "ruff"],
                "psscriptanalyzer": ["pwsh"]}.get(spec["tool"], [spec["tool"]])
    exe = argv[0] if os.path.isabs(argv[0]) else shutil.which(argv[0])
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


def _spawn(argv, cwd, timeout):
    env = _child_env(cwd)
    try:
        # surrogateescape: tool output carries paths, which must round-trip.
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                              errors="surrogateescape", stdin=subprocess.DEVNULL,
                              timeout=timeout, env=env, check=False)
    except subprocess.TimeoutExpired as exc:
        raise CouldNotCheck(f"timed out after {timeout}s") from exc
    except OSError as exc:
        raise CouldNotCheck(f"could not start {argv[0]}: {exc}") from exc
    return proc


def _expect(proc, ok_codes, tool):
    if proc.returncode not in ok_codes:
        tail = " ".join((proc.stderr or proc.stdout or "").strip().splitlines()[-3:])
        raise CouldNotCheck(f"{tool} exited {proc.returncode}: {tail[:400] or 'no output'}")


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
    proc = _spawn(argv + ["check", "--output-format", "json", "--exit-zero", "--no-cache"]
                  + list(spec.get("args") or []) + files, tmp, timeout)
    _expect(proc, (0,), "ruff")
    rows = _loads(proc.stdout, "ruff")
    if not isinstance(rows, list):
        raise CouldNotCheck("ruff output is not a list")
    for row in rows:
        code = row.get("code") or "invalid-syntax"
        yield _split(tmp, row["filename"]) + (code, row.get("message", ""),
                                               code == "invalid-syntax")


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
    for row in rows:
        code = f"SC{row['code']}"
        yield _split(tmp, os.path.join(tmp, row["file"])) + (code, row.get("message", ""),
                                                              code == "SC1072")


def _run_actionlint(argv, spec, tmp, files, timeout):
    proc = _spawn(argv + ["-format", "{{json .}}", "-no-color"] + list(spec.get("args") or [])
                  + files, tmp, timeout)
    _expect(proc, (0, 1), "actionlint")
    rows = _loads(proc.stdout or "[]", "actionlint")
    if not isinstance(rows, list):
        raise CouldNotCheck("actionlint output is not a list")
    for row in rows:
        kind = row.get("kind") or "?"
        yield _split(tmp, os.path.join(tmp, row["filepath"])) + (
            kind, row.get("message", ""), kind == "syntax-check")


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
    for row in rows:
        yield _split(tmp, row["file"]) + (row.get("rule") or "?", row.get("message", ""),
                                          row.get("severity") == "ParseError")


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
            aborted = []
            rows = RUNNERS[spec["tool"]](argv, spec, tmp, files,
                                         spec.get("timeout") or DEFAULT_TIMEOUT)
            for side, rel, rule, message, abort in rows:
                if abort:
                    aborted.append(f"{rel} ({'bundle' if side == 'head' else 'base'}: "
                                   f"{rule} {message})")
                counts[side][(rel, rule, " ".join(str(message).split()))] += 1
    except (CouldNotCheck, KeyError, TypeError, AttributeError, ValueError, OSError) as exc:
        result.update(status=COULD_NOT, detail=_detail(exc))
        return result
    if aborted:
        files = {line.split(" (", 1)[0] for line in aborted}
        result.update(status=COULD_NOT, detail=(
            f"{name} could not parse {len(files)} file(s), so they were not checked: "
            + "; ".join(sorted(set(aborted)))))
        return result
    new = []
    for key, n in sorted(counts["head"].items()):
        added = n - counts["base"][key]
        if added > 0:
            new.append({"path": key[0], "rule": key[1], "message": key[2], "count": added})
    result.update(status=FAIL if new else PASS, new=new,
                  detail=f"{sum(r['count'] for r in new)} new finding(s)" if new else
                  f"no new findings in {len(selected)} file(s)")
    return result


def _detail(exc):
    if isinstance(exc, KeyError):
        return f"tool output is missing the field {exc}"
    return str(exc) or type(exc).__name__


def run_checks(root, manifest_path):
    """(results, configured). results is a list of check_one dicts; a config
    or manifest problem is one could-not-check row named `config`/`manifest`."""
    linters, problem = load_config(root)
    if problem:
        return [{"name": "config", "status": COULD_NOT, "files": 0, "new": [],
                 "detail": problem}], True
    if linters is None:
        return [], False
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        entries = changed_files(manifest)
        if not isinstance(manifest.get("base"), str) or not manifest["base"]:
            raise ValueError("it names no base commit")
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        return [{"name": "manifest", "status": COULD_NOT, "files": 0, "new": [],
                 "detail": f"the bundle manifest could not be read: {exc}"}], True
    return [check_one(root, spec, entries, manifest) for spec in linters], True


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
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def recorded(scratch, bundle_sha256):
    """The record for exactly this bundle. Otherwise a `not-recorded` dict
    saying why, never None: an absent record must not read as a clean one."""
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
    return payload


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    results, configured = run_checks(os.path.abspath(args.root), args.manifest)
    if not configured:
        print(f"pre-review checks: none configured ({VERIFY_MAP} has no {CONFIG_KEY})")
        return EXIT_PASS
    for line in lines(results):
        print(line)
    return {PASS: EXIT_PASS, FAIL: EXIT_NEW, COULD_NOT: EXIT_COULD_NOT}[overall(results)]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
