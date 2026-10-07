# L-0535: .NET development standards set (DOTNET), T-0086 slice          status: spec   risk: medium
Slice of T-0086 (done, PR #282, crew 1.0.77). Written against origin/main `a555ff37` (crew 1.1.0). Research input:
`.work/tickets/T-0086/research/dotnet.md` (local only; its rule text and citations are what this slice cuts down).

## Intent
Ship the .NET / C# standards set on T-0085's loader, unchanged: `plugin/crew/skills/crew-standards/references/dotnet.md`,
set `DOTNET`, `applies-to: ["**/*.cs", "**/*.cshtml", "**/*.razor"]`. It holds only the research rules that findings
from at least three distinct reviewed change sets earn, counted by the rule `python.md`'s lead states. Each shipped
rule keeps its Earned-by citations and a Microsoft Learn Source quoted verbatim from the raw page. Every other
research rule is listed as a candidate in `stack-dotnet`, with its count and what would promote it. `stack-dotnet`
points at the set, and its guidance agrees with the owner's global .NET rules (`var` and the other style rules as
conventions; NSubstitute + FluentAssertions for new test projects; no `Result` package mandated). A change touching
C# then answers the DOTNET rows in its required self-check.

## Exclusions
- No change to the loader, gate, stamp or checklist: `crew_standards.py`, `review_run.py`, `review_prompt.py` and
  `crew_ticket.py` are not touched. A stack set is a new file in `references/` (`crew_standards.py:236` `_plugin_sets`).
- No edit to `plugin/crew/tests/sabotage*.py`. It is a HARNESS path (`scripts/check-tooling-pr.py:79`), so the
  sabotage entries for this set land in a separate tooling-only PR after this one. Exception: if L-0539 has
  merged first and its rule admits a feature's own sabotage entries, they ride along here, and the PR says so.
- No other stack and no other set file. No change to `python.md`, `generic.md` or `.crew/standards.md`.
- No candidate in the gated file. A rule below three change sets is not written into `dotnet.md` or the overlay.
- No machine-local citation in the shipped file: no `/repos/` path, vault note, `wiki/concepts`, auto-memory,
  `.work/` path or `Fnnn` id (`test_shipped_sets_cite_no_machine_local_note`, `test_shipped_sets_cite_nothing_local_only`).
- No conventions as standards: file-scoped namespaces, `var`, primary constructors, records, no `#region`,
  `IReadOnlyList<T>` returns get no id and no self-check row. No review finding earned them (`research/dotnet.md:56-58`).
- No `.NET Framework 4.8` rules. The research did not mine net48 history (`research/dotnet.md:1051-1052`).
- No `.crew/verify.json` change: `plugin/crew/skills/crew-standards/**` is already in the crew-standards rule
  (`.crew/verify.json:484`). No hook, no config key, so `plugin/crew/CONFIG.md` is unchanged.
- No crew guide change. `docs/guides/crew/src/*.md` says "any per-language set a changed file matches" and names no
  set (re-check with `grep -n "per-language" docs/guides/crew/src/*.md`). Docs: none there, for that reason.
- No version bump on the build branch (REPO-03, `.crew/standards.md`): set at land, after the review receipt.

