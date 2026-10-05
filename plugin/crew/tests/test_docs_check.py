"""T-0022: `crew_docs_check.py` -- per-document verdicts, read-only.

    python3 -m pytest plugin/crew/tests/test_docs_check.py -q

Every repository is a throwaway git repo under tmp_path with its scope base
recorded at the fixture commit, so the changed set is exactly what each test
writes after it. Nothing touches the real repo or ~/.claude. The command-text
tests at the bottom pin `/crew:docs`, `/crew:implement` step 6 and
`/crew:done`'s docs check.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_docs_check
import crew_refresh_check
import scope_base

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPT = os.path.join(_ROOT, "hooks", "scripts", "crew_docs_check.py")
_COMMANDS = os.path.join(_ROOT, "commands")
T = "T-1"
CHANGELOG_HEAD = "# Changelog\n\n## [Unreleased]\n\n## [0.1.0]\n\n- first\n"


def _git(root, *args):
    subprocess.run(["git", "-C", str(root)] + list(args), check=True, capture_output=True,
                   stdin=subprocess.DEVNULL)


def _write(root, rel, text):
    path = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _market(*entries):
    return json.dumps({"name": "m", "plugins": [
        {"name": name, "source": f"./plugin/{name}", "version": version}
        for name, version in entries]}, indent=2) + "\n"


def _repo(tmp_path, market=True, changelog=True, security=True, todo=True):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "T")
    _write(root, "README.md", "root readme\n")
    _write(root, "plugin/crew/README.md", "crew readme\n")
    _write(root, "plugin/crew/hooks/scripts/app.py", "x = 1\n")
    _write(root, "plugin/crew/commands/go.md", "go\n")
    _write(root, "src/lib.py", "y = 1\n")
    if market:
        _write(root, ".claude-plugin/marketplace.json", _market(("crew", "1.0.0")))
    if changelog:
        _write(root, "CHANGELOG.md", CHANGELOG_HEAD)
    if security:
        _write(root, "SECURITY.md", "report to x\n")
    if todo:
        _write(root, "TODO.md", "# TODO\n")
    _write(root, ".gitignore", ".work/\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    os.makedirs(os.path.join(str(root), ".work", "tickets", T), exist_ok=True)
    _, status = scope_base.record(str(root), T)
    assert status == "recorded"
    return root


def _docs_json(root, reasons=None, deferred=None):
    _write(root, f".work/tickets/{T}/docs.json",
           json.dumps({"reasons": reasons or {}, "deferred": deferred or []}))


def _bump(root, version="1.0.1"):
    _write(root, ".claude-plugin/marketplace.json", _market(("crew", version)))


def _changelog(root, entry):
    _write(root, "CHANGELOG.md", CHANGELOG_HEAD.replace(
        "## [Unreleased]\n", f"## [Unreleased]\n\n{entry}\n"))


def _check(root):
    return crew_docs_check.ticket_docs(str(root), T)


def _verdict(result, doc):
    rows = [d for d in result["documents"] if d["doc"] == doc]
    assert len(rows) == 1, (doc, result)
    return rows[0]["verdict"], rows[0]["reason"]


def _snapshot(root):
    found = {}
    for base, dirs, files in os.walk(str(root)):
        dirs[:] = [d for d in dirs if d != "objects"]
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as handle:
                found[path] = handle.read()
    return found


# --- CHANGELOG: mechanical, never waived --------------------------------------

def test_changed_plugin_without_changelog_is_missing(tmp_path):
    root = _repo(tmp_path)
    _write(root, "plugin/crew/hooks/scripts/app.py", "x = 2\n")
    _bump(root)

    got = _check(root)

    assert got["status"] == "missing"
    verdict, reason = _verdict(got, "CHANGELOG.md (crew 1.0.1)")
    assert verdict == "MISSING" and "`crew` 1.0.1" in reason


def test_changelog_reason_does_not_waive(tmp_path):
    root = _repo(tmp_path)
    _write(root, "plugin/crew/hooks/scripts/app.py", "x = 2\n")
    _bump(root)
    _docs_json(root, reasons={"CHANGELOG.md": "internal only",
                              "CHANGELOG.md (crew 1.0.1)": "internal only"})

    got = _check(root)

    assert (got["status"], _verdict(got, "CHANGELOG.md (crew 1.0.1)")[0]) == ("missing", "MISSING")


def test_changelog_entry_names_version_is_updated(tmp_path):
    root = _repo(tmp_path)
    _write(root, "plugin/crew/hooks/scripts/app.py", "x = 2\n")
    _bump(root)
    _changelog(root, "### Fixed - `crew` 1.0.1: app counts to two")

    got = _check(root)

    assert (got["status"], _verdict(got, "CHANGELOG.md (crew 1.0.1)")[0]) == ("ok", "updated")


@pytest.mark.parametrize("entry", [
    "### Fixed - `crew` 1.0.0: names the old version",
    "### Fixed - crew 1.0.1: name not backticked",
    "### Fixed - `crew` 1.0.10: a longer version is not this one",
    "### Fixed - `crew` 1.0.1.1: a dotted extension is not this one",
    "### Fixed - `crew` 1.0.1-rc.1: a prerelease is not this one",
    "### Fixed - `crew` 1.0.1+build5: build metadata is not this one",
    "### Fixed - `crew` 1.0.1_2: an underscored suffix is not this one",
], ids=["old-version", "unquoted-name", "prefix-version", "dotted-suffix", "prerelease",
        "build", "underscore"])
def test_changelog_entry_that_does_not_name_this_version_is_missing(tmp_path, entry):
    root = _repo(tmp_path)
    _write(root, "plugin/crew/hooks/scripts/app.py", "x = 2\n")
    _bump(root)
    _changelog(root, entry)

    assert _verdict(_check(root), "CHANGELOG.md (crew 1.0.1)")[0] == "MISSING"


def test_changelog_line_outside_unreleased_does_not_count(tmp_path):
    root = _repo(tmp_path)
    _write(root, "plugin/crew/hooks/scripts/app.py", "x = 2\n")
    _bump(root)
    _write(root, "CHANGELOG.md", CHANGELOG_HEAD + "\n- `crew` 1.0.1: filed under 0.1.0\n")

    assert _verdict(_check(root), "CHANGELOG.md (crew 1.0.1)")[0] == "MISSING"


def test_release_paths_only_needs_no_changelog(tmp_path):
    root = _repo(tmp_path)
    _bump(root)
    _write(root, "TODO.md", "# TODO\n- later\n")
    _write(root, "plugin/crew/.claude-plugin/plugin.json", '{"version": "1.0.1"}\n')
    _write(root, "plugin/crew/BUDGETS.md", "budgets\n")
    _write(root, ".work/tickets/T-1/notes.md", "scratch\n")

    got = _check(root)

    assert (got["status"], _verdict(got, "CHANGELOG.md")) == (
        "ok", ("not needed", "no marketplace entry's source changed"))


def test_release_paths_are_t0008s_list():
    assert crew_docs_check.RELEASE_PATHS is crew_refresh_check.RELEASE_BOOKKEEPING


def test_change_outside_every_entry_needs_no_changelog(tmp_path):
    root = _repo(tmp_path)
    _write(root, "src/lib.py", "y = 2\n")

    assert _verdict(_check(root), "CHANGELOG.md")[0] == "not needed"


def test_no_marketplace_changelog_is_judgement(tmp_path):
    root = _repo(tmp_path, market=False)
    _write(root, "src/lib.py", "y = 2\n")

    assert _verdict(_check(root), "CHANGELOG.md")[0] == "MISSING"
    _docs_json(root, reasons={"CHANGELOG.md": "refactor, nothing observable"})
    assert _verdict(_check(root), "CHANGELOG.md") == (
        "not needed", "refactor, nothing observable")


def test_no_changelog_is_not_applicable(tmp_path):
    root = _repo(tmp_path, changelog=False)
    _write(root, "plugin/crew/hooks/scripts/app.py", "x = 2\n")

    assert _verdict(_check(root), "CHANGELOG.md")[0] == "not applicable"


# --- README, SECURITY.md, TODO.md: judgement with a reason --------------------

def _readme_trigger(root):
    _write(root, "plugin/crew/commands/go.md", "go faster\n")
    _bump(root)
    _changelog(root, "- `crew` 1.0.1: go is faster")


def test_readme_trigger_without_reason_missing(tmp_path):
    root = _repo(tmp_path)
    _readme_trigger(root)

    got = _check(root)

    assert (got["status"], _verdict(got, "plugin/crew/README.md")[0]) == ("missing", "MISSING")


def test_readme_reason_not_needed(tmp_path):
    root = _repo(tmp_path)
    _readme_trigger(root)
    _docs_json(root, reasons={"plugin/crew/README.md": "wording only"})

    got = _check(root)

    assert (got["status"], _verdict(got, "plugin/crew/README.md")) == (
        "ok", ("not needed", "wording only"))


def test_readme_edited_is_updated(tmp_path):
    root = _repo(tmp_path)
    _readme_trigger(root)
    _write(root, "plugin/crew/README.md", "crew readme, go is faster\n")

    assert _verdict(_check(root), "plugin/crew/README.md")[0] == "updated"


def test_root_readme_when_entry_names_change(tmp_path):
    root = _repo(tmp_path)
    _write(root, ".claude-plugin/marketplace.json", _market(("crew", "1.0.0"), ("new", "0.1.0")))

    assert _verdict(_check(root), "README.md")[0] == "MISSING"


def test_no_readme_trigger_not_needed(tmp_path):
    root = _repo(tmp_path)
    _write(root, "src/lib.py", "y = 2\n")

    assert _verdict(_check(root), "README.md") == ("not needed", "no README trigger changed")


def test_security_untouched_not_needed(tmp_path):
    root = _repo(tmp_path)
    _write(root, "src/lib.py", "y = 2\n")

    assert _verdict(_check(root), "SECURITY.md") == (
        "not needed", "no security-relevant path changed")


def test_security_path_without_reason_missing(tmp_path):
    root = _repo(tmp_path)
    _write(root, "plugin/crew/hooks/scripts/scope_guard.py", "guard = 1\n")
    _bump(root)
    _changelog(root, "- `crew` 1.0.1: a guard")

    got = _check(root)

    assert (got["status"], _verdict(got, "SECURITY.md")[0]) == ("missing", "MISSING")
    _docs_json(root, reasons={"SECURITY.md": "reporting policy unchanged"})
    assert _verdict(_check(root), "SECURITY.md") == ("not needed", "reporting policy unchanged")


_DEFER = {"key": "T-0099", "why": "ADRs are not measured", "unblock": "T-0040 lands"}


def test_deferred_missing_from_todo(tmp_path):
    root = _repo(tmp_path)
    _write(root, "src/lib.py", "y = 2\n")
    _docs_json(root, deferred=[_DEFER])

    got = _check(root)

    assert (got["status"], _verdict(got, "TODO.md")[0]) == ("missing", "MISSING")
    _write(root, "TODO.md", "# TODO\n- T-0099: measure ADRs. Why: ADRs are not\n"
                            "  measured. Unblock: T-0040 lands.\n")
    assert _verdict(_check(root), "TODO.md")[0] == "updated"


@pytest.mark.parametrize("todo", [
    "# TODO\n- T-00990: ADRs are not measured; T-0040 lands\n",
    "# TODO\n- XT-0099: ADRs are not measured; T-0040 lands\n",
    "# TODO\n- T-0099: measure ADRs\n",
    "# TODO\n- T-0099: ADRs are not measured\n- other: T-0040 lands\n",
    "# TODO\n- T-1000: Notes for T-0099: ADRs are not measured; T-0040 lands\n",
    "# TODO\n## Notes for T-0099: ADRs are not measured; T-0040 lands\n",
], ids=["longer-id", "prefixed-id", "no-why-or-unblock", "unblock-in-another-entry",
        "inside-another-entry", "heading-not-opening-with-the-key"])
def test_deferred_todo_entry_must_be_its_own_with_why_and_unblock(tmp_path, todo):
    """T-0022 port review r2 FIX: the key as a whole id, and its own entry
    carries the recorded why and unblock."""
    root = _repo(tmp_path)
    _write(root, "src/lib.py", "y = 2\n")
    _docs_json(root, deferred=[_DEFER])
    _write(root, "TODO.md", todo)

    assert _verdict(_check(root), "TODO.md")[0] == "MISSING"


def test_nothing_deferred_todo_not_needed(tmp_path):
    root = _repo(tmp_path)
    _write(root, "src/lib.py", "y = 2\n")

    assert _verdict(_check(root), "TODO.md") == ("not needed", "nothing deferred")


# --- unknown is its own value --------------------------------------------------

def test_no_scope_base_unknown(tmp_path):
    root = _repo(tmp_path)
    _write(root, "src/lib.py", "y = 2\n")

    got = crew_docs_check.ticket_docs(str(root), "T-2")

    assert (got["status"], "no scope base" in got["reason"]) == ("unknown", True)
    assert crew_docs_check.exit_code(got) == 1


def test_fallback_equal_to_head_on_a_fresh_branch_unknown(tmp_path):
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, "src/lib.py", "y = 2\n")

    got = crew_docs_check.ticket_docs(str(root), "T-2")

    assert (got["status"], "hides the change" in got["reason"]) == ("unknown", True)


def test_fallback_base_off_the_default_branch_is_used(tmp_path):
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, "src/lib.py", "y = 2\n")
    _git(root, "commit", "-qam", "unrelated subject")

    got = crew_docs_check.ticket_docs(str(root), "T-2")

    assert (got["status"], got["base_source"]) == ("ok", "merge-base")


def test_fallback_with_the_ticket_behind_it_unknown(tmp_path):
    root = _repo(tmp_path)
    _write(root, "src/lib.py", "y = 2\n")
    _git(root, "commit", "-qam", "T-2: pushed to main before the branch")
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, "src/lib.py", "y = 3\n")
    _git(root, "commit", "-qam", "more")

    got = crew_docs_check.ticket_docs(str(root), "T-2")

    assert (got["status"], "may hide T-2's commits" in got["reason"]) == ("unknown", True)


def test_recorded_base_with_the_ticket_behind_it_unknown(tmp_path):
    root = _repo(tmp_path)
    _write(root, "src/lib.py", "y = 2\n")
    _git(root, "commit", "-qam", "T-2: earlier work already on main")
    scope_base.record(str(root), "T-2")

    got = crew_docs_check.ticket_docs(str(root), "T-2")

    assert (got["status"], "may hide T-2's commits" in got["reason"]) == ("unknown", True)


def test_docs_json_corrupt_unknown(tmp_path):
    root = _repo(tmp_path)
    _write(root, "src/lib.py", "y = 2\n")
    _write(root, f".work/tickets/{T}/docs.json", "{not json")

    got = _check(root)

    assert (got["status"], got["reason"].startswith("docs.json")) == ("unknown", True)


@pytest.mark.parametrize("body", [
    '[]', '{"reasons": ["x"]}', '{"deferred": [{"why": "x"}]}',
    '{"deferred": [{"key": "T-9"}]}', '{"deferred": [{"key": "T-9", "why": "x"}]}',
    '{"deferred": [{"key": "T-9", "why": " ", "unblock": "y"}]}'],
    ids=["list", "reasons-list", "no-key", "key-only", "no-unblock", "blank-why"])
def test_docs_json_misshapen_unknown(tmp_path, body):
    root = _repo(tmp_path)
    _write(root, f".work/tickets/{T}/docs.json", body)

    assert _check(root)["status"] == "unknown"


# --- git that cannot answer is unknown, never "absent" (review round 1 FIX) --------

def _git_fails_at_base(monkeypatch, commands=("ls-tree", "cat-file")):
    real = crew_docs_check._git_bytes  # pylint: disable=protected-access

    def failing(top, *args):
        if args and args[0] in commands:
            return None
        return real(top, *args)
    monkeypatch.setattr(crew_docs_check, "_git_bytes", failing)


def test_todo_base_unreadable_is_unknown_not_updated(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _write(root, "TODO.md", "# TODO\n- T-0099: already filed before this ticket\n")
    _git(root, "commit", "-qam", "file T-0099 earlier")
    scope_base.record(str(root), "T-3")
    _write(root, "src/lib.py", "y = 2\n")
    _write(root, ".work/tickets/T-3/docs.json",
           json.dumps({"reasons": {}, "deferred": [{"key": "T-0099", "why": "x", "unblock": "y"}]}))
    _git_fails_at_base(monkeypatch)

    got = crew_docs_check.ticket_docs(str(root), "T-3")

    rows = {d["doc"]: d["verdict"] for d in got["documents"]}
    assert (got["status"], rows["TODO.md"]) == ("unknown", "unknown")


def test_changelog_base_unreadable_is_unknown_not_updated(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _write(root, "plugin/crew/hooks/scripts/app.py", "x = 2\n")
    _changelog(root, "- `crew` 1.0.0: already released")
    _git_fails_at_base(monkeypatch)

    got = _check(root)

    assert (got["status"], _verdict(got, "CHANGELOG.md (crew 1.0.0)")[0]) == ("unknown", "unknown")
    assert crew_docs_check.exit_code(got) == 1


def test_changelog_base_listed_but_unreadable_is_unknown(tmp_path, monkeypatch):
    # ls-tree finds the file, cat-file cannot read it: still unknown, never "absent".
    root = _repo(tmp_path)
    _write(root, "plugin/crew/hooks/scripts/app.py", "x = 2\n")
    _changelog(root, "- `crew` 1.0.0: already released")
    _git_fails_at_base(monkeypatch, commands=("cat-file",))

    got = _check(root)

    assert (got["status"], _verdict(got, "CHANGELOG.md (crew 1.0.0)")[0]) == ("unknown", "unknown")


@pytest.mark.parametrize("commands", [("ls-tree", "cat-file"), ("cat-file",)])
def test_readme_base_marketplace_unreadable_is_unknown(tmp_path, monkeypatch, commands):
    # Only the README row reads git here: CHANGELOG has no touched entry, TODO
    # nothing deferred. A None base would read `crew` as an added entry.
    root = _repo(tmp_path)
    _write(root, "src/lib.py", "y = 2\n")
    _git_fails_at_base(monkeypatch, commands=commands)

    got = _check(root)

    assert (got["status"], _verdict(got, "README.md")[0]) == ("unknown", "unknown")


def test_readme_base_marketplace_corrupt_is_unknown(tmp_path):
    root = _repo(tmp_path)
    _write(root, ".claude-plugin/marketplace.json", "{not json\n")
    _git(root, "commit", "-qam", "corrupt marketplace")
    scope_base.record(str(root), "T-3")
    _write(root, ".claude-plugin/marketplace.json", _market(("crew", "1.0.0")))

    got = crew_docs_check.ticket_docs(str(root), "T-3")

    rows = {d["doc"]: d["verdict"] for d in got["documents"]}
    assert (got["status"], rows["README.md"]) == ("unknown", "unknown")


@pytest.mark.parametrize("line", [
    "- **T-0099**: ADRs are not measured; T-0040 lands",
    "* `T-0099` ADRs are not measured; T-0040 lands",
    "### T-0099: ADRs are not measured; T-0040 lands"])
def test_deferred_todo_entry_forms_that_count(tmp_path, line):
    root = _repo(tmp_path)
    _write(root, "src/lib.py", "y = 2\n")
    _docs_json(root, deferred=[_DEFER])
    _write(root, "TODO.md", f"# TODO\n{line}\n")

    assert _verdict(_check(root), "TODO.md")[0] == "updated"


def test_todo_absent_at_base_counts_every_line_added(tmp_path):
    root = _repo(tmp_path, todo=False)
    _write(root, "src/lib.py", "y = 2\n")
    _write(root, "TODO.md", "# TODO\n- T-0099: deferred here; ADRs are not measured; "
                            "T-0040 lands\n")
    _docs_json(root, deferred=[_DEFER])

    assert _verdict(_check(root), "TODO.md")[0] == "updated"


# --- the CLI ---------------------------------------------------------------------

def _cli(root, *extra):
    return subprocess.run([sys.executable, _SCRIPT, "--root", str(root), "--ticket", T, *extra],
                          capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)


def test_cli_prints_one_line_per_document_and_not_measured(tmp_path):
    root = _repo(tmp_path)
    _write(root, "plugin/crew/hooks/scripts/app.py", "x = 2\n")
    _bump(root)

    done = _cli(root)

    lines = done.stdout.splitlines()
    assert done.returncode == 1
    assert lines[0].startswith("docs-check T-1: missing - ")
    assert "CHANGELOG.md (crew 1.0.1): MISSING - " in done.stdout
    assert "SECURITY.md: not needed (no security-relevant path changed)" in lines
    assert lines[-1] == "adr, runbooks: not measured"


def test_cli_exit_zero_when_ok_and_two_on_usage(tmp_path):
    root = _repo(tmp_path)
    _write(root, "src/lib.py", "y = 2\n")

    assert _cli(root).returncode == 0
    assert _cli(root, "--bogus").returncode == 2
    assert "SECURITY_PATHS" in _cli(root, "--explain").stdout


def test_check_writes_nothing(tmp_path):
    root = _repo(tmp_path)
    _write(root, "plugin/crew/hooks/scripts/app.py", "x = 2\n")
    # Stat-dirty but unchanged: `git diff` would rewrite .git/index here.
    os.utime(os.path.join(str(root), "README.md"), (1, 1))
    _docs_json(root, reasons={"README.md": "x"})
    before = _snapshot(root)

    for extra in ((), ("--json",), ("--explain",)):
        _cli(root, *extra)

    assert _snapshot(root) == before


# --- the commands: /crew:docs records, implement orders, done verifies -----------

def _command(name):
    with open(os.path.join(_COMMANDS, name), encoding="utf-8") as handle:
        return handle.read()


def test_docs_command_records_decisions_and_runs_the_check():
    text = _command("docs.md")
    assert "argument-hint: \"[ticket id] [--audit]\"" in text
    assert ".work/tickets/$1/docs.json" in text
    assert "crew_docs_check.py --root . --ticket $1" in text


def test_implement_orders_docs_check_before_refresh_and_review():
    text = _command("implement.md")
    step6 = text[text.index("## 6."):text.index("## 7.")]
    marks = ["/crew:docs $1", "crew_docs_check.py", "crew_refresh_check.py",
             "**Then, last, `/crew:review $1`**"]
    at = [step6.find(mark) for mark in marks]
    assert -1 not in at and at == sorted(at), dict(zip(marks, at))


def test_done_docs_check_never_edits():
    text = _command("done.md")
    section = " ".join(text[text.index("## Check 5"):text.index("## On all")].split())
    assert "crew_docs_check.py --root . --ticket \"$1\"" in section
    assert "do not edit a document here" in section.lower()
    assert "stales check 1's receipt" in section
