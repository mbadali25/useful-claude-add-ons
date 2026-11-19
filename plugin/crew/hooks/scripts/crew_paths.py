"""Where crew keeps things on this machine, and the one safe recursive delete (R-04).

    python3 crew_paths.py where <kind> [--repo .] [--ticket T] [--role R] [--set S]
                                       [--round N] [--provider P] [--run-id ID] [--json]
    python3 crew_paths.py explain [--repo .] [--json]
    python3 crew_paths.py check-delete <path> --run-id ID [--nonce N] [--json]

Inert library: nothing in crew calls it yet (R-50, R-51, R-52, R-53 and R-60
will). There is no `delete` subcommand; `check-delete` is a dry run that
changes nothing.

LOCATIONS come from the MACHINE layer only (`~/.claude/crew/config.json`).
The crew root is `~/.claude/crew`; the worktree base is the machine layer's
`worktrees.root`, else `<root>/worktrees`. A repo-layer `worktrees.root` is
ignored here and reported by `explain` (`crew_worktrees.py` still honours it
until a later ticket makes it a protected key).

    worktree(repo, ticket)        <wt>/<leaf>-<digest>/dev-<ticket>
    lane(repo, set, ticket)       <wt>/<leaf>-<digest>/lane-<set>-<ticket>
    review(repo, ticket, r, p)    <root>/review/<leaf>-<digest>/<ticket>-r<r>-<p>   (in/, out/)
    scratch(repo, ticket, role)   <root>/scratch/<leaf>-<digest>/<ticket>/<role>
    sandbox(run_id)               <root>/scratch/sandbox/<run-id>                   (in/, home/, out/)
    tests(run_id)                 <root>/scratch/tests/<run-id>, or $CREW_TEST_ROOT/<run-id>

`<leaf>-<digest>` is `crew_worktrees._leaf` and `crew_state._repo_digest` of
the main checkout, the same name the worktree directory uses.

DELETION. `delete_run_dir(path, run_id)` removes one run folder that
`make_run_dir` created and nothing else. It never raises and never calls
`shutil.rmtree`. In order, each refusal changing nothing:

  1. string checks on the normalised path and again on its realpath: not
     empty, relative or NUL; not a filesystem, drive or share root, the home,
     the crew root, the worktree base, a category root or a `<leaf>-<digest>`
     folder; not a system path; strictly inside `<root>/scratch`,
     `<root>/review` or an accepted `$CREW_TEST_ROOT`; and exactly the shape
     of one kind's run folder (the table above).
  2. a link walk anchored at the resolved allowed root: the realpath must be
     the allowed root's realpath plus the same components, and no component
     below the allowed root may be a link, a reparse point or a non-directory.
  3. the ownership record `.crew-owner.json`: a regular file with one link,
     opened without following links and matched to its `lstat`, whose
     `v`, `run_id`, `kind`, `path` (and `nonce`, when given) agree.
  4. the run folder's identity is captured (POSIX: an `O_NOFOLLOW` fd).
  5. a read-only pre-scan refuses a mount inside the run (Linux mountinfo,
     `st_dev`, a Windows junction or mount point whose target is a volume
     root) and anything it cannot list; then the walk deletes.

The walk never follows a link: a symlink or junction ENTRY inside the run is
removed as a link and its target is never opened or changed. Deliberate
departure from plan 4.6: links inside a run dir are removed, not refused; why:
removing a link never touches its target, and refusing would make any run dir
that held a link undeletable. A read-only tree is handled (POSIX: `fchmod`
through a verified fd, never `chmod` by path; Windows: the READONLY flag is
cleared through a verified handle). A Windows read-only file with more than
one link may have a name outside the run, so its flag is never cleared: that
one name is deleted through the handle with POSIX-semantics, ignore-readonly
disposition, or the delete is refused.

Known limits, not closed here: Windows has no `dir_fd`, so its walk re-checks
identity and reparse attributes before each step, which narrows a swap race
but does not close it. A same-device bind mount made after the pre-scan is not
seen by the walk's `st_dev` re-check. macOS has no mountinfo, only `st_dev`.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime
import json
import os
import re
import secrets
import socket
import stat
import sys

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crew_config  # noqa: E402  pylint: disable=wrong-import-position
import crew_state  # noqa: E402  pylint: disable=wrong-import-position
import crew_worktrees  # noqa: E402  pylint: disable=wrong-import-position

OWNER = ".crew-owner.json"
RECORD_MAX = 64 * 1024
KINDS = ("scratch", "review", "sandbox", "tests")
SUBDIRS = {"scratch": (), "review": ("in", "out"), "sandbox": ("in", "home", "out"), "tests": ()}
TEST_ROOT_ENV = "CREW_TEST_ROOT"

# A `<leaf>-<digest>` folder: the leaf alphabet, then `-` and six hex digits.
_KEY_RE = re.compile(r"^[A-Za-z0-9._-]+-[0-9a-f]{6}$", re.IGNORECASE)
_VOLUME_RE = re.compile(r"^\\\\\?\\Volume\{[0-9A-Fa-f-]+\}\\?$")

_REPARSE = stat.FILE_ATTRIBUTE_REPARSE_POINT
_READONLY = stat.FILE_ATTRIBUTE_READONLY
_DIRECTORY = stat.FILE_ATTRIBUTE_DIRECTORY
_TAG_SYMLINK = 0xA000000C
_TAG_MOUNT = 0xA0000003
# POSIX open flags; only the POSIX code paths use them, where all three exist.
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)

# System paths. EXACT: the path itself is refused, children are judged by the
# other rules (a root user's home is /root; macOS tmp lives under /var).
# UNDER: the path and everything below it are refused.
_POSIX_EXACT = ("/root", "/home", "/tmp", "/var", "/opt", "/srv")
_POSIX_UNDER = ("/bin", "/sbin", "/usr", "/etc", "/lib", "/lib64", "/boot", "/dev", "/proc", "/sys", "/run", "/var/run")


class PathsError(ValueError):
    """A location cannot be resolved; the message names the rule."""


# ---------------------------------------------------------------- seams
# Module-level so a test can replace one with monkeypatch. Production code
# calls them by name.

def _lstat(path):
    return os.lstat(path)


def _readlink(path):
    return os.readlink(path)


def _is_linux():
    return sys.platform.startswith("linux")


def _read_mountinfo():
    with open("/proc/self/mountinfo", encoding="utf-8", errors="surrogateescape") as handle:
        return handle.read()


def _child_dev(st, path, phase):  # pylint: disable=unused-argument
    """The device a directory is on; `phase` is "scan" or "walk"."""
    return st.st_dev


def _after_record_lstat(record):  # pylint: disable=unused-argument
    return None


def _after_owner_check(path):  # pylint: disable=unused-argument
    return None


def _before_attr_clear(path):  # pylint: disable=unused-argument
    return None


# ---------------------------------------------------------------- string helpers

def _attrs(st):
    return getattr(st, "st_file_attributes", 0) or 0


def _n(fl, path):
    return fl.normcase(fl.normpath(path))


def _inside(fl, path, parent):
    """`path` equals `parent` or is below it (both already `_n`-normalised)."""
    return path == parent or path.startswith(parent.rstrip(fl.sep) + fl.sep)


def _strictly_inside(fl, path, parent):
    return path != parent and _inside(fl, path, parent)


def _is_fs_root(fl, path):
    drive, rest = fl.splitdrive(path)
    return rest in ("", fl.sep, "/") or (not drive and path == fl.sep)


def _expand(fl, raw, home):
    if raw == "~" or raw.startswith("~/") or raw.startswith("~" + fl.sep):
        return home + raw[1:]
    return raw


def component_problem(value):
    """Why `value` cannot be one path component, or ""."""
    if not isinstance(value, str) or not crew_worktrees.NAME_RE.match(value):
        return f"{value!r} is not a plain name (letters, digits, . _ -, at most 128, not leading . or -)"
    if value in (".", "..") or ".." in value:
        return f"{value!r} contains '..'"
    return ""


def _component(value):
    problem = component_problem(value)
    if problem:
        raise PathsError(problem)
    return value


def system_path_problem(path, flavour=None, env=None):
    """Why `path` (absolute, in `flavour`) is a system path, or ""."""
    fl = flavour or os.path
    env = os.environ if env is None else env
    p = _n(fl, path)
    if fl.sep == "/":
        exact, under = _POSIX_EXACT, _POSIX_UNDER
    else:
        drive = env.get("SystemDrive") or "C:"
        exact = (drive + "\\Users",)
        under = tuple(v for v in (env.get("SystemRoot") or drive + "\\Windows",
                                  env.get("ProgramFiles") or drive + "\\Program Files",
                                  env.get("ProgramFiles(x86)") or drive + "\\Program Files (x86)",
                                  env.get("ProgramW6432") or drive + "\\Program Files",
                                  env.get("ProgramData") or drive + "\\ProgramData") if v)
    for item in exact:
        if p == _n(fl, item):
            return f"system path: {path} is {item}"
    for item in under:
        if _inside(fl, p, _n(fl, item)):
            return f"system path: {path} is {item} or below it"
    return ""


# ---------------------------------------------------------------- layout

def _machine_config(path, repo):  # pylint: disable=unused-argument
    """The machine layer only. `repo` is deliberately unused: the repo layer
    never moves a crew location here (decision 2)."""
    cfg = crew_config.read_global_config(path)
    return cfg if isinstance(cfg, dict) else {}


def layout(*, home=None, machine_config_path=None, env=None, repo=None, flavour=None):
    """Every root crew uses, as a dict. Never raises; a value that cannot be
    used is `None` with its `*_problem` set."""
    fl = flavour or os.path
    env = os.environ if env is None else env
    injected = home is not None
    home = fl.normpath(home if injected else os.path.expanduser("~"))
    root = fl.join(home, ".claude", "crew")
    cfg_path = machine_config_path
    if cfg_path is None and injected:
        cfg_path = fl.join(root, "config.json")
    cfg = _machine_config(cfg_path, repo)
    section = cfg.get("worktrees")
    raw = section.get("root") if isinstance(section, dict) else None
    out = {"flavour": fl, "env": env, "home": home, "root": root, "config_path": cfg_path,
           "wt": None, "wt_source": "default" if raw is None else "machine", "wt_problem": "",
           "review": fl.join(root, "review"), "scratch": fl.join(root, "scratch"),
           "scratch_tests": fl.join(root, "scratch", "tests"),
           "scratch_sandbox": fl.join(root, "scratch", "sandbox"),
           "test_root": None, "test_root_problem": "", "test_root_set": TEST_ROOT_ENV in env}
    if raw is None:
        out["wt"] = fl.join(root, "worktrees")
    elif not isinstance(raw, str) or not raw.strip():
        out["wt_problem"] = f"machine worktrees.root = {raw!r} is not a non-empty path or null"
    else:
        base = _expand(fl, raw.strip(), home)
        if not fl.isabs(base):
            out["wt_problem"] = f"machine worktrees.root = {raw!r} is not an absolute path"
        else:
            out["wt"] = fl.normpath(base)
    if out["test_root_set"]:
        value = env.get(TEST_ROOT_ENV)
        problem = test_root_problem(value, out)
        if problem:
            out["test_root_problem"] = problem
        else:
            out["test_root"] = fl.normpath(value)
    return out


def _forms(lay):
    """(label, normaliser) pairs: the string form always, the resolved form
    when the layout is in this OS's own flavour."""
    fl = lay["flavour"]
    forms = [("string", lambda p: _n(fl, p))]
    if fl is os.path:
        forms.append(("resolved", lambda p: _n(fl, os.path.realpath(p))))
    return forms


