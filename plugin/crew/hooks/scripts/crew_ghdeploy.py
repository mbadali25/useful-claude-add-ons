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
A workflow is a `.yml`/`.yaml` filename (no display name, no numeric id), a
ref is a branch (no `refs/tags/`), and there is no key for `-R/--repo`.

Exit codes, with the last stdout line always `result=...`:
  0  `result=ok entries=N sha=<sha>` after one `dispatch: <command>` per entry,
     or `result=ok github=none` for an environment without a `github` key.
  2  `result=refused reason=<code>`: an entry problem or `deploy-prefix-mismatch`.
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
    if ".." in ref:
        return "ref-dotdot"
    if ref.startswith("refs/tags/"):
        return "ref-tag"
    if not _fits(ref):
        return "ref-chars"
    return None


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
    sha, corr = entry.get("shaInput"), entry.get("correlationInput")
    for key, name in (("shaInput", sha), ("correlationInput", corr)):
        if name is not None and (not isinstance(name, str)
                                 or NAME.fullmatch(name) is None):
            return "input-name-chars", f"`{key}` is not a plain input name"
    if sha is not None and sha in inputs:
        return "sha-input-in-inputs", f"`shaInput` {sha!r} is also in `inputs`"
    if corr is not None and corr == sha:
        return "sha-equals-correlation", "`shaInput` and `correlationInput` are the same input"
    if corr is not None and corr in inputs:
        return "correlation-in-inputs", f"`correlationInput` {corr!r} is also in `inputs`"
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
        return reason, "`ref` must be a branch name in [A-Za-z0-9._/@:+-]"
    problem = _inputs_problem(entry)
    if problem:
        return problem
    if "deployJob" in entry:
        job = entry["deployJob"]
        if not isinstance(job, str) or not job or any(ord(c) < 32 for c in job):
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
    return envs[env]


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
    cfg = _environment(root, env)
    found = entries(cfg)
    if found is None:
        return [f"environment {env!r} has no github entry", "result=ok github=none"]
    for index, entry in enumerate(found):
        problem = entry_problem(entry, env)
        if problem:
            raise Refused(problem[0], f"{env} github[{index}]: {problem[1]}")
    declared = cfg.get("deploy", [])
    if isinstance(declared, str):
        declared = [declared]
    wanted = {prefix(e) for e in found}
    if not isinstance(declared, list) or not all(isinstance(d, str) for d in declared) \
            or set(declared) != wanted:
        raise Refused("deploy-prefix-mismatch",
                      f"{env}: `deploy` must list exactly these prefixes, and nothing "
                      f"else: {sorted(wanted)}")
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
