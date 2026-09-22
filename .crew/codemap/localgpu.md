anchor: useful-claude-add-ons@2b337296
verified: 2026-09-22

# localgpu

Local models on the user's own GPU via Ollama. Two halves that never call
each other directly, both reaching the same Ollama server on loopback.

Plugin version at this anchor: **0.1.20** — **DERIVED**,
`plugin/localgpu/.claude-plugin/plugin.json:3` and
`plugin/localgpu/pyproject.toml:7`, which agree. (Was `0.1.18`; both places
moved together and both were re-read at the 2026-09-22 pass below.)

**DERIVED, added at this pass, corrected after QA.** The two files agreeing is
not enforced by any code path in this plugin — nothing here reads `plugin.json`
at runtime. `localgpu_cli.py` and `server.py` both get their version string
from `_version.py` (`plugin/localgpu/mcp/_version.py`), which regexes
`version = "..."` out of `pyproject.toml` alone (`_PYPROJECT`/`_VERSION_RE`,
`plugin/localgpu/mcp/_version.py:31-32`) and is deliberately **not**
`importlib.metadata.version("localgpu")` — its own docstring says why: an
editable install's dist-info is a snapshot taken at `pip install -e` time and
does not refresh when `pyproject.toml` is edited, which this file's author says
was confirmed on their own machine (`plugin/localgpu/mcp/_version.py:10-13`).

**This pass first wrote that `plugin/localgpu/.claude-plugin/plugin.json:3` and
`plugin/localgpu/pyproject.toml:7` agreeing "is a marketplace registration
convention checked by `scripts/check-marketplace.py`" — that is false, caught
by QA, and worth recording exactly how.** `grep -rn pyproject scripts/` is
empty: nothing under `scripts/` reads `pyproject.toml` at all.
`check_plugin_manifests` (`scripts/check-marketplace.py:160-170`) does check a
`plugin.json` version, but against `marketplace.json`'s declared version for
that entry (`declared != entry["version"]` at
`scripts/check-marketplace.py:169`), not against `pyproject.toml`. So
`plugin/localgpu/.claude-plugin/plugin.json:3` agreeing with
`plugin/localgpu/pyproject.toml:7` specifically is checked by **nothing** —
not by `localgpu`'s own code (see above) and not by this repo's marketplace
gate either. It is an unenforced convention maintained by whoever edits the
version, full stop; the gate only catches `plugin.json` drifting from
`marketplace.json`, a different pair.

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
0.1.10) — confirmed at this pass: `git log -- plugin/localgpu/mcp/config.py`
still lists `c7d7f8aa` as the most recent commit touching this file. The
plugin is now at 0.1.20; **measured, not the version-number subtraction**, via
`git log --follow -p -- plugin/localgpu/.claude-plugin/plugin.json`, which
version-bump commit changed the `"version"` field after `c7d7f8aa`: six did —
`84e36829` (`0.1.11`), `b7b7101d` (`0.1.14`), `9338e89d` (`0.1.16`), `ac93221d`
(`0.1.18`), `76d10447` (`0.1.19`), `dade775e` (`0.1.20`) — several of them
skipping intermediate patch numbers, so `20 - 10 = 10` is not the right count
and was not used. The file has been stable across those six bump commits.

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
(`plugin/localgpu/mcp/_test/test_unignore.py:30-51` — was cited as `:28-49`, off by
2 lines at both ends; re-found by grepping the `def`, not by offset) proves it end
to end:
`"unignore": ["*.key"]` lets a `.strings.key` file's *content* reach the embedder
while a `.env` in the same repo, not covered by the lifted pattern, stays
excluded. `unignore` layers as a union exactly like `ignore` does
(`plugin/localgpu/mcp/config.py:228-229`, and
`test_unignore_accumulates_across_layers_like_ignore` in
`plugin/localgpu/mcp/_test/test_config.py`) and is type-checked the same way — a
bare string fails the `_LIST_KEYS` shape check at `plugin/localgpu/mcp/config.py:180`
and raises `ConfigError` at `:181-184` rather than being shredded into
single-character globs (`test_unignore_as_a_bare_string_is_rejected_not_shredded`).

