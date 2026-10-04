"""Review metrics resolve the main checkout's `.crew/` from a linked worktree (L-0582).

Before this, `read_metrics`, `crew_standards metric` and `/crew:status` joined
`.crew/metrics.md` to the root they were given, so a lane made with
`git worktree add` read, and with `metric --record` wrote, its own gitignored
copy: rows recorded there were invisible to every reader in the main checkout.
When git cannot name the main checkout, every caller says it could not tell
and reads nothing; none falls back to the worktree's own copy.

Every case builds a throwaway repository under tmp_path and adds a linked
worktree to it with `git worktree add`. The lane's own `.crew/` holds a DECOY
with different counts, so a test that reads the wrong file fails. Nothing here
reads or writes the real repository's `.crew/`.
"""
import ast
import os

import pytest

# isort: split
import context  # pylint: disable=unused-import
import crew_common
import crew_standards as cs
import crew_state
import crew_status
from review_fixtures import git, init_repo
from scope_fixtures import make_repo

SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access

MAIN_ROWS = [("T-1", 2, 1), ("T-2", 0, 1)]
DECOY_ROWS = [("T-9", 9, 9)]


def _rows(crew_dir, rows):
    crew_dir.mkdir(parents=True, exist_ok=True)
    text = "| date | ticket | reviewer | BLOCK | FIX |\n|---|---|---|---|---|\n" + "".join(
        f"| 2026-10-02 | {t} | codex (r1) | {b} | {f} |\n" for t, b, f in rows)
    (crew_dir / "metrics.md").write_text(text, encoding="utf-8")


def _lane(tmp_path, decoy=True, name="wt"):
    """A main checkout holding MAIN_ROWS and a linked worktree of it; the
    worktree's own `.crew/metrics.md` holds DECOY_ROWS unless `decoy` is False."""
    main = tmp_path / "main"
    if not main.exists():
        main = make_repo(tmp_path, mode=None, name="main")
        _rows(main / ".crew", MAIN_ROWS)
    wt = tmp_path / name
    git(main, "worktree", "add", "-q", "-b", name, str(wt))
    if decoy:
        _rows(wt / ".crew", DECOY_ROWS)
    return main, wt


def _blind_git(monkeypatch):
    """git not on PATH, or timing out: `git_out` answers None."""
    monkeypatch.setattr(crew_common, "git_out", lambda *a: None)


def _main_crew(main):
    return os.path.join(os.path.realpath(str(main)), ".crew")


# --- the resolver -----------------------------------------------------------------------

def test_resolver_linked_worktree_names_main_checkout(tmp_path):
    main, wt = _lane(tmp_path)

    assert crew_common.metrics_crew_dir(str(wt)) == (_main_crew(main), "")


def test_resolver_main_checkout_names_its_own(tmp_path):
    main, _wt = _lane(tmp_path)

    assert crew_common.metrics_crew_dir(str(main)) == (os.path.join(str(main), ".crew"), "")


def test_resolver_plain_directory_names_its_own(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()

    assert crew_common.metrics_crew_dir(str(plain)) == (os.path.join(str(plain), ".crew"), "")


def test_resolver_submodule_names_its_own(tmp_path):
    other = init_repo(tmp_path / "other")
    main = make_repo(tmp_path, mode=None, name="main")
    git(main, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(other), "sub")
    sub = str(main / "sub")

    assert crew_common.metrics_crew_dir(sub) == (os.path.join(sub, ".crew"), "")


def test_resolver_unresolvable_git_file_is_could_not_tell(tmp_path):
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / ".git").write_text(f"gitdir: {tmp_path / 'missing'}\n", encoding="utf-8")

    crew_dir, problem = crew_common.metrics_crew_dir(str(broken))

    assert (crew_dir, bool(problem)) == (None, True)


def test_resolver_git_unanswering_is_could_not_tell(tmp_path, monkeypatch):
    _main, wt = _lane(tmp_path)
    _blind_git(monkeypatch)

    crew_dir, problem = crew_common.metrics_crew_dir(str(wt))

    assert (crew_dir, bool(problem)) == (None, True)


