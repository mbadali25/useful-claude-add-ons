# L-0650: wire the GitHub-deploy mutations into the sabotage harness (tooling only)          status: direction   risk: med   priority: med

Split from T-0045 on 2026-10-04 (T-0045 direction.md, "Direction check 2026-10-04", option 1).

## Problem
T-0045 and its children L-0644 to L-0649 each add mutations to `plugin/crew/tests/ghdeploy_mutations.py`, which nothing runs by default: `plugin/crew/tests/sabotage*.py` is review/gate harness, and a harness change may not ride in a feature PR (owner rule, 2026-09-28, T-0087). Until the file is wired, the full `sabotage.py` run does not prove those tests can go red.

## Decision
One tooling-only PR adds `GHDEPLOY_MUTATIONS` to `sabotage.py`'s `MUTATIONS`. No production code, no prompt, no feature.

## Options considered
1. **Import the existing file from `sabotage.py` (recommended).** Two edited lines, no file move, history kept.
2. Rename it to `sabotage_ghdeploy.py`. Matches the naming of the other families, but the rename is itself a harness path change and breaks the one-line runner the earlier slices document.
3. Leave it unwired, as T-0505's `promote_tree_mutations.py` still is. Then no gate ever runs it.

## Depends on
T-0045 and whichever children have landed. It can land once and be re-run as later children add entries, since it imports the tuple by name.

## Open questions for the owner
- Land it right after T-0045 (default, so every later child's mutations are in the full run from the start) or after the last child.
- `sabotage.py` is at the 3400-line pylint limit. Default: the import and the tuple are joined onto existing lines so the count does not grow.
