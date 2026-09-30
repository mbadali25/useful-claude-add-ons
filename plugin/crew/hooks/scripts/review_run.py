"""Run one review round: reserve it, launch the reviewer, compute the verdict.

ORDER IS THE POINT. The round is reserved in the ledger (`review_ledger.
reserve`) BEFORE the reviewer process is started, so a reviewer that crashes,
hangs, or takes this process down with it has still spent its round.
`test_review_ledger.py` kills this process from inside a fake reviewer and
asserts the round is on the ledger.

PROVIDERS.
  codex    `codex exec --json --sandbox read-only`, stdin closed (a real run
           hung here waiting on stdin). The final message and the turn's
           success are read from the JSON event stream; a failed turn is
           INCOMPLETE even when the process exited 0. `--model` and
           `--effort` pass through from config, and nothing is passed when
           they are empty.
  copilot  `copilot -p ... --deny-tool write --deny-tool shell -s`, stdin closed.
  kimi     `kimi -p ... -m <alias> --output-format stream-json --agent-file
           <scratch>/kimi-reviewer.md --skills-dir <scratch>/kimi-no-skills`,
           stdin closed, env from `kimi_probe.kimi_env` (no infinite retry, no
           KIMI_MODEL_* overrides). `kimi_probe.probe` runs BEFORE the round
           is reserved: any state but `ok` exits 2, names the state, and
           spends nothing. When the ledger's status already shows no round
           left, the run exits 4 before any probe or reservation: a Kimi
           round is never reserved unprobed. Prompt mode
           FORCES Kimi's permission mode to `auto` (2.1.1 refuses `-p` with
           --plan/--auto/--yolo), so no flag makes it read-only. Two controls
           stand in, for the probe call as for the review: the agent file
           allows Read, Grep and Glob and disallows Write, Edit and Bash, and
           the working tree is fingerprinted BEFORE THE PROBE and after the
           review exits. A tree that cannot be fingerprinted before the probe
           exits 2 (`unknown`) with no probe request and no round spent. A
           probe that changed it, whatever it answered, exits 8
           (EXIT_PROBE_CHANGED) naming the paths, with no round spent; a
           review that changed it is INCOMPLETE, naming the paths. Each call runs in a
           process group of its own, and whatever it leaves running there
           after it exits is killed before the tree is fingerprinted
           (`stop_survivors`); one that cannot be stopped is "could not tell".
           See `tree_fingerprint` and `reviewer_changes` for what is and is
           not seen. A write OUTSIDE the repository is caught by neither. The
           final message is read from the stream
           (`review_verdict.kimi_final_message`); its error text is redacted
           before it becomes a reason.
  claude   the `reviewer` subagent runs inside the Claude session, not as a
           process this script can launch. So it is two calls: `--reserve-only`
           before the subagent is dispatched, then `--round N --output FILE
           --exit-code 0` after, which refuses a round that was not reserved or
           already has a result.

A provider binary that is not on PATH is refused BEFORE reservation: nothing
was launched, so nothing is spent.

`--probe` (codex only) makes one minimal real call and reserves nothing: exit
0 ok, 5 limited (a usage/rate/quota limit, `review_limit.limit_line`), 6
failed, 7 unknown (timed out). /crew:review runs it before step 2a. Being on
PATH is not being able to review: a logged-out or rate-limited Codex resolves
on PATH and fails at the first call (T-0088).

The prompt is passed inline when it fits a Windows command line; otherwise the
argument tells the reviewer to read `prompt.txt`, and says so on stderr.

Before the verdict, every bundle part is re-read and checked against the
manifest's size and sha256 for it, and the parts together against
`bundle_sha256`, and their byte total against `patch_bytes`. A manifest
with no parts, or a part that is missing, truncated or altered, makes the round
INCOMPLETE: the receipt binds the manifest's hash, so without this check a
reviewer could have read an emptied part while the receipt still vouched for
the untouched tree.

Writes `<work-dir>/review.json` (default `.work/tickets/<id>/review.json`)
and records the round in the ledger; a CLEAN round writes the receipt.

WEB TESTS. In a Playwright repository (the manifest carries a `webtest`
listing) or wherever `.work/tickets/<id>/webtest/findings.json` exists, the
healer-skip check is RE-RUN here, before the verdict, stamped with the
manifest's head and bundle sha256 -- a findings file computed for an older
tree must never vouch for this one. `webtest_check` in review.json records
whether the file it replaced was missing, stale (another head or bundle) or
current. The review is INCOMPLETE when HEAD or the working tree no longer
matches the bundle (the findings would describe a different tree) or when
the check could not tell. `webtest_findings` is the open (unexcluded) rows,
None when the check does not apply; any open row makes a CLEAN verdict
FINDINGS, named in `webtest_verdict`, because a healer skip is a finding
whether or not the reviewer carried it. When the prompt overflowed its inline
rows into `webtest-findings.txt` in the scratch directory, that file is an
expected READ like a bundle part.

BEFORE ANY ROUND IS RESERVED, two questions, in this order (`preflight`):

  1. Does a CLEAN receipt already cover this exact bundle
     (`review_ledger.check_receipt`, the check `/crew:done` gates on)? Then
     nothing has changed since a clean review, so no round is spent: the
     verdict is that receipt's CLEAN, said as such. An owner-accepted
     FINDINGS receipt does not short-circuit -- that is a person's call about
     one round, not a clean review of the tree.
  2. Has the verify gate passed on this tree (`review_gate.gate_state`)? A
     tree it has not passed, or one whose state could not be read, is refused
     with exit 5 and no round spent: a reviewer's opinion on code the gate
     would refuse for free is the most expensive way to find out it is red.
     `--allow-unverified` reviews it anyway, and review.json says it did.
     No verify map, or a gate stood down, proceeds and says so.

Every round's review.json carries `gate` (the state observed at verdict time)
and `elapsed_s` (reservation to verdict, from the ledger's own timestamps), and
the `review:` summary line prints both.

Exit codes: 0 CLEAN; 1 FINDINGS; 3 INCOMPLETE; 4 budget refused
(NEEDS_REPLAN, or no round left per the status, before a Kimi probe); 5 not
run, gate not green (no round spent); 2 usage or setup error; 8 the Kimi probe
changed the working tree (stop and report the named paths; do not walk to the
next provider).
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time

import crew_common
import crew_freshness
import crew_state
import kimi_probe
import review_gate
import review_ledger
import review_limit
import review_patch
import review_prompt
import review_verdict
import webtest_guard

EXIT_CLEAN, EXIT_FINDINGS, EXIT_USAGE, EXIT_INCOMPLETE, EXIT_REFUSED = 0, 1, 2, 3, 4
EXIT_UNVERIFIED = 5
# The Kimi probe changed the working tree (round 4 of T-0028). 8 is the next
# code after T-0088's --probe exits 5-7, so it is never EXIT_UNVERIFIED's 5,
# which `run` also returns. No round was reserved, but the tree is no longer
# the one the bundle was built from, so /crew:review stops and reports the
# named paths -- it must never walk on to the next provider, as it does on
# EXIT_USAGE.
EXIT_PROBE_CHANGED = 8
DEFAULT_TIMEOUT = 1800
# Bound on the follow-up `communicate()` after a kill, below. Not the same
# knob as --timeout: this one exists so a descendant that escaped the kill
# (still holding the pipe open) cannot itself defeat --timeout by keeping
# this call blocked - see `launch`'s own comment for the full reproduction.
POST_KILL_TIMEOUT = 5
# Windows' CreateProcess limit is 32767 characters for the whole command line.
INLINE_PROMPT_LIMIT = 24000
LAUNCHED = ("codex", "copilot", "kimi")
KIMI_TREE_CHANGED = ("kimi: the working tree changed during the review - a reviewer "
                     "that can write may have fixed instead of reported")
KIMI_PROBE_CHANGED = "kimi probe: the working tree changed while the probe ran"
# Named paths per reason; the rest are counted, so a mass write cannot bury
# the review.json it is reported in.
CHANGED_SHOWN = 10
# `git status --ignored` walks every ignored file (node_modules and all), so
# it gets longer than crew_common's 10s hook-path bound. A git that still does
# not answer is "could not tell", never a hang after the round is reserved.
SNAPSHOT_GIT_TIMEOUT = 120
KIMI_TREE_UNKNOWN = ("kimi: the working tree could not be fingerprinted, so a write by the "
                     "reviewer cannot be ruled out")
KIMI_SURVIVOR_UNKNOWN = ("kimi: a process the reviewer left running could not be stopped, so "
                         "a write after the check cannot be ruled out")
# What `reviewer_changes` sets aside when it is IGNORED both before and after:
# paths something other than the reviewer writes mid-review AND that no check
# crew runs reads back. Fixed on purpose -- never read from config the reviewer
# could write -- and pinned by
# test_review_run_kimi.py::test_set_aside_names_are_the_fixed_tuples.
#   IDE_DIRS      an editor's own state: a directory of that name, any depth.
#   CREW_LOGS     appended by crew's hooks in the DISPATCHING session:
#                 `.crew/guard.log` by the scope, role-write and cloud guards
#                 (crew_guards.py:313, crew_config.py:1074), and
#                 `.crew/.autoclear.log` by auto-clear and context-watch
#                 (crew_autocycle.py:205, context-watch.sh:96). A Kimi review
#                 longer than the Bash tool's cap runs in the background, so
#                 those hooks fire mid-review (round 3 of T-0028).
#   CREW_MARKERS  context-watch's `.crew/.handoff-requested` and
#                 `.crew/.autoclear-sent`, bare or `-<session key>`
#                 (context-watch.sh:59-60), written the same way.
IDE_DIRS = (".idea", ".vscode")
CREW_LOGS = (".crew/guard.log", ".crew/.autoclear.log")
CREW_MARKERS = (".crew/.handoff-requested", ".crew/.autoclear-sent")
# `-c` settings on every fingerprint git call; a `-c` beats every config file.
# `core.fsmonitor` would otherwise run whatever program `.git/config` names --
# which the fingerprint does not hash -- and take its word for what changed
# (judgement, not measured). Tracked files do not rely on git's answer at all:
# every one is hashed (see `tree_fingerprint`).
GIT_OVERRIDES = ("-c", "core.fsmonitor=false")
# A nested repository is fingerprinted by recursion, and a symlink is followed
# to what it resolves to; deeper than this is "could not tell".
NESTED_DEPTH = 8
# The fingerprint's own entries. A NUL cannot occur in a git path, so no file
# can collide with them (round 4 of T-0028: tracked files named `:HEAD` and
# `:index` were never hashed, because those were the keys).
HEAD_KEY, INDEX_KEY = "\0HEAD", "\0index"
_META_SHOWN = {HEAD_KEY: "(HEAD)", INDEX_KEY: "(the index)"}
# Opening a regular file never blocks and never follows a link swapped in
# after the lstat (round 4: a FIFO blocked the walk with no deadline).
_READ_FLAGS = (os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
               | getattr(os, "O_BINARY", 0))
# What graph.out may hold as a TRACKED file and still be set aside.
GRAPH_FILES = ("graph.json", "GRAPH_REPORT.md")
# Crew config: a reviewer write here always counts, even under graph.out -- it
# is where graph.out itself is configured.
CREW_CONFIG_PATHS = (".crew/crew.json", ".crew/config.json")
# The probe (T-0088): one minimal real Codex call, before any reservation.
PROBE_TIMEOUT = 120
PROBE_PROMPT = "Reply with exactly the word OK. Do not run any command and do not read any file."
EXIT_PROBE_LIMITED, EXIT_PROBE_FAILED, EXIT_PROBE_UNKNOWN = 5, 6, 7
PROBE_OK, PROBE_LIMITED, PROBE_FAILED, PROBE_UNKNOWN = "ok", "limited", "failed", "unknown"
VERIFY_GATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify-gate.sh")


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _decode_partial(value):
    """CPython raises `TimeoutExpired` from INSIDE the read loop, before the
    text-mode translation `Popen.communicate` normally applies -- so
    `exc.output`/`exc.stderr` on a `communicate(timeout=...)` timeout are
    raw bytes even though this `Popen` was constructed with `text=True`,
    never the decoded str every other return path here already is. Decoded
    with the same utf-8/replace policy the Popen itself uses, so a partial
    capture from a second, bounded timeout is usable text rather than either
    bytes leaking into a str-typed return or silently discarded."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _write_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def prompt_argument(prompt_path):
    text = _read(prompt_path)
    if len(text) <= INLINE_PROMPT_LIMIT:
        return text
    sys.stderr.write(f"review-run: prompt is {len(text)} chars, over the inline limit; "
                     f"the reviewer is told to read {prompt_path}\n")
    return (f"Your complete instructions are in the file {prompt_path}. Read that file in "
            "full first and follow it exactly; it is the whole task.")


