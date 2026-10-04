# T-0083 vault recall relevance, slice 1: the obsidian-vault recall CLI skips excluded folders, applies a relevance floor, ranks durable notes first and accepts a project          status: spec   risk: med
## Refreshed 2026-10-04
First spec for this ticket; there was no spec.md or plan.md before. Written against origin/main `155fe6d8` (crew 1.0.322, obsidian-vault 0.4.16) from direction.md and its "Direction check 2026-10-04". Not approved: the owner was unavailable, so every open choice takes the recommended option and is listed under "Open questions for the owner".

The ticket is split into three slices (see "Size and split"). This file is slice 1, the CLI. The crew side is L-0675 (`children/1/`) and its sabotage mutations are L-0676 (`children/2/`).

## Intent
`vault_ops.py recall` stops returning off-topic notes. It never reads the vault's excluded folders (archived sessions first of all), it ignores stop words and returns nothing when too few query terms match, and within a vault it ranks the caller's project first and concept and decision notes above session notes. An empty answer is a correct "no hit". crew gets the archive, floor and note-kind fixes from this slice with no crew change, because it already calls this CLI.

## Exclusions
- No file under `plugin/crew/` changes. Passing the project from crew is L-0675.
- No change to vault priority: every hit in an earlier vault still ranks above every hit in a later one, and the `--max-chars` budget rule is unchanged.
- No change to the text line format (`[vault] path: snippet`), to the existing JSON keys, or to the exit codes. New JSON keys are additions.
- No embedding, index, cache or network call. The CLI stays a read-only walk (vault_recall.py:5).
- No write to any vault, and no edit to a vault's `.obsidian/app.json`. It is read only.
- Regex entries in `userIgnoreFilters` (written `/.../`) are not applied. They are counted and reported, never guessed at.
- The filter never drops a note for having no project. A note of another project is ranked last, not dropped.
- No change to capture, gardening, import, the guard, or the note templates. Sessions do not gain a `project:` key here.
- Nothing of T-0084 (native memories as pointers into the vault).

## Design
All in `plugin/obsidian-vault/hooks/scripts/vault_recall.py`.

1. **Excluded folders.** A vault-relative path is excluded when it starts with `wiki/sessions/archive/`, or with a plain entry of that vault's `.obsidian/app.json` `userIgnoreFilters`. A plain entry is a string that does not start with `/`; it is compared as a path prefix, with a trailing `/` added when missing. `iter_notes` prunes excluded directories, so they are not read at all. `app.json` missing, unreadable, not JSON, or with a non-list value means "no vault filters", and the built-in prefix still applies. `--include-excluded` turns the whole rule off.
2. **Stop words.** `terms_of` drops a small built-in English stop-word list (a frozenset constant) and any term shorter than three characters, then keeps the first 12 as today. A query that is only stop words has no terms and returns no results, exit 0.
3. **Relevance floor.** `matched` is the number of distinct query terms found anywhere in the note (title, headings or body). A note is a hit only when `matched >= need`. `need` is 1 for one or two terms, 2 for three to five, 3 for six or more. `--min-terms N` sets `need` to `min(N, number of terms)`; `--min-terms 1` restores today's behaviour.
4. **Note kind.** From the vault-relative path: `concept` under `wiki/concepts/`, `decision` under `wiki/decisions/`, `session` under `wiki/sessions/`, else `other`. Rank order: concept and decision (0), other (1), session (2).
5. **Project.** `--project NAME[,NAME...]` (repeatable). Names are compared case-insensitively after trimming. A note is `match` when its frontmatter `project:` value equals a name, or a directory component of its path equals a name. It is `other` when its frontmatter `project:` is non-empty and equals no name. Otherwise it is `none`. Rank order: match (0), none (1), other (2). Without `--project` every note is `none`. The `project:` value is read from the frontmatter block the module already parses (vault_recall.py:62-68): one scalar line, optional quotes, nothing else.
6. **Order.** Vault priority, then project rank, then kind rank, then score descending, then path. `search_vault` returns its hits in that order; `recall` keeps appending vault by vault as today.
7. **JSON additions.** Each result gains `kind`, `project` (`match`, `none` or `other`) and `matched`. The top level gains `project` (the names asked for, a list), `need`, `below_floor` (notes that scored but missed the floor), `excluded_dirs` (directories pruned) and `skipped_filters` (regex `userIgnoreFilters` entries not applied).

