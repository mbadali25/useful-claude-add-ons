#!/usr/bin/env python3
"""The verify gate's trust store (L-0888): does this machine trust THIS repo's
verify map enough to run the commands it names?

    python3 verify_trust.py check   [--root DIR]
    python3 verify_trust.py approve [--root DIR] [--yes]
    python3 verify_trust.py revoke  [--root DIR]
    python3 verify_trust.py status  [--root DIR]
    python3 verify_trust.py allow-owner HOST/OWNER [--under DIR ...] [--yes]
    python3 verify_trust.py disallow-owner HOST/OWNER [--yes]

`.crew/verify.json` is repo-authored text and its `run` strings reach `eval`;
`_verify/smoke.sh` / `scripts/smoke.sh` reach `bash`. A clone of a hostile repo
would run both on its first Stop. `verify-gate.sh` therefore calls `check`
before it runs either, and runs nothing unless the answer is exit 0.

A repo is trusted two ways, and only these two:

1. By HASH. `approve` records the sha256 of exactly what the gate would run
   (the verify.json bytes when that file exists, otherwise the bytes of the
   smoke script the gate would pick) under the repo's identity. Any byte
   change is CHANGED until approved again. The identity is the real path of
   the parent of `git rev-parse --git-common-dir`, so linked worktrees of one
   repo share an entry; each worktree's own bytes still need their own hash.
2. By REMOTE OWNER. `allow-owner github.com/someone` trusts a repo whose every
   remote URL in its LOCAL git config parses strictly to that host/owner. The
   first allowlisted run writes a pin (the sorted remote URL set); a later run
   whose set differs is REMOTE CHANGED until `approve` re-pins it. This is the
   owner's own pick and a weaker guard than a hash: a fresh directory with a
   forged `.git/config` naming an allowlisted owner passes on first sight.
   `--under DIR` narrows an entry to repos below DIR, and the mitigations
   below narrow it further: strict URL grammar (https, ssh://git@, scp-style
   git@host:owner/repo; no userinfo, port, `file:`, `ext::`, local path or
   `..`), `insteadOf` rewrites refused, the raw and the resolved remote lists
   must agree, and the repo must be owned by the running user (POSIX).

Exit codes of `check` (stdout carries one human line; the gate echoes it):
0 trusted; 10 UNTRUSTED; 11 CHANGED; 12 REMOTE CHANGED; 13 UNKNOWN (the store
or the repo could not be read). Anything but 0 means "run nothing": an unknown
is never read as trusted.

The store is machine-local: `$CREW_VERIFY_TRUST_FILE` (a test seam) else
`${CLAUDE_CONFIG_DIR:-~/.claude}/crew/verify-trust.json`, written through a
temp file and `os.replace` under a lock, mode 0600. It is not a crew config
key: the allowlist is never read from a repo file, so a hostile repo cannot
widen it. `scope_guard.py` refuses a model-run command that approves, allows,
disallows or revokes, and refuses a Write/Edit of the store, so only a person
at a terminal grows trust.

Not covered, by design: scripts a `run` string calls (the hash binds the map,
not `python3 scripts/foo.py`); `--ci`, which is a CI job's own pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

import crew_common

EXIT_TRUSTED = 0
EXIT_UNTRUSTED = 10
EXIT_CHANGED = 11
EXIT_REMOTE_CHANGED = 12
EXIT_UNKNOWN = 13

STORE_VERSION = 1
ENV_STORE = "CREW_VERIFY_TRUST_FILE"
SMOKE_CANDIDATES = ("_verify/smoke.sh", "scripts/smoke.sh")
GIT_TIMEOUT = 15
LOCK_WAIT = 5.0
LOCK_STALE = 30.0
REPLACE_TRIES = 5

_SEG = re.compile(r"[A-Za-z0-9_.-]+")
_HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?")
_HTTPS = re.compile(r"https://([^/@:\s]+)/([^/@:\s]+)/([^/@:\s]+)")
_SSH_URL = re.compile(r"ssh://git@([^/@:\s]+)/([^/@:\s]+)/([^/@:\s]+)")
_SCP = re.compile(r"git@([^/@:\s]+):([^/@:\s]+)/([^/@:\s]+)")
_OWNER_ARG = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?/[a-z0-9_][a-z0-9_.-]*")


class TrustError(Exception):
    """The store or the repo could not be read: an UNKNOWN, never a pass."""


class Verdict:
    """What `evaluate` decided: an exit code, the line to print, the facts."""

    def __init__(self, code, message, **facts):
        self.code = code
        self.message = message
        self.facts = facts


# --------------------------------------------------------------------- store

def store_path():
    explicit = os.environ.get(ENV_STORE)
    if explicit:
        return explicit
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "crew", "verify-trust.json")


def _empty_store():
    return {"version": STORE_VERSION, "repos": {}, "owners": {}}


def load_store(path):
    """The store at `path`. A missing file is an empty store (nothing trusted
    yet); a file that exists but cannot be read or understood raises
    TrustError, so a corrupt store never reads as an empty one that trusts
    nothing silently, nor as one that trusts everything."""
    try:
        # O_NONBLOCK so a FIFO with no writer cannot hang the Stop gate; the
        # fstat below refuses anything that is not a regular file.
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        return _empty_store()
    except OSError as exc:
        raise TrustError(f"cannot read {path}: {exc.__class__.__name__}") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise TrustError(f"{path} is not a regular file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read()
    except OSError as exc:
        raise TrustError(f"cannot read {path}: {exc.__class__.__name__}") from exc
    finally:
        os.close(fd)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise TrustError(f"{path} is not valid JSON") from exc
    if not isinstance(data, dict) or data.get("version") != STORE_VERSION:
        raise TrustError(f"{path} has no recognised version")
    repos, owners = data.get("repos"), data.get("owners")
    if not isinstance(repos, dict) or not isinstance(owners, dict):
        raise TrustError(f"{path} has a malformed repos/owners table")
    for entry in repos.values():
        if not isinstance(entry, dict) or not isinstance(entry.get("hashes", []), list) \
                or not all(isinstance(h, str) for h in entry.get("hashes", [])):
            raise TrustError(f"{path} has a malformed repo entry")
        pin = entry.get("pin")
        if pin is not None and (not isinstance(pin, list)
                                or not all(isinstance(u, str) for u in pin)):
            raise TrustError(f"{path} has a malformed repo pin")
    for entry in owners.values():
        under = entry.get("under", []) if isinstance(entry, dict) else None
        if not isinstance(under, list) or not all(isinstance(d, str) for d in under):
            raise TrustError(f"{path} has a malformed owner entry")
    return data


class _Lock:
    """A directory lock beside the store: portable, bounded, self-expiring.
    The holder writes a random token inside the directory and releases only a
    directory still carrying it; a stale lock is claimed by an atomic rename to
    a name of the claimer's own, so two waiters cannot both break it and a
    waiter never removes a lock that was re-taken after it looked."""

    def __init__(self, path):
        self.path = path + ".lock"
        self.token = uuid.uuid4().hex

    def _stale(self):
        try:
            return time.time() - os.stat(self.path).st_mtime > LOCK_STALE
        except OSError:
            return False

    def _break(self):
        claimed = f"{self.path}.stale.{self.token}"
        try:
            os.rename(self.path, claimed)
        except OSError:
            return
        try:
            if time.time() - os.stat(claimed).st_mtime <= LOCK_STALE:
                try:
                    os.rename(claimed, self.path)
                except OSError:
                    pass
                return
            shutil.rmtree(claimed, ignore_errors=True)
        except OSError:
            pass

    def __enter__(self):
        deadline = time.monotonic() + LOCK_WAIT
        while True:
            try:
                os.mkdir(self.path)
                try:
                    with open(os.path.join(self.path, "token"), "w", encoding="utf-8") as handle:
                        handle.write(self.token)
                except OSError:
                    pass
                return self
            except FileExistsError:
                if self._stale():
                    self._break()
                    continue
                if time.monotonic() > deadline:
                    raise TrustError(f"the store lock {self.path} is held") from None
                time.sleep(0.05)
            except OSError as exc:
                raise TrustError(f"cannot take the store lock: {exc.__class__.__name__}") from exc

    def __exit__(self, *exc):
        try:
            with open(os.path.join(self.path, "token"), encoding="utf-8") as handle:
                mine = handle.read() == self.token
        except OSError:
            mine = False
        if mine:
            shutil.rmtree(self.path, ignore_errors=True)
        return False


def _replace(src, dst):
    """os.replace, retried briefly: on Windows a concurrent reader holding the
    store open makes it raise PermissionError until the reader lets go."""
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == REPLACE_TRIES - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


def update_store(path, mutate):
    """Load the store fresh under the lock, apply `mutate(store)`, and write
    the result atomically. The full text is computed BEFORE anything is
    opened (CLAUDE.md, the `open(p, "w")` landmine). Raises TrustError."""
    directory = os.path.dirname(path) or "."
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
    except OSError as exc:
        raise TrustError(f"cannot create {directory}: {exc.__class__.__name__}") from exc
    with _Lock(path):
        store = load_store(path)
        mutate(store)
        text = json.dumps(store, indent=2, sort_keys=True) + "\n"
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(prefix=".verify-trust.", dir=directory)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            _replace(tmp, path)
            tmp = None
        except OSError as exc:
            raise TrustError(f"cannot write {path}: {exc.__class__.__name__}") from exc
        finally:
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    return store


# ----------------------------------------------------------------------- git

def _git(root, *args):
    env = {k: v for k, v in os.environ.items()
           if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")}
    try:
        proc = subprocess.run([crew_common.require_tool("git"), *args], cwd=root,
                              capture_output=True, env=env, stdin=subprocess.DEVNULL,
                              timeout=GIT_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "backslashreplace")


def repo_identity(root):
    """`(identity, toplevel)`. A directory that is not a git repo has its own
    real path as identity and no toplevel (so no owner trust)."""
    out = _git(root, "rev-parse", "--git-common-dir")
    top = _git(root, "rev-parse", "--show-toplevel")
    if out is None or top is None:
        return os.path.realpath(root), None
    common = out.strip()
    if not os.path.isabs(common):
        common = os.path.join(root, common)
    common = os.path.realpath(common)
    identity = os.path.dirname(common) if os.path.basename(common) == ".git" else common
    return identity, os.path.realpath(top.strip())


def local_remote_config(root):
    """`(urls, pushurls, rewrites)` from the repo's LOCAL config alone, as
    `{name: [values]}` for the first two and a list of rewrite keys. None when
    git cannot say."""
    out = _git(root, "config", "--local", "-z", "--list")
    if out is None:
        return None
    urls, pushes, rewrites = {}, {}, []
    for record in out.split("\0"):
        if not record:
            continue
        key, _, value = record.partition("\n")
        low = key.lower()
        if low.startswith("url."):
            rewrites.append(key)
        elif low.startswith("remote.") and low.endswith(".url"):
            urls.setdefault(key[len("remote."):-len(".url")], []).append(value)
        elif low.startswith("remote.") and low.endswith(".pushurl"):
            pushes.setdefault(key[len("remote."):-len(".pushurl")], []).append(value)
    return urls, pushes, rewrites


def remote_set(root):
    """The sorted remote URL set (pushurls prefixed `push:`), or None."""
    cfg = local_remote_config(root)
    if cfg is None:
        return None
    urls, pushes, _ = cfg
    out = [u for vals in urls.values() for u in vals]
    out += ["push:" + u for vals in pushes.values() for u in vals]
    return sorted(out)


def parse_remote(url):
    """`host/owner` (lower-cased) for a remote URL in the strict grammar, else
    None. Anything not spelled exactly as one of the three forms is None."""
    if not isinstance(url, str) or url != url.strip() or not url.isascii() \
            or any(ord(c) < 33 or c in "\\%" for c in url):
        return None
    match = _HTTPS.fullmatch(url) or _SSH_URL.fullmatch(url) or _SCP.fullmatch(url)
    if not match:
        return None
    host, owner, repo = match.groups()
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not _HOST.fullmatch(host) or ".." in host:
        return None
    for seg in (owner, repo):
        if not _SEG.fullmatch(seg) or seg in (".", ".."):
            return None
    return f"{host.lower()}/{owner.lower()}"


def _under(path, parents):
    for parent in parents:
        parent = os.path.realpath(parent)
        try:
            if os.path.commonpath([path, parent]) == parent:
                return True
        except ValueError:
            continue
    return False


def owner_trust(root, identity, toplevel, store, euid=None):
    """`(ok, reason, remotes)`: whether the allowlist trusts this repo now."""
    owners = store["owners"]
    if not owners:
        return False, "no remote owner is allowlisted", None
    if toplevel is None:
        return False, "not a git repository", None
    if os.path.realpath(root) != toplevel:
        # The gate runs the map of the directory it stands in. A directory
        # below a trusted repo's top level is not that repo.
        return False, "the directory is not the repository's top level", None
    cfg = local_remote_config(root)
    if cfg is None:
        return False, "git could not read the local config", None
    urls, pushes, rewrites = cfg
    if rewrites:
        return False, "the local config rewrites URLs (insteadOf)", None
    if not urls:
        return False, "the repo has no remote", None
    listed = _git(root, "remote")
    if listed is None or set(listed.split()) != set(urls):
        return False, "the remotes git resolves differ from the local config", None
    matched = set()
    for name, raw in urls.items():
        resolved = _git(root, "remote", "get-url", "--all", name)
        pushed = _git(root, "remote", "get-url", "--push", "--all", name)
        if resolved is None or pushed is None:
            return False, f"git could not resolve remote {name}", None
        if sorted(resolved.split("\n")[:-1]) != sorted(raw) \
                or sorted(pushed.split("\n")[:-1]) != sorted(pushes.get(name, raw)):
            return False, f"remote {name} resolves to a different URL than the config names", None
        for url in raw + pushes.get(name, []):
            owner = parse_remote(url)
            if owner is None or owner not in owners:
                return False, f"remote {name} ({url}) is not an allowlisted host/owner", None
            matched.add(owner)
    for owner in matched:
        under = (owners.get(owner) or {}).get("under") or []
        if under and not _under(toplevel, under):
            return False, f"{owner} is allowlisted only under {', '.join(under)}", None
    if os.name == "posix":
        uid = os.geteuid() if euid is None else euid
        for path in (toplevel, identity):
            try:
                if os.stat(path).st_uid != uid:
                    return False, f"{path} is not owned by the current user", None
            except OSError:
                return False, f"cannot stat {path}", None
    remotes = sorted([u for vals in urls.values() for u in vals]
                     + ["push:" + u for vals in pushes.values() for u in vals])
    return True, "", remotes


# -------------------------------------------------------------------- digest

def gate_target(root):
    """`[(label, path)]` for exactly what the gate would run: verify.json when
    it exists, else the smoke script it would pick, else nothing."""
    verify = os.path.join(root, ".crew", "verify.json")
    if os.path.isfile(verify):
        return [("verify.json", verify)]
    for cand in SMOKE_CANDIDATES:
        path = os.path.join(root, *cand.split("/"))
        if os.path.isfile(path):
            return [("smoke:" + cand, path)]
    return []


def digest(root, verify_file=None):
    """`(hex, targets)` over length-prefixed (label, bytes) records; `(None,
    [])` when the gate would run nothing. Raises TrustError when a file the
    gate would run cannot be read. `verify_file` stands in for the repo's own
    verify.json (a map the operator named, as `--price` can)."""
    targets = [("verify.json", verify_file)] if verify_file else gate_target(root)
    if not targets:
        return None, []
    sha = hashlib.sha256()
    for label, path in targets:
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError as exc:
            raise TrustError(f"cannot read {path}: {exc.__class__.__name__}") from exc
        name = label.encode("utf-8")
        sha.update(len(name).to_bytes(8, "big") + name + len(data).to_bytes(8, "big") + data)
    return sha.hexdigest(), targets


# ------------------------------------------------------------------- verdict

def _approve_hint(root):
    script = os.path.abspath(__file__)
    return f"python3 {script} approve --root {root}"


def evaluate(root, path=None, write_pin=True, euid=None, verify_file=None):
    """The trust verdict for the repo at `root`. Never raises. With
    `verify_file`, the bytes of that file are judged as the verify map and only
    a hash approval of exactly those bytes trusts them: the remote owner says
    nothing about a file that is not the repo's own."""
    path = path or store_path()
    try:
        return _evaluate(root, path, write_pin, euid, verify_file)
    except TrustError as exc:
        return Verdict(EXIT_UNKNOWN, f"VERIFY GATE: UNKNOWN, not run - nothing was verified. "
                       f"Trust could not be decided: {exc}. Fix or remove it, then re-run.")


