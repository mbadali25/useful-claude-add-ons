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
      -> test_scan_meta_write_is_complete_then_renamed and
         test_atomic_write_keeps_the_original_when_the_write_itself_fails
         (both make the write itself fail half-way; failing only in
         `_scan_meta_text` or only in os.replace cannot tell the two apart)
  (e) the output directory created before load_manifest
      -> test_manifest_errors_write_nothing[no-auth]
  (f) --run-manifest parsed and not passed to cmd_report
      -> test_report_run_manifest_renders_coverage
  (g) the exit-4 branch returning 0
      -> test_all_tools_missing_exits_4_end_to_end
  (h) `--replace` removing every child directory again
      -> test_replace_removes_only_the_directories_the_earlier_run_named and
         test_replace_leaves_a_symlink_the_earlier_run_did_not_name
         (neighbour test_replace_rewrites_the_set_and_removes_stale_target_dirs:
         a named directory is still removed)
  (i) an earlier scan-meta.json with no `targets` read as "nothing to remove",
      or its target names trusted as paths
      -> test_replace_refuses_when_it_cannot_tell_what_the_earlier_run_owns
         [no-targets] / [nested]
  (j) the earlier scan-meta.json kept until the new run finishes
      -> test_an_interrupted_replace_leaves_no_scan_meta_from_the_earlier_run
  (k) the manifest shape check dropped, or its plain-directory-name rule
      -> test_manifest_errors_write_nothing (every wrong-type case) /
         [dotdot-name] and [slash-name]
  (l) the default date hard-coded, or the local date
      -> test_scan_root_date_defaults_to_the_utc_date
  (m) `import routine` outside its ImportError handler
      -> test_routine_without_pyyaml_is_a_usage_error_naming_it
  (n) a named target directory that is a symlink removed through
      -> test_replace_refuses_a_target_directory_that_is_a_symlink
  (o) _sanitised_env without PYTHONUSERBASE
      -> test_sanitised_env_keeps_the_user_site
  (p) a target directory that already exists, and that no earlier run in
      the directory owns, written into anyway (the neighbour of (h): such a
      directory becomes "the earlier run's" and the next --replace removes it)
      -> test_a_target_directory_no_earlier_run_owns_is_refused [plain] /
         [symlink] and
         test_replace_refuses_a_new_target_directory_the_earlier_run_did_not_own
  (q) a target named after a file routine writes in the output directory
      -> test_manifest_errors_write_nothing[reserved-name] / [reserved-name-case]
  (r) a file routine writes (report.md, findings.jsonl, ...) that already
      exists in a directory with no scan-meta.json, overwritten anyway (the
      neighbour of (p) for files: `--out .` in a checkout replaces the
      operator's own report.md)
      -> test_a_routine_file_no_earlier_run_owns_is_refused [report.md] /
         [findings.jsonl] / [symlink]
  (s) the atomic write without newline="\\n" or without fsync before the swap
      -> test_atomic_write_states_newline_and_fsyncs_before_the_swap
  (t) the link check that misses a junction (Path.is_symlink alone)
      -> test_replace_refuses_a_target_directory_that_is_a_junction
  (u) the atomic write leaving mkstemp's 0600, or not keeping an existing
      file's mode
      -> test_atomic_write_keeps_the_mode_a_plain_write_would_give [None] /
         [416]
  (v) the PyYAML install hint printing the interpreter path unquoted
      -> test_missing_pyyaml_hint_quotes_the_interpreter_path
  Review round 2 (codex), each confirmed red against the code it fixed:
  (w) an active-scan gate option accepted as a string ("false" is truthy)
      -> test_manifest_errors_write_nothing[gate-option-string] /
         [sqlmap-option-string]
  (x) the manifest checked from one read and loaded from a second
      -> test_the_manifest_is_read_once
  (y) the output-directory lock not exclusive, or not released
      -> test_a_run_already_holding_the_directory_is_refused,
         test_a_second_run_started_mid_run_is_refused_and_the_lock_released,
         test_the_lock_is_released_when_the_run_raises
  (z) report.pdf rendered straight to its final name, or wkhtmltopdf unbounded
      -> test_report_pdf_is_rendered_to_a_temp_then_renamed,
         test_html_to_pdf_bounds_wkhtmltopdf_and_falls_through_on_timeout
  (aa) a run-manifest cell's shape unchecked
      -> test_report_unreadable_run_manifest_is_a_usage_error[cell-*]
  (ab) os.replace not retried on a transient PermissionError
      -> test_atomic_write_retries_a_transient_permission_error
  (ac) the target-name rule loosened: no allowlist, Windows device names or
      case-variant duplicates
      -> test_manifest_errors_write_nothing[newline-name] / [pipe-name] /
         [trailing-dot-name] / [windows-device-name] / [case-duplicate-name]
"""
import datetime
import importlib.util
import json
import os
import shutil
import site
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
    monkeypatch.setattr(gz, "html_to_pdf", lambda html, out, **_kw: False)


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


def _earlier_run(gz, tmp_path, names=("site-a", "site-b")):
    """A complete earlier run in `out/`, made by cmd_routine itself: the only
    honest way to get a scan-meta.json that names the targets it owns."""
    manifest = tmp_path / "earlier.yaml"
    rows = "".join(f"  - {{name: {n}, kind: web, url: 'https://{n}.invalid/'}}\n" for n in names)
    manifest.write_text(f"authorized_by: t\ntargets:\n{rows}", encoding="utf-8")
    out = tmp_path / "out"
    rc = gz.cmd_routine(str(manifest), str(out), registry=_registry(), date=_DATE, confirm=True)
    assert rc == 0
    for n in names:
        (out / n).mkdir(exist_ok=True)
        (out / n / "raw.txt").write_text("earlier", encoding="utf-8")
    return out


def test_replace_rewrites_the_set_and_removes_stale_target_dirs(gz, fixture, tmp_path):
    out = _earlier_run(gz, tmp_path, names=("old-target",))
    (out / "report.pdf").write_bytes(b"stale pdf")

    rc = _run(gz, fixture, tmp_path, _registry(), confirm=True, replace=True)

    assert rc == 0
    assert not (out / "old-target").exists()
    assert not (out / "report.pdf").exists()
    assert [t["name"] for t in _meta(out)["targets"]] == ["site-a", "site-b"]


def test_replace_removes_only_the_directories_the_earlier_run_named(gz, fixture, tmp_path):
    out = _earlier_run(gz, tmp_path)
    for mine in (".git", "plugin", "notes"):
        (out / mine).mkdir()
        (out / mine / "keep.txt").write_text(mine, encoding="utf-8")

    rc = _run(gz, fixture, tmp_path, _registry(), confirm=True, replace=True)

    assert rc == 0
    assert not (out / "site-a" / "raw.txt").exists()
    assert [(out / m / "keep.txt").read_text(encoding="utf-8")
            for m in (".git", "plugin", "notes")] == [".git", "plugin", "notes"]


_UNREADABLE_EARLIER_META = {
    "not-json": b"SENTINEL",
    "schema-0": b'{"schema": 0, "targets": [{"name": "site-a"}]}',
    "no-targets": b'{"schema": 1}',
    "targets-not-a-list": b'{"schema": 1, "targets": {"name": "site-a"}}',
    "nameless-target": b'{"schema": 1, "targets": [{"kind": "web"}]}',
    "dotdot": b'{"schema": 1, "targets": [{"name": ".."}]}',
    "absolute": lambda tmp: json.dumps(
        {"schema": 1, "targets": [{"name": str(tmp / "precious")}]}).encode(),
    "nested": b'{"schema": 1, "targets": [{"name": "a/b"}]}',
}


@pytest.mark.parametrize("case", list(_UNREADABLE_EARLIER_META))
def test_replace_refuses_when_it_cannot_tell_what_the_earlier_run_owns(gz, fixture, tmp_path,
                                                                      capsys, case):
    """An absolute name points into tmp_path, never at a system path: if this
    refusal ever regresses, what gets removed is the test's own sentinel."""
    out = tmp_path / "out"
    (out / "site-a").mkdir(parents=True)
    (out / "site-a" / "raw.txt").write_text("keep", encoding="utf-8")
    (tmp_path / "precious").mkdir()
    (tmp_path / "precious" / "keep.txt").write_text("keep", encoding="utf-8")
    (out / "report.md").write_text("earlier report", encoding="utf-8")
    earlier = _UNREADABLE_EARLIER_META[case]
    earlier = earlier(tmp_path) if callable(earlier) else earlier
    (out / "scan-meta.json").write_bytes(earlier)
    reg = _registry()

    rc = _run(gz, fixture, tmp_path, reg, confirm=True, replace=True)

    assert rc == 2
    assert "cannot tell which directories the earlier run owns" in capsys.readouterr().err
    assert (out / "scan-meta.json").read_bytes() == earlier
    assert (out / "report.md").read_text(encoding="utf-8") == "earlier report"
    assert (out / "site-a" / "raw.txt").read_text(encoding="utf-8") == "keep"
    assert (tmp_path / "precious" / "keep.txt").is_file()
    assert all(a.run_calls == [] for a in reg.ADAPTERS.values())


def _symlink_or_skip(link, target):
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")


def test_replace_refuses_a_target_directory_that_is_a_symlink(gz, fixture, tmp_path, capsys):
    out = _earlier_run(gz, tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "precious.txt").write_text("precious", encoding="utf-8")
    shutil.rmtree(out / "site-b")
    _symlink_or_skip(out / "site-b", elsewhere)

    rc = _run(gz, fixture, tmp_path, _registry(), confirm=True, replace=True)

    assert rc == 2
    assert "is a symlink" in capsys.readouterr().err
    assert (elsewhere / "precious.txt").read_text(encoding="utf-8") == "precious"
    assert (out / "report.md").is_file()
    assert (out / "site-a" / "raw.txt").is_file()
    assert _meta(out)["coverage"]["complete"] is True


def test_replace_leaves_a_symlink_the_earlier_run_did_not_name(gz, fixture, tmp_path):
    out = _earlier_run(gz, tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "precious.txt").write_text("precious", encoding="utf-8")
    _symlink_or_skip(out / "link", elsewhere)

    rc = _run(gz, fixture, tmp_path, _registry(), confirm=True, replace=True)

    assert rc == 0
    assert (out / "link" / "precious.txt").read_text(encoding="utf-8") == "precious"


@pytest.mark.parametrize("shape", ["plain", "symlink"])
def test_a_target_directory_no_earlier_run_owns_is_refused(gz, fixture, tmp_path, capsys, shape):
    """A directory routine did not create is never adopted as a target
    directory: an earlier run would then "own" it, and --replace removes it."""
    out = tmp_path / "out"
    out.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "keep.txt").write_text("keep", encoding="utf-8")
    if shape == "plain":
        (out / "site-a").mkdir()
        (out / "site-a" / "keep.txt").write_text("keep", encoding="utf-8")
        kept = out / "site-a" / "keep.txt"
    else:
        _symlink_or_skip(out / "site-a", elsewhere)
        kept = elsewhere / "keep.txt"
    reg = _registry()

    rc = _run(gz, fixture, tmp_path, reg, confirm=True)

    assert rc == 2
    assert "no earlier run in this directory owns it" in capsys.readouterr().err
    assert kept.read_text(encoding="utf-8") == "keep"
    assert sorted(p.name for p in out.iterdir()) == ["site-a"]
    assert all(a.run_calls == [] for a in reg.ADAPTERS.values())


