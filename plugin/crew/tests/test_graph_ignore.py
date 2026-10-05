"""T-0064: a graph build never reads a secrets-denylisted file.

    python3 -m pytest plugin/crew/tests/test_graph_ignore.py -q

`crew_graph_ignore.coverage` lists every file on disk that the repo's secrets
denylist matches and the root `.graphifyignore` does not exclude. Each case
builds a real git repository, because the matching is git's own
(`check-ignore --no-index`), and the question is what that matcher answers.

Must-refuse: an uncovered file (exit 1), and every "could not tell" (exit 2).
Must-allow: the same file once covered, `.env.example`, a Read rule outside
the repository, and a negation that cannot re-include a file whose parent
directory is excluded. `sabotage_refresh.py` mutates the module so that each
refusal can be seen to fail.
"""
import json
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
from crew_fixtures import make_repo

import crew_graph_ignore

HEADER = "# crew: secrets denylist (crew_graph_ignore.py --write)"


def _write(root, rel, text):
    path = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _track(root, *rels):
    subprocess.run(["git", "add", "-f", "--", *rels], cwd=root, check=True,
                   capture_output=True, stdin=subprocess.DEVNULL, timeout=30)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=root, check=True,
                   capture_output=True, stdin=subprocess.DEVNULL, timeout=30)


def _repo(tmp_path, files):
    """A git repo holding `files` ({rel: text}), all committed."""
    root = make_repo(tmp_path)
    for rel, text in files.items():
        _write(root, rel, text)
    if files:
        _track(root, *files)
    return root


def _main(root, *args):
    return crew_graph_ignore.main(["--root", str(root), *args])


def _check(root, capsys, *extra):
    code = _main(root, "--check", *extra)
    return code, capsys.readouterr().out


def _denylisted_config(tmp_path):
    return _repo(tmp_path, {"config/env.php": "<?php $pw = 'x';\n",
                            ".claude/secrets-denylist": "config/\n",
                            "app.py": "def main():\n    pass\n"})


def test_uncovered_denylisted_file_is_named(tmp_path, capsys):
    root = _denylisted_config(tmp_path)

    code, out = _check(root, capsys)

    assert (code, "config/env.php" in out) == (1, True), out


def test_covered_denylisted_file_passes(tmp_path, capsys):
    root = _denylisted_config(tmp_path)
    assert _main(root, "--write") == 0
    capsys.readouterr()

    code, out = _check(root, capsys)

    assert code == 0, out


_SOURCES = {
    "builtin": ({".env": "PW=x\n"}, ".env"),
    "secrets-denylist": ({".claude/secrets-denylist": "secrets/\n",
                          "secrets/token.txt": "t\n"}, "secrets/token.txt"),
    "settings.json": ({".claude/settings.json":
                       json.dumps({"permissions": {"deny": ["Read(./secrets/**)"]}}),
                       "secrets/token.txt": "t\n"}, "secrets/token.txt"),
    "settings.local.json": ({".claude/settings.local.json":
                             json.dumps({"permissions": {"deny": ["Read(./secrets/**)"]}}),
                             "secrets/token.txt": "t\n"}, "secrets/token.txt"),
}


@pytest.mark.parametrize("source", sorted(_SOURCES))
def test_each_source_contributes(tmp_path, capsys, source):
    files, secret = _SOURCES[source]
    root = _repo(tmp_path, files)

    code, out = _check(root, capsys)

    assert (code, secret in out) == (1, True), out


def test_env_example_is_not_denylisted(tmp_path, capsys):
    root = _repo(tmp_path, {".env.example": "PW=\n"})

    code, out = _check(root, capsys)

    assert code == 0, out


def test_gitignore_alone_does_not_cover_a_tracked_file(tmp_path, capsys):
    root = _repo(tmp_path, {".gitignore": ".env\n", ".env": "PW=x\n"})

    code, out = _check(root, capsys)

    assert (code, ".env" in out) == (1, True), out


def test_negation_in_graphifyignore_uncovers(tmp_path, capsys):
    root = _denylisted_config(tmp_path)
    _write(root, ".graphifyignore", "config/*\n!config/env.php\n")

    code, out = _check(root, capsys)

    assert (code, "config/env.php" in out) == (1, True), out


