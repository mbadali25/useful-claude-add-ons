# obsidian-vault
anchor: useful-claude-add-ons@17dc6d23
verified: 2026-10-01

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
- `plugin/obsidian-vault/hooks/scripts/vault_ops.py:1074-1103` - `register_commands`, builds the
  `claude mcp add` invocation per vault. Driven by `/obsidian-vault:install` and `:init`. (Was
  `:1059-1089`; re-numbered by crew 1.0-era insertions earlier in the file - see the 2026-09-25
  re-anchor below. Content unchanged.) (DERIVED, range by `ast.parse`.)
- `plugin/obsidian-vault/hooks/scripts/obsidian_common.py:321-329` - `resolve_vault_path`, the
  READ entry point every hook except capture/import/gardening uses to answer "which vault am I
  acting on" (was `:286-294`, re-numbered - see below). **It is no longer the only resolver.**
  `writer_vault()` (`plugin/obsidian-vault/hooks/scripts/obsidian_common.py:332-389`, new this pass)
  is the WRITE entry point: capture, import, ack and the gardener call it instead, because
  `resolve_vault_path` silently promotes a survivor when the configured default is unmounted, which
  is right for a reader and wrong for a writer (own docstring, `:333-339`). (DERIVED.)
- `plugin/obsidian-vault/hooks/scripts/bridge_status.py:385` — module entry point (`main()`), from the graph
- `plugin/obsidian-vault/hooks/scripts/vault_capture.py:85` — `main()` (was cited as `:35` for the
  module; `main()` itself starts at `:85`, re-confirmed this pass since capture's body changed
  substantially - see Landmines)
- `plugin/obsidian-vault/hooks/scripts/vault_guard.py:229` — module entry point (`main()`), from the graph
  (file byte-identical to the previous anchor - not re-read this pass beyond confirming the diff is
  empty)
- `plugin/obsidian-vault/hooks/scripts/vault_ops.py:1841` — `main()` (was `:1821`, re-numbered - see
  below). `build_parser()` (`:1749-1839`) now also calls
  `vault_setup.add_parsers(sub)`, `vault_import.add_parsers(sub)`, `vault_recall.add_parsers(sub)`
  and `vault_garden.add_parsers(sub)` (`:1833-1836`), so `vault_ops.py` stays the single CLI entry
  point while the setup/import/recall/garden subcommands live in their own new modules. (DERIVED.)
- `plugin/obsidian-vault/hooks/scripts/vault_setup.py:428` - `add_parsers`, registers
  `detect-obsidian`, `install-obsidian`, `create-vault`, `adopt` (new module this pass; module
  docstring at `:1-20`). (DERIVED, not read beyond the docstring and this signature - see Unverified.)
- `plugin/obsidian-vault/hooks/scripts/vault_import.py:330` - `add_parsers`, registers `import` (new
  module this pass; module docstring at `:1-20`). (DERIVED, not read beyond the docstring - see
  Unverified.)
- `plugin/obsidian-vault/hooks/scripts/vault_recall.py:222` - `add_parsers`, registers `recall` - "the
  contract crew's context hook calls" per its own module docstring (`:1`), read-only, no network, no
  bridge, no writes, no cache (new module this pass). (DERIVED, not read beyond the docstring - see
  Unverified.)
- `plugin/obsidian-vault/hooks/scripts/vault_garden.py:1095` - `add_parsers`, registers `queue`,
  `ack`, `garden-run`, `drain`, `reconcile`, `schedule` (new module this pass, 1137 lines - the
  largest of the four; module docstring at `:1-20` states per-host queue files, a legacy-file
  fallback, and hard bounds: at most 5 items and 600 seconds per run). (DERIVED, not read beyond the
  docstring and this signature - see Unverified.)

## Owns data
- The vault contents themselves, written by the gardener - outside this repo, at the path
  `resolve_vault_path` returns
  (`plugin/obsidian-vault/hooks/scripts/obsidian_common.py:321-329`, re-numbered from `:286-294`).
- **The session queue is now per-host, not one shared file.** `vault_capture.py` writes
  `inbox/pending-reflect.<host>.md` - one file PER HOST - via `inbox_path`
  (`plugin/obsidian-vault/hooks/scripts/vault_capture.py:41-42`), where `<host>` is
  `obsidian_common.host_id()` (`plugin/obsidian-vault/hooks/scripts/obsidian_common.py:105-115`:
  `OBSIDIAN_VAULT_HOST` env override, else `platform.node()`, lowercased and cleaned to
  `[a-z0-9-]`, falling back to `unknown-host` rather than producing `pending-reflect..md`). The
  legacy single `inbox/pending-reflect.md` (`legacy_inbox_path`, `plugin/obsidian-vault/hooks/scripts/vault_capture.py:37-38`)
  is no longer WRITTEN by this script, only read - for de-duplication (`already_queued`,
  `plugin/obsidian-vault/hooks/scripts/vault_capture.py:58-82`, checks both files) and as a queue the
  gardener still drains (`plugin/obsidian-vault/hooks/scripts/vault_garden.py`'s own docstring,
  `:9-14`). **This is why two machines syncing one vault no longer collide on one queue file - the
  gap this pass's per-host split closes.** (DERIVED.)
