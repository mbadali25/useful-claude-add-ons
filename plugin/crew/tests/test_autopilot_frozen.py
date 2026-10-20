"""The 17 `crew_autopilot*.py` modules are frozen (L-0727 A3): lane fan-out now lives in
`plugin/crew/workflows/`, so these modules take no new behaviour.

`autopilot_frozen.json` holds each file's sha256 and line count at the freeze. This test fails on
an added, missing, renamed or changed file and on a total line count above the freeze."""
import hashlib
import json
import os

import context  # noqa: F401  pylint: disable=unused-import

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "hooks", "scripts")
MANIFEST = os.path.join(HERE, "autopilot_frozen.json")

NEXT_STEP = (
    "crew_autopilot*.py is frozen (L-0727): new lane or wave behaviour goes in "
    "plugin/crew/workflows/. Only a bug fix or a removal may change one of these files, and then "
    "the same PR updates tests/autopilot_frozen.json (python3 tests/test_autopilot_frozen.py "
    "--write) and its body says why and names L-0727.")


def _measure():
    found = {}
    for name in sorted(os.listdir(SCRIPTS)):
        if not (name.startswith("crew_autopilot") and name.endswith(".py")):
            continue
        with open(os.path.join(SCRIPTS, name), "rb") as handle:
            data = handle.read().replace(b"\r\n", b"\n")
        found[name] = {"sha256": hashlib.sha256(data).hexdigest(), "lines": data.count(b"\n")}
    return found


def _manifest():
    with open(MANIFEST, encoding="utf-8") as handle:
        return json.load(handle)


def test_the_manifest_names_seventeen_modules():
    assert len(_manifest()["files"]) == 17


def test_no_autopilot_module_is_added_or_missing():
    frozen, now = set(_manifest()["files"]), set(_measure())

    assert (sorted(now - frozen), sorted(frozen - now)) == ([], []), NEXT_STEP


def test_no_autopilot_module_has_changed():
    frozen, now = _manifest()["files"], _measure()

    changed = sorted(name for name in frozen if name in now and frozen[name] != now[name])

    assert changed == [], NEXT_STEP


def test_the_total_line_count_is_not_above_the_freeze():
    now = sum(entry["lines"] for entry in _measure().values())

    assert now <= _manifest()["totalLines"], NEXT_STEP


def test_the_manifest_total_is_the_sum_of_its_files():
    manifest = _manifest()

    assert manifest["totalLines"] == sum(e["lines"] for e in manifest["files"].values())


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["--write"]:
        files = _measure()
        text = json.dumps({"note": NEXT_STEP, "files": files,
                           "totalLines": sum(e["lines"] for e in files.values())}, indent=2) + "\n"
        with open(MANIFEST, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
    else:
        sys.exit("usage: test_autopilot_frozen.py --write")
