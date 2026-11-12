"""A repo-layer WRITE from a linked worktree lands in the file reads use (L-0946).

Before: `crew_config.py --set --repo --apply` from a linked worktree with no
`.crew/config.json` of its own refused "no <worktree>/.crew/config.json -
nothing to write into. Run /crew:init ...", while every reader inherited the
main checkout's file (T-0088). Now the writer resolves through the same
`crew_common.repo_config_dir`: the main checkout's file is written and the
output names it and the checkout. Own files still win whole; when git cannot
tell, the write is refused ("could not tell") and nothing is created.

Every case builds a throwaway repository under tmp_path with a linked worktree
(`git worktree add`); nothing reads or writes the real repository's config.
"""
import json
import os

# isort: split
import context  # noqa: F401  pylint: disable=unused-import
import crew_common
import crew_config
import crew_config_files
import crew_config_menu
from review_fixtures import git
from scope_fixtures import make_repo

BASE = {"schema": 1, "tracker": "local", "tickets": {"baseBranch": None}}


def _lane(tmp_path, main_cfg="base"):
    """A main checkout whose `.crew/config.json` is `main_cfg` (`BASE` by
    default, none when None) and a linked worktree with no crew config."""
    main_cfg = BASE if main_cfg == "base" else main_cfg
    main = make_repo(tmp_path, mode=None, name="main")
    if main_cfg is not None:
        _write(main / ".crew" / "config.json", main_cfg)
    git(main, "worktree", "add", "-q", "-b", "lane", str(tmp_path / "wt"))
    return main, tmp_path / "wt"


def _write(path, data):
    text = data if isinstance(data, str) else json.dumps(data, indent=2) + "\n"
    path.write_bytes(text.encode("utf-8"))


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _cli(root, gpath, *extra):
    return crew_config.main(["--root", str(root), "--global-path", str(gpath),
                             "--repo", *extra])


def _same(a, b):
    return os.path.normcase(os.path.realpath(str(a))) == os.path.normcase(
        os.path.realpath(str(b)))


# --- must write: the main checkout's file, named ------------------------------------------

def test_worktree_set_writes_the_main_checkouts_file_and_says_so(tmp_path, capsys):
    main, wt = _lane(tmp_path)
    gpath = tmp_path / "global.json"

    code = _cli(wt, gpath, "--set", 'tickets.baseBranch="develop"', "--apply")
    out, err = capsys.readouterr()

    assert code == 0, err
    assert _read(main / ".crew" / "config.json")["tickets"]["baseBranch"] == "develop"
    assert not (wt / ".crew" / "config.json").exists()
    wrote = next(line for line in out.splitlines() if line.startswith("wrote: "))
    assert "the main checkout" in wrote and "linked worktree" in wrote, wrote
    assert _same(wrote[len("wrote: "):].split(" (the main checkout")[0],
                 main / ".crew" / "config.json"), wrote
    assert "Run /crew:init" not in out + err


def test_worktree_target_resolves_to_main(tmp_path):
    main, wt = _lane(tmp_path)

    path, main_root = crew_config.repo_write_target(str(wt))

    assert _same(path, main / ".crew" / "config.json")
    assert _same(main_root, main)


def test_worktree_dry_run_digest_binds_the_main_file(tmp_path, capsys):
    main, wt = _lane(tmp_path)
    gpath = tmp_path / "global.json"
    assert _cli(wt, gpath, "--set", "tracker=\"jira\"") == 0
    out = capsys.readouterr().out
    assert out.startswith("would write (dry run): ") and "the main checkout" in out
    digest = next(l for l in out.splitlines() if l.startswith("digest: "))[8:]
    assert digest == crew_config_files.digest((main / ".crew" / "config.json").read_bytes())

    assert _cli(wt, gpath, "--set", "tracker=\"jira\"", "--apply", "--expect", digest) == 0
    assert _read(main / ".crew" / "config.json")["tracker"] == "jira"


def test_worktree_unset_removes_from_the_main_file(tmp_path, capsys):
    main, wt = _lane(tmp_path, dict(BASE, verifyGate=True))

    assert _cli(wt, tmp_path / "g.json", "--unset", "verifyGate", "--apply") == 0, \
        capsys.readouterr().err
    assert "verifyGate" not in _read(main / ".crew" / "config.json")
    assert not (wt / ".crew" / "config.json").exists()


