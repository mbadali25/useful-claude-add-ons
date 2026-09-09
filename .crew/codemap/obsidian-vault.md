# obsidian-vault
anchor: useful-claude-add-ons@1f97e51c
verified: 2026-09-06

## Does
Turns one or more Obsidian vaults into Claude Code's durable memory: a PostToolUse guard that
holds notes to a contract, a SessionEnd/PreCompact capture hook that queues sessions for later
distillation, gardener and reflector agents that turn that queue into notes, and per-vault MCP
registration against Obsidian's Local REST API bridge. (DERIVED:
`plugin/obsidian-vault/hooks/hooks.json:3-20`, `plugin/obsidian-vault/agents/`,
`plugin/obsidian-vault/hooks/scripts/vault_ops.py:1059-1089`.)

**The guard does not block a write.** It is registered on PostToolUse
(`plugin/obsidian-vault/hooks/hooks.json:7-12`), which fires *after* the file is on disk - the
guard even re-reads it from disk at `plugin/obsidian-vault/hooks/scripts/vault_guard.py:261-262`.
Exit 2 sends stderr back to Claude as same-turn feedback, which its own docstring states at
`plugin/obsidian-vault/hooks/scripts/vault_guard.py:24-26`; the bad file still exists until Claude
fixes it. The plugin here that can actually deny a tool call is `crew`, which registers PreToolUse
on Bash (`plugin/crew/hooks/hooks.json`, matchers `Bash`/`PowerShell` -> `guard.sh` and
`promote-gate.sh`). (DERIVED. A prior version of this note said obsidian-vault was "the only plugin
here whose hooks can block a write" - false on both halves, and false in the direction that makes a
post-hoc advisory look like a gate.)

The regression suite is still load-bearing: exit 2 is the only thing that makes a contract
violation visible at all. (JUDGEMENT.)

## Entry points
- `plugin/obsidian-vault/hooks/hooks.json:3-20` - registers SessionStart, PostToolUse, SessionEnd
  and PreCompact, each as a bash + PowerShell pair (bash at `:4,9,14,18`, PowerShell with
  `"shell": "powershell"` at `:5,11,15,19`). Verified as a pair on all four; this is the defect that
  shipped once in `crew`, where a bare command went to Git Bash on Windows and the guard stood down.
  (DERIVED.)
- `plugin/obsidian-vault/hooks/scripts/vault_guard.py:229-297` - `main()`, the PostToolUse guard,
  fired on Edit/Write/MultiEdit. Reads its config toggles at `:240-246`; early-returns 0 at `:248`
  when all three are off. (DERIVED, ranges by `ast.parse`.)
- `plugin/obsidian-vault/hooks/scripts/vault_guard.py:156-203` - `check_note`, the
  frontmatter/required-keys/title/updated-date contract, scoped by `notesPrefix` at `:159-160`.
  (DERIVED.)
- `plugin/obsidian-vault/hooks/scripts/vault_capture.py:35-87` - `main()`, the SessionEnd and
  PreCompact hook. It does **not** distil anything: it appends one markdown task line to
  `inbox/pending-reflect.md` recording timestamp, trigger, session id, cwd and transcript path
  (`:72`), de-duplicated one entry per session (`:78-79`). The gardener agent is what reads that
  queue. (DERIVED.)
- `plugin/obsidian-vault/hooks/scripts/bridge_status.py:385-427` - `main()`, the SessionStart probe,
  one line per configured vault. Its module docstring (`:2-56`, of which `:2-30` was read here)
  names the design constraint: HTTP and
  HTTPS ports both come from the vault's own `data.json` and neither is derived from the other, and
  "down" is deliberately four distinguishable states. (DERIVED.)
- `plugin/obsidian-vault/hooks/scripts/vault_ops.py:1059-1089` - `register_commands`, builds the
  `claude mcp add` invocation per vault. Driven by `/obsidian-vault:install` and `:init`.
  (DERIVED, range by `ast.parse`.)
- `plugin/obsidian-vault/hooks/scripts/obsidian_common.py:286-294` - `resolve_vault_path`, the
  single entry point every hook uses to answer "which vault am I acting on". (DERIVED.)

