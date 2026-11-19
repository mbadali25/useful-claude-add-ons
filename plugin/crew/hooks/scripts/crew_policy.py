#!/usr/bin/env python3
"""crew_policy.py: the one deny-first decision table (revision-3 plan, 4.3).

REPORT-ONLY. Nothing in the plugin imports this module, so it changes no
allow or deny anywhere; `test_crew_policy.py` holds that (no other script
mentions it). A later ticket switches it on. Until then it answers one
question for a person or a test: "what would the table say?", with the
reason (`explain`).

Input: one request, a dict.

    operation   a key of `OPERATIONS`; an unlisted one is SERIOUS (4.13:
                "anything the classifier cannot place is serious")
    tier        dev | qa | prod; anything else is unknown
    presence    attended | unattended; anything else is unattended
    machine_layer   clear | block | mismatch | unreadable; anything else
                (including absent) trips rule 2, never passes it
    account     read-verified | write-verified | mismatch | fail |
                could-not-tell | none; checked only for operations that use
                an account, and only the exact access level passes
    provenance  plan-of-record | standing-plan | decider-approved-plan |
                record | none
    plan_covers, attested     True only if shown (see rule 5)
    prodcheck   pass | fail | unknown (the 4.5 checks, production only)
    admin_need  covers | other | none (rule 4)
    emergency   owner-declared | anything else (waives the review loop only)
    facts       per-operation facts (ownership, protection, backup, ...)

Every field is read the same way: a value that is missing, of the wrong
type, or not in the closed list is UNKNOWN, and unknown never takes the
permissive branch. The operating mode (guided or directive) is deliberately
not an input, so no mode can turn a deny into an allow.

Output: `decide` returns a dict with `outcome` (allow, ask-routine,
ask-owner, needs-plan or deny), `reason`, `rule` (the 4.3 rule number that
matched, or "human" for the one-way list), `serious` (the class, or None)
and `trace`, every rule looked at in order. `explain` renders the same
trace as text.

Readings this file chooses where the plan is silent (each is a test):
  * A condition that is definitely false is `deny`; one that cannot be shown
    is `ask-routine` (rule 8 names only the second).
  * Unknown ownership of a branch cannot make a push Free; unknown
    protection stops a force-push; a branch known to be protected is on the
    human-only list.
  * Destroying data needs the ticket's own data (ownership "own") and a
    provable backup (or "not-needed"); anything else is serious.
  * A reading with an unknown tier is refused by rule 3 like any other
    operation that names a target (the plan lists "read, any tier" at rule 6,
    after rule 3 has run).
  * An emergency counts only when "owner-declared", and waives only the
    merge review condition; it never lifts a deny, a needs-plan or a backup.

CLI (report-only, always exits 0 for a decision):
    crew_policy.py explain '<json>'     or  ... explain -   (stdin)
    crew_policy.py decide  '<json>'
    crew_policy.py operations
Unreadable JSON exits 2 with the reason on stderr and prints no decision.
"""
from __future__ import annotations

import json
import sys
from typing import Any, NamedTuple, Optional

REPORT_ONLY = True

ALLOW = "allow"
ASK_ROUTINE = "ask-routine"
ASK_OWNER = "ask-owner"
NEEDS_PLAN = "needs-plan"
DENY = "deny"
OUTCOMES = (ALLOW, ASK_ROUTINE, ASK_OWNER, NEEDS_PLAN, DENY)

TIERS = ("dev", "qa", "prod")
PRESENCE = ("attended", "unattended")
MACHINE_LAYER = ("clear", "block", "mismatch", "unreadable")
ACCOUNTS = ("read-verified", "write-verified", "mismatch", "fail",
            "could-not-tell", "none")
PROVENANCE = ("plan-of-record", "standing-plan", "decider-approved-plan",
              "record", "none")
PRODCHECK = ("pass", "fail", "unknown")
ADMIN_NEED = ("covers", "other", "none")
UNKNOWN = "unknown"

# Lanes (4.3 table).
FREE = "free"
READ = "read"
DESTRUCTIVE = "destructive"
CONDITIONAL = "conditional"
GRANT = "grant"
HUMAN = "human"
NEVER = "never"
SERIOUS_ALWAYS = "serious"

# The closed serious list (4.13). R-P6 owns refining it; this is its floor.
MONEY = "money"
PRODUCTION_WRITE = "production-write"
PERMISSION_CHANGE = "permission-change"
ACCOUNT_CREATION = "account-creation"
ADMIN_USE = "admin-use"
DESTROY_NOT_OWNED = "destroy-not-owned"
IRREVERSIBLE = "irreversible-or-outside-effect"
NO_PROVABLE_BACKUP = "no-provable-backup"
UNPLACED = "unplaced"

