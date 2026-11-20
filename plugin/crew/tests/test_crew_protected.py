"""R-32: the protected-policy comparator (`crew_protected.py`), report-only.

Must-block rows (each is a widening or unknown, and `classify` is not
`free`), must-allow rows, the differential against each enforcing reader
called directly, the coverage and isolation checks, and the in-file
MUTATIONS: weakened copies of the module, each of which must turn a named
case red (R-01's pattern; the shared `sabotage*.py` files are review
harness and wait for R-32b).

Every case builds its own throwaway HOME, machine file and git repo under
`tmp_path` and points the in-process readers there (`GLOBAL_CONFIG_PATH`,
as `test_git_allow.py` does); nothing touches real config and nothing is
installed. Route rule: a row that involves a receipt makes it with
`crew_confirm_config` on those same paths and judges with `judge_drift`
there, never through `judge_change`'s copies.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import types

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import cloud_guard
import crew_autopilot
import crew_config
import crew_confirm_config
import crew_gitallow
import crew_guards
import crew_humanonly
import crew_keys
import crew_policy
import crew_protected
import crew_state
import crew_ticket
import crew_worktrees

SCRIPTS = os.path.dirname(os.path.abspath(crew_protected.__file__))
PLUGIN = os.path.dirname(os.path.dirname(SCRIPTS))
MODULE = os.path.join(SCRIPTS, "crew_protected.py")
GIT_KEY = crew_gitallow.KEY
FREE = "free"


def source():
    with open(MODULE, encoding="utf-8") as handle:
        return handle.read()


# --- the throwaway world -------------------------------------------------------------------

class World:
    """A temp HOME with the machine file, and a git repo whose `.crew/` is
    ignored (so its config is untracked unless a case adds it)."""

    def __init__(self, base, monkeypatch):
        self.base = base
        self.home = base / "home"
        self.machine = self.home / ".claude" / "crew" / "config.json"
        self.machine.parent.mkdir(parents=True)
        self.machine.write_text("{}", encoding="utf-8")
        self.root = base / "repo"
        (self.root / ".crew").mkdir(parents=True)
        _git(self.root, "init", "-q", "-b", "main")
        _git(self.root, "config", "user.email", "t@example.com")
        _git(self.root, "config", "user.name", "t")
        (self.root / ".gitignore").write_text(".crew/\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "seed")
        self.repo_file = self.root / ".crew" / "config.json"
        for module in (crew_state, crew_config):
            monkeypatch.setattr(module, "GLOBAL_CONFIG_PATH", str(self.machine))
        monkeypatch.setenv("HOME", str(self.home))
        monkeypatch.setenv("USERPROFILE", str(self.home))
        for name in ("CI", "CREW_UNATTENDED"):
            monkeypatch.delenv(name, raising=False)

    @property
    def baseline(self):
        return self.machine.parent / "protected-policy" / "baseline.json"

    def put(self, layer, body):
        path = self.machine if layer == "machine" else self.repo_file
        if body is None:
            if path.exists():
                path.unlink()
            return
        text = body if isinstance(body, str) else json.dumps(body)
        path.write_text(text, encoding="utf-8")

    def init(self, mod):
        return mod.init_baseline(str(self.root), global_path=str(self.machine))

    def drift(self, mod, advance=True):
        return mod.judge_drift(str(self.root), global_path=str(self.machine), advance=advance)

    def baseline_digest(self):
        return hashlib.sha256(self.baseline.read_bytes()).hexdigest()

    def confirm(self, key, value, layer="machine", path=None):
        """`propose` then two `confirm`s from two prompts: the only way real
        code makes a receipt. Returns the applied record."""
        gpath = str(path or self.machine)
        cid = crew_confirm_config.propose(layer, key, root=str(self.root), global_path=gpath,
                                          value=value)["change_id"]
        crew_confirm_config.confirm(cid, "user-prompt", f"p1-{cid}", global_path=gpath)
        record = crew_confirm_config.confirm(cid, "user-prompt", f"p2-{cid}", global_path=gpath)
        assert record["state"] == "applied", record.get("reason")
        return record


def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL).stdout


@pytest.fixture(name="world")
def _world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def _row(result, leaf):
    rows = [r for r in result["leaves"] if r["leaf"] == leaf]
    assert rows, f"{leaf} not in the result"
    return rows[0]


def _blocked(mod, result):
    assert result["status"] != FREE, result["changed"]
    assert mod.classify(result) != FREE


def _change(mod, before, after, **kw):
    enc = {k: None if v is None else json.dumps(v).encode() for k, v in before.items()}
    new = {k: None if v is None else (v if isinstance(v, bytes) else json.dumps(v).encode())
           for k, v in after.items()}
    return mod.judge_change(enc, new, **kw)


def _dir_link(target, link):
    """A directory link: a junction on Windows, a symlink elsewhere. Returns
    why it could not be made, or ""."""
    try:
        if os.name == "nt":
            import _winapi  # pylint: disable=import-outside-toplevel
            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(str(target), str(link), target_is_directory=True)
    except (OSError, AttributeError, ImportError) as exc:
        return f"{type(exc).__name__}: {exc}"
    return ""


def _unlink_dir(link):
    if os.name == "nt":
        os.rmdir(link)
    else:
        os.unlink(link)


# --- must-block -------------------------------------------------------------------------------

def case_mb1_profile_to_off(mod, world):
    del world
    result = _change(mod, {"machine": {"guards": {"profile": "strict"}},
                           "repo": {"guards": {"profile": "off"}}},
                     {"machine": {"guards": {"profile": "off"}},
                      "repo": {"guards": {"profile": "off"}}})
    _blocked(mod, result)
    assert _row(result, "guards.roleWrites")["outcome"] == "widening"
    assert mod.classify(result) == "widen-policy"


def case_mb2_restrict_set_shrinks(mod, world):
    world.put("repo", {"production": {"hosts": ["prod-a", "prod-b"]}})
    assert world.init(mod)[0]
    world.put("repo", {"production": {"hosts": ["prod-a"]}})
    result = world.drift(mod)
    _blocked(mod, result)
    assert _row(result, "production.hosts")["outcome"] == "widening"


def case_mb3_whole_file_replaced(mod, world):
    world.put("repo", {"scope": {"mode": "block"}})
    assert world.init(mod)[0]
    world.put("repo", {})
    result = world.drift(mod)
    _blocked(mod, result)
    assert _row(result, "scope.mode")["outcome"] == "widening"


def case_mb4_whole_file_deleted(mod, world):
    world.put("repo", {"scope": {"mode": "block"}})
    assert world.init(mod)[0]
    world.put("repo", None)
    result = world.drift(mod)
    _blocked(mod, result)
    assert _row(result, "scope.mode")["outcome"] == "widening"


def case_mb5_link_after_baseline(mod, world):
    world.put("repo", {"scope": {"mode": "block"}})
    assert world.init(mod)[0]
    wide = world.base / "elsewhere" / ".crew"
    wide.mkdir(parents=True)
    (wide / "config.json").write_text(json.dumps({"scope": {"mode": "block"}}), encoding="utf-8")
    shutil.rmtree(world.root / ".crew")
    why = _dir_link(wide, world.root / ".crew")
    if why:
        pytest.skip(f"a directory link could not be made here: {why}")
    result = world.drift(mod)
    _blocked(mod, result)
    assert _row(result, "scope.mode")["outcome"] == "unknown"
    # A link present at baseline time, retargeted afterwards.
    other = world.base / "other" / ".crew"
    other.mkdir(parents=True)
    (other / "config.json").write_text(json.dumps({"scope": {"mode": "block"}}), encoding="utf-8")
    world.baseline.unlink()
    assert world.init(mod)[0]
    _unlink_dir(world.root / ".crew")
    assert not _dir_link(other, world.root / ".crew")
    result = world.drift(mod)
    _blocked(mod, result)
    assert _row(result, "scope.mode")["outcome"] == "unknown"


def case_mb6_alternate_writer(mod, world):
    world.put("machine", {"guards": {"profile": "strict"}})
    world.put("repo", {"guards": {"profile": "off"}})
    assert world.init(mod)[0]
    code = ("import json,sys; open(sys.argv[1],'w').write(json.dumps("
            "{'guards': {'profile': 'off'}}))")
    subprocess.run([sys.executable, "-c", code, str(world.machine)], check=True)
    result = world.drift(mod)
    _blocked(mod, result)
    assert _row(result, "guards.roleWrites")["outcome"] == "widening"
    assert mod.classify(result) == "change-guard-config-directly"


def case_mb7_corrupt_layer(mod, world, text="{not json"):
    assert world.init(mod)[0]
    world.put("machine", text)
    result = world.drift(mod)
    _blocked(mod, result)
    assert _row(result, "guards.forcePush")["outcome"] == "unknown"
    world.put("machine", "{}")
    result = _change(mod, {"machine": {}, "repo": None}, {"machine": text.encode(), "repo": None})
    _blocked(mod, result)
    assert _row(result, "guards.forcePush")["outcome"] == "unknown"


def case_mb8_repo_adds_non_prod(mod, world):
    world.put("repo", {"environments": {"nonProd": ["dev"]}})
    assert world.init(mod)[0]
    world.put("repo", {"environments": {"nonProd": ["dev", "prod-*"]}})
    result = world.drift(mod)
    _blocked(mod, result)
    assert _row(result, "environments.nonProd")["outcome"] == "widening"


def case_mb9_leaf_with_no_row(mod, world):
    assert world.init(mod)[0]
    world.put("repo", {"approvals": {"run": {"classes": ["deploy"]}}})
    result = world.drift(mod)
    _blocked(mod, result)
    assert _row(result, "approvals.run.classes")["outcome"] == "unknown"


def case_mb10_unreadable_baseline(mod, world):
    assert world.init(mod)[0]
    world.baseline.write_text("{broken", encoding="utf-8")
    result = world.drift(mod)
    _blocked(mod, result)
    assert result["status"] == "unknown"


def _assert_unhonoured(mod, world, leaf, digest):
    result = world.drift(mod)
    _blocked(mod, result)
    row = _row(result, leaf)
    assert row["outcome"] == "widening", row
    assert "would refuse: hand edit not honoured" in row["reason"], row
    assert mod.classify(result) == "change-guard-config-directly"
    assert world.baseline_digest() == digest
    return row


def _git_shape(world, shape):
    machine = str(world.machine)
    if shape == "another value":
        world.confirm(GIT_KEY, ["status"])
    elif shape == "another key":
        world.confirm("humanOnly.approve", False)
    elif shape == "another file":
        world.confirm(GIT_KEY, "all", path=world.machine.parent / "other.json")
    elif shape == "revoked":
        world.confirm(GIT_KEY, "all")
        assert crew_humanonly.revoke("machine", machine, GIT_KEY, global_path=machine)


GIT_SHAPES = ("another value", "another key", "another file", "revoked", "none")


def case_mb11_git_allow_hand_edit(mod, world, shapes=GIT_SHAPES):
    for shape in shapes:
        world.put("machine", {})
        world.put("repo", None)
        if world.baseline.exists():
            world.baseline.unlink()
        shutil.rmtree(crew_humanonly.store_dir(str(world.machine)), ignore_errors=True)
        assert world.init(mod)[0]
        digest = world.baseline_digest()
        _git_shape(world, shape)
        world.put("machine", {"guards": {"git": {"allow": "all"}}})
        setting = crew_gitallow.settings(str(world.root), global_path=str(world.machine))
        assert setting["allow"] == "off" and "not honoured" in setting["why"], (shape, setting)
        row = _assert_unhonoured(mod, world, GIT_KEY, digest)
        assert row["before"] == row["after"] == "off", (shape, row)


def _human_shape(world, shape):
    machine = str(world.machine)
    if shape == "another key":
        world.confirm("humanOnly.promoteMarker", False)
    elif shape == "another switch":
        world.confirm(GIT_KEY, "all")
    elif shape == "another file":
        world.confirm("humanOnly.approve", False, path=world.machine.parent / "other.json")
    elif shape == "revoked":
        world.confirm("humanOnly.approve", False)
        assert crew_humanonly.revoke("machine", machine, "humanOnly.approve",
                                     global_path=machine)


HUMAN_SHAPES = ("another key", "another switch", "another file", "revoked", "none")


def case_mb11_human_only_hand_edit(mod, world, shapes=HUMAN_SHAPES):
    for shape in shapes:
        world.put("machine", {})
        if world.baseline.exists():
            world.baseline.unlink()
        shutil.rmtree(crew_humanonly.store_dir(str(world.machine)), ignore_errors=True)
        assert world.init(mod)[0]
        digest = world.baseline_digest()
        _human_shape(world, shape)
        world.put("machine", {"humanOnly": {"approve": False}})
        answer = crew_humanonly.resolve(str(world.root), "approve",
                                        global_path=str(world.machine))
        assert answer["humanOnly"] is True, (shape, answer)
        assert answer["layers"]["machine"]["why"].startswith("false, not honoured"), answer
        row = _assert_unhonoured(mod, world, "humanOnly.approve", digest)
        assert row["before"] is True and row["after"] is True, (shape, row)


def case_mb11_tracked_repo_false(mod, world):
    world.put("repo", {"scope": {"mode": "off"}})  # the writer refuses an empty object
    assert world.init(mod)[0]
    digest = world.baseline_digest()
    record = world.confirm("humanOnly.approve", False, layer="repo")
    assert record["target"] == crew_humanonly.target_key(str(world.repo_file))
    _git(world.root, "add", "-f", ".crew/config.json")
    answer = crew_humanonly.resolve(str(world.root), "approve", global_path=str(world.machine))
    assert answer["humanOnly"] is True
    assert "only the machine file or an untracked repo file may opt out" in \
        answer["layers"]["repo"]["why"]
    _assert_unhonoured(mod, world, "humanOnly.approve", digest)


def case_mb12_init_refuses_a_widening(mod, world):
    world.put("repo", {"scope": {"mode": "block"}})
    assert world.init(mod)[0]
    digest = world.baseline_digest()
    world.put("repo", {"scope": {"mode": "off"}})
    written, why = world.init(mod)
    assert not written and why.startswith("refused"), why
    assert world.baseline_digest() == digest


def case_mb13_override_loosens_a_guard(mod, world):
    del world
    before = {"machine": {"guards": {"profile": "strict"}}, "repo": {"guards": {"profile": "off"}}}
    loose = {"guards": {"profile": "strict", "overrides": {"forcePush": "allow"}}}
    result = _change(mod, before, {"machine": loose,
                                   "repo": {"guards": {"profile": "off",
                                                       "overrides": {"forcePush": "allow"}}}})
    _blocked(mod, result)
    assert _row(result, "guards.forcePush")["outcome"] == "widening"
    result = _change(mod, before, {"machine": {"guards": {"profile": "strict",
                                                          "overrides": {"notAGuard": "block"}}},
                                   "repo": before["repo"]})
    _blocked(mod, result)
    assert _row(result, "guards.overrides")["outcome"] == "unknown"


def case_mb14_prod_unattended(mod, world):
    del world
    off = {"environments": {"prodUnattended": False}}
    on = {"environments": {"prodUnattended": True}}
    result = _change(mod, {"machine": off, "repo": off}, {"machine": on, "repo": on})
    _blocked(mod, result)
    assert _row(result, "environments.prodUnattended")["outcome"] == "widening"


def case_mb15_effective_narrowing_hides_raw(mod, world):
    world.confirm(GIT_KEY, ["status", "log"])
    assert crew_gitallow.settings(str(world.root), global_path=str(world.machine))["allow"] == \
        frozenset({"status", "log"})
    assert world.init(mod)[0]
    digest = world.baseline_digest()
    code = ("import json,sys; open(sys.argv[1],'w').write(json.dumps("
            "{'guards': {'git': {'allow': 'all'}}}))")
    subprocess.run([sys.executable, "-c", code, str(world.machine)], check=True)
    assert crew_gitallow.settings(str(world.root), global_path=str(world.machine))["allow"] == "off"
    row = _assert_unhonoured(mod, world, GIT_KEY, digest)
    assert row["change"] == "narrowing"


def case_mb16_scope_mode(mod, world):
    world.put("repo", {"scope": {"mode": "block"}})
    assert world.init(mod)[0]
    world.put("repo", {"scope": {"mode": "auto"}})
    result = world.drift(mod)
    _blocked(mod, result)
    assert _row(result, "scope.mode")["outcome"] == "widening"
    world.put("repo", {"scope": {"mode": "lax"}})
    result = world.drift(mod)
    _blocked(mod, result)
    assert _row(result, "scope.mode")["outcome"] == "unknown"


UC = {"aws": {"nonProd": {"dev": {"profile": "p", "region": "us-east-1",
                                  "identity": "arn:aws:sts::123456789012:assumed-role/r/"}}}}


def case_mb17_unattended_cloud(mod, world):
    assert crew_config.unattended_cloud_block_problem(UC) == ""
    world.put("machine", {"unattendedCloud": UC})
    assert world.init(mod)[0]
    world.put("repo", {"unattendedCloud": {"aws": {"nonProd": {}}}})
    result = world.drift(mod)
    assert result["status"] == FREE, result["changed"]
    wider = json.loads(json.dumps(UC))
    wider["aws"]["nonProd"]["qa"] = dict(UC["aws"]["nonProd"]["dev"])
    world.put("machine", {"unattendedCloud": wider})
    result = world.drift(mod)
    _blocked(mod, result)
    assert _row(result, "unattendedCloud.aws.nonProd")["outcome"] == "widening"


def case_mb18_confirmation_gap(mod, world):
    world.put("machine", {"guards": {"profile": "strict"}})
    world.put("repo", {"guards": {"profile": "off"}})
    assert world.init(mod)[0]
    digest = world.baseline_digest()
    world.put("machine", {"guards": {"profile": "standard"}})
    result = world.drift(mod)
    _blocked(mod, result)
    assert mod.classify(result) == "change-guard-config-directly"
    widened = {r["leaf"] for r in result["changed"] if r["outcome"] == "widening"}
    assert {"guards.roleWrites", "guards.envGuard"} <= widened, widened
    assert world.baseline_digest() == digest
    result = _change(mod, {"machine": {"guards": {"profile": "strict"}},
                           "repo": {"guards": {"profile": "off"}}},
                     {"machine": {"guards": {"profile": "standard"}},
                      "repo": {"guards": {"profile": "off"}}})
    assert mod.classify(result) == "widen-policy"
    with pytest.raises(crew_confirm_config.Refused):
        crew_confirm_config.propose("machine", "guards.profile", value="standard",
                                    global_path=str(world.machine))


def case_mb19_change_never_confirms(mod, world):
    record = world.confirm(GIT_KEY, "all")
    assert record["target"] == crew_humanonly.target_key(str(world.machine))
    result = _change(mod, {"machine": {}, "repo": None},
                     {"machine": {"guards": {"git": {"allow": "all"}}}, "repo": None})
    _blocked(mod, result)
    row = _row(result, GIT_KEY)
    assert row["outcome"] == "widening" and "confirm through /crew:confirm-config" in row["reason"]
    assert mod.classify(result) == "widen-policy"
    result = _change(mod, {"machine": {}, "repo": {}},
                     {"machine": {}, "repo": {"humanOnly": {"approve": False}}},
                     tracked=crew_humanonly.UNTRACKED)
    _blocked(mod, result)
    assert _row(result, "humanOnly.approve")["outcome"] == "widening"


# --- must-allow -------------------------------------------------------------------------------

def _free_and_advanced(mod, world):
    digest = world.baseline_digest()
    result = world.drift(mod)
    assert result["status"] == FREE, result["changed"]
    assert mod.classify(result) == FREE
    assert result["advanced"]
    return digest != world.baseline_digest()


def case_ma1_narrowing_in_each_kind(mod, world):
    world.put("machine", {"guards": {"profile": "off"}})
    world.put("repo", {"guards": {"profile": "off"}, "scope": {"mode": "off",
                                                              "allowCliApproval": True},
                       "environments": {"nonProd": ["dev", "qa"]},
                       "production": {"hosts": ["prod-a"]}})
    assert world.init(mod)[0]
    steps = [
        ("machine", {"guards": {"profile": "strict"}}),
        ("repo", {"guards": {"profile": "off"}, "scope": {"mode": "off", "allowCliApproval": True},
                  "environments": {"nonProd": ["dev"]}, "production": {"hosts": ["prod-a"]}}),
        ("repo", {"guards": {"profile": "off"}, "scope": {"mode": "off", "allowCliApproval": True},
                  "environments": {"nonProd": ["dev"]},
                  "production": {"hosts": ["prod-a", "prod-b"]}}),
        ("repo", {"guards": {"profile": "off"}, "scope": {"mode": "off",
                                                          "allowCliApproval": False},
                  "environments": {"nonProd": ["dev"]},
                  "production": {"hosts": ["prod-a", "prod-b"]}}),
        ("repo", {"guards": {"profile": "off"}, "scope": {"mode": "block",
                                                          "allowCliApproval": False},
                  "environments": {"nonProd": ["dev"]},
                  "production": {"hosts": ["prod-a", "prod-b"]}}),
    ]
    for layer, body in steps:
        world.put(layer, body)
        assert _free_and_advanced(mod, world), (layer, body)


def case_ma2_no_change_and_equivalent_rewrite(mod, world):
    body = {"scope": {"mode": "block"}, "production": {"hosts": ["a", "b"]}}
    world.put("repo", body)
    assert world.init(mod)[0]
    result = world.drift(mod)
    assert result["status"] == FREE and not result["changed"]
    world.put("repo", '{\n  "production": {"hosts": ["b", "a"]},\n\n "scope":{"mode":"block"}}')
    result = world.drift(mod)
    assert result["status"] == FREE and not result["changed"], result["changed"]


def case_ma3_unprotected_keys_are_ignored(mod, world):
    assert world.init(mod)[0]
    world.put("repo", {"notify": {"on": ["stop"]}, "graph": {"enabled": False},
                       "install": {"policy": "auto"}, "change": {"requireForProduction": False}})
    world.put("machine", {"install": {"policy": "auto"}})
    result = world.drift(mod)
    assert result["status"] == FREE and not result["changed"], result["changed"]


def case_ma4_receipts_confirm_exactly(mod, world):
    assert world.init(mod)[0]
    world.confirm("humanOnly.approve", False)
    record = world.confirm(GIT_KEY, "all")
    assert record["target"] == crew_humanonly.target_key(str(world.machine))
    assert crew_gitallow.settings(str(world.root), global_path=str(world.machine))["allow"] == "all"
    assert crew_humanonly.resolve(str(world.root), "approve",
                                  global_path=str(world.machine))["humanOnly"] is False
    assert _free_and_advanced(mod, world)
    entry = json.loads(world.baseline.read_text(encoding="utf-8"))["repos"]
    raw = next(iter(entry.values()))["raw"]
    assert raw[GIT_KEY]["machine"] == "all" and raw["humanOnly.approve"]["machine"] is False


def case_ma5_no_baseline(mod, world):
    result = world.drift(mod)
    assert result["status"] == "no-baseline"
    assert mod.classify(result) != FREE


def case_ma6_silent_default_control(mod, world):
    world.put("machine", {"humanOnly": {"approve": True}})
    assert world.init(mod)[0]
    world.put("machine", {"humanOnly": {}})
    result = world.drift(mod)
    assert result["status"] == FREE and not result["changed"], result["changed"]


def case_ma7_raw_narrowing_is_free(mod, world):
    for after in ({"guards": {"git": {"allow": ["status"]}}}, {}):
        world.put("machine", {})
        if world.baseline.exists():
            world.baseline.unlink()
        world.confirm(GIT_KEY, "all")
        assert world.init(mod)[0]
        world.put("machine", after)
        assert _free_and_advanced(mod, world), after


L_TABLE = [
    {"machine": None, "repo": None},
    {"machine": {"guards": {"profile": "strict", "git": {"allow": "all"}},
                 "humanOnly": {"approve": False}, "scope": {"mode": "off"}},
     "repo": {"guards": {"profile": "off"}, "scope": {"mode": "block"},
              "unattendedCloud": UC, "autopilot": {"sleep": {"approval": "self"}}}},
    {"machine": {"autopilot": {"approval": "self"}, "unattendedCloud": UC,
                 "environments": {"prodUnattended": True}},
     "repo": {"environments": {"nonProd": ["dev"], "prodUnattended": True},
              "production": {"databases": ["db-*"]}, "cloud": {"awsRegions": ["us-east-1"]},
              "humanOnly": {"approve": False}, "worktrees": {"root": None}}},
]


def case_ma8_same_route_both_sides(mod, world):
    del world
    for layers in L_TABLE:
        result = _change(mod, layers, layers)
        assert result["status"] == FREE and not result["changed"], (layers, result["changed"])


def case_ma9_machine_file_through_a_link(mod, world):
    real = world.home / "dotfiles" / "crew"
    real.parent.mkdir(parents=True)
    shutil.move(str(world.machine.parent), str(real))
    why = _dir_link(real, world.machine.parent)
    if why:
        pytest.skip(f"a directory link could not be made here: {why}")
    world.put("machine", {"guards": {"profile": "strict"}, "scope": {"mode": "off"}})
    assert world.init(mod)[0]
    world.put("machine", '{"scope": {"mode": "off"},\n "guards": {"profile": "strict"}}')
    result = world.drift(mod)
    assert result["status"] == FREE and not result["changed"], result["changed"]


CASES = {name: fn for name, fn in globals().items() if name.startswith("case_")}


@pytest.mark.parametrize("name", sorted(n for n in CASES if n != "case_mb7_corrupt_layer"))
def test_case(name, world):
    CASES[name](crew_protected, world)


@pytest.mark.parametrize("text", ["{not json", '{"a": 1, "a": 2}', "[]"])
def test_case_mb7_corrupt_layer(text, world):
    case_mb7_corrupt_layer(crew_protected, world, text)


def test_a_bom_prefixed_layer_reads_as_the_enforcing_readers_read_it(world):
    """`read_layer` decodes utf-8-sig. That tolerance is only safe while the
    enforcing readers tolerate a BOM too (`crew_common.read_text`, which
    `crew_config` and `crew_state` read through, and `crew_gitallow`'s own
    strict read): a BOM the comparator accepted but a reader rejected would
    let the two disagree about what a layer says."""
    body = {"guards": {"profile": "strict"}, "scope": {"allowCliApproval": False}}
    world.repo_file.write_bytes(b"\xef\xbb\xbf" + json.dumps(body).encode("utf-8"))
    layer = crew_protected.read_layer(str(world.repo_file))
    assert layer["state"] == "ok", layer["why"]
    assert layer["cfg"] == body
    assert json.loads(crew_state.read_text(str(world.repo_file))) == body
    assert json.loads(world.repo_file.read_bytes().decode("utf-8-sig"),
                      object_pairs_hook=crew_gitallow.strict_pairs) == body


# --- the differential: each row against its reader, called directly --------------------------

DIFF_TABLE = L_TABLE + [
    {"machine": {"guards": {"profile": "off", "overrides": {"forcePush": "allow"}},
                 "scope": {"allowCliApproval": True}, "worktrees": {"root": "/opt/wt"}},
     "repo": {"guards": {"profile": "strict"}, "humanOnly": {"approve": None},
              "autopilot": {"sleep": {"schedule": "22:00-06:00", "deploy": "nonprod"}}}},
    {"machine": {}, "repo": {"guards": {"forcePush": "allow"}, "scope": {"allowCliApproval": True},
                             "environments": {"workflows": {"deploy.yml": "dev"}}}},
]


def _direct(world):
    """Every leaf as its enforcing reader answers, called by its public name."""
    root, machine = str(world.root), str(world.machine)
    out = {}
    for name in crew_guards.ALL_GUARD_NAMES:
        out[f"guards.{name}"] = crew_config.resolve_ratcheted(root, f"guards.{name}",
                                                              machine)["effective"]
    out["environments.prodUnattended"] = crew_config.resolve_ratcheted(
        root, "environments.prodUnattended", machine)["effective"]
    allow = crew_gitallow.settings(root, global_path=machine)["allow"]
    out[GIT_KEY] = sorted(allow) if isinstance(allow, frozenset) else allow
    for key in crew_humanonly.KEYS:
        out[f"humanOnly.{key}"] = crew_humanonly.resolve(root, key,
                                                         global_path=machine)["humanOnly"]
    out["scope.mode"] = crew_ticket.configured_mode(root)[0]
    out["scope.allowCliApproval"] = crew_ticket.cli_approval_allowed(root)
    block = crew_config.resolve_config(root)["autopilot"]
    sleep = crew_autopilot._sleep_block(root, block)  # pylint: disable=protected-access
    out["autopilot.sleep.schedule"] = sleep.get("schedule")
    for key in ("approval", "questions", "deploy"):
        out[f"autopilot.sleep.{key}"] = sleep.get(key) or block.get(key)
    where = crew_worktrees.resolve(root)
    out["worktrees.root"] = {"base": where["base"], "problem": bool(where["problem"])}
    envs = cloud_guard.environments_config(root)
    out["environments.nonProd"] = sorted(json.dumps(v) for v in set(envs["nonProd"]))
    out["environments.workflows"] = envs["workflows"]
    out["environments.preProduction"] = envs["preProduction"]
    for key, guard in (("hosts", "prodServer"), ("databases", "prodDatabase")):
        out[f"production.{key}"] = sorted(
            json.dumps(v) for v in set(crew_config.production_declaration(root, guard).patterns))
    pins, _problem = cloud_guard.cloud_pins(root)
    for key, values in pins.items():
        out[f"cloud.{key}"] = sorted(json.dumps(v) for v in set(values))
    return out


def case_differential(mod, world):
    for layers in DIFF_TABLE:
        for layer, body in layers.items():
            world.put(layer, body)
        snap = mod.effective_protected(str(world.root), global_path=str(world.machine))
        direct = _direct(world)
        for leaf, value in direct.items():
            assert snap["policy"][leaf] == value, (leaf, layers, snap["policy"][leaf], value)


def case_differential_with_receipts(mod, world):
    world.put("repo", {"scope": {"mode": "off"}})
    world.confirm("humanOnly.approve", False, layer="repo")
    world.confirm(GIT_KEY, ["status"])
    snap = mod.effective_protected(str(world.root), global_path=str(world.machine))
    assert snap["targets"]["machine"] == crew_humanonly.target_key(str(world.machine))
    assert snap["targets"]["repo"] == crew_humanonly.target_key(str(world.repo_file))
    direct = _direct(world)
    assert direct["humanOnly.approve"] is False and direct[GIT_KEY] == ["status"]
    for leaf, value in direct.items():
        assert snap["policy"][leaf] == value, leaf
    # The tracked-repo-false row: the same receipt, the file now tracked.
    _git(world.root, "add", "-f", ".crew/config.json")
    snap = mod.effective_protected(str(world.root), global_path=str(world.machine))
    direct = _direct(world)
    assert direct["humanOnly.approve"] is True
    for leaf, value in direct.items():
        assert snap["policy"][leaf] == value, leaf


def test_differential(world):
    case_differential(crew_protected, world)


def test_differential_with_receipts(world):
    case_differential_with_receipts(crew_protected, world)


# --- coverage and isolation -----------------------------------------------------------------

def _under(path, prefixes):
    return any(path == p or path.startswith(p + ".") for p in prefixes)


def case_coverage(mod, world=None):
    del world
    union = set()
    union.update(p for p in crew_config.leaf_paths(crew_config.default_config())
                 if _under(p, mod.PROTECTED))
    union.update(k for k in crew_guards.RATCHETED_KEYS if _under(k, mod.PROTECTED))
    for key in crew_guards.REPO_ONLY_AUTOPILOT:
        if _under(key, mod.PROTECTED):
            union.update(p for p in crew_keys.all_leaves() if _under(p, (key,)))
    union.update(p for p in crew_keys.all_leaves()
                 if _under(p, crew_state.UNATTENDED_CLOUD_MACHINE_ONLY))
    union.update(p for p in crew_keys.all_leaves() if _under(p, mod.PROTECTED))
    assert {f"guards.{n}" for n in crew_guards.ALL_GUARD_NAMES} <= union
    assert "autopilot.sleep.schedule" in union and "unattendedCloud.aws.nonProd" in union
    for leaf in sorted(union):
        assert leaf in mod.LEAVES, leaf
        name = mod.row_name(leaf)
        assert name in mod.READERS and name in mod.DIRECTIONS, leaf
    assert mod.DIRECTIONS.get("guards.overrides") == ("derived", "guards")
    for key in crew_guards.RATCHETED_KEYS:
        assert _under(key, mod.PROTECTED) or key in mod.NOT_PROTECTED, key


def test_coverage():
    case_coverage(crew_protected)


def _plugin_sources():
    for root, dirs, files in os.walk(PLUGIN):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", "tests", "_test")]
        for name in files:
            if name.endswith((".py", ".sh", ".ps1", ".json", ".md")):
                yield os.path.join(root, name)


def test_nothing_in_the_plugin_reaches_the_comparator_yet():
    me = os.path.normcase(MODULE)
    hits = []
    for path in _plugin_sources():
        if os.path.normcase(path) == me:
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            if "crew_protected" in handle.read():
                hits.append(os.path.relpath(path, PLUGIN))
    assert hits == [], "report-only until R-32b wires it"


def test_outcomes_are_policy_operations_by_name_only():
    assert "crew_policy" not in source()
    for op in (crew_protected.WIDEN_POLICY, crew_protected.DIRECT):
        assert op in crew_policy.OPERATIONS


def test_the_module_declares_itself_report_only():
    assert crew_protected.REPORT_ONLY is True
    assert "REPORT-ONLY" in source()
    assert crew_protected.STORE_DIR.endswith("protected-policy")


def test_importing_the_module_prints_nothing():
    done = subprocess.run([sys.executable, "-c", "import crew_protected"], cwd=SCRIPTS,
                          capture_output=True, text=True, check=False, timeout=60)
    assert done.returncode == 0 and done.stdout == "" and done.stderr == ""


def test_the_cli(world):
    def run(*args):
        return subprocess.run([sys.executable, MODULE, *args, "--root", str(world.root),
                               "--global-path", str(world.machine)], capture_output=True,
                              text=True, check=False, timeout=120)
    assert run("keys").returncode == 0
    assert run("frobnicate").returncode == 2
    done = run("check")
    assert done.returncode == 1 and "no-baseline" in done.stdout
    assert run("baseline", "--init").returncode == 0
    assert run("check").returncode == 0
    world.put("repo", {"scope": {"mode": "block"}})
    assert run("check").returncode == 0
    world.put("repo", {})
    done = run("check")
    assert done.returncode == 1 and "would refuse scope.mode" in done.stdout


# --- sabotage: each weakened copy must turn a named case red -------------------------------

MUTATIONS = (
    ("unknown read as unchanged",
     "    if isinstance(before, Unknown) or isinstance(after, Unknown):\n        return UNKNOWN",
     "    if isinstance(before, Unknown) or isinstance(after, Unknown):\n        return UNCHANGED",
     ("case_mb7_corrupt_layer", "case_mb16_scope_mode")),
    ("allow-set growth read as narrowing", "            return WIDENING if grew else NARROWING",
     "            return NARROWING", ("case_mb8_repo_adds_non_prod",)),
    ("restrict-set shrink read as narrowing", "                grew, shrank = shrank, grew",
     "                pass", ("case_mb2_restrict_set_shrinks",)),
    ("corrupted layer read as absent",
     '        out.update(state=UNKNOWN, why=f"{path} does not parse',
     '        out.update(state="absent", why=f"{path} does not parse',
     ("case_mb7_corrupt_layer",)),
    ("link layer followed silently",
     "    if recorded_target is not None and target != recorded_target:",
     "    if False:", ("case_mb5_link_after_baseline",)),
    ("every link is unknown",
     "    if recorded_target is not None and target != recorded_target:",
     "    if target != os.path.normcase(os.path.abspath(path)) or (\n"
     "            recorded_target is not None and target != recorded_target):",
     ("case_ma9_machine_file_through_a_link",)),
    ("a leaf with no row read as unchanged",
     "        change = UNCHANGED if old == new else UNKNOWN", "        change = UNCHANGED",
     ("case_mb9_leaf_with_no_row",)),
    ("judge_drift drops the raw comparison", "        if leaf in RECEIPT_BOUND:\n",
     "        if leaf in RECEIPT_BOUND and not real:\n",
     ("case_mb11_git_allow_hand_edit", "case_mb15_effective_narrowing_hides_raw")),
    ("judge_change drops the raw comparison", "        if leaf in RECEIPT_BOUND:\n",
     "        if leaf in RECEIPT_BOUND and real:\n", ("case_mb19_change_never_confirms",)),
    ("any applied record for the key confirms a raw widening",
     '        "machine": (backed is not None, setting["why"]),',
     '        "machine": (any(r.get("key") == crew_gitallow.KEY and r.get("state") == "applied"'
     ' for r in crew_humanonly.all_records(store)[0]), setting["why"]),',
     ("case_mb11_git_allow_hand_edit",)),
    ("the outcome is the effective result alone",
     '        if _ORDER[outcome] > _ORDER[row["outcome"]]:', "        if False:",
     ("case_mb15_effective_narrowing_hides_raw",)),
    ("raw absent normalised to absent, not the silent default",
     "    value = block.get(key)\n    if value is None:\n        return True",
     '    value = block.get(key)\n    if value is None:\n        return "absent"',
     ("case_ma6_silent_default_control",)),
    ("the baseline advances over an unhonoured raw widening",
     '    if advance and result["status"] == FREE and not _has_unknown(now):',
     '    if advance and all(r["outcome"] != WIDENING or r["leaf"] in RECEIPT_BOUND\n'
     '                       for r in result["leaves"]) and not _has_unknown(now):',
     ("case_mb11_git_allow_hand_edit",)),
    ("the baseline advances on a widening",
     '    if advance and result["status"] == FREE and not _has_unknown(now):',
     "    if advance and not _has_unknown(now):",
     ("case_mb12_init_refuses_a_widening", "case_mb18_confirmation_gap")),
    ("the drift check reads only what was added, like a file diff",
     "    if before == after:\n        return UNCHANGED",
     '    if before == after or after in (None, [], {}, "off", False):\n        return UNCHANGED',
     ("case_mb3_whole_file_replaced", "case_mb4_whole_file_deleted")),
    ("the guard rows read by precedence (resolve_config)",
     '    row = crew_config.resolve_ratcheted(ctx["root"], f"guards.{name}", ctx["machine"])\n'
     '    return row["effective"]',
     '    merged = crew_config.resolve_config(ctx["root"])\n'
     '    return crew_guards.layer_guard_value(merged, name) or crew_guards.GUARD_DEFAULTS[name]',
     ("case_differential",)),
    ("the humanOnly rows read by precedence (resolve_config)",
     '        policy[dotted] = answer["humanOnly"]',
     '        policy[dotted] = crew_config.resolve_config(root).get("humanOnly", {}).get(key)'
     ' is not False',
     ("case_differential_with_receipts",)),
    ("the guards.overrides row is dropped", '    "guards.overrides": ("derived", "guards"),\n',
     "", ("case_coverage",)),
    ("the twelve guard leaves are dropped", "LEAVES = GUARD_LEAVES + (", "LEAVES = (",
     ("case_coverage",)),
    ("scope.mode order reversed", '("enum-order", ("block", "auto", "report", "off"))',
     '("enum-order", ("off", "report", "auto", "block"))', ("case_mb16_scope_mode",)),
    ("judge_change reads before from the real path",
     "            root, machine = _materialise(os.path.join(scratch, side), layers)\n",
     "            root, machine = _materialise(os.path.join(scratch, side), layers) \\\n"
     '                if side == "after" else (tempfile.gettempdir(), '
     "crew_state.GLOBAL_CONFIG_PATH)\n",
     ("case_ma8_same_route_both_sides",)),
)


def _variant(old, new):
    text = source()
    assert text.count(old) == 1, f"mutation target moved: {old!r}"
    name = "crew_protected_mutant"
    module = types.ModuleType(name)
    module.__file__ = MODULE
    sys.modules[name] = module
    try:
        exec(compile(text.replace(old, new), name, "exec"),  # pylint: disable=exec-used
             module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.mark.parametrize("label,old,new,cases", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_a_weakened_comparator_is_caught(label, old, new, cases, tmp_path, monkeypatch):
    mutant = _variant(old, new)
    for index, name in enumerate(cases):
        world = World(tmp_path / f"w{index}", monkeypatch)
        try:
            globals()[name](mutant, world)  # every case, defined by now
        except AssertionError:
            continue  # red for the reason the case asserts, not a crash
        pytest.fail(f"{label}: {name} stayed green against the mutant")
