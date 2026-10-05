"""crew_standards.py: the set-file format, the effective set, the self-check
record and its stamp, the findings-to-standards proposals and the before/after
metric (T-0085).

Every fixture lives under pytest's tmp_path: a throwaway references directory
stands in for the plugin's `skills/crew-standards/references/`, and a
throwaway repository for the one being reviewed. The only real files read are
the shipped `references/generic.md` and this repository's `.crew/standards.md`
overlay, and only by the tests that name them.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_standards as cs
from review_fixtures import git, init_repo

_SCRIPT = os.path.join(context._ROOT, "hooks", "scripts",  # pylint: disable=protected-access
                       "crew_standards.py")
_REPO_ROOT = os.path.abspath(os.path.join(context._ROOT, os.pardir, os.pardir))  # pylint: disable=protected-access
_REFS = os.path.join(context._ROOT, "skills", "crew-standards", "references")  # pylint: disable=protected-access


def _standard(sid, name, plugin=True):
    fields = ["**Rule.** Do the thing.", "**Self-check.**\n1. Did you? Pass: yes."]
    if plugin:
        fields = ["**Rule.** Do the thing.", "**Why.** It broke.",
                  "**Applies when.** Always.", "**Self-check.**\n1. Did you? Pass: yes.",
                  "**Earned by.**\n- T-0001 r1 @abcdef12, FIX `a.py:1`: \"broke\"",
                  "**Change sets.** 3: T-0001, T-0002, T-0003"]
    return f"## {sid} {name}\n\n" + "\n\n".join(fields) + "\n"


def _set_file(set_name, applies, body):
    return f"---\nset: {set_name}\napplies-to: {json.dumps(applies)}\n---\n\n# {set_name}\n\n{body}"


@pytest.fixture(name="refs")
def _refs(tmp_path):
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "generic.md").write_text(
        _set_file("GEN", ["**"], _standard("GEN-01", "One") + "\n" + _standard("GEN-02", "Two")),
        encoding="utf-8")
    (refs / "php.md").write_text(
        _set_file("PHP", ["**/*.php"], _standard("PHP-01", "Prepared statements")),
        encoding="utf-8")
    return refs


OVERLAY = _set_file("REPO", ["**"], _standard("REPO-01", "Local", plugin=False)
                    + "\n## Supplements GEN-01\n\nRun `grep -rn x plugin/`.\n")


@pytest.fixture(name="root")
def _root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    return root


def _write_overlay(root, text=OVERLAY, raw=None):
    (root / ".crew").mkdir(exist_ok=True)
    path = root / ".crew" / "standards.md"
    if raw is not None:
        path.write_bytes(raw)
    else:
        path.write_text(text, encoding="utf-8")
    return path


# ---- Step 1: the set-file format and the effective set -----------------------

def test_effective_set_is_generic_plus_matching_stacks_plus_overlay(refs, root):
    _write_overlay(root)

    both = cs.effective_set(str(root), ["a/b.php", "x.py"], refs_dir=str(refs))
    python_only = cs.effective_set(str(root), ["x.py"], refs_dir=str(refs))

    assert ([s["id"] for s in both["standards"]], [s["id"] for s in python_only["standards"]],
            both["problems"], both["overlay"]) == (
        ["GEN-01", "GEN-02", "PHP-01", "REPO-01"], ["GEN-01", "GEN-02", "REPO-01"], [],
        "present")


def test_overlay_supplements_attach_to_their_plugin_standard(refs, root):
    _write_overlay(root)

    found = cs.effective_set(str(root), ["x.py"], refs_dir=str(refs))

    gen01 = next(s for s in found["standards"] if s["id"] == "GEN-01")
    assert gen01["supplements"] == ["Run `grep -rn x plugin/`."]


def test_missing_overlay_reads_generic_only_and_says_so(refs, root):
    found = cs.effective_set(str(root), ["x.py"], refs_dir=str(refs))

    assert ([s["id"] for s in found["standards"]], found["overlay"], found["problems"]) == (
        ["GEN-01", "GEN-02"], "absent", [])
    assert "overlay: none (.crew/standards.md absent)" in cs.summary_line(found)


_BAD_OVERLAYS = {
    "no-front-matter": ("## REPO-01 Local\n\n**Rule.** x\n\n**Self-check.** y\n",
                        "no front matter"),
    "wrong-prefix": (OVERLAY.replace("set: REPO", "set: GEN"), "the overlay's set is REPO"),
    "duplicate-id": (OVERLAY + "\n" + _standard("REPO-01", "Again", plugin=False),
                     "REPO-01 is defined twice"),
    "supplements-unknown-id": (OVERLAY + "\n## Supplements GEN-99\n\ntext\n",
                               "Supplements GEN-99 names no plugin standard"),
    "id-prefix-mismatch": (OVERLAY + "\n" + _standard("XYZ-01", "Other", plugin=False),
                           "XYZ-01 does not carry this file's set prefix REPO"),
    "unknown-heading": (OVERLAY + "\n## Notes\n\nprose\n", "is neither"),
    "applies-to-not-json": (OVERLAY.replace('["**"]', "**"),
                            "applies-to is not a JSON list"),
    "missing-self-check": (_set_file("REPO", ["**"], "## REPO-01 Local\n\n**Rule.** x\n"),
                           "REPO-01 has no **Self-check.** field"),
}
_BAD_OVERLAY_CAUSES = {"not-utf8": "not UTF-8", "unreadable": "cannot be read"}


@pytest.mark.parametrize("shape", sorted(_BAD_OVERLAYS) + sorted(_BAD_OVERLAY_CAUSES))
def test_bad_overlay_refuses(refs, root, shape):
    if shape == "unreadable":
        if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
            pytest.skip("chmod 000 does not stop reads on Windows or as root, so an "
                        "unreadable overlay cannot be produced this way here")
        os.chmod(_write_overlay(root), 0)
    elif shape == "not-utf8":
        _write_overlay(root, raw=b"---\nset: REPO\napplies-to: [\"**\"]\n---\n\xff\xfe\n")
    else:
        _write_overlay(root, _BAD_OVERLAYS[shape][0])
    cause = _BAD_OVERLAYS[shape][1] if shape in _BAD_OVERLAYS else _BAD_OVERLAY_CAUSES[shape]

    found = cs.effective_set(str(root), ["x.py"], refs_dir=str(refs))

    assert (found["overlay"], any(cause in p for p in found["overlay_problems"])) == (
        "unknown", True), found["problems"]


def _refs_with_a_repo_set(refs):
    (refs / "repo.md").write_text(_set_file("REPO", ["**"], _standard("REPO-01", "Plugin")),
                                  encoding="utf-8")


def test_overlay_may_not_reuse_a_plugin_id(refs, root):
    _refs_with_a_repo_set(refs)
    _write_overlay(root)

    found = cs.effective_set(str(root), ["x.py"], refs_dir=str(refs))

    assert (found["overlay"], any("REPO-01 reuses a plugin id" in p
                                  for p in found["overlay_problems"])) == ("unknown", True), (
        found["problems"])


def test_plugin_set_may_not_claim_the_overlay_set(refs, root):
    _refs_with_a_repo_set(refs)

    found = cs.effective_set(str(root), ["x.py"], refs_dir=str(refs))

    assert any("references/repo.md" in p and "overlay's set" in p for p in found["problems"]), (
        found["problems"])


def test_overlay_that_is_a_directory_is_unknown_not_absent(refs, root):
    (root / ".crew" / "standards.md").mkdir(parents=True)

    found = cs.effective_set(str(root), ["x.py"], refs_dir=str(refs))

    assert found["overlay"] == "unknown" and found["problems"]


@pytest.mark.parametrize("field", ["Change sets", "Self-check", "Rule", "Why", "Applies when",
                                   "Earned by"])
def test_set_file_needs_every_field(refs, root, field):
    text = (refs / "generic.md").read_text(encoding="utf-8")
    first, rest = text.split("## GEN-02", 1)
    first = re.sub(r"\*\*" + re.escape(field) + r"\.\*\*[^\n]*\n(?:(?!\n\*\*)[^\n]*\n)*", "",
                   first, count=1)
    (refs / "generic.md").write_text(first + "## GEN-02" + rest, encoding="utf-8")

    found = cs.effective_set(str(root), ["x.py"], refs_dir=str(refs))

    assert any("GEN-01" in p and field in p for p in found["problems"]), found["problems"]


def test_overlay_needs_only_rule_and_self_check(refs, root):
    _write_overlay(root)

    found = cs.effective_set(str(root), ["x.py"], refs_dir=str(refs))

    assert found["problems"] == []


def test_digest_changes_with_the_overlay_and_with_a_matching_stack(refs, root):
    plain = cs.effective_set(str(root), ["x.py"], refs_dir=str(refs))["digest"]
    with_php = cs.effective_set(str(root), ["x.php"], refs_dir=str(refs))["digest"]
    _write_overlay(root)
    with_overlay = cs.effective_set(str(root), ["x.py"], refs_dir=str(refs))["digest"]

    assert len({plain, with_php, with_overlay}) == 3


# ---- Step 2: the shipped generic set and this repository's overlay ---------------

def test_generic_set_parses_with_every_field():
    parsed, problems, _ = cs.parse_set(os.path.join(_REFS, "generic.md"))

    assert (problems, [s["id"] for s in parsed["standards"]]) == (
        [], [f"GEN-{n:02d}" for n in range(1, 13)])


def test_every_generic_standard_names_three_change_sets():
    parsed, _, _ = cs.parse_set(os.path.join(_REFS, "generic.md"))

    for std in parsed["standards"]:
        line = std["fields"]["Change sets"]
        count, _, names = line.partition(":")
        listed = [n.strip() for n in names.split(",") if n.strip()]
        assert (int(count) >= 3, len(listed) == int(count), len(set(listed)) == len(listed)) == (
            True, True, True), (std["id"], line)


def test_every_generic_standard_cites_three_of_its_change_sets():
    """The admission rule's evidence is visible in the shipped file: at least
    three of the change sets a standard names are each cited in its Earned
    by, so a count of names alone cannot admit it (review round 3)."""
    parsed, _, _ = cs.parse_set(os.path.join(_REFS, "generic.md"))

    short = {}
    for std in parsed["standards"]:
        names = [n.strip() for n in std["fields"]["Change sets"].partition(":")[2].split(",")]
        cited = [n for n in names if f"- {n} r" in std["fields"]["Earned by"]]
        if len(cited) < 3:
            short[std["id"]] = cited

    assert short == {}


def test_shipped_sets_cite_nothing_local_only():
    offenders = []
    for name in sorted(os.listdir(_REFS)):
        with open(os.path.join(_REFS, name), encoding="utf-8") as fh:
            for number, line in enumerate(fh, 1):
                if re.search(r"\.work/|\bF\d{3}\b", line):
                    offenders.append(f"{name}:{number}: {line.strip()[:80]}")

    assert offenders == []


# ---- T-0086: the per-language stack sets -------------------------------------------

_ADMITTED_PYTHON = [f"PYTHON-{n:02d}" for n in (1, 3, 4, 6, 7, 8, 10, 11, 13)]
_STACK_SETS = sorted(n for n in os.listdir(_REFS) if n.endswith(".md") and n != "generic.md")


def test_python_set_parses_with_every_field():
    parsed, problems, _ = cs.parse_set(os.path.join(_REFS, "python.md"))

    assert parsed is not None, problems
    assert (problems, parsed["set"], parsed["applies_to"],
            [s["id"] for s in parsed["standards"]]) == (
        [], "PYTHON", ["**/*.py"], _ADMITTED_PYTHON)


def _change_set_problems(std):
    count, _, names = std["fields"]["Change sets"].partition(":")
    listed = [n.strip() for n in names.split(",") if n.strip()]
    earned = std["fields"]["Earned by"].splitlines()
    cited = [n for n in listed
             if any(line.startswith(f"- {n} ") or f"`{n}`" in line for line in earned)]
    problems = []
    if not count.strip().isdigit() or int(count) < 3:
        problems.append(f"count {count.strip()!r} is not a number of at least 3")
    elif len(listed) != int(count):
        problems.append(f"count {count.strip()} but {len(listed)} names")
    if len(set(listed)) != len(listed):
        problems.append("a name is repeated")
    if len(cited) < 3:
        problems.append(f"only {cited} cited in Earned by")
    return problems


@pytest.mark.parametrize("name", _STACK_SETS)
def test_every_stack_standard_names_and_cites_three_change_sets(name):
    """A stack set ships only standards earned by at least three distinct
    reviewed change sets (crew-standards/SKILL.md), each visible in Earned by."""
    parsed, problems, _ = cs.parse_set(os.path.join(_REFS, name))
    assert parsed is not None, problems

    short = {std["id"]: _change_set_problems(std) for std in parsed["standards"]}

    assert {sid: found for sid, found in short.items() if found} == {}


_WHY_COUNT_RE = re.compile(r"\b(\d+) findings? across (\d+) change\s+sets\b")


@pytest.mark.parametrize("name", _STACK_SETS)
def test_every_stack_standard_why_states_its_change_set_count(name):
    """A Why's "N findings across M change sets" names the same M as its
    Change sets line, and N is at least M: one finding per change set is the floor."""
    parsed, problems, _ = cs.parse_set(os.path.join(_REFS, name))
    assert parsed is not None, problems

    wrong = {}
    for std in parsed["standards"]:
        claim = _WHY_COUNT_RE.search(std["fields"]["Why"])
        listed = std["fields"]["Change sets"].partition(":")[0].strip()
        if claim is None:
            wrong[std["id"]] = "Why states no 'N findings across M change sets'"
        elif claim.group(2) != listed or int(claim.group(1)) < int(claim.group(2)):
            wrong[std["id"]] = f"Why {claim.group(0)!r}, Change sets {listed}"

    assert wrong == {}


# Each count below was taken by hand from the defects the standard's own Why
# enumerates, and each enumerated defect was matched to a quoted finding in its
# Earned by (review round 1, FIX python.md:245: PYTHON-07 said 6 and listed 7).
# A new or edited standard updates this table with a fresh count, never a copy
# of the number the Why already states.
_PYTHON_FINDINGS = {
    "PYTHON-01": 3, "PYTHON-03": 3, "PYTHON-04": 4, "PYTHON-06": 3, "PYTHON-07": 7,
    "PYTHON-08": 6, "PYTHON-10": 4, "PYTHON-11": 5, "PYTHON-13": 5,
}


def test_python_why_finding_counts_match_their_enumerations():
    parsed, problems, _ = cs.parse_set(os.path.join(_REFS, "python.md"))
    assert parsed is not None, problems

    stated = {}
    for std in parsed["standards"]:
        claim = _WHY_COUNT_RE.search(std["fields"]["Why"])
        stated[std["id"]] = int(claim.group(1)) if claim else None

    assert stated == _PYTHON_FINDINGS


@pytest.mark.parametrize("name", _STACK_SETS)
def test_every_stack_set_line_count_is_the_same_by_newline_and_splitlines(name):
    """A raw U+2028/U+2029 (or \\v, \\f, \\x1c-\\x1e, \\x85) is a line to
    splitlines() and not to wc -l, so BUDGETS.md's Markdown total would depend
    on which counter read it (review round 2, FIX BUDGETS.md:11)."""
    with open(os.path.join(_REFS, name), encoding="utf-8", newline="") as fh:
        text = fh.read()

    assert len(text.splitlines()) == text.count("\n")


def test_python_sources_quote_whole_spans_without_elision():
    """Every Source quote is checked verbatim against the raw page, so none may
    be cut with [...]: an elided span is not in the page (review round 2, FIX
    python.md:79)."""
    parsed, problems, _ = cs.parse_set(os.path.join(_REFS, "python.md"))
    assert parsed is not None, problems

    elided = [std["id"] for std in parsed["standards"]
              if re.search(r"\[(\.\.\.|…)\]", std["fields"]["Source"])]

    assert elided == []


def test_python_set_applies_to_python_files_only():
    def applies(files):
        return "PYTHON" in cs.effective_set(_REPO_ROOT, files)["sets"]

    assert (applies(["plugin/crew/hooks/scripts/x.py"]), applies(["setup.py"]),
            applies(["README.md"]), applies(["plugin/crew/x.pyc"])) == (
        True, True, False, False)


def test_shipped_sets_cite_no_machine_local_note():
    offenders = []
    for name in sorted(os.listdir(_REFS)):
        with open(os.path.join(_REFS, name), encoding="utf-8") as fh:
            for number, line in enumerate(fh, 1):
                if re.search(r"/repos/|claude-memories|wiki/concepts|/\.claude/projects/|auto-memory",
                             line):
                    offenders.append(f"{name}:{number}: {line.strip()[:80]}")

    assert offenders == []


# The owner accepted three amendments from review round 1's proposals
# (.work/tickets/T-0085/standards-proposals-r1.md, "Owner decision", 2026-09-28):
# #2 and #3 into GEN-01, #4 into REPO-03, #6 into GEN-04.
_ROUND_1_AMENDMENTS = [
    ("generic.md", "GEN-01", "Rule", "leaf is missing (ENOENT) and its parent is readable"),
    ("generic.md", "GEN-01", "Rule", "emits the safe superset it announces"),
    ("generic.md", "GEN-01", "Self-check", "a parent that is not a directory"),
    ("generic.md", "GEN-01", "Rule", "a test compares the message against what was emitted"),
    ("generic.md", "GEN-04", "Rule", "by label, not by count"),
    ("generic.md", "GEN-04", "Rule", "replaced with `pass`"),
    ("overlay", "REPO-03", "Rule", "the build branch carries none"),
    ("overlay", "REPO-03", "Rule", "has changed since version"),
    ("overlay", "REPO-03", "Rule", "not a finding"),
]


def _shipped_standard(where, sid):
    if where == "overlay":
        path, required = os.path.join(_REPO_ROOT, cs.OVERLAY_REL), cs.OVERLAY_FIELDS
    else:
        path, required = os.path.join(_REFS, where), cs.PLUGIN_FIELDS
    parsed, _, _ = cs.parse_set(path, required=required)
    return next(s for s in parsed["standards"] if s["id"] == sid)


@pytest.mark.parametrize("where, sid, field, phrase", _ROUND_1_AMENDMENTS,
                         ids=[f"{a[1]}-{a[3][:24]}" for a in _ROUND_1_AMENDMENTS])
def test_owner_accepted_amendment_is_in_its_standard(where, sid, field, phrase):
    text = " ".join(_shipped_standard(where, sid)["fields"][field].split())

    assert phrase in text


def test_repo_03_no_longer_asks_for_a_build_branch_bump():
    rule = _shipped_standard("overlay", "REPO-03")["fields"]["Rule"]

    assert "provisional" not in rule.lower()


def test_overlay_file_parses():
    found = cs.effective_set(_REPO_ROOT, ["plugin/crew/x.py"])

    overlay = [s["id"] for s in found["standards"] if s["source"] == cs.OVERLAY_REL]
    supplemented = [s["id"] for s in found["standards"] if s["supplements"]]
    assert (found["problems"], found["overlay"], overlay, supplemented) == (
        [], "present", ["REPO-01", "REPO-02", "REPO-03"],
        ["GEN-08", "GEN-09", "GEN-11", "GEN-12"])


# ---- Step 3: the self-check record and its stamp ----------------------------------

def _scoped_repo(tmp_path, ticket="T-1"):
    """A throwaway repo whose scope base for `ticket` is its first commit,
    with one committed, one staged, one unstaged and one untracked change."""
    import scope_base  # pylint: disable=import-outside-toplevel
    repo = init_repo(tmp_path / "repo")
    scope_base.record(str(repo), ticket)
    (repo / "committed.txt").write_text("c\n", encoding="utf-8")
    git(repo, "add", "committed.txt")
    git(repo, "commit", "-qm", "c")
    (repo / "staged.txt").write_text("s\n", encoding="utf-8")
    git(repo, "add", "staged.txt")
    (repo / "seed.txt").write_text("changed\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("u\n", encoding="utf-8")
    return repo


def _answer_all(repo, ticket="T-1"):
    path = repo / ".work" / "tickets" / ticket / "selfcheck.md"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^\| ([A-Z]+-\d\d) \|  \|  \|$",
                  r"| \1 | n/a | nothing in this change reads or writes that class |",
                  text, flags=re.M)
    path.write_text(text, encoding="utf-8")
    return path


def _cli(*args, cwd=None):
    return subprocess.run([sys.executable, _SCRIPT] + list(args), capture_output=True,
                          text=True, stdin=subprocess.DEVNULL, check=False, cwd=cwd)


def test_init_writes_a_row_per_standard_and_never_overwrites(tmp_path, refs):
    repo = _scoped_repo(tmp_path)

    first = cs.init(str(repo), "T-1", refs_dir=str(refs))
    path = repo / ".work" / "tickets" / "T-1" / "selfcheck.md"
    before = path.read_bytes()
    second = cs.init(str(repo), "T-1", refs_dir=str(refs))

    rows = re.findall(r"^\| ([A-Z]+-\d\d) \|  \|  \|$", before.decode(), flags=re.M)
    assert (first[0], second[0], rows, path.read_bytes() == before,
            before.decode().startswith("# T-1 self-check\n")) == (
        0, 1, ["GEN-01", "GEN-02"], True, True)


_INCOMPLETE = {
    "missing-row": lambda t: re.sub(r"^\| GEN-02 .*\n", "", t, flags=re.M),
    "unknown-status": lambda t: t.replace("| GEN-01 | n/a |", "| GEN-01 | maybe |"),
    "no-status": lambda t: re.sub(r"^\| GEN-01 \| n/a \|", "| GEN-01 |  |", t, flags=re.M),
    "na-without-reason": lambda t: re.sub(r"^\| GEN-01 \| n/a \| .*\|$", "| GEN-01 | n/a |  |",
                                          t, flags=re.M),
    "addressed-without-evidence": lambda t: re.sub(
        r"^\| GEN-01 \| n/a \| .*\|$", "| GEN-01 | addressed |  |", t, flags=re.M),
    "placeholder-tbd": lambda t: re.sub(r"^\| GEN-01 \| n/a \| .*\|$",
                                        "| GEN-01 | addressed | TBD |", t, flags=re.M),
    "placeholder-dash": lambda t: re.sub(r"^\| GEN-01 \| n/a \| .*\|$",
                                         "| GEN-01 | addressed | - |", t, flags=re.M),
    "placeholder-angle": lambda t: re.sub(r"^\| GEN-01 \| n/a \| .*\|$",
                                          "| GEN-01 | addressed | <evidence> |", t, flags=re.M),
    "unknown-id": lambda t: t + "| GEN-99 | n/a | no such standard |\n",
    "duplicate-row": lambda t: t + "| GEN-01 | n/a | again |\n",
}


@pytest.mark.parametrize("shape", sorted(_INCOMPLETE) + ["no-file"])
def test_stamp_refuses_incomplete_record(tmp_path, refs, shape):
    repo = _scoped_repo(tmp_path)
    path = repo / ".work" / "tickets" / "T-1" / "selfcheck.md"
    if shape != "no-file":
        cs.init(str(repo), "T-1", refs_dir=str(refs))
        _answer_all(repo)
        path.write_text(_INCOMPLETE[shape](path.read_text(encoding="utf-8")), encoding="utf-8")
    before = path.read_bytes() if path.exists() else None

    code, lines = cs.stamp(str(repo), "T-1", refs_dir=str(refs))

    after = path.read_bytes() if path.exists() else None
    named = "GEN-" in " ".join(lines) or "no self-check" in " ".join(lines)
    assert (code, named, after == before) == (1, True, True), lines


def test_stamp_accepts_complete_record(tmp_path, refs):
    repo = _scoped_repo(tmp_path)
    cs.init(str(repo), "T-1", refs_dir=str(refs))
    _answer_all(repo)

    code, lines = cs.stamp(str(repo), "T-1", refs_dir=str(refs))

    text = (repo / ".work" / "tickets" / "T-1" / "selfcheck.md").read_text(encoding="utf-8")
    stamps = re.findall(r"^<!-- stamp: bundle=[0-9a-f]{64} standards=[0-9a-f]{64} "
                        r"base=[0-9a-f]{40} -->$", text, flags=re.M)
    assert (code, len(stamps), text.split("\n")[1] == stamps[0]) == (0, 1, True), lines


def test_restamp_replaces_the_stamp_rather_than_adding_one(tmp_path, refs):
    repo = _scoped_repo(tmp_path)
    cs.init(str(repo), "T-1", refs_dir=str(refs))
    _answer_all(repo)
    cs.stamp(str(repo), "T-1", refs_dir=str(refs))
    (repo / "untracked.txt").write_text("u2\n", encoding="utf-8")

    code, _ = cs.stamp(str(repo), "T-1", refs_dir=str(refs))

    text = (repo / ".work" / "tickets" / "T-1" / "selfcheck.md").read_text(encoding="utf-8")
    assert (code, text.count("<!-- stamp:")) == (0, 1)


def test_stamp_refuses_without_a_scope_base(tmp_path, refs):
    repo = init_repo(tmp_path / "repo")
    (repo / "x.txt").write_text("x\n", encoding="utf-8")
    ticket_dir = repo / ".work" / "tickets" / "T-1"
    ticket_dir.mkdir(parents=True)
    (ticket_dir / "selfcheck.md").write_text(
        "# T-1 self-check\n\n| ID | Status | Evidence or reason |\n|---|---|---|\n"
        "| GEN-01 | n/a | none of it |\n| GEN-02 | n/a | none of it |\n", encoding="utf-8")

    code, lines = cs.stamp(str(repo), "T-1", refs_dir=str(refs))

    assert code == 1 and any("no scope base recorded for T-1" in line for line in lines), lines


def test_stamp_binds_the_review_bundle(tmp_path, refs):
    import review_patch  # pylint: disable=import-outside-toplevel
    import scope_base  # pylint: disable=import-outside-toplevel
    repo = _scoped_repo(tmp_path)
    cs.init(str(repo), "T-1", refs_dir=str(refs))
    _answer_all(repo)
    cs.stamp(str(repo), "T-1", refs_dir=str(refs))
    seal = cs.read_selfcheck(str(repo), "T-1")[1] or {}
    base = scope_base.resolve(str(repo), "T-1")[0]

    now = review_patch.compute(str(repo), base)[0]["bundle_sha256"]
    (repo / "staged.txt").write_text("edited after stamping\n", encoding="utf-8")
    later = review_patch.compute(str(repo), base)[0]["bundle_sha256"]

    assert (seal.get("bundle") == now, seal.get("bundle") != later, seal.get("base") == base) == (
        True, True, True)


def test_cli_refuses_bad_input_with_exit_2_and_no_traceback(tmp_path):
    results = [_cli("stamp", "--root", str(tmp_path), "--ticket", "../x"),
               _cli("stamp", "--root", str(tmp_path)),
               _cli("proposals", "--root", str(tmp_path), "--ticket", "T-1"),
               _cli("bogus")]

    assert [(r.returncode, "Traceback" in r.stderr) for r in results] == [(2, False)] * 4


# ---- Step 6: findings-to-standards proposals and the before/after metric -----------

_OUT = ("READ|part-001-of-001.patch\n"
        "BLOCK|a.py:1|first breaks|run it\n"
        "BLOCK|b.py:2|second | has a pipe|run it\n"
        "FIX|c.py:3|third breaks|run it\n"
        "NIT|d.py:4|style|none\n")


def test_proposals_lists_every_finding_verbatim(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "out.txt").write_text(_OUT, encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()

    first = _cli("proposals", "--root", str(root), "--ticket", "T-1", "--scratch", str(scratch),
                 "--round", "2")
    path = root / ".work" / "tickets" / "T-1" / "standards-proposals-r2.md"
    before = path.read_bytes()
    second = _cli("proposals", "--root", str(root), "--ticket", "T-1", "--scratch",
                  str(scratch), "--round", "2")

    text = before.decode("utf-8")
    verbatim = [line for line in _OUT.split("\n") if line.startswith(("BLOCK|", "FIX|"))]
    assert (first.returncode, second.returncode, path.read_bytes() == before,
            text.count("## Finding "), all(f"    {v}\n" in text for v in verbatim),
            "NIT|" in text, text.count("- Covered by:"), text.count("- Self-check said:"),
            text.count("- Proposal:")) == (0, 1, True, 3, True, False, 3, 3, 3)


def test_proposals_never_writes_a_set_file(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "out.txt").write_text(_OUT, encoding="utf-8")
    root = tmp_path / "root"
    _write_overlay_dir = root / ".crew"
    _write_overlay_dir.mkdir(parents=True)
    (_write_overlay_dir / "standards.md").write_text(OVERLAY, encoding="utf-8")

    def snapshot():
        found = {}
        for base in (_REFS, str(_write_overlay_dir)):
            for dirpath, _, names in os.walk(base):
                for name in names:
                    with open(os.path.join(dirpath, name), "rb") as fh:
                        found[os.path.join(dirpath, name)] = hashlib.sha256(fh.read()).hexdigest()
        return found

    before = snapshot()
    result = _cli("proposals", "--root", str(root), "--ticket", "T-1", "--scratch",
                  str(scratch), "--round", "1")

    assert (result.returncode, snapshot() == before) == (0, True)


def _metrics(root, rows):
    (root / ".crew").mkdir(parents=True, exist_ok=True)
    text = "| date | ticket | reviewer | BLOCK | FIX |\n|---|---|---|---|---|\n" + "".join(
        f"| 2026-09-28 | {t} | {r} | {b} | {f} |\n" for t, r, b, f in rows)
    (root / ".crew" / "metrics.md").write_text(text, encoding="utf-8")


def _many(prefix, count, reviewer, block, fix):
    return [(f"{prefix}-{n}", reviewer, block, fix) for n in range(1, count + 1)]


def test_metric_splits_on_the_std_token(tmp_path):
    _metrics(tmp_path, _many("T", 10, "codex (r1, high)", 2, 1)
             + _many("U", 10, "codex (r1, std:0123abcd)", 0, 1)
             + [("T-1", "codex (r2, high)", 5, 5)])

    found = cs.metric_summary((tmp_path / ".crew" / "metrics.md").read_text(encoding="utf-8"))

    assert ((found["before"]["n"], found["before"]["median"], found["before"]["enough"]),
            (found["after"]["n"], found["after"]["median"], found["after"]["enough"])) == (
        (10, 3, True), (10, 1, True))


def test_metric_unknown_round_is_not_pooled(tmp_path):
    _metrics(tmp_path, [("T-1", "codex (r1)", 1, 1), ("T-2", "codex", 9, 9),
                        ("T-3", "codex std:0123abcd", 9, 9)])

    found = cs.metric_summary((tmp_path / ".crew" / "metrics.md").read_text(encoding="utf-8"))

    assert (found["unknown_round"], found["before"]["n"], found["after"]["n"]) == (2, 1, 0)


def test_metric_not_enough_data(tmp_path):
    import crew_metrics  # pylint: disable=import-outside-toplevel
    _metrics(tmp_path, _many("T", crew_metrics.MIN_BASELINE_KNOWN - 1, "codex (r1)", 1, 0))

    code, lines = cs.metric(str(tmp_path))

    text = "\n".join(lines)
    assert (code, text.count("not enough data")) == (0, 2), text


def test_metric_record_is_invisible_to_existing_readers(tmp_path):
    import crew_migrate  # pylint: disable=import-outside-toplevel
    import crew_state  # pylint: disable=import-outside-toplevel
    _metrics(tmp_path, _many("T", 3, "codex (r1)", 1, 2))
    path = tmp_path / ".crew" / "metrics.md"
    before = (crew_state.read_metrics(str(tmp_path)),
              crew_migrate.metrics_rows(path.read_text(encoding="utf-8"))[0])

    code, _ = cs.metric(str(tmp_path), record=True, today="2026-09-28")

    text = path.read_text(encoding="utf-8")
    rows_after = crew_migrate.metrics_rows(text)[0]
    for row in rows_after + before[1]:
        row["source"] = None
    assert (code, crew_state.read_metrics(str(tmp_path)) == before[0], rows_after == before[1],
            text.rstrip("\n").split("\n")[-1].startswith("standards-metric 2026-09-28:"),
            "|" in text.rstrip("\n").split("\n")[-1]) == (0, True, True, True, False)


# ---- the gate's two bindings, each on its own ------------------------------------

def _stamped(tmp_path, refs):
    import review_patch  # pylint: disable=import-outside-toplevel
    import scope_base  # pylint: disable=import-outside-toplevel
    repo = _scoped_repo(tmp_path)
    cs.init(str(repo), "T-1", refs_dir=str(refs))
    _answer_all(repo)
    assert cs.stamp(str(repo), "T-1", refs_dir=str(refs))[0] == 0
    manifest = review_patch.compute(str(repo), scope_base.resolve(str(repo), "T-1")[0])[0]
    return repo, manifest


def test_gate_passes_a_current_stamp(tmp_path, refs):
    repo, manifest = _stamped(tmp_path, refs)

    assert cs.gate_problems(str(repo), "T-1", manifest, refs_dir=str(refs)) == []


def test_gate_refuses_a_stamp_for_another_standards_set(tmp_path, refs):
    repo, manifest = _stamped(tmp_path, refs)
    generic = refs / "generic.md"
    generic.write_text(generic.read_text(encoding="utf-8").replace("It broke.", "It broke again."),
                       encoding="utf-8")

    problems = cs.gate_problems(str(repo), "T-1", manifest, refs_dir=str(refs))

    assert any("standards set changed" in p for p in problems), problems


def test_gate_refuses_a_stamp_for_another_bundle(tmp_path, refs):
    repo, manifest = _stamped(tmp_path, refs)

    problems = cs.gate_problems(str(repo), "T-1", dict(manifest, bundle_sha256="0" * 64),
                                refs_dir=str(refs))

    assert any("another base" in p or "stale" in p for p in problems), problems


# ---- review round 1: could-not-tell stays could-not-tell ------------------------

def _break_receipt_path(repo, shape):
    """Make `approval.json`'s lookup fail with something other than ENOENT."""
    import crew_ticket  # pylint: disable=import-outside-toplevel
    path = crew_ticket.approval_path(str(repo), "T-1")
    ticket_dir = os.path.dirname(path)
    if shape == "ticket-dir-is-a-file":
        os.makedirs(os.path.dirname(ticket_dir), exist_ok=True)
        with open(ticket_dir, "w", encoding="utf-8") as fh:
            fh.write("not a directory\n")
    elif shape == "tickets-dir-is-a-file":
        os.makedirs(os.path.dirname(os.path.dirname(ticket_dir)), exist_ok=True)
        with open(os.path.dirname(ticket_dir), "w", encoding="utf-8") as fh:
            fh.write("not a directory\n")
    else:
        if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
            pytest.skip("chmod 000 does not stop a lookup on Windows or as root, so an "
                        "unreadable parent cannot be produced this way here")
        os.makedirs(ticket_dir, exist_ok=True)
        os.chmod(ticket_dir, 0)
    return ticket_dir


