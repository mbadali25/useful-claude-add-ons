# TODO

Findings queued for a later PR. Each carries the `path:line` it came from so it
can be re-verified rather than re-discovered — and so an item that turns out to
be wrong can be closed on evidence.

Opened 2026-09-05 from the codemap pass (`.crew/codemap/`). Every citation here
was checked against source when it was written; anchor `fe538879`.

## Blast radius — act on these first

### 1. `gizmoduck` opened real SDP tickets with no per-item gate — CLOSED 2026-09-05

**Fixed in gizmoduck 0.3.0.** `cmd_tickets`
(`plugin/gizmoduck/scripts/gizmoduck.py:289`) now takes a `create` argument,
wired to a `--create` flag on the CLI. Without it the function never builds the
`description` field, so a plain `tickets` run returns `"mode": "preview"` with
subjects, severities and target counts and **no ticket body**. That is the part
that matters: the flag withholds the payload rather than labelling it. An
earlier draft of this fix emitted the full records under an `authorized: false`
banner, which is a gate in name and a create-ready payload in fact — this repo's
signature defect, and it was caught in review before it shipped.

The three command surfaces that instruct the write were rewritten to match:
`commands/tickets.md` previews and asks before it reaches for `--create`,
`commands/scan.md` no longer files anything on its own, and
`skills/gizmoduck/SKILL.md` step 4 documents both runs and states plainly that
the `[Nuclei <id>]` de-dupe search is not the confirmation — it chooses between
creating a request and noting an open one, and both of those write.

Prose alone could not have closed this. The reason the entry stayed open through
several rounds was that nothing in the plugin performed the write, so there was
no line to put a check on; the answer was to stop producing the thing the write
needs.

**Two things this did not settle, recorded so they are not mistaken for closed:**

- **Whether the SDP MCP server confirms before `sdp_create` is still unread.**
  It was the decisive unknown when this entry was half-closed, and it is still
  unmeasured — settling it needs a way to observe `sdp_create` without filing a
  real ticket. It no longer blocks *this* item, because the gate above does not
  depend on the answer, but a different caller of those tools gets no protection
  from anything written here.
- **`skills/infra-work-ticketing/SKILL.md:209-211` still instructs the
  opposite** — "create the ticket and report what you made in the same turn - no
  confirmation round-trip." That skill is org-wide and was deliberately left
  alone: gizmoduck's commands no longer hand it a fileable payload, but any
  other path that invokes it directly is unchanged. Whether that instruction is
  right for the skill's own purpose is a separate question from this one.

### 2. `mcp-servers/core` credential chain caches its winner permanently

`AdminCredentialChain` (`mcp-servers/packages/core/src/adminAuth.ts:48-109`)
stores whichever link first succeeds in `this.resolved` and never retries an
earlier link for the process lifetime. Deliberate — the comment at `:44-46`
says so — but the consequence is that fixing `MS_ADMIN_CLIENT_SECRET` after
`cli` or `device` has won changes nothing until restart, and nothing says so.

Not necessarily a code change. A log line naming which link won, once, would
turn a silent wrong-identity into an obvious one.

### 3. `scopesOverride` silently broadens a narrow scope request

`src/adminAuth.ts:29-36`, `:127`, `:144` force `.default` for the `secret` and
`cli` links regardless of what the caller asked for. Only `device` honours
caller-supplied delegated scopes (`:159`).

Code that requests a narrow scope and receives `.default` did not fail — it was
never asked. That is the wrong default for a least-privilege story and should
at minimum be loud.

## Correctness and verification gaps

### 4. ~~`vault_guard.py` blocks every edit to a vault's own `CLAUDE.md`~~ — DONE

**Shipped 2026-09-05 as `obsidian-vault` 0.3.2, PR #69 (`3167721f`).** Seven
review rounds; the seventh ran against the merged head and came back CLEAN.

The fix is narrower than the plan below, and deliberately so. An early version
skipped `check_note` entirely for the exempt basenames — which also dropped the
required-keys, title-matches-filename and updated-date checks, while the comment
beside it still claimed the exemption was "frontmatter-only". A guarantee written
narrower than the code it describes is the same defect class as a guard that
fails open while looking like it checked. What shipped instead is an
`fm_optional` parameter suppressing **exactly one** issue, `NO FRONTMATTER`, so a
`README.md` that does carry frontmatter is still held to every other rule.
`ASCII_EXEMPT_NAMES` stays `{"claude.md"}` and was **not** widened. The suite
went from 44 to 57 assertions, each exempt name checked in both directions and
asserting the specific violation text rather than only an exit code.

The original entry follows, for the record.

`plugin/obsidian-vault/hooks/scripts/vault_guard.py:35` exempts `CLAUDE.md`
from the ASCII check **by design**, but not from the frontmatter check — so the
vault's instructions file is required to carry note frontmatter it can never
have. Every edit to it blocks.

Hit twice on 2026-09-05 while widening the `wiki/decisions` scope. The write
still lands (`PostToolUse`), so it is noise rather than prevention — but it is
noise on a legitimate, necessary edit, and it trains people to ignore the
guard. Extend the existing exemption to cover the frontmatter rule.

**A fix is already written and stashed**, not lost: `git stash list` ->
`TODO#4: vault_guard frontmatter exemption`. It adds
`FRONTMATTER_EXEMPT_NAMES = {"claude.md", "readme.md", "agents.md",
"gemini.md"}` and skips `check_note` for those basenames. It was kept out of
the crew 0.16.0 PR on purpose - an `obsidian-vault` file changing in that PR
would force an `obsidian-vault` version bump into a crew change. Before
shipping it: it has no regression test, and `CLAUDE.md` requires one for a
hook that can block. `git stash pop` it, add the must-block/must-allow cases,
bump `obsidian-vault` to 0.3.1.

### 5. `core` consumers import the built artifact; `dist/` staleness — CLOSED 2026-09-06

**The premise this was opened on was wrong in the direction that matters, and
the fix is narrower than the entry asked for.** Rewritten rather than ticked,
because a closure citing the wrong hole sends the next reader hunting a CI
problem that does not exist.

What is true: `mcp-servers/packages/core/package.json:11-14` does point `main`,
`types` and `exports` at `./dist/src/index.js`, and the tests import `dist/`
too, so compiled output really is what runs.

What is not: **`dist/` is untracked** — `git ls-files mcp-servers/packages/core/dist`
returns nothing — so "a CI check that rebuilds and diffs" has nothing to diff
against. And CI cannot test stale JS in the first place: `mcp-servers/package.json`'s
`test` is `npm run build && ...`, whose `build` is `npm run build -w packages/core
&& npm run build --workspaces`, so core is rebuilt first on every run.

The real hole is one invocation wide: `npm test -w packages/graph`, run after
editing `packages/core/src`, skips the root build and tests last build's core.
The consumer cannot see it — its own `dist` is current, its own tests compile,
and the behaviour under test is stale.

Closed by `mcp-servers/scripts/check-dist-fresh.mjs`, wired as every package's
`pretest`: newest `.ts` under `src/` and `test/` against newest `.js` under
`dist/`. A consumer is checked by checking **core itself, recursively** —
comparing the consumer's `dist` to `core/src` was the first shape and it is
wrong in the fail-open direction, since a consumer rebuilt after a core edit
then has the newest `dist` in the tree and still loads a stale `core/dist` at
runtime.

Two more fail-open shapes closed with it. An unreadable source directory raises
rather than contributing mtime `0` — `0` compares older than everything and
reads as fresh, so the guard would pass having seen nothing. And equal
timestamps are **stale**: measured on this repo, `npm run build` leaves every
package's newest `dist/*.js` strictly newer than its newest `src/*.ts` (11.9s
for core) with sub-millisecond mtime fractions, because tsc reads before it
writes — so accepting equal only ever admits a real edit landing in the same
coarse tick as an older build.

14 tests at `mcp-servers/scripts/_test/check-dist-fresh.test.mjs`, run by
`npm run test:scripts` which the root `npm test` now includes. Verified by
execution, not by reasoning: `touch packages/core/src/index.ts` then `npm test
-w packages/graph` exits 1 with `STALE BUILD -- @badali404/mcp-ms-core:
compiled output is not newer than core/src -- and @badali404/mcp-msgraph
imports it at runtime`, and passes again after `npm run build`.

### 6. `check_skill_manifests` is unread

`scripts/check-marketplace.py:122`. Confirmed to exist and to sit between
`check_registration` and `check_plugin_manifests`. Which SKILL.md frontmatter
fields it cross-checks against the marketplace entry is unknown, so
`.crew/codemap/skills.md` records the four-place registration rule without
being able to say what this function adds to it.

### 7. The install-scripts matched-pair rule has an enforcer — CLOSED 2026-09-06

Found, not written. `scripts/check-marketplace.py:194` `check_menu_parity`
parses `MENU_KEYS` out of the `.sh` and `Key = '...'` out of the `.ps1`'s
`$script:Catalog`, and fails when the two lists differ **as lists** — so a row
present in one, or the same rows in a different order, is caught, which is what
makes `--select 3,7` mean the same thing on both platforms. The same function
compares `MENU_DEFAULT` against the `.ps1`'s `Default = $true|$false` and names
each row that is ticked by default in one script and not the other, which is
the "default flags" half of CLAUDE.md's rule.

