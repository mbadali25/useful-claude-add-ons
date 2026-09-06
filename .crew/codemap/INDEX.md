# Code map — index

Not counted as a subsystem by `crew_state.py` (`read_knowledge`,
`plugin/crew/hooks/scripts/crew_state.py:222-223` lists `INDEX.md` in
`_NOT_SUBSYSTEMS`). It exists purely as a table of contents.

Every subsystem file below carries an `anchor:` line
(`plugin/crew/hooks/scripts/crew_state.py:218-220` is the regex that reads it)
naming the short commit hash the file's claims were checked against. If HEAD
has since moved past that hash, `crew_state.py` will list the file under
`knowledge.behind` at the next SessionStart — that is a prompt to re-check the
claims, not proof they are wrong.

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
to an unanswerable question, but it is not a useful one.

## Files

| File | Anchor | Covers |
|---|---|---|
| [`marketplace-registration.md`](marketplace-registration.md) | `3167721f` | The marketplace itself: what registers a skill vs. a plugin, the two install scripts, and the two separate version-check paths (`check-marketplace.py` vs. `_verify/smoke.sh`). |
| [`localgpu.md`](localgpu.md) | `3167721f` | The `localgpu` plugin: its two independent process trees, the shared-Ollama constraint that drives `OLLAMA_MAX_LOADED_MODELS=1`, the embed-model mismatch guard, `.mcp.json` provisioning, and the bootstrap.sh/bootstrap.ps1 parity verdict. |
| [`crew.md`](crew.md) | `3167721f` | The `crew` plugin: hooks, agents, commands, skills inventory, and how `crew_state.py` reads this very directory. |
| [`verification-harness.md`](verification-harness.md) | `3167721f` | `_verify/smoke.sh`, `_verify/run-all.sh`, `scripts/check-marketplace.py`, and `.crew/verify.json` — what each actually runs, and where they overlap or don't. **`.crew/verify.json` does not exist**; see below. |
| [`obsidian-vault.md`](obsidian-vault.md) | `a02331ee` | The `obsidian-vault` plugin: four hook events registered as bash+PowerShell pairs, the three guard checks and their **unequal defaults**, the two differently-sized exemption sets, and per-vault MCP registration. |
| [`mcp-servers.md`](mcp-servers.md) | `a02331ee` | The TypeScript monorepo — four stdio MCP servers over one shared `core`. Holds the two recorded `adminAuth.ts` defects (TODO #2 and #3), re-verified unchanged. Not a marketplace plugin; nothing registers it. |
| [`install-scripts.md`](install-scripts.md) | `a02331ee` | The `install-prerequisites.{sh,ps1}` matched pair: catalog parity (confirmed in sync), the `pick_fit`/`Format-PickerLine` no-bypass rule, idempotency branches, and hook-plugins-default-off on both sides. |
| [`skills-itsm.md`](skills-itsm.md) | `a02331ee` | `infra-work-ticketing` + `notify`. Records that **`SKILL.md:209-211` instructs an unconfirmed ticket creation** against a live service desk, and that its `:213` list is missing-fact questions, not write confirmation. |
| [`skills-security-ops.md`](skills-security-ops.md) | `a02331ee` | `cisco-meraki` + `wazuh-onprem`. Records that **Wazuh's generic `post`/`put`/`delete` have no gate in code** — only prose — and that the skill with the ungated verbs is the one with no tests. |
| [`repo-docs.md`](repo-docs.md) | `a02331ee` | `docs/` and `CHANGELOG.md`. Records that **`docs/adr/` does not exist** despite two documents citing it, and that TODO.md's `render.sh` entry is stale — the `cygpath -w` fix is in source. |

## Coverage — and what is still unmapped

Ten subsystems, covering 76% of graph nodes at `a02331ee` (5056 of 6614 with a `source_file`).
What remains unmapped is almost entirely the single-skill directories under `skills/` — the largest
are `work-log-reporter`, `web-testing-playwright`, `visio-diagrams`, `intune-graph`,
`aws-opensearch`, `claude-code-tuneup`, `sophos-central` and `repo-docs`, none individually large.

That percentage is a measurement, not a target, and it moves whenever the graph is rebuilt.
Re-measure instead of trusting it: group node `source_file` values by top-level directory and
subtract the prefixes each file above claims.

The four `3167721f` anchors were checked per-path on 2026-09-06 and are **current despite the lag**
— the only commits touching their cited paths since that sha are an `obsidian-vault` version bump
and a `PLUGINS.md` assertion count inside the obsidian-vault section, neither of which any of the
four describes. They were deliberately not re-anchored: an anchor bump is a freshness claim, and a
path diff cannot see prose that has gone stale in ways the paths do not reveal.

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
