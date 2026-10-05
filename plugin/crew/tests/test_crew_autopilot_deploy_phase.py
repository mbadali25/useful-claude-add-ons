"""autopilot's deploy phase after the merge (L-0649): `crew_autopilot_deploy.after_merge`.

Unit cases call `after_merge` on a repository holding `.crew/verify.json`
(github entries) and `.crew/config.json` (`environments.nonProd` and
`environments.workflows`, which T-0009's classifier reads), with a stand-in
`deploy_allowed` that records its calls; two integration cases go through
`crew_autopilot.next_phase` with the ship tests' merged-PR fixture. The phase
is read-only: no `gh`, no `crew_ghdeploy.py` subcommand, nothing written.
"""
import json

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_autopilot
import crew_autopilot_deploy
import crew_config
import crew_ship
import crew_state
import test_crew_autopilot_ship as ship
from review_fixtures import git

SHA = "a" * 40
CLOSED = {"phase": "closed", "stop": True, "reason": "PR #7 is merged (https://x/7)"}


def _entry(target, sha_input=True):
    entry = {"workflow": "deploy.yml", "ref": "main", "inputs": {"target": target}}
    if sha_input:
        entry["shaInput"] = "sha"
    return entry


def _env(target, **extra):
    entry = extra.pop("entry", None) or _entry(target)
    prefix = f"gh workflow run deploy.yml --ref main -f target={entry['inputs']['target']}"
    return dict({"deploy": [prefix], "github": entry, "rollback": "none",
                 "rollbackReason": "fixture"}, **extra)


_MAP = {"staging": _env("staging"), "production": _env("prod")}


def _repo(tmp_path, monkeypatch, envs=None, workflows=None, non_prod=("staging",),
          rows=None, raw=None):
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    (root / ".work").mkdir()
    text = raw if raw is not None else json.dumps({"environments": envs or _MAP})
    (root / ".crew" / "verify.json").write_text(text, encoding="utf-8")
    (root / ".crew" / "config.json").write_text(json.dumps({"environments": {
        "nonProd": list(non_prod),
        "workflows": workflows or {"deploy.yml": "input:target"}}}), encoding="utf-8")
    glob = tmp_path / "global.json"
    glob.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(glob))
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(glob))
    if rows:
        (root / ".work" / "PROMOTIONS.md").write_text(
            "| when | env | sha | smoke | regression | verify | by |\n|---|---|---|---|---|---|---|\n"
            + "".join(f"| t | {env} | {SHA} | {a} | {b} | {c} | x |\n" for env, a, b, c in rows),
            encoding="utf-8")
    return str(root)


def _answer(phase, stop, reason, command=""):
    return {"phase": phase, "stop": stop, "reason": reason, "command": command}


class Allowed:  # pylint: disable=too-few-public-methods
    """`deploy_allowed`'s stand-in: answers `verdict` and records the calls."""

    def __init__(self, verdict="allow", reason="autopilot.deploy=nonprod allows nonProd",
                 report=""):
        self.result = {"verdict": verdict, "reason": reason, "report": report}
        self.calls = []

    def __call__(self, top, env, klass):
        self.calls.append((env, klass))
        return dict(self.result)


def _after(root, allowed=None, deploy="nonprod", closed=None):
    """`after_merge` with `merged_phase` answering `closed` (default: the PR
    merged this HEAD) for a PR whose merged head is SHA."""
    saved = crew_ship.merged_phase
    crew_ship.merged_phase = lambda *_a: dict(closed or CLOSED)
    try:
        return crew_autopilot_deploy.after_merge(root, "T-1-build", {"headRefOid": SHA}, _answer,
                                                 deploy, allowed or Allowed())
    finally:
        crew_ship.merged_phase = saved


# --- must-block: deploy-target ------------------------------------------------

_TARGET_BLOCKS = {
    "require-human-target": ({"envs": {"staging": _env("staging", requireHuman=True)}},
                             "require-human-target"),
    "no-sha-input": ({"envs": {"staging": _env("staging", entry=_entry("staging", False))}},
                     "no-sha-input"),
    "class-unknown": ({"workflows": {"deploy.yml": "input:region"}}, "unknown-environment"),
    "unmapped-workflow": ({"workflows": {"other.yml": "staging"}}, "unmapped-workflow"),
    "nonprod-name-dispatches-prod": ({"workflows": {"deploy.yml": "production"}},
                                     "class-mismatch"),
    "verify-json-unreadable": ({"raw": "{not json"}, "verify-json-unreadable"),
    "entry-refused": ({"envs": {"staging": dict(_env("staging"), deploy=["x"])}},
                      "deploy-prefix-mismatch"),
}


@pytest.mark.parametrize("name", sorted(_TARGET_BLOCKS))
def test_deploy_target_stops(tmp_path, monkeypatch, name):
    kwargs, why = _TARGET_BLOCKS[name]
    root = _repo(tmp_path, monkeypatch, **kwargs)
    allowed = Allowed()
    got = _after(root, allowed)
    assert (got["phase"], got["stop"], got["command"]) == ("deploy-target", True, "")
    assert why in got["reason"], got["reason"]
    assert allowed.calls == []


