"""The semgrep rules in plugin/crew/lint/semgrep/crew-classes.yml (L-0715).

The pinned semgrep runs over a throwaway copy of the fixtures. A semgrep that cannot start FAILS
these tests: an unknown must not collapse into a pass (GEN-01). Only CREW_SKIP_SEMGREP=1 skips
them, and the skip message names that variable.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
LINT = ROOT / "plugin" / "crew" / "lint" / "semgrep"
RULES = LINT / "crew-classes.yml"
FIXTURES = LINT / "fixtures"

SEMGREP_PIN = "semgrep==1.95.0"
SKIP_VARIABLE = "CREW_SKIP_SEMGREP"
WINDOWS_SKIP_REASON = (
    "semgrep 1.95.0 ships no semgrep-core.exe on native Windows (CI: 'Failed to find semgrep-core.exe'); "
    "L-0715 PR B owns a stdlib checker for every host. Skipped on the OS, not on uvx being missing: "
    "on any other host a missing uvx still fails."
)
TIMEOUT_SECONDS = 180

CLASSES = (
    "u2028-line-protocol",
    "unquoted-plugin-root",
    "symlink-fifo-open",
    "duplicate-key-json",
    "bare-executable",
    "test-no-assertion",
)
PROTECTED = ("u2028-line-protocol", "duplicate-key-json", "bare-executable")


def _environment():
    """semgrep needs a HOME with a `.config`, and a fresh uv cache would download the pinned semgrep
    and Python on every run. HOME, USERPROFILE, the XDG directories and both caches live in one temp tree that survives
    between runs, so nothing here touches the real home whatever the caller's HOME is."""
    env = dict(os.environ)
    cache = pathlib.Path(tempfile.gettempdir()) / "crew-semgrep-uv"
    home = cache / "home"
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    for name, leaf in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                       ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache")):
        (home / leaf).mkdir(parents=True, exist_ok=True)
        env[name] = str(home / leaf)
    env["UV_CACHE_DIR"] = str(cache / "cache")
    env["UV_PYTHON_INSTALL_DIR"] = str(cache / "python")
    return env


def _command(*args):
    uvx = shutil.which("uvx")
    if uvx is None:
        pytest.fail(
            "uvx is not on PATH, so the pinned semgrep cannot start; install uv, or set "
            + SKIP_VARIABLE + "=1 to skip these tests on a host that cannot run it"
        )
    return [
        uvx, "--python", "3.12", "--with", "setuptools<81", "--from", SEMGREP_PIN, "semgrep",
        "--metrics=off", "--disable-version-check", "--quiet", *args,
    ]


@pytest.fixture
def semgrep_required():
    if sys.platform == "win32":
        pytest.skip(WINDOWS_SKIP_REASON)
    if os.environ.get(SKIP_VARIABLE) == "1":
        pytest.skip("semgrep tests skipped because " + SKIP_VARIABLE + "=1 is set")


def _rule_blocks():
    """(id, class, enabled) for every rule, read from the YAML text so this needs no YAML package."""
    text = RULES.read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^  - id: ", text)[1:]
    found = []
    for block in blocks:
        rule_id = block.splitlines()[0].strip()
        match = re.search(r"(?m)^      class: (\S+)\s*$", block)
        assert match, "rule " + rule_id + " has no metadata.class"
        found.append((rule_id, match.group(1)))
    return found


def _not_shipped():
    text = RULES.read_text(encoding="utf-8")
    listed = {}
    in_block = False
    for line in text.splitlines():
        if line.startswith("# not-shipped:"):
            in_block = True
            continue
        if in_block:
            match = re.match(r"#   ([a-z0-9-]+): (\S.*)$", line)
            if not match:
                break
            listed[match.group(1)] = match.group(2)
    return listed


def _run_over_fixtures(tmp_path):
    copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, copy)
    done = subprocess.run(
        _command("--config", str(RULES), "--json", str(copy)),
        capture_output=True, text=True, check=False, timeout=TIMEOUT_SECONDS, env=_environment(),
    )
    assert done.returncode == 0, "semgrep exited " + str(done.returncode) + ": " + done.stderr[-2000:]
    payload = json.loads(done.stdout)
    assert payload["errors"] == [], "semgrep reported errors: " + json.dumps(payload["errors"])[:2000]
    return copy, payload["results"]


def test_every_class_is_shipped_or_listed_not_shipped():
    shipped = {cls for _rule, cls in _rule_blocks()}
    not_shipped = set(_not_shipped())

    unknown = (shipped | not_shipped) - set(CLASSES)
    missing = set(CLASSES) - shipped - not_shipped

    assert not unknown, "unknown classes: " + ", ".join(sorted(unknown))
    assert not missing, "classes neither shipped nor listed under not-shipped: " + ", ".join(sorted(missing))
    assert not (shipped & not_shipped), "a class is both shipped and listed not-shipped"
    assert all(reason.strip() for reason in _not_shipped().values())


def test_enabled_rules_cover_at_least_four_classes():
    shipped = {cls for _rule, cls in _rule_blocks()}

    assert len(shipped) >= 4


def test_at_most_two_classes_are_not_shipped_and_never_a_protected_one():
    not_shipped = set(_not_shipped())

    assert len(not_shipped) <= 2
    assert not not_shipped.intersection(PROTECTED)


def test_every_rule_has_one_positive_and_one_negative_fixture():
    for rule_id, _cls in _rule_blocks():
        names = [path.name for path in (FIXTURES / rule_id).iterdir()]

        assert any("positive" in name for name in names), rule_id + " has no positive fixture"
        assert any("negative" in name for name in names), rule_id + " has no negative fixture"


def test_each_rule_matches_its_positive_fixture_and_not_its_negative_one(semgrep_required, tmp_path):
    copy, results = _run_over_fixtures(tmp_path)

    hits = {}
    for result in results:
        rule_id = result["check_id"].rsplit(".", 1)[-1]
        relative = pathlib.Path(result["path"]).resolve().relative_to(copy.resolve())
        hits.setdefault(rule_id, set()).add(relative.as_posix())

    for rule_id, _cls in _rule_blocks():
        files = {path.name for path in (FIXTURES / rule_id).iterdir()}
        positives = {rule_id + "/" + name for name in files if "positive" in name}
        negatives = {rule_id + "/" + name for name in files if "negative" in name}
        got = hits.get(rule_id, set())

        assert positives <= got, rule_id + " missed its positive fixture; hit only " + str(sorted(got))
        stray = sorted(negatives.intersection(got))
        assert not stray, rule_id + " fired on its negative fixture: " + str(stray)


def test_rules_in_one_fixture_directory_do_not_fire_on_another_rules_fixtures(semgrep_required, tmp_path):
    copy, results = _run_over_fixtures(tmp_path)

    stray = []
    for result in results:
        rule_id = result["check_id"].rsplit(".", 1)[-1]
        relative = pathlib.Path(result["path"]).resolve().relative_to(copy.resolve()).as_posix()
        if not relative.startswith(rule_id + "/"):
            stray.append(rule_id + " on " + relative)

    assert stray == []
