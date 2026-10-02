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

`--probe` (codex only) makes one minimal real call and reserves nothing: exit
0 ok, 5 limited (a usage/rate/quota limit, `review_limit.limit_line`), 6
failed, 7 unknown (timed out). /crew:review runs it before step 2a. Being on
PATH is not being able to review: a logged-out or rate-limited Codex resolves
on PATH and fails at the first call (T-0088).

STANDARDS SELF-CHECK (T-0085). Also before reservation, and AFTER `preflight`
(question 3 below), for every provider
(`claude --reserve-only` included): a ticket with an approval receipt must
have `.work/tickets/<id>/selfcheck.md` complete and stamped for exactly this
manifest's `bundle_sha256` and the effective standards digest
(`crew_standards.review_gate`). Missing, unreadable, incomplete, unstamped or
stale is exit 2 with each problem named and no round spent. A ticket with no
approval receipt never ran /crew:implement or /crew:fix, so the gate says it
does not apply; an active incident stands it down and logs a
`standards-selfcheck` skip.

The prompt is passed inline when it fits a Windows command line and the
provider is not a batch-file shim (cmd.exe ends a `.cmd`/`.bat` command line
at the first line break); otherwise the argument tells the reviewer to read
`prompt.txt`, and says so on stderr.

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

FAILURE CLASS AND REFUNDS (T-0087). An INCOMPLETE round is classed by
`review_verdict.failure_class`: `tree` when a bundle or webtest reason was
added here, `tool` when the answer never arrived intact (timeout, unknown or
non-zero exit, empty output, a `codex:` stream error), else `reviewer`.
review.json carries `failure_class`, and `refunded` / `refund_refused` as the
ledger recorded them; a `review:` line says whether the round was refunded. A
refunded round still exits 3.

BEFORE ANY ROUND IS RESERVED, four questions, in this order (`preflight`,
then `prereview_gate`, then `standards_gate`):

  1. Does a CLEAN receipt already cover this exact bundle
     (`review_ledger.check_receipt`, the check `/crew:done` gates on)? Then
     nothing has changed since a clean review, so no round is spent: the
     verdict is that receipt's CLEAN, said as such. An owner-accepted
     FINDINGS receipt does not short-circuit -- that is a person's call about
     one round, not a clean review of the tree.
  2. Has the verify gate passed on this tree (`review_gate.gate_state`)? A
     tree it has not passed, or one whose state could not be read, is refused
     with exit 5 and no round spent: a reviewer's opinion on code the gate
     would refuse for free is the most expensive way to find out it is red.
     `--allow-unverified` reviews it anyway, and review.json says it did.
     No verify map, or a gate stood down, proceeds and says so.
  3. Then (`prereview_gate`, L-0574): does the bundle add a linter finding
     its own base did not have (`review_checks.py`, configured under
     `preReview` in `.crew/verify.json`)? A NEW finding is exit 5, no round
     spent, and `--allow-unverified` does not override it. A check that could
     not run (missing tool, crash, timeout, bad output, a file the tool could
     not parse, a config it cannot read) is COULD NOT CHECK, never a pass:
     exit 5 too, unless `--allow-unverified`, which review.json records as
     `prereview.overridden`. Only an active incident stands both down, and
     logs a `prereview-checks` skip. No `preReview` key proceeds and says so.
  4. Only then (`standards_gate`, T-0085): is the standards self-check
     complete and stamped for this bundle? Missing or stale is exit 2, no
     round spent -- see STANDARDS SELF-CHECK above. A CLEAN receipt (1) never
     asks for a self-check, and a refusal at (2) or (3) comes first.

Questions 3 and 4 are not asked when the budget is already spent: the
reservation refuses that (exit 4) whatever they would say.

