"""The endpoint ledger: `.crew/endpoints.json` and its scan artifacts.

Split out of `crew_state.py` in 0.16.21, which had reached pylint's
`max-module-lines=3300` with five lines to spare. This block is the one place
the module divides cleanly: it reads and writes one file nothing else there
touches, and `crew_state` needs only five names back from it --
`declare_endpoint`, `load_endpoints`, `read_endpoints`, `record_scan_artifact`
and `scan_artifact_path`, all re-exported so no caller had to change.

Standard library only, and every read fails soft, for the reason `crew_state`
does: this runs from a SessionStart hook, where an exception breaks every
session opened in the repository.
"""

import hashlib
import json
import os
import re
import time
import uuid

from crew_common import dict_or_empty, git_out, read_text


# --- Endpoint ledger, for gizmoduck's security-scan obligation --------------
#
# `.crew/endpoints.json` tracks external endpoints so a security scan can be
# demanded of each one. This block only exists to serve `endpointUnscanned`
# below, and does no real work at all when gizmoduck is not installed -- see
# gizmoduck_installed. Every reader here still fails soft for the same reason
# every other read_* in this module does: it runs from a SessionStart hook.

_ENDPOINTS_PATH_PARTS = (".crew", "endpoints.json")


def _endpoints_path(root):
    return os.path.join(root, *_ENDPOINTS_PATH_PARTS)


# A conservative allowlist for a ledger record's "id": no path separator of
# either kind, so an id can never be more than ONE filesystem path component
# no matter what characters a hand-edited ledger squeezes in around it -- a
# value like "../../../unrelated" fails this outright rather than being
# stripped or escaped. Checked at MINT time (declare_endpoint) and again at
# READ time (scan_artifact_path) -- never trusted because it was minted
# safely once, since the ledger is a committed, hand-editable JSON file.
_SAFE_ENDPOINT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _valid_endpoint_id(value):
    """Whether `value` is safe to interpolate into a filesystem path as a
    single path component. See _SAFE_ENDPOINT_ID_RE above for what "safe"
    means here and why rejecting is the only sound response to a value that
    fails this -- there is no mangling that turns an unsafe id into the
    RIGHT safe one, only into a different unsafe one.
    """
    return isinstance(value, str) and bool(_SAFE_ENDPOINT_ID_RE.match(value))


def _relative_safe(root, value, default):
    """`value` -- a repo-relative path claimed by a hand-editable ledger
    record -- if joining it onto `root` stays inside the repository, else
    `default`. Same containment check as `contained_path` above, but hands
    back the caller's own repo-relative value (or the default) rather than
    an absolute path: every caller here rejoins the result onto `root` again
    later (`os.path.isfile(os.path.join(root, artifact))`), and handing back
    an absolute path here would double-root that join.
    """
    if not isinstance(value, str) or not value.strip():
        return default
    base = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(base, value))
    try:
        inside = os.path.commonpath([base, candidate]) == base
    except ValueError:
        inside = False          # different drives on Windows
    return value if inside else default


def _empty_endpoint_doc():
    """A FRESH empty document -- never a shared constant. `dict(SOME_MODULE_
    LEVEL_DICT)` copies the dict but not the values inside it, so a bare
    `{"records": [], "nextSeq": 0}` reused as a "default" would hand every
    caller with an absent/malformed ledger the SAME list object; the first
    declare_endpoint call to append to it would then leak that record into
    every OTHER repo's "empty" read for the rest of the process. A function
    call sidesteps this the way `def f(x=None): x = x or []` does for a
    mutable default argument.
    """
    return {"records": [], "nextSeq": 0}


def _load_endpoint_doc(root):
    """The ledger's full document -- `records` plus `nextSeq`, the minting
    sequence declare_endpoint counts up from -- or a fresh empty one when the
    file is absent, malformed, or shaped wrong. Never raises, same contract
    as load_config. Non-dict record entries are dropped rather than trusted;
    `nextSeq` resets to 0 (not merely "0 or higher") for anything that is not
    a plain non-negative int, including the JSON literal `true` -- `bool` is
    an `int` subclass in Python, and `isinstance(True, int)` is True, so the
    bool check has to come before the range check or a hand-edited
    `"nextSeq": true` would mint "ep-0002" next instead of being rejected.
    """
    text = read_text(_endpoints_path(root))
    if text is None:
        return _empty_endpoint_doc()
    try:
        parsed = json.loads(text)
    except ValueError:
        return _empty_endpoint_doc()
    if not isinstance(parsed, dict):
        return _empty_endpoint_doc()
    records = parsed.get("records")
    records = ([record for record in records if isinstance(record, dict)]
               if isinstance(records, list) else [])
    next_seq = parsed.get("nextSeq")
    if isinstance(next_seq, bool) or not isinstance(next_seq, int) or next_seq < 0:
        next_seq = 0
    return {"records": records, "nextSeq": next_seq}


def load_endpoints(root):
    """The ledger's records, or [] when the file is absent, malformed, or its
    "records" value is not a list. Never raises -- same contract as
    load_config. Non-dict entries are dropped rather than trusted, since the
    file is meant to be machine-written but is still a JSON file on disk."""
    return _load_endpoint_doc(root)["records"]


