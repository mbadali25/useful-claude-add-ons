"""What a `.crew/guard.log` row may say about the command it judged.

Until crew 1.2.34 the cloud guard (`cloud_guard.py`) wrote the command line
as typed as the last field of every row it logged, refusals included, so a
credential written inline -- `mysql -p<pw>`, `curl -u user:pw`, an
`Authorization:` header, `AWS_SECRET_ACCESS_KEY=...` -- went to disk in clear.
The row now carries `sha256:<12 hex>` of the REDACTED text, then that text cut
to `LOG_TEXT_CAP` characters. The target field goes through the same
redaction, because an `xargs`/`parallel` finding quotes part of the command
there.

The hash is of the redacted text, never the raw line: a hash of the raw line
written beside everything but its secret is an offline oracle for guessing
that secret. Its use is telling two cut rows apart.

This is a DENYLIST, so it is best effort: a secret in a shape no pattern below
names is still written. `env_guard.py` writes no command at all; the cloud
guard keeps a redacted one because `report` mode exists so an operator can
read what `block` would have refused, and a row with no command cannot answer
that. Over-masking (`mkdir -p***`, `xargs -P ***`) is accepted on purpose: a
log that hides too much costs a reader a guess, one that hides too little
costs a credential.

Kept out of `cloud_guard.py`, which sits at `.pylintrc`'s max-module-lines;
the writer, `append_row`, moved here with it so the redaction sits at the one
place a row is written rather than at each caller.
"""
import hashlib
import os
import re

import crew_state

LOG_TEXT_CAP = 200
MASK = "***"
# Only this much of a command is redacted and hashed; the rest is counted. It
# bounds the regex work on a huge pasted script, and a row shows only
# `LOG_TEXT_CAP` characters anyway.
REDACT_SCAN = 8192

_SECRET_WORD = (r"(?:pass(?:word|wd)?|pwd|secret|token|api[-_]?key|apikey|"
                r"access[-_]?key|private[-_]?key|credentials?|auth)")
# A value: a quoted string, or a run of non-blanks. The closing quote is
# optional because a finding's target can quote one WORD of the line, cut
# inside a quoted value (`'DB_PASSWORD="pw'`); an unclosed quote then masks to
# the end of the field, which over-masks rather than leaks.
_VALUE = r"(?:\"[^\"]*\"?|'[^']*'?|[^\s\"']+)"
# A flag starts a word: at the start, or after a blank or a quote.
_AT_WORD = r"(?<![^\s\"'])"

REDACTIONS = (
    # scheme://user:password@host -- keep the user, mask the password.
    (re.compile(r"(\b[a-z][a-z0-9+.-]*://[^\s/:@'\"]*:)[^\s/@'\"]+@", re.I),
     r"\1" + MASK + "@"),
    # Authorization / Proxy-Authorization headers, scheme kept.
    (re.compile(r"((?:proxy-)?authorization\s*:\s*(?:(?:bearer|basic|"
                r"digest|token|negotiate)\s+)?)[^\s'\"]+", re.I),
     r"\1" + MASK),
    # Other credential headers: Cookie, X-Api-Key, X-Auth-Token, ...
    (re.compile(r"((?:cookie|x-[\w-]*(?:key|token|secret|auth)[\w-]*)\s*:"
                r"\s*)[^'\"]+", re.I), r"\1" + MASK),
    # A bare `Bearer <token>` anywhere else.
    (re.compile(r"(\bbearer\s+)[^\s'\"]+", re.I), r"\1" + MASK),
    # NAME=value where NAME looks like a secret (AWS_SECRET_ACCESS_KEY,
    # GITHUB_TOKEN, PGPASSWORD, MYSQL_PWD, token=), and PowerShell
    # `$env:NAME = value`.
    (re.compile(r"(\b[A-Za-z0-9_]*" + _SECRET_WORD
                + r"[A-Za-z0-9_]*\s*=\s*)" + _VALUE, re.I), r"\1" + MASK),
    # --password=x / --password x / -Password x / --token x / --api-key x
    # (and `--password-stdin user`, which over-masks).
    (re.compile(_AT_WORD + r"(--?[\w-]*" + _SECRET_WORD + r"[\w-]*(?:=|\s+))"
                + _VALUE, re.I), r"\1" + MASK),
    # curl/wget style `-u user:pass`, `--user user:pass`, `--user=user:pass`.
    (re.compile(_AT_WORD + r"((?:-u|--user|--proxy-user)(?:=|\s*)['\"]?"
                r"[^\s:'\"]*:)[^\s'\"]+", re.I), r"\1" + MASK),
    # sshpass `-p <pw>`, mysql/mariadb `-p<pw>` (attached; `-p` alone
    # prompts), plink/pscp `-pw <pw>`, sqlcmd/bcp `-P <pw>`.
    (re.compile(r"(\bsshpass\s+-p\s*)" + _VALUE), r"\1" + MASK),
    (re.compile(_AT_WORD + r"(-pw\s+)" + _VALUE), r"\1" + MASK),
    (re.compile(_AT_WORD + r"(-p)(?!w\s)(?=\S)" + _VALUE), r"\1" + MASK),
    (re.compile(_AT_WORD + r"(-P\s*)" + _VALUE), r"\1" + MASK),
    # ConvertTo-SecureString "x" -AsPlainText
    (re.compile(r"(convertto-securestring\s+(?:-string\s+)?)" + _VALUE, re.I),
     r"\1" + MASK),
    # Well-known token shapes, wherever they appear.
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
                r"|(?:AKIA|ASIA)[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}"
                r"|sk-[A-Za-z0-9_-]{20,}|glpat-[A-Za-z0-9_-]{20,}"
                r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+)"),
     MASK),
)


def redact(text):
    """`text` with every value a `REDACTIONS` pattern names masked."""
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def log_text(text, digest=False):
    """What a guard.log field may hold of a command-derived `text`: redacted,
    blank runs flattened to one space, capped at `LOG_TEXT_CAP` with the
    number of characters cut, and with `digest` led by `sha256:<12 hex>` of
    the redacted text. Empty, `-` and non-strings pass through unchanged."""
    if not isinstance(text, str) or not text or text == "-":
        return text
    rest = max(0, len(text) - REDACT_SCAN)
    flat = " ".join(redact(text[:REDACT_SCAN]).split())
    more = max(0, len(flat) - LOG_TEXT_CAP) + rest
    cut = f"{flat[:LOG_TEXT_CAP]}...[+{more} chars]" if more else flat
    if not digest:
        return cut
    sha = hashlib.sha256(flat.encode("utf-8", "replace")).hexdigest()[:12]
    return f"sha256:{sha} {cut}"


def log_row(row):
    """`row` -- (time, rule, policy, decision, target, command) -- with its
    two command-derived fields, target and command, passed through
    `log_text`. The command is never written raw."""
    row = list(row)
    if len(row) > 4:
        row[4] = log_text(row[4])
    if len(row) > 5:
        row[5] = log_text(row[5], digest=True)
    return row


def append_row(root, row):
    """One row to `.crew/guard.log`, through `log_row`. The cloud guard's
    writer (`cloud_guard._log`). Never raises, never creates `.crew/` --
    `crew_config._log_guard`'s two rules, for its two reasons."""
    try:
        path = os.path.join(root, crew_state.GUARD_LOG_PATH)
        if not os.path.isdir(os.path.dirname(path)):
            return
        flat = ["-" if not f else str(f).replace("\t", " ").replace(
            "\r", " ").replace("\n", " ") for f in log_row(row)]
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\t".join(flat) + "\n")
    except OSError:
        pass