@pytest.mark.parametrize("shape", ["ticket-dir-is-a-file", "tickets-dir-is-a-file",
                                   "unreadable-parent"])
def test_gate_applies_when_the_receipt_cannot_be_looked_up(tmp_path, shape):
    repo = init_repo(tmp_path / "repo")
    ticket_dir = _break_receipt_path(repo, shape)

    try:
        applies, note = cs.gate_applies(str(repo), "T-1")
    finally:
        if os.path.isdir(ticket_dir):
            os.chmod(ticket_dir, 0o755)

    assert (applies, "could not tell" in (note or "")) == (True, True), note


@pytest.mark.parametrize("shape", ["ticket-dir-is-a-file", "tickets-dir-is-a-file"])
def test_gate_applies_when_a_file_parent_is_reported_as_not_found(tmp_path, monkeypatch, shape):
    """Windows answers a lookup under a regular file with FileNotFoundError, not
    NotADirectoryError; simulated here so the case runs on every OS."""
    repo = init_repo(tmp_path / "repo")
    _break_receipt_path(repo, shape)
    real_lstat = os.lstat

    def lstat_as_windows(path, *args, **kwargs):
        try:
            return real_lstat(path, *args, **kwargs)
        except NotADirectoryError as exc:
            raise FileNotFoundError(2, "The system cannot find the path specified", path) from exc

    monkeypatch.setattr(cs.os, "lstat", lstat_as_windows)

    applies, note = cs.gate_applies(str(repo), "T-1")

    assert (applies, "could not tell" in (note or "")) == (True, True), note


