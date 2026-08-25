# Onboarding

Two different things share the word: onboarding a repo (crew has never run
here) and onboarding a role (the crew exists, and gets one more member).
Report and recommend only — see `SKILL.md`'s authority section — before
either.

## Onboarding a repo

Do not run any of this yourself. Delegate.

1. Delegate to `crew-setup` for the phased bootstrap. That skill owns
   detection, the three setup questions, and `.crew/config.json` creation —
   duplicating any of it here would give the repo two sources of truth for
   the same decisions.
2. Once `.crew/` exists, run `/crew:onboard` to build the codemap.
3. Confirm the setup actually produced a usable crew, not just files that
   exist:
   - `.crew/verify.json` — the map from changed paths to the checks they
     require, built by `/crew:verify`. Present and not stubbed out. A verify
     gate that always passes is worse than none, because it looks like a
     safety net.
   - `.crew/secrets.md` — present if the repo has any secrets to track at
     all. Absence is fine for a repo with none; silence about whether it was
     checked is not.
   - `e2e/` — present if `crew-setup`'s detection found a UI to test.
     Absence is fine for a pure backend or library repo.

Report which of the three exist, which are legitimately absent and why, and
stop there. `crew-setup`'s own Step 5 already tells the user not to start a
feature until `scripts/smoke.sh` runs green — repeat that, don't relitigate
it.

## Onboarding a role

State the cost before naming the benefit. Every role added is:

- A full context load for that role's agent definition, every time it runs.
- The whole `CLAUDE.md` hierarchy, loaded again on every invocation — this
  is not shared with the main session's copy.

That cost is fixed regardless of whether the role ever finds anything. It is
paid on every ticket from the moment the role is added.

Before recommending a role, name the specific defect class it closes. "More
review" is not a defect class; "SQL migrations shipping without a rollback
check" is. A role proposal that cannot name what it catches is not ready to
propose.

Then check `.crew/metrics.md` supports it. The evidence bar is the same one
`crew-scaling` applies to growth in general — a recurring defect class
reaching review is the one clean case for a new role, named after that
class. If metrics don't show the pattern yet, say that plainly rather than
adding the role speculatively; a role justified by a single ticket cannot be
told apart from a role justified by nothing.

If the evidence holds: get the user's yes, then add the role to
`config.json.roles`, recompute `tier` from `crew-scaling`'s tier table, and
tell the user what the role now covers so the coverage is legible later —
this is the mirror of offboarding's requirement to name what coverage is
lost, applied on the way in instead of the way out.
