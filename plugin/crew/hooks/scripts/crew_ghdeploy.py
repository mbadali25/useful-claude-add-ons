"""GitHub Actions deploys for `/crew:promote`, as data in `.crew/verify.json`.

    python3 crew_ghdeploy.py check   --root DIR --env NAME
    python3 crew_ghdeploy.py prepare --root DIR --env NAME [--index N]
    python3 crew_ghdeploy.py identify --root DIR --env NAME [--index N]
    python3 crew_ghdeploy.py watch    --root DIR --env NAME [--index N] [--slice-seconds S]

T-0045 slice 1. An environment in `.crew/verify.json` may carry a `github`
entry -- one object or a list of them -- that describes a
`gh workflow run` dispatch:

    "staging": {
      "deploy": ["gh workflow run deploy.yml --ref main -f target=staging"],
      "github": {"workflow": "deploy.yml", "ref": "main",
                 "inputs": {"target": "staging"},
                 "shaInput": "sha", "correlationInput": "crew_id",
                 "deployJob": "deploy*", "watchMinutes": 60,
                 "identifySeconds": 120},
      ...
    }

`check` validates every entry, checks that the environment's `deploy` is
exactly the set of the entries' canonical prefixes -- so promote-gate's
existing substring match fires on the real dispatch -- and prints the one
literal dispatch per entry for HEAD. It writes nothing and runs no `gh`: the
only subprocess is `git rev-parse HEAD`. It decides no authority either; that
is the guard on the Bash call (T-0009). The later slices (`prepare`,
`identify`, `watch`, `record`: L-0644 to L-0647) build on this module.

VALUES ARE CLOSED, NOT ESCAPED. Every value that reaches the command matches
`[A-Za-z0-9._/@:+-]+`; anything else is refused by name and never quoted.
A workflow is a `.yml`/`.yaml` filename (no display name, no numeric id) and
there is no key for `-R/--repo`. A ref is checked as a branch NAME only: it
must pass `git check-ref-format --branch` (re-implemented here, no git call),
must not start with `-` or `@` (PowerShell splats `@name`), and must not be
`HEAD` or a `refs/` path other than `refs/heads/` (both case-insensitive). A
tag given by its bare name is NOT detected: telling it from a branch needs
the remote, and `check` asks nothing.

THE GATES ARE SIMULATED (L-1503): REFUSE WHEN EITHER GATE REFUSES, MATCH
WITH THE UNION. Both promote-gate flavours share one rule, and `check`
applies it (`load_map`, `gate_problem`, `gate_matches`):
  - every key the gates read (`environments`, `deploy`, `requireHuman`, ...)
    is read ignoring case; a map with two keys equal or equal ignoring case,
    an environment name that is empty or holds a control character or `,`,
    an environment that is not an object, a `deploy` that is null or not a
    command or list of commands, or a `requireHuman` that is a list or an
    object is REFUSED by the gates, so `check` refuses it too
    (`gate-refuses-map`); `"deploy": []` and `[""]` declare nothing;
  - the command loses every CR and its trailing newlines, and a blank one
    deploys nothing; a declared command matches when either one contains the
    other, literally, ignoring case (`*`, `?`, `[` are text: `[!-[]` is four
    characters, never a wildcard set);
  - EVERY matching environment applies, in file order, joined `staging,prod`:
    the union of their `requires`, `rollback` and `requireHuman`.
Where the two flavours still differ, `check` takes the STRICTER answer, by
construction rather than by luck:
  - it refuses a map EITHER gate refuses. promote-gate.ps1 alone refuses an
    empty key at any depth (ConvertFrom-Json), keys that are twins only
    under .NET's OrdinalIgnoreCase (`_DOTNET_ONLY_FOLDS`: 27 Greek
    iota-subscript pairs), and a `deploy` string ConvertFrom-Json turns into
    a DateTime (`_is_dotnet_date`). promote-gate.sh alone refuses keys that
    are twins only under Python's fold (dotless i, long s), and JSON nested
    past its recursion limit (about 1,000 levels, by interpreter): `check`
    refuses anything nested past `_MAX_DEPTH` (200), stricter than both;
  - an environment matches when it matches under EITHER gate's case fold,
    so `gated-as: <names>` (printed under each dispatch) is the union of
    what the two gates apply. They agree on every ASCII command, and a
    dispatch is ASCII by the value grammar; they differ only for another
    environment's deploy string holding one of those 29 characters.
A dispatch matching several environments is therefore not a refusal.
`<env>` is always in `gated-as`, because `deploy` lists the entry's prefix
and the dispatch starts with it.
`check` reads only the working `.crew/verify.json`, never the committed one:
with the map uncommitted, both gates block every deploy anyway (and then
match the committed map too).

Exit codes, with the last stdout line always `result=...`:
  0  `result=ok entries=N sha=<sha>` after a `dispatch: <command>` and a
     `gated-as: '<names>'` line per entry, or `result=ok github=none` for an environment without a `github` key.
  2  `result=refused reason=<code>`: an entry problem, `deploy-prefix-mismatch`
     or `gate-refuses-map` (a gate refuses the map, so every command blocks).
  3  `result=could-not-tell reason=<code>`: the map is absent or unreadable,
     the environment is not in it, or HEAD cannot be read. Never read as
     "no github entry".
"""
import argparse
import calendar
import datetime
import fnmatch
import json
import os
import re
import secrets
import subprocess
import sys
import time
import unicodedata

import crew_common

