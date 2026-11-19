"""R-C2: the copy-safe config blanks in `plugin/crew/docs/configuration/`.

`docs/guides/crew/src/config_reference.py --write` writes four files there:
`config.blank.json` (the repo layer), `global.blank.json` (the machine layer),
`keys.json` (the per-key facts) and `template.annotated.md`. This suite holds
them to the plan's four acceptance criteria:

1. each blank's keys plus its named exclusions are exactly that layer's
   registry keys;
2. each exclusion is named with a reason (`crew_keys.BLANK_EXCLUDED`);
3. applying a blank to an EMPTY layer leaves the effective policy unchanged,
   probed with one made-up value per key in the other layer
   (`MACHINE_FIXTURES`, `REPO_FIXTURES`);
4. the committed files are what the generator renders (a one-byte edit fails
   `--check`; `scripts/_test/config-reference.py` has the must-block rows).

"Effective policy" is the union of what every reader of the two files returns
(`policy()`): `explain_config` both ways, `resolve_guard` per guard,
`resolve_personal` per personal key, and the two readers that open the files
themselves, `crew_humanonly.resolve` and `crew_autocycle.settings`. A reader
added later that opens a config file directly is NOT caught by this list; it
must be added here (docs/crew/config-rationale.md).

Isolation: HOME and USERPROFILE point at a temp directory, every reader gets an
explicit path, receipts go to a store under `tmp_path`, and a guard fails the
test if anything opens the real `~/.claude/crew/` (config or `confirm-config`).
"""
import builtins
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autocycle
import crew_config
import crew_humanonly
import crew_keys
import crew_state

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(PLUGIN))
CONF_DIR = os.path.join(PLUGIN, "docs", "configuration")
CREW_CONFIG_PY = os.path.join(PLUGIN, "hooks", "scripts", "crew_config.py")
# Read before any fixture patches HOME: the directory no test may open.
REAL_CREW_DIR = os.path.normcase(os.path.realpath(os.path.join(
    os.path.expanduser("~"), ".claude", "crew")))


