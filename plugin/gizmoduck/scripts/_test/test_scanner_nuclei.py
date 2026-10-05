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
import sys

import pytest

from scanners import nuclei


@pytest.fixture(autouse=True)
def _scratch_home(scratch_nuclei_home):
    """No test here may read the operator's own Nuclei config."""
    return scratch_nuclei_home


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


def test_missing_raw_file_raises_parse_error(tmp_path):
    """A nonexistent path is not "ran and found nothing" - that claim is
    reserved for an empty file. It's "we cannot tell", which is exactly
    what base.ParseError is for: routine only calls parse() when run()
    just returned this same path, so a file that has since vanished means
    something is wrong that a silent [] would let nobody ever notice.
    """
    with pytest.raises(nuclei.base.ParseError):
        nuclei.parse(str(tmp_path / "does-not-exist.jsonl"), target="x")


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
    # T-0108: the safe defaults come from the shared builder.
    assert argv[argv.index("-etags") + 1] == "dos,intrusive,fuzz"
    assert argv[argv.index("-rl") + 1] == "50"
    assert result.returncode == 0
    assert raw_path.endswith("nuclei.jsonl")


def test_run_honours_nuclei_intrusive_and_rate_limit_options(monkeypatch, tmp_path):
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: "nuclei")
    captured = {}

    def fake_run_tool(argv, timeout, cwd=None):
        captured["argv"] = argv
        from scanners.base import ToolResult
        return ToolResult(0, "", "", False)

    monkeypatch.setattr(nuclei.base, "run_tool", fake_run_tool)
    nuclei.run("https://example.com", str(tmp_path),
               {"nuclei_intrusive": True, "nuclei_rate_limit": 8})

    assert "-etags" not in captured["argv"]
    assert captured["argv"][captured["argv"].index("-rl") + 1] == "8"
    assert nuclei.ACTIVE_OPTS == ["nuclei_intrusive"]


@pytest.mark.parametrize("extra", ["-itags dos", "-rl 500", "--exclude-tags=", "-dast",
                                   "-config c.yaml", "--tp=p.yaml", "-profile=p"])
def test_adapter_refuses_safety_flags_in_extra_without_running_nuclei(monkeypatch, tmp_path,
                                                                      extra):
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: "nuclei")
    calls = []
    monkeypatch.setattr(nuclei.base, "run_tool", lambda *a, **kw: calls.append(a))

    raw_path, result = nuclei.run("https://example.com", str(tmp_path / "out"),
                                  {"extra": extra})

    assert calls == []
    assert raw_path is None
    assert result.returncode == -1
    assert "nuclei_intrusive" in result.stderr
    assert not (tmp_path / "out").exists()


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


# --- HIGH defect: rejected output must not become a false-clean scan ------
#
# run()'s JSON-line filter used to write an empty nuclei.jsonl whenever no
# line survived AND the exit code was 0 - but a bare `[]` or a
# `[FATAL] could not load templates` message on stdout is nuclei failing to
# produce results, not a clean scan. Both have non-empty stdout with zero
# JSON finding lines; a genuinely clean scan's stdout (-silent, nothing
# found) is truly empty, not merely non-JSON.

def test_run_treats_a_bare_empty_array_as_rejected_not_clean(monkeypatch, tmp_path):
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: "nuclei")

    def fake_run_tool(argv, timeout, cwd=None):
        from scanners.base import ToolResult
        return ToolResult(0, "[]", "", False)

    monkeypatch.setattr(nuclei.base, "run_tool", fake_run_tool)

    raw_path, result = nuclei.run("https://example.com", str(tmp_path), {})

    assert raw_path is None
    assert result.returncode == 0
    assert not os.path.exists(os.path.join(str(tmp_path), "nuclei.jsonl"))


def test_run_treats_a_template_load_failure_as_rejected_not_clean(monkeypatch, tmp_path):
    # This is the exact failure mode bootstrap hard-fails on for a template
    # download error - it must never reach parse() looking like a clean run.
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: "nuclei")

    def fake_run_tool(argv, timeout, cwd=None):
        from scanners.base import ToolResult
        return ToolResult(0, "[FATAL] could not load templates", "", False)

    monkeypatch.setattr(nuclei.base, "run_tool", fake_run_tool)

    raw_path, _ = nuclei.run("https://example.com", str(tmp_path), {})

    assert raw_path is None
    assert not os.path.exists(os.path.join(str(tmp_path), "nuclei.jsonl"))


def test_run_a_genuinely_empty_stdout_on_clean_exit_is_still_a_clean_scan(
        monkeypatch, tmp_path):
    # The case the fix above must not break: -silent with truly nothing on
    # stdout and a clean exit is nuclei's real "ran, found nothing".
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: "nuclei")

    def fake_run_tool(argv, timeout, cwd=None):
        from scanners.base import ToolResult
        return ToolResult(0, "", "", False)

    monkeypatch.setattr(nuclei.base, "run_tool", fake_run_tool)

    raw_path, _ = nuclei.run("https://example.com", str(tmp_path), {})

    assert raw_path is not None
    assert os.path.isfile(raw_path)
    assert nuclei.parse(raw_path, target="example.com") == []


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


