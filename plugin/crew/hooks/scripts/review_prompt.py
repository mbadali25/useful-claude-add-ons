"""Write the ticket-contract block of the shared review prompt.

`/crew:review` builds ONE prompt that every reviewer reads byte-for-byte; this
script writes the part of it that is about the ticket rather than the diff:

  - the bundle parts, in order, and the READ acknowledgement each needs,
    and the paths the manifest excluded;
  - the ticket's spec sections -- Intent, Exclusions, Evidence, Unknowns,
    Acceptance checks -- from `.work/tickets/<id>/spec.md` (or, for a
    files-mode ticket with no spec.md yet, `.work/tickets/<id>.md`);
  - the plan, `.work/tickets/<id>/plan.md`, in full;
  - the test receipts: the verify gate's last verified commit
    (`.crew/.verify-verified-at`) against HEAD and, when that does not show
    HEAD clean, the local gate's answer (`review_gate.gate_state`: `Local
    gate: VERIFIED`, `No verify gate`) or, only when that is UNVERIFIED or
    UNKNOWN, the CI receipt for HEAD -- the upgrade `review_run.py` reserves
    on -- and every rule the local record (`.crew/.verify-gate.record.json`)
    still lists as NOT VERIFIED (marked superseded when the receipt covers
    HEAD). When the gate does not accept the tree, one fixed line
    (`OVERRIDE_LINE`, T-0101) says that such a round exists only under
    `--allow-unverified`, recorded as `gate.overridden`, so a reviewer can
    tell a recorded override from a gap nobody noticed.

  - the development standards checklist (T-0085): the effective standards
    set's ids, rules and self-check questions from `crew_standards.
    checklist_block`, stating that the author's self-check answers are
    withheld (`selfcheck.md` is never read here) and that the list does not
    bound the review; an unreadable overlay is written `UNREADABLE: ...`.
  - the recurring-findings checklist (L-0575, L-0601): the defect classes
    earlier reviews kept finding, keyed to the bundle's changed files, from
    `recurring_findings.review_block`; it says the list does not bound the
    review, and an unusable manifest lists every class under `UNKNOWN:`.

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

import ci_receipt
import crew_standards
import merged_main
import recurring_findings
import review_checks
import review_gate
import review_verdict
import verify_record

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


def _relpath(path, root):
    """`os.path.relpath`, forced to forward slashes. This text is read by a
    reviewer model, not a shell -- `os.path.relpath` alone renders as
    `.work\\tickets\\T9.md` on Windows, inconsistent with every literal
    forward-slash path this file writes elsewhere (`.work/tickets/{ticket}.md`
    at :106, `webtest-findings.txt`'s own `<out_dir>/...` lines) and with the
    manifest's own path fields, which are always POSIX-style."""
    return os.path.relpath(path, root).replace(os.sep, "/")


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
           f"{review_verdict.READ_FORM} on its own line. A READ line for a path in any",
           "other directory counts for nothing; a part with no READ line makes the review "
           "INCOMPLETE."]
    out += [f"  {p['path']}" for p in parts]
    # Three states, one line each (T-0099): an empty list is a manifest saying
    # nothing was left out; no key, or anything but a list of non-blank strings,
    # is one that cannot say, and must not read as either of the known answers.
    excluded = manifest.get("excluded")
    if isinstance(excluded, list) and all(isinstance(p, str) and p.strip() for p in excluded):
        out.append("  excluded (never in the bundle): "
                   + (", ".join(excluded) if excluded else "none"))
    else:
        out.append("  excluded: not recorded by this manifest (unknown)")
    out.append(_merged_main_line(manifest.get("merged_main")))
    out.append(f"Manifest (file categories, renames, modes, binaries, submodules): "
               f"{manifest.get('manifest_path', 'manifest.json')}")
    for key, label in (("renames", "renamed"), ("mode_changes", "mode changed"),
                       ("binary_files", "binary (marker only, blob ids in the patch)"),
                       ("submodules", "submodule")):
        if manifest.get(key):
            out.append(f"  {label}: {', '.join(manifest[key])}")
    return out


