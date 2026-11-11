"""Mass delete, mass create, mass change: the stop that stays when a human step
is opted out of (crew 1.3.36).

The owner's rule: full automation, except a MASS delete, a MASS create or a MASS
change, which wait for a human yes. This module is that exception. It is armed
by `guards.mass.enabled: true`, or by a double-confirmed `humanOnly` opt-out
(`crew_humanonly.resolve`), and by nothing else (`settings`): a repo that did
neither sees no change at all. `cloud_guard.py` calls it for every shell command.

THE LIMITS (`guards.mass`, `settings`). A count AT the limit is mass:

    deleteCount 10    files a command would remove
    createCount 20    files it would add
    changeCount 30    files it would rewrite

They were measured on this repo's own history (104 days, 623 merged PRs; a PR
adds a median 0 and p95 16 files, changes a median 5 and p95 30, deletes 0 in
all but 15). `guards.mass.overrides.<files|git|terraform>.<deleteCount|
createCount|changeCount>` replaces one limit for one kind of command; the
terraform defaults (delete 3, create 10, change 10) are INFERRED - there was no
terraform in the history to measure. `guards.mass.exempt` adds repo-relative
globs (generated files) that never count. The machine file sets the limits and
the exempt globs; the repo file can lower a limit and turn the stop on, never
loosen what the owner chose.

WHAT A HOOK CAN SEE. The command's text, the file system, and `git`:

    files      rm / unlink / `rd /s` / Remove-Item (counted after glob expansion;
               `-r` walks a directory), cp / mv / rsync / Copy-Item / Move-Item
               (new files create, existing ones change), touch, `sed -i` /
               `perl -pi` (change), `find -delete` / `rsync --delete` (delete)
    git        `git commit`, `git push`, `gh pr create`: the files the commit
               or the whole branch adds, deletes and changes against its base
               (`git diff --name-status -M`) - so Write and Edit work is counted
               here, at the point it is about to be committed or shared;
               `git clean -f`, `git rm` (delete); `git reset --hard`,
               `git checkout -f` / `-- <paths>`, `git restore` (change)
    terraform  `terraform apply <plan>`: the plan's own resource changes
               (`terraform show -json`); `destroy` and `apply -auto-approve`
               with no plan file to read
    sql        an unfiltered `DELETE FROM t` or `UPDATE t SET ...` (no WHERE, or
               `WHERE 1=1`) handed to psql, mysql, sqlcmd and the like

COUNTS IT CANNOT TAKE are "could not tell", and could not tell is mass: a
variable or substitution in a path, a relative path after a `cd`, a POSIX path
Git Bash maps somewhere this process cannot see, `find -delete`, `xargs rm`, a
git or terraform command that failed, and a row count (SQL: no command text says
how many rows an unfiltered DELETE hits, so it always asks).

EXEMPT. Regenerable directories never count: node_modules, __pycache__, .venv,
venv, caches, build, dist, .work, egg-info, and worktrees (the worktree
directory itself, `~/.claude/crew/worktrees/<repo>/<name>`, by path).

WHAT IT DOES NOT SEE. A script (`bash cleanup.sh`, `python -c`, `make clean`),
anything an MCP server does, the Write and Edit tools before they are
committed, `tar -x` / `unzip`, `git merge` / `pull` / `checkout <branch>`, and
many small commands each under the limit. `git push --force` stays
`guards.forcePush`'s. A tripwire in front of native permissions, not a sandbox.

HOW A HUMAN APPROVES. A stopped command prints an id (12 hex digits, a digest of
the exact command text and the worktree - one id covers every rule that command
trips). The owner types `/crew:approve-mass <id>` in the session;
`approval_hook.py` writes `<git-common-dir>/crew/mass-approvals/<id>.json` from
that prompt - the one input the session does not author, and a directory the
scope guard refuses the session to write. `live_approval` accepts it for
MASS_APPROVAL_TTL seconds, for that command only. Attended, a stop is an `ask`
(Claude Code's own prompt decides); unattended it is a `deny`, because nobody is
there to answer.

Standard library only; imports `crew_state` for nothing at module load.
"""
from __future__ import annotations

import fnmatch
import glob
import hashlib
import json
import os
import re
import subprocess
import time

MASS_DELETE, MASS_CREATE, MASS_CHANGE = "massDelete", "massCreate", "massChange"
RULES = (MASS_DELETE, MASS_CREATE, MASS_CHANGE)
COUNT_KEY = {MASS_DELETE: "deleteCount", MASS_CREATE: "createCount",
             MASS_CHANGE: "changeCount"}
DEFAULT_LIMITS = {"deleteCount": 10, "createCount": 20, "changeCount": 30}
CATEGORIES = ("files", "git", "terraform")
# INFERRED, not measured: a plan should rarely touch more than a handful of
# resources, and destroying three is the review line.
DEFAULT_OVERRIDES = {"terraform": {"deleteCount": 3, "createCount": 10, "changeCount": 10}}

EXEMPT_NAMES = frozenset((
    "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", ".cache", "build", "dist", ".work", ".eggs", "_build"))
WORKTREES = "worktrees"
MAX_WALK = 5000

APPROVAL_DIR = "mass-approvals"
MASS_APPROVAL_TTL = 900
GIT_TIMEOUT = 15
TF_TIMEOUT = 30

_ID_RE = re.compile(r"^[0-9a-f]{12}$")
_GLOB_RE = re.compile(r"[*?\[]")
_DYNAMIC_RE = re.compile(r"[$`]|\$\(")
_DRIVE_RE = re.compile(r"^/([A-Za-z])(/.*)?$")
_GIT_VALUE_OPTS = frozenset(("-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
                             "--config-env", "--attr-source", "--super-prefix"))
_RM_HEADS = frozenset(("rm", "unlink"))
_PS_RM = frozenset(("remove-item", "ri", "rm", "del", "erase", "rd", "rmdir"))
_PS_COPY = frozenset(("copy-item", "cpi", "copy", "cp", "move-item", "mi", "move", "mv"))
_CMD_RM = frozenset(("rd", "rmdir", "del", "erase"))
_SQL_HEADS = frozenset(("psql", "mysql", "mariadb", "sqlcmd", "invoke-sqlcmd", "sqlite3",
                        "mysqlsh", "osql", "clickhouse-client", "cockroach", "usql"))
_TERRAFORMS = frozenset(("terraform", "tofu"))
_WRITES_RE = re.compile(
    r"(?<!>)>>?(?!>)(?!\s*(?:&\d|/dev/null\b|\$null\b))|"
    r"\b(?:tee|cp|mv|rm|ln|touch|mkdir|rmdir|install|dd|rsync|truncate|sed|perl|"
    r"python[0-9.]*|py|node|chmod|echo|printf|set-content|add-content|out-file|"
    r"new-item|copy-item|move-item|remove-item|rename-item|clear-content|set-item|ni|"
    r"sc|ac)\b", re.IGNORECASE)
_STATEMENT_RE = re.compile(r"\b(delete\s+from|update)\b(.*)", re.IGNORECASE | re.DOTALL)
_TRIVIAL_WHERE_RE = re.compile(r"\bwhere\s+(?:1\s*=\s*1|true|'1'\s*=\s*'1')\s*$",
                               re.IGNORECASE)


class Spec:
    """What one recognised command would do, before anything is counted."""

    def __init__(self, rule, what, kind, operands=(), recursive=False, git=None,
                 unknown=False, dest=None, category="files", shared=None, extra=None):
        self.rule, self.what, self.kind = rule, what, kind
        self.operands, self.recursive = list(operands), recursive
        self.git, self.unknown, self.dest = git, unknown, dest
        self.category = category
        self.shared = shared if shared is not None else {}
        self.extra = extra
        self.why = ""  # the real reason a count came back None (set where it fails)


