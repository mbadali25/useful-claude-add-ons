"""gizmoduck.py's `tickets` confirmation gate - the control nothing covered before
this suite. `grep -rln gizmoduck scripts/_test/ plugin/crew/hooks/scripts/_test/`
found only menu-groups.sh, which tests the installer menu, not this command.

Runs `gizmoduck.py` as a real subprocess (the same boundary the `scan`/`tickets`
commands and the bundled skill actually cross - stdout, exit code, nothing more),
matching the shape used for guard.sh/guard.ps1 in plugin/crew/tests rather than
the in-process import shape in plugin/localgpu/cli/_test: gizmoduck.py is a
single script invoked by name (`python3 gizmoduck.py tickets ...`), never
imported as a module by a caller, so the contract worth pinning down is the CLI
surface, not its internal functions.

Every fixture here is a throwaway JSONL file written under pytest's `tmp_path`.
Nothing here touches real config, real ServiceDesk Plus, or installs anything.

SABOTAGE-TEST THIS FILE before trusting it (see the report for the run that did
this once already). `main()`'s `tickets` branch has two independent gates -
"no --yes yet" and "the --yes value does not match the recomputed digest" -
each ending in its own `sys.exit(3)`, so some single-line mutations degrade
gracefully instead of leaking; that is deliberate defense-in-depth, and the
three mutations below are the ones actually confirmed to defeat it:

  1. insert `safe_print(json.dumps(records, indent=2))` right after the
     preview loop in `main()` (before the `GIZMODUCK_CONFIRMATION_REQUIRED`
     marker / `sys.exit(3)`) - confirm
     `test_must_block_no_yes_exits_3_with_marker_and_no_records` goes RED on
     the record-content-leak assertion, whose message names
     GIZMODUCK_CONFIRMATION_REQUIRED, not merely "expected exit 3, got 0".
     This is the mutation that used to pass green before this rewrite: the
     marker alone satisfied a whole-stdout-JSON-parse-failure check even with
     every record's description/remediation text printed.
  2. invert `if a.yes is None:` (the first gate) to `if a.yes is not None:` -
     confirm both `test_must_block_*` and `test_must_allow_*` go RED (6 of 8
     tests here fail).
  3. mutate `for r in records:` in the preview loop to `for r in records[:1]:`
     - confirm `test_preview_lists_exactly_the_records_yes_would_emit` goes RED
     (the preview would show 1 line while --yes still emits all 3 records).

  NOT a red case, checked and noted rather than assumed: deleting only the
  first gate's `sys.exit(3)` does not leak and does not go red, because the
  second gate's `if a.yes != digest` independently fires (`a.yes` is `None`,
  which never equals a digest string) and exits 3 before
  `safe_print(json.dumps(records, ...))` is ever reached.

  Restore all mutations afterward.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "gizmoduck.py"

_MARKER = "GIZMODUCK_CONFIRMATION_REQUIRED"

# One High finding - enough to exercise the gate without depending on sort order.
_HIGH_FINDING = (
    '{"template-id":"http-title-exposed","info":{"name":"Exposed HTTP Title",'
    '"severity":"high"},"host":"h.example.com","matched-at":"https://h.example.com/"}\n'
)

# The exact non-ASCII repro from the review finding: a Nuclei template name with
# an accented character, an em dash, and an emoji - all outside cp1252... except
# the accented character and em dash, which cp1252 CAN encode; the warning sign
# emoji cannot, which is what used to crash the preview.
_UNICODE_FINDING = (
    '{"template-id":"uni-test","info":{"name":"Café — TLS ⚠",'
    '"severity":"high"},"host":"u.example.com","matched-at":"https://u.example.com/"}\n'
)

# Three distinct records, all at or above `high`, each carrying a description
# and remediation string unique enough that it can only ever have come from the
# record body - never from a preview line, which prints only severity+subject.
_MULTI_FINDINGS = (
    '{"template-id":"http-title-exposed","info":{"name":"Exposed HTTP Title",'
    '"severity":"high","description":"UNIQUE_DESC_TITLE_7f3a",'
    '"remediation":"UNIQUE_REM_TITLE_7f3a"},"host":"a.example.com",'
    '"matched-at":"https://a.example.com/"}\n'
    '{"template-id":"tls-weak-cipher","info":{"name":"Weak TLS Cipher",'
    '"severity":"critical","description":"UNIQUE_DESC_TLS_9b1c",'
    '"remediation":"UNIQUE_REM_TLS_9b1c"},"host":"b.example.com",'
    '"matched-at":"https://b.example.com/"}\n'
    '{"template-id":"exposed-panel","info":{"name":"Exposed Admin Panel",'
    '"severity":"high","description":"UNIQUE_DESC_PANEL_2d4e",'
    '"remediation":"UNIQUE_REM_PANEL_2d4e"},"host":"c.example.com",'
    '"matched-at":"https://c.example.com/"}\n'
)

_RECORD_CONTENT_MARKERS = [
    "UNIQUE_DESC_TITLE_7f3a", "UNIQUE_REM_TITLE_7f3a",
    "UNIQUE_DESC_TLS_9b1c", "UNIQUE_REM_TLS_9b1c",
    "UNIQUE_DESC_PANEL_2d4e", "UNIQUE_REM_PANEL_2d4e",
]


def _write(tmp_path, content, name="findings.jsonl"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8", newline="\n")
    return p


def _run(*args):
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True, text=True, check=False,
    )


def _extract_digest(stdout):
    """Pull the digest out of the rerun command the preview prints - the line
    containing the script's own name and a trailing `--yes <digest>`."""
    for line in stdout.splitlines():
        if _SCRIPT.name in line and "--yes" in line:
            return line.strip().rsplit("--yes", 1)[-1].strip()
    raise AssertionError(f"no rerun command with --yes found in preview stdout: {stdout!r}")


