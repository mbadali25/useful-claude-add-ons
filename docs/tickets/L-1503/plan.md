# L-1503 plan: promote-gate.ps1 matches deploy commands literally

Severity high, on main. Found reviewing #407. No spec folder; this plan is the contract and is
deleted in the final content commit.

## Bug

`plugin/crew/hooks/scripts/promote-gate.ps1:134` picks the environment with
`$cmd -like "*$dep*" -or $dep -like "*$cmd*"`. `-like` reads `*`, `?` and `[set]` in a deploy
string as wildcards:

- (a) a literal deploy containing `[...]` (`./deploy.sh && curl -s https://x/status | jq .items[0]`)
  never matches itself, so a `requireHuman` environment exits 0 with no in-flight marker, where
  promote-gate.sh exits 2;
- (b) a pattern `-like` cannot parse (`[`, `[]`, `[z-a]`, `[!-[]`) throws
  WildcardPatternException; the statement fails, the loop moves on, the gate exits 0;
- and `*` / `?` in one environment's deploy can claim a command meant for another.

The committed-map path (`:90`) uses `.Contains`, which is literal but case-sensitive, so the two
paths in one script disagree on case.

## Fix

One helper used by both paths: a literal, case-insensitive (`OrdinalIgnoreCase`) substring test in
both directions, on the command with every CR removed (promote-gate.sh runs `crew_strip_cr` on the
command before matching). Any exception while matching blocks with exit 2 before the emergency
lane, like the sh flavour's traceback path: the environment could not be determined.

## Tests (new `plugin/crew/tests/test_promote_gate_literal_match.py`, written first)

- must-block (ps1, and sh where it applies): the `jq .items[0]` env; `[`, `[]`, `[z-a]`, `[!-[]`;
  a `*` and a `?` deploy that must not claim another environment's command; a non-string command
  (makes the matcher throw) blocks instead of skipping; the committed-map path with a dirty map.
- must-allow: the same literal deploys allow once approved, naming the right environment; a plain
  deploy matches case-insensitively on ps1; an unrelated command passes untouched.
- agreement: sh and ps1 pick the same environment on every map in a table.
- sabotage by hand: restore `-like`; swallow the exception. Both must go red.
