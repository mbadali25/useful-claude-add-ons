"""The one place `/crew:init`, `/crew:migrate` and `/crew:onboard` decide what
to do about `context.autoClear`, so the three command files relay a plan
instead of each carrying their own copy of it.

Schema (owned by `crew_state.AUTOCLEAR_DEFAULTS` / `crew_platform._AUTOCLEAR_
METHODS`; not restated here beyond what this module needs to reason about):
`enabled` only the global layer may turn on; `method` defaults to `"auto"`,
which resolves to a tmux pane on Linux/macOS/WSL, to `notify` on native
Windows with no tmux pane, and never to `sendkeys` -- that is opt-in only,
requested by name.

Things this module exists to make impossible by construction rather than
by prompt discipline:

  * writing `sendkeys` to the global file without an explicit yes
    (`write_autoclear_method`'s `consent` parameter)
  * turning `enabled` on machine-wide without an explicit yes
    (`write_autoclear_enabled`'s `consent` parameter)
  * a repo's dead `enabled: true` (1.0 does nothing with it) or its illegal
    `onlyRepos`/`onlySessions` copy surviving a migration silently
    (`strip_repo_duplication`)
  * a machine-global `enabled: true` with `onlyRepos: null` arming every
    crew repo on the box without that widening ever being said out loud
    (`detect_onlyRepos_widening`)
  * converting only one of `.crew/config.json` (what every autoClear sender
    reads) and `.crew/crew.json` (what `crew_migrate.py` also writes,
    unconverted) and leaving the other one's legacy value live
    (`apply_migrate_to_repo`)
  * a malformed machine-global file being merged onto crew_config's
    intentional `{}` collapse and overwritten with only the proposed keys
    (`_require_global_readable`, called by every function that writes there)
  * a failed global `onlyRepos` write leaving a repo's opt-in already
    stripped with no record of the widening anywhere
    (`apply_migrate_to_repo`'s write ordering)

Every message-producing function here is covered by
`test_no_forbidden_words` in `tests/test_autoclear_setup.py`: nothing this
module prints may say "cleared" or "compacted" -- notify tells you it is
*safe* to run the command yourself, it does not claim the command ran.

Standard library only, plus `crew_config` for the actual global-file I/O
(`read_global_config`, `plan_global_write`, `write_global_config`) so there is
exactly one writer of `~/.claude/crew/config.json` in this plugin.
"""

import argparse
import copy
import json
import os
import sys

import crew_backup
import crew_config

FORBIDDEN_WORDS = ("cleared", "compacted")


class GlobalConfigUnreadable(RuntimeError):
    """The machine-global config file exists but does not parse as a JSON
    object. Distinct from "absent" (which every write below treats as an
    empty file to build on) and from the read-only merge collapse
    `crew_config.read_global_config` performs on purpose for
    `resolve_config`'s never-raise contract (see that function's
    docstring). Writing over an unreadable file through that collapse
    would silently replace it with just the keys this run proposed,
    discarding whatever else the file held -- this exception is how every
    write path here refuses that instead."""


def _global_file_problem(path=None):
    """`None` when the machine-global file at `path` (default
    `crew_config.GLOBAL_CONFIG_PATH`) is absent or parses as a JSON object;
    otherwise a human-readable reason it does not.

    Deliberately NOT `crew_config.read_global_config`, whose own docstring
    states it collapses "absent" and "malformed" to the identical `{}` --
    correct for `resolve_config`, reached from a SessionStart hook that
    must never raise, but wrong for a WRITE: `plan_global_write`/
    `write_global_config` merge updates onto whatever `read_global_config`
    returns, so a malformed file reaching them unflagged means "apply the
    proposed default" replaces the file with only the proposed keys.
    """
    real_path = crew_config.GLOBAL_CONFIG_PATH if path is None else path
    try:
        with open(real_path, "r", encoding="utf-8-sig") as handle:
            text = handle.read()
    except FileNotFoundError:
        return None
    except OSError as exc:
        return f"could not read {real_path} ({type(exc).__name__})"
    except UnicodeDecodeError as exc:
        # Text-mode `open` decodes eagerly on `.read()` -- bytes that are
        # not valid UTF-8 raise here, before `json.loads` ever runs. Left
        # uncaught this is a crash out of a plain read helper rather than
        # this function's own "unreadable" result; every caller already
        # expects a STRING reason or `None`, never an exception escaping
        # this deep for a file that is simply not text at all.
        return f"{real_path} is not valid UTF-8 ({exc})"
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        return f"{real_path} does not parse as JSON ({exc})"
    if not isinstance(parsed, dict):
        return f"{real_path} holds a JSON {type(parsed).__name__}, not an object"
    return None


def _require_global_readable(path=None):
    """Raise `GlobalConfigUnreadable` when `_global_file_problem` finds one;
    every function that writes to the global file calls this first."""
    problem = _global_file_problem(path)
    if problem is not None:
        raise GlobalConfigUnreadable(
            f"machine-global config is unreadable, refusing to write over "
            f"it: {problem}")

_SENDKEYS_NOTE = (
    "sendkeys is available as an explicit opt-in: it drives real keystrokes "
    "(System.Windows.Forms.SendKeys) into the terminal window this session "
    "owns, confirmed still foreground at send time, and it declines on its "
    "own inside Windows Terminal because that host cannot confirm which tab "
    "is active. Ask for it by name if you want it."
)

