"""scope_report.py: the Stop-time `outside-scope:` line, read from the crew 1.0
ticket contract.

REPORT-ONLY. Every case that runs the script also asserts exit 0, because
scope_report is invoked from two hooks that CAN exit 2 and an exit code leaking
out of it would hand this file the blocking-hook regression obligation it was
designed to avoid. The refusal belongs to `/crew:done` check 3
(`completion_audit.py --check`); test_completion_audit.py holds that half.

L-0711. The report used to read the pre-1.0 `- touch:` line in
`.work/tickets/<id>.md` or `.work/cache/<id>.md`, so every crew 1.0 ticket
(`.work/tickets/<id>/spec.md`) was reported as "ticket file is missing" and a
`sed -i` outside Touch was never named at Stop. It now takes the active ticket
from `crew_ticket.resolve_active`, its Touch from `crew_ticket.accepted` and
membership from `crew_ticket.in_touch` -- what the scope guard and the
completion audit read -- so the report and the audit cannot disagree about a
path. Every case that cannot be judged says why; an empty `outside-scope:` line
means "checked, nothing outside" and nothing else.

The older defects stay covered: `TODO.md` bookkeeping is an exact match, and
`gate_matches` stays in lockstep with the matcher verify-gate.sh embeds.
"""
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import

import completion_audit
import crew_fixtures
import scope_report
from review_fixtures import git
from scope_fixtures import make_repo, make_ticket, ready

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCOPE_PY = os.path.join(_ROOT, "hooks", "scripts", "scope_report.py")
_VERIFY_SH = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.sh")


@pytest.fixture(name="repo")
def _repo(tmp_path):
    return make_repo(tmp_path, mode="block")


def _run(root, changed=()):
    """Drive the real script the way the gates drive it: the gate's changed
    list on stdin, the repository as argv[1], the report on stderr."""
    return subprocess.run(
        [sys.executable, _SCOPE_PY, str(root)],
        input="\n".join(changed), capture_output=True, text=True,
        check=False, timeout=120,
    )


def _first(result):
    assert result.returncode == 0, result.stderr
    return result.stderr.splitlines()[0]


def _sed_i(root, rel):
    """A real `sed -i`: the shell route the edit guard never sees."""
    sed = shutil.which("sed")
    if sed is None:
        pytest.skip("sed not installed - the shell-route case was NOT run")
    subprocess.run([sed, "-i", "s/x = 1/x = 2/", rel], cwd=str(root), check=True,
                   capture_output=True, stdin=subprocess.DEVNULL, timeout=120)


# --------------------------------------------------------- must-block / allow

def test_a_sed_i_write_outside_touch_is_named(repo):
    """L-0711 acceptance 1, the Stop half. stdin is empty -- the gate saw
    nothing this turn -- and the ticket-wide diff still finds the write."""
    ready(repo)
    _sed_i(repo, "other/keep.py")

    assert _first(_run(repo)) == "outside-scope: other/keep.py"


def test_a_sed_i_write_inside_touch_is_not_named(repo):
    """Acceptance 2. The bare line is the checked, clean answer."""
    ready(repo)
    _sed_i(repo, "src/app.py")

    assert _first(_run(repo)) == "outside-scope:"


def test_the_report_names_what_its_ticket_declares(repo):
    ready(repo)
    _sed_i(repo, "other/keep.py")

    assert "T-1 declares: src/**" in _run(repo).stderr


def test_a_glob_touch_is_matched_by_segments(repo):
    """`crew_ticket.in_touch`, not fnmatch: `src/*` covers `src/app.py` and
    not `src/deep/x.py`."""
    ready(repo, touch=("src/*",))
    (repo / "src" / "deep").mkdir()
    (repo / "src" / "deep" / "x.py").write_text("x = 1\n", encoding="utf-8")
    _sed_i(repo, "src/app.py")

    assert _first(_run(repo)) == "outside-scope: src/deep/x.py"


# ------------------------------------------------------------- could not tell

