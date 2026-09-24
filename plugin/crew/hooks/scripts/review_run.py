"""Run one review round: reserve it, launch the reviewer, compute the verdict.

ORDER IS THE POINT. The round is reserved in the ledger (`review_ledger.
reserve`) BEFORE the reviewer process is started, so a reviewer that crashes,
hangs, or takes this process down with it has still spent its round.
`test_review_ledger.py` kills this process from inside a fake reviewer and
asserts the round is on the ledger.

PROVIDERS.
  codex    `codex exec --json --sandbox read-only`, stdin closed (a real run
           hung here waiting on stdin). The final message and the turn's
           success are read from the JSON event stream; a failed turn is
           INCOMPLETE even when the process exited 0. `--model` and
           `--effort` pass through from config, and nothing is passed when
           they are empty.
  copilot  `copilot -p ... --deny-tool write --deny-tool shell -s`, stdin closed.
  claude   the `reviewer` subagent runs inside the Claude session, not as a
           process this script can launch. So it is two calls: `--reserve-only`
           before the subagent is dispatched, then `--round N --output FILE
           --exit-code 0` after, which refuses a round that was not reserved or
           already has a result.

A provider binary that is not on PATH is refused BEFORE reservation: nothing
was launched, so nothing is spent.

The prompt is passed inline when it fits a Windows command line; otherwise the
argument tells the reviewer to read `prompt.txt`, and says so on stderr.

Before the verdict, every bundle part is re-read and checked against the
manifest's size and sha256 for it, and the parts together against
`bundle_sha256`, and their byte total against `patch_bytes`. A manifest
with no parts, or a part that is missing, truncated or altered, makes the round
INCOMPLETE: the receipt binds the manifest's hash, so without this check a
reviewer could have read an emptied part while the receipt still vouched for
the untouched tree.

Writes `<work-dir>/review.json` (default `.work/tickets/<id>/review.json`)
and records the round in the ledger; a CLEAN round writes the receipt.

WEB TESTS. In a Playwright repository (the manifest carries a `webtest`
listing) or wherever `.work/tickets/<id>/webtest/findings.json` exists, the
healer-skip check is RE-RUN here, before the verdict, stamped with the
manifest's head and bundle sha256 -- a findings file computed for an older
tree must never vouch for this one. `webtest_check` in review.json records
whether the file it replaced was missing, stale (another head or bundle) or
current. The review is INCOMPLETE when HEAD or the working tree no longer
matches the bundle (the findings would describe a different tree) or when
the check could not tell. `webtest_findings` is the open (unexcluded) rows,
None when the check does not apply; any open row makes a CLEAN verdict
FINDINGS, named in `webtest_verdict`, because a healer skip is a finding
whether or not the reviewer carried it. When the prompt overflowed its inline
rows into `webtest-findings.txt` in the scratch directory, that file is an
expected READ like a bundle part.

Exit codes: 0 CLEAN; 1 FINDINGS; 3 INCOMPLETE; 4 budget refused
(NEEDS_REPLAN); 2 usage or setup error.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys

import crew_common
import crew_state
import review_ledger
import review_patch
import review_prompt
import review_verdict
import webtest_guard

EXIT_CLEAN, EXIT_FINDINGS, EXIT_USAGE, EXIT_INCOMPLETE, EXIT_REFUSED = 0, 1, 2, 3, 4
DEFAULT_TIMEOUT = 1800
# Windows' CreateProcess limit is 32767 characters for the whole command line.
INLINE_PROMPT_LIMIT = 24000
LAUNCHED = ("codex", "copilot")


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _write_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def prompt_argument(prompt_path):
    text = _read(prompt_path)
    if len(text) <= INLINE_PROMPT_LIMIT:
        return text
    sys.stderr.write(f"review-run: prompt is {len(text)} chars, over the inline limit; "
                     f"the reviewer is told to read {prompt_path}\n")
    return (f"Your complete instructions are in the file {prompt_path}. Read that file in "
            "full first and follow it exactly; it is the whole task.")


def command_for(provider, exe, root, prompt, model, effort):
    if provider == "codex":
        cmd = [exe, "exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check",
               "-C", root]
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["-c", f"model_reasoning_effort={effort}"]
        return cmd + [prompt]
    return [exe, "-p", prompt, "--model", model, "--deny-tool", "write",
            "--deny-tool", "shell", "-s"]


def launch(cmd, root, timeout):
    """(stdout, stderr, exit_code, timed_out). stdin is always closed."""
    try:
        done = subprocess.run(cmd, cwd=root, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(
            "utf-8", "replace")
        return out, "", None, True
    except OSError as exc:
        return "", f"could not start {cmd[0]}: {exc}", None, False
    return done.stdout, done.stderr, done.returncode, False


def bundle_problems(manifest):
    """Reasons the part files on disk are not the bundle the manifest
    describes; empty when every part matches its recorded size and sha256
    and the parts together hash to `bundle_sha256`."""
    rows = manifest.get("parts")
    if not isinstance(rows, list) or not rows:
        return ["the manifest lists no bundle parts, so there is nothing the reviewer "
                "can be shown to have read"]
    problems = []
    whole = hashlib.sha256()
    total = 0
    for row in rows:
        try:
            with open(row["path"], "rb") as fh:
                data = fh.read()
        except (OSError, KeyError, TypeError) as exc:
            problems.append(f"bundle part {row.get('name')} could not be read: {exc}")
            continue
        whole.update(data)
        total += len(data)
        if len(data) != row.get("bytes") or hashlib.sha256(data).hexdigest() != row.get(
                "sha256"):
            problems.append(f"bundle part {row.get('name')} is {len(data)} bytes and does "
                            f"not match its manifest entry ({row.get('bytes')} bytes)")
    if not problems and whole.hexdigest() != manifest.get("bundle_sha256"):
        problems.append("the bundle parts do not hash to the manifest's bundle_sha256")
    if not problems and total != manifest.get("patch_bytes"):
        problems.append(f"the bundle parts total {total} bytes, not the patch's "
                        f"{manifest.get('patch_bytes')}")
    return problems


def _findings_doc(root, ticket):
    try:
        doc = json.loads(_read(webtest_guard.findings_path(root, ticket)))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def webtest_findings(root, ticket):
    """The healer-skip rows not excused by the spec, from
    `webtest_guard.py skips`; None when that check never ran for the ticket."""
    rows = (_findings_doc(root, ticket) or {}).get("findings")
    if not isinstance(rows, list):
        return None
    return [r for r in rows if isinstance(r, dict) and not r.get("excluded")]


def webtest_check(root, ticket, manifest):
    """(open_rows_or_None, record_or_None, incomplete_reasons). Re-runs the
    healer-skip check for the tree the bundle was cut from; see WEB TESTS."""
    path = webtest_guard.findings_path(root, ticket)
    if manifest.get("webtest") is None and not os.path.exists(path):
        return None, None, []
    head, bundle = manifest.get("head"), manifest.get("bundle_sha256")
    prior = _findings_doc(root, ticket)
    state = ("missing" if prior is None else "current"
             if (prior.get("head"), prior.get("bundle_sha256")) == (head, bundle) else "stale")
    reasons = []
    now = crew_common.git_out(root, "rev-parse", "HEAD")
    if now != head:
        reasons.append(f"webtest: HEAD is {str(now)[:12]}, not the bundle's {str(head)[:12]}; "
                       "the healer-skip check cannot be tied to the reviewed tree")
    else:
        try:
            current = review_patch.compute(root, manifest.get("base") or "")[0]
        except RuntimeError as exc:
            current = {}
            reasons.append(f"webtest: the bundle could not be rebuilt to check it is current: {exc}")
        if current and current.get("bundle_sha256") != bundle:
            reasons.append("webtest: the working tree changed after the bundle was cut; the "
                           "healer-skip check cannot be tied to the reviewed tree")
    code, lines = webtest_guard.check_skips(root, ticket, bundle_sha256=None if reasons else bundle)
    if code == webtest_guard.EXIT_UNKNOWN:
        reasons.append(f"webtest: {lines[0]}")
    rows = webtest_findings(root, ticket) if code != webtest_guard.EXIT_UNKNOWN else None
    record = {"prior_findings": state, "rerun_exit": code, "head": now, "bundle_sha256": bundle}
    return rows, record, reasons


def finish(args, number, output, exit_code, timed_out, extra_reasons=()):
    """Verdict -> ledger -> review.json. Returns the process exit code."""
    manifest = json.loads(_read(args.manifest))
    parts = [p["name"] for p in manifest.get("parts") or []]
    if os.path.exists(os.path.join(args.scratch, review_prompt.WEBTEST_FINDINGS_FILE)):
        parts.append(review_prompt.WEBTEST_FINDINGS_FILE)
    rows, webtest_record, webtest_reasons = webtest_check(args.root, args.ticket, manifest)
    extra_reasons = list(extra_reasons) + bundle_problems(manifest)
    extra_reasons += webtest_reasons
    result = review_verdict.parse(output, exit_code, timed_out, parts)
    if extra_reasons:
        result["reasons"] = list(extra_reasons) + result["reasons"]
        result["verdict"] = review_verdict.INCOMPLETE
    webtest_verdict = None
    if rows:
        webtest_verdict = (f"{len(rows)} open healer skip(s) in webtest_findings; a healer skip "
                           "is a finding, never accepted, so this round is not CLEAN")
        if result["verdict"] == review_verdict.CLEAN:
            result["verdict"] = review_verdict.FINDINGS
    review = {
        "ticket": args.ticket, "round": number, "budget": review_ledger.BUDGET,
        "verdict": result["verdict"], "counts": result["counts"],
        "reasons": result["reasons"], "parts_expected": parts,
        "parts_missing": result["parts_missing"],
        "provider": args.provider, "model": args.model or None,
        "model_family": crew_state.family(args.provider, args.model),
        "bundle_sha256": manifest.get("bundle_sha256"),
        "base": manifest.get("base"), "head": manifest.get("head"),
        "exit_code": exit_code, "timed_out": timed_out,
        "webtest_findings": rows, "webtest_check": webtest_record,
        "webtest_verdict": webtest_verdict,
        "written_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"),
    }
    # Ledger first: it refuses a round that was never reserved or already
    # has a result, and a refused record must not leave a review.json behind.
    state = review_ledger.record(args.root, args.ticket, number, review)
    work_dir = args.work_dir or os.path.join(args.root, ".work", "tickets", args.ticket)
    _write_atomic(os.path.join(work_dir, "review.json"),
                  json.dumps(review, indent=2, sort_keys=True) + "\n")
    counts = result["counts"]
    print(f"review: {result['verdict']} round {number}/{review_ledger.BUDGET} "
          f"({counts['BLOCK']} BLOCK, {counts['FIX']} FIX, {counts['NIT']} NIT) "
          f"{args.provider}/{args.model or 'default'} family={review['model_family']} "
          f"ledger={state}")
    for reason in result["reasons"]:
        print(f"review: INCOMPLETE because {reason}")
    if webtest_verdict:
        print(f"review: {result['verdict']} because {webtest_verdict}")
    return {review_verdict.CLEAN: EXIT_CLEAN, review_verdict.FINDINGS: EXIT_FINDINGS}.get(
        result["verdict"], EXIT_INCOMPLETE)


def run(args):
    exe = prompt = None
    if args.provider in LAUNCHED:
        if args.provider == "copilot" and not args.model:
            sys.stderr.write("review-run: copilot needs --model (qa.copilot.model); an "
                             "unpinned Copilot is the author's family\n")
            return EXIT_USAGE
        exe = shutil.which(args.provider)
        if not exe:
            sys.stderr.write(f"review-run: {args.provider} is not on PATH; nothing launched, "
                             "no round spent\n")
            return EXIT_USAGE
        prompt = prompt_argument(os.path.join(args.scratch, "prompt.txt"))

    ok, number, message = review_ledger.reserve(args.root, args.ticket, args.provider,
                                                args.model)
    sys.stderr.write(f"review-run: {message}\n")
    if not ok:
        return EXIT_REFUSED
    if args.provider not in LAUNCHED:
        print(f"ROUND={number}")
        return EXIT_CLEAN

    cmd = command_for(args.provider, exe, args.root, prompt, args.model, args.effort)
    stdout, stderr, code, timed_out = launch(cmd, args.root, args.timeout)
    extra = []
    if args.provider == "codex":
        _write_atomic(os.path.join(args.scratch, "codex-events.jsonl"), stdout)
        message_text, error = review_verdict.codex_final_message(stdout)
        output = message_text or ""
        if error and not timed_out:
            extra.append(f"codex: {error}")
    else:
        output = stdout
    _write_atomic(os.path.join(args.scratch, "out.txt"), output)
    _write_atomic(os.path.join(args.scratch, "stderr.txt"), stderr)
    return finish(args, number, output, code, timed_out, extra)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--provider", required=True, choices=("codex", "copilot", "claude"))
    parser.add_argument("--model", default="")
    parser.add_argument("--effort", default="")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--work-dir")
    parser.add_argument("--reserve-only", action="store_true")
    parser.add_argument("--round", type=int)
    parser.add_argument("--output")
    parser.add_argument("--exit-code", type=int)
    args = parser.parse_args(argv)
    args.root = os.path.abspath(args.root)
    args.scratch = os.path.abspath(args.scratch)
    args.manifest = args.manifest or os.path.join(args.scratch, "manifest.json")

    try:
        review_ledger.check_ticket(args.ticket)
        if args.provider == "claude":
            if args.reserve_only:
                return run(args)
            if args.round is None or args.output is None or args.exit_code is None:
                parser.error("the claude provider takes --reserve-only, or --round N "
                             "--output FILE --exit-code N after the subagent ran")
            output = _read(args.output) if os.path.exists(args.output) else ""
            return finish(args, args.round, output, args.exit_code, False)
        if args.reserve_only or args.round is not None:
            parser.error("--reserve-only and --round are for the claude provider only")
        return run(args)
    except review_ledger.LedgerError as exc:
        sys.stderr.write(f"review-run: {exc}\n")
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
