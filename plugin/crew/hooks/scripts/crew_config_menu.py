"""`/crew:config`'s menu: the rows, the values, Save, and repo-config delete.

    python3 crew_config_menu.py --root R [--global-path P] spec --layer machine|repo
                                [--area ID] [--json]
    python3 crew_config_menu.py --root R [--global-path P] save --changes JSON [--apply]
    python3 crew_config_menu.py --root R [--global-path P] delete-repo
                                [--confirm NAME] [--apply]
    python3 crew_config_menu.py --root R restore-repo --from PATH [--apply]

T-0075. The procedure a session follows is
`skills/crew-setup/config-menu.md`; this module is what it reads and calls,
so the menu cannot offer a key or a value the writers refuse.

DATA-DRIVEN, never a hand copy. The machine rows are
`crew_config.leaf_paths(default_global_config())`; the repo rows are
`leaf_paths(default_config())`, with the refused ones (`REPO_REFUSED`) shown
read-only and their reason. Allowed values come from `crew_config.enum_values`
(the tuples the readers normalise against), `KNOWN_VALUES` below (each entry
cites the reader that accepts it), the known model ids, and what either layer
already holds. A key added to a defaults block appears here with no edit.

Writes go through `crew_config` only: `plan_global_write` /
`write_global_config` for the machine file and `plan_repo_write` /
`write_repo_config` for `.crew/config.json`. `save` validates BOTH layers
before writing either, and writes each changed layer once.

Delete removes `.crew/config.json` only, after a verified backup
(`config.json.bak-<UTC timestamp>`, never the heal path's `.broken` name), and
prints the command that restores it. It never touches `crew.json`, backups,
`verify.json`, the codemap or ticket state.
"""

import argparse
import copy
import datetime
import json
import os
import shlex
import shutil
import sys
import tempfile

import crew_config
import crew_state

# (id, label, prefixes). Order is the menu order; `other` is the catch-all and
# must stay last. A key lands in the first area whose prefix matches.
AREAS = (
    ("models", "Reviewer and models", ("qa", "dev", "secondOpinion")),
    ("autopilot", "Autopilot", ("autopilot", "emergency")),
    ("guards", "Guards and production", ("guards", "install", "environments",
                                         "change", "production", "cloud",
                                         "scope")),
    ("notify", "Notifications", ("notify",)),
    ("memory", "Memory and tracker", ("memory", "tracker", "jira", "sdp",
                                      "obsidian", "graph")),
    ("autoclear", "Auto-clear and resume", ("context", "resume")),
    ("other", "Other", ()),
)

# Values the READER accepts, for keys that have no code-owned tuple. Each
# entry names that reader. Keys absent here fall back to generated choices
# (current, default, recommendation, values either layer holds): memory.mode,
# pm.mode, qa/dev.codex.reasoningEffort, docs.theme, docs.reportTheme,
# bitbucket.mergeGate.preset, and every free-text key (paths, env var names,
# ids, numbers).
_KNOWN_VALUES = {
    # plugin/crew/commands/jira-sync.md:11, plugin/crew/commands/sdp-sync.md:11,
    # plugin/crew/commands/obsidian-sync.md:11; `files` is the default.
    "tracker": ("files", "jira", "sdp", "obsidian"),
    # plugin/crew/hooks/scripts/notify.sh:33 (`none` exits), :55, :61.
    "notify.provider": ("none", "telegram", "teams"),
    # plugin/crew/commands/sdp-sync.md:63
    "sdp.noteVisibility": ("private", "public"),
    # plugin/crew/skills/crew-providers/SKILL.md:425
    "secondOpinion.provider": ("none", "gemini", "local"),
    # plugin/crew/skills/crew-providers/SKILL.md:426
    "secondOpinion.mode": ("cli", "api"),
    # plugin/crew/hooks/scripts/crew_autopilot.py:602 arms only on `plan`.
    "autopilot.mode": ("off", "plan"),
    # plugin/crew/skills/crew-graph/SKILL.md:168
    "graph.mode": ("code-only",),
    # plugin/crew/hooks/scripts/crew_autocycle.py reads true from the machine
    # file only; a repo false vetoes. CONFIG.md §10.
    "context.autoClear.enabled": (True, False, None),
    # plugin/crew/hooks/scripts/crew_resume.py, same rule. CONFIG.md §14a.
    "resume.auto": (True, False, None),
}


