"""Safe Nuclei defaults (T-0108): one argv builder for `scan` and the routine.

A Nuclei scan started through gizmoduck excludes templates tagged
`dos,intrusive,fuzz` and sends at most 50 requests per second, unless the
caller opts out by name (`scan --intrusive`, `scan --rate-limit N`). Both
`cmd_scan` and the routine's Nuclei adapter build their command line through
`gizmoduck.nuclei_argv`, so this suite pins the builder itself and then
proves both callers produce the same argv from the same inputs.

No scanner runs here: `subprocess.run` (cmd_scan) and `base.run_tool` (the
adapter) are replaced, and `find_nuclei` answers a fixed name.

Sabotage (each run by hand; the named test must go red):
  (a) the `-etags` line deleted from nuclei_argv
      -> test_nuclei_argv_excludes_dos_intrusive_fuzz_by_default
  (b) the strict refusal removed from nuclei_argv
      -> test_nuclei_argv_strict_refuses_tag_and_rate_flags_in_extra
"""
import sys

import pytest

from scanners import nuclei

TARGET = "https://defaults.invalid/"

_RATE_FLAGS = ("rl", "rate-limit", "rlm", "rate-limit-minute")
_TAG_FLAGS = ("etags", "exclude-tags", "itags", "include-tags")
# From `nuclei -h` on v3.11.1: re-include excluded templates, fuzz, or loosen
# the rate cap. The spec's eight names grew by these nine.
_ATTACK_FLAGS = ("it", "include-templates", "dast", "fuzz", "dts", "dast-server",
                 "per-host-rate-limit", "rld", "rate-limit-duration")
# A config or template-profile file can set any of the above unseen.
_CONFIG_FLAGS = ("config", "tp", "profile")


@pytest.fixture(autouse=True)
def _scratch_home(scratch_nuclei_home):
    return scratch_nuclei_home


@pytest.fixture
def gz(monkeypatch):
    """The gizmoduck module the adapter itself imports, so cmd_scan and the
    adapter are compared on one copy of the builder."""
    mod = nuclei._gizmoduck()
    monkeypatch.setattr(mod, "find_nuclei", lambda: "nuclei")
    return mod


def _value_after(argv, flag):
    assert flag in argv, f"{flag} missing from {argv}"
    return argv[argv.index(flag) + 1]


def _rate_flags_in(argv):
    return [t for t in argv
            if t.startswith("-") and t.lstrip("-").split("=", 1)[0] in _RATE_FLAGS]


def test_nuclei_argv_excludes_dos_intrusive_fuzz_by_default(gz):
    argv = gz.nuclei_argv("nuclei", TARGET, "", "")
    assert _value_after(argv, "-etags") == "dos,intrusive,fuzz"
    assert argv.count("-etags") == 1


def test_nuclei_argv_default_rate_limit_is_50(gz):
    argv = gz.nuclei_argv("nuclei", TARGET, "", "")
    assert _value_after(argv, "-rl") == "50"
    assert _rate_flags_in(argv) == ["-rl"]


def test_nuclei_argv_order_is_core_target_severity_etags_rate_extra(gz):
    argv = gz.nuclei_argv("nuclei", TARGET, "high", "-timeout 5")
    assert argv == ["nuclei", "-jsonl", "-silent", "-nc", "-u", TARGET,
                    "-severity", "high", "-etags", "dos,intrusive,fuzz",
                    "-rl", "50", "-rld", "1s", "-timeout", "5"]


def test_nuclei_argv_intrusive_drops_the_tag_exclusion_and_keeps_the_rate_limit(gz):
    argv = gz.nuclei_argv("nuclei", TARGET, "", "", intrusive=True)
    assert "-etags" not in argv
    assert _value_after(argv, "-rl") == "50"


def test_nuclei_argv_explicit_rate_limit_replaces_the_default(gz):
    argv = gz.nuclei_argv("nuclei", TARGET, "", "", rate_limit=7)
    assert _value_after(argv, "-rl") == "7"
    assert _rate_flags_in(argv) == ["-rl"]


@pytest.mark.parametrize("extra", ["-rl 10", "--rl 10", "-rl=10", "-rate-limit 10",
                                   "-rlm 600", "-rate-limit-minute=600"])
def test_nuclei_argv_rate_flag_in_extra_suppresses_the_default(gz, extra):
    argv = gz.nuclei_argv("nuclei", TARGET, "", extra)
    assert len(_rate_flags_in(argv)) == 1
    assert argv[-len(extra.split()):] == extra.split()


