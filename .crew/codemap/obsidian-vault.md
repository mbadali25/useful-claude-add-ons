# obsidian-vault
anchor: useful-claude-add-ons@8b8a4028
verified: 2026-09-23

## Does
Turns one or more Obsidian vaults into Claude Code's durable memory: a PostToolUse guard that
holds notes to a contract, a SessionEnd/PreCompact capture hook that queues sessions for later
distillation, gardener and reflector agents that turn that queue into notes, and per-vault MCP
registration against Obsidian's Local REST API bridge. (DERIVED:
`plugin/obsidian-vault/hooks/hooks.json:3-20`, `plugin/obsidian-vault/agents/`,
`plugin/obsidian-vault/hooks/scripts/vault_ops.py:1059-1089`.)

**The guard does not block a write.** It is registered on PostToolUse
(`plugin/obsidian-vault/hooks/hooks.json:7-12`), which fires *after* the file is on disk - the
guard even re-reads it from disk at `plugin/obsidian-vault/hooks/scripts/vault_guard.py:321-322`.
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
- `plugin/obsidian-vault/hooks/scripts/vault_guard.py:229-357` - `main()`, the PostToolUse guard,
  fired on Edit/Write/MultiEdit. Reads its config toggles at `:301-306`; early-returns 0 at
  `:308-309` when all three are off. `main()` grew from 69 to 129 lines between anchors: the stdin
  read and JSON parse that used to be one bare `json.load(sys.stdin)` inside a two-line
  `try/except Exception: return 0` are now a decode-then-parse pair, each with its own failure
  message - see Landmines. (DERIVED, ranges by `ast.parse`.)
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
  default OFF (`is True` tests at `plugin/obsidian-vault/hooks/scripts/vault_guard.py:301-302`);
  `checkCanvas` defaults ON, via an `is not False` test at `:303`. Assuming all three share a
  default is the easy mistake, and it inverts which rules a fresh install enforces. All three
  defaults are pinned by cases in the suite (`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:405,413,434`).
  (DERIVED.)
- **The guard only ever sees the DEFAULT vault.** `main()` calls
  `obsidian_common.resolve_vault_path()` with no name
  (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:295`), and `resolve_vault_path()` with
  `name=None` resolves the default entry
  (`plugin/obsidian-vault/hooks/scripts/obsidian_common.py:286-294` ->
  `:256-283`). Every edit to a second configured vault - the codegraphs vault, say - passes
  unchecked. `plugin/obsidian-vault/README.md:46-49` states this is deliberate. (DERIVED.)
- **`.base` files reach no structural check.** The extension filter admits `.md`, `.canvas` and
  `.base` (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:318`), but the dispatch below it is
  `if ext == ".md" and require_fm: ... elif ext == ".canvas" and check_canvas_shape:` (`:329-335`).
  A `.base` therefore only ever gets `check_ascii`, and only when `asciiOnly` is on. No case in the
  suite exercises a `.base` at all. (DERIVED; grep for `\.base` over
  `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh` returns nothing.)
- **Two differently-sized exemption sets, 20 lines apart.** `CLAUDE.md`, `README.md`, `AGENTS.md`
  and `GEMINI.md` are exempt from *requiring frontmatter*
  (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:59`); only `CLAUDE.md` is also ASCII-exempt
  (`:39`). Widening one while reading the other is how an exemption silently grows. Each of the
  three ASCII-checked names is pinned individually, after a Codex round found that testing
  `README.md` alone let a narrowing of `ASCII_EXEMPT_NAMES` pass the whole suite
  (`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:294-305`). (DERIVED.)
- **The frontmatter exemption is one check wide, not the whole function.** `fm_optional` excuses an
  exempt basename from *having* frontmatter and nothing else: a `README.md` that does carry
  frontmatter is still held to required keys, title-matches-filename and the updated date
  (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:163-178`). An earlier implementation skipped
  `check_note` entirely; the comment beside it still claimed "frontmatter-only". (DERIVED.)
