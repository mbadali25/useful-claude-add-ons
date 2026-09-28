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
import sys
import tempfile

import crew_config
import crew_config_files
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


def _probe_for(root, layer, global_path, pending):
    """`(probe, digest, unwritable)` for `layer`.

    `probe(dotted, value)` runs the layer's own PLANNER on the real file with
    the layer's pending set plus the candidate, and returns the refusal
    message or None -- so a value is offered only when Save would accept it
    on the file it would produce, a bad value already in the file included.
    The file is read once per spec (`snapshot`); the rules are the planner's.
    """
    pending_layer = dict((pending or {}).get(layer) or {})
    if layer == "repo":
        refused = (crew_config.RepoWriteRefused, crew_config.ProviderError)
        try:
            snap = crew_config.repo_snapshot(root)
        except crew_config.RepoWriteRefused as exc:
            return (lambda _d, _v: str(exc)), None, str(exc)
        machine = crew_config.machine_view(global_path)

        def plan(updates):
            crew_config.plan_repo_write(root, updates, global_path, snapshot=snap,
                                        machine=machine)
    else:
        refused = (crew_config.GlobalWriteRefused, crew_config.ProviderError)
        try:
            snap = crew_config.global_snapshot(global_path)
        except crew_config.GlobalWriteRefused as exc:
            return (lambda _d, _v: str(exc)), None, str(exc)

        def plan(updates):
            crew_config.plan_global_write(updates, global_path, snapshot=snap)

    def probe(dotted, value):
        try:
            plan({**pending_layer, dotted: value})
        except refused as exc:
            return str(exc)
        return None
    return probe, snap[2], None


# The null choice's tag, for the meanings a repo null has beyond "unset".
_NULL_TAGS = {"inherits the machine-global value": "inherit machine",
              "clears the veto": "clear veto"}


def choices(dotted, layer, ctx):
    """`(entries, refusal)`: the selectable values for `dotted` at `layer`,
    recommendation first, and the first refusal message when the probe
    refused every candidate (the row is then read-only with that reason).

    Order: recommendation, current effective value, default, a repo null
    that inherits or clears a veto, then the key's allowed values
    (`enum_values`, `known_values()`, model ids, or the role pins), then any
    value either layer holds. De-duplicated, and each one kept only when
    `ctx["probe"]` -- the layer's planner on the merged file -- accepts it.
    Each is `{value, label, tags}`.
    """
    ordered = [(ctx["recommendation"], "recommended"),
               (ctx["current"], "current")]
    ordered.append((ctx["default"], "default"))
    null_tag = _NULL_TAGS.get(crew_config.null_means(dotted, layer))
    if null_tag:
        ordered.append((None, null_tag))
    table = ctx.get("table")
    if table:
        ordered.extend((v, None) for v in _pin_values(_role_tables()[table][2]))
    else:
        allowed = crew_config.enum_values(dotted) or ctx["known"].get(dotted) or ()
        ordered.extend((v, None) for v in allowed)
        ordered.extend((v, None) for v in _model_values(dotted))
    for held in ctx["held"]:
        ordered.append((held, None))

    seen, out, refusal = {}, [], None
    for value, tag in ordered:
        if value is crew_config._MISSING:  # pylint: disable=protected-access
            continue
        key = _key(value)
        if key in seen:
            if seen[key] is not None and tag and tag not in seen[key]["tags"]:
                seen[key]["tags"].append(tag)
            continue
        problem = ctx["probe"](dotted, value)
        if problem is not None:
            seen[key] = None
            refusal = refusal or problem
            continue
        entry = {"value": copy.deepcopy(value), "tags": [tag] if tag else []}
        seen[key] = entry
        out.append(entry)
    for entry in out:
        label = "no pin" if table and entry["value"] == NO_PIN else json.dumps(
            entry["value"])
        entry["label"] = (f"{label} ({', '.join(entry['tags'])})"
                          if entry["tags"] else label)
    return out, (None if out else refusal)


def _dig(node, dotted):
    return crew_config._dig(node, tuple(dotted.split(".")))  # pylint: disable=protected-access


def _unmissing(value):
    return None if value is crew_config._MISSING else value  # pylint: disable=protected-access


def _layers(root, global_path):
    repo_raw = crew_state.load_config(root)
    global_raw = crew_config.read_global_config(global_path)
    global_kept, _ = crew_config.filter_global(global_raw)
    return repo_raw, global_raw, global_kept


