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
  kimi     `kimi -p ... -m <alias> --output-format stream-json --agent-file
           <scratch>/kimi-reviewer.md --skills-dir <scratch>/kimi-no-skills`,
           stdin closed, env from `kimi_probe.kimi_env` (no infinite retry, no
           KIMI_MODEL_* overrides). `kimi_probe.probe` runs BEFORE the round
           is reserved: any state but `ok` exits 2, names the state, and
           spends nothing. When the ledger's status already shows no round
           left, the run exits 4 before any probe or reservation: a Kimi
           round is never reserved unprobed. Prompt mode
           FORCES Kimi's permission mode to `auto` (2.1.1 refuses `-p` with
           --plan/--auto/--yolo), so no flag makes it read-only. Two controls
           stand in, for the probe call as for the review: the agent file
           allows Read, Grep and Glob and disallows Write, Edit and Bash, and
           the working tree is fingerprinted BEFORE THE PROBE and after the
           review exits. A tree that cannot be fingerprinted before the probe
           exits 2 (`unknown`) with no probe request and no round spent. A
           Kimi round is never retried in-process (L-0514): its probe and
           "before" fingerprint belong to one launch. A
           probe that changed it, whatever it answered, exits 8
           (EXIT_PROBE_CHANGED) naming the paths, with no round spent; a
           review that changed it is INCOMPLETE, naming the paths. Each call runs in a
           process group of its own, and whatever it leaves running there
           after it exits is killed before the tree is fingerprinted
           (`stop_survivors`); one that cannot be stopped is "could not tell".
           See `tree_fingerprint` and `reviewer_changes` for what is and is
           not seen. A write OUTSIDE the repository is caught by neither. The
           final message is read from the stream
           (`kimi_probe.final_message`, the one parser); its error text is redacted
           before it becomes a reason.
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

RETRY (L-0514). `run` relaunches a round the TOOL lost and the ledger
refunded, once per invocation (`RETRY_LIMIT`), after `RETRY_BACKOFF_SECONDS`,
with the same provider, model and effort: `preflight` is asked again and the
bundle re-hashed first, the failed round's out.txt, stderr.txt,
codex-events.jsonl and review.json are kept as `<name>.round<N>`, and a fresh
round is reserved. Only a refunded round retries, so a retry never spends
budget. Not retried, each with a `review: retry: not retried - <why>` line and
a `review: options:` line: a reviewer or tree INCOMPLETE, a refund the ledger
refused, a usage limit (the next round walks to the next cross-family provider), a
timeout (a retry could double a --timeout wait), a gate, receipt or bundle that
changed, and the second tool failure. The exit code is the last round's. The
claude provider records a round in two calls, so it never retries here.

THE FAMILY GUARD (L-0712) comes first, before any probe or question below.
`--authors "<families>"` (`/crew:review` passes `$AUTHORS`) names the author
families. A reviewer whose family (`crew_state.family(provider, model)`) is
one of them, or cannot be told, or an empty `--authors` (no author family
known), or an `--author-source unknown` (a dispatch whose family could not
be told: the families named are not all the authors), is refused with exit 2
and nothing reserved -- unless the operator
passes `--same-family "<reason>"`, which runs it with the ledger row labelled
`same_family` (and review.json and a CLEAN receipt with it). A
`--same-family` on a reviewer outside the author families is not a
same-family read: it is ignored, and said. `--probe` asks the guard first, so
a barred Codex costs no call. Without `--authors`, a reservation by a Claude
(or unknown-family) reviewer is refused the same way unless `--same-family`
labels it: crew's author is Claude unless proven otherwise, and `--round`
beside `--reserve-only` exempts nothing. Any other reviewer runs with the
guard not applied (callers that predate L-0712), and stderr says so on every
run. The recording call (`--round` alone) reserves nothing and never reaches
the guard. `review_ledger.py --reserve` asks this same guard.

BEFORE ANY ROUND IS RESERVED, five questions, in this order (`preflight`
asks 1 and 2 in `_receipt_and_gate`, then 3 in `train_gate`; then
`prereview_gate`, then `standards_gate`):

  1. Does a CLEAN receipt already cover this exact bundle
     (`review_ledger.check_receipt`, the check `/crew:done` gates on)? Then
     nothing has changed since a clean review, so no round is spent: the
     verdict is that receipt's CLEAN, said as such. An owner-accepted
     FINDINGS receipt does not short-circuit -- that is a person's call about
     one round, not a clean review of the tree. A receipt the delta gate KEPT
     across a catch-up (L-0522) short-circuits only once question 2 answers
     VERIFIED or NO_GATE: the merged tree is not the tree that was gated.
  2. Has the verify gate passed on this tree (`review_gate.gate_state`)? A
     tree it has not passed, or one whose state could not be read, is refused
     with exit 9 and no round spent: a reviewer's opinion on code the gate
     would refuse for free is the most expensive way to find out it is red.
     `--allow-unverified` reviews it anyway, and review.json says it did.
     No verify map, or a gate stood down, proceeds and says so.
  3. Once the clone's merge train is armed (`train_gate`, L-0526;
     `crew_train.py arm`): does this ticket hold the train? `crew_train.
     acquire` is asked; holding goes on. Waiting behind an overlapping
     ticket, `merge <base> first`, a train that could not be read, or any
     exception in the step is exit 10 with the reason on stderr and no round
     spent -- never a reservation on a tree another lane is landing over.
     An unarmed clone (state.json proven absent) is not asked and prints
     nothing. The train is taken BEFORE the pre-review checks, so they lint
     the tree that has the base merged in.
  4. Then (`prereview_gate`, L-0574): does the bundle add a linter finding
     its own base did not have (`review_checks.py`, configured under
     `preReview` in `.crew/verify.json`)? A NEW finding is exit 9, no round
     spent, and `--allow-unverified` does not override it. A check that could
     not run (missing tool, crash, timeout, bad output, a file the tool could
     not parse, a config it cannot read) is COULD NOT CHECK, never a pass:
     exit 9 too, unless `--allow-unverified`, which review.json records as
     `prereview.overridden`. Only an active incident stands both down, and
     logs a `prereview-checks` skip. No `preReview` key proceeds and says so.
  5. Only then (`standards_gate`, T-0085): is the standards self-check
     complete and stamped for this bundle? Missing or stale is exit 2, no
     round spent -- see STANDARDS SELF-CHECK above. A CLEAN receipt (1) never
     asks for a self-check, and a refusal at (2), (3) or (4) comes first.

Questions 3, 4 and 5 are not asked when the budget is already spent: the
reservation refuses that (exit 4) whatever they would say, and a ticket that
cannot gate never takes the train (it would hold it, and every overlapping
lane would wait on exit 10 behind it, for good). A holder refused after taking
the train (exit 9 from 4, exit 2 from 5) keeps holding it: the next review
re-confirms the hold, or `crew_train.py release --ticket <id>` frees it.
The Claude fallback's second call (`--round N --output`) records the round
the first call reserved and does not ask again; `--probe` never reaches the train.