This changes default results for every caller. It is flagged as a behaviour change in the CHANGELOG, and obsidian-vault takes a minor bump.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/obsidian-vault/hooks/scripts/vault_recall.py:40 `SKIP_DIRS` has no archive entry. :50-56 `terms_of` keeps every term of two or more characters, first 12. :59-78 `split_note` reads only `title` from the frontmatter. :81-97 `score_note`. :110-115 `iter_notes` prunes only `SKIP_DIRS` and dot directories. :135 the only filter is `score <= 0`. :139 sort is score, then path. :153-199 `recall`; :197-199 the JSON keys. :222-231 `add_parsers`, four options.
- plugin/obsidian-vault/hooks/scripts/vault_ops.py:76 imports `vault_recall`; :1836 registers its parser. No other caller: `git grep -n vault_recall origin/main -- plugin scripts` shows only vault_ops.py (:24, :76, :1836).
- plugin/crew/hooks/scripts/crew_recall.py:244-245 the argv crew sends. :153-160 `_items` reads `results`; :195-197 reads `vault`, `path`, `snippet`. Unknown keys are ignored, so the JSON additions are safe for crew 1.0.322. :209 crew re-sorts by vault priority and CLI rank, so the CLI's order inside a vault survives.
- plugin/obsidian-vault/templates/concept.md:15 `project:` is a concept key. plugin/obsidian-vault/templates/session.md and decision.md have no project key.
- plugin/obsidian-vault/skills/obsidian-memory-contract/profiles/memory-vault.md:18-22 the folder layout (`wiki/concepts/`, `wiki/sessions/`, `wiki/decisions/`); no archive line. :47 "`vault_ops.py recall` scores the title highest".
- plugin/obsidian-vault/hooks/scripts/vault_garden.py:167 `SESSIONS_DIR = "wiki/sessions"`, the one existing place the layout is in code.
- `userIgnoreFilters` appears nowhere on origin/main (`git grep -n userIgnoreFilters origin/main` prints nothing).
- Tests: plugin/obsidian-vault/hooks/scripts/_test/test_memory_ops.py:320-375 `_t_recall`. Its queries are `port collision` (two terms) and `port` (one), and the `beta` note matches only `port`. With `need` 1 for one or two terms, that case passes unchanged. :1350 the case list. The file is a plain script (1372 lines), run by plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:483 and by .github/workflows/shell-suites.yml:75-76.
- `.crew/verify.json` has no rule that runs the obsidian-vault suite for a `vault_recall.py` change. Its only obsidian-vault path is the pwsh-isolation guard at :501.
- Docs that state the ranking: plugin/obsidian-vault/README.md:230-246 (CLI and ranking) and :248-260 (JSON example); plugin/obsidian-vault/skills/obsidian-setup/SKILL.md:32; docs/guides/crew/src/memory-recall-proof.md:47-54; docs/guides/crew/src/troubleshooting.md:393-404 ("recall never surfaces anything you know is in the vault"); .crew/codemap/obsidian-vault.md:82 and :414-417.
- Versions: plugin/obsidian-vault/.claude-plugin/plugin.json:3 `0.4.16`; .claude-plugin/marketplace.json:242; plugin/PLUGINS.md:601.
- Harness: scripts/check-tooling-pr.py:58-87 `HARNESS`. No path in Touch below is on it.

## Unknowns
- The floor thresholds (1, 2, 3) are a judgement, not a measurement. Resolved at implement: run the new CLI by hand over a real vault with five recent prompts and record hits before and after in the PR body. Not a gate.
- The stop-word list's contents. Resolved at implement: a fixed list of about 60 common English words; the test pins five of them. Accepted as risk that a stop word is sometimes the meaningful term; `--min-terms 1` does not bring it back, a quoted exact search is out of scope.
- Whether every Obsidian version writes plain `userIgnoreFilters` entries as vault-relative prefixes. Resolved at implement by reading one real `app.json`. If the shape differs, only the built-in prefix ships and the filter part becomes a follow-up.
- A directory component equal to the project name can be a coincidence (a topic folder with the same name). Accepted as risk: it only promotes, never hides.
- The walk reads `app.json` once per vault per call. Cost is one small file; accepted.
- The exact next free obsidian-vault version is set at implement time.