def test_gate_does_not_apply_when_the_receipt_is_proven_absent(tmp_path):
    repo = init_repo(tmp_path / "repo")

    applies, note = cs.gate_applies(str(repo), "T-1")

    assert (applies, "not required" in note) == (False, True), note


def test_checklist_lists_the_always_on_sets_when_file_lists_are_unusable(refs, root):
    _write_overlay(root)

    out = "\n".join(cs.checklist_block(str(root), {"bundle_sha256": "x"}, refs_dir=str(refs)))

    assert (["GEN-01 One" in out, "GEN-02 Two" in out, "REPO-01 Local" in out,
             "PHP-01" in out, "UNKNOWN:" in out]) == [True, True, True, False, True], out


def test_checklist_with_a_manifest_that_is_not_an_object_still_lists(refs, root):
    out = "\n".join(cs.checklist_block(str(root), ["not", "a", "dict"], refs_dir=str(refs)))

    assert ("GEN-01 One" in out, "UNKNOWN:" in out) == (True, True), out


def test_stamp_refuses_a_record_that_changes_while_stamping(tmp_path, refs, monkeypatch):
    repo = _scoped_repo(tmp_path)
    cs.init(str(repo), "T-1", refs_dir=str(refs))
    path = _answer_all(repo)
    real_scope = cs._scope  # pylint: disable=protected-access

    def scope_then_edit(root, ticket):
        found = real_scope(root, ticket)
        path.write_bytes(path.read_bytes() + b"\xff\n")
        return found

    monkeypatch.setattr(cs, "_scope", scope_then_edit)
    code, lines = cs.stamp(str(repo), "T-1", refs_dir=str(refs))

    after = path.read_bytes()
    assert (code, any("changed while" in line for line in lines), after.endswith(b"\xff\n"),
            b"<!-- stamp:" in after) == (1, True, True, False), lines


