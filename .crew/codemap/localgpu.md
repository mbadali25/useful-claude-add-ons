anchor: useful-claude-add-ons@1f97e51c

# localgpu

Local models on the user's own GPU via Ollama. Two halves that never call
each other directly, both reaching the same Ollama server on loopback.

Plugin version at this anchor: **0.1.18** — **DERIVED**,
`plugin/localgpu/.claude-plugin/plugin.json:3` and
`plugin/localgpu/pyproject.toml:7`, which agree.

## Re-anchor provenance - 3167721f -> 1f97e51c, 2026-09-06

The per-path check named four changed files
(`plugin/localgpu/.claude-plugin/plugin.json`,
`plugin/localgpu/cli/localgpu_cli.py`, `plugin/localgpu/commands/setup.md`,
`plugin/localgpu/mcp/ollama.py`), and this pass re-read every cited file, not
only those four. That was the right call: **the single worst claim in the note
was in a file that did not change** — see "the floor refuses out loud" below.

**What actually changed in the code:**

- `plugin/localgpu/cli/localgpu_cli.py` grew three subcommands — `prompt`,
  `models`, `mcp-init` — and +322/-1 lines (`git diff --numstat`), moving every line number
  below the old `cmd_proxy`. All of them are corrected here.
- `plugin/localgpu/mcp/ollama.py`'s `generate` stopped collapsing a malformed
  200 into an empty answer.
- `plugin/localgpu/commands/setup.md` Step 6 was rewritten from "hand-substitute
  a template" to "run `localgpu mcp-init`", which falsifies one of the two gaps
  this note recorded.

**What changed about the note, with no code change behind it:**

