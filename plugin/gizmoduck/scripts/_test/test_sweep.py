"""sweep.py - scanning every site a repository declares, in one command.

The behaviours pinned here are the ones that were each got wrong once in an
ad-hoc script before this became a plugin command: a module skipped because its
DNS did not resolve, a clean module left with no readable report, and one
module's failure taking the whole sweep down with it.

Nothing here runs a scanner. `run()` is driven with gizmoduck.cmd_scan stubbed,
so these are about the sweep's own contract: what it discovers, where it writes,
what it does when something fails.

Run: pytest scripts/_test/test_sweep.py
"""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sweep  # noqa: E402


DECL = """---
name: "Thing"
url: "https://thing.example.com"
status: "live"
kind: "website"
purpose: "A long prose value: with a colon, an em-dash — and \\"quotes\\" in it."
---

## What it does
Prose.
"""


def _module(root, name, text=DECL, declaration="public-endpoint.md"):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / declaration).write_text(text, encoding="utf-8")
    return d


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------

def test_discovers_every_declaring_module(tmp_path):
    _module(tmp_path, "alpha")
    _module(tmp_path, "beta")
    (tmp_path / "gamma").mkdir()          # no declaration
    found = sweep.discover(str(tmp_path))
    assert [s["module"] for s in found] == ["alpha", "beta"]


def test_fields_survive_prose_values_with_colons(tmp_path):
    """The declarations carry long prose with colons and em-dashes. A strict
    YAML parse fails on files a human wrote correctly, which is why only the
    three scalars are extracted."""
    _module(tmp_path, "alpha")
    site = sweep.discover(str(tmp_path))[0]
    assert site["url"] == "https://thing.example.com"
    assert site["status"] == "live"
    assert site["kind"] == "website"


def test_noise_directories_are_pruned(tmp_path):
    """node_modules holds thousands of directories and no module worth
    scanning; walking it makes discovery take minutes."""
    for noisy in ("node_modules", ".git", ".terraform", "graphify-out"):
        _module(tmp_path / noisy, "vendored")
    _module(tmp_path, "real")
    assert [s["module"] for s in sweep.discover(str(tmp_path))] == ["real"]


def test_declaration_filename_is_configurable(tmp_path):
    _module(tmp_path, "alpha", declaration="endpoint.md")
    assert sweep.discover(str(tmp_path)) == []
    found = sweep.discover(str(tmp_path), declaration="endpoint.md")
    assert [s["module"] for s in found] == ["alpha"]


# --------------------------------------------------------------------------
# run(): the three behaviours learned from real runs
# --------------------------------------------------------------------------

@pytest.fixture
def stub_scan(monkeypatch):
    """Replace cmd_scan with something that writes a findings file, and record
    what it was called with."""
    import gizmoduck as gz
    calls = []

    def _fake(target, out, severity, extra, source=None, with_zap=False,
              with_checkov=False, semgrep_config="p/security-audit"):
        calls.append({"target": target, "out": out, "source": source,
                      "with_zap": with_zap, "with_checkov": with_checkov})
        rec = {"template-id": "t", "type": "http", "host": target,
               "matched-at": target, "timestamp": "",
               "info": {"name": "n", "severity": "high", "description": "",
                        "remediation": "", "reference": [], "tags": [],
                        "classification": {"cve-id": [], "cvss-score": ""}}}
        with io.open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")

    monkeypatch.setattr(gz, "cmd_scan", _fake)
    monkeypatch.setattr(gz, "html_to_pdf", lambda html, path: io.open(
        path, "w", encoding="utf-8").write("pdf"))
    return calls


def test_source_tools_get_the_modules_own_directory(tmp_path, stub_scan, monkeypatch):
    """The endpoint tools take the url; the source tools take that module's
    tree. Passing the repo root instead would scan every module 18 times."""
    d = _module(tmp_path, "alpha")
    monkeypatch.setattr(sweep, "_resolves", lambda h: True)
    sweep.run(str(tmp_path), run_date="2026-01-01")
    assert stub_scan[0]["source"] == str(d)
    assert stub_scan[0]["target"] == "https://thing.example.com"