def _source(repo_pruned, global_kept, dotted, value, defaults):
    """`explain_config`'s source rule for a row it does not cover (an
    expanded `qa.roles.<kind>` row, a repo-only leaf): each layer's
    contribution judged by `crew_config._layer_supplies` on the same pruned
    layers, and `repo+global` for a dict both layers put keys into -- the
    merged value, not a contest one layer won."""
    parts = tuple(dotted.split("."))
    from_repo = crew_config._layer_supplies(repo_pruned, parts, defaults)  # pylint: disable=protected-access
    from_global = (crew_config.is_global_path(dotted) and crew_config._layer_supplies(  # pylint: disable=protected-access
        global_kept, parts, defaults))
    if from_repo and from_global and isinstance(value, dict):
        return "repo+global"
    return "repo" if from_repo else "global" if from_global else "default"


# Repo-refused leaves the machine template omits, shown read-only at the
# machine layer too: `platform.*` is platform-sync's at both layers and
# `schema` is never a setting. Their reasons are the repo writer's own.
_MACHINE_READ_ONLY = ("platform", "schema")


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


def menu_spec(root, layer, global_path=None, pending=None):
    """Every row of the menu for `layer`, grouped by area.

    `{"layer", "path", "exists", "crewJson", "areas": [{id, label, rows}]}`,
    each row `{path, table, writable, refusedReason, value, source,
    layerValue, default, recommendation, choices}`. `value`/`source` are the
    effective value and the layer that decided it -- `explain_config`'s answer
    for a global key, `repo` or `default` for a repo-only one. `pending` is
    the session's unsaved `{"machine": {...}, "repo": {...}}`: choices are
    judged on the file Save would produce with it. `digest` is the sha256 of
    the layer's file as read (None when absent), for `save --expect-*`.
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
    repo_pruned = crew_config.without_null_shadows(repo_raw, global_kept, defaults)
    probe, digest, unwritable = _probe_for(root, layer, global_path, pending)

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
    if layer == "machine":
        paths.extend((dotted, None) for dotted in crew_config.leaf_paths(defaults)
                     if dotted.split(".", 1)[0] in _MACHINE_READ_ONLY)
    for table, kinds in extra_roles.items():
        known_rows = {p for p, _t in paths}
        paths.extend((f"{table}.{kind}", table) for kind in kinds
                     if f"{table}.{kind}" not in known_rows)

    for dotted, table in paths:
        if layer == "machine":
            reason = None if crew_config.is_global_path(dotted) else (
                crew_config._repo_refusal(dotted)  # pylint: disable=protected-access
                or "repo-only: not settable in the machine-global file")
        else:
            reason = crew_config._repo_refusal(dotted)  # pylint: disable=protected-access
        reason = reason or unwritable
        default = _unmissing(_dig(defaults, dotted))
        if table:
            default = NO_PIN
        if dotted in explain:
            value, source = explain[dotted]["value"], explain[dotted]["source"]
        else:
            value = _unmissing(_dig(resolved, dotted))
            source = _source(repo_pruned, global_kept, dotted, value, defaults)
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
            row["choices"], blocked = choices(dotted, layer, {
                "recommendation": rec[0], "current": value, "default": default,
                "held": held, "known": known, "table": table, "probe": probe})
            if blocked:
                row["writable"], row["refusedReason"] = False, blocked
        areas[area_of(dotted)].append(row)

    path = (crew_config.GLOBAL_CONFIG_PATH if global_path is None else global_path
            ) if layer == "machine" else crew_config.repo_config_path(root)
    return {
        "layer": layer,
        "path": path,
        "exists": os.path.isfile(path),
        "refusedReason": unwritable,
        "digest": digest,
        "crewJson": os.path.isfile(os.path.join(root, ".crew", "crew.json")),
        "areas": [{"id": area_id, "label": label, "rows": areas[area_id]}
                  for area_id, label, _p in AREAS],
    }


def _print_spec(spec):
    print(f"layer: {spec['layer']}  file: {spec['path']}"
          + ("" if spec["exists"] else "  (does not exist)"))
    if spec["layer"] == "repo" and spec["crewJson"]:
        print(crew_config.CREW_JSON_NOTICE)
    print(f"digest: {spec['digest'] or 'none (the file is absent)'}")
    if spec["refusedReason"]:
        print(f"every row is read-only: {spec['refusedReason']}")
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


def _current_digest(path):
    """The file's `state_digest` now: its sha256, or `ABSENT`."""
    return crew_config_files.read_tolerant(path)[1]