# ---- review round 2 FIX 1: a record the stamp cannot use --------------------------

def _approve_fixture(repo, ticket="T-1"):
    import crew_ticket  # pylint: disable=import-outside-toplevel
    path = crew_ticket.approval_path(str(repo), ticket)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"ticket": ticket, "approved_by": "fixture"}, fh)


def _commit(repo, name, text):
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-qm", name)


def _write_scope_record(repo, ticket, sha):
    (repo / ".crew").mkdir(exist_ok=True)
    (repo / ".crew" / ".scope-base").write_text(
        json.dumps({ticket: {"base": sha, "from": "HEAD", "recordedAt": "2026-09-29T00:00:00"}}),
        encoding="utf-8")


def _unusable_record_repo(tmp_path, shape):
    """A repo on branch `feat` off `main` whose T-1 record cannot be used:
    `not-ancestor` is round 2's reproduction (record at the branch's start,
    `git reset --hard HEAD~2`, commit again); `missing` names a commit this
    clone does not have. Returns (repo, the reason resolve gives)."""
    import scope_base  # pylint: disable=import-outside-toplevel
    repo = init_repo(tmp_path / "repo")
    _commit(repo, "main1.txt", "m1\n")
    _commit(repo, "main2.txt", "m2\n")
    git(repo, "checkout", "-qb", "feat")
    if shape == "not-ancestor":
        assert scope_base.record(str(repo), "T-1")[1] == "recorded"
        _commit(repo, "feat1.txt", "f1\n")
        git(repo, "reset", "-q", "--hard", "HEAD~2")
        reason = "no longer an ancestor of HEAD"
    else:
        _write_scope_record(repo, "T-1", "0123456789abcdef0123456789abcdef01234567")
        reason = "not in this clone"
    _commit(repo, "feat2.txt", "f2\n")
    return repo, reason


