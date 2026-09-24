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
catching a real bug and is now skipped reads as green.

So every test-capable file the change touches is read IN FULL, at the ticket's
base and now, and its skip sites are counted in both. "Test-capable" is any
`*.{js,jsx,ts,tsx,mjs,cjs,mts,cts}` that is a `*.spec.*` / `*.test.*` /
`*.setup.*` file, sits under a test directory (`TEST_DIRS`), or is reachable
by relative import from a spec file -- a helper's `test.skip(true)` disables
every test that calls it. A skip site is `.skip` / `.fixme` (called or not,
`test.describe.skip`, conditional `test.skip(cond, ...)`), the computed forms
`test['skip']` / `test["fixme"]`, `test.fail(` / `test.describe.fail(`, and an
annotation `{ type: 'skip' | 'fixme' | 'fail' }`. Files go through a tolerant
tokenizer, not line regexes: comments are dropped, string bodies cannot fake a
call, and a call or annotation split across lines is still one site.

A site in the file now that the base copy does not account for -- matched on
(kind, test title) -- is a FINDING. A rename is compared against its OLD
content, and a file that becomes a spec file by the rename counts from zero:
the skip it carried was inert until the rename made it run. The base is the
commit the ticket started from (`scope_base.resolve`), and its fallback shows
MORE, never less.