def _plan_both(root, machine, repo, global_path):
    """`(plans, digests, machine_after)` for one Save, both layers validated
    before either is written. The repo plan's widening marks are judged
    against the machine file as THIS Save leaves it, and the machine digest
    is recorded whenever either layer changes: a repo-only Save depends on
    the machine file too (review round 3)."""
    plans, digests, after = {}, {}, None
    if machine:
        snap = crew_config.global_snapshot(global_path)
        digests["machine"] = snap[2]
        merged, plans["machine"] = crew_config.plan_global_write(
            machine, global_path, snapshot=snap)
        after = crew_config.filter_global(merged)[0]
        view = (after, None)
    else:
        view = crew_config.machine_view(global_path)
        digests["machine"] = view[1]
    if repo:
        snap = crew_config.repo_snapshot(root)
        digests["repo"] = snap[2]
        plans["repo"] = crew_config.plan_repo_write(
            root, repo, global_path, snapshot=snap, machine=view)[1]
    return plans, digests, after


def _machine_as_written(global_path, planned):
    """The digest of the machine file the repo write is bound to, after this
    Save wrote it: its bytes read now, accepted only when they hold what the
    plan wrote (else a foreign write landed in between; None)."""
    parsed, state = crew_config_files.read_tolerant(
        crew_config.GLOBAL_CONFIG_PATH if global_path is None else global_path)
    return state if crew_config.filter_global(parsed)[0] == planned else None


def save(root, changes, apply, global_path=None, expect=None):
    """Validate both layers, print both diffs, then (with `apply`) write each
    changed layer once. Returns an exit code: 0, 2 refused, 1 a partial write.

    Both plans are computed before either write: a refusal anywhere means
    nothing is written, which is the whole point of one Save for a pending
    set that spans two files. The dry run prints the machine digest whenever
    anything changes and the repo digest when the repo does (`ABSENT` for no
    file); `expect` (`{"machine": d, "repo": d}`, from those lines, any
    subset) is checked before either write and passed to each writer, whose
    compare-and-swap refuses a file that changed in between. The repo write
    is bound to the machine file too, since its widening marks read it.
    """
    machine = dict((changes or {}).get("machine") or {})
    repo = dict((changes or {}).get("repo") or {})
    expect = {k: v for k, v in (expect or {}).items() if v is not None}
    target = crew_config.GLOBAL_CONFIG_PATH if global_path is None else global_path
    files = {"machine": target, "repo": crew_config.repo_config_path(root)}
    try:
        plans, digests, after = _plan_both(root, machine, repo, global_path)
    except (crew_config.GlobalWriteRefused, crew_config.RepoWriteRefused,
            crew_config.ProviderError) as exc:
        print(f"refused, nothing written: {exc}", file=sys.stderr)
        return 2

    verb = "writing" if apply else "would write (dry run)"
    for layer in LAYERS:
        if layer in plans:
            print(f"{layer} layer - {verb}: {files[layer]}")
        if layer in plans or (plans and layer == "machine"):
            print(f"{layer} digest: {digests[layer]}")
        if layer in plans:
            crew_config.print_changes(plans[layer])
    if not plans:
        print("nothing pending")
    if repo and os.path.isfile(os.path.join(root, ".crew", "crew.json")):
        print(crew_config.CREW_JSON_NOTICE)
    if not apply:
        return 0

    for layer in LAYERS:
        if layer in expect and _current_digest(files[layer]) != expect[layer]:
            print(f"refused, nothing written: the {layer} layer changed since "
                  f"the dry run ({files[layer]}); re-run the dry run and "
                  "review it again", file=sys.stderr)
            return 2

    written = []
    for layer in LAYERS:
        if not plans.get(layer):
            continue
        try:
            if layer == "machine":
                crew_config.write_global_config(machine, global_path,
                                                expect=expect.get("machine"))
            else:
                bound = (expect.get("machine") if "machine" not in written
                         else _machine_as_written(global_path, after))
                if "machine" in written and bound is None:
                    raise crew_config.RepoWriteConflict(
                        "the machine-global file changed after this Save "
                        "wrote it, so the repo plan's widening marks no "
                        "longer hold")
                crew_config.write_repo_config(root, repo, global_path,
                                              expect=expect.get("repo"),
                                              expect_global=bound)
        except (OSError, crew_config.GlobalWriteRefused,
                crew_config.RepoWriteRefused, crew_config.ProviderError) as exc:
            # Validated a moment ago, refused now: the file changed (deleted,
            # corrupted, edited, or its digest moved) between the plan and
            # this write. Same report as an OS failure -- which layer landed,
            # which did not.
            done = (f"the {', '.join(written)} layer was written"
                    if written else "nothing was written")
            print(f"{layer} layer: NOT written ({exc}); {done}. Re-run Save "
                  "for the rest once the cause is fixed.", file=sys.stderr)
            conflict = isinstance(exc, (crew_config.GlobalWriteConflict,
                                        crew_config.RepoWriteConflict))
            return 2 if conflict and not written else 1
        written.append(layer)
        print(f"{layer} layer: written")
    return 0


