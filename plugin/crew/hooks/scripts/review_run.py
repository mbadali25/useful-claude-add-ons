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
and `prereview_gate` (questions 1-4 below), for every provider
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

METRICS ROW (L-0578). Once the ledger has accepted the round, and before
review.json, `review_metrics.record` appends the round's row to the main
checkout's `.crew/metrics.md` and a `review:` line says where, or why not and
the row to append by hand. It never changes the verdict or the exit code.
The row's std: token is the one `standards_gate` checked before the
reservation, kept in memory and in `<scratch>/reserved-std.json` for the
claude provider's second call - never recomputed after the review.
`--note codex-probe=<exit>` (claude) carries the probe's answer, so a Codex
limit the probe found live is labelled though it records no marker.

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
expected READ like a bundle part. The ledger row and review.json also carry
`webtest_open` for the auto-accept guard (L-0510): the number of open rows,
`review_ledger.WEBTEST_NA` when the check did not apply, or None when it
applied and its findings could not be read -- could not tell, never 0.

AUTO-ACCEPT (L-0510). The row and review.json carry `findings`, the
reviewer's SEVERITY lines verbatim. After a FINDINGS round a `review:
auto-accept:` line says whether `review_ledger.py --auto-accept` would take
it (`eligible`) or why not (`refused - <reason>`); this script never accepts.

FAILURE CLASS AND REFUNDS (T-0087). An INCOMPLETE round is classed by
`review_verdict.failure_class`: `tree` when a bundle or webtest reason was
added here, `tool` when the answer never arrived intact (timeout, unknown or
non-zero exit, empty output, a `codex:` stream error), else `reviewer`.
review.json carries `failure_class`, and `refunded` / `refund_refused` as the
ledger recorded them; a `review:` line says whether the round was refunded. A
refunded round still exits 3.

BEFORE ANY ROUND IS RESERVED, five questions, in this order (`preflight`
asks 1 and 2 in `_receipt_and_gate`, then 3 in `train_gate`; then
`prereview_gate`, then `standards_gate`):

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
  3. Once the clone's merge train is armed (`train_gate`, L-0526;
     `crew_train.py arm`): does this ticket hold the train? `crew_train.
     acquire` is asked; holding goes on. Waiting behind an overlapping
     ticket, `merge <base> first`, a train that could not be read, or any
     exception in the step is exit 6 with the reason on stderr and no round
     spent -- never a reservation on a tree another lane is landing over.
     An unarmed clone (state.json proven absent) is not asked and prints
     nothing. The train is taken BEFORE the pre-review checks, so they lint
     the tree that has the base merged in.
  4. Then (`prereview_gate`, L-0574): does the bundle add a linter finding
     its own base did not have (`review_checks.py`, configured under
     `preReview` in `.crew/verify.json`)? A NEW finding is exit 5, no round
     spent, and `--allow-unverified` does not override it. A check that could
     not run (missing tool, crash, timeout, bad output, a file the tool could
     not parse, a config it cannot read) is COULD NOT CHECK, never a pass:
     exit 5 too, unless `--allow-unverified`, which review.json records as
     `prereview.overridden`. Only an active incident stands both down, and
     logs a `prereview-checks` skip. No `preReview` key proceeds and says so.
  5. Only then (`standards_gate`, T-0085): is the standards self-check
     complete and stamped for this bundle? Missing or stale is exit 2, no
     round spent -- see STANDARDS SELF-CHECK above. A CLEAN receipt (1) never
     asks for a self-check, and a refusal at (2), (3) or (4) comes first.

Questions 3, 4 and 5 are not asked when the budget is already spent: the
reservation refuses that (exit 4) whatever they would say, and a ticket that
cannot gate never takes the train (it would hold it, and every overlapping
lane would wait on exit 6 behind it, for good). A holder refused after taking
the train (exit 5 from 4, exit 2 from 5) keeps holding it: the next review
re-confirms the hold, or `crew_train.py release --ticket <id>` frees it.
The Claude fallback's second call (`--round N --output`) records the round
the first call reserved and does not ask again; `--probe` never reaches the train.

Every round's review.json carries `gate` (the state observed at verdict time)
and `elapsed_s` (reservation to verdict, from the ledger's own timestamps), and
the `review:` summary line prints both. It also carries `prereview`: the
<scratch>/prereview.json question 3 wrote for this bundle, or
`{"result": "not-recorded", "reason": ...}` -- never a bare null.

Exit codes: 0 CLEAN; 1 FINDINGS; 3 INCOMPLETE; 4 budget refused
(NEEDS_REPLAN); 5 not run, verify gate not green or a pre-review check new or
could not check (no round spent); 6 not run, the merge train is armed and
this ticket does not hold it (waiting, `merge <base> first`, or the train
could not be read; no round spent); 2 usage or setup error, or the standards
self-check missing or stale -- not run, no round spent. The verify gate's
exit 5 is decided before exit 6, exit 6 before the pre-review checks' exit 5,
and all of them before exit 2 (self-check) is asked for. (`--probe` keeps its
own 5/6/7: it reserves nothing and never reaches the train.)
"""
import argparse
import datetime
import hashlib
import json
import os
import signal
import subprocess
import sys

import crew_common
import crew_incident
import crew_standards
import crew_state
import crew_train
import review_checks
import review_gate
import review_ledger
import review_limit
import review_metrics
import review_patch
import review_prompt
import review_verdict
import webtest_guard

EXIT_CLEAN, EXIT_FINDINGS, EXIT_USAGE, EXIT_INCOMPLETE, EXIT_REFUSED = 0, 1, 2, 3, 4
EXIT_UNVERIFIED = 5
EXIT_TRAIN = 6
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


def _one(value):
    return review_checks.one_line(value)


def _out(text):
    """Every stdout line review_run prints: control characters escaped
    (review_checks.one_line), so a path, reason or error can never start a
    line of its own (L-0574 review round 8 sweep). A newline is added."""
    sys.stdout.write(review_checks.one_line(text) + "\n")
    sys.stdout.flush()


def _err(text):
    """Every stderr message: one line, control characters escaped but the
    final newline, which every caller ends with."""
    body = text[:-1] if text.endswith("\n") else text
    sys.stderr.write(review_checks.one_line(body) + "\n")


def _read(path, base):
    """Text of a regular file inside `base`, through review_checks.read_regular
    (class b): a symlink at the file or at any directory between `base` and it,
    a FIFO or a device raises NotRegularFile, an OSError, instead of being
    followed or blocking (L-0574 review round 7)."""
    return review_checks.read_regular(path, base).decode("utf-8", errors="replace").replace(
        "\r\n", "\n").replace("\r", "\n")


def _trusted(path, scratch):
    """The directory a read of `path` is checked from: the scratch directory
    when `path` is inside it (where /crew:review puts the manifest, the
    output and the prompt), else the path's own directory, which is where the
    operator pointed it."""
    path, scratch = os.path.abspath(path), os.path.abspath(scratch)
    try:
        inside = os.path.commonpath([path, scratch]) == scratch
    except ValueError:  # another drive on Windows
        inside = False
    return scratch if inside else os.path.dirname(path)


def _part_base(path):
    """review_patch writes parts into `<out>.parts/`; the directory holding
    that directory is the one trusted, so `<out>.parts` itself is checked."""
    folder = os.path.dirname(os.path.abspath(path))
    return os.path.dirname(folder) if folder.endswith(".parts") else folder


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
    text = _read(prompt_path, os.path.dirname(os.path.abspath(prompt_path)))
    if len(text) <= INLINE_PROMPT_LIMIT and not through_batch_shim(exe):
        return text
    if len(text) > INLINE_PROMPT_LIMIT:
        _err(f"review-run: prompt is {len(text)} chars, over the inline limit; "
                         f"the reviewer is told to read {prompt_path}\n")
    else:
        _err(f"review-run: {os.path.basename(exe)} is a batch shim and cmd.exe ends "
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

    On Windows (L-0574 review round 8, the neighbour of review_checks'
    FIX :574) the provider runs in a job object: a timeout ends every process
    in it, a descendant whose leader already exited included, so nothing is
    left holding the pipe. Membership is by handle, never a reusable pid.
    """
    job = _reviewer_job()
    try:
        return _launch(job, cmd, root, timeout)
    finally:
        if job is not None:
            job.close()


def _reviewer_job():
    """A job object for the provider on Windows, or None (POSIX, or a job
    Windows would not make: the taskkill /T path below is then all there is,
    said on stderr). kill_on_close is off: like POSIX, a provider's
    leftovers after a clean exit are not this script's to end."""
    if not review_checks._WINDOWS:  # pylint: disable=protected-access
        return None
    try:
        return review_checks.new_job(kill_on_close=False)
    except OSError as exc:
        _err(f"review-run: no job object for the provider ({exc}); a timeout falls back to "
             "taskkill /T, which cannot reach a child whose parent already exited\n")
        return None


def _launch_flags(job):
    if review_checks._WINDOWS:  # pylint: disable=protected-access
        flags = subprocess.CREATE_NEW_PROCESS_GROUP
        if job is not None:
            flags |= review_checks._CREATE_SUSPENDED  # pylint: disable=protected-access
        return {"creationflags": flags}
    return {"start_new_session": True}


def _launch(job, cmd, root, timeout):
    try:
        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            cmd, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            **_launch_flags(job))
    except OSError as exc:
        return "", f"could not start {cmd[0]}: {exc}", None, False
    if job is not None:
        try:
            job.adopt(proc)
        except OSError as exc:
            proc.kill()
            proc.communicate()
            return "", f"could not put {cmd[0]} in its job object: {exc}", None, False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        notes, tree_ended = [], False
        if job is not None:
            # By handle: safe whether or not the leader has already exited.
            try:
                job.terminate()
                tree_ended = True
            except OSError as exc:
                notes.append(f"job termination failed ({exc})")
        escaped = False
        if proc.poll() is None:
            if review_checks._WINDOWS:  # pylint: disable=protected-access
                # Never os.killpg here: Windows has none (L-0605, review round
                # 10 FIX :400). Only a job's terminate() establishes that the
                # tree ended; taskkill /T walks parent pids, so even its exit 0
                # cannot reach a child whose parent already exited.
                if not tree_ended:
                    _windows_taskkill(proc, notes)
                try:
                    proc.kill()  # TerminateProcess by the handle Popen holds
                except OSError:
                    pass  # already exited
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        else:
            # Leader already exited and been reaped: its pid (and any pgid
            # numbered the same) is free for reuse, so no bare-number signal
            # is safe here. Without a job, whatever kept the pipe open is on
            # its own; with one, job.terminate() above already ended it.
            escaped = job is None
        if review_checks._WINDOWS:  # pylint: disable=protected-access
            escaped = escaped or not tree_ended
        try:
            stdout, stderr = proc.communicate(timeout=POST_KILL_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            escaped = True
            stdout = _decode_partial(exc.output)
            stderr = _decode_partial(exc.stderr)
        if escaped:
            why = (f" ({'; '.join(notes)}: only the reviewer process itself is known to have "
                   "ended)") if notes else ""
            stderr = (stderr or "") + (
                "\nreview-run: a descendant process may have escaped the "
                f"{timeout}s timeout and is still holding the output pipe "
                f"open{why}; proceeding with whatever output had already arrived\n")
        return stdout, stderr, None, True
    return stdout, stderr, proc.returncode, False


def _windows_taskkill(proc, notes):
    """`taskkill /T /F` the leader's tree, adding to `notes` why the tree is
    still not known to have ended. Never raises (L-0605)."""
    killer = review_checks.taskkill()
    if not killer:
        notes.append("no taskkill.exe")
        return
    # Absolute, never a bare `taskkill` (L-0574 round-7 sweep).
    try:
        done = subprocess.run([killer, "/T", "/F", "/PID", str(proc.pid)],
                              capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        notes.append(f"taskkill failed ({exc})")
        return
    notes.append("no job object: taskkill /T cannot reach a child whose parent already exited"
                 if done.returncode == 0 else f"taskkill exited {done.returncode}")


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
            data = review_checks.read_regular(row["path"], _part_base(row["path"]))
        except (OSError, KeyError, TypeError, ValueError) as exc:
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
        doc = json.loads(_read(webtest_guard.findings_path(root, ticket), root))
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


def _manifest_problem(manifest):
    """The first field `finish` and its callees read that is malformed, or None."""
    if not isinstance(manifest, dict):
        return "not a JSON object"
    parts = manifest.get("parts")
    if parts is not None:
        if not isinstance(parts, list):
            return "parts is not a list"
        for part in parts:
            if not isinstance(part, dict):
                return "a part is not an object"
            path, name = part.get("path"), part.get("name")
            if not ((isinstance(path, str) and path) or (not path and isinstance(name, str)
                                                         and name)):
                return "a part has no non-empty path or name"
            if any(isinstance(v, str) and "\0" in v for v in (path, name)):
                return "a part's path or name holds a NUL"
    for key in ("bundle_sha256", "head", "base"):
        if manifest.get(key) is not None and not isinstance(manifest[key], str):
            return f"{key} is not a string"
    return None


def _finish_manifest(args):
    """(manifest, reasons). After a reservation the manifest may have been
    swapped: unreadable or malformed, it is `{}` and a tree reason, so the
    round is INCOMPLETE and review.json is still written (L-0605, the
    neighbour of review round 10 FIX :955)."""
    try:
        manifest = json.loads(_read(args.manifest, _trusted(args.manifest, args.scratch)))
    except (OSError, ValueError) as exc:
        return {}, [f"the manifest {args.manifest} could not be read ({exc})"]
    problem = _manifest_problem(manifest)
    if problem:
        return {}, [f"the manifest {args.manifest} is malformed ({problem})"]
    return manifest, []


def _webtest_open(rows, webtest_record):
    """The ledger's `webtest_open`: open rows counted, WEBTEST_NA when the
    check did not apply (no record), None when it applied and could not be
    read -- `rows is None` alone cannot tell those two apart."""
    if rows is not None:
        return len(rows)
    return review_ledger.WEBTEST_NA if webtest_record is None else None


def auto_accept_line(root, ticket):
    """The `review: auto-accept:` line, from the ledger as now recorded."""
    data, state = review_ledger.load(review_ledger.ledger_path(root, ticket))
    refusal = (review_ledger.auto_accept_refusal(data, ticket) if state == "ok"
               else f"ledger is {state}: could not tell")
    if refusal:
        return f"review: auto-accept: refused - {refusal}"
    return (f"review: auto-accept: eligible (run review_ledger.py --ticket {ticket} "
            "--auto-accept --follow-up <id>)")


def finish(args, number, output, exit_code, timed_out, extra_reasons=()):
    """Verdict -> ledger -> review.json. Returns the process exit code."""
    manifest, manifest_reasons = _finish_manifest(args)
    # The parts as the prompt lists them -- full paths -- so a READ line that
    # echoes the listed path counts (T-0079). A part with no path falls back to
    # its name, which review_verdict still matches exactly.
    parts = [p.get("path") or p["name"] for p in manifest.get("parts") or []]
    if os.path.exists(os.path.join(args.scratch, review_prompt.WEBTEST_FINDINGS_FILE)):
        parts.append(os.path.join(args.scratch, review_prompt.WEBTEST_FINDINGS_FILE))
    rows, webtest_record, webtest_reasons = webtest_check(args.root, args.ticket, manifest)
    stream_reasons = list(extra_reasons)
    extra_reasons = list(extra_reasons) + bundle_problems(manifest)
    extra_reasons += manifest_reasons
    extra_reasons += webtest_reasons
    # The outside reasons go INTO the parse, so a stray line is never
    # recovered on a round they make INCOMPLETE (L-0576).
    result = review_verdict.parse(output, exit_code, timed_out, parts,
                                  prior_reasons=extra_reasons)
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
        "reasons": result["reasons"],
        # L-0510's contract: an int on every round, 0 when none were ignored;
        # the lines themselves, verbatim, are `ignored_text` (L-0576).
        "ignored_lines": len(result["ignored"]), "ignored_text": result["ignored"],
        "parts_expected": parts,
        "parts_missing": result["parts_missing"],
        "provider": args.provider, "model": args.model or None,
        "model_family": crew_state.family(args.provider, args.model),
        "bundle_sha256": manifest.get("bundle_sha256"),
        "base": manifest.get("base"), "head": manifest.get("head"),
        "exit_code": exit_code, "timed_out": timed_out,
        "webtest_findings": rows, "webtest_check": webtest_record,
        "findings": result["findings"], "webtest_open": _webtest_open(rows, webtest_record),
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
    review["prereview"] = review_checks.recorded(args.scratch, manifest.get("bundle_sha256"),
                                                 args.ticket, number)
    # Before review.json: the row is owed once the ledger holds the round.
    metrics_line = review_metrics.record(args.root, args.ticket, number, review,
                                         review_metrics.reserved_std(args, number),
                                         getattr(args, "note", "") or "")
    work_dir = args.work_dir or os.path.join(args.root, ".work", "tickets", args.ticket)
    _write_atomic(os.path.join(work_dir, "review.json"),
                  json.dumps(review, indent=2, sort_keys=True) + "\n")
    counts = result["counts"]
    # The budget as the ledger charges it: a refunded round is a round number,
    # never a unit of budget, so "round 3/2" would read as over budget.
    spent, refunded = ledger.get("rounds_spent"), ledger.get("rounds_refunded")
    budget = (f"{spent if isinstance(spent, int) else '?'} of {review_ledger.BUDGET} "
              f"budget rounds used" + (f", {refunded} refunded" if refunded else ""))
    # Kept as print(): main's sabotage suites pin this line. Every value in
    # it is internal (the verdict constant, counts) or escaped here.
    print(f"review: {result['verdict']} round {number}, {budget} "
          f"({counts['BLOCK']} BLOCK, {counts['FIX']} FIX, {counts['NIT']} NIT) "
          f"{_one(args.provider)}/{_one(args.model or 'default')} "
          f"family={_one(review['model_family'])} "
          f"ledger={_one(state)} gate={_one(review['gate']['state'])} "
          f"elapsed={_fmt_elapsed(review['elapsed_s'])}")
    _out(metrics_line)
    for reason in result["reasons"]:
        _out(f"review: INCOMPLETE because {reason}")
    # Kept as print() (a pinned line): the verdict is a constant, the
    # ignored line goes out through !r, which escapes its newlines.
    if result["ignored"]:
        print(f"review: {result['verdict']} kept; {len(result['ignored'])} line(s) outside the "
              f"contract were ignored, first: {result['ignored'][0].strip()[:120]!r} - read them in "
              "out.txt and report them with the findings")
    if failure == review_verdict.TOOL and review["refunded"]:
        _out(f"review: round {number} was a tool failure ({result['reasons'][0]}); refunded - "
              f"{ledger.get('rounds_spent')} of {review_ledger.BUDGET} budget rounds used")
    elif failure == review_verdict.TOOL:
        _out(f"review: round {number} was a tool failure; NOT refunded - "
              f"{review['refund_refused']}")
    elif failure:
        _out(f"review: round {number} is INCOMPLETE ({failure}) and counts against the budget")
    if webtest_verdict:
        _out(f"review: {result['verdict']} because {webtest_verdict}")
    if result["verdict"] == review_verdict.FINDINGS:
        _out(auto_accept_line(args.root, args.ticket))
    return {review_verdict.CLEAN: EXIT_CLEAN, review_verdict.FINDINGS: EXIT_FINDINGS}.get(
        result["verdict"], EXIT_INCOMPLETE)


def gate_record(args):
    """The gate state for review.json: observed now, plus whether this round
    was told to go ahead regardless."""
    state, reason = review_gate.accepted_state(args.root)
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
    having reserved nothing. See BEFORE ANY ROUND IS RESERVED above:
    questions 1 and 2 (`_receipt_and_gate`), then 3 (`train_gate`) unless
    the budget is already spent (`_budget_spent`): then `reserve` refuses it
    (exit 4) and the train is never taken, so a ticket that cannot gate can
    never hold the train other lanes wait behind."""
    short = _receipt_and_gate(args)
    if short is not None:
        return short
    if _budget_spent(args):
        return None
    return train_gate(args)


def _budget_spent(args):
    """True when the ledger already reads NEEDS_REPLAN or no rounds left, or
    cannot be read at all (review of ee01a3ca: `reserve` refuses an unreadable
    ledger with exit 4 too, so taking the train first would hold it for a
    ticket that cannot run a round)."""
    ledger = review_ledger.status(args.root, args.ticket)
    return (ledger.get("state") in (review_ledger.NEEDS_REPLAN, review_ledger.UNKNOWN)
            or ledger.get("rounds_left") == 0)


def _receipt_and_gate(args):
    """Questions 1 and 2: None to go on, or the exit code to stop with."""
    ok, message = review_ledger.check_receipt(args.root, args.ticket)
    data, _ = review_ledger._load(review_ledger.ledger_path(args.root, args.ticket))  # pylint: disable=protected-access
    if ok and (data.get("receipt") or {}).get("kind") == "clean":
        _out(f"review: CLEAN from the existing receipt ({message}) - nothing in the bundle "
              "changed since that clean round, so no round was spent")
        if args.provider not in LAUNCHED:
            _out("ALREADY_CLEAN=1")
        return EXIT_CLEAN
    state, reason = review_gate.accepted_state(args.root)
    if state in (review_gate.UNVERIFIED, review_gate.UNKNOWN):
        if args.allow_unverified:
            _err(f"review-run: gate {state}: {reason}. Reviewing anyway "
                             "(--allow-unverified); review.json records the override\n")
            return None
        _err(
            f"review-run: gate {state}: {reason}. No round reserved. Run the verify gate on "
            f"this tree first (bash \"{VERIFY_GATE}\" </dev/null, or end the turn so the "
            "Stop gate runs), then review again. "
            "--allow-unverified reviews it anyway and records that it did.\n")
        return EXIT_UNVERIFIED
    _err(f"review-run: gate {state}: {reason}\n")
    return None


def train_gate(args):
    """None to go on; EXIT_TRAIN to refuse with nothing spent. See question 3
    above. An unarmed clone returns None and prints nothing; anything this
    step cannot vouch for -- including an exception -- refuses."""
    try:
        # Review of 84c841e6: a state.json that is not a regular file (a FIFO
        # would block crew_train's plain open) is could-not-tell.
        odd = review_checks.not_a_regular_file(
            os.path.join(crew_train.train_dir(args.root), "state.json"))
        if odd:
            _err(f"review-run: train: could not tell ({odd}); no round reserved\n")
            return EXIT_TRAIN
        _state, where, why = crew_train.load(args.root)
        if where == "absent":
            return None
        if where != "ok":
            _err(f"review-run: train: could not tell ({why}); no round reserved\n")
            return EXIT_TRAIN
        code, lines = crew_train.acquire(args.root, args.ticket)
    except Exception as exc:  # noqa: BLE001 - boundary  pylint: disable=broad-exception-caught
        # Boundary: an escaped exception would exit 1, which reads as FINDINGS.
        _err(f"review-run: train: could not tell ({type(exc).__name__}: {exc}); "
             "no round reserved\n")
        return EXIT_TRAIN
    for line in lines:
        _err(f"review-run: train: {line}\n")
    if code != crew_train.EXIT_OK:
        _err("review-run: train: no round reserved; the gate round runs once this ticket "
             "holds the train (crew_train.py status)\n")
        return EXIT_TRAIN
    return None


def standards_gate(args):
    """None to go on and reserve; EXIT_USAGE to refuse with nothing spent.

    The required standards self-check (T-0085, `crew_standards.py`) must be
    complete and stamped for exactly this bundle and this standards set. In an
    active incident the gate stands down and logs the skip, as verify-gate.sh
    does for its own."""
    problems, note = crew_standards.review_gate(args.root, args.ticket, args.manifest)
    # Escaped here because the write below is kept as it was (a pinned line).
    note = _one(note) if note else note
    if note:
        sys.stderr.write(f"review-run: {note}\n")
    if problems:
        incident = crew_incident.read_state(args.root, crew_state.load_config(args.root))
        if incident["active"]:
            crew_incident.log_skip(args.root, "standards-selfcheck", "; ".join(problems))
            _err(f"review-run: incident {incident['id']} is active; the standards "
                             "self-check stands down and the skip is logged\n")
            args.reserved_std = "std:none"
            return None
        for problem in problems:
            _err(f"review-run: self-check: {problem}\n")
        _err("review-run: answer .work/tickets/<id>/selfcheck.md, then run "
                         f"crew_standards.py stamp --root . --ticket {args.ticket}; nothing "
                         "launched, no round spent\n")
        return EXIT_USAGE
    # The token this round is reserved under: the row carries it, not a
    # recomputation after the review (L-0578 review round 2).
    args.reserved_std = review_metrics.std_from_note(note)
    return None


def prereview_gate(args):
    """None to go on and reserve; EXIT_UNVERIFIED to refuse with nothing spent.

    The pre-review checks (L-0574, `review_checks.py`): no new linter finding
    in the bundle against its own base. NEW findings refuse whatever else is
    true; COULD NOT CHECK refuses unless --allow-unverified; only an ACTIVE
    incident stands either down, and logs the skip. Every decision is written
    to <scratch>/prereview.json for `finish` to copy into review.json."""
    try:
        # One read of the manifest gives both the entries linted and the hash
        # recorded, so a replaced manifest cannot borrow these results.
        results, configured, bundle = review_checks.run_checks_bound(
            args.root, args.manifest, _trusted(args.manifest, args.scratch))
    except Exception as exc:  # noqa: BLE001 - boundary, see below  pylint: disable=broad-exception-caught
        # Boundary: an escaped exception would exit 1, which reads as FINDINGS.
        # No hash is trusted here: the record is written for no bundle at all.
        results, configured, bundle = [{"name": "pre-review", "status": review_checks.COULD_NOT,
                                        "files": 0, "new": [],
                                        "detail": f"{type(exc).__name__}: {exc}"}], True, None
    if not configured:
        _err(f"review-run: pre-review checks: none configured "
                         f"({review_checks.VERIFY_MAP} has no {review_checks.CONFIG_KEY})\n")
        args.prereview_staged = _record(args.scratch, bundle, [], False, False,
                                        configured=False)
        return None
    for line in review_checks.lines(results):
        _err(f"review-run: {line}\n")
    verdict = review_checks.overall(results)
    if verdict == review_checks.PASS:
        args.prereview_staged = _record(args.scratch, bundle, results, False, False)
        return None
    incident = crew_incident.read_state(args.root, crew_state.load_config(args.root))
    if incident["active"]:
        crew_incident.log_skip(args.root, "prereview-checks", f"{verdict}: " + "; ".join(
            f"{r['name']} {r['status']}" for r in results if r["status"] in (
                review_checks.FAIL, review_checks.COULD_NOT)))
        _err(f"review-run: incident {incident['id']} is active; the pre-review "
                         "checks stand down and the skip is logged\n")
        args.prereview_staged = _record(args.scratch, bundle, results, False, True)
        return None
    if verdict == review_checks.COULD_NOT and args.allow_unverified:
        _err("review-run: pre-review checks could not check everything; reviewing "
                         "anyway (--allow-unverified); review.json records the override\n")
        args.prereview_staged = _record(args.scratch, bundle, results, True, False)
        return None
    args.prereview_staged = _record(args.scratch, bundle, results, False, False)
    if verdict == review_checks.FAIL:
        _err("review-run: the bundle adds linter findings its base did not have. No "
                         "round reserved. Fix them (or suppress one with the tool's own inline "
                         "directive and a reason), then review again. --allow-unverified does "
                         "not override a new finding\n")
    else:
        _err("review-run: a pre-review check could not run, so this tree is not "
                         "known clean. No round reserved. Install or repair the tool and review "
                         "again, or pass --allow-unverified to review anyway (review.json "
                         "records the override)\n")
    return EXIT_UNVERIFIED


def _record(scratch, bundle, results, overridden, stood_down, configured=True):
    """Stage this run's record; a write that fails is said, never fatal: the
    decision is already made, and `finish` then reads `not-recorded`. Returns
    the staged path for _bind_record, or None."""
    try:
        return review_checks.record(scratch, bundle, results, overridden, stood_down,
                                    configured)
    except OSError as exc:
        _err(f"review-run: could not record the pre-review checks in {scratch} "
                         f"({exc}); review.json will say not-recorded\n")
        return None


def _bind_record(args, number):
    """Bind this run's staged record to the round `reserve` just gave it, so
    `finish` for that round reads it and no other run's (class d)."""
    staged = getattr(args, "prereview_staged", None)
    if not staged:
        return
    try:
        review_checks.bind_record(staged, args.scratch, args.ticket, number)
    except (OSError, ValueError) as exc:
        _err(f"review-run: could not bind the pre-review record to round {number} "
                         f"({exc}); review.json will say not-recorded\n")


def _keep_reserved_std(args, number):
    """Hand the reservation's std: token to the call that finishes the round:
    in memory for a launched provider, `<scratch>/reserved-std.json` for the
    claude provider's second call. A record that cannot be written leaves
    the row's token `std:unknown`, said here."""
    token = getattr(args, "reserved_std", None)
    if not token:
        return
    try:
        _write_atomic(os.path.join(args.scratch, review_metrics.RESERVED_STD_FILE),
                      json.dumps({"ticket": args.ticket, "round": number, "std": token}) + "\n")
    except OSError as exc:
        _err(f"review-run: could not record this round's std: token ({exc}); its "
                         "metrics row will say std:unknown\n")


def run(args):
    exe = prompt = None
    if args.provider in LAUNCHED:
        if args.provider == "copilot" and not args.model:
            _err("review-run: copilot needs --model (qa.copilot.model); an "
                             "unpinned Copilot is the author's family\n")
            return EXIT_USAGE
        exe = review_checks.resolve_executable(args.provider)
        if not exe:
            _err(f"review-run: {args.provider} is not on PATH; nothing launched, "
                             "no round spent\n")
            return EXIT_USAGE
        prompt = prompt_argument(os.path.join(args.scratch, "prompt.txt"), exe)

    short = preflight(args)
    if short is not None:
        return short

    # A spent budget is a precondition already known to fail (GEN-03): the
    # self-check cannot change it, so the budget refusal below answers first
    # rather than sending the author to answer and restamp for nothing.
    # `reserve` re-reads the ledger under its lock and is what refuses. One
    # predicate with the train's (review of 6ec829c9): an unreadable ledger
    # is refused by `reserve` too, so no later check answers first.
    if not _budget_spent(args):
        refused = prereview_gate(args)
        if refused is None:
            refused = standards_gate(args)
        if refused is not None:
            return refused

    ok, number, message = review_ledger.reserve(args.root, args.ticket, args.provider,
                                                args.model)
    _err(f"review-run: {message}\n")
    if not ok:
        return EXIT_REFUSED
    _bind_record(args, number)
    _keep_reserved_std(args, number)
    if args.provider not in LAUNCHED:
        _out(f"ROUND={number}")
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
        _out(f"review: codex usage limit in round {number}: {limit!r}; {then}")
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
    exe = review_checks.resolve_executable("codex")
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


# The providers this runner can launch. `qa.order` also names `kimi`, which has
# no runner here yet; commands/review.md filters `$ELIGIBLE` to this set (and
# says so on stderr) instead of relying on argparse's exit 2 to skip it.
PROVIDERS = ("codex", "copilot", "claude")


def main(argv):
    # Finding text and refusals quoting it reach stdout; see utf8_stdio.
    review_ledger.utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--provider", required=True, choices=PROVIDERS)
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
    parser.add_argument("--note", default="",
                        help="claude only: why this provider ran, for the metrics row "
                             "('codex-probe=<probe exit>'; 5 means a Codex limit)")
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
            _out(f"PROBE={outcome}")
            _out("PROBE_DETAIL=" + " ".join(str(detail).splitlines()))
            return {PROBE_OK: EXIT_CLEAN, PROBE_LIMITED: EXIT_PROBE_LIMITED,
                    PROBE_FAILED: EXIT_PROBE_FAILED,
                    PROBE_UNKNOWN: EXIT_PROBE_UNKNOWN}[outcome]
        if args.provider == "claude":
            if args.reserve_only:
                return run(args)
            if args.round is None or args.output is None or args.exit_code is None:
                parser.error("the claude provider takes --reserve-only, or --round N "
                             "--output FILE --exit-code N after the subagent ran")
            output, reasons = "", []
            if os.path.exists(args.output):
                # After the reservation: an output read_regular refuses is an
                # INCOMPLETE round, never an escaped exception (L-0605,
                # review round 10 FIX :955).
                try:
                    output = _read(args.output, _trusted(args.output, args.scratch))
                except OSError as exc:
                    reasons.append(f"the reviewer's output {args.output} could not be read "
                                   f"({exc})")
            return finish(args, args.round, output, args.exit_code, False, reasons)
        if args.reserve_only or args.round is not None:
            parser.error("--reserve-only and --round are for the claude provider only")
        return run(args)
    except review_ledger.LedgerError as exc:
        _err(f"review-run: {exc}\n")
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
