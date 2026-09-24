"""Web-testing checks crew enforces in code, not in prose.

    python3 webtest_guard.py skips     --root . [--ticket ID] [--base SHA]
    python3 webtest_guard.py auth-leak --root .
    python3 webtest_guard.py visual    --root . [-- <extra playwright args>]
    python3 webtest_guard.py artifacts --root .

Each is a check a `verify.json` rule calls (`webtest_rules.py` emits those
rules); none is a hook of its own. The verify gate runs every rule command
through `bash -c` from both of its flavours, so one script serves both.

## skips -- a healer "skip" is a finding, never accepted

`playwright-test-healer` re-runs a failing test until it passes or its
guardrails intervene, and may mark the test skipped when it decides the
feature is broken (https://playwright.dev/docs/test-agents). A test that was
catching a real bug and is now skipped reads as green. So every skip ADDED
since the ticket's base -- `.skip(`, `.fixme(`, `test.fail(` /
`test.describe.fail(`, or an annotation of type `skip`/`fixme`/`fail` -- in a
changed `*.spec.*` / `*.test.*` file is a FINDING. The base is the commit the
ticket started from (`scope_base.resolve`), and its fallback shows MORE, never
less. A skip is accepted only when the ticket's `spec.md` names it under
`## Exclusions` as a bullet `skip: <path>` (every new skip in that file) or
`skip: <path> "<text>"` (only added lines containing that text). Findings are
written to `.work/tickets/<id>/webtest/findings.json`, which `/crew:review`'s
prompt and `review.json` both carry.

A skip inside a comment is flagged too. That false positive is the safe
direction; a reviewer can dismiss it, but nobody can review a skip that was
never reported.

## auth-leak

`playwright/.auth/` holds live session cookies. Any tracked file with a
`.auth` path segment, or at a `storageState` path named in
`playwright.config.*`, fails the check.

## visual -- inside the pinned image, or UNVERIFIED

Screenshots rendered on Windows and on Linux CI differ, so baselines are only
compared inside `PINNED_IMAGE`. Outside it this exits 77 -- the verify gate's
SKIP, which is never recorded as verified -- and says UNVERIFIED. "Inside" is
`CREW_PLAYWRIGHT_IMAGE` naming exactly the pinned image on Linux, plus an
installed `@playwright/test` at `PINNED_PLAYWRIGHT`; a version mismatch fails
rather than skips, since that is a real misconfiguration, not an absent one.

## artifacts

A bounded listing of trace zips and axe results under `test-results/` for the
review bundle's manifest: at most `MAX_ARTIFACTS` of each, newest first, with
size and sha256; what was left out is counted, never silently dropped.

Exit codes: 0 pass; 1 a finding or a failure; 2 could not tell (not a git
repository, git failed, usage) -- never a pass; 77 visual skipped (UNVERIFIED).
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

import crew_common
import crew_ticket
import scope_base

EXIT_OK, EXIT_FINDING, EXIT_UNKNOWN, EXIT_SKIP = 0, 1, 2, 77

PINNED_PLAYWRIGHT = "1.63.0"
PINNED_IMAGE = f"mcr.microsoft.com/playwright:v{PINNED_PLAYWRIGHT}-noble"
IMAGE_ENV = "CREW_PLAYWRIGHT_IMAGE"
MAX_ARTIFACTS = 20

SPEC_FILE_RE = re.compile(r"(?:^|/)[^/]+\.(?:spec|test)\.[cm]?[jt]sx?$")
SKIP_RES = (
    re.compile(r"\.(?:skip|fixme)\s*\("),
    re.compile(r"\b(?:test|it)(?:\.describe)?\.fail\s*\("),
    re.compile(r"""\btype\s*:\s*['"`](?:skip|fixme|fail)['"`]"""),
)
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_EXCLUSION_RE = re.compile(r"""\bskip:\s*`?([^\s`"]+)`?(?:\s+"([^"]+)")?""")
_STORAGE_RE = re.compile(r"""storageState\s*:\s*['"`]([^'"`]+)['"`]""")
_AUTH_LITERAL_RE = re.compile(r"""['"`]([^'"`]*(?:^|/)\.auth/[^'"`]*)['"`]""")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _norm(path):
    return path[2:] if path.startswith("./") else path


def is_skip_line(text):
    return any(rx.search(text) for rx in SKIP_RES)


# ---------------------------------------------------------------- skips

