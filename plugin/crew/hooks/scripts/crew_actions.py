#!/usr/bin/env python3
"""crew_actions.py: the Actions block of a plan, one closed schema per kind (plan 4.4, R-30).

REPORT-ONLY. Nothing in the plugin imports this module, so it changes no allow
or deny anywhere; `test_crew_actions.py` holds that (no other plugin script
mentions it). It reads its argument and nothing else, and writes nothing. The
planned-action matcher (R-31) and the plan-of-record validator (R-P1) import
`KINDS` and `validate_text` from here; R-39 switches planned actions on one
kind at a time.

Input: one JSON document,

    {"schema": "crew-actions/1", "actions": [ <action>, ... ]}

Extracting that document from the plan-of-record Markdown is R-P1's.

Every action has `id`, `kind`, `form`, `tier` and an optional `uses`, plus the
fields of its kind (`KINDS`). The rules, each a refusal rather than a guess:

* only `form: "exact"`. `"envelope"` is `envelope-not-supported` (envelope
  bounds are R-P1's); any other or missing form is `unsupported-form`;
* `tier` (dev | qa | prod) is required on every kind;
* closed objects: an unknown field, a missing field, a wrong type, an empty
  string and a repeated JSON key at any depth are each refused;
* an int field takes a JSON integer only (`type(v) is int`): `true`, `1.0`
  and `1e0` are `wrong-type`. R-31 compares bound fields exactly;
* no `*` or `?` in any string field, except a workflow `inputs` value and
  `destructive.deletes`, which are literals matched byte for byte;
* an `inputs` key is an identifier (`INPUT_KEY`), else `bad-input-key`;
* money is a decimal string: `amount_cap` is `^[0-9]+(\\.[0-9]{1,2})?$`, > 0;
* two actions with one `id`, or equal in every field but `id`, are refused,
  so an execution can never match two actions.

Entry points. `validate_text(data)` is the one for anything that starts from
text: it parses with a hook that records repeated keys, then validates.
`validate(doc)` takes an already-parsed document; a plain `dict` (built in
code, or from `json.loads`) carries no record of repeated keys, so
`validate` cannot see them in it. Do not `json.loads` and then `validate`.

Error codes: unsupported-schema, unsupported-form, envelope-not-supported,
unknown-kind, unknown-tier, bad-base-kind, unknown-field, missing-field,
wrong-type, empty, bad-format, out-of-range, wildcard, bad-input-key,
duplicate-key, duplicate-id, duplicate-action, needs-irreversible,
unreadable-value (from `validate`); bad-utf8, invalid-json,
non-finite-number (from `parse`).

CLI: `crew_actions.py validate <file|->` exits 0 when the document is valid,
1 when a document was read and is not a valid Actions block (one line per
error on stdout: path, code, reason), and 2 when no document could be read
(stderr). `crew_actions.py kinds` prints the schema.
"""
import datetime
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, List, NamedTuple, Tuple

REPORT_ONLY = True

SCHEMA = "crew-actions/1"
FORM = "exact"
TIERS = ("dev", "qa", "prod")
INT_DIGIT_LIMIT = 4300  # an integer literal longer than this is not read