@pytest.mark.parametrize("shape", ["not-ancestor", "missing"])
def test_stamp_scope_fallback_when_the_record_is_unusable(tmp_path, refs, shape):
    import review_patch  # pylint: disable=import-outside-toplevel
    import scope_base  # pylint: disable=import-outside-toplevel
    repo, reason = _unusable_record_repo(tmp_path, shape)
    _approve_fixture(repo)
    base, source, _ = scope_base.resolve(str(repo), "T-1")

    init_code, init_lines = cs.init(str(repo), "T-1", refs_dir=str(refs))
    _answer_all(repo)
    code, lines = cs.stamp(str(repo), "T-1", refs_dir=str(refs))

    _, seal, _ = cs.read_selfcheck(str(repo), "T-1")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(review_patch.compute(str(repo), base)[0]),
                             encoding="utf-8")
    gate, _ = cs.review_gate(str(repo), "T-1", str(manifest_path), refs_dir=str(refs))
    marked = [any("(fallback)" in line and reason in line for line in out)
              for out in (init_lines, lines)]
    assert (source, init_code, code, (seal or {}).get("base") == base, marked, gate) == (
        "merge-base", 0, 0, True, [True, True], []), (init_lines, lines, gate)


def test_stamp_without_a_scope_base_names_a_remedy_that_works(tmp_path, refs):
    import scope_base  # pylint: disable=import-outside-toplevel
    repo = init_repo(tmp_path / "repo")
    ticket_dir = repo / ".work" / "tickets" / "T-1"
    ticket_dir.mkdir(parents=True)
    (repo / "x.txt").write_text("x\n", encoding="utf-8")
    (ticket_dir / "selfcheck.md").write_text(
        "# T-1 self-check\n\n| ID | Status | Evidence or reason |\n|---|---|---|\n"
        "| GEN-01 | n/a | none of it |\n| GEN-02 | n/a | none of it |\n", encoding="utf-8")

    first, first_lines = cs.stamp(str(repo), "T-1", refs_dir=str(refs))
    scope_base.record(str(repo), "T-1")
    second, second_lines = cs.stamp(str(repo), "T-1", refs_dir=str(refs))

    named = any("scope_base.py --root . --record T-1" in line for line in first_lines)
    assert (first, named, second) == (1, True, 0), (first_lines, second_lines)