def known_values():
    """`_KNOWN_VALUES` plus `context.autoClear.method`, read from
    `crew_platform._AUTOCLEAR_METHODS` (every method some platform delivers).
    Imported lazily: `crew_platform` imports `crew_config`."""
    import crew_platform  # pylint: disable=import-outside-toplevel
    methods = []
    for names in crew_platform._AUTOCLEAR_METHODS.values():  # pylint: disable=protected-access
        methods.extend(name for name in names if name not in methods)
    out = dict(_KNOWN_VALUES)
    out["context.autoClear.method"] = tuple(methods)
    return out


# Dotted path -> (value, one-line reason). From
# `skills/crew-setup/global-config.md`'s role-pin table and its `pm.authority`
# advice. A key without an entry recommends its built-in default.
RECOMMENDATIONS = {
    "pm.authority": ("report-only", "the default on any hesitation: it "
                     "recommends and waits for you"),
    "dev.roles.developer": ({"provider": "codex", "model": "gpt-6-astra"},
                            "global-config.md role-pin table"),
    "dev.roles.security": ({"provider": "codex", "model": "gpt-6-astra"},
                           "global-config.md role-pin table"),
    "qa.roles.phase1": ({"provider": "codex", "model": "gpt-5.6-sol"},
                        "global-config.md role-pin table"),
    "qa.roles.smoke": ({"provider": "codex", "model": "gpt-5.6-sol"},
                       "global-config.md role-pin table"),
    "qa.roles.review": ({"provider": "codex", "model": "gpt-5.6-luna"},
                        "global-config.md role-pin table"),
    "qa.roles.gate": ({"provider": "codex", "model": "gpt-5.6-luna"},
                      "global-config.md role-pin table"),
}

NO_PIN = {}
LAYERS = ("machine", "repo")


def area_of(dotted):
    head = dotted.split(".", 1)[0]
    for area_id, _label, prefixes in AREAS:
        if head in prefixes:
            return area_id
    return AREAS[-1][0]


def _key(value):
    return json.dumps(value, sort_keys=True)


def _role_tables():
    return {"qa.roles": ("qa", crew_state.QA_ROLE_KINDS, crew_state.QA_PROVIDERS),
            "dev.roles": ("dev", crew_state.DEV_ROLE_KINDS, crew_state.DEV_PROVIDERS)}


def _pin_values(providers):
    """"no pin", then provider x known model: `claude` unpinned (it is an
    in-session subagent), `codex` with each `gpt` id, `copilot` with each."""
    out = [NO_PIN]
    for provider in providers:
        if provider == "claude":
            out.append({"provider": "claude"})
            continue
        for model in crew_state.MODEL_DISPLAY:
            if provider == "codex" and crew_state.family("codex", model) != "gpt":
                continue
            out.append({"provider": provider, "model": model})
    return out


def _model_values(dotted):
    parts = dotted.split(".")
    if len(parts) == 3 and parts[0] in ("qa", "dev") and parts[2] == "model":
        return [m for m in crew_state.MODEL_DISPLAY
                if parts[1] != "codex" or crew_state.family("codex", m) == "gpt"]
    return []


def _allowed_at(dotted, layer, value):
    """Would this layer's writer accept `value` at `dotted`? The veto rule and
    the enum check; a hand-edited bad value in either layer is not offered."""
    if layer == "repo" and dotted in crew_config.REPO_VETO_ONLY and value not in (
            False, None):
        return False
    return not crew_config._value_problems({dotted: value})  # pylint: disable=protected-access