## Touch
- `plugin/obsidian-vault/hooks/scripts/vault_recall.py`
- `plugin/obsidian-vault/hooks/scripts/_test/test_memory_ops.py`
- `plugin/obsidian-vault/README.md`
- `plugin/obsidian-vault/skills/obsidian-setup/SKILL.md`
- `plugin/obsidian-vault/skills/obsidian-memory-contract/profiles/memory-vault.md`
- `plugin/obsidian-vault/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `docs/guides/crew/src/memory-recall-proof.md`
- `docs/guides/crew/src/troubleshooting.md`
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by the guide build script
- `.crew/codemap/obsidian-vault.md`
- `.crew/verify.json` - one new rule mapping vault_recall.py to its suite

Not in Touch, stated: anything under `plugin/crew/` (L-0675); `plugin/obsidian-vault/hooks/scripts/vault_ops.py` (the parser is registered through `vault_recall.add_parsers`); `plugin/obsidian-vault/agents/reflector.md` (it does not call the CLI); `docs/diagrams/` (no box or edge changes).

## Acceptance checks
Commands run from the repo root. The suite is a plain script; it prints `RESULT: 0 failed` and exits 0. New cases go in a new `_t_recall_relevance` function added to the case list at test_memory_ops.py:1350; each bullet names the `check` label to add.
- [ ] Whole suite: `python3 plugin/obsidian-vault/hooks/scripts/_test/test_memory_ops.py` exits 0, and `bash plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh` exits 0. The existing `_t_recall` checks pass with no edit to their expectations.
- [ ] `archived session is never returned`: a vault with `wiki/sessions/archive/2026-07/Session - x.md` matching every query term and no other match returns `results == []`, exit 0, `excluded_dirs >= 1`.
- [ ] `--include-excluded reads the archive`: the same vault and query with the flag returns that note.
- [ ] `userIgnoreFilters prefix is honoured`: `.obsidian/app.json` with `{"userIgnoreFilters": ["private/"]}` hides `private/n.md`; a regex entry `"/tmp.*/"` hides nothing and gives `skipped_filters == 1`; a broken `app.json` still applies the built-in prefix and exits 0.
- [ ] `stop words are not terms`: the query `what is the port for this` gives `terms == ["port"]`; the query `what is the` gives `terms == []`, `results == []`, exit 0.
- [ ] `floor drops a one-word match`: with the query `bridge port collision`, a note containing only `port` is absent and `below_floor == 1`; a note containing `port` and `collision` is present with `matched == 2`. With `--min-terms 1` both are present.
- [ ] `concept outranks a higher-scoring session`: in one vault, `wiki/sessions/Session - a.md` scores higher than `wiki/concepts/c.md`; the concept is first and carries `kind == "concept"`. A `wiki/decisions/` note ranks with concepts.
- [ ] `project match ranks first`: with `--project crew`, a concept with `project: crew` precedes a higher-scoring concept with no project, which precedes one with `project: other`. All three are returned. `--project CREW` gives the same order.
- [ ] `project by folder`: a note at `wiki/concepts/acme/crew/n.md` with no `project:` key is `match` for `--project crew`.
- [ ] `no project never hides a note`: with `--project crew` and one concept that has no `project:` key and no matching folder, that concept is returned with `project == "none"`.
- [ ] `the direction's case`: with `--project crew`, a crew concept note and an archived session note of another project that both match, only the concept is returned.
- [ ] `vault priority still wins`: with `--vaults beta,alpha`, a session hit in `beta` precedes a project-matching concept in `alpha`.
- [ ] `recall is still read-only`: the tree snapshot of every fixture vault is identical before and after all of the above, `.obsidian/app.json` included.
- [ ] Sabotage, by hand, each recorded in `.work/tickets/T-0083/sabotage.md` as mutation, red check label, green on restore: (a) `iter_notes` stops pruning excluded directories; (b) the floor compares against 1; (c) stop words are kept; (d) kind rank is dropped from the sort key; (e) project rank is dropped from the sort key; (f) a note of another project is dropped instead of ranked last; (g) a regex filter entry is applied as a prefix.
- [ ] `.crew/verify.json` gains a rule: paths `plugin/obsidian-vault/hooks/scripts/vault_recall.py` and `plugin/obsidian-vault/hooks/scripts/_test/test_memory_ops.py`, run `python3 plugin/obsidian-vault/hooks/scripts/_test/test_memory_ops.py`, `reach: local`, `seconds` measured. `python3 -c "import json;json.load(open('.crew/verify.json'))"` exits 0.
- [ ] Docs: README.md:230-260 states exclusion, stop words, the floor, kind and project order, the three new options and the new JSON keys; obsidian-setup SKILL.md:32 shows `--project`; memory-vault.md's layout names `wiki/sessions/archive/` as never recalled; memory-recall-proof.md and troubleshooting.md say an empty recall can be the floor and name `--min-terms 1` and `--include-excluded` as the way to check; the guide outputs are rebuilt with `python3 docs/guides/crew/src/build.py`; .crew/codemap/obsidian-vault.md describes the new ranking with a fresh anchor.
- [ ] Version: obsidian-vault is bumped in plugin.json, marketplace.json and PLUGINS.md:601, with a CHANGELOG entry that says "behaviour change: default recall results". After the commit, `python3 scripts/check-marketplace.py` passes.
- [ ] `python3 -m pylint plugin/obsidian-vault/hooks/scripts/vault_recall.py` reports no new message, and the ruff no-new-findings check against the merge base is clean.