# Only these may be unlocked by a standing plan (an envelope, 4.4: workflow
# dispatch and terraform apply). Every other serious kind is exact-only:
# money, permission grants, account creation, admin operations, anything
# irreversible or with no provable backup, data destruction. A positive list,
# so a new operation is exact-only until someone adds it here.
ENVELOPE_OPS = frozenset({"start-deploy", "terraform-apply",
                          "land-next-tier"})


class Op(NamedTuple):
    """One row of the operation registry."""
    lane: str
    tiered: bool = False           # names a target whose tier matters
    account: Optional[str] = None  # "read" / "write" if it uses an account
    prod_serious: bool = False     # serious when the tier is prod
    admin: bool = False            # rule 4 applies
    serious: Optional[str] = None  # SERIOUS_ALWAYS lane: its class
    facts: tuple = ()              # ((name, required value), ...)
    note: str = ""


_OWN = (("ownership", "own"),)

OPERATIONS = {
    # Free: no condition beyond what the row lists.
    "fetch": Op(FREE),
    "pull": Op(FREE),
    "rebase-own-branch": Op(FREE, facts=_OWN),
    "branch": Op(FREE),
    "worktree": Op(FREE),
    "commit": Op(FREE),
    "push-own-branch": Op(FREE, facts=_OWN),
    "open-pr": Op(FREE),
    "update-pr": Op(FREE),
    "read-file": Op(FREE),
    "read-log": Op(FREE),
    "read-plan": Op(FREE),
    "read-ticket": Op(FREE),
    "comment": Op(FREE),
    "attach-evidence": Op(FREE),
    "fast-check": Op(FREE),
    "start-deploy": Op(FREE, tiered=True, account="write", prod_serious=True,
                       note="dev or QA deploy is Free; production is serious"),
    # Reads with a verified read account, any tier (rule 6).
    "sql-read": Op(READ, tiered=True, account="read"),
    "cloud-read": Op(READ, tiered=True, account="read"),
    # Destructive, non-serious only for the ticket's own data (rule 7).
    "delete-data": Op(DESTRUCTIVE, tiered=True, account="write",
                      prod_serious=True),
    # Conditional (rule 8).
    "force-push-own-branch": Op(CONDITIONAL, facts=_OWN + (
        ("protection", "unprotected"), ("lease_pinned", True))),
    "start-implement": Op(CONDITIONAL, facts=(("spec_approved", True),)),
    "merge-pr": Op(CONDITIONAL, facts=(
        ("review_clean", True), ("gate_pass_same_sha", True),
        ("approver_other_family", True))),
    "land-next-tier": Op(CONDITIONAL, tiered=True, account="write",
                         prod_serious=True,
                         facts=(("prior_tier_landed", True),
                                ("smoke_pass", True))),
    "terraform-apply": Op(CONDITIONAL, tiered=True, account="write",
                          prod_serious=True,
                          note="non-production: allow and log"),
    "grant-permission": Op(GRANT, tiered=True,
                           note="serious unless a temporary grant of a listed "
                                "profile in dev or QA (4.4)"),
    "remove-worktree": Op(CONDITIONAL, facts=(("results_verified", True),)),
    "change-ticket-status": Op(CONDITIONAL, facts=(("status_on_map", True),)),
    # Serious whatever the tier (4.13).
    "payment": Op(SERIOUS_ALWAYS, tiered=True, serious=MONEY),
    "create-account": Op(SERIOUS_ALWAYS, tiered=True,
                         serious=ACCOUNT_CREATION),
    "admin-identity-op": Op(SERIOUS_ALWAYS, tiered=True, admin=True,
                            serious=ADMIN_USE),
    "irreversible-outside-effect": Op(SERIOUS_ALWAYS, tiered=True,
                                      serious=IRREVERSIBLE),
    # Human only (the one-way list).
    "skip-gate": Op(HUMAN),
    "widen-policy": Op(HUMAN),
    "switch-to-directive": Op(HUMAN),
    "declare-emergency": Op(HUMAN),
    "amend-plan-of-record": Op(HUMAN),
    "push-protected-branch": Op(HUMAN),
    "admin-merge": Op(HUMAN),
    "hand-edit-terraform-state": Op(HUMAN),
    "delete-others-branch": Op(HUMAN),
    "delete-others-worktree": Op(HUMAN),
    "second-workflow-restart": Op(HUMAN),
    "bypass-guard-approved-by-person": Op(HUMAN),
    # Never: no request is recorded.
    "skip-hooks-or-signing": Op(NEVER),
    "approve-own-spec": Op(NEVER),
    "review-own-code": Op(NEVER),
    "grant-self-exception": Op(NEVER),
    "write-secret-plaintext": Op(NEVER),
    "change-guard-config-directly": Op(NEVER),
    "invent-status": Op(NEVER),
    "bypass-guard-by-agent": Op(NEVER),
}