def choices(dotted, layer, ctx):
    """The selectable values for `dotted` at `layer`, recommendation first.

    Order: recommendation, current effective value, default, then the key's
    allowed values (`enum_values`, `known_values()`, model ids, or the role
    pins), then any value either layer holds. De-duplicated, and filtered
    through the layer's veto and enum rules. Each is `{value, label, tags}`.
    """
    ordered = [(ctx["recommendation"], "recommended"),
               (ctx["current"], "current")]
    ordered.append((ctx["default"], "default"))
    table = ctx.get("table")
    if table:
        ordered.extend((v, None) for v in _pin_values(_role_tables()[table][2]))
    else:
        allowed = crew_config.enum_values(dotted) or ctx["known"].get(dotted) or ()
        ordered.extend((v, None) for v in allowed)
        ordered.extend((v, None) for v in _model_values(dotted))
    for held in ctx["held"]:
        ordered.append((held, None))

    seen, out = {}, []
    for value, tag in ordered:
        if value is crew_config._MISSING:  # pylint: disable=protected-access
            continue
        key = _key(value)
        if key in seen:
            if tag and tag not in seen[key]["tags"]:
                seen[key]["tags"].append(tag)
            continue
        if not _allowed_at(dotted, layer, value):
            continue
        entry = {"value": copy.deepcopy(value), "tags": [tag] if tag else []}
        seen[key] = entry
        out.append(entry)
    for entry in out:
        label = "no pin" if table and entry["value"] == NO_PIN else json.dumps(
            entry["value"])
        entry["label"] = (f"{label} ({', '.join(entry['tags'])})"
                          if entry["tags"] else label)
    return out


def _dig(node, dotted):
    return crew_config._dig(node, tuple(dotted.split(".")))  # pylint: disable=protected-access


def _unmissing(value):
    return None if value is crew_config._MISSING else value  # pylint: disable=protected-access


def _layers(root, global_path):
    repo_raw = crew_state.load_config(root)
    global_raw = crew_config.read_global_config(global_path)
    global_kept, _ = crew_config.filter_global(global_raw)
    return repo_raw, global_raw, global_kept


def _paths(template):
    """Leaves of `template`, with each open role table expanded to one row per
    known role kind, plus any role the layers already name."""
    out = []
    for dotted in crew_config.leaf_paths(template):
        if dotted in _role_tables():
            out.extend((f"{dotted}.{kind}", dotted)
                       for kind in _role_tables()[dotted][1])
        else:
            out.append((dotted, None))
    return out


