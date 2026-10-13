"""`.crew/guard.log` never holds a credential written inline on a command.

Until crew 1.2.34 the cloud guard wrote the command line as typed as the last
field of every row it logged, refusals included, so `mysql -p<pw>`, `curl -u
user:pw`, an `Authorization:` header or `AWS_SECRET_ACCESS_KEY=...` reached
disk in clear. The row now carries a sha256 of the REDACTED text and that text
capped (`guard_log_redact.log_text`), and `_log` applies it itself.

Every secret below is fake and carries a marker (`FAKEVAL`) that must not
appear anywhere in the log afterwards. Each case is run through the real hook
(the python driver: the wrappers delegate to the same module and share its
`_log`) as a REFUSED command and as an ALLOWED one that still raises a
finding (report mode), and each asserts a row was written first -- a check
over an empty log would pass for the wrong reason.
"""
import hashlib
import re

import pytest

import context  # noqa: F401  pylint: disable=unused-import

import cloud_guard  # noqa: E402  pylint: disable=wrong-import-position
import guard_log_redact  # noqa: E402  pylint: disable=wrong-import-position
import test_cloud_guard as tcg  # noqa: E402  pylint: disable=wrong-import-position

MARK = "FAKEVAL"

# (id, tool, command). Each command raises at least one finding when armed:
# the secret-bearing part is joined to a destroy or a DROP where it is not a
# finding on its own.
SECRET_CASES = [
    ("mysql-attached-p", "Bash",
     'mysql -h db.example.test -u app -pFAKEVAL01 -e "DROP TABLE t"'),
    ("password-equals", "Bash",
     'mysql --password=FAKEVAL02 -e "DROP TABLE t"'),
    ("password-space", "Bash",
     'mariadb --password FAKEVAL03 -e "DROP TABLE t"'),
    ("sqlcmd-capital-P", "Bash",
     'sqlcmd -S db.example.test -U sa -P FAKEVAL04 -Q "DROP TABLE t"'),
    ("curl-user-colon-pass", "Bash",
     "curl -u svc:FAKEVAL05 https://api.example.test/x; terraform destroy"),
    ("url-userinfo", "Bash",
     "git clone https://svc:FAKEVAL06@git.example.test/r.git; "
     "terraform destroy"),
    ("authorization-bearer", "Bash",
     'curl -H "Authorization: Bearer FAKEVAL07" https://api.example.test; '
     "terraform destroy"),
    ("authorization-basic", "Bash",
     "curl -H 'Authorization: Basic FAKEVAL08' https://api.example.test; "
     "terraform destroy"),
    ("x-api-key-header", "Bash",
     'curl -H "X-Api-Key: FAKEVAL09" https://api.example.test; '
     "terraform destroy"),
    ("aws-secret-env", "Bash",
     "AWS_SECRET_ACCESS_KEY=FAKEVAL10 aws s3 rb s3://bucket-example"),
    ("token-env", "Bash", "GITHUB_TOKEN=FAKEVAL11 terraform destroy"),
    ("password-env", "Bash",
     'PGPASSWORD=FAKEVAL12 psql -h db.example.test -c "DROP TABLE t"'),
    ("quoted-env-with-blank", "Bash",
     'DB_PASSWORD="FAKEVAL13 second-half" terraform destroy'),
    ("api-key-flag", "Bash",
     "some-cli --api-key FAKEVAL14 ping; terraform destroy"),
    ("github-token-shape", "Bash",
     "echo ghp_FAKEVAL15aaaaaaaaaaaaaaaa; terraform destroy"),
    ("powershell-env", "PowerShell",
     "$env:API_TOKEN = 'FAKEVAL16'; terraform destroy"),
    ("powershell-password-param", "PowerShell",
     "Invoke-Sqlcmd -ServerInstance db.example.test -Password FAKEVAL17 "
     "-Query 'DROP TABLE t'"),
]


def _rows(repo):
    path = repo / ".crew" / "guard.log"
    assert path.exists(), "no guard.log was written: nothing was checked"
    text = path.read_text(encoding="utf-8")
    rows = [line.split("\t") for line in text.splitlines()]
    assert rows, "guard.log is empty: nothing was checked"
    return text, rows


def _ids(cases):
    return [c[0] for c in cases]


@pytest.mark.parametrize("case", SECRET_CASES, ids=_ids(SECRET_CASES))
def test_a_refused_command_leaves_no_secret_in_the_log(tmp_path, case):
    _id, tool, command = case
    repo = tcg._fixture(tmp_path, tcg.ARMED)  # pylint: disable=protected-access
    decision, reason, code, err = tcg.run_hook("python", tmp_path, tool,
                                               command)
    assert (decision, code) == ("deny", 0), (reason, err)
    text, rows = _rows(repo)
    assert any(r[3] == "deny" for r in rows), rows
    assert MARK not in text, text
    for row in rows:
        assert len(row) == 6, row
        assert re.match(r"^sha256:[0-9a-f]{12} \S", row[5]), row


