# T-0052 one split rulebook (crew_split.py) behind /crew:split in every tracker: files/Obsidian children via mint, Jira path unchanged, SDP stops (1 of 3; then T-0058, T-0059)          status: spec   risk: high
depends-on: T-0019, T-0037
## Decisions (standing authorization, 2026-09-26)
- Split ACCEPTED before approval, under the owner's standing authorization (autopilot-style self-decisions), because the pre-split contract tripped its own thresholds (10 plan steps, 14 acceptance checks) and its plan header already named three separable groups. The pre-split text is kept verbatim at `.work/tickets/T-0052/spec.pre-split.md` and `.work/tickets/T-0052/plan.pre-split.md`. Split out: T-0058 (autopilot's after-spec/after-plan size check and `/crew:autopilot split`) and T-0059 (plan `## PR slices`, shipped slice by slice through T-0011). Both depend on this ticket. Where every pre-split check and step went is the `## Split` table at the end.
- `/crew:split` stays model-invocable, and its confirmation refuses without a new human turn (Unknowns). This replaces the pre-split plan's `disable-model-invocation: true`.
## Intent
One split rulebook, `crew_split.py`, holds `/crew:split`'s judgement as code: split only on stated evidence, 2-5 children, every acceptance criterion placed verbatim or the split stops, each child's exclusions stated, and "not too big" reported as a result. `/crew:split` calls it here, and T-0058's `/crew:autopilot split` calls the same code later. `/crew:split` drops "Jira only" and works in files and Obsidian mode with the same rules and the same confirmation: the parent's text is kept as `spec.pre-split.md`, children are minted with T-0019's `mint`, and the parent becomes T-0037's `superseded`. Its Jira path stays as it is, and SDP mode stops with a clear message.
## Exclusions
- Split out (decided 2026-09-26). T-0058: `next`'s size check after spec and after plan, `split-check`/`split-approval`, `ticket_split_policy`, `apply --via autopilot`, `crew_autopilot.py split`, `autopilot.md`, and Jira mode always stopping for the owner under autopilot. T-0059: the plan's `## PR slices` section, `parse_slices` and its `crew_ticket.validate` report, slices run in order with `slices.json`, `review_ledger.open_slice` and the per-slice budget, and T-0011's ship per slice.
- No autopilot path here. This ticket adds no `next` phase and no approval policy, and `apply` accepts only `--via command`.
- No SDP split. SDP mode stops, naming the reason.
- No new ticket status. The parent becomes `superseded`, T-0037's word. No `split` or `cancelled` status is added here.
- No change to `/crew:split`'s Jira mechanics: MCP discovery, cloudId caching, sub-task-or-linked-issue choice, the parent comment and the cache files stay as they are. Only the judgement moves into shared code, and the "Jira only" precondition is removed.
- No change to `crew_ticket.mint`'s contract (T-0019). This ticket calls it.
- No approval grammar in the UserPromptSubmit hook. A `human` split approval is `/crew:split`'s existing in-chat confirmation, typed by the owner. The confirmation gate reads the turn record the context hook already writes and does not extend any hook. A `split:<id>` hook receipt, like T-0012's `goal:<slug>`, is a follow-up that needs the owner's explicit yes, because it extends a blocking hook.
- No thresholds in config. They are constants in `crew_split.py`, each carrying its evidence in a comment, so a change to one is a reviewed code change.
- No `disable-model-invocation` on `/crew:split` (decided, Unknowns).
## Evidence
Anchors are on origin/main 1e0706ac (crew 1.0.41) unless marked. Spec-only anchors are in `.work/tickets/<id>/spec.md` or `plan.md`, for tickets that have no branch yet (T-0019, T-0037).
- `/crew:split` today: `plugin/crew/commands/split.md:11-16` is the Jira-only precondition and its reason. `:24-26` forbids a silent files-mode fallback. `:42-54` is the evidence table (findings rate against `HEALTHY_HIGH` 2.0, the `ticketsTooLarge` trigger, more than one subsystem, criteria that cannot be verified together) and says the repo-wide rate is a reason to look, not a verdict. `:56-57` makes "not too large" a result. `:65-79` sets 2-5 children, the four fields per child, and requires every criterion to land somewhere. `:81-89` covers one confirmation for the whole set and `--dry-run`. `:91-109` is the Jira create, link and cache procedure, which leaves the parent untransitioned. The frontmatter (`:1-5`) has no `disable-model-invocation`. There is no SDP path.
- `plugin/crew/hooks/scripts/crew_state.py:189-190` (`HEALTHY_LOW` 0.3, `HEALTHY_HIGH` 2.0), `:2969-2970` (`ticketsTooLarge` fires when `health.rate > HEALTHY_HIGH`) and `:1029` (the trigger list).
- The tracker mode is read from `.crew/crew.json`, or `.crew/config.json` on an unmigrated repo (`plugin/crew/commands/brainstorm.md:21-22`). The config default is `tracker: "files"` (`plugin/crew/hooks/scripts/crew_config.py:265`), and `sdp` is a mode (`crew_config.py:275`, `plugin/crew/hooks/scripts/crew_migrate.py:100`). Obsidian mode adds a board card besides the INDEX row (`brainstorm.md:24-26`).
- The one manual split: `.work/tickets/T-0004/spec.pre-split.md` (kept verbatim), with the split recorded at `.work/tickets/T-0004/spec.md:5` and `:11`. Each child's direction points back to it (`.work/tickets/T-0010/direction.md:3`, `.work/tickets/T-0011/direction.md:3`, `.work/tickets/T-0012/direction.md:3`). This ticket's own split follows it (`.work/tickets/T-0052/spec.pre-split.md`).
- Measured on the pre-split T-0004 spec: 12 acceptance checks and 18 Touch entries, 10 of them outside bookkeeping (CHANGELOG, marketplace and plugin manifests, PLUGINS.md, README, CONFIG.md, verify.json, TODO, docs). Its four separable groups (next/resume, mint, the approval and question policies, ship) all named `plugin/crew/hooks/scripts/crew_autopilot.py` and `plugin/crew/tests/test_crew_autopilot.py`. So a "groups of criteria that share no files" measure would have called the one real split cohesive, and every Touch entry sits in one codemap subsystem (`crew`).
- Review ledgers, measured 2026-09-26 at `$(git rev-parse --git-common-dir)/crew/review/T-*.json` (19 ledgers with a spec and plan; `ledger_path` is `plugin/crew/hooks/scripts/review_ledger.py:127-128`), against each ticket's current spec.md and plan.md. Pearson r with total BLOCK+FIX findings: plan steps 0.73, acceptance checks 0.55, Touch outside bookkeeping 0.46, all Touch 0.43. With rounds: plan steps 0.55, acceptance checks 0.44, all Touch 0.24. The two heaviest tickets are T-0005 (10 steps, 10 checks, 24 Touch: 8 rounds, 44 findings) and T-0030 (9 steps, 13 checks, 13 Touch: 6 rounds, 33 findings). No ticket with 8 steps or fewer went past 4 rounds or 26 findings. The largest Touch, T-0004 after the split (30 entries, 8 steps, 10 checks), was accepted in 2 rounds, while T-0003 (9 entries) took 4. T-0028 took 4 rounds (7 steps, 9 checks).
- T-0019 (spec-only): `crew_ticket.mint(root, title, risk, status="ready", direction=None)` returns `{"ticket", "folder", "row"}`, and writes the direction before the row, or nothing (`.work/tickets/T-0019/spec.md` Acceptance 1-3).
- T-0037 (spec-only): `cancelled` and `superseded` become closed words that stale an approval on purpose (`.work/tickets/T-0037/spec.md:9` and `:30`). `STATUS_VALUES` is `plugin/crew/hooks/scripts/crew_ticket.py:143` on main.
- Owner-only commands use `disable-model-invocation: true` (`plugin/crew/commands/approve.md:5`).
- The human-turn record: the UserPromptSubmit context hook stores the prompt's `prompt_id` as the session's `turn.id` (`plugin/crew/hooks/scripts/crew_context.py:775`), in a per-session state file (`crew_context.py:222-224`). `crew_autopilot.py` on main is read-only and keeps no per-session run record (`plugin/crew/hooks/scripts/crew_autopilot.py:1-12`).
- Sabotage registration: `plugin/crew/tests/sabotage.py:3047-3049`, a file at `.pylintrc`'s max-module-lines (`:3045-3046`), so new mutations go in a sibling module.
## Unknowns
- **Thresholds, with the evidence each rests on.** They trigger a look, never a split. A split still needs `separable-criteria` evidence.
  - `PLAN_STEPS_LOOK = 9` (after plan): the two tickets over 4 rounds and over 30 findings had 9 and 10 steps. No ticket with 8 or fewer steps passed 4 rounds or 26 findings. r = 0.73 with findings.
  - `ACCEPTANCE_LOOK = 12` (after spec): the one real split (T-0004 pre-split) had 12, and T-0030 had 13. It misses T-0005 (10 checks), which the step count catches. Known cost: the pre-split T-0052 (14), T-0051, T-0012 and T-0019 each have 12 or more, so each would be asked, and "not too big" or "slices" is then a valid answer.
  - Subsystems in Touch > 1 (codemap files matched): kept from `split.md:48` so both callers use one rule. It did not detect the one measured split (a single subsystem).
  - The repo findings rate > `HEALTHY_HIGH` and `ticketsTooLarge`: kept from `split.md:46-47` as repo-wide reasons to look, never as a verdict on one ticket.
  - Touch count: reported, with no threshold. r = 0.24 with rounds, and the largest Touch was accepted in 2 rounds.
  - Caveats, stated rather than hidden: 19 tickets, one author and one reviewer family for most rounds. The specs and plans were read as they are now, some amended after review. The budget was changed during this history, so round counts include successor replans. Re-measure when 10 more ledgers exist, and record it in the constants' comments.