def _git_bytes(root, args, env):
    """Raw stdout of one git call, or None when git failed, could not start,
    or did not answer within SNAPSHOT_GIT_TIMEOUT."""
    try:
        done = subprocess.run(["git", *GIT_OVERRIDES, *args], cwd=root, env=env,
                              capture_output=True,
                              stdin=subprocess.DEVNULL, timeout=SNAPSHOT_GIT_TIMEOUT,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _inside(real, top):
    """True when the resolved `real` lies strictly inside the resolved `top`."""
    try:
        return real != top and os.path.commonpath([real, top]) == top
    except ValueError:  # another drive on Windows
        return False


def _link_digest(path, root, depth):
    """`link:<target>` and, after a NUL, the digest of what the link resolves
    to (round 4 of T-0028: a tracked link into ignored IDE state let its
    target change unseen, because only the target STRING was hashed): a
    regular file's content and mode, a directory inside `root` walked,
    `missing` when it dangles. None -- could not tell -- for a directory
    outside `root` (or with no `root` to check it against), or past
    NESTED_DEPTH links."""
    target = os.readlink(path)
    if depth >= NESTED_DEPTH:
        return None
    try:
        info = os.stat(path)
    except FileNotFoundError:
        return f"link:{target}\0missing"
    real = os.path.realpath(path)
    if stat.S_ISDIR(info.st_mode):
        if not root or not _inside(real, os.path.realpath(root)):
            return None
        resolved = _walk_digest(real, root, depth + 1)
    else:
        resolved = _path_digest(real, root, depth + 1)
    return None if resolved is None else f"link:{target}\0{resolved}"


def _path_digest(path, root=None, _depth=0):
    """What is at `path` now, never opening anything but a regular file:

      a regular file  `<content sha256>:<permission bits, octal>` -- the bits
                      so a chmod counts even where core.filemode=false hides
                      it from git (round 4 of T-0028)
      a symlink       `_link_digest`: its target and what it resolves to
      a directory     `dir`
      anything else   `special:<S_IFMT, octal>` -- a FIFO, socket or device is
                      recorded from `lstat` and never opened, so a FIFO cannot
                      block the walk (round 4)
      nothing there   `missing`

    None when it exists and cannot be read: an unreadable file is "could not
    tell", and two of those must not compare equal as "unchanged"."""
    try:
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode):
            return _link_digest(path, root, _depth)
        if stat.S_ISDIR(mode):
            return "dir"
        if not stat.S_ISREG(mode):
            return f"special:{stat.S_IFMT(mode):o}"
        fd = os.open(path, _READ_FLAGS)
        with os.fdopen(fd, "rb") as fh:
            opened = os.fstat(fh.fileno()).st_mode
            if not stat.S_ISREG(opened):
                return f"special:{stat.S_IFMT(opened):o}"
            digest = hashlib.sha256()
            for block in iter(lambda: fh.read(1 << 20), b""):
                digest.update(block)
        return f"{digest.hexdigest()}:{stat.S_IMODE(opened):o}"
    except FileNotFoundError:
        return "missing"
    except OSError:
        return None