def test_stamp_refusal_never_names_a_record_that_would_be_kept(tmp_path, refs):
    import scope_base  # pylint: disable=import-outside-toplevel
    repo = init_repo(tmp_path / "repo")
    git(repo, "branch", "-m", "main", "feat")
    _write_scope_record(repo, "T-1", "0123456789abcdef0123456789abcdef01234567")
    _commit(repo, "feat.txt", "f\n")
    source = scope_base.resolve(str(repo), "T-1")[1]
    ticket_dir = repo / ".work" / "tickets" / "T-1"
    ticket_dir.mkdir(parents=True)
    (ticket_dir / "selfcheck.md").write_text(
        "# T-1 self-check\n\n| ID | Status | Evidence or reason |\n|---|---|---|\n"
        "| GEN-01 | n/a | none of it |\n| GEN-02 | n/a | none of it |\n", encoding="utf-8")

    code, lines = cs.stamp(str(repo), "T-1", refs_dir=str(refs))

    text = "\n".join(lines)
    assert (source, code, "not in this clone" in text, "--record" in text) == (
        "head", 1, True, False), text


# ---- review round 2 FIX 2: each caller refuses a broken effective set ------------

_NOT_UTF8_OVERLAY = b"---\nset: REPO\napplies-to: [\"**\"]\n---\n\xff\xfe\n"


