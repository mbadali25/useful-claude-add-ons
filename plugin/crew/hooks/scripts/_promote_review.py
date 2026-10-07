"""promote-gate's review evidence (L-0703): is the sha being deployed covered
by an accepted review?

    _promote_review.py <tree> <full sha> <deadline> <environment>...

`<deadline>` is the gate's own deadline as a Unix time in seconds, so the
time this interpreter takes to start counts against it too.

Run by BOTH promote-gate.sh and promote-gate.ps1 from the project dir (the
map is `.crew/verify.json` there), so the two flavours cannot decide this
differently. stdout carries only the unmet preconditions, joined by U+001E
(the gates' separator), and is empty when every environment is satisfied.
Exit 0 means "decided". Any other status is could-not-tell, and both gates
block on it ("the pre-deploy check could not be evaluated"); a traceback is a
non-zero status too, so a crash never reads as a pass.

WHICH ENVIRONMENTS. Every gated environment requires review evidence unless
its map entry says `"requireReview": false` AND gives a non-empty
`reviewReason` string - the `rollback: "none"` + `rollbackReason` pattern. A
`requireReview` that is anything but true or false is refused, never read as
either. `requireHuman` does not waive it: the human's yes is a deploy
go/no-go, not a code review, and the approval marker is a file the session
can create itself.

WHAT COVERS THE SHA. A review ledger under `<git-common-dir>/crew/review/`,
read only through `review_ledger.status` and `review_ledger.check_receipt`,
for which ALL of these hold:
  1. its state is ACCEPTED and its receipt is for its latest round;
  2. that round's reviewed head H is a full sha whose TREE is the deploying
     commit's tree (`H^{tree} == D^{tree}`; D == H is the common case). An
     ancestor relation, or the delta gate's keep alone, would admit tracked
     bytes nobody was shown;
  3. `review_ledger.check_receipt`, run in the tree being deployed, says the
     receipt stands - the definition `/crew:done` uses: `receipt_stands`,
     check E, and the bundle rebuilt from the receipt's base equal to the
     accepted one (a review of a dirty tree cannot be rebuilt, so it fails);
  4. the ledger's bytes did not change while 3 ran.
What that does NOT prove - paths the bundle left out as identical to merged
main or excluded by check E, ignored build output, and who wrote the ledger
(local JSON, protected only by scope_guard's textual refusal) - is stated in
promote.md and the README.

BOUNDED. The search runs in a CHILD process in its own process group (it
rebuilds a bundle, and a git call inside review_patch may wait 30s). The
parent waits only until the gate's deadline (and never more than
`BUDGET_SECONDS`), then kills the whole group and reports could-not-tell.
`CREW_PROMOTE_REVIEW_BUDGET` may only SHORTEN that (tests use it to prove
the kill); it can never lengthen it. Less than `MIN_SECONDS`
left is could-not-tell without starting the search.
"""
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crew_common  # noqa: E402  pylint: disable=wrong-import-position

BUDGET_SECONDS = 12.0
MIN_SECONDS = 1.0
BUDGET_ENV = "CREW_PROMOTE_REVIEW_BUDGET"
SEP = "\x1e"
GIT_SECONDS = 10
_FULL_SHA = re.compile(r"[0-9a-f]{40}")


class CouldNotTell(Exception):
    """The helper could not decide; the gate blocks."""


def fold(text):
    """The gates' key folding: per-character simple upper case (the
    matcher's `fold` in promote-gate.sh)."""
    return "".join(c.upper() if len(c.upper()) == 1 else c for c in text)


def no_case_twins(pairs):
    """Keys folded; a key repeated, or two differing only by case, refuses
    the map, as both gates refuse it."""
    seen = set()
    for key, _ in pairs:
        if fold(key) in seen:
            raise ValueError(f"duplicate or case-differing key `{key}`")
        seen.add(fold(key))
    return {fold(k): v for k, v in pairs}


