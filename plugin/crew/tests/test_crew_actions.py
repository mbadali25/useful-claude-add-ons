"""`crew_actions.py`: the Actions schema per kind, REPORT-ONLY (plan 4.4, R-30).

The module is a validator, not a hook: "must-allow" means the document must
validate, "must-reject" means it must be refused with the named code at the
named JSON path. The two tables are replayed by `violations(module)`, which the
ordinary tests run against the real module (it must return nothing) and the
sabotage rows run against weakened copies of its source (each must return
something). A rule that no weakened copy is caught breaking is not tested.
(The shared `sabotage*.py` files are review-harness paths that must land alone,
and this module blocks nothing yet, so the in-file form R-01 used is used here.)
"""
import ast
import copy
import json
import os
import random
import subprocess
import sys
import types

import pytest

import context  # noqa: F401  pylint: disable=unused-import

import crew_actions as A  # noqa: E402  pylint: disable=wrong-import-position

SCRIPTS = os.path.dirname(os.path.abspath(A.__file__))
PLUGIN = os.path.dirname(os.path.dirname(SCRIPTS))
MODULE = os.path.join(SCRIPTS, "crew_actions.py")

HEX40 = "0123456789abcdef0123456789abcdef01234567"
HEX64 = "89abcdef" * 8
DIGEST = "sha256:" + "fedcba98" * 8
GONE = object()  # remove the field


def source():
    """The module's text."""
    with open(MODULE, encoding="utf-8") as handle:
        return handle.read()


# Hand-written, not derived from KINDS: every field here is required, and
# `test_the_fixtures_name_every_field_of_every_kind` holds the two together.
FIELDS = {
    "workflow-dispatch": {"repo": "acme/app", "workflow": ".github/workflows/deploy.yml",
                          "ref": HEX40, "inputs": {"env": "qa"}},
    "terraform-apply": {"workspace": "core", "backend": "s3://acme-state/core",
                        "plan_sha256": HEX64, "revision": HEX40, "manifest_digest": HEX64},
    "permission-grant": {"account": "123456789012",
                         "principal": "arn:aws:iam::123456789012:role/deployer",
                         "permission_set": "arn:aws:iam::aws:policy/ReadOnlyAccess",
                         "scope": "us-east-1", "expiry": "2026-12-01T00:00:00Z"},
    "sql": {"database": "orders", "statement_sha256": HEX64, "max_rows": 10},
    "cloud-change": {"account": "123456789012", "service": "s3",
                     "operation": "PutBucketPolicy", "resource_id": "arn:aws:s3:::acme-logs",
                     "parameter_digest": DIGEST},
    "destructive": {"base_kind": "sql", "database": "orders", "statement_sha256": HEX64,
                    "max_rows": 10, "deletes": "stale_sessions rows older than 90 days",
                    "count": 1, "backup": "snapshot orders-2026-11-19"},
    "payment": {"payee": "Example Hosting", "currency": "USD", "amount_cap": "12.50",
                "provider_ref": "price_123"},
    "account-create": {"name": "sandbox-r30", "provider": "aws",
                       "permission_profile": "developer",
                       "boundary": "arn:aws:iam::123456789012:policy/boundary",
                       "trust": DIGEST, "expiry": "permanent"},
    "admin-identity-op": {"operation": "reset-mfa", "payload_digest": DIGEST},
}
KIND_NAMES = list(FIELDS)
DESTRUCTIVE_OWN = ("base_kind", "deletes", "count", "backup")


def act(fixture, /, ident="a1", **over):
    """One valid action of kind `fixture`, with `over` applied (GONE removes)."""
    out = {"id": ident, "kind": fixture, "form": "exact", "tier": "dev"}
    out.update(copy.deepcopy(FIELDS[fixture]))
    for key, value in over.items():
        if value is GONE:
            out.pop(key, None)
        else:
            out[key] = value
    return out


def destructive_over(base, **over):
    out = {"id": "a1", "kind": "destructive", "form": "exact", "tier": "dev",
           "base_kind": base, **copy.deepcopy(FIELDS[base]),
           "deletes": "the rows the statement names", "count": 2, "backup": "snap-1"}
    for key, value in over.items():
        if value is GONE:
            out.pop(key, None)
        else:
            out[key] = value
    return out


def doc(*actions):
    return {"schema": A.SCHEMA, "actions": list(actions)}


def text(value):
    return json.dumps(value)


def one(action):
    return text(doc(action))


def _nine():
    return [act(kind, ident=f"a{n}") for n, kind in enumerate(KIND_NAMES)]