# Global-only under 1.0; a repo copy of either is never read. Every other
# leaf (`method`, `windowTitle`, `command`, `delaySeconds`, `minHandoffLines`)
# stays repo-settable and `strip_repo_duplication` leaves it untouched.
_REPO_ILLEGAL_LEAVES = ("onlyRepos", "onlySessions")


def _dig_dict(node, key):
    """`node[key]` if both exist and the value is a dict, else `{}`."""
    if not isinstance(node, dict):
        return {}
    value = node.get(key)
    return value if isinstance(value, dict) else {}


# --------------------------------------------------------------- reporting


def describe_notify():
    """What `notify` does, in the wording the owner requirements pin: it
    never claims anything was cleared or compacted, because nothing was."""
    return ("'notify' types nothing. It tells you when it is safe to /clear "
            "(or run the configured command) yourself, once a handoff is "
            "written and verified.")


def describe_global_windows_conversion():
    """The note printed when the machine-global file still carries the
    pre-1.0 `"windows"` method literal and is being converted to `"notify"`.
    Its own function so `check_no_forbidden_words` can sample it without
    writing a scratch file to disk to reach it through
    `plan_windows_notify_default`."""
    return ("context.autoClear.method is \"windows\" (SendKeys-armed by "
            "default pre-1.0) in the machine-global config. Proposing "
            "\"notify\", the 1.0 default, in its place. " + _SENDKEYS_NOTE)


def describe_tmux_path():
    """The Linux/macOS/WSL story: describe only, never propose a write."""
    return ("On Linux, macOS and WSL, 'auto' types the configured command "
            "into the tmux pane this session is already running in, when "
            "$TMUX names one and tmux is on PATH. There is no keystroke "
            "method to opt into here the way sendkeys is on Windows; nothing "
            "is written without you saying yes to enabling auto-clear at "
            "all.")


def already_configured_global(path=None):
    """The RAW (unmerged) global file's own `context.autoClear.method`, as a
    one-line report, or `None` when that key is simply absent OR still
    carries the pre-1.0 `"windows"` literal -- both read as "nothing has
    decided this yet", since `"windows"` is not a value 1.0 accepts and
    still needs converting (see `plan_windows_notify_default`'s windows
    branch).

    Read from the file as written, not through `resolve_config`'s merge:
    idempotence has to ask "did a previous run already write this key",
    which a merged-in default of `"auto"` would answer yes to even on a
    machine nobody has touched.
    """
    raw = crew_config.read_global_config(path)
    auto = _dig_dict(_dig_dict(raw, "context"), "autoClear")
    method = auto.get("method")
    if method is None or method == "windows":
        return None
    target = crew_config.GLOBAL_CONFIG_PATH if path is None else path
    return (f"context.autoClear.method is already `{json.dumps(method)}` "
            f"in {target} (machine-global); nothing to change")


# --------------------------------------------------------------- init


def plan_windows_notify_default(path=None):
    """What `/crew:init` (or `/crew:onboard`) should propose on native
    Windows: `{"status": "already-configured"|"proposed"|"unreadable",
    "message": str, "updates": dict}`. Writes nothing --
    `write_autoclear_method` does that, after a yes.

    `"unreadable"` is its own status, not folded into either of the other
    two: a malformed global file must stop here and say so, rather than
    `crew_config.read_global_config`'s read-side collapse making it look
    like a clean, unconfigured machine that this function then proposes a
    default write onto.
    """
    problem = _global_file_problem(path)
    if problem is not None:
        return {"status": "unreadable", "message": (
            f"could not read the machine-global config, nothing proposed: "
            f"{problem}. Fix or remove the file by hand before this can run."
        ), "updates": {}}

    raw = crew_config.read_global_config(path)
    auto = _dig_dict(_dig_dict(raw, "context"), "autoClear")
    legacy_windows = auto.get("method") == "windows"

    already = already_configured_global(path)
    if already is not None:
        return {"status": "already-configured", "message": already, "updates": {}}

    updates = {"context.autoClear.method": "notify"}
    merged, changes = crew_config.plan_global_write(updates, path)
    del merged
    if legacy_windows:
        message = describe_global_windows_conversion()
    else:
        message = (
            "Proposing context.autoClear.method = \"notify\" in the "
            "machine-global config (the value 'auto' already resolves to on "
            "native Windows with no tmux pane, written explicitly so the file "
            "says what will happen). " + describe_notify()
        )
    return {"status": "proposed", "message": message, "updates": updates,
            "changes": changes}


def write_autoclear_method(method, *, consent, path=None):
    """Write `context.autoClear.method` to the global layer.

    `consent` must be `True` to write `"sendkeys"` -- the one value the
    owner requirements forbid arming without an explicit yes. Every other
    value writes normally; this is the one guard `sendkeys` needs, not a
    generic write lock.

    Raises `GlobalConfigUnreadable` first, before the consent check, when
    the file is present but malformed -- a bad `path` argument should not
    depend on which consent branch got there first.
    """
    _require_global_readable(path)
    if method == "sendkeys" and not consent:
        raise PermissionError(
            "sendkeys is opt-in only; pass consent=True after an explicit yes"
        )
    return crew_config.write_global_config({"context.autoClear.method": method}, path)


