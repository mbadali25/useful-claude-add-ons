# L-0530 direction - crew_tracker maps INDEX statuses merged, approved and new (and land-blocked) to lanes

Status: approved 2026-10-05 for cloud hand-off, RESHAPED (see Recommendation). Original seed text kept below. Filed by owner decision 2026-09-30 ("File as L-0530"), after a /crew:obsidian-sync pull over every ticket.

Evidence (crew 1.0.75): `crew_tracker.py read` reports `INDEX status merged expects None` for 52 tickets, because `LANE_FOR_STATUS` only knows direction/ready/spec/planned/in-progress/review/done. The statuses used in practice are `merged` (26 tickets, board Done), `approved` (~23, board Ready) and `new` (3, board Backlog), plus `land-blocked`, which the handoff noted and offered earlier as T-0507, never answered. For those tickets the sync check cannot tell whether board and INDEX agree, and `move --to merged` is refused.

Scope: add merged -> done (checked, below **Complete**), approved -> ready, new -> backlog, and a decided lane for land-blocked (recommend review). Keep the refusal for any unknown status. Update the copy of the table in commands/obsidian-sync.md, the other tracker docs (sdp-sync/jira-sync if they map statuses) and tests, and add a sabotage entry that drops a mapping. Version bump and docs per repo rules.

Same pull, 6 lane disagreements pushed INDEX-to-board by owner decision ("INDEX wins"): T-0029, T-0028, T-0049, T-0086 -> In Progress; T-0094 -> Review; L-0520 -> Backlog (INDEX ready).

## Ask
The seed asked `crew_tracker` to map the INDEX words `merged`, `approved`, `new` and `land-blocked` to board
lanes, so `read` stops saying `INDEX status merged expects None` and `move --to merged` works.

Two things changed since the seed (2026-09-30):
- **Owner rule, 2026-10-05:** INDEX statuses are crew-known only - `direction`, `ready`, `needs-owner`, `spec`,
  `planned`, `in-progress`, `review`, `done`, `cancelled`, `superseded` - never `approved`, `merged`, `closed`,
  `new` or `parked`. The same day crew-chat rewrote the foreign cells at the owner's request (approved -> spec,
  closed -> done, new -> direction, parked -> needs-owner). Teaching the tracker the foreign words is therefore
  the opposite of the rule.
- **T-0037 (#394)** added `needs-owner`, `cancelled`, `superseded` as table rows, and made a move FROM an unknown
  word refuse with "could not tell whether X -> Y goes backwards ... pass --reopen"
  (`plugin/crew/hooks/scripts/crew_tracker.py:677-679` at `a555ff37`).

Measured 2026-10-05 in the main checkout's `.work/INDEX.md` (read-only): 344 rows, every status crew-known
(done 133, direction 107, spec 87, in-progress 13, review 1, ready 1, planned 1, needs-owner 1). The seed's 52
foreign rows are gone. What is left: `read` still reports a foreign word as a disagreement with lane `None`
(`crew_tracker.py:1526-1528`), which reads as a sync fault rather than the real problem (a bad INDEX cell), and
nothing names the crew word that replaces it, so the next hand-written foreign word costs the same diagnosis.

## Options
1. **Name, don't map (recommended).** Leave `LANE_FOR_STATUS` and every refusal as they are. `read` reports an
   INDEX status crew does not know as `disagree: "could not tell"` with the note `INDEX status <s> is not a
   status crew knows (<list>)`, plus `; the crew word is <w>` for the five retired words the owner's rule names
   (approved -> spec, merged -> done, closed -> done, new -> direction, parked -> needs-owner). `move` FROM such a
   word adds the same hint to its existing refusal. A hint is text only: never a write, never a lane.
2. **Map the words (the seed).** Rejected: contradicts the 2026-10-05 owner rule, and every reader held to the
   vocabulary by `test_status_vocabulary.py` would have to learn five more words.
3. **Close as superseded.** The data is already clean, so nothing is broken today. Rejected as the default:
   the `expects None` line is still wrong (an unknown collapsing into a disagreement), and the cost recurs on
   the next hand edit. Cheap enough to fix.

## Recommendation
Option 1. Retitled: **crew_tracker names an INDEX status crew does not know (and the crew word for a retired
one) instead of reporting `expects None`.** `land-blocked` gets no hint: no owner decision maps it, so it reads
as not crew-known only (the seed's "recommend review" is not adopted; guessing a lane is what the rule forbids).

## Open questions (default taken)
- `disagree` for an unknown INDEX status: the module's `COULD_NOT_TELL` string, not `True`. Default taken
  (CLAUDE.md lesson: an unknown must not collapse into the safe-looking value).
- Hint table name and home: `RETIRED_STATUSES` in `crew_tracker.py` beside `LANE_FOR_STATUS`, held disjoint from
  it by a test. Default taken.
- Sabotage entry (seed asked for one): `plugin/crew/tests/sabotage*.py` is a harness path, so it lands as a
  separate tooling-only follow-up, not in this PR. Default taken; the follow-up id is minted by the orchestrator.
- jira-sync / sdp-sync: neither maps INDEX words to lanes (they push only at `in-progress`/`done`), so no edit.

Approved 2026-10-05 for cloud hand-off by the orchestrator under the owner's standing self-approve authority.