# --- the tables ---------------------------------------------------------------------------------

def _uses_is(n):
    return lambda result: [a["uses"] for a in result["actions"]] == [n]


MUST_ALLOW = [(f"minimal {kind}", one(act(kind)), None) for kind in KIND_NAMES]
MUST_ALLOW += [
    ("uses absent becomes 1", one(act("sql")), _uses_is(1)),
    ("uses given is kept", one(act("sql", uses=3)), _uses_is(3)),
    ("inputs {} means no inputs", one(act("workflow-dispatch", inputs={})), None),
    ("several distinct actions", text(doc(*_nine())),
     lambda result: len(result["actions"]) == len(KIND_NAMES)),
    ("expiry permanent on a grant", one(act("permission-grant", expiry="permanent")), None),
    ("timestamp expiry on account-create",
     one(act("account-create", expiry="2027-01-31T23:59:59Z")), None),
    ("a sha256 permission set", one(act("permission-grant", permission_set=DIGEST)), None),
    ("backup none with irreversible true",
     one(act("destructive", backup="none", irreversible=True)), None),
    ("irreversible false with a backup", one(act("destructive", irreversible=False)), None),
    ("max_rows 0", one(act("sql", max_rows=0)), None),
    ("a wildcard in deletes is a literal",
     one(act("destructive", deletes="rows matching temp_* and a?b")), None),
    ("tier qa", one(act("sql", tier="qa")), None),
    ("tier prod", one(act("sql", tier="prod")), None),
    ("a .yaml workflow", one(act("workflow-dispatch", workflow=".github/workflows/x.yaml")), None),
    ("amount without decimals", one(act("payment", amount_cap="40")), None),
]
MUST_ALLOW += [(f"destructive over {base}", one(destructive_over(base)), None)
               for base in ("sql", "cloud-change", "terraform-apply", "workflow-dispatch")]
MUST_ALLOW += [(f"inputs key {key!r}", one(act("workflow-dispatch", inputs={key: "v"})), None)
               for key in ("env", "_x", "dry-run", "A1", "k" * 64)]
MUST_ALLOW += [(f"inputs value {value!r}", one(act("workflow-dispatch", inputs={"env": value})),
                None) for value in ("", "*", "a?b")]

P0 = "$.actions[0]"


def _reject(label, data, code, path, via="text", once=False):
    return (label, via, data, code, path, once)


MUST_REJECT = []
# form
MUST_REJECT += [_reject(f"envelope on {kind}", one(act(kind, form="envelope")),
                        "envelope-not-supported", P0 + ".form") for kind in KIND_NAMES]
MUST_REJECT += [_reject(f"form {value!r}", one(act("sql", form=value)), "unsupported-form",
                        P0 + ".form")
                for value in (GONE, None, "", "Exact", "partial", ["exact"])]
# kind
MUST_REJECT += [
    _reject("kind deploy", one(act("sql", kind="deploy")), "unknown-kind", P0 + ".kind"),
    _reject("kind missing", one(act("sql", kind=GONE)), "missing-field", P0 + ".kind"),
    _reject("kind wrong case", one(act("sql", kind="SQL")), "unknown-kind", P0 + ".kind"),
    _reject("kind payments", one(act("payment", kind="payments")), "unknown-kind", P0 + ".kind"),
]
# schema and document
MUST_REJECT += [
    _reject("schema missing", text({"actions": [act("sql")]}), "missing-field", "$.schema"),
    _reject("schema version 2", text({"schema": "crew-actions/2", "actions": [act("sql")]}),
            "unsupported-schema", "$.schema"),
    _reject("extra top-level key", text({**doc(act("sql")), "extra": 1}), "unknown-field",
            "$.extra"),
    _reject("actions not a list", text({"schema": A.SCHEMA, "actions": act("sql")}),
            "wrong-type", "$.actions"),
    _reject("actions empty", text(doc()), "empty", "$.actions"),
    _reject("actions missing", text({"schema": A.SCHEMA}), "missing-field", "$.actions"),
    _reject("document a list", text([act("sql")]), "wrong-type", "$"),
    _reject("action not an object", text(doc("sql")), "wrong-type", P0),
]
# every required field removed, one at a time
for _kind in KIND_NAMES:
    for _name in FIELDS[_kind]:
        MUST_REJECT.append(_reject(f"{_kind} without {_name}", one(act(_kind, **{_name: GONE})),
                                   "missing-field", f"{P0}.{_name}"))
for _name in ("id", "tier"):
    MUST_REJECT.append(_reject(f"no {_name}", one(act("sql", **{_name: GONE})), "missing-field",
                               f"{P0}.{_name}"))
