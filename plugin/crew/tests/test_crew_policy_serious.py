"""`crew_policy.classify`: the serious classifier, REPORT-ONLY (plan 4.13, R-P6).

The classifier places one action's *effects* into the closed serious list.
Every question is required, an answer it cannot read is the serious one, an
effect it has no question for is UNPLACED, and money is a real comparison of
a USD monthly estimate with the threshold (4.5, "Money"; default 50 USD a
month, plan section 8).

Three kinds of test:

* the classifier: a must-be-serious case per class (and for unplaced), the
  admin and empty-object paths through `decide`, and must-allow cases;
* parity with R-01: without `effects` nothing changes; with benign effects
  only the D9 rows change, and only to the answer the fact
  `estimate_under_threshold` True already gives; a serious answer never
  turns a non-allow into an allow;
* sabotage: `MUTATIONS` weaken the classifier one way each, and every copy
  must fail one of the `CHECKS` (the same in-file mechanism as R-01's).
"""
import contextlib
import copy
import decimal
import hashlib
import io
import json
import subprocess
import sys
from decimal import Decimal

import pytest

import context  # noqa: F401  pylint: disable=unused-import

import crew_policy as P  # noqa: E402  pylint: disable=wrong-import-position
import test_crew_policy as T  # noqa: E402  pylint: disable=wrong-import-position

GONE = T.GONE
NAN = float("nan")
INF = float("inf")


def usd(amount, currency="USD", period="month"):
    """A monthly cost estimate."""
    return {"amount": amount, "currency": currency, "period": period}


BENIGN = {"spends": False, "monthly_cost": usd(0), "writes": False,
          "permission_change": "none", "creates_account": False,
          "admin_use": "none", "destroys": "none", "reversible": True,
          "outside_effect": False, "backup": "provable"}


def fx(**over):
    """Benign effects with some answers changed (GONE removes the key)."""
    out = dict(BENIGN)
    for key, val in over.items():
        if val is GONE:
            out.pop(key, None)
        else:
            out[key] = val
    return out


def ask(effects, tier="dev", op="commit", presence="attended", **top):
    """A `decide` request for `effects` that reaches rule 5 when serious.

    Base: `commit` (free lane, no account of its own), machine layer clear, no
    plan. An admin class gets admin_need covers and account none; otherwise
    prod gets the write account (a class in prod asks for it) and dev or QA
    gets account none. The setup is computed with the real classifier, so a
    sabotaged copy is asked the same question."""
    out = {"operation": op, "tier": tier, "presence": presence,
           "machine_layer": "clear", "target": "repo", "effects": effects}
    found = set(P.classify(effects, tier)["classes"])
    if found & {P.ADMIN_USE, P.ACCOUNT_CREATION}:
        out.update(admin_need="covers", account="none")
    elif tier == "prod":
        out["account"] = "write-verified"
    else:
        out["account"] = "none"
    for key, val in top.items():
        if val is GONE:
            out.pop(key, None)
        else:
            out[key] = val
    return out


def brief(result):
    """(outcome, rule, serious) of one decision."""
    return (result["outcome"], result["rule"], result["serious"])


# --- must be serious: (id, effects, tier, classes, primary, through decide) --
#
# Unless a case says otherwise, every other answer is benign.

SERIOUS_CASES = [
    ("money: spends True", fx(spends=True), "dev", [P.MONEY], True),
    ("money: spends missing", fx(spends=GONE), "dev", [P.MONEY], True),
    ("money: 50.01 USD a month", fx(monthly_cost=usd(50.01)), "dev", [P.MONEY], True),
    ("money: amount missing", fx(monthly_cost={"currency": "USD", "period": "month"}),
     "dev", [P.MONEY], True),
    ("money: amount a string", fx(monthly_cost=usd("10")), "dev", [P.MONEY], True),
    ("money: amount a bool", fx(monthly_cost=usd(True)), "dev", [P.MONEY], True),
    ("money: amount NaN", fx(monthly_cost=usd(NAN)), "dev", [P.MONEY], True),
    ("money: amount inf", fx(monthly_cost=usd(INF)), "dev", [P.MONEY], True),
    ("money: amount negative", fx(monthly_cost=usd(-5)), "dev", [P.MONEY], True),
    ("money: EUR", fx(monthly_cost=usd(10, currency="EUR")), "dev", [P.MONEY], True),
    ("money: period year", fx(monthly_cost=usd(10, period="year")), "dev", [P.MONEY], True),
    ("money: monthly_cost absent", fx(monthly_cost=GONE), "dev", [P.MONEY], True),
    ("money: monthly_cost not an object", fx(monthly_cost=10), "dev", [P.MONEY], True),
    ("money: an estimate with an extra key", fx(monthly_cost=dict(usd(10), extra=True)),
     "dev", [P.MONEY], True),
    ("production-write: writes True in prod", fx(writes=True), "prod",
     [P.PRODUCTION_WRITE], True),
    ("production-write: writes missing in prod", fx(writes=GONE), "prod",
     [P.PRODUCTION_WRITE], True),
    # D3: only a known False is benign; an unreadable answer is a production
    # write whatever the tier (True stays tied to the tier, see MUST_ALLOW).
    ("production-write: writes missing in dev", fx(writes=GONE), "dev",
     [P.PRODUCTION_WRITE], True),
    ("production-write: writes missing in qa", fx(writes=GONE), "qa",
     [P.PRODUCTION_WRITE], True),
    ("production-write: writes 'yes' in dev", fx(writes="yes"), "dev",
     [P.PRODUCTION_WRITE], True),
    ("production-write: writes null in qa", fx(writes=None), "qa",
     [P.PRODUCTION_WRITE], True),
    ("production-write: writes 1 in qa", fx(writes=1), "qa",
     [P.PRODUCTION_WRITE], True),
    # decide stops an unknown tier at rule 3, so classify only (D4).
    ("production-write: writes True, tier staging", fx(writes=True), "staging",
     [P.PRODUCTION_WRITE], False),
    ("permission-change: permanent in dev", fx(permission_change="permanent"), "dev",
     [P.PERMISSION_CHANGE], True),
    ("permission-change: temporary-listed in prod",
     fx(permission_change="temporary-listed"), "prod", [P.PERMISSION_CHANGE], True),
    ("permission-change: temporary-unlisted in dev",
     fx(permission_change="temporary-unlisted"), "dev", [P.PERMISSION_CHANGE], True),
    ("permission-change: invalid value", fx(permission_change="a-little"), "dev",
     [P.PERMISSION_CHANGE], True),
    ("permission-change: missing", fx(permission_change=GONE), "dev",
     [P.PERMISSION_CHANGE], True),
    ("account-creation: True", fx(creates_account=True), "dev", [P.ACCOUNT_CREATION], True),
    ("account-creation: missing", fx(creates_account=GONE), "dev",
     [P.ACCOUNT_CREATION], True),
    ("account-creation: 'yes' is not a bool", fx(creates_account="yes"), "dev",
     [P.ACCOUNT_CREATION], True),
    ("admin-use: other in dev", fx(admin_use="other"), "dev", [P.ADMIN_USE], True),
    ("admin-use: grantable-profile-temporary in prod",
     fx(admin_use="grantable-profile-temporary"), "prod", [P.ADMIN_USE], True),
    ("admin-use: missing", fx(admin_use=GONE), "dev", [P.ADMIN_USE], True),
    ("destroy-not-owned: not-own", fx(destroys="not-own"), "dev",
     [P.DESTROY_NOT_OWNED], True),
    ("destroy-not-owned: missing", fx(destroys=GONE), "dev", [P.DESTROY_NOT_OWNED], True),
    ("irreversible: reversible False", fx(reversible=False), "dev", [P.IRREVERSIBLE], True),
    ("irreversible: outside_effect True", fx(outside_effect=True), "dev",
     [P.IRREVERSIBLE], True),
    ("irreversible: reversible missing", fx(reversible=GONE), "dev", [P.IRREVERSIBLE], True),
    ("irreversible: outside_effect missing", fx(outside_effect=GONE), "dev",
     [P.IRREVERSIBLE], True),
    ("no-provable-backup: none", fx(backup="none"), "dev", [P.NO_PROVABLE_BACKUP], True),
    ("no-provable-backup: missing", fx(backup=GONE), "dev", [P.NO_PROVABLE_BACKUP], True),
    ("no-provable-backup: not normalisable to a listed value",
     fx(backup="provable-ish"), "dev", [P.NO_PROVABLE_BACKUP], True),
    ("unplaced: an unknown effect key", fx(sends_email=True), "dev", [P.UNPLACED], True),
    ("unplaced: effects null", None, "dev", [P.UNPLACED], True),
    ("unplaced: effects a list", [], "dev", [P.UNPLACED], True),
    ("unplaced: effects a string", "writes", "dev", [P.UNPLACED], True),
    ("several: the strictest is reported, all are listed",
     fx(spends=True, destroys="not-own", writes=True), "prod",
     sorted([P.DESTROY_NOT_OWNED, P.MONEY, P.PRODUCTION_WRITE]), True),
]
SERIOUS_PRIMARY = {"several: the strictest is reported, all are listed": P.DESTROY_NOT_OWNED}


