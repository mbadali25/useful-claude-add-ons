"""The crew 1.0 T6 context-hook mutations, appended to `sabotage.py`'s
MUTATIONS. Kept apart because `sabotage.py` sits at `.pylintrc`'s
max-module-lines; the runner and its restore guarantees are `sabotage.py`'s.

Each was also run through `sabotage.py`'s own apply/run/restore helpers
before it was committed, and went red on its named test.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT = os.path.join(CREW, "hooks", "scripts", "crew_context.py")
RECALL = os.path.join(CREW, "hooks", "scripts", "crew_recall.py")

CONTEXT_MUTATIONS = (
    (
        # The hard cap raised past Codex's ~2,500-token context limit.
        "the context hook's hard cap is raised to 60,000 chars",
        CONTEXT,
        "HARD_CAP = 6000\n",
        "HARD_CAP = 60000\n",
        ("tests/test_crew_context.py::"
         "test_fit_never_exceeds_the_6000_char_hard_cap_whatever_the_budget"),
    ),
    (
        # A recall line that no longer says which vault it came from.
        "recall snippets are injected without their vault label",
        RECALL,
        "    return f\"- [vault:{snippet['vault']}] {snippet['note']}: {snippet['text']}\"\n",
        "    return f\"- {snippet['note']}: {snippet['text']}\"\n",
        ("tests/test_crew_context.py::"
         "test_every_recall_snippet_names_its_vault_and_unlabelled_items_are_dropped"),
    ),
    (
        # An item the CLI returned with no vault is let through.
        "unlabelled recall items are no longer dropped",
        RECALL,
        "        if not vault or not note or not text:\n",
        "        if not note or not text:\n",
        ("tests/test_crew_context.py::"
         "test_every_recall_snippet_names_its_vault_and_unlabelled_items_are_dropped"),
    ),
    (
        # Dedup dropped: the same slice on every touch of the subsystem.
        "the context hook no longer deduplicates per subsystem and epoch",
        CONTEXT,
        "        if item.get(\"id\") and item[\"id\"] in seen:\n",
        "        if False:  # pylint: disable=using-constant-test\n",
        "tests/test_crew_context.py::test_a_subsystem_slice_is_injected_once_per_epoch",
    ),
    (
        # The compaction epoch never advances: a slice lost with the
        # compacted context is never re-injected.
        "a compaction no longer starts a new dedup epoch",
        CONTEXT,
        "            state[\"epoch\"] += 1\n",
        "            state[\"epoch\"] += 0\n",
        ("tests/test_crew_context.py::"
         "test_a_compaction_starts_a_new_epoch_and_the_slice_returns"),
    ),
    (
        # The repo's vault priority is ignored in favour of the CLI's order.
        "recall ignores the repo's vault priority order",
        RECALL,
        "    snippets.sort(key=lambda s: (priority.get(s[\"vault\"], len(priority)), s[\"rank\"]))\n",
        "    snippets.sort(key=lambda s: s[\"rank\"])\n",
        ("tests/test_crew_context.py::"
         "test_snippets_follow_the_repo_vault_priority_not_the_cli_order"),
    ),
)
