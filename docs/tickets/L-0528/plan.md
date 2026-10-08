# L-0528 plan

Written by the implementing session (rush/h3-review, from origin/main `a555ff37`).

1. Test first: `test_review_run_exit_codes_are_distinct` (test_review_run_launch.py) collects every
   `EXIT_*` int in `review_run` by introspection and asserts no value is shared; it is RED on main
   (5 twice). `test_probe_codes_stay_and_the_unverified_refusal_moved_off_5` (test_review_limit.py)
   pins 5/6/7 for the probe and 9 for the refusal.
2. `review_run.py`: `EXIT_UNVERIFIED = 9`; the module docstring's three "exit 5" lines and the exit
   table say 9 and that 5/6/7 belong to `--probe` alone.
3. Tests that asserted the literal 5 for the gate or pre-review refusal assert
   `review_run.EXIT_UNVERIFIED` (test_review_gate.py, renaming `..._exit_5_...` to
   `..._exit_unverified_...` and the sabotage entry that names it; test_review_run_prereview.py;
   test_review_run_standards.py).
4. Sabotage: one `REVIEW_FIX_MUTATIONS` entry, `EXIT_UNVERIFIED = 9` back to 5, named test the
   distinct-values test. Placed beside the gate entries, not at the end of the tuple, to keep clear of
   the concurrent H1 lane's appends.
5. Docs: review.md (:440, :449, :472, line count unchanged), README (:766, diagram labels), the
   working-with-codex guide (+ rebuild), the two review `.mmd` sources and the generated diagram
   README/index lines that mirror them, the code map, CHANGELOG with a Breaking line.