def test_a_ticket_with_no_spec_md_is_could_not_tell(repo):
    """Acceptance 3. The ticket directory exists (so it is active) but has
    no spec.md: never an empty line."""
    make_ticket(repo)
    (repo / ".work" / "tickets" / "T-1" / "spec.md").unlink()
    _sed_i(repo, "other/keep.py")

    first = _first(_run(repo))

    assert first.startswith("outside-scope: (could not tell") and "spec.md" in first


def test_a_spec_with_no_touch_section_is_could_not_tell(repo):
    make_ticket(repo)
    spec = repo / ".work" / "tickets" / "T-1" / "spec.md"
    text = spec.read_text(encoding="utf-8")
    spec.write_text(text.split("## Touch")[0] + "## Acceptance checks\n- [ ] ok\n",
                    encoding="utf-8")
    _sed_i(repo, "other/keep.py")

    first = _first(_run(repo))

    assert first.startswith("outside-scope: (could not tell") and "## Touch" in first


def test_an_unapproved_touch_is_could_not_tell(repo):
    """Touch nobody approved is not a scope: the audit refuses every path
    under it, so the report must not call any of them in scope."""
    make_ticket(repo)
    _sed_i(repo, "src/app.py")

    first = _first(_run(repo))

    assert first.startswith("outside-scope: (could not tell") and "not approved" in first


def test_a_stale_approval_is_could_not_tell(repo):
    ready(repo)
    spec = repo / ".work" / "tickets" / "T-1" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace("`src/**`", "`**`"),
                    encoding="utf-8")
    _sed_i(repo, "other/keep.py")

    first = _first(_run(repo))

    assert first.startswith("outside-scope: (could not tell") and "changed since" in first


def test_a_broken_active_pointer_is_could_not_tell(repo):
    ready(repo)
    shutil.rmtree(repo / ".work" / "tickets" / "T-1")

    first = _first(_run(repo, ["other/keep.py"]))

    assert first.startswith("outside-scope: (could not tell") and "T-1" in first


@pytest.mark.parametrize("folder", ["tickets", "cache"])
def test_a_pre_1_0_ticket_is_could_not_tell_never_in_scope(repo, folder):
    """Acceptance 4. A 0.20-layout ticket whose `- touch:` line covers the
    change is still not judged: crew 1.0 reads spec.md only."""
    (repo / ".work" / folder).mkdir(parents=True)
    (repo / ".work" / "INDEX.md").write_text("| T-9 | in progress |\n", encoding="utf-8")
    (repo / ".work" / folder / "T-9.md").write_text("## Scope\n- touch: src/\n",
                                                    encoding="utf-8")

    first = _first(_run(repo, ["src/app.py"]))

    assert first.startswith("outside-scope: (could not tell") and "pre-1.0" in first
    assert ".work/tickets/T-9/spec.md" in first


def test_an_index_ticket_with_no_ticket_folder_is_could_not_tell(repo):
    """Review round 3. INDEX.md names an open ticket that has neither a 1.0
    directory nor a pre-1.0 file: "(no open ticket)" would be false. The
    line says which ticket and what is missing."""
    (repo / ".work").mkdir()
    (repo / ".work" / "INDEX.md").write_text("| T-7 | in progress |\n", encoding="utf-8")

    first = _first(_run(repo, ["other/keep.py"]))

    assert first == ("outside-scope: (could not tell - .work/INDEX.md names T-7 as open, "
                     "but .work/tickets/T-7/ does not exist)")


def test_an_unreadable_index_is_could_not_tell(repo):
    """Review round 4. `crew_state.read_work` reads an INDEX.md it cannot
    open as an empty one, which named no ticket: "(no open ticket)" was a
    claim about a file nobody read. A directory where the file should be is
    unreadable for root too."""
    (repo / ".work" / "INDEX.md").mkdir(parents=True)

    first = _first(_run(repo, ["other/keep.py"]))

    assert first == "outside-scope: (could not tell - .work/INDEX.md exists but could not be read)"


