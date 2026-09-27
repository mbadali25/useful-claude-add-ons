"""The T-0046 mutations: the BUDGETS.md claim allowance in `crew_bookkeeping.py`,
`scope_guard.py` and `completion_audit.py`, and the generated-file listing in
the review bundle (`review_patch.py`, `review_run.py`, `review_ledger.py`,
`review_prompt.py`). Same tuple shape as `sabotage.py`'s MUTATIONS --
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
(measured: dropping the identical-text rule alone left it green). "The status
check accepts R" alone cannot go red either: a rename also fails the
same-path check, so the mutation drops both.
"""
import os

CREW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_S = os.path.join(CREW, "hooks", "scripts")
BOOK = os.path.join(_S, "crew_bookkeeping.py")
GUARD = os.path.join(_S, "scope_guard.py")
AUDIT = os.path.join(_S, "completion_audit.py")
PATCH = os.path.join(_S, "review_patch.py")
LEDGER = os.path.join(_S, "review_ledger.py")
RUN = os.path.join(_S, "review_run.py")
PROMPT = os.path.join(_S, "review_prompt.py")
_B = "tests/test_crew_bookkeeping.py::"
_SG = "tests/test_scope_guard_claim_bookkeeping.py::"
_CA = "tests/test_completion_audit_claim_bookkeeping.py::"
_RP = "tests/test_review_patch_generated.py::"

_GUARD_APPROVED = '    approved = approval["status"] == "approved"\n'
_AUDIT_APPROVED = ('    if approval["status"] == "approved":\n'
                   "        return [p for p in paths if not _claim_bookkeeping(top, base, p)]\n")
_AUDIT_APPROVED_DROPPED = ("    if True:\n"
                           "        return [p for p in paths if not _claim_bookkeeping(top, base, p)]\n")
_SAME_FILE = "    if real_rel != named_rel:\n        return False\n"
_KINDS = ('            if e["status"] in _GENERATED_STATUS\n'
          '            and e["path"] == e["old_path"] and e["path"] in GENERATED\n')
_MODES = ('            and e["old_mode"] in _GENERATED_MODES and e["new_mode"] in _GENERATED_MODES\n')

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
    # review_patch.py -- what the bundle omits
    ("bundle: a rename into a generated path is omitted", PATCH,
     _KINDS, '            if e["path"] in GENERATED\n',
     _RP + "test_renamed_into"),
    ("bundle: a mode change of a generated path is omitted", PATCH,
     _MODES, "",
     _RP + "test_mode_change"),
    ("bundle: every file under graphify-out/ is omitted", PATCH,
     _KINDS,
     '            if e["status"] in _GENERATED_STATUS\n'
     '            and e["path"] == e["old_path"] and e["path"].startswith("graphify-out/")\n',
     _RP + "test_not_a_generated_path[other-file]"),
    ("bundle: generated paths match case-insensitively", PATCH,
     _KINDS,
     '            if e["status"] in _GENERATED_STATUS\n'
     '            and e["path"] == e["old_path"]\n'
     '            and e["path"].lower() in [g.lower() for g in GENERATED]\n',
     _RP + "test_not_a_generated_path[case-variant]"),
    ("bundle: a linked graphify-out is omitted", PATCH,
     '    if os.path.islink(os.path.join(root, "graphify-out")):\n',
     "    if False:\n",
     _RP + "test_dir_symlink"),
    ("bundle: the listing reaches the manifest but not the patch", PATCH,
     "        generated, listing = _listing(root, omitted)\n",
     '        generated, listing = _listing(root, omitted)[0], b""\n',
     _RP + "test_graph_edited_after_clean"),
    ("bundle: the prompt does not name the generated files", PROMPT,
     "    if generated:\n        out.append(",
     "    if False:\n        out.append(",
     _RP + "test_prompt_names_generated_files"),
    # review_run.py / review_ledger.py -- the receipt
    ("receipt: an unknown bundle scheme reads as the current one", LEDGER,
     "    elif scheme == review_patch.BUNDLE_SCHEME:\n",
     "    elif True:\n",
     _RP + "test_unknown_scheme"),
    ("receipt (must-allow): a pre-scheme receipt is rebuilt with the listing", LEDGER,
     "    if scheme is None:\n        omit = False\n",
     "    if scheme is None:\n        omit = True\n",
     _RP + "test_legacy_receipt_unchanged"),
    ("receipt: review.json drops the bundle scheme", RUN,
     '        "bundle_scheme": manifest.get("bundle_scheme"),\n',
     "",
     _RP + "test_round_row_carries_scheme"),
)
