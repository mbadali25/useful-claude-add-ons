# mcp-servers
anchor: useful-claude-add-ons@e8482046
verified: 2026-09-30
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
  `1f97e51c`; still open as `TODO.md:189` (item 2; was `:110` at `f2bb919b`, `:80` at `6c497a14` and `:51` before that, each
  move an insertion earlier in the file - re-read at `f2bb919b` on 2026-09-25, same heading and body).
- **`scopesOverride` silently broadens a narrow scope request.**
  `mcp-servers/packages/core/src/adminAuth.ts:29-36` (the field and its doc comment), `:127`
  (`secret`) and `:144` (`cli`) force `.default` regardless of what the caller asked for. Only
  `device` (`mcp-servers/packages/core/src/adminAuth.ts:149-158` - no `scopesOverride` key, and the
  comment at `:155-158` says why) honours caller-supplied delegated scopes. Code that requests a
  narrow scope and receives `.default` did not fail - it was never asked. Re-verified unchanged
  2026-09-06 at `1f97e51c`; still open as `TODO.md:200` (item 3; was `:121` at `f2bb919b`, `:91`, and `:62` before that - re-read at
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
    `TODO.md:281-288` (was `:202-209` at `f2bb919b`, `:172-179`, and `:143-150` before that; re-read at `f2bb919b` on 2026-09-25, same reasoning)
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

**Re-anchored `b2553d26` -> `8a084c6c` on 2026-09-28 (T-0085 merges main `6387ab49`, T-0089, T-0090, T-0092; crew 1.0.55).** `f97219dc` merged origin/main `6387ab49` into `T-0085-build` (mechanical conflicts only: crew version lines, CHANGELOG, anchors, provenance paragraphs, INDEX history cells, diagram headers, generated rules and graph); `8a084c6c` re-bumps crew to 1.0.55, one past main's 1.0.54. Each side had already re-verified its own changes (main's line to `136f4b33`/`2442d367`/`b2553d26`, T-0085's to `b82035e6`), so this pass checks the files BOTH sides changed: the crew version lines (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`, value only, same line), `CHANGELOG.md` (both sections kept; release bookkeeping), `plugin/crew/README.md` and `plugin/crew/commands/review.md` (main's T-0092 edits are in place and line-neutral: 2883 and 551 lines, as on T-0085's side), `plugin/crew/hooks/scripts/review_prompt.py` (main's docstring line split in two at `:6-7` and three `excluded` lines added at `:96-98` shift T-0085's lines below them by 4) and `plugin/crew/tests/test_review_prompt.py`. Every `path:N` citation into those files was compared by script against its text on the side that wrote it (`f3ad630b` or `6387ab49`) and at the merged tree; this note cites the root `README.md` only as `mcp-servers/`'s own README by bare name, and the root file's one change is T-0085's crew skill count (29 -> 30), which no claim here reads. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `8a084c6c` -> `07bcaf3b` on 2026-09-28 (T-0085 review round 1 fixes).** `07bcaf3b` changes `plugin/crew/hooks/scripts/crew_standards.py` (`gate_applies`, `checklist_block`, `stamp`, `_plugin_sets`, the module docstring), its tests and sabotage entries, `.crew/standards.md` (REPO-03's rule text), `.crew/verify.json` (rule 31 gains two test files; its `seconds` and `why`), `CHANGELOG.md` (T-0085's bump bullet, two lines to three), `plugin/crew/BUDGETS.md:10-11` (the count, in place), `plugin/crew/README.md` (three table rows, in place), `plugin/crew/commands/implement.md` (two lines reflowed in place; still 120 lines), `plugin/crew/commands/review.md` (step 6's reviewer-cell line becomes three, so lines below `:531` move by 2), `plugin/crew/skills/crew-standards/SKILL.md`, ADR 0004 and the working-with-codex guide. Every `path:N` citation in this note into those files was compared by script between `8a084c6c` and `07bcaf3b`: no citation into those files moved; the note cites `plugin/crew/README.md` and `review.md` by name only. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `07bcaf3b` -> `8abf7ffe` on 2026-09-28 (T-0085 provisional re-bump, crew 1.0.56).** `8abf7ffe` moves crew's version 1.0.55 -> 1.0.56 in place (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), because the round-1 fixes changed `plugin/crew/` after 1.0.55 was set and `scripts/check-marketplace.py`'s version-drift check failed on it; it also rewords `.crew/standards.md` REPO-03 (the provisional bump) and T-0085's `CHANGELOG.md` heading and bump bullet (three lines to four). Every `path:N` citation in this note into those files was compared by script between `07bcaf3b` and `8abf7ffe`: the version-file citations hold (value changed in place, same line) and every hit sits inside an earlier dated provenance paragraph, left as history; no body claim states the version. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `3648f59a` / `8abf7ffe` -> `e3f5fa49` on 2026-09-29 (T-0085 merges main `2693d0fa`, T-0075 landed as crew 1.0.59, and applies the owner-accepted round-1 standards amendments).** `0fd1bdf8` reverts T-0085's provisional crew 1.0.56 bump (`8abf7ffe`); `0fd92334` merges origin/main `2693d0fa` into `T-0085-build` (mechanical conflicts only: crew version lines take main's 1.0.59, crew counts take main's 36 commands with T-0085's 30 skills, `plugin/crew/tests/sabotage.py` registers both `CONFIG_MENU_MUTATIONS` and `STANDARDS_MUTATIONS`, anchors, provenance paragraphs, INDEX history cells, diagram notes, generated rules and graph); `e3f5fa49` amends GEN-01 and GEN-04 in `plugin/crew/skills/crew-standards/references/generic.md` and REPO-03 in `.crew/standards.md`, drops the version from T-0085's `CHANGELOG.md` heading and re-measures `plugin/crew/BUDGETS.md`. The build branch now declares main's 1.0.59 and carries no bump of its own (REPO-03 as amended). Every `path:N` citation outside provenance was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from the side that wrote it - `3648f59a` for a line in main's copy of this note, `0fd1bdf8` for a line only in T-0085's - to `e3f5fa49`, and every line that did not map to itself was read with `sed -n` / `grep -n`; the script attributes some bare `:N` to the wrong file, and those were read and hold. None moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `e3f5fa49` -> `001f8a78` on 2026-09-29 (T-0085 successor plan, review round 2's fixes).** `bc3602df`..`001f8a78` change `plugin/crew/hooks/scripts/crew_standards.py` (`_scope` gains the merge-base fallback for a kept but unusable scope record, `_has_scope_entry` and `_noted` are new, so every definition from `_scope` down moves by +8 to +30 lines), its tests (`test_crew_standards.py`, `test_review_run_standards.py`, `test_lifecycle_commands.py`) and `plugin/crew/tests/sabotage_standards.py` (nineteen new entries; `STANDARDS_MUTATIONS` moves `:21` -> `:35`), `plugin/crew/skills/crew-standards/SKILL.md` (step 3, +5 lines), `plugin/crew/README.md` (one table row, in place), `CHANGELOG.md` (one bullet in T-0085's section, so every line below it moves +8) and `plugin/crew/BUDGETS.md:11` (the count, in place). Every `path:N` citation in this note into those files was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from `e3f5fa49` to `001f8a78`; none moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `001f8a78` -> `a7f9c5e4` on 2026-09-29 (T-0085 merges main `8ab733d7`, T-0010 landed as crew 1.0.61, after review round 3's fixes `33521aa4`).** Nothing under `mcp-servers/` changed (`git diff --name-only 001f8a78 a7f9c5e4 -- mcp-servers` is empty); the paths the refresh check named are cited only inside earlier provenance paragraphs. No body citation moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `a7f9c5e4` / `b4f39fd3` -> `69c7edbd` on 2026-09-30 (T-0085's landing merge of main `a61a6f38`, crew 1.0.70).** `69c7edbd` merges T-0085's build head `0c6f01e0` (round 4, owner-accepted) onto origin/main `a61a6f38` (crew 1.0.69: #263-#267 and T-0088) on `T-0085-land`, and sets crew 1.0.70. Every body `path:N` citation was mapped by script (`difflib` equal blocks, from the anchor of whichever side's copy of this note carries the line - `a7f9c5e4` for T-0085's, main's own anchor for main's - to `69c7edbd`); each that mapped to one new line was moved, and each that did not map, or mapped differently from the two sides, was read with `sed -n` / `grep -n`. The script attributes a bare `:N` to the last path cited with a line number, so a bare `:N` after a path named without one (`.crew/verify.json` rule ranges, `crew_tfplan.py`, `sabotage_autopilot.py`, `crew_ticket.py`, `crew_standards.py`) was read against its real file and put back where the script moved it wrongly; `.crew/verify.json` lines up to `:340` did not move, and T-0085's rule is now `:361-373`, the last. A bare `review.md` citation is ambiguous since #267 added `crew-qa-standards/references/review.md`, so the script skipped those; `plugin/crew/commands/review.md` moved only below `:544` (+1, +3), and its cited lines above that were re-read. No citation in this note moved; nothing under `mcp-servers/` changed. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `69c7edbd` -> `7c86bd13` on 2026-09-30 (T-0085 landing: one sabotage anchor re-taken).** `git diff --name-only 69c7edbd 7c86bd13`, refresh artifacts aside, returns only `plugin/crew/tests/sabotage_standards.py`: the find and replace text of "review.md loses the self-check refusal" now end at `rebuild.` / `provider.`, because the merge joined main's exit-5 sentence onto that line. No line was added or removed; no citation moved. No suite was executed for this note.

**Re-anchored `7c86bd13` (`obsidian-vault`: `69c7edbd`) -> `c04dd2ef` on 2026-09-30 (T-0085 landing: `commands/review.md` rewrapped to its 551-line allowance, crew 1.0.71 then 1.0.72).** `git diff --name-only 7c86bd13 c04dd2ef`, refresh artifacts aside, returns the crew version files, `CHANGELOG.md`, `plugin/crew/BUDGETS.md` (20,707 lines, in place) and `plugin/crew/commands/review.md`: step 3's item 3 gains its last line on `:512`, item 4 and its `gh pr comment` paragraph and steps 8-9 are rewrapped at 100 columns, and the closing sentence is joined, taking the file from 557 to 551 lines with no text changed. Every line this note cites in `review.md` is at or above `:512` and holds; the version this note states now reads 1.0.72. No suite was executed for this note.

**Re-anchored `c04dd2ef` -> `8a89a596` on 2026-09-30 (T-0085 landing: catch-up merge of main `6813749b`, #268 T-0097, crew 1.0.70; T-0085 now 1.0.73).** `git diff --name-only 54192270 8a89a596` returns the crew version files, `CHANGELOG.md` (T-0097's entry below T-0085's), the 11 `.ps1` hook carriers (one `Resolve-CrewPython` line each: an empty probe answer is no longer piped into `ConvertFrom-Json`), `plugin/crew/tests/sabotage_scope.py` and `plugin/crew/tests/test_ps1_python_probe.py`. Citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 11 moved, 0 unmapped); version-line citations (`marketplace.json:218`, `plugin.json:3`, `PLUGINS.md:14`) hold by line and now read 1.0.73. The `Resolve-CrewPython` copies stay byte-identical across all 11 carriers, so the copy-list claims hold. No suite was executed for this note.

**Re-anchored `8a89a596` -> `9b6b0da7` on 2026-09-30 (T-0085 landing: Windows fail-open fix, crew 1.0.74).** `git diff --name-only 58431f49 9b6b0da7` returns the crew version files, `CHANGELOG.md`, `plugin/crew/hooks/scripts/crew_standards.py` (`import stat`, new `_ancestor_problem` before `gate_applies`, which now proves a receipt absent only when the nearest existing ancestor is a directory), `plugin/crew/tests/test_crew_standards.py` (new `test_gate_applies_when_a_file_parent_is_reported_as_not_found`) and `plugin/crew/tests/sabotage_standards.py` (one entry). Path-qualified citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 10 moved, 0 unmapped); `crew.md`'s bare `crew_standards.py` citations in its standards section were moved by the same diff (27). No suite was executed for this note.

**Re-anchored `9b6b0da7` -> `5c9a9db2` on 2026-09-30 (T-0085 landing: sabotage entry re-targeted, crew 1.0.75).** `git diff --name-only 33da9c91 5c9a9db2` returns the crew version files, `CHANGELOG.md` and `plugin/crew/tests/sabotage_standards.py` (the "receipt that cannot be looked up" entry now flips `gate_applies`' `OSError` verdict). Path-qualified citations into those files were moved by a line diff (`/root/crew-tmp/t-0085/remap_merge.py`, 9 moved, 0 unmapped). No suite was executed for this note.


## Re-anchor provenance - `2f7899a0` + `a61a6f38` -> `bd68ce88`, 2026-09-30 (T-0028 merges main `a61a6f38`, successor adaptations, crew 1.0.70)

`27e321aa` merges origin/main `a61a6f38` (crew 1.0.69: T-0088's Codex-limit fallback and
`crew_common.repo_config_dir` lane-config resolver, #263-#267's QA harness, `review_gate.py`
preflight and `crew-qa-standards`) into `T-0028-kimi` at `2f7899a0`, with the 12-file textual
resolution saved at `9a3ad3de` re-read hunk by hunk; `EXIT_PROBE_CHANGED` moves 5 -> 8.
`cba50c93` adds the owner's five successor adaptations (probe before the gate preflight,
`--allow-unverified` in two fingerprint tests, `graph_out` through `repo_config_dir`, the
`test_worktree_config.py` ALLOWED entry, crew-providers SKILL.md at 499 lines) and `bd68ce88`
re-sets crew 1.0.70, the last `plugin/crew/` commit. Every body citation into a file changed
between `2f7899a0` and `bd68ce88` was mapped by a `difflib` line diff
(`/root/crew-tmp/t-0028/refresh/reanchor.py`, machine-local); a bare `:N` goes to the last path
named before it in its paragraph. Provenance sections and history citations (followed by `at`,
`on`, `since`, `before`, `was` or `->`) were left as written. A cited line whose text changed
was re-read and its claim corrected; no cited line in this note changed text.
Re-anchor only (owner refresh-artifact standing rule, 2026-09-28); no test suite was executed for this note.

## Re-anchor provenance - `9831ba47` + `9af34e57` -> `e8482046`, 2026-09-30 (T-0028 merges main `301e478a` and `9af34e57`, crew 1.0.76)

`7939cc46` merges origin/main `301e478a` (crew 1.0.75: T-0085's standards self-check #269, T-0097
#268, #276, #277) into `T-0028-kimi` at `9831ba47`, and `a88111e2` merges `9af34e57` (#279, CI
triggers; crew stays 1.0.75); both mechanical. `e8482046` re-sets crew 1.0.76, the last
`plugin/crew/` commit (the approved plan's Step 7; `.crew/standards.md` REPO-03, landed with
T-0085, would leave the build branch at main's version - noted for the owner, not decided here).
In this note's conflicting hunks, a side that changed only numbers yielded to the other, appended
provenance keeps main's then T-0028's, and the rest took main's text. Every body citation into a
file changed since was then mapped by a `difflib` line diff from the side whose copy of this note
holds that exact line (`9831ba47` for T-0028's, `9af34e57` for main's; both when both hold it, and
a disagreement is re-read), with `/root/crew-tmp/t-0028/refresh/reanchor2.py` (machine-local); a
bare `:N` goes to the last path named before it. Provenance and history citations were left as
written. A cited line whose text changed was re-read and its claim corrected; no cited line in this note changed text beyond that.
Re-anchor only (owner refresh-artifact standing rule, 2026-09-28); no test suite was executed for this note.