def _walk_digest(path, root=None, _depth=0):
    """A directory's contents, walked without following a symlink: a sha256
    over each entry's relative path and `_path_digest` (so a link inside is
    digested with what it resolves to). None when an entry cannot be read or
    the walk itself fails."""
    rows, failed = [], []
    for top, dirs, files in os.walk(path, onerror=failed.append):
        dirs.sort()
        for name in sorted(dirs + files):
            full = os.path.join(top, name)
            digest = _path_digest(full, root, _depth)
            if digest is None:
                return None
            rows.append(f"{os.path.relpath(full, path)}\0{digest}")
    if failed:
        return None
    return "walk:" + hashlib.sha256("\n".join(rows).encode("utf-8", "surrogateescape")).hexdigest()


def _entry_digest(root, rel, problems, depth):
    """`_path_digest` for one listed path, except that a DIRECTORY is never the
    constant `dir` (round 3 of T-0028: a dirty submodule, or a nested clone,
    stayed `dir` whatever changed inside it). A directory holding `.git` is
    fingerprinted as the repository it is -- when git agrees it is one rooted
    there -- and any other directory (an uninitialised submodule, whose files
    no `git status` mode lists) is walked."""
    path = os.path.join(root, rel)
    digest = _path_digest(path, root)
    if digest != "dir":
        return digest
    if not os.path.lexists(os.path.join(path, ".git")):
        return _walk_digest(path, root)
    top = crew_common.git_out(path, "rev-parse", "--show-toplevel")
    if depth >= NESTED_DEPTH or not top or \
            os.path.normcase(os.path.realpath(top)) != os.path.normcase(os.path.realpath(path)):
        if problems is not None:
            problems.append(f"{rel} holds a .git that is not a repository rooted there, "
                            f"or is nested more than {NESTED_DEPTH} deep")
        return None
    inner = tree_fingerprint(path, problems, _depth=depth + 1)
    if inner is None:
        return None
    return "repo:" + hashlib.sha256(json.dumps(inner, sort_keys=True).encode(
        "utf-8", "surrogateescape")).hexdigest()


def tree_fingerprint(root, problems=None, _depth=0):
    """The working tree's state as `{path: "<XY> <digest>"}` (`_path_digest`:
    content and mode bits, a link with its target, a special file never
    opened), plus HEAD_KEY and INDEX_KEY -- or None when it cannot be taken.

    EVERY TRACKED FILE is in it, contents hashed, whatever `git status` says
    of it (`git ls-files --stage`, code `--` when status did not list it).
    Round 3 of T-0028 found an edit to a tracked file flagged skip-worktree or
    assume-unchanged unseen, and (measured) so was a same-size rewrite that
    restores the mtime once `.git/config` sets core.trustctime=false or
    core.checkStat=minimal: git answered "clean" and nothing re-read the file.
    Every path `git status` lists is in it too, CONTENTS hashed: modified,
    untracked and IGNORED files alike (`--untracked-files=all
    --ignored=traditional` lists each file inside an ignored directory, not
    the directory; `--no-renames` keeps each entry one path). Round 1 found
    the earlier digest hashed only an untracked file's status LINE and skipped
    ignored files. A directory is fingerprinted as the nested repository or
    submodule it is, or walked (`_entry_digest`). HEAD_KEY is there so a
    reviewer that COMMITTED its edit is seen, INDEX_KEY (every staged entry,
    blob id included) so one that only staged is; both hold a NUL, so no path
    can collide with them (round 4). `.work/` is excluded at the
    top level -- the scratch directory, review.json and the handoff live
    there. Taken with GIT_OPTIONAL_LOCKS=0 so taking it cannot itself change
    the index.

    NOT SEEN: a write outside the repository, and a change inside `.git`
    other than HEAD and the index (a hook, a config). None when any git call
    fails or times out, or a listed file cannot be read: "could not tell" is
    its own answer, never a value two failures would compare equal on. When
    `problems` is a list, the reason for a None is appended to it."""
    def unknown(reason):
        if problems is not None:
            problems.append(reason)

    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    head = crew_common.git_out(root, "rev-parse", "HEAD")
    if not head and _depth and crew_common.git_out(root, "rev-parse", "--git-dir"):
        head = "unborn"  # a nested repository with no commit yet
    if not head:
        unknown("HEAD could not be read (not a git repository?)")
        return None
    scope = ["--", "."] if _depth else ["--", ".", ":(exclude).work"]
    status = _git_bytes(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all",
                               "--no-renames",
                               "--ignored=traditional", *scope], env)
    staged = _git_bytes(root, ["ls-files", "--stage", "-z", *scope], env)
    if status is None or staged is None:
        unknown("git status or git ls-files failed or timed out")
        return None
    snapshot = {HEAD_KEY: head, INDEX_KEY: hashlib.sha256(staged).hexdigest()}
    listed = [(entry[:2].decode("ascii", "replace"), entry[3:])
              for entry in status.split(b"\0") if len(entry) >= 4]
    listed += [("--", entry.split(b"\t", 1)[1]) for entry in staged.split(b"\0")
               if b"\t" in entry]
    seen = set()
    for code, raw in listed:
        rel = os.fsdecode(raw).rstrip("/")
        if rel in seen:
            continue  # status listed it first, with its code
        seen.add(rel)
        digest = _entry_digest(root, rel, problems, _depth)
        if digest is None:
            unknown(f"{rel} exists and cannot be read")
            return None
        snapshot[rel] = f"{code} {digest}"
    return snapshot