_BRANCH_PUSHES = ("push-own-branch", "force-push-own-branch")


def _pick(value: Any, allowed: tuple) -> str:
    """Return `value` if it is one of `allowed`, else UNKNOWN."""
    if isinstance(value, str):
        value = value.strip().lower()
        if value in allowed:
            return value
    return UNKNOWN


def _fact(facts: dict, name: str, wanted: Any) -> str:
    """'met', 'violated' or UNKNOWN for one required fact."""
    seen = facts.get(name, UNKNOWN)
    if isinstance(wanted, bool):
        if isinstance(seen, bool):
            return "met" if seen == wanted else "violated"
        return UNKNOWN
    if isinstance(seen, str):
        seen = seen.strip().lower()
        if seen == wanted:
            return "met"
        if seen and seen != UNKNOWN:
            return "violated"
    return UNKNOWN


def _serious_class(spec: Op, tier: str, facts: dict) -> Optional[str]:
    """The seriousness class of this request, or None if it is not serious."""
    if spec.lane == SERIOUS_ALWAYS:
        return spec.serious
    if spec.prod_serious and tier == "prod":
        return PRODUCTION_WRITE
    if spec.lane == DESTRUCTIVE:
        if _fact(facts, "ownership", "own") != "met":
            return DESTROY_NOT_OWNED
        backup = facts.get("backup")
        if not (isinstance(backup, str)
                and backup.strip().lower() in ("provable", "not-needed")):
            return NO_PROVABLE_BACKUP
    if spec.lane == GRANT:
        permanence = _fact(facts, "permanence", "temporary")
        profile = _fact(facts, "profile", "listed")
        if tier == "prod" or permanence != "met" or profile != "met":
            return PERMISSION_CHANGE
    return None


class _Walk:
    """One walk of the table; keeps the trace and builds the answer."""

    def __init__(self, name: str, tier: str, unplaced: bool):
        self.trace: list = []
        self.name = name
        self.tier = tier
        self.unplaced = unplaced

    def look(self, rule: str, text: str) -> None:
        """Record one rule looked at."""
        self.trace.append(f"rule {rule}: {text}")

    def done(self, rule: str, outcome: str, reason: str,
             serious: Optional[str] = None) -> dict:
        """Close the walk with the decision."""
        self.trace.append(f"=> {outcome} ({reason})")
        return {"outcome": outcome, "reason": reason, "rule": rule,
                "serious": serious, "operation": self.name,
                "tier": self.tier, "known_operation": not self.unplaced,
                "trace": self.trace}


