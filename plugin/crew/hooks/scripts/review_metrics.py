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
refunded]) | <BLOCK> | <FIX>`. `<std>` is the token the round was RESERVED
under (review round 2): `std:<first 8 of the standards digest>`, or `std:none`
(the self-check is not required for this ticket, or an active incident stood
it down). `review_run.standards_gate` computes it before the reservation; the
same process carries it in memory, and the claude provider's second call reads
it from `<scratch>/reserved-std.json` for this ticket and round. Without that
record the token is `std:unknown` (on neither side of `crew_standards.metric`)
- never a recomputation, which would describe a self-check or standards set the
round was not reserved under. `<family>` is `same-family: codex limit` for a
Claude round run because Codex hit a limit - `review_limit`'s marker records
one in round N-1, or the caller passes `--note codex-probe=5`, the probe's exit
(a limit the probe found live records no marker) - else the reviewer family
against `crew_state.author_families`: `same-family` (named among the author
families, from any source), `different family` (only when a dispatch record
proves the author families), `different family unproven` (the author families
came from config or a stale record) or `family unknown` (no reviewer or author
family, or a source that could not be read: a dispatch record that would not
parse, or `unreadable config` - a config.json that exists but is not a JSON
object, which `load_config` answers with {} exactly as for no config), each
followed by `author from <source>`. A limit marker that cannot be read, or is
not the shape `review_limit.record` writes, adds `codex-limit marker
unreadable` and is never read as a limit. An INCOMPLETE round's count cells
are `INCOMPLETE`, never `0`: a round that produced no verdict found nothing
only in the sense that nobody looked, and `crew_state.read_metrics` skips a
non-numeric cell. A `|` inside a cell is written as `/`.

FAILURE. Nothing here may change a round's verdict or exit code: `record`
catches every exception and returns a `review:` line naming it and quoting the
exact row to append by hand. A write cut short after some bytes landed says so,
so the partial row is replaced rather than a second row added beside it; a
close that fails after every byte landed says the row IS written.

LINKS AND SPECIAL FILES. The checkout decides what `.crew` and
`.crew/metrics.md` are, and what the limit marker is. A linked `.crew`
directory (symlink, or on Windows any reparse point such as a junction), a
linked metrics file, or a path that is not a regular file (a FIFO would block
forever after the ledger has recorded the round) is refused: nothing followed,
nothing written, the row quoted. On POSIX the directory is opened
O_DIRECTORY|O_NOFOLLOW and the file O_NOFOLLOW relative to that descriptor, so
a link swapped in after the pre-check is not followed either. Windows has no
dir_fd open: the directory is re-checked immediately before the open, and the
window left between that check and the open is accepted risk (L-0578
amendment 2). Reads (the marker, config.json) are O_NOFOLLOW|O_NONBLOCK and
checked to be a regular file before any byte is read.
"""
import datetime
import json
import os
import re
import stat

import crew_common
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


RESERVED_STD_FILE = "reserved-std.json"
_STD_RE = re.compile(r"^std:(?:[0-9a-f]{8}|none)$")
MARKER_UNREADABLE = "unreadable"
_MARKER_MAX_BYTES = 64 * 1024
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_READ_FLAGS = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
               | getattr(os, "O_BINARY", 0))


def std_from_note(note):
    """The std: token for `crew_standards.review_gate`'s note when it found no
    problem: `std:<8>` when the self-check is current, `std:none` when it is
    not required."""
    marker = "std:"
    if note and marker in note:
        token = marker + note.split(marker, 1)[1][:8]
        return token if _STD_RE.match(token) else "std:unknown"
    return "std:none"


def reserved_std(args, number):
    """The std: token this round was RESERVED under - see THE ROW. In memory
    when the same process reserved it, else `<scratch>/reserved-std.json`
    naming this ticket and round. Anything else is `std:unknown`: a token
    recomputed after the review describes a self-check or standards set the
    round was not reserved under."""
    token = getattr(args, "reserved_std", None)
    if token is None:
        try:
            with open(os.path.join(args.scratch, RESERVED_STD_FILE), encoding="utf-8") as fh:
                kept = json.load(fh)
        except (OSError, ValueError):
            return "std:unknown"
        if not isinstance(kept, dict) or kept.get("ticket") != args.ticket \
                or kept.get("round") != number or isinstance(kept.get("round"), bool):
            return "std:unknown"
        token = kept.get("std")
    return token if isinstance(token, str) and _STD_RE.match(token) else "std:unknown"


def family_relation(reviewer_family, families, source):
    """The reviewer's family against the author's - see THE ROW."""
    if reviewer_family and reviewer_family in families:
        relation = "same-family"
    elif not reviewer_family or not families:
        relation = "family unknown"
    elif source == "dispatch":
        relation = "different family"
    elif source in ("config", "stale"):
        relation = "different family unproven"
    else:
        relation = "family unknown"
    return f"{relation}, author from {source or 'unknown'}"


def _read_regular(path):
    """The bytes of `path` if it is a regular file, read without following a
    link or blocking; None when absent. Raises OSError/NotARegularFile."""
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise NotARegularFile(f"{path} is not a regular file")
    except FileNotFoundError:
        return None
    fd = os.open(path, _READ_FLAGS)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise NotARegularFile(f"{path} is not a regular file")
        return os.read(fd, _MARKER_MAX_BYTES + 1)
    finally:
        os.close(fd)


def codex_limit_before(root, ticket, number):
    """True when `review_limit`'s marker records a Codex limit in round N-1,
    False when there is no marker or it names another round, MARKER_UNREADABLE
    when it cannot be read or is not the shape `review_limit.record` writes (a
    FIFO, a link, malformed JSON, a missing provider or error). Never blocks;
    an unreadable marker is never read as a limit."""
    try:
        data = _read_regular(review_limit.marker_path(root, ticket))
    except (OSError, review_ledger.LedgerError):
        return MARKER_UNREADABLE
    if data is None:
        return False
    try:
        mark = json.loads(data.decode("utf-8")) if len(data) <= _MARKER_MAX_BYTES else None
    except (UnicodeDecodeError, ValueError):
        return MARKER_UNREADABLE
    if not isinstance(mark, dict):
        return MARKER_UNREADABLE
    previous, provider, error = mark.get("round"), mark.get("provider"), mark.get("error")
    if not isinstance(previous, int) or isinstance(previous, bool) or provider != "codex" \
            or not isinstance(error, str) or not error.strip():
        return MARKER_UNREADABLE
    return previous == number - 1


def config_unreadable(root):
    """True when the repo config `crew_state.load_config` reads exists but
    cannot be read as a JSON object, or git cannot tell which one is in force:
    load_config answers {} for both, the same as no config at all."""
    _crew_dir, source, _detail = crew_common.repo_config_dir(root)
    if source == crew_common.SOURCE_UNKNOWN:
        return True
    path = crew_common.repo_config_file(root, "config.json")
    if not os.path.lexists(path):
        return False
    try:
        data = _read_regular(path)
        parsed = json.loads(data.decode("utf-8")) if data is not None else None
    except (OSError, UnicodeDecodeError, ValueError):
        return True
    return not isinstance(parsed, dict)


def family_tag(root, ticket, number, provider, reviewer_family, note=""):
    """The family part of the reviewer cell - see THE ROW. May raise."""
    limit = codex_limit_before(root, ticket, number) if provider == "claude" else False
    if provider == "claude" and (PROBE_LIMITED_NOTE in (note or "").split() or limit is True):
        return CODEX_LIMIT
    families, source = crew_state.author_families(root, crew_state.load_config(root))
    if source == "config" and config_unreadable(root):
        source = "unreadable config"
    tag = family_relation(reviewer_family, families, source)
    return tag + (", codex-limit marker unreadable" if limit == MARKER_UNREADABLE else "")


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


def is_link_or_junction(path):
    """True for a symlink, or on Windows any reparse point (a junction is one
    and `os.path.islink` says False for it); False when absent."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0)
                                            & _REPARSE_POINT)


def _refuse_links(path):
    """Refuse a linked `.crew` directory (symlink or junction) or metrics file,
    and anything at the path that is not a regular file: the checkout decides
    what these are, and a writer that follows them appends to a file outside
    it, or blocks forever on a FIFO after the ledger has recorded the round.
    A pre-check only: `_open_in` is what closes the race on POSIX."""
    parent = os.path.dirname(path)
    if is_link_or_junction(parent):
        raise NotARegularFile(f"{parent} is a link or junction; not following it")
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISREG(mode):
        raise NotARegularFile(f"{path} is not a regular file; not writing through it")


def _open_in(path):
    """Open `path` for append without following a link at the `.crew`
    directory or at the file. POSIX: the directory is opened O_NOFOLLOW and the
    file relative to that descriptor, so nothing swapped in after the
    pre-check is followed. Elsewhere (Windows): the directory is re-checked for
    a reparse point immediately before the open; the window that leaves is the
    accepted risk (L-0578 amendment 2)."""
    parent, name = os.path.split(path)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if nofollow and directory and os.open in os.supports_dir_fd:
        dfd = os.open(parent, os.O_RDONLY | directory | nofollow)
        try:
            return os.open(name, _OPEN_FLAGS, 0o644, dir_fd=dfd)
        finally:
            try:
                os.close(dfd)
            except OSError:
                pass  # the directory handle only scoped the open; the file's fd is what matters
    if is_link_or_junction(parent):
        raise NotARegularFile(f"{parent} is a link or junction; not following it")
    return os.open(path, _OPEN_FLAGS, 0o644)


def append(path, line):
    """Append `line` and a newline, after a newline if the file does not end
    in one, through one O_APPEND descriptor that follows no symlink and never
    blocks on a FIFO, looping on a short write. Returns "" or, when the close
    failed AFTER every byte landed, that error - the row IS written. Raises
    NotARegularFile or OSError before any byte lands, PartialWrite after."""
    _refuse_links(path)
    try:
        os.mkdir(os.path.dirname(path))
    except FileExistsError:
        pass
    _refuse_links(path)
    fd = _open_in(path)
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


def record(root, ticket, number, review, std, note=""):
    """Write this round's row; return the `review:` line to print. Never raises."""
    try:
        date = str(review.get("written_at") or "")[:10] or \
            datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        line = row(date, ticket, review.get("provider"), review.get("model"), number,
                   std if isinstance(std, str) and _STD_RE.match(std) else "std:unknown",
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
