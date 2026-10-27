"""The stdlib checker for the review-finding rule classes (L-0715 PR B2).

Positives are PR A's fixtures COPIED out of `plugin/crew/lint/semgrep/fixtures/` (every rule excludes
that directory, so the originals are skipped by scope) plus inline cases. Every case is also run with
CRLF endings and a BOM. A checker that cannot judge a file must say so (an `aborted` row or exit 2),
never report it clean (GEN-01).
"""
# The case tables hold one source snippet per row; wrapping them hides what each row is.
# pylint: disable=line-too-long

import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_lint_classes as rlc
import review_lint_rules as rlr

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "plugin" / "crew" / "hooks" / "scripts" / "review_lint_classes.py"
REAL = ROOT / "plugin" / "crew" / "lint" / "semgrep" / "crew-classes.yml"
FIXTURES = ROOT / "plugin" / "crew" / "lint" / "semgrep" / "fixtures"
BASE = REAL.read_text(encoding="utf-8")

SPLIT, JSON, BARE, ROOT_RULE, NOASSERT = (
    "crew-splitlines-untrusted-text",
    "crew-json-duplicate-keys",
    "crew-bare-interpreter",
    "crew-unquoted-plugin-root",
    "crew-test-no-assertion",
)
IDS = (SPLIT, JSON, BARE, ROOT_RULE, NOASSERT)


def _write(tmp_path, files):
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return list(files)


def _check(tmp_path, monkeypatch, files, skip=(), rules=REAL):
    monkeypatch.chdir(tmp_path)
    return rlc.run(str(rules), _write(tmp_path, files), skip)


def _lines(doc, rule, path=None):
    return sorted(r["line"] for r in doc["results"] if r["rule"] == rule and (path is None or r["path"] == path))


def _mutated(tmp_path, old, new, name="rules.yml"):
    assert BASE.count(old) >= 1, "mutation anchor moved in crew-classes.yml: " + repr(old)
    path = tmp_path / name
    path.write_bytes(BASE.replace(old, new, 1).encode("utf-8"))
    return path


def _cli(cwd, *args):
    return subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT), *args], cwd=str(cwd), capture_output=True, check=False, timeout=120
    )


def _variants(source, wrap):
    cases = {"plain": source, "crlf": source.replace("\n", "\r\n"), "bom": "\ufeff" + source}
    if wrap:
        cases["async"] = "async def wrapper():\n" + "".join("    " + line + "\n" for line in source.split("\n"))
    return cases


