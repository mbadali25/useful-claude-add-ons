# T-0058 autopilot size check after spec and after plan, and /crew:autopilot split: children through the rulebook and T-0019's mint, Jira always the owner's yes (2 of 3; depends on T-0052, T-0012, T-0019)          status: spec   risk: high
depends-on: T-0052, T-0012, T-0019
## Intent
Autopilot's `next` runs T-0052's size check once after spec and once after plan. When a measured trigger fires, autopilot writes a `split.md` decision through the rulebook, with one of three outcomes. **split**: approved under T-0012's split rule, where the owner's yes is always required in Jira mode; children are minted with T-0019's `mint` in files/Obsidian mode through T-0052's `apply --via autopilot`; the parent's text is kept as `spec.pre-split.md`; and the parent becomes T-0037's `superseded`. **slices**: recorded, and the run continues into a plan whose `## PR slices` section T-0059 validates and ships. **not-too-big**: said, recorded, and the run continues. `/crew:autopilot split <id>` runs the same check on demand.
## Exclusions
- Split from T-0052 (decided 2026-09-26, standing authorization). The rulebook, `/crew:split` in every tracker and `apply --via command` are T-0052's. The `## PR slices` section, running slices and shipping them are T-0059's.
- No mid-implement split and no re-slicing of a finished diff. The check runs after spec and after plan only.
- Autopilot never creates a Jira issue. In Jira mode a split always stops for the owner, who runs `/crew:split <KEY>`, whatever `autopilot.approval` says.
- No SDP split. SDP mode stops, naming the reason.
- No change to `crew_ticket.mint`'s contract (T-0019) or `split_policy`'s rule (T-0012). This ticket calls them.
- No approval grammar in the UserPromptSubmit hook. A `split:<id>` hook receipt, like T-0012's `goal:<slug>`, is a follow-up that needs the owner's explicit yes, because it extends a blocking hook.
- Autopilot never runs `/crew:split`. Its split path is `crew_autopilot.py split --apply`, under the policy.
- Autopilot does not re-open a parent's children as one run. Each child is its own ticket and is driven by its own `run`, or by T-0012's backlog.
## Evidence
Anchors are on origin/main 1e0706ac (crew 1.0.41) unless marked. Spec-only anchors are in `.work/tickets/<id>/spec.md` or `plan.md`, for tickets that have no branch yet (T-0012, T-0019, T-0037, T-0052).
- T-0052 (spec-only): `crew_split.measure`, `triggers(m, stage)` (with `unknown:<name>` for an unreadable measure), `check_proposal`, the `split.md` format and `apply(top, ticket, via)` accepting only `command` (`.work/tickets/T-0052/spec.md` Acceptance 1-5; `.work/tickets/T-0052/plan.md` steps 1-3). `SPLIT_MUTATIONS` in `plugin/crew/tests/sabotage_split.py` is the list this ticket appends to (T-0052 step 5).
- Autopilot's size-check points on main: the spec validation stop is `plugin/crew/hooks/scripts/crew_autopilot.py:358-364`, the plan validation stop is `:365-371`, and the approval stop is `:372-384` (`next_phase` `:451`). `done` closes a ticket on the spec header `status: done` (`:349-352`, set by `plugin/crew/commands/done.md:61`).
- T-0012 (spec-only): `split_policy(root, slug)` returns `{allow, policy, risk, known, reason, warnings}`. It refuses without `scope.allowCliApproval` or when unarmed, refuses under `human`, allows under `self`, and under `risk` allows only an all-`low` known risk. It is re-asked on every read (`.work/tickets/T-0012/spec.md:77`; `.work/tickets/T-0012/plan.md:23-24`). It is keyed to a goal slug.
- T-0019 (spec-only): `crew_ticket.mint(root, title, risk, status="ready", direction=None)` returns `{"ticket", "folder", "row"}`, and writes the direction before the row, or nothing (`.work/tickets/T-0019/spec.md` Acceptance 1-3).
- T-0037 (spec-only, reached through T-0052): `superseded` becomes a closed word (`.work/tickets/T-0037/spec.md:9` and `:30`).
- The tracker mode is read from `.crew/crew.json`, or `.crew/config.json` on an unmigrated repo (`plugin/crew/commands/brainstorm.md:21-22`); `sdp` is a mode (`plugin/crew/hooks/scripts/crew_config.py:275`).
- `test_command_never_types_approve` is the existing guard that autopilot's prose never types an approval (`plugin/crew/tests/test_lifecycle_commands.py`).
## Unknowns
- **Unattended Jira.** Decided per the recommendation and the owner's brief (T-0052's direction): always the owner's yes in Jira mode.
- **SDP.** Decided per the recommendation: stop ("SDP is a service desk, not where this work gets decomposed").
- **`slices` before T-0059 lands.** Decided (standing authorization, 2026-09-26): a `slices` decision continues at `spec`. At `plan` it continues only when the plan's `## PR slices` section validates; when `crew_split` has no `parse_slices`, it stops as `split-check-unknown` naming T-0059, never continuing as though the slices were checked.
- **The jira sabotage's red test.** The pre-split plan named `test_apply_refuses_jira_even_under_self`, but T-0052's `apply` already refuses Jira mode, so removing the refusal from `ticket_split_policy` would leave that test green. The mutation is held by `test_policy_refuses_jira_even_under_self`, which calls `ticket_split_policy` directly.
- **T-0051 ping.** When `next` stops at `split-approval`, autopilot's report sends T-0051's `blocker` if `crew_notify.py` exists on the base. If it has not landed, the line is left out and the PR says so.
- **Depends on three unmerged tickets.** Every T-0052, T-0012 and T-0019 anchor above is re-read on main before step 1, and T-0037's `superseded` through T-0052. If `split_policy` lands without a slug-free core, step 1 factors one out (`_split_rule(cfg, risk, known)`) with T-0012's tests unchanged. T-0059 also edits `next_phase`; whichever lands second rebases onto the other.
- Codex is out until 2026-10-01, so the review may be same-family. Accepted as risk and announced.
## Touch
- `plugin/crew/hooks/scripts/crew_split.py`
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/tests/test_crew_split.py`
- `plugin/crew/tests/test_crew_autopilot_split.py`
- `plugin/crew/tests/test_crew_autopilot.py`
- `plugin/crew/tests/test_lifecycle_commands.py`
- `plugin/crew/tests/sabotage_split.py`
- `plugin/crew/README.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `.crew/verify.json`
- `CHANGELOG.md`
## Acceptance checks
- [ ] `apply --via autopilot` also requires `ticket_split_policy(top, ticket)` to allow. That applies T-0012's split rule with the parent's spec risk (unknown reads `high`), refuses in `jira` mode ("the owner runs /crew:split <KEY>") and in `sdp` mode, and is re-asked at apply time, never read from a record. `--via command` needs no policy but refuses in `sdp` (tests: must-block under `human`, under `risk` with `med`/`high`/unknown, in `jira` under `self`, without `allowCliApproval`, unarmed; must-allow under `self` and under `risk` with `low` in files mode)
- [ ] `next_phase`: after the spec validation (`crew_autopilot.py:358-364`) and after the plan validation (`:365-371`), a fired trigger with no current decision returns `split-check` (not a stop), naming `/crew:autopilot split <id>`. A `split.md` decision is current when it records the trigger set it answered, and a new trigger fired later makes it stale. `not-too-big` continues. `slices` continues after plan only when the plan's `## PR slices` validates, and stops as `split-check-unknown` naming T-0059 when `parse_slices` is absent. `split` returns `split-approval` (a stop) until applied, and `closed` once the parent is `superseded`. An `unknown` measure stops as `split-check-unknown` (tests in `test_crew_autopilot_split.py`)
- [ ] `crew_autopilot.py split --root . --ticket <id> [--check|--apply]`: bare, it prints the measures and fired triggers; `--check` validates `split.md`; `--apply` runs `apply --via autopilot`. The router lists `split` as available (tests)
- [ ] `autopilot.md`: `split-check` runs the rulebook judgement (crew:explorer for boundaries), writes `split.md` and runs `split --check`. `split-approval` under an allowing policy runs `split --apply`, otherwise it stops with `/crew:split <id>` as the last line (and T-0051's blocker when present). It never runs `/crew:split` itself (text tests; `test_command_never_types_approve` stays green)
- [ ] sabotage: two mutations appended to T-0052's `SPLIT_MUTATIONS` in `sabotage_split.py`, each red on a named test: the jira refusal removed from `ticket_split_policy`; the policy re-ask replaced by a stored answer. A run shows each one red, and T-0052's mutations stay red
- [ ] `.crew/verify.json`'s `crew_split` rule gains `test_crew_autopilot_split.py`. README documents autopilot's size check after spec and after plan, `split-check`/`split-approval`/`split-check-unknown`, the policy, and Jira always stopping for the owner. The crew version is one patch past main at merge, in `plugin.json`, `marketplace.json` and PLUGINS.md, with a CHANGELOG entry. `python3 scripts/check-marketplace.py` passes
