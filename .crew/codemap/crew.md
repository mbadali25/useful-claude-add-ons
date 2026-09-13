anchor: useful-claude-add-ons@a573ca24
verified: 2026-09-13
re-derived, not re-verified: every live claim below was taken from the source at
this anchor. The historical sections are accounts of past work and are marked as
such; their coordinates were re-taken even where their stories did not change.
scope of that claim, measured rather than asserted: see "Citation freshness".


# crew

The `crew` plugin: a virtual dev team of context-isolated agents, slash
commands, bundled skills, and deterministic hooks. Registered in
`.claude-plugin/marketplace.json` like every other entry here.

## Re-derivation provenance - 7b0d8f3a -> a573ca24, 2026-09-13

**The previous anchor resolved, so the per-path check could run**, which is the
first time that has been true for this note. `git diff --name-only
7b0d8f3a..HEAD -- <the 17 repo paths this note cites>` returns nine:
`.claude-plugin/marketplace.json`, `.crew/codemap/verification-harness.md`,
`plugin/PLUGINS.md`, `plugin/crew/CONFIG.md`, `plugin/crew/agents/pm.md`,
`plugin/crew/hooks/scripts/_test/run-tests.sh`,
`plugin/crew/hooks/scripts/crew_config.py`,
`plugin/crew/hooks/scripts/crew_state.py` and
`plugin/crew/hooks/scripts/pm_brief.py`. Fourteen commits touched
`plugin/crew/` in the range.

**The eight cited files that did NOT change are closed by that result, not by
re-walking them**: `plugin/crew/hooks/hooks.json`,
`plugin/crew/hooks/scripts/_common.sh`,
`plugin/crew/hooks/scripts/crew_endpoints.py`,
`plugin/crew/commands/work.md`, `plugin/gizmoduck/commands/report.md`,
`plugin/gizmoduck/commands/scan.md`, `.crew/config.json` and
`.crew/metrics.md`. Every citation into them — including the interior ranges
this pass never re-measured, such as `crew_endpoints.py:50-78`, `:130-182`,
`:204-252`, `:468-496` and `:684-710` — is current *because the file is byte-
identical to the anchor those ranges were taken at*. That is what the per-path
check is for, and saying so is cheaper and more honest than re-deriving them
and implying the mechanism was not trusted.

**How the figures below were obtained.** A script imported `crew_config` and
`crew_state` directly and walked `plugin/crew/`; line numbers come from an AST
walk over the four modules, not from grep, so a name appearing in a comment or a
string cannot be mistaken for its definition. Ranges (`def` start to
`end_lineno`, docstring start to end) come from the same walk. Nothing in that
script reads the previous version of this file.

**Not verified at this anchor, stated as an unknown rather than guessed:**

- No hook was executed. Every claim about hook *behaviour* is read from source
  and from the committed suites, not observed.
- The agent and command bodies were counted, not read. What each role does is
  outside this note, as it has always been.
- `.crew/verify.json` is absent from this checkout (gitignored), so nothing
  about per-path verify routing could be checked here. See
  `.crew/codemap/verification-harness.md`, where that gap is the dominant fact.
  Crew 0.19.21 made that absence its own reported outcome in `/crew:review`
  step 0b rather than a silent skip; this note still cannot check the routing.
- `.crew/endpoints.json` does not exist here either, so the endpoint section
  below describes the code that would read it, never a record it read.

### Older provenance - d61342c3 -> 7b0d8f3a, 2026-09-12

