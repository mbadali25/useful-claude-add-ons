# mcp-servers
anchor: useful-claude-add-ons@5d1fc5fd
verified: 2026-09-22

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
- Azure identity providers through **two** separate paths: the admin credential chain at
  `mcp-servers/packages/core/src/adminAuth.ts:48` (`graph`, `intune`, `o365-admin`), and the
  device-code-only user credential at `mcp-servers/packages/core/src/auth.ts:66` (`o365-user`).

## Landmines
- **The credential chain caches its winner for the process lifetime.** `AdminCredentialChain`
  (`mcp-servers/packages/core/src/adminAuth.ts:48-109`) stores whichever link first succeeds in
  `this.resolved` and never retries an earlier, higher-priority link. Deliberate - the comment at
  `:44-46` says so - but fixing `MS_ADMIN_CLIENT_SECRET` after `cli` or `device` has won changes
  nothing until restart, and nothing tells you that. Re-verified unchanged 2026-09-06 at
  `1f97e51c`; still open as `TODO.md:51` (item 2).
- **`scopesOverride` silently broadens a narrow scope request.**
  `mcp-servers/packages/core/src/adminAuth.ts:29-36` (the field and its doc comment), `:127`
  (`secret`) and `:144` (`cli`) force `.default` regardless of what the caller asked for. Only
  `device` (`mcp-servers/packages/core/src/adminAuth.ts:149-158` - no `scopesOverride` key, and the
  comment at `:155-158` says why) honours caller-supplied delegated scopes. Code that requests a
  narrow scope and receives `.default` did not fail - it was never asked. Re-verified unchanged
  2026-09-06 at `1f97e51c`; still open as `TODO.md:62` (item 3).
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
    `TODO.md:143-150` are the later, correct account. Trust the code.
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
  `"@badali404/mcp-ms-core": "0.2.0"` at line `:29` of their own `package.json`, and core is at
  `0.2.0` (`mcp-servers/packages/core/package.json:3`). A core-only bump reaches nobody until all
  four servers republish.

## Unverified
- All four `cli.ts` files were read at this anchor, but only their first ~25 lines. Each package's
  `src/index.ts` (where `createServer` and the tool list live) and each
  `mcp-servers/packages/*/test/tools.test.ts` were not opened.
- The bodies of `mcp-servers/packages/core/src/jwt.ts`, `doctor.ts`, `toolResult.ts` and
  `graphClient.ts` were not read; their roles come from the README and from import sites.
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