def graph_out(root):
    """`graph.out` as a repo-relative, `/`-separated directory, or None.

    Resolved the way `crew_freshness._read_graph` and `crew_refresh_check`
    resolve it: `crew.json`, else `config.json`, in the `.crew/` that
    `crew_common.repo_config_dir` names -- so a linked lane worktree with no
    config of its own reads the main checkout's -- and None when that
    resolver answers `unknown` (nothing set aside); a missing or
    wrong-typed value is `graphify-out`; `contained_path` keeps it inside the
    repository. None when it lands on the root or in `.git`, or a symlink
    moves it -- an exemption for one generated directory must never widen to
    the tree. None too, since round 4 of T-0028, when the directory could
    hold a check input: it is `.crew` or lies under a `.crew`, it contains a
    `.crew`, or it holds a tracked file other than GRAPH_FILES (read with
    `git ls-files` beside the "before" fingerprint; a git that does not answer
    is None as well). graph.out set to `.crew` had excused a rewrite of
    `.crew/verify.json`."""
    top = os.path.realpath(root)
    crew_dir, source, _detail = crew_common.repo_config_dir(top)
    if source == crew_common.SOURCE_UNKNOWN:
        return None
    cfg = {}
    for name in crew_common.CONFIG_NAMES:
        text = crew_common.read_text(os.path.join(crew_dir, name))
        if text is None:
            continue
        try:
            cfg = json.loads(text)
        except ValueError:
            cfg = {}
        break
    value = crew_common.dict_or_empty(crew_common.dict_or_empty(cfg).get("graph")).get("out")
    if not isinstance(value, str) or not value:
        value = crew_freshness.GRAPH_OUT_DEFAULT
    real = crew_freshness.contained_path(top, value, crew_freshness.GRAPH_OUT_DEFAULT)
    named = {os.path.normcase(os.path.normpath(os.path.join(top, v)))
             for v in (value, crew_freshness.GRAPH_OUT_DEFAULT)}
    if os.path.normcase(real) not in named:
        return None
    rel = os.path.relpath(real, top).replace("\\", "/")
    if rel in ("", ".") or rel.split("/", 1)[0] in ("..", ".git"):
        return None
    if ".crew" in rel.split("/"):
        return None
    for _dir, dirs, _files in os.walk(real):
        if ".crew" in dirs:
            return None
    tracked = _git_bytes(top, ["ls-files", "-z", "--", ":(literal)" + rel],
                         dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    if tracked is None or any(os.fsdecode(name) not in (f"{rel}/{f}" for f in GRAPH_FILES)
                              for name in tracked.split(b"\0") if name):
        return None
    return rel


def _under(rel, directory):
    """True when `rel` lies strictly under `directory`, segment by segment:
    `graphify-outX/a` is not under `graphify-out`."""
    parts, stem = rel.split("/"), directory.split("/")
    return len(parts) > len(stem) and parts[:len(stem)] == stem


def _not_a_check_input(rel):
    """True when `rel` is one of the paths `reviewer_changes` may set aside:
    strictly under an IDE_DIRS directory, matched by whole segment at any depth
    (`pkg/.idea/x` is, `my.idea/x` and a bare `.idea` are not); exactly one of
    CREW_LOGS; or a CREW_MARKERS name, bare or with a `-<session key>` that
    holds no `/`."""
    parts = rel.split("/")
    if any(part in IDE_DIRS for part in parts[:-1]):
        return True
    if rel in CREW_LOGS or rel in CREW_MARKERS:
        return True
    return any(rel.startswith(marker + "-") and "/" not in rel[len(marker) + 1:]
               for marker in CREW_MARKERS)


def _ignored_throughout(before, after, rel):
    """True when every state `rel` has in the two fingerprints is IGNORED
    (`!!`); a path that was or became tracked or untracked is not."""
    states = [s for s in (before.get(rel), after.get(rel)) if s is not None]
    return bool(states) and all(s.startswith("!! ") for s in states)


def reviewer_changes(before, after, graph):
    """(changed, set_aside): the paths whose state differs between two
    `tree_fingerprint`s, split into those the reviewer is answerable for and
    those set aside -- under `graph`, or ignored throughout and
    `_not_a_check_input`.

    `graph` is graph.out as resolved BEFORE the reviewer ran (`run` does it
    once, beside the "before" fingerprint). Round 2 of T-0028 found it read
    after the review, from the tree the reviewer could write: writing
    `.crew/crew.json` = {"graph":{"out":".crew"}} then excused every other
    write under `.crew/`. `.crew/crew.json` and `.crew/config.json`
    (CREW_CONFIG_PATHS) are never set aside, whatever `graph` is.

    WHAT ELSE IS SET ASIDE, AND WHAT IS NOT. The fingerprint hashes ignored
    files (round 1), so any other writer to an ignored path spends the round.
    A path is set aside only when it is IGNORED in both fingerprints (a path
    that was or became tracked or untracked -- `.git/info/exclude` is not
    hashed, so a reviewer can flip it -- counts) AND no check crew runs reads
    it back: an IDE's own directory, crew's hook logs and context markers
    (IDE_DIRS, CREW_LOGS, CREW_MARKERS; round 3). Tool caches are NOT set
    aside, whatever round 2 did: CPython runs a `__pycache__` .pyc whose header
    matches its source, so a write there changes what the tests execute
    (round 3), and every other cache has the same shape -- `.pytest_cache`
    steers `--lf`/`--sw`, ruff and mypy trust a cached verdict, a bundler's
    `node_modules/.cache` holds output it runs. The cost is smaller than
    round 2 feared, measured: a second pytest run over an unchanged tree
    rewrote no byte under `__pycache__/` or `.pytest_cache/`, and only a
    CONTENT change counts. Nor are crew's gate inputs set aside
    (`.crew/.verify-verified-at`, `.verify-gate.fingerprint`, `.record.json`,
    `.timings.json`, `.scope-base`): a forged one narrows the verify gate. The
    verify gate rewrites its marker on every clean Stop, but at an unchanged
    HEAD with the same sha, which is no change (judgement from verify-gate.sh
    :122 and its fingerprint skip; not measured end to end).

    WHY `graph.out` IS SET ASIDE, and nothing else. graphify's post-commit and
    post-checkout hooks rebuild it IN THE BACKGROUND, and the normal order is
    commit, then review -- so the rebuild routinely lands mid-review and spent
    the round as INCOMPLETE with no reviewer write at all (round 1 of
    T-0028). Waiting for the rebuild instead was rejected: the hooks are
    machine-local (`.git/hooks` is untracked), write no lock and no pid
    crew could wait on, and build first and write last, so a quiet tree before
    launch proves nothing. Setting the directory aside is safe for the one
    thing this fingerprint exists for -- a reviewer that FIXED instead of
    reported: graph.out is generated, holds no code under review, and is
    overwritten by the next rebuild, so a write there fixes nothing. Every
    other path, the code map and the diagrams included, still counts, and
    HEAD_KEY and INDEX_KEY always do. `graph_out` refuses a directory that
    could hold a check input (round 4)."""
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    set_aside = []
    for path in changed:
        if path in (HEAD_KEY, INDEX_KEY) or path in CREW_CONFIG_PATHS:
            continue
        if graph and _under(path, graph):
            set_aside.append(path)
        elif _ignored_throughout(before, after, path) and _not_a_check_input(path):
            set_aside.append(path)
    return [p for p in changed if p not in set_aside], set_aside


def _named(paths):
    shown = ", ".join(_META_SHOWN.get(p, p) for p in paths[:CHANGED_SHOWN])
    more = len(paths) - CHANGED_SHOWN
    return shown + (f" and {more} more" if more > 0 else "")


def _round_available(root, ticket):
    """False when the ledger already shows the next reservation will be
    refused -- no round left, NEEDS_REPLAN, or unreadable. A read without the
    lock, so it only ever skips work `reserve` would refuse; `reserve` stays
    the authority either way."""
    status = review_ledger.status(root, ticket)
    return (status.get("state") not in (review_ledger.NEEDS_REPLAN, review_ledger.UNKNOWN)
            and status.get("rounds_left", 0) > 0)


def command_for(provider, exe, root, prompt, model, effort, scratch=None):
    if provider == "kimi":
        return [exe, "-p", prompt, "-m", model, "--output-format", "stream-json",
                *kimi_probe.read_only_flags(scratch)]
    if provider == "codex":
        cmd = [exe, "exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check",
               "-C", root]
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["-c", f"model_reasoning_effort={effort}"]
        return cmd + [prompt]
    return [exe, "-p", prompt, "--model", model, "--deny-tool", "write",
            "--deny-tool", "shell", "-s"]


def launch(cmd, root, timeout, env=None, started=None):
    """(stdout, stderr, exit_code, timed_out). stdin is always closed. When
    `started` is a list, the leader's pid -- its process group's id on POSIX
    -- is appended to it once the process exists (see `stop_survivors`).

    Spawned in its own process group/session so a timeout can kill the whole
    tree, not just the direct child. A provider CLI installed as an npm
    `.cmd` shim on Windows runs as `cmd.exe /c <shim>`, with the real work in
    a grandchild -- a bare `Popen.kill()` (what a plain `subprocess.run(...,
    timeout=...)` does on `TimeoutExpired`) only reaches `cmd.exe`. Left
    un-reaped, that grandchild keeps this process's stdout pipe open past the
    kill, and reading it blocks well past `timeout` -- observed as the
    caller's own outer safety timeout firing instead of this one.

    BLOCK (Codex): the leader's pid/pgid is only safe to signal by bare
    number while the leader is STILL ALIVE AND UNREAPED -- once `proc.poll()`
    shows it has exited, that number is free for the OS to hand to a brand
    new, entirely unrelated process, and `os.killpg(proc.pid, ...)` at that
    point can reach whatever the OS gave it to next instead of anything this
    process started. `proc.poll()` is checked immediately before either the
    POSIX `killpg` or the Windows `taskkill` -- both by pid -- and skipped
    entirely when the leader has already exited; a provider that forks a
    detached grandchild (`setsid sh -c '...' &`) and exits itself is exactly
    that shape, and is left alone here rather than guessed at.

    BLOCK (Codex): the follow-up `communicate()` after a kill used to carry
    no timeout of its own, so a descendant that escaped the kill (still
    holding the stdout/stderr pipe open -- the leader-already-exited case
    above is exactly when this can happen) kept it blocked past --timeout
    with nothing bounding the wait. Reproduced with a provider that runs
    `setsid sh -c "sleep 60" &` and exits: the leader is gone before this
    function ever gets to kill anything, the grandchild keeps sleeping and
    keeps the pipe open, and an unbounded second `communicate()` returns only
    after the full sleep. Bounded by `POST_KILL_TIMEOUT`; on a second
    `TimeoutExpired`, CPython's own exception already carries whatever bytes
    were read before that bound (`exc.output`/`exc.stderr`), so this keeps
    and decodes that partial capture (`_decode_partial`) rather than
    discarding it -- an earlier version of this fix threw the partial output
    away and closed the process's own stdout/stderr streams to unblock
    itself; on Windows, closing a pipe still being read by CPython's own
    reader thread for that stream can itself block, trading one hang for
    another. Reports the run as timed out either way, with whatever output
    had already arrived, rather than waiting on a descendant that is not
    coming back.
    """
    popen_kwargs = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            cmd, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            env=env, **popen_kwargs)
    except OSError as exc:
        return "", f"could not start {cmd[0]}: {exc}", None, False
    if started is not None:
        started.append(proc.pid)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        escaped = False
        if proc.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                               capture_output=True, timeout=30, check=False)
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        else:
            # Leader already exited and been reaped: its pid (and any pgid
            # numbered the same) is free for reuse, so no bare-number signal
            # is safe here. Whatever kept the pipe open is on its own.
            escaped = True
        try:
            stdout, stderr = proc.communicate(timeout=POST_KILL_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            escaped = True
            stdout = _decode_partial(exc.output)
            stderr = _decode_partial(exc.stderr)
        if escaped:
            stderr = (stderr or "") + (
                "\nreview-run: a descendant process may have escaped the "
                f"{timeout}s timeout and is still holding the output pipe "
                "open; proceeding with whatever output had already arrived\n")
        return stdout, stderr, None, True
    return stdout, stderr, proc.returncode, False


def _group_alive(pgid):
    """True when a process that is not a zombie is still in process group
    `pgid`. Read from /proc where there is one -- a zombie is dead but still
    answers signal 0 until something reaps it -- else signal 0."""
    if os.path.isdir("/proc/self"):
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                with open(f"/proc/{name}/stat", encoding="ascii", errors="replace") as fh:
                    fields = fh.read().rsplit(")", 1)[1].split()
            except (OSError, IndexError):
                continue
            if len(fields) > 2 and fields[2] == str(pgid) and fields[0] not in ("Z", "X"):
                return True
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # round 4 of T-0028: a member we may not signal is alive
    return True


def stop_survivors(started):
    """After a leader `launch` saw exit normally: SIGKILL whatever it left
    running in its process group and wait for the group to empty, so nothing
    it started can write after the "after" fingerprint (round 3 of T-0028: a
    backgrounded `sleep 2; echo fix >> seed.txt` landed after a CLEAN round).

    (killed, unknown_reason); a kill refused with PermissionError is
    (False, KIMI_SURVIVOR_UNKNOWN). The group is signalled only after `_group_alive`
    has just found a live member: while a group has members its id is not
    handed to a new process, so the bare number still names this group --
    the hazard `launch`'s timeout path guards against is a group that has
    already emptied. NOT SEEN: a descendant that left the group (`setsid`),
    and anything on Windows, where no group is probed at all."""
    if not started or os.name == "nt" or not _group_alive(started[0]):
        return False, None
    try:
        os.killpg(started[0], signal.SIGKILL)
    except ProcessLookupError:
        return False, None  # the group emptied between the probe and the kill
    except PermissionError:
        # Round 4 of T-0028: a member we may not signal is not "no survivor".
        return False, KIMI_SURVIVOR_UNKNOWN
    deadline = time.monotonic() + POST_KILL_TIMEOUT
    while _group_alive(started[0]):
        if time.monotonic() >= deadline:
            return True, KIMI_SURVIVOR_UNKNOWN
        time.sleep(0.05)
    return True, None


def bundle_problems(manifest):
    """Reasons the part files on disk are not the bundle the manifest
    describes; empty when every part matches its recorded size and sha256
    and the parts together hash to `bundle_sha256`."""
    rows = manifest.get("parts")
    if not isinstance(rows, list) or not rows:
        return ["the manifest lists no bundle parts, so there is nothing the reviewer "
                "can be shown to have read"]
    problems = []
    whole = hashlib.sha256()
    total = 0
    for row in rows:
        try:
            with open(row["path"], "rb") as fh:
                data = fh.read()
        except (OSError, KeyError, TypeError) as exc:
            problems.append(f"bundle part {row.get('name')} could not be read: {exc}")
            continue
        whole.update(data)
        total += len(data)
        if len(data) != row.get("bytes") or hashlib.sha256(data).hexdigest() != row.get(
                "sha256"):
            problems.append(f"bundle part {row.get('name')} is {len(data)} bytes and does "
                            f"not match its manifest entry ({row.get('bytes')} bytes)")
    if not problems and whole.hexdigest() != manifest.get("bundle_sha256"):
        problems.append("the bundle parts do not hash to the manifest's bundle_sha256")
    if not problems and total != manifest.get("patch_bytes"):
        problems.append(f"the bundle parts total {total} bytes, not the patch's "
                        f"{manifest.get('patch_bytes')}")
    return problems


def _findings_doc(root, ticket):
    try:
        doc = json.loads(_read(webtest_guard.findings_path(root, ticket)))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def webtest_findings(root, ticket):
    """The healer-skip rows not excused by the spec, from
    `webtest_guard.py skips`; None when that check never ran for the ticket."""
    rows = (_findings_doc(root, ticket) or {}).get("findings")
    if not isinstance(rows, list):
        return None
    return [r for r in rows if isinstance(r, dict) and not r.get("excluded")]


def webtest_check(root, ticket, manifest):
    """(open_rows_or_None, record_or_None, incomplete_reasons). Re-runs the
    healer-skip check for the tree the bundle was cut from; see WEB TESTS."""
    path = webtest_guard.findings_path(root, ticket)
    if manifest.get("webtest") is None and not os.path.exists(path):
        return None, None, []
    head, bundle = manifest.get("head"), manifest.get("bundle_sha256")
    prior = _findings_doc(root, ticket)
    state = ("missing" if prior is None else "current"
             if (prior.get("head"), prior.get("bundle_sha256")) == (head, bundle) else "stale")
    reasons = []
    now = crew_common.git_out(root, "rev-parse", "HEAD")
    if now != head:
        reasons.append(f"webtest: HEAD is {str(now)[:12]}, not the bundle's {str(head)[:12]}; "
                       "the healer-skip check cannot be tied to the reviewed tree")
    else:
        try:
            current = review_patch.compute(root, manifest.get("base") or "")[0]
        except RuntimeError as exc:
            current = {}
            reasons.append(f"webtest: the bundle could not be rebuilt to check it is current: {exc}")
        if current and current.get("bundle_sha256") != bundle:
            reasons.append("webtest: the working tree changed after the bundle was cut; the "
                           "healer-skip check cannot be tied to the reviewed tree")
    code, lines = webtest_guard.check_skips(root, ticket, bundle_sha256=None if reasons else bundle)
    if code == webtest_guard.EXIT_UNKNOWN:
        reasons.append(f"webtest: {lines[0]}")
    rows = webtest_findings(root, ticket) if code != webtest_guard.EXIT_UNKNOWN else None
    record = {"prior_findings": state, "rerun_exit": code, "head": now, "bundle_sha256": bundle}
    return rows, record, reasons


def finish(args, number, output, exit_code, timed_out, extra_reasons=()):
    """Verdict -> ledger -> review.json. Returns the process exit code."""
    manifest = json.loads(_read(args.manifest))
    # The parts as the prompt lists them -- full paths -- so a READ line that
    # echoes the listed path counts (T-0079). A part with no path falls back to
    # its name, which review_verdict still matches exactly.
    parts = [p.get("path") or p["name"] for p in manifest.get("parts") or []]
    if os.path.exists(os.path.join(args.scratch, review_prompt.WEBTEST_FINDINGS_FILE)):
        parts.append(os.path.join(args.scratch, review_prompt.WEBTEST_FINDINGS_FILE))
    rows, webtest_record, webtest_reasons = webtest_check(args.root, args.ticket, manifest)
    extra_reasons = list(extra_reasons) + bundle_problems(manifest)
    extra_reasons += webtest_reasons
    result = review_verdict.parse(output, exit_code, timed_out, parts)
    if extra_reasons:
        result["reasons"] = list(extra_reasons) + result["reasons"]
        result["verdict"] = review_verdict.INCOMPLETE
    webtest_verdict = None
    if rows:
        webtest_verdict = (f"{len(rows)} open healer skip(s) in webtest_findings; a healer skip "
                           "is a finding, never accepted, so this round is not CLEAN")
        if result["verdict"] == review_verdict.CLEAN:
            result["verdict"] = review_verdict.FINDINGS
    review = {
        "ticket": args.ticket, "round": number, "budget": review_ledger.BUDGET,
        "verdict": result["verdict"], "counts": result["counts"],
        "reasons": result["reasons"], "parts_expected": parts,
        "parts_missing": result["parts_missing"],
        "provider": args.provider, "model": args.model or None,
        "model_launched": getattr(args, "launched_model", None) or args.model or None,
        "model_family": crew_state.family(args.provider, args.model),
        "bundle_sha256": manifest.get("bundle_sha256"),
        "base": manifest.get("base"), "head": manifest.get("head"),
        "exit_code": exit_code, "timed_out": timed_out,
        "webtest_findings": rows, "webtest_check": webtest_record,
        "webtest_verdict": webtest_verdict,
        "gate": gate_record(args),
        "written_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"),
    }
    # Ledger first: it refuses a round that was never reserved or already
    # has a result, and a refused record must not leave a review.json behind.
    state = review_ledger.record(args.root, args.ticket, number, review)
    review["elapsed_s"] = round_elapsed(args.root, args.ticket, number)
    work_dir = args.work_dir or os.path.join(args.root, ".work", "tickets", args.ticket)
    _write_atomic(os.path.join(work_dir, "review.json"),
                  json.dumps(review, indent=2, sort_keys=True) + "\n")
    counts = result["counts"]
    print(f"review: {result['verdict']} round {number}/{review_ledger.BUDGET} "
          f"({counts['BLOCK']} BLOCK, {counts['FIX']} FIX, {counts['NIT']} NIT) "
          f"{args.provider}/{args.model or 'default'} family={review['model_family']} "
          f"ledger={state} gate={review['gate']['state']} "
          f"elapsed={_fmt_elapsed(review['elapsed_s'])}")
    for reason in result["reasons"]:
        print(f"review: INCOMPLETE because {reason}")
    if webtest_verdict:
        print(f"review: {result['verdict']} because {webtest_verdict}")
    return {review_verdict.CLEAN: EXIT_CLEAN, review_verdict.FINDINGS: EXIT_FINDINGS}.get(
        result["verdict"], EXIT_INCOMPLETE)