def test_root_problem(value, lay):
    """Why `value` cannot be `$CREW_TEST_ROOT`, or "" (decision 4)."""
    fl = lay["flavour"]
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        return f"{TEST_ROOT_ENV} = {value!r} is empty or contains NUL"
    if not fl.isabs(value):
        return f"{TEST_ROOT_ENV} = {value!r} is not an absolute path"
    if lay["wt"] is None:
        return f"{TEST_ROOT_ENV}: could not tell where the worktree base is ({lay['wt_problem']})"
    for label, norm in _forms(lay):
        t = norm(value)
        problem = system_path_problem(t, fl, lay["env"])
        if problem:
            return f"{TEST_ROOT_ENV} ({label}): {problem}"
        for name in ("home", "root", "wt"):
            if _inside(fl, norm(lay[name]), t):
                return f"{TEST_ROOT_ENV} ({label}) {value} is or contains the {name} {lay[name]}"
        if _inside(fl, t, norm(lay["wt"])):
            return f"{TEST_ROOT_ENV} ({label}) {value} is inside the worktree base"
        if _inside(fl, t, norm(lay["review"])):
            return f"{TEST_ROOT_ENV} ({label}) {value} is inside {lay['review']}"
        if _inside(fl, t, norm(lay["scratch"])) and not _inside(fl, t, norm(lay["scratch_tests"])):
            return f"{TEST_ROOT_ENV} ({label}) {value} is inside {lay['scratch']} but not {lay['scratch_tests']}"
    return ""