def test_classifier_raises_is_deploy_target(tmp_path, monkeypatch):
    import crew_dispatch  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path, monkeypatch)

    def boom(*_a):
        raise RuntimeError("classifier exploded")
    monkeypatch.setattr(crew_dispatch, "dispatch_environment", boom)
    got = _after(root)
    assert (got["phase"], got["stop"]) == ("deploy-target", True)
    assert "classifier-failed" in got["reason"]


@pytest.mark.parametrize("verdict,reason,report", [
    ("ask", "autopilot.deploy is none", ""),
    ("refuse", "an emergency may be active (.crew/incident.json exists)", ""),
    ("ask", "production needs all", "unattended production: production ask - x"),
], ids=["deploy-allowed-ask", "deploy-allowed-refuse", "report-printed"])
def test_deploy_allowed_anything_but_allow_stops(tmp_path, monkeypatch, verdict, reason, report):
    """Only the exact verdict `allow` proceeds; the reason and every
    non-empty report are printed."""
    root = _repo(tmp_path, monkeypatch)
    got = _after(root, Allowed(verdict, reason, report))
    assert (got["phase"], got["stop"]) == ("deploy-target", True)
    assert reason in got["reason"] and verdict in got["reason"]
    assert report in got["reason"]


def test_head_not_pr_head_stops_before_the_deploy_phase(tmp_path, monkeypatch):
    """`merged_phase`'s own stop (a commit after the merge) passes through:
    the deploy phase never names /crew:promote for it."""
    root = _repo(tmp_path, monkeypatch)
    stop = {"phase": "ship", "stop": True, "reason": "has commits after PR #7 merged"}
    allowed = Allowed()
    got = _after(root, allowed, closed=stop)
    assert got == stop and allowed.calls == []


# --- must-block: failed-deploy ------------------------------------------------

@pytest.mark.parametrize("cells", [("not-run", "not-run", "not-run"), ("pass", "FAIL", "pass")],
                         ids=["not-run", "fail"])
def test_row_not_pass_is_failed_deploy(tmp_path, monkeypatch, cells):
    root = _repo(tmp_path, monkeypatch, rows=[("staging",) + cells])
    allowed = Allowed()
    for _ in range(2):  # never names /crew:promote again for that sha
        got = _after(root, allowed)
        assert (got["phase"], got["stop"], got["command"]) == ("failed-deploy", True, "")
    assert allowed.calls == []


def test_a_later_pass_row_clears_a_failure(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, rows=[("staging", "pass", "FAIL", "pass"),
                                               ("staging", "pass", "pass", "pass")],
                 envs={"staging": _env("staging")})
    got = _after(root)
    assert (got["phase"], got["stop"]) == ("closed", True)


# --- must-allow ---------------------------------------------------------------

