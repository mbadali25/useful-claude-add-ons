#!/usr/bin/env python3
"""promote-gate.sh's whole decision, in ONE python process (crew 1.3.36).

    python3 _promote_gate.py < <hook payload>      (cwd: the project dir)

Why. On Git Bash every process start is an MSYS fork (0.3-0.5 s here when the
host is quiet, 1-3 s under load), and the gate used to run about forty-five of
them for one deploy: eight python starts, a dozen `git` probes, and the `$(...)`
subshells around them. That is 19-20 s best case against a 20 s hook timeout,
and 35-50 s when several lanes run at once, so a deploy-shaped command timed
out, which is not a block. promote-gate.sh now does only what needs a shell (the
PowerShell hand-off, the opt-out, the python lookup, the no-python jq fallback)
and runs this file once. Every rule below is the one the shell script held, in
the same order and with the same messages; the matcher, the verdict, the
dispatch, tree, github and review readers are the modules that were already
there, called in-process instead of through `$(...)`.

Exit status, the protocol with promote-gate.sh:
    0         allow
    2         block; the whole message was written to stderr
    10 + N    the containment match could not read the map (the old ENV_STATUS N,
              1 3 or 4); the reason is on stderr, promote-gate.sh writes the
              framing around it
    20 + N    the pre-deploy check could not be evaluated (the old VERDICT_STATUS
              N, 1 or 5); the header and the reason are on stderr, promote-gate.sh
              writes the closing lines
Anything else (a crash, a kill, an interpreter that would not start) is a block
too: an error is not permission. Two statuses carry their own number so that the
shell, which wrote those two messages before this file existed, still writes
them, and sabotage.py's two mutations of its `if` lines (the harness is not
touched here) still break the behaviour they were written to break.

THE DEADLINE. The gate keeps one deadline for everything after the shell began,
`promote.deadlineSeconds` (config) or, when that is null, the hook timeout of
this guard's row in crew_hook.TABLE less DEFAULT_MARGIN. A hook that runs out of
time is not a block, so every bounded step (the policy-map listing, the review
search) is given what is left of THIS deadline, never a slice of its own. A
configured value is clamped to the row's timeout less REAP (the helper's own
reap), so the setting can lengthen the gate up to what the hook allows and no
further.

What changed in what it decides: nothing that was measured (41 recorded cases
agree). One input differs by construction: the shell passed the command to
python as an ARGUMENT, and Git Bash rewrites an argument that starts like a POSIX
path (`/opt/deploy.sh prod` became `C:/Program Files/Git/opt/deploy.sh prod`).
The command is read from the payload here, so it is matched as written.
"""
import contextlib
import io
import importlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

GATE_ROW = "promote-gate.sh"
FALLBACK_TIMEOUT = 20          # crew_hook.TABLE could not be read: the row's value when written
DEFAULT_MARGIN = 4             # seconds kept back from the hook timeout (20 -> the old 16)
REAP = 2                       # seconds a helper needs to reap its child, kept back from a configured value
CONFIG_KEY = ("promote", "deadlineSeconds")
MAP = ".crew/verify.json"
ENV_BASE = 10                  # exit 10 + N: the containment match could not read the map
VERDICT_BASE = 20              # exit 20 + N: the pre-deploy check could not be evaluated
RS = "\x1e"


