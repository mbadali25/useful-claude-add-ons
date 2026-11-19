"""`crew_policy.py`: the deny-first decision table, REPORT-ONLY (plan 4.3, R-01).

The module blocks and allows nothing yet, so two kinds of test live here:

* the table itself: a positive and a negative case for every operation, and
  the unknowns the plan calls out (unknown tier, unknown protection, unknown
  ownership, unknown operation, unknown account, unknown machine layer),
  with the order of the rules held (first match wins);
* the inertness: no other script reaches it, it reads no operating mode, and
  it imports only the standard library, so merging it moves no outcome.

Because a later ticket will switch the table on, the suite also sabotages
itself: `MUTATIONS` re-introduce one way each rule could be weakened into a
copy of the module's source, and each copy must fail `violations()`. A table
that nothing catches a weakened rule in is not tested. (The shared
`sabotage*.py` files are review-harness paths that must land alone, and this
module is not block-capable yet, so the in-file form is used here; the
switch-on ticket adds a harness-only companion for them.)
"""
import ast
import itertools
import json
import os
import subprocess
import sys
import types

import pytest

import context  # noqa: F401  pylint: disable=unused-import

import crew_policy as P  # noqa: E402  pylint: disable=wrong-import-position

SCRIPTS = os.path.dirname(os.path.abspath(P.__file__))
PLUGIN = os.path.dirname(os.path.dirname(SCRIPTS))
MODULE = os.path.join(SCRIPTS, "crew_policy.py")


def source():
    """The module's text."""
    with open(MODULE, encoding="utf-8") as handle:
        return handle.read()


GONE = object()  # remove the key from the request
TIERED = [k for k, v in P.OPERATIONS.items() if v.tiered]
ACCOUNTED = [k for k, v in P.OPERATIONS.items() if v.account]
NOT_NEVER = [k for k, v in P.OPERATIONS.items() if v.lane != P.NEVER]
STOP = {"attended": "ask-owner", "unattended": "deny"}


def good_facts(spec):
    """The facts that satisfy every condition of an operation."""
    facts = dict(spec.facts)
    if spec.lane == P.GRANT:
        facts.update(permanence="temporary", profile="listed",
                     makes_admin=False)
        facts.update(P.GRANT_FACTS)
    if spec.lane == P.DESTRUCTIVE:
        facts.update(ownership="own", backup="provable",
                     noted_on_ticket=True)
    if spec.serious in P.IRREVERSIBLE_CLASSES:
        facts.update(irreversible_listed=True, cap_set=True,
                     preflight_ok=True)
    return facts


def req(op, tier="dev", presence="attended", facts=None, **top):
    """A request that satisfies the op's own conditions; override to break."""
    spec = P.OPERATIONS.get(op)
    out = {"operation": op, "tier": tier, "presence": presence,
           "machine_layer": "clear", "target": "repo"}
    if spec is not None:
        if spec.account:
            out["account"] = spec.account + "-verified"
        if spec.lane == P.GRANT and tier == "prod":
            out["account"] = "write-verified"
        if spec.admin:
            out["admin_need"] = "covers"
        out["facts"] = good_facts(spec)
    if facts:
        out["facts"] = dict(out.get("facts", {}))
        for key, val in facts.items():
            if val is GONE:
                out["facts"].pop(key, None)
            else:
                out["facts"][key] = val
    for key, val in top.items():
        if val is GONE:
            out.pop(key, None)
        else:
            out[key] = val
    return out


def planned(op, tier="dev", **top):
    """A request covered by an attested plan of record."""
    top.setdefault("provenance", "plan-of-record")
    top.setdefault("plan_covers", True)
    top.setdefault("attested", True)
    top.setdefault("prodcheck", "pass")
    return req(op, tier, **top)


def emergency(action="merge-pr", **over):
    """An emergency the owner declared for one action."""
    out = {"declared_by": "owner", "incident": "INC-1", "target": "repo",
           "action": action, "expired": False, "uses_left": 1}
    out.update(over)
    return out


def outcome(request, module=P):
    """The table's answer for one request."""
    return module.decide(request)["outcome"]


# --- the table as data: (id, request, expected outcome) ---------------------

