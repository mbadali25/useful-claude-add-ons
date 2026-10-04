# T-0037 direction

**Reconstructed in a cloud session on 2026-10-04 from downstream tickets because the owner's `.work` copy was never published; the owner must approve direction and plan before build.** Every decision below that the owner may have made differently is marked `OWNER CHECK:`.

## Ask
The original ask is not published. Reconstructed from what five downstream tickets need from T-0037:
- T-0052 needs a word for a ticket that was split, and asked: "T-0037 adds statuses; `split` or `cancelled` with a pointer to the children? Settle it with T-0037 rather than adding a status here" (`origin/T-0052-build:docs/tickets/T-0052/direction.md:81-82`). Its spec then settled it: "The parent becomes `superseded`, T-0037's word" (`spec.md:12`).
- T-0052, T-0058 and T-0059 cite T-0037's spec for "`cancelled` and `superseded` become closed words that stale an approval on purpose" (`origin/T-0052-build:docs/tickets/T-0052/spec.md:27`).
- T-0059 needs "the status vocabulary and which header edits stale an approval", because `/crew:done` on a non-final slice writes `in-progress` and must not stale the approval (`origin/T-0059-build:docs/tickets/T-0059/spec.md:18`, `:23`).
- T-0039 and T-0040 need a `needs-owner` status: "a proposal that needs the owner becomes a `needs-owner` item once T-0037 lands" (`origin/T-0039-build:docs/tickets/T-0039/direction.md:51`), and "The needs-owner status belongs to T-0037" (`origin/offload/win-repo-2-tickets:offload/T-0040/spec.md:15`).

So T-0037 is crew's ticket status vocabulary: add `needs-owner`, `cancelled` and `superseded`, and make every reader and every tracker treat them the same way.

## What investigation found (origin/main edb2b8ff, crew 1.0.321)
- **The status words are spread across five lists, with no single owner.**
  - `crew_ticket.STATUS_VALUES` (`plugin/crew/hooks/scripts/crew_ticket.py:163`) is the approval digest's list. A header edit between these values keeps the approval; any other value stales it (`_canonical`, `:550-576`).
  - `crew_tracker.STATUS_ORDER` / `LANE_FOR_STATUS` (`crew_tracker.py:91-100`) are the moves a tracker accepts. A status absent from the table "maps to no lane and is refused with nothing written" (`:1489-1490`).
  - `crew_state._TABLE_DONE_WORDS` and `_DONE_RE` (`crew_state.py:218-221`, `:238-240`) decide what is closed for `read_work`, the session brief and `resolve_active`'s INDEX fallback. `crew_ticket._index_closed` reuses them, so approval `precheck` refuses a closed ticket (`crew_ticket.py:831-872`, `:898-902`).
  - `crew_autopilot.INDEX_DONE` and `DIRECTION_APPROVED` (`crew_autopilot.py:181-183`). `_phase` closes on these INDEX words (`:433-435`) and on a spec header of exactly `done` (`:442-446`, again in `_closed` `:1442-1456`).
  - `crew_status._ticket_lines` lists only `open`, `in-progress`, `in progress` and `review` rows as open (`crew_status.py:116`).
- **Nothing on main knows `needs-owner`, `cancelled` or `superseded` as a ticket status.** Today a `cancelled` INDEX row reads as OPEN to `read_work`, so the session brief can name a cancelled ticket as the current one. Autopilot stops on it as "cannot tell whether direction is approved". `crew_tracker.py move --to cancelled` refuses with "maps to no lane".
- **The approval rule already does what downstream asks for closed words.** `cancelled` and `superseded` are not in `STATUS_VALUES`, so a header edit to either already stales the approval. T-0037 keeps that on purpose and writes it down, with tests.
- **T-0019 has landed** (`mint`, #379, `crew_ticket.py:1355`). `MINT_STATUSES` is `("ready", "direction")` (`:1048`).
- **Harness boundary.** `crew_ticket.py` and every `plugin/crew/tests/sabotage*.py` are `HARNESS` in `scripts/check-tooling-pr.py:58-84`. `crew_state.py` and `crew_tracker.py` are not, and are not `ALONGSIDE` either. One PR cannot carry both, so this ticket lands as two PRs (plan).

## Options
1. **Three words, owned by `crew_tracker.py`; the approval list stays as it is (recommended).** `crew_tracker.py` already says "a new status is a row here, not a branch in the code" (`:86-90`). Add `needs-owner` (open, off the linear order) and `cancelled` and `superseded` (closed and terminal). Each reader's closed list gains the two closed words. `STATUS_VALUES` is unchanged, so the digest is byte-identical and a blocking hook accepts nothing new.
2. **Also add the new words to `STATUS_VALUES`.** Rejected. That would make a `superseded` header keep the approval, which is the opposite of "stale an approval on purpose". It would also loosen what a blocking hook accepts.
3. **One `split` status, as T-0052's direction first asked.** Rejected. T-0052's own spec settled on `superseded` with a `split-into:` line, and `superseded` also covers a ticket replaced by one other ticket.

## Recommendation
Option 1.
- **`needs-owner`** is an INDEX/tracker status only, never a spec header word. It means the ticket is open and waiting on the owner. Autopilot stops on it, `/crew:status` lists it on its own line, and `read_work` still counts it as open.
  - OWNER CHECK: INDEX-only, with no header word. A header word would have to join `STATUS_VALUES`, which is a harness change.
  - OWNER CHECK: the question for the owner lives under the ticket's existing `## Open questions`, which autopilot already reads (`crew_autopilot.py:447-451`). No new field is added.
- **`cancelled`** closes a ticket that will not be done. **`superseded`** closes a ticket that other tickets replace. It carries `split-into: <id>, <id>` (T-0052) or `superseded-by: <id>` on its own line under the spec header. Both words close the ticket in every reader. Moving a ticket back out of either needs `--reopen`.
- **Approval:** `STATUS_VALUES` keeps its seven values. `in-progress` keeps the approval (T-0059), and `cancelled`/`superseded` in a header stale it on purpose. OWNER CHECK: downstream T-0059 says T-0037 "redefines `STATUS_VALUES`". This direction keeps its value and name, and documents it as the approval-keeping subset, because T-0052 and T-0059 cite the constant by name.
- **Trackers:**
  - Obsidian: `needs-owner` goes to the `backlog` lane. OWNER CHECK: `cancelled` and `superseded` go to the `done` lane, checked, because no `obsidian.columns` key exists for a closed lane and adding one is a config-key change.
  - Jira and SDP: none of the three is pushed. They stay boundary-only (`_PUSH_AT`, `crew_tracker.py:115`), and the tracker line says "nothing to push". OWNER CHECK: the owner closes a cancelled Jira or SDP item by hand.
- **No new command.** A ticket is cancelled with `crew_tracker.py move --to cancelled` (the INDEX alone closes it). T-0052 writes `superseded` from its own `apply`. OWNER CHECK: there is no `/crew:cancel`.

## Boundaries
- No new spec header word in `STATUS_VALUES`, and no change to `approval_digest`.
- `mint` is unchanged (`MINT_STATUSES` stays `ready|direction`). T-0039 and T-0040 mint `ready`, then move to `needs-owner`.
- `/crew:split`, `crew_split.py` and the `split-into:` writer belong to T-0052. `done.md`'s slice edit belongs to T-0059.
- No hook is added or registered.
