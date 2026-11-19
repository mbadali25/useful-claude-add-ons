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
    plan_covers, attested     True only if shown (see rule 5). plan_covers
                means the plan covers THIS action in its exact form (an
                envelope only for ENVELOPE_OPS under a standing plan); the
                caller that certifies it owns that check, not this table
    prodcheck   pass | fail | unknown (the 4.5 checks, production only)
    admin_need  covers | other | none (rule 4)
    target      the target the request acts on (an emergency must name it)
    classified_as   the classifier's verdict (R-P6): a serious class name, or
                "none". It can only raise seriousness; an unrecognised value
                is unplaced, hence serious. facts.estimate_under_threshold
                (True only when an estimate was made and is under the cost
                threshold) is what keeps an infrastructure apply from being
                a money action
    emergency   a dict naming the owner, incident, target, action, expiry
                and uses left (see below); anything else is no emergency
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
  * Unknown ownership of a branch cannot make a push Free, and neither can
    unknown protection (a push, plain or forced, needs facts.protection
    "unprotected"); a branch known to be protected is on the human-only
    list, always (the plan says "outside a plan" but the serious list is
    closed and has no such class).
  * Reads of files, logs, plans and tickets need facts.credential_store
    False (credential stores stay denied to reads); True is a deny.
  * Destroying data needs the ticket's own data (ownership "own") and a
    provable backup; anything else is serious. A backup that failed
    (facts.backup "failed") refuses whatever a plan says; an irreversible,
    unbacked or not-owned destruction also needs facts.irreversible_listed,
    cap_set and preflight_ok to be True.
  * A grant needs a provable expiry inside the ceiling, an existing crew
    account, a provider ticket and proven ownership; unattended and not
    proved is refused. A grant that would make the account an admin account
    (facts.makes_admin) is denied, with or without a plan.
  * In production the attestation is required attended or not (4.5 lists
    it among the per-operation checks); 4.13's "attended without an
    attestation" applies outside production.
  * A production write by any route (grant, payment, outside effect) needs
    the verified write account; an admin operation does not (the broker).
  * QA data deletion needs facts.noted_on_ticket True, planned or not.
  * A tier landing is exact-only (no standing plan), and its own conditions
    still hold when a plan covers it.
  * A reading with an unknown tier is refused by rule 3 like any other
    operation that names a target (the plan lists "read, any tier" at rule 6,
    after rule 3 has run).
  * An emergency is a dict (declared_by "owner", incident, target, action
    equal to the operation, expired False, uses_left >= 1); it waives only
    the merge review condition (the timing waiver is not modelled) and never
    lifts a deny, a needs-plan or a backup.

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
# dispatch and terraform apply, and no other kind). Every other serious kind
# is exact-only: money, permission grants, account creation, admin operations,
# anything irreversible or with no provable backup, data destruction, a tier
# landing. A positive list, so a new operation is exact-only until someone
# adds it here.
ENVELOPE_OPS = frozenset({"start-deploy", "terraform-apply"})

# Serious classes that run only when the plan lists the exact action as
# irreversible with a cap, and a preflight passes (4.5, "Checks").
IRREVERSIBLE_CLASSES = frozenset({NO_PROVABLE_BACKUP, IRREVERSIBLE,
                                  DESTROY_NOT_OWNED})


class Op(NamedTuple):
    """One row of the operation registry."""
    lane: str
    tiered: bool = False           # names a target whose tier matters
    account: Optional[str] = None  # "read" / "write" if it uses an account
    prod_serious: bool = False     # serious when the tier is prod
    admin: bool = False            # rule 4 applies
    cost_checked: bool = False     # infrastructure: an estimate is needed
    serious: Optional[str] = None  # SERIOUS_ALWAYS lane: its class
    facts: tuple = ()              # ((name, required value), ...)
    note: str = ""


_OWN = (("ownership", "own"),)
_NOT_A_SECRET_STORE = (("credential_store", False),)