# --- settings -----------------------------------------------------------------------

def _count(value):
    """A positive integer limit, else None (a bool is not a number here)."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _read_layer(path):
    """The `guards.mass` object of one config file, or None when absent. A file
    or block that cannot be read gives `{}`: the layer says nothing."""
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            cfg = json.loads(handle.read())
    except (OSError, ValueError):
        return None
    guards = cfg.get("guards") if isinstance(cfg, dict) else None
    block = guards.get("mass") if isinstance(guards, dict) else None
    return block if isinstance(block, dict) else None


def settings(root, global_path=None):
    """`{"armed", "why", "limits", "exempt"}` for `root`. Never raises: anything
    that cannot be told leaves the guard unarmed (an unknown switch is no
    switch) and a limit that cannot be read falls back to the default.

    `limits` is `{category: {deleteCount, createCount, changeCount}}`. The
    machine file sets the limits and the exempt globs; the repo file may only
    LOWER a limit and turn the stop on, because a cloned repo's config must
    never loosen what the owner chose."""
    try:
        import crew_common  # pylint: disable=import-outside-toplevel
        import crew_state  # pylint: disable=import-outside-toplevel
        machine_path = global_path or crew_state.GLOBAL_CONFIG_PATH
        machine = _read_layer(machine_path)
        repo = _read_layer(crew_common.repo_config_file(root, "config.json"))
        enabled = any(layer.get("enabled") is True for layer in (machine or {}, repo or {}))
        why = "guards.mass.enabled" if enabled else None
        if not enabled and opted_out(root, global_path):
            enabled, why = True, "humanOnly opt-out"
        return {"armed": enabled, "why": why, "limits": _limits(machine, repo),
                "exempt": _exempt_globs(machine)}
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return {"armed": False, "why": None, "limits": _limits(None, None), "exempt": ()}


def _layer_value(layer, category, key):
    """One layer's limit for `category` and `key`: its override, else its
    top-level count, else None. A bad value is None, never a number."""
    if not isinstance(layer, dict):
        return None
    over = layer.get("overrides")
    over = over.get(category) if isinstance(over, dict) else None
    value = _count(over.get(key)) if isinstance(over, dict) else None
    return value if value is not None else _count(layer.get(key))


def _limits(machine, repo):
    out = {}
    for category in CATEGORIES:
        out[category] = {}
        for key, default in DEFAULT_LIMITS.items():
            base = _layer_value(machine, category, key)
            if base is None:
                base = DEFAULT_OVERRIDES.get(category, {}).get(key, default)
            elif category in DEFAULT_OVERRIDES and _count(
                    ((machine.get("overrides") or {}).get(category) or {}).get(key)) is None:
                # a machine top-level count does not raise a category's own default
                base = min(base, DEFAULT_OVERRIDES[category].get(key, base))
            lower = _layer_value(repo, category, key)
            out[category][key] = min(base, lower) if lower is not None else base
    return out


def _exempt_globs(layer):
    block = layer.get("exempt") if isinstance(layer, dict) else None
    if not isinstance(block, list):
        return ()
    return tuple(g for g in block if isinstance(g, str) and g.strip())


def opted_out(root, global_path=None):
    """True when a human-only rule is opted out of for `root` (a double-confirmed
    `humanOnly.approve` or `humanOnly.promoteMarker` `false`). Anything that
    cannot be told is False: an unknown opt-out is no opt-out."""
    try:
        import crew_common  # pylint: disable=import-outside-toplevel
        import crew_humanonly  # pylint: disable=import-outside-toplevel
        import crew_state  # pylint: disable=import-outside-toplevel
        paths = (global_path or crew_state.GLOBAL_CONFIG_PATH,
                 crew_common.repo_config_file(root, "config.json"))
        if not any(_mentions(path) for path in paths):
            return False
        return any(crew_humanonly.resolve(root, key, global_path=global_path).get("humanOnly")
                   is False for key in crew_humanonly.KEYS)
    except Exception:  # noqa: BLE001  # pylint: disable=broad-except
        return False


def armed(root, global_path=None):
    """`settings(...)["armed"]`."""
    return settings(root, global_path)["armed"]


def _mentions(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return "humanOnly" in handle.read()
    except OSError:
        return False


# --- exemptions ---------------------------------------------------------------------

def _parts(path):
    return [p.lower() for p in re.split(r"[\\/]+", path) if p and p not in (".",)]


def exempt(path, relative=False, globs=()):
    """True when `path` is a regenerable file or directory that never counts.
    `relative` is a path inside a tree already being walked: any `worktrees`
    component exempts it. An absolute path exempts a `worktrees` component only
    when at most two components follow it (`worktrees/<repo>/<name>`), so a repo
    that LIVES in a worktree is still guarded."""
    parts = _parts(path)
    for index, part in enumerate(parts):
        if part in EXEMPT_NAMES or part.endswith(".egg-info"):
            return True
        if part == WORKTREES and (relative or len(parts) - index - 1 <= 2):
            return True
    if globs:
        text = "/".join(parts)
        return any(fnmatch.fnmatch(text, g.lower().replace("\\", "/")) for g in globs)
    return False


# --- recognising a command ----------------------------------------------------------

def _option_letters(args):
    """`(letters, longs, operands)` of a POSIX-style argument list."""
    letters, longs, operands, rest = set(), set(), [], False
    for arg in args:
        if rest or not arg.startswith("-") or arg == "-":
            operands.append(arg)
        elif arg == "--":
            rest = True
        elif arg.startswith("--"):
            longs.add(arg.split("=", 1)[0].lower())
        else:
            letters.update(arg[1:])
    return letters, longs, operands


def _git_split(args):
    """`(cwd_override, subcommand, rest)` of a git argument list."""
    index, override = 0, None
    while index < len(args) and args[index].startswith("-"):
        if args[index] == "-C" and index + 1 < len(args):
            # git resolves each -C against the one before it (an empty one is a no-op)
            value = args[index + 1]
            if value:
                override = value if override is None else os.path.join(override, value)
            index += 2
        elif args[index] in _GIT_VALUE_OPTS:
            index += 2
        else:
            index += 1
    if index >= len(args):
        return override, None, []
    return override, args[index], args[index + 1:]


def _after_dashdash(rest):
    return rest[rest.index("--") + 1:] if "--" in rest else []


def _diff_specs(what, override, argv):
    """Three specs (delete, create, change) over one `git diff --name-status`."""
    shared = {}
    return [Spec(rule, what, "git-diff", git=(override, argv), category="git", shared=shared)
            for rule in RULES]


def _classify_git(args, fed):
    override, sub, rest = _git_split(args)
    if sub is None:
        return []
    flags = {a for a in rest if a.startswith("-")}
    letters = set("".join(a[1:] for a in rest if a.startswith("-") and not a.startswith("--")))
    paths = _after_dashdash(rest)
    out = []
    if sub == "reset" and "--hard" in flags:
        target = next((a for a in rest if not a.startswith("-")), "HEAD")
        out = [Spec(MASS_CHANGE, "git reset --hard", "git-files", category="git",
                    git=(override, ["diff", "--name-only", target, "--"]))]
    elif sub == "checkout":
        if "--" not in rest and not (letters & {"f"} or flags & {"--force"}) \
                and "." not in rest:
            return []
        tree = next((a for a in rest if not a.startswith("-") and a != "."), None)
        if "--" in rest:
            tree = next((a for a in rest[:rest.index("--")] if not a.startswith("-")), None)
        spec_paths = paths or (["."] if "." in rest else [])
        if not spec_paths:  # `checkout -f <branch>`: discards every local change
            out = [Spec(MASS_CHANGE, "git checkout -f", "git-files", category="git",
                        git=(override, ["diff", "--name-only", "HEAD", "--"]))]
        else:
            argv = ["diff", "--name-only"] + ([tree] if tree else []) + ["--"] + spec_paths
            out = [Spec(MASS_CHANGE, "git checkout -- " + " ".join(spec_paths), "git-files",
                        category="git", git=(override, argv))]
    elif sub == "restore":
        if "--staged" in flags and "--worktree" not in flags and "-W" not in flags:
            return []
        source = next((a.split("=", 1)[1] for a in rest if a.startswith("--source=")), None)
        spec_paths = paths or [a for a in rest if not a.startswith("-")]
        argv = ["diff", "--name-only"] + ([source] if source else []) + ["--"] + spec_paths
        out = [Spec(MASS_CHANGE, "git restore " + " ".join(spec_paths), "git-files",
                    category="git", git=(override, argv))]
    elif sub == "clean":
        if "n" in letters or flags & {"--dry-run"} or not ("f" in letters or flags & {"--force"}):
            return []
        keep = [a for a in rest if a not in ("-f", "--force", "-i", "--interactive")]
        out = [Spec(MASS_DELETE, "git clean " + " ".join(rest), "git-clean", category="git",
                    git=(override, ["clean", "-n"] + keep))]
    elif sub == "rm":
        if flags & {"--cached"} or "n" in letters or flags & {"--dry-run"}:
            return []
        pathspec = paths or [a for a in rest if not a.startswith("-")]
        out = [Spec(MASS_DELETE, "git rm " + " ".join(rest), "git-files", category="git",
                    git=(override, ["ls-files", "--"] + pathspec))]
    elif sub == "commit":
        if flags & {"--dry-run"}:
            return []
        every = "a" in letters or "--all" in flags
        argv = ["diff", "--name-status", "-M"] + ([] if every else ["--cached"])
        argv += (["HEAD"] if every else []) + ["--"]
        out = _diff_specs("git commit", override, argv)
    elif sub == "push":
        if flags & {"--force", "-f", "--force-with-lease", "--dry-run", "-n", "--delete", "-d"} \
                or any(a.startswith("--force") for a in flags):
            return []
        out = _diff_specs("git push", override, ["diff", "--name-status", "-M", "@BASE@...HEAD",
                                                  "--"])
    if fed:
        for spec in out:
            spec.unknown = True
    if _redirects_repo(args):
        for spec in out:
            spec.unknown = True
            spec.why = ("--git-dir / --work-tree points git at a repository other than the "
                        "working directory's, and that is not read here")
    return out


def _redirects_repo(args):
    """True when git's own options (before the subcommand) move it to another
    repository: `--git-dir[=]`, `--work-tree[=]`. The value of `-c <k=v>`, `-C <path>` and
    the other value-taking options is skipped, not mistaken for the subcommand."""
    index = 0
    while index < len(args) and args[index].startswith("-"):
        name = args[index].split("=", 1)[0]
        if name in ("--git-dir", "--work-tree"):
            return True
        takes_value = (args[index] == "-C" or args[index] in _GIT_VALUE_OPTS)
        index += 2 if takes_value else 1
    return False


def _classify_gh(args):
    words = [a for a in args if not a.startswith("-")]
    if words[:2] == ["pr", "create"] and "--help" not in args and "-h" not in args:
        return _diff_specs("gh pr create", None, ["diff", "--name-status", "-M",
                                                   "@PRBASE@...HEAD", "--"])
    return []


def _classify_terraform(args, fed):
    words = [a for a in args if not a.startswith("-")]
    if not words or words[0] not in ("apply", "destroy"):
        return []
    sub = words[0]
    plan = next((w for w in words[1:] if not w.startswith("-")), None)
    destroy = sub == "destroy" or any(a in ("-destroy", "--destroy") for a in args)
    if sub == "apply" and plan and not destroy and not fed:
        shared = {}
        return [Spec(rule, f"terraform apply {plan}", "tf-plan", operands=[plan],
                     category="terraform", shared=shared) for rule in RULES]
    auto = any(a in ("-auto-approve", "--auto-approve") for a in args)
    if sub == "apply" and not auto and not destroy:
        return []  # interactive: nobody can answer its prompt, and it shows the plan
    rule = MASS_DELETE if destroy else MASS_CHANGE
    return [Spec(rule, f"terraform {sub}" + (" -auto-approve" if auto else ""), "unknown",
                 unknown=True, category="terraform")]


def _classify_sql(payloads):
    """A spec when a SQL text carries a DELETE or UPDATE with no real WHERE."""
    out, seen = [], set()
    for payload in payloads:
        for statement in re.split(r";", payload or ""):
            match = _STATEMENT_RE.search(statement)
            if not match:
                continue
            verb = match.group(1).lower().split()[0]
            rest = match.group(2)
            if verb == "update" and not re.search(r"\bset\b", rest, re.IGNORECASE):
                continue
            where = re.search(r"\bwhere\b", rest, re.IGNORECASE)
            if where and not _TRIVIAL_WHERE_RE.search(statement.strip()):
                continue
            rule = MASS_DELETE if verb == "delete" else MASS_CHANGE
            if rule not in seen:
                seen.add(rule)
                out.append(Spec(rule, f"unfiltered SQL {verb.upper()}", "unknown", unknown=True,
                                category="files"))
    return out


def classify(head, args, shell="bash", fed=False, sql=()):
    """A list of `Spec`s for `head args` (empty when it is not a command this
    module judges). `fed` is True behind `xargs`/`parallel`, which append words
    nobody sees. `sql` is the SQL text(s) a database client was handed."""
    head = head.lower()
    if head == "git":
        return _classify_git(args, fed)
    if head == "gh":
        return _classify_gh(args)
    if head in _TERRAFORMS:
        return _classify_terraform(args, fed)
    if head in _SQL_HEADS:
        return _classify_sql(sql)
    if head in _CMD_RM and any(a.lower() == "/s" for a in args):
        return [Spec(MASS_DELETE, f"{head} /s", "rm", [a for a in args if not a.startswith("/")],
                     recursive=True, unknown=fed)]
    if shell == "powershell" and head in _PS_RM:
        lowered = [a.lower() for a in args]
        recursive = any(a in ("-r", "-recurse") or (a.startswith("-rec") and len(a) <= 8)
                        for a in lowered)
        return [Spec(MASS_DELETE, f"{head} -Recurse" if recursive else head, "rm",
                     _ps_operands(args), recursive=recursive, unknown=fed)]
    if shell == "powershell" and head in _PS_COPY:
        return _copy_specs(head, _ps_copy_operands(args), recursive=_ps_recurse(args), fed=fed)
    if head in _RM_HEADS and shell != "powershell":
        letters, longs, operands = _option_letters(args)
        recursive = bool(letters & {"r", "R"} or "--recursive" in longs)
        return [Spec(MASS_DELETE, "rm -r" if recursive else "rm", "rm", operands,
                     recursive=recursive, unknown=fed)]
    if head == "find" and ("-delete" in args or any(
            a in ("-exec", "-execdir", "-ok", "-okdir") and i + 1 < len(args)
            and args[i + 1].rsplit("/", 1)[-1] in ("rm", "unlink", "rmdir", "shred")
            for i, a in enumerate(args))):
        return [Spec(MASS_DELETE, "find ... -delete", "unknown", unknown=True)]
    if head == "rsync":
        return _rsync_specs(args, fed)
    if head == "sed" or head == "perl" or head.startswith("sed"):
        return _classify_inplace(head, args, fed)
    if head in ("cp", "mv") and shell != "powershell":
        letters, longs, operands = _option_letters(args)
        if letters & {"n"} or "--no-clobber" in longs or len(operands) < 2:
            return []
        recursive = bool(letters & {"r", "R", "a"} or longs & {"--recursive", "--archive"})
        return _copy_specs(head, operands, recursive=recursive or head == "mv", fed=fed)
    if head == "touch":
        _letters, _longs, operands = _option_letters(args)
        return [Spec(MASS_CREATE, "touch", "touch", operands, unknown=fed)] if operands else []
    return []


def _rsync_specs(args, fed):
    letters, longs, operands = _option_letters(args)
    deleting = any(a == "--delete" or a.startswith("--delete-") for a in args)
    if deleting:
        return [Spec(MASS_DELETE, "rsync --delete", "unknown", unknown=True)]
    if len(operands) < 2 or any(":" in o for o in operands):
        return []
    recursive = bool(letters & {"r", "a"} or longs & {"--recursive", "--archive"})
    return _copy_specs("rsync", operands, recursive=recursive, fed=fed)


def _copy_specs(head, operands, recursive, fed):
    if len(operands) < 2:
        return []
    shared = {}
    what = head + (" -r" if recursive else "")
    return [Spec(rule, what, "copy", operands[:-1], recursive=recursive, dest=operands[-1],
                 unknown=fed, shared=shared) for rule in (MASS_CREATE, MASS_CHANGE)]


def _ps_recurse(args):
    return any(a.lower() in ("-r", "-recurse") or (a.lower().startswith("-rec") and len(a) <= 8)
               for a in args)


def _ps_operands(args):
    out, skip = [], False
    for index, arg in enumerate(args):
        if skip:
            skip = False
            continue
        if arg.startswith("-"):
            if arg.lower() in ("-path", "-literalpath", "-lp") and index + 1 < len(args):
                out.append(args[index + 1])
                skip = True
            elif arg.lower() in ("-include", "-exclude", "-filter", "-credential",
                                 "-stream") and index + 1 < len(args):
                skip = True
            continue
        out.append(arg)
    return out


def _ps_copy_operands(args):
    """`[source..., destination]` of a PowerShell copy/move: positional words,
    or `-Path` / `-Destination`."""
    named, positional, skip = {}, [], False
    for index, arg in enumerate(args):
        if skip:
            skip = False
            continue
        low = arg.lower()
        if low in ("-path", "-literalpath", "-lp", "-destination") and index + 1 < len(args):
            named["dest" if low == "-destination" else "src"] = args[index + 1]
            skip = True
        elif arg.startswith("-"):
            if low in ("-include", "-exclude", "-filter", "-credential") and index + 1 < len(args):
                skip = True
        else:
            positional.append(arg)
    src = [named["src"]] if "src" in named else positional[:1]
    rest = positional if "src" in named else positional[1:]
    dest = named.get("dest") or (rest[0] if rest else None)
    return src + [dest] if src and dest else []


def _classify_inplace(head, args, fed):
    if head.startswith("sed"):
        inplace = any(a == "--in-place" or a.startswith("--in-place=") or (
            a.startswith("-") and not a.startswith("--") and "i" in a[1:]) for a in args)
    else:
        inplace = head == "perl" and any(
            a.startswith("-") and not a.startswith("--") and "i" in a[1:] for a in args)
    if not inplace:
        return []
    operands = [a for a in args if not a.startswith("-")]
    scripted = any(a in ("-e", "-f", "--expression", "--file") or a.startswith("-e")
                   for a in args if a.startswith("-"))
    if not scripted and operands:
        operands = operands[1:]  # the first operand is the script
    return [Spec(MASS_CHANGE, f"{head} -i", "inplace", operands, unknown=fed)]


# --- counting -----------------------------------------------------------------------

def _resolve(operand, cwd, cd):
    """`(path, ok)`: `operand` as a path this process can open. Not ok - a
    variable or substitution, a relative path after a `cd`, a POSIX path this
    process cannot map - is "could not tell"."""
    if not isinstance(operand, str) or _DYNAMIC_RE.search(operand):
        return None, False
    if operand.startswith("~"):
        operand = os.path.expanduser(operand)
    if os.name == "nt":
        drive = _DRIVE_RE.match(operand)
        if drive:
            operand = drive.group(1).upper() + ":" + (drive.group(2) or "/")
        elif operand.startswith("/"):
            return None, False
    if os.path.isabs(operand):
        return operand, True
    if cd or not cwd:
        return None, False
    return os.path.join(cwd, operand), True


# --- the one cd this guard follows ---------------------------------------------------
#
# ONE strict grammar over the WHOLE command: `cd <plain path> && git <plain args>` on one
# plain line (PowerShell: `Set-Location|cd|sl <plain path>`, then `;` or `&&`, then git).
# Plain: ASCII only, ASCII space or tab between tokens, and
#   - a bash path of letters digits and `_ . / : -`; a PowerShell path of letters digits
#     `_ . / -` with at most one leading `<letter>:/` or `<letter>:\` drive prefix (no other
#     colon: `Env:`, `Variable:`, `HKLM:` are provider drives, and no other backslash);
#   - git arguments: the subcommand first (no global option, so no `-C`, `-c`, `--git-dir`,
#     `--work-tree`, `--namespace`), then bare words, flags that are letters and dashes only
#     (`-m`, `-a`, `--amend`; a flag with a glued value or a path is refused, and so are
#     `-C`/`-c`/`--git-dir`... anywhere), or quoted strings that hold no `$`, backtick,
#     backslash, `;`, newline or non-ASCII.
# A target with a `..` component is never followed: bash may take `..` through a symlink
# (a logical `cd ..`, or `set -P` from BASH_ENV) and this process would cut the text. A drive
# prefix (`c:/x`) is followed only where drives exist (os.name == "nt").
# Anything else after a cd (a second command, pipe, redirect, expansion, heredoc, assignment,
# alias, NBSP...) does not match and stays "could not tell", exactly as on main. A tripwire,
# not a sandbox: it decides only that the one git command runs in the cd's directory.
#
# LINEAR by construction (round 5): the old pattern put the arguments in one nested
# quantifier, `(?:WORD+|'..'|".."|[ \t])+`, which backtracks exponentially on a command that
# fails near its end (18 s through the real hook). The two prefix patterns below hold no
# nested quantifier and no overlapping alternation; the tail is read once, left to right, by
# `_plain_tail`.
_QCHARS = frozenset(chr(c) for c in range(0x20, 0x7f) if chr(c) not in "$`\\;")
_BASH_WORD_RE = re.compile(r"[A-Za-z0-9_\-./=:@,+%]+")
_PS_WORD_RE = re.compile(r"[A-Za-z0-9_\-./=:,+%]+")
_FLAG_RE = re.compile(r"--?[A-Za-z][A-Za-z-]*")
_WINDOWS = os.name == "nt"
_DRIVE_PREFIX_RE = re.compile(r"[A-Za-z]:")
_GIT_REDIRECT_FLAGS = frozenset((
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env",
    "--attr-source", "--super-prefix"))
_BASH_CD_RE = re.compile(
    r"[ \t]*cd[ \t]+(?P<path>(?!-)[A-Za-z0-9_./:-]+)[ \t]*&&[ \t]*git[ \t]+")
_PS_CD_RE = re.compile(
    r"[ \t]*(?:set-location|cd|sl)[ \t]+"
    r"(?P<path>(?!-)(?:[A-Za-z]:[/\\][A-Za-z0-9_./-]*|[A-Za-z0-9_./-]+))"
    r"[ \t]*(?:&&|;)[ \t]*git[ \t]+", re.IGNORECASE)


def _plain_tail(tail, word_re):
    """True when `tail` (what follows `git `) is plain git arguments (see above). One
    left-to-right pass: every character is looked at once, so the time is linear."""
    size, index, first = len(tail), 0, True
    while index < size:
        char = tail[index]
        if char in " \t":
            index += 1
            continue
        if char in "'\"":
            end = tail.find(char, index + 1)
            if first or end < 0 or not _QCHARS.issuperset(tail[index + 1:end]):
                return False
            index = end + 1
            if index < size and tail[index] not in " \t":
                return False
            first = False
            continue
        end = index
        while end < size and tail[end] not in " \t":
            end += 1
        word = tail[index:end]
        if not word_re.fullmatch(word):
            return False
        if word.startswith("-") and (first or word in _GIT_REDIRECT_FLAGS
                                     or not _FLAG_RE.fullmatch(word)):
            return False
        first, index = False, end
    return not first


def _per_process_dir(target):
    """True for a cd target under `/proc/` or `/dev/` (`/proc/self/cwd`, `/dev/fd/3`): the
    kernel resolves it per PROCESS, so it names the shell's directory when the shell reads it
    and this hook's own directory when the hook does. Never followed."""
    text = target.rstrip("/")
    return text in ("/proc", "/dev") or text.startswith(("/proc/", "/dev/"))


