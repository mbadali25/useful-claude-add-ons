"""Build-time development standards: the effective set, the required
self-check, the review gate, the reviewer's checklist, the findings-to-standards
proposals and the before/after metric (T-0085).

SETS. A set file is Markdown with a front matter of `key: value` lines:

    ---
    set: GEN
    applies-to: ["**"]
    ---
    ## GEN-01 Unknown stays unknown
    **Rule.** ...
    **Self-check.** ...

`set` is 2-6 capital letters and every `## <ID> <name>` heading's prefix must
equal it. `applies-to` is a JSON list of Touch-style globs, matched with
`crew_ticket.glob_match` against the change's files, case-folded on every
host; `"**"` applies always.
A field starts on a line that begins with its bold label (`FIELDS`) and runs to
the next label or heading. Plugin sets live in `skills/crew-standards/
references/*.md` (generic.md is set GEN; T-0086's per-language sets are
further files there) and need every field in `PLUGIN_FIELDS`. The repository
overlay `.crew/standards.md` is set REPO, needs `OVERLAY_FIELDS`, and may
carry `## Supplements <ID>` sections that add repository-specific text to a
plugin standard. An overlay adds; it never removes or reuses a plugin id.

UNKNOWN IS NOT ABSENT (GEN-01). Only `FileNotFoundError` on the overlay reads
as "absent" (generic only, and the summary line says so). Any other read error,
a decode error or a malformed file is "unknown" with a problem, and every
caller that gates on the set refuses on a problem.

THE SELF-CHECK. `.work/tickets/<id>/selfcheck.md` holds one table row per
effective standard: `addressed` with evidence, or `n/a` with a reason.
`stamp` refuses an incomplete record (exit 1, each problem named) and on a
complete one writes `<!-- stamp: bundle=<sha256> standards=<sha256>
base=<sha> -->` under the header. `bundle` is `review_patch.compute`'s
`bundle_sha256` for the ticket's recorded scope base -- the same function on
the same base `/crew:review` bundles with (GEN-07) -- so it covers committed,
staged, unstaged and untracked content, and any later edit stales it.

THE GATE. `review_run.py` calls `review_gate` before `review_ledger.reserve`:
a missing, unreadable, incomplete, unstamped or stale self-check refuses the
round (exit 2, nothing spent). It applies to a ticket that has an approval
receipt -- the precondition of `/crew:implement` and `/crew:fix`, the two
commands that run the self-check; a ticket with none never went through
either, and the gate says so rather than passing silently. "None" is proven
(FileNotFoundError), never inferred from a lookup that failed. On a pass it
prints the `std:<8 hex>` token the metrics row carries.

THE CHECKLIST. `checklist_block` lists the effective set's rules and
self-check questions for the shared review prompt. It never reads
`selfcheck.md`: the author's answers are withheld so the reviewer judges
applicability independently.

EXPORT (L-0718). A repo opts in with `export: ["review", "agents", "bugbot"]` (any
non-empty subset) in the overlay's front matter. `export --write` then renders every
standard of every set with its `applies-to` as `docs/review-rules/<SET>.md` (one file per
set: Bugbot truncates a rule at 30,000 characters), `REVIEW.md` and `.cursor/BUGBOT.md`
(the always-on sets in full, the stack sets as ids, names and a link) and a marked
`## Code Review Rules` block in a hand-written `AGENTS.md` (never one carrying
`crew:generated`). Rule, Self-check and Supplements only, never Why or Earned by. Every
output carries the `effective_set` digest and the crew version; `--check` compares a fresh
render byte for byte (not a commit sha), reports orphans, and writes nothing. A file over
`EXPORT_MAX_CHARS` is refused, never truncated; `--dry-run` reports sizes.

CLI: sets | init | stamp  --root R --ticket T
     proposals --root R --ticket T --scratch S --round N
     metric --root R [--record]
     export --root R (--write | --check | --dry-run)
Exit codes: 0 ok; 1 refused (each problem named); 2 usage.
"""
import argparse
import contextlib
import datetime
import hashlib
import json
import os
import re
import stat
import statistics
import sys
import tempfile
import time

import crew_common
import crew_ticket

OVERLAY_REL = ".crew/standards.md"
OVERLAY_SET = "REPO"
SELFCHECK_NAME = "selfcheck.md"
FIELDS = ("Rule", "Why", "Applies when", "Self-check", "Earned by", "Change sets", "Source")
PLUGIN_FIELDS = ("Rule", "Why", "Applies when", "Self-check", "Earned by", "Change sets")
OVERLAY_FIELDS = ("Rule", "Self-check")
FRONT_KEYS = ("set", "applies-to")
OVERLAY_KEYS = FRONT_KEYS + ("export",)
STATUSES = ("addressed", "n/a")
PLACEHOLDERS = ("", "-", "--", "?", "tbd", "todo", "n/a", "na", "none", "...")

_SET_RE = re.compile(r"^[A-Z]{2,6}$")
_ID_RE = re.compile(r"^[A-Z]{2,6}-\d{2}$")
_STANDARD_RE = re.compile(r"^## ([A-Z]{2,6}-\d{2}) (\S.*?)\s*$")
_SUPPLEMENTS_RE = re.compile(r"^## Supplements (\S+)\s*$")
_FIELD_RE = re.compile(r"^\*\*(" + "|".join(re.escape(f) for f in FIELDS) + r")\.\*\*\s?(.*)$")
_STAMP_RE = re.compile(r"^<!-- stamp: bundle=([0-9a-f]{64}) standards=([0-9a-f]{64}) "
                       r"base=([0-9a-f]{40}|[0-9a-f]{64}) -->$")
_ROW_RE = re.compile(r"^\|(.*)\|\s*$")
_STD_TOKEN_RE = re.compile(r"\bstd:([^\s,;)|]*)")
_STD_DIGEST_RE = re.compile(r"[0-9a-f]{8}")


def references_dir():
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         os.pardir, os.pardir, "skills", "crew-standards",
                                         "references"))


# ---- parsing a set file -------------------------------------------------------

def _read_bytes(path):
    """(bytes, None) or (None, "absent") or (None, <problem>)."""
    try:
        with open(path, "rb") as fh:
            return fh.read(), None
    except FileNotFoundError:
        return None, "absent"
    except OSError as exc:
        return None, f"cannot be read: {exc.__class__.__name__}: {exc.strerror or exc}"


def _front_matter(lines, label, keys=FRONT_KEYS):
    """(meta, body_start, problems). `keys` is the allowlist: the overlay alone
    may carry `export` (L-0718); an unknown key is refused everywhere else."""
    if not lines or lines[0].strip() != "---":
        return {}, 0, [f"{label}: no front matter (the first line must be ---)"]
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, 0, [f"{label}: front matter is not closed with ---"]
    meta, problems = {}, []
    for number, line in enumerate(lines[1:end], 2):
        key, sep, value = line.partition(":")
        key = key.strip()
        if not sep or key not in keys:
            problems.append(f"{label}: front matter line {number} is not one of "
                            f"{', '.join(keys)}: {line.strip()[:60]!r}")
            continue
        if key in meta:
            problems.append(f"{label}: front matter repeats {key!r}")
        meta[key] = value.strip()
    set_name = meta.get("set", "")
    if not _SET_RE.match(set_name):
        problems.append(f"{label}: set {set_name!r} is not 2-6 capital letters")
    try:
        globs = json.loads(meta.get("applies-to", ""))
    except ValueError:
        globs = None
    if not isinstance(globs, list) or not globs or not all(
            isinstance(g, str) and g for g in globs):
        problems.append(f"{label}: applies-to is not a JSON list of non-empty globs")
        globs = []
    meta["applies-to"] = globs
    return meta, end + 1, problems


