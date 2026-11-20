"""`crew_policy.classify` and the strict CLI reader, REPORT-ONLY (plan 4.13, R-P6).

The classifier places one action's *effects* into the closed serious list.
Every question is required, an answer it cannot read is the serious one, an
effect it has no question for is UNPLACED, and money is an exact comparison
of a USD monthly estimate with the threshold (4.5, "Money"; default 50 USD a
month, plan section 8), read in one pinned decimal context. Effects only add
classes: no effect lowers an outcome (spec D3). A present `account` outside
the closed list stops at rule 2 (D6). The CLI reads every request through one
strict reader and one wrapper: anything it refuses exits 2 with nothing on
stdout (D9, D10).

The checks below each return the failures they find in a module, so the same
check runs against the real module and against a sabotaged copy of it
(`MUTATIONS`, R-01's in-file `_variant` mechanism). Subprocess rows run the
file on disk and can never see a mutant, so every CLI mutation is killed by
an in-process row (`run_main`).
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

# pylint: disable=protected-access

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

    Base: `commit` (free lane, no account of its own), machine layer clear,
    no plan. An admin class gets admin_need covers and account none; other
    prod classes get the write account; dev or QA gets account none. The
    setup is computed with the real classifier, so a sabotaged copy is asked
    the same question."""
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


def flags_clear(m):
    """Failures if the module constant carries a flag or lost a trap."""
    ctx = m._DECIMAL
    bad = []
    if any(ctx.flags.values()):
        bad.append(f"flags set on _DECIMAL: {[k.__name__ for k, v in ctx.flags.items() if v]}")
    if ctx.prec != 34 or not all(ctx.traps.values()):
        bad.append(f"_DECIMAL changed: prec {ctx.prec}, traps "
                   f"{[k.__name__ for k, v in ctx.traps.items() if not v]} off")
    return bad


# --- must be serious: (id, effects, tier, classes, through decide) ----------

SERIOUS_CASES = [
    ("money: spends True", fx(spends=True), "dev", [P.MONEY], True),
    ("money: spends missing", fx(spends=GONE), "dev", [P.MONEY], True),
    ("money: 50.01 USD a month", fx(monthly_cost=usd(50.01)), "dev", [P.MONEY], True),
    ("money: amount missing", fx(monthly_cost={"currency": "USD", "period": "month"}),
     "dev", [P.MONEY], True),
    ("money: amount a string", fx(monthly_cost=usd("10")), "dev", [P.MONEY], True),
    ("money: amount a bool", fx(monthly_cost=usd(True)), "dev", [P.MONEY], True),
    ("money: amount negative", fx(monthly_cost=usd(-5)), "dev", [P.MONEY], True),
    ("money: EUR", fx(monthly_cost=usd(10, currency="EUR")), "dev", [P.MONEY], True),
    ("money: period year", fx(monthly_cost=usd(10, period="year")), "dev", [P.MONEY], True),
    ("money: an estimate with an extra key", fx(monthly_cost=dict(usd(10), extra=True)),
     "dev", [P.MONEY], True),
    ("money: monthly_cost absent", fx(monthly_cost=GONE), "dev", [P.MONEY], True),
    ("production-write: writes True in prod", fx(writes=True), "prod",
     [P.PRODUCTION_WRITE], True),
    ("production-write: writes missing in prod", fx(writes=GONE), "prod",
     [P.PRODUCTION_WRITE], True),
    ("production-write: writes missing in dev", fx(writes=GONE), "dev",
     [P.PRODUCTION_WRITE], True),
    ("production-write: writes missing in qa", fx(writes=GONE), "qa",
     [P.PRODUCTION_WRITE], True),
    ("production-write: writes 'yes' in dev", fx(writes="yes"), "dev",
     [P.PRODUCTION_WRITE], True),
    ("production-write: writes 'yes' in prod", fx(writes="yes"), "prod",
     [P.PRODUCTION_WRITE], True),
    ("production-write: writes null in qa", fx(writes=None), "qa",
     [P.PRODUCTION_WRITE], True),
    ("production-write: writes 1 in dev", fx(writes=1), "dev",
     [P.PRODUCTION_WRITE], True),
    # decide stops an unknown tier at rule 3, so classify only.
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
    ("account-creation: 'yes'", fx(creates_account="yes"), "dev",
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
    ("unplaced: an unknown effect key", fx(sends_email=True), "dev", [P.UNPLACED], True),
    ("unplaced: effects null", None, "dev", [P.UNPLACED], True),
    ("unplaced: effects a list", [], "dev", [P.UNPLACED], True),
    ("unplaced: effects a string", "writes", "dev", [P.UNPLACED], True),
    ("several: the strictest is reported, all are listed",
     fx(spends=True, destroys="not-own", writes=True), "prod",
     sorted([P.DESTROY_NOT_OWNED, P.MONEY, P.PRODUCTION_WRITE]), True),
]
SERIOUS_PRIMARY = {"several: the strictest is reported, all are listed": P.DESTROY_NOT_OWNED}


def check_serious_cases(m):
    """Each must-be-serious case, through classify and decide; an unknown
    operation with no effects is serious too."""
    bad = []
    for cid, effects, tier, want, via_decide in SERIOUS_CASES:
        primary = SERIOUS_PRIMARY.get(cid, want[0])
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
                               "machine_layer": "clear"}))
        if done != ("needs-plan", "5", P.UNPLACED):
            bad.append(f"an unknown operation with no effects: {done}")
    return bad


