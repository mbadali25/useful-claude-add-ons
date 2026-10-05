#!/usr/bin/env python3
"""promote-gate's `github`-entry rule (L-0648): the sha input of a declared
GitHub Actions dispatch must be the reviewed HEAD.

Both promote-gate flavours run this, after the environment match and once the
tree the deploy runs from is known, so the two cannot drift apart:

    python3 _promote_github.py --shell <bash|powershell> --full <sha40> \
        --envs <name>[,<name>...] -          (the command on stdin; cwd: the
                                              project dir)

For every matched environment that declares `github` entries, the entry whose
canonical prefix (`gh workflow run <workflow> --ref <ref> -f k=v ...`, what
`crew_ghdeploy.py check` makes `deploy` list) is the LONGEST substring of the
command, ignoring case, is the one being run. If it sets `shaInput`, the
command must carry `-f|--raw-field|-F|--field <shaInput>=<value>` exactly once,
the value must be 40 lowercase hex characters, and it must equal `--full`, the
full HEAD of the tree the gate judges. A substitution (`$(git rev-parse
HEAD)`) is not a literal: the gate does not run the shell that would expand
it. The command's inputs are read with T-0009's reader
(`crew_dispatch.dispatch_read`), the one T-0062's dispatch matcher uses, told
which shell runs the command.

stdout: `block<TAB><why>` per refusal, nothing when the rule is met or does not
apply (no `github` key, or an entry with no `shaInput`). Exit 0 whenever it
ran; 4 for a `github` value that is not an object or a list of objects (the
gates' "malformed map" status); anything else is a crash, which the gates
block on as "this is not a pass".

No second validator: the entry is read only as far as the prefix needs
(`workflow` and `ref` strings, `inputs` an object of strings); full validation
is `crew_ghdeploy.py check`'s.
"""
from __future__ import annotations

import json
import re
import sys

import crew_dispatch

_HEX40 = re.compile(r"[0-9a-f]{40}")


def fold(text):
    """promote-gate.sh's case fold."""
    return "".join(c.upper() if len(c.upper()) == 1 else c for c in text)


def get_ci(obj, name, default):
    keys = [k for k in obj if fold(k) == fold(name)]
    return obj[keys[0]] if keys else default


class Malformed(Exception):
    """A `github` value the gates refuse to read: exit 4."""


def entries(cfg, env):
    """The environment's `github` entries, [] when it has none."""
    github = get_ci(cfg, "github", None) if isinstance(cfg, dict) else None
    if github is None:
        return []
    if isinstance(github, dict):
        return [github]
    if isinstance(github, list) and github and all(isinstance(e, dict) for e in github):
        return github
    raise Malformed(f"environment `{env}` in .crew/verify.json has a `github` that is not "
                    "an object or a non-empty list of objects")


def prefix(entry):
    """The entry's canonical prefix, or None when it cannot be formed."""
    workflow, ref = entry.get("workflow"), entry.get("ref")
    inputs = entry.get("inputs", {})
    if not (isinstance(workflow, str) and isinstance(ref, str) and isinstance(inputs, dict)
            and all(isinstance(v, str) for v in inputs.values())):
        return None
    parts = ["gh workflow run", workflow, "--ref", ref]
    for name, value in inputs.items():
        parts += ["-f", f"{name}={value}"]
    return " ".join(parts)


def chosen(found, command, env):
    """The entry being run: the longest canonical prefix inside `command`."""
    fits = [(len(p), e) for e, p in ((e, prefix(e)) for e in found)
            if p and fold(p) in fold(command)]
    if not fits:
        raise ValueError(f"the command matches `{env}`, which declares a `github` entry, but no "
                         "entry's canonical dispatch is in it, so which entry's sha rule "
                         "applies cannot be told. Run the dispatch `crew_ghdeploy.py check "
                         f"--env {env}` prints")
    longest = max(n for n, _e in fits)
    best = [e for n, e in fits if n == longest]
    if len({json.dumps(e.get("shaInput")) for e in best}) > 1:
        raise ValueError(f"two `github` entries of `{env}` fit the command equally and name "
                         "different sha inputs, so which applies cannot be told")
    return best[0]


def sha_problem(entry, command, shell, full):
    """Why the command's sha input is not the reviewed HEAD, or None."""
    name = entry.get("shaInput")
    if not isinstance(name, str) or not name:
        return None
    flag = f"`-f {name}=<sha>`"
    kind, why, scopes = crew_dispatch.dispatch_read(command, shell)
    if kind == "unsure":
        return (f"the sha input {flag} is not a plain literal the gate can read ({why}). "
                "Pass the full sha itself, as `crew_ghdeploy.py prepare` prints it")
    values = [value for scope in scopes for got, value, _why in scope.get("inputs", [])
              if isinstance(got, str) and got.lower() == name.lower()]
    if not values:
        return f"the dispatch carries no {flag}, so the sha it deploys is the branch tip, unchecked"
    if len(values) > 1:
        return f"the dispatch gives {flag} {len(values)} times; give it exactly once"
    value = values[0]
    if value is None or not _HEX40.fullmatch(value):
        return (f"the sha input {flag} is `{value}`, not 40 lowercase hex characters: "
                "pass the full sha of HEAD, literally")
    if value != full:
        return (f"the sha input {flag} is {value}, but the tree the deploy runs from is at "
                f"{full}: the gate checks the sha being deployed. Deploy from a tree at that "
                "sha, or pass HEAD's")
    return None


def decide(command, shell, full, names):
    with open(".crew/verify.json", encoding="utf-8-sig", errors="replace") as fh:
        doc = json.load(fh)
    envs = get_ci(doc, "environments", {}) if isinstance(doc, dict) else {}
    out = []
    for env in names:
        cfg = envs.get(env) if isinstance(envs, dict) else None
        found = entries(cfg, env)
        if not found:
            continue
        try:
            problem = sha_problem(chosen(found, command, env), command, shell, full)
        except ValueError as why:
            problem = str(why)
        if problem:
            out.append(f"block\t{' '.join(problem.split())}")
    return out


def main(argv):
    args = dict(zip(argv[1:-1:2], argv[2:-1:2]))
    shell = args.get("--shell", "bash")
    if shell not in ("bash", "powershell") or argv[-1] != "-" or "--full" not in args:
        print("usage: _promote_github.py --shell <bash|powershell> --full <sha40> "
              "--envs <a,b> -", file=sys.stderr)
        return 2
    command = sys.stdin.read().replace("\r", "").rstrip("\n")
    names = [n for n in args.get("--envs", "").split(",") if n]
    try:
        records = decide(command, shell, args["--full"], names)
    except Malformed as why:
        print(why, file=sys.stderr)
        return 4
    if records:
        print("\n".join(records))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
