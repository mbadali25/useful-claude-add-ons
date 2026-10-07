# L-0534 direction - PowerShell development standards set (T-0086 slice)

Status: approved direction, inherited from T-0086. Owner 2026-09-30 ~11:20: "File 7 tickets now" - the remaining T-0086 language slices each get their own ticket, spec, review budget and PR. T-0086 closes as the Python slice.

Carry over unchanged from `.work/tickets/T-0086/direction.md`: the one-set-per-stack format on T-0085's wiring (`plugin/crew/skills/crew-standards/references/powershell.md`, `applies-to` globs), the admission bar (findings from at least three distinct reviewed change sets; an official doc is the Source, not a change set; rules below the bar are listed as candidates in the stack skill, not shipped), Earned-by citations re-read from the raw sources, a change-set count for every rule, and the self-check wiring. Follow T-0086's Python slice as the worked example: its spec, plan, tests (test_crew_standards.py count and quote checks) and sabotage_standards.py entries.

Research: `.work/tickets/T-0086/research/powershell.md` (and README.md, "Recommended next step").
Stack skill: extend stack-powershell; settle StrictMode, BOM-vs-ASCII, POWERSHELL-20 placement per research.
Order in T-0086's direction: Python (T-0086), SQL (L-0532), PHP (L-0533), PowerShell (L-0534), .NET (L-0535), Terraform (L-0536), Node.js (L-0537), Angular 2+ (L-0538). The slices are independent files, but each touches crew-standards/SKILL.md and BUDGETS.md, so they land through the merge train one at a time.
Depends on: T-0086 (Python) landing first, which sets the pattern and the test and sabotage scaffolding. Also L-0539 (the check-tooling-pr.py fix), else each slice needs the same rule-36 waiver T-0086 got.

## Ask
Owner, 2026-09-28 (T-0086): general development standards for PowerShell "so that other repos could benefit". Owner, 2026-09-30: each remaining T-0086 language slice gets its own ticket, spec, review budget and PR. This is the PowerShell slice: a set file in `plugin/crew/skills/crew-standards/references/` on T-0085's loader, unchanged, with the rules that meet the landed admission bar, and `stack-powershell` pointing at it and listing the rest as candidates. The three research questions (StrictMode, BOM vs ASCII, POWERSHELL-20) are settled here.

## Facts found at origin/main `a555ff37` (2026-10-05)
- T-0086 (Python) is merged (#282). No PowerShell set exists. No PR or commit names L-0534.
- **The research's ids cannot load.** A set name must be 2-6 capital letters (`plugin/crew/hooks/scripts/crew_standards.py:131-133`), a heading must match `^## ([A-Z]{2,6}-\d{2}) ` (`:84`, ids `:83`), and a standard's prefix must equal the file's `set:` (`:188-190`). `POWERSHELL` is ten letters, so both `set: POWERSHELL` and `## POWERSHELL-01 ...` are refused.
- `stack-powershell/SKILL.md` is 107 lines; the stack-skill cap is 120 (`plugin/crew/tests/test_stack_skills.py:142`). The Python slice's Standards and Candidates sections took about 40 lines.
- POWERSHELL-20 (code that reads PowerShell uses PowerShell's parser) is about Python and other code that parses PowerShell text, chiefly this repository's guards (`crew_guards.py`). A set whose `applies-to` is `*.ps1` never applies to that code.
- The research (held by the coordinator, `.work/tickets/T-0086/research/powershell.md`, not published) found no owner script using `Set-StrictMode`; POWERSHELL-16's strict-mode half rests on a document alone.
- All 44 tracked `.ps1`/`.psm1` files in this repository are ASCII-only (no byte above 0x7F, checked 2026-10-05).
- L-0539 is still `direction`, no PR; `sabotage*.py` is still `HARNESS` (`scripts/check-tooling-pr.py:79`).
- An orchestrator pre-count on 2026-10-05, under T-0086's counting rule, found that **no rule clearly reaches three reviewed change sets on the research's own citations**: several cited commits in this repository belong to one review series and count once, and session notes do not count. The leads are large: this repository's own `CHANGELOG.md` has 430 lines naming PowerShell, many inside review-round entries (for example `CHANGELOG.md:1641` "Second review of #347"), and the owner's private repos hold more.

## Options
1. **Set `PWSH`, mine then admit, compact skill pointer (recommended).** File `references/powershell.md`, set `PWSH`, ids `PWSH-NN` keeping the research numbers. An evidence step counts change sets from this repository's own reviews and CHANGELOG first, then the owner's private repos. `stack-powershell` gains a compact pointer and candidate list within 120 lines. Cost: ids differ from the research text, so the set's lead paragraph maps them.
2. **Widen `_ID_RE` to allow `POWERSHELL`.** Keeps research ids. Cost: a loader change, which every slice so far has excluded; it changes the parser for every repo's overlay too.
3. **Set `PS`.** Shortest. Cost: ambiguous (PostScript, process status) in a self-check row.

## Recommendation
Option 1, with these defaults, approved 2026-10-05 for cloud hand-off under the owner's standing self-approve authority.

## Open questions (default taken)
- **Set name and ids.** `PWSH`, `PWSH-01`..`PWSH-20` = research `POWERSHELL-01`..`-20`; the lead paragraph says so once.
- **applies-to.** `["**/*.ps1", "**/*.psm1", "**/*.psd1"]`.
- **StrictMode (research question 1).** Dropped from the gated rule: it has no owner change set. Listed in `stack-powershell` as a doc-only candidate ("`Set-StrictMode -Version 3.0` in new scripts"), 0 change sets. The command-resolution half of PWSH-16 is counted on its own.
- **BOM vs ASCII (question 2).** The lane's position: a `.ps1` holding any non-ASCII byte is saved as UTF-8 with a BOM; ASCII-only source meets the rule trivially. This repository's `.ps1` files are all ASCII already.
- **POWERSHELL-20 (question 3).** Not in the plugin set: its `applies-to` would be `.py`, and its change sets are this repository's guard tickets. Listed in `stack-powershell` as overlay material; this ticket does not write `.crew/standards.md`.
- **Skill length.** Admitted ids listed inline, candidates one line each, pitfall lines a standard now covers shrink to a pointer; if still over 120 lines, the candidate list moves to `stack-powershell/references/candidates.md`.
- **Private evidence in a public file.** Change sets from this repository are cited normally; any from the owner's private repos are cited generically under opaque labels, mapping kept machine-local.
- **Sabotage entries.** Not in this PR (harness, L-0539 not landed); a follow-up tooling-only PR, unless L-0539 merged first. Each new test is proven red by a hand-run mutation.
- **If no rule is admitted**, no `powershell.md` ships; every rule becomes a candidate.

## Approval
Direction approved 2026-10-05 for cloud hand-off by the orchestrator under the owner's standing self-approve authority. Next: spec (`docs/tickets/L-0534/spec.md`).