def _write_endpoints(root, doc):
    """Atomic replace of the ledger file. Best-effort; returns False (never
    raises) on any OSError, same failure posture as `_write_slot` below.

    `doc` is the FULL document (`{"records": [...], "nextSeq": N}`), not
    just the records list, because declare_endpoint needs the sequence
    counter written in the SAME atomic write as the record it mints -- two
    separate writes would let a crash between them either replay or skip a
    sequence number.

    Write-to-a-temp-file-then-rename rather than write-in-place: this is
    exactly the shared-mutable-file pattern `.crew/codemap/crew.md`
    describes crew already abandoning for `dispatch.json` (see
    `_write_slot`, `_append_dispatch`), for the same reason -- a reader must
    never be able to observe a half-written file, and a write that fails
    partway through must leave the ORIGINAL intact. `os.replace` is atomic
    on both POSIX and Windows.

    What this does NOT do: stop two writers from losing each other's
    updates. Atomic replace only guarantees each individual WRITE is
    all-or-nothing -- it says nothing about two callers who both read the
    document, each add their own record to their own in-memory copy, and
    then each atomically replace the file with THEIR copy. The second
    replace wins outright and the first writer's record is gone, with no
    error raised on either side (BLOCK 2, reproduced: 8 concurrent processes
    declaring 8 distinct endpoints kept 2; 20 threads kept 1). That is a
    lost update, a different failure from corruption, and this function does
    not address it -- see `_endpoints_lock`, which `declare_endpoint` holds
    for the entire read-modify-write cycle for that reason.
    """
    path = _endpoints_path(root)
    tmp_path = f"{path}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # newline="\n": this file is JSON, not one of the `.sh` scripts the
        # CRLF landmine names, but pinning it costs nothing and keeps every
        # file this module writes consistent on Windows.
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(doc, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except OSError:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False
    return True


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# BLOCK 2: `_write_endpoints`'s atomic replace protects one write from
# corruption, not two writers from losing each other's records -- see its
# docstring. `declare_endpoint` is the only place that reads, mutates and
# writes this document, so the fix belongs there: hold an exclusive lock
# across the whole read-modify-write cycle, the same idiom `hook_once.claim`
# already uses elsewhere in this plugin -- `os.open` with `O_CREAT|O_EXCL` as
# the atomic "who got here first" primitive -- rather than inventing a
# second locking mechanism. It differs from `hook_once.claim` in lifetime
# only: that one is a permanent per-session marker, never released, because
# its job is "run this exactly once for this session". This one is released
# the moment the write finishes, because its job is "let exactly one writer
# through at a time, then let the next one in".
_ENDPOINTS_LOCK_STALE_SECONDS = 30
_ENDPOINTS_LOCK_RETRY_SECONDS = 0.05
_ENDPOINTS_LOCK_TIMEOUT_SECONDS = 5


def _acquire_endpoints_lock(root):
    """Best-effort exclusive lock over the endpoint ledger file. Returns the
    lock path to release, or None if it could not be acquired -- callers
    proceed unlocked rather than hanging a hook forever on a stuck lock.

    A lock older than `_ENDPOINTS_LOCK_STALE_SECONDS` is assumed to be left
    by a process that crashed before releasing it, and is removed so one
    dead process cannot wedge every future `declare_endpoint` call in the
    repo. Spins with a short sleep rather than blocking: this runs from a
    short-lived CLI call and a SessionStart hook, neither of which should
    ever wait long, so giving up after `_ENDPOINTS_LOCK_TIMEOUT_SECONDS`
    (falling back to the old, race-prone behaviour rather than never
    returning) is the safer failure than hanging a session open.
    """
    path = _endpoints_path(root) + ".lock"
    deadline = time.time() + _ENDPOINTS_LOCK_TIMEOUT_SECONDS
    while True:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            return path
        except FileExistsError:
            try:
                stale = (time.time() - os.path.getmtime(path)
                          > _ENDPOINTS_LOCK_STALE_SECONDS)
            except OSError:
                stale = False
            if stale:
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
            if time.time() > deadline:
                return None
            time.sleep(_ENDPOINTS_LOCK_RETRY_SECONDS)
        except OSError:
            return None


def _release_endpoints_lock(lock_path):
    if not lock_path:
        return
    try:
        os.remove(lock_path)
    except OSError:
        pass


def declare_endpoint(root, endpoint, location, ticket=None, endpoint_id=None):
    """The documented entry point for an AUTHORITATIVE ledger record: a
    ticket or dispatch stated that this endpoint was created. This is the
    ONLY function in this module allowed to write `source="declared"`, the
    only writer of `.crew/endpoints.json` at all (candidates are computed,
    never persisted -- see infer_endpoints/read_endpoints below), and the
    entry point named in `plugin/crew/agents/pm.md` and `commands/work.md`
    for promoting a researched candidate. A record is "declared", not merely
    reported as one, only via this function.

    `location` is the `path:line` the endpoint was declared at, or a
    ticket/dispatch reference when there is no single line to cite.
    `endpoint_id` re-declares (updates in place) an existing record instead
    of minting a duplicate; omit it for a new record. New ids are minted
    from a sequence counter persisted alongside the records (`nextSeq`),
    never from `len(records) + 1` -- the latter collides the moment any
    record is removed from this committed, hand-editable file (declare a,
    declare b, delete a, declare c: `len()+1` mints b's own id for c).

    Re-declaring an EXISTING id updates `endpoint`/`location`/`ticket` but
    leaves `status` exactly as it was (finding 11). It used to force it back
    to `"open"` unconditionally, which silently reopened a record a human
    had deliberately closed -- the documented promotion flow
    (`plugin/crew/agents/pm.md`, `commands/work.md`) never passes
    `endpoint_id` at all, so the only realistic caller of this branch is
    someone amending the details of a record that already exists, not
    promoting a fresh candidate; that caller has no business flipping its
    status either way. A record's status changes only through the field
    itself (a human hand-editing the ledger, or a future explicit
    reopen/close entry point), never as a side effect of restating what an
    endpoint is.

    Returns `{"error": ...}` -- never raises -- when a caller-supplied
    `endpoint_id` fails `_valid_endpoint_id`; nothing may mint or re-target a
    record under an id that is not safe to use in a filesystem path.
    """
    if endpoint_id is not None and not _valid_endpoint_id(endpoint_id):
        return {"error": f"refusing to declare an unsafe endpoint id: {endpoint_id!r}"}
    lock = _acquire_endpoints_lock(root)
    try:
        doc = _load_endpoint_doc(root)
        records = doc["records"]
        now = _now_iso()
        if endpoint_id:
            for record in records:
                if record.get("id") == endpoint_id:
                    # status deliberately absent from this update -- see the
                    # docstring above (finding 11).
                    record.update(endpoint=endpoint, source="declared",
                                  location=location, ticket=ticket,
                                  updatedAt=now)
                    _write_endpoints(root, doc)
                    return record
            new_id = endpoint_id
        else:
            doc["nextSeq"] += 1
            new_id = f"ep-{doc['nextSeq']:04d}"
        record = {
            "id": new_id, "endpoint": endpoint, "source": "declared",
            "status": "open", "location": location, "ticket": ticket,
            "createdAt": now,
        }
        records.append(record)
        _write_endpoints(root, doc)
        return record
    finally:
        _release_endpoints_lock(lock)


# Files crew's own source lives under. Excluded from candidate generation
# entirely: this module comments on the exact call shapes _INFERENCE_SIGNALS
# looks for (see the http-route entry below), and a signal that flags its
# own source file on every session opened in THIS repo is the "cries wolf"
# failure finding 9 named -- reproduced as a hit at crew_state.py's own
# line describing the Express/Fastify/Koa shape in prose.
_INFERENCE_EXCLUDED_PREFIXES = ("plugin/crew/hooks/scripts/",)


def _excluded_from_inference(path):
    normalized = (path or "").replace("\\", "/")
    return any(normalized.startswith(prefix) or f"/{prefix}" in normalized
               for prefix in _INFERENCE_EXCLUDED_PREFIXES)


# Line prefixes (after stripping leading whitespace) that mark a comment in
# one of the languages these signals watch -- Python/YAML/shell `#`, C-style
# `//` and `/*`/`*` continuation, SQL/Lua `--`, and HTML/XML `<!--`. A diff
# line matching a signal but opening with one of these is prose ABOUT the
# shape, not the shape itself -- exactly the repro where a comment reading
# "app.get(\"/x\", ...)" as an EXAMPLE was read as a route registration.
_COMMENT_PREFIXES = ("#", "//", "/*", "*", "--", "<!--")


def _inside_quoted_string(text, index):
    """Whether position `index` in `text` sits inside a quote that opened
    earlier on the SAME line -- a cheap, single-line heuristic (no
    multi-line string tracking, which would need the whole file, not just
    one diff line) that is enough to tell "app.get(" the CALL from
    "app.get(" the WORDS INSIDE SOMEONE ELSE's STRING, e.g.
    `description: "app.get('/x')"`, a config value that happens to contain
    an example rather than a route registration.
    """
    before = text[:index]
    single = len(re.findall(r"(?<!\\)'", before))
    double = len(re.findall(r'(?<!\\)"', before))
    return single % 2 == 1 or double % 2 == 1


# Each entry flags a diff line that plausibly introduces a new externally
# reachable endpoint. Every hit becomes a CANDIDATE only (see read_endpoints,
# which computes these fresh on every read and never persists them) -- a
# regex match on one line cannot know whether the route is actually wired to
# a public listener, only that the SHAPE of one just appeared. Extend this by
# appending one more (name, pattern, label, extensions) tuple; nothing else
# needs to change. `extensions` -- a tuple of lower-case file extensions, or
# () to match any file -- narrows a signal to the kind of file it actually
# describes: an "app.get(" match inside a `.py` docstring is not a JS route
# registration, and gating on the file's own extension is cheaper and more
# reliable than trying to detect the language from the line's syntax.
_INFERENCE_SIGNALS = (
    # Express/Fastify/Koa-style route registration: app.get("/x", ...).
    # Framework-agnostic on purpose -- new frameworks keep re-inventing this
    # exact call shape.
    ("http-route",
     re.compile(r"""(?:app|router)\.(?:get|post|put|patch|delete|all)\s*\(\s*['"]"""),
     "an Express/Fastify/Koa-style route registration",
     (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")),
    # Flask/FastAPI decorator route.
    ("python-route",
     re.compile(r"@(?:app|router)\.(?:get|post|put|patch|delete|route)\s*\("),
     "a Flask/FastAPI route decorator",
     (".py",)),
    # A Kubernetes Ingress resource -- what actually exposes a service to the
    # outside world, independent of what the application code does.
    ("k8s-ingress", re.compile(r"^\s*kind:\s*Ingress\b"),
     "a Kubernetes Ingress resource",
     (".yml", ".yaml")),
    # Terraform resources that provision a public endpoint directly.
    ("tf-endpoint", re.compile(
        r'resource\s+"(?:aws_api_gateway_\w+|aws_apigatewayv2_\w+|'
        r'google_cloud_run_service|azurerm_api_management_api)"'),
     "a Terraform endpoint resource",
     (".tf",)),
    # A new OpenAPI/Swagger path entry (YAML-shaped; also matches the JSON
    # authoring style most editors preserve on save). Gated to spec-shaped
    # files on purpose: this pattern cannot tell an OpenAPI path from an
    # ordinary filesystem-looking YAML/JSON key ("/usr/local/bin:") without
    # seeing the enclosing "paths:" section, which a --unified=0 diff (no
    # context lines) never shows -- extension-gating is the cheap partial
    # fix; it does not claim to solve the ambiguity inside a spec file.
    ("openapi-path", re.compile(r'^\s*"?/[\w{}\-/]+"?\s*:\s*$'),
     "a new OpenAPI/Swagger path entry",
     (".yml", ".yaml", ".json")),
)


def infer_endpoints(root):
    """Endpoint CANDIDATES found in `git diff HEAD` (staged and unstaged), one
    per added line matching an `_INFERENCE_SIGNALS` pattern whose file
    extension the signal applies to. Never a declared record, and never
    persisted -- see read_endpoints, the only caller, which computes these
    fresh on every read (BLOCK 1: candidates are computed, not stored) and
    routes anything worth keeping through declare_endpoint instead, never
    through this function. [] with no git, no HEAD, an empty diff, or a diff
    confined to crew's own source (see _excluded_from_inference).

    Three restrictions keep this from crying wolf on its own source and on
    ordinary prose (finding 9): added lines only (a diff hunk header or a
    context line is never itself new code); comment/doc-string lines are
    skipped outright (_COMMENT_PREFIXES); and a match sitting inside a quote
    already opened earlier on the line is skipped too
    (_inside_quoted_string) -- a config value or example string that merely
    CONTAINS the shape of a route registration is not one.
    """
    diff = git_out(root, "diff", "HEAD", "--unified=0")
    if not diff:
        return []
    hits = []
    current_file, current_ext, current_excluded = None, "", False
    next_line = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            current_file = path[2:] if path.startswith("b/") else path
            current_ext = os.path.splitext(current_file)[1].lower()
            current_excluded = _excluded_from_inference(current_file)
            continue
        if raw.startswith("@@"):
            found = re.search(r"\+(\d+)", raw)
            next_line = int(found.group(1)) if found else 0
            continue
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        if current_excluded:
            next_line += 1
            continue
        added = raw[1:]
        stripped = added.strip()
        if stripped.startswith(_COMMENT_PREFIXES):
            next_line += 1
            continue
        for name, pattern, label, extensions in _INFERENCE_SIGNALS:
            if extensions and current_ext not in extensions:
                continue
            match = pattern.search(added)
            if match and not _inside_quoted_string(added, match.start()):
                where = f"{current_file}:{next_line}" if current_file else "unknown"
                hits.append({"signal": name, "location": where,
                             "label": label, "evidence": stripped[:200]})
                break
        next_line += 1
    return hits


def _candidate_record(candidate):
    """The EPHEMERAL record shape for one freshly-inferred candidate,
    built fresh on every call and never written to disk (see read_endpoints,
    the only caller). The id is a deterministic hash of (signal, location)
    rather than minted from a counter: there is no shared sequence to
    collide on when nothing is persisted, and hashing the pair is what lets
    the SAME diff line resolve to the SAME artifact path across repeated
    reads of the SAME diff state, even though the candidate that named the
    path was never saved anywhere.

    This does NOT survive the file changing shape. `location` carries a
    line number, and one line inserted above the candidate shifts it --
    a different location hashes to a different id, so a scan already
    written for the old id is silently orphaned (finding 6: reproduced as
    `cand-e79629d0` becoming `cand-ad136138` after prepending one `import
    os` line). Nothing here defends against that; the id is stable only
    between reads of an unchanged diff, not across an edit that moves the
    line.
    """
    digest = hashlib.sha1(
        f"{candidate.get('signal')}:{candidate.get('location')}".encode("utf-8")
    ).hexdigest()[:8]
    return {
        "id": f"cand-{digest}",
        "endpoint": candidate.get("label") or "unidentified endpoint candidate",
        "source": "inferred", "status": "candidate",
        "location": candidate.get("location"),
    }


def gizmoduck_installed(root=None):
    """Whether the gizmoduck PLUGIN is enabled for Claude Code on this
    machine -- never whether this repository merely contains its source.

    This very repo ships `plugin/gizmoduck/` (crew develops gizmoduck); that
    directory being present is not installation, and must not satisfy this
    check, or every session opened in useful-claude-add-ons would misreport
    gizmoduck as installed regardless of whether anyone actually enabled it.
    What decides installation is Claude Code's own settings, where an
    enabled plugin appears as `enabledPlugins["<name>@<marketplace>"]: true`.
    Matched on the plugin-name prefix before the `@`, because the
    marketplace name varies (this repo's own, a fork, a different one
    entirely) and is not part of what "installed" means here.

    Checked in this exact precedence order, each scope's own
    `settings.local.json` ahead of its `settings.json` (an untracked local
    override is meant to win over a shared, committed one), and every
    project scope ahead of every global scope (what THIS repo asked for must
    not be overridden by a machine-wide default):

      1. project `.claude/settings.local.json`
      2. project `.claude/settings.json`
      3. user-global `~/.claude/settings.local.json`
      4. user-global `~/.claude/settings.json`

    The first scope that names `enabledPlugins["gizmoduck@..."]` as a real
    JSON boolean decides the answer and STOPS the search there -- an
    explicit `false` at a narrower scope must mean off, not "keep looking
    until something says true". A scope is deferred to the next one (never
    treated as an implicit `false`) when: the file is absent (ordinary --
    most scopes will not exist); its JSON does not parse (malformed carries
    no signal either way -- failing THIS scope closed instead would mean a
    syntax error in one settings file silently reads as "gizmoduck is off"
    even when a wider scope has an explicit `true`, a worse and much harder
    to notice failure than reading one more file); `enabledPlugins` has no
    entry for `gizmoduck@...` at all; or the entry's value is present but
    not a JSON boolean -- the string `"false"` is truthy in Python, so
    `if value` would read it as "on", which is why the type is checked
    explicitly rather than the truthiness.
    """
    scopes = []
    if root:
        scopes.append(os.path.join(root, ".claude", "settings.local.json"))
        scopes.append(os.path.join(root, ".claude", "settings.json"))
    home = os.path.expanduser("~")
    scopes.append(os.path.join(home, ".claude", "settings.local.json"))
    scopes.append(os.path.join(home, ".claude", "settings.json"))

    for path in scopes:
        text = read_text(path)
        if text is None:
            continue
        try:
            parsed = json.loads(text)
        except ValueError:
            continue
        enabled = dict_or_empty(parsed).get("enabledPlugins")
        if not isinstance(enabled, dict):
            continue
        value = None
        for key, candidate_value in enabled.items():
            if isinstance(key, str) and key.split("@", 1)[0] == "gizmoduck":
                value = candidate_value
                break
        if not isinstance(value, bool):
            continue
        return value
    return False


# Directories a package scan must never descend into: generated, vendored, or
# VCS-internal trees that can legitimately contain their own
# go.mod/Cargo.toml/pyproject.toml-shaped files and would otherwise inflate
# the package count or misattribute an endpoint to a dependency's checkout.
_MONOREPO_SKIP_DIRS = frozenset({
    "node_modules", "graphify-out", "vendor", ".venv", "venv", "dist", "build",
})

_MONOREPO_MARKER_FILES = ("go.mod", "Cargo.toml", "pyproject.toml")
_PACKAGE_MARKER_FILES = _MONOREPO_MARKER_FILES + ("package.json",)


def _is_monorepo(root):
    """Whether `root` hosts more than one package, per the documented
    signals: a `pnpm-workspace.yaml`, a `lerna.json`, a `workspaces` key in
    the root `package.json`, or more than one
    go.mod/Cargo.toml/pyproject.toml below the root. Only the last needs a
    walk, so it runs last and stops at the first second hit.

    Used only to choose where a NEW record's scan lands (scan_artifact_path
    falls back to this the moment a record has no frozen `artifactPath`
    yet). A record that already landed a scan is never re-run through this
    -- see finding 6's fix in scan_artifact_path -- so a later repo-shape
    change (a second manifest appearing anywhere) cannot relocate history.
    """
    if os.path.isfile(os.path.join(root, "pnpm-workspace.yaml")):
        return True
    if os.path.isfile(os.path.join(root, "lerna.json")):
        return True
    pkg_text = read_text(os.path.join(root, "package.json"))
    if pkg_text:
        try:
            if "workspaces" in json.loads(pkg_text):
                return True
        except ValueError:
            pass

    hits = 0
    # `_` for the directory path: os.walk yields it, but only `dirnames`
    # (pruned in place, below) and `filenames` are read here.
    for _, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _MONOREPO_SKIP_DIRS
                        and not d.startswith(".")]
        if any(marker in filenames for marker in _MONOREPO_MARKER_FILES):
            hits += 1
            if hits > 1:
                return True
    return False


def _owning_package_dir(root, location):
    """The nearest ancestor directory containing a package marker
    (`package.json`, `go.mod`, `Cargo.toml`, `pyproject.toml`), relative to
    `root`, walking up from the directory named in `location`'s path part.

    `location` is a ledger record's repo-relative `path:line` (never an
    absolute path or a bare URL) or a ticket/dispatch reference with no path
    at all -- the latter has no directory separator, so it is recognised and
    rejected before ever reaching the filesystem. Returns "" -- attribute to
    the repo root -- when `location` has no path part, resolves outside
    `root`, or no ancestor carries a marker.
    """
    if not isinstance(location, str):
        return ""
    path_part = location.rsplit(":", 1)[0] if location.count(":") else location
    if "/" not in path_part and "\\" not in path_part:
        return ""  # a bare ticket/dispatch reference, not a path
    base = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(base, os.path.dirname(path_part)))
    try:
        inside = os.path.commonpath([base, candidate]) == base
    except ValueError:
        inside = False
    if not inside:
        return ""

    while True:
        if any(os.path.isfile(os.path.join(candidate, marker))
               for marker in _PACKAGE_MARKER_FILES):
            rel = os.path.relpath(candidate, base)
            # Native separator, deliberately: the caller feeds this straight
            # back into os.path.join to build the artifact path, and
            # normalising to "/" here would leave THAT join producing mixed
            # separators on Windows instead of a consistent native path.
            return "" if rel == "." else rel
        if candidate == base:
            return ""
        parent = os.path.dirname(candidate)
        if parent == candidate:
            return ""
        candidate = parent


# The one place the scan-artifact filename is decided, so read_endpoints and
# any future writer (gizmoduck itself, or a test) agree on where a scan for a
# given record must land.
_SCAN_ARTIFACT_TEMPLATE = "{id}.md"


def scan_artifact_path(root, record):
    """Repo-relative path where the scan artifact for `record` must live, or
    None when `record["id"]` is not safe to use in a path at all (see
    _valid_endpoint_id) -- callers must treat None as "cannot be checked",
    never as "scanned", and read_endpoints reports it as unscanned so an
    unsafe id fails safe instead of silently discharging the obligation.

    A record that already has a scan carries its OWN frozen `artifactPath`
    (written once, by record_scan_artifact, right after the scan that
    produced it landed) and that value is authoritative -- returned as-is
    (after a containment check; see _relative_safe) rather than recomputed.
    Only a record with no frozen path yet -- a brand new one -- falls
    through to the classifier below, which is what "the computed path is
    the default for NEW records only" (finding 6) means: a repo-shape
    change after the fact (`_is_monorepo` flipping) cannot relocate or
    orphan a scan that already happened, only decide where the NEXT one goes.

    The classifier itself: single repo -> `docs/security-scans/<id>.md` at
    the repo root. Monorepo -> `<package-dir>/docs/security-scans/<id>.md`,
    the package attributed from the record's `location`; falls back to the
    repo-root path when the endpoint cannot be attributed to one package --
    an unattributable record is not exempt from scanning, it just lands
    where a single repo would have put it anyway.

    A frozen `artifactPath` is normalised to POSIX (forward-slash)
    separators before use, regardless of what is actually stored (finding
    12). `.crew/endpoints.json` is a committed file read on whatever OS
    cloned it; `record_scan_artifact` stores the POSIX form for exactly
    this reason, but a ledger entry frozen before that fix -- or hand-edited
    with native separators -- still has to resolve correctly here. A literal
    `docs\\security-scans\\ep-0001.md` is a valid path component on Windows
    but not a separator at all on POSIX, so without this the record reads as
    permanently unscanned on any non-Windows clone.
    """
    record_id = record.get("id")
    if not _valid_endpoint_id(record_id):
        return None
    filename = _SCAN_ARTIFACT_TEMPLATE.format(id=record_id)
    if _is_monorepo(root):
        package_dir = _owning_package_dir(root, record.get("location"))
        default = (os.path.join(package_dir, "docs", "security-scans", filename)
                   if package_dir else os.path.join("docs", "security-scans", filename))
    else:
        default = os.path.join("docs", "security-scans", filename)

    frozen = record.get("artifactPath")
    if isinstance(frozen, str):
        frozen = frozen.replace("\\", "/")
    if frozen is not None:
        return _relative_safe(root, frozen, default)
    return default


def record_scan_artifact(root, endpoint_id):
    """Freezes the CURRENTLY computed scan-artifact path onto the ledger
    record `endpoint_id`, persisting it as `artifactPath` -- the one write
    this module needs outside declare_endpoint, and the fix for finding 6
    (a repo-shape flip must never orphan a scan that already landed).

    Called once, by whatever wrote the scan artifact -- gizmoduck's report
    command, per the `--out` convention documented in
    `plugin/gizmoduck/commands/report.md` and `scan.md` -- right after that
    write succeeds. Never called from a read path: collect() must stay a
    pure read (BLOCK 1), so nothing in this module calls this on its own.

    Returns the frozen path, or None when there is no ledger record with
    this id (a typo'd id must not silently mint one) or the id is not safe
    to use in a path at all. Idempotent: calling it again for the same scan,
    with the path unchanged, is a no-op rather than a redundant write.

    Stored as POSIX (forward-slash) separators regardless of the OS this
    runs on (finding 12) -- see scan_artifact_path's docstring for why a
    native-separator freeze breaks on a clone using a different OS. Holds
    the same lock `declare_endpoint` does, for the same reason: this is a
    read-modify-write over the same shared, hand-editable file.
    """
    if not _valid_endpoint_id(endpoint_id):
        return None
    lock = _acquire_endpoints_lock(root)
    try:
        doc = _load_endpoint_doc(root)
        for record in doc["records"]:
            if record.get("id") == endpoint_id:
                path = scan_artifact_path(root, record)
                if path is None:
                    return None
                path = path.replace("\\", "/")
                if record.get("artifactPath") == path:
                    return path
                record["artifactPath"] = path
                _write_endpoints(root, doc)
                return path
        return None
    finally:
        _release_endpoints_lock(lock)


# A URL is the strongest possible needle: if the endpoint names one, the
# artifact has to mention it verbatim to count as evidence of scanning THAT
# target. A bare absolute path ("/health") or a bare hostname is the fallback
# for an endpoint named without a scheme -- see _endpoint_needle for what
# counts as "specific enough" and why a lone "/" does not.
_URL_RE = re.compile(r"https?://[^\s'\")]+")

# A conservative "this looks like a hostname" test: at least one dot, no
# whitespace, nothing that reads as prose. Deliberately narrow -- a false
# negative here just means the record falls through to "no needle, fail
# closed" (BLOCK 3), which is the safe direction; a false positive would let
# a sentence that happens to contain a dot (an abbreviation, a version
# number) be treated as a hostname, which is the unsafe one.
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
                          r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+"
                          r"(?:/\S*)?$")