Every round's review.json carries `gate` (the state observed at verdict time)
and `elapsed_s` (reservation to verdict, from the ledger's own timestamps), and
the `review:` summary line prints both. It also carries `prereview`: the
<scratch>/prereview.json question 3 wrote for this bundle, or
`{"result": "not-recorded", "reason": ...}` -- never a bare null.

Exit codes: 0 CLEAN; 1 FINDINGS; 3 INCOMPLETE; 4 budget refused
(NEEDS_REPLAN, or no round left per the status, before a Kimi probe); 8 the
Kimi probe changed the working tree (stop and report the named paths; do not
walk to the next provider); 9 not run, verify gate not green or a pre-review check new or
could not check (no round spent); 10 not run, the merge train is armed and
this ticket does not hold it (waiting, `merge <base> first`, or the train
could not be read; no round spent); 2 usage or setup error, or the standards
self-check missing or stale, or a gate that could not run or a ledger that
moved since the gate decision (L-0518) -- not run, no round spent. The verify
gate's exit 9 is decided before exit 10, exit 10 before the pre-review checks'
exit 9, and all of them before exit 2 (self-check) is asked for. 5, 6 and 7
are `--probe`'s alone (L-0528): no two EXIT_* constants share a value, so the
train's exit is 10, not the 6 L-0526 first gave it (it reserves nothing and
`--probe` never reaches the train).
"""
import argparse
import datetime
import functools
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import time

import crew_common
import crew_freshness
import crew_incident
import crew_standards
import crew_state
import crew_train
import kimi_probe
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
EXIT_UNVERIFIED = 9
# The merge train is armed and this ticket does not hold it (L-0526).
EXIT_TRAIN = 10
# The Kimi probe changed the working tree (round 4 of T-0028). No round was
# reserved, but the tree is no longer the one the bundle was built from, so
# /crew:review stops and reports the named paths -- it must never walk on to
# the next provider, as it does on EXIT_USAGE. Distinct from every other code
# (L-0528's test_review_run_exit_codes_are_distinct).
EXIT_PROBE_CHANGED = 8
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
LAUNCHED = ("codex", "copilot", "kimi")
KIMI_TREE_CHANGED = ("kimi: the working tree changed during the review - a reviewer "
                     "that can write may have fixed instead of reported")
KIMI_PROBE_CHANGED = "kimi probe: the working tree changed while the probe ran"
# Named paths per reason; the rest are counted, so a mass write cannot bury
# the review.json it is reported in.
CHANGED_SHOWN = 10
# `git status --ignored` walks every ignored file (node_modules and all), so
# it gets longer than crew_common's 10s hook-path bound. A git that still does
# not answer is "could not tell", never a hang after the round is reserved.
SNAPSHOT_GIT_TIMEOUT = 120
KIMI_TREE_UNKNOWN = ("kimi: the working tree could not be fingerprinted, so a write by the "
                     "reviewer cannot be ruled out")
KIMI_SURVIVOR_UNKNOWN = ("kimi: a process the reviewer left running could not be stopped, so "
                         "a write after the check cannot be ruled out")
# Whether `stop_survivors` can probe a process group (POSIX). On Windows what
# Kimi left running is ended through its job object instead (`_end_job`), and
# a launch with no job there is could-not-tell (group review of L-0527).
KIMI_SURVIVORS_SEEN = os.name != "nt"
# The record `_launch` appends to `started` once it has ended a job.
_JOB_ENDED = "job-ended"
# What `reviewer_changes` sets aside when it is IGNORED both before and after:
# paths something other than the reviewer writes mid-review AND that no check
# crew runs reads back. Fixed on purpose -- never read from config the reviewer
# could write -- and pinned by
# test_review_run_kimi.py::test_set_aside_names_are_the_fixed_tuples.
#   IDE_DIRS      an editor's own state: a directory of that name, any depth.
#   CREW_LOGS     appended by crew's hooks in the DISPATCHING session:
#                 `.crew/guard.log` by the scope, role-write and cloud guards
#                 (crew_guards.py:313, crew_config.py:1074), and
#                 `.crew/.autoclear.log` by auto-clear and context-watch
#                 (crew_autocycle.py:205, context-watch.sh:96). A Kimi review
#                 longer than the Bash tool's cap runs in the background, so
#                 those hooks fire mid-review (round 3 of T-0028).
#   CREW_MARKERS  context-watch's `.crew/.handoff-requested` and
#                 `.crew/.autoclear-sent`, bare or `-<session key>`
#                 (context-watch.sh:59-60), written the same way.
IDE_DIRS = (".idea", ".vscode")
CREW_LOGS = (".crew/guard.log", ".crew/.autoclear.log")
CREW_MARKERS = (".crew/.handoff-requested", ".crew/.autoclear-sent")
# `-c` settings on every fingerprint git call; a `-c` beats every config file.
# `core.fsmonitor` would otherwise run whatever program `.git/config` names --
# which the fingerprint does not hash -- and take its word for what changed
# (judgement, not measured). Tracked files do not rely on git's answer at all:
# every one is hashed (see `tree_fingerprint`).
GIT_OVERRIDES = ("-c", "core.fsmonitor=false")
# A nested repository is fingerprinted by recursion, and a symlink is followed
# to what it resolves to; deeper than this is "could not tell".
NESTED_DEPTH = 8
# The fingerprint's own entries. A NUL cannot occur in a git path, so no file
# can collide with them (round 4 of T-0028: tracked files named `:HEAD` and
# `:index` were never hashed, because those were the keys).
HEAD_KEY, INDEX_KEY = "\0HEAD", "\0index"
_META_SHOWN = {HEAD_KEY: "(HEAD)", INDEX_KEY: "(the index)"}
# What graph.out may hold as a TRACKED file and still be set aside.
GRAPH_FILES = ("graph.json", "GRAPH_REPORT.md")
# Crew config: a reviewer write here always counts, even under graph.out -- it
# is where graph.out itself is configured.
CREW_CONFIG_PATHS = (".crew/crew.json", ".crew/config.json")
# The probe (T-0088): one minimal real Codex call, before any reservation.
PROBE_TIMEOUT = 120
PROBE_PROMPT = "Reply with exactly the word OK. Do not run any command and do not read any file."
EXIT_PROBE_LIMITED, EXIT_PROBE_FAILED, EXIT_PROBE_UNKNOWN = 5, 6, 7
# The in-process retry of a refunded tool round (L-0514): constants, never config.
RETRY_LIMIT = 1
RETRY_BACKOFF_SECONDS = 30
RETRY_KEPT = ("out.txt", "stderr.txt", "codex-events.jsonl")
RETRY_OPTIONS = ("review: options: rerun /crew:review (a round that was not refunded spends a "
                 "budget round), switch provider (qa.order), or replan")
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


def _git_bytes(root, args, env):
    """Raw stdout of one git call, or None when git failed, could not start,
    or did not answer within SNAPSHOT_GIT_TIMEOUT."""
    git = review_checks.resolve_executable("git")  # class a: never a bare `git`
    if not git:
        return None
    try:
        done = subprocess.run([git, *GIT_OVERRIDES, *args], cwd=root, env=env,
                              capture_output=True,
                              stdin=subprocess.DEVNULL, timeout=SNAPSHOT_GIT_TIMEOUT,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _inside(real, top):
    """True when the resolved `real` lies strictly inside the resolved `top`."""
    try:
        return real != top and os.path.commonpath([real, top]) == top
    except ValueError:  # another drive on Windows
        return False


def _link_digest(path, root, depth):
    """`link:<target>` and, after a NUL, the digest of what the link resolves
    to (round 4 of T-0028: a tracked link into ignored IDE state let its
    target change unseen, because only the target STRING was hashed): a
    regular file's content and mode, a directory inside `root` walked,
    `missing` when it dangles. None -- could not tell -- for a directory
    outside `root` (or with no `root` to check it against), or past
    NESTED_DEPTH links."""
    target = os.readlink(path)
    if depth >= NESTED_DEPTH:
        return None
    try:
        info = os.stat(path)
    except FileNotFoundError:
        return f"link:{target}\0missing"
    real = os.path.realpath(path)
    if stat.S_ISDIR(info.st_mode):
        if not root or not _inside(real, os.path.realpath(root)):
            return None
        resolved = _walk_digest(real, root, depth + 1)
    else:
        resolved = _path_digest(real, root, depth + 1)
    return None if resolved is None else f"link:{target}\0{resolved}"


def _digest_base(path, root):
    """The directory `read_regular` checks `path` from: the repository root
    as given when `path` lies under it, its resolved form for a link target
    (already resolved), else the path's own directory."""
    if root:
        for top in (os.path.abspath(root), os.path.realpath(root)):
            if _inside(os.path.abspath(path), top):
                return top
    return os.path.dirname(os.path.abspath(path))


