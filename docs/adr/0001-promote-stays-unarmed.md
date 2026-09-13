# 1. `/crew:promote` stays unarmed in this repo

**Status:** accepted, 2026-09-13
**Decided by:** the user, on a recommendation from the crew PM

CLAUDE.md says decisions live in `docs/adr/`. The directory did not exist
until this file; the design records already in `docs/` (`change-requests.md`,
`guard-overrides.md`, `rule-of-two.md`) are specifications rather than
decisions, so this starts the numbered series the project file already names
instead of adding a fourth flat document.

## Context

`/crew:promote production --dry-run` and `--status` were run here. Both stop
immediately: `.crew/verify.json` declares no `environments` block, so the gate
chain is empty. There is nothing to dry-run.

That is not a gap in the map. This repo deploys nothing. CLAUDE.md's own
promotion section says so in as many words — "Nothing is deployed;
'production' means merged to `main` and installable." The two steps that do
matter at promotion time are already written down there and neither is a
deploy: run `scripts/_test/drift-detection.sh` by hand, and re-pin the README
install URLs after an install-script change.

Verified rather than assumed, by simulating candidate deploy commands against
the resolver: `gh pr merge`, `./scripts/deploy.sh prod`, `git push origin main`
and `claude plugin update` all return NO MATCH, and there is no
`.crew/.deploy-in-flight`. `bitbucket.mergeGate.enabled` is `false`, confirmed
through `crew_config --explain`.

## Decision

Leave it unarmed. Do not write an `environments` block.

## Why not arm it

**A deploy-less `environments` block would be worse than none.** It would make
gate 2 structurally empty while the command reads as "promote works" — a check
that cannot fail, wearing the label of one that ran. That is this repo's named
recurring bug, and shipping an instance of it inside the promotion machinery
would be a poor place to start.

**The only honest deploy candidate cannot be declared safely.**
`promote-gate.sh:54` matches a declared deploy command against the invoked one
as a substring **in both directions** (`if d and (d in cmd or cmd in d)`) — it
is deliberately generous. Declaring `gh pr merge` as this repo's deploy would
therefore gate *every* merge on the machine, not only promotions.

**A `requires` clause could never be satisfied.** The natural artefact to
require is `.work/PROMOTIONS.md`, and `.work/` is gitignored. A requirement
pointing at a file that cannot be committed is a permanent red.

## Consequences

- `/crew:promote` reports an empty chain here, and that report is correct.
  Nobody should read it as a misconfiguration.
- Promotion discipline stays where CLAUDE.md already puts it: the hand-run
  drift check and the URL re-pin.
- Revisiting this needs a prior decision, not a config edit: something has to
  own writing `.work/PROMOTIONS.md`, and `.work/` has to stop being ignored,
  before an `environments` block can mean anything.
