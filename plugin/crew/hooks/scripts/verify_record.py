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


def _load_state(path):
    """(data, state): state is "absent" (no file), "ok", or "corrupt" (a
    file is there but is not a JSON object). Round 8 (verify_record.py:54):
    a corrupt record used to load as {} and the standing obligations in it
    were simply gone - the next successful sync then wrote an empty record
    and the marker advanced past work nothing had verified. Absent and
    corrupt must be told apart, because only one of them means "we have
    lost track of what is owed"."""
    if not os.path.lexists(path):
        return {}, "absent"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}, "corrupt"
    if not isinstance(data, dict):
        return {}, "corrupt"
    return data, "ok"


def _load(path):
    return _load_state(path)[0]


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
# WE STOP MODELLING SHELL, as of Codex round 6. Rounds 2-5 each tried to
# read THROUGH one more layer of shell syntax to find what a command
# actually runs - follow the wrapper it names, split it into the segments a
# shell would run separately, follow a `$( ... )` substitution's own
# contents - and every round of review found a new shape that defeated
# whatever the previous round had just added: subshell parentheses glued to
# a path, `-n` granted by mere PRESENCE anywhere in the token list rather
# than its actual position, a compound hidden inside a substitution the
# segmenter had not been told to open. Five rounds, the same lesson each
# time: a hand-rolled shell grammar is never finished, because "model shell
# more completely" is not a fixable bug, it is the wrong approach.
#
# So this scan does not parse shell at all any more. It is two rules:
#   (1) If the command string contains ANY shell metacharacter - anything
#       that could combine, substitute, quote, glob, redirect or comment -
#       the map author has written something this scan will not try to
#       read. Defer, unconditionally. No exception for `2>&1`, none for a
#       trailing `#` comment: a character on the list means "declare
#       reach", full stop, not "declare reach unless the shape is one we
#       recognise as probably fine" - recognising shapes is exactly the
#       modelling this round stops doing.
#   (2) Only once NOTHING on that list is present does whitespace-only
#       splitting become safe (there is no quoting left to get wrong), and
#       classification proceeds token by token: a reach verb anywhere,
#       then a short, closed set of interpreter-flag rules (see
#       _classify_command's docstring), then plain existing-file
#       resolution for anything else.
# There is no more file-content reading anywhere in this module - not even
# one level. A wrapper is "wrapper", full stop, whether or not this scan
# could have read what is inside it; reading it was always in service of
# possibly finding a MORE SPECIFIC reason ("verb" instead of generic
# "wrapper"), never of approving anything, so removing it changes no
# decision, only how precisely a few notices are worded.
REACH_VERBS = ("ssm", "ssh", "curl", "aws", "az", "gh", "psql", "mysql")
_REACH_RE = re.compile(r"\b(" + "|".join(re.escape(v) for v in REACH_VERBS) + r")\b")
# Recognised interpreters AND recognised script-running tools - anything
# that can be handed a file and made to execute it. `powershell` (Windows'
# built-in, distinct from `pwsh`) and `ruby`/`perl` were added in round 4.
_INTERPRETERS = ("bash", "sh", "dash", "zsh", "pwsh", "powershell",
                 "python", "python3", "py", "node", "ruby", "perl")
# Per-interpreter flag semantics (round 7): only these shells treat -n as
# parse-only, and only these Pythons treat -m as a module name.
_POSIX_SHELLS = frozenset({"bash", "sh", "dash", "zsh"})
_PYTHONS = frozenset({"python", "python3", "py"})
# Codex round 6 BLOCKs 352/474/543 were three different ways a hand-rolled
# shell grammar missed something it was reading through: subshell parens
# glued to a path (`(./check.sh)`), `-n` granted by mere presence anywhere
# in the token list rather than its actual position (`bash check.sh -n`),
# and a command substitution's contents bypassing segmentation entirely
# (`echo "$(true;./check.sh)"`). Every one of these characters, present
# ANYWHERE in the command, means "this scan will not try to read this" -
# not "unless the shape looks like a redirection we know about" (round 5's
# `2>&1` exception is GONE: no exceptions this round, by design).
_SHELL_METACHARS = frozenset('()$;&|<>`"\'\\{}*?[]~#!' + "\n\t")


def _has_shell_metachar(cmd):
    return any(c in _SHELL_METACHARS for c in cmd)


