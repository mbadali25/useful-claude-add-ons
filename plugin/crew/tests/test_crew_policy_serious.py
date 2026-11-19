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
import hashlib
import io
import json
import subprocess
import sys

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
    # An admin effect moves the account check to the broker (4.14), so a
    # dev cloud-read with no account goes from ask-owner at rule 2 to
    # needs-plan at rule 5: still no allow without a covering plan.
    read = {"operation": "cloud-read", "tier": "dev", "presence": "attended",
            "machine_layer": "clear", "account": "none", "admin_need": "covers"}
    if brief(P.decide(read))[:2] != ("ask-owner", "2"):
        bad.append(f"cloud-read without effects moved: {brief(P.decide(read))}")
    done = brief(m.decide(dict(read, effects=fx(admin_use="other"))))
    if done != ("needs-plan", "5", P.ADMIN_USE):
        bad.append(f"cloud-read with admin-use effects: {done}")
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


def _main_out(m, body):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = m._main(["crew_policy.py", "classify", body])  # pylint: disable=protected-access
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
    for raw, want in (("50.000000000000001", ["money"]), ("50.0", []),
                      ("49.99", []), ("50.01", ["money"]), ("1e999", ["money"])):
        body = json.dumps({"operation": "commit", "tier": "dev",
                           "effects": fx(monthly_cost=usd(0))})
        body = body.replace('"amount": 0', '"amount": ' + raw)
        code, out = _main_out(m, body)
        if code != 0 or json.loads(out)["classes"] != want:
            bad.append(f"classify CLI amount {raw}: {code} {out.strip()[:80]}")
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
          check_union_with_own_class, check_d9, check_threshold,
          check_presence_not_value, check_cli_reads_the_tier,
          check_cli_reads_fractions_exactly, check_unplaced_wording, check_r01_parity)


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
     "    return OVER if amount > limit else UNDER\n",
     "    return OVER if amount > limit + 1 else UNDER\n"),
    ("6b exactly the threshold is over",
     "    return OVER if amount > limit else UNDER\n",
     "    return OVER if amount >= limit else UNDER\n"),
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
     '        classes = classes | frozenset(effect["classes"])\n',
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
     "json.loads(raw, parse_float=Decimal)", "json.loads(raw)"),
    ("26 a Decimal amount is not a number",
     "not isinstance(value, (int, float, Decimal)):", "not isinstance(value, (int, float)):"),
    ("27 an unplaced effect on a known operation is worded as an unknown operation",
     "if walk.unplaced\n                or", "if True\n                or"),
)


@pytest.mark.parametrize("label,old,new", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_a_weakened_classifier_is_caught(label, old, new):
    bad = violations(T._variant(old, new))  # pylint: disable=protected-access
    assert bad, "nothing caught: " + label