def menu_spec(root, layer, global_path=None):
    """Every row of the menu for `layer`, grouped by area.

    `{"layer", "path", "exists", "crewJson", "areas": [{id, label, rows}]}`,
    each row `{path, table, writable, refusedReason, value, source,
    layerValue, default, recommendation, choices}`. `value`/`source` are the
    effective value and the layer that decided it -- `explain_config`'s answer
    for a global key, `repo` or `default` for a repo-only one.
    """
    if layer not in LAYERS:
        raise ValueError(f"layer must be one of {LAYERS}, not {layer!r}")
    defaults = crew_config.default_config()
    repo_raw, global_raw, global_kept = _layers(root, global_path)
    explain = {row["path"]: row for row in crew_config.explain_config(root, global_path)}
    resolved = crew_state.merge_defaults(
        crew_state.merge_defaults(defaults, global_kept),
        crew_config.without_null_shadows(repo_raw, global_kept, defaults))
    known = known_values()
    template = (crew_config.default_global_config() if layer == "machine"
                else defaults)
    own = global_raw if layer == "machine" else repo_raw

    areas = {area_id: [] for area_id, _l, _p in AREAS}
    extra_roles = {}
    for table in _role_tables():
        for raw in (repo_raw, global_raw):
            named = _dig(raw, table)
            if isinstance(named, dict):
                extra_roles.setdefault(table, [])
                extra_roles[table].extend(k for k in named
                                          if k not in extra_roles[table])
    paths = _paths(template)
    for table, kinds in extra_roles.items():
        known_rows = {p for p, _t in paths}
        paths.extend((f"{table}.{kind}", table) for kind in kinds
                     if f"{table}.{kind}" not in known_rows)

    for dotted, table in paths:
        if layer == "machine":
            reason = None if crew_config.is_global_path(dotted) else (
                "repo-only: not settable in the machine-global file")
        else:
            reason = crew_config._repo_refusal(dotted)  # pylint: disable=protected-access
        default = _unmissing(_dig(defaults, dotted))
        if table:
            default = NO_PIN
        if dotted in explain:
            value, source = explain[dotted]["value"], explain[dotted]["source"]
        else:
            value = _unmissing(_dig(resolved, dotted))
            in_repo = _dig(repo_raw, dotted) is not crew_config._MISSING  # pylint: disable=protected-access
            in_global = (crew_config.is_global_path(dotted)
                         and _dig(global_kept, dotted) is not crew_config._MISSING)  # pylint: disable=protected-access
            source = "repo" if in_repo else "global" if in_global else "default"
            if table and value is None:
                value = NO_PIN
        held = [v for v in (_dig(repo_raw, dotted), _dig(global_raw, dotted))
                if v is not crew_config._MISSING]  # pylint: disable=protected-access
        rec = RECOMMENDATIONS.get(dotted) or (default, "default")
        row = {
            "path": dotted,
            "table": table,
            "writable": reason is None,
            "refusedReason": reason,
            "value": value,
            "source": source,
            "layerValue": _unmissing(_dig(own, dotted)),
            "default": default,
            "recommendation": {"value": rec[0], "reason": rec[1]},
            "choices": [],
        }
        if reason is None:
            row["choices"] = choices(dotted, layer, {
                "recommendation": rec[0], "current": value, "default": default,
                "held": held, "known": known, "table": table})
        areas[area_of(dotted)].append(row)

    path = (crew_config.GLOBAL_CONFIG_PATH if global_path is None else global_path
            ) if layer == "machine" else crew_config.repo_config_path(root)
    return {
        "layer": layer,
        "path": path,
        "exists": os.path.isfile(path),
        "crewJson": os.path.isfile(os.path.join(root, ".crew", "crew.json")),
        "areas": [{"id": area_id, "label": label, "rows": areas[area_id]}
                  for area_id, label, _p in AREAS],
    }


def _print_spec(spec):
    print(f"layer: {spec['layer']}  file: {spec['path']}"
          + ("" if spec["exists"] else "  (does not exist)"))
    if spec["layer"] == "repo" and spec["crewJson"]:
        print(crew_config.CREW_JSON_NOTICE)
    for area in spec["areas"]:
        if not area["rows"]:
            continue
        print(f"\n## {area['id']} - {area['label']}")
        for row in area["rows"]:
            print(f"  {row['path']} = {json.dumps(row['value'])}  "
                  f"[{row['source']}]")
            if not row["writable"]:
                print(f"      read-only: {row['refusedReason']}")
                continue
            print("      choices: " + " | ".join(c["label"] for c in row["choices"]))


# --- Save -------------------------------------------------------------------