def _primary_of(cid, classes):
    return SERIOUS_PRIMARY.get(cid, classes[0])


# --- must allow: (id, decide request without effects, effects, tier) --------

MUST_ALLOW = [
    ("a dev delete-data of own data with a provable backup",
     T.req("delete-data"), fx(destroys="own", backup="provable"), "dev"),
    ("monthly_cost 0 USD", T.req("commit"), fx(monthly_cost=usd(0)), "dev"),
    ("monthly_cost exactly 50.00 USD is not over", T.req("commit"),
     fx(monthly_cost=usd(50.00)), "dev"),
    ("an integer amount and lower-case currency", T.req("commit"),
     fx(monthly_cost=usd(12, currency=" usd ", period="Month")), "dev"),
    ("temporary-listed in dev", T.req("commit"),
     fx(permission_change="temporary-listed"), "dev"),
    ("grantable-profile-temporary in QA", T.req("commit", tier="qa"),
     fx(admin_use="grantable-profile-temporary"), "qa"),
    ("backup no-state-change", T.req("commit"), fx(backup="no-state-change"), "dev"),
    # The reading: "Provable " is read with _pick's strip and lower-case
    # rule, so it is the listed value "provable" and is not serious.
    ("backup 'Provable ' read as provable", T.req("commit"), fx(backup="Provable "), "dev"),
    ("writes True in dev", T.req("commit"), fx(writes=True), "dev"),
    ("writes True in QA", T.req("commit", tier="qa"), fx(writes=True), "qa"),
]

D9_LINE = "stands in for facts.estimate_under_threshold"


def _tf(tier, fact=GONE, cost=None, **top):
    """A terraform-apply that satisfies its own conditions, with effects."""
    return T.req("terraform-apply", tier, facts={"estimate_under_threshold": fact},
                 effects=fx(monthly_cost=cost if cost is not None else usd(10)), **top)


# --- the checks: each returns the failures it found in `m` -------------------

def check_serious_cases(m):
    """Each must-be-serious case, through classify and decide."""
    bad = []
    for cid, effects, tier, want, via_decide in SERIOUS_CASES:
        primary = _primary_of(cid, want)
        got = m.classify(effects, tier)
        if got["classes"] != want or got["primary"] != primary:
            bad.append(f"{cid}: classify gave {got['classes']} / {got['primary']}")
        if got["placed"] != (P.UNPLACED not in got["classes"]):
            bad.append(f"{cid}: placed is {got['placed']}")
        if set(got["reasons"]) != set(got["classes"]):
            bad.append(f"{cid}: reasons {sorted(got['reasons'])}")
        if via_decide:
            done = brief(m.decide(ask(effects, tier)))
            if done != ("needs-plan", "5", primary):
                bad.append(f"{cid}: decide gave {done}")
    for presence in ("attended", "unattended"):
        done = brief(m.decide({"operation": "mystery", "tier": "dev", "presence": presence,
                               "machine_layer": "clear", "account": "none"}))
        if done != ("needs-plan", "5", P.UNPLACED):
            bad.append(f"an unknown operation with no effects: {done}")
    return bad


