anchor: useful-claude-add-ons@d61342c3

# crew

The `crew` plugin: a virtual dev team of context-isolated agents, slash
commands, bundled skills, and deterministic hooks. Registered in
`.claude-plugin/marketplace.json` (name `crew`, source `./plugin/crew`) at
version `0.16.25`, matching `plugin/crew/.claude-plugin/plugin.json:2-3`.
(Was `0.16.12` at the previous anchor. The thirteen bumps in between are not
all crew-substantive; the three that changed what this note documents are
`0.16.22` — `crew_state.py` split at the endpoint ledger, commit `ac93221d` —
`0.16.23` — twelve more domain specialists and three folded roles, commit
`24ea0119` — and `0.16.24` — the sabotage harness restore guards, commit
`4e2bfb78`. Both version sites move together — `check_versions`
(`scripts/check-marketplace.py:298`) compares "has the directory changed since
the version was set", which `_verify/smoke.sh` does not run.)

## Re-anchor provenance - 3167721f -> 1f97e51c, 2026-09-06

The per-path check named eight cited paths as changed in the window:
`.claude-plugin/marketplace.json`, `CLAUDE.md`, `TODO.md`,
`plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`,
`plugin/crew/agents/pm.md`, `plugin/crew/commands/work.md`, and
`plugin/crew/hooks/scripts/crew_state.py`. The last one is the expensive one:
`crew_state.py` was **split**, so every `path:line` citation into it was
suspect on arrival rather than merely aged.

What that split did, and why it invalidates coordinates rather than claims:
`crew_state.py` was at pylint's `max-module-lines=3300` with five lines to
spare (`plugin/crew/hooks/scripts/crew_common.py:3-5`), so the endpoint ledger
moved wholesale to `plugin/crew/hooks/scripts/crew_endpoints.py` (978 lines)
and the three shared readers to `plugin/crew/hooks/scripts/crew_common.py` (80
lines). `crew_state.py` re-exports eight names — `GIT_TIMEOUT`,
`dict_or_empty`, `git_out`, `read_text` from `crew_common`, and
`declare_endpoint`, `load_endpoints`, `read_endpoints`,
`record_scan_artifact`, `scan_artifact_path` from `crew_endpoints`
(`plugin/crew/hooks/scripts/crew_state.py:25-31`) — so `crew_state.<name>`
keeps resolving for callers, which is exactly why a stale citation into
`crew_state.py` can still *look* right to a grep. It is not: those functions'
bodies are in the other file now. `plugin/crew/tests/test_module_split.py`
exists for the matching hazard on the test side (a re-export is a second
binding, so patching `crew_state.read_endpoints` changes a name nothing
reads — a patch that passes while proving nothing).

Re-checked against source at this anchor, not inferred:

- Version is `0.16.25` in **both** `.claude-plugin/marketplace.json` and
  `plugin/crew/.claude-plugin/plugin.json:2-3`.
- Every `path:line` in this file was re-resolved by reading the current file.
  The ones that moved are listed in each section below; the ones that did not
  are `plugin/crew/hooks/scripts/_common.sh:38-43`,
  `scripts/install-prerequisites.sh:859` and
  `scripts/install-prerequisites.ps1:843`.
- Counts were re-counted, not carried forward. So was the codemap's own
  subsystem count, which had grown from 4 to 10.

**Not verified at this anchor, stated as an unknown rather than guessed:**

- Nothing in this note was verified by *running* crew's test suite. Every
  claim below is read off source. `plugin/crew/tests/` names
  `test_module_split.py`, `test_role_ladder.py`, `test_endpoints.py` and
  `test_sabotage_harness.py` as the committed guards for the split, the role
  roster, the ledger and the sabotage harness respectively — that those files
  exist is DERIVED; that they currently pass is **not checked here**.
- `plugin/crew/hooks/scripts/crew_common.py:3` says the split landed "in
  0.16.21"; the commit that shipped it (`ac93221d`) is titled 0.16.22. One of
  the two is off by a patch version and this note does not resolve which —
  recorded so the discrepancy is not re-discovered as new.
- Two comments **outside** this note still point at the pre-split location:
  `.gitignore:289` cites line 407 of `crew_state.py` for the codemap path (the
  read is at `plugin/crew/hooks/scripts/crew_state.py:395`), in the bare
  filename-plus-line form `CLAUDE.md` warns against; and `.gitignore:294` calls
  `read_endpoints` "crew_state.py's" when it is now
  `plugin/crew/hooks/scripts/crew_endpoints.py:914`. Not fixed here — this
  note's scope is this file.

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

**DERIVED**, counted directly rather than trusted from any one description:

| | Count | How counted |
|---|---|---|
| Agents | 29 | `ls plugin/crew/agents/*.md` |
| Commands | 24 | `ls plugin/crew/commands/*.md` |
| Skills | 17 | subdirectories of `plugin/crew/skills/` (`find-skills` plus 16 `crew-*` skills) |

`.claude-plugin/marketplace.json`'s own `crew` entry describes it as "29
context-isolated agents (13 tiered, 15 domain specialists opted into per repo,
and the standing manager), 24 slash commands, 17 bundled skills" — this agrees
exactly with the counts above, and the 13/15/1 split agrees with the code:
`ROLE_TIERS` has 13 entries (`plugin/crew/hooks/scripts/crew_state.py:611-628`),
`SPECIALIST_ROLES` has 15 (`plugin/crew/hooks/scripts/crew_state.py:659-675`),
and `agents/pm.md` is the standing manager, on neither list.

**The roster changed shape at `24ea0119` (0.16.23), which is what made the
previous version of this section wrong.** It recorded 17 agents and 3
specialists. The specialist set went 3 → 15: the three that were there
(`sharepoint-developer`, `power-automate-specialist`, `node-developer`) plus
eleven language/platform roles (`php-pro`, `python-pro`, `dotnet-core-expert`,
`dotnet-framework-4.8-expert`, `angular-architect`, `react-specialist`,
`rust-engineer`, `sql-pro`, `terraform-engineer`, `network-engineer`,
`windows-infra-admin`) and one web-grounded QA role (`qa-researcher`). The
tiered ladder did **not** grow: it is still 13, unchanged from the previous
anchor.

Three roles the same request named were **folded into existing ladder roles
rather than shipped as agents** — so looking for them in `agents/` and finding
nothing is the designed outcome, not a gap (DERIVED from `24ea0119`'s commit
body, cross-checked against the absence of the three filenames in
`plugin/crew/agents/`):

- `cloud-architect` → `infrastructure-architect` (multi-cloud, migration
  sequencing, RTO/RPO-first DR)
- `security-engineer` → `security` (pipeline, supply chain, least-privilege
  grants, per-change threat modelling)
- `database-administrator` → `dba` (backup, replication, failover, pooling as
  review questions a change can invalidate)

Every specialist still sits off the tier ladder — no tier grants one, and
onboarding one leaves `tier` alone. `roles_for_tier`
(`plugin/crew/hooks/scripts/crew_state.py:690-692`) reads only `ROLE_TIERS`;
`known_role` (`plugin/crew/hooks/scripts/crew_state.py:678-687`) is what keeps
a deliberately-onboarded specialist from being reported as a typo on every
upgrade. The reason is stated in the code rather than only in prose
(`plugin/crew/hooks/scripts/crew_state.py:635-658`): "this repo does
SharePoint" is a fact about one checkout, not a defect class every repo can
have.

**JUDGEMENT:** the enumerate-by-name form this section previously used is the
thing that rotted. `24ea0119` deliberately replaced the by-name lists in
crew's own prose with pointers at the table a test checks, because a list in
two places drifts. The names above are kept here anyway — a codemap that says
only "see the table" tells a reader nothing — but they are the part of this
section most likely to be stale first, and `SPECIALIST_ROLES` is the
authority.

**A real, currently-shipping discrepancy, found by cross-checking rather than
assumed — now much wider than it was:** both install scripts describe the same
plugin differently. `scripts/install-prerequisites.sh:859` and
`scripts/install-prerequisites.ps1:843` both still read *"crew - Virtual dev
team: 11 agents, 21 commands, safety hooks"* — unchanged since the last
refresh, so now **eighteen** fewer agents and three fewer commands than both
the marketplace entry and the actual directory contents (it was six and three
at the previous anchor, three and three before the first three specialists
shipped). This is stale menu-label text, not a registration failure (nothing
in `check-marketplace.py` or `_verify/smoke.sh` checks that a catalog *label's
prose* matches a directory count — only that catalog *rows exist*, per
`check_docs` at `scripts/check-marketplace.py:263`, documented in
`marketplace-registration.md`). **Not fixed here** — this note may edit only
itself; recorded so the widened gap does not get re-discovered as new.

## Hooks

`plugin/crew/hooks/hooks.json` registers **five** events: `SessionStart`,
`PreToolUse`, `PreCompact`, `Notification`, `Stop` (read via
`json.load(...)['hooks'].keys()`). The previous version of this section said
"four events" and then listed five — corrected here; the list was right and
the number was not.

Every bash `command` entry has a `shell: "powershell"` sibling for the same
event, counted per event rather than spot-checked: SessionStart 3+3,
PreToolUse 2+2, PreCompact 1+1, Notification 1+1, Stop 3+3.
`plugin/crew/hooks/hooks.json:3-11` shows the `SessionStart` pairing
(`handoff-read.sh`/`.ps1`, `pm-brief.sh`/`.ps1`, `platform-sync.sh`/`.ps1`) —
the previous anchor cited lines 1-19 of the same file and it is now only
38 lines long, so the range was re-taken. This matches the "branch on the tool, not
the OS" and "register each event once per flavour" rules already stated in
`CLAUDE.md` — not restated here beyond confirming the current file does it.

`PreToolUse` is the one event that matches on tool rather than firing
unconditionally: `guard.sh`/`guard.ps1` and `promote-gate.sh`/`promote-gate.ps1`
are registered with `matcher: "Bash"` and `matcher: "PowerShell"` respectively
(`plugin/crew/hooks/hooks.json:12-19`).

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
(`plugin/crew/hooks/scripts/crew_state.py:1101`,
`DISPATCH_DIR = (".work", "dispatch.d")`, with the reasoning at
`plugin/crew/hooks/scripts/crew_state.py:1084-1100`), bounded by
`DISPATCH_FILES_MAX` (`plugin/crew/hooks/scripts/crew_state.py:1108`). The
legacy single file is still read (`DISPATCH_PATH` at
`plugin/crew/hooks/scripts/crew_state.py:1048`; the legacy history and slot
are drained at `plugin/crew/hooks/scripts/crew_state.py:1274-1300`,
`read_dispatch` at `:1413`) so an older record is not silently discarded.

**Refined at this anchor:** the previous version called the legacy file "a
lower-priority fallback", which understates the mechanism. Priority is
*structural*, not a timestamp comparison: `_merge_history`
(`plugin/crew/hooks/scripts/crew_state.py:1306-1318`) ranks entries by
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

`plugin/crew/hooks/scripts/crew_state.py` is what reads `.crew/codemap/` and
turns it into `knowledge.subsystems` for the PM's SessionStart brief. This
matters directly to the writer of any codemap file, so it is recorded here
rather than assumed. **Every line number in this section was re-resolved at
this anchor; all of them had moved.**

- `read_knowledge()` (`plugin/crew/hooks/scripts/crew_state.py:387-415`, was
  cited `:399-428`) lists every file directly under `.crew/codemap/`
  (`plugin/crew/hooks/scripts/crew_state.py:395`). A file counts as a
  subsystem if its name ends in `.md` **and** is not in `_NOT_SUBSYSTEMS`
  (`plugin/crew/hooks/scripts/crew_state.py:234`, was `:225`:
  `frozenset({"INDEX.md", "UPGRADE.md", "MIGRATION.md"})`).
  **Corrected at this anchor:** this codemap now contributes **10**
  subsystems, not the 4 previously recorded — `crew.md` (this file),
  `install-scripts.md`, `localgpu.md`, `marketplace-registration.md`,
  `mcp-servers.md`, `obsidian-vault.md`, `repo-docs.md`, `skills-itsm.md`,
  `skills-security-ops.md`, `verification-harness.md`. `INDEX.md` and
  `UPGRADE.md` are the two excluded names actually present; `MIGRATION.md` is
  in the frozenset but does not exist here.
- Each counted file is checked for an anchor line matching `_ANCHOR_RE`
  (`plugin/crew/hooks/scripts/crew_state.py:229-231`, was `:220-222`):
  `^anchor:\s*(?:\S*@)?([0-9a-f]{7,40})\s*$`, case-insensitive, matched
  anywhere in the file (`re.MULTILINE`). The comparison is at
  `plugin/crew/hooks/scripts/crew_state.py:409` and truncates **both** sides
  to 7 chars, so an 8- or 40-character anchor matches exactly as well as a
  7-character one. If it does not match HEAD, the file's stem is added to
  `knowledge.behind` — surfaced as the `knowledgeBehind` trigger
  (`plugin/crew/hooks/scripts/crew_state.py:2095`, was cited `:2015`).
  Diagrams use a separate `_DIAGRAM_ANCHOR_RE`
  (`plugin/crew/hooks/scripts/crew_state.py:293`) with the same truncating
  comparison at `plugin/crew/hooks/scripts/crew_state.py:467`.
- `diagramsMissing` only fires once `knowledge.subsystems` is truthy
  (`plugin/crew/hooks/scripts/crew_state.py:2101-2102`, was cited
  `:2017-2022`, comment: *"A repo with no codemap has not decided what its
  subsystems ARE yet"*) — so writing this codemap is also what turns on the
  nag for missing per-subsystem diagrams.

**Superseding the previous version's note that "the line numbers in this
section moved by roughly +900":** they moved again, and not by a single
offset. `crew_state.py` is now 2313 lines, down from its pre-split peak, and
the shift is negative in the low ranges (`_ANCHOR_RE` moved +9, `read_knowledge`
moved −12) and positive in the high ones (`knowledgeBehind` moved +80). A
single-offset correction would have been wrong for most of them; each was
re-read.

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
and the one entry point named in `plugin/crew/agents/pm.md:276` and
`plugin/crew/commands/work.md:64` for turning a researched candidate into a
fact. Both of those still invoke it through the `crew_state.py` CLI
(`crew_state.py --root . --declare-endpoint …`) — the *implementation* moved
modules, the *command line* did not, which is why those two files needed no
change in the split.

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
(`plugin/crew/hooks/scripts/crew_state.py:2092`), gated entirely on
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

Placed in `TRIGGERS` (`plugin/crew/hooks/scripts/crew_state.py:486`) at
`:501`, just below `handoffPending` (`:493`) and above `graphStale` (`:502`):
a live, unscanned endpoint is an actionable security gap like an unfinished
handoff, not a documentation-freshness finding.

**Corrected at this anchor:** the "candidates are not confirmed until
researched" text is no longer in the `FINDINGS` entry. `pm_brief.FINDINGS`
now interpolates two pre-composed fields
(`plugin/crew/hooks/scripts/pm_brief.py:132-135`,
`"{endpointSummary}"` / `"{endpointAction}"`) and the sentence lives in
`_endpoint_fields` (`plugin/crew/hooks/scripts/pm_brief.py:249`, the literal at
`:303`: *"candidates are NOT confirmed endpoints until researched"*). The
claim is still true; its location is not where it was. The split into
declared/candidate is keyed on `status`, not `source`
(`plugin/crew/hooks/scripts/pm_brief.py:281-282`), so a record whose two fields
disagree still renders as a candidate rather than a confirmed fact — and it is
pre-composed so a candidates-only state never reads "0 declared endpoint(s)"
with an action telling the user to scan none of them.

Gizmoduck's own `plugin/gizmoduck/commands/report.md:29,37` and
`plugin/gizmoduck/commands/scan.md:27` document the seam this closes: when a
scan targets a declared endpoint, the report lands at that record's computed
path (`--scan-artifact-path`) and freezes it there (`--record-scan-artifact`)
afterward, rather than at gizmoduck's own default location.

## Citation freshness

The previous version of this file carried a section warning that every
`path:line` below a certain point predated a merge and was "a candidate for
drift". That warning is discharged: at `1f97e51c` every citation in this file
was re-resolved by reading the current file, and the ones that moved are named
inline in the section that carries them. What is **not** claimed is that the
underlying behaviour was re-tested — see the explicit unknowns in the
re-anchor provenance section above.

## What this file does not cover

Agent role definitions, command bodies, and the config precedence for which
model backs each role (`dev.roles`, `dev.provider`, `dev.fallback`) are not
traced here; this note covers `crew` at the level of "what exists and how it
is wired". `crew:reference` or `crew:roster` are the existing tools for the
finer grain and were not re-derived here. The other nine subsystem notes in
`.crew/codemap/` cover their own areas; `INDEX.md` is the table of contents.
## Entry points

- `plugin/crew/hooks/scripts/crew_state.py:2152` — `worktree_root(cfg, repo_root)`, the one resolver for `worktree.root`. Unset/blank/non-string means the checkout's parent, which is what crew did before the key existed.
- `plugin/crew/hooks/scripts/crew_state.py:2182` — `worktree_path(cfg, repo_root, branch)`, `<worktree_root>/<repo>-<digest>-<branch>`. Flattens every separator and `:` so a branch name cannot add a directory level.
- `plugin/crew/hooks/scripts/crew_state.py:2410` — the `--worktree-path BRANCH` CLI flag (`-` for the root alone). This is the only way a command can obtain the path; without it the setting resolved and nothing runnable returned it.
- `plugin/crew/hooks/scripts/crew_config.py:421` — `null_shadows`, and `:467` `without_null_shadows`: the rule that a repo `null` does not shadow a machine-global value. Called from `resolve_config` (`:611`) and `explain_config` (`:731`), the same helper in both so the run and the report cannot disagree.

## Owns data

- `worktree.root` in `.crew/config.json` and `~/.claude/crew/config.json`, defaulting from `crew_state.WORKTREE_DEFAULTS` (`plugin/crew/hooks/scripts/crew_state.py:610`). Inheritable globally — it is a fact about which disk has room, not about a checkout.
- `crew_state.SPECIALIST_ROLES` (`plugin/crew/hooks/scripts/crew_state.py:725`) — 36 domain specialists off the tier ladder, up from 15. `ROLE_TIERS` is unchanged at 13; with `pm` that is the 50 files in `plugin/crew/agents/`.

## Calls out to

- `crew_config.resolve_config` from `crew_state.main`'s `--worktree-path` branch, imported INSIDE the function — the two modules must not import each other at top level.
- `crew_state._repo_digest` (`plugin/crew/hooks/scripts/crew_state.py:628`) hashes `normcase(realpath(repo_root))` with `blake2b`, degrading to `abspath` when `realpath` raises, so a hook never dies for an unstattable path.
- `_SEPARATORS` (`plugin/crew/hooks/scripts/crew_state.py:623`) is derived from `os.sep`/`os.altsep` rather than written as a regex character class.
