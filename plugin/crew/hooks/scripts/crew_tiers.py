#!/usr/bin/env python3
"""crew's tier map (R-05): which tier is a target in - dev, qa, prod or unknown?

Two deciding consumers since R-35, both only under the opt-in guard value
`tiered` (profile `balanced`): `crew_dispatch._dispatch_tier` (a workflow
dispatch's tier) and `cloud_guard._tier_of` (a terraform workspace's tier,
logged; an apply still asks). Each imports this module lazily inside that one
function, so the `block`/`ask`/`allow` paths never load it, and each reads it
through `resolve` only. Nothing else that decides imports it: no other guard,
hook, launcher, autopilot or promote path (test_crew_tiers.py T-I1).
`crew_config.explain_config` imports it inside that one function (so the
SessionStart path through `resolve_config` never loads it) to show the `tiers`
row, and its own CLI prints the answer. R-01, R-A1 and R-36 read it later, from
`resolve` only, never from a merged `tiers` value (D10).

The rule (docs/plans/crew-revamp-2026-11-18.md 4.3, 4.14; R-05 spec D1-D11):

- The machine file (`~/.claude/crew/config.json`) is the authority. A repo
  `.crew/config.json` entry can only make a target STRICTER.
- Strictness order: dev < qa < prod < unknown. The effective tier is the
  stricter of the machine value and the repo value. A target the machine does
  not list has machine value `unknown`, so a repo cannot lift it out of
  `unknown`; a repo that says nothing imposes nothing.
- A target is `<kind>:<name>`, kind one of `KINDS` (matched ignoring ASCII
  case and normalised to lower case). The name is looked up EXACTLY: a query that
  differs from a listed name only by case does not match (it is `unlisted`,
  noted `case-mismatch`). Two keys in one `tiers` object that are equal after
  folding the whole target are case twins, and every target in that group is
  `unknown` (`conflicting`). No globs: `*` is a literal character.
- Anything uncertain is `unknown` with a reason. `resolve` always returns a
  value and a reason; `unknown` is never an error.

One reader, `_read_layer`, for both files. It parses with its own
`object_pairs_hook` that never raises: it keeps the FIRST value of a repeated
key and records, per object, every group of keys that fold to the same text.
Only the twins on the top-level object (for `tiers`), on the `tiers` object and
on each entry object are consulted; a duplicate anywhere else in the file
changes no tier. It never collapses a malformed file into `{}`, which is why it
is not `crew_config.read_global_config` or `crew_state.load_config`, and it does
not refuse the whole file on one twin elsewhere, which is why it is not
`crew_gitallow.strict_pairs`.

CLI (exit 0 always; 2 on bad usage):
    crew_tiers.py explain <target> [--json] [--root DIR] [--global-path FILE]
    crew_tiers.py list [--json] [--root DIR] [--global-path FILE]

Standard library only.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import stat
import sys

import _promote_match
import crew_common

TIERS = ("dev", "qa", "prod", "unknown")
RANK = {tier: index for index, tier in enumerate(TIERS)}
# A tier an entry may SET. `unknown` is a result, never a setting (D4).
SETTABLE = ("dev", "qa", "prod")
# The one field of an entry crew reads (D4). A name, so no line here reads like the
# old top-level `tier` key L-0725 dropped (tests/test_crew_keys.py's reader scan).
FIELD = "tier"
KINDS = ("workspace", "workflow", "database", "account", "host")
# Fields of an entry the plan names (4.14) and nothing reads until R-A1.
LATER_FIELDS = ("application", "accounts")

REASONS = ("machine-unreadable", "repo-unreadable", "conflicting", "invalid",
           "repo-invalid-entry", "unlisted", "narrowed-by-repo", "listed")

_TIERS_FOLD = _promote_match.fold("tiers")
_TIER_FOLD = _promote_match.fold("tier")


def parse_target(text):
    """`(kind, name)` for `<kind>:<name>` with a known kind, else None. The
    kind is matched ignoring case and returned lower case; the name is
    returned exactly as written and must not be empty."""
    if not isinstance(text, str) or ":" not in text:
        return None
    kind, name = text.split(":", 1)
    # ASCII only: `str.lower` maps the Kelvin sign (U+212A) onto `k`, which
    # `_promote_match.fold` (the twin rule) keeps apart, so `wor\u212aflow:x`
    # matched `workflow:x` without being its twin and the answer followed the
    # order of the keys (review round 6). A kind that is not ASCII is no kind.
    if not kind.isascii():
        return None
    kind = kind.lower()
    if kind not in KINDS or not name:
        return None
    return kind, name


def _norm(text):
    """The target as shown: the kind lower-cased, the name as written; an
    unparseable text unchanged."""
    parsed = parse_target(text)
    return text if parsed is None else f"{parsed[0]}:{parsed[1]}"


class _Obj(dict):
    """A JSON object as `_pairs` builds it: the first value of each key, plus
    `twins`, every group of keys (as written) that fold to the same text, and
    `twinValues`, the folded text of each such group -> EVERY value its keys
    held, in order (the dict itself keeps only the first)."""

    __slots__ = ("twins", "twinValues")

    def __init__(self):
        super().__init__()
        self.twins = []
        self.twinValues = {}


def _pairs(pairs):
    """The D11 `object_pairs_hook`. Never raises."""
    obj = _Obj()
    groups, values = {}, {}
    for key, value in pairs:
        folded = _promote_match.fold(key)
        groups.setdefault(folded, []).append(key)
        values.setdefault(folded, []).append(value)
        if key not in obj:
            obj[key] = value
    obj.twins = [keys for keys in groups.values() if len(keys) > 1]
    obj.twinValues = {folded: values[folded] for folded, keys in groups.items()
                      if len(keys) > 1}
    return obj


def _twins(obj):
    return getattr(obj, "twins", None) or []


def _no_constant(name):
    """`parse_constant` for `_read_layer`: `NaN`, `Infinity` and `-Infinity`
    are not JSON (RFC 8259), so a file holding one is unreadable (D5), never
    read as if the number were there."""
    raise ValueError(f"{name} is not JSON")


class _Number(str):
    """A JSON number Python cannot hold, kept as the text the file wrote."""

    __slots__ = ()


def _float(text):
    """`parse_float` for `_read_layer`. `1e999` is valid JSON that overflows a
    float; as infinity, `json.dumps` would write it into a `--json` report as
    the non-JSON `Infinity` (review round 3). It is kept as its text instead,
    so the file stays readable and a number in a field nothing reads changes
    no tier (D4; review round 6: refusing the whole layer over it was wrong)."""
    value = float(text)
    return _Number(text) if math.isinf(value) or math.isnan(value) else value


def _int(text):
    """`parse_int` for `_read_layer`: an integer too long for `int` (Python
    refuses more than 4300 digits with ValueError) is kept as its text, the
    same way and for the same reason as `_float`."""
    try:
        return int(text)
    except ValueError:
        return _Number(text)


def _kind(value):
    """What a value is, for a message: `number` for a `_Number`, never `str`."""
    if value is None:
        return "null"
    return "number" if isinstance(value, _Number) else type(value).__name__


def _dangling(path):
    """True when `path`, or the directory holding it, is a symlink whose
    target does not exist. Never raises."""
    try:
        if os.path.islink(path):
            return True  # called only after `open` found nothing behind it
        parent = os.path.dirname(path)
        return bool(parent) and os.path.islink(parent) and not os.path.exists(parent)
    except (OSError, ValueError, TypeError):
        return False


def _read_layer(path):
    """`("absent", None)`, `("unreadable", detail)` or `("ok", parsed)`.
    Never raises: a path `open` refuses (an embedded NUL, a wrong type) is
    unreadable, not absent, so an unknown never reads as "no file"."""
    if path is None:
        return "absent", None
    # O_NONBLOCK (POSIX): opening a FIFO for reading blocks until a writer
    # appears, so a FIFO at the config path would hang every caller instead of
    # being unreadable (review round 4). The type is then checked on the open
    # descriptor, so nothing but a regular file is ever read.
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except (FileNotFoundError, NotADirectoryError) as exc:
        if _dangling(path):
            # A link that leads nowhere is a file crew could not read, not "no
            # file": a narrowing behind it must not be dropped (review round 5).
            return "unreadable", f"{path!r}: a symlink that leads nowhere ({type(exc).__name__})"
        return "absent", None
    except (OSError, ValueError, TypeError) as exc:
        return "unreadable", f"{path!r}: {type(exc).__name__}: {exc}"
    try:
        with os.fdopen(fd, "rb") as fh:
            if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
                return "unreadable", f"{path!r}: not a regular file"
            raw = fh.read()
    except (OSError, ValueError) as exc:
        return "unreadable", f"{path!r}: {type(exc).__name__}: {exc}"
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return "unreadable", f"{path}: not UTF-8 ({exc})"
    try:
        parsed = json.loads(text, object_pairs_hook=_pairs, parse_constant=_no_constant,
                            parse_float=_float, parse_int=_int)
    except (ValueError, RecursionError) as exc:
        return "unreadable", f"{path}: not JSON ({type(exc).__name__}: {exc})"
    if not isinstance(parsed, dict):
        return "unreadable", f"{path}: not a JSON object"
    return "ok", parsed


def _layer(label, status, parsed):
    """One layer, analysed: `{"label", "status", "detail", "map", "topTwins",
    "twinTargets"}`. `status` is `absent`, `unreadable` or `ok`; `map` is the
    `tiers` object (an `_Obj`, `{}` when absent); `topTwins` names keys folding
    to `tiers`, and `twinTargets` every target key any of THEIR maps lists, so
    a report still names a target that only the second map holds (every one
    of them is `conflicting`, and a dropped target would read as "no row")."""
    out = {"label": label, "status": status, "detail": None, "map": _Obj(),
           "topTwins": None, "twinTargets": []}
    if status == "unreadable":
        out["detail"] = parsed
        return out
    if status != "ok":
        return out
    for group in _twins(parsed):
        if _promote_match.fold(group[0]) == _TIERS_FOLD:
            out["topTwins"] = group
            for value in parsed.twinValues.get(_TIERS_FOLD, []):
                if isinstance(value, dict):
                    out["twinTargets"].extend(value)
    if "tiers" not in parsed:
        return out
    tiers = parsed["tiers"]
    if not isinstance(tiers, dict):
        # `null` included (D5): a present key that is not a map is unreadable,
        # never "no map", so a `"tiers": null` cannot hide the layer's entries.
        out["status"] = "unreadable"
        out["detail"] = f"its `tiers` is {_kind(tiers)}, not an object"
        return out
    out["map"] = tiers
    return out


def _default_global_path():
    # Lazily, so this module has no module-level import of crew_config, and so
    # a test that points crew_config.GLOBAL_CONFIG_PATH elsewhere is obeyed.
    import crew_config  # pylint: disable=import-outside-toplevel
    return crew_config.GLOBAL_CONFIG_PATH


def read_layers(root, global_path=None):
    """`(machine, repo)`, each analysed by `_layer`. `root` None reads no repo
    file; `global_path` None is `crew_config.GLOBAL_CONFIG_PATH`."""
    machine_path = _default_global_path() if global_path is None else global_path
    machine = _layer("machine", *_read_layer(machine_path))
    repo = _layer("repo", *_repo_read(root))
    return machine, repo


def _repo_read(root):
    """`_read_layer` for the repo file `crew_common.repo_config_dir` names.
    When it cannot tell which `.crew/` is in force (a linked worktree git
    cannot resolve, SOURCE_UNKNOWN) or fails on the path, the repo layer is
    unreadable, not absent: a narrowing in the main checkout's file must not
    read as "the repo says nothing"."""
    if root is None:
        return "absent", None
    try:
        crew_dir, source, detail = crew_common.repo_config_dir(root)
    except (OSError, ValueError, TypeError) as exc:
        return "unreadable", f"{root!r}: could not resolve .crew/ ({type(exc).__name__}: {exc})"
    if source == crew_common.SOURCE_UNKNOWN:
        return "unreadable", f"could not tell which .crew/ is in force ({detail})"
    return _read_layer(os.path.join(crew_dir, "config.json"))


def _lookup(layer, target):
    """`(key as written, entry)` for `target` in `layer`'s map, else None.
    Exact on the name; the kind of a listed key folds. An unparseable target
    matches only a key written exactly as it is, and a target that is not
    text (`resolve(None)`) matches nothing."""
    if not isinstance(target, str):
        return None
    table = layer["map"]
    parsed = parse_target(target)
    if parsed is None:
        return (target, table[target]) if target in table else None
    for key, entry in table.items():
        if parse_target(key) == parsed:
            return key, entry
    return None


def _case_mismatch(layer, target):
    """A listed key that differs from `target` only by case, else None."""
    folded = _promote_match.fold(target)
    for key in layer["map"]:
        if _promote_match.fold(key) == folded and _norm(key) != _norm(target):
            return key
    return None


def _conflict(layer, target, found):
    """Why `target` is `conflicting` in `layer`, or None."""
    if layer["topTwins"]:
        return (f"{layer['label']}: the file holds more than one key folding to "
                f"`tiers`: {', '.join(layer['topTwins'])}")
    if not isinstance(target, str):
        return None
    folded = _promote_match.fold(target)
    for group in _twins(layer["map"]):
        if _promote_match.fold(group[0]) == folded:
            return f"{layer['label']}: case twins in `tiers`: {', '.join(group)}"
    if found is not None:
        for group in _twins(found[1]):
            if _promote_match.fold(group[0]) == _TIER_FOLD:
                return (f"{layer['label']}: the entry {found[0]} holds twins of "
                        f"`tier`: {', '.join(group)}")
    return None


def _entry_problem(key, entry):
    """Why a listed entry is invalid, or None (D4)."""
    if parse_target(key) is None:
        return (f"{key!r} is not `<kind>:<name>` with a kind of "
                + ", ".join(KINDS))
    if not isinstance(entry, dict):
        return f"{key}: the entry is {_kind(entry)}, not an object"
    if "tier" not in entry:
        return f"{key}: the entry has no `tier`"
    tier = entry[FIELD]
    if isinstance(tier, _Number):
        return f"{key}: tier is the number {tier}, not one of " + ", ".join(SETTABLE)
    if not isinstance(tier, str) or tier not in SETTABLE:
        return (f"{key}: tier {tier!r} is not one of " + ", ".join(SETTABLE)
                + (" (unknown is a result, not a setting)" if tier == "unknown" else ""))
    return None


def _field_notes(label, entry):
    out = []
    for field in entry:
        if field == "tier":
            continue
        if field in LATER_FIELDS:
            out.append(f"{label}: {field}: not read until R-A1")
        else:
            out.append(f"{label}: unknown field {field!r} (ignored)")
    return out


def _machine_value(found):
    """The machine's tier for a target: its entry's tier, or `unknown` when
    the machine lists no entry (D2). Called only on a valid entry or None."""
    if found is None:
        return "unknown"
    return found[1][FIELD]


def _combine(machine_tier, repo_tier):
    """The stricter of the two (D2). A repo that says nothing imposes nothing."""
    if repo_tier is None:
        return machine_tier
    return repo_tier if RANK[repo_tier] > RANK[machine_tier] else machine_tier


def resolve_layers(machine, repo, target):
    """`{"target", "tier", "reason", "machine", "repo", "notes"}` for one
    target from two analysed layers. Pure. `machine` and `repo` are the tier
    each layer's entry SETS (None when it lists none or its entry is invalid).
    A `target` that is not text (None, a number, a list) is `invalid` like any
    other unparseable query, never an exception (D5; review round 4); it is
    shown as its `repr`."""
    notes = []
    shown = _norm(target) if isinstance(target, str) else repr(target)
    out = {"target": shown, "tier": "unknown", "reason": None,
           "machine": None, "repo": None, "notes": notes}
    m_found, r_found = _lookup(machine, target), _lookup(repo, target)
    m_problem = None if m_found is None else _entry_problem(*m_found)
    r_problem = None if r_found is None else _entry_problem(*r_found)
    if m_found is not None and m_problem is None:
        out["machine"] = m_found[1][FIELD]
        notes.extend(_field_notes("machine", m_found[1]))
    if r_found is not None and r_problem is None:
        out["repo"] = r_found[1][FIELD]
        notes.extend(_field_notes("repo", r_found[1]))

    def done(reason, note=None):
        out["reason"] = reason
        if note:
            notes.insert(0, note)
        return out

    if machine["status"] == "unreadable":
        return done("machine-unreadable", f"machine: {machine['detail']}")
    if repo["status"] == "unreadable":
        return done("repo-unreadable", f"repo: {repo['detail']}")
    conflict = _conflict(machine, target, m_found) or _conflict(repo, target, r_found)
    if conflict:
        return done("conflicting", conflict)
    # The machine's entry first (it is the authority), then the repo's, then
    # the query itself: a repo-only `server:a` is the repo's bad entry (D5),
    # not an invalid query.
    if m_problem:
        return done("invalid", f"machine: {m_problem}")
    if r_problem:
        return done("repo-invalid-entry", f"repo: {r_problem}")
    if parse_target(target) is None:
        return done("invalid",
                    f"{target!r} is not `<kind>:<name>` with a kind of " + ", ".join(KINDS))
    tier = _combine(_machine_value(m_found), out["repo"])
    out[FIELD] = tier
    if m_found is None:
        listed = _case_mismatch(machine, target)
        return done("unlisted", f"case-mismatch: {listed}" if listed else None)
    if RANK[tier] > RANK[out["machine"]]:
        return done("narrowed-by-repo")
    return done("listed")


def resolve(target, root=None, global_path=None):
    """The tier of `target` for the repo at `root` (no repo file when None)."""
    machine, repo = read_layers(root, global_path)
    return resolve_layers(machine, repo, target)


def _targets(*layers):
    return sorted({_norm(key) for layer in layers
                   for key in itertools.chain(layer["map"], layer["twinTargets"])})


def resolve_all(root, global_path=None):
    """One result per target named in either layer, sorted by target."""
    machine, repo = read_layers(root, global_path)
    return [resolve_layers(machine, repo, t) for t in _targets(machine, repo)]


def _repo_ignored(result):
    """True when the repo's entry asked for less than the machine (or named a
    target the machine does not list), so it decides nothing."""
    if result["reason"] not in ("listed", "unlisted") or result["repo"] is None:
        return False
    return result["machine"] is None or RANK[result["repo"]] < RANK[result["machine"]]


def explain_row(root, global_path=None):
    """The `tiers` row for `crew_config.explain_config` (D1): the value per
    target is the EFFECTIVE tier, never a tier the repo widened."""
    machine, repo = read_layers(root, global_path)
    results = [resolve_layers(machine, repo, t) for t in _targets(machine, repo)]
    ignored = {}
    for result in results:
        if _repo_ignored(result):
            found = _lookup(repo, result["target"])
            ignored[result["target"]] = None if found is None else found[1]
    if any(r["reason"] == "narrowed-by-repo" for r in results):
        source = "repo+global"
    elif machine["map"] or machine["status"] == "unreadable" or machine["topTwins"]:
        source = "global"
    else:
        source = "default"
    row = {"path": "tiers", "value": {r["target"]: r[FIELD] for r in results},
           "source": source, "tiers": results, "lines": [_line(r) for r in results],
           "heldDownBy": "global" if ignored else None,
           "problems": layer_problems(machine, repo)}
    if ignored:
        row["repoIgnored"] = ignored
        row["ignoredLines"] = [
            show(f"{target}: repo asks {json.dumps(entry)}; a repo may only narrow "
                 "the machine's tier, so it is ignored")
            for target, entry in ignored.items()]
    return row


def layer_problems(machine, repo):
    """One display line per unreadable layer, and per layer holding more than
    one key folding to `tiers`, so a report still says the machine (or repo)
    file could not be used even when it lists no target of its own."""
    out = []
    for layer in (machine, repo):
        if layer["status"] == "unreadable":
            out.append(show(f"{layer['label']}-unreadable: {layer['detail']}"))
        elif layer["topTwins"]:
            out.append(show(f"{layer['label']}-conflicting: more than one key folding to "
                            f"`tiers`: {', '.join(layer['topTwins'])}; every target is unknown"))
    return out


def show(text):
    """`text` safe for one physical line on any stream
    (`crew_common.one_line`): a repo-written name cannot forge another result
    row, and a report never dies of UnicodeEncodeError on a stream that is
    not UTF-8 (review round 4). `--json` output is `json.dumps`, ASCII already."""
    return crew_common.one_line(text)


def _line(result):
    return show(f"{result['target']}  {result[FIELD]}  ({result['reason']})")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="crew_tiers.py",
        description="crew's tier map, report-only: which tier a target is in.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("explain", "list"):
        cmd = sub.add_parser(name)
        if name == "explain":
            cmd.add_argument("target", help="<kind>:<name>, kind one of " + ", ".join(KINDS))
        cmd.add_argument("--json", action="store_true")
        cmd.add_argument("--root", default=".")
        cmd.add_argument("--global-path", default=None)
    args = parser.parse_args(argv)
    if args.command == "explain":
        result = resolve(args.target, args.root, args.global_path)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(_line(result))
            for note in result["notes"]:
                print(f"  - {show(note)}")
        return 0
    machine, repo = read_layers(args.root, args.global_path)
    results = [resolve_layers(machine, repo, t) for t in _targets(machine, repo)]
    problems = layer_problems(machine, repo)
    if args.json:
        # stdout keeps its list shape; an unreadable or conflicting layer is
        # named on stderr, so `[]` from a broken file never reads as an empty
        # map (review round 3).
        for problem in problems:
            print(f"! {problem}", file=sys.stderr)
        print(json.dumps(results, indent=2))
        return 0
    for problem in problems:
        print(f"! {problem}")
    if not results:
        print("no targets listed: every target is unknown (report-only until R-01)")
    for result in results:
        print(_line(result))
        for note in result["notes"]:
            print(f"  - {show(note)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
