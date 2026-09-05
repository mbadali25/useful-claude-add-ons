# localgpu MCP tests

Real pytest, no GPU, no Ollama, no network beyond `127.0.0.1`. The embedder is
stubbed (`FakeEmbedder` in `conftest.py`: deterministic bag-of-words vectors),
and `test_ollama.py` runs a stub HTTP server on an ephemeral port instead of
talking to a real one. Every test writes into `tmp_path` with `LOCALGPU_HOME`
pointed there, so nothing touches a real index.

## Running them

Use the interpreter the bootstrap built, not the system one - `numpy` is a hard
dependency of `store.py` and system Python does not have it:

```powershell
& "$env:LOCALAPPDATA\localgpu\venv\Scripts\python.exe" -m pytest plugin/localgpu/mcp/_test
```

```bash
"$HOME/.local/share/localgpu/venv/bin/python" -m pytest plugin/localgpu/mcp/_test
```

Any interpreter with `numpy` will do. Without one the suite fails at import
with `ModuleNotFoundError: No module named 'numpy'` - that is the environment
being wrong, not the code.

`test_server.py` additionally needs the `mcp` SDK and skips itself when it is
absent.

## What each file covers

| File | Covers |
|---|---|
| `test_chunking.py` | 60-line windows with 15-line overlap; tail, tiny, empty, no-trailing-newline, binary and oversized files |
| `test_incremental.py` | the mtime+size fast path, the sha256 confirmation, re-embedding only what changed, ignore globs, the manifest |
| `test_deletion.py` | deleted files tombstoned and gone from results; compaction firing strictly past 20%; rows renumbered without losing which vector belongs to which chunk |
| `test_ranking.py` | cosine order over hand-checked vectors, float16 round-trip, `root` and `path_glob` filters, block-boundary scoring |
| `test_config.py` | `$LOCALGPU_HOME` resolution on both platforms, the two config layers, the ignore union, broken JSON |
| `test_ollama.py` | `keep_alive` on every request, and that "not running" and "not pulled" each name the command that fixes them |
| `test_server.py` | the three tool signatures as registered with MCP, and that `search_code` returns `file:line` with at most three lines - never a file |

## Sabotage log

The suite has been checked against deliberately broken code, and each of these
turned it red:

| Sabotage | What went red |
|---|---|
| compaction threshold `>=` instead of `>` | `test_deleting_one_of_five_stays_under_the_threshold`, `test_threshold_is_strictly_greater_than` |
| chunk step `= window` (overlap dropped) | 5 chunking tests |
| `keep_alive` removed from the request payload | `test_every_request_carries_a_short_keep_alive` |
| old chunks tombstoned *after* the new ones are appended | `test_changed_file_is_re_embedded_and_its_old_chunks_retired`, `test_a_file_growing_past_one_window_gains_chunks` |
