# Guardrail overrides and the merge-gate workflow — design

**Status: shipped 2026-09-13** — crew 0.19.30 (#142: `guards` block, production access levels, `github.mergeGate`, `/crew:gate`, schema 6) and the `github` skill 0.1.0 (#141: the merge-gate twin). The decisions below bind.
user and bind; the "open" section is what the builders must settle and record.

## The ask

Crew's guards refuse a fixed set of dangerous actions with no way to opt out per
machine. The user wants each one to be a **machine-global config choice**, plus a
workflow Claude follows when a merge gate is switched on, for both GitHub and
Bitbucket.

## Decisions

**Values: `block` / `ask` / `allow`, default `block`.** `block` is today's
behaviour. `ask` prints exactly what would run and stops for a yes at that
moment. `allow` runs without asking. Default `block` means the upgrade changes
nobody's behaviour. An unknown value fails closed to `block`, the way
`normalise_authority` fails to `report-only` and `normalise_install_policy` to
`manual`.

**Layering: global sets the ceiling; a repo may only narrow.** Same ratchet as
`install.policy` — effective value is the lower rank of the two layers, so a
cloned repo can tighten `allow` to `ask` and can never loosen. Without this a
repo you clone grants itself force-push rights on your machine. Normalise both
sides before ranking.

**Keys** (one block, so the ratchet is a table, not five copies):

```
guards.terraformApply   block | ask | allow   — terraform/tofu apply, incl. -chdir forms
guards.forcePush        block | ask | allow   — git push --force / -f / --force-with-lease to any branch, protected or not
guards.adminMerge       block | ask | allow   — gh pr merge --admin and equivalents
guards.mergeGate        block | ask | allow   — may crew disable/re-enable a live merge gate
install.policy          manual | ask | auto   — already shipped; unchanged
guards.prodDatabase     none | read | full    — added 2026-09-13, see below
guards.prodServer       none | read | full    — added 2026-09-13, see below
```

**Production access (added by the user after the first four).** The *level* is
machine-global with the same ratchet (`none` < `read` < `full`; repo narrows
only; unknown fails closed to `none`). *What counts as production* is a fact
about a checkout, so it lives in the repo file: `production.databases` and
`production.hosts`, lists of glob patterns matched against connection strings,
hostnames and `ssh`/`psql`/`mysql`/`sqlcmd`/`aws rds|ssm` targets. **With no
patterns declared the guard matches nothing**, which is what lets the default be
`none` without changing anyone's behaviour on upgrade. `read` permits statements
and commands the guard can classify as read-only; anything it cannot classify is
treated as a write — unknown is not read.

**The merge-gate workflow is explicit, never automatic.** A crew command,
`/crew:gate <disable|enable|status> <github|bitbucket>`, and `/crew:promote`
calling it inside gate 1 as it already does for Bitbucket. Nothing changes a
live repo's protection unless a command was typed or a yes was given.
`guards.mergeGate` governs whether the command may act at all.

**GitHub gets a twin of `skills/bitbucket/scripts/merge_gate.sh`**, in a
`github` skill: export the branch protection / ruleset to a file, remove it,
restore **from that export** — never a bare re-enable, which drops whatever the
export held. Mirror the Bitbucket script's interface and exit semantics
(`disable ... --export-to --dry-run`, `enable ... --from-export`, exit 3 = scope
undetermined and nothing deleted, exit 4 = partial writes). `adminMerge` is a
separate, lighter guard: it bypasses without touching protection.

**Config shape for the gates**: keep `bitbucket.mergeGate.{enabled,branch,preset}`
and add `github.mergeGate.{enabled,branch}` — symmetrical, and `preset` is not
copied because it binds to nothing (CONFIG.md §8).

## Invariants the builders must keep

- `enabled: false` means do nothing at all, never "apply the disabled preset".
- Never `disable` then bare `enable`; the only restore is `--from-export`.
- "Could not check" is its own outcome; it never collapses into "checked, fine".
- Under `allow`, the guard still logs what it let through, so the record exists.
- Every guard fix ships with a must-block case that reproduces the bypass and is
  run red before the fix, in **both** shell flavours (`guard.sh` and `guard.ps1`
  drift independently — three bypasses fixed in #132 were open in both).
- Schema bump (5 → 6) for the new blocks; migration proven through `run()` on a
  schema-5 fixture, not only through `upgrade_config()`.

## Open — settle and record in the change

- Whether `forcePush: allow` still refuses `main`/`master` outright or honours
  the value everywhere. Recommendation: honour it — the user chose the value —
  but `ask` and `allow` both print the target branch before acting.
- Which GitHub API the export uses: classic branch protection vs rulesets. A
  repo may have both; the export must capture both or say which it could not.