# ---------------------------------------------------------------------------
# T-0108 review FIX 2/3: the operator's Nuclei config, and hand-built options
# ---------------------------------------------------------------------------

def _counting_run_tool(monkeypatch):
    gzmod = nuclei._gizmoduck()
    monkeypatch.setattr(gzmod, "find_nuclei", lambda: "nuclei")
    calls = []

    def fake_run_tool(argv, timeout, cwd=None):
        calls.append(argv)
        from scanners.base import ToolResult
        return ToolResult(0, "", "", False)

    monkeypatch.setattr(nuclei.base, "run_tool", fake_run_tool)
    return calls


def _write_config(text, path=None):
    path = path or nuclei.nuclei_config_files()[0]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


@pytest.mark.parametrize("text,key", [
    ("include-tags:\n  - intrusive\n", "include-tags"),
    ("itags: [dos]\n", "itags"),
    ("include-templates: [dast/]\n", "include-templates"),
    ("rate-limit: 500\n", "rate-limit"),
    ("rl: 0\n", "rl"),
    ("rate-limit-minute: 60000\n", "rate-limit-minute"),
    ("rate-limit-duration: 10ms\n", "rate-limit-duration"),
    ("per-host-rate-limit: true\n", "per-host-rate-limit"),
    ("dast: true\n", "dast"),
    ("fuzz: true\n", "fuzz"),
    ("profile: aggressive.yaml\n", "profile"),
])
def test_routine_refuses_a_nuclei_config_that_loosens_the_defaults(monkeypatch, tmp_path,
                                                                    text, key):
    calls = _counting_run_tool(monkeypatch)
    path = _write_config("# mine\ntimeout: 5\n" + text)

    raw_path, result = nuclei.run("https://example.com", str(tmp_path / "out"), {})

    assert calls == []
    assert raw_path is None and result.returncode == -1
    assert path in result.stderr and key in result.stderr
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("text", [
    None,                                     # no file at all
    "",                                       # empty
    "# nuclei config file\n#rate-limit: 150\n",  # nuclei's own generated, comment-only
    "timeout: 5\nexclude-tags: [cve]\ndast: false\ninclude-tags: []\nrate-limit:\n",
])
def test_routine_runs_with_a_harmless_or_missing_nuclei_config(monkeypatch, tmp_path, text):
    calls = _counting_run_tool(monkeypatch)
    if text is not None:
        _write_config(text)

    _raw, result = nuclei.run("https://example.com", str(tmp_path / "out"), {})

    assert result.returncode == 0
    assert len(calls) == 1


@pytest.mark.parametrize("shape", ["unparseable", "not-a-mapping", "a-directory"])
def test_routine_refuses_a_nuclei_config_it_could_not_read(monkeypatch, tmp_path, shape):
    calls = _counting_run_tool(monkeypatch)
    path = nuclei.nuclei_config_files()[0]
    if shape == "unparseable":
        _write_config("rate-limit: [500\n  : :\n")
    elif shape == "not-a-mapping":
        _write_config("- rate-limit\n- 500\n")
    else:
        os.makedirs(path)

    raw_path, result = nuclei.run("https://example.com", str(tmp_path / "out"), {})

    assert calls == []
    assert raw_path is None and result.returncode == -1
    assert path in result.stderr


def test_nuclei_config_dir_env_is_checked_too(monkeypatch, tmp_path):
    calls = _counting_run_tool(monkeypatch)
    custom = tmp_path / "custom-cfg"
    monkeypatch.setenv("NUCLEI_CONFIG_DIR", str(custom))
    path = _write_config("include-tags: [intrusive]\n", str(custom / "config.yaml"))

    _raw, result = nuclei.run("https://example.com", str(tmp_path / "out"), {})

    assert calls == [] and path in result.stderr


@pytest.mark.skipif(os.name == "nt" or sys.platform == "darwin",
                    reason="XDG_CONFIG_HOME is Go's UserConfigDir on Linux/BSD only")
def test_xdg_config_home_is_where_go_looks(monkeypatch, tmp_path):
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    assert nuclei.nuclei_config_files()[0] == str(xdg / "nuclei" / "config.yaml")


@pytest.mark.parametrize("opts", [
    {"nuclei_rate_limit": 0}, {"nuclei_rate_limit": -1}, {"nuclei_rate_limit": True},
    {"nuclei_rate_limit": "50"}, {"nuclei_intrusive": "false"}, {"nuclei_intrusive": 1},
    {"extra": ["-rl", "5"]},
])
def test_adapter_refuses_bad_hand_built_options_without_running(monkeypatch, tmp_path, opts):
    calls = _counting_run_tool(monkeypatch)

    raw_path, result = nuclei.run("https://example.com", str(tmp_path / "out"), opts)

    assert calls == []
    assert raw_path is None and result.returncode == -1


def test_adapter_pins_rld_beside_its_rate_limit(monkeypatch, tmp_path):
    calls = _counting_run_tool(monkeypatch)
    nuclei.run("https://example.com", str(tmp_path / "out"), {"nuclei_rate_limit": 9})
    argv = calls[0]
    i = argv.index("-rl")
    assert argv[i:i + 4] == ["-rl", "9", "-rld", "1s"]