@pytest.mark.parametrize("extra", ["-rl 10", "--rate-limit-minute=600"])
def test_nuclei_argv_explicit_rate_limit_with_rate_flag_in_extra_is_refused(
        gz, monkeypatch, capsys, tmp_path, extra):
    with pytest.raises(ValueError, match="rate"):
        gz.nuclei_argv("nuclei", TARGET, "", extra, rate_limit=5)

    out = tmp_path / "f.jsonl"
    monkeypatch.setattr(gz.subprocess, "run", _must_not_run)
    monkeypatch.setattr(sys, "argv", ["gizmoduck.py", "scan", TARGET, "--out", str(out),
                                      "--rate-limit", "5", "--extra", extra])
    with pytest.raises(SystemExit) as exc:
        gz.main()
    assert exc.value.code == 2
    assert "rate" in capsys.readouterr().err
    assert not out.exists()


def test_nuclei_argv_extra_is_appended_last_and_unchanged(gz):
    extra = "-tags cve -timeout 5 -H X-Test:1"
    argv = gz.nuclei_argv("nuclei", TARGET, "", extra)
    assert argv[-len(extra.split()):] == extra.split()
    # The defaults stand: -tags is not a tag-exclusion flag.
    assert _value_after(argv, "-etags") == "dos,intrusive,fuzz"


def test_nuclei_argv_tag_flags_in_extra_pass_through_when_not_strict(gz):
    argv = gz.nuclei_argv("nuclei", TARGET, "", "-itags dos")
    assert argv[-2:] == ["-itags", "dos"]


_STRICT_CASES = [f"{dash}{name}{sep}x"
                 for name in _RATE_FLAGS + _TAG_FLAGS + _ATTACK_FLAGS + _CONFIG_FLAGS
                 for dash, sep in (("-", " "), ("--", "="))]


@pytest.mark.parametrize("extra", _STRICT_CASES)
def test_nuclei_argv_strict_refuses_tag_and_rate_flags_in_extra(gz, extra):
    with pytest.raises(ValueError) as exc:
        gz.nuclei_argv("nuclei", TARGET, "", extra, strict=True)
    assert "nuclei_intrusive" in str(exc.value)
    assert "nuclei_rate_limit" in str(exc.value)


def test_strict_list_matches_the_module_constants(gz):
    assert set(_RATE_FLAGS) == gz.NUCLEI_RATE_FLAGS
    assert set(_TAG_FLAGS) == gz.NUCLEI_TAG_FLAGS
    assert set(_ATTACK_FLAGS) == gz.NUCLEI_ATTACK_FLAGS
    assert set(_CONFIG_FLAGS) == gz.NUCLEI_CONFIG_FLAGS
    assert gz.NUCLEI_STRICT_FLAGS == set(_RATE_FLAGS + _TAG_FLAGS + _ATTACK_FLAGS
                                         + _CONFIG_FLAGS)


@pytest.mark.parametrize("extra", ["-config x.yaml", "--config=x.yaml", "-tp p.yaml",
                                   "--tp=p.yaml", "-profile p", "--profile=p"])
def test_scan_extra_config_flags_stay_raw_passthrough(gz, extra):
    """Owner, 2026-10-05: scan --extra is the user's own; only the routine refuses."""
    argv = gz.nuclei_argv("nuclei", TARGET, "", extra)
    assert argv[-len(extra.split()):] == extra.split()


@pytest.mark.parametrize("kwargs", [{}, {"rate_limit": 7}, {"intrusive": True}])
def test_every_emitted_rate_limit_carries_rld_1s(gz, kwargs):
    argv = gz.nuclei_argv("nuclei", TARGET, "", "", **kwargs)
    i = argv.index("-rl")
    assert argv[i + 2:i + 4] == ["-rld", "1s"]
    assert argv.count("-rld") == 1


@pytest.mark.parametrize("extra", ["-rl 10", "-rlm 600", "-rld 2s", "--rate-limit-duration=2s"])
def test_no_second_rld_when_scan_extra_owns_the_rate(gz, extra):
    argv = gz.nuclei_argv("nuclei", TARGET, "", extra)
    assert argv.count("-rld") + argv.count("--rate-limit-duration=2s") <= 1
    assert "1s" not in argv


@pytest.mark.parametrize("rate", [0, -1, True, False, "50", 1.5])
def test_nuclei_argv_refuses_a_rate_limit_that_is_not_a_positive_int(gz, rate):
    with pytest.raises(ValueError, match="nuclei_rate_limit"):
        gz.nuclei_argv("nuclei", TARGET, "", "", rate_limit=rate)


@pytest.mark.parametrize("intrusive", ["false", "true", 1, 0, None])
def test_nuclei_argv_refuses_an_intrusive_that_is_not_a_bool(gz, intrusive):
    with pytest.raises(ValueError, match="nuclei_intrusive"):
        gz.nuclei_argv("nuclei", TARGET, "", "", intrusive=intrusive)


