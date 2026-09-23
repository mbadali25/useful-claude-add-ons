"""The per-ticket review ledger: two rounds in total, reserved before launch.

WHERE. `<git-common-dir>/crew/review/<ticket>.json`. The common git directory
is shared by every worktree of a repository, so a second worktree of the same
repo reads and spends the same budget; a ledger under the worktree would give
each checkout its own two rounds.

THE BUDGET is `BUDGET`, a constant. No environment variable, CLI flag or
config key reads into it, and nothing here resets a ledger. (Deleting the file
by hand is outside that promise -- it is the operator's filesystem -- and the
README says so.) Five review rounds on one ticket is the measured failure this
exists for (`docs/review/03-codex-review.md`).

RESERVATION BEFORE LAUNCH. `reserve` appends a round with status `reserved`
and writes the ledger before any reviewer process exists. A reviewer that
crashes, hangs or is killed leaves that round `reserved` forever, and it
counts. A third reservation is refused and the state becomes `NEEDS_REPLAN`;
that refusal is written once, and every reservation attempt after it is
refused without writing anything.
That refusal, and an explicit `--reject --by <who>`, are the only ways into
NEEDS_REPLAN: a completed round 2 -- FINDINGS or INCOMPLETE -- leaves the
ticket REVIEWED, so the owner can still accept round 2's FINDINGS.

ATOMICITY. Every mutation holds `<ticket>.lock`, created with
O_CREAT|O_EXCL, for the read-modify-write, and replaces the ledger with
`os.replace` from a temp file in the same directory. Two concurrent
reservations for the last round: exactly one wins. A lock left by a process
that died inside the few-millisecond critical section is never broken
automatically -- breaking locks by age is how two writers both win -- so a
stuck lock fails closed with its path in the message.

AN UNREADABLE LEDGER is UNKNOWN, never empty: reservation refuses rather
than starting a fresh budget.

RECORDING A RESULT is allowed only for the most recent reserved round, only
once, and only with the provider and model that round was reserved for; once
the state is NEEDS_REPLAN no result changes it. Without the first rule an
older round's late CLEAN turned NEEDS_REPLAN back into ACCEPTED and minted a
receipt; without the third, a crashed Codex reservation could be completed by
an unreserved Claude run, erasing the provider that was actually launched.

RECEIPT. A CLEAN verdict writes `receipt` automatically; FINDINGS become a
receipt only through `--accept --by <who>`, which records who and when.
`--accept` takes only the most recent round, only once it completed with
FINDINGS, only once per round, and never once the state is NEEDS_REPLAN:
accepting an older completed round used to move NEEDS_REPLAN back to
ACCEPTED. Round 2's FINDINGS are acceptable -- the budget is exhausted only
when it is spent with nothing accepted, which is the refused third
reservation.
Either way the receipt carries the bundle sha256 the reviewer read, and
`--check-receipt` rebuilds the bundle from the receipt's base and exits
non-zero unless the hash still matches -- and unless the receipt is for the
latest recorded round, that round is CLEAN or owner-accepted, and the state
is not NEEDS_REPLAN, so an older round's receipt never outlives a later
verdict. `/crew:done` (T4) gates on it.

SUCCESSOR PLANS (T3). After NEEDS_REPLAN the only continuation is an
approved successor plan: `crew_ticket.py approve` on a NEEDS_REPLAN ticket
calls `continue_with_successor_plan`, which allows it only when the ticket's
approval receipt (`<git-common-dir>/crew/tickets/<id>/approval.json`, written
by `crew_ticket.py`, refused to Write/Edit by `scope_guard.py`) is current for
exactly that plan hash AND no earlier approval of the ticket carried the same
plan. It appends a `successors` row and opens a fresh budget of `BUDGET`
rounds counted from there; the rounds already spent stay in the ledger, the
old receipt is cleared, and nothing else resets the count.

Exit codes: 0 ok; 1 refused / receipt invalid / error; 2 usage.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time

import review_patch

BUDGET = 2

NEEDS_REPLAN = "NEEDS_REPLAN"
IN_REVIEW = "IN_REVIEW"
REVIEWED = "REVIEWED"
ACCEPTED = "ACCEPTED"
UNKNOWN = "UNKNOWN"

LOCK_WAIT_SECONDS = 10.0

_TICKET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_PLAN_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class LedgerError(RuntimeError):
    """A ledger operation that could not be carried out."""


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def check_ticket(ticket):
    if not isinstance(ticket, str) or not _TICKET_RE.match(ticket):
        raise LedgerError(f"ticket id {ticket!r} is not a plain id "
                          "(letters, digits, '.', '_', '-'; no path separators)")
    return ticket


def common_dir(root):
    """`git rev-parse --git-common-dir`, made absolute."""
    try:
        out = subprocess.run(
            ["git", "-C", root, "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, check=False, timeout=30,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LedgerError(f"git rev-parse --git-common-dir could not run: {exc}") from exc
    if out.returncode != 0:
        raise LedgerError(f"not a git repository: {out.stderr.strip()}")
    path = out.stdout.strip()
    if not os.path.isabs(path):
        path = os.path.join(os.path.abspath(root), path)
    return os.path.normpath(path)


def ledger_path(root, ticket):
    return os.path.join(common_dir(root), "crew", "review", check_ticket(ticket) + ".json")


def _load(path):
    """(data, state): state is 'absent', 'ok' or 'corrupt'."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}, "absent"
    except (OSError, ValueError):
        return {}, "corrupt"
    if not isinstance(data, dict) or not isinstance(data.get("rounds", []), list):
        return {}, "corrupt"
    return data, "ok"


