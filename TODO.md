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

### 5. `core` consumers import the built artifact; `dist/` staleness is unchecked

`mcp-servers/packages/core/package.json:11-14` points `main`, `types` and
`exports` at `./dist/src/index.js`. Editing `src/*.ts` without `npm run build`
leaves `graph`, `intune`, `o365-admin` and `o365-user` on stale compiled JS,
with nothing in the edit path warning.

Every `src` file currently has a matching `.js`/`.d.ts`/`.map`, so it was built
at some commit — but no timestamp or hash comparison was done. **Inferred risk,
not confirmed staleness.** A CI check that rebuilds and diffs would settle it
permanently.

### 6. `check_skill_manifests` is unread

`scripts/check-marketplace.py:122`. Confirmed to exist and to sit between
`check_registration` and `check_plugin_manifests`. Which SKILL.md frontmatter
fields it cross-checks against the marketplace entry is unknown, so
`.crew/codemap/skills.md` records the four-place registration rule without
being able to say what this function adds to it.

### 7. The install-scripts matched-pair rule has no identified enforcer

`CLAUDE.md` requires `install-prerequisites.sh` and `.ps1` to keep identical
menu keys, order and default flags — otherwise `--select 3,7` means different
things on Windows and Linux. `scripts/check-marketplace.py` is said to enforce
it; the specific check was not located. Either find it and cite it, or write it.

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

## The installer menu undersells crew by six agents and three commands

`scripts/install-prerequisites.sh:859` and `scripts/install-prerequisites.ps1:843`
both read:

```
crew                    - Virtual dev team: 11 agents, 21 commands, safety hooks
```

Actual on disk after the 0.16.10 merge: **17 agents, 24 commands.** The two
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