- **`notesPrefix` scopes the note contract only** - not the ASCII check and not the canvas check.
  `notes_glob` is passed to `check_note` alone
  (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:329-333`); `check_ascii` (`:328`) and
  `check_canvas` (`:334-335`) never receive it. The note half of that is pinned
  (`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:451`) and the ASCII half is pinned by
  the `wiki/ascii/CLAUDE.md` case (`:315`). **The canvas half is not pinned:** all four canvas
  cases live under `wiki/canvases/`, which is inside the `wiki/` prefix the ON config sets, so
  adding prefix-gating to `check_canvas` would pass the suite unnoticed. (DERIVED for the code;
  JUDGEMENT that this is the next gap worth closing.)
- The guard reads file content from disk rather than from the hook payload
  (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:321-322`). Only the ASCII check prefers the
  newly introduced text (`written_text`, `:93-103`), and it falls back to the full on-disk text
  when the payload carried no new string: `added if added is not None else text` (`:328`).
  `check_note` and `check_canvas` always see the whole file. (DERIVED; the fallback clause was not
  stated in the previous version of this note.)
- **A malformed or undecodable hook payload used to fail silently; as of PR #210 it fails loudly.**
  Until this pass `main()` opened with a bare `payload = json.load(sys.stdin)` inside
  `try/except Exception: return 0` - any read or parse failure returned 0 with nothing on stderr,
  the same "unknown collapsing into the safe-looking value" shape CLAUDE.md names for the
  interpreter-resolver defect below. `main()` (now `plugin/obsidian-vault/hooks/scripts/vault_guard.py:229-357`)
  splits this into two stages, each writing an explicit `"... NOT checked: ..."` message to stderr
  before returning 0: a raw-bytes stdin read (`:230-236`) and a decode-then-parse step
  (`:274-293`) that decodes with `errors="surrogateescape"` rather than the strict default
  (`:275`), so an invalid byte survives as a synthetic codepoint `check_ascii` still catches
  instead of raising and being swallowed by a bare `except`. The decode is explicit UTF-8, not
  `sys.stdin`'s own locale-dependent default - the comment at `:238-247` and `:249-264` notes
  that this only matters when nothing more specific (`PYTHONIOENCODING`, or the wrapper's own
  `PYTHONUTF8=1` backstop, below) already forced UTF-8. The MEASUREMENT is recorded elsewhere -
  `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:140-150` and
  `plugin/obsidian-vault/hooks/scripts/_test/test_vault_guard_sh.sh:358-363` - where the guard's own
  regression suite measured `PYTHONIOENCODING` as taking precedence OVER `PYTHONUTF8` when both are set - so the
  wrapper backstop cannot rescue a decode an explicit `PYTHONIOENCODING` in the calling environment
  has already corrupted. (DERIVED, and sabotage-tested: `_test/test_vault_guard_sh.sh`'s
  non-ASCII round-trip section calls `vault_guard.py` directly under a forced
  `PYTHONIOENCODING=cp1252`, then reverts the decode fix on a throwaway copy and confirms the case
  goes red - see that file's own comments on why it sandboxes a copy rather than editing the
  tracked file in place.)
  Both wrappers now also `export`/set `PYTHONUTF8=1` before invoking the interpreter -
  `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:151` and
  `plugin/obsidian-vault/hooks/scripts/vault-guard.ps1:176` - as a backstop for everything else
  python does under the process's default encoding (stdout/stderr text, not the stdin decode
  above, which never consults it). Its own comment states the narrower, measured scope rather than
  the wider claim a first draft made. (DERIVED.)
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
  - **It was deliberately stricter than crew's copy of the same resolver, and as of 5d1fc5fd that
    gap has narrowed.** `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:89-94` still carries the
    comment "deliberately stricter than crew's copy, which accepts any non-empty stdout on a zero
    exit" — that comment is unchanged (`vault-guard.sh` does not appear in the
    `2b337296..5d1fc5fd` diff at all) but it now describes `role-write-guard.sh` inaccurately.
    Crew's resolver (`plugin/crew/hooks/scripts/role-write-guard.sh:32-113`, was `:32-57` at the
    previous anchor — the function grew from 26 lines to 82) no longer merely accepts non-empty
    stdout: it strips a trailing CR (`:47`), converts a native Windows `sys.executable` path to a
    form this shell can stat via `cygpath -u` or a hand-written fallback (`:84-94`), and then
    requires `[ -x "$real" ]` (`:105`) — the printed path must exist and be executable, not just be
    non-empty. That closes part of the "shim that prints a line and exits 0" gap this note
    previously credited only to `vault-guard.sh`: such a shim now has to print a path to a real,
    executable file to get past crew's resolver too, not merely print any line.
    **The two resolvers are not equivalent, though.** `vault-guard.sh` proves the candidate is
    actually python by requiring the exact chosen token prefix
    (`vault-guard-python:`, `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:95-103`) in the
    probe's stdout; `role-write-guard.sh` has no such token and would accept any program that, when
    run with `-c 'import sys; print(sys.executable)'`, happens to exit 0 and print a path to a real
    executable file — a non-python interpreter that ignores or errors quietly on that flag and
    prints something else executable would still pass. That remaining difference is DERIVED from
    reading both files at this anchor, not carried over from the previous version of this note,
    which asserted the older, coarser gap. (DERIVED.)
  - **It is copied, not imported** (`:45-56`): crew and obsidian-vault are separate marketplace
    entries, `${CLAUDE_PLUGIN_ROOT}` points at one plugin, and a host with obsidian-vault and no
    crew is the ordinary case, so there is no path this script could source. **The reason this note
    previously gave for declining a shared copy no longer holds, and the source comment that gives
    it is now stale.** As of PR #210, `bridge-status.sh` and `vault-capture.sh` (and their `.ps1`
    twins) no longer carry the naive `command -v python3 || ...` one-liner this comment describes
    them as still carrying - each now has its own independently-copied proven-interpreter resolver
    (`_bridge_status_resolve_python`, `_vault_capture_resolve_python`, and the PowerShell
    equivalents), so all three hooks this plugin registers get the WindowsApps-alias defence, not
    just the one that can block. The comment at `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:45-56`
    itself is unchanged text (untouched in the `5d1fc5fd..60c79407` diff) that now misstates why a
    shared copy was declined; correcting the source is out of scope for this note - reported
    separately as a decision for scribe. (DERIVED that the four other wrappers were upgraded; the
    "why still not shared" question is now open rather than settled by the stale comment -
    JUDGEMENT.)
  - **`exec` was removed** (`:153-167`, moved from `:132-147` by the `export PYTHONUTF8=1` insert
    above it - see the new Landmines bullet). `vault_guard.py` exits 0 or 2 and nothing else, so any
    other status means it never reached a verdict; under `exec` that landed as a bare numeric exit,
    which is the silent shape the whole script exists to avoid. It now runs the interpreter as a
    child, and a status that is neither 0 nor 2 prints "this write was NOT checked" and stands down
    at exit 0.
  Pinned by `plugin/obsidian-vault/hooks/scripts/_test/test_vault_guard_sh.sh` (grown from 372 to
  652 lines this pass - see "Measured this pass"), run from the main suite as one folded case at
  `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:513`.
  **The stub is MODELLED, not observed** - built on Linux from the alias's documented behaviour
  (`plugin/obsidian-vault/hooks/scripts/vault-guard.sh:35-37` says so). The *shape* of the failure
  is verified; the Windows fixture behind it is not, and nobody has reproduced this on a real
  WindowsApps machine. (DERIVED, including the limitation - it is the script's own admission, not
  an inference.)