PY = "mod.py"
BLOCK = [
    ("split-read-text", PY, "import pathlib\n\ndef f(p):\n    text = pathlib.Path(p).read_text()\n    return text.splitlines()\n", SPLIT, [5], True),
    ("split-stdout", PY, "def f(done):\n    return done.stdout.splitlines()\n", SPLIT, [2], True),
    ("split-stdin", PY, "import sys\n\ndef f():\n    return sys.stdin.read().splitlines()\n", SPLIT, [4], True),
    ("split-helper", PY, "import pathlib\n\ndef f(p):\n    return helper(pathlib.Path(p).read_text()).splitlines()\n", SPLIT, [4], True),
    ("split-strip", PY, "import pathlib\n\ndef f(p):\n    return pathlib.Path(p).read_text().strip().splitlines()\n", SPLIT, [4], True),
    ("split-check-output", PY, "import subprocess\n\ndef f():\n    return subprocess.check_output(['x']).splitlines()\n", SPLIT, [4], True),
    ("split-container", PY, "def f(done):\n    box = [done.stdout]\n    return box[0].splitlines()\n", SPLIT, [3], True),
    ("split-for-loop", PY, "def f(done):\n    for part in done.stdout:\n        part.splitlines()\n", SPLIT, [3], True),
    ("split-branch-keeps-taint", PY, "def f(done, flag):\n    t = done.stdout\n    if flag:\n        t = 'x'\n    return t.splitlines()\n", SPLIT, [5], True),
    ("split-imported-read-text", PY, "from crew_common import read_text\n\ndef f(p):\n    text = read_text(p)\n    return text.splitlines()\n", SPLIT, [5], True),
    ("json-read-text", PY, "import json\nimport pathlib\n\ndef f(p):\n    return json.loads(pathlib.Path(p).read_text())\n", JSON, [5], True),
    ("json-handle", PY, "import json\n\ndef f(p):\n    with open(p) as handle:\n        return json.load(handle)\n", JSON, [5], True),
    ("json-from-alias", PY, "from json import loads as jl\nimport pathlib\n\ndef f(p):\n    return jl(pathlib.Path(p).read_text())\n", JSON, [5], True),
    ("json-module-alias", PY, "import json as j\nimport pathlib\n\ndef f(p):\n    return j.loads(pathlib.Path(p).read_text())\n", JSON, [5], True),
    ("json-kwargs-are-no-hook", PY, "import json\n\ndef f(s, opts):\n    return json.loads(open(s).read(), **opts)\n", JSON, [4], True),
    ("bare-pwsh", PY, "import subprocess\n\nsubprocess.run(['pwsh', '-File', 'x'])\n", BARE, [3], False),
    ("bare-popen-tuple", PY, "import subprocess\n\nsubprocess.Popen(('python3', 'x'))\n", BARE, [3], False),
    ("bare-from-import-raw", PY, "from subprocess import run\n\nrun([r'pwsh', 'x'])\n", BARE, [3], False),
    ("bare-module-alias", PY, "import subprocess as sp\n\nsp.run(['py', '-3'])\n", BARE, [3], False),
    ("bare-multiline", PY, "import subprocess\n\nsubprocess.run(\n    [\n        'python', 'x',\n    ],\n)\n", BARE, [3], False),
    ("root-fence", "cmd.md", "# C\n\n```bash\npython3 -B ${CLAUDE_PLUGIN_ROOT}/x.py\n```\n", ROOT_RULE, [4], False),
    ("root-inline", "cmd.md", "# C\n\n1. `python3 -B ${CLAUDE_PLUGIN_ROOT}/x.py`\n", ROOT_RULE, [3], False),
    ("root-bare-variable", "cmd.md", "bash $CLAUDE_PLUGIN_ROOT/x.sh\n", ROOT_RULE, [1], False),
    ("noassert-print", "tests/test_x.py", "def test_x():\n    print(1)\n", NOASSERT, [1], False),
    ("noassert-async", "tests/test_x.py", "async def test_x():\n    pass\n", NOASSERT, [1], False),
    ("noassert-name-only", "tests/test_x.py", "def test_assert_in_the_name_only():\n    pass\n", NOASSERT, [1], False),
    ("noassert-decorator-line", "tests/test_x.py", "import pytest\n\n\n@pytest.mark.parametrize('x', [1])\ndef test_x(x):\n    print(x)\n", NOASSERT, [4], False),
]
BLOCK_CASES = [
    pytest.param(path, text, rule, lines, id=name + "-" + kind)
    for name, path, source, rule, lines, wrap in BLOCK
    for kind, text in _variants(source, wrap).items()
    for lines in [[n + 1 for n in lines] if kind == "async" else lines]
]

