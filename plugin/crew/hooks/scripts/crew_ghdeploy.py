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

ONE ENVIRONMENT PER COMMAND: THE GATES ARE SIMULATED. Both promote-gate
flavours gate a command as the FIRST environment, in file order, with a
`deploy` string `d` that matches it either way round: promote-gate.sh with
plain substrings (`d in cmd or cmd in d`), promote-gate.ps1 with
`$cmd -like "*$d*" -or $d -like "*$cmd*"`, which ignores case and reads `*`,
`?` and `[...]` in `d` (or in the command) as wildcards. `_gate_pick` mirrors
both. `check <env>` refuses as `ambiguous-environment` unless both flavours
pick `<env>` for every dispatch it prints (rendered for two sample shas),
for every `deploy` string it lists, and pick each OTHER environment for each
of that environment's `deploy` strings. Pairwise overlap rules missed a plain
string that contains `<env>`'s prefix, and wildcards. Only the clean-map path
is simulated: with the map dirty the gates block before any deploy. Known
gap: `-like` folds case by the current culture (tr-TR maps `I` to dotless
`i`); this simulation folds culture-invariantly.

Exit codes, with the last stdout line always `result=...`:
  0  `result=ok entries=N sha=<sha>` after one `dispatch: <command>` per entry,
     or `result=ok github=none` for an environment without a `github` key.
  2  `result=refused reason=<code>`: an entry problem, `deploy-prefix-mismatch`
     or `ambiguous-environment`.
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

VALUE = re.compile(r"[A-Za-z0-9._/@:+-]+")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
WORKFLOW = re.compile(r"[A-Za-z0-9._][A-Za-z0-9._-]*\.ya?ml")
KEYS = ("workflow", "ref", "inputs", "shaInput", "correlationInput",
        "deployJob", "watchMinutes", "identifySeconds")
SAMPLE_SHAS = ("0" * 40, "f" * 40)
FLAVOURS = ("sh", "ps1")
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


def _deploys(cfg, flavour="sh"):
    """An environment's `deploy` as a list of strings, or None when malformed.
    The .ps1 reads `$p.Value.deploy`, which matches the key ignoring case; two
    keys that collide that way are a map ConvertFrom-Json refuses (ValueError)."""
    if flavour == "ps1":
        keys = [key for key in cfg if key.lower() == "deploy"]
        if len(keys) > 1:
            raise ValueError(f"keys {keys} differ only in case")
        declared = cfg[keys[0]] if keys else []
    else:
        declared = cfg.get("deploy", [])
    if isinstance(declared, str):
        declared = [declared]
    if not isinstance(declared, list) or not all(isinstance(d, str) for d in declared):
        return None
    return declared


def _like_set(pattern, start):
    """The `[set]` opening at `start`, as (regex class, index past it), read
    the way pwsh 7.4 reads it: a `]` first in the set is a member, a backtick
    makes the next character a plain member, `-` between two members is a
    range (a backtick-escaped `-` is not), and `!`/`^` are plain members.
    ValueError where pwsh throws: unclosed, empty, or a reversed range."""
    members, j = [], start + 1
    while True:
        if j >= len(pattern):
            raise ValueError(f"unclosed wildcard set in {pattern!r}")
        char = pattern[j]
        if char == "]" and members:
            break
        if char == "`":
            if j + 1 >= len(pattern):
                raise ValueError(f"unclosed wildcard set in {pattern!r}")
            members.append((pattern[j + 1], True))
            j += 2
        else:
            members.append((char, False))
            j += 1
    parts, k = [], 0
    while k < len(members):
        if k + 2 < len(members) and members[k + 1] == ("-", False):
            # A reversed range is left to `re`, whose error `_like_regex` turns
            # into the ValueError pwsh's throw corresponds to.
            parts.append(re.escape(members[k][0]) + "-" + re.escape(members[k + 2][0]))
            k += 3
        else:
            parts.append(re.escape(members[k][0]))
            k += 1
    return "[" + "".join(parts) + "]", j + 1