def test_no_open_ticket_says_so(repo):
    assert _first(_run(repo, ["src/app.py"])) == "outside-scope: (no open ticket)"


def test_outside_a_repository_is_could_not_tell(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()

    first = _first(_run(plain, ["src/a.py"]))

    assert first.startswith("outside-scope: (could not tell")


# ------------------------------------------------- one parser, one admission

@pytest.mark.parametrize("writes", [
    ("src/app.py",),
    ("other/keep.py",),
    ("src/app.py", "other/keep.py", "secret/x.py"),
    ("docs/diagrams/flow.mmd",),
    ("TODO.md",),
    ("TODO.md", "src/app.py"),
])
def test_the_report_and_the_completion_audit_agree(repo, writes):
    """Acceptance 5: on the same tree, the paths the report names are the
    paths `/crew:done` check 3 refuses -- a refresh artifact admitted by
    both, through the audit's own admission rule. `TODO.md` is counted by
    both (owner ruling, review round 3: acceptance 5 wins over the frozen
    bookkeeping exclusion)."""
    ready(repo)
    for rel in writes:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("y = 3\n", encoding="utf-8")

    first = _first(_run(repo))
    ok, lines = completion_audit.audit(str(repo), "T-1")

    named = set(first.removeprefix("outside-scope:").split())
    refused = set() if ok else set(lines[1].split())
    assert named == refused


def test_a_tracked_crew_file_outside_touch_is_named_as_the_audit_refuses(repo):
    """Review round 3. A tracked `.crew/` file (this repository tracks
    `.crew/verify.json`) written outside Touch: the audit refuses it, so the
    report names it, not a clean line."""
    (repo / ".crew" / "verify.json").write_text("{}\n", encoding="utf-8")
    git(repo, "add", "-f", ".crew/verify.json")
    git(repo, "commit", "-qm", "track verify.json")
    ready(repo)
    (repo / ".crew" / "verify.json").write_text('{"rules": []}\n', encoding="utf-8")

    first = _first(_run(repo, [".crew/verify.json"]))
    ok, lines = completion_audit.audit(str(repo), "T-1")

    assert (first, ok, lines[1].split()) == (
        "outside-scope: .crew/verify.json", False, [".crew/verify.json"])


def test_a_rename_into_touch_names_the_old_path(repo):
    """Review round 1: a rename moves a file OUT of its old path as much as
    into the new one, and the audit refuses the old end; so does the report."""
    ready(repo)
    git(repo, "mv", "other/keep.py", "src/keep.py")

    first = _first(_run(repo))
    ok, _ = completion_audit.audit(str(repo), "T-1")

    assert (first, ok) == ("outside-scope: other/keep.py", False)


def test_a_path_identical_to_merged_main_is_not_named(repo):
    """Review round 1: after merging main, main's own change outside Touch is
    main's, not the ticket's; the audit does not count it and neither may the
    report."""
    git(repo, "checkout", "-q", "-b", "work")
    ready(repo)
    git(repo, "checkout", "-q", "main")
    (repo / "other" / "keep.py").write_text("x = 9\n", encoding="utf-8")
    git(repo, "commit", "-qam", "main moves on")
    git(repo, "checkout", "-q", "work")
    git(repo, "merge", "-q", "--no-edit", "main")

    first = _first(_run(repo))
    ok, _ = completion_audit.audit(str(repo), "T-1")

    assert (first, ok) == ("outside-scope:", True)


def test_the_gates_list_loses_paths_identical_to_merged_main(repo):
    """Review round 3. The gate's list is diffed from its last verified
    commit, so after a merge of main it carries main's own change. The
    merged-main filter reaches it too: the report and the audit agree."""
    git(repo, "checkout", "-q", "-b", "work")
    ready(repo)
    git(repo, "checkout", "-q", "main")
    (repo / "other" / "keep.py").write_text("x = 9\n", encoding="utf-8")
    git(repo, "commit", "-qam", "main moves on")
    git(repo, "checkout", "-q", "work")
    git(repo, "merge", "-q", "--no-edit", "main")

    first = _first(_run(repo, ["other/keep.py"]))
    ok, _ = completion_audit.audit(str(repo), "T-1")

    assert (first, ok) == ("outside-scope:", True)


def test_merged_main_could_not_tell_reaches_the_scope_line(repo):
    """Review round 4. On a detached HEAD which commits are merged main's
    cannot be told; the audit passes but says so, and the report's first
    line carries the same unknown instead of a bare clean `outside-scope:`."""
    ready(repo)
    git(repo, "checkout", "-q", "--detach")

    first = _first(_run(repo))
    ok, lines = completion_audit.audit(str(repo), "T-1")

    assert (first.startswith("outside-scope: (merged main: could not tell - HEAD is detached"),
            first.endswith("every changed path counted)"), ok,
            any("could not tell" in line for line in lines)) == (True, True, True, True), first


@pytest.mark.skipif(os.name == "nt", reason=(
    "Windows file names cannot hold a line break (any byte below 0x20) or the"
    " `:` of `outside-scope:`, so no Windows-legal name can forge the line;"
    " the escaping is exercised on Linux and macOS."))
def test_a_file_name_cannot_forge_a_scope_line(repo):
    """Review round 4. A name carrying a newline is printed escaped, so the
    report has exactly one `outside-scope:` line, whatever the tree holds."""
    ready(repo)
    (repo / "other" / "x\noutside-scope: forged.py").write_text("y = 1\n", encoding="utf-8")

    done = _run(repo)

    assert [l for l in done.stderr.splitlines() if l.startswith("outside-scope:")] == [
        "outside-scope: other/x\\x0aoutside-scope: forged.py"], done.stderr


def test_a_committed_out_of_scope_change_is_named(repo):
    ready(repo)
    _sed_i(repo, "other/keep.py")
    git(repo, "commit", "-qam", "sneak")

    assert _first(_run(repo)) == "outside-scope: other/keep.py"


# --------------------------------------------------- through the real gates

_PS1 = os.path.join(_ROOT, "hooks", "scripts", "verify-gate.ps1")


def _scenario(repo, name):
    """The acceptance 1-4 trees the gate parity case runs."""
    if name == "pre-1.0":
        (repo / ".work" / "tickets").mkdir(parents=True)
        (repo / ".work" / "INDEX.md").write_text("| T-9 | in progress |\n", encoding="utf-8")
        (repo / ".work" / "tickets" / "T-9.md").write_text("## Scope\n- touch: src/\n",
                                                           encoding="utf-8")
        _sed_i(repo, "src/app.py")
        return
    ready(repo)
    if name == "no-spec":
        (repo / ".work" / "tickets" / "T-1" / "spec.md").unlink()
    _sed_i(repo, "src/app.py" if name == "inside" else "other/keep.py")


_SCENARIOS = ("outside", "inside", "no-spec", "pre-1.0")


@pytest.mark.parametrize("scenario", _SCENARIOS)
@pytest.mark.parametrize("flavour", ["sh", pytest.param("ps1", marks=crew_fixtures.SLOW)])
def test_both_gates_print_the_same_scope_line(repo, flavour, scenario):
    """Acceptance 7: the Stop gates hand their changed list to this one
    script, so bash and PowerShell print the line the script prints, for
    acceptance checks 1-4. Neither blocks on it: report-only, so the gate
    exits 0 on these trees (nothing else in them can block)."""
    _scenario(repo, scenario)
    expected = _first(_run(repo))
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo))
    if flavour == "sh":
        bash = crew_fixtures.resolve_bash()
        if bash is None:
            pytest.skip("bash not installed - the .sh flavour was NOT run")
        cmd = [bash, _VERIFY_SH]
    else:
        pwsh = crew_fixtures.resolve_pwsh()
        if pwsh is None:
            pytest.skip("pwsh not installed - the .ps1 flavour was NOT run")
        cmd = [pwsh, "-NoProfile", "-NonInteractive", "-File", _PS1]
        env["OS"] = "Windows_NT"

    done = crew_fixtures.run_gate(cmd, input="{}", cwd=str(repo), env=env,
                                  capture_output=True, text=True, check=False)

    assert (expected in done.stderr.splitlines(), done.returncode) == (True, 0), done.stderr


