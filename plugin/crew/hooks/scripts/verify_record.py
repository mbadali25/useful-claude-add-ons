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
# ONE function, called by all three (verify-gate.sh in-process, .ps1 via the
# `scan-reach` CLI, verify_price.py in-process).
#
# REJECT-ONLY, as of Codex round 4. Rounds 2-3 tried to APPROVE a command as
# safe by reading it: follow the wrapper it names, follow what THAT wrapper
# names, check the target looks like a script, and call it clean if nothing
# turned up. Every round of review found a new way to make that approval
# wrong - a compound `true && bash inner.sh` the segmenter did not split, an
# inline `bash -c 'bash inner.sh'` hiding a nested wrapper inside a STRING
# rather than a FILE, a `cd tools && bash inner.sh` resolving against the
# wrong base, an extensionless `check` with no shebang the heuristic waved
# through - four BLOCKs in two rounds, three of them the SAME shape: a new
# way to make a wrapper invisible to whatever this scan was trying to READ
# THROUGH. That is an arms race, and static inspection does not win it -
# nothing that only reads text can enumerate every way a command can end up
# running something else.
#
# So this scan no longer tries to approve anything. It can only REJECT:
#   (a) a reach verb appears anywhere in the command text, or in a directly-
#       named wrapper file's content, if that file can be read - "verb".
#   (b) the command invokes ANY script or interpreter-with-an-argument at
#       all (any token that resolves to an existing repo file, any
#       recognised interpreter followed by a non-flag argument anywhere
#       after it, or a `cd`) - "wrapper". Existence is enough; there is no
#       more extension/shebang test, because the arms race was never about
#       whether the scan could prove a target harmful, only whether it
#       could prove one harmless, and it never reliably could.
#   (c) neither: "local" - safe to run undeclared.
# There is no more "uninspected". A wrapper this scan cannot read is not a
# separate, softer category - it is still "wrapper", the same as one it
# reads and finds nothing verb-shaped in. Static inspection is USED only to
# defer; it is never the reason something is allowed to run.
#
# What this buys back: BLOCK verify_record.py:383 (a preceding `cd` changing
# the base a wrapper path resolves against) stops being reachable at all,
# because `cd` ANYWHERE in the command is itself grounds for (b) - the scan
# never needs to know where a `cd` would land, since it never tries to
# resolve anything past it. BLOCK verify_record.py:387 (an extensionless,
# shebang-less script) stops being reachable because existence alone is
# enough to trigger (b) - there is no "does it look like a script" gate left
# to route around. BLOCK verify_record.py:321 (`bash -c 'bash inner.sh'`,
# a wrapper invocation hidden inside an INLINE STRING rather than a file)
# stops being reachable because "any interpreter followed by a non-flag
# argument anywhere after it" catches the outer `bash -c '...'` on its own
# terms - it does not need to parse what is inside the string, because an
# interpreter invoked with an argument is ALREADY enough for (b), whatever
# that argument turns out to contain.
#
# What is deliberately NOT covered any more: (c)'s promise that "no verb, no
# wrapper" commands run undeclared is now much narrower than round 3's, and
# on purpose - `python3 -m pytest ...` (an INTERPRETER followed by a
# non-flag argument, `-m`'s module name included) now classifies as (b),
# where round 3's FIX specifically carved it out. That carve-out was
# exactly the kind of case-by-case cleverness this redesign stops doing:
# distinguishing "this token is a module name, not a file" from "this token
# is a file" is one more thing an attacker's command shape can get wrong on
# purpose, and the map is the place to say a command is safe, not the
# scanner. See THIS repo's own .crew/verify.json, which now declares
# `"reach": "local"` on every rule this reclassifies - test_28 checks it.
#
# Parse-only is the one narrow exception kept from round 3, unrelated to any
# of this: `bash -n X` / `sh -n X` / `dash -n X` / `zsh -n X` read X for
# SYNTAX ONLY and never execute a line of it, so whatever X contains cannot
# run under this specific invocation - (c), unconditionally, regardless of
# X's content. Nothing else about -n's target is inspected, because nothing
# needs to be: it never runs.
REACH_VERBS = ("ssm", "ssh", "curl", "aws", "az", "gh", "psql", "mysql")
_REACH_RE = re.compile(r"\b(" + "|".join(re.escape(v) for v in REACH_VERBS) + r")\b")
# Recognised interpreters AND recognised script-running tools - anything
# that can be handed a file and made to execute it. `powershell` (Windows'
# built-in, distinct from `pwsh`) and `ruby`/`perl` were never in earlier
# rounds' list; added here since (b) now depends on this list being
# complete rather than merely "complete enough for the cases seen so far".
_INTERPRETERS = ("bash", "sh", "dash", "zsh", "pwsh", "powershell",
                 "python", "python3", "py", "node", "ruby", "perl")