def parse_set(path, label=None, required=PLUGIN_FIELDS, keys=None):
    """(set_dict, problems, raw_bytes). A set_dict is {"set", "applies_to",
    "standards": [...], "supplements": {id: [text]}, "path"}; None when the
    file could not be read (problems then says why, or is ["absent"])."""
    label = label or os.path.basename(path)
    keys = keys or (OVERLAY_KEYS if required == OVERLAY_FIELDS else FRONT_KEYS)
    raw, why = _read_bytes(path)
    if raw is None:
        return None, [why if why == "absent" else f"{label}: {why}"], None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, [f"{label}: not UTF-8 ({exc.reason} at byte {exc.start})"], raw
    text = text.lstrip("﻿")
    lines = text.replace("\r\n", "\n").split("\n")
    meta, start, problems = _front_matter(lines, label, keys)
    if not meta:
        return None, problems, raw
    set_name = meta.get("set", "")
    standards, supplements, seen = [], {}, set()
    current = None  # ("standard", dict) or ("supplement", id, [lines])
    field = None

    def close():
        if current and current[0] == "supplement":
            body = "\n".join(current[2]).strip()
            if body:
                supplements.setdefault(current[1], []).append(body)

    for number, line in enumerate(lines[start:], start + 1):
        if line.startswith("## "):
            close()
            field = None
            match = _STANDARD_RE.match(line)
            sup = _SUPPLEMENTS_RE.match(line)
            if sup:
                target = sup.group(1)
                if not _ID_RE.match(target):
                    problems.append(f"{label}:{number}: Supplements names {target!r}, "
                                    "which is not a standard id")
                current = ("supplement", target, [])
            elif match:
                sid, name = match.group(1), match.group(2)
                if sid.split("-")[0] != set_name:
                    problems.append(f"{label}:{number}: {sid} does not carry this file's "
                                    f"set prefix {set_name}")
                if sid in seen:
                    problems.append(f"{label}:{number}: {sid} is defined twice")
                seen.add(sid)
                current = ("standard", {"id": sid, "name": name, "set": set_name,
                                        "fields": {}, "supplements": [], "line": number})
                standards.append(current[1])
            else:
                problems.append(f"{label}:{number}: heading {line.strip()[:60]!r} is neither "
                                "'## <ID> <name>' nor '## Supplements <ID>'")
                current = None
            continue
        if current is None:
            continue
        if current[0] == "supplement":
            current[2].append(line)
            continue
        found = _FIELD_RE.match(line)
        if found:
            field = found.group(1)
            if field in current[1]["fields"]:
                problems.append(f"{label}:{number}: {current[1]['id']} repeats **{field}.**")
            current[1]["fields"][field] = [found.group(2)]
        elif field:
            current[1]["fields"][field].append(line)
    close()
    for std in standards:
        std["fields"] = {k: "\n".join(v).strip() for k, v in std["fields"].items()}
        for name in required:
            if not std["fields"].get(name):
                problems.append(f"{label}: {std['id']} has no **{name}.** field")
    if not standards and not supplements:
        problems.append(f"{label}: defines no standard")
    return ({"set": set_name, "applies_to": meta["applies-to"], "standards": standards,
             "supplements": supplements, "path": path, "export": meta.get("export")},
            problems, raw)


# ---- the effective set ----------------------------------------------------------

def _applies(globs, changed_files):
    """Case-insensitive on every host: `fnmatch` folds case on Windows only,
    so `check.PS1` would miss PWSH on Linux and the same change would stamp a
    different digest per host. Folding can only add a set (over-list), never
    drop one."""
    if "**" in globs:
        return True
    return any(crew_ticket.glob_match(path.replace("\\", "/").lower(), glob.lower())
               for path in changed_files for glob in globs)


def _plugin_sets(refs_dir):
    """([(set_dict, raw)], problems) for every *.md in the references dir."""
    try:
        names = sorted(n for n in os.listdir(refs_dir) if n.endswith(".md"))
    except OSError as exc:
        return [], [f"the plugin standards directory {refs_dir} cannot be listed: {exc}"]
    sets, problems, owners = [], [], {}
    for name in names:
        parsed, found, raw = parse_set(os.path.join(refs_dir, name), f"references/{name}")
        problems += [p for p in found if p != "absent"]
        if parsed is None:
            continue
        if parsed["supplements"]:
            problems.append(f"references/{name}: a plugin set may not carry Supplements")
        if parsed["set"] == OVERLAY_SET:
            problems.append(f"references/{name}: set {OVERLAY_SET} is the repository "
                            "overlay's set; a plugin set may not use it")
        if parsed["set"] in owners:
            problems.append(f"references/{name}: set {parsed['set']} is also "
                            f"references/{owners[parsed['set']]}")
        owners[parsed["set"]] = name
        sets.append((parsed, raw))
    if "GEN" not in owners:
        problems.append(f"the plugin standards directory {refs_dir} has no set GEN")
    return sorted(sets, key=lambda item: (item[0]["set"] != "GEN", item[0]["set"])), problems


def effective_set(root, changed_files, refs_dir=None, applies=None):
    """{"standards", "overlay": present|absent|unknown, "digest", "problems",
    "sets", "overlay_problem"}. The generic set always; each stack set whose
    applies-to matches a changed file; the overlay when present. `applies`,
    when given, replaces the changed-file match: it takes a set's applies-to
    list and answers whether the set is in (`sets --touch`, L-0518)."""
    refs_dir = refs_dir or references_dir()
    changed_files = list(changed_files or [])
    if applies is None:
        def applies(globs):
            return _applies(globs, changed_files)
    plugin, problems = _plugin_sets(refs_dir)
    plugin_ids = {s["id"] for parsed, _ in plugin for s in parsed["standards"]}
    digest = hashlib.sha256()
    standards, sets = [], []
    for parsed, raw in plugin:
        if not applies(parsed["applies_to"]):
            continue
        sets.append(parsed["set"])
        standards += [dict(s, source=f"references/{os.path.basename(parsed['path'])}")
                      for s in parsed["standards"]]
        digest.update(parsed["set"].encode() + b"\0" + raw + b"\0")

    overlay_path = os.path.join(root, *OVERLAY_REL.split("/"))
    parsed, found, raw = parse_set(overlay_path, OVERLAY_REL, OVERLAY_FIELDS, OVERLAY_KEYS)
    overlay_problems = [] if found == ["absent"] else list(found)
    if found == ["absent"]:
        overlay = "absent"
        digest.update(OVERLAY_SET.encode() + b"\0absent\0")
    else:
        if parsed is not None:
            if parsed["set"] != OVERLAY_SET:
                overlay_problems.append(f"{OVERLAY_REL}: set is {parsed['set']!r}; the "
                                        f"overlay's set is {OVERLAY_SET}")
            for std in parsed["standards"]:
                if std["id"] in plugin_ids:
                    overlay_problems.append(f"{OVERLAY_REL}: {std['id']} reuses a plugin id")
            for target in parsed["supplements"]:
                if target not in plugin_ids:
                    overlay_problems.append(f"{OVERLAY_REL}: Supplements {target} names no "
                                            "plugin standard")
        overlay = "unknown" if overlay_problems or parsed is None else "present"
        digest.update(OVERLAY_SET.encode() + b"\0" + (raw or b"") + b"\0")
        if overlay == "present":
            sets.append(OVERLAY_SET)
            for std in standards:
                std["supplements"] = list(parsed["supplements"].get(std["id"], []))
            standards += [dict(s, source=OVERLAY_REL) for s in parsed["standards"]]
    return {"standards": standards, "overlay": overlay, "digest": digest.hexdigest(),
            "problems": problems + overlay_problems, "sets": sets,
            "overlay_problems": overlay_problems}


def summary_line(found):
    ids = [s["id"] for s in found["standards"]]
    if found["overlay"] == "absent":
        overlay = f"overlay: none ({OVERLAY_REL} absent)"
    elif found["overlay"] == "present":
        overlay = f"overlay: present ({OVERLAY_REL})"
    else:
        overlay = f"overlay: UNREADABLE ({OVERLAY_REL}; see the problems below)"
    return (f"standards: {len(ids)} in sets {', '.join(found['sets']) or 'none'}; {overlay}; "
            f"digest {found['digest'][:8]}")


# ---- the self-check record ------------------------------------------------------

def selfcheck_path(root, ticket):
    """The self-check in the ticket's folder, live or `Complete/` (L-0509);
    TicketError when where the ticket lives could not be told."""
    return os.path.join(crew_common.ticket_folder(root, crew_ticket.check_ticket(ticket),
                                                  crew_ticket.TicketError), SELFCHECK_NAME)


