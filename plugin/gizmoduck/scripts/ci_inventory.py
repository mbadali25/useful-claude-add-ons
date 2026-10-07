"""ci_inventory.py - the monorepo endpoints inventory (`endpoints-inventory.md`).

A repository is walked for MODULES, and each module's endpoints are listed in
one generated Markdown file at the repository root. The pattern - per-module
declarations compiled into a generated root document, a check that fails when
the committed copy is stale, and a branch-only publish - follows a monorepo
that already runs it; the code here is written for gizmoduck.

Module discovery. Under each configured root (default: the repository root),
a directory is a module when it directly holds either

  - the declaration file (`public-endpoint.md` by default), or
  - a project marker: *.csproj / *.fsproj / *.vbproj, package.json,
    pyproject.toml, setup.py, requirements.txt, main.tf, go.mod, pom.xml,
    build.gradle(.kts), Cargo.toml, composer.json.

The OUTERMOST qualifying directory wins: once a directory is a module, nothing
below it is considered separately (`svc/frontend/package.json` belongs to
`svc`). A root is itself a module only when nothing below it qualifies - a
single-project repository is one module, `.`. Hidden directories, ci_detect's
dependency/build directories, and the configured excludes (fnmatch globs on
the repo-relative directory path; default `docs`, `docs/*`) are never walked.
Discovery is bounded in depth (_MAX_MODULE_DEPTH below a root) and never
follows a symlink.

Per module: when the declaration exists it is the whole truth for that module
(nothing is autodetected there); otherwise `ci_detect.detect(root, module)`
runs and every endpoint finding is listed with its confidence and `path:line`.
The declaration format is the one that repository uses: YAML-style frontmatter
between `---` lines with `name` and `url` required, `status`, `kind`,
`additional_endpoints` (a list), and optionally `staging_url`. Only those keys
are read; any other key and its continuation lines are ignored. The
frontmatter parser is deliberately small and self-contained - plain or quoted
scalars and `- item` lists - so the output never depends on whether PyYAML is
installed where it runs; a line it cannot read is an error naming `path:line`.

Sources are cited by file, not `path:line`: a line number moves with every
edit above it, and an inventory that goes stale on unrelated edits trains
people to regenerate it without reading the diff.

Staging URL column: a declared module's `status: staging` URL, or its
`staging_url` for the main `url`; a detected module's best medium-or-high
confidence staging literal (`gizmoduck-ci.json`'s owner-confirmed base URL for
the root module `.`) joined with the endpoint path; otherwise `undetermined` -
never guessed. Every URL goes through ci_guard.redact_url.

Purity. `render(...)` is a pure function of the repository: no dates, no
absolute paths, no environment, sorted modules and endpoints, LF newlines.
Rendering twice - or from a copy of the repository at another path - gives the
same bytes. That is what makes `check` meaningful.
"""
import difflib
import fnmatch
import os
import re
import stat

import ci_detect
import ci_guard

FORMAT = 1
DEFAULT_OUTPUT = "endpoints-inventory.md"
DEFAULT_DECLARATION = "public-endpoint.md"
DEFAULT_EXCLUDE = ("docs", "docs/*")
MARKER_NAMES = frozenset({"package.json", "pyproject.toml", "setup.py", "requirements.txt", "main.tf", "go.mod",
                          "pom.xml", "build.gradle", "build.gradle.kts", "Cargo.toml", "composer.json"})
MARKER_SUFFIXES = (".csproj", ".fsproj", ".vbproj")
REGENERATE = 'python3 "$GIZMODUCK_HOME/scripts/gizmoduck_ci.py" inventory --repo .'
_MAX_MODULE_DEPTH = 6
_MAX_DIR_ENTRIES = 20_000
_KEYS = ("name", "url", "status", "kind", "additional_endpoints", "staging_url")
_FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.md")


class InventoryError(ValueError):
    pass


# --------------------------------------------------------------------------
# settings
# --------------------------------------------------------------------------