# ---------------------------------------------------------------- resolver

def repo_key(repo):
    """`<leaf>-<digest>` of `repo`'s main checkout; raises PathsError."""
    main, name_problem = crew_worktrees.main_checkout(repo)
    if name_problem:
        raise PathsError(f"{repo}: {name_problem}")
    return f"{crew_worktrees._leaf(main)}-{crew_state._repo_digest(main)}"  # pylint: disable=protected-access


def _need(lay, key):
    if lay[key] is None:
        raise PathsError(lay.get(f"{key}_problem") or f"{key} could not be resolved")
    return lay[key]


def repo_dir(repo, **kw):
    return os.path.join(_need(layout(repo=repo, **kw), "wt"), repo_key(repo))


def worktree(repo, ticket, **kw):
    return os.path.join(repo_dir(repo, **kw), _component(f"dev-{_component(ticket)}"))


def lane(repo, set_name, ticket, **kw):
    name = f"lane-{_component(set_name)}-{_component(ticket)}"
    return os.path.join(repo_dir(repo, **kw), _component(name))


def _round(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PathsError(f"round {value!r} is not a non-negative integer")
    return value


def review(repo, ticket, round_no, provider, **kw):
    name = _component(f"{_component(ticket)}-r{_round(round_no)}-{_component(provider)}")
    return os.path.join(layout(repo=repo, **kw)["review"], repo_key(repo), name)


def scratch(repo, ticket, role, **kw):
    return os.path.join(layout(repo=repo, **kw)["scratch"], repo_key(repo),
                        _component(ticket), _component(role))


def sandbox(run_id, **kw):
    return os.path.join(layout(**kw)["scratch_sandbox"], _component(run_id))


def tests(run_id, **kw):
    lay = layout(**kw)
    if lay["test_root_set"]:
        if lay["test_root_problem"]:
            raise PathsError(lay["test_root_problem"])
        return os.path.join(lay["test_root"], _component(run_id))
    return os.path.join(lay["scratch_tests"], _component(run_id))


def _target(kind, repo, ticket, role, round_no, provider, run_id, kw):
    """(path, recorded run_id) for `make_run_dir`."""
    if kind == "scratch":
        return scratch(repo, ticket, role, **kw), f"{ticket}/{role}"
    if kind == "review":
        path = review(repo, ticket, round_no, provider, **kw)
        return path, os.path.basename(path)
    if kind == "sandbox":
        return sandbox(run_id, **kw), run_id
    if kind == "tests":
        return tests(run_id, **kw), run_id
    raise PathsError(f"kind {kind!r} is not one of {', '.join(KINDS)}")


# ---------------------------------------------------------------- step 1

def _shape(which, rem):
    """The kind a path of components `rem` below allowed root `which` is, or None."""
    if any(component_problem(c) for c in rem):
        return None
    if which == "test_root":
        return "tests" if len(rem) == 1 else None
    if which == "review":
        return "review" if len(rem) == 2 and _KEY_RE.match(rem[0]) else None
    if which == "scratch":
        if len(rem) == 2 and rem[0].lower() in ("tests", "sandbox"):
            return rem[0].lower()
        if len(rem) == 3 and _KEY_RE.match(rem[0]):
            return "scratch"
    return None


def string_problem(path, lay, resolved=False):
    """Step 1 on one form of `path`. {problem, root, which, rem, kind}; pure
    when `resolved` is False (only `lay`'s flavour is used)."""
    fl = lay["flavour"]
    out = {"problem": "", "root": None, "which": None, "rem": [], "kind": None}
    if not isinstance(path, str) or not path.strip() or "\0" in path or not fl.isabs(path):
        out["problem"] = f"guard: {path!r} is empty, relative or contains NUL"
        return out
    p_raw = fl.normpath(fl.abspath(path))
    norm = (lambda q: _n(fl, os.path.realpath(q))) if resolved else (lambda q: _n(fl, q))
    p = _n(fl, p_raw)
    if lay["wt"] is None:
        out["problem"] = f"layout: could not tell where the worktree base is ({lay['wt_problem']})"
        return out
    if _is_fs_root(fl, p):
        out["problem"] = f"protected: {path} is a filesystem, drive or share root"
        return out
    problem = system_path_problem(p, fl, lay["env"])
    if problem:
        out["problem"] = problem
        return out
    protected = ["home", "root", "wt", "review", "scratch", "scratch_tests", "scratch_sandbox"]
    if lay["test_root"]:
        protected.append("test_root")
    for name in protected:
        if p == norm(lay[name]):
            out["problem"] = f"protected: {path} is the {name} {lay[name]}"
            return out
    if _inside(fl, p, norm(lay["wt"])):
        out["problem"] = f"containment: {path} is inside the worktree base; worktrees are removed by git"
        return out
    candidates = (("test_root", lay["test_root"]), ("review", lay["review"]), ("scratch", lay["scratch"]))
    for which, root in candidates:
        if root and _strictly_inside(fl, p, norm(root)):
            out["which"], out["root"] = which, root
            break
    else:
        out["problem"] = (f"containment: {path} is not inside {lay['scratch']}, {lay['review']} "
                          f"or an accepted {TEST_ROOT_ENV}")
        return out
    base = norm(out["root"]).rstrip(fl.sep)
    rem = [c for c in p_raw[len(base) + 1:].split(fl.sep) if c] if not resolved else \
        [c for c in p[len(base) + 1:].split(fl.sep) if c]
    out["rem"] = rem
    if rem and _KEY_RE.match(rem[0]) and len(rem) == 1:
        out["problem"] = f"protected: {path} is a <leaf>-<digest> folder"
        return out
    kind = _shape(out["which"], rem)
    if kind is None:
        out["problem"] = f"shape: {path} is not a run folder of any kind (a shared parent or a subfolder)"
        return out
    out["kind"] = kind
    return out


# ---------------------------------------------------------------- step 2

def _anchor_problem(path, root, rem):
    """The realpath must be the allowed root's realpath plus the same components."""
    if os.path.normcase(os.path.realpath(path)) != os.path.normcase(os.path.join(os.path.realpath(root), *rem)):
        return f"anchor: {path} resolves to {os.path.realpath(path)}, not inside {root} by the same names"
    return ""


def _component_problem(root, rem):
    """No component below the allowed root is a link, a reparse point or a non-directory."""
    cur = root
    for part in rem:
        cur = os.path.join(cur, part)
        try:
            st = _lstat(cur)
        except OSError as exc:
            return f"link walk: could not lstat {cur}: {exc}"
        if stat.S_ISLNK(st.st_mode) or _attrs(st) & _REPARSE or not stat.S_ISDIR(st.st_mode):
            return f"link walk: {cur} is a link, a reparse point or not a directory"
    return ""


# ---------------------------------------------------------------- step 3

def _read_record(rec):
    """(dict or None, problem): the record, never read through a link."""
    try:
        lst = _lstat(rec)
    except FileNotFoundError:
        return None, f"record: no {OWNER} in the run folder"
    except OSError as exc:
        return None, f"record: could not lstat {rec}: {exc}"
    if not stat.S_ISREG(lst.st_mode):
        return None, f"record: {rec} is not a regular file"
    if _attrs(lst) & _REPARSE:
        return None, f"record: {rec} is a reparse point"
    if lst.st_nlink != 1:
        return None, f"record: {rec} has {lst.st_nlink} links"
    _after_record_lstat(rec)
    try:
        if os.name == "nt":
            fd = os.open(rec, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        else:
            fd = os.open(rec, os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK)
    except OSError as exc:
        return None, f"record: could not open {rec} without following links: {exc}"
    try:
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode) or (fst.st_dev, fst.st_ino) != (lst.st_dev, lst.st_ino):
            return None, f"record: {rec} changed between its check and its open"
        chunks, size = [], 0
        while size <= RECORD_MAX:
            chunk = os.read(fd, RECORD_MAX + 1 - size)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
    finally:
        os.close(fd)
    data = b"".join(chunks)
    if len(data) > RECORD_MAX:
        return None, f"record: {rec} is larger than {RECORD_MAX} bytes"
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, f"record: {rec} is not JSON"
    if not isinstance(parsed, dict):
        return None, f"record: {rec} is not a JSON object"
    return parsed, ""


def _record_problem(path, run_id, kind, nonce):
    rec, problem = _read_record(os.path.join(path, OWNER))
    if problem:
        return problem
    if rec.get("v") != 1:
        return f"record: version {rec.get('v')!r} is not 1"
    if rec.get("run_id") != run_id:
        return f"record: run_id {rec.get('run_id')!r} is not {run_id!r}"
    if rec.get("kind") != kind:
        return f"record: kind {rec.get('kind')!r} is not the folder's shape {kind!r}"
    if not isinstance(rec.get("path"), str) or \
            os.path.normcase(rec["path"]) != os.path.normcase(os.path.realpath(path)):
        return f"record: path {rec.get('path')!r} is not {os.path.realpath(path)}"
    if nonce is not None and rec.get("nonce") != nonce:
        return "record: nonce does not match"
    return ""


# ---------------------------------------------------------------- step 4

def _identity(st):
    return (st.st_dev, st.st_ino)


def _capture_root(path):
    """(stat, fd or None): POSIX opens the run folder O_NOFOLLOW; Windows re-lstats."""
    if os.name == "nt":
        return _lstat(path), None
    fd = os.open(path, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW)
    return os.fstat(fd), fd


# ---------------------------------------------------------------- step 5: mounts

def _unescape(field):
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), field)


