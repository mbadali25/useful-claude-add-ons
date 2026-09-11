"""Tests for routine.py orchestration (Task 15).

Every real scanner is faked out through the `registry` parameter - no test
here ever invokes nuclei, zap, nikto, nmap, testssl, trivy, depcheck, checkov
or sqlmap as a subprocess. The point of this suite is the four run-manifest
statuses (`ran`, `skipped-missing`, `skipped-active`, `error:<reason>`) and
the exact strings/objects passed across the adapter boundary, not scanner
behavior itself - that belongs to Tasks 5-13's own per-adapter tests.
"""
import json

import pytest

import routine
from scanners import base


class FakeAdapter:
    """A minimal stand-in satisfying the adapter protocol (base.py's
    docstring contract: NAME/KINDS/ACTIVE/ACTIVE_OPTS/DEFAULT_ENABLED plus
    is_available/run/parse). Behavior is injected per-instance so each test
    scripts exactly the path it is checking.
    """

    def __init__(self, name, kinds, active=False, active_opts=None,
                 default_enabled=True, available=True, run_fn=None,
                 findings=None, parse_errors_fn=None):
        self.NAME = name
        self.KINDS = kinds
        self.ACTIVE = active
        self.ACTIVE_OPTS = active_opts or []
        self.DEFAULT_ENABLED = default_enabled
        self._available = available
        self._run_fn = run_fn
        self._findings = findings if findings is not None else []
        self._parse_errors_fn = parse_errors_fn
        self.run_calls = []
        self.parse_calls = []

    def is_available(self):
        return self._available

    def run(self, target, outdir, opts):
        self.run_calls.append((target, outdir, opts))
        return self._run_fn(target, outdir, opts)

    def parse(self, raw_path, target, **kw):
        self.parse_calls.append((raw_path, target, kw))
        return [dict(f, target=target) for f in self._findings]

    def parse_errors(self, raw_path, target):
        if self._parse_errors_fn:
            return self._parse_errors_fn(raw_path, target)
        return []


class FakeRegistry:
    def __init__(self, adapters, kind_defaults):
        self.ADAPTERS = {a.NAME: a for a in adapters}
        self.KIND_DEFAULTS = kind_defaults

    def get(self, name):
        return self.ADAPTERS[name]


def _finding(tool, rule_id, severity=2):
    return {
        "template_id": "%s:%s" % (tool, rule_id), "name": rule_id,
        "severity": severity, "severity_name": "medium", "type": "",
        "timestamp": "", "host": "", "matched_at": "", "cve": [], "cvss": "",
        "description": "", "remediation": "", "reference": [], "tags": [],
        "tool": tool, "target": "",
    }


def _ok(raw_path="raw-output"):
    def _run(target, outdir, opts):
        return raw_path, base.ToolResult(0, "", "", False)
    return _run


def _raises(message):
    def _run(target, outdir, opts):
        raise RuntimeError(message)
    return _run


def _times_out():
    def _run(target, outdir, opts):
        return None, base.ToolResult(-1, "", "", True)
    return _run


def _declines_without_confirm():
    def _run(target, outdir, opts):
        if not opts.get("confirm"):
            return None, base.ToolResult(None, "", "declined: no confirm token", False)
        return "sqlmap-session", base.ToolResult(0, "", "", False)
    return _run


@pytest.fixture
def manifest():
    return routine.Manifest(
        authorized_by="THDDEV-0000 - test harness",
        targets=[
            routine.Target(name="site-a", kind="web",
                            url="https://a.example/x?id=1",
                            options={"sqlmap": True}),
            routine.Target(name="site-b", kind="web",
                            url="https://b.example/"),
        ],
    )


@pytest.fixture
def fake_registry():
    nuclei = FakeAdapter("nuclei", ["web", "host"],
                         run_fn=_ok("nuclei-raw"),
                         findings=[_finding("nuclei", "tpl-1")])
    zap = FakeAdapter("zap", ["web"], active_opts=["zap_active"],
                      run_fn=_raises("zap AF plan failed to launch"))
    nikto = FakeAdapter("nikto", ["web"], available=False)
    nmap = FakeAdapter("nmap", ["web", "host"], active_opts=["nmap_vuln"],
                       run_fn=_ok("nmap-raw"))
    testssl = FakeAdapter("testssl", ["web", "host"], run_fn=_times_out())
    sqlmap = FakeAdapter("sqlmap", ["web"], active=True, default_enabled=False,
                        run_fn=_declines_without_confirm())

    return FakeRegistry(
        [nuclei, zap, nikto, nmap, testssl, sqlmap],
        {"web": ["nuclei", "zap", "nikto", "nmap", "testssl"]},
    )


