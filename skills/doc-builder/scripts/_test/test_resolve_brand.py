"""resolve_brand.py's cross-install discovery and opt-out - the paths nothing
covered before this suite (`scripts/_test/` held only `checklist.sh`, which
never touches brand resolution at all).

The property this file exists to prove: **`doc-builder` and `solomon-doc-builder`
are two separate marketplace entries** (`.claude-plugin/marketplace.json` has no
field for expressing "installing this brings that along"), so the only way
Solomon styling reaches a document with zero extra steps is if resolution
already treats two independently-installed plugins from the *same marketplace*
as siblings. It does, via the "plugin cache" search step - `search_locations()`
climbs from `resolve_brand.py`'s own directory and finds a sibling plugin's
`assets/brand.json` two levels up, at the marketplace folder - and that
behaviour had no regression test. `test_two_separate_plugin_installs_resolve_to_solomon`
is the one that matters most: break the cache-climb glob patterns or the
`CACHE_CLIMB` depth and this goes red without anyone needing to install
anything for real.

Every fixture is a throwaway directory tree under pytest's `tmp_path`, laid out
exactly as `claude plugin install` leaves two plugins from one marketplace:
`<tmp>/plugins/cache/<marketplace>/<plugin>/<version>/...`. `resolve_brand.py`
itself is copied into the fixture (not imported) and run as a real subprocess,
because `SCRIPTS_DIR`/`SKILL_ROOT` are computed once at import time from
`__file__` - the exact thing this suite needs to vary between cases - so a
plain `import resolve_brand` from the real checkout location would always
report the checkout's own paths regardless of the fixture. This matches the
subprocess-boundary shape used for `gizmoduck.py` in
`plugin/gizmoduck/scripts/_test/test_tickets_gate.py`.

`HOME`/`USERPROFILE` are pointed at an empty directory in the fixture's own env
so a real machine's `~/.claude/skills` or `~/.claude/plugins/cache` cannot add
a third pack and turn a two-pack case into an ambiguous three-pack one; without
it this suite would be reproducible on a clean machine and nowhere else.

SABOTAGE-TESTED: `CACHE_CLIMB` was changed from `4` to `1` locally and confirmed
`test_two_separate_plugin_installs_resolve_to_solomon` goes RED (no pack found,
falls back to neutral) rather than silently staying green - the climb has to
actually reach the marketplace folder two levels up, not just report a plugin
cache location by name. Restored afterward.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_DOC_BUILDER_ROOT = Path(__file__).resolve().parent.parent.parent
_RESOLVE_BRAND = _DOC_BUILDER_ROOT / "scripts" / "resolve_brand.py"
_NEUTRAL_JSON = _DOC_BUILDER_ROOT / "assets" / "brands" / "neutral" / "brand.json"
_SOLOMON_JSON = _DOC_BUILDER_ROOT.parent / "solomon-doc-builder" / "assets" / "brand.json"

pytestmark = pytest.mark.skipif(
    not _SOLOMON_JSON.is_file(),
    reason="solomon-doc-builder is not checked out as doc-builder's sibling here",
)


def _make_plugin_cache(tmp_path: Path, marketplace: str = "useful-claude-add-ons"):
    """<tmp>/plugins/cache/<marketplace>/doc-builder/1.0.0/... with solomon-doc-builder
    installed alongside it as a SEPARATE plugin - the real shape two `claude plugin
    install` calls against the same marketplace leave on disk. Returns the path to
    the copied resolve_brand.py to run."""
    mp = tmp_path / "plugins" / "cache" / marketplace

    doc_builder = mp / "doc-builder" / "1.0.0"
    (doc_builder / "scripts").mkdir(parents=True)
    (doc_builder / "assets" / "brands" / "neutral").mkdir(parents=True)
    shutil.copy(_RESOLVE_BRAND, doc_builder / "scripts" / "resolve_brand.py")
    shutil.copy(_NEUTRAL_JSON, doc_builder / "assets" / "brands" / "neutral" / "brand.json")

    solomon = mp / "solomon-doc-builder" / "1.0.0"
    (solomon / "assets").mkdir(parents=True)
    shutil.copy(_SOLOMON_JSON, solomon / "assets" / "brand.json")

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()

    return doc_builder / "scripts" / "resolve_brand.py", fake_home


def _run(script: Path, fake_home: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"PATH": __import__("os").environ.get("PATH", ""),
           "HOME": str(fake_home), "USERPROFILE": str(fake_home)}
    return subprocess.run(
        [sys.executable, str(script), *args],
        env=env, capture_output=True, text=True, timeout=30, check=False,
    )


def test_two_separate_plugin_installs_resolve_to_solomon(tmp_path):
    """The property this file exists to prove: doc-builder and solomon-doc-builder,
    installed as two independent plugins from one marketplace with no dependency
    field connecting them, still resolve to Solomon with no --brand and no env var -
    nobody has to ask."""
    script, fake_home = _make_plugin_cache(tmp_path)
    result = _run(script, fake_home, "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["name"] == "solomon"

    # --json suppresses the announce (see main()'s `announce=not args.json`);
    # a plain run is what actually names the pack and why on stderr.
    plain = _run(script, fake_home)
    assert "solomon" in plain.stderr


def test_explicit_neutral_opts_out_even_with_solomon_installed(tmp_path):
    """--brand neutral always wins - the opt-out for someone who does not want
    branded output even though a brand pack is present."""
    script, fake_home = _make_plugin_cache(tmp_path)
    result = _run(script, fake_home, "--brand", "neutral", "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["name"] == "neutral"


def test_env_var_opts_out_the_same_way(tmp_path):
    """DOC_BUILDER_BRAND=neutral is the same opt-out for a caller that cannot pass
    a flag (a wrapper script, a scheduled task)."""
    script, fake_home = _make_plugin_cache(tmp_path)
    env = {"PATH": __import__("os").environ.get("PATH", ""),
           "HOME": str(fake_home), "USERPROFILE": str(fake_home),
           "DOC_BUILDER_BRAND": "neutral"}
    result = subprocess.run([sys.executable, str(script), "--json"],
                            env=env, capture_output=True, text=True,
                            timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["name"] == "neutral"


def test_two_different_packs_refuses_and_names_both(tmp_path):
    """A second, differently-named pack turns "the only one found" into an
    ambiguous choice - refused rather than guessed, naming both packs, per the
    module docstring's step 5."""
    script, fake_home = _make_plugin_cache(tmp_path)
    marketplace_dir = script.parent.parent.parent.parent  # .../<marketplace>/
    other = marketplace_dir / "acme-doc-builder" / "1.0.0" / "assets"
    other.mkdir(parents=True)
    (other / "brand.json").write_text(
        json.dumps({"name": "acme", "organisation": "Acme Corp"}), encoding="utf-8")

    result = _run(script, fake_home)
    assert result.returncode != 0
    assert "solomon" in result.stderr and "acme" in result.stderr
    assert "--brand" in result.stderr