ALLOW = [
    ("split-literal", PY, "def f():\n    return 'a\\nb'.splitlines()\n", SPLIT),
    ("split-or-first-idiom", PY, "def f(done):\n    return (done.stderr.strip().splitlines() or ['none'])[0]\n", SPLIT),
    ("split-clean-reassign", PY, "def f(done):\n    t = done.stdout\n    t = 'a'\n    return t.splitlines()\n", SPLIT),
    ("split-untainted-param", PY, "def f(text):\n    return text.splitlines()\n", SPLIT),
    ("split-other-function-env", PY, "def f(done):\n    t = done.stdout\n\ndef g(t):\n    return t.splitlines()\n", SPLIT),
    ("split-comprehension-is-not-entered", PY, "def f(done):\n    return [x for x in done.stdout.splitlines()]\n", SPLIT),
    ("split-sliced-is-not-a-sink", PY, "def f(done):\n    return done.stdout.splitlines()[1:]\n", SPLIT),
    ("split-local-read-text-is-not-a-source", PY, "def read_text(p):\n    return p\n\ndef f(p):\n    return read_text(p).splitlines()\n", SPLIT),
    ("json-literal", PY, "import json\n\ndef f():\n    return json.loads('{\"a\": 1}')\n", JSON),
    ("json-hook", PY, "import json\n\ndef f(p, refuse):\n    return json.loads(p.read_text(), object_pairs_hook=refuse)\n", JSON),
    ("json-untainted-name", PY, "import json\n\ndef f(s):\n    return json.loads(s)\n", JSON),
    ("bare-sys-executable", PY, "import subprocess\nimport sys\n\nsubprocess.run([sys.executable, 'x'])\n", BARE),
    ("bare-variable-and-env", PY, "import subprocess\n\nsubprocess.run([pwsh_path, 'x'])\nsubprocess.run(['/usr/bin/env', 'x'])\n", BARE),
    ("bare-argv-in-variable", PY, "import subprocess\n\nargv = ['pwsh', 'x']\nsubprocess.run(argv)\n", BARE),
    ("root-quoted", "cmd.md", "python3 -B \"${CLAUDE_PLUGIN_ROOT}/x.py\"\n", ROOT_RULE),
    ("root-not-a-command", "cmd.md", "Read `${CLAUDE_PLUGIN_ROOT}/x.md` first.\n", ROOT_RULE),
    ("noassert-check-call", "tests/test_x.py", "def test_x():\n    check('a', True)\n", NOASSERT),
    ("noassert-raises", "tests/test_x.py", "import pytest\n\ndef test_x():\n    with pytest.raises(E):\n        f()\n", NOASSERT),
    ("noassert-bare-raises-import", "tests/test_x.py", "from pytest import raises\n\ndef test_x():\n    with raises(E):\n        f()\n", NOASSERT),
    ("noassert-helper-named-assert", "tests/test_x.py", "def test_x():\n    assert_blocked('x')\n", NOASSERT),
    ("noassert-assert-in-decorator", "tests/test_x.py", "@mark('check(')\ndef test_x():\n    pass\n", NOASSERT),
    ("noassert-not-a-test", "tests/test_x.py", "def helper():\n    pass\n", NOASSERT),
    ("noassert-outside-tests", "src/mod.py", "def test_x():\n    pass\n", NOASSERT),
]
ALLOW_CASES = [
    pytest.param(path, text, rule, id=name + "-" + kind)
    for name, path, source, rule in ALLOW
    for kind, text in _variants(source, False).items()
]


@pytest.mark.parametrize(("path", "text", "rule", "lines"), BLOCK_CASES)
def test_must_block(tmp_path, monkeypatch, path, text, rule, lines):
    doc = _check(tmp_path, monkeypatch, {path: text})

    assert doc["files"]["aborted"] == []
    assert _lines(doc, rule) == lines
    assert [r["rule"] for r in doc["results"]] == [rule] * len(lines)


@pytest.mark.parametrize(("path", "text", "rule"), ALLOW_CASES)
def test_must_allow(tmp_path, monkeypatch, path, text, rule):
    doc = _check(tmp_path, monkeypatch, {path: text})

    assert doc["files"]["aborted"] == []
    assert doc["results"] == []


EXPECTED_FIXTURE_LINES = {
    SPLIT: [7, 12, 18],
    JSON: [6, 11],
    BARE: [5, 9, 15, 16],
    ROOT_RULE: [3, 6],
    NOASSERT: [1, 6, 11, 15, 19],
}


@pytest.mark.parametrize("rule", IDS)
def test_each_rule_blocks_its_positive_fixture_and_allows_its_negative(tmp_path, monkeypatch, rule):
    copy = tmp_path / rule
    shutil.copytree(FIXTURES / rule, copy)
    monkeypatch.chdir(tmp_path)
    paths = sorted(rule + "/" + p.name for p in copy.iterdir())

    doc = rlc.run(str(REAL), paths)

    positives = [p for p in paths if "positive" in p]
    negatives = [p for p in paths if "negative" in p]
    assert doc["files"]["aborted"] == []
    assert sorted(doc["files"]["scanned"]) == sorted(paths)
    assert [r["path"] for r in doc["results"] if r["path"] in negatives] == []
    assert _lines(doc, rule, positives[0]) == EXPECTED_FIXTURE_LINES[rule]
    assert {r["rule"] for r in doc["results"]} == {rule}