def _like_regex(pattern):
    """PowerShell's `-like` pattern as a regex: `*`, `?`, `[set]` (see
    `_like_set`) and a backtick escaping the next character. ValueError when
    PowerShell could not read it -- never re.error."""
    out, i = [], 0
    while i < len(pattern):
        char = pattern[i]
        if char == "`" and i + 1 < len(pattern):
            out.append(re.escape(pattern[i + 1]))
            i += 2
        elif char == "*":
            out.append(".*")
            i += 1
        elif char == "?":
            out.append(".")
            i += 1
        elif char == "[":
            regex, i = _like_set(pattern, i)
            out.append(regex)
        else:
            out.append(re.escape(char))
            i += 1
    try:
        return re.compile("".join(out), re.IGNORECASE | re.DOTALL)
    except re.error as exc:
        raise ValueError(f"unreadable wildcard pattern {pattern!r}: {exc}") from exc


def _like(text, pattern):
    """`$text -like $pattern`, culture-invariant (see the docstring's gap)."""
    return _like_regex(pattern).fullmatch(text) is not None


def _gate_pick(command, envs, flavour):
    """The environment promote-gate.<flavour> gates `command` as, or None.
    Raises ValueError where the .ps1 could not read a pattern or the map.
    The command is cleaned as each gate cleans it first: the .sh strips every
    CR and `$(...)` strips trailing newlines; both exit 0 on an empty one."""
    if flavour == "sh":
        command = command.replace("\r", "").rstrip("\n")
        if not command:
            return None
    elif not command.strip():
        return None
    for name, cfg in envs.items():
        for dep in _deploys(cfg, flavour) or []:
            if not dep:
                continue
            if flavour == "sh":
                hit = dep in command or command in dep
            else:
                hit = _like(command, f"*{dep}*") or _like(dep, f"*{command}*")
            if hit:
                return name
    return None


def _ambiguity(envs, env, mine):
    """Refuse unless both simulated gates pick `env` for each of its own
    commands and each other environment for each of that one's."""
    views = {}
    for other, cfg in envs.items():
        try:
            views[other] = ([] if not isinstance(cfg, dict) else
                            [_deploys(cfg, flavour) for flavour in FLAVOURS])
        except ValueError as exc:
            raise Refused("ambiguous-environment",
                          f"promote-gate.ps1 cannot read environment {other!r}: {exc}") from exc
        if not views[other] or None in views[other]:
            raise CouldNotTell("verify-json-unreadable",
                               f"environment {other!r} is not an object with a `deploy` "
                               "command or list of commands")
    wanted = [(dispatch(e, env, sha), env) for sha in SAMPLE_SHAS
              for e in entries(envs[env])]
    wanted += [(dep, env) for dep in dict.fromkeys(mine + views[env][1]) if dep]
    # Each other environment's strings as either gate reads them.
    wanted += [(dep, other) for other in envs if other != env
               for dep in dict.fromkeys(views[other][0] + views[other][1]) if dep]
    for command, owner in wanted:
        for flavour in FLAVOURS:
            try:
                picked = _gate_pick(command, envs, flavour)
            except ValueError as exc:
                raise Refused("ambiguous-environment",
                              f"promote-gate.ps1 cannot read a deploy pattern: {exc}") from exc
            if picked != owner:
                raise Refused("ambiguous-environment",
                              f"promote-gate.{flavour} would gate {command!r} as {picked!r}, "
                              f"not {owner!r}: a gate takes the first environment whose deploy "
                              "string matches the command")


def _environment(root, env):
    path = os.path.join(root, ".crew", "verify.json")
    if not os.path.lexists(path):
        raise CouldNotTell("verify-json-absent", f"{path} does not exist")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        raise CouldNotTell("verify-json-unreadable", f"{path}: {exc}") from exc
    envs = doc.get("environments") if isinstance(doc, dict) else None
    if not isinstance(envs, dict):
        raise CouldNotTell("verify-json-unreadable",
                           "`environments` is not an object in .crew/verify.json")
    if env not in envs:
        raise CouldNotTell("environment-absent",
                           f"no environment {env!r} in .crew/verify.json")
    if not isinstance(envs[env], dict):
        raise CouldNotTell("verify-json-unreadable", f"environment {env!r} is not an object")
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
    _ambiguity(envs, env, declared)
    sha = _head(root)
    return ([f"dispatch: {dispatch(e, env, sha)}" for e in found]
            + [f"result=ok entries={len(found)} sha={sha}"])


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
