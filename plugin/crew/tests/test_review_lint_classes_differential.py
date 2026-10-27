"""The stdlib checker against the pinned semgrep (L-0715 PR B2, Linux CI only).

Both run over the same throwaway copy: PR A's fixtures, a corner-case corpus, and every tracked
`.py`/`.md` file under `plugin scripts docs .crew`. They must agree on (rule, path, line) exactly,
except for the reviewed `KNOWN_DIVERGENCES`. A semgrep that cannot start FAILS (GEN-01); only native
Windows (by OS) and CREW_SKIP_SEMGREP=1 skip, with a message naming the reason.
"""

import json
import pathlib
import shutil
import subprocess

import context  # noqa: F401  pylint: disable=unused-import
import review_lint_classes as rlc
from test_crew_lint_rules import (  # noqa: F401  pylint: disable=unused-import
    FIXTURES,
    RULES,
    TIMEOUT_SECONDS,
    _command,
    _environment,
    semgrep_required,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
TREE_ROOTS = ("plugin", "scripts", "docs", ".crew")

# {(rule id, path): (checker lines, semgrep lines, reason)}. Empty means the two agree on the whole
# tree today. An entry is for a reviewed, deliberate difference only, and must still differ.
KNOWN_DIVERGENCES = {}

PARENTHESISED = (
    "import pathlib\n\n\ndef f(p):\n    t = pathlib.Path(p).read_text()\n    return (\n"
    "        t.splitlines()  # nosemgrep: crew-splitlines-untrusted-text\n    )\n"
)

CORNERS = '''import json
import pathlib
import subprocess
from pathlib import Path


def containers(p, i, done):
    text = pathlib.Path(p).read_text()
    box = [text]
    a = box[0].splitlines()
    d = {"k": text}
    b = d["k"].splitlines()
    c = json.loads(*box)
    for line in text:
        line.splitlines()
    return a, b, c


def reassign(p, flag):
    t = pathlib.Path(p).read_text()
    t = "clean"
    u = Path(p).read_text()
    if flag:
        u = "x"
    return t.splitlines(), u.splitlines()


def shapes(p, i):
    text = pathlib.Path(p).read_text()
    return (
        text.splitlines()[0],
        text.splitlines()[-1],
        text.splitlines()[i],
        text.splitlines()[1:],
        text.splitlines()[:3],
        (text.splitlines() or ["none"])[0],
        len(text.splitlines()),
        sorted(text.splitlines()),
        [x for x in text.splitlines()],
        {x for x in text.splitlines()},
        [text.splitlines() for _ in p],
        (x for x in [1] if text.splitlines()),
    )


def methods(p, helper):
    text = pathlib.Path(p).read_text()
    return text.strip().replace("a", "b").splitlines(), helper(text).splitlines(), " ".join(text).splitlines()


def sources(done, proc, path):
    a = done.stderr.splitlines()
    b = subprocess.check_output(["x"]).splitlines()
    c = path.read_bytes().splitlines()
    d = json.loads(path.read_bytes())
    e = json.loads(open(path).read(), object_pairs_hook=dict)
    f = json.loads("{}", **{})
    return a, b, c, d, e, f
'''

DECORATED = (
    "import pytest\n\n\n@pytest.mark.parametrize('x', [1])\ndef test_decorated(x):\n    print(x)\n\n\n"
    "@pytest.mark.parametrize('check(', [1])\ndef test_decorator_holds_a_check(x):\n    print(x)\n\n\n"
    "def test_plain():\n    print(1)\n"
)


def _semgrep(root):
    (root / ".semgrepignore").write_text("", encoding="utf-8")
    done = subprocess.run(
        _command("--config", str(RULES), "--json", "--no-git-ignore", "."),
        cwd=str(root), capture_output=True, text=True, check=False, timeout=TIMEOUT_SECONDS, env=_environment(),
    )
    assert done.returncode == 0, "semgrep exited " + str(done.returncode) + ": " + done.stderr[-2000:]
    payload = json.loads(done.stdout)
    assert payload["errors"] == [], "semgrep reported errors: " + json.dumps(payload["errors"])[:2000]
    found = {}
    for hit in payload["results"]:
        path = hit["path"][2:] if hit["path"].startswith("./") else hit["path"]
        found.setdefault((hit["check_id"].split(".")[-1], path), []).append(hit["start"]["line"])
    return {key: sorted(lines) for key, lines in found.items()}


def _checker(root):
    paths = sorted(
        str(p.relative_to(root).as_posix()) for p in root.rglob("*") if p.is_file() and p.suffix in (".py", ".md")
    )
    doc = rlc.run(str(RULES), paths)
    assert doc["files"]["aborted"] == [], "the checker could not judge: " + json.dumps(doc["files"]["aborted"])
    found = {}
    for hit in doc["results"]:
        found.setdefault((hit["rule"], hit["path"]), []).append(hit["line"])
    return {key: sorted(lines) for key, lines in found.items()}


def _compare(root, monkeypatch):
    monkeypatch.chdir(root)
    return _checker(root), _semgrep(root)


def _unexpected(checker, semgrep):
    return {
        key: (checker.get(key, []), semgrep.get(key, []))
        for key in set(checker) | set(semgrep)
        if checker.get(key, []) != semgrep.get(key, []) and key not in KNOWN_DIVERGENCES
    }


def test_checker_and_semgrep_agree_on_the_fixtures(tmp_path, monkeypatch, semgrep_required):  # noqa: F811
    root = tmp_path / "fx"
    shutil.copytree(FIXTURES, root)

    checker, semgrep = _compare(root, monkeypatch)

    assert checker, "the fixtures produced no findings at all"
    assert _unexpected(checker, semgrep) == {}


def test_checker_and_semgrep_agree_on_the_corner_cases(tmp_path, monkeypatch, semgrep_required):  # noqa: F811
    root = tmp_path / "corners"
    (root / "tests").mkdir(parents=True)
    (root / "corners.py").write_text(CORNERS, encoding="utf-8")
    (root / "tests" / "test_dec.py").write_text(DECORATED, encoding="utf-8")

    checker, semgrep = _compare(root, monkeypatch)

    assert len(checker[("crew-splitlines-untrusted-text", "corners.py")]) >= 10
    assert _unexpected(checker, semgrep) == {}


def test_checker_and_semgrep_agree_on_the_repo_tree(tmp_path, monkeypatch, semgrep_required):  # noqa: F811
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", *TREE_ROOTS], cwd=str(ROOT), capture_output=True, check=True, timeout=60
    ).stdout.decode("utf-8")
    root = tmp_path / "tree"
    for name in filter(None, listed.split("\0")):
        if name.endswith((".py", ".md")) and (ROOT / name).is_file():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    checker, semgrep = _compare(root, monkeypatch)

    assert len(checker) > 20
    assert _unexpected(checker, semgrep) == {}


def test_known_divergences_are_still_divergent(tmp_path, monkeypatch, semgrep_required):  # noqa: F811
    root = tmp_path / "paren"
    root.mkdir()
    (root / "paren.py").write_text(PARENTHESISED, encoding="utf-8")

    checker, semgrep = _compare(root, monkeypatch)

    assert checker == {}, "the checker honours a comment on the sink line of a parenthesised sink"
    assert semgrep == {("crew-splitlines-untrusted-text", "paren.py"): [6]}


def test_every_known_divergence_names_its_reason_and_both_sides():
    for key, entry in KNOWN_DIVERGENCES.items():
        assert len(key) == 2 and len(entry) == 3 and entry[2].strip() and entry[0] != entry[1], key
