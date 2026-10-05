# T-0102 one marketplace reference skill: Linux tools on a Windows system, and SSM's limits          status: spec   risk: med
## Refreshed 2026-10-04
First spec for this ticket; there was no earlier spec.md or plan.md on this box. Written from direction.md (rebuilt the same day from the INDEX row) and checked against origin/main `155fe6d8`. The owner was not available, so each open question in direction.md has its default taken here: the skill is named `windows-ssm`, the helper is in scope, and output exactly at a limit counts as truncated.

## Intent
Add one installable skill, `skills/windows-ssm/`, that a session loads when it runs Linux-style tools on a Windows machine or drives a node through AWS Systems Manager. It carries two reference files: `references/windows-tools.md` (which shell a command lands in, path conversion, missing interpreters, line endings, WSL against Git Bash against PowerShell) and `references/ssm-limits.md` (what Run Command, Session Manager, documents and Parameter Store will carry, each number cited to an AWS documentation URL). One offline helper, `scripts/ssm_output.py`, reads a `get-command-invocation` result and exits non-zero when the output is cut or when it cannot tell, so a truncated payload fails loudly and is never parsed as complete.

## Exclusions
- No change under `plugin/crew/`. The skill points to crew's `shellRoute` setting for crew users and does not restate it. No crew version bump and no crew document set.
- No hook. Nothing here runs unless the model or the user invokes it.
- The helper makes no AWS call, reads no credentials and writes no file. It reads one JSON document from a path or stdin. It never prints the command output it inspects, only lengths and a verdict.
- No wrapper around `aws ssm send-command`, no polling loop, no S3 or CloudWatch fetch. The reference file shows those commands; the helper does not run them.
- No PowerShell twin of the helper. It is stdlib Python and runs on both systems.
- No hostnames, account or profile names, instance ids, bucket names or customer data in any file. Examples use AWS's documentation placeholders (`i-02573cafcfEXAMPLE`, `amzn-s3-demo-bucket`).
- No new claims about other repositories or their security setup.
- No edit to the review or gate harness (`HARNESS` in `scripts/check-tooling-pr.py`).
- The README's install URLs are pinned to a commit sha (`README.md:12`, `:18`). Re-pinning them is the usual separate step after the merge, not part of this PR.