def _evaluate(root, path, write_pin, euid, verify_file=None):
    store = load_store(path)
    if os.environ.get(ENV_STORE) and store.get("testTrustAll") is True:
        return Verdict(EXIT_TRUSTED, "verify trust: trusted (test store)")
    current, _targets = digest(root, verify_file)
    if current is None:
        return Verdict(EXIT_TRUSTED, "verify trust: nothing to run here")
    identity, toplevel = repo_identity(root)
    entry = store["repos"].get(identity) or {}
    hashes = entry.get("hashes") or []
    if current in hashes:
        return Verdict(EXIT_TRUSTED, f"verify trust: trusted (approved bytes {current[:12]})",
                       digest=current, identity=identity)
    ok, why, remotes = owner_trust(root, identity, toplevel, store, euid)
    if ok and verify_file:
        ok, why = False, "a named verify map is trusted by its approved bytes only"
    if ok:
        pin = entry.get("pin")
        if pin is not None and pin != remotes:
            return Verdict(EXIT_REMOTE_CHANGED,
                           "VERIFY GATE: REMOTE CHANGED, not run - nothing was verified. The "
                           "remotes of this repo differ from the set pinned when it was first "
                           f"trusted by owner. Review them, then run: {_approve_hint(root)}",
                           identity=identity)
        if pin is None:
            if not write_pin:
                return Verdict(EXIT_TRUSTED, "verify trust: trusted by remote owner (no pin yet)",
                               digest=current, identity=identity)

            def pin_it(st):
                st["repos"].setdefault(identity, {}).setdefault("hashes", [])
                st["repos"][identity]["pin"] = remotes
            try:
                update_store(path, pin_it)
            except TrustError as exc:
                return Verdict(EXIT_UNTRUSTED,
                               "VERIFY GATE: UNTRUSTED, not run - nothing was verified. This repo "
                               f"is trusted by remote owner but its pin could not be written ({exc}).",
                               identity=identity)
        return Verdict(EXIT_TRUSTED, "verify trust: trusted by remote owner",
                       digest=current, identity=identity)
    if hashes:
        return Verdict(EXIT_CHANGED,
                       "VERIFY GATE: CHANGED, not run - nothing was verified. What the gate would "
                       "run differs from every version approved on this machine. Review the "
                       f"change, then run: {_approve_hint(root)}",
                       identity=identity, owner_reason=why)
    return Verdict(EXIT_UNTRUSTED,
                   "VERIFY GATE: UNTRUSTED, not run - nothing was verified. This repo's verify "
                   "map (or smoke script) is repo-authored and has not been approved on this "
                   f"machine. Read it, then run: {_approve_hint(root)}",
                   identity=identity, owner_reason=why)


