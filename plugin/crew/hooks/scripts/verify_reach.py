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

So `--apply` writes down what the gate already does. Making a deferred rule
run is a decision, taken only by `--set N=local` (or network/host), naming the
rule by its index. A `"reach": null` is undeclared, exactly as the gate reads it.

THE CACHES FOLLOW THE RULE. `reach` is part of `verify_record.rule_key`, the
hash the gate keys its measured timings (`.crew/.verify-gate.timings.json`)
and per-rule record (`.crew/.verify-gate.record.json`) by. A stamped rule
therefore gets a new key, and without a move its cached price and its standing
obligations would be orphaned: a rule priced from the cache would be re-priced
(or become unknown, so mandatory), and its record entry would hold the marker.
So after the map is written, each stamped rule's entries are moved from its old
key to its new one (temp file + `os.replace`, same format the gate writes). A
cache that is unreadable is left alone and said so; it is advisory.

WHERE IT CLASSIFIES. The gate classifies from its cwd, the project root it
read `.crew/verify.json` from; this runs from `--root` the same way.

HOW IT WRITES. `.crew/verify.json` is hand-formatted and often tracked, so it
is never re-serialised: each `"reach": "..."` is inserted as text right after
its rule's opening brace, the result is parsed back and compared with the
original plus exactly the new keys, and only then written, via a temp file
and `os.replace`. Any mismatch writes nothing and exits 1.

Usage: verify_reach.py [--root DIR] [--apply] [--set N=REACH ...]
Exit: 0 printed or written; 1 refused (unreadable map, a bad --set, or the
text insert did not round-trip) or a cache move could not be written; 2 usage.
"""
import argparse
import copy
import json
import os
import sys

import verify_record

REACHES = ("local", "network", "host")
PROPOSE = {"local": "local", "verb": "network"}


def load(path):
    """(text, map) or raises ValueError naming why the map cannot be used."""
    try:
        with open(path, encoding="utf-8", newline="") as fh:  # keep CRLF: "every other byte"
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


def plan(vmap):
    """One entry per rule with no `reach` (absent or null, as the gate reads
    it): index, classifier status, detail, the proposed value (None when only
    a person can decide), and whether requiresCleanTree keeps it off Stop.
    Classifies from the cwd, as the gate does: call it from the project root."""
    out = []
    for i, rule in enumerate(vmap["rules"]):
        if not isinstance(rule, dict) or rule.get("reach") is not None:
            continue
        run = [c for c in rule.get("run") or [] if isinstance(c, str)]
        status, detail = verify_record.scan_reach(run, os.getcwd())
        out.append({"index": i, "status": status, "detail": detail,
                    "propose": PROPOSE.get(status), "paths": rule.get("paths") or [],
                    "clean_tree": rule.get("requiresCleanTree") is True})
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
        if rules[n].get("reach") is not None:
            raise ValueError(f"--set {item!r}: rule {n} already declares reach "
                             f"{rules[n]['reach']!r}; edit it by hand")
        chosen[n] = reach
    return chosen


def _skip(text, pos, chars=" \t\r\n,"):
    while pos < len(text) and text[pos] in chars:
        pos += 1
    return pos


def _members(text, pos):
    """{key: (value_start, value_end)} for the object whose `{` is at pos; a
    duplicate key keeps its last span, the one json.loads keeps."""
    decoder, spans = json.JSONDecoder(), {}
    pos = _skip(text, pos + 1)
    while text[pos] != "}":
        key, pos = decoder.raw_decode(text, pos)
        start = _skip(text, _skip(text, pos, " \t\r\n") + 1, " \t\r\n")
        _, pos = decoder.raw_decode(text, start)
        spans[key] = (start, pos)
        pos = _skip(text, pos)
    return spans


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
        span = _members(out, at).get("reach")
        if span:  # "reach": null - replace the value, never add a second key
            out = out[:span[0]] + f'"{chosen[index]}"' + out[span[1]:]
        else:
            sep = "," if out[_skip(out, at + 1, " \t\r\n")] != "}" else " "
            out = out[:at + 1] + f' "reach": "{chosen[index]}"{sep}' + out[at + 1:]
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


CACHES = (verify_record.TIMINGS_PATH, verify_record.RECORD_PATH)


def rekey(before, after, stamped):
    """Move each stamped rule's timing and record entries from its old
    rule_key to its new one, in every cache under the cwd. An old key another
    rule still has keeps its entry. Returns (lines to print, ok)."""
    moves = {}
    for i in stamped:
        old, new = verify_record.rule_key(before[i]), verify_record.rule_key(after[i])
        if old != new:
            moves.setdefault(old, set()).add(new)
    live = {verify_record.rule_key(r) for r in after if isinstance(r, dict)}
    lines, ok = [], True
    for path in CACHES:
        data, state = verify_record._load_state(path)  # pylint: disable=protected-access
        if state == "absent":
            continue
        entries = data.get("rules")
        if state != "ok" or not isinstance(entries, dict):
            lines.append(f"stamp-reach: WARNING: {path} is unreadable, so its entries were not "
                         "moved to the stamped rules' new keys; the gate treats it as it is today")
            continue
        moved = 0
        for old, news in moves.items():
            if old not in entries:
                continue
            for new in news:
                entries.setdefault(new, copy.deepcopy(entries[old]))
            if old not in live:
                del entries[old]
            moved += 1
        if not moved:
            continue
        try:
            write(path, json.dumps(data, indent=2, sort_keys=True))
        except OSError as exc:
            ok = False
            lines.append(f"stamp-reach: could not move {moved} entr(ies) in {path} ({exc}); "
                         "the map IS written, so those rules lose their cached price/record")
            continue
        lines.append(f"stamp-reach: moved {moved} entr(ies) in {path} to the new rule keys")
    return lines, ok


def render(entries, chosen):
    lines = ["| Rule | Paths | Gate today | Proposed | Why |", "|---|---|---|---|---|"]
    for e in entries:
        today = ("SKIPPED on Stop (requiresCleanTree)" if e["clean_tree"]
                 else "runs" if e["status"] == "local" else "SKIPPED on Stop")
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
    """Runs from --root, the cwd the gate itself classifies from."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--apply", action="store_true",
                        help="write the proposals and every --set (default: dry run)")
    parser.add_argument("--set", action="append", metavar="N=REACH",
                        help="declare rule N's reach yourself; repeatable")
    args = parser.parse_args(argv)
    back = os.getcwd()
    try:
        os.chdir(args.root)  # contextlib.chdir is 3.11+
    except OSError as exc:
        print(f"stamp-reach: REFUSED: cannot enter {args.root}: {exc}", file=sys.stderr)
        return 1
    try:
        return _main(args)
    finally:
        os.chdir(back)


def _main(args):
    path = os.path.join(".crew", "verify.json")
    try:
        text, vmap = load(path)
        chosen = parse_sets(args.set, vmap)
    except ValueError as exc:
        print(f"stamp-reach: REFUSED: {exc}", file=sys.stderr)
        return 1
    entries = plan(vmap)
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
    lines, ok = rekey(vmap["rules"], json.loads(new)["rules"], chosen)
    for line in lines:
        print(line, file=sys.stderr if "WARNING" in line or not ok else sys.stdout)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
