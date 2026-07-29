#!/usr/bin/env python3
"""
meraki_diff.py -- semantic diffing for Meraki config, plus secret redaction.

Two Meraki-specific behaviors live here because getting either wrong corrupts
production config:

1. Ordered rule sets. Meraki firewall and ACL rules are evaluated in order, so
   position IS semantics. Moving a deny above a permit changes behavior while
   set membership stays identical -- a set-based diff would report "no change"
   on a reorder that breaks the network. diff_rules() is therefore positional.

2. The implicit default rule. GET on L3 firewall rules returns Meraki's
   trailing "Default rule" allow-any entry, but PUT REJECTS it in the payload.
   Unhandled, a snapshot->PUT round trip fails outright and every diff shows a
   phantom removal. strip_default_rule() removes it on read; the caller
   re-derives it implicitly by simply not sending it. Do not "fix" this by
   passing the default rule through -- the API will reject the write.
"""

import copy
import json

SECRET_KEYS = frozenset({
    "psk", "secret", "sharedsecret", "passphrase", "password",
    "privatekey", "authkey", "presharedkey", "radiussecret",
})

REDACTION = "***REDACTED***"

_DEFAULT_RULE_COMMENTS = {"default rule"}


def is_default_l3_rule(rule):
    """True for Meraki's implicit trailing allow-any default rule."""
    if not isinstance(rule, dict):
        return False
    if (rule.get("comment") or "").strip().lower() not in _DEFAULT_RULE_COMMENTS:
        return False
    if (rule.get("policy") or "").lower() != "allow":
        return False
    wildcards = ("srcCidr", "destCidr", "srcPort", "destPort", "protocol")
    return all((rule.get(k) or "").lower() == "any" for k in wildcards)


def strip_default_rule(rules):
    """Drop a trailing implicit default rule. Never mutates the input."""
    out = list(rules or [])
    if out and is_default_l3_rule(out[-1]):
        return out[:-1]
    return out


def redact_secrets(obj):
    """Deep copy with any secret-bearing value replaced."""
    if isinstance(obj, dict):
        return {
            k: (REDACTION if k.lower() in SECRET_KEYS else redact_secrets(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact_secrets(v) for v in obj]
    return copy.copy(obj)


def rule_key(rule):
    """Stable, hashable identity for a rule, independent of dict key order."""
    return json.dumps(rule, sort_keys=True, default=str)


def diff_rules(current, proposed):
    """Positional diff over two ordered rule lists.

    Returns a list of (op, position, rule) where op is one of
    "added" / "removed" / "moved" / "changed" and position is 1-based.
    Empty list means genuinely no change.
    """
    cur = list(current or [])
    prop = list(proposed or [])
    cur_keys = [rule_key(r) for r in cur]
    prop_keys = [rule_key(r) for r in prop]

    if cur_keys == prop_keys:
        return []

    cur_set = set(cur_keys)
    prop_set = set(prop_keys)

    # Same membership, different order: a pure reorder. Report every position
    # that shifted -- this is the case a set-based diff would silently miss.
    if cur_set == prop_set and len(cur_keys) == len(prop_keys):
        return [
            ("moved", i + 1, prop[i])
            for i, (c, p) in enumerate(zip(cur_keys, prop_keys))
            if c != p
        ]

    lines = []
    # Positions present in both lists but holding different rules: an in-place
    # edit rather than an add plus a remove.
    for i in range(min(len(cur_keys), len(prop_keys))):
        if cur_keys[i] == prop_keys[i]:
            continue
        if prop_keys[i] not in cur_set and cur_keys[i] not in prop_set:
            lines.append(("changed", i + 1, prop[i]))

    changed_positions = {pos for _, pos, _ in lines}

    for i, key in enumerate(prop_keys):
        if key not in cur_set and (i + 1) not in changed_positions:
            lines.append(("added", i + 1, prop[i]))
    for i, key in enumerate(cur_keys):
        if key not in prop_set and (i + 1) not in changed_positions:
            lines.append(("removed", i + 1, cur[i]))

    lines.sort(key=lambda item: (item[1], item[0]))
    return lines


_PREFIX = {"added": "+", "removed": "-", "moved": "~", "changed": "~"}


def render_diff(lines):
    """Human-readable diff. Always redacts secrets -- a diff gets pasted into
    tickets, so a PSK must never appear here even though the snapshot keeps it.
    """
    if not lines:
        return "no change"
    out = []
    for op, position, rule in lines:
        safe = redact_secrets(rule)
        body = json.dumps(safe, sort_keys=True, default=str)
        note = " (moved)" if op == "moved" else ""
        out.append(f"{_PREFIX[op]} [{position}]{note} {body}")
    return "\n".join(out)