def test_negation_under_an_excluded_parent_stays_covered(tmp_path, capsys):
    """git and graphify 0.9.65 (`detect.py` `_is_ignored`, the parent-exclusion
    walk) both keep a file excluded when its directory is: `!` cannot
    re-include it. Reporting it uncovered would refuse a safe graph."""
    root = _denylisted_config(tmp_path)
    _write(root, ".graphifyignore", "config/\n!config/env.php\n")

    code, out = _check(root, capsys)

    assert code == 0, out


def test_global_excludes_never_count_as_coverage(tmp_path, capsys, monkeypatch):
    """graphify never reads the user's global git excludes, so a pattern
    there must not make a file look excluded by `.graphifyignore`."""
    root = _repo(tmp_path, {".env": "PW=x\n", ".graphifyignore": "vendor/\n"})
    excludes = tmp_path / "global-excludes"
    excludes.write_text(".env\n", encoding="utf-8")
    config = tmp_path / "global-gitconfig"
    config.write_text(f"[core]\n\texcludesFile = {excludes.as_posix()}\n", encoding="utf-8")
    monkeypatch.setattr(crew_graph_ignore, "_GIT_ENV",
                        dict(crew_graph_ignore._GIT_ENV,  # pylint: disable=protected-access
                             GIT_CONFIG_GLOBAL=str(config)))

    code, out = _check(root, capsys)

    assert (code, ".env" in out) == (1, True), out


def test_untracked_and_ignored_files_are_candidates(tmp_path, capsys):
    root = _repo(tmp_path, {".gitignore": ".env\n"})
    _write(root, ".env", "PW=x\n")

    code, out = _check(root, capsys)

    assert (code, ".env" in out) == (1, True), out


def test_out_of_repo_read_rules_are_skipped(tmp_path, capsys):
    rules = ["Read(~/.ssh/**)", "Read(//etc/passwd)"]
    root = _repo(tmp_path, {".claude/settings.json":
                            json.dumps({"permissions": {"deny": rules}})})

    code = _main(root, "--check", "--json")
    data = json.loads(capsys.readouterr().out)

    assert (code, sorted(s["rule"] for s in data["skipped"])) == (0, sorted(rules)), data


@pytest.mark.parametrize("rule,pattern", [
    ("Read(/config/**)", "/config/**"),
    ("Read(./.env)", ".env"),
    ("Read(secrets/**)", "**/secrets/**"),
    ("Read(//**/.env)", "**/.env"),
])
def test_read_rules_translate_to_root_patterns(rule, pattern):
    patterns, skipped, unknown = crew_graph_ignore.translate_rule(rule, "/repo")

    assert (pattern in patterns, skipped, unknown) == (True, None, None), patterns


def test_a_read_rule_naming_a_path_inside_the_repo_absolutely_is_kept():
    patterns, _skipped, _unknown = crew_graph_ignore.translate_rule(
        "Read(//repo/keys/**)", "/repo")

    assert patterns == ["/keys/**"]


def _unreadable_graphifyignore(root):
    _write(root, ".graphifyignore", "vendor/\n")
    os.chmod(os.path.join(str(root), ".graphifyignore"), 0)


def _graphifyignore_directory(root):
    os.makedirs(os.path.join(str(root), ".graphifyignore"))
    _write(root, ".graphifyignore/x", "x\n")


def _nested_graphifyignore(root):
    _write(root, "sub/.graphifyignore", "!*.pem\n")


def _settings(text):
    return lambda root: _write(root, ".claude/settings.json", text)


_UNKNOWNS = {
    "settings-unparseable": _settings("{not json"),
    "settings-deny-not-a-list": _settings(json.dumps({"permissions": {"deny": "Read"}})),
    "graphifyignore-unreadable": _unreadable_graphifyignore,
    "graphifyignore-is-a-directory": _graphifyignore_directory,
    "nested-graphifyignore": _nested_graphifyignore,
    "deny-all-bare": _settings(json.dumps({"permissions": {"deny": ["Read"]}})),
    "deny-all-star": _settings(json.dumps({"permissions": {"deny": ["Read(*)"]}})),
    "deny-all-starstar": _settings(json.dumps({"permissions": {"deny": ["Read(**)"]}})),
    "git-missing": None,
}