def decide(request: Any) -> dict:
    """Walk the table once and return the decision with its trace."""
    req = request if isinstance(request, dict) else {}
    facts = req.get("facts") if isinstance(req.get("facts"), dict) else {}
    name = req.get("operation")
    name = name.strip().lower() if isinstance(name, str) else ""
    tier = _pick(req.get("tier"), TIERS)
    attended = _pick(req.get("presence"), PRESENCE) == "attended"
    stop_outcome = ASK_OWNER if attended else DENY
    stop_word = "attended: ask the owner" if attended else "unattended: deny"

    unplaced = name not in OPERATIONS
    spec = OPERATIONS.get(name) or Op(SERIOUS_ALWAYS, tiered=True,
                                      serious=UNPLACED)
    walk = _Walk(name, tier, unplaced)
    walk.look("-", f"operation {name or '<missing>'!r}, tier {tier}, "
                   f"{'attended' if attended else 'unattended'}")
    if unplaced:
        walk.look("-", "operation is not in the table, so it is serious")
    if name in _BRANCH_PUSHES and _fact(facts, "protection",
                                        "protected") == "met":
        walk.look("-", "branch is protected, so this is a push to a "
                       "protected branch")
        name = walk.name = "push-protected-branch"
        spec = OPERATIONS[name]
    done = walk.done

    walk.look("1", "never lane?")
    if spec.lane == NEVER:
        return done("1", DENY, "never lane: no approval of any kind applies")

    layer = _pick(req.get("machine_layer"), MACHINE_LAYER)
    walk.look("2", f"machine layer {layer}")
    if layer != "clear":
        return done("2", stop_outcome,
                    f"machine layer is {layer} ({stop_word})")
    if spec.account:
        account = _pick(req.get("account"), ACCOUNTS)
        walk.look("2", f"account {account}, needs {spec.account}-verified")
        if account != spec.account + "-verified":
            return done("2", stop_outcome,
                        f"account is {account}, not the verified {spec.account} "
                        f"account the tier map names ({stop_word})")

    if spec.lane == HUMAN:
        walk.look("human", "one-way list")
        return done("human", ASK_OWNER,
                    "one-way: only the owner's yes, repeat-back and confirm; "
                    "the decider never answers it")

    if spec.tiered:
        walk.look("3", f"tier {tier}")
        if tier == UNKNOWN:
            return done("3", stop_outcome,
                        "tier is unknown, conflicting or unlisted; never "
                        "unattended and never classified by the decider "
                        f"({stop_word})")

    if spec.admin:
        need = _pick(req.get("admin_need"), ADMIN_NEED)
        walk.look("4", f"admin need {need}")
        if need != "covers":
            return done("4", DENY, "admin operation with no open need that "
                                   "covers exactly this operation")

    serious = _serious_class(spec, tier, facts)
    walk.look("5", f"serious class {serious or 'none'}")
    if serious:
        return _serious(req, walk, name, serious, attended, stop_outcome,
                        stop_word)

    if spec.lane == READ:
        return done("6", ALLOW, "read with a verified read account")
    if spec.lane == DESTRUCTIVE:
        return done("7", ALLOW, "own data with a provable backup")
    needed = list(spec.facts)
    if spec.lane == GRANT:
        needed = [("expiry_provable", True), ("within_ceiling", True)]
    if (_pick(req.get("emergency"), ("owner-declared",)) == "owner-declared"
            and name == "merge-pr"):
        needed = [f for f in needed if f[0] != "review_clean"]
        walk.look("8", "owner-declared emergency waives the review condition")
    verdicts = [(n, _fact(facts, n, want)) for n, want in needed]
    if needed:
        walk.look("8", "conditions: " + ", ".join(
            f"{n}={v}" for n, v in verdicts))
    bad = [n for n, v in verdicts if v == "violated"]
    if bad:
        return done("8", DENY, "condition is false: " + ", ".join(bad))
    unknown = [n for n, v in verdicts if v == UNKNOWN]
    if unknown:
        return done("8", ASK_ROUTINE,
                    "condition cannot be shown: " + ", ".join(unknown))
    if spec.lane == FREE:
        return done("9", ALLOW, "free")
    return done("8", ALLOW, "every condition met")


def _serious(req: dict, walk: _Walk, name: str, serious: str,
             attended: bool, stop_outcome: str, stop_word: str) -> dict:
    """Rule 5 for a serious request."""
    if serious == UNPLACED:
        return walk.done(
            "5", NEEDS_PLAN,
            "the operation is not in the closed table, and a plan of record "
            "cannot list a form the schema does not know", serious)
    prov = _pick(req.get("provenance"), PROVENANCE)
    covers = req.get("plan_covers") is True
    attested = req.get("attested") is True
    walk.look("5", f"provenance {prov}, covers {covers}, "
                   f"attested {attested}")
    if prov == "plan-of-record":
        usable = True
    elif prov == "standing-plan":
        usable = serious == PRODUCTION_WRITE and name in ENVELOPE_OPS
    else:
        usable = False
    if not (usable and covers):
        return walk.done(
            "5", NEEDS_PLAN,
            f"serious ({serious}) and no human-approved plan of record covers "
            f"it (provenance {prov}); no receipt, routine reply or decider "
            "answers this", serious)
    if not attended and not attested:
        return walk.done(
            "5", NEEDS_PLAN,
            f"serious ({serious}): unattended work needs an attested plan "
            "approval; without one it can only run attended", serious)
    if walk.tier == "prod":
        check = _pick(req.get("prodcheck"), PRODCHECK)
        walk.look("5", f"production checks {check}")
        if check != "pass":
            return walk.done(
                "5", stop_outcome,
                f"production checks are {check} ({stop_word})", serious)
    return walk.done("5", ALLOW,
                     f"covered by a plan of record ({serious})", serious)


def explain(request: Any) -> str:
    """Plain-text trace of one decision."""
    result = decide(request)
    lines = list(result["trace"])
    lines.append(f"outcome: {result['outcome']}")
    lines.append("report-only: this answer is not enforced anywhere yet")
    return "\n".join(lines)


def _main(argv: list) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "operations":
        for key in sorted(OPERATIONS):
            print(f"{key}\t{OPERATIONS[key].lane}")
        return 0
    if cmd not in ("decide", "explain") or len(argv) < 3:
        print("usage: crew_policy.py decide|explain <json|-> | operations",
              file=sys.stderr)
        return 2
    raw = sys.stdin.read() if argv[2] == "-" else argv[2]
    try:
        request = json.loads(raw)
    except ValueError as exc:
        print(f"crew_policy: request is not JSON ({exc}); no decision",
              file=sys.stderr)
        return 2
    if cmd == "explain":
        print(explain(request))
    else:
        print(json.dumps(decide(request), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
