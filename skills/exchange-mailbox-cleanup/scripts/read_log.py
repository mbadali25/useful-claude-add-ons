#!/usr/bin/env python3
"""Read back a log or CSV the Exchange scripts wrote, decoding defensively.

Standard library only. Never touches the tenant.

Why this exists: under Windows PowerShell 5.1 the five Exchange scripts write their
``*.csv`` with ``Export-Csv -Encoding UTF8`` (UTF-8 **with a BOM**) but write their
``*.log`` with ``Add-Content`` and **no** ``-Encoding``, which lands in the ANSI code page
(cp1252). No parameter the skill prints can change that - it is inside the scripts. A
reader that assumes UTF-8 turns every accented display name, smart quote or em dash into
mojibake silently, with no error.

So: open as bytes, try ``utf-8-sig`` (strict), fall back to ``cp1252``. Say which one won.

Usage:
    read_log.py C:\\scripts\\logs\\Invoke-M365OffboardingHold-20260910.log
    read_log.py C:\\scripts\\logs\\Test-MailboxPreservation-20260910.log --tail 40
    read_log.py C:\\scripts\\logs\\MailboxPreservation-202609101455.csv --grep NotPreserved
    read_log.py <file> --json          # {"encoding": ..., "lines": [...]} for the skill to parse

Exit codes:
    0  read and decoded
    2  file missing or unreadable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _looks_like_utf16(raw: bytes) -> str | None:
    """Detect BOM-less UTF-16 by NUL position, or return None.

    A BOM is the easy case and is handled by the caller. This covers the file that
    lost its BOM in transit, or was written by something other than Out-File: ASCII
    text encoded UTF-16LE is 'A\\x00B\\x00', so the NULs sit at odd offsets and at
    even offsets for UTF-16BE. Without this, cp1252 decodes it 'successfully' into
    'A B C' with the NULs shown as spaces, exit 0, and nobody is told - which is the
    silent-wrong-answer failure this whole reader exists to prevent.
    """
    head = raw[:4096]
    if b"\x00" not in head or len(head) < 4:
        return None
    odd = sum(1 for i in range(1, len(head), 2) if head[i] == 0)
    even = sum(1 for i in range(0, len(head), 2) if head[i] == 0)
    half = len(head) // 2
    if half and odd / half > 0.3 and odd > even:
        return "utf-16-le"
    if half and even / half > 0.3 and even > odd:
        return "utf-16-be"
    return None


def decode(raw: bytes) -> tuple[str, str]:
    """Return (text, encoding_used).

    Order matters. UTF-16 is checked before the cp1252 fallback because cp1252
    never raises - it will happily turn UTF-16 into interleaved NULs and report
    success.
    """
    # 1. Explicit UTF-16 BOM. Unambiguous, so it wins outright.
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"

    # 2. BOM-less UTF-16, by NUL position. THIS MUST COME BEFORE UTF-8.
    #
    #    NUL is U+0000 -- a perfectly valid UTF-8 codepoint -- so strict UTF-8
    #    does NOT raise on UTF-16-encoded ASCII. `"Mailbox preserved"` encoded
    #    UTF-16LE decodes as utf-8-sig into "M\x00a\x00i\x00l..." and is
    #    reported as UTF-8, exit 0. Every character in a normal log line is
    #    ASCII, so this is the COMMON case, not an edge case.
    #
    #    An earlier version of this function tried UTF-8 first and was tested
    #    only with fixtures containing accented characters -- those DO make
    #    UTF-8 raise, so the tests passed while the real case stayed broken.
    #    Order matters more than the individual checks.
    guess = _looks_like_utf16(raw)
    if guess:
        try:
            return raw.decode(guess), guess
        except UnicodeDecodeError:
            pass

    # 3. UTF-8, with or without a BOM. Strict, so a wrong guess raises rather than
    #    producing mojibake. This is what `Export-Csv -Encoding UTF8` writes on 5.1.
    try:
        return raw.decode("utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        pass

    # 4. cp1252 - what `Add-Content` with no -Encoding writes under 5.1. Never fails,
    #    so it must stay last.
    return raw.decode("cp1252", errors="replace"), "cp1252"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("path", help="log or CSV file under C:\\scripts\\logs or C:\\scripts\\reports")
    ap.add_argument("--tail", type=int, metavar="N", help="only the last N lines")
    ap.add_argument("--grep", metavar="TEXT", help="only lines containing TEXT (case-insensitive)")
    ap.add_argument("--json", action="store_true", help="emit {encoding, path, lines} as JSON")
    args = ap.parse_args()

    # Emit UTF-8 regardless of the console code page, or a cp1252 console re-mangles the
    # very characters this script exists to decode correctly - in --json mode too.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = Path(args.path)
    try:
        raw = p.read_bytes()
    except OSError as exc:
        print(f"ERROR  could not read {p}: {exc}", file=sys.stderr)
        return 2

    text, enc = decode(raw)
    lines = text.splitlines()
    if args.grep:
        needle = args.grep.lower()
        lines = [ln for ln in lines if needle in ln.lower()]
    if args.tail:
        lines = lines[-args.tail:]

    if args.json:
        print(json.dumps({"path": str(p.resolve()), "encoding": enc, "lines": lines}, indent=2, ensure_ascii=False))
    else:
        print(f"# {p.resolve()}  ({enc}, {len(lines)} line(s) shown)", file=sys.stderr)
        for ln in lines:
            print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