## Size and split
- Estimate for this slice: about 135 added production lines, all in `vault_recall.py` (exclusion and `app.json` read about 35, stop words and floor about 30, kind and project about 35, ordering, JSON keys and three parser options about 35). Under the 300-line rule.
- It holds one small new reader (the `userIgnoreFilters` list and the `project:` scalar share the existing frontmatter and JSON reads) and no fail-closed state machine.
- The whole ticket is about 205 production lines, under 300, but it is split anyway for two reasons. The crew side needs sabotage mutations in `plugin/crew/tests/sabotage_context.py`, which is harness (scripts/check-tooling-pr.py:78) and cannot ride with the `crew_recall.py` change. And the CLI slice is useful alone and touches a different plugin with its own version.
  - T-0083 (this spec): the CLI. No crew file.
  - L-0675: crew passes `--project`, with a clean fallback on an older CLI. About 70 production lines.
  - L-0676: the sabotage mutations for L-0675. Tooling-only, no production lines.

## Dependencies
Must land first: none open.
- T-0021 (merged): Obsidian support in crew; context only.
- T-0087 (merged): the tooling-PRs-land-alone rule that shapes the split.
- The 1.0.25 redesign (`6c497a14`, on main): introduced `vault_recall.py` and `crew_recall.py`.

Related, no order forced:
- T-0084 (direction): native memories become pointers into vault notes. It makes recall quality matter more; it does not need this ticket to land first.
- T-0507 (direction): refreshes the code maps, `obsidian-vault.md` included. Whichever lands second re-anchors.

Blocks: L-0675 (needs `--project`), and through it L-0676.

## Open questions for the owner
Each has a default already taken above.
1. Another project's notes: rank last (taken), or drop them when `--project` is given?
2. Excluded folders: the built-in archive prefix plus the vault's plain `userIgnoreFilters` entries (taken), or the built-in prefix only?
3. Floor thresholds 1, 2, 3 by term count (taken), or a stricter or looser rule?
4. Version: minor bump to 0.5.0 because default results change (taken), or a patch bump?
5. direction.md's "Ask" names two other projects by short name. Replace them with "other projects" before publishing? Recommended: yes.

## Split
- L-0675 (child 1 of T-0083, filed 2026-10-04): crew passes the repo's project to vault recall and falls back cleanly on an older CLI
- L-0676 (child 2 of T-0083, filed 2026-10-04): sabotage mutations prove the recall project tests (tooling-only)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
