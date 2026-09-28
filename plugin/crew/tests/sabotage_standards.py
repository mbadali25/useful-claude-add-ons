"""The T-0085 development-standards mutations, appended to `sabotage.py`'s
MUTATIONS. Kept apart only because `sabotage.py` sits at `.pylintrc`'s
max-module-lines; the runner, its restore guarantees and its reporting are
all `sabotage.py`'s. Run that file, not this one.

Each entry weakens one refusal the required self-check depends on and names
the test that must go red: the review gate, the stamp's completeness check,
the reviewer's independence from the author's answers, the overlay's
could-not-tell reading, and both halves of the stamp's binding.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STANDARDS = os.path.join(CREW, "hooks", "scripts", "crew_standards.py")
REVIEW_RUN = os.path.join(CREW, "hooks", "scripts", "review_run.py")

STANDARDS_MUTATIONS = (
    (
        "the self-check gate finds no problem",
        STANDARDS,
        '                            f"({seal[\'standards\'][:8]} then, {found[\'digest\'][:8]} now)")\n'
        "    return problems\n",
        '                            f"({seal[\'standards\'][:8]} then, {found[\'digest\'][:8]} now)")\n'
        "    return []\n",
        ("tests/test_review_run_standards.py::"
         "test_run_refuses_before_reserve_without_selfcheck"),
    ),
    (
        "review_run skips the self-check gate",
        REVIEW_RUN,
        "        sys.stderr.write(f\"review-run: {note}\\n\")\n"
        "    if problems:\n",
        "        sys.stderr.write(f\"review-run: {note}\\n\")\n"
        "    if False:\n",
        ("tests/test_review_run_standards.py::"
         "test_run_refuses_before_reserve_without_selfcheck"),
    ),
    (
        "the stamp ignores a standard with no row",
        STANDARDS,
        "    for sid in wanted:\n"
        "        if sid not in seen:\n",
        "    for sid in wanted:\n"
        "        if False:\n",
        "tests/test_crew_standards.py::test_stamp_refuses_incomplete_record",
    ),
    (
        "the reviewer's checklist carries the author's answers",
        STANDARDS,
        "    out.append(summary_line(found))\n",
        "    out.append(summary_line(found))\n"
        "    out += [open(p, encoding=\"utf-8\").read() for p in __import__(\"glob\").glob(\n"
        "        os.path.join(root, \".work\", \"tickets\", \"*\", SELFCHECK_NAME))]\n",
        "tests/test_review_prompt.py::test_prompt_never_carries_selfcheck_answers",
    ),
    (
        "an overlay that cannot be read reads as absent",
        STANDARDS,
        "    except OSError as exc:\n"
        "        return None, f\"cannot be read: {exc.__class__.__name__}: {exc.strerror or exc}\"\n",
        "    except OSError as exc:\n"
        "        return None, \"absent\"\n",
        ("tests/test_crew_standards.py::"
         "test_overlay_that_is_a_directory_is_unknown_not_absent"),
    ),
    (
        "an overlay that is not UTF-8 reads as absent",
        STANDARDS,
        "        return None, [f\"{label}: not UTF-8 ({exc.reason} at byte {exc.start})\"], raw\n",
        "        return None, [\"absent\"], raw\n",
        "tests/test_crew_standards.py::test_bad_overlay_refuses",
    ),
    (
        "a stamp for another bundle passes",
        STANDARDS,
        "        if seal[\"bundle\"] != manifest.get(\"bundle_sha256\"):\n",
        "        if False:\n",
        "tests/test_review_run_standards.py::test_run_refuses_stale_selfcheck",
    ),
    (
        "a stamp for another standards set passes",
        STANDARDS,
        "        if seal[\"standards\"] != found[\"digest\"]:\n",
        "        if False:\n",
        ("tests/test_crew_standards.py::"
         "test_gate_refuses_a_stamp_for_another_standards_set"),
    ),
)