## Evidence
Read at origin/main `155fe6d8` on 2026-10-04.
- Nothing on main covers this. `git ls-tree --name-only origin/main skills/` lists 35 skill directories, none for Windows shells or SSM. SSM is named only as a reach verb (`plugin/crew/CONFIG.md:1456`, `:2453`; `plugin/crew/commands/verify.md:179`) and in one clause of `plugin/crew/skills/stack-powershell/SKILL.md:26`.
- Existing Windows shell facts this skill generalises: the repo `CLAUDE.md` "Landmines" section (`pwsh` not on Git Bash's PATH, no `python3` in Git Bash, a bare hook command goes to Git Bash, `write_text` makes CRLF, `MSYS_NO_PATHCONV=1`); `plugin/crew/skills/crew-setup/SKILL.md:51-55` (WSL facts and the `shellRoute.mode` values); `plugin/crew/skills/crew-setup/phases.md:76-86` (`/mnt/c` is slow, credentials do not cross the WSL boundary); `plugin/crew/skills/crew-diagrams/scripts/render.sh:96-105` (`cygpath -w` for a Windows program given a POSIX path).
- Registration, every place a new skill must appear:
  - `.claude-plugin/marketplace.json:203-215`: entries are alphabetical; `windows-ssm` goes after `web-testing-playwright` and before `work-log-reporter` (`:215`). Required fields are `name`, `source`, `description`, `version` (`scripts/check-marketplace.py:35`).
  - `scripts/install-prerequisites.sh:1298` `SKILL_KEYS` and `:1335` `SKILL_NAME`; `scripts/install-prerequisites.ps1:1127` `$script:SkillCatalog`. `check_catalogs` (`scripts/check-marketplace.py:301-326`) requires both to list the same keys in marketplace order.
  - `README.md:826` (the skills table; `web-research` row at `:860`) and `skills/README.md:86` (table; `web-research` row at `:120`). `check_docs` (`scripts/check-marketplace.py:413-427`) requires a row linking `[`name`](skills/name)` and `[`name`](name)`.
  - `skills/UPDATE.md:1-9`: new skills are listed here and mirrored into both READMEs by `scripts/sync-updates.py`.
  - `CHANGELOG.md:5-7`: entries go under `## [Unreleased]` as `### Added — `name` version: summary`.
- Counts that move from 35 to 36: `README.md:52` (inside the fence under the marker at `:46`), `README.md:154`, `INSTALLATION.md:19` (fence under the marker at `:13`), `INSTALLATION.md:45`. All four are bound to `<!-- claim: skills-count -->` and checked by `check_self_claims` (`scripts/check-marketplace.py:673`).
- `check_skill_manifests` (`scripts/check-marketplace.py:132-157`): SKILL.md must have frontmatter with `name` equal to the directory and a `description`.
- Skill shape: `Skill-Authoring-Standard.md` sections 1-6 (kebab-case directory, `references/` for long material, stdlib-only scripts, description states what and when). `skills/session-defaults/` is a reference-style skill with four reference files; `skills/mailgun/scripts/mg.py` is a stdlib-only helper.
- Test wiring for a skill suite. Three places name the skill test directories and must agree:
  - `.crew/verify.json:287-292` (paths `skills/mermaid-svg-bitbucket/**`, `skills/notify/**`, `skills/cisco-meraki/**`; one pytest command)
  - `scripts/gate-runner.py:132-134` `COMBINED_DIRS`
  - `.github/workflows/pytest-crew.yml:123` (the combined pytest step)
  `pytest-crew.yml:130` records that two test directories each holding a file with the same module name collide in a combined run, so the new test file needs a name no other suite uses.
- `.crew/verify.json:80-86` runs `python3 scripts/check-marketplace.py` for any `skills/**` change; `:88-93` runs `bash _verify/smoke.sh` for `**/SKILL.md` and either install script; `:96-104` runs `self-claims.py` and `sync-updates.py --check` for README, INSTALLATION and CHANGELOG; `:256-259` runs ruff and pylint for any `*.py`.
- Harness: `scripts/check-tooling-pr.py:58-87`. None of this ticket's paths is in `HARNESS`.
- AWS facts, read 2026-10-04:
  - `GetCommandInvocation` API reference (`https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_GetCommandInvocation.html`): `StandardOutputContent` is "The first 24,000 characters written by the plugin to stdout", maximum length 24000; `StandardErrorContent` is the first 8,000 characters, maximum length 8000; `StandardOutputUrl` and `StandardErrorUrl` hold the complete text in S3 and are empty when no bucket was given; `Comment` has a maximum length of 100; `Status` is one of `Pending | InProgress | Delayed | Success | Cancelled | TimedOut | Failed | Cancelling`; `ResponseCode` `-1` means the command has not started or was not received.
  - Systems Manager service quotas (`https://docs.aws.amazon.com/general/latest/gr/ssm.html`): document size 64 KB; Parameter Store value 4 KB standard, 8 KB advanced; Session Manager idle timeout 20 minutes by default, configurable from 1 to 60; Automation `executeScript` output 100 KB.

## Unknowns
- Whether SSM Agent appends a marker such as `---Output truncated---` inside the 24,000 characters, and its exact text for stdout and stderr. Not confirmed from an AWS page on 2026-10-04. Resolved by design: the helper's rule is length at or above the limit; a marker is an extra signal only if the implementer finds it in AWS documentation or the agent's public source, with the URL cited. No uncited marker string goes into the code or the reference.
- Whether "characters" means characters or bytes for non-ASCII output. Resolved by design: the helper counts both and reports truncated if either reaches the limit.
- Limits on the request side (the size of `SendCommand` `Parameters`, the Windows command-line length a script is passed on). Resolved at implement: each number in `ssm-limits.md` carries an AWS or Microsoft documentation URL, or the line says "not documented; stage the payload in S3 and verify its hash on the node". A number with no URL is not written.
- Whether `pytest-crew.yml`'s path filter already starts the leg for a change under `skills/windows-ssm/`. Resolved at implement: read the workflow's `paths` and the `RUN_LEG` logic before editing line 123.
- Whether `scripts/_test/gate-runner.py` pins the `COMBINED_DIRS` text. Resolved at implement: run that suite after the edit; it is listed in Touch.
- Skill name, helper in or out, the at-limit rule, default-on in the menu: owner questions with defaults taken (direction.md).

## Size and split
- Estimate: about 125 added production lines. `skills/windows-ssm/scripts/ssm_output.py` about 110, the marketplace entry 6, the two install scripts 2 lines each, `gate-runner.py` 1, the workflow and verify.json a few. The three markdown files (about 400 lines together) are documentation.
- One new checker with one fail-closed outcome set (complete, truncated, could not tell). No second parser or guard.
- No harness path. One feature PR.
- Not split. If the owner answers question 2 with "out", drop the helper, its tests and the three test-wiring files from Touch, and the rest stands as written.

## Touch
- `skills/windows-ssm/SKILL.md` - new
- `skills/windows-ssm/references/windows-tools.md` - new
- `skills/windows-ssm/references/ssm-limits.md` - new
- `skills/windows-ssm/scripts/ssm_output.py` - new
- `skills/windows-ssm/tests/test_ssm_output.py` - new
- `.claude-plugin/marketplace.json` - one entry, version 1.0.0
- `scripts/install-prerequisites.sh` - SKILL_KEYS and SKILL_NAME, same position and text as the ps1
- `scripts/install-prerequisites.ps1` - SkillCatalog row
- `README.md` - table row, the two counts, the mirrored update block
- `skills/README.md` - table row, the mirrored update block
- `skills/UPDATE.md`
- `INSTALLATION.md` - the two counts
- `CHANGELOG.md`
- `.crew/verify.json` - the skill-suites rule gains the path and the test directory
- `scripts/gate-runner.py` - COMBINED_DIRS
- `scripts/_test/gate-runner.py` - only if it pins the directory list
- `.github/workflows/pytest-crew.yml` - the combined pytest step
- `.crew/codemap/marketplace-registration.md` - count and re-anchor
- `.crew/codemap/install-scripts.md` - count and re-anchor
- `graphify-out/**` - rebuilt by graphify update .

Not in Touch, stated: anything under `plugin/` (so `plugin/PLUGINS.md` and crew's documents do not move); `MARKETPLACE.md`, `Skill-Authoring-Standard.md`, `Skill-Pipeline.md` (no rule changes); `docs/diagrams/` (no box or edge changes).

## Acceptance checks
Commands run from the repo root, after the commit (the version-drift check compares commits).
- [ ] The skill exists and is well formed: `skills/windows-ssm/SKILL.md` has frontmatter `name: windows-ssm` and a description that states what it covers and when to use it, with symptom phrasings (for example "command not found: python3 in Git Bash", "the SSM output stops halfway", "path turned into C:/Program Files/Git/..."). It has a reference map naming both reference files and 3 to 6 example invocations of the helper. `python3 scripts/check-marketplace.py` prints `marketplace: 36 skills, 5 plugins` and `all checks passed`. Maps to verify.json rule `:80`.
- [ ] `references/windows-tools.md` covers, each with the command that shows it: which shell a bare command reaches; resolving `python3`/`python`/`py` and naming `pwsh` by full path; MSYS path conversion and `MSYS_NO_PATHCONV=1`; `cygpath -w` for a Windows program given a POSIX path; CRLF and how to measure it (`file`, `od -c`); when WSL is the better route and what does not cross its boundary; for crew users, one pointer to `shellRoute`. Check: `grep -c -E 'MSYS_NO_PATHCONV|cygpath|pwsh|python3|CRLF|WSL|shellRoute' skills/windows-ssm/references/windows-tools.md` is 7 or more.
- [ ] `references/ssm-limits.md` states each limit in a table with its source URL: stdout 24,000 and stderr 8,000 characters through the API, document size 64 KB, Parameter Store 4 KB and 8 KB, Session Manager idle timeout, `Comment` 100. It gives the two complete-output routes (`--output-s3-bucket-name`, `--cloud-watch-output-config`) and the rule for inbound payloads (stage in S3, verify a hash on the node). Check: every table row with a number has a `https://docs.aws.amazon.com/` or `https://learn.microsoft.com/` link on the same row: `python3 -m pytest skills/windows-ssm/tests/test_ssm_output.py -q -k test_every_limit_row_cites_a_source`.
- [ ] Helper, must-pass: a terminal invocation (`Success` or `Failed`) with stdout and stderr under their limits exits 0 and prints `complete`. `-k test_short_output_is_complete`
- [ ] Helper, must-fail, one test each, all exit non-zero and name the reason on stderr:
  - stdout of exactly 24,000 characters (exit 3, `truncated`)
  - stdout over the limit in bytes but under it in characters (exit 3)
  - stderr of exactly 8,000 characters (exit 3)
  - a status that is not terminal: `Pending`, `InProgress`, `Delayed`, `Cancelling` (exit 4, `could not tell`)
  - `TimedOut` or `Cancelled` (exit 4)
  - input that is not JSON, or JSON with no `StandardOutputContent` key (exit 4)
  - an empty file (exit 4)
- [ ] When the output is truncated and `StandardOutputUrl` is non-empty, the helper prints that URL as where the full text is, and still exits 3. `-k test_truncated_output_names_the_s3_url`
- [ ] The helper never prints the inspected content: a fixture with a sentinel string in stdout does not show the sentinel on the helper's stdout or stderr. `-k test_content_is_never_echoed`
- [ ] Sabotage, run by hand and reported in the PR: change the comparison from `>=` to `>` and `test_stdout_at_the_limit_is_truncated` goes red; make the non-terminal branch return 0 and the could-not-tell tests go red. Restore, and the suite is green.
- [ ] The suite is wired in all three places and they agree: `python3 -m pytest skills/windows-ssm/tests/ -q` passes; `.crew/verify.json`'s skill-suites rule lists `skills/windows-ssm/**` and the test directory; `scripts/gate-runner.py` and `.github/workflows/pytest-crew.yml:123` name `skills/windows-ssm/tests/`; `python3 scripts/_test/gate-runner.py` passes.
- [ ] Registration is whole: both install scripts list `windows-ssm` at the same position with the same label text; both READMEs have the table row; the four counts read 36. `bash _verify/smoke.sh`, `python3 scripts/_test/self-claims.py` and `python3 scripts/sync-updates.py --check` pass.
- [ ] Lint: `python3 -m ruff check skills/windows-ssm` and `python3 -m pylint skills/windows-ssm/scripts/ssm_output.py` report nothing new.
- [ ] No private data: `git grep -n -E 'i-[0-9a-f]{8,17}|[0-9]{12}|AKIA[0-9A-Z]{16}' -- skills/windows-ssm` prints only AWS documentation placeholders ending in `EXAMPLE`.
- [ ] `CHANGELOG.md` has ``### Added — `windows-ssm` 1.0.0`` under Unreleased and `skills/UPDATE.md` has the entry.
- [ ] The PR body states which suites ran and which did not, and that `scripts/_test/drift-detection.sh` was skipped (it drives the real CLI).

## Dependencies
Must land first: none open.
- T-0040 (merged, PR #290): crew's Windows shell routes. Context only; the new skill points to `shellRoute` and must not contradict it.
- L-0561 (merged): registered `mailgun` and set the count to 35, the number this ticket moves.

Related, no order forced: L-0632 (direction; diagram standard for other skills), L-0597 (done; Skill-Pipeline merge wording).

Blocks: nothing in INDEX names T-0102.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
