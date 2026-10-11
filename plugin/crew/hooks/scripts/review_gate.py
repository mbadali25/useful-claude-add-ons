"""Has the verify gate passed on THIS tree? Asked before a review round is spent.

WHY. A review round is the scarce thing here: two per ticket, reserved before
launch, never reset (`review_ledger.BUDGET`). Spending one on a tree whose tests
or lint are red buys a reviewer's opinion on code the gate would have refused
for free, and it is a round the ticket does not get back. So `review_run.py`
asks this module first, and a tree the gate has not passed is refused before
the ledger is touched.

WHAT COUNTS AS PASSED. Not verify-gate's exit status: it exits 0 when it is
stood down, when it backs off a lock held by the other shell flavour, and when
nothing it checks has changed, as well as on a pass. The evidence is what a
full clean pass LEAVES BEHIND, and it is written in exactly one place
(`verify-gate.sh`'s final `record_verified` / `record_verified_fingerprint`
pair, gated on nothing deferred, nothing skipped and the record synced):

  * `.crew/.verify-verified-at` names HEAD, and
  * either nothing material differs from HEAD (its own marker files never
    count; since L-0710 a turn where zero rules ran writes no marker, so a
    marker at HEAD always means rules ran and passed on it), or
    `.crew/.verify-gate.fingerprint` equals the digest of the tree AS IT IS NOW.

The digest is `verify_fingerprint.fingerprint` over the gate's own Stop-mode
changed set. With the marker at HEAD the gate's BASE is HEAD, so that set is
`git diff --name-only HEAD` plus untracked files -- the same two git calls,
the same flags. It is not re-derived in a second way: `test_review_gate.py`
runs the real gate on fixture trees and asserts this module agrees with the
fingerprint the gate wrote, so the two cannot drift apart unnoticed.

FOUR ANSWERS, and "could not tell" is its own one:

  VERIFIED    the evidence above holds
  UNVERIFIED  it does not, and the reason names which half failed
  UNKNOWN     git, the marker or the digest could not be read -- never read
              as VERIFIED, and refused like UNVERIFIED
  NO_GATE     no `.crew/verify.json`, or `"verifyGate": false` in the
              resolved `.crew/config.json` (the same test the gate's own
              first lines make, on the same file: in a linked worktree with
              no config of its own, the main checkout's, L-0681) -- there is
              nothing to be green against, so the review proceeds and SAYS so
"""
import json
import os
import re
import subprocess

import crew_common
import verify_fingerprint

VERIFIED, UNVERIFIED, UNKNOWN, NO_GATE = "VERIFIED", "UNVERIFIED", "UNKNOWN", "NO_GATE"
MARKER = os.path.join(".crew", ".verify-verified-at")
FINGERPRINT = os.path.join(".crew", ".verify-gate.fingerprint")
VERIFY_MAP = os.path.join(".crew", "verify.json")
# verify-gate.sh:73, byte for byte in meaning: a grep over the raw file, not a
# JSON read, so a file the gate stands down on is one this module stands down on.
_STOOD_DOWN_RE = re.compile(r'"verifyGate"[ \t\r\n\f\v]*:[ \t\r\n\f\v]*false')


class _Unreadable(Exception):
    pass