def test_results_land_in_the_conventional_path(tmp_path, stub_scan, monkeypatch):
    _module(tmp_path, "alpha")
    monkeypatch.setattr(sweep, "_resolves", lambda h: True)
    sweep.run(str(tmp_path), run_date="2026-01-01")
    out = tmp_path / "alpha" / "docs" / "security-scans" / "2026-01-01"
    assert (out / "findings.jsonl").exists()
    for fmt in ("md", "html", "pdf"):
        assert (out / f"report.{fmt}").exists(), f"report.{fmt} missing"


def test_unreachable_endpoint_is_still_scanned(tmp_path, stub_scan, monkeypatch):
    """Dependencies, Terraform and source code do not care whether the endpoint
    resolves. Skipping the module would drop real coverage."""
    _module(tmp_path, "alpha")
    monkeypatch.setattr(sweep, "_resolves", lambda h: False)
    results = sweep.run(str(tmp_path), run_date="2026-01-01")
    assert len(stub_scan) == 1, "an unresolvable host must not skip the module"
    assert results[0]["reachable"] is False
    assert results[0]["scanned"] is True


def test_a_clean_module_still_gets_readable_reports(tmp_path, monkeypatch):
    """Zero findings is a result somebody needs to open and file."""
    import gizmoduck as gz
    _module(tmp_path, "alpha")
    monkeypatch.setattr(sweep, "_resolves", lambda h: True)
    monkeypatch.setattr(gz, "cmd_scan",
                        lambda *a, **k: io.open(a[1], "w", encoding="utf-8").close())
    monkeypatch.setattr(gz, "html_to_pdf", lambda html, path: io.open(
        path, "w", encoding="utf-8").write("pdf"))
    sweep.run(str(tmp_path), run_date="2026-01-01")
    out = tmp_path / "alpha" / "docs" / "security-scans" / "2026-01-01"
    for fmt in ("md", "html", "pdf"):
        assert (out / f"report.{fmt}").exists(), f"clean module missing report.{fmt}"


def test_one_modules_failure_does_not_kill_the_sweep(tmp_path, monkeypatch):
    """cmd_scan exits the process when nuclei fails - right for one scan, fatal
    for a sweep of eighteen."""
    import gizmoduck as gz
    _module(tmp_path, "alpha")
    _module(tmp_path, "beta")
    monkeypatch.setattr(sweep, "_resolves", lambda h: True)
    seen = []

    def _fake(target, out, severity, extra, **kw):
        seen.append(target)
        if len(seen) == 1:
            raise SystemExit("nuclei exited 2 with no findings on stdout")
        io.open(out, "w", encoding="utf-8").close()

    monkeypatch.setattr(gz, "cmd_scan", _fake)
    monkeypatch.setattr(gz, "html_to_pdf", lambda html, path: io.open(
        path, "w", encoding="utf-8").write("pdf"))
    results = sweep.run(str(tmp_path), run_date="2026-01-01")
    assert len(seen) == 2, "the second module must still be scanned"
    notes = {r["module"]: r["note"] for r in results}
    assert "nuclei exited 2" in notes["alpha"]
    assert notes["beta"] == ""


def test_a_module_with_no_url_is_recorded_not_crashed(tmp_path, stub_scan, monkeypatch):
    _module(tmp_path, "alpha", text="---\nname: \"x\"\nstatus: \"planned\"\n---\n")
    monkeypatch.setattr(sweep, "_resolves", lambda h: True)
    results = sweep.run(str(tmp_path), run_date="2026-01-01")
    assert results[0]["scanned"] is False
    assert results[0]["note"] == "no url"
    assert stub_scan == []


def test_optional_tools_are_off_unless_asked(tmp_path, stub_scan, monkeypatch):
    _module(tmp_path, "alpha")
    monkeypatch.setattr(sweep, "_resolves", lambda h: True)
    sweep.run(str(tmp_path), run_date="2026-01-01")
    assert stub_scan[0]["with_zap"] is False
    assert stub_scan[0]["with_checkov"] is False
    stub_scan.clear()
    sweep.run(str(tmp_path), with_zap=True, with_checkov=True, run_date="2026-01-01")
    assert stub_scan[0]["with_zap"] is True
    assert stub_scan[0]["with_checkov"] is True


def test_empty_repo_is_reported_not_crashed(tmp_path):
    assert sweep.run(str(tmp_path), run_date="2026-01-01") == []