- The `unignore` **JUDGEMENT was already false at the previous anchor**. The
  behaviour it described was replaced by commit `c7d7f8aa` ("localgpu 0.1.10:
  the unignore floor refuses out loud instead of dropping the entry"), which is
  an ancestor of `b56d41f` — so the *previous* re-anchor's per-path check
  (`b56d41f..3167721f`, correctly empty) could not have caught it, and the
  anchor before that had already been advanced past it. A per-path check only
  proves nothing moved **since the anchor**; it says nothing about a claim that
  went stale before the anchor was last set. That is the blind spot, and it is
  why this pass re-read unchanged files instead of trusting the empty diff.
- Two anchors did not resolve at all: `skills/localgpu/SKILL.md` (no such path
  — there is no top-level `skills/localgpu/`), and a quotation of
  `plugin/localgpu/commands/setup.md` at "line ~148" that was never a real
  citation. Both are corrected below.

**Not re-verified at this anchor:** nothing under
`plugin/localgpu/cli/anthropic_proxy.py` was read end to end; its three cited
lines were confirmed individually by grep and nothing more. No claim here rests
on running any of it — every DERIVED line below is a reading of source, not an
execution.

## Two independent process trees, one shared Ollama

**DERIVED, confirmed by reading the entry points:**

1. **The MCP half.** Claude Code spawns `plugin/localgpu/mcp/server.py` as a
   stdio child (via the venv's Python interpreter, per the `.mcp.json` entry —
   see below). It exposes three tools — `search_code`, `index_status`,
   `index_refresh` (`plugin/localgpu/mcp/server.py:73`, `:157`, `:187`) — and
   talks to Ollama over HTTP on `127.0.0.1:11434`.
2. **The `localgpu shell` half.** `cmd_shell` in
   `plugin/localgpu/cli/localgpu_cli.py:112-155` builds an `anthropic_proxy`
   server (`make_server(...)`, line 119) and runs it **on a background
   thread inside the CLI process itself** — `threading.Thread(target=server.serve_forever, daemon=True)`
   at line 130, not a subprocess. It then spawns a **second, separate Claude
   Code process** via `subprocess.run([claude, *args.claude_args], env=_child_env(base_url))`
   at lines 141-149, with `ANTHROPIC_BASE_URL` pointed at the loopback proxy port
   (`_child_env`, `plugin/localgpu/cli/localgpu_cli.py:98-109`) so only that
   child session talks to the local model — the parent session and crew's own
   config are untouched (module docstring, lines 1-21).

Both halves end up at the one Ollama server. **JUDGEMENT:** that shared
endpoint is exactly why `OLLAMA_MAX_LOADED_MODELS=1` and the split
`keep_alive` (seconds for embed calls, minutes for chat) exist at all — an 8
GB card cannot keep an embedding model and a 7B chat model resident at once,
so whichever half asked last has to be free to evict the other's model
without a manual step.

## Three one-shot subcommands that are neither half — new at 0.1.18

**DERIVED.** `plugin/localgpu/cli/localgpu_cli.py` now carries three
subcommands that start no proxy and no MCP server:

- `cmd_prompt` (`plugin/localgpu/cli/localgpu_cli.py:224-278`) — one question
  straight to `/api/generate`, answer on stdout. Its docstring and the module
  docstring (`plugin/localgpu/cli/localgpu_cli.py:3-10`) both state the point: nothing is retrieved first, so
  nothing can be checked against sources. The model label goes to **stderr**
  (`plugin/localgpu/cli/localgpu_cli.py:277`) so a pipeline gets the answer alone.
- `cmd_models` (`plugin/localgpu/cli/localgpu_cli.py:281-313`) — what this
  Ollama has pulled, marking which entries the config points at.
- `cmd_mcp_init` (`plugin/localgpu/cli/localgpu_cli.py:339-432`) — writes
  `<repo>/.mcp.json`. See the gaps section: this is the script whose absence
  the previous version of this note recorded as a gap.

**DERIVED.** `OllamaClient.generate` (`plugin/localgpu/mcp/ollama.py:150-196`)
no longer returns `str(data.get("response", ""))`. Two guards were added, and
they are the repo's "unknown collapsing into the safe-looking value" lesson
applied to a wire response:

- `plugin/localgpu/mcp/ollama.py:174` — a 200 with no `response` key raises
  `OllamaError` instead of printing a blank line as though the model had
  replied.
- `plugin/localgpu/mcp/ollama.py:188` — a `response` that is present but not a
  `str` (a `null`, list, or object) raises rather than being `str()`-ed into a
  Python repr and printed as the model's words. `""` stays valid: an empty
  string is a real answer.

Pinned by `test_a_200_with_no_response_field_is_an_error_not_an_empty_answer`,
`test_a_response_that_is_not_a_string_is_an_error_not_a_repr`, and
`test_a_genuinely_empty_response_is_still_returned`
(`plugin/localgpu/mcp/_test/test_ollama.py:170`, `:189`, `:206`).

## `check_embed_model` — line numbers, re-checked at this anchor

`plugin/localgpu/mcp/indexer.py` did not change between the anchor and HEAD;
these were re-resolved anyway and all four still land where the note said.

- **DERIVED.** `check_embed_model` is defined at
  `plugin/localgpu/mcp/indexer.py:240`.
- **DERIVED.** The refresh path does not call it directly. It calls the
  instance method `Indexer._check_embed_model`
  (`plugin/localgpu/mcp/indexer.py:315`), which itself calls the shared
  function. `_check_embed_model` is invoked from `Indexer.refresh()`
  (`plugin/localgpu/mcp/indexer.py:401`) at **line 403** — one call site,
  confirmed by grep.
- **DERIVED.** `plugin/localgpu/mcp/server.py:109` calls `check_embed_model(...)`
  directly inside `search_code`, before any embedding request is sent
  (`_client(settings).embed(...)` comes after, `plugin/localgpu/mcp/server.py:117`).

So it runs on both paths before any Ollama call — search directly, refresh one
level removed via `_check_embed_model`.

## `ignore` / `unignore` / `.gitignore` — three layers

`plugin/localgpu/mcp/config.py` last changed at commit `c7d7f8aa` (localgpu
0.1.10). The plugin is now at 0.1.18; the file has been stable across those
eight bumps.

**DERIVED.** `DEFAULT_IGNORE` (`plugin/localgpu/mcp/config.py:30-87`) carries a
block of credential patterns appended after the original binary/vendor list:
`.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `credentials.json`
(lines 79-86). The comment directly above them (lines 72-78) gives the reason: the
indexer embeds file *contents* into an on-disk vector store, so a secret excluded
from git by name but missing from `DEFAULT_IGNORE` becomes a second, less-guarded
copy on disk on every machine the plugin is installed on. The same comment notes a
deliberate gap: `.env.*` does not catch the bare name `env.production` some tools
use instead, because that cannot be told apart from an ordinary dotted filename by
name alone — recorded as a known miss, not fixed.

**DERIVED.** An `unignore` config key (in `DEFAULTS`,
`plugin/localgpu/mcp/config.py:96`, and in `_LIST_KEYS`, line 112) subtracts from
the effective `ignore` list. Confirmed **pattern removal, not path exemption** —
`load_config`'s own docstring says so explicitly
(`plugin/localgpu/mcp/config.py:203-207`) and
`test_unignoring_a_liftable_default_lets_the_file_through`
(`plugin/localgpu/mcp/_test/test_unignore.py:28-49`) proves it end to end:
`"unignore": ["*.key"]` lets a `.strings.key` file's *content* reach the embedder
while a `.env` in the same repo, not covered by the lifted pattern, stays
excluded. `unignore` layers as a union exactly like `ignore` does
(`plugin/localgpu/mcp/config.py:228-229`, and
`test_unignore_accumulates_across_layers_like_ignore` in
`plugin/localgpu/mcp/_test/test_config.py`) and is type-checked the same way — a
bare string raises `ConfigError` at `plugin/localgpu/mcp/config.py:180` rather
than being shredded into single-character globs
(`test_unignore_as_a_bare_string_is_rejected_not_shredded`).

`.git`, `.localgpu`, and `node_modules` are an unliftable floor —
`UNLIFTABLE_IGNORE = frozenset({".git", ".localgpu", "node_modules"})`, defined
at `plugin/localgpu/mcp/config.py:94` with its rationale in the comment
immediately above (`plugin/localgpu/mcp/config.py:89-93`). Confirmed by
`test_unignore_cannot_lift_the_hard_floor`
(`plugin/localgpu/mcp/_test/test_config.py`) and by
`test_hard_floor_survives_an_unignore_attempt`
(`plugin/localgpu/mcp/_test/test_unignore.py:52-71`), which additionally proves
it at the content level: a `node_modules/pkg/index.js` file's text never reaches
the embedder even when a repo config explicitly asks to lift `node_modules`.

### The floor refuses out loud — correcting this note's own JUDGEMENT

**DERIVED, and it reverses what this note said at the previous two anchors.**
The note claimed that "a user who tries to lift one is told, not silently
ignored" does *not* hold, that `load_config` computes
`lifted = set(unignore) - UNLIFTABLE_IGNORE` and quietly drops the entry, and
that the only "telling" lives in prose a human reads ahead of time. **All three
of those are false against the code, and were false at the previous anchor
too.**

`load_config` computes `refused = sorted(set(unignore) & UNLIFTABLE_IGNORE)`
(`plugin/localgpu/mcp/config.py:241`) and, if it is non-empty, raises
`ConfigError` naming every refused entry and giving the reason for each
(`plugin/localgpu/mcp/config.py:242-250`). The config does not load at all. Only
after that does it compute `lifted = set(unignore)`
(`plugin/localgpu/mcp/config.py:252`) — a plain set, with no subtraction left in
it, because the subtraction was replaced by the refusal. The comment at
`plugin/localgpu/mcp/config.py:236-240` says why in the repo's own terms:
"Silently discarding a directive the user wrote by hand is the failure this repo
keeps re-learning."

The documentation agrees with the code, which is the other half of the old claim
that was wrong: `plugin/localgpu/commands/index.md:28-30` says lifting the floor
"is a hard error rather than a line that quietly does nothing — the config fails
to load and names the entry." The config table the old note pointed at is at
`plugin/localgpu/skills/localgpu/SKILL.md:72` (**not** `skills/localgpu/SKILL.md`
— that path does not exist in this repo).

**JUDGEMENT on how this survived.** The stale claim outlived two re-anchors
because both relied on the per-path diff and neither re-read the file. The
per-path check answers "did anything move since the anchor"; it cannot answer
"was the claim true when the anchor was last set". A claim that inverts a
guard's behaviour — silent-drop versus hard-error — is exactly the kind that
sends a reader to add a warning that already exists, or to trust a `unignore`
config that will in fact refuse to load.

## `.gitignore` merging

**DERIVED.** `iter_files` (`plugin/localgpu/mcp/indexer.py:155-179`) merges a
`.gitignore` found directly under the root being walked into the active pattern
list before the `os.walk` (`plugin/localgpu/mcp/indexer.py:169-171`). Two limits
are documented in the block comment above `GITIGNORE_NAME`
(`plugin/localgpu/mcp/indexer.py:127-136`) and hold up against the parsing code:

- **`!` negation is dropped, not applied.** `_parse_gitignore`
  (`plugin/localgpu/mcp/indexer.py:140-152`) skips any line starting with `!`
  outright, in the same `continue` branch as comments and blanks — a negated
  rule some other tool would use to re-include a path is silently discarded
  rather than acted on either way.
- **Nested `.gitignore` files below the root are not read.** `iter_files` reads
  `root / GITIGNORE_NAME` exactly once, before the walk starts
  (`plugin/localgpu/mcp/indexer.py:169`), and the pattern list built from it
  (line 171) is the same one used for every directory the walk descends into — a
  `.gitignore` inside a subdirectory is never opened.

`plugin/localgpu/mcp/_test/test_secrets.py` (unmodified since the previous
anchor) exercises the `.gitignore` half of this alongside `DEFAULT_IGNORE`'s
credential patterns, asserting on embedder-received content rather than just the
file list, for the reason its module docstring gives: a file missing from the
index proves nothing about whether its bytes were the ones that never got read.

## `.mcp.json` — the gap closed at 0.1.18

**This section replaces a gap the previous version of this note recorded. The
gap is closed.**

**DERIVED, and it falsifies "No script performs this substitution".** A script
performs it: `localgpu mcp-init`. `_entry`
(`plugin/localgpu/cli/localgpu_cli.py:317-336`) builds the server entry with
every path already literal — the venv interpreter from
`localgpu_config.venv_python(home)`, `mcp/server.py` from `PLUGIN_ROOT`, and
`LOCALGPU_HOME` in the entry's `env` block, all backslashes normalised to `/`.
`cmd_mcp_init` (`plugin/localgpu/cli/localgpu_cli.py:339-432`) writes it, and
`plugin/localgpu/commands/setup.md:114-160` (Step 6) now instructs the operator
to run that command and says **"Do not hand-substitute a template"** in bold.

The three placeholders the old note listed (`{{LOCALGPU_PYTHON}}`,
`{{LOCALGPU_PLUGIN_ROOT}}`, `{{LOCALGPU_HOME}}`) still live in
`plugin/localgpu/skills/localgpu/templates/mcp.json`, but nothing in the
documented path substitutes them by hand any more.

**DERIVED.** `cmd_mcp_init`'s behaviour, all of it detect-before-act:

1. Refuses to write a registration that cannot spawn — it stats the interpreter
   and `mcp/server.py` first and names each missing path
   (`plugin/localgpu/cli/localgpu_cli.py:356-370`).
2. Merges rather than clobbers; invalid JSON, a non-object document, or a
   non-object `mcpServers` are each refused with their own message
   (`:373-389`).
3. Idempotent — an identical entry prints "already registered" and writes
   nothing, exit 0 (`:391-395`).
4. A *differing* entry is shown as a diff and left alone unless `--force`,
   because that difference is usually a version-pinned plugin path from an
   older localgpu (`:396-403`).
5. Adds `.mcp.json` to the repo's `.gitignore` by default, once
   (`_ignore`, `plugin/localgpu/cli/localgpu_cli.py:446-455`); `--no-gitignore`
   opts out.

**DERIVED — this is the repo's `open(p,"w")` landmine, fixed by ordering.**
`plugin/localgpu/cli/localgpu_cli.py:421-422` computes the whole payload into
`body` and only then opens the file:

```python
body = json.dumps(doc, indent=2) + "\n"
with io.open(target, "w", encoding="utf-8", newline="\n") as fh:
```

The comment above it (`plugin/localgpu/cli/localgpu_cli.py:406-420`) is explicit that nothing reaching that line
can make `json.dumps` raise *today*, and that the ordering is what keeps that a
fact about today rather than something the next editor must re-derive — because
`doc` is the user's whole `.mcp.json`, every other MCP server in it included.
`newline="\n"` is the CRLF landmine, closed on the same line.
`test_a_failed_serialisation_leaves_the_existing_mcp_json_intact`
(`plugin/localgpu/cli/_test/test_cli.py:925`) pins the order by making the
serialisation raise and checking the file survives.

**DERIVED, corrected.** The old claim "No `.mcp.json` exists anywhere in this
repo. Confirmed: a repo-wide search finds none" is now wrong in two ways. No
`.mcp.json` is **tracked** — `git ls-files` finds only the two templates
(`plugin/crew/skills/crew-setup/templates/mcp.json`,
`plugin/localgpu/skills/localgpu/templates/mcp.json`) — but one **exists in this
working tree**, untracked and ignored by `.gitignore:369`, written by
`mcp-init`. Its `args` path is pinned to plugin version `0.1.11` while the
plugin is at `0.1.18`, which is exactly the stale-pin case item 4 above exists
for; `mcp-init --force` re-pins it.

**JUDGEMENT, unchanged and still true.** "Per repo, never plugin-level"
(`plugin/localgpu/commands/setup.md:157-160`) remains prose, not a rule any code
enforces — nothing stops a future plugin from shipping a `.mcp.json`. The old
note cited this at "line ~148" with a hyphen the source does not have; the exact
text is "**Per repo, never plugin-level.**"

## bootstrap.ps1 vs bootstrap.sh — verdict: the "twin" claim holds

**DERIVED**, from a full read at the previous anchor; neither file has changed
since, and every citation below was re-resolved at this one. `wc -l` reports
**943** lines for `plugin/localgpu/bootstrap.sh` and **890** for
`plugin/localgpu/bootstrap.ps1` — the previous note said 944 and 891, off by one
each; the numbers here are `wc -l` on the working tree.

Both headers assert the pair is "the same six steps, same order, same flag
names" (`plugin/localgpu/bootstrap.sh:2`, `plugin/localgpu/bootstrap.ps1:3`).

**Structurally faithful:**
- Same six steps, same order, same numbering in output (`1/6` NVIDIA driver
  through `6/6` VERIFY) — `plugin/localgpu/bootstrap.sh:910`,
  `plugin/localgpu/bootstrap.ps1:854-855`.
- Same flag *meanings* under each shell's own convention:
  `--yes/-y` ↔ `-Yes`, `--dry-run` ↔ `-DryRun`, `--skip-models` ↔
  `-SkipModels`, `--verify-only` ↔ `-VerifyOnly`, `--install-root` ↔
  `-InstallRoot`, `--help/-h` ↔ `-Help` (`plugin/localgpu/bootstrap.sh:62-73`;
  `plugin/localgpu/bootstrap.ps1:44-51`). PascalCase-with-no-dashes vs.
  kebab-case-with-dashes is the correct idiom per shell, not a drift.
- Same model constants (`nomic-embed-text`, `qwen2.5-coder:7b-instruct-q4_K_M`),
  same install root shape (`$LOCALGPU_HOME/venv`, `/index`), same
  editable-install self-check logic for the `localgpu` console script
  (compares `localgpu_cli.__file__`'s real path against `$SCRIPT_DIR/cli` —
  `plugin/localgpu/bootstrap.sh:552-571`, `plugin/localgpu/bootstrap.ps1:524-550`,
  byte-for-byte the same embedded Python).
- Same GPU-offload assertion (`assert_on_gpu` / `Assert-ModelOnGpu`) with the
  same ordering bug they both deliberately avoid: checking for `*CPU*` before
  `*GPU*` so a partial split like `38%/62% CPU/GPU` is caught rather than
  matched as a pass — both scripts carry the identical comment explaining why
  the order matters (`plugin/localgpu/bootstrap.sh:788-790`,
  `plugin/localgpu/bootstrap.ps1:721-723`).

**One real behavioral asymmetry, JUDGEMENT (minor, not a defect):** the bash
script's `embed_dimension` (`plugin/localgpu/bootstrap.sh:739`) has a three-way
outcome in `verify()` (`plugin/localgpu/bootstrap.sh:870-877`): dimension parsed
→ pass; no parser found but the body looks like it contains an embedding →
**warn and continue**; no embedding-shaped content at all → **die**. The
`"no JSON parser was available"` warn-only branch exists because Git Bash ships
without `python3` and this script cannot assume one is resolvable. PowerShell's
`Get-EmbedDimension` (`plugin/localgpu/bootstrap.ps1:669`) has no equivalent
tolerant branch — `ConvertFrom-Json` is always available on PowerShell 5.1+, so
`Invoke-Verification` (`plugin/localgpu/bootstrap.ps1:808-813`) either gets a
dimension or calls `Stop-Bootstrap` outright. This is not a bug: the case the
bash tolerance branch exists for cannot occur on PowerShell. But the two are not
byte-for-byte equivalent state machines in this one corner — ps1 is strictly
stricter here because it never needs to be lenient.

Platform-specific steps that differ by necessity, not drift: Ollama install
(`curl | sh` vs. `winget install --id Ollama.Ollama -e`), PATH persistence
(profile files vs. the registry `User` environment scope plus a
`Sync-ProcessPath` replay), and `bootstrap.sh`'s extra
`check_other_root_duplicate` (`plugin/localgpu/bootstrap.sh:266-287`) — needed
only because Git Bash on Windows can reach *both* the POSIX-style default root
and the Windows default root, a possibility that does not exist for a native
PowerShell process.

**Verdict: the "same six steps, same order, same flag names" claim in both
headers is accurate.**

**Unknown, recorded rather than asserted:** neither bootstrap was re-read end to
end at this anchor. The verdict above rests on the previous anchor's full read
plus the fact that `git diff --name-only 3167721f..1f97e51c` names neither file,
and on the twelve individual citations re-resolved here. If either script
appears in a future diff, the verdict is spent.

**Unknown:** Step 6 of both bootstraps was not checked against
`plugin/localgpu/commands/setup.md`'s rewritten Step 6. The command file now
says to run `localgpu mcp-init`; whether either bootstrap still describes the
old template-substitution route was not established at this anchor.

## Entry points

All re-resolved at this anchor; every `localgpu_cli.py` line below moved.

- `plugin/localgpu/mcp/server.py:253` — `main()`, which calls `mcp.run("stdio")`
  at `:254`. Claude Code spawns this as a stdio child using the venv interpreter
  named in the repo's `.mcp.json`
- `plugin/localgpu/mcp/server.py:73` — `search_code`, MCP tool
- `plugin/localgpu/mcp/server.py:157` — `index_status`, MCP tool
- `plugin/localgpu/mcp/server.py:187` — `index_refresh`, MCP tool
- `plugin/localgpu/cli/localgpu_cli.py:568` — `main()`, the `localgpu` console
  script declared at `plugin/localgpu/pyproject.toml:16` (was `:247`)
- `plugin/localgpu/cli/localgpu_cli.py:112` — `cmd_shell`, starts the proxy on a
  background thread in THIS process and launches a child Claude Code against it
  (was `:100`)
- `plugin/localgpu/cli/localgpu_cli.py:158` — `cmd_proxy`, the same proxy in the
  foreground with no child session (was `:146`)
- `plugin/localgpu/cli/localgpu_cli.py:224` — `cmd_prompt`, one ungrounded
  question to `/api/generate` (new)
- `plugin/localgpu/cli/localgpu_cli.py:281` — `cmd_models`, what Ollama has
  pulled (new)
- `plugin/localgpu/cli/localgpu_cli.py:339` — `cmd_mcp_init`, writes
  `<repo>/.mcp.json` (new)
- `plugin/localgpu/cli/localgpu_cli.py:458` — `build_parser`, where every
  subcommand and its flags are declared
- `plugin/localgpu/bootstrap.sh` and `plugin/localgpu/bootstrap.ps1` — the
  install entry point, a matched pair

## Owns data

- `vectors.f16` — rows x dim little-endian float16, memmapped, via
  `plugin/localgpu/mcp/store.py:254`
- `meta.sqlite` — one row per chunk (path, line span, file sha256), via
  `plugin/localgpu/mcp/store.py:255`
- `refresh.lock` — the cross-process refresh lock, via
  `plugin/localgpu/mcp/store.py:149`
- `manifest.json` — records `embed_model` and `dim`; the record
  `check_embed_model` reads on every later call, written by
  `plugin/localgpu/mcp/indexer.py`'s `refresh()`
  (`plugin/localgpu/mcp/indexer.py:401`)
- all four live under `$LOCALGPU_HOME/index/`, resolved by
  `plugin/localgpu/mcp/config.py`

## Calls out to

- Ollama `/api/embed` at `plugin/localgpu/mcp/ollama.py:137` — text to vectors
- Ollama `/api/generate` at `plugin/localgpu/mcp/ollama.py:168` — the chat model,
  one shot, behind `cmd_prompt`
- Ollama `/api/tags` at `plugin/localgpu/mcp/ollama.py:200` — model presence
  check behind `list_models` (`:198`) and `require_models` (`:210`); **was cited
  as `:173`, which is now inside `generate`'s new guards**
- Ollama `/api/show` at `plugin/localgpu/cli/anthropic_proxy.py:286` — reads the
  model's own advertised context length
- Ollama `/api/chat` — the proxy's translation target,
  `plugin/localgpu/cli/anthropic_proxy.py:9` and the request at `:891`; default
  URL `http://127.0.0.1:11434` at `plugin/localgpu/cli/anthropic_proxy.py:45`
- the real `claude` binary as a child process at
  `plugin/localgpu/cli/localgpu_cli.py:141`, with `ANTHROPIC_BASE_URL` pointed at
  the loopback proxy (was `:129`)
