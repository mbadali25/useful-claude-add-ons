"""The troubleshooting guide names config keys and script paths as facts about
the shipped code. Nothing renders this guide at runtime, so nothing else would
notice a key that got renamed out from under it, or a script that moved.

Two directions, extracted straight out of the guide's own text rather than
from a second list kept here -- a parallel list would drift the moment the
guide changes and nobody touched this file:

  * Every backtick-quoted, dot-separated token whose first segment names a
    real top-level block of `crew_config.default_config()` or
    `default_global_config()` must resolve to an actual leaf (or a real
    intermediate node) in one of those two structures.
  * Every backtick-quoted `.py`/`.sh`/`.ps1` name -- bare, or a full
    repo-relative path -- must exist on disk, either directly under
    `plugin/crew/hooks/scripts/` (every hook wrapper this guide tables lives
    there) or at the repo-relative path given.

This is deliberately light, per its own scope: it cannot catch a key the
guide never mentions, and it skips any dotted token whose root is not one of
crew's own config sections (a made-up example like `foo.bar` in prose would
not be flagged). What it catches is the drift that actually happens --
`crew_config.py` renaming a leaf, or a hook script moving -- without the
guide's own prose saying so.
"""
import os
import re

import context  # noqa: F401  pylint: disable=unused-import
import crew_config

_GUIDE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "..", "..", "docs", "guides", "crew", "src", "troubleshooting.md")
_GUIDE = os.path.normpath(_GUIDE)

_SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir,
    "hooks", "scripts")

# Extensions that end a backtick token but are never a config key's last
# segment -- so `hooks.json`, `CLAUDE.md`, `notify.sh`, `plan.md`, `spec.md`
# and `TODO.md` are excluded before anything is checked against config.
_NOT_CONFIG_EXTENSIONS = frozenset(
    ("md", "json", "sh", "py", "ps1", "log", "txt", "html", "yml", "yaml"))

_DOTTED_TOKEN_RE = re.compile(
    r"`([A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9]*)+)`")

_SCRIPT_TOKEN_RE = re.compile(
    r"`([A-Za-z0-9_./-]+\.(?:sh|py|ps1))`")


def _guide_text():
    if not os.path.isfile(_GUIDE):
        return None
    with open(_GUIDE, encoding="utf-8") as handle:
        return handle.read()


def _requires_guide():
    text = _guide_text()
    if text is None:
        import pytest
        pytest.skip(f"troubleshooting.md not found at {_GUIDE} -- crew's "
                    "tests are running outside the marketplace repo")
    return text


def _config_leaves_and_roots():
    merged_leaves = set()
    roots = set()
    for builder in (crew_config.default_config, crew_config.default_global_config):
        cfg = builder()
        roots.update(cfg.keys())
        merged_leaves.update(crew_config.leaf_paths(cfg))
    return merged_leaves, roots


def _dotted_candidates(text):
    """Every backtick dotted token whose root is a real config section and
    whose last segment is not a file extension -- the two together are what
    separate `guards.cloudGuard` from `hooks.json` and `pm_pulse.py:247`."""
    _leaves, roots = _config_leaves_and_roots()
    out = []
    for token in _DOTTED_TOKEN_RE.findall(text):
        segments = token.split(".")
        if segments[0] not in roots:
            continue
        if segments[-1].lower() in _NOT_CONFIG_EXTENSIONS:
            continue
        out.append(token)
    return sorted(set(out))


def test_every_config_key_the_guide_names_exists():
    text = _requires_guide()
    leaves, _roots = _config_leaves_and_roots()
    candidates = _dotted_candidates(text)
    assert candidates, "no candidate config keys found -- the extraction " \
        "regex or the guide's own wording changed; this test would be " \
        "vacuous"

    prefixes = {".".join(leaf.split(".")[:i])
                for leaf in leaves
                for i in range(1, len(leaf.split(".")))}

    missing = [c for c in candidates if c not in leaves and c not in prefixes]
    assert not missing, (
        "troubleshooting.md names config key(s) that do not exist in "
        f"crew_config.default_config()/default_global_config(): {missing}")


def test_every_script_the_guide_names_exists():
    text = _requires_guide()
    tokens = sorted(set(_SCRIPT_TOKEN_RE.findall(text)))
    assert tokens, "no script names found in the guide -- the extraction " \
        "regex or the guide's own wording changed; this test would be " \
        "vacuous"

    repo_root = os.path.normpath(os.path.join(_SCRIPTS_DIR, "..", "..", "..", ".."))

    missing = []
    for token in tokens:
        if "/" in token:
            candidate = os.path.join(repo_root, token)
        else:
            candidate = os.path.join(_SCRIPTS_DIR, token)
        if not os.path.isfile(candidate):
            missing.append(token)

    assert not missing, (
        "troubleshooting.md names script(s) that do not exist on disk: "
        f"{missing}")