# ---------------------------------------------------------------------------
# The four statuses - each gets its own test (plan Task 15).
# ---------------------------------------------------------------------------

def test_missing_tool_is_recorded_as_skipped_not_silently_dropped(
        manifest, fake_registry, tmp_path):
    rm = routine.run_routine(manifest, tmp_path, registry=fake_registry)
    assert rm.status("site-a", "nikto") == "skipped-missing"


def test_active_tool_not_opted_in_is_skipped_with_its_own_status(
        manifest, fake_registry, tmp_path):
    rm = routine.run_routine(manifest, tmp_path, registry=fake_registry)
    assert rm.status("site-a", "sqlmap") == "skipped-active"


def test_a_tool_that_raises_records_an_error_and_the_run_continues(
        manifest, fake_registry, tmp_path):
    rm = routine.run_routine(manifest, tmp_path, registry=fake_registry)
    assert rm.status("site-a", "zap").startswith("error")
    assert rm.status("site-a", "nuclei") == "ran"


def test_a_tool_that_times_out_records_error_timeout(
        manifest, fake_registry, tmp_path):
    rm = routine.run_routine(manifest, tmp_path, registry=fake_registry)
    assert rm.status("site-a", "testssl") == "error:timeout"


def test_findings_are_combined_with_tool_and_target_set(
        manifest, fake_registry, tmp_path):
    routine.run_routine(manifest, tmp_path, registry=fake_registry)
    lines = (tmp_path / "findings.jsonl").read_text().splitlines()
    recs = [json.loads(l) for l in lines]
    assert {r["target"] for r in recs} == {"site-a", "site-b"}
    assert all(r["tool"] for r in recs)


def test_sqlmap_does_not_run_without_the_confirm_token(
        manifest, fake_registry, tmp_path):
    rm = routine.run_routine(manifest, tmp_path, registry=fake_registry)
    assert rm.status("site-a", "sqlmap") != "ran"


def test_sqlmap_runs_once_confirm_is_supplied(manifest, fake_registry, tmp_path):
    rm = routine.run_routine(manifest, tmp_path, registry=fake_registry,
                             confirm="THDDEV-0000-approved")
    assert rm.status("site-a", "sqlmap") == "ran"


def test_unopted_target_never_gets_a_sqlmap_cell_at_all(
        manifest, fake_registry, tmp_path):
    # site-b never set options["sqlmap"], so resolve_adapters() (Task 14)
    # excludes it outright - there is no cell to be skipped-active *or* ran.
    rm = routine.run_routine(manifest, tmp_path, registry=fake_registry)
    assert rm.status("site-b", "sqlmap") is None


# ---------------------------------------------------------------------------
# The adapter contract this module consumes - regressions here would be
# invisible to the four-statuses tests above but break every downstream tool.
# ---------------------------------------------------------------------------

def test_run_receives_the_location_string_not_the_target_object(
        manifest, fake_registry, tmp_path):
    routine.run_routine(manifest, tmp_path, registry=fake_registry)
    nuclei = fake_registry.ADAPTERS["nuclei"]
    locations = [call[0] for call in nuclei.run_calls]
    assert "https://a.example/x?id=1" in locations
    assert "https://b.example/" in locations
    assert all(isinstance(loc, str) for loc in locations)


def test_parse_receives_the_manifest_name_not_the_location(
        manifest, fake_registry, tmp_path):
    routine.run_routine(manifest, tmp_path, registry=fake_registry)
    nuclei = fake_registry.ADAPTERS["nuclei"]
    names = [call[1] for call in nuclei.parse_calls]
    assert set(names) == {"site-a", "site-b"}


def test_parse_errors_are_folded_into_the_run_manifest_cell(
        manifest, fake_registry, tmp_path):
    testssl = fake_registry.ADAPTERS["testssl"]
    testssl._run_fn = _ok("testssl-raw")
    testssl._parse_errors_fn = lambda raw_path, target: [
        {"tool": "testssl", "target": target, "id": "TLS1", "severity": "FATAL",
         "message": "connection refused"}]

    rm = routine.run_routine(manifest, tmp_path, registry=fake_registry)
    cell = rm.cell("site-a", "testssl")
    assert cell["status"] == "ran"
    assert cell["errors"] and cell["errors"][0]["severity"] == "FATAL"