def _save(path, data):
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


class _Lock:
    """O_CREAT|O_EXCL lock file held for one read-modify-write."""

    def __init__(self, path):
        self.path = path + ".lock"

    def __enter__(self):
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                if time.monotonic() > deadline:
                    raise LedgerError(
                        f"ledger lock {self.path} has been held for over "
                        f"{LOCK_WAIT_SECONDS:.0f}s. If no review is running, a process "
                        "died holding it -- remove that file by hand") from exc
                time.sleep(0.02)
                continue
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return self

    def __exit__(self, *exc):
        try:
            os.remove(self.path)
        except OSError:
            pass


def _mutate(root, ticket, change):
    """Run `change(data, state)` under the lock; it returns (data_or_None,
    result). A non-None data is written back atomically."""
    path = ledger_path(root, ticket)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _Lock(path):
        data, state = _load(path)
        new, result = change(data, state)
        if new is not None:
            _save(path, new)
    return result


def _spent(data):
    """Rounds reserved since the latest successor plan (or ever, without one)."""
    successors = data.get("successors") or []
    after = successors[-1].get("after_round", 0) if successors else 0
    return len(data.get("rounds", [])) - (after if isinstance(after, int) else 0)


def _fresh(ticket):
    return {"ticket": ticket, "budget": BUDGET, "state": None, "rounds": [],
            "refused": [], "receipt": None}


def reserve(root, ticket, provider, model=None):
    """Reserve the next round BEFORE launching a reviewer. Returns
    (True, round_number, message) or (False, None, message)."""

    def change(data, state):
        if state == "corrupt":
            return None, (False, None,
                          f"ledger {ledger_path(root, ticket)} is unreadable, so the rounds "
                          "already spent are UNKNOWN; refusing to start a fresh budget")
        if state == "absent":
            data = _fresh(ticket)
        rounds = data.setdefault("rounds", [])
        exhausted = (False, None,
                     f"review budget exhausted: {_spent(data)} of {BUDGET} rounds used. "
                     f"State is {NEEDS_REPLAN}; only an approved successor plan continues")
        if data.get("state") == NEEDS_REPLAN:
            return None, exhausted
        if _spent(data) >= BUDGET:
            data["state"] = NEEDS_REPLAN
            data.setdefault("refused", []).append({"at": _now(), "provider": provider})
            return data, exhausted
        number = len(rounds) + 1
        rounds.append({"round": number, "status": "reserved", "reserved_at": _now(),
                       "provider": provider, "model": model or None, "pid": os.getpid()})
        data["state"] = IN_REVIEW
        return data, (True, number, f"round {number} of {BUDGET} reserved")

    return _mutate(root, ticket, change)