for _base in ("cloud-change", "terraform-apply", "workflow-dispatch"):
    for _name in FIELDS[_base]:
        MUST_REJECT.append(_reject(f"destructive over {_base} without {_name}",
                                   one(destructive_over(_base, **{_name: GONE})),
                                   "missing-field", f"{P0}.{_name}"))
# unknown fields
MUST_REJECT += [_reject(f"unknown field on {kind}", one(act(kind, extra="x")), "unknown-field",
                        P0 + ".extra") for kind in KIND_NAMES]
MUST_REJECT += [_reject(f"irreversible on {kind}", one(act(kind, irreversible=True)),
                        "unknown-field", P0 + ".irreversible")
                for kind in KIND_NAMES if kind != "destructive"]
MUST_REJECT.append(_reject("a field of another base kind", one(act("destructive", ref=HEX40)),
                           "unknown-field", P0 + ".ref"))
# wrong types
MUST_REJECT += [
    _reject("int for a string", one(act("workflow-dispatch", repo=5)), "wrong-type",
            P0 + ".repo"),
    _reject("string for max_rows", one(act("sql", max_rows="10")), "wrong-type",
            P0 + ".max_rows"),
    _reject("bool for max_rows", one(act("sql", max_rows=True)), "wrong-type", P0 + ".max_rows"),
    _reject("bool for count", one(act("destructive", count=True)), "wrong-type", P0 + ".count"),
    _reject("bool for uses", one(act("sql", uses=True)), "wrong-type", P0 + ".uses"),
    _reject("float amount_cap", one(act("payment", amount_cap=12.5)), "wrong-type",
            P0 + ".amount_cap"),
    _reject("int amount_cap", one(act("payment", amount_cap=12)), "wrong-type",
            P0 + ".amount_cap"),
    _reject("uses 0", one(act("sql", uses=0)), "out-of-range", P0 + ".uses"),
    _reject("uses -1", one(act("sql", uses=-1)), "out-of-range", P0 + ".uses"),
    _reject("count 0", one(act("destructive", count=0)), "out-of-range", P0 + ".count"),
    _reject("max_rows -1", one(act("sql", max_rows=-1)), "out-of-range", P0 + ".max_rows"),
    _reject("inputs a list", one(act("workflow-dispatch", inputs=["env"])), "wrong-type",
            P0 + ".inputs"),
    _reject("irreversible a string", one(act("destructive", irreversible="yes")), "wrong-type",
            P0 + ".irreversible"),
    _reject("id an int", one(act("sql", ident=7)), "wrong-type", P0 + ".id"),
    _reject("id upper case", one(act("sql", ident="A1")), "bad-format", P0 + ".id"),
    _reject("an empty string field", one(act("sql", database="")), "empty", P0 + ".database"),
    _reject("tier not a string", one(act("sql", tier=1)), "wrong-type", P0 + ".tier"),
]
# a float in an int field, spelled in the JSON text
_SQL = one(act("sql"))
_DESTRUCTIVE = one(act("destructive"))
MUST_REJECT += [
    _reject("max_rows 1.0", _SQL.replace('"max_rows": 10', '"max_rows": 1.0'), "wrong-type",
            P0 + ".max_rows"),
    _reject("max_rows 1e999", _SQL.replace('"max_rows": 10', '"max_rows": 1e999'), "wrong-type",
            P0 + ".max_rows"),
    _reject("count 2.0", _DESTRUCTIVE.replace('"count": 1', '"count": 2.0'), "wrong-type",
            P0 + ".count"),
    _reject("uses 1.0", _SQL.replace('"max_rows": 10', '"max_rows": 10, "uses": 1.0'),
            "wrong-type", P0 + ".uses"),
    _reject("uses 1e0", _SQL.replace('"max_rows": 10', '"max_rows": 10, "uses": 1e0'),
            "wrong-type", P0 + ".uses"),
    _reject("python float max_rows", doc(act("sql", max_rows=1.0)), "wrong-type",
            P0 + ".max_rows", via="doc"),
    _reject("python float uses", doc(act("sql", uses=1.0)), "wrong-type", P0 + ".uses",
            via="doc"),
]
# formats
MUST_REJECT += [
    _reject("39-hex ref", one(act("workflow-dispatch", ref=HEX40[:39])), "bad-format",
            P0 + ".ref"),
    _reject("41-hex ref", one(act("workflow-dispatch", ref=HEX40 + "0")), "bad-format",
            P0 + ".ref"),
    _reject("upper-case sha256", one(act("sql", statement_sha256=HEX64.upper())), "bad-format",
            P0 + ".statement_sha256"),
    _reject("63-hex sha256", one(act("sql", statement_sha256=HEX64[:63])), "bad-format",
            P0 + ".statement_sha256"),
    _reject("digest without prefix", one(act("admin-identity-op", payload_digest=HEX64)),
            "bad-format", P0 + ".payload_digest"),
    _reject("workflow outside .github/workflows",
            one(act("workflow-dispatch", workflow=".github/deploy.yml")), "bad-format",
            P0 + ".workflow"),
    _reject("workflow in a subfolder",
            one(act("workflow-dispatch", workflow=".github/workflows/a/b.yml")), "bad-format",
            P0 + ".workflow"),
    _reject("workflow not yaml", one(act("workflow-dispatch", workflow=".github/workflows/a.sh")),
            "bad-format", P0 + ".workflow"),
    _reject("repo without owner", one(act("workflow-dispatch", repo="app")), "bad-format",
            P0 + ".repo"),
    _reject("timestamp without Z", one(act("permission-grant", expiry="2026-12-01T00:00:00")),
            "bad-format", P0 + ".expiry"),
    _reject("impossible date", one(act("permission-grant", expiry="2026-02-30T00:00:00Z")),
            "bad-format", P0 + ".expiry"),
    _reject("one-digit day", one(act("permission-grant", expiry="2026-12-1T00:00:00Z")),
            "bad-format", P0 + ".expiry"),
    _reject("amount 0", one(act("payment", amount_cap="0")), "out-of-range", P0 + ".amount_cap"),
    _reject("amount 0.00", one(act("payment", amount_cap="0.00")), "out-of-range",
            P0 + ".amount_cap"),
    _reject("amount 1.234", one(act("payment", amount_cap="1.234")), "bad-format",
            P0 + ".amount_cap"),
    _reject("amount 1e3", one(act("payment", amount_cap="1e3")), "bad-format",
            P0 + ".amount_cap"),
    _reject("currency usd", one(act("payment", currency="usd")), "bad-format",
            P0 + ".currency"),
    _reject("permission set not an ARN", one(act("permission-grant", permission_set="ReadOnly")),
            "bad-format", P0 + ".permission_set"),
]
# wildcards: every string field but the literal ones
for _kind in KIND_NAMES:
    for _name, _value in FIELDS[_kind].items():
        if isinstance(_value, str) and _name not in ("deletes", "amount_cap", "base_kind"):
            for _char in "*?":
                MUST_REJECT.append(_reject(f"{_char!r} in {_kind}.{_name}",
                                           one(act(_kind, **{_name: _value[:3] + _char})),
                                           "wildcard", f"{P0}.{_name}"))
