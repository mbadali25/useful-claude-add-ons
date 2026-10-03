"""The T-0046 mutations: the BUDGETS.md claim allowance in `crew_bookkeeping.py`,
`scope_guard.py` and `completion_audit.py`. Same tuple shape as `sabotage.py`'s MUTATIONS --
(label, target, find, replace, test) -- and appended to it there; `sabotage.py`
sits near `.pylintrc`'s max-module-lines, so this list lives apart. Run
`sabotage.py`, not this file.

One mutation per refusing branch, each turning its named must-block case red,
plus must-allow mutations that make an allowed case refuse, so an allowance
that never allows anything cannot pass either. A mutation listed more than
once with different tests is on purpose: dropping the guard's approval
condition must fail the unapproved, the stale and the `cli` case each.

Two of the plan's mutations are not here, and why. "An unreadable base blob
is read as empty text" cannot go red on any case: an empty base against a
non-empty file changes the line count, and against an empty file it is
identical text, which the audit refuses as a mode or type change before the
predicate runs -- so that identical-text refusal is sabotaged instead
(`mode-change`), and so is reading the wrong base. `added-empty` is refused
twice, by the missing base blob and by that identical-text rule, so no single
mutation reaches it; it stays as a must-block case, not a sabotage target
(measured: dropping the identical-text rule alone left it green).
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_S = os.path.join(CREW, "hooks", "scripts")
BOOK = os.path.join(_S, "crew_bookkeeping.py")
GUARD = os.path.join(_S, "scope_guard.py")
AUDIT = os.path.join(_S, "completion_audit.py")
_B = "tests/test_crew_bookkeeping.py::"
_SG = "tests/test_scope_guard_claim_bookkeeping.py::"
_CA = "tests/test_completion_audit_claim_bookkeeping.py::"

_GUARD_APPROVED = '    approved = approval["status"] == "approved"\n'
_AUDIT_APPROVED = ('    if approval["status"] == "approved":\n'
                   "        return [p for p in paths if not _claim_bookkeeping(top, base, p)]\n")
_AUDIT_APPROVED_DROPPED = ("    if True:\n"
                           "        return [p for p in paths if not _claim_bookkeeping(top, base, p)]\n")
_SAME_FILE = "    if real_rel != named_rel:\n        return False\n"

BOOKKEEPING_MUTATIONS = (
    # crew_bookkeeping.py -- the predicate
    ("bookkeeping: any line may differ, not only a bound one", BOOK,
     "    unbound = [i for i in differing if i not in targets]\n",
     "    unbound = []\n",
     _B + "test_must_block[number-outside-window]"),
    ("bookkeeping: a bound line may change more than its numbers", BOOK,
     "        if not _numbers_only(old[i], new[i]):\n",
     "        if False:\n",
     _B + "test_must_block[prose-edit]"),
    ("bookkeeping: a marker may move or vanish", BOOK,
     "    if marks != bound_lines(new):\n",
     "    if False:\n",
     _B + "test_must_block[marker-moved]"),
    ("bookkeeping: any plugin Markdown file is a BUDGETS.md", BOOK,
     'BUDGETS_GLOB = "plugin/*/BUDGETS.md"\n',
     'BUDGETS_GLOB = "plugin/*/*.md"\n',
     _B + "test_must_block[other-path]"),
    ("bookkeeping (must-allow): only identical text passes", BOOK,
     "    old, new = before.splitlines(keepends=True), after.splitlines(keepends=True)\n",
     '    return False, "not identical"\n',
     _B + "test_must_allow[lines-and-files]"),
    # scope_guard.py -- the PreToolUse allowance
    ("guard claim allowance ignores approval (unapproved)", GUARD,
     _GUARD_APPROVED, "    approved = True\n", _SG + "test_unapproved[module]"),
    ("guard claim allowance ignores approval (stale)", GUARD,
     _GUARD_APPROVED, "    approved = True\n", _SG + "test_stale_approval[module]"),
    ("guard claim allowance ignores approval (cli receipt)", GUARD,
     _GUARD_APPROVED, "    approved = True\n",
     _SG + "test_cli_receipt_without_allow_cli_approval[module]"),
    ("guard claim allowance: a link may carry the write", GUARD,
     _SAME_FILE, "    if False:\n        return False\n",
     _SG + "test_symlink_named_budgets[module]"),
    ("guard claim allowance: a missing old_string is a no-op", GUARD,
     "    if hits == 0:\n        return None\n",
     "    if hits == 0:\n        return text\n",
     _SG + "test_edit_old_string_missing[module]"),
    ("guard claim allowance: an ambiguous old_string replaces the first", GUARD,
     "    if hits != 1:\n        return None\n",
     "    if hits != 1:\n        return text.replace(old, new, 1)\n",
     _SG + "test_edit_old_string_ambiguous[module]"),
    ("guard claim allowance (must-allow): no Edit after-text is computed", GUARD,
     '    if tool == "Edit":\n',
     '    if tool == "Edit-never":\n',
     _SG + "test_number_edit_edit[module]"),
    # completion_audit.py -- the Stop / done allowance
    ("audit claim allowance ignores approval", AUDIT,
     _AUDIT_APPROVED, _AUDIT_APPROVED_DROPPED, _CA + "test_unapproved"),
    ("audit claim allowance: identical text (a mode change) is a re-measure", AUDIT,
     "    if before == after:\n",
     "    if False:\n",
     _CA + "test_mode_change"),
    ("audit claim allowance reads the index, not the scope base", AUDIT,
     '"--filters", f"{base}:{path}"]',
     '"--filters", f":{path}"]',
     _CA + "test_prose_committed_number_uncommitted"),
)
