"""The T-0500 mutations for `crew_setup_status.py`, appended to `sabotage.py`'s
MUTATIONS. Kept apart for the same reason as `sabotage_migrate.py`:
`sabotage.py` sits at `.pylintrc`'s max-module-lines. Run that file, not this
one.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP = os.path.join(CREW, "hooks", "scripts", "crew_setup_status.py")

SETUP_STATUS_MUTATIONS = (
    # Each was also run by hand against the tracked file through
    # `sabotage.apply_mutation` / `restore`, and the restore checked with
    # `git hash-object`.
    (
        # (a) The unknown collapses into the safe-looking value: a file with no
        # `crew:` line is read as marked against the installed crew.
        "setup status reads a missing crew: line as the current version",
        SETUP,
        "    if marked is None:\n"
        "        reasons.append(\"could not tell when marked (no crew: line)\")\n",
        "    if marked is None:\n"
        "        marked = current_version(PLUGIN_JSON)\n"
        "    if marked is None:\n"
        "        reasons.append(\"could not tell when marked (no crew: line)\")\n",
        "tests/test_setup_status.py::test_no_crew_line_flags_every_done_row_as_could_not_tell",
    ),
    (
        # (b) Versions compared as strings: "1.0.9" sorts after "1.0.10".
        "setup status compares versions lexically",
        SETUP,
        "    return tuple(int(part) for part in text.split(\".\"))\n",
        "    return text\n",
        "tests/test_setup_status.py::test_version_compare_is_numeric_not_lexical",
    ),
    (
        # (c) No breakage word: a note recording notify broken stays `done`.
        "setup status ignores a note that records a breakage",
        SETUP,
        "BREAKAGE_WORDS = (\"broken\", \"failing\", \"not working\", \"provider none\", \"unreachable\", "
        "\"never arrived\",\n"
        "                  \"timed out\", \"no longer\")\n",
        "BREAKAGE_WORDS = ()\n",
        "tests/test_setup_status.py::test_done_row_whose_note_records_a_breakage_is_flagged",
    ),
    (
        # (d) A heading with no marker skipped instead of could-not-tell.
        "setup status skips a phase heading with no phase-rev marker",
        SETUP,
        "            raise SetupStatusError(f'phases.md: \"{line}\" has no <!-- phase-rev: X.Y.Z --> "
        "within 3 lines')\n",
        "            continue\n",
        "tests/test_setup_status.py::test_a_phase_heading_without_a_rev_marker_is_could_not_tell_exit_3",
    ),
    (
        # (e) Exit 0 whatever was flagged: init.md's exit-1 branch never fires.
        "setup status exits 0 with rows flagged",
        SETUP,
        "    return lines, EXIT_FLAGGED if flagged else EXIT_CLEAN\n",
        "    return lines, EXIT_CLEAN\n",
        "tests/test_setup_status.py::test_the_reporters_file_is_flagged_ten_times",
    ),
    (
        # (f) The read-only checker writes one byte into the file it reads.
        "setup status appends to .crew/STATUS.md",
        SETUP,
        "    text = read_text(status_path)\n",
        "    open(status_path, \"a\", encoding=\"utf-8\").write(\"\\n\")\n"
        "    text = read_text(status_path)\n",
        "tests/test_setup_status.py::test_it_writes_nothing",
    ),
)
