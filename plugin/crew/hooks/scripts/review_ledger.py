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

REFUNDS (T-0087). A round the TOOL lost -- recorded INCOMPLETE with
`failure_class: "tool"` (`review_verdict.failure_class`: the answer never
arrived intact) -- is refunded automatically: its row says `refunded: true`
and it does not count against `BUDGET`. At most `REFUND_LIMIT` rounds per plan
are refunded; the next one is recorded `refunded: false` with
`refund_refused` saying why, and counts. Never refunded: a `reviewer` or
`tree` INCOMPLETE, a FINDINGS or CLEAN round, a round with no recorded result
(still `reserved`, above), and rows written before this rule (no
`failure_class`). `_spent` keeps meaning "rows reserved since the successor
boundary" -- the boundary checks in `record` and `accept` read it -- and
`_charged` (spent minus refunded) is what the budget uses. Nothing else resets
the count.

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
AUTO-ACCEPT (L-0510, owner policy 2026-09-30). `--auto-accept --follow-up <id>`
takes no `--by`: it writes a receipt of kind `auto-accepted` whose
`accepted_by` is fixed to `AUTO_BY`, carrying the round's finding lines
verbatim (`findings`), the follow-up ticket id and the model family. It runs
every check `--accept` runs, then the guard (`auto_accept_refusal`): the
round was reviewed by another model family than the author's -- its
`provider` is codex or kimi (`AUTO_PROVIDERS`) and its `model_family` a
non-empty string that is not `claude` (owner decision 2026-10-01 #3; a
Claude-fallback round, a missing provider or family, and any other provider
are refused); the round's verdict is exactly FINDINGS; its counts are a dict whose BLOCK, FIX
and NIT are ints (never a bool) and not negative; BLOCK is 0; `findings` is a
list of strings, none a `BLOCK|` line, each a `FIX|` or `NIT|` line, as many
of each as its own count (never only the total) and at least one;
none carrying an embedded line break; `ignored_lines` (L-0576's count of the
stray lines a verdict was recovered despite) is 0 on the row, and this
round's `.work/tickets/<id>/review.json` counts 0 (owner decision
2026-10-01 #6: a recovered round is the owner's; a missing, mistyped or
unreadable count is could-not-tell, never 0, and this branch does not
write the field); `webtest_open` is 0 or `WEBTEST_NA`; and the round is final -- `_charged`
has reached `BUDGET`, so the next reservation would be refused. Every case
the ledger cannot tell is a refusal, never a 0: an INCOMPLETE or CLEAN
verdict, a missing or mistyped count, a missing `findings` or `webtest_open`
(which is every row recorded before this rule), an unreadable ledger. A
refusal raises and changes nothing. `--accept` refuses a `--by` beginning
`auto:` (any case), so that string can come only from the guarded verb.
`receipt_stands` is the one predicate for whether a FINDINGS receipt stands
-- `owner-accepted`, or `auto-accepted` with its row still passing the guard
and its lines, provider and model family equal to the row's -- and both `check_receipt` and
`crew_autopilot` call it. `--check-follow-up` confirms the follow-up's
`.work/tickets/<id>/direction.md` holds every receipt line verbatim as a
whole line, as many times as the receipt carries it; a direction.md that is
not UTF-8, or a receipt whose kind is none of clean, owner-accepted and
auto-accepted, is could-not-tell, never "not applicable". A CLEAN round
stands only under a receipt of kind `clean`.
The ledger never files the follow-up; `/crew:review` step 3 does.

Either way the receipt carries the bundle sha256 the reviewer read, and
`--check-receipt` rebuilds the bundle from the receipt's base and exits
non-zero unless the hash still matches -- and unless the receipt is for the
latest recorded round, that round is CLEAN or its receipt stands
(`receipt_stands`), and the state
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
import collections
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import time

import merged_main
import review_patch

BUDGET = 2
# A constant like BUDGET: bounds a refund loop at four launched rounds per
# two-round budget. No flag, env var or config key reads into it.
REFUND_LIMIT = 2