- **Both PowerShell flavours no longer run on one host.** `hooks.json` registers every event twice,
  once per flavour, so on a machine with bash *and* `pwsh` both halves of each pair would fire
  unless the `.ps1` stands down off Windows. All three `.ps1` wrappers now open with
  `if ($env:OS -ne 'Windows_NT') { exit 0 }` -
  `plugin/obsidian-vault/hooks/scripts/bridge-status.ps1:19`,
  `plugin/obsidian-vault/hooks/scripts/vault-capture.ps1:24`,
  `plugin/obsidian-vault/hooks/scripts/vault-guard.ps1:45`. (DERIVED - the first two moved when
  PR #210 added a header comment ahead of the flavour guard in each file; `vault-guard.ps1`'s
  own flavour-guard line did not move.)
  **`$env:OS`, not `$IsWindows`** - and the comment at
  `plugin/obsidian-vault/hooks/scripts/bridge-status.ps1:14-18` records why: `$IsWindows` does not
  exist in PowerShell 5.1, so a bare `if (-not $IsWindows)` is truthy there and stands the hook
  down on the one platform it exists for. crew shipped that inversion once already.
  The pin derives its file list from `hooks.json` itself
  (`plugin/obsidian-vault/hooks/scripts/_test/test_flavour_guard.py`), so registering a new hook
  with no guard turns it red without anyone editing the test - which is the difference between a
  regression test and a list that goes stale. (DERIVED.)