def added_lines(diff_text):
    """[(path, new_line_number, text)] for every `+` line of a -U0 diff."""
    out, path, line = [], None, 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:]
            path = target[2:] if target.startswith("b/") else None
            continue
        if raw.startswith("--- "):
            continue
        hunk = _HUNK_RE.match(raw)
        if hunk:
            line = int(hunk.group(1))
            continue
        if path and raw.startswith("+"):
            out.append((path, line, raw[1:]))
            line += 1
    return out


def _section(markdown, name):
    """Body of the first heading called `name` (any level), else ''."""
    lines = markdown.splitlines()
    for i, text in enumerate(lines):
        match = _HEADING_RE.match(text)
        if match and match.group(2).strip().lower() == name.lower():
            level = len(match.group(1))
            body = []
            for rest in lines[i + 1:]:
                nxt = _HEADING_RE.match(rest)
                if nxt and len(nxt.group(1)) <= level:
                    break
                body.append(rest)
            return "\n".join(body)
    return ""


def exclusions(root, ticket):
    """[(path, text_or_None)] from the ticket spec's `## Exclusions`."""
    if not ticket:
        return []
    text = crew_common.read_text(os.path.join(root, ".work", "tickets", ticket, "spec.md"))
    if not text:
        return []
    return [(_norm(m.group(1)), m.group(2))
            for m in _EXCLUSION_RE.finditer(_section(text, "Exclusions"))]


def _excluded(path, text, rules):
    return any(path == rpath and (want is None or want in text) for rpath, want in rules)


def find_skips(root, base):
    """[(path, line, text)] skips added since `base`, or None when git could
    not answer. Untracked spec files count as wholly added."""
    diff = crew_common.git_out(root, "-c", "core.quotePath=false", "diff", "-U0",
                               "--no-color", "--no-ext-diff", "-M", base, "--")
    untracked = crew_common.git_out(root, "-c", "core.quotePath=false", "ls-files",
                                    "--others", "--exclude-standard")
    if diff is None or untracked is None:
        return None
    found = [(p, n, t) for p, n, t in added_lines(diff)
             if SPEC_FILE_RE.search(p) and is_skip_line(t)]
    for rel in untracked.splitlines():
        rel = rel.strip()
        if not rel or not SPEC_FILE_RE.search(rel):
            continue
        body = crew_common.read_text(os.path.join(root, rel)) or ""
        found += [(rel, n, t) for n, t in enumerate(body.splitlines(), 1) if is_skip_line(t)]
    return sorted(found)


def _write_json(path, obj):
    text = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def check_skips(root, ticket=None, base=None):
    """(exit_code, lines). Writes the findings file when a ticket is known."""
    if ticket is None:
        ticket, _source = crew_ticket.active_ticket(root)
    else:
        try:
            crew_ticket.check_ticket(ticket)
        except crew_ticket.TicketError as exc:
            return EXIT_UNKNOWN, [f"webtest skips: UNKNOWN -- {exc}"]
    reason = f"--base {base}"
    if base is None:
        base, _src, reason = scope_base.resolve(root, ticket or "(no active ticket)")
    if base is None:
        return EXIT_UNKNOWN, [f"webtest skips: UNKNOWN -- no base to diff from ({reason})"]
    skips = find_skips(root, base)
    if skips is None:
        return EXIT_UNKNOWN, [f"webtest skips: UNKNOWN -- git could not diff against {base[:12]}"]
    rules = exclusions(root, ticket)
    rows = [{"kind": "healer-skip", "severity": "FIX", "path": p, "line": n,
             "text": t.strip(), "excluded": _excluded(p, t, rules)} for p, n, t in skips]
    if ticket:
        _write_json(os.path.join(root, ".work", "tickets", ticket, "webtest", "findings.json"),
                    {"ticket": ticket, "base": base, "baseReason": reason, "findings": rows})
    lines = [f"webtest skips: base {base[:12]} ({reason}); ticket {ticket or 'none'}"]
    open_rows = [r for r in rows if not r["excluded"]]
    for row in rows:
        tag = "EXCLUDED" if row["excluded"] else "FINDING"
        lines.append(f"{tag}|{row['severity']}|healer-skip|{row['path']}:{row['line']}|{row['text']}")
    if open_rows:
        lines.append(f"webtest skips: {len(open_rows)} new skip(s) not listed under the spec's "
                     "Exclusions -- a healer skip is a finding, never accepted")
        return EXIT_FINDING, lines
    lines.append(f"webtest skips: no unexcused skip ({len(rows)} excluded by the spec)")
    return EXIT_OK, lines


# ---------------------------------------------------------------- auth-leak