def test_original_fixture_path_is_listed_as_skipped_by_scope(monkeypatch):
    monkeypatch.chdir(ROOT)
    original = "plugin/crew/lint/semgrep/fixtures/" + SPLIT + "/positive.py"

    doc = rlc.run(str(REAL), [original])

    assert doc["files"]["skipped_by_scope"] == [original]
    assert doc["files"]["scanned"] == []
    assert doc["results"] == []


def test_suppression_matches_semgrep_placement(tmp_path, monkeypatch):
    body = "import pathlib\n\ndef f(p):\n    text = pathlib.Path(p).read_text()\n"
    files = {
        "same_line.py": body + "    return text.splitlines()  # nosemgrep: " + SPLIT + " reason\n",
        "line_above.py": body + "    # nosemgrep: " + SPLIT + "\n    return text.splitlines()\n",
        "bare.py": body + "    return text.splitlines()  # nosemgrep\n",
        "other_id.py": body + "    return text.splitlines()  # nosemgrep: some-other-id\n",
        "id_list.py": body + "    return text.splitlines()  # nosemgrep: other-id, " + SPLIT + "\n",
        "two_lines_above.py": body + "    # nosemgrep: " + SPLIT + "\n\n    return text.splitlines()\n",
        "in_a_string.py": body + "    return text.splitlines(), '# nosemgrep'\n",
        "pylint_first.py": body + "    return text.splitlines()  # pylint: disable=x  # nosemgrep: " + SPLIT + "\n",
    }

    doc = _check(tmp_path, monkeypatch, files)

    flagged = sorted({r["path"] for r in doc["results"]})
    assert flagged == ["in_a_string.py", "other_id.py", "two_lines_above.py"]


def test_markdown_suppression_is_read_from_the_line_text(tmp_path, monkeypatch):
    files = {
        "a.md": "<!-- nosemgrep: " + ROOT_RULE + " -->\npython3 $CLAUDE_PLUGIN_ROOT/x\n",
        "b.md": "python3 $CLAUDE_PLUGIN_ROOT/x <!-- nosemgrep -->\n",
        "c.md": "python3 $CLAUDE_PLUGIN_ROOT/x <!-- nosemgrep: other -->\n",
    }

    doc = _check(tmp_path, monkeypatch, files)

    assert [r["path"] for r in doc["results"]] == ["c.md"]


def test_nosemgrep_on_a_parenthesised_multiline_sink(tmp_path, monkeypatch):
    source = (
        "import pathlib\n\n\ndef f(p):\n    t = pathlib.Path(p).read_text()\n    return (\n"
        "        t.splitlines()  # nosemgrep: " + SPLIT + "\n    )\n"
    )

    doc = _check(tmp_path, monkeypatch, {PY: source})

    assert doc["results"] == []


def test_crlf_and_bom_give_the_same_findings(tmp_path, monkeypatch):
    source = (FIXTURES / SPLIT / "positive.py").read_text(encoding="utf-8")
    files = {
        "lf/m.py": source,
        "crlf/m.py": source.replace("\n", "\r\n"),
        "bom/m.py": "\ufeff" + source,
        "cr/m.py": source.replace("\n", "\r"),
    }

    doc = _check(tmp_path, monkeypatch, files)

    assert [len(_lines(doc, SPLIT, p)) for p in files] == [3, 3, 3, 3]
    assert {tuple(_lines(doc, SPLIT, p)) for p in files} == {(7, 12, 18)}


def test_u2028_in_a_string_literal_does_not_move_lines(tmp_path, monkeypatch):
    source = (
        "import pathlib\n\nNOTE = 'a\u2028b\u0085c\u2029d'\n\n\ndef f(p):\n"
        "    t = pathlib.Path(p).read_text()\n    return t.splitlines()  # nosemgrep: other\n"
    )
    suppressed = source.replace("nosemgrep: other", "nosemgrep: " + SPLIT)

    flagged = _check(tmp_path, monkeypatch, {"a.py": source})
    quiet = _check(tmp_path, monkeypatch, {"b.py": suppressed})

    assert _lines(flagged, SPLIT) == [8]
    assert quiet["results"] == []