# (amount, cost) asked in-process; the class is money for every one of them,
# so the `cost` value is what is asserted (sabotage 8 and 28).
COST_VALUES = (
    (NAN, "cannot-estimate"), (INF, "cannot-estimate"), (-INF, "cannot-estimate"),
    (Decimal("NaN"), "cannot-estimate"), (Decimal("sNaN"), "cannot-estimate"),
    (Decimal("Infinity"), "cannot-estimate"), (Decimal("-Infinity"), "cannot-estimate"),
    (Decimal("1E+1000"), "cannot-estimate"),
    (10 ** 39, "cannot-estimate"),                         # 40 digits: Rounded
    (Decimal("1." + "0" * 38 + "1"), "cannot-estimate"),   # Inexact
    (-1, "cannot-estimate"), (Decimal("-0.01"), "cannot-estimate"),
)


def check_cost_values(m):
    """The cost answer itself, not only the money class."""
    bad = []
    for amount, want in COST_VALUES:
        got = m.classify(fx(monthly_cost=usd(amount)), "dev")
        if got["cost"] != want or got["classes"] != [P.MONEY]:
            bad.append(f"amount {amount!r}"[:80] + f": {got['cost']} {got['classes']}")
    return bad + flags_clear(m)


# --- must allow: (id, decide request without effects, effects, tier) --------

MUST_ALLOW = [
    ("every key benign", T.req("commit"), BENIGN, "dev"),
    ("monthly_cost 0 USD", T.req("commit"), fx(monthly_cost=usd(0)), "dev"),
    ("monthly_cost 50 USD is not over", T.req("commit"), fx(monthly_cost=usd(50)), "dev"),
    ("monthly_cost 50.00 USD", T.req("commit"), fx(monthly_cost=usd(50.00)), "dev"),
    ("monthly_cost Decimal 49.99", T.req("commit"),
     fx(monthly_cost=usd(Decimal("49.99"))), "dev"),
    ("monthly_cost float 49.99", T.req("commit"), fx(monthly_cost=usd(49.99)), "dev"),
    ("monthly_cost -0", T.req("commit"), fx(monthly_cost=usd(-0)), "dev"),
    ("monthly_cost float -0.0", T.req("commit"), fx(monthly_cost=usd(-0.0)), "dev"),
    ("lower-case currency and period", T.req("commit"),
     fx(monthly_cost=usd(12, currency=" usd ", period="Month")), "dev"),
    ("temporary-listed in dev", T.req("commit"),
     fx(permission_change="temporary-listed"), "dev"),
    ("grantable-profile-temporary in QA", T.req("commit", tier="qa"),
     fx(admin_use="grantable-profile-temporary"), "qa"),
    ("backup no-state-change", T.req("commit"), fx(backup="no-state-change"), "dev"),
    ("writes True in dev", T.req("commit"), fx(writes=True), "dev"),
    ("writes True in QA", T.req("commit", tier="qa"), fx(writes=True), "qa"),
]


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


# --- the pinned context (D5) -------------------------------------------------

PINNED_ROWS = ((50, "under"), (50.0, "under"), (Decimal("50"), "under"),
               (50.01, "over"), (Decimal("50.01"), "over"),
               (49.99, "under"), (Decimal("49.99"), "under"))
PINNED_THRESHOLDS = (None, 50, 50.0, Decimal("50"))
ALL_TRAPS = [decimal.Clamped, decimal.DivisionByZero, decimal.Inexact,
             decimal.InvalidOperation, decimal.Overflow, decimal.Rounded,
             decimal.Subnormal, decimal.Underflow, decimal.FloatOperation]
CALLER_CONTEXTS = (("default", lambda: decimal.Context()),  # pylint: disable=unnecessary-lambda
                   ("every trap", lambda: decimal.Context(traps=ALL_TRAPS)),
                   ("prec 3, no trap", lambda: decimal.Context(prec=3, traps=[])))


def _state(ctx):
    return (dict(ctx.flags), dict(ctx.traps), ctx.prec, ctx.rounding, ctx.Emax, ctx.Emin)


