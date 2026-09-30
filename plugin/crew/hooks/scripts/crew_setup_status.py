"""Which `done` setup phases `/crew:init` must re-verify before it resumes.

    python3 crew_setup_status.py [--root .] [--phases <phases.md>] [--plugin-json <plugin.json>]

`.crew/STATUS.md` says which setup phases were marked `done`; it did not say
against which crew, so a table marked under 0.20 read as finished under 1.0
and `/crew:init` had nothing to resume (T-0500, aws-ops report item 13). Each
`## Phase N` heading of `skills/crew-setup/phases.md` now carries
`<!-- phase-rev: X.Y.Z -->`, the crew version at which that phase's definition
last changed, and STATUS.md carries `crew: X.Y.Z`, the crew it was written
under. This compares the two and prints, for every `done` row only:

    phase N  <Phase>  done  definition changed since marked (marked A < phase-rev B) - re-verify
    phase N  <Phase>  done  could not tell when marked (no crew: line) - re-verify
    phase N  <Phase>  done  could not tell when marked (crew: X is not a version) - re-verify
    phase N  <Phase>  done  note may record a breakage ("<notes>") - re-verify

then `re-verify: phases N, ...` or `re-verify: none`, then the `crew:` line to
write on the next rewrite. A missing stamp is never read as current: it is
could-not-tell, on every `done` row.

The breakage check matches the Notes cell, case-insensitively, against
BREAKAGE_WORDS. It is a heuristic and says "may"; the rule in `phases.md` - a
`done` row whose note records a breakage is not `done` - is the authority.

Exit 0 nothing flagged (no STATUS.md included), 1 at least one row flagged,
3 could not tell (STATUS.md with no table or an unknown state, a phase heading
with no marker, a row naming a phase `phases.md` does not define, an
unreadable `phases.md`); 2 is argparse's usage error.

It writes nothing: no file is opened for writing, and bytecode writing is off.
The test suite snapshots every mtime in a fixture around a run.
"""

import sys

sys.dont_write_bytecode = True

# pylint: disable=wrong-import-position
import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PHASES_MD = os.path.join(HERE, os.pardir, os.pardir, "skills", "crew-setup", "phases.md")
PLUGIN_JSON = os.path.join(HERE, os.pardir, os.pardir, ".claude-plugin", "plugin.json")
STATES = ("todo", "in progress", "partial", "blocked", "done", "n/a")
BREAKAGE_WORDS = ("broken", "failing", "not working", "provider none", "unreachable", "never arrived",
                  "timed out", "no longer")
_HEADING_RE = re.compile(r"^## Phase (\d+)\b")
_REV_RE = re.compile(r"<!-- phase-rev: (\d+(?:\.\d+)*) -->")
_CREW_RE = re.compile(r"^crew:\s*(\S+)\s*$", re.M)
_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")
EXIT_CLEAN, EXIT_FLAGGED, EXIT_COULD_NOT_TELL = 0, 1, 3


class SetupStatusError(Exception):
    """The could-not-tell path; printed after `setup status: could not tell - `."""


def read_text(path):
    """The file's text, or None when it cannot be read. utf-8-sig drops a BOM."""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _vtuple(text):
    """Map "1.0.10" to (1, 0, 10); None when it is not a dotted version."""
    if text is None or not _VERSION_RE.match(text):
        return None
    return tuple(int(part) for part in text.split("."))


def phase_revs(phases_path):
    """{phase number: marker} for every `## Phase N` heading of phases.md."""
    text = read_text(phases_path)
    if text is None:
        raise SetupStatusError(f"phases.md unreadable at {phases_path}")
    lines = text.splitlines()
    revs = {}
    for i, line in enumerate(lines):
        heading = _HEADING_RE.match(line)
        if not heading:
            continue
        found = [m.group(1) for m in (_REV_RE.search(nxt) for nxt in lines[i + 1:i + 4]) if m]
        if not found:
            raise SetupStatusError(f'phases.md: "{line}" has no <!-- phase-rev: X.Y.Z --> within 3 lines')
        if len(found) > 1:
            raise SetupStatusError(f'phases.md: "{line}" carries two markers')
        revs[int(heading.group(1))] = found[0]
    return revs


