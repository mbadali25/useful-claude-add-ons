# T-0045 plan: slice 1, the `github` entry and `crew_ghdeploy.py check`

Written 2026-10-04 by the implementing cloud session, from spec.md (refreshed 2026-10-04)
and origin/main `baf193aa`. The 2026-09-26 plan.md was never published; this plan replaces
it for slice 1 only. Every child (L-0644 to L-0650) plans itself.

## Re-checked anchors (origin/main `baf193aa`)

- `plugin/crew/hooks/scripts/promote-gate.sh` reads `deploy` as a string or list of strings
  and matches `d in cmd or cmd in d`; unknown environment keys are ignored. A `github` key
  breaks no existing map.
- `.crew/verify.json` has no rule naming `crew_ghdeploy.py`; `git grep ghdeploy` on main is empty.
- `scripts/check-tooling-pr.py` `HARNESS` holds `plugin/crew/tests/sabotage*.py`; a new
  `ghdeploy_mutations.py` matches no harness glob.
- `plugin/crew/tests/promote_tree_mutations.py` is the unwired-mutations precedent.

## Design (slice 1)

The entry. `environments.<env>.github` is one object or a list of objects, normalised to a
list. Keys, closed set (an unknown key is refused):

| key | required | rule |
|---|---|---|
| `workflow` | yes | a filename `[A-Za-z0-9._-]+` ending `.yml`/`.yaml`, not starting `-` (no display name, no numeric id) |
| `ref` | yes | value grammar; not starting `-`; no `..`; not `refs/tags/...` (branches only) |
| `inputs` | no (`{}`) | object; names `[A-Za-z_][A-Za-z0-9_-]*`; values strings in the value grammar |
| `shaInput` | no | an input name, not also in `inputs` |
| `correlationInput` | no | an input name, not in `inputs`, not equal to `shaInput` |
| `deployJob` | no | non-empty string with no control characters (an fnmatch glob read by L-0646) |
| `watchMinutes` | no (60) | integer 1..360, not a bool |
| `identifySeconds` | no (120) | integer 10..900, not a bool (L-0645's range) |

Value grammar `[A-Za-z0-9._/@:+-]+` (spec). A value outside it is refused with its name,
never quoted or escaped. `-R/--repo` cannot be expressed: there is no key for it.

Canonical prefix: `gh workflow run <workflow> --ref <ref>` then ` -f k=v` per input in the
entry's order. Dispatch: prefix, then ` -f <shaInput>=<40-hex HEAD>`, then
` -f <correlationInput>=crew-<env>-<sha7>-<8 hex>`. With `correlationInput` set, the
environment name must fit the value grammar too (it is inside the id).

The environment's `deploy` (string or list, as the gate reads it) must be exactly the set of
the entries' prefixes: each prefix present, and no other string. So promote-gate's existing
substring match fires on the real dispatch.

`check --root R --env E` exit codes and last line:

- 0 `result=ok entries=N sha=<sha>` after one `dispatch: <command>` line per entry;
  0 `result=ok github=none` for an environment with no `github` key (HEAD not read).
- 2 `result=refused reason=<code>`, preceded by a line naming the env, entry index and key.
  Codes: `github-shape`, `unknown-key`, `workflow-missing`, `workflow-not-filename`,
  `ref-missing`, `ref-dash`, `ref-dotdot`, `ref-tag`, `ref-chars`, `inputs-not-object`,
  `input-name-chars`, `input-not-string`, `value-chars`, `sha-input-in-inputs`,
  `sha-equals-correlation`, `correlation-in-inputs`, `deploy-job-bad`,
  `watch-minutes-range`, `identify-seconds-range`, `env-name-chars`, `deploy-prefix-mismatch`.
- 3 `result=could-not-tell reason=<code>`: `verify-json-absent`, `verify-json-unreadable`
  (unreadable, unparseable, not an object, `environments` not an object, environment not an
  object), `environment-absent`, `head-unreadable`. None reads as "no github entry".

It writes nothing and runs no `gh`; the only subprocess is `git rev-parse HEAD`.

JUDGEMENT (not in the spec, chosen here): the reason-code names, the `dispatch:` line prefix,
the `ref` grammar reusing the value grammar, the input-name grammar, the `deployJob` rule and
`refs/tags/` as the testable form of "no tag". Each is local to this module and a child can
rename it in its own landing.

## Steps (test-first, each red then green)

1. `plugin/crew/tests/test_crew_ghdeploy.py`: the spec's acceptance tests
   (`test_entry_problem` parametrised over every must-block case, `test_check_refuses_deploy_prefix_mismatch`,
   `test_check_unreadable_map_is_could_not_tell`, `test_prefix_is_listed_order`,
   `test_dispatch_appends_sha_then_correlation`, `test_check_prints_dispatch_for_head`,
   `test_environment_without_github_is_not_a_problem`, `test_check_calls_no_gh`,
   `test_dispatch_matches_promote_gate`). Run: red (module absent).
2. `plugin/crew/hooks/scripts/crew_ghdeploy.py`: `entries()`, `entry_problem()`, `prefix()`,
   `dispatch()`, `check()`, `main()`. Run: green.
3. `plugin/crew/tests/ghdeploy_mutations.py`: one mutation per refusing branch plus one
   must-allow non-vacuity entry, unwired; run with the spec's one-line runner. All RED, no
   ANCHOR LOST.
4. Docs: crew-verification SKILL.md section 4 (`github` keys, `check`, "the dispatch sequence
   is not built yet"); `plugin/crew/README.md` names `crew_ghdeploy.py check`; BUDGETS.md
   `crew-markdown-lines` re-measured; `.crew/verify.json` rule with measured seconds; code map
   entry for the new module; CHANGELOG. Rules regenerated.
5. Delete `docs/tickets/T-0045/` in the last content commit.
6. Version-only commit: crew to the placeholder version in every stated place.

Not in this slice: `prepare`, `identify`, `watch`, `record`, promote-gate, autopilot, any
`sabotage*.py`, `promote.md`, `crew_config.py`, templates.