def _git(root, *args):
    try:
        out = subprocess.run([crew_common.require_tool("git"), "-c", "core.quotePath=false", *args], cwd=root,
                             capture_output=True, text=True, check=False, timeout=60,
                             stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise _Unreadable(f"git {args[0]} could not run: {exc}") from exc
    if out.returncode != 0:
        raise _Unreadable(f"git {' '.join(args)} exited {out.returncode}: "
                          f"{(out.stderr or '').strip()}")
    return out.stdout


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise _Unreadable(f"{path} could not be read: {exc}") from exc


def changed_now(root):
    """The gate's Stop-mode changed set when its BASE is HEAD, one path per
    entry, blank lines dropped the way `verify_fingerprint.main` drops them."""
    text = _git(root, "diff", "--name-only", "HEAD") + "\n" + \
        _git(root, "ls-files", "--others", "--exclude-standard")
    return sorted(set(line for line in text.split("\n") if line.strip()))


RECORD = os.path.join(".crew", ".verify-gate.record.json")
_OUTSTANDING_SHOWN = 3


def _outstanding(root):
    """What the gate's per-rule record still lists as not verified, as a
    suffix for an UNVERIFIED reason -- so a gate that can never pass here
    (a tool that is not installed skips with 77, and a skip never advances the
    marker) says so instead of refusing every review without a cause."""
    try:
        rules = json.loads(_read(os.path.join(root, RECORD)) or "{}").get("rules")
    except (_Unreadable, ValueError, AttributeError):
        return "; the gate's per-rule record could not be read"
    if not isinstance(rules, dict) or not rules:
        return ""
    rows = [f"{info.get('label', '?')} ({info.get('reason', '')})"
            for info in rules.values() if isinstance(info, dict)]
    more = f" (+{len(rows) - _OUTSTANDING_SHOWN} more)" if len(rows) > _OUTSTANDING_SHOWN else ""
    return "; the gate's record lists as not verified: " + "; ".join(rows[:_OUTSTANDING_SHOWN]) + more


def gate_state(root):
    """(state, reason). See the module docstring for what each state means."""
    root = os.path.abspath(root)
    state, reason = _gate_state(root)
    if state == UNVERIFIED:
        reason += _outstanding(root)
    return state, reason


def _gate_state(root):
    try:
        if _read(os.path.join(root, VERIFY_MAP)) is None:
            return NO_GATE, ("no .crew/verify.json - there is no verify gate here to be "
                             "green against, so nothing was checked before this review")
        # L-0681: the resolved file, as verify-gate.sh's stand-down reads it.
        config = _read(crew_common.repo_config_file(root, "config.json"))
        if config is not None and _STOOD_DOWN_RE.search(config):
            return NO_GATE, ('"verifyGate": false in .crew/config.json - the gate is stood '
                             "down, so nothing was checked before this review")
        head = _git(root, "rev-parse", "HEAD").strip()
        marker = (_read(os.path.join(root, MARKER)) or "").strip()
        if not marker:
            return UNVERIFIED, ("the verify gate has never recorded a clean pass in this "
                                "checkout (no .crew/.verify-verified-at)")
        if marker != head:
            return UNVERIFIED, (f"the last clean verify pass was at {marker[:12]}, but HEAD "
                                f"is {head[:12]} - the commits since have not been through "
                                "the gate")
        changed = changed_now(root)
        # The gate's own markers are not material: the digest excludes them by
        # name (verify_fingerprint._material), and in a repo that does not
        # ignore `.crew/` the marker this pass just wrote is itself untracked.
        if not verify_fingerprint._material(changed):  # pylint: disable=protected-access
            return VERIFIED, (f"clean pass at HEAD {head[:12]}, and nothing that can move "
                              "the verdict differs from it")
        if verify_fingerprint._corrupt_cache(root):  # pylint: disable=protected-access
            return UNKNOWN, ("the fingerprint cache is corrupt, so the tree's digest "
                             "cannot be computed the way the gate computes it")
        recorded = (_read(os.path.join(root, FINGERPRINT)) or "").strip()
        if not recorded:
            return UNVERIFIED, (f"{len(changed)} path(s) differ from HEAD and no clean pass "
                                "recorded a fingerprint for them (.crew/.verify-gate."
                                "fingerprint is absent)")
        current = verify_fingerprint.fingerprint(root, changed)
    except _Unreadable as exc:
        return UNKNOWN, str(exc)
    except Exception as exc:  # pylint: disable=broad-except
        return UNKNOWN, f"the gate state could not be computed: {type(exc).__name__}: {exc}"
    if current != recorded:
        return UNVERIFIED, (f"{len(changed)} path(s) differ from HEAD and the tree has changed "
                            f"since the last clean pass (fingerprint {recorded} recorded, "
                            f"{current} now)")
    return VERIFIED, (f"clean pass at HEAD {head[:12]} covering the {len(changed)} changed "
                      f"path(s), fingerprint {current}")


def accepted_state(root, fetch=None):
    """(state, reason) a CONSUMER acts on: `gate_state`, upgraded to VERIFIED
    when the local evidence does not hold but a CI receipt
    (`ci_receipt.check`) proves the gate passed on exactly this committed tree.

    WHY. A local `verify-gate.sh --all` costs 17-20 minutes; the self-hosted
    pool runs the same gate on every pushed lane branch and leaves a receipt
    bound to HEAD, its tree, the verify map and the gate implementation.
    Re-running the gate locally to prove what that receipt already proves is
    the single most expensive duplicate in the review path.

    ONLY EVER AN UPGRADE. The receipt is consulted only when the local answer
    is UNVERIFIED or UNKNOWN, and anything but a receipt VERIFIED leaves the
    local answer standing with the receipt's own reason appended -- an
    unreadable receipt (UNKNOWN: gh, the network, the artifact) never moves a
    verdict either way. NO_GATE is never consulted about. `gate_state` itself
    stays local-only: `ci_receipt build` asks it on the runner, and a receipt
    that consulted receipts could vouch for itself.

    The checks that need no network come first in `ci_receipt.check` (map,
    local edits, origin/main, a branch that changes the gate, a GitHub
    origin), so a dirty tree or a fixture repo is answered without a call."""
    state, reason = gate_state(root)
    if state not in (UNVERIFIED, UNKNOWN):
        return state, reason
    import ci_receipt  # pylint: disable=import-outside-toplevel  # it imports this module
    r_state, r_reason, _ = ci_receipt.check(root, fetch=fetch)
    if r_state == VERIFIED:
        return VERIFIED, f"{r_reason} (the local gate evidence said {state}: {reason})"
    return state, f"{reason}; CI receipt {r_state}: {r_reason}"