@pytest.mark.parametrize("case", sorted(_UNKNOWNS))
def test_unknowns_never_read_as_covered(tmp_path, capsys, case):
    if case == "graphifyignore-unreadable" and (
            sys.platform == "win32" or getattr(os, "geteuid", lambda: 1)() == 0):
        pytest.skip("chmod 000 does not stop root or Windows from reading; "
                    "graphifyignore-is-a-directory covers the unreadable case")
    root = _repo(tmp_path, {"app.py": "x = 1\n"})
    extra = ()
    if case == "git-missing":
        extra = ("--git", str(tmp_path / "no-such-git"))
    else:
        _UNKNOWNS[case](root)

    code, out = _check(root, capsys, *extra)

    assert (code, "unknown" in out) == (2, True), out


def test_write_is_idempotent_and_additive(tmp_path, capsys):
    root = _repo(tmp_path, {".env": "PW=x\n"})
    before = b"# ours\nvendor/\n\n# more\n"
    target = os.path.join(str(root), ".graphifyignore")
    with open(target, "wb") as handle:
        handle.write(before)

    first = _main(root, "--write")
    with open(target, "rb") as handle:
        once = handle.read()
    second = _main(root, "--write")
    with open(target, "rb") as handle:
        twice = handle.read()
    capsys.readouterr()

    assert (first, second, once.startswith(before), once.count(HEADER.encode()),
            b"\r" in once, b"\n.env\n" in once, twice) == (
        0, 0, True, 1, False, True, once), once


