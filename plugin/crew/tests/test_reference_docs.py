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


def test_lint_refuses_an_empty_auth_line(tmp_path):
    entry = ENTRY.replace("Auth: basic, key from env `SHIPSTATION_API_KEY`", "Auth:   ")

    problems = _problems(tmp_path, _doc(entry))

    assert any(":8: " in p and "no `Auth:` line" in p for p in problems), problems


def test_a_fenced_example_entry_is_not_an_entry(tmp_path):
    doc = (HEADER + "\n# Integrations\n\nThis repo makes no outbound calls. The format:\n\n"
           "```markdown\n## Shop\n\n" + ENTRY + "```\n")

    problems = _problems(tmp_path, doc)

    assert any("no `### ` entry" in p for p in problems), problems


def test_an_anchor_or_auth_line_only_in_a_fenced_example_is_no_evidence(tmp_path):
    entry = ("### POST https://ssapi.shipstation.com/orders/createorder\n"
             "Example:\n```\n`src/client.py:12`\nAuth: none\n```\n"
             "Response: 200 `{ orderId }`\n")

    problems = _problems(tmp_path, _doc(entry))

    assert (any("no `path:line` anchor" in p for p in problems),
            any("no `Auth:` line" in p for p in problems)) == (True, True), problems


def test_a_four_backtick_example_holding_a_three_backtick_line_stays_an_example(tmp_path):
    doc = (HEADER + "\n# Integrations\n\nNo outbound calls. The format:\n\n"
           "````markdown\n```\n## Shop\n\n" + ENTRY + "````\n")

    problems = _problems(tmp_path, doc)

    assert any("no `### ` entry" in p for p in problems), problems


def test_an_entry_outside_any_system_heading_is_refused(tmp_path):
    problems = _problems(tmp_path, _doc(system=""))

    assert any("not under a `## ` external-system heading" in p for p in problems), problems


def test_a_fence_inside_an_entry_does_not_end_it(tmp_path):
    entry = ENTRY.replace("Retries: 3", "```\n## not a section\n### not an entry\n```\nRetries: 3")

    assert _problems(tmp_path, _doc(entry)) == []


def test_lint_refuses_a_doc_with_no_entry(tmp_path):
    problems = _problems(tmp_path, HEADER + "\n# Integrations\n\nNothing here.\n")

    assert any("no `### ` entry" in p for p in problems), problems


# --- the secret refusal --------------------------------------------------------

_JWT_PART = "eyJ" + "hbGciOiJIUzI1NiJ9"
_AWS_SECRET = "wJalrXUtnFEMI" + "/K7MDENG/bPxRfiCY" + "EXAMPLEKEY"
_HUNTER = "hunter2" * 2
# (pattern name, the line written into the doc, the part that must never be echoed)
_SECRETS = [
    ("aws-access-key-id", "AKIA" + "Q" * 16, "Q" * 16),
    ("aws-access-key-id", "akia" + "q" * 16, "q" * 16),
    ("aws-secret-access-key", "aws_secret_access_key = " + _AWS_SECRET, _AWS_SECRET),
    ("aws-secret-access-key", "AWS_SECRET_ACCESS_KEY: " + _AWS_SECRET, _AWS_SECRET),
    ("private-key", "-----BEGIN RSA " + "PRIVATE KEY-----", "PRIVATE KEY"),
    ("github-token", "ghp_" + "a" * 36, "a" * 36),
    ("github-pat", "github_pat_" + "a" * 60, "a" * 60),
    ("slack-token", "xoxb-" + "1" * 12 + "-" + "a" * 24, "a" * 24),
    ("slack-webhook", "https://hooks.slack.com/services/T" + "0" * 8 + "/B" + "1" * 8 + "/"
     + "x" * 24, "x" * 24),
    ("api-key", "sk-" + "a" * 40, "a" * 40),
    ("stripe-key", "sk_live_" + "b" * 24, "b" * 24),
    ("stripe-key", "rk_live_" + "c" * 24, "c" * 24),
    ("google-api-key", "AIza" + "d" * 35, "d" * 35),
    ("npm-token", "npm_" + "e" * 36, "e" * 36),
    ("sendgrid-key", "SG." + "f" * 22 + "." + "g" * 43, "g" * 43),
    ("jwt", _JWT_PART + "." + "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" + "." + "b" * 43, "b" * 43),
    ("url-credentials", "https://orders:" + "s3cretPw9" + "@api.example.com/v1", "s3cretPw9"),
    ("authorization-header", "Authorization: Bearer " + "h" * 12 + "9" * 8, "h" * 12),
    ("authorization-header", "Authorization: Basic " + "b3JkZXJzOnMzY3JldA==",
     "b3JkZXJzOnMzY3JldA=="),
    ("assigned-literal", 'password = "' + _HUNTER + '"', _HUNTER),
    ("assigned-literal", 'password="' + "abc12" + '"', "abc12"),
    ("assigned-literal", 'password = "' + "correct horse" + ' battery staple"', "battery staple"),
    ("assigned-literal", "secret: '" + "two words" + "'", "two words"),
    ("assigned-unquoted", "password: " + _HUNTER, _HUNTER),
    ("assigned-unquoted", "api_key: " + "abcdef" + "123456789", "abcdef123456789"),
]


