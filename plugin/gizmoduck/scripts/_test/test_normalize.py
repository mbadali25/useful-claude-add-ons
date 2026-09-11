import pytest
import normalize as n


@pytest.mark.parametrize("text,expected", [
    ("CRITICAL", 4), ("critical", 4),
    ("HIGH", 3), ("High", 3), ("IMPORTANT", 3),
    ("MEDIUM", 2), ("MODERATE", 2),
    ("LOW", 1), ("INFO", 0), ("INFORMATIONAL", 0),
])
def test_known_text_levels(text, expected):
    sev, known = n.sev_from_text(text)
    assert (sev, known) == (expected, True)


@pytest.mark.parametrize("text", [None, "", "UNKNOWN", "banana", "OK"])
def test_unknown_text_falls_back_and_flags(text):
    sev, known = n.sev_from_text(text)
    assert sev == 0 and known is False


def test_unknown_respects_explicit_default():
    # Checkov's null severity must land on medium, not info (spec 13.5).
    sev, known = n.sev_from_text(None, default="medium")
    assert sev == 2 and known is False


@pytest.mark.parametrize("score,expected", [
    (10.0, 4), (9.0, 4), (8.9, 3), (7.0, 3), (6.9, 2),
    (4.0, 2), (3.9, 1), (0.1, 1), (0.0, 0),
])
def test_cvss_bands_including_boundaries(score, expected):
    # A valid score is a real assessment: known must be True.
    assert n.sev_from_cvss(score) == (expected, True)


@pytest.mark.parametrize("score", [
    None, "", "NaN", float("nan"), "Infinity", float("inf"), float("-inf"),
    -1, -0.1, 11, 10.1, "banana",
])
def test_cvss_rejects_missing_non_finite_and_out_of_range(score):
    # Not a valid CVSS score - must not be presented as a real assessment.
    # The int half is not asserted: only `known` is part of the contract
    # for an invalid score, per the docstring.
    sev, known = n.sev_from_cvss(score)
    assert known is False


def test_cvss_falls_through_from_invalid_v2_to_valid_v3():
    # The real Dependency-Check case the review found: a garbage cvssv2
    # score must not shadow a good cvssv3 score. This is the adapter's
    # responsibility (depcheck.py), but the contract it relies on - that
    # an invalid score comes back with known=False - is asserted here.
    bad_sev, bad_known = n.sev_from_cvss(-1)
    good_sev, good_known = n.sev_from_cvss(9.8)
    assert bad_known is False
    assert (good_sev, good_known) == (4, True)


@pytest.mark.parametrize("code,expected,known", [
    (3, 3, True), (2, 2, True), (1, 1, True), (0, 0, True),
    ("3", 3, True), (9, 0, False), (None, 0, False),
])
def test_riskcode_map_and_unexpected(code, expected, known):
    assert n.sev_from_riskcode(code) == (expected, known)


@pytest.mark.parametrize("code", [0.9, 3.9, 1.5, "2.5", float("nan"), float("inf")])
def test_riskcode_rejects_non_integral_values(code):
    # int(0.9) truncates to a "recognized" 0 - a non-integral riskcode is
    # not riskcode 0, it is not a riskcode at all.
    assert n.sev_from_riskcode(code) == (0, False)


def test_synthetic_id_namespaces_by_tool():
    assert n.synthetic_id("zap", "10038") == "zap:10038"


def test_make_finding_has_every_required_key():
    f = n.make_finding(tool="trivy", target="repo", rule_id="CVE-1", name="x", severity=3)
    for key in ("template_id", "name", "severity", "severity_name", "type",
                "timestamp", "host", "matched_at", "cve", "cvss", "description",
                "remediation", "reference", "tags", "tool", "target"):
        assert key in f, key
    assert f["template_id"] == "trivy:CVE-1"
    assert f["severity_name"] == "high"


def test_severity_ints_match_gizmoduck(scripts_dir):
    import importlib.util
    spec = importlib.util.spec_from_file_location("gz", scripts_dir / "gizmoduck.py")
    gz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gz)
    # Strict equality on SEV_NUM: this is the band-consistency check the risk
    # note is about - a drift here silently reshuffles which int a severity
    # word maps to. gizmoduck.py:38 also carries an "unknown": 0 entry (a
    # vestige of its own dict.get() default) that normalize.py mirrors for
    # this reason alone; sev_from_text() explicitly refuses to treat the text
    # "unknown" as a recognized level regardless.
    assert gz.SEV_NUM == n.SEV_NUM
    # SEV_NAME is compared case-insensitively, not with ==: gizmoduck.py's
    # copy is Title-case for display ("Critical"), while normalize.make_finding
    # deliberately emits a lowercase severity_name (asserted above in
    # test_make_finding_has_every_required_key) - a machine-readable field is
    # a different contract than a display string, and the two were never
    # meant to be the same object. Only the severity *band* has to agree.
    assert {k: v.lower() for k, v in gz.SEV_NAME.items()} == n.SEV_NAME