# --- Delete and restore -----------------------------------------------------

BACKUP_PREFIX = "config.json.bak-"


def repo_name(root):
    """The name the owner types to confirm a delete: the basename of
    `git rev-parse --show-toplevel` run in `root` (the checkout's name, a
    worktree's own directory), falling back to `root`'s basename outside git
    or when git cannot run. `crew_ticket.toplevel` is that call, reused.
    Imported lazily, like `crew_platform` above."""
    import crew_ticket  # pylint: disable=import-outside-toplevel
    top = crew_ticket.toplevel(root)
    return os.path.basename(top or os.path.realpath(root))


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


def _file_leaves(parsed, known):
    """The file's own leaves that no known leaf covers: unknown keys, and
    anything under a key the defaults do not hold. A leaf under a known open
    table (`qa.roles.review.provider`) is that table's row, not its own."""
    out = []
    for dotted in crew_config.leaf_paths(parsed):
        if dotted in known or any(dotted.startswith(k + ".") for k in known):
            continue
        out.append(dotted)
    return out


def _redetected():
    """The `platform.*` leaves platform-sync writes (`crew_platform.
    DERIVED_KEYS`); any other `platform.*` leaf is removed with the file.
    Imported lazily: `crew_platform` imports `crew_config`."""
    import crew_platform  # pylint: disable=import-outside-toplevel
    return frozenset("platform." + key for key in crew_platform.DERIVED_KEYS)


def delete_preview(root, parsed, global_path=None):
    """What deleting `.crew/config.json` changes, walking the FILE's own
    leaves as well as the known ones, so the preview is the whole of what the
    delete removes.

    Rows: `{path, before, after, widens}` for a known key whose value changes;
    `before == after` plus `heldAgainst` for a ratcheted key a repo narrowing
    keeps in force anyway (an absent repo value is the floor; `guards.
    roleWrites` and `change.requireForProduction` widen because their DEFAULT
    is wider); `removed: True` for a leaf crew does not know (preserved by
    every write, removed with the file); `redetected: True` for a
    `platform.*` leaf in `crew_platform.DERIVED_KEYS`, which the same
    SessionStart that heals the file re-detects from this machine -- a
    "becomes null" row would be a change that never happens. Any other
    `platform.*` leaf is unknown, so `removed`.
    `before` is what is in force now, `after` what platform-sync's heal leaves.
    """
    defaults = crew_config.default_config()
    known = crew_config.leaf_paths(defaults)
    known_set = set(known)
    now = {row["path"]: row["value"] for row in
           crew_config.explain_config(root, global_path)}
    later = {path: row["value"] for path, row in
             _post_heal_rows(root, global_path).items()}
    global_kept, _ = crew_config.filter_global(
        crew_config.read_global_config(global_path))
    rows = []
    redetected = _redetected()
    for dotted in known + _file_leaves(parsed, known_set):
        held = _dig(parsed, dotted)
        if dotted in redetected:
            if held is not crew_config._MISSING:  # pylint: disable=protected-access
                rows.append({"path": dotted, "before": held, "after": held,
                             "widens": False, "redetected": True})
            continue
        if dotted not in known_set:
            rows.append({"path": dotted, "before": held, "after": None,
                         "widens": False, "removed": True})
            continue
        if dotted in now:
            before, after = now[dotted], later.get(dotted)
        else:
            if held is crew_config._MISSING:  # pylint: disable=protected-access
                continue
            before, after = held, _unmissing(_dig(defaults, dotted))
        if _key(before) == _key(after):
            holder = _held_by_ratchet(dotted, parsed, global_kept, before)
            if holder is not None:
                rows.append({"path": dotted, "before": before, "after": after,
                             "widens": False, "heldAgainst": holder})
            continue
        rows.append({"path": dotted, "before": before, "after": after,
                     "widens": _widens(dotted, before, after)})
    return rows