def _clean_rel(value, what):
    if not isinstance(value, str) or not value.strip():
        raise InventoryError(f"{what} must be a non-empty repo-relative path")
    value = value.strip().replace("\\", "/")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value) or ".." in value.split("/"):
        raise InventoryError(f"{what} {value!r} must be repo-relative and stay inside the repository")
    return os.path.normpath(value).replace("\\", "/")


def settings(config=None, output=None, roots=None, exclude=None, declaration=None):
    """The effective inventory settings: CLI values over gizmoduck-ci.json's
    `inventory` block over the defaults."""
    block = (config or {}).get("inventory") or {}
    if not isinstance(block, dict):
        raise InventoryError(f"{ci_detect.CONFIG_NAME}: `inventory` must be an object")
    out = output or block.get("output") or DEFAULT_OUTPUT
    decl = declaration or block.get("declaration") or DEFAULT_DECLARATION
    for label, name in (("output", out), ("declaration", decl)):
        if not isinstance(name, str) or not _FILE_NAME.fullmatch(name):
            raise InventoryError(f"inventory {label} {name!r} must be a plain *.md file name at the repository "
                                 f"root (letters, digits, . _ -)")
    raw_roots = roots or block.get("roots") or ["."]
    raw_excl = list(exclude) if exclude else list(block.get("exclude") or DEFAULT_EXCLUDE)
    if not isinstance(raw_roots, list) or not isinstance(raw_excl, list):
        raise InventoryError("inventory roots and exclude must be lists")
    return {"output": out, "declaration": decl,
            "roots": sorted({_clean_rel(r, "inventory root") for r in raw_roots}),
            "exclude": sorted({str(e).strip().strip("/") for e in raw_excl if str(e).strip()})}


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------

def _entries(path, rel=None):
    """Sorted (name, is_dir, is_file) for a directory's entries, symlinks
    excluded; bounded.

    A directory this cannot fully read - permission denied, a scandir error
    partway through, or more entries than `_MAX_DIR_ENTRIES` - makes
    discovery under it INCOMPLETE, never an empty (and so passing) result:
    raise `InventoryError` naming the path rather than returning `[]`. An
    empty list here used to be indistinguishable from "no entries", so a
    directory nobody could read silently dropped every module below it and
    the stale check still passed."""
    label = path if rel is None else rel
    out = []
    try:
        with os.scandir(path) as it:
            for n, entry in enumerate(it):
                if n >= _MAX_DIR_ENTRIES:
                    raise InventoryError(f"{label}: more than {_MAX_DIR_ENTRIES} entries - "
                                         f"discovery is bounded and cannot be complete here")
                if entry.is_symlink():
                    continue
                out.append((entry.name, entry.is_dir(follow_symlinks=False),
                            entry.is_file(follow_symlinks=False)))
    except OSError as exc:
        raise InventoryError(f"{label}: cannot read directory ({exc.strerror or exc})") from exc
    return sorted(out)


def _qualifies(entries, declaration):
    for name, _is_dir, is_file in entries:
        if is_file and (name == declaration or name in MARKER_NAMES or name.endswith(MARKER_SUFFIXES)):
            return True
    return False


def _excluded(rel, exclude):
    return any(fnmatch.fnmatchcase(rel, pat) for pat in exclude)


def _walk_modules(path, rel, depth, conf, below):
    """Append to `below` every outermost qualifying directory under `path`."""
    if depth > _MAX_MODULE_DEPTH:
        return
    for name, is_dir, _ in _entries(path, rel):
        if not is_dir or name.startswith(".") or name in ci_detect._SKIP_DIRS:
            continue
        child_rel = name if rel == "." else f"{rel}/{name}"
        if _excluded(child_rel, conf["exclude"]):
            continue
        child = os.path.join(path, name)
        if _qualifies(_entries(child, child_rel), conf["declaration"]):
            below.append(child_rel)
        else:
            _walk_modules(child, child_rel, depth + 1, conf, below)