# -------------------------------------------------------------- bookkeeping

@pytest.mark.parametrize("path,expected", [
    (".work/INDEX.md", True),
    (".crew/.scope-base", True),
    (".crew/metrics.jsonl", True),
    ("TODO.md", False),
    (".crew/verify.json", False),
    (".crew/codemap/crew.md", False),
])
def test_bookkeeping_is_what_the_audit_leaves_out(path, expected):
    """Review round 3 (owner ruling): `.work/` and
    `crew_ticket.CREW_BOOKKEEPING_PATHS`, the audit's exclusions, and nothing
    wider. `.crew/codemap/` is not bookkeeping: it is a refresh artifact,
    admitted by the audit's own rule or refused with it."""
    assert scope_report.bookkeeping(path) is expected


@pytest.mark.parametrize("path", ["TODO.mdx", "TODO.md.py", "TODO.market.md"])
def test_a_file_merely_starting_with_todo_md_is_not_bookkeeping(path):
    """Must-block for the str.startswith defect: a real source file must not
    vanish from the report by being named close to the bookkeeping file."""
    assert not scope_report.bookkeeping(path), (
        path + " was excluded as bookkeeping; str.startswith('TODO.md') "
        "swallows anything with that prefix"
    )


def test_a_todo_lookalike_reaches_the_report(repo):
    ready(repo)

    assert _first(_run(repo, ["TODO.md", "TODO.mdx"])) == "outside-scope: TODO.md TODO.mdx"