def check_admin_and_empty_paths(m):
    """D3 with needs_admin: an empty object is an admin operation."""
    bad = []
    for presence, stop in (("attended", "ask-owner"), ("unattended", "deny")):
        base = {"operation": "commit", "tier": "dev", "presence": presence,
                "machine_layer": "clear", "target": "repo", "effects": {}}
        done = brief(m.decide(dict(base, account="none")))
        if done[:2] != ("deny", "4"):
            bad.append(f"empty effects, no admin need, {presence}: {done}")
        done = brief(m.decide(dict(base, account="write-verified")))
        if done[:2] != (stop, "2"):
            bad.append(f"empty effects, write account, {presence}: {done}")
        done = brief(m.decide(dict(base, account="none", admin_need="covers")))
        if done != ("needs-plan", "5", P.NO_PROVABLE_BACKUP):
            bad.append(f"empty effects, admin need covers, {presence}: {done}")
    # An empty object answers nothing, so every class but unplaced applies in
    # every tier: a missing `writes` is a production write in dev too (D3).
    want = {"dev": sorted(P.SERIOUS_CLASSES), "qa": sorted(P.SERIOUS_CLASSES),
            "prod": sorted(P.SERIOUS_CLASSES)}
    for tier, classes in want.items():
        got = m.classify({}, tier)
        if got["classes"] != classes or got["primary"] != P.NO_PROVABLE_BACKUP:
            bad.append(f"classify({{}}, {tier}): {got['classes']} / {got['primary']}")
        if got["cost"] != "cannot-estimate" or not got["placed"]:
            bad.append(f"classify({{}}, {tier}): cost {got['cost']}, placed {got['placed']}")
    partial = fx(destroys=GONE)
    done = brief(m.decide({"operation": "commit", "tier": "dev", "presence": "attended",
                           "machine_layer": "clear", "account": "none",
                           "effects": partial}))
    if done != ("needs-plan", "5", P.DESTROY_NOT_OWNED):
        bad.append(f"partial object without destroys: {done}")
    # An admin effect adds the broker's account rule (4.14) to the row's own;
    # it does not replace it. A dev cloud-read with no account stops at rule
    # 2 with or without the effect, even with a covering, attested plan.
    read = {"operation": "cloud-read", "tier": "dev", "presence": "attended",
            "machine_layer": "clear", "account": "none", "admin_need": "covers"}
    for plan in ({}, COVERING_PLAN):
        if brief(P.decide(dict(read, **plan)))[:2] != ("ask-owner", "2"):
            bad.append(f"cloud-read without effects moved: {brief(P.decide(read))}")
        done = brief(m.decide(dict(read, effects=fx(admin_use="other"), **plan)))
        if done[:2] != ("ask-owner", "2"):
            bad.append(f"cloud-read with admin-use effects, plan {bool(plan)}: {done}")
    return bad


COVERING_PLAN = {"provenance": "plan-of-record", "plan_covers": True, "attested": True}


def check_effects_never_swap_the_account(m):
    """Effects only add requirements: with a covering, attested plan (the one
    place rule 5 can allow), no single serious answer turns a request that is
    not allowed with benign effects into an allow, in any tier, for any
    account answer, for every operation in the table."""
    bad = []
    covered = dict(COVERING_PLAN, presence="attended", machine_layer="clear",
                   admin_need="covers", prodcheck="pass", target="repo")
    for op in sorted(P.OPERATIONS):
        for tier in ("dev", "qa", "prod"):
            for account in P.ACCOUNTS:
                request = dict(covered, operation=op, tier=tier, account=account)
                baseline = m.decide(dict(request, effects=BENIGN))["outcome"]
                if baseline == "allow":
                    continue
                for key, value in SINGLE_SERIOUS:
                    done = m.decide(dict(request, effects=fx(**{key: value})))
                    if done["outcome"] == "allow":
                        bad.append(f"{op} {tier} account {account}: {key}={value!r} "
                                   f"allowed ({done['serious']})")
    return bad


def check_must_allow(m):
    """Benign answers add no class and change no decision."""
    bad = []
    for cid, request, effects, tier in MUST_ALLOW:
        got = m.classify(effects, tier)
        if (got["classes"], got["primary"], got["placed"], got["cost"]) != \
                ([], None, True, "under"):
            bad.append(f"{cid}: classify gave {got}")
        plain = brief(P.decide(request))
        done = brief(m.decide(dict(request, effects=effects)))
        if done != plain or plain[0] != "allow":
            bad.append(f"{cid}: decide gave {done}, without effects {plain}")
    return bad


def check_union_with_own_class(m):
    """Effects add classes; they never remove the operation's own."""
    bad = []
    for op, tier in (("payment", "dev"), ("delete-data", "dev"),
                     ("start-deploy", "prod")):
        facts = {"ownership": "theirs"} if op == "delete-data" else None
        request = T.req(op, tier, facts=facts)
        plain = brief(P.decide(request))
        done = brief(m.decide(dict(request, effects=BENIGN)))
        if done != plain or plain[0] == "allow":
            bad.append(f"{op} {tier}: with benign effects {done}, without {plain}")
    return bad


def check_d9(m):
    """The one way effects lower an outcome, and its limits."""
    bad = []
    for tier in ("dev", "qa", "prod"):
        want = brief(P.decide(T.req("terraform-apply", tier)))
        for fact in (GONE, None, "yes", "unknown"):
            request = _tf(tier, fact)
            snapshot = copy.deepcopy(request)
            done = m.decide(request)
            if brief(done) != want:
                bad.append(f"D9 {tier} fact {fact!r}: {brief(done)}, want {want}")
            if D9_LINE not in "\n".join(done["trace"]):
                bad.append(f"D9 {tier} fact {fact!r}: no trace line")
            if request != snapshot:
                bad.append(f"D9 {tier}: the caller's request was changed")
    if want != ("needs-plan", "5", P.PRODUCTION_WRITE):
        bad.append(f"the R-01 estimate-True answer in prod moved: {want}")
    for tier in ("dev", "qa"):
        if brief(P.decide(T.req("terraform-apply", tier)))[:2] != ("allow", "8"):
            bad.append(f"the R-01 estimate-True answer in {tier} moved")
        done = m.decide(_tf(tier, False))
        if brief(done) != ("needs-plan", "5", P.MONEY):
            bad.append(f"D9 {tier}: an explicit False fact was overridden: {brief(done)}")
        for label, cost in (("60 USD", usd(60)), ("EUR", usd(10, currency="EUR")),
                            ("an extra key", dict(usd(10), extra=True))):
            done = m.decide(_tf(tier, GONE, cost))
            if brief(done) != ("needs-plan", "5", P.MONEY):
                bad.append(f"D9 {tier} {label}: {brief(done)}")
            if D9_LINE in "\n".join(done["trace"]):
                bad.append(f"D9 {tier} {label}: the estimate stood in for the fact")
    return bad