# BLOCK 4: the fixed marker gizmoduck's own report command always emits --
# `cmd_report` in `plugin/gizmoduck/scripts/gizmoduck.py` writes this exact
# line before branching on severity, so it is present in EVERY report that
# tool produces, empty findings or not. Documented as a contract in
# `plugin/gizmoduck/commands/report.md`/`scan.md` rather than merely inferred
# from the script, so a future change to the report format has to update
# both sides deliberately instead of silently breaking this check. Its
# purpose is narrow: prove the file was produced by an actual scan-report
# run, not typed by hand -- `echo "TODO: scan <url> later" > ...` mentions
# the URL but could never contain this line.
_SCAN_MARKER_RE = re.compile(r"\*\*Total finding instances:\*\*\s*\d+")


def _endpoint_needle(endpoint):
    """A short, specific fragment to look for in a scan artifact's text, or
    None when `endpoint` carries nothing specific enough to search for.

    Covers every shape the docs invite an endpoint to be declared as
    (`commands/work.md`: "<url or host>"; `report.md`: "a host or URL") --
    BLOCK 3 found this covered only a URL or an absolute path, so a bare
    hostname (and the free-text description the docs used to also invite)
    fell through to None and the caller treated that as "nothing to check",
    discharging the obligation on any non-empty file. A bare "/" is excluded
    on purpose even though it starts with "/": it would match almost any
    markdown file that contains a slash anywhere, which is not a needle at
    all (finding 4's related bug).

    An inferred candidate's label -- prose like "a Flask/FastAPI route
    decorator" -- correctly still returns None here: it is not a hostname,
    a URL, or a path, so there is genuinely nothing specific to search for.
    See _artifact_confirms_scan for how that case is now handled without
    falling back to "anything non-empty passes" (BLOCK 4's marker check).
    """
    if not isinstance(endpoint, str):
        return None
    stripped = endpoint.strip()
    if not stripped:
        return None
    match = _URL_RE.search(stripped)
    if match:
        return match.group(0)
    if stripped == "/":
        return None
    if stripped.startswith("/") or _HOSTNAME_RE.match(stripped):
        return stripped
    return None