def _probe_runner(cmd, env, timeout, cwd):
    """`kimi_probe.probe`'s runner: `launch`, in a process group of its own,
    then `stop_survivors`, so the probe call cannot leave a writer running
    past the fingerprint taken after it. A survivor that could not be stopped
    answers as a call that never said PROBE_OK, which the probe reads as
    `unknown`."""
    started = []
    stdout, stderr, code, timed_out = launch(cmd, cwd, timeout, env=env, started=started)
    if not timed_out and stop_survivors(started)[1]:
        return "", KIMI_SURVIVOR_UNKNOWN, None, False
    return stdout, stderr, code, timed_out


def _probe_kimi(args, before):
    """Run the probe. None when the review may go on (the binary and alias it
    resolved are then `args.kimi_exe` and `args.launched_model`); otherwise
    (exit code, refusal message). The tree is fingerprinted after the probe
    WHATEVER it answered (round 4 of T-0028: a failing probe that wrote
    returned EXIT_USAGE, and /crew:review walked on to the next provider
    against a tree the probe had changed): a change is EXIT_PROBE_CHANGED."""
    probed = kimi_probe.probe(args.model or None, runner=_probe_runner)
    answer = f"kimi probe: {probed['state']} - {probed['reason']}"
    problems = []
    mid = tree_fingerprint(args.root, problems)
    if mid is None:
        # Round 3 NIT: this used to fall through as "clean" and reserve, so
        # the round was spent as INCOMPLETE when nothing had been launched.
        return EXIT_USAGE, (f"kimi probe: unknown - the tree could not be fingerprinted "
                            f"after the probe: {'; '.join(problems) or 'no reason given'} "
                            f"(the probe answered: {answer})")
    if before is not None:
        changed, _set_aside = reviewer_changes(before, mid, args.graph_out)
        if changed:
            return EXIT_PROBE_CHANGED, (f"{KIMI_PROBE_CHANGED}: {_named(changed)} (the probe "
                                        f"answered: {answer}); stop and report these paths, "
                                        "do not walk to the next provider")
    if not kimi_probe.launchable(probed["state"]):
        return EXIT_USAGE, answer
    args.kimi_exe, args.launched_model = probed["exe"], probed["alias"]
    return None


