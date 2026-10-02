"""The `.crew/metrics.md` row for one recorded review round (L-0578).

WHY CODE, NOT PROSE. /crew:review's step 6 used to ask the agent to append
`<date> | <ticket> | <reviewer> | <n BLOCK> | <n FIX>` after the verdict, the
notify and the PR review. Measured 2026-10-01: 162 rounds in the ledgers, 59
scored rows in the main checkout's file, 27 of 49 tickets with no row
anywhere. `review_run.finish` now calls `record` as soon as the ledger has
accepted the round, before review.json is written.

AT MOST ONCE, NOT EXACTLY ONCE. The ledger refuses a second record of a round
and the row is written only after it accepts, so a round never gets two rows
from here. A process killed between the ledger write and this append loses the
row while the ledger keeps the round; the window is one function call, and the
ledger stays the authority a backfill can rebuild from.

WHERE. The main checkout's `.crew/metrics.md`, also from a linked worktree.
`.crew/*` is gitignored, so each worktree has its own `.crew/`; 25 rows written
from lanes sat in lane worktrees that the main checkout's `/crew:status` never
reads and that are deleted with the lane. The main checkout is
`crew_common._main_checkout`'s answer, the resolver repo config already uses
(T-0088): a linked worktree's main checkout, else `root` itself (a plain
checkout, a submodule, a bare common directory, not a repository). When git
cannot tell, NOTHING is written - a row in the lane's own file is the stranded
row this module exists to stop - and the printed line quotes the row to append
by hand to the main checkout's file.

THE ROW. `<UTC date> | <ticket> | <provider>/<model> (r<N>, <std>, <family>[,
refunded]) | <BLOCK> | <FIX>`. `<std>` is `std:<first 8 of the standards
digest>`, `std:none` (the self-check is not required for this ticket, or an
active incident stood it down) or `std:unknown` (it could not be computed:
on neither side of `crew_standards.metric`). `<family>` is
`same-family: codex limit` for a Claude round run because Codex hit a limit -
the round before recorded one (`review_limit`'s marker names round N-1), or the
caller passes `--note codex-probe=5`, the probe's exit (a limit the probe found
live records no marker) -
else the reviewer family against `crew_state.author_families`:
`same-family` (named among the author families, from any source),
`different family` (only when a dispatch record proves the author families),
`different family unproven` (the author families came from config, a stale
record, or a record that would not fully parse) or `family unknown` (no
reviewer or author family), each followed by `author from <source>`. An
INCOMPLETE round's count cells are `INCOMPLETE`, never `0`: a round that
produced no verdict found nothing only in the sense that nobody looked, and
`crew_state.read_metrics` skips a non-numeric cell. A `|` inside a cell is
written as `/`.

FAILURE. Nothing here may change a round's verdict or exit code: `record`
catches every exception and returns a `review:` line naming it and quoting the
exact row to append by hand. A write cut short after some bytes landed says so,
so the partial row is replaced rather than a second row added beside it; a
close that fails after every byte landed says the row IS written.

LINKS AND SPECIAL FILES. The checkout decides what `.crew` and
`.crew/metrics.md` are. A symlinked `.crew` directory or metrics file, or a
metrics path that is not a regular file (a FIFO would block forever after the
ledger has recorded the round), is refused: nothing followed, nothing written,
the row quoted. The open uses O_NOFOLLOW and O_NONBLOCK where the platform has
them, and the descriptor is checked to be a regular file before anything is
read or written.
"""
import datetime
import json
import os
import stat

import crew_common
import crew_incident
import crew_standards
import crew_state
import review_ledger
import review_limit

CODEX_LIMIT = "same-family: codex limit"
# What /crew:review step 2c passes as --note when the probe answered limited (exit 5).
PROBE_LIMITED_NOTE = "codex-probe=5"


def metrics_path(root):
    """(path, problem). The main checkout's `.crew/metrics.md` for a linked
    worktree, else `root`'s. `problem` is non-empty when git could not tell
    which, and then `path` is None."""
    main_root, problem = crew_common._main_checkout(root)  # pylint: disable=protected-access
    if problem:
        return None, problem
    return os.path.join(main_root or root, ".crew", "metrics.md"), ""


def std_token(root, ticket, manifest_path):
    """`std:<8>`, `std:none` or `std:unknown` - see THE ROW."""
    try:
        problems, note = crew_standards.review_gate(root, ticket, manifest_path)
        if problems:
            incident = crew_incident.read_state(root, crew_state.load_config(root))
            return "std:none" if incident.get("active") else "std:unknown"
    except Exception:  # pylint: disable=broad-except  # noqa: BLE001 - any failure is unknown
        return "std:unknown"
    marker = "std:"
    if note and marker in note:
        token = note.split(marker, 1)[1][:8]
        return marker + token if len(token) == 8 else "std:unknown"
    return "std:none"


def family_relation(reviewer_family, families, source):
    """The reviewer's family against the author's - see THE ROW."""
    if reviewer_family and reviewer_family in families:
        relation = "same-family"
    elif not reviewer_family or not families:
        relation = "family unknown"
    elif source == "dispatch":
        relation = "different family"
    else:
        relation = "different family unproven"
    return f"{relation}, author from {source or 'unknown'}"