# ------------------------------------------------------------------- commands

def _rule_count(root):
    try:
        with open(os.path.join(root, ".crew", "verify.json"), "rb") as handle:
            rules = json.loads(handle.read().decode("utf-8")).get("rules")
        return len(rules) if isinstance(rules, list) else None
    except (OSError, ValueError, AttributeError):
        return None


def _confirm(prompt, yes):
    if os.environ.get("CLAUDECODE") and not os.environ.get(ENV_STORE):
        print("verify_trust: refused - this is running inside a Claude Code session, and trust is "
              "the owner's, given in their own terminal. Nothing was changed.", file=sys.stderr)
        return False
    if yes:
        return True
    if not sys.stdin.isatty():
        print("verify_trust: refused - this needs a person at a terminal (or --yes in your own "
              "shell). Nothing was changed.", file=sys.stderr)
        return False
    try:
        answer = input(prompt + " Type 'yes' to continue: ")
    except EOFError:
        return False
    return answer.strip().lower() == "yes"


def _parsed_bytes_verdict(root, expect):
    """None when verify.json's bytes now are the bytes the matcher parsed
    (`expect`, a sha256), else the CHANGED verdict. Trust that held for the
    bytes at the first check and again at the second is not trust for the
    bytes in between: A, swapped to B for the matcher, swapped back to A."""
    try:
        with open(os.path.join(root, ".crew", "verify.json"), "rb") as handle:
            now = hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        now = None
    if now == expect:
        return None
    return Verdict(EXIT_CHANGED,
                   "VERIFY GATE: CHANGED, not run - nothing was verified. verify.json is not "
                   "the file the gate parsed a moment ago. Review the change, then run: "
                   f"{_approve_hint(root)}")