def test_worktree_write_backs_up_the_main_file_first(tmp_path):
    main, wt = _lane(tmp_path)
    before = (main / ".crew" / "config.json").read_bytes()

    crew_config.write_repo_config(str(wt), {"tracker": "jira"}, str(tmp_path / "g.json"))

    stamps = crew_config.crew_backup.list_backups(str(main / ".crew" / "config.json"))
    assert stamps, "no backup of the main checkout's file"
    assert crew_config.crew_backup.read_backup(
        str(main / ".crew" / "config.json"), stamps[0]) == before


def test_worktree_menu_save_writes_the_main_file(tmp_path, capsys):
    main, wt = _lane(tmp_path)

    code = crew_config_menu.save(str(wt), {"repo": {"tracker": "jira"}}, True,
                                 str(tmp_path / "g.json"))
    out = capsys.readouterr().out

    assert code == 0
    assert _read(main / ".crew" / "config.json")["tracker"] == "jira"
    assert not (wt / ".crew" / "config.json").exists()
    assert "the main checkout" in out


def test_worktree_rebuild_dry_run_names_the_main_file(tmp_path, capsys):
    main, wt = _lane(tmp_path)

    code = _cli(wt, tmp_path / "g.json", "--rebuild", "--no-profile")
    out = capsys.readouterr().out

    assert code == 0, out
    first = out.splitlines()[0]
    assert "the main checkout" in first, first
    assert _same(first.split(": ", 1)[1].split(" (the main checkout")[0],
                 main / ".crew" / "config.json")


# --- unchanged: the main checkout, a non-git dir, a worktree with its own file -------------

def test_main_checkout_write_is_unchanged(tmp_path, capsys):
    main, _wt = _lane(tmp_path)

    assert _cli(main, tmp_path / "g.json", "--set", 'tracker="jira"', "--apply") == 0
    out = capsys.readouterr().out
    assert _read(main / ".crew" / "config.json")["tracker"] == "jira"
    wrote = next(line for line in out.splitlines() if line.startswith("wrote: "))
    assert "main checkout" not in wrote
    assert crew_config.repo_write_target(str(main))[1] == ""


def test_non_git_dir_writes_its_own_file(tmp_path, capsys):
    root = tmp_path / "plain"
    (root / ".crew").mkdir(parents=True)
    _write(root / ".crew" / "config.json", BASE)

    assert _cli(root, tmp_path / "g.json", "--set", 'tracker="jira"', "--apply") == 0
    assert _read(root / ".crew" / "config.json")["tracker"] == "jira"
    assert "main checkout" not in capsys.readouterr().out


def test_non_git_dir_without_config_still_refuses_as_before(tmp_path, capsys):
    root = tmp_path / "plain"
    root.mkdir()

    assert _cli(root, tmp_path / "g.json", "--set", 'tracker="jira"', "--apply") == 2
    assert "nothing to write into" in capsys.readouterr().err
    assert not (root / ".crew").exists()


def test_worktree_own_config_wins_and_is_written_main_untouched(tmp_path, capsys):
    """Precedence is the reader's (T-0088): own files win whole, so the write
    goes to the worktree's own file and the main checkout's is not touched."""
    main, wt = _lane(tmp_path)
    (wt / ".crew").mkdir(exist_ok=True)
    _write(wt / ".crew" / "config.json", BASE)
    main_before = (main / ".crew" / "config.json").read_bytes()

    assert _cli(wt, tmp_path / "g.json", "--set", 'tracker="jira"', "--apply") == 0
    out = capsys.readouterr().out
    assert _read(wt / ".crew" / "config.json")["tracker"] == "jira"
    assert (main / ".crew" / "config.json").read_bytes() == main_before
    assert "main checkout" not in out


def test_worktree_with_only_crew_json_does_not_write_main(tmp_path, capsys):
    """An own legacy crew.json is an own config to the reader: no inheritance,
    so the writer refuses (no own config.json) rather than writing main."""
    main, wt = _lane(tmp_path)
    (wt / ".crew").mkdir(exist_ok=True)
    _write(wt / ".crew" / "crew.json", {"schema": 1})
    main_before = (main / ".crew" / "config.json").read_bytes()

    assert _cli(wt, tmp_path / "g.json", "--set", 'tracker="jira"', "--apply") == 2
    assert "nothing to write into" in capsys.readouterr().err
    assert (main / ".crew" / "config.json").read_bytes() == main_before
    assert not (wt / ".crew" / "config.json").exists()


