"""`crew_gitignore.py`: detect the languages in a repo, recommend ignore
patterns from a vendored table, and add the missing ones inside ONE managed
block of the root `.gitignore` -- never touching a line a human wrote.

Every fixture is a real git repository: what a pattern does is measured with
git (`check-ignore`, `ls-files -ci`), so a mocked git would test the mock.
"""
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_gitignore as cg
import crew_ticket

SCRIPT = os.path.join(os.path.dirname(cg.__file__), "crew_gitignore.py")
START = "# crew:gitignore:managed"
END = "# crew:gitignore:end"


def _git(root, *args):
    return subprocess.run(("git",) + args, cwd=root, check=True, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL, timeout=30).stdout


def _repo(tmp_path, files=None, tracked=None, gitignore=None):
    """A real repo. `files` are written (untracked unless in `tracked`);
    `tracked` paths are force-added and committed."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    for rel, body in (files or {}).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    if gitignore is not None:
        (root / ".gitignore").write_bytes(gitignore.encode("utf-8") if isinstance(gitignore, str)
                                          else gitignore)
    _git(root, "add", "README.md")
    for rel in tracked or ():
        _git(root, "add", "-f", rel)
    _git(root, "commit", "-q", "-m", "fixture")
    return root


def _run(root, *args, env=None):
    return subprocess.run([sys.executable, SCRIPT, *args, "--root", str(root)],
                          capture_output=True, text=True, check=False, env=env,
                          stdin=subprocess.DEVNULL, timeout=60)


def _ignored(root, path):
    done = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=root,
                          capture_output=True, check=False)
    return done.returncode == 0


def _human_lines(text):
    lines = text.splitlines(keepends=True)
    if START not in text:
        return lines
    start = next(i for i, line in enumerate(lines) if line.startswith(START))
    end = next(i for i, line in enumerate(lines) if line.startswith(END))
    return lines[:start] + lines[end + 1:]


def _block(text):
    lines = text.splitlines()
    start = lines.index(next(line for line in lines if line.startswith(START)))
    end = lines.index(END)
    return [line for line in lines[start + 1:end] if line and not line.startswith("#")]


# --- Step 1: the table, detection and the git reader ----------------------------------

def test_detects_languages_from_tracked_and_untracked_files_only(tmp_path):
    root = _repo(tmp_path, files={
        "app/x.py": "", "web/package.json": "{}", "src/App/App.csproj": "<Project/>",
        "infra/main.tf": "", "node_modules/pkg/setup.py": "", "vendored/Cargo.toml": ""},
        tracked=["app/x.py", "web/package.json"],
        gitignore="node_modules/\nvendored/\n")

    langs = cg.detect(cg.list_files(str(root))[1])

    assert set(langs) == {"python", "node", "dotnet", "terraform"}
    assert all("node_modules" not in path for paths in langs.values() for path in paths)


def test_anchored_rows_emit_one_pattern_per_manifest_dir(tmp_path):
    root = _repo(tmp_path, files={"src/A/A.csproj": "", "src/B/B.csproj": "", "bin/tool.sh": ""})

    patterns = [c["pattern"] for c in cg.candidates(cg.detect(cg.list_files(str(root))[1]))]

    assert "/src/A/bin/" in patterns and "/src/B/bin/" in patterns
    assert "/src/A/obj/" in patterns and "/src/B/obj/" in patterns
    assert "bin/" not in patterns and "/bin/" not in patterns


def _all_patterns():
    for row in cg.all_rows():
        for pattern in row["patterns"]:
            yield pattern.replace("{dir}", "")


def test_every_manifest_dir_gets_its_anchored_rows_however_many():
    """Review round 2: no cap drops the projects past the 200th."""
    dirs = [f"p{i:03d}/" for i in range(205)]
    langs = {"dotnet": [d + "App.csproj" for d in dirs]}

    pats = {c["pattern"] for c in cg.candidates(langs)}

    assert all(f"/{d}bin/" in pats for d in dirs)


def test_never_emits_crew_or_work_patterns(tmp_path):
    for pattern in _all_patterns():
        bare = pattern.lstrip("!").lstrip("/")
        assert not bare.startswith((".crew", ".work")), pattern
    root = _repo(tmp_path, files={"a.py": "", "web/package.json": "", "x/x.csproj": ""})
    done = _run(root, "apply")
    text = (root / ".gitignore").read_text(encoding="utf-8")
    assert done.returncode == 0, done.stdout + done.stderr
    assert not any(p.lstrip("!/").startswith((".crew", ".work")) for p in _block(text))


def test_render_refuses_a_crew_pattern_even_if_one_reaches_it():
    rows = [{"lang": "x", "reason": "r", "patterns": [".crew/*.log"], "pattern": ".crew/*.log"}]
    assert ".crew" not in cg.render("", rows)


def test_every_row_has_reason_probe_and_provenance():
    assert cg.PROVENANCE["sha"] and len(cg.PROVENANCE["sha"]) == 40
    for row in cg.all_rows():
        assert row["reason"].strip(), row
        assert row["probe"].strip(), row
        assert row["source"].strip(), row
        positives = [p for p in row["patterns"] if not p.startswith("!")]
        assert len(positives) == 1, row


@pytest.mark.parametrize("case", ["not-a-repo", "git-missing", "timeout", "undecodable"])
def test_git_failure_is_unknown_exit_4(tmp_path, monkeypatch, case, capsys):
    if case == "not-a-repo":
        root = tmp_path / "plain"
        root.mkdir()
        (root / "a.py").write_text("", encoding="utf-8")
    else:
        root = _repo(tmp_path, files={"a.py": ""})
    if case == "git-missing":
        monkeypatch.setattr(cg, "GIT", str(tmp_path / "no-such-git"))
    if case == "timeout":
        real = subprocess.run

        def slow(cmd, *a, **k):
            if "ls-files" in cmd:
                raise subprocess.TimeoutExpired(cmd, k.get("timeout"))
            return real(cmd, *a, **k)  # pylint: disable=subprocess-run-check
        monkeypatch.setattr(cg.subprocess, "run", slow)
    if case == "undecodable":
        (root / ".gitignore").write_bytes(b"\xff\xfe__pycache__/\n\x80\n")
    before = (root / ".gitignore").read_bytes() if (root / ".gitignore").exists() else None

    code_check = cg.main(["check", "--root", str(root)])
    out_check = capsys.readouterr().out
    code_apply = cg.main(["apply", "--root", str(root)])
    out_apply = capsys.readouterr().out
    summary = cg.summary(str(root))

    assert (code_check, code_apply) == (4, 4), out_check + out_apply
    assert "unknown " in out_check and "unknown " in out_apply
    assert summary.startswith("unknown (")
    after = (root / ".gitignore").read_bytes() if (root / ".gitignore").exists() else None
    assert after == before


def test_check_ignore_status_other_than_0_or_1_is_unknown(tmp_path, monkeypatch):
    root = _repo(tmp_path, files={"a.py": ""})
    real = subprocess.run

    def broken(cmd, *a, **k):
        if "check-ignore" in cmd:
            return subprocess.CompletedProcess(cmd, 128, "", "fatal: boom")
        return real(cmd, *a, **k)  # pylint: disable=subprocess-run-check
    monkeypatch.setattr(cg.subprocess, "run", broken)

    result = cg.measure(str(root))

    assert result["state"] == "unknown"
    assert "128" in result["reason"]


# --- Step 2: check ----------------------------------------------------------------------

def test_check_reports_missing_and_exits_1(tmp_path):
    root = _repo(tmp_path, files={"app/x.py": ""}, tracked=["app/x.py"])

    done = _run(root, "check")

    assert done.returncode == 1, done.stdout + done.stderr
    assert "detected python (app/x.py)" in done.stdout
    assert "missing __pycache__/ - " in done.stdout
    assert not (root / ".gitignore").exists()


def test_covered_pattern_is_not_added(tmp_path):
    root = _repo(tmp_path, files={"app/x.py": "", "web/package.json": "{}",
                                  "web/.gitignore": "node_modules/\n"},
                 gitignore="__pycache__/\n")

    result = cg.measure(str(root))

    by = {c["pattern"]: c["status"] for c in result["candidates"]}
    assert by["__pycache__/"] == "covered"
    assert by["node_modules/"] == "covered"
    assert by["*.py[cod]"] == "missing"
    cg.main(["apply", "--root", str(root)])
    block = _block((root / ".gitignore").read_text(encoding="utf-8"))
    assert "__pycache__/" not in block and "node_modules/" not in block


def test_global_excludes_file_does_not_count_as_covered(tmp_path, monkeypatch):
    root = _repo(tmp_path, files={"app/x.py": ""})
    excludes = tmp_path / "global-ignore"
    excludes.write_text("__pycache__/\n", encoding="utf-8")
    cfg = tmp_path / "gitconfig"
    cfg.write_text(f"[core]\n\texcludesFile = {excludes}\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    _git(root, "config", "core.excludesFile", str(excludes))  # the repo's local config too
    (root / ".git" / "info" / "exclude").write_text("__pycache__/\n", encoding="utf-8")
    assert _ignored(root, "__pycache__/x.pyc")  # git itself honours it

    result = cg.measure(str(root))

    by = {c["pattern"]: c["status"] for c in result["candidates"]}
    assert by["__pycache__/"] == "missing"


def test_tracked_match_is_added_and_named(tmp_path):
    root = _repo(tmp_path, files={"src/App/App.csproj": "", "src/App/bin/tool.exe": "x"},
                 tracked=["src/App/App.csproj", "src/App/bin/tool.exe"])

    done = _run(root, "apply")

    assert done.returncode == 0, done.stdout + done.stderr
    assert "tracked /src/App/bin/ matches 1 tracked file(s): src/App/bin/tool.exe" in done.stdout
    assert "/src/App/bin/" in _block((root / ".gitignore").read_text(encoding="utf-8"))
    assert "src/App/bin/tool.exe" in _git(root, "ls-files")


@pytest.mark.parametrize("secret", ["certs/server.pem", ".env"])
def test_tracked_secret_is_needs_owner_exit_3(tmp_path, secret):
    root = _repo(tmp_path, files={secret: "s3cret"}, tracked=[secret])

    check = _run(root, "check")
    apply = _run(root, "apply")

    assert check.returncode == 3, check.stdout + check.stderr
    assert f"needs-owner {secret} is tracked and secret-shaped" in check.stdout
    assert apply.returncode == 3, apply.stdout + apply.stderr
    assert secret in _git(root, "ls-files")  # never untracked
    assert cg.summary(str(root)).startswith("owner: ")


def test_conflict_with_human_negation_is_not_added(tmp_path):
    root = _repo(tmp_path, files={"src/App/App.csproj": ""},
                 gitignore="!src/App/bin/keep.txt\n")

    done = _run(root, "apply")

    assert "conflict /src/App/bin/ would override !src/App/bin/keep.txt at .gitignore:1" in done.stdout
    assert "/src/App/bin/" not in _block((root / ".gitignore").read_text(encoding="utf-8"))
    assert "/src/App/obj/" in _block((root / ".gitignore").read_text(encoding="utf-8"))


def test_wildcard_negation_under_candidate_is_conflict(tmp_path):
    root = _repo(tmp_path, files={"src/App/App.csproj": "", "src/App/.gitignore": "!bin/*.keep\n"},
                 tracked=["src/App/.gitignore"])

    result = cg.measure(str(root))

    by = {c["pattern"]: c for c in result["candidates"]}
    assert by["/src/App/bin/"]["status"] == "conflict"
    assert by["/src/App/bin/"]["where"] == "src/App/.gitignore:1"


@pytest.mark.parametrize("negation", ["!src/*/bin/keep.txt", "!src/**", "!*/App/bin/k?ep.txt",
                                      "!src/[A]pp/bin/keep.txt"])
def test_a_wildcard_before_the_directory_is_still_a_conflict(tmp_path, negation):
    """Review round 3: a glob in a segment above the candidate directory is
    compared segment by segment, not truncated."""
    root = _repo(tmp_path, files={"src/App/App.csproj": ""}, gitignore=negation + "\n")

    by = {c["pattern"]: c["status"] for c in cg.measure(str(root))["candidates"]}

    assert by["/src/App/bin/"] == "conflict"


@pytest.mark.parametrize("negation", ["!lib/*/bin/keep.txt", "!src/App/keep.txt", "!src/Other/bin/x"])
def test_a_negation_elsewhere_is_no_conflict(tmp_path, negation):
    root = _repo(tmp_path, files={"src/App/App.csproj": ""}, gitignore=negation + "\n")

    by = {c["pattern"]: c["status"] for c in cg.measure(str(root))["candidates"]}

    assert by["/src/App/bin/"] == "missing"


def test_unanchored_directory_conflicts_with_a_negation_under_a_wildcard(tmp_path):
    root = _repo(tmp_path, files={"a.py": ""}, gitignore="!*/__pycache__/keep.pyc\n")

    by = {c["pattern"]: c["status"] for c in cg.measure(str(root))["candidates"]}

    assert by["__pycache__/"] == "conflict"


def test_unanchored_directory_conflicts_with_a_negation_inside_it(tmp_path):
    root = _repo(tmp_path, files={"a.py": ""}, gitignore="!pkg/__pycache__/keep.pyc\n")

    by = {c["pattern"]: c["status"] for c in cg.measure(str(root))["candidates"]}

    assert by["__pycache__/"] == "conflict"


def test_root_anchored_secret_rule_is_not_covered_for_nested_secrets(tmp_path):
    """Review round 1: `/.env` ignores only the root `.env`; `config/.env`
    stays visible, so the `.env` row is not covered and apply adds it."""
    root = _repo(tmp_path, files={"a.py": ""}, gitignore="/.env\n/.env.*\n/*.pem\n")
    assert not _ignored(root, "config/.env")

    by = {c["pattern"]: c["status"] for c in cg.measure(str(root))["candidates"]}
    assert (by[".env"], by[".env.*"], by["*.pem"]) == ("missing", "missing", "missing")

    cg.main(["apply", "--root", str(root)])
    assert _ignored(root, "config/.env") and _ignored(root, "config/.env.local")
    by = {c["pattern"]: c["status"] for c in cg.measure(str(root))["candidates"]}
    assert (by[".env"], by[".vscode/*"]) == ("covered", "covered")


def test_basename_negation_conflicts_where_a_listed_file_carries_the_name(tmp_path):
    """Review round 1: `!keep.txt` re-includes src/App/bin/keep.txt, which an
    added `/src/App/bin/` would stop git re-including."""
    root = _repo(tmp_path, files={"src/App/App.csproj": "", "src/App/bin/keep.txt": ""},
                 gitignore="!keep.txt\n")

    done = _run(root, "apply")

    assert "conflict /src/App/bin/ would override !keep.txt at .gitignore:1" in done.stdout
    block = _block((root / ".gitignore").read_text(encoding="utf-8"))
    assert "/src/App/bin/" not in block and "/src/App/obj/" in block
    assert not _ignored(root, "src/App/bin/keep.txt")


def test_basename_negation_with_no_file_under_a_candidate_is_no_conflict(tmp_path):
    root = _repo(tmp_path, files={"src/App/App.csproj": "", "docs/keep.txt": ""},
                 gitignore="!keep.txt\n")

    by = {c["pattern"]: c["status"] for c in cg.measure(str(root))["candidates"]}

    assert by["/src/App/bin/"] == "missing"


def test_conflict_left_after_apply_is_not_a_bare_current(tmp_path):
    """Review round 1: a conflict row is not added, so the status line names it
    instead of reading `current`."""
    root = _repo(tmp_path, files={"src/App/App.csproj": ""}, gitignore="!src/App/bin/keep.txt\n")
    cg.main(["apply", "--root", str(root)])

    line = cg.summary(str(root))

    assert line.startswith("current except 1 conflict(s) - /src/App/bin/ would override "
                           "!src/App/bin/keep.txt"), line


def test_check_is_read_only(tmp_path):
    root = _repo(tmp_path, files={"a.py": "", "w/package.json": ""}, gitignore="x/\n")
    snap = {}
    for base, dirs, files in os.walk(root):
        for name in dirs + files:
            st = os.lstat(os.path.join(base, name))
            snap[os.path.join(base, name)] = (st.st_mtime_ns, st.st_size)

    done = _run(root, "check")
    _run(root, "summary")

    after = {}
    for base, dirs, files in os.walk(root):
        for name in dirs + files:
            st = os.lstat(os.path.join(base, name))
            after[os.path.join(base, name)] = (st.st_mtime_ns, st.st_size)
    assert done.returncode == 1
    assert after == snap


# --- Step 3: apply ---------------------------------------------------------------------

HUMAN = "# mine\n*.log\n  leading-space\ntrailing-tab\t\n!keep.log\n\n/build-out/\n"


def test_apply_adds_only_inside_the_managed_block(tmp_path):
    root = _repo(tmp_path, files={"a.py": ""}, gitignore=HUMAN)

    done = _run(root, "apply")

    text = (root / ".gitignore").read_text(encoding="utf-8")
    assert done.returncode == 0, done.stdout + done.stderr
    assert text.startswith(START)
    assert "".join(_human_lines(text)).lstrip("\n") == HUMAN
    assert text.count(START) == 1 and text.splitlines().count(END) == 1
    assert "__pycache__/" in _block(text)
    assert "--- a/.gitignore" in done.stdout and "+__pycache__/" in done.stdout


def test_apply_is_idempotent(tmp_path):
    root = _repo(tmp_path, files={"a.py": "", "w/package.json": ""}, gitignore=HUMAN)
    first = _run(root, "apply")
    before = (root / ".gitignore").read_bytes()

    second = _run(root, "apply")

    assert (first.returncode, second.returncode) == (0, 0), second.stdout
    assert (root / ".gitignore").read_bytes() == before
    assert "+++" not in second.stdout
    assert _run(root, "check").returncode == 0


def test_apply_keeps_previous_block_entries(tmp_path):
    old = f"{START} - old\n# go: gone\n*.test\n{END}\n*.log\n"
    root = _repo(tmp_path, files={"a.py": ""}, gitignore=old)

    _run(root, "apply")

    text = (root / ".gitignore").read_text(encoding="utf-8")
    assert "*.test" in _block(text)
    assert "__pycache__/" in _block(text)
    assert text.endswith(f"{END}\n*.log\n")


def test_apply_creates_gitignore_when_absent(tmp_path):
    root = _repo(tmp_path, files={"a.py": ""})

    done = _run(root, "apply")

    assert done.returncode == 0
    text = (root / ".gitignore").read_text(encoding="utf-8")
    assert text.startswith(START) and text.endswith(END + "\n")


def test_opt_out_line_reports_and_never_writes(tmp_path):
    root = _repo(tmp_path, files={"a.py": ""}, gitignore="*.log\n# crew:gitignore:off\n")
    before = (root / ".gitignore").read_bytes()

    done = _run(root, "apply")
    check = _run(root, "check")

    assert done.returncode == 5, done.stdout
    assert "crew:gitignore:off" in done.stdout and "missing __pycache__/" in done.stdout
    assert check.returncode == 1 and "off " in check.stdout
    assert (root / ".gitignore").read_bytes() == before


@pytest.mark.parametrize("kind", ["symlink", "directory"])
def test_non_regular_gitignore_refuses(tmp_path, kind):
    root = _repo(tmp_path, files={"a.py": "", "other": "*.log\n"})
    if kind == "symlink":
        try:
            os.symlink("other", root / ".gitignore")
        except OSError:
            pytest.skip("symlinks not available")
    else:
        (root / ".gitignore").mkdir()

    done = _run(root, "apply")

    assert done.returncode == 5, done.stdout + done.stderr
    assert "not a regular file" in done.stdout
    assert (root / "other").read_text(encoding="utf-8") == "*.log\n"
    if kind == "symlink":
        assert os.path.islink(root / ".gitignore")
    else:
        assert os.listdir(root / ".gitignore") == []


def test_crlf_and_bom_are_preserved(tmp_path):
    body = "﻿*.log\r\n/out/\r\n".encode("utf-8")
    root = _repo(tmp_path, files={"a.py": ""}, gitignore=body)

    done = _run(root, "apply")

    raw = (root / ".gitignore").read_bytes()
    assert done.returncode == 0, done.stdout + done.stderr
    assert raw.startswith(b"\xef\xbb\xbf" + START.encode())
    assert b"\n" not in raw.replace(b"\r\n", b"")
    assert raw.endswith(b"*.log\r\n/out/\r\n")
    assert _run(root, "apply").returncode == 0
    assert (root / ".gitignore").read_bytes() == raw


def test_write_is_atomic_and_leaves_original_on_failure(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, files={"a.py": ""}, gitignore=HUMAN)
    before = (root / ".gitignore").read_bytes()
    real_render = cg.render

    def boom(*_a, **_k):
        raise RuntimeError("render failed")
    monkeypatch.setattr(cg, "render", boom)
    assert cg.main(["apply", "--root", str(root)]) == 4  # an uncaught error is "could not tell"
    assert "unknown " in capsys.readouterr().out

    assert (root / ".gitignore").read_bytes() == before
    assert sorted(os.listdir(root)) == [".git", ".gitignore", "README.md", "a.py"]

    real_replace = os.replace

    def bad_replace(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(cg, "render", real_render)
    monkeypatch.setattr(cg.os, "replace", bad_replace)
    code = cg.main(["apply", "--root", str(root)])
    monkeypatch.setattr(cg.os, "replace", real_replace)

    assert code == 4
    assert (root / ".gitignore").read_bytes() == before
    assert sorted(os.listdir(root)) == [".git", ".gitignore", "README.md", "a.py"]


@pytest.mark.parametrize("text", [
    f"{START}\n{END}\n{START}\n{END}\n",
    f"{START}\n*.x\n",
    f"{END}\n",
    f"*.log\n{START}\n{END}\n",
])
def test_duplicate_or_unterminated_marker_is_unknown(tmp_path, text):
    root = _repo(tmp_path, files={"a.py": ""}, gitignore=text)

    done = _run(root, "apply")

    assert done.returncode == 4, done.stdout
    assert "unknown " in done.stdout
    assert (root / ".gitignore").read_text(encoding="utf-8") == text


def _ticket(root, touch):
    tdir = root / ".work" / "tickets" / "T-0001"
    tdir.mkdir(parents=True)
    bullets = "".join(f"- `{p}`\n" for p in touch)
    (tdir / "spec.md").write_text(f"# T-0001\n## Touch\n{bullets}", encoding="utf-8")
    crew_ticket.activate(str(root), "T-0001")


def test_apply_refuses_inside_a_ticket_whose_touch_lacks_gitignore(tmp_path):
    root = _repo(tmp_path, files={"a.py": ""}, gitignore="*.log\n")
    _ticket(root, ["src/"])
    before = (root / ".gitignore").read_bytes()

    done = _run(root, "apply")

    assert done.returncode == 5, done.stdout + done.stderr
    assert "T-0001" in done.stdout
    assert (root / ".gitignore").read_bytes() == before


def test_apply_allowed_when_touch_covers_gitignore(tmp_path):
    root = _repo(tmp_path, files={"a.py": ""}, gitignore="*.log\n")
    _ticket(root, [".gitignore", "src/"])

    done = _run(root, "apply")

    assert done.returncode == 0, done.stdout + done.stderr
    assert "__pycache__/" in _block((root / ".gitignore").read_text(encoding="utf-8"))


def test_broken_active_pointer_refuses(tmp_path):
    root = _repo(tmp_path, files={"a.py": ""}, gitignore="*.log\n")
    state = root / ".git" / "crew"
    state.mkdir()
    (state / "active-ticket").write_text("{not json", encoding="utf-8")
    before = (root / ".gitignore").read_bytes()

    done = _run(root, "apply")

    assert done.returncode == 5, done.stdout + done.stderr
    assert (root / ".gitignore").read_bytes() == before


POLICY = """.env
.env.*
!.env.example

