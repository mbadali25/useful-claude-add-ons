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
           spends nothing -- and is skipped when the ledger already shows no
           round left, since the reservation would refuse anyway. Prompt mode
           FORCES Kimi's permission mode to `auto` (2.1.1 refuses `-p` with
           --plan/--auto/--yolo), so no flag makes it read-only. Two controls
           stand in, for the probe call as for the review: the agent file
           allows Read, Grep and Glob and disallows Write, Edit and Bash, and
           the working tree is fingerprinted BEFORE THE PROBE and after the
           review exits. A probe that changed it exits 2 with no round
           spent; a review that changed it is INCOMPLETE, naming the paths.
           See `tree_fingerprint` and `reviewer_changes` for what is and is
           not seen. A write OUTSIDE the repository is caught by neither. The
           final message is read from the stream
           (`review_verdict.kimi_final_message`); its error text is redacted
           before it becomes a reason.
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
import signal
import stat
import subprocess
import sys

import crew_common
import crew_freshness
import crew_state
import kimi_probe
import review_ledger
import review_patch
import review_prompt
import review_verdict
import webtest_guard

EXIT_CLEAN, EXIT_FINDINGS, EXIT_USAGE, EXIT_INCOMPLETE, EXIT_REFUSED = 0, 1, 2, 3, 4
DEFAULT_TIMEOUT = 1800
# Bound on the follow-up `communicate()` after a kill, below. Not the same
# knob as --timeout: this one exists so a descendant that escaped the kill
# (still holding the pipe open) cannot itself defeat --timeout by keeping
# this call blocked - see `launch`'s own comment for the full reproduction.
POST_KILL_TIMEOUT = 5
# Windows' CreateProcess limit is 32767 characters for the whole command line.
INLINE_PROMPT_LIMIT = 24000
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


def prompt_argument(prompt_path):
    text = _read(prompt_path)
    if len(text) <= INLINE_PROMPT_LIMIT:
        return text
    sys.stderr.write(f"review-run: prompt is {len(text)} chars, over the inline limit; "
                     f"the reviewer is told to read {prompt_path}\n")
    return (f"Your complete instructions are in the file {prompt_path}. Read that file in "
            "full first and follow it exactly; it is the whole task.")


def _git_bytes(root, args, env):
    """Raw stdout of one git call, or None when git failed, could not start,
    or did not answer within SNAPSHOT_GIT_TIMEOUT."""
    try:
        done = subprocess.run(["git", *args], cwd=root, env=env, capture_output=True,
                              stdin=subprocess.DEVNULL, timeout=SNAPSHOT_GIT_TIMEOUT,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _path_digest(path):
    """What is at `path` now, without following a symlink: a content sha256,
    `link:<target>`, `dir`, or `missing`. None when it exists and cannot be
    read -- an unreadable file is "could not tell", and two of those must not
    compare equal as "unchanged"."""
    try:
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode):
            return "link:" + os.readlink(path)
        if stat.S_ISDIR(mode):
            return "dir"
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                digest.update(block)
        return digest.hexdigest()
    except FileNotFoundError:
        return "missing"
    except OSError:
        return None


def tree_fingerprint(root):
    """The working tree's state as `{path: "<XY> <content digest>"}`, plus
    `:HEAD` and `:index` -- or None when it cannot be taken.

    Every path `git status` lists is in it, with its CONTENTS hashed: modified
    tracked files, untracked files and IGNORED files alike
    (`--untracked-files=all --ignored=traditional` lists each file inside an
    ignored directory, not the directory). Round 1 of T-0028 found the
    earlier digest hashed only an untracked file's status LINE and skipped
    ignored files, so a reviewer editing an already-untracked file, or a
    gitignored `.crew/config.json`, left before == after. `:HEAD` is there so
    a reviewer that COMMITTED its edit is seen, `:index` (the staged diff) so
    one that only staged is. `.work/` is excluded -- the scratch directory,
    review.json and the handoff live there. Taken with GIT_OPTIONAL_LOCKS=0
    so taking it cannot itself change the index.

    NOT SEEN: a write outside the repository, and a change inside `.git`
    other than HEAD and the index (a hook, a config). None when any git call
    fails or times out, or a listed file cannot be read: "could not tell" is
    its own answer, never a value two failures would compare equal on."""
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    head = crew_common.git_out(root, "rev-parse", "HEAD")
    if not head:
        return None
    scope = ["--", ".", ":(exclude).work"]
    status = _git_bytes(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all",
                               "--ignored=traditional", *scope], env)
    staged = _git_bytes(root, ["diff", "--cached", "--binary", *scope], env)
    if status is None or staged is None:
        return None
    snapshot = {":HEAD": head, ":index": hashlib.sha256(staged).hexdigest()}
    fields = iter(status.split(b"\0"))
    for entry in fields:
        if len(entry) < 4:
            continue
        code = entry[:2].decode("ascii", "replace")
        if code[0] in "RC":
            next(fields, None)  # -z puts a rename's source path in its own field
        rel = os.fsdecode(entry[3:]).rstrip("/")
        digest = _path_digest(os.path.join(root, rel))
        if digest is None:
            return None
        snapshot[rel] = f"{code} {digest}"
    return snapshot


def graph_out(root):
    """`graph.out` as a repo-relative, `/`-separated directory, or None.

    Resolved the way `crew_freshness._read_graph` and `crew_refresh_check`
    resolve it: `.crew/crew.json`, else `.crew/config.json`; a missing or
    wrong-typed value is `graphify-out`; `contained_path` keeps it inside the
    repository. None when it lands on the root or in `.git`, or a symlink
    moves it -- an exemption for one generated directory must never widen to
    the tree."""
    top = os.path.realpath(root)
    cfg = {}
    for name in ("crew.json", "config.json"):
        text = crew_common.read_text(os.path.join(top, ".crew", name))
        if text is None:
            continue
        try:
            cfg = json.loads(text)
        except ValueError:
            cfg = {}
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
    return rel