def record(root, ticket, number, review):
    """Record a reserved round's result. `review` is the review.json dict.
    A CLEAN verdict writes the receipt."""

    def change(data, state):
        if state != "ok":
            raise LedgerError(f"ledger is {state}; round {number} was never reserved")
        if data.get("state") == NEEDS_REPLAN:
            raise LedgerError(f"{ticket} is {NEEDS_REPLAN}; no review result changes that "
                              "state, only an approved successor plan continues")
        rounds = data.get("rounds", [])
        rows = [r for r in rounds if r.get("round") == number]
        if not rows:
            raise LedgerError(f"round {number} was never reserved for {ticket}")
        row = rows[0]
        if row is not rounds[-1]:
            raise LedgerError(f"round {number} is not the most recent reservation (round "
                              f"{rounds[-1].get('round')} is); an older round's result "
                              "cannot be recorded")
        if row.get("status") != "reserved":
            raise LedgerError(f"round {number} already has a result ({row.get('verdict')})")
        if len(rounds) - _spent(data) >= number:
            raise LedgerError(f"round {number} was reserved under the plan a successor "
                              "replaced; its result cannot be recorded")
        reserved_for = (row.get("provider"), row.get("model") or None)
        recording = (review.get("provider"), review.get("model") or None)
        if recording != reserved_for:
            raise LedgerError(f"round {number} was reserved for {reserved_for[0]}/"
                              f"{reserved_for[1] or 'default'}, not {recording[0]}/"
                              f"{recording[1] or 'default'}; a round is recorded only by "
                              "the reviewer it was reserved for")
        row.update({
            "status": "completed", "completed_at": _now(),
            "verdict": review["verdict"], "counts": review.get("counts"),
            "bundle_sha256": review.get("bundle_sha256"), "base": review.get("base"),
            "head": review.get("head"), "model_family": review.get("model_family"),
        })
        if review["verdict"] == "CLEAN":
            data["receipt"] = {
                "kind": "clean", "round": number, "bundle_sha256": review["bundle_sha256"],
                "base": review["base"], "verdict": "CLEAN", "accepted_by": None,
                "accepted_at": row["completed_at"],
            }
            data["state"] = ACCEPTED
        else:
            data["state"] = REVIEWED
        return data, data["state"]

    return _mutate(root, ticket, change)


def accept(root, ticket, by):
    """The owner accepts the latest round's FINDINGS. Refuses anything else,
    and refuses when the tree no longer matches the bundle that round read."""
    if not isinstance(by, str) or not by.strip():
        raise LedgerError("--accept needs --by <who is accepting>")

    def change(data, state):
        if state != "ok":
            raise LedgerError(f"ledger is {state}; there is no review to accept")
        if data.get("state") == NEEDS_REPLAN:
            raise LedgerError(f"{ticket} is {NEEDS_REPLAN}; no acceptance changes that "
                              "state, only an approved successor plan continues")
        rounds = data.get("rounds", [])
        if not rounds:
            raise LedgerError("no review round to accept")
        row = rounds[-1]
        if row.get("status") != "completed":
            raise LedgerError(f"round {row.get('round')}, the most recent, has no result "
                              "yet; only the most recent round can be accepted, once it "
                              "has completed")
        if len(rounds) - _spent(data) >= row.get("round", 0):
            raise LedgerError(f"round {row.get('round')} reviewed the plan a successor "
                              "replaced; only a round under the current plan can be accepted")
        if row.get("verdict") != "FINDINGS":
            raise LedgerError(f"round {row['round']} is {row.get('verdict')}; only FINDINGS "
                              "can be owner-accepted (CLEAN writes its own receipt, and "
                              "INCOMPLETE was not read)")
        receipt = data.get("receipt") or {}
        if receipt.get("round") == row["round"]:
            raise LedgerError(f"round {row['round']} was already accepted by "
                              f"{receipt.get('accepted_by')} at {receipt.get('accepted_at')}")
        current = _current_hash(root, row.get("base"))
        if current != row.get("bundle_sha256"):
            raise LedgerError("the tree has changed since that review, so accepting it would "
                              "accept code nobody reviewed")
        data["receipt"] = {
            "kind": "owner-accepted", "round": row["round"],
            "bundle_sha256": row["bundle_sha256"], "base": row["base"],
            "verdict": "FINDINGS", "accepted_by": by.strip(), "accepted_at": _now(),
        }
        data["state"] = ACCEPTED
        return data, data["receipt"]

    return _mutate(root, ticket, change)