VALUE = re.compile(r"[A-Za-z0-9._/@:+-]+")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
WORKFLOW = re.compile(r"[A-Za-z0-9._][A-Za-z0-9._-]*\.ya?ml")
KEYS = ("workflow", "ref", "inputs", "shaInput", "correlationInput",
        "deployJob", "watchMinutes", "identifySeconds")
RANGES = {"watchMinutes": (1, 360, 60, "watch-minutes-range"),
          "identifySeconds": (10, 900, 120, "identify-seconds-range")}


class Refused(Exception):
    """An entry or map problem: exit 2, refused by name."""

    def __init__(self, reason, detail):
        super().__init__(detail)
        self.reason = reason


class CouldNotTell(Exception):
    """crew cannot read what it needs to answer: exit 3."""

    def __init__(self, reason, detail):
        super().__init__(detail)
        self.reason = reason


def _fits(value):
    return isinstance(value, str) and VALUE.fullmatch(value) is not None


def _ref_problem(ref):
    if not isinstance(ref, str) or not ref:
        return "ref-chars"
    if ref.startswith("-"):
        return "ref-dash"
    if ref.startswith("@"):
        return "ref-at"
    if ".." in ref:
        return "ref-dotdot"
    low = ref.lower()
    if low == "head" or (low.startswith("refs/") and not ref.startswith("refs/heads/")):
        return "ref-not-branch"
    if not _fits(ref):
        return "ref-chars"
    # What `git check-ref-format --branch` still rejects inside the value grammar.
    # An empty component is a leading or trailing `/` or a `//`.
    parts = ref.split("/")
    if ":" in ref or "" in parts or ref.endswith(".") \
            or any(part.startswith(".") or part.endswith(".lock") for part in parts):
        return "ref-format"
    return None


def _one_line(text):
    """No C0/C1 control character, DEL, or Unicode line/paragraph separator."""
    return not any(ord(c) < 32 or 127 <= ord(c) <= 159 or c in "\u2028\u2029"
                   for c in text)


def _inputs_problem(entry):
    inputs = entry.get("inputs", {})
    if not isinstance(inputs, dict):
        return "inputs-not-object", "`inputs` is not an object"
    for name, value in inputs.items():
        if NAME.fullmatch(name) is None:
            return "input-name-chars", f"input name {name!r} is not a plain name"
        if not isinstance(value, str):
            return "input-not-string", f"input {name!r} is not a string"
        if not _fits(value):
            return "value-chars", (f"input {name!r} has a value outside "
                                   "[A-Za-z0-9._/@:+-]; it is refused, never quoted")
    # Input names are compared case-insensitively throughout.
    names = {name.lower() for name in inputs}
    if len(names) != len(inputs):
        return "input-name-duplicate", "two `inputs` names differ only in case"
    for key in ("shaInput", "correlationInput"):
        if key in entry and (not isinstance(entry[key], str)
                             or NAME.fullmatch(entry[key]) is None):
            return "input-name-chars", f"`{key}` is not a plain input name"
    sha = entry.get("shaInput", "").lower()
    corr = entry.get("correlationInput", "").lower()
    if sha and sha in names:
        return "sha-input-in-inputs", f"`shaInput` {entry['shaInput']!r} is also in `inputs`"
    if corr and corr == sha:
        return "sha-equals-correlation", "`shaInput` and `correlationInput` are the same input"
    if corr and corr in names:
        return "correlation-in-inputs", (f"`correlationInput` {entry['correlationInput']!r} "
                                         "is also in `inputs`")
    return None


def entry_problem(entry, env):
    """(reason, detail) for the first thing wrong with one entry (an object,
    as `entries` returns it), else None."""
    unknown = sorted(set(entry) - set(KEYS))
    if unknown:
        return "unknown-key", f"unknown key {unknown[0]!r}"
    if "workflow" not in entry:
        return "workflow-missing", "no `workflow`"
    workflow = entry["workflow"]
    if not isinstance(workflow, str) or WORKFLOW.fullmatch(workflow) is None:
        return "workflow-not-filename", ("`workflow` must be a .yml/.yaml filename "
                                         "from [A-Za-z0-9._-], not a display name or id")
    if "ref" not in entry:
        return "ref-missing", "no `ref`"
    reason = _ref_problem(entry["ref"])
    if reason:
        return reason, ("`ref` must be a branch name: valid for `git check-ref-format "
                        "--branch`, in [A-Za-z0-9._/@:+-], not starting with - or @, not "
                        "HEAD, and no refs/ path other than refs/heads/")
    problem = _inputs_problem(entry)
    if problem:
        return problem
    if "deployJob" in entry:
        job = entry["deployJob"]
        if not isinstance(job, str) or not job or not _one_line(job):
            return "deploy-job-bad", "`deployJob` must be a non-empty glob on one line"
    for key, (low, high, _default, code) in RANGES.items():
        if key in entry:
            value = entry[key]
            if isinstance(value, bool) or not isinstance(value, int) \
                    or not low <= value <= high:
                return code, f"`{key}` must be an integer from {low} to {high}"
    if entry.get("correlationInput") is not None and not _fits(env):
        return "env-name-chars", ("the environment name is inside the correlation id, "
                                  "so it must fit [A-Za-z0-9._/@:+-]")
    return None


def entries(cfg):
    """The environment's `github` entries as a list, or None when it has none."""
    if "github" not in cfg:
        return None
    github = cfg["github"]
    if isinstance(github, dict):
        return [github]
    if isinstance(github, list) and github and all(isinstance(e, dict) for e in github):
        return github
    raise Refused("github-shape", "`github` is neither an object nor a "
                                  "non-empty list of objects")


