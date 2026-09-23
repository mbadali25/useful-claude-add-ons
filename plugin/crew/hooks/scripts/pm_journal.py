"""Append-only writer/reader for the PM journal and standing files.

Replaces the quoted heredoc `agents/pm.md` used to prescribe for the append
(a shell `cat`, redirected onward, with a `CREW_EOF` closing delimiter).
That form was accepted as a Codex BLOCK finding
(`plugin/crew/agents/pm.md:941`): the fixed delimiter is still a shell
heredoc, and a veto reason or decision text containing a line reading
exactly that delimiter closes it early and lets whatever follows run as a
shell command, quoting notwithstanding. This module removes the shell from
the append path entirely: the caller writes the entry to a plain file under
`.work/` with the `Write` tool (no shell involved at all), and this script
moves those bytes into the target file itself, with one `os.open`/`os.write`
call and nothing that interpolates or interprets shell syntax anywhere in
the path.

Usage:
    python3 pm_journal.py --root <repo> --append {journal|standing} --from <entry-file>
    python3 pm_journal.py --root <repo> --read {journal|standing}

`--from` must resolve to a file inside `<root>/.work/` -- never anywhere
else, and never a shell-expanded path. The entry file is deleted after a
successful append; it is left in place on any refusal, so the caller can
inspect or fix it.

Refuses, with a non-zero exit and a stderr message, rather than doing any of
these:
  - appending or reading anything outside a real crew repo -- `isCrew` from
    `crew_state.collect(root)` must be true AND `<root>/.crew` must already
    exist as a directory. This script never creates `.crew/`; a `False` here
    is a refusal, not a provisioning step. `/crew:init` is what creates a
    crew, not a journal append.
  - an empty entry
  - an entry file outside `<root>/.work/`
  - a `standing` entry spanning more than one line -- standing is "one line
    per still-live decision, veto, or onboard/offboard ruling"
    (`agents/pm.md`), and a multi-line standing entry breaks that shape.
  - a journal/standing TARGET that escapes containment -- `<root>/.crew`
    itself is a symlink resolving outside `<root>`, or `pm-journal.md` /
    `pm-standing.md` is a symlink at all (regardless of where it points), or
    the target's resolved path is not inside the resolved `.crew` directory.
    Checked with `os.path.realpath` before anything is opened, on both
    `--append` and `--read`; the actual `os.open()` call additionally passes
    `O_NOFOLLOW` on POSIX (absent on Windows, so unavailable there) to close
    the gap between that check and the open.

Every append normalises the entry to exactly one trailing newline, UTF-8, LF
only (Python's universal-newlines text read already collapses CRLF/CR to LF
on the way in, so nothing downstream reintroduces one), and computes the
full byte payload BEFORE opening the target file -- CLAUDE.md's
`open(p, "w")`-truncates-before-the-payload-exists landmine, guarded against
here even though this path only ever opens in append mode. The write itself
is one `os.open(..., O_WRONLY | O_APPEND | O_CREAT | O_NOFOLLOW, 0o644)`
plus one `os.write` -- append is atomic enough for a single small write on
every platform this runs on, and there is no partial-write recovery to
reason about because there is only ever one write call.

A journal entry gets a `## <UTC timestamp>` header line prepended by this
script, not typed by the caller -- so the journal's own ordering and date
stamps do not depend on a caller getting the date right. `--read journal`
uses that header to split the file back into entries and returns the tail:
the last 40 entries, or the last 200 lines, whichever is the smaller
result -- entries are dropped oldest-first until both bounds hold at once.
`--read standing` returns the whole file: standing has no bound, by design
(`agents/pm.md` and `crew-pm/SKILL.md` both say "read in full").
"""

import argparse
import os
import re
import sys
import time

import crew_state

JOURNAL_NAME = "pm-journal.md"
STANDING_NAME = "pm-standing.md"

# The two knobs behind "last 40 entries or 200 lines, whichever is smaller."
_MAX_JOURNAL_ENTRIES = 40
_MAX_JOURNAL_LINES = 200