def _run_kimi(args, number, prompt, before):
    """Launch the reserved Kimi round and finish it."""
    extra = []
    cmd = command_for("kimi", args.kimi_exe, args.root, prompt, args.launched_model, "",
                      args.scratch)
    started = []
    stdout, stderr, code, timed_out = launch(cmd, args.root, args.timeout,
                                             env=kimi_probe.kimi_env(), started=started)
    killed, survivor_unknown = stop_survivors(started) if not timed_out else (False, None)
    if survivor_unknown:
        extra.append(survivor_unknown)
    elif killed:
        sys.stderr.write("review-run: kimi left processes running after it exited; they were "
                         "stopped before the tree was checked\n")
    after = tree_fingerprint(args.root)
    if before is None or after is None:
        extra.append(KIMI_TREE_UNKNOWN)
    else:
        changed, set_aside = reviewer_changes(before, after, args.graph_out)
        if changed:
            extra.append(f"{KIMI_TREE_CHANGED}: {_named(changed)}")
        if set_aside:
            sys.stderr.write(f"review-run: not counted against the reviewer, under graph.out "
                             f"(graphify's background rebuild), or ignored IDE state or crew "
                             f"hook logs: {_named(set_aside)}\n")
    _write_atomic(os.path.join(args.scratch, "kimi-events.jsonl"), stdout)
    message_text, error = review_verdict.kimi_final_message(stdout)
    output = message_text or ""
    if error and not timed_out:
        extra.append(f"kimi: {kimi_probe.redact(error)}")
    _write_atomic(os.path.join(args.scratch, "out.txt"), output)
    _write_atomic(os.path.join(args.scratch, "stderr.txt"), kimi_probe.redact(stderr))
    return finish(args, number, output, code, timed_out, extra)


