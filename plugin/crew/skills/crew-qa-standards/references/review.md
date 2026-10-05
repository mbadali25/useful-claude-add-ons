# QA review standard

How an LLM review is run so that it costs as little as it can while still finding what it
should. Crew implements R1-R8 itself (`commands/review.md`, `hooks/scripts/review_*.py`). In a
repo that runs its own review harness, hold that harness to the same rules. `qa_audit.py`
checks the rules marked **[audited]**.

## R1 — The deterministic gate goes first

No review round is spent on a tree the gate has not passed. Judge "passed" by what a full
clean pass **leaves behind** (in crew: `.crew/.verify-verified-at` at HEAD, and a fingerprint
matching the tree now), never by the gate's exit status. That status is also 0 when the gate
is stood down, backs off a lock, or has nothing to check. An override is explicit and recorded
(`--allow-unverified` → `gate.overridden` in `review.json`).

- **Why.** A reviewer's opinion on code the gate would refuse for free is the costliest way to
  learn it is red. With only a small number of rounds, it also spends one the ticket needs.

## R2 — Review the change, as one hashed bundle

The reviewer gets committed, staged, unstaged and untracked changes as one bundle. The bundle
is split into parts (never truncated), hashed, and excludes generated directories, **saying
what it excluded**. Whole-file context comes from the reviewer reading the repo, not from
pasting files into the prompt.

## R3 — Rounds are bounded and reserved before launch

A fixed budget per ticket (crew: 2), reserved before the reviewer starts, so a crash still
counts. A refused third round means replan, not retry.

## R4 — Never review an unchanged bundle twice

A bundle whose hash matches a current CLEAN receipt is not reviewed again. The verdict is that
receipt's, said as such. An owner-accepted FINDINGS receipt is a person's call about one round,
not a clean review, so it does **not** short-circuit.

## R5 — Structured output, verdict by script

One line per defect, `SEVERITY|file:line|what breaks|how to reproduce`, with severity
`BLOCK`/`FIX`/`NIT`. A script computes the verdict. Empty output, a non-zero exit, a timeout, an
unacknowledged part, or a stray line that might be a misformatted contract line or admits the
review fell short is **INCOMPLETE**, never CLEAN. Harmless stray prose or a code fence beside
well-formed findings is ignored and reported, and the round is **FINDINGS**; never recovered beside
CLEAN (L-0576). Findings are reported verbatim, BLOCK first.

## R6 — The reviewer is independent of the author

A different model family from the one that wrote the diff, and a gate reviewer is never
downgraded to a cheaper model for "triage". A weaker model does not review, it agrees, and its
agreement looks like a pass. Cheap models are fine **outside** the gate, for explaining lint
output or drafting fixes.

## R7 — Feed the reviewer the deterministic results

The contract carries the test receipts: the last clean gate pass, and every rule still listed
as not verified. The reviewer then confirms and explains instead of hunting.

## R8 — Record cost per round, then claim savings

Every round records elapsed seconds, gate state and finding counts (crew: `review.json` and
`.crew/metrics.md`). A saving is claimed from those records, not estimated.

## R9 — Keep always-loaded instructions small [audited]

`CLAUDE.md` loads into every session, reviews included. Keep rules there as one to three lines
each, and move the evidence and history into `docs/`, pointed to by name. Command prompts are
line-budgeted too (crew: `.budget-allowance.json`).

- **Evidence.** In #266, this repo's `CLAUDE.md` went from 24,614 to 10,026 chars (~6,150 →
  ~2,500 tokens a session) with no rule removed. A script confirmed every original line
  survived in `CLAUDE.md` or the evidence file.
- **Audit threshold.** 12,000 characters. A heuristic, not a law: the check reports the size and
  lets a reader decide.

## R10 — A guard that can block ships with must-block, must-allow and sabotage

Each blocking rule has a test that must block and one that must allow. Each test is proven by a
mutation that reintroduces the bug and turns the suite red. After fixing a guard, check the
neighbouring case before closing it: in this repo, the next defect was there every time it was
measured.

Code-level standard: GEN-04 (crew-standards); this rule is its process form.

## R11 — Each repo carries a steward skill for its PR loop [audited]

`.claude/skills/steward/SKILL.md` holds what an agent driving a PR to green needs in **this**
repo: gate order, which failures are environmental, merge-vs-rebase, generated-file commands.
It cites `CLAUDE.md` sections rather than copying them, and states no counts. Start from
`steward-template.md`.

## R12 — A PR reports what was measured, what ran, and what did not

Every PR body, written by a person or an agent, carries four sections:

| Section | Holds |
|---|---|
| Summary | What changed, as a table when it's more than two items |
| Measured | Each number with its ref and the machine it was measured on (a number without them can only be believed) |
| Verification | Which suites ran, with counts; which sabotage runs went red |
| Not verified | Every suite skipped, every environment not run (Windows, a missing tool), every heuristic |

Code-level standard: GEN-12 (crew-standards), the evidence this report states.

- **Why.** A reviewer reads "Not verified" first. A PR that omits it reads as fully checked,
  which is the unknown-as-pass failure again, at the level of the whole change.
- **Apply.** Mirror these four headings in `.github/pull_request_template.md` if the repo
  wants a template. Add no checkboxes for what CI already enforces: they get ticked on
  autopilot.