# inputs keys
for _key, _path in (("", '[""]'), ("*", '["*"]'), ("env*", '["env*"]'), ("a?", '["a?"]'),
                    ("1env", '["1env"]'), ("-env", '["-env"]'), ("my key", '["my key"]'),
                    ("a.b", '["a.b"]'), ("a/b", '["a/b"]'), ("k" * 65, "." + "k" * 65)):
    MUST_REJECT.append(_reject(f"inputs key {_key[:8]!r}",
                               one(act("workflow-dispatch", inputs={"env": "qa", _key: "v"})),
                               "bad-input-key", P0 + ".inputs" + _path))
MUST_REJECT.append(_reject("inputs value not a string",
                           one(act("workflow-dispatch", inputs={"env": 1})), "wrong-type",
                           P0 + ".inputs.env"))
# repeated JSON keys
_WD = one(act("workflow-dispatch"))
MUST_REJECT += [
    _reject("repeated top-level key",
            _SQL.replace('"schema": ', '"schema": "crew-actions/1", "schema": ', 1),
            "duplicate-key", "$.schema"),
    _reject("repeated key in an action", _SQL.replace('"tier": "dev"', '"tier": "dev", "tier": "dev"'),
            "duplicate-key", P0 + ".tier"),
    _reject("repeated key in inputs", _WD.replace('{"env": "qa"}', '{"env": "qa", "env": "qa"}'),
            "duplicate-key", P0 + ".inputs.env"),
    _reject("repeated key in an unknown field",
            _SQL.replace('"tier": "dev"', '"tier": "dev", "note": {"a": 1, "a": 1}'),
            "duplicate-key", P0 + ".note.a"),
    _reject("repeated key in a list in an unknown field",
            _SQL.replace('"tier": "dev"', '"tier": "dev", "note": [{"b": 1, "b": 2}]'),
            "duplicate-key", P0 + ".note[0].b"),
    _reject("a key three times is reported once",
            _SQL.replace('"tier": "dev"', '"tier": "dev", "tier": "dev", "tier": "dev"'),
            "duplicate-key", P0 + ".tier", once=True),
]
# not JSON numbers, not readable text
MUST_REJECT += [_reject(f"{token} in max_rows", _SQL.replace('"max_rows": 10',
                                                             f'"max_rows": {token}'),
                        "non-finite-number", "$") for token in ("NaN", "Infinity", "-Infinity")]
