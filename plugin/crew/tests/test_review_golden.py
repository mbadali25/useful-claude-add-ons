"""Real reviewer output, replayed through the verdict parser.

Every fixture under `golden/review/<checkout>--<review-dir>/` is a real
reviewer's `out.txt` (and, for one, its `codex exec --json` stream), redacted
by `golden_build.py` -- absolute paths to `<ROOT>`/`<HOME>`/`<TMP>`, the host
name to `<HOST>`, nothing else changed -- with the bundle part paths its
manifest listed (`parts.json`) and the verdict it replays to (`expected.json`).

Hand-written fixtures are how T-0079 shipped: the parser's tests used bare
names, every real reviewer echoed the full listed path, and honest rounds read
as INCOMPLETE. These fixtures are the shapes reviewers actually produce
(T-0087).
"""
import glob
import json
import os
import re
import socket
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import golden_build
import review_verdict as rv

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "review")
FIXTURES = sorted(glob.glob(os.path.join(GOLDEN, "*", "")))
SIZE_BOUND = 1_500_000

# The patterns golden_build.py refuses a fixture on -- the builder's own, not
# a copy: a second list kept the builder's gaps and could not catch them
# (review round 5).
MACHINE_PATHS = ("/repos/", "/root/", "/home/", "/Users/", "C:\\Users\\", "\\\\Users\\\\")
SECRETS = tuple(pattern for name, pattern in golden_build.LEAKS if name != "machine path")
EMAIL = golden_build.EMAIL


def _text(folder, name):
    with open(os.path.join(folder, name), encoding="utf-8", newline="") as fh:
        return fh.read()


def _json(folder, name):
    return json.loads(_text(folder, name))


def _ids():
    return [os.path.basename(os.path.dirname(f)) for f in FIXTURES]


def test_golden_corpus_is_not_empty():
    assert len(FIXTURES) >= 40, f"{len(FIXTURES)} fixtures under {GOLDEN}"


@pytest.mark.parametrize("folder", FIXTURES, ids=_ids())
def test_golden_outputs_replay_to_their_recorded_verdicts(folder):
    expected = _json(folder, "expected.json")

    result = rv.parse(_text(folder, "out.txt"), 0, False, _json(folder, "parts.json"))

    assert (result["verdict"], result["counts"], result["parts_missing"]) == (
        expected["verdict"], expected["counts"], expected["parts_missing"]), result["reasons"]
    assert rv.failure_class(result["verdict"], result["delivered"], False) == \
        expected["failure_class"]


STREAMS = [f for f in FIXTURES if os.path.exists(os.path.join(f, "events.jsonl"))]


@pytest.mark.parametrize("folder", STREAMS,
                         ids=[os.path.basename(os.path.dirname(f)) for f in STREAMS])
def test_golden_codex_stream_yields_its_out_txt(folder):
    assert rv.codex_final_message(_text(folder, "events.jsonl")) == (
        _text(folder, "out.txt"), None)


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__)))))
ATTRIBUTES = "plugin/crew/tests/golden/.gitattributes"


def _corpus_files():
    return sorted(os.path.relpath(p, REPO).replace(os.sep, "/")
                  for p in glob.glob(os.path.join(GOLDEN, "**", "*"), recursive=True)
                  if os.path.isfile(p))


def test_golden_corpus_is_checked_out_without_line_ending_conversion():
    files = _corpus_files()
    proc = subprocess.run(["git", "check-attr", "text", "--"] + files, cwd=REPO,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          check=False)

    assert proc.returncode == 0, proc.stderr
    converted = [line for line in proc.stdout.splitlines() if not line.endswith(": text: unset")]
    assert files and not converted, (
        f"{len(converted)} corpus file(s) are not -text; {ATTRIBUTES} must hold `* -text` "
        f"so an autocrlf checkout replays the corpus byte-exact: {converted[:3]}")


