"""T-0048: `crew_keys.py`, the one table the settings reference is generated
from. Each check here is what keeps that table honest against the code:
one row per leaf, value tuples held by identity (never copied), code-branch
values run through the real reader, and no "coming" key already in the code.
"""
import json
import os
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import l0725_keyset
import crew_autocycle
import crew_autopilot
import crew_config
import crew_guards
import crew_keys
import crew_platform
import crew_resume
import crew_route
import crew_state
import crew_ticket
import crew_tracker

PLUGIN = context._ROOT  # pylint: disable=protected-access


def _leaves():
    return set(crew_config.leaf_paths(crew_config.default_config())) | set(
        crew_config.leaf_paths(crew_config.default_global_config()))


# --- Step 1: one row per leaf, and no copied tuples ---------------------------

def test_every_leaf_has_a_row():
    assert _leaves() <= set(crew_keys.KEY_META)
    assert not [p for p in crew_keys.problems() if p.startswith("missing")]


def test_no_orphan_rows():
    assert set(crew_keys.KEY_META) <= _leaves()
    assert not [p for p in crew_keys.problems() if p.startswith("orphan")]


def test_problems_names_a_deleted_and_an_extra_row(monkeypatch):
    """The two checks above go red on the change they exist to catch."""
    meta = dict(crew_keys.KEY_META)
    del meta["pm.maxDispatches"]
    meta["pm.noSuchKey"] = meta["pm.authority"]
    monkeypatch.setattr(crew_keys, "KEY_META", meta)
    found = crew_keys.problems()
    assert "missing: pm.maxDispatches is a config leaf with no KEY_META row" in found
    assert "orphan: pm.noSuchKey has a KEY_META row and is not a config leaf" in found


def test_ratcheted_rows_do_not_restate_tiers():
    ratcheted = [k for k in crew_keys.KEY_META if crew_guards.ratchet_spec(k)]
    assert ratcheted, "no ratcheted key found: the test would pass vacuously"
    for key in ratcheted:
        assert crew_keys.KEY_META[key]["values"] is None, key
        assert crew_keys.KEY_META[key]["kind"] == "ratchet", key
        assert crew_keys.values_of(key) is crew_guards.RATCHETED_KEYS[key][0], key
    assert not [p for p in crew_keys.problems() if p.startswith("restated")]


def test_a_restated_tier_tuple_is_a_problem(monkeypatch):
    meta = dict(crew_keys.KEY_META)
    meta["install.policy"] = dict(meta["install.policy"],
                                  values=("manual", "ask", "auto"))
    monkeypatch.setattr(crew_keys, "KEY_META", meta)
    assert any(p.startswith("restated tiers: install.policy")
               for p in crew_keys.problems())


@pytest.mark.parametrize("key, obj", [
    ("dev.provider", crew_state.DEV_PROVIDERS),
    ("qa.order", crew_state.QA_PROVIDERS),
    ("pm.authority", crew_state.AUTHORITIES),
    ("scope.mode", crew_ticket.MODES),
    ("tracker", crew_tracker.KINDS),
    ("autopilot.deploy", crew_autopilot.DEPLOY_VALUES),
    ("autopilot.approval", crew_autopilot.POLICIES),
    ("autopilot.questions", crew_autopilot.POLICIES),
    ("autopilot.ship", crew_autopilot.SHIP_POLICIES),
])
def test_tuple_backed_values_are_the_same_object(key, obj):
    assert crew_keys.values_of(key) is obj


def test_qa_provider_is_auto_then_qa_providers_own_items():
    values = crew_keys.values_of("qa.provider")
    assert values is crew_keys.values_of("qa.provider")
    assert values[0] == "auto"
    tail = values[1:]
    assert len(tail) == len(crew_state.QA_PROVIDERS)
    assert all(a is b for a, b in zip(tail, crew_state.QA_PROVIDERS))


