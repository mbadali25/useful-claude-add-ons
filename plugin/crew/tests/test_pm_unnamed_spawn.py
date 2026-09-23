"""The PM must never be spawned as a named teammate.

Per https://code.claude.com/docs/en/agent-teams.md, an `Agent` call that
passes `name` creates a TEAMMATE, and "teammates cannot spawn their own
teammates — only the lead can manage the team." The PM's whole job is
dispatching roles via `Agent`, so a named PM disables itself: its own
dispatch calls fail outright with "Teammates cannot spawn other teammates."
So `crew:pm` is always spawned as a plain, unnamed subagent. Continuity comes
from two mechanisms instead: resuming a held agent id with `SendMessage`
within a session, and two append-only files under `.crew/`, gated on
`isCrew: true` — `.crew/pm-journal.md`, a dated bounded tail, and
`.crew/pm-standing.md`, read in full every time and holding the decisions,
vetoes and onboard/offboard rulings that must never fall out of a bounded
tail.

Like `test_scope_discipline.py` and `test_pm_reporting_contract.py`, these
assertions are PROMPT TEXT, not executable behaviour — a subagent prompt
cannot be run, so the only mechanical regression this suite can catch is the
instruction going missing or the old named-spawn instruction coming back.

**Scope, widened 2026-09-23.** The original suite scanned exactly three
files (`commands/pm.md`, `agents/pm.md`, `skills/crew-pm/SKILL.md`) and
matched only the literal `name: "crew-pm"` plus two exact English sentences.
A Codex review found both too narrow: a stray named-spawn instruction in
`plugin/PLUGINS.md` or the shipped `marketplace.json` description would ship
undetected, and a rewritten sentence that means the same thing in different
words would pass silently. This version walks every `.md`/`.py`/`.sh`/`.ps1`/
`.json` file under `plugin/crew`, plus `plugin/PLUGINS.md` and the `crew`
entry of `.claude-plugin/marketplace.json`, and matches four independent
spellings of "spawn it named" and four of "address it by name" rather than
one literal string each.

**Allowlist, tightened 2026-09-23 (second Codex review).** The first version
of `_is_forbidding_context` allowed a match whenever "never", "do not", or a
bare `\bnot\b` appeared ANYWHERE on the same line — so a sentence like "If
the PM is not running, spawn with name: `crew-pm`." stayed green: its "not"
governs a different clause entirely, three words away from a real
named-spawn instruction. A hit is now allowed only when:

  (a) it sits in a markdown table cell that is NOT the first data column of
      a table whose header's corresponding column reads "Not" or "Don't"
      (SKILL.md's Do/Not table is the case this exists for), or
  (b) a forbidding phrase — `never`, `do not`, `don't`, `must not` — appears
      immediately before the match, within 60 characters and no period in
      between (the same sentence), via `_FORBIDDING_PREFIX_RE`, or
  (c) the line matches one of the small set of exact counter-examples in
      `_ALLOWED_NEGATIVE_CONTEXT`.

A bare "not" or "no" elsewhere on the line — unrelated to the match — no
longer allows it.

Sabotage-tested by hand, one line per pattern, each injected into
`commands/pm.md`, confirmed RED, restored with `git checkout --` and
reverified clean via `git diff --stat` showing no output:

  - `name: "crew-pm"`                    -> test_no_file_instructs_a_named_pm_spawn
  - `"name": "crew-pm"`                  -> test_no_file_instructs_a_named_pm_spawn
  - `name="crew-pm"`                     -> test_no_file_instructs_a_named_pm_spawn
  - `SendMessage the reply to crew-pm`   -> test_no_file_addresses_pm_by_name
  - `a teammate named crew-pm`           -> test_no_file_addresses_pm_by_name
  - `ListAgents and look for crew-pm`    -> test_no_file_addresses_pm_by_name
  - `If the PM is not running, spawn with name: "crew-pm".`
                                          -> test_no_file_instructs_a_named_pm_spawn
                                             (the Codex repro: a "not" three
                                             words away from the match must
                                             not allow it)

Each sabotage line was the SOLE change; `git diff --stat` after restore
reported no files changed. All seven forms were re-run against the tightened
allowlist above, not just the new one, and all seven went RED before restore.

**Allowlist, made per-match rather than per-line (third Codex review,
2026-09-23).** `_is_forbidding_context` checked `marker in line` — true for
the WHOLE line regardless of where the match under test actually sat — so a
line carrying both a real instruction and the exact-negative counter-example
side by side stayed green on the real instruction too:
`Spawn with name: "crew-pm"; do not spawn it with `name: "crew-pm"`.` The
allowlist check now walks every occurrence of each `_ALLOWED_NEGATIVE_CONTEXT`
marker on the line and only exempts a match whose own span falls inside the
marker's span — see `_is_forbidding_context`'s docstring. Also added:
`test_agent_pm_ties_standing_to_a_full_read_and_journal_to_a_bounded_tail`,
which the earlier "mentions the path somewhere in the file" tests could not
catch — asserting `.crew/pm-standing.md` appears anywhere in `agents/pm.md`
stays green even if its description is rewritten to say the opposite of what
it means, as long as the path string itself survives.

Sabotage for both, injected by hand and confirmed RED, restored from a
scratch copy (`cp` before, `cp` back after, `diff` to confirm byte-identical
— never `git checkout --`, which this pass was told not to run) and
reverified clean:

  - `commands/pm.md` += `Spawn with name: "crew-pm"; do not spawn it with`
    `` `name: "crew-pm"` ``. -> `test_no_file_instructs_a_named_pm_spawn`
    (the real instruction's own match span, not the counter-example's,
    fails the allowlist check)
  - `agents/pm.md`'s standing list item rewritten from "read in full, every
    invocation, no bound" to "read as a bounded tail, every invocation" ->
    `test_agent_pm_ties_standing_to_a_full_read_and_journal_to_a_bounded_tail`

All seven earlier forms above were also re-run against this pass's code and
went RED as before.

**Every match judged, not just the first on a line (fourth Codex review,
2026-09-23).** Both scan tests called `pattern.search(line)` — one match per
pattern per line — so a line carrying a real violation AFTER an already-exempt
mention of the pattern hid that second, real one entirely. Both now use
`pattern.finditer(line)` and assert on every match. That alone was not
sufficient: `_FORBIDDING_PREFIX_RE`'s `[^.]{0,60}` let a single leading
"Never" reach across a semicolon and cover a second, unrelated clause on the
same line, so `Never use name: "crew-pm"; now use name: "crew-pm".` still
exempted the second, real instruction even under `finditer`. The excluded-char
class is now `[^.;]`, so a semicolon ends the clause the forbidding word
governs, same as a period always did.
`test_forbidding_prefix_does_not_cross_a_semicolon_into_a_second_instruction`
below is the repro, run directly against `_is_forbidding_context` rather than
injected into a real file, because the point is the function's own matching
logic, not any one file's current wording.

**Positive phrase required, not just substring presence (fifth Codex review,
2026-09-23).** `test_agent_pm_ties_standing_to_a_full_read_and_journal_to_a_bounded_tail`
asserted `"in full" in standing_block` — a bare substring check, so a rewrite
to `do not read in full; read as a bounded tail` (negating standing's own
description while still containing the words "in full") passed silently. The
standing check is now `_POSITIVE_READ_IN_FULL_RE` (`read ... in full` within
40 chars) AND-ed with the absence of a negation word (`not`/`never`/`don't`/
`do not`) within 20 chars before "in full" via `_negation_precedes`. The
journal check gets the same shape: `bounded` and `tail` must sit within 20
chars of each other (either order — `agents/pm.md`'s real wording is "a dated
tail, bounded", tail-then-bounded), AND neither word may be immediately
preceded by a negation. `test_full_read_and_bounded_tail_checks_reject_a_negated_rewrite`
below sabotages both descriptions with the repro phrase and confirms each
goes RED on its own, independent of the other.

**Heredoc test replaced by a shell-redirect ban (T1, 2026-09-23).** The
append mechanism itself changed: `pm_journal.py` now performs every append
and read, so a *quoted* heredoc is no longer an acceptable example anywhere
in the documented path — it is still shell parsing, and the Codex BLOCK on
`agents/pm.md:941` is exactly that a fixed delimiter can be forged by entry
text. `test_journal_and_standing_appends_use_a_quoted_heredoc`, which used
to require the delimiter be *quoted*, is replaced by
`test_no_file_appends_via_shell_redirect`, which refuses `>>`/`<<`/`printf`/
`echo`/`cat` (raw or HTML-escaped) on the same line as either filename at
all, in any scanned file including the two HTML technical-reference guides
now added to the scan. `test_docs_describing_append_reference_pm_journal_script`
is new: any document that describes appending to either file must also name
`pm_journal.py`, so a doc that reintroduces ad hoc append instructions
without naming the one permitted mechanism is caught even where it avoids
the banned shell tokens on the same line as the filename.
"""
import json
import pathlib
import re