# L-0510: the auto-accept receipt. Constants, like BUDGET: no flag, env var or
# config key turns the policy on or off or changes the string.
AUTO_KIND = "auto-accepted"
AUTO_BY = "auto: 0 BLOCK, owner policy 2026-09-30"
AUTO_PREFIX = "auto:"
# `webtest_open` when the healer-skip check did not apply to the round. None
# means it applied and could not be read: could not tell, never 0.
WEBTEST_NA = "not-applicable"
# Owner decision 2026-10-01 #3: only a reviewer from another model family than
# the author's auto-accepts. The author is `claude` (crew's developer runs
# in-session); the providers whose family is not claude's by construction are
# codex and kimi. Copilot hosts several families, so it is an unknown provider
# here, never guessed. Constants: no config is read for either.
AUTHOR_FAMILY = "claude"
AUTO_PROVIDERS = ("codex", "kimi")

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
    # `_spent` and `_boundary` read the latest successor row: a `successors`
    # that is not a list of objects is unreadable, never a crash (T-0087). Any
    # wrong type on that path -- `{}`, `0`, `""`, `false` or `null` for the
    # list, an `after_round` that is missing, not an integer, a boolean, or
    # outside the rounds it splits -- is unreadable too, never "no successor"
    # or "boundary 0" (review round 5).
    successors = data.get("successors", [])
    if not isinstance(successors, list) or not all(isinstance(s, dict) for s in successors):
        return {}, "corrupt"
    if successors:
        after = successors[-1].get("after_round")
        if (not isinstance(after, int) or isinstance(after, bool)
                or not 0 <= after <= len(data.get("rounds", []))):
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


def _boundary(data):
    """Index of the first round under the current plan (the latest successor's
    `after_round`, or 0 without one)."""
    successors = data.get("successors") or []
    after = successors[-1].get("after_round", 0) if successors else 0
    return after if isinstance(after, int) else 0


def _refunded(data):
    """Rounds under the current plan that were refunded as tool failures."""
    return sum(1 for r in data.get("rounds", [])[_boundary(data):]
               if isinstance(r, dict) and r.get("refunded") is True)


def _charged(data):
    """Rounds under the current plan that count against BUDGET."""
    return _spent(data) - _refunded(data)


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
                     f"review budget exhausted: {_charged(data)} of {BUDGET} rounds used. "
                     f"State is {NEEDS_REPLAN}; only an approved successor plan continues")
        if data.get("state") == NEEDS_REPLAN:
            return None, exhausted
        if _charged(data) >= BUDGET:
            data["state"] = NEEDS_REPLAN
            data.setdefault("refused", []).append({"at": _now(), "provider": provider})
            return data, exhausted
        number = len(rounds) + 1
        rounds.append({"round": number, "status": "reserved", "reserved_at": _now(),
                       "provider": provider, "model": model or None, "pid": os.getpid()})
        data["state"] = IN_REVIEW
        return data, (True, number,
                      f"round {number} reserved ({_charged(data)} of {BUDGET} budget rounds "
                      f"used, {_refunded(data)} refunded)")

    return _mutate(root, ticket, change)