def check_threshold(m):
    """D5, D6 and D7."""
    bad = []
    if m.classify(fx(monthly_cost=usd(60)), "dev", threshold=100)["classes"]:
        bad.append("threshold 100 did not let 60 USD pass")
    for threshold in (-1, "100", True, NAN, INF, [100]):
        got = m.classify(fx(monthly_cost=usd(0.01)), "dev", threshold=threshold)
        if got["classes"] != [P.MONEY]:
            bad.append(f"invalid threshold {threshold!r} widened: {got['classes']}")
    if m.classify(fx(monthly_cost=usd(50)), "dev")["classes"]:
        bad.append("the default threshold is not 50")
    if m.classify(fx(monthly_cost=usd(50.01)), "dev")["classes"] != [P.MONEY]:
        bad.append("the default threshold is not 50 (strictly over)")
    # The reason names the threshold applied, not the rejected one given.
    said = m.classify(fx(monthly_cost=usd(1)), "dev", threshold="100")["reasons"]
    if "threshold 0 USD" not in said.get(P.MONEY, "") or "threshold '100' USD" in said.get(P.MONEY, ""):
        bad.append(f"an invalid threshold is named as applied: {said}")
    said = m.classify(fx(monthly_cost=usd(60)), "dev")["reasons"].get(P.MONEY, "")
    if "threshold 50 USD a month)" not in said:
        bad.append(f"the default threshold is not named: {said}")
    for field in ("threshold", "costThreshold"):
        request = ask(fx(monthly_cost=usd(60)), **{field: 100})
        done = brief(m.decide(request))
        if done != ("needs-plan", "5", P.MONEY):
            bad.append(f"request field {field} raised the threshold: {done}")
    return bad


def check_presence_not_value(m):
    """D8: the key's presence, not its value, turns the classifier on."""
    bad = []
    for value in (None, [], "", 0, False):
        done = brief(m.decide(ask(value)))
        if done != ("needs-plan", "5", P.UNPLACED):
            bad.append(f"effects {value!r}: {done}")
    return bad


def _main_out(m, body, verb="classify"):
    """(exit code, stdout) of the CLI; a crash is code None and its repr."""
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = m._main(["crew_policy.py", verb, body])  # pylint: disable=protected-access
    except (ArithmeticError, ValueError, TypeError) as exc:   # decimal.InvalidOperation
        return None, repr(exc)
    return code, out.getvalue()


def check_cli_reads_the_tier(m):
    """The classify verb reads the request's tier (D4, D11)."""
    bad = []
    for tier, want in (("prod", ["production-write"]), ("dev", []),
                       ("staging", ["production-write"]), (GONE, ["production-write"])):
        request = {"operation": "commit", "tier": tier, "effects": fx(writes=True)}
        if tier is GONE:
            request.pop("tier")
        code, out = _main_out(m, json.dumps(request))
        if code != 0 or json.loads(out)["classes"] != want:
            bad.append(f"classify CLI tier {tier!r}: {code} {out.strip()[:80]}")
    return bad


def check_cli_reads_fractions_exactly(m):
    """A JSON fraction a hair over the threshold is not rounded down to it."""
    bad = []
    for raw, want, cost in CLI_AMOUNTS:
        body = json.dumps({"operation": "commit", "tier": "dev",
                           "effects": fx(monthly_cost=usd(0))})
        body = body.replace('"amount": 0', '"amount": ' + raw)
        # The reader's answer must not depend on the caller's decimal
        # context: with InvalidOperation untrapped Decimal(text) returns NaN
        # where it would raise, and an in-process caller may have set that.
        for name, traps in CONTEXTS:
            with decimal.localcontext(traps):
                code, out = _main_out(m, body)
            if code != 0 or (json.loads(out)["classes"],
                             json.loads(out)["cost"]) != (want, cost):
                bad.append(f"classify CLI amount {raw[:40]}{name}: {code} {out.strip()[:80]}")
    # D9 end to end: a negative amount too small for a Decimal must not stand
    # in for the fact (it did, read as -0.0 and so as a cost under the
    # threshold), where the same request with amount 10 is allowed.
    # A zero no Decimal can hold is still zero: it stands in like any other.
    for raw, want in (("10", "allow"), ("-" + TINY, "needs-plan"), ("-" + ZERO, "allow"),
                      (ZERO, "allow")):
        body = json.dumps(_tf("qa")).replace('"amount": 10', '"amount": ' + raw)
        for name, traps in CONTEXTS:
            with decimal.localcontext(traps):
                code, out = _main_out(m, body, "decide")
            if code != 0 or json.loads(out)["outcome"] != want:
                bad.append(f"decide CLI D9 amount {raw}{name}: {code} {out.strip()[:80]}")
    # A number no Decimal can hold is still valid JSON: a decide request
    # without effects that carries one in an unused field is answered as
    # if the field were not there (origin/main answers it allow).
    plain = {"operation": "commit", "tier": "dev", "presence": "attended",
             "machine_layer": "clear", "account": "none"}
    code, out = _main_out(m, json.dumps(plain)[:-1] + ', "unused": ' + HUGE + "}", "decide")
    if code != 0 or json.loads(out)["outcome"] != "allow":
        bad.append(f"decide CLI with an unused {HUGE}: {code} {out.strip()[:80]}")
    return bad


HUGE = "1e9999999999999999999999999999999999"
TINY = "1e-9999999999999999999999999999999999"
LONG = "9" * 5000   # more digits than int() converts by default (4300)
ZERO = "0e99999999999999999999"   # exactly zero, with an exponent no Decimal holds

# (the JSON text of the amount, classes, cost) through the classify CLI.
CLI_AMOUNTS = (
    ("50.000000000000001", ["money"], "over"), ("50.0", [], "under"),
    ("49.99", [], "under"), ("50.01", ["money"], "over"), ("1e999", ["money"], "over"),
    # A positive amount no Decimal can hold is still a finite number over the
    # threshold: over, not cannot-estimate (D5). Only the class is the same.
    (HUGE, ["money"], "over"), ("1e99999999999999999999", ["money"], "over"),
    ("0.001E+99999999999999999999", ["money"], "over"),
    ("-" + HUGE, ["money"], "cannot-estimate"),
    (TINY, [], "under"),
    # Below zero, however small: float reads it as -0.0, which is not < 0.
    ("-" + TINY, ["money"], "cannot-estimate"),
    ("-1e-400", ["money"], "cannot-estimate"), ("-0.01", ["money"], "cannot-estimate"),
    ("-1", ["money"], "cannot-estimate"),
    # Zero written with a sign is zero, not a negative amount.
    ("-0.0", [], "under"), ("-0", [], "under"),
    # ... whatever its exponent: the reader's fallback must not see the sign
    # alone and call an exact zero a negative amount.
    (ZERO, [], "under"), ("-" + ZERO, [], "under"),
    ("-0.000E+99999999999999999999", [], "under"),
    ("-0.001e-99999999999999999999", ["money"], "cannot-estimate"),
    (LONG, ["money"], "over"), ("-" + LONG, ["money"], "cannot-estimate"),
)

ALL_TRAPS = decimal.Context(traps=[
    decimal.Clamped, decimal.DivisionByZero, decimal.Inexact, decimal.InvalidOperation,
    decimal.Overflow, decimal.Rounded, decimal.Subnormal, decimal.Underflow,
    decimal.FloatOperation])

