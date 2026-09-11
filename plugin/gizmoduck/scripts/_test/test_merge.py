"""Tests for normalize.merge_category - the cross-tool merge for the `deps`
and `iac` categories (spec sec 7, plan Task 18).

Findings here are built with normalize.make_finding for a realistic base
shape, then given the extra fields the merge key reads (`package`/`version`
for deps, `host`/`matched_at` for iac's resource/path/line) by direct dict
assignment - merge_category operates on plain finding dicts and does not
require those extra fields to come through make_finding's own kwargs.
"""
import normalize as n


def _finding(tool, rule_id, name, severity, cve=None, **extra):
    f = n.make_finding(tool=tool, target="repo-a", rule_id=rule_id,
                        name=name, severity=severity, cve=cve)
    f.update(extra)
    return f


def test_deps_findings_sharing_cve_package_version_merge_with_highest_severity():
    depcheck_finding = _finding(
        "depcheck", "CVE-2023-9999",
        "jackson-databind vulnerable to deserialization attack", 2,
        cve=["CVE-2023-9999"], package="jackson-databind", version="2.9.8",
    )
    trivy_finding = _finding(
        "trivy", "CVE-2023-9999",
        "jackson-databind deserialization vulnerability found", 3,
        cve=["CVE-2023-9999"], package="jackson-databind", version="2.9.8",
    )

    merged, near_misses = n.merge_category([depcheck_finding, trivy_finding], "deps")

    assert near_misses == []
    assert len(merged) == 1
    m = merged[0]
    assert m["tools"] == ["depcheck", "trivy"]
    assert m["severity"] == 3
    assert m["severity_name"] == "high"
    assert {c["tool"]: c["rule_id"] for c in m["merged_from"]} == {
        "depcheck": "CVE-2023-9999",
        "trivy": "CVE-2023-9999",
    }


def test_iac_findings_sharing_path_line_resource_merge_despite_different_check_ids():
    checkov_finding = _finding(
        "checkov", "CKV_AWS_18",
        "S3 bucket should have access logging enabled", 1,
        host="aws_s3_bucket.data", matched_at="main.tf:12",
    )
    trivy_finding = _finding(
        "trivy", "AVD-AWS-0089",
        "S3 bucket access logging is not enabled", 2,
        host="aws_s3_bucket.data", matched_at="main.tf:12",
    )

    merged, near_misses = n.merge_category([checkov_finding, trivy_finding], "iac")

    assert near_misses == []
    assert len(merged) == 1
    m = merged[0]
    assert m["tools"] == ["checkov", "trivy"]
    assert m["severity"] == 2
    assert {c["tool"]: c["rule_id"] for c in m["merged_from"]} == {
        "checkov": "CKV_AWS_18",
        "trivy": "AVD-AWS-0089",
    }


def test_finding_with_no_cve_never_merges():
    depcheck_finding = _finding(
        "depcheck", "jackson-databind-vuln", "jackson-databind vulnerable", 2,
        package="jackson-databind", version="2.9.8",
    )
    trivy_finding = _finding(
        "trivy", "jackson-databind-vuln", "jackson-databind vulnerable", 2,
        package="jackson-databind", version="2.9.8",
    )

    merged, near_misses = n.merge_category([depcheck_finding, trivy_finding], "deps")

    # Same package/version and identical title, but neither carries a CVE id
    # - the merge key requires one, so both render on their own (spec sec 7).
    assert len(merged) == 2
    assert near_misses == []


def test_titles_sharing_no_token_stay_separate_and_record_a_near_miss():
    depcheck_finding = _finding(
        "depcheck", "CVE-2024-1111",
        "Remote code execution via deserialization", 3,
        cve=["CVE-2024-1111"], package="libfoo", version="1.0.0",
    )
    trivy_finding = _finding(
        "trivy", "CVE-2024-1111",
        "SQL injection through crafted header", 2,
        cve=["CVE-2024-1111"], package="libfoo", version="1.0.0",
    )

    merged, near_misses = n.merge_category([depcheck_finding, trivy_finding], "deps")

    # Same (cve, package, version) key, but the titles share no token - the
    # guard is asymmetric on purpose (a wrong merge hides a real finding),
    # so both stay separate and the near-miss is recorded instead.
    assert len(merged) == 2
    assert len(near_misses) == 1
    nm = near_misses[0]
    assert nm["category"] == "deps"
    assert set(nm["tools"]) == {"depcheck", "trivy"}
    assert set(nm["titles"]) == {
        "Remote code execution via deserialization",
        "SQL injection through crafted header",
    }


