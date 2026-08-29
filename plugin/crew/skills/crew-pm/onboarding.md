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

### The roster

These are the roles that exist. Onboarding one that is not on this list means
writing its agent definition first — a name in `config.json.roles` with no
`agents/<role>.md` behind it dispatches nothing and fails silently.

| Role | Closes | Tier |
|---|---|---|
| `explorer` | "where does this live" answered by loading files into the wrong context | 0 |
| `qa-reviewer` | code merged with nobody but its author having read it (the fallback when Codex is absent) | 0 |
| `security` | auth, input-handling and permission defects reaching review | 1 |
| `smoke-author` | changes shipping into a repo with no check that would have caught the regression | 1 |
| `developer` | implementation done in the manager's context, or in a context that then reviews itself | 1 |
| `dba` | migrations and large-table queries merged without a rollback or an index check | 2 |
| `docs-writer` | architecture and data-flow docs drifting until nobody trusts them | 2 |
| `browser-tester` | UI regressions that an API smoke check cannot see | 2 |
| `analyst` | working the queue without anyone asking whether it is the right queue | 2 |
| `planner` | designs reworked after implementation already started | 2 |

`pm` is not on the ladder. It is not sized in or out by `/crew:scale` — it is
the thing doing the sizing.

### `developer` is the one role justified by delegation, not by metrics

Every other role above earns its place by a defect class showing up in
`.crew/metrics.md`. `developer` does not, and pretending otherwise would make
this procedure unusable for it: it closes a *structural* gap rather than a
defect class. Without it, either the PM implements — which burns the one
context that holds the project picture and produces work nobody independent has
read — or the main session does, which is fine until the PM is the one running
the work end to end.

So the bar for `developer` is a question, not a metric: **is the PM expected to
take work from assigned to done on its own?** If yes, onboard it — a PM with no
developer either narrates or does the work itself, and both are failures. If
no, and the user is still the one writing code with the crew reviewing, leave
it off; it would sit unused and cost a context load on every dispatch decision.

Say which of those two the repo is in when you propose it. That sentence is the
justification, and it is the one an offboarding six weeks later will be checked
against.