# (label, context) the CLI reader is asked in: the caller's own, every trap
# set, and no trap set.
CONTEXTS = (("", None), (" with every trap set", ALL_TRAPS),
            (" with no trap set", decimal.Context(traps=[])))

# (amount, cost) through classify, at the default threshold.
COST_VALUES = (
    (0, "under"), (50, "under"), (51, "over"), (10 ** 5000, "over"),
    (INF, "cannot-estimate"), (-INF, "cannot-estimate"), (NAN, "cannot-estimate"),
    (-5, "cannot-estimate"), (-0.5, "cannot-estimate"),
    (Decimal("50"), "under"), (Decimal("50.000000000000001"), "over"),
    (Decimal("1e1000000"), "over"), (Decimal("1e-1000000"), "under"),
    (Decimal("-1e-1000000"), "cannot-estimate"), (Decimal("-1"), "cannot-estimate"),
    (Decimal("Infinity"), "cannot-estimate"), (Decimal("-Infinity"), "cannot-estimate"),
    (Decimal("NaN"), "cannot-estimate"), (Decimal("sNaN"), "cannot-estimate"),
)


def _label(amount):
    """An amount for a failure line; str() of 10 ** 5000 is itself refused."""
    if isinstance(amount, int):
        return f"int of {amount.bit_length()} bits" if abs(amount) > 10 ** 9 else str(amount)
    return repr(amount)


def check_cost_values(m):
    """The cost answer itself, not only the money class: an amount that is
    not a finite number >= 0 cannot be estimated, it is never `over` (D5).
    Each amount is asked twice, the second time with every decimal trap set:
    the answer must not depend on the caller's decimal context."""
    bad = []
    for amount, want in COST_VALUES:
        for traps in (None, ALL_TRAPS):
            try:
                with decimal.localcontext(traps):
                    got = m.classify(fx(monthly_cost=usd(amount)), "dev")["cost"]
            except ArithmeticError as exc:
                got = repr(exc)
            if got != want:
                bad.append(f"amount {_label(amount)}"
                           f"{' with every trap set' if traps else ''}: {got}")
    return bad


# (amount, threshold, cost): a Decimal beside a float, either way round. A
# float 0.1 is 0.1000000000000000055511..., so the comparison must be exact.
MIXED_VALUES = (
    (Decimal(10), 50.0, "under"), (Decimal("50.5"), 50.0, "over"),
    (Decimal("50"), 50.0, "under"), (10.5, Decimal(50), "under"),
    (60.0, Decimal(50), "over"), (50.0, Decimal(50), "under"),
    (Decimal("0.1"), 0.1, "under"), (Decimal("0.1000000000000000056"), 0.1, "over"),
    (0.1, Decimal("0.1"), "over"), (0.1, Decimal("0.1000000000000000056"), "under"),
    (Decimal("1e1000000"), 50.0, "over"), (1e308, Decimal("1e1000000"), "under"),
)


def check_mixed_number_types(m):
    """A Decimal amount against a float threshold (and the reverse) is
    answered exactly, with every decimal trap set too: FloatOperation, when
    trapped, refuses the direct comparison."""
    bad = []
    for amount, threshold, want in MIXED_VALUES:
        for traps in (None, ALL_TRAPS):
            try:
                with decimal.localcontext(traps):
                    got = m.classify(fx(monthly_cost=usd(amount)), "dev", threshold)["cost"]
            except ArithmeticError as exc:
                got = repr(exc)
            if got != want:
                bad.append(f"amount {amount!r} against threshold {threshold!r}"
                           f"{' with every trap set' if traps else ''}: {got}")
    return bad


BIG = 10 ** 5000   # str() and repr() of it are refused (over 4300 digits)


class Unprintable:
    """A threshold whose str() raises something other than ValueError."""

    def __str__(self):
        raise RuntimeError("no text for this value")

# (estimate, threshold, classes, cost, text the money reason must hold).
BIG_THRESHOLDS = (
    (GONE, BIG, ["money"], "cannot-estimate", "integer of 16610 bits"),
    (60, BIG, [], "under", None),
    (60.5, BIG, [], "under", None),
    (Decimal("1e1000000"), BIG, ["money"], "over", "integer of 16610 bits"),
    (60, -BIG, ["money"], "over", "threshold 0 USD a month; the given threshold a negative "
                                  "integer of 16610 bits"),
    (0, -BIG, [], "under", None),
    # A container holding such an int is not a number: 0 applies (D6), and
    # the reason describes it, where str() of it is refused too.
    (60, [BIG], ["money"], "over", "threshold 0 USD a month; the given threshold a value "
                                   "of type list that cannot be printed"),
    (60, (BIG,), ["money"], "over", "the given threshold a value of type tuple that "
                                    "cannot be printed"),
    (60, {"usd": BIG}, ["money"], "over", "the given threshold a value of type dict that "
                                          "cannot be printed"),
    (0, [BIG], [], "under", None),
    (GONE, [BIG], ["money"], "cannot-estimate", "a value of type list that cannot be printed"),
    (60, Unprintable(), ["money"], "over", "a value of type Unprintable that cannot be printed"),
)


def check_a_threshold_too_long_to_print(m):
    """D5 and D6: a threshold int() will not print still gets a verdict, and
    the reason describes it instead of raising."""
    bad = []
    for amount, threshold, classes, cost, text in BIG_THRESHOLDS:
        effects = fx() if amount is GONE else fx(monthly_cost=usd(amount))
        if amount is GONE:
            effects.pop("monthly_cost")
        shown = (f"{'-' if threshold < 0 else ''}10**5000" if isinstance(threshold, int)
                 else f"a {type(threshold).__name__}")
        label = f"amount {'missing' if amount is GONE else amount!r}, threshold {shown}"
        try:
            got = m.classify(effects, "dev", threshold)
        except (ArithmeticError, ValueError, TypeError, RuntimeError) as exc:
            bad.append(f"{label}: {exc!r}"[:160])
            continue
        if (got["classes"], got["cost"]) != (classes, cost):
            bad.append(f"{label}: {got['classes']} {got['cost']}")
        elif text is not None and text not in got["reasons"].get(P.MONEY, ""):
            bad.append(f"{label}: the reason is {got['reasons'].get(P.MONEY, '')[:160]}")
    return bad