def requirement(env, cfg):
    """(needs review, problem or None) for one environment's map entry."""
    if "REQUIREREVIEW" not in cfg:
        return True, None
    value = cfg["REQUIREREVIEW"]
    if value is True:
        return True, None
    if value is False:
        reason = cfg.get("REVIEWREASON")
        if isinstance(reason, str) and reason.strip():
            return False, None
        return False, (f"'{env}' sets requireReview: false but has no reviewReason string. "
                       f"State why {env} may take a deploy nobody reviewed. Fix: add a "
                       "non-empty reviewReason string next to requireReview in "
                       ".crew/verify.json.")
    return False, (f"'{env}' has requireReview: {json.dumps(value)}, which is not true or "
                   "false. Fix: set it to true, or to false plus a reviewReason string.")


def budget(deadline):
    """The seconds the search may take: what is left until the gate's
    deadline, capped, and only ever shortened by the environment variable."""
    try:
        left = float(deadline) - time.time()
    except ValueError as exc:
        raise CouldNotTell(f"deadline {deadline!r} is not a number") from exc
    cap = BUDGET_SECONDS
    raw = os.environ.get(BUDGET_ENV)
    if raw:
        try:
            cap = min(cap, max(0.5, float(raw)))
        except ValueError:
            pass
    return min(left, cap)


# --------------------------------------------------------------------------
# the search (child process)

def _git(tree, args, data=None):
    done = subprocess.run([crew_common.require_tool("git"), "-C", tree] + args, input=data,
                          capture_output=True, text=True, check=False, timeout=GIT_SECONDS,
                          stdin=None if data is not None else subprocess.DEVNULL)
    return done.returncode, done.stdout