def test_autoclear_methods_are_the_platform_table():
    row = crew_keys.KEY_META["context.autoClear.method"]
    table = crew_platform._AUTOCLEAR_METHODS  # pylint: disable=protected-access
    assert row["values_by_os"] is table
    union = []
    for methods in table.values():
        union += [m for m in methods if m not in union]
    assert crew_keys.values_of("context.autoClear.method") == tuple(union)


def test_values_agree_with_the_writers_enum_values():
    """`crew_config.enum_values` is what both config writers refuse against;
    the reference must print the same list for every key it covers."""
    covered = 0
    for key in crew_keys.KEY_META:
        allowed = crew_config.enum_values(key)
        if allowed is None:
            continue
        covered += 1
        if key in crew_guards.PERSONAL_KEYS:
            # T-0050: a personal key's writer lists its tiers strictest first
            # (rank order, `crew_guards.PERSONAL_KEYS`), while the reference
            # prints the reader's own tuple (`crew_autopilot.POLICIES`, ...).
            # Same values, so neither side refuses what the other accepts.
            assert sorted(crew_keys.values_of(key)) == sorted(allowed), key
            assert allowed == crew_guards.PERSONAL_KEYS[key][1], key
            continue
        assert tuple(crew_keys.values_of(key)) == allowed, key
    assert covered >= 10


# `branch` rows whose reader checks a shape rather than a closed value list.
_OPEN_BRANCH_ROWS = ("autopilot.maxPhases", "autopilot.maxAutoReplans", "tickets.baseBranch",
                     "git.forbiddenTrailers", "autopilot.sleep.schedule",
                     "autopilot.maxLanes",
                     "autopilot.maxTicketsPerRun", "autopilot.maxTokensPerSession")


def test_every_row_has_a_summary_and_a_values_kind():
    for key, row in crew_keys.KEY_META.items():
        assert row["summary"].strip(), key
        assert row["kind"] in crew_keys.KINDS, key
        if row["kind"] in ("tuple", "prose", "branch") and key not in _OPEN_BRANCH_ROWS:
            assert row["values"], key
        if row["kind"] in ("unvalidated", "prose", "type", "branch", "open-table"):
            assert row["source"], key
    assert not crew_keys.problems()


def test_every_source_is_a_file_in_the_plugin():
    for key, row in crew_keys.KEY_META.items():
        if row["source"]:
            assert os.path.isfile(os.path.join(PLUGIN, row["source"])), (key, row["source"])


def test_machine_arms_keys_render_as_machine_arms():
    assert crew_config.REPO_VETO_ONLY
    for key in crew_config.REPO_VETO_ONLY:
        assert crew_keys.layer_of(key) == "machine-arms", key
    for name in crew_state.AUTOCLEAR_MACHINE_ONLY_KEYS:
        assert crew_keys.layer_of("context.autoClear." + name) == "machine-only"


def test_notify_env_name_keys_render_as_machine_only():
    """T-0051. `crew_notify.effective_config` honours `notify.tokenEnv` and
    `notify.tokenEnv` from the machine file alone; the layer is derived from the
    table it enforces with, never restated here."""
    import crew_notify  # pylint: disable=import-outside-toplevel
    assert set(crew_notify.GLOBAL_ONLY_KEYS) == {"tokenEnv"}
    for name in crew_notify.GLOBAL_ONLY_KEYS:
        assert crew_keys.layer_of("notify." + name) == "machine-only"
    assert crew_keys.layer_of("notify.chatId") == "both"


def test_layer_follows_is_global_path():
    for key in crew_keys.KEY_META:
        layer = crew_keys.layer_of(key)
        assert (layer == "repo") == (not crew_config.is_global_path(key)), key
    assert crew_keys.layer_of("pm.authority") == "both, widening warned"
    assert crew_keys.layer_of("install.policy") == "both, ratchet"
    assert crew_keys.layer_of("qa.provider") == "both"
    # T-0050: the personal keys combine per key, the stricter layer winning.
    for key in crew_guards.PERSONAL_KEYS:
        assert crew_keys.layer_of(key) == "both, stricter wins", key


# --- Step 2: arrival versions, code branches, prose, COMING -------------------