## Evidence
origin/main `a555ff37`:
- Format and bar: `plugin/crew/skills/crew-standards/SKILL.md:16-17` ("A plugin standard needs findings from at least
  three distinct reviewed change sets"), `:18-22` (stack sets; "The first is `references/python.md`").
- Loader: `plugin/crew/hooks/scripts/crew_standards.py:76` `PLUGIN_FIELDS`; `:83` `_ID_RE` `^[A-Z]{2,6}-\d{2}$` (so
  `DOTNET-08` is valid); `:146` `parse_set`; `:229` `_applies`; `:236` `_plugin_sets` reads every `references/*.md`;
  `:263` `effective_set`. `crew_ticket.glob_match` `plugin/crew/hooks/scripts/crew_ticket.py:393`.
- The worked example: `plugin/crew/skills/crew-standards/references/python.md` (lead paragraph `:8-20` states the
  counting rule; nine standards; ids keep the research numbering). Tests over shipped sets,
  `plugin/crew/tests/test_crew_standards.py`: `_ADMITTED_PYTHON` `:260`, `_STACK_SETS` `:261` (every `references/*.md`
  but `generic.md`, so the parametrized tests pick up `dotnet.md` with no edit), `test_python_set_parses_with_every_field`
  `:264`, `_change_set_problems` `:273`, `test_every_stack_standard_names_and_cites_three_change_sets` `:292`,
  `test_every_stack_standard_why_states_its_change_set_count` `:307`, `_PYTHON_FINDINGS` `:330`,
  `test_python_why_finding_counts_match_their_enumerations` `:336`, `test_every_stack_set_line_count_is_the_same_by_newline_and_splitlines`
  `:349`, `test_python_sources_quote_whole_spans_without_elision` `:359` (Python only), `test_python_set_applies_to_python_files_only`
  `:372`, `test_shipped_sets_cite_no_machine_local_note` `:381`.
- Sabotage pattern (for the follow-up tooling PR): `plugin/crew/tests/sabotage_standards.py:59` `PYTHON_SET`, entries
  `:434-489`.
- Harness: `scripts/check-tooling-pr.py:58` `HARNESS`, `:79` `"plugin/crew/tests/sabotage*.py"`. L-0539 (the fix) is
  at `direction` in `.work/INDEX.md`, not merged (`gh pr list --search L-0539` shows no PR of its own).
- Stack skill: `plugin/crew/skills/stack-dotnet/SKILL.md` (95 lines; pitfalls `:19-38`; no Standards section).
  Python's shape to copy: `plugin/crew/skills/stack-python/SKILL.md:46` `## Standards`, `:63` `## Candidate standards (not gated)`.
- Research rules: `research/dotnet.md` DOTNET-01 `:82` ... DOTNET-20 `:923`; Earned-by blocks under each; open
  questions `:1007-1022`; quotes "cut with `[...]`" (`:78`) and three pages through a summarising fetch (`:1029-1031`).
- Provisional re-count, 2026-10-05, by `git -C /repos/anew/<repo> log -1 --format=%B <sha>` over every cited commit
  (a commit counts only when its own message records a review round or finding; one SRL ticket or one Vault PR
  counts once; Vault `4dd5a6d`, `7c49dfa` and `9f9fb17` (2026-09-16) have no merge commit on `main` naming a PR,
  so they count once together, "V-0916"):
  - Admitted: **DOTNET-08** 3 (SRL-527 `2a33b2e1` "codex round 4 findings"; SRL-966 `f4acae45` "fix round-1 Codex
    findings"; Vault PR #27 `b75ce4e` "fix round 1"). **DOTNET-13** 4 (SRL-953 `315ac3b7` "Codex round 2 (qa-1195)
    BLOCK"; SRL-1008 `434901ba` "round-2 FIX"; Vault PR #27 `4894446` "Codex FIX"; V-0916 `4dd5a6d`).
    **DOTNET-15** 3 (SRL-966 `1db151cc` "Codex round 2"; Vault PR #28 `d73b0d3` "Review fix round 1"; SRL-953
    `37a0d67a` "Codex round 3 BLOCK").
  - Short, candidates: -01 2 (SRL-966, SRL-740); -02 1 confirmed (SRL-601 `3727f71c` mentions round 1; SRL-574
    `35152d1c` and SRL-887 `db82991e` record no review); -03 0-1 (SRL-628 `4aad30dc` and SRL-774 `996effd4` record
    no review; the security-findings doc is a doc); -04 1 confirmed (SRL-793 `56263837` "Review findings on PR #1068";
    SRL-713/711 `2cc1ca50` and SRL-716 `7f2a6d48` record none); -05 1 (SRL-779); -06 1 (SRL-1063 `9be6db4a`
    "Codex: 1 FIX"; SRL-1062 records none); -07 2 (SRL-968, SRL-653); -09 1 (SRL-966; SRL-487 records none); -10 2
    (SRL-968, SRL-966); -11 2 (SRL-1008, SRL-966); -12 1 (Vault PR #28); -14 2 (SRL-527, SRL-966); -16 1 (SRL-484
    "second codex review"); -17 1 (Vault PR #32 `c96e79a`); -18 1 (V-0916, three commits); -19 2 (Vault PR #27,
    V-0916; SRL-887 records none); -20 1 (SRL-718).
- Owner global rules (`~/.claude/CLAUDE.md`, re-read 2026-10-05): "Always use `var`" with no contrary line;
  "Use `Result<TValue, TError>` for expected failures"; xUnit + NSubstitute + FluentAssertions; `TimeProvider`.
- Docs that describe the sets: `plugin/crew/README.md:795` (names the Python set and "The other stacks (... .NET ...)
  follow"); `plugin/PLUGINS.md:217` (crew-standards row, "Python so far"), `:220` (stack-dotnet row);
  `.crew/codemap/crew.md:1830-1831` ("The first stack set is ... python.md"); `CHANGELOG.md:10` `[Unreleased]`;
  `plugin/crew/BUDGETS.md:10-11` (`crew-markdown-lines` claim).
- Version: `plugin/crew/.claude-plugin/plugin.json:3` is `1.1.0`.

## Unknowns
- **The final admitted list.** The re-count above reads commit messages from the SRL and Vault clones on this host.
  Resolved at implement: the session re-reads every cited commit (`git show -s --format='%h %ad %s%n%b'`), records
  one line per change set in `.work/tickets/L-0535/changesets-dotnet.txt` (rule, name, subject, review evidence,
  PR/ticket), and ships what passes. A rule may move either way: -02, -04 and -18 reach three if commits recorded
  as "no review" are shown to be review fixes (for example by the PR's review thread) or V-0916 is shown to be three
  PRs; -08, -13 or -15 drop if a citation fails. If fewer than one rule passes, stop and report: an empty set is
  refused by the loader (`test_refusal_branch_empty_set`).
- **The SRL and Vault repositories are private.** Accepted as risk, as TheHomeDepot is for PYTHON: each citation
  names the repo, the ticket or PR and the quoted message, so a reader with access can check it.
- **Microsoft Learn quotes.** The research quoted through WebFetch, some via a summariser, and cut quotes with
  `[...]`. Resolved at implement: fetch each Source URL raw (`curl -sL`), strip tags, collapse whitespace, and
  string-match every quoted sentence; record results in `.work/tickets/L-0535/quote-check-dotnet.txt`. A quote
  that does not match is replaced by the page's sentence or dropped, never paraphrased, never elided.
- **Merge train.** L-0532, L-0533 and L-0534 touch the same SKILL.md, README, PLUGINS.md, CHANGELOG and BUDGETS
  lines. Whichever lands first, the others merge main and re-measure. `_STACK_SETS` is a directory listing, so
  sibling sets do not conflict in the tests.
- **The 120-line cap.** Every stack skill is at most 120 lines (`plugin/crew/tests/test_stack_skills.py:73`, `:142`);
  `stack-dotnet` is 95 now, and seventeen candidate lines plus the Standards pointer and conventions do not fit.
  Default taken: the candidate list and the conventions go to `plugin/crew/skills/stack-dotnet/references/candidates.md`,
  and SKILL.md keeps the `## Standards` pointer, a one-line link to the candidates file and the test-framework and
  `Result` defaults.
- The next free crew patch version is set at land.

## Size and split
One new Markdown set (about 150-250 lines for three rules), about 60 lines of tests, about 15 lines in
`stack-dotnet/SKILL.md` and about 40 in its new `references/candidates.md`, a few lines in each doc. No production code. No harness path in this PR (the sabotage
entries are the separate tooling-only PR). No further split.

## Touch
- `plugin/crew/skills/crew-standards/references/dotnet.md` - new, the DOTNET set
- `plugin/crew/skills/crew-standards/SKILL.md` - the stack-sets bullet names the DOTNET set
- `plugin/crew/skills/stack-dotnet/SKILL.md` - `## Standards` pointer, a link to the candidates, test-framework and
  Result guidance; `description:` mentions the set (stays within 120 lines)
- `plugin/crew/skills/stack-dotnet/references/candidates.md` - new: `## Candidate standards (not gated)` and the
  conventions list
- `plugin/crew/tests/test_crew_standards.py` - `_ADMITTED_DOTNET`, `_DOTNET_FINDINGS`, the parse, applies-to and
  finding-count tests; the elision test parametrized over `_STACK_SETS` (unless a sibling slice already did it)
- `plugin/crew/README.md`
- `plugin/PLUGINS.md` - `crew-standards` and `stack-dotnet` rows, version
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json` - version, at land only
- `.claude-plugin/marketplace.json` - version, at land only
- `.crew/codemap/crew.md` - the effective-set bullet names the DOTNET set; re-anchor
- `.crew/codemap/**`, `.claude/rules/**`, `graphify-out/**`, `docs/diagrams/**` - refresh only (standing rule)
- `docs/tickets/L-0535/` - removed in the final PR

Not in Touch: `plugin/crew/tests/sabotage_standards.py` (harness; tooling-only follow-up), `plugin/crew/CONFIG.md`
(no key), `docs/guides/crew/**` (no set named there), `docs/adr/0004-build-time-development-standards.md` (decision 3
already covers per-language files), `.crew/verify.json` (already mapped).

## Acceptance checks
Commands from the repo root; pytest through the heavy-run wrapper on a memory-bound host.
`S` is `plugin/crew/tests/test_crew_standards.py`; run as `python3 plugin/crew/tests/pytest_rule.py S -q -k <name>`.
- [ ] `references/dotnet.md` parses with no problems; set `DOTNET`; `applies-to` exactly
  `["**/*.cs", "**/*.cshtml", "**/*.razor"]`; ids exactly `_ADMITTED_DOTNET` (DOTNET-08, -13, -15, or the list the
  re-count in `changesets-dotnet.txt` gives). `-k test_dotnet_set_parses_with_every_field`
- [ ] Every DOTNET standard names at least three change sets, all cited in its Earned by, and its Why states
  "N findings across M change sets" with M equal to the count. (Existing parametrized tests, now with `[dotnet.md]`.)
  `-k "test_every_stack_standard_names_and_cites_three_change_sets or test_every_stack_standard_why_states_its_change_set_count"`
- [ ] Each Why's finding count equals a hand count of the defects it enumerates, held in `_DOTNET_FINDINGS`.
  `-k test_dotnet_why_finding_counts_match_their_enumerations`
- [ ] The DOTNET set applies to `src/Api/Program.cs`, `Views/Home/Index.cshtml` and `Pages/X.razor`, and not to
  `README.md`, `src/Api/Api.csproj` or `x.cs.bak`. `-k test_dotnet_set_applies_to_csharp_files_only`
- [ ] No Source quote in any stack set is cut with `[...]` (the Python test parametrized over `_STACK_SETS`, its
  `[python.md]` case still green). `-k test_every_stack_set_quotes_whole_spans_without_elision`
- [ ] Shipped sets cite nothing machine-local, and line counts agree by `\n` and `splitlines()`.
  `-k "test_shipped_sets_cite_no_machine_local_note or test_shipped_sets_cite_nothing_local_only or test_every_stack_set_line_count_is_the_same_by_newline_and_splitlines"`
- [ ] Each new test was sabotaged by hand once (narrow `applies-to` to `["**/*.csx"]`; rename an admitted heading to
  a candidate id; change one Why count; insert `[...]` in a Source) and went red; the four mutations and the red
  test names are in the PR body for the tooling-only follow-up to commit.
- [ ] `.work/tickets/L-0535/changesets-dotnet.txt` and `quote-check-dotnet.txt` exist and every shipped citation
  and quote is in them, found.
- [ ] `stack-dotnet/SKILL.md` names `crew-standards/references/dotnet.md`, lists the admitted ids with names, links
  `references/candidates.md`, and states the test-framework and `Result` defaults; it stays within 120 lines
  (`python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_stack_skills.py -q`). `references/candidates.md`
  lists every other research rule with `(<N>` count and the conventions with no id; no id is in both.
  `grep -n "references/dotnet.md\|candidates.md" plugin/crew/skills/stack-dotnet/SKILL.md`
- [ ] Existing suites: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_standards.py plugin/crew/tests/test_review_run_standards.py plugin/crew/tests/test_stack_skills.py plugin/crew/tests/test_lifecycle_commands.py -q`
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK` (no harness path in the diff).
- [ ] Docs: README `:795`, PLUGINS.md rows, `crew-standards/SKILL.md`, `.crew/codemap/crew.md` name the DOTNET set;
  CHANGELOG entry flags the behaviour change (a C# change now answers DOTNET rows; in-flight stamps go stale);
  BUDGETS.md re-measured; crew bumped to the next free patch at land; `python3 scripts/check-marketplace.py` passes
  after the commit.
- [ ] Refresh: `python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check` and
  `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket L-0535` pass.

## Dependencies
- T-0086 (Python slice, PR #282): merged. Pattern, tests and sabotage scaffolding are on main.
- L-0539 (check-tooling-pr.py admits a feature's own sabotage entries): not merged. Not a blocker under Option 1;
  if it lands first, the sabotage entries ride along.
- Siblings L-0532, L-0533, L-0534 (and L-0536, L-0537, L-0538): independent files, shared doc lines; land one at a
  time through the merge train.
- Follow-up: a tooling-only ticket for the DOTNET sabotage entries (id minted by the coordinator).

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05. Plan: to be written by the implementing session.