def _separate_git_dir_lane(tmp_path):
    """A main checkout made with `git init --separate-git-dir` (its common dir
    is `sep.git`, not `.git`) and a linked worktree of it holding a decoy."""
    main = tmp_path / "main"
    git(tmp_path, "init", "-q", "--separate-git-dir", str(tmp_path / "sep.git"), str(main))
    git(main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i")
    _rows(main / ".crew", MAIN_ROWS)
    wt = tmp_path / "wt"
    git(main, "worktree", "add", "-q", "-b", "wt", str(wt))
    _rows(wt / ".crew", DECOY_ROWS)
    return wt


def _bare_repo_lane(tmp_path):
    """A linked worktree of a bare repository (no main checkout at all),
    holding a decoy."""
    seed = make_repo(tmp_path, mode=None, name="seed")
    bare = tmp_path / "bare.git"
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(bare))
    wt = tmp_path / "wt"
    git(bare, "worktree", "add", "-q", "-b", "wt", str(wt))
    _rows(wt / ".crew", DECOY_ROWS)
    return wt


LAYOUTS = {"separate-git-dir": _separate_git_dir_lane, "bare": _bare_repo_lane}


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_resolver_linked_worktree_without_a_dot_git_common_dir_is_could_not_tell(tmp_path, layout):
    wt = LAYOUTS[layout](tmp_path)

    crew_dir, problem = crew_common.metrics_crew_dir(str(wt))

    assert (crew_dir, bool(problem), crew_common.metrics_md_path(str(wt))[0]) == (
        None, True, None), problem


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_callers_never_read_the_decoy_without_a_dot_git_common_dir(tmp_path, layout):
    wt = LAYOUTS[layout](tmp_path)
    decoy = (wt / ".crew" / "metrics.md").read_bytes()

    health = crew_state.read_metrics(str(wt))
    code, _lines = cs.metric(str(wt), record=True, today="2026-10-02")
    line = crew_status._metrics_line(str(wt))  # pylint: disable=protected-access

    assert (health["verdict"].startswith("could not tell: "), health["rate"], code,
            line.startswith("metrics  could not tell ("),
            (wt / ".crew" / "metrics.md").read_bytes() == decoy) == (
        True, None, 1, True, True), (health, line)


def test_repo_config_resolution_is_unchanged_without_a_dot_git_common_dir(tmp_path):
    """The metrics could-not-tell does not leak into T-0088's config reader:
    such a worktree still reads its own config, as before."""
    wt = _separate_git_dir_lane(tmp_path)

    assert crew_common._main_checkout(str(wt)) == (None, "")  # pylint: disable=protected-access


def test_metrics_md_path_joins_the_resolved_dir(tmp_path):
    main, wt = _lane(tmp_path)

    assert crew_common.metrics_md_path(str(wt)) == (
        os.path.join(_main_crew(main), "metrics.md"), "")


# --- read_metrics -----------------------------------------------------------------------

def _triple(health):
    return health["tickets"], health["findings"], health["rate"]


def test_read_metrics_from_linked_worktree_finds_main_rows(tmp_path):
    _main, wt = _lane(tmp_path)

    assert _triple(crew_state.read_metrics(str(wt))) == (2, 4, 2.0)


def test_read_metrics_from_main_checkout_finds_its_rows(tmp_path):
    main, _wt = _lane(tmp_path)

    assert _triple(crew_state.read_metrics(str(main))) == (2, 4, 2.0)


def test_read_metrics_could_not_tell_is_not_no_data(tmp_path, monkeypatch):
    _main, wt = _lane(tmp_path)
    _blind_git(monkeypatch)

    got = crew_state.read_metrics(str(wt))
    fired = crew_state.evaluate_triggers({"health": got})

    assert (got["verdict"].startswith("could not tell: "), got["rate"], got["tickets"],
            "reviewNotWorking" in fired, "ticketsTooLarge" in fired) == (
        True, None, 0, False, False), got


# --- crew_standards metric --------------------------------------------------------------

def test_standards_metric_from_linked_worktree_reads_main(tmp_path):
    main, wt = _lane(tmp_path)

    code, lines = cs.metric(str(wt))

    assert (code, os.path.join(_main_crew(main), "metrics.md") in lines[0]) == (0, True), lines


def test_standards_metric_record_from_linked_worktree_appends_to_main(tmp_path):
    main, wt = _lane(tmp_path)
    _main, bare_lane = _lane(tmp_path, decoy=False, name="wt2")
    decoy = (wt / ".crew" / "metrics.md").read_bytes()
    main_file = main / ".crew" / "metrics.md"
    before = main_file.read_text(encoding="utf-8").count("\n")

    first, _ = cs.metric(str(wt), record=True, today="2026-10-02")
    second, _ = cs.metric(str(bare_lane), record=True, today="2026-10-02")

    text = main_file.read_text(encoding="utf-8")
    assert (first, second, text.count("\n") - before,
            text.rstrip("\n").split("\n")[-1].startswith("standards-metric 2026-10-02:"),
            (wt / ".crew" / "metrics.md").read_bytes() == decoy,
            (bare_lane / ".crew" / "metrics.md").exists()) == (0, 0, 2, True, True, False)