def _version(text):
    return tuple(int(p) for p in text.split("."))


def test_since_is_a_version_no_newer_than_the_plugin():
    with open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
        plugin = _version(json.load(fh)["version"])
    for key, row in crew_keys.KEY_META.items():
        since = row["since"]
        if since is None or since == "<=0.11.0":
            continue
        assert re.fullmatch(r"\d+\.\d+\.\d+", since), (key, since)
        assert _version(since) <= plugin, (key, since)


def _repo(tmp_path, cfg):
    (tmp_path / ".crew").mkdir(exist_ok=True)
    (tmp_path / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return str(tmp_path)


@pytest.mark.parametrize("value", ["off", "plan", "Plan"])
def test_autopilot_mode_values_agree_with_the_reader(tmp_path, value):
    declared = crew_keys.values_of("autopilot.mode")
    got = crew_autopilot.settings(_repo(tmp_path, {"autopilot": {"mode": value}}))
    assert got["armed"] == (value == "plan")
    assert (value in declared) == (not any("autopilot.mode" in w for w in got["warnings"]))


@pytest.mark.parametrize("key", ["approval", "questions"])
@pytest.mark.parametrize("value", [None, "human", "self", "risk", "Self"])
def test_sleep_override_values_agree_with_the_reader(tmp_path, key, value):
    """T-0053: every declared value is read without a warning; one that is
    not declared warns. The tail of the tuple is POLICIES' own items."""
    declared = crew_keys.values_of(f"autopilot.sleep.{key}")
    got = crew_autopilot.settings(_repo(tmp_path, {"autopilot": {"sleep": {key: value}}}))
    assert declared[1:] == crew_autopilot.POLICIES
    assert all(a is b for a, b in zip(declared[1:], crew_autopilot.POLICIES))
    assert (value in declared) == (
        not any(f"autopilot.sleep.{key}" in w for w in got["warnings"]))


@pytest.mark.parametrize("value, kept", [(1, True), (12, True), (0, False), ("12", False)])
def test_autopilot_max_phases_agrees_with_the_reader(tmp_path, value, kept):
    got = crew_autopilot.settings(_repo(tmp_path, {"autopilot": {"maxPhases": value}}))
    assert got["maxPhases"] == (value if kept else 12)
    assert kept == (not any("maxPhases" in w for w in got["warnings"]))
    assert crew_keys.KEY_META["autopilot.maxPhases"]["type"] == "positive integer"


@pytest.mark.parametrize("value", ["pr", "merge", "Merge", "squash", True])
def test_autopilot_ship_values_agree_with_the_reader(tmp_path, value):
    declared = crew_keys.values_of("autopilot.ship")
    got = crew_autopilot.settings(_repo(tmp_path, {"autopilot": {"ship": value}}))
    assert got["ship"] == (value if value in declared else "pr")
    assert (value in declared) == (not any("autopilot.ship" in w for w in got["warnings"]))


@pytest.mark.parametrize("value, kept", [
    (None, True), ("main", True), ("release/2.x", True),
    ("", False), ("   ", False), (7, False), (True, False), (["main"], False),
])
def test_tickets_base_branch_is_checked_not_coerced(tmp_path, value, kept):
    # scope_base.read_base_branch refuses a non-string or blank value, and the
    # scope base becomes "could not tell": nothing is coerced, so the row is
    # kind `branch` ("checked in"), never `type` ("coerced in").
    import scope_base
    got, problem = scope_base.read_base_branch(
        _repo(tmp_path, {"tickets": {"baseBranch": value}}))
    assert (problem is None) == kept, (value, problem)
    if not kept:
        assert got is None
    row = crew_keys.KEY_META["tickets.baseBranch"]
    assert row["kind"] == "branch"
    assert row["type"] == "branch name or null"
    assert row["source"] == "hooks/scripts/scope_base.py"


@pytest.mark.parametrize("value, kept", [
    ([], True), (["Co-Authored-By"], True), (["Signed-off-by", "X-1"], True),
    ("Co-Authored-By", False), (["Co-Authored-By:"], False), ([7], False),
    (None, False), ({"a": 1}, False),
])
def test_git_forbidden_trailers_is_checked_not_coerced(tmp_path, value, kept):
    # crew_trailers.forbidden refuses anything but a list of tokens and the
    # list becomes unknown, never `[]`: nothing is coerced, so the row is kind
    # `branch` ("checked in"), never `type` ("coerced in").
    import crew_trailers
    root = _repo(tmp_path, {"git": {"forbiddenTrailers": value}})
    got, unknown = crew_trailers.forbidden(root, global_path=str(tmp_path / "none.json"))
    assert (unknown is None) == kept, (value, unknown)
    if kept:
        assert got == tuple(value)
    else:
        assert got == ()
    row = crew_keys.KEY_META["git.forbiddenTrailers"]
    assert row["kind"] == "branch"
    assert row["source"] == "hooks/scripts/crew_trailers.py"
    assert crew_keys.layer_of("git.forbiddenTrailers") == "both"


def _machine(tmp_path, cfg):
    path = tmp_path / "machine.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("repo, machine, armed", [
    (True, None, False),     # a repo `true` alone arms nothing
    (None, True, True),      # the machine arms it
    (False, True, False),    # a repo `false` vetoes
    ("true", "true", False),  # an undeclared value (a string) never arms
])
def test_machine_armed_values_agree_with_the_readers(tmp_path, repo, machine, armed):
    for key in ("resume.auto", "context.autoClear.enabled", "context.autoClear.wrapUp"):
        declared = crew_keys.values_of(key)
        assert crew_keys.layer_of(key) == "machine-arms"
        block, leaf = key.rsplit(".", 1)

        def nest(value, block=block, leaf=leaf):
            out = {leaf: value}
            for part in reversed(block.split(".")):
                out = {part: out}
            return out
        root = _repo(tmp_path, nest(repo) if repo is not None else {})
        gpath = _machine(tmp_path, nest(machine) if machine is not None else {})
        if key == "resume.auto":
            got = crew_resume.settings(root, global_path=gpath)["armed"]
        else:
            got = crew_autocycle.settings(root, global_path=gpath)[leaf]
        assert got is armed, (key, repo, machine)
        if armed:
            assert machine in declared


