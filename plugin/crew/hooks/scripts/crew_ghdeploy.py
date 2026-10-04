"""GitHub Actions deploys for `/crew:promote`, as data in `.crew/verify.json`.

    python3 crew_ghdeploy.py check --root DIR --env NAME

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

THE GATES ARE SIMULATED, EXACTLY (L-1503). Both promote-gate flavours read
the map and pick environments by one shared rule, and `check` applies the
same rule (`gate_problem`, `gate_matches`):
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
So a dispatch matching several environments is not a refusal: `check`
prints `gated-as: <names>` under each dispatch, the exact set both gates
apply to that literal command. `<env>` is always in it, because `deploy`
lists the entry's prefix and the dispatch starts with it. Only the working
map is simulated: a dirty map is also matched against the committed one.
Known gap: case folding is per character (Python's simple upper case, as
promote-gate.sh); the .ps1's OrdinalIgnoreCase differs on 29 non-ASCII BMP
characters (#489 N1), so the gates themselves disagree there. A dispatch is
ASCII by the value grammar; another environment's deploy string need not be.

Exit codes, with the last stdout line always `result=...`:
  0  `result=ok entries=N sha=<sha>` after a `dispatch: <command>` and a
     `gated-as: '<names>'` line per entry, or `result=ok github=none` for an environment without a `github` key.
  2  `result=refused reason=<code>`: an entry problem, `deploy-prefix-mismatch`
     or `gate-refuses-map` (both gates refuse the map, so every command blocks).
  3  `result=could-not-tell reason=<code>`: the map is absent or unreadable,
     the environment is not in it, or HEAD cannot be read. Never read as
     "no github entry".
"""
import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import unicodedata

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


def dispatch(entry, env, sha):
    """The one literal dispatch for `sha`: prefix, sha input, correlation id."""
    line = prefix(entry)
    if entry.get("shaInput"):
        line += f" -f {entry['shaInput']}={sha}"
    if entry.get("correlationInput"):
        line += (f" -f {entry['correlationInput']}="
                 f"crew-{env}-{sha[:7]}-{secrets.token_hex(4)}")
    return line


class _MapRefused(Exception):
    """A map both gates refuse to read: every command then blocks."""


def _fold(text):
    """promote-gate.sh's case fold: per-character simple upper case, a
    character whose upper case is longer than one character kept as is."""
    return "".join(c.upper() if len(c.upper()) == 1 else c for c in text)


def _blank(text):
    """.NET's String.IsNullOrWhiteSpace, as promote-gate.sh spells it."""
    return all(c.isspace() and c not in "\x1c\x1d\x1e\x1f" for c in text)


def _no_twins(pairs):
    """json object hook: two keys equal, or equal ignoring case, refuse."""
    seen = set()
    for key, _value in pairs:
        if _fold(key) in seen:
            raise _MapRefused(f"two keys equal or differing only by case ({key!r})")
        seen.add(_fold(key))
    return dict(pairs)


def _get_ci(obj, name, default):
    """`obj[name]` with the key matched ignoring case (twins never get here)."""
    keys = [key for key in obj if _fold(key) == _fold(name)]
    return obj[keys[0]] if keys else default


def _deploys(cfg):
    """An environment's `deploy` as a list of strings, the key read ignoring
    case; None when it is neither a command nor a list of commands."""
    declared = _get_ci(cfg, "deploy", [])
    if isinstance(declared, str):
        declared = [declared]
    if not isinstance(declared, list) or not all(isinstance(d, str) for d in declared):
        return None
    return declared


def gate_problem(envs):
    """Why both promote gates refuse this map of environments, or None."""
    for name in envs:
        if not name or "," in name or any(unicodedata.category(c) == "Cc" for c in name):
            return (f"environment name {name!r} is empty or holds a control "
                    "character or a comma")
    for name, cfg in envs.items():
        if not isinstance(cfg, dict):
            return f"environment {name!r} is not an object"
        if isinstance(_get_ci(cfg, "requireHuman", None), (list, dict)):
            return f"environment {name!r} has a `requireHuman` that is a list or an object"
        if _deploys(cfg) is None:
            return (f"environment {name!r} has a `deploy` that is not a command "
                    "or a list of commands")
    return None


def gate_matches(command, envs):
    """Every environment, in file order, both promote gates apply to
    `command` on this (gate_problem-free) map: [] when none."""
    command = command.replace("\r", "").rstrip("\n")
    if _blank(command):
        return []
    folded = _fold(command)
    return [name for name, cfg in envs.items()
            if any(dep and (_fold(dep) in folded or folded in _fold(dep))
                   for dep in _deploys(cfg))]


def load_map(text):
    """The environments object of map `text`, read as the gates read it.
    Raises _MapRefused where both gates refuse it."""
    try:
        doc = json.loads(text, object_pairs_hook=_no_twins)
    except ValueError as exc:
        raise _MapRefused(f"not JSON: {exc}") from exc
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
    names joined by `,` - the agreement table's comparison."""
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
            doc = json.loads(fh.read(), object_pairs_hook=_no_twins)
    except _MapRefused as exc:
        raise Refused("gate-refuses-map", f"both promote gates refuse {path}: {exc}") from exc
    except (OSError, ValueError) as exc:
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
        raise Refused("gate-refuses-map", "both promote gates refuse .crew/verify.json, "
                                          f"so every command would block: {problem}")
    return envs


def _head(root):
    try:
        proc = subprocess.run(["git", "-C", root, "rev-parse", "--verify", "-q", "HEAD"],
                              capture_output=True, text=True, check=False,
                              stdin=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CouldNotTell("head-unreadable", f"git rev-parse HEAD: {exc}") from exc
    sha = proc.stdout.strip()
    if proc.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise CouldNotTell("head-unreadable", f"git rev-parse HEAD in {root} gave no commit")
    return sha


def check(root, env):
    """Lines to print for `check`; raises Refused or CouldNotTell."""
    envs = _environment(root, env)
    cfg = envs[env]
    found = entries(cfg)
    if found is None:
        return [f"environment {env!r} has no github entry", "result=ok github=none"]
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
    sha = _head(root)
    lines = []
    for entry in found:
        command = dispatch(entry, env, sha)
        lines += [f"dispatch: {command}",
                  f"gated-as: {','.join(gate_matches(command, envs))!r}"]
    return lines + [f"result=ok entries={len(found)} sha={sha}"]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="crew_ghdeploy.py")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("check", help="validate the github entry and print the dispatch")
    cmd.add_argument("--root", default=".")
    cmd.add_argument("--env", required=True)
    args = parser.parse_args(argv)
    try:
        lines = check(os.path.abspath(args.root), args.env)
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