def _held_by_ratchet(dotted, repo_raw, global_kept, value):
    """The machine value a repo narrowing sits under, when deleting leaves it
    in force anyway; else None. A ratcheted key takes the LOWER rank and an
    absent repo value is the default, which is the floor
    (`crew_guards.effective_ratcheted`), so a repo `block` under a machine
    `allow` stays `block` -- named, so the preview says why no widening."""
    spec = crew_state.ratchet_spec(dotted)
    if spec is None or _dig(repo_raw, dotted) is crew_config._MISSING:  # pylint: disable=protected-access
        return None
    machine = _dig(global_kept, dotted)
    if machine is crew_config._MISSING or spec[2](machine) <= spec[2](value):  # pylint: disable=protected-access
        return None
    return machine


DELETE_NOTICE = (
    "What deleting means on disk:",
    "  - Until the next SessionStart there is NO .crew/config.json. "
    "crew_state.load_config returns {} and isCrew is false, so every hook "
    "that gates on isCrew stands down; the scope guard and completion audit "
    "read scope.mode as off (crew_ticket.configured_mode).",
    "  - At the next SessionStart, platform-sync (crew_platform.heal_config) "
    "recreates .crew/config.json from the built-in defaults, because .crew/ "
    "still exists. The rows above are that state.",
    "  - The file is not copied: it is MOVED to the backup name in one "
    "rename, under the config lock, and compared with what this preview "
    "read. A file that changed since is put back and nothing is deleted.",
    "  - Only .crew/config.json is removed. .crew/crew.json, verify.json, the "
    "codemap, backups and ticket state are untouched.",
)


def _print_preview(root, rows):
    print(f"delete {crew_config.repo_config_path(root)} - what changes:")
    changed = [row for row in rows if not {"heldAgainst", "removed",
                                           "redetected"} & set(row)]
    for row in changed:
        mark = "  !" if row["widens"] else ""
        print(f"  {row['path']}: {json.dumps(row['before'])} -> "
              f"{json.dumps(row['after'])}{mark}")
    for row in rows:
        if row.get("removed"):
            print(f"  {row['path']}: {json.dumps(row['before'])} -> (removed) "
                  "- not a crew setting; kept by every write, removed with "
                  "the file")
    if not changed and not any(row.get("removed") for row in rows):
        print("  no setting changes value")
    for row in rows:
        if "heldAgainst" in row:
            print(f"  {row['path']}: stays {json.dumps(row['after'])} - the "
                  f"machine-global {json.dumps(row['heldAgainst'])} does not "
                  "widen it: this key ratchets, and an absent repo value is "
                  "the default, which is the floor")
    redetected = [row for row in rows if row.get("redetected")]
    if redetected:
        print("re-detected by platform-sync at the next SessionStart (from "
              "this machine; a key it finds no value for is left unset):")
        for row in redetected:
            print(f"  {row['path']}: now {json.dumps(row['before'])}")
    for line in DELETE_NOTICE:
        print(line)


def command_forms(parts):
    """`parts` as one command line per shell, every form always given.

    `sh`: `shlex.quote`. `cmd`: cmd.exe does not honour single quotes, so each
    part is double-quoted with its backslashes turned to forward slashes --
    Python and every Windows API accept them, and a Windows path cannot
    contain `"`. `powershell`: the call operator and single-quoted parts, a
    `'` inside doubled (PowerShell's only escape in a single-quoted string).
    """
    return {
        "sh": " ".join(shlex.quote(part) for part in parts),
        "cmd": " ".join('"' + part.replace("\\", "/") + '"' for part in parts),
        "powershell": "& " + " ".join("'" + part.replace("'", "''") + "'"
                                      for part in parts),
    }