def save(root, changes, apply, global_path=None):
    """Validate both layers, print both diffs, then (with `apply`) write each
    changed layer once. Returns an exit code: 0, 2 refused, 1 a partial write.

    Both plans are computed before either write: a refusal anywhere means
    nothing is written, which is the whole point of one Save for a pending
    set that spans two files.
    """
    machine = dict((changes or {}).get("machine") or {})
    repo = dict((changes or {}).get("repo") or {})
    target = crew_config.GLOBAL_CONFIG_PATH if global_path is None else global_path
    plans = {}
    try:
        if machine:
            plans["machine"] = crew_config.plan_global_write(machine, global_path)[1]
        if repo:
            plans["repo"] = crew_config.plan_repo_write(root, repo, global_path)[1]
    except (crew_config.GlobalWriteRefused, crew_config.RepoWriteRefused,
            crew_config.ProviderError) as exc:
        print(f"refused, nothing written: {exc}", file=sys.stderr)
        return 2

    verb = "writing" if apply else "would write (dry run)"
    files = {"machine": target, "repo": crew_config.repo_config_path(root)}
    for layer in LAYERS:
        if layer in plans:
            print(f"{layer} layer - {verb}: {files[layer]}")
            crew_config.print_changes(plans[layer])
    if not plans:
        print("nothing pending")
    if repo and os.path.isfile(os.path.join(root, ".crew", "crew.json")):
        print(crew_config.CREW_JSON_NOTICE)
    if not apply:
        return 0

    written = []
    for layer, updates, writer in (
            ("machine", machine, lambda u: crew_config.write_global_config(u, global_path)),
            ("repo", repo, lambda u: crew_config.write_repo_config(root, u, global_path))):
        if not plans.get(layer):
            continue
        try:
            writer(updates)
        except OSError as exc:
            print(f"{layer} layer: NOT written ({exc}); the "
                  + (", ".join(written) or "no") + " layer was. Re-run Save "
                  "for the rest once the cause is fixed.", file=sys.stderr)
            return 1
        written.append(layer)
        print(f"{layer} layer: written")
    return 0


# --- Delete and restore -----------------------------------------------------

BACKUP_PREFIX = "config.json.bak-"


def repo_name(root):
    """The name the owner types to confirm a delete: the basename of `root`,
    the directory whose `.crew/config.json` is deleted. For a checkout that is
    `git rev-parse --show-toplevel`'s basename; it is read from `root` itself
    so a `.crew/` nested inside some other repository names its own
    directory, never the outer one's."""
    return os.path.basename(os.path.realpath(root))