def _cases():
    rows = []

    def add(cid, request, want):
        rows.append((cid, request, want))

    for op, spec in P.OPERATIONS.items():
        lane = spec.lane
        good = {P.HUMAN: "ask-owner", P.NEVER: "deny",
                P.SERIOUS_ALWAYS: "needs-plan"}.get(lane, "allow")
        add(f"{op}: the plain case", req(op), good)
        for presence in ("attended", "unattended"):
            for layer in ("block", "mismatch", "unreadable", GONE, "nonsense"):
                want = "deny" if lane == P.NEVER else STOP[presence]
                add(f"{op}: machine layer {layer}, {presence}",
                    req(op, presence=presence, machine_layer=layer), want)
        if spec.account:
            for acct in ("mismatch", "fail", "could-not-tell", "none", GONE,
                         7, "read-verified" if spec.account == "write"
                         else "write-verified"):
                for presence in ("attended", "unattended"):
                    add(f"{op}: account {acct!r}, {presence}",
                        req(op, presence=presence, account=acct),
                        STOP[presence])
        if spec.tiered:
            for tier in (GONE, None, "", "staging", "conflict", 3):
                for presence in ("attended", "unattended"):
                    add(f"{op}: tier {tier!r}, {presence}",
                        req(op, presence=presence, tier=tier), STOP[presence])
        if spec.prod_serious:
            add(f"{op}: prod needs a plan", req(op, "prod"), "needs-plan")
        for cond, want in spec.facts:
            add(f"{op}: {cond} is false",
                req(op, facts={cond: (not want) if isinstance(want, bool)
                               else "other"}), "deny")
            add(f"{op}: {cond} is absent",
                req(op, facts={cond: GONE}), "ask-routine")
            add(f"{op}: {cond} is unknown",
                req(op, facts={cond: "unknown"}), "ask-routine")
            if isinstance(want, bool):
                add(f"{op}: {cond} is the string 'yes'",
                    req(op, facts={cond: "yes"}), "ask-routine")
        if lane == P.SERIOUS_ALWAYS:
            for tier in ("dev", "prod"):
                add(f"{op}: {tier}, unattended and not attested",
                    planned(op, tier, presence="unattended", attested=False),
                    "needs-plan")
                add(f"{op}: {tier}, attended and not attested",
                    planned(op, tier, attested=False), "allow")
                add(f"{op}: {tier}, plan of record, unattended",
                    planned(op, tier, presence="unattended"), "allow")
            for presence in ("attended", "unattended"):
                add(f"{op}: plan of record, {presence}",
                    planned(op, presence=presence), "allow")
                add(f"{op}: plan does not cover, {presence}",
                    planned(op, presence=presence, plan_covers=False),
                    "needs-plan")
                for prov in ("decider-approved-plan", "record", "none",
                             "standing-plan", "junk"):
                    add(f"{op}: {prov}, {presence}",
                        planned(op, presence=presence, provenance=prov),
                        "needs-plan")
            add(f"{op}: unattended and not attested",
                planned(op, presence="unattended", attested=False),
                "needs-plan")
            add(f"{op}: attended and not attested",
                planned(op, attested=False), "allow")
            add(f"{op}: presence unknown and not attested",
                planned(op, presence="away", attested=False), "needs-plan")
        if lane == P.HUMAN:
            for prov in ("plan-of-record", "standing-plan", "none"):
                add(f"{op}: {prov}", planned(op, provenance=prov),
                    "ask-owner")
        if spec.admin:
            for need in ("none", "other", GONE):
                for tier in ("dev", "prod"):
                    add(f"{op}: {tier}, admin need {need!r}",
                        planned(op, tier, admin_need=need), "deny")
            add(f"{op}: an open need alone", req(op), "needs-plan")
        if spec.prod_serious:
            for prov, covers, want in (
                    ("plan-of-record", True, "allow"),
                    ("plan-of-record", False, "needs-plan"),
                    ("decider-approved-plan", True, "needs-plan"),
                    ("standing-plan", True,
                     "allow" if op in P.ENVELOPE_OPS else "needs-plan")):
                add(f"{op}: prod, {prov} covers={covers}",
                    planned(op, "prod", provenance=prov, plan_covers=covers),
                    want)
            for check in ("fail", "unknown", GONE, True):
                for presence in ("attended", "unattended"):
                    add(f"{op}: prod checks {check!r}, {presence}",
                        planned(op, "prod", presence=presence,
                                prodcheck=check), STOP[presence])
            for tier in ("dev", "qa"):
                add(f"{op}: {tier} needs no production checks",
                    req(op, tier, prodcheck="fail"), "allow")
    # Branches, destruction, grants, emergencies and presence.
    for op in ("push-own-branch", "force-push-own-branch"):
        for presence in ("attended", "unattended"):
            add(f"{op}: protected branch, {presence}",
                planned(op, presence=presence,
                        facts={"protection": "protected"}), "ask-owner")
    for ownership in ("other", "unknown", GONE, None, ""):
        add(f"delete-data: ownership {ownership!r} is not the ticket's own",
            req("delete-data", facts={"ownership": ownership}), "needs-plan")
    for backup in ("none", "unknown", GONE, None, True, "not-needed"):
        add(f"delete-data: backup {backup!r} is not provable",
            req("delete-data", facts={"backup": backup}), "needs-plan")
    for backup in ("provable",):
        add(f"delete-data: backup {backup}",
            req("delete-data", facts={"backup": backup}), "allow")
    unlisted = {"irreversible_listed": True, "cap_set": True}
    add("delete-data: a plan that lists the unbacked action unlocks it",
        planned("delete-data", facts=dict(unlisted, backup="none",
                                          preflight_ok=True)), "allow")
    add("delete-data: no irreversible listing",
        planned("delete-data", facts={"backup": "none"}), "needs-plan")
    add("delete-data: listing without a cap",
        planned("delete-data", facts={"backup": "none",
                                      "irreversible_listed": True,
                                      "preflight_ok": True}), "needs-plan")
    for pre in (False, GONE, "yes"):
        add(f"delete-data: preflight {pre!r} refuses",
            planned("delete-data", facts=dict(unlisted, backup="none",
                                              preflight_ok=pre)), "deny")
    add("delete-data: a failed backup refuses even with a listing",
        planned("delete-data", facts=dict(unlisted, backup="failed",
                                          preflight_ok=True)), "deny")
    add("irreversible-outside-effect: no listing",
        planned("irreversible-outside-effect",
                facts={"irreversible_listed": GONE}), "needs-plan")
    add("irreversible-outside-effect: no preflight",
        planned("irreversible-outside-effect",
                facts={"preflight_ok": False}), "deny")
    add("payment: a failed backup refuses",
        planned("payment", facts={"backup": "failed"}), "deny")
    for protection, want in (("unprotected", "allow"),
                             ("unknown", "ask-routine"),
                             (GONE, "ask-routine"), (False, "ask-routine")):
        add(f"push-own-branch: protection {protection!r}",
            req("push-own-branch", facts={"protection": protection}), want)
    for op in ("read-file", "read-log", "read-plan", "read-ticket"):
        add(f"{op}: a credential store is denied",
            planned(op, facts={"credential_store": True}), "deny")
    add("land-next-tier: prod, plan covers but the prior tier did not land",
        planned("land-next-tier", "prod", facts={"prior_tier_landed": False}),
        "deny")
    add("land-next-tier: prod, plan covers but smoke is unknown",
        planned("land-next-tier", "prod", facts={"smoke_pass": GONE}),
        "ask-owner")
    add("land-next-tier: prod, standing plan is not enough",
        planned("land-next-tier", "prod", provenance="standing-plan"),
        "needs-plan")
    add("remove-worktree: published but not verified",
        req("remove-worktree", facts={"results_verified": False}), "deny")
    add("remove-worktree: verified but not published",
        req("remove-worktree", facts={"results_published": False}), "deny")
    for facts, want in (
            ({}, "allow"),
            ({"permanence": "permanent"}, "needs-plan"),
            ({"permanence": "unknown"}, "needs-plan"),
            ({"permanence": GONE}, "needs-plan"),
            ({"profile": "unlisted"}, "needs-plan"),
            ({"profile": GONE}, "needs-plan"),
            ({"makes_admin": True}, "deny"),
            ({"makes_admin": GONE}, "ask-owner"),
            ({"makes_admin": "no"}, "ask-owner"),
            ({"expiry_provable": GONE}, "ask-routine"),
            ({"expiry_provable": False}, "deny"),
            ({"within_ceiling": GONE}, "ask-routine"),
            ({"within_ceiling": False}, "deny"),
            ({"crew_account_exists": False}, "deny"),
            ({"crew_account_exists": GONE}, "ask-routine"),
            ({"provider_ticket": False}, "deny"),
            ({"provider_ticket": GONE}, "ask-routine"),
            ({"ownership": GONE}, "ask-routine"),
            ({"ownership": "other"}, "deny")):
        add(f"grant-permission: {facts!r}",
            req("grant-permission", facts=facts), want)
        if want == "ask-routine":
            add(f"grant-permission: unattended, {facts!r}",
                req("grant-permission", presence="unattended", facts=facts),
                "deny")
    add("grant-permission: production", req("grant-permission", "prod"),
        "needs-plan")
    for tier in ("dev", "prod"):
        for presence in ("attended", "unattended"):
            # In dev a temporary listed grant is not serious: a fact that
            # cannot be shown asks (attended) or is refused (unattended).
            unknown_is = (STOP[presence] if tier == "prod" else
                          "ask-routine" if presence == "attended" else "deny")
            for fact, bad, want in (
                    ("crew_account_exists", False, "deny"),
                    ("provider_ticket", False, "deny"),
                    ("ownership", "other", "deny"),
                    ("expiry_provable", False, "deny"),
                    ("within_ceiling", False, "deny"),
                    ("crew_account_exists", GONE, unknown_is),
                    ("expiry_provable", GONE, unknown_is)):
                add(f"grant-permission: covered {tier}, {presence}, "
                    f"{fact}={bad!r}",
                    planned("grant-permission", tier, presence=presence,
                            facts={fact: bad}),
                    want)
    add("grant-permission: a covered permanent grant needs no expiry facts",
        planned("grant-permission", "prod",
                facts={"permanence": "permanent", "expiry_provable": GONE,
                       "within_ceiling": GONE}), "allow")
    for acct in ("mismatch", "fail", "could-not-tell"):
        for presence in ("attended", "unattended"):
            add(f"grant-permission: covered, account {acct}, {presence}",
                planned("grant-permission", "prod", presence=presence,
                        account=acct), STOP[presence])
            add(f"commit: account {acct}, {presence}",
                req("commit", presence=presence, account=acct), STOP[presence])
    add("delete-data: prod, ownership unknown, covered but not listed",
        planned("delete-data", "prod", facts={"ownership": GONE}),
        "needs-plan")
    add("delete-data: prod, no backup, covered but not listed",
        planned("delete-data", "prod", facts={"backup": "none"}),
        "needs-plan")
    add("delete-data: prod, no backup, listed with a cap, preflight fails",
        planned("delete-data", "prod", facts={
            "backup": "none", "irreversible_listed": True, "cap_set": True,
            "preflight_ok": False}), "deny")
    add("delete-data: prod, provable backup, covered",
        planned("delete-data", "prod"), "allow")
    add("merge-pr: an emergency for another target does not waive it",
        req("merge-pr", facts={"review_clean": False}, target="repo#2",
            emergency=emergency(target="repo#1")), "deny")
    add("merge-pr: an emergency with no request target does not waive it",
        req("merge-pr", facts={"review_clean": False}, target=GONE,
            emergency=emergency()), "deny")
    for acct in ("none", "read-verified", GONE):
        for presence in ("attended", "unattended"):
            add(f"grant-permission: covered prod grant, account {acct!r}, "
                f"{presence}",
                planned("grant-permission", "prod", presence=presence,
                        account=acct), STOP[presence])
    for tier in ("dev", "prod"):
        add(f"grant-permission: covered {tier}, permanence and expiry unknown",
            planned("grant-permission", tier,
                    facts={"permanence": GONE, "expiry_provable": GONE,
                           "within_ceiling": GONE}),
            "ask-owner")
    add("delete-data: qa, not noted on the ticket is unknown",
        req("delete-data", "qa", facts={"noted_on_ticket": GONE}),
        "ask-routine")
    add("delete-data: qa, noted_on_ticket false",
        req("delete-data", "qa", facts={"noted_on_ticket": False}), "deny")
    add("delete-data: dev needs no ticket note",
        req("delete-data", "dev", facts={"noted_on_ticket": GONE}), "allow")
    add("grant-permission: a plan cannot grant admin rights",
        planned("grant-permission", "prod", facts={"makes_admin": True}),
        "deny")
    add("grant-permission: a covered production grant",
        planned("grant-permission", "prod"), "allow")
    for who, want in ((emergency(), "allow"),
                      (emergency(action="payment"), "deny"),
                      (emergency(declared_by="agent"), "deny"),
                      (emergency(expired=True), "deny"),
                      (emergency(expired=GONE), "deny"),
                      (emergency(uses_left=0), "deny"),
                      (emergency(uses_left=True), "deny"),
                      (emergency(incident=""), "deny"),
                      (emergency(target=None), "deny"),
                      ("owner-declared", "deny"), (True, "deny"),
                      ("yes", "deny"), (GONE, "deny")):
        add(f"merge-pr: emergency {who!r} waives the review",
            req("merge-pr", facts={"review_clean": False}, emergency=who),
            want)
    add("merge-pr: an emergency does not waive the gate",
        req("merge-pr", facts={"gate_pass_same_sha": False},
            emergency=emergency()), "deny")
    add("payment: an emergency does not unlock it",
        req("payment", emergency=emergency("payment")), "needs-plan")
    for presence in (GONE, None, "away", 1):
        add(f"start-deploy: presence {presence!r} is unattended",
            req("start-deploy", tier="staging", presence=presence), "deny")
    return rows