@pytest.mark.parametrize("value", [True, False, "true", 1])
def test_route_enabled_values_agree_with_the_reader(tmp_path, value):
    got = crew_route.settings(_repo(tmp_path, {"route": {"enabled": value}}))
    declared = crew_keys.values_of("route.enabled")
    assert got["enabled"] is (value is True)
    assert any(value is d for d in declared) == (value in (True, False) and
                                                 isinstance(value, bool))


@pytest.mark.parametrize("value", [True, False, "true", 1])
def test_allow_cli_approval_values_agree_with_the_reader(tmp_path, value):
    root = _repo(tmp_path, {"scope": {"allowCliApproval": value}})
    assert crew_ticket.cli_approval_allowed(root) is (value is True)


def test_prose_values_appear_in_their_source():
    rows = [(k, r) for k, r in crew_keys.KEY_META.items() if r["kind"] == "prose"]
    assert rows
    for key, row in rows:
        with open(os.path.join(PLUGIN, row["source"]), encoding="utf-8") as fh:
            text = fh.read()
        for value in row["values"]:
            assert f"`{value}`" in text, (key, value, row["source"])


def test_no_coming_key_is_in_code():
    landed = crew_keys.coming_in_code()
    assert not landed, "; ".join(
        f"{key} ({ticket}) is in the code now: move this row to KEY_META and set since"
        for key, ticket in landed)


def test_coming_in_code_names_a_landed_key(monkeypatch):
    coming = crew_keys.COMING + (dict(crew_keys.COMING[0], key="pm.maxDispatches",
                                      ticket="T-9999"),)
    monkeypatch.setattr(crew_keys, "COMING", coming)
    assert ("pm.maxDispatches", "T-9999") in crew_keys.coming_in_code()