`.git`, `.localgpu`, and `node_modules` are an unliftable floor —
`UNLIFTABLE_IGNORE = frozenset({".git", ".localgpu", "node_modules"})`, defined
at `plugin/localgpu/mcp/config.py:94` with its rationale in the comment
immediately above (`plugin/localgpu/mcp/config.py:89-93`). Confirmed by
`test_unignore_cannot_lift_the_hard_floor`
(`plugin/localgpu/mcp/_test/test_config.py`) and by
`test_hard_floor_survives_an_unignore_attempt`
(`plugin/localgpu/mcp/_test/test_unignore.py:54-82` — was cited as `:52-71`, which
undercounted the function by 11 lines and cut off before its content-level
assertions), which additionally proves it at the content level: a
`node_modules/pkg/index.js` file's text never reaches the embedder even when a
repo config explicitly asks to lift `node_modules`.

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

**DERIVED, re-checked at this anchor and changed.** No `.mcp.json` is **tracked**
— `git ls-files | grep mcp.json` still finds only the two templates
(`plugin/crew/skills/crew-setup/templates/mcp.json`,
`plugin/localgpu/skills/localgpu/templates/mcp.json`) — and the repo's
`.gitignore` still carries the `.mcp.json` line `mcp-init` writes
(`_IGNORE_NOTE`, `plugin/localgpu/cli/localgpu_cli.py:435-443`), but it moved to
`.gitignore:421` (was cited as `:369`; the file grew — it is 482 lines now).

**Correction, not just a re-point.** The pass that set the previous anchor
(`84976536`) reported an untracked `.mcp.json` actually present in the working
tree at that time, pinned to plugin version `0.1.11`. At this pass that file
**does not exist** — `ls .mcp.json` fails with "No such file or directory".
(`git check-ignore -v .mcp.json` was checked too, in this absent-file state,
and printed `.gitignore:421:.mcp.json	.mcp.json` — a pattern match against the
path, not a check against the filesystem. It was dropped as evidence for that
reason: it says nothing about whether the file is present, since it reasons
about `.gitignore` patterns, not about what's on disk. The present-file case
was not separately run here, only reasoned about from how the tool works.)
This is expected to be volatile: `.mcp.json` is per-machine, written only
after someone runs `mcp-init` in this exact working tree, and gitignored by
design (that is the whole point of the mechanism above) — so whether one exists
here is a fact about this checkout's history, not about the repo, and it is not
safe to assert as a standing claim. Treat any future observation of it the same
way: as a snapshot of this working tree at read time, not a repo fact.

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

## Six slash commands — new section, added at this pass

**DERIVED, from `git ls-files` under `plugin/localgpu/commands/` and each
file's frontmatter, not previously listed in this note.** `plugin.json`'s
`description` field claims "Six commands"
(`plugin/localgpu/.claude-plugin/plugin.json:4`) and `ls` confirms six files:

- `setup.md` (176 lines) — `allowed-tools: Read, Write, Edit, Bash, Glob`. The
  only command whose *own* `allowed-tools` include `Write`/`Edit`: venv,
  models, `.localgpu/config.json`, and (Step 6) `<repo>/.mcp.json` via
  `localgpu mcp-init` — see `.mcp.json` gap section above. **Corrected after
  QA:** it is not the only command that writes to disk — `index.md` below
  runs `index_refresh`, and the writes there (`vectors.f16`, `meta.sqlite`,
  `manifest.json`) happen inside the MCP server process the tool call reaches,
  not through this command's own `allowed-tools`.