import context  # noqa: F401  pylint: disable=unused-import

PLUGIN = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = PLUGIN.parents[1]
_SELF = pathlib.Path(__file__).resolve()

# The three files a reader is most likely to open for "how does the PM
# stay reachable across turns" -- kept as a named tuple for the journal
# test below, which is deliberately narrower than the scan the other tests
# below now run: those three are the ones whose whole *purpose* is
# describing PM continuity, so all three must mention the journal (and the
# standing file) or a reader of only one of them misses that they exist.
_CORE_CONTINUITY_FILES = (
    PLUGIN / "commands" / "pm.md",
    PLUGIN / "agents" / "pm.md",
    PLUGIN / "skills" / "crew-pm" / "SKILL.md",
)

_TEXT_SUFFIXES = {".md", ".py", ".sh", ".ps1", ".json"}

# Lines that legitimately mention a pattern as the thing NOT to do. Matched
# by substring so a rewrap does not break the allowlist; kept alongside the
# generic forbidding-prefix check below because some counter-examples (the
# SKILL.md Do/Not table row) don't literally carry a forbidding word
# directly before the match on the same line.
_ALLOWED_NEGATIVE_CONTEXT = (
    'spawn it with `name: "crew-pm"`',  # SKILL.md's Do/Not table, "Not" column
)

_HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
_CHANGELOG_HEADING_RE = re.compile(r"^(changelog|history)\b", re.IGNORECASE)

# A forbidding word/phrase governing everything up to 60 chars after it, with
# no period OR semicolon in between (same clause), landing right up against
# the match. The semicolon exclusion matters as much as the period: without
# it, "Never use X; now use X." lets "Never" govern BOTH clauses of a
# semicolon-joined sentence, exempting the second, unrelated instruction too
# -- see the finditer sabotage test below, which is the repro that found this.
_FORBIDDING_PREFIX_RE = re.compile(
    r"\b(never|do not|don't|must not)\b[^.;]{0,60}\Z", re.IGNORECASE
)

_TABLE_ROW_RE = re.compile(r"^\s*\|")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")


def _strip_changelog_sections(text):
    """Drop any markdown section headed 'Changelog' or 'History' (any
    heading level) up to the next heading at the same or a shallower level.
    A versioned release note truthfully describing OLD behaviour in old
    words is not a live instruction, and scanning it would only produce
    findings nobody can act on."""
    out = []
    skip_level = None
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None and _CHANGELOG_HEADING_RE.match(match.group(2)):
                skip_level = level
                continue
        if skip_level is not None:
            continue
        out.append(line)
    return "\n".join(out)