class Stop(Exception):
    """End the gate with `code` (0 allow, 2 block); the message was already written."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def say(text=""):
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


# --------------------------------------------------------------------------
# the deadline

def hook_timeout():
    """This guard's row timeout (seconds) from the dispatcher's own table."""
    try:
        import crew_hook  # pylint: disable=import-outside-toplevel
        for row in crew_hook.TABLE:
            if row.script == GATE_ROW and row.event == "PreToolUse":
                return float(row.timeout)
    except Exception:  # pylint: disable=broad-except
        pass
    return float(FALLBACK_TIMEOUT)


def configured_seconds():
    """`promote.deadlineSeconds` of the effective config, or None (null, absent,
    unreadable, or not a positive number: the derived default applies)."""
    try:
        import crew_config  # pylint: disable=import-outside-toplevel
        value = crew_config.resolve_config(os.getcwd())
    except Exception:  # pylint: disable=broad-except
        return None
    for key in CONFIG_KEY:
        value = value.get(key) if isinstance(value, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value > 0 else None


def deadline_seconds(timeout=None, configured=None):
    """Seconds after the shell began that the gate may run. Pure, so a test can
    call it with the row's timeout and the configured value."""
    timeout = hook_timeout() if timeout is None else float(timeout)
    ceiling = max(timeout - REAP, 1.0)
    if configured is None:
        return max(timeout - DEFAULT_MARGIN, 1.0)
    return min(float(configured), ceiling)


class Clock:
    """The gate's one deadline, a Unix time, taken from the shell's start."""

    def __init__(self):
        raw = os.environ.get("CREW_GATE_START", "")
        try:
            self.start = float(raw) if raw else time.time()
        except ValueError:
            self.start = time.time()
        self._deadline = None

    @property
    def deadline(self):
        if self._deadline is None:
            self._deadline = self.start + deadline_seconds(None, configured_seconds())
        return self._deadline

    def left(self):
        return self.deadline - time.time()


# --------------------------------------------------------------------------
# git

_GIT = shutil.which("git")