def test_write_adds_only_missing_patterns(tmp_path, capsys):
    root = _repo(tmp_path, {".env": "PW=x\n", ".graphifyignore": ".env\n*.pem\n"})

    _main(root, "--write")
    capsys.readouterr()
    with open(os.path.join(str(root), ".graphifyignore"), encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    assert (lines.count(".env"), lines.count("*.pem"), "!.env.example" in lines) == (1, 1, False)


def test_write_never_truncates_on_a_failed_build(tmp_path, capsys, monkeypatch):
    root = _repo(tmp_path, {".env": "PW=x\n", ".graphifyignore": "vendor/\n"})
    target = os.path.join(str(root), ".graphifyignore")

    def boom(*_args):
        raise ValueError("block builder failed")
    monkeypatch.setattr(crew_graph_ignore, "_block", boom)

    code = _main(root, "--write")
    capsys.readouterr()
    with open(target, "rb") as handle:
        after = handle.read()

    assert (code != 0, after) == (True, b"vendor/\n")


def _stat_tree(root):
    out = {}
    for base, dirs, files in os.walk(root):
        for name in dirs + files:
            path = os.path.join(base, name)
            stat = os.lstat(path)
            out[os.path.relpath(path, root)] = (stat.st_mtime_ns, stat.st_size)
    return out


def test_check_is_read_only(tmp_path, capsys):
    root = _denylisted_config(tmp_path)
    before = _stat_tree(root)

    _check(root, capsys)

    assert _stat_tree(root) == before


def test_text_output_names_at_most_ten_paths(tmp_path, capsys):
    root = _repo(tmp_path, {f"k{n:02d}.pem": "k\n" for n in range(13)})

    code, out = _check(root, capsys)

    assert (code, "k09.pem" in out, "k10.pem" in out, "(+3 more)" in out) == (
        1, True, False, True), out


def _symlink(root, target, rel):
    try:
        os.symlink(target, os.path.join(str(root), *rel.split("/")))
    except (OSError, NotImplementedError):
        pytest.skip("this platform or user cannot create symlinks")


def test_a_nested_repository_is_unknown_until_excluded(tmp_path, capsys):
    """git lists a nested repository (or submodule) as a bare `sub/`, never
    its files, so a `.env` inside it was never judged and read as covered."""
    root = _repo(tmp_path, {"app.py": "x = 1\n"})
    sub = os.path.join(str(root), "sub")
    os.makedirs(sub)
    subprocess.run(["git", "init", "-q"], cwd=sub, check=True, capture_output=True,
                   stdin=subprocess.DEVNULL, timeout=30)
    _write(root, "sub/.env", "PW=x\n")

    first, out = _check(root, capsys)
    _write(root, ".graphifyignore", "sub/\n")
    second, again = _check(root, capsys)

    assert (first, "sub/" in out, second) == (2, True, 0), (out, again)


def test_a_symlink_is_judged_by_its_target(tmp_path, capsys):
    root = _repo(tmp_path, {".env": "PW=x\n", ".graphifyignore": ".env\n"})
    _symlink(root, ".env", "notes.txt")

    code, out = _check(root, capsys)

    assert (code, "notes.txt" in out) == (1, True), out


def test_a_symlinked_directory_matches_a_directory_rule(tmp_path, capsys):
    root = _repo(tmp_path, {".claude/secrets-denylist": "config/\n",
                            "real/env.php": "<?php $pw = 'x';\n",
                            ".graphifyignore": "real/\n"})
    _symlink(root, "real", "config")

    code, out = _check(root, capsys)

    assert (code, "config" in out) == (1, True), out


def test_a_symlink_leaving_the_repository_is_unknown(tmp_path, capsys):
    root = _repo(tmp_path, {"app.py": "x = 1\n"})
    outside = tmp_path / "outside.txt"
    outside.write_text("x\n", encoding="utf-8")
    _symlink(root, str(outside), "notes.txt")

    code, out = _check(root, capsys)

    assert (code, "notes.txt" in out) == (2, True), out


@pytest.mark.parametrize("rule,pattern", [
    ("Read(.\\secrets\\**)", "**/secrets/**"),
    ("Read(secrets\\x.txt)", "secrets/x.txt"),
])
def test_windows_separators_in_read_rules(rule, pattern):
    patterns, _skipped, _unknown = crew_graph_ignore.translate_rule(rule, "/repo")

    assert pattern in patterns and not any("\\" in p for p in patterns), patterns


def test_write_covers_a_differently_cased_secret(tmp_path, capsys):
    """The denylist folds case and coverage does not: `--write` must not
    leave a `.ENV` that `--check` still names after it."""
    root = _repo(tmp_path, {".ENV": "PW=x\n", "Prod.PEM": "k\n"})

    before, _out = _check(root, capsys)
    wrote = _main(root, "--write")
    after, out = _check(root, capsys)

    assert (before, wrote, after) == (1, 0, 0), out


def test_write_keeps_the_target_mode(tmp_path, capsys):
    if sys.platform == "win32":
        pytest.skip("Windows has no POSIX permission bits")
    root = _repo(tmp_path, {".env": "PW=x\n", ".graphifyignore": "vendor/\n"})
    target = os.path.join(str(root), ".graphifyignore")
    os.chmod(target, 0o640)

    _main(root, "--write")
    capsys.readouterr()

    assert oct(os.stat(target).st_mode & 0o777) == oct(0o640)


def test_write_goes_through_a_symlinked_graphifyignore(tmp_path, capsys):
    root = _repo(tmp_path, {".env": "PW=x\n", "shared/ignore": "vendor/\n"})
    _symlink(root, os.path.join("shared", "ignore"), ".graphifyignore")

    code = _main(root, "--write")
    capsys.readouterr()
    with open(os.path.join(str(root), "shared", "ignore"), "rb") as handle:
        real = handle.read()

    assert (code, os.path.islink(os.path.join(str(root), ".graphifyignore")),
            b"\n.env\n" in real) == (0, True, True), real


def test_write_refuses_a_graphifyignore_symlinked_outside_the_repository(tmp_path, capsys):
    """Review: --write must not append to (and replace) a file outside the
    repository that a checked-out `.graphifyignore` symlink names."""
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"precious\n")
    root = _repo(tmp_path, {".env": "PW=x\n"})
    _symlink(root, str(outside), ".graphifyignore")

    code = _main(root, "--write")
    out = capsys.readouterr().out

    assert (code, outside.read_bytes(), os.path.islink(os.path.join(str(root), ".graphifyignore")),
            "resolves outside the repository" in out) == (2, b"precious\n", True, True), out


def test_write_keeps_crlf_line_endings(tmp_path, capsys):
    root = _repo(tmp_path, {".env": "PW=x\n"})
    target = os.path.join(str(root), ".graphifyignore")
    with open(target, "wb") as handle:
        handle.write(b"vendor/\r\n")

    _main(root, "--write")
    capsys.readouterr()
    with open(target, "rb") as handle:
        after = handle.read()

    assert (after.count(b"\n"), b"\r\n.env\r\n" in after) == (after.count(b"\r\n"), True), after