`scripts/check-marketplace.py:233` `check_group_parity` does the same for all
four sub-pickers (`own-skills`, `team`, `community`, `repo-plugins`), and also
fails an empty group — a sub-picker that would render nothing.

Nothing to build. The entry was opened because the check had not been located,
which is a different finding from it being absent, and the two are worth
keeping distinguishable.

## Deferred by design, not oversight

- **`plugin/crew` is unmapped** in `.crew/codemap/`. It is the file set the
  in-flight PR is rewriting; mapping it now yields `DERIVE` facts from
  `fe538879` and judgment from a moved-on working tree. Run
  `/crew:onboard --refresh plugin/crew` after that PR merges.
- **Unmapped smaller areas**, in node order: `mcp-servers/` root (65),
  `mcp-servers/graph` / `intune` / `o365-admin` / `o365-user` (54 each),
  `claude-obsidian-setup/` (48), `vault-automation/` (22).
- **`/crew:diagram`** — deferred until the codemap covers `plugin/crew`, so the
  diagram does not need redrawing immediately.

## Found during the 0.16.8 merge review, deferred as out of scope

### `crew_py` can hand back a Python that is not a Python

`plugin/crew/hooks/scripts/_common.sh:38-43`. `crew_py()` returns the first of
`python3`, `python`, `py` that `command -v` resolves, and never checks that it
runs. On Windows, `command -v python3` succeeds on the App Execution Alias in
`%LOCALAPPDATA%\Microsoft\WindowsApps` — a stub that opens the Microsoft Store
and is not an interpreter. `crew_py` hands that stub to `guard.sh`, whose
`$PY -c ...` then produces nothing, so `CMD` comes back empty and
`[ -z "$CMD" ] && exit 0` fires: **the command guard stands down silently, on
exactly the platform where it has already shipped broken once.** A working `py`
sitting further down the list is never reached, because the first match wins.

Confirmed by experiment, not inferred: with jq hidden and `C:\Python\314`
removed from PATH, `plugin/crew/hooks/scripts/_test/run-tests.sh` goes from
`128 passed, 0 failed` to `77 passed, 51 failed` — the must-BLOCK cases stop
blocking. `py -c "print(1)"` works fine in that same shell; `python3` is the
stub that wins.

Not fixed here on scope discipline: this is pre-existing in `_common.sh`, not
introduced by the branch under review, and `crew_py` is called from several
hooks — changing it is its own ticket with its own must-block/must-allow
regression cases, per the CLAUDE.md rule for anything that can block. The
`_test/run-tests.sh` guard added in this branch now *detects* the condition and
fails loudly, so the suite can no longer go green against a stood-down guard;
the underlying resolver is still wrong.

Fix shape when it is picked up: have `crew_py` execute each candidate
(`"$c" -c "print(1)"`) and return the first that actually runs, rather than the
first that resolves. Add a must-block case that runs with the stub first on
PATH.

### `CHANGELOG.md`'s "0.16.8: the machine-global config..." entries are mislabeled

