anchor: useful-claude-add-ons@62b1c7a

# localgpu

Local models on the user's own GPU via Ollama. Two halves that never call
each other directly, both reaching the same Ollama server on loopback.

## Two independent process trees, one shared Ollama

**DERIVED, confirmed by reading the entry points:**

1. **The MCP half.** Claude Code spawns `plugin/localgpu/mcp/server.py` as a
   stdio child (via the venv's Python interpreter, per the `.mcp.json`
   template — see below). It exposes three tools —
   `search_code`, `index_status`, `index_refresh` (docstring at
   `plugin/localgpu/mcp/server.py:1-10`) — and talks to Ollama over HTTP on
   `127.0.0.1:11434`.
2. **The `localgpu shell` half.** `cmd_shell` in
   `plugin/localgpu/cli/localgpu_cli.py:97-129` builds an `anthropic_proxy`
   server (`make_server(...)`, line 102) and runs it **on a background
   thread inside the CLI process itself** — `threading.Thread(target=server.serve_forever, daemon=True)`
   at line 114, not a subprocess. It then spawns a **second, separate Claude
   Code process** via `subprocess.run([claude, *args.claude_args], env=_child_env(base_url))`
   at line 125, with `ANTHROPIC_BASE_URL` pointed at the loopback proxy port
   (`_child_env`, lines 82-91) so only that child session talks to the local
   model — the parent session and crew's own config are untouched (module
   docstring, lines 1-10).

Both halves end up at the one Ollama server. **JUDGEMENT:** that shared
endpoint is exactly why `OLLAMA_MAX_LOADED_MODELS=1` and the split
`keep_alive` (seconds for embed calls, minutes for chat) exist at all — an 8
GB card cannot keep an embedding model and a 7B chat model resident at once,
so whichever half asked last has to be free to evict the other's model
without a manual step.

## `check_embed_model` — corrected line numbers

The ground truth handed into this task cited `mcp/indexer.py:266-281` for the
function and `:354` as its refresh-path call site. Re-checked against source:

- **DERIVED.** `check_embed_model` is defined at
  `plugin/localgpu/mcp/indexer.py:240-290`. Lines 266-281 do fall inside it
  (the tail of its docstring and the first `raise EmbedModelMismatch` branch),
  so that part of the citation is close enough to trust, if not the tightest
  possible anchor.
- **DERIVED, this part is wrong and is corrected here.** The refresh path
  does not call `check_embed_model` directly at any `:354`. It calls the
  instance method `Indexer._check_embed_model` (defined
  `plugin/localgpu/mcp/indexer.py:315-328`), which itself calls the shared
  `check_embed_model` function at line 328. `_check_embed_model` is invoked
  from `Indexer.refresh()` at **line 403**
  (`self._check_embed_model()`, inside `def refresh(...)` starting line 401)
  — confirmed by `grep -n "_check_embed_model()"`, which returns exactly one
  call site, line 403.
- **DERIVED, the search path citation holds.** `plugin/localgpu/mcp/server.py:109`
  calls `check_embed_model(...)` directly (the call spans lines 109-113),
  inside `search_code`, guarded by a live-count check and before any
  embedding request is sent to Ollama (`_client(settings).embed(...)` comes
  after, line 116).

So both claims in the "runs on both paths before any Ollama call" framing are
still true — search calls it directly before embedding a query; refresh calls
it (one level removed, via `_check_embed_model`) before touching the
filesystem or Ollama in `refresh()`. Only the exact line number for the
refresh call site (`:354` claimed, `:403` actual) was wrong.

## `ignore` / `unignore` / `.gitignore` — three layers, checked against source

The version at the previous anchor (`c635aca`) predates all of this; `config.py`
changed substantively since (0.1.8 -> 0.1.9, `plugin/localgpu/.claude-plugin/plugin.json`
and `pyproject.toml`), and this section replaces what the old map did not cover.

