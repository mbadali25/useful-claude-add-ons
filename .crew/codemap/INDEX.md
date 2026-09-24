# Code map — index

Not counted as a subsystem by `crew_state.py` (`read_knowledge` at
`plugin/crew/hooks/scripts/crew_state.py:692`; `_NOT_SUBSYSTEMS` at
`plugin/crew/hooks/scripts/crew_state.py:539` lists `INDEX.md`). It exists purely
as a table of contents.

Every subsystem file below carries an `anchor:` line
(`_ANCHOR_RE`, `plugin/crew/hooks/scripts/crew_state.py:534`, is the regex that
reads it) naming the short commit hash the file's claims were checked against.

**Since crew 0.19.13 that read has three outcomes, not two**, and the difference
decides what you do next:

| State | Means | Do |
|---|---|---|
| current | the anchor is HEAD | nothing |
| `knowledge.behind` | the anchor resolves to a commit, but is not HEAD | **re-check** — run the path diff below; empty output means current despite the lag |
| `knowledge.unresolvable` | no anchor, or a sha this repository does not contain | **re-derive** — the path diff cannot run at all, so nothing about the note can be confirmed or refuted from git |

The third state exists because five notes here spent weeks in it while being
reported as merely "behind". `519754fa` wrote them and was a squash merge, which
discards the branch commit the writer recorded — so the sha they carried named
nothing. "Behind" is a cheap, definite finding, and a reader who cannot tell the
two apart does the cheap thing. The writer now records
`git merge-base HEAD origin/main`, a commit already on the trunk, which survives
a squash.

**The anchor line's shape is load-bearing.** `_ANCHOR_RE` ends `\s*$`, so
anything after the sha on that line — a parenthetical note included — stops it
matching and puts the note straight into `unresolvable`. Commentary goes on the
next line.

**That prompt is much coarser than the real test, and treating the two as the
same thing is how the trigger stops meaning anything.** `crew_state.py` compares
the anchor to HEAD as a *string*, so any commit at all — including one that
touches only this directory — marks every note behind. The test that actually
decides is the path diff:

```bash
git diff --name-only <anchor>..HEAD -- <the paths the note cites>
```

Comparison is by path, never by `path:line`. Run on 2026-09-05 across
`b56d41f..3167721f`, that test found `localgpu.md` and all three diagrams
*current* while the sha test called all seven behind.

**Every `path:line` here is repo-relative, and that is load-bearing rather than
cosmetic** — an anchor written relative to its subsystem root (`config.py:99`
instead of `plugin/localgpu/mcp/config.py:99`) resolves fine by eye and cannot
be pasted into the command above, so nobody can re-verify it. 30 anchors here
and 30 more in `docs/diagrams/` were in that shape and were rewritten on
2026-09-05 (`server.py:187` -> `plugin/localgpu/mcp/server.py:187`).

**The invariant, rather than a count:** every `path:line` in this directory
resolves to an existing file with the cited line in range. The only exceptions
are `127.0.0.1:11434` in `localgpu.md`, a loopback URL that a naive
`name.ext:digits` regex reads as a path and which is not one.

A total is deliberately not stated. Writing "N anchors" into a note *changes*
N — the provenance sections added on 2026-09-05 cite files of their own, and
the sentence recording the number moved the number twice while being written.
Re-measure instead of trusting a figure: walk the `` `path:line` `` tokens in
these files, skip anything whose "extension" is all digits, and confirm each
resolves. A number that is wrong by one is worse than no number, because it
looks measured.

Diagrams under `docs/diagrams/` carry the same contract via a
`%% Anchors: <comma-separated paths>` header. All three were missing one, which
left them permanently unfalsifiable — "stale by default" is the honest answer
to an unanswerable question, but it is not a useful one. **All four now carry
one** (`data-flow-crew-config.mmd` was added 2026-09-12), so each is
hand-re-verifiable via the path diff.

Diagrams are read by a *different* regex — `_DIAGRAM_ANCHOR_RE`,
`plugin/crew/hooks/scripts/crew_state.py:598`. It cannot be the same one: a bare
`anchor:` line is a syntax error in a Mermaid source, so the provenance has to
live inside a `%%` comment. Both `%% anchor: <sha>` and
`%% Generated from <repo>@<sha> on <date>.` are accepted.

## Files

Anchors are re-measured below rather than carried forward — the previous table
named `3167721f` and `a02331ee` for every row, and no file carried either sha.

Re-measured again 2026-09-23, at `bc6a3a09`: the table had drifted the same way a
third time, naming `7b0d8f3a` and `1f97e51c` for rows whose notes carried neither.
Every anchor in the table is now read out of the note's own `anchor:` line with the
`<repo>@` prefix stripped, rather than typed. The drift has recurred on every pass
that edited this table by hand, so **re-derive this column mechanically or not at
all** - a hand-written anchor here is indistinguishable from a measured one and has
been wrong three times running.