def check_unplaced_wording(m):
    """The unplaced reason names what could not be placed."""
    bad = []
    known = m.decide(ask(fx(sends_email=True)))["reason"]
    if "effect has no question" not in known or "not in the closed table" in known:
        bad.append(f"a known operation with an unplaced effect: {known}")
    unknown = m.decide(ask(BENIGN, op="mystery"))["reason"]
    if "operation is not in the closed table" not in unknown:
        bad.append(f"an unknown operation: {unknown}")
    # An unrecognised classified_as hint with benign effects is the hint's,
    # not an effect's and not the operation's.
    hint = m.decide(ask(BENIGN, classified_as="no-such-class"))["reason"]
    if "classified_as hint" not in hint or "effect has no question" in hint \
            or "not in the closed table" in hint:
        bad.append(f"an unplaced hint with benign effects: {hint}")
    both = m.decide(ask(fx(sends_email=True), classified_as="no-such-class"))["reason"]
    if "classified_as hint" not in both or "effect has no question" not in both:
        bad.append(f"an unplaced hint and an unplaced effect: {both}")
    return bad


# sha256 of json.dumps([decide(row) for every R-01 row], sort_keys=True), the
# full result and trace of each row, measured with the R-01 module (origin/main
# 75088d6aa, before R-P6). Row ids are left out: some hold an object's address,
# which changes from run to run. When the R-01 table or its rules change on
# purpose, re-measure it with the module of that change and replace this value.
R01_RESULTS_SHA256 = "cabc86892694b951a2f08e87efd2ded5b7e9b70a8710e73eb55ed0e76751bbe5"


def r01_results_digest(m):
    """The digest of `m.decide` over every R-01 row, result and trace."""
    rows = [m.decide(copy.deepcopy(r)) for _cid, r, _want in T.CASES]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()


def check_r01_parity(m):
    """Without effects, every R-01 row keeps its full result and trace."""
    got = r01_results_digest(m)
    return [] if got == R01_RESULTS_SHA256 else [
        f"the R-01 rows' results or traces moved: {got}"]


CHECKS = (check_serious_cases, check_admin_and_empty_paths, check_must_allow,
          check_union_with_own_class, check_effects_never_swap_the_account,
          check_d9, check_threshold,
          check_presence_not_value, check_cli_reads_the_tier,
          check_cli_reads_fractions_exactly, check_cost_values,
          check_mixed_number_types, check_a_threshold_too_long_to_print,
          check_unplaced_wording, check_r01_parity)


def violations(module):
    """Every failure of every check. Empty means the classifier is intact."""
    bad = []
    for check in CHECKS:
        bad.extend(f"{check.__name__}: {line}" for line in check(module))
    return bad


@pytest.mark.parametrize("check", CHECKS, ids=[c.__name__ for c in CHECKS])
def test_the_classifier_passes(check):
    assert check(P) == []


def test_every_class_and_unplaced_has_a_must_be_serious_case():
    covered = set()
    for _cid, _effects, _tier, want, _via in SERIOUS_CASES:
        covered.update(want)
    assert covered >= set(P.SERIOUS_CLASSES) | {P.UNPLACED}


def test_the_serious_list_is_the_closed_list_of_the_plan():
    assert P.SERIOUS_CLASSES == frozenset({
        "money", "production-write", "permission-change", "account-creation",
        "admin-use", "destroy-not-owned", "irreversible-or-outside-effect",
        "no-provable-backup"})
    assert P.UNPLACED not in P.SERIOUS_CLASSES
    assert set(P.EFFECT_QUESTIONS) == set(BENIGN)
    assert P.DEFAULT_COST_THRESHOLD_USD_MONTH == 50


def test_classify_answers_in_the_documented_shape():
    for _cid, effects, tier, _want, _via in SERIOUS_CASES:
        got = P.classify(effects, tier)
        assert set(got) == {"classes", "primary", "reasons", "placed", "cost"}
        assert got["cost"] in ("under", "over", "cannot-estimate")
        assert got["classes"] == sorted(got["classes"])
    for effects in (None, [], "x", 5):
        assert P.classify(effects, "dev") == {
            "classes": ["unplaced"], "primary": "unplaced", "placed": False,
            "cost": "cannot-estimate", "reasons": P.classify(effects, "dev")["reasons"]}
        assert set(P.classify(effects, "dev")["reasons"]) == {"unplaced"}


def test_an_unknown_key_is_unplaced_and_the_known_keys_are_still_read():
    got = P.classify(fx(sends_email=True, spends=True), "dev")
    assert got["classes"] == sorted([P.UNPLACED, P.MONEY])
    assert got["primary"] == P.UNPLACED and got["placed"] is False


# --- parity with the R-01 table ------------------------------------------------

def _r01_classes(request):
    """The R-01 class set of one row, as `decide` would build it."""
    req = request if isinstance(request, dict) else {}
    facts = req.get("facts") if isinstance(req.get("facts"), dict) else {}
    name = req.get("operation")
    name = name.strip().lower() if isinstance(name, str) else ""
    spec = P.OPERATIONS.get(name) or P.Op(P.SERIOUS_ALWAYS, tiered=True, serious=P.UNPLACED)
    tier = P._pick(req.get("tier"), P.TIERS)  # pylint: disable=protected-access
    return spec, facts, P._classes(spec, tier, facts,  # pylint: disable=protected-access
                                   req.get("classified_as"))


def _d9_exempt(request):
    spec, facts, classes = _r01_classes(request)
    return (spec.cost_checked
            and P._fact(facts, "estimate_under_threshold", True) == P.UNKNOWN  # pylint: disable=protected-access
            and classes == frozenset({P.MONEY}))


def _with_fact(request):
    facts = request.get("facts") if isinstance(request.get("facts"), dict) else {}
    return dict(request, facts=dict(facts, estimate_under_threshold=True))


DICT_ROWS = [(cid, r) for cid, r, _want in T.CASES if isinstance(r, dict)]


def test_the_r01_table_is_the_one_measured():
    assert len(T.CASES) == 1316
    assert len(DICT_ROWS) == len(T.CASES)
    assert not any("effects" in r for _cid, r in DICT_ROWS)


def test_without_effects_every_r01_row_is_unchanged_trace_included():
    for cid, request, want in T.CASES:
        done = P.decide(request)
        assert done["outcome"] == want, cid
        assert "effects" not in "\n".join(done["trace"]), cid
    # The full result and trace of every row, not only the outcome.
    assert r01_results_digest(P) == R01_RESULTS_SHA256


def _baseline(request):
    return brief(P.decide(_with_fact(request) if _d9_exempt(request) else request))


def test_benign_effects_change_only_the_d9_rows_and_only_to_the_fact_true_answer():
    exempt = []
    for cid, request in DICT_ROWS:
        done = brief(P.decide(dict(request, effects=BENIGN)))
        if _d9_exempt(request):
            exempt.append(request["operation"])
            assert done == brief(P.decide(_with_fact(request))), cid
        else:
            assert done == brief(P.decide(request)), cid
    assert exempt, "no row reaches D9"
    assert set(exempt) == {"terraform-apply"}