def reject(root, ticket, by):
    """The owner sends the ticket to NEEDS_REPLAN without spending a third
    reservation. Refuses on a ticket already ACCEPTED or NEEDS_REPLAN, and
    changes nothing when it refuses."""
    if not isinstance(by, str) or not by.strip():
        raise LedgerError("--reject needs --by <who is rejecting>")

    def change(data, state):
        if state != "ok":
            raise LedgerError(f"ledger is {state}; there is no review to reject")
        if data.get("state") in (NEEDS_REPLAN, ACCEPTED):
            raise LedgerError(f"{ticket} is {data.get('state')}; --reject does not change "
                              "that state")
        data["rejected"] = {"by": by.strip(), "at": _now(),
                            "round": (data.get("rounds") or [{}])[-1].get("round")}
        data["state"] = NEEDS_REPLAN
        return data, data["rejected"]

    return _mutate(root, ticket, change)


def _current_hash(root, base):
    if not base:
        raise LedgerError("the recorded round has no base commit")
    try:
        manifest, _, _ = review_patch.compute(root, base)
    except RuntimeError as exc:
        raise LedgerError(f"could not rebuild the bundle: {exc}") from exc
    return manifest["bundle_sha256"]


def check_receipt(root, ticket):
    """(ok, message). ok only when an accepted receipt exists AND the bundle
    rebuilt now from its base has the same sha256."""
    data, state = _load(ledger_path(root, ticket))
    if state != "ok":
        return False, f"no accepted review receipt for {ticket} (ledger {state})"
    receipt = data.get("receipt")
    if not isinstance(receipt, dict) or not receipt.get("bundle_sha256"):
        return False, f"no accepted review receipt for {ticket}"
    if data.get("state") == NEEDS_REPLAN:
        return False, f"{ticket} is {NEEDS_REPLAN}; no receipt stands"
    latest = (data.get("rounds") or [{}])[-1]
    if not isinstance(latest, dict) or latest.get("round") != receipt.get("round"):
        return False, (f"receipt is for round {receipt.get('round')}, not the latest recorded "
                       "round; only the latest round's verdict counts")
    accepted = (latest.get("verdict") == "CLEAN"
                or (latest.get("verdict") == "FINDINGS"
                    and receipt.get("kind") == "owner-accepted"))
    if latest.get("status") != "completed" or not accepted:
        return False, (f"round {latest.get('round')} is {latest.get('verdict') or 'not completed'}"
                       "; a receipt stands only on a CLEAN or owner-accepted round")
    try:
        current = _current_hash(root, receipt.get("base"))
    except LedgerError as exc:
        return False, f"receipt could not be checked: {exc}"
    if current != receipt["bundle_sha256"]:
        return False, (f"receipt is stale: round {receipt.get('round')} accepted bundle "
                       f"{receipt['bundle_sha256'][:12]}, the tree now builds "
                       f"{(current or 'nothing')[:12]}; the change was edited after review")
    return True, (f"receipt current: round {receipt.get('round')} {receipt.get('kind')}, "
                  f"bundle {(current or '')[:12]}")


def _plan_approval_receipt(root, ticket, plan_hash):
    """(receipt, None) when `ticket`'s approval receipt is current AND is for
    `plan_hash` AND no earlier approval carried that plan, else (None, why)."""
    import crew_ticket  # pylint: disable=import-outside-toplevel
    # `accepted`, not `status`: the same rule the scope guard acts on, so a
    # cli receipt continues a NEEDS_REPLAN ledger only where
    # `scope.allowCliApproval` is true.
    result = crew_ticket.accepted(root, ticket)
    receipt = result.get("receipt") or {}
    if result["status"] != "approved":
        return None, f"no current approval for {ticket}: {result['why']}"
    if receipt.get("plan_sha256") != plan_hash:
        return None, (f"the approved plan is {str(receipt.get('plan_sha256'))[:12]}, "
                      f"not {plan_hash[:12]}")
    if plan_hash in crew_ticket.earlier_plan_hashes(root, ticket):
        return None, (f"plan {plan_hash[:12]} was approved before; a successor plan must "
                      "be a different plan")
    return receipt, None