@pytest.mark.parametrize("shape", ["report.md", "findings.jsonl", "symlink"])
def test_a_routine_file_no_earlier_run_owns_is_refused(gz, fixture, tmp_path, capsys, shape):
    """With no scan-meta.json, no earlier run owns the directory, so a file
    named like one routine writes is the operator's, never overwritten."""
    out = tmp_path / "out"
    out.mkdir()
    if shape == "symlink":
        elsewhere = tmp_path / "elsewhere.md"
        elsewhere.write_text("keep", encoding="utf-8")
        _symlink_or_skip(out / "report.md", elsewhere)
        kept, name = elsewhere, "report.md"
    else:
        (out / shape).write_text("keep", encoding="utf-8")
        kept, name = out / shape, shape
    reg = _registry()

    rc = _run(gz, fixture, tmp_path, reg, confirm=True)

    assert rc == 2
    assert "no earlier run in this directory owns it" in capsys.readouterr().err
    assert kept.read_text(encoding="utf-8") == "keep"
    assert sorted(p.name for p in out.iterdir()) == [name]
    assert all(a.run_calls == [] for a in reg.ADAPTERS.values())


def test_replace_refuses_a_new_target_directory_the_earlier_run_did_not_own(gz, fixture,
                                                                           tmp_path, capsys):
    out = _earlier_run(gz, tmp_path, names=("site-a",))
    earlier_meta = (out / "scan-meta.json").read_bytes()
    (out / "site-b").mkdir()
    (out / "site-b" / "keep.txt").write_text("keep", encoding="utf-8")
    reg = _registry()

    rc = _run(gz, fixture, tmp_path, reg, confirm=True, replace=True)

    assert rc == 2
    assert "no earlier run in this directory owns it" in capsys.readouterr().err
    assert (out / "scan-meta.json").read_bytes() == earlier_meta
    assert (out / "site-a" / "raw.txt").is_file()
    assert (out / "site-b" / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert all(a.run_calls == [] for a in reg.ADAPTERS.values())


def test_an_interrupted_replace_leaves_no_scan_meta_from_the_earlier_run(gz, fixture, tmp_path):
    out = _earlier_run(gz, tmp_path)
    assert _meta(out)["coverage"]["complete"] is True

    def _interrupt(target, outdir, opts):
        raise KeyboardInterrupt

    reg = _registry(nuclei=FakeAdapter("nuclei", ["web", "host"], run_fn=_interrupt))
    with pytest.raises(KeyboardInterrupt):
        _run(gz, fixture, tmp_path, reg, confirm=True, replace=True)

    assert not (out / "scan-meta.json").exists()
    assert list(out.glob("scan-meta.json*")) == []


def test_scan_root_builds_the_dated_path(gz, fixture, tmp_path):
    root = tmp_path / "module"

    rc = gz.cmd_routine(str(fixture("manifest-routine-cli.yaml")), None, scan_root=str(root),
                        date=_DATE, registry=_registry(), confirm=True)

    dated = root / "docs" / "security-scans" / "2026-09-29"
    assert rc == 0
    assert _meta(dated)["date"] == "2026-09-29"


def test_scan_root_date_defaults_to_the_utc_date(gz, fixture, tmp_path, monkeypatch):
    utc_now = datetime.datetime(2031, 1, 2, 0, 30, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(gz, "_utc_now", lambda: utc_now)
    root = tmp_path / "module"

    rc = gz.cmd_routine(str(fixture("manifest-routine-cli.yaml")), None, scan_root=str(root),
                        date=None, registry=_registry(), confirm=True)

    assert rc == 0
    assert _meta(root / "docs" / "security-scans" / "2031-01-02")["date"] == "2031-01-02"


def _half_write_then_fail(gz, monkeypatch, basename):
    """Make every write-mode `open` in gizmoduck whose file name starts with
    `basename` write half its text and then raise ENOSPC, the way a full disk
    does. It is injected as gizmoduck's own `open`, so it reaches whatever
    open call the writer makes: the temp file of the atomic helper, or the
    destination itself if that helper is ever replaced by a plain
    `open(path, "w")`."""
    real_open = open

    class _HalfWriter:
        def __init__(self, fh):
            self._fh = fh

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._fh.close()
            return False

        def write(self, text):
            self._fh.write(text[: len(text) // 2])
            self._fh.flush()
            raise OSError(28, "No space left on device")

    def _open(file, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        # The caller's own `with` closes it: this stands in for `open` itself.
        fh = real_open(file, *args, **kwargs)  # pylint: disable=consider-using-with
        if "w" in mode and Path(file).name.startswith(basename):
            return _HalfWriter(fh)
        return fh

    monkeypatch.setattr(gz, "open", _open, raising=False)


def test_scan_meta_write_is_complete_then_renamed(gz, fixture, tmp_path, monkeypatch):
    out = tmp_path / "out"
    _half_write_then_fail(gz, monkeypatch, "scan-meta.json")

    with pytest.raises(OSError, match="No space left"):
        _run(gz, fixture, tmp_path, _registry(), confirm=True)

    assert list(out.glob("scan-meta.json*")) == []


def test_atomic_write_keeps_the_original_when_the_write_itself_fails(gz, tmp_path, monkeypatch):
    target = tmp_path / "report.md"
    target.write_bytes(b"ORIGINAL")
    _half_write_then_fail(gz, monkeypatch, "report.md")

    with pytest.raises(OSError, match="No space left"):
        gz._atomic_write_text(target, "new text that never lands")

    assert target.read_bytes() == b"ORIGINAL"
    assert list(tmp_path.iterdir()) == [target]


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


def test_atomic_write_states_newline_and_fsyncs_before_the_swap(gz, tmp_path, monkeypatch):
    """PYTHON-01/04: the temp is opened with newline="\\n" (a Windows run must
    write LF, which a Linux run cannot show by bytes alone), and fsynced
    before os.replace makes it the destination."""
    target = tmp_path / "report.md"
    events = []
    real_open, real_fsync, real_replace = open, gz.os.fsync, gz.os.replace

    def _open(file, *args, **kwargs):
        if "w" in (args[0] if args else kwargs.get("mode", "r")):
            events.append(("open", Path(file).parent, kwargs.get("newline")))
        return real_open(file, *args, **kwargs)  # pylint: disable=consider-using-with

    def _fsync(fd):
        events.append(("fsync",))
        return real_fsync(fd)

    def _replace(src, dst):
        events.append(("replace",))
        return real_replace(src, dst)

    monkeypatch.setattr(gz, "open", _open, raising=False)
    monkeypatch.setattr(gz.os, "fsync", _fsync)
    monkeypatch.setattr(gz.os, "replace", _replace)

    gz._atomic_write_text(target, "a\nb\n")

    assert events == [("open", tmp_path, "\n"), ("fsync",), ("replace",)]
    assert target.read_bytes() == b"a\nb\n"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits; Windows chmod sets read-only only")
@pytest.mark.parametrize("existing", [None, 0o640])
def test_atomic_write_keeps_the_mode_a_plain_write_would_give(gz, tmp_path, existing):
    """mkstemp creates its file 0600. A new report gets the umask's mode, as a
    plain open(path, "w") would give it, and an existing one keeps its own."""
    target = tmp_path / "report.md"
    if existing is not None:
        target.write_text("old", encoding="utf-8")
        target.chmod(existing)
    old_umask = os.umask(0o022)
    try:
        gz._atomic_write_text(target, "new")
    finally:
        os.umask(old_umask)

    assert target.stat().st_mode & 0o777 == (existing if existing is not None else 0o644)


def test_missing_pyyaml_hint_quotes_the_interpreter_path(gz, fixture, tmp_path, capsys,
                                                         monkeypatch):
    """The printed install command must survive a path with a space in it
    (C:\\Program Files\\Python312\\python.exe, /opt/my python/bin/python3)."""
    monkeypatch.setitem(sys.modules, "routine", None)
    monkeypatch.setattr(gz.sys, "executable", "/opt/my python/bin/python3")

    rc = gz.cmd_routine(str(fixture), str(tmp_path / "out"))

    assert rc == 2
    err = capsys.readouterr().err
    expected = (subprocess.list2cmdline(["/opt/my python/bin/python3"]) if os.name == "nt"
                else "'/opt/my python/bin/python3'")
    assert f"{expected} -m pip install pyyaml" in err
    assert not (tmp_path / "out").exists()


def test_replace_refuses_a_target_directory_that_is_a_junction(gz, fixture, tmp_path, capsys,
                                                                monkeypatch):
    """PYTHON-13: a Windows junction is not a symlink to Path.is_symlink, but
    removing through one reaches outside the output directory all the same.
    Linux cannot make a junction, so os.path.isjunction is faked for the one
    path; NOT RUN ON WINDOWS against a real junction."""
    out = _earlier_run(gz, tmp_path, names=("site-a",))
    earlier_meta = (out / "scan-meta.json").read_bytes()
    junction = str(out / "site-a")
    monkeypatch.setattr(gz.os.path, "isjunction", lambda p: str(p) == junction, raising=False)

    rc = _run(gz, fixture, tmp_path, _registry(), confirm=True, replace=True)

    assert rc == 2
    assert "symlink or junction" in capsys.readouterr().err
    assert (out / "scan-meta.json").read_bytes() == earlier_meta
    assert (out / "site-a").is_dir()


def test_a_true_gate_option_still_enables_its_tool(gz, fixture, tmp_path):
    """The must-allow side of the gate-option check: a real boolean passes."""
    rc = _run(gz, fixture, tmp_path, _registry(), confirm=True)

    assert rc == 0
    assert _cells(tmp_path / "out")[("site-a", "sqlmap")]["status"].startswith("ran")


def test_the_manifest_is_read_once(gz, fixture, tmp_path, monkeypatch):
    """The checked bytes are the loaded bytes: a manifest swapped after the
    shape check (to a target named ../escape) is never what runs."""
    manifest = tmp_path / "m.yaml"
    manifest.write_bytes(Path(fixture("manifest-routine-cli.yaml")).read_bytes())
    real_check = gz._check_manifest_shape

    def _check_then_swap(*args, **kwargs):
        result = real_check(*args, **kwargs)
        manifest.write_text("authorized_by: t\ntargets:\n"
                            "  - {name: ../escape, kind: web, url: 'https://e.invalid/'}\n",
                            encoding="utf-8")
        return result

    monkeypatch.setattr(gz, "_check_manifest_shape", _check_then_swap)

    rc = gz.cmd_routine(str(manifest), str(tmp_path / "out"), registry=_registry(),
                        date=_DATE, confirm=True)

    assert rc == 0
    assert [t["name"] for t in _meta(tmp_path / "out")["targets"]] == ["site-a", "site-b"]
    assert not (tmp_path / "escape").exists()


def test_a_run_already_holding_the_directory_is_refused(gz, fixture, tmp_path, capsys):
    """Two runs never share an output directory: the second finds the first's
    lock and exits 2 without running a scanner or touching the lock."""
    out = tmp_path / "out"
    out.mkdir()
    (out / gz.ROUTINE_LOCK).write_text("held", encoding="utf-8")
    reg = _registry()

    rc = _run(gz, fixture, tmp_path, reg, confirm=True)

    assert rc == 2
    assert "another routine run holds" in capsys.readouterr().err
    assert sorted(p.name for p in out.iterdir()) == [gz.ROUTINE_LOCK]
    assert (out / gz.ROUTINE_LOCK).read_text(encoding="utf-8") == "held"
    assert all(a.run_calls == [] for a in reg.ADAPTERS.values())


def test_a_second_run_started_mid_run_is_refused_and_the_lock_released(gz, fixture, tmp_path,
                                                                       capsys):
    """The race itself: a second cmd_routine on the same directory, started
    while the first is inside its scanners, is refused; the first finishes and
    releases its lock."""
    inner = {}

    def _nuclei_starts_a_second_run(target, outdir, opts):
        inner["rc"] = _run(gz, fixture, tmp_path, _registry(), confirm=True)
        return _ok("nuclei-raw")(target, outdir, opts)

    reg = _registry(nuclei=FakeAdapter("nuclei", ["web", "host"],
                                       run_fn=_nuclei_starts_a_second_run))

    rc = _run(gz, fixture, tmp_path, reg, confirm=True)

    assert inner["rc"] == 2
    assert "another routine run holds" in capsys.readouterr().err
    assert rc == 0
    assert not (tmp_path / "out" / gz.ROUTINE_LOCK).exists()


def test_the_lock_is_released_when_the_run_raises(gz, fixture, tmp_path, monkeypatch):
    def _boom(*_a, **_kw):
        raise RuntimeError("scanner exploded")

    monkeypatch.setattr(gz, "load", _boom)

    with pytest.raises(RuntimeError, match="scanner exploded"):
        _run(gz, fixture, tmp_path, _registry(), confirm=True)

    assert not (tmp_path / "out" / gz.ROUTINE_LOCK).exists()


def test_report_pdf_is_rendered_to_a_temp_then_renamed(gz, fixture, tmp_path, monkeypatch):
    out = tmp_path / "out"
    seen = {}

    def _render(html, path, **kwargs):
        seen["path"], seen["kwargs"] = Path(path), kwargs
        Path(path).write_bytes(b"%PDF-complete")
        return True

    monkeypatch.setattr(gz, "html_to_pdf", _render)

    rc = _run(gz, fixture, tmp_path, _registry(), confirm=True)

    assert rc == 0
    assert seen["path"].parent == out and seen["path"].name != "report.pdf"
    assert seen["kwargs"].get("timeout") == gz.PDF_TIMEOUT_SECONDS
    assert (out / "report.pdf").read_bytes() == b"%PDF-complete"
    assert not seen["path"].exists()
    assert _meta(out)["files"]["report_pdf"] == "report.pdf"


def test_a_failed_pdf_render_leaves_no_partial_pdf(gz, fixture, tmp_path, monkeypatch):
    out = tmp_path / "out"

    def _half_render(html, path, **_kw):
        Path(path).write_bytes(b"%PDF-trunc")
        return False

    monkeypatch.setattr(gz, "html_to_pdf", _half_render)

    rc = _run(gz, fixture, tmp_path, _registry(), confirm=True)

    assert rc == 0
    assert not (out / "report.pdf").exists()
    assert not [p for p in out.iterdir() if p.name.startswith("report.pdf")]
    assert _meta(out)["files"]["report_pdf"] is None


def test_html_to_pdf_bounds_wkhtmltopdf_and_falls_through_on_timeout(scripts_dir, tmp_path,
                                                                     monkeypatch):
    """A fresh copy of the module: the autouse fixture stubs html_to_pdf on `gz`."""
    spec = importlib.util.spec_from_file_location("gz_pdf", scripts_dir / "gizmoduck.py")
    gz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gz)
    calls = []

    def _hangs(argv, **kwargs):
        calls.append(kwargs.get("timeout"))
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(gz.shutil, "which", lambda name: "/fake/wkhtmltopdf")
    monkeypatch.setattr(gz.subprocess, "run", _hangs)
    monkeypatch.setitem(sys.modules, "weasyprint", None)

    ok = gz.html_to_pdf("<p>x</p>", str(tmp_path / "r.pdf"), timeout=7)

    assert ok is False
    assert calls == [7]
    assert not (tmp_path / "r.pdf").exists()


def test_atomic_write_retries_a_transient_permission_error(gz, tmp_path, monkeypatch):
    """Windows: antivirus or a reader briefly holding the destination makes
    os.replace raise PermissionError; a bounded retry gets past it."""
    target = tmp_path / "report.md"
    real_replace = gz.os.replace
    attempts = []

    def _held_once(src, dst):
        attempts.append(1)
        if len(attempts) == 1:
            raise PermissionError(13, "The process cannot access the file")
        return real_replace(src, dst)

    monkeypatch.setattr(gz.os, "replace", _held_once)
    monkeypatch.setattr(gz.time, "sleep", lambda _s: None)

    gz._atomic_write_text(target, "new")

    assert len(attempts) == 2
    assert target.read_text(encoding="utf-8") == "new"
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_write_gives_up_after_a_bounded_number_of_attempts(gz, tmp_path, monkeypatch):
    target = tmp_path / "report.md"
    target.write_bytes(b"ORIGINAL")
    attempts = []

    def _always_held(src, dst):
        attempts.append(1)
        raise PermissionError(13, "The process cannot access the file")

    monkeypatch.setattr(gz.os, "replace", _always_held)
    monkeypatch.setattr(gz.time, "sleep", lambda _s: None)

    with pytest.raises(PermissionError):
        gz._atomic_write_text(target, "new")

    assert len(attempts) == gz.REPLACE_ATTEMPTS
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
    "top-level-list": ("- {name: a, kind: web, url: 'https://a.invalid/'}\n",
                       "the manifest must be a mapping"),
    "auth-not-a-string": ("authorized_by: 123\ntargets: []\n",
                          "'authorized_by' must be a string"),
    "targets-not-a-list": ("authorized_by: t\ntargets: {a: 1}\n", "'targets' must be a list"),
    "target-not-a-mapping": ("authorized_by: t\ntargets: [foo]\n",
                             "targets[0] must be a mapping"),
    "no-name": ("authorized_by: t\ntargets:\n  - {kind: web, url: 'https://a.invalid/'}\n",
                "targets[0] needs a 'name'"),
    "int-name": ("authorized_by: t\ntargets:\n  - {name: 1, kind: web, url: 'https://a.invalid/'}\n",
                 "targets[0] needs a 'name'"),
    "dotdot-name": (("authorized_by: t\ntargets:\n"
                     "  - {name: '..', kind: web, url: 'https://a.invalid/'}\n"),
                    "targets[0] needs a 'name'"),
    "slash-name": (("authorized_by: t\ntargets:\n"
                    "  - {name: 'a/b', kind: web, url: 'https://a.invalid/'}\n"),
                   "targets[0] needs a 'name'"),
    "kind-not-a-string": ("authorized_by: t\ntargets:\n  - {name: a, kind: [web], url: x}\n",
                          "targets[0] 'kind' must be a string"),
    "url-not-a-string": ("authorized_by: t\ntargets:\n  - {name: a, kind: web, url: 5}\n",
                         "targets[0] 'url' must be a string"),
    "tools-not-a-list": (("authorized_by: t\ntargets:\n"
                          "  - {name: a, kind: web, url: 'https://a.invalid/', tools: 5}\n"),
                         "targets[0] 'tools' must be a list of tool names"),
    "options-not-a-mapping": (("authorized_by: t\ntargets:\n"
                               "  - {name: a, kind: web, url: 'https://a.invalid/', options: 5}\n"),
                              "targets[0] 'options' must be a mapping"),
    "reserved-name": (("authorized_by: t\ntargets:\n"
                       "  - {name: report.md, kind: web, url: 'https://a.invalid/'}\n"),
                      "is a file routine writes in the output directory"),
    "reserved-name-case": (("authorized_by: t\ntargets:\n"
                            "  - {name: Scan-Meta.JSON, kind: web, url: 'https://a.invalid/'}\n"),
                           "is a file routine writes in the output directory"),
    "missing-file": (None, "No such file or directory"),
    "gate-option-string": (("authorized_by: t\ntargets:\n"
                            "  - {name: a, kind: web, url: 'https://a.invalid/',"
                            " options: {nmap_vuln: 'false'}}\n"),
                           "targets[0] option 'nmap_vuln' must be true or false"),
    "sqlmap-option-string": (("authorized_by: t\ntargets:\n"
                              "  - {name: a, kind: web, url: 'https://a.invalid/',"
                              " options: {sqlmap: 'yes'}}\n"),
                             "targets[0] option 'sqlmap' must be true or false"),
    "case-duplicate-name": (("authorized_by: t\ntargets:\n"
                             "  - {name: site, kind: web, url: 'https://a.invalid/'}\n"
                             "  - {name: SITE, kind: web, url: 'https://b.invalid/'}\n"),
                            "differ only in case"),
    "windows-device-name": (("authorized_by: t\ntargets:\n"
                             "  - {name: Con, kind: web, url: 'https://a.invalid/'}\n"),
                            "reserved on Windows"),
    "windows-device-name-ext": (("authorized_by: t\ntargets:\n"
                                 "  - {name: nul.txt, kind: web, url: 'https://a.invalid/'}\n"),
                                "reserved on Windows"),
    "trailing-dot-name": (("authorized_by: t\ntargets:\n"
                           "  - {name: 'a.', kind: web, url: 'https://a.invalid/'}\n"),
                          "targets[0] needs a 'name'"),
    "newline-name": (("authorized_by: t\ntargets:\n"
                      "  - {name: \"a\\n## Forged\", kind: web, url: 'https://a.invalid/'}\n"),
                     "targets[0] needs a 'name'"),
    "pipe-name": (("authorized_by: t\ntargets:\n"
                   "  - {name: 'a|b', kind: web, url: 'https://a.invalid/'}\n"),
                  "targets[0] needs a 'name'"),
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


def test_routine_without_pyyaml_is_a_usage_error_naming_it(gz, fixture, tmp_path, capsys,
                                                         monkeypatch):
    monkeypatch.delitem(sys.modules, "routine", raising=False)
    monkeypatch.setitem(sys.modules, "yaml", None)

    rc = gz.cmd_routine(str(fixture("manifest-routine-cli.yaml")), str(tmp_path / "out"),
                        registry=_registry(), date=_DATE)

    assert rc == 2
    assert "needs PyYAML" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


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
    # HOME moved, so the user site would move with it and hide a PyYAML
    # installed with `pip install --user`. Pin it where this interpreter found
    # it. Scanners resolve through PATH, which stays empty.
    env.setdefault("PYTHONUSERBASE", site.getuserbase())
    return env


def test_sanitised_env_keeps_the_user_site(tmp_path):
    probe = subprocess.run([sys.executable, "-c",
                            "import site; print(site.getusersitepackages())"],
                           capture_output=True, text=True, check=True,
                           env=_sanitised_env(tmp_path), timeout=60)

    assert probe.stdout.strip() == site.getusersitepackages()


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

    assert (out / "run-manifest.json").is_file(), (
        f"routine wrote no run-manifest.json (exit {result.returncode}): {result.stderr}")
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


@pytest.mark.parametrize("case", ["missing", "not-json", "no-cells", "cell-not-a-mapping",
                                  "cell-missing-tool", "cell-status-not-a-string",
                                  "cell-errors-not-a-list"])
def test_report_unreadable_run_manifest_is_a_usage_error(gz, monkeypatch, fixture, tmp_path,
                                                         capsys, case):
    bad = tmp_path / "bad.json"
    if case == "not-json":
        bad.write_text("{not json", encoding="utf-8")
    elif case == "no-cells":
        bad.write_text('{"authorized_by": "x"}', encoding="utf-8")
    elif case == "cell-not-a-mapping":
        bad.write_text('{"cells": [1]}', encoding="utf-8")
    elif case == "cell-missing-tool":
        bad.write_text('{"cells": [{"target": "a", "status": "ran"}]}', encoding="utf-8")
    elif case == "cell-status-not-a-string":
        bad.write_text('{"cells": [{"target": "a", "tool": "t", "status": 1}]}',
                       encoding="utf-8")
    elif case == "cell-errors-not-a-list":
        bad.write_text('{"cells": [{"target": "a", "tool": "t", "status": "ran", '
                       '"errors": 5}]}', encoding="utf-8")
    md_out = tmp_path / "r.md"

    code = _main_exit(gz, monkeypatch, ["report", str(fixture("combined-findings.jsonl")),
                                        "--run-manifest", str(bad), "--out", str(md_out)])

    assert code == 2
    assert "--run-manifest:" in capsys.readouterr().err
    assert not md_out.exists()


# ---------------------------------------------------------------------------
# T-0108: Nuclei's safe defaults in a routine manifest
# ---------------------------------------------------------------------------

def _nuclei_registry():
    """The `web` default with a fake nuclei carrying the REAL adapter's
    ACTIVE_OPTS, so `nuclei_intrusive` is a gate key exactly as it is in the
    shipped registry."""
    from scanners import nuclei as real_nuclei
    return _registry(nuclei=FakeAdapter("nuclei", ["web", "host"],
                                        active_opts=list(real_nuclei.ACTIVE_OPTS),
                                        run_fn=_ok("nuclei-raw")))


def _bad_nuclei_manifest(gz, tmp_path, capsys, options):
    manifest = tmp_path / "m.yaml"
    manifest.write_text("authorized_by: t\ntargets:\n"
                        "  - {name: a, kind: web, url: 'https://a.invalid/', "
                        f"options: {options}}}\n", encoding="utf-8")
    reg = _nuclei_registry()
    rc = gz.cmd_routine(str(manifest), str(tmp_path / "out"), registry=reg, date=_DATE)
    err = capsys.readouterr().err
    assert rc == 2
    assert "routine: manifest refused" in err
    assert not (tmp_path / "out").exists()
    assert all(a.run_calls == [] for a in reg.ADAPTERS.values())
    return err


def test_manifest_nuclei_intrusive_must_be_a_boolean(gz, tmp_path, capsys):
    err = _bad_nuclei_manifest(gz, tmp_path, capsys, "{nuclei_intrusive: 'false'}")
    assert "option 'nuclei_intrusive' must be true or false" in err


@pytest.mark.parametrize("value", ["0", "-1", "'50'", "true", "1.5"])
def test_manifest_nuclei_rate_limit_must_be_a_positive_integer(gz, tmp_path, capsys, value):
    err = _bad_nuclei_manifest(gz, tmp_path, capsys, f"{{nuclei_rate_limit: {value}}}")
    assert "option 'nuclei_rate_limit' must be an integer of 1 or more" in err


@pytest.mark.parametrize("extra", ["-itags dos", "--rl=500", "-exclude-tags x", "-dast"])
def test_manifest_refuses_nuclei_safety_flags_in_extra(gz, tmp_path, capsys, extra):
    err = _bad_nuclei_manifest(gz, tmp_path, capsys, f"{{extra: '{extra}'}}")
    assert "nuclei_intrusive" in err and "nuclei_rate_limit" in err


def test_manifest_allows_other_nuclei_extra_flags(gz, tmp_path):
    manifest = tmp_path / "m.yaml"
    manifest.write_text("authorized_by: t\ntargets:\n"
                        "  - {name: a, kind: web, url: 'https://a.invalid/', "
                        "options: {extra: '-tags cve -timeout 5', nuclei_rate_limit: 5}}\n",
                        encoding="utf-8")
    rc = gz.cmd_routine(str(manifest), str(tmp_path / "out"), registry=_nuclei_registry(),
                        date=_DATE)
    assert rc == 0


def test_routine_records_nuclei_mode(gz, fixture, tmp_path):
    reg = _nuclei_registry()
    rc = gz.cmd_routine(str(fixture("manifest-nuclei-options.yaml")), str(tmp_path / "out"),
                        registry=reg, date=_DATE)

    assert rc == 0
    cells = _cells(tmp_path / "out")
    assert cells[("site-safe", "nuclei")]["status"] == "ran(safe)"
    assert cells[("site-intrusive", "nuclei")]["status"] == "ran(safe+intrusive)"
    opts = {t: o for t, _d, o in reg.ADAPTERS["nuclei"].run_calls}
    assert opts["https://nuclei-intrusive.invalid/"]["nuclei_rate_limit"] == 10
    coverage = _meta(tmp_path / "out")["coverage"]
    assert coverage["by_status"] == {"ran": 6}
    assert coverage["complete"] is True
