#!/usr/bin/env python3
"""promote-gate's `github`-entry rule (L-0648): the sha input of a declared
GitHub Actions dispatch must be the reviewed HEAD.

Both promote-gate flavours run this, after the environment match and once the
tree the deploy runs from is known, so the two cannot drift apart:

    python3 _promote_github.py --shell <bash|powershell> --full <sha40> \
        --envs <name>[,<name>...] [--tree <dir> --deadline <unix time>] -
                                             (the command on stdin; cwd: the
                                              project dir)

With `--tree` the `github` entries are read from the map that is policy for
the deployed sha (L-0768: the one committed in it, else the project dir's),
the map every other requirement comes from; a map that cannot be read is a
crash, which both gates block on.

For every matched environment that declares `github` entries, each entry
whose canonical prefix (`gh workflow run <workflow> --ref <ref> -f k=v ...`,
what `crew_ghdeploy.py check` makes `deploy` list) is a substring of the
command, ignoring case, may be being run. Each dispatch in the command is
bound to the entries it fits; per environment, the one with the LONGEST
prefix among them is the one that dispatch runs. If it sets `shaInput`, that
dispatch must carry `-f|--raw-field|-F|--field <shaInput>=<value>` exactly once,
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


_ABSENT = object()


def entries(cfg, env):
    """The environment's `github` entries, [] when it has no `github` key (a
    key holding null is malformed, never "none")."""
    github = get_ci(cfg, "github", _ABSENT) if isinstance(cfg, dict) else _ABSENT
    if github is _ABSENT:
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
    """`[(prefix length, entry)]`: every entry whose canonical prefix is
    inside `command`. Which of them a dispatch runs is decided per dispatch
    (`sha_problems`): keeping only the longest here would let a second
    dispatch of a shorter entry go unchecked."""
    fits = [(len(p), e) for e, p in ((e, prefix(e)) for e in found)
            if p and fold(p) in fold(command)]
    if not fits:
        raise ValueError(f"the command matches `{env}`, which declares a `github` entry, but no "
                         "entry's canonical dispatch is in it, so which entry's sha rule "
                         "applies cannot be told. Run the dispatch `crew_ghdeploy.py check "
                         f"--env {env}` prints")
    return fits


def _runs(fit, picked, where):
    """The entries a dispatch fitting `fit` (indices into `picked`) runs: per
    environment (`where[i]` = (env, prefix length)), the longest prefix.
    Raises ValueError when two equally long ones name different sha inputs."""
    runs = []
    for env in dict.fromkeys(where[i][0] for i in fit):
        mine = [i for i in fit if where[i][0] == env]
        longest = max(where[i][1] for i in mine)
        best = [i for i in mine if where[i][1] == longest]
        if len({json.dumps(picked[i].get("shaInput")) for i in best}) > 1:
            raise ValueError(f"two `github` entries of `{env}` fit the command equally and name "
                             "different sha inputs, so which applies cannot be told")
        runs.append(best[0])
    return runs


def _workflow(name):
    name = name or ""
    return name[len(".github/workflows/"):] if name.startswith(".github/workflows/") else name


def _name_problem(entry):
    """Why a present `shaInput` names no input, or None."""
    name = entry["shaInput"]
    if not isinstance(name, str) or not name:
        return (f"the `github` entry's `shaInput` is {json.dumps(name)}, which names no input, "
                "so the sha rule cannot be applied. Fix the entry (`crew_ghdeploy.py check`)")
    return None


def sha_problems(picked, command, shell, full, where=None):
    """Why the command's dispatches do not carry the reviewed HEAD, for the
    entries `picked` (every entry of a matched environment whose prefix is in
    the command; `where[i]` = (environment, prefix length), default one
    environment each): [] when they do. Each dispatch of a picked entry's
    workflow is bound to the picked entries whose ref and declared inputs it
    gives (`_fits`) -
    it must fit at least one, and carries the sha input of the entry it runs
    in each environment (`_runs`), on its own inputs: neither another
    dispatch's sha input nor the declared text elsewhere on the line (an
    `echo`) vouches for it. Every picked entry with `shaInput` needs a
    dispatch that fits it."""
    where = where or [(i, 0) for i in range(len(picked))]
    problems = [p for p in (_name_problem(e) for e in picked if "shaInput" in e) if p]
    checked = [e for e in picked if "shaInput" in e]
    if problems or not checked:
        return problems
    kind, why, scopes = crew_dispatch.dispatch_read(command, shell)
    if kind == "unsure":
        flags = ", ".join(sorted({f"`-f {e['shaInput']}=<sha>`" for e in checked}))
        return [f"the sha input {flags} is not a plain literal the gate can read ({why}). "
                "Pass the full sha itself, as `crew_ghdeploy.py prepare` prints it"]
    workflows = {_workflow(e.get("workflow")) for e in picked}
    seen = set()
    for scope in scopes:
        if _workflow(scope.get("workflow")) not in workflows:
            continue
        fit = [i for i, e in enumerate(picked) if _workflow(e.get("workflow")) ==
               _workflow(scope.get("workflow")) and _fits(scope, e)]
        if not fit:
            return [f"a dispatch of `{scope.get('workflow')}` in the command does not give any "
                    "matched entry's `ref` and declared inputs, so it fits no declared environment and "
                    "which environment's preconditions apply cannot be told"]
        seen.update(fit)
        try:
            runs = _runs(fit, picked, where)
        except ValueError as why:
            return [str(why)]
        for i in runs:
            entry = picked[i]
            if "shaInput" in entry:
                problem = _scope_problem(scope, entry["shaInput"],
                                         f"`-f {entry['shaInput']}=<sha>`", full)
                if problem:
                    return [problem]
    missing = [e for i, e in enumerate(picked) if "shaInput" in e and i not in seen]
    if missing:
        return [f"the gate cannot read a dispatch of `{missing[0].get('workflow')}` giving the "
                "matched entry's declared inputs, so its `-f "
                f"{missing[0]['shaInput']}=<sha>` cannot be checked"]
    return []


def _fits(scope, entry):
    """Whether the dispatch gives the entry's `ref`, exactly once and ignoring
    case as the prefix match does, and every one of its declared inputs, with
    the same value. Without the ref, two entries differing only in `ref` both
    fit and the longer one's (maybe absent) sha input stood in for the other's."""
    refs = scope.get("refs", [])
    ref = entry.get("ref")
    if not (isinstance(ref, str) and len(refs) == 1 and isinstance(refs[0], str)
            and fold(refs[0]) == fold(ref)):
        return False
    given = {}
    for got, value, _why in scope.get("inputs", []):
        if isinstance(got, str):
            given.setdefault(got.lower(), []).append(value)
    return all(given.get(str(k).lower()) == [v] for k, v in entry.get("inputs", {}).items())


def _scope_problem(scope, name, flag, full):
    values = [value for got, value, _why in scope.get("inputs", [])
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


def _policy_doc(tree, full, deadline):
    """The map that is policy for deploying `full` from `tree` (L-0768): the
    one committed in that sha, else the project dir's - `_promote_review`'s
    reading, so the github rule and every other requirement come from the same
    map. Without `--tree` (a direct call), the project dir's working map."""
    if tree is None:
        with open(".crew/verify.json", encoding="utf-8-sig", errors="replace") as fh:
            return json.load(fh)
    import _promote_review  # pylint: disable=import-outside-toplevel
    try:
        text, _ = _promote_review.policy_map_text(tree, full.lower(), deadline)
    except _promote_review.CouldNotTell as exc:
        raise ValueError(str(exc)) from exc
    return json.loads(text)


def decide(command, shell, full, names, tree=None, deadline=None):
    doc = _policy_doc(tree, full, deadline)
    envs = get_ci(doc, "environments", {}) if isinstance(doc, dict) else {}
    picked, where, out = [], [], []
    for env in names:
        cfg = envs.get(env) if isinstance(envs, dict) else None
        found = entries(cfg, env)
        if not found:
            continue
        try:
            for length, entry in chosen(found, command, env):
                picked.append(entry)
                where.append((env, length))
        except ValueError as why:
            out.append(str(why))
    out += sha_problems(picked, command, shell, full, where) if not out else []
    return [f"block\t{' '.join(problem.split())}" for problem in out]


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
        records = decide(command, shell, args["--full"], names, args.get("--tree"),
                         args.get("--deadline"))
    except Malformed as why:
        print(why, file=sys.stderr)
        return 4
    except ValueError as why:
        # Could not tell: a policy map that does not parse (L-0768). Non-zero,
        # so both gates block; never read as "no github entry".
        print(f"_promote_github.py: the deployment map that is policy for this sha does not "
              f"parse: {why}", file=sys.stderr)
        return 3
    if records:
        print("\n".join(records))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