def restore_lines(root, backup):
    """The three labelled restore lines delete prints, plus a warning when the
    cmd form holds a `%` (cmd.exe may expand it as a variable, and no escape
    survives both interactive and batch use)."""
    forms = command_forms((sys.executable, os.path.abspath(__file__), "--root",
                           os.path.abspath(root), "restore-repo", "--from",
                           os.path.abspath(backup), "--apply"))
    lines = [f"restore (sh): {forms['sh']}", f"restore (cmd): {forms['cmd']}"]
    if "%" in forms["cmd"]:
        lines.append("  warning: the cmd line contains %, which cmd.exe may "
                     "expand as a variable; use the sh or PowerShell line")
    lines.append(f"restore (PowerShell): {forms['powershell']}")
    return lines


class DeleteRefused(Exception):
    """The repo config cannot be deleted as it stands; nothing was touched."""


def _machine_path(global_path):
    return crew_config.GLOBAL_CONFIG_PATH if global_path is None else global_path


def _machine_digest(global_path):
    return crew_config_files.read_tolerant(_machine_path(global_path))[1]


def plan_delete(root, global_path=None):
    """Phase one: read and HOLD the file's bytes, refusing a file `restorable`
    rejects or one that is not a regular file (`read_restorable`, the read
    restore shares: a symlink moved into a backup is one restore refuses),
    and build the preview.

    `{"path", "held", "digest", "machine", "machinePath", "parsed", "rows",
    "name"}`: `digest` and `machine` are what the preview was computed from,
    and what `--apply` must name (review round 3); `machinePath` is the
    machine file they were read from."""
    path = crew_config.repo_config_path(root)
    try:
        parsed, held = crew_config_files.read_restorable(path)
    except crew_config_files.Unreadable as exc:
        if exc.kind == "absent":
            raise DeleteRefused(f"no {path} to delete") from exc
        if exc.kind == "notregular":
            raise DeleteRefused(
                f"{exc}. Its backup would be one a restore refuses, so it is "
                "not deleted; replace it with a regular file or remove it by "
                "hand") from exc
        raise DeleteRefused(
            f"{exc}. A restore could not take this file back, so it is not "
            "deleted. platform-sync backs an unreadable config up to "
            "config.json.broken and heals it at the next SessionStart; or "
            "remove it by hand") from exc
    machine = _machine_digest(global_path)
    rows = delete_preview(root, parsed, global_path)
    if _machine_digest(global_path) != machine:
        raise DeleteRefused("the machine-global file changed while the "
                            "preview was built; run it again")
    return {"path": path, "held": held, "digest": crew_config_files.digest(held),
            "machine": machine, "machinePath": _machine_path(global_path),
            "parsed": parsed, "rows": rows, "name": repo_name(root)}


def _unbound(plan, expect):
    """Why `expect` does not name the preview `plan` was built from, or None.
    Both digests are required: the rows depend on the repo file AND the
    machine file, and the typed name confirms those rows, not a fresh plan."""
    expect = expect or {}
    for layer, have in (("repo", plan["digest"]), ("machine", plan["machine"])):
        if expect.get(layer) is None:
            return (f"--apply needs --expect-{layer} <digest> from the preview "
                    "(the dry run prints it), so the delete is the one the "
                    "preview showed")
        if expect[layer] != have:
            return (f"the {layer} file changed since the preview (digest "
                    f"{have}, expected {expect[layer]}); run the preview again")
    return None