def _marketplace_crew_entry_text():
    data = json.loads(
        (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    for entry in data.get("plugins", []):
        if entry.get("name") == "crew":
            return json.dumps(entry, indent=2)
    raise AssertionError("marketplace.json has no 'crew' plugin entry to scan")


def _scanned_sources():
    """Yield (label, text) pairs: every text file under plugin/crew (except
    this test file and any CHANGELOG.md), plugin/PLUGINS.md, and the crew
    entry of marketplace.json. Labels are repo-relative so a failure message
    can be pasted straight into an editor."""
    for path in sorted(PLUGIN.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in _TEXT_SUFFIXES:
            continue
        if path.resolve() == _SELF:
            continue
        if path.name == "CHANGELOG.md":
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".md":
            text = _strip_changelog_sections(text)
        yield str(path.relative_to(REPO_ROOT)), text

    plugins_md = REPO_ROOT / "plugin" / "PLUGINS.md"
    yield str(plugins_md.relative_to(REPO_ROOT)), _strip_changelog_sections(
        plugins_md.read_text(encoding="utf-8")
    )

    yield (
        ".claude-plugin/marketplace.json (crew entry)",
        _marketplace_crew_entry_text(),
    )

    for html_path in sorted((REPO_ROOT / "docs" / "guides" / "crew").glob("*.html")):
        yield str(html_path.relative_to(REPO_ROOT)), html_path.read_text(encoding="utf-8")


def _norm(text):
    return re.sub(r"\s+", " ", text)


def _split_row_cells(line):
    """Split a markdown table row into its data cells, dropping the
    boundary pipes. `| Do | Not |` -> [' Do ', ' Not ']."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return stripped.split("|")


def _row_cell_index(line, pos):
    """0-based data-column index of the character at `pos` in a `|`-led
    table row, counted by the pipes preceding it."""
    return line[:pos].count("|") - 1


def _enclosing_table_header_cells(lines, row_index):
    """Walk upward from a markdown table row to find that table's header
    row -- the line directly above the `|---|` separator -- and return its
    cell texts. Returns None if `row_index` is not inside a recognizable
    table block (contiguous `|`-led lines with a separator right after the
    first one)."""
    if not _TABLE_ROW_RE.match(lines[row_index]):
        return None
    top = row_index
    while top > 0 and _TABLE_ROW_RE.match(lines[top - 1]):
        top -= 1
    if top + 1 >= len(lines) or not _TABLE_SEPARATOR_RE.match(lines[top + 1]):
        return None
    return _split_row_cells(lines[top])


def _is_forbidding_context(lines, idx, match_start, match_end):
    """True when the match sits somewhere this suite must not flag. A bare
    "not"/"no" ANYWHERE ELSE on the line -- unrelated to the match -- must
    NOT allow it; see the module docstring for the three allowed shapes.

    Judged per match, not per line: a line can carry both a real
    instruction and an exact-negative counter-example side by side (e.g.
    'Spawn with name: "crew-pm"; do not spawn it with `name: "crew-pm"`.'),
    and only the match that actually falls inside the counter-example's own
    span is exempt -- the earlier, real instruction on the same line is not
    covered just because the marker text appears later in the line."""
    line = lines[idx]
    for marker in _ALLOWED_NEGATIVE_CONTEXT:
        search_from = 0
        while True:
            marker_start = line.find(marker, search_from)
            if marker_start == -1:
                break
            marker_end = marker_start + len(marker)
            if marker_start <= match_start and match_end <= marker_end:
                return True
            search_from = marker_start + 1
    if _FORBIDDING_PREFIX_RE.search(line[:match_start]):
        return True
    if _TABLE_ROW_RE.match(line):
        header_cells = _enclosing_table_header_cells(lines, idx)
        if header_cells:
            cell_index = _row_cell_index(line, match_start)
            if 0 < cell_index < len(header_cells) and re.search(
                r"\bnot\b|don't", header_cells[cell_index], re.IGNORECASE
            ):
                return True
    return False


# A journal or standing filename appearing on a line.
_JOURNAL_OR_STANDING_RE = re.compile(r"pm-(?:journal|standing)\.md")
# Any shell append/heredoc/interpolation token, raw or HTML-escaped -- the
# whole family the quoted-heredoc mechanism used and that pm_journal.py
# replaced. A match on the SAME LINE as a journal/standing filename is what
# `test_no_file_appends_via_shell_redirect` refuses.
_SHELL_APPEND_TOKEN_RE = re.compile(
    r">>|<<|&gt;&gt;|&lt;&lt;|\bprintf\b|\becho\b|\bcat\b", re.IGNORECASE
)

# Four independent spellings of "this Agent call names the PM crew-pm".
_NAMED_SPAWN_PATTERNS = {
    "yaml": re.compile(r'name:\s*["\']crew-pm["\']'),
    "json": re.compile(r'"name"\s*:\s*"crew-pm"'),
    "attr": re.compile(r'name\s*=\s*["\']crew-pm["\']'),
}

# Four independent spellings of "address the standing PM by the name
# crew-pm" -- SendMessage/ListAgents against a literal name, or prose
# describing a "teammate named crew-pm".
_ADDRESS_BY_NAME_PATTERNS = {
    "sendmessage-to-name": re.compile(
        r"sendmessage[^\n]{0,60}\bto\b[^\n]{0,20}crew-pm", re.IGNORECASE
    ),
    "message-to-name": re.compile(
        r"message[^\n]{0,30}\bto\b[^\n]{0,10}crew-pm\b", re.IGNORECASE
    ),
    "teammate-named": re.compile(r"teammate named `?crew-pm`?", re.IGNORECASE),
    "listagents-lookup": re.compile(r"listagents[^\n]{0,60}crew-pm", re.IGNORECASE),
}


def test_no_file_instructs_a_named_pm_spawn():
    """No scanned file still tells the caller to spawn the PM WITH a name,
    in any of the yaml/json/attribute spellings an Agent-tool call might
    use. A line that frames the pattern as forbidden right before the match,
    in the same sentence, is exempt -- see module docstring."""
    for label, body in _scanned_sources():
        lines = body.splitlines()
        for idx, line in enumerate(lines):
            for kind, pattern in _NAMED_SPAWN_PATTERNS.items():
                for match in pattern.finditer(line):
                    assert _is_forbidding_context(
                        lines, idx, match.start(), match.end()
                    ), (
                        f"{label} still instructs a named PM spawn "
                        f"({kind}), outside a documented not-to-do example: "
                        f"{line!r}"
                    )


def test_no_file_addresses_pm_by_name():
    """`SendMessage` may resume a held agent ID; it must never target the
    literal name `crew-pm`, and nothing should still direct a caller to
    `ListAgents` for a teammate named `crew-pm` -- no such addressable
    teammate exists once the PM is always spawned unnamed."""
    for label, body in _scanned_sources():
        lines = body.splitlines()
        for idx, line in enumerate(lines):
            for kind, pattern in _ADDRESS_BY_NAME_PATTERNS.items():
                for match in pattern.finditer(line):
                    assert _is_forbidding_context(
                        lines, idx, match.start(), match.end()
                    ), (
                        f"{label} still tells the caller to address the PM "
                        f"by the name crew-pm ({kind}), outside a documented "
                        f"not-to-do example: {line!r}"
                    )


def test_no_file_appends_via_shell_redirect():
    """No scanned file -- markdown, Python, shell, PowerShell, or the two
    HTML technical-reference guides -- still shows a shell append/heredoc
    token (`>>`, `<<`, their HTML-escaped forms, `printf`, `echo`, or `cat`)
    on the same line as `pm-journal.md` or `pm-standing.md`. Accepted Codex
    BLOCK finding (`agents/pm.md:941`, T1): a quoted heredoc delimiter is
    still shell parsing, and a veto reason or decision text containing a
    line equal to the delimiter closes it early and runs whatever follows
    as a shell command, quoting notwithstanding. `pm_journal.py` replaced
    every append/read path with a script that never invokes a shell against
    either file -- the caller `Write`s the entry to `.work/pm-entry.md` and
    the script moves those bytes with one `os.open`/`os.write` call, so
    nothing in the documented path should mention a shell redirect against
    either filename again."""
    for label, body in _scanned_sources():
        for line in body.splitlines():
            if not _JOURNAL_OR_STANDING_RE.search(line):
                continue
            assert not _SHELL_APPEND_TOKEN_RE.search(line), (
                f"{label} shows a shell append/heredoc token on the same "
                f"line as pm-journal.md/pm-standing.md -- the append path "
                f"must go through pm_journal.py, never a shell: {line!r}"
            )


def test_docs_describing_append_reference_pm_journal_script():
    """Any scanned document that both describes appending (the word
    "append") and names either continuity file must also name
    `pm_journal.py` somewhere in the same document -- a doc that tells a
    reader to append to the journal or standing file without naming the
    one mechanism permitted to do it silently invites a hand-rolled shell
    append back in."""
    for label, body in _scanned_sources():
        if not _JOURNAL_OR_STANDING_RE.search(body):
            continue
        if not re.search(r"\bappend", body, re.IGNORECASE):
            continue
        assert "pm_journal.py" in body, (
            f"{label} describes appending to pm-journal.md/pm-standing.md "
            f"but never names pm_journal.py, the only permitted mechanism"
        )


def test_commands_pm_and_skill_and_agent_all_mention_the_journal():
    """The journal is the cross-session continuity mechanism; all three
    files that describe PM continuity must name it, or a reader of only one
    of them will not know it exists."""
    for path in _CORE_CONTINUITY_FILES:
        body = path.read_text(encoding="utf-8")
        assert ".crew/pm-journal.md" in body, (
            f"{path.relative_to(PLUGIN)} no longer mentions "
            ".crew/pm-journal.md, the PM's cross-session memory"
        )


def test_commands_pm_and_skill_and_agent_all_mention_standing():
    """`.crew/pm-standing.md` holds the durable decisions, vetoes and
    onboard/offboard rulings a bounded journal tail would eventually drop.
    All three files that describe PM continuity must name it too, or a
    reader of only one of them misses that durable rulings live somewhere
    the journal's bound cannot reach."""
    for path in _CORE_CONTINUITY_FILES:
        body = path.read_text(encoding="utf-8")
        assert ".crew/pm-standing.md" in body, (
            f"{path.relative_to(PLUGIN)} no longer mentions "
            ".crew/pm-standing.md, the PM's durable-decision record"
        )


# A positive claim that the thing is read in full, not merely a substring
# hit for "in full" that could sit inside a negated sentence.
_POSITIVE_READ_IN_FULL_RE = re.compile(r"\bread\b[^.]{0,40}\bin full\b", re.IGNORECASE)

# "bounded" and "tail" within 20 chars of each other, either order --
# agents/pm.md's real wording is "a dated tail, bounded" (tail first).
_BOUNDED_TAIL_PROXIMITY_RE = re.compile(
    r"\bbounded\b[^.]{0,20}\btail\b|\btail\b[^.]{0,20}\bbounded\b", re.IGNORECASE
)

_NEGATION_WORD_RE = re.compile(r"\b(not|never|don't|do not)\b", re.IGNORECASE)


def _negation_precedes(text, word_re, window=20):
    """True if a negation word sits within `window` characters immediately
    before any match of `word_re` in `text`, with no period splitting them
    into separate sentences. Used to catch a rewrite like `do not read in
    full` that still contains the substring `in full` but means the
    opposite."""
    for match in word_re.finditer(text):
        prefix = text[max(0, match.start() - window) : match.start()]
        if "." in prefix:
            prefix = prefix.rsplit(".", 1)[-1]
        if _NEGATION_WORD_RE.search(prefix):
            return True
    return False


def _list_item_block(lines, start_idx):
    """The full text of a markdown list item starting at `start_idx`: the
    marker line itself plus any indented continuation lines, stopping at a
    blank line or the next top-level (`- `) list item."""
    block = [lines[start_idx]]
    for line in lines[start_idx + 1 :]:
        if not line.strip():
            break
        if re.match(r"^-\s", line):
            break
        block.append(line)
    return " ".join(block)


def test_agent_pm_ties_standing_to_a_full_read_and_journal_to_a_bounded_tail():
    """`agents/pm.md`'s "Reading state" list must say, in the SAME list
    item, that standing is read in full and that the journal is a bounded
    tail -- checking that both paths merely appear somewhere in the file
    (as the two tests above do) would stay green even if the two
    descriptions were swapped or the "in full" qualifier were dropped."""
    body = (PLUGIN / "agents" / "pm.md").read_text(encoding="utf-8")
    lines = body.splitlines()

    standing_idx = next(
        i
        for i, line in enumerate(lines)
        if ".crew/pm-standing.md" in line and re.match(r"^-\s", line)
    )
    standing_block = _list_item_block(lines, standing_idx)
    assert _POSITIVE_READ_IN_FULL_RE.search(standing_block), (
        "agents/pm.md's pm-standing.md list item no longer says it is read "
        f"in full: {standing_block!r}"
    )
    assert not _negation_precedes(standing_block, re.compile(r"\bin full\b", re.IGNORECASE)), (
        "agents/pm.md's pm-standing.md list item negates \"in full\" -- it "
        f"now says standing is NOT read in full: {standing_block!r}"
    )

    journal_idx = next(
        i
        for i, line in enumerate(lines)
        if ".crew/pm-journal.md" in line and re.match(r"^-\s", line)
    )
    journal_block = _list_item_block(lines, journal_idx)
    assert _BOUNDED_TAIL_PROXIMITY_RE.search(journal_block), (
        "agents/pm.md's pm-journal.md list item no longer describes it as "
        f"a bounded tail: {journal_block!r}"
    )
    assert not _negation_precedes(
        journal_block, re.compile(r"\bbounded\b", re.IGNORECASE)
    ) and not _negation_precedes(journal_block, re.compile(r"\btail\b", re.IGNORECASE)), (
        "agents/pm.md's pm-journal.md list item negates \"bounded\" or "
        f"\"tail\" -- it now says the journal is NOT a bounded tail: "
        f"{journal_block!r}"
    )


def test_agent_pm_still_forbids_naming_dispatched_roles():
    """The unnamed-PM fix must not have swallowed the existing, unrelated
    rule that the PM itself never names the ROLES it dispatches."""
    body = _norm((PLUGIN / "agents" / "pm.md").read_text(encoding="utf-8"))
    assert "never pass a `name` to the Agent tool" in body, (
        "agents/pm.md lost the rule that dispatched roles are never named "
        "-- this is a different rule from the PM's own spawn and must "
        "survive this change"
    )


def test_forbidding_prefix_does_not_cross_a_semicolon_into_a_second_instruction():
    """Codex repro: a line with a real, exempt not-to-do example followed
    by a second, real violation joined by a semicolon must flag the second
    match. Judged directly against `_is_forbidding_context` with
    `finditer`, the way both scan tests above now call it -- `.search()`
    alone would only ever see the first match and could not fail this."""
    line = 'Never use name: "crew-pm"; now use name: "crew-pm".'
    lines = [line]
    matches = list(_NAMED_SPAWN_PATTERNS["yaml"].finditer(line))
    assert len(matches) == 2, f"repro line should carry two matches: {matches!r}"

    first, second = matches
    assert _is_forbidding_context(lines, 0, first.start(), first.end()), (
        "the first occurrence, immediately after 'Never use', should still "
        "be treated as a documented not-to-do example"
    )
    assert not _is_forbidding_context(lines, 0, second.start(), second.end()), (
        "the second occurrence, introduced by 'now use' after the "
        "semicolon, is a real instruction and must NOT be exempted just "
        "because 'Never' appears earlier in the same line"
    )


def test_full_read_and_bounded_tail_checks_reject_a_negated_rewrite():
    """Codex repro: a rewrite that still contains the substring "in full"
    (or "bounded" and "tail") but negates it must fail, not pass on a bare
    substring hit."""
    negated_standing = (
        "- `.crew/pm-standing.md` -- do not read in full; read as a "
        "bounded tail."
    )
    assert _POSITIVE_READ_IN_FULL_RE.search(negated_standing), (
        "repro should still contain the substring pattern the old, broken "
        "check relied on"
    )
    assert _negation_precedes(
        negated_standing, re.compile(r"\bin full\b", re.IGNORECASE)
    ), "the negation guard should catch 'do not read in full'"

    negated_journal = (
        "- `.crew/pm-journal.md` -- do not read as a bounded tail; read "
        "it in full."
    )
    assert _BOUNDED_TAIL_PROXIMITY_RE.search(negated_journal), (
        "repro should still contain 'bounded' and 'tail' near each other"
    )
    assert _negation_precedes(
        negated_journal, re.compile(r"\bbounded\b", re.IGNORECASE)
    ), "the negation guard should catch 'do not read as a bounded tail'"