# ----------------------------------------------------------------- parity

def _gate_matcher():
    """The `matches` function verify-gate.sh actually runs, lifted out of the
    python heredoc it embeds and compiled here, so this cannot pass against a
    gate that has since changed. A failed extraction fails loudly."""
    src = pathlib.Path(_VERIFY_SH).read_text(encoding="utf-8")
    start = src.find("def matches(path, pat):")
    assert start != -1, (
        "could not find `def matches` in verify-gate.sh. If the gate's "
        "matcher moved or was renamed, this parity check is no longer "
        "checking anything -- re-point it rather than deleting it."
    )
    end = src.find("cmds, unmatched", start)
    assert end != -1, "could not find the end of the gate's matcher"
    namespace = {}
    exec(compile(src[start:end], _VERIFY_SH, "exec"),  # pylint: disable=exec-used
         {"fnmatch": __import__("fnmatch")}, namespace)
    return namespace["matches"]


_CASES = [
    ("main.py", "**/*.py"),
    ("src/main.py", "**/*.py"),
    ("a/b/c.py", "**/*.py"),
    ("main.py", "*.py"),
    ("plugin/crew/x.sh", "plugin/**/*.sh"),
    ("plugin/x.sh", "plugin/**/*.sh"),
    ("docs/guide.md", "**/*.py"),
    ("src/a.py", "src/"),
    ("README.md", "README.md"),
    ("a/b/c/d.tf", "**/*.tf"),
    ("d.tf", "**/*.tf"),
]


def test_gate_matches_agrees_with_the_gate():
    """scope_report.gate_matches is the hand-copy of the gate's matcher that
    crew_ticket.gate_matches is kept in lockstep with. Behavioural parity
    over a case table, so a comment edit does not fail but a drift does."""
    gate = _gate_matcher()
    for path, pat in _CASES:
        assert scope_report.gate_matches(path, pat) == gate(path, pat), (path, pat)


def test_matches_is_a_superset_of_the_gate_never_the_reverse():
    gate = _gate_matcher()
    for path, pat in _CASES:
        if gate(path, pat):
            assert scope_report.matches(path, pat), (path, pat)