CASES = _cases()


def violations(module):
    """Every row of the table the module answers differently, with the
    unknown-operation rows. An empty list means the table is intact."""
    bad = []
    for cid, request, want in CASES:
        got = outcome(request, module)
        if got != want:
            bad.append(f"{cid}: wanted {want}, got {got}")
    for request in (None, [], "allow", {}, {"operation": None},
                    {"operation": 5}, {"operation": "nope"}):
        if outcome(request, module) == "allow":
            bad.append(f"unplaced operation {request!r} was allowed")
    if outcome(planned("mystery"), module) != "needs-plan":
        bad.append("a plan of record unlocked an operation not in the table")
    return bad


# --- the table ---------------------------------------------------------------

def test_the_table_answers_every_case():
    assert violations(P) == []


def test_every_operation_has_a_positive_and_a_negative_case():
    for op, spec in P.OPERATIONS.items():
        mine = {want for cid, _, want in CASES if cid.startswith(op + ":")}
        assert len(mine) >= 2 or spec.lane in (P.NEVER,), (op, mine)
        if spec.lane in (P.FREE, P.READ, P.CONDITIONAL, P.GRANT,
                         P.DESTRUCTIVE):
            assert "allow" in mine and mine - {"allow"}, (op, mine)


def test_lanes_cover_the_plan_table():
    lanes = {spec.lane for spec in P.OPERATIONS.values()}
    assert lanes == {P.FREE, P.READ, P.DESTRUCTIVE, P.CONDITIONAL, P.GRANT,
                     P.SERIOUS_ALWAYS, P.HUMAN, P.NEVER}
    never = {k for k, v in P.OPERATIONS.items() if v.lane == P.NEVER}
    assert {"skip-hooks-or-signing", "approve-own-spec", "review-own-code",
            "grant-self-exception", "write-secret-plaintext",
            "change-guard-config-directly", "invent-status"} <= never