def test_golden_corpus_files_carry_no_carriage_return():
    with_cr = []
    for rel in _corpus_files():
        with open(os.path.join(REPO, rel), "rb") as fh:
            if b"\r" in fh.read():
                with_cr.append(rel)

    assert not with_cr, (
        f"{len(with_cr)} corpus file(s) hold a CR; the committed blobs hold none, so an "
        f"autocrlf checkout without {ATTRIBUTES} is the known cause: {with_cr[:3]}")


def test_golden_corpus_covers_the_shapes_that_broke():
    expected = [_json(f, "expected.json") for f in FIXTURES]
    forms = {e["read_form"] for e in expected}

    assert {"full", "bare"} <= forms, forms
    assert any("\u2028" in _text(f, "events.jsonl") for f in STREAMS)
    assert any(e["failure_class"] == "reviewer" for e in expected)


def test_golden_corpus_holds_a_round_recovered_despite_stray_prose():
    """T-0100 round 2 scored INCOMPLETE for one trailing paragraph beside four
    well-formed findings and full READ coverage; L-0576 recovers it."""
    recovered = []
    for folder in FIXTURES:
        result = rv.parse(_text(folder, "out.txt"), 0, False, _json(folder, "parts.json"))
        if result["ignored"]:
            recovered.append((os.path.basename(os.path.dirname(folder)), result["verdict"]))

    assert ("uca-t0100--T-0100-build--nqUaqO", rv.FINDINGS) in recovered, recovered


def _files(root=GOLDEN):
    return [p for p in glob.glob(os.path.join(root, "**", "*"), recursive=True)
            if os.path.isfile(p)]


def _corpus_leaks(root=GOLDEN):
    """Every leak in the files under `root`: the builder's own `leak` (its
    patterns, the host name, a person's address) plus the machine-path
    substrings. Review round 6: this test used to re-check the patterns
    itself and never looked for the host name."""
    leaks = []
    for path in _files(root):
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
        name = os.path.relpath(path, root)
        found = golden_build.leak(text)
        if found:
            leaks.append((name, found))
        leaks += [(name, p) for p in MACHINE_PATHS if p in text]
        leaks += [(name, s.pattern) for s in SECRETS if s.search(text)]
        leaks += [(name, m) for m in EMAIL.findall(text) if not golden_build.allowed_address(m)]
    return leaks


def test_golden_corpus_holds_no_machine_paths_or_secrets():
    assert _files(), "no golden corpus"

    leaks = _corpus_leaks()

    assert not leaks, leaks


def test_corpus_leak_check_refuses_a_planted_host_name(tmp_path):
    host = socket.gethostname()
    if not host:
        pytest.skip("no host name on this machine")
    (tmp_path / "clean.txt").write_text("READ part 1\nCLEAN\n", encoding="utf-8", newline="\n")
    assert _corpus_leaks(str(tmp_path)) == []
    (tmp_path / "out.txt").write_text(f"READ part 1\nran on {host} today\n",
                                      encoding="utf-8", newline="\n")

    leaks = _corpus_leaks(str(tmp_path))

    assert ("out.txt", "host name") in leaks, leaks


@pytest.mark.parametrize("text, leaked", [
    ("fixture-vmVkDU/parts.json", False), ("unvmed", False), ("ran on vm today", True),
    ("vm.local", True), ("user@vm prompt", True)])
def test_leak_finds_the_host_name_only_as_a_whole_word(monkeypatch, text, leaked):
    """A short host name (`vm`) inside an unrelated word is not a leak; the
    same name standing alone, or as a domain label, is."""
    monkeypatch.setattr(golden_build.socket, "gethostname", lambda: "vm")

    assert (golden_build.leak(text) == "host name") is leaked, golden_build.leak(text)


def test_golden_corpus_stays_under_its_size_bound():
    total = sum(os.path.getsize(p) for p in _files())

    assert 0 < total < SIZE_BOUND, total


def test_golden_corpus_placeholders_replace_whole_paths_only():
    """`symlink<HOME> race` was `symlink/root race`: a placeholder glued to
    the word before it replaced prose, not a path."""
    glued = []
    for path in _files():
        with open(path, encoding="utf-8", newline="") as fh:
            glued += [(os.path.relpath(path, GOLDEN), m.group(0)) for m in
                      re.finditer(r"(?<!\\)[A-Za-z0-9_]<(?:ROOT|HOME|TMP|HOST)>", fh.read())]

    assert not glued, glued