def _stamp(now):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now.astimezone(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _free_backup(root, now):
    base = os.path.join(root, ".crew", BACKUP_PREFIX + _stamp(now))
    candidate, slot = base, 1
    while os.path.exists(candidate):
        slot += 1
        candidate = f"{base}-{slot}"
    return candidate


def _backup(src, dest):
    """Copy, fsync, byte-compare. Raises OSError on any failure."""
    shutil.copy2(src, dest)
    with open(dest, "rb+") as handle:
        os.fsync(handle.fileno())
    with open(src, "rb") as a, open(dest, "rb") as b:
        if a.read() != b.read():
            raise OSError(f"backup {dest} does not match {src}")


def _post_heal_rows(root, global_path):
    """`explain_config` rows as they will read once platform-sync has healed
    the deleted file with the built-in defaults: the same resolver, run on a
    scratch repo holding exactly what `heal_config` writes."""
    with tempfile.TemporaryDirectory() as scratch:
        os.makedirs(os.path.join(scratch, ".crew"))
        with open(os.path.join(scratch, ".crew", "config.json"), "w",
                  encoding="utf-8") as handle:
            handle.write(json.dumps(crew_config.default_config(), indent=2) + "\n")
        return {row["path"]: row for row in
                crew_config.explain_config(scratch, global_path)}


def _widens(dotted, before, after):
    spec = crew_state.ratchet_spec(dotted)
    if spec is not None:
        return spec[2](after) > spec[2](before)
    if dotted in crew_config._RATCHETED:  # pylint: disable=protected-access
        rank = crew_config._RATCHETED[dotted][0]  # pylint: disable=protected-access
        return rank(after) > rank(before)
    return crew_config._consent_widening(dotted, after)  # pylint: disable=protected-access


def delete_preview(root, global_path=None):
    """What deleting `.crew/config.json` changes, as `{path, before, after,
    widens}` rows. `before` is what is in force now; `after` is what platform-
    sync's heal leaves in force. Ratcheted keys follow the ratchet: an absent
    repo value is the floor, so a repo narrowing under a wider machine value
    does not widen on delete unless the DEFAULT is wider (`guards.roleWrites`,
    `change.requireForProduction`)."""
    defaults = crew_config.default_config()
    repo_raw = crew_state.load_config(root)
    now = {row["path"]: row["value"] for row in
           crew_config.explain_config(root, global_path)}
    later = {path: row["value"] for path, row in
             _post_heal_rows(root, global_path).items()}
    rows = []
    for dotted in crew_config.leaf_paths(defaults):
        if dotted in now:
            before, after = now[dotted], later.get(dotted)
        else:
            held = _dig(repo_raw, dotted)
            if held is crew_config._MISSING:  # pylint: disable=protected-access
                continue
            before, after = held, _unmissing(_dig(defaults, dotted))
        if _key(before) == _key(after):
            continue
        rows.append({"path": dotted, "before": before, "after": after,
                     "widens": _widens(dotted, before, after)})
    return rows


DELETE_NOTICE = (
    "What deleting means on disk:",
    "  - Until the next SessionStart there is NO .crew/config.json. "
    "crew_state.load_config returns {} and isCrew is false, so every hook "
    "that gates on isCrew stands down; the scope guard and completion audit "
    "read scope.mode as off (crew_ticket.configured_mode).",
    "  - At the next SessionStart, platform-sync (crew_platform.heal_config) "
    "recreates .crew/config.json from the built-in defaults, because .crew/ "
    "still exists. The rows above are that state.",
    "  - Only .crew/config.json is removed. .crew/crew.json, verify.json, the "
    "codemap, backups and ticket state are untouched.",
)


def _print_preview(root, rows):
    print(f"delete {crew_config.repo_config_path(root)} - what changes:")
    for row in rows:
        mark = "  !" if row["widens"] else ""
        print(f"  {row['path']}: {json.dumps(row['before'])} -> "
              f"{json.dumps(row['after'])}{mark}")
    if not rows:
        print("  no setting changes value")
    for line in DELETE_NOTICE:
        print(line)


def _script_command(root, *args):
    return " ".join(shlex.quote(part) for part in (
        sys.executable, os.path.abspath(__file__), "--root",
        os.path.abspath(root)) + args)


def delete_repo_config(root, confirm, apply, now=None, global_path=None):
    """Preview, then (typed name + `apply`) back up, verify, and delete.

    Order is the safety: the confirmation, then a copy to a fresh
    `config.json.bak-<UTC>` that is fsynced and byte-compared, and only then
    `os.remove`. Any failure before the remove leaves the file in place and
    exits 2. Returns 0 on a delete or a confirmed dry run.
    """
    path = crew_config.repo_config_path(root)
    if not os.path.isfile(path):
        print(f"no {path} to delete", file=sys.stderr)
        return 2
    _print_preview(root, delete_preview(root, global_path))
    name = repo_name(root)
    if confirm != name:
        why = "no confirmation" if confirm is None else f"{confirm!r} is not the repo name"
        print(f"refused ({why}): type the repo name to confirm - "
              f"--confirm {name}", file=sys.stderr)
        return 2
    backup = _free_backup(root, now)
    if not apply:
        print(f"would back up to {backup}, verify it, then delete {path} "
              "(dry run; add --apply)")
        return 0
    try:
        _backup(path, backup)
    except OSError as exc:
        print(f"refused: the backup could not be written and verified ({exc}); "
              f"{path} left in place", file=sys.stderr)
        return 2
    os.remove(path)
    print(f"backed up to {backup} (verified) and deleted {path}")
    print("restore: " + _script_command(root, "restore-repo", "--from",
                                        os.path.abspath(backup), "--apply"))
    return 0


def _valid_backup(root, backup):
    crew_dir = os.path.realpath(os.path.join(root, ".crew"))
    real = os.path.realpath(backup)
    if os.path.dirname(real) != crew_dir:
        return f"{backup} is not in {crew_dir}"
    if not os.path.basename(real).startswith(BACKUP_PREFIX):
        return f"{backup} is not named {BACKUP_PREFIX}*"
    try:
        with open(real, encoding="utf-8-sig") as handle:
            parsed = json.load(handle)
    except (OSError, ValueError) as exc:
        return f"{backup} does not parse ({exc})"
    if not isinstance(parsed, dict) or not parsed:
        return f"{backup} is not a config (empty or not a JSON object)"
    return None


def restore_repo_config(root, backup, apply, now=None):
    """Copy a `config.json.bak-*` back to `.crew/config.json`.

    A config already there (platform-sync's healed defaults, most often) is
    backed up to a fresh `.bak-` first, so a restore never destroys a file
    either. The copy is sibling-then-replace, like every crew config write.
    """
    problem = _valid_backup(root, backup)
    if problem:
        print(f"refused: {problem}", file=sys.stderr)
        return 2
    path = crew_config.repo_config_path(root)
    exists = os.path.isfile(path)
    if not apply:
        print(f"would restore {backup} to {path}"
              + (" (backing up the current file first)" if exists else "")
              + " (dry run; add --apply)")
        return 0
    if exists:
        saved = _free_backup(root, now)
        try:
            _backup(path, saved)
        except OSError as exc:
            print(f"refused: could not back up the current {path} ({exc})",
                  file=sys.stderr)
            return 2
        print(f"backed up the current file to {saved}")
    with open(backup, "rb") as handle:
        data = handle.read()
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    print(f"restored {backup} to {path}")
    return 0


# --- CLI --------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--global-path", default=None,
                        help="override ~/.claude/crew/config.json (testing)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    spec_p = sub.add_parser("spec", help="the menu rows for one layer")
    spec_p.add_argument("--layer", choices=LAYERS, required=True)
    spec_p.add_argument("--area", default=None)
    spec_p.add_argument("--json", action="store_true")
    save_p = sub.add_parser("save", help="validate both layers, then write each once")
    save_p.add_argument("--changes", required=True,
                        help='{"machine": {PATH: VALUE}, "repo": {PATH: VALUE}}')
    save_p.add_argument("--apply", action="store_true")
    del_p = sub.add_parser("delete-repo", help="preview, back up and delete .crew/config.json")
    del_p.add_argument("--confirm", default=None, metavar="REPO_NAME")
    del_p.add_argument("--apply", action="store_true")
    res_p = sub.add_parser("restore-repo", help="restore a config.json.bak-* backup")
    res_p.add_argument("--from", dest="source", required=True)
    res_p.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if args.cmd == "spec":
        spec = menu_spec(args.root, args.layer, args.global_path)
        if args.area:
            ids = [a[0] for a in AREAS]
            if args.area not in ids:
                print(f"unknown area {args.area!r} (known: {', '.join(ids)})",
                      file=sys.stderr)
                return 2
            spec["areas"] = [a for a in spec["areas"] if a["id"] == args.area]
        if args.json:
            print(json.dumps(spec, indent=2))
        else:
            _print_spec(spec)
        return 0
    if args.cmd == "save":
        try:
            changes = json.loads(args.changes)
        except ValueError as exc:
            print(f"--changes is not JSON: {exc}", file=sys.stderr)
            return 2
        if not isinstance(changes, dict) or set(changes) - set(LAYERS):
            print('--changes must be {"machine": {...}, "repo": {...}}',
                  file=sys.stderr)
            return 2
        return save(args.root, changes, args.apply, args.global_path)
    if args.cmd == "delete-repo":
        return delete_repo_config(args.root, args.confirm, args.apply,
                                  global_path=args.global_path)
    return restore_repo_config(args.root, args.source, args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
