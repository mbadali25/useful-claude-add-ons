"""The recurring-findings checklist's mutations (L-0575, L-0592, L-0601),
appended to `sabotage.py`'s MUTATIONS. Kept apart because `sabotage.py` sits at
`.pylintrc`'s max-module-lines; the runner, its restore guarantees and its
reporting are all `sabotage.py`'s. Run that file, not this one.

L-0575's entries were drafted with that ticket and re-anchored to the code
after L-0592; L-0592's are the eight it ran by hand (its notes.md). Each one
removes a guard and names the test that must go red.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE = os.path.join(CREW, "hooks", "scripts", "recurring_findings.py")
DATA = os.path.join(CREW, "skills", "crew-qa-standards", "references", "recurring-findings.md")
IMPLEMENT = os.path.join(CREW, "commands", "implement.md")
PROMPT = os.path.join(CREW, "hooks", "scripts", "review_prompt.py")
_T = "tests/test_recurring_findings.py::"


def _section(sid, nxt):
    """The text of data section `sid` up to section `nxt`, read when this
    module loads, so the deletion mutation removes exactly one section. Read
    the way `sabotage.read` reads a target (newlines translated): a CRLF
    checkout on Windows must yield the same anchor text the runner sees."""
    with open(DATA, encoding="utf-8") as fh:
        text = fh.read()
    start = text.index(f"## {sid} ")
    return text[start:text.index(f"## {nxt} ", start)]


RECURRING_MUTATIONS = (
    (
        # Path scoping gone: every class is printed for every path.
        "recurring_findings selects every entry whatever the paths",
        MODULE,
        "            if any(matches(p, g, touch, root) for p in paths for g in e[\"applies_to\"])]\n",
        "            if True]\n",
        _T + "test_select_keeps_file_order_and_drops_unkeyed",
    ),
    (
        # The last valid section is lost on parse: a shipped class vanishes.
        "recurring_findings parse drops the last section",
        MODULE,
        "    if not entries:\n        problems.append(f\"PROBLEM: {label}: no valid '## RF-NN' section\")\n",
        "    entries = entries[:-1]\n    if not entries:\n"
        "        problems.append(f\"PROBLEM: {label}: no valid '## RF-NN' section\")\n",
        _T + "test_shipped_checklist_parses_and_fits",
    ),
    (
        # The cap cuts without saying so.
        "recurring_findings truncates without the announcement",
        MODULE,
        "            dropped = [e[\"id\"] for e in entries[index:]]\n",
        "            return out\n            dropped = [e[\"id\"] for e in entries[index:]]\n",
        _T + "test_cap_drops_whole_entries_and_says_which",
    ),
    (
        # An unusable manifest reads as "nothing changed".
        "recurring_findings lists nothing when the manifest is unusable",
        MODULE,
        "        return render(REVIEW_HEADER, entries,\n",
        "        return render(REVIEW_HEADER, [],\n",
        _T + "test_scope_unknown_manifest_lists_every_section",
    ),
    (
        # A Touch problem beside a valid bullet narrows the scope.
        "recurring_findings trusts a Touch list that had a problem",
        MODULE,
        "            if why:\n                unknown = f\"UNKNOWN: the spec's Touch list: {'; '.join(why)}\"\n",
        "            if why and not touch:\n"
        "                unknown = f\"UNKNOWN: the spec's Touch list: {'; '.join(why)}\"\n",
        _T + "test_scope_unknown_touch_lists_every_section",
    ),
    (
        # A broken data file reads as "no class applies".
        "recurring_findings reports a data problem as no match",
        MODULE,
        "        if data:\n",
        "        if False:\n",
        _T + "test_data_unreadable_file",
    ),
    (
        # Diagnostic notes push the block past its cap.
        "recurring_findings lets notes overflow the line cap",
        MODULE,
        "    room = MAX_LINES - len(out) - 1\n",
        "    room = len(data) + 1\n",
        _T + "test_cap_holds_when_notes_alone_would_overflow",
    ),
    (
        # L-0592 F1a: the stat refusal before the open is gone.
        "recurring_findings opens a non-regular file before checking it",
        MODULE,
        "    mode = os.stat(path).st_mode\n    if not stat.S_ISREG(mode):\n"
        "        raise OSError(f\"not a regular file ({_kind(mode)})\")\n    fd = os.open(path, _OPEN_FLAGS)\n",
        "    fd = os.open(path, _OPEN_FLAGS)\n",
        _T + "test_read_regular_never_opens_a_non_regular_file",
    ),
    (
        # L-0592 F1b: a FIFO swapped in after the stat is read as an empty file.
        "recurring_findings reads a swapped-in FIFO without the fstat check",
        MODULE,
        "        mode = os.fstat(fd).st_mode\n        if not stat.S_ISREG(mode):\n"
        "            raise OSError(f\"not a regular file ({_kind(mode)})\")\n",
        "",
        _T + "test_read_regular_refuses_a_fifo_swapped_in_after_stat",
    ),
    (
        # L-0592 F1c: the open blocks on a FIFO with no writer.
        "recurring_findings opens without O_NONBLOCK",
        MODULE,
        "_OPEN_FLAGS = os.O_RDONLY | getattr(os, \"O_NONBLOCK\", 0) | getattr(os, \"O_NOCTTY\", 0)\n",
        "_OPEN_FLAGS = os.O_RDONLY | getattr(os, \"O_NOCTTY\", 0)\n",
        _T + "test_read_regular_refuses_a_fifo_swapped_in_after_stat",
    ),
    (
        # L-0592 F2: a Touch match without a root guesses "directory".
        "recurring_findings matches a Touch entry without its root",
        MODULE,
        "    if touch and not (isinstance(root, str) and root):\n        raise ValueError(",
        "    if False:\n        raise ValueError(",
        _T + "test_select_touch_needs_a_root",
    ),
    (
        # L-0592 F3: notes kept in arrival order, so a late UNKNOWN is cut.
        "recurring_findings truncates an UNKNOWN note with the data notes",
        MODULE,
        "    out = list(header) + scope\n",
        "    out = list(header)\n    data = list(notes)\n",
        _T + "test_scope_unknown_survives_note_truncation",
    ),
    (
        # L-0592 N4: a header at the cap overflows it.
        "recurring_findings renders past the cap when the required lines cannot fit",
        MODULE,
        "    if required > MAX_LINES:\n",
        "    if False:\n",
        _T + "test_render_header_bound",
    ),
    (
        # L-0592 F5: a shipped class vanishes from the data (RF-01 here, RF-06 next).
        "the shipped data loses RF-01",
        DATA,
        _section("RF-01", "RF-02"),
        "",
        _T + "test_shipped_checklist_pins_the_seven_classes",
    ),
    (
        "the shipped data loses RF-06",
        DATA,
        _section("RF-06", "RF-07"),
        "",
        _T + "test_shipped_checklist_pins_the_seven_classes",
    ),
    (
        # L-0592 F6: the implementer is told only about UNKNOWN.
        "implement.md drops UNREADABLE from the checklist's exit 1",
        IMPLEMENT,
        "UNKNOWN,\nUNREADABLE or PROBLEM",
        "UNKNOWN,\nor PROBLEM",
        "tests/test_lifecycle_commands.py::test_implement_names_every_checklist_exit_1_prefix",
    ),
    (
        # L-0601: the review prompt loses the block.
        "review_prompt.build drops the recurring-findings block",
        PROMPT,
        "                  recurring_findings.review_block(root, manifest),\n",
        "",
        "tests/test_review_prompt.py::test_build_carries_the_recurring_findings_block",
    ),
)