def test_coming_rows_name_a_ticket():
    assert crew_keys.COMING
    for row in crew_keys.COMING:
        assert re.fullmatch(r"T-\d{4}", row["ticket"]), row
        assert row["summary"] and row["default"] and row["layer"], row


def test_coming_changes_name_an_existing_key():
    for row in crew_keys.COMING:
        assert row["change"] == "new key" or row["change"].startswith("changes "), row
        if row["change"] != "new key":
            assert row["key"] in crew_keys.KEY_META, row


# --- L-0725: families, the new guard rows, the committed key set ----------------

def test_every_row_has_a_family():
    for key, row in crew_keys.KEY_META.items():
        assert row["family"] in crew_keys.FAMILIES, key


def test_families_tuple_is_the_declared_ten():
    assert crew_keys.FAMILIES == ("core", "providers", "guards", "cloud", "trackers",
                                  "autopilot", "context", "notify", "memory",
                                  "platform")


def test_guards_profile_row_references_the_tuple():
    row = crew_keys.KEY_META["guards.profile"]

    assert row["values"] is crew_guards.GUARD_PROFILES
    assert crew_keys.values_of("guards.profile") is crew_guards.GUARD_PROFILES


def test_guards_overrides_row_is_an_open_table():
    assert crew_keys.KEY_META["guards.overrides"]["kind"] == "open-table"


def test_no_legacy_guard_row_remains():
    legacy = [k for k in crew_keys.KEY_META
              if k.startswith("guards.") and k.split(".", 1)[1] in crew_guards.ALL_GUARD_NAMES]

    assert legacy == []


def test_key_set_is_the_l0725_set():
    repo = set(crew_config.leaf_paths(crew_config.default_config()))
    machine = set(crew_config.leaf_paths(crew_config.default_global_config()))

    assert repo | machine == l0725_keyset.L0725_KEYS
    assert repo == l0725_keyset.L0725_REPO_KEYS
    assert machine == l0725_keyset.L0725_MACHINE_KEYS
    assert (len(l0725_keyset.L0725_KEYS), len(repo), len(machine)) == (87, 83, 50)


def test_no_dropped_key_is_a_leaf():
    leaves = _leaves()

    assert not (leaves & l0725_keyset.L0725_DROPPED)


# --- L-0725: a dropped key has no reader ------------------------------------------

_SCAN_ROOTS = (("hooks", "scripts"), ("skills",))
_SCAN_SUFFIXES = (".py", ".sh", ".ps1")
# Files that legitimately NAME a dropped key: the registry, and the module that
# tells a person the key is dropped.
_NAMES_DROPPED_KEYS = {"crew_dropped.py"}

