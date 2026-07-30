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
from collections import defaultdict
from difflib import SequenceMatcher

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

    Built on difflib.SequenceMatcher over the rule_key sequences so that a
    reorder is detected as a reorder even when it co-occurs with an add, a
    remove, or an in-place edit in the same call -- the previous version only
    recognized a reorder in isolation (identical set membership, identical
    length) and silently dropped it the moment anything else changed too.

    Approach:
      1. Walk SequenceMatcher's opcodes over cur_keys/prop_keys.
         - "equal" spans contribute nothing.
         - "delete" spans are candidate removals (position in current).
         - "insert" spans are candidate additions (position in proposed).
         - "replace" spans are decomposed the same way: the removed side
           feeds the removal candidates, the inserted side feeds the
           addition candidates. When a replace span has equal length on
           both sides we *also* remember the same-offset (removal,
           addition) pairing as a candidate in-place edit, since that is
           the common case of a single field changing without a reorder.
      2. Match candidate removals against candidate additions by rule_key,
         by count (not just set membership) -- a rule_key shared between
         the two pools is a moved rule, not an add-plus-remove. Duplicate
         rule_keys are handled the same way: two removals and one addition
         of the same key yield one move and one leftover removal.
      3. Whatever a same-offset replace pairing left unclaimed by a move
         (i.e. neither side turned out to be part of a bigger reorder) is
         reported as a "changed" in-place edit instead of an add+remove.
      4. Anything still unclaimed is a genuine "removed" or "added".

    WHAT IS GUARANTEED:
      - A pure reorder (no adds, removes, or edits) is always reported with
        "moved" operations.
      - A reorder is still reported when it co-occurs with unrelated additions,
        removals, or in-place edits to *other* rules.
      - The diff is never empty when the two lists differ (every change is
        reported, though it may not explicitly say "moved" for reordered rules).

    KNOWN LIMITATION:
      When a reorder co-occurs with an in-place edit to one of the *reordered*
      rules themselves, the move detection link breaks and the "moved" label
      may be lost. This is because move detection links a removal to an addition
      by exact content equality: if you change any field of a moved rule, it no
      longer matches its pre-edit counterpart by rule_key, so the link breaks.
      The changed rule is still reported with correct position and full content,
      but the unedited counterpart -- sitting inside a difflib "equal" opcode
      which does not track index shifts -- may not appear in the output at all.

      This is fixable via fuzzy matching of edited rules to their pre-edit
      selves by partial similarity, but fuzzy matching is deliberately not
      implemented. If a future change makes that fix, update this docstring
      and the test that documents this limitation together.

      Example of the limitation:
        allow       = rule("allow", "10.0.0.0/8", comment="permit")
        deny        = rule("deny",  "10.0.0.0/8", comment="block")
        deny_edited = rule("deny",  "10.0.0.0/8", comment="block-edited")

        diff_rules([allow, deny], [deny_edited, allow])
        # actual: [('added', 1, deny_edited), ('removed', 2, deny)]
        # no 'moved' appears, and `allow` -- which now evaluates SECOND
        # instead of first -- does not appear in the output at all.
    """
    cur = list(current or [])
    prop = list(proposed or [])
    cur_keys = [rule_key(r) for r in cur]
    prop_keys = [rule_key(r) for r in prop]

    if cur_keys == prop_keys:
        return []

    removals = []  # [{"pos": 1-based index in current, "rule": ..., "key": ...}]
    additions = []  # [{"pos": 1-based index in proposed, "rule": ..., "key": ...}]
    # (removal_index, addition_index) pairs from same-offset, equal-length
    # replace spans -- candidate in-place edits, used only as a fallback
    # once move-matching has had first claim on both pools.
    equal_pairs = []

    opcodes = SequenceMatcher(None, cur_keys, prop_keys).get_opcodes()
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        if tag == "delete":
            for i in range(i1, i2):
                removals.append({"pos": i + 1, "rule": cur[i], "key": cur_keys[i]})
        elif tag == "insert":
            for j in range(j1, j2):
                additions.append({"pos": j + 1, "rule": prop[j], "key": prop_keys[j]})
        elif tag == "replace":
            if (i2 - i1) == (j2 - j1):
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    r_idx = len(removals)
                    removals.append({"pos": i + 1, "rule": cur[i], "key": cur_keys[i]})
                    a_idx = len(additions)
                    additions.append({"pos": j + 1, "rule": prop[j], "key": prop_keys[j]})
                    equal_pairs.append((r_idx, a_idx))
            else:
                for i in range(i1, i2):
                    removals.append({"pos": i + 1, "rule": cur[i], "key": cur_keys[i]})
                for j in range(j1, j2):
                    additions.append({"pos": j + 1, "rule": prop[j], "key": prop_keys[j]})

    removals_by_key = defaultdict(list)
    for idx, r in enumerate(removals):
        removals_by_key[r["key"]].append(idx)
    additions_by_key = defaultdict(list)
    for idx, a in enumerate(additions):
        additions_by_key[a["key"]].append(idx)

    consumed_removals = set()
    consumed_additions = set()
    moved_lines = []
    for key, r_indices in removals_by_key.items():
        a_indices = additions_by_key.get(key)
        if not a_indices:
            continue
        for r_idx, a_idx in zip(r_indices, a_indices):
            consumed_removals.add(r_idx)
            consumed_additions.add(a_idx)
            addition = additions[a_idx]
            moved_lines.append(("moved", addition["pos"], addition["rule"]))

    changed_lines = []
    for r_idx, a_idx in equal_pairs:
        if r_idx in consumed_removals or a_idx in consumed_additions:
            continue
        consumed_removals.add(r_idx)
        consumed_additions.add(a_idx)
        addition = additions[a_idx]
        changed_lines.append(("changed", addition["pos"], addition["rule"]))

    removed_lines = [
        ("removed", r["pos"], r["rule"])
        for idx, r in enumerate(removals)
        if idx not in consumed_removals
    ]
    added_lines = [
        ("added", a["pos"], a["rule"])
        for idx, a in enumerate(additions)
        if idx not in consumed_additions
    ]

    lines = moved_lines + changed_lines + removed_lines + added_lines
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