# -- must-block: no --yes ----------------------------------------------------


def test_must_block_no_yes_exits_3_with_marker_and_no_records(tmp_path):
    findings = _write(tmp_path, _MULTI_FINDINGS)
    result = _run("tickets", str(findings), "--min-severity", "high")

    # The control this gate exists for: no record content - descriptions,
    # remediation text, anything that names what would actually be filed - may
    # reach stdout without --yes. A whole-stdout JSON-parse failure is not
    # enough on its own: an implementation could print the preview and then
    # dump the records afterward, which still fails to whole-parse as JSON
    # while leaking everything.
    leaked = [m for m in _RECORD_CONTENT_MARKERS if m in result.stdout]
    assert not leaked, (
        f"record content leaked into stdout without --yes, defeating "
        f"{_MARKER}: {leaked!r} found in stdout={result.stdout!r}"
    )

    assert result.returncode == 3, (
        f"expected the gate to exit 3, got {result.returncode} "
        f"(stdout={result.stdout!r}, stderr={result.stderr!r})"
    )
    assert _MARKER in result.stdout


def test_preview_lists_exactly_the_records_yes_would_emit(tmp_path):
    findings = _write(tmp_path, _MULTI_FINDINGS)

    preview = _run("tickets", str(findings), "--min-severity", "high")
    assert preview.returncode == 3
    preview_lines = [ln for ln in preview.stdout.splitlines() if ln.startswith("  [")]
    digest = _extract_digest(preview.stdout)

    approved = _run("tickets", str(findings), "--min-severity", "high", "--yes", digest)
    assert approved.returncode == 0, (
        f"expected the matching digest to be accepted, got {approved.returncode} "
        f"(stdout={approved.stdout!r})"
    )
    records = json.loads(approved.stdout)

    assert len(preview_lines) == len(records) == 3, (
        f"preview showed {len(preview_lines)} ticket(s) ({preview_lines!r}) but "
        f"--yes would emit {len(records)} record(s) ({records!r}) - the preview "
        f"must show exactly the batch --yes creates, not a truncated view of it"
    )


# -- must-allow: --yes plus the matching digest -------------------------------


def test_must_allow_yes_with_matching_digest_exits_0_with_expected_record_count(tmp_path):
    findings = _write(tmp_path, _HIGH_FINDING)

    preview = _run("tickets", str(findings), "--min-severity", "high")
    assert preview.returncode == 3
    digest = _extract_digest(preview.stdout)

    result = _run("tickets", str(findings), "--min-severity", "high", "--yes", digest)
    assert result.returncode == 0, (
        f"expected --yes <matching digest> to succeed, got {result.returncode} "
        f"(stderr={result.stderr!r})"
    )
    records = json.loads(result.stdout)
    assert len(records) == 1
    assert records[0]["severity"] == "High"


# -- the approval-scope escape: --yes must be bound to the previewed batch ---


def test_bare_yes_with_no_digest_value_is_rejected(tmp_path):
    findings = _write(tmp_path, _MULTI_FINDINGS)
    # A bare `--yes` (no digest) must fail to parse, not fall through to
    # emitting every record at the tool's default floor - the exact widening
    # this finding closes (previously: preview at --min-severity critical
    # showed 1 ticket, then a bare `--yes` emitted every High as well).
    result = _run("tickets", str(findings), "--min-severity", "critical", "--yes")
    assert result.returncode == 2, (
        f"a bare --yes with no digest must be rejected by argparse, not "
        f"treated as approval - got {result.returncode} (stdout={result.stdout!r})"
    )
    try:
        json.loads(result.stdout)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("a bare --yes must not emit ticket records")


