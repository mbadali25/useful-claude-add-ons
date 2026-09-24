"""Write the ticket-contract block of the shared review prompt.

`/crew:review` builds ONE prompt that every reviewer reads byte-for-byte; this
script writes the part of it that is about the ticket rather than the diff:

  - the bundle parts, in order, and the READ acknowledgement each needs;
  - the ticket's spec sections -- Intent, Exclusions, Evidence, Unknowns,
    Acceptance checks -- from `.work/tickets/<id>/spec.md` (or, for a
    files-mode ticket with no spec.md yet, `.work/tickets/<id>.md`);
  - the plan, `.work/tickets/<id>/plan.md`, in full;
  - the test receipts: the verify gate's last verified commit
    (`.crew/.verify-verified-at`) against HEAD, and every rule its record
    (`.crew/.verify-gate.record.json`) still lists as NOT VERIFIED.

Anything missing is written as `MISSING: ...` naming the path looked at. A
reviewer handed a prompt with no acceptance section cannot tell "this ticket
has none" from "nobody passed it"; a line saying which is the difference.

  - web tests, only in a Playwright repository: the trace zips and axe
    results `review_patch.py` listed in the manifest (bounded there), and the
    healer-skip rows `webtest_guard.py skips` wrote to
    `.work/tickets/<id>/webtest/findings.json`. Each open row is handed to the
    reviewer as a FINDING to carry, never as context to weigh. Every row is
    handed over: past WEBTEST_FINDINGS_MAX the full list goes to
    `webtest-findings.txt` beside `--out`, with its own READ acknowledgement.

The codemap landmines are gathered by `review.md` itself (its existing step)
and are not repeated here.

CLI: --root <repo> --ticket <id> --manifest <json> --out <file>
"""
import argparse
import json
import os
import re
import subprocess
import sys

SPEC_SECTIONS = ("Intent", "Exclusions", "Evidence", "Unknowns", "Acceptance checks")
WEBTEST_FINDINGS_MAX = 50
WEBTEST_FINDINGS_FILE = "webtest-findings.txt"
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def sections(markdown):
    """{lowercased heading: body} for every markdown heading at any level. A
    body runs to the next heading of the same or a higher level, so nested
    subheadings stay inside it. The first occurrence of a name wins."""
    lines = markdown.splitlines()
    heads = [(i, len(m.group(1)), m.group(2).strip().lower())
             for i, m in ((i, _HEADING.match(line)) for i, line in enumerate(lines)) if m]
    found = {}
    for pos, (index, level, name) in enumerate(heads):
        stop = next((j for j, lvl, _ in heads[pos + 1:] if lvl <= level), len(lines))
        found.setdefault(name, "\n".join(lines[index + 1:stop]).strip())
    return found


def _bundle_block(manifest):
    parts = manifest.get("parts") or []
    out = [f"== Bundle: {len(parts)} part(s), {manifest.get('patch_bytes', 0)} bytes, "
           f"sha256 {manifest.get('bundle_sha256')} ==",
           "Read EVERY part below, in order, in full. After reading each one, output",
           "READ|<its file name> on its own line. A part with no READ line makes the",
           "review INCOMPLETE."]
    out += [f"  {p['path']}" for p in parts]
    out.append(f"Manifest (file categories, renames, modes, binaries, submodules): "
               f"{manifest.get('manifest_path', 'manifest.json')}")
    for key, label in (("renames", "renamed"), ("mode_changes", "mode changed"),
                       ("binary_files", "binary (marker only, blob ids in the patch)"),
                       ("submodules", "submodule")):
        if manifest.get(key):
            out.append(f"  {label}: {', '.join(manifest[key])}")
    return out


def _spec_block(root, ticket):
    ticket_dir = os.path.join(root, ".work", "tickets", ticket)
    spec_path = os.path.join(ticket_dir, "spec.md")
    text = _read(spec_path)
    source = spec_path
    if text is None:
        legacy = os.path.join(root, ".work", "tickets", ticket + ".md")
        text = _read(legacy)
        source = legacy if text is not None else None
    out = [f"== Ticket {ticket}: spec =="]
    if text is None:
        out.append(f"MISSING: no spec at {spec_path} (nor .work/tickets/{ticket}.md). "
                   "Review against the diff alone and say that you had no spec.")
        return out
    out.append(f"(from {os.path.relpath(source, root)})")
    found = sections(text)
    for name in SPEC_SECTIONS:
        body = found.get(name.lower())
        if body:
            out += [f"-- {name} --", body]
        else:
            out.append(f"-- {name} -- MISSING: no '{name}' section in "
                       f"{os.path.relpath(source, root)}")
    return out


def _plan_block(root, ticket):
    path = os.path.join(root, ".work", "tickets", ticket, "plan.md")
    text = _read(path)
    if text is None or not text.strip():
        return ["== Plan ==", f"MISSING: no plan at {os.path.relpath(path, root)}."]
    return ["== Plan ==", text.strip()]