**DERIVED.** `DEFAULT_IGNORE` (`plugin/localgpu/mcp/config.py:30-87`) now carries a
block of credential patterns appended after the original binary/vendor list:
`.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `credentials.json`
(lines 79-86). The comment directly above them (lines 72-78) gives the reason: the
indexer embeds file *contents* into an on-disk vector store, so a secret excluded
from git by name but missing from `DEFAULT_IGNORE` becomes a second, less-guarded
copy on disk on every machine the plugin is installed on. The same comment notes a
deliberate gap: `.env.*` does not catch the bare name `env.production` some tools
use instead, because that cannot be told apart from an ordinary dotted filename by
name alone — recorded as a known miss, not fixed.

**DERIVED.** A new `unignore` config key (added to `CONFIG_KEYS` via `DEFAULTS`,
`config.py:99`, and to `_LIST_KEYS`, line 112) subtracts from the effective
`ignore` list. Confirmed **pattern removal, not path exemption** —
`load_config`'s own docstring says so explicitly (`config.py:203-207`) and
`test_unignoring_a_liftable_default_lets_the_file_through`
(`mcp/_test/test_unignore.py:28-49`) proves it end to end: `"unignore": ["*.key"]`
lets a `.strings.key` file's *content* reach the embedder while a `.env` in the
same repo, not covered by the lifted pattern, stays excluded. `unignore` layers
as a union exactly like `ignore` does (`config.py:224-229`, and
`test_unignore_accumulates_across_layers_like_ignore`,
`mcp/_test/test_config.py`) and is type-checked the same way — a bare string
raises `ConfigError` rather than being shredded into single-character globs
(`test_unignore_as_a_bare_string_is_rejected_not_shredded`).

`.git`, `.localgpu`, and `node_modules` are an unliftable floor —
`UNLIFTABLE_IGNORE = frozenset({".git", ".localgpu", "node_modules"})`, defined
at `config.py:94` with its rationale in the comment immediately above
(`config.py:89-93`: "not a preference anyone holds ... a mistake"). Confirmed by
`test_unignore_cannot_lift_the_hard_floor` (`mcp/_test/test_config.py`) and by
`test_hard_floor_survives_an_unignore_attempt`
(`mcp/_test/test_unignore.py:52-71`), which additionally proves it at the content
level: a `node_modules/pkg/index.js` file's text never reaches the embedder even
when a repo config explicitly asks to lift `node_modules`.

**JUDGEMENT, correcting the brief handed into this task.** The claim that "a user
who tries to lift one is told, not silently ignored" does not hold against the
code as it stands. `load_config` computes `lifted = set(unignore) - UNLIFTABLE_IGNORE`
(`config.py:236`) and filters `ignore` against `lifted` — an unliftable name the
user listed in `unignore` is simply absent from `lifted`, with no `ConfigError`,
no log line, no return value flagging the rejection anywhere in `config.py`,
`indexer.py`, `server.py`, or `localgpu_cli.py` (checked by grepping all four for
`cannot lift`, `floor`, and `UNLIFTABLE_IGNORE` — the only hits are the docstring
and comment prose already cited above). The "telling" that exists is entirely in
documentation a human reads ahead of time — `commands/index.md:28-29` and
`skills/localgpu/SKILL.md`'s config table — not anything the running code
surfaces back to whoever wrote the unliftable name into `unignore`. Anyone
relying on the tool to notice and complain will not be told; they will just see
`.git` or `node_modules` still excluded and have to go read the docs to learn why.

**DERIVED, and this one predates the anchor rather than following it** — added by
commit `0131d0f0`, which is an ancestor of `c635aca8`, so the previous map's gap
here was an omission, not staleness. `iter_files` (`mcp/indexer.py:155-179`)
merges a `.gitignore` found directly under the root being walked into the active
pattern list before the `os.walk` (lines 169-171). Two limits are documented in
the block comment above `GITIGNORE_NAME` (`mcp/indexer.py:127-136`) and hold up
against the parsing code:
- **`!` negation is dropped, not applied.** `_parse_gitignore`
  (`mcp/indexer.py:140-152`) skips any line starting with `!` outright
  (`line.startswith("!")` in the same `continue` branch as comments and blanks) —
  a negated rule some other tool would use to re-include a path is silently
  discarded rather than acted on either way.
- **Nested `.gitignore` files below the root are not read.** `iter_files` reads
  `root / GITIGNORE_NAME` exactly once, before the walk starts, and the pattern
  list built from it (line 171) is the same one used for every directory the
  walk descends into — a `.gitignore` inside a subdirectory is never opened.

`test_secrets.py` (present at the anchor already, unmodified since) exercises the
`.gitignore` half of this alongside `DEFAULT_IGNORE`'s credential patterns,
asserting on embedder-received content rather than just the file list, for the
reason its module docstring gives: a file missing from the index proves nothing
about whether its bytes were the ones that never got read.

## Two gaps, recorded, not fixed

- **No `.mcp.json` exists anywhere in this repo.** Confirmed: a repo-wide
  search for `.mcp.json` under this checkout finds none. Only the template
  at `plugin/localgpu/skills/localgpu/templates/mcp.json` exists. Per
  `plugin/localgpu/commands/setup.md:114-144` (Step 6, "register the MCP
  server"), a human — or Claude Code following that command's prose — copies
  the template to the repo root as `.mcp.json` and substitutes three
  placeholders (`{{LOCALGPU_PYTHON}}`, `{{LOCALGPU_PLUGIN_ROOT}}`,
  `{{LOCALGPU_HOME}}`) with literal absolute paths, because `.mcp.json` is
  read by Claude Code directly, not by a shell, so `${CLAUDE_PLUGIN_ROOT}`
  or `~` left in the file resolve to nothing. **No script performs this
  substitution.** "Per-repo, never plugin-level" (setup.md's own framing,
  line ~148) is prose a human or an LLM follows, not a rule any code
  enforces.
- **`bootstrap.ps1` vs `bootstrap.sh` — see the verdict below.** Both
  scripts' header comments assert they are "the same six steps, same order,
  same flag names" (`plugin/localgpu/bootstrap.sh:2`,
  `plugin/localgpu/bootstrap.ps1:3`). This task read both in full to check
  that claim rather than repeating it.

## bootstrap.ps1 vs bootstrap.sh — verdict: the "twin" claim holds

**DERIVED**, from reading both files end to end
(`plugin/localgpu/bootstrap.sh`, 944 lines; `plugin/localgpu/bootstrap.ps1`,
891 lines).

**Structurally faithful:**
- Same six steps, same order, same numbering in output (`1/6` NVIDIA driver
  through `6/6` VERIFY) — `bootstrap.sh:910-926`, `bootstrap.ps1:854-871`.
- Same flag *meanings* under each shell's own convention:
  `--yes/-y` ↔ `-Yes`, `--dry-run` ↔ `-DryRun`, `--skip-models` ↔
  `-SkipModels`, `--verify-only` ↔ `-VerifyOnly`, `--install-root` ↔
  `-InstallRoot`, `--help/-h` ↔ `-Help` (bash: lines 62-73; ps1: lines
  44-51). PascalCase-with-no-dashes vs. kebab-case-with-dashes is the
  correct idiom per shell, not a drift.
- Same model constants (`nomic-embed-text`, `qwen2.5-coder:7b-instruct-q4_K_M`),
  same install root shape (`$LOCALGPU_HOME/venv`, `/index`), same
  editable-install self-check logic for the `localgpu` console script
  (compares `localgpu_cli.__file__`'s real path against `$SCRIPT_DIR/cli` —
  bash `bootstrap.sh:552-571`, ps1 `bootstrap.ps1:524-550`, byte-for-byte the
  same embedded Python).
- Same GPU-offload assertion (`assert_on_gpu` / `Assert-ModelOnGpu`) with the
  same ordering bug they both deliberately avoid: checking for `*CPU*` before
  `*GPU*` so a partial split like `38%/62% CPU/GPU` is caught rather than
  matched as a pass — both scripts carry the identical comment explaining why
  the order matters (`bootstrap.sh:788-790`, `bootstrap.ps1:721-723`).

**One real behavioral asymmetry found, worth flagging as JUDGEMENT (minor,
not a defect):** the bash script's `embed_dimension` (lines 739-758) has a
three-way outcome in `verify()` (lines 870-877): dimension parsed → pass;
no parser found but the body looks like it contains an embedding → **warn
and continue**; no embedding-shaped content at all → **die**. The
`"no JSON parser was available"` warn-only branch exists because Git Bash
ships without `python3` and this script cannot assume one is resolvable.
PowerShell's `Get-EmbedDimension` (`bootstrap.ps1:669-687`) has no equivalent
tolerant branch — `ConvertFrom-Json` is always available on PowerShell 5.1+,
so `Invoke-Verification` (`bootstrap.ps1:808-813`) either gets a dimension or
calls `Stop-Bootstrap` outright. This is not a bug: the case the bash
tolerance branch exists for (no parser found) cannot occur on PowerShell.
But it means the two scripts are not byte-for-byte equivalent state machines
in this one corner — ps1 is strictly stricter here because it never needs to
be lenient.

Platform-specific steps that differ by necessity, not drift: Ollama install
(`curl | sh` vs. `winget install --id Ollama.Ollama -e`), PATH persistence
(profile files vs. the registry `User` environment scope plus a
`Sync-ProcessPath` replay), and `bootstrap.sh`'s extra
`check_other_root_duplicate` (lines 266-287) — needed only because Git Bash
on Windows can reach *both* the POSIX-style default root and the Windows
default root, a possibility that does not exist for a native PowerShell
process.

**Verdict: the "same six steps, same order, same flag names" claim in both
headers is accurate.** The one asymmetry above is a justified simplification
on the Windows side, not evidence the pair has drifted apart.
