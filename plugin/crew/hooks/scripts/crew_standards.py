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
`crew_ticket.glob_match` against the change's files; `"**"` applies always.
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

CLI: sets | init | stamp  --root R --ticket T
     proposals --root R --ticket T --scratch S --round N
     metric --root R [--record]
Exit codes: 0 ok; 1 refused (each problem named); 2 usage.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import statistics
import sys

import crew_ticket

OVERLAY_REL = ".crew/standards.md"
OVERLAY_SET = "REPO"
SELFCHECK_NAME = "selfcheck.md"
FIELDS = ("Rule", "Why", "Applies when", "Self-check", "Earned by", "Change sets", "Source")
PLUGIN_FIELDS = ("Rule", "Why", "Applies when", "Self-check", "Earned by", "Change sets")
OVERLAY_FIELDS = ("Rule", "Self-check")
FRONT_KEYS = ("set", "applies-to")
STATUSES = ("addressed", "n/a")
PLACEHOLDERS = ("", "-", "--", "?", "tbd", "todo", "n/a", "na", "none", "...")

_SET_RE = re.compile(r"^[A-Z]{2,6}$")
_ID_RE = re.compile(r"^[A-Z]{2,6}-\d{2}$")
_STANDARD_RE = re.compile(r"^## ([A-Z]{2,6}-\d{2}) (\S.*?)\s*$")
_SUPPLEMENTS_RE = re.compile(r"^## Supplements (\S+)\s*$")
_FIELD_RE = re.compile(r"^\*\*(" + "|".join(re.escape(f) for f in FIELDS) + r")\.\*\*\s?(.*)$")
_STAMP_RE = re.compile(r"^<!-- stamp: bundle=([0-9a-f]{64}) standards=([0-9a-f]{64}) "
                       r"base=([0-9a-f]{40}) -->$")
_ROW_RE = re.compile(r"^\|(.*)\|\s*$")
_STD_TOKEN_RE = re.compile(r"\bstd:[0-9a-f]{8}\b")


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


def _front_matter(lines, label):
    """(meta, body_start, problems)."""
    if not lines or lines[0].strip() != "---":
        return {}, 0, [f"{label}: no front matter (the first line must be ---)"]
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, 0, [f"{label}: front matter is not closed with ---"]
    meta, problems = {}, []
    for number, line in enumerate(lines[1:end], 2):
        key, sep, value = line.partition(":")
        key = key.strip()
        if not sep or key not in FRONT_KEYS:
            problems.append(f"{label}: front matter line {number} is not one of "
                            f"{', '.join(FRONT_KEYS)}: {line.strip()[:60]!r}")
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


def parse_set(path, label=None, required=PLUGIN_FIELDS):
    """(set_dict, problems, raw_bytes). A set_dict is {"set", "applies_to",
    "standards": [...], "supplements": {id: [text]}, "path"}; None when the
    file could not be read (problems then says why, or is ["absent"])."""
    label = label or os.path.basename(path)
    raw, why = _read_bytes(path)
    if raw is None:
        return None, [why if why == "absent" else f"{label}: {why}"], None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, [f"{label}: not UTF-8 ({exc.reason} at byte {exc.start})"], raw
    text = text.lstrip("﻿")
    lines = text.replace("\r\n", "\n").split("\n")
    meta, start, problems = _front_matter(lines, label)
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
             "supplements": supplements, "path": path}, problems, raw)


# ---- the effective set ----------------------------------------------------------

