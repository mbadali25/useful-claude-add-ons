"""`worklog.py init` must copy its assets byte-identically on every platform.

The defect this suite exists to catch is Windows-only and **silent**. Both
asset reads in `cmd_init` declared `encoding="utf-8"` on the *write* and
nothing on the *read*, so the read fell through to
`locale.getpreferredencoding(False)` - cp1252 on a default Windows install.
`assets/worklog-readme.md` contains an em dash (U+2014) and the box-drawing
characters of its directory tree (U+2502, U+250C, U+2514, U+2500); every byte
of their UTF-8 encoding is *assigned* in cp1252, so the read does not raise.
It mis-decodes, the utf-8 write re-encodes the mojibake, and `init` exits 0
having written garbage into the file it then tells the user to commit. This
file stays ASCII rather than pasting the mojibake; regenerate it with

    python3 -c "import pathlib; print(pathlib.Path(
        'skills/work-log-reporter/assets/worklog-readme.md'
    ).read_bytes().decode('cp1252'))"

So **an exit-code test passes against the broken code**. Every case here
asserts on bytes or on the absence of a locale-dependent read, never on the
status alone.

`test_init_copies_readme_byte_identical*` compare the whole written file
against the whole asset, so an asset that gains a *new* glyph later is covered
without anyone editing this file - that is the "would a future glyph go red"
property, and it is why these compare bytes rather than grepping for the five
characters that happen to be there today.

Two things no test here can do, stated rather than implied:

* **No Windows host was available.** cp1252 is not an installable locale on
  this runner (`locale -a` lists no single-byte locale at all), so
  `test_init_copies_readme_byte_identical_under_non_utf8_locale` forces the
  ASCII C locale instead. Under the broken code that read raises
  `UnicodeDecodeError` rather than mis-decoding - the same root cause, a
  louder symptom than Windows produces.
* The *silent* Windows shape is therefore covered from the other end, by
  `test_init_does_no_locale_dependent_text_io`, which turns Python's
  `EncodingWarning` (PEP 597) into an error. That case goes red on a UTF-8
  host, where both byte comparisons above are green, and it is the only case
  covering `worklog.config.example.json` - that asset is pure ASCII today, so
  its identical missing-`encoding` read was latent, not live.

SABOTAGE-TESTED: `encoding="utf-8"` was removed from each of the two reads in
`worklog.py` in turn and this suite confirmed RED both times, then restored
and confirmed GREEN. Output quoted in the ticket report.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SKILL_ROOT = Path(__file__).resolve().parent.parent.parent
_WORKLOG = _SKILL_ROOT / "scripts" / "worklog.py"
_README_ASSET = _SKILL_ROOT / "assets" / "worklog-readme.md"
_CONFIG_ASSET = _SKILL_ROOT / "assets" / "worklog.config.example.json"


def _run_init(tmp_path: Path, extra_env: dict[str, str] | None = None,
              extra_argv: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run `worklog.py init` against a throwaway root.

    `WORKLOG_ROOT` is what keeps this off the real repository: `find_root()`
    prefers it over the `.git` climb, so nothing here can reach a checkout.
    `HOME`/`USERPROFILE` are redirected for the same reason.
    """
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)

    env = dict(os.environ)
    env["WORKLOG_ROOT"] = str(root)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env.update(extra_env or {})

    argv = [sys.executable, *(extra_argv or []), str(_WORKLOG), "init",
            "--project", "fixture"]
    return subprocess.run(argv, cwd=root, env=env, capture_output=True,
                          text=True, check=False)


def _written_readme(tmp_path: Path) -> Path:
    return tmp_path / "repo" / "work-log" / "README.md"


def test_readme_asset_still_carries_non_ascii():
    """Guards the other cases against going vacuously green.

    An all-ASCII asset round-trips through *any* encoding, so if someone
    ASCII-ifies this file the byte comparisons below keep passing while
    testing nothing. This fails loudly instead.
    """
    raw = _README_ASSET.read_bytes()

    assert any(byte > 127 for byte in raw), (
        f"{_README_ASSET} is pure ASCII - the encoding cases below no longer "
        "distinguish a correct read from a locale-dependent one"
    )
    assert raw.decode("cp1252").encode("utf-8") != raw, (
        "this asset now survives a cp1252 read unchanged; the regression it "
        "was chosen to expose is no longer reachable through it"
    )


def test_init_copies_readme_byte_identical(tmp_path):
    result = _run_init(tmp_path)

    assert result.returncode == 0, result.stderr
    assert _written_readme(tmp_path).read_bytes() == _README_ASSET.read_bytes()


def test_init_copies_readme_byte_identical_under_non_utf8_locale(tmp_path):
    """The C locale gives an ASCII `locale.getpreferredencoding(False)`.

    `PYTHONUTF8=0` and `PYTHONCOERCECLOCALE=0` are both required: UTF-8 mode
    and PEP 538 locale coercion each independently paper over the C locale and
    would hand the broken code a working default encoding.
    """
    env = {"LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0",
           "PYTHONCOERCECLOCALE": "0"}
    result = _run_init(tmp_path, extra_env=env)

    assert result.returncode == 0, result.stderr
    assert _written_readme(tmp_path).read_bytes() == _README_ASSET.read_bytes()


def test_init_does_no_locale_dependent_text_io(tmp_path):
    """Red on a UTF-8 host, where the byte comparisons above cannot fail.

    `PYTHONWARNDEFAULTENCODING=1` makes every `open()`/`read_text()` that omits
    `encoding=` emit an `EncodingWarning`; `-W error::EncodingWarning` turns
    that into a traceback. This is what covers the ASCII-today
    `worklog.config.example.json` read, and any asset added later.
    """
    env = {"PYTHONWARNDEFAULTENCODING": "1"}
    result = _run_init(tmp_path, extra_env=env,
                       extra_argv=["-W", "error::EncodingWarning"])

    assert "EncodingWarning" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert _written_readme(tmp_path).read_bytes() == _README_ASSET.read_bytes()


@pytest.mark.parametrize("env", [
    {},
    {"LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"},
])
def test_init_writes_config_that_reparses_as_utf8_json(tmp_path, env):
    """The `worklog.config.example.json` read, from the behaviour end.

    Latent rather than live while that asset stays ASCII - if a future edit
    puts a name or a comment with an accent in it, this is the case that
    notices the template no longer survives the copy.
    """
    result = _run_init(tmp_path, extra_env=env)

    assert result.returncode == 0, result.stderr
    written = (tmp_path / "repo" / "work-log" / "worklog.config.json").read_bytes()
    template = json.loads(_CONFIG_ASSET.read_text(encoding="utf-8"))
    produced = json.loads(written.decode("utf-8"))
    template["project"]["name"] = "fixture"
    assert produced == template
