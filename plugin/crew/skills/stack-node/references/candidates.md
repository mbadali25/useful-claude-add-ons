# Node.js candidate standards (not gated)

No gated Node.js standards set ships yet (L-0537). Nothing in this file is loaded by
`crew_standards.py` or asked in the pre-review self-check. It is guidance, kept with its
evidence. A rule is promoted once three distinct reviewed change sets earn it. NODE-08 keeps
its research id. NODE-P1, -P2 and -P3 are public-pass labels that the loader cannot read
(`[A-Z]{2,6}-\d{2}`), so on promotion each takes its research id once the owner's file maps
it, or else the next unused `NODE-NN`. It goes into `crew-standards/references/node.md` (set `NODE`, `applies-to:
["**/*.ts", "**/*.mts", "**/*.cts", "**/*.js", "**/*.mjs", "**/*.cjs"]`).

**Why nothing ships.** The bar and the counting rule are `python.md`'s: a change set is a
crew review, or a fix commit whose own message or CHANGELOG entry records that a review found
the defect. There is no file-type condition. The spec's re-count over the owner's private
repository and this one puts NODE-08 at four, and every other research rule at two or fewer.
NODE-08's Earned-by text has to come from that private repository, and this build did not
have it. The owner decided on 2026-10-05 that public third-party change sets do not count.
The rules marked `NODE-Pn` come from a public pass on 2026-10-05. Its commit messages came
from GitHub commit search, and diffs were not read. `NODE-Pn` are labels, not research ids.
Every Source sentence was string-matched against the raw page on 2026-10-05: Node.js
v26.10.0 docs, MDN, and the MCP specification 2025-06-18.

## Candidate standards (not gated)

### NODE-08 A partial result says it is partial, and a complete one says it is complete

Counted toward the bar: 4, in the spec's re-count (one change set in this repository, three
in a private one). It is held back because the private change sets cannot be cited here yet.
2 public change sets and 1 weak lead, none of which count.

A paging client that stops early (a page, item, size or time cap) returns a value that says
so: `{ items, truncated: true }`, a cursor, or an explicit note in a tool result. It never
returns a short list shaped like a complete one. The flag is exact: a fetch that reached the
cap with nothing left is not marked truncated.

- This repository, commit `c80c68c8` ("mcp-servers: fix Codex QA findings - ... truncation"):
  "getAllPages() silently truncated at maxPages, presenting a partial list as complete. It
  now returns { items, truncated } instead of a bare array".
- Public change sets: devondragon/MotionMCP@53fb3106 (a review-cleanup finding: truncation
  reported the actual returned count) and evdanil/vscode-NexTerminal@f0e739cc (a review
  finding: an exact-cap fetch is no longer marked truncated). Uncounted lead:
  knpkv/npm@6b460535 (review pagination feedback, but its message does not tie the
  truncation change to a review item).

Source: https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/pagination:
"Clients SHOULD: Treat a missing nextCursor as the end of results". So a server never drops
a cursor it still has. No Node doc states the rule itself.

### NODE-P1 Spawn a child process with an argument array, never a shell string built from input

Counted toward the bar: unknown (its research id could not be determined). 3 public change
sets, which do not count.

Use `execFile`, `spawn` or `execFileSync` with an argv array and `shell: false` (the default)
for any command that carries a value from outside the code. Do not use `exec`/`execSync`,
or a template literal with `shell: true`. A Windows `.cmd` or `.bat` target is the exception:
it cannot be launched without `cmd.exe`, so an argument array alone does not make it safe.
Quoting is not enough there, because embedded quotes can break out of it. Untrusted input is
refused, or checked against a strict allow-list that admits no quotes and no `cmd.exe`
metacharacters, before it reaches a batch file.

Public leads: grimmerk/codev@897c2889 (CodeRabbit review, "use execFile instead of exec"; a
second review fix one day later counts with it), iOfficeAI/AionUi@f192f772 (code review HIGH
#3: `exec()` replaced by `execFile()` with an args array), and
ryanbr/network-scanner@51cc08b3 (a review pass found command strings built by template
literals).

Source: https://nodejs.org/api/child_process.html: "Never pass unsanitized user input to this
function. Any input containing shell metacharacters may be used to trigger arbitrary command
execution." "The child_process.execFile() function is similar to child_process.exec() except
that it does not spawn a shell by default."

### NODE-P2 Check the HTTP status before treating the body as data; a failed read is an error, never empty data

Counted toward the bar: unknown (its research id could not be determined). This repository's
commit `c80c68c8` records it ("status-first parsing", from Codex QA findings). 3 public change
sets, which do not count.

After `fetch`, or any HTTP client that does not throw on 4xx/5xx, branch on `res.ok` or
`res.status` before treating the body as successful data. An error body may still be read
safely (as text, and parsed only if it is JSON) to carry its detail into the error, as
`c80c68c8` does. Throw an error that carries the status. An error response is never mapped to `[]`, `0`, "none found" or "no positions",
and a write whose response is not `ok` is reported as failed.

Public leads: BDortant/ToDo@51eeef65 (CodeRabbit review: `JSON.parse` ran before the `res.ok`
branch), frankbria/podcaststudiohub@a3c7f8a1 (a cross-family review: Sentry 401/429 were
reported as success; that repository is mainly Python), and
akyachtsman/claude.trading@89260275 (an audit: an error read as "no positions").

Source: https://developer.mozilla.org/en-US/docs/Web/API/Window/fetch: "A fetch() promise
does not reject if the server responds with HTTP status codes that indicate errors (404, 504,
etc.). Instead, a then() handler must check the Response.ok and/or Response.status
properties."

### NODE-P3 Send credentials only to the configured origin

Counted toward the bar: unknown. This repository's mcp-servers 0.2.1 (T-0090) fixed it ("the
Graph token goes only to the configured Graph origin"), but the entry does not say how the
defect was found. The Angular analogue is NG-P2.

A client that attaches a bearer token checks every request URL it builds or follows against
the configured origin before it attaches the token: absolute caller URLs, paths joined to the
base, and next-page links such as `@odata.nextLink` or `Link: rel=next`. The check compares
scheme, host and port, and refuses userinfo. Redirects are a separate question. The T-0090
entry records that Node 22's `fetch` already strips `Authorization` on a cross-origin
redirect, measured on Node 22.22.1, so that fix left redirects unchanged. A client on another
HTTP stack checks its own redirect behaviour.

Source: this repository's CHANGELOG, "Security - mcp-servers 0.2.1: the Graph token goes only
to the configured Graph origin (T-0090)". It records the defect and the fix, but not a review
that found it. Verdict: candidate. The available evidence does not establish a reviewed change
set.

## Research rules not written here

NODE-01 to -07 and -09 to -18 are the owner's research ids. The spec's re-count gives -06 2,
-07 2 and -10 2. It gives 1 each to -01, -03, -04, -05, -09, -11, -12, -13, -14, -15 and -18,
and 0 to -02, -16 and -17. Their rule text was not available to this build. Whether NODE-P1,
-P2 or -P3 is one of them could not be determined.
