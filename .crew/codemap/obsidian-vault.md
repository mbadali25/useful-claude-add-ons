# obsidian-vault
anchor: useful-claude-add-ons@2b337296
verified: 2026-09-22

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
- `plugin/obsidian-vault/hooks/scripts/bridge_status.py:385` — module entry point (`main()`), from the graph
- `plugin/obsidian-vault/hooks/scripts/vault_capture.py:35` — module entry point (`main()`), from the graph
- `plugin/obsidian-vault/hooks/scripts/vault_guard.py:229` — module entry point (`main()`), from the graph
- `plugin/obsidian-vault/hooks/scripts/vault_ops.py:1821` — module entry point (`main()`), from the graph

## Owns data
- The vault contents themselves, written by the gardener - outside this repo, at the path
  `resolve_vault_path` returns
  (`plugin/obsidian-vault/hooks/scripts/obsidian_common.py:286-294`).
- The session queue `inbox/pending-reflect.md` inside that vault
  (`plugin/obsidian-vault/hooks/scripts/vault_capture.py:31-32`). (DERIVED.)
- Machine-global vault registry `~/.claude/obsidian/config.json`, named by
  `obsidian_common.config_path` (`plugin/obsidian-vault/hooks/scripts/obsidian_common.py:62-63`)
  and read by `read_config` (`:66-73`); each vault's HTTP port lives there. Shape documented at
  `plugin/obsidian-vault/README.md:36-44`. (DERIVED. The note previously cited
  `plugin/obsidian-vault/README.md:39`, which is one row *inside* that JSON block rather than the
  block.)

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
- **Every claim above is about `vault_guard.py`. Nothing runs it directly.** `hooks.json` invokes
  the *wrappers* - `plugin/obsidian-vault/hooks/scripts/vault-guard.sh` (`:9`) and
  `vault-guard.ps1` (`:11`) - and until 2026-09-22 this note documented the Python and never the
  two scripts that decide whether the Python runs at all. That gap is where the 0.3.13 defect
  lived: a guard can be perfectly correct and still check nothing.
  The resolver was `command -v python3 || command -v python || command -v py`
  (`plugin/obsidian-vault/hooks/scripts/vault-guard.sh` at the anchor), which answers "is there a
  FILE named python on PATH", not "is there a working interpreter". A Windows WindowsApps App
  Execution Alias is a real executable file, so `command -v python3` resolved it, the stand-down
  branch was skipped, and `exec`-ing the stub **exited 49 with zero bytes on stderr** (the alias
  prints its Store message to stdout and exits 9009; `9009 & 0xFF = 49`). PostToolUse treats any
  status but 2 as non-blocking and surfaces only stderr, so the guard checked nothing, said
  nothing, and was indistinguishable from a clean pass. CLAUDE.md's named recurring bug - an
  unknown collapsing into the safe-looking value - in its purest form. (DERIVED, from the incident
  comment the fix left behind at
  `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:19-37`.)
  Fixed in 0.3.13. `_vault_guard_resolve_python`
  (`plugin/obsidian-vault/hooks/scripts/vault-guard.sh:70-121`) rejects a WindowsApps path by
  pattern (`:79-81`), then **runs** each candidate and requires it to echo back a token this script
  chose (`:95-103`), rejects an empty `sys.executable` (`:106-108`), re-checks the resolved
  `sys.executable` for WindowsApps (`:109-113`), and uses `sys.executable` rather than the
  PATH-found name. Two distinct stand-down messages, not one (`:125` and `:127`): "found nothing
  named python" and "found something named python that is not an interpreter" send a reader to
  different places, and the second says in the message that the write **was not checked**.
  Three further things about that fix that are easy to get backwards:
  - **It is deliberately stricter than crew's copy of the same resolver**
    (`plugin/crew/hooks/scripts/role-write-guard.sh:32-57`), which accepts any non-empty stdout on
    a zero exit. That rejects the Store alias but not its neighbour, a shim that prints a line and
    exits 0. The reasoning is at `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:89-94`.
  - **It is copied, not imported, and that was a decision rather than an oversight**
    (`:45-56`): crew and obsidian-vault are separate marketplace entries, `${CLAUDE_PLUGIN_ROOT}`
    points at one plugin, and a host with obsidian-vault and no crew is the ordinary case, so
    there is no path this script could source. A shared copy *inside* obsidian-vault was declined
    for now because the other two bash wrappers here - `bridge-status.sh` and `vault-capture.sh` -
    **still carry the naive one-liner**, and moving all three onto one resolver widens the blast
    radius from the one hook that can report a violation to every hook this plugin registers.
    (DERIVED for the decision and its reasoning; the two remaining naive wrappers are JUDGEMENT as
    to risk - they are SessionStart and SessionEnd/PreCompact, neither of which reports a contract
    violation, so the same stub costs a status line rather than a false clean bill.)
  - **`exec` was removed** (`:132-147`). `vault_guard.py` exits 0 or 2 and nothing else, so any
    other status means it never reached a verdict; under `exec` that landed as a bare numeric exit,
    which is the silent shape the whole script exists to avoid. It now runs the interpreter as a
    child, and a status that is neither 0 nor 2 prints "this write was NOT checked" and stands down
    at exit 0.
  Pinned by `plugin/obsidian-vault/hooks/scripts/_test/test_vault_guard_sh.sh`, run from the main
  suite as one folded case at `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:500`.
  **The stub is MODELLED, not observed** - built on Linux from the alias's documented behaviour
  (`plugin/obsidian-vault/hooks/scripts/vault-guard.sh:35-37` says so). The *shape* of the failure
  is verified; the Windows fixture behind it is not, and nobody has reproduced this on a real
  WindowsApps machine. (DERIVED, including the limitation - it is the script's own admission, not
  an inference.)
