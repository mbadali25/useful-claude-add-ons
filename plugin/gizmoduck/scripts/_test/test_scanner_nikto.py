import pytest

from scanners import base, nikto


# --- HIGH defect: nikto needs a perl + nikto.pl route on Windows -----------
#
# nikto is a Perl script with no native Windows package (bootstrap.ps1's
# Install-Nikto comment). Whether the perl on PATH can actually run nikto
# (it hard-requires XML::Writer) is verified and fixed at BOOTSTRAP time
# (bootstrap.ps1's Test-PerlHasXmlWriter installs the module or falls back
# to Strawberry Perl) - by the time this adapter runs, `base.which("perl")`
# is expected to already work, the same way every other adapter trusts
# `base.which()` for its own tool. An earlier version of this adapter
# duplicated that capability check at runtime and hard-coded a preference
# for Strawberry Perl over PATH; a second, independent verification found
# PATH perl (Git for Windows' bundled perl, once XML::Writer was present) to
# be the *better* choice - Strawberry's perl emitted an unrelated warning
# nikto.pl doesn't hit under Git's perl - so that preference was wrong and
# has been removed. This adapter now just uses whichever perl is on PATH.

def test_is_available_true_via_native_nikto_binary(monkeypatch):
    monkeypatch.setattr(base, "which", lambda name: "/usr/bin/nikto" if name == "nikto" else None)
    assert nikto.is_available() is True


def test_is_available_true_via_nikto_pl_and_path_perl(monkeypatch, tmp_path):
    nikto_pl = tmp_path / "nikto.pl"
    nikto_pl.write_text("# stand-in")
    monkeypatch.setattr(
        base, "which",
        lambda name: {"perl": "/usr/bin/perl"}.get(name))  # no native nikto, perl on PATH
    monkeypatch.setattr(nikto, "_NIKTO_PL_CANDIDATES", (str(nikto_pl),))

    assert nikto.is_available() is True


def test_is_available_false_when_no_perl_is_found(monkeypatch, tmp_path):
    nikto_pl = tmp_path / "nikto.pl"
    nikto_pl.write_text("# stand-in")
    monkeypatch.setattr(base, "which", lambda name: None)
    monkeypatch.setattr(nikto, "_NIKTO_PL_CANDIDATES", (str(nikto_pl),))

    assert nikto.is_available() is False


def test_run_uses_perl_and_nikto_pl_when_no_native_binary_is_found(monkeypatch, tmp_path):
    nikto_pl = tmp_path / "nikto.pl"
    nikto_pl.write_text("# stand-in")
    monkeypatch.setattr(
        base, "which",
        lambda name: {"perl": "/usr/bin/perl"}.get(name))
    monkeypatch.setattr(nikto, "_NIKTO_PL_CANDIDATES", (str(nikto_pl),))

    captured = {}

    def fake_run_tool(argv, timeout, cwd=None):
        captured["argv"] = argv
        (tmp_path / "nikto.csv").write_text(
            "000001,1,1,1.2.3.4,example.test,443,1,,GET,/,retrieved x-powered-by header,,\n")
        return base.ToolResult(1, "", "", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    result_path, result = nikto.run("https://example.test", str(tmp_path))

    assert result_path == str(tmp_path / "nikto.csv")
    assert captured["argv"][0] == "/usr/bin/perl"
    assert captured["argv"][1] == str(nikto_pl)
    assert "-h" in captured["argv"] and "https://example.test" in captured["argv"]


def test_run_returns_an_error_when_no_native_binary_and_no_working_perl_route(monkeypatch, tmp_path):
    # Neither a native `nikto` nor a usable perl+nikto.pl route exists - run()
    # must decline with a ToolResult explaining why, and must never call
    # base.run_tool (nothing to invoke).
    monkeypatch.setattr(base, "which", lambda name: None)
    monkeypatch.setattr(nikto, "_NIKTO_PL_CANDIDATES", ())

    called = []
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: called.append(1))

    result_path, result = nikto.run("https://example.test", str(tmp_path))

    assert called == []
    assert result_path is None
    assert result.returncode != 0
    assert "perl" in result.stderr.lower() or "nikto" in result.stderr.lower()


def test_parses_both_rows_with_derived_severities(fixture):
    findings = nikto.parse(str(fixture("nikto.csv")), "https://example.test")
    assert len(findings) == 2

    banner, vuln = findings
    assert banner["severity"] == 0
    assert banner["severity_name"] == "info"
    assert vuln["severity"] == 2
    assert vuln["severity_name"] == "medium"