- `index.md` (129 lines) — `allowed-tools: Read, Bash, Glob,
  mcp__localgpu__index_refresh, mcp__localgpu__search_code`. Drives the
  `index_refresh` MCP tool, which is a write path — the `vectors.f16`,
  `meta.sqlite` and `manifest.json` bullets under "Owns data" below, not the
  `.mcp.json`-writing paragraph further down that section (that one is about
  `cmd_mcp_init`, a different write). `setup.md` is not the only command that
  writes. Argument-hint is the quoted string `"[--full] [--root <path>]"`;
  corrected below — that quoting is commit `dade775e`, an ancestor of the
  *previous* anchor `84976536`, not a change made between `84976536` and this
  one. The `84976536..2b337296` diff over `plugin/localgpu/` is empty (see
  the full re-derivation provenance below), so nothing in `index.md` changed
  during this pass; the quoting was already in place and already documented
  in the `1f97e51c -> 84976536` provenance section further down.
- `search.md` (83 lines) and `ask.md` (81 lines) — both
  `allowed-tools: Read, Bash, Grep, mcp__localgpu__search_code`; `ask.md`'s
  description is explicit that its answer is "grounded in indexed excerpts",
  the opposite of `localgpu prompt`.
- `doctor.md` (184 lines) — `allowed-tools: Read, Bash, Glob,
  mcp__localgpu__search_code, mcp__localgpu__index_status`. Report-only, no
  `Write`/`Edit`. `WARN`s rather than `FAIL`s a missing `localgpu_cli` package
  because `mcp/server.py` never imports it
  (`plugin/localgpu/commands/doctor.md:79-82`), and separately `WARN`s when
  `OLLAMA_MAX_LOADED_MODELS` is unset or above 1 (`:158`).
- `crew.md` (229 lines) — `allowed-tools: Read, Bash, Grep`, report-only. States
  the boundary this whole plugin operates inside: `localgpu` is not one of
  crew's dev/QA providers. `crew.md` itself attributes the provider tuples to
  `plugin/crew/hooks/scripts/crew_config.py` (prose at
  `plugin/localgpu/commands/crew.md:29-30`), with the literal tuples
  `DEV_PROVIDERS = ("claude", "codex", "copilot")` /
  `QA_PROVIDERS = ("claude", "codex", "copilot")` quoted at `:33-34`.
  **Checked against the code, corrected after QA:**
  `plugin/crew/hooks/scripts/crew_config.py:126-127` only re-exports
  (`DEV_PROVIDERS = crew_state.DEV_PROVIDERS`); the tuples are actually
  *defined* at `plugin/crew/hooks/scripts/crew_state.py:1503-1504`.
  So `crew.md`'s own attribution to `crew_config.py` names the re-export, not
  the definition — true as far as it goes (that file does hold those names),
  but not where the literals live. This command also states it "writes
  nothing — not `.crew/config.json`, not an environment variable, not a shim
  on `PATH`" (`plugin/localgpu/commands/crew.md:9-10`).
  **Narrowed after QA, not "Unknown":** this note read `crew.md` through line
  40 (Step 0 and the opening of Step 1, including the provider-tuple block).
  The rest of its 229 lines — its account of which specific crew roles a 7B
  can and cannot take over — was not read at this pass.

`plugin.json`'s own description also states "No hooks and no agents; nothing
leaves 127.0.0.1" (`plugin/localgpu/.claude-plugin/plugin.json:4`); confirmed
by directory listing — `plugin/localgpu/` has no `hooks/` or `agents/`
directory.

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

**DERIVED, added at this pass — the `open(p, "w")` landmine, and this file is
immune to it, not by accident.** `VectorStore.compact()`
(`plugin/localgpu/mcp/store.py:620-674`) rewrites `vectors.f16` by writing to a
sibling temp file first — `temp = self.vectors_path.with_suffix(".f16.compacting")`
(`:637`), opened and written inside `with open(temp, "wb") as handle:` (`:639-648`)
— and only afterward calls `self._replace_vectors_file(temp)` (`:651`), which
`os.replace`s it into place with retries for a lingering Windows reader
(`_replace_vectors_file`, `:676` onward; its docstring names the Windows
`PermissionError` case explicitly). Because the write target is the *temp* file
and the live `vectors.f16` is only ever replaced atomically after that write
succeeds, a raising argument to `handle.write(...)` (line `:646`, inside the
`with`) costs the temp file, never the live one — this is the one write site
in the plugin the repo `CLAUDE.md`'s `open(p, "w")` landmine section names as
already immune, and reading the code confirms it: `compact()` never opens
`self.vectors_path` itself for writing.