## Owns data
- The vault contents themselves, written by the gardener - outside this repo, at the path
  `resolve_vault_path` returns
  (`plugin/obsidian-vault/hooks/scripts/obsidian_common.py:286-294`).
- The session queue `inbox/pending-reflect.md` inside that vault
  (`plugin/obsidian-vault/hooks/scripts/vault_capture.py:31-32`). (DERIVED.)
- Machine-global vault registry `~/.claude/obsidian/config.json`, named by
  `obsidian_common.config_path` (`plugin/obsidian-vault/hooks/scripts/obsidian_common.py:62-63`)
  and read by `read_config` (`:66-73`); each vault's HTTP port lives there. Shape documented at
  `plugin/obsidian-vault/README.md:36-44`. (DERIVED. The note previously cited `README.md:39`,
  which is one row *inside* that JSON block rather than the block.)

## Calls out to
- Obsidian's Local REST API plugin, one MCP server per vault on its own port, registered via
  `claude mcp add` at `plugin/obsidian-vault/hooks/scripts/vault_ops.py:1086-1088`. A server
  already pointing at the right URL *and* carrying the right apiKey is left alone; an unreadable
  key re-registers rather than assuming a match (`:1076`, and the docstring at `:1067-1073`).
  (DERIVED.)

## Landmines
- **The three guard checks do not ship the same way.** `asciiOnly` and `requireFrontmatter`
  default OFF (`is True` tests at `plugin/obsidian-vault/hooks/scripts/vault_guard.py:241-242`);
  `checkCanvas` defaults ON, via an `is not False` test at `:243`. Assuming all three share a
  default is the easy mistake, and it inverts which rules a fresh install enforces. All three
  defaults are pinned by cases in the suite (`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:404,412,433`).
  (DERIVED.)
- **The guard only ever sees the DEFAULT vault.** `main()` calls
  `obsidian_common.resolve_vault_path()` with no name
  (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:235`), and `resolve_vault_path()` with
  `name=None` resolves the default entry
  (`plugin/obsidian-vault/hooks/scripts/obsidian_common.py:286-294` ->
  `:256-283`). Every edit to a second configured vault - the codegraphs vault, say - passes
  unchecked. `plugin/obsidian-vault/README.md:46-49` states this is deliberate. (DERIVED.)
- **`.base` files reach no structural check.** The extension filter admits `.md`, `.canvas` and
  `.base` (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:258`), but the dispatch below it is
  `if ext == ".md" and require_fm: ... elif ext == ".canvas" and check_canvas_shape:` (`:269-275`).
  A `.base` therefore only ever gets `check_ascii`, and only when `asciiOnly` is on. No case in the
  suite exercises a `.base` at all. (DERIVED; grep for `\.base` over
  `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh` returns nothing.)
- **Two differently-sized exemption sets, 20 lines apart.** `CLAUDE.md`, `README.md`, `AGENTS.md`
  and `GEMINI.md` are exempt from *requiring frontmatter*
  (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:59`); only `CLAUDE.md` is also ASCII-exempt
  (`:39`). Widening one while reading the other is how an exemption silently grows. Each of the
  three ASCII-checked names is pinned individually, after a Codex round found that testing
  `README.md` alone let a narrowing of `ASCII_EXEMPT_NAMES` pass the whole suite
  (`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:293-304`). (DERIVED.)
- **The frontmatter exemption is one check wide, not the whole function.** `fm_optional` excuses an
  exempt basename from *having* frontmatter and nothing else: a `README.md` that does carry
  frontmatter is still held to required keys, title-matches-filename and the updated date
  (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:163-178`). An earlier implementation skipped
  `check_note` entirely; the comment beside it still claimed "frontmatter-only". (DERIVED.)
- **`notesPrefix` scopes the note contract only** - not the ASCII check and not the canvas check.
  `notes_glob` is passed to `check_note` alone
  (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:270-271`); `check_ascii` (`:268`) and
  `check_canvas` (`:275`) never receive it. The note half of that is pinned
  (`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:450`) and the ASCII half is pinned by
  the `wiki/ascii/CLAUDE.md` case (`:314`). **The canvas half is not pinned:** all four canvas
  cases live under `wiki/canvases/`, which is inside the `wiki/` prefix the ON config sets, so
  adding prefix-gating to `check_canvas` would pass the suite unnoticed. (DERIVED for the code;
  JUDGEMENT that this is the next gap worth closing.)
- The guard reads file content from disk rather than from the hook payload
  (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:261-262`). Only the ASCII check prefers the
  newly introduced text (`written_text`, `:93-103`), and it falls back to the full on-disk text
  when the payload carried no new string: `added if added is not None else text` (`:268`).
  `check_note` and `check_canvas` always see the whole file. (DERIVED; the fallback clause was not
  stated in the previous version of this note.)