def _path_digest(path, root=None, _depth=0):
    """What is at `path` now, never opening anything but a regular file:

      a regular file  `<content sha256>:<permission bits, octal>` -- the bits
                      so a chmod counts even where core.filemode=false hides
                      it from git (round 4 of T-0028)
      a symlink       `_link_digest`: its target and what it resolves to
      a directory     `dir`
      anything else   `special:<S_IFMT, octal>` -- a FIFO, socket or device is
                      recorded from `lstat` and never opened, so a FIFO cannot
                      block the walk (round 4)
      nothing there   `missing`

    None when it exists and cannot be read: an unreadable file is "could not
    tell", and two of those must not compare equal as "unchanged"."""
    try:
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode):
            return _link_digest(path, root, _depth)
        if stat.S_ISDIR(mode):
            return "dir"
        if not stat.S_ISREG(mode):
            return f"special:{stat.S_IFMT(mode):o}"
        # Class b (L-0574): through read_regular, which never follows a link
        # and never blocks on a FIFO swapped in after the lstat.
        data = review_checks.read_regular(path, _digest_base(path, root))
        return f"{hashlib.sha256(data).hexdigest()}:{stat.S_IMODE(mode):o}"
    except FileNotFoundError:
        return "missing"
    except OSError:
        return None


def _walk_digest(path, root=None, _depth=0):
    """A directory's contents, walked without following a symlink: a sha256
    over each entry's relative path and `_path_digest` (so a link inside is
    digested with what it resolves to). None when an entry cannot be read or
    the walk itself fails."""
    rows, failed = [], []
    for top, dirs, files in os.walk(path, onerror=failed.append):
        dirs.sort()
        for name in sorted(dirs + files):
            full = os.path.join(top, name)
            digest = _path_digest(full, root, _depth)
            if digest is None:
                return None
            rows.append(f"{os.path.relpath(full, path)}\0{digest}")
    if failed:
        return None
    return "walk:" + hashlib.sha256("\n".join(rows).encode("utf-8", "surrogateescape")).hexdigest()


def _entry_digest(root, rel, problems, depth):
    """`_path_digest` for one listed path, except that a DIRECTORY is never the
    constant `dir` (round 3 of T-0028: a dirty submodule, or a nested clone,
    stayed `dir` whatever changed inside it). A directory holding `.git` is
    fingerprinted as the repository it is -- when git agrees it is one rooted
    there -- and any other directory (an uninitialised submodule, whose files
    no `git status` mode lists) is walked."""
    path = os.path.join(root, rel)
    digest = _path_digest(path, root)
    if digest != "dir":
        return digest
    if not os.path.lexists(os.path.join(path, ".git")):
        return _walk_digest(path, root)
    top = crew_common.git_out(path, "rev-parse", "--show-toplevel")
    if depth >= NESTED_DEPTH or not top or \
            os.path.normcase(os.path.realpath(top)) != os.path.normcase(os.path.realpath(path)):
        if problems is not None:
            problems.append(f"{rel} holds a .git that is not a repository rooted there, "
                            f"or is nested more than {NESTED_DEPTH} deep")
        return None
    inner = tree_fingerprint(path, problems, _depth=depth + 1)
    if inner is None:
        return None
    return "repo:" + hashlib.sha256(json.dumps(inner, sort_keys=True).encode(
        "utf-8", "surrogateescape")).hexdigest()


def tree_fingerprint(root, problems=None, _depth=0):
    """The working tree's state as `{path: "<XY> <digest>"}` (`_path_digest`:
    content and mode bits, a link with its target, a special file never
    opened), plus HEAD_KEY and INDEX_KEY -- or None when it cannot be taken.

    EVERY TRACKED FILE is in it, contents hashed, whatever `git status` says
    of it (`git ls-files --stage`, code `--` when status did not list it).
    Round 3 of T-0028 found an edit to a tracked file flagged skip-worktree or
    assume-unchanged unseen, and (measured) so was a same-size rewrite that
    restores the mtime once `.git/config` sets core.trustctime=false or
    core.checkStat=minimal: git answered "clean" and nothing re-read the file.
    Every path `git status` lists is in it too, CONTENTS hashed: modified,
    untracked and IGNORED files alike (`--untracked-files=all
    --ignored=traditional` lists each file inside an ignored directory, not
    the directory; `--no-renames` keeps each entry one path). Round 1 found
    the earlier digest hashed only an untracked file's status LINE and skipped
    ignored files. A directory is fingerprinted as the nested repository or
    submodule it is, or walked (`_entry_digest`). HEAD_KEY is there so a
    reviewer that COMMITTED its edit is seen, INDEX_KEY (every staged entry,
    blob id included) so one that only staged is; both hold a NUL, so no path
    can collide with them (round 4). `.work/` is excluded at the
    top level -- the scratch directory, review.json and the handoff live
    there. Taken with GIT_OPTIONAL_LOCKS=0 so taking it cannot itself change
    the index.

    NOT SEEN: a write outside the repository, and a change inside `.git`
    other than HEAD and the index (a hook, a config). None when any git call
    fails or times out, or a listed file cannot be read: "could not tell" is
    its own answer, never a value two failures would compare equal on. When
    `problems` is a list, the reason for a None is appended to it."""
    def unknown(reason):
        if problems is not None:
            problems.append(reason)

    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    head = crew_common.git_out(root, "rev-parse", "HEAD")
    if not head and _depth and crew_common.git_out(root, "rev-parse", "--git-dir"):
        head = "unborn"  # a nested repository with no commit yet
    if not head:
        unknown("HEAD could not be read (not a git repository?)")
        return None
    scope = ["--", "."] if _depth else ["--", ".", ":(exclude).work"]
    status = _git_bytes(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all",
                               "--no-renames",
                               "--ignored=traditional", *scope], env)
    staged = _git_bytes(root, ["ls-files", "--stage", "-z", *scope], env)
    if status is None or staged is None:
        unknown("git status or git ls-files failed or timed out")
        return None
    snapshot = {HEAD_KEY: head, INDEX_KEY: hashlib.sha256(staged).hexdigest()}
    listed = [(entry[:2].decode("ascii", "replace"), entry[3:])
              for entry in status.split(b"\0") if len(entry) >= 4]
    listed += [("--", entry.split(b"\t", 1)[1]) for entry in staged.split(b"\0")
               if b"\t" in entry]
    seen = set()
    for code, raw in listed:
        rel = os.fsdecode(raw).rstrip("/")
        if rel in seen:
            continue  # status listed it first, with its code
        seen.add(rel)
        digest = _entry_digest(root, rel, problems, _depth)
        if digest is None:
            unknown(f"{rel} exists and cannot be read")
            return None
        snapshot[rel] = f"{code} {digest}"
    return snapshot