Every round's review.json carries `gate` (the state observed at verdict time)
and `elapsed_s` (reservation to verdict, from the ledger's own timestamps), and
the `review:` summary line prints both. It also carries `prereview`: the
<scratch>/prereview.json question 3 wrote for this bundle, or
`{"result": "not-recorded", "reason": ...}` -- never a bare null.

Exit codes: 0 CLEAN; 1 FINDINGS; 3 INCOMPLETE; 4 budget refused
(NEEDS_REPLAN); 5 not run, verify gate not green or a pre-review check new or
could not check (no round spent); 2 usage or setup error, or the standards
self-check missing or stale -- not run, no round spent. Exit 5 is decided
before exit 2 (self-check) is asked for.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys

import crew_common
import crew_incident
import crew_standards
import crew_state
import review_checks
import review_gate
import review_ledger
import review_limit
import review_patch
import review_prompt
import review_verdict
import webtest_guard

EXIT_CLEAN, EXIT_FINDINGS, EXIT_USAGE, EXIT_INCOMPLETE, EXIT_REFUSED = 0, 1, 2, 3, 4
EXIT_UNVERIFIED = 5
DEFAULT_TIMEOUT = 1800
# Bound on the follow-up `communicate()` after a kill, below. Not the same
# knob as --timeout: this one exists so a descendant that escaped the kill
# (still holding the pipe open) cannot itself defeat --timeout by keeping
# this call blocked - see `launch`'s own comment for the full reproduction.
POST_KILL_TIMEOUT = 5
# Windows' CreateProcess limit is 32767 characters for the whole command line.
INLINE_PROMPT_LIMIT = 24000
# cmd.exe ends a batch file's command line at the first line break, so a
# provider resolved to one of these (an npm-installed codex.cmd or copilot.cmd)
# is never handed a multi-line prompt inline (T-0087, PR #260's Windows job).
BATCH_SHIM_SUFFIXES = (".cmd", ".bat")
LAUNCHED = ("codex", "copilot")
# The probe (T-0088): one minimal real Codex call, before any reservation.
PROBE_TIMEOUT = 120
PROBE_PROMPT = "Reply with exactly the word OK. Do not run any command and do not read any file."
EXIT_PROBE_LIMITED, EXIT_PROBE_FAILED, EXIT_PROBE_UNKNOWN = 5, 6, 7
PROBE_OK, PROBE_LIMITED, PROBE_FAILED, PROBE_UNKNOWN = "ok", "limited", "failed", "unknown"
VERIFY_GATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify-gate.sh")


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _decode_partial(value):
    """CPython raises `TimeoutExpired` from INSIDE the read loop, before the
    text-mode translation `Popen.communicate` normally applies -- so
    `exc.output`/`exc.stderr` on a `communicate(timeout=...)` timeout are
    raw bytes even though this `Popen` was constructed with `text=True`,
    never the decoded str every other return path here already is. Decoded
    with the same utf-8/replace policy the Popen itself uses, so a partial
    capture from a second, bounded timeout is usable text rather than either
    bytes leaking into a str-typed return or silently discarded."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _write_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def through_batch_shim(exe):
    """True when `exe` is a Windows batch file (an npm shim is one): cmd.exe
    ends a batch file's command line at the first line break, so a
    multi-line argument never reaches the program behind it intact."""
    return os.path.splitext(exe or "")[1].lower() in BATCH_SHIM_SUFFIXES


def prompt_argument(prompt_path, exe=None):
    """`exe` is the resolved provider binary. The prompt goes inline only when
    it fits INLINE_PROMPT_LIMIT and `exe` is not a batch shim; otherwise the
    argument is a one-line pointer to `prompt_path`, said on stderr."""
    text = _read(prompt_path)
    if len(text) <= INLINE_PROMPT_LIMIT and not through_batch_shim(exe):
        return text
    if len(text) > INLINE_PROMPT_LIMIT:
        sys.stderr.write(f"review-run: prompt is {len(text)} chars, over the inline limit; "
                         f"the reviewer is told to read {prompt_path}\n")
    else:
        sys.stderr.write(f"review-run: {os.path.basename(exe)} is a batch shim and cmd.exe ends "
                         "its arguments at the first line break; the reviewer is told to read "
                         f"{prompt_path}\n")
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
    """(stdout, stderr, exit_code, timed_out). stdin is always closed.

    Spawned in its own process group/session so a timeout can kill the whole
    tree, not just the direct child. A provider CLI installed as an npm
    `.cmd` shim on Windows runs as `cmd.exe /c <shim>`, with the real work in
    a grandchild -- a bare `Popen.kill()` (what a plain `subprocess.run(...,
    timeout=...)` does on `TimeoutExpired`) only reaches `cmd.exe`. Left
    un-reaped, that grandchild keeps this process's stdout pipe open past the
    kill, and reading it blocks well past `timeout` -- observed as the
    caller's own outer safety timeout firing instead of this one.

    BLOCK (Codex): the leader's pid/pgid is only safe to signal by bare
    number while the leader is STILL ALIVE AND UNREAPED -- once `proc.poll()`
    shows it has exited, that number is free for the OS to hand to a brand
    new, entirely unrelated process, and `os.killpg(proc.pid, ...)` at that
    point can reach whatever the OS gave it to next instead of anything this
    process started. `proc.poll()` is checked immediately before either the
    POSIX `killpg` or the Windows `taskkill` -- both by pid -- and skipped
    entirely when the leader has already exited; a provider that forks a
    detached grandchild (`setsid sh -c '...' &`) and exits itself is exactly
    that shape, and is left alone here rather than guessed at.

    BLOCK (Codex): the follow-up `communicate()` after a kill used to carry
    no timeout of its own, so a descendant that escaped the kill (still
    holding the stdout/stderr pipe open -- the leader-already-exited case
    above is exactly when this can happen) kept it blocked past --timeout
    with nothing bounding the wait. Reproduced with a provider that runs
    `setsid sh -c "sleep 60" &` and exits: the leader is gone before this
    function ever gets to kill anything, the grandchild keeps sleeping and
    keeps the pipe open, and an unbounded second `communicate()` returns only
    after the full sleep. Bounded by `POST_KILL_TIMEOUT`; on a second
    `TimeoutExpired`, CPython's own exception already carries whatever bytes
    were read before that bound (`exc.output`/`exc.stderr`), so this keeps
    and decodes that partial capture (`_decode_partial`) rather than
    discarding it -- an earlier version of this fix threw the partial output
    away and closed the process's own stdout/stderr streams to unblock
    itself; on Windows, closing a pipe still being read by CPython's own
    reader thread for that stream can itself block, trading one hang for
    another. Reports the run as timed out either way, with whatever output
    had already arrived, rather than waiting on a descendant that is not
    coming back.
    """
    popen_kwargs = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            cmd, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            **popen_kwargs)
    except OSError as exc:
        return "", f"could not start {cmd[0]}: {exc}", None, False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        escaped = False
        if proc.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                               capture_output=True, timeout=30, check=False)
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        else:
            # Leader already exited and been reaped: its pid (and any pgid
            # numbered the same) is free for reuse, so no bare-number signal
            # is safe here. Whatever kept the pipe open is on its own.
            escaped = True
        try:
            stdout, stderr = proc.communicate(timeout=POST_KILL_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            escaped = True
            stdout = _decode_partial(exc.output)
            stderr = _decode_partial(exc.stderr)
        if escaped:
            stderr = (stderr or "") + (
                "\nreview-run: a descendant process may have escaped the "
                f"{timeout}s timeout and is still holding the output pipe "
                "open; proceeding with whatever output had already arrived\n")
        return stdout, stderr, None, True
    return stdout, stderr, proc.returncode, False


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
    # The parts as the prompt lists them -- full paths -- so a READ line that
    # echoes the listed path counts (T-0079). A part with no path falls back to
    # its name, which review_verdict still matches exactly.
    parts = [p.get("path") or p["name"] for p in manifest.get("parts") or []]
    if os.path.exists(os.path.join(args.scratch, review_prompt.WEBTEST_FINDINGS_FILE)):
        parts.append(os.path.join(args.scratch, review_prompt.WEBTEST_FINDINGS_FILE))
    rows, webtest_record, webtest_reasons = webtest_check(args.root, args.ticket, manifest)
    stream_reasons = list(extra_reasons)
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
    # Whose fault an INCOMPLETE was: extra reasons beyond the stream's are the
    # bundle/webtest checks (the tree); a stream error means the answer never
    # arrived intact (the tool).
    failure = review_verdict.failure_class(result["verdict"],
                                           result["delivered"] and not stream_reasons,
                                           len(extra_reasons) > len(stream_reasons))
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
        "gate": gate_record(args),
        "written_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"),
    }
    review["failure_class"] = failure
    # Ledger first: it refuses a round that was never reserved or already
    # has a result, and a refused record must not leave a review.json behind.
    state = review_ledger.record(args.root, args.ticket, number, review)
    ledger = review_ledger.status(args.root, args.ticket)
    row = next((r for r in ledger.get("rounds") or [] if r.get("round") == number), {})
    review["refunded"] = row.get("refunded") is True
    review["refund_refused"] = row.get("refund_refused")
    review["elapsed_s"] = round_elapsed(args.root, args.ticket, number)
    review["prereview"] = review_checks.recorded(args.scratch, manifest.get("bundle_sha256"))
    work_dir = args.work_dir or os.path.join(args.root, ".work", "tickets", args.ticket)
    _write_atomic(os.path.join(work_dir, "review.json"),
                  json.dumps(review, indent=2, sort_keys=True) + "\n")
    counts = result["counts"]
    # The budget as the ledger charges it: a refunded round is a round number,
    # never a unit of budget, so "round 3/2" would read as over budget.
    spent, refunded = ledger.get("rounds_spent"), ledger.get("rounds_refunded")
    budget = (f"{spent if isinstance(spent, int) else '?'} of {review_ledger.BUDGET} "
              f"budget rounds used" + (f", {refunded} refunded" if refunded else ""))
    print(f"review: {result['verdict']} round {number}, {budget} "
          f"({counts['BLOCK']} BLOCK, {counts['FIX']} FIX, {counts['NIT']} NIT) "
          f"{args.provider}/{args.model or 'default'} family={review['model_family']} "
          f"ledger={state} gate={review['gate']['state']} "
          f"elapsed={_fmt_elapsed(review['elapsed_s'])}")
    for reason in result["reasons"]:
        print(f"review: INCOMPLETE because {reason}")
    if failure == review_verdict.TOOL and review["refunded"]:
        print(f"review: round {number} was a tool failure ({result['reasons'][0]}); refunded - "
              f"{ledger.get('rounds_spent')} of {review_ledger.BUDGET} budget rounds used")
    elif failure == review_verdict.TOOL:
        print(f"review: round {number} was a tool failure; NOT refunded - "
              f"{review['refund_refused']}")
    elif failure:
        print(f"review: round {number} is INCOMPLETE ({failure}) and counts against the budget")
    if webtest_verdict:
        print(f"review: {result['verdict']} because {webtest_verdict}")
    return {review_verdict.CLEAN: EXIT_CLEAN, review_verdict.FINDINGS: EXIT_FINDINGS}.get(
        result["verdict"], EXIT_INCOMPLETE)


def gate_record(args):
    """The gate state for review.json: observed now, plus whether this round
    was told to go ahead regardless."""
    state, reason = review_gate.gate_state(args.root)
    return {"state": state, "reason": reason,
            "overridden": bool(getattr(args, "allow_unverified", False))
            and state in (review_gate.UNVERIFIED, review_gate.UNKNOWN)}


def round_elapsed(root, ticket, number):
    """Seconds from the round's reservation to its recorded verdict, read from
    the ledger's own `reserved_at` / `completed_at`. None when either is
    missing or unparseable -- an unknown duration, never a zero one."""
    data, state = review_ledger._load(review_ledger.ledger_path(root, ticket))  # pylint: disable=protected-access
    if state != "ok":
        return None
    for row in data.get("rounds") or []:
        if isinstance(row, dict) and row.get("round") == number:
            try:
                start = datetime.datetime.fromisoformat(row["reserved_at"])
                end = datetime.datetime.fromisoformat(row["completed_at"])
            except (KeyError, TypeError, ValueError):
                return None
            return max(int((end - start).total_seconds()), 0)
    return None


def _fmt_elapsed(seconds):
    return "unknown" if seconds is None else f"{seconds}s"


def preflight(args):
    """None to go on and reserve a round, or the exit code to stop with
    having reserved nothing. See BEFORE ANY ROUND IS RESERVED above."""
    ok, message = review_ledger.check_receipt(args.root, args.ticket)
    data, _ = review_ledger._load(review_ledger.ledger_path(args.root, args.ticket))  # pylint: disable=protected-access
    if ok and (data.get("receipt") or {}).get("kind") == "clean":
        print(f"review: CLEAN from the existing receipt ({message}) - nothing in the bundle "
              "changed since that clean round, so no round was spent")
        if args.provider not in LAUNCHED:
            print("ALREADY_CLEAN=1")
        return EXIT_CLEAN
    state, reason = review_gate.gate_state(args.root)
    if state in (review_gate.UNVERIFIED, review_gate.UNKNOWN):
        if args.allow_unverified:
            sys.stderr.write(f"review-run: gate {state}: {reason}. Reviewing anyway "
                             "(--allow-unverified); review.json records the override\n")
            return None
        sys.stderr.write(
            f"review-run: gate {state}: {reason}. No round reserved. Run the verify gate on "
            f"this tree first (bash \"{VERIFY_GATE}\" </dev/null, or end the turn so the "
            "Stop gate runs), then review again. "
            "--allow-unverified reviews it anyway and records that it did.\n")
        return EXIT_UNVERIFIED
    sys.stderr.write(f"review-run: gate {state}: {reason}\n")
    return None


def standards_gate(args):
    """None to go on and reserve; EXIT_USAGE to refuse with nothing spent.

    The required standards self-check (T-0085, `crew_standards.py`) must be
    complete and stamped for exactly this bundle and this standards set. In an
    active incident the gate stands down and logs the skip, as verify-gate.sh
    does for its own."""
    problems, note = crew_standards.review_gate(args.root, args.ticket, args.manifest)
    if note:
        sys.stderr.write(f"review-run: {note}\n")
    if problems:
        incident = crew_incident.read_state(args.root, crew_state.load_config(args.root))
        if incident["active"]:
            crew_incident.log_skip(args.root, "standards-selfcheck", "; ".join(problems))
            sys.stderr.write(f"review-run: incident {incident['id']} is active; the standards "
                             "self-check stands down and the skip is logged\n")
            return None
        for problem in problems:
            sys.stderr.write(f"review-run: self-check: {problem}\n")
        sys.stderr.write("review-run: answer .work/tickets/<id>/selfcheck.md, then run "
                         f"crew_standards.py stamp --root . --ticket {args.ticket}; nothing "
                         "launched, no round spent\n")
        return EXIT_USAGE
    return None


def prereview_gate(args):
    """None to go on and reserve; EXIT_UNVERIFIED to refuse with nothing spent.

    The pre-review checks (L-0574, `review_checks.py`): no new linter finding
    in the bundle against its own base. NEW findings refuse whatever else is
    true; COULD NOT CHECK refuses unless --allow-unverified; only an ACTIVE
    incident stands either down, and logs the skip. Every decision is written
    to <scratch>/prereview.json for `finish` to copy into review.json."""
    results, configured = review_checks.run_checks(args.root, args.manifest)
    bundle = _bundle_sha(args.manifest)
    if not configured:
        sys.stderr.write(f"review-run: pre-review checks: none configured "
                         f"({review_checks.VERIFY_MAP} has no {review_checks.CONFIG_KEY})\n")
        review_checks.record(args.scratch, bundle, [], False, False, configured=False)
        return None
    for line in review_checks.lines(results):
        sys.stderr.write(f"review-run: {line}\n")
    verdict = review_checks.overall(results)
    if verdict == review_checks.PASS:
        review_checks.record(args.scratch, bundle, results, False, False)
        return None
    incident = crew_incident.read_state(args.root, crew_state.load_config(args.root))
    if incident["active"]:
        crew_incident.log_skip(args.root, "prereview-checks", f"{verdict}: " + "; ".join(
            f"{r['name']} {r['status']}" for r in results if r["status"] in (
                review_checks.FAIL, review_checks.COULD_NOT)))
        sys.stderr.write(f"review-run: incident {incident['id']} is active; the pre-review "
                         "checks stand down and the skip is logged\n")
        review_checks.record(args.scratch, bundle, results, False, True)
        return None
    if verdict == review_checks.COULD_NOT and args.allow_unverified:
        sys.stderr.write("review-run: pre-review checks could not check everything; reviewing "
                         "anyway (--allow-unverified); review.json records the override\n")
        review_checks.record(args.scratch, bundle, results, True, False)
        return None
    review_checks.record(args.scratch, bundle, results, False, False)
    if verdict == review_checks.FAIL:
        sys.stderr.write("review-run: the bundle adds linter findings its base did not have. No "
                         "round reserved. Fix them (or suppress one with the tool's own inline "
                         "directive and a reason), then review again. --allow-unverified does "
                         "not override a new finding\n")
    else:
        sys.stderr.write("review-run: a pre-review check could not run, so this tree is not "
                         "known clean. No round reserved. Install or repair the tool and review "
                         "again, or pass --allow-unverified to review anyway (review.json "
                         "records the override)\n")
    return EXIT_UNVERIFIED


def _bundle_sha(manifest_path):
    """The manifest's bundle_sha256, or None when it cannot be read (the
    checks have already said so as a could-not-check `manifest` row)."""
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            value = json.load(fh).get("bundle_sha256")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) else None


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
        prompt = prompt_argument(os.path.join(args.scratch, "prompt.txt"), exe)

    short = preflight(args)
    if short is not None:
        return short

    # A spent budget is a precondition already known to fail (GEN-03): the
    # self-check cannot change it, so the budget refusal below answers first
    # rather than sending the author to answer and restamp for nothing.
    # `reserve` re-reads the ledger under its lock and is what refuses.
    ledger = review_ledger.status(args.root, args.ticket)
    if not (ledger.get("state") == review_ledger.NEEDS_REPLAN
            or ledger.get("rounds_left") == 0):
        refused = prereview_gate(args)
        if refused is None:
            refused = standards_gate(args)
        if refused is not None:
            return refused

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
    limit = None
    if args.provider == "codex":
        _write_atomic(os.path.join(args.scratch, "codex-events.jsonl"), stdout)
        message_text, error = review_verdict.codex_final_message(stdout)
        output = message_text or ""
        if error and not timed_out:
            extra.append(f"codex: {error}")
        # Only a FAILED call is judged: a 429 Codex retried and got past leaves
        # `error` events in a round that still delivered (T-0088).
        if timed_out or code != 0 or not output.strip():
            limit = review_limit.limit_line(error or "", stderr)
    else:
        output = stdout
    _write_atomic(os.path.join(args.scratch, "out.txt"), output)
    _write_atomic(os.path.join(args.scratch, "stderr.txt"), stderr)
    status = finish(args, number, output, code, timed_out, extra)
    if limit:
        # After finish, never before: the round's INCOMPLETE record is the
        # ledger's, and a marker that cannot be written (disk full, a path that
        # is not a directory) must not take it, or exit 3, down with it.
        try:
            review_limit.record(args.root, args.ticket, number, "codex", args.model, limit)
            then = "the next round runs the Claude reviewer (same-family, not independent)"
        except OSError as exc:
            then = (f"could not record it ({exc}), so the next probe calls Codex live "
                    "instead of answering limited from the record")
        print(f"review: codex usage limit in round {number}: {limit!r}; {then}")
    return status


def probe(args):
    """(outcome, detail). One minimal real Codex call, BEFORE any reservation.

    Four outcomes, never collapsed: `ok` is a delivered message at exit 0 (a
    429 Codex retried and then got past is still ok); `limited` is a failed
    call whose error or stderr names a limit, or a limit recorded by the round
    before (`review_limit.recorded`, no call made); `failed` is any other
    failure, quoted; `unknown` is no answer within the probe's timeout."""
    mark = review_limit.recorded(args.root, args.ticket)
    if mark:
        return PROBE_LIMITED, f"recorded in round {mark['round']}: {mark['error']}"
    exe = shutil.which("codex")
    if not exe:
        return PROBE_FAILED, "codex is not on PATH"
    timeout = args.probe_timeout
    cmd = command_for("codex", exe, args.root, PROBE_PROMPT, args.model, args.effort)
    stdout, stderr, code, timed_out = launch(cmd, args.root, timeout)
    _write_atomic(os.path.join(args.scratch, "probe-events.jsonl"), stdout)
    _write_atomic(os.path.join(args.scratch, "probe-stderr.txt"), stderr)
    message, error = review_verdict.codex_final_message(stdout)
    if code == 0 and not timed_out and (message or "").strip():
        return PROBE_OK, message.strip().splitlines()[0][:120]
    line = review_limit.limit_line(error or "", stderr)
    if line:
        return PROBE_LIMITED, line
    if timed_out:
        return PROBE_UNKNOWN, f"no answer within {timeout}s"
    tail = (stderr or "").strip().splitlines()[-1:] or [f"exit {code}"]
    return PROBE_FAILED, error or tail[0]


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
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--probe-timeout", type=int, default=PROBE_TIMEOUT)
    parser.add_argument("--allow-unverified", action="store_true",
                        help="review a tree the verify gate has not passed; recorded in "
                             "review.json as gate.overridden")
    args = parser.parse_args(argv)
    args.root = os.path.abspath(args.root)
    args.scratch = os.path.abspath(args.scratch)
    args.manifest = args.manifest or os.path.join(args.scratch, "manifest.json")

    try:
        review_ledger.check_ticket(args.ticket)
        if args.probe:
            if args.provider != "codex":
                parser.error("--probe is for the codex provider only")
            if args.reserve_only or args.round is not None:
                parser.error("--probe reserves nothing; it takes neither --reserve-only "
                             "nor --round")
            outcome, detail = probe(args)
            print(f"PROBE={outcome}")
            print("PROBE_DETAIL=" + " ".join(str(detail).splitlines()))
            return {PROBE_OK: EXIT_CLEAN, PROBE_LIMITED: EXIT_PROBE_LIMITED,
                    PROBE_FAILED: EXIT_PROBE_FAILED,
                    PROBE_UNKNOWN: EXIT_PROBE_UNKNOWN}[outcome]
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
