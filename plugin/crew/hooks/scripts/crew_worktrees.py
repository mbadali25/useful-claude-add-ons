"""One standard place for git worktrees, outside the repo (crew 1.3.19).

    python3 crew_worktrees.py root          [--root .]            print the repo's worktree directory
    python3 crew_worktrees.py path <branch> [--root .]            print where a worktree for <branch> goes
    python3 crew_worktrees.py list          [--root .] [--days N] [--json]   classify every worktree (read-only)
    python3 crew_worktrees.py remove <path> --yes [--root .]      remove ONE removable worktree
    python3 crew_worktrees.py hook-snippet                        print the settings.json block that registers the hook
    python3 crew_worktrees.py hook-create | hook-remove           the hook entry points (JSON on stdin)

`worktrees.root` (repo or machine layer, repo wins) names the BASE directory;
null means `~/.claude/crew/worktrees`. A repo's worktrees live in
`<base>/<repo>-<digest>/<name>`: the digest of the main checkout's real path
keeps two repos called `myrepo` apart.

What this controls, and what it does not. Claude Code places its own worktrees
(`claude --worktree`, an Agent with `isolation: worktree`, `EnterWorktree`)
under `<repo>/.claude/worktrees/` and has no setting for another place: its
only location key, `worktree.location`, is for Desktop SSH sessions. The one
supported redirect is a `WorktreeCreate` hook, which REPLACES git's creation
(the hook must create the worktree and print its path) - so it is opt-in:
`hook-snippet` prints the block for the owner's settings.json and nothing here
registers it. `WorktreeRemove` does not fire for subagent or workflow
worktrees, which is why `list` exists.

`list` and `remove` never guess. A probe that fails is `could not tell` and
keeps the worktree off the removable list; `remove` needs `--yes` (the owner's
word, asked for by `/crew:worktrees`), takes one path, runs `git worktree
remove` WITHOUT `--force`, and refuses the main checkout, the checkout it runs
in, a locked or unreachable one, and any with uncommitted work, untracked
files, or commits no remote has.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crew_state  # noqa: E402  pylint: disable=wrong-import-position

DEFAULT_BASE = os.path.join("~", ".claude", "crew", "worktrees")
STALE_DAYS = 14
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
BRANCH_PREFIX = "worktree-"

# `where` values
STANDARD, IN_REPO, ELSEWHERE, UNREACHABLE = "standard", "in-repo", "elsewhere", "unreachable"
UNKNOWN = "could not tell"


class WorktreeRootError(ValueError):
    """The configured root cannot be used; the message says why and what to do."""


def _git(cwd, *args, timeout=60):
    """(returncode, stdout, stderr); returncode None when git could not run."""
    try:
        done = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True,
                              check=False, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "", f"{type(exc).__name__}: {exc}"
    return done.returncode, done.stdout, done.stderr.strip()


def _norm(path):
    return os.path.normcase(os.path.realpath(path))


def _inside(path, parent):
    path, parent = _norm(path), _norm(parent)
    return path == parent or path.startswith(parent.rstrip(os.sep) + os.sep)


def records(cwd):
    """[{path, branch, head, locked, prunable}] from `git worktree list
    --porcelain` (the first is the main checkout), or None when git could not
    answer."""
    code, out, _ = _git(cwd, "worktree", "list", "--porcelain")
    if code != 0:
        return None
    found, cur = [], None
    for line in out.splitlines():
        if line.startswith("worktree "):
            cur = {"path": line[len("worktree "):], "branch": "", "head": "",
                   "locked": False, "prunable": False, "bare": False}
            found.append(cur)
        elif cur is None:
            continue
        elif line.startswith("branch refs/heads/"):
            cur["branch"] = line[len("branch refs/heads/"):]
        elif line.startswith("HEAD "):
            cur["head"] = line[5:]
        elif line.startswith("locked"):
            cur["locked"] = True
        elif line.startswith("prunable"):
            cur["prunable"] = True
        elif line == "bare":
            cur["bare"] = True
    return found


def main_checkout(root):
    """(main checkout path, problem): the first `git worktree list` record, or
    `root` itself when it is not a git repository's worktree (problem set)."""
    found = records(root)
    if not found:
        return os.path.abspath(root), "git could not name the main checkout"
    return found[0]["path"], ""