_POSIX_SHELLS = ("bash", "sh", "dash", "zsh")
# A WHOLE-LINE comment (bash/PowerShell/python all use `#`) is prose, not
# code - a wrapper script's own comment describing what it does NOT do
# (`_verify/smoke.sh`: "there is no service to curl and no ...") used to
# verb-match on the strength of that sentence alone and deferred two rules
# in this repo's own .crew/verify.json on every Stop, forever, since
# smoke.sh is the default gate. Stripped BEFORE verb matching. A TRAILING
# comment on a code line is left alone - a verb appearing in actual code
# must still match even if the same line also carries a `# comment` after
# it - so this only ever drops a line whose first non-blank character is
# `#`. Still needed under the reject-only design: it changes whether (a)
# fires (a verb in a comment must not), not whether (b) does (comment text
# was never a wrapper-detection signal).
_PS_BLOCK_COMMENT_RE = re.compile(r"<#.*?#>", re.S)


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
    only a line whose first non-blank character is `#` is dropped."""
    if not text:
        return text
    text = _PS_BLOCK_COMMENT_RE.sub("", text)
    return "\n".join(line for line in text.splitlines()
                      if not line.lstrip().startswith("#"))


def _tokenize(cmd):
    """Shell-aware tokens for one command string. `shlex.split(posix=True)`
    strips quote characters properly (`bash "local.sh"` -> ['bash',
    'local.sh'], not the literal '"local.sh"'); an unbalanced quote shlex
    cannot parse falls back to a plain split with surrounding quote
    characters stripped per token, rather than silently yielding no tokens
    at all (which would read as safe)."""
    try:
        return shlex.split(cmd, posix=True)
    except ValueError:
        return [p.strip("'\"") for p in cmd.split()]


def _base_name(token):
    """The interpreter/executable name a token would resolve to on PATH,
    lower-cased and with a trailing .exe dropped - `Bash`, `BASH.EXE` and
    `bash` are all the same interpreter for this check's purposes."""
    base = os.path.basename(token).lower()
    if base.endswith(".exe"):
        base = base[:-4]
    return base


def _resolves_to_repo_file(token, repo_root):
    """The real, symlink-resolved path if `token` names an existing FILE
    under repo_root (any extension or none - existence is the only test;
    see the module docstring for why the extension/shebang heuristic was
    removed), else None. A file that exists but resolves OUTSIDE repo_root
    (an absolute path, or a symlink escaping it) does not count as "under
    the repo" and returns None here - it can still trigger (b) through the
    interpreter-token check below if it was invoked via a recognised
    interpreter, which covers every case actually seen; a bare invocation
    of something outside the repo with no interpreter prefix is not one
    this scan is asked to catch."""
    candidate = token if os.path.isabs(token) else os.path.join(repo_root, token)
    real = os.path.realpath(candidate)
    root_real = os.path.realpath(repo_root)
    inside = real == root_real or real.startswith(root_real + os.sep)
    if inside and os.path.isfile(real):
        return real
    return None


