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

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import review_verdict as rv

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "review")
FIXTURES = sorted(glob.glob(os.path.join(GOLDEN, "*", "")))
SIZE_BOUND = 1_500_000

# The same patterns golden_build.py refuses a fixture on.
MACHINE_PATHS = ("/repos/", "/root/", "/home/", "/Users/", "C:\\Users\\", "\\\\Users\\\\")
SECRETS = (
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20}"),
    re.compile(r"(?<![A-Za-z0-9])gh[po]_[A-Za-z0-9]{20}"),
    re.compile(r"github_pat_"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[bap]-"),
    re.compile(r"-----BEGIN"),
    re.compile(r"Bearer [A-Za-z0-9]"),
)
EMAIL = re.compile(r"(?<![\\A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*"
                   r"\.[A-Za-z]{2,}")


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


def test_golden_corpus_covers_the_shapes_that_broke():
    expected = [_json(f, "expected.json") for f in FIXTURES]
    forms = {e["read_form"] for e in expected}

    assert {"full", "bare"} <= forms, forms
    assert any("\u2028" in _text(f, "events.jsonl") for f in STREAMS)
    assert any(e["failure_class"] == "reviewer" for e in expected)


def _files():
    return [p for p in glob.glob(os.path.join(GOLDEN, "**", "*"), recursive=True)
            if os.path.isfile(p)]


def test_golden_corpus_holds_no_machine_paths_or_secrets():
    assert _files(), "no golden corpus"
    leaks = []
    for path in _files():
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
        name = os.path.relpath(path, GOLDEN)
        leaks += [(name, p) for p in MACHINE_PATHS if p in text]
        leaks += [(name, s.pattern) for s in SECRETS if s.search(text)]
        leaks += [(name, m) for m in EMAIL.findall(text)
                  if not (m.endswith("@example.com") or "noreply" in m or m.startswith("git@"))]
    assert not leaks, leaks


def test_golden_corpus_stays_under_its_size_bound():
    total = sum(os.path.getsize(p) for p in _files())

    assert 0 < total < SIZE_BOUND, total
