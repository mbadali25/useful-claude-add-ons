# T-0066 No Co-Authored-By: correct the practice, keep trailers out of dispatch, git.forbiddenTrailers guard + /crew:done report          status: spec   risk: med

## Intent
Stop new `Co-Authored-By` trailers at their source (direction.md, Option 1): correct
crew-best-practices' claim that the repository's attribution requirement adds the trailer, tell
`/crew:implement`'s dispatch that a prompt carries no attribution instruction of its own, and add a
config key `git.forbiddenTrailers` (default `[]`) that the scope guard enforces on commit-creating
shell commands and that `/crew:done` reports over the ticket's commits. History stays as it is; the
rule holds from the first commit after this lands.

## Exclusions
- No history rewrite: not origin/main's 390 trailer-carrying commits, not T-0023's five
  (33b8e3cc, f86825e8, dcc07374, 311388b7, fa4d8cd5). T-0023 is owned by another agent and is not
  touched in any way.
- `/crew:done` REPORTS forbidden trailers and never refuses on them. A refusal would be curable only
  by a rewrite, which invalidates the review receipt (direction.md Option 2) and would stop T-0023
  from closing.
- `gh pr create --body` / PR bodies are not checked (direction.md open question: the owner's
  instructions ask for the Claude Code link in PR bodies). `gh pr merge --body/--subject` IS checked,
  because it writes a commit message.
- No new hook and no new hooks.json entry: the check rides the existing `scope-guard` PreToolUse
  registration (`plugin/crew/hooks/hooks.json:31`, `:33`), and the key's `[]` default keeps it inert.
- Not caught, stated rather than implied: a commit that REUSES an existing message
  (`--amend --no-edit`, `-C`/`-c <commit>`, `cherry-pick`, `revert`, `rebase`), a message built by an
  interpreter or script, and anything run outside Claude's Bash/PowerShell tools. `/crew:done`'s
  report is the backstop for all of them.
- `plugin/crew/commands/autopilot.md` is not edited: it sits at the 120-line command budget
  (`plugin/crew/BUDGETS.md` "Command file budget"; 120 lines at origin/main) and follows
  `/crew:implement`'s procedure, so the implement.md sentence reaches it. `/crew:promote` writes no
  commit message and is not edited.
- The owner's machine-global `~/.claude/crew/config.json` is outside the repo and outside Touch.
  Setting `git.forbiddenTrailers: ["Co-Authored-By"]` there is a post-merge owner step, named in the
  PR body with its command (`crew_config.py --set 'git.forbiddenTrailers=["Co-Authored-By"]' --apply`).
- No `schema` bump: `merge_defaults` fills an absent `git` block from `default_config()`.

