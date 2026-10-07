"""ci_inventory - module discovery, declared vs detected rows, purity, and the
stale check (`gizmoduck_ci.py check`).

The fixture repository, fixtures/monorepo/, is modelled on a real monorepo's
layout: `billing-portal/` declares its endpoints in `public-endpoint.md` (that
repository's frontmatter format), `orders-api/` declares nothing and is
autodetected, `docs/` holds a package.json but is excluded by default, and
`tools/` has no project marker. Its committed `endpoints-inventory.md` is the
golden file: test_committed_fixture_inventory_is_current fails when rendering
changes, and GIZMODUCK_UPDATE_GOLDEN=1 rewrites it.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import ci_inventory
import pytest

_CLI = Path(__file__).resolve().parent.parent / "gizmoduck_ci.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "monorepo"


def conf(**kw):
    return ci_inventory.settings(None, **kw)


def cli(*argv):
    return subprocess.run([sys.executable, str(_CLI), *argv], capture_output=True, text=True, check=False)


@pytest.fixture()
def repo(tmp_path):
    dst = tmp_path / "repo"
    shutil.copytree(FIXTURE, dst)
    return dst


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------

def test_discovers_one_declared_and_one_detected_module():
    assert ci_inventory.discover_modules(str(FIXTURE), conf()) == ["billing-portal", "orders-api"]


def test_outermost_module_wins_and_markers_below_it_are_not_modules():
    mods = ci_inventory.discover_modules(str(FIXTURE), conf())
    assert "billing-portal/frontend" not in mods and "billing-portal/terraform" not in mods


def test_docs_is_excluded_by_default_and_can_be_included(repo):
    assert "docs" in ci_inventory.discover_modules(str(repo), conf(exclude=["nothing-excluded"]))


def test_single_project_repo_is_module_dot(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    assert ci_inventory.discover_modules(str(tmp_path), conf()) == ["."]


def test_a_symlinked_directory_is_never_a_module(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "package.json").write_text("{}", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    os.symlink(outside, repo / "linked")
    assert ci_inventory.discover_modules(str(repo), conf()) == []


def test_roots_and_excludes_come_from_gizmoduck_ci_json(repo):
    config = {"inventory": {"roots": ["orders-api"], "exclude": []}}
    assert ci_inventory.discover_modules(str(repo), ci_inventory.settings(config)) == ["orders-api"]


@pytest.mark.parametrize("kw,needle", [
    ({"output": "../escape.md"}, "plain *.md file name"),
    ({"output": "sub/dir.md"}, "plain *.md file name"),
    ({"output": "inventory.txt"}, "plain *.md file name"),
    ({"roots": ["../other"]}, "stay inside the repository"),
    ({"roots": ["/etc"]}, "stay inside the repository"),
])
def test_settings_refuse_paths_outside_the_repository(kw, needle):
    with pytest.raises(ci_inventory.InventoryError, match=re.escape(needle)):
        conf(**kw)


# --------------------------------------------------------------------------
# rows
# --------------------------------------------------------------------------

def _module(path):
    return next(m for m in ci_inventory.build(str(FIXTURE), conf()) if m["path"] == path)


def test_declared_module_uses_the_declaration_only():
    m = _module("billing-portal")
    assert m["mode"] == "declared" and m["name"] == "Billing Portal"
    assert [r["endpoint"] for r in m["rows"]] == [
        "https://***@admin.billing.example.test/",      # credentials redacted
        "https://api.billing.example.test/v1",
        "https://billing.example.test",
    ]
    main = m["rows"][-1]
    assert main["staging_url"] == "https://billing.staging.example.test"
    assert main["where"] == "billing-portal/public-endpoint.md"
    assert all(r["source"] == "declared" for r in m["rows"])


def test_detected_module_lists_confidence_source_and_staging_url():
    m = _module("orders-api")
    assert m["mode"] == "detected"
    assert m["staging_base"]["url"] == "https://orders.staging.example.test"
    rows = {(r["method"], r["endpoint"]): r for r in m["rows"]}
    assert set(rows) == {("GET", "/api/orders"), ("POST", "/api/orders"), ("GET", "/api/orders/{id}")}
    post = rows[("POST", "/api/orders")]
    assert post["confidence"] == "high, protected"
    assert post["where"] == "orders-api/Controllers/OrdersController.cs"
    assert rows[("GET", "/api/orders/{id}")]["staging_url"] == "https://orders.staging.example.test/api/orders/{id}"
    assert rows[("GET", "/api/orders/{id}")]["scan_url"] == "https://orders.staging.example.test/api/orders"


def test_staging_url_is_undetermined_rather_than_guessed(repo):
    (repo / "orders-api" / "appsettings.Staging.json").unlink()
    m = next(m for m in ci_inventory.build(str(repo), conf()) if m["path"] == "orders-api")
    assert m["staging_base"] is None
    assert {r["staging_url"] for r in m["rows"]} == {"undetermined"}
    assert "Staging base: undetermined." in ci_inventory.generate(str(repo), conf())


def test_a_module_with_no_endpoint_is_unverified(repo):
    shutil.rmtree(repo / "orders-api" / "Controllers")
    text = ci_inventory.generate(str(repo), conf())
    assert "| Modules with no endpoint (UNVERIFIED) | 1 |" in text
    assert "**UNVERIFIED** - no endpoint declared or detected" in text


# --------------------------------------------------------------------------
# fail-closed discovery: a directory this cannot fully read is never a
# silent, passing empty result (BLOCK, ci_inventory.py:130)
# --------------------------------------------------------------------------

def test_an_unreadable_directory_fails_discovery_closed_instead_of_dropping_the_module(repo, monkeypatch):
    """Root can read anything a real chmod would block, so the repro forces
    os.scandir to raise - exactly the alternative the finding names."""
    blocked = os.path.normpath(os.path.join(str(repo), "orders-api"))
    real_scandir = ci_inventory.os.scandir

    def fake_scandir(path):
        if os.path.normpath(os.fspath(path)) == blocked:
            raise PermissionError(13, "Permission denied")
        return real_scandir(path)

    monkeypatch.setattr(ci_inventory.os, "scandir", fake_scandir)

    with pytest.raises(ci_inventory.InventoryError, match=re.escape("orders-api") + ".*cannot read directory"):
        ci_inventory.build(str(repo), conf())
    # The stale check must fail closed too - never silently pass on an
    # incomplete discovery.
    with pytest.raises(ci_inventory.InventoryError):
        ci_inventory.check(str(repo), conf())


def test_a_scandir_error_partway_through_a_directory_also_fails_closed(repo, monkeypatch):
    blocked = os.path.normpath(str(repo))
    real_scandir = ci_inventory.os.scandir

    class _BoomIter:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __iter__(self):
            raise OSError("stat failed mid-read")

    def fake_scandir(path):
        if os.path.normpath(os.fspath(path)) == blocked:
            return _BoomIter()
        return real_scandir(path)

    monkeypatch.setattr(ci_inventory.os, "scandir", fake_scandir)

    with pytest.raises(ci_inventory.InventoryError, match="cannot read directory"):
        ci_inventory.discover_modules(str(repo), conf())


def test_more_entries_than_the_bound_fails_closed_rather_than_depending_on_readdir_order(tmp_path):
    """The 20,000-entry cap used to be applied before sorting, so which
    module survived depended on filesystem enumeration order. It must now
    fail closed instead of silently keeping (or dropping) an arbitrary one."""
    monkeypatch_bound = ci_inventory._MAX_DIR_ENTRIES
    try:
        ci_inventory._MAX_DIR_ENTRIES = 5
        for i in range(6):
            (tmp_path / f"sibling-{i}").mkdir()
        (tmp_path / "sibling-3" / "package.json").write_text("{}", encoding="utf-8")
        with pytest.raises(ci_inventory.InventoryError, match="more than 5 entries"):
            ci_inventory.discover_modules(str(tmp_path), conf())
    finally:
        ci_inventory._MAX_DIR_ENTRIES = monkeypatch_bound


# --------------------------------------------------------------------------
# safe Markdown encoding (FIX, ci_inventory.py:411)
# --------------------------------------------------------------------------

def test_a_newline_bearing_module_path_cannot_forge_a_heading(repo):
    """A directory name may legally hold a raw newline on Linux; the
    generated heading must never let it start a new document line."""
    evil = repo / "weird\n\n# Forged Heading\n\nname"
    evil.mkdir()
    (evil / "package.json").write_text("{}", encoding="utf-8")
    text = ci_inventory.generate(str(repo), conf())
    assert "\n# Forged Heading\n" not in text
    assert "## weird" in text


def test_an_html_bearing_declared_name_is_neutralised(repo):
    decl = repo / "billing-portal" / "public-endpoint.md"
    decl.write_text(decl.read_text(encoding="utf-8").replace(
        'name: "Billing Portal"', 'name: "<img src=x onerror=alert(1)>"'), encoding="utf-8")
    text = ci_inventory.generate(str(repo), conf())
    assert "<img" not in text and "&lt;img" in text


def test_a_backtick_bearing_value_still_renders_as_a_code_span(repo):
    decl = repo / "billing-portal" / "public-endpoint.md"
    decl.write_text(decl.read_text(encoding="utf-8").replace(
        "https://billing.example.test", "https://billing.example.test/`x`"), encoding="utf-8")
    text = ci_inventory.generate(str(repo), conf())
    assert "`` https://billing.example.test/`x` ``" in text   # a longer fence, never a bare fallback
    assert "| https://billing.example.test/`x` |" not in text   # never emitted unquoted


@pytest.mark.parametrize("front,needle", [
    ('name: "x"\n', "missing required frontmatter key `url`"),
    ('url: "https://a.example.test"\n', "missing required frontmatter key `name`"),
    ('name: "x"\nurl: >\n  https://a.example.test\n', "public-endpoint.md:3: block, flow"),
    ('name: "x\nurl: "https://a.example.test"\n', "public-endpoint.md:2: unterminated"),
    ('name: "x"\nurl: "https://a.example.test"\nurl: "https://b.example.test"\n', "declared twice"),
])
def test_an_unreadable_declaration_is_an_error_naming_path_and_line(repo, front, needle):
    (repo / "billing-portal" / "public-endpoint.md").write_text(f"---\n{front}---\nbody\n", encoding="utf-8")
    p = cli("inventory", "--repo", str(repo))
    assert p.returncode == 2 and "GIZMODUCK_INVENTORY_FAILED" in p.stderr and needle in p.stderr, p.stderr


def test_unknown_keys_and_their_continuations_are_ignored(repo):
    decl = repo / "billing-portal" / "public-endpoint.md"
    decl.write_text(decl.read_text(encoding="utf-8").replace(
        "owner:", "notes: >\n  folded text: with a colon\n  - and a dash\nowner:"), encoding="utf-8")
    assert cli("check", "--repo", str(repo)).returncode == 0


# --------------------------------------------------------------------------
# purity
# --------------------------------------------------------------------------

def test_committed_fixture_inventory_is_current():
    text = ci_inventory.generate(str(FIXTURE), conf())
    path = FIXTURE / "endpoints-inventory.md"
    if os.environ.get("GIZMODUCK_UPDATE_GOLDEN") == "1":
        path.write_bytes(text.encode("utf-8"))
    assert path.read_bytes().decode("utf-8") == text


def test_render_is_byte_identical_across_runs_and_checkout_paths(tmp_path):
    a, b = tmp_path / "a" / "deep" / "one", tmp_path / "b"
    shutil.copytree(FIXTURE, a)
    shutil.copytree(FIXTURE, b)
    first = ci_inventory.generate(str(a), conf())
    assert ci_inventory.generate(str(a), conf()) == first
    assert ci_inventory.generate(str(b), conf()) == first
    assert str(tmp_path) not in first and "/tmp" not in first


def test_render_carries_no_date_and_only_lf():
    text = ci_inventory.generate(str(FIXTURE), conf())
    assert not re.search(r"\b(19|20)\d\d-\d\d-\d\d\b", text)
    assert not re.search(r"\b\d\d:\d\d(:\d\d)?\b", text)
    assert "\r" not in text and text.endswith("\n") and not text.endswith("\n\n")
    assert "Generated, do not edit." in text


def test_output_name_is_configurable(repo):
    p = cli("inventory", "--repo", str(repo), "--output", "ENDPOINTS.md")
    assert p.returncode == 0 and (repo / "ENDPOINTS.md").is_file()
    assert cli("check", "--repo", str(repo), "--output", "ENDPOINTS.md").returncode == 0


# --------------------------------------------------------------------------
# the stale check
# --------------------------------------------------------------------------

def test_check_passes_on_a_current_inventory(repo):
    p = cli("check", "--repo", str(repo))
    assert p.returncode == 0 and "is current" in p.stdout, p.stdout + p.stderr


@pytest.mark.parametrize("change", ["declared url", "declaration removed", "route added", "file missing",
                                    "hand edit"])
def test_check_fails_with_a_regenerate_hint_when_stale(repo, change):
    decl = repo / "billing-portal" / "public-endpoint.md"
    if change == "declared url":
        decl.write_text(decl.read_text(encoding="utf-8").replace("https://billing.example.test",
                                                                 "https://billing2.example.test"), encoding="utf-8")
    elif change == "declaration removed":
        decl.unlink()
    elif change == "route added":
        ctl = repo / "orders-api" / "Controllers" / "OrdersController.cs"
        ctl.write_text(ctl.read_text(encoding="utf-8").replace(
            "    [Authorize]", '    [HttpDelete("{id:int}")]\n    public IActionResult Delete(int id) => Ok();\n\n'
                              "    [Authorize]"), encoding="utf-8")
    elif change == "file missing":
        (repo / "endpoints-inventory.md").unlink()
    else:
        inv = repo / "endpoints-inventory.md"
        inv.write_text(inv.read_text(encoding="utf-8").replace("Billing Portal", "Billing Portal (edited)"),
                       encoding="utf-8")

    p = cli("check", "--repo", str(repo))

    assert p.returncode == 1, p.stdout + p.stderr
    assert "GIZMODUCK_INVENTORY_STALE" in p.stderr and ci_inventory.REGENERATE in p.stderr


def test_regenerating_makes_a_stale_inventory_current(repo):
    decl = repo / "billing-portal" / "public-endpoint.md"
    decl.write_text(decl.read_text(encoding="utf-8").replace('status: "live"', 'status: "staging"'),
                    encoding="utf-8")
    assert cli("check", "--repo", str(repo)).returncode == 1

    assert cli("inventory", "--repo", str(repo)).returncode == 0

    assert cli("check", "--repo", str(repo)).returncode == 0


def test_check_shows_what_changed(repo):
    decl = repo / "billing-portal" / "public-endpoint.md"
    decl.write_text(decl.read_text(encoding="utf-8").replace("https://api.billing.example.test/v1",
                                                             "https://api.billing.example.test/v2"), encoding="utf-8")
    p = cli("check", "--repo", str(repo))
    assert "-| `https://api.billing.example.test/v1`" in p.stdout
    assert "+| `https://api.billing.example.test/v2`" in p.stdout


def test_a_crlf_checkout_of_a_current_inventory_is_current(repo):
    inv = repo / "endpoints-inventory.md"
    inv.write_bytes(inv.read_bytes().replace(b"\n", b"\r\n"))
    assert cli("check", "--repo", str(repo)).returncode == 0
