"""The one place `/crew:init`, `/crew:migrate` and `/crew:onboard` decide what
to do about `context.autoClear`, so the three command files relay a plan
instead of each carrying their own copy of it.

Schema (owned by `crew_state.AUTOCLEAR_DEFAULTS` / `crew_platform._AUTOCLEAR_
METHODS`; not restated here beyond what this module needs to reason about):
`enabled` only the global layer may turn on; `method` defaults to `"auto"`,
which resolves to a tmux pane on Linux/macOS/WSL, to `notify` on native
Windows with no tmux pane, and never to `sendkeys` -- that is opt-in only,
requested by name.

Four things this module exists to make impossible by construction rather than
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
    one-line report, or `None` when that key is simply absent -- the signal
    that nothing has decided this yet.

    Read from the file as written, not through `resolve_config`'s merge:
    idempotence has to ask "did a previous run already write this key",
    which a merged-in default of `"auto"` would answer yes to even on a
    machine nobody has touched.
    """
    raw = crew_config.read_global_config(path)
    auto = _dig_dict(_dig_dict(raw, "context"), "autoClear")
    if "method" not in auto:
        return None
    target = crew_config.GLOBAL_CONFIG_PATH if path is None else path
    return (f"context.autoClear.method is already `{json.dumps(auto['method'])}` "
            f"in {target} (machine-global); nothing to change")


# --------------------------------------------------------------- init


def plan_windows_notify_default(path=None):
    """What `/crew:init` (or `/crew:onboard`) should propose on native
    Windows: `{"status": "already-configured"|"proposed", "message": str,
    "updates": dict}`. Writes nothing -- `write_autoclear_method` does that,
    after a yes.
    """
    already = already_configured_global(path)
    if already is not None:
        return {"status": "already-configured", "message": already, "updates": {}}
    updates = {"context.autoClear.method": "notify"}
    merged, changes = crew_config.plan_global_write(updates, path)
    del merged
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
    """
    if method == "sendkeys" and not consent:
        raise PermissionError(
            "sendkeys is opt-in only; pass consent=True after an explicit yes"
        )
    return crew_config.write_global_config({"context.autoClear.method": method}, path)


def write_autoclear_enabled(enabled, *, consent, path=None):
    """Turn auto-clear on (or off) machine-wide. `consent` must be `True` to
    turn it ON; turning it off never needs consent."""
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
    other global write does."""
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


def apply_migrate_to_repo(root, global_path=None, repo_label=None, yes_widen=False):
    """Read `<root>/.crew/crew.json`'s `context` block, apply
    `plan_migrate_context` to it, and write it back in place.

    Returns the plan (see `plan_migrate_context`) plus `alreadyConfigured`
    (no notes -> nothing to convert -> the file is not touched at all, so a
    repeat run is byte-idempotent) and `wideningApplied`. The ONLY global
    write this makes is the `onlyRepos` narrowing, and only when
    `plan["widening"]["widening"]` is true AND `yes_widen` is true -- the
    explicit-yes gate `detect_onlyRepos_widening`'s docstring describes.
    Everything else this function does stays inside `root`.

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
    crew_json_path = os.path.join(root, ".crew", "crew.json")
    with open(crew_json_path, "r", encoding="utf-8") as handle:
        crew_json = json.load(handle)
    context = crew_json.get("context")
    context = context if isinstance(context, dict) else {}
    global_cfg = crew_config.read_global_config(global_path)
    label = repo_label or os.path.basename(os.path.abspath(root))
    plan = plan_migrate_context(context, global_cfg, root, label)
    already_configured = not plan["notes"]
    plan["alreadyConfigured"] = already_configured
    if not already_configured:
        crew_json["context"] = plan["context"]
        _atomic_write_json(crew_json_path, crew_json)

    widening_applied = False
    if plan["widening"]["widening"] and yes_widen:
        apply_onlyRepos_narrowing(
            plan["widening"]["proposedOnlyRepos"], consent=True, path=global_path)
        widening_applied = True
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
                          help="rewrite .crew/crew.json's context block in place")
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
        except PermissionError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(changes, indent=2))
        return 0

    if args.cmd == "apply-enabled":
        try:
            _, changes = write_autoclear_enabled(
                args.value == "true", consent=args.yes, path=args.global_path)
        except PermissionError as exc:
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
        plan = apply_migrate_to_repo(
            args.root, args.global_path, args.repo_label, args.yes_widen)
        print(json.dumps(plan, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
