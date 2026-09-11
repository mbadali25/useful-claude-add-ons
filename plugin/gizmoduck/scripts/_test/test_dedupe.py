import importlib.util
import pytest


@pytest.fixture(scope="module")
def gz(scripts_dir):
    spec = importlib.util.spec_from_file_location("gz", scripts_dir / "gizmoduck.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _f(tid, matched, target=None):
    d = {"template_id": tid, "matched_at": matched, "host": matched,
         "severity": 0, "severity_name": "info", "name": tid}
    if target is not None:
        d["target"] = target
    return d


def test_same_template_different_targets_stay_separate(gz):
    out = gz.dedupe([_f("nuclei:tls-version", "a.example", "site-a"),
                     _f("nuclei:tls-version", "b.example", "site-b")])
    assert len(out) == 2
    assert {g["target"] for g in out} == {"site-a", "site-b"}


def test_same_template_same_target_still_merges(gz):
    out = gz.dedupe([_f("nuclei:tls-version", "a.example/1", "site-a"),
                     _f("nuclei:tls-version", "a.example/2", "site-a")])
    assert len(out) == 1
    assert out[0]["instances"] == 2


def test_no_target_field_preserves_legacy_behaviour(gz):
    """Plain Nuclei findings carry no target - must merge exactly as before."""
    out = gz.dedupe([_f("nuclei:x", "a.example"), _f("nuclei:x", "b.example")])
    assert len(out) == 1
    assert out[0]["raw_count"] == 2
    assert out[0]["affected"] == ["a.example", "b.example"]


# --- HIGH defect: severity provenance and later assessments were dropped --
#
# setdefault() kept only the FIRST record's severity/tags per group; later
# records in the same group only contributed location/count. A group must
# take the HIGHEST severity any member carries, and must keep the
# severity-assigned marker if ANY member has it. Both properties must hold
# regardless of record order.

def _sev(tid, matched, severity, severity_name, target=None, assigned=False):
    d = _f(tid, matched, target)
    d["severity"] = severity
    d["severity_name"] = severity_name
    d["tags"] = ["severity-assigned"] if assigned else []
    return d


def test_group_takes_highest_severity_low_then_critical(gz):
    out = gz.dedupe([
        _sev("checkov:CKV_1", "a.example", 1, "low"),
        _sev("checkov:CKV_1", "a.example/2", 4, "critical"),
    ])
    assert len(out) == 1
    assert out[0]["severity"] == 4
    assert out[0]["severity_name"] == "critical"


def test_group_takes_highest_severity_is_order_independent(gz):
    """Reversing the order of a low and a critical record for the same
    group must not change the reported severity - this is the exact
    regression the earlier setdefault()-based implementation had: whichever
    record arrived first won, regardless of severity.
    """
    forward = gz.dedupe([
        _sev("checkov:CKV_1", "a.example", 1, "low"),
        _sev("checkov:CKV_1", "a.example/2", 4, "critical"),
    ])
    reversed_ = gz.dedupe([
        _sev("checkov:CKV_1", "a.example/2", 4, "critical"),
        _sev("checkov:CKV_1", "a.example", 1, "low"),
    ])
    assert forward[0]["severity"] == reversed_[0]["severity"] == 4
    assert forward[0]["severity_name"] == reversed_[0]["severity_name"] == "critical"


def test_group_retains_severity_assigned_marker_from_any_member(gz):
    """A known-severity finding followed by a null-severity (assigned
    default) one must not lose the severity-assigned marker from the
    aggregate - an assigned default must not be presented as a real
    assessment just because it merged with one that was.
    """
    out = gz.dedupe([
        _sev("checkov:CKV_2", "a.example", 4, "critical", assigned=False),
        _sev("checkov:CKV_2", "a.example/2", 2, "medium", assigned=True),
    ])
    assert len(out) == 1
    assert "severity-assigned" in out[0]["tags"]


def test_group_retains_severity_assigned_marker_regardless_of_order(gz):
    forward = gz.dedupe([
        _sev("checkov:CKV_2", "a.example", 4, "critical", assigned=False),
        _sev("checkov:CKV_2", "a.example/2", 2, "medium", assigned=True),
    ])
    reversed_ = gz.dedupe([
        _sev("checkov:CKV_2", "a.example/2", 2, "medium", assigned=True),
        _sev("checkov:CKV_2", "a.example", 4, "critical", assigned=False),
    ])
    assert "severity-assigned" in forward[0]["tags"]
    assert "severity-assigned" in reversed_[0]["tags"]
    # And the highest severity still wins alongside the retained marker.
    assert forward[0]["severity"] == reversed_[0]["severity"] == 4


def test_hundred_records_same_group_severity_and_tags_order_independent(gz):
    """Order-independence as a general property, not just a two-record
    special case - build the same group from 100 records (one per severity
    band, some severity-assigned) in two different orders. The aggregated
    fields dedupe() actually computes from every member - severity,
    severity_name, the severity-assigned marker, and the affected/instances/
    raw_count rollups - must come out identical either way. (`matched_at`/
    `name`/`host` are seeded from whichever record a group happens to see
    first and were never an order-independent property of dedupe() to begin
    with - not part of this defect.)
    """
    import random

    records = []
    for i in range(100):
        sev = i % 5
        records.append(_sev("checkov:CKV_3", "a.example/%d" % i, sev,
                            gz.SEV_NAME.get(sev, "info").lower(),
                            assigned=(i % 7 == 0)))

    forward = gz.dedupe(records)[0]
    shuffled = records[:]
    random.Random(42).shuffle(shuffled)
    out_of_order = gz.dedupe(shuffled)[0]

    assert forward["severity"] == out_of_order["severity"] == 4
    assert forward["severity_name"] == out_of_order["severity_name"] == "critical"
    assert "severity-assigned" in forward["tags"]
    assert "severity-assigned" in out_of_order["tags"]
    assert forward["raw_count"] == out_of_order["raw_count"] == 100
    assert forward["instances"] == out_of_order["instances"] == 100
    assert forward["affected"] == out_of_order["affected"]
