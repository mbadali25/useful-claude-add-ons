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
_WRAPPER_INTERPRETERS = ("bash", "sh", "python", "python3", "pwsh")
REACH_SCAN_MAX_DEPTH = 3
REACH_SCAN_MAX_BYTES = 256 * 1024


def _looks_remote_text(text):
    if not text:
        return None
    m = _REACH_RE.search(text)
    return m.group(1) if m else None


def _wrapper_script_path(cmd):
    """The script FILE a single command line directly invokes - `bash x.sh`,
    `sh x`, `./x`, `pwsh -File x.ps1`, `python(3) x.py` - or None. One
    token, the interpreter's own first positional argument (or the bare
    ./x form), not a subcommand-taking tool like npx or terraform."""
    parts = cmd.split()
    if not parts:
        return None
    head = parts[0]
    if head.startswith("./") or head.startswith("../"):
        return head
    base = os.path.basename(head).lower()
    if base.endswith(".exe"):
        base = base[:-4]
    if base == "pwsh":
        for i in range(1, len(parts) - 1):
            if parts[i].lower() == "-file":
                return parts[i + 1]
        return None
    if base in _WRAPPER_INTERPRETERS:
        for p in parts[1:]:
            if p == "-c":
                # bash/sh/python(3) all use -c for INLINE code, not a
                # script file - `python -c "raise SystemExit(1)"` split()s
                # to ['python', '-c', '"raise', 'SystemExit(1)"'], and
                # without this check the first non-flag token ('"raise')
                # was returned as a "wrapper script", which then failed to
                # resolve inside the repo and forced the whole rule to
                # reach_uninspected - silently excluding it from Stop
                # entirely. There is no file to follow here; the inline
                # code is already covered by the verb scan over the whole
                # command string, above this function's caller.
                return None
            if not p.startswith("-"):
                return p
    return None


def _wrapper_paths_in_text(text):
    """Every wrapper-script invocation found on any LINE of `text` - used
    both for a single command string (one line) and for a wrapper script's
    own full content (many), so a script that itself calls another wrapper
    is followed."""
    paths = []
    for line in (text or "").splitlines():
        p = _wrapper_script_path(line.strip())
        if p:
            paths.append(p)
    return paths


def _resolve_within_root(path, repo_root):
    """Absolute, symlink-resolved path, or None if it is not a real file
    inside repo_root. `os.path.realpath` on both sides so a symlink cannot
    be used to point the scan at a file outside the repository."""
    candidate = path if os.path.isabs(path) else os.path.join(repo_root, path)
    real = os.path.realpath(candidate)
    root_real = os.path.realpath(repo_root)
    if real != root_real and not real.startswith(root_real + os.sep):
        return None
    return real


def _read_bounded(path):
    """(True, text) or (False, reason). Never raises."""
    try:
        if not os.path.isfile(path):
            return (False, "missing")
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
                        was missing, too large, binary, outside the repo,
                        or the depth limit was hit while more wrappers were
                        still queued). NEVER read as "local".
      "clean"        - detail is None: every command and every wrapper it
                        reaches (within the bound) was actually read and
                        named nothing.
    """
    visited = set()

    def scan(text, depth):
        verb = _looks_remote_text(text)
        if verb:
            return ("verb", verb)
        wrapper_paths = _wrapper_paths_in_text(text)
        if not wrapper_paths:
            return ("clean", None)
        if depth >= REACH_SCAN_MAX_DEPTH:
            return ("uninspected",
                    f"depth limit ({REACH_SCAN_MAX_DEPTH}) reached following a wrapper script")
        for wp in wrapper_paths:
            real = _resolve_within_root(wp, repo_root)
            if real is None:
                return ("uninspected",
                        f"wrapper script {wp!r} resolves outside the repository")
            if real in visited:
                continue
            visited.add(real)
            ok, payload = _read_bounded(real)
            if not ok:
                return ("uninspected",
                        f"wrapper script {wp!r} could not be read ({payload})")
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