def configured_base(root):
    """The raw `worktrees.root` value of the effective config, or None."""
    try:
        import crew_config  # pylint: disable=import-outside-toplevel
        value = (crew_config.resolve_config(root).get("worktrees") or {}).get("root")
    except Exception:  # pylint: disable=broad-except
        return None
    return value


def resolve(root):
    """{base, dir, main, source, problem}: where this repo's worktrees go.

    `problem` is non-empty when the configured value cannot be used: it is
    never replaced by the default, so a typo is a refusal and not a second
    location. `dir` is None then."""
    main, name_problem = main_checkout(root)
    raw = configured_base(root)
    source = "default" if raw is None else "config"
    out = {"base": None, "dir": None, "main": main, "source": source, "problem": ""}
    if raw is not None and (not isinstance(raw, str) or not raw.strip()):
        out["problem"] = (f"worktrees.root = {raw!r} is not a path (a non-empty string) or null; "
                          "fix it with /crew:config worktrees.root <absolute path>")
        return out
    base = os.path.expanduser((raw or DEFAULT_BASE).strip())
    if not os.path.isabs(base):
        out["problem"] = (f"worktrees.root = {raw!r} is not an absolute path (a leading ~ is "
                          "expanded; environment variables and relative paths are not)")
        return out
    base = os.path.normpath(base)
    out["base"] = base
    if _inside(base, main):
        out["problem"] = (f"worktrees.root = {base} is inside the repo ({main}); the point of the "
                          "setting is a place outside it")
        return out
    if name_problem:
        out["problem"] = name_problem
        return out
    leaf = re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.basename(main.rstrip("/\\")) or "repo").strip("-.") or "repo"
    out["dir"] = os.path.join(base, f"{leaf}-{crew_state._repo_digest(main)}")  # pylint: disable=protected-access
    return out


def repo_dir(root):
    """The directory this repo's worktrees go in; raises WorktreeRootError."""
    got = resolve(root)
    if got["problem"]:
        raise WorktreeRootError(got["problem"])
    return got["dir"]


def branch_leaf(branch):
    """One directory level for `branch`: separators and `:` become `-`."""
    return crew_state.branch_leaf(branch)


def worktree_path(root, branch):
    return os.path.join(repo_dir(root), branch_leaf(branch))


# --- classification (read-only) -------------------------------------------------------------

def _where(path, main, std_dir):
    if not os.path.isdir(path):
        return UNREACHABLE
    if std_dir and _inside(path, std_dir):
        return STANDARD
    if _inside(path, main):
        return IN_REPO
    return ELSEWHERE