def test_u2028_before_a_test_does_not_shift_its_text(tmp_path, monkeypatch):
    source = "NOTE = 'a\u2028b\u0085c'\n\n\ndef test_x():\n    assert 1\n\n\ndef test_y():\n    pass\n"

    doc = _check(tmp_path, monkeypatch, {"tests/test_x.py": source})

    assert _lines(doc, NOASSERT) == [8]


def test_u2028_before_a_markdown_marker_does_not_shift_it(tmp_path, monkeypatch):
    source = "intro \u2028 line\npython3 $CLAUDE_PLUGIN_ROOT/x <!-- nosemgrep -->\n"

    doc = _check(tmp_path, monkeypatch, {"a.md": source})

    assert doc["results"] == []


def test_u2028_in_markdown_does_not_move_lines(tmp_path, monkeypatch):
    source = "intro \u2028 line\n\npython3 $CLAUDE_PLUGIN_ROOT/x\n"

    doc = _check(tmp_path, monkeypatch, {"a.md": source})

    assert _lines(doc, ROOT_RULE) == [3]


UNPARSABLE = [
    ("syntax-error", b"def f(:\n    pass\n"),
    ("nul-byte", b"x = 1\x00\n"),
    ("invalid-utf8", b"x = '\xff\xfe'\n"),
    ("deep-parentheses", b"x = " + b"(" * 5000 + b"1" + b")" * 5000 + b"\n"),
    ("deep-binop", b"x = " + b"+".join([b"1"] * 20000) + b"\n"),
]


@pytest.mark.parametrize(("name", "data"), UNPARSABLE, ids=[n for n, _ in UNPARSABLE])
def test_unparsable_python_is_an_aborted_file_not_a_pass(tmp_path, monkeypatch, name, data):
    doc = _check(tmp_path, monkeypatch, {"bad.py": data, "ok.md": "fine\n"})

    assert [row["path"] for row in doc["files"]["aborted"]] == ["bad.py"]
    assert doc["files"]["aborted"][0]["reason"].split(":")[0] in {
        "SyntaxError", "ValueError", "RecursionError", "MemoryError", "UnicodeDecodeError"
    }
    assert "bad.py" not in doc["files"]["scanned"]
    assert doc["results"] == []


def test_an_aborted_file_does_not_hide_findings_in_another(tmp_path, monkeypatch):
    files = {"bad.py": b"def f(:\n", "tests/test_x.py": "def test_x():\n    pass\n"}

    doc = _check(tmp_path, monkeypatch, files)

    assert [row["path"] for row in doc["files"]["aborted"]] == ["bad.py"]
    assert _lines(doc, NOASSERT) == [1]


def test_invalid_utf8_markdown_is_an_aborted_file(tmp_path, monkeypatch):
    doc = _check(tmp_path, monkeypatch, {"a.md": b"python3 $CLAUDE_PLUGIN_ROOT/x \xff\n"})

    assert doc["files"]["aborted"][0]["path"] == "a.md"
    assert doc["results"] == []


def test_missing_file_and_symlink_are_aborted_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "real.py").write_text("x = 1\n", encoding="utf-8")
    try:
        os.symlink("real.py", tmp_path / "link.py")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")

    doc = rlc.run(str(REAL), ["gone.py", "link.py", "real.py"])

    assert sorted(row["path"] for row in doc["files"]["aborted"]) == ["gone.py", "link.py"]
    assert doc["files"]["scanned"] == ["real.py"]


def test_checker_survives_deep_nesting(tmp_path, monkeypatch):
    chain = "import pathlib\n\ndef f(p):\n    return pathlib.Path(p).read_text()" + ".strip()" * 3000 + ".splitlines()\n"

    doc = _check(tmp_path, monkeypatch, {"deep.py": chain})

    judged = doc["files"]["scanned"] + [row["path"] for row in doc["files"]["aborted"]]
    assert judged == ["deep.py"]
    assert bool(doc["results"]) == (doc["files"]["scanned"] == ["deep.py"])


def test_taint_does_not_cross_functions(tmp_path, monkeypatch):
    source = "def a(done):\n    return done.stdout\n\ndef b(done):\n    return a(done).splitlines()\n"

    doc = _check(tmp_path, monkeypatch, {PY: source})

    assert _lines(doc, SPLIT) == []