def test_a_dangling_symlink_is_unknown(tmp_path, capsys):
    """A link to nothing could later name a secret; until it resolves, what
    graphify would read through it is not known."""
    root = _repo(tmp_path, {"app.py": "x = 1\n"})
    _symlink(root, "no-such-target.txt", "notes.txt")

    code, out = _check(root, capsys)

    assert (code, "unknown" in out, "notes.txt" in out) == (2, True, True), out


_LINE_BREAKS = {"lf": "\n", "cr": "\r", "vt": "\x0b", "ff": "\x0c", "fs": "\x1c",
                "nel": "\x85", "ls": "\u2028", "ps": "\u2029", "tab-inside": "\t",
                "zero-width": "\u200b"}


@pytest.mark.parametrize("case", sorted(_LINE_BREAKS))
def test_write_never_splits_a_line_on_a_hostile_name(tmp_path, capsys, case):
    """`ID_RSA<break>!.env` written as a literal would append an attacker's
    `!.env`. Such a name is never written, stays UNCOVERED and named, and a
    second `--write` changes nothing."""
    name = f"ID_RSA{_LINE_BREAKS[case]}!.env"
    root = _repo(tmp_path, {".env": "PW=x\n", ".graphifyignore": ".env\n"})
    try:
        _write(root, name, "k\n")
    except (OSError, ValueError, UnicodeError):
        pytest.skip(f"this filesystem cannot hold a name with {case}")
    target = os.path.join(str(root), ".graphifyignore")

    first = _main(root, "--write")
    with open(target, "rb") as handle:
        once = handle.read()
    second = _main(root, "--write")
    with open(target, "rb") as handle:
        twice = handle.read()
    out = capsys.readouterr().out

    assert (first, second, b"ID_RSA" in once, b"!" in once, twice == once,
            ascii(name) in out) == (1, 1, False, False, True, True), (once, out)


def _negated_config(tmp_path, ignore):
    root = _denylisted_config(tmp_path)
    _write(root, ".graphifyignore", ignore)
    return root, os.path.join(str(root), ".graphifyignore")


