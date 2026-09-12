import sys
from scanners import base


def test_run_tool_returns_nonzero_without_raising():
    r = base.run_tool([sys.executable, "-c", "import sys; sys.exit(3)"], timeout=10)
    assert r.returncode == 3 and r.timed_out is False


def test_run_tool_marks_timeout_instead_of_hanging():
    r = base.run_tool([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)
    assert r.timed_out is True


def test_which_returns_none_for_missing_binary():
    assert base.which("definitely-not-a-real-binary-xyz") is None


def test_registry_lists_ten_tools_and_no_tfsec():
    """Ten since semgrep was added for the `code` kind. Still no tfsec: its
    engine was folded into Trivy in 2023 and its rules stopped moving in 2025,
    so IaC coverage runs through trivy's misconfig scanner (spec 13.4)."""
    import scanners
    assert len(scanners.ADAPTERS) == 10
    assert "tfsec" not in scanners.ADAPTERS
    assert "semgrep" in scanners.ADAPTERS
    assert set(scanners.KIND_DEFAULTS) == {"web", "host", "iac", "deps", "code"}


def test_every_kind_default_names_a_registered_adapter():
    """A kind whose default list names an adapter the registry does not hold
    produces an empty adapter list at run time, which routine cannot tell apart
    from a clean scan."""
    import scanners
    for kind, names in scanners.KIND_DEFAULTS.items():
        assert names, "kind %r has an empty default adapter list" % kind
        for name in names:
            assert name in scanners.ADAPTERS, \
                "kind %r defaults to unknown adapter %r" % (kind, name)


def test_every_kind_has_a_location_resolver():
    """The registry and routine's location map are two halves of the same
    fact; either alone leaves a kind unroutable."""
    import routine
    import scanners
    for kind in scanners.KIND_DEFAULTS:
        assert routine._location_field_name(kind)


def test_every_registered_adapter_satisfies_the_protocol():
    import scanners
    for name, mod in scanners.ADAPTERS.items():
        for attr in ("NAME", "KINDS", "ACTIVE", "DEFAULT_ENABLED",
                     "is_available", "run", "parse"):
            assert hasattr(mod, attr), "%s missing %s" % (name, attr)
        assert mod.NAME == name