def cmd_check(args):
    root = os.path.abspath(args.root)
    verify_file = os.path.abspath(args.verify_file) if args.verify_file else None
    verdict = evaluate(root, verify_file=verify_file)
    if verdict.code == EXIT_TRUSTED and args.expect_verify_sha:
        verdict = _parsed_bytes_verdict(root, args.expect_verify_sha) or verdict
    print(verdict.message)
    return verdict.code


def cmd_status(args):
    root = os.path.abspath(args.root)
    path = store_path()
    print(f"store: {path}")
    verdict = evaluate(root, path, write_pin=False)
    print(f"repo: {repo_identity(root)[0]}")
    print(f"verdict: exit {verdict.code} - {verdict.message}")
    try:
        store = load_store(path)
    except TrustError as exc:
        print(f"owners: unknown ({exc})")
        return 0
    for owner, entry in sorted(store["owners"].items()):
        under = entry.get("under") or []
        print(f"owner: {owner}" + (f" (under {', '.join(under)})" if under else " (unrestricted)"))
    return 0


def cmd_approve(args):
    root = os.path.abspath(args.root)
    try:
        current, targets = digest(root)
    except TrustError as exc:
        print(f"verify_trust: {exc}", file=sys.stderr)
        return 1
    if current is None:
        print("verify_trust: nothing to approve - no .crew/verify.json and no smoke script.",
              file=sys.stderr)
        return 1
    identity, _top = repo_identity(root)
    remotes = remote_set(root)
    rules = _rule_count(root)
    print(f"repo:    {identity}")
    print(f"runs:    {', '.join(label for label, _ in targets)}"
          + (f" ({rules} rules)" if rules is not None else ""))
    print(f"sha256:  {current}")
    # The remotes come from the repo's own config: shown escaped, so a hostile
    # URL cannot carry terminal control sequences into the confirmation prompt.
    print("remotes: " + (", ".join(json.dumps(url) for url in remotes)
                         if remotes else "(none readable)"))
    if not _confirm("The gate will run the commands in this file on every Stop.", args.yes):
        return 1

    def add(st):
        entry = st["repos"].setdefault(identity, {})
        hashes = entry.setdefault("hashes", [])
        if current not in hashes:
            hashes.append(current)
        entry["remotes"] = remotes
        entry["pin"] = remotes
        entry["approved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        update_store(store_path(), add)
    except TrustError as exc:
        print(f"verify_trust: {exc}", file=sys.stderr)
        return 1
    print("approved.")
    return 0


def cmd_revoke(args):
    identity, _top = repo_identity(os.path.abspath(args.root))
    found = []

    def drop(st):
        if st["repos"].pop(identity, None) is not None:
            found.append(1)
    try:
        update_store(store_path(), drop)
    except TrustError as exc:
        print(f"verify_trust: {exc}", file=sys.stderr)
        return 1
    print("revoked." if found else "no entry for this repo.")
    return 0


def cmd_allow_owner(args):
    owner = args.owner.strip().lower()
    if not _OWNER_ARG.fullmatch(owner):
        print("verify_trust: the owner must be host/owner, e.g. github.com/someone",
              file=sys.stderr)
        return 2
    under = [os.path.realpath(d) for d in (args.under or [])]
    for directory in under:
        if not os.path.isdir(directory):
            print(f"verify_trust: --under {directory} is not a directory", file=sys.stderr)
            return 2
    where = f"only under {', '.join(under)}" if under else "ANYWHERE on this machine"
    if not under:
        print("warning: without --under, any directory whose git config names this owner is "
              "trusted on first sight.")
    if not _confirm(f"Trust every repo whose remotes are {owner}, {where}.", args.yes):
        return 1

    def add(st):
        st["owners"][owner] = {"under": under}
    try:
        update_store(store_path(), add)
    except TrustError as exc:
        print(f"verify_trust: {exc}", file=sys.stderr)
        return 1
    print(f"allowed {owner}.")
    return 0


def cmd_disallow_owner(args):
    owner = args.owner.strip().lower()
    found = []
    if not _confirm(f"Stop trusting every repo whose remotes are {owner}.", args.yes):
        return 1

    def drop(st):
        if st["owners"].pop(owner, None) is not None:
            found.append(1)
        for entry in st["repos"].values():
            if not entry.get("hashes"):
                entry["pin"] = None
    try:
        update_store(store_path(), drop)
    except TrustError as exc:
        print(f"verify_trust: {exc}", file=sys.stderr)
        return 1
    print(f"disallowed {owner}." if found else f"{owner} was not allowlisted.")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="verify_trust.py", description=__doc__.split("\n", maxsplit=1)[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, func in (("check", cmd_check), ("status", cmd_status), ("approve", cmd_approve),
                       ("revoke", cmd_revoke)):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
        if name == "approve":
            p.add_argument("--yes", action="store_true")
        if name == "check":
            p.add_argument("--verify-file")
            p.add_argument("--expect-verify-sha")
        p.set_defaults(func=func)
    allow = sub.add_parser("allow-owner")
    allow.add_argument("owner")
    allow.add_argument("--under", action="append")
    allow.add_argument("--yes", action="store_true")
    allow.set_defaults(func=cmd_allow_owner)
    deny = sub.add_parser("disallow-owner")
    deny.add_argument("owner")
    deny.add_argument("--yes", action="store_true")
    deny.set_defaults(func=cmd_disallow_owner)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