def _is_volume_target(target):
    return bool(_VOLUME_RE.match(target or ""))


def _mount_problem(path):
    """Linux: a mount point equal to or under the run folder, from mountinfo.
    An unreadable or unparsable mountinfo is a refusal, never "no mounts"."""
    if _is_linux():
        try:
            text = _read_mountinfo()
        except OSError as exc:
            return f"could not tell whether a mount is inside: {exc}"
        real = os.path.normcase(os.path.realpath(path))
        for line in text.splitlines():
            if not line.strip():
                continue
            fields = line.split(" ")
            if len(fields) < 10 or "-" not in fields[6:]:
                return f"could not tell whether a mount is inside: unparsable mountinfo line {line!r}"
            point = os.path.normcase(os.path.normpath(_unescape(fields[4])))
            if _inside(os.path, point, real):
                return f"mount crossing: {_unescape(fields[4])} is a mount inside {path}"
    return ""


def _link_entry(st):
    """True for an entry the walk removes as a link (never descends)."""
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(_attrs(st) & _REPARSE) and getattr(st, "st_reparse_tag", 0) in (_TAG_SYMLINK, _TAG_MOUNT)


def _prescan(path, root_dev):
    """(problem, entries, notes): a read-only pass over the run folder."""
    problem = _mount_problem(path)
    if problem:
        return problem, 0, []
    count, notes, stack = 0, [], [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                names = [e.name for e in it]
        except OSError as exc:
            return f"could not tell what {current} holds: {exc}", count, notes
        for name in names:
            entry = os.path.join(current, name)
            count += 1
            try:
                st = _lstat(entry)
            except OSError as exc:
                return f"could not tell what {entry} is: {exc}", count, notes
            if _link_entry(st):
                if _attrs(st) & _REPARSE:
                    try:
                        target = _readlink(entry)
                    except OSError as exc:
                        return f"could not read the target of {entry}: {exc}", count, notes
                    if _is_volume_target(target):
                        return f"mount crossing: {entry} points at the volume root {target}", count, notes
                continue
            if _attrs(st) & _REPARSE and stat.S_ISDIR(st.st_mode):
                tag = getattr(st, 'st_reparse_tag', 0)
                return f"could not tell what {entry} is: a directory with reparse tag {tag:#x}", count, notes
            if stat.S_ISDIR(st.st_mode):
                if _child_dev(st, entry, "scan") != root_dev:
                    return f"mount crossing at {entry} (pre-scan)", count, notes
                stack.append(entry)
            elif os.name == "nt" and _attrs(st) & _READONLY and st.st_nlink > 1:
                notes.append(f"{entry}: read-only with {st.st_nlink} links, deleted by name, flag unchanged")
    return "", count, notes


# ---------------------------------------------------------------- walk: Windows

_DWORD = ctypes.c_uint32


class _BHFI(ctypes.Structure):  # BY_HANDLE_FILE_INFORMATION (FILETIME as two DWORDs)
    _fields_ = [("attrs", _DWORD), ("created", _DWORD * 2), ("accessed", _DWORD * 2),
                ("written", _DWORD * 2), ("serial", _DWORD), ("size_high", _DWORD),
                ("size_low", _DWORD), ("links", _DWORD), ("index_high", _DWORD), ("index_low", _DWORD)]


class _BasicInfo(ctypes.Structure):  # FILE_BASIC_INFO; zero times mean "unchanged"
    _fields_ = [("created", ctypes.c_longlong), ("accessed", ctypes.c_longlong),
                ("written", ctypes.c_longlong), ("changed", ctypes.c_longlong), ("attrs", _DWORD)]


_KERNEL32 = []


def _k32():
    """kernel32 with the signatures used here; Windows only, loaded on first use."""
    if not _KERNEL32:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.argtypes = [ctypes.c_wchar_p, _DWORD, _DWORD, ctypes.c_void_p, _DWORD, _DWORD,
                                    ctypes.c_void_p]
        k32.CreateFileW.restype = ctypes.c_void_p
        k32.SetFileInformationByHandle.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, _DWORD]
        k32.SetFileInformationByHandle.restype = ctypes.c_int
        k32.GetFileInformationByHandle.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        k32.GetFileInformationByHandle.restype = ctypes.c_int
        _KERNEL32.append(k32)
    return _KERNEL32[0]