def _ignored_count(value):
    """review.json's `ignored_lines`: a non-negative int count (L-0576), kept
    as is. Anything else -- missing, null, a bool, a string, a negative -- is
    unknown and recorded as None, never 0: 0 means "none were ignored", and
    a reader (L-0510's auto-accept) must be able to tell that from "could not
    tell"."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


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
            "failure_class": review.get("failure_class"),
            # How many stray lines a FINDINGS round was recovered despite
            # (L-0576): an acceptance can see the round was not strictly read.
            "ignored_lines": _ignored_count(review.get("ignored_lines")),
        })
        # L-0510: stored only when the caller passed them, so a row from a
        # caller that never did reads as "could not tell" to the guard.
        for key in ("findings", "webtest_open"):
            if key in review:
                row[key] = review[key]
        if review["verdict"] == "INCOMPLETE" and review.get("failure_class") == "tool":
            row["refunded"] = _refunded(data) < REFUND_LIMIT
            if not row["refunded"]:
                row["refund_refused"] = f"refund limit {REFUND_LIMIT} per plan reached"
        else:
            row["refunded"] = False
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
    if by.strip().lower().startswith(AUTO_PREFIX):
        raise LedgerError(f"--by {by.strip()!r}: the {AUTO_PREFIX!r} prefix is reserved for "
                          "--auto-accept, which checks the round itself")

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
        current, _merged = _current_hash(root, row.get("base"))
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


def _is_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _family_problem(row):
    """None when the row's reviewer is from another model family than the
    author's, read from the provider and family recorded on the row; else why
    not. A missing or unknown value is could-not-tell, never a pass."""
    provider, family = row.get("provider"), row.get("model_family")
    if not isinstance(provider, str) or not provider:
        return (f"round {row.get('round')} records no provider ({provider!r}): could not "
                "tell the reviewer's family")
    if provider == AUTHOR_FAMILY:
        return (f"round {row.get('round')} was reviewed by {provider}, the same family as "
                "the author; a same-family round needs the owner's --accept")
    if provider not in AUTO_PROVIDERS:
        return (f"round {row.get('round')} was reviewed by {provider!r}, an unknown provider "
                f"for auto-accept (only {', '.join(AUTO_PROVIDERS)}): could not tell")
    if not isinstance(family, str) or not family.strip():
        return (f"round {row.get('round')} records no model family ({family!r}): could not "
                "tell the reviewer's family")
    if family.strip().lower() == AUTHOR_FAMILY:
        return (f"round {row.get('round')}'s reviewer family is {family}, the same family as "
                "the author; a same-family round needs the owner's --accept")
    return None


def _auto_row_problem(row):
    """None when a completed FINDINGS row's own evidence allows an auto
    receipt, else why not. Shared by `auto_accept_refusal` and
    `receipt_stands`, so the two cannot drift. Every unknown is a reason."""
    problem = _family_problem(row)
    if problem:
        return problem
    counts = row.get("counts")
    if not isinstance(counts, dict):
        return f"round {row.get('round')} has no readable counts ({counts!r}): could not tell"
    for sev in ("BLOCK", "FIX", "NIT"):
        if not _is_count(counts.get(sev)):
            return (f"round {row.get('round')}'s {sev} count is {counts.get(sev)!r}, not a "
                    "non-negative integer: could not tell")
    if counts["BLOCK"] != 0:
        return (f"round {row.get('round')} has {counts['BLOCK']} BLOCK finding(s); a BLOCK "
                "is never auto-accepted")
    findings = row.get("findings")
    if not isinstance(findings, list) or not all(isinstance(f, str) for f in findings):
        return (f"round {row.get('round')} carries no finding lines (recorded before L-0510, "
                "or by a caller that did not pass them): could not tell")
    # One finding is one line. A line break inside a string can hide a
    # BLOCK-form line behind a FIX prefix (review round 4 FIX 1).
    broken = [f for f in findings if "\n" in f or "\r" in f]
    if broken:
        return (f"round {row.get('round')} lists a finding with an embedded line break "
                f"({broken[0]!r}): could not tell")
    if any(f.strip().startswith("BLOCK|") for f in findings):
        return f"round {row.get('round')} lists a BLOCK line; a BLOCK is never auto-accepted"
    other = [f for f in findings if not f.strip().startswith(("FIX|", "NIT|"))]
    if other:
        return (f"round {row.get('round')} lists a line that is neither a FIX nor a NIT "
                f"({other[0]!r}): could not tell")
    # Per severity, never the total: one NIT line under counts FIX=1, NIT=0
    # agrees on the sum and disagrees on what was found.
    fixes = sum(1 for f in findings if f.strip().startswith("FIX|"))
    if not findings or (fixes, len(findings) - fixes) != (counts["FIX"], counts["NIT"]):
        return (f"round {row.get('round')}'s finding lines ({fixes} FIX + "
                f"{len(findings) - fixes} NIT) do not agree with its counts "
                f"({counts['FIX']} FIX + {counts['NIT']} NIT): could not tell")
    # Owner decision 2026-10-01 #6: L-0576's `ignored_lines` counts the stray
    # lines a FINDINGS verdict was recovered despite. Recovered is the owner's;
    # an absent or unread count is could-not-tell, never 0.
    ignored = row.get("ignored_lines")
    if not _is_count(ignored):
        return (f"round {row.get('round')} has no readable ignored_lines ({ignored!r}; "
                "recorded before L-0576, or unreadable): could not tell whether its "
                "verdict was recovered from stray lines")
    if ignored:
        return (f"round {row.get('round')}'s verdict was recovered from {ignored} stray "
                "line(s) (ignored_lines); a recovered round is the owner's to accept")
    if "webtest_open" not in row:
        return (f"round {row.get('round')} has no webtest state (recorded before L-0510): "
                "could not tell")
    webtest = row["webtest_open"]
    # Never a membership test: `False in (0, WEBTEST_NA)` is true.
    if not ((type(webtest) is int and webtest == 0) or webtest == WEBTEST_NA):  # pylint: disable=unidiomatic-typecheck
        return (f"round {row.get('round')}'s webtest state is {webtest!r}: open healer "
                "skips are never accepted, and an unread check is could-not-tell")
    return None


def auto_accept_refusal(data, ticket):
    """None when the latest round may be auto-accepted, else the reason. Pure:
    reads only `data` (a loaded ledger). The tree-hash check needs the
    repository and is `auto_accept`'s."""
    if not isinstance(data, dict):
        return "the ledger is unreadable: could not tell"
    if data.get("state") == NEEDS_REPLAN:
        return f"{ticket} is {NEEDS_REPLAN}; only an approved successor plan continues"
    rounds = data.get("rounds") or []
    if not rounds or not isinstance(rounds[-1], dict):
        return "no review round to accept"
    row = rounds[-1]
    if row.get("status") != "completed":
        return f"round {row.get('round')}, the most recent, has no result yet"
    if len(rounds) - _spent(data) >= row.get("round", 0):
        return (f"round {row.get('round')} reviewed the plan a successor replaced; only a "
                "round under the current plan can be accepted")
    if row.get("verdict") != "FINDINGS":
        failure = f" ({row.get('failure_class')})" if row.get("failure_class") else ""
        return (f"round {row.get('round')} is {row.get('verdict')}{failure}; only a FINDINGS "
                "round is auto-accepted")
    problem = _auto_row_problem(row)
    if problem:
        return problem
    if _charged(data) < BUDGET:
        return (f"not the final round: {_charged(data)} of {BUDGET} budget rounds used; fix "
                "and run the next round")
    receipt = data.get("receipt") or {}
    if receipt.get("round") == row.get("round"):
        return (f"round {row.get('round')} was already accepted by "
                f"{receipt.get('accepted_by')} at {receipt.get('accepted_at')}")
    return None


