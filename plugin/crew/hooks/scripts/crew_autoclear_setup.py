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


def detect_onlyRepos_widening(global_cfg, repo_root, repo_had_opt_in):
    """Whether leaving the global file untouched arms every crew repo on
    this machine, and what to propose instead.

    `global_cfg` is the RAW (unfiltered) global file. `repo_had_opt_in` is
    `had_repo_local_opt_in` on this repo's PRE-migration config -- this repo
    asked for auto-clear under 0.20.x, before 1.0's global-only `enabled`
    existed.

    Returns `{"widening": bool, "proposedOnlyRepos": [...], "message": str}`.
    `proposedOnlyRepos` can only ever name repos this process can see, which
    in practice is just `repo_root` -- it cannot enumerate every crew repo on
    the machine, and says so rather than implying it did.
    """
    auto = _dig_dict(global_cfg, "context").get("autoClear")
    auto = auto if isinstance(auto, dict) else {}
    if auto.get("enabled") is not True or auto.get("onlyRepos") is not None:
        return {"widening": False, "proposedOnlyRepos": [], "message": ""}
    proposed = [os.path.realpath(repo_root)] if repo_had_opt_in else []
    message = (
        "context.autoClear.enabled is true machine-wide and onlyRepos is "
        "null, so under 1.0 this arms EVERY initialised crew repo on this "
        "machine, not just the ones that opted in under 0.20.x. "
    )
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
    return {"widening": True, "proposedOnlyRepos": proposed, "message": message}


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


def _atomic_write_json(path, obj):
    """The full payload is built before anything is opened (CLAUDE.md's
    `open(p, "w")` truncation trap), and the target is only ever replaced
    whole via a sibling temp file, never truncated in place."""
    payload = (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
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
    one, and swallowing it here would silently skip the conversion."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None


def apply_migrate_to_repo(root, global_path=None, repo_label=None, yes_widen=False):
    """Convert `context.autoClear` in whichever of `<root>/.crew/config.json`
    and `<root>/.crew/crew.json` are present, and write each one back in
    place.

    **Both, when both exist, because they can disagree about what fires.**
    `crew_migrate.py --apply` copies `config.json`'s `context` block into a
    new `crew.json` UNCONVERTED and keeps the original -- `config.json` is
    marked "retireable", not deleted (`commands/migrate.md`'s own table).
    Every autoClear SENDER (`auto-clear.sh`, `auto-clear.ps1`,
    `crew_autocycle.py`'s `_load`) reads `.crew/config.json` only; nothing
    in this plugin's runtime reads `crew.json` for autoClear behaviour --
    `crew_status.py` reads it only to report the migration schema. So
    converting `crew.json` alone (the previous behaviour here) left a
    retained legacy method like `"windows"` live in `config.json`, where
    every sender still reads it and then refuses it as unsupported --
    migration looked complete and autoClear was silently dead. Converting
    `config.json` alone would leave `crew.json`'s copy stale for
    `/crew:status`'s own report. So both are read, the plan is computed
    once (from whichever exists; their `context` blocks are identical
    immediately after `crew_migrate.py --apply`, before this function has
    touched either), and both are rewritten when there is something to
    convert.

    Returns the plan (see `plan_migrate_context`) plus `alreadyConfigured`
    (no notes -> nothing to convert -> neither file is touched, so a
    repeat run is byte-idempotent) and `wideningApplied`. The ONLY global
    write this makes is the `onlyRepos` narrowing, and only when
    `plan["widening"]["widening"]` is true AND `yes_widen` is true -- the
    explicit-yes gate `detect_onlyRepos_widening`'s docstring describes.

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

    **Decide `yes_widen` on THIS call, not a follow-up one.** The widening
    proposal's `proposedOnlyRepos` reads this repo's pre-migration
    `enabled: true` off the file passed in -- the FIRST call that strips it
    (because there was something to convert) removes that signal for good.
    A second call after that one will report this repo as never having
    opted in, which is wrong for THIS repo even though it is an honest read
    of what is left on disk. Show the proposal and get the yes before
    calling this at all, or accept `--yes-widen` up front on the one call
    that also does the stripping.
    """
    config_path = os.path.join(root, ".crew", "config.json")
    crew_json_path = os.path.join(root, ".crew", "crew.json")
    config_doc = _read_json_if_present(config_path)
    crew_doc = _read_json_if_present(crew_json_path)
    if config_doc is None and crew_doc is None:
        raise FileNotFoundError(
            f"neither {config_path} nor {crew_json_path} exists -- nothing "
            "to migrate")

    source_doc = config_doc if config_doc is not None else crew_doc
    context = source_doc.get("context")
    context = context if isinstance(context, dict) else {}
    global_cfg = crew_config.read_global_config(global_path)
    label = repo_label or os.path.basename(os.path.abspath(root))
    plan = plan_migrate_context(context, global_cfg, root, label)
    already_configured = not plan["notes"]
    plan["alreadyConfigured"] = already_configured

    widening_applied = False
    if plan["widening"]["widening"] and yes_widen:
        apply_onlyRepos_narrowing(
            plan["widening"]["proposedOnlyRepos"], consent=True, path=global_path)
        widening_applied = True

    if not already_configured:
        if config_doc is not None:
            config_doc["context"] = plan["context"]
            _atomic_write_json(config_path, config_doc)
        if crew_doc is not None:
            crew_doc["context"] = plan["context"]
            _atomic_write_json(crew_json_path, crew_doc)

    plan["wideningApplied"] = widening_applied
    return plan


# --------------------------------------------------------------- self-check


def check_no_forbidden_words():
    """Every literal string this module can print, scanned for "cleared" and
    "compacted". Returns the offending strings, empty when clean. Exists so
    `test_no_forbidden_words` has one thing to call rather than hand-listing
    every function here and forgetting the next one that's added."""
    samples = [
        describe_notify(), describe_tmux_path(), _SENDKEYS_NOTE,
        describe_global_windows_conversion(),
        plan_windows_notify_default(path="/nonexistent")["message"],
    ]
    widening = detect_onlyRepos_widening(
        {"context": {"autoClear": {"enabled": True, "onlyRepos": None}}},
        "/tmp/example-repo", True)
    samples.append(widening["message"])
    _, notes = strip_repo_duplication(
        {"autoClear": {"enabled": True, "onlyRepos": [], "onlySessions": []}})
    samples.extend(notes)
    _, note = convert_method_windows_literal({"autoClear": {"method": "windows"}})
    samples.append(note)
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

    args = parser.parse_args(argv)

    if args.cmd == "plan-windows-default":
        print(json.dumps(plan_windows_notify_default(args.global_path), indent=2))
        return 0

    if args.cmd == "apply-method":
        try:
            _, changes = write_autoclear_method(
                args.method, consent=args.yes, path=args.global_path)
        except (PermissionError, GlobalConfigUnreadable) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(changes, indent=2))
        return 0

    if args.cmd == "apply-enabled":
        try:
            _, changes = write_autoclear_enabled(
                args.value == "true", consent=args.yes, path=args.global_path)
        except (PermissionError, GlobalConfigUnreadable) as exc:
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
                args.root, args.global_path, args.repo_label, args.yes_widen)
        except (GlobalConfigUnreadable, OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(plan, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