_INVALID_HANDLE = ctypes.c_void_p(-1).value
_SETTABLE = 0x1 | 0x2 | 0x4 | 0x20 | 0x100 | 0x1000 | 0x2000
_DISPOSE_FLAGS = 0x1 | 0x2 | 0x10  # DELETE | POSIX_SEMANTICS | IGNORE_READONLY_ATTRIBUTE


def _settable(attrs):
    """`attrs` minus READONLY, as FILE_BASIC_INFO accepts them (0 means NORMAL)."""
    return (attrs & _SETTABLE & ~_READONLY) or 0x80


def _win_open(path):
    """A handle on `path` itself (never its target), or None."""
    access = 0x00010000 | 0x80 | 0x100  # DELETE | FILE_READ_ATTRIBUTES | FILE_WRITE_ATTRIBUTES
    handle = _k32().CreateFileW(path, access, 0x7, None, 3, 0x02000000 | 0x00200000, None)
    if handle in (None, 0, _INVALID_HANDLE):
        return None
    return handle


def _win_links(handle):
    info = _BHFI()
    if not _k32().GetFileInformationByHandle(handle, ctypes.byref(info)):
        return None
    return info.links


def _win_set_attrs(handle, attrs):
    info = _BasicInfo(0, 0, 0, 0, _settable(attrs))
    return bool(_k32().SetFileInformationByHandle(handle, 0, ctypes.byref(info), ctypes.sizeof(info)))


