"""Tests for routine.py's manifest parsing and authorization gate (Task 14).

Fully offline: load_manifest() only reads YAML off disk and validates it -
no subprocess, no network, no scanner registry involved.
"""
import pytest

import routine


def test_missing_authorized_by_is_refused(fixture):
    with pytest.raises(routine.AuthorizationError):
        routine.load_manifest(fixture("manifest-no-auth.yaml"))


def test_empty_authorized_by_is_refused(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text('authorized_by: ""\ntargets: [{name: a, kind: web, url: "http://a"}]\n')
    with pytest.raises(routine.AuthorizationError):
        routine.load_manifest(p)


def test_kind_drives_the_default_adapter_list(fixture):
    m = routine.load_manifest(fixture("manifest-valid.yaml"))
    web = [t for t in m.targets if t.kind == "web"][0]
    assert routine.resolve_adapters(web) == ["nuclei", "zap", "nikto", "nmap", "testssl"]


def test_sqlmap_is_absent_unless_opted_in(fixture):
    m = routine.load_manifest(fixture("manifest-valid.yaml"))
    web = [t for t in m.targets if t.kind == "web"][0]
    assert "sqlmap" not in routine.resolve_adapters(web)
    web.options["sqlmap"] = True
    assert "sqlmap" in routine.resolve_adapters(web)


def test_unknown_kind_is_an_error_not_an_empty_list(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text('authorized_by: "me"\ntargets: [{name: a, kind: spaceship}]\n')
    with pytest.raises(ValueError, match="spaceship"):
        routine.load_manifest(p)


# --- Additional coverage beyond the plan's skeleton ------------------------

def test_iac_and_deps_targets_get_their_own_kind_defaults(fixture):
    m = routine.load_manifest(fixture("manifest-valid.yaml"))
    iac = [t for t in m.targets if t.kind == "iac"][0]
    deps = [t for t in m.targets if t.kind == "deps"][0]
    assert routine.resolve_adapters(iac) == ["checkov", "trivy"]
    assert routine.resolve_adapters(deps) == ["trivy", "depcheck"]


def test_tools_override_replaces_the_kind_default_entirely(fixture):
    m = routine.load_manifest(fixture("manifest-valid.yaml"))
    web = [t for t in m.targets if t.kind == "web"][0]
    web.tools = ["nuclei"]
    assert routine.resolve_adapters(web) == ["nuclei"]


def test_missing_authorized_by_key_entirely_is_refused(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text('targets: [{name: a, kind: web, url: "http://a"}]\n')
    with pytest.raises(routine.AuthorizationError):
        routine.load_manifest(p)


def test_report_header_can_restate_the_authorization_statement(fixture):
    # spec section 8: "The report header restates it" - so the full string,
    # not just a truthy flag, must survive parsing unchanged.
    m = routine.load_manifest(fixture("manifest-valid.yaml"))
    assert m.authorized_by.startswith("THDDEV-0000")