def _cdpath_may_apply(target):
    """True when bash's `cd <target>` could resolve through CDPATH: a bare relative name
    (not `.`, `..`, `./x`, `../x`, or absolute). CDPATH is not read from this process: bash
    may take it from BASH_ENV or a profile, unexported, so every bare name is refused."""
    if target in (".", "..") or target.startswith(("/", "./", "../")):
        return False
    return not (os.path.isabs(target) or _DRIVE_RE.match(target))


def leading_cd(command, cwd, shell="bash"):
    """The directory `command` runs git in when it is exactly one plain
    `cd <path> && git <args>` line (see above) and the path is an existing
    directory, else None ("could not tell")."""
    powershell = shell == "powershell"
    text = command or ""
    match = (_PS_CD_RE if powershell else _BASH_CD_RE).match(text)
    if not match or not cwd:
        return None
    if not _plain_tail(text[match.end():], _PS_WORD_RE if powershell else _BASH_WORD_RE):
        return None
    target = match.group("path")
    if ".." in re.split(r"[/\\]", target):
        return None  # bash may walk a symlink for `..`; this process would cut the text
    if powershell and not _WINDOWS and _DRIVE_PREFIX_RE.match(target):
        return None  # `c:` is no drive here: Set-Location fails and `;` still runs git
    if _per_process_dir(target):
        return None
    if powershell and _WINDOWS and _DRIVE_RE.match(target):
        return None  # PowerShell reads `/c/x` against the CURRENT drive (D:\c\x), not C:\x
    if not powershell and _cdpath_may_apply(target):
        return None
    path, ok = _resolve(target, cwd, False)
    if not ok or not os.path.isdir(path):
        return None
    return os.path.normpath(path)


