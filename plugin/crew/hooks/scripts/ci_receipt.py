"""The verify gate's CI receipt: built on the runner, checked against HEAD here.

    ci_receipt.py build --root . --gate-rc <rc> --gate-log <file> --out <file> [--summary <file>]
    ci_receipt.py check --root .

WHY. A local `verify-gate.sh --all` costs 17-20 minutes and holds a heavy
slot on a shared box that OOM-kills it at the 6G cap. The self-hosted runner
pool sits idle most of the day. `.github/workflows/verify-gate.yml` runs the
same gate there on a pushed lane branch and uploads what this module's
`build` writes; `check` reports whether that result provably describes the
commit checked out here. Diagnostic in this release: no gate consumer
(`/crew:done`, `review_run.py`, `crew_train.py check-land`, the Stop hook)
accepts it yet; that wiring is a separate tooling change.

WHAT `build` RECORDS (runner side, after the gate). The verdict is not the
gate's exit status. It is `review_gate.gate_state` asked on the runner, the
one definition of "the gate passed on this tree" every local consumer uses,
plus the facts that bind it: HEAD, `HEAD^{tree}`, the blob of
`.crew/verify.json` at HEAD, the per-rule record's outstanding entries (must
be none), whether anything material differs from HEAD after the gate ran,
and the run's id, attempt and repository. `pass` is true only when every one
of those holds. Per-command outcomes are parsed from the gate log for a
reader; they are never what acceptance rests on.

WHAT `check` ACCEPTS (local side). VERIFIED needs ALL of:
  * a verify map that is present and not stood down (else NO_GATE, the same
    two tests `review_gate` makes);
  * nothing material differs from HEAD locally -- the receipt covers the
    committed tree, not edits on top of it;
  * this branch did not itself change the gate implementation or the
    receipt's producer (GATE_IMPL) against origin/main: a push runs the
    workflow AT the pushed sha, so such a branch would vouch for itself;
  * the NEWEST run of verify-gate.yml for HEAD's sha in this repository,
    from a push or workflow_dispatch, completed with conclusion success;
  * its `crew-verify-receipt-<attempt>` artifact (exactly one, unexpired, naming
    that run and HEAD), holding a receipt of this
    schema whose head, tree, verify.json blob, gate_impl digest, run id,
    attempt and repository all equal what git and the API say, with `pass` true, gate
    state VERIFIED, gate rc 0, nothing outstanding and a clean tree;
  * the newest run, and the local HEAD, tree, map and working tree, all
    unchanged from the start of the check to its end.

A receipt stays valid evidence about its sha after CREW_RUNNER is unset:
unsetting it stops new receipts, it does not revoke old ones.

FOUR ANSWERS, "could not tell" its own one (`review_gate`'s names):
  VERIFIED    exit 0
  UNVERIFIED  exit 1 -- a fact was read and it did not hold
  UNKNOWN     exit 3 -- gh, git, the network or the artifact could not be
              read; never read as VERIFIED, refused like UNVERIFIED
  NO_GATE     exit 4 -- no verify map, or the gate is stood down
Usage errors exit 2. The last stdout line of `check` is always the one line
`CI_RECEIPT <STATE> head=<sha or -> <reason>`, its reason folded onto one line
(gh's stderr is multi-line).

The network is reached only through `fetch` (default: `gh api`), so tests
inject a fake and never touch it.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

if __name__ == "__main__":
    sys.dont_write_bytecode = True

import review_gate  # noqa: E402  pylint: disable=wrong-import-position
import verify_fingerprint  # noqa: E402  pylint: disable=wrong-import-position

try:
    sys.stdout.reconfigure(newline="\n")
except (AttributeError, ValueError):
    pass

SCHEMA = "crew-ci-gate-receipt/v1"
WORKFLOW = ".github/workflows/verify-gate.yml"
WORKFLOW_FILE = os.path.basename(WORKFLOW)
ARTIFACT = "crew-verify-receipt"
RECEIPT_NAME = "receipt.json"
_HOOKS = "plugin/crew/hooks/scripts/"
# The code that runs the gate, writes its evidence (marker, record,
# fingerprint), reads that evidence back as a verdict, or builds and uploads
# the receipt. A push runs the workflow AT the pushed sha, so a branch that
# changes any of these would have its own edit vouch for itself: such a
# branch gates locally. This is tamper-evidence against the direct forgery
# path, not isolation -- a rule command is branch code either way, exactly as
# it is in a local gate, and review is the control for that.
GATE_IMPL = (WORKFLOW, _HOOKS + "ci_receipt.py", _HOOKS + "review_gate.py",
             _HOOKS + "verify-gate.sh", _HOOKS + "_common.sh", _HOOKS + "verify_record.py",
             _HOOKS + "verify_fingerprint.py")
PRODUCER_PATHS = GATE_IMPL
EVENTS = ("push", "workflow_dispatch")
BASE = "origin/main"

VERIFIED, UNVERIFIED, UNKNOWN, NO_GATE = (review_gate.VERIFIED, review_gate.UNVERIFIED,
                                          review_gate.UNKNOWN, review_gate.NO_GATE)
EXIT = {VERIFIED: 0, UNVERIFIED: 1, UNKNOWN: 3, NO_GATE: 4}
EXIT_USAGE = 2

_GH_TIMEOUT_S = 60
_RECORD = os.path.join(".crew", ".verify-gate.record.json")
_REMOTE_RE = re.compile(r"github\.com[:/]+([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
_ELAPSED_RE = re.compile(r"^verify-gate: (\d+)s  (.+)$")
_SKIP_RE = re.compile(r"^verify-gate: SKIP \(rc 77[^)]*\): (.+)$")
_FAILED_RE = re.compile(r"^VERIFY FAILED: (.+)$")


class Unreadable(Exception):
    """Something needed for an answer could not be read: UNKNOWN, never a pass."""


def _git(root, *args):
    try:
        out = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=root,
                             capture_output=True, text=True, check=False, timeout=60,
                             stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Unreadable(f"git {args[0]} could not run: {exc}") from exc
    if out.returncode != 0:
        raise Unreadable(f"git {' '.join(args)} exited {out.returncode}: "
                         f"{(out.stderr or '').strip()}")
    return out.stdout.strip()


def _git_ok(root, *args):
    """True/False for a git command whose exit status IS the answer."""
    try:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                             check=False, timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Unreadable(f"git {args[0]} could not run: {exc}") from exc
    return out.returncode == 0


def _verify_blob(root):
    """The blob id of `.crew/verify.json` at HEAD, or None when HEAD has none."""
    if not _git_ok(root, "cat-file", "-e", "HEAD:.crew/verify.json"):
        return None
    return _git(root, "rev-parse", "HEAD:.crew/verify.json")


def _worktree_blob(root):
    """`git hash-object` of the working copy of `.crew/verify.json`, or None."""
    if not os.path.isfile(os.path.join(root, ".crew", "verify.json")):
        return None
    return _git(root, "hash-object", "--", ".crew/verify.json")


def _material_changes(root):
    try:
        changed = review_gate.changed_now(root)
    except review_gate._Unreadable as exc:  # pylint: disable=protected-access
        raise Unreadable(str(exc)) from exc
    return verify_fingerprint._material(changed)  # pylint: disable=protected-access


def _no_gate_reason(root):
    """The NO_GATE reason, or None. Asked of `review_gate.gate_state` itself, so
    the stand-down test (and the repo-config read behind it) has one home."""
    state, why = review_gate.gate_state(root)
    return why if state == NO_GATE else None


# --- build (runner side) -----------------------------------------------------------

def parse_log(text):
    """Per-command outcomes from verify-gate's stderr, in order: `{cmd, seconds,
    state}` with state PASS, FAIL or SKIP. Informative only."""
    out, pending = [], {}
    for raw in (text or "").splitlines():
        line = raw.rstrip("\r")
        skip, failed, elapsed = _SKIP_RE.match(line), _FAILED_RE.match(line), \
            _ELAPSED_RE.match(line)
        if skip:
            pending[skip.group(1)] = "SKIP"
        elif failed:
            pending[failed.group(1)] = "FAIL"
        elif elapsed:
            cmd = elapsed.group(2)
            out.append({"cmd": cmd, "seconds": int(elapsed.group(1)),
                        "state": pending.pop(cmd, "PASS")})
    return out


def _outstanding(root):
    """(entries, problem): the per-rule record's not-verified entries."""
    path = os.path.join(root, _RECORD)
    if not os.path.isfile(path):
        return [], None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return [], f"the per-rule record could not be read: {exc}"
    rules = data.get("rules") if isinstance(data, dict) else None
    if rules is None:
        return [], None
    if not isinstance(rules, dict):
        return [], "the per-rule record's rules is not an object"
    entries = [{"label": str(v.get("label", "?")), "status": str(v.get("status", "?")),
                "reason": str(v.get("reason", ""))}
               for v in rules.values() if isinstance(v, dict)]
    if len(entries) != len(rules):
        return entries, "the per-rule record holds an entry that is not an object"
    return entries, None


def _rc(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def gate_impl(root):
    """sha256 over the blob ids of GATE_IMPL at HEAD: which gate produced the
    verdict. With `tree` and `verify_json` it is every input L-0512's tree
    cache key needs; None when HEAD lacks one of the files."""
    digest = hashlib.sha256(b"crew-ci-gate-impl-v1")
    for path in GATE_IMPL:
        if not _git_ok(root, "cat-file", "-e", f"HEAD:{path}"):
            return None
        blob_id = _git(root, "rev-parse", f"HEAD:{path}")
        digest.update(b"\0" + path.encode() + b"\0" + blob_id.encode())
    return digest.hexdigest()


def _marker_fresh(root, since):
    """True when the verified marker was written at or after `since` (epoch
    seconds): evidence from THIS gate run, not one left in the workspace."""
    try:
        return os.path.getmtime(os.path.join(root, review_gate.MARKER)) >= since
    except OSError:
        return False


def build(root, gate_rc, gate_log, env=None, since=None):
    """The receipt for the gate run that just finished in `root`. `since` is
    the epoch second the gate started; the marker must be newer."""
    env = os.environ if env is None else env
    root = os.path.abspath(root)
    reasons = []
    receipt = {"schema": SCHEMA, "pass": False, "reasons": reasons}
    try:
        head = _git(root, "rev-parse", "HEAD")
        receipt["head"] = head
        receipt["tree"] = _git(root, "rev-parse", "HEAD^{tree}")
        receipt["verify_json"] = _verify_blob(root)
        receipt["gate_impl"] = gate_impl(root)
        worktree_blob = _worktree_blob(root)
        material = _material_changes(root)
    except Unreadable as exc:
        reasons.append(f"could not read the checkout: {exc}")
        return receipt
    rc = _rc(gate_rc)
    state, why = review_gate.gate_state(root)
    outstanding, record_problem = _outstanding(root)
    receipt.update({
        "gate": {"rc": rc, "state": state, "reason": why},
        "outstanding": outstanding,
        "clean": not material,
        "commands": parse_log(gate_log),
        "run": {"id": str(env.get("GITHUB_RUN_ID", "")),
                "attempt": str(env.get("GITHUB_RUN_ATTEMPT", "")),
                "repository": env.get("GITHUB_REPOSITORY", ""),
                "event": env.get("GITHUB_EVENT_NAME", ""),
                "sha": env.get("GITHUB_SHA", ""),
                "workflow_ref": env.get("GITHUB_WORKFLOW_REF", ""),
                "runner": env.get("RUNNER_NAME", "")},
    })
    if rc != 0:
        reasons.append(f"verify-gate.sh --all exited {gate_rc!r}, not 0")
    if state != VERIFIED:
        reasons.append(f"gate state on the runner is {state}: {why}")
    if record_problem:
        reasons.append(record_problem)
    if outstanding:
        reasons.append(f"{len(outstanding)} rule(s) in the per-rule record are not verified")
    if material:
        reasons.append(f"{len(material)} path(s) differ from HEAD after the gate: "
                       + ", ".join(material[:5]))
    if receipt["verify_json"] is None:
        reasons.append("HEAD carries no .crew/verify.json")
    elif worktree_blob != receipt["verify_json"]:
        reasons.append("the working .crew/verify.json differs from HEAD's")
    if since is None:
        reasons.append("no gate start time given, so the marker cannot be shown to be "
                       "from this run")
    elif not _marker_fresh(root, since):
        reasons.append("the verified marker is older than this gate run (or absent): "
                       "the evidence is not this run's")
    if receipt["run"]["sha"] and receipt["run"]["sha"] != head:
        reasons.append(f"GITHUB_SHA {receipt['run']['sha']} is not HEAD {head}")
    receipt["pass"] = not reasons
    return receipt


def _summary(receipt):
    lines = [f"## crew verify-gate receipt: {'PASS' if receipt.get('pass') else 'NOT PASSED'}",
             "", f"head `{receipt.get('head', '-')}` tree `{receipt.get('tree', '-')}` "
             f"verify.json `{receipt.get('verify_json', '-')}`", ""]
    lines += [f"- {r}" for r in receipt.get("reasons", [])]
    cmds = receipt.get("commands") or []
    if cmds:
        lines += ["", "| state | s | command |", "|---|---|---|"]
        lines += [f"| {c['state']} | {c['seconds']} | `{c['cmd'][:120].replace('|', '/')}` |"
                  for c in cmds]
    return "\n".join(lines) + "\n"


# --- check (local side) ------------------------------------------------------------

def gh_fetch(path):
    """`gh api <path>`'s body as bytes. Any failure is Unreadable."""
    gh = shutil.which("gh")
    if gh is None:
        raise Unreadable("gh is not on PATH, so the run and its receipt cannot be read")
    try:
        out = subprocess.run([gh, "api", path], capture_output=True, check=False,
                             timeout=_GH_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Unreadable(f"gh could not run: {exc}") from exc
    if out.returncode != 0:
        err = out.stderr.decode("utf-8", "replace").strip()
        raise Unreadable(f"gh api {path} exited {out.returncode}: {err}")
    return out.stdout


def _json(fetch, path):
    try:
        data = json.loads(fetch(path).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, AttributeError) as exc:
        raise Unreadable(f"{path} did not return JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise Unreadable(f"{path} returned {type(data).__name__}, not an object")
    return data


def repo_slug(root):
    url = _git(root, "remote", "get-url", "origin")
    match = _REMOTE_RE.search(url)
    if not match:
        raise Unreadable(f"origin {url!r} is not a GitHub repository URL")
    return f"{match.group(1)}/{match.group(2)}"


def _run_key(run):
    return (str(run.get("created_at") or ""), _rc(run.get("id")) or 0,
            _rc(run.get("run_attempt")) or 0)


def _newest_run(fetch, slug, head):
    data = _json(fetch, f"repos/{slug}/actions/workflows/{WORKFLOW_FILE}/runs"
                        f"?head_sha={head}&per_page=100")
    runs = data.get("workflow_runs")
    if not isinstance(runs, list):
        raise Unreadable("the workflow-runs response has no workflow_runs list")
    mine = [r for r in runs if isinstance(r, dict)
            and r.get("head_sha") == head
            and r.get("path") == WORKFLOW
            and r.get("event") in EVENTS
            and (r.get("repository") or {}).get("full_name") == slug
            and (r.get("head_repository") or {}).get("full_name") == slug]
    return max(mine, key=_run_key) if mine else None


def artifact_name(attempt):
    """One artifact per attempt, so a re-run's receipt is never confused with
    an earlier attempt's."""
    return f"{ARTIFACT}-{attempt}"


def _receipt_bytes(fetch, slug, run, head):
    run_id, name = str(run.get("id")), artifact_name(run.get("run_attempt"))
    data = _json(fetch, f"repos/{slug}/actions/runs/{run_id}/artifacts?per_page=100")
    arts = data.get("artifacts")
    if not isinstance(arts, list):
        raise Unreadable(f"run {run_id}'s artifacts response has no artifacts list")
    named = [a for a in arts if isinstance(a, dict) and a.get("name") == name]
    if not named:
        raise Unreadable(f"run {run_id} concluded success but has no {name} artifact")
    if len(named) > 1:
        raise Unreadable(f"run {run_id} has {len(named)} artifacts named {name}; ambiguous")
    art = named[0]
    if art.get("expired") is not False:
        raise Unreadable(f"run {run_id}'s {name} artifact has expired")
    origin = art.get("workflow_run") or {}
    if str(origin.get("id")) != run_id or origin.get("head_sha") != head:
        raise Unreadable(f"artifact {art.get('id')} names run {origin.get('id')} at "
                         f"{origin.get('head_sha')}, not run {run_id} at HEAD")
    blob = fetch(f"repos/{slug}/actions/artifacts/{art.get('id')}/zip")
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            return zf.read(RECEIPT_NAME)
    except (zipfile.BadZipFile, KeyError, OSError, TypeError) as exc:
        raise Unreadable(f"run {run_id}'s {ARTIFACT} artifact holds no readable "
                         f"{RECEIPT_NAME}: {exc}") from exc


def _mismatch(receipt, want):
    """The first field of `receipt` that does not equal `want`, or None."""
    for path, expected in want:
        node = receipt
        for key in path.split("."):
            node = node.get(key) if isinstance(node, dict) else None
        if node != expected:
            return f"receipt {path} is {node!r}, expected {expected!r}"
    return None


def _local(root):
    """(head, tree, blob, worktree blob, material changes): one observation."""
    return (_git(root, "rev-parse", "HEAD"), _git(root, "rev-parse", "HEAD^{tree}"),
            _verify_blob(root), _worktree_blob(root), _material_changes(root))


def check(root, fetch=None):
    """(state, reason, head) for the checkout at `root`. The newest eligible
    run is chosen BEFORE its status is looked at, so a newer pending or failed
    run is never passed over for an older success."""
    root = os.path.abspath(root)
    fetch = gh_fetch if fetch is None else fetch
    head = None
    try:
        no_gate = _no_gate_reason(root)
        if no_gate:
            return NO_GATE, no_gate, head
        first = _local(root)
        head, tree, blob, worktree, material = first
        if blob is None:
            return UNVERIFIED, "HEAD carries no .crew/verify.json; a CI receipt cannot cover it", head
        if worktree != blob:
            return UNVERIFIED, ("the working .crew/verify.json differs from HEAD's; the CI "
                                "receipt covers HEAD's map only"), head
        impl = gate_impl(root)
        if impl is None:
            return UNVERIFIED, ("HEAD lacks a gate implementation file (GATE_IMPL), so the "
                                "receipt's gate_impl cannot be matched"), head
        if material:
            return UNVERIFIED, (f"{len(material)} path(s) differ from HEAD locally "
                                f"({', '.join(material[:3])}); a CI receipt covers only the "
                                "committed tree - commit and push, or gate locally"), head
        if not _git_ok(root, "rev-parse", "--verify", "-q", f"{BASE}^{{commit}}"):
            raise Unreadable(f"{BASE} is not a commit here, so whether this branch changed "
                             "the receipt producer cannot be told")
        producer = _git(root, "diff", "--name-only", f"{BASE}...HEAD", "--", *PRODUCER_PATHS)
        if producer:
            return UNVERIFIED, (f"this branch changes the receipt producer "
                                f"({', '.join(producer.split())}); a receipt it produced "
                                "cannot vouch for itself - gate locally"), head
        slug = repo_slug(root)
        run = _newest_run(fetch, slug, head)
        if run is None:
            return UNVERIFIED, (f"no {WORKFLOW_FILE} run for HEAD in {slug} (not pushed, "
                                "CREW_RUNNER unset, or the run not started)"), head
        run_id = str(run.get("id"))
        if run.get("status") != "completed":
            return UNVERIFIED, f"{WORKFLOW_FILE} run {run_id} is {run.get('status')}, not completed", head
        if run.get("conclusion") != "success":
            return UNVERIFIED, (f"{WORKFLOW_FILE} run {run_id} (the newest for HEAD) concluded "
                                f"{run.get('conclusion')}"), head
        raw = _receipt_bytes(fetch, slug, run, head)
        try:
            receipt = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise Unreadable(f"run {run_id}'s {RECEIPT_NAME} is not JSON: {exc}") from exc
        if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
            raise Unreadable(f"run {run_id}'s {RECEIPT_NAME} is not a {SCHEMA} receipt")
        wrong = _mismatch(receipt, (
            ("head", head), ("tree", tree), ("verify_json", blob), ("gate_impl", impl),
            ("run.id", run_id), ("run.attempt", str(run.get("run_attempt"))),
            ("run.repository", slug), ("pass", True), ("gate.state", VERIFIED),
            ("gate.rc", 0), ("outstanding", []), ("clean", True)))
        if wrong:
            return UNVERIFIED, f"run {run_id}: {wrong}", head
        again = _newest_run(fetch, slug, head)
        if again is None or (str(again.get("id")), again.get("run_attempt"),
                             again.get("status"), again.get("conclusion")) != (
                                 run_id, run.get("run_attempt"), "completed", "success"):
            raise Unreadable(f"the newest {WORKFLOW_FILE} run for HEAD changed while the "
                             "receipt was being checked")
        if _local(root) != first:
            raise Unreadable("HEAD, its tree, .crew/verify.json or the working tree changed "
                             "while the receipt was being checked")
    except Unreadable as exc:
        return UNKNOWN, str(exc), head
    except Exception as exc:  # pylint: disable=broad-except
        return UNKNOWN, f"the CI receipt could not be checked: {type(exc).__name__}: {exc}", head
    return VERIFIED, (f"CI receipt from {WORKFLOW_FILE} run {run_id} attempt "
                      f"{run.get('run_attempt')} covers HEAD {head[:12]}, tree {tree[:12]}, "
                      f"verify.json {blob[:12]}"), head


# --- CLI ---------------------------------------------------------------------------

def _write(path, text):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    b = sub.add_parser("build")
    b.add_argument("--root", default=".")
    b.add_argument("--gate-rc", required=True)
    b.add_argument("--gate-log", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--summary")
    b.add_argument("--since", type=int,
                   help="epoch second the gate started; the marker must be newer")
    c = sub.add_parser("check")
    c.add_argument("--root", default=".")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code in (0, None) else EXIT_USAGE
    if args.verb == "build":
        try:
            with open(args.gate_log, encoding="utf-8", errors="replace") as fh:
                log = fh.read()
        except OSError as exc:
            log = ""
            print(f"ci-receipt: gate log unreadable: {exc}", file=sys.stderr)
        receipt = build(args.root, args.gate_rc, log, since=args.since)
        if not log:
            receipt["pass"] = False
            receipt["reasons"].append("the gate log is empty or unreadable")
        text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        _write(args.out, text)
        summary = _summary(receipt)
        if args.summary:
            try:
                with open(args.summary, "a", encoding="utf-8", newline="\n") as fh:
                    fh.write(summary)
            except OSError as exc:
                print(f"ci-receipt: step summary not written: {exc}", file=sys.stderr)
        print(summary, end="")
        print(f"CI_RECEIPT_BUILT pass={str(receipt['pass']).lower()} "
              f"sha256={hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}")
        return 0 if receipt["pass"] else 1
    state, reason, head = check(args.root)
    print(f"CI_RECEIPT {state} head={head or '-'} {' '.join(str(reason).split())}")
    return EXIT[state]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