def test_write_reports_a_users_negation_and_does_not_override_it(tmp_path, capsys):
    """Owner decision: a `!` line is the user's choice. `--write` appends the
    patterns that do not cover the path it re-includes (not `config/`, not
    `/config/env.php`), names the line, exits 1, and converges."""
    root, target = _negated_config(tmp_path, "config/*\n\n!config/env.php\n")

    first = _main(root, "--write")
    out = capsys.readouterr().out
    with open(target, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    second = _main(root, "--write")
    capsys.readouterr()
    with open(target, encoding="utf-8") as handle:
        again = handle.read().splitlines()

    assert (first, second, "line 3 (`!config/env.php`) re-includes denylisted "
            "config/env.php; remove that line or accept the exposure" in out,
            "config/" in lines, "/config/env.php" in lines, "*.pem" in lines,
            again == lines) == (1, 1, True, False, False, True, True), (out, lines)


def test_write_never_appends_a_literal_over_a_users_negation(tmp_path, capsys):
    """`.ENV` is denylisted (case folds) and `!.ENV` re-includes it: the
    `/.ENV` literal `--write` adds for a case gap would override that."""
    root = _repo(tmp_path, {".ENV": "PW=x\n", ".graphifyignore": "!.ENV\n"})

    code = _main(root, "--write")
    out = capsys.readouterr().out
    with open(os.path.join(str(root), ".graphifyignore"), encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    assert (code, "/.ENV" in lines, "line 1 (`!.ENV`) re-includes denylisted .ENV" in out) == (
        1, False, True), (out, lines)


def test_write_names_an_unknown_line_and_still_withholds_the_literal(
        tmp_path, capsys, monkeypatch):
    root = _repo(tmp_path, {".ENV": "PW=x\n", ".graphifyignore": "!.ENV\n"})
    monkeypatch.setattr(crew_graph_ignore, "_reincluded",
                        lambda paths, _lines, _git: {p: (None, "!") for p in paths})

    code = _main(root, "--write")
    out = capsys.readouterr().out
    with open(os.path.join(str(root), ".graphifyignore"), encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    assert (code, "/.ENV" in lines, "an unknown line re-includes denylisted .ENV" in out) == (
        1, False, True), (out, lines)


@pytest.mark.parametrize("before,eol", [(b"a\r\nb\nc\n", b"\n"),
                                        (b"a\r\nb\r\nc\n", b"\r\n")])
def test_write_uses_crlf_only_when_most_lines_do(tmp_path, capsys, before, eol):
    root = _repo(tmp_path, {".env": "PW=x\n"})
    target = os.path.join(str(root), ".graphifyignore")
    with open(target, "wb") as handle:
        handle.write(before)

    _main(root, "--write")
    capsys.readouterr()
    with open(target, "rb") as handle:
        block = handle.read()[len(before):]

    assert (b"\r" in block, block.count(eol)) == (eol == b"\r\n", block.count(b"\n")), block


def test_an_unknown_reason_names_a_symlink_escaped(tmp_path, capsys):
    """A name interpolated into the `unknown` reason is escaped: a raw ESC
    or BEL would reach the terminal (here, retitling it)."""
    name = "evil\x1b]0;pwn\x07"
    root = _repo(tmp_path, {"app.py": "x = 1\n"})
    _symlink(root, "no-such-target.txt", name)

    code, out = _check(root, capsys)

    assert (code, "\x1b" in out, "\x07" in out, ascii(name) in out) == (
        2, False, False, True), out


def test_a_non_utf8_name_under_strict_utf8_stdout_is_unknown_not_a_crash(tmp_path):
    """A dangling link named with a byte that is not UTF-8 makes the status
    unknown (exit 2); printing its name must not crash into exit 1, which
    reads as uncovered."""
    root = _repo(tmp_path, {"app.py": "x = 1\n"})
    try:
        os.symlink(b"no-such-target.txt", os.path.join(os.fsencode(str(root)), b"l\xffnk"))
    except (OSError, NotImplementedError, UnicodeError, TypeError):
        pytest.skip("this platform cannot hold a non-UTF-8 symlink name")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")

    done = subprocess.run([sys.executable, crew_graph_ignore.__file__, "--root", str(root),
                           "--check"], capture_output=True, env=env, check=False, timeout=60)

    assert (done.returncode, b"Traceback" in done.stderr, b"l\\udcffnk" in done.stdout) == (
        2, False, True), (done.stdout, done.stderr)


def test_an_unexpected_exception_is_unknown_never_uncovered(tmp_path, capsys, monkeypatch):
    root = _repo(tmp_path, {"app.py": "x = 1\n"})

    def boom(*_args, **_kwargs):
        raise RuntimeError("surprise")
    monkeypatch.setattr(crew_graph_ignore, "coverage", boom)

    code, out = _check(root, capsys)

    assert (code, "graph-ignore: unknown - RuntimeError: surprise" in out) == (2, True), out


def test_write_with_a_negation_and_unjudgeable_paths_writes_nothing(
        tmp_path, capsys, monkeypatch):
    """The documented branch: a `!` line exists and the paths cannot be
    judged, so whether an appended pattern would override it is not known.
    Nothing is written; exit 2."""
    root = _repo(tmp_path, {"a.pem": "k\n", ".graphifyignore": "!a.pem\n"})
    target = os.path.join(str(root), ".graphifyignore")
    with open(target, "rb") as handle:
        before = handle.read()

    def cannot_judge(*_args, **_kwargs):
        raise crew_graph_ignore._Unknown("cannot judge")  # pylint: disable=protected-access
    monkeypatch.setattr(crew_graph_ignore, "_judge", cannot_judge)

    code = _main(root, "--write")
    out = capsys.readouterr().out
    with open(target, "rb") as handle:
        after = handle.read()

    assert (code, after == before, "has a `!` line" in out) == (2, True, True), (out, after)


def test_an_unknown_reason_names_a_nested_repository_escaped(tmp_path, capsys):
    name = "sub\x1b[2J"
    root = _repo(tmp_path, {"app.py": "x = 1\n"})
    subprocess.run(["git", "init", "-q", name], cwd=str(root), check=True,
                   capture_output=True, stdin=subprocess.DEVNULL, timeout=30)

    code, out = _check(root, capsys)

    assert (code, "\x1b" in out, ascii(name + "/") in out) == (2, False, True), out