def _write_replacing(path, text):
    """The full text is computed before anything opens `path` (CLAUDE.md
    "Landmines"); a per-writer temp name, then `os.replace` (GEN-02)."""
    data = text.encode("utf-8")
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def _create_exclusive(path, text):
    """True when `path` was created with `text`; False when it already existed."""
    data = text.encode("utf-8")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                     0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return True


def selfcheck_template(ticket, found):
    rows = "\n".join(f"| {s['id']} |  |  |" for s in found["standards"])
    return (f"# {ticket} self-check\n\n"
            f"{summary_line(found)}\n\n"
            "Answer every row before `/crew:review`. Status is `addressed` (Evidence: the test that\n"
            "covers it, a `mutation -> failing test` pair, or the file:line that does it) or `n/a`\n"
            "(the reason it does not apply to this change). Then run `crew_standards.py stamp`;\n"
            "any later edit to the change needs a new stamp.\n\n"
            "| ID | Status | Evidence or reason |\n|---|---|---|\n" + rows + "\n")


def read_selfcheck(root, ticket):
    """(rows, stamp, problems). rows: [(id, status, evidence)] in file order;
    stamp: {"bundle", "standards", "base"} or None."""
    return _read_selfcheck_raw(root, ticket)[1:]


def _read_selfcheck_raw(root, ticket):
    """(raw_bytes_or_None, rows, stamp, problems): one read, parsed from the
    bytes it returned, so a caller that writes back writes what it checked."""
    try:
        path = selfcheck_path(root, ticket)
    except crew_ticket.TicketError as exc:
        return None, [], None, [str(exc)]
    raw, why = _read_bytes(path)
    if raw is None:
        return None, [], None, [f"no self-check at .work/tickets/{ticket}/{SELFCHECK_NAME}; "
                                f"run crew_standards.py init --root . --ticket {ticket}"
                                if why == "absent" else f"the self-check {why}"]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw, [], None, ["the self-check is not UTF-8"]
    rows, stamps, problems = [], [], []
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("<!-- stamp:"):
            match = _STAMP_RE.match(stripped)
            if not match:
                problems.append(f"line {number}: the stamp line does not parse")
            else:
                stamps.append({"bundle": match.group(1), "standards": match.group(2),
                               "base": match.group(3)})
            continue
        match = _ROW_RE.match(stripped)
        if not match:
            continue
        cells = [c.strip() for c in match.group(1).split("|", 2)]
        if re.fullmatch(r"[\s|:\-]*", match.group(1)) or cells[0].lower() == "id":
            continue
        if len(cells) < 3 or not _ID_RE.match(cells[0]):
            problems.append(f"line {number}: table row {stripped[:60]!r} is not "
                            "| <ID> | <status> | <evidence or reason> |")
            continue
        rows.append((cells[0], cells[1], cells[2].rstrip("|").strip()))
    if len(stamps) > 1:
        problems.append(f"the self-check carries {len(stamps)} stamp lines; one is allowed")
    return raw, rows, (stamps[0] if len(stamps) == 1 else None), problems


def _placeholder(text):
    value = text.strip().strip("`").strip()
    return value.lower() in PLACEHOLDERS or bool(re.fullmatch(r"<[^<>]*>", value))


def record_problems(rows, found):
    """Every way the rows fail to answer the effective set, one line each."""
    problems, seen = [], {}
    wanted = [s["id"] for s in found["standards"]]
    for sid, status, evidence in rows:
        if sid in seen:
            problems.append(f"{sid}: answered twice")
            continue
        seen[sid] = (status, evidence)
        if sid not in wanted:
            problems.append(f"{sid}: not in the effective set ({', '.join(found['sets'])})")
            continue
        if status not in STATUSES:
            problems.append(f"{sid}: status {status!r} is not addressed or n/a")
        elif _placeholder(evidence):
            problems.append(f"{sid}: {status} needs "
                            f"{'evidence' if status == 'addressed' else 'a reason'}, "
                            f"not {evidence!r}")
    for sid in wanted:
        if sid not in seen:
            problems.append(f"{sid}: no row; every standard in the effective set is answered")
    return problems


def _scope_entry(root, ticket):
    """(has_entry, unreadable): whether `.crew/.scope-base` holds an entry for
    `ticket` that `scope_base.record` would keep, so naming `--record` would
    change nothing; and why the record could not be read, or None.

    `scope_base.read_record` returns None for an absent record and for one it
    cannot read alike. The two are told apart here, because `--record` over an
    unreadable record rewrites the whole file with this ticket's entry alone and
    drops every other ticket's recorded start (GEN-01: could not tell is not
    absent)."""
    import scope_base  # pylint: disable=import-outside-toplevel
    raw, why = _read_bytes(os.path.join(root, scope_base.RECORD))
    if raw is None:
        return False, (None if why == "absent" else why)
    record = scope_base.read_record(root)
    if record is None:
        return False, "does not parse as a JSON object"
    entry = record.get(ticket)
    return (isinstance(entry, dict) and isinstance(entry.get("base"), str)
            and bool(entry["base"])), None


def _scope(root, ticket):
    """(base, manifest, problems, note): the base `scope_base.py --base`
    resolves for the ticket and review_patch.compute's manifest for it -- the
    same function on the same base /crew:review bundles with (GEN-07).

    A recorded start is used as recorded. A record that exists but cannot be
    used (its commit is gone, or no longer an ancestor of HEAD) resolves to the
    merge-base with the default branch, which is what /crew:review bundles
    against too; that base is used and `note` says "(fallback)" with resolve's
    reason, for every line derived from it (GEN-01). A start first recorded on
    a branch already past the default branch is the merge-base, recorded as a
    guess (`record-fallback`); it is used, and marked the same way. `--record`
    keeps an existing entry, so it is named only when there is no entry, and
    never over a record that cannot be read, which it would rewrite with this
    ticket's entry alone; a base resolved to HEAD alone (no default branch) is
    refused."""
    import review_patch  # pylint: disable=import-outside-toplevel
    import scope_base  # pylint: disable=import-outside-toplevel
    has_entry, unreadable = _scope_entry(root, ticket)
    if unreadable:
        return None, None, [f"the scope base record {scope_base.RECORD} cannot be read "
                            f"({unreadable}); recording a start now would rewrite it with "
                            f"{ticket}'s entry alone and drop every other ticket's, so repair "
                            "it by hand first"], None
    base, source, why = scope_base.resolve(root, ticket)
    note = None
    if source == "record-fallback" and base:
        note = why
    elif source == "merge-base" and base and has_entry:
        note = why if "(fallback)" in why else f"(fallback) {why}"
    elif source != scope_base.RECORDED or not base:
        if has_entry:
            return None, None, [f"the scope base for {ticket} cannot be used ({why}); an "
                                "existing record is never overwritten, so recording again "
                                "changes nothing: restore that commit, or fetch the default "
                                "branch so a merge-base fallback exists"], None
        return None, None, [f"no scope base recorded for {ticket} ({why}); run "
                            f"scope_base.py --root . --record {ticket} "
                            "(/crew:implement step 1)"], None
    try:
        manifest = review_patch.compute(root, base)[0]
    except RuntimeError as exc:
        return base, None, [f"the review bundle could not be built: {exc}"], note
    return base, manifest, [], note


def _noted(line, base, note):
    return f"{line}; scope base {base[:12]} is {note}" if note else line


def changed_files(manifest):
    files = []
    for key in ("committed_files", "staged_files", "unstaged_files", "untracked_files"):
        value = manifest.get(key)
        if not isinstance(value, list):
            raise ValueError(f"the manifest has no {key} list")  # noqa: TRY004 - callers catch ValueError
        files += [f for f in value if isinstance(f, str)]
    return sorted(set(files))


def init(root, ticket, refs_dir=None):
    """(exit_code, lines)."""
    base, manifest, problems, note = _scope(root, ticket)
    if problems:
        return 1, problems
    found = effective_set(root, changed_files(manifest), refs_dir)
    if found["problems"]:
        return 1, ["the effective standards set could not be read:"] + found["problems"]
    try:
        path = selfcheck_path(root, ticket)
    except crew_ticket.TicketError as exc:
        return 1, [str(exc)]
    if not _create_exclusive(path, selfcheck_template(ticket, found)):
        return 1, [f".work/tickets/{ticket}/{SELFCHECK_NAME} already exists; left unchanged"]
    return 0, [_noted(f"self-check: wrote .work/tickets/{ticket}/{SELFCHECK_NAME} with "
                      f"{len(found['standards'])} rows", base, note), summary_line(found)]


