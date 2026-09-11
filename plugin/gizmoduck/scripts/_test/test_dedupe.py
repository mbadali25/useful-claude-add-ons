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
