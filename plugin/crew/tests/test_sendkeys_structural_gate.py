"""SAFETY (L-0727 slice 3): the `sendkeys` method, and with it the only code in
the repository that pressed keys through Windows' keystroke API, was removed
in crew 1.2.60 together with `auto-clear.ps1`. Nothing a test run, a hook or a
sabotage run can reach may call that API again unnoticed.

This is a repo-wide scan, not a check of one file: every path `git ls-files`
reports is read from the working tree, and no tracked file other than
documentation, recorded reviewer output under `tests/golden/`, the generated
`graphify-out/` pair and this test itself may contain a keystroke CALL (the
`_KEYSTROKE_CALL` pattern, any case, because PowerShell is case-insensitive).
Prose that merely names the API, and identifiers that merely contain it, are
not calls and are not matched. A scan that read nothing, or could not read a
tracked script, fails rather than passing vacuously.
"""
import os
import re
import subprocess

import context  # noqa: F401  pylint: disable=unused-import

_ROOT = context._ROOT  # pylint: disable=protected-access
_SELF = "plugin/crew/tests/test_sendkeys_structural_gate.py"

# A keystroke-sending CALL:
#  - the SendKeys static type reached with a double colon, with or without the
#    closing bracket of a type literal in front of it;
#  - SendWait or Send after a PowerShell static-member double colon, the
#    member name bare or in single or double quotes, then an opening paren;
#  - SendWait or SendKeys (the WScript.Shell COM method) after a `.`, bare or
#    quoted, then an opening paren.
# A bare `.send(` is deliberately NOT matched: it is every socket, generator
# and HTTP client in the repo. The pattern's own source text does not match
# it (a `(?:` or `|` sits where a call has `::` or `(`).
_KEYSTROKE_CALL = re.compile(
    r"(?:SendKeys\s*\]?\s*::"
    r"|::\s*(['\"]?)(?:SendWait|Send)\1\s*\("
    r"|\.\s*(['\"]?)(?:SendWait|SendKeys)\2\s*\()",
    re.IGNORECASE)

_EXCLUDED_PREFIXES = ("docs/", "graphify-out/", "plugin/crew/tests/golden/")
_DOCUMENTATION = frozenset({".md", ".html", ".docx", ".pdf", ".txt"})

# A tracked file whose BOM names an encoding its bytes then fail to decode as
# is skipped as a binary -- unless its extension says it is a script, in which
# case it is reported as unreadable and the scan fails: a script this scan
# cannot read is an unknown, not a file with no keystroke call in it.
_SCRIPT_EXTENSIONS = frozenset({".ps1", ".psm1", ".psd1", ".sh", ".py", ".cmd", ".bat"})

_BOMS = (
    (b"\xff\xfe\x00\x00", "utf-32"), (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16"),
)


def _decoded_texts(raw):
    """The texts `raw` is scanned as; [] only when a BOM names an encoding
    the bytes then fail to decode as.

    A UTF-16/UTF-32 BOM (Windows PowerShell 5.1's `Out-File` / `>` default
    is UTF-16LE with a BOM) is decoded as it says. Otherwise UTF-8, and if
    that decodes without a NUL it is the one text. If UTF-8 fails, or yields
    NULs -- BOM-less UTF-16LE of ASCII is VALID UTF-8, one NUL per
    character -- both UTF-16 byte orders are tried, and Latin-1 is added
    last: it decodes any bytes and keeps every ASCII byte as itself."""
    for bom, codec in _BOMS:
        if raw.startswith(bom):
            try:
                return [raw.decode(codec)]
            except UnicodeDecodeError:
                return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is not None and "\x00" not in text:
        return [text]
    texts = [] if text is None else [text]
    for codec in ("utf-16-le", "utf-16-be"):
        try:
            texts.append(raw.decode(codec))
        except UnicodeDecodeError:
            pass
    texts.append(raw.decode("latin-1"))
    return texts


def _tracked_paths():
    top = subprocess.run(
        ["git", "-C", _ROOT, "rev-parse", "--show-toplevel"],
        check=True, capture_output=True, text=True).stdout.strip()
    listed = subprocess.run(
        ["git", "-C", top, "ls-files", "-z"],
        check=True, capture_output=True).stdout.decode("utf-8").split("\0")
    return top, [rel for rel in listed if rel]


def _is_exempt(rel):
    return (rel == _SELF or rel.startswith(_EXCLUDED_PREFIXES)
            or os.path.splitext(rel)[1].lower() in _DOCUMENTATION)


def _scan():
    """(matches_by_path, files_scanned, unreadable_scripts) over every
    tracked, non-exempt file. A path git lists but the working tree lacks (a
    sparse or mid-edit checkout) is skipped: it cannot hold a call."""
    top, paths = _tracked_paths()
    matches, scanned, unreadable = {}, 0, []
    for rel in paths:
        if _is_exempt(rel):
            continue
        try:
            with open(os.path.join(top, rel), "rb") as handle:
                raw = handle.read()
        except OSError:
            continue
        texts = _decoded_texts(raw)
        if not texts:
            if os.path.splitext(rel)[1].lower() in _SCRIPT_EXTENSIONS:
                unreadable.append(rel)
            continue
        scanned += 1
        found = max(([m.start() for m in _KEYSTROKE_CALL.finditer(text)]
                     for text in texts), key=len)
        if found:
            matches[rel] = found
    return matches, scanned, unreadable


def test_no_tracked_file_outside_documentation_and_recorded_output_calls_a_keystroke_api():
    matches, scanned, unreadable = _scan()

    assert scanned > 0, (
        "git ls-files yielded no readable tracked file -- the repo-wide "
        "keystroke scan read nothing, so its silence would prove nothing")
    assert not unreadable, (
        f"tracked scripts whose BOM names an encoding they fail to decode as: "
        f"{unreadable} -- an unreadable script is an unknown, not a file "
        "without a keystroke call")
    assert not matches, (
        f"keystroke API call outside documentation and recorded output "
        f"(scanned {scanned} tracked files): {matches} -- the sendkeys method "
        "was removed in crew 1.2.60 (L-0727)")


def test_the_scan_pattern_matches_every_call_form_and_no_prose():
    calls = [
        "[System.Windows.Forms." + "SendKeys]::" + "SendWait('^v')",
        "$k = [Windows.Forms." + "SendKeys" + "]" + "::" + "Send('x')",
        "$wsh.SendKeys" + "('x')",
        "$wsh . 'SendWait'" + "(\"x\")",
        "[type]::" + "'sendwait'" + "('x')",
        "SENDKEYS" + "::SENDWAIT" + "('x')",
    ]
    prose = [
        "just before SendWait in the old child",
        "test_the_inhibit_gate_sits_between_every_upstream_decision_and_sendwait()",
        "sendkeys was removed in crew 1.2.60 (L-0727)",
        "sock.send(b'x')",
        "stream.Send (value)",
    ]

    assert [bool(_KEYSTROKE_CALL.search(line)) for line in calls] == [True] * len(calls)
    assert [bool(_KEYSTROKE_CALL.search(line)) for line in prose] == [False] * len(prose)


def test_the_removed_sender_is_not_tracked():
    _top, paths = _tracked_paths()

    assert "plugin/crew/hooks/scripts/auto-clear.ps1" not in paths
