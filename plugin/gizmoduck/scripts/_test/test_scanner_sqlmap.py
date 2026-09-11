import pytest

from scanners import base, sqlmap


# --- gating: the confirm token and the injection-point check --------------
#
# Cross-adapter contract: run() -> (raw_path | None, ToolResult) always, even
# on a declined gate. A decline is signalled via result.returncode is None -
# never an int - so routine.py can tell "we chose not to fire" (skipped-
# active) apart from a real failure (a real int returncode, or the -1
# sentinel base.run_tool uses for a timeout/missing binary).

def test_run_refuses_without_confirm_token(monkeypatch, fixture):
    called = []
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: called.append(1))

    raw_path, result = sqlmap.run(
        "http://example.test/page?id=1", str(fixture("sqlmap-session/confirmed")), {})

    # The refusal must happen before any subprocess is built - sqlmap sends
    # real attack traffic, so an absent token must send zero bytes, not just
    # get flagged after the fact.
    assert called == []
    assert raw_path is None
    assert result.returncode is None
    assert isinstance(result, base.ToolResult)


def test_run_refuses_falsy_confirm_token(monkeypatch, fixture):
    called = []
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: called.append(1))

    raw_path, result = sqlmap.run(
        "http://example.test/page?id=1",
        str(fixture("sqlmap-session/confirmed")), {"confirm": False})

    assert called == []
    assert raw_path is None
    assert result.returncode is None


def test_run_refuses_a_target_with_no_injection_point(monkeypatch):
    called = []
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: called.append(1))

    raw_path, result = sqlmap.run(
        "http://example.test/page", "/tmp/out", {"confirm": "APPROVED-BY-ME"})

    assert called == []
    assert raw_path is None
    assert result.returncode is None


def test_declined_result_is_distinguishable_from_a_real_error(monkeypatch):
    # A real failure (e.g. the binary missing) still gets an int returncode
    # from base.run_tool (its own -1 sentinel) - only a declined gate ever
    # produces returncode is None. The two must never be confused.
    monkeypatch.setattr(
        base, "run_tool",
        lambda *a, **k: base.ToolResult(-1, "", "sqlmap: command not found", False))

    _, declined = sqlmap.run("http://example.test/page?id=1", "/tmp/out", {})
    _, real_error = sqlmap.run(
        "http://example.test/page?id=1", "/tmp/out", {"confirm": "APPROVED-BY-ME"})

    assert declined.returncode is None
    assert real_error.returncode == -1
    assert declined.returncode is not real_error.returncode