def prefix(entry):
    """The canonical prefix: the string the environment's `deploy` must list."""
    parts = ["gh workflow run", entry["workflow"], "--ref", entry["ref"]]
    for name, value in entry.get("inputs", {}).items():
        parts += ["-f", f"{name}={value}"]
    return " ".join(parts)


def dispatch(entry, env, sha, corr=None):
    """The one literal dispatch for `sha`: prefix, sha input, correlation id
    (`corr`, or a fresh one when the entry names a `correlationInput`)."""
    line = prefix(entry)
    if entry.get("shaInput"):
        line += f" -f {entry['shaInput']}={sha}"
    if entry.get("correlationInput"):
        corr = corr or f"crew-{env}-{sha[:7]}-{secrets.token_hex(4)}"
        line += f" -f {entry['correlationInput']}={corr}"
    return line


class _MapRefused(Exception):
    """A map at least one promote gate refuses to read: every command blocks."""


# Case pairs .NET's OrdinalIgnoreCase folds and Python's per-character simple
# upper case does not (its full upper case of the lower one is two
# characters): measured with [string]::Equals on pwsh 7.4.6 (.NET 8), every
# BMP code point. The reverse direction - U+0131 dotless i and U+017F long s,
# folded by Python only - is what `_fold` already does.
_DOTNET_ONLY_FOLDS = {chr(low): chr(low + 8) for low in
                      list(range(0x1F80, 0x1F88)) + list(range(0x1F90, 0x1F98))
                      + list(range(0x1FA0, 0x1FA8))}
_DOTNET_ONLY_FOLDS.update({"\u1fb3": "\u1fbc", "\u1fc3": "\u1fcc", "\u1ff3": "\u1ffc"})


def _fold(text):
    """promote-gate.sh's case fold: per-character simple upper case, a
    character whose upper case is longer than one character kept as is."""
    return "".join(c.upper() if len(c.upper()) == 1 else c for c in text)


def _dotnet_fold(text):
    """promote-gate.ps1's: OrdinalIgnoreCase, which keeps U+0131 and U+017F
    and folds the iota-subscript pairs Python keeps."""
    return "".join(c if c in "\u0131\u017f" else _DOTNET_ONLY_FOLDS.get(c) or _fold(c)
                   for c in text)


def _blank(text):
    """.NET's String.IsNullOrWhiteSpace, as promote-gate.sh spells it."""
    return all(c.isspace() and c not in "\x1c\x1d\x1e\x1f" for c in text)


def _no_twins(pairs):
    """json object hook, at every depth: an empty key (ConvertFrom-Json
    refuses it), or two keys equal ignoring case under EITHER gate's fold."""
    seen = set()
    for key, _value in pairs:
        if key == "":
            raise _MapRefused("an empty key, which ConvertFrom-Json refuses")
        folds = {("py", _fold(key)), ("net", _dotnet_fold(key))}
        if folds & seen:
            raise _MapRefused(f"two keys equal or differing only by case ({key!r})")
        seen |= folds
    return dict(pairs)


def _iso_date(s):
    """Newtonsoft's DateTimeParser.Parse (ISO 8601), which ConvertFrom-Json
    runs on every string of 19-40 characters starting with a digit and
    holding `T` at index 10."""
    end = len(s)

    def num(start, width):
        if start + width - 1 < end and all("0" <= c <= "9" for c in s[start:start + width]):
            return int(s[start:start + width])
        return None

    head = re.match(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})", s)
    if head is None:
        return False
    year, month, day, hour, minute, second = (int(g) for g in head.groups())
    if not (year and 1 <= month <= 12 and 1 <= day <= calendar.monthrange(year, month)[1]):
        return False
    if hour > 24 or max(minute, second) >= 60 or (hour == 24 and minute + second):
        return False
    pos = 19
    if pos < end and s[pos] == ".":
        digits = ""
        pos += 1
        while pos < end and len(digits) < 7 and "0" <= s[pos] <= "9":
            digits += s[pos]
            pos += 1
        if not digits or (hour == 24 and int(digits)):
            return False
    if pos < end:
        if s[pos] in "zZ":
            pos += 1
        else:
            if pos + 2 < end and num(pos + 1, 2) is not None and s[pos] in "+-":
                pos += 3
            if pos < end:
                if s[pos] == ":":
                    pos += 1
                    if pos + 1 < end and num(pos, 2) is not None:
                        pos += 2
                elif pos + 1 < end and num(pos, 2) is not None:
                    pos += 2
    return pos == end


def _is_dotnet_date(s):
    """A string ConvertFrom-Json (pwsh 7, Newtonsoft DateParseHandling
    .DateTime) reads as a DateTime, so promote-gate.ps1 finds no command.
    `/Date(<ticks>[+-<offset>])/`: the ticks must be an Int64; Newtonsoft's
    offset parse depends on the string's position in its read buffer, so any
    offset is treated as a date - stricter than the gate, never laxer."""
    if s.startswith("/"):
        if not (len(s) >= 9 and s.startswith("/Date(") and s.endswith(")/")):
            return False
        cut = s.find("+", 7, len(s) - 1)
        cut = s.find("-", 7, len(s) - 1) if cut == -1 else cut
        ticks = s[6:cut if cut != -1 else len(s) - 2]
        return (re.fullmatch(r"-?[0-9]+", ticks) is not None
                and -2 ** 63 <= int(ticks) < 2 ** 63)
    return (19 <= len(s) <= 40 and unicodedata.category(s[0]) == "Nd"
            and s[10] == "T" and _iso_date(s))


def _get_ci(obj, name, default):
    """`obj[name]` with the key matched ignoring case (twins never get here)."""
    keys = [key for key in obj if _fold(key) == _fold(name)]
    return obj[keys[0]] if keys else default