- Machine-global vault registry `~/.claude/obsidian/config.json`, named by
  `obsidian_common.config_path` (`plugin/obsidian-vault/hooks/scripts/obsidian_common.py:62-72`)
  and read by `read_config` (`:75-82`); each vault's HTTP port lives there, and - new this pass - each
  vault's `role` (`primary`, `recall` or `ignore`; `ROLES = ("primary", "recall", "ignore")` at
  `plugin/obsidian-vault/hooks/scripts/obsidian_common.py:102`). The pre-roles multi-vault example
  at `plugin/obsidian-vault/README.md:36-42` is unchanged and still has no `"role"` key (roles are
  optional, per `writer_vault`'s own fallback path); the role-bearing shape is documented separately
  at `plugin/obsidian-vault/README.md:221`: `{ "vaults": { "<name>": { "path": "...", "role": "primary|recall|ignore",
  "default": true } } }`. (DERIVED.)
- **New this pass:** an acknowledgement file per host, `inbox/reflected.<host>.md` - "every file
  here therefore has exactly one writer" per `vault_garden.py`'s own docstring
  (`plugin/obsidian-vault/hooks/scripts/vault_garden.py:12-14`); a `- [x]` check-off in the legacy
  file (the pre-this-pass gardening mechanism) also still counts as done. (DERIVED from the
  docstring, not from reading `ack`'s body - see Unverified.)

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
  defaults are pinned by cases in the suite (`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:408,413,434`).
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
  (`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:297-308`). (DERIVED.)
- **The frontmatter exemption is one check wide, not the whole function.** `fm_optional` excuses an
  exempt basename from *having* frontmatter and nothing else: a `README.md` that does carry
  frontmatter is still held to required keys, title-matches-filename and the updated date
  (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:163-178`). An earlier implementation skipped
  `check_note` entirely; the comment beside it still claimed "frontmatter-only". (DERIVED.)
- **`notesPrefix` scopes the note contract only** - not the ASCII check and not the canvas check.
  `notes_glob` is passed to `check_note` alone
  (`plugin/obsidian-vault/hooks/scripts/vault_guard.py:329-333`); `check_ascii` (`:328`) and
  `check_canvas` (`:334-335`) never receive it. The note half of that is pinned
  (`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:454`) and the ASCII half is pinned by
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
  `plugin/obsidian-vault/hooks/scripts/_test/test_vault_guard_sh.sh:361-366` - where the guard's own
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
  `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:516`.
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
  (188 lines), run from the main suite at `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:519-520`. **Like the WindowsApps stub, this
  reproduction is MODELLED under a forced setting, not observed on a real legacy-mode Windows
  PowerShell 5.1 host** - the script's own header says so. (DERIVED.)
- **Crew 1.0 retired two adjacent memory systems this note used to reference by name; both are
  gone from the marketplace.** `claude-memories-vault` and `claude-memories-canvas` no longer exist
  as skills (`.claude-plugin/marketplace.json` no longer lists either; `git show --diff-filter=D
  6c497a14 --name-status -- skills/claude-memories-vault skills/claude-memories-canvas` is empty
  because they were never tracked as files at all - they were marketplace-only entries removed in
  the same commit). `vault-automation` never existed as a path in this repo either (`git log
  --diff-filter=D --all -- '*vault-automation*'` finds nothing) - if it was a real thing, it left no
  trace under that name here, and this note does not assert it existed. What *is* still recorded,
  but not in this repo: a "Two vault systems on one host" entry describing `obsidian-vault` (this
  plugin) and a separate personal vault tooling as different systems on the same machine lives in
  the operator's untracked Claude Code auto-memory (`two-vault-systems-one-host.md`), **not** in this
  repo's `CLAUDE.md` - `git grep 'Two vault systems'` at `07ca3972` finds it in no tracked file but
  this note, and it was absent from `CLAUDE.md` at `f2bb919b` too, so the earlier wording was wrong
  when written rather than drifted. That boundary still stands; only the two named skills were
  removed. (DERIVED for the removal and the location; the "vault-automation" non-finding is a negative result, not a confirmed prior
  existence.)
- **A refused capture is now a distinct, named outcome, not a queued garbage line.** `main()`
  (`plugin/obsidian-vault/hooks/scripts/vault_capture.py:119-146`) refuses to queue anything when
  BOTH the session id and the transcript path come back unusable
  (`usable_sid is None and usable_transcript is None`, `:136`) - previously a bare `sid="?"` would
  still queue a line the gardener could never resolve to anything and could never dedupe (`sid="?"`
  never matched itself). It now says so on stderr and returns (`:143-146`) rather than writing. When
  a transcript exists but the session id does not, `transcript_key` hashes `trigger+transcript`
  (`plugin/obsidian-vault/hooks/scripts/vault_capture.py:45-55`) into a `key=` field so the SAME
  event firing twice - the `.sh`/`.ps1` twins both registered on one Windows host, or a hook that
  simply fires twice - dedupes against itself; `already_queued` (`:58-82`) checks the key against
  both the new per-host file and the legacy shared one. (DERIVED; pinned in
  `plugin/obsidian-vault/hooks/scripts/_test/test_memory_ops.py`, sabotage-tested per its own header
  - not read in depth, see Unverified.)
- **All six wrappers (three `.sh`, three `.ps1`) now share one resolver shape, not three
  independently-drifting ones.** Each walks EVERY PATH match of `python3`/`python`/`py` (bash:
  `type -aP`, `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:88-95`; PowerShell: the
  `Get-Command -All` equivalent) rather than the first match per name - crew 1.0's Windows burn-in
  found a path-rule-plus-first-match version discarded three WORKING WindowsApps aliases before
  reaching the real `python.exe` behind them. Each candidate is run and must answer a probe of the
  shape `vault-guard-python:<major>:<minor>:<impl>:<executable>` (bash:
  `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:126-128`; PowerShell:
  `plugin/obsidian-vault/hooks/scripts/vault-guard.ps1:115`), checked for Python >= 3.8, `cpython` or
  `pypy`, and a non-empty, existing `sys.executable` - a plain path with no version/impl check (the
  previous anchor's shape) accepted a Python 2 or a fake printing a missing path. (DERIVED, and
  pinned by the new `plugin/obsidian-vault/hooks/scripts/_test/test_python_probe_proof.py`, run
  standalone with `python3 hooks/scripts/_test/test_python_probe_proof.py`; its own header names
  three Codex-round-1 FAILs this closed.)
  - **An overall deadline, not just a per-candidate timeout.** Each candidate probe is bounded at
    3 seconds, but an 8-second OVERALL deadline (`_vault_guard_deadline=$((SECONDS + 8))`,
    `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:86`; PowerShell's `$deadline` `Stopwatch`
    equivalent) stops the PATH walk once spent, because several near-3s-but-under candidates
    followed by one hung one could otherwise blow past the hook's own timeout even with every
    single probe individually bounded. (DERIVED.)
  - **The probe string was rebuilt to contain no literal `%`, because it now has to survive
    `cmd.exe` - and this fix is `.ps1`-only.** The three `.sh` wrappers still build their probe with
    Python's `%`-formatting (confirmed unchanged: `plugin/obsidian-vault/hooks/scripts/vault-guard.sh:128`
    still reads `"%d:%d:%s:" % (v[0], v[1], sys.implementation.name)`) - bash never routes a
    candidate through `cmd.exe`, so the trap below does not apply to it, and
    `check_no_percent_reaches_cmd` in `test_python_probe_proof.py` only reads the three `.ps1` files
    for this reason (confirmed by re-reading that function). A `.cmd`/`.bat`-shimmed Python (a
    pyenv-win install) cannot be launched with
    `UseShellExecute=false` directly - .NET's `CreateProcess` only starts a real PE executable - so a
    `.cmd`/`.bat` candidate is routed through `cmd.exe /d /c` instead
    (`plugin/obsidian-vault/hooks/scripts/vault-guard.ps1:116-129`). `cmd.exe` expands `%...%` pairs
    in the command line before python ever sees them, and the old probe built its answer with
    Python's `'%d:%d:%s:' % (...)` formatting - three `%` that a `.cmd`-only Python always failed on.
    Rebuilt with `str(...)` and string concatenation instead (same
    `<major>:<minor>:<impl>:<executable>` output shape, zero `%`), matching how crew's own
    `Resolve-CrewPython` (`plugin/crew/hooks/scripts/role-write-guard.ps1`) already avoided the same
    trap by printing a `json.dumps(...)` line, which likewise never contains a bare `%`. Pinned by
    `check_no_percent_reaches_cmd` and `check_cmd_bat_routing_present` in
    `test_python_probe_proof.py`, which check the source statically (whether a `%` reaches `cmd.exe`
    is a fact about the string, not something the sandbox executes end to end). (DERIVED.)
  - **A timed-out probe is killed and reaped, whole tree, with its own bound.** On timeout,
    PowerShell tries `$proc.Kill($true)` (recursive kill, .NET Core 3+/PowerShell 7) and falls back
    to `taskkill /T /F /PID` on Windows PowerShell 5.1, which has no such overload
    (`plugin/obsidian-vault/hooks/scripts/vault-guard.ps1:141-151`); either way the kill is followed
    by its own bounded `WaitForExit(2000)` so a killed tree is waited on rather than left torn down
    indefinitely. Bash's twin gives the candidate its own process group (`set -m`) and a watchdog
    subshell that tries `taskkill /F /T /PID` under MSYS (via `/proc/$pid/winpid`) before falling
    back to `kill -9` on the group
    (`plugin/obsidian-vault/hooks/scripts/vault-guard.sh:126-141`). **MODELLED, not observed on
    Windows** - same caveat this note has carried for the WindowsApps stub since the previous
    anchor. (DERIVED.)
- **New this pass: vault roles (`primary`/`recall`/`ignore`) via `vault_setup.py adopt`, layered
  under three new CLI modules `vault_ops.py` now dispatches to.** `vault_setup.py`'s own docstring
  (`plugin/obsidian-vault/hooks/scripts/vault_setup.py:1-20`) states the contract: exactly one
  `primary` (receives captures and imports, also `default`); any number of `recall` (read for
  injection, never written); `ignore` (answered "no" during setup, kept in config so the question is
  not asked again, never recalled, written, or included in `--all`). `vault_ops.py`'s own `select()`
  now drops `ignore`-role vaults from `--all` (`plugin/obsidian-vault/hooks/scripts/vault_ops.py:406-409`,
  new this pass). `vault_recall.py` is, per its own docstring, "the contract crew's context hook
  calls" - a pure read (no network, no bridge, no writes, no cache) that scores hits by
  title/heading/body and orders results by vault priority then score, budgeted by `--max-chars`
  (`plugin/obsidian-vault/hooks/scripts/vault_recall.py:1-20`). `vault_import.py` copies notes from
  another vault or a plain Markdown folder into the primary, dry-run by default, never overwriting,
  stamping `imported_from`/`imported_at` frontmatter so a re-run is a no-op
  (`plugin/obsidian-vault/hooks/scripts/vault_import.py:1-20`). None of these four modules' internals
  were read past the module docstring and `add_parsers` signature - see Unverified. (DERIVED.)
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
  `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:517-518`. (DERIVED.)

- **The two retired `claude-memories-*` skills' conventions did not disappear - they moved into
  this plugin as portable "profiles".** New this pass:
  `plugin/obsidian-vault/skills/obsidian-memory-contract/profiles/memory-vault.md` (78 lines) states
  in its own opening line that it "carries the conventions the `claude-memories-vault` skill
  documents for one specific vault, with that vault's paths, counts and host-local tooling taken
  out, so any primary vault can adopt them"; `profiles/canvas-maps.md` (48 lines) does the same for
  `claude-memories-canvas`. Both apply to "the `primary` vault, and any `recall` vault that says it
  follows this profile"
  (`plugin/obsidian-vault/skills/obsidian-memory-contract/profiles/memory-vault.md:9`) - tying the
  new profile mechanism to the new role
  mechanism above. Neither profile file's full body was read past its opening section - see
  Unverified. (DERIVED.)

## Measured this pass
- `env -u MSYS_NO_PATHCONV bash plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh` re-run at
  `6c497a14`, on **Linux**, checkout `/repos/personal/uca-k4`, branch `crew-refresh-k4`:
  **RESULT: 71 passed, 0 failed, 0 skipped.** `pwsh` present at `/snap/bin/pwsh`. Grew from 69 (at
  `60c79407`) to 71 exactly because `run-tests.sh` gained two new folded cases, each counting as one
  pass/fail regardless of how many assertions it makes internally: `py_suite ... test_memory_ops.py`
  (`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:483-484`) and `py_suite ... test_python_probe_proof.py`
  (`:520-521`) - confirmed by reading `run-tests.sh` itself, not inferred from the count alone.
- Previous run, kept for its own record: at `60c79407`, on **Linux**, checkout
  `/repos/personal/useful-claude-add-ons/.claude/worktrees/agent-a13e59fa14639e19c`, branch
  `codemap/obsidian-vault-refresh`: **RESULT: 69 passed, 0 failed, 0 skipped.** (DERIVED - run, not
  inferred. The ref and the platform are stated because a count without them can only be believed:
  the previous `67 passed, 0 failed` recorded here was taken on Linux at `84976536`, before PR #210
  added the `SKIP` counter, two new sub-suites, and the `PYTHONUTF8=1` decode backstop.)
  `RESULT` itself changed shape this pass - `"$PASS passed, $FAIL failed"` became
  `"$PASS passed, $FAIL failed, $SKIP skipped"` (`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:538`), and `sh_suite` (`:488-511`)
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
- Plugin version is `0.4.15` (L-0529: `_test/test_python_probe_proof.py::tools` dedupes PATH dirs by realpath and names by `lexists`) in both places that must agree:
  `plugin/obsidian-vault/.claude-plugin/plugin.json:3` and the `obsidian-vault` entry in
  `.claude-plugin/marketplace.json:234-237` (was `:248`; re-numbered by the marketplace-wide catalog
  changes in crew 1.0, including the removal of the `claude-memories-canvas` and
  `claude-memories-vault` entries above it - see Landmines). (DERIVED - `0.3.16` -> `0.4.14` -> `0.4.15` between
  anchors; both places still agree, checked byte-for-byte.)

## Unverified
- `plugin/obsidian-vault/agents/gardener.md` (modified this pass, per the whole-tree diff below) and
  `plugin/obsidian-vault/agents/reflector.md` were not opened. Their existence is confirmed by
  listing the directory; what they do is taken from the README command table and from
  `vault_capture.py`'s `HEADER` constant (`plugin/obsidian-vault/hooks/scripts/vault_capture.py:30-34`,
  re-numbered from `:24-28` by this pass's rewrite of the surrounding module docstring), not
  from reading the agents.
- Eleven command files exist under `plugin/obsidian-vault/commands/` - canvas, doctor, garden,
  graph, init, install, map, note, optimize, reflect, repair (DERIVED, directory listing).
  `commands/garden.md` and `commands/init.md` were modified this pass (whole-tree diff below); none
  of the eleven were opened. The plugin also ships three skills (`obsidian-memory-contract`,
  `obsidian-scheduling`, `obsidian-setup`); `obsidian-memory-contract/SKILL.md` and
  `obsidian-scheduling/SKILL.md` and `obsidian-setup/SKILL.md` all changed this pass; none were
  opened beyond the two new profile files noted above.
- `plugin/obsidian-vault/hooks/scripts/vault_profiles.py` internals are still inferred from its
  test file rather than read (this file did not change this pass, per the diff below).
  `bridge_status.py` has now been read at the docstring and function-boundary level (`ast.parse`),
  but no function body beyond that was read - treat any claim about its per-state wording as
  unverified.
- **New this pass, module docstring and signature only:** `vault_setup.py` (454 lines),
  `vault_import.py` (341 lines), `vault_recall.py` (231 lines), `vault_garden.py` (1137 lines - the
  largest of the four). None of the four was read past its opening docstring and `add_parsers`
  definition. Every claim this note makes about them (the role contract, the import
  never-overwrites rule, recall's read-only scope, the gardener's bounds) is taken from those
  docstrings, not from tracing the implementation, and none was executed - `test_memory_ops.py`
  (1368 lines, new this pass) is the regression suite for all four, run only as one folded case
  inside `run-tests.sh`'s 71-case total above, not read or run standalone.
- `plugin/obsidian-vault/hooks/scripts/vault_capture.py`'s new `already_queued`/`transcript_key`
  logic (documented above) was read in full and is DERIVED from the source; it was not additionally
  confirmed by running `test_memory_ops.py`'s specific dedup cases in isolation.
- Nothing in this pass touched a live vault, a live bridge port, or `~/.claude/obsidian/config.json`.
  Every guard fact above comes from reading the source or from the suite's own throwaway fixtures.
- Whether anything in a SKILL.md or command markdown *contradicts* the code above is unknown: those
  files are prose instructions to a model, not mechanism, and none were read this pass beyond the
  two new profile files.
- The bounded-reap mechanism for a timed-out interpreter probe (`Kill($true)` / `taskkill /T /F`,
  bash's process-group `kill -9`) is, like the WindowsApps stub before it, **MODELLED, not observed
  on a real Windows host** - this note repeats that caveat rather than treating the source reading
  as equivalent to a Windows run.

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
`plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:1-43,285-330,436-482`,
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
  its tail, shifting everything from `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:516` on by more. Both effects were checked by
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
  `plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh:52` (caught on the second review).
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

## Re-anchor provenance — 60c79407 -> 6c497a14, 2026-09-25 (crew 1.0, PR #225). Re-derive provenance.

**Wide diff first, as the previous three re-anchors above all learned to do.**
`git diff --name-status 60c79407..6c497a14 -- plugin/obsidian-vault/` (the whole plugin tree, not
a per-path check over this note's prior citations, for the same reason the `ea8a014 -> 84976536`
and `2b337296 -> 5d1fc5fd` sections above give: a path this note never cited cannot appear in its
own freshness check):

```
M  plugin/obsidian-vault/.claude-plugin/plugin.json
M  plugin/obsidian-vault/README.md
M  plugin/obsidian-vault/agents/gardener.md
M  plugin/obsidian-vault/commands/garden.md
M  plugin/obsidian-vault/commands/init.md
M  plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh
M  plugin/obsidian-vault/hooks/scripts/_test/test_bridge_capture_sh.sh
A  plugin/obsidian-vault/hooks/scripts/_test/test_memory_ops.py
M  plugin/obsidian-vault/hooks/scripts/_test/test_ps1_legacy_args.sh
A  plugin/obsidian-vault/hooks/scripts/_test/test_python_probe_proof.py
M  plugin/obsidian-vault/hooks/scripts/_test/test_vault_guard_sh.sh
M  plugin/obsidian-vault/hooks/scripts/bridge-status.ps1
M  plugin/obsidian-vault/hooks/scripts/bridge-status.sh
M  plugin/obsidian-vault/hooks/scripts/obsidian_common.py
M  plugin/obsidian-vault/hooks/scripts/vault-capture.ps1
M  plugin/obsidian-vault/hooks/scripts/vault-capture.sh
M  plugin/obsidian-vault/hooks/scripts/vault-guard.ps1
M  plugin/obsidian-vault/hooks/scripts/vault-guard.sh
M  plugin/obsidian-vault/hooks/scripts/vault_capture.py
A  plugin/obsidian-vault/hooks/scripts/vault_garden.py
A  plugin/obsidian-vault/hooks/scripts/vault_import.py
M  plugin/obsidian-vault/hooks/scripts/vault_ops.py
A  plugin/obsidian-vault/hooks/scripts/vault_recall.py
A  plugin/obsidian-vault/hooks/scripts/vault_setup.py
M  plugin/obsidian-vault/skills/obsidian-memory-contract/SKILL.md
A  plugin/obsidian-vault/skills/obsidian-memory-contract/profiles/canvas-maps.md
A  plugin/obsidian-vault/skills/obsidian-memory-contract/profiles/memory-vault.md
M  plugin/obsidian-vault/skills/obsidian-scheduling/SKILL.md
M  plugin/obsidian-vault/skills/obsidian-setup/SKILL.md
```

24 files (17 modified, 7 added), against twelve modified at the previous re-anchor - this is by far
the largest single-pass change this note has tracked. **`plugin/obsidian-vault/hooks/scripts/vault_guard.py`
and `plugin/obsidian-vault/hooks/scripts/hooks.json` are NOT in this list** - both are
byte-identical to the previous anchor (`git diff --name-only 60c79407..6c497a14 -- <each>` empty),
confirmed directly rather than assumed from their absence above. Every `## Landmines` claim about
`vault_guard.py`'s contract logic (the three checks, the exemption sets, `notesPrefix` scoping, the
stdin decode-then-parse split) therefore still holds unchanged and was not re-read this pass.

**What changed, grouped by the task that requested this pass:**

- **Per-host capture, dedup, and a named refusal.** `vault_capture.py` (+121/-, see diff stat) -
  covered above in Owns data and Landmines. Pinned by the new `test_memory_ops.py`.
- **All six wrappers converged on one resolver shape: walk every PATH match, verify with a
  version/impl/executable probe, an 8s overall deadline on top of each 3s per-candidate bound, a
  `%`-free probe string routed through `cmd.exe` for a `.cmd`/`.bat` shim, and a whole-process-tree
  kill-and-reap on timeout.** `vault-guard.sh` (+171/-), `vault-guard.ps1` (+242/-),
  `bridge-status.sh` (+156/-), `bridge-status.ps1` (+221/-), `vault-capture.sh` (+157/-),
  `vault-capture.ps1` (+222/-) - covered above in Landmines. Pinned by the new
  `test_python_probe_proof.py`, and by updates to the three existing `_test/*.sh` suites
  (`test_vault_guard_sh.sh`, `test_bridge_capture_sh.sh`, `test_ps1_legacy_args.sh`).
- **A test-fixture bug in the same burn-in: `PWSH_DIR`, an isolated symlink-only directory, replaces
  appending `$(dirname "$PWSH")` to a fixture PATH.** On GitHub's `ubuntu-latest` image, `pwsh` and
  the system's real `python3` both live in `/usr/bin`, so a fixture PATH meant to simulate "no
  usable interpreter" was leaking a real, working `python3` into every such case - every must-refuse
  case became a false PASS-through instead of the expected stand-down. Fixed by creating
  `$work/pwsh-only` holding nothing but a symlink to the real `pwsh`
  (`plugin/obsidian-vault/hooks/scripts/_test/test_vault_guard_sh.sh:695-707`, and the identical
  pattern in `plugin/obsidian-vault/hooks/scripts/_test/test_bridge_capture_sh.sh:354-358`).
  (DERIVED, read in full - not merely inferred from the task's own summary of it.)
- **Roles and profiles.** `writer_vault()`, `ROLES`, `host_id()` in `obsidian_common.py` (+102/-);
  `vault_setup.py`, `vault_import.py`, `vault_recall.py`, `vault_garden.py` (all new); `select()`'s
  `ignore`-role filter and the four modules' `add_parsers` wiring in `vault_ops.py` (+22/-); the two
  new profile files under `obsidian-memory-contract/profiles/` - all covered above in Entry points,
  Owns data and Landmines.
- **Retired: `claude-memories-vault` and `claude-memories-canvas`** removed from
  `.claude-plugin/marketplace.json` in the same commit (covered above in Landmines); their
  conventions are what the two new profile files carry forward in portable form.
- **Not investigated further, low materiality:** `agents/gardener.md` (+31/-23, likely updated for
  the per-host queue and role concepts above - not opened, per Unverified), `commands/garden.md`
  (+20/-, probably documents `garden-run`/`drain`/`reconcile` - not opened),
  `commands/init.md` (+23/-, probably documents `adopt` - not opened), the three `SKILL.md` files
  (not opened beyond the two profile files), and `README.md` (+153/-13 - read only at the specific
  lines cited above: `:20-23`, `:33-44`, `:218-222`).

**Every `path:line` citation in this note that pointed into a file NOT in the 24-file list above is
unaffected and was not re-read**, per the same logic the previous three re-anchors used: `hooks.json`,
`vault_guard.py`, `bridge_status.py`, `vault_profiles.py`, `CLAUDE.md`, `README.md` (outside the
cited ranges), `AGENTS.md`, and `plugin/crew/hooks/hooks.json` all resolve into an empty diff for
their own path and were left as written.

**The regression suite was re-run, not assumed.** See "Measured this pass" above: 71 passed, 0
failed, 0 skipped, on Linux with `pwsh` present, in this worktree (`/repos/personal/uca-k4`) at
`6c497a14`.

**Existence check, since the task that requested this pass expected the plugin's other codemap-cited
paths (crew's role-write-guard.sh, TODO.md-adjacent citations) to show real changes elsewhere in
this repo.** Nothing under `plugin/obsidian-vault/` disappeared; every file this note has ever cited
still exists at `6c497a14` (`vault_guard.py:243`'s three copies of a since-corrected stale citation,
recorded at the previous anchor, were not re-checked this pass since `vault_guard.py` did not
change).

Not re-verified at this pass, beyond what "Unverified" above already states: `agents/gardener.md`,
`agents/reflector.md`, all eleven command files, and all three skills remain unopened even though
five of those eight paths changed this pass (`gardener.md`, `garden.md`, `init.md`, and two of the
three `SKILL.md` files); `vault_setup.py`, `vault_import.py`, `vault_recall.py` and `vault_garden.py`
were read only at their module docstrings and top-level signatures, not end to end; nothing touched
a live vault, a live bridge port, or `~/.claude/obsidian/config.json`; the bounded process-tree kill
on Windows remains MODELLED, not observed.

**Re-anchored `6c497a14` -> `f2bb919b` on 2026-09-25 (T-0015).** `git diff --name-only 6c497a14
f2bb919b -- <the 45 tracked paths this note cites>` returns `.claude-plugin/marketplace.json`,
`CHANGELOG.md` and `README.md`, and nothing under `plugin/obsidian-vault/`. None of the three
carries a live claim here: the marketplace hunk is crew's `version` on `:218` alone, so the
`obsidian-vault` entry at `.claude-plugin/marketplace.json:234-237` still reads `0.4.14` (re-read);
`README.md` changed only its two install-URL pins (`:12`, `:18`), and this note names it only as an
exempt basename; `CHANGELOG.md` gained crew 1.0.26-1.0.28 entries, and no `CHANGELOG.md:<n>`
citation appears in this note. No claim moved.

**Re-anchored `f2bb919b` -> `07ca3972` on 2026-09-26 (T-0004).** `git diff --name-only f2bb919b..HEAD
-- <every tracked path this note cites> plugin/obsidian-vault/` returns `.claude-plugin/marketplace.json`,
`CHANGELOG.md`, `CLAUDE.md` and `README.md`, and nothing under `plugin/obsidian-vault/` or crew's
`role-write-guard.*`/`hooks.json`. The marketplace hunk is crew's description and `version` alone
(+2/-2, no line shift), so `.claude-plugin/marketplace.json:234-237` still reads `obsidian-vault`
`0.4.14` (re-read). `README.md` changed only crew's slash-command count (34 -> 35) at `:168` and
`:874`; this note names it only as an exempt basename. `CLAUDE.md` changed only three
`crew_freshness.py` line numbers in its Memory section; this note cites `crew_freshness.py` without
a line. `CHANGELOG.md` gained entries and has no `CHANGELOG.md:<n>` citation here. **One claim
corrected, and it was wrong when written, not drifted:** the Landmines bullet on the retired
`claude-memories-*` skills placed the "Two vault systems on one host" entry in this repo's
`CLAUDE.md`; it is in no tracked file (`git grep`, at both commits) and lives in the operator's
untracked auto-memory. The suite was not re-run this pass.

**Re-anchored `6f96e627` -> `d2444be9` on 2026-09-27 (T-0075).** `git diff --name-only 6f96e627
d2444be9 -- <every tracked path this note cites> plugin/obsidian-vault/` returns `README.md` alone:
crew's slash-command count (35 -> 36) in place at `:168` and `:874`, no line shift. This note names
`README.md` only as an exempt basename. Nothing under `plugin/obsidian-vault/` changed. The suite was
not re-run this pass.

**Re-anchored `6f96e627` -> `b5c37635` on 2026-09-28 (T-0087, crew 1.0.52).** Of the paths this note cites, only `CLAUDE.md` (the tooling-alone bullet, cited by name here, no line), `CHANGELOG.md`, `TODO.md` and `.claude-plugin/marketplace.json` (other plugins' versions and crew's, none cited at a line this note depends on) changed between `6f96e627` and `b5c37635`. No citation moved. Nothing was executed for this note.
**Re-anchored `6f96e627` -> `22399a9c` on 2026-09-28 (T-0085, crew 1.0.52).** `git diff --name-only 6f96e627 22399a9c` over the paths this note cites returns `.claude-plugin/marketplace.json`, `CHANGELOG.md`, `CLAUDE.md` and `README.md`: crew's version and description, crew skills figures and changelog entries from T-0072, T-0079 and T-0085, and T-0085's ignore-policy paragraph in `CLAUDE.md`. Nothing under `plugin/obsidian-vault/` changed. The one line citation into them, the `obsidian-vault` entry at `.claude-plugin/marketplace.json:234-237`, was re-read at both commits: identical, still `0.4.14`. Nothing was executed for this note.

**Re-anchored `6f96e627` -> `051f9e85` on 2026-09-28 (T-0091).** `051f9e85` is T-0091's one commit on `T-0091-build`, off main `f54af3fa`. `git diff --name-only 6f96e627 f54af3fa -- <every tracked path this note cites>` is empty; `f54af3fa..051f9e85` changes only `CLAUDE.md` (the Landmines truncating-`open` entry's measurement paragraph, now `:185-212`, +28/-18, so every later line moves +10) and `TODO.md` (one entry closed at `:4473`, three lines appended at `:4480-4482`). This note cites `CLAUDE.md` without a line (its exempt basename and the Lessons section by name). No claim moved. Nothing was executed.

**Re-anchored `051f9e85` -> `c192b83d` on 2026-09-28 (T-0091 review round 1).** `c192b83d` is T-0091's review-round-1 fix on `T-0091-build`. `git diff --name-only 051f9e85 c192b83d` returns only `CLAUDE.md`: the same Landmines truncating-`open` measurement paragraph, now `:185-219` (+16/-9, so every later line moves +7; lines above `:192` are byte-identical). This note cites `CLAUDE.md` without a line. No claim moved. Nothing was executed.

**Re-anchored `d2444be9` / `c192b83d` -> `3648f59a` on 2026-09-28 (T-0075 review round 5, merge of `6387ab49`).** The merge kept both lines' notes (T-0075's `d2444be9` paragraph first, main's T-0091 paragraphs after it). `git diff --name-only c192b83d 3648f59a -- <every tracked path this note cites> plugin/obsidian-vault/` returns `.claude-plugin/marketplace.json` (crew's description and version lines, in place), `CHANGELOG.md`, `README.md` (crew's slash-command count 35 -> 36 at `:168` and `:874`, in place; the `d2444be9` note above) and `TODO.md` (T-0092's entry at `:5051`, below every citation here). `.claude-plugin/marketplace.json:234-237` re-read: the `obsidian-vault` entry, `0.4.14`, matching `plugin/obsidian-vault/.claude-plugin/plugin.json:3`. Nothing under `plugin/obsidian-vault/` changed. No claim moved. Nothing was executed.

**Re-anchored `6f96e627` -> `a43acd56` on 2026-09-28 (T-0088, crew 1.0.53).** `a43acd56` is T-0088's crew 1.0.53 version commit on `T-0088-build`, after `7b1e2228` merged origin/main `c426c018` with a merge commit. `git diff --name-only 6f96e627 a43acd56` over this note's cited paths returns `plugin/crew/hooks/scripts/crew_platform.py` (T-0088's inheriting-worktree guard in `heal_config`, and the resolver import), which this note cites by name only (`:799`), and `.claude-plugin/marketplace.json`, cited only at `:248` inside provenance sections that describe their own commits. No citation moved. Nothing was executed for this note.

**Re-anchored `a43acd56` -> `6caa1872` on 2026-09-28 (T-0088 merges origin/main `f8b6c8d7`, T-0091).** `6caa1872` is the merge commit on `T-0088-build` that joins T-0088's line (above, `a43acd56`) with T-0091's (above, `c192b83d`); its conflicts were the parallel anchor lines and re-anchor paragraphs only, both histories kept. `git diff --name-only a43acd56 6caa1872`, refresh artifacts aside, returns `CLAUDE.md` and `TODO.md` and nothing under `plugin/`, `scripts/` or `skills/`. `git diff c192b83d 6caa1872 -- CLAUDE.md` is empty, so this note's `CLAUDE.md` citations are the ones T-0091 re-verified at `c192b83d`, carried in by the merge; `TODO.md`'s only change (T-0091, `:4473` and `:4480-4482`) sits below every `TODO.md` line cited here. Every citation into a path T-0088 changed is as re-verified at `a43acd56`. No claim, count or citation changed. Nothing was executed for this note beyond those comparisons.

**Re-anchored `6caa1872` -> `fe80f69d` on 2026-09-28 (T-0088 review round 1 fixes, crew 1.0.55 unchanged).** `c3624af6` fixes the round's four FIX and three NIT findings (`crew_common.py`, `crew_platform.py`, `crew_config.py`, `review_run.py`, `review_limit.py`, their tests and sabotage entries, and the docs that describe them: `plugin/crew/CONFIG.md` +10 below `:126`, `plugin/crew/README.md` +7 below `:942`, `commands/review.md` in place, `CHANGELOG.md`, the troubleshooting and working-with-codex guides, `BUDGETS.md:11` in place); `fe80f69d` rebuilds the two guides. Every body citation of the form `path:line` into those files was compared by script (`/root/crew-tmp/t-0088/cites.py`, local), including the seven into `crew_platform.py`, all above its +7 at `:239`: each holds; `BUDGETS.md:11` (the count, in place) and `CHANGELOG.md` lines inside dated provenance notes are left as history. Nothing was executed for this note.

**Re-anchored `fe80f69d` -> `68e106f5` on 2026-09-28 (T-0088 re-bumps crew to 1.0.56 for its review round 1 fixes).** `68e106f5` sets the version files (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`) to 1.0.56 and moves T-0088's own current-version mentions (`plugin/crew/CONFIG.md:117`, `:135`, `:141`, `plugin/crew/README.md:963`, `:963`, `docs/guides/crew/src/troubleshooting.md:166`, `:170` and the rebuilt troubleshooting HTML/DOCX/PDF) and its `CHANGELOG.md` heading and bump line to 1.0.56, all in place: `git diff --numstat fe80f69d 68e106f5` shows equal added and removed counts for every text file. No cited line moved. Nothing was executed for this note.

**Re-anchored `b5c37635` -> `c0768d0e` on 2026-09-28 (T-0087, crew 1.0.53).** `c0768d0e` is T-0087's merge of main `f8b6c8d7` (T-0091, no plugin version change) into `T-0087-build`; crew stays 1.0.53, one past main's 1.0.52, and `c8cc69ec` is still the last `plugin/crew` commit. `git diff --name-only b5c37635 c0768d0e`, refresh artifacts aside, returns `CLAUDE.md` (T-0091's Landmines truncating-`open` measurement paragraph, +35/-18 at `:189`, so every later line moves +17) and `TODO.md`. `b5c37635..c8cc69ec` changed, of this note's cited paths, only `CHANGELOG.md`, `.claude-plugin/marketplace.json` and `CLAUDE.md` above `:189` (T-0087's own crew version re-sets and the tooling-alone bullet, cited by name here, no line). Every other body `CLAUDE.md:N` citation here is at or above `:189`, or sits inside a dated re-anchor note that states the coordinates of its own commit, so none moved. Nothing was executed for this note.

**Re-anchored `c0768d0e` / `c192b83d` -> `379ab5e6` on 2026-09-28 (T-0087 merged onto `6387ab49`, crew 1.0.55).** `01dd3854` merges origin/main `6387ab49` into `T-0087-build`: T-0089 (crew 1.0.53, `plugin/crew/tests/test_role_write_guard.py`), T-0090 (mcp-servers 0.2.1: `SECURITY.md`, ten files under `mcp-servers/`) and T-0092 (crew 1.0.54: `graphify-out/` left out of review bundles - `review_patch.py`, `review_prompt.py`, `completion_audit.py`'s comment, `crew_autopilot.py`'s docstring, `commands/review.md`, `plugin/crew/README.md`, `TODO.md`, three test files). `379ab5e6` re-bumps crew to 1.0.55, one past main's 1.0.54, and moves T-0087's `1.0.53` mentions (`plugin/crew/README.md:754`, its `CHANGELOG.md` entry) to 1.0.55 in place. The code-map, INDEX, diagram, rules and graph conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the version sentence, `.claude/rules/` and `graphify-out/` taken from main and then refreshed. Every body citation of the form `path:line` was re-mapped by script (difflib over each cited file, from the anchor of the side `git blame` puts the note line on, both anchors for a line common to both, never guessed): none moved in this map. Citations the script could not map, or where the two sides' anchors disagree on a line common to both, were not re-read here and are unchanged; they predate this merge (for example `CHANGELOG.md`'s "117 -> 119" is cited at `:654-655` on both sides and sits at `:909-910`), and this pass only re-anchors.

**Re-anchored `379ab5e6` -> `17fa035e` on 2026-09-28 (T-0087 review round 1, crew 1.0.55 unchanged - not yet released).** `bbe68e85` fixes review round 1: autopilot lets a refunded round's `/crew:review` rerun past its no-progress stop, rule 31 triggers on its suites and seam consumers, `scripts/check-tooling-pr.py` admits no production code or prompt alongside the harness (a `SEAM` consumer only with a `Tooling-seam:` trailer), `golden_build.redact` bounds both sides of a match, a malformed `successors` loads as corrupt, `review_run.py`'s summary line counts charged rounds, a worktree rename is parsed, and the guides stop calling a post-refund rerun free; `17fa035e` re-prices rule 31. `git diff --name-only 379ab5e6 17fa035e`, refresh artifacts aside, returns those scripts, their tests, one golden fixture, `.crew/verify.json`, `CLAUDE.md`, `CHANGELOG.md`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`, `commands/autopilot.md`, `commands/review.md` and the troubleshooting guide. Body citations of the form `path:line` into those files were re-mapped by script (difflib over each cited file from `379ab5e6` to `bbe68e85`, only for note lines committed before this pass, never guessed): none moved in this map.

## Re-anchor provenance - `3648f59a` -> `9e38a891`, 2026-09-29 (`T-0087-build` merges T-0010's `8ab733d7`)

`git diff --name-only 3648f59a 9e38a891` over the paths this note cites returns only `README.md`,
`CLAUDE.md`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md` and `scripts/check-tooling-pr.py`,
each cited here by name, never by line; nothing under `plugin/obsidian-vault/` changed. Re-anchor only: no claim below moved and nothing was executed for this note.

## Re-anchor provenance - `b4f39fd3` -> `78b7080a`, 2026-09-30 (`T-0087-build` merges T-0088's main `a61a6f38`)

`f702cb24` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68's CI ruff and xdist changes, gate-first review, the steward skill and `crew-qa-standards`) into `T-0087-build`, with a merge commit; its conflicts were mechanical and both sides were kept. `a9bc8877` moves T-0087's version text to 1.0.70 and its harness rule to `.crew/verify.json` rule 35, `90b71bbf` re-sets crew 1.0.70, one past main's 1.0.69, and `78b7080a` rebuilds two guides. Every body citation of the form `path:line` was re-mapped by script (difflib over each cited file, from T-0087's `cb9b79b1` for a note line both parents carry and from `a61a6f38` for a line only main carries, to this tree; a bare `:N` binds to the last path named on its line, with or without a line number): none moved in this map. Citations the script could not attribute to a file that has that line (a bare `:N` after a different file's name, or a short name with no directory) predate this merge and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.

## Re-anchor provenance - `78b7080a` -> `b142d8e3`, 2026-09-30 (T-0087 review round 4 fixes)

`dc412c5c` limits the refunded-rerun marker to the `review` phase in `crew_autopilot._review_phase` (+2 lines, so every `crew_autopilot.py` line from `_toward_review` on moves by 2), with a must-block test and sabotage entry (ac); `b5f87132` re-maps `plugin/crew/docs/external-tool-formats.md`'s citations and adds a test that pins them; `af7eccbe` re-times `.crew/verify.json` rule 35 in place (no line moved); `b142d8e3` corrects a CHANGELOG figure. Every body citation of the form `path:line` was re-mapped by script (difflib from `78b7080a` to `b142d8e3`; a bare `:N` binds to the last path named on its line), and the `crew_autopilot.py` citations whose path is on the line above were re-mapped by hand. Citations the script could not attribute predate this change and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.

**Re-anchored `22399a9c` -> `b82035e6` on 2026-09-28 (T-0085 merges main `f8b6c8d7`, T-0091).** `17b70570` merged origin/main `f8b6c8d7` into `T-0085-build` (mechanical conflicts only: anchors, provenance paragraphs, INDEX history cells, generated rules and graph); `b82035e6` moves the crew skills claim at `plugin/README.md:414` and `INSTALLATION.md:252` from 29 to 30 (spec Touch amendment). Of the paths this note cites, `git diff --name-only 22399a9c b82035e6` returns only `CLAUDE.md`. `CLAUDE.md`'s change is T-0091's Landmines truncating-`open` paragraph, whose citations were moved on main's side and merged in, plus T-0085's four-line ignore-policy reflow, which shifts no line. Every `CLAUDE.md:N`, `INSTALLATION.md:N` and `plugin/README.md:N` citation was compared by script against its text at `2aa49bb8`, `c192b83d` and HEAD; none needed moving: every `CLAUDE.md:N` citation here reads the same text at HEAD as at main's `c192b83d`, where T-0091 already moved them. No suite was executed for this note.

**Re-anchored `3648f59a` / `8abf7ffe` -> `e3f5fa49` on 2026-09-29 (T-0085 merges main `2693d0fa`, T-0075 landed as crew 1.0.59, and applies the owner-accepted round-1 standards amendments).** `0fd1bdf8` reverts T-0085's provisional crew 1.0.56 bump (`8abf7ffe`); `0fd92334` merges origin/main `2693d0fa` into `T-0085-build` (mechanical conflicts only: crew version lines take main's 1.0.59, crew counts take main's 36 commands with T-0085's 30 skills, `plugin/crew/tests/sabotage.py` registers both `CONFIG_MENU_MUTATIONS` and `STANDARDS_MUTATIONS`, anchors, provenance paragraphs, INDEX history cells, diagram notes, generated rules and graph); `e3f5fa49` amends GEN-01 and GEN-04 in `plugin/crew/skills/crew-standards/references/generic.md` and REPO-03 in `.crew/standards.md`, drops the version from T-0085's `CHANGELOG.md` heading and re-measures `plugin/crew/BUDGETS.md`. The build branch now declares main's 1.0.59 and carries no bump of its own (REPO-03 as amended). Every `path:N` citation outside provenance was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from the side that wrote it - `3648f59a` for a line in main's copy of this note, `0fd1bdf8` for a line only in T-0085's - to `e3f5fa49`, and every line that did not map to itself was read with `sed -n` / `grep -n`; the script attributes some bare `:N` to the wrong file, and those were read and hold. None moved; nothing under `plugin/obsidian-vault/` changed. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `e3f5fa49` -> `a7f9c5e4` on 2026-09-29 (T-0085 merges main `8ab733d7`, T-0010 landed as crew 1.0.61, after review round 3's fixes `33521aa4`).** Nothing under `plugin/obsidian-vault/` changed (`git diff --name-only e3f5fa49 a7f9c5e4 -- plugin/obsidian-vault` is empty); the one T-0085 path the refresh check named, `plugin/crew/skills/crew-standards/references/generic.md`, is cited only inside an earlier provenance paragraph. No body citation moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `a7f9c5e4` / `b4f39fd3` -> `69c7edbd` on 2026-09-30 (T-0085's landing merge of main `a61a6f38`, crew 1.0.70).** `69c7edbd` merges T-0085's build head `0c6f01e0` (round 4, owner-accepted) onto origin/main `a61a6f38` (crew 1.0.69: #263-#267 and T-0088) on `T-0085-land`, and sets crew 1.0.70. Every body `path:N` citation was mapped by script (`difflib` equal blocks, from the anchor of whichever side's copy of this note carries the line - `a7f9c5e4` for T-0085's, main's own anchor for main's - to `69c7edbd`); each that mapped to one new line was moved, and each that did not map, or mapped differently from the two sides, was read with `sed -n` / `grep -n`. The script attributes a bare `:N` to the last path cited with a line number, so a bare `:N` after a path named without one (`.crew/verify.json` rule ranges, `crew_tfplan.py`, `sabotage_autopilot.py`, `crew_ticket.py`, `crew_standards.py`) was read against its real file and put back where the script moved it wrongly; `.crew/verify.json` lines up to `:339` did not move, and T-0085's rule is now `:361-373`, the last. A bare `review.md` citation is ambiguous since #267 added `crew-qa-standards/references/review.md`, so the script skipped those; `plugin/crew/commands/review.md` moved only below `:543` (+1, +3), and its cited lines above that were re-read. The merge kept both lines' provenance paragraphs (main's T-0088 ones first). No body citation moved; nothing under `plugin/obsidian-vault/` changed. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

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

## Re-anchor provenance - `7c88bf3d` -> `680e6783`, 2026-09-30 (T-0087 merges main `b601d450`, L-0521)

`680e6783` merges origin/main `b601d450` (L-0521: opt-in self-hosted runners for the crew pytest `test` job and the `crew-shell-matrix` ubuntu leg, #280) into `T-0087-build`. Of the paths this note cites, only `AGENTS.md` changed (L-0521's runner paragraph); a difflib re-map of every `path:line` citation from `7c88bf3d` to `680e6783` moved none. The `verification-harness` note's own L-0521 paragraph came from main's side cleanly. Re-anchor only: nothing was executed for this note.

**Re-anchored `5c9a9db2` -> `06cb9b51` on 2026-09-30 (T-0086 slice 1: the Python standards set, on main `301e478a`).** `git diff --name-only 5c9a9db2 06cb9b51` over this note's paths returns T-0086's files - `plugin/crew/skills/crew-standards/references/python.md` (new, set PYTHON), `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/test_crew_standards.py` (four new tests), `plugin/crew/tests/sabotage_standards.py` (three entries), `plugin/crew/README.md`, `plugin/PLUGINS.md` (rows only), `plugin/crew/BUDGETS.md` (count only) and `CHANGELOG.md` (T-0086's entry on top) - plus main's own commits since `5c9a9db2`. Path-qualified citations into changed files were moved by a line diff (`/root/crew-tmp/t-0086/remap.py`, 9 moved); `plugin/crew/BUDGETS.md:10-11` citations stay on the claim line, whose number changed in place. No suite was executed for this note.
**Re-anchored `06cb9b51` -> `35100955` on 2026-09-30 (T-0086's merge of main `9af34e57`, #279: CI triggers, concurrency, PR CI on Python 3.12 only).** `git diff --name-only 06cb9b51 35100955` returns, outside refresh artifacts, only `.github/workflows/*.yml`, `AGENTS.md` and `.crew/verify.json` (one line rewritten in place, line count unchanged). No `AGENTS.md:NN` citation exists in any map, and no claim outside verification-harness.md states the CI trigger shape (checked by grep for `push, pull_request`, `six workflows`, `three Python versions`, `windows-latest`), so no citation moved. No suite was executed for this note.

**Re-anchored `35100955` -> `fb292689` on 2026-09-30 (T-0086 review round 1's FIX: PYTHON-07's finding count).** `git diff --name-only 35100955 fb292689` returns only `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-07's Why, `6` -> `7` in place, line count unchanged), `plugin/crew/tests/test_crew_standards.py` (two tests and a pinned table inserted after `:302`) and `plugin/crew/tests/sabotage_standards.py` (four docstring lines after `:43`, two entries at the end; `STANDARDS_MUTATIONS` `:54` -> `:57`, 49 entries by `len()`). Every `path:N` citation into those files sits inside an earlier dated provenance paragraph, left as history. No suite was executed for this note.

**Re-anchored `fb292689` -> `f2cf0508` on 2026-09-30 (T-0086's merge of main `b601d450`, #280 L-0521: opt-in self-hosted runners).** `git diff --name-only fb292689 f2cf0508` returns, outside refresh artifacts, only `.github/workflows/pytest-crew.yml` (the `test` and `crew-shell-matrix` `runs-on` expressions) and `AGENTS.md` (one inserted paragraph after `:50`). No map cites `AGENTS.md:NN` or `.github/workflows/pytest-crew.yml:NN`; the one claim about those jobs' runner placement is verification-harness.md's, which main's own L-0521 commit already updated and the merge carries. No citation moved. No suite was executed for this note.

**Re-anchored `f2cf0508` -> `38b220cf` on 2026-09-30 (T-0086 review round 2's FIXes, merge of main `a7524aac` (T-0087, crew 1.0.76) as `142421d0`, crew 1.0.77).** `27387d83` fixes round 2: `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-01's EncodingWarning quote whole, +1 line; PYTHON-03's splitlines table escapes U+2028/U+2029), `plugin/crew/tests/test_crew_standards.py` (two tests before `test_python_set_applies_to_python_files_only`), `plugin/crew/tests/sabotage_standards.py` (four docstring lines, two entries; `STANDARDS_MUTATIONS` `:57` -> `:61`, 51 by `len()`), `plugin/crew/BUDGETS.md` and `CHANGELOG.md`. `142421d0` merges main's T-0087 with a merge commit; its map conflicts were mechanical: anchors took T-0086's side, provenance hunks kept both (main's first), and one-line hunks differing only in numbers took theirs plus T-0086's own shift (ours + theirs - base, per number); INDEX rows keep main's history cell plus T-0086's additions; `sabotage.py`'s import `:84` -> `:85` and append `:3061` -> `:3062` were set in the body. `38b220cf` sets crew 1.0.77 (`plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:218`, `plugin/PLUGINS.md:14`). BUDGETS.md re-measured at 21,421 lines across 136 files. No suite was executed for this note.

## Re-anchor provenance - `b4f39fd3` -> `f5d0f1b1`, 2026-09-30 (T-0094 merges `a61a6f38`, crew 1.0.70)

`0cd952b2` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68, the review gate `review_gate.py`, the `crew-qa-standards` skill, parallel CI and `CLAUDE.md`'s evidence moved to `docs/claude-md-evidence.md`) into T-0094-build at `d331c192`. Its conflicts were the version lines, `CHANGELOG.md` (both entries kept, T-0094's first), `.crew/verify.json` (T-0094's rule 32 kept, main's three new rules after it as 33-35), `crew_refresh_check.py`'s imports (both kept) and `plugin/crew/BUDGETS.md` (re-measured, 19,921 lines across 132 files); no code map, diagram or rule file conflicted (main's maps were still at `bbd9a66d`, but for `obsidian-vault.md`). `f5d0f1b1` sets crew 1.0.70, one past main's 1.0.69. Per-path: `git diff --name-only b4f39fd3 f5d0f1b1 -- <the 51 tracked paths this note cites>` returns `.claude-plugin/marketplace.json`, `CHANGELOG.md`, `CLAUDE.md`, `README.md`, `TODO.md`, `docs/guides/crew/src/troubleshooting.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`. Citations were re-mapped by a `difflib` line diff from each cited file's copy at the old anchor to `f5d0f1b1` (`/root/crew-tmp/t-0094/cite_apply2.py`, `cite_ident.py`, `cite_explicit.py`, machine-local): an explicit `path:N`, and a bare `:N` whose file is the one named before it in the paragraph, or the one whose old line carries the identifier beside the citation; every mapped line is text-identical at both ends. History positions ("at <sha>", "before", "on <branch>", "it was") and the provenance sections were left as written; a bare `:N` the scripts attributed to the wrong file was found by that identifier check and put back. Nothing under `plugin/obsidian-vault/` changed; `CLAUDE.md`'s restructure and the crew docs are outside what this note cites by line. No citation moved (a bare `:39` of `vault_guard.py` the scripts attributed to `CLAUDE.md` was put back). Nothing was executed for this note.

**Re-anchored `f5d0f1b1` -> `0c19512c` on 2026-09-30 (T-0094 crew 1.0.71).** `0c19512c` sets crew 1.0.71 (review round 3's fixes changed `plugin/crew/` after 1.0.70 was set, and origin/main is 1.0.70 too, T-0097 #268). Per-path: `git diff --name-only f5d0f1b1 0c19512c` over this note's cited paths returns only `plugin/crew/README.md` (two in-place "since 1.0.70" -> "since 1.0.71" edits, line count unchanged), beside the version files and `CHANGELOG.md` (release bookkeeping). No body citation moved.

**Re-anchored `0c19512c` (T-0094) / `5c9a9db2` (main) -> `1b9e4bfe` on 2026-09-30 (T-0094 merges main `9af34e57`, T-0085 landed as crew 1.0.75; review round 4's successor, crew 1.0.76).** `e1144866` merges origin/main `9af34e57` into T-0094-build at `7c261a19`; this map conflicted on anchor, version, provenance and cited-line text only (both sides' provenance kept, main's first; body hunks resolved to main's lines for files T-0094 does not change, T-0094's for its own). `c815bed8` and `f3fe692f` are the successor's code steps (`crew_refresh_check.py`: `_names_no_commit` new before `_moved_from`, `_rendered_verdict` pairs its source case-folded; `completion_audit.py`: `_default_artifacts` new after `_verdicts`; their tests, fixtures and sabotage entries), and `1b9e4bfe` sets crew 1.0.76 with the README, CHANGELOG and daily-workflow guide text. Per-path, `git diff --name-only 5c9a9db2..1b9e4bfe` over this note's 51 cited, existing paths returns `.claude-plugin/marketplace.json`, `.crew/verify.json`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`; from T-0094's side, `0c19512c..1b9e4bfe` adds `.crew/standards.md`, `plugin/README.md`, `plugin/crew/commands/review.md`, `plugin/crew/hooks/scripts/crew_standards.py`, `plugin/crew/hooks/scripts/role-write-guard.ps1`, `plugin/crew/skills/crew-standards/references/generic.md`, `plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_scope.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_crew_standards.py`, `plugin/crew/tests/test_ps1_python_probe.py` (main's T-0085, T-0097 and CI changes). Every body `path:N` citation was mapped by `/root/crew-tmp/t-0094/cite_map_merge.py` (difflib equal blocks, from the anchor of whichever side's copy carries the line; `MAIN_REV=origin/main`, `OURS_REV=7c261a19`) and each one it reported was read at HEAD. No body citation moved. No suite was executed for this note.

**Re-anchored `1b9e4bfe` -> `a0c171c7` on 2026-09-30 (T-0094 review round 5).** `git diff --name-only 1b9e4bfe a0c171c7` over this note's cited paths, refresh artifacts and release bookkeeping aside, returns `plugin/crew/README.md` (one sentence extended in place, line count unchanged), `plugin/crew/hooks/scripts/crew_refresh_check.py` (`_present` new at `:327`, everything below it +19 to +25 lines). No body citation of this note names a moved line of those files. Citations checked with `/root/crew-tmp/t-0094/cite_apply3.py` (DRY, machine-local) and `grep -n`. No suite was executed for this note.

**Re-anchored `a0c171c7` (T-0094) / main -> `a0db0703` on 2026-09-30 (T-0094 merges origin/main `a7524aac`, T-0087 landed as crew 1.0.76, #281, and L-0521, #280; crew 1.0.77, before review round 6).** `f6f2c2f0` merges `a7524aac` into T-0094-build at `75565970`; `a0db0703` re-sets the version one past main's 1.0.76 (plugin.json, marketplace.json, `plugin/PLUGINS.md:14`, two README sentences, the CHANGELOG heading). The code maps conflicted on anchor, version, provenance and cited-line text only: both sides' provenance kept, main's first. In body hunks a citation into a file only one side changed takes that side's number (`crew_autopilot.py`, `review_ledger.py`, `sabotage.py` and `CLAUDE.md` main's; `crew_refresh_check.py` T-0094's); positions in files both sides changed (`.crew/verify.json`, `plugin/crew/tests/sabotage_refresh.py`) were re-measured on the merged tree: T-0087's harness rule is rule 37 at `.crew/verify.json:411-436`, after T-0094's rule 32; `REFRESH_MUTATIONS` is at `plugin/crew/tests/sabotage_refresh.py:119`; the CLAUDE.md Lessons line is `:144`. Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from each side's anchor (`a0c171c7` and main's own) to `a0db0703` (difflib equal blocks): no citation outside those re-measured positions fails both mappings. Carried as main has them, not corrected here: main's own `crew_autopilot.py` body citations in `crew.md` that already lag main's tree by a few lines (e.g. `next_phase` `:556`, the def is at `:559`) - outside T-0094's change.

**Re-anchored `a0db0703` (T-0094) / `38b220cf` (main) -> `65abeb8d` on 2026-09-30 (T-0094 merges origin/main `549cda24`, T-0086 landed as crew 1.0.77, #282, as `44407f8e`; the owner's split moves the harness half to L-0540 at `c974f997`; review round 6's successor `6ecb6403`..`b17266ed`; crew 1.0.78 at `65abeb8d`).** Per-path, `git diff --name-only a0db0703 65abeb8d` over this note's 69 cited, tracked paths returns `.claude-plugin/marketplace.json`, `CHANGELOG.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/crew-standards/references/python.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/sabotage_refresh.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_crew_standards.py`; from main's side, `git diff --name-only 38b220cf 65abeb8d` over the same paths returns `.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`. The merge's conflicts in this map were the anchor and provenance only (both kept, main's first). No body citation in this map names a line the successor or the merge moved (checked with `/root/crew-tmp/t-0094/cite_map_merge.py`, `MAIN_REV=origin/main`, `OURS_REV=b4d87187`, machine-local). No suite was executed for this note.

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

**Re-anchored `0c3508e9` -> `6e581365` on 2026-09-30 (T-0505 merges main 64b04c6b: W-0116 crew 1.0.89, runner auto-start #294; crew 1.0.91).** `git diff --name-only 0c3508e9 6e581365` outside the refresh artifacts returns W-0116's `plugin/crew/hooks/scripts/crew_refresh_check.py` and `plugin/crew/tests/test_refresh_admission.py`, `.github/workflows/runner-autostart.yml` (#294), the repo README, and T-0505's files: `promote-gate.sh`/`.ps1`, the new `_promote_tree.py`, `test_promote_gate_effective_tree.py`, `promote_tree_mutations.py`, `promote.md`, crew README, CONFIG.md (+2 lines in section 16), the crew-verification SKILL, INSTALLATION.md, `.crew/verify.json` (rule 4 path), the troubleshooting guide and its builds, the cloud handoff note and README, CHANGELOG.md and the version files (crew 1.0.91, past main's 1.0.89). A difflib re-map of every path-qualified `path:line` citation in the eight maps (history sections skipped) moved four: `crew_refresh_check.py:970` -> `:1013` (W-0116) and three `plugin/crew/CONFIG.md:2410-2417` -> `:2412-2419` (T-0505's sentence); none was unmapped. Re-applied by hand in `crew.md`: `promote-gate.sh:79` is the plain `crew_py()` call (re-read with `grep -n`), and `promote-gate.sh` is not a `crew_config.py` user (no `crew_config` import or `.crew/config.json` read in either flavour). Bare `:N` continuations and `CHANGELOG.md` citations in history sections were left as written. No suite was executed for this note.

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

**Re-anchored `11f476a2` -> `1390bb23` on 2026-10-01 (L-0516 merges main `52489039` (T-0110 #297 at crew 1.0.97, T-0040 #290 at 1.0.98) without rerere and re-bumps crew to 1.0.100).** Main moved while this lane's suites ran. Conflicts were refresh artifacts, CHANGELOG and BUDGETS.md only; maps, diagram notes and INDEX keep both histories (main's first). A citation re-map that follows each line's origin (this branch's lines from `e9375690`, main's from `52489039`, each to `1390bb23`; history skipped) moved nothing: main's own lines already carry T-0040's moves (`CONFIG.md`, `crew_config.py`, crew README). Re-read by hand: `crew.md`'s W-0116 `_FINAL_PATH` sentence keeps this branch's text (`crew_refresh_check.py:716`); `verification-harness.md`'s verify.json paragraph now reads 42 rules / 443 lines (T-0040's rule 42 at `.crew/verify.json:460-466`, `default` `:441`, `unmapped` `:442`), and rule 39 `:418-431` is unchanged. No suite was executed for this note.

**Re-anchored `1390bb23` -> `0027f794` on 2026-10-01 (L-0516 merges main `05a679bf` (L-0558 #293 at crew 1.0.102) without rerere and re-bumps crew to 1.0.103).** Main moved while this lane's required checks ran. Conflicts were refresh artifacts, CHANGELOG and the version files only; maps, diagram notes and INDEX keep both histories (main's first). Main's change outside refresh artifacts is `crew_train.py`, `test_crew_train.py`, crew README, the daily-workflow and troubleshooting guides, CHANGELOG, the version files and `.crew/verify.json` rule 37's line rewritten in place (443 lines at both `1390bb23` and `0027f794`, so no `.crew/verify.json:N` citation moves). Main's own lines already carry L-0558's `crew_train.py` moves; no line this branch added cites `crew_train.py`, `test_crew_train.py`, the crew README or either guide by line. `crew.md`'s version sentence names 1.0.103 in place. No suite was executed for this note.

**Re-anchored `9580571e` (main's side of the merge) and `4a48f594` (L-0513's side) -> `de32cb87` on 2026-10-01 (L-0513 merges origin/main `44d3dbc6` at `293b78a1` with `git -c rerere.enabled=false`, bringing T-0110 #297 and crew 1.0.97, then review round 4's five fixes; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept above. `git diff --name-only 9580571e de32cb87` outside refresh artifacts returns L-0513's `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 55 -> 57 and their `why`, in place, line count unchanged), `CLAUDE.md` (L-0513's two-line pointer in Commands) and `CHANGELOG.md`, and main's T-0110 files: `.github/workflows/pytest-crew.yml`, `AGENTS.md`, eight files under `plugin/crew/tests/` (`crew_fixtures.py`, `test_msys_tmp_pin.py` and six others) and the version files `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md:14` and `plugin/crew/.claude-plugin/plugin.json:3` (crew 1.0.97, in place). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `de32cb87`, found every one mapping onto itself from at least one parent, except the in-place version lines and `CHANGELOG.md:N` figures inside history notes, left as written; `crew.md`'s version sentence now reads 1.0.97. No suite was executed for this note.

**Re-anchored `de32cb87` -> `f23b01b4` on 2026-10-01 (L-0513 Fix phase: review round 5's two FIX findings; repository tooling, no plugin version of its own, crew is main's 1.0.97).** `git diff --name-only de32cb87 f23b01b4` outside refresh artifacts returns `scripts/gate-runner.py` (`_valid_result` now takes the table step, requires phase/group/argv/cwd/timeout, and refuses a FAIL whose rc `classify()` would not call FAIL), `scripts/_test/gate-runner.py` (two new cases, `part_row`), `.crew/verify.json` (rules 22 and 40: `seconds` 57 -> 58 and their `why`, in place, line count unchanged) and `CHANGELOG.md` (+3 lines inside L-0513's entry, at :30-36). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped) from `de32cb87` found every one mapping onto itself except nine `CHANGELOG.md:N` citations in `crew.md`, shifted +3 to the lines they cited, and the in-place `.crew/verify.json:287`/`:430` lines. No suite was executed for this note.

**Re-anchored `f23b01b4` (L-0513's side) and main's side -> `71038cb9` on 2026-10-01 (L-0513 owner amendment for review round 6's BLOCK at `fbd48532`, then `git -c rerere.enabled=false merge origin/main` `52489039` (T-0040 #290, crew 1.0.98) at `74130bbd`, then rules 22 and 40 repriced at `71038cb9`; repository tooling, no plugin version of its own).** `git diff --name-only f23b01b4 71038cb9` outside refresh artifacts returns L-0513's `scripts/gate-runner.py` and `scripts/_test/gate-runner.py` (the BLOCK fix: no process-group signal once the leader is reaped, and its two cases), `CHANGELOG.md` (L-0513's entry +3 lines; T-0040's 1.0.98 entry now sits below it) and `.crew/verify.json` (rules 22 and 40 `seconds` 58 -> 60 and `why`, in place; T-0040's shell-route rule appended as rule 41 at `:432-437`), and T-0040's own paths, which main's side of this map already describes. Where the merge conflicted here it was the anchor header and these provenance notes: both sides kept, main's first. The `CHANGELOG.md:N` citations in older provenance notes name lines at the commits those notes name and were not shifted. Refresh artifacts per owner rule 2026-09-28; no test suite was executed for this note.

**Re-anchored `71038cb9` (L-0513's side) and `89ebda03` (main's side) -> `0d159692` on 2026-10-01 (L-0513 merges origin/main `05a679bf` - L-0558 #293, crew 1.0.102 - at `0d159692` with `git -c rerere.enabled=false`; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept, main's first. `git diff --name-only 71038cb9 0d159692` outside refresh artifacts is main's L-0558 change only: `plugin/crew/hooks/scripts/crew_train.py`, `plugin/crew/tests/test_crew_train.py`, `plugin/crew/README.md`, the daily-workflow and troubleshooting guide sources and their six builds, `.crew/verify.json`, `CHANGELOG.md` and the three version files (crew 1.0.102). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `0d159692`, found every one mapping onto itself from at least one parent except three `CHANGELOG.md:N` citations in `crew.md` from L-0513's side, moved to the lines they cited (`:485-486` -> `:519-520`, `:645-646` -> `:679-680`, `:274` -> `:308`); `crew.md`'s version sentence now reads 1.0.102. No suite was executed for this note.

**Re-anchored `0027f794` (L-0516's side) and `0d159692` (main's side) -> `ec95c8aa` on 2026-10-01 (L-0516 merges origin/main `cacf7ff0` - L-0513 #301, the gate runner; crew stays 1.0.102 on main - with `git -c rerere.enabled=false`; crew 1.0.104, re-bumped at `1f2114bc` past 1.0.103, which L-0510's worktree claimed first).** Conflicts were refresh artifacts and CHANGELOG only; each map keeps both re-anchor histories. `git diff --name-only 0027f794 ec95c8aa` outside refresh artifacts returns main's L-0513 paths (`.crew/verify.json` rule 22 rewritten in place at `:262-266` and its gate-runner rule appended at `:432-436`, `CLAUDE.md`, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`) and the three version files plus CHANGELOG; `git diff --name-only 0d159692 ec95c8aa` returns L-0516's own paths. A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor, found every one mapping onto itself from at least one parent except the version lines (changed in place) and nine `CHANGELOG.md:N` citations in `crew.md` from main's side, which L-0516's CHANGELOG entry above them moved by 35 (`:519-520` -> `:554-555`, `:679-680` -> `:714-715`, `:308` -> `:343`, `:676-677` -> `:711-712`, `:887-888` -> `:922-923`, `:898-899` -> `:933-934`, `:1114-1115` -> `:1149-1150`, `:1238` -> `:1273`, `:1134` -> `:1169`). `verification-harness.md`'s verify.json section now reads the merged tree (448 lines, 43 rules). No suite was executed for this note.

**Re-anchored `ec95c8aa` -> `5ffffbe3` on 2026-10-01 (L-0516 merges origin/main `ddcbf90d` - W-0115 #299, T-0040's shell-route sabotage mutations, crew 1.0.106 - with `git -c rerere.enabled=false` and re-bumps crew to 1.0.110, skipping 1.0.105 (L-0557), 1.0.107 (T-0504), 1.0.108 (L-0510) and 1.0.109 (T-0501)).** Conflicts were the three version files and CHANGELOG only. `git diff --name-only ec95c8aa 5ffffbe3` outside refresh artifacts returns W-0115's paths (`plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_shell.py`, `.crew/verify.json`'s last rule gaining one path line) plus the version files and CHANGELOG. A difflib re-map of every path-qualified citation (history notes skipped) moved two `plugin/crew/tests/sabotage.py` citations in `crew.md` by +2 (`:3055` -> `:3057`, `:3056` -> `:3058`; W-0115 adds an import at `:86` and a comment line at `:3055`), the nine main-side `CHANGELOG.md` citations in `crew.md` by +15 for W-0115's entry, and `verification-harness.md`'s verify.json header to 449 lines; every other citation maps onto itself. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `b1d8a4e8` on 2026-09-30 (L-0557: per-test XDG_CACHE_HOME for every pwsh the suites spawn, crew 1.0.89, obsidian-vault 0.4.16).** `git diff --name-only 0c3508e9 b1d8a4e8` returns, outside refresh artifacts, L-0557's test-only files (`plugin/crew/tests/conftest.py`, `plugin/crew/tests/crew_fixtures.py`, new `plugin/crew/tests/test_pwsh_cache_isolation.py`, both `test_flavour_guard.py` copies, the obsidian-vault `_test` suites, six `scripts/_test/*.sh`), `.crew/verify.json` (one new rule, appended after the Kimi rule), `plugin/crew/README.md` (one paragraph after the test-layer table), the harness reference's H4 table (one row), `CHANGELOG.md`, `plugin/crew/BUDGETS.md` and the version files. Body `path:line` citations into those files were moved by difflib from `0c3508e9` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local): 25 moved, in crew.md (CHANGELOG), obsidian-vault.md (its `_test` suites) and verification-harness.md (verify.json range unchanged). No hook or production script changed. No suite was executed for this note. The obsidian-vault `_test` suites that run pwsh (`test_vault_guard_sh.sh`, `test_bridge_capture_sh.sh`, `test_ps1_legacy_args.sh`, `run-tests.sh`, and the Python `test_flavour_guard.py`, `test_memory_ops.py`, `test_python_probe_proof.py`) now give it a throwaway `XDG_CACHE_HOME`.

**Re-anchored `b1d8a4e8` -> `d9ccfd5a` on 2026-10-01 (L-0557 merges main 0c0275e8 (W-0116 #292, crew 1.0.89) and re-sets crew 1.0.95).** `git diff --name-only b1d8a4e8 d9ccfd5a` returns, outside refresh artifacts, W-0116's `plugin/crew/hooks/scripts/crew_refresh_check.py` (a final-path check in `_read_regular`'s no-dir_fd branch, hunks from :684) and `plugin/crew/tests/test_refresh_admission.py`, `CHANGELOG.md` (both sides' Unreleased entries kept) and the version files (crew 1.0.95). Body `path:line` citations into those files were moved by difflib from `b1d8a4e8` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local), each onto the same line text. No suite was executed for this note.

**Re-anchored `d9ccfd5a` -> `97ace923` on 2026-10-01 (L-0557 review round 1 fixes, crew 1.0.96).** `git diff --name-only d9ccfd5a 97ace923` returns, outside refresh artifacts, L-0557's test-only `plugin/crew/tests/conftest.py` (the per-test cache dir is now `tmp_path_factory.mktemp("xdg-cache")`), `plugin/crew/tests/crew_fixtures.py` (one comment), `plugin/crew/tests/test_pwsh_cache_isolation.py` (the static guard judges values and returned environments, reports unreadable suites), `CHANGELOG.md` (L-0557's entry, five lines longer) and the version files (crew 1.0.96: 1.0.95 is also claimed by L-0558, #293). Body `path:line` citations into those files were moved by difflib from `d9ccfd5a` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local): none in this map (all 10 are `CHANGELOG.md` in crew.md). No hook or production script changed. No suite was executed for this note.

**Re-anchored `97ace923` / `9580571e` -> `550c39cd` on 2026-10-01 (L-0557 merges main 6fe0e0db: T-0505 #296 crew 1.0.92, runner auto-start #294; crew stays 1.0.96).** `550c39cd` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were refresh artifacts, version files and CHANGELOG only. This side's notes were anchored `97ace923` and main's `9580571e`; `git diff --name-only 9580571e 6fe0e0db` outside the refresh artifacts returns only the 1.0.92 version files and CHANGELOG, so main's notes already describe every non-artifact change it brings, and this side's notes describe L-0557's. Body `path:line` citations were moved by difflib, each from the anchor of the side whose copy of this map carries the line (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 17 moved - 10 `CHANGELOG.md` in crew.md (T-0505's 1.0.92 entry now sits below L-0557's) and 7 `plugin/crew/CONFIG.md` in verification-harness.md (T-0505's CONFIG.md edit), every one an exact-text match. No suite was executed for this note.

**Re-anchored `550c39cd` -> `038d5d10` on 2026-10-01 (L-0557 merges main 44d3dbc6: T-0110 #297, crew 1.0.97; L-0557 re-sets crew 1.0.99 at `4fc11923`).** `038d5d10` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were version files, CHANGELOG and one generated rules file. `git diff --name-only 6fe0e0db 44d3dbc6` outside the refresh artifacts returns T-0110's `.github/workflows/pytest-crew.yml`, `AGENTS.md`, `plugin/crew/tests/crew_fixtures.py` (new helpers below L-0557's, auto-merged), seven crew test files, CHANGELOG and the 1.0.97 version files. T-0110 updated verification-harness.md's `pytest-crew.yml` sentence itself; the other files are cited by name only. Body `path:line` citations were moved by difflib (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 10 moved, all `CHANGELOG.md` in crew.md (T-0110's 1.0.97 entry now sits below L-0557's), every one an exact-text match. No suite was executed for this note.

**Re-anchored `038d5d10` / `44d3dbc6` -> `90186613` on 2026-10-01 (L-0557 merges main 52489039 at `327e6ec1`: T-0040 #290, crew 1.0.98; L-0557 re-sets crew 1.0.101 at `90186613`).** `327e6ec1` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were refresh artifacts, version files, CHANGELOG, BUDGETS.md's count and `.crew/verify.json` (both sides appended one rule; both kept). Main's notes (anchor line `44d3dbc6`) were re-taken by T-0040 on its own merged tree `52489039`, so a line only in main's copy of a map is measured from `52489039`; a line in this side's copy is measured from `038d5d10`. Body `path:line` citations were moved by difflib (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 73 moved, all from this side's lines - `plugin/crew/README.md` (+11 lines from T-0040 above :743), `plugin/crew/CONFIG.md` (+11 from T-0040), `CHANGELOG.md` (T-0040's 1.0.98 entry, then this side's below it), `plugin/crew/tests/test_crew_config.py` and `plugin/crew/hooks/scripts/crew_config.py` (T-0040); every one an exact-text match, none on a changed line. T-0040's own claims about crew_shell.py, crew_status.py and the shell-route config are main's notes above and were not re-derived here. No suite was executed for this note.

**Re-anchored `89ebda03` (main) and `90186613` (L-0557) -> `773ce841` on 2026-10-01 (L-0557 merges main `05a679bf`, L-0558 #293, crew 1.0.102, at `2169bd11` with rerere disabled; L-0557 re-sets crew 1.0.105 at `773ce841`).** Both provenance histories are kept above, main's first. Body citations were re-checked by mapping each one from the tree its line came from (`89ebda03` for main's lines, `74dd1aa5` for L-0557's) to this tree with difflib: no citation moved. Citations into the version lines of `plugin/crew/.claude-plugin/plugin.json`, `plugin/PLUGINS.md` and `.claude-plugin/marketplace.json` keep their line numbers (the value changed in place). No suite was executed for this note.

**Re-anchored `0d159692` (main, L-0513 #301) and `773ce841` (L-0557) -> `a9608aa5` on 2026-10-01 (L-0557 merges main `cacf7ff0`, L-0513 #301: `scripts/gate-runner.py`, no plugin version; rerere disabled; crew stays 1.0.105).** Both provenance histories are kept, main's first. Where both sides had re-mapped the same citation, main's line was taken, and each citation was then mapped with difflib from the tree its line came from (`cacf7ff0` for main's lines, `95036b4c` for L-0557's) to this tree: no citation moved. No suite was executed for this note.

**Re-anchored `a9608aa5` -> `c43a9ce3` on 2026-10-01 (L-0557 merges main `ddcbf90d`, W-0115 #299, crew 1.0.106, at `0597e5c6` with rerere disabled, and re-sets crew 1.0.111 at `c43a9ce3`).** The merge touched no code map. `git diff --name-only a9608aa5 c43a9ce3` outside refresh artifacts is W-0115's `plugin/crew/tests/sabotage.py`, `sabotage_shell.py` and `.crew/verify.json` plus the version files and CHANGELOG; each citation into a changed file was mapped with difflib from `92448f1a` to this tree: no citation moved. No suite was executed for this note.

**Re-anchored `5ffffbe3` (main, L-0516 #298) and `c43a9ce3` (L-0557) -> `6053b65d` on 2026-10-01 (L-0557 merges main `2906dcbd`, L-0516 #298, crew 1.0.110, at `2f3fb34c` with rerere disabled, and re-sets crew 1.0.114 at `6053b65d`).** Both provenance histories are kept, main's first, and main's body citations were taken where both sides had re-mapped the same one. Each citation into a changed file was then mapped with difflib from the tree its line came from (`2906dcbd` for main's lines, `a54ff87b` for L-0557's) to this tree: no body citation moved; the `.crew/verify.json:460-466` range in L-0516's provenance note was kept, because it describes that tree. No suite was executed for this note.

**Re-anchored `6053b65d` -> `17dc6d23` on 2026-10-01 (L-0574, built on origin/main `ffd11270`: `review_checks.py` and `review_run.py`'s `prereview_gate`, no plugin version yet).** Every citation into a file L-0574 changed (`review_run.py`, `commands/review.md`, `plugin/crew/README.md`, `.crew/verify.json` - which gained a top-level `preReview` block above `rules`, so every rule citation moved by 27 lines - `docs/external-tool-formats.md`, `tests/sabotage.py`, `tests/test_review_contracts.py`, `BUDGETS.md`, `CHANGELOG.md`, the lifecycle diagram) was mapped with difflib from `ffd11270` to `17dc6d23`; `BUDGETS.md:10-11` is the changed count line itself and keeps its number. The verify map still has 44 rules; `preReview` is read by `review_run.py`, not the Stop gate.
