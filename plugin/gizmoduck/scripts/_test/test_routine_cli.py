"""The CLI surface of `gizmoduck.py routine` and `report --run-manifest` (T-0107).

`routine.run_routine` was the only path to checkov, trivy, dependency-check,
semgrep, ZAP, testssl, nmap, nikto and sqlmap, and nothing shipped called it:
only nuclei was runnable headless. This suite pins the front door that
`routine` adds - the file set it writes, the dated `--scan-root` layout, the
0 / 4 / 2 exit contract (4 = outputs written but some cell did not run, which
is NOT a clean result), the same-day refusal without `--replace`, sqlmap's
`--confirm-active` asked for by name, and `report --run-manifest` re-rendering
a routine run with its coverage table.

No scanner ever runs here. Every in-process test passes a `FakeRegistry`
through `cmd_routine(registry=...)`, the seam `run_routine` already has, and
every manifest host is an RFC 6761 `.invalid` name. The two subprocess tests
run in a sanitised environment (empty PATH, HOME and LOCALAPPDATA pointed at
tmp, every GIZMODUCK_* tool override unset) and assert that every cell is
`skipped-missing` BEFORE asserting anything else, so a scanner that somehow
resolves fails the test by name instead of running.

Sabotage (each run by hand against the tracked gizmoduck.py; the named test
must go red):
  (a) drop the scan-meta.json existence check
      -> test_existing_scan_meta_refuses_without_replace
         (neighbour test_replace_rewrites_the_set_and_removes_stale_target_dirs
         stays green)
  (b) coverage `complete` computed with any() instead of all()
      -> test_exit_4_when_any_cell_is_not_ran[skipped-missing]
  (c) confirm=True passed to run_routine unconditionally
      -> test_confirm_active_is_required_by_name
  (d) the atomic helper replaced by a plain open(path, "w")
      -> test_scan_meta_write_is_complete_then_renamed
  (e) the output directory created before load_manifest
      -> test_manifest_errors_write_nothing[no-auth]
  (f) --run-manifest parsed and not passed to cmd_report
      -> test_report_run_manifest_renders_coverage
  (g) the exit-4 branch returning 0
      -> test_all_tools_missing_exits_4_end_to_end
"""
import datetime
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_routine_orchestration import (
    FakeAdapter,
    FakeRegistry,
    _declines_without_confirm,
    _finding,
    _ok,
    _raises,
    _times_out,
)

_SCRIPT = Path(__file__).resolve().parent.parent / "gizmoduck.py"
_DATE = datetime.date(2026, 9, 29)


