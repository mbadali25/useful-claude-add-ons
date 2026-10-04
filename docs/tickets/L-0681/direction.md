# L-0681: the verify gate, the scope and completion wrappers and the review gate inherit the main checkout's repo config in a linked worktree (tooling PR)

Split from T-0096 on 2026-10-04. Filed as L-0681.

## Problem
The review/gate harness still reads only the worktree's own `.crew/config.json`. Lines at origin/main `155fe6d8`:
- `verify-gate.sh:164`, `verify-gate.ps1:510-511`: `verifyGate: false`. `verify-gate.sh:993`, `verify-gate.ps1:1363-1364`: `verify.stopBudgetSeconds`. `verify-gate.ps1:402-410`: the incident stand-down.
- `review_gate.py:126` reads the own file on purpose, to agree with `verify-gate.sh:164`. It is allowlisted for this ticket (`test_worktree_config.py:220-223`) and pinned by `test_review_gate.py:158-170`, whose comment says to flip the test and route both together.
- `verify_fingerprint.py:80` fingerprints the own `.crew/config.json` as the file that carries the Stop budget.
- `scope-guard.sh:26-30`, `completion-audit.sh:24-28` (`_scope_provably_off`) and `scope-guard.ps1:221`, `completion-audit.ps1:220` (`Test-ScopeProvablyOff`): with no usable python, an **absent own file** is the proof that `scope.mode` is off. In a lane whose main checkout sets `scope.mode: block`, the own file is absent, so a session without python writes and stops unjudged, while `scope_guard.py` with python blocks (`crew_ticket.py:658` reads the inherited file). That is a fail-open.

Every one of these files is in `HARNESS` (scripts/check-tooling-pr.py:58-87), so they cannot land with T-0096 or L-0680.

## Direction
One tooling-only PR after T-0096 has merged:
- The gate reads `verifyGate` and `verify.stopBudgetSeconds` from the resolved config, in both flavours, and `verify-gate.ps1`'s inline incident check reads the resolved `standDown`.
- `review_gate.py` and `verify_fingerprint.py` use `crew_common.repo_config_file`, in the same commit as the gate, and the pinned test is flipped.
- The provably-off readers prove against the resolved file, and `unknown` is never provably off.
- The mutations for the whole of T-0096 (resolver, cloud guard, these readers) are added to `sabotage_limit_worktree.py`, which a feature PR could not touch.

## Options
1. **(Recommended, taken)** Route all four harness readers in one tooling PR. They share one behaviour and one test matrix, `review_gate.py` must move with `verify-gate.sh`, and together they are about 125 production lines.
2. Two tooling PRs (gate + review gate, then the scope wrappers). Not needed for size; costs a second harness review.

## Open questions for the owner
1. **This can loosen a lane.** A lane whose main checkout says `"verifyGate": false` gets no Stop gate, and `/crew:review` reads NO_GATE there, where today the lane's gate runs. Default: yes, it is the owner's setting and the Python readers already behave this way for every other key; a lane that must be gated writes its own config. `verify-gate --ci` still exits 2 on an inherited `verifyGate: false`.
2. **`unknown` is not provably off.** Default: with no python, a lane where git cannot name the main checkout blocks writes and the Stop. The alternative is today's fail-open.
3. **`.crew/verify.json` is not inherited.** Default: unchanged. The resolver covers `config.json` and `crew.json` only; a lane with no verification map still has no gate.