def test_init_refuses_a_broken_effective_set(tmp_path, refs):
    repo = _scoped_repo(tmp_path)
    _write_overlay(repo, raw=_NOT_UTF8_OVERLAY)

    code, lines = cs.init(str(repo), "T-1", refs_dir=str(refs))

    text = "\n".join(lines)
    assert (code, ".crew/standards.md: not UTF-8" in text,
            (repo / ".work" / "tickets" / "T-1" / "selfcheck.md").exists()) == (
        1, True, False), text


def test_stamp_refuses_a_broken_effective_set(tmp_path, refs):
    repo = _scoped_repo(tmp_path)
    _write_overlay(repo)
    cs.init(str(repo), "T-1", refs_dir=str(refs))
    path = _answer_all(repo)
    before = path.read_bytes()
    _write_overlay(repo, raw=_NOT_UTF8_OVERLAY)

    code, lines = cs.stamp(str(repo), "T-1", refs_dir=str(refs))

    text = "\n".join(lines)
    assert (code, ".crew/standards.md: not UTF-8" in text, path.read_bytes() == before) == (
        1, True, True), text


# ---- review round 2 FIX 3: every other refusal branch, each by its own text ------
# Each test reaches its refusal through the caller that must refuse (`stamp`
# exit 1, or `review_gate`'s problems) and asserts that branch's own message,
# so one branch's test cannot pass on another branch's refusal.

def _stamp_after(tmp_path, refs, break_it):
    """A complete record for a scoped repo, then `break_it(repo, path)`, then
    `stamp`. Returns (code, joined lines)."""
    repo = _scoped_repo(tmp_path)
    cs.init(str(repo), "T-1", refs_dir=str(refs))
    path = _answer_all(repo)
    break_it(repo, path)
    code, lines = cs.stamp(str(repo), "T-1", refs_dir=str(refs))
    return code, "\n".join(lines)