def _read_best_effort(path):
    """The file's text, or None. Never raises, never bounds size (the 256
    KiB cap was a round-2/3 approval-path artefact - see the module
    docstring; this read is used only to possibly UPGRADE a "wrapper"
    verdict to the more specific "verb" one, never to downgrade it, so a
    read that fails just means the generic wrapper reason is kept)."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    return raw.decode("utf-8", errors="replace")


def _classify_command(cmd, repo_root):
    """Classify ONE command string under the reject-only reach model.
    Returns (status, detail):

      "verb"    - detail is the matched reach verb - found in the command
                  text itself, or in a directly-named wrapper file's
                  content if that file could be read.
      "wrapper" - detail is a short human-readable reason. The command
                  invokes something (a script, an interpreter with an
                  argument, a `cd`) that could run anything; inspection
                  can reject this, never approve it.
      "local"   - detail is None. No verb, no wrapper, no inline shell,
                  no `cd`.
    """
    stripped = _strip_comments(cmd)
    verb = _looks_remote_text(stripped)
    if verb:
        return ("verb", verb)

    parts = _tokenize(cmd)
    if not parts:
        return ("local", None)
    lowered = [p.lower() for p in parts]

    if "cd" in lowered:
        return ("wrapper", "a `cd` appears in the command")

    head_base = _base_name(parts[0])
    if head_base in _POSIX_SHELLS and "-n" in parts[1:]:
        # Parse-only: nothing after -n is ever executed by THIS
        # invocation, so nothing about its target needs inspecting.
        return ("local", None)

    interpreter_reason = None
    for i, p in enumerate(parts):
        if _base_name(p) in _INTERPRETERS:
            for later in parts[i + 1:]:
                if not later.startswith("-"):
                    interpreter_reason = interpreter_reason or (
                        f"`{p}` is followed by an argument")
                    break

    verb_from_file = None
    file_reason = None
    for p in parts:
        real = _resolves_to_repo_file(p, repo_root)
        if real is None:
            continue
        file_reason = file_reason or f"invokes an existing repo file {p!r}"
        text = _read_best_effort(real)
        if text is None:
            continue
        v = _looks_remote_text(_strip_comments(text))
        if v:
            verb_from_file = v
            break

    if verb_from_file:
        return ("verb", verb_from_file)
    if interpreter_reason or file_reason:
        return ("wrapper", interpreter_reason or file_reason)
    return ("local", None)


def scan_reach(run, repo_root):
    """Classify every command in a rule's `run` under the reject-only
    model (see _classify_command). Returns (status, detail) for the FIRST
    command that is not "local" - "verb" takes priority over "wrapper" for
    the SAME command, but between commands this is simply run order.
    "local" (detail None) only when every command in `run` is local."""
    for cmd in run or []:
        if not isinstance(cmd, str):
            continue
        result = _classify_command(cmd, repo_root)
        if result[0] != "local":
            return result
    return ("local", None)


def cmd_scan_reach():
    """CLI entry for verify-gate.ps1: reads {"run": [...], "root": "..."}
    from stdin, prints `status\\tdetail` (detail empty for "local").
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
    "reach_undeclared": ("remote verb detected - declare `reach` or run "
                          "/crew:verify --all"),
    # Renamed from "reach_uninspected" in Codex round 4: the reject-only
    # redesign (see scan_reach's module docstring) means a wrapper the
    # scanner cannot fully verify is not a SOFTER, "could not tell" bucket
    # any more - it is classified the exact same way as any other wrapper
    # invocation, verified or not. "Wrapper" names what actually happened
    # (an unattended script or interpreter invocation was found), not an
    # epistemic state about how well it was read.
    "reach_wrapper": ("wrapper or inline shell invocation - declare "
                       '`"reach": "local"` (or network/host) to run it on Stop'),
    "clean_tree_required": ("requires a clean working tree - not run on "
                             "Stop, run /crew:verify --all"),
}

# Kinds a matched rule can be classified as that mean "never ran this turn
# by construction" -- see cmd_sync's docstring. requiresCleanTree shares this
# set with the two reach kinds and chronic: all five are decided BEFORE the
# rule ever runs, so all five persist and get reported the same way.
_NEVER_RAN_KINDS = ("chronic", "reach_declared", "reach_undeclared",
                    "reach_wrapper", "clean_tree_required")


def cmd_sync():
    """Read a JSON payload from stdin:

        {"sha": "<HEAD>",
         "matched_rules": [{"key":..., "label":..., "kind": "normal"|
             "chronic"|"reach_declared"|"reach_undeclared"|"reach_wrapper"|
             "clean_tree_required", "reason":..., "cmds": [...],
             "unknown": bool}, ...],
         "cmd_log": [{"cmd":..., "status": "pass"|"skip77", "elapsed": N}, ...]}

    `matched_rules` is every rule that matched a changed path this turn,
    from the SAME matcher run that decided what to execute; `cmd_log` is
    only the commands that were ACTUALLY RUN (so an acutely budget-deferred
    rule's commands are simply absent from it).

    Classification, per matched rule:
      - chronic / reach_declared / reach_undeclared / reach_wrapper /
        clean_tree_required (see _NEVER_RAN_KINDS): never ran this turn by
        construction. Persist it, named, so it cannot go quiet once the
        sha marker advances past the commit where its own files last
        changed.
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