# --- the unknowns -------------------------------------------------------------

@pytest.mark.parametrize("operation", ["", "nope", "git-push --force", None, 5,
                                       ["commit"]])
def test_an_unknown_operation_is_serious_and_needs_a_plan(operation):
    result = P.decide({"operation": operation, "tier": "dev",
                       "presence": "attended", "machine_layer": "clear"})
    assert result["outcome"] == "needs-plan"
    assert result["serious"] == "unplaced"
    assert result["known_operation"] is False


@pytest.mark.parametrize("request_", [None, [], "allow", 3, {}])
def test_an_unreadable_request_allows_nothing(request_):
    assert P.decide(request_)["outcome"] in ("deny", "ask-owner")


def test_an_unknown_operation_is_not_unlocked_by_a_decider_plan_or_record():
    for prov in ("decider-approved-plan", "record", "none", "junk", GONE):
        request = {"operation": "mystery", "tier": "dev",
                   "presence": "attended", "machine_layer": "clear",
                   "plan_covers": True, "attested": True}
        if prov is not GONE:
            request["provenance"] = prov
        assert outcome(request) == "needs-plan", prov


@pytest.mark.parametrize("ownership,want", [
    ("own", "allow"), ("other", "deny"), ("unknown", "ask-routine"),
    (GONE, "ask-routine"), ("", "ask-routine"), (None, "ask-routine"),
    (True, "ask-routine")])
@pytest.mark.parametrize("op", ["push-own-branch", "rebase-own-branch"])
def test_unknown_ownership_of_a_branch_cannot_make_a_push_free(op, ownership,
                                                              want):
    assert outcome(req(op, facts={"ownership": ownership})) == want


@pytest.mark.parametrize("ownership", ["other", "unknown", GONE, None, ""])
def test_destroying_data_not_shown_to_be_the_tickets_own_needs_a_plan(
        ownership):
    for tier in ("dev", "qa"):
        result = P.decide(req("delete-data", tier,
                              facts={"ownership": ownership}))
        assert result["outcome"] == "needs-plan"
        assert result["serious"] == "destroy-not-owned"


@pytest.mark.parametrize("backup", ["none", "unknown", "", GONE, None, True,
                                    "not-needed"])
def test_destroying_data_without_a_provable_backup_needs_a_plan(backup):
    result = P.decide(req("delete-data", facts={"backup": backup}))
    assert (result["outcome"], result["serious"]) == (
        "needs-plan", "no-provable-backup")


def test_own_data_with_a_provable_backup_is_free_in_dev_and_qa():
    for tier in ("dev", "qa"):
        assert outcome(req("delete-data", tier,
                           facts={"backup": "provable"})) == "allow"


def test_a_failed_backup_refuses_whatever_a_plan_says():
    for presence in ("attended", "unattended"):
        assert outcome(planned("delete-data", presence=presence, facts={
            "backup": "failed", "irreversible_listed": True,
            "cap_set": True, "preflight_ok": True})) == "deny"


@pytest.mark.parametrize("protection,want", [
    ("unprotected", "allow"), ("unknown", "ask-routine"),
    (GONE, "ask-routine"), ("", "ask-routine"), (None, "ask-routine"),
    ("protected", "ask-owner")])
def test_unknown_protection_stops_a_force_push(protection, want):
    assert outcome(req("force-push-own-branch",
                       facts={"protection": protection})) == want


def test_a_protected_branch_is_a_human_only_push_whatever_was_asked():
    for op in ("push-own-branch", "force-push-own-branch"):
        for presence in ("attended", "unattended"):
            result = P.decide(planned(op, presence=presence,
                                      facts={"protection": "protected"}))
            assert result["outcome"] == "ask-owner"
            assert result["operation"] == "push-protected-branch"
            assert result["rule"] == "human"


def test_a_plain_push_needs_protection_to_be_known_to_be_absent():
    assert outcome(req("push-own-branch")) == "allow"
    for protection in ("unknown", GONE, False, None):
        assert outcome(req("push-own-branch",
                           facts={"protection": protection})) == "ask-routine"


@pytest.mark.parametrize("tier", [GONE, None, "", "staging", "conflict",
                                  "dev,prod", 0, ["prod"]])
@pytest.mark.parametrize("op", TIERED)
def test_an_unknown_tier_is_never_unattended_and_never_allowed(op, tier):
    attended = outcome(planned(op, tier=tier, attested=True))
    unattended = outcome(planned(op, tier=tier, presence="unattended"))
    assert attended == "ask-owner" and unattended == "deny"


def test_the_decider_cannot_classify_an_unknown_tier_as_dev_or_qa():
    result = P.decide(req("start-deploy", tier="staging"))
    assert result["outcome"] == "ask-owner"
    assert "decider" in result["reason"]