def _edit(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_refusal_branch_gate_applies_lookup_error(tmp_path, refs, monkeypatch):
    import crew_ticket  # pylint: disable=import-outside-toplevel
    import review_patch  # pylint: disable=import-outside-toplevel
    repo = _scoped_repo(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(review_patch.compute(
        str(repo), git(repo, "rev-list", "--max-parents=0", "HEAD"))[0]), encoding="utf-8")

    def refuse(*_args, **_kwargs):
        raise crew_ticket.TicketError("lookup broke")

    monkeypatch.setattr(crew_ticket, "read_approval", refuse)
    applies, note = cs.gate_applies(str(repo), "T-1")
    problems, _ = cs.review_gate(str(repo), "T-1", str(manifest_path), refs_dir=str(refs))

    assert (applies, "could not be looked up" in (note or ""),
            any("no self-check at" in p for p in problems)) == (True, True, True), (note, problems)


def test_refusal_branch_manifest_not_an_object(tmp_path, refs):
    repo = _scoped_repo(tmp_path)
    _approve_fixture(repo)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("[]", encoding="utf-8")

    problems, _ = cs.review_gate(str(repo), "T-1", str(manifest_path), refs_dir=str(refs))

    assert any("is not an object" in p for p in problems), problems


def test_refusal_branch_nothing_to_review(tmp_path, refs):
    import scope_base  # pylint: disable=import-outside-toplevel
    repo = init_repo(tmp_path / "repo")
    exclude = repo / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text(".crew/\n", encoding="utf-8")
    scope_base.record(str(repo), "T-1")
    ticket_dir = repo / ".work" / "tickets" / "T-1"
    ticket_dir.mkdir(parents=True)
    (ticket_dir / "selfcheck.md").write_text(
        "# T-1 self-check\n\n| ID | Status | Evidence or reason |\n|---|---|---|\n"
        "| GEN-01 | n/a | none of it |\n| GEN-02 | n/a | none of it |\n", encoding="utf-8")

    code, lines = cs.stamp(str(repo), "T-1", refs_dir=str(refs))

    assert (code, any("nothing to review" in line for line in lines)) == (1, True), lines


def test_refusal_branch_malformed_row(tmp_path, refs):
    code, text = _stamp_after(tmp_path, refs, lambda repo, path: path.write_text(
        path.read_text(encoding="utf-8") + "| GEN-01 | addressed |\n", encoding="utf-8"))

    assert (code, "is not | <ID> | <status> | <evidence or reason> |" in text) == (1, True), text


def test_refusal_branch_unparseable_stamp(tmp_path, refs):
    code, text = _stamp_after(tmp_path, refs, lambda repo, path: path.write_text(
        path.read_text(encoding="utf-8") + "<!-- stamp: bundle=xyz -->\n", encoding="utf-8"))

    assert (code, "the stamp line does not parse" in text) == (1, True), text


def test_refusal_branch_second_stamp(tmp_path, refs):
    line = f"<!-- stamp: bundle={'a' * 64} standards={'b' * 64} base={'c' * 40} -->\n"
    code, text = _stamp_after(tmp_path, refs, lambda repo, path: path.write_text(
        path.read_text(encoding="utf-8") + line + line, encoding="utf-8"))

    assert (code, "carries 2 stamp lines" in text) == (1, True), text


def test_refusal_branch_repeated_field(tmp_path, refs):
    code, text = _stamp_after(tmp_path, refs, lambda repo, path: _edit(
        refs / "generic.md", "## GEN-02 Two\n\n**Rule.** Do the thing.",
        "## GEN-02 Two\n\n**Rule.** Do the thing.\n\n**Rule.** Again."))

    assert (code, "GEN-02 repeats **Rule.**" in text) == (1, True), text


def test_refusal_branch_repeated_front_matter_key(tmp_path, refs):
    code, text = _stamp_after(tmp_path, refs, lambda repo, path: _edit(
        refs / "generic.md", "set: GEN\n", "set: GEN\nset: GEN\n"))

    assert (code, "front matter repeats 'set'" in text) == (1, True), text


def test_refusal_branch_plugin_set_supplements(tmp_path, refs):
    code, text = _stamp_after(tmp_path, refs, lambda repo, path: (refs / "php.md").write_text(
        (refs / "php.md").read_text(encoding="utf-8") + "\n## Supplements GEN-01\n\ntext\n",
        encoding="utf-8"))

    assert (code, "a plugin set may not carry Supplements" in text) == (1, True), text


def test_refusal_branch_duplicate_plugin_set(tmp_path, refs):
    code, text = _stamp_after(tmp_path, refs, lambda repo, path: (refs / "php2.md").write_text(
        _set_file("PHP", ["**/*.php"], _standard("PHP-02", "Again")), encoding="utf-8"))

    assert (code, "set PHP is also references/php.md" in text) == (1, True), text


def test_refusal_branch_no_gen_set(tmp_path, refs):
    code, text = _stamp_after(tmp_path, refs, lambda repo, path: (refs / "generic.md").unlink())

    assert (code, "has no set GEN" in text) == (1, True), text


def test_refusal_branch_empty_set(tmp_path, refs):
    code, text = _stamp_after(tmp_path, refs, lambda repo, path: (refs / "empty.md").write_text(
        _set_file("EMP", ["**"], ""), encoding="utf-8"))

    assert (code, "references/empty.md: defines no standard" in text) == (1, True), text


# ---- review round 3: a recorded guess, an unreadable record, proposals, std:none --

def _record_fallback_repo(tmp_path):
    """A repo on branch `feat`, one commit past `main`, whose T-1 entry was
    first recorded there, so `scope_base.record` wrote the merge-base marked
    `from: merge-base with main` (round 3 FIX 1's reproduction)."""
    import scope_base  # pylint: disable=import-outside-toplevel
    repo = init_repo(tmp_path / "repo")
    git(repo, "checkout", "-qb", "feat")
    _commit(repo, "feat1.txt", "f1\n")
    assert scope_base.record(str(repo), "T-1")[1] == "recorded-fallback"
    _approve_fixture(repo)
    return repo


def test_stamp_marks_a_record_written_as_a_fallback(tmp_path, refs):
    import scope_base  # pylint: disable=import-outside-toplevel
    repo = _record_fallback_repo(tmp_path)
    base, source, _ = scope_base.resolve(str(repo), "T-1")

    init_code, init_lines = cs.init(str(repo), "T-1", refs_dir=str(refs))
    _answer_all(repo)
    code, lines = cs.stamp(str(repo), "T-1", refs_dir=str(refs))
    sets_code, sets_lines = cs._sets(str(repo), "T-1", refs_dir=str(refs))  # pylint: disable=protected-access

    _, seal, _ = cs.read_selfcheck(str(repo), "T-1")
    marked = [any("(fallback)" in line and base[:12] in line for line in out)
              for out in (init_lines, lines, sets_lines)]
    assert (source, init_code, code, sets_code, (seal or {}).get("base") == base, marked) == (
        "record-fallback", 0, 0, 0, True, [True, True, True]), (init_lines, lines, sets_lines)


_BROKEN_SCOPE_RECORDS = {"not-json": b"{", "not-an-object": b"[]\n"}


@pytest.mark.parametrize("shape", sorted(_BROKEN_SCOPE_RECORDS))
def test_stamp_refuses_an_unreadable_scope_record_without_naming_record(tmp_path, refs, shape):
    import scope_base  # pylint: disable=import-outside-toplevel
    repo = _scoped_repo(tmp_path)
    scope_base.record(str(repo), "T-2")
    cs.init(str(repo), "T-1", refs_dir=str(refs))
    _answer_all(repo)
    record = repo / ".crew" / ".scope-base"
    record.write_bytes(_BROKEN_SCOPE_RECORDS[shape])

    code, lines = cs.stamp(str(repo), "T-1", refs_dir=str(refs))
    init_code, init_lines = cs.init(str(repo), "T-9", refs_dir=str(refs))

    text = "\n".join(lines + init_lines)
    assert (code, init_code, text.count("cannot be read"), "--record" in text,
            record.read_bytes() == _BROKEN_SCOPE_RECORDS[shape]) == (
        1, 1, 2, False, True), text


_INCOMPLETE_OUTPUTS = {
    "empty": "",
    "bullet": "READ|part-001-of-001.patch\n- BLOCK|a.py:1|first breaks|run it\n",
    "fenced-clean": "READ|part-001-of-001.patch\n```\nCLEAN\n```\n",
    "neither": "READ|part-001-of-001.patch\n",
}


@pytest.mark.parametrize("shape", sorted(_INCOMPLETE_OUTPUTS))
def test_proposals_refuses_an_incomplete_output_and_writes_nothing(tmp_path, shape):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "out.txt").write_text(_INCOMPLETE_OUTPUTS[shape], encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    args = ("proposals", "--root", str(root), "--ticket", "T-1", "--scratch", str(scratch),
            "--round", "1")

    first = _cli(*args)
    written = (root / ".work" / "tickets" / "T-1" / "standards-proposals-r1.md").exists()
    (scratch / "out.txt").write_text(_OUT, encoding="utf-8")
    second = _cli(*args)

    assert (first.returncode, "INCOMPLETE" in first.stderr, written, second.returncode) == (
        1, True, False, 0), (first.stdout, first.stderr, second.stderr)


def test_proposals_writes_the_findings_of_a_recovered_round(tmp_path):
    """A fence around well-formed findings is a harmless stray line; the
    parser recovers the round as FINDINGS (L-0576), so its BLOCK is proposed."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "out.txt").write_text(
        "READ|part-001-of-001.patch\n```\nBLOCK|a.py:1|first breaks|run it\n```\n",
        encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()

    result = _cli("proposals", "--root", str(root), "--ticket", "T-1", "--scratch",
                  str(scratch), "--round", "1")

    text = (root / ".work" / "tickets" / "T-1" / "standards-proposals-r1.md").read_text(
        encoding="utf-8")
    assert (result.returncode, "BLOCK|a.py:1|first breaks|run it" in text) == (
        0, True), result.stderr


def test_proposals_proposes_a_round_whose_admission_the_wording_list_misses(tmp_path):
    """L-0604: the docstring's rule. A shortfall admission outside
    `review_verdict._SHORTFALL` is recovered as prose, so the round is
    FINDINGS: its FIX is proposed and the admission is not written."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "out.txt").write_text(
        "FIX|x.py:1|bad|repro\nI only inspected one of the nine files", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()

    result = _cli("proposals", "--root", str(root), "--ticket", "T-1", "--scratch",
                  str(scratch), "--round", "1")

    text = (root / ".work" / "tickets" / "T-1" / "standards-proposals-r1.md").read_text(
        encoding="utf-8")
    assert (result.returncode, "FIX|x.py:1|bad|repro" in text,
            "nine files" in text) == (0, True, False), result.stderr


@pytest.mark.parametrize("out", ["READ|part-001-of-001.patch\nCLEAN\n",
                                 "READ|part-001-of-001.patch\nNIT|d.py:4|style|none\n"])
def test_proposals_writes_a_round_with_no_block_or_fix(tmp_path, out):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "out.txt").write_text(out, encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()

    result = _cli("proposals", "--root", str(root), "--ticket", "T-1", "--scratch",
                  str(scratch), "--round", "1")

    text = (root / ".work" / "tickets" / "T-1" / "standards-proposals-r1.md").read_text(
        encoding="utf-8")
    assert (result.returncode, "No BLOCK or FIX finding in this round." in text) == (
        0, True), result.stderr


@pytest.mark.parametrize("token, key", [("std:none", "std_none"),
                                        ("std:0123abcd99", "std_unreadable"),
                                        ("std:", "std_unreadable"),
                                        ("std:0123ABCD", "std_unreadable")])
def test_metric_keeps_a_row_without_a_digest_out_of_the_baseline(tmp_path, token, key):
    _metrics(tmp_path, _many("T", 10, "codex (r1, high)", 1, 1)
             + [("T-99", f"codex (r1, {token})", 9, 9)])

    found = cs.metric_summary((tmp_path / ".crew" / "metrics.md").read_text(encoding="utf-8"))

    assert ((found["before"]["n"], found["before"]["median"]), found["after"]["n"],
            found[key]) == ((10, 2), 0, 1)


def test_metric_prints_the_rows_on_neither_side(tmp_path):
    _metrics(tmp_path, _many("T", 3, "codex (r1, high)", 1, 1)
             + [("T-98", "codex (r1, std:none)", 9, 9), ("T-99", "codex (r1, std:zz)", 9, 9)])

    code, lines = cs.metric(str(tmp_path))

    text = "\n".join(lines)
    assert (code, "std:none rows 1" in text, "unreadable std: tokens 1" in text) == (
        0, True, True), text