def _deploys(cfg):
    """An environment's `deploy` as a list of strings, the key read ignoring
    case; None when it is neither a command nor a list of commands - to
    either gate, so a string ConvertFrom-Json reads as a DateTime too."""
    declared = _get_ci(cfg, "deploy", [])
    if isinstance(declared, str):
        declared = [declared]
    if not isinstance(declared, list) or not all(
            isinstance(d, str) and not _is_dotnet_date(d) for d in declared):
        return None
    return declared


def gate_problem(envs):
    """Why at least one promote gate refuses this map of environments, or None."""
    # An empty name never gets here: `_no_twins` refuses an empty key.
    for name in envs:
        if "," in name or any(unicodedata.category(c) == "Cc" for c in name):
            return f"environment name {name!r} holds a control character or a comma"
    for name, cfg in envs.items():
        if not isinstance(cfg, dict):
            return f"environment {name!r} is not an object"
        if isinstance(_get_ci(cfg, "requireHuman", None), (list, dict)):
            return f"environment {name!r} has a `requireHuman` that is a list or an object"
        if _deploys(cfg) is None:
            return (f"environment {name!r} has a `deploy` that is not a command "
                    "or a list of commands (a date-time string is not one to "
                    "promote-gate.ps1)")
    return None


def _matches(command, dep):
    return any(fold(dep) in fold(command) or fold(command) in fold(dep)
               for fold in (_fold, _dotnet_fold))


def gate_matches(command, envs):
    """Every environment, in file order, either promote gate applies to
    `command` on this (gate_problem-free) map: [] when none."""
    command = command.replace("\r", "").rstrip("\n")
    if _blank(command):
        return []
    return [name for name, cfg in envs.items()
            if any(dep and _matches(command, dep) for dep in _deploys(cfg))]


# Deeper JSON is refused before it is parsed. promote-gate.sh's json.loads
# raises RecursionError somewhere near 1,000 levels, but where depends on the
# interpreter (3.11 refuses 1,000; 3.12 and 3.13 read it), and
# promote-gate.ps1's ConvertFrom-Json stops at 1,024. A fixed bound far below
# every one of them keeps `check` at least as strict as either gate on every
# interpreter, and the scan is iterative, so it cannot recurse itself.
_MAX_DEPTH = 200


def _depth(text):
    """The deepest `[`/`{` nesting in JSON `text`, strings skipped."""
    depth = deepest = 0
    in_string = escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            deepest = max(deepest, depth)
        elif char in "]}":
            depth -= 1
    return deepest


def _load_json(text):
    """`text` as JSON with `_no_twins` at every depth. _MapRefused for a map
    nested past `_MAX_DEPTH` or a key either gate refuses; ValueError for
    text that is not JSON."""
    if _depth(text) > _MAX_DEPTH:
        raise _MapRefused(f"nested deeper than {_MAX_DEPTH} levels")
    return json.loads(text, object_pairs_hook=_no_twins)


def _parse(text):
    """`_load_json`, with text that is not JSON a _MapRefused too."""
    try:
        return _load_json(text)
    except ValueError as exc:
        raise _MapRefused(f"not JSON: {exc}") from exc


def load_map(text):
    """The environments object of map `text`, read as the gates read it.
    Raises _MapRefused where either gate refuses it."""
    doc = _parse(text)
    envs = _get_ci(doc, "environments", {}) if isinstance(doc, dict) else None
    if not isinstance(envs, dict):
        raise _MapRefused("no object of environments")
    problem = gate_problem(envs)
    if problem:
        raise _MapRefused(problem)
    return envs


def simulate_gate(text, command):
    """What promote-gate.sh and .ps1 decide for `command` on a clean,
    committed map `text`: "map" (refused), None (no match) or the matched
    names joined by `,` - the agreement table's comparison.

    THE RULE: refuse when EITHER gate refuses; match with the UNION of both.
    Two choices are deliberately stricter than both gates: the map is read
    before the command is checked for being blank (a blank command on a
    refused map is "map", where the gates exit 0 first), and a leading BOM
    is refused (`text` is the decoded file; the gates read utf-8-sig, as
    `check` itself does)."""
    try:
        envs = load_map(text)
    except _MapRefused:
        return "map"
    return ",".join(gate_matches(command, envs)) or None


def _environment(root, env):
    """The map's environments, read as the gates read them."""
    path = os.path.join(root, ".crew", "verify.json")
    if not os.path.lexists(path):
        raise CouldNotTell("verify-json-absent", f"{path} does not exist")
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        raise CouldNotTell("verify-json-unreadable", f"{path}: {exc}") from exc
    try:
        doc = _load_json(text)
    except _MapRefused as exc:
        raise Refused("gate-refuses-map", f"a promote gate refuses {path}: {exc}") from exc
    except ValueError as exc:
        raise CouldNotTell("verify-json-unreadable", f"{path}: {exc}") from exc
    envs = _get_ci(doc, "environments", None) if isinstance(doc, dict) else None
    if not isinstance(envs, dict):
        raise CouldNotTell("verify-json-unreadable",
                           "`environments` is not an object in .crew/verify.json")
    if env not in envs:
        raise CouldNotTell("environment-absent",
                           f"no environment {env!r} in .crew/verify.json")
    if not isinstance(envs[env], dict):
        raise CouldNotTell("verify-json-unreadable", f"environment {env!r} is not an object")
    problem = gate_problem(envs)
    if problem:
        raise Refused("gate-refuses-map", "a promote gate refuses .crew/verify.json, "
                                          f"so every command would block: {problem}")
    return envs