- The regression suite is `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh`, sabotage-tested
  per its own header (`:5-6`), with must-block and must-allow sections and four Python suites
  (`:476-479`). A change to any rule above needs a must-block and a must-allow case here before it
  ships - this repo's rule for a hook that can block. (DERIVED - all four citations in this bullet
  moved by one line versus the previous anchor: `SKIP=0` was added near the top of the file, at
  line 29, shifting every line below it by exactly one.)
- **A PowerShell legacy-argument-passing bug rejected every real interpreter, in the opposite
  direction from the WindowsApps defect above - fail-open-by-standing-down rather than fail-open-
  by-running-a-stub, but still silent about why.** `vault-guard.ps1` - the only `.ps1` wrapper that HAD
  an interpreter probe at the previous anchor (`bridge-status.ps1` and `vault-capture.ps1` used a
  bare `Get-Command python3, python, py` with no probe, per the naive-one-liner bullet above) -
  used to pass its `-c` program double-quoted:
  `-c 'import sys; sys.stdout.write("vault-guard-python:" + sys.executable)'`. Under
  `$PSNativeCommandArgumentPassing = 'Legacy'` - the default on Windows PowerShell 5.1 and on pwsh
  <=7.2 - PowerShell reconstructs native-command arguments itself and silently strips embedded
  double quotes before the child process ever sees them, so python received
  `sys.stdout.write(vault-guard-python: + sys.executable)`, a `SyntaxError`, exit 1, and every real
  interpreter on the machine was rejected as "ran, but did not answer the interpreter probe" - the
  same stand-down message a genuinely broken shim earns. Fixed by single-quoting the python string
  literal, escaped for PowerShell's own single-quoted outer argument as `''...''`
  (`plugin/obsidian-vault/hooks/scripts/vault-guard.ps1:109`); the probes the other two wrappers
  GAINED in the same change were written that way from the start
  (`plugin/obsidian-vault/hooks/scripts/bridge-status.ps1:60`,
  `plugin/obsidian-vault/hooks/scripts/vault-capture.ps1:65`), which has nothing left for legacy reconstruction to strip. Reproduced without a Windows
  machine by explicitly setting `$PSNativeCommandArgumentPassing = 'Legacy'` under `pwsh` on Linux,
  and pinned in the new `plugin/obsidian-vault/hooks/scripts/_test/test_ps1_legacy_args.sh`
  (188 lines), run from the main suite at `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:516-517`. **Like the WindowsApps stub, this
  reproduction is MODELLED under a forced setting, not observed on a real legacy-mode Windows
  PowerShell 5.1 host** - the script's own header says so. (DERIVED.)