def _merged_main_line(merged):
    """What the bundle left out as identical to the merged integration commit
    (T-0100), could-not-tell, none, or not recorded -- never silent."""
    if not isinstance(merged, dict):
        return "  merged main: not recorded"
    if merged.get("applies"):
        dropped = merged.get("dropped") or []
        against = merged.get("diffed_from_merged") or []
        return (f"  merged main: {str(merged.get('commit'))[:12]} ({merged.get('ref')}) - "
                f"{len(dropped)} path(s) identical to it left out: "
                f"{', '.join(dropped) if dropped else 'none'}"
                + (f"; {len(against)} path(s) main also changed diffed from it, so main's "
                   f"lines there are context: {', '.join(against)}" if against else "")
                + _fork_clause(merged))
    if merged.get("commit") is None:
        return (f"  merged main: {merged_main.UNKNOWN} - {merged_main.bare_reason(merged)}; "
                "nothing left out")
    return f"  merged main: none since the ticket start ({merged_main.bare_reason(merged)})"


def _fork_clause(merged):
    """The could-not-tell clause when the fork lookup failed (`fork` recorded as
    null): which paths main also changed is unknown, so none were diffed from
    the merged commit. A manifest without the key (an older crew) adds nothing."""
    if merged.get("fork", "") is not None:
        return ""
    reason = str(merged.get("fork_reason") or "could not tell: the fork lookup gave no answer")
    reason = reason[len("could not tell: "):] if reason.startswith("could not tell: ") else reason
    return (f"; could not tell which paths main also changed ({reason}), so main's lines "
            "there may read as the ticket's")


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
    out.append(f"(from {_relpath(source, root)})")
    found = sections(text)
    for name in SPEC_SECTIONS:
        body = found.get(name.lower())
        if body:
            out += [f"-- {name} --", body]
        else:
            out.append(f"-- {name} -- MISSING: no '{name}' section in "
                       f"{_relpath(source, root)}")
    return out


def _plan_block(root, ticket):
    path = os.path.join(root, ".work", "tickets", ticket, "plan.md")
    text = _read(path)
    if text is None or not text.strip():
        return ["== Plan ==", f"MISSING: no plan at {_relpath(path, root)}."]
    return ["== Plan ==", text.strip()]


def _head(root):
    try:
        return subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=False, timeout=30,
                              stdin=subprocess.DEVNULL).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


REASON_MAX = 400

# T-0101: printed only in the branch where the gate does not accept the tree
# (local UNVERIFIED or UNKNOWN, no CI receipt VERIFIED), after the unchanged
# MISSING / NOT-been-through-the-gate and `Gate answer for HEAD` lines. A rule
# about the tool, so it stays true whatever the operator passes later.
OVERRIDE_LINE = ("Order: review_run.py reserves no round on a tree in this state unless the "
                 "operator passes --allow-unverified, and review.json then records "
                 "gate.overridden. /crew:done still needs a clean gate. The missing pass is "
                 "that recorded override: do not report it as a defect on its own. Report "
                 "anything in the diff a gate run would catch.")


def _reason(text):
    """A gate reason as ONE line: control characters escaped (a git or gh
    stderr carried in a reason can be multi-line, and a line of its own in
    the prompt reads as an instruction) and capped at REASON_MAX."""
    one = review_checks.one_line(str(text))
    return one if len(one) <= REASON_MAX else one[:REASON_MAX] + "... (truncated)"


def _ask(question, root):
    """(state, reason) from a gate question; a call that raises is UNKNOWN,
    never a pass."""
    try:
        return question(root)
    except Exception as exc:  # pylint: disable=broad-except
        return review_gate.UNKNOWN, f"{exc.__class__.__name__}: {exc}"


def _receipt(root):
    """(state, reason) of the CI receipt alone (`ci_receipt.check`), never
    the local gate. `accepted_state` is NOT asked here: it re-asks
    `gate_state`, so a local pass that lands between two calls (the Stop gate
    finishing while the prompt is built) would come back VERIFIED and be
    printed as a receipt (review r2). This is the same upgrade
    `accepted_state` makes, on the ONE local answer this block already holds."""
    state, reason, _ = ci_receipt.check(root)
    return state, reason


