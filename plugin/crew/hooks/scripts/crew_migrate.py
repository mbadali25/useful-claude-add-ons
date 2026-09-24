"""One-time move of a 0.20 crew setup onto the 1.0 layout.

    python3 crew_migrate.py [--root .] [--preview]        # default; writes nothing
    python3 crew_migrate.py [--root .] --apply            # backup, then atomic writes
    python3 crew_migrate.py [--root .] --rollback <dir>   # undo one apply, byte-identical

What moves, and what does not:

| Source (0.20)                          | Target (1.0)                                  | Original      |
|----------------------------------------|-----------------------------------------------|---------------|
| `.crew/config.json` (schema <= 7)      | `.crew/crew.json` (schema 1, table below)     | kept, retireable |
| `.work/tickets/<ID>.md` (files mode)   | `.work/tickets/<ID>/ticket.md` + provenance   | kept          |
| `.work/cache/<ID>.md` (jira/sdp/obsidian) | `.work/tickets/<ID>/ticket.md` + provenance | kept          |
| `.crew/metrics.md`                     | `.crew/metrics.jsonl`, missing values UNKNOWN | kept          |
| `.crew/pm-journal.md`, `pm-standing.md` | `.crew/archive/<name>` (a copy)              | kept, retireable |
| `.crew/codemap/**`, anchors            | untouched                                     | untouched     |

The PM journal was only ever appended to through `pm_journal.py`; migrate
never appends to it, it copies the bytes into `.crew/archive/` whole.

Nothing a user owns is deleted or moved in place. Every target is new, and apply
refuses when a target already exists with different bytes, so the only thing
`--rollback` ever has to do is remove what apply created -- after checking the
bytes are still the ones apply wrote.

## crew.json schema 1 -- the whole mapping

Every top-level key of `config.json` lands somewhere. A key this table does
not name is carried whole under `unmapped.<key>` and listed in the report. A
key the 1.0 layout no longer reads is carried whole under `retired.<key>`.
Nothing is dropped, and `to_legacy()` rebuilds the original dict exactly from
crew.json alone -- that inverse is what the round-trip test asserts.

A setting 1.0 carries but no longer acts on is also said out loud: crew.json
gains a `notes` list and the report a `note` line. Today that is one case,
`pm.authority: autonomous` -> "autopilot arrives in 1.1.0".

| config.json (<= 7) | crew.json (1)            | Note |
|--------------------|--------------------------|------|
| `schema`           | `migratedFrom.schema`    | crew.json's own `schema` is 1 |
| `tier`             | `retired.tier`           | tiers go with the 54-agent roster |
| `roles`            | `retired.roles`          | also filtered into `agents` (see ROSTER) |
| `qa`               | `review`                 | provider walk and pins, unchanged |
| `dev`              | `dev`                    | |
| `worktree`         | `worktree`               | |
| `secondOpinion`    | `secondOpinion`          | |
| `tracker`          | `tracker.kind`           | |
| `jira`             | `tracker.jira`           | |
| `sdp`              | `tracker.sdp`            | |
| `obsidian`         | `tracker.obsidian`       | |
| `memory`           | `memory`                 | |
| `verifyGate`       | `gates.verify`           | |
| `context`          | `context`                | |
| `emergency`        | `emergency`              | |
| `notify`           | `notify`                 | |
| `platform`         | `platform`               | |
| `pm`               | `retired.pm`             | the PM agent and pulse are removed in 1.0 |
| `graph`            | `graph`                  | |
| `docs`             | `docs`                   | |
| `bitbucket`        | `mergeGate.bitbucket`    | |
| `github`           | `mergeGate.github`       | |
| `install`          | `install`                | |
| `guards`           | `guards`                 | |
| `production`       | `production`             | |
| `change`           | `change`                 | |

`MAPPING` below is this table as code; a test asserts the two agree.

Standard library only. Exit 0 on success (or a clean preview), 1 when the
migration cannot proceed (conflict, unreadable source, interrupted apply), 2 on
a usage error.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time

CREW_SCHEMA = 1
LEGACY_SCHEMA_MAX = 7

UNKNOWN = "UNKNOWN"

# (legacy top-level key, dotted crew.json path). Order is report order.
MAPPING = (
    ("schema", "migratedFrom.schema"),
    ("tier", "retired.tier"),
    ("roles", "retired.roles"),
    ("qa", "review"),
    ("dev", "dev"),
    ("worktree", "worktree"),
    ("secondOpinion", "secondOpinion"),
    ("tracker", "tracker.kind"),
    ("jira", "tracker.jira"),
    ("sdp", "tracker.sdp"),
    ("obsidian", "tracker.obsidian"),
    ("memory", "memory"),
    ("verifyGate", "gates.verify"),
    ("context", "context"),
    ("emergency", "emergency"),
    ("notify", "notify"),
    ("platform", "platform"),
    ("pm", "retired.pm"),
    ("graph", "graph"),
    ("docs", "docs"),
    ("bitbucket", "mergeGate.bitbucket"),
    ("github", "mergeGate.github"),
    ("install", "install"),
    ("guards", "guards"),
    ("production", "production"),
    ("change", "change"),
)

# The 1.0 roster (docs/review/04-redesign.md, "Roster: 54 agents -> 4").
ROSTER = ("explorer", "reviewer", "security", "researcher")
RENAMED = {"qa-reviewer": "reviewer"}
# `pm.authority: autonomous` moves under `retired.pm` with the rest of the PM
# block, and nothing in 1.0 dispatches on its own. Said in the report and in
# crew.json, never dropped silently.
AUTOPILOT_NOTE = ("pm.authority: autonomous - autopilot arrives in 1.1.0; until then "
                  "nothing dispatches without you (kept under retired.pm)")

# `LETTERS-digits`, the shape the rest of crew recognises as a ticket id
# (crew_state._TICKET_RE). Anchored, so it doubles as a path-safety check: an
# id that passes cannot contain a separator or `..`.
_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
_REVIEW_ROUND_RE = re.compile(r"\br(\d+)\b")
_METRIC_FIELDS_1_0 = (
    "phases", "activeTime", "tokens", "cost", "findingsConfirmed",
    "findingsRejected", "findingsDuplicate", "scopeBlocks", "injectedChars",
    "escapedDefects",
)
JOURNAL_FILES = ("pm-journal.md", "pm-standing.md")
BACKUP_DIR = os.path.join(".crew", "backups")
TMP_SUFFIX = ".crew-migrate.tmp"

# Every path apply may write, and so every path rollback may remove. A
# manifest naming anything else was not written by this tool.
_TARGET_RE = re.compile(
    r"^(?:\.crew/crew\.json|\.crew/metrics\.jsonl"
    r"|\.crew/archive/(?:pm-journal|pm-standing)\.md"
    r"|\.work/tickets/[A-Z][A-Z0-9]*-\d+/(?:ticket(?:\.[a-z-]+)?\.md|provenance\.json))$")

_MISSING = object()


class MigrateError(Exception):
    """A refusal the caller reports and exits 1 on."""


# ---------------------------------------------------------------- helpers

def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read_bytes(path):
    """File bytes, or None when absent. A symlink is refused, not followed."""
    if os.path.islink(path):
        raise MigrateError(f"{path} is a symlink; refusing to read through it")
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _is_link(path):
    """A symlink, or a Windows directory junction (which `islink` misses)."""
    isjunction = getattr(os.path, "isjunction", None)
    return os.path.islink(path) or bool(isjunction and isjunction(path))


def _within(path, real_root):
    try:
        return (os.path.commonpath([os.path.normcase(path), os.path.normcase(real_root)])
                == os.path.normcase(real_root))
    except ValueError:
        return False


def contained(root, rel):
    """Absolute path for repo-relative `rel`, or MigrateError.

    Refused: an absolute path, an empty, `.` or `..` component, any existing
    component that is a symlink or junction, and a deepest existing ancestor
    whose realpath is not inside the root's realpath.
    """
    parts = rel.replace("\\", "/").split("/")
    if os.path.isabs(rel) or any(p in ("", ".", "..") for p in parts):
        raise MigrateError(f"{rel}: not a plain path inside the repository; refused")
    path = os.path.join(root, *parts)
    probe = root
    for part in parts:
        probe = os.path.join(probe, part)
        if _is_link(probe):
            raise MigrateError(f"{_rel(root, probe)} is a symlink or junction; refusing to "
                               "write or remove through it")
        if not os.path.lexists(probe):
            break
    existing = path
    while not os.path.lexists(existing):
        existing = os.path.dirname(existing)
    if not _within(os.path.realpath(existing), os.path.realpath(root)):
        raise MigrateError(f"{rel} resolves outside {root}; refused")
    return path


def _get(tree, dotted):
    node = tree
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _put(tree, dotted, value):
    parts = dotted.split(".")
    node = tree
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _json_bytes(obj):
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def atomic_write(path, data):
    """Write `data` to `path` via a sibling temp file and `os.replace`.

    The payload is fully built before anything is opened, and the target is
    only ever replaced whole -- never truncated in place (CLAUDE.md, the
    `open(p, "w")` landmine). The temp file is created exclusively under a
    unique name, so no file already beside the target is truncated or removed.
    """
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=os.path.basename(path) + ".",
                               suffix=TMP_SUFFIX)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        _remove(tmp)
        raise


# ---------------------------------------------------------------- config

def to_crew(legacy):
    """(crew.json dict, unmapped key list) from a legacy config dict."""
    crew = {"schema": CREW_SCHEMA, "migratedFrom": {"file": ".crew/config.json"}}
    known = {old for old, _ in MAPPING}
    for old, new in MAPPING:
        if old in legacy:
            _put(crew, new, legacy[old])
    roles = legacy.get("roles")
    if isinstance(roles, list):
        agents = []
        for role in roles:
            name = RENAMED.get(role, role) if isinstance(role, str) else None
            if name in ROSTER and name not in agents:
                agents.append(name)
        crew["agents"] = agents
    else:
        crew["agents"] = list(ROSTER)
    unmapped = [key for key in legacy if key not in known]
    if unmapped:
        crew["unmapped"] = {key: legacy[key] for key in unmapped}
    notes = migration_notes(legacy)
    if notes:
        crew["notes"] = notes
    return crew, unmapped


def migration_notes(legacy):
    """Settings 1.0 carries but does not act on, said out loud. `to_legacy`
    never reads `notes`, so the round trip is unaffected."""
    pm = legacy.get("pm")
    if isinstance(pm, dict) and pm.get("authority") == "autonomous":
        return [AUTOPILOT_NOTE]
    return []


def to_legacy(crew):
    """The inverse of `to_crew`: rebuild the legacy dict from crew.json alone."""
    legacy = {}
    for old, new in MAPPING:
        value = _get(crew, new)
        if value is not _MISSING:
            legacy[old] = value
    for key, value in (crew.get("unmapped") or {}).items():
        legacy[key] = value
    return legacy


def _load_legacy(root):
    path = os.path.join(root, ".crew", "config.json")
    data = _read_bytes(path)
    if data is None:
        return None, None
    try:
        cfg = json.loads(data.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise MigrateError(f".crew/config.json is not valid JSON: {exc}") from exc
    if not isinstance(cfg, dict):
        raise MigrateError(".crew/config.json is not a JSON object")
    schema = cfg.get("schema")
    if isinstance(schema, bool) or not isinstance(schema, int):
        raise MigrateError(
            f".crew/config.json schema is {schema!r}, not an integer - cannot "
            "tell which layout it is, so nothing is migrated")
    if schema > LEGACY_SCHEMA_MAX:
        raise MigrateError(
            f".crew/config.json schema {schema} is newer than {LEGACY_SCHEMA_MAX}; "
            "this migrate does not know it and refuses to guess")
    return cfg, data


# ---------------------------------------------------------------- tickets

def _index_lines(root):
    data = _read_bytes(os.path.join(root, ".work", "INDEX.md"))
    lines = {}
    for line in (data or b"").decode("utf-8", "replace").splitlines():
        found = re.search(r"([A-Z][A-Z0-9]*-\d+)", line)
        if found and found.group(1) not in lines:
            lines[found.group(1)] = line.strip()
    return lines


def _cache_source(ticket_id, tracker):
    if ticket_id.startswith("SDP-"):
        return "sdp"
    if re.match(r"^T-\d+$", ticket_id):
        return "obsidian" if tracker == "obsidian" else "files-cache"
    return "jira"


def _ticket_candidates(root, tracker):
    """[(id, source, abs path)] from the files tracker and the tracker caches,
    plus [(rel path, reason)] for every file skipped, so nothing is silent."""
    found, skipped = [], []
    for sub, kind in ((os.path.join(".work", "tickets"), "files"),
                      (os.path.join(".work", "cache"), "cache")):
        folder = os.path.join(root, sub)
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            path = os.path.join(folder, name)
            if os.path.isdir(path) and not os.path.islink(path):
                continue
            if not name.endswith(".md"):
                skipped.append((_rel(root, path), "not a .md ticket file"))
                continue
            ticket_id = name[:-3]
            if not _ID_RE.match(ticket_id):
                skipped.append((_rel(root, path), "name is not a LETTERS-digits ticket id"))
                continue
            source = "files" if kind == "files" else _cache_source(ticket_id, tracker)
            found.append((ticket_id, source, path))
    return found, skipped


# ---------------------------------------------------------------- metrics

def _metric_value(cell):
    if cell is None or not cell.strip():
        return UNKNOWN
    found = re.match(r"^\s*(\d+)\b", cell)
    return int(found.group(1)) if found else UNKNOWN


def metrics_rows(text):
    """(rows, skipped): one dict per table row; header/separator/prose skipped
    and counted, never parsed into a row of guesses."""
    rows, skipped = [], 0
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        if "|" not in stripped or re.fullmatch(r"[|:\-\s]+", stripped):
            skipped += 1
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        lowered = [c.lower() for c in cells]
        if "date" in lowered[:1] and any("ticket" in c for c in lowered):
            skipped += 1
            continue

        def cell(i, cells=cells):
            return cells[i] if i < len(cells) and cells[i] else None
        date = cell(0)
        ticket = cell(1)
        reviewer = cell(2)
        found = re.search(r"([A-Z][A-Z0-9]*-\d+)", ticket or "")
        rnd = _REVIEW_ROUND_RE.search(reviewer or "")
        row = {
            "date": date if date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) else UNKNOWN,
            "ticket": ticket or UNKNOWN,
            "ticketId": found.group(1) if found else UNKNOWN,
            "reviewer": reviewer or UNKNOWN,
            "reviewRound": int(rnd.group(1)) if rnd else UNKNOWN,
            "block": _metric_value(cell(3)),
            "fix": _metric_value(cell(4)),
        }
        for name in _METRIC_FIELDS_1_0:
            row[name] = UNKNOWN
        row["source"] = {"file": ".crew/metrics.md", "line": number, "raw": line}
        rows.append(row)
    return rows, skipped


# ---------------------------------------------------------------- the plan

def build_plan(root):
    """Read-only. Returns a plan dict; nothing on disk changes."""
    root = os.path.abspath(root)
    plan = {"root": root, "writes": [], "conflicts": [], "notes": [],
            "retireable": [], "unmapped": [], "skipped": [], "untouched": []}

    def want(rel, data, why):
        try:
            path = contained(root, rel.replace(os.sep, "/"))
        except MigrateError as exc:
            plan["conflicts"].append(str(exc))
            return
        if os.path.lexists(path + TMP_SUFFIX):
            plan["conflicts"].append(f"{_rel(root, path + TMP_SUFFIX)}: exists - migrate "
                                     "stages through that name and will not overwrite it")
            return
        current = _read_bytes(path)
        if current is None:
            plan["writes"].append({"path": rel.replace(os.sep, "/"), "data": data, "why": why,
                                   "pre_sha256": None})
        elif current == data:
            plan["notes"].append(f"{rel.replace(os.sep, '/')}: already migrated (identical)")
        else:
            plan["conflicts"].append(
                f"{rel.replace(os.sep, '/')}: exists with different content - not overwritten")

    cfg, _raw = _load_legacy(root)
    tracker = "files"
    if cfg is None:
        if _read_bytes(os.path.join(root, ".crew", "crew.json")) is None:
            plan["notes"].append(".crew/config.json absent - no config to migrate")
    else:
        crew, unmapped = to_crew(cfg)
        if to_legacy(crew) != cfg:
            raise MigrateError("internal: config mapping does not round-trip; refusing")
        plan["unmapped"] = unmapped
        plan["notes"].extend(crew.get("notes", []))
        tracker = cfg.get("tracker") if isinstance(cfg.get("tracker"), str) else "files"
        want(os.path.join(".crew", "crew.json"), _json_bytes(crew),
             f"config schema {cfg['schema']} -> crew.json schema {CREW_SCHEMA}")
        plan["retireable"].append(".crew/config.json")

    index = _index_lines(root)
    by_id = {}
    candidates, skipped = _ticket_candidates(root, tracker)
    plan["skipped"].extend(skipped)
    for ticket_id, source, path in candidates:
        by_id.setdefault(ticket_id, []).append((source, path))
    for ticket_id, sources in sorted(by_id.items()):
        records = []
        bodies = {}
        for source, path in sources:
            body = _read_bytes(path)
            records.append({"source": source, "originalId": ticket_id,
                            "originalPath": _rel(root, path), "sha256": _sha(body)})
            bodies.setdefault(_sha(body), (source, body))
        primary_source, primary = bodies[records[0]["sha256"]]
        provenance = {"id": ticket_id, "source": primary_source,
                      "tracker": tracker, "sources": records,
                      "indexLine": index.get(ticket_id, UNKNOWN)}
        base = os.path.join(".work", "tickets", ticket_id)
        want(os.path.join(base, "ticket.md"), primary, f"ticket from {primary_source}")
        for digest, (source, body) in bodies.items():
            if digest != records[0]["sha256"]:
                want(os.path.join(base, f"ticket.{source}.md"), body,
                     f"differing copy from {source}, kept beside ticket.md")
                plan["notes"].append(f"{ticket_id}: {source} copy differs from "
                                     f"{primary_source}; both kept")
        want(os.path.join(base, "provenance.json"), _json_bytes(provenance), "provenance")

    metrics = _read_bytes(os.path.join(root, ".crew", "metrics.md"))
    if metrics is not None:
        rows, skipped_lines = metrics_rows(metrics.decode("utf-8-sig", "replace"))
        payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        want(os.path.join(".crew", "metrics.jsonl"), payload.encode("utf-8"),
             f"{len(rows)} metric rows ({skipped_lines} header/prose lines skipped)")

    for name in JOURNAL_FILES:
        data = _read_bytes(os.path.join(root, ".crew", name))
        if data is not None:
            want(os.path.join(".crew", "archive", name), data, "PM journal archived (copy)")
            plan["retireable"].append(f".crew/{name}")

    codemap = os.path.join(root, ".crew", "codemap")
    if os.path.isdir(codemap):
        count = sum(len(files) for _, _, files in os.walk(codemap))
        plan["untouched"].append(f".crew/codemap/ ({count} files, anchors unchanged)")
    interrupted = find_interrupted(root)
    if interrupted:
        plan["conflicts"].append(
            f"interrupted apply at {interrupted} - run --rollback {interrupted} first")
    return plan


def render_plan(plan, mode):
    out = [f"crew migrate {mode}: {plan['root']}"]
    for item in plan["writes"]:
        out.append(f"  write  {item['path']}  ({item['why']})")
    for note in plan["notes"]:
        out.append(f"  note   {note}")
    for key in plan["unmapped"]:
        out.append(f"  unmapped  config key '{key}' carried under crew.json unmapped.{key}")
    for rel, why in plan["skipped"]:
        out.append(f"  skip   {rel}: {why}")
    for rel in plan["untouched"]:
        out.append(f"  keep   {rel}")
    for rel in plan["retireable"]:
        out.append(f"  retireable  {rel} (left in place; remove by hand once 1.0 is settled)")
    for conflict in plan["conflicts"]:
        out.append(f"  CONFLICT  {conflict}")
    out.append(f"{len(plan['writes'])} write(s), {len(plan['conflicts'])} conflict(s)")
    return "\n".join(out)


# ---------------------------------------------------------------- apply

def _manifest_path(backup):
    return os.path.join(backup, "manifest.json")


def find_interrupted(root):
    """Relative path of a backup whose apply never finished, else None."""
    folder = os.path.join(root, BACKUP_DIR)
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return None
    for name in names:
        data = _read_bytes(_manifest_path(os.path.join(folder, name)))
        if data is None:
            continue
        try:
            state = json.loads(data).get("state")
        except (ValueError, AttributeError):
            return _rel(root, os.path.join(folder, name))
        if state not in ("applied", "rolled-back"):
            return _rel(root, os.path.join(folder, name))
    return None


def _new_backup_dir(root):
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    base = os.path.join(root, BACKUP_DIR, f"migrate-{stamp}")
    path, n = base, 1
    while os.path.exists(path):
        n += 1
        path = f"{base}-{n}"
    return path


def _missing_dirs(root, rels):
    """Directories apply will create, deepest first, so rollback can remove them."""
    made = set()
    for rel in rels:
        parent = os.path.dirname(os.path.join(root, rel))
        while parent and parent != root and not os.path.isdir(parent):
            made.add(parent)
            parent = os.path.dirname(parent)
    return sorted((_rel(root, p) for p in made), key=lambda p: -p.count("/"))


def apply_plan(plan):
    """Back up, then make every write land or none of them.

    Order: (1) the backup directory and a `prepared` manifest naming every
    target, its absence, and the sha256 about to be written; (2) every payload
    staged as a sibling temp file; (3) manifest -> `committing`; (4) one
    `os.replace` per target; (5) manifest -> `applied`. An exception in (2)-(4)
    undoes whatever landed and removes the temps before re-raising, so the tree
    is the old one. A hard kill in (4) leaves the manifest at `committing`,
    which every later run reports, and `--rollback` finishes the undo.

    Every target is resolved inside the repository before it is touched, its
    temp is created with O_EXCL (an existing file of that name is an error,
    never truncated), and immediately before each replace the target is
    re-read and compared with the pre-state the plan recorded: a file that
    appeared since the plan was built aborts the apply and undoes it.
    """
    if plan["conflicts"]:
        raise MigrateError("refusing to apply with conflicts:\n  " + "\n  ".join(plan["conflicts"]))
    root = plan["root"]
    if not plan["writes"]:
        return None
    backup = _new_backup_dir(root)
    contained(root, _rel(root, backup))
    os.makedirs(backup)
    sources = [".crew/config.json", ".crew/metrics.md"] + [f".crew/{n}" for n in JOURNAL_FILES]
    for rel in sources:
        data = _read_bytes(os.path.join(root, rel))
        if data is not None:
            atomic_write(os.path.join(backup, "sources", rel), data)
    rels = [w["path"] for w in plan["writes"]]
    manifest = {
        "tool": "crew_migrate", "crewSchema": CREW_SCHEMA, "state": "prepared",
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "createdDirs": _missing_dirs(root, rels),
        "targets": [{"path": w["path"], "existed": False, "sha256": _sha(w["data"])}
                    for w in plan["writes"]],
    }
    atomic_write(_manifest_path(backup), _json_bytes(manifest))

    staged, landed = [], []
    try:
        for item in plan["writes"]:
            os.makedirs(os.path.dirname(contained(root, item["path"])), exist_ok=True)
            path = contained(root, item["path"])
            try:
                fd = os.open(path + TMP_SUFFIX,
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0))
            except FileExistsError as exc:
                raise MigrateError(f"{item['path']}{TMP_SUFFIX} appeared since the plan was "
                                   "built; not overwritten, and this apply is undone") from exc
            staged.append((item, path))
            with os.fdopen(fd, "wb") as fh:
                fh.write(item["data"])
                fh.flush()
                os.fsync(fh.fileno())
        manifest["state"] = "committing"
        atomic_write(_manifest_path(backup), _json_bytes(manifest))
        for item, path in staged:
            _check_pre_state(root, item)
            os.replace(path + TMP_SUFFIX, path)
            landed.append(path)
        manifest["state"] = "applied"
        atomic_write(_manifest_path(backup), _json_bytes(manifest))
    except BaseException:
        for path in landed:
            _remove(path)
        for _, path in staged:
            _remove(path + TMP_SUFFIX)
        _prune_dirs(root, manifest["createdDirs"])
        manifest["state"] = "rolled-back"
        manifest["note"] = "apply raised; undone in-process"
        atomic_write(_manifest_path(backup), _json_bytes(manifest))
        raise
    return backup


def _check_pre_state(root, item):
    current = _read_bytes(contained(root, item["path"]))
    now = None if current is None else _sha(current)
    if now != item.get("pre_sha256"):
        raise MigrateError(f"{item['path']} changed since the plan was built; not "
                           "overwritten, and this apply is undone")


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _prune_dirs(root, rels):
    for rel in rels:
        try:
            os.rmdir(os.path.join(root, rel))
        except OSError:
            pass


def _manifest_entries(root, manifest):
    """([(target, abs path)], [dir rel]) from a manifest, or MigrateError
    before anything is removed. A target must be a path apply writes, resolve
    inside the repository and pass through no symlink; a created directory
    must be an ancestor of one of those targets."""
    targets = manifest.get("targets")
    if not isinstance(targets, list):
        raise MigrateError("manifest has no targets list; refused")
    out = []
    for target in targets:
        rel = target.get("path") if isinstance(target, dict) else None
        if (not isinstance(rel, str) or not _TARGET_RE.match(rel)
                or not isinstance(target.get("sha256"), str)):
            raise MigrateError(f"manifest names {rel!r}, which migrate never writes; "
                               "refusing the whole rollback")
        out.append((target, contained(root, rel)))
    dirs = manifest.get("createdDirs", [])
    rels = [t["path"] for t, _ in out]
    for rel in dirs if isinstance(dirs, list) else [None]:
        if not isinstance(rel, str) or not any(r.startswith(rel + "/") for r in rels):
            raise MigrateError(f"manifest createdDirs names {rel!r}, which no target is in; "
                               "refusing the whole rollback")
        contained(root, rel)
    return out, dirs


def rollback(root, backup):
    """Undo one apply. Refuses, changing nothing, if any file apply wrote has
    been edited since -- removing a file someone changed is data loss."""
    root = os.path.abspath(root)
    backup = backup if os.path.isabs(backup) else os.path.join(root, backup)
    backups = os.path.realpath(os.path.join(root, BACKUP_DIR))
    real_backup = os.path.realpath(backup)
    if real_backup == backups or not _within(real_backup, backups):
        raise MigrateError(f"{backup} is not a backup under {BACKUP_DIR}; refused")
    contained(root, _rel(root, backup))
    data = _read_bytes(_manifest_path(backup))
    if data is None:
        raise MigrateError(f"no manifest.json in {backup}")
    try:
        manifest = json.loads(data)
    except ValueError as exc:
        raise MigrateError(f"{_manifest_path(backup)} is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise MigrateError(f"{_manifest_path(backup)} is not a manifest")
    if manifest.get("state") == "rolled-back":
        return []
    targets, dirs = _manifest_entries(root, manifest)
    edited = []
    for target, path in targets:
        current = _read_bytes(path)
        if current is not None and _sha(current) != target["sha256"]:
            edited.append(target["path"])
    if edited:
        raise MigrateError("edited since apply, not removed; resolve by hand:\n  "
                           + "\n  ".join(edited))
    removed = []
    for target, path in targets:
        staged = _read_bytes(path + TMP_SUFFIX)
        if staged is not None and _sha(staged) == target["sha256"]:
            os.remove(path + TMP_SUFFIX)
        if os.path.exists(path):
            os.remove(path)
            removed.append(target["path"])
    _prune_dirs(root, dirs)
    manifest["state"] = "rolled-back"
    atomic_write(_manifest_path(backup), _json_bytes(manifest))
    return removed


# ---------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="show the plan; write nothing (default)")
    mode.add_argument("--apply", action="store_true", help="back up, then write atomically")
    mode.add_argument("--rollback", metavar="BACKUP_DIR", help="undo one apply")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    try:
        if args.rollback:
            removed = rollback(root, args.rollback)
            print(f"crew migrate rollback: removed {len(removed)} file(s) apply created")
            for rel in removed:
                print(f"  removed  {rel}")
            return 0
        plan = build_plan(root)
        if not args.apply:
            print(render_plan(plan, "preview (nothing written)"))
            return 1 if plan["conflicts"] else 0
        print(render_plan(plan, "apply"))
        backup = apply_plan(plan)
        if backup is None:
            print("nothing to write")
        else:
            print(f"backup: {_rel(root, backup)}  (undo: --rollback {_rel(root, backup)})")
        return 0
    except MigrateError as exc:
        print(f"crew migrate: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