def check_pinned_context(m):
    """The same answers under three caller contexts, each asserted; the
    caller's context is left as it was, and the constant carries no flag."""
    bad = []
    for name, make in CALLER_CONTEXTS:
        saved = decimal.getcontext()
        caller = make()
        decimal.setcontext(caller)
        try:
            before = _state(caller)
            for amount, want in PINNED_ROWS:
                for threshold in PINNED_THRESHOLDS:
                    try:
                        got = m.classify(fx(monthly_cost=usd(amount)), "dev",
                                         threshold)["cost"]
                    except ArithmeticError as exc:
                        got = repr(exc)
                    if got != want:
                        bad.append(f"{name}: amount {amount!r} threshold {threshold!r}: {got}")
            if decimal.getcontext() is not caller or _state(caller) != before:
                bad.append(f"{name}: the caller's context changed")
        finally:
            decimal.setcontext(saved)
        bad.extend(f"{name}: {line}" for line in flags_clear(m))
    return bad


# --- the threshold (D7) ------------------------------------------------------

BAD_THRESHOLDS = (-1, "100", True, NAN, 10 ** 10, Decimal("1E+1000"), [100])


def check_threshold(m):
    """A valid threshold applies; any other reads as 0 and is never printed;
    a decide request cannot carry a threshold."""
    bad = []
    if m.classify(fx(monthly_cost=usd(60)), "dev", threshold=100)["classes"]:
        bad.append("threshold 100 did not let 60 USD pass")
    if m.classify(fx(monthly_cost=usd(50)), "dev")["classes"]:
        bad.append("the default threshold is not 50")
    for threshold in BAD_THRESHOLDS:
        got = m.classify(fx(monthly_cost=usd(0.01)), "dev", threshold=threshold)
        if got["classes"] != [P.MONEY] or got["cost"] != "over":
            bad.append(f"invalid threshold {threshold!r} widened: {got['classes']}")
        said = got["reasons"].get(P.MONEY, "")
        if str(threshold) in said or repr(threshold) in said:
            bad.append(f"invalid threshold {threshold!r} printed: {said}")
    for field in ("threshold", "costThreshold"):
        done = brief(m.decide(ask(fx(monthly_cost=usd(60)), **{field: 100})))
        if done != ("needs-plan", "5", P.MONEY):
            bad.append(f"request field {field} raised the threshold: {done}")
    return bad + flags_clear(m)


def check_presence_not_value(m):
    """D8: the key's presence, not its value, turns the classifier on."""
    bad = []
    for value in (None, [], "", 0, False):
        done = brief(m.decide(ask(value)))
        if done != ("needs-plan", "5", P.UNPLACED):
            bad.append(f"effects {value!r}: {done}")
    return bad


def check_union_with_own_class(m):
    """Effects add classes; they never remove the operation's own."""
    bad = []
    for op, tier in (("payment", "dev"), ("delete-data", "dev"),
                     ("start-deploy", "prod"), ("terraform-apply", "qa")):
        facts = {"ownership": "theirs"} if op == "delete-data" else None
        if op == "terraform-apply":
            facts = {"estimate_under_threshold": GONE}
        request = T.req(op, tier, facts=facts)
        plain = brief(P.decide(request))
        done = brief(m.decide(dict(request, effects=BENIGN)))
        if done != plain or plain[0] == "allow":
            bad.append(f"{op} {tier}: with benign effects {done}, without {plain}")
    return bad


# --- the malformed account (D6) ----------------------------------------------

MALFORMED = ("typo", 7, None, [], {}, "")
COVERING_PLAN = {"provenance": "plan-of-record", "plan_covers": True, "attested": True}
STOP = {"attended": "ask-owner", "unattended": "deny"}


def _d6_requests():
    """(label, request without the account key, R-01 answer with the key
    absent or 'none' as (outcome, rule))."""
    commit = {"operation": "commit", "tier": "dev", "machine_layer": "clear",
              "target": "repo"}
    repro = dict(commit, effects={}, admin_need="covers", prodcheck="pass",
                 facts={"irreversible_listed": True, "cap_set": True,
                        "preflight_ok": True}, **COVERING_PLAN)
    create = {k: v for k, v in T.req("create-account").items() if k != "presence"}
    return (("a: commit dev", commit, ("allow", "9")),
            ("b: round-9 repro, empty effects under a covering plan", repro,
             ("allow", "5")),
            ("c: create-account dev", create, ("needs-plan", "5")))


def check_malformed_account_stops(m):
    """A present account outside the closed list stops at rule 2 in every
    branch; absent and 'none' keep their answer."""
    bad = []
    for label, base, control in _d6_requests():
        for presence in ("attended", "unattended"):
            request = dict(base, presence=presence)
            for account in MALFORMED + ("Could-Not-Tell ",):
                done = brief(m.decide(dict(request, account=account)))
                if done[:2] != (STOP[presence], "2"):
                    bad.append(f"{label}, {presence}, account {account!r}: {done}")
            if presence == "attended":
                for account in (GONE, "none"):
                    asked = dict(request) if account is GONE else dict(request, account=account)
                    done = brief(m.decide(asked))
                    if done[:2] != control:
                        bad.append(f"{label}, account {account!r}: {done}, want {control}")
    # (d) a human-lane operation, unattended: R-01 asks the owner with the
    # key absent; a malformed account is a rule-2 deny.
    human = {"operation": "skip-gate", "tier": "dev", "presence": "unattended",
             "machine_layer": "clear", "target": "repo"}
    if brief(m.decide(human))[:2] != ("ask-owner", "human"):
        bad.append(f"d: skip-gate unattended without account: {brief(m.decide(human))}")
    for account in MALFORMED:
        done = brief(m.decide(dict(human, account=account)))
        if done[:2] != ("deny", "2"):
            bad.append(f"d: skip-gate unattended, account {account!r}: {done}")
    return bad


