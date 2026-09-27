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

    def boom(_patterns):
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