# --- a GIT_* location variable set in the command -----------------------------------
#
# Only a REAL assignment counts, judged per statement (round 7):
#   - a `GIT_X=` / `GIT_X+=` word at COMMAND position (the first word of a statement, after
#     any other `NAME=v` words, `time`, `if`, `then`, `sudo`, `{`...), brace-expanded
#     (`GIT_{INDEX_FILE,ZZ}=x`), quotes removed (`"GIT_X=v"`, `$'GIT_X=v'`);
#   - the same words after `export`, `declare`, `typeset`, `readonly`, `local` (a bare
#     `export GIT_DIR` counts), and after `env` (with `-S <string>` read as a command);
#   - the string given to `eval`, `bash|sh|dash|zsh|ksh -c`, `pwsh|powershell -c`, `iex`;
#   - PowerShell: a statement that starts `$env:GIT_X =`, `${env:GIT_X} =`, `$env:GIT_X +=`,
#     `Set-Item|Set-Content|New-Item|Add-Content|Set-ItemProperty ... Env:\GIT_X`, or a call
#     `[Environment]::SetEnvironmentVariable('GIT_X', ...)`.
# NOT an assignment, so allowed as on main: a quoted argument (`git commit -m "GIT_DIR=/x was
# wrong"`), a bare word (`-m GIT_DIR`), `unset GIT_DIR`, `grep -rn GIT_INDEX_FILE .`, a heredoc
# body that holds no running `$(...)`. Known gaps, the same on main: a heredoc or here-string
# fed to a shell, `printf -v`, `read`, a variable that builds the name, `xargs`, `sudo -u`.
# One left-to-right pass; a `$(...)` or backtick inside a double-quoted string or an
# unquoted heredoc body runs, so it is scanned as a command too, to a nesting of 3 (deeper is
# reported as a location variable: "could not tell"). No nested quantifier anywhere.
_GIT_NAMES = (r"GIT_(?:DIR|WORK_TREE|INDEX_FILE|OBJECT_DIRECTORY|ALTERNATE_OBJECT_DIRECTORIES|"
              r"COMMON_DIR|CEILING_DIRECTORIES|NAMESPACE)")