@pytest.mark.parametrize("extra", [["-rl", "5"], 5, {"rl": 5}])
def test_nuclei_argv_refuses_an_extra_that_is_not_a_string(gz, extra):
    with pytest.raises(ValueError, match="must be a string"):
        gz.nuclei_argv("nuclei", TARGET, "", extra, strict=True)


@pytest.mark.parametrize("rate,intrusive", [(1, False), (1, True), (None, False), (500, True)])
def test_nuclei_argv_accepts_valid_rate_and_intrusive(gz, rate, intrusive):
    argv = gz.nuclei_argv("nuclei", TARGET, "", "", rate_limit=rate, intrusive=intrusive)
    assert argv[argv.index("-rl") + 1] == str(rate or 50)


def test_nuclei_argv_strict_allows_other_extra_flags(gz):
    argv = gz.nuclei_argv("nuclei", TARGET, "", "-tags cve -timeout 5", strict=True)
    assert argv[-4:] == ["-tags", "cve", "-timeout", "5"]


def _must_not_run(*_a, **_kw):
    raise AssertionError("nuclei must not be started")


class _Proc:
    returncode = 0
    stdout = '{"template-id":"x"}\n'
    stderr = ""


@pytest.mark.parametrize("severity,extra,intrusive,rate", [
    ("", "", False, None),
    ("critical,high", "-timeout 5", False, None),
    ("", "-tags cve", True, None),
    ("medium", "", True, 20),
])
def test_cmd_scan_and_adapter_build_the_same_argv(gz, monkeypatch, tmp_path,
                                                  severity, extra, intrusive, rate):
    seen = {}

    def fake_subprocess_run(argv, **_kw):
        seen["scan"] = list(argv)
        return _Proc()

    def fake_run_tool(argv, timeout, cwd=None):
        seen["adapter"] = list(argv)
        return nuclei.base.ToolResult(0, '{"template-id":"x"}\n', "", False)

    monkeypatch.setattr(gz.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(nuclei.base, "run_tool", fake_run_tool)

    gz.cmd_scan(TARGET, str(tmp_path / "scan.jsonl"), severity, extra,
                intrusive=intrusive, rate_limit=rate)
    opts = {"severity": severity, "extra": extra, "nuclei_intrusive": intrusive}
    if rate is not None:
        opts["nuclei_rate_limit"] = rate
    nuclei.run(TARGET, str(tmp_path / "adapter"), opts)

    assert seen["scan"] == seen["adapter"]


@pytest.mark.parametrize("value", ["0", "-5", "abc", "1.5"])
def test_scan_rate_limit_rejects_zero_negative_and_non_integer(gz, monkeypatch, tmp_path,
                                                                value):
    out = tmp_path / "f.jsonl"
    monkeypatch.setattr(gz.subprocess, "run", _must_not_run)
    monkeypatch.setattr(sys, "argv", ["gizmoduck.py", "scan", TARGET, "--out", str(out),
                                      f"--rate-limit={value}"])
    with pytest.raises(SystemExit) as exc:
        gz.main()
    assert exc.value.code == 2
    assert not out.exists()


def test_scan_intrusive_flag_reaches_the_argv(gz, monkeypatch, tmp_path):
    seen = []

    def fake_subprocess_run(argv, **_kw):
        seen.append(list(argv))
        return _Proc()

    monkeypatch.setattr(gz.subprocess, "run", fake_subprocess_run)
    for flags in ([], ["--intrusive"], ["--rate-limit", "12"]):
        monkeypatch.setattr(sys, "argv", ["gizmoduck.py", "scan", TARGET,
                                          "--out", str(tmp_path / "f.jsonl"), *flags])
        gz.main()

    assert len(seen) == 3
    default, intrusive, rated = seen[0], seen[1], seen[2]
    assert _value_after(default, "-etags") == "dos,intrusive,fuzz"
    assert "-etags" not in intrusive
    assert _value_after(intrusive, "-rl") == "50"
    assert _value_after(rated, "-rl") == "12"


@pytest.mark.parametrize("flags", [["--intrusive"], ["--rate-limit", "5"]],
                         ids=["--intrusive", "--rate-limit"])
def test_scan_only_flags_are_refused_elsewhere(gz, monkeypatch, capsys, tmp_path, flags):
    monkeypatch.setattr(sys, "argv", ["gizmoduck.py", "summary", str(tmp_path / "x.jsonl"),
                                      *flags])
    with pytest.raises(SystemExit) as exc:
        gz.main()
    assert exc.value.code == 2
    assert "only applies to the 'scan' command" in capsys.readouterr().err
