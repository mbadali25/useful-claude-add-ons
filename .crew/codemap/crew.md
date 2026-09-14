anchor: useful-claude-add-ons@975480b7
verified: 2026-09-14
Narrow pass, not a re-derivation: only the "Where every live count of crew's
shape agrees" table (below) was re-read against its cited files at this
anchor, because `f12003e2` (#166, "fix three stale self-describing counts")
landed between the previous anchor and this one and changed three of the four
places that table quotes. Everything else in this note carries forward from
`0a9d8937` unread.


# crew

The `crew` plugin: a virtual dev team of context-isolated agents, slash
commands, bundled skills, and deterministic hooks. Registered in
`.claude-plugin/marketplace.json` like every other entry here.

## Re-derivation provenance — a573ca24 -> 0a9d8937, 2026-09-14

`git diff --name-only a573ca24..HEAD -- <the 19 repo paths this note cites>`
returns eleven: `plugin/PLUGINS.md`, `plugin/README.md`, `plugin/crew/CONFIG.md`,
`plugin/crew/hooks/scripts/_common.sh`,
`plugin/crew/hooks/scripts/_test/run-tests.sh`,
`plugin/crew/hooks/scripts/crew_config.py`,
`plugin/crew/hooks/scripts/crew_state.py`,
`plugin/crew/hooks/scripts/pm_brief.py`,
`plugin/crew/tests/test_guard_bypasses.py`,
`plugin/crew/tests/test_promote_gate_fails_closed.py` and
`scripts/install-prerequisites.sh`.

**The eight files that did NOT change are closed by that result, not by
re-walking them:** `.claude-plugin/marketplace.json`,
`plugin/crew/hooks/hooks.json`, `plugin/crew/hooks/scripts/crew_endpoints.py`,
`plugin/crew/agents/pm.md`, `plugin/crew/commands/work.md`,
`plugin/gizmoduck/commands/report.md`, `plugin/gizmoduck/commands/scan.md` and
`.crew/config.json`/`.crew/metrics.md` (both machine-local; `git diff` against
them is a no-op either way since neither is tracked). Every citation into the
unchanged files — `crew_endpoints.py`'s interior ranges included — is current
because the file is byte-identical to the anchor those ranges were taken at.

**This pass inverts the previous one's population.** At `a573ca24` eight files
were unchanged and this section could mostly cite the per-path check. Here,
`crew_state.py` was split (`crew_freshness.py` is new, `crew_config.py` grew by
roughly 900 lines, `pm_brief.py` moved), so nearly every coordinate this note
carries into those three files had to be re-taken from an AST walk or a direct
read, not carried forward. Only the sections resting on `crew_endpoints.py`,
`hooks.json`, `pm.md` and `work.md` could lean on the per-path check this time.

**Corrections this pass made that are not line-number drift — read these even
if you skip the rest:**

1. **`behind` was never gated on the fixpoint check in the way this note
   described.** The three-state table below said `behind` means "resolves,
   but is not HEAD." At this anchor `read_knowledge`
   (`plugin/crew/hooks/scripts/crew_freshness.py:451`) only appends to `behind`
   when `_moved_since(...) is not False` — i.e. the anchor is old *and* the
   paths the map cites actually moved. `read_diagrams` does the same at
   `plugin/crew/hooks/scripts/crew_freshness.py:522`. This is not new code —
   it is the fixpoint fix from crew 0.19.34 (`1767790`, "knowledgeBehind and
   diagramsStale had no fixpoint") — but the previous version of this note
   never updated its own description of the state machine to match. A reader
   who trusted the table would re-check a map the moment it stopped being
   HEAD, not the moment something it cites actually moved.
2. **`_widens` is no longer "two ratcheted keys," and the guard machinery it
   ratchets is not in `crew_state.py` at all.** The previous version said
   `install.policy` becoming a second ratcheted key was the whole story. At
   this anchor `_RATCHETED` (`plugin/crew/hooks/scripts/crew_config.py:2140`)
   holds `pm.authority`, `install.policy`, one entry per guard in
   `GUARD_NAMES` (four: `terraformApply`, `forcePush`, `adminMerge`,
   `mergeGate`), one per `PROD_GUARD_NAMES` (two: `prodDatabase`,
   `prodServer`), and `change.requireForProduction` — nine ratcheted keys, not
   two. `_widens` itself moved to `:2043`. **A second split this note had not
   previously accounted for:** `GUARD_NAMES`, `PROD_GUARD_NAMES`,
   `guard_policy_rank`, `prod_level_rank`, `install_policy_rank`,
   `require_change_rank` and their `normalise_*` counterparts are all defined
   in `plugin/crew/hooks/scripts/crew_guards.py` (888 lines, new within this
   diff range — introduced in `68c1f93a`, crew 0.19.30, confirmed an
   ancestor-descendant of `a573ca24` by `git merge-base --is-ancestor`), not
   in `crew_state.py`. `plugin/crew/hooks/scripts/crew_state.py:63-88`
   re-exports them, which is why
   `crew_config.py` reaches them as `crew_state.GUARD_NAMES` etc. and why a
   grep of `crew_state.py` alone for `def guard_policy_rank` finds nothing.
   See "Config, and what a machine-global file may supply" below.
3. **The `--worktree-path` CLI branch does not import `crew_config`.** The
   previous "Calls out to" section said it did. At this anchor
   (`plugin/crew/hooks/scripts/crew_state.py:2767-2772`) that branch calls
   plain `load_config(root)`. The deferred `import crew_config` /
   `crew_config.resolve_config` pattern belongs to a *different* branch of
   `main`, `--archive-stale-handoff`
   (`plugin/crew/hooks/scripts/crew_state.py:2780-2782`). `crew_config.py`
   itself contains no reference to `worktree_path`/`worktree_root` at all —
   checked by grep over the whole file, zero hits. This was read wrong at
   `a573ca24` and carried forward from there; it is fixed below rather than
   just re-pointed, because the *subject* of the claim was wrong, not the line
   number.
4. **`.crew/verify.json` is no longer absent/gitignored.** Crew 0.19.46
   (`0a9d8937`, merged in this range) rewrote the `.crew/` ignore policy:
   `.gitignore` now ignores `.crew/*` and un-ignores exactly three paths —
   `.crew/codemap/`, `.crew/endpoints.json`, `.crew/verify.json` — and
   `.crew/verify.json` is tracked in this repository (`git ls-files .crew/`
   lists it). The previous version of this note's "not verified" block said
   the opposite. See "The `.crew/` ignore policy" section, new in this pass.
5. **Inventory counts moved.** 24 -> **26** commands (two new: `change.md`,
   `gate.md`). Skills are still stated as **17**, and that is not a
   contradiction of the 18 directories under `plugin/crew/skills/` — see
   "Inventory" below for the counting rule and its citation.

## Older provenance

Kept as an account of what earlier passes covered and did not, not as claims
about the current code.

**d61342c3 -> 7b0d8f3a, 2026-09-12.** Six merged PRs rewrote the config
layering, the consent-key carve-out, and the codemap anchor mechanism itself,
so that pass re-derived rather than re-pointed.
`useful-claude-add-ons@d61342c3` named no object in this repository — it was
the head of a squash-merged branch, discarded by the merge — so the per-path
check could not run at all until crew 0.19.13 changed the anchor writer to
record `git merge-base HEAD origin/main` instead.

**b56d41f -> 3167721f, 2026-09-05.** That pass declined to re-verify
`crew_state.py`'s internals because the file had not moved in its diff window,
and said explicitly that the guarantee was spent the moment
`plugin/crew/hooks/scripts/` appeared in a future diff. It did, twice more
since (the 0.16.7 defects below, and this pass's split), and each time the
internals were re-derived rather than carried.

**What the first re-derivation (2026-09-12) got wrong, kept as the lesson
rather than the detail.** That pass's header claimed full re-derivation; a
post-hoc diff against its own predecessor found 33 citations that had simply
been carried forward on lines that had not been touched, 12 of which were
wrong — some by hundreds of lines, because the file had grown underneath them.
The reusable rule, still followed here: a re-derivation cannot be verified by
the thing doing the re-deriving. This pass's own "Citation freshness" section
below is that check, run again.

## Re-anchor provenance — 0a9d8937 -> 975480b7, 2026-09-14

Narrow pass, not a re-derivation: `f12003e2` (#166, "fix three stale
self-describing counts") landed between the previous anchor and this one and
changed three of the four places the "Where every live count of crew's shape
agrees" table (below) quotes. Only that table was re-read against its cited
files at this anchor; nothing else in this note was re-checked, and no other
path was diffed. See that table's own header for what changed and what did
not.

## Inventory

**DERIVED at this anchor**, counted by walking the directories:

| | Count | How counted |
|---|---|---|
| Agents | 54 | `.md` files in `plugin/crew/agents/` |
| Commands | 26 | `.md` files in `plugin/crew/commands/` |
| Skills | 18 | subdirectories of `plugin/crew/skills/` |

**Corrected 2026-09-14 — the previous version of this note had the wrong
explanation, not just an outdated count.** `plugin/crew/skills/` holds **18**
directories. The claim that 17 was correct because the count excludes
`find-skills` (a vendored third-party skill — `plugin/crew/README.md:2359`
confirms it is bundled, and its own `BUNDLING-NOTE.md:1` says the same) does
not hold up against the primary artifact: `plugin/PLUGINS.md`'s own "Bundled
skills" roster table lists `find-skills` as one of its rows, so the repo's own
enumeration already counts it as one of the 17/18. The real defect was a
missing row — `crew-change` (added in crew 0.19.31, commit `53294344`) was
never added to that roster, so the table stayed at 17 rows after an 18th
directory landed. `python3 scripts/check-marketplace.py` passing at the prior
anchor is not corroboration for the "minus find-skills" rule: `check_self_claims`'s
`skills-count` marker checks the *marketplace's* total skill-plugin count
(`source` starting `./skills/`), a different quantity from crew's own bundled
count, and never touches this number at all. The marketplace entry,
`PLUGINS.md` and `README.md` are corrected to 18 in the same change that fixed
this note; `scripts/install-prerequisites.{sh,ps1}` do not state a skill count
at all (checked by grep) — the previous version of this note was wrong to cite
them as saying 17.

The 54 agents still decompose exactly, re-counted at this anchor: `ROLE_TIERS`
has **13** entries (`plugin/crew/hooks/scripts/crew_state.py:906-923`),
`SPECIALIST_ROLES` has **40**
(`plugin/crew/hooks/scripts/crew_state.py:954-995`), and `agents/pm.md` is the
standing manager on neither list. 13 + 40 + 1 = 54, and the two-way check
(every `.md` stem in `plugin/crew/agents/` accounted for by the roster, and
every roster name backed by a file) holds — same membership as the previous
anchor, re-verified rather than assumed unchanged since `crew_state.py` moved.

### Where every live count of crew's shape agrees — and where it no longer does

**Re-read at this anchor** (975480b7), not swept fresh: `f12003e2` ("crew
0.19.51: fix three stale self-describing counts", #166) landed between the
previous anchor and this one and corrected the skill count in three of these
four places from 17 to 18. It did not touch the root `README.md` or
`INSTALLATION.md`, so those two still say 17. The table below is no longer
one number agreed everywhere — it is 18 in three places and 17 in two.

| Place | Says |
|---|---|
| `.claude-plugin/marketplace.json:223` | 54 context-isolated agents (13 tiered, 40 domain specialists, and the standing manager), 26 slash commands, **18** bundled skills — fixed by `f12003e2` |
| `plugin/PLUGINS.md:17` | 54 agents, 26 commands, **18** skills, 20 hook entries (10 scripts × `.sh`/`.ps1`) across 5 events — fixed by `f12003e2` |
| `README.md:166`, `INSTALLATION.md:251` | 54 subagents, 26 slash commands, **17** bundled skills, 20 hook entries across 5 events — unchanged; `f12003e2` did not touch either file (confirmed: `git diff --name-only 0a9d8937..975480b7 -- README.md INSTALLATION.md` returns nothing) |
| `scripts/install-prerequisites.sh:902`, `.ps1:856` | 54 agents, 26 commands — does not state a skill count, so it is not part of the split |

Agent and command counts still agree everywhere. The skill count does not:
three places read 18, two read 17, and nothing in this repo's own tooling
would catch that split — `check-marketplace.py` has no reference to
`ROLE_TIERS`, `SPECIALIST_ROLES`, or a command/skill count, so this table has
always been maintained by hand, and the hand missed two of five places this
time. This is a finding for the report, not a fix made in this note: bringing
`README.md:166` and `INSTALLATION.md:251` to 18 is a source-file edit, not a
codemap correction.

**JUDGEMENT, unchanged reasoning from the previous anchor:** this note does not
list specialists by name. `SPECIALIST_ROLES` is the authority and cheap to
print; a reproduced list is a second copy that can only rot.

Structural facts about the roster, re-verified rather than assumed:

- Every specialist sits off the tier ladder — `roles_for_tier`
  (`plugin/crew/hooks/scripts/crew_state.py:1010`) reads only `ROLE_TIERS`.
- `known_role` (`plugin/crew/hooks/scripts/crew_state.py:998`) is what keeps a
  deliberately-onboarded specialist from being reported as a typo on upgrade.

## Hooks

`plugin/crew/hooks/hooks.json` (38 lines) registers **five** events and **20**
hook entries. The file is byte-identical to the previous anchor (confirmed by
`git diff`, not re-walked), so these figures and lines are current by the
per-path check:

| Event | Entries | Line |
|---|---|---|
| `SessionStart` | 6 | `plugin/crew/hooks/hooks.json:3` |
| `PreToolUse` | 4 | `plugin/crew/hooks/hooks.json:11` |
| `PreCompact` | 2 | `plugin/crew/hooks/hooks.json:21` |
| `Notification` | 2 | `plugin/crew/hooks/hooks.json:25` |
| `Stop` | 6 | `plugin/crew/hooks/hooks.json:29` |

Every count is even because each bash `command` has a `shell: "powershell"`
sibling on the same event. `PreToolUse` matches on tool: `guard` and
`promote-gate` are each registered twice, `matcher: "Bash"`
(`plugin/crew/hooks/hooks.json:12`, `:16`) and `matcher: "PowerShell"`
(`:14`, `:18`).

## The 0.16.7 guard defects and the run-tests.sh PATH-scrub proofs

**Historical section — the defects and fixes are unchanged; only the
coordinates into the files that moved were re-taken.**

`plugin/crew/tests/test_guard_bypasses.py` (changed in this range — re-read,
not carried) still documents the same three command-guard bypasses crew 0.19.23
closed: `terraform -chdir=infra apply` (`:10`), `git push 2>&1 --force` and
`git reset HEAD --hard` (`:18`), each fixed in `guard.sh` *and* `guard.ps1` in
that shell's own syntax. `plugin/crew/tests/test_promote_gate_fails_closed.py`
still covers the fourth: a raised exception from `promote-gate`'s own
precondition check being read as "no unmet preconditions" and letting a deploy
through.

`plugin/crew/hooks/scripts/_test/run-tests.sh` is **1180** lines at this
anchor (its total was not recorded at `a573ca24`, so no growth figure is
claimed here — only that the file is in this range's changed set and every
citation into it below was re-taken). The jq PATH-scrub self-proofs it runs
before the guard suite moved but did not change in kind:

| Check | Line | What a silent failure would look like |
|---|---|---|
| the jq mirror (`$JQ_SHADOW`) still resolves `jq` | `:132-136` | a scrub that does nothing, so every case takes the jq fast path |
| the scrubbed real `PATH` still resolves `jq` | `:178-183` | the same, one layer out |
| no working python survives the scrub | `:192-208` | `guard.sh` prints "no jq and no python" and exits 0, so every must-BLOCK case passes against a guard that never ran |

The third proof walks `crew_py`'s own order (`python3`, `python`, `py`,
`:192-201`) and *executes* the first name that resolves, exactly as `crew_py`
does — checking the rest of the list would pass where `crew_py` fails. Every
`jq` spelling the mirror must exclude (`jq`, `jq.exe`, `jq.bat`, …) is
enumerated at `:128`. Resolved-directory comparison (`cd … && pwd -P`, the fix
for the merged-`/usr` Linux false-refusal) is at `:88` for jq's own directory
and `:143` for each `PATH` entry.

**Known open issue, still open, re-confirmed at this anchor and not touched by
the split:** `crew_py()` (`plugin/crew/hooks/scripts/_common.sh:44-47`, the
file changed in this range but the function is textually the same three-line
`command -v` chase) returns the first of `python3`/`python`/`py` that
*resolves*, not the first that *runs*. On Windows, `command -v python3` can
resolve the `WindowsApps` App Execution Alias stub, which opens the Microsoft
Store and produces no output. `TODO.md:383-413` still records this as open and
still cites the pre-split line numbers
(`plugin/crew/hooks/scripts/_common.sh:38-43`) — a stale citation
inside `TODO.md` itself, out of this note's scope to fix, but worth naming so
nobody re-derives the same issue believing the line number. **The distinction
that is easy to lose:** the test harness now executes the interpreter it
resolves; `crew_py` in production code still does not.

## `crew_state.py` was split — twice, into `crew_freshness.py` and `crew_guards.py`

`plugin/crew/hooks/scripts/crew_state.py` **shrank** in this range, from 3170
lines at the previous anchor to **2858** here — the first time this note has
recorded a shrink rather than growth. Two modules absorbed the difference, and
this note previously traced only the code that stayed behind, so both are new
ground here:

- `plugin/crew/hooks/scripts/crew_freshness.py` (**541** lines, new since
  `a573ca24`) owns telling a stale codemap, diagram, or graph from a current
  one — `_ANCHOR_RE`, `_DIAGRAM_ANCHOR_RE`, `read_knowledge`, `read_diagrams`,
  `_read_graph` and their helpers.
  `plugin/crew/hooks/scripts/crew_state.py:112-134` re-imports the
  fifteen names it exports, three of them (`contained_path`, `read_diagrams`,
  `read_knowledge`) actually called from within `crew_state.py`.
- `plugin/crew/hooks/scripts/crew_guards.py` (**888** lines, new since
  `a573ca24` — introduced in crew 0.19.30, `68c1f93a`, which is within this
  diff range and confirmed by `git merge-base --is-ancestor a573ca24 68c1f93a`)
  owns the guard and install-policy vocabulary: `GUARD_NAMES`, `PROD_GUARD_NAMES`,
  `GUARD_DEFAULTS`, `INSTALL_POLICIES`, every `normalise_*`/`*_rank` pair
  except `authority_rank`, and its own `RATCHETED_KEYS` list.
  `plugin/crew/hooks/scripts/crew_state.py:63-88` re-imports 22 names from it.
  This split is not about
  anchor freshness at all — it is the mechanism behind the `_widens`/
  `_RATCHETED` section below — and it was missed by the previous anchor's
  "Calls out to"/"Owns data" sections, which cited `crew_state.GUARD_NAMES`
  etc. as though `crew_state.py` were where they were defined.

Only the first split is really about "this very directory" (`.crew/codemap/`
freshness); the second is included here because the previous version of this
note attributed its symbols to the wrong file, and that error would have
repeated itself at the next anchor if not corrected now.

- `read_knowledge(root, cfg)` (`plugin/crew/hooks/scripts/crew_freshness.py:375-459`)
  lists every file directly under `.crew/codemap/`. A file counts as a
  subsystem if its name ends in `.md` **and** is not in `_NOT_SUBSYSTEMS`
  (`plugin/crew/hooks/scripts/crew_freshness.py:69` —
  `frozenset({"INDEX.md", "UPGRADE.md", "MIGRATION.md"})`). This codemap
  contributes **10** subsystems out of 12 `.md` files at this anchor (same
  count as before; `INDEX.md` and `UPGRADE.md` are the two present exclusions,
  `MIGRATION.md` does not exist here).

- Each counted file is checked against `_ANCHOR_RE`
  (`plugin/crew/hooks/scripts/crew_freshness.py:64-66`):
  `^anchor:\s*(?:\S*@)?([0-9a-f]{7,40})\s*$`. The `\s*$` is still load-bearing:
  anything after the sha on that line stops the match and the file reads as
  having no anchor at all.

- **The three-state anchor logic (current / behind / unresolvable) now lives
  entirely inside `read_knowledge`, not split across a separate state-dict
  helper the way the previous anchor's citations implied.** Read in order at
  `plugin/crew/hooks/scripts/crew_freshness.py:405-459`:

  | State | Test | What the reader does |
  |---|---|---|
  | current | `sha[:7] == head[:7]` (`:430`, truncating both sides — 8- and 40-char anchors compare exactly as 7-char ones do) | nothing |
  | unresolvable | no anchor at all (`:421-428`), OR the sha does not resolve via `git cat-file -e <sha>^{commit}` (`:437-439`) | re-derive: the per-path diff cannot run at all |
  | behind | anchor resolves, is not HEAD, **and** `_moved_since(root, sha, head, _cited_paths(root, body))` is not `False` (`:451-452`) | re-check: the per-path diff already ran as part of this test and said something moved |

  This is the correction from the top of this note: the previous version's
  table stopped at "resolves, but is not HEAD" for `behind`, which described
  the code as it existed *before* the 0.19.34 fixpoint fix and was never
  updated afterward. Folding an old-but-untouched map into "behind" wastes a
  re-check; the current code does not do that, because `_moved_since` is
  evaluated before the state is assigned, not after.

- `read_diagrams(root, cfg)`
  (`plugin/crew/hooks/scripts/crew_freshness.py:473-541`) mirrors the same
  structure for `docs/diagrams/*.mmd`, using `_DIAGRAM_ANCHOR_RE`
  (`plugin/crew/hooks/scripts/crew_freshness.py:128-132`) and its own
  `_moved_since` gate at `:522`. A diagram with no anchor header counts as
  `behind` outright (`:509-511`) — unknown provenance resolves to stale, the
  same direction `_read_graph` takes for a graph with no `built_at_commit`.

- `TRIGGERS` (`plugin/crew/hooks/scripts/crew_state.py:667-697`) — this stayed
  in `crew_state.py`, not the freshness module — still holds **12** entries in
  presentation order, and `knowledgeUnverifiable` (`:688`) still sits above
  `knowledgeBehind` (`:689`) and below `graphStale` (`:683`): a map that cannot
  be verified outranks one that merely needs re-checking, and a diagram
  (drawn from the map) is ranked below both codemap findings
  (`diagramsStale`/`diagramsMissing` at `:693-694`).

- `evaluate_triggers(state)` (`plugin/crew/hooks/scripts/crew_state.py:2525-2573`)
  sets the sixteen-entry `fired` dict at `:2540-2572`; `knowledgeBehind` is set
  at `:2556` and `knowledgeUnverifiable` at `:2557` — evaluation order is still
  the reverse of `TRIGGERS`' presentation order, as it was at the previous
  anchor. `diagramsMissing` (`:2563-2564`) still fires only once
  `knowledge.subsystems` is truthy.

- `_DIAGRAM_ANCHORS_RE` and `_diagram_paths` — the machinery reading the
  hand-written `%% Anchors: <paths>` line out of a diagram so `_moved_since`
  has something to diff — are both real, both in `crew_freshness.py` (imported
  at `plugin/crew/hooks/scripts/crew_state.py:120` and `:127`), and both used at
  `plugin/crew/hooks/scripts/crew_freshness.py:519`'s call into
  `_diagram_paths`. `repo-docs.md`'s claim that this line is "read by no code
  in this repo" is corrected in that note, from this same evidence.

**Growth and shrink together: `SCHEMA_CURRENT` is now 7**
(`plugin/crew/hooks/scripts/crew_state.py:163`), up from 5. Schema 6 added the
four guards, two production guards and `github.mergeGate.{enabled,branch}`
(`crew_upgrade.SCHEMA_6_KEYS`); schema 7 added `/crew:change`'s six `change.*`
keys (`crew_upgrade.SCHEMA_7_KEYS`). `crew_upgrade.py` itself is not under
`plugin/crew/hooks/scripts/` — it lives at
`plugin/crew/skills/crew-graph/scripts/crew_upgrade.py` — noted here because a
reader chasing `SCHEMA_CURRENT`'s consumer would otherwise look in the wrong
directory.

## The endpoint ledger and `endpointUnscanned`

**`plugin/crew/hooks/scripts/crew_endpoints.py` (978 lines) did not change
between the two anchors** — confirmed by `git diff`, and its own line count is
identical to the previous anchor's. Every citation into it below is therefore
current by the per-path check. Only the two citations that reach *out* of it,
into `crew_state.py`, were re-derived.

`.crew/endpoints.json` (`_ENDPOINTS_PATH_PARTS` at
`plugin/crew/hooks/scripts/crew_endpoints.py:33`) holds only **declared**
records, written only by `declare_endpoint`
(`plugin/crew/hooks/scripts/crew_endpoints.py:254`) — the only writer of the
file, and the entry point named in `plugin/crew/agents/pm.md:286` and
`plugin/crew/commands/work.md:63-64` (both unchanged files, confirmed by
`git diff`) for turning a researched candidate into a fact. The file does not
exist in this checkout; `.gitignore` un-ignores it (`!.crew/endpoints.json`,
part of the same 0.19.46 policy rewrite — see below), so a repo that creates
one would have it tracked, but nothing in this checkout has yet.

Ids are minted from a sequence counter (`nextSeq`), sanitised against a
conservative allowlist at mint and read time
(`plugin/crew/hooks/scripts/crew_endpoints.py:50-78`), and the file is written
via temp-file-then-`os.replace`
(`plugin/crew/hooks/scripts/crew_endpoints.py:130-182`, the `os.replace` at
`:172`) under an advisory lock
(`plugin/crew/hooks/scripts/crew_endpoints.py:204-252`).

**Candidates are computed, never persisted.** `infer_endpoints`
(`plugin/crew/hooks/scripts/crew_endpoints.py:410`) scans `git diff HEAD` fresh
on every call; `read_endpoints` (`:914`) merges declared records on disk with
that fresh output. An inferred hit's id is a deterministic sha1 of
`(signal, location)` (`:468-496`), stable across repeated reads of the same
diff state but NOT across an edit that shifts the cited line — the function's
own docstring names the reproduction.

The scan-artifact path is decided once per record (`scan_artifact_path`, `:667`,
classifier at `:684-710`): single repo -> `docs/security-scans/<id>.md`;
mono-repo (`_is_monorepo`, `:580`) -> `<package-dir>/docs/security-scans/<id>.md`.
`_artifact_confirms_scan` (`:829`) requires three things, in order: non-empty,
carries `_SCAN_MARKER_RE`'s marker (`:791`), and — when the record is specific
enough (`_endpoint_needle`, `:794`) — mentions it.

`endpointUnscanned` fires when a record needs an artifact it does not have,
evaluated in `evaluate_triggers` at
`plugin/crew/hooks/scripts/crew_state.py:2553` (re-derived: this line moved
from `:2865` at the previous anchor along with the rest of `evaluate_triggers`),
gated on `gizmoduck_installed`
(`plugin/crew/hooks/scripts/crew_endpoints.py:498`) — checked across four
config scopes, project outranking global and each scope's own `.local.json`
outranking its `.json`, deferred to rather than read as `false` on any parse
failure or missing key. Placed in `TRIGGERS` at
`plugin/crew/hooks/scripts/crew_state.py:682`, below `handoffPending` (`:674`)
and above `graphStale` (`:683`) — re-derived, both lines moved.

`pm_brief.FINDINGS` (`plugin/crew/hooks/scripts/pm_brief.py:103` — unchanged
position despite the file being in this range's changed set, re-checked rather
than assumed) interpolates `"{endpointSummary}"` / `"{endpointAction}"`
(`:143-144`, also unchanged position), composed in `_endpoint_fields`
(`plugin/crew/hooks/scripts/pm_brief.py:321-398`, re-derived: this range moved
from `:295-373`). The "candidates are NOT confirmed endpoints until researched"
literal is at `:375` (moved from `:349`). The declared/candidate split is keyed
on `status`, not `source` (`:353-354`, moved from `:327-328`), for the same
reason as before: a record whose two fields disagree still renders as a
candidate.

Gizmoduck's own `plugin/gizmoduck/commands/report.md:29,37` and
`plugin/gizmoduck/commands/scan.md:27` (both unchanged, confirmed by
`git diff`) still document the seam: a scan targeting a declared endpoint
lands at that record's computed path and freezes it there afterward.

## Config, and what a machine-global file may supply

**DERIVED at this anchor by importing `crew_config` and walking both default
functions.** The full reference is `plugin/crew/CONFIG.md` (**1327** lines, up
from 900); this section records only the shape and the one invariant that is
easy to break.

Two layers, unchanged in kind: `~/.claude/crew/config.json` is machine-global,
`.crew/config.json` is per-repo and wins where both speak, `schema` is exempt
from global inheritance.

| | Leaves | Source |
|---|---|---|
| `default_config()` | **102** | `plugin/crew/hooks/scripts/crew_config.py:274` |
| `default_global_config()` | **59** | `plugin/crew/hooks/scripts/crew_config.py:407` |
| repo-only | **43** | the difference |

**Corrected 2026-09-14 — the previous version of this table undercounted the
first two figures by two each.** Re-derived by executing
`leaf_paths(default_config())` and `leaf_paths(default_global_config())` from
`plugin/crew/hooks/scripts/`, matching `plugin/crew/CONFIG.md`'s own
re-measurement. Re-run rather than trusting either file: both are a fact about
one commit.

Both totals rose (86 -> 102, 45 -> 59) and repo-only rose too this time
(41 -> 43) — a different shape than the previous anchor's "both rose by
exactly one." **The per-schema breakdown of that growth is not re-derived at
this anchor and its arithmetic did not close even before this correction**
("four guards plus two production guards plus `github.mergeGate.{enabled,branch}`"
is eight items, not the "seven" the text named, and "six `change.*` keys"
does not account for "+2 repo-only") — re-derive it from the schema 6/7 diffs
rather than trusting either the old or a patched-up version of it. `upgradeNeeded` is still
`schema < SCHEMA_CURRENT` and compares no key sets, so none of this required a
migration prompt beyond the schema bump itself.

**Consent is not capability, unchanged from the previous anchor.**
`context.autoClear.unsafeFocus` is still the one `autoClear` leaf held out of
the global layer by `AUTOCLEAR_CONSENT_KEYS`
(`plugin/crew/hooks/scripts/crew_config.py:271` — moved from `:267`,
`("unsafeFocus",)`); the other six `autoClear` leaves
(`command`, `delaySeconds`, `enabled`, `method`, `minHandoffLines`,
`windowTitle`) are globally settable. Re-verified by `leaf_paths` over both
defaults at this anchor, not assumed unchanged.

**The invariant, enforced in two places that must agree, unchanged in kind but
moved:** what the global file may *write* is what the global layer may
*supply*. Reading is pruned by `filter_global`
(`plugin/crew/hooks/scripts/crew_config.py:676`, moved from `:624`) against
`default_global_config()`; writing is refused by `plan_global_write`
(`:2211`, moved from `:1510`) against the same object.

### The ratchet is now a registry, not two special-cased keys

**Corrected at this anchor — the previous version's claim about scope, not
just its line numbers, was wrong.** `_widens(dotted, before, after)`
(`plugin/crew/hooks/scripts/crew_config.py:2043-2063`) still does what its name
says — ranks `after` against `before` and reports a widening only when the
rank rises — but it is now driven entirely by a lookup table,
`_RATCHETED` (`plugin/crew/hooks/scripts/crew_config.py:2140-2208`), which at
this anchor holds:

| Key(s) | Rank fn, all in `plugin/crew/hooks/scripts/crew_guards.py` except `pm.authority` | Notes table |
|---|---|---|
| `pm.authority` | `authority_rank` — in `plugin/crew/hooks/scripts/crew_state.py:1041` | `_WIDENING_NOTES` |
| `install.policy` | `install_policy_rank` (`plugin/crew/hooks/scripts/crew_guards.py:268`) | `_INSTALL_WIDENING_NOTES` |
| `guards.terraformApply`, `guards.forcePush`, `guards.adminMerge`, `guards.mergeGate` | `guard_policy_rank` (`plugin/crew/hooks/scripts/crew_guards.py:294`), guards named in `GUARD_NAMES` (`plugin/crew/hooks/scripts/crew_guards.py:104`) | one note per guard via `_guard_widening_notes` |
| `guards.prodDatabase`, `guards.prodServer` | `prod_level_rank` (`plugin/crew/hooks/scripts/crew_guards.py:323`), guards named in `PROD_GUARD_NAMES` (`plugin/crew/hooks/scripts/crew_guards.py:125`) | `none`/`read`/`full` vocabulary (`PROD_LEVELS`, `plugin/crew/hooks/scripts/crew_guards.py:122`), not `block`/`ask`/`allow` — deliberately different words for a different meaning |
| `change.requireForProduction` | `require_change_rank` (`plugin/crew/hooks/scripts/crew_guards.py:212`) | `_CHANGE_WIDENING_NOTES`, keyed on bool; `False` is the widening direction and the one value only the global file may set |

`pm.authority`'s rank function is the one exception that really does live in
`plugin/crew/hooks/scripts/crew_state.py:1041` (`authority_rank`) rather than
`crew_guards.py` — it predates the guard split and was never moved. Everything
else ratcheted is guard-module territory.

Nine ratcheted keys, not the two the previous anchor described. The
`pm.authority` story that motivated `_widens` in the first place is unchanged:
rank, never equality, because a third tier (`autonomous`) made an `== "act"`
comparison wrong in both directions at once.

### `pm.authority`

Three values, `normalise_authority`
(`plugin/crew/hooks/scripts/crew_state.py:1027`, moved from `:1246`) and
`authority_rank` (`:1041`, moved from `:1260`). Default is `report-only`
(`AUTHORITY_DEFAULT`, `:726`, moved from `:898`).

| Value | The PM may |
|---|---|
| `report-only` | read and report; dispatch nothing |
| `act` | dispatch roles and do the work, putting open decisions to the user |
| `autonomous` | everything `act` does, and settle its own open decisions |

`AUTONOMOUS_STOPS` (`plugin/crew/hooks/scripts/crew_state.py:739-746`, moved
from `:911-918`) still enumerates the same four things `autonomous` may never
do unasked: `offboard-role`, `delete-map`, `rewrite-metrics`,
`git-destruction`.

## The `.crew/` ignore policy — new in crew 0.19.46

**Not covered by any previous version of this note.** `0a9d8937` ("crew
0.19.46: one .crew/ ignore policy, stated once, with a checker that keeps it
that way") rewrote `.gitignore`'s `.crew/` stanza and added an enforcer.

The policy, read directly from `.gitignore:292-330`: `.crew/*` is ignored, and
exactly three paths are un-ignored — `!.crew/codemap/` (`:301`),
`!.crew/endpoints.json` (`:308`), `!.crew/verify.json` (`:330`). Everything
else under `.crew/` — `config.json`, `STATUS.md`, `metrics.md`,
`transcripts/`, `state.json` — is machine-local. Verified against this
checkout: `git ls-files .crew/` returns the twelve `.crew/codemap/*.md` files
plus `.crew/verify.json`; `.crew/endpoints.json` is absent (nothing has
written one here yet, but it is not ignored — `git check-ignore` confirms the
negation pattern matches it, not the block).

`check_crew_ignore_policy`
(`scripts/check-marketplace.py:727-891`) is the enforcer: it treats
`.gitignore` as the authority and checks that every file carrying a
`crew-ignore-policy:list` marker states the identical set. **Six files carry
that marker** per the function's own docstring at `:746-756`: `.gitignore` and
`plugin/crew/skills/crew-setup/SKILL.md` (required), plus `CLAUDE.md`,
`plugin/crew/README.md`, `plugin/crew/skills/crew-setup/phases.md` and
`plugin/crew/skills/crew-verification/SKILL.md`. `.crew/codemap/` — this
directory — is **explicitly out of scope** of that marker requirement
(`:750-756`): it is a derived map with its own anchor-staleness mechanism, and
a generated artefact failing the gate would be fixed by regenerating it, not
by hand-editing it. So this note restates the policy in prose (above) without
needing the marker, and the policy can still drift here without the checker
noticing — which is the tradeoff the check's own author documented, not an
oversight this note is flagging as new.

A regression suite exists at `scripts/_test/crew-ignore-policy.py` (confirmed
present, not read line-by-line at this pass).

## Citation freshness

Every `path:line` in this file was resolved at this anchor by one of two
mechanisms:

1. **Re-derived** — read directly or found by grep/AST walk against
   `crew_state.py`, `crew_freshness.py`, `crew_config.py` or `pm_brief.py` at
   `0a9d8937`. This is what every citation into those four files got, because
   all four are in the changed-file set.
2. **Closed by the per-path check** — the file is byte-identical between
   `a573ca24` and this anchor. This is what `crew_endpoints.py`, `hooks.json`,
   `pm.md`, `work.md` and the two gizmoduck command files got.

**Not re-run this pass, and named rather than silently dropped:** the
byte-identical-line sweep the previous two passes ran (diffing this file
against its own prior revision to catch a carried-forward citation on an
untouched line). Given that mechanism 1 above covers nearly every citation
into the three files that moved — there being almost nothing left this pass
*could* have carried forward without touching — the sweep's marginal value was
low enough that the time went into re-deriving instead. That is a judgment
call, not a finding; a future pass with a smaller diff should run the sweep
again rather than assume this one's coverage.

**What is not claimed:** that the behaviour behind these lines was re-tested.
No hook was run and no test suite was executed as part of this pass —
`pytest`'s "948 passed, 1 skipped" figure the previous anchor recorded is
**not re-measured here** and should not be read as current.

## What this file does not cover

Agent role definitions and command bodies are not traced here. `crew:reference`
and `crew:roster` are the tools for the finer grain. Config is covered here
only in outline — `plugin/crew/CONFIG.md` is the full reference and the
authority where the two disagree. The other subsystem notes in
`.crew/codemap/` cover their own areas; `INDEX.md` is the table of contents.

## Entry points

- `plugin/crew/hooks/scripts/crew_state.py:2444` - `worktree_root(cfg, repo_root)`, the one resolver for `worktree.root`.
- `plugin/crew/hooks/scripts/crew_state.py:2474` - `worktree_path(cfg, repo_root, branch)`, `<worktree_root>/<repo>-<branch>`, flattening every separator so a branch name cannot add a directory level.
- `plugin/crew/hooks/scripts/crew_state.py:2683` - `main`, carrying the `--worktree-path BRANCH` flag (`-` for the root alone; see the correction above about which branch imports `crew_config`).
- `plugin/crew/hooks/scripts/crew_state.py:2576` - `collect`, the one function that assembles the whole state a SessionStart brief renders.
- `plugin/crew/hooks/scripts/crew_config.py:771` - `resolve_config`, and `:1441` `explain_config`. They share `null_shadows` (`:581`) and `without_null_shadows` (`:627`) so the run and the report cannot disagree about a repo `null` shadowing a global value.
- `plugin/crew/hooks/scripts/crew_config.py:676` - `filter_global`, the read-side gate; `:2211` `plan_global_write`, the write-side gate.
- `plugin/crew/hooks/scripts/crew_freshness.py:375` - `read_knowledge`; `:473` `read_diagrams` - both new entry points into this module, called from `crew_state.collect`.

## Owns data

- `.crew/codemap/` - this directory. Read by `read_knowledge`
  (`plugin/crew/hooks/scripts/crew_freshness.py:375-459`); ten subsystem files
  at this anchor, out of twelve `.md` files. Tracked in git as of crew 0.19.46
  (see the ignore-policy section above) — the codemap itself was already
  tracked before that release; what changed is `.crew/verify.json` alongside it.
- `worktree.root` in `.crew/config.json` and `~/.claude/crew/config.json`,
  defaulting from `crew_state.WORKTREE_DEFAULTS`
  (`plugin/crew/hooks/scripts/crew_state.py:839-841`, moved from `:1058`).
- `crew_state.ROLE_TIERS` (`plugin/crew/hooks/scripts/crew_state.py:906-923`) -
  13 tiered roles.
- `crew_state.SPECIALIST_ROLES`
  (`plugin/crew/hooks/scripts/crew_state.py:954-995`) - 40 domain specialists.
- `crew_state.AUTONOMOUS_STOPS`
  (`plugin/crew/hooks/scripts/crew_state.py:739-746`) - the four things
  `autonomous` may not do unasked.
- `crew_config.AUTOCLEAR_CONSENT_KEYS`
  (`plugin/crew/hooks/scripts/crew_config.py:271`) - the one key held out of
  the global layer.
- `crew_config._RATCHETED`
  (`plugin/crew/hooks/scripts/crew_config.py:2140-2208`) - the nine keys whose
  widening is marked, printed on the dry run and printed again on the write.
- `.crew/verify.json` - tracked as of crew 0.19.46; the un-ignore list itself
  lives in `.gitignore:292-330`, restated (not authoritatively) by the six
  `crew-ignore-policy:list`-marked files named above.

## Calls out to

- `crew_config.resolve_config`, from `crew_state.main`'s
  `--archive-stale-handoff` branch
  (`plugin/crew/hooks/scripts/crew_state.py:2780-2782`), imported INSIDE the
  function to keep the import direction one-way. **Not** from the
  `--worktree-path` branch — see the correction at the top of this note.
- `git cat-file -e <sha>^{commit}` from `read_knowledge`
  (`plugin/crew/hooks/scripts/crew_freshness.py:437`), to tell a resolvable
  anchor from one this repository does not contain. `git_out` returns `None`
  on any failure, so a missing git lands as "cannot tell" rather than raising
  out of a SessionStart hook.
- `crew_state._repo_digest` (`plugin/crew/hooks/scripts/crew_state.py:857`,
  moved from `:1076`) hashes `normcase(realpath(repo_root))` with `blake2b`,
  degrading to `abspath` when `realpath` raises.
- `_SEPARATORS` (`plugin/crew/hooks/scripts/crew_state.py:852-854`, moved from
  `:1071`) is derived from `os.sep`/`os.altsep` rather than written as a regex
  character class.

## Unverified at this anchor

- No hook was executed and no pytest run was made part of this pass; every
  claim about *behaviour* is read from source and from the committed test
  file headers, not observed running.
- Agent and command bodies were counted, not read.
- `crew_upgrade.py`'s schema-6 migration path itself (`crew_upgrade.SCHEMA_6_KEYS`
  and its consumer) was located but not read line-by-line; only the key list
  and its file location are cited above.
- `scripts/_test/crew-ignore-policy.py` was confirmed to exist and was not
  read; its coverage of the six-marker-file check is taken from
  `check_crew_ignore_policy`'s own docstring, not from the test file.
- The byte-identical-line sweep the previous two passes ran was not repeated
  this pass — see "Citation freshness" for why, and treat that as a real gap
  rather than an oversight elided.