@pytest.mark.parametrize("name,line,secret", _SECRETS,
                         ids=[f"{n}-{i}" for i, (n, _, _) in enumerate(_SECRETS)])
def test_lint_refuses_secret_shaped_strings(tmp_path, name, line, secret):
    entry = ENTRY.replace("Retries: 3", f"Example: {line}\nRetries: 3")
    root, path = _repo(tmp_path, _doc(entry))

    problems = crew_reference.lint(root, path, "integrations")["problems"]
    run = _cli("lint", "--root", root, "--kind", "integrations", path)

    assert any(":14: " in p and f"secret-shaped string ({name})" in p for p in problems), problems
    assert run.returncode == 1, run
    assert secret not in run.stdout + run.stderr
    assert all(secret not in p for p in problems)


@pytest.mark.parametrize("line", [
    "password: <set in env>",
    "api_key: ${API_KEY}",
    'password = "${DB_PASSWORD}"',
    "Authorization: Bearer <token>",
    "Authorization: Bearer <orders-api-token>",
    "Authorization: Bearer ${ORDERS_API_TOKEN}",
    "Token: undocumented - needs a human",
    "Secret: environment variable `ORDERS_SECRET`",
    "secret: orders/prod2/api",
    "https://user:<password>@api.example.com",
    "https://api.example.com:443/v1/orders",
    "Auth: basic, key from env `SHIPSTATION_API_KEY`",
])
def test_lint_allows_placeholders_and_prose_beside_credential_words(tmp_path, line):
    entry = ENTRY.replace("Retries: 3", f"Example: {line}\nRetries: 3")

    assert _problems(tmp_path, _doc(entry)) == []


def test_an_anchor_on_a_secret_line_is_never_echoed(tmp_path):
    token = "ghp_" + "z" * 36
    entry = ENTRY.replace("Retries: 3", f"Example: `{token}:3`\nRetries: 3")
    root, path = _repo(tmp_path, _doc(entry))

    problems = crew_reference.lint(root, path, "integrations")["problems"]
    run = _cli("lint", "--root", root, "--kind", "integrations", path)

    assert any("secret-shaped string (github-token)" in p for p in problems), problems
    assert any(":14: " in p and "anchor" in p for p in problems), problems
    assert "z" * 36 not in run.stdout + run.stderr
    assert all("z" * 36 not in p for p in problems)


@pytest.mark.parametrize("anchor", ["`/etc/passwd:1`", "`../outside.py:1`"])
def test_lint_refuses_an_absolute_or_parent_relative_anchor(tmp_path, anchor):
    entry = ENTRY.replace("Call sites: `src/client.py:12`",
                          f"Call sites: `src/client.py:12`, {anchor}")

    problems = _problems(tmp_path, _doc(entry))

    assert any(":15: " in p and "repo-relative" in p for p in problems), problems


def test_a_header_inside_a_fenced_example_is_not_the_header(tmp_path):
    body = "# Integrations\n\n```\n" + HEADER + "```\n\n## ShipStation\n\n" + ENTRY

    problems = _problems(tmp_path, body)

    assert any(":1: " in p and "Generated from" in p for p in problems), problems


def test_the_header_must_be_the_first_non_blank_line(tmp_path):
    assert _problems(tmp_path / "a", "\n\n" + _doc()) == []
    assert any("Generated from" in p for p in _problems(
        tmp_path / "b", "# Integrations\n\n" + _doc()))


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