_MISSING = object()

ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
INPUT_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}")
_PLAIN_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_WORKFLOW = re.compile(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml")
_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_POLICY_ARN = re.compile(r"arn:aws[a-z-]*:iam::(?:aws|[0-9]{12}):policy/[A-Za-z0-9+=,.@_/-]+")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_CURRENCY = re.compile(r"[A-Z]{3}")
_AMOUNT = re.compile(r"[0-9]+(?:\.[0-9]{1,2})?")

Problems = List[Tuple[str, str, str]]  # (path suffix, code, reason)


class Field(NamedTuple):
    """One field of a kind: its JSON type, the rule in words, and its check.

    `check(value)` returns a list of (path suffix, code, reason); empty means
    the value is good. The suffix is "" for the field itself."""
    type: str
    rule: str
    check: Callable[[Any], Problems]


def _text(rule, pattern=None, literal=False, extra=None):
    """A non-empty string; `pattern` must match all of it; `literal` lets it
    hold `*` and `?`; `extra(value)` is a last check returning problems."""
    def check(value):
        if not isinstance(value, str):
            return [("", "wrong-type", "must be a string")]
        if value == "":
            return [("", "empty", "must not be empty")]
        if not literal and ("*" in value or "?" in value):
            return [("", "wildcard", "no wildcard ('*' or '?'): name the one thing exactly")]
        if pattern is not None and not pattern.fullmatch(value):
            return [("", "bad-format", "must be " + rule)]
        if extra is not None:
            return extra(value)
        return []
    return Field("string", rule, check)


def _int(minimum):
    def check(value):
        if type(value) is not int:  # pylint: disable=unidiomatic-typecheck
            return [("", "wrong-type", "must be a JSON integer (not a bool, not 1.0)")]
        if value < minimum:
            return [("", "out-of-range", f"must be >= {minimum}")]
        return []
    return Field("int", f"a JSON integer >= {minimum}", check)


def _timestamp_or_permanent(value):
    if value == "permanent":
        return []
    if _TIMESTAMP.fullmatch(value):
        try:
            datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
            return []
        except ValueError:
            pass
    return [("", "bad-format", "must be YYYY-MM-DDTHH:MM:SSZ (UTC) or 'permanent'")]


def _permission_set(value):
    if _POLICY_ARN.fullmatch(value) or _DIGEST.fullmatch(value):
        return []
    return [("", "bad-format", "must be an IAM policy ARN or sha256:<64 hex>")]


def _check_amount(value):
    if not isinstance(value, str):
        return [("", "wrong-type", "a decimal string such as \"12.50\", never a JSON number")]
    if not _AMOUNT.fullmatch(value):
        return [("", "bad-format", "must be digits with at most two decimals, e.g. \"12.50\"")]
    try:
        positive = Decimal(value) > 0
    except InvalidOperation:
        positive = False
    if not positive:
        return [("", "out-of-range", "must be more than zero")]
    return []


def _key_path(key):
    if isinstance(key, str) and _PLAIN_KEY.fullmatch(key):
        return "." + key
    if isinstance(key, str):
        return "[" + json.dumps(key) + "]"
    return "[" + json.dumps(ascii(key)) + "]"


def _check_inputs(value):
    if not isinstance(value, dict):
        return [("", "wrong-type", "must be an object of input name -> string ({} for none)")]
    out = []
    for key, item in value.items():
        if not isinstance(key, str) or not INPUT_KEY.fullmatch(key):
            out.append((_key_path(key), "bad-input-key",
                        "an input name is a letter or '_', then letters, digits, '-' or '_' (64 at most)"))
        elif not isinstance(item, str):
            out.append((_key_path(key), "wrong-type", "an input value must be a string"))
    return out


TEXT = _text("a non-empty string with no wildcard")
HEX40 = _text("40 lower-case hex digits", _HEX40)
SHA256 = _text("64 lower-case hex digits", _HEX64)
DIGEST = _text("sha256:<64 lower-case hex digits>", _DIGEST)
EXPIRY = _text("YYYY-MM-DDTHH:MM:SSZ or 'permanent'", extra=_timestamp_or_permanent)

DESTRUCTIVE_BASES = ("sql", "cloud-change", "terraform-apply", "workflow-dispatch")

KINDS = {
    "workflow-dispatch": {
        "repo": _text("owner/name", _REPO),
        "workflow": _text("a .yml or .yaml file directly under .github/workflows/", _WORKFLOW),
        "ref": HEX40,
        "inputs": Field("object", "input name -> string value ({} for no inputs)", _check_inputs),
    },
    "terraform-apply": {
        "workspace": TEXT,
        "backend": TEXT,
        "plan_sha256": SHA256,
        "revision": HEX40,
        "manifest_digest": SHA256,
    },
    "permission-grant": {
        "account": TEXT,
        "principal": TEXT,
        "permission_set": _text("an IAM policy ARN or sha256:<64 hex>", extra=_permission_set),
        "scope": TEXT,
        "expiry": EXPIRY,
    },
    "sql": {
        "database": TEXT,
        "statement_sha256": SHA256,
        "max_rows": _int(0),
    },
    "cloud-change": {
        "account": TEXT,
        "service": TEXT,
        "operation": TEXT,
        "resource_id": TEXT,
        "parameter_digest": DIGEST,
    },
    "destructive": {
        "base_kind": _text("one of " + ", ".join(DESTRUCTIVE_BASES)),
        "deletes": _text("what is deleted, in words (a literal)", literal=True),
        "count": _int(1),
        "backup": TEXT,
    },
    "payment": {
        "payee": TEXT,
        "currency": _text("three upper-case letters (ISO 4217)", _CURRENCY),
        "amount_cap": Field("string", "a decimal string > 0, at most two decimals", _check_amount),
        "provider_ref": TEXT,
    },
    "account-create": {
        "name": TEXT,
        "provider": TEXT,
        "permission_profile": TEXT,
        "boundary": TEXT,
        "trust": DIGEST,
        "expiry": EXPIRY,
    },
    "admin-identity-op": {
        "operation": TEXT,
        "payload_digest": DIGEST,
    },
}

COMMON = ("id", "kind", "form", "tier")
USES = _int(1)
IRREVERSIBLE = Field("bool", "true or false; only on destructive", lambda v: [] if type(v) is bool  # pylint: disable=unidiomatic-typecheck
                     else [("", "wrong-type", "must be true or false")])


# --- parse -------------------------------------------------------------------------------------

class _Obj(dict):
    """A JSON object as parsed: a dict that also names its repeated keys."""
    duplicate_keys = ()


class _NonFinite(Exception):
    pass


def _pairs(pairs):
    obj = _Obj()
    repeated = []
    for key, value in pairs:
        if key in obj and key not in repeated:
            repeated.append(key)
        obj[key] = value
    obj.duplicate_keys = tuple(repeated)
    return obj


def _non_finite(token):
    raise _NonFinite(token)


def _bounded_int(literal):
    if len(literal.lstrip("-")) > INT_DIGIT_LIMIT:
        raise ValueError("integer literal too long")
    return int(literal)


def _parse_error(code, reason):
    return None, [{"path": "$", "code": code, "reason": reason}]


def parse(data):
    """Text or bytes -> (doc, errors). Never raises.

    On success `(doc, [])`; on failure `(None, [one error])` at path `$` with
    code `bad-utf8`, `invalid-json` or `non-finite-number`. Bytes are decoded
    as strict UTF-8 and a byte-order mark is refused. Repeated keys are not
    reported here (the hook has no path); `validate` reports them."""
    if isinstance(data, (bytes, bytearray)):
        try:
            data = bytes(data).decode("utf-8")
        except UnicodeDecodeError:
            return _parse_error("bad-utf8", "not UTF-8")
    if not isinstance(data, str):
        return _parse_error("invalid-json", "not text")
    if data.startswith("\ufeff"):
        return _parse_error("bad-utf8", "starts with a byte-order mark")
    try:
        doc = json.loads(data, object_pairs_hook=_pairs,
                         parse_constant=_non_finite,
                         parse_int=_bounded_int)
    except _NonFinite as exc:
        return _parse_error("non-finite-number", f"{exc} is not a JSON number (RFC 8259)")
    except RecursionError:
        return _parse_error("invalid-json", "nested too deep")
    except ValueError as exc:
        return _parse_error("invalid-json", str(exc).split("\n", 1)[0])
    return doc, []


# --- validate ----------------------------------------------------------------------------------

def _duplicates(doc, errors):
    """Every repeated key, anywhere in the tree, at its own path."""
    stack = [(doc, "$")]
    while stack:
        node, path = stack.pop()
        if isinstance(node, dict):
            for key in getattr(node, "duplicate_keys", ()):
                errors.append({"path": path + _key_path(key), "code": "duplicate-key",
                               "reason": "the key appears more than once in this object"})
            for key, child in node.items():
                stack.append((child, path + _key_path(key)))
        elif isinstance(node, list):
            for index, child in enumerate(node):
                stack.append((child, f"{path}[{index}]"))


def _form_problem(form):
    if isinstance(form, str) and form == FORM:
        return None
    if isinstance(form, str) and form == "envelope":
        return "envelope-not-supported", "only exact actions are supported; envelope bounds are R-P1's"
    return "unsupported-form", "form must be \"exact\""


def _fields_for(kind, action, add):
    """The kind's fields, with a destructive action's base fields added; None
    when the base kind cannot be read (its fields are then not checked)."""
    fields = dict(KINDS[kind])
    if kind != "destructive":
        return fields
    fields["irreversible"] = IRREVERSIBLE
    base = action.get("base_kind", _MISSING)
    if base is _MISSING:
        add(".base_kind", "missing-field", "destructive names the kind it is built on")
        return None
    if not isinstance(base, str) or base not in DESTRUCTIVE_BASES:
        add(".base_kind", "bad-base-kind", "must be one of " + ", ".join(DESTRUCTIVE_BASES))
        return None
    fields.update(KINDS[base])
    return fields


def _check_action(action, path, errors):
    """Append the action's problems to `errors`; True when it had none."""
    before = len(errors)

    def add(suffix, code, reason):
        errors.append({"path": path + suffix, "code": code, "reason": reason})

    if not isinstance(action, dict):
        add("", "wrong-type", "an action is an object")
        return False
    form = action.get("form", _MISSING)
    problem = _form_problem(form)
    if problem is not None:
        add(".form", *problem)
    ident = action.get("id", _MISSING)
    if ident is _MISSING:
        add(".id", "missing-field", "every action has an id")
    elif not isinstance(ident, str):
        add(".id", "wrong-type", "an id is a string")
    elif not ID.fullmatch(ident):
        add(".id", "bad-format", "an id is lower-case letters, digits and '-', 64 at most")
    tier = action.get("tier", _MISSING)
    if tier is _MISSING:
        add(".tier", "missing-field", "every action names its tier")
    elif not isinstance(tier, str):
        add(".tier", "wrong-type", "tier is a string")
    elif tier == "":
        add(".tier", "empty", "tier must be one of " + ", ".join(TIERS))
    elif tier not in TIERS:
        add(".tier", "unknown-tier", "tier must be one of " + ", ".join(TIERS))
    if "uses" in action:
        for suffix, code, reason in USES.check(action["uses"]):
            add(".uses" + suffix, code, reason)
    kind = action.get("kind", _MISSING)
    if kind is _MISSING:
        add(".kind", "missing-field", "every action names its kind")
        return False
    if not isinstance(kind, str) or kind not in KINDS:
        add(".kind", "unknown-kind", "kind must be one of " + ", ".join(KINDS))
        return False
    fields = _fields_for(kind, action, add)
    if fields is None:
        return False
    allowed = set(COMMON) | {"uses"} | set(fields)
    for name in action:
        if name not in allowed:
            add(_key_path(name), "unknown-field", f"{kind} has no such field")
    for name, field in fields.items():
        if name not in action:
            if name != "irreversible":
                add(_key_path(name), "missing-field", f"{kind} requires it")
            continue
        for suffix, code, reason in field.check(action[name]):
            add(_key_path(name) + suffix, code, reason)
    if kind == "destructive" and action.get("backup") == "none" \
            and action.get("irreversible") is not True:
        add(".backup", "needs-irreversible", "backup 'none' requires irreversible: true")
    return len(errors) == before


def _normalised(action):
    plain = json.loads(json.dumps(action))
    plain.setdefault("uses", 1)
    return plain


def _validate(doc):
    errors = []
    if not isinstance(doc, dict):
        return [{"path": "$", "code": "wrong-type", "reason": "the document is an object"}], []
    _duplicates(doc, errors)
    for name in doc:
        if name not in ("schema", "actions"):
            errors.append({"path": "$" + _key_path(name), "code": "unknown-field",
                           "reason": "the document has only schema and actions"})
    schema = doc.get("schema", _MISSING)
    if schema is _MISSING:
        errors.append({"path": "$.schema", "code": "missing-field", "reason": "name the schema"})
    elif not isinstance(schema, str) or schema != SCHEMA:
        errors.append({"path": "$.schema", "code": "unsupported-schema",
                       "reason": f"schema must be {SCHEMA!r}"})
    actions = doc.get("actions", _MISSING)
    if actions is _MISSING:
        errors.append({"path": "$.actions", "code": "missing-field", "reason": "list the actions"})
        return errors, []
    if not isinstance(actions, list):
        errors.append({"path": "$.actions", "code": "wrong-type", "reason": "actions is a list"})
        return errors, []
    if not actions:
        errors.append({"path": "$.actions", "code": "empty", "reason": "list at least one action"})
    good = []
    seen_ids = {}
    seen_bound = {}
    for index, action in enumerate(actions):
        path = f"$.actions[{index}]"
        if not _check_action(action, path, errors):
            continue
        plain = _normalised(action)
        if plain["id"] in seen_ids:
            errors.append({"path": path + ".id", "code": "duplicate-id",
                           "reason": f"same id as $.actions[{seen_ids[plain['id']]}]"})
        seen_ids.setdefault(plain["id"], index)
        bound = json.dumps({k: v for k, v in plain.items() if k != "id"}, sort_keys=True)
        if bound in seen_bound:
            errors.append({"path": path, "code": "duplicate-action",
                           "reason": f"equal to $.actions[{seen_bound[bound]}] in every field but id"})
        seen_bound.setdefault(bound, index)
        good.append(plain)
    return errors, good


def validate(doc):
    """An already-parsed document -> {"ok", "errors", "actions"}. Never raises.

    `actions` is the list with `uses` filled in, `[]` unless `ok`. A plain
    `dict` carries no record of repeated keys, so they are only caught when
    the document came from `parse` (use `validate_text` for text)."""
    try:
        errors, good = _validate(doc)
    # Fail closed: any value the walk cannot read is refused, never passed.
    except Exception:  # noqa: BLE001  pylint: disable=broad-except
        errors, good = [{"path": "$", "code": "unreadable-value",
                         "reason": "the value could not be read as an Actions block"}], []
    ok = not errors
    return {"ok": ok, "errors": errors, "actions": good if ok else []}


def validate_text(data):
    """Text or bytes -> the `validate` result; a parse error is `ok: false`."""
    doc, errors = parse(data)
    if errors:
        return {"ok": False, "errors": errors, "actions": []}
    return validate(doc)


def describe():
    """The schema as plain data (the `kinds` subcommand)."""
    return {
        "schema": SCHEMA,
        "report_only": REPORT_ONLY,
        "forms": [FORM],
        "tiers": list(TIERS),
        "common": {"id": "lower-case letters, digits and '-', 64 at most",
                   "kind": "one of the kinds", "form": FORM,
                   "tier": " | ".join(TIERS), "uses": "optional; " + USES.rule + "; default 1"},
        "kinds": {kind: {name: f"{field.type}: {field.rule}" for name, field in fields.items()}
                  for kind, fields in KINDS.items()},
        "destructive": {"base_kinds": list(DESTRUCTIVE_BASES),
                        "adds": "the base kind's fields",
                        "irreversible": IRREVERSIBLE.rule},
    }


_USAGE = "usage: crew_actions.py validate <file|-> | crew_actions.py kinds"


def _refuse(code, reason):
    sys.stderr.write(f"crew_actions: {code}: {reason}; nothing validated\n")
    return 2


def _main(argv):
    if argv == ["kinds"]:
        sys.stdout.write(json.dumps(describe(), indent=2) + "\n")
        return 0
    if len(argv) != 2 or argv[0] != "validate":
        sys.stderr.write(_USAGE + "\n")
        return 2
    try:
        if argv[1] == "-":
            raw = sys.stdin.buffer.read()
        else:
            with open(argv[1], "rb") as handle:
                raw = handle.read()
    except OSError as exc:
        return _refuse("unreadable", exc.strerror or "cannot read the file")
    doc, problems = parse(raw)
    if problems:
        return _refuse(problems[0]["code"], problems[0]["reason"])
    result = validate(doc)
    if result["ok"]:
        sys.stdout.write(f"ok {len(result['actions'])} action(s)\n")
        return 0
    for error in result["errors"]:
        sys.stdout.write(f"{error['path']} {error['code']} {error['reason']}\n")
    return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