def _head(root):
    try:
        proc = subprocess.run([crew_common.require_tool("git"), "-C", root, "rev-parse",
                               "--verify", "-q", "HEAD"],
                              capture_output=True, text=True, check=False,
                              stdin=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CouldNotTell("head-unreadable", f"git rev-parse HEAD: {exc}") from exc
    sha = proc.stdout.strip()
    if proc.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise CouldNotTell("head-unreadable", f"git rev-parse HEAD in {root} gave no commit")
    return sha


def validated(envs, env):
    """The environment's entries, each validated, with `deploy` exactly
    their prefixes; None when it has no `github` key. Raises Refused."""
    cfg = envs[env]
    found = entries(cfg)
    if found is None:
        return None
    for index, entry in enumerate(found):
        problem = entry_problem(entry, env)
        if problem:
            raise Refused(problem[0], f"{env!r} github[{index}]: {problem[1]}")
    declared = _deploys(cfg)
    wanted = {prefix(e) for e in found}
    if declared is None or set(declared) != wanted:
        raise Refused("deploy-prefix-mismatch",
                      f"{env!r}: `deploy` must list exactly these prefixes, and nothing "
                      f"else: {sorted(wanted)}")
    return found


def check(root, env):
    """Lines to print for `check`; raises Refused or CouldNotTell."""
    envs = _environment(root, env)
    found = validated(envs, env)
    if found is None:
        return [f"environment {env!r} has no github entry", "result=ok github=none"]
    sha = _head(root)
    lines = []
    for entry in found:
        command = dispatch(entry, env, sha)
        lines += [f"dispatch: {command}",
                  f"gated-as: {','.join(gate_matches(command, envs))!r}"]
    return lines + [f"result=ok entries={len(found)} sha={sha}"]


# --- prepare (L-0644) ------------------------------------------------------
#
# `prepare` decides whether one dispatch may be attempted and records what
# `identify` needs to find its run: who dispatches, which runs of that
# workflow on that ref already exist, and that the sha is on the remote. It
# refuses (exit 2, nothing written) on the first problem, in this order:
# the entry's config (`check`'s validator, then `deploy-prefix-mismatch`),
# `unmapped-workflow`, `unknown-environment`, `class-mismatch`,
# `actor-unreadable`, `sha-not-on-remote`, `branch-tip-not-head` (no
# `shaInput` only) and `snapshot-unreadable`. The class comes from T-0009's
# classifier (`crew_dispatch.dispatch_scopes`, `dispatch_environment`),
# called read-only; `prepare` decides no authority and never reads
# unattended state. It never dispatches: its only `gh` calls are `api user`,
# two GETs and `run list`. The session runs the printed command as its own
# Bash call, so the cloud guard and promote-gate judge it.

STATE_DIR = os.path.join(".crew", ".ghdeploy")
SNAPSHOT_LIMIT = 50


def _run_gh(args, root, timeout=600):
    """`(exit status, stdout)` of `gh <args>` in `root`; the one seam every
    `gh` call goes through, stubbed by the tests. A gh that cannot start is
    exit 127; one still running after `timeout` seconds is killed, exit 124."""
    try:
        proc = subprocess.run([crew_common.require_tool("gh")] + list(args), cwd=root,
                              capture_output=True, text=True, check=False,
                              stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, ""
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)
    return proc.returncode, proc.stdout


def _clock():
    return time.time()


def _sleep(seconds):
    time.sleep(seconds)


def _gh_json(args, root, **kw):
    """`gh <args>`'s stdout as JSON, or None when it failed or is not JSON."""
    code, out = _run_gh(args, root, **kw)
    if code != 0:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


def state_path(root, env, index):
    """`.crew/.ghdeploy/<env>-<index>.json`. An environment name that is not
    one plain file-name word (a `/`, a `\\`, a leading `.`) is refused, so the
    path never leaves the state directory."""
    if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._-]*", env) is None:
        raise Refused("env-name-path", f"environment name {env!r} cannot name a state file: "
                                       "it must be [A-Za-z0-9._-], not starting with `.`")
    return os.path.join(root, STATE_DIR, f"{env}-{index}.json")


def write_state(path, state):
    """The state file, written whole: a temp file then `os.replace`, so a
    failure leaves the old file (or none) and never a partial one."""
    text = json.dumps(state, indent=2, sort_keys=True) + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _entry(root, env, index):
    """`check`'s validated entry `index` of `env`; raises."""
    found = validated(_environment(root, env), env)
    if found is None:
        raise Refused("github-none", f"environment {env!r} has no github entry")
    if not 0 <= index < len(found):
        raise Refused("index-range", f"{env!r} has {len(found)} github entries; "
                                     f"--index {index} is not one of them")
    return found[index]