def _digest(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def _accepted(tree, ledger_dir, names):
    """[(ticket, reviewed head, ledger path)] for every ledger whose state is
    ACCEPTED with its receipt on its latest round and a full-sha head."""
    import review_ledger  # pylint: disable=import-outside-toplevel
    found = []
    for name in names:
        if not name.endswith(".json"):
            continue
        ticket = name[:-len(".json")]
        try:
            review_ledger.check_ticket(ticket)
            st = review_ledger.status(tree, ticket)
        except review_ledger.LedgerError:
            continue
        receipt, rounds = st.get("receipt"), st.get("rounds")
        if st.get("state") != review_ledger.ACCEPTED or not isinstance(receipt, dict):
            continue
        if not isinstance(rounds, list) or not rounds or not isinstance(rounds[-1], dict):
            continue
        head = rounds[-1].get("head")
        if rounds[-1].get("round") != receipt.get("round") or not isinstance(head, str) \
                or not _FULL_SHA.fullmatch(head):
            continue
        found.append((ticket, head, os.path.join(ledger_dir, name)))
    return found


def find_cover(tree, sha):
    """(covered, detail): the receipt that covers `sha`, or why none does."""
    import review_ledger  # pylint: disable=import-outside-toplevel
    code, out = _git(tree, ["rev-parse", "--verify", "-q", sha + "^{tree}"])
    want = out.strip()
    if code != 0 or not want:
        return False, f"could not tell: the tree of {sha} could not be read"
    try:
        ledger_dir = os.path.dirname(review_ledger.ledger_path(tree, "probe"))
    except review_ledger.LedgerError as exc:
        return False, f"could not tell: {exc}"
    try:
        names = sorted(os.listdir(ledger_dir))
    except FileNotFoundError:
        return False, "this repository has no review ledger at all"
    except OSError as exc:
        return False, f"could not tell: the review ledgers could not be listed ({exc})"
    accepted = _accepted(tree, ledger_dir, names)
    if not accepted:
        return False, "no ticket's review ledger holds an accepted receipt"
    code, out = _git(tree, ["cat-file", "--batch-check=%(objectname) %(objecttype)"],
                     data="".join(f"{head}^{{tree}}\n" for _, head, _ in accepted))
    lines = out.splitlines()
    if code != 0 or len(lines) != len(accepted):
        return False, "could not tell: the reviewed heads' trees could not be read"
    candidates = [entry for entry, line in zip(accepted, lines)
                  if line == f"{want} tree"]
    if not candidates:
        return False, ("no accepted review was of a tree identical to this sha's tree, so "
                       "these bytes were never shown to a reviewer as they are")
    candidates.sort(key=lambda entry: os.path.getmtime(entry[2]), reverse=True)
    reasons = []
    for ticket, head, path in candidates:
        before = _digest(path)
        try:
            ok, why = review_ledger.check_receipt(tree, ticket)
        except (review_ledger.LedgerError, RuntimeError, OSError, ValueError) as exc:
            ok, why = False, f"could not be checked: {exc}"
        if ok and before is not None and before == _digest(path):
            return True, f"{ticket}: {why} (reviewed head {head[:12]})"
        reasons.append(f"{ticket}: {why}" if not ok else f"{ticket}: its ledger changed while read")
    return False, "the accepted reviews of this tree do not stand - " + "; ".join(reasons)


def child_main(tree, sha):
    covered, detail = find_cover(tree, sha)
    sys.stdout.write(json.dumps({"covered": covered, "detail": detail}))
    return 0


# --------------------------------------------------------------------------
# the bounded wait (parent process)

def _kill_group(proc):
    """Kill the child and everything it started."""
    if os.name == "nt":
        taskkill = crew_common.resolve_tool("taskkill")
        if taskkill:
            subprocess.run([taskkill, "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                           check=False, timeout=5, stdin=subprocess.DEVNULL)
        proc.kill()
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()


def search(tree, sha, seconds):
    """(covered, detail), bounded by `seconds` of wall clock."""
    if seconds < MIN_SECONDS:
        return False, (f"could not tell: only {max(seconds, 0):.1f}s of the gate's deadline "
                       "was left to look for a receipt")
    kwargs = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
              else {"start_new_session": True})
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        [sys.executable, os.path.abspath(__file__), "--cover", tree, sha],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    try:
        out, err = proc.communicate(timeout=seconds)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        try:
            proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        return False, (f"could not tell: the receipt check did not finish inside {seconds:.1f}s "
                       "and was stopped")
    try:
        answer = json.loads(out.decode("utf-8", errors="replace"))
        return answer["covered"] is True, str(answer["detail"])
    except (ValueError, KeyError, TypeError):
        tail = err.decode("utf-8", errors="replace").strip().splitlines()[-1:] or ["no output"]
        return False, (f"could not tell: the receipt check failed (exit {proc.returncode}: "
                       f"{tail[0]})")


def main(argv):
    if argv[:1] == ["--cover"] and len(argv) == 3:
        return child_main(argv[1], argv[2])
    if len(argv) < 4:
        print("usage: _promote_review.py <tree> <full sha> <deadline> <environment>...",
              file=sys.stderr)
        return 2
    tree, sha, deadline, envs = argv[0], argv[1].lower(), argv[2], argv[3:]
    if not _FULL_SHA.fullmatch(sha):
        print(f"_promote_review.py: not a full sha: {sha!r}", file=sys.stderr)
        return 2
    try:
        seconds = budget(deadline)
    except CouldNotTell as exc:
        print(f"_promote_review.py: {exc}", file=sys.stderr)
        return 2
    with open(".crew/verify.json", encoding="utf-8-sig") as fh:
        doc = json.load(fh, object_pairs_hook=no_case_twins)
    environments = doc.get("ENVIRONMENTS", {}) if isinstance(doc, dict) else {}
    problems, needing = [], []
    for env in envs:
        cfg = environments.get(fold(env), {}) if isinstance(environments, dict) else {}
        need, problem = requirement(env, cfg if isinstance(cfg, dict) else {})
        if problem:
            problems.append((env, problem))
        elif need:
            needing.append(env)
    if needing:
        covered, detail = search(tree, sha, seconds)
        if not covered:
            for env in needing:
                problems.append((env, (
                    f"'{env}' requires an accepted review of the sha being deployed ({sha}), "
                    f"and there is none: {detail}. Run /crew:review on this exact tree and get "
                    f"it accepted, or set requireReview: false plus a reviewReason on '{env}' "
                    "in .crew/verify.json.")))
    sys.stdout.write(SEP.join(f"[{env}] {msg}" if len(envs) > 1 else msg
                              for env, msg in problems))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