def test_checker_reports_the_rules_it_ran(tmp_path, monkeypatch):
    doc = _check(tmp_path, monkeypatch, {"a.md": "x\n"}, skip=(BARE,))

    assert doc["version"] == 1
    assert doc["rules"] == [SPLIT, JSON, ROOT_RULE, NOASSERT]
    assert doc["skipped_rules"] == [BARE]
    assert doc["not_covered"] == ["symlink-fifo-open"]


def test_output_is_ascii_json_and_names_skipped_files(tmp_path):
    name = "d\u00e9j\u00e0/m\u00f6d.py"
    _write(tmp_path, {name: "import subprocess\nsubprocess.run(['pwsh'])\n", "tests/test_a.py": "x = 1\n"})
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "n.txt").write_text("x\n", encoding="utf-8")

    done = _cli(tmp_path, "--rules", str(REAL), name, "docs/n.txt", "tests/test_a.py")

    assert done.returncode == 0
    assert done.stdout.decode("ascii").endswith("}\n")
    doc = json.loads(done.stdout)
    assert doc["results"][0]["path"] == name
    assert doc["files"]["skipped_by_scope"] == ["docs/n.txt"]
    assert doc["files"]["scanned"] == [name, "tests/test_a.py"]


def test_strip_first_segment_and_windows_paths(tmp_path):
    _write(tmp_path, {"head/a/m.py": "import subprocess\nsubprocess.run(['pwsh'])\n"})

    done = _cli(tmp_path, "--rules", str(REAL), "--strip-first-segment", "head/a/m.py")

    assert json.loads(done.stdout)["results"][0]["path"] == "a/m.py"
    assert rlc._relative("head\\a\\m.py", True) == "a/m.py"  # pylint: disable=protected-access
    assert rlc._relative(".\\a\\.\\m.py", False) == "a/m.py"  # pylint: disable=protected-access


@pytest.mark.parametrize("bad", ["/etc/passwd", "C:\\x\\m.py", "c:/x.py", "../m.py", "a/../../m.py", ""])
def test_absolute_drive_and_climbing_paths_exit_2(tmp_path, bad):
    done = _cli(tmp_path, "--rules", str(REAL), bad)

    assert done.returncode == 2
    assert done.stdout == b""
    assert b"Traceback" not in done.stderr


def test_the_same_path_twice_exits_2(tmp_path):
    _write(tmp_path, {"m.py": "x = 1\n"})

    done = _cli(tmp_path, "--rules", str(REAL), "m.py", "./m.py")

    assert done.returncode == 2


def test_unknown_skip_id_exits_2(tmp_path):
    done = _cli(tmp_path, "--rules", str(REAL), "--skip", "no-such-rule")

    assert done.returncode == 2
    assert b"no-such-rule" in done.stderr


def test_missing_symlinked_and_empty_rule_files_exit_2(tmp_path):
    (tmp_path / "empty.yml").write_bytes(b"")
    try:
        os.symlink(REAL, tmp_path / "link.yml")
        linked = ["link.yml"]
    except (OSError, NotImplementedError):
        linked = []

    codes = [_cli(tmp_path, "--rules", name) for name in ["missing.yml", "empty.yml", *linked]]

    assert [done.returncode for done in codes] == [2] * len(codes)
    assert all(done.stdout == b"" and b"Traceback" not in done.stderr for done in codes)


def test_rule_without_implementation_exits_2(tmp_path):
    extra = BASE + (
        "\n  - id: crew-new-rule\n    languages: [python]\n    severity: WARNING\n    message: >-\n"
        "      A new rule.\n    metadata:\n      class: new-class\n      standards: [GEN-01]\n"
        "    paths:\n      include: [\"*.py\"]\n    pattern-regex: 'x'\n"
    )
    path = tmp_path / "rules.yml"
    path.write_bytes(extra.encode("utf-8"))

    done = _cli(tmp_path, "--rules", str(path))

    assert done.returncode == 2
    assert b"crew-new-rule has no implementation" in done.stderr