def test_unknown_active_opts_key_does_not_crash_a_bare_adapter(
        manifest, fake_registry, tmp_path):
    # A future adapter that forgot ACTIVE_OPTS entirely must not take the
    # whole run down with an AttributeError (plan Tasks 5-13: read every
    # adapter constant defensively).
    nuclei = fake_registry.ADAPTERS["nuclei"]
    del nuclei.ACTIVE_OPTS
    rm = routine.run_routine(manifest, tmp_path, registry=fake_registry)
    assert rm.status("site-a", "nuclei") == "ran"


# ---------------------------------------------------------------------------
# Mode recording for the two-mode adapters (nmap safe/vuln, zap
# baseline/active) - a bare "ran" would imply coverage a safe-only or
# baseline-only scan never attempted (plan Global Constraints).
# ---------------------------------------------------------------------------

def test_nmap_records_safe_mode_when_vuln_was_not_requested(
        manifest, fake_registry, tmp_path):
    rm = routine.run_routine(manifest, tmp_path, registry=fake_registry)
    assert rm.status("site-b", "nmap") == "ran(safe)"


def test_nmap_records_safe_plus_vuln_mode_when_opted_in(fake_registry, tmp_path):
    m = routine.Manifest(
        authorized_by="THDDEV-0000 - test harness",
        targets=[routine.Target(name="site-c", kind="web",
                                url="https://c.example/",
                                options={"nmap_vuln": True})],
    )
    rm = routine.run_routine(m, tmp_path, registry=fake_registry)
    assert rm.status("site-c", "nmap") == "ran(safe+vuln)"


# ---------------------------------------------------------------------------
# trivy's two-kind threading: routine must pass opts["kind"] to run() and
# kind= to parse() since a plain-string target carries no .kind of its own
# (spec 13.14 / trivy.py's own _resolve_kind).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# run-manifest.json's on-disk schema - Tasks 16/17 (coverage table) read this
# file directly, so its shape is a cross-agent contract in its own right.
# ---------------------------------------------------------------------------

def test_run_manifest_json_has_the_documented_schema(manifest, fake_registry, tmp_path):
    rm = routine.run_routine(manifest, tmp_path, registry=fake_registry)
    on_disk = json.loads((tmp_path / "run-manifest.json").read_text())

    assert on_disk["authorized_by"] == manifest.authorized_by
    assert "generated_at" in on_disk

    by_key = {(c["target"], c["tool"]): c for c in on_disk["cells"]}
    nuclei_cell = by_key[("site-a", "nuclei")]
    assert nuclei_cell["status"] == "ran"
    assert nuclei_cell["mode"] is None
    assert nuclei_cell["error"] is None
    assert isinstance(nuclei_cell["duration_s"], float)
    assert nuclei_cell["count"] == 1
    assert nuclei_cell["errors"] == []

    nmap_cell = by_key[("site-b", "nmap")]
    assert nmap_cell["status"] == "ran(safe)"
    assert nmap_cell["mode"] == "safe"

    zap_cell = by_key[("site-a", "zap")]
    assert zap_cell["status"].startswith("error:")
    assert zap_cell["mode"] is None
    assert zap_cell["error"] == "zap AF plan failed to launch"

    testssl_cell = by_key[("site-a", "testssl")]
    assert testssl_cell["status"] == "error:timeout"
    assert testssl_cell["error"] == "timeout"


def test_trivy_kind_is_threaded_through_run_opts_and_parse_kwarg(tmp_path):
    trivy = FakeAdapter("trivy", ["deps", "iac"], run_fn=_ok("trivy-raw"))
    checkov = FakeAdapter("checkov", ["iac"], run_fn=_ok("checkov-raw"))
    reg = FakeRegistry([trivy, checkov], {"iac": ["checkov", "trivy"]})

    m = routine.Manifest(
        authorized_by="THDDEV-0000 - test harness",
        targets=[routine.Target(name="infra", kind="iac", path="../infra")],
    )
    routine.run_routine(m, tmp_path, registry=reg)

    _, _, opts = trivy.run_calls[0]
    assert opts["kind"] == "iac"
    _, _, parse_kwargs = trivy.parse_calls[0]
    assert parse_kwargs.get("kind") == "iac"
