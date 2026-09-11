def test_fixture_helper_resolves_under_test_dir(fixture):
    p = fixture("sample.json")
    assert p.parent.name == "fixtures"
    assert p.parent.parent.name == "_test"


def test_plugin_root_contains_scripts(plugin_root):
    assert (plugin_root / "scripts" / "gizmoduck.py").is_file()