# --- order: first match wins ---------------------------------------------------

def test_the_never_lane_beats_every_later_rule():
    for presence in ("attended", "unattended"):
        for prov in ("plan-of-record", "standing-plan", "none"):
            for op in (k for k, v in P.OPERATIONS.items()
                       if v.lane == P.NEVER):
                result = P.decide(planned(op, presence=presence,
                                          provenance=prov,
                                          emergency=emergency(op)))
                assert (result["outcome"], result["rule"]) == ("deny", "1")


def test_a_never_op_is_denied_even_when_the_machine_layer_is_not_clear():
    result = P.decide(req("invent-status", machine_layer="block"))
    assert (result["outcome"], result["rule"]) == ("deny", "1")


def test_the_machine_layer_beats_the_human_only_list_and_a_plan():
    result = P.decide(req("skip-gate", machine_layer="mismatch"))
    assert result["rule"] == "2"
    result = P.decide(planned("payment", machine_layer="block"))
    assert (result["outcome"], result["rule"]) == ("ask-owner", "2")


def test_an_unknown_tier_beats_the_admin_need_and_the_plan():
    result = P.decide(planned("admin-identity-op", tier="mystery"))
    assert result["rule"] == "3"


def test_the_admin_rule_beats_the_plan_of_record():
    result = P.decide(planned("admin-identity-op", admin_need="none"))
    assert (result["outcome"], result["rule"]) == ("deny", "4")


# --- machine layer, identity, account -----------------------------------------

@pytest.mark.parametrize("op", NOT_NEVER)
def test_nothing_passes_a_machine_layer_that_is_not_clear(op):
    for layer in ("block", "mismatch", "unreadable", "clear-ish", None, 1,
                  GONE):
        for presence in ("attended", "unattended"):
            got = outcome(planned(op, presence=presence, machine_layer=layer))
            assert got == STOP[presence], (op, layer, presence, got)


@pytest.mark.parametrize("op", ACCOUNTED)
def test_the_account_must_be_the_verified_one_for_the_access_level(op):
    spec = P.OPERATIONS[op]
    other = "read" if spec.account == "write" else "write"
    for acct in ("mismatch", "fail", "could-not-tell", "none", other +
                 "-verified", "verified", "", None, GONE):
        for presence in ("attended", "unattended"):
            assert outcome(planned(op, presence=presence,
                                   account=acct)) == STOP[presence]


def test_a_read_is_allowed_in_any_tier_with_a_verified_read_account():
    for op in ("sql-read", "cloud-read"):
        for tier in ("dev", "qa", "prod"):
            for presence in ("attended", "unattended"):
                assert outcome(req(op, tier, presence)) == "allow"


def test_a_read_with_a_write_account_is_not_the_read_rule():
    assert outcome(req("sql-read", "prod", account="write-verified")) == \
        "ask-owner"


# --- admin ---------------------------------------------------------------------

@pytest.mark.parametrize("need", ["none", "other", "", None, GONE, "open",
                                  True])
def test_an_admin_operation_without_a_covering_need_is_denied(need):
    for presence in ("attended", "unattended"):
        assert outcome(planned("admin-identity-op", presence=presence,
                               admin_need=need)) == "deny"


def test_an_open_need_is_a_prerequisite_never_an_allow():
    assert outcome(req("admin-identity-op")) == "needs-plan"
    assert outcome(req("admin-identity-op", provenance="decider-approved-plan",
                       plan_covers=True, attested=True)) == "needs-plan"
    assert outcome(planned("admin-identity-op")) == "allow"


# --- serious ---------------------------------------------------------------------

SERIOUS_OPS = [k for k, v in P.OPERATIONS.items() if v.lane == P.SERIOUS_ALWAYS]


@pytest.mark.parametrize("op", SERIOUS_OPS)
def test_serious_work_with_no_human_approved_plan_needs_a_plan(op):
    for prov in ("none", "record", "decider-approved-plan", "junk", GONE):
        for presence in ("attended", "unattended"):
            got = outcome(req(op, presence=presence, plan_covers=True,
                              attested=True,
                              **({} if prov is GONE else {"provenance": prov})))
            assert got == "needs-plan", (op, prov, presence)


@pytest.mark.parametrize("op", SERIOUS_OPS)
def test_a_standing_plan_never_unlocks_an_exact_only_kind(op):
    assert outcome(req(op, provenance="standing-plan", plan_covers=True,
                       attested=True)) == "needs-plan"


@pytest.mark.parametrize("op", SERIOUS_OPS)
def test_an_attested_plan_that_covers_it_unlocks_it(op):
    assert outcome(planned(op)) == "allow"
    assert outcome(planned(op, presence="unattended")) == "allow"


@pytest.mark.parametrize("covers", [False, None, "yes", 1, "True", GONE])
def test_a_plan_that_is_not_shown_to_cover_the_action_unlocks_nothing(covers):
    assert outcome(planned("payment", plan_covers=covers)) == "needs-plan"


@pytest.mark.parametrize("attested", [False, None, "yes", 1, GONE])
def test_unattended_serious_work_needs_the_attestation(attested):
    assert outcome(planned("payment", presence="unattended",
                           attested=attested)) == "needs-plan"
    assert outcome(planned("payment", presence="attended",
                           attested=attested)) == "allow"


@pytest.mark.parametrize("presence", [GONE, None, "away", "ATTENDED?", 1])
def test_unknown_presence_is_unattended(presence):
    assert outcome(planned("payment", presence=presence,
                           attested=False)) == "needs-plan"
    assert outcome(planned("start-deploy", tier="staging",
                           presence=presence)) == "deny"


PROD_WRITES = ["start-deploy", "terraform-apply", "land-next-tier",
               "delete-data"]


@pytest.mark.parametrize("op", PROD_WRITES)
def test_a_production_write_needs_a_plan_but_dev_and_qa_do_not(op):
    assert P.decide(req(op, "prod"))["serious"] == "production-write"
    for tier in ("dev", "qa"):
        assert outcome(req(op, tier)) == "allow"
    assert outcome(req(op, "prod")) == "needs-plan"
    assert outcome(planned(op, "prod")) == "allow"