def parse_status(text):
    """(crew stamp or None, rows) from STATUS.md's text."""
    table_at = next((i for i, line in enumerate(text.splitlines()) if line.startswith("|")), None)
    head = "\n".join(text.splitlines()[:table_at]) if table_at is not None else text
    stamp = _CREW_RE.search(head)
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        n, phase, state = int(cells[0]), cells[1], cells[2]
        notes = "|".join(cells[3:]).strip()
        if state not in STATES:
            raise SetupStatusError(f'.crew/STATUS.md: row {n} state "{state}" is not one of {", ".join(STATES)}')
        rows.append({"n": n, "phase": phase, "state": state, "notes": notes})
    if not rows:
        raise SetupStatusError(".crew/STATUS.md: no | # | Phase | State | Notes | table")
    return (stamp.group(1) if stamp else None), rows


def current_version(plugin_json_path):
    """The installed plugin's version, or None when the manifest cannot be read."""
    text = read_text(plugin_json_path)
    try:
        version = json.loads(text)["version"] if text is not None else None
    except (ValueError, KeyError, TypeError):
        return None
    return version if isinstance(version, str) and version else None


def flags_for(row, marked, revs):
    """The reasons a `done` row must be re-verified, in reporting order."""
    if row["state"] != "done":
        return []
    if row["n"] not in revs:
        raise SetupStatusError(f".crew/STATUS.md: row {row['n']} names a phase phases.md does not define")
    reasons = []
    rev = revs[row["n"]]
    if marked is None:
        reasons.append("could not tell when marked (no crew: line)")
    elif _vtuple(marked) is None:
        reasons.append(f"could not tell when marked (crew: {marked} is not a version)")
    elif _vtuple(marked) < _vtuple(rev):
        reasons.append(f"definition changed since marked (marked {marked} < phase-rev {rev})")
    if any(word in row["notes"].lower() for word in BREAKAGE_WORDS):
        reasons.append(f'note may record a breakage ("{row["notes"]}")')
    return reasons


def _current_line(plugin_json):
    cur = current_version(plugin_json)
    if cur is None:
        return (f"current crew: could not tell (plugin.json unreadable at {plugin_json})"
                " - write the installed crew version as crew: <version>")
    return f"current crew: {cur} - write `crew: {cur}` when rewriting .crew/STATUS.md"


def report(root, phases_path=PHASES_MD, plugin_json=PLUGIN_JSON):
    """(output lines, exit code). Raises SetupStatusError when it cannot tell."""
    status_path = os.path.join(root, ".crew", "STATUS.md")
    if not os.path.exists(status_path):
        return ["setup status: no .crew/STATUS.md - nothing marked; /crew:init starts at Phase 0",
                _current_line(plugin_json)], EXIT_CLEAN
    revs = phase_revs(phases_path)
    text = read_text(status_path)
    if text is None:
        raise SetupStatusError(".crew/STATUS.md exists but cannot be read")
    marked, rows = parse_status(text)
    if marked is None:
        lines = ["setup status  .crew/STATUS.md  no crew: line - could not tell when any row was marked"]
    else:
        lines = [f"setup status  .crew/STATUS.md  marked against crew {marked}"]
    flagged = []
    for row in rows:
        for reason in flags_for(row, marked, revs):
            lines.append(f"phase {row['n']}  {row['phase']}  done  {reason} - re-verify")
            if row["n"] not in flagged:
                flagged.append(row["n"])
    lines.append("re-verify: phases " + ", ".join(str(n) for n in flagged) if flagged else "re-verify: none")
    lines.append(_current_line(plugin_json))
    return lines, EXIT_FLAGGED if flagged else EXIT_CLEAN


def main(argv=None):
    parser = argparse.ArgumentParser(description="Which done setup phases /crew:init must re-verify.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--phases", default=PHASES_MD)
    parser.add_argument("--plugin-json", default=PLUGIN_JSON)
    args = parser.parse_args(argv)
    try:
        lines, code = report(args.root, args.phases, args.plugin_json)
    except SetupStatusError as exc:
        line = f"setup status: could not tell - {exc}"
        print(line)
        print(line, file=sys.stderr)
        return EXIT_COULD_NOT_TELL
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
