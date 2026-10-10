"""promote-gate's review evidence (L-0703): is the sha being deployed covered
by an accepted review?

    _promote_review.py <tree> <full sha> <deadline> <environment>...

`<deadline>` is the gate's own deadline as a Unix time in seconds, so the
time this interpreter takes to start counts against it too.

Run by BOTH promote-gate.sh and promote-gate.ps1 from the project dir, so
the two flavours cannot decide this differently.

WHICH MAP (L-0768). The policy is the map COMMITTED IN THE SHA BEING DEPLOYED:
`git -C <tree> ls-tree --full-tree <sha> -- .crew/verify.json`, then that
blob (`policy_map_text`). The sha is the tree's HEAD (T-0505), so this is
exactly what a deploy from a checkout of that sha reads: a worktree can do
nothing a checkout of the same sha could not, and a waiver committed on the
branch being deployed is seen. Read from the project dir instead, a
worktree deploy was judged by the main checkout's map - its waiver admitted
a branch that required review, and the branch's own waiver was never read.
Only when the sha carries no map at all (an old sha, a repo whose map is
ignored) is the project dir's map the policy, read as before: the working
file held to the project dir's HEAD (`project_map_text`). That fallback is
why this still runs with the project dir as cwd: a worktree's untracked or
ignored copy is never read. A listing that fails is could-not-tell, never
"no map". Every read of the sha's map passes `--no-replace-objects`: a
`refs/replace/` entry would otherwise swap the map's bytes (or the commit's
tree) with nothing committed and the sha and tree hashes unchanged.
promote-gate.sh's VERDICT step imports `policy_map_text`, and
promote-gate.ps1 makes the same two git calls (`ls-tree --full-tree`, then
`cat-file blob`), so requires / rollback / requireHuman come from the same
map as requireReview. stdout carries only the unmet preconditions, joined by U+001E
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
# Killing and reaping a search that ran out of time; the gate's 16s deadline
# leaves 4s of the 20s hook timeout for this and the hook's own exit.
REAP_SECONDS = 2.0
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
    """([(ticket, reviewed head, ledger path, digest)], [unreadable ticket])
    for every ledger whose state is ACCEPTED with its receipt on its latest
    round and a full-sha head. The digest is taken BEFORE the ledger is read,
    and compared again after check_receipt (find_cover), so a ledger replaced
    at any point in between cannot lend one receipt's head to another's
    check (L-0703 review r2)."""
    import review_ledger  # pylint: disable=import-outside-toplevel
    found, unreadable = [], []
    for name in names:
        if not name.endswith(".json"):
            continue
        ticket = name[:-len(".json")]
        digest = _digest(os.path.join(ledger_dir, name))
        try:
            review_ledger.check_ticket(ticket)
            st = review_ledger.status(tree, ticket)
        except review_ledger.LedgerError:
            continue
        if digest is None or st.get("state") == review_ledger.UNKNOWN:
            unreadable.append(ticket)
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
        found.append((ticket, head, os.path.join(ledger_dir, name), digest))
    return found, unreadable


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
    accepted, unreadable = _accepted(tree, ledger_dir, names)
    # An unreadable ledger is could-not-tell, never "holds no receipt"; it
    # still cannot cover, so it only changes what the refusal says.
    unknown = (f"could not tell: {len(unreadable)} ledger(s) could not be read "
               f"({', '.join(unreadable[:5])}); " if unreadable else "")
    if not accepted:
        return False, unknown + "no readable ticket's review ledger holds an accepted receipt"
    code, out = _git(tree, ["cat-file", "--batch-check=%(objectname) %(objecttype)"],
                     data="".join(f"{head}^{{tree}}\n" for _, head, _, _ in accepted))
    lines = out.splitlines()
    if code != 0 or len(lines) != len(accepted):
        return False, "could not tell: the reviewed heads' trees could not be read"
    candidates = [entry for entry, line in zip(accepted, lines)
                  if line == f"{want} tree"]
    if not candidates:
        return False, unknown + ("no accepted review was of a tree identical to this sha's "
                                 "tree, so these bytes were never shown to a reviewer as they are")
    candidates.sort(key=lambda entry: os.path.getmtime(entry[2]), reverse=True)
    reasons = []
    for ticket, head, path, before in candidates:
        try:
            ok, why = review_ledger.check_receipt(tree, ticket)
        except (review_ledger.LedgerError, RuntimeError, OSError, ValueError) as exc:
            ok, why = False, f"could not be checked: {exc}"
        if ok and before is not None and before == _digest(path):
            return True, f"{ticket}: {why} (reviewed head {head[:12]})"
        reasons.append(f"{ticket}: {why}" if not ok else f"{ticket}: its ledger changed while read")
    return False, unknown + "the accepted reviews of this tree do not stand - " + "; ".join(reasons)


def child_main(tree, sha):
    covered, detail = find_cover(tree, sha)
    sys.stdout.write(json.dumps({"covered": covered, "detail": detail}))
    return 0


# --------------------------------------------------------------------------
# the bounded wait (parent process)

def _left(deadline):
    """Seconds left until `deadline` (a Unix time) for one bounded call;
    none left is could-not-tell."""
    try:
        left = float(deadline) - time.time()
    except ValueError as exc:
        raise CouldNotTell(f"deadline {deadline!r} is not a number") from exc
    if left < MIN_SECONDS / 2:
        raise CouldNotTell("the gate's deadline passed before the review check could finish")
    return min(left, GIT_SECONDS)


def _kill_group(proc, until):
    """Kill the child and everything it started, by `until` (a monotonic time)."""
    if os.name == "nt":
        # PATH first, then the system copy: a PATH without System32 must not
        # leave the search's descendants running.
        taskkill = crew_common.resolve_tool("taskkill") or next(
            (p for p in (os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32",
                                      "taskkill.exe"),) if os.path.isfile(p)), None)
        if taskkill:
            try:
                # Half of what is left, so the reap below keeps the rest.
                subprocess.run([taskkill, "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                               check=False, stdin=subprocess.DEVNULL,
                               timeout=max((until - time.monotonic()) / 2, 0.1))
            except (OSError, subprocess.SubprocessError):
                pass  # the child is still killed below; the deploy is refused either way
        proc.kill()
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()


def _stop(proc):
    """Kill the search's group and reap it, the two together inside
    REAP_SECONDS. The gate's deadline is 16s of the 20s hook timeout, and
    this is what spends the difference: on Windows a flat 5s `taskkill` and
    then a 2s reap returned the refusal after the hook had timed out, which is
    not a block (L-0703 Codex r3)."""
    until = time.monotonic() + REAP_SECONDS
    _kill_group(proc, until)
    try:
        proc.communicate(timeout=max(until - time.monotonic(), 0.1))
    except subprocess.TimeoutExpired:
        pass


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
        _stop(proc)
        return False, (f"could not tell: the receipt check did not finish inside {seconds:.1f}s "
                       "and was stopped")
    try:
        answer = json.loads(out.decode("utf-8", errors="replace"))
        if proc.returncode != 0:
            raise ValueError(f"exit {proc.returncode}")
        return answer["covered"] is True, str(answer["detail"])
    except (ValueError, KeyError, TypeError):
        tail = err.decode("utf-8", errors="replace").strip().splitlines()[-1:] or ["no output"]
        return False, (f"could not tell: the receipt check failed (exit {proc.returncode}: "
                       f"{tail[0]})")


def project_map_text(deadline):
    """The PROJECT DIR's `.crew/verify.json` text (the cwd), read ONCE, and -
    when HEAD carries a map - only when those bytes are the map committed at
    HEAD. Used only when the deployed sha carries no map (policy_map_text).
    The gate refused an uncommitted map before it ran this, but that check and this read are two moments: an opt-out
    written in between would otherwise waive review for a deploy (L-0703
    review r1). git hash-object compares the bytes read, not the file now."""
    # Every git call here is bounded by what is left of the gate's deadline
    # (L-0703 review r2), never by a flat GIT_SECONDS that two calls could
    # spend past the hook timeout.
    try:
        if not os.path.isfile(".crew/verify.json"):
            raise CouldNotTell(".crew/verify.json is not a regular file")
        with open(".crew/verify.json", "rb") as fh:
            raw = fh.read()
        git = crew_common.require_tool("git")
        # --path: hash the bytes as git would store THIS path (autocrlf and
        # .gitattributes eol applied), or a Windows checkout's CRLF map never
        # equals its own LF blob.
        hashed = subprocess.run([git, "hash-object", "--stdin", "--path", ".crew/verify.json"],
                                input=raw, capture_output=True, check=False,
                                timeout=_left(deadline))
        # ls-tree, not rev-parse: "no such entry" is an empty answer at exit
        # 0, so a FAILED probe can never pass for "HEAD has no map".
        listed = subprocess.run([git, "ls-tree", "HEAD", "--", ".crew/verify.json"],
                                capture_output=True, check=False, timeout=_left(deadline),
                                stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CouldNotTell(f"the deployment map could not be read and compared with HEAD: {exc}") \
            from exc
    if listed.returncode != 0:
        raise CouldNotTell("git could not list HEAD's .crew/verify.json, so the map cannot be "
                           "held to its committed copy")
    entry = listed.stdout.decode("utf-8", errors="replace").split()
    if not entry:
        # No map at HEAD at all: an ignored, never-committed map, which the
        # gate itself treats as policy (git status cannot see it, so it is not
        # "dirty"). There is no committed copy to hold the bytes to.
        return raw.decode("utf-8-sig")
    mine = hashed.stdout.strip().decode("ascii", errors="replace")
    committed = entry[2] if len(entry) >= 3 else ""
    if hashed.returncode != 0 or not mine or mine != committed:
        raise CouldNotTell(".crew/verify.json as read now is not the map committed at HEAD, so "
                           "its requireReview cannot be trusted; commit or revert it")
    return raw.decode("utf-8-sig")


def _sha_map_blob(tree, sha, deadline):
    """The blob id of `.crew/verify.json` in commit `sha` of `tree`, or None
    when that commit carries no map. Could-not-tell raises."""
    try:
        found = subprocess.run(
            [crew_common.require_tool("git"), "--no-replace-objects", "-C", tree, "ls-tree",
             "--full-tree", sha, "--", ".crew/verify.json"],
            capture_output=True, check=False, timeout=_left(deadline), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CouldNotTell(f"the deployed sha's .crew/verify.json could not be listed: {exc}") \
            from exc
    if found.returncode != 0:
        raise CouldNotTell(f"git could not list .crew/verify.json in the deployed sha {sha} of "
                           f"{tree}, so which map is policy cannot be told")
    entry = found.stdout.decode("utf-8", errors="replace").split()
    if not entry:
        return None
    if len(entry) < 4 or entry[1] != "blob" or not _FULL_SHA.fullmatch(entry[2]):
        raise CouldNotTell(f".crew/verify.json in the deployed sha {sha} is not a file "
                           f"({' '.join(entry[:2])}), so it cannot be read as the map")
    return entry[2]


def policy_map_text(tree, sha, deadline):
    """(text, source) of the map that is policy for deploying `sha` from
    `tree` (module docstring, WHICH MAP). `source` is "sha" or "project"."""
    blob = _sha_map_blob(tree, sha, deadline)
    if blob is None:
        return project_map_text(deadline), "project"
    try:
        # Bounded by what is left of the gate's deadline, like every probe.
        shown = subprocess.run([crew_common.require_tool("git"), "--no-replace-objects", "-C",
                                tree, "cat-file", "blob", blob], capture_output=True, check=False,
                               stdin=subprocess.DEVNULL, timeout=_left(deadline))
    except (OSError, subprocess.SubprocessError) as exc:
        raise CouldNotTell(f"the deployed sha's .crew/verify.json could not be read: {exc}") \
            from exc
    if shown.returncode != 0:
        raise CouldNotTell(f"the deployed sha's .crew/verify.json could not be read (git "
                           f"cat-file exited {shown.returncode})")
    return shown.stdout.decode("utf-8-sig", errors="replace"), "sha"


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
        doc = json.loads(policy_map_text(tree, sha, deadline)[0], object_pairs_hook=no_case_twins)
    except ValueError as exc:
        print(f"_promote_review.py: the deployment map does not parse: {exc}", file=sys.stderr)
        return 3
    except CouldNotTell as exc:
        print(f"_promote_review.py: {exc}", file=sys.stderr)
        return 3
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
        # The budget is taken only now, so the map read above counts too.
        try:
            seconds = budget(deadline)
        except CouldNotTell as exc:
            print(f"_promote_review.py: {exc}", file=sys.stderr)
            return 2
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