MUST_REJECT += [
    _reject("NaN at top level", _SQL.replace('"schema"', '"x": NaN, "schema"', 1),
            "non-finite-number", "$"),
    _reject("a byte-order mark", b"\xef\xbb\xbf" + _SQL.encode("utf-8"), "bad-utf8", "$"),
    _reject("not UTF-8", b"\xff" + _SQL.encode("utf-8"), "bad-utf8", "$"),
    _reject("truncated", _SQL[:-1], "invalid-json", "$"),
    _reject("empty text", "", "invalid-json", "$"),
]
# duplicates across actions
MUST_REJECT += [
    _reject("two actions, one id", text(doc(act("sql"), act("payment"))), "duplicate-id",
            "$.actions[1].id"),
    _reject("equal but for id", text(doc(act("sql"), act("sql", ident="a2"))),
            "duplicate-action", "$.actions[1]"),
    _reject("equal once uses is filled in",
            text(doc(act("sql"), act("sql", ident="a2", uses=1))), "duplicate-action",
            "$.actions[1]"),
]
# destructive rules and tiers
MUST_REJECT += [
    _reject("backup none without irreversible", one(act("destructive", backup="none")),
            "needs-irreversible", P0 + ".backup"),
    _reject("backup none, irreversible false",
            one(act("destructive", backup="none", irreversible=False)), "needs-irreversible",
            P0 + ".backup"),
    _reject("base kind payment", one(act("destructive", base_kind="payment")), "bad-base-kind",
            P0 + ".base_kind"),
    _reject("base kind destructive", one(act("destructive", base_kind="destructive")),
            "bad-base-kind", P0 + ".base_kind"),
    _reject("tier production", one(act("sql", tier="production")), "unknown-tier", P0 + ".tier"),
    _reject("tier empty", one(act("sql", tier="")), "empty", P0 + ".tier"),
]


def violations(module):
    """The rows of the two tables that `module` gets wrong."""
    bad = []
    for label, data, check in MUST_ALLOW:
        try:
            result = module.validate_text(data)
        except Exception as exc:  # noqa: BLE001  pylint: disable=broad-except
            bad.append(f"allow {label}: raised {exc!r}")
            continue
        if not result["ok"] or (check is not None and not check(result)):
            bad.append(f"allow {label}: {result['errors'][:3]}")
    for label, via, data, code, path, once in MUST_REJECT:
        try:
            result = module.validate_text(data) if via == "text" else module.validate(data)
        except Exception as exc:  # noqa: BLE001  pylint: disable=broad-except
            bad.append(f"reject {label}: raised {exc!r}")
            continue
        hits = [e for e in result["errors"] if (e["code"], e["path"]) == (code, path)]
        if result["ok"] or not hits or (once and len(hits) != 1) or result["actions"]:
            bad.append(f"reject {label}: wanted {code} at {path}, got {result['errors'][:3]}")
    return bad


def test_the_real_module_gets_every_row_right():
    assert violations(A) == []


def test_the_tables_are_not_trivially_small():
    assert len(MUST_ALLOW) >= 30 and len(MUST_REJECT) >= 150


def test_the_fixtures_name_every_field_of_every_kind():
    assert set(FIELDS) == set(A.KINDS)
    for kind, fields in A.KINDS.items():
        want = set(fields) | (set(FIELDS["sql"]) if kind == "destructive" else set())
        assert set(FIELDS[kind]) == want, kind


def test_every_error_names_a_path_a_code_and_a_reason():
    for _, via, data, _, _, _ in MUST_REJECT:
        result = A.validate_text(data) if via == "text" else A.validate(data)
        for error in result["errors"]:
            assert set(error) == {"path", "code", "reason"}
            assert error["path"].startswith("$") and error["code"] and error["reason"]


# --- parse and the validate contract ------------------------------------------------------------

def test_parse_returns_the_document_for_text_and_bytes():
    for data in (_SQL, _SQL.encode("utf-8")):
        parsed, errors = A.parse(data)
        assert errors == [] and parsed == doc(act("sql"))


