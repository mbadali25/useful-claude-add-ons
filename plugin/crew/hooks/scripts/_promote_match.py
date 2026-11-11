#!/usr/bin/env python3
"""promote-gate's containment match: which declared environments does a command deploy to?

This is the heredoc that promote-gate.sh used to run as `python - "$CMD"`, moved
here VERBATIM in its rules and messages so the one gate process (_promote_gate.py)
can call it without starting another python. The sh flavour with no python at all
never ran it, and promote-gate.ps1 has its own copy of the rule (L-1503).

    names(command, head_map, map_dirty) -> [environment, ...]   (cwd: the project dir)

raises Unreadable(why, status) where the old step printed `why` on stderr and
exited `status` (3 a map that could not be read, 4 one that is malformed); the gate
then blocks with the same message as before.
"""
import json
import os
import shutil
import subprocess
import unicodedata

MAP = ".crew/verify.json"

# THE RULE (L-1503), shared word for word with promote-gate.ps1 so both
# flavours choose the same environment for the same command:
#   - normalise the command: drop every CR, then trailing newlines; a command
#     that is then empty or whitespace deploys nothing;
#   - a declared command matches when the command CONTAINS it (L-0689: a
#     fragment of a declared command - `git rev-parse HEAD`, `development` -
#     is no deploy), literally, ignoring case (`*`, `?`, `[` are text, never
#     wildcards);
#   - every key the gate reads (`environments`, `deploy`, and below
#     `requires`, `rollback`, `rollbackReason`, `requireHuman`) is read
#     ignoring case, as PowerShell property access does, and a map holding two
#     keys that differ only by case is refused - ConvertFrom-Json refuses it,
#     and which one is policy cannot be told. Read case-sensitively here,
#     `"RequireHuman": true` demanded a human on PowerShell and nobody on bash.
#     An EXACT duplicate key is refused the same way: both parsers keep the
#     last, so `"requireHuman": true, "requireHuman": false` read as gated
#     and applied as not gated;
#   - an environment name that is empty, holds a control character or holds
#     `,` (the union's join character) refuses the map (bad_name);
#   - in the working map, `"deploy": null` and a `requireHuman` that is a list
#     or an object are malformed and refuse the map; `"deploy": []` and
#     `[""]` declare nothing;
#   - when more than one environment matches, ALL of them apply: every name is
#     printed, and below every one's `requires`, `rollback` and `requireHuman`
#     is checked - the union of their requirements. First-match made qa
#     `target=Prod` and production `target=prod` resolve differently per
#     flavour (#489 FIX1) and gated prod's command as staging; blocking it as
#     ambiguous locked `git push` out of a map with `git push staging main`
#     and `git push prod main` for good (#489 F1).
# Case is ignored because on Windows `./Deploy.ps1` and `./deploy.ps1` are
# one file: a case-sensitive gate fails open there.



def fold(text):
    """Per-character simple upper case from Python's Unicode database: a
    character whose upper case is longer than one character (`\u00df` -> `SS`)
    is kept. This is NOT exactly .NET's OrdinalIgnoreCase, which the .ps1
    uses: they agree on ASCII and almost all of the BMP, and differ on 29 BMP
    characters (#489 N1) - Python folds dotless i (U+0131) and long s
    (U+017F) onto I and S, .NET does not; .NET folds the Greek letters with
    iota subscript onto their title-case pairs, Python keeps them. A deploy
    command differing from the one run only in those characters is matched by
    one flavour and not the other."""
    return "".join(c.upper() if len(c.upper()) == 1 else c for c in text)


def blank(text):
    """.NET's String.IsNullOrWhiteSpace: Python's isspace() less U+001C-1F,
    which .NET does not count as white space."""
    return all(c.isspace() and c not in "\x1c\x1d\x1e\x1f" for c in text)



class Unreadable(Exception):
    """The old `unreadable(why, status)`: `why` went to stderr, the step exited `status`."""

    def __init__(self, why, status):
        super().__init__(why)
        self.why = why
        self.status = status


def unreadable(why, status):
    raise Unreadable(why, status)


class CaseTwins(ValueError):
    """Two keys in one JSON object that differ only by case."""


def no_case_twins(pairs):
    seen = {}
    for key, _ in pairs:
        if fold(key) in seen:
            first = seen[fold(key)]
            if first == key:
                raise CaseTwins(f"it contains the duplicate key `{key}`, so which "
                                "value is policy cannot be told")
            raise CaseTwins(f"it contains keys with different casing (`{first}` "
                            f"and `{key}`), so which one is policy cannot be told")
        seen[fold(key)] = key
    return dict(pairs)


def get_ci(obj, name, default):
    """`obj[name]`, the key matched ignoring case (case twins never get this
    far: no_case_twins refused the map)."""
    keys = [k for k in obj if fold(k) == fold(name)]
    return obj[keys[0]] if keys else default


def deploy_of(cfg):
    return get_ci(cfg, "deploy", [])


def bad_name(name):
    """A name the gate cannot carry (#489 F1): empty, holding a control
    character (Unicode Cc, what .NET's Char.IsControl tests), or holding `,`,
    the union's join character. Matched names travel one per line to the
    shell, so `"a\nb"` became the lax environments `a` and `b`.
    promote-gate.ps1's Assert-EnvironmentName applies the same test."""
    return (not name or "," in name
            or any(unicodedata.category(c) == "Cc" for c in name))




