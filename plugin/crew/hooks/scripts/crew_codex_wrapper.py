#!/usr/bin/env python3
"""Provision and check the Codex host wrapper, `hooks/codex-review.sh` (L-0813).

    python3 crew_codex_wrapper.py check   [--json]
    python3 crew_codex_wrapper.py install [--force]
    python3 crew_codex_wrapper.py summary

WHAT IT IS. Review harnesses outside crew (the SRL and TSS repos) call Codex
through `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/codex-review.sh
<prompt_file> <out_file> [repo_dir]`, a per-machine file that closes stdin,
caps each run at 20 minutes and restarts once. Crew's own review (`review_run.py`)
launches `codex` directly and never calls it. The file was hand-installed and
versioned nowhere, so a rebuilt machine silently lost it and the harness exited
77 "SKIP - NO REVIEW HAPPENED". Crew ships a reference copy at
`templates/codex-review.sh` and this script installs and checks it.

LOOKUP, the same order the consumer uses: `CODEX_WRAPPER` when set (`none`
means "direct codex, opted in"; any other value must be an executable file),
else `${CLAUDE_CONFIG_DIR:-~/.claude}/hooks/codex-review.sh`, then
`$CODEX_WRAPPER_FALLBACK` (default `/root/.claude/hooks/codex-review.sh`; set
but empty disables it).

STATES, each its own line and exit code, none collapsed into another:
    ok              0  found, executable, byte-identical to crew's shipped copy
    present         0  found, executable, NOT crew's copy; never touched
    direct          0  CODEX_WRAPPER=none: the caller opted into direct codex
    n/a             0  no wrapper found AND codex is not on PATH
    missing         2  no wrapper found while codex is on PATH; names every path tried
    not-executable  2  a candidate exists but cannot be run
    unknown         4  a path could not be examined; says nothing about presence

INSTALL writes the shipped copy to the config-dir path, mode 755, through a
temp file and `os.replace`. An identical file is "already installed"; a
different one is refused (exit 3) unless `--force`, which keeps it as
`codex-review.sh.bak-<UTC stamp>` first. The result is re-checked after the
write. Exit 0 installed or already installed, 3 refused, 4 could not write.
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
import time

import crew_common

SHIPPED = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir,
                       "templates", "codex-review.sh")
DEFAULT_FALLBACK = "/root/.claude/hooks/codex-review.sh"

EXIT = {"ok": 0, "present": 0, "direct": 0, "n/a": 0, "missing": 2, "not-executable": 2,
        "unknown": 4}


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def target_path():
    return os.path.join(config_dir(), "hooks", "codex-review.sh")


def candidates():
    """The paths looked in, in the consumer's order. CODEX_WRAPPER (a real
    path) is the only candidate when set."""
    explicit = os.environ.get("CODEX_WRAPPER", "")
    if explicit and explicit != "none":
        return [explicit]
    found = [target_path()]
    fallback = os.environ.get("CODEX_WRAPPER_FALLBACK", DEFAULT_FALLBACK)
    if fallback and fallback not in found:
        found.append(fallback)
    return found


def _digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _probe(path):
    """('file'|'absent'|'unknown', detail) for one path. Only a not-found is
    'absent'; a permission error or any other failure is 'unknown'."""
    try:
        if os.path.isfile(path):
            return "file", ""
        os.stat(path)
        return "unknown", "exists but is not a regular file"
    except FileNotFoundError:
        return "absent", ""
    except OSError as exc:
        return "unknown", f"{type(exc).__name__}: {exc}"[:120]


def measure():
    """{'state', 'path', 'looked', 'detail'} for this machine."""
    if os.environ.get("CODEX_WRAPPER") == "none":
        return {"state": "direct", "path": "", "looked": [],
                "detail": "CODEX_WRAPPER=none: callers run codex exec directly, by opt-in"}
    looked = candidates()
    shipped_digest = None
    try:
        shipped_digest = _digest(SHIPPED)
    except OSError:
        pass
    problems = []
    for path in looked:
        kind, detail = _probe(path)
        if kind == "unknown":
            problems.append(f"{path}: {detail}")
            continue
        if kind == "absent":
            continue
        if not os.access(path, os.X_OK):
            return {"state": "not-executable", "path": path, "looked": looked,
                    "detail": f"{path} exists but is not executable (chmod +x it, or "
                              "crew_codex_wrapper.py install --force)"}
        try:
            same = shipped_digest is not None and _digest(path) == shipped_digest
        except OSError as exc:
            problems.append(f"{path}: {type(exc).__name__}: {exc}"[:160])
            continue
        if same:
            return {"state": "ok", "path": path, "looked": looked, "detail": "matches crew's shipped copy"}
        why = "not crew's shipped copy" if shipped_digest is not None else \
            "crew's shipped copy could not be read to compare"
        return {"state": "present", "path": path, "looked": looked, "detail": why + "; left as is"}
    if problems:
        return {"state": "unknown", "path": "", "looked": looked,
                "detail": "could not examine: " + "; ".join(problems)}
    if crew_common.resolve_tool("codex") is None:
        return {"state": "n/a", "path": "", "looked": looked,
                "detail": "no wrapper found and codex is not on PATH, so nothing here can review"}
    return {"state": "missing", "path": "", "looked": looked,
            "detail": "no wrapper found (looked in: " + ", ".join(looked) + "); a harness that "
                      "needs it exits 77 'NO REVIEW HAPPENED'. Fix: python3 crew_codex_wrapper.py install"}


def summarize(info):
    state = info["state"]
    if state == "ok":
        return f"ok ({info['path']})"
    if state == "present":
        return f"present ({info['path']}): {info['detail']}"
    label = state.upper() if EXIT[state] else state
    return f"{label}: {info['detail']}"


def summary():
    return summarize(measure())


def install(force=False):
    """(exit_code, message). Never leaves a half-written wrapper."""
    try:
        with open(SHIPPED, "rb") as handle:
            payload = handle.read()
    except OSError as exc:
        return 4, f"cannot read crew's shipped wrapper {SHIPPED}: {exc}"
    target = target_path()
    kind, detail = _probe(target)
    if kind == "unknown":
        return 4, f"cannot examine {target}: {detail}"
    backup = None
    if kind == "file":
        try:
            with open(target, "rb") as handle:
                current = handle.read()
        except OSError as exc:
            return 4, f"cannot read {target}: {exc}"
        if current == payload:
            if not os.access(target, os.X_OK):
                os.chmod(target, 0o755)
                return 0, f"fixed the executable bit on {target}"
            return 0, f"already installed: {target}"
        if not force:
            return 3, (f"{target} exists and is not crew's copy; refusing to overwrite it. "
                       "Re-run with --force to keep it as a .bak and install crew's copy.")
        backup = f"{target}.bak-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if backup:
            with open(backup, "wb") as handle:
                handle.write(current)
        fd, tmp = tempfile.mkstemp(prefix=".codex-review-", dir=os.path.dirname(target))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            os.chmod(tmp, 0o755)
            os.replace(tmp, target)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    except OSError as exc:
        return 4, f"could not write {target}: {exc}"
    try:
        written = _digest(target) == hashlib.sha256(payload).hexdigest() and os.access(target, os.X_OK)
    except OSError:
        written = False
    if not written:
        return 4, f"wrote {target} but the re-check found it unreadable, changed or not executable"
    note = f" (previous file kept as {backup})" if backup else ""
    return 0, f"installed: {target}{note}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", maxsplit=1)[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check")
    check.add_argument("--json", action="store_true")
    inst = sub.add_parser("install")
    inst.add_argument("--force", action="store_true")
    sub.add_parser("summary")
    args = parser.parse_args(argv)
    if args.cmd == "install":
        code, message = install(args.force)
        print(f"codex-wrapper {message}", file=sys.stderr if code else sys.stdout)
        return code
    info = measure()
    if args.cmd == "summary":
        print(summarize(info))
        return 0
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print("codex-wrapper " + summarize(info))
    return EXIT[info["state"]]


if __name__ == "__main__":
    sys.exit(main())