def continue_with_successor_plan(root, ticket, plan_hash):
    """(allowed, reason). The only way past NEEDS_REPLAN: an approved
    successor plan (see the module docstring). Changes nothing on refusal."""
    check_ticket(ticket)
    if not isinstance(plan_hash, str) or not _PLAN_HASH_RE.match(plan_hash):
        return False, "refused: the plan hash must be a 64-character lowercase sha256"
    receipt, why = _plan_approval_receipt(root, ticket, plan_hash)
    if receipt is None:
        return False, f"refused: {why}; {NEEDS_REPLAN} stands"

    def change(data, state):
        # Re-checked UNDER the ledger lock: the check above is a cheap early
        # refusal, and the approval can go stale (or be replaced) between it
        # and the lock. The receipt acted on is the one read here.
        receipt, why = _plan_approval_receipt(root, ticket, plan_hash)
        if receipt is None:
            return None, (False, f"refused: {why}; {NEEDS_REPLAN} stands")
        if state != "ok" or data.get("state") != NEEDS_REPLAN:
            return None, (False, f"refused: {ticket} is "
                                 f"{data.get('state') if state == 'ok' else state}, not "
                                 f"{NEEDS_REPLAN}; there is nothing to continue")
        if plan_hash in {s.get("plan_sha256") for s in data.get("successors") or []}:
            return None, (False, f"refused: plan {plan_hash[:12]} already continued "
                                 f"{ticket} once")
        data.setdefault("successors", []).append({
            "plan_sha256": plan_hash, "approved_at": receipt.get("approved_at"),
            "approved_by": receipt.get("approved_by"), "at": _now(),
            "after_round": len(data.get("rounds", []))})
        data["receipt"] = None
        data["state"] = IN_REVIEW
        return data, (True, f"successor plan {plan_hash[:12]} approved by "
                            f"{receipt.get('approved_by')}; {BUDGET} review rounds available")

    return _mutate(root, ticket, change)


def status(root, ticket):
    path = ledger_path(root, ticket)
    data, state = _load(path)
    if state == "corrupt":
        return {"ticket": ticket, "path": path, "state": UNKNOWN}
    rounds = data.get("rounds", [])
    return {"ticket": ticket, "path": path, "state": data.get("state") or "EMPTY",
            "rounds_used": len(rounds), "budget": BUDGET,
            "rounds_left": max(0, BUDGET - _spent(data)), "rounds": rounds,
            "successors": data.get("successors") or [],
            "receipt": data.get("receipt")}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--status", action="store_true")
    action.add_argument("--reserve", action="store_true",
                        help="reserve the next round (use review_run.py; this is for the "
                             "Claude fallback, which is not a process it can launch)")
    action.add_argument("--accept", action="store_true")
    action.add_argument("--reject", action="store_true",
                        help="send the ticket to NEEDS_REPLAN now (needs --by)")
    action.add_argument("--check-receipt", action="store_true")
    action.add_argument("--successor-plan", metavar="PLAN_SHA256")
    parser.add_argument("--provider", default="claude")
    parser.add_argument("--model")
    parser.add_argument("--by", help="who accepts or rejects, with --accept / --reject")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)

    try:
        check_ticket(args.ticket)
        if args.status:
            print(json.dumps(status(root, args.ticket), indent=2, sort_keys=True))
            return 0
        if args.reserve:
            ok, number, message = reserve(root, args.ticket, args.provider, args.model)
            print(f"ROUND={number}" if ok else "ROUND=")
            sys.stderr.write(f"review-ledger: {message}\n")
            return 0 if ok else 1
        if args.accept:
            receipt = accept(root, args.ticket, args.by)
            print(f"review-ledger: round {receipt['round']} FINDINGS accepted by "
                  f"{receipt['accepted_by']} at {receipt['accepted_at']}")
            return 0
        if args.reject:
            rejected = reject(root, args.ticket, args.by)
            print(f"review-ledger: {args.ticket} is {NEEDS_REPLAN}, rejected by "
                  f"{rejected['by']} at {rejected['at']}")
            return 0
        if args.check_receipt:
            ok, message = check_receipt(root, args.ticket)
            print(f"review-ledger: {message}")
            return 0 if ok else 1
        ok, message = continue_with_successor_plan(root, args.ticket, args.successor_plan)
        print(f"review-ledger: {message}")
        return 0 if ok else 1
    except LedgerError as exc:
        sys.stderr.write(f"review-ledger: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
