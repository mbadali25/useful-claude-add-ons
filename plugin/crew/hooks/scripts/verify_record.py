"""Per-rule verified record, machine-local, shared by verify-gate.sh and
verify-gate.ps1 so the two flavours cannot write two different shapes of the
same file.

WHY THIS EXISTS. The single sha marker (.crew/.verify-verified-at) only ever
advances when NOTHING was deferred this turn. A rule that is over its Stop
budget on its own -- this repo's own rules[8] at 185s against a 60s default --
is therefore deferred on EVERY Stop, forever, and the marker never advances.
That does not just leave rules[8] unverified; it leaves EVERY rule unverified,
because a frozen marker means every later Stop diffs against the same old
base and re-matches (and re-runs) the whole accumulated changeset again. The
fix is to let the marker advance past a rule that is KNOWN to be permanently
over budget, while making sure that rule cannot quietly read as "verified":
its own entry here persists, and is reported, until it is actually run clean
(via --all) or its budget changes.

WHAT THIS FILE IS NOT. It does not decide whether the marker may advance this
turn -- that stays exactly where it lives today, in verify-gate.sh/ps1's own
DEFERRED_COUNT (now counting only ACUTE budget-contention deferrals; a
chronic, over-budget-alone deferral is excluded from that count by the
matcher itself). This script only persists PER-RULE STATUS across turns so a
chronic/skipped/reach-excluded rule is not silently forgotten once the
marker moves past the commit where its own files last changed, and it caches
measured wall time for rules verify.json has not priced.

FAIL-SAFE DIRECTION. An unreadable or corrupt record is treated as EMPTY, not
as "everything already verified" -- the same direction as DEFERRED_COUNT
defaulting to 1 in verify-gate.sh. Losing this file loses only history; it
never invents a clean rule that never ran.
"""
import json
import math
import os
import re
import shlex
import sys
import hashlib

# Every line this module writes to stdout is read by a shell on the other
# end (bash `read` or a PowerShell pipe), one record per line. On native
# Windows Python, stdout defaults to TEXT mode and translates every '\n' to
# '\r\n' - the read site then gets a trailing \r baked into its last field.
# Measured: `unset "$VAR"` where $VAR was "AWS_PROFILE\r" (a name nothing
# ever exports) silently failed to unset the real AWS_PROFILE, so a
# credential the pin exists to strip rode along into the check anyway.
# Fixed at the SOURCE - the read site ALSO strips '\r' defensively (see
# verify-gate.sh/.ps1's `tr -d '\r'` at each call site), but a source that
# never emits '\r' is the fix that does not depend on every caller
# remembering the workaround.
try:
    sys.stdout.reconfigure(newline="\n")
except (AttributeError, ValueError):
    pass

RECORD_PATH = os.path.join(".crew", ".verify-gate.record.json")
TIMINGS_PATH = os.path.join(".crew", ".verify-gate.timings.json")


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, ValueError):
        return {}


