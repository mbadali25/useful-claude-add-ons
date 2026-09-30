# 4. Development standards are applied at build time, with a required self-check

**Status:** accepted, 2026-09-28
**Decided by:** the owner (T-0085 direction, 2026-09-28), on the brainstorm's recommendation

## Context

Crew's QA reviews kept finding the same classes of defect, one round at a time. Across the 44
review outputs under this host's `.work/review/`, 224 unique BLOCK/FIX findings fall into a
dozen recurring shapes: an unknown collapsing into a safe-looking value, a check-then-act race
on a shared file, a fix right for its case and one rung short of its neighbour, docs that
contradict the code, verification evidence missing at the reviewed head. The cost was rounds:
T-0075 took three rounds with 9, then 11 findings; T-0072 used six; T-0009 and T-0010 each had a
round-4 rejection. Each round is roughly 30-50 minutes of suites plus a Codex run.

Nothing fed those findings back into how crew builds. `crew-best-practices` is a community
digest and the `stack-*` skills are per language; neither is built from this repository's own
review history, and neither `/crew:plan` nor `/crew:implement` checked a plan or a diff against
past findings before review. The owner's ask (2026-09-28): development standards so these items
are not missed the first time the code is built.

## Decision

1. **Standards are mined from findings and cited to them.** A classification of the 224 findings
   (`.work/tickets/T-0085/standards-draft.md`, local to this host) produced twelve crew-generic
   standards, GEN-01 to GEN-12, shipped in the `crew-standards` skill's `references/generic.md`.
   Each carries a rule, why, when it applies, a self-check with the answer that passes, the
   findings that earned it (ticket, round, `file:line@sha`, quoted claim) and the change sets they
   came from.
2. **Admission: three distinct reviewed change sets.** A class earned by fewer is not a plugin
   standard; it goes to the overlay of the repository that found it and is promoted when a third
   change set earns it. That moved identity (REPO-01) and change detection (REPO-02) into this
   repository's overlay, beside the release bookkeeping that names this repository's files
   (REPO-03).
3. **Plugin plus overlay.** Generic standards ship in the plugin; a repository adds its own in a
   tracked `.crew/standards.md` (set `REPO`, `## Supplements <GEN-id>` for literal commands). The
   overlay adds and never removes or weakens a plugin standard. A missing overlay reads as generic
   only; an unreadable or malformed one is could-not-tell and refuses, never "absent". T-0086's
   per-language sets plug in as further files with `applies-to` globs.
4. **Applied at build time.** `/crew:plan` names the standards each step triggers. `/crew:implement`
   and `/crew:fix` run a **required** self-check: every standard in the effective set answered
   `addressed` with evidence or `n/a` with a reason, then stamped with the review bundle's sha256
   and the standards digest.
5. **Gated before reservation, not by a hook.** `review_run.py` refuses to reserve a round (exit 2,
   nothing spent) without a current stamp, for every provider. It applies to a ticket with an
   approval receipt (the precondition of the two commands that run the self-check), or whose
   receipt cannot be proven absent, and stands down, logged, in an active incident.
6. **The reviewer gets the checklist, never the answers.** The shared prompt ends with the
   effective set's rules and self-check questions; the author's answers are withheld from the
   prompt so the reviewer judges applicability independently, and the prompt says the list does
   not bound the review. Withheld from the prompt, not hidden: `selfcheck.md` stays at
   `.work/tickets/<id>/selfcheck.md`, which a reviewer with read access to the checkout can open;
   the prompt never names it.
7. **The owner approves every new standard.** After each round, `crew_standards.py proposals`
   writes the round's findings verbatim for classification; nothing is added to a standards file
   automatically.
8. **Measured.** The metrics row's reviewer cell carries `std:<digest>`, and `crew_standards.py
   metric` reports first-round BLOCK+FIX per ticket before and after, refusing to call it below
   ten known tickets a side.

## Consequences

- No new hook and no new config key: the gate lives in the script that reserves the round, so
  CLAUDE.md's "Adding a hook" stop does not arise and `CONFIG.md` is unchanged.
- An `/crew:autopilot` run that reaches review without a self-check gets the exit-2 refusal and
  stops on its existing no-progress rule; teaching autopilot a self-check phase is a later ticket.
- Every in-flight ticket reviewed after this lands needs a self-check first; a ticket with no
  approval receipt is told the gate does not apply.
- The classification is one lane's judgement plus one second-reader spot check (24 findings, two
  disagreements, no admission change); the owner can overturn a standard at review acceptance.