def test_an_explicit_false_fact_is_never_exempt():
    rows = [(cid, r) for cid, r in DICT_ROWS
            if isinstance(r.get("facts"), dict)
            and r["facts"].get("estimate_under_threshold") is False]
    assert rows
    for cid, request in rows:
        assert not _d9_exempt(request)
        assert brief(P.decide(dict(request, effects=BENIGN))) == brief(P.decide(request)), cid


SINGLE_SERIOUS = [("spends", True), ("monthly_cost", usd(60)), ("writes", True),
                  ("permission_change", "permanent"), ("creates_account", True),
                  ("admin_use", "other"), ("destroys", "not-own"),
                  ("reversible", False), ("outside_effect", True), ("backup", "none")]


def test_a_serious_answer_never_creates_an_allow():
    for cid, request in DICT_ROWS:
        baseline = _baseline(request)[0]
        for key, value in SINGLE_SERIOUS:
            done = P.decide(dict(request, effects=fx(**{key: value})))["outcome"]
            assert done != "allow" or baseline == "allow", f"{cid}: {key}={value!r}"


# --- the CLI --------------------------------------------------------------------

def _cli(*args, stdin=None):
    return subprocess.run([sys.executable, T.MODULE] + list(args), input=stdin,
                          capture_output=True, text=True, check=False,
                          encoding="utf-8", errors="replace", timeout=60)


FULL = {"operation": "commit", "tier": "prod", "presence": "attended",
        "machine_layer": "clear", "account": "write-verified",
        "effects": fx(writes=True)}


def test_the_cli_classifies_a_full_request():
    done = _cli("classify", json.dumps(FULL))
    assert done.returncode == 0 and done.stderr == ""
    got = json.loads(done.stdout)
    assert set(got) == {"classes", "primary", "reasons", "placed", "cost"}
    assert got["classes"] == ["production-write"]
    assert set(got["classes"]) <= set(P.SERIOUS_CLASSES) | {P.UNPLACED}
    assert got["primary"] == "production-write"
    assert set(got["reasons"]) == set(got["classes"])
    assert got["placed"] is ("unplaced" not in got["classes"])
    assert got["cost"] in ("under", "over", "cannot-estimate")
    assert done.stdout.strip() == json.dumps(got, indent=2, sort_keys=True)
    stdin = _cli("classify", "-", stdin=json.dumps(FULL))
    assert stdin.returncode == 0 and stdin.stdout == done.stdout


@pytest.mark.parametrize("tier,want", [("dev", []), ("qa", []), ("prod", ["production-write"]),
                                       ("staging", ["production-write"]),
                                       (GONE, ["production-write"])])
def test_the_cli_reads_the_tier(tier, want):
    body = dict(FULL, tier=tier)
    if tier is GONE:
        body.pop("tier")
    got = json.loads(_cli("classify", json.dumps(body)).stdout)
    assert got["classes"] == want
    assert got["primary"] == (want[0] if want else None)


@pytest.mark.parametrize("body", [{"operation": "commit", "tier": "dev"}, [], [FULL], 5])
def test_the_cli_classifies_a_request_without_effects_as_unplaced(body):
    done = _cli("classify", json.dumps(body))
    assert done.returncode == 0 and done.stderr == ""
    got = json.loads(done.stdout)
    assert got["classes"] == ["unplaced"] and got["placed"] is False
    assert got["cost"] == "cannot-estimate"


@pytest.mark.parametrize("args,stdin", [(("classify", "{not json"), None),
                                        (("classify", "-"), "nope"), (("classify",), None)])
def test_the_cli_prints_no_verdict_for_a_request_it_cannot_read(args, stdin):
    done = _cli(*args, stdin=stdin)
    assert done.returncode == 2 and done.stdout == "" and done.stderr.strip()


def test_the_cli_ignores_facts_classified_as_and_threshold():
    effects = fx(writes=True, monthly_cost=usd(60))
    plain = _cli("classify", json.dumps(dict(FULL, effects=effects))).stdout
    loaded = dict(FULL, effects=effects, threshold=100,
                  costThreshold=100, classified_as="money",
                  facts={"estimate_under_threshold": True})
    assert _cli("classify", json.dumps(loaded)).stdout == plain
    assert json.loads(plain)["classes"] == sorted(["money", "production-write"])


# --- sabotage: each weakened classifier must be caught ----------------------------