def stamp(root, ticket, refs_dir=None):
    """(exit_code, lines). Refuses on any problem; writes nothing then. The
    rows are validated from one read and those same bytes are written back
    with the stamp; a record that changed during the compute is refused, not
    stamped.

    That re-read is not a GEN-03 binding, and is not claimed as one: the
    filesystem offers no compare-and-swap on a file's content, so an edit
    landing between the re-read and `os.replace` is overwritten. GEN-03 asks
    for the missing binding and the window to be named: this is the window,
    accepted as a risk because the only writer is the author's own editor on
    this checkout, and the loss is visible (the edit is gone from the file
    and the next stamp or gate reads what is there)."""
    raw, rows, _, problems = _read_selfcheck_raw(root, ticket)
    base, manifest, scope_problems, note = _scope(root, ticket)
    problems += scope_problems
    found = None
    if manifest is not None:
        if not manifest.get("bundle_sha256"):
            problems.append(f"nothing to review: no change since the scope base {base[:12]}")
        found = effective_set(root, changed_files(manifest), refs_dir)
        problems += found["problems"] + record_problems(rows, found)
    if problems or found is None:
        return 1, [f"self-check: {p}" for p in problems]
    try:
        path = selfcheck_path(root, ticket)
    except crew_ticket.TicketError as exc:
        return 1, [f"self-check: {exc}"]
    now, why = _read_bytes(path)
    if now != raw:
        return 1, [f"self-check: .work/tickets/{ticket}/{SELFCHECK_NAME} changed while it was "
                   f"being stamped{'' if now is not None else f' ({why})'}; nothing written, "
                   "run stamp again"]
    lines = [line for line in raw.decode("utf-8").split("\n")
             if not line.strip().startswith("<!-- stamp:")]
    line = (f"<!-- stamp: bundle={manifest['bundle_sha256']} standards={found['digest']} "
            f"base={base} -->")
    _write_replacing(path, "\n".join(lines[:1] + [line] + lines[1:]))
    return 0, [_noted(f"self-check: stamped {len(rows)} rows for bundle "
                      f"{manifest['bundle_sha256'][:12]}, standards {found['digest'][:8]}, "
                      f"base {base[:12]}", base, note)]


# ---- the review gate --------------------------------------------------------------

def _ancestor_problem(path):
    """None when the nearest existing ancestor of `path` is a directory, so a
    FileNotFoundError on `path` proves it absent; otherwise why it does not.
    Windows raises FileNotFoundError, not NotADirectoryError, for a path under
    a regular file, so ENOENT alone does not prove absence there (GEN-01)."""
    parent = os.path.dirname(path)
    while True:
        try:
            mode = os.stat(parent).st_mode
        except FileNotFoundError:
            up = os.path.dirname(parent)
            if up == parent:
                return f"no ancestor of {path} exists"
            parent = up
            continue
        except OSError as exc:
            return f"{exc.__class__.__name__} on {parent}: {exc.strerror or exc}"
        return None if stat.S_ISDIR(mode) else f"{parent} is not a directory"


def gate_applies(root, ticket):
    """(applies, note). The self-check is required of /crew:implement and
    /crew:fix, which both refuse without an approval receipt; a ticket with no
    receipt never ran either, so the gate does not apply and says so. A
    receipt that cannot be read, or a lookup that fails, applies the gate.
    `read_approval` says "absent" whenever the path does not exist after a
    failed read, which is also what an unreadable or non-directory parent
    looks like; so absence is proven here with an lstat, and only
    FileNotFoundError is absent (GEN-01)."""
    try:
        _, state = crew_ticket.read_approval(root, ticket)
        path = crew_ticket.approval_path(root, ticket)
    except crew_ticket.TicketError as exc:
        return True, f"the approval receipt could not be looked up ({exc}); gating anyway"
    if state != "absent":
        return True, None
    try:
        os.lstat(path)
    except FileNotFoundError:
        why = _ancestor_problem(path)
        if why:
            return True, (f"could not tell whether {ticket} has an approval receipt ({why}); "
                          "gating anyway")
        return False, (f"standards self-check not required: {ticket} has no approval receipt, "
                       "so /crew:implement and /crew:fix never ran for it")
    except OSError as exc:
        return True, (f"could not tell whether {ticket} has an approval receipt "
                      f"({exc.__class__.__name__}: {exc.strerror or exc}); gating anyway")
    return True, (f"could not tell whether {ticket} has an approval receipt (it was not "
                  "readable, then it existed); gating anyway")


def gate_problems(root, ticket, manifest, refs_dir=None):
    """Why the round must not be reserved; empty when the self-check is
    complete and stamped for exactly this bundle and this standards set."""
    return _gate(root, ticket, manifest, refs_dir)[0]


def _gate(root, ticket, manifest, refs_dir=None):
    """(problems, standards digest or None)."""
    problems = []
    try:
        files = changed_files(manifest)
    except (ValueError, AttributeError) as exc:
        return [f"the review manifest is unusable: {exc}"], None
    found = effective_set(root, files, refs_dir)
    problems += found["problems"]
    rows, seal, read_problems = read_selfcheck(root, ticket)
    problems += read_problems
    if not read_problems or rows:
        problems += record_problems(rows, found)
    if seal is None:
        if not read_problems:
            problems.append("the self-check is not stamped")
    else:
        if seal["bundle"] != manifest.get("bundle_sha256"):
            problems.append("the stamp is stale: it was made for review bundle "
                            f"{seal['bundle'][:12]}, and this bundle is "
                            f"{str(manifest.get('bundle_sha256'))[:12]} (the change moved "
                            "after stamping, or the review used another base)")
        if seal["standards"] != found["digest"]:
            problems.append("the stamp is stale: the standards set changed since stamping "
                            f"({seal['standards'][:8]} then, {found['digest'][:8]} now)")
    return problems, found["digest"]