# A journal entry's own header line, written by THIS script (never the
# caller), one per appended entry: "## 2026-09-23T18:04:11Z".
_JOURNAL_HEADER_RE = re.compile(
    r"(?m)^## \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
)

# POSIX-only; absent from the `os` module on Windows. Passed into every
# os.open() below (bitwise-OR'd in as 0 where unavailable) to close the
# check-then-open race between `_containment_refusal`'s os.path.islink
# check and the actual open -- without it, a symlink swapped in between the
# two would still be followed.
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _target_path(root, kind):
    name = JOURNAL_NAME if kind == "journal" else STANDING_NAME
    return os.path.join(root, ".crew", name)


def _crew_ready(root):
    """True only for a real, already-provisioned crew repo.

    Checks BOTH `isCrew` and that `.crew/` actually exists as a directory --
    belt and suspenders, since `crew_state.collect` already implies the
    second from the first, but a caller of this function must never be able
    to make it return True for a directory with no `.crew/` to write into.
    Never creates `.crew/` itself, on any branch.
    """
    crew_dir = os.path.join(root, ".crew")
    if not os.path.isdir(crew_dir):
        return False
    try:
        state = crew_state.collect(root)
    except Exception:  # pylint: disable=broad-except
        # `collect` is documented as "never raises," but this script must
        # fail closed (refuse) rather than crash if that guarantee is ever
        # broken by something upstream -- an unknown must not read as ready.
        return False
    return bool(state.get("isCrew"))


def _containment_refusal(root, kind):
    """None if `<root>/.crew`'s `<kind>` target is safe to open; otherwise a
    ready-to-print stderr message.

    Three checks, all against `os.path.realpath` so a chain of symlinks
    cannot hide the real destination:
      - `.crew` itself must not be a symlink resolving outside `root` --
        that would let a repo redirect every journal/standing write
        somewhere the caller never agreed to.
      - the target (`pm-journal.md` / `pm-standing.md`) must not be a
        symlink at all -- refused unconditionally, even if it happens to
        point back inside `.crew`, because the write should only ever land
        on a plain file this script itself created.
      - the target's resolved path must still be inside the resolved
        `.crew` directory (belt-and-suspenders once the two checks above
        hold, but catches anything the other checks did not anticipate).

    This is the check half of the guard; it still leaves a gap between the
    check and the eventual `open()`/`os.open()` call, which is what
    `O_NOFOLLOW` at the actual open closes on POSIX.
    """
    crew_dir = os.path.join(root, ".crew")
    real_root = os.path.realpath(root)
    real_crew_dir = os.path.realpath(crew_dir)
    if os.path.islink(crew_dir) and real_crew_dir != real_root and not (
        real_crew_dir.startswith(real_root + os.sep)
    ):
        return (
            f"pm_journal: refusing -- '.crew' is a symlink resolving "
            f"outside {real_root}"
        )

    target = _target_path(root, kind)
    if os.path.islink(target):
        return f"pm_journal: refusing -- {target} is a symlink"

    real_target = os.path.realpath(target)
    if real_target != real_crew_dir and not real_target.startswith(
        real_crew_dir + os.sep
    ):
        return f"pm_journal: refusing -- target escapes {real_crew_dir}"

    return None


def _resolve_entry_path(root, from_arg):
    """Absolute, symlink-resolved path of `--from`, or None if it does not
    land inside `<root>/.work/`. Resolution happens on the path alone --
    it does not require the file to exist yet, so a refusal here never
    depends on what is or is not on disk."""
    work_dir = os.path.realpath(os.path.join(root, ".work"))
    candidate = from_arg if os.path.isabs(from_arg) else os.path.join(root, from_arg)
    candidate = os.path.realpath(candidate)
    if candidate == work_dir or not candidate.startswith(work_dir + os.sep):
        return None
    return candidate


def _normalise_one_trailing_newline(text):
    return text.rstrip("\n") + "\n"