# --- must refuse: could not tell, unreadable, digest moved, no main ------------------------

def test_worktree_could_not_tell_refuses_and_creates_nothing(tmp_path, capsys, monkeypatch):
    main, wt = _lane(tmp_path)
    main_before = (main / ".crew" / "config.json").read_bytes()
    monkeypatch.setattr(crew_common, "git_out", lambda *a: None)

    code = _cli(wt, tmp_path / "g.json", "--set", 'tracker="jira"', "--apply")
    err = capsys.readouterr().err

    assert code == 2
    assert "could not tell" in err and "nothing written" in err, err
    assert "Run /crew:init" not in err
    assert not (wt / ".crew" / "config.json").exists()
    assert (main / ".crew" / "config.json").read_bytes() == main_before


def test_could_not_tell_refuses_every_repo_writer(tmp_path, capsys, monkeypatch):
    main, wt = _lane(tmp_path)
    main_before = (main / ".crew" / "config.json").read_bytes()
    monkeypatch.setattr(crew_common, "git_out", lambda *a: None)
    gpath = tmp_path / "g.json"

    assert crew_config_menu.save(str(wt), {"repo": {"tracker": "jira"}}, True,
                                 str(gpath)) == 2
    assert _cli(wt, gpath, "--rebuild", "--no-profile", "--apply") == 2
    assert _cli(wt, gpath, "--restore", "20260101T000000Z", "--apply") == 2
    assert _cli(wt, gpath, "--backups") == 2
    err = capsys.readouterr().err
    assert err.count("could not tell") >= 4, err
    assert not (wt / ".crew" / "config.json").exists()
    assert (main / ".crew" / "config.json").read_bytes() == main_before


def test_worktree_unreadable_main_config_refuses_untouched(tmp_path, capsys):
    main, wt = _lane(tmp_path)
    _write(main / ".crew" / "config.json", "{ not json")

    code = _cli(wt, tmp_path / "g.json", "--set", 'tracker="jira"', "--apply")
    err = capsys.readouterr().err

    assert code == 2
    assert "left untouched" in err and str(os.path.realpath(main)).lower()[:3] in err.lower()
    assert (main / ".crew" / "config.json").read_text(encoding="utf-8") == "{ not json"
    assert not (wt / ".crew" / "config.json").exists()


def test_worktree_digest_mismatch_refuses(tmp_path, capsys):
    main, wt = _lane(tmp_path)
    before = (main / ".crew" / "config.json").read_bytes()

    code = _cli(wt, tmp_path / "g.json", "--set", 'tracker="jira"', "--apply",
                "--expect", "sha256:" + "0" * 64)

    assert code == 2, capsys.readouterr()
    assert (main / ".crew" / "config.json").read_bytes() == before


def test_worktree_whose_main_checkout_is_gone_refuses(tmp_path, capsys):
    """The main checkout moved away (git objects are read-only on Windows, so
    it is renamed rather than deleted): the worktree's `.git` file points at
    nothing, git cannot answer, and the write is refused."""
    main, wt = _lane(tmp_path)
    moved = tmp_path / "moved"
    main.rename(moved)

    code = _cli(wt, tmp_path / "g.json", "--set", 'tracker="jira"', "--apply")
    err = capsys.readouterr().err

    assert code == 2, err
    assert "could not tell" in err, err
    assert not (wt / ".crew" / "config.json").exists()
    assert not main.exists()
    assert _read(moved / ".crew" / "config.json") == BASE


def test_worktree_main_without_config_refuses_and_creates_nothing(tmp_path, capsys):
    main, wt = _lane(tmp_path, None)

    assert _cli(wt, tmp_path / "g.json", "--set", 'tracker="jira"', "--apply") == 2
    assert "nothing to write into" in capsys.readouterr().err
    assert not (wt / ".crew" / "config.json").exists()
    assert not (main / ".crew" / "config.json").exists()