- **`bridge-status.sh`/`.ps1` and `vault-capture.sh`/`.ps1` now carry their own proven-interpreter
  resolvers, closing the gap the previous version of this note flagged as open risk.** Each is an
  independently-copied near-twin of `vault-guard.sh`'s `_vault_guard_resolve_python` (bash) or
  `vault-guard.ps1`'s `Resolve-VaultGuardPython` (PowerShell) - own name, own rejection-token
  prefix (`bridge-status-python:`, `vault-capture-python:`), same WindowsApps-alias rejection and
  probe-and-verify shape. Both hooks still cannot block (SessionStart and SessionEnd/PreCompact
  have no exit code that stops anything), so the fail-open behaviour is unchanged - what changed is
  that a bad interpreter now says so on stderr instead of silently running a Store stub or a shim.
  Pinned by the new `plugin/obsidian-vault/hooks/scripts/_test/test_bridge_capture_sh.sh`
  (350 lines), whose own header states it is closing exactly the gap this note used to name: "the
  two remaining naive wrappers ... still carry the naive one-liner". Run from the main suite at
  `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:514-515`. (DERIVED.)

## Measured this pass
- `env -u MSYS_NO_PATHCONV bash plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh` re-run at
  `60c79407`, on **Linux**, checkout
  `/repos/personal/useful-claude-add-ons/.claude/worktrees/agent-a13e59fa14639e19c`, branch
  `codemap/obsidian-vault-refresh`: **RESULT: 69 passed, 0 failed, 0 skipped.** (DERIVED - run, not
  inferred. The ref and the platform are stated because a count without them can only be believed:
  the previous `67 passed, 0 failed` recorded here was taken on Linux at `84976536`, before PR #210
  added the `SKIP` counter, two new sub-suites, and the `PYTHONUTF8=1` decode backstop.)
  `RESULT` itself changed shape this pass - `"$PASS passed, $FAIL failed"` became
  `"$PASS passed, $FAIL failed, $SKIP skipped"` (`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:535`), and `sh_suite` (`:488-511`)
  now also greps each sub-suite's own output for `SKIP:` lines and folds their count in
  (`:498-502`) rather than discarding that output silently on a clean exit, which is what the
  previous version of this note's "67 is not the number every machine sees" paragraph was working
  around. There are now three `sh_suite` sub-suites, not one:
  `test_vault_guard_sh.sh` (`:513`, grown to 652 lines this pass), the new
  `test_bridge_capture_sh.sh` (`:514-515`, 350 lines) and the new `test_ps1_legacy_args.sh`
  (`:516-517`, 188 lines), plus the PowerShell flavour guard at `:519-533`. **All ran behaviourally
  here**, because `pwsh` is on PATH at `/snap/bin/pwsh` (confirmed by `SKIP=0` in the result line,
  not just by `pwsh`'s presence on PATH - the two came apart before, see the codemap lesson on
  running states rather than reasoning about them). The no-`pwsh` count from the previous anchor
  (`66 passed, 1 skip`, pre-dating the three-way `sh_suite` split and the new `SKIP` counter) was
  **not re-measured this pass** - re-running it needs `pwsh` actually absent from PATH, not merely
  reasoned about, and that was not done here.
- Plugin version is `0.3.16` in both places that must agree:
  `plugin/obsidian-vault/.claude-plugin/plugin.json:3` and the `obsidian-vault` entry in
  `.claude-plugin/marketplace.json:248`. (DERIVED - `0.3.14` -> `0.3.16` between anchors; both
  places still agree, checked byte-for-byte against `git diff 5d1fc5fd..60c79407`, not offset.)

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

## Re-anchor provenance — 2b337296 -> 5d1fc5fd, 2026-09-22

**Correction, not a bare re-anchor.** Per-path check over this note's cited
paths (extracted the same way `_cited_paths` in
`plugin/crew/hooks/scripts/crew_freshness.py` would - every backtick-quoted
repo-relative path in this file that still exists):

