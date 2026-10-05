---
name: stack-node
description: |
  Server-side and CLI Node.js and TypeScript pitfalls, checks and verify.json wiring - child
  processes, fetch status handling, paging that says when it stopped, unhandled rejections,
  module format, dates and big integers - and the Node candidate standards. Use when the repo
  has a package.json with server, Lambda, MCP-server or CLI code, or the user asks to write or
  review Node.js or TypeScript outside a browser.
---

# Stack: Node.js and TypeScript (server and CLI)

## When this applies

MCP servers, Lambdas, CLIs and services: any `*.ts`/`*.mts`/`*.cts`/`*.js`/`*.mjs`/`*.cjs`
that runs under Node. Read `package.json` (`engines`, `"type"`, scripts) and the lockfile
first, and run the Node major the deploy target runs. Browser, Angular-template and
Playwright work is `stack-angular`'s and `stack-web`'s; `stack-web` also owns the Windows
`cmd /c npx` and `node_modules/.bin` probe rules, which this skill does not repeat.

## Pitfalls that cost time

- **A shell string is an injection sink.** `exec`/`execSync` and `shell: true` hand one string
  to `/bin/sh -c` or `cmd.exe`. Values from outside the code (paths, branch names, user text)
  go as an argv array to `execFile`/`spawn`. On Windows a `.cmd`/`.bat` target cannot run
  without a shell, so it needs an explicit, quoted plan. (Candidate NODE-P1.)
- **`fetch` resolves on HTTP errors.** Branch on `res.ok`/`res.status` before treating the body
  as data; read an error body safely (text, JSON only if it is JSON) and throw with the status.
  An error response never becomes `[]`, `0` or "none found". (Candidate NODE-P2.)
- **A page cap is not the end of the data.** A client that stops early returns a value that
  says so (`{ items, truncated }`, a cursor), and one that fetched everything does not claim
  truncation. (Candidate NODE-08.)
- **An unhandled promise rejection ends the process** (the default since Node 15). Await or
  `.catch` every promise; a fire-and-forget call needs its own handler.
- **Types are erased at run time.** `as Foo` and a generic on `JSON.parse` check nothing; parse
  input from the network, a file or a child at the boundary and refuse the wrong shape.
- **ESM and CommonJS differ by file**: `"type"` in `package.json` and the `.mjs`/`.cjs`
  extensions decide how a file loads, and the interop rules changed across Node majors.
- **`new Date("2026-01-02")` is UTC midnight; `new Date("2026-01-02T00:00:00")` is local
  time.** Store and compare instants in UTC with an explicit offset.
- **Integers above 2^53 lose precision in `JSON.parse`** (`9007199254740993` reads back as
  `...992`). Keep large ids as strings, or use `BigInt` deliberately.
- **`process.exit()` can cut off buffered output** to a pipe; set `process.exitCode` and let
  the event loop drain instead.
- **`npm ci` installs the lockfile; `npm install` may rewrite it.** CI and reviews use `npm ci`,
  and a lockfile change in a feature change is a dependency change - say which packages moved.

## Standards

No gated Node standards set ships yet (L-0537). NODE-08 is at the bar in the spec's private
re-count (4), but its Earned-by evidence lives in a private repository and could not be
written here; public change sets do not count (owner, 2026-10-05). When earned, the set is
`crew-standards/references/node.md`, set `NODE`. The candidates and the evidence each has
are in `references/candidates.md`; they are guidance, not rows of the self-check.

## Verification

Run what the repo runs (`npm test`, `vitest`, `jest`, `node --test`) and the type check
(`tsc --noEmit`) with the Node major the target runs, and report exit codes, never the
summary line. A change to a child-process or HTTP path needs a test that drives the failure
(a non-zero child exit, a 4xx/5xx with an HTML body, a page cap reached).

## verify.json rules to propose

```json
{
  "paths": ["**/*.ts", "**/*.mts", "**/*.cts", "**/*.js", "**/*.mjs", "**/*.cjs", "package.json"],
  "run": [
    "sh -c 'command -v npm >/dev/null 2>&1 || { echo \"TOOL MISSING: npm is not on PATH, so the test suite DID NOT RUN. This is a missing tool, not a passing or failing check. Install Node.js to check locally.\" >&2; exit 77; }; npm test'",
    "sh -c 'T=node_modules/.bin/tsc; [ -x \"$T\" ] || { echo \"TOOL MISSING: node_modules/.bin/tsc is not installed, so the type check DID NOT RUN. Run npm ci to check locally.\" >&2; exit 77; }; \"$T\" --noEmit'"
  ],
  "reach": "local",
  "why": "the repo's tests and the TypeScript compiler catch a broken change before a human reviews the diff"
}
```

Drop the `tsc` command in a plain-JavaScript repo. Nothing in this repo writes rules into
`verify.json` on a skill's behalf (see `crew-verification`) - add by hand.

## LSP

No official TypeScript LSP plugin is decided for crew.