- **Both PowerShell flavours no longer run on one host.** `hooks.json` registers every event twice,
  once per flavour, so on a machine with bash *and* `pwsh` both halves of each pair would fire
  unless the `.ps1` stands down off Windows. All three `.ps1` wrappers now open with
  `if ($env:OS -ne 'Windows_NT') { exit 0 }` -
  `plugin/obsidian-vault/hooks/scripts/bridge-status.ps1:13`,
  `plugin/obsidian-vault/hooks/scripts/vault-capture.ps1:14`,
  `plugin/obsidian-vault/hooks/scripts/vault-guard.ps1:45`. (DERIVED.)
  **`$env:OS`, not `$IsWindows`** - and the comment at
  `plugin/obsidian-vault/hooks/scripts/bridge-status.ps1:9-12` records why: `$IsWindows` does not
  exist in PowerShell 5.1, so a bare `if (-not $IsWindows)` is truthy there and stands the hook
  down on the one platform it exists for. crew shipped that inversion once already.
  The pin derives its file list from `hooks.json` itself
  (`plugin/obsidian-vault/hooks/scripts/_test/test_flavour_guard.py`), so registering a new hook
  with no guard turns it red without anyone editing the test - which is the difference between a
  regression test and a list that goes stale. (DERIVED.)
- The regression suite is `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh`, sabotage-tested
  per its own header (`:5-6`), with must-block and must-allow sections and four Python suites
  (`:475-478`). A change to any rule above needs a must-block and a must-allow case here before it
  ships - this repo's rule for a hook that can block. (DERIVED.)