def _artifact_confirms_scan(root, artifact, record):
    """Whether the file at `artifact` is real evidence that record was
    actually scanned, not merely a file sitting at the computed name.

    Three checks, in order, all necessary:
    - Non-empty. `touch docs/security-scans/ep-0001.md` (0 bytes) must not
      permanently discharge the obligation for free -- `os.path.isfile`
      alone cannot tell a completed scan from a placeholder (finding 2).
    - Carries the scan marker (`_SCAN_MARKER_RE`, BLOCK 4). "Content
      references the endpoint" used to be a bare substring match, which a
      44-byte to-do note satisfies trivially (`echo "TODO: scan
      https://api.example.com/pay later" > ...`) without a scan ever having
      run. The marker is what gizmoduck's own report command always writes;
      requiring it is what makes this check answer the question its name
      claims to answer.
    - When the record names something specific enough to search for (see
      _endpoint_needle), the file's text must ALSO mention it,
      case-insensitively -- a real report for a DIFFERENT endpoint that
      happens to land at this path (copy-pasted, or a colliding id) must not
      confirm this one. When there is nothing specific to search for
      (BLOCK 3: a DECLARED record whose endpoint text yields no needle,
      e.g. free prose) this now fails CLOSED rather than passing on the
      marker alone -- a declared record is supposed to name a real target,
      and one that cannot be checked must not read as scanned. The one
      exception is an INFERRED candidate, whose generic label is expected to
      yield no needle (see _endpoint_needle's docstring); the marker plus
      non-empty is genuinely all that can be asked of it, which is the
      "common case for an unresearched inferred candidate" the previous
      version of this docstring described.
    """
    text = read_text(os.path.join(root, artifact))
    if not text or not text.strip():
        return False
    if not _SCAN_MARKER_RE.search(text):
        return False
    needle = _endpoint_needle(record.get("endpoint"))
    if needle is None:
        return record.get("source") != "declared"
    return needle.lower() in text.lower()


