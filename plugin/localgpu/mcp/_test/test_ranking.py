"""Cosine ranking, and the filters that narrow it."""

from __future__ import annotations

import math

import numpy as np
import pytest
from conftest import TEST_DIM

import config
from store import ChunkRecord, Hit, VectorStore, match_glob, normalise


@pytest.fixture
def tiny(home) -> VectorStore:
    """A 3-dimensional index, so the expected order can be worked out by hand."""
    with VectorStore(config.index_dir(home), dim=3) as store:
        yield store


def add(store, path, vector, start=1, end=5):
    store.add(
        [ChunkRecord(path, start, end, "sha", 1.0, 10)],
        [vector],
    )


def test_known_vectors_rank_in_the_expected_order(tiny):
    add(tiny, "/repo/east.py", [1.0, 0.0, 0.0])          # cos 1.000
    add(tiny, "/repo/tilted.py", [0.8, 0.6, 0.0])        # cos 0.800
    add(tiny, "/repo/diagonal.py", [1.0, 1.0, 0.0])      # cos 0.707
    add(tiny, "/repo/north.py", [0.0, 1.0, 0.0])         # cos 0.000
    add(tiny, "/repo/west.py", [-1.0, 0.0, 0.0])         # cos -1.000

    hits = tiny.search([1.0, 0.0, 0.0], k=5)
    assert [h.path for h in hits] == [
        "/repo/east.py",
        "/repo/tilted.py",
        "/repo/diagonal.py",
        "/repo/north.py",
        "/repo/west.py",
    ]
    expected = [1.0, 0.8, math.sqrt(0.5), 0.0, -1.0]
    for hit, want in zip(hits, expected):
        assert hit.score == pytest.approx(want, abs=1e-3), hit
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_magnitude_does_not_beat_direction(tiny):
    add(tiny, "/repo/loud.py", [40.0, 40.0, 0.0])   # long, but 45 degrees off
    add(tiny, "/repo/quiet.py", [0.01, 0.0, 0.0])   # tiny, but pointing at it
    hits = tiny.search([2.0, 0.0, 0.0], k=2)
    assert [h.path for h in hits] == ["/repo/quiet.py", "/repo/loud.py"]
    assert hits[0].score == pytest.approx(1.0, abs=1e-3)


def test_k_limits_and_never_exceeds_the_index(tiny):
    for index in range(4):
        add(tiny, f"/repo/f{index}.py", [1.0, index / 10.0, 0.0])
    assert len(tiny.search([1.0, 0.0, 0.0], k=2)) == 2
    assert len(tiny.search([1.0, 0.0, 0.0], k=99)) == 4
    assert tiny.search([1.0, 0.0, 0.0], k=0) == []


def test_search_on_an_empty_index_is_empty_not_an_error(tiny):
    assert tiny.search([1.0, 0.0, 0.0], k=5) == []


def test_hits_carry_the_line_span(tiny):
    add(tiny, "/repo/east.py", [1.0, 0.0, 0.0], start=46, end=105)
    hit = tiny.search([1.0, 0.0, 0.0], k=1)[0]
    assert isinstance(hit, Hit)
    assert (hit.start_line, hit.end_line) == (46, 105)
    assert hit.chunk_id > 0


def test_root_filter_keeps_only_that_subtree(tiny):
    add(tiny, "/repo/one/a.py", [1.0, 0.0, 0.0])
    add(tiny, "/repo/two/b.py", [1.0, 0.0, 0.0])
    add(tiny, "/repo/one-more/c.py", [1.0, 0.0, 0.0])

    hits = tiny.search([1.0, 0.0, 0.0], k=5, root="/repo/one")
    assert [h.path for h in hits] == ["/repo/one/a.py"], (
        "a prefix match must respect directory boundaries"
    )
    assert len(tiny.search([1.0, 0.0, 0.0], k=5, root="/repo")) == 3
    assert tiny.search([1.0, 0.0, 0.0], k=5, root="/elsewhere") == []


def test_path_glob_filter(tiny):
    add(tiny, "/repo/src/a.py", [1.0, 0.0, 0.0])
    add(tiny, "/repo/src/b.js", [1.0, 0.0, 0.0])
    add(tiny, "/repo/docs/c.md", [1.0, 0.0, 0.0])

    assert [h.path for h in tiny.search([1.0, 0.0, 0.0], k=5, path_glob="*.py")] == [
        "/repo/src/a.py"
    ]
    assert [h.path for h in tiny.search([1.0, 0.0, 0.0], k=5, path_glob="**/*.js")] == [
        "/repo/src/b.js"
    ]
    assert len(tiny.search([1.0, 0.0, 0.0], k=5, path_glob="*/src/*")) == 2
    assert tiny.search([1.0, 0.0, 0.0], k=5, path_glob="*.rs") == []


def test_match_glob_handles_both_separators():
    assert match_glob(r"C:\repo\src\a.py", "*.py")
    assert match_glob(r"C:\repo\src\a.py", "**/*.py")
    assert match_glob("/repo/src/a.py", "a.py")
    assert not match_glob("/repo/src/a.py", "*.md")


def test_vectors_survive_the_float16_round_trip(home, embedder):
    with VectorStore(config.index_dir(home), dim=TEST_DIM) as store:
        vector = embedder.vector("def search_code(query, k): return ranked")
        add(store, "/repo/x.py", vector)
        hit = store.search(vector, k=1)[0]
        assert hit.score == pytest.approx(1.0, abs=2e-3), (
            "a vector must still match itself after float16 storage"
        )


def test_normalise_leaves_a_zero_vector_alone():
    result = normalise([[0.0, 0.0, 0.0], [3.0, 4.0, 0.0]])
    assert not np.isnan(result).any()
    assert result[0].tolist() == [0.0, 0.0, 0.0]
    assert result[1].tolist() == pytest.approx([0.6, 0.8, 0.0])


def test_scoring_is_correct_across_block_boundaries(home, monkeypatch):
    """The blocked dot product must not lose or misalign rows."""
    import store as store_mod

    monkeypatch.setattr(store_mod, "_SCORE_BLOCK", 4)
    with store_mod.VectorStore(config.index_dir(home), dim=3) as store:
        for index in range(11):
            # Gaps wide enough that float16 rounding cannot reorder them.
            add(store, f"/repo/f{index:02d}.py", [1.0, index / 5.0, 0.0])
        hits = store.search([1.0, 0.0, 0.0], k=11)
        assert [h.path for h in hits] == [f"/repo/f{i:02d}.py" for i in range(11)]


def test_wrong_dimension_vectors_are_refused(tiny):
    with pytest.raises(ValueError):
        add(tiny, "/repo/x.py", [1.0, 0.0])


def test_mismatched_record_and_vector_counts_are_refused(tiny):
    with pytest.raises(ValueError):
        tiny.add(
            [ChunkRecord("/repo/x.py", 1, 5, "sha", 1.0, 10)],
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        )
