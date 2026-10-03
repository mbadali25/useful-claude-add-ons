"""`/crew:verify --stamp-reach`: declare `reach` on the rules that have none (L-0562).

A rule without `reach` is classified on every Stop by `verify_record.scan_reach`
(CONFIG.md §19): a plain local command runs, anything with shell syntax, a
remote verb or a wrapper script is deferred and recorded as skipped. A map
written before `reach` existed can therefore run nothing on Stop while its
verified-at marker advances (D10, docs/review/09-qa-standards-crew.md).

WHAT IT PROPOSES, per undeclared rule, from the gate's own classifier:

  local    -> "local"    the gate already runs it; declaring changes nothing
  verb     -> "network"  the gate already defers it; declaring changes nothing
  syntax   -> nothing    only a person can say whether it is safe on every Stop
  wrapper  -> nothing    ditto

So `--apply` is behaviour-preserving by construction: it writes down what the
gate already does. Making a deferred rule run is a decision, and it is taken
only by `--set N=local` (or network/host), naming the rule by its index.

HOW IT WRITES. `.crew/verify.json` is hand-formatted and often tracked, so it
is never re-serialised: each `"reach": "..."` is inserted as text right after
its rule's opening brace, the result is parsed back and compared with the
original plus exactly the new keys, and only then written, via a temp file
and `os.replace`. Any mismatch writes nothing and exits 1.

Usage: verify_reach.py [--root DIR] [--map PATH] [--apply] [--set N=REACH ...]
Exit: 0 printed or written; 1 refused (unreadable map, a bad --set, or the
text insert did not round-trip); 2 usage.
"""
import argparse
import json
import os
import sys

import verify_record

REACHES = ("local", "network", "host")
PROPOSE = {"local": "local", "verb": "network"}


def load(path):
    """(text, map) or raises ValueError naming why the map cannot be used."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    try:
        vmap = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(vmap, dict) or not isinstance(vmap.get("rules"), list):
        raise ValueError(f"{path} has no `rules` list")
    return text, vmap


def plan(vmap, root):
    """One entry per rule with no `reach`: index, classifier status, detail,
    and the proposed value (None when only a person can decide)."""
    out = []
    for i, rule in enumerate(vmap["rules"]):
        if not isinstance(rule, dict) or "reach" in rule:
            continue
        run = [c for c in rule.get("run") or [] if isinstance(c, str)]
        status, detail = verify_record.scan_reach(run, root)
        out.append({"index": i, "status": status, "detail": detail,
                    "propose": PROPOSE.get(status), "paths": rule.get("paths") or []})
    return out


def parse_sets(values, vmap):
    """{index: reach} from `--set N=REACH`. Raises ValueError on a bad one."""
    chosen = {}
    for item in values or []:
        index, _, reach = item.partition("=")
        if not index.isdigit() or reach not in REACHES:
            raise ValueError(f"--set {item!r}: expected N=local|network|host")
        n = int(index)
        rules = vmap["rules"]
        if n >= len(rules) or not isinstance(rules[n], dict):
            raise ValueError(f"--set {item!r}: there is no rule {n}")
        if "reach" in rules[n]:
            raise ValueError(f"--set {item!r}: rule {n} already declares reach "
                             f"{rules[n]['reach']!r}; edit it by hand")
        chosen[n] = reach
    return chosen


def _skip(text, pos, chars=" \t\r\n,"):
    while pos < len(text) and text[pos] in chars:
        pos += 1
    return pos


def _rule_offsets(text):
    """Offset of each rule object's opening brace, in `rules` order. Walks the
    top-level object key by key with the JSON decoder, so a string that merely
    contains "rules" (a `why`, say) is never mistaken for the key."""
    decoder = json.JSONDecoder()
    pos = _skip(text, 0)
    if text[pos] != "{":
        raise ValueError("the map is not a JSON object")
    pos += 1
    while True:
        pos = _skip(text, pos)
        if text[pos] == "}":
            raise ValueError("could not find the `rules` array")
        key, pos = decoder.raw_decode(text, pos)
        pos = _skip(text, pos, " \t\r\n")
        pos = _skip(text, pos + 1, " \t\r\n")  # past the colon
        if key == "rules":
            break
        _, pos = decoder.raw_decode(text, pos)
    offsets, pos = [], pos + 1
    while True:
        pos = _skip(text, pos)
        if text[pos] == "]":
            return offsets
        offsets.append(pos)
        _, pos = decoder.raw_decode(text, pos)


def stamp_text(text, vmap, chosen):
    """The map's text with `"reach": v` inserted into each chosen rule, checked
    to parse back to exactly the original plus those keys."""
    offsets = _rule_offsets(text)
    if len(offsets) != len(vmap["rules"]):
        raise ValueError("rule count from the text disagrees with the parsed map")
    out = text
    for index in sorted(chosen, reverse=True):
        at = offsets[index]
        if out[at] != "{":
            raise ValueError(f"rule {index} is not an object")
        out = out[:at + 1] + f' "reach": "{chosen[index]}",' + out[at + 1:]
    expected = json.loads(text)
    for index, reach in chosen.items():
        expected["rules"][index]["reach"] = reach
    if json.loads(out) != expected:
        raise ValueError("the inserted text did not round-trip; nothing written")
    return out


def write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)


def render(entries, chosen):
    lines = ["| Rule | Paths | Gate today | Proposed | Why |", "|---|---|---|---|---|"]
    for e in entries:
        today = "runs" if e["status"] == "local" else "SKIPPED on Stop"
        why = e["status"] + (f": {e['detail']}" if e["detail"] else "")
        proposed = chosen.get(e["index"]) or e["propose"] or "**you decide**"
        paths = ", ".join(str(p) for p in e["paths"][:2]).replace("|", "\\|")
        lines.append(f"| {e['index']} | {paths} | {today} | {proposed} | {why.replace('|', chr(92) + '|')} |")
    undecided = [e["index"] for e in entries if not e["propose"] and e["index"] not in chosen]
    tail = []
    if undecided:
        tail.append(f"undecided: rules {', '.join(map(str, undecided))}. `local` runs a rule on every "
                    "Stop with no inspection; `network`/`host` keep it deferred. Choose with "
                    "--set N=local|network|host.")
    return "\n".join(lines + [""] + tail) + "\n"


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--map", help="default: <root>/.crew/verify.json")
    parser.add_argument("--apply", action="store_true",
                        help="write the proposals and every --set (default: dry run)")
    parser.add_argument("--set", action="append", metavar="N=REACH",
                        help="declare rule N's reach yourself; repeatable")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    path = args.map or os.path.join(root, ".crew", "verify.json")
    try:
        text, vmap = load(path)
        chosen = parse_sets(args.set, vmap)
    except ValueError as exc:
        print(f"stamp-reach: REFUSED: {exc}", file=sys.stderr)
        return 1
    entries = plan(vmap, root)
    if not entries and not chosen:
        print(f"stamp-reach: every rule in {path} already declares reach")
        return 0
    for e in entries:
        if e["propose"] and e["index"] not in chosen:
            chosen[e["index"]] = e["propose"]
    sys.stdout.write(render(entries, chosen))
    if not args.apply:
        print("dry run: nothing written; re-run with --apply")
        return 0
    if not chosen:
        print("stamp-reach: nothing to write")
        return 0
    try:
        new = stamp_text(text, vmap, chosen)
    except ValueError as exc:
        print(f"stamp-reach: REFUSED: {exc}", file=sys.stderr)
        return 1
    write(path, new)
    print(f"stamp-reach: declared reach on {len(chosen)} rule(s) in {path}; review the diff, "
          "then commit it on its own")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
