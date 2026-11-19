"""R-04: `crew_paths.py`, machine-owned roots and the one safe recursive delete.

    python3 -m pytest plugin/crew/tests/test_crew_paths.py -q

Every fixture lives under pytest's tmp_path; HOME / USERPROFILE point at a
scratch home, the machine config path and the environment are injected, so
nothing reads or writes the real `~/.claude`. Every must-block case checks
that a sentinel tree outside the run folder (names, contents, modes and the
READONLY attribute) is unchanged.

`paths_mutations.py` reintroduces one bug per row against a named,
unparametrized node here that runs unskipped on the OS the row is applied on.
"""
import json
import ntpath
import os
import posixpath
import shutil
import stat
import subprocess
import sys
import types

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_paths
import crew_worktrees

WIN = os.name == "nt"
LINUX = sys.platform.startswith("linux")
POSIX_ONLY = pytest.mark.skipif(WIN, reason="POSIX-only case")
WINDOWS_ONLY = pytest.mark.skipif(not WIN, reason="Windows-only case")
LINUX_ONLY = pytest.mark.skipif(not LINUX, reason="Linux-only case")
KEY = "myrepo-0a1b2c"
_SCRIPT = os.path.join(context._ROOT, "hooks", "scripts", "crew_paths.py")  # pylint: disable=protected-access
_SCRIPTS = os.path.dirname(_SCRIPT)
_RO = stat.FILE_ATTRIBUTE_READONLY


# ---------------------------------------------------------------- fixtures and helpers

@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    monkeypatch.setenv("USERPROFILE", str(path))
    monkeypatch.delenv("CREW_TEST_ROOT", raising=False)
    return path


@pytest.fixture
def kw(home, tmp_path):
    return {"home": str(home), "machine_config_path": str(tmp_path / "machine.json"), "env": {}}


@pytest.fixture
def root(home):
    return os.path.join(str(home), ".claude", "crew")