def classify(root, env, command):
    """T-0009's class for the dispatch `command`, compared with the class of
    the environment's own name. Raises Refused; a classifier that raises is
    a refusal too, never a pass."""
    try:
        import cloud_guard  # pylint: disable=import-outside-toplevel
        import crew_dispatch  # pylint: disable=import-outside-toplevel
        config = cloud_guard.environments_config(root)
        scopes = crew_dispatch.dispatch_scopes(command.split()[1:])
        klass = crew_dispatch.dispatch_environment(scopes[0], config) \
            if len(scopes) == 1 else (crew_dispatch.ENV_UNKNOWN, None,
                                      "the dispatch did not read as one", None)
        named = crew_dispatch._dispatch_class(  # pylint: disable=protected-access
            env, config.get("nonProd", []))
    except Exception as exc:  # pylint: disable=broad-except
        raise Refused("classifier-failed", f"the dispatch classifier failed: "
                                           f"{type(exc).__name__}: {exc}") from exc
    if klass is None:
        raise Refused("unmapped-workflow",
                      "environments.workflows in .crew/config.json lists no key "
                      "matching this workflow; an unlisted workflow is never nonProd")
    # Either config layer's malformed block: the dispatch guard reads both.
    problem = crew_dispatch._envs_problem(config)  # pylint: disable=protected-access
    if problem or klass[0] == crew_dispatch.ENV_UNKNOWN:
        raise Refused("unknown-environment", "the classifier cannot name the "
                      f"environment: {problem or klass[2]}")
    if klass[0] != named:
        raise Refused("class-mismatch",
                      f"the dispatch classifies as {klass[0]} ({klass[1]!r}) but the "
                      f"environment {env!r} is {named}")
    return klass[0]


def branch(ref):
    """The branch NAME of an entry's ref: `refs/heads/main` is `main`. The
    branches API and `gh run list -b` take a name, and a run's `headBranch`
    is one; the dispatch itself keeps the ref as written."""
    return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref


def _actor(root):
    user = _gh_json(["api", "user"], root)
    login = user.get("login") if isinstance(user, dict) else None
    if not isinstance(login, str) or not login or not _fits(login):
        raise Refused("actor-unreadable", "`gh api user` gave no login")
    return login


def prepare(root, env, index):
    """Lines to print for `prepare`; writes the state file last."""
    entry = _entry(root, env, index)
    path = state_path(root, env, index)
    sha = _head(root)  # the dispatch deploys HEAD
    corr = (f"crew-{env}-{sha[:7]}-{secrets.token_hex(4)}"
            if entry.get("correlationInput") else None)
    command = dispatch(entry, env, sha, corr)
    klass = classify(root, env, command)
    actor = _actor(root)
    remote = _gh_json(["api", f"repos/{{owner}}/{{repo}}/commits/{sha}"], root)
    if not isinstance(remote, dict) or remote.get("sha") != sha:
        raise Refused("sha-not-on-remote", f"{sha} is not on the remote; push it first")
    if not entry.get("shaInput"):
        tip = _gh_json(["api", f"repos/{{owner}}/{{repo}}/branches/{branch(entry['ref'])}"],
                       root)
        tip = tip.get("commit") if isinstance(tip, dict) else None
        tip = tip.get("sha") if isinstance(tip, dict) else None
        if tip != sha:
            raise Refused("branch-tip-not-head",
                          f"with no `shaInput` the workflow deploys {entry['ref']!r}'s tip "
                          f"({tip or 'unreadable'}), which is not HEAD {sha}")
    runs = _gh_json(["run", "list", "-w", entry["workflow"], "-b", branch(entry["ref"]),
                     "-e", "workflow_dispatch", "-u", actor, "-L", str(SNAPSHOT_LIMIT),
                     "--json", "databaseId"], root)
    if not isinstance(runs, list) or not all(
            isinstance(r, dict) and isinstance(r.get("databaseId"), int) for r in runs):
        raise Refused("snapshot-unreadable", "`gh run list` gave no list of runs")
    t0 = int(_clock())
    watch = entry.get("watchMinutes", RANGES["watchMinutes"][2])
    state = {"env": env, "index": index, "workflow": entry["workflow"],
             "ref": entry["ref"], "sha": sha, "actor": actor, "t0": t0,
             "snapshot": sorted(r["databaseId"] for r in runs),
             "correlationId": corr, "command": command, "class": klass,
             "shaInput": entry.get("shaInput"), "deployJob": entry.get("deployJob"),
             "identifySeconds": entry.get("identifySeconds",
                                          RANGES["identifySeconds"][2]),
             "watchMinutes": watch, "deadline": t0 + watch * 60}
    write_state(path, state)
    return [f"state: {os.path.join(STATE_DIR, f'{env}-{index}.json')}",
            f"snapshot: {len(runs)} existing run(s)", command,
            f"result=ok class={klass} sha={sha}"]


# --- identify (L-0645) -----------------------------------------------------
#
# `identify` names the one run the session's dispatch created, or says it
# cannot tell. A candidate is a run of `gh run list` (same workflow, ref,
# event and actor filters as `prepare`'s snapshot) whose id is not in the
# snapshot, whose event is `workflow_dispatch`, whose branch is the ref and
# whose `createdAt` is no earlier than `t0` minus 30 seconds; with a
# correlation id, its display title must also hold the id, with no fallback
# to the time rule. Exactly one candidate is the run. It NEVER PICKS: two or
# more, none by `identifySeconds`, an unparseable `createdAt`, or a state
# file that is missing, unreadable or older than 600 seconds is could-not-tell
# (exit 3) and writes no run id. Its only `gh` call is `run list`.

POLL_SECONDS = 5
SKEW_SECONDS = 30
STALE_SECONDS = 600
RUN_FIELDS = "databaseId,createdAt,headBranch,event,displayTitle,url"