def _head(root):
    try:
        return subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=False, timeout=30,
                              stdin=subprocess.DEVNULL).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _receipts_block(root, manifest):
    out = ["== Test receipts (verify gate) =="]
    marker = os.path.join(root, ".crew", ".verify-verified-at")
    verified = (_read(marker) or "").strip()
    head = _head(root)
    if not verified:
        out.append("MISSING: no .crew/.verify-verified-at -- the verify gate has not recorded "
                   "a clean pass in this checkout.")
    elif verified == head and not manifest.get("dirty"):
        out.append(f"Last clean verify pass: {verified[:12]} = HEAD, tree clean.")
    else:
        out.append(f"Last clean verify pass: {verified[:12]}; HEAD is {head[:12]}"
                   f"{', tree dirty' if manifest.get('dirty') else ''}. Changes after that "
                   "pass have NOT been through the gate.")
    record_path = os.path.join(root, ".crew", ".verify-gate.record.json")
    raw = _read(record_path)
    if raw is None:
        out.append("MISSING: no .crew/.verify-gate.record.json (no per-rule record).")
        return out
    try:
        rules = json.loads(raw).get("rules")
    except (ValueError, AttributeError):
        rules = None
    if not isinstance(rules, dict):
        out.append("UNREADABLE: .crew/.verify-gate.record.json does not parse; which rules "
                   "are unverified is UNKNOWN.")
    elif not rules:
        out.append("Per-rule record: no rule is outstanding.")
    else:
        for info in rules.values():
            if isinstance(info, dict):
                out.append(f"NOT VERIFIED: {info.get('label', '?')}: {info.get('reason', '')}")
    return out


def _artifact_lines(listing):
    out = ["Open these; they are not in the patch. A trace opens with "
           "`npx playwright show-trace <zip>`."]
    for kind, label in (("traces", "TRACE"), ("axe", "AXE")):
        rows = listing.get(kind) or []
        if not rows:
            out.append(f"MISSING: no {label.lower()} artefact under {listing.get('root')}/ -- "
                       "say that you reviewed without it.")
        out += [f"{label}: {r['path']} ({r['bytes']} bytes, sha256 {r['sha256'][:12]})"
                for r in rows]
        omitted = (listing.get("omitted") or {}).get(kind)
        if omitted:
            out.append(f"  ... {omitted} older {label.lower()} artefact(s) not listed "
                       f"(limit {listing.get('limit')})")
    return out


def _finding_row(row):
    tag = "EXCLUDED" if row.get("excluded") else "FINDING"
    return (f"{tag}|{row.get('severity', 'FIX')}|{row.get('kind', 'healer-skip')}|"
            f"{row.get('path')}:{row.get('line')}|{row.get('text', '')}")


def _write_file(path, text):
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _webtest_block(root, ticket, manifest, out_dir=None):
    """Empty when this is not a Playwright repository and no skip check ran.
    Every row reaches the reviewer: up to WEBTEST_FINDINGS_MAX inline, and
    past that ALL of them in `<out_dir>/webtest-findings.txt`, which the
    reviewer must READ like a bundle part (review_run.py expects it). With no
    out_dir, every row is inline."""
    overflow = os.path.join(out_dir, WEBTEST_FINDINGS_FILE) if out_dir else None
    if overflow and os.path.exists(overflow):
        os.remove(overflow)  # a previous round's list must not be read as this one's
    listing = manifest.get("webtest")
    path = os.path.join(root, ".work", "tickets", ticket, "webtest", "findings.json")
    raw = _read(path)
    if listing is None and raw is None:
        return []
    out = ["== Web tests =="] + (_artifact_lines(listing) if listing else [])
    if raw is None:
        out.append(f"MISSING: no {os.path.relpath(path, root)} -- the healer-skip check "
                   "(webtest_guard.py skips) has not run for this ticket.")
        return out
    try:
        rows = json.loads(raw).get("findings")
    except (ValueError, AttributeError):
        rows = None
    if not isinstance(rows, list):
        out.append(f"UNREADABLE: {os.path.relpath(path, root)}; whether a skip was added "
                   "is UNKNOWN.")
        return out
    every = [_finding_row(row) for row in rows]
    if overflow and len(every) > WEBTEST_FINDINGS_MAX:
        _write_file(overflow, "\n".join(every) + "\n")
        out += every[:WEBTEST_FINDINGS_MAX]
        out.append(f"  ... and {len(every) - WEBTEST_FINDINGS_MAX} more. ALL {len(every)} rows "
                   f"are in {overflow}: read that file in full, carry every FINDING row in it, "
                   f"and output READ|{WEBTEST_FINDINGS_FILE} on its own line. Without that "
                   "READ line the review is INCOMPLETE.")
    else:
        out += every
    out.append("Carry every FINDING row into your findings as FIX: a healer skip is a "
               "finding, never accepted. EXCLUDED rows are named in the spec's Exclusions."
               if rows else "Healer-skip check: no skip added since the ticket's base.")
    return out


def build(root, ticket, manifest, out_dir=None):
    lines = []
    for block in (_bundle_block(manifest), _spec_block(root, ticket),
                  _plan_block(root, ticket), _receipts_block(root, manifest),
                  _webtest_block(root, ticket, manifest, out_dir)):
        if not block:
            continue
        lines += block + [""]
    return "\n".join(lines)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    with open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)
    manifest.setdefault("manifest_path", os.path.abspath(args.manifest))
    text = build(root, args.ticket, manifest, os.path.dirname(os.path.abspath(args.out)))
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
