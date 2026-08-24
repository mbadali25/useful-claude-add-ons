# Offboarding a role

`/crew:scale` today only adds roles. This is the removal path, and it is
new capability — there is no existing procedure to match against, so follow
this exactly rather than improvising a shorter version.

Report and recommend only — see `SKILL.md`'s authority section. Get the
user's explicit yes before touching `.crew/config.json` or deleting
anything.

## The one outcome this must never produce

A role removed without naming what it was catching is a silent coverage
regression: the crew gets cheaper and nobody finds out it also got blinder
until the defect that role used to catch ships. Every offboarding ends with
a sentence naming that failure mode out loud, in a place someone will read
later. That sentence is not optional polish — it is the actual point of
this procedure. Everything else here is bookkeeping in service of that one
line existing and being findable.

## Steps

1. **Remove the role.** Delete it from `.crew/config.json` → `roles`.
2. **Recompute `tier`.** Use the tier table in `crew-scaling/SKILL.md` — do
   not restate that table here, it drifts out of sync with this copy if you
   do. Removing a role can drop the crew below the tier it currently claims;
   set `tier` to match what `roles` actually contains, not what it used to.
3. **Record the removal in `.crew/metrics.md`.** Append a plain dated line,
   not a pipe-table row — the review-metrics table has a fixed five-column
   shape (`date | ticket | reviewer | BLOCK | FIX`) that `crew_state.py`
   parses by column position, and a removal note in that shape would either
   get silently skipped (harmless) or, worse, get misread as a review row if
   it happens to have five pipe-delimited fields. A line like:

   ```
   2026-08-24 — offboarded `dba`: no migration in the last 40 tickets;
   metrics showed 0 DB-related findings over that window. Coverage lost:
   unreviewed migrations shipping without a rollback path. Re-add if
   migrations resume.
   ```

4. **Clean role-specific artifacts.** Anything that existed only to support
   this role — its dedicated checklist file, a review template named after
   it, cached output only it consumed. Leave anything shared with other
   roles or with the crew in general; offboarding one role should not erase
   history other roles or the user still rely on.
5. **Name the failure mode now uncovered**, out loud, to the user, and
   confirm the same sentence made it into the `metrics.md` line from step 3.
   Be concrete: not "less review," but the specific defect class that role
   was the one thing catching. If you cannot name one, that is itself worth
   saying — it means either the role was never earning its cost (a clean
   removal) or you don't actually know what it covered (find out before
   removing it, not after).

## Re-adding later

A role removed with a clear reason and a named coverage gap is cheap to
re-add later — the sentence from step 5 is exactly the evidence `crew-scaling`
would want to see before scaling back up. A role removed with no reason
recorded has to be re-justified from scratch, which is the real cost of
skipping step 5.