def _receipts_block(root, manifest):
    """The verify evidence, as the gate that reserved this round judged it
    (docs/review/08, defect 1). A clean local pass on HEAD needs no question.
    Otherwise the LOCAL gate is asked ONCE (`review_gate.gate_state`): a
    dirty tree its fingerprint covers is a local VERIFIED, and a repo with no
    gate is NO_GATE -- neither is a receipt, and neither is MISSING. Only a
    local UNVERIFIED or UNKNOWN asks the CI receipt (`_receipt`), the upgrade
    `review_gate.accepted_state` makes for `review_run.py`; then, and only
    then, the local record's rows are marked superseded, because a receipt is
    a `--all` run with nothing outstanding."""
    out = ["== Test receipts (verify gate) =="]
    marker = os.path.join(root, ".crew", ".verify-verified-at")
    verified = (_read(marker) or "").strip()
    head = _head(root)
    receipt = False
    if verified and verified == head and not manifest.get("dirty"):
        out.append(f"Last clean verify pass: {_reason(verified[:12])} = HEAD, tree clean.")
    else:
        local, local_why = _ask(review_gate.gate_state, root)
        if local == review_gate.VERIFIED:
            out.append(f"Local gate: VERIFIED - {_reason(local_why)}")
        elif local == review_gate.NO_GATE:
            out.append(f"No verify gate: {_reason(local_why)}")
        else:
            r_state, r_reason = _ask(_receipt, root)
            if r_state == review_gate.VERIFIED:
                receipt = True
                out.append(f"CI receipt: VERIFIED for HEAD - {_reason(r_reason)}")
            else:
                if not verified:
                    out.append("MISSING: no .crew/.verify-verified-at -- the verify gate has "
                               "not recorded a clean pass in this checkout.")
                else:
                    out.append(f"Last clean verify pass: {_reason(verified[:12])}; HEAD is "
                               f"{head[:12]}"
                               f"{', tree dirty' if manifest.get('dirty') else ''}. Changes "
                               "after that pass have NOT been through the gate.")
                # Each part capped on its own: one cap over both let a long
                # local reason (up to three record rows) cut the receipt's
                # answer off entirely (review r3).
                out.append(f"Gate answer for HEAD: {local}: {_reason(local_why)}; "
                           f"CI receipt {r_state}: {_reason(r_reason)}")
                out.append(OVERRIDE_LINE)
    state, rules = verify_record.read_record(root)
    shown = verify_record.RECORD_PATH.replace("\\", "/")
    if state == "absent":
        out.append(f"MISSING: no {shown} (no per-rule record).")
        return out
    if state != "ok":
        out.append(f"UNREADABLE: {shown} does not parse; which rules "
                   "are unverified is UNKNOWN.")
    elif not rules:
        out.append("Per-rule record: no rule is outstanding.")
    else:
        prefix = "Local record, superseded for HEAD by the CI receipt: " if receipt else ""
        for info in rules.values():
            if isinstance(info, dict):
                out.append(f"{prefix}NOT VERIFIED: {info.get('label', '?')}: "
                           f"{info.get('reason', '')}")
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
        out.append(f"MISSING: no {_relpath(path, root)} -- the healer-skip check "
                   "(webtest_guard.py skips) has not run for this ticket.")
        return out
    try:
        rows = json.loads(raw).get("findings")
    except (ValueError, AttributeError):
        rows = None
    if not isinstance(rows, list):
        out.append(f"UNREADABLE: {_relpath(path, root)}; whether a skip was added "
                   "is UNKNOWN.")
        return out
    every = [_finding_row(row) for row in rows]
    if overflow and len(every) > WEBTEST_FINDINGS_MAX:
        _write_file(overflow, "\n".join(every) + "\n")
        out += every[:WEBTEST_FINDINGS_MAX]
        out.append(f"  ... and {len(every) - WEBTEST_FINDINGS_MAX} more. ALL {len(every)} rows "
                   f"are in {overflow}: read that file in full, carry every FINDING row in it, "
                   f"and output {review_verdict.READ_FORM} for that file on its own line. "
                   "Without that READ line the review is INCOMPLETE.")
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
                  crew_standards.checklist_block(root, manifest),
                  recurring_findings.review_block(root, manifest),
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
