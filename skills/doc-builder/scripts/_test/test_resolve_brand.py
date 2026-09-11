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
        env=env, capture_output=True, text=True, timeout=30,
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
                             env=env, capture_output=True, text=True, timeout=30)
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
