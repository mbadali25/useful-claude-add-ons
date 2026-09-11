"""Nuclei adapter tests.

This adapter is a refactor, not a new parser (plan, Task 5): parse() must
delegate entirely to gizmoduck.load(), so the whole point of these tests is
to assert against gz.load() directly rather than hand-written expectations -
that comparison is the regression guard for the other eight adapters too,
since a drift here would mean the routine path and the single-scanner path
silently disagree about what Nuclei found.

Byte-identity to load() is asserted for every key EXCEPT `tags`: this adapter
also has to mark an assigned-default severity (Global Constraints'
`severity-assigned` tag) with a fix load() itself doesn't make, so `tags` is
checked separately - identical to load()'s for a real, recognized severity,
and load()'s list plus the marker for a missing/unrecognized one.
"""
import importlib.util
import os

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
        # tool/target are the only keys this adapter adds outright on top of
        # load()'s existing 14-key shape (Global Constraints). `tags` is
        # compared on its own below, since it may additionally carry the
        # `severity-assigned` marker load() itself never adds.
        stripped = {k: v for k, v in act.items()
                    if k not in ("tool", "target", "tags")}
        exp_sans_tags = {k: v for k, v in exp.items() if k != "tags"}
        assert stripped == exp_sans_tags

        if "severity-assigned" in act["tags"]:
            assert act["tags"] == exp["tags"] + ["severity-assigned"]
        else:
            assert act["tags"] == exp["tags"]


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


def test_missing_severity_carries_the_severity_assigned_provenance_marker(fixture):
    """Defect fix: load() folds "missing" and "unrecognized" into the same
    Info fallback as a real Info assessment, with nothing in its output to
    tell them apart. Without a marker, an assigned default renders in a
    report identically to an actual assessment - this is what distinguishes
    the two. Records 0/1 have an explicit, recognized severity in the
    fixture and must NOT carry the marker; only record 2 (no info.severity
    at all) should.
    """
    got = nuclei.parse(str(fixture("nuclei.jsonl")), target="example.com")

    assert "severity-assigned" not in got[0]["tags"]
    assert "severity-assigned" not in got[1]["tags"]
    assert "severity-assigned" in got[2]["tags"]


def test_missing_raw_file_yields_no_findings(tmp_path):
    got = nuclei.parse(str(tmp_path / "does-not-exist.jsonl"), target="x")
    assert got == []


def test_empty_raw_file_yields_no_findings(tmp_path):
    """An empty output file is "nuclei ran and found nothing", not a parse
    failure - run() writes exactly this when -silent has nothing to say.
    """
    raw = tmp_path / "nuclei.jsonl"
    raw.write_text("")
    assert nuclei.parse(str(raw), target="x") == []


def test_parse_raises_parse_error_on_malformed_jsonl(tmp_path):
    """Defect fix: a line that isn't valid JSON must raise base.ParseError,
    never come back as an empty (and therefore falsely "clean") list. An
    empty finding list must mean only "nuclei ran and found nothing" -
    conflating it with "couldn't read the output" hides a broken scan.
    """
    raw = tmp_path / "nuclei.jsonl"
    raw.write_text('{"template-id": "x", "info": {"severity": "high"}}\n'
                    '{not valid json at all\n')

    with pytest.raises(nuclei.base.ParseError):
        nuclei.parse(str(raw), target="example.com")


def test_parse_raises_parse_error_on_truncated_jsonl(tmp_path):
    """A truncated line (a scan killed mid-write) is exactly the case the
    fixed-width exit-code gate used to mask - it must surface as
    base.ParseError, not as zero findings.
    """
    raw = tmp_path / "nuclei.jsonl"
    raw.write_text('{"template-id": "x", "info": {"severity": "high"')

    with pytest.raises(nuclei.base.ParseError):
        nuclei.parse(str(raw), target="example.com")


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


def test_run_returns_none_path_when_nuclei_binary_is_missing(monkeypatch, tmp_path):
    """Standardized run() contract (team-lead cross-adapter decision): a
    missing binary must return (None, ToolResult), the same shape every
    other adapter returns for "couldn't run" - not raise. This test used to
    assert FileNotFoundError; that encoded the bug, because raising here
    skips routine.py's normal per-tool `skipped-missing` recording instead
    of going through it like every other adapter's missing-binary case.
    """
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: None)

    raw_path, result = nuclei.run("https://example.com", str(tmp_path), {})

    assert raw_path is None
    assert result.returncode != 0
    assert not result.timed_out


def test_run_returns_none_path_on_a_failed_invocation(monkeypatch, tmp_path):
    """Standardized run() contract (team-lead cross-adapter decision):
    (None, result) when no output file was written - a plain failure exit,
    with no findings on stdout to redeem it as `-ec`'s "findings exist" 1.
    The ToolResult still comes back (with returncode/timed_out intact) so
    routine.py can record error:<n> / error:timeout per-cell.
    """
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: "nuclei")

    def fake_run_tool(argv, timeout, cwd=None):
        from scanners.base import ToolResult
        return ToolResult(2, "", "connection refused", False)

    monkeypatch.setattr(nuclei.base, "run_tool", fake_run_tool)

    raw_path, result = nuclei.run("https://example.com", str(tmp_path), {})

    assert raw_path is None
    assert result.returncode == 2
    assert not os.path.exists(os.path.join(str(tmp_path), "nuclei.jsonl"))


def test_run_keeps_findings_from_a_nonzero_exit_code(monkeypatch, tmp_path):
    """Defect fix: valid finding output on stdout must never be discarded
    just because nuclei's exit code was nonzero and not the `-ec`
    "findings exist" 1. Nmap is the only adapter in this package permitted
    to gate findings on exit status - Nuclei's findings must come from
    parsed output alone.
    """
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: "nuclei")

    def fake_run_tool(argv, timeout, cwd=None):
        from scanners.base import ToolResult
        return ToolResult(2, '{"template-id":"x"}', "", False)

    monkeypatch.setattr(nuclei.base, "run_tool", fake_run_tool)

    raw_path, result = nuclei.run("https://example.com", str(tmp_path), {})

    assert raw_path is not None
    assert os.path.isfile(raw_path)
    with open(raw_path, encoding="utf-8") as fh:
        assert fh.read().strip() == '{"template-id":"x"}'
    assert result.returncode == 2


def test_run_returns_none_path_on_a_timeout(monkeypatch, tmp_path):
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: "nuclei")

    def fake_run_tool(argv, timeout, cwd=None):
        from scanners.base import ToolResult
        return ToolResult(-1, "", "", True)

    monkeypatch.setattr(nuclei.base, "run_tool", fake_run_tool)

    raw_path, result = nuclei.run("https://example.com", str(tmp_path), {})

    assert raw_path is None
    assert result.timed_out is True
