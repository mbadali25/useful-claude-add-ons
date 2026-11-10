"""L-0726 slice 2 / AC8: `.crew/verify.json` gave every rule an `id` and moved the long `why` prose
into docs/crew/verify-rationale.md, one `## <id>` section per rule. Nothing may be lost or re-keyed.

The comparison is against the pre-migration map, read with `git show <merge-base with origin/main>`.
Once main carries the ids that base has none left to migrate, and the comparison tests skip with
that reason rather than fail every later edit to a rule."""
import json
import os
import re
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import verify_reach
import verify_record

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir))
MAP = os.path.join(REPO, ".crew", "verify.json")
DOC = os.path.join(REPO, "docs", "crew", "verify-rationale.md")
SECTION = re.compile(r"^## (\S+)\n\n(.*?)(?=\n\n## |\Z)", re.DOTALL | re.MULTILINE)


def _git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _rules():
    return json.loads(_read(MAP))["rules"]


def _sections():
    return {m.group(1): m.group(2).rstrip("\n") for m in SECTION.finditer(_read(DOC))}


def _base_rules():
    """The rules as the merge-base with origin/main has them, or a skip saying why not."""
    for ref in ("origin/main", "main"):
        base = _git("merge-base", "HEAD", ref)
        if base.returncode == 0 and base.stdout.strip():
            break
    else:
        pytest.skip("no origin/main or main to take a merge-base from, so there is no base to compare")
    shown = _git("show", f"{base.stdout.strip()}:.crew/verify.json")
    if shown.returncode != 0:
        pytest.skip(f"git show of the base verify.json failed: {shown.stderr.strip()}")
    rules = json.loads(shown.stdout)["rules"]
    if all("id" in r and "why" in r and len(r["why"]) <= 300 for r in rules):
        pytest.skip("the base already carries the migrated map; nothing is left to compare")
    return rules


def test_rule_keys_unchanged():
    base, now = _base_rules(), _rules()

    assert [verify_record.rule_key(r) for r in now] == [verify_record.rule_key(r) for r in base]


def test_covered_by_map_unchanged():
    base, now = _base_rules(), _rules()

    assert verify_record.cover_declarations(now) == verify_record.cover_declarations(base)


def test_only_id_and_why_differ_from_the_base():
    base, now = _base_rules(), _rules()
    stripped = [{k: v for k, v in r.items() if k not in ("id", "why")} for r in now]
    expected = [{k: v for k, v in r.items() if k not in ("id", "why")} for r in base]

    assert (stripped, [list(r) for r in stripped]) == (expected, [list(r) for r in expected])


def test_rationale_doc_matches_ids():
    ids = [r.get("id") for r in _rules()]
    headings = re.findall(r"^## (\S+)\s*$", _read(DOC), re.MULTILINE)

    assert (all(isinstance(i, str) and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", i) for i in ids),
            len(set(ids)) == len(ids), headings) == (True, True, ids)


def test_old_why_text_is_the_doc_section_for_every_rule():
    base, now, sections = _base_rules(), _rules(), _sections()
    lost = [r["id"] for r, old in zip(now, base) if sections.get(r["id"]) != old["why"]]

    assert (len(now), lost) == (len(base), [])


def test_stamp_reach_keeps_ids_and_key_order(tmp_path):
    data = json.loads(_read(MAP))
    for rule in data["rules"][:2]:
        rule.pop("reach", None)
    root = tmp_path / "repo"
    (root / ".crew").mkdir(parents=True)
    with open(root / ".crew" / "verify.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=2) + "\n")

    code = verify_reach.main(["--root", str(root), "--apply", "--set", "0=local", "--set", "1=local"])
    after = json.loads(_read(str(root / ".crew" / "verify.json")))["rules"]

    assert (code, [r.get("id") for r in after], [[k for k in r if k != "reach"] for r in after]) == (
        0, [r.get("id") for r in data["rules"]], [[k for k in r if k != "reach"] for r in data["rules"]])