A skip is accepted only when the ticket's `spec.md` names it in a list item
directly under `## Exclusions` (not a subsection) whose text BEGINS
`skip: <path>` -- every new skip in that file -- or `skip: <path> "<text>"`,
only skips whose line or test title contains that text. Prose that merely
mentions `skip: <path>` is not an exclusion. Findings are written to
`.work/tickets/<id>/webtest/findings.json` with the HEAD they were computed
at (and the review bundle's sha256 when `review_run.py` ran it), which
`/crew:review`'s prompt and `review.json` both carry.

## auth-leak

`playwright/.auth/` holds live session cookies. Any tracked file with a
`.auth` path segment, or at a `storageState` path, fails the check. The
storageState paths come from `playwright.config.*`: a string literal, or a
name bound by a plain `const`/`let`/`var` to one, with `\\` read as `/`. Any
other value (a call, a template, a ternary) cannot be resolved without running
the config, so the check FAILS CLOSED unless the repository's
`.crew/config.json` declares the paths as `webtest.storageState` (a string or
a list of them).

## visual -- inside the pinned image, or UNVERIFIED

Screenshots rendered on Windows and on Linux CI differ, so baselines are only
compared inside `PINNED_IMAGE`. Outside it this exits 77 -- the verify gate's
SKIP, which is never recorded as verified -- and says UNVERIFIED. The
environment variable is not evidence on its own, since any caller can set it.
"Inside" needs all of: Linux; `CREW_PLAYWRIGHT_IMAGE` naming the pinned image
(the scaffolded config gates the visual project on it); a container marker
(`/.dockerenv`, `/run/.containerenv`, or docker/containerd/kubepods/podman in
`/proc/1/cgroup`); the image's browser store `/ms-playwright`; and in it the
chromium revision the installed `playwright-core/browsers.json` asks for,
which only the matching image release ships. An installed `@playwright/test`
that is not `PINNED_PLAYWRIGHT` fails rather than skips, since that is a real
misconfiguration, not an absent one. What was verified is printed.

## artifacts

A bounded listing of trace zips and axe results under `test-results/` for the
review bundle's manifest: at most `MAX_ARTIFACTS` of each, newest first, with
size and sha256; what was left out is counted, never silently dropped.

Exit codes: 0 pass; 1 a finding or a failure; 2 could not tell (not a git
repository, git failed, usage) -- never a pass; 77 visual skipped (UNVERIFIED).
"""
import argparse
import collections
import hashlib
import json
import os
import posixpath
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

# Container evidence, module-level so the tests can point them at tmp_path.
CONTAINER_MARKERS = ("/.dockerenv", "/run/.containerenv")
CGROUP_FILE = "/proc/1/cgroup"
CGROUP_WORDS = ("docker", "containerd", "kubepods", "podman", "libpod")
BROWSERS_DIR = "/ms-playwright"

JS_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts")
TEST_DIRS = frozenset(("test", "tests", "e2e", "spec", "specs", "__tests__", "playwright",
                       "integration"))
SPEC_FILE_RE = re.compile(r"(?:^|/)[^/]+\.(?:spec|test|setup)\.[cm]?[jt]sx?$")
SKIP_NAMES = ("skip", "fixme")
ANNOTATION_TYPES = ("skip", "fixme", "fail")
_IMPORT_RE = re.compile(r"""(?:\bfrom|\bimport|\brequire)\s*\(?\s*['"](\.{1,2}/[^'"]+)['"]""")
_EXCLUSION_RE = re.compile(r"""^[-*+]\s+skip:\s*`?([^\s`"]+)`?(?:\s+"([^"]+)")?"""
                           r"""(?:\s+(?:-|--|–|—|#)(?:\s.*)?)?\s*$""")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_AUTH_LITERAL_RE = re.compile(r"""['"`]([^'"`]*(?:^|/)\.auth/[^'"`]*)['"`]""")
_REGEX_AFTER = frozenset(("return", "typeof", "case", "do", "else", "in", "of", "new", "delete",
                          "void", "throw", "yield", "await"))
_VALUE_END = frozenset((",", "}", ")", ";"))


def _norm(path):
    path = re.sub(r"/+", "/", path.replace("\\", "/"))
    while path.startswith("./"):
        path = path[2:]
    return path


# ---------------------------------------------------------------- tokenizer

def _unescape(body):
    return re.sub(r"\\(.)", r"\1", body, flags=re.S)


def _string(text, i, quote):
    """(end_index, value) for a '...' or "..." starting at text[i]. An
    unterminated string ends at the newline, so one stray quote (an apostrophe
    in JSX text) costs one line of tokens, never the rest of the file."""
    j = i + 1
    while j < len(text) and text[j] not in (quote, "\n"):
        j += 2 if text[j] == "\\" else 1
    return min(j + 1, len(text)) if j < len(text) and text[j] == quote else j, _unescape(
        text[i + 1:j])


def _regex_end(text, i):
    j, klass = i + 1, False
    while j < len(text) and text[j] != "\n":
        char = text[j]
        if char == "\\":
            j += 2
            continue
        if char == "[":
            klass = True
        elif char == "]":
            klass = False
        elif char == "/" and not klass:
            j += 1
            while j < len(text) and (text[j].isalnum() or text[j] == "_"):
                j += 1
            return j
        j += 1
    return j


def _regex_allowed(out):
    if not out:
        return True
    kind, value, _line = out[-1]
    if kind == "id":
        return value in _REGEX_AFTER
    return kind == "p" and value not in (")", "]", "}")


def _scan(text, i, line, out, in_template):
    """Tokenize code from text[i]; returns (index, line). With `in_template`
    it stops after the `}` closing a template literal's `${`."""
    depth = 0
    while i < len(text):
        char = text[i]
        if char == "\n":
            line += 1
            i += 1
        elif char.isspace():
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = len(text) if end < 0 else end + 2
            line += text.count("\n", i, end)
            i = end
        elif char in "'\"":
            end, value = _string(text, i, char)
            out.append(("str", value, line))
            i = end
        elif char == "`":
            i, line = _template(text, i, line, out)
        elif char == "/" and _regex_allowed(out):
            i = _regex_end(text, i)
        elif char.isalpha() or char in "_$":
            match = re.compile(r"[\w$]+").match(text, i)
            out.append(("id", match.group(0), line))
            i = match.end()
        elif char.isdigit():
            i = re.compile(r"[\w.]+").match(text, i).end()
        else:
            if in_template and char == "}" and depth == 0:
                return i + 1, line
            depth += {"{": 1, "}": -1}.get(char, 0)
            if text.startswith("?.", i) and not text[i + 2:i + 3].isdigit():
                out.append(("p", ".", line))
                i += 2
                continue
            out.append(("p", char, line))
            i += 1
    return i, line


def _template(text, i, line, out):
    """A template literal: one `str` token (its `${}` bodies blanked), with
    the code inside each `${...}` tokenized in place after it."""
    start_line, body, inner = line, [], []
    i += 1
    while i < len(text) and text[i] != "`":
        if text[i] == "\\":
            body.append(text[i + 1:i + 2])
            i += 2
            continue
        if text.startswith("${", i):
            body.append("${}")
            i, line = _scan(text, i + 2, line, inner, True)
            continue
        if text[i] == "\n":
            line += 1
        body.append(text[i])
        i += 1
    out.append(("str", "".join(body), start_line))
    out.extend(inner)
    return i + 1, line


def tokens(text):
    """[(kind, value, line)] with kind 'id', 'str' or 'p' (one punctuation
    character; `?.` reads as `.`). Comments and regex literals are dropped;
    numbers are skipped. Tolerant, not a parser: it only has to stop a string
    or a comment from faking a call, and to keep a split call in one piece."""
    out = []
    _scan(text or "", 0, 1, out, False)
    return out


# ---------------------------------------------------------------- skips

def _tok(toks, i):
    return toks[i] if 0 <= i < len(toks) else (None, None, None)


def _first_string_arg(toks, j):
    """The first string argument of the call whose `(` is toks[j], else None."""
    if _tok(toks, j)[1] != "(":
        return None
    depth = 0
    for kind, value, _line in toks[j:j + 400]:
        if kind == "p" and value in "([{":
            depth += 1
        elif kind == "p" and value in ")]}":
            depth -= 1
            if depth == 0:
                return None
        elif kind == "str" and depth == 1:
            return value
    return None


def skip_sites(text):
    """[(line, name, title)] for every skip site in a JS/TS source. `title`
    is the call's first string argument, or for an annotation the title of
    the test it sits in; None when there is none."""
    toks = tokens(text)
    out, test_title = [], None
    for i, (kind, value, _line) in enumerate(toks):
        nxt, after = _tok(toks, i + 1), _tok(toks, i + 2)
        if kind == "id" and value in ("test", "it") and nxt[1] == "(" and after[0] == "str":
            test_title = after[1]
        if kind == "p" and value == "." and nxt[0] == "id":
            if nxt[1] in SKIP_NAMES:
                out.append((nxt[2], nxt[1], _first_string_arg(toks, i + 2)))
            elif (nxt[1] == "fail" and after[1] == "("
                  and _tok(toks, i - 1)[1] in ("test", "it", "describe")):
                out.append((nxt[2], "fail", _first_string_arg(toks, i + 2)))
        elif (kind == "p" and value == "[" and nxt[0] == "str" and nxt[1] in SKIP_NAMES
              and after[1] == "]"):
            out.append((nxt[2], nxt[1], _first_string_arg(toks, i + 3)))
        elif (kind in ("id", "str") and value == "type" and nxt[1] == ":"
              and after[0] == "str" and after[1] in ANNOTATION_TYPES):
            out.append((after[2], after[1], test_title))
    return out


def _is_js(path):
    return path.lower().endswith(JS_EXTS)


def _is_spec(path):
    return bool(SPEC_FILE_RE.search(path))


def _in_test_dir(path):
    return any(seg in TEST_DIRS for seg in path.split("/")[:-1])


def _resolve_import(files, importer, spec):
    target = posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))
    stem = target[:-len(posixpath.splitext(target)[1])] if _is_js(target) else target
    for cand in ([target] + [stem + ext for ext in JS_EXTS]
                 + [posixpath.join(target, "index" + ext) for ext in JS_EXTS]):
        if cand in files:
            return cand
    return None


def spec_reachable(root, files):
    """Every file in `files` reachable by relative import from a spec file
    (the spec files included). Path aliases (tsconfig `paths`) are not
    followed; a helper reached only that way is caught by TEST_DIRS or not
    at all."""
    files = set(files)
    queue = [f for f in files if _is_spec(f)]
    seen = set(queue)
    while queue:
        rel = queue.pop()
        text = crew_common.read_text(os.path.join(root, rel)) or ""
        for match in _IMPORT_RE.finditer(text):
            dep = _resolve_import(files, rel, match.group(1))
            if dep and dep not in seen:
                seen.add(dep)
                queue.append(dep)
    return seen


def changed_files(root, base):
    """[(old_path_or_None, new_path)] for every file changed since `base`,
    untracked included; None when git could not answer."""
    status = crew_common.git_out(root, "-c", "core.quotePath=false", "diff", "--name-status",
                                 "-M", "--no-color", "--no-ext-diff", base, "--")
    untracked = crew_common.git_out(root, "-c", "core.quotePath=false", "ls-files",
                                    "--others", "--exclude-standard")
    if status is None or untracked is None:
        return None
    out = []
    for row in status.splitlines():
        cols = row.split("\t")
        if len(cols) < 2 or cols[0].startswith("D"):
            continue
        if cols[0][:1] in ("R", "C") and len(cols) == 3:
            out.append((cols[1], cols[2]))
        else:
            out.append((None if cols[0].startswith("A") else cols[1], cols[-1]))
    out += [(None, rel.strip()) for rel in untracked.splitlines() if rel.strip()]
    return out


def find_skips(root, base):
    """[(path, line, text, title)] skip sites the base does not account for,
    or None when git could not answer."""
    changed = changed_files(root, base)
    if changed is None:
        return None
    js = [(old, new) for old, new in changed if _is_js(new)]
    reachable = set()
    if any(not (_is_spec(new) or _in_test_dir(new)) for _old, new in js):
        tracked = crew_common.git_out(root, "-c", "core.quotePath=false", "ls-files")
        if tracked is None:
            return None
        every = [p for p in tracked.splitlines() + [n for _o, n in changed] if _is_js(p)]
        reachable = spec_reachable(root, every)
    found = []
    for old, new in js:
        if not (_is_spec(new) or _in_test_dir(new) or new in reachable):
            continue
        body = crew_common.read_text(os.path.join(root, new))
        if body is None:
            continue
        before = collections.Counter()
        if old is not None and (_is_spec(old) or not _is_spec(new)):
            base_text = crew_common.git_out(root, "show", f"{base}:{old}")
            if base_text is None:
                return None
            before.update((name, title) for _l, name, title in skip_sites(base_text))
        lines = body.splitlines()
        for line, name, title in skip_sites(body):
            if before[(name, title)] > 0:
                before[(name, title)] -= 1
                continue
            text = lines[line - 1] if 0 < line <= len(lines) else ""
            found.append((new, line, text, title))
    return sorted(found, key=lambda r: (r[0], r[1], r[2], r[3] or ""))


def _section(markdown, name):
    """Lines directly under the first heading called `name` (any level), up
    to the next heading of ANY level -- a subsection is not "directly under"."""
    lines = markdown.splitlines()
    for i, text in enumerate(lines):
        match = _HEADING_RE.match(text)
        if match and match.group(2).strip().lower() == name.lower():
            body = []
            for rest in lines[i + 1:]:
                if _HEADING_RE.match(rest):
                    break
                body.append(rest)
            return body
    return []


def exclusions(root, ticket):
    """[(path, text_or_None)] from list items directly under the ticket
    spec's `## Exclusions` whose text begins `skip:`. Prose never counts."""
    if not ticket:
        return []
    text = crew_common.read_text(os.path.join(root, ".work", "tickets", ticket, "spec.md"))
    if not text:
        return []
    rules = []
    for line in _section(text, "Exclusions"):
        match = _EXCLUSION_RE.match(line.strip())
        if match:
            rules.append((_norm(match.group(1)), match.group(2)))
    return rules


def _excluded(path, text, title, rules):
    return any(path == rpath and (want is None or want in text or want in (title or ""))
               for rpath, want in rules)


def _write_json(path, obj):
    text = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def findings_path(root, ticket):
    return os.path.join(root, ".work", "tickets", ticket, "webtest", "findings.json")


def check_skips(root, ticket=None, base=None, bundle_sha256=None):
    """(exit_code, lines). Writes the findings file when a ticket is known,
    stamped with HEAD and, from `review_run.py`, the bundle it was run for."""
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
    head = crew_common.git_out(root, "rev-parse", "HEAD")
    if skips is None or not head:
        return EXIT_UNKNOWN, [f"webtest skips: UNKNOWN -- git could not diff against {base[:12]}"]
    rules = exclusions(root, ticket)
    rows = [{"kind": "healer-skip", "severity": "FIX", "path": p, "line": n,
             "text": t.strip(), "title": title, "excluded": _excluded(p, t, title, rules)}
            for p, n, t, title in skips]
    if ticket:
        _write_json(findings_path(root, ticket),
                    {"ticket": ticket, "base": base, "baseReason": reason, "head": head,
                     "bundle_sha256": bundle_sha256, "findings": rows})
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

def storage_state_values(text):
    """(paths, unresolved) for a playwright config's `storageState` values:
    literal paths, and a snippet for every value that is not a literal or a
    name bound to exactly one literal."""
    toks = tokens(text)
    consts = {}
    for i, (kind, value, _line) in enumerate(toks):
        if kind == "id" and value in ("const", "let", "var") and _tok(toks, i + 2)[1] == "=":
            name, rhs, end = _tok(toks, i + 1)[1], _tok(toks, i + 3), _tok(toks, i + 4)
            literal = rhs[0] == "str" and (end[1] in _VALUE_END or end[0] in ("id", None))
            consts.setdefault(name, []).append(rhs[1] if literal else None)
    paths, unresolved = set(), []
    for i, (kind, value, _line) in enumerate(toks):
        if kind not in ("id", "str") or value != "storageState":
            continue
        nxt = _tok(toks, i + 1)
        if nxt[1] == ":":
            j, depth, expr = i + 2, 0, []
            while j < len(toks) and not (depth == 0 and toks[j][1] in _VALUE_END):
                depth += {"(": 1, "[": 1, "{": 1, ")": -1, "]": -1, "}": -1}.get(toks[j][1], 0)
                expr.append(toks[j])
                j += 1
        elif kind == "id" and _tok(toks, i - 1)[1] in ("{", ",") and nxt[1] in (",", "}"):
            expr = [toks[i]]
        else:
            continue
        if len(expr) == 1 and expr[0][0] == "str":
            paths.add(_norm(expr[0][1]))
            continue
        if len(expr) == 1 and expr[0][0] == "id":
            if expr[0][1] == "undefined":
                continue
            bound = consts.get(expr[0][1], [None])
            if None not in bound and len(set(bound)) == 1:
                paths.add(_norm(bound[0]))
                continue
        unresolved.append(" ".join(t[1] for t in expr[:8]) or "(empty)")
    return paths, unresolved


def declared_storage_state(root):
    """Paths the repository's `.crew/config.json` declares as
    `webtest.storageState` (a string or a list of strings)."""
    try:
        cfg = json.loads(crew_common.read_text(os.path.join(root, ".crew", "config.json")) or "{}")
    except ValueError:
        return []
    value = (cfg.get("webtest") or {}).get("storageState") if isinstance(cfg, dict) else None
    value = [value] if isinstance(value, str) else value
    return sorted(_norm(v) for v in value or [] if isinstance(v, str) and v)


def config_auth_paths(root):
    """(paths, unresolved) across every root `playwright.config.*`."""
    paths, unresolved = set(), []
    for name in sorted(os.listdir(root)):
        if not name.startswith("playwright.config."):
            continue
        text = crew_common.read_text(os.path.join(root, name)) or ""
        found, bad = storage_state_values(text)
        paths.update(found)
        paths.update(_norm(m.group(1)) for m in _AUTH_LITERAL_RE.finditer(text))
        unresolved += [f"{name}: storageState: {b}" for b in bad]
    return sorted(paths), unresolved


def check_auth_leak(root):
    tracked = crew_common.git_out(root, "-c", "core.quotePath=false", "ls-files")
    if tracked is None:
        return EXIT_UNKNOWN, ["webtest auth-leak: UNKNOWN -- git ls-files failed; not a pass"]
    found, unresolved = config_auth_paths(root)
    declared = declared_storage_state(root)
    named = set(found) | set(declared)
    leaks = [p for p in tracked.splitlines()
             if p and (".auth" in p.split("/") or p in named)]
    lines = []
    if leaks:
        lines += (["webtest auth-leak: tracked session state -- untrack it "
                   "(git rm --cached) and gitignore playwright/.auth/:"]
                  + [f"  {p}" for p in leaks])
    if unresolved and not declared:
        lines += (["webtest auth-leak: cannot resolve storageState; declare it in crew config "
                   "`webtest.storageState` (.crew/config.json) -- failing closed:"]
                  + [f"  {u}" for u in unresolved])
    if lines:
        return EXIT_FINDING, lines
    return EXIT_OK, ["webtest auth-leak: no tracked .auth or storageState file"]


# ---------------------------------------------------------------- visual

def installed_playwright(root):
    text = crew_common.read_text(
        os.path.join(root, "node_modules", "@playwright", "test", "package.json"))
    try:
        return json.loads(text).get("version") if text else None
    except (ValueError, AttributeError):
        return None


def container_evidence():
    """The container markers present on this host; empty when there are none."""
    found = [m for m in CONTAINER_MARKERS if os.path.exists(m)]
    cgroup = crew_common.read_text(CGROUP_FILE) or ""
    if any(word in cgroup for word in CGROUP_WORDS):
        found.append(f"{CGROUP_FILE} ({', '.join(w for w in CGROUP_WORDS if w in cgroup)})")
    return found


def expected_chromium(root):
    """The `chromium-<revision>` directory the installed playwright-core
    downloads, or None when browsers.json cannot be read."""
    text = crew_common.read_text(
        os.path.join(root, "node_modules", "playwright-core", "browsers.json"))
    try:
        rows = json.loads(text).get("browsers") if text else None
    except (ValueError, AttributeError):
        return None
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and row.get("name") == "chromium" and row.get("revision"):
            return f"chromium-{row['revision']}"
    return None


def _unverified(why):
    return EXIT_SKIP, [f"webtest visual: UNVERIFIED -- visual diffs run only inside "
                       f"{PINNED_IMAGE}; skipped here ({why})"]


def check_visual(root, extra=(), runner=subprocess.call):
    image = os.environ.get(IMAGE_ENV, "")
    if not sys.platform.startswith("linux"):
        return _unverified(sys.platform)
    if image != PINNED_IMAGE:
        return _unverified(f"{IMAGE_ENV}={image!r}" if image else f"{IMAGE_ENV} unset")
    markers = container_evidence()
    if not markers:
        return _unverified(f"{IMAGE_ENV} is set but nothing shows a container: none of "
                           f"{', '.join(CONTAINER_MARKERS)}, and no container in {CGROUP_FILE}")
    if not os.path.isdir(BROWSERS_DIR):
        return _unverified(f"container, but no Playwright image browser store {BROWSERS_DIR}")
    version = installed_playwright(root)
    if version != PINNED_PLAYWRIGHT:
        return EXIT_FINDING, [f"webtest visual: @playwright/test is {version or 'not installed'}, "
                              f"the image is {PINNED_PLAYWRIGHT}; baselines would not compare"]
    chromium = expected_chromium(root)
    if chromium is None:
        return _unverified("cannot read node_modules/playwright-core/browsers.json, so the "
                           "image's browsers cannot be matched to the pinned release")
    if not os.path.isdir(os.path.join(BROWSERS_DIR, chromium)):
        return _unverified(f"{BROWSERS_DIR} has no {chromium}, the browser "
                           f"{PINNED_PLAYWRIGHT} renders with -- not the pinned image")
    verified = (f"verified: {', '.join(markers)}; {BROWSERS_DIR}/{chromium}; "
                f"@playwright/test {version}")
    rc = runner(["npx", "playwright", "test", "--project=visual"] + list(extra), cwd=root)
    # A real run cannot SKIP: 77 from playwright is a failure, not an absent environment.
    code = EXIT_OK if rc == 0 else EXIT_FINDING
    return code, [f"webtest visual: {verified}",
                  f"webtest visual: npx playwright test --project=visual exited {rc}"]


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