_GIT_ASSIGN_RE = re.compile(_GIT_NAMES + r"\+?=", re.IGNORECASE)
_GIT_EXPORT_RE = re.compile(_GIT_NAMES + r"(?:\+?=|\Z)", re.IGNORECASE)
_GIT_SETENV_RE = re.compile(_GIT_NAMES + r"(?:,|\Z)", re.IGNORECASE)
_PS_VAR_RE = re.compile(r"\$\{?env:" + _GIT_NAMES + r"\}?(?P<tail>.*)\Z",
                        re.IGNORECASE | re.DOTALL)
_PS_ENVPATH_RE = re.compile(r"(?:\A|[:=])env:[\\/]?" + _GIT_NAMES + r"\Z", re.IGNORECASE)
_ASSIGN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
_SHELL_BREAK = frozenset(" \t\r\n;|&()<>`")
_STMT_BREAK = frozenset("\r\n;|&()`")
_KEYWORDS = frozenset(("time", "!", "if", "then", "elif", "else", "while", "until", "do", "{",
                       "nohup", "exec", "command", "builtin", "sudo", "nice", "setsid"))
_EXPORTERS = frozenset(("export", "declare", "typeset", "readonly", "local"))
_SHELLS = frozenset(("bash", "sh", "dash", "zsh", "ksh", "ash"))
_PS_SHELLS = frozenset(("pwsh", "powershell"))
_PS_SETTERS = frozenset(("set-item", "si", "set-content", "sc", "new-item", "ni",
                         "add-content", "ac", "set-itemproperty", "sp", "new-itemproperty"))
_MAX_NEST = 3