@pytest.mark.parametrize("text", [
    "a symlink/root race", "a/tmp/b is not the temp dir", "a boxer is not the host",
    "unbox the thing", "re/repos/personal/x stays"])
def test_redact_leaves_prose_that_only_contains_a_machine_string(monkeypatch, text):
    monkeypatch.setattr(golden_build.os.path, "expanduser", lambda p: "/root")
    monkeypatch.setattr(golden_build.tempfile, "gettempdir", lambda: "/tmp")
    monkeypatch.setattr(golden_build.socket, "gethostname", lambda: "box")

    assert golden_build.redact(text, "/repos/personal/x") == text


@pytest.mark.parametrize("text, want", [
    ("see /root/x and (/root)", "see <HOME>/x and (<HOME>)"),
    ("in /tmp/a", "in <TMP>/a"),
    ("host box: ok, box.local", "host <HOST>: ok, <HOST>.local"),
    ("cd /repos/personal/x/y", "cd <ROOT>/y"),
    ('"text":"a\\n/root/x"', '"text":"a\\n<HOME>/x"'),
])
def test_redact_still_replaces_whole_machine_strings(monkeypatch, text, want):
    monkeypatch.setattr(golden_build.os.path, "expanduser", lambda p: "/root")
    monkeypatch.setattr(golden_build.tempfile, "gettempdir", lambda: "/tmp")
    monkeypatch.setattr(golden_build.socket, "gethostname", lambda: "box")

    assert golden_build.redact(text, "/repos/personal/x") == want


# Review round 5 BLOCK: a person's address straight after a JSON escape, and
# key shapes with hyphenated or underscored segments, went through as clean.
_A36 = "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
_SECRET_SHAPES = [
    "x\\nalice@corp.com", "\\talice@corp.com", "\\u003calice@corp.com\\u003e",
    "sk-proj-" + "abcdefghijklmnopqrstuvwxyzABCDEF", "sk-proj-abc_DEF-" + _A36[:24],
    "sk-ant-api03-" + "Ab_cD-eF" * 5, "sk-" + _A36[:24],
    "ghp_" + _A36, "gho_" + _A36, "ghu_" + _A36, "ghs_" + _A36, "ghr_" + _A36,
    "github_pat_11AB", "AKIA" + "ABCDEFGHIJ012345", "ASIA" + "ABCDEFGHIJ012345",
    "AIza" + _A36[:35], "sk_live_" + _A36[:24], "rk_live_" + _A36[:24], "npm_" + _A36,
    "glpat-" + _A36[:20], "xoxb-1", "xoxp-1", "-----BEGIN OPENSSH PRIVATE KEY-----",
    "Bearer eyJ",
]
_NOT_SECRETS = [
    "git@github.com:owner/repo.git", "\\n@pytest.mark.parametrize", "\\n+@x.y",
    "noreply@anthropic.com", "dev@example.com", "task-runner and risk-free", "sk-short",
    "the ask-" + "abcdefghijklmnopqrstuvwxyzabcd", "AKIAshort",
]


@pytest.mark.parametrize("text", _SECRET_SHAPES)
def test_leak_refuses_every_secret_shape(monkeypatch, text):
    monkeypatch.setattr(golden_build.socket, "gethostname", lambda: "zz-no-such-host")

    assert golden_build.leak(text) is not None


@pytest.mark.parametrize("text", _NOT_SECRETS)
def test_leak_allows_what_is_not_a_secret(monkeypatch, text):
    monkeypatch.setattr(golden_build.socket, "gethostname", lambda: "zz-no-such-host")

    assert golden_build.leak(text) is None


def test_redact_replaces_an_address_after_a_json_escape(monkeypatch):
    monkeypatch.setattr(golden_build.socket, "gethostname", lambda: "zz-no-such-host")

    got = golden_build.redact("x\\nalice@corp.com y", "/nowhere")

    assert ("<EMAIL>" in got, "alice@" in got) == (True, False)