def _under(rel, directory):
    """True when `rel` lies strictly under `directory`, segment by segment:
    `graphify-outX/a` is not under `graphify-out`."""
    parts, stem = rel.split("/"), directory.split("/")
    return len(parts) > len(stem) and parts[:len(stem)] == stem


def reviewer_changes(root, before, after):
    """(changed, generated): the paths whose state differs between two
    `tree_fingerprint`s, split into those the reviewer is answerable for and
    those under `graph.out`.

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
    `:HEAD` and `:index` always do."""
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    graph = graph_out(root)
    generated = [p for p in changed
                 if graph and not p.startswith(":") and _under(p, graph)]
    return [p for p in changed if p not in generated], generated


def _named(paths):
    shown = ", ".join(paths[:CHANGED_SHOWN])
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


def launch(cmd, root, timeout, env=None):
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
            env=env, **popen_kwargs)
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
        "model_launched": getattr(args, "launched_model", None) or args.model or None,
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


def _probe_kimi(args, before):
    """Run the probe. None when the review may go on (the binary and alias it
    resolved are then `args.kimi_exe` and `args.launched_model`); otherwise
    the refusal message. A probe that changed the tree is refused too."""
    probed = kimi_probe.probe(args.model or None)
    if not kimi_probe.launchable(probed["state"]):
        return f"kimi probe: {probed['state']} - {probed['reason']}"
    mid = tree_fingerprint(args.root)
    if before is not None and mid is not None:
        changed, _generated = reviewer_changes(args.root, before, mid)
        if changed:
            return f"{KIMI_PROBE_CHANGED}: {_named(changed)}"
    args.kimi_exe, args.launched_model = probed["exe"], probed["alias"]
    return None


def _run_kimi(args, number, prompt, before):
    """Launch the reserved Kimi round and finish it."""
    extra = []
    cmd = command_for("kimi", args.kimi_exe, args.root, prompt, args.launched_model, "",
                      args.scratch)
    stdout, stderr, code, timed_out = launch(cmd, args.root, args.timeout,
                                             env=kimi_probe.kimi_env())
    after = tree_fingerprint(args.root)
    if before is None or after is None:
        extra.append(KIMI_TREE_UNKNOWN)
    else:
        changed, generated = reviewer_changes(args.root, before, after)
        if changed:
            extra.append(f"{KIMI_TREE_CHANGED}: {_named(changed)}")
        if generated:
            sys.stderr.write(f"review-run: not counted against the reviewer, under graph.out "
                             f"(graphify's background rebuild): {_named(generated)}\n")
    _write_atomic(os.path.join(args.scratch, "kimi-events.jsonl"), stdout)
    message_text, error = review_verdict.kimi_final_message(stdout)
    output = message_text or ""
    if error and not timed_out:
        extra.append(f"kimi: {kimi_probe.redact(error)}")
    _write_atomic(os.path.join(args.scratch, "out.txt"), output)
    _write_atomic(os.path.join(args.scratch, "stderr.txt"), kimi_probe.redact(stderr))
    return finish(args, number, output, code, timed_out, extra)


def run(args):
    exe = prompt = before = None
    probed = False
    if args.provider in LAUNCHED:
        if args.provider == "copilot" and not args.model:
            sys.stderr.write("review-run: copilot needs --model (qa.copilot.model); an "
                             "unpinned Copilot is the author's family\n")
            return EXIT_USAGE
        exe = shutil.which(args.provider)
        if not exe:
            sys.stderr.write(f"review-run: {args.provider} is not on PATH (not-installed); "
                             "nothing launched, no round spent\n")
            return EXIT_USAGE
        if args.provider == "kimi":
            # The fingerprint comes FIRST: the probe is a Kimi call too, so it
            # is inside the watched window. Then the probe, BEFORE `reserve`:
            # it is not a review, and a quota or auth wall found here must
            # cost no round. Only `ok` goes on.
            before = tree_fingerprint(args.root)
            if _round_available(args.root, args.ticket):
                refusal = _probe_kimi(args, before)
                if refusal:
                    sys.stderr.write(f"review-run: {refusal}; nothing launched, no round "
                                     "spent\n")
                    return EXIT_USAGE
                probed = True
        prompt = prompt_argument(os.path.join(args.scratch, "prompt.txt"))

    ok, number, message = review_ledger.reserve(args.root, args.ticket, args.provider,
                                                args.model)
    sys.stderr.write(f"review-run: {message}\n")
    if not ok:
        return EXIT_REFUSED
    if args.provider not in LAUNCHED:
        print(f"ROUND={number}")
        return EXIT_CLEAN

    if args.provider == "kimi":
        if not probed:
            # The unlocked status said no round was left, yet one was granted
            # (a successor plan landed in between). Never launch unprobed: the
            # round is already spent, so a failing probe ends it INCOMPLETE.
            refusal = _probe_kimi(args, before)
            if refusal:
                return finish(args, number, "", None, False,
                              [f"{refusal} (probed after the reservation)"])
        return _run_kimi(args, number, prompt, before)
    extra = []
    cmd = command_for(args.provider, exe, args.root, prompt, args.model, args.effort)
    stdout, stderr, code, timed_out = launch(cmd, args.root, args.timeout)
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
    parser.add_argument("--provider", required=True, choices=("codex", "copilot", "kimi", "claude"))
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