def discover_modules(root, conf):
    """Repo-relative module directories, sorted; `.` for a single-project repo."""
    root = os.path.abspath(root)
    found = set()
    for r in conf["roots"]:
        base = os.path.join(root, r)
        if not ci_detect._inside(root, base) or os.path.islink(base) or not os.path.isdir(base):
            raise InventoryError(f"inventory root {r!r} is not a directory inside the repository")
        below = []
        _walk_modules(base, r, 1, conf, below)
        if below:
            found.update(below)
        elif _qualifies(_entries(base, r), conf["declaration"]):
            found.add(r)
    ordered = sorted(found)
    # Outermost wins across overlapping roots too.
    return [m for m in ordered
            if not any(o != m and (o == "." or m.startswith(o + "/")) for o in ordered)]


# --------------------------------------------------------------------------
# declarations
# --------------------------------------------------------------------------

def _scalar(raw, where):
    raw = raw.strip()
    if not raw:
        return ""
    if raw[0] in "\"'":
        q = raw[0]
        end = raw.find(q, 1)
        while q == '"' and end > 0 and raw[end - 1] == "\\":
            end = raw.find(q, end + 1)
        if end < 0:
            raise InventoryError(f"{where}: unterminated quoted value")
        rest = raw[end + 1:].strip()
        if rest and not rest.startswith("#"):
            raise InventoryError(f"{where}: text after a quoted value")
        body = raw[1:end]
        return body.replace('\\"', '"').replace("\\\\", "\\") if q == '"' else body.replace("''", "'")
    if raw[0] in "|>[{&*!":
        raise InventoryError(f"{where}: block, flow and tagged YAML values are not read here - write the value "
                             f"on one line, quoted")
    return re.sub(r"\s+#.*$", "", raw).strip()