`cmd_mcp_init`'s `.mcp.json` write (`plugin/localgpu/cli/localgpu_cli.py:421-422`,
documented above) is the opposite pattern — it opens the real target directly —
and is made safe a different way: by computing the full payload into `body`
*before* the `open()` call, not by writing through a temp file.

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

## Re-anchor provenance - 1f97e51c -> 84976536, 2026-09-22

**Narrow pass, and weaker evidence than the numbers below make it look.** Read
the caveat before the result.

The per-path check over this note's cited paths:

```
git diff --name-only 1f97e51c..HEAD -- \
  plugin/crew/skills/crew-setup/templates/mcp.json plugin/localgpu/ skills/localgpu/SKILL.md
```
```
plugin/localgpu/.claude-plugin/plugin.json
plugin/localgpu/commands/index.md
plugin/localgpu/pyproject.toml
```

Three files over a range of many commits. Every `path:line` citation in this
note was then re-resolved mechanically against HEAD and against `1f97e51c` and
compared byte-for-byte. **Two moved, and both are the same version string**:
`plugin/localgpu/.claude-plugin/plugin.json:3` and
`plugin/localgpu/pyproject.toml:7`, `0.1.18` -> `0.1.20`, corrected at the top
of this note. The third changed file, `plugin/localgpu/commands/index.md`,
changed only at its frontmatter `argument-hint`, which was quoted so the YAML
parses (`[--full] [--root <path>]` -> `"[--full] [--root <path>]"`); this note
cites that file only at `:28-30`, which is byte-identical.

Every other citation - across `bootstrap.sh`, `bootstrap.ps1`,
`cli/localgpu_cli.py`, `cli/anthropic_proxy.py`, `mcp/config.py`,
`mcp/indexer.py`, `mcp/ollama.py`, `mcp/server.py`, `mcp/store.py`, the four
`_test/` files, `commands/setup.md` and `skills/localgpu/SKILL.md` - resolves to
byte-identical text at both commits.

**Why that is a floor and not a measurement.** `1f97e51c` is one of the five
anchors `INDEX.md` records as *not* touched in the 2026-09-12 re-anchor pass and
*not* claimed fresh. So this pass proves exactly one thing: nothing this note
cites has changed since `1f97e51c`. It proves nothing at all about whether the
claims were true when they were written, and this note's own history is the
reason that distinction matters - the `unignore` JUDGEMENT recorded above was
already false at its anchor, was carried across a correctly-empty per-path
check, and was caught only by re-reading a file that had not changed. The same
blind spot is open here and has not been closed: **no file was re-read at this
pass.** A "1 of 83 citations moved" ratio reads like a strong freshness result
and is not one.

What that means for a reader: treat the line numbers as reliable and the
*claims* as last independently checked on 2026-09-06, sixteen days ago, by the
pass recorded above. This note is the least-verified of the four re-anchored
today and should be the first re-derived when someone has the budget for it.

Not re-verified at this pass: nothing was read, executed, imported or run.
No Ollama server was contacted, no index was built, neither bootstrap script was
run, and no test suite was executed. The `Not re-verified at this anchor` note
in the 2026-09-06 section above still stands - `cli/anthropic_proxy.py` has
still never been read end to end.

## Full re-derivation, 84976536 -> 2b337296, 2026-09-22

