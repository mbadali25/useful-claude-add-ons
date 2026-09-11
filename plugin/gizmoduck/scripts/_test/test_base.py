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


def test_registry_lists_nine_tools_and_no_tfsec():
    import scanners
    assert len(scanners.ADAPTERS) == 9
    assert "tfsec" not in scanners.ADAPTERS
    assert set(scanners.KIND_DEFAULTS) == {"web", "host", "iac", "deps"}


def test_every_registered_adapter_satisfies_the_protocol():
    import scanners
    for name, mod in scanners.ADAPTERS.items():
        for attr in ("NAME", "KINDS", "ACTIVE", "DEFAULT_ENABLED",
                     "is_available", "run", "parse"):
            assert hasattr(mod, attr), "%s missing %s" % (name, attr)
        assert mod.NAME == name