- The regression suite is `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh`, sabotage-tested
  per its own header (`:5-6`), with must-block and must-allow sections and four Python suites
  (`:475-478`). A change to any rule above needs a must-block and a must-allow case here before it
  ships - this repo's rule for a hook that can block. (DERIVED.)

## Measured this pass
- `env -u MSYS_NO_PATHCONV bash plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh` on `main`
  at `1f97e51c`, worktree `C:\repos\personal\useful-claude-add-ons`:
  **RESULT: 65 passed, 0 failed.** (DERIVED - run, not inferred. `MSYS_NO_PATHCONV` is unset
  deliberately; CLAUDE.md records that leaving it set mangles the suite's paths and produces a
  false regression.)
- Plugin version is `0.3.6` in both places that must agree:
  `plugin/obsidian-vault/.claude-plugin/plugin.json:3` and the `obsidian-vault` entry in
  `.claude-plugin/marketplace.json`. (DERIVED.)

## Unverified
- `plugin/obsidian-vault/agents/gardener.md` and `plugin/obsidian-vault/agents/reflector.md` were
  not opened. Their existence is confirmed by listing the directory; what they do is taken from the
  README command table and from `vault_capture.py`'s HEADER text
  (`plugin/obsidian-vault/hooks/scripts/vault_capture.py:24-28`), not from reading the agents.
- Eleven command files exist under `plugin/obsidian-vault/commands/` - canvas, doctor, garden,
  graph, init, install, map, note, optimize, reflect, repair (DERIVED, directory listing). None
  were opened. The plugin also ships three skills (`obsidian-memory-contract`,
  `obsidian-scheduling`, `obsidian-setup`) that the previous version of this note did not mention
  at all; none were opened.
- `plugin/obsidian-vault/hooks/scripts/vault_profiles.py` internals are still inferred from its
  test file rather than read. `bridge_status.py` has now been read at the docstring and
  function-boundary level (`ast.parse`), but no function body beyond that was read - treat any
  claim about its per-state wording as unverified.
- Nothing in this pass touched a live vault, a live bridge port, or `~/.claude/obsidian/config.json`.
  Every guard fact above comes from reading the source or from the suite's own throwaway fixtures.
- Whether anything in a SKILL.md or command markdown *contradicts* the code above is unknown: those
  files are prose instructions to a model, not mechanism, and none were read this pass.

## Re-anchor provenance
The per-path diff `a02331ee..1f97e51c` over the paths this note cites showed **documentation churn
only** - `CLAUDE.md` and `README.md`, nothing under `plugin/obsidian-vault/hooks/scripts/`. By the
usual signal the note was current.

**That signal was wrong.** The note was re-read against the code anyway, and the near-empty diff
turned out to be a false clean bill: three claims were wrong *when written*, not drifted into.
Re-read in full this pass: `plugin/obsidian-vault/hooks/hooks.json` (all 22 lines),
`plugin/obsidian-vault/hooks/scripts/vault_guard.py` (all 301 lines),
`plugin/obsidian-vault/hooks/scripts/vault_capture.py` (all 91),
`plugin/obsidian-vault/hooks/scripts/obsidian_common.py:60-100` and `:256-300`,
`plugin/obsidian-vault/hooks/scripts/vault_ops.py:1036-1100`,
`plugin/obsidian-vault/hooks/scripts/bridge_status.py:2-30`,
`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:1-40,285-330,436-482`,
`plugin/obsidian-vault/README.md:25-60`, `plugin/crew/hooks/hooks.json` (events and PreToolUse
matchers), and the marketplace entry. Every function range quoted above came from `ast.parse`
printing `lineno`-`end_lineno`, not from counting `sed` output. The suite was executed rather than
cited.