def _looks_remote_text(text):
    if not text:
        return None
    m = _REACH_RE.search(text)
    return m.group(1) if m else None


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
    under repo_root (any extension or none - existence is the only test),
    else None. A file that exists but resolves OUTSIDE repo_root (an
    absolute path, or a symlink escaping it) does not count as "under the
    repo" and returns None here."""
    candidate = token if os.path.isabs(token) else os.path.join(repo_root, token)
    real = os.path.realpath(candidate)
    root_real = os.path.realpath(repo_root)
    inside = real == root_real or real.startswith(root_real + os.sep)
    if inside and os.path.isfile(real):
        return real
    return None


def _classify_command(cmd, repo_root):
    """Classify ONE command string. Returns (status, detail):

      "verb"    - detail is the matched reach verb, found as a whole word
                  in the command text.
      "syntax"  - detail is None. The command contains a shell
                  metacharacter (see _SHELL_METACHARS) this scan will not
                  try to read through; it is deferred unconditionally,
                  before anything else about it is examined.
      "wrapper" - detail is a short human-readable reason: the command
                  invokes something (an interpreter's inline-code/script
                  flag, or a token that resolves to an existing repo
                  file) that could run anything.
      "local"   - detail is None. No metacharacter, no verb, no wrapper.

    Once (1) `_has_shell_metachar` has cleared the command, whitespace is
    the only remaining delimiter that could possibly mean anything (no
    quoting survives to make a whitespace-split wrong), so tokenising is
    `cmd.split()` - nothing shell-aware needed, or wanted.

    Interpreter-flag rules, checked only when token[0] is a recognised
    interpreter, in this order:
      - `-n` grants the parse-only exemption ONLY when it is EXACTLY
        token[1] and there is EXACTLY ONE further token - `bash -n a.sh`
        is parse-only; `bash a.sh -n` is not (that argument order never
        makes bash treat -n as a parse-only flag at all), and neither is
        `bash -n a.sh b.sh` (round 6 BLOCK verify_record.py:474: -n used
        to be granted by mere PRESENCE in the token list, not its actual
        position and arity).
      - `-m` as token[1] names a MODULE, never a file - local,
        unconditionally, regardless of what follows (`python3 -m pytest
        x -q` is local).
      - `-c` / `-Command` / `-File` as token[1] name inline code or a
        script argument - wrapper, unconditionally.
      - any other token from token[1] onward that resolves to an existing
        repo file - wrapper.
      - otherwise: local.
    Otherwise (token[0] is not a recognised interpreter): any token at all
    that resolves to an existing repo file - wrapper; otherwise local.
    """
    if _has_shell_metachar(cmd):
        return ("syntax", None)

    parts = cmd.split()
    if not parts:
        return ("local", None)

    verb = _looks_remote_text(cmd)
    if verb:
        return ("verb", verb)

    head_base = _base_name(parts[0])
    if head_base in _INTERPRETERS:
        # Round 7 (verify_record.py:306, :313): the flag exemptions are
        # PER INTERPRETER, not interpreter-wide - `-n` is parse-only for
        # POSIX shells alone (`perl -n x.pl` EXECUTES x.pl), `-m` names a
        # module for Python alone (`bash -m x.sh` enables job control and
        # EXECUTES x.sh). And an interpreter given ANY non-flag argument is
        # running a script whether or not that path resolves inside the
        # repo (`python ../outside.py` executes) - so the decision no
        # longer consults the filesystem at all.
        if head_base in _POSIX_SHELLS and len(parts) == 3 and parts[1] == "-n":
            return ("local", None)
        if head_base in _PYTHONS and len(parts) >= 2 and parts[1] == "-m":
            return ("local", None)
        if len(parts) >= 2 and parts[1] in ("-c", "-Command", "-File"):
            return ("wrapper", f"`{parts[1]}` names inline code or a script argument")
        for p in parts[1:]:
            if not p.startswith("-"):
                return ("wrapper", f"interpreter given a script argument {p!r}")
        return ("local", None)

    for p in parts:
        if _resolves_to_repo_file(p, repo_root) is not None:
            return ("wrapper", f"invokes an existing repo file {p!r}")
    return ("local", None)