def test_standards_metric_could_not_tell_exits_1_and_writes_nothing(tmp_path, monkeypatch):
    main, wt = _lane(tmp_path)
    files = (main / ".crew" / "metrics.md", wt / ".crew" / "metrics.md")
    before = [f.read_bytes() for f in files]
    _blind_git(monkeypatch)

    code, lines = cs.metric(str(wt), record=True, today="2026-10-02")

    assert (code, any("could not tell" in line for line in lines),
            [f.read_bytes() for f in files] == before) == (1, True, True), lines


# --- /crew:status -----------------------------------------------------------------------

def test_status_metrics_line_from_linked_worktree_counts_main(tmp_path):
    main, wt = _lane(tmp_path, decoy=False)
    rows = sum(1 for line in (main / ".crew" / "metrics.md").read_text(
        encoding="utf-8").splitlines() if line.strip())
    (wt / ".crew").mkdir(exist_ok=True)

    line = crew_status._metrics_line(str(wt))  # pylint: disable=protected-access

    assert (f"{rows} row(s)" in line, _main_crew(main) in line) == (True, True), line


def test_status_metrics_line_from_linked_worktree_ignores_decoy_count(tmp_path):
    main, wt = _lane(tmp_path)
    rows = sum(1 for line in (main / ".crew" / "metrics.md").read_text(
        encoding="utf-8").splitlines() if line.strip())

    line = crew_status._metrics_line(str(wt))  # pylint: disable=protected-access

    assert line.startswith(f"metrics  {os.path.join(_main_crew(main), 'metrics.md')}: "
                           f"{rows} row(s)"), line


def test_status_metrics_line_could_not_tell(tmp_path, monkeypatch):
    _main, wt = _lane(tmp_path)
    _blind_git(monkeypatch)

    line = crew_status._metrics_line(str(wt))  # pylint: disable=protected-access

    assert line.startswith("metrics  could not tell ("), line


@pytest.mark.parametrize("name", ["metrics.md", "metrics.jsonl"])
def test_status_names_stranded_lane_copy_as_not_counted(tmp_path, name):
    _main, wt = _lane(tmp_path, decoy=False)
    (wt / ".crew").mkdir(exist_ok=True)
    (wt / ".crew" / name).write_text("stranded\n", encoding="utf-8")

    line = crew_status._metrics_line(str(wt))  # pylint: disable=protected-access

    assert (os.path.join(str(wt), ".crew", name) in line, "not counted" in line,
            "\n" in line) == (True, True, False), line


def test_status_has_no_stranded_note_without_a_lane_copy(tmp_path):
    main, wt = _lane(tmp_path, decoy=False)

    lines = [crew_status._metrics_line(str(main)),  # pylint: disable=protected-access
             crew_status._metrics_line(str(wt))]  # pylint: disable=protected-access

    assert [("not counted" in line) for line in lines] == [False, False], lines


# --- nothing joins the metrics file outside the resolver ---------------------------------

METRICS_NAMES = {"metrics.md", "metrics.jsonl"}

# The files allowed to join `.crew` with a metrics file name outside crew_common,
# with the exact count and why. A file listed here but absent is skipped, so
# L-0578's review_metrics.py may land before or after this ticket.
ALLOWED = {
    "crew_migrate.py": (2, "one-time migration of the checkout it is pointed at"),
    "crew_metrics.py": (1, "metrics.jsonl writer, out of L-0582 scope"),
    "review_metrics.py": (1, "L-0578 writer, delegates to crew_common in its follow-up"),
}


def _const(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _metrics_sites(tree):
    """Each `os.path.join(..., ".crew", "metrics.md" | "metrics.jsonl")`. A
    non-constant follower is not counted: it also matches unrelated markers."""
    sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "join":
            args = node.args
            for index, arg in enumerate(args[:-1]):
                if _const(arg) == ".crew" and _const(args[index + 1]) in METRICS_NAMES:
                    sites.append(node.lineno)
    return sites


def test_no_module_opens_metrics_outside_the_resolver():
    found = {}
    for name in sorted(os.listdir(SCRIPTS)):
        if not name.endswith(".py") or name == "crew_common.py":
            continue
        with open(os.path.join(SCRIPTS, name), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        sites = _metrics_sites(tree)
        if sites or name in ALLOWED:
            found[name] = sites

    unrouted = {name: lines for name, lines in found.items()
                if len(lines) != ALLOWED.get(name, (0, ""))[0]}

    assert unrouted == {}