def matching(envs, strict, fcmd):
    """Every environment whose declared deploy matches `cmd`. `strict` is the
    working map's reading, which refuses a malformed entry; the COMMITTED map
    below is read leniently, as it always was - except for a bad name, which
    refuses either map (3 committed, 4 working)."""
    for name in envs:
        if bad_name(name):
            shown = "".join("?" if unicodedata.category(c) == "Cc" else c for c in name)
            unreadable(f"{'.crew/verify.json' if strict else 'the committed .crew/verify.json'} "
                       f"has the environment name `{shown}`, which is empty, holds a "
                       "control character or holds a comma - a name the gate cannot "
                       "report or record", 4 if strict else 3)
    hits = []
    for name, cfg in envs.items():
        if not isinstance(cfg, dict):
            if strict:
                unreadable(f"environment `{name}` in .crew/verify.json is a "
                           f"{type(cfg).__name__}, not an object", 4)
            continue
        if strict and isinstance(get_ci(cfg, "requireHuman", None), (list, dict)):
            unreadable(f"environment `{name}` in .crew/verify.json has a "
                       "`requireHuman` that is a list or an object, not true or "
                       "false", 4)
        # L-0648: the gate reads a `github` entry's sha rule, so a `github`
        # that is not an object or a non-empty list of objects is malformed.
        has_github = any(fold(k) == fold("github") for k in cfg)
        github = get_ci(cfg, "github", None)
        if strict and has_github and not isinstance(github, dict) and not (
                isinstance(github, list) and github
                and all(isinstance(e, dict) for e in github)):
            unreadable(f"environment `{name}` in .crew/verify.json has a `github` "
                       "that is not an object or a non-empty list of objects", 4)
        declared = deploy_of(cfg)
        if isinstance(declared, str):
            # ONE command, not a list of them: iterating a bare string walked
            # its CHARACTERS, so `deploy: "deploy-prod"` matched any command
            # holding a `d`.
            declared = [declared]
        if not isinstance(declared, list) or not all(
                isinstance(d, str) for d in declared):
            if strict:
                unreadable(f"environment `{name}` in .crew/verify.json has a "
                           "`deploy` that is not a command or a list of "
                           "commands", 4)
            continue
        # The command contains the declared text: run verbatim, with extra
        # flags, or wrapped (`cd <dir> && <declared>`). Not the reverse (L-0689):
        # a fragment of a declared command matched it, so `git rev-parse HEAD`
        # wrote an in-flight marker for a deploy that never ran.
        if any(isinstance(d, str) and d and fold(d) in fcmd
               for d in declared):
            hits.append(name)
    return hits




def names(cmd, head_map="", map_dirty=""):
    """Every environment `cmd` deploys to, in map order; [] when none."""
    cmd = cmd.replace("\r", "").rstrip("\n")
    if blank(cmd):
        return []
    fcmd = fold(cmd)
    # A dirty map is matched against the committed one too (T-0505). A committed
    # map that cannot be read or has no readable environments is could-not-tell,
    # status 3: with the working map dirty, "matched nothing" would be a guess.
    if map_dirty and head_map:
        git = shutil.which("git")
        if git is None:
            unreadable("the deploy map is uncommitted and git is not on PATH, so the "
                       "committed map cannot be read to compare with", 3)
        try:
            proc = subprocess.run([git, "cat-file", "blob", head_map],
                                  capture_output=True, check=False, timeout=10,
                                  stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as exc:
            unreadable(f"the committed .crew/verify.json could not be read: {exc}", 3)
        if proc.returncode != 0:
            unreadable("the committed .crew/verify.json could not be read "
                       f"(git cat-file exited {proc.returncode})", 3)
        try:
            committed = json.loads(proc.stdout.decode("utf-8-sig", errors="replace"),
                                   object_pairs_hook=no_case_twins)
        except ValueError as exc:
            unreadable(f"the committed .crew/verify.json does not parse as JSON: {exc}", 3)
        committed_envs = (get_ci(committed, "environments", {})
                          if isinstance(committed, dict) else None)
        if not isinstance(committed_envs, dict):
            unreadable("the committed .crew/verify.json holds no object of environments", 3)
        hits = matching(committed_envs, False, fcmd)
        if hits:
            return hits
        if not os.path.exists(MAP):
            return []
    try:
        with open(MAP, encoding="utf-8-sig", errors="replace") as fh:
            raw = fh.read()
    except OSError as exc:
        unreadable(f".crew/verify.json exists and could not be read: {exc}", 3)
    try:
        doc = json.loads(raw, object_pairs_hook=no_case_twins)
    except ValueError as exc:
        unreadable(f".crew/verify.json does not parse as JSON: {exc}", 4)
    if not isinstance(doc, dict):
        unreadable(f".crew/verify.json holds a JSON {type(doc).__name__}, "
                   "not an object", 4)
    envs = get_ci(doc, "environments", {})
    if not isinstance(envs, dict):
        unreadable(f"`environments` in .crew/verify.json is a "
                   f"{type(envs).__name__}, not an object, so no environment can "
                   "be read out of it", 4)
    return matching(envs, True, fcmd)