def read_state(root, env, index):
    """The state file `prepare` wrote; raises CouldNotTell."""
    path = state_path(root, env, index)
    missing = not os.path.lexists(path)
    if missing:
        raise CouldNotTell("state-file-missing", f"{path} does not exist; run prepare first")
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.loads(fh.read())
    except (OSError, ValueError) as exc:
        raise CouldNotTell("state-file-unreadable", f"{path}: {exc}") from exc
    low, high = RANGES["identifySeconds"][:2]
    good = (isinstance(state, dict)
            and all(isinstance(state.get(k), str) and state[k]
                    for k in ("workflow", "ref", "actor"))
            and isinstance(state.get("t0"), int) and not isinstance(state["t0"], bool)
            and isinstance(state.get("snapshot"), list)
            and all(isinstance(r, int) for r in state["snapshot"])
            and isinstance(state.get("correlationId"), (str, type(None)))
            and isinstance(state.get("identifySeconds"), int)
            and low <= state["identifySeconds"] <= high)
    if not good:
        raise CouldNotTell("state-file-unreadable", f"{path} is not a state file prepare wrote")
    return state


def _created(text):
    """`createdAt` as epoch seconds, or None when it is not an ISO 8601
    date-time with a zone."""
    if not isinstance(text, str):
        return None
    try:
        when = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when.timestamp() if when.tzinfo is not None else None


def pick_run(runs, state):
    """The candidates in one `gh run list` answer, never a choice among
    them. Raises CouldNotTell for an answer that is not a list of runs or a
    new run whose `createdAt` cannot be read. Returns (candidates, near):
    `near` counts new runs in the window that lack the correlation id."""
    if not (isinstance(runs, list) and all(
            isinstance(r, dict) and isinstance(r.get("databaseId"), int) for r in runs)):
        raise CouldNotTell("run-list-unreadable", "`gh run list` gave no list of runs")
    seen = set(state["snapshot"])
    corr = state.get("correlationId")
    candidates, near = [], 0
    for run in runs:
        if run["databaseId"] in seen or run.get("event") != "workflow_dispatch" \
                or run.get("headBranch") != branch(state["ref"]):
            continue
        created = _created(run.get("createdAt"))
        if created is None:
            raise CouldNotTell("created-unparseable",
                               f"a new run's createdAt {run.get('createdAt')!r} cannot be read")
        if created < state["t0"] - SKEW_SECONDS:
            continue
        if corr and corr not in str(run.get("displayTitle", "")):
            near += 1
            continue
        candidates.append(run)
    return candidates, near


def identify(root, env, index):
    """Lines to print for `identify`; writes the run id into the state file."""
    path = state_path(root, env, index)
    state = read_state(root, env, index)
    start = _clock()
    if start - state["t0"] > STALE_SECONDS:
        raise CouldNotTell("stale-prepare", f"prepare ran {int(start - state['t0'])}s ago, "
                                            f"over {STALE_SECONDS}s; prepare again")
    deadline = start + state["identifySeconds"]
    polls = state["identifySeconds"] // POLL_SECONDS + 1
    answered = near = 0
    for poll in range(polls):
        left = deadline - _clock()
        if left <= 0:
            break  # never a poll that starts after identifySeconds
        runs = _gh_json(["run", "list", "-w", state["workflow"], "-b", branch(state["ref"]),
                         "-e", "workflow_dispatch", "-u", state["actor"],
                         "-L", str(SNAPSHOT_LIMIT), "--json", RUN_FIELDS], root,
                        timeout=left)
        answered += runs is not None
        if _clock() > deadline:
            break  # an answer that came after identifySeconds is not used
        if runs is not None:
            candidates, near = pick_run(runs, state)
            if len(candidates) > 1:
                raise CouldNotTell("two-candidates", f"{len(candidates)} new runs match; "
                                                     "crew never picks one")
            if candidates:
                run = candidates[0]
                if not isinstance(run.get("url"), str) or not run["url"]:
                    raise CouldNotTell("run-url-unreadable", "the one new run has no URL")
                state.update(runId=run["databaseId"], runUrl=run.get("url"))
                write_state(path, state)
                return [f"run: {run['databaseId']} {run['url']}",
                        f"result=ok run={run['databaseId']}"]
        if poll + 1 == polls or _clock() >= deadline:
            break
        _sleep(POLL_SECONDS)
    if not answered:
        raise CouldNotTell("run-list-fails", "`gh run list` failed on every poll")
    if near:
        raise CouldNotTell("correlation-not-found", f"{near} new run(s) in the window, none "
                                                    f"titled with {state['correlationId']}")
    raise CouldNotTell("none-in-timeout", f"no new run within {state['identifySeconds']}s")


# --- watch (L-0646) --------------------------------------------------------
#
# `watch` follows the identified run in slices that fit the Bash tool's
# 600-second limit, then reads the run itself. Each call runs `gh run watch
# <id> --exit-status --interval 15` for at most one slice or until the
# deadline (`t0` + `watchMinutes`); when the watch cannot run, it polls `gh
# run view` every 15 seconds for the rest of the slice instead. A slice that
# ends with the run unfinished before the deadline is exit 75: call again.
# THE WATCH EXIT CODE NEVER DECIDES: it is recorded, and the verdict comes
# from `gh run view --json status,conclusion,headSha,jobs,url` -
#   pass (0)    completed, conclusion `success`, every job matching
#               `deployJob` succeeded (at least one matches) and, with no
#               `shaInput`, the run's head sha is the state's sha;
#   fail (1)    any other conclusion (`cancelled` too), a deploy job that
#               did not succeed or is absent, or a head sha mismatch;
#   unknown (3) the view is unreadable, the run is still running at the
#               deadline (it is left running and named), or no run id.
# It never cancels, re-runs or approves: its only `gh` calls are `run watch`
# and `run view`. The verdict and its reason go into the state file.

SLICE_SECONDS = 540
SLICE_MAX = 570
VIEW_INTERVAL = 15
VIEW_FIELDS = "status,conclusion,headSha,jobs,url"
EXIT = {"pass": 0, "fail": 1, "unknown": 3}