def git(args, cwd=None, timeout=None, data=None):
    """(status, stdout text) of one git run; (127, '') when git cannot run, 124
    on a timeout. stdout loses its trailing newlines, as `$(...)` did."""
    if _GIT is None:
        return 127, ""
    try:
        done = subprocess.run([_GIT] + list(args), cwd=cwd, capture_output=True, check=False,
                              timeout=timeout, input=data,
                              stdin=None if data is not None else subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError:
        return 127, ""
    return done.returncode, done.stdout.decode("utf-8", errors="replace").rstrip("\n")


def git_parallel(jobs, timeout=None):
    """Run several independent git commands at once. [(status, stdout), ...]."""
    if _GIT is None:
        return [(127, "")] * len(jobs)
    procs = []
    for args in jobs:
        try:
            procs.append(subprocess.Popen(  # pylint: disable=consider-using-with
                [_GIT] + list(args), stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL))
        except OSError:
            procs.append(None)
    results = []
    for proc in procs:
        if proc is None:
            results.append((127, ""))
            continue
        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            results.append((124, ""))
            continue
        results.append((proc.returncode, out.decode("utf-8", errors="replace").rstrip("\n")))
    return results


class Tree:
    """What `git -C <dir>` says about one directory, asked once. The combined
    question answers all four fields in one process; when it fails (no commit
    yet, not a repository) each field is asked alone, so a failure names the
    field that failed, as the separate probes always did."""

    def __init__(self, path):
        self.path = path
        self._info = None

    def _load(self):
        if self._info is not None:
            return self._info
        status, out = git(["-C", self.path, "rev-parse", "--show-toplevel", "--git-common-dir",
                           "HEAD", "--short", "HEAD"])
        lines = out.split("\n")
        if status == 0 and len(lines) == 4 and all(lines):
            self._info = {"top": lines[0], "common": lines[1], "full": lines[2], "short": lines[3]}
            return self._info
        info = {}
        for field, args in (("top", ["--show-toplevel"]), ("common", ["--git-common-dir"]),
                            ("full", ["HEAD"]), ("short", ["--short", "HEAD"])):
            code, text = git(["-C", self.path, "rev-parse"] + args)
            info[field] = text if code == 0 else ""
        self._info = info
        return info

    top = property(lambda self: self._load()["top"])
    full = property(lambda self: self._load()["full"])
    short = property(lambda self: self._load()["short"])

    @property
    def common(self):
        """The repository's common git dir as a real path, '' when unknown."""
        raw = self._load()["common"]
        where = os.path.join(self.path, raw) if raw else ""
        return os.path.normcase(real(where)) if where and os.path.isdir(where) else ""


def real(path):
    return os.path.realpath(path)


def same_path(first, second):
    return os.path.normcase(real(first)) == os.path.normcase(real(second))


# --------------------------------------------------------------------------
# directories, the way `( cd "$1" && cd "$2" && pwd -P )` resolved them

_DRIVE = re.compile(r"^/([A-Za-z])(?:/(.*))?$")


def native(target):
    """`target` as this OS can open it. On Windows an MSYS drive path
    (`/c/work`) becomes `C:/work` and any other POSIX-rooted path goes through
    `cygpath -w`; None when it cannot be told."""
    if os.name != "nt" or not target.startswith("/"):
        return target
    match = _DRIVE.match(target)
    if match:
        return f"{match.group(1).upper()}:/{match.group(2) or ''}"
    cygpath = shutil.which("cygpath")
    if cygpath is None:
        return None
    try:
        done = subprocess.run([cygpath, "-w", "--", target], capture_output=True, check=False,
                              timeout=10, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    text = done.stdout.decode("utf-8", errors="replace").strip()
    return text if done.returncode == 0 and text else None


def resolve_dir(base, target):
    """The physical path of `target` as `cd`ed to from `base`, or '' when it
    does not resolve to a directory."""
    home = os.environ.get("HOME") or os.path.expanduser("~")
    if target == "~":
        target = home
    elif target.startswith("~/"):
        target = home + "/" + target[2:]
    if target == "":
        path = base
    else:
        converted = native(target)
        if converted is None:
            return ""
        path = converted if os.path.isabs(converted) or re.match(r"^[A-Za-z]:", converted) \
            else os.path.join(base, converted)
    return real(path) if os.path.isdir(path) else ""


# --------------------------------------------------------------------------
# incidents (_common.sh's crew_incident_active / crew_incident_log)

def incident_active():
    """An open incident turns every block into a recorded skip. Any failure to
    read it is "not active": a gate that cannot read its own state keeps gating."""
    if not os.path.isfile(".crew/incident.json"):
        return False
    try:
        import crew_common  # pylint: disable=import-outside-toplevel
        cfg_dir = crew_common.repo_config_dir(".")[0]
        with open(os.path.join(cfg_dir, "config.json"), encoding="utf-8", errors="replace") as fh:
            if re.search(r'"standDown"\s*:\s*false', fh.read()):
                return False
    except Exception:  # pylint: disable=broad-except
        pass
    try:
        with open(".crew/incident.json", encoding="utf-8") as fh:
            data = json.load(fh)
        expires = int(data["expiresAtEpoch"]) if isinstance(data, dict) else 0
    except Exception:  # pylint: disable=broad-except
        expires = 0
    return expires > 0 and int(time.time()) < expires


def incident_log(detail):
    import crew_incident  # pylint: disable=import-outside-toplevel
    table = str.maketrans({"\t": " ", "\r": " ", "\n": " "})
    crew_incident.log_skip(".", "promote", detail.translate(table))


# --------------------------------------------------------------------------
# the payload

def payload_field(doc, *path):
    """jq's `.a.b // empty`, raw: a string as is, nothing for null/false/absent."""
    value = doc
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    if value is None or value is False:
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def clean(text):
    """`$(...)` drops trailing newlines, then crew_strip_cr drops every CR."""
    return text.rstrip("\n").replace("\r", "")


# --------------------------------------------------------------------------
# the gate

class Gate:  # pylint: disable=too-many-instance-attributes
    def __init__(self):
        self.clock = Clock()
        self.project = os.getcwd()
        self.cmd = ""
        self.run_cwd = ""
        self.head_map = os.environ.get("CREW_HEAD_MAP", "")
        self.map_dirty = os.environ.get("CREW_MAP_DIRTY", "")
        self.envname = ""
        self.sha = ""
        self.envlist = []

    # -- blocking ---------------------------------------------------------

    def require(self, module, why):
        """Import a helper; one that is not in the scripts directory blocks by
        name (the shell checked each with crew_py_script before it ran it)."""
        if not os.path.isfile(os.path.join(HERE, module + ".py")):
            self.block(f"{module}.py is missing or its path could not be resolved, so {why}. "
                       "This is not a pass.")
        return importlib.import_module(module)

    def block(self, why):
        """The old `block()`: an open incident records a skip, otherwise exit 2."""
        if incident_active():
            incident_log(f"{self.envname} at {self.sha or 'unknown-sha'}: {why}")
            raise Stop(0)
        say(f"PROMOTION BLOCKED ({self.envname}): {why}")
        raise Stop(2)

    def deny(self, *lines):
        for line in lines:
            say(line)
        raise Stop(2)

    # -- reading the payload and the map -----------------------------------

    def read_payload(self, raw):
        try:
            doc = json.loads(raw)
        except ValueError:
            doc = {}
        self.cmd = clean(payload_field(doc, "tool_input", "command"))
        self.run_cwd = clean(payload_field(doc, "cwd"))

    def opted_out(self):
        """No map at all is an opt-out: none in the working copy AND none
        committed. A map deleted from the working copy but committed at HEAD is
        not (T-0505): it is matched as the committed one, and reported dirty."""
        if os.path.exists(MAP):
            return False
        if not self.head_map:
            _, self.head_map = git(["rev-parse", "-q", "--verify", "HEAD:./" + MAP])
        if not self.head_map:
            return True
        self.map_dirty = "deleted, and committed at HEAD"
        return False

    def hash_dirt(self):
        """MAP_DIRTY: the working map's bytes, hashed as git would store them
        (`git hash-object` applies the autocrlf and eol filters), against HEAD's
        blob. The exact git answer is the arbiter, never a re-implementation."""
        if not os.path.exists(MAP):
            return
        if not self.head_map:
            _, self.head_map = git(["rev-parse", "-q", "--verify", "HEAD:./" + MAP])
        if self.head_map:
            code, work = git(["hash-object", "--", MAP])
            if code != 0 or not work:
                self.map_dirty = "could not be hashed to compare with HEAD"
            elif work != self.head_map:
                self.map_dirty = "differs from HEAD"
        else:
            code, out = git(["ls-files", "--others", "--exclude-standard", "--", MAP])
            if out:
                self.map_dirty = "untracked - in no commit"

    # -- step 0: is it a deploy at all? -------------------------------------

    def provably_no_deploy(self):
        """The allow fast path (crew 1.2.115): the command matches no environment
        and dispatches nothing, and the map is committed as it is."""
        if not os.path.isfile(MAP) or not self.cmd.strip():
            return False
        os.environ["CREW_HEAD_MAP"] = ""
        os.environ["CREW_MAP_DIRTY"] = ""
        try:
            import _promote_dispatch  # pylint: disable=import-outside-toplevel
            import _promote_match  # pylint: disable=import-outside-toplevel
            if _promote_match.names(self.cmd, "", ""):
                return False
            if _promote_dispatch.decide(self.cmd.replace("\r", "").rstrip("\n"), "bash") != []:
                return False
        except Exception:  # pylint: disable=broad-except
            return False
        left = min(5.0, self.clock.left() - 2)
        if left <= 0:
            return False
        code, blob = git(["rev-parse", "-q", "--verify", "HEAD:./" + MAP], timeout=left)
        if code != 0 or len(blob) not in (40, 64) or blob.strip("0123456789abcdef"):
            return False
        self.head_map = blob
        return committed_as_is(blob)

    # -- the run ------------------------------------------------------------

    def run(self, raw):  # pylint: disable=too-many-branches,too-many-statements
        self.read_payload(raw)
        if self.opted_out() or not self.cmd:
            return 0
        if self.provably_no_deploy():
            return 0
        self.hash_dirt()

        names = self.match_environments()
        names = self.add_dispatched(names)
        if not names:
            return 0
        self.envlist = names
        self.envname = ",".join(names)

        project_top = Tree(self.project).top
        if not project_top:
            self.block("not a git repository - cannot establish what is being deployed.")
        tree, run_top, hexes = self.find_tree()

        info = Tree(tree)
        project_common = Tree(project_top).common
        tree_common = info.common
        if not tree_common or not project_common:
            self.block(f"could not read the git common dir of '{tree}' or of '{project_top}', so "
                       "the gate cannot tell whether the deploy runs from this repository.")
        if tree_common != project_common:
            self.block(f"the deploy runs from '{tree}', which is a worktree of a different "
                       f"repository than this project ('{project_top}'). Its sha has no PASS row, "
                       "marker or map here.")
        if run_top != tree and Tree(run_top).common != project_common:
            self.block(f"the deploy process runs in '{run_top}', which is not a worktree of this "
                       f"project ('{project_top}').")
        self.sha, full = info.short, info.full
        if not self.sha:
            self.block(f"'{tree}' has no commit at HEAD - cannot establish what is being deployed.")

        policy_blob = self.policy_blob(tree, full, project_top)
        self.github_rule(full, tree, policy_blob)
        self.clean_or_block(tree)
        if run_top != tree:
            self.clean_or_block(run_top)
        self.literal_shas(tree, full, hexes)

        verdict = self.verdict(tree, policy_blob, full)
        review = self.review(tree, full)
        if review:
            verdict = verdict + [review] if verdict else [review]
        return self.finish(verdict, tree)

    # -- containment and dispatch -----------------------------------------

    def match_environments(self):
        import _promote_match  # pylint: disable=import-outside-toplevel
        os.environ["CREW_HEAD_MAP"] = self.head_map
        os.environ["CREW_MAP_DIRTY"] = self.map_dirty
        status, why = 0, ""
        try:
            names = _promote_match.names(self.cmd, self.head_map, self.map_dirty)
        except _promote_match.Unreadable as exc:
            names, status, why = [], exc.status, exc.why
        except Exception:  # pylint: disable=broad-except
            names, status, why = [], 1, traceback.format_exc().rstrip("\n")
        if status != 0:
            if why:
                say(why)
            raise Stop(ENV_BASE + status)
        return [name.replace("\r", "") for name in names]

    def add_dispatched(self, names):
        """T-0062: the command read as a workflow dispatch too; its environments
        are added to containment's. A reader that FAILS is never "nothing"."""
        self.envname = ",".join(names) if names else "workflow dispatch"
        _promote_dispatch = self.require(
            "_promote_dispatch", "the command cannot be read as a workflow dispatch")
        text = self.cmd.replace("\r", "").rstrip("\n")
        try:
            records = _promote_dispatch.decide(text, "bash") if text.strip() else []
        except _promote_dispatch.Block as why:
            reason = str(why)
            if "could not tell" not in reason:
                reason = f"the gate could not tell which environment this deploys: {reason}"
            records = ["block\t" + " ".join(reason.split())]
        except Exception:  # pylint: disable=broad-except
            traceback.print_exc()
            self.block("the command could not be read as a workflow dispatch "
                       "(_promote_dispatch.py failed). This is not a pass.")
        names = list(names)
        for record in records:
            kind, _, tok = record.replace("\r", "").partition("\t")
            tok = tok.strip("\t")
            if kind == "block":
                self.block(tok)
            elif kind == "env" and tok not in names:
                names.append(tok)
        return names

    # -- which tree the deploy runs from ----------------------------------

    def find_tree(self):  # pylint: disable=too-many-branches
        base = real(os.getcwd())
        if self.run_cwd:
            base = resolve_dir(base, self.run_cwd)
            if not base:
                self.block(f"the command runs from '{self.run_cwd}', which does not exist, so it "
                           "is not inside a git worktree - cannot establish what is being "
                           "deployed.")
        _promote_tree = self.require(
            "_promote_tree", "the directory the deploy runs from cannot be read")
        try:
            records = []
            for kind, tok in _promote_tree.records(self.cmd):
                if "\n" in tok or "\r" in tok or "\t" in tok:
                    kind, tok = "bad", tok.replace("\n", " ").replace("\r", " ").replace("\t", " ")
                records.append((kind, tok))
        except Exception:  # pylint: disable=broad-except
            traceback.print_exc()
            self.block("the deploy command could not be parsed for the directory it runs from "
                       "(_promote_tree.py failed). This is not a pass.")
        trees, rundirs, bare, hexes = [], [], False, []
        for kind, tok in records:
            tok = tok.replace("\r", "").strip("\t")
            if kind == "cd":
                nxt = resolve_dir(base, tok)
                if not nxt:
                    self.block(f"cannot tell which directory the deploy runs from: 'cd {tok}' "
                               f"does not resolve from '{base}'.")
                base = nxt
            elif kind == "bad":
                self.block(f"cannot tell which directory the deploy runs from: '{tok}' is not a "
                           "form the gate reads with certainty (a shell-expanded path, an "
                           "unlisted git option, git inside quoted text), and it will not guess. "
                           "Use a literal 'cd <dir> &&' or 'git -C <dir>'.")
            elif kind in ("C", "Crun"):
                found = resolve_dir(base, tok)
                if not found:
                    self.block(f"cannot tell which directory the deploy runs from: 'git -C {tok}' "
                               f"does not resolve from '{base}'.")
                (trees if kind == "C" else rundirs).append(found)
            elif kind == "midcd":
                self.block("cannot tell which directory the deploy runs from: the command changes "
                           f"directory after it starts ('{tok}'). Put the cd first - 'cd <dir> "
                           "&& <deploy>' - so the gate judges the tree the deploy runs in.")
            elif kind == "gitdir":
                self.block(f"cannot tell which tree the deploy reads: '{tok}' points git at a "
                           "repository by a route the gate does not follow. Use 'cd <dir> &&' or "
                           "'git -C <dir>'.")
            elif kind == "bare":
                bare = True
            elif kind == "hex":
                hexes.append(tok)
        if not trees or bare:
            trees.append(base)
        run_top = Tree(base).top
        if not run_top:
            self.block(f"the deploy runs from '{base}', which is not inside a git worktree - "
                       "cannot establish what is being deployed.")
        for found in rundirs:
            if Tree(found).top != run_top:
                self.block(f"the command names 'git -C {found}' outside a command substitution, "
                           f"which is not the tree the deploy runs in ('{run_top}'). Use 'cd "
                           "<dir> &&' so the deploy runs there, or '$(git -C <dir> ...)' to feed "
                           "it a sha.")
        tree = ""
        for found in trees:
            top = Tree(found).top
            if not top:
                self.block(f"the deploy runs from '{found}', which is not inside a git worktree - "
                           "cannot establish what is being deployed.")
            if not tree:
                tree = top
            elif top != tree:
                self.block(f"the deploy command names more than one tree ('{tree}' and '{top}'), "
                           "so which sha is being deployed is ambiguous. Run it from one tree.")
        return tree, run_top, hexes

    # -- which map is policy ------------------------------------------------

    def policy_blob(self, tree, full, project_top):
        """L-0768: the blob of the map committed in the deployed sha, bounded by
        what is left of the deadline; '' when the sha carries no map."""
        left = self.clock.left()
        if left < 1 or _GIT is None:
            code, listed = 124, ""
        else:
            code, listed = git(["--no-replace-objects", "-C", tree, "ls-tree", "--full-tree", full,
                                "--", MAP], timeout=left)
        if code != 0:
            self.block(f"could not list .crew/verify.json in the deployed sha {full} of '{tree}' "
                       "inside the gate's deadline, so the gate cannot tell which deployment map "
                       "is policy. This is not a pass.")
        here = real(os.getcwd())
        if self.map_dirty and tree == project_top:
            self.block(f".crew/verify.json in the project dir ({here}) has uncommitted changes: "
                       f"it {self.map_dirty}. The deploy map is policy; commit the change (it is "
                       "then reviewed like any other) or revert it.")
        blob = ""
        if listed:
            fields = listed.split(None, 3)
            kind, oid, rest = (fields + ["", "", ""])[1:4]
            if not re.fullmatch(r"[0-9a-f]+", oid or ""):
                kind = "bad"
            if not (kind == "blob" and len(oid) == 40 and rest):
                self.block(f".crew/verify.json in the deployed sha {full} is not a file, so it "
                           "cannot be read as the deployment map. This is not a pass.")
            blob = oid
        if self.map_dirty and not listed:
            self.block(f"the deployed sha {full} carries no committed .crew/verify.json, so the "
                       "project dir's map is policy, and .crew/verify.json in the project dir "
                       f"({here}) has uncommitted changes: it {self.map_dirty}. Commit the change "
                       "(it is then reviewed like any other) or revert it.")
        return blob

    def github_rule(self, full, tree, blob):
        """L-0648: the matched environment's `github` sha rule."""
        _promote_github = self.require(
            "_promote_github", "the github entry's sha rule cannot be checked")
        command = self.cmd.replace("\r", "").rstrip("\n")
        names = [n for n in self.envname.split(",") if n]
        try:
            records = _promote_github.decide(command, "bash", full, names, tree, blob or None,
                                             repr(self.clock.deadline))
        except _promote_github.Malformed as why:
            say(str(why))
            records = None
        except ValueError as why:
            say(f"_promote_github.py: the deployment map that is policy for this sha does not "
                f"parse: {why}")
            records = None
        except Exception:  # pylint: disable=broad-except
            traceback.print_exc()
            records = None
        if records is None:
            self.block("the github entry's sha rule could not be checked (_promote_github.py "
                       "failed). This is not a pass.")
        for record in records:
            kind, _, tok = record.replace("\r", "").partition("\t")
            if kind == "block":
                self.block(tok.strip("\t"))

    # -- the tree must be what is committed -------------------------------

    def clean_or_block(self, where):
        """A clean tree: a status that FAILS is could-not-tell, never clean; an
        index entry flagged skip-worktree or assume-unchanged hides edits."""
        (code_st, status), (code_ls, flags) = git_parallel([
            ["-C", where, "status", "--porcelain", "--untracked-files=all",
             "--ignore-submodules=none"],
            ["-C", where, "ls-files", "-v"]])
        if code_st != 0:
            self.block(f"could not read git status in '{where}', so the gate cannot tell whether "
                       "it is clean. This is not a pass.")
        if status:
            self.block(f"the tree this deploy runs from ('{where}') is dirty. You would be "
                       f"deploying \"{self.sha}\" plus changes that are in no commit and no "
                       "review. Commit or stash there first.")
        if code_ls != 0:
            self.block(f"could not read the index of '{where}', so the gate cannot tell whether "
                       "it is clean. This is not a pass.")
        if re.search(r"^[a-zS]", flags, re.M):
            self.block(f"'{where}' has index entries flagged skip-worktree or assume-unchanged, "
                       "which hide changes from git status. Clear them (git update-index "
                       "--no-skip-worktree / --no-assume-unchanged) before deploying.")

    def literal_shas(self, tree, full, hexes):
        """A literal sha in the command must be the tree's HEAD. A hex token that
        names no commit here (a build id, a digest) is not a sha and is left alone."""
        for hexed in hexes:
            code, resolved = git(["-C", tree, "rev-parse", "-q", "--verify", hexed + "^{commit}"])
            if code != 0:
                continue
            if resolved and resolved != full:
                self.block(f"the command names commit '{hexed}', but the tree it runs from "
                           f"('{tree}') is at \"{self.sha}\". The gate checks the sha being "
                           f"deployed; run it from a tree at '{hexed}', or drop the literal.")

    # -- checks 1-3 and 5 ---------------------------------------------------

    def verdict(self, tree, blob, full):
        import _promote_verdict  # pylint: disable=import-outside-toplevel
        try:
            return list(_promote_verdict.verdict(
                tree, blob, self.clock.deadline, self.sha, full, self.envlist))
        except _promote_verdict.CouldNotTell as why:
            detail = str(why)
            status = 5
        except Exception:  # pylint: disable=broad-except
            detail = ""
            status = 1
        say(f"PROMOTION BLOCKED ({self.envname}, sha {self.sha}, tree {tree}):")
        say(f"  - the pre-deploy check could not be evaluated (exit {status}).")
        if detail:
            say(f"    {detail}")
        raise Stop(VERDICT_BASE + status)

    def review(self, tree, full):
        """L-0703: review evidence, decided by _promote_review for both flavours.
        Returns the reasons joined, '' when none; a check that could not run is
        a reason during an incident and a block otherwise."""
        status, text = 0, ""
        try:
            import _promote_review  # pylint: disable=import-outside-toplevel
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = _promote_review.main([tree, full, repr(self.clock.deadline)]
                                              + self.envlist)
            text = out.getvalue()
            if err.getvalue():
                sys.stderr.write(err.getvalue())
        except SystemExit as stop:
            # A helper that ends the interpreter (a broken or replaced one) ran out of
            # the gate's hands: its status is the check's, and 0 with no answer is not one.
            status = stop.code if isinstance(stop.code, int) and stop.code else 1
        except Exception:  # pylint: disable=broad-except
            traceback.print_exc()
            status = 1
        if status != 0 and incident_active():
            return ("the review-evidence check could not be evaluated "
                    f"(exit {status}): _promote_review.py failed or is missing. This is not a pass.")
        if status != 0:
            self.deny(f"PROMOTION BLOCKED ({self.envname}, sha {self.sha}, tree {tree}):",
                      f"  - the review-evidence check could not be evaluated (exit {status}).",
                      "    This is not a pass. _promote_review.py failed or is missing; its",
                      "    reason is above.")
        return text

    def finish(self, verdict, tree):
        if verdict and incident_active():
            # Every unmet precondition, one row each, so the closing report names them.
            for joined in verdict:
                for reason in joined.split(RS):
                    if reason:
                        incident_log(f"{self.envname} at {self.sha}: {reason}")
            verdict = []
        if verdict:
            say(f"PROMOTION BLOCKED ({self.envname}, sha {self.sha}, tree {tree}):")
            for joined in verdict:
                for reason in joined.split(RS):
                    say(f"  - {reason}")
            say("")
            say("These are the pre-deploy gates from .crew/verify.json. Fix them, or set")
            say("verifyGate:false in .crew/config.json if this repo should not be gated.")
            raise Stop(2)
        # Allowed. Record that a deploy happened so the Stop gate can insist on a
        # PROMOTIONS row - a deploy nobody wrote down is a deploy nobody can audit.
        os.makedirs(".crew", exist_ok=True)
        with open(".crew/.deploy-in-flight", "w", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{self.envname} {self.sha}\n")
        return 0


def committed_as_is(blob):
    """Check 3 of the fast path: the map's bytes, or its bytes with every CRLF
    made LF (a `core.autocrlf` checkout), hash to HEAD's blob."""
    import hashlib  # pylint: disable=import-outside-toplevel
    with open(MAP, "rb") as handle:
        data = handle.read()
    algo = "sha1" if len(blob) == 40 else "sha256"

    def blob_id(body):
        digest = hashlib.new(algo)
        digest.update(b"blob %d\0" % len(body))
        digest.update(body)
        return digest.hexdigest()
    return blob in (blob_id(data), blob_id(data.replace(b"\r\n", b"\n")))


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", newline="\n")
        except (AttributeError, ValueError):
            pass
    gate = Gate()
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        return gate.run(raw)
    except Stop as stop:
        return stop.code
    except SystemExit:
        # An imported helper ended the interpreter on its own (a broken or replaced
        # one). Letting its status through could be a 0, an allow nobody decided.
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