def _win_dispose(handle):
    flags = _DWORD(_DISPOSE_FLAGS)
    return bool(_k32().SetFileInformationByHandle(handle, 21, ctypes.byref(flags), ctypes.sizeof(flags)))


def _win_readonly(path, st):
    """Clear READONLY on `path` through a verified handle. (problem, gone):
    `gone` is True when the name was deleted through the handle (a file with
    more than one link: its shared flag is never cleared)."""
    _before_attr_clear(path)
    handle = _win_open(path)
    if handle is None:
        return f"could not open {path} to clear its read-only flag: winerror {ctypes.get_last_error()}", False
    import msvcrt  # pylint: disable=import-outside-toplevel,import-error
    fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    try:
        fst = os.fstat(fd)
        links = _win_links(handle)
        if links is None:
            return f"could not read the link count of {path}", False
        if _identity(fst) != _identity(st) or _attrs(fst) & _REPARSE:
            return f"{path} changed before its read-only flag was cleared", False
        if links > 1:
            if _win_dispose(handle):
                return "", True
            return (f"read-only file with {links} links: cannot delete without changing the shared file: "
                    f"{path}"), False
        if not _win_set_attrs(handle, _attrs(fst)):
            return f"could not clear the read-only flag of {path}: winerror {ctypes.get_last_error()}", False
    finally:
        os.close(fd)
    return "", False


def _walk_windows(directory, run, root_id, root_dev, done):
    """Delete everything below `directory`; `done` counts removals. Returns a
    problem string or "". No dir_fd on Windows: identity is re-checked."""
    with os.scandir(directory) as it:
        names = [e.name for e in it]
    for name in names:
        if _identity(_lstat(run)) != root_id:
            return f"root identity changed: {run} was replaced during the walk"
        entry = os.path.join(directory, name)
        st = _lstat(entry)
        attrs = _attrs(st)
        if attrs & _REPARSE:  # walk: a link entry is removed as a link, never descended
            tag = getattr(st, "st_reparse_tag", 0)
            if tag in (_TAG_SYMLINK, _TAG_MOUNT):
                if _is_volume_target(_readlink(entry)):
                    return f"mount crossing at {entry}"
                if attrs & _DIRECTORY:
                    os.rmdir(entry)
                else:
                    os.unlink(entry)
                done[0] += 1
                continue
            if attrs & _DIRECTORY:
                return f"could not tell what {entry} is: a directory with reparse tag {tag:#x}"
            os.unlink(entry)
            done[0] += 1
            continue
        if attrs & _DIRECTORY:
            problem = _walk_dir_check(st, entry, root_dev)
            if problem:
                return problem
            if attrs & _READONLY:
                problem, _gone = _win_readonly(entry, st)
                if problem:
                    return problem
            problem = _walk_windows(entry, run, root_id, root_dev, done)
            if problem:
                return problem
            again = _lstat(entry)
            if _identity(again) != _identity(st) or _attrs(again) & _REPARSE:
                return f"{entry} changed during the walk"
            os.rmdir(entry)
            done[0] += 1
            continue
        if attrs & _READONLY:
            problem, gone = _win_readonly(entry, st)
            if problem:
                return problem
            if gone:
                done[0] += 1
                continue
        os.unlink(entry)
        done[0] += 1
    return ""


# ---------------------------------------------------------------- walk: POSIX

def _walk_dir_check(st, path, root_dev):
    if _child_dev(st, path, "walk") != root_dev:
        return f"mount crossing at {path}"
    return ""