```
git diff --name-only 2b337296..5d1fc5fd -- \
  plugin/crew/hooks/hooks.json plugin/obsidian-vault/hooks/scripts/bridge_status.py \
  plugin/obsidian-vault/hooks/scripts/vault_capture.py plugin/obsidian-vault/hooks/scripts/vault_guard.py \
  plugin/obsidian-vault/hooks/scripts/vault_ops.py plugin/obsidian-vault/README.md \
  plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh CLAUDE.md README.md AGENTS.md \
  plugin/obsidian-vault/hooks/scripts/vault-guard.sh plugin/obsidian-vault/hooks/scripts/_test/test_vault_guard_sh.sh \
  plugin/obsidian-vault/hooks/scripts/bridge-status.ps1 plugin/obsidian-vault/hooks/scripts/vault-capture.ps1 \
  plugin/obsidian-vault/hooks/scripts/vault-guard.ps1 plugin/obsidian-vault/hooks/scripts/_test/test_flavour_guard.py \
  plugin/obsidian-vault/.claude-plugin/plugin.json plugin/obsidian-vault/agents/gardener.md \
  plugin/obsidian-vault/agents/reflector.md plugin/obsidian-vault/hooks/scripts/vault_profiles.py \
  plugin/obsidian-vault/hooks/hooks.json CHANGELOG.md
```
```
CHANGELOG.md
CLAUDE.md
```

Two files, neither with a `path:line` citation into it from this note (grepped
`CHANGELOG.md:<n>` and `CLAUDE.md:<n>` - neither appears here), so nothing in
either changed file's diff could move a claim this note makes about it.

**This diff alone missed the one change that mattered, for the exact reason
the `ea8a014 -> 84976536` section above already names: a path the extraction
regex does not capture cannot appear in its own freshness check.** Two of this
note's citations are in that shape, for two different reasons, and neither is
in the diff above: `.claude-plugin/marketplace.json:248` (`_CITED_PATH_RE`'s
path body starts `[A-Za-z0-9_]`, so a leading `.` is never matched - this is a
gap in the regex, not a case it handles) and
`plugin/crew/hooks/scripts/role-write-guard.sh:32-57` (a *range* citation;
the regex's optional suffix is `:\d+` alone, not `:\d+-\d+`, immediately
before the closing backtick, so this one is never extracted either). Checking
only the regex-extracted paths and the whole `plugin/obsidian-vault/` tree
said "clean"; the miss was outside both, and finding it required diffing
these two citations by hand rather than trusting the mechanical check.

`git diff --name-only 2b337296..5d1fc5fd -- .claude-plugin/marketplace.json
plugin/crew/hooks/scripts/role-write-guard.sh` returns both files. The
marketplace citation still holds: `.claude-plugin/marketplace.json:248` is
still the `obsidian-vault` entry, still version `0.3.14`, byte-identical at
both commits (`git diff 2b337296..5d1fc5fd -- .claude-plugin/marketplace.json`
is a single hunk, the `crew` entry - description rewrite, 27→28 slash commands
and 19→20 skills, plus version `0.20.10`→`0.20.11`; nowhere near `:248`. The
`doc-builder` bump this note mentions above belongs to the earlier
`84976536 -> 2b337296` range, not this one - confirmed by reading the diff,
not assumed).

**`role-write-guard.sh` did move, and the claim built on it was wrong at
HEAD.** The bullet under `## Landmines` said crew's resolver "accepts any
non-empty stdout on a zero exit" - true at `2b337296`, false at `5d1fc5fd`:
the function (now `:32-113`, was `:32-57` - it grew from 26 to 82 lines) added
a trailing-CR strip, a Windows-path-to-POSIX-path conversion, and an
`[ -x "$real" ]` executable check (`:105`) that the old text did not have and
did not need. **Corrected in place above**, `was` -> new text, with the
narrower difference that remains (crew's resolver still has no token-probe
proof that the candidate is actually python, unlike `vault-guard.sh`'s
`vault-guard-python:` prefix check). The
`plugin/obsidian-vault/hooks/scripts/vault-guard.sh:89-94` comment this
note also cites is unchanged text (the file itself is untouched in this
range) that now describes the other script inaccurately; that is a fact about
`vault-guard.sh`'s own comment, out of scope to fix here since this note may
only correct its own text, not the source it cites - reported separately as a
decision for scribe.

Every other citation in this note resolves into the empty first diff above
(no `plugin/obsidian-vault/` file, `CLAUDE.md`, `README.md`, `AGENTS.md`, or
`plugin/crew/hooks/hooks.json` moved), so nothing else was re-read at this
pass.