@pytest.mark.parametrize("op", ["start-deploy", "terraform-apply"])
def test_a_standing_plan_unlocks_an_envelope_kind_in_production(op):
    assert outcome(planned(op, "prod", provenance="standing-plan")) == "allow"
    assert outcome(planned(op, "prod", provenance="standing-plan",
                           plan_covers=False)) == "needs-plan"


@pytest.mark.parametrize("check", ["fail", "unknown", "", None, True, GONE,
                                   "PASS-ish"])
def test_production_checks_must_pass_at_execution(check):
    for op in PROD_WRITES:
        for presence in ("attended", "unattended"):
            assert outcome(planned(op, "prod", presence=presence,
                                   prodcheck=check)) == STOP[presence]


def test_a_dev_write_does_not_need_production_checks():
    assert outcome(planned("payment", prodcheck="fail")) == "allow"


@pytest.mark.parametrize("facts,cls", [
    ({"permanence": "permanent"}, "permission-change"),
    ({"permanence": "unknown"}, "permission-change"),
    ({"permanence": GONE}, "permission-change"),
    ({"profile": "unlisted"}, "permission-change"),
    ({"profile": GONE}, "permission-change"),
    ({"profile": "unknown"}, "permission-change")])
def test_a_grant_other_than_a_temporary_listed_profile_is_serious(facts, cls):
    result = P.decide(req("grant-permission", facts=facts))
    assert (result["outcome"], result["serious"]) == ("needs-plan", cls)


def test_any_grant_in_production_is_serious():
    result = P.decide(req("grant-permission", "prod"))
    assert (result["outcome"], result["serious"]) == (
        "needs-plan", "permission-change")


def test_a_dev_grant_needs_every_grant_condition():
    assert outcome(req("grant-permission")) == "allow"
    for fact, _ in P.GRANT_FACTS:
        assert outcome(req("grant-permission", presence="unattended",
                           facts={fact: GONE})) == "deny", fact
        assert outcome(req("grant-permission",
                           facts={fact: GONE})) == "ask-routine", fact
        broken = "other" if fact == "ownership" else False
        assert outcome(req("grant-permission",
                           facts={fact: broken})) == "deny", fact


def test_serious_classes_cover_the_closed_list():
    seen = {P.decide(req(op))["serious"] for op in SERIOUS_OPS}
    seen.add(P.decide(req("start-deploy", "prod"))["serious"])
    seen.add(P.decide(req("grant-permission", "prod"))["serious"])
    seen.add(P.decide(req("delete-data", facts={"ownership": "other"}))["serious"])
    seen.add(P.decide(req("delete-data", facts={"backup": "none"}))["serious"])
    assert seen == {"money", "production-write", "permission-change",
                    "account-creation", "admin-use", "destroy-not-owned",
                    "irreversible-or-outside-effect", "no-provable-backup"}


# --- human only and never ----------------------------------------------------------

HUMAN_OPS = [k for k, v in P.OPERATIONS.items() if v.lane == P.HUMAN]
NEVER_OPS = [k for k, v in P.OPERATIONS.items() if v.lane == P.NEVER]


@pytest.mark.parametrize("op", HUMAN_OPS)
def test_a_one_way_operation_is_always_the_owners_and_never_allowed(op):
    for prov in ("plan-of-record", "standing-plan", "decider-approved-plan",
                 "record", "none"):
        for presence in ("attended", "unattended"):
            result = P.decide(planned(op, presence=presence, provenance=prov,
                                      emergency=emergency(op)))
            assert result["outcome"] == "ask-owner", (op, prov, presence)
            assert result["rule"] == "human"


@pytest.mark.parametrize("op", NEVER_OPS)
def test_a_never_operation_is_denied_with_no_request(op):
    for presence in ("attended", "unattended"):
        assert outcome(planned(op, presence=presence)) == "deny"


def test_bypassing_a_guard_is_human_only_when_a_person_approves_never_alone():
    assert outcome(req("bypass-guard-approved-by-person")) == "ask-owner"
    assert outcome(req("bypass-guard-by-agent")) == "deny"


# --- conditional ----------------------------------------------------------------------

COND_BOOL = [(op, name) for op, spec in P.OPERATIONS.items()
             for name, want in spec.facts if isinstance(want, bool)]


@pytest.mark.parametrize("op,name", COND_BOOL)
def test_a_condition_must_be_the_boolean_true_to_count(op, name):
    wanted = dict(P.OPERATIONS[op].facts)[name]
    for junk in ("yes", "true", 1, "", None):
        assert outcome(req(op, facts={name: junk})) == "ask-routine", junk
    assert outcome(req(op, facts={name: not wanted})) == "deny"
    assert outcome(req(op)) == "allow"


def test_a_merge_needs_review_gate_and_a_different_family_approver():
    assert outcome(req("merge-pr")) == "allow"
    for name in ("review_clean", "gate_pass_same_sha",
                 "approver_other_family"):
        assert outcome(req("merge-pr", facts={name: False})) == "deny"


def test_a_terraform_apply_outside_production_is_allowed_and_logged():
    for tier in ("dev", "qa"):
        assert outcome(req("terraform-apply", tier)) == "allow"
    assert outcome(req("terraform-apply", "prod")) == "needs-plan"


def test_an_emergency_waives_only_the_review_loop_and_only_when_scoped():
    waived = req("merge-pr", facts={"review_clean": False},
                 emergency=emergency())
    assert outcome(waived) == "allow"
    for who in ("agent", "model", True, "yes", "", None, "owner",
                "owner-declared", emergency(declared_by="model")):
        assert outcome(req("merge-pr", facts={"review_clean": False},
                           emergency=who)) == "deny", who
    gate = req("merge-pr", facts={"gate_pass_same_sha": False},
               emergency=emergency())
    assert outcome(gate) == "deny"
    assert outcome(req("payment", emergency=emergency("payment"))) == \
        "needs-plan"
    assert outcome(req("invent-status",
                       emergency=emergency("invent-status"))) == "deny"
    assert outcome(req("skip-gate",
                       emergency=emergency("skip-gate"))) == "ask-owner"


# --- mode is not an input ---------------------------------------------------------------