# --- parity over R-01 --------------------------------------------------------

# sha256 of json.dumps([decide(row) for every R-01 row], sort_keys=True): the
# full result and trace of each row, measured with the R-01 module (origin/main
# 9cdf4a326, before R-P6; the same value as at 75088d6aa). Row ids are left
# out: some hold an object's address. The 12 R-01 rows with a present
# malformed account (`account 7`) already stop at rule 2 with the same trace,
# so D6 moves none of them and the digest is unchanged.
R01_RESULTS_SHA256 = "cabc86892694b951a2f08e87efd2ded5b7e9b70a8710e73eb55ed0e76751bbe5"
DICT_ROWS = [(cid, r) for cid, r, _want in T.CASES if isinstance(r, dict)]


def r01_results_digest(m):
    """The digest of `m.decide` over every R-01 row, result and trace."""
    rows = [m.decide(copy.deepcopy(r)) for _cid, r, _want in T.CASES]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()


def check_r01_parity(m):
    """Parity 1: without effects, every R-01 row keeps its result and trace."""
    got = r01_results_digest(m)
    return [] if got == R01_RESULTS_SHA256 else [f"the R-01 rows moved: {got}"]


def check_benign_effects_parity(m):
    """Parity 2: benign effects on every R-01 row change nothing (no D9)."""
    bad = []
    for cid, request in DICT_ROWS:
        if brief(m.decide(dict(request, effects=BENIGN))) != brief(P.decide(request)):
            bad.append(f"{cid}: benign effects moved the answer")
    return bad


SINGLE_SERIOUS = [("spends", True), ("monthly_cost", usd(60)), ("writes", True),
                  ("permission_change", "permanent"), ("creates_account", True),
                  ("admin_use", "other"), ("destroys", "not-own"),
                  ("reversible", False), ("outside_effect", True), ("backup", "none")]


def check_a_serious_answer_never_creates_an_allow(m):
    """Parity 3: one serious answer on every R-01 row is allow only where
    the row without effects is allow."""
    bad = []
    for cid, request in DICT_ROWS:
        baseline = P.decide(request)["outcome"]
        for key, value in SINGLE_SERIOUS:
            done = m.decide(dict(request, effects=fx(**{key: value})))["outcome"]
            if done == "allow" and baseline != "allow":
                bad.append(f"{cid}: {key}={value!r} allowed")
    return bad


def check_effects_never_swap_the_account(m):
    """Parity 4: under a covering attested plan, for every operation, tier
    and account value (malformed too), no single serious effect turns a
    non-allow into an allow."""
    bad = []
    covered = dict(COVERING_PLAN, presence="attended", machine_layer="clear",
                   admin_need="covers", prodcheck="pass", target="repo")
    for op in sorted(P.OPERATIONS):
        for tier in ("dev", "qa", "prod"):
            for account in P.ACCOUNTS + ("typo", 7, None):
                request = dict(covered, operation=op, tier=tier, account=account)
                if P.decide(request)["outcome"] == "allow":
                    continue
                for key, value in SINGLE_SERIOUS:
                    done = m.decide(dict(request, effects=fx(**{key: value})))
                    if done["outcome"] == "allow":
                        bad.append(f"{op} {tier} account {account!r}: {key}={value!r} allowed")
    return bad


# --- the CLI, in-process -----------------------------------------------------

def run_main(module, argv, stdin_bytes=None):
    """(exit code, stdout, stderr) of `module._main`; stdin, when given, is a
    latin-1 text layer over the bytes, so a reader that takes the text layer
    gets a string where the bytes layer holds invalid UTF-8. An exception out
    of `_main` is code None."""
    out, err = io.StringIO(), io.StringIO()
    kept = sys.stdin
    if stdin_bytes is not None:
        sys.stdin = io.TextIOWrapper(io.BytesIO(stdin_bytes), encoding="latin-1")
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = module._main(["crew_policy.py"] + list(argv))
            except Exception as exc:  # pylint: disable=broad-exception-caught  # noqa: BLE001
                code = None
                err.write(f"Traceback: {exc!r}"[:200])
    finally:
        sys.stdin = kept
    return code, out.getvalue(), err.getvalue()


def refused(result):
    """None if (code, stdout, stderr) is a clean refusal, else why not."""
    code, out, err = result
    if code == 2 and out == "" and len(err.strip().splitlines()) == 1 \
            and "Traceback" not in err:
        return None
    return f"code {code}, stdout {out[:60]!r}, stderr {err.strip()[:80]!r}"