def write_autoclear_enabled(enabled, *, consent, path=None):
    """Turn auto-clear on (or off) machine-wide. `consent` must be `True` to
    turn it ON; turning it off never needs consent. See
    `write_autoclear_method` for why the readability check runs first."""
    _require_global_readable(path)
    if enabled and not consent:
        raise PermissionError(
            "enabling auto-clear machine-wide needs an explicit yes; "
            "pass consent=True"
        )
    return crew_config.write_global_config({"context.autoClear.enabled": bool(enabled)}, path)


# --------------------------------------------------------------- migrate


def convert_method_windows_literal(context):
    """`context` with the pre-1.0 `"windows"` method literal converted to the
    1.0 default. Pure: returns `(new_context, note_or_None)`, `context` is
    not mutated.
    """
    auto = _dig_dict(context, "autoClear")
    if auto.get("method") != "windows":
        return context, None
    new_context = copy.deepcopy(context)
    new_context["autoClear"]["method"] = "notify"
    note = ("context.autoClear.method was \"windows\" (SendKeys-armed by "
            "default pre-1.0). Converted to \"notify\", the 1.0 default. "
            + _SENDKEYS_NOTE)
    return new_context, note


def strip_repo_duplication(context, repo_label="this repo"):
    """Remove the pre-1.0 repo-local duplication workaround from `context`.

    Some 0.20.x repos carried a full copy of the machine-global
    `context.autoClear` block, including `enabled: true`, because 0.20.17
    read only the repo file (real example: solomon/aws-managed-services).
    Under 1.0 only the global layer can turn `enabled` on, so a repo
    `enabled: true` does nothing -- it is dead weight, not a working opt-in.
    `onlyRepos`/`onlySessions` are global-only in 1.0 too; a repo copy of
    either is never read.

    A repo `enabled: false` is a legitimate opt-out and is kept, along with
    every other repo-settable leaf (`method`, `windowTitle`, `command`,
    `delaySeconds`, `minHandoffLines`), untouched.

    Pure: returns `(new_context, notes)`, `notes` empty when nothing needed
    removing.
    """
    auto = _dig_dict(context, "autoClear")
    if not auto:
        return context, []
    new_context = copy.deepcopy(context)
    new_auto = new_context["autoClear"]
    notes = []
    if new_auto.get("enabled") is True:
        del new_auto["enabled"]
        notes.append(
            f"{repo_label}: context.autoClear.enabled was `true` in the repo "
            "file - a pre-1.0 workaround for 0.20.17 reading only the repo "
            "copy. Under 1.0 a repo `enabled: true` does nothing (only the "
            "machine-global layer can turn auto-clear on), so it was removed "
            "rather than carried forward as dead config. A repo "
            "`enabled: false` opt-out, if this repo had one, is kept."
        )
    for leaf in _REPO_ILLEGAL_LEAVES:
        if leaf in new_auto:
            del new_auto[leaf]
            notes.append(
                f"{repo_label}: context.autoClear.{leaf} was set in the repo "
                "file. It is machine-global-only under 1.0 - the repo copy "
                "is never read - so it was removed."
            )
    return new_context, notes


def had_repo_local_opt_in(context):
    """Whether this repo's pre-migration `context.autoClear` carried
    `enabled: true` -- the signal both `strip_repo_duplication` (above) and
    `detect_onlyRepos_widening` (below) read, kept as one function so the
    two agree on what "opted in" meant under 0.20.x."""
    return _dig_dict(context, "autoClear").get("enabled") is True


# ------------------------------------------- migrate: --scan-root (T-0106)

SCAN_DEPTH_DEFAULT = 3
_REPO_CONFIG_NAMES = ("config.json", "crew.json")


class WideningRefused(ValueError):
    """`--yes-widen` would write a list that disarms or silently leaves out
    an opted-in repo. Raised before anything is written anywhere."""


def check_scan_roots(roots):
    """Raise `ValueError` naming the first `--scan-root` that is not an
    existing directory. Called before anything is read or written."""
    for root in roots or ():
        if not os.path.isdir(root):
            raise ValueError(_scan_root_problem(root))


def _scan_root_problem(root):
    return (f"--scan-root {root} does not exist or is not a directory; "
            "nothing was written")