class _DuplicateKey(ValueError):
    """A JSON object names one key twice; json.load would keep the last."""


def _refuse_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise _DuplicateKey(f"duplicate key {key!r}")
        seen[key] = value
    return seen


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _review_json_path(root, ticket):
    return os.path.join(root, ".work", "tickets", ticket, "review.json")


def read_review_json(root, ticket):
    """(review, sha256, problem) for this ticket's review.json, read once as
    bytes: never through a link, never with a duplicate key at any depth
    (review round 6 BLOCK 2: json.load keeps the last of two), and hashed
    over exactly the bytes parsed so a receipt can bind them (BLOCK 1).
    `problem` is None or a could-not-tell reason; on a problem `review`
    and `sha256` are None."""
    path = _review_json_path(root, ticket)
    try:
        if os.path.islink(path):
            return None, None, (f"{path} is a link; not following it: could not tell "
                                "whether the verdict was recovered from stray lines")
        with open(path, "rb") as fh:
            raw = fh.read()
        review = json.loads(raw.decode("utf-8"), object_pairs_hook=_refuse_duplicate_keys)
    except _DuplicateKey as exc:
        return None, None, (f"{path} has a {exc}: could not tell which value the round "
                            "recorded")
    except (OSError, ValueError) as exc:
        return None, None, (f"{path} is unreadable ({exc}): could not tell whether the "
                            "verdict was recovered from stray lines")
    return review, hashlib.sha256(raw).hexdigest(), None