def review_gate(root, ticket, manifest_path, refs_dir=None):
    """(problems, note) for review_run.py: note is a line to print either way."""
    applies, note = gate_applies(root, ticket)
    if not applies:
        return [], note
    try:
        with open(manifest_path, "rb") as fh:
            manifest = json.loads(fh.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        return [f"the review manifest {manifest_path} cannot be read: {exc}"], note
    if not isinstance(manifest, dict):
        return [f"the review manifest {manifest_path} is not an object"], note
    problems, digest = _gate(root, ticket, manifest, refs_dir)
    if problems:
        return problems, note
    current = (f"standards self-check current (std:{digest[:8]}); that token goes in "
               "this round's .crew/metrics.md reviewer cell")
    return [], f"{note}; {current}" if note else current


# ---- the reviewer's checklist -----------------------------------------------------

def _indent(text):
    return "\n".join("    " + line if line.strip() else "" for line in text.split("\n"))


def checklist_block(root, manifest, refs_dir=None):
    """The shared prompt's standards appendix. Never reads selfcheck.md."""
    out = ["== Development standards checklist (appendix) ==",
           "The author ran these as a self-check; the answers are withheld so you judge "
           "applicability yourself.",
           "This list does not bound the review: report a defect outside it the same way."]
    try:
        files, unknown = changed_files(manifest), None
    except (ValueError, AttributeError) as exc:
        files, unknown = [], (f"UNKNOWN: the manifest's file lists are unusable ({exc}); which "
                              "stack sets apply is not known, so only the always-on sets are "
                              "listed.")
    found = effective_set(root, files, refs_dir)
    out.append(summary_line(found))
    if unknown:
        out.append(unknown)
    for problem in found["overlay_problems"]:
        out.append(f"UNREADABLE: {problem}")
    for problem in found["problems"]:
        if problem not in found["overlay_problems"]:
            out.append(f"PROBLEM: {problem}")
    for std in found["standards"]:
        out.append(f"{std['id']} {std['name']} ({std['source']})")
        out.append("  Rule:")
        out.append(_indent(std["fields"].get("Rule", "")))
        out.append("  Self-check:")
        out.append(_indent(std["fields"].get("Self-check", "")))
        for text in std.get("supplements") or []:
            out.append(f"  Supplement ({OVERLAY_REL}):")
            out.append(_indent(text))
    return out


# ---- findings to standards --------------------------------------------------------

_PROPOSABLE = ("CLEAN", "FINDINGS")


def _recorded_verdict(root, ticket, round_no):
    """None when the review ledger records round `round_no` as completed with
    a CLEAN or FINDINGS verdict; otherwise why not (L-0518 F1). The ledger is
    where `review_run.finish` scores a round, exit code, timeout, every bundle
    part and webtest reason included, so an out.txt that reads as FINDINGS on
    its own is not proposed from a round finish called INCOMPLETE. No ledger,
    an unreadable one, no row, a row with no result or two rows for the round
    are could-not-tell, never "the out.txt decides" (GEN-01)."""
    import review_ledger  # pylint: disable=import-outside-toplevel
    try:
        found = review_ledger.status(root, ticket)
    except (review_ledger.LedgerError, OSError, ValueError) as exc:
        return f"the review ledger could not be read ({exc})"
    if found.get("state") == review_ledger.UNKNOWN:
        return f"the review ledger {found.get('path')} is unreadable"
    rounds = found.get("rounds") or []
    if any(not isinstance(r, dict) for r in rounds):
        return f"the review ledger {found.get('path')} holds a round that is not an object"
    rows = [r for r in rounds
            if r.get("round") == round_no and not isinstance(r.get("round"), bool)]
    if len(rows) != 1:
        return (f"the review ledger records {'no' if not rows else len(rows)} round "
                f"{round_no}" + ("" if rows else f" for {ticket}"))
    row = rows[0]
    if row.get("status") != "completed" or row.get("verdict") not in _PROPOSABLE:
        return (f"the review ledger records round {round_no} as "
                f"{row.get('verdict') or row.get('status') or 'no result'}, not CLEAN or "
                "FINDINGS")
    return None


def proposals(root, ticket, scratch, round_no):
    """(exit_code, lines). One section per BLOCK/FIX line of the round's
    out.txt, verbatim, for the owner to rule on. Writes only the proposals
    file, with an exclusive create; never a set file.

    The round must first be recorded CLEAN or FINDINGS in the review ledger
    (`_recorded_verdict`); the out.txt parse below is a second check.

    An out.txt the verdict parser calls INCOMPLETE -- empty, a line that might
    be a contract line it cannot read (a finding behind a bullet), a stray
    line matching the shortfall wording list (`review_verdict._SHORTFALL`:
    "could not review ...", "skipped", ...), even beside well-formed
    findings, or neither CLEAN nor a finding -- is refused and nothing is
    written: "could not tell" never becomes "no findings", and the exclusive
    create is left free for the corrected run (GEN-01). A round the parser
    recovered despite harmless stray lines (prose or a code fence beside
    well-formed findings, L-0576) is FINDINGS, and its findings are proposed
    like any other. That wording list cannot be complete, so an admission it
    misses ("I only inspected one of the nine files") is recovered as prose
    and the round is FINDINGS: such a line is in the parser's `ignored`, which
    /crew:review always reports (`review.json`'s `ignored_text`), and is not
    written here."""
    import review_verdict  # pylint: disable=import-outside-toplevel
    recorded = _recorded_verdict(root, ticket, round_no)
    if recorded:
        return 1, [f"proposals: {recorded}, so which findings round {round_no} holds is not "
                   "known; nothing written"]
    source = os.path.join(scratch, "out.txt")
    raw, why = _read_bytes(source)
    if raw is None:
        return 1, [f"proposals: {source} {'does not exist' if why == 'absent' else why}"]
    text = raw.decode("utf-8", errors="replace")
    parsed = review_verdict.parse(text, 0)
    if parsed["verdict"] == review_verdict.INCOMPLETE:
        return 1, [f"proposals: {source} is {review_verdict.INCOMPLETE}, so which findings it "
                   "holds is not known; nothing written"] + [
                       f"proposals:   {reason}" for reason in parsed["reasons"]]
    findings = [line for line in parsed["findings"] if not line.startswith("NIT|")]
    name = f"standards-proposals-r{round_no}.md"
    try:
        path = os.path.join(crew_common.ticket_folder(root, crew_ticket.check_ticket(ticket),
                                                      crew_ticket.TicketError), name)
    except crew_ticket.TicketError as exc:
        return 1, [f"proposals: {exc}"]
    body = [f"# {ticket} standards proposals, review round {round_no}", "",
            f"From `{source}`: {len(findings)} BLOCK/FIX finding(s), each verbatim below. For each,",
            "fill Covered by (the standard that covers it, or `none`), Self-check said (what the",
            "self-check row for that standard said), and Proposal (a new standard or an amendment",
            "when no standard covers it or the self-check said addressed). The owner approves or",
            "rejects each proposal; nothing is added to any standards file automatically.", ""]
    for number, line in enumerate(findings, 1):
        body += [f"## Finding {number}", "", "    " + line, "",
                 "- Covered by:", "- Self-check said:", "- Proposal:", ""]
    if not findings:
        body.append("No BLOCK or FIX finding in this round.")
    if not _create_exclusive(path, "\n".join(body).rstrip("\n") + "\n"):
        return 1, [f"proposals: .work/tickets/{ticket}/{name} already exists; left unchanged"]
    return 0, [f"proposals: wrote .work/tickets/{ticket}/{name} with {len(findings)} "
               "finding(s) for the owner to rule on"]


# ---- the before/after metric -------------------------------------------------------

def _side(values, floor):
    if not values:
        return {"n": 0, "median": None, "mean": None, "enough": False}
    return {"n": len(values), "median": statistics.median(values),
            "mean": round(statistics.mean(values), 2), "enough": len(values) >= floor}


def _std_side(reviewer):
    """"before" (no `std:` token), "after" (`std:<8 hex>`), "std_none"
    (`std:none`: the gate stood down or did not apply, so the row is after the
    change but had no self-check), or "std_unreadable" (a `std:` token that is
    neither). Only "before" and "after" are measured; the other two are
    counted and on neither side, so a post-change row never lands in the
    baseline (GEN-01)."""
    match = _STD_TOKEN_RE.search(reviewer or "")
    if not match:
        return "before"
    if _STD_DIGEST_RE.fullmatch(match.group(1)):
        return "after"
    if match.group(1) == "none":
        return "std_none"
    return "std_unreadable"


def metric_summary(text):
    """First-round BLOCK+FIX per ticket, before (no std: token) and after
    (a std:<8 hex> token); std:none and unreadable std: rows on neither side."""
    import crew_metrics  # pylint: disable=import-outside-toplevel
    import crew_migrate  # pylint: disable=import-outside-toplevel
    rows, _ = crew_migrate.metrics_rows(text or "")
    per = {"before": {}, "after": {}}
    unknown_round = unscored = 0
    neither = {"std_none": 0, "std_unreadable": 0}
    for index, row in enumerate(rows):
        if row["reviewRound"] == crew_migrate.UNKNOWN:
            unknown_round += 1
            continue
        if row["reviewRound"] != 1:
            continue
        if crew_migrate.UNKNOWN in (row["block"], row["fix"]):
            unscored += 1
            continue
        side = _std_side(row["reviewer"])
        if side in neither:
            neither[side] += 1
            continue
        key = row["ticketId"] if row["ticketId"] != crew_migrate.UNKNOWN else ("row", index)
        per[side][key] = per[side].get(key, 0) + row["block"] + row["fix"]
    floor = crew_metrics.MIN_BASELINE_KNOWN
    return {"before": _side(list(per["before"].values()), floor),
            "after": _side(list(per["after"].values()), floor),
            "unknown_round": unknown_round, "unscored": unscored, "floor": floor, **neither}


def _side_text(name, side, floor):
    if not side["n"]:
        return f"{name} median n/a (n=0, not enough data)"
    enough = "" if side["enough"] else f", not enough data: fewer than {floor} tickets"
    return f"{name} median {side['median']} mean {side['mean']} (n={side['n']}{enough})"


def metric(root, record=False, today=None):
    """(exit_code, lines). --record appends one line with no `|`, so neither
    crew_state.read_metrics nor crew_migrate.metrics_rows reads it as a row.

    The file is the main checkout's from a linked worktree (L-0582). When git
    cannot name it, exit 1 before any read or write: nothing is read, nothing
    is recorded, and the worktree's own copy is never the fallback."""
    path, problem = crew_common.metrics_md_path(root)
    if problem:
        return 1, [f"standards-metric: could not tell which .crew/metrics.md to use ({problem}); "
                   "nothing read, nothing recorded"]
    raw, why = _read_bytes(path)
    if raw is None and why != "absent":
        return 1, [f"standards-metric: {path} {why}"]
    text = raw.decode("utf-8", errors="replace") if raw is not None else ""
    found = metric_summary(text)
    floor = found["floor"]
    lines = [f"standards-metric: first-round BLOCK+FIX per ticket ({path})",
             "  " + _side_text("before (no std: token)", found["before"], floor),
             "  " + _side_text("after (std: token)", found["after"], floor),
             f"  unknown-round rows {found['unknown_round']} (on neither side); first-round rows "
             f"with no BLOCK/FIX count {found['unscored']}",
             f"  std:none rows {found['std_none']} (the gate did not apply; on neither side); "
             f"unreadable std: tokens {found['std_unreadable']} (on neither side)"]
    if record:
        today = today or datetime.date.today().isoformat()  # noqa: DTZ011 - operator's local day
        line = (f"standards-metric {today}: first-round BLOCK+FIX "
                f"{_side_text('before', found['before'], floor)}, "
                f"{_side_text('after', found['after'], floor)}, "
                f"unknown-round rows {found['unknown_round']}, std:none rows {found['std_none']}, "
                f"unreadable std: tokens {found['std_unreadable']}")
        line = line.replace("|", "/")
        prefix = "" if not text or text.endswith("\n") else "\n"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(prefix + line + "\n")
        lines.append(f"standards-metric: recorded in {path}: {line}")
    return 0, lines


# ---- CLI ---------------------------------------------------------------------------

def _touch_sets(root, ticket, refs_dir=None):
    """`sets --touch` (L-0518 F4): the effective set from the spec's Touch
    list, needing no scope base, so it answers at plan time. A stack set is in
    when its applies-to overlaps a Touch entry, through the matcher
    `/crew:implement` step 2 uses (it over-lists, never under-lists). A spec or
    Touch list that cannot be read lists every set under UNKNOWN and exits 1."""
    import recurring_findings  # pylint: disable=import-outside-toplevel
    folder, _where, why = crew_common.locate_ticket(root, crew_ticket.check_ticket(ticket))
    spec = os.path.join(folder, "spec.md") if folder else None  # L-0509: live or archived
    unknown = None
    try:
        if spec is None:
            raise OSError(f"could not tell where {ticket} lives: {why}")
        # The FIFO-safe reader step 2's block uses (PYTHON-07), so both read a spec alike.
        text = recurring_findings._read_regular(spec)  # pylint: disable=protected-access
    except (OSError, UnicodeDecodeError) as exc:
        touch, unknown = [], f"{spec or ticket} cannot be read ({exc.__class__.__name__}: {exc})"
    else:
        touch, why = crew_ticket.parse_touch(text)
        if why:
            unknown = f"the spec's Touch list: {'; '.join(why)}"
    if unknown:
        found = effective_set(root, [], refs_dir, applies=lambda globs: True)
        lines = [summary_line(found),
                 f"UNKNOWN: {unknown}; which stack sets apply is not known, so every set is "
                 "listed"]
    else:
        def applies(globs):
            # Case-folded like `_applies`; the as-written pass keeps a Touch
            # entry naming a mixed-case directory on a case-sensitive disk.
            return "**" in globs or any(
                recurring_findings.matches(entry, glob, touch=True, root=root)
                or recurring_findings.matches(entry.lower(), glob.lower(), touch=True,
                                              root=root)
                for entry in touch for glob in globs)
        found = effective_set(root, [], refs_dir, applies=applies)
        lines = [f"{summary_line(found)}; from the spec's Touch list"]
    lines += [f"{s['id']} {s['name']} ({s['source']})" for s in found["standards"]]
    lines += [f"PROBLEM: {p}" for p in found["problems"]]
    return (1 if unknown or found["problems"] else 0), lines


def _sets(root, ticket, refs_dir=None, touch=False):
    if touch:
        return _touch_sets(root, ticket, refs_dir)
    base, manifest, problems, note = _scope(root, ticket)
    if problems:
        return 1, problems
    found = effective_set(root, changed_files(manifest), refs_dir)
    lines = [_noted(summary_line(found), base, note)]
    lines += [f"{s['id']} {s['name']} ({s['source']})" for s in found["standards"]]
    lines += [f"PROBLEM: {p}" for p in found["problems"]]
    return (1 if found["problems"] else 0), lines


# ---- exporting the standards to PR-side reviewers (L-0718) --------------------------

EXPORT_TARGETS = ("review", "agents", "bugbot")
EXPORT_MAX_CHARS = 28000   # Bugbot truncates a rule at 30,000 characters
AGENTS_BLOCK_MAX_LINES = 40
EXPORT_MARK = "crew-standards-export"
EXPORT_DIR = "docs/review-rules"
EXPORT_FILES = {"review": "REVIEW.md", "bugbot": ".cursor/BUGBOT.md"}
AGENTS_REL = "AGENTS.md"
NOT_OPTED_IN = "standards export: not opted in (no export key in .crew/standards.md)"
# crew_instructions.MARKER: a substring test makes crew own the whole AGENTS.md
# (test_standards_export holds the two equal).
GENERATED_MARKER = "crew:generated"
_FILE_MARK_RE = re.compile(r"^<!-- " + EXPORT_MARK + r" digest=([0-9a-f]{64}) crew=(\S+) -->$")
_START_RE = re.compile(r"^<!-- " + EXPORT_MARK + r" start digest=([0-9a-f]{64}) crew=(\S+) -->$")
_END_LINE = f"<!-- {EXPORT_MARK} end -->"


def _crew_version():
    """(version, None) or (None, problem): the plugin.json beside hooks/."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir,
                        ".claude-plugin", "plugin.json")
    raw, why = _read_bytes(path)
    try:
        version = json.loads(raw)["version"] if raw is not None else None
    except (ValueError, KeyError, TypeError):
        version = None
    if not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z.+-]+", version):
        return None, f"the crew version cannot be read from plugin.json ({why or 'malformed'})"
    return version, None


def _export_targets(raw):
    """(targets, None) for a valid `export` value, else (None, problem)."""
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        value = None
    if (not isinstance(value, list) or not value or len(set(map(str, value))) != len(value)
            or not all(isinstance(v, str) and v in EXPORT_TARGETS for v in value)):
        return None, (f"{OVERLAY_REL}: export must be a non-empty JSON list of distinct "
                      f"values from {list(EXPORT_TARGETS)}, got {str(raw)[:60]!r}")
    return [t for t in EXPORT_TARGETS if t in value], None


def _scope_text(globs):
    return "always (`**`)" if "**" in globs else "files matching " + ", ".join(
        f"`{g}`" for g in globs)


def _render_standards(group):
    """The one rendering of a set's standards, shared by the set file and the
    entry points. Rule, Self-check and Supplements only: never Why or Earned by."""
    out = []
    for std in group["standards"]:
        out += [f"## {std['id']} {std['name']}", "",
                "**Rule.** " + std["fields"].get("Rule", ""), "",
                "**Self-check.**", std["fields"].get("Self-check", ""), ""]
        for text in std.get("supplements") or []:
            out += [f"**Supplement ({OVERLAY_REL}).**", text, ""]
    return out


def _link(frm, to):
    return os.path.relpath(to, os.path.dirname(frm) or ".").replace(os.sep, "/")


def _render_set_file(group, mark):
    return "\n".join([mark, f"# Review rules: set {group['set']}", "",
                      f"Applies to: {_scope_text(group['applies_to'])}.",
                      "Generated from crew's standards by `crew_standards.py export --write`; "
                      "do not edit by hand. Check a change against every standard here whose "
                      "scope matches the files it touches.", ""]
                     + _render_standards(group)) + "\n"


def _render_entry(rel, groups, mark):
    out = [mark, "# Review rules", "",
           "Generated from crew's standards by `crew_standards.py export --write`; do not edit "
           "by hand. Check every change against the standards below. The always-on standards "
           "are written out in full. For each stack set, read the linked file when the change "
           "touches files matching its scope; the lists show ids and names only.", "",
           "# Always-on standards", ""]
    for group in (g for g in groups if "**" in g["applies_to"]):
        out += [f"Set {group['set']}, applies to {_scope_text(group['applies_to'])}:", ""]
        out += _render_standards(group)
    out += ["# Stack sets", ""]
    for group in (g for g in groups if "**" not in g["applies_to"]):
        link = _link(rel, f"{EXPORT_DIR}/{group['set']}.md")
        out.append(f"- Set {group['set']}, applies to {_scope_text(group['applies_to'])}: "
                   f"[{group['set']}.md]({link})")
        out += [f"  - {s['id']} {s['name']}" for s in group["standards"]]
    return "\n".join(out) + "\n"


def _render_block(groups, targets, mark):
    start = mark.replace(f"<!-- {EXPORT_MARK} ", f"<!-- {EXPORT_MARK} start ")
    out = [start, "## Code Review Rules", "",
           f"Every standard crew applies in review is written out in `{EXPORT_DIR}/`, one file "
           "per set, each stating the files it applies to.",
           "Check a change against the standards whose scope matches the files it touches."
           + (f" The always-on standards are also written out in full in `{EXPORT_FILES['review']}`."
              if "review" in targets else ""), ""]
    for group in groups:
        link = f"{EXPORT_DIR}/{group['set']}.md"
        out += [f"- {s['id']} {s['name']}: [{link}]({link})" for s in group["standards"]]
    return "\n".join(out + [_END_LINE]) + "\n"


def _find_block(text):
    """(start, end, None) character offsets of the one marked block, (None, None, None)
    for none, (None, None, problem) for a start without an end, two blocks or an
    end first."""
    starts = list(re.finditer(_START_RE.pattern, text, re.M))
    ends = list(re.finditer("^" + re.escape(_END_LINE) + r"[ \t]*$\n?", text, re.M))
    if not starts and not ends:
        return None, None, None
    if len(starts) != 1 or len(ends) != 1 or ends[0].start() < starts[0].start():
        return None, None, (f"{AGENTS_REL}: the {EXPORT_MARK} markers are malformed (need exactly "
                            "one start followed by one end)")
    return starts[0].start(), ends[0].end(), None


def _splice(existing, block):
    """AGENTS.md text with `block` in place of the marked one, appended when none, removed
    when `block` is None. (text, problem)."""
    start, end, problem = _find_block(existing)
    if problem:
        return None, problem
    if start is None:
        if block is None:
            return existing, None
        return (existing.rstrip("\n") + "\n\n" if existing.strip() else "") + block, None
    head = existing[:start]
    if block is None:
        head = head.rstrip("\n") + "\n" if head.strip() else ""
        return head + existing[end:].lstrip("\n"), None
    return head + block + existing[end:], None


def _symlink_problem(root, rel):
    """Why `rel` may not be read or written as an export output, or None: a symlink
    anywhere under `root` on its path (a write would replace it or leave the repository)
    or a leaf that exists and is not a regular file."""
    path = root
    for part in rel.split("/"):
        path = os.path.join(path, part)
        try:
            mode = os.lstat(path).st_mode
        except FileNotFoundError:
            return None
        except OSError as exc:
            return f"{rel} cannot be inspected: {exc.__class__.__name__}"
        if stat.S_ISLNK(mode):
            return f"{rel} is, or sits under, a symlink ({part}); the export does not follow it"
    return None if stat.S_ISREG(mode) or stat.S_ISDIR(mode) else f"{rel} is not a regular file"


def _read_text_file(root, rel):
    """(text, None) / (None, None) when absent / (None, problem)."""
    problem = _symlink_problem(root, rel)
    if problem:
        return None, problem
    raw, why = _read_bytes(os.path.join(root, *rel.split("/")))
    if raw is None:
        return None, (None if why == "absent" else f"{rel} {why}")
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, f"{rel} is not UTF-8"


def _export_build(root, refs_dir=None, crew=None):
    """{"opted", "targets", "digest", "crew", "files": {rel: text}, "block", "agents",
    "problems"}. `opted` False: not opted in. `block` and `agents` are "" when not wanted.
    Reads, writes nothing. A non-empty `problems` means refuse: nothing may be written
    from it (GEN-01)."""
    out = {"opted": False, "targets": [], "digest": "", "crew": "", "files": {}, "block": "",
           "agents": "", "problems": []}
    found = effective_set(root, [], refs_dir, applies=lambda globs: True)
    if found["overlay"] == "unknown":
        out["problems"] = list(found["overlay_problems"])
        return out
    if found["overlay"] == "absent":
        return out
    refs_dir = refs_dir or references_dir()
    overlay, _, _ = parse_set(os.path.join(root, *OVERLAY_REL.split("/")), OVERLAY_REL,
                              OVERLAY_FIELDS, OVERLAY_KEYS)
    if overlay is None or overlay["export"] is None:
        return out
    out["opted"] = True
    targets, problem = _export_targets(overlay["export"])
    out["targets"] = targets or []
    if problem or found["problems"]:
        out["problems"] = ([problem] if problem else []) + found["problems"]
        return out
    version, problem = (crew, None) if crew else _crew_version()
    if problem:
        out["problems"] = [problem]
        return out
    scopes = {parsed["set"]: parsed["applies_to"] for parsed, _ in _plugin_sets(refs_dir)[0]}
    scopes[OVERLAY_SET] = overlay["applies_to"]
    groups = [{"set": name, "applies_to": scopes[name],
               "standards": [s for s in found["standards"] if s["set"] == name]}
              for name in found["sets"]]
    digest = found["digest"]
    mark = f"<!-- {EXPORT_MARK} digest={digest} crew={version} -->"
    out.update(digest=digest, crew=version)
    out["files"] = {f"{EXPORT_DIR}/{g['set']}.md": _render_set_file(g, mark) for g in groups}
    for target, rel in EXPORT_FILES.items():
        if target in targets:
            out["files"][rel] = _render_entry(rel, groups, mark)
    for rel, text in out["files"].items():
        if len(text) > EXPORT_MAX_CHARS:
            out["problems"].append(f"{rel} is {len(text)} characters, over the {EXPORT_MAX_CHARS} "
                                   "budget: it is refused, never truncated")
        existing, why = _read_text_file(root, rel)
        if why or (existing is not None and not _FILE_MARK_RE.match(existing.split("\n", 1)[0])):
            out["problems"].append(why or f"{rel} exists and is not crew's generated file (no "
                                   f"{EXPORT_MARK} marker); move or delete it first")
    if "agents" in targets:
        out["block"] = _render_block(groups, targets, mark)
        lines = len(out["block"].splitlines())
        existing, why = _read_text_file(root, AGENTS_REL)
        agents_text, problem = (None, why) if why else _splice(existing or "", out["block"])
        out["agents"] = agents_text or ""
        if existing and GENERATED_MARKER in existing:
            problem = (f"{AGENTS_REL} is crew-generated ({GENERATED_MARKER}), which the export "
                       "does not cover")
        elif existing and "\r" in existing:
            problem = f"{AGENTS_REL} has CRLF line endings; convert it to LF first"
        elif lines > AGENTS_BLOCK_MAX_LINES:
            problem = (f"the {AGENTS_REL} block is {lines} lines, over the "
                       f"{AGENTS_BLOCK_MAX_LINES}-line budget")
        elif GENERATED_MARKER in out["block"]:
            problem = f"the {AGENTS_REL} block would contain {GENERATED_MARKER}"
        if problem:
            out["problems"].append(problem)
    return out


def _owned_text(root, rel):
    """`_read_text_file`, except that a symlink or a non-regular entry is `(None, None)`:
    the export never wrote it, so it is neither read nor listed, and never touched. A path
    the export would write is refused earlier, by `_export_build`."""
    if _symlink_problem(root, rel):
        return None, None
    try:
        regular = stat.S_ISREG(os.lstat(os.path.join(root, *rel.split("/"))).st_mode)
    except OSError:
        regular = True   # absent or unreadable: `_read_text_file` says which
    return _read_text_file(root, rel) if regular else (None, None)


def _orphans(root, built):
    """[(kind, rel, problem)] for marked files and a marked block the current targets
    do not name. Unmarked files, symlinks and non-regular entries are never listed."""
    keep, found = set(built["files"]), []
    listing = [] if _symlink_problem(root, EXPORT_DIR) else _listdir(
        os.path.join(root, *EXPORT_DIR.split("/")))
    for rel in [f"{EXPORT_DIR}/{n}" for n in listing if n.endswith(".md")] + list(
            EXPORT_FILES.values()):
        text, why = _owned_text(root, rel)
        if why:
            found.append(("unreadable", rel, why))
        elif text is not None and _FILE_MARK_RE.match(text.split("\n", 1)[0]) and rel not in keep:
            found.append(("file", rel, f"{rel} is orphaned"))
    text, why = _owned_text(root, AGENTS_REL)
    block = _find_block(text) if text else (None, None, None)
    if text and "\r" in text and EXPORT_MARK in text and not built["block"]:
        why = f"{AGENTS_REL} has CRLF line endings and mentions {EXPORT_MARK}; convert it to LF"
    if why or block[2]:
        found.append(("unreadable", AGENTS_REL, why or block[2]))
    elif block[0] is not None and not built["block"]:
        found.append(("block", AGENTS_REL, f"{AGENTS_REL} carries an orphaned {EXPORT_MARK} block"))
    return found


def _listdir(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _why_stale(text, fresh, built):
    first = (text or "").split("\n", 1)[0]
    mark = _FILE_MARK_RE.match(first) or _START_RE.match(first)
    if mark and mark.group(1) != built["digest"]:
        return f"stale: recorded digest {mark.group(1)[:8]}, standards digest {built['digest'][:8]}"
    if mark and mark.group(2) != built["crew"]:
        return f"stale: written by crew {mark.group(2)}, this is crew {built['crew']}"
    return "differs from the standards (edited by hand?)" if mark else "carries no marker"


def export_check(root, refs_dir=None, crew=None):
    """(code, lines). 0 current or not opted in; 1 stale, missing, hand-edited,
    orphaned or refused. Writes nothing."""
    built = _export_build(root, refs_dir, crew)
    if built["problems"]:
        return 1, [f"standards export REFUSED: {p}" for p in built["problems"]]
    orphans = _orphans(root, built)
    bad = [f"{kind.upper()}: {why}" for kind, _, why in orphans]
    for rel, fresh in built["files"].items():
        text, why = _read_text_file(root, rel)
        if why or text is None or text != fresh:
            bad.append(f"{rel}: " + (why or "missing" if text is None
                                     else _why_stale(text, fresh, built)))
    if built["block"]:
        text, why = _read_text_file(root, AGENTS_REL)
        start, end, problem = _find_block(text or "")
        if why or problem or start is None or text[start:end] != built["block"]:
            bad.append(f"{AGENTS_REL}: " + (why or problem or ("missing the Code Review Rules block"
                       if start is None else _why_stale(text[start:], built["block"], built))))
    if not built["opted"] and not bad:
        return 0, [NOT_OPTED_IN]
    if bad:
        return 1, [f"standards export STALE: {line}" for line in bad] + [
            "regenerate: python3 \"$CLAUDE_PLUGIN_ROOT/hooks/scripts/crew_standards.py\" export "
            "--write --root ."]
    return 0, [f"standards export current (digest {built['digest'][:8]}, crew {built['crew']}, "
               f"{len(built['files']) + bool(built['block'])} outputs)"]


REPLACE_ATTEMPTS = 5   # Windows refuses a rename while another process holds the target open


def _write_atomic(path, text):
    """Complete or not at all: a temp file beside the target, flushed to disk, then
    os.replace, which keeps the target's mode and retries a sharing violation."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        mode = 0o644
    handle, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".crew-export-")
    try:
        with os.fdopen(handle, "wb") as fh:
            fh.write(text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(0.1)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def _contained(root, rel):
    real = os.path.realpath(os.path.dirname(os.path.join(root, *rel.split("/"))))
    top = os.path.realpath(root)
    try:
        return os.path.commonpath([real, top]) == top
    except ValueError:
        return False


def export_report(root, refs_dir=None, crew=None):
    """(code, lines) for --dry-run: per output its path, size, budget and digest."""
    built = _export_build(root, refs_dir, crew)
    if not built["opted"] and not built["problems"]:
        return 0, [NOT_OPTED_IN]
    lines = [f"{rel}: {len(text)} characters, budget {EXPORT_MAX_CHARS}, digest {built['digest']}"
             for rel, text in built["files"].items()]
    if built["block"]:
        lines.append(f"{AGENTS_REL} (block): {len(built['block'].splitlines())} lines, budget "
                     f"{AGENTS_BLOCK_MAX_LINES}, digest {built['digest']}")
    lines += [f"REFUSED: {p}" for p in built["problems"]]
    return (1 if built["problems"] else 0), lines


def export_write(root, refs_dir=None, crew=None):
    """(code, lines). Refuses with nothing written when anything is unknown, over budget or
    unsafe; otherwise writes each output complete-or-not-at-all and removes orphans."""
    built = _export_build(root, refs_dir, crew)
    if built["problems"]:
        return 1, [f"standards export REFUSED, nothing written: {p}" for p in built["problems"]]
    orphans = _orphans(root, built)
    if any(kind == "unreadable" for kind, _, _ in orphans):
        return 1, [f"standards export REFUSED, nothing written: {why}" for _, _, why in orphans]
    outputs = dict(built["files"])
    if built["agents"]:
        outputs[AGENTS_REL] = built["agents"]
    for rel in outputs:
        if not _contained(root, rel):
            return 1, [f"standards export REFUSED, nothing written: {rel} resolves outside "
                       "the repository"]
    lines = []
    try:
        for rel, text in outputs.items():
            _write_atomic(os.path.join(root, *rel.split("/")), text)
            lines.append(f"wrote {rel}")
        for kind, rel, _ in orphans:
            path = os.path.join(root, *rel.split("/"))
            if kind == "file":
                os.remove(path)
            else:
                text, _ = _read_text_file(root, rel)
                stripped, _ = _splice(text, None)
                if stripped.strip():
                    _write_atomic(path, stripped)
                else:
                    os.remove(path)
            lines.append(f"removed orphan {rel}")
    except OSError as exc:
        return 1, lines + [f"standards export FAILED part-way: {exc.__class__.__name__}: "
                           f"{exc.strerror or exc}; the lines above landed, rerun --write"]
    return 0, lines or [NOT_OPTED_IN]


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("sets", "init", "stamp", "proposals", "metric", "export"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket")
    parser.add_argument("--scratch")
    parser.add_argument("--round", type=int)
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--touch", action="store_true",
                        help="sets only: from the spec's Touch list, with no scope base")
    parser.add_argument("--write", action="store_true", help="export only: write the files")
    parser.add_argument("--check", action="store_true", help="export only: fail when stale")
    parser.add_argument("--dry-run", action="store_true", help="export only: report sizes")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.command == "export" and [args.write, args.check, args.dry_run].count(True) != 1:
        parser.error("export needs exactly one of --write, --check, --dry-run")
    if args.command not in ("metric", "export"):
        if not args.ticket:
            parser.error(f"{args.command} needs --ticket")
        try:
            crew_ticket.check_ticket(args.ticket)
        except crew_ticket.TicketError as exc:
            parser.error(str(exc))
    if args.command == "proposals" and (not args.scratch or args.round is None
                                        or args.round < 1):
        parser.error("proposals needs --scratch DIR and --round N (N >= 1)")
    if args.command == "sets":
        code, lines = _sets(root, args.ticket, touch=args.touch)
    elif args.command == "init":
        code, lines = init(root, args.ticket)
    elif args.command == "stamp":
        code, lines = stamp(root, args.ticket)
    elif args.command == "proposals":
        code, lines = proposals(root, args.ticket, os.path.abspath(args.scratch), args.round)
    elif args.command == "export":
        code, lines = (export_write if args.write else export_check if args.check
                       else export_report)(root)
    else:
        code, lines = metric(root, record=args.record)
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        stream.write(line + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
