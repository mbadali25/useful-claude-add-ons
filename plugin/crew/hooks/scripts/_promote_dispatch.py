#!/usr/bin/env python3
"""promote-gate's dispatch matcher (T-0062): is a workflow dispatch the deploy
of an environment `.crew/verify.json` declares?

`promote-gate.sh` runs this only when its containment match found nothing. It
reads the command and every declared `deploy` with T-0009's dispatch reader,
`crew_dispatch.dispatch_read` -- the reader `cloud_guard.py` uses, never a
second one -- so `gh workflow run <wf> -f environment=x` and its REST twin, `gh api -X POST`
on the workflow's dispatch endpoint with `-f 'inputs[environment]=x'`, reach
the same environment.

    python3 _promote_dispatch.py "<command>"     (cwd: the project dir)

stdout, one record per line, tab-separated:

    env<TAB><name>    the command deploys to <name> (several: all apply)
    block<TAB><why>   could not tell, or a declared workflow fitting no
                      single environment: the gate blocks, naming <why>

and nothing at all when the command is not a deploy this reads: no declared
deploy is a dispatch, the command sends no dispatch, or it dispatches a
workflow file no declared deploy names. Exit 0 whenever it ran; anything else
is a crash, which the gate blocks on as "this is not a pass".

THE RULE.
- A declared deploy is a dispatch when the reader reads one in it. Each
  `$(...)` or backtick substitution in a DECLARED string becomes the one word
  `SUBSTITUTED`, and an input whose declared value is that word is not
  compared (`-f ref=$(git rev-parse HEAD)`). The command judged gets no such
  treatment: a substitution there is could-not-tell.
- Workflow names compare after dropping a leading `.github/workflows/`, and
  only names ending `.yml`/`.yaml`; a numeric id or a display name cannot be
  compared with a file name, so it is could-not-tell (U2).
- A dispatch of a declared workflow is the deploy of every environment whose
  declared dispatch names it and whose declared literal inputs all appear in
  the command with the same value; extra inputs are allowed (U3). Exactly one
  environment must fit. None, or several, blocks.
- Could not tell, which blocks: a dispatch-shaped command the reader refuses;
  a command input the reader cannot name or read; one input given two
  values; a workflow that is not a file name; a declared dispatch the reader
  itself cannot read. A map that declares no dispatch sees no change (U4).
- With the map dirty (`CREW_MAP_DIRTY`), the committed map (`CREW_HEAD_MAP`,
  a blob id) is matched first, as the containment match does.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import crew_dispatch

PLACEHOLDER = "SUBSTITUTED"
_WORKFLOW_DIR = ".github/workflows/"


class Block(Exception):
    """The gate must block, for the reason carried."""


def fold(text):
    """promote-gate.sh's case fold for the map's keys."""
    return "".join(c.upper() if len(c.upper()) == 1 else c for c in text)


def get_ci(obj, name, default):
    keys = [k for k in obj if fold(k) == fold(name)]
    return obj[keys[0]] if keys else default


def substitute(text):
    """`text` with each `$(...)` and backtick substitution outside single
    quotes replaced by PLACEHOLDER. An unbalanced one is left as written, so
    the reader refuses the declared string (could not tell)."""
    out, i, quoted = [], 0, False
    while i < len(text):
        char = text[i]
        if char == "'":
            quoted = not quoted
        elif not quoted and text.startswith("$(", i):
            depth, j = 1, i + 2
            while j < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            if depth == 0:
                out.append(PLACEHOLDER)
                i = j
                continue
        elif not quoted and char == "`":
            end = text.find("`", i + 1)
            if end != -1:
                out.append(PLACEHOLDER)
                i = end + 1
                continue
        out.append(char)
        i += 1
    return "".join(out)


def workflow_file(scope, whose):
    """The scope's workflow as a comparable file name, or Block."""
    named = scope.get("workflow")
    if named is None or scope.get("extra"):
        raise Block(f"{whose} names no single workflow")
    name = named[len(_WORKFLOW_DIR):] if named.startswith(_WORKFLOW_DIR) else named
    if not name.endswith((".yml", ".yaml")):
        raise Block(f"{whose} names the workflow `{named}`, which is not a "
                    "file name (an id or a display name cannot be compared "
                    "with a declared workflow file)")
    return name