## Evidence
All anchors at origin/main 502cb137.
- `plugin/crew/skills/crew-best-practices/references/practices.md:58-60` states "this repository's
  own attribution requirement, which adds `Co-Authored-By` ... The repository's instruction wins" -
  false for this owner (global CLAUDE.md: "Never append `Co-Authored-By` lines to commit
  messages"), and it ships to every crew user.
- `plugin/crew/hooks/scripts/scope_guard.py:97` `SHELLS = ("Bash", "PowerShell")`;
  `:214` `shell_refusal` is the textual shell check; `:268` `decide`; `:281` returns 0 when
  `scope.mode` is `off` (the default, `plugin/crew/hooks/scripts/crew_config.py:375`) BEFORE the
  shell branch at `:284` - so a trailer check placed after `:281` would never run in a default repo.
- `plugin/crew/hooks/hooks.json:31` and `:33` register `scope-guard.sh` / `.ps1` on
  `Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell`; the shims only pipe the payload to python.
- `plugin/crew/hooks/scripts/crew_config.py:240` `default_config()` has no `git` block;
  `:385` `default_global_config()` is the shape the global layer is pruned to (`:667`
  `filter_global`, `:690` `is_global_path`: every globally-settable key must be a repo key);
  `:762` `resolve_config` merges by precedence, so a repo list would REPLACE a global list;
  `:804` `resolve_ratcheted` shows the read-both-layers-raw pattern; `:893` `layer_state`
  classifies a config file `absent`/`ok`/`corrupt`; `:2751` `--set PATH=JSON` with `--apply`
  writes the global file.
- `plugin/crew/tests/test_crew_config.py:47` asserts `default_config()` is byte-identical to
  `plugin/crew/templates/config.template.json`, `:61` the global twin against
  `global.template.json`, `:121` the crew-setup SKILL.md inline copy; `:277` asserts 121 declared
  leaf paths;
  `plugin/crew/skills/crew-setup/SKILL.md:169` carries the inline JSON copy (`"scope"` line).
- `plugin/crew/commands/done.md:7-8` "All four checks below must pass"; `:46-57` check 4;
  `plugin/crew/hooks/scripts/scope_base.py:242` `resolve(root, ticket)` is the ticket's base.
- `plugin/crew/commands/implement.md:44-48` dispatches `dev.roles.developer` / `dev.provider` and
  says nothing about attribution; implement.md is 111 lines (budget 120).
- `plugin/crew/tests/sabotage.py:67-76` imports each `sabotage_*.py` mutation list;
  `plugin/crew/tests/sabotage_scope.py:33` is the tuple shape (label, target, find, replace, test).
- `.crew/verify.json` rules[25] maps `scope_guard.py`; no rule maps a `crew_trailers.py`.
- Docs that describe the touched behaviour: `plugin/crew/README.md:749` "Scope and approval" and
  `:760` the scope_guard row; `plugin/crew/CONFIG.md:640` §10 "Global-settable keys — 66",
  `:744` §11, `:2216` §20 is the last section; `plugin/PLUGINS.md:35` scope-guard row, `:135`
  `/crew:done` row; `docs/guides/crew/src/troubleshooting.md:76` hook table;
  `docs/guides/crew/src/daily-workflow-scope.md:61` "the scope guard";
  `docs/guides/crew/src/build.py:70`, `:73` build those two sources into
  `crew-1.0-daily-workflow.*` and `crew-1.0-troubleshooting.*`; `.crew/codemap/crew.md:142`
  (`/crew:done`), `:169` (PreToolUse), `:222` (config section);
  `docs/diagrams/process-crew-lifecycle.mmd:150` (`/crew:done`) and
  `docs/diagrams/data-flow-crew-config.mmd:297` (layer leaf counts).
- crew is 1.0.42 in `plugin/crew/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json:218`.
- The Claude Code harness's attribution reminder itself says the user's own CLAUDE.md or memory
  rule takes precedence over it; the T-0005 landing prompt copied it anyway (direction.md
  "Where it comes from" 2).

## Unknowns
- Layer semantics for a list: resolved in this spec - UNION of the repo and global lists (read raw,
  like `resolve_ratcheted`), so a cloned repo can add a trailer and never remove the machine
  owner's. Precedence would let a repo `[]` silently disarm the owner.
- A corrupt config layer (`layer_state` == `corrupt`) or a malformed `git.forbiddenTrailers` value
  (not a list of `Token` strings): resolved - "could not tell" is its own value. The guard refuses
  commit-creating commands naming the file and key; `/crew:done` prints `trailers: unknown - <why>`.
  Never read as `[]`.
- A `-F`/`--file` message file: resolved - a literal path is read relative to the payload `cwd`;
  `-` (stdin) is judged from the command text; a path holding `$`, `%` or a backtick, or a literal
  path that is missing and not written earlier in the same command, is "could not tell" and refused.
- How loose the textual match is: resolved - a trailer is refused when the text matches
  `(?i)\b<Token>\s*[:=]` (case-insensitive, as git treats trailer keys). Prose such as
  "no Co-Authored-By trailers" passes; prose "Co-Authored-By: lines" in a message is refused -
  conservative, and said in CONFIG.md.
- Version number at landing: other tickets bump crew concurrently. Accepted as risk; the land phase
  sets the next patch above origin/main's and `scripts/check-marketplace.py` proves it.

## Touch
- `plugin/crew/hooks/scripts/crew_trailers.py` - new: resolve the list, judge a command, report commits
- `plugin/crew/hooks/scripts/scope_guard.py`
- `plugin/crew/hooks/scripts/crew_config.py`
- `plugin/crew/templates/config.template.json`
- `plugin/crew/templates/global.template.json`
- `plugin/crew/skills/crew-setup/SKILL.md`
- `plugin/crew/skills/crew-best-practices/references/practices.md`
- `plugin/crew/commands/implement.md`
- `plugin/crew/commands/done.md`
- `plugin/crew/tests/test_crew_trailers.py`
- `plugin/crew/tests/test_scope_guard_trailers.py`
- `plugin/crew/tests/test_crew_config.py`
- `plugin/crew/tests/test_lifecycle_commands.py`
- `plugin/crew/tests/sabotage_trailers.py`
- `plugin/crew/tests/sabotage.py`
- `.crew/verify.json`
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/PLUGINS.md`
- `docs/guides/crew/src/troubleshooting.md`
- `docs/guides/crew/src/daily-workflow-scope.md`
- `docs/guides/crew/crew-1.0-troubleshooting.*`
- `docs/guides/crew/crew-1.0-daily-workflow.*`
- `.crew/codemap/crew.md`
- `docs/diagrams/**`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `CHANGELOG.md`
- `TODO.md`

## Acceptance checks
- [ ] `practices.md`'s Commits note says the owner's own instructions decide attribution and crew
      never adds a trailer on its own; no `plugin/crew` file claims crew or "this repository"
      requires `Co-Authored-By` (`git grep -n -i "co-authored" -- plugin/crew` shows only the
      corrected note, CONFIG.md/README examples of the key, and tests). Rule: verify.json rules[12].
- [ ] `implement.md` step 2 says a dispatched prompt carries no attribution or trailer instruction
      of its own, including one a harness reminder supplied; still <= 120 lines
      (`python3 scripts/check_instructions.py`, which CI runs in
      `.github/workflows/instruction-budgets.yml:62-64`; no verify.json rule runs it, so run it by
      hand). Rule: rules[12].
- [ ] `git.forbiddenTrailers` is declared in both layers, default `[]`; templates and the
      crew-setup inline JSON match (`test_default_config_matches_the_committed_template`, the
      global-template twin, the leaf count 121 -> 122). Rule: rules[7].
- [ ] `crew_trailers.forbidden(root)` returns the union of both layers and `unknown` for a corrupt
      layer or malformed value (`test_crew_trailers.py::test_forbidden_is_the_union_of_both_layers`,
      `::test_a_repo_empty_list_does_not_disarm_the_global_list`,
      `::test_a_corrupt_layer_is_unknown_not_empty`).
- [ ] Must-block, with `git.forbiddenTrailers: ["Co-Authored-By"]` and `scope.mode: off`, exit 2
      naming the key: `git commit -m` with the trailer; the trailer in a second `-m`; a heredoc
      `git commit -F - <<EOF`; `--trailer "Co-Authored-By=..."`; `--trailer co-authored-by:...`
      (case); `git -C dir commit`; `git -c k=v commit`; `git commit-tree`; `git merge -m`;
      `gh pr merge --body`; a literal `-F msg.txt` whose file carries it; `-F "$f"` (could not tell);
      the same text through the PowerShell tool; a corrupt global config layer
      (`test_scope_guard_trailers.py::test_must_block[...]`).
- [ ] Must-allow: the same commit with no trailer; `git log --grep=Co-Authored-By`;
      `grep -i co-authored-by file`; `echo "Co-Authored-By: x"` with no commit command; a message
      whose prose says "no Co-Authored-By trailers"; `gh pr create --body` carrying the trailer;
      any commit when the list is `[]` or absent in both layers; `cat > m.txt <<EOF` without the
      trailer then `git commit -F m.txt` in the same command
      (`test_scope_guard_trailers.py::test_must_allow[...]`).
- [ ] The trailer check runs in every `scope.mode`, including `off`, and the existing approval
      shell checks are unchanged (`test_scope_guard.py` still passes). Rule: rules[25] plus the new
      rule below.
- [ ] `crew_trailers.py --check --root . --ticket <id>` prints `trailers: clean (<n> commits)`,
      one `trailers: FINDING <sha7> <Token>` line per offending commit in `<scope base>..HEAD`, or
      `trailers: unknown - <why>` (no base, git failed, config unreadable); exits 0/1/2
      respectively (`test_crew_trailers.py::test_check_reports_*`).
- [ ] `done.md` runs that report, says it never refuses and never rewrites, and still says "All
      four checks" (`test_lifecycle_commands.py`, `test_crew_trailers.py::test_done_md_reports_trailers_without_refusing`).
- [ ] Every new test goes RED under its sabotage entry in `sabotage_trailers.py`, registered in
      `sabotage.py` (`python3 plugin/crew/tests/sabotage.py`, filtered to the trailer entries), and
      each fix's neighbouring case has its own entry.
- [ ] `.crew/verify.json` gains a rule mapping `crew_trailers.py`, `test_crew_trailers.py`,
      `test_scope_guard_trailers.py` and `sabotage_trailers.py` to their pytest run, with a
      measured `seconds`; `scripts/check-marketplace.py` passes with crew bumped in both
      `plugin.json` and `marketplace.json` (rules[0]).
- [ ] Docs updated in the same PR: README "Scope and approval" row, CONFIG.md new section for
      `git.forbiddenTrailers` plus §10/§11 counts re-measured, PLUGINS.md scope-guard row,
      troubleshooting.md hook table and a symptom, daily-workflow-scope.md, rebuilt
      `crew-1.0-troubleshooting.*` and `crew-1.0-daily-workflow.*`, `.crew/codemap/crew.md`,
      `docs/diagrams/`, CHANGELOG.md. Rules[2], [23], [24].