.crew/*
!.crew/codemap/
!.crew/endpoints.json
!.crew/verify.json
!.crew/standards.md
.crew/.approved-*
.work/
"""


def test_policy_block_survives_apply(tmp_path):
    root = _repo(tmp_path, files={"a.py": "", ".crew/verify.json": "{}", ".crew/config.json": "{}"},
                 gitignore=POLICY)

    done = _run(root, "apply")

    text = (root / ".gitignore").read_text(encoding="utf-8")
    assert done.returncode == 0, done.stdout + done.stderr
    assert text.endswith("\n" + POLICY)
    assert not _ignored(root, ".crew/verify.json")
    assert _ignored(root, ".crew/config.json")
    block = _block(text)
    assert ".env" not in block and ".env.*" not in block  # covered by the policy block


def test_pattern_overridden_below_the_block_is_reported_not_re_added(tmp_path):
    root = _repo(tmp_path, files={"a.py": ""})
    _run(root, "apply")
    with open(root / ".gitignore", "a", encoding="utf-8") as fh:
        fh.write("!*.pyc\n")
    before = (root / ".gitignore").read_bytes()

    done = _run(root, "apply")

    assert done.returncode == 0, done.stdout
    assert "overridden *.py[cod]" in done.stdout
    assert (root / ".gitignore").read_bytes() == before


# --- review round 1: no exception may exit 1 ("additions pending") ----------------------

def test_unreadable_gitignore_is_unknown_exit_4(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, files={"a.py": ""}, gitignore="*.log\n")
    real_open = open

    def guarded(path, *a, **k):
        if str(path).endswith(".gitignore"):
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, *a, **k)
    monkeypatch.setattr(cg, "open", guarded, raising=False)

    codes = (cg.main(["check", "--root", str(root)]), cg.main(["apply", "--root", str(root)]))

    out = capsys.readouterr().out
    assert codes == (4, 4), out
    assert "unknown .gitignore could not be read: " in out and "Permission denied" in out


def test_unexpected_exception_is_unknown_exit_4(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, files={"a.py": ""})

    def boom(*_a, **_k):
        raise ValueError("surprise")
    monkeypatch.setattr(cg, "measure", boom)

    codes = [cg.main([action, "--root", str(root)]) for action in ("check", "apply", "summary")]

    assert codes == [4, 4, 4]
    assert capsys.readouterr().out.count("unknown ") == 3


@pytest.mark.parametrize("encoding", ["utf-8", "cp1252"])
def test_undecodable_tracked_name_still_reports_owner_exit_3(tmp_path, encoding):
    root = _repo(tmp_path, files={"a.py": ""})
    name = os.fsencode(str(root)) + b"/k\xff.pem"
    with open(name, "wb") as fh:
        fh.write(b"secret")
    subprocess.run([b"git", b"add", b"-f", b"k\xff.pem"], cwd=root, check=True)

    done = subprocess.run([sys.executable, SCRIPT, "check", "--root", str(root)], capture_output=True,
                          check=False, env=dict(os.environ, PYTHONIOENCODING=encoding))

    assert done.returncode == 3, done.stdout + done.stderr
    assert b"needs-owner k" in done.stdout and b"Traceback" not in done.stderr


@pytest.mark.parametrize("template", [".env.example", ".env.sample", ".env.template", ".env.dist",
                                      ".env.defaults"])
def test_tracked_env_template_is_not_a_secret(tmp_path, template):
    root = _repo(tmp_path, files={template: "KEY=\n"}, tracked=[template])

    done = _run(root, "check")

    assert done.returncode != 3, done.stdout
    assert "needs-owner" not in done.stdout


@pytest.mark.parametrize("gitignore", [None, "*.tfstate\n"])
def test_tracked_terraform_state_is_needs_owner_exit_3(tmp_path, gitignore):
    """Review round 4: Terraform state holds secrets; tracked, it goes to the
    owner whether or not .gitignore already covers it."""
    root = _repo(tmp_path, files={"infra/main.tf": "", "infra/terraform.tfstate": "{}"},
                 tracked=["infra/terraform.tfstate"], gitignore=gitignore)

    done = _run(root, "check")

    assert (done.returncode, "needs-owner infra/terraform.tfstate" in done.stdout) == (3, True), done.stdout


def test_tracked_env_local_is_still_a_secret(tmp_path):
    root = _repo(tmp_path, files={".env.local": "KEY=v\n", ".env.sample": "KEY=\n"},
                 tracked=[".env.local", ".env.sample"])

    done = _run(root, "check")

    assert done.returncode == 3, done.stdout
    assert "needs-owner .env.local" in done.stdout and "needs-owner .env.sample" not in done.stdout


def test_line_numbers_follow_git_lf_lines_only(tmp_path):
    """git splits an ignore file on LF alone; a form feed, a lone CR or U+2028
    inside a human line must not shift the line a finding names, nor the block."""
    human = "a\x0cb\rc\u2028d\n!src/App/bin/keep.txt\n"
    root = _repo(tmp_path, files={"src/App/App.csproj": ""}, gitignore=human)

    by = {c["pattern"]: c for c in cg.measure(str(root))["candidates"]}
    assert by["/src/App/bin/"]["where"] == ".gitignore:2"
    assert _run(root, "apply").returncode == 0
    before = (root / ".gitignore").read_bytes()
    assert _run(root, "apply").returncode == 0
    assert (root / ".gitignore").read_bytes() == before
    assert (root / ".gitignore").read_bytes().decode("utf-8").endswith("\n" + human)


def test_rev_parse_refusal_names_what_git_said(tmp_path, monkeypatch):
    root = _repo(tmp_path, files={"a.py": ""})
    real = subprocess.run

    def refused(cmd, *a, **k):
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 128, "", "fatal: detected dubious ownership in repository")
        return real(cmd, *a, **k)  # pylint: disable=subprocess-run-check
    monkeypatch.setattr(cg.subprocess, "run", refused)

    reason = cg.measure(str(root))["reason"]

    assert reason.startswith("could not run git rev-parse: ") and "dubious ownership" in reason