def test_every_finding_carries_severity_assigned(fixture):
    # Nikto has no severity field at all (spec 13.6) - every finding here is
    # a heuristic assignment, and the marker must say so every time.
    findings = nikto.parse(str(fixture("nikto.csv")), "https://example.test")
    assert len(findings) == 2
    for f in findings:
        assert "severity-assigned" in f["tags"]


def test_template_id_is_namespaced_by_tool(fixture):
    findings = nikto.parse(str(fixture("nikto.csv")), "https://example.test")
    ids = {f["template_id"] for f in findings}
    assert ids == {"nikto:000001", "nikto:999100"}


def test_target_is_set_from_argument(fixture):
    findings = nikto.parse(str(fixture("nikto.csv")), "https://example.test")
    for f in findings:
        assert f["target"] == "https://example.test"


def test_parse_missing_file_raises_parse_error(tmp_path):
    # CRITICAL defect fix: a missing file at parse time is not "nikto ran
    # and found nothing" - that claim is reserved for a real, empty-of-rows
    # CSV. routine only calls parse() with the path run() just returned, so
    # a file gone at that point means evidence vanished, which must surface
    # loudly rather than render as a silently clean target.
    with pytest.raises(base.ParseError):
        nikto.parse(str(tmp_path / "absent.csv"), "https://example.test")


def test_module_constants_match_the_plan():
    assert nikto.NAME == "nikto"
    assert nikto.KINDS == ["web"]
    assert nikto.ACTIVE is False
    assert nikto.ACTIVE_OPTS == []


# --- parse(): must not manufacture a vulnerability from garbage input ----
#
# MEDIUM defect: any nonempty CSV row - including a truncated row or a
# single diagnostic/garbage line - used to get padded out to the full
# column set and turned into a `medium` finding. That invents a
# vulnerability that was never actually observed. Required columns must
# now be validated, raising base.ParseError instead.

def test_truncated_row_raises_parse_error_instead_of_a_finding(fixture):
    with pytest.raises(base.ParseError):
        nikto.parse(str(fixture("nikto-truncated.csv")), "https://example.test")


def test_garbage_line_raises_parse_error_instead_of_a_finding(fixture):
    with pytest.raises(base.ParseError):
        nikto.parse(str(fixture("nikto-bad-shape.csv")), "https://example.test")


def test_bare_null_line_raises_parse_error_instead_of_a_finding(fixture):
    with pytest.raises(base.ParseError):
        nikto.parse(str(fixture("nikto-null.csv")), "https://example.test")


# --- CRITICAL defect: a failed invocation must never reuse stale output ----
#
# run() used to always hand back the same raw_path regardless of whether
# THIS invocation wrote anything: a failed run() (crash, unreachable target)
# that produced no fresh CSV would still return the path, and if an earlier
# run had left a CSV sitting in the same outdir, that stale file would be
# read back as if it were this run's evidence - a failed scan inheriting a
# previous run's clean bill of health, or a previous run's findings.

def test_run_deletes_a_preexisting_csv_before_invoking_nikto(monkeypatch, tmp_path):
    monkeypatch.setattr(base, "which", lambda name: "/usr/bin/nikto" if name == "nikto" else None)
    raw_path = tmp_path / "nikto.csv"
    raw_path.write_text("stale,data,from,a,previous,run\n")

    def fake_run_tool(argv, timeout, cwd=None):
        # Simulates a failed invocation: nikto never wrote a fresh CSV.
        return base.ToolResult(1, "", "nikto: connection failed", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    result_path, result = nikto.run("https://example.test", str(tmp_path))

    assert not raw_path.exists()
    assert result_path is None
    assert result.returncode == 1


def test_run_returns_none_path_when_no_fresh_csv_is_written(monkeypatch, tmp_path):
    monkeypatch.setattr(base, "which", lambda name: "/usr/bin/nikto" if name == "nikto" else None)
    monkeypatch.setattr(
        base, "run_tool",
        lambda *a, **k: base.ToolResult(1, "", "failed", False))

    result_path, result = nikto.run("https://example.test", str(tmp_path))

    assert result_path is None
    assert result.returncode == 1


def test_run_returns_the_path_when_a_fresh_csv_is_written(monkeypatch, tmp_path):
    monkeypatch.setattr(base, "which", lambda name: "/usr/bin/nikto" if name == "nikto" else None)

    def fake_run_tool(argv, timeout, cwd=None):
        (tmp_path / "nikto.csv").write_text(
            "000001,1,1,1.2.3.4,example.test,443,1,,GET,/,retrieved x-powered-by header,,\n")
        return base.ToolResult(1, "", "", False)  # nikto always exits nonzero

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    result_path, result = nikto.run("https://example.test", str(tmp_path))

    assert result_path == str(tmp_path / "nikto.csv")
    findings = nikto.parse(result_path, "https://example.test")
    assert len(findings) == 1