def _applies(globs, changed_files):
    if "**" in globs:
        return True
    return any(crew_ticket.glob_match(path.replace("\\", "/"), glob)
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


def effective_set(root, changed_files, refs_dir=None):
    """{"standards", "overlay": present|absent|unknown, "digest", "problems",
    "sets", "overlay_problem"}. The generic set always; each stack set whose
    applies-to matches a changed file; the overlay when present."""
    refs_dir = refs_dir or references_dir()
    changed_files = list(changed_files or [])
    plugin, problems = _plugin_sets(refs_dir)
    plugin_ids = {s["id"] for parsed, _ in plugin for s in parsed["standards"]}
    digest = hashlib.sha256()
    standards, sets = [], []
    for parsed, raw in plugin:
        if not _applies(parsed["applies_to"], changed_files):
            continue
        sets.append(parsed["set"])
        standards += [dict(s, source=f"references/{os.path.basename(parsed['path'])}")
                      for s in parsed["standards"]]
        digest.update(parsed["set"].encode() + b"\0" + raw + b"\0")

    overlay_path = os.path.join(root, *OVERLAY_REL.split("/"))
    parsed, found, raw = parse_set(overlay_path, OVERLAY_REL, required=OVERLAY_FIELDS)
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
    return os.path.join(root, ".work", "tickets", crew_ticket.check_ticket(ticket),
                        SELFCHECK_NAME)


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
    raw, why = _read_bytes(selfcheck_path(root, ticket))
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


def _has_scope_entry(root, ticket):
    """True when `.crew/.scope-base` holds an entry for `ticket` that
    `scope_base.record` would keep, so naming `--record` would change nothing."""
    import scope_base  # pylint: disable=import-outside-toplevel
    entry = (scope_base.read_record(root) or {}).get(ticket)
    return isinstance(entry, dict) and isinstance(entry.get("base"), str) and bool(entry["base"])


def _scope(root, ticket):
    """(base, manifest, problems, note): the base `scope_base.py --base`
    resolves for the ticket and review_patch.compute's manifest for it -- the
    same function on the same base /crew:review bundles with (GEN-07).

    A recorded start is used as recorded. A record that exists but cannot be
    used (its commit is gone, or no longer an ancestor of HEAD) resolves to the
    merge-base with the default branch, which is what /crew:review bundles
    against too; that base is used and `note` says "(fallback)" with resolve's
    reason, for every line derived from it (GEN-01). `--record` keeps an
    existing entry, so it is named only when there is no entry; a base resolved
    to HEAD alone (no default branch) is refused."""
    import review_patch  # pylint: disable=import-outside-toplevel
    import scope_base  # pylint: disable=import-outside-toplevel
    base, source, why = scope_base.resolve(root, ticket)
    note = None
    has_entry = _has_scope_entry(root, ticket)
    if source == "merge-base" and base and has_entry:
        note = f"(fallback) {why}"
    elif source not in (scope_base.RECORDED, "record-fallback") or not base:
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
            raise ValueError(f"the manifest has no {key} list")
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
    path = selfcheck_path(root, ticket)
    if not _create_exclusive(path, selfcheck_template(ticket, found)):
        return 1, [f".work/tickets/{ticket}/{SELFCHECK_NAME} already exists; left unchanged"]
    return 0, [_noted(f"self-check: wrote .work/tickets/{ticket}/{SELFCHECK_NAME} with "
                      f"{len(found['standards'])} rows", base, note), summary_line(found)]


def stamp(root, ticket, refs_dir=None):
    """(exit_code, lines). Refuses on any problem; writes nothing then. The
    rows are validated from one read and those same bytes are written back
    with the stamp; a record that changed during the compute is refused, not
    stamped (GEN-03: the authorizing fact is read once)."""
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
    path = selfcheck_path(root, ticket)
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

def proposals(root, ticket, scratch, round_no):
    """(exit_code, lines). One section per BLOCK/FIX line of the round's
    out.txt, verbatim, for the owner to rule on. Writes only the proposals
    file, with an exclusive create; never a set file."""
    import review_verdict  # pylint: disable=import-outside-toplevel
    source = os.path.join(scratch, "out.txt")
    raw, why = _read_bytes(source)
    if raw is None:
        return 1, [f"proposals: {source} {'does not exist' if why == 'absent' else why}"]
    text = raw.decode("utf-8", errors="replace")
    findings = [line for line in review_verdict.parse(text, 0)["findings"]
                if not line.startswith("NIT|")]
    name = f"standards-proposals-r{round_no}.md"
    path = os.path.join(root, ".work", "tickets", crew_ticket.check_ticket(ticket), name)
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


def metric_summary(text):
    """First-round BLOCK+FIX per ticket, before (no std: token) and after."""
    import crew_metrics  # pylint: disable=import-outside-toplevel
    import crew_migrate  # pylint: disable=import-outside-toplevel
    rows, _ = crew_migrate.metrics_rows(text or "")
    per = {"before": {}, "after": {}}
    unknown_round = unscored = 0
    for index, row in enumerate(rows):
        if row["reviewRound"] == crew_migrate.UNKNOWN:
            unknown_round += 1
            continue
        if row["reviewRound"] != 1:
            continue
        if crew_migrate.UNKNOWN in (row["block"], row["fix"]):
            unscored += 1
            continue
        side = "after" if _STD_TOKEN_RE.search(row["reviewer"] or "") else "before"
        key = row["ticketId"] if row["ticketId"] != crew_migrate.UNKNOWN else ("row", index)
        per[side][key] = per[side].get(key, 0) + row["block"] + row["fix"]
    floor = crew_metrics.MIN_BASELINE_KNOWN
    return {"before": _side(list(per["before"].values()), floor),
            "after": _side(list(per["after"].values()), floor),
            "unknown_round": unknown_round, "unscored": unscored, "floor": floor}


def _side_text(name, side, floor):
    if not side["n"]:
        return f"{name} median n/a (n=0, not enough data)"
    enough = "" if side["enough"] else f", not enough data: fewer than {floor} tickets"
    return f"{name} median {side['median']} mean {side['mean']} (n={side['n']}{enough})"


def metric(root, record=False, today=None):
    """(exit_code, lines). --record appends one line with no `|`, so neither
    crew_state.read_metrics nor crew_migrate.metrics_rows reads it as a row."""
    path = os.path.join(root, ".crew", "metrics.md")
    raw, why = _read_bytes(path)
    if raw is None and why != "absent":
        return 1, [f"standards-metric: .crew/metrics.md {why}"]
    text = raw.decode("utf-8", errors="replace") if raw is not None else ""
    found = metric_summary(text)
    floor = found["floor"]
    lines = ["standards-metric: first-round BLOCK+FIX per ticket (.crew/metrics.md)",
             "  " + _side_text("before (no std: token)", found["before"], floor),
             "  " + _side_text("after (std: token)", found["after"], floor),
             f"  unknown-round rows {found['unknown_round']} (on neither side); first-round rows "
             f"with no BLOCK/FIX count {found['unscored']}"]
    if record:
        today = today or datetime.date.today().isoformat()
        line = (f"standards-metric {today}: first-round BLOCK+FIX "
                f"{_side_text('before', found['before'], floor)}, "
                f"{_side_text('after', found['after'], floor)}, "
                f"unknown-round rows {found['unknown_round']}")
        line = line.replace("|", "/")
        prefix = "" if not text or text.endswith("\n") else "\n"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(prefix + line + "\n")
        lines.append(f"standards-metric: recorded in .crew/metrics.md: {line}")
    return 0, lines


# ---- CLI ---------------------------------------------------------------------------

def _sets(root, ticket, refs_dir=None):
    base, manifest, problems, note = _scope(root, ticket)
    if problems:
        return 1, problems
    found = effective_set(root, changed_files(manifest), refs_dir)
    lines = [_noted(summary_line(found), base, note)]
    lines += [f"{s['id']} {s['name']} ({s['source']})" for s in found["standards"]]
    lines += [f"PROBLEM: {p}" for p in found["problems"]]
    return (1 if found["problems"] else 0), lines


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("sets", "init", "stamp", "proposals", "metric"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket")
    parser.add_argument("--scratch")
    parser.add_argument("--round", type=int)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.command != "metric":
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
        code, lines = _sets(root, args.ticket)
    elif args.command == "init":
        code, lines = init(root, args.ticket)
    elif args.command == "stamp":
        code, lines = stamp(root, args.ticket)
    elif args.command == "proposals":
        code, lines = proposals(root, args.ticket, os.path.abspath(args.scratch), args.round)
    else:
        code, lines = metric(root, record=args.record)
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        stream.write(line + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