def _braces(word):
    """The words bash brace expansion makes of `word` (`GIT_{A,B}=x`): up to 6 groups, 64
    results; a longer word is left as it is (a GIT_ name is short)."""
    if "{" not in word or len(word) > 200:
        return [word]
    found = [word]
    for _ in range(6):
        grown, changed = [], False
        for item in found:
            start = item.find("{")
            end = item.find("}", start) if start >= 0 else -1
            if end > start and "," in item[start:end]:
                changed = True
                grown.extend(item[:start] + alt + item[end + 1:]
                             for alt in item[start + 1:end].split(","))
            else:
                grown.append(item)
        found = grown[:64]
        if not changed:
            break
    return found


def _name_hit(word, pattern):
    return any(pattern.match(item) for item in _braces(word))


def _cmd_name(word):
    name = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _script_after(rest, is_flag):
    """The word after the first flag (by `is_flag`) in `rest`, else None."""
    for pos, word in enumerate(rest):
        if is_flag(word):
            return rest[pos + 1] if pos + 1 < len(rest) else None
    return None


def _is_bash_c(word):
    return (word.startswith("-") and not word.startswith("--") and "c" in word[1:]
            and word[1:].isalpha())


def _env_prefix(words, pos, shell, depth):
    """Read `env` options and `NAME=v` words from `pos`. `(True, _)` when one is a GIT_
    assignment (or an `-S` string that is); else `(False, index of the utility)`."""
    size = len(words)
    while pos < size:
        arg = words[pos]
        script = None
        if arg in ("-u", "--unset", "-C", "--chdir"):
            pos += 2
            continue
        if arg in ("-S", "--split-string"):
            script = words[pos + 1] if pos + 1 < size else ""
        elif arg.startswith("--split-string="):
            script = arg.split("=", 1)[1]
        elif arg.startswith("-S") and len(arg) > 2:
            script = arg[2:]
        if script is not None:
            return depth >= _MAX_NEST or sets_git_location(script, shell, depth + 1), pos
        if arg.startswith("-") or _ASSIGN_RE.match(arg):
            if _name_hit(arg, _GIT_ASSIGN_RE):
                return True, pos
            pos += 1
        elif _name_hit(arg, _GIT_ASSIGN_RE):
            return True, pos
        else:
            break
    return False, pos


def _statement_sets(words, shell, depth, after_setenv):
    """True when one statement (its words, quotes removed) assigns a GIT_ location variable."""
    powershell = shell == "powershell"
    size = len(words)
    if after_setenv and _GIT_SETENV_RE.match(words[0]):
        return True
    pos = 0
    while pos < size:
        word = words[pos]
        if powershell:
            match = _PS_VAR_RE.match(word)
            if match:
                tail = match.group("tail")
                if not tail and pos + 1 < size:
                    tail = words[pos + 1]
                if tail.startswith(("=", "+=")):
                    return True
        elif _name_hit(word, _GIT_ASSIGN_RE):
            return True
        elif _ASSIGN_RE.match(word):
            pos += 1
            continue
        name = _cmd_name(word)
        if name in _KEYWORDS:
            pos += 1
            continue
        if name == "env":
            found, pos = _env_prefix(words, pos + 1, shell, depth)
            if found:
                return True
            continue
        break
    if pos >= size:
        return False
    name, rest = _cmd_name(words[pos]), words[pos + 1:]
    script, script_shell = None, shell
    if name in _EXPORTERS and not powershell:
        return any(_name_hit(arg, _GIT_EXPORT_RE) for arg in rest if not arg.startswith("-"))
    if (name == "eval" and not powershell) or name in ("iex", "invoke-expression"):
        script = " ".join(rest)
    elif name in _SHELLS:
        script, script_shell = _script_after(rest, _is_bash_c), "bash"
    elif name in _PS_SHELLS:
        script = _script_after(rest, lambda w: w.lower() in ("-c", "-command"))
        script_shell = "powershell"
    elif powershell and name in _PS_SETTERS:
        return any(_PS_ENVPATH_RE.search(arg) for arg in rest)
    if script:
        return depth >= _MAX_NEST or sets_git_location(script, script_shell, depth + 1)
    return False


def _heredoc_skip(text, index, tags):
    """`(index after the heredoc bodies, [expanding bodies])` for the heredocs `tags`
    (tag, tab-stripped, quoted) whose bodies start after the newline at `index`."""
    expanding, size = [], len(text)
    pos = index + 1
    for tag, dash, quoted in tags:
        start = pos
        while pos < size:
            end = text.find("\n", pos)
            end = size if end < 0 else end
            line = text[pos:end].rstrip("\r")
            pos = min(end + 1, size)
            if (line.lstrip("\t") if dash else line) == tag:
                break
        if not quoted:
            expanding.append(text[start:pos])
    return pos - 1, expanding


def sets_git_location(command, shell="bash", _depth=0):
    """True when `command` assigns a `GIT_DIR`-style variable (see above)."""
    text = command or ""
    powershell = shell == "powershell"
    escape = "`" if powershell else "\\"
    size, index = len(text), 0
    word, stmt, pending = [], [], []
    carry = [False, False]  # [the last statement ended in SetEnvironmentVariable, skip a word]

    def nested(body):
        if "$(" not in body and "`" not in body:
            return False
        return _depth >= _MAX_NEST or sets_git_location(body, shell, _depth + 1)

    def end_word():
        if word:
            joined = "".join(word)
            word.clear()
            if carry[1]:  # the target of a redirect is not an argument
                carry[1] = False
            else:
                stmt.append(joined)

    def end_stmt():
        end_word()
        words = stmt[:]
        stmt.clear()
        carry[1] = False
        if not words:
            return False
        found = _statement_sets(words, shell, _depth, carry[0])
        carry[0] = words[-1].lower().endswith("setenvironmentvariable")
        return found

    while index < size:
        char = text[index]
        if char == escape and index + 1 < size:
            if text[index + 1] != "\n":
                word.append(text[index + 1])
            index += 2
        elif char == "'":
            end = text.find("'", index + 1)
            end = size if end < 0 else end
            word.append(text[index + 1:end])
            index = end + 1
        elif char == "$" and not powershell and text.startswith("$'", index):
            end = index + 2
            while end < size and text[end] != "'":
                end += 2 if text[end] == "\\" else 1
            word.append(text[index + 2:end])
            index = end + 1
        elif char == '"':
            end = index + 1
            while end < size and text[end] != '"':
                end += 2 if text[end] == escape else 1
            body = text[index + 1:end]
            if nested(body):
                return True
            word.append(body)
            index = end + 1
        elif text.startswith("<<", index) and not text.startswith("<<<", index):
            end_word()
            index += 2
            dash = text.startswith("-", index)
            index += dash
            while index < size and text[index] in " \t":
                index += 1
            quote = text[index] if index < size and text[index] in "'\"" else ""
            end = text.find(quote, index + 1) if quote else index
            if quote:
                end = size if end < 0 else end
                tag, index = text[index + 1:end], end + 1
            else:
                while end < size and text[end] not in _SHELL_BREAK:
                    end += 1
                tag, index = text[index:end], end
            pending.append((tag, dash, bool(quote)))
        elif char in "<>":
            if "".join(word).isdigit():
                word.clear()  # the `2` of `2>file`
            else:
                end_word()
            carry[1] = True
            index += 1
            if char == ">" and text.startswith("&", index):
                index += 1
        elif char in _SHELL_BREAK:
            if char in _STMT_BREAK:
                if end_stmt():
                    return True
            else:
                end_word()
            if char == "\n" and pending:
                index, bodies = _heredoc_skip(text, index, pending)
                pending = []
                if any(nested(body) for body in bodies):
                    return True
            index += 1
        else:
            word.append(char)
            index += 1
    return end_stmt()