def test_deploy_none_default_is_closed_unchanged(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    allowed = Allowed()
    assert _after(root, allowed, deploy="none") == CLOSED
    assert allowed.calls == []


@pytest.mark.parametrize("map_text", [None, json.dumps({"environments": {
    "staging": {"deploy": "./deploy.sh", "rollback": "none", "rollbackReason": "f"}}})],
                         ids=["no-map", "no-github-env"])
def test_no_github_env_is_closed_and_says_promotion_is_a_persons(tmp_path, monkeypatch,
                                                                 map_text):
    root = _repo(tmp_path, monkeypatch, raw=map_text or "")
    if map_text is None:
        (tmp_path / "repo" / ".crew" / "verify.json").unlink()
    got = _after(root)
    assert (got["phase"], got["stop"]) == ("closed", True)
    assert "promotion is a person's" in got["reason"]


def test_nonprod_deploy_phase(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    allowed = Allowed()
    got = _after(root, allowed)
    assert (got["phase"], got["stop"], got["command"]) == ("deploy", False, "/crew:promote staging")
    assert allowed.calls == [("staging", "nonProd")]


def test_after_pass_row_is_closed_naming_env_and_sha(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, envs={"staging": _env("staging")},
                 rows=[("staging", "pass", "pass", "pass")])
    got = _after(root)
    assert (got["phase"], got["stop"]) == ("closed", True)
    assert "staging has an all-pass row for aaaaaaa" in got["reason"]


def test_prod_under_all_is_named_only_after_every_nonprod_passes(tmp_path, monkeypatch):
    """Production is the last target even when the map lists it first; its
    class goes to deploy_allowed, which decides (both layers' prodUnattended
    and cloudGuard: block are its rows, T-0072)."""
    envs = {"production": _env("prod"), "staging": _env("staging")}
    root = _repo(tmp_path, monkeypatch, envs=envs)
    allowed = Allowed()
    got = _after(root, allowed, deploy="all")
    assert got["command"] == "/crew:promote staging"
    root2 = _repo(tmp_path / "b", monkeypatch, envs=envs, rows=[("staging", "pass", "pass", "pass")])
    allowed = Allowed()
    got = _after(root2, allowed, deploy="all")
    assert (got["phase"], got["command"]) == ("deploy", "/crew:promote production")
    assert allowed.calls == [("production", "prod")]
    got = _after(root2, Allowed("ask", "environments.prodUnattended is not true"), deploy="all")
    assert got["phase"] == "deploy-target"


def test_prod_under_all_with_the_real_deploy_allowed(tmp_path, monkeypatch):
    """The real `deploy_allowed`: missing `prodUnattended` in the machine
    layer asks, so production is deploy-target."""
    envs = {"staging": _env("staging"), "production": _env("prod")}
    root = _repo(tmp_path, monkeypatch, envs=envs, rows=[("staging", "pass", "pass", "pass")])
    cfg = json.loads((tmp_path / "repo" / ".crew" / "config.json").read_text(encoding="utf-8"))
    cfg["autopilot"] = {"mode": "plan", "deploy": "all"}
    cfg["environments"]["prodUnattended"] = True
    cfg["guards"] = {"cloudGuard": "block"}
    (tmp_path / "repo" / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    got = _after(root, crew_autopilot.deploy_allowed, deploy="all")
    assert (got["phase"], got["stop"]) == ("deploy-target", True)
    assert "prodUnattended" in got["reason"]


# --- through `next` -----------------------------------------------------------

def _merged(tmp_path, monkeypatch, **block):
    root = ship._done_ticket(tmp_path, **block)  # pylint: disable=protected-access
    head = git(root, "rev-parse", "HEAD").strip()
    monkeypatch.setattr(crew_ship, "_run_gh",
                        ship.FakeGh(pr_view=ship._view(ship._pr("MERGED", head=head))))  # pylint: disable=protected-access
    return root, head


def test_next_with_deploy_none_is_closed_as_t0011_leaves_it(tmp_path, monkeypatch):
    root, _head = _merged(tmp_path, monkeypatch)
    got = crew_autopilot.next_phase(str(root), ship.T)
    assert (got["phase"], got["stop"], got["reason"]) == (
        "closed", True, "PR #7 is merged (https://example.test/pull/7)")


def test_next_with_deploy_nonprod_names_promote(tmp_path, monkeypatch):
    root, _head = _merged(tmp_path, monkeypatch, deploy="nonprod")
    cfg = json.loads((root / ".crew" / "config.json").read_text(encoding="utf-8"))
    cfg["environments"] = {"nonProd": ["staging"], "workflows": {"deploy.yml": "input:target"}}
    (root / ".crew" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (root / ".crew" / "verify.json").write_text(json.dumps({"environments": {
        "staging": _env("staging")}}), encoding="utf-8")
    got = crew_autopilot.next_phase(str(root), ship.T)
    assert (got["phase"], got["stop"], got["command"]) == ("deploy", False,
                                                           "/crew:promote staging")


def test_a_crash_reading_the_targets_is_deploy_target(tmp_path, monkeypatch):
    """Anything the target read raises is could-not-tell, never closed."""
    import crew_ghdeploy  # pylint: disable=import-outside-toplevel
    root = _repo(tmp_path, monkeypatch)

    def boom(*_a):
        raise RuntimeError("validator exploded")
    monkeypatch.setattr(crew_ghdeploy, "validated", boom)
    got = _after(root)
    assert (got["phase"], got["stop"]) == ("deploy-target", True)
    assert "RuntimeError" in got["reason"]



def test_a_later_unsafe_target_does_not_block_an_earlier_one(tmp_path, monkeypatch):
    """L-0649 r1: staging is eligible; production later needs a human. The
    phase names staging; production's problem stops only once it is next."""
    envs = {"staging": _env("staging"), "production": _env("prod", requireHuman=True)}
    root = _repo(tmp_path, monkeypatch, envs=envs)
    got = _after(root, deploy="all")
    assert (got["phase"], got["command"]) == ("deploy", "/crew:promote staging")
    root = _repo(tmp_path / "b", monkeypatch, envs=envs,
                 rows=[("staging", "pass", "pass", "pass")])
    got = _after(root, deploy="all")
    assert (got["phase"], got["stop"]) == ("deploy-target", True)
    assert "require-human-target: production" in got["reason"]


def test_github_null_is_deploy_target(tmp_path, monkeypatch):
    """L-0649 r1: `github: null` is an entry `check` refuses, never "no
    github environment"."""
    root = _repo(tmp_path, monkeypatch, envs={"staging": dict(_env("staging"), github=None)})
    got = _after(root)
    assert (got["phase"], got["stop"]) == ("deploy-target", True)
    assert "github-shape" in got["reason"]


@pytest.mark.parametrize("form", ["directory", "dangling-symlink"])
def test_an_unreadable_promotions_file_is_deploy_target(tmp_path, monkeypatch, form):
    root = _repo(tmp_path, monkeypatch)
    path = tmp_path / "repo" / ".work" / "PROMOTIONS.md"
    if form == "directory":
        path.mkdir()
    else:
        path.symlink_to(tmp_path / "gone.md")
    got = _after(root)
    assert (got["phase"], got["stop"]) == ("deploy-target", True)
    assert "promotions-unreadable" in got["reason"]
