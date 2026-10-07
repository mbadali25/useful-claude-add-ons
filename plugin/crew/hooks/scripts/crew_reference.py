"""Lint a `/crew:reference --integrations` doc before it is written. T-0036.

    python3 crew_reference.py lint --root . --kind integrations <file>

Exit 0 clean, 1 problems, 2 usage error or a file that cannot be read (an
unreadable file is never exit 0). `/crew:reference` drafts the doc outside
the repo, runs this, and copies it into `docs/reference/` only on exit 0.

## The doc contract (`--kind integrations`, `docs/reference/integrations.md`)

- A header line `> Generated from <repo>@<sha> on <YYYY-MM-DD>` as the FIRST
  non-blank line -- the sha is what `crew_refresh_check.py` judges the doc
  against (`generated_header`, which it imports from here); one further down,
  in a fenced example say, is not the header.
- One `### ` entry per outbound call, grouped under a `## <external system>`
  heading; a `### ` inside a fenced example is not an entry. A doc with no
  entry is refused: a repo with no outbound calls
  writes no integrations.md and says so in the report.
- Every entry holds one or more backticked `path:line` / `path:start-end`
  anchors (ANCHOR_RE) and a non-empty line starting `Auth:` -- naming WHERE the
  credential comes from (an env var, a secret name, a config key), `none`,
  or `undocumented - needs a human`, which is counted, not refused.
- Every anchor anywhere in the doc names a regular file inside `--root`
  (realpath, so a symlink or `..` cannot leave it) and a line range within
  that file's line count; a backticked `/abs:N` or `../x:N` is refused. A
  backticked `host:port` reads as an anchor and is refused as a missing
  file: write hosts unquoted or as a URL.

## The secret refusal

SECRET_PATTERNS runs over every line, before any shape check. A hit is a
problem naming the pattern and `<doc>:<line>` only -- never the matched
value, which would otherwise leak into the transcript the lint exists to
keep it out of -- nor the text of an anchor on a line it hit. The patterns
are a list of KNOWN shapes: a token format not on it, or a bare high-entropy
string with no credential-named key beside it, passes (a known gap, not a
guarantee). They also refuse documented example keys (write a placeholder
such as `"${API_KEY}"` or `<token>`); `crew:security` reviews every auth
draft as a second line.

Flow docs (`--flows`, `docs/reference/flows/`) are L-0549's. Standard
library only.
"""
import argparse
import os
import re
import sys

