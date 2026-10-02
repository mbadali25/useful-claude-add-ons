"""The recurring-findings checklist: the defect classes earlier reviews kept
finding, each keyed by path globs, printed for the paths a change touches
(L-0575).

THE DATA is `skills/crew-qa-standards/references/recurring-findings.md`,
curated and tracked, so every machine prints the same list. A section is

    ## RF-NN <title>
    applies-to: ["<glob>", ...]
    seen: <one line: the measured count and the related standards>
    - <probe>            (one to MAX_PROBES of these)

Text outside the sections (the introduction, the provenance) is never
printed. Sections stay in the file's order, which is its priority order: past
MAX_LINES the block drops whole sections from the end and says which.

TWO READERS, ONE BLOCK.
  - The implementer: `recurring_findings.py --root . --ticket <id>` matches the
    spec's Touch entries (`/crew:implement` step 2). A Touch entry may be a
    glob, so it is matched by OVERLAP with each section's globs, on purpose
    conservatively: two wildcard segments are taken to overlap, and an entry
    with no wildcard also covers everything under it, as
    `crew_ticket.path_matches` reads a Touch directory.
  - The reviewer: `review_block(root, manifest)` matches the bundle's changed
    files (`crew_standards.changed_files`), concrete paths, through
    `crew_ticket.glob_match`, the Touch matcher.

UNKNOWN STAYS UNKNOWN (GEN-01). A data file that cannot be read prints
`UNREADABLE:`; a malformed section prints `PROBLEM:` and the sections that did
parse are still listed. Paths that cannot be read (no spec, no Touch entry, a
manifest whose file lists are unusable) print `UNKNOWN:` and list EVERY
section: a list that cannot be scoped is over-included, never emptied. A known
empty match says so in one line.

CLI: --root R (--ticket T | --paths P [P ...]) [--paths ...]
Exit codes: 0 everything read; 1 something was UNKNOWN, UNREADABLE or a
PROBLEM (the block is still printed); 2 usage.
"""
import argparse
import fnmatch
import functools
import json
import os
import re
import sys

import crew_ticket

MAX_LINES = 60
MAX_PROBES = 4
NONE_KEYED = "No recurring-finding class is keyed to these paths."
FILE_KEYS = ("committed_files", "staged_files", "unstaged_files", "untracked_files")
DATA_REL = "skills/crew-qa-standards/references/recurring-findings.md"

_SECTION_RE = re.compile(r"^## (RF-\d{2}) (\S.*?)\s*$")
_WILD = re.compile(r"[*?\[]")
_WILD_TOKEN = re.compile(r"\[[^\]]*\]|[*?]")


def data_path():
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         os.pardir, os.pardir, *DATA_REL.split("/")))


# ---- parsing --------------------------------------------------------------------

def _globs(value):
    try:
        globs = json.loads(value)
    except ValueError:
        return None
    if not isinstance(globs, list) or not globs or not all(
            isinstance(g, str) and g.strip() for g in globs):
        return None
    return globs


def parse(path):
    """(entries, problems). An entry is {"id", "title", "applies_to", "seen",
    "probes", "line"}. A section with a problem is left out and named; the
    others are kept."""
    label = os.path.basename(path)
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except FileNotFoundError:
        return [], [f"UNREADABLE: {path} does not exist"]
    except (OSError, UnicodeDecodeError) as exc:
        return [], [f"UNREADABLE: {path}: {exc.__class__.__name__}: {exc}"]
    sections, body = [], None
    for number, line in enumerate(text.lstrip("﻿").replace("\r\n", "\n").split("\n"), 1):
        if line.startswith("## "):
            match = _SECTION_RE.match(line)
            body = [] if match else None
            sections.append({"id": match.group(1), "title": match.group(2), "line": number,
                             "body": body} if match else {"bad": line.strip(), "line": number})
        elif body is not None:
            body.append(line)
    entries, problems, seen_ids = [], [], set()
    for section in sections:
        where = f"{label}:{section['line']}"
        if "bad" in section:
            if section["bad"] != "## Provenance":
                problems.append(f"PROBLEM: {where}: heading {section['bad'][:60]!r} is not "
                                "'## RF-NN <title>'")
            continue
        entry, why = _entry(section)
        if section["id"] in seen_ids:
            why = why or f"{section['id']} is defined twice"
        seen_ids.add(section["id"])
        if why:
            problems.append(f"PROBLEM: {where}: {section['id']}: {why}")
        else:
            entries.append(entry)
    if not entries:
        problems.append(f"PROBLEM: {label}: no valid '## RF-NN' section")
    return entries, problems