def test_deps_findings_sharing_cve_with_package_and_version_both_absent_stay_separate():
    depcheck_finding = _finding(
        "depcheck", "CVE-2026-1234", "openssl vulnerable to buffer overflow", 3,
        cve=["CVE-2026-1234"],
    )
    trivy_finding = _finding(
        "trivy", "CVE-2026-1234", "openssl buffer overflow vulnerability", 3,
        cve=["CVE-2026-1234"],
    )

    merged, near_misses = n.merge_category([depcheck_finding, trivy_finding], "deps")

    # Same CVE and matching titles, but neither carries a package or a
    # version - an absent slot means "does not merge on it", not "matches
    # every other finding that is also missing it" (spec sec 7), so both
    # render on their own.
    assert len(merged) == 2
    assert near_misses == []


def test_deps_findings_sharing_cve_with_only_package_absent_stay_separate():
    depcheck_finding = _finding(
        "depcheck", "CVE-2026-1234", "openssl vulnerable to buffer overflow", 3,
        cve=["CVE-2026-1234"], version="3.0.1",
    )
    trivy_finding = _finding(
        "trivy", "CVE-2026-1234", "openssl buffer overflow vulnerability", 3,
        cve=["CVE-2026-1234"], version="3.0.1",
    )

    merged, near_misses = n.merge_category([depcheck_finding, trivy_finding], "deps")

    assert len(merged) == 2
    assert near_misses == []


def test_deps_findings_sharing_cve_with_only_version_absent_stay_separate():
    depcheck_finding = _finding(
        "depcheck", "CVE-2026-1234", "openssl vulnerable to buffer overflow", 3,
        cve=["CVE-2026-1234"], package="openssl",
    )
    trivy_finding = _finding(
        "trivy", "CVE-2026-1234", "openssl buffer overflow vulnerability", 3,
        cve=["CVE-2026-1234"], package="openssl",
    )

    merged, near_misses = n.merge_category([depcheck_finding, trivy_finding], "deps")

    assert len(merged) == 2
    assert near_misses == []


def test_iac_findings_with_path_line_and_resource_all_absent_stay_separate():
    checkov_finding = _finding(
        "checkov", "CKV_AWS_99",
        "resource has an insecure default configuration", 1,
    )
    trivy_finding = _finding(
        "trivy", "AVD-AWS-0999",
        "insecure default configuration on resource", 2,
    )

    merged, near_misses = n.merge_category([checkov_finding, trivy_finding], "iac")

    # No path, line, or resource on either side (make_finding's own
    # defaults leave host/matched_at as "") - the key is incomplete, so an
    # absent slot must not stand in as a match against another finding's
    # equally-absent slot (spec sec 7).
    assert len(merged) == 2
    assert near_misses == []


def test_nothing_merges_across_categories():
    # An iac-shaped finding carries no `cve` at all, so a deps-category call
    # must never fold it into a deps group no matter what its other fields
    # look like - categories are never mixed within one merge key.
    deps_finding = _finding(
        "trivy", "CVE-2024-2222", "prototype pollution in lodash", 3,
        cve=["CVE-2024-2222"], package="lodash", version="4.17.15",
    )
    iac_finding = _finding(
        "checkov", "CKV_AWS_20", "S3 bucket allows public read", 2,
        host="aws_s3_bucket.foo", matched_at="main.tf:5",
    )

    merged, near_misses = n.merge_category([deps_finding, iac_finding], "deps")

    assert len(merged) == 2
    assert near_misses == []
    untouched = [f for f in merged if f is iac_finding][0]
    assert "tools" not in untouched
    assert "merged_from" not in untouched