def test_run_builds_the_expected_argv_when_confirmed(monkeypatch, tmp_path):
    captured = {}

    def fake_run_tool(argv, timeout, cwd=None):
        captured["argv"] = argv
        captured["timeout"] = timeout
        (tmp_path / "log").write_text("no injection point found\n")
        return base.ToolResult(0, "", "", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    raw_path, result = sqlmap.run("http://example.test/page?id=1", str(tmp_path),
                                  {"confirm": "APPROVED-BY-ME", "time_limit": 120})

    assert result.returncode == 0
    assert raw_path == str(tmp_path)
    argv = captured["argv"]
    assert argv[0] == "sqlmap"
    assert "-u" in argv and "http://example.test/page?id=1" in argv
    assert "--batch" in argv
    # CRITICAL (installed-toolchain defect): sqlmap's own cmdline parser
    # (lib/parse/cmdline.py) wraps argument parsing in try/except SystemExit
    # and, on Windows, prints "Press Enter to continue..." and blocks on
    # stdin unless `--non-interactive` is LITERALLY in sys.argv - this fires
    # even on `--version` and is not suppressed by `--batch`. Without this
    # flag a routine run hangs until base.run_tool's timeout eventually
    # fires, which then looks like a mysterious timeout rather than a hang.
    assert "--non-interactive" in argv
    assert "--time-limit=120" in argv
    assert "--output-dir=%s" % tmp_path in argv


def test_run_returns_none_path_when_timed_out(monkeypatch, tmp_path):
    monkeypatch.setattr(
        base, "run_tool",
        lambda *a, **k: base.ToolResult(-1, "", "", True))

    raw_path, result = sqlmap.run("http://example.test/page?id=1", str(tmp_path),
                                  {"confirm": "APPROVED-BY-ME"})

    assert raw_path is None
    assert result.timed_out is True


def test_run_returns_none_path_when_no_session_artifacts_were_written(monkeypatch, tmp_path):
    # sqlmap can exit 0 having written nothing (spec 13.9) - success is
    # decided by whether a session actually landed on disk, not the exit code.
    monkeypatch.setattr(base, "run_tool", lambda *a, **k: base.ToolResult(0, "", "", False))

    raw_path, result = sqlmap.run("http://example.test/page?id=1", str(tmp_path),
                                  {"confirm": "APPROVED-BY-ME"})

    assert raw_path is None
    assert result.returncode == 0


# --- CRITICAL defect: run() and parse() must agree on usable evidence -----
#
# run() previously accepted `log` OR `session.sqlite` as proof a session
# landed, while parse() only ever reads `log`. That let a session sqlmap
# interrupted before it wrote its log (e.g. --time-limit firing mid-request)
# come back as returncode 0, a non-null raw_path, and parse() silently
# returning [] - a scan that was cut short presented as a clean target. The
# fix must turn that combination into an error, never an empty list.

def test_run_then_parse_on_interrupted_session_is_an_error_not_a_clean_scan(
        monkeypatch, tmp_path):
    # sqlmap wrote its HashDB cache (proof it started) but was cut off
    # before persisting the human-readable `log` sqlmap.parse() reads.
    def fake_run_tool(argv, timeout, cwd=None):
        (tmp_path / "session.sqlite").write_bytes(b"fake-hashdb-zlib-pickle-blob")
        return base.ToolResult(0, "", "", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    raw_path, result = sqlmap.run("http://example.test/page?id=1", str(tmp_path),
                                  {"confirm": "APPROVED-BY-ME"})

    # run() still reports "a session happened" - that part of the contract
    # doesn't change; it's what parse() does with it that must change.
    assert raw_path is not None
    assert result.returncode == 0

    with pytest.raises(base.ParseError):
        sqlmap.parse(raw_path, "http://example.test/page?id=1")


def test_session_sqlite_without_log_is_a_parse_error(fixture):
    with pytest.raises(base.ParseError):
        sqlmap.parse(fixture("sqlmap-session/interrupted"),
                     "http://example.test/page?id=1")


# --- HIGH defect: the session directory must match the requested host -----
#
# _find_session_dir() previously returned the first alphabetical child under
# an --output-dir root that merely *contained* artifacts, with no check that
# it belonged to the target being parsed. That misattributes findings to a
# host that was never tested, and lets an alphabetically-earlier empty
# session hide a later vulnerable one.

def test_parse_does_not_misattribute_an_unrelated_hosts_session(fixture):
    # sqlmap-session/ holds "confirmed" and "empty" children from other
    # tests - neither is named after this host, so nothing here belongs to
    # it. Picking either one (as the old alphabetical-first logic did) would
    # attribute injection findings to a host that was never scanned.
    findings = sqlmap.parse(fixture("sqlmap-session"), "http://unrelated.example/?id=1")
    assert findings == []


def test_parse_picks_the_matching_host_not_the_alphabetically_first_one(fixture):
    # alpha.example sorts before victim.example and has its own confirmed
    # injection (on a *different* parameter) - if the session directory
    # were still picked alphabetically, we'd get alpha's "user" finding
    # instead of victim's "id" finding, or victim's real vulnerability would
    # never surface at all. victim.example carries the sidecar run() writes
    # (_write_target_sidecar); alpha.example does not, standing in for a
    # stale/unrelated leftover directory that must never be picked.
    findings = sqlmap.parse(fixture("sqlmap-session/multi-host"),
                            "http://victim.example/page?id=1")

    assert len(findings) == 1
    assert findings[0]["host"] == "victim.example"
    assert findings[0]["template_id"].startswith("sqlmap:id-get-")


# --- third defect: parse()'s `target` is the manifest NAME, not a URL ------
#
# Per the cross-adapter contract, routine.py calls run(location, ...) but
# parse(raw_path, target.name) - target.name is an operator-chosen label
# ("prod-web") with no guaranteed relationship to the scanned host. The old
# code called urlparse(target).hostname in parse() itself, which silently
# returns None for a bare name - every sqlmap finding would lose its real
# host/matched_at the moment routine.py (rather than a direct unit test) is
# the caller. host/matched_at must come from session artifacts - the sidecar
# run() writes recording the exact scanned URL, or (lacking that) the
# session directory's own name, which sqlmap itself always sets to the host.

def test_parse_populates_host_and_matched_at_from_session_data_not_target_name(fixture):
    # "prod-web" is a bare manifest name - no scheme, no hostname urlparse
    # can extract. The real URL and host must still surface, sourced from
    # the sidecar run() left in the session directory, not from this string.
    findings = sqlmap.parse(fixture("sqlmap-session/bare-name-run"), "prod-web")

    assert len(findings) == 1
    assert findings[0]["host"] == "prod-web.example.test"
    assert findings[0]["matched_at"] == "http://prod-web.example.test/checkout?sku=42"
    # The manifest name is still the finding's `target` field (spec section
    # 6) - that part of the contract is untouched by this fix.
    assert findings[0]["target"] == "prod-web"


def test_run_writes_a_target_sidecar_parse_can_later_read(monkeypatch, tmp_path):
    # End-to-end: run() is the only place that ever sees the real URL for a
    # bare-name manifest target (routine.py passes it `location`, never
    # `target.name`). It must persist that URL next to sqlmap's own
    # artifacts so a later parse(raw_path, "prod-web") call - a fresh
    # process, or just routine.py's normal flow - can still resolve the
    # real host instead of silently losing it.
    def fake_run_tool(argv, timeout, cwd=None):
        (tmp_path / "log").write_text(
            "Parameter: id (GET)\n"
            "    Type: boolean-based blind\n"
            "    Title: AND boolean-based blind - WHERE or HAVING clause\n"
            "    Payload: id=1 AND 7331=7331\n")
        return base.ToolResult(0, "", "", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    raw_path, _ = sqlmap.run("http://example.test/page?id=1", str(tmp_path),
                             {"confirm": "APPROVED-BY-ME"})

    # parse() is now called the way routine.py actually calls it: with the
    # manifest's bare name, never the URL run() used.
    findings = sqlmap.parse(raw_path, "prod-web")
    assert len(findings) == 1
    assert findings[0]["host"] == "example.test"
    assert findings[0]["matched_at"] == "http://example.test/page?id=1"


def test_parse_finds_the_session_when_manifest_name_is_not_the_hostname(fixture):
    # The realistic manifest shape: {name: prod-web, kind: web,
    # url: http://www.example.com/?id=1} - the name and the hostname are
    # ordinarily different strings. A single session directory under the
    # root is unambiguous regardless of what it's named or what `target`
    # is, so this must be found and populated purely from the log/directory
    # data - with no sidecar present at all, proving the fallback (not just
    # the sidecar path) handles a manifest name that differs from the host.
    findings = sqlmap.parse(fixture("sqlmap-session/name-differs-from-host"), "prod-web")

    assert len(findings) == 1
    assert findings[0]["host"] == "www.example.com"
    assert findings[0]["matched_at"] == "www.example.com"
    assert findings[0]["target"] == "prod-web"


def test_parse_raises_rather_than_silently_dropping_an_unresolvable_bare_name(fixture):
    # Two candidate session directories, a bare manifest name, and no
    # sidecar in either one to say which (if either) belongs to this
    # manifest entry: genuine, unresolvable ambiguity. Silently returning []
    # here would be indistinguishable from "this target has no injection" -
    # exactly the false-clean outcome the CRITICAL defect above exists to
    # prevent. This must raise, not disappear.
    with pytest.raises(base.ParseError):
        sqlmap.parse(fixture("sqlmap-session/ambiguous-bare-name"), "prod-web")


# --- parsing: confirmed session yields findings, empty session yields none -

def test_confirmed_session_yields_findings_for_every_captured_technique(fixture):
    # Fixture replaced with a REAL sqlmap capture (1.10.9.8#dev) against the
    # labtarget fixture app's /item?id= endpoint, run with the exact argv
    # shape sqlmap.run() itself builds (no --technique/-p/--dump narrowing).
    # A real confirmed injection on this target reports 4 techniques for the
    # one parameter, not the 2 a hand-built fixture once guessed: boolean-
    # based blind, error-based, and time-based blind (all "high" - none is a
    # _CRITICAL_MARKERS match) plus a UNION query (critical).
    findings = sqlmap.parse(fixture("sqlmap-session/confirmed"),
                            "http://example.test/page?id=1")

    assert len(findings) == 4
    severities = sorted(f["severity"] for f in findings)
    assert severities == [3, 3, 3, 4]

    for f in findings:
        assert f["template_id"].startswith("sqlmap:id-get-")
        assert f["target"] == "http://example.test/page?id=1"
        assert f["tool"] == "sqlmap"
        assert f["host"] == "example.test"

    union_finding = next(f for f in findings if f["severity"] == 4)
    assert "union" in union_finding["template_id"]
    assert union_finding["severity_name"] == "critical"

    high_findings = [f for f in findings if f["severity"] == 3]
    assert len(high_findings) == 3
    assert all(f["severity_name"] == "high" for f in high_findings)
    assert {f["template_id"] for f in high_findings} == {
        "sqlmap:id-get-boolean-based-blind",
        "sqlmap:id-get-error-based",
        "sqlmap:id-get-time-based-blind",
    }


def test_empty_session_yields_zero_findings_not_a_low_severity_entry(fixture):
    # Probed-and-negative parameters are never persisted - a clean run must
    # come back as an empty list, never a synthetic "info: nothing found".
    # Fixture replaced with a REAL capture: sqlmap 1.10.9.8#dev run to
    # completion (--technique=B) against a decoy, non-injectable parameter
    # on the labtarget fixture app - `log` is a genuine 0-byte file next to
    # a real session.sqlite, not a hand-built guess.
    findings = sqlmap.parse(fixture("sqlmap-session/empty"),
                            "http://example.test/page?id=1")
    assert findings == []


def test_parse_accepts_an_output_dir_root_and_finds_the_host_subfolder(fixture, tmp_path):
    # run() is given the --output-dir root; sqlmap creates the per-host
    # folder underneath it. parse() must be able to take that same root.
    root = tmp_path / "output"
    hostdir = root / "example.test"
    hostdir.mkdir(parents=True)
    (hostdir / "log").write_text((fixture("sqlmap-session/confirmed") / "log").read_text())

    findings = sqlmap.parse(root, "http://example.test/page?id=1")
    # The real captured `confirmed` log records four techniques on the one
    # injectable parameter (boolean-based blind, error-based, time-based
    # blind, UNION query) - one finding each. This matches the count the
    # same fixture asserts through the direct-session-dir path above.
    assert len(findings) == 4


def test_missing_log_yields_zero_findings(tmp_path):
    # No log at all (session never ran, or nothing survived) is still zero
    # findings, not an error and not a placeholder finding.
    empty_dir = tmp_path / "nothing-here"
    empty_dir.mkdir()
    assert sqlmap.parse(empty_dir, "http://example.test/page?id=1") == []


def test_exit_code_is_not_a_parameter_parse_can_even_consult():
    # parse()'s signature has no returncode slot - the exit-code trap the
    # plan warns about (sqlmap exits 0 whether or not anything was found)
    # cannot leak into the finding count even by accident.
    import inspect
    params = inspect.signature(sqlmap.parse).parameters
    assert "returncode" not in params and "exit_code" not in params


# --- round 2 CRITICAL defect: run() returns the exact session directory ---
#
# run() used to hand back the bare --output-dir root, forcing parse() to
# re-derive which child folder belonged to this target from a manifest name
# that may not even be a URL. run() is the only place that ever holds the
# real URL, so it should return the exact session directory it resolved
# instead - collapsing the whole ambiguity for the ordinary run()-then-
# parse() cycle.

def test_run_returns_the_resolved_session_dir_not_the_output_root(monkeypatch, tmp_path):
    def fake_run_tool(argv, timeout, cwd=None):
        hostdir = tmp_path / "b.example"
        hostdir.mkdir()
        (hostdir / "log").write_text(
            "Parameter: id (GET)\n"
            "    Type: boolean-based blind\n"
            "    Title: AND boolean-based blind - WHERE or HAVING clause\n"
            "    Payload: id=1 AND 7331=7331\n")
        # A stale, unrelated sibling session must never be picked instead.
        other = tmp_path / "a.example"
        other.mkdir()
        (other / "log").write_text(
            "[10:00:01] [INFO] testing connection to the target URL\n"
            "[10:00:06] [CRITICAL] all tested parameters do not appear to "
            "be injectable.\n")
        return base.ToolResult(0, "", "", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    raw_path, result = sqlmap.run("https://b.example/?id=1", str(tmp_path),
                                  {"confirm": "APPROVED-BY-ME"})

    assert raw_path == str(tmp_path / "b.example")
    findings = sqlmap.parse(raw_path, "b-web")  # opaque manifest name
    assert len(findings) == 1
    assert findings[0]["host"] == "b.example"


# --- round 2 reproductions: parse() called directly on a pre-existing ------
# artifact root, with no run() in this process to have already resolved the
# session directory. An output root holds a.example/log (empty, no
# injection) and b.example/log (a confirmed injection).

def test_repro1_no_sidecars_finds_the_correctly_named_folder(fixture):
    # No sidecars anywhere, target is a real URL for b.example: the
    # correctly-named vulnerable folder must still be found via its own
    # name (sqlmap always names a session folder after the host it
    # scanned), even with no sidecar to corroborate it.
    findings = sqlmap.parse(fixture("sqlmap-session/round2-no-sidecars"),
                            "https://b.example/?id=1")
    assert len(findings) == 1
    assert findings[0]["host"] == "b.example"


def test_repro2_opaque_target_with_multiple_candidates_refuses(fixture):
    # Only a.example (the empty session) has an internally-consistent
    # sidecar; target is an opaque manifest name. The old "trust a sidecar
    # that merely agrees with its own folder name" fallback silently picked
    # the stale, empty a.example session here and returned [] - a false-
    # clean result. That heuristic correlates with nothing about the real
    # target, so this must now refuse rather than guess.
    with pytest.raises(base.ParseError):
        sqlmap.parse(fixture("sqlmap-session/round2-opaque-one-consistent"),
                     "prod")


def test_repro3_single_candidate_with_conflicting_sidecar_is_not_reported(fixture):
    # The lone candidate is named b.example (sqlmap's own naming), but its
    # sidecar declares a.example - a corrupted/reused directory. Blindly
    # trusting "only one candidate, nothing to disambiguate" used to report
    # the injection under the sidecar's a.example, i.e. against a host that
    # was never actually asked about. Since we know we're asking about
    # b.example and this candidate's own sidecar denies it, that is a
    # confident negative, not a report at the wrong host.
    findings = sqlmap.parse(
        fixture("sqlmap-session/round2-single-conflicting-sidecar"),
        "https://b.example/?id=1")
    assert findings == []


def test_repro4_run_then_parse_with_resolved_session_dir_needs_no_matching(
        monkeypatch, tmp_path):
    # The remaining pre-existing-artifact ambiguity (opaque target, 2+
    # candidates) is unresolvable and correctly raises ParseError when
    # parse() is called on a root with no run() in this process (see
    # test_repro2 above) - refusing to guess is the intended, deliberate
    # behaviour there, not a bug. What must NOT happen is a *successful*
    # run() ever hitting that ambiguity: run() returning the exact session
    # directory it resolved means the ordinary run()-then-parse() cycle
    # never needs to guess at all, even with an opaque manifest name and
    # other stale sessions sitting in the same output root.
    def fake_run_tool(argv, timeout, cwd=None):
        hostdir = tmp_path / "b.example"
        hostdir.mkdir()
        (hostdir / "log").write_text(
            "Parameter: id (GET)\n"
            "    Type: boolean-based blind\n"
            "    Title: AND boolean-based blind - WHERE or HAVING clause\n"
            "    Payload: id=1 AND 7331=7331\n")
        stale = tmp_path / "a.example"
        stale.mkdir()
        (stale / "log").write_text(
            "[10:00:01] [INFO] testing connection to the target URL\n"
            "[10:00:06] [CRITICAL] all tested parameters do not appear to "
            "be injectable.\n")
        return base.ToolResult(0, "", "", False)

    monkeypatch.setattr(base, "run_tool", fake_run_tool)

    raw_path, _ = sqlmap.run("https://b.example/?id=1", str(tmp_path),
                             {"confirm": "APPROVED-BY-ME"})

    # routine.py calls parse() with target.name (opaque), never the URL -
    # this must not raise, because raw_path is already the resolved session
    # directory, not the ambiguous root.
    findings = sqlmap.parse(raw_path, "prod")
    assert len(findings) == 1


# --- round 2 HIGH defect: a corrupt or truncated log must not mean clean ---

def test_truncated_record_is_a_parse_error_not_a_clean_scan(fixture):
    # Parameter: id (GET) / Type: ... / Title: ... with NO Payload: line -
    # a record cut off mid-write. Must not silently read as "no injection".
    with pytest.raises(base.ParseError):
        sqlmap.parse(fixture("sqlmap-session/round2-truncated-log"),
                     "https://example.test/?id=1")


def test_garbage_log_is_a_parse_error_not_a_clean_scan(fixture):
    # Not sqlmap output at all - no timestamped log lines, no Parameter:
    # header, nothing recognizable.
    with pytest.raises(base.ParseError):
        sqlmap.parse(fixture("sqlmap-session/round2-garbage-log"),
                     "https://example.test/?id=1")


def test_nonexistent_session_still_yields_zero_findings(tmp_path):
    # A missing session must stay indistinguishable from "never ran" -
    # zero findings, not an error - unlike a log that exists but is
    # unreadable as sqlmap output.
    empty_dir = tmp_path / "never-ran"
    empty_dir.mkdir()
    assert sqlmap.parse(empty_dir, "https://example.test/?id=1") == []


def test_a_genuinely_clean_log_still_yields_zero_findings(fixture):
    # Regression guard: the `empty` fixture is a real, fully-completed clean
    # run - a genuine 0-byte `log` file next to a real session.sqlite - not
    # the "timestamped INFO/WARNING/CRITICAL lines with no Parameter: block"
    # shape originally guessed here (real sqlmap never puts those lines in
    # `log` at all - see the module docstring correction). The defect-4 fix
    # must not turn this into a false error.
    findings = sqlmap.parse(fixture("sqlmap-session/empty"),
                            "https://example.test/page?id=1")
    assert findings == []


def test_empty_log_without_session_sqlite_is_a_parse_error_not_a_clean_scan(fixture):
    # REAL capture: sqlmap cut off by --time-limit before it finished
    # testing even one parameter leaves an empty `log` behind with NO
    # session.sqlite next to it - the mirror image of the
    # session-sqlite-without-log "interrupted" case above, and the one that
    # actually occurs in practice (verified against real sqlmap 1.10.9.8#dev:
    # `log` is created immediately: session.sqlite, sqlmap's HashDB cache, is
    # only ever written once a run completes). An empty `log` alone is not
    # enough to call a scan clean; session.sqlite's presence is what
    # actually distinguishes "clean" from "cut short".
    with pytest.raises(base.ParseError):
        sqlmap.parse(fixture("sqlmap-session/time-limit-cutoff"),
                     "http://example.test/page?id=1")


def test_sidecar_with_unparseable_url_is_a_parse_error_not_a_crash(tmp_path):
    # A sidecar containing `http://[` makes urlparse() raise ValueError
    # (an unterminated IPv6 bracket) - that must never escape as a raw
    # ValueError; it must surface as base.ParseError like any other
    # unreadable/unusable session evidence.
    session_dir = tmp_path / "broken.example"
    session_dir.mkdir()
    (session_dir / "log").write_text(
        "Parameter: id (GET)\n"
        "    Type: boolean-based blind\n"
        "    Title: AND boolean-based blind - WHERE or HAVING clause\n"
        "    Payload: id=1 AND 7331=7331\n")
    (session_dir / sqlmap._TARGET_SIDECAR).write_text("http://[")

    # Single, unambiguous session directory - _session_location is where
    # the sidecar is actually read for host/matched_at, and must not raise
    # a bare ValueError out of parse().
    findings = sqlmap.parse(session_dir, "broken-web")
    assert len(findings) == 1
    # The unparseable sidecar is treated as unusable, falling back to the
    # session directory's own name (sqlmap's own naming) for host/matched_at.
    assert findings[0]["host"] == "broken.example"


# --- registry protocol conformance -----------------------------------------

def test_module_constants():
    assert sqlmap.NAME == "sqlmap"
    assert sqlmap.KINDS == ["web"]
    assert sqlmap.ACTIVE is True
    assert sqlmap.ACTIVE_OPTS == []
    assert sqlmap.DEFAULT_ENABLED is False