# Matched against the FIRST non-blank line only (`generated_header`): a
# header-shaped line further down -- inside a fenced example, say -- is not
# the doc's header, and the refresh check would judge against its sha.
GENERATED_RE = re.compile(
    r"> Generated from (\S+)@([0-9a-f]{7,40}) on (\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
# A backticked `/abs/path:N` or `../path:N`: ANCHOR_RE never matches one, so
# without this it would pass as prose rather than be refused.
BAD_ANCHOR_RE = re.compile(r"`(?:/|\.\.[/\\])[^`\s]*:\d+(?:-\d+)?`")
ANCHOR_RE = re.compile(
    r"`(\.?[A-Za-z0-9_][A-Za-z0-9_.@+-]*(?:/[A-Za-z0-9_.@+-]+)*):(\d+)(?:-(\d+))?`")
UNDOCUMENTED = "undocumented - needs a human"
# An `Auth:` line that names something: `Auth:` alone says nothing.
_AUTH_RE = re.compile(r"Auth:[ \t]*\S")
KINDS = ("integrations",)
# An opening or closing code fence: three or more backticks or tildes, also
# inside a blockquote (`> ```), which is a fence all the same.
_FENCE_RE = re.compile(r"^(?: {0,3}> ?)* {0,3}(`{3,}|~{3,})")

# (name, pattern). Order is the report order when one line holds several.
SECRET_PATTERNS = (
    ("aws-access-key-id", re.compile(r"(?i)\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("aws-secret-access-key", re.compile(
        r"(?i)\baws_?secret_?(?:access_?)?key\b[\"']?\s*[:=]\s*[\"']?(?![$<{%])"
        r"[A-Za-z0-9/+=]{20,}")),
    ("private-key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("github-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("slack-webhook", re.compile(
        r"(?i)https://hooks\.slack\.com/services/T[A-Za-z0-9_]+/B[A-Za-z0-9_]+/[A-Za-z0-9_]+")),
    ("api-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("stripe-key", re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("npm-token", re.compile(r"\bnpm_[A-Za-z0-9]{36}")),
    ("sendgrid-key", re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    # A password in a URL: `scheme://user:pass@host`. `<`, `>`, `{`, `}` and
    # `$` cannot appear in either half, so `user:<password>@` is a placeholder.
    ("url-credentials", re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/:@<>{}$]+:[^\s/@<>{}$]+@")),
    ("authorization-header", re.compile(
        r"(?i)\bauthorization[\"']?\s*[:=]\s*[\"']?(?:bearer|basic|token|digest)\s+"
        r"(?![<$%{])(?![*xX.]+(?:\s|$|[\"'`,;)|#]))"
        # 8+ characters anywhere; any length when the value ends the line, a
        # quoted string, a Markdown table cell (`|`) or comes before a `#`
        # comment (`Basic YTpi` is `a:b`), so prose after the scheme word
        # (`Bearer token from env`) still passes.
        r"(?:[A-Za-z0-9._~+/=-]{8,}|[A-Za-z0-9._~+/=-]+(?=\s*(?:$|[\"'`,;)|#])))")),
    # A quoted literal assigned to a credential-named key, spaces and all (a
    # passphrase is still a password). A value starting `$`, `<`, `{` or `%`
    # is a placeholder, and backticks are not quotes, so
    # ``token from env `ORDERS_API_TOKEN` `` stays allowed. Any length counts
    # (`"abc"` is still a password); a value of only `*`, `x` or `.` is a mask.
    ("assigned-literal", re.compile(
        r"(?i)[\w.-]*(?:password|passwd|secret|token|api[_-]?key)[\w.-]*[\"']?\s*[:=]\s*"
        r"([\"'])(?![$<{%])(?![*xX.]+\1)(?:(?!\1).)+\1")),
    # The same, unquoted (YAML, .env): a value of 8+ characters holding a
    # letter AND a digit and no `/` -- prose (`Token: undocumented - needs a
    # human`) and secret-manager paths (`secret: orders/prod2/api`) pass.
    ("assigned-unquoted", re.compile(
        r"(?i)[\w.-]*(?:password|passwd|secret|token|api[_-]?key)[\w.-]*\s*[:=]\s*"
        r"(?=[^\s\"'`]*\d)(?=[^\s\"'`]*[A-Za-z])(?![^\s\"'`]*/)(?![$<{%(\[`\"'])"
        r"[^\s\"'`,;]{8,}")),
)


def _secrets(lines, shown):
    """(problems, the numbers of the lines that hit)."""
    problems, hit = [], set()
    for number, line in enumerate(lines, 1):
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                hit.add(number)
                problems.append(f"{shown}:{number}: secret-shaped string ({name}); value "
                                "not shown - write where the credential comes from instead")
    return problems, hit


def generated_header(text):
    """The GENERATED_RE match on the first non-blank line, or None. Shared
    with `crew_refresh_check._references`, so both read the same header."""
    for line in text.lstrip("\ufeff").splitlines():
        if line.strip():
            return GENERATED_RE.match(line)
    return None


def _fence_states(lines):
    """[(line, inside)] for every line: `inside` is True for a fence marker
    and every line between an opening fence and its close (CommonMark: a run
    of the opener's character at least as long, nothing after it)."""
    out, fence = [], None
    for line in lines:
        run = _FENCE_RE.match(line)
        if fence is None and run:
            fence = run.group(1)
            out.append((line, True))
            continue
        if fence is not None:
            if (run and run.group(1)[0] == fence[0] and len(run.group(1)) >= len(fence)
                    and not line[run.end():].strip()):
                fence = None
            out.append((line, True))
            continue
        out.append((line, False))
    return out


def unfenced_lines(lines):
    """`lines` without fenced examples: what the doc itself says. The refresh
    check reads citations from these, as the lint reads entries."""
    return [line for line, inside in _fence_states(lines) if not inside]


def _sections(lines):
    """[(heading line number, [lines], under a `## ` system)] for each `### `
    entry. A heading inside a ``` or ~~~ fence is an example, not an entry or
    a section end, and a fenced line is no part of an entry's body: an anchor
    or `Auth:` line in an example is not evidence for the call the entry
    documents. A fence closes only on a run of its own character at least as
    long as the one that opened it (CommonMark), so a ```` example holding
    ``` lines stays one example."""
    found, system = [], False
    for number, (line, inside) in enumerate(_fence_states(lines), 1):
        if inside:
            continue
        if line.startswith("### "):
            found.append((number, [], system))
        elif line.startswith("## ") or line.startswith("# "):
            system = line.startswith("## ")
            if found and found[-1][1] is not None:
                found.append((None, None, system))
        if found and found[-1][1] is not None:
            found[-1][1].append(line)
    return [(n, body, under) for n, body, under in found if n is not None]


def _line_count(path):
    with open(path, "rb") as handle:
        data = handle.read()
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def _anchor_problem(root, real_root, rel, start, end):
    """None when `rel:start[-end]` holds, else what is wrong with it."""
    if start < 1:
        return "line 0 does not exist"
    if end < start:
        return "its range runs backwards"
    real = os.path.realpath(os.path.join(root, rel))
    try:
        inside = os.path.commonpath([real_root, real]) == real_root
    except ValueError:
        inside = False
    if not inside:
        return "resolves outside the repository"
    if not os.path.isfile(real):
        return "no such file"
    try:
        count = _line_count(real)
    except OSError as exc:
        return f"cannot be read ({exc.strerror or type(exc).__name__})"
    if end > count:
        return f"runs past its end (the file has {count} lines)"
    return None


def _anchors(root, lines, shown, secret_lines):
    """Anchor problems. On a line the secret pass hit, the anchor's text is
    never printed: a secret-shaped token in backticks with a `:N` reads as an
    anchor, and echoing it would leak what the secret pass withheld."""
    real_root = os.path.realpath(root)
    problems = []
    for number, line in enumerate(lines, 1):
        def said(text, number=number):
            return ("(text not shown: the line holds a secret-shaped string)"
                    if number in secret_lines else text)
        for match in BAD_ANCHOR_RE.finditer(line):
            problems.append(f"{shown}:{number}: anchor {said(match.group(0))} is absolute or "
                            "leaves the repository - write it repo-relative")
        for match in ANCHOR_RE.finditer(line):
            start = int(match.group(2))
            end = int(match.group(3)) if match.group(3) else start
            why = _anchor_problem(root, real_root, match.group(1), start, end)
            if why:
                problems.append(f"{shown}:{number}: anchor {said(match.group(0))} {why}")
    return problems


def _entries(lines, shown):
    sections = _sections(lines)
    if not sections:
        return [f"{shown}:1: no `### ` entry - a repo with no outbound calls writes no "
                "integrations.md and says so in the report"]
    problems = []
    for number, body, under_system in sections:
        if not under_system:
            problems.append(f"{shown}:{number}: entry is not under a `## ` external-system "
                            "heading")
        if not any(ANCHOR_RE.search(line) for line in body):
            problems.append(f"{shown}:{number}: entry has no `path:line` anchor")
        if not any(_AUTH_RE.match(line) for line in body):
            problems.append(f"{shown}:{number}: entry has no `Auth:` line (name where the "
                            f"credential comes from, `none`, or `{UNDOCUMENTED}`)")
    return problems


def _shown(root, path):
    real_root, real = os.path.realpath(root), os.path.realpath(path)
    try:
        if os.path.commonpath([real_root, real]) == real_root:
            return os.path.relpath(real, real_root).replace(os.sep, "/")
    except ValueError:
        pass
    return path


def lint(root, path, kind):
    """`{"problems": ["<doc>:<line>: <what>", ...], "undocumented": n}`.
    Raises OSError or UnicodeDecodeError when `path` cannot be read, and
    ValueError for an unknown `kind`."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r} (expected one of {', '.join(KINDS)})")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    lines = text.splitlines()
    shown = _shown(root, path)
    problems, secret_lines = _secrets(lines, shown)
    if not generated_header(text):
        problems.append(f"{shown}:1: no `> Generated from <repo>@<sha> on <YYYY-MM-DD>` "
                        "header as the first non-blank line, so the refresh check cannot "
                        "judge it")
    problems += _entries(lines, shown)
    problems += _anchors(root, lines, shown, secret_lines)
    # Entries marked undocumented, not occurrences of the phrase: one entry
    # saying it twice, or a fenced example, is not two.
    undocumented = sum(1 for _n, body, _s in _sections(lines)
                       if any(UNDOCUMENTED in line for line in body))
    return {"problems": problems, "undocumented": undocumented}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("lint", help="check one reference doc")
    one.add_argument("--root", default=".")
    one.add_argument("--kind", required=True, choices=KINDS)
    one.add_argument("path")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    try:
        result = lint(args.root, args.path, args.kind)
    except (OSError, UnicodeDecodeError) as exc:
        reason = getattr(exc, "strerror", None) or type(exc).__name__
        sys.stderr.write(f"cannot read {args.path}: {reason}\n")
        return 2
    for problem in result["problems"]:
        sys.stdout.write(problem + "\n")
    if result["problems"]:
        sys.stdout.write(f"lint {args.path}: {len(result['problems'])} problem(s)\n")
        return 1
    sys.stdout.write(f"lint {args.path}: ok ({result['undocumented']} undocumented)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