def _scan_candidate(directory):
    """`(is_candidate, opted_in, reason)` for one directory. A candidate
    holds `.crew/config.json` or `.crew/crew.json`. Opted in when either
    file's `context.autoClear.enabled` is exactly `true` -- the test
    `had_repo_local_opt_in` applies to the current repo. `reason` is set
    when either present file could not be read as a JSON object -- even
    when the other shows the opt-in, as the spec has it -- and when the
    `.crew` directory itself is a symlink (never followed) or cannot be
    listed: that repo is unreadable (never "not opted in"), and it blocks
    `--yes-widen`."""
    crew_dir = os.path.join(directory, ".crew")
    if os.path.islink(crew_dir):
        return True, False, ".crew is a symlink; the scan does not follow it"
    if not os.path.isdir(crew_dir):
        return False, False, ""
    try:
        names = set(os.listdir(crew_dir))
    except OSError as exc:
        return True, False, f".crew could not be listed: {exc}"
    present, opted_in, problems = False, False, []
    for name in _REPO_CONFIG_NAMES:
        # The filesystem decides, not an exact match on `listdir`'s stored
        # spelling: on a case-insensitive one (Windows, macOS) crew reads
        # `.crew/Config.json` as `config.json`, so the scan must see it too.
        if name not in names and not os.path.lexists(os.path.join(crew_dir, name)):
            continue
        present = True
        try:
            doc = _read_json_if_present(os.path.join(directory, ".crew", name))
        except (OSError, ValueError) as exc:
            problems.append(f".crew/{name}: {exc}")
            continue
        if doc is None:
            problems.append(f".crew/{name}: vanished while it was read")
            continue
        context = doc.get("context")
        if had_repo_local_opt_in(context if isinstance(context, dict) else {}):
            opted_in = True
    return present, opted_in, "; ".join(problems)


def _scan_children(directory):
    """`(children, unchecked)`: the subdirectories the walk may enter (not
    hidden, not `node_modules`, not a symlink), and `{path: reason}` for
    entries whose type could not be read -- unknown, never skipped as "not
    a directory". Raises `OSError` when the directory cannot be listed."""
    children, unchecked = [], {}
    with os.scandir(directory) as entries:
        for entry in entries:
            if entry.name.startswith(".") or entry.name == "node_modules":
                continue
            try:
                if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError as exc:
                unchecked[entry.path] = f"could not tell whether it is a directory: {exc}"
                continue
            children.append(entry.path)
    return children, unchecked


def scan_opted_in_repos(roots, depth=SCAN_DEPTH_DEFAULT, *, current=None):
    """Read-only walk of each root for repos that still carry a 0.20.x
    repo-local `context.autoClear.enabled: true`. Depth 1 is a root's
    direct children; the root itself can be a candidate. A candidate is
    not descended into; hidden directories, `node_modules` and symlinked
    directories are not entered. `current` (a realpath) is skipped: its
    opt-in comes from its own files.

    Returns `{"roots", "depth", "found", "unreadable"}` -- `found` sorted
    realpaths, `unreadable` `{"path", "reason"}` entries (a file that is
    not a JSON object, or a directory that could not be listed)."""
    real_roots = [os.path.realpath(root) for root in roots]
    found, unreadable = set(), {}
    best = {}
    for top in real_roots:
        stack = [(top, 0)]
        while stack:
            directory, level = stack.pop()
            if best.get(directory, depth + 1) <= level:
                continue
            best[directory] = level
            if directory == current:
                continue
            is_candidate, opted_in, reason = _scan_candidate(directory)
            if is_candidate:
                if reason:
                    unreadable[directory] = reason
                elif opted_in:
                    found.add(directory)
                continue
            if level >= depth:
                continue
            try:
                children, unchecked = _scan_children(directory)
            except OSError as exc:
                unreadable[directory] = f"could not list it: {exc}"
                continue
            unreadable.update(unchecked)
            stack.extend((child, level + 1) for child in children)
    return {
        "roots": real_roots,
        "depth": depth,
        "found": sorted(found),
        "unreadable": [{"path": path, "reason": unreadable[path]}
                       for path in sorted(unreadable)],
    }


def _widening_message(proposed, scan, repo_had_opt_in):
    """The widening text. Without a scan it is the pre-T-0106 text plus one
    sentence naming `--scan-root`; with one it names the roots, the depth,
    what was found and what could not be read, and the two limits."""
    message = (
        "context.autoClear.enabled is true machine-wide and onlyRepos is "
        "null, so under 1.0 this arms EVERY initialised crew repo on this "
        "machine, not just the ones that opted in under 0.20.x. "
    )
    if scan is None:
        if proposed:
            message += (
                f"This repo had a repo-local opt-in before migration, so it is "
                f"proposed for onlyRepos: {proposed}. This process can only see "
                "this repo - if other repos on this machine also opted in "
                "locally, add their paths by hand."
            )
        else:
            message += (
                "This repo had no repo-local opt-in, so nothing is proposed to "
                "add to onlyRepos from here - if some other repo on this "
                "machine did opt in, add it by hand."
            )
        return message + (
            " Re-run with --scan-root <dir> to look for them under a "
            "directory (read-only).")
    message += (
        f"This repo {'had' if repo_had_opt_in else 'had no'} repo-local "
        f"opt-in. Scanned {', '.join(scan['roots'])} to depth "
        f"{scan['depth']} (read-only): found {len(scan['found'])} other "
        "opted-in repo(s)."
    )
    if scan["unreadable"]:
        listed = "; ".join(f"{item['path']} ({item['reason']})"
                           for item in scan["unreadable"])
        message += (
            f" Could not read {len(scan['unreadable'])}, so whether they "
            f"opted in is unknown and they block --yes-widen: {listed}.")
    message += (
        f" Proposed for onlyRepos: {proposed}. Repos outside these roots are "
        "not seen, and a repo an earlier apply-migrate already converted no "
        "longer carries its opt-in, so no scan can find it - add those by "
        "hand."
    )
    return message