@pytest.fixture(scope="module")
def gz(scripts_dir):
    spec = importlib.util.spec_from_file_location("gz", scripts_dir / "gizmoduck.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(autouse=True)
def _no_pdf_renderer(gz, monkeypatch):
    """A PDF renderer on the test machine must not decide what these tests
    see; `files.report_pdf` is asserted null, the no-renderer case."""
    monkeypatch.setattr(gz, "html_to_pdf", lambda html, out: False)


def _registry(**overrides):
    """nuclei, nmap and testssl as the `web` default, plus sqlmap as the one
    active, opt-in-only adapter. Every fake runs clean unless overridden."""
    fakes = {
        "nuclei": FakeAdapter("nuclei", ["web", "host"], run_fn=_ok("nuclei-raw"),
                              findings=[_finding("nuclei", "tpl-1", severity=3)]),
        "nmap": FakeAdapter("nmap", ["web", "host"], active_opts=["nmap_vuln"],
                            run_fn=_ok("nmap-raw")),
        "testssl": FakeAdapter("testssl", ["web", "host"], run_fn=_ok("testssl-raw")),
        "sqlmap": FakeAdapter("sqlmap", ["web"], active=True, default_enabled=False,
                              run_fn=_declines_without_confirm()),
    }
    fakes.update(overrides)
    return FakeRegistry(list(fakes.values()), {"web": ["nuclei", "nmap", "testssl"]})


def _meta(outdir):
    return json.loads((Path(outdir) / "scan-meta.json").read_text(encoding="utf-8"))


def _cells(outdir):
    data = json.loads((Path(outdir) / "run-manifest.json").read_text(encoding="utf-8"))
    return {(c["target"], c["tool"]): c for c in data["cells"]}


def _run(gz, fixture, tmp_path, reg, **kw):
    return gz.cmd_routine(str(fixture("manifest-routine-cli.yaml")), str(tmp_path / "out"),
                          registry=reg, date=kw.pop("date", _DATE), **kw)


# ---------------------------------------------------------------------------
# cmd_routine, in process, over fakes
# ---------------------------------------------------------------------------

def test_routine_writes_the_file_set_and_exits_0_when_every_cell_ran(gz, fixture, tmp_path):
    manifest_path = str(fixture("manifest-routine-cli.yaml"))
    rc = gz.cmd_routine(manifest_path, str(tmp_path / "out"), registry=_registry(),
                        date=_DATE, confirm=True)

    out = tmp_path / "out"
    assert rc == 0
    for name in ("findings.jsonl", "run-manifest.json", "scan-meta.json", "report.md",
                 "report.html"):
        assert (out / name).is_file(), name
    assert not (out / "report.pdf").exists()
    meta = _meta(out)
    assert meta["schema"] == 1
    assert meta["coverage"] == {"cells": 7, "by_status": {"ran": 7}, "complete": True,
                                "ran_with_scan_errors": 0}
    findings = gz.load(str(out / "findings.jsonl"))
    assert meta["findings"] == {"total": 2,
                                "by_severity": gz.cmd_summary(findings)["by_severity"]}
    assert meta["targets"] == [
        {"name": "site-a", "kind": "web", "location": "https://routine-cli-a.invalid/x?id=1"},
        {"name": "site-b", "kind": "web", "location": "https://routine-cli-b.invalid/"},
    ]
    assert meta["authorized_by"] == "ACME-0107 - test harness, authorized to test these names"
    assert meta["date"] == "2026-09-29"
    assert meta["manifest"] == manifest_path
    assert meta["confirm_active"] is True
    assert meta["started_at"].endswith("+00:00") and meta["completed_at"].endswith("+00:00")
    assert meta["started_at"] <= meta["completed_at"]
    assert meta["files"] == {"findings": "findings.jsonl", "run_manifest": "run-manifest.json",
                             "report_md": "report.md", "report_html": "report.html",
                             "report_pdf": None}


@pytest.mark.parametrize("family,status_text,overrides,confirm", [
    ("skipped-missing", "skipped-missing",
     {"nmap": FakeAdapter("nmap", ["web", "host"], available=False)}, True),
    ("skipped-active", "skipped-active", {}, False),
    ("error", "error:timeout",
     {"testssl": FakeAdapter("testssl", ["web", "host"], run_fn=_times_out())}, True),
    ("error", "error:boom",
     {"nuclei": FakeAdapter("nuclei", ["web", "host"], run_fn=_raises("boom"))}, True),
], ids=["skipped-missing", "skipped-active", "error:timeout", "error:raise"])
def test_exit_4_when_any_cell_is_not_ran(gz, fixture, tmp_path, capsys, family, status_text,
                                         overrides, confirm):
    rc = _run(gz, fixture, tmp_path, _registry(**overrides), confirm=confirm)

    out = tmp_path / "out"
    assert rc == gz.ROUTINE_INCOMPLETE_EXIT == 4
    meta = _meta(out)
    assert meta["coverage"]["complete"] is False
    assert meta["coverage"]["by_status"][family] >= 1
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "## Coverage" in report
    assert status_text in report
    for name in gz.ROUTINE_FILES:
        if name != "report.pdf":
            assert (out / name).is_file(), name
    last = capsys.readouterr().out.rstrip().splitlines()[-1]
    assert last.startswith(f"{gz.ROUTINE_MARKER}: ")


def test_report_md_carries_the_coverage_table_and_the_scan_marker(gz, fixture, tmp_path):
    _run(gz, fixture, tmp_path, _registry(), confirm=True)

    report = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "**Authorized by:**" in report
    assert "## Coverage" in report
    assert "**Total finding instances:**" in report


def test_confirm_active_is_required_by_name(gz, fixture, tmp_path):
    without = _registry()
    with_flag = _registry()
    gz.cmd_routine(str(fixture("manifest-routine-cli.yaml")), str(tmp_path / "one"),
                   registry=without, date=_DATE)
    gz.cmd_routine(str(fixture("manifest-routine-cli.yaml")), str(tmp_path / "two"),
                   registry=with_flag, date=_DATE, confirm=True)

    assert without.ADAPTERS["sqlmap"].run_calls[0][2]["confirm"] is False
    assert _cells(tmp_path / "one")[("site-a", "sqlmap")]["status"] == "skipped-active"
    assert with_flag.ADAPTERS["sqlmap"].run_calls[0][2]["confirm"] is True
    assert _cells(tmp_path / "two")[("site-a", "sqlmap")]["status"] == "ran"


def test_existing_scan_meta_refuses_without_replace(gz, fixture, tmp_path, capsys):
    out = tmp_path / "out"
    out.mkdir()
    (out / "scan-meta.json").write_bytes(b"SENTINEL")
    reg = _registry()

    rc = _run(gz, fixture, tmp_path, reg, confirm=True)

    assert rc == 2
    err = capsys.readouterr().err
    assert str(out / "scan-meta.json") in err
    assert "--replace" in err
    assert (out / "scan-meta.json").read_bytes() == b"SENTINEL"
    assert not (out / "report.md").exists()
    assert all(a.run_calls == [] for a in reg.ADAPTERS.values())


def test_replace_rewrites_the_set_and_removes_stale_target_dirs(gz, fixture, tmp_path):
    out = tmp_path / "out"
    (out / "old-target").mkdir(parents=True)
    (out / "old-target" / "raw.txt").write_text("stale", encoding="utf-8")
    (out / "scan-meta.json").write_text('{"schema": 0}', encoding="utf-8")
    (out / "report.pdf").write_bytes(b"stale pdf")

    rc = _run(gz, fixture, tmp_path, _registry(), confirm=True, replace=True)

    assert rc == 0
    assert not (out / "old-target").exists()
    assert not (out / "report.pdf").exists()
    assert _meta(out)["schema"] == 1


def test_scan_root_builds_the_dated_path(gz, fixture, tmp_path):
    root = tmp_path / "module"
    gz.cmd_routine(str(fixture("manifest-routine-cli.yaml")), None, scan_root=str(root),
                   date=_DATE, registry=_registry(), confirm=True)
    gz.cmd_routine(str(fixture("manifest-routine-cli.yaml")), None, scan_root=str(root),
                   date=None, registry=_registry(), confirm=True)

    dated = root / "docs" / "security-scans" / "2026-09-29"
    assert (dated / "scan-meta.json").is_file()
    assert _meta(dated)["date"] == "2026-09-29"
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    assert (root / "docs" / "security-scans" / today / "scan-meta.json").is_file()


def test_scan_meta_write_is_complete_then_renamed(gz, fixture, tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    (out / "scan-meta.json").write_bytes(b"EARLIER RUN")
    monkeypatch.setattr(gz, "_scan_meta_text", lambda **kw: 1 / 0)

    with pytest.raises(ZeroDivisionError):
        _run(gz, fixture, tmp_path, _registry(), confirm=True, replace=True)

    assert (out / "scan-meta.json").read_bytes() == b"EARLIER RUN"
    assert list(out.glob("scan-meta.json*")) == [out / "scan-meta.json"]


def test_atomic_write_leaves_the_original_when_the_write_raises(gz, tmp_path, monkeypatch):
    target = tmp_path / "report.md"
    target.write_bytes(b"ORIGINAL")

    def _explode(*_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr(gz.os, "replace", _explode)
    with pytest.raises(OSError, match="disk full"):
        gz._atomic_write_text(target, "new text")

    assert target.read_bytes() == b"ORIGINAL"
    assert list(tmp_path.iterdir()) == [target]


_BAD_MANIFESTS = {
    "no-auth": ("targets:\n  - {name: a, kind: web, url: 'https://a.invalid/'}\n",
                "authorized_by"),
    "duplicate-name": (("authorized_by: t\ntargets:\n"
                        "  - {name: a, kind: web, url: 'https://a.invalid/'}\n"
                        "  - {name: a, kind: web, url: 'https://b.invalid/'}\n"),
                       "duplicate target name 'a'"),
    "unknown-kind": ("authorized_by: t\ntargets:\n  - {name: a, kind: spaceship, url: x}\n",
                     "unknown target kind 'spaceship'"),
    "missing-location": ("authorized_by: t\ntargets:\n  - {name: a, kind: web}\n",
                         "missing its required 'url' field"),
    "bad-yaml": ("authorized_by: [\n", "while parsing"),
    "missing-file": (None, "No such file or directory"),
}


@pytest.mark.parametrize("case", list(_BAD_MANIFESTS))
def test_manifest_errors_write_nothing(gz, tmp_path, capsys, case):
    text, message = _BAD_MANIFESTS[case]
    manifest = tmp_path / "manifests" / f"{case}.yaml"
    manifest.parent.mkdir()
    if text is not None:
        manifest.write_text(text, encoding="utf-8")
    reg = _registry()

    rc = gz.cmd_routine(str(manifest), str(tmp_path / "out"), registry=reg, date=_DATE)

    assert rc == 2
    err = capsys.readouterr().err
    assert "routine: manifest refused" in err
    assert message in err
    assert not (tmp_path / "out").exists()
    assert all(a.run_calls == [] for a in reg.ADAPTERS.values())


def test_a_manifest_with_no_targets_is_not_complete(gz, tmp_path, capsys):
    manifest = tmp_path / "empty.yaml"
    manifest.write_text("authorized_by: t\ntargets: []\n", encoding="utf-8")

    rc = gz.cmd_routine(str(manifest), str(tmp_path / "out"), registry=_registry(), date=_DATE)

    assert rc == 4
    assert _meta(tmp_path / "out")["coverage"] == {"cells": 0, "by_status": {},
                                                   "complete": False,
                                                   "ran_with_scan_errors": 0}
    assert capsys.readouterr().out.rstrip().splitlines()[-1].startswith(f"{gz.ROUTINE_MARKER}: ")


def test_ran_cells_with_scan_errors_are_counted(gz, fixture, tmp_path):
    noisy = FakeAdapter("testssl", ["web", "host"], run_fn=_ok("testssl-raw"),
                        parse_errors_fn=lambda raw, target: ["WARN: could not connect"])

    rc = _run(gz, fixture, tmp_path, _registry(testssl=noisy), confirm=True)

    coverage = _meta(tmp_path / "out")["coverage"]
    assert rc == 0
    assert coverage["complete"] is True
    assert coverage["ran_with_scan_errors"] == 2


# ---------------------------------------------------------------------------
# argparse, through gz.main()
# ---------------------------------------------------------------------------

def _main_exit(gz, monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["gizmoduck.py", *argv])
    with pytest.raises(SystemExit) as e:
        gz.main()
    return e.value.code


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _nothing_written(tmp_path):
    return (not (tmp_path / "out").exists() and not (tmp_path / "routine-out").exists()
            and not (tmp_path / "root").exists())


def test_routine_needs_a_manifest(gz, monkeypatch, capsys, in_tmp):
    code = _main_exit(gz, monkeypatch, ["routine"])

    assert code == 2
    assert "routine needs a manifest" in capsys.readouterr().err
    assert _nothing_written(in_tmp)


@pytest.mark.parametrize("flag", [["--scan-root", "root"], ["--date", "2026-09-29"],
                                  ["--replace"], ["--confirm-active"]],
                         ids=["--scan-root", "--date", "--replace", "--confirm-active"])
def test_routine_only_flags_are_refused_elsewhere(gz, monkeypatch, capsys, in_tmp, flag):
    code = _main_exit(gz, monkeypatch, ["scan", "https://x.invalid/", "--out", "out/f.jsonl",
                                        *flag])

    assert code == 2
    err = capsys.readouterr().err
    assert f"{flag[0]} only applies to the 'routine' command" in err
    assert _nothing_written(in_tmp)


def test_run_manifest_only_applies_to_report(gz, monkeypatch, capsys, in_tmp):
    code = _main_exit(gz, monkeypatch, ["summary", "f.jsonl", "--run-manifest", "m.json"])

    assert code == 2
    assert "--run-manifest only applies to the 'report' command" in capsys.readouterr().err
    assert _nothing_written(in_tmp)


def test_scan_root_and_out_together_is_a_usage_error(gz, monkeypatch, capsys, in_tmp, fixture):
    code = _main_exit(gz, monkeypatch, ["routine", str(fixture("manifest-routine-cli.yaml")),
                                        "--scan-root", "root", "--out", "out"])

    assert code == 2
    assert "--scan-root and --out" in capsys.readouterr().err
    assert _nothing_written(in_tmp)


def test_date_without_scan_root_is_a_usage_error(gz, monkeypatch, capsys, in_tmp, fixture):
    code = _main_exit(gz, monkeypatch, ["routine", str(fixture("manifest-routine-cli.yaml")),
                                        "--date", "2026-09-29", "--out", "out"])

    assert code == 2
    assert "--date only shapes the --scan-root layout" in capsys.readouterr().err
    assert _nothing_written(in_tmp)


def test_bad_date_is_a_usage_error(gz, monkeypatch, capsys, in_tmp, fixture):
    code = _main_exit(gz, monkeypatch, ["routine", str(fixture("manifest-routine-cli.yaml")),
                                        "--scan-root", "root", "--date", "2026-13-40"])

    assert code == 2
    assert "--date must be YYYY-MM-DD, not '2026-13-40'" in capsys.readouterr().err
    assert _nothing_written(in_tmp)


def test_confirm_active_abbreviation_is_refused(gz, monkeypatch, capsys, in_tmp, fixture):
    code = _main_exit(gz, monkeypatch, ["routine", str(fixture("manifest-routine-cli.yaml")),
                                        "--out", "out", "--confirm"])

    assert code == 2
    assert "unrecognized arguments: --confirm" in capsys.readouterr().err
    assert _nothing_written(in_tmp)


# ---------------------------------------------------------------------------
# End to end, in a sanitised subprocess where no scanner can resolve
# ---------------------------------------------------------------------------

def _sanitised_env(tmp_path):
    env = os.environ.copy()
    emptybin = tmp_path / "emptybin"
    emptybin.mkdir(exist_ok=True)
    env["PATH"] = str(emptybin)
    for var in ("HOME", "USERPROFILE", "LOCALAPPDATA", "TMPDIR"):
        env[var] = str(tmp_path)
    for var in ("GIZMODUCK_ZAP_HOME", "GIZMODUCK_NIKTO_PL", "GIZMODUCK_TESTSSL_SH",
                "GIZMODUCK_MSYS2_BIN"):
        env.pop(var, None)
    return env


def _write_e2e_manifest(tmp_path):
    manifest = tmp_path / "targets.yaml"
    manifest.write_text(
        "authorized_by: \"ACME-0107 - end-to-end harness\"\n"
        "targets:\n"
        "  - {name: web-a, kind: web, url: 'https://routine-cli.invalid/'}\n"
        f"  - {{name: iac-b, kind: iac, path: {json.dumps(str(tmp_path / 'no-such-dir'))}}}\n",
        encoding="utf-8")
    return manifest


def test_all_tools_missing_exits_4_end_to_end(tmp_path):
    manifest = _write_e2e_manifest(tmp_path)
    out = tmp_path / "out"

    result = subprocess.run([sys.executable, str(_SCRIPT), "routine", str(manifest),
                             "--out", str(out)],
                            capture_output=True, text=True, check=False,
                            env=_sanitised_env(tmp_path), timeout=120)

    cells = list(_cells(out).values())
    assert {c["status"] for c in cells} == {"skipped-missing"}, (
        "a scanner resolved in the sanitised environment: " + repr(cells))
    assert result.returncode == 4, result.stderr
    last = result.stdout.rstrip().splitlines()[-1]
    assert last.startswith("GIZMODUCK_ROUTINE_INCOMPLETE: ")
    assert f"{len(cells)} of {len(cells)} cells did not run" in last
    assert _meta(out)["coverage"]["complete"] is False


def test_usage_error_end_to_end(tmp_path):
    result = subprocess.run([sys.executable, str(_SCRIPT), "routine"],
                            capture_output=True, text=True, check=False,
                            env=_sanitised_env(tmp_path), cwd=str(tmp_path), timeout=120)

    assert result.returncode == 2
    assert "routine needs a manifest" in result.stderr
    assert not (tmp_path / "out").exists()
    assert not (tmp_path / "routine-out").exists()


# ---------------------------------------------------------------------------
# report --run-manifest
# ---------------------------------------------------------------------------

def test_report_run_manifest_renders_coverage(gz, monkeypatch, fixture, tmp_path, capsys):
    md_out = tmp_path / "r.md"
    html_out = tmp_path / "r.html"
    monkeypatch.setattr(sys, "argv", ["gizmoduck.py", "report",
                                      str(fixture("combined-findings.jsonl")),
                                      "--run-manifest", str(fixture("run-manifest.json")),
                                      "--out", str(md_out)])
    gz.main()
    monkeypatch.setattr(sys, "argv", ["gizmoduck.py", "report",
                                      str(fixture("combined-findings.jsonl")),
                                      "--run-manifest", str(fixture("run-manifest.json")),
                                      "--format", "html", "--out", str(html_out)])
    gz.main()

    md = md_out.read_text(encoding="utf-8")
    assert "## Coverage" in md
    assert "skipped-missing" in md
    assert "<table class='coverage'>" in html_out.read_text(encoding="utf-8")


def test_report_without_run_manifest_is_unchanged(gz, monkeypatch, fixture, tmp_path):
    md_out = tmp_path / "r.md"
    monkeypatch.setattr(sys, "argv", ["gizmoduck.py", "report",
                                      str(fixture("combined-findings.jsonl")),
                                      "--out", str(md_out)])
    gz.main()

    findings = gz.load(str(fixture("combined-findings.jsonl")))
    expected = gz.cmd_report(findings, gz.SEV_NUM["medium"], "Nuclei Vulnerability Report")
    text = md_out.read_text(encoding="utf-8")
    assert "## Coverage" not in text
    assert text == expected


def test_report_run_manifest_on_flat_input_renders_the_flat_golden(gz, monkeypatch, fixture,
                                                                   tmp_path):
    md_out = tmp_path / "r.md"
    monkeypatch.setattr(sys, "argv", ["gizmoduck.py", "report", str(fixture("nuclei.jsonl")),
                                      "--run-manifest", str(fixture("run-manifest.json")),
                                      "--min-severity", "info",
                                      "--title", "Flat Regression Report",
                                      "--out", str(md_out)])
    gz.main()

    golden = fixture("flat-report-golden.md").read_text(encoding="utf-8")
    assert md_out.read_text(encoding="utf-8") == golden


@pytest.mark.parametrize("case", ["missing", "not-json", "no-cells"])
def test_report_unreadable_run_manifest_is_a_usage_error(gz, monkeypatch, fixture, tmp_path,
                                                         capsys, case):
    bad = tmp_path / "bad.json"
    if case == "not-json":
        bad.write_text("{not json", encoding="utf-8")
    elif case == "no-cells":
        bad.write_text('{"authorized_by": "x"}', encoding="utf-8")
    md_out = tmp_path / "r.md"

    code = _main_exit(gz, monkeypatch, ["report", str(fixture("combined-findings.jsonl")),
                                        "--run-manifest", str(bad), "--out", str(md_out)])

    assert code == 2
    assert "--run-manifest:" in capsys.readouterr().err
    assert not md_out.exists()
