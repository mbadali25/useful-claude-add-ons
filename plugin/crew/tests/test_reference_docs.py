"""T-0036: `crew_reference.py lint` checks a `/crew:reference --integrations`
doc before it is written, and refuses a secret-shaped string in it.

    python3 -m pytest plugin/crew/tests/test_reference_docs.py -q

Must-allow: a well-formed integrations doc, credential SOURCE names (an env
var, a secret-manager path, a config key), and an entry admitted as
`undocumented - needs a human`, which is counted. Must-block, each naming
`<doc>:<line>`: no Generated header, an entry with no anchor or no `Auth:`
line, an anchor to a missing file or past its end, a doc with no entry, and
every secret pattern -- whose matched value never reaches the output.

Every secret-shaped value here is built at runtime by concatenation, so this
file itself holds no literal secret shape. Flow docs (`--flows`) are L-0549's.
"""
import os
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import

import crew_reference

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPT = os.path.join(_ROOT, "hooks", "scripts", "crew_reference.py")
_COMMANDS = os.path.join(_ROOT, "commands")
_SKILL_REF = os.path.join(_ROOT, "skills", "crew-docs", "integrations.md")

HEADER = ("> Generated from demo@502cb13 on 2026-09-27. Every entry is anchored to a\n"
          "> file and line - re-verify the anchor before trusting the entry.\n")

ENTRY = (
    "### POST https://ssapi.shipstation.com/orders/createorder\n"
    "`src/client.py:12`\n"
    "\n"
    "Auth: basic, key from env `SHIPSTATION_API_KEY`\n"
    "Request: order JSON (`src/client.py:8-11`)\n"
    "Response: 200 `{ orderId }` | 429 rate limited\n"
    "Retries: 3, exponential, 10s timeout\n"
    "Call sites: `src/client.py:12`\n"
)


def _doc(*entries, header=HEADER, system="## ShipStation\n\n"):
    return header + "\n# Integrations\n\n" + system + "\n".join(entries or (ENTRY,))


def _repo(tmp_path, doc):
    """A repo with a 20-line `src/client.py` and `doc` as its integrations doc.
    Returns (root, doc path)."""
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "client.py").write_text(
        "".join(f"line {n}\n" for n in range(1, 21)), encoding="utf-8", newline="\n")
    path = root / "docs" / "reference" / "integrations.md"
    path.parent.mkdir(parents=True)
    path.write_text(doc, encoding="utf-8", newline="\n")
    return str(root), str(path)


def _lint(tmp_path, doc):
    root, path = _repo(tmp_path, doc)
    return crew_reference.lint(root, path, "integrations")


def _problems(tmp_path, doc):
    return _lint(tmp_path, doc)["problems"]


def _cli(*args):
    return subprocess.run([sys.executable, _SCRIPT, *args], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=60, check=False)


# --- must-allow ----------------------------------------------------------------

def test_lint_accepts_a_well_formed_integrations_doc(tmp_path):
    assert _lint(tmp_path, _doc()) == {"problems": [], "undocumented": 0}


def test_lint_allows_credential_source_names(tmp_path):
    entry = ENTRY.replace(
        "Auth: basic, key from env `SHIPSTATION_API_KEY`",
        "Auth: bearer, token from env `ORDERS_API_TOKEN` (`src/client.py:3`), else "
        "secret name orders/prod/api, else config key `orders.apiToken`")

    assert _problems(tmp_path, _doc(entry)) == []


def test_lint_counts_undocumented_entries(tmp_path):
    second = ("### GET https://ssapi.shipstation.com/carriers\n`src/client.py:15`\n\n"
              "Auth: undocumented - needs a human\n")

    assert _lint(tmp_path, _doc(ENTRY, second)) == {"problems": [], "undocumented": 1}


def test_lint_accepts_auth_none(tmp_path):
    entry = ENTRY.replace("Auth: basic, key from env `SHIPSTATION_API_KEY`", "Auth: none")

    assert _problems(tmp_path, _doc(entry)) == []


# --- must-block ----------------------------------------------------------------

def test_lint_refuses_a_doc_without_the_generated_header(tmp_path):
    problems = _problems(tmp_path, _doc(header="> Written by hand.\n"))

    assert any(p.startswith("docs/reference/integrations.md:1: ") and "Generated from" in p
               for p in problems), problems


def test_lint_refuses_an_integration_entry_without_an_anchor(tmp_path):
    entry = ENTRY.replace("`src/client.py:12`", "src/client.py").replace(
        "(`src/client.py:8-11`)", "")

    problems = _problems(tmp_path, _doc(entry))

    assert any(":8: " in p and "no `path:line` anchor" in p for p in problems), problems


def test_lint_refuses_an_integration_entry_without_an_auth_line(tmp_path):
    entry = ENTRY.replace("Auth: basic, key from env `SHIPSTATION_API_KEY`\n", "")

    problems = _problems(tmp_path, _doc(entry))

    assert any(":8: " in p and "no `Auth:` line" in p for p in problems), problems