def _config_auth_paths(root):
    paths = set()
    for name in sorted(os.listdir(root)):
        if not name.startswith("playwright.config."):
            continue
        text = crew_common.read_text(os.path.join(root, name)) or ""
        paths.update(m.group(1) for m in _STORAGE_RE.finditer(text))
        paths.update(m.group(1) for m in _AUTH_LITERAL_RE.finditer(text))
    return sorted(_norm(p) for p in paths)


def check_auth_leak(root):
    tracked = crew_common.git_out(root, "-c", "core.quotePath=false", "ls-files")
    if tracked is None:
        return EXIT_UNKNOWN, ["webtest auth-leak: UNKNOWN -- git ls-files failed; not a pass"]
    named = set(_config_auth_paths(root))
    leaks = [p for p in tracked.splitlines()
             if p and (".auth" in p.split("/") or p in named)]
    if leaks:
        return EXIT_FINDING, (["webtest auth-leak: tracked session state -- untrack it "
                               "(git rm --cached) and gitignore playwright/.auth/:"]
                              + [f"  {p}" for p in leaks])
    return EXIT_OK, ["webtest auth-leak: no tracked .auth or storageState file"]


# ---------------------------------------------------------------- visual

def installed_playwright(root):
    text = crew_common.read_text(
        os.path.join(root, "node_modules", "@playwright", "test", "package.json"))
    try:
        return json.loads(text).get("version") if text else None
    except (ValueError, AttributeError):
        return None


def check_visual(root, extra=(), runner=subprocess.call):
    image = os.environ.get(IMAGE_ENV, "")
    if image != PINNED_IMAGE or not sys.platform.startswith("linux"):
        where = f"{IMAGE_ENV}={image!r}" if image else f"{IMAGE_ENV} unset"
        return EXIT_SKIP, [f"webtest visual: UNVERIFIED -- visual diffs run only inside "
                           f"{PINNED_IMAGE}; skipped here ({where}, {sys.platform})"]
    version = installed_playwright(root)
    if version != PINNED_PLAYWRIGHT:
        return EXIT_FINDING, [f"webtest visual: @playwright/test is {version or 'not installed'}, "
                              f"the image is {PINNED_PLAYWRIGHT}; baselines would not compare"]
    rc = runner(["npx", "playwright", "test", "--project=visual"] + list(extra), cwd=root)
    # A real run cannot SKIP: 77 from playwright is a failure, not an absent environment.
    code = EXIT_OK if rc == 0 else EXIT_FINDING
    return code, [f"webtest visual: npx playwright test --project=visual exited {rc}"]


# ---------------------------------------------------------------- artifacts

def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def artifacts(root, limit=MAX_ARTIFACTS):
    """{"traces": [...], "axe": [...], "omitted": {...}} or None when the
    repo has no Playwright config and no `test-results/` directory."""
    results = os.path.join(root, "test-results")
    has_config = any(n.startswith("playwright.config.") for n in os.listdir(root))
    if not has_config and not os.path.isdir(results):
        return None
    found = {"traces": [], "axe": []}
    for base, _dirs, files in os.walk(results):
        for name in files:
            kind = ("traces" if name == "trace.zip" else
                    "axe" if name.endswith(".json") and "axe" in name.lower() else None)
            if kind:
                path = os.path.join(base, name)
                found[kind].append((os.path.getmtime(path), path))
    out = {"root": "test-results", "limit": limit, "omitted": {}}
    for kind, rows in found.items():
        rows.sort(key=lambda r: (-r[0], r[1]))
        out[kind] = [{"path": os.path.relpath(p, root).replace(os.sep, "/"),
                      "bytes": os.path.getsize(p), "sha256": _sha256(p)} for _m, p in rows[:limit]]
        out["omitted"][kind] = max(0, len(rows) - limit)
    return out


# ---------------------------------------------------------------- CLI

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("check", choices=("skips", "auth-leak", "visual", "artifacts"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket")
    parser.add_argument("--base")
    argv = list(argv)
    extra = argv[argv.index("--") + 1:] if "--" in argv else []
    args = parser.parse_args(argv[:argv.index("--")] if "--" in argv else argv)
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"webtest {args.check}: UNKNOWN -- {root} is not a directory", file=sys.stderr)
        return EXIT_UNKNOWN
    if args.check == "artifacts":
        print(json.dumps(artifacts(root), indent=2, sort_keys=True))
        return EXIT_OK
    if args.check == "skips":
        code, lines = check_skips(root, args.ticket, args.base)
    elif args.check == "auth-leak":
        code, lines = check_auth_leak(root)
    else:
        code, lines = check_visual(root, extra)
    stream = sys.stdout if code == EXIT_OK else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