Not re-verified at this pass: the regression suite was not re-run (last run
recorded above is 67 passed, 0 failed at `84976536`, still the most recent
execution on record); the two agents and eleven command files remain unopened;
`vault_profiles.py` internals are still inferred from its tests; nothing
touched a live vault, a live bridge port, or `~/.claude/obsidian/config.json`.

## Re-anchor provenance — 5d1fc5fd -> 60c79407, 2026-09-22 (PR #210, "Windows audit wave 3")

`git diff 5d1fc5fd..60c79407 -- plugin/obsidian-vault` (the whole plugin tree, not just this
note's prior citations - the `ea8a014 -> 84976536` and `2b337296 -> 5d1fc5fd` sections above both
found that a narrow per-path diff misses a change this note never had an anchor into, so this pass
started wide instead):

```
plugin/obsidian-vault/.claude-plugin/plugin.json
plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh
plugin/obsidian-vault/hooks/scripts/_test/test_bridge_capture_sh.sh   (new, 350 lines)
plugin/obsidian-vault/hooks/scripts/_test/test_ps1_legacy_args.sh     (new, 188 lines)
plugin/obsidian-vault/hooks/scripts/_test/test_vault_guard_sh.sh
plugin/obsidian-vault/hooks/scripts/bridge-status.ps1
plugin/obsidian-vault/hooks/scripts/bridge-status.sh
plugin/obsidian-vault/hooks/scripts/vault-capture.ps1
plugin/obsidian-vault/hooks/scripts/vault-capture.sh
plugin/obsidian-vault/hooks/scripts/vault-guard.ps1
plugin/obsidian-vault/hooks/scripts/vault-guard.sh
plugin/obsidian-vault/hooks/scripts/vault_guard.py
```

Twelve files, every one of them re-read in full or diffed line-by-line against `5d1fc5fd` this
pass (not the whole-directory grep-and-hope the two previous re-anchors warn against). The
`.claude-plugin/marketplace.json` version bump (`0.3.14` -> `0.3.16` at `:248`, same line) was
caught separately, the same way the `2b337296 -> 5d1fc5fd` pass caught it - `:248` starts with `.`,
so it is outside every regex this note has ever used to auto-extract its own citations, and has to
be checked by hand each time.

**Every `path:line` and `path:range` citation in this note that pointed into one of the twelve
files above was re-resolved against the new content and corrected above where it moved; none was
left un-checked.** The shifts fall into two causes, both mechanical rather than semantic:

- `vault_guard.py`'s `main()` gained a two-stage, loudly-failing stdin read/decode/parse in place
  of a single bare `json.load(sys.stdin)` inside a silent `except Exception: return 0` - every line
  number from `:235` onward inside `main()` moved by 60 lines (`main()` grew from 69 to 129 lines).
  Nothing before line 228 moved; every citation into `check_note`, `check_canvas`,
  `written_text`, the exemption-name lists, and the module docstring is unaffected.
- `run-tests.sh` gained one line (`SKIP=0`) near its top (line 29), shifting every citation below
  it by exactly one, and gained two new `sh_suite` calls plus a widened flavour-guard block near
  its tail, shifting everything from `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:513` on by more. Both effects were checked by
  grepping for the cited text itself and reading off its new line number, not by assuming a
  constant offset - the `+1` shift and the tail rewrite do not compose predictably from one number.

**New mechanism this pass added, not previously covered by this note:** `vault-guard.sh` and
`vault-guard.ps1` now export/set `PYTHONUTF8=1` before invoking the interpreter, as a backstop for
everything except the stdin decode itself (which is explicit UTF-8 and never consults it);
`bridge-status.sh`/`.ps1` and `vault-capture.sh`/`.ps1` gained their own independently-copied
proven-interpreter resolvers, closing the "two remaining naive wrappers" gap this note's Landmines
section previously named as open JUDGEMENT risk; and `vault-guard.ps1`'s interpreter probe was fixed for a
`$PSNativeCommandArgumentPassing = 'Legacy'` double-quote-stripping bug that rejected every real
interpreter under Windows PowerShell 5.1 and pwsh <=7.2 (the two new probes never had it). All three are
documented in `## Landmines` above, each anchored to the code and, where the plugin's own suite
covers it, to the regression case.

