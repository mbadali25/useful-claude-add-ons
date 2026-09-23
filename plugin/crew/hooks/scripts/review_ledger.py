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
counts. A third reservation is refused and the state becomes `NEEDS_REPLAN`.

ATOMICITY. Every mutation holds `<ticket>.lock`, created with
O_CREAT|O_EXCL, for the read-modify-write, and replaces the ledger with
`os.replace` from a temp file in the same directory. Two concurrent
reservations for the last round: exactly one wins. A lock left by a process
that died inside the few-millisecond critical section is never broken
automatically -- breaking locks by age is how two writers both win -- so a
stuck lock fails closed with its path in the message.

AN UNREADABLE LEDGER is UNKNOWN, never empty: reservation refuses rather
than starting a fresh budget.

RECEIPT. A CLEAN verdict writes `receipt` automatically; FINDINGS become a
receipt only through `--accept --by <who>`, which records who and when.
Either way the receipt carries the bundle sha256 the reviewer read, and
`--check-receipt` rebuilds the bundle from the receipt's base and exits
non-zero unless the hash still matches. `/crew:done` (T4) gates on it.

SUCCESSOR PLANS (the T3 seam). After NEEDS_REPLAN the only continuation is an
approved successor plan. Plan approval belongs to T3, which does not exist
yet, so `continue_with_successor_plan` always refuses in 0.20.16 and says why.
T3 implements `_plan_approval_receipt` and the continuation behind it.

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
        if len(rounds) >= BUDGET or data.get("state") == NEEDS_REPLAN:
            data["state"] = NEEDS_REPLAN
            data.setdefault("refused", []).append({"at": _now(), "provider": provider})
            return data, (False, None,
                          f"review budget exhausted: {len(rounds)} of {BUDGET} rounds used. "
                          f"State is {NEEDS_REPLAN}; only an approved successor plan continues")
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
        rows = [r for r in data.get("rounds", []) if r.get("round") == number]
        if not rows:
            raise LedgerError(f"round {number} was never reserved for {ticket}")
        row = rows[0]
        if row.get("status") != "reserved":
            raise LedgerError(f"round {number} already has a result ({row.get('verdict')})")
        row.update({
            "status": "completed", "completed_at": _now(),
            "verdict": review["verdict"], "counts": review.get("counts"),
            "bundle_sha256": review.get("bundle_sha256"), "base": review.get("base"),
            "head": review.get("head"), "provider": review.get("provider"),
            "model": review.get("model"), "model_family": review.get("model_family"),
        })
        if review["verdict"] == "CLEAN":
            data["receipt"] = {
                "kind": "clean", "round": number, "bundle_sha256": review["bundle_sha256"],
                "base": review["base"], "verdict": "CLEAN", "accepted_by": None,
                "accepted_at": row["completed_at"],
            }
            data["state"] = ACCEPTED
        elif number >= BUDGET:
            data["state"] = NEEDS_REPLAN
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
        done = [r for r in data.get("rounds", []) if r.get("status") == "completed"]
        if not done:
            raise LedgerError("no completed review round to accept")
        row = done[-1]
        if row.get("verdict") != "FINDINGS":
            raise LedgerError(f"round {row['round']} is {row.get('verdict')}; only FINDINGS "
                              "can be owner-accepted (CLEAN writes its own receipt, and "
                              "INCOMPLETE was not read)")
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


def _plan_approval_receipt(root, ticket, plan_hash):  # pylint: disable=unused-argument
    """T3 SEAM. Returns T3's approval receipt for `plan_hash` as a successor
    plan of `ticket`, or None. Plan approval does not exist in 0.20.16, so
    there is never a receipt."""
    return None


def continue_with_successor_plan(root, ticket, plan_hash):
    """(allowed, reason). The only way past NEEDS_REPLAN: an approved
    successor plan. Always refuses in 0.20.16 -- T3 owns plan approval."""
    check_ticket(ticket)
    if not isinstance(plan_hash, str) or not _PLAN_HASH_RE.match(plan_hash):
        return False, "refused: the plan hash must be a 64-character lowercase sha256"
    if _plan_approval_receipt(root, ticket, plan_hash) is None:
        return False, ("refused: no approval receipt exists for successor plan "
                       f"{plan_hash[:12]}. Plan approval is built in T3 and does not exist "
                       f"in this release, so {NEEDS_REPLAN} is terminal: replan as a new "
                       "ticket")
    return False, "refused: successor continuation is not implemented until T3"


def status(root, ticket):
    path = ledger_path(root, ticket)
    data, state = _load(path)
    if state == "corrupt":
        return {"ticket": ticket, "path": path, "state": UNKNOWN}
    rounds = data.get("rounds", [])
    return {"ticket": ticket, "path": path, "state": data.get("state") or "EMPTY",
            "rounds_used": len(rounds), "budget": BUDGET,
            "rounds_left": max(0, BUDGET - len(rounds)), "rounds": rounds,
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
    action.add_argument("--check-receipt", action="store_true")
    action.add_argument("--successor-plan", metavar="PLAN_SHA256")
    parser.add_argument("--provider", default="claude")
    parser.add_argument("--model")
    parser.add_argument("--by", help="who accepts, with --accept")
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