def _review_json_problem(root, ticket, row):
    """(problem, sha256). problem is None when this round's review.json is
    readable, is for `row`'s round and bundle, and its `ignored_lines` count
    is 0; else why not (owner decision 2026-10-01 #6). The row already carries
    the count; this is the second witness the owner asked for, so an
    unreadable file is could-not-tell, never a pass."""
    path = _review_json_path(root, ticket)
    review, digest, problem = read_review_json(root, ticket)
    if problem:
        return problem, None
    got = review.get("round") if isinstance(review, dict) else review
    # `True == 1`: a bool round would pass as round 1, so the type is checked.
    if not isinstance(review, dict) or isinstance(got, bool) or got != row.get("round"):
        return (f"{path} is not round {row.get('round')}'s (it reads {got!r}): could not "
                "tell whether the verdict was recovered from stray lines"), None
    if review.get("bundle_sha256") != row.get("bundle_sha256"):
        return (f"{path} is for bundle {str(review.get('bundle_sha256'))[:12]}, not the "
                f"round's {str(row.get('bundle_sha256'))[:12]}: could not tell whether the "
                "verdict was recovered from stray lines"), None
    # L-0576 writes the count here as an int (the lines go to `ignored_text`).
    # Any other shape is could-not-tell, never 0 (review round 5 BLOCK).
    count = review.get("ignored_lines")
    if not _is_count(count):
        return (f"{path} carries no readable ignored_lines count ({count!r}): could not "
                f"tell whether round {row.get('round')}'s verdict was recovered from stray "
                "lines"), None
    if count:
        return (f"{path}: round {row.get('round')}'s verdict was recovered from "
                f"{count} stray line(s); a recovered round is the owner's to accept"), None
    return None, digest


def auto_accept(root, ticket, follow_up):
    """Accept the latest round under the owner policy of 2026-09-30, or raise
    LedgerError naming the condition that failed (and change nothing)."""
    if not follow_up:
        raise LedgerError("--auto-accept needs --follow-up <id>: the ticket its FIX/NIT "
                          "lines go to")
    check_ticket(follow_up)
    if follow_up == ticket:
        raise LedgerError(f"--follow-up {follow_up} is the ticket itself; the follow-up is "
                          "a new ticket")

    def change(data, state):
        if state != "ok":
            raise LedgerError(f"--auto-accept refused: ledger is {state}; could not tell")
        refusal = auto_accept_refusal(data, ticket)
        if refusal:
            raise LedgerError(f"--auto-accept refused: {refusal}")
        row = data["rounds"][-1]
        problem, review_digest = _review_json_problem(root, ticket, row)
        if problem:
            raise LedgerError(f"--auto-accept refused: {problem}")
        if _current_hash(root, row.get("base"))[0] != row.get("bundle_sha256"):
            raise LedgerError("--auto-accept refused: the tree has changed since that review, "
                              "so accepting it would accept code nobody reviewed")
        data["receipt"] = {
            "kind": AUTO_KIND, "round": row["round"],
            "bundle_sha256": row["bundle_sha256"], "base": row["base"],
            "verdict": "FINDINGS", "accepted_by": AUTO_BY, "accepted_at": _now(),
            "findings": list(row["findings"]), "follow_up": follow_up,
            "provider": row.get("provider"), "model_family": row.get("model_family"),
            # What the review.json witness read, so receipt_stands can tell a
            # later edit (review round 6 BLOCK 1).
            "review_json_sha256": review_digest, "ignored_lines": 0,
        }
        data["state"] = ACCEPTED
        return data, data["receipt"]

    return _mutate(root, ticket, change)


def receipt_stands(receipt, latest, root, ticket):
    """Whether `receipt` stands on `latest`, the latest recorded round: a
    CLEAN round under a clean receipt; FINDINGS owner-accepted; or FINDINGS
    auto-accepted whose row still passes the guard, whose lines, provider
    and model family are the row's (review r3: a receipt that misstates the
    family the guard checked does not stand), and whose review.json still
    hashes to the bytes the guard read, with a count of 0 (review r6 BLOCK 1;
    an edited, missing, linked or unreadable file is could-not-tell, so the
    receipt does not stand)."""
    if not isinstance(receipt, dict) or not isinstance(latest, dict):
        return False
    if latest.get("status") != "completed" or receipt.get("round") != latest.get("round"):
        return False
    if latest.get("verdict") == "CLEAN":
        return receipt.get("kind") == "clean"
    if latest.get("verdict") != "FINDINGS":
        return False
    if receipt.get("kind") == "owner-accepted":
        return True
    return (receipt.get("kind") == AUTO_KIND and receipt.get("accepted_by") == AUTO_BY
            and receipt.get("findings") == latest.get("findings")
            and _receipt_names_the_reviewer(receipt, latest)
            and _auto_row_problem(latest) is None
            and _receipt_binds_review_json(receipt, latest, root, ticket))


