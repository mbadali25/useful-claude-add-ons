"""crew_config's machine-only `unattendedCloud` block (T-0044), split out of
test_crew_config.py to keep that module under pylint's 3,400-line cap."""
import json

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_fixtures
import crew_state


# --- T-0044: the machine-only `unattendedCloud` block -----------------------
#
# Which cloud identity an unattended run holds is the machine owner's answer
# and nobody else's: a repo travels inside a clone written by someone else, so
# a repo copy is IGNORED (not merged, not ratcheted) and reported as such. The
# defaults name no identity, and `crew_unattended.py` refuses every launch
# until the owner names one.

def test_unattended_cloud_defaults_grant_nothing():
    block = crew_config.default_global_config()["unattendedCloud"]
    assert block == {"aws": {
        "readOnly": {"profile": None, "identity": None, "region": None},
        "nonProd": {}}}
    assert crew_state.UNATTENDED_CLOUD_DEFAULTS == block
    assert crew_state.UNATTENDED_CLOUD_MACHINE_ONLY == ("unattendedCloud",)
    leaves = crew_config.leaf_paths(crew_config.default_global_config())
    # `nonProd` is an open table, so it is one leaf, like `dev.roles`.
    assert [p for p in leaves if p.startswith("unattendedCloud.")] == [
        "unattendedCloud.aws.readOnly.profile",
        "unattendedCloud.aws.readOnly.identity",
        "unattendedCloud.aws.readOnly.region",
        "unattendedCloud.aws.nonProd"]


def test_unattended_cloud_is_global_only():
    assert "unattendedCloud" in crew_config.default_global_config()
    assert "unattendedCloud" not in crew_config.default_config()
    assert crew_config.is_global_path("unattendedCloud.aws.readOnly.identity")


def test_repo_unattended_cloud_is_ignored(tmp_path):
    """A repo naming its own identity must change nothing: not the resolved
    config, not the explain table's value, and never `source: repo`."""
    machine = "arn:aws:sts::111111111111:assumed-role/ReadOnly/"
    forged = "arn:aws:sts::111111111111:assumed-role/AdministratorAccess/"
    global_path = tmp_path / "global-config.json"
    global_path.write_text(json.dumps({"unattendedCloud": {"aws": {
        "readOnly": {"profile": "ro", "identity": machine}}}}),
        encoding="utf-8")
    root = tmp_path / "repo"
    crew_fixtures.make_repo(tmp_path, config={
        "schema": crew_state.SCHEMA_CURRENT,
        "unattendedCloud": {"aws": {"readOnly": {
            "profile": "admin", "identity": forged, "region": "us-east-1"}}}},
        git=False)

    rows = {r["path"]: r for r in
            crew_config.explain_config(str(root), path=str(global_path))}
    ident = rows["unattendedCloud.aws.readOnly.identity"]
    assert ident["value"] == machine and ident["source"] == "global"
    assert ident["repoIgnored"] == forged
    region = rows["unattendedCloud.aws.readOnly.region"]
    assert region["value"] is None and region["source"] == "default"
    assert region["repoIgnored"] == "us-east-1"
    assert all(r["source"] not in ("repo", "repo+global") for p, r in
               rows.items() if p.startswith("unattendedCloud."))


def test_resolve_config_drops_a_repo_unattended_cloud(tmp_path, monkeypatch):
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH",
                        str(tmp_path / "absent.json"))
    root = tmp_path / "repo"
    crew_fixtures.make_repo(tmp_path, config={
        "schema": crew_state.SCHEMA_CURRENT,
        "unattendedCloud": {"aws": {"readOnly": {"identity": "x/"}}}},
        git=False)
    assert "unattendedCloud" not in crew_config.resolve_config(str(root))


@pytest.mark.parametrize("block,needle", [
    ({"aws": {"readOnly": {"identity": "arn:aws:sts::1:assumed-role/RO"}}},
     "end in `/`"),
    # T-0044 port review r6 BLOCK: one named role, never every role.
    ({"aws": {"readOnly": {"identity": "arn:aws:sts::111111111111:assumed-role/"}}},
     "must name one role"),
    ({"aws": {"nonProd": []}}, "nonProd"),
    ({"aws": {"readOnly": {"profile": 7}}}, "profile"),
    ({"aws": {}, "azure": {}}, "azure"),
    ({"aws": {"nonProd": {"dev": {"profile": "d"}}}}, "identity"),
    ({"aws": {"readOnly": []}}, "readOnly"),
    ("aws", "not an object"),
    ({"aws": None}, "aws"),
])
def test_unattended_cloud_block_problem(block, needle):
    problem = crew_config.unattended_cloud_block_problem(block)
    assert problem and needle in problem, problem


def test_unattended_cloud_block_problem_accepts_the_shapes_it_must():
    ident = "arn:aws:sts::111111111111:assumed-role/ReadOnly/"
    for block in (crew_state.UNATTENDED_CLOUD_DEFAULTS,
                  {"aws": {"readOnly": {"profile": "ro", "identity": ident,
                                        "region": "eu-west-1"}}},
                  {"aws": {"nonProd": {"dev": {"profile": "d",
                                               "identity": ident}}}}):
        assert crew_config.unattended_cloud_block_problem(block) == ""