def test_yes_digest_from_a_narrower_batch_does_not_unlock_a_wider_one(tmp_path):
    findings = _write(tmp_path, _MULTI_FINDINGS)

    # Preview at `critical`: strictly fewer records than the tool's default
    # `high` floor would produce.
    narrow = _run("tickets", str(findings), "--min-severity", "critical")
    assert narrow.returncode == 3
    narrow_digest = _extract_digest(narrow.stdout)
    narrow_records = json.loads(
        _run("tickets", str(findings), "--min-severity", "critical",
             "--yes", narrow_digest).stdout
    )

    # Reusing that digest against the wider (default `high`) batch must be
    # refused, not honoured, even though a valid-looking digest was supplied.
    wide = _run("tickets", str(findings), "--yes", narrow_digest)
    assert wide.returncode != 0, (
        "a digest approved for a narrower batch must not unlock a wider one"
    )
    assert "GIZMODUCK_APPROVAL_MISMATCH" in wide.stdout, (
        f"expected the mismatch marker, got stdout={wide.stdout!r}"
    )
    try:
        json.loads(wide.stdout)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError(
            f"a mismatched digest must not emit ticket records - got {len(json.loads(wide.stdout))} "
            f"records for a batch approved as {len(narrow_records)}"
        )


# -- non-ASCII fixture: must not crash (BLOCK 1) ------------------------------


def test_non_ascii_finding_name_does_not_crash_the_preview(tmp_path):
    findings = _write(tmp_path, _UNICODE_FINDING)
    result = _run("tickets", str(findings), "--min-severity", "high")

    assert result.returncode == 3, (
        "a non-ASCII finding name must still hit the gate (exit 3), not crash "
        f"with a generic failure - got {result.returncode} (stderr={result.stderr!r})"
    )
    assert _MARKER in result.stdout


def test_non_ascii_finding_name_still_emits_records_with_yes(tmp_path):
    findings = _write(tmp_path, _UNICODE_FINDING)

    preview = _run("tickets", str(findings), "--min-severity", "high")
    assert preview.returncode == 3
    digest = _extract_digest(preview.stdout)

    result = _run("tickets", str(findings), "--min-severity", "high", "--yes", digest)
    assert result.returncode == 0
    records = json.loads(result.stdout)
    assert len(records) == 1


# -- abbreviation: --ye/--y must NOT satisfy the gate (FIX 3) -----------------


def test_abbreviated_yes_flag_is_rejected_not_honoured(tmp_path):
    findings = _write(tmp_path, _HIGH_FINDING)
    result = _run("tickets", str(findings), "--min-severity", "high", "--ye")

    # allow_abbrev=False means argparse must refuse this as an unrecognized
    # argument (exit 2) rather than silently treating it as --yes (exit 0).
    assert result.returncode == 2, (
        f"--ye must be rejected, not accepted as an abbreviation of --yes - "
        f"got returncode {result.returncode} (stdout={result.stdout!r})"
    )
    assert _MARKER not in result.stdout
    try:
        json.loads(result.stdout)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("an abbreviated --ye must not emit ticket records")


# -- the shipped command prose is part of the gate ----------------------------
#
# The CLI gate above can only refuse what it is asked to do; what it is asked
# is decided by the command files, because prose is what the model actually
# follows. A `scan.md` whose FIRST `gizmoduck.py tickets` line already carried
# `--yes` would satisfy every test above while filing tickets nobody previewed
# - the gate would hold and the batch would still never be shown to anyone.
#
# Only backticked spans and fenced blocks are read, never the surrounding
# sentences. Scoped by line instead, this test reported a false positive on its
# first run: `scan.md`'s own prose says "(no `--yes`)", and a line-scoped match
# read that as the flag being passed. The command, never the prose about it.

_COMMANDS = Path(__file__).resolve().parents[2] / "commands"

# Fenced block first, so its ``` fences are never mistaken for inline spans.
# An inline span may contain a newline - `scan.md`'s preview invocation wraps
# mid-command - so `[^`]` deliberately allows one.
_CODE_SPAN_RE = re.compile(r"```[a-z]*\n(.*?)```|`([^`]+)`", re.S)


def _tickets_invocations(name):
    """Every `gizmoduck.py tickets ...` command in `commands/<name>`, in order."""
    text = (_COMMANDS / name).read_text(encoding="utf-8")
    found = []
    for block, span in _CODE_SPAN_RE.findall(text):
        for chunk in (block.splitlines() if block else [span]):
            flat = " ".join(chunk.split())
            if "gizmoduck.py tickets" in flat:
                found.append(flat)
    return found


@pytest.mark.parametrize("command", ["scan.md", "tickets.md"])
def test_the_first_shipped_tickets_invocation_omits_yes(command):
    invocations = _tickets_invocations(command)

    assert invocations, f"commands/{command} invokes gizmoduck.py tickets nowhere"
    assert "--yes" not in invocations[0], (
        f"commands/{command}'s FIRST gizmoduck.py tickets invocation carries "
        f"--yes: {invocations[0]!r}. The first run is the preview the user is "
        f"shown; approving a batch nobody previewed is the gate failing open "
        f"while every CLI test here still passes."
    )


@pytest.mark.parametrize("command", ["scan.md", "tickets.md"])
def test_the_shipped_rerun_carries_yes_with_a_digest(command):
    """The other half: a command file that never reaches --yes cannot file."""
    invocations = _tickets_invocations(command)

    assert any("--yes" in inv for inv in invocations[1:]), (
        f"commands/{command} never reaches a `--yes <digest>` rerun: "
        f"{invocations!r}"
    )