def test_implementation_without_rule_exits_2(tmp_path):
    start = BASE.index("  - id: " + ROOT_RULE)
    end = BASE.index("  - id: " + NOASSERT)
    path = tmp_path / "rules.yml"
    path.write_bytes((BASE[:start] + BASE[end:]).encode("utf-8"))

    done = _cli(tmp_path, "--rules", str(path))

    assert done.returncode == 2
    assert ROOT_RULE.encode() in done.stderr


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("      - pattern: sys.stdin\n    pattern-sinks:", "      - pattern: sys.stdin\n      - pattern: $Z.recv()\n    pattern-sinks:"),
        ("          - pattern: json.load(...)\n", "          - pattern: json.load(...)\n          - pattern: json.dump(...)\n"),
        ("          - pattern: subprocess.$F(($E, ...), ...)\n", "          - pattern: subprocess.$F(($E, ...), ...)\n          - pattern: xx.$F($E)\n"),
        ("    mode: taint\n    message: >-\n      json.load/json.loads", "    mode: search\n    message: >-\n      json.load/json.loads"),
        ("          - pattern: $X.splitlines(...)\n          - pattern-not-inside", "          - pattern: $X.splitlines(...)\n            # nested\n          - pattern-not-inside"),
        ("          - pattern-either:\n              - pattern: json.loads(...)", "          - pattern-either:\n                  - pattern: json.loads(...)"),
    ],
    ids=["extra-source", "extra-either-branch", "extra-bare-branch", "mode-edit", "comment-in-block", "indentation-only"],
)
def test_changed_pattern_with_old_fingerprint_exits_2(tmp_path, old, new):
    path = _mutated(tmp_path, old, new)

    done = _cli(tmp_path, "--rules", str(path))

    assert done.returncode == 2, done.stderr
    assert b"changed shape" in done.stderr or b"rule file" in done.stderr


def test_a_message_or_regex_edit_needs_no_checker_change(tmp_path, monkeypatch):
    path = _mutated(tmp_path, "regex: '^[rRbBuU]?[\"''](pwsh|", "regex: '^[rRbBuU]?[\"''](pwsh2|")
    other = _mutated(tmp_path, "A bare interpreter name", "A BARE interpreter name", name="other.yml")

    doc = _check(tmp_path, monkeypatch, {PY: "import subprocess\nsubprocess.run(['pwsh'])\n"}, rules=path)
    reworded = rlc.run(str(other), [PY])

    assert doc["results"] == []
    assert reworded["results"][0]["message"].startswith("A BARE interpreter name")


def test_checker_accepts_a_set_of_fingerprints_per_rule(tmp_path, monkeypatch):
    path = _mutated(tmp_path, "          - pattern: json.load(...)\n", "          - pattern: json.load(...)\n          - pattern: json.dump(...)\n")
    new = rlr.read_rules(path)
    old = rlr.read_rules(REAL)
    new_fp = next(r.fingerprint for r in new.rules if r.id == JSON)
    old_fp = next(r.fingerprint for r in old.rules if r.id == JSON)
    function, accepted = rlc.RULES[JSON]
    assert new_fp != old_fp and accepted == frozenset({old_fp})
    monkeypatch.setitem(rlc.RULES, JSON, (function, accepted | {new_fp}))
    monkeypatch.chdir(tmp_path)

    both = [rlc.run(str(p), []) for p in (REAL, path)]

    assert [doc["rules"] for doc in both] == [list(IDS), list(IDS)]


def test_base_and_head_are_judged_by_their_own_rule_copy(tmp_path, monkeypatch):
    head_rules = _mutated(tmp_path, "regex: '^[rRbBuU]?[\"''](pwsh|", "regex: '^[rRbBuU]?[\"''](pwsh2|")
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, {"base/m.py": "import subprocess\nsubprocess.run(['pwsh'])\n", "head/m.py": "import subprocess\nsubprocess.run(['pwsh'])\n"})

    base = rlc.run(str(REAL), ["base/m.py"], (), True)
    head = rlc.run(str(head_rules), ["head/m.py"], (), True)

    assert [len(base["results"]), len(head["results"])] == [1, 0]


def _canary_tree(tmp_path, rules_path, skip=()):
    reader = rlr.read_rules(rules_path)
    paths = {}
    for rule in reader.rules:
        if rule.id in skip:
            continue
        path, source = rlr.CANARIES[rule.id].render("canarydir1", "tok9f3a2b")
        paths[rule.id] = path
        _write(tmp_path, {path: source})
    return paths