def answered(result):
    """None if (code, stdout, stderr) is an answer, else why not."""
    code, out, err = result
    if code == 0 and out.strip() and err == "":
        return None
    return f"code {code}, stdout {out[:60]!r}, stderr {err.strip()[:120]!r}"


VERBS = ("decide", "explain", "classify")
BASE = {"operation": "commit", "tier": "dev", "presence": "attended",
        "machine_layer": "clear", "account": "none", "effects": BENIGN}


def with_field(raw, request=None):
    """The JSON text of a request with an unused field "x" holding `raw`."""
    return json.dumps(request or BASE)[:-1] + ', "x": ' + raw + "}"


def with_amount(raw):
    """The JSON text of BASE with the monthly amount written as `raw`."""
    text = json.dumps(BASE)
    assert text.count('"amount": 0') == 1
    return text.replace('"amount": 0', '"amount": ' + raw)


def padded(size):
    """A valid request padded with spaces to exactly `size` bytes."""
    text = json.dumps(BASE)
    return text + " " * (size - len(text))


def nested(depth):
    """A body nested exactly `depth` deep in total."""
    return "[" * depth + "]" * depth


def nested_field(depth):
    """A request object whose unused field nests to `depth` in total."""
    return with_field(nested(depth - 1))


NON_ASCII = '{"operation": "commit", "note": "é"}'.encode("utf-8")
FF_TOP = b'{"operation": "commit", "x": "\xff"}'
FF_EFFECTS = b'{"operation": "commit", "effects": {"x": "\xff"}}'

# (label, body text) refused by argv and by stdin; each kills a reader rule.
REFUSE_TEXT = [
    ("bad JSON", "{not json"),
    ("65537 bytes", padded(65537)),
    ("NaN in a field", with_field("NaN")),
    ("Infinity in a field", with_field("Infinity")),
    ("-Infinity in a field", with_field("-Infinity")),
    ("NaN as the amount", with_amount("NaN")),
    ("a 33-character integer", with_field("1" * 33)),
    ("a 33-character fraction", with_field("0." + "1" * 31)),
    ("a 33-character integer amount", with_amount("1" * 33)),
    ("1e1000 in a field", with_field("1e1000")),
    ("1e-1000 in a field", with_field("1e-1000")),
    ("-0e999999999 in a field", with_field("-0e999999999")),
    ("1e1000 as the amount", with_amount("1e1000")),
    ("1e-1000 as the amount", with_amount("1e-1000")),
    ("-0e999999999 as the amount", with_amount("-0e999999999")),
    ("a name twice at the top", '{"operation": "commit", "operation": "commit"}'),
    ("a name twice in effects",
     json.dumps(BASE).replace('"spends": false', '"spends": true, "spends": false')),
    ("a name twice in monthly_cost",
     json.dumps(BASE).replace('"amount": 0', '"amount": 60, "amount": 10')),
    ("a name twice in facts", with_field("1")[:-1] + ', "facts": {"a": 1, "a": 1}}'),
    ("33 deep", nested(33)),
    ("33 deep in a field", nested_field(33)),
    ("30000 deep", nested(30000)),
    ("30000 deep in a field", nested_field(30000)),
]
# (label, body text) that must answer: the controls beside the refusals.
ANSWER_TEXT = [
    ("65536 bytes", padded(65536)),
    ("a 32-character integer", with_field("1" * 32)),
    ("a 32-character fraction", with_field("0." + "1" * 30)),
    ("32 deep", nested(32)),
    ("32 deep in a field", nested_field(32)),
    ("each name once", json.dumps(BASE)),
]


def check_cli_refusals(m):
    """Every must-refuse body, by argv and by stdin, for each verb, run
    in-process; the controls answer. Kills sabotage 21 to 26."""
    bad = []
    for label, text in REFUSE_TEXT:
        for verb in VERBS:
            for how, args, data in (("argv", [verb, text], None),
                                    ("stdin", [verb, "-"], text.encode("utf-8"))):
                why = refused(run_main(m, args, data))
                if why:
                    bad.append(f"{verb} {how} {label}: {why}")
    for label, text in ANSWER_TEXT:
        for verb in VERBS:
            for how, args, data in (("argv", [verb, text], None),
                                    ("stdin", [verb, "-"], text.encode("utf-8"))):
                why = answered(run_main(m, args, data))
                if why:
                    bad.append(f"{verb} {how} {label} must answer: {why}")
    for verb in VERBS:
        for label, data in (("0xff at the top", FF_TOP), ("0xff in effects", FF_EFFECTS)):
            why = refused(run_main(m, [verb, "-"], data))
            if why:
                bad.append(f"{verb} stdin {label}: {why}")
        why = answered(run_main(m, [verb, "-"], NON_ASCII))
        if why:
            bad.append(f"{verb} stdin non-ASCII UTF-8 must answer: {why}")
        why = refused(run_main(m, [verb, '{"operation": "commit\udcff"}']))
        if why:
            bad.append(f"{verb} argv lone surrogate: {why}")
    return bad + flags_clear(m)


