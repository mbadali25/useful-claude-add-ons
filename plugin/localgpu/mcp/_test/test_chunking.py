"""Window size, overlap, and the awkward files: tail, tiny, empty."""

from __future__ import annotations

import pytest
from conftest import lines

from indexer import OVERLAP_LINES, WINDOW_LINES, chunk_lines, read_text_file


def spans(chunks):
    return [(c.start_line, c.end_line) for c in chunks]


def test_defaults_are_the_documented_ones():
    assert (WINDOW_LINES, OVERLAP_LINES) == (60, 15)


def test_empty_file_yields_nothing():
    assert chunk_lines([]) == []


def test_tiny_file_is_one_chunk():
    chunks = chunk_lines(lines(3))
    assert spans(chunks) == [(1, 3)]
    assert chunks[0].text == "line 1\nline 2\nline 3\n"


def test_exactly_one_window_is_one_chunk():
    assert spans(chunk_lines(lines(60))) == [(1, 60)]


def test_one_line_over_a_window_adds_a_short_tail():
    assert spans(chunk_lines(lines(61))) == [(1, 60), (46, 61)]


def test_windows_step_by_window_minus_overlap():
    assert spans(chunk_lines(lines(150))) == [(1, 60), (46, 105), (91, 150)]


def test_consecutive_windows_share_exactly_the_overlap():
    chunks = chunk_lines(lines(300))
    for previous, following in zip(chunks, chunks[1:]):
        shared = previous.end_line - following.start_line + 1
        assert shared == OVERLAP_LINES


def test_every_line_appears_in_some_chunk():
    source = lines(137)
    covered = set()
    for chunk in chunk_lines(source):
        covered.update(range(chunk.start_line, chunk.end_line + 1))
    assert covered == set(range(1, 138))


def test_last_chunk_ends_on_the_last_line():
    for count in (1, 46, 59, 60, 61, 104, 105, 106, 500):
        chunks = chunk_lines(lines(count))
        assert chunks[-1].end_line == count, count
        assert chunks[0].start_line == 1


def test_no_chunk_is_wholly_contained_in_the_previous_one():
    chunks = chunk_lines(lines(104))
    assert spans(chunks) == [(1, 60), (46, 104)]
    assert chunks[-1].end_line > chunks[0].end_line


def test_chunk_text_is_the_lines_verbatim():
    source = lines(70)
    chunk = chunk_lines(source)[1]
    assert chunk.text == "".join(source[chunk.start_line - 1 : chunk.end_line])


def test_custom_window_and_overlap():
    assert spans(chunk_lines(lines(10), window=4, overlap=1)) == [
        (1, 4),
        (4, 7),
        (7, 10),
    ]


@pytest.mark.parametrize("window,overlap", [(0, 0), (-1, 0), (10, 10), (10, 11), (10, -1)])
def test_nonsense_parameters_are_refused(window, overlap):
    with pytest.raises(ValueError):
        chunk_lines(lines(5), window=window, overlap=overlap)


def test_file_with_no_trailing_newline_keeps_its_last_line(tmp_path):
    path = tmp_path / "a.py"
    path.write_bytes(b"one\ntwo")
    read = read_text_file(path)
    assert read == ["one\n", "two"]
    assert spans(chunk_lines(read)) == [(1, 2)]


def test_binary_and_oversized_files_are_not_text(tmp_path, monkeypatch):
    binary = tmp_path / "b.bin"
    binary.write_bytes(b"MZ\x00\x00payload")
    assert read_text_file(binary) is None

    import indexer

    monkeypatch.setattr(indexer, "MAX_FILE_BYTES", 8)
    big = tmp_path / "big.py"
    big.write_text("x" * 64, encoding="utf-8")
    assert read_text_file(big) is None


def test_empty_file_on_disk_reads_as_no_lines(tmp_path):
    path = tmp_path / "empty.py"
    path.write_text("", encoding="utf-8")
    assert read_text_file(path) == []
    assert chunk_lines(read_text_file(path)) == []