def _unscanned_hit(root, record):
    """One `unscanned` entry for `record`, or None once it is confirmed
    scanned (see _artifact_confirms_scan). `status` travels on the hit
    alongside `source`, and is the field pm_brief's declared/candidate split
    must key on -- `status` is what the design makes authoritative, and a
    record whose `source` and `status` disagree (a bug elsewhere writing
    `source="declared", status="candidate"`) must still read as a candidate,
    never as a confirmed fact (finding 10).

    `location` also travels on the hit (finding 7). `_candidate_record`
    always supplies one, and a declared record's is whatever `declare_endpoint`
    was given -- but before this, nothing downstream ever saw it: `pm.md`
    tells the PM to promote a candidate with `--location <path:line>` and
    the brief says "research each candidate first", yet neither the state
    JSON nor the rendered brief ever named a path:line to research. With
    twenty inferred candidates the brief rendered the SAME generic label
    ("a Flask/FastAPI route decorator") twenty times, indistinguishable and
    unfindable.
    """
    artifact = scan_artifact_path(root, record)
    if artifact is None:
        # An unsafe id: never build or probe a path from it, but fail SAFE
        # -- report it as unscanned rather than silently discharging an
        # obligation just because it could not be checked (finding 3).
        return {
            "id": record.get("id") or "unknown",
            "endpoint": record.get("endpoint") or "an endpoint",
            "source": record.get("source"),
            "status": record.get("status"),
            "location": record.get("location"),
            "path": None,
        }
    if _artifact_confirms_scan(root, artifact, record):
        return None
    return {
        "id": record.get("id") or "unknown",
        "endpoint": record.get("endpoint") or "an endpoint",
        "source": record.get("source"),
        "status": record.get("status"),
        "location": record.get("location"),
        "path": artifact,
    }