## Measured this pass
- `env -u MSYS_NO_PATHCONV bash plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh` re-run at
  `84976536`, on **Linux**, checkout `/repos/personal/useful-claude-add-ons`, branch
  `crew-0.19.96-docbuilder-install-fixes`: **RESULT: 67 passed, 0 failed.** (DERIVED - run, not
  inferred. The ref and the platform are stated because a count without them can only be believed:
  the previous `65 passed` was taken on Windows at `34a333f0`, and two of this run's cases are
  platform-sensitive.)
  The two new passes are not new assertions about old code - they are two whole sub-suites folded
  into one case each: `sh_suite` at
  `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:500` (the wrapper resolver, below) and
  the PowerShell flavour guard at `:508-515`. **Both ran behaviourally here**, because `pwsh` is on
  PATH at `/snap/bin/pwsh`; run directly, `test_flavour_guard.py` reports 36 passed, 0 failed over
  four cases. On a host without `pwsh` the flavour guard exits 77 and the runner prints `SKIP:` and
  folds it into neither count (`:511-515`), so **67 is not the number every machine sees** - a host
  with no `pwsh` gets 66 passed and one skip. (DERIVED.)
- Plugin version is `0.3.14` in both places that must agree:
  `plugin/obsidian-vault/.claude-plugin/plugin.json:3` and the `obsidian-vault` entry in
  `.claude-plugin/marketplace.json:248`. (DERIVED - `0.3.8` -> `0.3.14` between anchors; both places
  still agree. **The marketplace citation was re-pointed, not offset**: this note cited
  `.claude-plugin/marketplace.json:242`, and `:242` now lands inside the `localgpu` entry and reads
  `"version": "0.1.20"`. A line number that still resolves, still looks like a version, and names a
  different plugin is the worst shape a stale citation can take - it re-reads as confirmation.)

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

**Re-anchored `1f97e51c` -> `34a333f0` on 2026-09-14.** The per-path diff over this note's cited
paths flagged two moved files. `plugin/obsidian-vault/.claude-plugin/plugin.json` bumped
`0.3.6` -> `0.3.8`; the marketplace entry moved with it (both re-read and re-cited above; that citation was
`.claude-plugin/marketplace.json:242` and is corrected to `:248` at the 2026-09-22 pass). `plugin/obsidian-vault/hooks/scripts/vault_profiles.py`
changed only in a
comment - two client names in the reference-machine list were anonymized (`claude-anew-thd-codegraph`
-> `claude-anew-acme-codegraph`, `claude-anew-theselectsource` -> `claude-anew-acme-select`) - and
this note makes no claim that names or depends on those strings, so nothing here needed
correction.
The regression suite was re-run rather than assumed: still 65 passed, 0 failed.

**Re-anchored `ea8a014` -> `84976536` on 2026-09-22. Narrow pass on the Python, re-derivation of
the wrappers.** The per-path check over this note's cited paths:

```
git diff --name-only ea8a014..HEAD -- .claude-plugin/marketplace.json plugin/crew/hooks/hooks.json \
  plugin/obsidian-vault/agents/gardener.md plugin/obsidian-vault/agents/reflector.md \
  plugin/obsidian-vault/.claude-plugin/plugin.json plugin/obsidian-vault/hooks/hooks.json \
  plugin/obsidian-vault/hooks/scripts/bridge_status.py \
  plugin/obsidian-vault/hooks/scripts/obsidian_common.py \
  plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh \
  plugin/obsidian-vault/hooks/scripts/vault_capture.py \
  plugin/obsidian-vault/hooks/scripts/vault_guard.py \
  plugin/obsidian-vault/hooks/scripts/vault_ops.py \
  plugin/obsidian-vault/hooks/scripts/vault_profiles.py plugin/obsidian-vault/README.md
```
```
.claude-plugin/marketplace.json
plugin/crew/hooks/hooks.json
plugin/obsidian-vault/.claude-plugin/plugin.json
plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh
```