def _receipt_binds_review_json(receipt, latest, root, ticket):
    """The auto receipt's `review_json_sha256` is a lowercase sha256 equal to
    review.json's bytes now, its `ignored_lines` is exactly int 0, and the
    file still passes the witness check for this round."""
    digest, count = receipt.get("review_json_sha256"), receipt.get("ignored_lines")
    if not isinstance(digest, str) or not _SHA256_RE.match(digest):
        return False
    if type(count) is not int or count != 0:  # pylint: disable=unidiomatic-typecheck
        return False
    problem, now = _review_json_problem(root, ticket, latest)
    return problem is None and now == digest


def _receipt_names_the_reviewer(receipt, latest):
    """The auto receipt's provider and model family are the row's, both
    present: the receipt carries the family the guard checked, never another."""
    pairs = ((receipt.get("provider"), latest.get("provider")),
             (receipt.get("model_family"), latest.get("model_family")))
    return all(isinstance(mine, str) and mine and mine == row for mine, row in pairs)


def check_follow_up(root, ticket):
    """(ok, message). For an auto-accepted receipt: the follow-up ticket's
    direction.md under `root` holds every receipt line verbatim as a whole
    line, as many times as the receipt carries it. Only a clean or
    owner-accepted receipt is not applicable; any other kind is could-not-tell."""
    data, state = _load(ledger_path(root, ticket))
    if state != "ok":
        return False, f"ledger is {state}; could not tell whether a follow-up is owed"
    receipt = data.get("receipt")
    if not isinstance(receipt, dict):
        return False, f"no receipt for {ticket}; run --check-receipt first"
    if receipt.get("kind") in ("clean", "owner-accepted"):
        return True, f"not applicable: the receipt is {receipt.get('kind')}, not {AUTO_KIND}"
    if receipt.get("kind") != AUTO_KIND:
        return False, (f"the receipt's kind is {receipt.get('kind')!r}, none of clean, "
                       f"owner-accepted or {AUTO_KIND}: could not tell")
    lines, follow_up = receipt.get("findings"), receipt.get("follow_up")
    if not isinstance(lines, list) or not lines or not all(isinstance(x, str) for x in lines):
        return False, "the auto-accepted receipt carries no finding lines: could not tell"
    try:
        check_ticket(follow_up)
    except LedgerError as exc:
        return False, f"the receipt's follow-up id is unusable: {exc}"
    path = os.path.join(root, ".work", "tickets", follow_up, "direction.md")
    try:
        # newline="": no universal-newline translation, so a bare \r is text,
        # never a break (review round 6 FIX 4). Lines split on "\n" only --
        # never splitlines(), which also breaks on U+2028, U+0085, \v, \f
        # (review round 4 FIX 2) -- and a CRLF line drops its one "\r", so a
        # direction.md checked out with Windows line endings still matches.
        with open(path, encoding="utf-8", newline="") as fh:
            have = collections.Counter(
                line[:-1] if line.endswith("\r") else line for line in fh.read().split("\n"))
    except OSError as exc:
        return False, f"follow-up {follow_up}: cannot read {path} ({exc.strerror or exc})"
    except UnicodeDecodeError as exc:
        return False, f"follow-up {follow_up}: {path} is not UTF-8 ({exc.reason}): could not tell"
    # Verbatim, never stripped, and counted: a line the receipt carries twice
    # is owed twice.
    missing = list((collections.Counter(lines) - have).elements())
    if missing:
        return False, (f"follow-up {follow_up}: {path} lacks {len(missing)} of {len(lines)} "
                       f"line(s) as a whole line, first: {missing[0]}")
    return True, f"follow-up {follow_up} quotes all {len(lines)} line(s) ({path})"


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
    return manifest["bundle_sha256"], manifest.get("merged_main")