def test_no_pack_installed_falls_back_to_neutral_loudly(tmp_path):
    """No sibling plugin present at all -> neutral, and the fallback names every
    location it searched rather than silently rendering unbranded output."""
    mp = tmp_path / "plugins" / "cache" / "useful-claude-add-ons"
    doc_builder = mp / "doc-builder" / "1.0.0"
    (doc_builder / "scripts").mkdir(parents=True)
    (doc_builder / "assets" / "brands" / "neutral").mkdir(parents=True)
    shutil.copy(_RESOLVE_BRAND, doc_builder / "scripts" / "resolve_brand.py")
    shutil.copy(_NEUTRAL_JSON, doc_builder / "assets" / "brands" / "neutral" / "brand.json")
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()

    script = doc_builder / "scripts" / "resolve_brand.py"
    result = _run(script, fake_home, "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["name"] == "neutral"

    plain = _run(script, fake_home)
    assert "no brand pack found" in plain.stderr
    assert "Searched:" in plain.stderr


def test_windows_drive_path_resolves_absolute_on_linux(tmp_path):
    """A brand pack's masters_dir/assets_dir can be authored on Windows
    (`C:\\repos\\...`) and read on Linux - that is exactly what
    solomon-doc-builder/assets/brand.json does. Before this fix, `_rel()`
    only recognised the CURRENT OS's own absolute form (`os.path.isabs()`),
    so on Linux a `C:\\...` value read as relative and got silently joined
    onto `assets/`, producing something like
    `.../solomon-doc-builder/assets/C:\\repos\\OnboardingSOPs\\sops_new` -
    which `--json` printed with no indication anything was wrong.

    SABOTAGE-TESTED: reverting `_rel()` to `return value if os.path.isabs(value)
    else os.path.normpath(os.path.join(self.root, value))` makes this go RED
    on Linux - `masters_dir` comes back containing the literal string
    `assets/C:` instead of `/repos/OnboardingSOPs/sops_new`.
    """
    script, fake_home = _make_plugin_cache(tmp_path)
    marketplace_dir = script.parent.parent.parent.parent  # .../<marketplace>/
    pack = marketplace_dir / "acme-doc-builder" / "1.0.0" / "assets"
    pack.mkdir(parents=True)
    (pack / "brand.json").write_text(json.dumps({
        "name": "acme",
        "sop": {
            "masters_dir": "C:\\repos\\OnboardingSOPs\\sops_new",
            "assets_dir": "C:\\repos\\OnboardingSOPs\\assets",
        },
    }), encoding="utf-8")
    # Remove the sibling solomon pack so acme is the only one found, rather
    # than an ambiguous two-pack case this test is not about.
    shutil.rmtree(marketplace_dir / "solomon-doc-builder")

    result = _run(script, fake_home, "--json")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    # --json prints the merged SOURCE dict, before _rel() resolves anything -
    # this should be the untouched Windows string.
    assert data["sop"]["masters_dir"] == "C:\\repos\\OnboardingSOPs\\sops_new"

    if os.name != "nt":
        # The resolved (made-absolute) paths only show up in the plain,
        # non-JSON run.
        plain = _run(script, fake_home)
        assert plain.returncode == 0, plain.stderr
        assert "/repos/OnboardingSOPs/sops_new" in plain.stdout
        assert "/repos/OnboardingSOPs/assets" in plain.stdout
        assert "assets/C:" not in plain.stdout
        assert "NOT FOUND" in plain.stdout  # honestly reported, not silently swallowed


# -- logo resolution -----------------------------------------------------------
#
# These four run against the REAL checkout rather than a copied fixture, and
# import resolve_brand directly instead of shelling out to a copy of it. That
# is a deliberate departure from every test above, not an oversight: the
# module docstring's reason for the subprocess boundary is that SCRIPTS_DIR/
# SKILL_ROOT are fixed at import time from __file__, which only matters when a
# test needs to VARY that location (a fixture standing in for a different
# install layout). Nothing below does - the property under test IS "what the
# real, committed solomon-doc-builder/assets/ directory resolves to", so the
# real __file__ location is exactly what these tests want, and copying only
# brand.json into a fixture (as `_make_plugin_cache` does) would leave the
# logo/*.png files it points at missing, proving nothing.

_SCRIPTS_DIR = _DOC_BUILDER_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import resolve_brand  # noqa: E402  pylint: disable=wrong-import-position


def test_solomon_logo_variants_resolve_to_existing_files():
    """All four committed logo files - two wordmark, two icon - resolve to a
    path that actually exists on disk, not just a plausible-looking string."""
    brand = resolve_brand.resolve(explicit=str(_SOLOMON_JSON), announce=False)
    for background in ("light", "dark"):
        logo = brand.logo_for(background)
        assert logo, f"logo_for({background!r}) resolved to nothing"
        assert os.path.isfile(logo), f"logo_for({background!r}) -> {logo} does not exist"
        icon = brand.icon_for(background)
        assert icon, f"icon_for({background!r}) resolved to nothing"
        assert os.path.isfile(icon), f"icon_for({background!r}) -> {icon} does not exist"


def test_neutral_pack_has_no_logo_and_resolution_returns_absent():
    """The neutral pack carries the `logo` key (every key in the schema is
    present, per brand.json's own _comment), but every value is null - so
    resolution must return the absent value, not raise and not synthesise a
    path that looks plausible but points nowhere."""
    brand = resolve_brand.resolve(explicit="neutral", announce=False)
    for background in ("light", "dark"):
        assert brand.logo_for(background) is None
        assert brand.icon_for(background) is None


def test_windows_style_logo_path_resolves_absolute_on_linux(tmp_path):
    """The same `os.path.isabs()` trap `_rel()` was fixed for on
    masters_dir/assets_dir applies to a logo path too - it goes through the
    exact same `_rel()` method, but nothing exercised that fact until now.

    SABOTAGE-TESTED: reverting `_rel()` to
    `return value if os.path.isabs(value) else os.path.normpath(os.path.join(self.root, value))`
    makes this go RED on Linux - `logo_for("dark")` comes back joined onto the
    pack's assets/ directory (`.../assets/C:\\fake\\logo.png`) instead of
    `/fake/logo.png`.
    """
    pack_dir = tmp_path / "acme-doc-builder" / "assets"
    pack_dir.mkdir(parents=True)
    (pack_dir / "brand.json").write_text(json.dumps({
        "name": "acme",
        "logo": {"on_dark": "C:\\fake\\logo.png"},
    }), encoding="utf-8")

    brand = resolve_brand.resolve(explicit=str(pack_dir / "brand.json"), announce=False)
    resolved = brand.logo_for("dark")
    if os.name != "nt":
        assert resolved == "/fake/logo.png", resolved
        assert "assets/C:" not in resolved


def test_logo_for_selects_the_variant_that_matches_the_background():
    """`logo_for("dark")` must return the `-on-dark` file and `logo_for("light")`
    the `-on-light` file - asserted by exact filename, not merely "not None",
    so a later refactor that swaps the two (making the logo invisible against
    its own background) goes red here rather than only in a rendered document
    nobody is looking at."""
    brand = resolve_brand.resolve(explicit=str(_SOLOMON_JSON), announce=False)
    assert os.path.basename(brand.logo_for("dark")) == "solomon-logo-on-dark.png"
    assert os.path.basename(brand.logo_for("light")) == "solomon-logo-on-light.png"
    assert os.path.basename(brand.icon_for("dark")) == "solomon-icon-on-dark.png"
    assert os.path.basename(brand.icon_for("light")) == "solomon-icon-on-light.png"


def test_logo_for_rejects_an_unknown_background():
    brand = resolve_brand.resolve(explicit="neutral", announce=False)
    with pytest.raises(ValueError):
        brand.logo_for("navy")