def _default_ref(main):
    """origin's default branch as a ref, or None."""
    code, out, _ = _git(main, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")
    if code == 0 and out.strip():
        return out.strip()
    for ref in ("refs/remotes/origin/main", "refs/remotes/origin/master"):
        if _git(main, "rev-parse", "-q", "--verify", ref)[0] == 0:
            return ref
    return None


def classify(rec, main, std_dir, default_ref, days=STALE_DAYS, now=None):
    """One worktree's facts. Every probe that fails is UNKNOWN, never clean."""
    path = rec["path"]
    row = {"path": path, "branch": rec["branch"], "where": _where(path, main, std_dir),
           "main": _norm(path) == _norm(main), "locked": rec["locked"], "dirty": UNKNOWN,
           "unpushed": UNKNOWN, "merged": UNKNOWN, "age_days": None, "removable": False,
           "why": []}
    if row["main"]:
        row["where"] = "main"
        row["why"].append("the main checkout")
        return row
    if row["where"] == UNREACHABLE:
        row["why"].append("path not reachable from this OS" + (" (git marks it prunable)"
                                                              if rec["prunable"] else ""))
        return row
    code, out, _ = _git(path, "status", "--porcelain=v1", "--untracked-files=all")
    if code == 0:
        row["dirty"] = bool(out.strip())
    code, out, _ = _git(path, "rev-list", "--count", "HEAD", "--not", "--remotes")
    if code == 0 and out.strip().isdigit():
        row["unpushed"] = int(out.strip())
    if default_ref:
        code = _git(path, "merge-base", "--is-ancestor", "HEAD", default_ref)[0]
        row["merged"] = True if code == 0 else False if code == 1 else UNKNOWN
    code, out, _ = _git(path, "log", "-1", "--format=%ct")
    if code == 0 and out.strip().isdigit():
        row["age_days"] = int(((now or time.time()) - int(out.strip())) // 86400)
    problems = []
    if row["locked"]:
        problems.append("locked")
    if row["dirty"] is not False:
        problems.append("uncommitted or untracked files" if row["dirty"] else "dirty state " + UNKNOWN)
    if row["unpushed"] != 0:
        problems.append("commits no remote has" if isinstance(row["unpushed"], int)
                        else "unpushed commits " + UNKNOWN)
    if row["merged"] is not True:
        problems.append("branch not merged into the default branch" if row["merged"] is False
                        else "merge state " + UNKNOWN)
    if row["age_days"] is None or row["age_days"] < days:
        problems.append(f"newer than {days} days" if row["age_days"] is not None else "age " + UNKNOWN)
    row["why"] = problems
    row["removable"] = not problems
    return row


def survey(root, days=STALE_DAYS):
    """(rows, problem): every worktree of the repo at `root`, classified."""
    found = records(root)
    if not found:
        return [], "git could not list worktrees"
    main = found[0]["path"]
    got = resolve(root)
    std_dir = got["dir"]
    default_ref = _default_ref(main)
    return [classify(rec, main, std_dir, default_ref, days) for rec in found], got["problem"]


def render(rows, problem, std_dir=None):
    lines = []
    counts = {}
    for row in rows:
        counts[row["where"]] = counts.get(row["where"], 0) + 1
    lines.append("worktrees: " + ", ".join(f"{n} {w}" for w, n in sorted(counts.items())))
    if problem:
        lines.append(f"root: refused - {problem}")
    elif std_dir:
        lines.append(f"root: {std_dir}")
    for row in rows:
        tag = "REMOVABLE" if row["removable"] else "keep"
        why = "; ".join(row["why"]) or "clean, merged, pushed, old enough"
        lines.append(f"{tag:9} {row['where']:11} {row['branch'] or '(detached)':32} {row['path']}  [{why}]")
    n = sum(1 for r in rows if r["removable"])
    lines.append(f"{n} removable. Nothing was changed. To remove one, the owner confirms it by name: "
                 "crew_worktrees.py remove <path> --yes")
    return "\n".join(lines)


# --- remove (owner-confirmed, one path) --------------------------------------------------------

def remove(root, path, yes, days=STALE_DAYS):
    """(ok, message). One worktree, only when `classify` calls it removable."""
    if not yes:
        return False, "refused: removal needs --yes, the owner's confirmation of this one path"
    found = records(root)
    if not found:
        return False, "refused: git could not list worktrees"
    main = found[0]["path"]
    target = next((r for r in found if _norm(r["path"]) == _norm(path)), None)
    if target is None:
        return False, f"refused: {path} is not a worktree of this repository"
    here = _git(os.getcwd(), "rev-parse", "--show-toplevel")[1].strip()
    if here and _norm(here) == _norm(target["path"]):
        return False, "refused: this is the checkout the command runs in"
    row = classify(target, main, resolve(root)["dir"], _default_ref(main), days)
    if row["main"] or not row["removable"]:
        return False, "refused: " + "; ".join(row["why"] or ["not removable"])
    code, _, err = _git(main, "worktree", "remove", target["path"])
    if code != 0:
        return False, f"git worktree remove failed (no --force): {err}"
    note = ""
    if target["branch"] and _git(main, "branch", "-d", target["branch"])[0] == 0:
        note = f"; deleted merged branch {target['branch']}"
    return True, f"removed {target['path']}{note}"


# --- the WorktreeCreate / WorktreeRemove hook ----------------------------------------------------

def _base_ref_setting(main):
    """`worktree.baseRef` from Claude settings (repo local, repo, user): 'head' or 'fresh'."""
    for path in (os.path.join(main, ".claude", "settings.local.json"),
                 os.path.join(main, ".claude", "settings.json"),
                 os.path.join(os.path.expanduser("~"), ".claude", "settings.json")):
        try:
            with open(path, encoding="utf-8") as handle:
                value = (json.load(handle).get("worktree") or {}).get("baseRef")
        except (OSError, ValueError, AttributeError):
            continue
        if value in ("head", "fresh"):
            return value
    return "fresh"


def _worktreeinclude(main, dest):
    """Copy what `.worktreeinclude` names and git ignores (the hook replaces
    Claude Code's own copy step). Returns the count; never raises."""
    listing = os.path.join(main, ".worktreeinclude")
    if not os.path.isfile(listing):
        return 0
    code_a, out_a, _ = _git(main, "ls-files", "-o", "-i", "-z", f"--exclude-from={listing}")
    code_b, out_b, _ = _git(main, "ls-files", "-o", "-i", "-z", "--exclude-standard")
    if code_a != 0 or code_b != 0:
        return 0
    both = set(out_a.split("\0")) & set(out_b.split("\0"))
    copied = 0
    for rel in sorted(p for p in both if p):
        source = os.path.join(main, rel)
        if os.path.islink(source) or not os.path.isfile(source):
            continue
        try:
            os.makedirs(os.path.dirname(os.path.join(dest, rel)), exist_ok=True)
            shutil.copy2(source, os.path.join(dest, rel))
            copied += 1
        except OSError:
            continue
    return copied


def hook_create(payload):
    """(ok, path_or_message). Create `<repo dir>/<name>` as a new worktree on
    `worktree-<name>`; an existing worktree of this repo at that path is reused."""
    cwd = payload.get("cwd") or os.getcwd()
    name = str(payload.get("name") or "")
    if not NAME_RE.match(name) or name.endswith(".") or ".." in name:
        return False, f"refused: worktree name {name!r} is not a plain name"
    try:
        main_dir = repo_dir(cwd)
    except WorktreeRootError as exc:
        return False, f"refused: {exc}"
    main, _ = main_checkout(cwd)
    dest = os.path.join(main_dir, name)
    found = records(main) or []
    if any(_norm(r["path"]) == _norm(dest) for r in found):
        return True, dest
    if os.path.exists(dest):
        return False, f"refused: {dest} exists and is not a worktree of {main}"
    ref = None if _base_ref_setting(main) == "head" else _default_ref(main)
    start = ref or "HEAD"
    branch = BRANCH_PREFIX + name
    os.makedirs(main_dir, exist_ok=True)
    exists = _git(main, "rev-parse", "-q", "--verify", f"refs/heads/{branch}")[0] == 0
    args = ["worktree", "add", dest, branch] if exists else ["worktree", "add", "-b", branch, dest, start]
    code, _, err = _git(main, *args, timeout=300)
    if code != 0:
        return False, f"git {' '.join(args[:2])} failed: {err}"
    _worktreeinclude(main, dest)
    return True, dest


def hook_remove(payload):
    """(ok, message). `git worktree remove` WITHOUT --force on a registered
    linked worktree: git itself refuses uncommitted work. A merged
    `worktree-*` branch is deleted; an unmerged one is left."""
    path = str(payload.get("worktree_path") or "")
    if not path:
        return False, "refused: no worktree_path in the payload"
    found = records(path if os.path.isdir(path) else os.path.dirname(path) or ".")
    if not found:
        return False, f"refused: {path} is not in a git repository crew can read"
    main = found[0]["path"]
    target = next((r for r in found[1:] if _norm(r["path"]) == _norm(path)), None)
    if target is None:
        return False, f"refused: {path} is not a linked worktree"
    code, _, err = _git(main, "worktree", "remove", target["path"])
    if code != 0:
        return False, f"left in place (git refuses, and crew never forces): {err}"
    if target["branch"].startswith(BRANCH_PREFIX):
        _git(main, "branch", "-d", target["branch"])
    return True, f"removed {target['path']}"


def hook_snippet(python=None, script=None):
    """The settings.json block that registers the two hooks (owner pastes it)."""
    python = python or sys.executable or "python3"
    script = script or os.path.abspath(__file__)

    def command(which):
        return f'"{python}" "{script}" {which}'
    return json.dumps({"hooks": {
        "WorktreeCreate": [{"hooks": [{"type": "command", "command": command("hook-create")}]}],
        "WorktreeRemove": [{"hooks": [{"type": "command", "command": command("hook-remove")}]}],
    }}, indent=2)


def hook_state():
    """(state, detail) of the owner's user settings: `registered`, `missing
    script`, `not registered` or `could not tell`."""
    path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return "not registered", path
    except (OSError, ValueError) as exc:
        return UNKNOWN, f"{path}: {exc}"
    names = []
    try:
        for entry in (data.get("hooks") or {}).get("WorktreeCreate") or []:
            for hook in (entry or {}).get("hooks") or []:
                names += re.findall(r'"([^"]*crew_worktrees\.py)"', str((hook or {}).get("command") or ""))
    except AttributeError:
        return UNKNOWN, f"{path}: hooks.WorktreeCreate is not the expected shape"
    if not names:
        return "not registered", path
    if not all(os.path.isfile(n) for n in names):
        return "missing script", "the registered path no longer exists (re-run hook-snippet after a plugin update)"
    return "registered", path


# --- CLI ------------------------------------------------------------------------------------

def _stdin_payload():
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="crew_worktrees.py", description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["root", "path", "list", "remove", "hook-snippet",
                                            "hook-create", "hook-remove", "status"])
    parser.add_argument("target", nargs="?", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--days", type=int, default=STALE_DAYS)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = args.root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    if args.command == "hook-snippet":
        print(hook_snippet())
        return 0
    if args.command in ("hook-create", "hook-remove"):
        ok, message = (hook_create if args.command == "hook-create" else hook_remove)(_stdin_payload())
        if ok:
            print(message)
            return 0
        print(message, file=sys.stderr)
        return 1
    if args.command in ("root", "path"):
        try:
            print(repo_dir(root) if args.command == "root" else worktree_path(root, args.target or "detached"))
        except WorktreeRootError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "remove":
        if not args.target:
            print("refused: name the worktree path to remove", file=sys.stderr)
            return 2
        ok, message = remove(root, args.target, args.yes, args.days)
        print(message, file=None if ok else sys.stderr)
        return 0 if ok else 1
    got = resolve(root)
    if args.command == "status":
        state, detail = hook_state()
        print(f"root: {got['dir'] or 'refused - ' + got['problem']} ({got['source']})")
        print(f"hook: {state} ({detail})")
        return 0
    rows, problem = survey(root, args.days)
    if args.json:
        print(json.dumps({"root": got["dir"], "problem": problem or got["problem"], "worktrees": rows},
                         indent=2, default=str))
    else:
        print(render(rows, problem or got["problem"], got["dir"]))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