def test_every_canary_fires_only_its_own_rule(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths = _canary_tree(tmp_path, REAL)

    doc = rlc.run(str(REAL), list(paths.values()))

    assert doc["files"]["aborted"] == [] and doc["files"]["skipped_by_scope"] == []
    assert sorted((r["path"], r["rule"]) for r in doc["results"]) == sorted((p, r) for r, p in paths.items())


def test_canary_fails_when_a_rule_is_broken(tmp_path, monkeypatch):
    broken = _mutated(tmp_path, "regex: '^[rRbBuU]?[\"''](pwsh|powershell|python3?|py)[\"'']$'", "regex: '^$'")
    monkeypatch.chdir(tmp_path)
    paths = _canary_tree(tmp_path, REAL)

    doc = rlc.run(str(broken), list(paths.values()))

    fired = {r["rule"] for r in doc["results"]}
    assert fired == set(IDS) - {BARE}


def test_a_skipped_rule_has_no_canary_and_does_not_fire(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths = _canary_tree(tmp_path, REAL)

    doc = rlc.run(str(REAL), list(paths.values()), (SPLIT,))

    assert SPLIT not in {r["rule"] for r in doc["results"]}
    assert len(doc["results"]) == len(IDS) - 1


def test_checker_source_has_no_findings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    copy = tmp_path / "scripts" / "review_lint_classes.py"
    copy.parent.mkdir()
    shutil.copyfile(SCRIPT, copy)
    reader = tmp_path / "scripts" / "review_lint_rules.py"
    shutil.copyfile(SCRIPT.parent / "review_lint_rules.py", reader)

    doc = rlc.run(str(REAL), ["scripts/review_lint_classes.py", "scripts/review_lint_rules.py"])

    assert doc["files"]["scanned"] == ["scripts/review_lint_classes.py", "scripts/review_lint_rules.py"]
    assert doc["results"] == []


def test_checker_does_not_import_from_the_checked_tree(tmp_path):
    _write(tmp_path, {
        "json.py": "raise SystemExit('decoy json imported')\n",
        "review_lint_rules.py": "raise SystemExit('decoy reader imported')\n",
        "m.py": "x = 1\n",
    })

    done = _cli(tmp_path, "--rules", str(REAL), "m.py")

    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["files"]["scanned"] == ["m.py"]


def test_a_fifo_is_an_aborted_file_not_a_hang(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("no FIFOs on this host")
    os.mkfifo(tmp_path / "x.py")

    done = _cli(tmp_path, "--rules", str(REAL), "x.py")

    assert done.returncode == 0
    assert [row["path"] for row in json.loads(done.stdout)["files"]["aborted"]] == ["x.py"]


def test_an_exception_with_a_broken_str_is_still_an_aborted_row(tmp_path, monkeypatch):
    class Broken(MemoryError):
        def __str__(self):
            raise RuntimeError("no str")

    def explode(*_args):
        raise Broken("boom")

    monkeypatch.chdir(tmp_path)
    _write(tmp_path, {"m.py": "x = 1\n"})
    monkeypatch.setattr(rlc, "check_text", explode)

    doc = rlc.run(str(REAL), ["m.py"])

    assert doc["files"]["aborted"] == [{"path": "m.py", "reason": "Broken: boom"}]


def test_a_regex_that_does_not_compile_exits_2(tmp_path):
    path = _mutated(tmp_path, "pattern-regex: '(?:python3?|", "pattern-regex: '[(?:python3?|")

    done = _cli(tmp_path, "--rules", str(path))

    assert done.returncode == 2
    assert b"does not compile" in done.stderr and b"Traceback" not in done.stderr


def test_a_nosemgrep_that_is_not_a_marker_does_not_suppress(tmp_path, monkeypatch):
    body = "import pathlib\n\ndef f(p):\n    text = pathlib.Path(p).read_text()\n"
    files = {
        "not_marker.py": body + "    return text.splitlines()  # not nosemgrep: " + SPLIT + "\n",
        "word_in_comment.py": body + "    return text.splitlines()  # see the nosemgrep docs\n",
    }

    doc = _check(tmp_path, monkeypatch, files)

    assert sorted({r["path"] for r in doc["results"]}) == ["not_marker.py", "word_in_comment.py"]
