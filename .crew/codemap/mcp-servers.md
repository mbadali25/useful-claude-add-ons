# mcp-servers
anchor: useful-claude-add-ons@aab858e9
verified: 2026-10-03
paths: mcp-servers/packages/**, mcp-servers/scripts/**

## Does
An npm workspace monorepo shipping four thin stdio MCP servers for Microsoft Graph, Intune and
O365 - `packages/graph`, `intune`, `o365-admin`, `o365-user` - all built on one shared
`packages/core` that owns HTTP, auth, the write gate and the doctor. It is the odd one out in this
repo: everything else here is a Claude Code plugin or skill, and nothing in the marketplace
registers it. (DERIVED: `grep -c mcp-servers .claude-plugin/marketplace.json` returns 0.)

## Entry points
- `mcp-servers/packages/graph/src/cli.ts:1` - the process entry point: dispatches either a `doctor`
  subcommand or `createServer()` over a stdio transport. Representative of **three** of the four,
  not all four - see the `o365-user` landmine below.
- `mcp-servers/package.json:9-11` - root workspace scripts. `build` (`:9`) builds core first, then
  every workspace; `test` (`:10`) is `npm run build && npm run test:scripts && npm run test
  --workspaces`; `test:scripts` (`:11`) runs the stale-build guard's own suite.
- `mcp-servers/packages/core/src/writeGate.ts:19` - `assertWriteAllowed`, the gate every write tool
  passes through. Requires BOTH `MCP_MS_ALLOW_WRITES=1` in the environment (`:20`) and
  `confirm: true` on the individual call (`:26`).
- `mcp-servers/scripts/check-dist-fresh.mjs:126` - `main()`, the stale-build guard, wired as every
  package's `pretest` (`mcp-servers/packages/core/package.json:26`, and `:25` in each of the four
  server manifests).

## Owns data
- Nothing persistent of its own. State is the caller's Microsoft tenant, reached over HTTP.
- Compiled output under `mcp-servers/packages/core/dist/`, which is what is actually loaded -
  `mcp-servers/packages/core/package.json:11` points `main`/`types`/`exports` at `./dist/src/index.js`.
- `dist/` is **untracked** (DERIVED: `git ls-files mcp-servers/packages/core/dist` returns nothing).
  So there is no committed build to diff a rebuild against, and CI cannot ship a stale one.

## Calls out to
- Microsoft Graph and the Intune / O365 admin endpoints, via the shared client in
  `mcp-servers/packages/core/src/graphClient.ts`.
- **DERIVED: `GraphClient` sends its Bearer token only to its base URL's origin** (T-0090, 0.2.1).
  `pinToOrigin` (`mcp-servers/packages/core/src/graphClient.ts:64`) compares parsed scheme, host
  and port against the base and refuses userinfo and non-absolute URLs, throwing
  `GraphOriginError` (`:30`); the refused URL is named by `describeRefused` (`:48`) as scheme and
  host only, never `url.origin`, which is the inner Graph origin for a `blob:` URL and `null` for a
  non-special scheme. It is applied to the FINAL URL in
  `buildUrl` (`:166`, pin at `:168`, so a relative path concatenated off a path-less base is caught
  too) and to every page in `getAllPages` (`:246`, pin at `:257`), both before `getToken`
  (`request()` builds the URL at `:197`, then acquires the token at `:198`). Redirects are not
  pinned: Node's `fetch` strips `Authorization` on a cross-origin redirect (measured Node 22.22.1,
  T-0090 spec). Must-block / must-allow cases live in
  `mcp-servers/packages/core/test/graphClient.test.ts`.
- Azure identity providers through **two** separate paths: the admin credential chain at
  `mcp-servers/packages/core/src/adminAuth.ts:48` (`graph`, `intune`, `o365-admin`), and the
  device-code-only user credential at `mcp-servers/packages/core/src/auth.ts:66` (`o365-user`).

## Landmines
- **The credential chain caches its winner for the process lifetime.** `AdminCredentialChain`
  (`mcp-servers/packages/core/src/adminAuth.ts:48-109`) stores whichever link first succeeds in
  `this.resolved` and never retries an earlier, higher-priority link. Deliberate - the comment at
  `:44-46` says so - but fixing `MS_ADMIN_CLIENT_SECRET` after `cli` or `device` has won changes
  nothing until restart, and nothing tells you that. Re-verified unchanged 2026-09-06 at
  `1f97e51c`; still open as `TODO.md:218` (item 2; was `:110` at `f2bb919b`, `:80` at `6c497a14` and `:51` before that, each
  move an insertion earlier in the file - re-read at `f2bb919b` on 2026-09-25, same heading and body).
- **`scopesOverride` silently broadens a narrow scope request.**
  `mcp-servers/packages/core/src/adminAuth.ts:29-36` (the field and its doc comment), `:127`
  (`secret`) and `:144` (`cli`) force `.default` regardless of what the caller asked for. Only
  `device` (`mcp-servers/packages/core/src/adminAuth.ts:149-158` - no `scopesOverride` key, and the
  comment at `:155-158` says why) honours caller-supplied delegated scopes. Code that requests a
  narrow scope and receives `.default` did not fail - it was never asked. Re-verified unchanged
  2026-09-06 at `1f97e51c`; still open as `TODO.md:229` (item 3; was `:121` at `f2bb919b`, `:91`, and `:62` before that - re-read at
  `f2bb919b` on 2026-09-25, same heading and body).
- **`dist/` is what runs, `src/` is what you edit.** Editing a `.ts` file and then *starting a
  server* leaves the stale compiled JS in place and the change does not take effect. Nothing guards
  that path - the guard below is a `pretest`, so it fires on `npm test` and on nothing else.
- **The stale-build gap in the TEST path is CLOSED (2026-09-06, commit `4e2bfb78`).** Do not build a
  fix for it. `mcp-servers/scripts/check-dist-fresh.mjs` runs as every package's `pretest` and
  refuses a run whose newest `.js` under `dist/` is not strictly newer than the newest `.ts` under
  `src/` and `test/` (`:95-101`). Three design points that are easy to get backwards:
  - A consumer is checked by checking **core itself, recursively** (`:117-122`), never by comparing
    the consumer's `dist` to `core/src` - the latter passes the moment the consumer is rebuilt while
    `core/dist` is still stale.
  - **Equal mtimes are stale, not fresh** (`:96-97`, reasoning at `:82-94`). The commit message for
    `4e2bfb78` states the opposite ("Equal timestamps count as fresh"); the shipped code and
    `TODO.md:310-317` (was `:202-209` at `f2bb919b`, `:172-179`, and `:143-150` before that; re-read at `f2bb919b` on 2026-09-25, same reasoning)
    are the later, correct account. Trust the code.
  - An unreadable directory throws rather than returning mtime `0` (`:44-51`), because `0` compares
    older than everything and would read as fresh.
  14 tests at `mcp-servers/scripts/_test/check-dist-fresh.test.mjs` (DERIVED: 14 `test(` at column
  0), run by the root `npm run test:scripts`. (The commit message says ten; the file has 14.)
- **`o365-user` does not use the admin credential chain at all.** Its `cli.ts` calls
  `getUserCredential` (`mcp-servers/packages/o365-user/src/cli.ts:3`,`:11`), which is device-code
  only with no chain and no CLI fallback (`mcp-servers/packages/core/src/auth.ts:66-70`, rationale
  at `:55-61`). The two `adminAuth` landmines above therefore do **not** apply to it. The other
  three all call `buildAdminCredential` (`mcp-servers/packages/core/src/adminAuth.ts:176`).
- **Each server pins an exact core version, not a range.** All four carry
  `"@badali404/mcp-ms-core": "0.2.1"` at line `:29` of their own `package.json`, and core is at
  `0.2.1` (`mcp-servers/packages/core/package.json:3`). A core-only bump reaches nobody until all
  four servers republish.

## Unverified
- All four `cli.ts` files were read at this anchor, but only their first ~25 lines. Each package's
  `src/index.ts` (where `createServer` and the tool list live) and each
  `mcp-servers/packages/*/test/tools.test.ts` were not opened.
- The bodies of `mcp-servers/packages/core/src/jwt.ts` and `doctor.ts` were not read; their roles
  come from the README and from import sites. (`graphClient.ts` and `toolResult.ts` were read in
  full at `79127fa1` for T-0090.)
- `mcp-servers/packages/core/test/adminAuth.test.ts` exists and is offline/mocked, which answers "is
  adminAuth covered" - but it was not run here, so it is not known to pass at this anchor.
- **This worktree's `dist/` is stale right now** (measured 2026-09-06 by importing `checkPackage`
  from `mcp-servers/scripts/check-dist-fresh.mjs` and calling it per package - no build run): all
  five report `compiled output is not newer than core/test`. That is a fact about one untracked
  working tree on one machine, not about the repo, and it means `npm test -w packages/<anything>`
  here would exit 1 at `pretest` until `npm run build` is run from `mcp-servers/`. (JUDGEMENT: this
  is the guard working, not a defect.)

## Re-anchor provenance
Re-anchored `a02331ee` -> `1f97e51c` on 2026-09-06. The per-path check flagged
`mcp-servers/package.json` and `mcp-servers/packages/core/package.json` as moved; the cause was
`4e2bfb78`, which added the stale-build guard.

Re-read in full or in the cited region: `mcp-servers/package.json`,
`mcp-servers/packages/core/package.json`, all four server `package.json` files,
`mcp-servers/scripts/check-dist-fresh.mjs` (whole file),
`mcp-servers/scripts/_test/check-dist-fresh.test.mjs` (test names only),
`mcp-servers/packages/core/src/adminAuth.ts:20-176`, `mcp-servers/packages/core/src/auth.ts:55-70`,
`mcp-servers/packages/core/src/writeGate.ts:1-32`, all four `src/cli.ts` heads, and
`TODO.md:105-158` plus its heading list.

Corrected here: the `dist/` staleness gap was described as open and is closed in the test path
(`TODO.md:113`, item 5, CLOSED 2026-09-06); `graph/src/cli.ts` was called representative of all four
when `o365-user` takes a different credential path; the `device` link was cited at `:159` (the
`build:` line) rather than at the function and comment that carry the claim.

Not re-verified: nothing was built, installed or executed beyond importing `checkPackage` as a
library to read mtimes. No test suite was run.

**Re-anchored `1f97e51c` -> `34a333f0` on 2026-09-14, re-anchor-only.** `git diff --name-only
1f97e51c..34a333f0 -- mcp-servers/` shows one changed file, `mcp-servers/README.md`, which this note
does not cite - zero of the ~25 `path:line` citations above changed. Body prose was left as written
rather than rewritten. Spot-checked at this pass:
`mcp-servers/packages/core/src/writeGate.ts:19-26` (still gates on
`MCP_MS_ALLOW_WRITES` and `confirm: true` exactly as quoted) and the `check-dist-fresh.test.mjs`
test count (`grep -c '^test(' mcp-servers/scripts/_test/check-dist-fresh.test.mjs` still returns
14). The `1f97e51c` dates inside the Landmines section (2026-09-06 "re-verified unchanged") are
historical records of that earlier pass and are left as written; this pass did not repeat them.

**Re-anchored `34a333f0` -> `089a04b9` on 2026-09-22, re-anchor-only.** `git diff --name-only
34a333f0..HEAD -- mcp-servers/` returns nothing across 91 commits, so not one of the ~25
`mcp-servers/**` citations above could have moved. Nothing under `mcp-servers/` was re-read at this
pass and no claim about it is re-asserted as freshly checked - the empty diff is the whole evidence.

**Two cited paths outside `mcp-servers/` did move, and were checked line by line.** This note also
cites `TODO.md` (at `:51`, `:62`, `:113`, `:143-150`) and `.claude-plugin/marketplace.json` (the
`grep -c` claim in `## Does`); 64 of those 91 commits touched one of the two, and `TODO.md` grew
from 2346 lines to 3558. A path diff scoped to `mcp-servers/` alone would have missed that
entirely, which is the trap: a note's cited-path set is not the same thing as its subsystem
directory. Every one of the six citations was re-resolved against HEAD and is byte-identical to the
same line at `34a333f0` - `TODO.md:51` and `:62` are still the item 2 and item 3 headings, `:113` is
still item 5's `CLOSED 2026-09-06` heading, `:143-150` is still the unreadable-directory and
equal-timestamps reasoning, and `grep -c mcp-servers .claude-plugin/marketplace.json` still returns
0. TODO.md's 1212 new lines are all appended below `:150`.

Not re-verified at this pass: nothing was built, installed, executed or imported. The
`## Unverified` section above stands unchanged and its "this worktree's `dist/` is stale right now"
measurement is still a 2026-09-06 fact about one machine, not a fact re-taken here.

**Re-anchored `089a04b9` -> `84976536` on 2026-09-22, re-anchor-only, second pass
that day.** Two path diffs were run rather than one, because the previous entry
above records that a note's cited-path set is not the same thing as its
subsystem directory.

```
git diff --name-only 089a04b9..HEAD -- mcp-servers/
```
returns nothing. The whole TypeScript monorepo is untouched, so not one of the
`mcp-servers/**` citations in this note could have moved. Nothing under
`mcp-servers/` was read at this pass and no claim about it is re-asserted as
freshly checked - the empty diff is the whole evidence, exactly as at the
previous anchor.

```
git diff --name-only 089a04b9..HEAD -- <the paths this note cites>
```
returns two, `.claude-plugin/marketplace.json` and `TODO.md`. Both were
re-resolved and both citations still hold:

- `grep -c mcp-servers .claude-plugin/marketplace.json` still returns **0**, so
  the `## Does` claim that nothing in the marketplace registers this tree is
  re-measured, not carried. The file's only change is version fields on
  unrelated entries.
- `TODO.md:1-150` is **byte-identical** to the same range at `089a04b9`
  (`diff` over both renderings of that range, empty). So `:51` is still item 2's
  heading, `:62` item 3's, `:113` item 5's `CLOSED 2026-09-06` heading, and
  `:143-150` still the unreadable-directory and equal-timestamps reasoning. The
  eleven lines this commit range added to `TODO.md` land at `:1136` and after,
  below every citation here.

Spot-checked despite the empty subsystem diff, because a sha test that says
"nothing moved" is the cheap finding and this note's own history records a
claim that was false before its anchor was set:
`grep -c '^test(' mcp-servers/scripts/_test/check-dist-fresh.test.mjs` still
returns **14**, matching the count in the Landmines section.

Not re-verified at this pass: nothing was built, installed, executed or
imported. The `## Unverified` section stands unchanged, and its "this worktree's
`dist/` is stale right now" line is still a 2026-09-06 measurement of one
untracked working tree on one machine. It has now gone sixteen days without
being re-taken and should be read as a record of what was once true there, not
as a fact about this checkout.

**Re-anchored `84976536` -> `5d1fc5fd` on 2026-09-22, re-anchor-only.** Per-path
check over this note's cited paths (extracted the same way `_cited_paths` in
`plugin/crew/hooks/scripts/crew_freshness.py` would):

```
git diff --name-only 84976536..5d1fc5fd -- \
  mcp-servers/packages/graph/src/cli.ts mcp-servers/packages/core/src/writeGate.ts \
  mcp-servers/scripts/check-dist-fresh.mjs mcp-servers/packages/core/package.json \
  mcp-servers/packages/core/src/graphClient.ts mcp-servers/packages/core/src/adminAuth.ts \
  mcp-servers/packages/core/src/auth.ts TODO.md \
  mcp-servers/scripts/_test/check-dist-fresh.test.mjs mcp-servers/packages/o365-user/src/cli.ts \
  mcp-servers/packages/core/src/jwt.ts mcp-servers/packages/core/test/adminAuth.test.ts \
  mcp-servers/package.json mcp-servers/README.md
```
```
TODO.md
```

One file moved. `git diff --name-only 84976536..5d1fc5fd -- mcp-servers/`
returns nothing - the whole monorepo is untouched, exactly as at the previous
anchor - so no `mcp-servers/**` citation could have moved.

This note also cites `.claude-plugin/marketplace.json` in prose (the `grep -c`
claim in `## Does`), a leading-dot path the regex above does not extract, so it
was diffed by hand: `git diff --name-only 84976536..5d1fc5fd --
.claude-plugin/marketplace.json` returns the file. Re-checked:
`grep -c mcp-servers .claude-plugin/marketplace.json` still returns **0** -
`git diff 84976536..5d1fc5fd -- .claude-plugin/marketplace.json` is two hunks:
`doc-builder` (version string only, `1.5.2`→`1.5.3`) and `crew` (a
description rewrite - 27→28 slash commands, 19→20 skills - plus version
`0.20.10`→`0.20.11`). Neither hunk is near an `mcp-servers` entry, so the
conclusion is unaffected. Claim holds.

`TODO.md` was re-checked line by line. `:51`, `:62` and `:113` are still the
item 2, item 3 and item 5 headings, and `:143-150` is still the
unreadable-directory/equal-timestamps reasoning, byte-identical at both
commits (`sed -n` over both, diffed by eye - no change). `TODO.md` grew from
3569 to 3645 lines in this range; the new lines land after every citation this
note makes. The `check-dist-fresh.test.mjs` test count was re-run:
`grep -c '^test(' mcp-servers/scripts/_test/check-dist-fresh.test.mjs` still
returns **14**.

No content correction was needed. Not re-verified at this pass: nothing was
built, installed, executed or imported. The `## Unverified` section's
"this worktree's `dist/` is stale right now" line is now a 2026-09-06
measurement, unrefreshed for sixteen further days, and should still be read
as a record of what was once true on one machine, not a fact about this
checkout.

**Re-anchored `5d1fc5fd` -> `6c497a14` on 2026-09-25 (after crew 1.0, PR #225).
Re-derive provenance.** Per-path check over the same cited-path list recorded
at the previous entry, plus `.claude-plugin/marketplace.json`:

```
git diff --name-only 5d1fc5fd..6c497a14 -- <the paths this note cites>
```
returns two files: `.claude-plugin/marketplace.json` and `TODO.md`.
`git diff --name-only 5d1fc5fd..6c497a14 -- mcp-servers/` returns nothing - the
whole TypeScript monorepo is untouched by crew 1.0, so none of the
`mcp-servers/**` citations in Entry points, Owns data, Calls out to or
Landmines could have moved, and none was re-read.

- `.claude-plugin/marketplace.json`: `grep -c mcp-servers .claude-plugin/marketplace.json`
  still returns **0**. The diff is version bumps (`doc-builder` 1.5.3->1.7.2,
  `intune-graph` 1.1.0->1.1.3, `jira-manager` 1.0.2->1.0.3,
  `mermaid-svg-bitbucket` 1.2.4->1.2.5, `obsidian-canvas` 1.1.0->1.1.2,
  `wazuh-onprem` 1.1.0->1.1.1), the `crew` entry's description and version
  rewritten for the 1.0 lifecycle redesign (0.20.11 -> 1.0.25), and two skills
  removed from the catalog (`claude-memories-canvas`, `claude-memories-vault`).
  None of it touches an `mcp-servers` entry - the claim holds.
- `TODO.md` grew and every numbered item shifted down because content was
  inserted ahead of item 2. The three line-number citations this note makes
  into `TODO.md` were corrected in the body above, each re-read at its new
  location: `:51` -> `:80` (item 2 heading, same text), `:62` -> `:91` (item 3
  heading, same text), `:143-150` -> `:172-179` (the unreadable-directory and
  equal-timestamps reasoning inside item 5, same text). `grep -n '^### [0-9]\.'
  TODO.md` confirms item 2, 3 and 5 are still the same claims under new
  numbers (item 5's own CLOSED heading is now at `:142`, not separately cited
  by this note's active claims); nothing was renamed or reworded, only
  displaced by insertions earlier in the file. Historical provenance entries
  above that quote the old `:51`/`:62`/`:113`/`:143-150` numbers are left as
  written - they are records of what an earlier pass verified, not live
  citations.

Not re-verified at this pass: nothing under `mcp-servers/` was rebuilt,
installed or executed; the `## Unverified` section's dist-staleness measurement
is now nineteen days old and still describes one machine, not this checkout.

**Re-anchored `6c497a14` -> `f2bb919b` on 2026-09-25 (T-0015; origin/main after crew 1.0.26-1.0.28,
#226-#230).** Per-path check over the same cited paths:

```
git diff --name-only 6c497a14 f2bb919b -- mcp-servers/ .claude-plugin/marketplace.json TODO.md
```
returns `.claude-plugin/marketplace.json` and `TODO.md`; `mcp-servers/` is untouched again.

- `.claude-plugin/marketplace.json`: the only hunk is crew's `version` (`1.0.25` -> `1.0.28`,
  `:218`). `grep -c mcp-servers .claude-plugin/marketplace.json` still returns **0**.
- `TODO.md`: 30 lines were inserted after `:16` (the header block) and 177 more near the end, so
  every live citation above moved by exactly +30. Each was re-read at its new line rather than
  offset: `:110` and `:121` are the item 2 and item 3 headings, `:202-209` the unreadable-directory
  and equal-timestamps paragraph inside item 5 (item 5's CLOSED heading is now `:172`). Historical
  provenance entries above keep the numbers they recorded.

Not re-verified at this pass: nothing under `mcp-servers/` was built, installed or executed.

**Re-anchored `f2bb919b` -> `79127fa1` on 2026-09-28 (T-0090, the Graph token origin pin, on
`T-0090-build`).** Per-path check:

```
git diff --name-only f2bb919b 79127fa1 -- mcp-servers/ TODO.md .claude-plugin/marketplace.json
```
returns `.claude-plugin/marketplace.json`, `TODO.md` and ten `mcp-servers/` files - T-0090's
`graphClient.ts`, `index.ts`, `graphClient.test.ts`, the five `package.json` files (version `:3`
and each server's core pin `:29`, in place), `package-lock.json` and `README.md`.

- `graphClient.ts` was read in full and the origin-pin bullet under "Calls out to" added, each line
  re-read with `grep -n` at `79127fa1`; it is no longer in the Unverified not-read list.
- The exact-pin landmine now reads 0.2.1 (`package.json:3` in core, `:29` in each server, in place;
  `:25` pretest and core's `:11`/`:26` did not move).
- `TODO.md` grew ahead of every citation here: item 2's heading is now `:189`, item 3's `:200`,
  and the unreadable-directory / equal-timestamps paragraph `:281-288` - byte-identical to
  `f2bb919b`'s `:202-209` (`diff` over both ranges, empty). Corrected in the body.
- `grep -c mcp-servers .claude-plugin/marketplace.json` still returns **0**.

Executed for this pass: `npm --prefix mcp-servers test` and the T-0090 hand
sabotage of the pin. The `## Unverified` dist-staleness line is still a 2026-09-06 measurement of
one machine.
(Corrected at the next pass: this line first said "65 pass / 0 fail", which is the core suite
alone - `npm --prefix mcp-servers test` runs six `node --test` suites and each prints its own
`# pass` line.)

**Re-anchored `79127fa1` -> `eb4c4fa8` on 2026-09-28 (T-0090 review round 1 fix).**
```
git diff --name-only 79127fa1 eb4c4fa8 -- mcp-servers/ TODO.md .claude-plugin/marketplace.json
```
returns two files, `mcp-servers/packages/core/src/graphClient.ts` and its test. `describeRefused`
was inserted at `:42-50`, so every `graphClient.ts` citation from `pinToOrigin` down moved by +10
(re-read with `grep -n` at `eb4c4fa8`); `GraphOriginError` `:30` did not move. The
"origins only" clause above was false after this change and is corrected in place.

Executed for this pass: `npm --prefix mcp-servers test`, exit 0 - `check-dist-fresh` 14/0,
`o365-user` 6/0, `o365-admin` 7/0, `intune` 6/0, `msgraph` 6/0, `core` 69/0 (108 pass in all).
Re-measure by reading every `# pass` line of that run, not by counting `test(` in source: the
tables in `graphClient.test.ts` generate their tests in loops.

(Corrected at the T-0090 landing: the `f2bb919b` -> `79127fa1` paragraph first said "eleven
`mcp-servers/` files"; the list it gives and `git diff --name-only f2bb919b 79127fa1 -- mcp-servers/ | wc -l`
are both 10. Review round 2 FIX, owner-accepted, fixed at this re-anchor.)

**Re-anchored `eb4c4fa8` -> `b2553d26` on 2026-09-28 (T-0090 landing).** `b2553d26` is `T-0090-land`'s
merge of the reviewed `T-0090-build` (`631d3317`) onto main `ff59160f`.
```
git diff --name-only eb4c4fa8 b2553d26 -- mcp-servers/ TODO.md .claude-plugin/marketplace.json
```
returns `.claude-plugin/marketplace.json` (crew's version line only) and `TODO.md` (one hunk at
`:4470`, below every citation here); nothing under `mcp-servers/`. `TODO.md:189`, `:200` and
`:281` re-read, unchanged; `grep -c mcp-servers .claude-plugin/marketplace.json` is still **0**.
No citation moved.

**Re-anchored `b2553d26` -> `3648f59a` on 2026-09-28 (T-0075 review round 5, merge of `6387ab49`).** `git diff --name-only b2553d26 3648f59a -- mcp-servers/ README.md TODO.md .claude-plugin/marketplace.json` returns `README.md` (T-0075: crew's slash-command count 35 -> 36 at `:168` and `:874`, in place), `TODO.md` (T-0092's entry at `:5051`, below every citation here) and `.claude-plugin/marketplace.json` (crew's lines only); nothing under `mcp-servers/`. `TODO.md:189`, `:200` and `:281` re-read, unchanged; `grep -c mcp-servers .claude-plugin/marketplace.json` is still **0**. No citation moved.

## Re-anchor provenance - `3648f59a` -> `9e38a891`, 2026-09-29 (`T-0087-build` merges T-0010's `8ab733d7`)

`git diff --name-only 3648f59a 9e38a891` over the paths this note cites returns only `README.md`,
`CLAUDE.md`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md` and `scripts/check-tooling-pr.py`,
each cited here by name, never by line; nothing under `mcp-servers/` changed. Re-anchor only: no claim below moved and nothing was executed for this note.

## Re-anchor provenance - `9e38a891` -> `78b7080a`, 2026-09-30 (`T-0087-build` merges T-0088's main `a61a6f38`)

`f702cb24` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68's CI ruff and xdist changes, gate-first review, the steward skill and `crew-qa-standards`) into `T-0087-build`, with a merge commit; its conflicts were mechanical and both sides were kept. `a9bc8877` moves T-0087's version text to 1.0.70 and its harness rule to `.crew/verify.json` rule 35, `90b71bbf` re-sets crew 1.0.70, one past main's 1.0.69, and `78b7080a` rebuilds two guides. Every body citation of the form `path:line` was re-mapped by script (difflib over each cited file, from T-0087's `cb9b79b1` for a note line both parents carry and from `a61a6f38` for a line only main carries, to this tree; a bare `:N` binds to the last path named on its line, with or without a line number): none moved in this map. Citations the script could not attribute to a file that has that line (a bare `:N` after a different file's name, or a short name with no directory) predate this merge and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.

## Re-anchor provenance - `78b7080a` -> `b142d8e3`, 2026-09-30 (T-0087 review round 4 fixes)

`dc412c5c` limits the refunded-rerun marker to the `review` phase in `crew_autopilot._review_phase` (+2 lines, so every `crew_autopilot.py` line from `_toward_review` on moves by 2), with a must-block test and sabotage entry (ac); `b5f87132` re-maps `plugin/crew/docs/external-tool-formats.md`'s citations and adds a test that pins them; `af7eccbe` re-times `.crew/verify.json` rule 35 in place (no line moved); `b142d8e3` corrects a CHANGELOG figure. Every body citation of the form `path:line` was re-mapped by script (difflib from `78b7080a` to `b142d8e3`; a bare `:N` binds to the last path named on its line), and the `crew_autopilot.py` citations whose path is on the line above were re-mapped by hand. Citations the script could not attribute predate this change and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.
**Re-anchored `b2553d26` -> `8a084c6c` on 2026-09-28 (T-0085 merges main `6387ab49`, T-0089, T-0090, T-0092; crew 1.0.55).** `f97219dc` merged origin/main `6387ab49` into `T-0085-build` (mechanical conflicts only: crew version lines, CHANGELOG, anchors, provenance paragraphs, INDEX history cells, diagram headers, generated rules and graph); `8a084c6c` re-bumps crew to 1.0.55, one past main's 1.0.54. Each side had already re-verified its own changes (main's line to `136f4b33`/`2442d367`/`b2553d26`, T-0085's to `b82035e6`), so this pass checks the files BOTH sides changed: the crew version lines (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`, value only, same line), `CHANGELOG.md` (both sections kept; release bookkeeping), `plugin/crew/README.md` and `plugin/crew/commands/review.md` (main's T-0092 edits are in place and line-neutral: 2883 and 551 lines, as on T-0085's side), `plugin/crew/hooks/scripts/review_prompt.py` (main's docstring line split in two at `:6-7` and three `excluded` lines added at `:96-98` shift T-0085's lines below them by 4) and `plugin/crew/tests/test_review_prompt.py`. Every `path:N` citation into those files was compared by script against its text on the side that wrote it (`f3ad630b` or `6387ab49`) and at the merged tree; this note cites the root `README.md` only as `mcp-servers/`'s own README by bare name, and the root file's one change is T-0085's crew skill count (29 -> 30), which no claim here reads. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `8a084c6c` -> `07bcaf3b` on 2026-09-28 (T-0085 review round 1 fixes).** `07bcaf3b` changes `plugin/crew/hooks/scripts/crew_standards.py` (`gate_applies`, `checklist_block`, `stamp`, `_plugin_sets`, the module docstring), its tests and sabotage entries, `.crew/standards.md` (REPO-03's rule text), `.crew/verify.json` (rule 31 gains two test files; its `seconds` and `why`), `CHANGELOG.md` (T-0085's bump bullet, two lines to three), `plugin/crew/BUDGETS.md:10-11` (the count, in place), `plugin/crew/README.md` (three table rows, in place), `plugin/crew/commands/implement.md` (two lines reflowed in place; still 120 lines), `plugin/crew/commands/review.md` (step 6's reviewer-cell line becomes three, so lines below `:530` move by 2), `plugin/crew/skills/crew-standards/SKILL.md`, ADR 0004 and the working-with-codex guide. Every `path:N` citation in this note into those files was compared by script between `8a084c6c` and `07bcaf3b`: no citation into those files moved; the note cites `plugin/crew/README.md` and `review.md` by name only. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `07bcaf3b` -> `8abf7ffe` on 2026-09-28 (T-0085 provisional re-bump, crew 1.0.56).** `8abf7ffe` moves crew's version 1.0.55 -> 1.0.56 in place (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), because the round-1 fixes changed `plugin/crew/` after 1.0.55 was set and `scripts/check-marketplace.py`'s version-drift check failed on it; it also rewords `.crew/standards.md` REPO-03 (the provisional bump) and T-0085's `CHANGELOG.md` heading and bump bullet (three lines to four). Every `path:N` citation in this note into those files was compared by script between `07bcaf3b` and `8abf7ffe`: the version-file citations hold (value changed in place, same line) and every hit sits inside an earlier dated provenance paragraph, left as history; no body claim states the version. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `3648f59a` / `8abf7ffe` -> `e3f5fa49` on 2026-09-29 (T-0085 merges main `2693d0fa`, T-0075 landed as crew 1.0.59, and applies the owner-accepted round-1 standards amendments).** `0fd1bdf8` reverts T-0085's provisional crew 1.0.56 bump (`8abf7ffe`); `0fd92334` merges origin/main `2693d0fa` into `T-0085-build` (mechanical conflicts only: crew version lines take main's 1.0.59, crew counts take main's 36 commands with T-0085's 30 skills, `plugin/crew/tests/sabotage.py` registers both `CONFIG_MENU_MUTATIONS` and `STANDARDS_MUTATIONS`, anchors, provenance paragraphs, INDEX history cells, diagram notes, generated rules and graph); `e3f5fa49` amends GEN-01 and GEN-04 in `plugin/crew/skills/crew-standards/references/generic.md` and REPO-03 in `.crew/standards.md`, drops the version from T-0085's `CHANGELOG.md` heading and re-measures `plugin/crew/BUDGETS.md`. The build branch now declares main's 1.0.59 and carries no bump of its own (REPO-03 as amended). Every `path:N` citation outside provenance was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from the side that wrote it - `3648f59a` for a line in main's copy of this note, `0fd1bdf8` for a line only in T-0085's - to `e3f5fa49`, and every line that did not map to itself was read with `sed -n` / `grep -n`; the script attributes some bare `:N` to the wrong file, and those were read and hold. None moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `e3f5fa49` -> `001f8a78` on 2026-09-29 (T-0085 successor plan, review round 2's fixes).** `bc3602df`..`001f8a78` change `plugin/crew/hooks/scripts/crew_standards.py` (`_scope` gains the merge-base fallback for a kept but unusable scope record, `_has_scope_entry` and `_noted` are new, so every definition from `_scope` down moves by +8 to +30 lines), its tests (`test_crew_standards.py`, `test_review_run_standards.py`, `test_lifecycle_commands.py`) and `plugin/crew/tests/sabotage_standards.py` (nineteen new entries; `STANDARDS_MUTATIONS` moves `:21` -> `:35`), `plugin/crew/skills/crew-standards/SKILL.md` (step 3, +5 lines), `plugin/crew/README.md` (one table row, in place), `CHANGELOG.md` (one bullet in T-0085's section, so every line below it moves +8) and `plugin/crew/BUDGETS.md:11` (the count, in place). Every `path:N` citation in this note into those files was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from `e3f5fa49` to `001f8a78`; none moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `001f8a78` -> `a7f9c5e4` on 2026-09-29 (T-0085 merges main `8ab733d7`, T-0010 landed as crew 1.0.61, after review round 3's fixes `33521aa4`).** Nothing under `mcp-servers/` changed (`git diff --name-only 001f8a78 a7f9c5e4 -- mcp-servers` is empty); the paths the refresh check named are cited only inside earlier provenance paragraphs. No body citation moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `a7f9c5e4` / `b4f39fd3` -> `69c7edbd` on 2026-09-30 (T-0085's landing merge of main `a61a6f38`, crew 1.0.70).** `69c7edbd` merges T-0085's build head `0c6f01e0` (round 4, owner-accepted) onto origin/main `a61a6f38` (crew 1.0.69: #263-#267 and T-0088) on `T-0085-land`, and sets crew 1.0.70. Every body `path:N` citation was mapped by script (`difflib` equal blocks, from the anchor of whichever side's copy of this note carries the line - `a7f9c5e4` for T-0085's, main's own anchor for main's - to `69c7edbd`); each that mapped to one new line was moved, and each that did not map, or mapped differently from the two sides, was read with `sed -n` / `grep -n`. The script attributes a bare `:N` to the last path cited with a line number, so a bare `:N` after a path named without one (`.crew/verify.json` rule ranges, `crew_tfplan.py`, `sabotage_autopilot.py`, `crew_ticket.py`, `crew_standards.py`) was read against its real file and put back where the script moved it wrongly; `.crew/verify.json` lines up to `:339` did not move, and T-0085's rule is now `:361-373`, the last. A bare `review.md` citation is ambiguous since #267 added `crew-qa-standards/references/review.md`, so the script skipped those; `plugin/crew/commands/review.md` moved only below `:543` (+1, +3), and its cited lines above that were re-read. No citation in this note moved; nothing under `mcp-servers/` changed. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `69c7edbd` -> `7c86bd13` on 2026-09-30 (T-0085 landing: one sabotage anchor re-taken).** `git diff --name-only 69c7edbd 7c86bd13`, refresh artifacts aside, returns only `plugin/crew/tests/sabotage_standards.py`: the find and replace text of "review.md loses the self-check refusal" now end at `rebuild.` / `provider.`, because the merge joined main's exit-5 sentence onto that line. No line was added or removed; no citation moved. No suite was executed for this note.

**Re-anchored `7c86bd13` (`obsidian-vault`: `69c7edbd`) -> `c04dd2ef` on 2026-09-30 (T-0085 landing: `commands/review.md` rewrapped to its 551-line allowance, crew 1.0.71 then 1.0.72).** `git diff --name-only 7c86bd13 c04dd2ef`, refresh artifacts aside, returns the crew version files, `CHANGELOG.md`, `plugin/crew/BUDGETS.md` (20,707 lines, in place) and `plugin/crew/commands/review.md`: step 3's item 3 gains its last line on `:511`, item 4 and its `gh pr comment` paragraph and steps 8-9 are rewrapped at 100 columns, and the closing sentence is joined, taking the file from 557 to 551 lines with no text changed. Every line this note cites in `review.md` is at or above `:511` and holds; the version this note states now reads 1.0.72. No suite was executed for this note.

**Re-anchored `c04dd2ef` -> `8a89a596` on 2026-09-30 (T-0085 landing: catch-up merge of main `6813749b`, #268 T-0097, crew 1.0.70; T-0085 now 1.0.73).** `git diff --name-only 54192270 8a89a596` returns the crew version files, `CHANGELOG.md` (T-0097's entry below T-0085's), the 11 `.ps1` hook carriers (one `Resolve-CrewPython` line each: an empty probe answer is no longer piped into `ConvertFrom-Json`), `plugin/crew/tests/sabotage_scope.py` and `plugin/crew/tests/test_ps1_python_probe.py`. Citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 11 moved, 0 unmapped); version-line citations (`marketplace.json:218`, `plugin.json:3`, `PLUGINS.md:14`) hold by line and now read 1.0.73. The `Resolve-CrewPython` copies stay byte-identical across all 11 carriers, so the copy-list claims hold. No suite was executed for this note.

**Re-anchored `8a89a596` -> `9b6b0da7` on 2026-09-30 (T-0085 landing: Windows fail-open fix, crew 1.0.74).** `git diff --name-only 58431f49 9b6b0da7` returns the crew version files, `CHANGELOG.md`, `plugin/crew/hooks/scripts/crew_standards.py` (`import stat`, new `_ancestor_problem` before `gate_applies`, which now proves a receipt absent only when the nearest existing ancestor is a directory), `plugin/crew/tests/test_crew_standards.py` (new `test_gate_applies_when_a_file_parent_is_reported_as_not_found`) and `plugin/crew/tests/sabotage_standards.py` (one entry). Path-qualified citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 10 moved, 0 unmapped); `crew.md`'s bare `crew_standards.py` citations in its standards section were moved by the same diff (27). No suite was executed for this note.

**Re-anchored `9b6b0da7` -> `5c9a9db2` on 2026-09-30 (T-0085 landing: sabotage entry re-targeted, crew 1.0.75).** `git diff --name-only 33da9c91 5c9a9db2` returns the crew version files, `CHANGELOG.md` and `plugin/crew/tests/sabotage_standards.py` (the "receipt that cannot be looked up" entry now flips `gate_applies`' `OSError` verdict). Path-qualified citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 9 moved, 0 unmapped). No suite was executed for this note.

## Re-anchor provenance - `b142d8e3` / main `5c9a9db2`-`37f4e807` -> `2697bf67`, 2026-09-30 (T-0087 review round 5 successor, merge of main `9af34e57`)

`4e97588e` (golden leak check) and `2de03e41` (review ledger successors path) fix review round 5; `7b62e321` adds their sabotage entries. `7ccff1db` merges origin/main `9af34e57` (T-0085 landed as crew 1.0.75, with #268, #276, #277, #279) into `T-0087-build` with a merge commit, and `2697bf67` re-sets crew 1.0.76. The merge's map conflicts were mechanical: a hunk that differed only in numbers or in the anchor took main's side, and a provenance hunk kept both. Every body citation of the form `path:line` was then re-mapped by script (difflib from the parent the line came from - T-0087's `7b62e321` for a line T-0087 carries, main's `9af34e57` otherwise - to this tree; a bare `:N` binds to the last path named on its line). `.crew/verify.json` now holds T-0085's standards rule as rule 35 (`:361-373`) and T-0087's harness rule as rule 36 (`:374-399`); those descriptions were re-read by hand. Citations the script could not attribute predate this change and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.

## Re-anchor provenance - `2697bf67` -> `45f32c3c`, 2026-09-30 (T-0087, after merging main `9af34e57`)

`5f52ba61` re-maps `plugin/crew/docs/external-tool-formats.md`'s `review_run.py` and `review.md` citations to the merged tree (in place; no line moved), and `2b7e7a05`/`45f32c3c` step crew back and re-set 1.0.76 as the last `plugin/crew` commit. No citation in this note points into a line that moved. Re-anchor only: no claim moved and nothing was executed for this note.

## Re-anchor provenance - `45f32c3c` -> `7c88bf3d`, 2026-09-30 (T-0087 review round 6 fix)

`cff30f72` makes the committed-corpus test in `plugin/crew/tests/test_review_golden.py` run `golden_build.leak` on every fixture (host name included), adds `test_corpus_leak_check_refuses_a_planted_host_name`, and adds sabotage entries (ah)-(ai) to `plugin/crew/tests/sabotage_tooling.py`; its CHANGELOG bullet moved later CHANGELOG lines by 4, and the CHANGELOG citations above were re-mapped by script (difflib `45f32c3c` -> `7c88bf3d`). `49ed9a29` / `7c88bf3d` step crew back and re-set 1.0.76. No other cited line moved. Re-anchor only: nothing was executed for this note.

**Re-anchored `5c9a9db2` -> `06cb9b51` on 2026-09-30 (T-0086 slice 1: the Python standards set, on main `301e478a`).** `git diff --name-only 5c9a9db2 06cb9b51` over this note's paths returns T-0086's files - `plugin/crew/skills/crew-standards/references/python.md` (new, set PYTHON), `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/test_crew_standards.py` (four new tests), `plugin/crew/tests/sabotage_standards.py` (three entries), `plugin/crew/README.md`, `plugin/PLUGINS.md` (rows only), `plugin/crew/BUDGETS.md` (count only) and `CHANGELOG.md` (T-0086's entry on top) - plus main's own commits since `5c9a9db2`. Path-qualified citations into changed files were moved by a line diff (`/root/crew-tmp/t-0086/remap.py`, 9 moved); `plugin/crew/BUDGETS.md:10-11` citations stay on the claim line, whose number changed in place. No suite was executed for this note.
**Re-anchored `06cb9b51` -> `35100955` on 2026-09-30 (T-0086's merge of main `9af34e57`, #279: CI triggers, concurrency, PR CI on Python 3.12 only).** `git diff --name-only 06cb9b51 35100955` returns, outside refresh artifacts, only `.github/workflows/*.yml`, `AGENTS.md` and `.crew/verify.json` (one line rewritten in place, line count unchanged). No `AGENTS.md:NN` citation exists in any map, and no claim outside verification-harness.md states the CI trigger shape (checked by grep for `push, pull_request`, `six workflows`, `three Python versions`, `windows-latest`), so no citation moved. No suite was executed for this note.

**Re-anchored `35100955` -> `fb292689` on 2026-09-30 (T-0086 review round 1's FIX: PYTHON-07's finding count).** `git diff --name-only 35100955 fb292689` returns only `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-07's Why, `6` -> `7` in place, line count unchanged), `plugin/crew/tests/test_crew_standards.py` (two tests and a pinned table inserted after `:302`) and `plugin/crew/tests/sabotage_standards.py` (four docstring lines after `:43`, two entries at the end; `STANDARDS_MUTATIONS` `:54` -> `:57`, 49 entries by `len()`). Every `path:N` citation into those files sits inside an earlier dated provenance paragraph, left as history. No suite was executed for this note.

**Re-anchored `fb292689` -> `f2cf0508` on 2026-09-30 (T-0086's merge of main `b601d450`, #280 L-0521: opt-in self-hosted runners).** `git diff --name-only fb292689 f2cf0508` returns, outside refresh artifacts, only `.github/workflows/pytest-crew.yml` (the `test` and `crew-shell-matrix` `runs-on` expressions) and `AGENTS.md` (one inserted paragraph after `:50`). No map cites `AGENTS.md:NN` or `.github/workflows/pytest-crew.yml:NN`; the one claim about those jobs' runner placement is verification-harness.md's, which main's own L-0521 commit already updated and the merge carries. No citation moved. No suite was executed for this note.

**Re-anchored `f2cf0508` -> `38b220cf` on 2026-09-30 (T-0086 review round 2's FIXes, merge of main `a7524aac` (T-0087, crew 1.0.76) as `142421d0`, crew 1.0.77).** `27387d83` fixes round 2: `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-01's EncodingWarning quote whole, +1 line; PYTHON-03's splitlines table escapes U+2028/U+2029), `plugin/crew/tests/test_crew_standards.py` (two tests before `test_python_set_applies_to_python_files_only`), `plugin/crew/tests/sabotage_standards.py` (four docstring lines, two entries; `STANDARDS_MUTATIONS` `:57` -> `:61`, 51 by `len()`), `plugin/crew/BUDGETS.md` and `CHANGELOG.md`. `142421d0` merges main's T-0087 with a merge commit; its map conflicts were mechanical: anchors took T-0086's side, provenance hunks kept both (main's first), and one-line hunks differing only in numbers took theirs plus T-0086's own shift (ours + theirs - base, per number); INDEX rows keep main's history cell plus T-0086's additions; `sabotage.py`'s import `:84` -> `:85` and append `:3061` -> `:3062` were set in the body. `38b220cf` sets crew 1.0.77 (`plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:218`, `plugin/PLUGINS.md:14`). BUDGETS.md re-measured at 21,421 lines across 136 files. No suite was executed for this note.

## Re-anchor provenance - `3648f59a` -> `f5d0f1b1`, 2026-09-30 (T-0094 merges `a61a6f38`, crew 1.0.70)

`0cd952b2` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68, the review gate `review_gate.py`, the `crew-qa-standards` skill, parallel CI and `CLAUDE.md`'s evidence moved to `docs/claude-md-evidence.md`) into T-0094-build at `d331c192`. Its conflicts were the version lines, `CHANGELOG.md` (both entries kept, T-0094's first), `.crew/verify.json` (T-0094's rule 32 kept, main's three new rules after it as 33-35), `crew_refresh_check.py`'s imports (both kept) and `plugin/crew/BUDGETS.md` (re-measured, 19,921 lines across 132 files); no code map, diagram or rule file conflicted (main's maps were still at `bbd9a66d`, but for `obsidian-vault.md`). `f5d0f1b1` sets crew 1.0.70, one past main's 1.0.69. Per-path: `git diff --name-only 3648f59a f5d0f1b1 -- <the 18 tracked paths this note cites>` returns `.claude-plugin/marketplace.json`, `README.md`, `TODO.md`. Citations were re-mapped by a `difflib` line diff from each cited file's copy at the old anchor to `f5d0f1b1` (`/root/crew-tmp/t-0094/cite_apply2.py`, `cite_ident.py`, `cite_explicit.py`, machine-local): an explicit `path:N`, and a bare `:N` whose file is the one named before it in the paragraph, or the one whose old line carries the identifier beside the citation; every mapped line is text-identical at both ends. History positions ("at <sha>", "before", "on <branch>", "it was") and the provenance sections were left as written; a bare `:N` the scripts attributed to the wrong file was found by that identifier check and put back. `README.md` changed in place only (crew's counts), `TODO.md` below every citation here, `.claude-plugin/marketplace.json` only in crew's entry; nothing under `mcp-servers/`. `grep -c mcp-servers .claude-plugin/marketplace.json` is still **0**. No citation moved.

**Re-anchored `f5d0f1b1` (T-0094) / `5c9a9db2` (main) -> `1b9e4bfe` on 2026-09-30 (T-0094 merges main `9af34e57`, T-0085 landed as crew 1.0.75; review round 4's successor, crew 1.0.76).** `e1144866` merges origin/main `9af34e57` into T-0094-build at `7c261a19`; this map conflicted on anchor, version, provenance and cited-line text only (both sides' provenance kept, main's first; body hunks resolved to main's lines for files T-0094 does not change, T-0094's for its own). `c815bed8` and `f3fe692f` are the successor's code steps (`crew_refresh_check.py`: `_names_no_commit` new before `_moved_from`, `_rendered_verdict` pairs its source case-folded; `completion_audit.py`: `_default_artifacts` new after `_verdicts`; their tests, fixtures and sabotage entries), and `1b9e4bfe` sets crew 1.0.76 with the README, CHANGELOG and daily-workflow guide text. Per-path, `git diff --name-only 5c9a9db2..1b9e4bfe` over this note's 36 cited, existing paths returns `.claude-plugin/marketplace.json`, `.crew/verify.json`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/commands/implement.md`; from T-0094's side, `f5d0f1b1..1b9e4bfe` adds `.crew/standards.md`, `plugin/crew/commands/review.md`, `plugin/crew/hooks/scripts/crew_standards.py`, `plugin/crew/hooks/scripts/review_prompt.py`, `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/crew-standards/references/generic.md`, `plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_scope.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_crew_standards.py`, `plugin/crew/tests/test_ps1_python_probe.py`, `plugin/crew/tests/test_review_prompt.py` (main's T-0085, T-0097 and CI changes). Every body `path:N` citation was mapped by `/root/crew-tmp/t-0094/cite_map_merge.py` (difflib equal blocks, from the anchor of whichever side's copy carries the line; `MAIN_REV=origin/main`, `OURS_REV=7c261a19`) and each one it reported was read at HEAD. No body citation moved. No suite was executed for this note.

**Re-anchored `1b9e4bfe` -> `8a15557b` on 2026-09-30 (T-0094: `implement.md` step 6 rewrapped to its 120-line budget).** `git diff --name-only 1b9e4bfe 8a15557b`, refresh artifacts aside, returns `plugin/crew/BUDGETS.md` (the count, in place: 20,711 lines) and `plugin/crew/commands/implement.md`: the merged step-6 paragraph (T-0094's admission sentence beside main's self-check paragraph) was 122 lines, over `test_lifecycle_commands.py`'s 120-line command budget, and is rewrapped to 104 columns with its wording unchanged, so every line from the self-check paragraph down sits where main has it again (tracker `:112`, step 7 `:116`); the refresh check is still `:93`. No other body citation moved. No suite was executed for this note beyond `test_lifecycle_commands.py`.

**Re-anchored `8a15557b` -> `a0c171c7` on 2026-09-30 (T-0094 review round 5).** `git diff --name-only 8a15557b a0c171c7` over this note's cited paths, refresh artifacts and release bookkeeping aside, returns `plugin/crew/README.md` (one sentence extended in place, line count unchanged), `plugin/crew/hooks/scripts/crew_refresh_check.py` (`_present` new at `:327`, everything below it +19 to +25 lines). No body citation of this note names a moved line of those files. Citations checked with `/root/crew-tmp/t-0094/cite_apply3.py` (DRY, machine-local) and `grep -n`. No suite was executed for this note.

**Re-anchored `a0c171c7` (T-0094) / main -> `a0db0703` on 2026-09-30 (T-0094 merges origin/main `a7524aac`, T-0087 landed as crew 1.0.76, #281, and L-0521, #280; crew 1.0.77, before review round 6).** `f6f2c2f0` merges `a7524aac` into T-0094-build at `75565970`; `a0db0703` re-sets the version one past main's 1.0.76 (plugin.json, marketplace.json, `plugin/PLUGINS.md:14`, two README sentences, the CHANGELOG heading). The code maps conflicted on anchor, version, provenance and cited-line text only: both sides' provenance kept, main's first. In body hunks a citation into a file only one side changed takes that side's number (`crew_autopilot.py`, `review_ledger.py`, `sabotage.py` and `CLAUDE.md` main's; `crew_refresh_check.py` T-0094's); positions in files both sides changed (`.crew/verify.json`, `plugin/crew/tests/sabotage_refresh.py`) were re-measured on the merged tree: T-0087's harness rule is rule 37 at `.crew/verify.json:431-457`, after T-0094's rule 32; `REFRESH_MUTATIONS` is at `plugin/crew/tests/sabotage_refresh.py:119`; the CLAUDE.md Lessons line is `:144`. Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from each side's anchor (`a0c171c7` and main's own) to `a0db0703` (difflib equal blocks): no citation outside those re-measured positions fails both mappings. Carried as main has them, not corrected here: main's own `crew_autopilot.py` body citations in `crew.md` that already lag main's tree by a few lines (e.g. `next_phase` `:556`, the def is at `:559`) - outside T-0094's change.

**Re-anchored `a0db0703` (T-0094) / `38b220cf` (main) -> `65abeb8d` on 2026-09-30 (T-0094 merges origin/main `549cda24`, T-0086 landed as crew 1.0.77, #282, as `44407f8e`; the owner's split moves the harness half to L-0540 at `c974f997`; review round 6's successor `6ecb6403`..`b17266ed`; crew 1.0.78 at `65abeb8d`).** Per-path, `git diff --name-only a0db0703 65abeb8d` over this note's 50 cited, tracked paths returns `.claude-plugin/marketplace.json`, `CHANGELOG.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/crew-standards/references/python.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/sabotage_refresh.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_crew_standards.py`; from main's side, `git diff --name-only 38b220cf 65abeb8d` over the same paths returns `.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/commands/implement.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`. The merge's conflicts in this map were the anchor and provenance only (both kept, main's first). No body citation in this map names a line the successor or the merge moved (checked with `/root/crew-tmp/t-0094/cite_map_merge.py`, `MAIN_REV=origin/main`, `OURS_REV=b4d87187`, machine-local). No suite was executed for this note.

**Re-anchored `65abeb8d` -> `1f21f73b` on 2026-09-30 (T-0094 review round 7: `902fb96a`..`91da43bc` code and tests, docs, guide rebuilt, crew 1.0.78 un-set and re-set as `1f21f73b`).** `git diff --name-only 65abeb8d 1f21f73b` returns `CHANGELOG.md`, `docs/guides/crew/crew-1.0-daily-workflow.docx`, `docs/guides/crew/crew-1.0-daily-workflow.html`, `docs/guides/crew/crew-1.0-daily-workflow.pdf`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/test_refresh_admission.py`. No body citation in this map names a line that moved. No suite was executed for this note.

**Re-anchored `1f21f73b` (T-0094) / main -> `17d0b1d2` on 2026-09-30 (T-0094 merges origin/main `d1462bbd`, L-0529 landed as crew 1.0.80 (#283), and re-sets crew 1.0.81 in the merge commit).** `git diff --name-only 79ef56c4 17d0b1d2`, refresh artifacts aside, returns `.claude-plugin/marketplace.json`, `CHANGELOG.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/README.md`, `plugin/crew/tests/crew_fixtures.py`, `plugin/crew/tests/test_context_watch_python_resolver.py`, `plugin/crew/tests/test_event_claim_crash_safety.py`, `plugin/crew/tests/test_path_link_farm.py`, `plugin/crew/tests/test_ps1_python_probe.py`, `plugin/obsidian-vault/.claude-plugin/plugin.json`, `plugin/obsidian-vault/hooks/scripts/_test/test_python_probe_proof.py`: main's L-0529 files plus the version statements. The merge's conflicts were version lines and the generated rules' stamps; main's body lines kept. No body citation moved (checked with `/root/crew-tmp/t-0094/cite_map_merge.py`, `MAIN_REV=origin/main`, `OURS_REV=79ef56c4`; its only flags are history positions in verification-harness.md's per-commit lists, left as written). No suite was executed for this note.

## Re-anchor provenance - main `6a8c60b1` -> `c43a54c1`, 2026-09-30 (T-0028, feature half, crew 1.0.84)

T-0028 (the Kimi Code provider, feature half after the owner's split; the review launch is L-0527)
merged origin/main `6a8c60b1` (L-0531 #284 and T-0099 #278, crew 1.0.83) with rerere disabled, taking main's code
maps. The branch differs from main only in the Kimi provider's feature files (`crew_state.py`,
`crew_config.py` with the launch gate, `kimi_probe.py`, the templates, provider docs and tests,
`.crew/verify.json`, the release files). This note is main's copy; every body citation into a
changed file was mapped by a `difflib` line diff from `6a8c60b1` to `c43a54c1` with
`/root/crew-tmp/t-0028/refresh/reanchor2.py` (machine-local), each moved citation landing on the
same line text. T-0028's earlier branch provenance is in git history. Re-anchor
only (owner refresh-artifact standing rule, 2026-09-28); no test suite was executed for this note.

## Re-anchor provenance - `c43a54c1` -> `f4adf923`, 2026-09-30 (T-0028 re-sets crew 1.0.85)

`f4adf923` changes only the release files (crew 1.0.84 -> 1.0.85: `plugin.json`, `marketplace.json`,
`PLUGINS.md`, the README's version mention and the CHANGELOG heading), because T-0505 targets
1.0.84. No cited line moved; the version sentences were re-read. Re-anchor only (owner
refresh-artifact standing rule, 2026-09-28); no test suite was executed for this note.

## Re-anchor provenance - `f4adf923` -> `328fdf4a`, 2026-09-30 (T-0028 round-7 fixes, crew 1.0.85 re-set)

`233701d5` fixes review round 7's four FIXes in `kimi_probe.py` (the owner accepted round 7 and
ordered the fixes); `328fdf4a` re-sets crew 1.0.85. Body citations were mapped by `difflib` from
`ea90a4e4` to `328fdf4a` with `/root/crew-tmp/t-0028/refresh/reanchor2.py` (machine-local), each moved
citation landing on the same line text. Re-anchor only (owner refresh-artifact
standing rule, 2026-09-28); no test suite was executed for this note.

**Re-anchored `17d0b1d2` -> `c4e2eb98` on 2026-09-30 (L-0520 PR 1, the merge train CLI, after merging main 42d5ef58 (T-0094)).** `git diff --name-only 17d0b1d2 c4e2eb98` adds L-0520's PR 1 outside refresh artifacts (crew_train.py, done.md, README, two guides, CHANGELOG, TODO, BUDGETS.md in place, verify.json, two tests); path-qualified citations outside dated provenance were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`, machine-local). No suite was executed for this note.

**Re-anchored `c4e2eb98` -> `0be97503` on 2026-09-30 (L-0520 PR 1 merges main 42af3fb7 (L-0531)).** `git diff --name-only c4e2eb98 0be97503` returns, outside refresh artifacts, only L-0531's `plugin/crew/tests/sabotage_qa.py`, `.crew/verify.json` and release bookkeeping; path-qualified citations were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`). No suite was executed for this note.

**Re-anchored `0be97503` -> `14bb59ef` on 2026-09-30 (L-0520 PR 1 merges main 6a8c60b1 (T-0099)).** `git diff --name-only 0be97503 14bb59ef` returns, outside refresh artifacts, T-0099's `review_prompt.py`, `sabotage_review.py`, `test_review_prompt.py` and release bookkeeping; path-qualified citations were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`). No suite was executed for this note.

**Re-anchored `14bb59ef` -> `8bf710ed` on 2026-09-30 (L-0520 PR 1 review round 1 fixes).** `git diff --name-only 14bb59ef 8bf710ed` returns crew_train.py, done.md and README.md (edits in place), BUDGETS.md, two tests and the version files; path-qualified citations outside dated provenance were moved by a line diff (`/root/crew-tmp/l-0520/tools/l0520_remap.py`). No suite was executed for this note.

**Re-anchored `8bf710ed` -> `14b52c91` on 2026-09-30 (L-0520 PR 1 merges main bd4b2f30 (T-0028 #288, crew 1.0.85, and the mailgun skill), crew 1.0.86).**  No suite was executed for this note.

**Re-anchored `14b52c91` -> `0c3508e9` on 2026-09-30 (L-0520 PR 1 merges main f7caa37d (L-0561 #289: mailgun registered as skills/mailgun 1.0.1, both install scripts, README, INSTALLATION.md), crew stays 1.0.86).**  No suite was executed for this note.

**Re-anchored `0c3508e9` -> `fe524012` on 2026-09-30 (L-0513, the shared gate runner `scripts/gate-runner.py`; repository tooling, no plugin version, crew stays 1.0.86).** `git diff --name-only 0c3508e9 fe524012` returns, outside refresh artifacts, `.crew/verify.json` (rule 22's `run`, `seconds` and `why` in place, and rule 40 appended after T-0028's Kimi rule 39 at `:426-430`), `CLAUDE.md` (a two-line gate-runner pointer in Commands, so every line from the old `:14` moved down 2), `CHANGELOG.md`, `README.md` (main's re-pin `767fa3ef`, in place), `scripts/gate-runner.py` and `scripts/_test/gate-runner.py`; no `plugin/crew` path. Every `CLAUDE.md:N` and `.crew/verify.json:N` body citation in this note was re-read with `grep -n`/`sed -n`. No body citation in this note moved. No suite was executed for this note.

**Re-anchored `fe524012` -> `4eacfacf` on 2026-09-30 (L-0513 step 6 fix: the inner gate runner exits 128+signum after a signal).** `git diff --name-only fe524012 4eacfacf` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py` and `.crew/verify.json` (rules 22 and 40: `why` text only, in place; line count unchanged, rule 40 still `:426-430`). No body citation in this note moved. No suite was executed for this note.

**Re-anchored `4eacfacf` -> `3437cbdd` on 2026-10-01 (L-0513 Fix phase: review round 1's 2 BLOCK and 6 FIX; repository tooling, no plugin version, crew stays 1.0.86).** `git diff --name-only 4eacfacf 3437cbdd` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `CHANGELOG.md` (the L-0513 Unreleased entry, +9 lines) and `.crew/verify.json` (rules 22 and 40: `seconds` 12 -> 20 and `why` text, in place; line count unchanged, rule 40 still `:426-430`). No body citation of this map points into those files' changed lines. No suite was executed for this note.

**Re-anchored `3437cbdd` -> `e41bc6fd` on 2026-10-01 (L-0513 successor plan: review round 2's six fixes, after `git -c rerere.enabled=false merge origin/main` at `1899c370`; repository tooling, no plugin version of its own, crew is main's 1.0.89).** `git diff --name-only 3437cbdd e41bc6fd` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 20 -> 41, in place, line count unchanged), and from main's merge `.github/workflows/runner-autostart.yml`, `CHANGELOG.md` (+22 lines at `:31`, W-0116's entry), `plugin/PLUGINS.md:14`, `.claude-plugin/marketplace.json:224` and `plugin/crew/.claude-plugin/plugin.json:3` (crew 1.0.86 -> 1.0.89, in place), `plugin/crew/hooks/scripts/crew_refresh_check.py` (+43 lines, inserted after `:686`, `:694` and `:713`) and `plugin/crew/tests/test_refresh_admission.py`. No body citation of this map points into a moved line of those files. No suite was executed for this note.

**Re-anchored `e41bc6fd` -> `4a48f594` on 2026-10-01 (L-0513 Fix phase: review round 3's BLOCK, five FIX and the NIT; repository tooling, no plugin version of its own, crew is main's 1.0.89).** `git diff --name-only e41bc6fd 4a48f594` returns, outside refresh artifacts, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 41 -> 55 and their `why` text, in place, line count unchanged) and `CHANGELOG.md` (+7 lines inserted after `:29`, inside L-0513's own entry). No map cites a `scripts/gate-runner.py` line. The `CHANGELOG.md:N` figures inside earlier re-anchor notes describe the file at those notes' own anchors and are left as written; none is a body citation of current content. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `6e581365` on 2026-09-30 (T-0505 merges main 64b04c6b: W-0116 crew 1.0.89, runner auto-start #294; crew 1.0.91).** `git diff --name-only 0c3508e9 6e581365` outside the refresh artifacts returns W-0116's `plugin/crew/hooks/scripts/crew_refresh_check.py` and `plugin/crew/tests/test_refresh_admission.py`, `.github/workflows/runner-autostart.yml` (#294), the repo README, and T-0505's files: `promote-gate.sh`/`.ps1`, the new `_promote_tree.py`, `test_promote_gate_effective_tree.py`, `promote_tree_mutations.py`, `promote.md`, crew README, CONFIG.md (+2 lines in section 16), the crew-verification SKILL, INSTALLATION.md, `.crew/verify.json` (rule 4 path), the troubleshooting guide and its builds, the cloud handoff note and README, CHANGELOG.md and the version files (crew 1.0.91, past main's 1.0.89). A difflib re-map of every path-qualified `path:line` citation in the eight maps (history sections skipped) moved four: `crew_refresh_check.py:970` -> `:1013` (W-0116) and three `plugin/crew/CONFIG.md:2422-2429` -> `:2412-2419` (T-0505's sentence); none was unmapped. Re-applied by hand in `crew.md`: `promote-gate.sh:79` is the plain `crew_py()` call (re-read with `grep -n`), and `promote-gate.sh` is not a `crew_config.py` user (no `crew_config` import or `.crew/config.json` read in either flavour). Bare `:N` continuations and `CHANGELOG.md` citations in history sections were left as written. No suite was executed for this note.

**Re-anchored `6e581365` -> `9580571e` on 2026-10-01 (T-0505 raises promote.md's line ceiling in .budget-allowance.json, crew 1.0.91).** `git diff --name-only 6e581365 9580571e` outside the refresh artifacts returns only `plugin/crew/.budget-allowance.json`: promote.md's entry edited in place (`lines` 335 -> 380, reason `T8: to trim` -> a `raised:` reason), line count unchanged. No note cites a line of that file; a difflib re-map of every path-qualified citation moved none. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `bf7ce780` on 2026-09-30 (L-0558: L-0520 round-2 fixes and the rerere rule, crew 1.0.87).**  No suite was executed for this note.

**Re-anchored `bf7ce780` -> `dbad6519` on 2026-09-30 (L-0558 self-review fixes, crew 1.0.87).** `git diff --name-only bf7ce780 dbad6519` touches only crew_train.py, its tests and CHANGELOG.md's top entry; nothing this map cites by line moved. No suite was executed for this note.

**Re-anchored `dbad6519` -> `c8118baf` on 2026-09-30 (L-0558 lint fix and version re-set).** `git diff --name-only dbad6519 c8118baf` returns, outside refresh artifacts, `plugin/crew/tests/test_crew_train.py` (one trailing blank line dropped) and the three version files (stepped back and re-set to 1.0.87 on the same lines); nothing any map cites by line moved. No suite was executed for this note.

**Re-anchored `c8118baf` -> `afd976ee` on 2026-09-30 (L-0558 review round 1 fix).** `git diff --name-only c8118baf afd976ee` returns, outside refresh artifacts: CHANGELOG.md plugin/crew/README.md plugin/crew/hooks/scripts/crew_train.py plugin/crew/tests/test_crew_train.py - see the merge-train section for crew_train.py citations, re-mapped by definition name; no other cited line moved. No suite was executed for this note.

**Re-anchored `afd976ee` -> `d21fa82d` on 2026-09-30 (L-0558 round-2 fixes and main merge, crew 1.0.95).** `git diff --name-only afd976ee d21fa82d` returns, outside refresh artifacts: .claude-plugin/marketplace.json CHANGELOG.md plugin/PLUGINS.md plugin/crew/.claude-plugin/plugin.json plugin/crew/README.md plugin/crew/hooks/scripts/crew_refresh_check.py plugin/crew/hooks/scripts/crew_train.py plugin/crew/tests/test_crew_train.py plugin/crew/tests/test_refresh_admission.py - crew_train.py citations in the merge-train section were re-mapped by definition name; W-0116's crew_refresh_check.py and test_refresh_admission.py are main's (merged with rerere disabled at 8935fc25), and no line this map cites in them is relied on here without re-reading; the version files moved value, not line. No suite was executed for this note.

**Re-anchored `9580571e` -> `b0ac0e1a` on 2026-09-30 (L-0558 merges main 6fe0e0db (T-0505), crew 1.0.95).** Both histories are kept above: main's T-0505 chain to 9580571e and L-0558's chain to d21fa82d, merged at f7118a04 with rerere disabled. `git diff --name-only 9580571e b0ac0e1a` outside refresh artifacts is L-0558's change (crew_train.py, test_crew_train.py, plugin/crew/README.md, the two guide sources and their outputs, CHANGELOG.md, .crew/verify.json rule 37, the version files) plus main's W-0116 files already in 9580571e's ancestry; the merge-train section's crew_train.py citations were re-mapped at d21fa82d and crew_train.py has not changed since; no other cited line moved. No suite was executed for this note.

**Re-anchored `b0ac0e1a` (main) and `b0ac0e1a` (L-0558) -> `89ebda03` on 2026-10-01 (L-0558 merges main 52489039: T-0110 #297, T-0040 #290; crew 1.0.102).** Both histories are kept above; the merge (c481ada4) ran with rerere disabled. `git diff --name-only b0ac0e1a 89ebda03` outside refresh artifacts is 36 paths: L-0558's change (crew_train.py, test_crew_train.py, plugin/crew/README.md, two guide sources and outputs, CHANGELOG.md, .crew/verify.json rule 37, the version files) plus main's commits since b0ac0e1a; the merge-train section's crew_train.py citations hold (crew_train.py unchanged since 7a71faff); no other line this map cites was re-checked beyond the merge. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `5ab63076` on 2026-09-30 (L-0516: deadline polls replace fixed sleeps in the flaky crew tests, crew 1.0.89; verify.json gains rule 10 so later rules shift by one and six lines).**  No suite was executed for this note.

**Re-anchored `5ab63076` -> `805b0a25` on 2026-09-30 (L-0516 split per the tooling-PR rule: sabotage_qa.py back to main's copy, its four entries move to L-0563; verify.json rule 10's why and CHANGELOG reworded in place).**  No suite was executed for this note.

**Re-anchored `805b0a25` -> `7ecbdc7f` on 2026-09-30 (L-0516 re-bumps crew to 1.0.91 after the split; version files, CHANGELOG heading and the two version sentences only).**  No suite was executed for this note.

**Re-anchored `7ecbdc7f` -> `a9c0d9ab` on 2026-09-30 (L-0516: pylint R1732 fix in test_poll_fixtures.py (with-blocks, no line this map cites moves) and crew re-bumped to 1.0.92; version files, CHANGELOG heading and the two version sentences in place).**  No suite was executed for this note.

**Re-anchored `a9c0d9ab` -> `083cda66` on 2026-10-01 (L-0516 merges main `64b04c6b` (W-0116 #292: `crew_refresh_check.py` gains the Windows `_FINAL_PATH` check, `test_refresh_admission.py` two Windows premises; runner-autostart.yml) and crew re-bumped to 1.0.93; version files, CHANGELOG heading and the two version sentences in place).** `git diff --name-only a9c0d9ab 083cda66` over this map's cited paths: no cited line moved.  No suite was executed for this note.

**Re-anchored `083cda66` -> `908c03af` on 2026-10-01 (L-0516 review round 1 fixes: `poll_until` reads the clock before each probe after the first, `test_poll_fixtures.py` reaps its children with `wait(timeout=10)`, CHANGELOG corrected; crew re-bumped to 1.0.97; version files, CHANGELOG heading and the two version sentences in place).** `git diff --name-only 083cda66 908c03af` over this map's cited paths: no cited line moved.  No suite was executed for this note.

**Re-anchored `908c03af` -> `11f476a2` on 2026-10-01 (L-0516 merges main `6fe0e0db` (T-0505 #296: promote-gate judges the deploy's tree, crew 1.0.92) without rerere and re-bumps crew to 1.0.98).** Conflicts were refresh artifacts, CHANGELOG, BUDGETS.md and the version files only; each map keeps both branches' history notes (main's first). `git diff --name-only 908c03af 11f476a2` outside the refresh artifacts returns T-0505's files (`promote-gate.sh`/`.ps1`, `_promote_tree.py`, `test_promote_gate_effective_tree.py`, `promote_tree_mutations.py`, `promote.md`, crew README, CONFIG.md, `.budget-allowance.json`, the crew-verification SKILL, INSTALLATION.md, `.crew/verify.json` rule 4's path, the troubleshooting guide and its builds, the cloud handoff note and README), CHANGELOG.md, BUDGETS.md (21,621 lines, still `:11`) and the version files. Main's own re-maps of those files (`CONFIG.md:2412-2419`, `promote-gate.sh:79`) arrived with the merge; a difflib re-map of every path-qualified citation from `908c03af` to `11f476a2` moved none outside history sections, where `CHANGELOG.md` and `CONFIG.md` citations are left as written. `crew_refresh_check.py`'s `main()` `:1406` and `artifact_verdicts` `:1013` keep this branch's values (re-read with `grep -n`; main's map still read `:1363`/`:970`). No suite was executed for this note.

**Re-anchored `11f476a2` -> `1390bb23` on 2026-10-01 (L-0516 merges main `52489039` (T-0110 #297 at crew 1.0.97, T-0040 #290 at 1.0.98) without rerere and re-bumps crew to 1.0.100).** Main moved while this lane's suites ran. Conflicts were refresh artifacts, CHANGELOG and BUDGETS.md only; maps, diagram notes and INDEX keep both histories (main's first). A citation re-map that follows each line's origin (this branch's lines from `e9375690`, main's from `52489039`, each to `1390bb23`; history skipped) moved nothing: main's own lines already carry T-0040's moves (`CONFIG.md`, `crew_config.py`, crew README). Re-read by hand: `crew.md`'s W-0116 `_FINAL_PATH` sentence keeps this branch's text (`crew_refresh_check.py:716`); `verification-harness.md`'s verify.json paragraph now reads 42 rules / 443 lines (T-0040's rule 42 at `.crew/verify.json:482-493`, `default` `:441`, `unmapped` `:442`), and rule 39 `:418-431` is unchanged. No suite was executed for this note.

**Re-anchored `1390bb23` -> `0027f794` on 2026-10-01 (L-0516 merges main `05a679bf` (L-0558 #293 at crew 1.0.102) without rerere and re-bumps crew to 1.0.103).** Main moved while this lane's required checks ran. Conflicts were refresh artifacts, CHANGELOG and the version files only; maps, diagram notes and INDEX keep both histories (main's first). Main's change outside refresh artifacts is `crew_train.py`, `test_crew_train.py`, crew README, the daily-workflow and troubleshooting guides, CHANGELOG, the version files and `.crew/verify.json` rule 37's line rewritten in place (443 lines at both `1390bb23` and `0027f794`, so no `.crew/verify.json:N` citation moves). Main's own lines already carry L-0558's `crew_train.py` moves; no line this branch added cites `crew_train.py`, `test_crew_train.py`, the crew README or either guide by line. `crew.md`'s version sentence names 1.0.103 in place. No suite was executed for this note.

**Re-anchored `9580571e` (main's side of the merge) and `4a48f594` (L-0513's side) -> `de32cb87` on 2026-10-01 (L-0513 merges origin/main `44d3dbc6` at `293b78a1` with `git -c rerere.enabled=false`, bringing T-0110 #297 and crew 1.0.97, then review round 4's five fixes; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept above. `git diff --name-only 9580571e de32cb87` outside refresh artifacts returns L-0513's `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 55 -> 57 and their `why`, in place, line count unchanged), `CLAUDE.md` (L-0513's two-line pointer in Commands) and `CHANGELOG.md`, and main's T-0110 files: `.github/workflows/pytest-crew.yml`, `AGENTS.md`, eight files under `plugin/crew/tests/` (`crew_fixtures.py`, `test_msys_tmp_pin.py` and six others) and the version files `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md:14` and `plugin/crew/.claude-plugin/plugin.json:3` (crew 1.0.97, in place). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `de32cb87`, found every one mapping onto itself from at least one parent, except the in-place version lines and `CHANGELOG.md:N` figures inside history notes, left as written; `crew.md`'s version sentence now reads 1.0.97. No suite was executed for this note.

**Re-anchored `de32cb87` -> `f23b01b4` on 2026-10-01 (L-0513 Fix phase: review round 5's two FIX findings; repository tooling, no plugin version of its own, crew is main's 1.0.97).** `git diff --name-only de32cb87 f23b01b4` outside refresh artifacts returns `scripts/gate-runner.py` (`_valid_result` now takes the table step, requires phase/group/argv/cwd/timeout, and refuses a FAIL whose rc `classify()` would not call FAIL), `scripts/_test/gate-runner.py` (two new cases, `part_row`), `.crew/verify.json` (rules 22 and 40: `seconds` 57 -> 58 and their `why`, in place, line count unchanged) and `CHANGELOG.md` (+3 lines inside L-0513's entry, at :30-36). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped) from `de32cb87` found every one mapping onto itself except nine `CHANGELOG.md:N` citations in `crew.md`, shifted +3 to the lines they cited, and the in-place `.crew/verify.json:296`/`:430` lines. No suite was executed for this note.

**Re-anchored `f23b01b4` (L-0513's side) and main's side -> `71038cb9` on 2026-10-01 (L-0513 owner amendment for review round 6's BLOCK at `fbd48532`, then `git -c rerere.enabled=false merge origin/main` `52489039` (T-0040 #290, crew 1.0.98) at `74130bbd`, then rules 22 and 40 repriced at `71038cb9`; repository tooling, no plugin version of its own).** `git diff --name-only f23b01b4 71038cb9` outside refresh artifacts returns L-0513's `scripts/gate-runner.py` and `scripts/_test/gate-runner.py` (the BLOCK fix: no process-group signal once the leader is reaped, and its two cases), `CHANGELOG.md` (L-0513's entry +3 lines; T-0040's 1.0.98 entry now sits below it) and `.crew/verify.json` (rules 22 and 40 `seconds` 58 -> 60 and `why`, in place; T-0040's shell-route rule appended as rule 41 at `:432-437`), and T-0040's own paths, which main's side of this map already describes. Where the merge conflicted here it was the anchor header and these provenance notes: both sides kept, main's first. The `CHANGELOG.md:N` citations in older provenance notes name lines at the commits those notes name and were not shifted. Refresh artifacts per owner rule 2026-09-28; no test suite was executed for this note.

**Re-anchored `71038cb9` (L-0513's side) and `89ebda03` (main's side) -> `0d159692` on 2026-10-01 (L-0513 merges origin/main `05a679bf` - L-0558 #293, crew 1.0.102 - at `0d159692` with `git -c rerere.enabled=false`; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept, main's first. `git diff --name-only 71038cb9 0d159692` outside refresh artifacts is main's L-0558 change only: `plugin/crew/hooks/scripts/crew_train.py`, `plugin/crew/tests/test_crew_train.py`, `plugin/crew/README.md`, the daily-workflow and troubleshooting guide sources and their six builds, `.crew/verify.json`, `CHANGELOG.md` and the three version files (crew 1.0.102). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `0d159692`, found every one mapping onto itself from at least one parent except three `CHANGELOG.md:N` citations in `crew.md` from L-0513's side, moved to the lines they cited (`:485-486` -> `:519-520`, `:645-646` -> `:679-680`, `:274` -> `:308`); `crew.md`'s version sentence now reads 1.0.102. No suite was executed for this note.

**Re-anchored `0027f794` (L-0516's side) and `0d159692` (main's side) -> `ec95c8aa` on 2026-10-01 (L-0516 merges origin/main `cacf7ff0` - L-0513 #301, the gate runner; crew stays 1.0.102 on main - with `git -c rerere.enabled=false`; crew 1.0.104, re-bumped at `1f2114bc` past 1.0.103, which L-0510's worktree claimed first).** Conflicts were refresh artifacts and CHANGELOG only; each map keeps both re-anchor histories. `git diff --name-only 0027f794 ec95c8aa` outside refresh artifacts returns main's L-0513 paths (`.crew/verify.json` rule 22 rewritten in place at `:262-266` and its gate-runner rule appended at `:432-436`, `CLAUDE.md`, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`) and the three version files plus CHANGELOG; `git diff --name-only 0d159692 ec95c8aa` returns L-0516's own paths. A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor, found every one mapping onto itself from at least one parent except the version lines (changed in place) and nine `CHANGELOG.md:N` citations in `crew.md` from main's side, which L-0516's CHANGELOG entry above them moved by 35 (`:519-520` -> `:554-555`, `:679-680` -> `:714-715`, `:308` -> `:343`, `:676-677` -> `:711-712`, `:887-888` -> `:922-923`, `:898-899` -> `:933-934`, `:1114-1115` -> `:1149-1150`, `:1238` -> `:1273`, `:1134` -> `:1169`). `verification-harness.md`'s verify.json section now reads the merged tree (448 lines, 43 rules). No suite was executed for this note.

**Re-anchored `ec95c8aa` -> `5ffffbe3` on 2026-10-01 (L-0516 merges origin/main `ddcbf90d` - W-0115 #299, T-0040's shell-route sabotage mutations, crew 1.0.106 - with `git -c rerere.enabled=false` and re-bumps crew to 1.0.110, skipping 1.0.105 (L-0557), 1.0.107 (T-0504), 1.0.108 (L-0510) and 1.0.109 (T-0501)).** Conflicts were the three version files and CHANGELOG only. `git diff --name-only ec95c8aa 5ffffbe3` outside refresh artifacts returns W-0115's paths (`plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_shell.py`, `.crew/verify.json`'s last rule gaining one path line) plus the version files and CHANGELOG. A difflib re-map of every path-qualified citation (history notes skipped) moved two `plugin/crew/tests/sabotage.py` citations in `crew.md` by +2 (`:3055` -> `:3057`, `:3056` -> `:3058`; W-0115 adds an import at `:86` and a comment line at `:3055`), the nine main-side `CHANGELOG.md` citations in `crew.md` by +15 for W-0115's entry, and `verification-harness.md`'s verify.json header to 449 lines; every other citation maps onto itself. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `b1d8a4e8` on 2026-09-30 (L-0557: per-test XDG_CACHE_HOME for every pwsh the suites spawn, crew 1.0.89, obsidian-vault 0.4.16).** `git diff --name-only 0c3508e9 b1d8a4e8` returns, outside refresh artifacts, L-0557's test-only files (`plugin/crew/tests/conftest.py`, `plugin/crew/tests/crew_fixtures.py`, new `plugin/crew/tests/test_pwsh_cache_isolation.py`, both `test_flavour_guard.py` copies, the obsidian-vault `_test` suites, six `scripts/_test/*.sh`), `.crew/verify.json` (one new rule, appended after the Kimi rule), `plugin/crew/README.md` (one paragraph after the test-layer table), the harness reference's H4 table (one row), `CHANGELOG.md`, `plugin/crew/BUDGETS.md` and the version files. Body `path:line` citations into those files were moved by difflib from `0c3508e9` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local): 25 moved, in crew.md (CHANGELOG), obsidian-vault.md (its `_test` suites) and verification-harness.md (verify.json range unchanged). No hook or production script changed. No suite was executed for this note.

**Re-anchored `b1d8a4e8` -> `d9ccfd5a` on 2026-10-01 (L-0557 merges main 0c0275e8 (W-0116 #292, crew 1.0.89) and re-sets crew 1.0.95).** `git diff --name-only b1d8a4e8 d9ccfd5a` returns, outside refresh artifacts, W-0116's `plugin/crew/hooks/scripts/crew_refresh_check.py` (a final-path check in `_read_regular`'s no-dir_fd branch, hunks from :684) and `plugin/crew/tests/test_refresh_admission.py`, `CHANGELOG.md` (both sides' Unreleased entries kept) and the version files (crew 1.0.95). Body `path:line` citations into those files were moved by difflib from `b1d8a4e8` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local), each onto the same line text. No suite was executed for this note.

**Re-anchored `d9ccfd5a` -> `97ace923` on 2026-10-01 (L-0557 review round 1 fixes, crew 1.0.96).** `git diff --name-only d9ccfd5a 97ace923` returns, outside refresh artifacts, L-0557's test-only `plugin/crew/tests/conftest.py` (the per-test cache dir is now `tmp_path_factory.mktemp("xdg-cache")`), `plugin/crew/tests/crew_fixtures.py` (one comment), `plugin/crew/tests/test_pwsh_cache_isolation.py` (the static guard judges values and returned environments, reports unreadable suites), `CHANGELOG.md` (L-0557's entry, five lines longer) and the version files (crew 1.0.96: 1.0.95 is also claimed by L-0558, #293). Body `path:line` citations into those files were moved by difflib from `d9ccfd5a` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local): none in this map (all 10 are `CHANGELOG.md` in crew.md). No hook or production script changed. No suite was executed for this note.

**Re-anchored `97ace923` / `9580571e` -> `550c39cd` on 2026-10-01 (L-0557 merges main 6fe0e0db: T-0505 #296 crew 1.0.92, runner auto-start #294; crew stays 1.0.96).** `550c39cd` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were refresh artifacts, version files and CHANGELOG only. This side's notes were anchored `97ace923` and main's `9580571e`; `git diff --name-only 9580571e 6fe0e0db` outside the refresh artifacts returns only the 1.0.92 version files and CHANGELOG, so main's notes already describe every non-artifact change it brings, and this side's notes describe L-0557's. Body `path:line` citations were moved by difflib, each from the anchor of the side whose copy of this map carries the line (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 17 moved - 10 `CHANGELOG.md` in crew.md (T-0505's 1.0.92 entry now sits below L-0557's) and 7 `plugin/crew/CONFIG.md` in verification-harness.md (T-0505's CONFIG.md edit), every one an exact-text match. No suite was executed for this note.

**Re-anchored `550c39cd` -> `038d5d10` on 2026-10-01 (L-0557 merges main 44d3dbc6: T-0110 #297, crew 1.0.97; L-0557 re-sets crew 1.0.99 at `4fc11923`).** `038d5d10` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were version files, CHANGELOG and one generated rules file. `git diff --name-only 6fe0e0db 44d3dbc6` outside the refresh artifacts returns T-0110's `.github/workflows/pytest-crew.yml`, `AGENTS.md`, `plugin/crew/tests/crew_fixtures.py` (new helpers below L-0557's, auto-merged), seven crew test files, CHANGELOG and the 1.0.97 version files. T-0110 updated verification-harness.md's `pytest-crew.yml` sentence itself; the other files are cited by name only. Body `path:line` citations were moved by difflib (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 10 moved, all `CHANGELOG.md` in crew.md (T-0110's 1.0.97 entry now sits below L-0557's), every one an exact-text match. No suite was executed for this note.

**Re-anchored `038d5d10` / `44d3dbc6` -> `90186613` on 2026-10-01 (L-0557 merges main 52489039 at `327e6ec1`: T-0040 #290, crew 1.0.98; L-0557 re-sets crew 1.0.101 at `90186613`).** `327e6ec1` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were refresh artifacts, version files, CHANGELOG, BUDGETS.md's count and `.crew/verify.json` (both sides appended one rule; both kept). Main's notes (anchor line `44d3dbc6`) were re-taken by T-0040 on its own merged tree `52489039`, so a line only in main's copy of a map is measured from `52489039`; a line in this side's copy is measured from `038d5d10`. Body `path:line` citations were moved by difflib (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 73 moved, all from this side's lines - `plugin/crew/README.md` (+11 lines from T-0040 above :743), `plugin/crew/CONFIG.md` (+11 from T-0040), `CHANGELOG.md` (T-0040's 1.0.98 entry, then this side's below it), `plugin/crew/tests/test_crew_config.py` and `plugin/crew/hooks/scripts/crew_config.py` (T-0040); every one an exact-text match, none on a changed line. T-0040's own claims about crew_shell.py, crew_status.py and the shell-route config are main's notes above and were not re-derived here. No suite was executed for this note.

**Re-anchored `89ebda03` (main) and `90186613` (L-0557) -> `773ce841` on 2026-10-01 (L-0557 merges main `05a679bf`, L-0558 #293, crew 1.0.102, at `2169bd11` with rerere disabled; L-0557 re-sets crew 1.0.105 at `773ce841`).** Both provenance histories are kept above, main's first. Body citations were re-checked by mapping each one from the tree its line came from (`89ebda03` for main's lines, `74dd1aa5` for L-0557's) to this tree with difflib: no citation moved. Citations into the version lines of `plugin/crew/.claude-plugin/plugin.json`, `plugin/PLUGINS.md` and `.claude-plugin/marketplace.json` keep their line numbers (the value changed in place). No suite was executed for this note.

**Re-anchored `0d159692` (main, L-0513 #301) and `773ce841` (L-0557) -> `a9608aa5` on 2026-10-01 (L-0557 merges main `cacf7ff0`, L-0513 #301: `scripts/gate-runner.py`, no plugin version; rerere disabled; crew stays 1.0.105).** Both provenance histories are kept, main's first. Where both sides had re-mapped the same citation, main's line was taken, and each citation was then mapped with difflib from the tree its line came from (`cacf7ff0` for main's lines, `95036b4c` for L-0557's) to this tree: no citation moved. No suite was executed for this note.

**Re-anchored `a9608aa5` -> `c43a9ce3` on 2026-10-01 (L-0557 merges main `ddcbf90d`, W-0115 #299, crew 1.0.106, at `0597e5c6` with rerere disabled, and re-sets crew 1.0.111 at `c43a9ce3`).** The merge touched no code map. `git diff --name-only a9608aa5 c43a9ce3` outside refresh artifacts is W-0115's `plugin/crew/tests/sabotage.py`, `sabotage_shell.py` and `.crew/verify.json` plus the version files and CHANGELOG; each citation into a changed file was mapped with difflib from `92448f1a` to this tree: no citation moved. No suite was executed for this note.

**Re-anchored `5ffffbe3` (main, L-0516 #298) and `c43a9ce3` (L-0557) -> `6053b65d` on 2026-10-01 (L-0557 merges main `2906dcbd`, L-0516 #298, crew 1.0.110, at `2f3fb34c` with rerere disabled, and re-sets crew 1.0.114 at `6053b65d`).** Both provenance histories are kept, main's first, and main's body citations were taken where both sides had re-mapped the same one. Each citation into a changed file was then mapped with difflib from the tree its line came from (`2906dcbd` for main's lines, `a54ff87b` for L-0557's) to this tree: no body citation moved; the `.crew/verify.json:482-493` range in L-0516's provenance note was kept, because it describes that tree. No suite was executed for this note.

**Re-anchored `6053b65d` -> `f5cab1f9` on 2026-10-01 (T-0503 merges origin/main `ffd11270`, L-0557 #300, crew 1.0.114, at `f5cab1f9` with rerere disabled; bitbucket 1.2.3).** The merge took main's side of every code map. `git diff --name-only ffd11270 f5cab1f9` is T-0503's own change only: `.claude-plugin/marketplace.json` (bitbucket version), `CHANGELOG.md` (its entry, 33 lines at the top), the `bitbucket` catalog row in `README.md` and `skills/README.md` (edited in place, no line count changed), `docs/handoff/cloud/T-0503.md`, and `skills/bitbucket/` (`SKILL.md`, `references/api.md`, `scripts/_test/merge_gate.sh`). Every citation into those files was compared by script against `ffd11270` (158 checked across the eight maps); no other cited line moved. Re-anchor only, under the refresh-artifact standing rule (owner 2026-09-28); no suite was executed for this note.

**Re-anchored `f5cab1f9` -> `b4f04e23` on 2026-10-02 (L-0578 merges origin/main `8d84786d`, W-0117 #302, crew 1.0.115, at `b4f04e23` with rerere disabled; crew 1.0.119).** L-0578's own change is `review_metrics.py` (new), `review_run.py`, `review_patch.py`, `commands/review.md`, the README, BUDGETS.md, external-tool-formats.md, `.crew/verify.json` rule 38, its tests and sabotage entries, and the version files and CHANGELOG. Every full `path:line` citation into a changed file was compared by script (difflib) against the old anchor: none moved; the only citations whose line text changed are the version and count lines (`plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:224`, `plugin/PLUGINS.md:14`, `plugin/crew/BUDGETS.md:10-11`), which still sit on the lines they cite. No suite was executed for this note.

**Re-anchored `3648f59a` -> `0da787d3` on 2026-09-29 (T-0107, gizmoduck 0.5.4). Current despite the lag.** `crew_refresh_check.py` named README.md as changed since the anchor. T-0107 edits exactly one line of each, in place (`git diff --numstat 2693d0fa 0da787d3 -- README.md plugin/README.md` is `1 1` for both): the gizmoduck catalog row, `README.md:875` and `plugin/README.md:415`, gains one clause naming the routine. No line shifted, and a script over every `README.md:N[-M]` citation in `.crew/codemap/` found none covering either line. `plugin/PLUGINS.md` changes only at `:441`, `:446`, `:451` and `:470` (+2 lines after it), and no note cites a `PLUGINS.md` line at or after `:441`. No claim re-read; nothing was executed for this note.

**Re-anchored `6053b65d` -> `40292eca` on 2026-10-02 (T-0107 merges origin/main `ffd11270`, without rerere). Current despite the lag.** `40292eca` merges origin/main into `T-0107-build`; the header conflict took main's anchor and both sides' provenance notes were kept, main's first. `crew_refresh_check.py` named README.md and plugin/README.md: `git diff --numstat 6053b65d 40292eca -- README.md plugin/README.md` is `1 1` for each, T-0107's gizmoduck catalog row edited in place, now `README.md:876` (main's side added a line above it) and `plugin/README.md:415`. The only citations covering those lines sit in dated notes that state their own commit's coordinates. gizmoduck is re-set to 0.5.4, one patch above main's 0.5.3, after the last content change. Nothing was executed for this note.

**Re-anchored `f5cab1f9` -> `e60394fd` on 2026-10-02 (T-0107 merges origin/main `8d84786d`, without rerere). Current despite the lag.** `e60394fd` merges origin/main (W-0117, crew 1.0.115) into `T-0107-build`; the header conflict took main's anchor and both sides' provenance notes were kept, main's first. Against the scope base `8d84786d`, `crew_refresh_check.py` named README.md and plugin/README.md: `git diff --numstat 8d84786d e60394fd -- README.md plugin/README.md` is `1 1` for each, T-0107's gizmoduck catalog row edited in place, still `README.md:876` and `plugin/README.md:415`. The only citations covering those lines sit in dated notes that state their own commit's coordinates. gizmoduck stays 0.5.5 (main is 0.5.3). Nothing was executed for this note.

**Re-anchored `b4f04e23` -> `56f28a16` on 2026-10-02 (T-0107 merges origin/main `04dde5a2`, without rerere). Current despite the lag.** The header conflict took main's anchor and both sides' provenance notes were kept, main's first. Against the scope base `04dde5a2`, `git diff --numstat 04dde5a2 56f28a16 -- README.md plugin/README.md` is `1 1` for each: T-0107's gizmoduck catalog row, edited in place (`README.md:889`, `plugin/README.md:415`). The only citations covering those lines sit in dated notes that state their own commit's coordinates. gizmoduck stays 0.5.5 (main is 0.5.3). Nothing was executed for this note.

**Re-anchored `56f28a16` -> `d6e51bb8` on 2026-10-02 (T-0107 merges origin/main `d2ec37d3`, W-0120's re-pin, without rerere; no conflict).** `git diff -U0 56f28a16 d6e51bb8 -- README.md` is main's two install-URL lines, `:12` and `:18`, re-pinned in place to `04dde5a2` (no line shifts); T-0107's gizmoduck catalog row is still `README.md:889` and `plugin/README.md:415`, unchanged. No body citation covers `:12` or `:18` here. gizmoduck stays 0.5.5 (main is 0.5.3). Nothing was executed for this note.

**Re-anchored `6053b65d` -> `1066a28d` on 2026-10-01 (L-0575, the recurring-findings checklist for the implementer; `1066a28d` adds only refresh artifacts and the rebuilt daily-workflow guide HTML, DOCX and PDF to `dac06883`).** `git diff --name-only 6053b65d dac06883` returns `.crew/verify.json` (one rule appended, the last, `:454-464`), `CHANGELOG.md` (one Unreleased section, 18 lines), `docs/guides/crew/src/daily-workflow.md`, `plugin/crew/BUDGETS.md` (the count at `:11`), `plugin/crew/README.md` (one paragraph at `:727`), `plugin/crew/commands/fix.md` (step 4, one line), `plugin/crew/commands/implement.md` (step 2 and the method paragraph, still 120 lines), `plugin/crew/skills/crew-qa-standards/SKILL.md`, and three new files: `plugin/crew/hooks/scripts/recurring_findings.py`, `plugin/crew/skills/crew-qa-standards/references/recurring-findings.md` and `plugin/crew/tests/test_recurring_findings.py`. Each citation into a changed file was mapped with difflib from `6053b65d` to this tree; body citations are named below when one moved, and the citations inside earlier provenance notes were kept, because they describe their own trees. No suite was executed for this note.

**Re-anchored `1066a28d` -> `871c5043` on 2026-10-02 (L-0575 review round 1 fixes).** `git diff --name-only 1066a28d 871c5043` returns `.crew/verify.json` (the L-0575 rule's why, in place), `plugin/crew/BUDGETS.md` (the count at `:11`), `plugin/crew/README.md` (the L-0575 paragraph, in place), `plugin/crew/commands/implement.md` (step 2 re-wrapped in place, still 120 lines), `recurring_findings.py`, its data file and its suite. Each citation into a changed file was mapped with difflib from `1066a28d` to this tree: no citation moved. No suite was executed for this note.

**Re-anchored `b4f04e23` (main) and L-0575's `871c5043` -> `2859ab05` on 2026-10-02 (L-0575 merges origin/main 8d84786d at f12f742c and d2ec37d3 at 2859ab05, rerere disabled; crew 1.0.123. Both provenance histories kept, main's first. Body citations were mapped with difflib from the tree each line came from (4234c443 for L-0575's lines, d2ec37d3 for main's): ten CHANGELOG.md citations in crew.md moved +19 (L-0575's entry above main's); verification-harness.md's two verify.json ranges were set by hand to :448-453 (rule 41) and :455-465 (L-0575's rule); crew.md's version sentence reads 1.0.123. History notes were not re-mapped. No suite was executed for this note).**

**Re-anchored `b4f04e23` (main) and L-0575's `2859ab05` -> `99c8f66e` on 2026-10-02 (L-0575 merges origin/main 7ba4f9ea (L-0572 #309 crew 1.0.126, L-0593 #312) at 99c8f66e, rerere disabled; crew 1.0.129 is set in the last commit. Body citations were mapped with difflib from the tree each line came from (9dad04ef for L-0575's lines, 7ba4f9ea for main's): ten CHANGELOG.md citations in crew.md moved +21 (L-0572's entry, below L-0575's); verification-harness.md's verify.json ranges were set by hand to :469-476 (rule 41) and :486-496 (L-0575's rule, after L-0572's at :478-485). History notes were not re-mapped. No suite was executed for this note).**

**Re-anchored `d6e51bb8` (main) and L-0575's `99c8f66e` -> `273ec0f6` on 2026-10-02 (L-0575 merges origin/main a9b4734d (L-0576 #306 crew 1.0.128, L-0577 #305, T-0107 #273) at 273ec0f6, rerere disabled; crew 1.0.129 is re-set in the last commit. Both provenance histories kept, main's first. Body citations were mapped with difflib from the tree each line came from (986c9ca5 for L-0575's lines, a9b4734d for main's): ten CHANGELOG.md citations in crew.md moved +113 (main's new entries sit below L-0575's), and ten plugin/crew/README.md citations in crew.md and repo-docs.md moved +2 (L-0575's README paragraph at :727 sits above them); verification-harness.md's verify.json ranges were set by hand to :474-481 (rule 41), :483-490 (L-0572) and :491-501 (L-0575, last). History notes were not re-mapped. No suite was executed for this note).**

**Re-anchored `6053b65d` -> `3a33161c` on 2026-10-01 (L-0555 PR 1: the diagnostic CI verify-gate receipt - `plugin/crew/hooks/scripts/ci_receipt.py`, `.github/workflows/verify-gate.yml` (mmdc pinned at 12.0.0), `plugin/crew/tests/test_ci_receipt.py` - merging origin/main `ffd11270` (L-0557 #300, crew 1.0.114) at `751d6d2a` with rerere disabled, crew 1.0.116, skipping 1.0.115 claimed by another lane).** Refresh-artifact conflicts were resolved by taking main's side and redoing this pass. `git diff --name-only 6053b65d 3a33161c` outside refresh artifacts returns L-0555's paths only: the three new files, `.crew/verify.json` (one rule appended last, at `.crew/verify.json:481`), `CHANGELOG.md` (+16 lines at the top), `plugin/crew/README.md` (+23 lines in section 17), `scripts/gate-runner.py` (+2 lines in EXCLUDED_WORKFLOWS), `plugin/crew/BUDGETS.md` (count only) and the version files. A difflib re-map of every path-qualified citation into those files (history notes skipped) moved nine `CHANGELOG.md` citations in `crew.md` by +16 and six `plugin/crew/README.md` citations in `repo-docs.md` by +23; every other citation maps onto itself. No suite was executed for this note.


**Re-anchored `3a33161c` -> `79c116b4` on 2026-10-01 (L-0555 gate fix: `ci_receipt.py` asks `review_gate.gate_state` for NO_GATE instead of reading `.crew/config.json` itself; `plugin/crew/BUDGETS.md` count corrected; crew 1.0.116 re-set at `79c116b4`).** `git diff --name-only 3a33161c 79c116b4` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py` and `plugin/crew/BUDGETS.md` (the count line only, changed in place, so the `plugin/crew/BUDGETS.md:10` and `:11` citations keep their lines; the version files net to no change). No note cites `ci_receipt.py` at a line, so every citation maps onto itself. No suite was executed for this note.


**Re-anchored `79c116b4` -> `8b21ecc3` on 2026-10-01 (L-0555 pre-review fix: `ci_receipt.py` resolves gh with shutil.which and folds the check reason onto one line; crew 1.0.116 re-set).** `git diff --name-only 79c116b4 8b21ecc3` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py` and `plugin/crew/tests/test_ci_receipt.py` (the version files net to no change). No note cites either at a line, so every citation maps onto itself. No suite was executed for this note.


**Re-anchored `8b21ecc3` -> `1e2762a0` on 2026-10-02 (L-0555 review round 1 fixes: `ci_receipt.py` requires the receipt's gate_impl to match HEAD's and its docstring says diagnostic; the verify.json rule is priced 10s from measured runs; crew 1.0.116 re-set).** `git diff --name-only 8b21ecc3 1e2762a0` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py`, `plugin/crew/tests/test_ci_receipt.py` and `.crew/verify.json` (the last rule's line edited in place, no line moved); the version files net to no change. Every citation maps onto itself. No suite was executed for this note.


**Re-anchored `1e2762a0` -> `b10e3895` on 2026-10-02 (L-0555 review round 2 fixes: `ci_receipt.py` treats an unreadable stand-down as UNKNOWN, re-reads the stand-down at the last look, and anchors the origin host to github.com; crew 1.0.116 re-set).** `git diff --name-only 1e2762a0 b10e3895` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py` and `plugin/crew/tests/test_ci_receipt.py`; the version files net to no change. No code map cites a line of either file, so every citation maps onto itself. No suite was executed for this note.


**Re-anchored `b4f04e23` -> `fa63852d` on 2026-10-02 (L-0555 merges origin/main `dd95135a`, L-0578 #304, crew 1.0.119, at `fa63852d` with rerere disabled; crew 1.0.127).** The merge took main's anchor and INDEX rows and kept both lanes' re-anchor notes. L-0555's own change against main is `ci_receipt.py`, `test_ci_receipt.py`, `.github/workflows/verify-gate.yml`, `scripts/gate-runner.py`, one `.crew/verify.json` rule (line 454 edited in place, 455 appended), `plugin/crew/README.md` (+23 lines after `:2167`), `CHANGELOG.md` (+17 lines at the top) and the version and count lines. Citations moved by difflib: `CHANGELOG.md` +17 in `crew.md`'s current-citation lines, `plugin/crew/README.md` +23 past `:2167` in `repo-docs.md` (nine). No suite was executed for this note.


**Re-anchored `fa63852d` -> `f937576e` on 2026-10-02 (L-0555 merges origin/main `04dde5a2`, W-0120 #307, the claude- prefix renames, at `f937576e` with rerere disabled; crew 1.0.127).** Only `CHANGELOG.md` conflicted. Citations moved by difflib: this lane's `CHANGELOG.md` lines in `crew.md` +26 (W-0120's entry), `README.md:736` -> `:749` (three, in `repo-docs.md` and `install-scripts.md`) and `skills/README.md:15` -> `:28`. No suite was executed for this note.


**Re-anchored `f937576e` -> `af59b237` on 2026-10-02 (L-0555 merges origin/main `d2ec37d3`, W-0120 #308, README install URLs re-pinned to `04dde5a2`).** The merge changed `README.md:12` and `:18` in place; no line moved. The install-URL pin landmines in `install-scripts.md` and `repo-docs.md` now state the `04dde5a2` pin, and `git log --oneline 04dde5a2..af59b237 -- scripts/install-prerequisites.sh scripts/install-prerequisites.ps1` is empty. No suite was executed for this note.


**Re-anchored `af59b237` -> `7e18daf8` on 2026-10-02 (L-0555 merges origin/main `c7a9e649`: L-0572 #309 (subset coverage under --all, crew 1.0.126), runner auto-start #295, L-0593 #312/#313; rerere disabled; crew 1.0.127).** Conflicts: version files, CHANGELOG (both entries, L-0555's on top), BUDGETS count, `.crew/verify.json` (L-0555's rule then L-0572's), `crew.md`'s version sentence, generated rules. Main's notes for L-0572 came in unchanged. Every main-side citation into a file this branch changes resolves to the same line (difflib), except one historical `CHANGELOG.md:1372` in a past-tense note, left as written. No suite was executed for this note.


**Re-anchored `d6e51bb8` (main) and `7e18daf8` (L-0555) -> `5467b110` on 2026-10-02 (L-0555 merges origin/main `75681fba`: L-0577 #305, T-0107 #273 (gizmoduck 0.5.5); rerere disabled; crew 1.0.127).** The header conflict took main's anchor and both sides' provenance notes, main's first; the install-URL pin bullet took main's equivalent wording. Citations moved by difflib: this lane's `CHANGELOG.md` lines in `crew.md` +86 (the entries main added). Main-side citations into files this branch changes resolve to the same text. No suite was executed for this note.


**Re-anchored `5467b110` -> `2594c90f` on 2026-10-02 (L-0555 merges origin/main `a9b4734d`, L-0576 #306, crew 1.0.128; rerere disabled; crew 1.0.132).** No citation in this map moved.

**Re-anchored `2594c90f` (L-0555) and `273ec0f6` (main) -> `a81e4382` on 2026-10-02 (L-0555 merges origin/main `0487fc39`: L-0575 #311, crew 1.0.129, and L-0599 #315, gizmoduck 0.5.6; rerere disabled; crew 1.0.132 re-set after the merge).** The anchor, INDEX and provenance hunks conflicted: both sides' provenance was kept, main's first. Citation-number hunks took main's side. No citation in this map moved.

**Re-anchored `a81e4382` -> `407f2b33` on 2026-10-02 (L-0587, repository tooling, no plugin version).** `git diff --name-only a81e4382 407f2b33` is main's own history to e0c70fc9 plus L-0587's three commits. L-0587 changes `scripts/install-prerequisites.sh:1675` and `scripts/_test/lsp-stack-tools.sh:7` in place (comment text only, no line added or removed), `.crew/verify.json` rules[3] in place (one command appended on the existing last `run` line, its `why` extended; no line added), adds `scripts/_test/shellcheck-directives.py`, one `_py_suite` TABLE row in `scripts/gate-runner.py` (after `version-drift`, +1 line at `:155`), one step in `.github/workflows/marketplace.yml` (+8 lines after the Shell syntax step) and a CHANGELOG entry (+23 lines near the top). No current citation in this map points into `scripts/gate-runner.py` or `marketplace.yml` past the insertion; the `CHANGELOG.md` line numbers in this map sit in past provenance paragraphs that record the tree they were read at, and are left as written. No claim in this note was re-derived; no suite was executed for this note.

**Re-anchored `407f2b33` -> `4fc93b19` on 2026-10-03 (L-0587 merges origin/main `ffeb0e2f`: L-0598 #321, crew 1.0.135; rerere disabled).** Main's side changes `plugin/crew/hooks/scripts/crew_standards.py` (one hunk at `:729`, +4 lines, in `proposals`) and `plugin/crew/skills/crew-qa-standards/references/review.md` (one hunk at `:40`, +2 lines), plus version files, CHANGELOG, BUDGETS and `crew.md`'s version sentence, which came in unchanged. The only current citations into `crew_standards.py` in these maps are `:145` and `:664`, above the hunk, so they stand; the larger numbers that mention it sit in past provenance paragraphs and are left as written. Only the generated `.claude/rules/crew.md` conflicted and was regenerated. No claim was re-derived; no suite was executed for this note.

**Re-anchored `a81e4382` -> `6475c41c` on 2026-10-02 (L-0592, L-0575's round-2 fixes to the recurring-findings checklist; origin/main `ffeb0e2f` merged first as a fast-forward, rerere disabled).** `git diff --name-only a81e4382 6475c41c` against this map's paths returns five files under the crew plugin: its README, the implement command, recurring_findings.py and two test modules (test_lifecycle_commands.py, test_recurring_findings.py). The README changes one line in place (727) and implement.md re-wraps step 2 in its same five lines (40-44), so no line moves; paths are named here without citation markup so this note does not shift the map's derived rule paths; no citation in this map points at a changed line or at recurring_findings.py or either test. No claim changed.

**Re-anchored `6475c41c` -> `35b9e6d9` on 2026-10-02 (L-0592 review round 1 fixes).** Of this map's paths only the test module test_recurring_findings.py changed (its render table made exhaustive); this map cites no line of it. No claim changed.

**Re-anchored `4fc93b19` (main, L-0587) and `35b9e6d9` (L-0592) -> `39ebbc18` on 2026-10-02 (L-0592 merges origin/main 6ac3b1b3, L-0587 #319 and #322; rerere disabled; crew 1.0.139).** Main's maps, INDEX and diagram were taken and L-0592's notes re-applied after main's. Since main's anchor, L-0592 changed five files under the crew plugin (README, the implement command, recurring_findings.py, two test modules) with no line moved, and main's re-pin changed two root README lines in place. No citation moved; no claim changed.

**Re-anchored `6053b65d` -> `17dc6d23` on 2026-10-01 (L-0574, built on origin/main `ffd11270`: `review_checks.py` and `review_run.py`'s `prereview_gate`, no plugin version yet).** Every citation into a file L-0574 changed (`review_run.py`, `commands/review.md`, `plugin/crew/README.md`, `.crew/verify.json` - which gained a top-level `preReview` block above `rules`, so every rule citation moved by 27 lines - `docs/external-tool-formats.md`, `tests/sabotage.py`, `tests/test_review_contracts.py`, `BUDGETS.md`, `CHANGELOG.md`, the lifecycle diagram) was mapped with difflib from `ffd11270` to `17dc6d23`; `BUDGETS.md:10-11` is the changed count line itself and keeps its number. The verify map still has 44 rules; `preReview` is read by `review_run.py`, not the Stop gate.

**Re-anchored `17dc6d23` -> `8177fdff` on 2026-10-01 (L-0574 review round 1 and pre-round fixes).** The commits since changed `review_checks.py`, its tests, `sabotage_prereview.py`, `docs/external-tool-formats.md`, `BUDGETS.md`'s count line and `CHANGELOG.md`; difflib found no citation in this map that moved.

**Re-anchored `8177fdff` -> `3afec6e6` on 2026-10-01 (L-0574: noqa BLE001 on two boundary catches, same lines; difflib moved no citation).**

**Re-anchored `3afec6e6` -> `d640eba3` on 2026-10-01 (L-0574 round-2 fixes and the crew 1.0.122 bump; ten CHANGELOG citations moved +2 by difflib, the crew map's version sentence now reads 1.0.122).**

**Re-anchored `d640eba3` -> `d41c2c94` on 2026-10-01 (L-0574: a sabotage anchor re-targeted and the graph rebuilt; no cited line moved).**

**Re-anchored `d41c2c94` -> `1f5400df` on 2026-10-01 (L-0574 round-3 fixes; ten CHANGELOG citations moved +6 by difflib).**

**Re-anchored `1f5400df` -> `5143dbcd` on 2026-10-02 (L-0574 round-4 fixes and the merge of origin/main d2ec37d3: this branch's map text kept, main's re-anchor notes restored, citations into the eight files round 4 changed re-mapped by difflib from 1f5400df and the rest from 846cc465 onto the merge).**

**Re-anchored `5143dbcd` -> `ded603a7` on 2026-10-02 (L-0574: the gate's pylint findings fixed; no cited line moved).**

**Re-anchored `ded603a7` -> `a4ffe1de` on 2026-10-02 (L-0574 merges origin/main 7ba4f9ea, crew 1.0.126: citations into files main changed re-mapped by difflib, two verify.json:418 read by hand as :439).**

**Re-anchored `a4ffe1de` -> `18b764dc` on 2026-10-02 (L-0574: merge of origin/main 22292d63 (rerere disabled, scope re-based to it) and the round-5 fixes; ten CHANGELOG citations moved by difflib).**

**Re-anchored `18b764dc` -> `22aeb5a8` on 2026-10-02 (L-0574 round-7 class sweep: fifteen citations moved by difflib (review_run.py, CHANGELOG.md), two bare review_run.py citations re-read by hand).**

**Re-anchored `22aeb5a8` -> `9581933e` on 2026-10-02 (L-0574: external-tool-formats.md citation fix and the crew 1.0.131 re-set; no cited line moved).**

**Re-anchored `9581933e` -> `34c9a8bc` on 2026-10-02 (L-0574 merges origin/main 0487fc39 at bd459af7 (rerere disabled; both provenance histories kept, main's first) and fixes review round 7 at 4a35e5d2; citations re-mapped by difflib, bare review_run.py citations re-read by hand).**

**Re-anchored `34c9a8bc` -> `370a7a5b` on 2026-10-02 (L-0574 merges origin/main e0c70fc9 (L-0555 #310, #317, L-0597 #316; crew 1.0.134) at 370a7a5b, rerere disabled: both provenance histories kept (main's first), citations into files either side changed re-mapped by difflib (67 moved), the verify.json heading corrected to 48 rules).**

**Re-anchored `370a7a5b` -> `e2c11c0b` on 2026-10-02 (L-0574 review round 8 fixes at 0f5d76e7 (review_checks.py, review_run.py, CHANGELOG, external-tool-formats.md; install-scripts.md gains an explicit paths: line); citations re-mapped by difflib, bare review_run.py citations re-read).**

**Re-anchored `e2c11c0b` -> `0891d6a6` on 2026-10-02 (L-0574 merges origin/main ffeb0e2f (L-0598 #321, crew 1.0.135; crew_standards.py proposals and references/review.md, which this map cites by name only) at 26d2c1c0, rerere disabled, then fixes review round 9 at c7e4c87f; citations re-mapped by difflib).**

**Re-anchored `0891d6a6` -> `4dcad808` on 2026-10-02 (L-0574 merges origin/main 6ac3b1b3 (L-0587 #319 ShellCheck directive fixes, README re-pin #322; crew 1.0.135) at 4dcad808, rerere disabled: both provenance histories kept (main's first), citations re-mapped by difflib).**

**Re-anchored `4dcad808` -> `819a2d2b` on 2026-10-02 (L-0574: three test_review_checks.py cases made to pass on a real Windows host (PR #323 CI); citations re-mapped by difflib).**

**Re-anchored `819a2d2b` -> `d95d8b25` on 2026-10-02 (L-0574 merges origin/main 2a2d6e07 (L-0592 #325, crew 1.0.139: recurring_findings.py, implement.md step 2 re-wrapped in place, README) at d95d8b25, rerere disabled: both provenance histories kept (main's first), citations re-mapped by difflib; crew is set to 1.0.140).**

**Re-anchored `0c3508e9` -> `963d2905` on 2026-09-30 (L-0510: review closure, a final 0-BLOCK round auto-accepts, crew 1.0.90).** `git diff --name-only 0c3508e9 963d2905` returns, outside refresh artifacts, main's L-0561 README repin and L-0510's files (review_ledger.py, review_run.py, crew_autopilot.py, review.md, done.md, autopilot.md, README.md, CONFIG.md, BUDGETS.md, PLUGINS.md, the troubleshooting guide, CHANGELOG.md, two tests, sabotage_review.py and the version files); path-qualified citations outside dated provenance checked by a line diff: no body citation moved: provenance paragraphs keep their dated numbers, and the only cited lines that changed are version lines (plugin.json, PLUGINS.md, BUDGETS.md), unchanged in place. No suite was executed for this note.

**Re-anchored `963d2905` -> `bee8b203` on 2026-09-30 (L-0510 suite fixes, crew re-bumped to 1.0.93).** `git diff --name-only 963d2905 bee8b203` returns, outside refresh artifacts, `sabotage_review.py` (one row's find string), `plugin/crew/docs/external-tool-formats.md` (four `review_run.py` citations), CHANGELOG.md and the version files; a body-only line diff moved no citation here (`docs/diagrams/data-flow-crew-config.mmd:1-2` is its re-written header, still lines 1-2). No suite was executed for this note.

**Re-anchored `bee8b203` -> `52e309cf` on 2026-10-01 (L-0510 review fix round, crew re-bumped to 1.0.94).** `git diff --name-only bee8b203 52e309cf` returns, outside refresh artifacts, `review_ledger.py` (the per-severity count check, the CLEAN receipt-kind check and `check_follow_up`'s kind allowlist, UTF-8 refusal and verbatim counted match), its tests and sabotage rows, `plugin/crew/README.md`, `plugin/crew/commands/done.md`, `plugin/crew/commands/review.md`, `plugin/crew/BUDGETS.md`, the troubleshooting guide and its rendered outputs, CHANGELOG.md and the version files. A body-only line diff moved no citation here. No suite was executed for this note.

**Merged `490f4ec1` (L-0510) + `52489039` (main) on L-0510-build, 2026-10-01 (merge `58fc8da8` of origin/main `52489039`: T-0040 #290, crew 1.0.98, with rerere off), then re-anchored to `5254bbfe` (L-0510 re-bumped to crew 1.0.103).** The code paths are disjoint: main touched none of `review_ledger.py`, `review_run.py`, `crew_autopilot.py`, `commands/review.md` or `commands/autopilot.md`, and L-0510 touched none of T-0040's files. The anchor and the provenance tail conflicted in every map (both sides' provenance kept, main's first); `crew.md`'s T-0087 refund paragraph keeps L-0510's `review_run.py` / `review_ledger.py` / `crew_autopilot.py` positions with main's `plugin/crew/hooks/scripts/crew_status.py:140`, and `repo-docs.md`'s runbooks-index citation was re-grepped on the merged tree (`plugin/crew/README.md:2287`). Every body `path:line` into a file either side changed was checked against the parent whose copy of the map carries that line verbatim, by a line diff of that file onto the merged tree (`/root/crew-tmp/l-0510/tools/merge_cites2.py`, machine-local): none moved. `5254bbfe` itself changes only release bookkeeping (version files, CHANGELOG, BUDGETS count). No suite was executed for this note.

**Re-anchored `5254bbfe` -> `a98be035` on 2026-10-01 (L-0510, owner decision 2026-10-01 #3: the family rule).** `git diff --name-only 5254bbfe a98be035` returns `review_ledger.py`, its two test files and `sabotage_review.py`, `commands/review.md`, README, CONFIG, PLUGINS.md, BUDGETS.md, CHANGELOG, the troubleshooting guide and its three outputs, and refresh artifacts. Line counts are unchanged in every file except `review_ledger.py` (+37, cited only in `crew.md`, re-read there), CONFIG.md (+1 at `:2510`, past every CONFIG citation in these maps) and CHANGELOG.md (+3 at `:21`; the CHANGELOG line numbers in these maps are history notes of earlier anchors, not re-cited).

**Merged `a98be035`/`8c82f974` (L-0510) + `5ffffbe3` (main) on L-0510-build, 2026-10-01 (merge `d4193b70` of origin/main `2906dcbd`, crew 1.0.110, rerere off), then re-anchored to `8f0df4ca` (L-0510 re-bumped to crew 1.0.112).** Both provenance blocks are kept above, main's first. Main touched none of `review_ledger.py`, `review_run.py`, `crew_autopilot.py`, `commands/review.md` or `commands/autopilot.md`, so every L-0510 citation reads as L-0510 drew it, except `review_ledger.py`, which L-0510's review round 3 FIX 2 (`8c82f974`: `_receipt_names_the_reviewer`) grew by 10 lines below `:590`; `crew.md`'s citations of it were re-read with `grep -n '^def '` on the merged tree and moved (`check_receipt` `:691`, `check_follow_up` `:620`, `continue_with_successor_plan` `:742`, `summary` `:781`). Main's citations are main's, unchanged by L-0510's side.

**Re-anchored `8f0df4ca` -> `39e1237a` on 2026-10-02 (L-0510 review round 4 fixes, owner decision 2026-10-01 #5).** `3181121c` changed `review_ledger.py` (`_auto_row_problem` +6 lines: the embedded line-break refusal; `check_follow_up` +3: newline-only split), `commands/autopilot.md` (one sentence extended in place, line count unchanged) and the L-0510 tests; `00450ce0` CHANGELOG and README text; `fb33f9dc`/`39e1237a` un-set and re-set crew 1.0.112. `crew.md`'s `review_ledger.py` citations were re-read with `grep -n '^def '` and moved (`receipt_stands` `:596`, `check_receipt` `:700`, `_receipt_names_the_reviewer` `:618`, `auto_accept_refusal` `:528`, `auto_accept` `:562`, `check_follow_up` `:626`, `continue_with_successor_plan` `:751`, `summary` `:790`, `load` `:787`). No other note cites a moved line.

**Merged `39e1237a`/`ecc76d10` (L-0510) + `6053b65d` (main, L-0557 #300) on L-0510-build, 2026-10-02 (merge `122fc10d` of origin/main `ffd11270`, crew 1.0.114, rerere off), then re-anchored to `6ffb589d` (L-0510 at crew 1.0.121).** Both provenance blocks are kept above, main's first. L-0557 touched none of `review_ledger.py`, `review_run.py`, `crew_autopilot.py`, `commands/review.md` or `commands/autopilot.md`. L-0510's own changes since `39e1237a`: `156882d2` (decision #6: `_auto_row_problem` +12 lines, `_review_json_problem` new at `:578`, `auto_accept` +3) and `ecc76d10`/`7d32fbc6` (docs and the rebuilt troubleshooting guide); `crew.md`'s `review_ledger.py` citations were re-read with `grep -n '^def '` and moved (`receipt_stands` `:641`, `check_receipt` `:745`, `auto_accept` `:604`, `check_follow_up` `:671`, `continue_with_successor_plan` `:796`, `summary` `:835`). Main's citations are main's.

**Merged `979ea023` (L-0510) + `8d84786d` (main: T-0503 #270 bitbucket 1.2.3, W-0117 #302 crew 1.0.115) on L-0510-build, 2026-10-02 (merge `9f39dd61`, rerere off, owner decision #9), anchored at `9f39dd61`.** Both provenance blocks are kept above, main's first. Neither T-0503 nor W-0117 touched `review_ledger.py`, `review_run.py`, `crew_autopilot.py`, `commands/review.md` or `commands/autopilot.md`, so L-0510's citations read as L-0510 drew them at `e7227a2b` (`receipt_stands` `:644`, `check_receipt` `:748`, `auto_accept` `:607`, `_review_json_problem` `:578`, `check_follow_up` `:674`, `summary` `:838`). Main's citations are main's.

**Merged L-0510 (`553f4aa0`, the UTF-8 console fix) + `04dde5a2` (main: L-0578 #304 crew 1.0.119, W-0120 #307) on L-0510-build, 2026-10-02 (merge `41aa4e2a`, rerere off, standing go #9), anchored at `2b372b84`.** Both provenance blocks are kept above, main's first. L-0578 changed `review_run.py` (the metrics row) and `commands/review.md` step 6; every `review_run.py` citation in this note was re-derived on the merged file by difflib from each parent and read with `sed -n` (preflight `:555`, called at `:642`; `--provider` `:739`; `finish`'s parts `:438`/`:440`; `failure_class` `:458`; refund lines `:508`/`:511`; `_webtest_open` `:412`; `auto_accept_line` `:421`). `review_ledger.py` gained `utf8_stdio` after `summary` (`:838`), so no earlier citation moved.

**Re-anchored `2b372b84` -> `252dd5d4` on 2026-10-02 (L-0510 review round 6 fixes, owner decision #10; merge `24f3ec25` of origin/main `d2ec37d3`, README only).** `d551680c` changed `review_ledger.py` (`read_review_json` `:599` and `_receipt_binds_review_json` `:721` new, `receipt_stands` gained `root, ticket`, `hashlib` imported, docstring +5), `crew_autopilot.py` (one line edited in place), `commands/review.md` (step 3 quoted in place), the L-0510 tests, CHANGELOG and README. `crew.md`'s `review_ledger.py` citations were re-read with `grep -n` by name (`receipt_stands` `:695`, `check_receipt` `:819`, `auto_accept` `:655`, `check_follow_up` `:742`, `summary` `:909`, `BUDGET` `:132`, `REFUND_LIMIT` `:135`). No other note cites a moved line.

**Re-anchored `252dd5d4` -> `97b65952` on 2026-10-02 (L-0510, merge `48cf52dd` of origin/main `7ba4f9ea`, crew 1.0.126 -> 1.0.130).** Main brought L-0572's `verify-gate.sh`/`.ps1`, `verify_record.py`, CONFIG.md and its own codemap edits; it touched none of the files L-0510's citations name (`review_ledger.py`, `crew_autopilot.py`, `review_run.py`, `commands/review.md`, `commands/autopilot.md`), so no L-0510 citation moved; L-0572's citations were written against main and carried by the merge unchanged.

**Re-anchored `273ec0f6` (main) and L-0510's `97b65952` -> `d05b0211` on 2026-10-02 (L-0510 merges origin/main `0487fc39` (L-0599 #315, crew 1.0.129; L-0576, L-0577, T-0107, L-0575 before it) at `ec508e5e`, rerere off; crew 1.0.130 set last at `d05b0211`).** Both provenance histories kept, main's first. In `crew.md` the `review_ledger.py`, `review_run.py` and `review_verdict.py` citations were re-derived on the merged files by function name (`grep -n '^def '`) and difflib from the tree each line came from: L-0510's ledger lines moved +14 (L-0576's `_ignored_count` and `record` row above them), `review_run.py`'s preflight `:563`/`:650`, provider list `:747` and refund lines `:517`/`:520`, `review_verdict.py`'s `VERDICTS`/`FINDING_FORM`/class names `:90`/`:93`/`:95`; main's L-0576 paragraph's three stale lines set to `review_run.py:447`, `:467`, `:513` and `review_ledger.py:394`. One L-0510 sentence that said the field was not written now says L-0576 writes it. Other maps: no cited line moved. History notes were not re-mapped.

**Re-anchored `a81e4382` (main) and L-0510's `d05b0211` -> `77e8dcfd` on 2026-10-02 (L-0510 merges origin/main `e0c70fc9` (#317, L-0597 #316, L-0555 #310; crew 1.0.134) at `e6dc6b1b`, rerere off; crew 1.0.137 set last at `77e8dcfd`).** Both provenance histories kept, main's first. Main touched none of `review_ledger.py`, `review_run.py`, `review_verdict.py`, `crew_autopilot.py`, `review.md` or `autopilot.md`; `crew.md`'s `crew_autopilot.py` `questions_check` `:1246` / `QUESTIONS_SHAPE` `:1154` are L-0510's merged-file lines (main's side read `:1232` / `:1140` without L-0510's autopilot change); `repo-docs.md`'s README citation is `:2314` on the merged README (L-0555 +23). History notes were not re-mapped.

**Re-anchored `4fc93b19` (main) and L-0510's `77e8dcfd` -> `96a69068` on 2026-10-03 (L-0510 merges origin/main `bd3e9ad1` (L-0598 #321, L-0587 #319; crew 1.0.135) at `d3f26a4b`, rerere off; crew 1.0.137 set last at `96a69068`).** Both provenance histories kept, main's first. Main touched no file L-0510's citations name; L-0510's `c86365ee` (a test helper) moves no cited line. History notes were not re-mapped.

**Re-anchored `39ebbc18` (main) and L-0510's `96a69068` -> `a06dd790` on 2026-10-03 (L-0510 merges origin/main `2a2d6e07` (L-0592 #325, L-0587 re-pin #322; crew 1.0.139) at `39c290be`, rerere off; crew 1.0.142 set last at `a06dd790`).** Both provenance histories kept, main's first. Main touched no file L-0510's citations name (its README edit is one line, no cited line moved). History notes were not re-mapped.

**Re-anchored `d95d8b25` (main) and L-0510's `a06dd790` -> `b8d09685` on 2026-10-03 (L-0510 merges origin/main `8123fe74` (L-0574 #323; crew 1.0.140) at `8c04c783`, rerere off; crew 1.0.142 set last at `b8d09685`).** Both provenance histories kept, main's first. In `crew.md` main's L-0574 `review_run.py` citations were re-derived on the merged file (L-0510 adds 8 lines above `finish` and 28 through it): by difflib, and by name for `prereview_gate` `:731` (called `:857`), `standards_gate` `:699` (at `:859`) and `review_ledger.reserve` `:863`, which main's side had stale; L-0510's `review_ledger.py` citations are unchanged. `verification-harness.md`'s `sabotage.py` citations moved +1 (main's import at `:87`; main's side had them stale). History notes were not re-mapped.

**Re-anchored `b8d09685` -> `452b30cc` on 2026-10-03.** `204e813b` routes `review_run.finish`'s auto-accept line through `_out` (main's L-0574 one-writer test), one line, no line count change, so no citation moved; `452b30cc` re-sets crew 1.0.142 last.

**Re-anchored `452b30cc` -> `586cabe0` on 2026-10-03 (T-0046 merges origin/main `3a064f4f`, L-0510 #318, at `9e6d8b0f`, rerere disabled; crew 1.0.147 re-set at `586cabe0`).** Main's maps were taken in the merge. T-0046 is split under the tooling-PR rule: its change is the new BUDGETS.md claim-number predicate module under the crew hooks and its test, one verify-map rule appended at the end, the version files and CHANGELOG; the hook consumers move to L-0610. No body citation in this map points at a line that moved.

**Re-anchored `586cabe0` -> `aab858e9` on 2026-10-03 (T-0046 merges origin/main `f808e5f0` - #328, #329, #330, crew 1.0.154 - at `cbe74d03`, rerere disabled; crew 1.0.158 set last at `aab858e9`).** Main's three PRs changed crew_config.py, verify-gate.sh/.ps1, verify_record.py, review_run.py, crew_train.py, done.md, review.md, CONFIG.md, README.md and .crew/verify.json without moving these maps. Every body citation to a file changed since `586cabe0` was re-mapped by a line diff (difflib, equal blocks only) and rewritten where it moved; a citation whose own line changed was re-read by hand. `.crew/verify.json` rules 1-48 keep their line ranges (main edited their content in place: `seconds`, `coveredBy`, `why`), so rule citations stand; the prose describing those rules' prices and coverage was not re-verified against main's edits. No body citation in this map points at a line that moved.
