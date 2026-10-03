# L-0582 direction - read_metrics and every .crew/metrics.md reader resolve the MAIN checkout's .crew/ when run from a linked worktree

Status: approved (2026-10-02, workflow brainstorm phase under the owner's standing authority:
"between the 2 crew sessions lets get them done", Matthew Badali 2026-10-02, relayed by
crew-chat). Open questions below were settled by recorded owner answers where they exist and by
the written recommendation otherwise; each says which.

Owner decision 2026-10-01 (relayed by crew-chat from its AskUserQuestion on L-0578): file this follow-up.

## Ask

Problem: lane review rows were written to each linked worktree's own gitignored `.crew/metrics.md`
instead of the main checkout's, so they are invisible to `read_metrics`. That is half of the
162-vs-73 gap between review rounds run and rows recorded. Evidence:
/repos/personal/uca-l0578/.work/tickets/L-0578/notes.md.

Ask (verbatim from the seed): `read_metrics`, and every other reader and writer of
`.crew/metrics.md` (grep for every caller), resolves the main worktree's `.crew/` through
`git rev-parse --git-common-dir` when run from a linked worktree, and says when it could not tell
rather than falling back silently to the local copy. Tests: a must-find from a linked worktree, a
must-find from the main checkout, and a could-not-tell outside git. Plus a sabotage row (revert to
the local `.crew/` and the linked-worktree test goes red).

## Callers found (origin/main 8d84786d, crew 1.0.115)

Code that opens `.crew/metrics.md` by joining it to `root`:
- `plugin/crew/hooks/scripts/crew_state.py:314` - `read_metrics` (reader; feeds `/crew:status` health and `/crew:split`).
- `plugin/crew/hooks/scripts/crew_standards.py:831` - `metric` (reader, and with `--record` an append writer).
- `plugin/crew/hooks/scripts/crew_status.py:180` - `_metrics_line` (reader; loops over `metrics.jsonl` then `metrics.md`).
- `plugin/crew/hooks/scripts/crew_migrate.py:507` - `/crew:migrate` source read (one-time 0.20 -> 1.0 move).
- Prose writer: `plugin/crew/commands/review.md:527` step 6 ("Append the result to `.crew/metrics.md`").
- In flight, not on main: L-0578's `plugin/crew/hooks/scripts/review_metrics.py` (`metrics_path(root)` -> `(path, problem)`, built on `crew_common._main_checkout`; writes nothing when the main checkout cannot be named). L-0578 is crew 1.0.119, branch `L-0578-build`, not merged as of this phase.

The tri-state resolver already exists on main: `plugin/crew/hooks/scripts/crew_common.py:129`
`_main_checkout(root)` -> `(main_root | None, problem)`, using `git rev-parse --git-dir --git-common-dir`
(T-0088, repo config inheritance).

## Options

1. **(recommended) One shared resolver in `crew_common`, every caller routed through it.**
   A public `crew_common.metrics_md_path(root)` -> `(path, problem)` built on `_main_checkout`:
   a linked worktree gets `<main checkout>/.crew/metrics.md`; a plain checkout, submodule or bare
   common dir gets `root`'s own; a git that cannot answer returns `problem` and no path. Each
   caller turns `problem` into its own visible could-not-tell output. Tradeoff: touches four
   scripts plus docs in one PR, but there is exactly one place the rule lives, and L-0578's
   `review_metrics.metrics_path` can delegate to it rather than being a second copy.
2. **Patch each caller in place** with its own `rev-parse` call. Tradeoff: smallest diff per
   file, but four copies of the same resolution logic, which is how the local fallback crept in
   the first time.
3. **Readers union main and local copies.** Tradeoff: recovers stranded rows on read, but it
   double-counts once L-0583 backfills them, and pooling two files hides which one is
   authoritative - the unknown-collapsing-into-a-value bug this repo keeps paying for.

## Recommendation

Option 1. It reuses the resolver T-0088 already proved and L-0578 already adopted, keeps the
could-not-tell value as its own state, and leaves backfill to L-0583, which depends on this
ticket deciding the target.

## Open questions (settled)

1. **Which callers are in scope?** - *Recommendation (standing authority).* `read_metrics`,
   `crew_standards.metric` (read and `--record` write), and `crew_status._metrics_line`, plus the
   `review.md` step 6 prose so a hand-appended row names the main checkout's file.
   `crew_status._metrics_line` resolves both of its names (`metrics.jsonl` and `metrics.md`)
   through the same main-checkout `.crew/`, since it is one loop and splitting it would leave the
   jsonl branch reading the lane copy while the md branch reads main's.
   **Out of scope:** `crew_metrics.py`'s own `metrics.jsonl` writer (`metrics_path` at
   `plugin/crew/hooks/scripts/crew_metrics.py:138`) and `crew_migrate.py` (a one-time migration
   that runs against the checkout it is pointed at). The spec records the jsonl writer as a
   candidate follow-up rather than widening this ticket.
2. **How does this relate to L-0578, which also changes review_metrics?** - *Owner's recorded
   instruction (workflow task): "check origin/main for it first and build on what landed".* L-0578
   has not landed (origin/main 8d84786d has no `review_metrics.py`). So: the spec phase re-checks
   origin/main. If L-0578 has landed, this ticket makes `review_metrics.metrics_path` delegate to
   the shared resolver and covers it with the same tests. If it has not, this ticket builds only
   on `crew_common._main_checkout` (already on main) and does not touch `review_metrics.py`; the
   merge with L-0578 is then a reconciliation of one function, flagged in the spec as a known
   merge point.
3. **What does could-not-tell look like?** - *Recommendation (standing authority), matching
   L-0578's writer.* No caller falls back to the local `.crew/` when `problem` is set.
   `read_metrics` returns a distinct verdict (`could not tell: <problem>`, `rate` None), never
   `no data`; `/crew:status` prints `metrics  could not tell (<problem>)`; `crew_standards metric`
   exits 1 with the reason and, under `--record`, writes nothing. A missing file at a resolved
   path stays `no data` / `absent` as today.
4. **What about rows already stranded in a lane's own `.crew/metrics.md`?** - *Recommendation
   (standing authority).* Not read, not merged, not moved by this ticket (Option 3's
   double-count). Recovering them is L-0583's backfill. `/crew:status` from a linked worktree
   whose own `.crew/metrics.md` exists adds one line naming it as not counted, so the stranded
   copy is visible rather than silently ignored.
5. **Tests and sabotage.** - *Owner's seed (recorded).* Must-find from a linked worktree (a real
   `git worktree add` fixture whose main checkout holds the row and whose own `.crew/` holds a
   decoy), must-find from the main checkout, could-not-tell outside git or with git unable to
   answer, applied to every in-scope reader; sabotage: point the resolver back at `root/.crew`
   and the linked-worktree tests go red. Fixtures are throwaway temp repos, per CLAUDE.md.
6. **Path.** - *Recommendation.* Full lifecycle, not `/crew:fix`: several callers across the
   status, standards and state scripts, plus a new could-not-tell behaviour. Docs that describe
   these readers (`plugin/crew/commands/review.md`, `status.md`, `split.md`, the crew README /
   guides where they name `.crew/metrics.md`) are on the spec's Touch list per the 2026-09-26
   owner rule. A content change bumps crew's version at implement time (next free number).

Related: L-0578, L-0583 (depends on this ticket).