def scan_reach(run, repo_root):
    """Classify every command in a rule's `run` (see _classify_command).
    Returns (status, detail) for the FIRST command that is not "local" -
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
    # Codex round 6: a command containing ANY shell metacharacter is a
    # SEPARATE kind from "reach_wrapper" - not because it is handled any
    # differently (both defer, both persist, both need `reach` declared),
    # but because the reason a map author reads should name the actual
    # trigger (shell syntax this scan will not try to read through) rather
    # than the generic wrapper phrasing, which used to say "invokes an
    # existing repo file" for a command that may not even name one.
    "reach_syntax": ('shell syntax in an undeclared rule - declare '
                      '`"reach": "local"` (or network/host) to run it on Stop'),
    "clean_tree_required": ("requires a clean working tree - not run on "
                             "Stop, run /crew:verify --all"),
}

# Kinds a matched rule can be classified as that mean "never ran this turn
# by construction" -- see cmd_sync's docstring. requiresCleanTree shares this
# set with the reach kinds and chronic: all six are decided BEFORE the rule
# ever runs, so all six persist and get reported the same way.
_NEVER_RAN_KINDS = ("chronic", "reach_declared", "reach_undeclared",
                    "reach_wrapper", "reach_syntax", "clean_tree_required")


def cmd_sync():
    """Read a JSON payload from stdin:

        {"sha": "<HEAD>",
         "matched_rules": [{"key":..., "label":..., "kind": "normal"|
             "chronic"|"reach_declared"|"reach_undeclared"|"reach_wrapper"|
             "reach_syntax"|"clean_tree_required", "reason":..., "cmds": [...],
             "unknown": bool}, ...],
         "cmd_log": [{"cmd":..., "status": "pass"|"skip77", "elapsed": N}, ...]}

    `matched_rules` is every rule that matched a changed path this turn,
    from the SAME matcher run that decided what to execute; `cmd_log` is
    only the commands that were ACTUALLY RUN (so an acutely budget-deferred
    rule's commands are simply absent from it).

    Classification, per matched rule:
      - chronic / reach_declared / reach_undeclared / reach_wrapper /
        reach_syntax / clean_tree_required (see _NEVER_RAN_KINDS): never
        ran this turn by construction. Persist it, named, so it cannot go
        quiet once the sha marker advances past the commit where its own
        files last changed.
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
    all_run = bool(payload.get("all")) if isinstance(payload, dict) else False
    return _sync(sha, matched, cmd_log, all_run)


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


def _sync(sha, matched, cmd_log, all_run=False):

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

    record, record_state = _load_state(RECORD_PATH)
    entries = record.get("rules")
    if not isinstance(entries, dict):
        entries = {}
    # Round 8 (verify_record.py:54): a corrupt record means the obligations
    # it held are UNKNOWN, and unknown never collapses into "none". Until a
    # --all run rebuilds the record from a full pass, the sync refuses (the
    # gate then withholds both markers) and says why, every turn. On --all
    # every rule ran, so the rebuild below is the recovery.
    record_lost = record_state == "corrupt" and not all_run

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
    orphaned = 0
    if valid_keys is not None:
        for stale_key in [k for k in entries if k not in valid_keys]:
            info = entries[stale_key]
            # Round 8 (verify_record.py:558): an entry whose rule was edited
            # (its content hash changed) or removed is NOT thereby verified.
            # A resolved entry can go; an unresolved one stays, marked
            # orphaned, reported every turn, and holds the marker until a
            # --all run (where every rule ran) clears it. Deleting it used
            # to let one edit to a rule's `paths` erase the obligation and
            # advance the marker with zero commands run.
            # Every entry here IS an unresolved obligation - a rule that
            # passed is removed from `entries`, never stored - so a stale
            # key is orphaned, not resolved, unless this is an --all run.
            if all_run or not isinstance(info, dict):
                del entries[stale_key]
            else:
                if not info.get("orphaned"):
                    info["orphaned"] = True
                    info["reason"] = (info.get("reason", "") +
                                      " [rule edited or removed since - still unverified; "
                                      "run /crew:verify --all]")
                orphaned += 1

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
    if record_lost:
        print("verify-gate: the verified record was unreadable, so the obligations it "
              "held are UNKNOWN; NOT advancing the marker - run /crew:verify --all to rebuild it")
        return False
    if orphaned:
        print(f"verify-gate: {orphaned} unverified obligation(s) belong to a rule that was "
              "edited or removed; NOT advancing the marker - run /crew:verify --all")
        return False
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