Every `path:line` in this note was then re-resolved mechanically at HEAD and at `ea8a014` and
compared byte-for-byte. **Two moved, both version strings** -
`plugin/obsidian-vault/.claude-plugin/plugin.json:3` (`0.3.8` -> `0.3.14`) and
`.claude-plugin/marketplace.json:242`, corrected above. Every citation into `vault_guard.py`,
`vault_capture.py`, `obsidian_common.py`, `vault_ops.py`, `bridge_status.py`,
`plugin/obsidian-vault/hooks/hooks.json` and `plugin/obsidian-vault/README.md` is byte-identical;
those files did not change at all, so the whole `## Landmines` account of the Python guard is
closed by the per-path check and **was not re-read**. `run-tests.sh` changed but grew only at its
tail (482 -> 519 lines); all six cited lines in it - `:5-6`, `:293-304`, `:314`, `:404,412,433`,
`:450`, `:475-478` - still carry the text this note quotes, checked individually rather than
offset.

**The per-path check missed the change that mattered, and the cause is a citation style this
directory already has a rule about.** `vault-guard.sh`, `vault-guard.ps1`, `bridge-status.ps1`,
`vault-capture.ps1`, `commands/graph.md`, `commands/init.md`, `commands/repair.md` and two new
`_test/` files all changed in that range and **none of them appears in the diff above**, because
this note never cited any of them in a pasteable form. The 0.3.13 interpreter defect - a guard that
exited 49 with zero bytes on stderr and checked nothing - is in a file this note had no anchor
into. `INDEX.md` states the repo-relative rule as being about *re-verification*; this is the other
half of the same failure. A path the note never cites cannot appear in its own freshness check, so
a narrow per-path diff silently measures only what the note already knows about, and returns
"clean" with the highest-value change sitting outside the query. Widening the same diff to
`plugin/obsidian-vault/` returns thirteen files instead of four.

That is why the two new Landmines above are a **re-derivation**, not a re-point: they were read
from source at this pass (`vault-guard.sh` in full, all three `.ps1` flavour guards, the new tail
of `run-tests.sh`, and `test_flavour_guard.py` by execution), and they document mechanism this
note had never covered rather than correcting something it said.

One thing this pass did **not** do, and the omission is deliberate rather than an oversight:
`vault-guard.ps1`'s own `Resolve-VaultGuardPython` was confirmed to exist and to carry the flavour
guard at `:45`, but its body was not read line by line against the `.sh` twin. The two are asserted
to be equivalent by the wrappers' own comments and by the shared regression file
`plugin/obsidian-vault/hooks/scripts/_test/test_vault_guard_sh.sh`, which the suite runs - not by a
reading done here. CLAUDE.md's "re-review the fix to a guard as hard as the guard" applies
squarely, and the `.ps1` half is the neighbouring case nobody has checked.

Also not re-verified at this pass: the two agents (`gardener.md`, `reflector.md`) and the eleven
command files are still unopened, as the `## Unverified` section above says; `vault_profiles.py`
internals are still inferred from its tests; nothing touched a live vault, a live bridge port or
`~/.claude/obsidian/config.json`. No `.md` or `SKILL.md` prose was read, so whether any of it
contradicts the code remains unknown.

## Re-anchor provenance — 84976536 -> 2b337296, 2026-09-22

Re-anchor only. The per-path check over this note's cited paths (listed in
the `ea8a014 -> 84976536` provenance section above) returns empty against
`2b337296` for every `plugin/obsidian-vault/` path. Outside this note's own
cited paths, the whole-repo diff (`git diff --name-only 84976536..2b337296`)
also lists `.claude-plugin/marketplace.json` (doc-builder's version only —
re-diffed to confirm the `obsidian-vault` block this note cites at `:248` is
untouched), `CHANGELOG.md`, `README.md`, three `docs/diagrams/*.mmd` files,
`graphify-out/*`, two `skills/doc-builder/*` files, and eight
`.crew/codemap/*.md` files (concurrent re-anchor edits by this and other
sessions — not code, and not cited by this note). None of the above is a
`plugin/obsidian-vault/` path or otherwise cited here.

Grepped for `CHANGELOG.md:<n>` and `README.md:<n>`: **neither appears in this
note.** Nothing was re-read.