Six merged PRs between those two anchors rewrote exactly what this note
describes — the config layering and what a machine-global file may supply
(#102, #105, #106), ten previously-undeclared keys and the consent key held
back from the global layer (#106), and the codemap anchor mechanism this note
explains to its own future writer (#108) — so that pass re-derived rather than
re-pointed. `useful-claude-add-ons@d61342c3` named no object in this
repository: `519754fa`, which wrote it, was a squash merge, so the branch
commit its writer recorded died with the branch, and the per-path check could
not run at all. Crew 0.19.13 fixed the writer — it records `git merge-base HEAD
origin/main`, a commit already on the trunk — which is why the check *did* run
this time.

### Older provenance - b56d41f -> 3167721f, 2026-09-05

Kept because it records what an earlier pass did and did **not** cover. That
pass explicitly declined to re-verify `crew_state.py`'s internals, on the
grounds that the file had not moved in its diff window, and said: "If
`plugin/crew/hooks/scripts/` appears in a future diff against this anchor,
treat this section's guarantee as spent." It did appear, and it is spent. That
pass also fixed 9 anchors written relative to `plugin/crew/hooks/scripts/`
rather than repo-relative, which is the form that cannot be pasted into
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
entries (`plugin/crew/hooks/scripts/crew_state.py:1125-1142`),
`SPECIALIST_ROLES` has **40**
(`plugin/crew/hooks/scripts/crew_state.py:1173-1214`), and `agents/pm.md` is
the standing manager on neither list. 13 + 40 + 1 = 54. DERIVED: the set of
`.md` stems in `plugin/crew/agents/` minus `ROLE_TIERS | SPECIALIST_ROLES` is
exactly `{pm}`, and the reverse difference is empty -- so no role is named in
code without an agent file, and no agent file is unreachable from the roster.
That two-way check is the point; counting one direction only would miss a
specialist that exists on disk and is named nowhere.

### The count claim inverted between the anchors, and this is the correction

**The previous version of this note said `.claude-plugin/marketplace.json:217`
was wrong and that "no place in the repo states crew's agent count correctly",
listing install scripts at 11, `plugin/PLUGINS.md:17` and the marketplace entry
at 29, `plugin/PLUGINS.md:153` at 14, and `README.md:165` at 50. All five of
those readings are now false.** `5d2e2950` ("crew 0.19.20: correct the agent
count everywhere it is claimed", #124) fixed every one of them, and
`plugin/PLUGINS.md:153` is no longer a count at all — it is the heading
`### Agents — one per agents/*.md`, with `:157` now saying outright that the
table below it is abridged and that `crew_state.SPECIALIST_ROLES` is the
register.

This inversion is the whole reason this file was refreshed first. A reader who
trusted the old paragraph would go to `marketplace.json:217`, find a correct
entry, and "fix" it back to 29.

**DERIVED at this anchor, by sweeping every tracked `.md`/`.json`/`.sh`/`.ps1`
for a number adjacent to "agent"/"subagent" on a line that mentions crew:**
every live, present-tense claim about crew's agent count now reads 54.

| Place | Says |
|---|---|
| `.claude-plugin/marketplace.json:217` | 54 context-isolated agents (13 tiered, 40 domain specialists, and the standing manager), 24 slash commands, 17 bundled skills |
| `plugin/PLUGINS.md:17` | 54 agents, 24 commands, 17 skills, 20 hook entries (10 scripts × `.sh`/`.ps1`) across 5 events |
| `README.md:165`, `INSTALLATION.md:250` | 54 subagents, 24 slash commands, 17 bundled skills, 20 hook entries across 5 events |
| `scripts/install-prerequisites.sh:900`, `.ps1:855` | 54 agents, 24 commands |

Thirteen other hits carry a different number and every one is correct where it
sits: `INSTALLATION.md:250` and `README.md:165` name *other* plugins' counts on
the same line as crew's; `README.md:590`, `plugin/README.md:370` and
`plugin/UPDATE.md:366` are the crew 0.15.1 release note ("taking crew to 14
agents"), true as history; `TODO.md:590`, `:593`, `:607` and `:635` quote the
old wrong strings in the record of what #124 replaced; `docs/HANDOFF.md:87` and
the two `work-log/2026-08-23-session-01/` files are dated session records.

**What did NOT change is the mechanism.** #124 corrected nine files of prose and
added no checker, and `check-marketplace.py` still contains no reference to
`ROLE_TIERS`, `SPECIALIST_ROLES` or any agent count — `check_catalogs`,
`check_menu_parity` and `check_group_parity` compare keys and booleans, never
descriptive prose. So the repo is currently right about this and nothing keeps
it right. The next specialist added to `SPECIALIST_ROLES` will make nine files
wrong again, silently, and this is the same class `marketplace-registration.md`
records.

**JUDGEMENT, and it is why this section does not list specialists by name.**
A version two anchors back enumerated all fifteen. That list is what rotted
first: the set went 15 -> 40 while the prose stayed, and a reader checking three
names off would have had no signal the other twenty-five existed.
`SPECIALIST_ROLES` is the authority and is cheap to print. A codemap that
reproduces a list which lives in code has taken on a maintenance burden it
cannot discharge — and `plugin/PLUGINS.md:157` now makes the same concession
about its own table.

Structural facts about the roster that are *not* just counts, and that survived
re-derivation unchanged:

- Every specialist sits off the tier ladder. No tier grants one, and onboarding
  one leaves `tier` alone -- `roles_for_tier`
  (`plugin/crew/hooks/scripts/crew_state.py:1229`) reads only `ROLE_TIERS`.
- `known_role` (`plugin/crew/hooks/scripts/crew_state.py:1217`) is what keeps a
  deliberately-onboarded specialist from being reported as a typo on every
  upgrade.
- The reason is in the code rather than only in prose: "this repo does
  SharePoint" is a fact about one checkout, not a defect class every repo has.

## Hooks

`plugin/crew/hooks/hooks.json` (38 lines) registers **five** events and **20**
hook entries. The file did not change between the anchors, so these figures are
current by the per-path check as well as by the `json.load` that re-counted
them:

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

**The two-flavour rule is a live defect class, not a settled one.** Crew 0.19.23
(`a573ca24`) closed three command-guard bypasses and one fail-open promote gate,
and every one of them had to be fixed in `guard.sh` *and* `guard.ps1`, each in
that shell's own syntax: `terraform -chdir=infra apply`, `git push 2>&1 --force`
and `git reset HEAD --hard` were allowed by both flavours, and
`promote-gate.{sh,ps1}` each read a raised exception from their own check as
"no unmet preconditions" and let the deploy through. The regression cases live in
`plugin/crew/tests/test_guard_bypasses.py` and
`plugin/crew/tests/test_promote_gate_fails_closed.py`, which run both flavours
against the same payloads for exactly this reason.

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
(`DISPATCH_DIR = (".work", "dispatch.d")` at
`plugin/crew/hooks/scripts/crew_state.py:1792`, with the reasoning at
`plugin/crew/hooks/scripts/crew_state.py:1772-1791`), bounded by
`DISPATCH_FILES_MAX` (`plugin/crew/hooks/scripts/crew_state.py:1799`) and, per
branch, by `DISPATCH_BRANCHES_MAX`
(`plugin/crew/hooks/scripts/crew_state.py:1770`). The legacy single file is
still read (`DISPATCH_PATH` at
`plugin/crew/hooks/scripts/crew_state.py:1739`; opened by `_read_record_file`
(`plugin/crew/hooks/scripts/crew_state.py:1912-1939`) and drained into history
by `_history_items` (`plugin/crew/hooks/scripts/crew_state.py:1942-1994`), with
`read_dispatch` at `plugin/crew/hooks/scripts/crew_state.py:2104-2165`) so an
older record is not silently discarded.

Priority between the two is *structural*, not a timestamp comparison:
`_merge_history` (`plugin/crew/hooks/scripts/crew_state.py:1997-2101`; the tier
rule is stated in its own docstring at
`plugin/crew/hooks/scripts/crew_state.py:2000-2008` and enforced at `:2095`)
ranks entries by `(tier, sort key)`, with `.work/dispatch.d/` at tier 1 and
anything read out of the legacy `dispatch.json` at tier 0, so nothing in the
legacy file can outrank the store *no matter what its `at` says*. The hazard
that motivates it is a legacy record with far-future timestamps — a clock that
ran ahead, a hand edit, a restored backup — evicting the dispatch that had just
happened.

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

**DERIVED (`plugin/crew/hooks/scripts/_test/run-tests.sh:74-201`, range
re-taken at this anchor — it was cited as `:74-148` and the block now runs 53
lines further, because a third self-proof was added to it): that PATH scrub was
fixed twice more after `0bf0c2f3`, and the reason is worth carrying — CI was red
for both.** It compared `PATH` entries as *strings*, so on a merged-`/usr`
Linux — every GitHub runner — dropping the literal `/usr/bin` left `/bin` behind
pointing at the same directory, jq stayed reachable, and the suite FATAL'd
rather than run. Fixed by resolving each entry with `cd … && pwd -P` before
comparing (`plugin/crew/hooks/scripts/_test/run-tests.sh:77` for jq's own
directory, `:132` for each `PATH` entry). That exposed the real problem: the
scrub removed jq's whole *directory*, because `PATH` has directory granularity
while the thing being hidden is one file — and on Linux that directory is
`/usr/bin`, holding `python3` and `sh`, the interpreter the no-jq fallback runs
on. It now **substitutes** rather than subtracts: mirrors the directory into a
temp dir as symlinks minus every spelling of jq (`jq`, `jq.exe`, `jq.bat`, …,
enumerated at `plugin/crew/hooks/scripts/_test/run-tests.sh:117`; the bare name
alone was not enough on Windows, where the binary is `jq.exe` plus a chocolatey
`jq.bat` shim), and puts the mirror at the same `PATH` position.

The block now proves itself **three** times, and each proof exists because
skipping it produces a green suite that tested nothing:

| Check | Line | What a silent failure would look like |
|---|---|---|
| the mirror still resolves `jq` | `:121-125` | a scrub that does nothing, so every case takes the jq fast path |
| the scrubbed `PATH` still resolves `jq` | `:167-172` | the same, one layer out |
| **no working python survives the scrub** | `:181-197` | `guard.sh` prints "no jq and no python" and exits 0, so every must-BLOCK case below passes against a guard that never ran |

The third is new since the previous anchor and is the interesting one: it walks
`crew_py`'s own order (`python3`, `python`, `py`), takes the **first** name that
resolves exactly as `crew_py` does, and then *executes* it
(`plugin/crew/hooks/scripts/_test/run-tests.sh:181-191`). Checking the rest of
the list would pass where `crew_py` fails.

**Known open issue, not fixed, recorded in `TODO.md:383-413` (repo root) rather
than here — re-confirmed still open at this anchor:** `crew_py()`
(`plugin/crew/hooks/scripts/_common.sh:38-43`, citation unchanged and the file
unchanged since the previous anchor) returns the first of
`python3`/`python`/`py` that `command -v` *resolves*, not the first that
actually *runs*. On Windows, `command -v python3` can resolve the `WindowsApps`
App Execution Alias stub, which opens the Microsoft Store and produces no
output — so a guard fed that stub sees an empty result and stands down
silently, on exactly the platform where a guard has already shipped broken once
before. `TODO.md` records this as reproduced (128 → 77 passed with the real
interpreter removed from `PATH`) and gives the fix shape (execute each
candidate, don't just resolve it).

**The distinction that is easy to lose:** the harness now executes the
interpreter, `crew_py` still does not. The suite protects itself from a false
green; the shipped guard is unchanged. A reader who sees `run-tests.sh:181-197`
and concludes the TODO is closed has read the test for the product.

## `crew_state.py` and this very directory

`plugin/crew/hooks/scripts/crew_state.py` (**3170** lines at this anchor) is what
reads `.crew/codemap/` and turns it into the PM's SessionStart brief. That makes
it the one section of this note a codemap writer has to get right, so it is
re-derived rather than carried forward. **Every line number below came from an
AST walk at this anchor, not from the previous version.**

- `read_knowledge()` (`plugin/crew/hooks/scripts/crew_state.py:692-763`) lists
  every file directly under `.crew/codemap/`. A file counts as a subsystem if
  its name ends in `.md` **and** is not in `_NOT_SUBSYSTEMS`
  (`plugin/crew/hooks/scripts/crew_state.py:539` --
  `frozenset({"INDEX.md", "UPGRADE.md", "MIGRATION.md"})`). This codemap
  contributes **10** subsystems out of 12 `.md` files. `INDEX.md` and
  `UPGRADE.md` are the two excluded names actually present; `MIGRATION.md` is in
  the frozenset and does not exist here.

- Each counted file is checked for an anchor line matching `_ANCHOR_RE`
  (`plugin/crew/hooks/scripts/crew_state.py:534-536`):
  `^anchor:\s*(?:\S*@)?([0-9a-f]{7,40})\s*$` -- anchored to the start of a
  line, case-insensitive, `re.MULTILINE`. **The `\s*$` is load-bearing for
  anyone editing one of these files:** anything after the sha on that line, a
  parenthetical note included, stops the regex matching and the map reads as
  having no anchor at all. Put commentary on the next line.

- **An anchor resolves to one of three states, not two** (crew 0.19.13,
  `plugin/crew/hooks/scripts/crew_state.py:692-763`):

  | State | Test | What the reader does |
  |---|---|---|
  | current | `sha[:7] == head[:7]` (`:746`, truncating **both** sides, so 8- and 40-char anchors compare exactly as 7-char ones do) | nothing |
  | behind | resolves, but is not HEAD -- probed with `git cat-file -e <sha>^{commit}` | **re-check**: run the per-path diff; empty output means current despite the lag |
  | unresolvable | no anchor, or a sha this repository does not contain | **re-derive**: the per-path diff cannot run at all |

  The third is the state this note's own anchor was in one refresh ago, and the
  first time it has not been. Folding it into "behind" is the repo's named bug
  -- an unknown collapsing into the safe-looking value -- because "behind" is a
  cheap, definite finding and a reader who cannot tell the two apart does the
  cheap thing.

- The distinction is carried into the triggers rather than stopping at the state
  dict. `TRIGGERS` (`plugin/crew/hooks/scripts/crew_state.py:839-869`) holds
  **12** entries, with `knowledgeUnverifiable` (`:860`) sorted deliberately
  **above** `knowledgeBehind` (`:861`) and **below** `graphStale` (`:855`) -- a
  map that cannot be verified outranks one that merely needs re-checking, but a
  map is drawn against the graph, so a stale graph is the earlier input. Both
  are set in `evaluate_triggers`
  (`plugin/crew/hooks/scripts/crew_state.py:2837-2885`) at `:2869` and `:2868`
  respectively -- note that the *evaluation* order there is the reverse of the
  *presentation* order in `TRIGGERS`, and only the latter decides what the brief
  leads with.

- Diagrams use a separate `_DIAGRAM_ANCHOR_RE`
  (`plugin/crew/hooks/scripts/crew_state.py:598-602`), with its own comparison
  at `:814`. It cannot reuse `_ANCHOR_RE`: a bare `anchor:` line is a syntax
  error in a Mermaid source, so the provenance has to live inside a `%%`
  comment. The reason is written out at `:586-597`, which is worth reading
  before touching either regex.

- `diagramsMissing` (`plugin/crew/hooks/scripts/crew_state.py:866`, set at
  `:2875-2876`) fires only once `knowledge.subsystems` is truthy -- a repo with
  no codemap has not decided what its subsystems are yet. So writing this
  codemap is also what turns on the nag for missing per-subsystem diagrams.

**On the growth this file keeps recording about itself:** 2313 lines two
anchors ago, 3023 at the previous one, **3170** here. Of the 22 `crew_state.py`
coordinates this note carries, **17 moved** between the two anchors and 5 did
not (`SCHEMA_CURRENT:54`, `_ANCHOR_RE:534`, `_NOT_SUBSYSTEMS:539`,
`_DIAGRAM_ANCHOR_RE`'s reasoning block, `read_knowledge:692`). Every number in
this section was re-taken; none was adjusted by an offset.

## The endpoint ledger and `endpointUnscanned`

**`plugin/crew/hooks/scripts/crew_endpoints.py` (978 lines) did not change
between the two anchors.** Every citation in this section is therefore current
by the per-path check, at the coordinates the previous pass read off the file
after it was split out of `crew_state.py` at `ac93221d`. Only the citations
into `crew_state.py` and `pm_brief.py` — the two files that did move — were
re-derived here.

`.crew/endpoints.json` (`_ENDPOINTS_PATH_PARTS` at
`plugin/crew/hooks/scripts/crew_endpoints.py:33`; re-admitted in
`.gitignore:298` next to `.crew/codemap/`, same reasoning — a scan obligation
that exists only in one clone's untracked state reaches nobody) holds only
**declared** records — `source: "declared"`, written only by
`declare_endpoint` (`plugin/crew/hooks/scripts/crew_endpoints.py:254`), the
one function allowed to write that source, the only writer of the file at all,
and the one entry point named in `plugin/crew/agents/pm.md:286` and
`plugin/crew/commands/work.md:63-64` for turning a researched candidate into a
fact. `pm.md` *did* change in this range, so that citation was re-checked
rather than carried: the string `--declare-endpoint` occurs exactly once in the
file, on line 286. Both still invoke it through the `crew_state.py` CLI
(`crew_state.py --root . --declare-endpoint …`) — the *implementation* moved
modules, the *command line* did not, which is why neither file needed a change
in the split.

**A false correction stood here from 2026-09-12 until later the same day, and
the retraction is kept rather than deleted because the way it was made is worth
more than the claim was.** This note asserted that `pm.md` named the declare
path **nowhere** — that the pm agent was told to act on declared endpoints
without being told what creates one. It is not true. `plugin/crew/agents/pm.md:286`
spells out the full command, flag included, and has since `b7b7101d`.

The error came from reading that line through a print truncated to about 115
characters. `pm.md:286` is a single table row roughly 700 characters long, and
`--declare-endpoint` sits past the cutoff. Absence from the *output* was read as
absence from the *file*, and the finding was then reported twice and written
into this note as a correction.

That is the same failure as the 33 carried-forward citations recorded below, and
it happened in the pass that found them: a conclusion drawn from a partial view
of the evidence, stated with the confidence of a complete one. The check that
settles it takes one line — count the exact string in the whole file
(`open(p).read().count("--declare-endpoint")` returns 1, re-run at this anchor)
— and it was available the whole time. **When a claim is that something is
absent, search the file, not a rendering of it.** A truncating pretty-printer is
a lossy view, and every `[:110]` in a verification script is a place where
absence can be manufactured.

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
same pattern crew abandoned `dispatch.json` for, above. Re-declaring an
existing id updates `endpoint`/`location`/`ticket` but leaves `status` alone; it
used to force it back to `"open"`, silently reopening a record a human had
closed.

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
function's own docstring says only that, and names the reproduction
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

**The evidence rule has three checks, not two.** `_artifact_confirms_scan`
(`plugin/crew/hooks/scripts/crew_endpoints.py:829`) requires all three, in
order: non-empty (a `touch`ed 0-byte file must not discharge the obligation);
carries the scan marker `_SCAN_MARKER_RE`
(`plugin/crew/hooks/scripts/crew_endpoints.py:791`,
`**Total finding instances:** <n>`, which gizmoduck's report command always
writes); and, when the record names something specific enough to search for
(`_endpoint_needle`, `:794`), the text mentions it. The middle check is the
one an older two-check description of this dropped, and it is the one that
closes a 44-byte to-do note satisfying a bare substring match without a scan
ever having run.

`endpointUnscanned` fires when a record needs an artifact it does not have
(evaluated in `evaluate_triggers`,
`plugin/crew/hooks/scripts/crew_state.py:2837-2885`, at
`plugin/crew/hooks/scripts/crew_state.py:2865`), gated entirely on
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

Placed in `TRIGGERS` (`plugin/crew/hooks/scripts/crew_state.py:839-869`) at
`plugin/crew/hooks/scripts/crew_state.py:854`, below `handoffPending` (`:846`)
and directly above `graphStale` (`:855`):
a live, unscanned endpoint is an actionable security gap like an unfinished
handoff, not a documentation-freshness finding.

The "candidates are not confirmed until researched" text is not in the
`FINDINGS` entry. `pm_brief.FINDINGS`
(`plugin/crew/hooks/scripts/pm_brief.py:103`) interpolates two pre-composed
fields (`plugin/crew/hooks/scripts/pm_brief.py:143-144`,
`"{endpointSummary}"` / `"{endpointAction}"` — both citations unchanged across
this range even though the file moved) and the sentence lives in
`_endpoint_fields` (`plugin/crew/hooks/scripts/pm_brief.py:295-373`, the literal
at `plugin/crew/hooks/scripts/pm_brief.py:349`: *"candidates are NOT confirmed
endpoints until researched"*; the fields are returned from `:370`). The split
into declared/candidate is keyed on `status`, not `source`
(`plugin/crew/hooks/scripts/pm_brief.py:327-328`, with the reasoning at
`plugin/crew/hooks/scripts/pm_brief.py:306`), so a record whose two fields
disagree still renders as a candidate rather than a confirmed fact — and it is
pre-composed so a candidates-only state never reads "0 declared endpoint(s)"
with an action telling the user to scan none of them.

Gizmoduck's own `plugin/gizmoduck/commands/report.md:29,37` and
`plugin/gizmoduck/commands/scan.md:27` document the seam this closes: when a
scan targets a declared endpoint, the report lands at that record's computed
path (`--scan-artifact-path`) and freezes it there (`--record-scan-artifact`)
afterward, rather than at gizmoduck's own default location. Neither file changed
in this range.

## Config, and what a machine-global file may supply

**DERIVED at this anchor by importing `crew_config`.** The full reference is
`plugin/crew/CONFIG.md` (**900** lines, up from 721 at the previous anchor);
this section records only the shape a codemap reader needs and the one
invariant that is easy to break.

Two layers. `~/.claude/crew/config.json` is machine-global -- facts about this
computer. `.crew/config.json` is per-repo and wins where both speak. `schema` is
exempt from global inheritance.

| | Leaves | Source |
|---|---|---|
| `default_config()` | **86** | `plugin/crew/hooks/scripts/crew_config.py:270` |
| `default_global_config()` | **45** | `plugin/crew/hooks/scripts/crew_config.py:383` |
| repo-only | **41** | the difference |

**Both totals rose by exactly one and the difference did not, and the reason is
named rather than inferred:** the single new leaf is `install.policy`, and
DERIVED by set difference it is present in *both* defaults — so it is globally
settable, which is why repo-only held at 41. That is the schema 5 addition:
what crew may do when a skill it needs is not installed. It arrives as
`manual`, which is what crew already did.

`SCHEMA_CURRENT` is **5** (`plugin/crew/hooks/scripts/crew_state.py:54`), up
from 4. `upgradeNeeded` is `schema < SCHEMA_CURRENT` and compares no key sets,
so adding a default needs no schema bump and triggers no migration prompt —
`install.policy` got one because it changes what crew is permitted to do, not
because a key appeared.

**The invariant, and it is enforced in two places that must agree:** what the
global file may *write* is exactly what the global layer may *supply*. Reading
is pruned by `filter_global` (`plugin/crew/hooks/scripts/crew_config.py:624`)
against `default_global_config()`; writing is refused by `plan_global_write`
(`:1510`) against the same object. One object, two gates. A key added to one
path and not the other produces a file that accepts a value and then ignores it,
or rejects a value it would have honoured.

**Consent is not capability**, and `context.autoClear.unsafeFocus` is the live
case. Six of the seven `autoClear` keys are globally settable -- the method is
validated per platform, which makes it a fact about the machine. The seventh is
held out by `AUTOCLEAR_CONSENT_KEYS`
(`plugin/crew/hooks/scripts/crew_config.py:267`,
`("unsafeFocus",)`) and is repo-only. DERIVED at this anchor: `leaf_paths` over
both defaults puts `command`, `delaySeconds`, `enabled`, `method`,
`minHandoffLines` and `windowTitle` in the global set and `unsafeFocus` outside
it. The precedent is `graph.obsidian.confirmed`: consent to act outside the
repo is not something a machine-global file, or a guided flow, may grant on the
user's behalf.

### `pm.authority`

Three values, normalised by `normalise_authority`
(`plugin/crew/hooks/scripts/crew_state.py:1246`) and ordered by `authority_rank`
(`:1260`). The default is `report-only`
(`AUTHORITY_DEFAULT`, `plugin/crew/hooks/scripts/crew_state.py:898`).

| Value | The PM may |
|---|---|
| `report-only` | read and report; dispatch nothing |
| `act` | dispatch roles and do the work, putting open decisions to the user |
| `autonomous` | everything `act` does, and settle its own open decisions |

Read the value as a floor, never as a label: whatever `act` may do,
`autonomous` may do.

**What `autonomous` adds is deciding, not destroying.** `AUTONOMOUS_STOPS`
(`plugin/crew/hooks/scripts/crew_state.py:911-918`) enumerates four things it
may never do unasked, and the list is in code rather than prose so it can be
tested:

- `offboard-role` -- offboarding a role, or removing one from the roster
- `delete-map` -- deleting a codemap file or a diagram
- `rewrite-metrics` -- rewriting `.crew/metrics.md`
- `git-destruction` -- destroying git history or tracked work: force-push,
  branch delete, history rewrite, or `rm` of a tracked file

**Corrected at this anchor, and it is a renamed symbol rather than a moved
line.** The previous version said a widening of `pm.authority` is "the one
config change `plan_global_write` marks specially", citing `widens_authority`
at `crew_config.py:1447`. There is no `widens_authority`: it was renamed
`_widens` (`plugin/crew/hooks/scripts/crew_config.py:1473`, called at `:1591`)
when **`install.policy` became a second ratcheted key**, and the rename is
explained in place at `:1587-1590` — the old name would have had to either lie
about install policy or spawn a sibling flag beside it, and a sibling is how the
two-mechanism failure starts. So the claim is now: a widening of *either*
`pm.authority` or `install.policy` is marked, printed on the dry run and printed
again on the write, and granting either can never happen silently.

The comparison is by **rank, never equality** (`:1576-1586`). It used to read
`after == "act" and before != "act"`, correct only while `act` was the top
tier. With a third tier that is wrong in both directions at once:
`act -> autonomous` computes False, so the widest grant crew offers would ship
unannounced, and `autonomous -> act` computes True, so dialling *down* warns
about a widening. The second is the more corrosive — a warning that fires on
the safe direction is one users learn to click past, which costs the first case
its only defence.

## Citation freshness

Every `path:line` in this file was resolved at this anchor, by one of two
mechanisms, and which one applies is stated where it is used:

1. **Re-derived** — an AST walk over `crew_state.py`, `crew_config.py`,
   `crew_endpoints.py` and `pm_brief.py`, or reading the cited line. This is
   what the nine changed files got.
2. **Closed by the per-path check** — the file is byte-identical between
   `7b0d8f3a` and this anchor, so a citation that was correct there is correct
   here. This is what the eight unchanged files got, and it is why
   `crew_endpoints.py`'s interior ranges are not re-listed as re-derived.

**Measured, not asserted: the byte-identical-line sweep.** The previous pass
claimed full re-derivation in its header and a sweep afterwards found 33
citations sitting on lines it had never touched. That sweep was re-run here,
diffing this file against `git show a573ca24:.crew/codemap/crew.md`.

Of **766** lines, **379** survived byte-identical, and **28** of those carry a
citation. Twenty-two point into the eight files that did not change between the
anchors, so mechanism 2 closes them. The remaining **six** point into files that
*did* change, and all six were re-derived in this pass anyway — they read the
same afterwards because the coordinates genuinely did not move:
`crew_state.py:539` (`_NOT_SUBSYSTEMS`), `crew_state.py:692-763`
(`read_knowledge`), `crew_config.py:267` (`AUTOCLEAR_CONSENT_KEYS`, twice) and
`plugin/crew/agents/pm.md:286` (twice). Each was resolved independently against
HEAD after this file was written: **0 unresolvable, 0 blank, 0 past EOF.**

That is the number to compare against: 33 carried-forward citations last pass,
6 surviving citations this pass and every one of them independently resolved.
The sweep script is not committed — it is twenty lines of `difflib` plus the
resolver above, and a checked-in copy would become another thing to keep
current. Re-derive it; the description here is the specification.

What is **not** claimed: that the behaviour behind those lines was re-tested. No
hook was run. `python -m pytest plugin/crew/tests` on branch
`docs/codemap-refresh-crew` at `a573ca24` (no commits of its own yet) gives
**948 passed, 1 skipped**, up from 886 at the previous anchor — which is
evidence about the code, not about this note's reading of it.

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

- `plugin/crew/hooks/scripts/crew_state.py:2756` - `worktree_root(cfg, repo_root)`, the one resolver for `worktree.root`. Unset, blank or non-string means the checkout's parent, which is what crew did before the key existed.
- `plugin/crew/hooks/scripts/crew_state.py:2786` - `worktree_path(cfg, repo_root, branch)`, `<worktree_root>/<repo>-<digest>-<branch>`. Flattens every separator and `:` so a branch name cannot add a directory level.
- `plugin/crew/hooks/scripts/crew_state.py:2995` - `main`, which carries the `--worktree-path BRANCH` flag (`-` for the root alone). This is the only way a command can obtain the path.
- `plugin/crew/hooks/scripts/crew_state.py:2888-2992` - `collect`, the one function that assembles the whole state a SessionStart brief renders.
- `plugin/crew/hooks/scripts/crew_config.py:719` - `resolve_config`, and `:904` `explain_config`. The run and the report share `null_shadows` (`:529`) and `without_null_shadows` (`:575`) so they cannot disagree about whether a repo `null` shadows a machine-global value.
- `plugin/crew/hooks/scripts/crew_config.py:624` - `filter_global`, the read-side gate; `:1510` `plan_global_write`, the write-side gate. Both judge against `default_global_config()`.

## Owns data

- `.crew/codemap/` - this directory. Read by `read_knowledge` (`plugin/crew/hooks/scripts/crew_state.py:692-763`); ten subsystem files at this anchor, out of twelve `.md` files.
- `worktree.root` in `.crew/config.json` and `~/.claude/crew/config.json`, defaulting from `crew_state.WORKTREE_DEFAULTS` (`plugin/crew/hooks/scripts/crew_state.py:1058`). Globally inheritable - it is a fact about which disk has room, not about a checkout.
- `crew_state.ROLE_TIERS` (`plugin/crew/hooks/scripts/crew_state.py:1125-1142`) - 13 tiered roles, unchanged across this re-derivation.
- `crew_state.SPECIALIST_ROLES` (`plugin/crew/hooks/scripts/crew_state.py:1173-1214`) - **40** domain specialists off the tier ladder, unchanged in count since the previous anchor. With the 13 tiers and `pm`, that is the 54 files in `plugin/crew/agents/`.
- `crew_state.AUTONOMOUS_STOPS` (`plugin/crew/hooks/scripts/crew_state.py:911-918`) - the four things `autonomous` may not do unasked.
- `crew_config.AUTOCLEAR_CONSENT_KEYS` (`plugin/crew/hooks/scripts/crew_config.py:267`) - the keys held out of the global layer because consent is not capability.
- `install.policy` in both layers (`plugin/crew/hooks/scripts/crew_config.py:270` and `:383`) - the schema 5 addition, and the second key `_widens` ratchets.

## Calls out to

- `crew_config.resolve_config` from `crew_state.main`'s `--worktree-path` branch, imported INSIDE the function - the two modules must not import each other at top level.
- `git cat-file -e <sha>^{commit}` from `read_knowledge`, to tell a resolvable anchor from one this repository does not contain. `git_out` returns `None` on any failure, so a missing git lands as "cannot tell" rather than raising out of a SessionStart hook.
- `crew_state._repo_digest` (`plugin/crew/hooks/scripts/crew_state.py:1076`) hashes `normcase(realpath(repo_root))` with `blake2b`, degrading to `abspath` when `realpath` raises, so a hook never dies for an unstattable path.
- `_SEPARATORS` (`plugin/crew/hooks/scripts/crew_state.py:1071`) is derived from `os.sep`/`os.altsep` rather than written as a regex character class.


## What the first re-derivation missed

This section exists because the check that found it was run *after* the file was
written, and nearly was not run at all. It is kept because the sweep it
describes is now a standing step, run again for this pass and reported under
"Citation freshness".

The 2026-09-12 pass claimed in its own header that every live claim was taken
from the source at its anchor. A sweep afterwards - diffing that file against
its previous version and flagging every citation sitting on a byte-identical
line - found **33 citations that had simply been carried forward**. The header
was true of the sections that were rewritten and false of the ones that were
not, and nothing in the file distinguished them.

That is this repository's recurring failure wearing yet another costume: a claim
that covers the whole file, resting on evidence gathered from part of it. The
header said "re-derived", the reader has no way to tell which paragraphs that
covers, and the confident label is what makes it expensive - a note marked
`behind` gets re-checked, a note marked re-derived does not.

All 33 were then resolved against HEAD, by AST for definitions and by reading
the line otherwise. The split was not random:

- **21 resolved correctly.** Every `plugin/crew/hooks/scripts/crew_endpoints.py`
  citation still landed on the exact `def` it named, as did the four into
  `plugin/crew/hooks/scripts/_test/run-tests.sh`, the one into
  `plugin/crew/hooks/scripts/_common.sh`, and both gizmoduck command citations.
  Those files had not moved between the two anchors.
- **12 were wrong**, all in the three files that grew: `crew_state.py`,
  `pm_brief.py` and `plugin/crew/agents/pm.md`. The errors were large, not
  off-by-one - `TRIGGERS` was cited at `:486`, which is a blank line inside
  `archive_stale_handoff`'s docstring; it was at `:833`. `DISPATCH_PATH` was
  cited at `:1048`, a `hashlib.blake2b` call; it was at `:1592`.

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

**The 2026-09-12 numbers are also why this pass leaned on the per-path check
instead of re-walking everything.** Of the 21 that resolved correctly, every one
was in a file that had not changed — which is precisely the population the
per-path diff identifies for free, before any citation is opened. The sweep is
still needed, because a carried-forward citation into a file that *did* change
is invisible to the per-path check; the two together are what make the header's
scope claim measurable rather than aspirational.