@pytest.mark.parametrize("data,code", [
    (b"\xff\xfe{}", "bad-utf8"), (b"\xef\xbb\xbf{}", "bad-utf8"), ("\ufeff{}", "bad-utf8"),
    ("", "invalid-json"), ('{"schema": ', "invalid-json"), ("[" * 100000, "invalid-json"),
    ('{"n": ' + "9" * 5000 + "}", "invalid-json"), ("[NaN]", "non-finite-number"),
    ("[-Infinity]", "non-finite-number"), (None, "invalid-json"), (12, "invalid-json")],
    # Short ids: the default id of the 100000-bracket input overflows Windows' 32767-char env limit.
    ids=["ff-fe", "bom-bytes", "bom-text", "empty", "truncated", "too-deep", "long-int", "nan",
         "neg-infinity", "none", "int"])
def test_parse_never_raises_and_returns_one_error(data, code):
    parsed, errors = A.parse(data)
    assert parsed is None
    assert [(e["path"], e["code"]) for e in errors] == [("$", code)]


def test_a_plain_dict_carries_no_duplicate_evidence_but_text_does():
    assert A.validate(json.loads(_SQL.replace('"tier": "dev"', '"tier": "dev", "tier": "dev"')))["ok"]
    assert not A.validate_text(_SQL.replace('"tier": "dev"', '"tier": "dev", "tier": "dev"'))["ok"]


def test_validate_normalises_only_uses():
    action = act("workflow-dispatch")
    result = A.validate(doc(action))
    assert result["actions"] == [{**action, "uses": 1}]
    assert "uses" not in action  # the input is not changed


@pytest.mark.parametrize("value", [None, 1, "x", [], {}, {"actions": None}, [[[]]], object(),
                                   {1: 2}, {"schema": A.SCHEMA, "actions": [{1: 2}]}])
def test_validate_never_raises_on_odd_values(value):
    result = A.validate(value)
    assert set(result) == {"ok", "errors", "actions"} and result["ok"] is False


def test_validate_survives_a_deep_python_value():
    deep = []
    for _ in range(50000):
        deep = [deep]
    result = A.validate({"schema": A.SCHEMA, "actions": [act("sql", note=deep)]})
    assert result["ok"] is False


# --- fuzz -------------------------------------------------------------------------------------------

def _random_value(rng, depth=0):
    choice = rng.randrange(7 if depth < 4 else 5)
    if choice == 0:
        return None
    if choice == 1:
        return rng.random() < 0.5
    if choice == 2:
        return rng.randint(-5, 5)
    if choice == 3:
        return rng.choice([0.0, 1.0, -2.5, float("nan"), float("inf")])
    if choice == 4:
        return rng.choice(["", "*", "exact", "dev", "sql", A.SCHEMA, "a1", "envelope"])
    if choice == 5:
        return [_random_value(rng, depth + 1) for _ in range(rng.randrange(3))]
    keys = ["schema", "actions", "id", "kind", "form", "tier", "uses", "x"]
    return {rng.choice(keys): _random_value(rng, depth + 1) for _ in range(rng.randrange(4))}


def _never_valid(rng, depth=0):
    """A value no field accepts (no str, no int; containers non-empty)."""
    choice = rng.randrange(5 if depth < 3 else 3)
    if choice == 0:
        return None
    if choice == 1:
        return rng.random() < 0.5
    if choice == 2:
        return rng.choice([0.5, 1.0, float("nan")])
    if choice == 3:
        return [_never_valid(rng, depth + 1) for _ in range(1 + rng.randrange(2))]
    return {f"k{n}": _never_valid(rng, depth + 1) for n in range(1 + rng.randrange(2))}


