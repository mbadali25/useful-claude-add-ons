anchor: useful-claude-add-ons@7b0d8f3a
verified: 2026-09-12
re-derived, not re-verified: the live claims below were taken from the source at
this anchor, not carried forward and re-pointed. The historical sections are
accounts of past work and are marked as such.
scope of that claim, measured rather than asserted: the first pass left 33
citations on lines byte-identical to the previous version of this file. All 33
were then re-resolved against HEAD - see "What the first re-derivation missed".


# crew

The `crew` plugin: a virtual dev team of context-isolated agents, slash
commands, bundled skills, and deterministic hooks. Registered in
`.claude-plugin/marketplace.json` like every other entry here.

## Re-derivation provenance - d61342c3 -> 7b0d8f3a, 2026-09-12

**Why this note was re-derived rather than re-verified, unlike its four
neighbours.** Six merged PRs between the previous anchor and this one rewrote
exactly what this note describes: the config layering and what a machine-global
file may supply (#102, #105, #106), ten previously-undeclared keys and the
consent key held back from the global layer (#106), and the codemap anchor
mechanism this note explains to its own future writer (#108). Re-pointing its
citations would have produced a note whose line numbers were right and whose
claims were about a crew that no longer exists.

**The previous anchor did not resolve.** `useful-claude-add-ons@d61342c3` names
no object in this repository; `519754fa`, which wrote it, was a squash merge, so
the branch commit its writer recorded died with the branch. The per-path check
(`git diff --name-only <anchor>..HEAD -- <cited paths>`) could not run at all.
crew 0.19.13 fixes the writer -- it now records `git merge-base HEAD origin/main`,
a commit already on the trunk -- and makes an unresolvable anchor its own
reported value rather than a kind of "behind".

**How the figures below were obtained.** A script imported `crew_config` and
`crew_state` directly and walked `plugin/crew/`; line numbers come from an AST
walk over the two modules, not from grep, so a name appearing in a comment or a
string cannot be mistaken for its definition. Nothing in that script reads the
previous version of this file.

**Not verified at this anchor, stated as an unknown rather than guessed:**

- No hook was executed. Every claim about hook *behaviour* is read from source
  and from the committed suites, not observed.
- The agent and command bodies were counted, not read. What each role does is
  outside this note, as it has always been.
- `.crew/verify.json` is absent from this checkout (gitignored), so nothing
  about per-path verify routing could be checked here. See
  `.crew/codemap/verification-harness.md`, where that gap is the dominant fact.

### Older provenance - b56d41f -> 3167721f, 2026-09-05

Kept because it records what an earlier pass did and did **not** cover. That
pass explicitly declined to re-verify `crew_state.py`'s internals, on the
grounds that the file had not moved in its diff window, and said: "If
`plugin/crew/hooks/scripts/` appears in a future diff against this anchor,
treat this section's guarantee as spent." It did appear, and it is spent — the
2026-09-06 pass above is what replaces it. That pass also fixed 9 anchors that
had been written relative to `plugin/crew/hooks/scripts/` rather than
repo-relative, which is the form that cannot be pasted into
`git diff --name-only <anchor>..HEAD -- <paths>`.

## Inventory

**DERIVED at this anchor**, counted by walking the directories and importing the
modules, not trusted from any description:

| | Count | How counted |
|---|---|---|
| Agents | 54 | `.md` files in `plugin/crew/agents/` |
| Commands | 24 | `.md` files in `plugin/crew/commands/` |
| Skills | 17 | subdirectories of `plugin/crew/skills/` |

The 54 agents decompose exactly, with no remainder: `ROLE_TIERS` has **13**
entries (`plugin/crew/hooks/scripts/crew_state.py:1071`), `SPECIALIST_ROLES` has
**40** (`plugin/crew/hooks/scripts/crew_state.py:1119`), and `agents/pm.md` is
the standing manager on neither list. 13 + 40 + 1 = 54. DERIVED: the set of
`.md` stems in `plugin/crew/agents/` minus `ROLE_TIERS | SPECIALIST_ROLES` is
exactly `{pm}`, and the reverse difference is empty -- so no role is named in
code without an agent file, and no agent file is unreachable from the roster.
That two-way check is the point; counting one direction only would miss a
specialist that exists on disk and is named nowhere.

**The marketplace entry is now wrong about this, and it was right at the previous
anchor.** `.claude-plugin/marketplace.json:217` still describes crew as "29
context-isolated agents (13 tiered, 15 domain specialists opted into per repo,
and the standing manager)". The tiered figure (13) and the manager still hold;
the specialist figure is 40, not 15, and the total is 54, not 29. DERIVED by
comparing the string to the imported constants.

This is the same class of drift `marketplace-registration.md` records, and at
this anchor **no place in the repo states crew's agent count correctly** -- the
install scripts say 11, `plugin/PLUGINS.md:17` and the marketplace entry say 29,
`plugin/PLUGINS.md:153` says 14, `README.md:165` says 50. Nothing checks any of
them: `check_catalogs`, `check_menu_parity` and `check_group_parity` compare
keys and booleans, never descriptive prose.

**JUDGEMENT, and it is why this section no longer lists specialists by name.**
The previous version enumerated all fifteen. That list is what rotted first: the
set went 15 -> 40 while the prose stayed, and a reader checking three names off
would have had no signal the other twenty-five existed. `SPECIALIST_ROLES` is
the authority and is cheap to print. A codemap that reproduces a list which
lives in code has taken on a maintenance burden it cannot discharge.

Structural facts about the roster that are *not* just counts, and that survived
re-derivation unchanged:

- Every specialist sits off the tier ladder. No tier grants one, and onboarding
  one leaves `tier` alone -- `roles_for_tier` reads only `ROLE_TIERS`.
- `known_role` is what keeps a deliberately-onboarded specialist from being
  reported as a typo on every upgrade.
- The reason is in the code rather than only in prose: "this repo does
  SharePoint" is a fact about one checkout, not a defect class every repo has.

## Hooks

`plugin/crew/hooks/hooks.json` (38 lines) registers **five** events and **20**
hook entries. DERIVED by `json.load` and counting, at this anchor:

| Event | Entries | Line |
|---|---|---|
| `SessionStart` | 6 | `plugin/crew/hooks/hooks.json:3` |
| `PreToolUse` | 4 | `plugin/crew/hooks/hooks.json:11` |
| `PreCompact` | 2 | `plugin/crew/hooks/hooks.json:21` |
| `Notification` | 2 | `plugin/crew/hooks/hooks.json:25` |
| `Stop` | 6 | `plugin/crew/hooks/hooks.json:29` |

Every count is even, and that is the invariant rather than a coincidence: each
bash `command` has a `shell: "powershell"` sibling on the same event, so 20
entries are 10 scripts times two flavours. A bare `command` goes to Git Bash on
Windows, which is how crew once shipped a release where the guard stood down
there and blocked nothing -- the rule is in `CLAUDE.md` and is confirmed, not
restated, here.

`PreToolUse` is the one event matching on tool rather than firing
unconditionally: `guard` and `promote-gate` are each registered twice, with
`matcher: "Bash"` (`plugin/crew/hooks/hooks.json:12`, `:16`) and
`matcher: "PowerShell"` (`:14`, `:18`).

## The 0.16.7 guard defects, and the dispatch.d rewrite that fixed the largest one

**Historical section — the four defects and their fixes are unchanged. Only
the coordinates were re-taken at this anchor.**

`plugin/crew/hooks/scripts/crew_state.py` gained 926 lines between the
`2b0972d` and `b56d41f` anchors, with smaller additions to `crew_config.py`,
`crew_platform.py` and `pm_brief.py`. All four files changed in commit
`875c9c6f`, "crew 0.16.7: three domain specialists, and four guard defects
that failed open" (merged at `27832d4f`). Read against the commit body rather
than summarised from memory, the four defects were:

1. **A later dispatch cleared the actual author.** `dispatch.json` held one
   `dev` slot; a second, unrelated dispatch on the same branch overwrote it,
   so review could read the wrong author, bar the wrong family, and clear
   the one that actually wrote the diff.
2. **The dispatch write was not atomic.** A concurrent reader could see a
   truncated file, `read_dispatch` collapsed the malformed JSON to `{}`, and
   the guard fell back to config describing the *next* run.
3. **A config of `{}` switched crew off permanently** — it parses, so
   `heal_config` treated it as healthy, and `/crew:upgrade` reported
   "already current" forever with no way out.
4. **`/crew:model` printed `eligible` for a family it could not name** — an
   unpinned `copilot` was reported eligible instead of `CANNOT PROVE
   INDEPENDENCE`.

The substantive fix for (1) and (2): `dispatch.json` (one shared, mutable
file) is replaced by `.work/dispatch.d/`, one immutable file per dispatch
(`plugin/crew/hooks/scripts/crew_state.py:1645`,
`DISPATCH_DIR = (".work", "dispatch.d")`, with the reasoning at
`plugin/crew/hooks/scripts/crew_state.py:1625-1644`), bounded by
`DISPATCH_FILES_MAX` (`plugin/crew/hooks/scripts/crew_state.py:1652`). The
legacy single file is still read (`DISPATCH_PATH` at
`plugin/crew/hooks/scripts/crew_state.py:1592`; it is opened by
`_read_record_file` (`plugin/crew/hooks/scripts/crew_state.py:1765-1792`) and
drained into history by `_history_items`
(`plugin/crew/hooks/scripts/crew_state.py:1795-1847`), with `read_dispatch` at
`plugin/crew/hooks/scripts/crew_state.py:1957-2018`) so an older record is not
silently discarded.

**Refined at this anchor:** the previous version called the legacy file "a
lower-priority fallback", which understates the mechanism. Priority is
*structural*, not a timestamp comparison: `_merge_history`
(`plugin/crew/hooks/scripts/crew_state.py:1850-1954`; the tier rule is stated in
its own docstring at `plugin/crew/hooks/scripts/crew_state.py:1853-1856` and
enforced at `:1948`) ranks entries by
`(tier, sort key)`, with `.work/dispatch.d/` at tier 1 and anything read out
of the legacy `dispatch.json` at tier 0, so nothing in the legacy file can
outrank the store *no matter what its `at` says*. The hazard that motivates it
is a legacy record with far-future timestamps — a clock that ran ahead, a hand
edit, a restored backup — evicting the dispatch that had just happened.

Anyone who gitignores crew's working files by hand needs to add
`.work/dispatch.d/`, not just `dispatch.json` — `/crew:init` does both.

**Separately, two defects in the `.sh` hook layer rather than the `.py`
layer,** both predating that refresh's diff window (they landed before the
`2b0972d` anchor). `plugin/crew/hooks/scripts/_test/run-tests.sh`'s PATH scrub
used to end every `PATH` entry in a trailing colon, which every POSIX shell
reads as "also search the current directory" — fixed in `0bf0c2f3`. And
`pm-brief.sh`, `pm-pulse.sh`, `platform-sync.sh` and `handoff-read.sh` used to
resolve Python with `command -v python3 || command -v python`, skipping the
`py` launcher and exiting 0 with nothing on stderr when neither resolved —
fixed in `0131d0f0` to use the shared `crew_py()` in `_common.sh` and to print
to stderr on failure.

**DERIVED (`plugin/crew/hooks/scripts/_test/run-tests.sh:74-148`, range
re-taken at this anchor — it was cited as `:74-135` and the block runs 13
lines further): that PATH scrub was fixed twice more after `0bf0c2f3`, and the
reason is worth carrying — CI was red for both.** It compared `PATH` entries as
*strings*, so on a merged-`/usr` Linux — every GitHub runner — dropping the
literal `/usr/bin` left `/bin` behind pointing at the same directory, jq
stayed reachable, and the suite FATAL'd rather than run. Fixed by resolving
each entry with `cd … && pwd -P` before comparing
(`plugin/crew/hooks/scripts/_test/run-tests.sh:131`). That exposed the real
problem: the scrub removed jq's whole *directory*, because `PATH` has
directory granularity while the thing being hidden is one file — and on Linux
that directory is `/usr/bin`, holding `python3` and `sh`, the interpreter the
no-jq fallback runs on. It now **substitutes** rather than subtracts: mirrors
the directory into a temp dir as symlinks minus every spelling of jq (`jq`,
`jq.exe`, `jq.bat`, …, enumerated at
`plugin/crew/hooks/scripts/_test/run-tests.sh:117`; the bare name alone was
not enough on Windows, where the binary is `jq.exe` plus a chocolatey `jq.bat`
shim), and puts the mirror at the same `PATH` position. The mirror proves
itself — if `command -v jq` still resolves under it the suite FATALs and names
the cause (`plugin/crew/hooks/scripts/_test/run-tests.sh:121-123`), because a
scrub that silently does nothing is the exact false green this section exists
to prevent.

**Known open issue, not fixed, recorded in `TODO.md:200-229` (repo root)
rather than here — re-confirmed still open and still accurate at this
anchor:** `crew_py()` (`plugin/crew/hooks/scripts/_common.sh:38-43`, citation
unchanged) returns the first of `python3`/`python`/`py` that `command -v`
*resolves*, not the first that actually *runs*. On Windows, `command -v
python3` can resolve the `WindowsApps` App Execution Alias stub, which opens
the Microsoft Store and produces no output — so a guard fed that stub sees an
empty result and stands down silently, on exactly the platform where a guard
has already shipped broken once before. `TODO.md` records this as reproduced
(128 → 77 passed with the real interpreter removed from `PATH`) and gives the
fix shape (execute each candidate, don't just resolve it).

## `crew_state.py` and this very directory

`plugin/crew/hooks/scripts/crew_state.py` (**3023** lines at this anchor) is what
reads `.crew/codemap/` and turns it into the PM's SessionStart brief. That makes
it the one section of this note a codemap writer has to get right, so it is
re-derived rather than carried forward. **Every line number below came from an
AST walk at this anchor, not from the previous version.**

- `read_knowledge()` (`plugin/crew/hooks/scripts/crew_state.py:692`) lists every
  file directly under `.crew/codemap/`. A file counts as a subsystem if its name
  ends in `.md` **and** is not in `_NOT_SUBSYSTEMS`
  (`plugin/crew/hooks/scripts/crew_state.py:539` --
  `frozenset({"INDEX.md", "UPGRADE.md", "MIGRATION.md"})`). This codemap
  contributes **10** subsystems. `INDEX.md` and `UPGRADE.md` are the two excluded
  names actually present; `MIGRATION.md` is in the frozenset and does not exist
  here.

- Each counted file is checked for an anchor line matching `_ANCHOR_RE`
  (`plugin/crew/hooks/scripts/crew_state.py:534`):
  `^anchor:\s*(?:\S*@)?([0-9a-f]{7,40})\s*$` -- anchored to the start of a
  line, case-insensitive, `re.MULTILINE`. **The `\s*$` is load-bearing for
  anyone editing one of these files:** anything after the sha on that line, a
  parenthetical note included, stops the regex matching and the map reads as
  having no anchor at all. Put commentary on the next line.

- **An anchor now resolves to one of three states, not two** (crew 0.19.13,
  `plugin/crew/hooks/scripts/crew_state.py:692-763`):

  | State | Test | What the reader does |
  |---|---|---|
  | current | `sha[:7] == head[:7]` (`:746`, truncating **both** sides, so 8- and 40-char anchors compare exactly as 7-char ones do) | nothing |
  | behind | resolves, but is not HEAD -- probed with `git cat-file -e <sha>^{commit}` | **re-check**: run the per-path diff; empty output means current despite the lag |
  | unresolvable | no anchor, or a sha this repository does not contain | **re-derive**: the per-path diff cannot run at all |

  The third is the one this note's own anchor was in. Folding it into "behind"
  is the repo's named bug -- an unknown collapsing into the safe-looking value --
  because "behind" is a cheap, definite finding and a reader who cannot tell the
  two apart does the cheap thing.

- The distinction is carried into the triggers rather than stopping at the state
  dict. `TRIGGERS` (`plugin/crew/hooks/scripts/crew_state.py:833`) holds **12**
  entries, with `knowledgeUnverifiable` (`:854`) sorted deliberately **above**
  `knowledgeBehind` (`:855`) and **below** `graphStale` -- a map that cannot be
  verified outranks one that merely needs re-checking, but a map is drawn
  against the graph, so a stale graph is the earlier input. Both are set in
  `evaluate_triggers` (`:2721`, `:2722`).

- Diagrams use a separate `_DIAGRAM_ANCHOR_RE`
  (`plugin/crew/hooks/scripts/crew_state.py:598`), with its own comparison at
  `:814`. It cannot reuse `_ANCHOR_RE`: a bare `anchor:` line is a syntax error
  in a Mermaid source, so the provenance has to live inside a `%%` comment. The
  reason is written out at `:586-597`, which is worth reading before touching
  either regex.

- `diagramsMissing` (`plugin/crew/hooks/scripts/crew_state.py:860`, set at
  `:2728`) fires only once `knowledge.subsystems` is truthy -- a repo with no
  codemap has not decided what its subsystems are yet. So writing this codemap
  is also what turns on the nag for missing per-subsystem diagrams.

**On the previous version's note that the line numbers "moved again, and not by
a single offset":** still true, and more so. `crew_state.py` is 3023 lines here
against the 2313 that note recorded -- it grew by 710 while that note described
it as having shrunk from a pre-split peak. Every number in this section was
re-taken; none was adjusted.

## The endpoint ledger and `endpointUnscanned`

**Now DERIVED — this was JUDGEMENT at the previous anchor and no longer needs
to be.** The previous version said the design "changed twice in the same
working tree and was never committed at either shape", that HEAD contained
none of the code, and that no `path:line` citation could be checked. That is
now false in the useful direction: the code is committed and lives in its own
module, `plugin/crew/hooks/scripts/crew_endpoints.py` (978 lines), split out
of `crew_state.py` at `ac93221d`. Every citation below was read off that file
at this anchor.

`.crew/endpoints.json` (`_ENDPOINTS_PATH_PARTS` at
`plugin/crew/hooks/scripts/crew_endpoints.py:33`; re-admitted in
`.gitignore:298` next to `.crew/codemap/`, same reasoning — a scan obligation
that exists only in one clone's untracked state reaches nobody) holds only
**declared** records — `source: "declared"`, written only by
`declare_endpoint` (`plugin/crew/hooks/scripts/crew_endpoints.py:254`), the
one function allowed to write that source, the only writer of the file at all,
and the one entry point for turning a researched candidate into a fact.

**Corrected here.** The previous pass said that entry point was named in two
files: a line in `plugin/crew/agents/pm.md` (cited at a line number that is now
blank - deliberately not repeated here, because a checker walking these
citations cannot tell a quoted wrong one from a broken one) and
`plugin/crew/commands/work.md:64`. Only the second survives: `plugin/crew/commands/work.md:63-64` still spells out
`crew_state.py --root . --declare-endpoint …`, but `pm.md` names the declare
path **nowhere**. Its single remaining mention of endpoints is the trigger row
at `plugin/crew/agents/pm.md:286`, which tells the pm to send `gizmoduck:scan`
for a declared endpoint and nobody for a candidate - it describes what to do
with a declaration, never how one is made. So the pm agent is told to act on
declared endpoints without being told what declares them; the instruction lives
only in `work.md`, which the pm does not read. That gap is stated, not fixed
here - it is a change to a shipped agent file and belongs in its own commit with
its own version bump.

It still runs through the `crew_state.py` CLI: the *implementation* moved
modules, the *command line* did not, which is why `work.md` needed no change in
the split.

Ids are minted from a sequence counter persisted alongside the records
(`nextSeq`, not `len(records) + 1`, which collides the moment a record is
deleted from this committed, hand-editable file), sanitised against a
conservative allowlist at both mint and read time
(`plugin/crew/hooks/scripts/crew_endpoints.py:50-78` — a value with a path
separator is rejected, never mangled), and the file is written via a
temp-file-then-`os.replace`
(`plugin/crew/hooks/scripts/crew_endpoints.py:130-182`, the `os.replace` at
`:172`) under an advisory lock
(`plugin/crew/hooks/scripts/crew_endpoints.py:204-252`) — never in place, the
same pattern crew abandoned `dispatch.json` for, above. **Added at this
anchor:** re-declaring an existing id updates `endpoint`/`location`/`ticket`
but leaves `status` alone; it used to force it back to `"open"`, silently
reopening a record a human had closed.

**Candidates are computed, never persisted** — the design's central decision.
`infer_endpoints` (`plugin/crew/hooks/scripts/crew_endpoints.py:410`) scans
`git diff HEAD` for a diff-line pattern match and returns candidates fresh;
nothing in the module writes one to `.crew/endpoints.json`. `read_endpoints`
(`plugin/crew/hooks/scripts/crew_endpoints.py:914`) merges the declared
records on disk with `infer_endpoints`'s fresh output on every call. An
inferred hit's id is a deterministic sha1 of `(signal, location)`
(`plugin/crew/hooks/scripts/crew_endpoints.py:468-496`), not a counter —
stable across repeated reads of the SAME diff state despite never being saved,
which is what lets a scan written today be found by a read tomorrow. That
stability does NOT survive an edit that shifts the line: `location` carries a
line number, so one line inserted above the candidate changes its location and
therefore its id, orphaning any scan already written for the old one. The
function's own docstring now says only that, and names the reproduction
(`cand-e79629d0` → `cand-ad136138` after prepending one `import os`). `status`
(`"open"` for declared, `"candidate"` for inferred, `"closed"` for either once
dealt with) is what every consumer treats as authoritative — never `source`
alone, which a bug could set inconsistently.

The scan-artifact path is decided once per record (`scan_artifact_path`,
`plugin/crew/hooks/scripts/crew_endpoints.py:667`, classifier documented at
`:684-710`): single repo → `docs/security-scans/<id>.md` at the repo root;
mono-repo (`_is_monorepo`, `:580`) → `<package-dir>/docs/security-scans/<id>.md`,
attributed from the record's `location` (`_owning_package_dir`, `:618`). The
classifier is consulted only for a record with no scan yet — one that already
has a landed scan carries its own frozen path, written by `record_scan_artifact`
(`plugin/crew/hooks/scripts/crew_endpoints.py:720`) — so a later repo-shape
change moves where the NEXT scan goes without relocating or orphaning one that
already happened.

**Corrected at this anchor: the evidence rule has three checks, not two.** The
previous version said an artifact counts "when it is non-empty and, where the
record names something specific enough to search for, mentions it".
`_artifact_confirms_scan` (`plugin/crew/hooks/scripts/crew_endpoints.py:829`)
requires all three, in order: non-empty (a `touch`ed 0-byte file must not
discharge the obligation); carries the scan marker `_SCAN_MARKER_RE`
(`plugin/crew/hooks/scripts/crew_endpoints.py:791`,
`**Total finding instances:** <n>`, which gizmoduck's report command always
writes); and, when the record names something specific enough to search for
(`_endpoint_needle`, `:794`), the text mentions it. The middle check is the
one the old two-check description dropped, and it is the one that closes a
44-byte to-do note satisfying a bare substring match without a scan ever
having run.

`endpointUnscanned` fires when a record needs an artifact it does not have
(evaluated in `evaluate_triggers`,
`plugin/crew/hooks/scripts/crew_state.py:2690-2738`, at
`plugin/crew/hooks/scripts/crew_state.py:2718`), gated entirely on
`gizmoduck_installed` (`plugin/crew/hooks/scripts/crew_endpoints.py:498`) —
checked at project `.claude/settings.local.json`, project
`.claude/settings.json`, user-global `~/.claude/settings.local.json`, then
user-global `~/.claude/settings.json`, project outranking global and each
scope's own `.local.json` outranking its `.json`; the first scope with a real
JSON boolean wins and stops the search. Never whether this repo's own
`plugin/gizmoduck/` source directory exists. A scope is *deferred to*, never
read as an implicit `false`, when the file is absent, its JSON does not parse,
`enabledPlugins` has no `gizmoduck@…` entry, or the value is present but not a
JSON boolean — the string `"false"` is truthy in Python, so the type is checked
rather than the truthiness.

Placed in `TRIGGERS` (`plugin/crew/hooks/scripts/crew_state.py:833-863`) at
`plugin/crew/hooks/scripts/crew_state.py:848`, below `handoffPending` (`:840`)
and directly above `graphStale` (`:849`):
a live, unscanned endpoint is an actionable security gap like an unfinished
handoff, not a documentation-freshness finding.

**Corrected at this anchor:** the "candidates are not confirmed until
researched" text is no longer in the `FINDINGS` entry. `pm_brief.FINDINGS`
now interpolates two pre-composed fields
(`plugin/crew/hooks/scripts/pm_brief.py:143-144`,
`"{endpointSummary}"` / `"{endpointAction}"`) and the sentence lives in
`_endpoint_fields` (`plugin/crew/hooks/scripts/pm_brief.py:289-366`, the literal
at `plugin/crew/hooks/scripts/pm_brief.py:343`: *"candidates are NOT confirmed
endpoints until researched"*; the two fields are returned at `:364-365`). The
claim is still true; its location is not where it was. The split into
declared/candidate is keyed on `status`, not `source`
(`plugin/crew/hooks/scripts/pm_brief.py:322`, with the reasoning at
`plugin/crew/hooks/scripts/pm_brief.py:300`), so a record whose two fields
disagree still renders as a candidate rather than a confirmed fact — and it is
pre-composed so a candidates-only state never reads "0 declared endpoint(s)"
with an action telling the user to scan none of them.

Gizmoduck's own `plugin/gizmoduck/commands/report.md:29,37` and
`plugin/gizmoduck/commands/scan.md:27` document the seam this closes: when a
scan targets a declared endpoint, the report lands at that record's computed
path (`--scan-artifact-path`) and freezes it there (`--record-scan-artifact`)
afterward, rather than at gizmoduck's own default location.

## Config, and what a machine-global file may supply

**DERIVED at this anchor by importing `crew_config`.** The full reference is
`plugin/crew/CONFIG.md` (721 lines), written between the previous anchor and
this one; this section records only the shape a codemap reader needs and the one
invariant that is easy to break.

Two layers. `~/.claude/crew/config.json` is machine-global -- facts about this
computer. `.crew/config.json` is per-repo and wins where both speak. `schema` is
exempt from global inheritance.

| | Leaves | Source |
|---|---|---|
| `default_config()` | **85** | `plugin/crew/hooks/scripts/crew_config.py:270` |
| `default_global_config()` | **44** | `plugin/crew/hooks/scripts/crew_config.py:378` |
| repo-only | **41** | the difference |

`SCHEMA_CURRENT` is **4** (`plugin/crew/hooks/scripts/crew_state.py:54`).
`upgradeNeeded` is `schema < SCHEMA_CURRENT` and compares no key sets, so adding
a default needs no schema bump and triggers no migration prompt.

**The invariant, and it is enforced in two places that must agree:** what the
global file may *write* is exactly what the global layer may *supply*. Reading
is pruned by `filter_global` (`plugin/crew/hooks/scripts/crew_config.py:613`)
against `default_global_config()`; writing is refused by `plan_global_write`
(`:1371`) against the same object. One object, two gates. A key added to one
path and not the other produces a file that accepts a value and then ignores it,
or rejects a value it would have honoured.

**Consent is not capability**, and `context.autoClear.unsafeFocus` is the live
case. Six of the seven `autoClear` keys are globally settable -- the method is
validated per platform, which makes it a fact about the machine. The seventh is
held out by `AUTOCLEAR_CONSENT_KEYS`
(`plugin/crew/hooks/scripts/crew_config.py:267`,
`("unsafeFocus",)`) and is repo-only. DERIVED: `leaf_paths` over both defaults
puts `command`, `delaySeconds`, `enabled`, `method`, `minHandoffLines` and
`windowTitle` in the global set and `unsafeFocus` outside it. The precedent is
`graph.obsidian.confirmed`: consent to act outside the repo is not something a
machine-global file, or a guided flow, may grant on the user's behalf.

### `pm.authority`

Three values, normalised by `normalise_authority`
(`plugin/crew/hooks/scripts/crew_state.py:1192`) and ordered by `authority_rank`
(`:1206`). The default is `report-only`
(`AUTHORITY_DEFAULT`, `plugin/crew/hooks/scripts/crew_state.py:892`).

| Value | The PM may |
|---|---|
| `report-only` | read and report; dispatch nothing |
| `act` | dispatch roles and do the work, putting open decisions to the user |
| `autonomous` | everything `act` does, and settle its own open decisions |

Read the value as a floor, never as a label: whatever `act` may do,
`autonomous` may do.

**What `autonomous` adds is deciding, not destroying.** `AUTONOMOUS_STOPS`
(`plugin/crew/hooks/scripts/crew_state.py:905`) enumerates four things it may
never do unasked, and the list is in code rather than prose so it can be tested:

- `offboard-role` -- offboarding a role, or removing one from the roster
- `delete-map` -- deleting a codemap file or a diagram
- `rewrite-metrics` -- rewriting `.crew/metrics.md`
- `git-destruction` -- destroying git history or tracked work: force-push,
  branch delete, history rewrite, or `rm` of a tracked file

A widening of `pm.authority` is the one config change `plan_global_write` marks
specially (`widens_authority`, `plugin/crew/hooks/scripts/crew_config.py:1447`),
so granting it can never happen silently.

## Citation freshness

Every `path:line` in this file was resolved at this anchor by an AST walk over
`crew_config.py` and `crew_state.py`, or by reading the cited file. None was
carried forward from the previous version and none was adjusted by an offset.

What is **not** claimed: that the behaviour behind those lines was re-tested. No
hook was run. The crew test suite passes at this anchor (886 passed, 1 skipped),
which is evidence about the code, not about this note's reading of it.

## What this file does not cover

Agent role definitions and command bodies are not traced here; this note covers
`crew` at the level of "what exists and how it is wired". `crew:reference` and
`crew:roster` are the tools for the finer grain.

Config is covered here only in outline. `plugin/crew/CONFIG.md` is the full
reference -- every key, its default, its type, which layer may supply it, and
what it does -- and it is the authority where the two disagree.

The other nine subsystem notes in `.crew/codemap/` cover their own areas;
`INDEX.md` is the table of contents.

## Entry points

- `plugin/crew/hooks/scripts/crew_state.py:2609` - `worktree_root(cfg, repo_root)`, the one resolver for `worktree.root`. Unset, blank or non-string means the checkout's parent, which is what crew did before the key existed.
- `plugin/crew/hooks/scripts/crew_state.py:2639` - `worktree_path(cfg, repo_root, branch)`, `<worktree_root>/<repo>-<digest>-<branch>`. Flattens every separator and `:` so a branch name cannot add a directory level.
- `plugin/crew/hooks/scripts/crew_state.py:2848` - `main`, which carries the `--worktree-path BRANCH` flag (`-` for the root alone). This is the only way a command can obtain the path.
- `plugin/crew/hooks/scripts/crew_state.py:2741` - `collect`, the one function that assembles the whole state a SessionStart brief renders.
- `plugin/crew/hooks/scripts/crew_config.py:708` - `resolve_config`, and `:828` `explain_config`. The run and the report share `null_shadows` (`:518`) and `without_null_shadows` (`:564`) so they cannot disagree about whether a repo `null` shadows a machine-global value.
- `plugin/crew/hooks/scripts/crew_config.py:613` - `filter_global`, the read-side gate; `:1371` `plan_global_write`, the write-side gate. Both judge against `default_global_config()`.

## Owns data

- `.crew/codemap/` - this directory. Read by `read_knowledge` (`plugin/crew/hooks/scripts/crew_state.py:692`); ten subsystem files at this anchor.
- `worktree.root` in `.crew/config.json` and `~/.claude/crew/config.json`, defaulting from `crew_state.WORKTREE_DEFAULTS` (`plugin/crew/hooks/scripts/crew_state.py:1004`). Globally inheritable - it is a fact about which disk has room, not about a checkout.
- `crew_state.ROLE_TIERS` (`plugin/crew/hooks/scripts/crew_state.py:1071`) - 13 tiered roles, unchanged across this re-derivation.
- `crew_state.SPECIALIST_ROLES` (`plugin/crew/hooks/scripts/crew_state.py:1119`) - **40** domain specialists off the tier ladder, up from 15 at the previous anchor. With the 13 tiers and `pm`, that is the 54 files in `plugin/crew/agents/`.
- `crew_state.AUTONOMOUS_STOPS` (`plugin/crew/hooks/scripts/crew_state.py:905`) - the four things `autonomous` may not do unasked.
- `crew_config.AUTOCLEAR_CONSENT_KEYS` (`plugin/crew/hooks/scripts/crew_config.py:267`) - the keys held out of the global layer because consent is not capability.

## Calls out to

- `crew_config.resolve_config` from `crew_state.main`'s `--worktree-path` branch, imported INSIDE the function - the two modules must not import each other at top level.
- `git cat-file -e <sha>^{commit}` from `read_knowledge`, to tell a resolvable anchor from one this repository does not contain. `git_out` returns `None` on any failure, so a missing git lands as "cannot tell" rather than raising out of a SessionStart hook.
- `crew_state._repo_digest` (`plugin/crew/hooks/scripts/crew_state.py:1022`) hashes `normcase(realpath(repo_root))` with `blake2b`, degrading to `abspath` when `realpath` raises, so a hook never dies for an unstattable path.
- `_SEPARATORS` (`plugin/crew/hooks/scripts/crew_state.py:1017`) is derived from `os.sep`/`os.altsep` rather than written as a regex character class.


## What the first re-derivation missed

This section exists because the check that found it was run *after* the file was
written, and nearly was not run at all.

The pass that produced this note claimed in its own header that every live claim
was taken from the source at this anchor. A sweep afterwards - diffing this file
against its previous version and flagging every citation sitting on a
byte-identical line - found **33 citations that had simply been carried
forward**. The header was true of the sections that were rewritten and false of
the ones that were not, and nothing in the file distinguished them.

That is this repository's recurring failure wearing yet another costume: a claim
that covers the whole file, resting on evidence gathered from part of it. The
header said "re-derived", the reader has no way to tell which paragraphs that
covers, and the confident label is what makes it expensive - a note marked
`behind` gets re-checked, a note marked re-derived does not.

All 33 were then resolved against HEAD, by AST for definitions and by reading
the line otherwise. The split was not random:

- **21 resolved correctly.** Every `plugin/crew/hooks/scripts/crew_endpoints.py`
  citation still lands on the exact `def` it names, as do the four into
  `plugin/crew/hooks/scripts/_test/run-tests.sh`, the one into
  `plugin/crew/hooks/scripts/_common.sh`, and both gizmoduck command citations.
  Those files did not move between the two anchors.
- **12 were wrong**, all in the three files that grew: `crew_state.py`,
  `pm_brief.py` and `plugin/crew/agents/pm.md`. The errors were large, not
  off-by-one - `TRIGGERS` was cited at `:486`, which is a blank line inside
  `archive_stale_handoff`'s docstring; it is at `:833`. `DISPATCH_PATH` was
  cited at `:1048`, a `hashlib.blake2b` call; it is at `:1592`.

Two of the twelve were found only because a blank cited line is detectable
without knowing what the line should say. The other ten needed the name to be
checked against the text at the line it claimed, which is the only check that
distinguishes a stale number from a correct one when both point at real code.

**The reusable form.** A re-derivation cannot be verified by the thing doing the
re-deriving. Diff the new note against the old one and treat every surviving
line with a citation on it as unverified until something independent resolves
it, because those are exactly the lines the re-derivation did not touch - and
they are invisible from inside the work, since every paragraph you actually
rewrote looks right when you read back over it.