def _load_config_reference():
    path = os.path.join(REPO, "docs", "guides", "crew", "src", "config_reference.py")
    spec = importlib.util.spec_from_file_location("config_reference_r_c2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REF = _load_config_reference()
FILES = {
    "config.blank.json": REF.render_repo_blank,
    "global.blank.json": REF.render_global_blank,
    "keys.json": REF.render_keys_json,
    "template.annotated.md": REF.render_annotated,
}
BLANK_FILE = {"repo": "config.blank.json", "machine": "global.blank.json"}


def committed(name):
    """A committed file's text through the generator's own reader, which folds
    CRLF, so an autocrlf checkout compares equal."""
    return REF._read(os.path.join(CONF_DIR, name))  # pylint: disable=protected-access


def committed_blank(layer):
    return json.loads(committed(BLANK_FILE[layer]))


SCHEMA = crew_config.default_config()["schema"]

# --- the probe's fixtures (D12) --------------------------------------------------
#
# One made-up value per key, written out by hand so a reviewer reads the exact
# value each key is probed with: a declared value where the registry declares
# any, else a value of the default's type, else of the type the `type` text
# names. `humanOnly.*` is `false` in both tables: `true` resolves to the same
# human-only as the default, so only a (receipt-backed) `false` reaches
# `crew_humanonly.resolve`. A new registry key fails `test_fixture_coverage`,
# by name, until it has a row here or in FIXTURE_SKIPPED.

MACHINE_FIXTURES = {
    "qa.provider": "claude",
    "qa.order": ["claude", "codex"],
    "qa.fallback": "claude-sonnet-5-zz",
    "qa.codex.model": "gpt-6.2-sol-zz",
    "qa.codex.reasoningEffort": "high",
    "qa.copilot.model": "zz-copilot",
    "qa.kimi.model": "zz-kimi",
    "qa.roles": {"review": {"provider": "claude"}},
    "dev.provider": "codex",
    "dev.fallback": "claude-sonnet-5-zz",
    "dev.codex.model": "zz-codex",
    "dev.codex.reasoningEffort": "low",
    "dev.copilot.model": "zz-copilot",
    "dev.kimi.model": "zz-kimi",
    "dev.roles": {"developer": {"provider": "codex"}},
    "secondOpinion.provider": "codex",
    "secondOpinion.mode": "zz-mode",
    "secondOpinion.model": "zz-second",
    "memory.mode": "vault",
    "memory.vaultPath": "/zz/vault",
    "context.autoClear.enabled": True,
    "context.autoClear.method": "none",
    "context.autoClear.delaySeconds": 10,
    "context.autoClear.minHandoffLines": 12,
    "context.autoClear.onlyRepos": ["/zz/repo"],
    "context.autoClear.onlySessions": ["zz-session"],
    "context.autoClear.wrapUp": True,
    "resume.auto": True,
    "humanOnly.approve": False,
    "humanOnly.promoteMarker": False,
    "worktrees.root": "/zz/worktrees",
    "promote.deadlineSeconds": 9,
    "reaper.enabled": True,
    "reaper.dryRun": False,
    "reaper.spinCpuPct": 57,
    "reaper.spinMinAgeMin": 22,
    "reaper.blockedMinAgeHours": 9,
    "reaper.protectedRegex": "zz-protected",
    "reaper.intervalMin": 17,
    "reaper.onSessionStart": True,
    "notify.provider": "telegram",
    "notify.tokenEnv": "ZZ_TOKEN",
    "notify.chatId": "12345",
    "notify.events": ["deploy"],
    "pm.authority": "act",
    "pm.maxDispatches": 10,
    "install.policy": "ask",
    "guards.profile": "standard",
    "guards.overrides": {"forcePush": "ask"},
    "guards.git.allow": "all",
    "environments.prodUnattended": True,
    "change.requireForProduction": True,
    "git.forbiddenTrailers": ["Zz-Trailer"],
    "autopilot.mode": "plan",
    "autopilot.maxPhases": 19,
    "autopilot.deploy": "nonprod",
    "autopilot.approval": "human",
    "autopilot.questions": "human",
    "route.enabled": True,
    "unattendedCloud.aws.readOnly.profile": "zz-readonly",
    "unattendedCloud.aws.readOnly.identity": "arn:aws:sts::123456789012:assumed-role/zz/",
    "unattendedCloud.aws.readOnly.region": "eu-west-1",
    "unattendedCloud.aws.nonProd": {"dev": {"profile": "zz-dev",
                                            "identity": "arn:aws:sts::123456789012:"
                                                        "assumed-role/zz-dev/"}},
}

REPO_FIXTURES = {
    "qa.provider": "claude",
    "qa.order": ["claude", "codex"],
    "qa.fallback": "claude-sonnet-5-zz",
    "qa.codex.model": "gpt-6.2-sol-zz",
    "qa.codex.reasoningEffort": "high",
    "qa.copilot.model": "zz-copilot",
    "qa.kimi.model": "zz-kimi",
    "qa.roles": {"review": {"provider": "claude"}},
    "dev.provider": "codex",
    "dev.fallback": "claude-sonnet-5-zz",
    "dev.codex.model": "zz-codex",
    "dev.codex.reasoningEffort": "low",
    "dev.copilot.model": "zz-copilot",
    "dev.kimi.model": "zz-kimi",
    "dev.roles": {"developer": {"provider": "codex"}},
    "secondOpinion.provider": "codex",
    "secondOpinion.mode": "zz-mode",
    "secondOpinion.model": "zz-second",
    "tracker": "obsidian",
    "jira.project": "ZZ",
    "jira.cloudId": "zz-cloud",
    "obsidian.vaultPath": "/zz/vault",
    "obsidian.boardDir": "zz-board",
    "memory.mode": "vault",
    "memory.vaultPath": "/zz/vault",
    "verifyGate": False,
    "context.enabled": False,
    "context.warnAt": 0.5,
    "context.reserveTokens": 7,
    "context.autoClear.enabled": True,
    "context.autoClear.method": "none",
    "context.autoClear.delaySeconds": 10,
    "context.autoClear.minHandoffLines": 12,
    "context.autoClear.wrapUp": True,
    "resume.auto": True,
    "humanOnly.approve": False,
    "humanOnly.promoteMarker": False,
    "worktrees.root": "/zz/worktrees",
    "promote.deadlineSeconds": 9,
    "verify.stopBudgetSeconds": 67,
    "reaper.enabled": True,
    "reaper.dryRun": False,
    "reaper.spinCpuPct": 57,
    "reaper.spinMinAgeMin": 22,
    "reaper.blockedMinAgeHours": 9,
    "reaper.protectedRegex": "zz-protected",
    "reaper.intervalMin": 17,
    "reaper.onSessionStart": True,
    "emergency.standDown": False,
    "emergency.maxTtlMinutes": 487,
    "notify.provider": "telegram",
    "notify.chatId": "12345",
    "notify.events": ["deploy"],
    "platform.os": "zz-os",
    "platform.wsl": True,
    "platform.shell": "zz-shell",
    "platform.windowsHostIp": "10.0.0.9",
    "pm.authority": "act",
    "pm.maxDispatches": 10,
    "graph.out": "graphify-out-zz",
    "install.policy": "ask",
    "guards.profile": "standard",
    "guards.overrides": {"forcePush": "ask"},
    "guards.git.allow": "all",
    "production.databases": ["zz-db-*"],
    "production.hosts": ["zz-host-*"],
    "cloud.awsProfiles": ["zz-profile"],
    "cloud.awsRegions": ["eu-west-1"],
    "cloud.azureSubscriptions": ["zz-sub"],
    "environments.nonProd": ["zz-dev-*"],
    "environments.prodUnattended": True,
    "environments.workflows": {".github/workflows/zz-*.yml": "staging"},
    "environments.preProduction": {"zz-launch": {"reason": "not live yet"}},
    "change.requireForProduction": True,
    "git.forbiddenTrailers": ["Zz-Trailer"],
    "scope.mode": "report",
    "scope.allowCliApproval": True,
    "autopilot.mode": "plan",
    "autopilot.maxPhases": 19,
    "autopilot.deploy": "nonprod",
    "autopilot.approval": "human",
    "autopilot.questions": "human",
    "autopilot.maxAutoReplans": 2,
    "autopilot.ship": "pr",
    "autopilot.sleep.schedule": "23:00-06:00",
    "autopilot.sleep.approval": "human",
    "autopilot.sleep.questions": "human",
    "autopilot.sleep.deploy": "nonprod",
    "autopilot.maxTicketsPerRun": 10,
    "autopilot.maxTokensPerSession": 2000007,
    "autopilot.maxLanes": 2,
    "autopilot.reviewPolicy": "clean-only",
    "tickets.baseBranch": "develop",
    "route.enabled": True,
}

FIXTURES = {"machine": MACHINE_FIXTURES, "repo": REPO_FIXTURES}

FIXTURE_SKIPPED = {
    "repo": {"schema": "the file-format stamp: every repo fixture file carries the real "
                       "one, and policy() leaves it out of the comparison"},
    "machine": {},
}

INERT_ALONE = {
    "install.policy": "a ratchet key: a loose value in one layer alone resolves to the "
                      "strict default, so it shows only when both layers say it",
    "environments.prodUnattended": "a ratchet key: `true` takes effect only when both "
                                   "layers say so",
}

# The two readers that open the config files themselves, by their policy() tag.
DIRECT_READERS = {"humanonly": "crew_humanonly.resolve", "autocycle": "crew_autocycle.settings"}


# --- isolation -------------------------------------------------------------------

def _under_real_crew(path):
    try:
        text = os.fspath(path)
    except TypeError:
        return False
    if isinstance(text, bytes) or not text:
        return False
    full = os.path.normcase(os.path.realpath(os.path.abspath(text)))
    return full == REAL_CREW_DIR or full.startswith(REAL_CREW_DIR + os.sep)


@pytest.fixture(scope="module")
def _isolated(tmp_path_factory):
    """HOME and USERPROFILE at a temp directory, and a record of every open or
    listing under the real `~/.claude/crew/`, which the test then fails on."""
    home = tmp_path_factory.mktemp("home")
    touched = []
    real_open, real_listdir = builtins.open, os.listdir

    def guarded_open(file, *args, **kwargs):
        if _under_real_crew(file):
            touched.append(str(file))
        return real_open(file, *args, **kwargs)

    def guarded_listdir(path="."):
        if _under_real_crew(path):
            touched.append(str(path))
        return real_listdir(path)

    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("HOME", str(home))
        patch.setenv("USERPROFILE", str(home))
        patch.setattr(builtins, "open", guarded_open)
        patch.setattr(io, "open", guarded_open)
        patch.setattr(os, "listdir", guarded_listdir)
        yield touched


@pytest.fixture(autouse=True)
def _no_real_crew_dir(_isolated):
    before = len(_isolated)
    yield
    assert _isolated[before:] == [], f"opened the real crew directory: {_isolated[before:]}"


# --- the effective policy (D5) ---------------------------------------------------

def nest(dotted, value):
    out = value
    for part in reversed(dotted.split(".")):
        out = {part: out}
    return out


def merged(table, keys=None):
    """One config holding every `table` value (or those of `keys`)."""
    out = {}
    for key, value in table.items():
        if keys is not None and key not in keys:
            continue
        parts = key.split(".")
        node = out
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return out


def repo_file(cfg=None):
    """A repo fixture file: always the real schema stamp, plus `cfg`."""
    out = {"schema": SCHEMA}
    out.update(cfg or {})
    return out


def seed_receipts(store, layer, path, cfg):
    """One applied double-confirmation record per `humanOnly` key that this
    layer's file sets to exactly `false`, written with crew_humanonly's own
    writer, so `resolve` honours the opt-out as on a real opted-out machine."""
    block = cfg.get("humanOnly") if isinstance(cfg, dict) else None
    if not isinstance(block, dict):
        return
    for index, key in enumerate(crew_humanonly.KEYS):
        if block.get(key) is False:
            crew_humanonly.write_record(store, {
                "change_id": f"cc-{index + (0 if layer == 'machine' else 16):08x}",
                "layer": layer, "target": crew_humanonly.target_key(path),
                "key": f"humanOnly.{key}", "value": False,
                "state": crew_humanonly.APPLIED, "created": 1.0, "settled": 2.0,
                "confirmations": []})


class Probe:  # pylint: disable=too-few-public-methods
    """`policy(repo_cfg, machine_cfg)` in fresh directories under one base."""

    def __init__(self, base):
        self.base = str(base)
        self.count = 0

    def policy(self, repo_cfg, machine_cfg):
        """`{(reader, ...): value}`; a `None` layer writes no file."""
        self.count += 1
        here = os.path.join(self.base, f"p{self.count}")
        root = os.path.join(here, "repo")
        os.makedirs(os.path.join(root, ".crew"))
        gpath = os.path.join(here, "machine", "config.json")
        os.makedirs(os.path.dirname(gpath))
        rpath = os.path.join(root, ".crew", "config.json")
        store = os.path.join(here, "store")
        for cfg, path in ((repo_cfg, rpath), (machine_cfg, gpath)):
            if cfg is not None:
                text = json.dumps(cfg)
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(text)
        if machine_cfg is not None:
            seed_receipts(store, "machine", gpath, machine_cfg)
        if repo_cfg is not None:
            seed_receipts(store, "repo", rpath, repo_cfg)
        out = {}
        for all_keys in (True, False):
            for row in crew_config.explain_config(root, gpath, all_keys=all_keys):
                if row["path"] != "schema":  # the format stamp, not a policy value
                    out[("explain", all_keys, row["path"])] = json.dumps(row["value"],
                                                                         sort_keys=True)
        for name in crew_state.ALL_GUARD_NAMES:
            # `effective` only: the rest of the result is diagnostic (which layer
            # said what), and a blank may change that without changing policy.
            out[("guard", name)] = json.dumps(
                crew_config.resolve_guard(root, name, gpath)["effective"],
                sort_keys=True, default=str)
        for dotted in crew_config.PERSONAL_PATHS:
            out[("personal", dotted)] = json.dumps(
                crew_config.resolve_personal(root, dotted, gpath)["effective"], default=str)
        for key in crew_humanonly.KEYS:
            out[("humanonly", key)] = crew_humanonly.resolve(
                root, key, global_path=gpath, store=store,
                tracker=lambda _path: crew_humanonly.UNTRACKED)["humanOnly"]
        found = crew_autocycle.settings(root, global_path=gpath)
        found.pop("_warnings")
        for key, value in found.items():
            out[("autocycle", key)] = json.dumps(value, default=str)
        return out


def diff(one, two):
    return sorted((k for k in set(one) | set(two) if one.get(k) != two.get(k)), key=repr)


@pytest.fixture
def probe(tmp_path):
    return Probe(tmp_path)


@pytest.fixture(scope="module")
def effects(tmp_path_factory, _isolated):
    """`{table: {key: entries changed}}`: each single-key fixture against the
    empty layer, the other layer empty. Computed once for the validity and
    direct-reader tests. Its reader calls run before any test's
    `_no_real_crew_dir` takes its start index, so it asserts isolation itself."""
    before = len(_isolated)
    probe = Probe(tmp_path_factory.mktemp("effects"))
    base_machine = probe.policy(None, None)
    base_repo = probe.policy(repo_file(), None)
    out = {"machine": {}, "repo": {}}
    for key, value in MACHINE_FIXTURES.items():
        out["machine"][key] = diff(base_machine, probe.policy(None, nest(key, value)))
    for key, value in REPO_FIXTURES.items():
        out["repo"][key] = diff(base_repo, probe.policy(repo_file(nest(key, value)), None))
    assert _isolated[before:] == [], f"opened the real crew directory: {_isolated[before:]}"
    return out


# --- acceptance 1 and 2: keys per layer, exclusions named --------------------------

@pytest.mark.parametrize("layer", ["repo", "machine"])
def test_blank_keys_plus_exclusions_are_the_layer(layer):
    blank = crew_config.leaf_paths(committed_blank(layer))
    excluded = set(crew_keys.BLANK_EXCLUDED[layer])
    assert not set(blank) & excluded
    assert len(blank) == len(set(blank))
    assert sorted(set(blank) | excluded) == sorted(crew_keys.layer_keys(layer))


def test_layer_key_counts():
    """The sets D1 names: a repo key is any leaf not machine-only, a machine key
    any leaf the machine file may set that is not repo-only."""
    leaves = crew_keys.all_leaves()
    assert crew_keys.repo_layer_keys() == [k for k in leaves
                                           if crew_keys.layer_of(k) != "machine-only"]
    assert crew_keys.machine_layer_keys() == [
        k for k in leaves
        if crew_config.is_global_path(k) and crew_keys.layer_of(k) != "repo"]


def test_machine_blank_is_the_global_template_in_content():  # D3
    assert committed_blank("machine") == crew_config.global_template_config()


def test_repo_blank_holds_the_schema_stamp():  # D5: a file without it reads unmigrated
    assert committed_blank("repo")["schema"] == SCHEMA


@pytest.mark.parametrize("layer", ["repo", "machine"])
def test_every_exclusion_is_named_with_a_reason(layer):
    keys = {row["key"]: row for row in json.loads(committed("keys.json"))["keys"]}
    for key, reason in crew_keys.BLANK_EXCLUDED[layer].items():
        assert isinstance(reason, str) and reason.strip(), key
        assert keys[key]["blank"][layer] == "excluded: " + reason, key


def test_annotated_template_lists_every_exclusion():
    text = committed("template.annotated.md")
    for layer, flag in (("repo", "--repo"), ("machine", "--global")):
        for key in crew_keys.BLANK_EXCLUDED[layer]:
            assert f"`crew_config.py --set {key}=JSON --apply {flag}`" in text, key


# --- acceptance 4: the committed files are the renderer's output -------------------

@pytest.mark.parametrize("name", sorted(FILES))
def test_committed_file_equals_the_renderer(name):
    assert committed(name) == FILES[name](), (
        f"{name} is stale: python3 docs/guides/crew/src/config_reference.py --write")


@pytest.mark.parametrize("name", ["config.blank.json", "global.blank.json", "keys.json"])
def test_json_files_parse(name):
    json.loads(committed(name))


# --- the fixture tables (D12) ----------------------------------------------------

@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_fixture_coverage(layer):
    fixtures, skipped = set(FIXTURES[layer]), set(FIXTURE_SKIPPED[layer])
    keys = set(crew_keys.layer_keys(layer))
    assert not fixtures & skipped, sorted(fixtures & skipped)
    assert sorted(keys - fixtures - skipped) == [], (
        f"{layer} keys with no fixture and no named skip")
    assert sorted((fixtures | skipped) - keys) == [], f"{layer} fixtures outside the layer"


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_fixture_values_are_valid(layer):
    bad = []
    for key, value in FIXTURES[layer].items():
        found, default = crew_keys.layer_default(layer, key)
        if found and value == default:
            bad.append(f"{key}: equals the {layer} default {default!r}")
        declared = crew_keys.values_of(key)
        if declared:
            items = value if crew_keys.KEY_META[key]["type"] == "list of" else [value]
            if not isinstance(items, list) or any(v not in declared for v in items):
                bad.append(f"{key}: {value!r} is not one of the declared {declared!r}")
        if json.loads(json.dumps(value)) != value:
            bad.append(f"{key}: does not round-trip through JSON")
    assert bad == []


def _table_key_params():
    return ([("machine", k) for k in MACHINE_FIXTURES]
            + [("repo", k) for k in REPO_FIXTURES])


def test_inert_alone_names_are_live():
    """A stale INERT_ALONE name would otherwise go unnoticed once its key left
    both fixture tables: the effect test only visits keys the tables hold."""
    registry = set(crew_keys.layer_keys("machine")) | set(crew_keys.layer_keys("repo"))
    fixtures = set(MACHINE_FIXTURES) | set(REPO_FIXTURES)
    assert sorted(set(INERT_ALONE) - registry) == [], "INERT_ALONE names outside the registry"
    assert sorted(set(INERT_ALONE) - fixtures) == [], "INERT_ALONE names with no fixture row"


@pytest.mark.parametrize("layer,key", _table_key_params())
def test_fixture_has_an_effect(layer, key, effects, probe):
    """A fixture the readers ignore would make its probe case pass emptily."""
    alone = effects[layer][key]
    if key not in INERT_ALONE:
        assert alone, f"{layer} fixture {key} changes no policy entry on its own"
        return
    assert not alone, f"{key} shows alone ({alone}): drop it from INERT_ALONE"
    value = FIXTURES[layer][key]
    both = probe.policy(repo_file(nest(key, value)), nest(key, value))
    assert diff(probe.policy(repo_file(), None), both), (
        f"{key} set in both layers still changes nothing")


@pytest.mark.parametrize("layer", ["machine", "repo"])
@pytest.mark.parametrize("reader", sorted(DIRECT_READERS))
def test_each_direct_reader_is_reached(layer, reader, effects):
    """At least one single-key fixture changes an entry that comes from the
    reader itself, not only an explain_config entry."""
    reached = [key for key, entries in effects[layer].items()
               if any(entry[0] == reader for entry in entries)]
    assert reached, f"no {layer} fixture reaches {DIRECT_READERS[reader]}"


# --- the seeded opt-out really resolves False ----------------------------------------

def _approve(policy):
    return policy[("humanonly", "approve")]


def test_seeded_machine_opt_out_resolves_false(probe):
    machine = {"humanOnly": {"approve": False}}
    assert _approve(probe.policy(None, None)) is True
    assert _approve(probe.policy(None, machine)) is False
    assert _approve(probe.policy(committed_blank("repo"), machine)) is False


def test_seeded_repo_opt_out_resolves_false(probe):
    repo = repo_file({"humanOnly": {"approve": False}})
    assert _approve(probe.policy(repo_file(), None)) is True
    assert _approve(probe.policy(repo, None)) is False
    assert _approve(probe.policy(repo, committed_blank("machine"))) is False


# --- acceptance 3: a blank in an empty layer changes nothing -------------------------

def test_repo_blank_with_machine_layer_empty(probe):
    assert diff(probe.policy(None, None), probe.policy(committed_blank("repo"), None)) == []


@pytest.mark.parametrize("key", list(MACHINE_FIXTURES))
def test_repo_blank_over_one_machine_value(key, probe):
    machine = nest(key, MACHINE_FIXTURES[key])
    assert diff(probe.policy(None, machine),
                probe.policy(committed_blank("repo"), machine)) == []


def test_repo_blank_over_every_machine_value(probe):
    machine = merged(MACHINE_FIXTURES)
    assert diff(probe.policy(None, machine),
                probe.policy(committed_blank("repo"), machine)) == []


def test_machine_blank_with_repo_layer_schema_only(probe):
    assert diff(probe.policy(repo_file(), None),
                probe.policy(repo_file(), committed_blank("machine"))) == []


@pytest.mark.parametrize("key", list(REPO_FIXTURES))
def test_machine_blank_under_one_repo_value(key, probe):
    repo = repo_file(nest(key, REPO_FIXTURES[key]))
    assert diff(probe.policy(repo, None), probe.policy(repo, committed_blank("machine"))) == []


def test_machine_blank_under_every_repo_value(probe):
    repo = repo_file(merged(REPO_FIXTURES))
    assert diff(probe.policy(repo, None), probe.policy(repo, committed_blank("machine"))) == []


def test_autocycle_settings_warn_about_neither_blank(tmp_path):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.json").write_text(committed(BLANK_FILE["repo"]), encoding="utf-8")
    gpath = tmp_path / "machine.json"
    gpath.write_text(committed(BLANK_FILE["machine"]), encoding="utf-8")
    assert crew_autocycle.settings(str(root), global_path=str(gpath))["_warnings"] == []


# --- the blanks pass crew's own validator ---------------------------------------------

_INFO_TAGS = ("[missing-keys]", "[authority]")


def value_problems(layer, cfg):
    """Every leaf of `cfg` that is not a legal blank value for `layer`: outside
    the layer, not the layer default, or (when not null) outside the values the
    registry declares. `crew_config.py --check` validates the `environments`
    block only and exits 0 on findings, so it cannot catch a bad value; this is
    the value-level check the blanks are held to."""
    bad = []
    keys = set(crew_keys.layer_keys(layer))
    for key, value in _leaf_values(cfg).items():
        if key == "schema" and layer == "repo":
            if value != SCHEMA:
                bad.append(f"schema: {value!r} is not {SCHEMA!r}")
            continue
        if key not in keys:
            bad.append(f"{key}: not a {layer}-layer key")
            continue
        found, default = crew_keys.layer_default(layer, key)
        if not found or value != default:
            bad.append(f"{key}: {value!r} is not the {layer} default {default!r}")
        declared = crew_keys.values_of(key)
        if declared and value is not None:
            items = value if crew_keys.KEY_META[key]["type"] == "list of" else [value]
            if not isinstance(items, list) or any(v not in declared for v in items):
                bad.append(f"{key}: {value!r} is not one of the declared {declared!r}")
    return bad


def _leaf_values(cfg, prefix=""):
    out = {}
    for name, value in cfg.items():
        dotted = prefix + name
        if isinstance(value, dict) and value and dotted not in crew_keys.KEY_META:
            out.update(_leaf_values(value, dotted + "."))
        else:
            out[dotted] = value
    return out


@pytest.mark.parametrize("layer", ["repo", "machine"])
def test_blank_values_are_layer_defaults(layer):
    assert value_problems(layer, committed_blank(layer)) == []


def _run_check(tmp_path, args, cwd):
    env = dict(os.environ)
    env["HOME"] = env["USERPROFILE"] = str(tmp_path / "home")
    env.pop("CLAUDE_CONFIG_DIR", None)
    done = subprocess.run([sys.executable, CREW_CONFIG_PY, *args], cwd=str(cwd), env=env,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          timeout=120, check=False)
    return done.returncode, done.stdout + done.stderr


def test_repo_blank_passes_check(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".crew").mkdir(parents=True)
    (tmp_path / "home").mkdir()
    shutil.copyfile(os.path.join(CONF_DIR, BLANK_FILE["repo"]), repo / ".crew" / "config.json")
    code, out = _run_check(tmp_path, ["--check"], repo)
    # `--check` exits 0 even with findings (crew_config.py, `if args.check:`) and
    # reports the `environments` block only, so "no warnings" is the signal.
    assert code == 0, out
    assert "no warnings" in out and "[warn]" not in out, out
    copied = json.loads((repo / ".crew" / "config.json").read_text(encoding="utf-8"))
    assert value_problems("repo", copied) == []


def test_machine_blank_passes_check_global(tmp_path):
    (tmp_path / "home" / ".claude" / "crew").mkdir(parents=True)
    (tmp_path / "repo").mkdir()
    shutil.copyfile(os.path.join(CONF_DIR, BLANK_FILE["machine"]),
                    tmp_path / "home" / ".claude" / "crew" / "config.json")
    code, out = _run_check(tmp_path, ["--check-global"], tmp_path / "repo")
    assert code == 0, out
    findings = [line for line in out.splitlines() if line.startswith("- [")]
    assert findings and all(line[2:].startswith(_INFO_TAGS) for line in findings), out
    copied = json.loads((tmp_path / "home" / ".claude" / "crew" / "config.json")
                        .read_text(encoding="utf-8"))
    assert value_problems("machine", copied) == []


# --- the mutations this suite must catch (the spec's sabotage rows, committed) ---------
#
# Each row breaks one thing the probe depends on, in memory only (monkeypatch
# restores it), and asserts the check that should notice goes red. A row that
# stays green means that check has gone vacuous. The file-level rows (a one-byte
# edit, a deleted file, a dropped exclusion) are in scripts/_test/config-reference.py.

THIS = sys.modules[__name__]


def goes_red(check, *args):
    with pytest.raises(AssertionError):
        check(*args)


def test_mutation_null_shadows_disabled_is_caught(probe, monkeypatch):
    """Without `null_shadows`, the repo blank's nulls beat the machine values."""
    monkeypatch.setattr(crew_config, "null_shadows", lambda *_a, **_k: [])
    key = "qa.codex.reasoningEffort"
    machine = nest(key, MACHINE_FIXTURES[key])
    changed = diff(probe.policy(None, machine), probe.policy(committed_blank("repo"), machine))
    assert ("explain", True, key) in changed, changed
    goes_red(test_repo_blank_over_one_machine_value, key, probe)
    goes_red(test_repo_blank_over_every_machine_value, probe)


def test_mutation_humanonly_null_read_as_true_is_caught(probe, monkeypatch):
    """`crew_humanonly._layer_value` reading a blank's `null` as `true`: red in
    both directions, and only because the opt-out is receipt-backed."""
    real = crew_humanonly._layer_value  # pylint: disable=protected-access

    def null_is_true(cfg, key):
        block = cfg.get("humanOnly") if isinstance(cfg, dict) else None
        if isinstance(block, dict) and key in block and block[key] is None:
            return True
        return real(cfg, key)

    monkeypatch.setattr(crew_humanonly, "_layer_value", null_is_true)
    opt_out = {"humanOnly": {"approve": False}}
    entry = ("humanonly", "approve")
    assert entry in diff(probe.policy(None, opt_out),
                         probe.policy(committed_blank("repo"), opt_out))
    assert entry in diff(probe.policy(repo_file(opt_out), None),
                         probe.policy(repo_file(opt_out), committed_blank("machine")))
    goes_red(test_seeded_machine_opt_out_resolves_false, probe)
    goes_red(test_seeded_repo_opt_out_resolves_false, probe)


def test_mutation_autocycle_null_read_as_false_is_caught(probe, monkeypatch):
    """`crew_autocycle.settings` reading a repo `enabled: null` as `false`."""
    real = crew_autocycle._block  # pylint: disable=protected-access

    def null_is_false(*args):
        block = real(*args)
        if "enabled" in block and block["enabled"] is None:
            block = dict(block, enabled=False)
        return block

    monkeypatch.setattr(crew_autocycle, "_block", null_is_false)
    machine = nest("context.autoClear.enabled", True)
    changed = diff(probe.policy(None, machine), probe.policy(committed_blank("repo"), machine))
    assert changed == [("autocycle", "enabled")], changed


def test_mutation_no_receipts_seeded_is_caught(probe, monkeypatch):
    """Unseeded, `resolve` answers human-only whatever the files say, so its
    policy() entry would be a constant that proves nothing."""
    monkeypatch.setattr(THIS, "seed_receipts", lambda *_a, **_k: None)
    goes_red(test_seeded_machine_opt_out_resolves_false, probe)
    goes_red(test_seeded_repo_opt_out_resolves_false, probe)
    for layer, cfgs in (("machine", (None, nest("humanOnly.approve", False))),
                        ("repo", (repo_file(nest("humanOnly.approve", False)), None))):
        base = probe.policy(None, None) if layer == "machine" else probe.policy(repo_file(), None)
        entries = diff(base, probe.policy(*cfgs))
        assert not any(entry[0] == "humanonly" for entry in entries), (layer, entries)


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_mutation_humanonly_fixture_true_is_caught(layer, probe):
    """A `humanOnly.*` fixture of `true` never reaches `crew_humanonly.resolve`
    (it resolves like the default), which is why both tables hold `false`."""
    def policy(value):
        cfg = None if value is None else nest("humanOnly.approve", value)
        if layer == "machine":
            return probe.policy(None, cfg)
        return probe.policy(repo_file(cfg), None)

    assert FIXTURES[layer]["humanOnly.approve"] is False
    assert ("humanonly", "approve") in diff(policy(None), policy(False))
    assert ("humanonly", "approve") not in diff(policy(None), policy(True))


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_mutation_dropped_fixture_is_caught(layer, monkeypatch):
    monkeypatch.delitem(FIXTURES[layer], "reaper.spinCpuPct")
    goes_red(test_fixture_coverage, layer)


@pytest.mark.parametrize("layer", ["machine", "repo"])
def test_mutation_fixture_at_its_default_is_caught(layer, monkeypatch):
    found, default = crew_keys.layer_default(layer, "reaper.spinCpuPct")
    assert found
    monkeypatch.setitem(FIXTURES[layer], "reaper.spinCpuPct", default)
    goes_red(test_fixture_values_are_valid, layer)


@pytest.mark.parametrize("layer", ["machine", "repo"])
@pytest.mark.parametrize("key", sorted(INERT_ALONE))
def test_mutation_inert_alone_entry_removed_is_caught(layer, key, effects, probe, monkeypatch):
    monkeypatch.delitem(INERT_ALONE, key)
    goes_red(test_fixture_has_an_effect, layer, key, effects, probe)


def test_mutation_invalid_blank_value_is_caught():
    """`crew_config.py --check` exits 0 on a bogus value; `value_problems` does not."""
    blank = committed_blank("repo")
    blank["qa"]["codex"]["reasoningEffort"] = "bogus"
    assert any(line.startswith("qa.codex.reasoningEffort:")
               for line in value_problems("repo", blank))
