# Cloud handoff: L-0685

**gizmoduck `bootstrap.sh` without sudo, and a CI and containers guide (item 9 of a report from another repository's session)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**Needs L-0684 merged first.** Without L-0684's tool home, nothing a `--user` install puts down is found by gizmoduck.

- **Role:** child ticket, split from T-0108, slice 2 of 2 (the other is L-0684).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0685-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0685/direction.md`, `docs/tickets/L-0685/spec.md`
- **Size:** about 150 production lines, all in `plugin/gizmoduck/bootstrap.sh`. No harness path, and `plugin/crew` is untouched: this is a gizmoduck-only feature PR. Risk is marked med in the spec.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0684 | open, not built (direction; handed off 2026-10-04) | Defines the tool home and makes `base.which` look in its `bin`. `test_user_mode_tool_home_matches_base_tool_home` imports its `tool_home()`. Must be merged first. |
| T-0107 | done (merged as PR #273) | The `routine` CLI the CI section points at. |
| L-0599 | done (merged as PR #315, gizmoduck 0.5.6) | The version this family bumps from. |

This ticket blocks nothing.

No hard dependency on T-0108 (the parent; safe Nuclei defaults). If T-0108 has landed by then, the CI section should mention the safe defaults. All three tickets bump gizmoduck's version and edit the same README: land one at a time, each merging origin/main first (merge, never rebase).

Family order:

1. T-0108 first, as the parent's direction recommends (a recommendation, not a code dependency).
2. L-0684.
3. L-0685 (this ticket), after L-0684 has merged.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan.
- No Python change here. The tool-home rule in the script must equal `scanners/base.py` `tool_home()` as L-0684 merged it; read that first.
- The suite must never install anything or reach the network: every test runs `--dry-run` or a refusal, against fakes on a temp PATH. The privilege decision calls `id -u` and `command -v sudo`, not `$EUID`, so the tests can simulate root.
- The real end-to-end runs are manual, in a throwaway Ubuntu 24.04 container, quoted verbatim in the PR or stated as not done. Never run them on a workstation or a CI runner's host.
- Not verified when the spec was written: whether `pip3 install --user` is refused on Ubuntu 24.04; whether trivy's install script works unprivileged with `-b`; the upstream archive layouts of nikto and ZAP. Each is resolved at implement time as the spec's Unknowns say. If pip is refused on main today, record it in `TODO.md` and the README; do not widen this ticket without the owner.
- `bootstrap.sh` stays LF. Edit it as text.
- The no-Docker decision stays: no image, no Dockerfile, no `docker run`.
- The README's CI section names no real host, account, pipeline or organisation; placeholders only. Secrets come from the pipeline's secret store, and `GITHUB_TOKEN` is never printed.
- Behaviour change to flag in the CHANGELOG: `bootstrap.sh` used to exit 0 after a partial install; it now exits 1.
- The version to bump is gizmoduck's, in `plugin/gizmoduck/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md`. The crew version is not bumped. The PR body says `Docs: none for crew - gizmoduck only`.
- Sabotage is by hand, quoted in the PR. If shellcheck is not available, say so; that is not a pass.

## Open questions for the owner (recommended option taken)

1. Not root and no `sudo`: exit 2 and point at `--user`. Alternative: switch to `--user` automatically.
2. `bootstrap.sh` exits 1 after a partial install, where it used to exit 0. Alternative: keep 0 and add `--strict`.
3. Skipped-only is exit 0 with a `GIZMODUCK_BOOTSTRAP_SKIPPED:` last line. Alternative: a distinct non-zero status.
4. `GITHUB_TOKEN` is used for release lookups when set. Alternative: a gizmoduck-specific variable name.
5. If `pip3 install --user` is refused on Ubuntu 24.04 (not verified), should `--user` build a virtual environment under the tool home for checkov and semgrep? Default taken: no, record as a follow-up.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0685/` in the final PR unless the owner wants it kept. For this ticket the version taken from the coordinator is gizmoduck's, not crew's.