@pytest.mark.parametrize("anchor,why", [
    ("`src/missing.py:3`", "no such file"),
    ("`src/client.py:99`", "past its end"),
    ("`src/client.py:18-25`", "past its end"),
    ("`src/client.py:0`", "line 0"),
    ("`src/link.py:1`", "outside the repository"),
])
def test_lint_refuses_an_anchor_to_a_missing_file_or_past_its_end(tmp_path, anchor, why):
    entry = ENTRY.replace("Call sites: `src/client.py:12`", f"Call sites: {anchor}")
    root, path = _repo(tmp_path, _doc(entry))
    (tmp_path / "outside.py").write_text("x\n", encoding="utf-8")
    if anchor.startswith("`src/link.py"):
        if not hasattr(os, "symlink"):
            pytest.skip("no symlinks here")
        os.symlink(str(tmp_path / "outside.py"), os.path.join(root, "src", "link.py"))

    problems = crew_reference.lint(root, path, "integrations")["problems"]

    assert any(":15: " in p and why in p and anchor in p for p in problems), problems


def test_lint_refuses_a_doc_with_no_entry(tmp_path):
    problems = _problems(tmp_path, HEADER + "\n# Integrations\n\nNothing here.\n")

    assert any("no `### ` entry" in p for p in problems), problems


# --- the secret refusal --------------------------------------------------------

_JWT_PART = "eyJ" + "hbGciOiJIUzI1NiJ9"
_SECRETS = [
    ("aws-access-key-id", "AKIA" + "Q" * 16),
    ("private-key", "-----BEGIN RSA " + "PRIVATE KEY-----"),
    ("github-token", "ghp_" + "a" * 36),
    ("github-pat", "github_pat_" + "a" * 60),
    ("slack-token", "xoxb-" + "1" * 12 + "-" + "a" * 24),
    ("api-key", "sk-" + "a" * 40),
    ("jwt", _JWT_PART + "." + "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" + "." + "b" * 43),
    ("assigned-literal", 'password = "' + "hunter2" * 2 + '"'),
]


@pytest.mark.parametrize("name,value", _SECRETS, ids=[n for n, _ in _SECRETS])
def test_lint_refuses_secret_shaped_strings(tmp_path, name, value):
    entry = ENTRY.replace("Retries: 3", f"Example: {value}\nRetries: 3")
    root, path = _repo(tmp_path, _doc(entry))

    problems = crew_reference.lint(root, path, "integrations")["problems"]
    run = _cli("lint", "--root", root, "--kind", "integrations", path)

    assert any(":14: " in p and f"secret-shaped string ({name})" in p for p in problems), problems
    assert run.returncode == 1, run
    assert value not in run.stdout + run.stderr
    assert all(value not in p for p in problems)


def test_a_documented_placeholder_is_not_a_secret(tmp_path):
    entry = ENTRY.replace("Retries: 3", 'Example: password = "${DB_PASSWORD}"\nRetries: 3')

    assert _problems(tmp_path, _doc(entry)) == []


# --- the CLI ---------------------------------------------------------------------

def test_lint_cli_exit_codes(tmp_path):
    root, path = _repo(tmp_path, _doc())
    broken = os.path.join(root, "broken.md")
    with open(broken, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(_doc(header=""))

    clean = _cli("lint", "--root", root, "--kind", "integrations", path)
    bad = _cli("lint", "--root", root, "--kind", "integrations", broken)
    no_kind = _cli("lint", "--root", root, path)
    missing = _cli("lint", "--root", root, "--kind", "integrations",
                   os.path.join(root, "nope.md"))

    assert (clean.returncode, "ok (0 undocumented)" in clean.stdout) == (0, True), clean
    assert (bad.returncode, "1 problem(s)" in bad.stdout) == (1, True), bad
    assert no_kind.returncode == 2, no_kind
    assert (missing.returncode, "cannot read" in missing.stderr,
            "nope.md" in missing.stderr) == (2, True, True), missing


def test_lint_cli_refuses_a_file_that_is_not_utf8(tmp_path):
    root, path = _repo(tmp_path, _doc())
    with open(path, "wb") as handle:
        handle.write(b"\xff\xfe\x00bad")

    run = _cli("lint", "--root", root, "--kind", "integrations", path)

    assert (run.returncode, "cannot read" in run.stderr) == (2, True), run


# --- the command and its reference file -------------------------------------------

def test_reference_md_documents_integrations_and_audit():
    with open(os.path.join(_COMMANDS, "reference.md"), encoding="utf-8") as handle:
        text = handle.read()
    with open(os.path.join(_COMMANDS, "implement.md"), encoding="utf-8") as handle:
        implement = handle.read()
    audit = text.split("## `--audit`", 1)[1].split("\n## ", 1)[0]

    assert "## `--integrations`" in text
    for needle in ("crew_reference.py lint", "crew:security", "crew-docs/integrations.md"):
        assert needle in text, needle
    assert "integrations.md" in audit
    assert len(text.splitlines()) <= 120
    assert "docs/reference/integrations.md" in implement
    assert os.path.isfile(_SKILL_REF)