`CHANGELOG.md:420` and five more at 469-650, all `crew 0.16.8: ...`. That
content actually shipped as **0.16.6**: `git show abe639ce:plugin/crew/.claude-plugin/plugin.json`
reads `"version": "0.16.6"`, and `abe639ce` (PR #65) is a real ancestor of
`origin/main` — so 0.16.6 is what anyone installing from `main` at that commit
actually got. This branch's own history even carried an intermediate state at
`4b92b518` (an earlier merge of `origin/main`) where `plugin.json` briefly read
**0.16.7** for the same content, before a later local commit moved on to
`0.16.8` for unrelated work (the PATH-scrub fix) and, at some point since, a
local edit relabeled this already-shipped entry's text from 0.16.6 to 0.16.8.

Found during the `origin/main` merge that brought in crew 0.16.7 (three
specialists, four dispatch-guard defects) and bumped this branch to 0.16.10.
The rule applied throughout that merge was: relabel a still-unreleased
CHANGELOG entry to the version it actually ships under; never relabel one
that already shipped. By that rule, 0.16.8 here is the mistake the rule
forbids — it should read 0.16.6.

Not fixed in that merge commit, on scope discipline: this divergence predates
the merge, is already committed, and spans ~200 lines of long-shared
CHANGELOG text that git did not flag as conflicting. `CLAUDE.md` is explicit
that renumbering historical prose outside the change at hand falsifies the
record in the other direction, and correcting it *approximately* inside an
unrelated merge commit is how a record gets quietly worse rather than better.

Fix shape when it is picked up: change the six `0.16.8:` labels at the lines
above back to `0.16.6:`, and confirm no other file (`plugin/UPDATE.md`,
`README.md`, `plugin/README.md`) repeats the same mislabel via its
`scripts/sync-updates.py` mirror.

## Moved to CLAUDE.md: `pathlib.write_text` converts a `.sh` to CRLF on Windows

Applied to `CLAUDE.md`'s Landmines list with the user's explicit yes. Kept as a
pointer rather than deleted outright, so anyone who remembers reading it here
finds where it went instead of concluding it was dropped.

## Nit: the request body is translated twice per request

`plugin/localgpu/cli/anthropic_proxy.py`. `check_fits_context` (via
`estimate_prompt_tokens`) and `to_ollama_request` each independently call
`to_ollama_messages`/`to_ollama_tools` on the same body, so the translation runs
twice per request rather than once and reused.

Both functions are pure and in-memory with no I/O, so this is discarded work, not
a correctness problem. Explicitly **not** worth blocking a release on and not
worth a version bump of its own — fold it into whatever next has a reason to
touch that file. Recorded because it becomes invisible the moment the session
that found it ends.

Note for whoever does fold it in: `check_fits_context(body, num_ctx)` at
`:1083`/`:1093` passing the raw `body` is **correct** as written, because
`estimate_prompt_tokens` translates internally. Changing those call sites to pass
`to_ollama_request(...)`'s output would double-translate and measure the wrong
thing. The obvious-looking fix is a bug.

## Correction: nothing under `.crew/` is committed, and one commit message says otherwise

`.gitignore:277` ignores `.crew/` deliberately, with a stated rationale —
`obsidian.vaultPath` and `boardDir` are absolute paths valid on one machine, and
`pm.authority` is a trust decision a clone should not inherit. That is correct
and should stay. But three consequences were not obvious and bit this session:

**1. `ae1c92ee`'s commit message is wrong.** It reads "Record both round-3 review
passes, and rebuild the code graph". The `.crew/metrics.md` append it describes
happened on disk and is still there, but `git add -A` silently skipped it as an
ignored path, so the commit contains only `graphify-out/graph.json` and
`plugin/localgpu/cli/anthropic_proxy.py`. The message claims a file the commit
could not have held. Not amended, because the commit is several deep and other
lanes have read it; recorded here instead so the history is not trusted blindly.

**2. The `/crew:review` skill's stated assumption is false in this repo.** It says
`.crew/verify.json` "is committed and travels between machines", and reasons from
that when deciding whether a rule naming an uninstalled agent is a gap. Here it
travels nowhere. A rule added on one machine is invisible on every other.

**3. Half of the CLI-suite gate fix does not travel.** `_verify/run-all.sh` now
runs `plugin/localgpu/cli/_test` and that change IS committed, so the gate is
fixed for everyone. The matching `.crew/verify.json` rule that maps
`plugin/localgpu/cli/**` to `run-all.sh` is local-only. The important half
travels; the routing half does not, and a fresh clone gets it back from
`/crew:init`.

**4. The codemap is local-only too.** `.crew/codemap/` now holds four subsystem
files and `crew_state.py` counts `knowledge.subsystems: 4` on this machine — but
a fresh clone reads 0 again. That is by design, not a defect: a clone runs
`/crew:init`. Worth knowing before anyone treats the codemap as a shipped
artifact.

If the intent is for `verify.json` specifically to travel while the rest of
`.crew/` stays machine-local, that is a one-line negation in `.gitignore`
(`!.crew/verify.json`) plus a decision about whether its `agents` lists are
portable. Not doing it unasked — it changes what a clone inherits.

## Landmine candidate: an 8-character anchor can never match, and fails silently

**Staged here for a human to approve into `CLAUDE.md`'s Landmines list**, the same
way the `write_text` CRLF entry was. An agent asking for a project-instruction
change is not authorisation. Content below is ready to move verbatim.

`crew_state.py` decides whether a codemap or diagram is stale by comparing its
recorded anchor against `git rev-parse --short=7 HEAD` (`read_knowledge` and
`read_diagrams`). But the anchor patterns — `_ANCHOR_RE` and
`_DIAGRAM_ANCHOR_RE` — both accept `[0-9a-f]{7,40}`. So an anchor written with
`--short=8` **parses perfectly and then never equals HEAD**. There is no error,
no warning, and no hint in the output; every affected map or diagram simply
reports `behind` forever, including immediately after someone "refreshes" it.

The tell is that *all* of them flip to `behind` at once, right after the edit
that was supposed to fix them — which reads as the refresh having failed rather
than the anchor format being wrong. Write anchors with
`git rev-parse --short=7`.

**Related, and not a bug to fix:** `graphStale` and `diagramsStale` are
structurally unsatisfiable for any *tracked* artifact. The anchor names a commit,
and committing the file advances HEAD past the commit it names, so a committed
anchored artifact can never report itself current. Re-anchoring makes another
commit and reproduces the condition — there is no fixed point. The codemap under
`.crew/` escapes this only because it is gitignored, so re-anchoring it creates no
commit. Treat both triggers as artifacts; a diagram's anchor honestly records the
commit it was **drawn from**, which is what a provenance header is for.

## Briefing style: state claims as claims, and say that refuting them is a win

Three times in one session the most valuable thing a subagent did was refute a
confident claim in its own brief:

- The codemap lane checked "a user who tries to lift an unliftable entry is told,
  not silently ignored" and found `load_config` dropped it in silence — which
  became the localgpu 0.1.10 fix.
- `qa-proxy` refuted the framing that B1/B2/F1/F5 were one design error, and the
  correction carried a hard ordering constraint: fixing the clamp before the
  estimator would have capped every reply while no test went red.
- The diagram lane checked "`/localgpu:setup` is a six-step flow" against
  `setup.md:7`, which says "Seven steps, in order". `bootstrap.sh` is the one with
  six.

In all three the brief was confident and wrong, and the lane caught it only
because it went to source instead of transcribing. Make that deliberate rather
than lucky: in any lane brief, mark which statements are verified and which are
claims to check, and say explicitly that refuting the brief is a valid and valued
outcome. A lane that believes its brief is a lane that can only find the bugs you
already suspected.

## Crew's agent count is wrong in three places, right in four

`scripts/install-prerequisites.sh:859` and `scripts/install-prerequisites.ps1:843`
both read:

```
crew                    - Virtual dev team: 11 agents, 21 commands, safety hooks
```

Actual on disk: **29 agents, 24 commands** (`ls plugin/crew/agents/*.md`,
`ls plugin/crew/commands/*.md` — re-measure rather than trusting this line).

The installer is not the only wrong site. Verified 2026-09-06 at `1f97e51c`:

| Location | Says | Actual |
|---|---|---|
| `scripts/install-prerequisites.sh:859`, `.ps1:843` | `11 agents, 21 commands` | 29 / 24 |
| `plugin/PLUGINS.md:153` | `Agents — 14, tiered plus the manager` | 29 |
| `README.md:162` | `17 subagents` (its `24 slash commands` is correct) | 29 |

Correct in four places, so this is drift and not a convention:
`.claude-plugin/marketplace.json`'s crew description, `plugin/PLUGINS.md:17`,
`plugin/README.md:370`, `README.md:773` — all four read 29 agents, 24 commands.

**Why no check catches it.** `check_catalogs`, `check_menu_parity` and
`check_group_parity` compare keys and booleans, never descriptive strings, so
four separate places can state the count wrongly while the gate stays green.
`check_docs` (`scripts/check-marketplace.py:263-277`) reads three files and
never opens `plugin/PLUGINS.md` at all.

The two
scripts agree with each other, so the matched-pair rule is satisfied — they are
consistently wrong, which is why no check catches it. `check-marketplace.py`
compares the *menu keys* between the two scripts, not the descriptive text, and
nothing compares that text against the plugin it describes.

This is the first thing a user reads when deciding what to install, and it
undersells the plugin by a third.

**Not fixed in this PR deliberately, and the reason is process rather than
scope.** `CLAUDE.md` requires that after a change to either install script,
`scripts/_test/drift-detection.sh` is run by hand — it cannot run in CI — and the
README's install URLs, which are pinned to a commit SHA, are re-pinned. PR #67
has just been brought current with a verified drift run against its exact tip.
A one-line label fix would invalidate that run and buy another manual pass plus a
re-pin, for text that is wrong but harmless.

Fix in a follow-up alongside the other deferred items. When it is done, consider
whether the check that would have caught it is worth writing: the counts are
derivable from `ls plugin/crew/agents/*.md` and `commands/*.md`, so a smoke check
comparing the installer's advertised numbers against the directory contents is
about ten lines and would cover every plugin's menu line, not just crew's.

## The staleness triggers are unsatisfiable for tracked artifacts

`crew_state.py` flags `graphStale`, `diagramsStale` and `knowledgeBehind` on a
strict `anchor != HEAD` comparison. All three artifacts are tracked
(`graphify-out/graph.json`, `docs/diagrams/*.mmd`, `.crew/codemap/*.md`), so
committing a refresh advances HEAD past the sha the refresh just recorded. The
condition is true the instant it is fixed and can never be cleared.

Evidence, at HEAD `dc32c12` against anchor `b56d41f`:

    $ git diff --name-only b56d41f..HEAD
    .crew/codemap/UPGRADE.md
    .crew/codemap/crew.md
    .crew/codemap/localgpu.md
    .crew/codemap/marketplace-registration.md
    .crew/codemap/verification-harness.md
    .gitignore
    docs/diagrams/architecture.mmd
    docs/diagrams/data-flow.mmd
    docs/diagrams/process.mmd
    graphify-out/graph.json

Ten files, and **not one is a source file** — the maps, the diagrams, the graph
and a comment-only `.gitignore` change. Every subsystem the codemap documents is
current in substance; the lag is the self-reference, not drift. Re-running
`/crew:onboard --refresh` or `/crew:diagram refresh` here would rewrite files
byte-for-byte identical and advance HEAD again.

The comparison needs to be "has any path this artifact documents changed since
its anchor", not "does its anchor equal HEAD". Until then the pulse reports
three permanent false positives, which is how a real staleness signal gets
trained away.

`plugin/crew/hooks/scripts/crew_state.py` — the anchor comparison.

## `/localgpu:ask` has no empty-argument branch

`plugin/localgpu/commands/ask.md:8` interpolates `$ARGUMENTS` straight into
prose — "`$ARGUMENTS` is the question" — and nothing in the file branches on it
being empty. Invoked with no question the command renders its whole body,
including the retrieval procedure and the VRAM warning, with a blank where the
question should be. There is no instruction for that state, so the reading model
has to invent one.

Observed twice in one session, both times as a bare `/localgpu:ask`.

The fix is a guard at the top: if `$ARGUMENTS` is empty, print the
`argument-hint` line (`<question> [--k N] [--glob <pattern>]`) and stop, without
loading the rest. Cheap, and it turns a confusing non-response into a usable one.

**Check the sibling commands for the same shape before fixing just this one.**
`/localgpu:search` takes the same flags and almost certainly has the same gap;
`gizmoduck`'s `scan`, `report`, `tickets` and `diff` all take required
arguments. A command whose entire body is instructions for work it cannot do is
worse than an error, because it reads as though it is working.

`plugin/localgpu/commands/ask.md:3` carries a correct `argument-hint` already —
the metadata is right, nothing consumes it on the empty path.

## `resolve_role` accepted any provider name, and the review gate failed open — CLOSED 2026-09-06

**Fixed before this closure was written, not by it.** The analysis below is
kept verbatim because it is the record of what the hole was; what follows
immediately is where each half of it is now closed, cited so the claim can be
re-checked rather than believed.

- `plugin/crew/hooks/scripts/crew_state.py` defines `QA_PROVIDERS` and bars an
  unrecognised QA provider as **item 0 of `resolve_role`, before the family
  check is reached** — with the reason this entry asked for stated in the
  announce line: an unrecognised name "is not a reviewer at all, and
  `family() is None` for it must never read as no conflict."
- The write side refuses too: `crew_config.validate_providers` rejects a
  provider outside the set and **names the offending key**, covering
  `qa.provider`, `qa.order` and `qa.roles.<role>.provider` — the two holes the
  table below called out. `crew_config.order_candidates` marks such a row
  ineligible with the same reason, so `auto` cannot walk into one either.
- Regression coverage exists on both sides, in
  `plugin/crew/tests/test_provider_table.py`: must-block for a pinned
  `localgpu` reviewer, for an unpinned one (the worse case — `family` is
  `None`), and for a name crew has never heard of; refusal-with-key-named for
  each of the three config shapes; must-allow for `auto`, which is not in
  `QA_PROVIDERS` and must still resolve.

One thing deliberately left as it is: the bar sets `barred: True` and appends
to `announce` but leaves `barredBy: None`. That is not an oversight —
`crew_config.py:1041` documents it and `:1073` branches on it, because
`barredBy` names a *family* and an unrecognised provider has none. "BARRED —
same `None` family as the author" would be a worse line than the one that
actually prints.

Verified by execution at `1394aab6`, not inferred — that ref is the state the
entry describes, which predates the fix.

### No code validates a provider name

The closed set `{claude, codex, copilot}` appears three times in the Python and
is never a check:

- `crew_config.py:792` — builds a dict of names for the report
- `crew_config.py:794` — `onPath` probe for codex/copilot
- `crew_state.py:1334` — the default `qa.order`

`resolve_role` (`crew_state.py:1612`) takes the name verbatim:

    provider = pin.get("provider") or block.get("provider") or "claude"

The only validation that exists is **prose in `commands/model.md:105-119`,
executed by a model**. Hand-editing `.crew/config.json` bypasses it completely,
and so does a model that reads the table imprecisely.

### The table itself has two holes

| Key | Documented rule | Hole |
|---|---|---|
| `dev.provider` | `claude`, `codex`, or `copilot` | closed |
| `qa.provider` | `auto`, or a name in `qa.order` | **`qa.order` has no rule, so adding `localgpu` there makes `qa.provider: localgpu` valid** |
| `qa.roles.<role>` | "a `{provider, model}` object. Any role name is accepted" | **says nothing about the provider VALUE. `qa.roles.review.provider: localgpu` passes.** |

So the restriction on `dev.provider` is real and the same restriction on the
reviewer seat does not exist.

### What resolve_role then returns

Config: `dev.provider: codex` / `gpt-6-astra` (author family `gpt`), reviewer
pinned to `localgpu`.

    provider   = 'localgpu'
    model      = 'qwen2.5-coder:7b-instruct-q4_K_M'
    family     = 'qwen'
    barred     = False
    announce   = []

`qwen != gpt`, so the family-independence guard **passes cleanly**. The 7B is
affirmatively cleared to review GPT-authored code.

Unpinned is worse. `qa.provider: localgpu` with no model:

    family     = None
    barred     = False
    announce   = []

`family` is `None`, and the guard reads
`if out["family"] is not None and out["family"] in authors` — so it **does not
run at all**. Not "a different family cleared it": the check is skipped.

### The part that makes it undetectable

`announce` is `[]` in both cases, against a docstring that states the contract
directly (`crew_state.py:1643-1646`):

> `announce` is never empty when something happened. A review that quietly ran
> on the fallback is indistinguishable from one that ran on the pin, and the
> difference matters most exactly when the pin was chosen to get a different
> family onto the diff.

An unknown provider is precisely "something happened", and nothing is said. The
config file reports a reviewer is configured, `resolve_role` agrees, and a 7B
that agrees fluently produces output indistinguishable from a real pass. Same
shape as every other defect in this file: **the signal and its absence look
identical.**

### Fix shape

`resolve_role` must not silently accept a provider it has no runner for. Either
bar it, or at minimum append to `announce` — a review that ran on an unknown
provider must never be reportable as clean without saying so. `family()`
returning `None` for an unrecognised provider must not be treated as "no family
conflict"; unknown is not the same as independent.

Needs must-block / must-allow regression cases and sabotage testing per
CLAUDE.md, since it governs a gate that can block.

**Taken, in full: barred rather than merely announced.** See the closure at the
top of this entry for where each part lives.

## `sabotage.py` could leave a live mutation in the tree and still report PASS — CLOSED 2026-09-06

Fixed in crew 0.16.24. All four defects below are closed; the analysis is kept
because it is what the fix was built against, and because defect 1's residue is
permanent and needs to stay visible.

| Defect | Where it is closed now |
|---|---|
| 1. `finally` does not survive a kill | `install_exit_handlers` registers `atexit` plus SIGTERM/SIGINT/SIGBREAK/SIGHUP, each looked up with `getattr(signal, name, None)` because SIGBREAK is Windows-only and SIGHUP POSIX-only. A restore that FAILS on that path stays in `_LIVE` so the atexit pass retries it. **SIGKILL is still uncatchable and always will be** — defect 2's guard is what covers it, on the next run. |
| 2. The next run destroys the only good copy | `main` calls `stale_backups` before touching anything, prints the `mv <target>.bak <target>` line that undoes the mutation still in the tree, and exits 2 without mutating. `apply_mutation` raises rather than copying over an existing `.bak`, and builds each backup as `<target>.bak.partial` before `os.replace`-ing it into position — so a `.bak` is complete or absent, never half-written. That last part is not decoration: the startup guard tells the user to move a `.bak` over the target, so a partial one would make that instruction the thing that destroys an intact source. |
| 3. The restore is never verified | A sha256 per target is taken before the first mutation, held in module state, and compared after every restore **on all three paths** — the loop's `finally`, the signal handler and atexit. A mismatch prints both digests and fails the suite, so `PASS` can no longer be printed over a modified tree. Verifying only the loop's path while claiming all three would be the same defect wearing the fix's label. |
| 4. `crew_state.py.bak` is tracked | It is no longer tracked (`git ls-files '*.bak'` is empty), and `*.bak` plus `*.bak.partial` are in `.gitignore` — the existing `env.bak/`/`venv.bak/` entries are directories and never matched a file. The reason recorded there is that a **tracked** `.bak` now gates the suite off on every clone, since the harness refuses to start when it sees one. Ignoring does not preserve a `git status` signal; ignored files are hidden from it, and the filesystem check at startup is what replaces that. |

Coverage: `plugin/crew/tests/test_sabotage_harness.py`, 16 tests, none of which
touch a real source file — a regression suite for a harness that corrupts files
must not be able to corrupt what it is testing against. Sabotage-tested
independently: ten mutations, one per guard, 10/10 red.

That independent run paid for itself on the first pass by catching one of these
new tests being **vacuous**: it asserted a `.bak.partial` was gone after the
run, which `apply_mutation` makes true whether or not the sweep that removes it
exists. It now observes the state at the moment the first mutation is applied,
which only the sweep can produce. Worth recording because it is the exact thing
this suite exists to find, found in the suite's own coverage.

**Not taken: mutating a copy under a temp tree.** It removes the whole class,
and it is the right answer eventually. It is not this change because `run_test`
invokes pytest against the real checkout, so relocating the mutation means
relocating the suite it is trying to make go red — a bigger change than the
four guards above, and one that would land untested alongside them.

Landed in `d362a2bd`: `plugin/crew/hooks/scripts/crew_state.py:1191` shipped as
`if False:
        frozen = frozen` instead of the real
`if isinstance(frozen, str): frozen = frozen.replace("\\", "/")`. That is the
"frozen artifact path is stored with native separators" mutation. A path frozen
on Windows then never matches on Linux, so a completed scan reads as unscanned
forever on any other machine. Found by review, not by any gate.

`plugin/crew/tests/sabotage.py` mutates real source in place: `apply_mutation`
(:980) copies `target` to `target + ".bak"`, writes the mutation, and `restore`
(:1024) does `shutil.move(backup, target)`. `main` (:1041-1043) wraps only the
`run_test` call in `try/finally: restore(target)`.

Four distinct defects, in the order they bite:

1. **`finally` does not survive a kill.** It unwinds on exceptions, including
   `KeyboardInterrupt` -- but a `SIGTERM` or `SIGKILL` from an external timeout
   terminates without unwinding, so neither `restore` nor any cleanup runs. The
   mutated file and its `.bak` both survive. This is the most likely cause here:
   the run was killed by a harness timeout mid-mutation.

2. **The next run destroys the only good copy.** After a killed run leaves
   `crew_state.py.bak`, the next `apply_mutation` does
   `shutil.copy(target, target + ".bak")` unconditionally -- overwriting the
   good backup with the ALREADY-MUTATED file. The harness's own mutation table
   flags exactly this class for the code under test (:174-176, *"Skipping the
   backup when the name is taken destroys the newer original and then reports
   that it was saved"*) and the harness itself does it. There is no startup
   guard that refuses to run, or recovers, when a stale `.bak` is present.

3. **The restore is never verified.** Nothing compares the file to its pre-run
   content after `restore`. `main` prints PASS from `ok`, which tracks only
   whether each mutation went red -- so a restore that silently failed is
   indistinguishable from one that worked. Signal and absence identical, which
   is the failure mode this repo keeps shipping.

4. **`crew_state.py.bak` is tracked in HEAD** (`7c420e90`, swept in by
   `git add -A`; the removal in `d362a2bd` did not take). It is not stray lane
   litter -- it IS the harness's backup, and a `.bak` appearing in `git status`
   is the diagnostic tell that a run died mid-mutation. Tracking it removes that
   signal and makes defect 2 permanent, since the file is always present.

Fix shape: restore on every exit path including signals (`signal` handlers plus
`atexit`, not `finally` alone); refuse to start -- or recover from -- a stale
`.bak` rather than overwriting it; verify the restored bytes against a hash
taken before the first mutation and fail the suite loudly if they differ;
untrack the `.bak` and add it to `.gitignore`. Consider mutating a copy under a
temp tree instead of real source, which removes the whole class.

Verified while scoping this: exactly one sabotage-shaped line exists in all of
HEAD's Python (`crew_state.py:1191`), and the HEAD-vs-worktree diff for that
file is exactly those two lines -- so the working-tree restore is complete and
nothing else was left mutated.
## `render.sh` cannot render a diagram on Windows — it hands `mmdc` a `/tmp` path

`skills/crew-diagrams/scripts/render.sh` writes a puppeteer config to a Git
Bash `/tmp/puppeteer-XXXX.json` and passes that POSIX path to `mmdc`, which is
a Windows Node program that cannot resolve it. Every render fails identically:

```
FAIL  architecture.svg
Configuration file "/tmp/puppeteer-DQrB.json" doesn't exist
```

Six for six on 2026-09-05 (`architecture`, `data-flow`, `process`, `.svg` and
`.png` each), exit 1.

**This is not a Mermaid problem, and that is the part worth writing down.** The
same three sources render cleanly when `mmdc` is invoked directly with a
Windows-resolvable output path — 71632, 40140 and 75882 bytes of SVG. Anyone
reading only the render log would conclude the diagrams are broken and start
editing correct Mermaid, which is the expensive wrong turn this entry exists to
prevent.

Fix shape when it is picked up: resolve the temp path through `cygpath -w`
(or write the config beside the output directory) before handing it to `mmdc`,
on the branch that already knows it is on Windows. The `_test` fixture should
assert a non-zero output file, not just exit 0 — the failure above still wrote
`docs/diagrams/out/` and reported a summary line, so an exit-code-only check
would have passed it.

Found while re-anchoring the diagrams after PR #69, 2026-09-05. Anchor
`3167721f`. Measured, not inferred: both the failing and the passing
invocations were run.

## `crew_state.py` is 3283 lines and should be split — CLOSED 2026-09-06

**Done in crew 0.16.22** (PR #76, `ac93221d`). Split three ways:
`crew_state.py` 3300 -> 2293 lines, the endpoint ledger into
`crew_endpoints.py`, and the three shared readers into `crew_common.py`.
`max-module-lines` was not raised. Both hazards named below were real and were
handled: the codemap citations were re-anchored, and every `sabotage.py` anchor
was re-verified as matching exactly once in the file its mutation names. A
third hazard the entry did not predict turned up and is worth carrying forward
— a re-export is a second binding, so `monkeypatch.setattr(crew_state, "<moved
name>")` now succeeds and rebinds a name nothing reads;
`tests/test_module_split.py` is the guard for it.

The original entry, kept because its reasoning is what made the split safe:

It went 2154 -> 3283 on the endpoint-ledger branch, a 52% increase in one
module. `.pylintrc`'s `max-module-lines` was raised 2400 -> 3300 to let CI pass,
which unblocks a branch and fixes nothing: the ceiling now tracks the file
rather than constraining it, and that is the second time it has been raised for
exactly that reason (2000 -> 2400 before it).

The module now holds at least five separable concerns: config/schema resolution,
the dispatch record, the codemap and diagram anchor comparisons, the provider
and family guards, and the endpoint ledger. The last is the newest and the most
self-contained -- `read_endpoints`, `declare_endpoint`, `scan_artifact_path`,
`_candidate_record`, `_artifact_confirms_scan`, `gizmoduck_installed` and the
monorepo detection - and is the obvious first extraction.

Two things make this harder than it looks, and both belong in the ticket rather
than being discovered halfway:

- **Every `path:line` citation in `.crew/codemap/crew.md` points into this
  file.** A split invalidates all of them at once, so the codemap refresh is
  part of the work, not a follow-up.
- **`sabotage.py`'s mutation table addresses this file by line-anchored
  content.** Mutations that no longer match anything do not fail loudly -- they
  are simply not applied, and the suite still reports PASS. Any split has to
  re-verify that every mutation still binds, or the harness silently covers less
  while looking identical. That is the same signal-and-absence failure this file
  is full of.

Do not raise `max-module-lines` a third time.

## Perplexity is an agent, not a `qa.provider` — the routing half is not done

Opened 2026-09-06 with crew 0.16.23, which added `crew:qa-researcher`
(`plugin/crew/agents/qa-researcher.md`): a domain specialist holding the
`mcp__perplexity__*` tools that checks what a diff assumes about the outside
world against live sources. That half shipped and is usable today.

What did not ship is Perplexity as a selectable reviewer. `qa.provider` and
`qa.roles.*` still resolve to the same set they did before
(`plugin/crew/hooks/scripts/crew_config.py`), so `/crew:review`'s routing, the
fallback chain and the self-review family guard are untouched. That was
deliberate — the guard bars a reviewer whose family matches the author's, and
Perplexity's family, fallback behaviour and what "the model that reviewed this"
even means for a web-grounded answer all need deciding before a name is added
to that table. `resolve_role` accepting any provider name (the open entry above)
is the reason a half-answer here would fail open rather than loudly.

Three questions to settle before writing any code:

- **What family does it report?** A wrong answer either bars a reviewer that is
  genuinely independent, or clears one that is not. "Could not tell" has to
  survive into every row derived from it.
- **What does it review?** It is strong on "is this deprecated / is there an
  advisory" and weak at reading a diff's logic. A `qa.provider` slot implies the
  second, which is the thing it is worst at.
- **What happens when the MCP server is absent?** The agent stops and says so.
  A provider entry would need the same, and `qa.fallback` is the existing
  mechanism — but a fallback that silently produces a different kind of review
  is not the same check.

Until then, the honest description is the one in crew's README section 12b:
Perplexity is an opt-in second pass alongside the code review, not a reviewer
crew can route to.

## Session transcripts and subagent tool-result files write raw file content to disk with no secret redaction

Filed from a consumer repo (TheSelectSource), where the pattern was found
concretely and is tracked there as `TO-DO.md` F155/F157, and cross-referenced
against SRL's own counterpart ticket `SRL-997`. Recorded here per that repo's
own `.crew/secrets.md` §10: "a value printed into a tool result... is written
to the session transcript on disk, carried into every compaction summary, and
repeated into every subagent that inherits that context. It cannot be
un-printed." That is a property of this harness's transcript persistence, not
of any one project, so fixing it only in the consumer repo leaves it live in
every other repo this plugin touches.

**What was actually observed, twice, in one session, in that repo — despite
the operator having already read the exact warning beforehand:** a `Read`/`sed
-n` pass over that repo's committed `config/env.{development,production}.php`
files printed a production and a development database password verbatim into
the session's own tool-result output and `.jsonl` transcript; a later `grep`
for a literal username value did the same for a production DB username. Both
are now sitting in plaintext in local transcript/tool-result files
(`~/.claude/projects/<repo>/**/*.jsonl` and equivalent subagent transcript
files) purely as a side effect of reading files the project's own convention
already flagged as sensitive — no malice, no unusual command, just the
default behavior of a normal file-read tool call in this harness.

**Why "just don't do that" is not a fix.** Two independent lanes in that
repo's history made the identical mistake on the same day, one via a `sed`
redaction with a quoting bug that printed the value it was trying to hide, one
via an early `grep` used to locate a value before comparing it. A third
instance (this one) happened in a *different* session, after the operator had
read the written-down rule immediately beforehand. A rule that only humans (or
Claude) have to remember correctly, every single time, forever, across every
project, is not a control — it is hope with a docs page. The actual fix has
to sit in the harness or the plugin's tool-interception layer, not in prose a
lane might not re-read at the right moment.

**Where this plugin already has the right shape of hook, and could extend
it:**

- `plugin/crew/hooks/hooks.json:11-19` already registers a `PreToolUse`
  matcher on `Bash` (`guard.sh`/`guard.ps1`) that runs *before* every shell
  command and can `exit 2` to block it outright — see the `block()` helper and
  the destructive-operation rules in `plugin/crew/hooks/scripts/guard.sh:17-32`
  (terraform apply/destroy, destructive DDL, force-push, `rm -rf /`, etc.).
  That is the exact interception point a "do not raw-read a declared secret
  file" rule would need, and the file already has the regex-and-`block()`
  idiom to add it in.
- **What such a rule could plausibly catch:** a `cat`/`sed`/`grep`/`echo`/`type`
  (or shell redirection like `< file`) invocation whose argument matches a
  project-declared secret-bearing path. A repo that documents its own
  secret-bearing files (as `.crew/secrets.md` already asks every onboarded
  repo to do, listing exact paths) gives the hook a concrete, low-noise
  denylist to match against, rather than needing a generic entropy heuristic.
  Denying the raw read and pointing at the hash-compare procedure
  (`.crew/secrets.md` §10's own "hash, do not read" idiom) would close the
  *shell-command* half of this exposure — the half both real incidents and
  this one went through.
- **What that fix does NOT close, and is the harder half:** any read of such a
  file through the `Read` tool itself (not `Bash`), which is a first-class,
  non-shell tool this plugin's hooks do not currently intercept at all before
  a repo-declared secret path — and which is exactly the tool that produced
  the specific 2026-09-06 exposure described above (a direct `Read`/file-view
  call on the config files, not a shell command). A `PreToolUse` matcher on
  `Read` (this harness does support multi-tool matchers the same way it
  supports `Bash`/`PowerShell` today) checking `tool_input.file_path` against
  the same declared-secret-path list would be the natural second half.
- **What neither of the above closes:** once a tool call is *allowed* to run
  and returns content, this harness's own transcript writer persists that
  content to the `.jsonl` file on disk with no redaction pass, and no hook in
  this plugin runs *after* that point with write access back into the
  transcript file. A `PostToolUse` hook could observe the outbound content and
  warn, but by the time it fires the content is already on disk — the
  transcript-writing step itself is core-harness behavior outside this
  plugin's reach, and closing this half would need a request into the host
  CLI/SDK, not a plugin change. Recorded here as the ceiling on what a
  plugin-side fix can achieve, not skipped over.

**Fix shape, in priority order (each independently useful, none complete on
its own):**

1. Extend `guard.sh`/`guard.ps1`'s existing `PreToolUse`/`Bash` matcher with a
   `block()` rule for raw-read commands against paths a project declares
   secret-bearing (read that project's own `.crew/secrets.md` "declared"
   locations, if present, as the denylist source — no new config surface
   needed).
2. Add a parallel `PreToolUse` matcher on the `Read` tool (and any other
   first-class file-reading tool this harness exposes) applying the same
   denylist to `tool_input.file_path`.
3. File the transcript-redaction gap as a request against the host CLI/SDK
   itself, since no hook available to a plugin today can act on content
   already written to a `.jsonl` transcript.

**Not fixed here — this is the finding, not the patch.** No code in this pass
was changed; `TheSelectSource/TO-DO.md` F157 is the record of the concrete
2026-09-06 instance and the workaround applied there (comparing secret values
by `strpos()`/hash entirely inside a single script process rather than via any
shell command, going forward, in that one repo, for that one task).

**Related.** `SRL-997` (the same check-shape gap, filed independently in a
different consumer repo); `TheSelectSource/TO-DO.md` F155 (the original,
broader finding — committed secrets appearing in transcripts generally) and
F157 (this specific incident plus the `_verify` control that incident's task
was building); `TheSelectSource/.crew/secrets.md` §9-§10 (the procedure this
gap makes hard to follow reliably by hand).


## Two install-script invariants CLAUDE.md states that the scripts do not hold

Both verified 2026-09-06 at `1f97e51c` by reading the worktree. Found while
re-reading `.crew/codemap/install-scripts.md`, whose per-path diff against its
anchor was **empty** — neither of these is drift; both were true at the previous
anchor too.

### 1. `json_query` resolves `python3` only — not `python`, not `py`

`scripts/install-prerequisites.sh:164-176` tries `jq`, then `python3`, then
`return 1`. CLAUDE.md's landmine says: "Git Bash ships without `python3`.
Resolve `python3`/`python`/`py` and fail loudly on stderr rather than
suppressing the error and exiting 0." Both back ends carry `2>/dev/null`, so a
back end that runs and fails is indistinguishable from one that is absent.

`jq` is tried first, so this bites only where `jq` is absent AND `python3` is
absent while `python` or `py` is present — an ordinary Git Bash box with the
Windows Python launcher.

Traced consequence: `json_query` returns 1 -> `PLUGINS_CACHE` is empty
(`:248`) -> `plugin_version` returns 1 for every name (`:260`) -> every plugin
reads as not-installed and is reinstalled. That is loud rather than silent,
which is the only reason this is not urgent. It still violates the stated rule,
and the `2>/dev/null` is the part that makes a diagnosis expensive.

### 2. The scroll line bypasses `pick_fit` / `Format-PickerLine`

CLAUDE.md: "Nothing may bypass `pick_fit` / `Format-PickerLine`. Clipping is
degradation; a line that *wraps* throws off the cursor-up redraw count and
smears the menu over what was above it."

The `showing N-M of T` line is printed directly in both scripts —
`scripts/install-prerequisites.sh:1271-1272` (`printf`) and
`scripts/install-prerequisites.ps1:1140-1141` (`Write-Host ... PadRight`) —
without passing through either clipper.

It cannot wrap today: the string is bounded near 24 characters and both scripts
floor the width at 40 columns (`sh:1150`, `ps1:1105`). So this is currently
harmless *by arithmetic, not by construction* — the invariant is stated
absolutely and holds only incidentally. Worth either routing through the
clipper or amending CLAUDE.md to name the exemption; leaving it undocumented is
what makes the next reader distrust the rule.

Related: the two clippers are **not** interchangeable — `pick_fit` reserves one
character for a single-character ellipsis, `Format-PickerLine` reserves three
for `...` and additionally pads. A line tuned against one can overflow the
other.


## `wazuh-onprem` writes production config with no confirmation, and redacts nothing

Both verified 2026-09-06 at `1f97e51c` by reading the worktree. Found while
re-reading `.crew/codemap/skills-security-ops.md`, whose per-path diff against
its anchor was **empty**. Neither is drift.

### 1. `manager_config.py apply` has no confirmation of any kind

The `apply` subparser (`skills/wazuh-onprem/scripts/manager_config.py:251-254`)
accepts only `--block`, `--anchor` and `--restart`. There is no `--yes`, because
there is no prompt: a grep of the whole file for `input(`, `confirm`, `--yes`,
`_auto_confirm` and `getpass` returns nothing.

`cmd_apply` (`:170-223`) backs up, then `sudo cp`s the candidate over the live
`ossec.conf` at `:200`, in one non-interactive run. It does validate after the
copy and roll back on failure — real, enforced, and worth keeping — but the
rollback protects against a *bad config*, not against an *unintended run*.

The only restraint on intent is prose at `skills/wazuh-onprem/SKILL.md:144`.
Compare `meraki_config.py`, the sibling skill: its apply is safe by control
flow — `:152-187` cannot reach the PUT at `:176` without taking the snapshot
at `:157` — and it carries `HARD_BLOCKS`/`check_hard_block` plus batch caps.
One skill enforces; the other describes.

### 2. Zero redaction, while two commands emit the whole config

`grep -rniE 'redact|scrub|mask|sanitiz' skills/wazuh-onprem/scripts/` returns
nothing. Meanwhile `cmd_diff` writes the full live `ossec.conf` to stdout
(`:167`) and `cmd_fetch` writes it to `--out` (`:148`). That file carries
integration webhook URLs and authd keys.

This compounds the already-recorded finding that session transcripts write raw
secret content with no redaction (commit `1f97e51c`): the output of a single
`manager_config.py diff` lands verbatim in a transcript.

`meraki_diff.py:32-42` does display-path redaction, so the pattern exists in
this repo already and was simply not applied here.


## Queued 2026-09-08 — Codex QA findings on the new skills' own scripts

Raised by the Codex review of PR #81 (`gpt-5.6-luna`, `model_reasoning_effort=high`)
against `1f97e51c...HEAD`. Every one is **inside the two new skills' scripts**, not
in the marketplace wiring that PR added — they are pre-existing bugs in code that
was written before the PR and merely registered by it, which is why they were
ticketed rather than fixed in the same change. Anchor: `9370ad02`.

Not independently re-verified line by line; each is the reviewer's own repro,
kept in its words so a reader can check it rather than trust it.

### `skills/power-automate-api/scripts/pa.py`

1. **`pa.py:143` — a custom `--client-id` is not cached**, so a token refresh
   silently falls back to `DEFAULT_CLIENT_ID` and later SharePoint calls fail.
   Repro: log in with `--client-id`, expire the token, run a command that
   refreshes.
2. **`pa.py:360` — snapshot filenames use second-resolution timestamps**, so two
   patches of the same flow inside one second overwrite each other's rollback
   state. Repro: start two same-flow patch processes within one second and list
   the snapshot files. (Note this is the rollback safety net, so the failure is
   silent until a rollback is actually needed.)
3. **`pa.py:69` — DNS, connection, timeout and non-JSON responses escape as
   unhandled tracebacks** rather than a diagnosed error. Repro: point a command
   at an unreachable or malformed endpoint.
4. **`pa.py:472` — the rollback command it prints omits the required `--org` and
   `--flow` arguments**, so copying it verbatim fails immediately. Repro:
   complete a patch and run the printed command. Worst of the four: the one
   moment a user needs it, it does not work.

### `skills/jira-manager/scripts/jira-api.sh`

5. **`jira-api.sh:33` — the documented no-auth cloud-ID helper is unusable**,
   because sourcing the file requires the email and API-token variables first.
   Repro: set only `JIRA_WORKSPACE`, source, call `jira_get_cloud_id`.
6. **`jira-api.sh:31` — sourcing permanently enables `nounset` and `pipefail` in
   the CALLER's shell.** A helper meant to be sourced must not change the shell
   it is sourced into. Repro: source it in a shell with `set +u`, then expand an
   unset variable.
7. **`jira-api.sh:124` — mutation helpers return success and print completion
   text on 4xx/5xx.** Repro: edit or delete a nonexistent issue, check `$?`.
   This is the "fails open while looking like it worked" shape this repo keeps
   paying for.
8. **`jira-api.sh:131` — account-search values are not URL-encoded**, so any
   name with a space fails lookup. Repro: `jira_find_account_id "Jane Doe"`.

## Ticket B: `docs.theme` has no consumer, and its default is silently overridden

Raised 2026-09-12 by team-lead, who measured it correctly: `docs.theme` and
`docs.reportTheme` are settable in BOTH config layers and six files in
`plugin/crew` mention them -- two templates, two tests, `crew_upgrade.py` and
`crew-setup/SKILL.md`. Every one is a template, a test or a migration. **No code
in crew consumes either key.** Confirmed independently here with the same grep.

Two premises in the original report need correcting before anyone works this,
because both would send the work in the wrong direction.

**1. A resolver already exists, and it is good.**
`skills/doc-builder/scripts/resolve_brand.py` (with
`scripts/_test/test_resolve_brand.py`) resolves a brand-pack name through a
five-step order -- `--brand`, `DOC_BUILDER_BRAND`, sibling skill directories,
the plugin cache, then neutral -- and announces which step matched. The
fall-through to neutral is announced LOUDLY and names every location searched,
which is most of the "skill not installed" degraded path the ticket asks for.
So the work is NOT "write a resolver". It is narrower: **crew stores a theme
name and never passes it to the resolver that already exists.** The wiring is
the ticket.

**2. The two brand-pack layouts are deliberate, not an inconsistency.**
The report warned that a resolver assuming one uniform layout "will find
`neutral` and miss `solomon`". It is the other way round, and by design. Every
discovery glob is `<skill>/assets/brand.json` -- the FLAT shape, which is what
`solomon-doc-builder/assets/brand.json` has. The nested
`doc-builder/assets/brands/neutral/brand.json` is excluded from discovery on
purpose (`_is_own`) because neutral is the built-in fallback rather than a
discovered pack. Verified by running it: `--list` reports `neutral (built in)`
and finds `solomon` under sibling skills.

**The actual defect, found by running the resolver rather than reading it.**
With both skills installed and no `--brand`, resolution prints:

```
brand: solomon -- the only brand pack found in sibling skill directories
```

Neutral is not a candidate, so "the only pack found" is solomon and there is no
ambiguity to stop on. A user whose crew config says `docs.theme: "neutral"` --
the shipped default, which `/crew:config --show` will print back to them -- gets
**solomon-branded documents**. That is one client's footer on another client's
report, which is the exact failure `resolve_brand.py`'s own docstring says its
ambiguity check exists to prevent. It happens only because the key has no
consumer, so the check never sees the user's stated answer.

So this is worse than a key that quietly does nothing. It is a key whose
documented default is actively contradicted by whatever pack happens to be
installed, while the config UI reports the default as being in effect.

**The wrong brand is also a partly broken one, which misdirects the diagnosis.**
Confirmed on this machine and reproduced independently by team-lead: solomon's
pack resolves `masters_dir` to `C:/repos/OnboardingSOPs/sops_new`, and the
script prints it as `(NOT FOUND on this machine)`. So a user who never chose
solomon gets a brand whose template directory does not exist, and the first
failure they hit is a MISSING TEMPLATE rather than a wrong footer. That points
the diagnosis at doc-builder's assets, or at their own checkout, and away from
branding entirely -- which is where the actual defect is. A wrong answer that
fails in an unrelated-looking way costs more than one that fails plainly.

`--list` makes the same point: `neutral` is shown, labelled `(built in)`. It is
VISIBLE and still not a candidate, so nothing reads as missing and no ambiguity
stop fires. Everything looks correct from the outside.

**Acceptance criterion for this ticket:** an unresolvable or unset theme must
not fall through to "whatever happens to be installed". Fail loud, or fall back
to neutral and say so, the way the resolver already does for a genuinely missing
pack.

Repro, both halves:

```
python skills/doc-builder/scripts/resolve_brand.py            # -> solomon
python skills/doc-builder/scripts/resolve_brand.py --brand neutral  # -> neutral
```

Scope when this is picked up: pass `docs.theme` through to `--brand` /
`DOC_BUILDER_BRAND`, and decide what an unresolvable theme name does. It must
NOT fall through to "whatever is installed" -- that is the bug above. Fail loud
or fall back to neutral and say so, the way the resolver already does for a
missing pack.

### Design settled 2026-09-12: crew passes the name through, it resolves nothing

Crew reads the merged `docs.theme` and passes `--brand <name>`; `docs.reportTheme`
goes to the findings-report script. Two keys are implementable because the two
pipelines are separate scripts. Crew adds the one thing doc-builder lacks -- a
per-repo setting with a machine-global default, which neither a per-invocation
flag nor a machine-wide env var can express. Keep the layering and add nothing
else. Do NOT write a second resolver.

**The refusal is real, and it is narrower than it sounds. Measured, not read.**
With two discovered packs the resolver exits 1 and names them:

```
$ DOC_BUILDER_SKILLS_DIR=<two packs> resolve_brand.py
More than one brand pack is installed (...): alpha, beta.
Pass --brand <name> (or set DOC_BUILDER_BRAND) to say which one this document is for.
exit=1
```

With exactly ONE discovered pack it returns that pack silently, exit 0. `neutral`
is never a discovery candidate, so this repo -- doc-builder plus
solomon-doc-builder -- is the one-pack case. **The refusal therefore does not
protect the common configuration**, which is a single client brand installed.
That is not an argument against pass-through; it is the argument FOR it, because
pass-through is what creates protection in exactly the case the refusal leaves
open.

**`docs.theme` does NOT ship as `null`. It ships as `"neutral"`.** Verified in
all three places that define it -- `crew_upgrade.DOCS_BLOCK` (`theme: "neutral"`,
`reportTheme: None`) and both templates. Only `reportTheme` is null. The design
note that "both are null in the templates today" is wrong on the half that
matters, and building on it would ship a behaviour change nobody chose:

- Under pass-through with the default untouched, every repo passes
  `--brand neutral`. That is an explicit instruction, so it **overrides an
  installed client pack**. Today that pack wins; afterwards neutral would.
  Upgrading crew would silently DE-BRAND an existing Solomon user's documents,
  and the config file would not have changed to explain it.
- `null` meaning "pass no `--brand`, let doc-builder resolve" is the right
  semantic, and it preserves the refusal exactly -- but today it only describes
  `reportTheme`.

So the ticket carries a decision, and the recommendation is the second option:

1. Keep `theme: "neutral"`. Predictable, and the config then means what it says
   -- but the first upgrade silently stops applying an installed brand pack.
2. **(Recommended)** Ship `theme: null` and treat null as "pass no `--brand`".
   Pass-through then only ever NARROWS from doc-builder's own behaviour, the
   upgrade is a no-op for every existing user, and pinning a brand becomes an
   opt-in the user performs deliberately. Cost: the migration has to move an
   existing `"neutral"` forward, and `"neutral"` typed deliberately must stay
   distinguishable from `"neutral"` inherited from a template nobody edited --
   which is why this is a decision and not a default.

Degraded path: use what exists. `resolve_brand.py` already reports what would be
used and why, and `--list` enumerates visible packs. Do not invent separate
detection. It must degrade rather than throw when doc-builder is not installed
at all -- a second code path, and it needs its own test.

**Does `solomon-doc-builder` need a crew reference once this lands? No, and 0 is
the correct final number.** Pass-through means crew hands over a NAME and
doc-builder discovers the pack; crew never has to know that `solomon` exists.
Adding a reference would hardcode one client's name into a general-purpose
plugin, which is the coupling pass-through exists to avoid. So its 0 is correct
for a different reason than `report-builder`'s 0 -- that one is a deprecated
stub, this one is a plugin that is correctly ignorant of its clients. Neither
should be "fixed" to make a count look better.

### Blocker found 2026-09-12: there is no call site, and the routing table names a different tool

Measured before writing any wiring, and it changes the ticket's size. Both
findings below are about crew as it ships at 0.17.0.

**1. No crew agent or command invokes doc-builder.** Grepping `plugin/crew` for
`doc-builder`, `DOC_BUILDER`, `resolve_brand` and `--brand`, outside tests, returns
FOUR files and not one of them is an invocation: `crew_config.py:383` (a help
string naming the key), `crew_upgrade.py` (the migration block and its comment),
and `crew-setup/SKILL.md` (the setup doc). `agents/docs-writer.md:49` says a
document "ships as HTML, DOCX or PDF" and names no tool at all. So "pass the
configured name through as `--brand`" has nothing to pass it FROM. Pass-through
is still the right design; it just has no attachment point yet, and building one
is a larger change than wiring an existing one.

**2. Crew's document routing table exists, and doc-builder is not in it.**
`plugin/crew/skills/crew-house-style/SKILL.md:63-70` is the "Generating it"
section, and it is explicit -- "Route to the skill that owns the format. Do not
reimplement any of them" -- then routes DOCX to `anthropic-office-skills:docx`,
PDF to `anthropic-office-skills:pdf`, decks to `anthropic-office-skills:pptx` or
`ppt-master`, and `.vsdx` to `visio-diagrams`. **doc-builder appears nowhere.**

That is the real mismatch, and it is bigger than a missing call site.
`docs.theme` names a doc-builder brand pack, while crew's own documented
generation path goes to a tool that has no brand packs and would not know what to
do with the name. Wiring `--brand` into the route that exists is not possible,
because that route does not lead to doc-builder. So the ticket implies one of
three decisions, and this is a scoping question for whoever owns crew's document
story rather than something to settle inside a wiring ticket:

- **(a)** Add doc-builder to the house-style routing table as the owner of
  branded DOCX/PDF, and pass `--brand` there. Largest change: it edits crew's
  documented generation policy, not just a config key.
- **(b)** Leave the routing table alone and drop `docs.theme` / `docs.reportTheme`
  entirely, since crew does not use the tool they configure. Smallest change, and
  honest -- but it discards a setting someone wanted.
- **(c)** Keep the keys, keep them inert, and say so everywhere they appear.
  Already done as of this branch's first commit, which is why the two false
  present-tense claims are now corrected. This is the current state, and it is a
  stopping point rather than a fix.

**The degraded path the ticket asks for is already written, three lines below the
routing table.** `crew-house-style/SKILL.md:74-80` tells the crew that these are
user- and plugin-level skills crew does not bundle, that the one you want may be
missing, and to hand over the markdown saying "PDF export unavailable,
`anthropic-office-skills:pdf` is not installed" rather than improvising a
generator. Whatever lands for doc-builder should match that sentence shape rather
than invent a second convention.

**Corrected on this branch already (commit 1 of B):** `crew_upgrade.py:71` and
`crew-setup/SKILL.md:201` both described the pass-through in the PRESENT TENSE,
and both justified the `"neutral"` default with "the default resolves to exactly
what doc-builder already falls back to" -- which is false, as measured above:
doc-builder falls back to neutral only when no pack is discovered, and returns
the installed pack otherwise. That false premise is the entire stated reason the
default is `"neutral"` rather than `null`, so correcting it strengthens the
`theme: null` recommendation from a preference to a correction: the author's own
stated intent was "the default changes nothing about how documents come out
today", and `null` is what implements that intent while `"neutral"` overrides an
installed pack. Each key's `null` then means one thing -- "I have no answer, ask
the next authority" -- which for `reportTheme` is `theme` and for `theme` is
doc-builder's own resolution. One rule, not two.

**`report-builder`'s 0 references are correct, not a gap.** Its SKILL.md
declares it a deprecated stub as of 2026-09-10, superseded by `doc-builder`, and
its 2.0.0 catalog entry already says so. An earlier concern of mine that the
entry misdescribed the skill was unfounded -- team-lead checked and I am
recording the correction here so nobody re-opens it. `solomon-doc-builder` also
has 0 references in `plugin/crew`; that one IS the gap above, since it is the
pack the theme key is supposed to select. For contrast, `doc-builder` has 3 and
`bitbucket` has 8.

## A raw `Agent` dispatch writes no record, so crew misreports its own authorship

Found 2026-09-11, during the bitbucket merge-gate work. Belongs with the ticket C
/ D config work, not chased on its own.

`.work/dispatch.d/` holds exactly one record on this branch — a `developer` from
2026-09-06, made on `main`. Six roles were dispatched on `bitbucket-merge-gate`
in this session and not one of them was recorded, because the recorder fires on
crew's own command paths and a bare `Agent` tool call is not one of them.

The consequence is not a missing log line. `crew_state.py` and
`crew_config.py --models` read that store to answer "who wrote this diff", and
with a record that predates the merge-base they correctly report:

```
author family: claude  (STALE RECORD - the dispatch was made on a different
branch, so BOTH the recorded family and the config family are struck)
last dev dispatch: role=developer provider=claude model=None branch=main |
current branch=bitbucket-merge-gate
```

That is the guard failing *safe* — striking both families costs a reviewer rung
rather than clearing one wrongly — so nothing shipped unreviewed. But it fails
safe by accident: the store is not empty-and-honest, it is stale-and-confident,
and the guard only survives because the staleness check happens to catch it. A
record from a dispatch made on THIS branch would read as fresh and authoritative
while describing none of the work under review. That is the same class as
`crew_config.py --models` deriving author family from config describing the next
run — an unknown wearing the label of a check that happened.

Two candidate fixes, neither chosen: have the `Agent` path write a record, or
have the readers treat "no record for any commit in this range" as its own value
distinct from a stale one. The second is the one that matches this repo's
standing rule that a probe which can fail needs "could not tell" as a real value.

Re-measure before acting: `ls .work/dispatch.d/` and
`python3 <crew>/hooks/scripts/crew_config.py --root . --models`.

**Narrowed 2026-09-12, on the ticket C/D branch, where this was folded in as
instructed.** The choice between the two candidate fixes is no longer open, and
it was settled by what is reachable rather than by preference: **the first is
not implementable from inside crew.** The `Agent` tool is supplied by the
harness, not by the plugin; crew registers `PreToolUse`, `Stop`, `PreCompact`
and `SessionStart` hooks and none of them can interpose on a bare `Agent` call
to write a record for it. So "have the `Agent` path write a record" is a change
to Claude Code, not to this repo, and listing it as an option here reads as a
choice somebody could take.

That leaves the reader-side fix, which is also the one this repo's standing rule
already points at: **"no record covers any commit in this range" must be its own
value, distinct from "a record exists and is older than the range".** Today both
collapse into `STALE RECORD`, which is why the current behaviour is
stale-and-confident rather than empty-and-honest. Not done on this branch -- it
is a change to the author-family guard, and C/D were an authority and config
change; mixing them would have put a guard edit inside a release whose test
matrix is about something else.

**A second defect, found while running the suite for C/D.** Two tests in
`plugin/crew/tests/test_provider_table.py` call `crew_state.author_families(".")`
-- a literal `"."`, so they read whatever dispatch store is in the CURRENT
WORKING DIRECTORY rather than a fixture:

- `test_an_unset_copilot_model_is_not_barred_against_another_unset_one`
- `test_author_family_honours_a_per_role_dev_pin_over_the_block_default`

Both pass in a CLEAN checkout and both fail on any developer machine that has
ever used crew here, because `.work/` is gitignored and therefore absent from a
fresh clone but present locally. Measured rather than inferred: a worktree at
`7a234ba0` passes 124/124, and the same worktree with this repo's real
`.work/dispatch.json` and `.work/dispatch.d/` copied in fails exactly these two.

Say "clean checkout", not "CI". **CI does not currently run these tests at
all** -- the `Pytest (crew + gizmoduck plugins)` job collects 954 items and dies
on 12 gizmoduck `ImportError`s before executing one of them, so its log reports
neither test by name. An earlier draft of this entry said "both pass in CI",
which is an overclaim of exactly the kind this file exists to stop: it cites a
green signal that was never produced. The clean-worktree run is the real
evidence, and it is enough.

So this is environmental and pre-existing, not from the C/D branch -- but it
means the local suite is not the suite a clean checkout runs, and a developer
who sees these two red learns to ignore red. Fix belongs with the reader-side work above, since it is
the same store: pass a `tmp_path` root like the neighbouring tests do.

## No claim of the form "CI proves X" is available for any crew or gizmoduck test

Recorded 2026-09-12 so the four ticketed failures above and below are read
correctly. The `Pytest (crew + gizmoduck plugins)` job collects 954 items and
dies on 12 gizmoduck `ImportError`s before executing one of them. It therefore
reports NO test by name, passing or failing.

The consequence is easy to state and easy to forget: **until those imports are
fixed, "CI is green on this test" is not a sentence anyone can say about
anything in that job.** The only evidence available is a local run, and the only
honest phrasing is "clean checkout" or "local, at <ref>". An earlier entry here
said two tests "pass in CI"; they do not, because nothing in that job passes or
fails -- it never runs. Corrected, and recorded here rather than only at the
entry, because the trap is general.

The jobs that DO produce usable signal are `Marketplace` (`check`) and the
`test (ubuntu-latest)` / `test (windows-latest)` pair. Cite those freely.

## The specialist role tables disagree with the code, on `main`

Found 2026-09-12, running the full crew suite for the C/D branch. Pre-existing:
`plugin/crew/tests/test_role_ladder.py` fails these two at `7a234ba0` itself,
before any of this branch's commits.

```
FAILED test_onboarding_specialist_table_matches_the_code_set
FAILED test_the_readme_roster_table_matches_the_code
```

`crew_state.SPECIALIST_ROLES` names four roles that neither the onboarding table
nor the README roster lists: `powershell-7-expert`, `powershell-5.1-expert`,
`skill-author`, `exchange-online-specialist`. The code is the side with more, so
these are roles that exist and are undiscoverable rather than documented roles
that vanished -- a reader of either table cannot learn they can onboard them.

Belongs with ticket B (the crew referencing work), which is already about crew's
tables disagreeing with what is installed. Not fixed here on scope discipline:
C/D was an authority and config change, and these two suites were red before it
started and are equally red after.

## Five marketplace entries are shipping stale — inherited, not from this branch

Found 2026-09-11 while running `python3 scripts/check-marketplace.py` as the gate
for the bitbucket merge-gate work. The gate reported **6 problems, 0 of them
introduced by branch `bitbucket-merge-gate`**; `plugin/crew` was the one that
branch owed and it has since been bumped, leaving **5**. Each is a directory that changed
after its `version` was last set, so `claude plugin update` compares the declared
version, finds no change, and every already-installed copy reports "already at
the latest version" forever. Nothing in the repo looks wrong; the bug exists only
on other people's machines.

Measured per entry as `git log --oneline <sha-version-was-set>..origin/main --
<dir>` — all six are already red on `origin/main`, so none of this is caused by
uncommitted work:

| Entry | Version | Set at | Commits on `origin/main` since |
|---|---|---|---|
| `skills/exchange-mailbox-cleanup` | 1.0.0 | `b678e3cf` | 4 |
| `skills/exchange-mailbox-restore` | 1.0.1 | `b678e3cf` | 1 |
| `skills/jira-manager` | 1.0.0 | `ee9fcc2e` | 3 |
| `skills/power-automate-api` | 1.0.0 | `ee9fcc2e` | 3 |
| `plugin/gizmoduck` | 0.2.5 | `9338e89d` | 76 |
| ~~`plugin/crew`~~ | ~~0.16.33~~ | ~~`a1363e48`~~ | ~~5~~ — **fixed, now 0.16.34** |

Deferred rather than fixed, for two different reasons:

- The five above touch nothing this branch changed, so bumping them here is scope
  creep — and each bump pushes a plugin update to every machine that installed
  it, which is a shipping decision, not a lint fix. They need the user's call on
  whether to bump all five in one housekeeping commit or leave them.
- `plugin/crew` was the exception: commits `089af55e` and `f8bdb25e` on this
  branch touch five files under `plugin/crew/`, so that bump **was** owed by this
  branch, and it landed in the branch's final commit at 0.16.34 — both
  `.claude-plugin/marketplace.json` and `plugin/crew/.claude-plugin/plugin.json`,
  which must always match.

Re-measure before acting. These counts are facts about `origin/main` at
`bd4d125a`, and the gate is the only thing that tracks them.

### Not ticketed, decided instead

The review's one BLOCK — a real tenant snapshot committed under
`skills/power-automate-api/scripts/pa-snapshots/` and pushed to this public
repo — was raised with the user on 2026-09-08. They chose to leave what is
already published and stop it recurring: the file is untracked and
`skills/power-automate-api/.gitignore` now ignores the whole snapshot
directory. Nothing was rewritten or force-pushed. Recorded here because "we
decided not to" is the half that otherwise gets rediscovered as a new finding.