@contextlib.contextmanager
def patched(module, name, value):
    """Replace one module attribute for the duration."""
    kept = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, kept)


def _raiser(exc):
    def verb(*_args, **_kwargs):
        raise exc
    return verb


def check_cli_single_wrapper(m):
    """A verb that raises, or returns what cannot be written, prints
    nothing and exits 2 (sabotage 19 and 20)."""
    bad = []
    body = json.dumps(BASE)
    for name, verbs in (("decide", ("decide", "explain")), ("classify", ("classify",))):
        for exc in (RecursionError("deep"), MemoryError(), TypeError("t"),
                    ArithmeticError("a")):
            with patched(m, name, _raiser(exc)):
                for verb in verbs:
                    why = refused(run_main(m, [verb, body]))
                    if why:
                        bad.append(f"{verb} with {name} raising {type(exc).__name__}: {why}")
        with patched(m, name, lambda *_a, **_k: {"a": 1, "z": object()}):
            why = refused(run_main(m, [verbs[0], body]))
            if why:
                bad.append(f"{verbs[0]} returning what cannot be serialised: {why}")
    return bad


def check_cli_classify_answers(m):
    """The classify verb reads the tier and reads amounts exactly."""
    bad = []
    full = dict(BASE, tier="prod", account="write-verified", effects=fx(writes=True))
    for tier, want in (("prod", ["production-write"]), ("dev", []), ("qa", []),
                       ("staging", ["production-write"]), (GONE, ["production-write"])):
        request = dict(full, tier=tier)
        if tier is GONE:
            request.pop("tier")
        code, out, _err = run_main(m, ["classify", json.dumps(request)])
        if code != 0 or json.loads(out)["classes"] != want:
            bad.append(f"classify tier {tier!r}: {code} {out[:80]}")
    for raw, want in (("50.000000000000001", ["money"]), ("50.0", []),
                      ("50.01", ["money"]), ("49.99", [])):
        code, out, _err = run_main(m, ["classify", with_amount(raw)])
        if code != 0 or json.loads(out)["classes"] != want:
            bad.append(f"classify amount {raw}: {code} {out[:80]}")
    return bad + flags_clear(m)


CHECKS = (check_serious_cases, check_cost_values, check_must_allow,
          check_pinned_context, check_threshold, check_presence_not_value,
          check_union_with_own_class, check_malformed_account_stops,
          check_cli_classify_answers, check_cli_single_wrapper,
          check_cli_refusals, check_r01_parity, check_benign_effects_parity,
          check_a_serious_answer_never_creates_an_allow,
          check_effects_never_swap_the_account)


@pytest.mark.parametrize("check", CHECKS, ids=[c.__name__ for c in CHECKS])
def test_the_classifier_and_reader_pass(check):
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
    assert set(P.EFFECT_QUESTIONS) == set(BENIGN)
    assert P.DEFAULT_COST_THRESHOLD_USD_MONTH == 50
    assert (P.MAX_REQUEST_BYTES, P.MAX_NUMBER_CHARS, P.MAX_DEPTH) == (65536, 32, 32)
    assert P.REPORT_ONLY is True


def test_one_helper_makes_every_decimal():
    text = T.source()
    assert text.count("decimal.localcontext(_DECIMAL)") == 1
    assert text.count("ctx.create_decimal(") == 1
    assert text.count("create_decimal") == 1
    assert "Decimal(" not in text.replace("decimal.Decimal(", "")


def test_classify_answers_in_the_documented_shape():
    for _cid, effects, tier, _want, _via in SERIOUS_CASES:
        got = P.classify(effects, tier)
        assert set(got) == {"classes", "primary", "reasons", "placed", "cost"}
        assert got["cost"] in ("under", "over", "cannot-estimate")
        assert got["classes"] == sorted(got["classes"])
    for effects in (None, [], "x", 5):
        got = P.classify(effects, "dev")
        assert (got["classes"], got["primary"], got["placed"], got["cost"]) == \
            (["unplaced"], "unplaced", False, "cannot-estimate")
        assert set(got["reasons"]) == {"unplaced"}


def test_without_effects_the_trace_never_mentions_them():
    for cid, request, want in T.CASES:
        done = P.decide(request)
        assert done["outcome"] == want, cid
        assert "effects" not in "\n".join(done["trace"]), cid


def test_the_r01_table_is_the_one_measured():
    assert len(T.CASES) == 1316
    assert not any("effects" in r for _cid, r in DICT_ROWS)
    odd = [cid for cid, r in DICT_ROWS
           if "account" in r and P._pick(r["account"], P.ACCOUNTS) == P.UNKNOWN]
    # D6's exception set over R-01: every such row already stops at rule 2.
    assert len(odd) == 12
    for cid, request in DICT_ROWS:
        if cid in odd:
            assert P.decide(request)["rule"] == "2", cid


def test_the_unplaced_reason_names_an_effect_when_one_is_unplaced():
    known = P.decide(ask(fx(sends_email=True)))["reason"]
    assert "effect has no question" in known and "not in the closed table" not in known
    assert "operation is not in the closed table" in \
        P.decide(ask(BENIGN, op="mystery"))["reason"]