def graph_out(root):
    """`graph.out` as a repo-relative, `/`-separated directory, or None.

    Resolved the way `crew_freshness._read_graph` and `crew_refresh_check`
    resolve it: `crew.json`, else `config.json`, in the `.crew/` that
    `crew_common.repo_config_dir` names -- so a linked lane worktree with no
    config of its own reads the main checkout's -- and None when that
    resolver answers `unknown` (nothing set aside); a config file that
    exists but cannot be read, is not valid JSON, or is not an object is
    None too (round 5 of T-0028: it had fallen back to `graphify-out`); a
    missing or wrong-typed value is `graphify-out`; `contained_path` keeps it inside the
    repository. None when it lands on the root or in `.git`, or a symlink
    moves it -- an exemption for one generated directory must never widen to
    the tree. None too, since round 4 of T-0028, when the directory could
    hold a check input: it is `.crew` or lies under a `.crew`, it contains a
    `.crew`, or it holds a tracked file other than GRAPH_FILES (read with
    `git ls-files` beside the "before" fingerprint; a git that does not answer
    is None as well). graph.out set to `.crew` had excused a rewrite of
    `.crew/verify.json`."""
    top = os.path.realpath(root)
    crew_dir, source, _detail = crew_common.repo_config_dir(top)
    if source == crew_common.SOURCE_UNKNOWN:
        return None
    cfg = {}
    for name in crew_common.CONFIG_NAMES:
        path = os.path.join(crew_dir, name)
        try:  # class b: through read_regular
            text = review_checks.read_regular(path, crew_dir).decode("utf-8-sig")  # as read_text
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError):
            return None  # round 5 of T-0028: unreadable is could-not-tell
        try:
            cfg = json.loads(text)
        except ValueError:
            return None  # round 5 of T-0028: invalid JSON sets nothing aside
        if not isinstance(cfg, dict):
            return None
        break
    value = crew_common.dict_or_empty(crew_common.dict_or_empty(cfg).get("graph")).get("out")
    if not isinstance(value, str) or not value:
        value = crew_freshness.GRAPH_OUT_DEFAULT
    real = crew_freshness.contained_path(top, value, crew_freshness.GRAPH_OUT_DEFAULT)
    named = {os.path.normcase(os.path.normpath(os.path.join(top, v)))
             for v in (value, crew_freshness.GRAPH_OUT_DEFAULT)}
    if os.path.normcase(real) not in named:
        return None
    rel = os.path.relpath(real, top).replace("\\", "/")
    if rel in ("", ".") or rel.split("/", 1)[0] in ("..", ".git"):
        return None
    if ".crew" in rel.split("/"):
        return None
    for _dir, dirs, _files in os.walk(real):
        if ".crew" in dirs:
            return None
    tracked = _git_bytes(top, ["ls-files", "-z", "--", ":(literal)" + rel],
                         dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    if tracked is None or any(os.fsdecode(name) not in (f"{rel}/{f}" for f in GRAPH_FILES)
                              for name in tracked.split(b"\0") if name):
        return None
    return rel


def _under(rel, directory):
    """True when `rel` lies strictly under `directory`, segment by segment:
    `graphify-outX/a` is not under `graphify-out`."""
    parts, stem = rel.split("/"), directory.split("/")
    return len(parts) > len(stem) and parts[:len(stem)] == stem


def _not_a_check_input(rel):
    """True when `rel` is one of the paths `reviewer_changes` may set aside:
    strictly under an IDE_DIRS directory, matched by whole segment at any depth
    (`pkg/.idea/x` is, `my.idea/x` and a bare `.idea` are not); exactly one of
    CREW_LOGS; or a CREW_MARKERS name, bare or with a `-<session key>` that
    holds no `/`."""
    parts = rel.split("/")
    if any(part in IDE_DIRS for part in parts[:-1]):
        return True
    if rel in CREW_LOGS or rel in CREW_MARKERS:
        return True
    return any(rel.startswith(marker + "-") and "/" not in rel[len(marker) + 1:]
               for marker in CREW_MARKERS)


def _ignored_throughout(before, after, rel):
    """True when every state `rel` has in the two fingerprints is IGNORED
    (`!!`); a path that was or became tracked or untracked is not."""
    states = [s for s in (before.get(rel), after.get(rel)) if s is not None]
    return bool(states) and all(s.startswith("!! ") for s in states)


def reviewer_changes(before, after, graph):
    """(changed, set_aside): the paths whose state differs between two
    `tree_fingerprint`s, split into those the reviewer is answerable for and
    those set aside -- under `graph`, or ignored throughout and
    `_not_a_check_input`.

    `graph` is graph.out as resolved BEFORE the reviewer ran (`run` does it
    once, beside the "before" fingerprint). Round 2 of T-0028 found it read
    after the review, from the tree the reviewer could write: writing
    `.crew/crew.json` = {"graph":{"out":".crew"}} then excused every other
    write under `.crew/`. `.crew/crew.json` and `.crew/config.json`
    (CREW_CONFIG_PATHS) are never set aside, whatever `graph` is.

    WHAT ELSE IS SET ASIDE, AND WHAT IS NOT. The fingerprint hashes ignored
    files (round 1), so any other writer to an ignored path spends the round.
    A path is set aside only when it is IGNORED in both fingerprints (a path
    that was or became tracked or untracked -- `.git/info/exclude` is not
    hashed, so a reviewer can flip it -- counts) AND no check crew runs reads
    it back: an IDE's own directory, crew's hook logs and context markers
    (IDE_DIRS, CREW_LOGS, CREW_MARKERS; round 3). Tool caches are NOT set
    aside, whatever round 2 did: CPython runs a `__pycache__` .pyc whose header
    matches its source, so a write there changes what the tests execute
    (round 3), and every other cache has the same shape -- `.pytest_cache`
    steers `--lf`/`--sw`, ruff and mypy trust a cached verdict, a bundler's
    `node_modules/.cache` holds output it runs. The cost is smaller than
    round 2 feared, measured: a second pytest run over an unchanged tree
    rewrote no byte under `__pycache__/` or `.pytest_cache/`, and only a
    CONTENT change counts. Nor are crew's gate inputs set aside
    (`.crew/.verify-verified-at`, `.verify-gate.fingerprint`, `.record.json`,
    `.timings.json`, `.scope-base`): a forged one narrows the verify gate. The
    verify gate rewrites its marker on every clean Stop, but at an unchanged
    HEAD with the same sha, which is no change (judgement from verify-gate.sh
    :122 and its fingerprint skip; not measured end to end).

    WHY `graph.out` IS SET ASIDE, and nothing else. graphify's post-commit and
    post-checkout hooks rebuild it IN THE BACKGROUND, and the normal order is
    commit, then review -- so the rebuild routinely lands mid-review and spent
    the round as INCOMPLETE with no reviewer write at all (round 1 of
    T-0028). Waiting for the rebuild instead was rejected: the hooks are
    machine-local (`.git/hooks` is untracked), write no lock and no pid
    crew could wait on, and build first and write last, so a quiet tree before
    launch proves nothing. Setting the directory aside is safe for the one
    thing this fingerprint exists for -- a reviewer that FIXED instead of
    reported: graph.out is generated, holds no code under review, and is
    overwritten by the next rebuild, so a write there fixes nothing. Every
    other path, the code map and the diagrams included, still counts, and
    HEAD_KEY and INDEX_KEY always do. `graph_out` refuses a directory that
    could hold a check input (round 4)."""
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    set_aside = []
    for path in changed:
        if path in (HEAD_KEY, INDEX_KEY) or path in CREW_CONFIG_PATHS:
            continue
        if graph and _under(path, graph):
            set_aside.append(path)
        elif _ignored_throughout(before, after, path) and _not_a_check_input(path):
            set_aside.append(path)
    return [p for p in changed if p not in set_aside], set_aside


def _named(paths):
    shown = ", ".join(_META_SHOWN.get(p, p) for p in paths[:CHANGED_SHOWN])
    more = len(paths) - CHANGED_SHOWN
    return shown + (f" and {more} more" if more > 0 else "")


def _round_available(root, ticket):
    """False when the ledger already shows the next reservation will be
    refused -- no round left, NEEDS_REPLAN, or unreadable. A read without the
    lock, so it only ever skips work `reserve` would refuse; `reserve` stays
    the authority either way."""
    status = review_ledger.status(root, ticket)
    return (status.get("state") not in (review_ledger.NEEDS_REPLAN, review_ledger.UNKNOWN)
            and status.get("rounds_left", 0) > 0)


def command_for(provider, exe, root, prompt, model, effort, scratch=None):
    if provider == "kimi":
        return [exe, "-p", prompt, "-m", model, "--output-format", "stream-json",
                *kimi_probe.read_only_flags(scratch)]
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


def launch(cmd, root, timeout, env=None, started=None):
    """(stdout, stderr, exit_code, timed_out). stdin is always closed. When
    `started` is a list, the leader's pid -- its process group's id on POSIX
    -- is appended to it once the process exists (see `stop_survivors`).

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
        return _launch(job, cmd, root, timeout, env, started)
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


def _launch(job, cmd, root, timeout, env=None, started=None):  # pylint: disable=too-many-arguments,too-many-positional-arguments
    try:
        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            cmd, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            env=env, **_launch_flags(job))
    except OSError as exc:
        return "", f"could not start {cmd[0]}: {exc}", None, False
    if started is not None:
        started.append(proc.pid)
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
        if job is not None and started is not None:
            started.append(_end_job(job))  # a caller watching survivors (Kimi)
        if escaped:
            why = (f" ({'; '.join(notes)}: only the reviewer process itself is known to have "
                   "ended)") if notes else ""
            stderr = (stderr or "") + (
                "\nreview-run: a descendant process may have escaped the "
                f"{timeout}s timeout and is still holding the output pipe "
                f"open{why}; proceeding with whatever output had already arrived\n")
        return stdout, stderr, None, True
    if job is not None and started is not None:
        started.append(_end_job(job))
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


def _end_job(job):
    """After a leader exited normally on Windows, for a caller that watches
    survivors (Kimi passes `started`): end what is still in the job and wait
    for it to empty, as `stop_survivors` does for a POSIX group (group review
    of L-0527: kill_on_close is off, so a child left running could write after
    the "after" fingerprint). (_JOB_ENDED, killed, unknown_reason); a job
    that cannot be asked, or does not empty within POST_KILL_TIMEOUT, is
    could-not-tell."""
    try:
        if not job.active_processes():
            return _JOB_ENDED, False, None
        job.terminate()
        deadline = time.monotonic() + POST_KILL_TIMEOUT
        while job.active_processes():
            if time.monotonic() >= deadline:
                return _JOB_ENDED, True, KIMI_SURVIVOR_UNKNOWN
            time.sleep(0.05)
    except OSError:
        return _JOB_ENDED, False, KIMI_SURVIVOR_UNKNOWN
    return _JOB_ENDED, True, None


def _group_alive(pgid):
    """True when a process that is not a zombie is still in process group
    `pgid`. Read from /proc where there is one -- a zombie is dead but still
    answers signal 0 until something reaps it -- else signal 0."""
    if os.path.isdir("/proc/self"):
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                raw = review_checks.read_regular(f"/proc/{name}/stat", "/proc")  # class b
                fields = raw.decode("ascii", "replace").rsplit(")", 1)[1].split()
            except (OSError, IndexError):
                continue
            if len(fields) > 2 and fields[2] == str(pgid) and fields[0] not in ("Z", "X"):
                return True
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # round 4 of T-0028: a member we may not signal is alive
    return True


def stop_survivors(started):
    """After a leader `launch` saw exit normally: SIGKILL whatever it left
    running in its process group and wait for the group to empty, so nothing
    it started can write after the "after" fingerprint (round 3 of T-0028: a
    backgrounded `sleep 2; echo fix >> seed.txt` landed after a CLEAN round).

    (killed, unknown_reason); a kill refused with PermissionError is
    (False, KIMI_SURVIVOR_UNKNOWN). The group is signalled only after `_group_alive`
    has just found a live member: while a group has members its id is not
    handed to a new process, so the bare number still names this group --
    the hazard `launch`'s timeout path guards against is a group that has
    already emptied. NOT SEEN: a descendant that left the group (`setsid`).

    Windows (group review of L-0527): no group is probed; `_launch` already
    ended the provider's job and recorded the answer in `started`. With no
    such record -- no job could be made -- nothing can tell whether a
    descendant is still running, so that is could-not-tell."""
    if not started:
        return False, None
    ended = [entry for entry in started if isinstance(entry, tuple) and entry[0] == _JOB_ENDED]
    if ended:
        return ended[-1][1], ended[-1][2]
    if not KIMI_SURVIVORS_SEEN:
        return False, KIMI_SURVIVOR_UNKNOWN  # no job ended, no group to probe
    if not _group_alive(started[0]):
        return False, None
    try:
        os.killpg(started[0], signal.SIGKILL)
    except ProcessLookupError:
        return False, None  # the group emptied between the probe and the kill
    except PermissionError:
        # Round 4 of T-0028: a member we may not signal is not "no survivor".
        return False, KIMI_SURVIVOR_UNKNOWN
    deadline = time.monotonic() + POST_KILL_TIMEOUT
    while _group_alive(started[0]):
        if time.monotonic() >= deadline:
            return True, KIMI_SURVIVOR_UNKNOWN
        time.sleep(0.05)
    return True, None


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


def finish(args, number, output, exit_code, timed_out, extra_reasons=(), tree_reasons=()):  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Verdict -> ledger -> review.json. Returns the process exit code.
    `extra_reasons` are the stream's (the answer never arrived intact: a tool
    failure); `tree_reasons` are what the working tree did (a Kimi write, or a
    tree or survivor that cannot be checked), classed `tree` like a bundle
    problem, so never refunded (group review r4 of #540)."""
    manifest, manifest_reasons = _finish_manifest(args)
    # The parts as the prompt lists them -- full paths -- so a READ line that
    # echoes the listed path counts (T-0079). A part with no path falls back to
    # its name, which review_verdict still matches exactly.
    parts = [p.get("path") or p["name"] for p in manifest.get("parts") or []]
    if os.path.exists(os.path.join(args.scratch, review_prompt.WEBTEST_FINDINGS_FILE)):
        parts.append(os.path.join(args.scratch, review_prompt.WEBTEST_FINDINGS_FILE))
    rows, webtest_record, webtest_reasons = webtest_check(args.root, args.ticket, manifest)
    stream_reasons = list(extra_reasons)
    extra_reasons = list(extra_reasons) + list(tree_reasons) + bundle_problems(manifest)
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
        "model_launched": getattr(args, "launched_model", None) or args.model or None,
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
    # L-0712: the label is the reservation's, read back from the ledger row.
    review["same_family"] = row.get("same_family") is True
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
    if review["same_family"]:
        _out(f"review: round {number} is SAME-FAMILY by the operator's choice "
             f"({_one(row.get('same_family_reason'))}); not an independent review")
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


def _after_the_gates(args, before):
    """The "before" fingerprint once crew's own gates have run (L-0527
    review): during an incident `prereview_gate` and `standards_gate` append
    `crew_incident.SKIP_LOG_PATH`, between the probe and the launch, with no
    Kimi process alive (the probe's survivors were stopped). When that log is
    ALL that changed, the fingerprint taken now is the one the review is
    judged against; anything else stays counted against `before`."""
    now = tree_fingerprint(args.root)
    if now is None:
        return before
    changed, _set_aside = reviewer_changes(before, now, args.graph_out)
    return now if changed and set(changed) <= {crew_incident.SKIP_LOG_PATH} else before


def _probe_runner(cmd, env, timeout, cwd, unstopped=None):  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """`kimi_probe.probe`'s runner: `launch`, in a process group of its own,
    then `stop_survivors`, so the probe call cannot leave a writer running
    past the fingerprint taken after it. A survivor that could not be stopped
    answers as a call that never said PROBE_OK, which the probe reads as
    `unknown`, and is appended to `unstopped`: `_probe_kimi` then stops the
    review (exit 8), since that process may still write after any check."""
    started = []
    stdout, stderr, code, timed_out = launch(cmd, cwd, timeout, env=env, started=started)
    if stop_survivors(started)[1]:  # after a timeout too (group review r3)
        if unstopped is not None:
            unstopped.append(cmd[0])
        return "", KIMI_SURVIVOR_UNKNOWN, None, False
    return stdout, stderr, code, timed_out


def _probe_kimi(args, before):
    """Run the probe. None when the review may go on (the binary and alias it
    resolved are then `args.kimi_exe` and `args.launched_model`); otherwise
    (exit code, refusal message). The tree is fingerprinted after the probe
    WHATEVER it answered (round 4 of T-0028: a failing probe that wrote
    returned EXIT_USAGE, and /crew:review walked on to the next provider
    against a tree the probe had changed): a change is EXIT_PROBE_CHANGED."""
    unstopped = []
    probed = kimi_probe.probe(args.model or None, runner=functools.partial(
        _probe_runner, unstopped=unstopped))
    answer = f"kimi probe: {probed['state']} - {probed['reason']}"
    problems = []
    mid = tree_fingerprint(args.root, problems)
    if mid is None:
        # Round 3 NIT: this used to fall through as "clean" and reserve, so
        # the round was spent as INCOMPLETE when nothing had been launched.
        # Group review (L-0527): could-not-tell is not "Kimi unavailable" --
        # exit 2 walked on to the next provider with the old bundle while the
        # probe may have changed the tree (made a file unreadable), so it
        # stops exactly as a change does.
        return EXIT_PROBE_CHANGED, (f"kimi probe: unknown - the tree could not be "
                                    f"fingerprinted after the probe: "
                                    f"{'; '.join(problems) or 'no reason given'} (the probe "
                                    f"answered: {answer}); stop and check the tree, do not "
                                    "walk to the next provider")
    if before is not None:
        changed, _set_aside = reviewer_changes(before, mid, args.graph_out)
        if changed:
            return EXIT_PROBE_CHANGED, (f"{KIMI_PROBE_CHANGED}: {_named(changed)} (the probe "
                                        f"answered: {answer}); stop and report these paths, "
                                        "do not walk to the next provider")
    if unstopped:
        # Group review of #540: a probe process that could not be stopped can
        # write after any fingerprint, so this is not "Kimi unavailable" (exit
        # 2 walks on with the bundle already built): it stops as a change does.
        return EXIT_PROBE_CHANGED, (f"{KIMI_SURVIVOR_UNKNOWN} (the kimi probe; it answered: "
                                    f"{answer}); stop and check the tree, do not walk to "
                                    "the next provider")
    if not kimi_probe.launchable(probed["state"]):
        return EXIT_USAGE, answer
    args.kimi_exe, args.launched_model = probed["exe"], probed["alias"]
    return None


def _run_kimi(args, number, prompt, before):
    """Launch the reserved Kimi round and finish it."""
    extra, tree = [], []
    cmd = command_for("kimi", args.kimi_exe, args.root, prompt, args.launched_model, "",
                      args.scratch)
    started = []
    stdout, stderr, code, timed_out = launch(cmd, args.root, args.timeout,
                                             env=kimi_probe.kimi_env(), started=started)
    # A timeout too (group review r3 of #540): `launch` may leave a descendant
    # running once its leader is gone, so survivors are stopped either way.
    killed, survivor_unknown = stop_survivors(started)
    if survivor_unknown:
        tree.append(survivor_unknown)
    elif killed:
        _err("review-run: kimi left processes running after it exited; they were "
             "stopped before the tree was checked\n")
    after = tree_fingerprint(args.root)
    if before is None or after is None:
        tree.append(KIMI_TREE_UNKNOWN)
    else:
        changed, set_aside = reviewer_changes(before, after, args.graph_out)
        if changed:
            tree.append(f"{KIMI_TREE_CHANGED}: {_named(changed)}")
        if set_aside:
            _err(f"review-run: not counted against the reviewer, under graph.out "
                 f"(graphify's background rebuild), or ignored IDE state or crew "
                 f"hook logs: {_named(set_aside)}\n")
    _write_atomic(os.path.join(args.scratch, "kimi-events.jsonl"), stdout)
    message_text, error = kimi_probe.final_message(stdout)
    output = message_text or ""
    if error and not timed_out:
        extra.append(f"kimi: {kimi_probe.redact(error)}")
    _write_atomic(os.path.join(args.scratch, "out.txt"), output)
    _write_atomic(os.path.join(args.scratch, "stderr.txt"), kimi_probe.redact(stderr))
    return finish(args, number, output, code, timed_out, extra, tree)


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
    having reserved nothing. For Kimi the probe has already run before
    these questions, as Codex's `--probe` runs before its round (T-0028,
    owner 2026-09-30). See BEFORE ANY ROUND IS RESERVED above:
    questions 1 and 2 (`_receipt_and_gate`), then 3 (`train_gate`) unless
    the budget is already spent (`_budget_spent`): then `reserve` refuses it
    (exit 4) and the train is never taken, so a ticket that cannot gate can
    never hold the train other lanes wait behind.

    The budget answer is kept on `args.budget_spent` for `run`, which must
    reserve on the SAME decision (H1 group review r3): a round refunded
    between two reads would otherwise skip the train here yet reserve gated
    there. A skipped train always reserves ungated, so `reserve` refuses a
    ledger that is no longer spent under its lock (L-0518's GATE_CHANGED)."""
    short = _receipt_and_gate(args)
    if short is not None:
        return short
    args.budget_spent = _budget_spent(args)
    if args.budget_spent:
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
    clean = ok and (data.get("receipt") or {}).get("kind") == "clean"
    if clean and message.startswith("receipt kept by delta gate"):
        # A delta-kept receipt stands over a MERGED tree the verify gate may
        # never have passed (L-0522): CLEAN only once the gate is VERIFIED or
        # NO_GATE; otherwise on to the gate handling below, as for a new round.
        state, _reason = review_gate.accepted_state(args.root)
        if state in (review_gate.VERIFIED, review_gate.NO_GATE):
            _out(f"review: CLEAN from the existing receipt ({message}) - kept by the delta "
                 "gate: nothing of the ticket's own changed since that clean round, and the "
                 f"verify gate is {state} on this tree, so no round was spent")
            if args.provider not in LAUNCHED:
                _out("ALREADY_CLEAN=1")
            return EXIT_CLEAN
    elif clean:
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
        incident = _incident(args, "self-check")
        if incident is None:
            return EXIT_USAGE
        if incident["active"]:
            if not _log_skip(args, "self-check", "standards-selfcheck", "; ".join(problems)):
                return EXIT_USAGE
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


def _incident(args, gate):
    """The incident state for a gate's stand-down, or None after saying the
    gate could not run (L-0518 N4): an exception escaping here would exit 1,
    which /crew:review reads as FINDINGS, not as "not run"."""
    try:
        return crew_incident.read_state(args.root, crew_state.load_config(args.root))
    except (OSError, ValueError) as exc:
        _gate_failed(gate, exc)
        return None


def _log_skip(args, gate, check, detail):
    """Log an incident skip; False after saying the gate could not run (N4)."""
    try:
        crew_incident.log_skip(args.root, check, detail)
    except (OSError, ValueError) as exc:
        _gate_failed(gate, exc)
        return False
    return True


def _gate_failed(gate, exc):
    _err(f"review-run: {gate} gate could not run: {type(exc).__name__}: {exc}; nothing "
         "launched, no round spent\n")


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
    incident = _incident(args, "pre-review")
    if incident is None:
        return EXIT_USAGE
    if incident["active"]:
        if not _log_skip(args, "pre-review", "prereview-checks", f"{verdict}: " + "; ".join(
                f"{r['name']} {r['status']}" for r in results if r["status"] in (
                    review_checks.FAIL, review_checks.COULD_NOT))):
            return EXIT_USAGE
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


def family_guard(args):
    """L-0712: (refusal, label). `refusal` is the stderr line when this
    reviewer may not run, else None; `label` is the `same_family` reason to
    reserve with, or None. See THE FAMILY GUARD in the module docstring."""
    reason = getattr(args, "same_family", None)
    if reason is not None:
        # Checked before anything runs: an empty or multi-line reason is a
        # usage error, never a label the ledger refuses after the gates.
        reason = review_ledger._one_line_arg(reason, "--same-family", "a same-family read")  # pylint: disable=protected-access
    if getattr(args, "authors", None) is None:
        fam = crew_state.family(args.provider, args.model or None)
        if fam in (None, "claude") and reason is None:
            # Round 4 BLOCK: crew's author is Claude unless proven otherwise, so a
            # Claude (or unknown-family) reservation with no --authors is
            # could-not-tell, never an unlabelled independent round. This guard
            # runs only where a round is reserved (run, --probe, and
            # review_ledger.py --reserve); the recording call never reaches it,
            # so no flag here, --round included, may exempt a reservation
            # (round 5 BLOCK: --reserve-only --round slipped past).
            return (f"review-run: same-family: no --authors given, so {args.provider} "
                    f"({fam or 'unknown'} family) may be the author's family; not an "
                    "independent review. Pass --authors \"$AUTHORS\", or --same-family "
                    "\"<reason>\" to run it labelled. Nothing launched, no round spent\n"), None
        _err("review-run: family guard NOT applied: no --authors given, so nothing here "
             "checked this reviewer against the diff's author (L-0712)\n")
        return None, reason
    authors = {a.strip().lower() for a in args.authors.replace(",", " ").split() if a.strip()}
    fam = crew_state.family(args.provider, args.model or None)
    unknown_source = getattr(args, "author_source", None) == "unknown"
    if authors and not unknown_source and fam is not None and fam not in authors:
        if reason is not None:
            _err(f"review-run: --same-family ignored: {args.provider} ({fam} family) is not "
                 f"the author's ({', '.join(sorted(authors))})\n")
        return None, None
    if reason is not None:
        return None, reason
    why = (f"{args.provider} speaks as the `{fam}` family that wrote this diff"
           if fam is not None and fam in authors else
           "the author source is `unknown`: a dispatch's family could not be told, so "
           f"{', '.join(sorted(authors)) or 'no family'} may not be every author"
           if unknown_source else
           f"could not tell whether {args.provider} ({fam or 'unknown'} family) is the "
           f"author's ({', '.join(sorted(authors)) or 'no author family known'})")
    return (f"review-run: same-family: {why}; not an independent review. Walk to the next "
            "cross-family provider, or record no reviewer (review_ledger.py --no-reviewer); "
            "--same-family \"<reason>\" runs it labelled. Nothing launched, no round spent\n"), None


def run(args):
    exe = prompt = before = None
    refusal, args.same_family_label = family_guard(args)
    if refusal:
        _err(refusal)
        return EXIT_USAGE
    if args.provider in LAUNCHED:
        if args.provider == "copilot" and not args.model:
            _err("review-run: copilot needs --model (qa.copilot.model); an "
                             "unpinned Copilot is the author's family\n")
            return EXIT_USAGE
        exe = review_checks.resolve_executable(args.provider)
        if not exe:
            _err(f"review-run: {args.provider} is not on PATH (not-installed); nothing launched, "
                             "no round spent\n")
            return EXIT_USAGE
        if args.provider == "kimi":
            # A Kimi round is never reserved unprobed (round 4 of T-0028: the
            # unlocked status said none was left, a successor plan landed, and
            # the probe that then ran after `reserve` spent the round). So the
            # status refuses first, before any probe request.
            if not _round_available(args.root, args.ticket):
                # A CLEAN receipt still answers CLEAN with no round left, as
                # for every other provider (L-0527 review): nothing is spent.
                if review_ledger.check_receipt(args.root, args.ticket)[0] \
                        and preflight(args) == EXIT_CLEAN:
                    return EXIT_CLEAN
                _err("review-run: kimi: no round left per the ledger's status; "
                     "re-run once a successor plan is approved; nothing "
                     "launched, no round spent\n")
                return EXIT_REFUSED
            # The fingerprint comes FIRST: the probe is a Kimi call too, so it
            # is inside the watched window. graph.out is resolved with it, from
            # the tree as it is BEFORE any Kimi call could write it. A "before"
            # that could not be taken already decides the round (INCOMPLETE),
            # so it stops here: no probe request, no reservation. Then the
            # probe, BEFORE `reserve`: it is not a review, and a quota or auth
            # wall found here must cost no round. Only `ok` goes on.
            problems = []
            before = tree_fingerprint(args.root, problems)
            args.graph_out = graph_out(args.root)
            if before is None:
                _err("review-run: kimi: unknown - cannot fingerprint the tree: "
                     f"{'; '.join(problems) or 'no reason given'}; nothing "
                     "launched, no round spent\n")
                return EXIT_USAGE
            refusal = _probe_kimi(args, before)
            if refusal:
                _err(f"review-run: {refusal[1]}; nothing launched, no round "
                     "spent\n")
                return refusal[0]
        prompt = prompt_argument(os.path.join(args.scratch, "prompt.txt"), exe)

    short = preflight(args)
    if short is not None:
        return short

    # A spent budget is a precondition already known to fail (GEN-03): the
    # self-check cannot change it, so the budget refusal below answers first
    # rather than sending the author to answer and restamp for nothing.
    # `reserve` re-reads the ledger under its lock and is what refuses. One
    # predicate with the train's (review of 6ec829c9): an unreadable ledger
    # is refused by `reserve` too, so no later check answers first. The
    # decision is preflight's own (`args.budget_spent`), never a second read:
    # a skipped train must reserve ungated.
    spent = getattr(args, "budget_spent", None)
    gated = not (_budget_spent(args) if spent is None else spent)
    if gated:
        refused = prereview_gate(args)
        if refused is None:
            refused = standards_gate(args)
        if refused is not None:
            return refused

    if before is not None:
        before = _after_the_gates(args, before)
    # The skip is carried into the locked read (L-0518 F2): a ledger that is
    # no longer spent there refuses rather than reserving an ungated round.
    ok, number, message = review_ledger.reserve(args.root, args.ticket, args.provider,
                                                args.model, gated=gated,
                                                same_family=args.same_family_label)
    _err(f"review-run: {message}\n")
    if not ok:
        return EXIT_USAGE if message == review_ledger.GATE_CHANGED else EXIT_REFUSED
    _bind_record(args, number)
    _keep_reserved_std(args, number)
    if args.provider not in LAUNCHED:
        _out(f"ROUND={number}")
        return EXIT_CLEAN

    if args.provider == "kimi":
        return _run_kimi(args, number, prompt, before)
    retries = 0
    while True:
        status, timed_out, limit = _launch_round(args, exe, prompt, number)
        if status != EXIT_INCOMPLETE:
            return status
        why = _retry_reason(args, number, timed_out, limit, retries)
        if why is None:
            time.sleep(RETRY_BACKOFF_SECONDS)
            why = _retry_blocked(args, gated)
        if why is not None:
            _out(f"review: retry: not retried - {why}")
            _out(RETRY_OPTIONS)
            return status
        # On the retry preflight's own budget decision, as the first
        # reservation (H1 group review r4): a train that read skipped is never
        # followed by a gated reservation.
        ok, retry_number, message = review_ledger.reserve(
            args.root, args.ticket, args.provider, args.model,
            same_family=args.same_family_label,
            gated=not getattr(args, "budget_spent", False))
        _err(f"review-run: {message}\n")
        if not ok:
            _out("review: retry: not retried - the ledger refused the retry's reservation")
            _out(RETRY_OPTIONS)
            return status
        # Only once the retry holds a round: a refused one leaves round
        # `number`'s review.json the canonical artifact.
        _keep_round_files(args, number)
        _out(f"review: retry: round {number} was a tool failure; retrying once")
        _carry_record(args, number, retry_number)
        number, retries = retry_number, retries + 1
        _keep_reserved_std(args, number)


def _launch_round(args, exe, prompt, number):
    """Launch round `number` and record it. (exit code, timed out, usage-limit line)."""
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
            then = ("the next round walks to the next cross-family provider, else "
                    "records no reviewer (INCOMPLETE, refunded)")
        except OSError as exc:
            then = (f"could not record it ({exc}), so the next probe calls Codex live "
                    "instead of answering limited from the record")
        _out(f"review: codex usage limit in round {number}: {limit!r}; {then}")
    return status, timed_out, limit


def _retry_reason(args, number, timed_out, limit, retries):
    """None when INCOMPLETE round `number` may be retried; else why not.

    Only a `tool` round the ledger refunded retries, so a retry never spends
    budget; a limit or a timeout is a tool round a relaunch does not fix."""
    if limit:
        return "a usage limit is not retried; the next round walks to a cross-family provider"
    if timed_out:
        return (f"round {number} timed out, and a retry could double a {args.timeout}s "
                "wait")
    rows = review_ledger.status(args.root, args.ticket).get("rounds") or []
    row = next((r for r in rows if isinstance(r, dict) and r.get("round") == number), {})
    failure = row.get("failure_class")
    if failure != review_verdict.TOOL:
        return (f"round {number} is a {failure or 'unclassified'} INCOMPLETE, which a retry "
                "does not fix")
    if row.get("refunded") is not True:
        return f"round {number}'s refund was refused ({row.get('refund_refused') or 'unknown'})"
    if retries >= RETRY_LIMIT:
        return f"retry limit {RETRY_LIMIT} per invocation"
    return None


def _retry_blocked(args, gated=True):
    """After the backoff: None when the retry may reserve, else why not. The
    gate and receipt are asked again (`preflight`), and the bundle re-hashed:
    a tree that moved since the failed round is not the bundle it lost. A
    gated round's standards self-check is asked again too (group review of
    #540): it lives under `.work/`, which neither the bundle nor the gate
    sees, so it can go stale or vanish during the backoff."""
    if preflight(args) is not None:
        return "the gate or the review receipt changed before the retry (above)"
    if gated and standards_gate(args) is not None:
        return "the standards self-check no longer passes (above)"
    try:
        manifest = json.loads(_read(args.manifest, _trusted(args.manifest, args.scratch)))
        problems = bundle_problems(manifest)
    except (OSError, ValueError) as exc:
        problems = [f"the manifest could not be read ({exc})"]
    if problems:
        return f"the tree changed: {problems[0]}"
    # The saved parts can still match their manifest while a source file
    # moved under them: rebuild the bundle from the tree as it is now.
    try:
        fresh = review_patch.compute(args.root, manifest["base"])[0].get("bundle_sha256")
    except (RuntimeError, OSError, KeyError, TypeError) as exc:
        return f"could not tell whether the tree changed: {exc}"
    if fresh != manifest.get("bundle_sha256"):
        return (f"the tree changed: it now builds bundle {str(fresh)[:12]}, not the "
                f"{str(manifest.get('bundle_sha256'))[:12]} the failed round read")
    return None


def _carry_record(args, previous, number):
    """The retry lints nothing again: its bundle is the one round `previous`
    was checked on (re-hashed above), so that round's pre-review record is
    bound to round `number` too. A copy that fails is said, never fatal:
    `finish` then reads `not-recorded`."""
    if not getattr(args, "prereview_staged", None):
        return
    try:
        source = review_checks.round_record_path(args.scratch, args.ticket, previous)
        staged = os.path.join(args.scratch, f"prereview.retry-r{number}.json")
        _write_atomic(staged, review_checks.read_regular(source, args.scratch).decode("utf-8"))
        review_checks.bind_record(staged, args.scratch, args.ticket, number)
    except (OSError, ValueError) as exc:
        _err(f"review-run: could not carry the pre-review record to round {number} "
             f"({exc}); review.json will say not-recorded\n")


def _keep_round_files(args, number):
    """Keep the failed round's scratch files and review.json as
    `<name>.round<N>`, so the retry writes its own and the earlier stays
    inspectable. A file that cannot be moved is said, never fatal."""
    work_dir = args.work_dir or os.path.join(args.root, ".work", "tickets", args.ticket)
    paths = [os.path.join(args.scratch, name) for name in RETRY_KEPT]
    for path in paths + [os.path.join(work_dir, "review.json")]:
        try:
            os.replace(path, f"{path}.round{number}")
        except FileNotFoundError:
            continue
        except OSError as exc:
            _err(f"review-run: could not keep {path} as .round{number} ({exc})\n")


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


# The providers this runner can launch (`kimi` since L-0527); commands/review.md
# filters `$ELIGIBLE` to this set (and says so on stderr) instead of relying on
# argparse's exit 2 to skip a provider it does not name.
PROVIDERS = ("codex", "copilot", "kimi", "claude")


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
    parser.add_argument("--authors", default=None,
                        help="the author families ($AUTHORS); a reviewer of one of them, or "
                             "of an unknown family, is refused unless --same-family (L-0712)")
    parser.add_argument("--author-source", default=None,
                        help="$AUTHOR_SOURCE; `unknown` is could-not-tell (L-0712)")
    parser.add_argument("--same-family", default=None, metavar="REASON",
                        help="the operator's explicit choice of a same-family read, one line; "
                             "the round is labelled same_family")
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
            refusal, _ = family_guard(args)
            if refusal:
                _err(refusal)
                return EXIT_USAGE
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
