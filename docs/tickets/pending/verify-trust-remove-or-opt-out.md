# Remove the verify-map trust re-approval, or let the owner opt out of it; make the agent-assisted route default-on

Priority: NEXT (first in the queue, owner 2026-11-18), above the priority-D automation tickets. Scale mapping unconfirmed.
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-18 from the owner's request and one coordinator addition.
Siblings: `automate-verify-trust-approval.md` (the agent-assisted route this ticket now builds on), `verify-gate-trust-codes-10-13-exit-0.md`.

Labels: VERIFIED = read in a fresh clone of origin/main `016c7b1` (path:line below); INFERRED = reasoned, not run. Nothing here was executed.

## Owner's words (verbatim)

> "we need to remove the functionality or at least be able to opt out of it"
> "please add that as a ticket a next item"

Added by the owner via the coordinator, 2026-11-18: the agent-assisted approval route (the owner types `/crew:allow-run <id>`, the agent runs
`verify_trust.py approve --receipt`) "should be on by default".

## Problem

Whenever `.crew/verify.json` changes (the example the owner hit: after #787 changed it), the owner must run `verify_trust.py approve` again
before the Stop gate runs the repo's rules.

- VERIFIED, `plugin/crew/hooks/scripts/verify_trust.py:20-24`: trust by hash records the sha256 of the verify.json bytes; any byte change is CHANGED until approved again.
- VERIFIED, `verify_trust.py:38-41`: `check` exits 0 trusted, 10 UNTRUSTED, 11 CHANGED, 12 REMOTE CHANGED, 13 UNKNOWN; anything but 0 means run nothing.
- VERIFIED, `plugin/crew/hooks/scripts/verify-gate.sh:1771-1776`: codes 10-13 take `*) exit 0`, only 14 (the check itself broke) exits 2. So after a verify.json change the Stop gate silently runs nothing and lets the turn end; the owner gets verification back only by re-approving. (Whether 10-13 should block is the sibling ticket `verify-gate-trust-codes-10-13-exit-0.md`; not decided here.)
- VERIFIED, `verify_trust.py:96-105`: `approve` refuses inside a Claude Code session (`CLAUDECODE` in the environment) and refuses without a TTY unless `--yes` in the owner's own shell.
- VERIFIED, `plugin/crew/CONFIG.md:123` and `verify_trust.py:49-54`: the one agent-assisted route is `/crew:allow-run <id>` plus `--receipt`, and it is OFF by default; it acts only when the machine config `~/.claude/crew/config.json` names `verify-trust` in `approvals.run.classes` (`CONFIG.md:276`, default `[]`; `crew_runapproval.py:26-28`, machine layer only).
- VERIFIED, `verify_trust.py:43-47`: the store is `${CLAUDE_CONFIG_DIR:-~/.claude}/crew/verify-trust.json`, not a crew config key, so no repo file can widen it.

## Ask

Remove the requirement, or at minimum give the owner an opt-out. Plus the owner's addition: the `/crew:allow-run` route is on by default. The options below are
candidates for the design step; the owner has not picked one.

1. Opt-out key (smallest). A machine-layer-only switch that makes the gate treat a repo as trusted without a hash match.
2. Trust on first use plus auto re-pin when verify.json changes in a repo the owner already trusted. INFERRED: weakens the hash guard for a hostile edit made after the first approval.
3. Allowlisted roots (for example `C:\repos`): every repo below a listed directory is trusted. INFERRED: similar in spirit to the existing `allow-owner ... --under DIR` (`verify_trust.py:26-36`), which already exists and is not default.
4. Remove trust entirely. INFERRED: re-opens the hazard in `verify_trust.py:13-16` (a cloned hostile repo's `run` strings reach `eval` on its first Stop).
5. Default-on agent route only (the owner's addition): leave the hash but make the owner's cost one typed `/crew:allow-run <id>` instead of a terminal.

## Constraints (hard)

- An opt-out MUST NOT be settable from the repo layer (`.crew/config.json`, `.claude/settings.json`, any repo file). A cloned repo could disable its own trust check. Machine layer `~/.claude/crew/config.json` only (the rule `crew_runapproval.py:28` already states), or one of the structural alternatives above. VERIFIED precedent: a project's `.claude/settings.json` `env` block reaches hook processes (`verify_trust.py:170-176`), so an env-var switch is repo-controllable and must not carry the opt-out.
- The default-on route must also stay machine-layer, never repo-layer.
- A turn that cannot read the machine config reads as "off" (an unknown must not collapse into the permissive value).

## Tension to resolve first: default-on versus the store guard (VERIFIED by the coordinator from PR #787's landing; not re-run here)

- With a run class ON, the store guard still over-refuses everyday commands: `git commit -m "... run-approvals ..."`, `rm -rf run-*`, `claude -c`, `pytest` on `test_approval_hook.py`, `git add approval_hook.py`, `pylint crew_runapproval.py`, and `echo '{}' > ~/.claude/crew/config.json`.
- With the class OFF, nothing guards `~/.claude/crew/run-approvals/`.
- So default-on needs the over-refusal fixed or narrowed first; turning it on by default today would block ordinary work. INFERRED: the fix is in the textual patterns of `scope_guard.py` (`_TRUST_RE` at line 169 is the trust-verb pattern; the run-approvals store pattern was not read for this ticket). Reproduce each command above before narrowing.

## Acceptance criteria

1. The owner can stop re-approving after a verify.json change by a documented, machine-layer-only setting (or the requirement is removed), chosen in the design step.
2. A `.crew/config.json` (or any repo file) carrying the opt-out has no effect: must-block case.
3. With the opt-out set in the machine config, a changed verify.json runs the gate: must-allow case. With it unset, behaviour is exactly today's (10-13 run nothing).
4. An unreadable, duplicate-keyed or wrongly typed machine config reads as off (must-block).
5. `/crew:allow-run <id>` with `--receipt` works with no config edit: `verify-trust` is in the effective default `approvals.run.classes`, read from the machine layer only; a repo file naming the class changes nothing (must-block).
6. None of the seven everyday commands above is refused by the store guard when the class is on; the guard still refuses a command that really writes or reads the receipt store (must-block and must-allow rows for each).
7. Something guards `~/.claude/crew/run-approvals/` whatever the class value (the class-OFF gap), or the ticket records why not.
8. Sabotage rows: reintroduce each bug (repo-layer opt-out honoured; over-refusing pattern restored; default class list emptied; unreadable config read as on) and confirm the suite goes red, per CLAUDE.md "Adding a hook".

## Landing and process

- Touches HARNESS paths (`scope_guard.py`, `verify-gate.sh`; `HARNESS` and `SEAM` in `scripts/check-tooling-pr.py`, not re-read here), so by owner rule T-0087 it lands ALONE: no feature work in the same PR; tests, docs and version files may ride along. INFERRED: the config-default change in `crew_runapproval.py` may need to be a separate feature PR after the guard PR.
- Crew version bump required (content change), in `plugin.json` and the marketplace entry.

## Docs to update in the same PR(s) (CLAUDE.md: crew change updates every document that describes it)

- `plugin/crew/CONFIG.md`: "Verify gate trust" (line 382 onward) and the `approvals.run.*` rows (lines 276-278). VERIFIED: CONFIG.md is 599 lines and `plugin/crew/tests/test_crew_config.py:3151` asserts `len(text.splitlines()) < 600`, so one more line fails. Raise the cap in that test (and its docstring at line 3137) or make room, in the Touch list.
- `plugin/crew/README.md`, the `/crew:allow-run` command file, `plugin/PLUGINS.md` row, `docs/guides/crew/src/*.md` plus the rebuilt HTML, DOCX and PDF (`build.py`, `config_reference.py`), `.crew/codemap/`, `docs/diagrams/`.
- The Configuration Guide built from `docs/guides/crew/src/`, AND the published Claude Docs document titled "Configuration Guide" (CLAUDE.md standing rule: a key, value or default change updates both).
- The stale docstring in `verify_trust.py:43-54` ("default off") and `crew_runapproval.py:26`.

## Owner questions

1. Which option: remove, machine opt-out key, trust on first use with re-pin, allowlisted roots (which?), or default-on route only?
2. Should the opt-out apply to all repos or only repos under listed roots (for example `C:\repos`)?
3. Is a silent no-run Stop after a verify.json change (codes 10-13 exit 0) acceptable once the owner has opted out of trust, or should an opted-out machine still hash and warn?
4. Default-on for `verify-trust` only, with `approve` the only verb (today's `approvals.run.verbs.verifyTrust` default), or also `revoke`?

## Out of scope

Letting any repo file widen trust; changing the hash algorithm; the exit codes of 10-13 (sibling ticket); the other priority-D automation tickets.