def apply_delete(root, plan, confirm, now=None, expect=None):
    """Phase two: the typed name and the preview's two digests (`expect`),
    then, under the machine lock and then the repo config lock (crew's one
    order), the machine digest again -- the preview's widening rows read that
    file, so a machine write since refuses (review round 4) -- then ONE
    no-clobber rename of the file to a fresh `config.json.bak-<UTC>` (the
    backup is the original inode: no copy, no moment the bytes are at
    neither name), then compare the moved bytes with the held ones. A
    mismatch means the file changed since the preview: it is moved straight
    back, never over a file saved in the gap. Returns an exit code: 0
    deleted, 2 refused (file in place), 1 a foreign writer interleaved (every
    file kept, each named)."""
    path = plan["path"]
    if confirm != plan["name"]:
        why = ("no confirmation" if confirm is None
               else f"{confirm!r} is not the repo name")
        print(f"refused ({why}): type the repo name to confirm - "
              f"--confirm {plan['name']}", file=sys.stderr)
        return 2
    problem = _unbound(plan, expect)
    if problem:
        print(f"refused, nothing deleted: {problem}", file=sys.stderr)
        return 2
    try:
        with crew_config_files.machine_lock(plan["machinePath"]), \
                crew_config_files.Lock(path):
            now_machine = _machine_digest(plan["machinePath"])
            if now_machine != plan["machine"]:
                print(f"refused, nothing deleted: the machine-global file "
                      f"{plan['machinePath']} changed since the preview "
                      f"(digest {now_machine}, expected {plan['machine']}); "
                      "run the preview again", file=sys.stderr)
                return 2
            backup = _free_backup(root, now)
            got = crew_config_files.move_aside(path, backup)
            if got != plan["held"]:
                try:
                    crew_config_files.move_no_clobber(backup, path)
                except FileExistsError:
                    print(f"refused: {path} changed since the preview and a "
                          f"new file appeared there too; the moved one is at "
                          f"{backup}. Check both.", file=sys.stderr)
                    return 1
                print(f"refused: {path} changed since the preview; it is back "
                      "in place and nothing was deleted. Re-run the preview.",
                      file=sys.stderr)
                return 2
    except crew_config_files.Busy as exc:
        print(f"refused: {exc}; {path} left in place", file=sys.stderr)
        return 2
    except crew_config_files.Displaced as exc:
        print(f"refused: {exc}; nothing is lost: the original is at {backup}, "
              f"check {path}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"refused: {path} could not be moved to a backup ({exc}); left "
              "in place", file=sys.stderr)
        return 2
    if os.path.lexists(path):
        print(f"note: a new {path} appeared after the move; the original is "
              f"at {backup}", file=sys.stderr)
        return 1
    print(f"backed up to {backup} (the original file, moved) and deleted {path}")
    for line in restore_lines(root, backup):
        print(line)
    return 0


def delete_repo_config(root, confirm, apply, now=None, global_path=None,
                       expect=None):
    """Preview (phase one), then with the typed name, `apply` and the
    preview's digests (`expect`), the compare-and-delete (phase two). Returns
    0 on a delete or a confirmed dry run, 2 on a refusal."""
    try:
        plan = plan_delete(root, global_path)
    except DeleteRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    _print_preview(root, plan["rows"])
    print(f"repo digest: {plan['digest']}")
    print(f"machine digest: {plan['machine']}")
    if not apply:
        if confirm != plan["name"]:
            return apply_delete(root, plan, confirm, now)
        print(f"would move {plan['path']} to {_free_backup(root, now)} (the "
              "backup is the file itself), compare it with what this preview "
              "read, and report it deleted (dry run; add --apply "
              f"--expect-repo {plan['digest']} --expect-machine "
              f"{plan['machine']})")
        return 0
    return apply_delete(root, plan, confirm, now, expect)


def _valid_backup(root, backup):
    """`(problem, data)`: the location and name rules, then `read_restorable`
    on the backup itself -- the read delete refuses by (a regular file that
    `restorable` accepts), so the two cannot drift."""
    crew_dir = os.path.realpath(os.path.join(root, ".crew"))
    real = os.path.realpath(backup)
    if os.path.dirname(real) != crew_dir:
        return f"{backup} is not in {crew_dir}", None
    if not os.path.basename(real).startswith(BACKUP_PREFIX):
        return f"{backup} is not named {BACKUP_PREFIX}*", None
    try:
        return None, crew_config_files.read_restorable(backup)[1]
    except crew_config_files.Unreadable as exc:
        return f"{exc}; not a config a restore puts back", None