def detect_onlyRepos_widening(global_cfg, repo_root, repo_had_opt_in, *,
                              scan_roots=None, scan_depth=SCAN_DEPTH_DEFAULT):
    """Whether leaving the global file untouched arms every crew repo on
    this machine, and what to propose instead.

    `global_cfg` is the RAW (unfiltered) global file. `repo_had_opt_in` is
    `had_repo_local_opt_in` on this repo's PRE-migration config -- this repo
    asked for auto-clear under 0.20.x, before 1.0's global-only `enabled`
    existed.

    Returns `{"widening": bool, "proposedOnlyRepos": [...], "message": str}`,
    plus `"scan"` (`scan_opted_in_repos`' result) when `scan_roots` was
    given and there is a widening. Without `scan_roots` the proposal can
    only name `repo_root`, and the message says so rather than implying it
    looked further. The scan runs only when there is a widening.
    """
    auto = _dig_dict(global_cfg, "context").get("autoClear")
    auto = auto if isinstance(auto, dict) else {}
    if auto.get("enabled") is not True or auto.get("onlyRepos") is not None:
        return {"widening": False, "proposedOnlyRepos": [], "message": ""}
    here = os.path.realpath(repo_root)
    scan = (scan_opted_in_repos(scan_roots, scan_depth, current=here)
            if scan_roots else None)
    proposed = {here} if repo_had_opt_in else set()
    proposed.update(scan["found"] if scan else ())
    proposed = sorted(proposed)
    result = {"widening": True, "proposedOnlyRepos": proposed,
              "message": _widening_message(proposed, scan, repo_had_opt_in)}
    if scan is not None:
        result["scan"] = scan
    return result


def widening_refusal(widening):
    """Why `--yes-widen` must not write `widening`'s proposal, or None."""
    unreadable = widening.get("scan", {}).get("unreadable") or []
    if unreadable:
        return ("refused --yes-widen: these repos could not be read, so "
                "whether they opted in is unknown and writing onlyRepos now "
                "could leave one out: "
                + "; ".join(f"{item['path']} ({item['reason']})"
                            for item in unreadable)
                + ". Fix or move them and run again; nothing was written.")
    if not widening["proposedOnlyRepos"]:
        return ("refused --yes-widen: the proposed onlyRepos list is empty, "
                "and an empty list would turn auto-clear off in every repo "
                "on this machine. Run again with --scan-root <dir> to find "
                "the repos that opted in, or write the list yourself with "
                "crew_config.py --set 'context.autoClear.onlyRepos=<list>' "
                "--apply. Nothing was written.")
    return None


def apply_onlyRepos_narrowing(only_repos, *, consent, path=None):
    """Write the proposed `onlyRepos` narrowing. `consent` must be `True` --
    narrowing what fires changes behaviour on every OTHER repo on this
    machine too, not just this one, and that needs the same explicit yes any
    other global write does. Raises `GlobalConfigUnreadable` before the
    consent check, same as `write_autoclear_method` -- a malformed global
    file must not silently drop the narrowing signal onto a `{}` collapse
    either."""
    _require_global_readable(path)
    if not consent:
        raise PermissionError(
            "narrowing onlyRepos changes what fires on other repos too; "
            "needs an explicit yes"
        )
    return crew_config.write_global_config(
        {"context.autoClear.onlyRepos": only_repos}, path)


def plan_migrate_context(context, global_cfg, repo_root, repo_label="this repo"):
    """Everything `/crew:migrate` needs to know about one repo's
    `context.autoClear`, without writing anything. Pure.

    Returns `{"context": new_context, "notes": [...], "widening": {...}}` --
    `new_context` is `context` with the method-rename and the duplication
    strip both applied; `notes` is every visible note to print, in order;
    `widening` is `detect_onlyRepos_widening`'s result, using
    `had_repo_local_opt_in` on the ORIGINAL (pre-strip) context, since
    stripping removes the very `enabled: true` that signal reads.
    """
    opted_in = had_repo_local_opt_in(context)
    renamed, rename_note = convert_method_windows_literal(context)
    stripped, strip_notes = strip_repo_duplication(renamed, repo_label)
    notes = ([rename_note] if rename_note else []) + strip_notes
    widening = detect_onlyRepos_widening(global_cfg, repo_root, opted_in)
    return {"context": stripped, "notes": notes, "widening": widening}