def _exempt_at(path, cwd, globs=()):
    """`exempt` for an absolute `path`, judged by its part below `cwd` when it
    is inside it: a repo that itself sits under a `build` or `worktrees`
    directory is still guarded."""
    if cwd:
        try:
            rel = os.path.relpath(path, cwd)
        except ValueError:
            rel = None
        if rel not in (None, ".") and not rel.startswith(".."):
            return exempt(rel, relative=True, globs=globs)
    return exempt(path, globs=globs)


def _walk_files(path, globs=(), cwd=None):
    """Files under `path`, regenerable directories pruned and `globs` (relative
    to `cwd`) honoured."""
    total = []
    for folder, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not exempt(d, relative=True)]
        for name in files:
            full = os.path.join(folder, name)
            if exempt(os.path.relpath(full, path), relative=True):
                continue
            if globs and _exempt_at(full, cwd, globs):
                continue
            total.append(full)
        if len(total) >= MAX_WALK:
            break
    return total


def _expand(path):
    return glob.glob(path, recursive=True) if _GLOB_RE.search(path) else [path]


def count_operands(spec, cwd, cd, globs=()):
    """Files `spec` would delete, create or rewrite, or None for "could not
    tell"."""
    total = 0
    for operand in spec.operands:
        path, ok = _resolve(operand, cwd, cd)
        if not ok:
            return None
        for match in _expand(path):
            if _exempt_at(match, cwd, globs):
                continue
            if spec.kind == "touch":
                total += 0 if os.path.lexists(match) else 1
            elif os.path.isdir(match) and not os.path.islink(match):
                if spec.kind == "rm" and spec.recursive:
                    total += len(_walk_files(match, globs, cwd))
            elif os.path.lexists(match) and spec.kind in ("rm", "inplace"):
                total += 1
    return total


def count_copy(spec, cwd, cd, globs=()):
    """`(new, changed)`: files `cp`/`mv`/`rsync` would add under the destination
    and files already there it would replace."""
    dest, ok = _resolve(spec.dest, cwd, cd)
    if not ok:
        return None
    if _exempt_at(dest, cwd, globs):
        return 0, 0
    new = changed = 0
    for operand in spec.operands:
        path, ok = _resolve(operand, cwd, cd)
        if not ok:
            return None
        for match in _expand(path):
            if not os.path.lexists(match) or _exempt_at(match, cwd, globs):
                continue
            base = os.path.join(dest, os.path.basename(match.rstrip("/\\"))) \
                if os.path.isdir(dest) else dest
            if os.path.isdir(match):
                if not spec.recursive:
                    continue
                for source in _walk_files(match, globs, cwd):
                    target = os.path.normpath(os.path.join(base, os.path.relpath(source, match)))
                    if os.path.lexists(target):
                        changed += 1
                    else:
                        new += 1
            elif os.path.lexists(base):
                changed += 1
            else:
                new += 1
    return new, changed


def _git_lines(spec, cwd, cd, runner):
    """Output lines of the read-only git command behind `spec`, or None. The
    `@BASE@` placeholder is the branch's base (`_base`); `@PRBASE@` (gh pr create) is the same
    without the upstream fallback, because a PR's base is the repository's default branch."""
    override, argv = spec.git
    base = cwd
    if override:
        base, ok = _resolve(override, cwd, cd)
        if not ok:
            spec.why = (f"the directory `{override}` is not a literal path this process can "
                        "open (a variable, a substitution, a POSIX path it cannot map, or "
                        "relative to an earlier cd)")
            return None
    elif cd or not cwd:
        spec.why = ("a cd/pushd/Set-Location in this command moves the shell, so which "
                    "repository it runs in is not known" if cd else
                    "the hook payload names no working directory")
        return None
    run = runner or subprocess.run
    for marker in ("@BASE@...HEAD", "@PRBASE@...HEAD"):
        if marker in argv:
            found = _base(base, run, spec, upstream=marker == "@BASE@...HEAD")
            if found is None:
                return None
            argv = [found + "...HEAD" if a == marker else a for a in argv]
    key = (base, tuple(argv))
    if key in spec.shared:
        return spec.shared[key]
    done, why = _git(run, base, argv)
    lines = None
    if done is None:
        spec.why = why
    else:
        lines = [ln for ln in done.stdout.splitlines() if ln.strip()]
    spec.shared[key] = lines
    return lines


