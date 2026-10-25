"""L-0724: the opt-in inventory is generated, complete, and holds every anchor in place.

`data/optin_inventory.json` is written by `optin_inventory.py --write`. The sabotage
mutations anchor on exact text in files L-0724 moves; a slice that edits an anchored
line, or moves a target to a path the harness cannot resolve, turns a mutation into one
that tests nothing. These tests hold each slice to the inventory.
"""
import json
import os
from pathlib import Path

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import optin_inventory
import sabotage
import sabotage_autopilot

INVENTORY = json.loads(Path(optin_inventory.DATA).read_text(encoding="utf-8"))
ANCHORS = INVENTORY["sabotage"]["anchors"]


def _resolve(layouts):
    for rel in layouts:
        path = os.path.join(optin_inventory.ROOT, *rel.split("/"))
        if os.path.isfile(path):
            return path
    raise AssertionError("no layout exists: " + ", ".join(layouts))


def test_inventory_has_no_blank_kind_and_no_empty_section():
    assert INVENTORY["refs"] and INVENTORY["shim_targets"] and ANCHORS
    blank = [r for r in INVENTORY["refs"] if r.get("kind") not in ("exec", "alias", "read", "local")]
    assert not blank, blank


def test_inventory_matches_what_the_tree_generates():
    """Stale when a mutation, anchor or moved-Markdown reference changed without a regenerate."""
    on_disk = Path(optin_inventory.DATA).read_bytes().decode("utf-8")

    assert optin_inventory.render(optin_inventory.build()) == on_disk, (
        "run: python3 plugin/crew/tests/optin_inventory.py --write")


def test_sabotage_anchors_survive_slices():
    """Each anchor is found in its target, in whichever layout exists, exactly as often as at the base."""
    lost = []
    for row in ANCHORS:
        text = Path(_resolve(row["layouts"])).read_text(encoding="utf-8", errors="replace")
        hits = text.count(row["find"])
        if hits != row["count"] or hits != 1:
            lost.append(f"{hits} hit(s), want {row['count']}: {row['layouts'][0]} -- {row['label']}")
    assert not lost, "\n".join(lost)


def test_every_moved_sabotage_target_resolves_through_the_harness():
    """The module constants resolve to a file in the layout the tree is in, never to a missing path."""
    moved = {os.path.abspath(path) for path in (
        sabotage.PROMOTE_DOC, sabotage.GATE_DOC, sabotage.HOUSE_STYLE, sabotage_autopilot.COMMAND)}
    for path in moved:
        assert os.path.isfile(path), path
    targets = {os.path.abspath(m[1]) for m in sabotage.MUTATIONS}
    for row in ANCHORS:
        if row["layouts"][0].startswith("plugin/crew-") or row["layouts"][0].startswith("plugin/crew/"):
            assert os.path.abspath(_resolve(row["layouts"])) in targets, row["layouts"]


def test_every_mutation_on_a_moved_file_is_in_the_inventory():
    """A new mutation on a file L-0724 moves must be recorded, or no slice knows to keep its anchor."""
    recorded = {(r["layouts"][0], r["find"]) for r in ANCHORS}
    missing = []
    for mutation in sabotage.MUTATIONS:
        layouts = optin_inventory.moved_layouts(mutation[1])
        if layouts and (layouts[0], mutation[2]) not in recorded:
            missing.append((layouts[0], mutation[0]))
    assert not missing, missing


@pytest.mark.parametrize("module, table", [
    ("sabotage_wave", "WAVE_MUTATIONS"), ("sabotage_coord", "COORD_MUTATIONS"),
    ("sabotage_bridge", "BRIDGE_MUTATIONS"), ("sabotage_tracker", "TRACKER_MUTATIONS")])
def test_named_suites_target_files_that_stay_in_core(module, table):
    """The four suites the plan review named target core files only; none moves, none needs a layout."""
    rows = getattr(__import__(module), table)
    assert rows, module
    moving = [m[0] for m in rows if optin_inventory.moved_layouts(m[1])]
    assert not moving, moving


@pytest.mark.parametrize("home", ["crew-autopilot", "crew"])
def test_refs_and_layouts_follow_a_moved_file_to_its_opt_in(tmp_path, monkeypatch, home):
    """After a slice moves a file the generator still sees it, in the opt-in or in core."""
    command = tmp_path / "plugin" / home / "commands" / "autopilot.md"
    command.parent.mkdir(parents=True)
    command.write_text("1. `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_autopilot.py status`\n",
                       encoding="utf-8")
    monkeypatch.setattr(optin_inventory, "ROOT", str(tmp_path))
    monkeypatch.setattr(optin_inventory, "CREW", str(tmp_path / "plugin" / "crew"))

    refs = [r for r in optin_inventory.refs_section() if r["file"] == "commands/autopilot.md"]

    assert [(r["kind"], r["in"], r["target"]) for r in refs] == [
        ("exec", "core", "hooks/scripts/crew_autopilot.py")]
    assert optin_inventory.moved_layouts(str(command)) == [
        "plugin/crew-autopilot/commands/autopilot.md", "plugin/crew/commands/autopilot.md"]


def test_a_non_utf8_byte_in_a_moved_file_fails_the_generator(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"ok \xff not utf-8\n")

    with pytest.raises(UnicodeDecodeError):
        optin_inventory._read(str(bad))  # pylint: disable=protected-access