# --- the CLI, as a process ---------------------------------------------------

def _cli(args, data=None):
    return subprocess.run([sys.executable, T.MODULE] + list(args), input=data,
                          capture_output=True, check=False, timeout=60)


def _refused_proc(done):
    err = done.stderr.decode("utf-8", "replace")
    return (done.returncode == 2 and done.stdout == b""
            and len(err.strip().splitlines()) == 1 and "Traceback" not in err)


SUBPROCESS_REFUSE = [
    ("bad JSON", b"{not json"),
    ("65537 bytes", padded(65537).encode("utf-8")),
    ("0xff at the top", FF_TOP),
    ("0xff in effects", FF_EFFECTS),
    ("NaN", with_field("NaN").encode("utf-8")),
    ("1e1000 as the amount", with_amount("1e1000").encode("utf-8")),
    ("a name twice in monthly_cost",
     json.dumps(BASE).replace('"amount": 0', '"amount": 60, "amount": 10').encode("utf-8")),
    ("33 deep", nested(33).encode("utf-8")),
    ("30000 deep", nested(30000).encode("utf-8")),
]


@pytest.mark.parametrize("verb", VERBS)
@pytest.mark.parametrize("label,data", SUBPROCESS_REFUSE, ids=[r[0] for r in SUBPROCESS_REFUSE])
def test_the_cli_process_refuses_by_stdin(verb, label, data):
    assert _refused_proc(_cli([verb, "-"], data)), label


@pytest.mark.parametrize("verb", VERBS)
@pytest.mark.parametrize("label", ["bad JSON", "NaN", "1e1000 as the amount",
                                   "a name twice in monthly_cost", "33 deep"])
def test_the_cli_process_refuses_by_argv(verb, label):
    body = dict(SUBPROCESS_REFUSE)[label].decode("utf-8")
    assert len(body) <= 30000
    assert _refused_proc(_cli([verb, body])), label


@pytest.mark.parametrize("verb", VERBS)
def test_the_cli_process_answers_the_controls(verb):
    for data in (padded(65536).encode("utf-8"), NON_ASCII):
        done = _cli([verb, "-"], data)
        assert done.returncode == 0 and done.stdout.strip() and done.stderr == b""


FULL = {"operation": "commit", "tier": "prod", "presence": "attended",
        "machine_layer": "clear", "account": "write-verified",
        "effects": fx(writes=True)}


def test_the_cli_classifies_a_full_request():
    done = _cli(["classify", json.dumps(FULL)])
    assert done.returncode == 0 and done.stderr == b""
    got = json.loads(done.stdout)
    assert set(got) == {"classes", "primary", "reasons", "placed", "cost"}
    assert got["classes"] == ["production-write"] and got["primary"] == "production-write"
    assert set(got["reasons"]) == set(got["classes"]) and got["placed"] is True
    stdin = _cli(["classify", "-"], json.dumps(FULL).encode("utf-8"))
    assert stdin.returncode == 0 and stdin.stdout == done.stdout


@pytest.mark.parametrize("body", [{"operation": "commit", "tier": "dev"}, [], [FULL], 5])
def test_the_cli_classifies_a_request_without_effects_as_unplaced(body):
    done = _cli(["classify", json.dumps(body)])
    assert done.returncode == 0 and done.stderr == b""
    got = json.loads(done.stdout)
    assert got["classes"] == ["unplaced"] and got["placed"] is False
    assert got["cost"] == "cannot-estimate"


def test_the_cli_ignores_facts_classified_as_and_threshold():
    effects = fx(writes=True, monthly_cost=usd(60))
    plain = _cli(["classify", json.dumps(dict(FULL, effects=effects))]).stdout
    loaded = dict(FULL, effects=effects, threshold=100, costThreshold=100,
                  classified_as="money", facts={"estimate_under_threshold": True})
    assert _cli(["classify", json.dumps(loaded)]).stdout == plain
    assert json.loads(plain)["classes"] == sorted(["money", "production-write"])


def test_the_usage_line_names_classify():
    done = _cli(["frobnicate", "{}"])
    assert done.returncode == 2 and done.stdout == b""
    assert b"decide|explain|classify" in done.stderr


# --- sabotage: each weakened rule must be caught -------------------------------

