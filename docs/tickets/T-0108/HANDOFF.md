# Cloud handoff: T-0108

**gizmoduck safe Nuclei defaults: dos/intrusive/fuzz excluded and a rate limit unless opted out by name (item 11 of a report from another repository's session)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent ticket, narrowed to report item 11. Children: L-0684 (item 10, tool lookup) and L-0685 (item 9, bootstrap without sudo and a CI guide).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0108-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0108/direction.md`, `docs/tickets/T-0108/spec.md`
- **Size:** about 95 production lines (`gizmoduck.py` about 70, `scanners/nuclei.py` about 20, `routine.py` about 3). No harness path, and `plugin/crew` is untouched: this is a gizmoduck-only feature PR. Risk is marked med in the spec.

This ticket was first handed to the cloud on 2026-09-30 as a seed direction only (`docs/handoff/cloud/T-0108.md` on main, no branch, no PR). This handoff replaces that note: it adds the direction check and the spec. The spec requires this ticket's PR to delete `docs/handoff/cloud/T-0108.md` and its row in `docs/handoff/cloud/README.md`.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0107 | done (merged as PR #273, gizmoduck 0.5.5) | Added `gizmoduck.py routine`, `_check_manifest_shape` and `_gate_option_keys`, which this spec extends with the `nuclei_intrusive` and `nuclei_rate_limit` options. |
| L-0599 | done (merged as PR #315, gizmoduck 0.5.6) | Pylint fix on `gizmoduck.py`; the version this ticket bumps from. |

Nothing open blocks this ticket. It blocks nothing hard: L-0684 and L-0685 are independent of it in code. All three bump gizmoduck's version and edit the same README, so they land one at a time, each merging origin/main first (merge, never rebase).

Same report, no ordering constraint: T-0104, T-0105, T-0106, T-0500, T-0501, T-0502, T-0503.

Family order:

1. T-0108 (this ticket) first, as the direction recommends: it changes what traffic a scan sends, so it is the one with a safety consequence. This order is a recommendation, not a code dependency.
2. L-0684: one tool-home lookup rule for every adapter.
3. L-0685: needs L-0684 merged first (it installs into the tool home L-0684 defines).

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published (none existed). The implementing session writes the plan.
- In spec.md, `children/1/` means L-0684 and `children/2/` means L-0685.
- Nothing was run when the spec was written: no pytest, no scanner. The Nuclei flag names and precedence (`-etags`, `-itags`, `-rl`, `-rlm`) come from Nuclei v3's help text. Before implementing, run `nuclei -h` on the version bootstrap installs, record the version in the PR, and confirm with the template lister (sends no traffic) that exclusion beats `-tags`. If it does not, stop and report; the design assumes it does.
- Also from `nuclei -h`: any other switch that enables fuzzing or attack traffic joins the strict refusal list. If the list grows past the eight names in the spec, say so in the PR.
- This is a behaviour change, to be flagged in the CHANGELOG: a default scan runs fewer templates and sends at most 50 requests per second.
- The version to bump is gizmoduck's (0.5.6 at `155fe6d8`; the spec takes 0.6.0), in `plugin/gizmoduck/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md`. The crew version is not bumped by this ticket. The PR body says `Docs: none for crew - gizmoduck only`.
- Sabotage is by hand, quoted in the PR.
- If Nuclei is not installed where the PR is built, say so; do not imply the manual check ran.
- direction.md holds two owner decisions from 2026-09-30 that still apply: catch up with main by merge, never rebase, force-push or squash; and the parallel-suite instructions. The heavy-run wrapper they name is a local tool of the original host; the cloud session uses its own equivalent.

## Open questions for the owner (recommended option taken)

1. Default Nuclei rate limit: 50 requests per second (Nuclei's own is 150). Alternatives: 25, 150, or no default with a required manifest value.
2. Excluded tags: `dos,intrusive,fuzz`, as the report names them. Add `bruteforce`?
3. Version 0.6.0, because a default changed. Alternative: 0.5.7.
4. Manifest `nuclei_intrusive: true` does not also need `--confirm-active` (matches `zap_active` and `nmap_vuln`). Should it, like sqlmap?
5. In a routine manifest, tag and rate flags inside `options.extra` are refused (exit 2). Alternative: allow them and record the cell as `ran(custom)`.
6. `scan --extra` stays unchecked for tag flags on the single-scanner CLI. Alternative: refuse them there too so `--intrusive` is the only way.

The children's questions are listed in L-0684 and L-0685.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0108/` in the final PR unless the owner wants it kept. For this ticket the version taken from the coordinator is gizmoduck's, not crew's.