def _entry(section):
    """(entry, None) or (None, why). Every non-blank line is one of the three
    fields: a stray line is how a mistyped label (`Applies-to:`) or a probe
    written as `* ...` would otherwise vanish without a word."""
    fields, probes = {}, []
    for offset, line in enumerate(section["body"], 1):
        label = line.partition(":")[0]
        if line.startswith("-") and not line[1:].strip():
            return None, f"line {section['line'] + offset} is an empty probe"
        if line.startswith("- "):
            probes.append(line[2:].strip())
        elif label in ("applies-to", "seen") and ":" in line:
            if label in fields:
                return None, f"repeats {label}"
            fields[label] = line.partition(":")[2].strip()
        elif line.strip():
            return None, (f"line {section['line'] + offset} is not applies-to, seen or a "
                          f"'- ' probe: {line.strip()[:60]!r}")
    if "applies-to" not in fields:
        return None, "no applies-to line"
    applies = _globs(fields["applies-to"])
    if applies is None:
        return None, "applies-to is not a JSON list of non-empty globs"
    if not fields.get("seen"):
        return None, "no seen line"
    if not probes or len(probes) > MAX_PROBES:
        return None, f"{len(probes)} probes; 1 to {MAX_PROBES} are allowed"
    return {"id": section["id"], "title": section["title"], "applies_to": applies,
            "seen": fields["seen"], "probes": probes, "line": section["line"]}, None


# ---- matching -------------------------------------------------------------------

def _segments(text):
    return tuple(s for s in text.replace("\\", "/").split("/") if s not in ("", "."))


def overlap(a, b):
    """Whether glob `a` and glob `b` can name a common path. Conservative: two
    segments that both carry a wildcard are taken to overlap."""
    left, right = _segments(a), _segments(b)

    @functools.lru_cache(maxsize=None)
    def walk(i, j):
        if i == len(left) and j == len(right):
            return True
        if i < len(left) and left[i] == "**":
            return walk(i + 1, j) or (j < len(right) and walk(i, j + 1))
        if j < len(right) and right[j] == "**":
            return walk(i, j + 1) or (i < len(left) and walk(i + 1, j))
        if i == len(left) or j == len(right):
            return False
        x, y = left[i], right[j]
        return _segment_overlap(x, y) and walk(i + 1, j + 1)

    return walk(0, 0)


def _segment_overlap(x, y):
    """One segment of each glob. A literal side decides by fnmatch. Two
    wildcard sides overlap unless their literal heads, or their literal tails,
    rule it out (`*.py` and `*.ps1` cannot name one file); otherwise they are
    taken to overlap, the conservative answer."""
    if not _WILD.search(x) or not _WILD.search(y):
        return fnmatch.fnmatch(x, y) or fnmatch.fnmatch(y, x)
    heads = [_WILD_TOKEN.split(s, 1)[0] for s in (x, y)]
    tails = [_WILD_TOKEN.split(s)[-1] for s in (x, y)]
    head_ok = heads[0].startswith(heads[1]) or heads[1].startswith(heads[0])
    tail_ok = tails[0].endswith(tails[1]) or tails[1].endswith(tails[0])
    return head_ok and tail_ok


def _names_a_directory(entry, root):
    """A wildcard-free Touch entry covers what is under it, as
    `crew_ticket.path_matches` reads it, unless it exists in `root` as a
    regular file: only a file proven on disk is kept narrow, so a new
    directory (`docs/v1.0`) and anything that cannot be checked are covered."""
    if _WILD.search(entry):
        return False
    if root:
        try:
            return not os.path.isfile(os.path.join(root, *_segments(entry)))
        except (OSError, ValueError):
            return True
    return True


def matches(path, glob, touch=False, root=None):
    """A concrete changed path through the Touch matcher; a Touch entry by
    overlap, and one naming a directory also as everything under it."""
    path = path.replace("\\", "/")
    if not touch:
        return crew_ticket.glob_match(path, glob)
    if overlap(path, glob):
        return True
    return _names_a_directory(path, root) and overlap(path.rstrip("/") + "/**", glob)


def select(entries, paths, touch=False):
    return [e for e in entries
            if any(matches(p, g, touch) for p in paths for g in e["applies_to"])]


# ---- rendering ------------------------------------------------------------------

def _entry_lines(entry):
    return ([f"{entry['id']} {entry['title']} (seen: {entry['seen']})"]
            + [f"  - {probe}" for probe in entry["probes"]])