def restore_repo_config(root, backup, apply, now=None):
    """Put a `config.json.bak-*` back as `.crew/config.json`, byte for byte.

    Under the config lock: a config already there (platform-sync's healed
    defaults, most often) is MOVED aside to a fresh `.bak-` first, so a
    restore never destroys a file either; then the backup's bytes are written
    as a NEW file (`create_bytes`: a file that appeared meanwhile is refused,
    never replaced) and read back and compared.
    """
    problem, data = _valid_backup(root, backup)
    if problem:
        print(f"refused: {problem}", file=sys.stderr)
        return 2
    path = crew_config.repo_config_path(root)
    exists = os.path.lexists(path)
    if not apply:
        print(f"would restore {backup} to {path}"
              + (" (moving the current file aside first)" if exists else "")
              + " (dry run; add --apply)")
        return 0
    try:
        with crew_config_files.Lock(path):
            if os.path.lexists(path):
                saved = _free_backup(root, now)
                crew_config_files.move_aside(path, saved)
                print(f"moved the current file aside to {saved}")
            crew_config_files.create_bytes(path, data)
            with open(path, "rb") as handle:
                back = handle.read()
    except crew_config_files.Busy as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except crew_config_files.Displaced as exc:
        print(f"{exc}; nothing is lost, check {path}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"refused: could not restore {path} ({exc})", file=sys.stderr)
        return 2
    if back != data:
        print(f"{path} does not read back as {backup}; compare them by hand",
              file=sys.stderr)
        return 1
    print(f"restored {backup} to {path}")
    return 0


# --- CLI ---

def validate_change_set(obj, what):
    """None when `obj` is `{"machine"?: {PATH: VALUE}, "repo"?: {PATH: VALUE}}`
    with every PATH a dotted path; else the message. `save --changes` and
    `spec --pending` share it, so a malformed shape is exit 2, never a
    traceback."""
    if not isinstance(obj, dict):
        return f'{what} must be a JSON object {{"machine": {{...}}, "repo": {{...}}}}'
    for layer, updates in obj.items():
        if layer not in LAYERS:
            return f"{what}: {layer!r} is not a layer (machine, repo)"
        if not isinstance(updates, dict):
            return (f"{what}: the {layer} value must be an object of "
                    f"PATH: VALUE, not {type(updates).__name__}")
        for dotted in updates:
            if not crew_config_files.is_dotted(dotted):
                return f"{what}: {dotted!r} is not a dotted path (a.b.c)"
    return None


def _json_arg(raw, what):
    """`(obj, None)` or `(None, message)` for a JSON-shaped change set."""
    try:
        obj = json.loads(raw)
    except ValueError as exc:
        return None, f"{what} is not JSON: {exc}"
    problem = validate_change_set(obj, what)
    return (None, problem) if problem else (obj, None)


def _usage_problem(args):
    for flag, value in (("--expect-machine", getattr(args, "expect_machine", None)),
                        ("--expect-repo", getattr(args, "expect_repo", None))):
        if crew_config_files.expectation_problem(flag, value):
            return crew_config_files.expectation_problem(flag, value)
    for flag, value in (("--confirm", getattr(args, "confirm", None)),
                        ("--from", getattr(args, "source", None))):
        if value is not None and not value.strip():
            return f"{flag} must not be empty"
    return None


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
    spec_p.add_argument("--pending", default=None,
                        help='the unsaved {"machine": {...}, "repo": {...}}')
    save_p = sub.add_parser("save", help="validate both layers, then write each once")
    save_p.add_argument("--changes", required=True,
                        help='{"machine": {PATH: VALUE}, "repo": {PATH: VALUE}}')
    save_p.add_argument("--apply", action="store_true")
    save_p.add_argument("--expect-machine", default=None, metavar="DIGEST")
    save_p.add_argument("--expect-repo", default=None, metavar="DIGEST")
    del_p = sub.add_parser("delete-repo", help="preview, back up and delete .crew/config.json")
    del_p.add_argument("--confirm", default=None, metavar="REPO_NAME")
    del_p.add_argument("--apply", action="store_true")
    del_p.add_argument("--expect-repo", default=None, metavar="DIGEST")
    del_p.add_argument("--expect-machine", default=None, metavar="DIGEST")
    res_p = sub.add_parser("restore-repo", help="restore a config.json.bak-* backup")
    res_p.add_argument("--from", dest="source", required=True)
    res_p.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    problem = _usage_problem(args)
    if problem:
        print(problem, file=sys.stderr)
        return 2

    if args.cmd == "spec":
        pending = None
        if args.pending is not None:
            pending, problem = _json_arg(args.pending, "--pending")
            if problem:
                print(problem, file=sys.stderr)
                return 2
        spec = menu_spec(args.root, args.layer, args.global_path, pending)
        if args.area is not None:
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
        changes, problem = _json_arg(args.changes, "--changes")
        if problem:
            print(problem, file=sys.stderr)
            return 2
        return save(args.root, changes, args.apply, args.global_path,
                    {"machine": args.expect_machine, "repo": args.expect_repo})
    if args.cmd == "delete-repo":
        return delete_repo_config(args.root, args.confirm, args.apply,
                                  global_path=args.global_path, expect={
                                      "repo": args.expect_repo,
                                      "machine": args.expect_machine})
    return restore_repo_config(args.root, args.source, args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