def _nodes(value, trail=()):
    yield trail
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _nodes(child, trail + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _nodes(child, trail + (index,))


def _replaced(value, trail, new):
    if not trail:
        return new
    out = copy.deepcopy(value)
    node = out
    for step in trail[:-1]:
        node = node[step]
    node[trail[-1]] = new
    return out


VALID_DOCS = [doc(act(kind)) for kind in KIND_NAMES] + [doc(*_nine())]


def test_fuzz_validate_returns_the_shape_and_accepts_only_valid_documents():
    rng = random.Random(0)
    for valid in VALID_DOCS:
        assert A.validate(valid)["ok"]
    for _ in range(300):
        value = _random_value(rng)
        result = A.validate(value)
        assert set(result) == {"ok", "errors", "actions"}
        assert not result["ok"] or value in VALID_DOCS
    for _ in range(300):
        valid = rng.choice(VALID_DOCS)
        trail = rng.choice(list(_nodes(valid)))
        value = _replaced(valid, trail, _never_valid(rng))
        result = A.validate(value)
        assert set(result) == {"ok", "errors", "actions"}
        assert not result["ok"], (trail, value)


def test_fuzz_validate_text_refuses_every_prefix_and_random_bytes():
    rng = random.Random(0)
    for valid in VALID_DOCS:
        serial = text(valid)
        assert A.validate_text(serial)["ok"]
        for cut in range(len(serial)):
            assert not A.validate_text(serial[:cut].strip())["ok"], cut
    for _ in range(300):
        data = bytes(rng.randrange(256) for _ in range(rng.randrange(40)))
        assert not A.validate_text(data)["ok"]


# --- the CLI ----------------------------------------------------------------------------------------

def _cli(*args, stdin=b""):
    return subprocess.run([sys.executable, MODULE, *args], input=stdin, capture_output=True,
                          check=False, timeout=60)


def _write(tmp_path, data):
    path = tmp_path / "actions.json"
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return str(path)


def test_cli_valid_document_exits_0(tmp_path):
    done = _cli("validate", _write(tmp_path, _SQL))
    assert done.returncode == 0 and done.stdout.decode().startswith("ok 1 ")


@pytest.mark.parametrize("args,data,code", [
    (("frobnicate",), None, None), (("validate",), None, None), ((), None, None),
    (("validate", "MISSING"), None, "unreadable"),
    (("validate", "FILE"), b"\xff{}", "bad-utf8"),
    (("validate", "FILE"), _SQL[:-3], "invalid-json"),
    (("validate", "FILE"), _SQL.replace('"max_rows": 10', '"max_rows": NaN'),
     "non-finite-number")])
def test_cli_exits_2_when_no_document_could_be_read(tmp_path, args, data, code):
    path = _write(tmp_path, data) if data is not None else str(tmp_path / "missing.json")
    args = tuple(path if a in ("FILE", "MISSING") else a for a in args)
    done = _cli(*args)
    assert done.returncode == 2 and done.stdout == b""
    err = done.stderr.decode()
    assert err.strip()
    if code:
        assert err.startswith(f"crew_actions: {code}: ") and "nothing validated" in err


@pytest.mark.parametrize("data,line", [
    (_SQL.replace('"tier": "dev"', '"tier": "dev", "tier": "dev"'),
     "$.actions[0].tier duplicate-key "),
    (one(act("sql", form="envelope")), "$.actions[0].form envelope-not-supported ")])
def test_cli_exits_1_for_a_document_that_is_not_a_valid_actions_block(tmp_path, data, line):
    done = _cli("validate", _write(tmp_path, data))
    assert done.returncode == 1
    assert line in done.stdout.decode()


def test_cli_reads_stdin_for_dash():
    done = _cli("validate", "-", stdin=_SQL.encode("utf-8"))
    assert done.returncode == 0 and done.stdout.decode().startswith("ok 1 ")


def test_cli_kinds_prints_the_schema():
    done = _cli("kinds")
    assert done.returncode == 0
    described = json.loads(done.stdout.decode())
    assert set(described["kinds"]) == set(A.KINDS) and described["forms"] == ["exact"]


# --- inert --------------------------------------------------------------------------------------

def _plugin_sources():
    for root, dirs, files in os.walk(PLUGIN):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", "tests", "_test")]
        for name in files:
            if name.endswith((".py", ".sh", ".ps1", ".json")):
                yield os.path.join(root, name)


def test_nothing_in_the_plugin_reaches_the_actions_schema_yet():
    me = os.path.normcase(MODULE)
    hits = []
    for path in _plugin_sources():
        if os.path.normcase(path) == me:
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            if "crew_actions" in handle.read():
                hits.append(os.path.relpath(path, PLUGIN))
    assert hits == [], "the schema is report-only until R-31 imports it"


def test_the_module_imports_only_the_standard_library():
    names = set()
    for node in ast.walk(ast.parse(source())):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names <= {"datetime", "decimal", "json", "re", "sys", "typing"}, names


def test_the_module_declares_itself_report_only():
    assert A.REPORT_ONLY is True
    assert "REPORT-ONLY" in source()


def test_the_module_does_nothing_when_imported():
    done = subprocess.run([sys.executable, "-c", "import crew_actions"], cwd=SCRIPTS,
                          capture_output=True, text=True, check=False, timeout=60)
    assert done.returncode == 0 and done.stdout == "" and done.stderr == ""


# --- sabotage: each weakened rule must be caught --------------------------------------------------

MUTATIONS = (
    ("envelope is accepted", "    if isinstance(form, str) and form == FORM:\n",
     '    if isinstance(form, str) and form in (FORM, "envelope"):\n'),
    ("a missing form is exact", 'form = action.get("form", _MISSING)',
     'form = action.get("form", FORM)'),
    ("the unknown-field check is dropped", "        if name not in allowed:\n",
     "        if False:\n"),
    ("the duplicate-key hook is dropped", "object_pairs_hook=_pairs,", ""),
    ("the duplicate walk stops at unknown fields",
     "            for key, child in node.items():\n",
     "            for key, child in node.items():\n"
     '                if key not in ("actions", "inputs") and isinstance(child, (dict, list)):\n'
     "                    continue\n"),
    ("a bool counts as an int",
     "        if type(value) is not int:  # pylint: disable=unidiomatic-typecheck\n",
     "        if not isinstance(value, int):\n"),
    ("a whole float counts as an int",
     "        if type(value) is not int:  # pylint: disable=unidiomatic-typecheck\n",
     "        if not isinstance(value, (int, float)):\n"),
    ("the wildcard check is skipped",
     '        if not literal and ("*" in value or "?" in value):\n', "        if False:\n"),
    ("the inputs key check is dropped",
     "        if not isinstance(key, str) or not INPUT_KEY.fullmatch(key):\n",
     "        if False:\n"),
    ("the key pattern allows an empty key",
     'INPUT_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}")',
     'INPUT_KEY = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_-]{0,63})?")'),
    ("sql loses its max_rows field", '        "max_rows": _int(0),\n', ""),
    ("a JSON-number amount_cap is accepted",
     '    if not isinstance(value, str):\n        return [("", "wrong-type", "a decimal string',
     "    if isinstance(value, (int, float)) and value > 0:\n        return []\n"
     '    if not isinstance(value, str):\n        return [("", "wrong-type", "a decimal string'),
    ("the duplicate-action check is dropped", "        if bound in seen_bound:\n",
     "        if False:\n"),
    ("an unknown tier is read as dev", "    elif tier not in TIERS:\n", "    elif False:\n"),
    ("parse_constant is dropped", "parse_constant=_non_finite,", ""),
    ("the duplicate-id check is dropped", '        if plain["id"] in seen_ids:\n',
     "        if False:\n"),
    ("backup none needs no irreversible", '    if kind == "destructive" and action.get("backup") == "none" \\\n',
     "    if False \\\n"),
    ("payment is a destructive base",
     'DESTRUCTIVE_BASES = ("sql", "cloud-change", "terraform-apply", "workflow-dispatch")',
     'DESTRUCTIVE_BASES = ("sql", "cloud-change", "terraform-apply", "workflow-dispatch",'
     ' "payment")'),
    ("a missing field is not reported", '            if name != "irreversible":\n',
     "            if False:\n"),
    ("the schema version is not checked",
     "    elif not isinstance(schema, str) or schema != SCHEMA:\n", "    elif False:\n"),
    ("a byte-order mark is accepted", '    if data.startswith("\\ufeff"):\n',
     "    if False:\n"),
    ("a 39- or 41-hex ref passes", '_HEX40 = re.compile(r"[0-9a-f]{40}")',
     '_HEX40 = re.compile(r"[0-9a-f]{39,41}")'),
    ("a zero amount passes", "        positive = Decimal(value) > 0\n",
     "        positive = Decimal(value) >= 0\n"),
    ("an empty string passes", '        if value == "":\n', "        if False:\n"),
    ("a timestamp is not held to its digits", "    if _TIMESTAMP.fullmatch(value):\n",
     "    if True:\n"),
    ("an impossible date passes",
     '            datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")\n', ""),
    ("a workflow may sit anywhere", r'_WORKFLOW = re.compile(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml")',
     r'_WORKFLOW = re.compile(r".*\.ya?ml")'),
    ("irreversible is allowed on every kind", '    if kind != "destructive":\n        return fields\n',
     '    fields["irreversible"] = IRREVERSIBLE\n    if kind != "destructive":\n        return fields\n'),
)


def _variant(old, new):
    text_ = source()
    assert text_.count(old) == 1, f"mutation target moved: {old!r}"
    name = "crew_actions_mutant"
    module = types.ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(text_.replace(old, new), name, "exec"),  # pylint: disable=exec-used
             module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.mark.parametrize("label,old,new", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_a_weakened_rule_is_caught(label, old, new):
    bad = violations(_variant(old, new))
    assert bad, "nothing caught: " + label