@pytest.mark.parametrize("mode", ["guided", "directive", "junk", None])
def test_the_operating_mode_changes_no_outcome(mode):
    for cid, request, want in CASES:
        got = outcome(dict(request, mode=mode, operating_mode=mode))
        assert got == want, cid


def test_the_module_never_reads_a_mode():
    tree = ast.parse(source())
    keys = {node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert not {k for k in keys if k in ("mode", "operating_mode", "guided",
                                         "directive")}


# --- fail closed, over a grid -------------------------------------------------------------

def test_no_combination_of_inputs_allows_what_the_table_forbids():
    ops = sorted(P.OPERATIONS) + ["mystery"]
    grid = itertools.product(
        ops,
        ("dev", "prod", "mystery"),
        ("attended", "unattended"),
        ("plan-of-record", "standing-plan", "decider-approved-plan", "none"),
        (True, False),
        (True, False),
        ("pass", "fail"),
        (True, False),
        ("clear", "block"))
    checked = 0
    for (op, tier, presence, prov, covers, attested, check, good_acct,
         layer) in grid:
        spec = P.OPERATIONS.get(op)
        wanted = (spec.account + "-verified") if spec and spec.account else ""
        request = {"operation": op, "presence": presence, "tier": tier,
                   "machine_layer": layer, "provenance": prov,
                   "plan_covers": covers, "attested": attested,
                   "prodcheck": check,
                   "admin_need": "covers" if good_acct else "none",
                   "account": wanted if good_acct else "none"}
        result = P.decide(request)
        checked += 1
        if result["outcome"] != "allow":
            continue
        label = (op, tier, presence, prov, covers, attested, check, good_acct,
                 layer)
        assert layer == "clear", label
        assert spec is not None and spec.lane not in (P.NEVER, P.HUMAN), label
        if spec.tiered:
            assert tier in P.TIERS, label
        assert good_acct or not (spec.account or spec.admin), label
        if result["serious"]:
            assert prov in ("plan-of-record", "standing-plan"), label
            assert covers is True, label
            assert presence == "attended" or attested is True, label
            assert tier != "prod" or check == "pass", label
            if prov == "standing-plan":
                assert op in P.ENVELOPE_OPS, label
    assert checked > 20000


# --- explain and the CLI -------------------------------------------------------------------

def test_explain_names_each_rule_looked_at_and_the_outcome():
    text = P.explain(req("start-deploy", "prod"))
    lines = text.splitlines()
    assert lines[0].startswith("rule -: operation 'start-deploy', tier prod")
    assert any(line.startswith("rule 1:") for line in lines)
    assert any(line.startswith("rule 5:") for line in lines)
    assert "=> needs-plan" in text
    assert lines[-2] == "outcome: needs-plan"
    assert "report-only" in lines[-1]


def test_explain_says_why_a_request_stopped_early():
    text = P.explain(req("start-deploy", machine_layer="block"))
    assert "rule 2: machine layer block" in text
    assert "rule 5" not in text


def _cli(*args, stdin=None):
    return subprocess.run([sys.executable, MODULE] + list(args), input=stdin,
                          capture_output=True, text=True, check=False,
                          encoding="utf-8", errors="replace", timeout=60)


def test_the_cli_decides_and_explains_and_lists():
    body = json.dumps(req("commit"))
    done = _cli("decide", body)
    assert done.returncode == 0 and json.loads(done.stdout)["outcome"] == "allow"
    done = _cli("explain", "-", stdin=body)
    assert done.returncode == 0 and "outcome: allow" in done.stdout
    done = _cli("operations")
    assert done.returncode == 0
    assert {line.split("\t")[0] for line in done.stdout.splitlines()} == \
        set(P.OPERATIONS)


@pytest.mark.parametrize("args,stdin", [
    (("decide", "{not json"), None), (("explain", "-"), "nope"),
    (("decide",), None), (("frobnicate", "{}"), None), ((), None)])
def test_the_cli_prints_no_decision_for_a_request_it_cannot_read(args, stdin):
    done = _cli(*args, stdin=stdin)
    assert done.returncode == 2
    assert done.stdout == ""
    assert done.stderr.strip()


# --- inert -----------------------------------------------------------------------------------

def _plugin_sources():
    for root, dirs, files in os.walk(PLUGIN):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__",
                                                "tests", "_test")]
        for name in files:
            if name.endswith((".py", ".sh", ".ps1", ".json")):
                yield os.path.join(root, name)


def test_nothing_in_the_plugin_reaches_the_policy_table_yet():
    me = os.path.normcase(MODULE)
    hits = []
    for path in _plugin_sources():
        if os.path.normcase(path) == me:
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            if "crew_policy" in handle.read():
                hits.append(os.path.relpath(path, PLUGIN))
    assert hits == [], "the table is report-only until its switch-on ticket"


def test_the_module_imports_only_the_standard_library():
    tree = ast.parse(source())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names <= {"__future__", "json", "sys", "typing"}, names


def test_the_module_declares_itself_report_only():
    assert P.REPORT_ONLY is True
    assert "REPORT-ONLY" in source()


def test_the_module_does_nothing_when_imported():
    done = subprocess.run([sys.executable, "-c",
                           "import crew_policy"], cwd=SCRIPTS,
                          capture_output=True, text=True, check=False,
                          encoding="utf-8", errors="replace", timeout=60)
    assert done.returncode == 0 and done.stdout == "" and done.stderr == ""


# --- sabotage: each weakened rule must be caught --------------------------------------------------