def git(cwd, *args):
    done = subprocess.run(["git", "-C", str(cwd), "-c", "user.email=t@example.com", "-c", "user.name=t",
                           "-c", "core.autocrlf=false"] + list(args), capture_output=True, text=True,
                          check=False, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, f"git {args}: {done.stderr}"
    return done.stdout.strip()


def make_repo(path):
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    (path / "a.txt").write_text("a\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "seed")
    return path


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path / "work" / "myrepo")


def link_dir(link, target):
    """A directory link: a symlink on POSIX, a junction on Windows."""
    if WIN:
        import _winapi  # pylint: disable=import-outside-toplevel,import-error
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(str(target), str(link), target_is_directory=True)


def set_ro(path):
    path = str(path)
    if WIN:
        import ctypes  # pylint: disable=import-outside-toplevel
        k32 = ctypes.windll.kernel32
        attrs = k32.GetFileAttributesW(path)
        assert attrs != 0xFFFFFFFF
        assert k32.SetFileAttributesW(path, (attrs | 0x1) & ~0x80)
    else:
        os.chmod(path, 0o555 if os.path.isdir(path) else 0o444)


def is_ro(path):
    st = os.lstat(str(path))
    if WIN:
        return bool(st.st_file_attributes & _RO)
    return stat.S_IMODE(st.st_mode) & 0o222 == 0


def snapshot(top):
    """Names, contents, modes and READONLY of everything at and below `top`."""
    top = str(top)
    st = os.lstat(top)
    out = {".": (stat.S_IMODE(st.st_mode), getattr(st, "st_file_attributes", 0) & _RO, None)}
    for dirpath, dirnames, filenames in os.walk(top):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            st = os.lstat(path)
            content = None
            if stat.S_ISREG(st.st_mode):
                with open(path, "rb") as handle:
                    content = handle.read()
            out[os.path.relpath(path, top)] = (stat.S_IMODE(st.st_mode),
                                               getattr(st, "st_file_attributes", 0) & _RO, content)
    return out


@pytest.fixture
def outside(tmp_path):
    """A sentinel tree outside every crew root, with a read-only file."""
    top = tmp_path / "outside"
    (top / "deep").mkdir(parents=True)
    (top / "keep.txt").write_text("keep\n", encoding="utf-8")
    (top / "deep" / "inner.txt").write_text("inner\n", encoding="utf-8")
    ro = top / "ro.txt"
    ro.write_text("ro\n", encoding="utf-8")
    set_ro(ro)
    return top


def make(kind, kw, **args):
    return crew_paths.make_run_dir(kind, **args, **kw)


def delete(path, run_id, kw, **extra):
    return crew_paths.delete_run_dir(str(path), run_id, **extra, **kw)


def write_record(directory, run_id, kind, path=None, **over):
    record = {"v": 1, "run_id": run_id, "kind": kind,
              "path": os.path.realpath(str(path or directory)), "nonce": "n0"}
    record.update(over)
    target = os.path.join(str(directory), crew_paths.OWNER)
    with open(target + ".tmp", "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
    os.replace(target + ".tmp", target)
    return target


def run_folder(kw, run_id="t1"):
    """A `tests` run folder (the default location) with a small tree."""
    made = make("tests", kw, run_id=run_id)
    path = made["path"]
    os.mkdir(os.path.join(path, "sub"))
    with open(os.path.join(path, "a.txt"), "w", encoding="utf-8") as handle:
        handle.write("a")
    with open(os.path.join(path, "sub", "b.txt"), "w", encoding="utf-8") as handle:
        handle.write("b")
    return made


def assert_refused(result, prefix=None, suffix=None):
    ok, report = result
    assert ok is False, report
    # startswith / endswith, never `in`: a rule quotes paths, and a tmp path
    # carries the test's own name, so a substring check can match any refusal.
    if prefix:
        assert report["rule"].startswith(prefix), report
    if suffix:
        assert report["rule"].endswith(suffix), report
    return report


# ---------------------------------------------------------------- resolver

def test_r1_default_layout(repo, kw, root):
    key = crew_paths.repo_key(str(repo))
    wt = os.path.join(root, "worktrees", key)
    assert crew_paths.worktree(str(repo), "T1", **kw) == os.path.join(wt, "dev-T1")
    assert crew_paths.lane(str(repo), "s1", "T1", **kw) == os.path.join(wt, "lane-s1-T1")
    assert crew_paths.review(str(repo), "T1", 2, "codex", **kw) == os.path.join(root, "review", key, "T1-r2-codex")
    assert crew_paths.scratch(str(repo), "T1", "dev", **kw) == os.path.join(root, "scratch", key, "T1", "dev")
    assert crew_paths.sandbox("S1", **kw) == os.path.join(root, "scratch", "sandbox", "S1")
    assert crew_paths.tests("X1", **kw) == os.path.join(root, "scratch", "tests", "X1")


def test_r1_machine_root_moves_worktree_base(repo, kw, tmp_path):
    base = tmp_path / "wtbase"
    with open(kw["machine_config_path"], "w", encoding="utf-8") as handle:
        json.dump({"worktrees": {"root": str(base)}}, handle)
    assert crew_paths.repo_dir(str(repo), **kw) == os.path.join(str(base), crew_paths.repo_key(str(repo)))


def test_r1_repo_worktrees_root_ignored(repo, kw, root, tmp_path):
    (repo / ".crew").mkdir()
    (repo / ".crew" / "config.json").write_text(
        json.dumps({"worktrees": {"root": str(tmp_path / "repo-wt")}}), encoding="utf-8")
    assert crew_paths.repo_dir(str(repo), **kw) == os.path.join(root, "worktrees", crew_paths.repo_key(str(repo)))
    got = crew_paths.explain(str(repo), **kw)
    assert got["repo_value_ignored"] is True
    assert any("repo value ignored by crew_paths" in line for line in got["lines"]), got["lines"]


def test_r1_machine_config_absent_or_broken(repo, kw, root):
    got = crew_paths.explain(str(repo), **kw)
    assert got["worktree_base"] == os.path.join(root, "worktrees")
    assert got["machine_config"] == "absent"
    with open(kw["machine_config_path"], "w", encoding="utf-8") as handle:
        handle.write("{not json")
    got = crew_paths.explain(str(repo), **kw)
    assert got["worktree_base"] == os.path.join(root, "worktrees")
    assert any("machine config unreadable" in line for line in got["lines"]), got["lines"]


@pytest.mark.parametrize("name", ["my repo", "r\u00e9po", ".hidden", "---"])
def test_r2_leaf_parity(tmp_path, name, monkeypatch):
    monkeypatch.setattr(crew_worktrees, "configured_base", lambda _root: None)
    made = make_repo(tmp_path / "p" / name)
    want = os.path.basename(crew_worktrees.resolve(str(made))["dir"])
    assert crew_paths.repo_key(str(made)) == want


@pytest.mark.parametrize("field,value", [
    ("ticket", ".."), ("ticket", "a/b"), ("ticket", "a\\b"), ("ticket", ""), ("ticket", ".x"),
    ("ticket", "a" * 129), ("ticket", "a..b"), ("round", -1), ("round", True), ("provider", "a b")])
def test_r3_bad_component_refused(repo, kw, field, value):
    args = {"ticket": "T1", "round_no": 0, "provider": "codex"}
    args["round_no" if field == "round" else field] = value
    with pytest.raises(crew_paths.PathsError):
        crew_paths.review(str(repo), args["ticket"], args["round_no"], args["provider"], **kw)
    if field == "ticket":
        with pytest.raises(crew_paths.PathsError):
            crew_paths.scratch(str(repo), value, "dev", **kw)


def test_r3_name_re_is_shared(monkeypatch):
    assert not hasattr(crew_paths, "NAME_RE")
    assert crew_paths.crew_worktrees is crew_worktrees
    assert crew_paths.component_problem("abc") == ""
    monkeypatch.setattr(crew_worktrees, "NAME_RE", __import__("re").compile(r"^$"))
    assert crew_paths.component_problem("abc") != ""


def _test_root_value(which, home, root, tmp_path):
    system = "C:\\Windows\\crewtest" if WIN else "/usr/crewtest"
    return {"relative": "rel/dir", "empty": "", "nul": str(tmp_path / "a\0b"), "system": system,
            "home": str(home), "crew-root": root, "crew-root-ancestor": os.path.dirname(root),
            "in-worktree-base": os.path.join(root, "worktrees", "x")}[which]


@pytest.mark.parametrize("which", ["relative", "empty", "nul", "system", "home", "crew-root",
                                   "crew-root-ancestor", "in-worktree-base"])
def test_r4_test_root_refused(kw, home, root, tmp_path, which):
    kw["env"] = {"CREW_TEST_ROOT": _test_root_value(which, home, root, tmp_path)}
    lay = crew_paths.layout(home=kw["home"], machine_config_path=kw["machine_config_path"], env=kw["env"])
    assert lay["test_root"] is None and lay["test_root_problem"]
    with pytest.raises(crew_paths.PathsError):
        crew_paths.tests("r1", **kw)


def test_r4_test_root_ancestor_of_home_refused(kw, tmp_path):
    kw["env"] = {"CREW_TEST_ROOT": str(tmp_path)}
    with pytest.raises(crew_paths.PathsError):
        crew_paths.tests("r1", **kw)


def test_r4_test_root_inside_review_refused(kw, root):
    for value in (os.path.join(root, "review"), os.path.join(root, "review", KEY)):
        kw["env"] = {"CREW_TEST_ROOT": value}
        with pytest.raises(crew_paths.PathsError):
            crew_paths.tests("r1", **kw)


def test_r4_test_root_inside_scratch_outside_tests_refused(kw, root):
    scratch = os.path.join(root, "scratch")
    for value in (scratch, os.path.join(scratch, "sandbox"), os.path.join(scratch, "sandbox", "x"),
                  os.path.join(scratch, KEY)):
        kw["env"] = {"CREW_TEST_ROOT": value}
        with pytest.raises(crew_paths.PathsError):
            crew_paths.tests("r1", **kw)


def test_r4_test_root_accepted(kw, home, root):
    for value in (os.path.join(str(home), "elsewhere"), os.path.join(root, "scratch", "tests"),
                  os.path.join(root, "scratch", "tests", "ci")):
        kw["env"] = {"CREW_TEST_ROOT": value}
        assert crew_paths.tests("r1", **kw) == os.path.join(value, "r1")


def test_r5_run_folder_per_kind(repo, kw, root, tmp_path):
    key = crew_paths.repo_key(str(repo))
    cases = [
        ("scratch", {"repo": str(repo), "ticket": "T1", "role": "dev"},
         os.path.join(root, "scratch", key, "T1", "dev"), "T1/dev", ()),
        ("review", {"repo": str(repo), "ticket": "T1", "round_no": 1, "provider": "codex"},
         os.path.join(root, "review", key, "T1-r1-codex"), "T1-r1-codex", ("in", "out")),
        ("sandbox", {"run_id": "s1"}, os.path.join(root, "scratch", "sandbox", "s1"), "s1", ("in", "home", "out")),
        ("tests", {"run_id": "t1"}, os.path.join(root, "scratch", "tests", "t1"), "t1", ()),
    ]
    for kind, args, want, run_id, subs in cases:
        made = make(kind, kw, **args)
        assert made["path"] == want and made["run_id"] == run_id
        assert sorted(os.listdir(want)) == sorted((crew_paths.OWNER,) + subs)
        with open(os.path.join(want, crew_paths.OWNER), encoding="utf-8") as handle:
            record = json.load(handle)
        assert (record["kind"], record["run_id"], record["v"]) == (kind, run_id, 1)
        ok, report = delete(want, run_id, kw, nonce=made["nonce"])
        assert ok, report
        assert not os.path.lexists(want)
        assert os.path.isdir(os.path.dirname(want))
    assert os.path.isdir(os.path.join(root, "scratch", key, "T1"))
    assert os.path.isdir(os.path.join(root, "review", key))
    troot = tmp_path / "troot"
    kw["env"] = {"CREW_TEST_ROOT": str(troot)}
    made = make("tests", kw, run_id="t2")
    assert made["path"] == os.path.join(str(troot), "t2")
    assert delete(made["path"], "t2", kw)[0]
    assert troot.is_dir()


def test_r5_exclusive(kw):
    made = make("tests", kw, run_id="t1")
    with pytest.raises(crew_paths.PathsError):
        make("tests", kw, run_id="t1")
    assert os.listdir(made["path"]) == [crew_paths.OWNER]
    with open(os.path.join(made["path"], crew_paths.OWNER), encoding="utf-8") as handle:
        assert json.load(handle)["nonce"] == made["nonce"]


def test_r5_refused_location(kw, root):
    kw["env"] = {"CREW_TEST_ROOT": os.path.join(root, "review")}
    with pytest.raises(crew_paths.PathsError):
        make("tests", kw, run_id="t1")
    assert not os.path.exists(os.path.join(root, "review", "t1"))


# ---------------------------------------------------------------- deletion: must-block

def test_c1_empty_string_is_not_cwd(kw, monkeypatch):
    made = run_folder(kw)
    monkeypatch.chdir(made["path"])
    assert_refused(delete("", made["run_id"], kw), "guard:")
    assert os.path.isfile(os.path.join(made["path"], crew_paths.OWNER))
    assert os.path.isfile(os.path.join(made["path"], "sub", "b.txt"))


@pytest.mark.parametrize("which", ["whitespace", "relative", "nul"])
def test_c1_bad_strings_refused(kw, which):
    made = run_folder(kw)
    value = {"whitespace": "   ", "relative": os.path.join("a", "b"), "nul": made["path"] + "\0"}[which]
    assert_refused(delete(value, made["run_id"], kw), "guard:")
    assert os.path.isfile(os.path.join(made["path"], "a.txt"))


@pytest.mark.parametrize("which", ["slash", "drive", "unc", "home", "crew-root", "worktree-base",
                                   "review", "scratch", "scratch-tests", "scratch-sandbox",
                                   "test-root", "leaf-digest"])
def test_c2_protected_roots_refused(kw, home, root, tmp_path, which):
    troot = tmp_path / "troot"
    troot.mkdir()
    kw["env"] = {"CREW_TEST_ROOT": str(troot)}
    value = {"slash": "/", "drive": "C:\\", "unc": "\\\\server\\share", "home": str(home),
             "crew-root": root, "worktree-base": os.path.join(root, "worktrees"),
             "review": os.path.join(root, "review"), "scratch": os.path.join(root, "scratch"),
             "scratch-tests": os.path.join(root, "scratch", "tests"),
             "scratch-sandbox": os.path.join(root, "scratch", "sandbox"),
             "test-root": str(troot), "leaf-digest": os.path.join(root, "scratch", KEY)}[which]
    assert_refused(delete(value, "x", kw))
    assert troot.is_dir() and home.is_dir()


def test_c2_shared_parent_with_planted_record_refused(repo, kw):
    made = make("scratch", kw, repo=str(repo), ticket="T1", role="dev")
    ticket_dir = os.path.dirname(made["path"])
    write_record(ticket_dir, "T1", "scratch")
    assert_refused(delete(ticket_dir, "T1", kw), "shape:")
    assert os.path.isfile(os.path.join(made["path"], crew_paths.OWNER))
    rev = make("review", kw, repo=str(repo), ticket="T1", round_no=0, provider="codex")
    inner = os.path.join(rev["path"], "in")
    write_record(inner, "in", "review")
    assert_refused(delete(inner, "in", kw), "shape:")
    assert os.path.isdir(inner)


_POSIX_UNDER = ("/bin", "/sbin", "/usr", "/etc", "/lib", "/lib64", "/boot", "/dev", "/proc", "/sys",
                "/run", "/var/run")
_NT_ENV = {"SystemDrive": "C:", "SystemRoot": "C:\\Windows", "ProgramFiles": "C:\\Program Files",
           "ProgramFiles(x86)": "C:\\Program Files (x86)", "ProgramW6432": "C:\\Program Files",
           "ProgramData": "C:\\ProgramData"}


def test_c3_under_list_posix_flavour():
    for path in _POSIX_UNDER:
        assert crew_paths.system_path_problem(path, posixpath, {}), path
        assert crew_paths.system_path_problem(path + "/x", posixpath, {}), path + "/x"


def test_c3_under_list_nt_flavour():
    for name, path in _NT_ENV.items():
        if name == "SystemDrive":
            continue
        assert crew_paths.system_path_problem(path, ntpath, _NT_ENV), path
        assert crew_paths.system_path_problem(path + "\\x", ntpath, _NT_ENV), path + "\\x"


def test_c3_exact_only_list():
    for path in ("/root", "/home", "/tmp", "/var", "/opt", "/srv"):
        assert crew_paths.system_path_problem(path, posixpath, {}), path
        assert not crew_paths.system_path_problem(path + "/u/x", posixpath, {}), path + "/u/x"
    assert crew_paths.system_path_problem("C:\\Users", ntpath, _NT_ENV)
    assert not crew_paths.system_path_problem("C:\\Users\\u\\x", ntpath, _NT_ENV)


def test_c4_planted_record_outside_roots_refused(kw, tmp_path):
    planted = tmp_path / "elsewhere" / "run"
    planted.mkdir(parents=True)
    (planted / "data.txt").write_text("d", encoding="utf-8")
    write_record(planted, "run", "tests")
    assert_refused(delete(planted, "run", kw), "containment:")
    assert (planted / "data.txt").is_file()


def test_c5_record_missing_refused(kw):
    made = run_folder(kw)
    os.unlink(os.path.join(made["path"], crew_paths.OWNER))
    assert_refused(delete(made["path"], made["run_id"], kw), "record:")
    assert os.path.isfile(os.path.join(made["path"], "sub", "b.txt"))


def test_c5_record_wrong_run_id_refused(kw):
    made = run_folder(kw)
    assert_refused(delete(made["path"], "other", kw), "record:")
    assert os.path.isfile(os.path.join(made["path"], "a.txt"))


@pytest.mark.parametrize("which", ["path", "kind", "nonce", "directory", "version", "not-json"])
def test_c5_record_bad_refused(kw, tmp_path, which):
    made = run_folder(kw)
    rec = os.path.join(made["path"], crew_paths.OWNER)
    nonce = None
    if which == "path":
        write_record(made["path"], made["run_id"], "tests", path=str(tmp_path))
    elif which == "kind":
        write_record(made["path"], made["run_id"], "sandbox")
    elif which == "nonce":
        nonce = "wrong"
    elif which == "directory":
        os.unlink(rec)
        os.mkdir(rec)
    elif which == "version":
        write_record(made["path"], made["run_id"], "tests", v=2)
    else:
        with open(rec, "w", encoding="utf-8") as handle:
            handle.write("{not json")
    assert_refused(delete(made["path"], made["run_id"], kw, nonce=nonce), "record:")
    assert os.path.isfile(os.path.join(made["path"], "a.txt"))


def test_c5_record_hard_link_refused(kw, tmp_path):
    made = run_folder(kw)
    os.link(os.path.join(made["path"], crew_paths.OWNER), str(tmp_path / "record-elsewhere"))
    assert_refused(delete(made["path"], made["run_id"], kw), "record:", "has 2 links")
    assert os.path.isfile(os.path.join(made["path"], "a.txt"))
    assert (tmp_path / "record-elsewhere").is_file()


@POSIX_ONLY
def test_c5b_record_symlink_refused_posix(kw, tmp_path):
    made = run_folder(kw)
    rec = os.path.join(made["path"], crew_paths.OWNER)
    elsewhere = tmp_path / "rec"
    elsewhere.mkdir()
    shutil.copy(rec, str(elsewhere / "r.json"))
    os.unlink(rec)
    os.symlink(str(elsewhere / "r.json"), rec)
    assert_refused(delete(made["path"], made["run_id"], kw), "record:")
    assert os.path.isfile(os.path.join(made["path"], "a.txt"))


@POSIX_ONLY
def test_c5b_record_onofollow_isolated_posix(kw, tmp_path, monkeypatch):
    made = run_folder(kw)
    rec = os.path.join(made["path"], crew_paths.OWNER)
    elsewhere = tmp_path / "rec"
    elsewhere.mkdir()
    shutil.copy(rec, str(elsewhere / "r.json"))
    os.unlink(rec)
    os.symlink(str(elsewhere / "r.json"), rec)
    real_lstat = crew_paths._lstat  # pylint: disable=protected-access
    monkeypatch.setattr(crew_paths, "_lstat",
                        lambda p: os.stat(p) if p.endswith(crew_paths.OWNER) else real_lstat(p))
    assert_refused(delete(made["path"], made["run_id"], kw), "record:")
    assert os.path.isfile(os.path.join(made["path"], "a.txt"))


def test_c5b_record_swapped_refused(kw, monkeypatch):
    made = run_folder(kw)
    rec = os.path.join(made["path"], crew_paths.OWNER)
    with open(rec, encoding="utf-8") as handle:
        text = handle.read()

    def swap(record):
        with open(record + ".new", "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(record + ".new", record)

    monkeypatch.setattr(crew_paths, "_after_record_lstat", swap)
    assert_refused(delete(made["path"], made["run_id"], kw), "record:", "changed between its check and its open")
    assert os.path.isfile(os.path.join(made["path"], "a.txt"))


@WINDOWS_ONLY
def test_c5b_record_reparse_injected_windows(kw, monkeypatch):
    made = run_folder(kw)
    real_lstat = crew_paths._lstat  # pylint: disable=protected-access
    calls = []

    def fake(path):
        st = real_lstat(path)
        if not path.endswith(crew_paths.OWNER) or calls:
            return st
        calls.append(path)  # only the ownership check's lstat is faked, never the walk's
        return types.SimpleNamespace(st_mode=st.st_mode, st_dev=st.st_dev, st_ino=st.st_ino,
                                     st_nlink=st.st_nlink, st_reparse_tag=0xA000000C,
                                     st_file_attributes=st.st_file_attributes | stat.FILE_ATTRIBUTE_REPARSE_POINT)

    monkeypatch.setattr(crew_paths, "_lstat", fake)
    assert_refused(delete(made["path"], made["run_id"], kw), "record:", "is a reparse point")
    assert calls, "the record's lstat was never faked"
    assert os.path.isfile(os.path.join(made["path"], "a.txt"))


@WINDOWS_ONLY
def test_c5b_record_real_symlink_windows(kw, tmp_path):
    made = run_folder(kw)
    rec = os.path.join(made["path"], crew_paths.OWNER)
    elsewhere = tmp_path / "r.json"
    shutil.copy(rec, str(elsewhere))
    os.unlink(rec)
    try:
        os.symlink(str(elsewhere), rec)
    except OSError as exc:
        pytest.skip(f"symlink not permitted here: {exc}")
    assert_refused(delete(made["path"], made["run_id"], kw), "record:")
    assert os.path.isfile(os.path.join(made["path"], "a.txt"))


def test_c6_linked_ancestor_allowed(tmp_path):
    real = tmp_path / "real" / "home"
    real.mkdir(parents=True)
    link_dir(tmp_path / "link", tmp_path / "real")
    kw = {"home": str(tmp_path / "link" / "home"), "machine_config_path": str(tmp_path / "m.json"), "env": {}}
    made = run_folder(kw)
    assert made["path"].startswith(str(tmp_path / "link"))
    ok, report = delete(made["path"], made["run_id"], kw)
    assert ok, report
    assert not os.path.lexists(os.path.join(str(real), ".claude", "crew", "scratch", "tests", "t1"))


def _linked_scratch(root, tmp_path, outside_target=False):
    """scratch/KEY/T2/role is a real run folder whose record says run_id
    T1/role; scratch/KEY/T1 links to T2 (or, with outside_target, to a copy
    outside the roots). Returns (path through the link, real folder)."""
    key_dir = os.path.join(root, "scratch", KEY)
    if outside_target:
        real_ticket = tmp_path / "outside-ticket"
    else:
        real_ticket = os.path.join(key_dir, "T2")
    real_role = os.path.join(str(real_ticket), "role")
    os.makedirs(real_role)
    os.makedirs(key_dir, exist_ok=True)
    with open(os.path.join(real_role, "keep.txt"), "w", encoding="utf-8") as handle:
        handle.write("keep")
    write_record(real_role, "T1/role", "scratch")
    link_dir(os.path.join(key_dir, "T1"), real_ticket)
    return os.path.join(key_dir, "T1", "role"), real_role


def test_c6_link_below_root_refused(kw, root, tmp_path):
    path, real_role = _linked_scratch(root, tmp_path, outside_target=True)
    before = snapshot(real_role)
    assert_refused(delete(path, "T1/role", kw))
    assert snapshot(real_role) == before


def test_c6_anchor_isolated(kw, root, tmp_path, monkeypatch):
    path, real_role = _linked_scratch(root, tmp_path)
    monkeypatch.setattr(crew_paths, "_component_problem", lambda *_a: "")
    assert_refused(delete(path, "T1/role", kw), "anchor:")
    assert os.path.isfile(os.path.join(real_role, "keep.txt"))


def test_c6_component_walk_isolated(kw, root, tmp_path, monkeypatch):
    path, real_role = _linked_scratch(root, tmp_path)
    monkeypatch.setattr(crew_paths, "_anchor_problem", lambda *_a: "")
    assert_refused(delete(path, "T1/role", kw), "link walk:")
    assert os.path.isfile(os.path.join(real_role, "keep.txt"))


@POSIX_ONLY
def test_c7_symlink_dir_inside_removed_posix(kw, outside):
    made = run_folder(kw)
    before = snapshot(outside)
    os.symlink(str(outside), os.path.join(made["path"], "sub", "l"), target_is_directory=True)
    ok, report = delete(made["path"], made["run_id"], kw)
    assert snapshot(outside) == before
    assert ok, report
    assert not os.path.lexists(made["path"])


@POSIX_ONLY
def test_c7_symlink_file_inside_removed_posix(kw, outside):
    made = run_folder(kw)
    before = snapshot(outside)
    os.symlink(str(outside / "ro.txt"), os.path.join(made["path"], "f"))
    ok, report = delete(made["path"], made["run_id"], kw)
    assert ok, report
    assert snapshot(outside) == before


@WINDOWS_ONLY
def test_c7_junction_inside_removed_windows(kw, outside):
    made = run_folder(kw)
    before = snapshot(outside)
    link_dir(os.path.join(made["path"], "sub", "j"), outside)
    ok, report = delete(made["path"], made["run_id"], kw)
    assert snapshot(outside) == before
    assert ok, report
    assert not os.path.lexists(made["path"])


@WINDOWS_ONLY
def test_c7_symlink_inside_removed_windows(kw, outside):
    made = run_folder(kw)
    before = snapshot(outside)
    try:
        os.symlink(str(outside), os.path.join(made["path"], "sd"), target_is_directory=True)
        os.symlink(str(outside / "ro.txt"), os.path.join(made["path"], "sf"))
    except OSError as exc:
        pytest.skip(f"symlink not permitted here: {exc}")
    ok, report = delete(made["path"], made["run_id"], kw)
    assert ok, report
    assert snapshot(outside) == before


def test_c7_run_dir_replaced_by_link_refused(kw, root, outside):
    write_record(outside, "t1", "tests")
    before = snapshot(outside)
    tests_dir = os.path.join(root, "scratch", "tests")
    os.makedirs(tests_dir)
    link_dir(os.path.join(tests_dir, "t1"), outside)
    assert_refused(delete(os.path.join(tests_dir, "t1"), "t1", kw))
    assert snapshot(outside) == before


def _dev_seam(monkeypatch, name, phase):
    real = crew_paths._child_dev  # pylint: disable=protected-access

    def fake(st, path, which):
        dev = real(st, path, which)
        return dev + 1 if which == phase and os.path.basename(path) == name else dev

    monkeypatch.setattr(crew_paths, "_child_dev", fake)


def test_c8a_prescan_st_dev_refused(kw, monkeypatch):
    made = run_folder(kw)
    before = snapshot(made["path"])
    _dev_seam(monkeypatch, "sub", "scan")
    assert_refused(delete(made["path"], made["run_id"], kw), "mount crossing at", "(pre-scan)")
    assert snapshot(made["path"]) == before


def test_c8a_walk_st_dev_stops(kw, monkeypatch):
    made = run_folder(kw)
    _dev_seam(monkeypatch, "sub", "walk")
    report = assert_refused(delete(made["path"], made["run_id"], kw), "mount crossing at")
    assert os.path.isfile(os.path.join(made["path"], "sub", "b.txt"))
    assert "removed" in report


_UNSHARE_SCRIPT = r'''
import json, os, subprocess, sys
sys.path.insert(0, sys.argv[1])
import crew_paths
home, mode, outside = sys.argv[2], sys.argv[3], sys.argv[4]
kw = {"home": home, "machine_config_path": os.path.join(home, "none.json"), "env": {}}
made = crew_paths.make_run_dir("tests", run_id="mnt", **kw)
inner = os.path.join(made["path"], "m")
os.mkdir(inner)
if mode == "tmpfs":
    subprocess.run(["mount", "-t", "tmpfs", "tmpfs", inner], check=True)
    with open(os.path.join(inner, "f"), "w") as handle:
        handle.write("x")
else:
    subprocess.run(["mount", "--bind", outside, inner], check=True)
ok, report = crew_paths.delete_run_dir(made["path"], made["run_id"], nonce=made["nonce"], **kw)
print(json.dumps({"ok": ok, "report": report, "inner": os.path.exists(os.path.join(inner, "f")),
                  "source": os.path.exists(os.path.join(outside, "f"))}))
'''


def _unshare(tmp_path, home, mode):
    probe_dir = tmp_path / "probe"
    probe_dir.mkdir()
    probe = subprocess.run(["unshare", "-rm", "sh", "-c", f"mount -t tmpfs tmpfs '{probe_dir}'"],
                           capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)
    if probe.returncode != 0:
        pytest.skip(f"unshare -rm not permitted here: {probe.stderr.strip()}")
    source = tmp_path / "bind-source"
    source.mkdir()
    (source / "f").write_text("source", encoding="utf-8")
    script = tmp_path / "inside.py"
    script.write_text(_UNSHARE_SCRIPT, encoding="utf-8")
    done = subprocess.run(["unshare", "-rm", sys.executable, str(script), _SCRIPTS, str(home), mode, str(source)],
                          capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stderr
    got = json.loads(done.stdout.strip().splitlines()[-1])
    assert (source / "f").read_text(encoding="utf-8") == "source"
    return got


@LINUX_ONLY
def test_c8b_real_tmpfs_linux(tmp_path, home):
    got = _unshare(tmp_path, home, "tmpfs")
    assert got["ok"] is False and got["report"]["rule"].startswith("mount crossing:"), got
    assert got["inner"] is True, got


@LINUX_ONLY
def test_c8b_real_bind_linux(tmp_path, home):
    got = _unshare(tmp_path, home, "bind")
    assert got["ok"] is False and got["report"]["rule"].startswith("mount crossing:"), got
    assert got["source"] is True, got


def _escape(path):
    return "".join({" ": "\\040", "\t": "\\011", "\n": "\\012", "\\": "\\134"}.get(c, c) for c in path)


def _mountinfo(point):
    return ("22 1 8:1 / / rw,relatime shared:1 - ext4 /dev/sda1 rw\n"
            f"36 22 98:0 / {_escape(point)} rw,noatime master:1 - ext3 /dev/root rw,errors=continue\n")


def test_c8c_listed_mount_refused(kw, monkeypatch):
    made = run_folder(kw)
    monkeypatch.setattr(crew_paths, "_is_linux", lambda: True)
    monkeypatch.setattr(crew_paths, "_read_mountinfo",
                        lambda: _mountinfo(os.path.join(os.path.realpath(made["path"]), "sub")))
    assert_refused(delete(made["path"], made["run_id"], kw), "mount crossing:")
    assert os.path.isfile(os.path.join(made["path"], "sub", "b.txt"))


def test_c8c_escaped_space_refused(kw, monkeypatch):
    made = run_folder(kw)
    spaced = os.path.join(made["path"], "a b")
    os.mkdir(spaced)
    monkeypatch.setattr(crew_paths, "_is_linux", lambda: True)
    monkeypatch.setattr(crew_paths, "_read_mountinfo", lambda: _mountinfo(os.path.realpath(spaced)))
    assert_refused(delete(made["path"], made["run_id"], kw), "mount crossing:")
    assert os.path.isdir(spaced)


def test_c8c_reader_raises_refused(kw, monkeypatch):
    made = run_folder(kw)

    def boom():
        raise OSError("mountinfo unreadable (test)")

    monkeypatch.setattr(crew_paths, "_is_linux", lambda: True)
    monkeypatch.setattr(crew_paths, "_read_mountinfo", boom)
    assert_refused(delete(made["path"], made["run_id"], kw), "could not tell")
    assert os.path.isfile(os.path.join(made["path"], "a.txt"))


def test_c8c_unparsable_line_refused(kw, monkeypatch):
    made = run_folder(kw)
    monkeypatch.setattr(crew_paths, "_is_linux", lambda: True)
    monkeypatch.setattr(crew_paths, "_read_mountinfo", lambda: "garbage line\n")
    assert_refused(delete(made["path"], made["run_id"], kw), "could not tell")
    assert os.path.isfile(os.path.join(made["path"], "a.txt"))


_VOLUME = "\\\\?\\Volume{00000000-0000-0000-0000-000000000000}\\"


@WINDOWS_ONLY
def test_c8d_volume_target_injected_windows(kw, outside, monkeypatch):
    made = run_folder(kw)
    junction = os.path.join(made["path"], "j")
    link_dir(junction, outside)
    before = snapshot(made["path"])
    real = crew_paths._readlink  # pylint: disable=protected-access
    monkeypatch.setattr(crew_paths, "_readlink", lambda p: _VOLUME if os.path.basename(p) == "j" else real(p))
    assert_refused(delete(made["path"], made["run_id"], kw), "mount crossing:")
    assert snapshot(made["path"]) == before
    assert os.path.lexists(junction)


def _volume_of(drive):
    if hasattr(os, "listvolumes"):
        for volume in os.listvolumes():
            try:
                mounts = os.listmounts(volume)
            except OSError:
                continue
            if any(m.rstrip("\\").lower() == drive.rstrip("\\").lower() for m in mounts):
                return volume, ""
        return None, f"no volume lists {drive} as a mount"
    done = subprocess.run(["mountvol"], capture_output=True, text=True, check=False)
    lines = [line.strip() for line in done.stdout.splitlines()]
    for i, line in enumerate(lines):
        if line.startswith("\\\\?\\Volume{") and i + 1 < len(lines) and \
                lines[i + 1].rstrip("\\").lower() == drive.rstrip("\\").lower():
            return line, ""
    return None, f"mountvol listed no volume for {drive}"


@WINDOWS_ONLY
def test_c8d_real_volume_junction_windows(kw):
    made = run_folder(kw)
    drive = os.path.splitdrive(os.path.realpath(made["path"]))[0] + "\\"
    volume, why = _volume_of(drive)
    if not volume:
        pytest.skip(f"no volume name can be read: {why}")
    junction = os.path.join(made["path"], "vol")
    done = subprocess.run(["cmd", "/c", "mklink", "/J", junction, volume], capture_output=True, text=True,
                          check=False)
    if done.returncode != 0:
        pytest.skip(f"mklink /J to {volume} failed: {done.stdout.strip()} {done.stderr.strip()}")
    try:
        listing = sorted(os.listdir(drive))
        dry_ok, dry = delete(made["path"], made["run_id"], kw, dry_run=True)
        assert dry_ok is False, f"dry run would have deleted through a volume junction: {dry}"
        assert_refused(delete(made["path"], made["run_id"], kw), "mount crossing:")
        assert os.path.lexists(junction)
        assert sorted(os.listdir(drive)) == listing
    finally:
        if os.path.lexists(junction):
            os.rmdir(junction)


def _swap_to_link(monkeypatch, name, target):
    state = {"done": False}

    def swap(path):
        if os.path.basename(path) == name and not state["done"]:
            os.rename(path, path + "-moved")  # same parent: moving a 0555 dir elsewhere needs its w bit
            link_dir(path, target)
            state["done"] = True

    monkeypatch.setattr(crew_paths, "_before_attr_clear", swap)
    return state


def test_c9_root_replaced_by_link_refused(kw, outside, tmp_path, monkeypatch):
    made = run_folder(kw)
    before = snapshot(outside)

    def swap(path):
        os.rename(path, str(tmp_path / "moved"))
        link_dir(path, outside)

    monkeypatch.setattr(crew_paths, "_after_owner_check", swap)
    assert_refused(delete(made["path"], made["run_id"], kw), "root identity:")
    assert snapshot(outside) == before
    assert (tmp_path / "moved" / "a.txt").is_file()


def test_c9_root_replaced_by_dir_refused(kw, tmp_path, monkeypatch):
    made = run_folder(kw)

    def swap(path):
        os.rename(path, str(tmp_path / "moved"))
        os.mkdir(path)
        shutil.copy(str(tmp_path / "moved" / crew_paths.OWNER), os.path.join(path, crew_paths.OWNER))
        with open(os.path.join(path, "other.txt"), "w", encoding="utf-8") as handle:
            handle.write("other")

    monkeypatch.setattr(crew_paths, "_after_owner_check", swap)
    assert_refused(delete(made["path"], made["run_id"], kw), "root identity:")
    assert os.path.isfile(os.path.join(made["path"], "other.txt"))


def _readonly_tree(top):
    ro = os.path.join(top, "ro")
    nested = os.path.join(ro, "n")
    os.makedirs(nested)
    for path in (os.path.join(ro, "f.txt"), os.path.join(nested, "g.txt")):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("x")
        set_ro(path)
    set_ro(nested)
    set_ro(ro)
    return ro


def test_c10_readonly_tree_removed(kw):
    made = run_folder(kw)
    _readonly_tree(made["path"])
    set_ro(made["path"])
    ok, report = delete(made["path"], made["run_id"], kw)
    assert ok, report
    assert not os.path.lexists(made["path"])


def test_c10_swap_before_attr_clear_refused(kw, tmp_path, monkeypatch):
    target = tmp_path / "outside-ro"
    target.mkdir()
    (target / "t.txt").write_text("t", encoding="utf-8")
    set_ro(target / "t.txt")
    set_ro(target)
    before = snapshot(target)
    made = run_folder(kw)
    _readonly_tree(made["path"])
    state = _swap_to_link(monkeypatch, "ro", target)
    ok, report = delete(made["path"], made["run_id"], kw)
    assert state["done"], "the seam never fired: the read-only dir was not reached"
    assert ok is False, report
    assert snapshot(target) == before
    assert is_ro(target)


def test_c10_hardlinked_readonly_file(kw, tmp_path):
    source = tmp_path / "outside-file"
    source.write_text("x", encoding="utf-8")
    os.chmod(str(source), stat.S_IREAD)
    made = run_folder(kw)
    os.link(str(source), os.path.join(made["path"], "sub", "hl"))
    ok, report = delete(made["path"], made["run_id"], kw)
    if not ok:
        assert report["rule"].startswith("read-only file with 2 links"), report
    else:
        assert not os.path.lexists(made["path"])
    st = os.lstat(str(source))
    assert source.read_text(encoding="utf-8") == "x"
    assert st.st_nlink == (2 if not ok else 1)
    assert is_ro(source), "the outside file lost its read-only flag"


def test_c10_outside_readonly_via_link_unchanged(kw, outside):
    made = run_folder(kw)
    before = snapshot(outside)
    if WIN:
        link_dir(os.path.join(made["path"], "j"), outside)
    else:
        os.symlink(str(outside / "ro.txt"), os.path.join(made["path"], "l"))
    ok, report = delete(made["path"], made["run_id"], kw)
    assert ok, report
    assert snapshot(outside) == before
    assert is_ro(outside / "ro.txt")


@POSIX_ONLY
def test_c10_mode_0000_dir_posix(kw):
    made = run_folder(kw)
    locked = os.path.join(made["path"], "locked")
    os.mkdir(locked)
    with open(os.path.join(locked, "f"), "w", encoding="utf-8") as handle:
        handle.write("f")
    os.chmod(locked, 0)
    try:
        ok, report = delete(made["path"], made["run_id"], kw)
        if os.geteuid() != 0:  # pylint: disable=no-member
            assert ok is False and report["rule"].startswith("could not tell"), f"non-root branch: {report}"
            assert stat.S_IMODE(os.lstat(locked).st_mode) == 0, "non-root branch: mode changed"
            assert os.path.isfile(os.path.join(made["path"], "a.txt")), "non-root branch: something deleted"
        else:
            assert ok, f"root branch: {report}"
            assert not os.path.lexists(made["path"]), "root branch: not removed"
    finally:
        if os.path.lexists(locked):
            os.chmod(locked, 0o755)


# ---------------------------------------------------------------- must-allow

def test_a1_full_tree_removed(kw, root):
    made = run_folder(kw)
    path = made["path"]
    os.makedirs(os.path.join(path, "empty", "deeper"))
    os.makedirs(os.path.join(path, "x", "y", "z"))
    with open(os.path.join(path, "x", "y", "z", "f"), "w", encoding="utf-8") as handle:
        handle.write("f")
    _readonly_tree(path)
    link_dir(os.path.join(path, "x", "internal"), os.path.join(path, "x", "y"))
    ok, report = delete(path, made["run_id"], kw)
    assert ok, report
    assert not os.path.lexists(path)
    assert os.path.isdir(os.path.join(root, "scratch", "tests"))


def test_a2_root_home_layout(tmp_path):
    lay = crew_paths.layout(home="/root", machine_config_path=str(tmp_path / "none.json"), env={},
                            flavour=posixpath)
    good = crew_paths.string_problem(f"/root/.claude/crew/scratch/{KEY}/T1/dev", lay)
    assert good["problem"] == "" and good["kind"] == "scratch", good
    assert crew_paths.string_problem("/root", lay)["problem"]
    assert crew_paths.string_problem("/usr/local/x", lay)["problem"]


@POSIX_ONLY
def test_a2_tmp_home_real_posix(kw):
    made = run_folder(kw)
    ok, report = delete(made["path"], made["run_id"], kw)
    assert ok, report


def test_a3_check_delete_cli(kw, home):
    made = run_folder(kw)
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
    env.pop("CREW_TEST_ROOT", None)
    done = subprocess.run([sys.executable, _SCRIPT, "check-delete", made["path"], "--run-id", made["run_id"]],
                          capture_output=True, text=True, check=False, env=env, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "would delete" in done.stdout
    refused = subprocess.run([sys.executable, _SCRIPT, "check-delete", made["path"], "--run-id", "nope"],
                             capture_output=True, text=True, check=False, env=env, stdin=subprocess.DEVNULL)
    assert refused.returncode == 1 and "would refuse" in refused.stdout, refused.stdout + refused.stderr
    assert os.path.isfile(os.path.join(made["path"], "sub", "b.txt"))
