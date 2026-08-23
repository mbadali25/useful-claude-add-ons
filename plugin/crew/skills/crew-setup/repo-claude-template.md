<!-- <repo>/CLAUDE.md — target 40 lines, hard ceiling 60.
     Loads into EVERY subagent on EVERY delegation. Eight delegations x 4k tokens
     is 32k of overhead before any work happens. Everything mechanizable belongs
     in .crew/verify.json instead, where a hook enforces it and nothing is paid
     for repeatedly. What stays here is judgment a command cannot make. -->

# <repo-name>

**Stack:** <...>   **Runs:** <one line to start locally>
**Platform:** <linux | wsl2/Ubuntu | windows>   **Shell:** <bash | powershell>
**Talks to:** <db, upstream services, consumers>

## Commands
| build | `<...>` |
| test  | `<...>` |
| verify | `bash _verify/smoke.sh` |
| regression | `bash _verify/run-all.sh` |
| promote | `/crew:promote <development\|qa\|production>` |
| migrate | `<...>` |

## Where things are
- entrypoint: `<path>`   logic: `<path>`   data access: `<path>`
- DO NOT TOUCH: `<vendor/, generated/, legacy/>`

## Scope discipline
- Fix the ticket, not what you notice nearby. Unrelated problems go in
  `.work/FINDINGS.md`, not into this diff.
- Match the patterns already in the file over your preferred style.
- No new dependency without asking first.
- If a change grows past roughly 10 files, stop and confirm the approach.

## Stop and ask
- The ticket's "done when" is not observable
- The fix requires changing a public interface or a schema
- You are about to work around a failing check rather than fix it
- You are unsure. A question costs less than a wrong guess.

## Promotion: development -> qa -> production
- That order, no skipping. Production only gets an artifact qa proved. Same sha
  across environments - a rebuild between them means qa proved nothing.
- Every deploy is followed by all three, in order: **smoke** (does it respond),
  **regression** (does everything else still work), **verify** (error logs,
  alarms, queues - after a soak, not immediately). Run `/crew:promote <env>`.
- A green deploy is the weakest evidence in that list. It proves bytes moved.
- No verified rollback runbook inside 90 days, no production deploy. No override.
- A failed gate stops the promotion. Roll back or fix forward, then run the
  whole sequence again from the start. Never resume mid-sequence.
- Never `terraform apply`, never DDL against prod, never force push.

## Reporting
- Report failures and error text verbatim. Never paraphrase an error.
- Say what you did NOT verify. Silence reads as confirmation.
- No summary of what you just did unless asked — the diff is right there.

## Memory
Code map: `.crew/codemap/INDEX.md`. Runbooks: `docs/runbooks/INDEX.md`.
Read the index, then one file. Check a note's anchor sha before trusting it —
code wins over notes, always.