def judge(view, state):
    """`(verdict, reason)` from one `gh run view` answer (None: unreadable)."""
    if not isinstance(view, dict):
        return "unknown", "view-unreadable"
    if view.get("status") != "completed":
        return "unknown", "still-running"
    conclusion = view.get("conclusion")
    if not isinstance(conclusion, str) or not conclusion:
        return "unknown", "conclusion-unreadable"
    if conclusion != "success":
        return "fail", f"conclusion-{conclusion}"
    if not state.get("shaInput"):
        head = view.get("headSha")
        if not isinstance(head, str) or not head:
            return "unknown", "headsha-unreadable"
        if head != state["sha"]:
            return "fail", "headsha-mismatch"
    glob = state.get("deployJob")
    if not glob:
        return "pass", "success-deploy-job-not-checked"
    jobs = view.get("jobs")
    if not isinstance(jobs, list) or not all(
            isinstance(j, dict) and isinstance(j.get("name"), str) for j in jobs):
        return "unknown", "jobs-unreadable"
    matched = [j for j in jobs if fnmatch.fnmatchcase(j["name"], glob)]
    if not matched:
        return "fail", "deploy-job-absent"
    for job in matched:
        if job.get("conclusion") != "success":
            return "fail", f"deploy-job-{job.get('conclusion') or 'unfinished'}"
    return "pass", "success-deploy-job-succeeded"


def _view(root, run_id):
    return _gh_json(["run", "view", str(run_id), "--json", VIEW_FIELDS], root)


def watch(root, env, index, slice_seconds=SLICE_SECONDS):
    """`(exit code, lines)` for `watch`; writes the verdict into the state file."""
    path = state_path(root, env, index)
    state = read_state(root, env, index)
    run_id = state.get("runId")
    if not isinstance(run_id, int) or isinstance(run_id, bool):
        raise CouldNotTell("no-run-id-in-state", "the state file names no run; "
                                                 "identify could not tell, so nothing is watched")
    deadline = state.get("deadline")
    if not isinstance(deadline, int) or isinstance(deadline, bool):
        raise CouldNotTell("state-file-unreadable", f"{path} holds no deadline")
    start = _clock()
    end = min(start + slice_seconds, deadline)
    watched = None
    if end > start:
        watched, _out = _run_gh(["run", "watch", str(run_id), "--exit-status",
                                 "--interval", str(VIEW_INTERVAL)], root,
                                timeout=max(1, int(end - start)))
    view = _view(root, run_id)
    # A watch that could not run: poll the view for the rest of the slice.
    while judge(view, state)[1] == "still-running" and _clock() + VIEW_INTERVAL <= end \
            and watched not in (None, 124):
        _sleep(VIEW_INTERVAL)
        view = _view(root, run_id)
    verdict, reason = judge(view, state)
    if reason == "still-running" and _clock() < deadline:
        return 75, [f"run {run_id} is still running; the slice ended before the deadline",
                    f"result=again run={run_id} watch-exit={watched}"]
    url = view.get("url") if isinstance(view, dict) else None
    state.update(verdict=verdict, verdictReason=reason, watchExit=watched,
                 runUrl=url if isinstance(url, str) and url else state.get("runUrl"))
    write_state(path, state)
    lines = [f"run {run_id}: {state.get('runUrl') or '-'}"]
    if reason == "still-running":
        lines.append(f"run {run_id} is still running at the deadline; it is left running")
    return EXIT[verdict], lines + [f"result={verdict} run={run_id} reason={reason}"]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="crew_ghdeploy.py")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("check", help="validate the github entry and print the dispatch")
    cmd.add_argument("--root", default=".")
    cmd.add_argument("--env", required=True)
    cmd = sub.add_parser("prepare", help="refuse, or snapshot before the dispatch (L-0644)")
    cmd.add_argument("--root", default=".")
    cmd.add_argument("--env", required=True)
    cmd.add_argument("--index", type=int, default=0)
    cmd = sub.add_parser("identify", help="name the one run the dispatch created (L-0645)")
    cmd.add_argument("--root", default=".")
    cmd.add_argument("--env", required=True)
    cmd.add_argument("--index", type=int, default=0)
    cmd = sub.add_parser("watch", help="pass, fail or unknown from the run (L-0646)")
    cmd.add_argument("--root", default=".")
    cmd.add_argument("--env", required=True)
    cmd.add_argument("--index", type=int, default=0)
    cmd.add_argument("--slice-seconds", type=int, default=SLICE_SECONDS)
    args = parser.parse_args(argv)
    # A name or key in a message may hold any character, and a Windows
    # console or pipe is cp1252: an unencodable one must not turn a verdict
    # into a traceback with no result line (#407 CI, U+0131 / U+1F88).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    root = os.path.abspath(args.root)
    try:
        if args.command == "prepare":
            lines = prepare(root, args.env, args.index)
        elif args.command == "identify":
            lines = identify(root, args.env, args.index)
        elif args.command == "watch":
            if not 1 <= args.slice_seconds <= SLICE_MAX:
                raise Refused("slice-seconds-range", f"--slice-seconds must be 1 to {SLICE_MAX}, "
                                                     "inside the Bash tool's 600-second limit")
            code, lines = watch(root, args.env, args.index, args.slice_seconds)
            print("\n".join(lines))
            return code
        else:
            lines = check(root, args.env)
    except Refused as exc:
        print(exc)
        print(f"result=refused reason={exc.reason}")
        return 2
    except CouldNotTell as exc:
        print(exc)
        print(f"result=could-not-tell reason={exc.reason}")
        return 3
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