def _save(path, data):
    """Returns None on success, the exception on failure - never raises.

    Swallowing a write failure here used to mean the CALLER (verify-gate.sh)
    had no way to know the record was never actually persisted, so it kept
    advancing the sha marker and fingerprint as though the chronic/skipped
    obligation just written had actually made it to disk. A `_save` that
    fails now has to fail LOUDLY enough that the gate can refuse to advance
    anything - see cmd_sync, which turns a non-None return here into exactly
    that refusal.
    """
    try:
        os.makedirs(".crew", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
        return None
    except OSError as e:
        return e


# CANONICAL, and the ONLY place this hash is computed - verify-gate.sh
# imports this module in-process (it is already a python interpreter) and
# verify-gate.ps1 shells out to `rule_key` below, rather than either flavour
# hashing independently. They used to: the .sh matcher's own inline
# `_rule_key` used `json.dumps(..., sort_keys=True)` (space-separated,
# python's default), while the .ps1 side used `ConvertTo-Json -Compress`
# (no spaces) - two different byte strings for the same logical rule, so
# every content-hash key the two flavours wrote NEVER matched: a timing
# seeded by one was invisible to the other, and neither could ever clear the
# other's chronic record entry. `separators=(",", ":")` fixes the byte
# string; being the one function BOTH flavours call is what keeps it fixed.
def rule_key(rule):
    """A content hash of everything about a rule that changes what it
    actually DOES, so a persisted entry survives verify.json being
    reordered (an index alone would not) and so an edited rule starts fresh
    rather than inheriting a stale clean/deferred status.

    `env`, `reach` and `requiresCleanTree` are hashed alongside `paths`/
    `run` - Codex round 2: two rules with identical paths/run but different
    `env` (ENV=prod, seconds=999 chronic; ENV=test, seconds=1, passes) used
    to hash to the SAME key (env was not part of it), so the passing test
    rule's clean result overwrote the chronic prod rule's record entry -
    the chronic obligation vanished from a run that never actually checked
    prod at all. `env` is re-serialised with its own keys sorted (a dict is
    unordered) rather than trusted to arrive pre-sorted.
    """
    env = rule.get("env")
    env_sorted = ({k: env[k] for k in sorted(env)}
                  if isinstance(env, dict) else None)
    blob = json.dumps({
        "paths": rule.get("paths"),
        "run": rule.get("run"),
        "env": env_sorted,
        "reach": rule.get("reach"),
        "requiresCleanTree": rule.get("requiresCleanTree"),
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


# --- env pinning, shared with --price (Codex round 2, FIX verify_price.py:63) ---
#
# The gates already pin these five correctly (bash export/unset, PowerShell
# Set-Item/Remove-Item); --price ran commands with NO pinning at all, so a
# caller's inherited ENV=prod rode straight into a `seconds` measurement
# whose whole point is to be reusable by everyone who later reads the map.
# ONE list, here, rather than a fourth copy: verify-gate.sh, verify-gate.ps1
# and verify_price.py all read PINNED_VARS instead of naming the five again.
PINNED_VARS = ("ENV", "AWS_PROFILE", "AWS_DEFAULT_REGION", "KUBECONFIG",
               "TF_WORKSPACE")


def pinned_env(rule_env, base=None):
    """The environment `--price` should run a rule's commands under: a copy
    of `base` (default os.environ) with every PINNED_VARS entry removed,
    then the rule's own declared `env` (string values only) applied on top.
    Never touches anything outside PINNED_VARS - this is isolation for the
    five variables a Stop gate cannot reason about if they leak in, not a
    general env sandbox."""
    env = dict(base if base is not None else os.environ)
    for v in PINNED_VARS:
        env.pop(v, None)
    if isinstance(rule_env, dict):
        for k, v in rule_env.items():
            if isinstance(k, str) and isinstance(v, str) and k in PINNED_VARS:
                env[k] = v
    return env


# --- reach scanning, shared by both gates and --price (Codex round 2, BLOCK
# verify-gate.sh:841 / verify_price.py:35) ---
#
# ONE function. It used to be regex logic duplicated three ways - a python
# heredoc inline in verify-gate.sh, native PowerShell in verify-gate.ps1,
# and NOTHING at all in verify_price.py (which scanned only the outer
# command string, so `--price` timed - and thereby RAN - a wrapper script
# whose body called ssh, on the strength of a scan Stop itself would have
# refused). All three now call this.
#
# NESTED wrappers: `bash outer.sh` where outer.sh itself runs `bash
# inner.sh` which calls ssh used to bypass the scan entirely - the scan
# read outer.sh's TEXT for a reach verb, found none, and stopped; it never
# noticed outer.sh's own body was ANOTHER wrapper invocation to follow.
# Bounded recursion fixes it: depth 3, a visited set (a script that wraps
# itself, or two scripts that wrap each other, terminates instead of
# looping), a 256 KiB per-file size cap, a binary check (NUL in the first
# 8 KiB), and every resolved path must stay inside the repo root.
#
# "COULD NOT TELL" IS ITS OWN VALUE. A wrapper this scan cannot read -
# missing, too large, binary, outside the repo, or past the depth limit -
# is UNINSPECTED, not local. Reading it as local would be exactly this
# repo's named recurring bug (an unknown collapsing into the safe-looking
# value) wearing a new hat: a script nobody can prove is safe is not the
# same claim as a script proven harmless.
REACH_VERBS = ("ssm", "ssh", "curl", "aws", "az", "gh", "psql", "mysql")
_REACH_RE = re.compile(r"\b(" + "|".join(re.escape(v) for v in REACH_VERBS) + r")\b")
_WRAPPER_INTERPRETERS = ("bash", "sh", "dash", "zsh", "python", "python3",
                         "py", "pwsh", "node")
# -m's argument is a MODULE NAME (`python -m pytest`), -c/-Command/-e's is
# INLINE CODE (`bash -c '...'`, `pwsh -Command '...'`, `node -e '...'`) -
# neither names a script FILE, so an interpreter carrying one of these
# names NO wrapper at all; the whole invocation stops there rather than
# treating the next non-flag token as a path to resolve. Applied to every
# entry in _WRAPPER_INTERPRETERS - safe even for a family where the flag
# does not exist, since the outcome (treat as no wrapper) is the cautious
# direction, never the permissive one.
_NO_WRAPPER_FLAGS = ("-c", "-m", "-e")
# -n is POSIX-SHELL-SPECIFIC and NOT folded into _NO_WRAPPER_FLAGS above,
# unlike -c/-m/-e: `bash -n script.sh` / `sh -n` / `dash -n` / `zsh -n`
# mean "read commands but do not execute them" - the named script is
# PARSED for syntax only and never actually RUN, so a `curl ... | bash`
# inside it can never fire under THIS invocation. Codex follow-up: rules[3]
# in THIS repo's own .crew/verify.json runs `bash -n scripts/
# install-prerequisites.sh` (a syntax-check step, not an execution), and
# the scanner followed it anyway, found a real `curl | bash` deep in that
# script's actual code (not a comment - see the comment-strip fix above,
# which is why this surfaced instead of an earlier, unrelated false
# match), and deferred a rule that never runs a single line of it. Unlike
# -c/-m/-e, -n does NOT mean "this token is safe to apply everywhere
# regardless of family" - python/node/pwsh have no such "parse but never
# execute" flag, and treating an unrelated -n there as "no wrapper" could
# hide a real invocation instead of a syntax check. Scoped to
# _POSIX_SHELLS for that reason, checked separately from the universal set.
_POSIX_SHELLS = ("bash", "sh", "dash", "zsh")
# A WHOLE-LINE comment (bash/PowerShell/python all use `#`) is prose, not
# code - a wrapper script's own comment describing what it does NOT do
# (`_verify/smoke.sh`: "there is no service to curl and no ...") used to
# verb-match on the strength of that sentence alone and deferred two rules
# in this repo's own .crew/verify.json on every Stop, forever, since
# smoke.sh is the default gate. Stripped BEFORE verb matching and BEFORE
# wrapper-path detection, so a comment naming either a verb or a wrapper
# script is inert in both directions. A TRAILING comment on a code line is
# left alone - a verb appearing in actual code must still match even if
# the same line also carries a `# comment` after it - so this only ever
# drops a line whose first non-blank character is `#`.
_PS_BLOCK_COMMENT_RE = re.compile(r"<#.*?#>", re.S)
REACH_SCAN_MAX_DEPTH = 3
REACH_SCAN_MAX_BYTES = 256 * 1024
# A token following an interpreter is only a wrapper CANDIDATE if, once it
# exists under repo_root, it also LOOKS like a script - Codex round 3 FIX:
# `python -m pytest` used to hand "pytest" (a module name, not a path) to
# the resolver, which correctly failed to find a file called "pytest" and
# read that failure as UNINSPECTED ("could not tell") rather than as what
# it actually was: no wrapper here at all. An extensionless file still
# counts if it starts with a shebang (`#!`) - checked in _looks_like_script.
_SCRIPT_EXTENSIONS = (".sh", ".bash", ".py", ".ps1", ".psm1",
                      ".js", ".mjs", ".cjs")
# A single LINE can chain several commands - Codex round 3 BLOCK: `true &&
# bash inner.sh` is one line but two commands, and treating the whole line
# as one cmd.split() target hid "bash inner.sh" (and anything after `;`,
# `|` or `||`) from wrapper detection entirely, so a compound wrapper
# invocation reached ssh unscanned. Every segment is scanned separately,
# for both the reach-verb text search and the wrapper-path search.
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|]")


def _looks_remote_text(text):
    if not text:
        return None
    m = _REACH_RE.search(text)
    return m.group(1) if m else None


def _strip_comments(text):
    """Remove PowerShell `<# ... #>` blocks and every WHOLE-LINE `#`
    comment from `text`, in that order (a block can span several lines
    that would otherwise each individually look like code). A TRAILING
    `# comment` on a line that also carries real code is left untouched -
    only a line whose first non-blank character is `#` is dropped. See
    _NO_WRAPPER_FLAGS's neighbouring comment for why this exists."""
    if not text:
        return text
    text = _PS_BLOCK_COMMENT_RE.sub("", text)
    return "\n".join(line for line in text.splitlines()
                      if not line.lstrip().startswith("#"))


def _command_segments(text):
    """Every individual command segment in `text`: each line split on &&,
    ||, ; and | in turn, trimmed, blanks dropped."""
    segments = []
    for line in (text or "").splitlines():
        for seg in _SEGMENT_SPLIT_RE.split(line):
            seg = seg.strip()
            if seg:
                segments.append(seg)
    return segments


def _tokenize(cmd):
    """Shell-aware tokens for one command segment - Codex round 3 FIX:
    `cmd.split()` left quote characters IN the token (`bash "local.sh"`
    split to the literal 4-character string '"local.sh"'), which could
    never match the real, unquoted file on disk and stayed UNINSPECTED
    forever. `shlex.split(posix=True)` strips them properly; an unbalanced
    quote shlex cannot parse falls back to a plain split with surrounding
    quote characters stripped per token, rather than silently yielding no
    tokens at all (which would read as "clean")."""
    try:
        return shlex.split(cmd, posix=True)
    except ValueError:
        return [p.strip("'\"") for p in cmd.split()]


def _wrapper_script_path(cmd):
    """The script FILE a single command segment directly invokes - `bash
    x.sh`, `sh x`, `./x`, `pwsh -File x.ps1`, `python(3) x.py`, `node x.js`
    - or None. One token, the interpreter's own first positional argument
    (or the bare ./x form), not a subcommand-taking tool like npx or
    terraform, and not a flag whose OWN argument is inline code or a
    module name rather than a file (see _NO_WRAPPER_FLAGS)."""
    parts = _tokenize(cmd)
    if not parts:
        return None
    head = parts[0]
    if head.startswith("./") or head.startswith("../"):
        return head
    base = os.path.basename(head).lower()
    if base.endswith(".exe"):
        base = base[:-4]
    if base == "pwsh":
        for i in range(1, len(parts)):
            low = parts[i].lower()
            if low == "-command":
                return None
            if low == "-file":
                return parts[i + 1] if i + 1 < len(parts) else None
        return None
    if base in _WRAPPER_INTERPRETERS:
        for p in parts[1:]:
            if p in _NO_WRAPPER_FLAGS:
                return None
            if p == "-n" and base in _POSIX_SHELLS:
                # Parse-only: the script named after -n is never executed
                # by THIS invocation, so there is nothing to follow.
                return None
            if not p.startswith("-"):
                return p
    return None


def _wrapper_paths_in_text(text):
    """Every wrapper-script invocation found in `text` - one command
    segment at a time (see _command_segments), used both for a single
    command string and for a wrapper script's own full content (many
    lines, possibly several segments each), so a script that itself calls
    another wrapper - directly or after `&&`/`;`/`|`/`||` - is followed."""
    paths = []
    for seg in _command_segments(text):
        p = _wrapper_script_path(seg)
        if p:
            paths.append(p)
    return paths


def _looks_like_script(path):
    """True if `path` (an existing, readable file) has a recognised script
    extension, or - for an extensionless file - starts with a shebang
    line. Decides whether a token following an interpreter is genuinely a
    SCRIPT FILE this scan should follow, or something else (a module name,
    a test id, ...) that merely happens to also exist under the repo."""
    ext = os.path.splitext(path)[1].lower()
    if ext in _SCRIPT_EXTENSIONS:
        return True
    if ext:
        return False
    try:
        with open(path, "rb") as fh:
            head = fh.read(2)
    except OSError:
        return False
    return head == b"#!"


def _classify_wrapper_candidate(token, repo_root):
    """(kind, real_path_or_None) for a token _wrapper_script_path found:

      "candidate" - a real, readable-looking, script-like file under
                    repo_root - follow it.
      "outside"   - it resolves to a real file OUTSIDE repo_root - cannot
                    verify it, and unlike a merely absent name this one
                    genuinely points somewhere; UNINSPECTED.
      "none"      - it does not exist under repo_root at all, or exists but
                    is not script-like (no recognised extension, no
                    shebang) - Codex round 3 FIX: `python -m pytest`'s
                    "pytest" resolves to nothing on disk; that is "no
                    wrapper here", not "could not tell".
    """
    candidate = token if os.path.isabs(token) else os.path.join(repo_root, token)
    real = os.path.realpath(candidate)
    root_real = os.path.realpath(repo_root)
    inside = real == root_real or real.startswith(root_real + os.sep)
    if not os.path.isfile(real):
        return ("none", None)
    if not inside:
        return ("outside", None)
    if not _looks_like_script(real):
        return ("none", None)
    return ("candidate", real)


def _read_bounded(path):
    """(True, text) or (False, reason). Never raises."""
    try:
        size = os.path.getsize(path)
        if size > REACH_SCAN_MAX_BYTES:
            return (False, f"too large ({size}B > {REACH_SCAN_MAX_BYTES}B cap)")
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as e:
        return (False, f"unreadable ({e})")
    if b"\x00" in raw[:8192]:
        return (False, "binary")
    return (True, raw.decode("utf-8", errors="replace"))


def scan_reach(run, repo_root):
    """Scan a rule's `run` commands for reach verbs, following wrapper
    scripts up to REACH_SCAN_MAX_DEPTH. Returns (status, detail):

      "verb"         - detail is the matched reach verb.
      "uninspected"  - detail is why the scan could not finish (a wrapper
                        resolved outside the repo, was too large, binary,
                        or the depth limit was hit while a real wrapper was
                        still queued). NEVER read as "local".
      "clean"        - detail is None: every command and every wrapper it
                        reaches (within the bound) was actually read and
                        named nothing - or named a token that turned out
                        not to be a wrapper at all (see _classify_wrapper_
                        candidate's "none").
    """
    visited = set()

    def scan(text, depth):
        text = _strip_comments(text)
        verb = _looks_remote_text(text)
        if verb:
            return ("verb", verb)
        wrapper_tokens = _wrapper_paths_in_text(text)
        real_candidates = []
        for tok in wrapper_tokens:
            kind, real = _classify_wrapper_candidate(tok, repo_root)
            if kind == "outside":
                return ("uninspected",
                        f"wrapper script {tok!r} resolves outside the repository")
            if kind == "candidate":
                real_candidates.append((tok, real))
        if not real_candidates:
            return ("clean", None)
        if depth >= REACH_SCAN_MAX_DEPTH:
            return ("uninspected",
                    f"depth limit ({REACH_SCAN_MAX_DEPTH}) reached following a wrapper script")
        for tok, real in real_candidates:
            if real in visited:
                continue
            visited.add(real)
            ok, payload = _read_bounded(real)
            if not ok:
                return ("uninspected",
                        f"wrapper script {tok!r} could not be read ({payload})")
            result = scan(payload, depth + 1)
            if result[0] != "clean":
                return result
        return ("clean", None)

    for cmd in run or []:
        if not isinstance(cmd, str):
            continue
        result = scan(cmd, 0)
        if result[0] != "clean":
            return result
    return ("clean", None)


def cmd_scan_reach():
    """CLI entry for verify-gate.ps1: reads {"run": [...], "root": "..."}
    from stdin, prints `status\\tdetail` (detail empty for "clean").
    verify-gate.sh and verify_price.py never call this - both already run
    inside python and import scan_reach directly."""
    try:
        payload = json.load(sys.stdin)
    except (OSError, ValueError):
        payload = {}
    run = payload.get("run") if isinstance(payload, dict) else None
    root = payload.get("root") if isinstance(payload, dict) else None
    status, detail = scan_reach(run or [], root or os.getcwd())
    print(f"{status}\t{detail or ''}")


def cmd_rule_key():
    """CLI entry for verify-gate.ps1: reads a JSON object from stdin with
    the same fields rule_key() hashes (paths, run, env, reach,
    requiresCleanTree - extra keys are ignored), prints the canonical key.
    verify-gate.sh never calls this - it imports rule_key directly, since
    it already runs inside python."""
    try:
        rule = json.load(sys.stdin)
    except (OSError, ValueError):
        rule = {}
    if not isinstance(rule, dict):
        rule = {}
    print(rule_key(rule))


def cmd_time_key(cmd):
    return hashlib.sha1(cmd.encode("utf-8")).hexdigest()[:16]


REASON_TEXT = {
    "chronic": "permanently over budget - run /crew:verify --all",
    "skipped": "SKIP (rc 77, environment absent) - not verified",
    "reach_declared": ("declared reach is not local - not run on Stop, "
                        "run /crew:verify --all"),
    "reach_undeclared": ("undeclared reach, looks like it leaves this "
                          "machine - declare `reach` or run /crew:verify --all"),
    "reach_uninspected": ("undeclared reach could not be verified - "
                           "declare `reach` or run /crew:verify --all"),
    "clean_tree_required": ("requires a clean working tree - not run on "
                             "Stop, run /crew:verify --all"),
}

# Kinds a matched rule can be classified as that mean "never ran this turn
# by construction" -- see cmd_sync's docstring. requiresCleanTree shares this
# set with the two reach kinds and chronic: all five are decided BEFORE the
# rule ever runs, so all five persist and get reported the same way.
_NEVER_RAN_KINDS = ("chronic", "reach_declared", "reach_undeclared",
                    "reach_uninspected", "clean_tree_required")


def cmd_sync():
    """Read a JSON payload from stdin:

        {"sha": "<HEAD>",
         "matched_rules": [{"key":..., "label":..., "kind": "normal"|
             "chronic"|"reach_declared"|"reach_undeclared"|
             "clean_tree_required", "reason":..., "cmds": [...],
             "unknown": bool}, ...],
         "cmd_log": [{"cmd":..., "status": "pass"|"skip77", "elapsed": N}, ...]}

    `matched_rules` is every rule that matched a changed path this turn,
    from the SAME matcher run that decided what to execute; `cmd_log` is
    only the commands that were ACTUALLY RUN (so an acutely budget-deferred
    rule's commands are simply absent from it).

    Classification, per matched rule:
      - chronic / reach_declared / reach_undeclared / clean_tree_required
        (see _NEVER_RAN_KINDS): never ran this turn by construction. Persist
        it, named, so it cannot go quiet once the sha marker advances past
        the commit where its own files last changed.
      - normal, but one of its commands is missing from cmd_log (an acute
        budget deferral this turn): leave any prior record entry untouched.
        The sha marker already refuses to advance while this is outstanding,
        so nothing here needs to say so a second time.
      - normal, and one of its commands came back rc=77: record "skipped".
        Not a pass, not a fail -- see verify-gate.sh/.ps1's SKIP handling.
      - normal, and every command passed: the rule is CLEAN. Any previous
        entry for it is cleared, and if it had no declared or cached cost
        (`unknown`), its measured elapsed time is written to the timings
        cache so the NEXT Stop can price it instead of running it forever.
    """
    try:
        payload = json.load(sys.stdin)
    except (OSError, ValueError):
        payload = {}
    sha = payload.get("sha") or ""
    matched = payload.get("matched_rules") or []
    cmd_log = payload.get("cmd_log") or []
    return _sync(sha, matched, cmd_log)


def _current_rule_keys():
    """The set of rule_key() values verify.json currently declares, or None
    if the map could not be read at all. None (not an empty set) is the
    unknown case: an unreadable map must not be read as "no rules exist",
    which would prune every standing obligation on a transient read error.
    Only a SUCCESSFULLY read map may prune anything."""
    try:
        with open(os.path.join(".crew", "verify.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return None
    rules = cfg.get("rules") if isinstance(cfg, dict) else None
    if not isinstance(rules, list):
        return None
    return {rule_key(r) for r in rules if isinstance(r, dict)}


def _sync(sha, matched, cmd_log):

    status_by_cmd = {}
    elapsed_by_cmd = {}
    for row in cmd_log:
        if not isinstance(row, dict):
            continue
        c = row.get("cmd")
        if not isinstance(c, str):
            continue
        status_by_cmd[c] = row.get("status")
        try:
            elapsed_by_cmd[c] = int(row.get("elapsed") or 0)
        except (TypeError, ValueError):
            elapsed_by_cmd[c] = 0

    record = _load(RECORD_PATH)
    entries = record.get("rules")
    if not isinstance(entries, dict):
        entries = {}

    timings = _load(TIMINGS_PATH)
    if not isinstance(timings.get("rules"), dict):
        timings["rules"] = {}

    for rule in matched:
        if not isinstance(rule, dict):
            continue
        key = rule.get("key")
        if not isinstance(key, str) or not key:
            continue
        label = rule.get("label", key)
        kind = rule.get("kind")
        if kind in _NEVER_RAN_KINDS:
            entries[key] = {
                "status": kind,
                "reason": rule.get("reason") or REASON_TEXT.get(kind, ""),
                "label": label,
                "sha": sha,
            }
            continue
        cmds = rule.get("cmds") or []
        if not cmds:
            continue
        statuses = [status_by_cmd.get(c) for c in cmds]
        if any(s is None for s in statuses):
            # At least one of this rule's commands never ran this turn --
            # an acute budget deferral. Leave whatever was recorded before
            # exactly as it was; the sha marker already will not advance.
            continue
        if any(s == "skip77" for s in statuses):
            entries[key] = {
                "status": "skipped",
                "reason": REASON_TEXT["skipped"],
                "label": label,
                "sha": sha,
            }
            continue
        # Every command this rule names ran and passed: clean.
        entries.pop(key, None)
        if rule.get("unknown"):
            # STORE EVEN 0s, as max(1, ceil(...)). `if total > 0` used to
            # discard a subsecond measurement outright, so a genuinely fast
            # rule with no declared `seconds` never got cached at all and
            # stayed "truly unknown" (mandatory, runs every Stop) forever -
            # the one case measure-and-cache exists for and the one case the
            # old guard silently excluded from it.
            total = sum(elapsed_by_cmd.get(c, 0) for c in cmds)
            timings["rules"][key] = max(1, math.ceil(total))

    # STALE OBLIGATIONS. A key here that verify.json no longer declares - the
    # rule was edited (rule_key is a content hash, so a changed `run` or
    # `paths` is a NEW key) or deleted outright - would otherwise sit in
    # `entries` forever, since nothing else ever visits a key absent from
    # THIS turn's `matched_rules`. Only prune when the current map was
    # actually readable (see _current_rule_keys) - an unreadable map must
    # not be read as "no rules exist" and silently clear every obligation.
    valid_keys = _current_rule_keys()
    if valid_keys is not None:
        for stale_key in [k for k in entries if k not in valid_keys]:
            del entries[stale_key]

    record["rules"] = entries
    record_err = _save(RECORD_PATH, record)
    timings_err = _save(TIMINGS_PATH, timings)
    failure = record_err or timings_err
    if failure:
        # NEITHER marker may advance on a record that was never actually
        # written - the caller (verify-gate.sh/.ps1) checks THIS process's
        # exit code and skips both record_verified and the fingerprint write
        # when it is non-zero. Printing "NOT VERIFIED" entries below would be
        # honest about the STALE state on disk but silent about why nothing
        # NEW made it there - say that first.
        print(f"verify-gate: could not persist the record ({failure}); "
              f"NOT advancing the marker")

    for key, info in sorted(entries.items(), key=lambda kv: kv[1].get("label", kv[0])):
        print(f"verify-gate: NOT VERIFIED ON THIS TREE - "
              f"{info.get('label', key)}: {info.get('reason', '')}")
    return failure is None


def cmd_report():
    """Read-only: print the standing reminders without changing anything.
    Used when nothing ran this turn (CHANGED was empty) so a permanently
    deferred rule is still not allowed to go quiet forever."""
    record = _load(RECORD_PATH)
    entries = record.get("rules")
    if not isinstance(entries, dict):
        return
    for key, info in sorted(entries.items(), key=lambda kv: kv[1].get("label", kv[0])):
        print(f"verify-gate: NOT VERIFIED ON THIS TREE - "
              f"{info.get('label', key)}: {info.get('reason', '')}")


def cmd_timings_get():
    """Print `<ruleKey><TAB><seconds>` for every cached measurement, for the
    matcher to fold into its budget arithmetic as '(measured, not
    declared)'. Missing/corrupt cache prints nothing -- unknown stays
    unknown, which keeps a rule mandatory exactly as before this feature
    existed."""
    timings = _load(TIMINGS_PATH)
    rules = timings.get("rules")
    if not isinstance(rules, dict):
        return
    for key, secs in rules.items():
        if isinstance(secs, int) and secs > 0:
            print(f"{key}\t{secs}")


def main(argv):
    usage = "usage: verify_record.py sync|report|timings-get|rule-key|scan-reach"
    if len(argv) < 2:
        print(usage, file=sys.stderr)
        return 2
    cmd = argv[1]
    if cmd == "sync":
        # Non-zero exit is the signal the gate scripts check: a record that
        # could not be persisted must not let the sha marker or fingerprint
        # advance either. See _sync's "STALE OBLIGATIONS" / failure handling.
        return 0 if cmd_sync() else 1
    if cmd == "report":
        cmd_report()
    elif cmd == "timings-get":
        cmd_timings_get()
    elif cmd == "rule-key":
        cmd_rule_key()
    elif cmd == "scan-reach":
        cmd_scan_reach()
    else:
        print(usage, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
