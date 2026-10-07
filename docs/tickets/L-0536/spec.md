# L-0536: Terraform development standards (TERRAFORM), T-0086 slice: candidates now, a set when earned          status: spec   risk: low
Slice of T-0086 (done, PR #282, crew 1.0.77). Written against origin/main `a555ff37` (crew 1.1.0). Research input:
`.work/tickets/T-0086/research/terraform.md` (local only).

## Intent
Apply T-0086's admission bar to the nineteen Terraform research rules and ship what it gives. The re-count for this
spec finds no rule with three reviewed change sets, so the expected result is guidance only: `stack-terraform`
gets a `## Standards` section that says no gated TERRAFORM set ships yet, and why, and a `## Candidate standards
(not gated)` section listing TERRAFORM-01 to -19, each in one sentence with its change-set count and what promotes
it. The three Terraform questions are settled there (default positions in direction.md). If the implementing
session's check of the cited PRs' review threads lifts any rule to three, that rule ships in
`plugin/crew/skills/crew-standards/references/terraform.md`, set `TERRAFORM`, `applies-to: ["**/*.tf", "**/*.tftest.hcl"]`,
exactly as the Python and .NET slices do, with the test and doc additions listed in Touch under "only if a set ships".

## Exclusions
- No change to the counting rule or the bar. A plan failure, an apply failure, a TFC run or an author's own fix
  is not a reviewed change set (direction Option 2, rejected). CLAUDE.md lines, repo docs and vault notes are not.
- No change to the loader, gate, stamp or checklist (`crew_standards.py`, `review_run.py`, `review_prompt.py`).
- No empty or placeholder set file. A `references/terraform.md` with no standard is refused by the loader
  (`test_refusal_branch_empty_set`), so it exists only if a rule passes.
- No edit to `plugin/crew/tests/sabotage*.py` (HARNESS, `scripts/check-tooling-pr.py:79`). If a set ships, its
  sabotage entries are a tooling-only follow-up (or ride along if L-0539 has merged).
- No change to `crew-terraform` (terraform-docs, tflint, `--output-check`); the research says nothing here restates it.
- No restatement of `stack-terraform`'s existing pitfalls (`:20-43`); a candidate that extends one is pointed to
  from the end of that pitfall.
- No overlay change (`.crew/standards.md`). Owner conventions with no recorded defect (tags, `BackupPlan`) stay out,
  as the research recommends (`research/terraform.md:1076-1079`).
- No `.crew/verify.json`, CONFIG.md, hook or guide change. No version bump on the build branch (REPO-03).

## Evidence
origin/main `a555ff37`:
- Bar: `plugin/crew/skills/crew-standards/SKILL.md:16-17`; counting rule as shipped:
  `plugin/crew/skills/crew-standards/references/python.md:8-20` (lead paragraph).
- Stack skill: `plugin/crew/skills/stack-terraform/SKILL.md` (84 lines; pitfalls `:20-43`, Verification `:45`,
  verify.json rule `:52`; no Standards section). Python's shape: `plugin/crew/skills/stack-python/SKILL.md:46`
  `## Standards`, `:63` `## Candidate standards (not gated)` (one line per candidate, count and names in brackets).
- Stack skills test: `plugin/crew/tests/test_stack_skills.py:63`, `:80` (`stack-terraform` and its trigger word).
- Research rules: `research/terraform.md` TERRAFORM-01 `:80` ... -19 `:995`; anti-patterns `:1036`; candidates
  considered `:1071`; open questions `:1084-1094`; HashiCorp quotes through WebFetch's summariser (`:1103-1106`).
- Re-count, 2026-10-05: `git -C /repos/anew/<repo> log -1 --format=%B <sha>` over every cited commit, PR from the
  first merge commit after it. Commits whose message records a review: `tsi@b2e03ad` and `tsi@6e5eb4b` (PR #4, "Codex
  review findings", "Codex re-review"), `Warehouse@d7dcf6b` (PR #45, "Review caught a divergence"), `Vault@f445977`
  (PR #19, "Codex merge-gate HOLD"), `Vault@ce7a5d4` (PR #19, "security review, PR #19"), `Vault@9ac86ab` (PR #34,
  "task-2-review"), `Vault@d969203` (PR #10, "review finding"), `Vault@c96e79a` (PR #32, "Review fix round 1").
  Every other cited commit records none (its defect was found by a plan, an apply, a TFC run or the author).
  Per rule: -01 0; -02 0; -03 0; -04 0; -05 1 (tsi #4); -06 1 (Warehouse #45); -07 0; -08 0; -09 1 (tsi #4); -10 1
  (Vault #19); -11 2 (Vault #34, #19); -12 2 (Vault #19, #10); -13 0; -14 1 (Vault #32; `Warehouse@5b41162` says
  only "worth reviewing carefully"); -15 0; -16 1 (tsi #4); -17 1 (Vault #32); -18 0; -19 0.
- Docs that name the stacks: `plugin/crew/README.md:795` ("The other stacks (... Terraform ...) follow as further
  files"); `plugin/PLUGINS.md:224` (stack-terraform row), `:217` (crew-standards row).
- Version: `plugin/crew/.claude-plugin/plugin.json:3` is `1.1.0`.

## Unknowns
- **PR review threads.** The repos are on GitHub (ANEW-Business-Solutions). A PR whose review thread records a
  finding for a cited commit's defect makes that PR a reviewed change set even if the commit message does not say
  so. Resolved at implement: for each cited PR, `gh pr view <n> -R <owner/repo> --comments` and `gh api
  repos/<owner>/<repo>/pulls/<n>/reviews`; record one line per change set in
  `.work/tickets/L-0536/changesets-terraform.txt`. If access fails, the count stays as above (unknown is not counted).
- **Whether a set ships.** Follows from the line above. If one does: raw-verify every HashiCorp/AWS quote with
  `curl` into `.work/tickets/L-0536/quote-check-terraform.txt`, no `[...]` elisions, and add the Touch items
  marked "only if a set ships".
- **Terraform 1.7 for `for_each` in `import`.** Resolved at implement from the raw 1.7 changelog
  (`https://github.com/hashicorp/terraform/blob/v1.7/CHANGELOG.md`); unverified means the candidate line says so.
- **The 120-line cap.** Every stack skill is at most 120 lines (`plugin/crew/tests/test_stack_skills.py:73`, `:142`);
  `stack-terraform` is 84 now, and nineteen candidate lines plus the settled questions do not fit. Default taken:
  the candidates and the three settled questions go to `plugin/crew/skills/stack-terraform/references/candidates.md`;
  SKILL.md keeps `## Standards` (no gated set yet, or the pointer) and a one-line link to it.
- **Private repositories.** Accepted as risk, as for PYTHON and DOTNET: each count names the repo and PR.
- Merge train with L-0532..L-0535, L-0537, L-0538 (shared doc lines). Next free crew patch set at land.

## Size and split
Expected: about 10 lines in `stack-terraform/SKILL.md` and about 50 in its new `references/candidates.md`, a few doc lines, no tests beyond the existing ones, no
production code, no harness path. If a set ships: about 60-120 more lines of set file and about 40 lines of tests.
No further split.

## Touch
- `plugin/crew/skills/stack-terraform/SKILL.md` - `## Standards` (no gated set yet, or the pointer if one ships),
  a link to the candidates, pointers from pitfalls `:22-43`; stays within 120 lines
- `plugin/crew/skills/stack-terraform/references/candidates.md` - new: `## Candidate standards (not gated)` and the
  three settled questions
- `plugin/crew/README.md` - `:795` says Terraform has candidates only (or names the set)
- `plugin/PLUGINS.md` - `stack-terraform` row; version
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` - version, at land only
- `.crew/codemap/**`, `.claude/rules/**`, `graphify-out/**`, `docs/diagrams/**` - refresh only (standing rule)
- `docs/tickets/L-0536/` - removed in the final PR
- Only if a set ships: `plugin/crew/skills/crew-standards/references/terraform.md` (new),
  `plugin/crew/skills/crew-standards/SKILL.md` (stack-sets bullet), `plugin/crew/tests/test_crew_standards.py`
  (`_ADMITTED_TERRAFORM`, `_TERRAFORM_FINDINGS`, parse / applies-to / finding-count tests), `plugin/PLUGINS.md`
  `crew-standards` row, `.crew/codemap/crew.md` effective-set bullet.

Not in Touch: `plugin/crew/tests/sabotage*.py` (harness), `plugin/crew/skills/crew-terraform/SKILL.md`,
`plugin/crew/CONFIG.md`, `docs/guides/crew/**` (names no set), `.crew/verify.json`, `.crew/standards.md`.

## Acceptance checks
Commands from the repo root; pytest through the heavy-run wrapper on a memory-bound host.
- [ ] `.work/tickets/L-0536/changesets-terraform.txt` lists every cited commit with its PR, the review evidence (or
  "none recorded") and the per-rule count; the counts in `stack-terraform/SKILL.md` match it.
  `grep -c "^TERRAFORM-" .work/tickets/L-0536/changesets-terraform.txt`
- [ ] `stack-terraform/SKILL.md` has `## Standards` and links `references/candidates.md`, which has `## Candidate
  standards (not gated)`; every research id TERRAFORM-01 to -19 is either a candidate line with `(<N>` count or, if
  shipped, listed under Standards; none is in both. `python3 -c "import re;t=''.join(open(p,encoding='utf-8').read() for p in ('plugin/crew/skills/stack-terraform/SKILL.md','plugin/crew/skills/stack-terraform/references/candidates.md'));ids=re.findall(r'TERRAFORM-\d\d',t);print(sorted(set(ids))==[f'TERRAFORM-{n:02d}' for n in range(1,20)])"` prints `True`
- [ ] The three questions are stated with their settled position and, where uncited, flagged as such.
  `grep -n "1.7\|CMK\|literal ARN" plugin/crew/skills/stack-terraform/references/candidates.md`
- [ ] If no set ships: `test ! -e plugin/crew/skills/crew-standards/references/terraform.md`, and README `:795`
  says Terraform has candidates only. If a set ships: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_standards.py -q`
  passes with `[terraform.md]` cases, and `-k test_terraform_set_applies_to_terraform_files_only` shows `.tf` and
  `.tftest.hcl` draw the set and `README.md`, `x.tfvars`, `.terraform.lock.hcl` do not; each new test was
  hand-sabotaged red once (PR body).
- [ ] Existing suites: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_stack_skills.py plugin/crew/tests/test_crew_standards.py plugin/crew/tests/test_lifecycle_commands.py -q`
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`.
- [ ] Docs: README, PLUGINS.md row, CHANGELOG entry (stating the re-count result), BUDGETS.md re-measured; crew bumped
  to the next free patch at land; `python3 scripts/check-marketplace.py` passes after the commit.
- [ ] Refresh: `python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check` and
  `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket L-0536` pass.

## Dependencies
- T-0086 (PR #282): merged.
- L-0539: not merged; matters only if a set ships (sabotage entries).
- Siblings L-0532..L-0535, L-0537, L-0538: shared doc lines; land one at a time.
- Owner may later choose direction Option 2 (count plan/apply findings for infrastructure); that would be a new
  ticket changing the bar, not this one.

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05. Plan: to be written by the implementing session.