OPERATIONS = {
    # Free: no condition beyond what the row lists.
    "fetch": Op(FREE),
    "pull": Op(FREE),
    "rebase-own-branch": Op(FREE, facts=_OWN),
    "branch": Op(FREE),
    "worktree": Op(FREE),
    "commit": Op(FREE),
    "push-own-branch": Op(FREE, facts=_OWN + (("protection",
                                               "unprotected"),)),
    "open-pr": Op(FREE),
    "update-pr": Op(FREE),
    "read-file": Op(FREE, facts=_NOT_A_SECRET_STORE),
    "read-log": Op(FREE, facts=_NOT_A_SECRET_STORE),
    "read-plan": Op(FREE, facts=_NOT_A_SECRET_STORE),
    "read-ticket": Op(FREE, facts=_NOT_A_SECRET_STORE),
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
                          prod_serious=True, cost_checked=True,
                          note="non-production: allow and log"),
    "grant-permission": Op(GRANT, tiered=True,
                           note="serious unless a temporary grant of a listed "
                                "profile in dev or QA (4.4)"),
    "remove-worktree": Op(CONDITIONAL, facts=(("results_published", True),
                                              ("results_verified", True))),
    "change-ticket-status": Op(CONDITIONAL, facts=(("status_on_map", True),)),
    # Serious whatever the tier (4.13).
    "payment": Op(SERIOUS_ALWAYS, tiered=True, serious=MONEY),
    "create-account": Op(SERIOUS_ALWAYS, tiered=True, admin=True,
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


SERIOUS_CLASSES = frozenset({MONEY, PRODUCTION_WRITE, PERMISSION_CHANGE,
                             ACCOUNT_CREATION, ADMIN_USE, DESTROY_NOT_OWNED,
                             IRREVERSIBLE, NO_PROVABLE_BACKUP})


# The class reported for a request that is serious in more than one way,
# strictest first.
_PRIORITY = (UNPLACED, NO_PROVABLE_BACKUP, DESTROY_NOT_OWNED, IRREVERSIBLE,
             MONEY, ACCOUNT_CREATION, ADMIN_USE, PERMISSION_CHANGE,
             PRODUCTION_WRITE)


def _classes(spec: Op, tier: str, facts: dict, hint: Any = None) -> frozenset:
    """Every seriousness class that applies: the table's own and the
    classifier's verdict (request field classified_as). The verdict can only
    add a class, never remove one. A class this table knows is added; any
    other non-empty value is one it cannot place, so UNPLACED."""
    found = set()
    own = _own_class(spec, tier, facts)
    if own is not None:
        found.add(own)
    if hint is not None and hint != "none":
        said = hint.strip().lower() if isinstance(hint, str) else ""
        found.add(said if said in SERIOUS_CLASSES else UNPLACED)
    return frozenset(found)


def _primary(classes: frozenset) -> Optional[str]:
    """The strictest class of a set, for the answer and its reason."""
    return next((c for c in _PRIORITY if c in classes), None)


def _own_class(spec: Op, tier: str, facts: dict) -> Optional[str]:
    """The class this table derives from the operation and its facts."""
    if spec.lane == SERIOUS_ALWAYS:
        return spec.serious
    if spec.cost_checked and _fact(facts, "estimate_under_threshold",
                                   True) != "met":
        # An estimate that cannot be made counts as over (4.5, Money).
        return MONEY
    if spec.lane == DESTRUCTIVE:
        # The stricter classes win over "production write": the same facts
        # that make a dev deletion serious must not be dropped in prod.
        if _fact(facts, "ownership", "own") != "met":
            return DESTROY_NOT_OWNED
        backup = facts.get("backup")
        if not (isinstance(backup, str)
                and backup.strip().lower() == "provable"):
            return NO_PROVABLE_BACKUP
    if spec.prod_serious and tier == "prod":
        return PRODUCTION_WRITE
    if spec.lane == GRANT:
        permanence = _fact(facts, "permanence", "temporary")
        profile = _fact(facts, "profile", "listed")
        if tier == "prod" or permanence != "met" or profile != "met":
            return PERMISSION_CHANGE
    return None


GRANT_FACTS = (("expiry_provable", True), ("within_ceiling", True),
               ("crew_account_exists", True), ("provider_ticket", True),
               ("ownership", "own"))


def _lane_facts(spec: Op, facts: dict, tier: str) -> list:
    """The conditions of the operation's own lane. A grant's expiry facts
    are dropped only when the grant is positively shown to be permanent
    (nothing to expire); unknown permanence keeps them."""
    if spec.lane == DESTRUCTIVE:
        # QA: the data change is noted on the ticket (4.5), planned or not.
        return [("noted_on_ticket", True)] if tier == "qa" else []
    if spec.lane != GRANT:
        return list(spec.facts)
    if _fact(facts, "permanence", "permanent") == "met":
        return [f for f in GRANT_FACTS
                if f[0] not in ("expiry_provable", "within_ceiling")]
    return list(GRANT_FACTS)


def _verdicts(needed: list, facts: dict) -> tuple:
    """(verdicts, names of false conditions, names that cannot be shown)."""
    verdicts = [(n, _fact(facts, n, want)) for n, want in needed]
    return (verdicts, [n for n, v in verdicts if v == "violated"],
            [n for n, v in verdicts if v == UNKNOWN])


def _emergency(req: dict, name: str) -> bool:
    """True only for an emergency the owner declared for this very action
    (4.5): incident, target, action, expiry not passed, a use left."""
    emerg = req.get("emergency")
    if not isinstance(emerg, dict):
        return False
    uses = emerg.get("uses_left")
    target = req.get("target")
    return (emerg.get("declared_by") == "owner"
            and isinstance(emerg.get("incident"), str)
            and emerg.get("incident").strip() != ""
            and isinstance(target, str) and target.strip() != ""
            and emerg.get("target") == target
            and emerg.get("action") == name
            and emerg.get("expired") is False
            and isinstance(uses, int) and not isinstance(uses, bool)
            and uses >= 1)


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
    # Every class that applies is known before any rule runs, so a class the
    # classifier adds (classified_as) pulls in the same requirements the
    # operation's own class would: a tier, the write account, an admin need.
    classes = _classes(spec, tier, facts, req.get("classified_as"))
    needs_admin = spec.admin or bool(classes & {ADMIN_USE, ACCOUNT_CREATION})

    walk.look("1", "never lane?")
    if spec.lane == NEVER:
        return done("1", DENY, "never lane: no approval of any kind applies")

    layer = _pick(req.get("machine_layer"), MACHINE_LAYER)
    walk.look("2", f"machine layer {layer}")
    if layer != "clear":
        return done("2", stop_outcome,
                    f"machine layer is {layer} ({stop_word})")
    # A production write by any route uses the verified write account; an
    # admin operation goes through the broker instead (4.14).
    access = spec.account or (
        "write" if tier == "prod" and classes and not needs_admin
        and spec.lane not in (HUMAN, NEVER) else None)
    if access:
        account = _pick(req.get("account"), ACCOUNTS)
        walk.look("2", f"account {account}, needs {access}-verified")
        if account != access + "-verified":
            return done("2", stop_outcome,
                        f"account is {account}, not the verified {access} "
                        f"account the tier map names ({stop_word})")
    else:
        other = _pick(req.get("account"), ACCOUNTS)
        if other in ("mismatch", "fail", "could-not-tell"):
            walk.look("2", f"account {other} (identity does not check out)")
            return done("2", stop_outcome,
                        f"account is {other} ({stop_word})")

    if spec.lane == HUMAN:
        walk.look("human", "one-way list")
        return done("human", ASK_OWNER,
                    "one-way: only the owner's yes, repeat-back and confirm; "
                    "the decider never answers it")

    if spec.tiered or classes:
        walk.look("3", f"tier {tier}")
        if tier == UNKNOWN:
            return done("3", stop_outcome,
                        "tier is unknown, conflicting or unlisted; never "
                        "unattended and never classified by the decider "
                        f"({stop_word})")

    if needs_admin:
        need = _pick(req.get("admin_need"), ADMIN_NEED)
        walk.look("4", f"admin need {need}")
        if need != "covers":
            return done("4", DENY, "admin operation with no open need that "
                                   "covers exactly this operation")

    if spec.lane == GRANT:
        admin = _fact(facts, "makes_admin", False)
        walk.look("4a", f"grant would make the account an admin account: "
                        f"{admin}")
        if admin == "violated":
            return done("4a", DENY, "a grant may never give identity-"
                                    "management rights or * on *; that is "
                                    "an admin account (4.4)")
        if admin != "met":
            return done("4a", stop_outcome,
                        "cannot show the grant is not an admin grant "
                        f"({stop_word})")

    backup = facts.get("backup")
    if isinstance(backup, str) and backup.strip().lower() == "failed":
        walk.look("5a", "a required backup whose probe failed")
        return done("5a", DENY, "a backup that was required and whose probe "
                                "failed always refuses; no plan excuses it")

    serious = _primary(classes)
    walk.look("5", f"serious class {serious or 'none'}"
                   + (f" (all: {sorted(classes)})" if len(classes) > 1
                      else ""))
    if serious:
        return _serious(req, walk, (name, spec, facts, classes), serious,
                        attended, (stop_outcome, stop_word))

    if spec.lane == READ:
        return done("6", ALLOW, "read with a verified read account")
    needed = _lane_facts(spec, facts, tier)
    if name == "merge-pr" and _emergency(req, name):
        needed = [f for f in needed if f[0] != "review_clean"]
        walk.look("8", "an owner-declared emergency for this action waives "
                       "the review condition")
    verdicts, bad, unknown = _verdicts(needed, facts)
    if needed:
        walk.look("8", "conditions: " + ", ".join(
            f"{n}={v}" for n, v in verdicts))
    if bad:
        return done("8", DENY, "condition is false: " + ", ".join(bad))
    if unknown and spec.lane == GRANT and not attended:
        return done("8", DENY, "unattended and cannot be proved, so refused "
                               "(4.4): " + ", ".join(unknown))
    if unknown:
        return done("8", ASK_ROUTINE,
                    "condition cannot be shown: " + ", ".join(unknown))
    if spec.lane == FREE:
        return done("9", ALLOW, "free")
    if spec.lane == DESTRUCTIVE:
        return done("7", ALLOW, "own data with a provable backup"
                                + (" and the change noted on the ticket"
                                   if tier == "qa" else ""))
    return done("8", ALLOW, "every condition met")


def _serious(req: dict, walk: _Walk, subject: tuple, serious: str,
             attended: bool, stop: tuple) -> dict:
    """Rule 5 for a serious request. `subject` is (name, spec, facts,
    classes) and
    `stop` is (outcome, wording) for a stop that depends on presence.
    `subject` carries every class that applies; the strictest is `serious`."""
    name, spec, facts, classes = subject
    stop_outcome, stop_word = stop
    if UNPLACED in classes:
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
        usable = classes == {PRODUCTION_WRITE} and name in ENVELOPE_OPS
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
    if classes & IRREVERSIBLE_CLASSES:
        listed = (_fact(facts, "irreversible_listed", True),
                  _fact(facts, "cap_set", True))
        walk.look("5", f"irreversible listing and cap {listed}")
        if listed != ("met", "met"):
            return walk.done(
                "5", NEEDS_PLAN,
                f"serious ({serious}) runs only when the plan lists this "
                "exact action as irreversible with a cap (4.5)", serious)
        if _fact(facts, "preflight_ok", True) != "met":
            return walk.done("5", DENY, "the preflight is missing or "
                                        "failed, so it refuses (4.5)", serious)
    if walk.tier == "prod":
        if not attested:
            return walk.done(
                "5", NEEDS_PLAN,
                f"serious ({serious}) in production: the plan approval's "
                "attestation is one of the per-operation checks (4.5), "
                "attended or not", serious)
        check = _pick(req.get("prodcheck"), PRODCHECK)
        walk.look("5", f"production checks {check}")
        if check != "pass":
            return walk.done(
                "5", stop_outcome,
                f"production checks are {check} ({stop_word})", serious)
    lane_facts = _lane_facts(spec, facts, walk.tier)
    if lane_facts:
        verdicts, bad, unknown = _verdicts(lane_facts, facts)
        walk.look("5", "the lane's own conditions still hold: " + ", ".join(
            f"{n}={v}" for n, v in verdicts))
        if bad:
            return walk.done("5", DENY, "condition is false: " + ", ".join(bad),
                             serious)
        if unknown:
            return walk.done(
                "5", stop_outcome,
                f"condition cannot be shown: {', '.join(unknown)} "
                f"({stop_word})", serious)
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