def gate_record(args):
    """The gate state for review.json: observed now, plus whether this round
    was told to go ahead regardless."""
    state, reason = review_gate.gate_state(args.root)
    return {"state": state, "reason": reason,
            "overridden": bool(getattr(args, "allow_unverified", False))
            and state in (review_gate.UNVERIFIED, review_gate.UNKNOWN)}


def round_elapsed(root, ticket, number):
    """Seconds from the round's reservation to its recorded verdict, read from
    the ledger's own `reserved_at` / `completed_at`. None when either is
    missing or unparseable -- an unknown duration, never a zero one."""
    data, state = review_ledger._load(review_ledger.ledger_path(root, ticket))  # pylint: disable=protected-access
    if state != "ok":
        return None
    for row in data.get("rounds") or []:
        if isinstance(row, dict) and row.get("round") == number:
            try:
                start = datetime.datetime.fromisoformat(row["reserved_at"])
                end = datetime.datetime.fromisoformat(row["completed_at"])
            except (KeyError, TypeError, ValueError):
                return None
            return max(int((end - start).total_seconds()), 0)
    return None


def _fmt_elapsed(seconds):
    return "unknown" if seconds is None else f"{seconds}s"


def preflight(args):
    """None to go on and reserve a round, or the exit code to stop with
    having reserved nothing. See BEFORE ANY ROUND IS RESERVED above. For
    Kimi the probe has already run before these two questions, as Codex's
    `--probe` runs before its round (T-0028, owner 2026-09-30)."""
    ok, message = review_ledger.check_receipt(args.root, args.ticket)
    data, _ = review_ledger._load(review_ledger.ledger_path(args.root, args.ticket))  # pylint: disable=protected-access
    if ok and (data.get("receipt") or {}).get("kind") == "clean":
        print(f"review: CLEAN from the existing receipt ({message}) - nothing in the bundle "
              "changed since that clean round, so no round was spent")
        if args.provider not in LAUNCHED:
            print("ALREADY_CLEAN=1")
        return EXIT_CLEAN
    state, reason = review_gate.gate_state(args.root)
    if state in (review_gate.UNVERIFIED, review_gate.UNKNOWN):
        if args.allow_unverified:
            sys.stderr.write(f"review-run: gate {state}: {reason}. Reviewing anyway "
                             "(--allow-unverified); review.json records the override\n")
            return None
        sys.stderr.write(
            f"review-run: gate {state}: {reason}. No round reserved. Run the verify gate on "
            f"this tree first (bash \"{VERIFY_GATE}\" </dev/null, or end the turn so the "
            "Stop gate runs), then review again. "
            "--allow-unverified reviews it anyway and records that it did.\n")
        return EXIT_UNVERIFIED
    sys.stderr.write(f"review-run: gate {state}: {reason}\n")
    return None