def _stage_json(path, obj):
    """Build the full payload and write it to a SIBLING temp file next to
    `path` -- CLAUDE.md's `open(p, "w")` truncation trap: `path` itself is
    never opened for writing here, so a failure anywhere in this function
    leaves whatever was already at `path` completely untouched. Returns
    the temp file's path; `path` itself is not replaced until the caller
    does that explicitly, which is what lets `apply_migrate_to_repo` stage
    more than one file before committing any of them.

    On any failure the temp file is removed and the exception re-raised --
    callers staging several files in a batch are expected to remove any
    EARLIER temp file in that same batch themselves (this function only
    knows about its own).
    """
    payload = (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return tmp


def _atomic_write_json(path, obj):
    """Single-file atomic write: stage, then replace. The target is only
    ever replaced whole via a sibling temp file, never truncated in
    place."""
    tmp = _stage_json(path, obj)
    try:
        crew_backup.backup(path)          # T-0050: no backup, no write
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _read_json_if_present(path):
    """The parsed JSON object at `path`, or `None` when it does not exist.
    Any other read/parse failure is left to raise -- a present-but-broken
    repo file is not the same "nothing to convert" signal as an absent
    one, and swallowing it here would silently skip the conversion.

    Raises `ValueError` (caught by `main`'s `apply-migrate` handler,
    alongside the JSON-decode `ValueError` `json.load` itself already
    raises for unparseable text) when the file parses cleanly but is not a
    JSON OBJECT -- a top-level `[]` or a bare string is valid JSON, so
    `json.load` would otherwise hand back something this module's own
    `doc.get("context")` / `doc["context"] = ...` calls further down
    assume is a dict, crashing with an uncaught `AttributeError`/
    `TypeError` instead of the same controlled failure a malformed global
    file already gets via `GlobalConfigUnreadable`."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            parsed = json.load(handle)
    except FileNotFoundError:
        return None
    if not isinstance(parsed, dict):
        raise ValueError(
            f"{path} holds a JSON {type(parsed).__name__}, not an object -- "
            "refusing to migrate it")
    return parsed


def apply_migrate_to_repo(root, global_path=None, repo_label=None, yes_widen=False, *,
                          scan_roots=None, scan_depth=SCAN_DEPTH_DEFAULT):
    """Convert `context.autoClear` in whichever of `<root>/.crew/config.json`
    and `<root>/.crew/crew.json` are present, and write each one back in
    place.

    **Both, when both exist, because they can disagree about what fires --
    and EACH FILE'S OWN `context` IS CONVERTED FROM ITSELF, never copied
    from the other.** `crew_migrate.py --apply` copies `config.json`'s
    `context` block into a new `crew.json` UNCONVERTED and keeps the
    original -- `config.json` is marked "retireable", not deleted
    (`commands/migrate.md`'s own table). Every autoClear SENDER
    (`auto-clear.sh`, `auto-clear.ps1`, `crew_autocycle.py`'s `_load`)
    reads `.crew/config.json` only; nothing in this plugin's runtime reads
    `crew.json` for autoClear behaviour -- `crew_status.py` reads it only
    to report the migration schema. So converting `crew.json` alone (an
    earlier version of this function) left a retained legacy method like
    `"windows"` live in `config.json`, where every sender still reads it
    and then refuses it as unsupported -- migration looked complete and
    autoClear was silently dead.

    A LATER version of this function fixed that by computing ONE plan
    (from whichever file it read first) and writing that SAME converted
    `context` into both files. That is only correct the instant after
    `crew_migrate.py --apply` runs, when the two blocks are still
    identical; nothing keeps them in step after that, and nothing here
    ever re-syncs them on purpose. A repo that has since hand-edited
    `config.json` (or `crew.json`) independently -- or was migrated,
    edited, and is only now being converted -- would have that whole
    file's divergent `context` silently OVERWRITTEN with the other file's
    post-migration copy, discarding settings nobody asked to change. Each
    file below is read, converted (method-rename, then the repo-local-
    duplication strip) and re-checked for "anything to convert" entirely
    from its OWN prior content; the only thing shared between the two is
    the widening signal, which is deliberately the OR of both files'
    pre-migration `enabled: true` (a repo-local opt-in recorded in EITHER
    file counts, since either is evidence this repo asked for auto-clear
    under 0.20.x).

    Returns `{"notes": [...], "perFile": {"config.json": {...} or None,
    "crew.json": {...} or None}, "widening": {...}, "alreadyConfigured":
    bool, "wideningApplied": bool}`. `perFile[<name>]` is `None` when that
    file does not exist, and otherwise the module's post-conversion
    `context` for that specific file. `alreadyConfigured` is true only
    when NEITHER file had anything to convert -- a repeat run is then
    byte-idempotent for both.

    The ONLY global write this makes is the `onlyRepos` narrowing, and
    only when `plan["widening"]["widening"]` is true AND `yes_widen` is
    true -- the explicit-yes gate `detect_onlyRepos_widening`'s docstring
    describes.

    **The global write happens BEFORE either repo file is touched.**
    `apply_onlyRepos_narrowing` raises (`GlobalConfigUnreadable`, an
    `OSError` from a read-only global directory, etc.) rather than
    returning a failure code, so if it raises, this function has not yet
    written anything to `root` -- the repo files stay exactly as they were
    and the caller sees a non-zero exit with the reason. The previous
    ordering wrote the repo copy first: a failed global write then left
    the repo's opt-in already stripped with nothing on the machine-global
    side recording the widening, and no way to retell which repos had
    opted in.

    **The two repo writes are not one transaction, but a retry repairs a
    half-migrated pair on its own.** Both new file payloads are computed
    and staged into sibling temp files (`_stage_json`) BEFORE either real
    file is replaced, so a failure anywhere in that staging leaves BOTH
    real files untouched (every already-staged temp file in the same
    batch is removed first). A crash between the two `os.replace` calls
    that follow can still leave one file converted and the other not --
    POSIX has no atomic rename of two files at once -- but nothing here
    needs that to be safe: each file's own "does IT still have anything to
    convert" check is independent and re-derived from that file's own
    on-disk content on every call, so a retry converts exactly the file
    that did not make it and leaves the one that already did alone.

    **Decide `yes_widen` on THIS call, not a follow-up one.** The widening
    proposal's `proposedOnlyRepos` reads this repo's pre-migration
    `enabled: true` off the file(s) passed in -- the FIRST call that strips
    it (because there was something to convert) removes that signal for
    good. A second call after that one will report this repo as never
    having opted in, which is wrong for THIS repo even though it is an
    honest read of what is left on disk. Show the proposal and get the yes
    before calling this at all, or accept `--yes-widen` up front on the one
    call that also does the stripping.

    **`scan_roots` (T-0106) looks for the OTHER opted-in repos**, read-only,
    through `scan_opted_in_repos`, and adds them to the proposal; a root
    that is not a directory raises `ValueError` before anything is read.
    `yes_widen` raises `WideningRefused` (nothing written anywhere) when
    the proposal is empty -- `onlyRepos: []` would disarm every repo -- or
    a scanned repo could not be read. Each note starts with its file
    (`.crew/config.json: ` or `.crew/crew.json: `).
    """
    check_scan_roots(scan_roots)
    config_path = os.path.join(root, ".crew", "config.json")
    crew_json_path = os.path.join(root, ".crew", "crew.json")
    config_doc = _read_json_if_present(config_path)
    crew_doc = _read_json_if_present(crew_json_path)
    if config_doc is None and crew_doc is None:
        raise FileNotFoundError(
            f"neither {config_path} nor {crew_json_path} exists -- nothing "
            "to migrate")

    global_cfg = crew_config.read_global_config(global_path)
    label = repo_label or os.path.basename(os.path.abspath(root))

    # Each entry's `context` is converted from THAT file's own prior
    # content -- never from the other file's result -- so a divergent
    # crew.json (or config.json) setting is never silently clobbered.
    entries = []
    opted_in = False
    for name, path, doc in (("config.json", config_path, config_doc),
                            ("crew.json", crew_json_path, crew_doc)):
        if doc is None:
            entries.append({"name": name, "path": path, "doc": None,
                           "context": None, "notes": []})
            continue
        context = doc.get("context")
        context = context if isinstance(context, dict) else {}
        opted_in = opted_in or had_repo_local_opt_in(context)
        renamed, rename_note = convert_method_windows_literal(context)
        stripped, strip_notes = strip_repo_duplication(renamed, label)
        file_notes = [f".crew/{name}: {note}" for note in
                      ([rename_note] if rename_note else []) + strip_notes]
        entries.append({"name": name, "path": path, "doc": doc,
                        "context": stripped, "notes": file_notes})

    notes = [note for entry in entries for note in entry["notes"]]
    already_configured = not notes
    widening = detect_onlyRepos_widening(global_cfg, root, opted_in,
                                         scan_roots=scan_roots, scan_depth=scan_depth)

    widening_applied = False
    if widening["widening"] and yes_widen:
        refusal = widening_refusal(widening)
        if refusal:
            raise WideningRefused(refusal)
        apply_onlyRepos_narrowing(
            widening["proposedOnlyRepos"], consent=True, path=global_path)
        widening_applied = True

    if not already_configured:
        to_write = [entry for entry in entries if entry["notes"]]
        staged = []
        try:
            for entry in to_write:
                new_doc = copy.deepcopy(entry["doc"])
                new_doc["context"] = entry["context"]
                tmp = _stage_json(entry["path"], new_doc)
                staged.append((tmp, entry["path"]))
        except BaseException:
            for tmp, _ in staged:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            raise
        # NOT a bare loop. An `os.replace` failure partway through this
        # batch (permissions, disk full, an antivirus lock on `path`, ...)
        # used to leave every UNCONSUMED staged temp file behind -- the
        # staging loop above already cleans up after a failure to STAGE,
        # but nothing cleaned up after a failure to COMMIT what was
        # already staged. `finally` runs on both the success and the
        # failure path; on success every staged tmp has already been
        # renamed away by `os.replace` (so `os.path.exists` is false and
        # the removal is a no-op), and on a failure partway through it
        # removes the temp that failed to commit and every later one that
        # never got the chance to. Committed-and-replaced files are left
        # exactly as they are -- the docstring above already accepts a
        # partial conversion across a crash between two `os.replace`
        # calls; this only stops the LEFTOVER TEMP FILE from being the
        # thing a crash leaves behind too.
        try:
            # T-0050: back up `config.json` before the FIRST replace, so a
            # failed backup refuses the whole batch with nothing written.
            for _tmp, path in staged:
                if os.path.basename(path) == "config.json":
                    crew_backup.backup(path)
            for tmp, path in staged:
                os.replace(tmp, path)
        finally:
            for tmp, _ in staged:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass

    return {
        "notes": notes,
        "perFile": {entry["name"]: entry["context"] for entry in entries},
        "widening": widening,
        "alreadyConfigured": already_configured,
        "wideningApplied": widening_applied,
    }


# --------------------------------------------------------------- self-check


def forbidden_word_samples():
    """Every message this module can print, one sample each (T-0106 adds a
    scan with a found and an unreadable repo, and both `--yes-widen`
    refusals)."""
    samples = [
        describe_notify(), describe_tmux_path(), _SENDKEYS_NOTE,
        describe_global_windows_conversion(),
        plan_windows_notify_default(path="/nonexistent")["message"],
    ]
    widening = detect_onlyRepos_widening(
        {"context": {"autoClear": {"enabled": True, "onlyRepos": None}}},
        "/tmp/example-repo", True)
    samples.append(widening["message"])
    scan = {"roots": ["/tmp/src"], "depth": SCAN_DEPTH_DEFAULT,
            "found": ["/tmp/src/other"],
            "unreadable": [{"path": "/tmp/src/broken",
                            "reason": ".crew/config.json: not valid JSON"}]}
    samples.append(_widening_message(["/tmp/src/other"], scan, False))
    samples.append(_widening_message([], None, False))
    samples.append(widening_refusal(
        {"proposedOnlyRepos": ["/tmp/src/other"], "scan": scan}))
    samples.append(widening_refusal({"proposedOnlyRepos": []}))
    samples.append(_scan_root_problem("/tmp/missing"))
    _, notes = strip_repo_duplication(
        {"autoClear": {"enabled": True, "onlyRepos": [], "onlySessions": []}})
    samples.extend(notes)
    _, note = convert_method_windows_literal({"autoClear": {"method": "windows"}})
    samples.append(note)
    return samples


def check_no_forbidden_words():
    """Every literal string this module can print, scanned for "cleared" and
    "compacted". Returns the offending strings, empty when clean. Exists so
    `test_no_forbidden_words` has one thing to call rather than hand-listing
    every function here and forgetting the next one that's added."""
    samples = forbidden_word_samples()
    lowered = [s.lower() for s in samples]
    return [s for s, low in zip(samples, lowered)
            if any(word in low for word in FORBIDDEN_WORDS)]


# --------------------------------------------------------------- CLI


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--global-path", default=None,
                        help="override ~/.claude/crew/config.json (testing)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("plan-windows-default",
                   help="what /crew:init would propose on native Windows")

    p_apply = sub.add_parser("apply-method", help="write context.autoClear.method")
    p_apply.add_argument("method")
    p_apply.add_argument("--yes", action="store_true",
                         help="consent; required for method=sendkeys")

    p_enable = sub.add_parser("apply-enabled", help="write context.autoClear.enabled")
    p_enable.add_argument("value", choices=("true", "false"))
    p_enable.add_argument("--yes", action="store_true",
                          help="consent; required to turn it on")

    p_conv = sub.add_parser("plan-migrate",
                            help="what migrate should do to a repo's context block")
    p_conv.add_argument("--context-json", required=True,
                        help="the repo's context block, as a JSON file path")
    p_conv.add_argument("--repo-label", default=None)

    p_am = sub.add_parser("apply-migrate",
                          help=("rewrite context.autoClear in .crew/config.json and "
                                ".crew/crew.json in place, whichever exist"))
    p_am.add_argument("--repo-label", default=None)
    p_am.add_argument("--yes-widen", action="store_true",
                      help="also apply the proposed onlyRepos narrowing")
    p_am.add_argument("--scan-root", action="append", default=None,
                      help=("look under this directory, read-only, for other repos "
                            "that opted in (repeatable)"))
    p_am.add_argument("--scan-depth", type=int, default=None,
                      help=f"levels below each --scan-root (default {SCAN_DEPTH_DEFAULT})")

    args = parser.parse_args(argv)
    if getattr(args, "scan_depth", None) is not None:
        if not args.scan_root:
            parser.error("--scan-depth needs --scan-root")
        if args.scan_depth < 1:
            parser.error("--scan-depth must be at least 1")

    if args.cmd == "plan-windows-default":
        print(json.dumps(plan_windows_notify_default(args.global_path), indent=2))
        return 0

    if args.cmd == "apply-method":
        try:
            _, changes = write_autoclear_method(
                args.method, consent=args.yes, path=args.global_path)
        except (PermissionError, GlobalConfigUnreadable,
                crew_config.WriteBackupRefused) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(changes, indent=2))
        return 0

    if args.cmd == "apply-enabled":
        try:
            _, changes = write_autoclear_enabled(
                args.value == "true", consent=args.yes, path=args.global_path)
        except (PermissionError, GlobalConfigUnreadable,
                crew_config.WriteBackupRefused) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(changes, indent=2))
        return 0

    if args.cmd == "plan-migrate":
        with open(args.context_json, "r", encoding="utf-8") as handle:
            context = json.load(handle)
        global_cfg = crew_config.read_global_config(args.global_path)
        label = args.repo_label or os.path.basename(os.path.abspath(args.root))
        plan = plan_migrate_context(context, global_cfg, args.root, label)
        print(json.dumps(plan, indent=2))
        return 0

    if args.cmd == "apply-migrate":
        try:
            plan = apply_migrate_to_repo(
                args.root, args.global_path, args.repo_label, args.yes_widen,
                scan_roots=args.scan_root,
                scan_depth=args.scan_depth or SCAN_DEPTH_DEFAULT)
        except (GlobalConfigUnreadable, OSError, ValueError,
                crew_backup.BackupError, crew_config.WriteBackupRefused) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(plan, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