**Correction, not just an addition: stale source comments are flagged rather than silently
updated.** The `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:45-56` comment this note cites (unchanged text at this pass) still
justifies declining a shared resolver by saying `bridge-status.sh` and `vault-capture.sh` "carry
the same naive one-liner" - false as of this commit, for the same reason the `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:89-94`
comment about `role-write-guard.sh` was already flagged stale at the previous anchor. These, and the others below, are
facts about source comments this note may correct its own text against but not rewrite; every
one found is reported here for scribe:

- `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:45-56` - says `bridge-status.sh` and
  `vault-capture.sh` "carry the same naive one-liner"; false since PR #210.
- `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:89-94` - the `role-write-guard.sh` remark,
  stale since the previous anchor.
- `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:9` and
  `plugin/obsidian-vault/hooks/scripts/vault-guard.ps1:9` - both cite `vault_guard.py:243` for the
  checkCanvas default; that line is now inside a comment and the check is at
  `plugin/obsidian-vault/hooks/scripts/vault_guard.py:303`. Missed by this pass's first sweep and
  caught on review. A third copy of the same stale citation is at
  `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:49` (caught on the second review).
- `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:42` and
  `plugin/obsidian-vault/hooks/scripts/vault-guard.ps1:53` cite crew's resolver as
  `plugin/crew/hooks/scripts/role-write-guard.sh:32-57`; it now spans `:32-113`.
- `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:159` cites crew's exit-status closure as
  `plugin/crew/hooks/scripts/role-write-guard.sh:105-126`; those lines are now the resolver's tail
  and `_role_write_is_restricted`, and the status capture and its handling start at `:159`.
- `plugin/obsidian-vault/hooks/scripts/bridge_status.py:54` says its claim-file pattern mirrors
  "platform-sync.py" in crew; no such file has ever existed (crew has `platform-sync.sh`/`.ps1`,
  and the claim logic is in `plugin/crew/hooks/scripts/crew_platform.py`).
- `plugin/obsidian-vault/hooks/scripts/bridge_status.py:439` prints its error as coming from
  "bridge-status.py"; the file is `bridge_status.py` (the `-` form is the `.sh`/`.ps1` wrappers).

How "every one" was established, so the next pass can repeat it rather than trust it: every
`path:line` in the plugin's `.py`/`.sh`/`.ps1` was checked against the cited file, and every bare
`*.py|*.sh|*.ps1` name was checked for existence with `git ls-files`. The names that exist
nowhere and are NOT listed above are deliberate: two provenance notes naming a personal
`~/.claude/hooks/` original (`bridge_status.py:4`, `vault_guard.py:4`) and the test suites' own
throwaway sandbox/sabotage copies.

The regression suite was re-run (`env -u MSYS_NO_PATHCONV bash run-tests.sh`, see
"Measured this pass" above): **69 passed, 0 failed, 0 skipped**, with `pwsh` present. The no-`pwsh`
count was not re-measured this pass - see the caveat there.

Not re-verified at this pass: the two agents, the eleven command files, and the three skills remain
unopened; `vault_profiles.py`, `obsidian_common.py`, `vault_ops.py`, `bridge_status.py` and
`vault_capture.py` internals are unaffected by this diff and were not re-read (confirmed absent
from the twelve-file list above, not assumed); nothing touched a live vault, a live bridge port, or
`~/.claude/obsidian/config.json`; the `.ps1` twins' bodies were read in full this pass (unlike the
previous anchor, which explicitly declined to), but still only against their own `.sh` twins and
this note's claims about them, not against a real Windows host.

## Re-anchor provenance - 60c79407 -> 8b8a4028
`git diff --name-only 60c79407..8b8a4028 -- <paths this note cites>`, run 2026-09-23. Version-string-only changes to `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md` and `plugin.json` files, and edits to other `.crew/codemap/` notes, were set aside. Substantive changes: none. Current despite the lag; no claim re-read.