def run(args):
    exe = prompt = before = None
    if args.provider in LAUNCHED:
        if args.provider == "copilot" and not args.model:
            sys.stderr.write("review-run: copilot needs --model (qa.copilot.model); an "
                             "unpinned Copilot is the author's family\n")
            return EXIT_USAGE
        exe = shutil.which(args.provider)
        if not exe:
            sys.stderr.write(f"review-run: {args.provider} is not on PATH (not-installed); "
                             "nothing launched, no round spent\n")
            return EXIT_USAGE
        if args.provider == "kimi":
            # A Kimi round is never reserved unprobed (round 4 of T-0028: the
            # unlocked status said none was left, a successor plan landed, and
            # the probe that then ran after `reserve` spent the round). So the
            # status refuses first, before any probe request.
            if not _round_available(args.root, args.ticket):
                sys.stderr.write("review-run: kimi: no round left per the ledger's status; "
                                 "re-run once a successor plan is approved; nothing "
                                 "launched, no round spent\n")
                return EXIT_REFUSED
            # The fingerprint comes FIRST: the probe is a Kimi call too, so it
            # is inside the watched window. graph.out is resolved with it, from
            # the tree as it is BEFORE any Kimi call could write it. A "before"
            # that could not be taken already decides the round (INCOMPLETE),
            # so it stops here: no probe request, no reservation. Then the
            # probe, BEFORE `reserve`: it is not a review, and a quota or auth
            # wall found here must cost no round. Only `ok` goes on.
            problems = []
            before = tree_fingerprint(args.root, problems)
            args.graph_out = graph_out(args.root)
            if before is None:
                sys.stderr.write("review-run: kimi: unknown - cannot fingerprint the tree: "
                                 f"{'; '.join(problems) or 'no reason given'}; nothing "
                                 "launched, no round spent\n")
                return EXIT_USAGE
            refusal = _probe_kimi(args, before)
            if refusal:
                sys.stderr.write(f"review-run: {refusal[1]}; nothing launched, no round "
                                 "spent\n")
                return refusal[0]
        prompt = prompt_argument(os.path.join(args.scratch, "prompt.txt"))

    short = preflight(args)
    if short is not None:
        return short
    ok, number, message = review_ledger.reserve(args.root, args.ticket, args.provider,
                                                args.model)
    sys.stderr.write(f"review-run: {message}\n")
    if not ok:
        return EXIT_REFUSED
    if args.provider not in LAUNCHED:
        print(f"ROUND={number}")
        return EXIT_CLEAN

    if args.provider == "kimi":
        return _run_kimi(args, number, prompt, before)
    extra = []
    cmd = command_for(args.provider, exe, args.root, prompt, args.model, args.effort)
    stdout, stderr, code, timed_out = launch(cmd, args.root, args.timeout)
    limit = None
    if args.provider == "codex":
        _write_atomic(os.path.join(args.scratch, "codex-events.jsonl"), stdout)
        message_text, error = review_verdict.codex_final_message(stdout)
        output = message_text or ""
        if error and not timed_out:
            extra.append(f"codex: {error}")
        # Only a FAILED call is judged: a 429 Codex retried and got past leaves
        # `error` events in a round that still delivered (T-0088).
        if timed_out or code != 0 or not output.strip():
            limit = review_limit.limit_line(error or "", stderr)
    else:
        output = stdout
    _write_atomic(os.path.join(args.scratch, "out.txt"), output)
    _write_atomic(os.path.join(args.scratch, "stderr.txt"), stderr)
    status = finish(args, number, output, code, timed_out, extra)
    if limit:
        # After finish, never before: the round's INCOMPLETE record is the
        # ledger's, and a marker that cannot be written (disk full, a path that
        # is not a directory) must not take it, or exit 3, down with it.
        try:
            review_limit.record(args.root, args.ticket, number, "codex", args.model, limit)
            then = "the next round runs the Claude reviewer (same-family, not independent)"
        except OSError as exc:
            then = (f"could not record it ({exc}), so the next probe calls Codex live "
                    "instead of answering limited from the record")
        print(f"review: codex usage limit in round {number}: {limit!r}; {then}")
    return status


def probe(args):
    """(outcome, detail). One minimal real Codex call, BEFORE any reservation.

    Four outcomes, never collapsed: `ok` is a delivered message at exit 0 (a
    429 Codex retried and then got past is still ok); `limited` is a failed
    call whose error or stderr names a limit, or a limit recorded by the round
    before (`review_limit.recorded`, no call made); `failed` is any other
    failure, quoted; `unknown` is no answer within the probe's timeout."""
    mark = review_limit.recorded(args.root, args.ticket)
    if mark:
        return PROBE_LIMITED, f"recorded in round {mark['round']}: {mark['error']}"
    exe = shutil.which("codex")
    if not exe:
        return PROBE_FAILED, "codex is not on PATH"
    timeout = args.probe_timeout
    cmd = command_for("codex", exe, args.root, PROBE_PROMPT, args.model, args.effort)
    stdout, stderr, code, timed_out = launch(cmd, args.root, timeout)
    _write_atomic(os.path.join(args.scratch, "probe-events.jsonl"), stdout)
    _write_atomic(os.path.join(args.scratch, "probe-stderr.txt"), stderr)
    message, error = review_verdict.codex_final_message(stdout)
    if code == 0 and not timed_out and (message or "").strip():
        return PROBE_OK, message.strip().splitlines()[0][:120]
    line = review_limit.limit_line(error or "", stderr)
    if line:
        return PROBE_LIMITED, line
    if timed_out:
        return PROBE_UNKNOWN, f"no answer within {timeout}s"
    tail = (stderr or "").strip().splitlines()[-1:] or [f"exit {code}"]
    return PROBE_FAILED, error or tail[0]


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--provider", required=True, choices=("codex", "copilot", "kimi", "claude"))
    parser.add_argument("--model", default="")
    parser.add_argument("--effort", default="")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--work-dir")
    parser.add_argument("--reserve-only", action="store_true")
    parser.add_argument("--round", type=int)
    parser.add_argument("--output")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--probe-timeout", type=int, default=PROBE_TIMEOUT)
    parser.add_argument("--allow-unverified", action="store_true",
                        help="review a tree the verify gate has not passed; recorded in "
                             "review.json as gate.overridden")
    args = parser.parse_args(argv)
    args.root = os.path.abspath(args.root)
    args.scratch = os.path.abspath(args.scratch)
    args.manifest = args.manifest or os.path.join(args.scratch, "manifest.json")

    try:
        review_ledger.check_ticket(args.ticket)
        if args.probe:
            if args.provider != "codex":
                parser.error("--probe is for the codex provider only")
            if args.reserve_only or args.round is not None:
                parser.error("--probe reserves nothing; it takes neither --reserve-only "
                             "nor --round")
            outcome, detail = probe(args)
            print(f"PROBE={outcome}")
            print("PROBE_DETAIL=" + " ".join(str(detail).splitlines()))
            return {PROBE_OK: EXIT_CLEAN, PROBE_LIMITED: EXIT_PROBE_LIMITED,
                    PROBE_FAILED: EXIT_PROBE_FAILED,
                    PROBE_UNKNOWN: EXIT_PROBE_UNKNOWN}[outcome]
        if args.provider == "claude":
            if args.reserve_only:
                return run(args)
            if args.round is None or args.output is None or args.exit_code is None:
                parser.error("the claude provider takes --reserve-only, or --round N "
                             "--output FILE --exit-code N after the subagent ran")
            output = _read(args.output) if os.path.exists(args.output) else ""
            return finish(args, args.round, output, args.exit_code, False)
        if args.reserve_only or args.round is not None:
            parser.error("--reserve-only and --round are for the claude provider only")
        return run(args)
    except review_ledger.LedgerError as exc:
        sys.stderr.write(f"review-run: {exc}\n")
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
