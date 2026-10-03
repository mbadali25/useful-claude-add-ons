"""Which edits to `plugin/*/BUDGETS.md` are bookkeeping (T-0046).

`plugin/crew/BUDGETS.md` states the plugin's Markdown line total under a
`<!-- claim: crew-markdown-lines -->` marker, and `scripts/check-marketplace.py`
fails the gate when that number is wrong. Every ticket that adds or resizes a
`plugin/crew/*.md` file must therefore re-measure it, and before this module
every such ticket needed BUDGETS.md in its Touch or it stopped at the scope
guard or the completion audit.

`claim_numbers_only(before, after, path)` is the one predicate both hooks will
use to let an approved ticket make that re-measure without Touch. The hooks
are wired to it by L-0610, a separate tooling PR (the owner's tooling-PR rule);
until that lands nothing imports this module. It is True only when ALL of
these hold:

- `path` is `plugin/<one segment>/BUDGETS.md`, compared case-sensitively;
- both sides are `str` (bytes, None or anything else is "could not tell");
- both sides have the same number of lines (`splitlines(keepends=True)`, so a
  changed line ending is a changed line);
- every `crew-markdown-lines` marker binds the same line on both sides;
- every line that differs is a line such a marker binds;
- each differing line differs only in its runs of digits and commas, and has
  at least one such run on each side.

Anything else is False with the first failing rule named, and so is anything
this module cannot evaluate: it never raises. A caller is to treat False as
"not exempt", so the Touch check decides as it did before this module existed.

What is NOT bookkeeping: any other line of the file, any other claim kind, any
other Markdown file, and the version files (plugin.json, marketplace.json,
PLUGINS.md, CHANGELOG.md), which every spec still lists in Touch.

The claim grammar -- `CLAIM_RE`, `CODE_SPAN_RE`, `MARKDOWN_LINES_RE` and
`BIND_WINDOW` -- is restated from `scripts/check-marketplace.py` (the claim
block beside `count_crew_markdown_lines`), because an installed plugin copy
has no `scripts/` to import from. `test_crew_bookkeeping.py`'s lockstep test
compares the two. Binding is the checker's own: fenced lines are skipped, code
spans are stripped before the marker is matched, and a marker binds the first
line in `lines[i : i + BIND_WINDOW]` that its kind's regex matches.

Standard library only, and no crew imports, so both hooks can load it first.
"""
import fnmatch
import re

CLAIM_RE = re.compile(r"<!--\s*claim:\s*([a-z0-9-]+(?::[a-z0-9._-]+)?)\s*-->")
CODE_SPAN_RE = re.compile(r"`[^`]*`")
MARKDOWN_LINES_RE = re.compile(r"([\d,]+)\s+lines\b")
BIND_WINDOW = 12

BUDGETS_GLOB = "plugin/*/BUDGETS.md"
BOOKKEEPING_CLAIMS = {"crew-markdown-lines": MARKDOWN_LINES_RE}

_NUMBER_RE = re.compile(r"[0-9][0-9,]*")
_MASK = "\0N\0"


def matches_budgets(path):
    """True when `path` is `plugin/<segment>/BUDGETS.md`: whole segments,
    `*` never crossing a `/`, case-sensitive on every OS."""
    if not isinstance(path, str):
        return False
    want = BUDGETS_GLOB.split("/")
    have = path.split("/")
    return len(have) == len(want) and all(
        fnmatch.fnmatchcase(seg, pat) and seg for seg, pat in zip(have, want))


def bound_lines(lines):
    """{marker index: bound line index} for every bookkeeping marker in
    `lines`, bound the way `scripts/check-marketplace.py` binds it."""
    bound = {}
    fenced = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        for claim in CLAIM_RE.finditer(CODE_SPAN_RE.sub("", line)):
            pattern = BOOKKEEPING_CLAIMS.get(claim.group(1))
            if pattern is None:
                continue
            window = lines[index:index + BIND_WINDOW]
            hit = next((offset for offset, text in enumerate(window) if pattern.search(text)),
                       None)
            if hit is not None:
                bound[index] = index + hit
    return bound


def _numbers_only(before, after):
    """True when two lines differ only in their digit runs, each has one."""
    runs = _NUMBER_RE.findall(before), _NUMBER_RE.findall(after)
    if not runs[0] or not runs[1]:
        return False
    return _NUMBER_RE.sub(_MASK, before) == _NUMBER_RE.sub(_MASK, after)


def _judge(before, after, path):
    if not matches_budgets(path):
        return False, f"{path} is not plugin/*/BUDGETS.md"
    if not isinstance(before, str) or not isinstance(after, str):
        return False, "could not tell"
    if before == after:
        return True, "unchanged"
    old, new = before.splitlines(keepends=True), after.splitlines(keepends=True)
    if len(old) != len(new):
        return False, "a line was added or removed"
    marks = bound_lines(old)
    if marks != bound_lines(new):
        return False, ("the crew-markdown-lines markers bind different lines before and after "
                       "(one moved, appeared or disappeared, or its number stopped matching)")
    targets = set(marks.values())
    differing = [i for i, (a, b) in enumerate(zip(old, new)) if a != b]
    unbound = [i for i in differing if i not in targets]
    if unbound:
        return False, f"line {unbound[0] + 1} changed and no crew-markdown-lines marker binds it"
    for i in differing:
        if not _numbers_only(old[i], new[i]):
            return False, f"line {i + 1} changed more than its numbers"
    return True, "only the claim's numbers changed"


def claim_numbers_only(before, after, path):
    """(ok, reason): True only for a bookkeeping re-measure (module
    docstring). Never raises; anything it cannot evaluate is False."""
    try:
        return _judge(before, after, path)
    except Exception:  # noqa: BLE001  pylint: disable=broad-except
        return False, "could not tell"