MUTATIONS = (
    ("never lane is skipped", "    if spec.lane == NEVER:\n", "    if False:\n"),
    ("a machine layer that is not clear passes", '    if layer != "clear":\n',
     "    if False:\n"),
    ("the account check is dropped",
     '        if account != access + "-verified":\n',
     "        if False:\n"),
    ("a read account passes for a write", 'access + "-verified"',
     '"read-verified"'),
    ("an unknown tier passes", "        if tier == UNKNOWN:\n",
     "        if False:\n"),
    ("the admin need is not required", '        if need != "covers":\n',
     "        if False:\n"),
    ("a plan that does not cover is enough",
     "    if not (usable and covers):\n", "    if not usable:\n"),
    ("no plan is needed", "    if not (usable and covers):\n",
     "    if False:\n"),
    ("a decider-approved plan unlocks serious work",
     '    if prov == "plan-of-record":\n',
     '    if prov in ("plan-of-record", "decider-approved-plan"):\n'),
    ("a bare record unlocks serious work",
     '    if prov == "plan-of-record":\n',
     '    if prov in ("plan-of-record", "record"):\n'),
    ("a standing plan unlocks an exact-only kind",
     "usable = serious == PRODUCTION_WRITE and name in ENVELOPE_OPS",
     "usable = True"),
    ("a plan of record unlocks an operation the schema does not know",
     "    if serious == UNPLACED:\n", "    if False:\n"),
    ("the attestation is not required unattended",
     "    if not attended and not attested:\n", "    if False:\n"),
    ("the production checks are not required",
     '        if check != "pass":\n', "        if False:\n"),
    ("an unplaced operation is not serious",
     "Op(SERIOUS_ALWAYS, tiered=True,\n                                      serious=UNPLACED)", "Op(FREE)"),
    ("a protected branch is not human-only",
     '_fact(facts, "protection",\n                                        "protected") == "met"', "False"),
    ("a destroy of data not shown to be owned is not serious",
     '        if _fact(facts, "ownership", "own") != "met":\n',
     "        if False:\n"),
    ("a destroy without a provable backup is not serious",
     '        if not (isinstance(backup, str)\n'
     '                and backup.strip().lower() == "provable"):\n',
     "        if False:\n"),
    ("a grant in production is not serious",
     '        if tier == "prod" or permanence != "met" or profile != "met":\n',
     '        if permanence != "met" or profile != "met":\n'),
    ("a condition that cannot be shown is allowed",
     "    if unknown:\n        return done(\"8\", ASK_ROUTINE,",
     "    if False:\n        return done(\"8\", ASK_ROUTINE,"),
    ("a condition that is false is allowed",
     "    if bad:\n        return done(\"8\", DENY,",
     "    if False:\n        return done(\"8\", DENY,"),
    ("the one-way list is allowed", '    if spec.lane == HUMAN:\n',
     '    if False:\n'),
    ("any emergency waives the review",
     'if name == "merge-pr" and _emergency(req, name):',
     'if name == "merge-pr" and req.get("emergency"):'),
    ("an emergency for another action waives the review",
     '            and emerg.get("action") == name\n', ''),
    ("a grant that makes an admin account is allowed",
     '        if admin == "violated":\n', '        if False:\n'),
    ("a failed backup is excused by a plan",
     '    if isinstance(backup, str) and backup.strip().lower() == "failed":\n',
     '    if False:\n'),
    ("an irreversible action runs with no listing",
     '        if listed != ("met", "met"):\n', '        if False:\n'),
    ("a failed preflight does not refuse",
     '        if _fact(facts, "preflight_ok", True) != "met":\n',
     '        if False:\n'),
    ("the lane's own conditions are dropped under a plan",
     '    if lane_facts:\n        verdicts, bad, unknown = _verdicts(lane_facts, facts)',
     '    if False:\n        verdicts, bad, unknown = _verdicts(lane_facts, facts)'),
    ("an emergency for another target waives the review",
     '            and emerg.get("target") == target\n', ''),
    ("an account that does not check out passes when none is required",
     '        if other in ("mismatch", "fail", "could-not-tell"):\n',
     '        if False:\n'),
    ("a production deletion drops the stricter classes",
     "    if spec.lane == DESTRUCTIVE:\n        # The stricter classes win",
     '    if spec.lane == DESTRUCTIVE and tier == "prod":\n'
     "        return PRODUCTION_WRITE\n"
     "    if spec.lane == DESTRUCTIVE:\n        # The stricter classes win"),
    ("unknown permanence drops the expiry facts",
     '    if _fact(facts, "permanence", "permanent") == "met":\n',
     '    if _fact(facts, "permanence", "temporary") != "met":\n'),
    ("a production grant needs no write account",
     'else None)\n    if access:', 'else None)\n    if spec.account:'),
    ("a QA deletion needs no ticket note",
     '    if spec.lane == DESTRUCTIVE and tier == "qa":\n',
     '    if False:\n'),
    ("a grant's expiry facts are not required for a temporary grant",
     '    return list(GRANT_FACTS)\n', '    return []\n'),
    ("an unattended grant that cannot be proved only asks",
     '    if unknown and spec.lane == GRANT and not attended:\n',
     '    if False:\n'),
    ("the tier landing may use a standing plan",
     'ENVELOPE_OPS = frozenset({"start-deploy", "terraform-apply"})',
     'ENVELOPE_OPS = frozenset({"start-deploy", "terraform-apply", "land-next-tier"})'),
    ("a credential store may be read",
     '_NOT_A_SECRET_STORE = (("credential_store", False),)',
     '_NOT_A_SECRET_STORE = ()'),
    ("creating an account needs no admin need",
     '    "create-account": Op(SERIOUS_ALWAYS, tiered=True, admin=True,',
     '    "create-account": Op(SERIOUS_ALWAYS, tiered=True, admin=False,'),
    ("a truthy fact counts as met", "        if isinstance(seen, bool):\n",
     "        if True:\n"),
    ("unknown presence is attended",
     'attended = _pick(req.get("presence"), PRESENCE) == "attended"',
     'attended = _pick(req.get("presence"), PRESENCE) != "unattended"'),
    ("the machine layer is read as clear when missing",
     'layer = _pick(req.get("machine_layer"), MACHINE_LAYER)',
     'layer = _pick(req.get("machine_layer"), MACHINE_LAYER + (UNKNOWN,))'
     ' if req.get("machine_layer") else "clear"'),
)


def _variant(old, new):
    text = source()
    assert text.count(old) == 1, f"mutation target moved: {old!r}"
    name = "crew_policy_mutant"
    module = types.ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(text.replace(old, new), name, "exec"),  # pylint: disable=exec-used
             module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.mark.parametrize("label,old,new", MUTATIONS,
                         ids=[m[0] for m in MUTATIONS])
def test_a_weakened_rule_is_caught(label, old, new):
    bad = violations(_variant(old, new))
    assert bad, "nothing caught: " + label