def command_inputs(scope):
    """`{name: value}` for the command's inputs, or Block."""
    got = {}
    for name, value, why in scope.get("inputs", []):
        if value is None or name == "*":
            raise Block(f"the command's input cannot be read: {why}")
        if got.get(name, value) != value:
            raise Block(f"the command gives the input `{name}` two values")
        got[name] = value
    return got


def declared(envs):
    """Every declared dispatch as `(env, scope)`, plus the declared deploys
    the reader cannot read, as `(env, command, why)`."""
    found, unsure = [], []
    for env, cfg in envs.items():
        if not isinstance(cfg, dict):
            continue
        deploys = get_ci(cfg, "deploy", [])
        deploys = [deploys] if isinstance(deploys, str) else deploys
        if not isinstance(deploys, list):
            continue
        for command in deploys:
            if not isinstance(command, str) or not command.strip():
                continue
            kind, why, scopes = crew_dispatch.dispatch_read(
                substitute(command), "bash")
            if kind == "unsure":
                unsure.append((env, command, why))
            found += [(env, scope) for scope in scopes]
    return found, unsure


def fits(scope_inputs, decl):
    """Whether every literal input the declared dispatch gives is in the
    command with the same value."""
    for name, value, why in decl.get("inputs", []):
        if value is None or name == "*":
            raise Block(f"a declared deploy's input cannot be read: {why}")
        if value == PLACEHOLDER:
            continue
        if scope_inputs.get(name) != value:
            return False
    return True


def match(scopes, envs, label):
    """The environments the command's dispatches deploy to under one map."""
    found, unsure = declared(envs)
    if unsure:
        env, command, why = unsure[0]
        raise Block(f"the deploy `{env}` declares in {label} looks like a "
                    f"workflow dispatch crew cannot read ({why}): `{command}`")
    names = {}
    for env, decl in found:
        names.setdefault(workflow_file(decl, f"the deploy `{env}` declares"),
                         []).append((env, decl))
    hits = []
    for scope in scopes:
        workflow = workflow_file(scope, "the command")
        if workflow not in names:
            continue
        inputs = command_inputs(scope)
        fit = sorted({env for env, decl in names[workflow] if fits(inputs, decl)})
        if len(fit) != 1:
            which = ("no declared environment" if not fit else
                     "more than one declared environment (" + ", ".join(fit) + ")")
            raise Block(f"the dispatch of `{workflow}` fits {which} in {label}, "
                        "so which environment's preconditions apply cannot be "
                        "told. Give the inputs a declared deploy gives, "
                        "literally")
        hits += [env for env in fit if env not in hits]
    return hits


def committed_envs():
    blob = os.environ.get("CREW_HEAD_MAP")
    if not (os.environ.get("CREW_MAP_DIRTY") and blob):
        return None
    git = shutil.which("git")
    if git is None:
        raise Block("the deploy map is uncommitted and git is not on PATH")
    proc = subprocess.run([git, "cat-file", "blob", blob], capture_output=True,
                          check=False, timeout=10, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise Block("the committed .crew/verify.json could not be read")
    return get_ci(json.loads(proc.stdout.decode("utf-8-sig", errors="replace")),
                  "environments", {})


def working_envs():
    if not os.path.exists(".crew/verify.json"):
        return None
    with open(".crew/verify.json", encoding="utf-8-sig", errors="replace") as fh:
        return get_ci(json.load(fh), "environments", {})


def decide(command):
    """The records to print for `command`."""
    maps = [(label, envs) for label, envs in (
        ("the committed .crew/verify.json", committed_envs()),
        (".crew/verify.json", working_envs())) if isinstance(envs, dict)]
    if not any(any(declared(envs)) for _label, envs in maps):
        return []
    kind, why, scopes = crew_dispatch.dispatch_read(command, "bash")
    if kind == "none" or (kind == "read" and not scopes):
        return []
    if kind == "unsure":
        raise Block(f"the gate could not tell whether this command deploys: "
                    f"it sends a workflow dispatch crew cannot read ({why}). "
                    "Spell it with plain literal words, as a declared deploy is")
    for label, envs in maps:
        hits = match(scopes, envs, label)
        if hits:
            return [f"env\t{env}" for env in hits]
    return []


def main(argv):
    command = argv[1].replace("\r", "").rstrip("\n") if len(argv) > 1 else ""
    try:
        records = decide(command) if command.strip() else []
    except Block as why:
        text = str(why)
        if "could not tell" not in text:
            text = f"the gate could not tell which environment this deploys: {text}"
        records = ["block\t" + " ".join(text.split())]
    if records:
        print("\n".join(records))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