def _utc_timestamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _build_payload(kind, text):
    """The full byte payload for one append, computed entirely before any
    file is opened."""
    body = _normalise_one_trailing_newline(text)
    if kind == "journal":
        return f"## {_utc_timestamp()}\n{body}".encode("utf-8")
    return body.encode("utf-8")


def append_entry(root, kind, from_arg):
    if not _crew_ready(root):
        print(
            "pm_journal: refusing -- not a crew repo (isCrew is false, or "
            "'.crew/' does not exist); this script never creates '.crew/'",
            file=sys.stderr,
        )
        return 2

    refusal = _containment_refusal(root, kind)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    entry_path = _resolve_entry_path(root, from_arg)
    if entry_path is None:
        print(
            f"pm_journal: --from must resolve inside "
            f"{os.path.join(root, '.work')}, got {from_arg!r}",
            file=sys.stderr,
        )
        return 2

    try:
        with open(entry_path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"pm_journal: could not read {from_arg}: {exc}", file=sys.stderr)
        return 2

    text = raw.strip("\n")
    if not text.strip():
        print("pm_journal: refusing an empty entry", file=sys.stderr)
        return 2

    if kind == "standing" and "\n" in text:
        print(
            "pm_journal: standing entries must be a single line -- "
            f"got {text.count(chr(10)) + 1} lines",
            file=sys.stderr,
        )
        return 2

    payload = _build_payload(kind, text)  # computed before opening anything

    target = _target_path(root, kind)
    try:
        fd = os.open(
            target,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | _O_NOFOLLOW,
            0o644,
        )
    except OSError as exc:
        print(
            f"pm_journal: refusing -- could not open {target} safely: {exc}",
            file=sys.stderr,
        )
        return 2
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)

    os.unlink(entry_path)
    return 0


def _split_journal_entries(text):
    """Whole journal text -> list of entry strings, each starting at its own
    `## <timestamp>` header and running up to (not including) the next.
    Content written before this script existed, with no header at all,
    comes back as a single legacy entry rather than being dropped."""
    if not text:
        return []
    starts = [m.start() for m in _JOURNAL_HEADER_RE.finditer(text)]
    if not starts:
        return [text]
    starts.append(len(text))
    return [text[starts[i]:starts[i + 1]] for i in range(len(starts) - 1)]


def _tail_journal(text):
    """Last 40 entries or 200 lines, whichever is smaller: apply both bounds
    together, dropping the oldest selected entry until neither is exceeded.
    Entries are dropped whole, never mid-entry, so a returned tail is always
    a sequence of complete, parseable entries."""
    entries = _split_journal_entries(text)
    selected = entries[-_MAX_JOURNAL_ENTRIES:]
    while len(selected) > 1 and sum(
        e.count("\n") for e in selected
    ) > _MAX_JOURNAL_LINES:
        selected = selected[1:]
    return "".join(selected)


def read_entries(root, kind):
    if not _crew_ready(root):
        print(
            "pm_journal: refusing -- not a crew repo (isCrew is false, or "
            "'.crew/' does not exist); this script never creates '.crew/'",
            file=sys.stderr,
        )
        return 2

    refusal = _containment_refusal(root, kind)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

    path = _target_path(root, kind)
    try:
        fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
    except FileNotFoundError:
        # A crew with nothing dispatched or ruled on yet is not an error.
        text = ""
    except OSError as exc:
        print(f"pm_journal: could not read {path}: {exc}", file=sys.stderr)
        return 2
    else:
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            text = handle.read()

    if kind == "journal":
        text = _tail_journal(text)

    sys.stdout.write(text)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pm_journal")
    parser.add_argument("--root", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--append", choices=("journal", "standing"))
    mode.add_argument("--read", choices=("journal", "standing"))
    parser.add_argument(
        "--from", dest="from_path", default=None,
        help="entry file under <root>/.work/, required with --append",
    )
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)

    if args.append:
        if not args.from_path:
            print("pm_journal: --append requires --from <entry-file>", file=sys.stderr)
            return 2
        return append_entry(root, args.append, args.from_path)

    return read_entries(root, args.read)


if __name__ == "__main__":
    raise SystemExit(main())
