"""Nuclei adapter tests.

This adapter is a refactor, not a new parser (plan, Task 5): parse() must
delegate entirely to gizmoduck.load(), so the whole point of these tests is
to assert against gz.load() directly rather than hand-written expectations -
that comparison is the regression guard for the other eight adapters too,
since a drift here would mean the routine path and the single-scanner path
silently disagree about what Nuclei found.
"""
import importlib.util

import pytest

from scanners import nuclei


@pytest.fixture(scope="module")
def gz(scripts_dir):
    spec = importlib.util.spec_from_file_location("gz", scripts_dir / "gizmoduck.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_parse_is_byte_identical_to_gizmoduck_load(fixture, gz):
    raw = str(fixture("nuclei.jsonl"))
    expected = gz.load(raw)
    got = nuclei.parse(raw, target="example.com")

    assert len(got) == len(expected) == 3
    for exp, act in zip(expected, got):
        # tool/target are the only keys this adapter adds on top of load()'s
        # existing 14-key shape (Global Constraints) - strip them before
        # comparing so the rest is asserted byte-identical to today's output.
        stripped = {k: v for k, v in act.items() if k not in ("tool", "target")}
        assert stripped == exp


def test_every_finding_carries_tool_and_target(fixture):
    got = nuclei.parse(str(fixture("nuclei.jsonl")), target="example.com")
    assert len(got) == 3
    assert all(f["tool"] == "nuclei" for f in got)
    assert all(f["target"] == "example.com" for f in got)


def test_template_id_is_the_raw_nuclei_template_id(fixture):
    got = nuclei.parse(str(fixture("nuclei.jsonl")), target="example.com")
    assert got[0]["template_id"] == "CVE-2023-12345"
    assert got[0]["severity"] == 4
    assert got[0]["cve"] == ["CVE-2023-12345"]


def test_missing_severity_key_falls_back_to_info(fixture):
    """The fixture's third record has no info.severity at all - gizmoduck.load()
    treats an absent severity the same as an unrecognized one (falls back to
    "unknown" -> Info), and this adapter must reproduce that exactly rather
    than treating "missing" as some other default.
    """
    got = nuclei.parse(str(fixture("nuclei.jsonl")), target="example.com")
    assert got[2]["template_id"] == "tech-detect-nginx"
    assert got[2]["severity"] == 0
    assert got[2]["severity_name"] == "Info"


def test_missing_raw_file_yields_no_findings(tmp_path):
    got = nuclei.parse(str(tmp_path / "does-not-exist.jsonl"), target="x")
    assert got == []


def test_is_available_reflects_find_nuclei(monkeypatch):
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: None)
    assert nuclei.is_available() is False
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: "/usr/bin/nuclei")
    assert nuclei.is_available() is True


def test_run_reuses_cmd_scans_argv_shape(monkeypatch, tmp_path):
    """run() must build the same core argv as cmd_scan() (gizmoduck.py:63) -
    -jsonl/-silent/-nc, -u for a bare target, -severity when given - rather
    than a second, divergent command construction.
    """
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: "nuclei")

    captured = {}

    def fake_run_tool(argv, timeout, cwd=None):
        captured["argv"] = argv
        captured["timeout"] = timeout
        from scanners.base import ToolResult
        return ToolResult(0, '{"template-id":"x"}\n', "", False)

    monkeypatch.setattr(nuclei.base, "run_tool", fake_run_tool)

    raw_path, result = nuclei.run("https://example.com", str(tmp_path),
                                  {"severity": "critical,high"})

    argv = captured["argv"]
    assert argv[0] == "nuclei"
    assert "-jsonl" in argv and "-silent" in argv and "-nc" in argv
    assert "-u" in argv and "https://example.com" in argv
    assert "-severity" in argv and "critical,high" in argv
    assert result.returncode == 0
    assert raw_path.endswith("nuclei.jsonl")


def test_run_uses_l_flag_for_a_targets_file(monkeypatch, tmp_path):
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: "nuclei")

    targets_file = tmp_path / "targets.txt"
    targets_file.write_text("https://a.example\nhttps://b.example\n")

    captured = {}

    def fake_run_tool(argv, timeout, cwd=None):
        captured["argv"] = argv
        from scanners.base import ToolResult
        return ToolResult(0, "", "", False)

    monkeypatch.setattr(nuclei.base, "run_tool", fake_run_tool)

    nuclei.run(str(targets_file), str(tmp_path / "out"), {})

    assert "-l" in captured["argv"] and str(targets_file) in captured["argv"]
    assert "-u" not in captured["argv"]


def test_run_raises_when_nuclei_binary_is_missing(monkeypatch, tmp_path):
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: None)
    with pytest.raises(FileNotFoundError):
        nuclei.run("https://example.com", str(tmp_path), {})