@pytest.mark.parametrize("case", SECRET_CASES, ids=_ids(SECRET_CASES))
def test_an_allowed_command_with_a_finding_leaves_no_secret_in_the_log(
        tmp_path, case):
    """Report mode: the command runs, the would-be refusal is logged."""
    _id, tool, command = case
    repo = tcg._fixture(  # pylint: disable=protected-access
        tmp_path, {"guards": {"cloudGuard": "report"}})
    decision, note, code, err = tcg.run_hook("python", tmp_path, tool,
                                             command)
    assert (decision, code) == ("allow", 0), (note, err)
    text, rows = _rows(repo)
    assert any(r[3].startswith("report:") for r in rows), rows
    assert MARK not in text, text


def test_a_policy_allow_leaves_no_secret_in_the_log(tmp_path):
    """A real `allow` (per-rule policy widened in both layers) still logs
    the finding -- and not the password."""
    repo = tcg._fixture(  # pylint: disable=protected-access
        tmp_path, {"guards": {"cloudGuard": "block",
                              "sqlDestructive": "allow"}},
        tcg.PERMISSIVE_GLOBAL)
    decision, _note, code, err = tcg.run_hook(
        "python", tmp_path, "Bash",
        'MYSQL_PWD=FAKEVAL20 mysql -pFAKEVAL21 -e "DROP TABLE t"')
    assert (decision, code) == ("allow", 0), err
    text, rows = _rows(repo)
    assert any(r[1] == "sqlDestructive" and r[3] == "allow" for r in rows), \
        rows
    assert MARK not in text, text


def test_the_unpinned_identity_note_leaves_no_secret_in_the_log(tmp_path):
    """`_note_unpinned` writes its own row with the command in it."""
    repo = tcg._fixture(tmp_path, tcg.ARMED)  # pylint: disable=protected-access
    decision, note, _code, err = tcg.run_hook(
        "python", tmp_path, "Bash",
        "AWS_SECRET_ACCESS_KEY=FAKEVAL22 aws s3 ls",
        extra_env={"CI": "true"})
    assert decision == "allow", err
    assert "nothing is pinned" in note, note
    text, rows = _rows(repo)
    assert any(r[1] == "cloudIdentity" for r in rows), rows
    assert MARK not in text, text


def test_log_redacts_target_and_command_at_the_writer(tmp_path):
    """The internal-error path and any future caller hand `_log` the raw
    command; the writer itself redacts both command-derived fields."""
    crew = tmp_path / ".crew"
    crew.mkdir()
    cloud_guard._log(  # pylint: disable=protected-access
        str(tmp_path), ("1", "cloudGuard", "block", "deny",
                        "xargs mysql -pFAKEVAL30 (via xargs)",
                        "mysql -pFAKEVAL31 -e 'select 1'"))
    text = (crew / "guard.log").read_text(encoding="utf-8")
    assert MARK not in text, text
    row = text.rstrip("\n").split("\t")
    assert row[:4] == ["1", "cloudGuard", "block", "deny"], row
    assert row[4] == "xargs mysql -p*** (via xargs)", row
    assert row[5].endswith("mysql -p*** -e 'select 1'"), row


def test_log_text_hashes_the_redacted_text_and_caps_it():
    command = "terraform destroy -var token=FAKEVAL40 " + "x" * 500
    got = guard_log_redact.log_text(command, digest=True)
    assert MARK not in got
    redacted = " ".join(guard_log_redact.redact(command).split())
    want = hashlib.sha256(redacted.encode("utf-8")).hexdigest()[:12]
    assert got.startswith(f"sha256:{want} "), got
    # Never a hash of the raw line, which would be a guessing oracle.
    raw = hashlib.sha256(command.encode("utf-8")).hexdigest()[:12]
    assert raw not in got
    body = got.split(" ", 1)[1]
    assert body.endswith(
        f"...[+{len(redacted) - guard_log_redact.LOG_TEXT_CAP} chars]"), body
    assert len(body) < guard_log_redact.LOG_TEXT_CAP + 30


@pytest.mark.parametrize("text", [
    "terraform destroy", "aws s3 ls", "git push --force origin main",
    "gh pr merge --admin 12", 'mysql -h db.example.test -u app -e "select 1"',
    "terraform -chdir=infra destroy -auto-approve",
])
def test_redaction_leaves_a_command_with_no_secret_alone(text):
    """must-allow: the log still says what was judged."""
    assert guard_log_redact.redact(text) == text
