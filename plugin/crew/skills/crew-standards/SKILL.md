---
name: crew-standards
description: Build-time development standards mined from crew's QA reviews. Use at /crew:plan to name the standards each step triggers, at /crew:implement for the required pre-review self-check and its stamp, and at /crew:review for the reviewer's checklist and the findings-to-standards proposals.
---

# crew-standards

Standards that review keeps finding, applied the first time the code is
written instead. Each one is earned by real BLOCK/FIX findings from crew's own
reviews, cites them, and carries a self-check with the answer that passes. The
script is `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_standards.py`.

## The sets, and which apply

- **Generic** - `references/generic.md`, set `GEN`, applies to every change.
  A plugin standard needs findings from at least three distinct reviewed
  change sets; its `Change sets` line names them.
- **Stack sets** - further files in `references/` (per language, T-0086),
  each with an `applies-to` glob list; a set applies when a changed file
  matches one of its globs.
- **The repository overlay** - `.crew/standards.md`, set `REPO`, read when it
  exists. It adds standards (`## REPO-01 <name>`) and `## Supplements
  <GEN-id>` sections carrying the repository's literal commands for a plugin
  standard. It never removes, reuses or weakens a plugin standard. Track it,
  so every clone reads it.

A set file is Markdown: a `---` front matter with `set:` and `applies-to:` (a
JSON list), then one `## <ID> <name>` heading per standard with the bold
fields `**Rule.**`, `**Why.**`, `**Applies when.**`, `**Self-check.**`,
`**Earned by.**`, `**Change sets.**` and optionally `**Source.**`. The overlay
needs only Rule and Self-check.

No overlay reads as generic only, and the summary line says so. An overlay
that cannot be read, is not UTF-8 or is malformed is **could-not-tell**, never
"absent": the stamp and the review gate refuse until it is fixed.

`crew_standards.py sets --root . --ticket <id>` prints the effective set for
the ticket's change: its ids, the overlay state and the set's digest.

## At /crew:plan

Each step carries a line after `Risk:`:

    Standards: GEN-01, GEN-07     (or: none - <why>)

naming the standards the step's Files and Risk trigger (read each standard's
**Applies when.**). The plan's self-review asks whether every step names them.
Naming them at plan time is what puts the self-check's questions in front of
the person writing the code, before review asks them.

## At /crew:implement: the required self-check

After the tests, docs and refresh, before `/crew:review`:

1. `crew_standards.py init --root . --ticket <id>` writes
   `.work/tickets/<id>/selfcheck.md` with one row per standard in the
   effective set. It never overwrites an existing record.
2. Answer every row. `addressed` needs evidence: the test that covers it, a
   `mutation -> failing test` pair you ran, or the file:line that does it.
   `n/a` needs the reason the standard does not apply to this change.
   Placeholders (`TBD`, `-`, `<evidence>`) are refused.
3. `crew_standards.py stamp --root . --ticket <id>` refuses (exit 1, each
   problem named) a missing row, an unknown status, a placeholder, an unknown
   or duplicated id, or no recorded scope base. A recorded start that is gone
   or no longer an ancestor of HEAD stamps against the same merge-base
   fallback `/crew:review` bundles with, and says `(fallback)` on its output
   line; with no default branch to fall back to it refuses, and it names
   `scope_base.py --record` only when no record exists, since `--record` never
   overwrites one. On a complete record it writes
   `<!-- stamp: bundle=... standards=... base=... -->` under the header:
   the review bundle's sha256 (`review_patch.compute` on the ticket's scope
   base, so staged, unstaged and untracked content count) and the standards
   digest.

Any edit after the stamp changes the bundle, so stamp again. When a standard
fired on a fix, re-run its self-check over the fixed line's whole class, not
only the line: in crew's own reviews the next defect was the neighbour of the
last fix.

## At /crew:review: the gate, the checklist, the proposals

- **Gate.** `review_run.py` refuses to reserve a round (exit 2, nothing spent)
  when the self-check is missing, unreadable, incomplete, unstamped, or stamped
  for another bundle or another standards set. It applies to a ticket with an
  approval receipt, or whose receipt cannot be proven absent. In an active
  incident (`/crew:emergency`) it stands down and logs a `standards-selfcheck`
  skip. On a pass it prints the `std:<8 hex>` token for the metrics row.
- **Checklist.** The shared review prompt ends with the effective set's rules
  and self-check questions. The author's answers are withheld from the prompt,
  so the reviewer judges applicability itself, and the list does not bound the
  review. `selfcheck.md` itself stays readable in `.work/`; the prompt never names it.
- **Proposals.** After a round, `crew_standards.py proposals --root .
  --ticket <id> --scratch <dir> --round <N>` writes
  `.work/tickets/<id>/standards-proposals-r<N>.md`: every BLOCK/FIX line
  verbatim, each with Covered by, Self-check said and Proposal to fill. The
  owner approves or rejects each proposal. An approved one is written into
  `.crew/standards.md` by hand, or filed as a crew ticket for the plugin set.
  Nothing is added to any standards file automatically.

## The metric

`/crew:review` records its metrics row with `(r<N>, std:<first 8 of the
digest>)` in the reviewer cell, or `std:none` when the gate stood down or did
not apply. `crew_standards.py metric --root .` prints first-round BLOCK+FIX
per ticket before (no `std:` token) and after (a `std:` token), with count,
median and mean. Rows whose round cannot be read count as unknown and are on
neither side; fewer than `crew_metrics.MIN_BASELINE_KNOWN` tickets on a side
reads "not enough data". `--record` appends one summary line with no `|`, so
the existing metrics readers skip it.