# Reviewed hits that are not readers. (path relative to plugin/crew, stripped
# line) -> why. Empty is the goal; each entry is a sentence, not a shrug.
_NOT_A_READER = {
    ('hooks/scripts/crew_config.py',
     'table = block.get("roles")'):
        'a qa/dev role-pin table (kept) or the 0.20 legacy file read by status and migrate, not the retired top-level key',
    ('hooks/scripts/crew_config.py',
     'pinned = crew_state.dict_or_empty(block.get("roles"))'):
        'a qa/dev role-pin table (kept) or the 0.20 legacy file read by status and migrate, not the retired top-level key',
    ('hooks/scripts/crew_coord.py',
     'value = coord.get("ttlMinutes", DEFAULT_TTL_MINUTES) if isinstance(coord, dict) else DEFAULT_TTL_MINUTES'):
        "the incident's own state field and the coordination claim's key; the config value is the constant",
    ('hooks/scripts/crew_incident.py',
     '"ttlMinutes": ttl,'):
        "the incident's own state field and the coordination claim's key; the config value is the constant",
    ('hooks/scripts/crew_incident.py',
     'ttl = _int_or(ttl_minutes, emergency["ttlMinutes"])'):
        "the incident's own state field and the coordination claim's key; the config value is the constant",
    ('hooks/scripts/crew_incident.py',
     'state["ttlMinutes"] = ttl'):
        "the incident's own state field and the coordination claim's key; the config value is the constant",
    ('hooks/scripts/crew_migrate.py',
     'roles = legacy.get("roles")'):
        'a qa/dev role-pin table (kept) or the 0.20 legacy file read by status and migrate, not the retired top-level key',
    ('hooks/scripts/crew_notify.py',
     '_say("notify.provider teams has no webhook to post to since L-0725 (notify.urlEnv is "'):
        'records that the key was removed (message or docstring)',
    ('hooks/scripts/crew_notify_hold.py',
     'L-0725: nothing holds a ping any more. `autopilot.sleep.notifyHold` is gone'):
        'records that the key was removed (message or docstring)',
    ('hooks/scripts/crew_state.py',
     'STALE_HANDOFF_DEFAULTS = {"maxAgeHours": 72, "maxCommitsBehind": 3}'):
        "the constant's own definition",
    ('hooks/scripts/crew_state.py',
     'STALE_HANDOFF_MAX_AGE_HOURS = STALE_HANDOFF_DEFAULTS["maxAgeHours"]'):
        "the constant's own definition",
    ('hooks/scripts/crew_state.py',
     'STALE_HANDOFF_MAX_COMMITS_BEHIND = STALE_HANDOFF_DEFAULTS["maxCommitsBehind"]'):
        "the constant's own definition",
    ('hooks/scripts/crew_state.py',
     'OBSIDIAN_COLUMNS = {"backlog": "Backlog", "ready": "Ready", "inProgress": "In Progress",'):
        "the constant's own definition",
    ('hooks/scripts/crew_state.py',
     'pin = dict_or_empty(dict_or_empty(block.get("roles")).get(role))'):
        'a qa/dev role-pin table (kept) or the 0.20 legacy file read by status and migrate, not the retired top-level key',
    ('hooks/scripts/crew_state.py',
     'L-0725: this was `worktree.root`; it is fixed at `WORKTREE_ROOT` (None),'):
        'records that the key was removed (message or docstring)',
    ('hooks/scripts/crew_status.py',
     'roles = legacy.get("roles", [])'):
        'a qa/dev role-pin table (kept) or the 0.20 legacy file read by status and migrate, not the retired top-level key',
    ('hooks/scripts/crew_tracker.py',
     'done = board["columns"]["done"]'):
        "the tracker's own board dictionary built from the constant",
    ('hooks/scripts/crew_tracker.py',
     '"in-progress": "inProgress",'):
        "the tracker's own board dictionary built from the constant",
    ('hooks/scripts/crew_wave.py',
     'crew_state.dict_or_empty(cfg.get("dev")).get("roles")).get(role))'):
        'a qa/dev role-pin table (kept) or the 0.20 legacy file read by status and migrate, not the retired top-level key',
}


def _scan_files():
    out = []
    for parts in _SCAN_ROOTS:
        base = os.path.join(PLUGIN, *parts)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in ("_test", "__pycache__", "node_modules")]
            if os.path.basename(dirpath) == "tests":
                continue
            for name in filenames:
                if name.endswith(_SCAN_SUFFIXES) and name not in _NAMES_DROPPED_KEYS:
                    out.append(os.path.join(dirpath, name))
    return sorted(out)


def _triples():
    """(key, leaf, block) for each dropped key; block is the key's parent
    segment, or None for a top-level key."""
    out = []
    for key in sorted(l0725_keyset.L0725_DROPPED):
        parts = key.split(".")
        out.append((key, parts[-1], parts[-2] if len(parts) > 1 else None))
    return out


def _kept_leaves():
    return {k.split(".")[-1] for k in l0725_keyset.L0725_KEYS}