def read_endpoints(root, cfg):
    """Ledger records vs. their security-scan artifacts -- gated entirely on
    gizmoduck being installed. Returns immediately, doing no ledger,
    inference, or filesystem work, when it is not: see evaluate_triggers's
    endpointUnscanned, which must be strictly inert (no error, no finding) on
    a machine without the plugin. `cfg` is unused today -- threaded through
    for the same reason read_diagrams and read_knowledge take it, so a
    future config knob lands here without changing collect()'s call site.

    A pure read, deliberately (BLOCK 1): this never writes the ledger, never
    calls declare_endpoint, and never persists a candidate. Two sources feed
    `unscanned`:
    - DECLARED records loaded from `.crew/endpoints.json` (status "open" or
      "candidate" -- a record's own status, set only by declare_endpoint,
      not the source of this list).
    - INFERRED candidates computed fresh, right here, from infer_endpoints
      -- never loaded from disk and never written to it. A location already
      covered by a persisted record (declared and open, or already closed)
      is skipped so the same diff line does not surface twice under two
      different ids once a human has dealt with it.

    A record with status "closed" is done -- decommissioned, or a candidate
    already researched and dismissed -- and is never unscanned; a closed
    record's location is still excluded from fresh inference, above.

    `unfrozen` (finding 8, additive) names a DECLARED record that reads as
    scanned right now -- a real artifact sits at its freshly COMPUTED
    default path -- but was never frozen there via `record_scan_artifact`.
    The documented protocol (`plugin/gizmoduck/commands/report.md`) is two
    steps, write then freeze, and skipping the second one is otherwise
    silent: the trigger still clears today because the computed path
    happens to match, right up until a repo-shape change (`_is_monorepo`
    flipping) recomputes a DIFFERENT default and orphans the artifact with
    no record of why. This makes that gap observable before it bites,
    without writing anything -- read_endpoints stays a pure read.
    """
    del cfg
    if not gizmoduck_installed(root):
        return {"installed": False, "unscanned": []}

    declared = load_endpoints(root)
    covered_locations = {record.get("location") for record in declared}

    unscanned, unfrozen = [], []
    for record in declared:
        if record.get("status") not in ("open", "candidate"):
            continue
        hit = _unscanned_hit(root, record)
        if hit:
            unscanned.append(hit)
        elif (record.get("source") == "declared"
              and record.get("artifactPath") is None):
            unfrozen.append({
                "id": record.get("id") or "unknown",
                "endpoint": record.get("endpoint") or "an endpoint",
                "path": scan_artifact_path(root, record),
            })

    for candidate in infer_endpoints(root):
        if candidate.get("location") in covered_locations:
            continue
        hit = _unscanned_hit(root, _candidate_record(candidate))
        if hit:
            unscanned.append(hit)
    return {"installed": True, "unscanned": unscanned, "unfrozen": unfrozen}
