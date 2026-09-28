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


def test_shipped_sets_cite_nothing_local_only():
    offenders = []
    for name in sorted(os.listdir(_REFS)):
        with open(os.path.join(_REFS, name), encoding="utf-8") as fh:
            for number, line in enumerate(fh, 1):
                if re.search(r"\.work/|\bF\d{3}\b", line):
                    offenders.append(f"{name}:{number}: {line.strip()[:80]}")

    assert offenders == []


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
    _, seal, _ = cs.read_selfcheck(str(repo), "T-1")
    base = scope_base.resolve(str(repo), "T-1")[0]

    now = review_patch.compute(str(repo), base)[0]["bundle_sha256"]
    (repo / "staged.txt").write_text("edited after stamping\n", encoding="utf-8")
    later = review_patch.compute(str(repo), base)[0]["bundle_sha256"]

    assert (seal["bundle"] == now, seal["bundle"] != later, seal["base"] == base) == (
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