MUTATIONS = (
    ("1 an unknown effect key is ignored", "    if extra:\n", "    if False:\n"),
    ("2 non-object effects count as benign",
     "    if not isinstance(effects, dict):\n        return _verdict(",
     "    if not isinstance(effects, dict):\n        return _verdict({}, UNDER)\n"
     "    if False:\n        return _verdict("),
    ("3a a missing bool answer counts as benign",
     '    if effects.get("spends") is not False:\n',
     '    if effects.get("spends") is True:\n'),
    ("3b a missing enum answer counts as benign",
     '    if destroys not in ("none", "own"):\n',
     '    if destroys == "not-own":\n'),
    ("3c a missing cost amount counts as zero",
     '    if set(estimate) != {"amount", "currency", "period"}:\n'
     '        return CANNOT_ESTIMATE   # an extra or missing key is not the shape\n'
     '    amount = _amount(estimate.get("amount"))\n',
     '    if not set(estimate) <= {"amount", "currency", "period"}:\n'
     '        return CANNOT_ESTIMATE\n'
     '    amount = _amount(estimate.get("amount", 0))\n'),
    ("4 a missing cost estimate is under the threshold",
     "    if not isinstance(estimate, dict):\n        return CANNOT_ESTIMATE\n",
     "    if not isinstance(estimate, dict):\n        return UNDER\n"),
    ("5 another currency is accepted at face value", ' or currency != "usd"', ""),
    ("6a a small overrun passes (50.01 is under)",
     "    return amount > limit\n", "    return amount > limit + 1\n"),
    ("6b exactly the threshold is over",
     "    return amount > limit\n", "    return amount >= limit\n"),
    ("7 a bool amount is a number",
     "    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):\n",
     "    if not isinstance(value, (int, float, Decimal)):\n"),
    ("8 NaN or inf is a number", "    if value - value != 0 or value < 0:",
     "    if value < 0:"),
    ("9a an invalid threshold falls back to a large value",
     "        limit = 0   # an invalid threshold must not widen (D6)\n",
     "        limit = 10 ** 9\n"),
    ("9b an invalid threshold falls back to the default",
     "        limit = 0   # an invalid threshold must not widen (D6)\n",
     "        limit = DEFAULT_COST_THRESHOLD_USD_MONTH\n"),
    ("10a a decide request field threshold raises the threshold",
     'classify(req["effects"], tier)', 'classify(req["effects"], tier, req.get("threshold"))'),
    ("10b a decide request field costThreshold raises the threshold",
     'classify(req["effects"], tier)',
     'classify(req["effects"], tier, req.get("cost" + "Threshold"))'),
    ("11 the grantable-profile exception applies in prod", "and not prod):", "):"),
    ("12 a temporary listed grant in prod is not a permission change",
     '(prod and perm != "none")', '(prod and perm not in ("none", "temporary-listed"))'),
    ("13 an unknown tier with writes True is not a production write",
     '    prod = _pick(tier, TIERS) not in ("dev", "qa")\n',
     '    prod = _pick(tier, TIERS) == "prod"\n'),
    ("14 effects replace the operation's own classes",
     '        classes = base | frozenset(effect["classes"])\n',
     '        classes = frozenset(effect["classes"])\n'),
    ("15 an under-threshold estimate overrides an explicit False fact",
     '"estimate_under_threshold", True) == UNKNOWN:',
     '"estimate_under_threshold", True) != "met":'),
    ("16 outside_effect True with reversible True is not serious",
     '            or effects.get("outside_effect") is not False):',
     '            and effects.get("outside_effect") is not False):'),
    ("17 effects null is treated as absent",
     'if "effects" in req else None', 'if req.get("effects") is not None else None'),
    ("18 D9 applies when the cost is over or cannot be estimated",
     'effect is not None and effect["cost"] == UNDER and _fact(',
     "effect is not None and _fact("),
    ("19 D9 writes the fact into the caller's facts",
     "        facts = dict(facts, estimate_under_threshold=True)\n",
     '        facts["estimate_under_threshold"] = True\n'),
    ("20 the classify CLI ignores the request's tier",
     "classify(effects, _request_tier(body))", 'classify(effects, "dev")'),
    ("21 effects that omit admin_use do not add admin-use",
     '    admin = _pick(effects.get("admin_use"), ADMIN_USES)\n',
     '    admin = _pick(effects.get("admin_use", "none"), ADMIN_USES)\n'),
    ("22 an estimate with an extra key is still an estimate",
     '    if set(estimate) != {"amount", "currency", "period"}:\n',
     "    if False:\n"),
    ("23 a request without effects gets a new trace line",
     'if "effects" in req else None\n',
     'if "effects" in req else None\n    walk.look("-", "classifier off")\n'),
    ("24 a missing or non-bool writes is benign in dev and QA",
     "    if writes is not False and (prod or writes is not True):\n",
     "    if writes is not False and prod:\n"),
    ("25 the CLI reads a fraction as a float (50.000000000000001 is 50.0)",
     "parse_float=_json_fraction,\n                             parse_int=_json_integer",
     "parse_int=_json_integer"),
    ("26 a Decimal amount is not a number",
     "not isinstance(value, (int, float, Decimal)):", "not isinstance(value, (int, float)):"),
    ("27 an unplaced effect on a known operation is worded as an unknown operation",
     "    if walk.unplaced or effect is None:\n", "    if True:\n"),
    ("27b an unplaced classified_as hint is worded as an effect",
     "    if UNPLACED in base:\n", "    if False:\n"),
    ("28 an effect-added class replaces the row's account rule",
     "(base, classes) if classes != base else (classes,)", "(classes,)"),
    ("29 the CLI reads every fraction with Decimal, which crashes on 1e9999...",
     "parse_float=_json_fraction", "parse_float=Decimal"),
    ("30 the money reason names the rejected threshold as applied",
     "        applied = _limit(limit)\n", "        applied = limit\n"),
    ("31 a negative amount no Decimal can hold is read as -0.0",
     '    if text.startswith("-"):\n        return float("-inf")\n', ""),
    ("32 a float inf amount is over, not cannot-estimate",
     "    if value - value != 0 or value < 0:", "    if value != value or value < 0:"),
    ("33 a Decimal Infinity amount is over, not cannot-estimate",
     "return value if value.is_finite() and value >= 0 else None",
     "return value if not value.is_nan() and value >= 0 else None"),
    ("34 a Decimal amount is checked with arithmetic (raises under the Clamped trap)",
     "        return value if value.is_finite() and value >= 0 else None\n",
     "        return value if value.is_finite() and value - value == 0 and value >= 0 "
     "else None\n"),
    ("35 the CLI reads an integer with int alone (over 4300 digits is a reader error)",
     ",\n                             parse_int=_json_integer)", ")"),
    ("36 a Decimal is compared with a float directly (raises under FloatOperation)",
     "    return OVER if _exceeds(amount, limit) else UNDER\n",
     "    return OVER if amount > limit else UNDER\n"),
    ("37 a Decimal amount is rounded to a float beside a float threshold",
     "        limit = Decimal.from_float(limit)\n", "        amount = float(amount)\n"),
    ("38 the money reason prints the threshold applied (over 4300 digits raises)",
     "(threshold {_shown(applied)} USD", "(threshold {applied} USD"),
    ("39 the money reason prints the threshold given (over 4300 digits raises)",
     'f"{_shown(limit)} is not a finite', 'f"{limit!r} is not a finite'),
    ("40 a zero no Decimal can hold is read by its sign (-0e9999... is -inf)",
     '    if not mantissa.strip("-0."):\n', "    if False:\n"),
    ("41 any amount no Decimal can hold is read as zero",
     '.strip("-0."):\n', '.strip("-0.123456789"):\n'),
    ("42 a positive amount no Decimal can hold is read as inf (cannot-estimate, not over)",
     'return 0.0 if exponent.startswith("-") else _LARGEST',
     'return 0.0 if exponent.startswith("-") else float("inf")'),
    ("43 the CLI trusts Decimal to raise (NaN with InvalidOperation untrapped)",
     "    if value is not None and not value.is_nan():\n", "    if value is not None:\n"),
    ("44 only an int that will not print is described (a list of one raises TypeError)",
     "        if isinstance(value, int):\n", "        if True:\n"),
    ("45 only a ValueError from str() is caught",
     "    except Exception:  # pylint: disable=broad-except  # noqa: BLE001\n",
     "    except ValueError:\n"),
    ("46 a positive amount too small for a Decimal is read as the largest",
     'return 0.0 if exponent.startswith("-") else _LARGEST', "return _LARGEST"),
)


@pytest.mark.parametrize("label,old,new", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_a_weakened_classifier_is_caught(label, old, new):
    bad = violations(T._variant(old, new))  # pylint: disable=protected-access
    assert bad, "nothing caught: " + label