def _hits():
    """Every line that reads a dropped key, by the three searches: the dotted
    name; the block accessor (`"block"` ... `get("leaf")` / `["leaf"]` on one
    line); and the quoted leaf when it is a camelCase name no KEPT key shares (a
    plain word like `mode`, `command` or `done` is everywhere, so only the first
    two searches can tell a reader from a coincidence for it)."""
    kept = _kept_leaves()
    found = []
    for path in _scan_files():
        rel = os.path.relpath(path, PLUGIN).replace(os.sep, "/")
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().split("\n")
        for key, leaf, block in _triples():
            dotted = re.compile(
                r"(?<![\w.])" + re.escape(key) + r"(?![\w])" if block else
                r"""(?:get\(\s*|\[\s*)["']""" + re.escape(key) + r"""["']""")
            access = re.compile(
                r"""["']""" + re.escape(block) + r"""["'][^\n]{0,60}?(?:get\(\s*|\[\s*)["']"""
                + re.escape(leaf) + r"""["']""") if block else None
            quoted = re.compile(r"""["']""" + re.escape(leaf) + r"""["']""") \
                if leaf not in kept and re.search(r"[a-z][A-Z]", leaf) else None
            for number, line in enumerate(lines, 1):
                text = line.strip()
                if text.startswith(("#", "//")):
                    continue
                for search, pattern in (("dotted", dotted), ("block", access), ("leaf", quoted)):
                    if pattern is not None and pattern.search(line):
                        if (rel, text) not in _NOT_A_READER:
                            found.append(f"{rel}:{number}: [{key}] ({search}) {text[:100]}")
                        break
    return found


def test_no_dropped_key_is_read():
    hits = _hits()

    assert hits == [], "a dropped key still has a reader:\n" + "\n".join(hits[:60])


def test_every_not_a_reader_entry_still_matches_a_line():
    live = set()
    for path in _scan_files():
        rel = os.path.relpath(path, PLUGIN).replace(os.sep, "/")
        with open(path, encoding="utf-8", errors="replace") as handle:
            live.update((rel, line.strip()) for line in handle.read().split("\n"))

    assert set(_NOT_A_READER) <= live


def test_dropped_registry_equals_the_committed_list():
    import crew_dropped  # pylint: disable=import-outside-toplevel
    assert set(crew_dropped.DROPPED) == set(l0725_keyset.L0725_DROPPED)
    assert len(crew_dropped.DROPPED) == 60


def test_every_dropped_constant_exists_and_holds_the_old_default():
    import crew_dropped  # pylint: disable=import-outside-toplevel
    for key, (default, where) in crew_dropped.DROPPED.items():
        if where.startswith("retired"):
            continue
        module, name = where.split(".")
        value = getattr(crew_state, name)
        if key.startswith("obsidian.columns."):
            value = value[key.rsplit(".", 1)[1]]
        if key == "shellRoute.mode":
            default = crew_dropped.GLOBAL_DEFAULTS[key]
        assert module == "crew_state", key
        assert tuple(value) == tuple(default) if isinstance(default, list) else value == default, key


_CITATION = re.compile(r"CONFIG\.md[^§\n]{0,3}§ ?[0-9]+")
# Recorded history and the harness files the follow-up tooling PR owns.
_CITATION_EXEMPT_PREFIXES = (
    ".work/", "CHANGELOG.md", "docs/tickets/", "plugin/crew/tests/golden/", "cloud-handoff-notes.md",
    "pending-tickets.md", "docs/review/", "docs/handoff/", "plugin/crew/tests/sabotage",
    "plugin/crew/commands/review.md", "plugin/crew/agents/reviewer.md", "graphify-out/",
)


def test_no_section_citations():
    import subprocess  # pylint: disable=import-outside-toplevel
    repo = os.path.dirname(os.path.dirname(PLUGIN))
    listed = subprocess.run(["git", "grep", "-lE", r"CONFIG\.md[^§]{0,3}§ ?[0-9]+"], cwd=repo,
                            capture_output=True, text=True, check=False)
    if listed.returncode not in (0, 1):
        pytest.skip("git grep unavailable here")
    offenders = [p for p in listed.stdout.split() if not p.startswith(_CITATION_EXEMPT_PREFIXES)]

    assert offenders == [], "CONFIG.md section citations remain in:\n" + "\n".join(offenders)
