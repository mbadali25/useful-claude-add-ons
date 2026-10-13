"""README_DE.md keeps up with README.md: same section outline, every server limit documented."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EN = ROOT / "README.md"
DE = ROOT / "README_DE.md"


def _outline(path: Path) -> list[int]:
    """The heading levels in order, outside fenced code blocks."""
    levels, fenced = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and (match := re.match(r"(#+) ", line)):
            levels.append(len(match.group(1)))
    return levels


def test_german_readme_has_the_same_section_outline():
    assert _outline(DE) == _outline(EN)


def test_every_server_key_in_the_example_is_documented_in_both_readmes():
    example = yaml.safe_load((ROOT / "config.yaml.example").read_text(encoding="utf-8"))
    for key in example["server"]:
        for readme in (EN, DE):
            assert f"server.{key}" in readme.read_text(encoding="utf-8"), f"server.{key} missing from {readme.name}"