def _codex_limit_before(root, ticket, number):
    try:
        with open(review_limit.marker_path(root, ticket), encoding="utf-8") as handle:
            mark = json.load(handle)
    except (OSError, ValueError, review_ledger.LedgerError):
        # No marker, or one that cannot be read: the relation below still
        # names the reviewer's family against the author's, so nothing is
        # claimed that was not checked.
        return False
    previous = mark.get("round") if isinstance(mark, dict) else None
    return isinstance(previous, int) and not isinstance(previous, bool) \
        and previous == number - 1


def family_tag(root, ticket, number, provider, reviewer_family, note=""):
    """The family part of the reviewer cell - see THE ROW. May raise."""
    said = (note or "").split()
    if provider == "claude" and (PROBE_LIMITED_NOTE in said
                                 or _codex_limit_before(root, ticket, number)):
        return CODEX_LIMIT
    families, source = crew_state.author_families(root, crew_state.load_config(root))
    return family_relation(reviewer_family, families, source)


def _cell(text):
    return " ".join(str(text).replace("|", "/").split())


def _one_line(value):
    """An exception's text on one line: the `review:` line is one record."""
    return " ".join(str(value).split())


def row(date, ticket, provider, model, number, std, family, verdict, counts, refunded):
    """One metrics.md line, without a trailing newline."""
    notes = [f"r{number}", std, family] + (["refunded"] if refunded else [])
    reviewer = _cell(f"{provider}/{model or 'default'} ({', '.join(notes)})")
    if verdict in ("CLEAN", "FINDINGS"):
        block, fix = int(counts.get("BLOCK") or 0), int(counts.get("FIX") or 0)
    else:
        block = fix = "INCOMPLETE"
    return f"{_cell(date)} | {_cell(ticket)} | {reviewer} | {block} | {fix}"


class PartialWrite(OSError):
    """Some of the row's bytes reached the file before the write failed."""


class NotARegularFile(OSError):
    """The metrics path, or its `.crew` directory, is a symlink or not a plain
    file. Nothing is followed and nothing is written."""


_OPEN_FLAGS = (os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
               | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))


def _refuse_links(path):
    """Refuse a symlinked `.crew` directory or metrics file, and anything at
    the path that is not a regular file: the checkout decides what these are,
    and a writer that follows them appends to a file outside it, or blocks
    forever on a FIFO after the ledger has already recorded the round."""
    parent = os.path.dirname(path)
    if os.path.islink(parent):
        raise NotARegularFile(f"{parent} is a symlink; not following it")
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISREG(mode):
        raise NotARegularFile(f"{path} is not a regular file; not writing through it")


def append(path, line):
    """Append `line` and a newline, after a newline if the file does not end
    in one, through one O_APPEND descriptor that follows no symlink and never
    blocks on a FIFO, looping on a short write. Returns "" or, when the close
    failed AFTER every byte landed, that error - the row IS written. Raises
    NotARegularFile or OSError before any byte lands, PartialWrite after."""
    _refuse_links(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _refuse_links(path)
    fd = os.open(path, _OPEN_FLAGS, 0o644)
    done = 0
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise NotARegularFile(f"{path} is not a regular file; not writing through it")
        prefix = ""
        if os.fstat(fd).st_size:
            os.lseek(fd, -1, os.SEEK_END)
            prefix = "" if os.read(fd, 1) == b"\n" else "\n"
        data = (prefix + line + "\n").encode("utf-8")
        while done < len(data):
            try:
                wrote = os.write(fd, data[done:])
            except OSError as exc:
                if done:
                    raise PartialWrite(f"{done} of {len(data)} bytes written: {exc}") from exc
                raise
            if wrote <= 0:
                raise PartialWrite(f"{done} of {len(data)} bytes written: write returned {wrote}")
            done += wrote
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    try:
        os.close(fd)
    except OSError as exc:
        return _one_line(exc)
    return ""


def record(root, ticket, number, review, manifest_path, note=""):
    """Write this round's row; return the `review:` line to print. Never raises."""
    try:
        date = str(review.get("written_at") or "")[:10] or \
            datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        line = row(date, ticket, review.get("provider"), review.get("model"), number,
                   std_token(root, ticket, manifest_path),
                   family_tag(root, ticket, number, review.get("provider"),
                              review.get("model_family"), note),
                   review.get("verdict"), review.get("counts") or {},
                   review.get("refunded") is True)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 - keep the verdict
        return (f"review: metrics row NOT written (could not build it: {_one_line(exc)}); "
                f"round {number} is in the ledger")
    try:
        path, problem = metrics_path(root)
        if problem:
            return (f"review: metrics row NOT written ({_one_line(problem)}); append it by hand to the "
                    f"main checkout's .crew/metrics.md: {line}")
        closed = append(path, line)
    except PartialWrite as exc:
        return (f"review: metrics row PARTLY written to {path} ({_one_line(exc)}); replace the partial "
                f"last line by hand with: {line}")
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 - keep the verdict
        return f"review: metrics row NOT written ({_one_line(exc)}); append it by hand: {line}"
    if closed:
        return (f"review: metrics row appended to {path} (closing it then failed: {closed}; "
                "the row is written - do not append it again)")
    return f"review: metrics row appended to {path}"