**This is the pass the section above said this note needed, and "the previous
pass" here means the narrow one directly above, not 2026-09-06 — those two are
not the same kind of pass and the note's own history says so.** The
2026-09-06 re-anchor (`3167721f -> 1f97e51c`, top of this note) did open every
cited file — that is the pass that caught the "floor refuses out loud" error
by re-reading `config.py` even though it had not changed. The narrow pass
immediately above (`1f97e51c -> 84976536`) is the one that advanced the anchor
on a per-path diff without opening the cited files, and says so itself ("no
file was re-read at this pass"). This pass opened every cited file, closing
the gap the narrow pass left open and bringing the claims themselves current
for the first time since 2026-09-06.

`git diff --name-only 84976536..2b337296 -- plugin/localgpu/` is empty — no
file this note cites changed in the underlying repo between the two commits.
That made this a pure re-read: every citation was checked against HEAD by
opening the file and either grepping for the cited symbol/string or reading
the surrounding lines directly, not by trusting the line number carried over
from the last pass.

**Counts, measured by diffing two greps of this file's own citations** — one
run against `git show 84976536:.crew/codemap/localgpu.md`, one against the
version on disk now, both with a single regex that matches any repo-relative
`path:line` citation regardless of which top-level directory it starts
under (requires at least one `/`, so it catches `plugin/localgpu/...`,
`plugin/crew/...` and `scripts/...` alike, in one pass rather than one regex
per prefix plus a manual add-on for whatever the regex missed — the
add-on approach is what produced the wrong count QA caught below):

```
grep -oE '[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+\.(py|md|sh|ps1|json|toml):[0-9]+(-[0-9]+)?' .crew/codemap/localgpu.md | sort -u | wc -l
```

plus `\.gitignore:[0-9]+` handled the same way separately (it is a single
path segment with an extension this regex's list does not include, so it
never matches and has to be counted on its own):

- **84 distinct `path:line` citations existed before this pass** (83 from the
  command above run against `git show 84976536:.crew/codemap/localgpu.md`,
  plus one `.gitignore:NNN`). All 84 were re-read against HEAD.
- **81 confirmed unchanged** — same file, same line(s), same claim, verified by
  opening the file (not by the empty `git diff` alone — see the `test_unignore.py`
  case below for why that distinction matters).
- **2 corrected** — both in `plugin/localgpu/mcp/_test/test_unignore.py`, both
  wrong by an amount too large to be a copy-paste slip and too small to be a
  different function: `test_unignoring_a_liftable_default_lets_the_file_through`
  was cited at `:28-49`, its `def` is at line 30 (off by 2 at the start, and the
  same 2 at the end since the function is exactly the length cited); and
  `test_hard_floor_survives_an_unignore_attempt` was cited at `:52-71`, its `def`
  is at line 54 and it runs to line 82, not 71 — the old citation cut off before
  the function's own content-level assertions, which are the specific thing the
  note's prose claims the test proves. **Neither error was catchable by the
  `1f97e51c -> 84976536` pass's "byte-for-byte identical at both commits" check**
  (see that section above): the file genuinely is byte-identical across that
  range, so the same wrong line numbers were wrong at both commits equally, and
  a diff of identical-but-wrong text against itself reports no problem. Byte
  comparison across commits proves nothing about whether a citation was right
  to begin with — only re-reading the cited content against its own prose claim
  does, which is what this pass did differently.
- **1 re-pointed** — `.gitignore:369` -> `.gitignore:421`. The claim (that
  `mcp-init`'s `.gitignore` entry for `.mcp.json` is still present) still
  holds; `.gitignore` itself grew to 482 lines and the line moved.
- **1 claim invalidated by working-tree state, not by a code or repo change** —
  the previous pass reported an actual untracked `.mcp.json` present in this
  checkout, pinned to plugin version `0.1.11`. At this pass no such file exists
  in the working tree. Corrected in place rather than re-pointed, with a note
  that this specific fact is inherently checkout-local and should not be
  re-asserted as a standing claim about the repo (see the "Correction, not
  just a re-point" paragraph above).
- **1 refined for precision, not corrected** —
  `plugin/localgpu/mcp/config.py:180` is the `if` guard that leads to the
  bare-string `ConfigError`; the `raise` itself is at `:181-184`. The original
  claim was not false, just anchored to the condition rather than the
  statement it guards; both are now cited.
- **13 new distinct citations added**, for material this note did not
  previously cover at all (see "Six slash commands", the `store.py`
  write-safety paragraph, and the `_version.py`/`plugin.json` version
  paragraph at the top) — **corrected twice by QA, this is the version the
  command above actually produces.** The command run against the current
  file returns 96; against the pre-pass version it returns 83; 81 of those
  are common to both (the "confirmed unchanged" count above), so
  `96 - 81 = 15` raw new lines, minus the 2 that are the corrected
  `test_unignore.py` replacements already counted above (not new content,
  a re-pointed citation for existing content) leaves **13**. Listed in full:
  `plugin/localgpu/.claude-plugin/plugin.json:4`,
  `plugin/localgpu/cli/anthropic_proxy.py:947`,
  `plugin/localgpu/cli/localgpu_cli.py:435-443`,
  `plugin/localgpu/commands/crew.md:9-10`, `:29-30`,
  `plugin/localgpu/commands/doctor.md:79-82` (and `:158`, cited in shorthand),
  `plugin/localgpu/mcp/store.py:620-674` (and its internal `:637`, `:639-648`,
  `:646`, `:651`, `:676`, cited in shorthand),
  `plugin/localgpu/mcp/_version.py:10-13`, `:31-32`,
  `plugin/crew/hooks/scripts/crew_config.py:126-127`,
  `plugin/crew/hooks/scripts/crew_state.py:1503-1504`, and, both written out
  in full rather than one of them in shorthand,
  `scripts/check-marketplace.py:160-170` and `scripts/check-marketplace.py:169`.
  The first version of this bullet said 9 and listed 7 (both wrong, an
  earlier miscount); the QA round after that said 12 and described the
  `crew_state.py` citation above as falling outside the `plugin/` regex used
  above, when it in fact matches that regex (it starts with `plugin/crew/`)
  and was already in that regex's output — the "outside the regex, tallied
  separately" split was the error, not the citation. Unifying the regex to
  match any repo-relative path in one pass, as done above, removes the need
  for that kind of manual add-on and the place it went wrong.

**What this closes.** The task instruction for `plugin/localgpu/mcp/store.py`
around line 646 and `plugin/localgpu/cli/localgpu_cli.py`'s write ordering is
now recorded in the note itself (the "Owns data" section and the existing
`cmd_mcp_init` write-safety paragraph respectively) rather than only in this
repo's `CLAUDE.md`; both were verified by reading the code, not assumed from
that document's description.

### QA block, fixed in place, same day

QA blocked the first version of this pass with ten findings (4 BLOCK, 4 FIX,
2 NIT), all against content this pass itself had added or changed — not
against anything carried over from an earlier anchor. All ten were re-checked
by opening the named files and fixed in place; the counts above and every
section they reference already reflect the fixes, not the original mistakes.
For the record, what was wrong and how it was found:

1. **False tool-coverage claim.** This note first said the plugin manifest's
   version field and the Python project file's version field
   (`plugin/localgpu/.claude-plugin/plugin.json:3` and
   `plugin/localgpu/pyproject.toml:7`) agreeing "is a marketplace registration
   convention checked by `scripts/check-marketplace.py`".
   `grep -rn pyproject scripts/` is empty; `check_plugin_manifests` checks
   `plugin.json` against `marketplace.json`, not against `pyproject.toml`.
   Nothing checks that specific pair. Fixed in the version paragraph at the
   top of this note.
2. **Wrong attribution of an unrelated commit's timing.** The new "Six slash
   commands" section called `index.md`'s argument-hint quoting "the one
   substantive text change between the previous anchor and this one" — but
   that quoting is commit `dade775e`, an ancestor of the *previous* anchor
   (`84976536`), already documented in the `1f97e51c -> 84976536` section
   further down. Fixed to say so and point at the existing section instead of
   re-claiming the change for this pass.
3. **Self-contradiction about the note's own history.** The new provenance
   section said "the previous two re-anchors ... advanced the anchor on a
   per-path diff without opening the cited files" — true of the narrow pass
   directly above, false of the 2026-09-06 pass, which this note's own top
   section says re-read every cited file. Fixed to name only the narrow pass.
4. **Wrong line numbers plus an overstated read.** `crew.md`'s provider
   tuples were cited at `plugin/localgpu/commands/crew.md:29-30` (that is the
   prose sentence introducing them); the literal tuples are at `:33-34`.
   Re-read `crew_config.py`: `DEV_PROVIDERS`/`QA_PROVIDERS` there are a
   re-export (`plugin/crew/hooks/scripts/crew_config.py:126-127`,
   `DEV_PROVIDERS = crew_state.DEV_PROVIDERS`), not the definition — that is
   `plugin/crew/hooks/scripts/crew_state.py:1503-1504`. Also narrowed the
   "read only past the opening constraint (lines 1-32)" claim: this pass
   read through line 40, which is where the code block with the tuples ends.
5. **Version-number subtraction presented as a count.** "Stable across those
   eight bumps" (from an older pass, comparing `0.1.10` to `0.1.18`) was left
   unfixed while the version paragraph above it had already moved to
   `0.1.20`. Measured properly with
   `git log --follow -p -- plugin/localgpu/.claude-plugin/plugin.json`: six
   commits changed the version field after `c7d7f8aa` (`0.1.10`), several
   skipping patch numbers, so neither the old "eight" nor a naive `20-10=10`
   is the right count. Fixed to "six bump commits", named.
6. **Count and list did not match.** "9 new distinct citations added" was
   followed by a list of 7, and omitted two citations this pass had actually
   added (`plugin/localgpu/cli/anthropic_proxy.py:947` and
   `plugin/localgpu/cli/localgpu_cli.py:435-443`) because the list was
   written before the last few edits and never re-measured. Re-ran the same
   `comm`-based measurement used for the rest of this section against the
   fully-fixed file and corrected the count and list to match — see the
   "new distinct citations added" bullet above, in the "Counts" block, for
   the number and method (that bullet went through a second correction on
   the next QA round; see below).
7. **Overclaimed exclusivity.** "The only command that writes" (`setup.md`)
   ignored that `index.md` runs `index_refresh`, which writes `vectors.f16`,
   `meta.sqlite` and `manifest.json`. Narrowed to "the only command whose own
   `allowed-tools` include `Write`/`Edit`" and cross-referenced `index.md`.
8. **Bare-basename anchors.** The plugin manifest and project-file version
   citations in the new version paragraph, and the `config.py` citation in
   the counts section, were not repo-relative. Made all of them fully
   repo-relative wherever restated — including, on the next QA round, the
   ones this very QA block had introduced by restating the bad form instead
   of describing it (this repo's own `CLAUDE.md` says to describe the bad
   form, never show it, because a checker cannot tell a quoted
   counter-example from a broken citation — this list did the latter and
   was fixed).
9. **Evidence that doesn't discriminate, and an overclaim about how that was
   checked.** `git check-ignore -v .mcp.json` was offered as evidence the
   file does not exist. Only the absent case was actually run (the file was
   absent in this working tree at the time); the claim that it "prints the
   same pattern match regardless of whether the file is present" asserted
   the present case too, without running it. `git check-ignore` matches a
   path against `.gitignore` patterns lexically — it does not stat the
   path — so the present case is expected to behave the same way, but that
   is reasoning about the tool, not a second observed run, and the note
   should not have implied otherwise. Dropped `check-ignore` as evidence
   either way; `ls .mcp.json` failing is what the claim now rests on, and is
   itself a direct observation of presence/absence.
10. **Miscased quote.** `plugin.json`'s description says "Six commands"
    (capital S); this note quoted it lowercase. Fixed to match the source
    exactly.

### Second QA round, same day — each finding right about its target, wrong one line over

Re-review of the fixes above found four more, every one a new claim the *fix
itself* introduced rather than anything carried over. Consistent with this
repo's own lesson about re-reviewing a guard fix as hard as the guard: a fix
being correct about the specific thing it targeted is not the same as the
sentence around it staying correct.

1. **BLOCK — bare-basename anchors, reintroduced by the fix meant to remove
   them.** Item 8 above (and item 4's `crew_config.py`/`crew_state.py`
   citations, and item 6's `anthropic_proxy.py`/`localgpu_cli.py` citations)
   restated the bad bare-`name.py:N` form to describe what had been wrong,
   instead of using the repo-relative form or prose without the token shape —
   this repo's own `CLAUDE.md` says a checker cannot tell a quoted
   counter-example from a broken citation, so showing the bad form at all
   defeats the check regardless of intent. A new bare basename-form citation
   of the `crew_config.py` re-export line had also been added in the body
   text, at the "Six slash commands" `crew.md` bullet. Fixed all nine
   occurrences (checked
   with `grep -noE '`[A-Za-z0-9_.-]+\.(py|json|toml):[0-9]+(-[0-9]+)?'
   .crew/codemap/localgpu.md`, which now returns nothing) to either full
   repo-relative paths or prose describing the shape without reproducing it.
2. **FIX — the "12 new citations" method did not reproduce 12.** The bullet
   said `plugin/crew/hooks/scripts/crew_state.py:1503-1504` fell outside the
   `plugin/` regex the rest of the section used and was "tallied separately"
   — it does not; that path starts with `plugin/crew/`, which the regex
   already matches, and the citation was already in that regex's output. And
   `scripts/check-marketplace.py:169` was described as "cited in shorthand"
   when it is written out in full. Replaced the two-regex-plus-manual-add-on
   method with one regex that matches any repo-relative citation regardless
   of top-level directory, so the count is whatever running that one command
   produces rather than a hand-added total: 13, not 12, not 9. See the
   "Counts" block above for the exact command and arithmetic.
3. **NIT — wrong cross-reference.** The `index.md` bullet pointed
   `index_refresh`'s writes at "the `.mcp.json` writes note under 'Owns
   data'", but that paragraph is about `cmd_mcp_init`, a different write
   entirely. `index_refresh` writes `vectors.f16`, `meta.sqlite` and
   `manifest.json` — the bullets directly under the "Owns data" heading, not
   the paragraph further down it. Fixed to point at those bullets and name
   the `cmd_mcp_init` paragraph as the thing it is *not* pointing at, so a
   reader who checked the old reference and found it about the wrong thing
   does not repeat the same wrong turn.
4. **NIT — overclaim about what was tested.** The `.gitignore`/`.mcp.json`
   correction said `git check-ignore -v .mcp.json` was "tested ... against
   the actual (absent) file and confirmed it prints the same match regardless
   of whether the file is present" — only the absent case was run; the
   present case was never executed, so "confirmed ... regardless" overstated
   what happened. Narrowed to say only the absent case was observed, and that
   the present case is expected (not confirmed) to behave the same way
   because `check-ignore` matches a pattern against a path string, not
   against the filesystem.

**Not re-verified at this pass, same as every pass before it:** nothing was
executed. No Ollama server was contacted, no index was built, neither
bootstrap script was run, and no test suite was executed — every claim above
is a reading of source and of `git`/`grep`/`wc` output, not a run. `crew.md`
(229 lines) was read through line 40 (Step 0 and the opening of Step 1,
including the provider-tuple block at `:33-34`); its account of which
specific crew roles a 7B can and cannot take over (the rest of the file) was
not checked. `cli/anthropic_proxy.py` was read at every cited line (module
docstring, the `/api/show` context-length lookup, `_post_ollama`) but still not
end to end — `ProxyHandler` (`plugin/localgpu/cli/anthropic_proxy.py:947`,
including `_resolved_num_ctx` at `:975`) and the tool-call translation code
were located by grep only, not read.
