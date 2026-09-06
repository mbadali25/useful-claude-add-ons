"""The `tickets` opt-in gate: what `--create` withholds, and what it releases.

This suite exists because the gate is the only thing standing between a scan and
a write to a live ServiceDesk Plus instance. Everything else in that path
*instructs* the write rather than restraining it: `commands/tickets.md` and
`skills/gizmoduck/SKILL.md` are prose the model follows, and
`skills/infra-work-ticketing/SKILL.md:209-211` tells it explicitly to create a
ticket with no confirmation round-trip. Prose cannot restrain a call.

So the assertion that carries the weight is not "the preview is labelled" - it
is **`description` is absent**. A preview that carried a fileable body under a
warning would be a gate in name and a create-ready payload in fact, and a caller
that skips prose could file straight from it. `test_preview_carries_no_fileable_body`
is that test; if it ever goes green while `--create` is absent, the gate is gone
whatever the labels say.

Run: python -m pytest plugin/gizmoduck/scripts/_test/ -q
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

GIZMODUCK = Path(__file__).resolve().parent.parent / "gizmoduck.py"

# One Critical and one Medium, so the severity floor is exercised too: `tickets`
# floors at high, and a Medium reaching the output would mean the floor moved.
FINDINGS = [
    {
        "template-id": "CVE-2021-44228",
        "info": {
            "name": "Log4j RCE",
            "severity": "critical",
            "description": "Remote code execution.",
            "remediation": "Upgrade log4j.",
            "classification": {"cve-id": ["CVE-2021-44228"], "cvss-score": 10.0},
        },
        "type": "http",
        "host": "https://example.com",
        "matched-at": "https://example.com/app",
    },
    {
        "template-id": "tls-version",
        "info": {
            "name": "Legacy TLS offered",
            "severity": "medium",
            "description": "TLS 1.0 is enabled.",
            "remediation": "Disable TLS 1.0.",
            "classification": {},
        },
        "type": "ssl",
        "host": "https://example.com",
        "matched-at": "https://example.com:443",
    },
]


@pytest.fixture
def findings_file(tmp_path: Path) -> Path:
    p = tmp_path / "findings.jsonl"
    p.write_text("".join(json.dumps(f) + "\n" for f in FINDINGS), encoding="utf-8")
    return p


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GIZMODUCK), *args],
        capture_output=True,
        text=True,
    )


def tickets(findings_file: Path, *extra: str) -> dict:
    proc = run("tickets", str(findings_file), *extra)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# -- the gate ---------------------------------------------------------------


def test_preview_carries_no_fileable_body(findings_file: Path):
    """The assertion the whole gate rests on.

    Not "is it labelled a preview" - whether the payload a `sdp_create` call
    needs exists at all. It must not, so that a caller which ignores every
    warning still has nothing to file.
    """
    payload = tickets(findings_file)

    assert payload["tickets"], "a preview must still name what would be ticketed"
    for record in payload["tickets"]:
        assert "description" not in record, (
            "the preview generated a fileable ticket body - the gate is a label, "
            "not a gate"
        )


def test_preview_says_it_is_a_preview_and_is_not_authorized(findings_file: Path):
    payload = tickets(findings_file)

    assert payload["mode"] == "preview"
    assert payload["authorized"] is False
    assert "--create" in payload["instruction"], (
        "the preview must name the flag that releases it, or the caller cannot proceed"
    )


def test_preview_still_identifies_every_finding(findings_file: Path):
    """Withholding the body must not withhold the decision.

    A preview nobody can act on would push callers straight to --create, which
    is the opposite of the point.
    """
    record = tickets(findings_file)["tickets"][0]

    for field in ("ref", "template_id", "severity", "subject", "instances"):
        assert field in record, f"preview dropped {field}, which the user needs to decide"
    assert "CVE-2021-44228" in record["subject"]


def test_create_releases_the_body(findings_file: Path):
    payload = tickets(findings_file, "--create")

    assert payload["mode"] == "create"
    assert payload["authorized"] is True
    for record in payload["tickets"]:
        assert record["description"], "--create must produce a fileable body"
    assert "CVSS: 10.0" in payload["tickets"][0]["description"]


def test_create_and_preview_agree_on_which_findings(findings_file: Path):
    """The preview must not under-report what --create will file.

    A preview showing fewer tickets than the authorized run is worse than no
    preview: the user consents to a list, and a longer one gets written.
    """
    preview = tickets(findings_file)
    created = tickets(findings_file, "--create")

    assert preview["count"] == created["count"]
    assert [t["ref"] for t in preview["tickets"]] == [t["ref"] for t in created["tickets"]]


# -- the severity floor, which decides what reaches the gate ----------------


def test_the_floor_is_high_so_a_medium_never_reaches_a_ticket(findings_file: Path):
    """`_FLOORS["tickets"] = "high"`. A Medium is worth reading in a report
    without being worth opening a ticket for."""
    refs = [t["ref"] for t in tickets(findings_file)["tickets"]]

    assert "nuclei:CVE-2021-44228" in refs
    assert "nuclei:tls-version" not in refs, "a Medium reached the ticket list"


def test_an_explicit_min_severity_can_still_widen_the_floor(findings_file: Path):
    """Deliberate, and worth pinning: the floor is a default, not a ceiling.
    `commands/scan.md` must therefore NOT pass `$2` through to it - that would
    let a report-widening flag widen the write."""
    refs = [t["ref"] for t in tickets(findings_file, "--min-severity", "medium")["tickets"]]

    assert "nuclei:tls-version" in refs


# -- the flag itself --------------------------------------------------------


def test_create_is_rejected_on_every_other_command(findings_file: Path):
    """A flag ignored on five of six commands is one rename away from being
    honoured on all of them."""
    proc = run("report", str(findings_file), "--create")

    assert proc.returncode != 0
    assert "--create applies to `tickets` only" in proc.stderr


def test_the_default_is_the_safe_one(findings_file: Path):
    """No flag at all means preview. Stated as its own test because a default
    that flips is the whole failure this gate exists to prevent."""
    assert tickets(findings_file)["authorized"] is False

# -- what the gate does NOT do ---------------------------------------------
#
# `--create` is an ordinary CLI switch. Nothing in argv can verify that a human
# said yes, so this gate makes the write DELIBERATE, not AUTHORIZED: a caller
# that decides to pass the flag gets the payload. What it removes is the
# incidental write - the one that happens because a preview already carried a
# fileable body and prose was the only thing saying "ask first".
#
# Authorization lives one layer up, in a permission rule on the `sdp_*` MCP
# tools. That is machine configuration, not repository content, so no test here
# can assert it. These two tests cover the part that IS in this repo: the
# shipped command files must not pass `--create` in their preview step.


def _command_text(name: str) -> str:
    p = Path(__file__).resolve().parent.parent.parent / "commands" / f"{name}.md"
    return p.read_text(encoding="utf-8")


@pytest.mark.parametrize("command", ["scan", "tickets"])
def test_the_first_shipped_tickets_invocation_omits_create(command: str):
    """The prose is what the model actually follows, so it is part of the gate.

    Both commands invoke `tickets` twice: once to preview, once after a yes. The
    FIRST invocation must not carry the flag - a command whose preview step
    passes --create files tickets on a run the user only asked to see. Asserted
    against the invocation itself rather than any sentence about it, so a
    rewording cannot silently retire the check.
    """
    # Only the command itself - a backticked span or a fenced block - never the
    # prose around it. `scan.md` legitimately says "**without** `--create`" on
    # the same line as its preview invocation, and a line-scoped match reads
    # that sentence as the flag being passed.
    text = _command_text(command)
    invocations = [
        span for span in re.findall(r"`([^`\n]*gizmoduck\.py tickets[^`\n]*)`", text)
    ] + [
        line.strip()
        for block in re.findall(r"```[a-z]*\n(.*?)```", text, re.S)
        for line in block.splitlines()
        if "gizmoduck.py tickets" in line
    ]

    assert invocations, f"commands/{command}.md invokes gizmoduck.py tickets nowhere"
    assert "--create" not in invocations[0], (
        f"commands/{command}.md's FIRST tickets invocation passes --create, so its "
        "preview step files real tickets"
    )


@pytest.mark.parametrize("command", ["scan", "tickets"])
def test_the_shipped_command_asks_before_it_creates(command: str):
    """A command that reached --create without a question would be a gate with
    nobody behind it."""
    text = _command_text(command).lower()

    assert "ask" in text, f"commands/{command}.md never asks the user anything"
    assert "yes" in text, (
        f"commands/{command}.md does not condition --create on an explicit yes"
    )