NL = "\\n"
MUTATIONS = (
    ("1 an unknown effect key is ignored", "    if extra:\n", "    if False:\n"),
    ("2 non-object effects count as benign",
     '        return _verdict({UNPLACED: ["effects is not an object',
     '        return _verdict({}, UNDER)\n'
     '        return _verdict({UNPLACED: ["effects is not an object'),
    ("3a a missing bool answer counts as benign",
     '    if effects.get("spends") is not False:\n',
     '    if effects.get("spends") is True:\n'),
    ("3b a missing enum answer counts as benign",
     '    admin = _pick(effects.get("admin_use"), ADMIN_USES)\n',
     '    admin = _pick(effects.get("admin_use", "none"), ADMIN_USES)\n'),
    ("3c a missing cost estimate counts as zero",
     '    cost = _cost(effects.get("monthly_cost"), limit)\n',
     '    cost = _cost(effects.get("monthly_cost", {"amount": 0, "currency": "USD", '
     '"period": "month"}), limit)\n'),
    ("4 writes that is not a bool is benign in dev and QA",
     "    if writes is not False and (prod or writes is not True):\n",
     "    if writes is not False and prod:\n"),
    ("5 another currency is accepted", ' or currency != "usd"', ""),
    ("6a exactly the threshold is over",
     "    return OVER if amount > limit else UNDER\n",
     "    return OVER if amount >= limit else UNDER\n"),
    ("6b 50.01 passes",
     "    return OVER if amount > limit else UNDER\n",
     "    return OVER if int(amount) > limit else UNDER\n"),
    ("7 a bool amount is accepted",
     "    if isinstance(value, bool) or not isinstance(\n", "    if not isinstance(\n"),
    ("8 a non-finite amount is accepted",
     "        if number.is_finite() and (signed or number >= 0):\n",
     "        if (signed or number >= 0):\n"),
    ("9 an invalid threshold falls back to the default",
     "        return _exact(0), False\n",
     "        return _exact(DEFAULT_COST_THRESHOLD_USD_MONTH), False\n"),
    ("10a a decide request field threshold raises the threshold",
     'classify(req["effects"], tier)', 'classify(req["effects"], tier, req.get("threshold"))'),
    ("10b a decide request field costThreshold raises the threshold",
     'classify(req["effects"], tier)',
     'classify(req["effects"], tier, req.get("cost" + "Threshold"))'),
    ("11 the grantable-profile exception applies in prod",
     "                                and not prod):\n", "                                ):\n"),
    ("12 temporary-listed in prod is not a permission change",
     ' or (prod and perm != "none")', ""),
    ("13 an unknown tier with writes True is not a production write",
     '    prod = _pick(tier, TIERS) not in ("dev", "qa")\n',
     '    prod = _pick(tier, TIERS) == "prod"\n'),
    ("14 effects replace the operation's own classes",
     '        classes = base | frozenset(effect["classes"])\n',
     '        classes = frozenset(effect["classes"])\n'),
    ("15 effects null is treated as absent",
     'if "effects" in req else None', 'if req.get("effects") is not None else None'),
    ("16 the rule-2 run with the effects classes is removed",
     "(base, classes) if classes != base else (classes,)", "(classes,)"),
    ("17 a malformed account passes", "        bad += (UNKNOWN,)\n", "        bad += ()\n"),
    ("18 a null account is treated as absent",
     '    if "account" in req:\n', '    if req.get("account") is not None:\n'),
    ("19 the wrapper catches only ValueError",
     "    except Exception as exc:  # pylint", "    except ValueError as exc:  # pylint"),
    ("20 the answer is streamed instead of built then written",
     f'            out = json.dumps(result, indent=2, sort_keys=True) + "{NL}"\n',
     '            out = ""\n'
     "            json.dump(result, sys.stdout, indent=2, sort_keys=True)\n"),
    ("21 the size cap is removed", "    if len(data) > MAX_REQUEST_BYTES:\n",
     "    if False:\n"),
    ("22 a name given twice keeps the last", "    if len(out) != len(pairs):\n",
     "    if False:\n"),
    ("23 the parse_constant hook is removed",
     "                             parse_constant=_json_constant,\n", ""),
    ("24 the number length cap is removed", "    if len(text) > MAX_NUMBER_CHARS:\n",
     "    if False:\n"),
    ("25 the depth cap is removed", "            if depth > MAX_DEPTH:\n",
     "            if False:\n"),
    ("26 stdin is read as text instead of bytes",
     "sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)", 'sys.stdin.read().encode("utf-8")'),
    ("27 the pinned context is dropped",
     "decimal.localcontext(_DECIMAL)", "decimal.localcontext()"),
    ("28 Inexact and Rounded are untrapped",
     "           decimal.Inexact, decimal.Rounded])", "           ])"),
    ("29 a rejected threshold is printed in the reason",
     '"; the given threshold is not a valid "',
     'f"; the given threshold {threshold!r} is not a valid "'),
    ("30 the classify verb ignores the request's tier",
     'classify(req.get("effects"), _request_tier(req))',
     'classify(req.get("effects"), "prod")'),
    ("31 a Decimal is made by a direct call on the constant",
     "ctx.create_decimal(", "_DECIMAL.create_decimal("),
)


def first_violation(module):
    """The first check that fails for `module`, with its failures; None if
    every check passes. Stops early: a mutant needs only one failure."""
    for check in CHECKS:
        bad = check(module)
        if bad:
            return check.__name__, bad[:3]
    return None


@pytest.mark.parametrize("label,old,new", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_a_weakened_rule_is_caught(label, old, new):
    assert first_violation(T._variant(old, new)) is not None, "nothing caught: " + label