| File | Anchor | Last pass | Covers |
|---|---|---|---|
| [`marketplace-registration.md`](marketplace-registration.md) | `5d1fc5fd` | re-verified 2026-09-12 | The marketplace itself: what registers a skill vs. a plugin, the two install scripts, and the two separate version-check paths (`check-marketplace.py` vs. `_verify/smoke.sh`). |
| [`localgpu.md`](localgpu.md) | `5d1fc5fd` | unchanged | The `localgpu` plugin: its two independent process trees, the shared-Ollama constraint that drives `OLLAMA_MAX_LOADED_MODELS=1`, the embed-model mismatch guard, `.mcp.json` provisioning, and the bootstrap.sh/bootstrap.ps1 parity verdict. |
| [`crew.md`](crew.md) | `5d1fc5fd` | **re-derived** 2026-09-12 | The `crew` plugin: hooks, agents, commands, skills inventory, and how `crew_state.py` reads this very directory. |
| [`verification-harness.md`](verification-harness.md) | `5d1fc5fd` | re-verified 2026-09-12 | `_verify/smoke.sh`, `_verify/run-all.sh`, `scripts/check-marketplace.py`, and `.crew/verify.json` — what each actually runs, and where they overlap or don't. **`.crew/verify.json` does not exist**; see below. |
| [`obsidian-vault.md`](obsidian-vault.md) | `60c79407` | **re-derived** 2026-09-22 | The `obsidian-vault` plugin: four hook events registered as bash+PowerShell pairs, the three guard checks and their **unequal defaults**, the two differently-sized exemption sets, and per-vault MCP registration. PR #210 added a proven-interpreter resolver to the two remaining "naive" wrappers, a loud stdin-decode failure mode, and a PowerShell legacy-argument-passing fix. |
| [`mcp-servers.md`](mcp-servers.md) | `5d1fc5fd` | unchanged | The TypeScript monorepo — four stdio MCP servers over one shared `core`. Holds the two recorded `adminAuth.ts` defects (TODO #2 and #3), re-verified unchanged. Not a marketplace plugin; nothing registers it. |
| [`install-scripts.md`](install-scripts.md) | `5d1fc5fd` | re-verified 2026-09-12 | The `install-prerequisites.{sh,ps1}` matched pair: catalog parity (confirmed in sync), the `pick_fit`/`Format-PickerLine` no-bypass rule, idempotency branches, and hook-plugins-default-off on both sides. |
| [`skills-itsm.md`](skills-itsm.md) | `089a04b9` | unchanged | `infra-work-ticketing` + `notify`. Records that **`SKILL.md:209-211` instructs an unconfirmed ticket creation** against a live service desk, and that its `:213` list is missing-fact questions, not write confirmation. |
| [`skills-security-ops.md`](skills-security-ops.md) | `ea8a014` | unchanged | `cisco-meraki` + `wazuh-onprem`. Records that **Wazuh's generic `post`/`put`/`delete` have no gate in code** — only prose — and that the skill with the ungated verbs is the one with no tests. |
| [`repo-docs.md`](repo-docs.md) | `5d1fc5fd` | re-verified 2026-09-12 | `docs/` and `CHANGELOG.md`. Records that **`docs/adr/` does not exist** despite two documents citing it, and that TODO.md's `render.sh` entry is stale — the `cygpath -w` fix is in source. |

## Coverage — and what is still unmapped

Ten subsystems, covering 76% of graph nodes at `a02331ee` (5056 of 6614 with a `source_file`).
What remains unmapped is almost entirely the single-skill directories under `skills/` — the largest
are `work-log-reporter`, `web-testing-playwright`, `visio-diagrams`, `intune-graph`,
`aws-opensearch`, `claude-code-tuneup`, `sophos-central` and `repo-docs`, none individually large.

That percentage is a measurement, not a target, and it moves whenever the graph is rebuilt.
Re-measure instead of trusting it: group node `source_file` values by top-level directory and
subtract the prefixes each file above claims.

**Re-anchor pass, 2026-09-12.** Five notes carried `d61342c3`, which resolves to nothing here, so
the path diff could not run on any of them. Four were **re-verified** — every claim is the previous
pass's, re-read against the file it cites and its citation re-pointed where the code had moved, by
matching on content rather than applying an offset. `crew.md` was **re-derived**: six merged PRs had
rewritten what it describes (the config layering, the authority tiers, the ten newly-declared keys,
`AUTOCLEAR_CONSENT_KEYS`), so re-pointing it would have produced correct line numbers pointing at
claims about a crew that no longer existed. Each of the four says on its own line which it got.

The five `1f97e51c` anchors were **not** touched in that pass and are not claimed to be fresh.

What the re-verification found that a working anchor would not have: `install-scripts.md`'s
citations never matched its own anchor (they match `0131d0f0`, three days earlier);
`repo-docs.md` is mixed-base, with its `TODO.md` citations from one commit and its `CHANGELOG.md`
citations from another; `marketplace-registration.md`'s count finding had **inverted**, with all
four places it named as correct now wrong; and `verification-harness.md` has 31 citations into
`.crew/verify.json`, which is gitignored and absent from this checkout and therefore unverifiable
by anyone cloning the repo.

## How to read these files

Every non-obvious claim is marked **DERIVED** (read from source, with a
`path:line` a reader can re-check) or **JUDGEMENT** (this writer's
interpretation of why something is the way it is). A DERIVED claim that turns
out wrong on re-check is more valuable to flag than to quietly leave — say so
in the file rather than deleting the claim, so the next reader knows it was
checked and found stale.

These files do not restate `CLAUDE.md`. That file holds the judgement calls
and the landmines already earned by past incidents; this directory holds the
map — what is actually true of the code right now, at the anchored commit.