def _walk_posix(dfd, dpath, root_dev, done):
    """Delete everything below the directory open as `dfd` (verified by the
    caller). Returns a problem string or ""."""
    st = os.fstat(dfd)
    if not (st.st_mode & stat.S_IWUSR and st.st_mode & stat.S_IXUSR and st.st_mode & stat.S_IRUSR):
        _before_attr_clear(dpath)
        os.fchmod(dfd, stat.S_IMODE(st.st_mode) | stat.S_IRWXU)
    with os.scandir(dfd) as it:
        names = [e.name for e in it]
    for name in names:
        entry = os.path.join(dpath, name)
        lst = os.stat(name, dir_fd=dfd, follow_symlinks=False)
        if stat.S_ISLNK(lst.st_mode):
            os.unlink(name, dir_fd=dfd)
            done[0] += 1
            continue
        if stat.S_ISDIR(lst.st_mode):
            cfd = os.open(name, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW, dir_fd=dfd)
            try:
                fst = os.fstat(cfd)
                if _identity(fst) != _identity(lst):
                    return f"{entry} changed between its lstat and its open"
                problem = _walk_dir_check(fst, entry, root_dev) or _walk_posix(cfd, entry, root_dev, done)
                if problem:
                    return problem
            finally:
                os.close(cfd)
            again = os.stat(name, dir_fd=dfd, follow_symlinks=False)
            if _identity(again) != _identity(lst) or not stat.S_ISDIR(again.st_mode):
                return f"{entry} changed during the walk"
            os.rmdir(name, dir_fd=dfd)
            done[0] += 1
            continue
        os.unlink(name, dir_fd=dfd)
        done[0] += 1
    return ""


# ---------------------------------------------------------------- delete

def _report(path, ok, removed=0, rule="", at="", notes=None, would=None):
    out = {"ok": ok, "path": path, "removed": removed, "rule": rule, "at": at or (path if rule else "")}
    if notes:
        out["notes"] = notes
    if would is not None:
        out["would_remove"] = would
    return out


def delete_run_dir(path, run_id, *, nonce=None, dry_run=False, home=None,
                   machine_config_path=None, env=None):
    """(ok, report). Removes the run folder `path` that `make_run_dir`
    created, or refuses and changes nothing. Never raises."""
    try:
        return _delete(path, run_id, nonce, dry_run, home, machine_config_path, env)
    except Exception as exc:  # pylint: disable=broad-except
        return False, _report(path, False, rule=f"unexpected error: {type(exc).__name__}: {exc}")


def _delete(path, run_id, nonce, dry_run, home, machine_config_path, env):  # pylint: disable=too-many-return-statements
    lay = layout(home=home, machine_config_path=machine_config_path, env=env)
    first = string_problem(path, lay)
    if first["problem"]:
        return False, _report(path, False, rule=first["problem"])
    path = os.path.normpath(os.path.abspath(path))
    second = string_problem(os.path.realpath(path), lay, resolved=True)
    if second["problem"]:
        return False, _report(path, False, rule=f"(resolved) {second['problem']}")
    if second["kind"] != first["kind"]:
        return False, _report(path, False, rule="shape: the path and its realpath are different kinds")
    root, rem, kind = first["root"], first["rem"], first["kind"]
    problem = _anchor_problem(path, root, rem)
    if problem:
        return False, _report(path, False, rule=problem)
    problem = _component_problem(root, rem)
    if problem:
        return False, _report(path, False, rule=problem)
    st_path = _lstat(path)
    problem = _record_problem(path, run_id, kind, nonce)
    if problem:
        return False, _report(path, False, rule=problem)
    _after_owner_check(path)
    fd = parent_fd = None
    try:
        try:
            cur, fd = _capture_root(path)
        except OSError as exc:
            return False, _report(path, False, rule=(f"root identity: could not open {path} without "
                                                     f"following links: {exc}"))
        if _identity(cur) != _identity(st_path):
            return False, _report(path, False, rule=f"root identity: {path} was replaced after its checks")
        root_id = _identity(cur)
        problem, count, notes = _prescan(path, cur.st_dev)
        if problem:
            return False, _report(path, False, rule=problem, notes=notes)
        if dry_run:
            return True, _report(path, True, notes=notes, would=count + 1)
        done = [0]
        if os.name == "nt":
            problem = _walk_windows(path, path, root_id, cur.st_dev, done)
            if not problem:
                again = _lstat(path)
                if _identity(again) != root_id or _attrs(again) & _REPARSE:
                    problem = f"root identity changed: {path} was replaced during the walk"
                elif _attrs(again) & _READONLY:
                    problem, _gone = _win_readonly(path, again)
            if not problem:
                os.rmdir(path)
                done[0] += 1
        else:
            parent = os.path.dirname(path)
            parent_st = os.lstat(parent)
            parent_fd = os.open(parent, os.O_RDONLY | _O_DIRECTORY)
            if _identity(os.fstat(parent_fd)) != _identity(parent_st):
                return False, _report(path, False, rule=f"root identity: the parent of {path} changed")
            problem = _walk_posix(fd, path, cur.st_dev, done)
            if not problem:
                name = os.path.basename(path)
                again = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if _identity(again) != root_id or _identity(os.fstat(parent_fd)) != _identity(parent_st):
                    problem = f"root identity changed: {path} was replaced during the walk"
                else:
                    os.rmdir(name, dir_fd=parent_fd)
                    done[0] += 1
        if problem:
            return False, _report(path, False, removed=done[0], rule=problem)
        return True, _report(path, True, removed=done[0])
    finally:
        for handle in (fd, parent_fd):
            if handle is not None:
                os.close(handle)


# ---------------------------------------------------------------- make