def parse_declaration(text, rel):
    """(fields, line_of_key) from a declaration's frontmatter. Raises
    InventoryError naming `rel:line` for anything it cannot read."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise InventoryError(f"{rel}:1: does not start with a '---' frontmatter block")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise InventoryError(f"{rel}:1: frontmatter block is not closed with a second '---' line") from None
    fields, where_of, current = {}, {}, None
    for i in range(1, end):
        line, n = lines[i], i + 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] not in " \t-":
            key, sep, rest = line.partition(":")
            key = key.strip()
            if not sep or not re.fullmatch(r"[A-Za-z_][\w-]*", key):
                raise InventoryError(f"{rel}:{n}: expected `key: value`")
            current = key if key in _KEYS else None
            if current is None:
                continue
            if key in fields:
                raise InventoryError(f"{rel}:{n}: `{key}` is declared twice")
            where_of[key] = n
            fields[key] = _scalar(rest, f"{rel}:{n}") if rest.strip() else []
            continue
        if current is None:
            continue    # continuation of a key this parser does not read
        item = line.strip()
        if not item.startswith("-") or not isinstance(fields[current], list):
            raise InventoryError(f"{rel}:{n}: `{current}` continues on an indented line this parser cannot "
                                 f"read - write it on one line, quoted")
        fields[current].append(_scalar(item[1:], f"{rel}:{n}"))
    for key in ("name", "url"):
        if not isinstance(fields.get(key), str) or not fields[key]:
            raise InventoryError(f"{rel}: missing required frontmatter key `{key}`")
    extra = fields.get("additional_endpoints", [])
    if isinstance(extra, str):
        extra = [extra] if extra else []
    fields["additional_endpoints"] = [e for e in extra if e]
    for key in ("status", "kind", "staging_url"):
        if isinstance(fields.get(key), list):
            raise InventoryError(f"{rel}:{where_of[key]}: `{key}` must be a single value")
    return fields, where_of


def _read_text(path):
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    return ci_detect._read(path)


# --------------------------------------------------------------------------
# per-module rows
# --------------------------------------------------------------------------

def _url(value):
    return ci_guard.redact_url(value.strip()) if isinstance(value, str) else ""


def _join_url(base, path):
    return base.rstrip("/") + (path if path.startswith("/") else "/" + path)


def _declared(root, module, conf):
    rel = conf["declaration"] if module == "." else f"{module}/{conf['declaration']}"
    text = _read_text(os.path.join(root, rel))
    if text is None:
        raise InventoryError(f"{rel}: not a readable regular file")
    fields, _ = parse_declaration(text, rel)
    status = (fields.get("status") or "").strip().lower()
    main_staging = fields.get("url") if status == "staging" else fields.get("staging_url")
    rows = [{"endpoint": _url(fields["url"]), "method": "", "source": "declared", "confidence": "",
             "where": rel,
             "staging_url": _url(main_staging) if main_staging else "not declared", "scan_url": ""}]
    for extra in fields["additional_endpoints"]:
        rows.append({"endpoint": _url(extra), "method": "", "source": "declared", "confidence": "",
                     "where": rel,
                     "staging_url": _url(extra) if status == "staging" else "not declared", "scan_url": ""})
    for r in rows:
        if r["staging_url"].startswith(("http://", "https://")):
            r["scan_url"] = r["staging_url"]
    return {"path": module, "mode": "declared", "declaration": rel, "name": fields["name"],
            "status": status, "kind": (fields.get("kind") or "").strip().lower(),
            "staging_base": None, "rows": sorted(rows, key=lambda r: (r["endpoint"], r["where"]))}


def _file_of(source):
    """`path:line` -> `path`. Line numbers are left out of the inventory on
    purpose: an edit above a route would otherwise make it stale."""
    return re.sub(r":\d+(-\d+)?$", "", source)


def _staging_base(det, module, config):
    if module == ".":
        base = ((config or {}).get("staging") or {}).get("base_url")
        if isinstance(base, str) and base.startswith(("http://", "https://")):
            return {"url": _url(base), "source": f"{ci_detect.CONFIG_NAME} (owner-confirmed)"}
    for f in ci_detect._staging_candidates(det):
        if f.confidence in (ci_detect.HIGH, ci_detect.MEDIUM):
            return {"url": _url(f.value), "source": f"detected, {f.confidence} - {_file_of(f.source)}"}
    return None


def _detected(root, module, config):
    det = ci_detect.detect(root, module)
    base = _staging_base(det, module, config)
    best = {}
    for f in det.of("endpoint"):
        value = ci_detect.normalise_path(f.value) if f.value.startswith("/") else _url(f.value)
        key = (value, f.method)
        cur = best.get(key)
        if cur is None or ci_detect._RANK[f.confidence] > ci_detect._RANK[cur.confidence] or (
                f.confidence == cur.confidence and _file_of(f.source) < _file_of(cur.source)):
            best[key] = f
    rows = []
    for (value, method), f in sorted(best.items()):
        if value.startswith("/"):
            staging = _join_url(base["url"], value) if base else "undetermined"
            scan_url = _join_url(base["url"], ci_detect.scan_path(value)) if base else ""
        else:
            staging, scan_url = value, value
        source = "declared (crew ledger)" if f.detector == "crew-ledger" else "detected"
        conf = f.confidence + (", protected" if f.protected else "")
        rows.append({"endpoint": value, "method": method, "source": source, "confidence": conf,
                     "where": _file_of(f.source), "staging_url": staging, "scan_url": scan_url})
    return {"path": module, "mode": "detected", "declaration": None, "name": module, "status": "", "kind": "",
            "staging_base": base, "rows": rows}


def build(root, conf, config=None):
    """The inventory as data: one dict per module, sorted by path."""
    root = os.path.abspath(root)
    modules = []
    for module in discover_modules(root, conf):
        decl = conf["declaration"] if module == "." else f"{module}/{conf['declaration']}"
        if os.path.isfile(os.path.join(root, decl)) and not os.path.islink(os.path.join(root, decl)):
            modules.append(_declared(root, module, conf))
        else:
            modules.append(_detected(root, module, config))
    return modules


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _cell(text):
    # `<` is neutralised so an embedded HTML/script tag is never live Markdown;
    # `\r`/`\n` so a module path or declared value can never inject a line of
    # its own (a forged heading, say) into the generated document.
    text = str(text).replace("\r", " ").replace("\n", " ").replace("|", "\\|").replace("<", "&lt;")
    return text


def _code(text):
    """`text` as an inline code span, always - never a bare, unquoted `_cell`
    fallback. A code span's content is literal in Markdown (no HTML, no
    further Markdown), so the fence must always close: choose a run of
    backticks one longer than any run already in the text, padding with a
    space when the text itself starts or ends with a backtick."""
    text = _cell(str(text))
    if "`" not in text:
        return f"`{text}`"
    longest = max(len(run) for run in re.findall(r"`+", text))
    fence = "`" * (longest + 1)
    pad = " " if text[:1] == "`" or text[-1:] == "`" else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def render(modules, conf):
    n_rows = sum(len(m["rows"]) for m in modules)
    empty = [m for m in modules if not m["rows"]]
    lines = [
        "# Endpoints inventory",
        "",
        f"<!-- gizmoduck endpoints inventory, format {FORMAT}. Generated - do not edit. -->",
        "",
        "> **Generated, do not edit.** Built by gizmoduck from each module's own",
        f"> `{conf['declaration']}` declaration, or by endpoint autodetection where a module",
        "> declares nothing. To change a row, edit the declaration (or the code), then run",
        f"> `{REGENERATE}`",
        "> and commit the result. A pipeline check fails while this file is stale.",
        "",
        "> **These are declarations and static detections, not observations.** Nothing that",
        "> built this file contacted an endpoint. `undetermined` means no staging URL could be",
        "> read from the repository; it is never guessed.",
        "",
        "This file carries no generation date on purpose: it is a pure function of the",
        "repository, so it changes only when an endpoint does. Provenance is git history.",
        "",
        "## Summary",
        "",
        "| Measure | Count |",
        "| --- | ---: |",
        f"| Modules | {len(modules)} |",
        f"| Declared (`{conf['declaration']}`) | {sum(1 for m in modules if m['mode'] == 'declared')} |",
        f"| Autodetected | {sum(1 for m in modules if m['mode'] == 'detected')} |",
        f"| Endpoints | {n_rows} |",
        f"| Modules with no endpoint (UNVERIFIED) | {len(empty)} |",
        "",
    ]
    if not modules:
        lines += ["**UNVERIFIED:** no module was found. A module is a directory holding "
                  f"`{conf['declaration']}` or a project marker (csproj, package.json, pyproject.toml, "
                  "main.tf, ...).", ""]
    for m in modules:
        lines.append(f"## {_cell(m['path'])}")
        lines.append("")
        if m["mode"] == "declared":
            meta = ", ".join(x for x in (m["kind"], m["status"]) if x)
            lines.append(f"Declared in {_code(m['declaration'])}: **{_cell(m['name'])}**"
                         + (f" ({_cell(meta)})" if meta else "") + ".")
        else:
            base = m["staging_base"]
            lines.append("Autodetected (no declaration). Staging base: "
                         + (f"{_code(base['url'])} ({_cell(base['source'])})." if base else "undetermined."))
        lines.append("")
        if not m["rows"]:
            lines += ["**UNVERIFIED** - no endpoint declared or detected. Add "
                      f"{_code((m['path'] + '/' if m['path'] != '.' else '') + conf['declaration'])} "
                      f"or {ci_detect.DETECT_HINT}.", ""]
            continue
        lines += ["| Endpoint | Source | Staging URL |", "| --- | --- | --- |"]
        for r in m["rows"]:
            what = (r["method"] + " " if r["method"] else "") + r["endpoint"]
            src = r["source"] + (f", {r['confidence']}" if r["confidence"] else "") + f" - {_code(r['where'])}"
            staging = _code(r["staging_url"]) if r["staging_url"].startswith(("http://", "https://")) \
                else _cell(r["staging_url"])
            lines.append(f"| {_code(what)} | {src} | {staging} |")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def generate(root, conf, config=None):
    return render(build(root, conf, config), conf)


def check(root, conf, config=None):
    """(current, expected_text, diff_lines). A committed file with CRLF line
    endings (a Windows checkout) is compared as LF."""
    expected = generate(root, conf, config)
    path = os.path.join(root, conf["output"])
    committed = _read_text(path)
    if committed is None:
        return False, expected, [f"{conf['output']} is missing"]
    committed = committed.replace("\r\n", "\n")
    if committed == expected:
        return True, expected, []
    diff = list(difflib.unified_diff(committed.splitlines(), expected.splitlines(),
                                     f"{conf['output']} (committed)", f"{conf['output']} (regenerated)",
                                     lineterm="", n=1))
    return False, expected, diff