def _git(run, cwd, argv):
    """`(completed, "")` for a git command that exited 0, else `(None, why)`
    with the real reason: git missing, timed out, or its exit code and stderr."""
    label = "git " + " ".join(argv[:2])
    try:
        done = run(["git", "-C", cwd] + list(argv), capture_output=True, text=True,
                   timeout=GIT_TIMEOUT, check=False, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, f"`{label}` timed out after {GIT_TIMEOUT}s"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"`{label}` could not run ({type(exc).__name__}: {exc})"
    if done.returncode != 0:
        err = " ".join((done.stderr or "").split())[:200]
        return None, f"`{label}` exited {done.returncode}" + (f": {err}" if err else "")
    return done, ""


def _base(cwd, run, spec=None, upstream=True):
    """The ref a branch's PR would be measured against: `origin/HEAD`, else
    `origin/main`, else `origin/master`, else the branch's upstream; on that
    branch itself, its upstream. None, with `spec.why` set, when there is none. With
    `upstream=False` (`gh pr create`: the PR base is the repository's default branch, never the
    branch's upstream, which may be a fork's feature branch) only the origin refs count."""
    def one(*argv):
        done, _why = _git(run, cwd, list(argv))
        out = done.stdout.strip() if done is not None else ""
        return out or None

    def fail(why):
        if spec is not None:
            spec.why = why
    head = one("symbolic-ref", "--short", "-q", "HEAD")
    candidates = [one("symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD"),
                  "origin/main", "origin/master"]
    for ref in candidates:
        if ref and one("rev-parse", "--verify", "-q", ref + "^{commit}"):
            if head and ref.split("/", 1)[-1] == head:
                if not upstream:
                    return fail(f"the branch `{head}` is the default branch `{ref}`: a pull "
                                "request from it has no base to measure against")
                return one("rev-parse", "--abbrev-ref", "@{u}") or fail(
                    f"the branch `{head}` is its own base `{ref}` and has no upstream to "
                    "measure against")
            return ref
    if not upstream:
        done, why = _git(run, cwd, ["rev-parse", "--git-dir"])
        if done is None:
            return fail(f"{why}: this is not a git repository, or git cannot read it")
        return fail("no base to measure the pull request against: origin/HEAD, origin/main and "
                    "origin/master are all missing, and the branch's upstream is not the "
                    "repository's default branch")
    tracked = one("rev-parse", "--abbrev-ref", "@{u}")
    if tracked:
        return tracked
    done, why = _git(run, cwd, ["rev-parse", "--git-dir"])
    if done is None:
        return fail(f"{why}: this is not a git repository, or git cannot read it")
    return fail("no base to measure the branch against: origin/HEAD, origin/main, "
                "origin/master and the branch's upstream are all missing")


def count_git(spec, cwd, cd, runner=None, globs=()):
    """The count behind a git-based `spec`, or None."""
    lines = _git_lines(spec, cwd, cd, runner)
    if lines is None:
        return None
    if spec.kind == "git-files":
        return sum(1 for ln in lines if not exempt(ln.strip(), relative=True, globs=globs))
    if spec.kind == "git-clean":
        return _count_clean(lines, spec, cwd, cd, globs)
    total = 0
    for line in lines:
        fields = line.split("\t")
        status, names = fields[0][:1], fields[1:]
        if not names or exempt(names[-1], relative=True, globs=globs):
            continue
        counted = ((status == "D" and spec.rule == MASS_DELETE)
                   or (status == "A" and spec.rule == MASS_CREATE)
                   or (status in "MRCT" and spec.rule == MASS_CHANGE))
        if counted:
            total += 1
    return total


def _count_clean(lines, spec, cwd, cd, globs):
    override = spec.git[0]
    base = cwd
    if override:
        base, _ok = _resolve(override, cwd, cd)
    total = 0
    for line in lines:
        if not line.startswith("Would remove "):
            continue
        name = line[len("Would remove "):].strip()
        if exempt(name, relative=True, globs=globs):
            continue
        full = os.path.join(base or "", name)
        total += len(_walk_files(full, globs, base)) if name.endswith("/") and os.path.isdir(full) else 1
    return total


def count_terraform(spec, cwd, cd, runner=None):
    """Resource changes in the plan file `spec` applies, or None."""
    plan, ok = _resolve(spec.operands[0], cwd, cd)
    if not ok:
        return None
    if "plan" not in spec.shared:
        run = runner or subprocess.run
        head = "terraform"
        try:
            done = run([head, "show", "-json", plan], capture_output=True, text=True,
                       timeout=TF_TIMEOUT, check=False, stdin=subprocess.DEVNULL,
                       cwd=os.path.dirname(plan) or cwd)
            data = json.loads(done.stdout) if done.returncode == 0 else None
            changes = data.get("resource_changes") if isinstance(data, dict) else None
            spec.shared["plan"] = changes if isinstance(changes, list) else None
        except (OSError, subprocess.SubprocessError, ValueError):
            spec.shared["plan"] = None
    changes = spec.shared["plan"]
    if changes is None:
        return None
    want = {MASS_DELETE: "delete", MASS_CREATE: "create", MASS_CHANGE: "update"}[spec.rule]
    return sum(1 for change in changes if isinstance(change, dict) and want in
               (change.get("change") or {}).get("actions", []))


def count(spec, cwd, cd, runner=None, globs=()):
    """Files `spec` would touch, or None for "could not tell" (`spec.why` then
    says which of the ways it could not)."""
    if spec.unknown:
        spec.why = spec.why or ("its list is built at run time (xargs, find -delete, rsync "
                                "--delete, an unfiltered SQL statement or a terraform apply "
                                "with no plan file), so no count exists to read")
        return None
    if spec.kind == "tf-plan":
        found = count_terraform(spec, cwd, cd, runner)
    elif spec.git:
        found = count_git(spec, cwd, cd, runner, globs)
    elif spec.kind == "copy":
        pair = count_copy(spec, cwd, cd, globs)
        found = None if pair is None else pair[0 if spec.rule == MASS_CREATE else 1]
    else:
        found = count_operands(spec, cwd, cd, globs)
    if found is None and not spec.why:
        spec.why = ("a path in it is not a literal this process can open (a variable or "
                    "substitution, a POSIX path it cannot map, or a path relative to an "
                    "earlier cd), or the terraform plan could not be read")
    return found


# --- the verdict --------------------------------------------------------------------

def approval_id(text, toplevel):
    """The 12 hex digits `/crew:approve-mass` takes: binds the exact command
    text and the worktree (one id covers every rule the command trips)."""
    raw = "\0".join(("crew-mass/2", text, os.path.normcase(toplevel or "")))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def approval_path(state_dir, mass_id):
    return os.path.join(state_dir, APPROVAL_DIR, mass_id + ".json")


def live_approval(state_dir, mass_id, now=None):
    """True when the user's `/crew:approve-mass <mass_id>` is recorded and
    within MASS_APPROVAL_TTL. Anything unreadable, forged in shape, expired or
    dated in the future is not an approval."""
    if not state_dir or not _ID_RE.match(mass_id or ""):
        return False
    now = time.time() if now is None else now
    try:
        with open(approval_path(state_dir, mass_id), encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError):
        return False
    if not isinstance(record, dict) or record.get("id") != mass_id \
            or record.get("approved_via") != "user-prompt":
        return False
    stamp, expires = record.get("approved_at"), record.get("expires")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (stamp, expires)):
        return False
    return stamp <= now + 60 and now <= min(expires, stamp + MASS_APPROVAL_TTL)


def tampers(command):
    """True when a shell command names the approvals directory beside a word
    that writes: the session reaching for the owner's yes."""
    return isinstance(command, str) and APPROVAL_DIR in command and bool(
        _WRITES_RE.search(command))


def repo_paths(cwd, runner=None):
    """`(toplevel, <git-common-dir>/crew)` for `cwd`, or `(None, None)` outside
    git or when git cannot tell. Called only once a command is already mass."""
    top, state_dir, _why = repo_paths_why(cwd, runner)
    return top, state_dir


def repo_paths_why(cwd, runner=None):
    """`repo_paths` plus the reason: `(toplevel, state_dir, "")` or
    `(None, None, "git rev-parse failed: ...")`."""
    done, why = _git(runner or subprocess.run, cwd or ".",
                     ["rev-parse", "--show-toplevel", "--git-common-dir"])
    if done is None:
        return None, None, "git rev-parse failed: " + why
    lines = done.stdout.splitlines()
    if len(lines) != 2 or not all(ln.strip() for ln in lines):
        return None, None, ("git rev-parse failed: expected a toplevel and a common dir, got "
                            f"{len(lines)} line(s)")
    top, common = lines[0].strip(), lines[1].strip()
    if not os.path.isabs(common):
        common = os.path.join(cwd or ".", common)
    return os.path.realpath(top), os.path.join(os.path.realpath(common), "crew"), ""


def judge(spec, text, cwd, cd, alone, config=None, runner=None, now=None, repo=None):
    """`None` when the command is not mass; `("allow", "", policy)` when it is
    and the user approved it; else `(decision, reason, policy)` with decision
    `ask` (attended) or `deny` (unattended). `config` is `settings(...)`;
    `repo` is `(toplevel, state_dir)`, looked up only when needed."""
    config = config or settings(cwd or ".")
    key = COUNT_KEY[spec.rule]
    limit = config["limits"][spec.category][key]
    touched = count(spec, cwd, cd, runner, config["exempt"])
    if touched is not None and touched < limit:
        return None
    repo_why = ""
    if repo is not None:
        toplevel, state_dir = repo
    else:
        toplevel, state_dir, repo_why = repo_paths_why(cwd, runner)
    mass_id = approval_id(text, toplevel)
    shown = (f"could not be counted ({spec.why})" if touched is None
             else f"is {touched} files")
    policy = f"mass:{spec.rule}:{'unknown' if touched is None else touched}"
    if live_approval(state_dir, mass_id, now):
        return "allow", "", policy + ":approved"
    verb = {MASS_DELETE: "delete", MASS_CREATE: "create", MASS_CHANGE: "change"}[spec.rule]
    shown_text = text if len(text) <= 300 else text[:300] + "..."
    reason = (f"[{spec.rule}] `{spec.what}` would {verb} a mass of files: the count {shown} "
              f"(the stop is at {limit}, guards.mass.{key}). To approve THIS command once, "
              f"type `/crew:approve-mass {mass_id}` yourself in this session, then re-run it "
              f"(good for {MASS_APPROVAL_TTL // 60} minutes). Command: {shown_text}")
    if repo_why:
        reason += f" -- note: no approval can be recorded for it here ({repo_why})"
    if alone:
        reason += " -- nobody is attending to answer, so it is refused."
        return "deny", reason, policy
    return "ask", reason, policy