def render(header, entries, notes=()):
    """`header` lines, then `notes` (UNKNOWN/UNREADABLE/PROBLEM), then whole
    entries while they fit; never more than MAX_LINES lines in all. Notes past
    their share are counted, not dropped silently; entries past the cap are
    named by id. With a data note present, an empty selection is never
    reported as "none applies": the section that could not be read may have
    been the one that did."""
    out = list(header)
    room = MAX_LINES - len(out) - 2
    out += list(notes[:room])
    if len(notes) > room:
        out[-1] = f"[... {len(notes) - room + 1} more notes not shown]"
    if not entries:
        if any(n.startswith(("UNREADABLE:", "PROBLEM:")) for n in notes):
            out.append("No class could be read that is keyed to these paths, and the checklist "
                       "has unreadable parts (above), so whether one applies is not known.")
        else:
            out.append(NONE_KEYED)
        return out
    for index, entry in enumerate(entries):
        lines = _entry_lines(entry)
        reserve = 1 if index + 1 < len(entries) else 0
        if len(out) + len(lines) + reserve > MAX_LINES:
            dropped = [e["id"] for e in entries[index:]]
            out.append(f"[TRUNCATED at {MAX_LINES} lines: {', '.join(dropped)} not shown; "
                       f"read them in plugin/crew/{DATA_REL}.]")
            return out
        out += lines
    return out


def _load(data):
    return parse(data or data_path())


def manifest_files(manifest):
    """(files, None) or (None, why). Every one of the four lists must be a
    list of non-blank strings: one bad element makes the scope unknown, where
    `crew_standards.changed_files` would drop it and narrow the scope."""
    if not isinstance(manifest, dict):
        return None, "the manifest is not a JSON object"
    files = set()
    for key in FILE_KEYS:
        value = manifest.get(key)
        if not isinstance(value, list):
            return None, f"the manifest has no {key} list"
        for item in value:
            if not isinstance(item, str) or not item.strip():
                return None, f"the manifest's {key} holds {item!r}, not a path"
            files.add(item)
    return sorted(files), None


# ---- the two readers ------------------------------------------------------------

REVIEW_HEADER = (
    "== Recurring review findings for these paths (appendix) ==",
    "Defect classes earlier reviews kept finding on paths like the ones this diff changes. Check "
    "the diff for each; an item the diff does not touch is not a finding.",
    "This list does not bound the review: report a defect outside it the same way.",
)


def review_block(root, manifest, data=None):
    """The shared review prompt's block, from the manifest's changed files.
    `root` is unused: the data is the plugin's own (module docstring)."""
    del root
    entries, notes = _load(data)
    files, why = manifest_files(manifest)
    if why:
        return render(REVIEW_HEADER, entries,
                      notes + [f"UNKNOWN: {why}; which classes apply is not known, so every "
                               "one is listed."])
    return render(REVIEW_HEADER, select(entries, files), notes)


def implementer_block(root, ticket, paths=(), data=None):
    """(lines, complete): the block for the spec's Touch entries plus `paths`."""
    entries, notes = _load(data)
    header = [f"== Recurring review findings for {ticket or 'these paths'} ==",
              "Earlier reviews kept finding these on paths like the ones you will touch. Treat "
              "each as a check to run on your change before /crew:review."]
    touch, unknown = [], None
    if ticket:
        spec = os.path.join(root, ".work", "tickets", crew_ticket.check_ticket(ticket), "spec.md")
        try:
            with open(spec, encoding="utf-8", newline="") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            unknown = f"UNKNOWN: {spec} cannot be read ({exc.__class__.__name__})"
        else:
            touch, why = crew_ticket.parse_touch(text)
            if why:
                unknown = f"UNKNOWN: the spec's Touch list: {'; '.join(why)}"
    if unknown:
        notes = notes + [unknown + "; every class is listed."]
        return render(header, entries, notes), False
    chosen = [e for e in entries
              if any(matches(t, g, touch=True, root=root) for t in touch for g in e["applies_to"])
              or any(matches(p, g) for p in paths for g in e["applies_to"])]
    return render(header, chosen, notes), not notes


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket")
    parser.add_argument("--paths", nargs="+", default=[])
    parser.add_argument("--data", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.ticket and not args.paths:
        parser.error("name --ticket or --paths")
    try:
        lines, complete = implementer_block(os.path.abspath(args.root), args.ticket,
                                            args.paths, args.data)
    except crew_ticket.TicketError as exc:
        print(f"recurring-findings: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