def _merged_note(merged, stale):
    """What the rebuild left out as identical to merged main (T-0100), for the
    receipt check's line: the commit on a stale receipt, the count on a
    current one, and could-not-tell on either."""
    if not isinstance(merged, dict):
        return ""
    if merged.get("commit") is None:
        return (f"; merged main: {merged_main.UNKNOWN} - {merged_main.bare_reason(merged)}; "
                "nothing left out")
    if not merged.get("applies"):
        return ""
    count = len(merged.get("dropped") or [])
    # A failed fork lookup (`fork` recorded as null) is could-not-tell on both
    # lines; a manifest without the key, rebuilt by an older crew, reads as before.
    fork = "; fork: could not tell" if merged.get("fork", "") is None else ""
    if stale:
        return (f"; merged main: {merged['commit'][:12]} ({count} path(s) identical to it "
                f"left out){fork}")
    return (f" ({count} path(s) identical to merged main left out)" if count else "") + fork


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
    if not receipt_stands(receipt, latest, root, ticket):
        return False, (f"round {latest.get('round')} is {latest.get('verdict') or 'not completed'}"
                       "; a receipt stands only on a CLEAN or owner-accepted round, or an "
                       "auto-accepted 0-BLOCK one")
    try:
        current, merged = _current_hash(root, receipt.get("base"))
    except LedgerError as exc:
        return False, f"receipt could not be checked: {exc}"
    if current != receipt["bundle_sha256"]:
        return False, (f"receipt is stale: round {receipt.get('round')} accepted bundle "
                       f"{receipt['bundle_sha256'][:12]}, the tree now builds "
                       f"{(current or 'nothing')[:12]}; the change was edited after review"
                       f"{_merged_note(merged, stale=True)}")
    return True, (f"receipt current: round {receipt.get('round')} {receipt.get('kind')}, "
                  f"bundle {(current or '')[:12]}{_merged_note(merged, stale=False)}")


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


load = _load


def summary(data, state, ticket, path):
    """The status dict for a loaded ledger: what `status` returns and what
    `/crew:status` renders, so the two cannot count rounds differently."""
    if state == "corrupt":
        return {"ticket": ticket, "path": path, "state": UNKNOWN}
    rounds = data.get("rounds", [])
    return {"ticket": ticket, "path": path, "state": data.get("state") or "EMPTY",
            "rounds_used": len(rounds), "budget": BUDGET,
            "rounds_spent": _charged(data), "rounds_refunded": _refunded(data),
            "refund_limit": REFUND_LIMIT,
            "rounds_left": max(0, BUDGET - _charged(data)), "rounds": rounds,
            "successors": data.get("successors") or [],
            "receipt": data.get("receipt")}


def status(root, ticket):
    path = ledger_path(root, ticket)
    return summary(*_load(path), ticket, path)


def utf8_stdio():
    """Write stdout and stderr as UTF-8 whatever the console code page: a
    finding line is reviewer text, and on a Windows cp1252 console printing
    one carrying U+2028 (or any character cp1252 lacks) raised
    UnicodeEncodeError after the receipt was written (win-repo-2, 75bd0aea).
    A stream that cannot be reconfigured is left as it is."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def main(argv):
    utf8_stdio()
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
    action.add_argument("--auto-accept", action="store_true",
                        help="accept a final 0-BLOCK FINDINGS round (needs --follow-up; "
                             "takes no --by)")
    action.add_argument("--check-follow-up", action="store_true",
                        help="an auto-accepted receipt's follow-up quotes every line")
    action.add_argument("--successor-plan", metavar="PLAN_SHA256")
    parser.add_argument("--provider", default="claude")
    parser.add_argument("--model")
    parser.add_argument("--by", help="who accepts or rejects, with --accept / --reject")
    parser.add_argument("--follow-up", help="with --auto-accept: the follow-up ticket id")
    args = parser.parse_args(argv)
    if args.auto_accept and args.by is not None:
        parser.error("--auto-accept takes no --by: its accepted_by is fixed")
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
        if args.auto_accept:
            receipt = auto_accept(root, args.ticket, args.follow_up)
            print(f"review-ledger: round {receipt['round']} FINDINGS auto-accepted "
                  f"({AUTO_BY}), follow-up {receipt['follow_up']}, "
                  f"{len(receipt['findings'])} line(s)")
            for line in receipt["findings"]:
                print(line)
            return 0
        if args.check_follow_up:
            ok, message = check_follow_up(root, args.ticket)
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