- **`/crew:split` stays model-invocable. Decided (standing authorization, 2026-09-26).** The pre-split plan made it owner-only (`disable-model-invocation: true`, as `approve.md:5`) so that no session could run the command and answer its own confirmation. The owner has asked for fewer interruptions, so asking the model to split a ticket keeps working, and the guard moves onto the confirmation step itself. `crew_split.py check`, when it passes, records the proposal's sha256 and the session's current human-turn id (the hook-written `turn.id` above) at `<common>/crew/tickets/<id>/split-check.json`. `crew_split.py confirm` exits 0 only when that record exists, the proposal is unchanged since, and the current turn id is readable and different: a human prompt has arrived since the check. It refuses when invoked by autopilot, because autopilot runs its phases with no human prompt in between, so its turn id at confirm is the one recorded at check. It refuses with no human turn, and when the turn record is absent, unreadable or cannot be tied to the session: could-not-tell is a refusal, never a yes. `apply --via command` calls it; the Jira path runs it after the owner's answer and before the first create call. The split.md prose also stops under `/crew:autopilot` and names T-0058's path. Known limit, accepted: a human prompt that is not a yes (for example "keep going" typed mid-run) passes the code gate, and the prose confirmation is what reads it. If step 3 finds no hook-written turn record that `crew_split.py` can tie to the calling session, it stops and reports, rather than falling back to owner-only or trusting the model's word.
- **The parent's status after a split.** T-0037's `superseded`, with `split-into: <ids>` on its own line under the spec header. If T-0037 has not merged when this ticket is implemented, step 3 stops rather than inventing a status.
- **SDP.** Decided per the recommendation: stop ("SDP is a service desk, not where this work gets decomposed").
- **Obsidian mode.** Children are minted like files mode (`mint` writes the folder and the INDEX row). The board cards are not written here. The report names `/crew:obsidian-sync` as the next step, because `mint` does not write cards and changing it is T-0019's scope.
- **T-0019's `mint` stays a dependency of this ticket. Decided (standing authorization, 2026-09-26).** `/crew:split` in files and Obsidian mode creates the children, and `mint` is the only ticket writer this ticket may call (the no-change-to-mint exclusion). Moving `apply --via command` to T-0058 would leave `/crew:split`'s files mode unable to finish a split it confirmed. T-0011 and T-0012 are no longer dependencies: nothing here ships PRs or reads `split_policy`.
- **Depends on two unmerged tickets.** Every T-0019 and T-0037 anchor above is re-read on main before step 1.
- Codex is out until 2026-10-01, so the review may be same-family. Accepted as risk and announced.
## Touch
- `plugin/crew/hooks/scripts/crew_split.py`
- `plugin/crew/commands/split.md`
- `plugin/crew/tests/test_crew_split.py`
- `plugin/crew/tests/split_fixtures/t0004_spec_pre_split.md`
- `plugin/crew/tests/sabotage_split.py`
- `plugin/crew/tests/sabotage.py`
- `plugin/crew/README.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `.crew/verify.json`
- `CHANGELOG.md`
## Acceptance checks
- [ ] `crew_split.py` holds the rulebook: `measure(top, ticket)` returns `{plan_steps, acceptance, touch, subsystems, findings_rate, tickets_too_large}`, with `None` for anything unreadable and never 0. `triggers(measures, stage)` returns the fired names for `spec` or `plan`, and an unreadable measure is reported as `unknown`, never as "not fired" (tests in `test_crew_split.py`)
- [ ] `check_proposal(parent_criteria, text)` accepts a `split.md` only when its `decision:` is `split`, `slices` or `not-too-big`, and `## Evidence` names at least one known evidence key. For `split` it also requires 2-5 children, each with a title, a `risk:` in `low|med|high`, a subsystem, at least one criterion and at least one exclusion; every parent criterion placed verbatim exactly once across the children and `## Stays on parent`; and a `separable-criteria` evidence line. Anything else is refused with a reason naming the unplaced or duplicated criterion (tests)
- [ ] rulebook must-block: a proposal with 1 or 6 children, a paraphrased criterion, a dropped criterion, one criterion placed twice, a child with no exclusions, `split` without `separable-criteria`, evidence naming only an unknown key, and an unreadable parent spec are each refused. Must-allow: `not-too-big` with evidence and no children, and the T-0004 pre-split spec split three ways as T-0010/T-0011/T-0012 were (a fixture built from `spec.pre-split.md`) (tests)
- [ ] `/crew:split`: the "Jira only" precondition becomes a tracker switch. `jira` keeps today's steps 1-6, runs `crew_split.py check` on the proposal before the confirmation, and runs `crew_split.py confirm` after the owner's answer and before the first create call. `files` and `obsidian` write `.work/tickets/<id>/split.md`, run `crew_split.py check`, ask one confirmation, then run `crew_split.py apply --ticket <id> --via command`. `sdp` stops. The frontmatter stays model-invocable (no `disable-model-invocation`). `confirm`, and `apply --via command` through it, refuses unless a human prompt has arrived since `check` passed on an unchanged proposal, and refuses when the turn record is absent or unreadable. The evidence table and the 2-5 rule stay in the prose only as a pointer to `crew_split.py` (`validate-prompts.py`, verify rule 11; text tests and confirm must-block/must-allow tests in `test_crew_split.py`)
- [ ] `apply(top, ticket, via)` in files and Obsidian mode: writes `spec.pre-split.md` byte-identical to the parent's spec.md; mints each child through `crew_ticket.mint(top, title, risk, status="ready", direction=<body pointing to the parent, its pre-split spec and split.md, with the child's criteria and exclusions verbatim>)`; then sets the parent's spec header and INDEX status to `superseded` with a `split-into:` line. A mint that raises part-way stops, names the minted and unminted children, and leaves the parent's status unchanged. It refuses in `jira` and `sdp` mode, on a `via` other than `command` (T-0058 adds `autopilot`), and on a proposal `check_proposal` refuses (tests)
- [ ] sabotage `sabotage_split.py`, registered in `sabotage.py`, one mutation per refusing branch here, each red on a named test: child count bounds widened; the verbatim-placement check made a substring check; duplicate placement allowed; the exclusions check removed; `separable-criteria` not required; an unknown measure read as 0; the sdp stop removed from `apply`; mint before `spec.pre-split.md` is written; the parent status set before every mint returned; the confirm turn check removed. `SPLIT_MUTATIONS` is a list T-0058 and T-0059 append to. A run shows each one red
- [ ] `.crew/verify.json` maps `crew_split.py` and `test_crew_split.py`. README documents the rulebook, the thresholds and their evidence, `/crew:split`'s tracker behaviour (files/Obsidian mint and `superseded`, Jira unchanged, SDP stop) and its confirmation gate. The crew version is one patch past main at merge, in `plugin.json`, `marketplace.json` and PLUGINS.md, with a CHANGELOG entry naming `/crew:split`'s files/Obsidian support and that its confirmation refuses without a new human turn. `python3 scripts/check-marketplace.py` passes
## Split
Every pre-split acceptance check (A1-A14) and plan step (S1-S10) from `.work/tickets/T-0052/spec.pre-split.md` and `plan.pre-split.md`, and where it went. "Verbatim" means the text moved unchanged; a part is named where one item was divided.

| Pre-split | Went to | Note |
|---|---|---|
| A1 measure and triggers | T-0052 acceptance 1 | verbatim |
| A2 check_proposal | T-0052 acceptance 2 | verbatim |
| A3 rulebook must-block/must-allow | T-0052 acceptance 3 | verbatim |
| A4 /crew:split tracker switch | T-0052 acceptance 4 | amended: model-invocable with the confirm gate, not `disable-model-invocation` |
| A5 apply in files/Obsidian mode | T-0052 acceptance 5 | amended: refuses a `via` other than `command` until T-0058 |
| A6 apply --via autopilot and ticket_split_policy | T-0058 acceptance 1 | verbatim |
| A7 next_phase split-check/split-approval | T-0058 acceptance 2 | amended: the `slices` continuation when T-0059 is absent |
| A8 crew_autopilot.py split subcommand | T-0058 acceptance 3 | verbatim |
| A9 PR slices parse and validate | T-0059 acceptance 1 | verbatim |
| A10 slices run in order, per-slice budget | T-0059 acceptance 2 | verbatim |
| A11 T-0011 ship per slice | T-0059 acceptance 3 | verbatim |
| A12 autopilot.md split-check/split-approval | T-0058 acceptance 4 | verbatim |
| A13 part 1: mutations 1-6, 8, 10, 11 (bounds, substring, duplicate, exclusions, separable, None as 0, sdp stop, mint order, parent-status order) | T-0052 acceptance 6 | plus a new mutation for the confirm gate |
| A13 part 2: mutations 7, 9 (jira refusal in ticket_split_policy, policy re-ask) | T-0058 acceptance 5 | the jira mutation's test calls the policy directly |
| A13 part 3: mutations 12-15 (Base: main overlap, contiguity, slice order, _spent slice rows) | T-0059 acceptance 4 | verbatim |
| A14 part 1: verify.json for crew_split, README rulebook/thresholds/tracker, version, CHANGELOG | T-0052 acceptance 7 | CHANGELOG names the confirm gate, not owner-only |
| A14 part 2: verify.json, README, version for autopilot's check | T-0058 acceptance 6 | per-ticket bump |
| A14 part 3: verify.json, README, version for PR slices and per-slice budget | T-0059 acceptance 5 | per-ticket bump |
| S1 measures and triggers | T-0052 step 1 | SLICES_MIN/SLICES_MAX moved to T-0059 step 1 |
| S2 proposal check | T-0052 step 2 | verbatim |
| S3 part 1: tracker_mode, apply via command, CLI, apply tests | T-0052 step 3 | plus the confirm gate |
| S3 part 2: ticket_split_policy, via autopilot, policy tests | T-0058 step 1 | |
| S4 /crew:split in every tracker | T-0052 step 4 | amended frontmatter and confirm call |
| S5 autopilot size check, split subcommand, report | T-0058 step 2 | amended `slices` fallback |
| S6 ## PR slices plan section | T-0059 step 1 | plus SLICES_MIN/SLICES_MAX |
| S7 slices run in order | T-0059 step 2 | verbatim |
| S8 ship per slice | T-0059 step 3 | verbatim |
| S9 part 1: sabotage module, registration, group A mutations | T-0052 step 5 | |
| S9 part 2: group B mutations | T-0058 step 3 | |
| S9 part 3: group C mutations | T-0059 step 4 | |
| S10 part 1: verify map, docs, version for group A | T-0052 step 6 | |
| S10 part 2: the same for group B | T-0058 step 4 | |
| S10 part 3: the same for group C | T-0059 step 5 | |