def make_run_dir(kind, *, repo=None, ticket=None, role=None, round_no=None, provider=None,
                 run_id=None, home=None, machine_config_path=None, env=None):
    """Create one run folder exclusively, with its ownership record and fixed
    subfolders. {path, run_id, nonce}; raises PathsError."""
    kw = {"home": home, "machine_config_path": machine_config_path, "env": env}
    path, recorded = _target(kind, repo, ticket, role, round_no, provider, run_id, kw)
    lay = layout(**kw)
    check = string_problem(path, lay)
    if check["problem"] or check["kind"] != kind:
        raise PathsError(f"refused: crew could not later delete {path}: {check['problem'] or 'shape'}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        os.mkdir(path)
    except FileExistsError as exc:
        raise PathsError(f"refused: {path} already exists (run folders are exclusive)") from exc
    real = os.path.realpath(path)
    again = string_problem(real, lay, resolved=True)
    if again["problem"]:
        os.rmdir(path)
        raise PathsError(f"refused: {path} resolves outside crew's roots: {again['problem']}")
    nonce = secrets.token_hex(16)
    record = {"v": 1, "run_id": recorded, "kind": kind, "path": real,
              "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "pid": os.getpid(), "host": socket.gethostname(), "nonce": nonce}
    text = json.dumps(record, indent=1, sort_keys=True) + "\n"
    tmp = os.path.join(path, f"{OWNER}.{nonce}.tmp")
    with open(tmp, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp, os.path.join(path, OWNER))
    for sub in SUBDIRS[kind]:
        os.mkdir(os.path.join(path, sub))
    return {"path": path, "run_id": recorded, "nonce": nonce}


# ---------------------------------------------------------------- explain

def _repo_layer_root(repo):
    """The repo layer's raw worktrees.root, or None; never raises."""
    try:
        main, _ = crew_worktrees.main_checkout(repo)
        with open(os.path.join(main, ".crew", "config.json"), encoding="utf-8") as handle:
            data = json.load(handle)
        section = data.get("worktrees") if isinstance(data, dict) else None
        return section.get("root") if isinstance(section, dict) else None
    except (OSError, ValueError):
        return None


def explain(repo=".", *, home=None, machine_config_path=None, env=None):
    """Report-only: where crew_paths puts things and how that differs from the
    repo layer. Returns a dict with a `lines` list."""
    lay = layout(home=home, machine_config_path=machine_config_path, env=env, repo=repo)
    lines = [f"crew root: {lay['root']}"]
    cfg_path = lay["config_path"] or crew_config.GLOBAL_CONFIG_PATH
    state = "absent"
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as handle:
                state = "read" if isinstance(json.load(handle), dict) else "machine config unreadable"
        except (OSError, ValueError):
            state = "machine config unreadable"
    if state == "machine config unreadable":
        lines.append(f"machine config unreadable: {cfg_path} (defaults used)")
    else:
        lines.append(f"machine config: {cfg_path} ({state})")
    if lay["wt"]:
        lines.append(f"worktree base: {lay['wt']} ({lay['wt_source']})")
    else:
        lines.append(f"worktree base: could not tell ({lay['wt_problem']})")
    repo_value = _repo_layer_root(repo)
    ignored = False
    if repo_value is not None:
        expanded = _expand(os.path, str(repo_value), lay["home"])
        if not lay["wt"] or _n(os.path, expanded) != _n(os.path, lay["wt"]):
            ignored = True
            lines.append(f"repo worktrees.root = {repo_value!r}: repo value ignored by crew_paths; "
                         "crew_worktrees still honours it (protected-key change is a later ticket)")
    if lay["test_root_set"]:
        lines.append(f"{TEST_ROOT_ENV}: {lay['test_root'] or 'refused: ' + lay['test_root_problem']}")
    return {"root": lay["root"], "worktree_base": lay["wt"], "machine_config": state,
            "repo_value": repo_value, "repo_value_ignored": ignored, "lines": lines}


# ---------------------------------------------------------------- CLI

def _cli(argv=None):
    parser = argparse.ArgumentParser(prog="crew_paths.py", description=__doc__.split("\n\n", 1)[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    where = sub.add_parser("where")
    where.add_argument("kind", choices=("worktree", "lane") + KINDS)
    for flag in ("--ticket", "--role", "--set", "--provider", "--run-id"):
        where.add_argument(flag)
    where.add_argument("--round", type=int)
    where.add_argument("--repo", default=".")
    where.add_argument("--json", action="store_true")
    exp = sub.add_parser("explain")
    exp.add_argument("--repo", default=".")
    exp.add_argument("--json", action="store_true")
    chk = sub.add_parser("check-delete")
    chk.add_argument("path")
    chk.add_argument("--run-id", required=True)
    chk.add_argument("--nonce")
    chk.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "where":
        try:
            path = {
                "worktree": lambda: worktree(args.repo, args.ticket),
                "lane": lambda: lane(args.repo, args.set, args.ticket),
                "review": lambda: review(args.repo, args.ticket, args.round, args.provider),
                "scratch": lambda: scratch(args.repo, args.ticket, args.role),
                "sandbox": lambda: sandbox(args.run_id),
                "tests": lambda: tests(args.run_id),
            }[args.kind]()
        except PathsError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"kind": args.kind, "path": path}) if args.json else path)
        return 0
    if args.cmd == "explain":
        got = explain(args.repo)
        print(json.dumps(got, indent=1) if args.json else "\n".join(got["lines"]))
        return 0
    ok, report = delete_run_dir(args.path, args.run_id, nonce=args.nonce, dry_run=True)
    if args.json:
        print(json.dumps(report, indent=1))
    elif ok:
        print(f"would delete {report['path']} ({report['would_remove']} entries); nothing was changed")
        for note in report.get("notes", []):
            print(f"  note: {note}")
    else:
        print(f"would refuse {report['path']}: {report['rule']}; nothing was changed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_cli())
