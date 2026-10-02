anchor: useful-claude-add-ons@fa63852d
verified: 2026-10-01

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
`.gitignore:428` (was cited as `:421` before T-0085 and `:369` before that; the file grew — it is 489 lines now).

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
  `plugin/crew/hooks/scripts/crew_config.py:129-130` only re-exports
  (`DEV_PROVIDERS = crew_state.DEV_PROVIDERS`); the tuples are actually
  *defined* at `plugin/crew/hooks/scripts/crew_state.py:1450-1451` on T-0028 at `c43a54c1`, where both
  tuples end in `"kimi"`, so the literal tuples localgpu quotes at `:33-34` are stale there
  (`TODO.md`'s T-0028 item (f)); `:1440-1441` before T-0028, since T-0010's four `AUTOPILOT_DEFAULTS`
  lines (T-0010-solo's merge of `67caa4b8`; `:1432-1433` at `65bb3330`; `:1430-1431` on main before
  T-0005's three import lines merged in, re-numbered
  from `:1540-1541` by crew 1.0 - see the re-anchor entries below; same two
  lines, `DEV_PROVIDERS = ("claude", "codex", "copilot")` /
  `QA_PROVIDERS = ("claude", "codex", "copilot")`, byte-identical).
  So `crew.md`'s own attribution to `crew_config.py` names the re-export, not
  the definition — true as far as it goes (that file does hold those names),
  but not where the literals live. This command also states it "writes
  nothing — not `.crew/config.json`, not an environment variable, not a shim
  on `PATH`" (`plugin/localgpu/commands/crew.md:9-10`).
  **Read in full at the 2026-09-25 pass (previously narrowed to line 40,
  "not Unknown").** `plugin/localgpu/commands/crew.md` is itself unchanged
  since `5d1fc5fd` (`git diff --name-only 5d1fc5fd..6c497a14 --
  plugin/localgpu/commands/crew.md` is empty), but its Step 2 table (`:99-107`)
  names eleven crew roles by name - `scribe`, `docs-writer`, `analyst`,
  `planner`, `developer`, `qa-reviewer`, `dba`, `infrastructure-architect`,
  `smoke-author`, `browser-tester`, `pm` - and **crew 1.0 (`6c497a14`) deleted
  every one of their agent definitions.** `git show --diff-filter=DR
  --name-status 6c497a14 -- plugin/crew/agents/` lists all eleven among fifty
  `D` (deleted) files; `plugin/crew/agents/` now holds only four:
  `explorer.md`, `researcher.md`, `reviewer.md`, `security.md` (`ls
  plugin/crew/agents/`), matching `.claude-plugin/marketplace.json`'s `crew`
  entry, which now describes "4 context-isolated agents (explorer, reviewer,
  security, researcher)" in place of the old tiered roster. **JUDGEMENT:** this
  makes most of `crew.md`'s Step 2 table stale documentation about a roster
  that no longer exists in this repo - not a broken citation (the file and its
  line numbers are exactly where this note says), but a claim whose subject
  matter was deleted out from under it. `explorer` and `researcher` still map
  to real agent files; `qa-reviewer`'s successor is `reviewer`, unnamed as such
  in the table; the other eight rows describe roles this repo no longer has.
  Whether `crew.md` should be rewritten for the 4-role roster is outside this
  note's scope (that file lives in `plugin/localgpu/`, not `plugin/crew/`, and
  fixing it is a decision, not a fact this codemap records) - flagged here
  because a reader trusting this note's summary of "which crew roles a 7B can
  take over" would be reasoning about roles this repo has removed.

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
  `plugin/crew/hooks/scripts/crew_config.py:127-128`,
  `plugin/crew/hooks/scripts/crew_state.py:1540-1541`, and, both written out
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
   re-export (`plugin/crew/hooks/scripts/crew_config.py:127-128`,
   `DEV_PROVIDERS = crew_state.DEV_PROVIDERS`), not the definition — that is
   `plugin/crew/hooks/scripts/crew_state.py:1540-1541`. Also narrowed the
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
   said `plugin/crew/hooks/scripts/crew_state.py:1540-1541` fell outside the
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

## Re-anchor provenance - 2b337296 -> 5d1fc5fd, 2026-09-22

Re-anchor only. Per-path check over this note's cited paths (extracted the
same way `_cited_paths` in `plugin/crew/hooks/scripts/crew_freshness.py`
would - every backtick-quoted repo-relative path in this file that still
exists):

```
git diff --name-only 2b337296..5d1fc5fd -- \
  plugin/localgpu/.claude-plugin/plugin.json plugin/localgpu/pyproject.toml \
  plugin/localgpu/mcp/_version.py scripts/check-marketplace.py \
  plugin/localgpu/cli/localgpu_cli.py plugin/localgpu/commands/setup.md \
  plugin/localgpu/mcp/ollama.py plugin/localgpu/cli/anthropic_proxy.py \
  plugin/localgpu/mcp/server.py plugin/localgpu/mcp/_test/test_ollama.py \
  plugin/localgpu/mcp/indexer.py plugin/localgpu/mcp/config.py \
  plugin/localgpu/mcp/_test/test_config.py plugin/localgpu/skills/localgpu/SKILL.md \
  plugin/localgpu/mcp/_test/test_secrets.py plugin/localgpu/skills/localgpu/templates/mcp.json \
  plugin/localgpu/cli/_test/test_cli.py plugin/crew/skills/crew-setup/templates/mcp.json \
  plugin/localgpu/bootstrap.sh plugin/localgpu/bootstrap.ps1 \
  plugin/crew/hooks/scripts/crew_config.py plugin/localgpu/mcp/store.py CLAUDE.md \
  plugin/localgpu/commands/index.md plugin/localgpu/mcp/_test/test_unignore.py
```
```
CLAUDE.md
scripts/check-marketplace.py
```

Two files moved. (Not stating a total citation count here: this note's own
`INDEX.md` entry warns that recording such a total changes it, and this
provenance paragraph itself adds new backtick-quoted paths to the file,
which would move the number again on the next mechanical count - re-run the
extraction instead of trusting a figure written here.) Both moved files were
checked:

- `CLAUDE.md`: this note has no `CLAUDE.md:<line>` citation anywhere in it -
  every reference is prose ("this repo's own `CLAUDE.md` says...") with no
  line number - so there is nothing in this note that the diff (a `render.sh`
  citation correction, per `CLAUDE.md`'s own changelog) could have moved.
  Nothing to correct.
- `scripts/check-marketplace.py`: this note cites `:160-170` (the whole
  `check_plugin_manifests` function) and `:169` (the `declared != entry["version"]`
  comparison) at lines 30 and 33, and again spelled out at line 736. The file
  grew by 394 lines between the two anchors (`wc -l scripts/check-marketplace.py`:
  1627 at HEAD, 1233 at `2b337296` — was miscounted as 396 in an earlier draft
  of this entry), but `grep -n "def
  check_plugin_manifests\|declared != entry" scripts/check-marketplace.py`
  returns `160:` and `169:` at both `2b337296` and `5d1fc5fd` - the function
  is untouched; the growth is new checks appended later in the file. Both
  citations confirmed byte-identical. Nothing to correct.

No content correction was needed. Not re-verified at this pass: nothing
beyond the two files above was read, and nothing was executed - no Ollama
server contacted, no index built, no bootstrap script or test suite run. The
`cli/anthropic_proxy.py` end-to-end gap noted above still stands.

## Re-anchor provenance - 5d1fc5fd -> 6c497a14, 2026-09-25 (after crew 1.0, PR #225)

**Re-derive provenance.** Per-path check over every backtick-quoted
repo-relative path this note cites (the same cited-path list used at the
previous re-anchor, plus `plugin/localgpu/commands/crew.md`,
`plugin/localgpu/commands/doctor.md` and `plugin/crew/hooks/scripts/crew_state.py`,
which the previous list already carried):

```
git diff --name-only 5d1fc5fd..6c497a14 -- <every path this note cites>
```
returns three files: `plugin/crew/hooks/scripts/crew_config.py`,
`plugin/crew/hooks/scripts/crew_state.py`, `scripts/check-marketplace.py`.
**Few paths moved, as expected** - crew 1.0 did not touch `plugin/localgpu/`
itself (`git diff --name-only 5d1fc5fd..6c497a14 -- plugin/localgpu/` is
empty), so every `plugin/localgpu/**` citation in this note - `mcp/*.py`,
`cli/*.py`, `bootstrap.sh`/`.ps1`, `commands/*.md`, `_test/*.py`,
`.claude-plugin/plugin.json`, `pyproject.toml` - is untouched and was not
re-read.

**Existence check, because the task that requested this pass expected many
gone.** Every cited path was checked with a plain existence test
(`[ -e "$p" ]`) against the working tree at `6c497a14`. All exist except
`skills/localgpu/SKILL.md` - which this note has already recorded, since the
2026-09-06 pass, as not a real path (the real one is
`plugin/localgpu/skills/localgpu/SKILL.md`). No newly-missing *file* turned
up. What crew 1.0 actually removed is not a path this note cites by
`path:line` - it is the **content** one of those paths describes:
`plugin/localgpu/commands/crew.md` is byte-identical at both commits, but its
Step 2 role table names eleven crew roles whose agent definitions crew 1.0
deleted wholesale. See the correction inside the "Six slash commands" section
above for the full finding, established with `git show --diff-filter=DR
--name-status 6c497a14 -- plugin/crew/agents/` (fifty deletions) cross-checked
against `ls plugin/crew/agents/` (four files remain) and
`.claude-plugin/marketplace.json`'s rewritten `crew` entry.

**The three moved files, checked line by line:**

- `scripts/check-marketplace.py` grew from 1627 to 1678 lines
  (`wc -l`); `grep -n "def check_plugin_manifests\|declared != entry\[.version.\]"`
  still returns `160:` and `169:` - both citations this note makes into that
  file are byte-identical. Nothing to correct.
- `plugin/crew/hooks/scripts/crew_config.py`: `git diff --stat` reports
  +173/-that file between the two commits, but the two lines this note cites,
  `:126-127` (`DEV_PROVIDERS = crew_state.DEV_PROVIDERS` /
  `QA_PROVIDERS = crew_state.QA_PROVIDERS`), are byte-identical at the same
  line numbers. Nothing to correct.
- `plugin/crew/hooks/scripts/crew_state.py`: `git diff --stat` reports
  238 lines changed. The one line pair this note cites moved -
  `DEV_PROVIDERS = ("claude", "codex", "copilot")` /
  `QA_PROVIDERS = ("claude", "codex", "copilot")` shifted from `:1503-1504` to
  `:1411-1412` (confirmed by `grep -n "^DEV_PROVIDERS\|^QA_PROVIDERS"`), text
  unchanged. Corrected in the "Six slash commands" section above; the
  historical QA-block entries further up this file that quote the old
  `:1503-1504` number are left as written, as records of what an earlier pass
  verified at its own anchor, not live citations.

Not re-verified at this pass: nothing under `plugin/localgpu/` was rebuilt,
installed, executed or imported - no Ollama server contacted, no index built,
neither bootstrap script run, no test suite executed. `cli/anthropic_proxy.py`
still has not been read end to end. The crew-roster finding above was
established entirely from `git show`/`git diff`/`ls`, not from opening every
deleted agent file's prior content.

**Re-anchored `6c497a14` -> `f2bb919b` on 2026-09-25 (T-0015).** `git diff --name-only 6c497a14
f2bb919b -- <the 32 tracked paths this note cites>` returns one file,
`.claude-plugin/marketplace.json`, whose only hunk is crew's `version` (`1.0.25` -> `1.0.28`,
`:218`). The `crew` entry's description, which this note quotes ("4 context-isolated agents
(explorer, reviewer, security, researcher)"), is on `:217` and unchanged, and `localgpu`'s own
entry is untouched (still `0.1.20`). Nothing under `plugin/localgpu/` changed. No claim moved.

**Re-anchored `f2bb919b` -> `6d35ef8c` on 2026-09-26 (T-0006).** `git diff --name-only f2bb919b
6d35ef8c -- <the paths this note cites>` returns `.claude-plugin/marketplace.json` (crew's
`version` `:218` only; the `:217` description this note quotes is unchanged and `localgpu`'s own
entry is still `0.1.20`), `plugin/crew/hooks/scripts/crew_config.py` and
`plugin/crew/hooks/scripts/crew_state.py`. `crew_config.py`'s `:126-127` re-export is above its
hunks (`:301`, `:498`) and holds. `crew_state.py` gained `RESUME_DEFAULTS` at `:684`, so the
provider tuples moved `:1411-1412` -> `:1421-1422` (re-read: the same two lines,
byte-identical), corrected in place above; the `:1503-1504` mentions are history of earlier
passes and are left as written. Nothing under `plugin/localgpu/` changed.

**Re-anchored `6d35ef8c` -> `07ca3972` on 2026-09-26 (T-0004).** `git diff --name-only 6d35ef8c
07ca3972 -- <the paths this note cites>` returns `.claude-plugin/marketplace.json` (crew's
`version` `:218`, and its `:217` description's slash-command count; the quoted "4
context-isolated agents (explorer, reviewer, security, researcher)" is unchanged, `ls
plugin/crew/agents/` still lists those four, and `localgpu`'s own entry is still `0.1.20`),
`plugin/crew/hooks/scripts/crew_config.py` and `plugin/crew/hooks/scripts/crew_state.py`.
`crew_config.py`'s `:126-127` re-export is above its only hunk (`:366`, `default_config`) and
holds. `crew_state.py` gained `AUTOPILOT_DEFAULTS` at `:1087`, so the provider tuples moved
`:1421-1422` -> `:1429-1430` (re-read via `grep -n "^DEV_PROVIDERS\|^QA_PROVIDERS"`: the same
two lines, byte-identical), corrected in place above. Nothing under `plugin/localgpu/` changed.
Nothing was executed.

**Re-anchored `f2bb919b` -> `fc54def6` on 2026-09-25 (T-0005).** `git diff --name-only f2bb919b
fc54def6 -- <the files this note cites>` returns `.claude-plugin/marketplace.json` (crew's
`version` only, now `1.0.41`; `:217`'s description and `localgpu`'s own entry, still `0.1.20`,
unchanged), `CLAUDE.md` (cited without a line; its `open(p, "w")` landmine still names
`plugin/localgpu/mcp/store.py`), `plugin/crew/hooks/scripts/crew_config.py` and
`plugin/crew/hooks/scripts/crew_state.py`. `plugin/crew/` and `plugin/crew/agents/` are named only
as locations (still 4 agent files).
Both crew files were re-read at the two live citations: the `crew_config.py` re-export moved
`:126-127` -> `:127-128` (one import line added above it) and the `crew_state.py` definition
`:1411-1412` -> `:1414-1415` (three import lines); both still read as quoted and are corrected
above. The citations in the QA-history sections record what was true at their own passes and are
left as written. Nothing under `plugin/localgpu/` changed.

**Re-anchored `6f96e627` + `fc54def6` -> `2b18f7ab` on 2026-09-26 (T-0005 landing).** `2b18f7ab` is the crew 1.0.42 bump on top of `4ed4b763`, the merge of T-0005 (`4e0abc8f`) into main at `1e0706ac`. Both lines' provenance is above, side by side. A citation can only be wrong at the merge when its file changed on both sides, or when a line from one side cites a file the other side changed; each such citation was re-mapped with a line diff of the cited file and re-read with `grep -n`/`sed -n` on the merged tree. The bump commit replaced `1.0.41` with `1.0.42` in place in the version files and in T-0005's own version statements (no line added or removed, except one line in `CHANGELOG.md`'s T-0005 bump note). Of the paths this note cites, `plugin/crew/hooks/scripts/crew_config.py` and
`plugin/crew/hooks/scripts/crew_state.py` changed on both sides: the `crew_config.py` re-export is
at `:127-128` and the provider tuples at `crew_state.py:1432-1433` (`grep -n
"^DEV_PROVIDERS\|^QA_PROVIDERS"`, the same two lines, byte-identical), corrected above.
`.claude-plugin/marketplace.json` changed at crew's `version` only (1.0.42); `localgpu`'s own entry
is still `0.1.20`. Nothing under `plugin/localgpu/` changed. Nothing was executed.

## Re-anchor provenance - `2b18f7ab` -> `50e67586`, 2026-09-27 (T-0010-solo, crew 1.0.43)

T-0010's code commit was cherry-picked off `origin/main` (`502cb137`) as `0fc5b069`, apart from
T-0018 and T-0024, and the version set in `50e67586`. Every `path:line` citation this note makes into
a path T-0010 changed was mapped from the `2b18f7ab` tree with `difflib`; each one that moved
was re-pointed and compared line for line with the anchor tree at `50e67586`.

Only `plugin/crew/hooks/scripts/crew_state.py` changed among the cited paths: the
`DEV_PROVIDERS`/`QA_PROVIDERS` definitions moved `:1432-1433` -> `:1436-1437` (four
`AUTOPILOT_DEFAULTS` lines above them), byte-identical. The dated QA-record sections keep
their own numbers as history.

**Re-anchored `6f96e627` -> `eba11657` on 2026-09-26 (T-0023).** `6f96e627` -> `1e0706ac` touched
only refresh artifacts; of the paths this note cites, `git diff --name-only 1e0706ac eba11657`
returns `.claude-plugin/marketplace.json` (crew's `version` `:218` only; the `:217` description
this note quotes is unchanged and `localgpu`'s own entry is still `0.1.20`) and
`plugin/crew/hooks/scripts/crew_config.py`, whose two hunks (`:375-382` in `default_config()`,
`:547-549` in `default_global_config()`, each adding `route`) are below the `:126-127` re-export,
which holds (re-read: `DEV_PROVIDERS = crew_state.DEV_PROVIDERS` /
`QA_PROVIDERS = crew_state.QA_PROVIDERS`). `crew_state.py` did not change, so the `:1429-1430`
tuples stand. Nothing under `plugin/localgpu/` changed.

## Re-anchor provenance - `2b18f7ab` + `488053fc` -> `a1acd9b7`, 2026-09-27 (T-0023 merge of main)

`3c968175` merges main at `502cb137` (T-0005 landed, its notes anchored `2b18f7ab`) into T-0023 at
`488053fc` (review round 1's fixes); `f6abe8c1` re-sets crew to 1.0.43 and `a1acd9b7` re-prices
`.crew/verify.json` rule 28 in place. Both lines' provenance is above. A citation can only be
wrong at the merge when its file changed on both sides, or when a line from one side cites a file
the other side changed. Each line of this note was classified by origin (main's text or
T-0023's), its citations into such files re-mapped with a line diff from that side's revision to
the merged tree (`502cb137` or `fa4d8cd5`), and each moved one re-read by content with
`grep -n`/`sed -n`; citations the line diff attributed to the wrong file were discarded, not
applied. `crew_config.py` changed on both sides; the `:127-128` re-export is above both sides' hunks and holds (re-read). `crew_state.py` changed on T-0005's side only, so `:1432-1433` stands. `.claude-plugin/marketplace.json` moved crew to 1.0.43 in place; `localgpu`'s own entry is still `0.1.20`. Nothing under `plugin/localgpu/` changed. Nothing was executed.

## Re-anchor provenance - `db14619c` + `ad74ed35` -> `e463ca53`, 2026-09-27 (T-0023 lands on T-0021's main)

`c68b40bd` merges origin/main `db14619c` (T-0042 landed as crew 1.0.43, PR #242; T-0021 as
1.0.45, PR #243) into T-0023's `ad74ed35`, and `e463ca53` bumps crew to 1.0.46. The files both
sides changed since `502cb137` are `CHANGELOG.md`, `.crew/verify.json`, `plugin/crew/README.md`,
`plugin/crew/CONFIG.md`, `plugin/crew/BUDGETS.md`, `plugin/crew/hooks/scripts/crew_context.py`,
`plugin/crew/tests/sabotage.py`, the version files and the refresh artifacts. The conflicting
provenance sections keep both sides, main's first. Every `path:N` citation in the body, and every
bare `:N` that follows a path, was mapped from the side its line came from onto the merged tree
with a line diff (`git show <side>:<path>` against the merge); each one that moved was re-read
with `sed -n` and corrected, and hits the diff attributed to the wrong file (a bare `:N` after
an unrelated path) were discarded rather than applied. This note cites
`.crew/verify.json` by name only, and nothing under `plugin/localgpu/` changed on either side;
the refresh check named the note only because `.crew/verify.json` gained T-0021's rule 28
ahead of T-0023's routing rule, now 29. No citation moved. Nothing was executed for this note.

## Re-anchor provenance - `e463ca53` -> `65bb3330`, 2026-09-27 (T-0018 lands on T-0023's main)

`f458e752` merges main `bebbb97f` into T-0018-land (T-0018's reviewed head `e6b696fb` merged into
`db14619c`), and `65bb3330` re-bumps crew to 1.0.47. `git diff --name-only e463ca53 65bb3330` returns
T-0018's files and the refresh artifacts; nothing under `plugin/localgpu/` changed. This note cites
`.crew/verify.json` and `plugin/crew/README.md` by name only; the refresh check named it because
T-0018 widened rule 27 (one path line added) and documented its subcommands in the README. No
citation moved. Nothing was executed for this note.

## Re-anchor provenance - `65bb3330` + `474aea8b` -> `8de3c669`, 2026-09-27 (T-0024 lands on T-0018's main)

`affa22a5` merges T-0024's reviewed head `474aea8b` (review round 4 FINDINGS, owner-accepted) into
main `67caa4b8` (T-0018 landed as crew 1.0.47, PR #245), and `8de3c669` bumps crew to 1.0.48.
The two sides share no source file: T-0024 changed `approval_hook.py`, both approval-hook wrappers,
`crew_ticket.py`, `commands/approve.md` and their tests; both sides changed `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md` (merged cleanly), `plugin/crew/tests/sabotage.py`,
`plugin/crew/BUDGETS.md`, the version files and the refresh artifacts. The conflicting provenance
sections keep both sides, main's first.
Nothing under `plugin/localgpu/` changed on either side. This note cites `.crew/verify.json` and
`plugin/crew/README.md` by name only; the refresh check named it because T-0024's approval rule was
appended as rule 30 and the README gained its group-approval paragraph. No citation moved. Nothing
was executed for this note.

**Re-anchored `2b18f7ab` -> `28893380` on 2026-09-27 (T-0072 build).** `28893380` is T-0072's last content commit on `T-0072-build`, cut from origin/main `502cb137` (T-0005's landing, which changed none of this note's text). `git diff --name-only 2b18f7ab 28893380` was read per cited path. T-0072 edited in place, with no line added or removed, `crew_state.py` (`:1084-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (one Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`), `plugin/PLUGINS.md` (`:14` version, the `/crew:autopilot` row), `.claude-plugin/marketplace.json` (`:218`), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It added lines to `crew_autopilot.py` (the `deploy-allowed` section and functions), `CONFIG.md` (+1 at the leaf paragraph, +1 in the key table, +1 in §20's table, and a closing §20 section), `CHANGELOG.md` (+30 at the top) and the autopilot tests. Of the paths this note cites, only `plugin/crew/hooks/scripts/crew_state.py` changed, line-neutral at `:1084-1090`; `DEV_PROVIDERS`/`QA_PROVIDERS` are still `:1432-1433` and `:1503-1504` holds (`grep -n`). `.claude-plugin/marketplace.json` changed at crew's version only (1.0.43); `localgpu` is still `0.1.20`. Nothing under `plugin/localgpu/` changed. Nothing was executed.

**Re-anchored `28893380` -> `d3a1c77e` on 2026-09-27 (T-0072, crew 1.0.44).** `d3a1c77e` is T-0072's version commit on `T-0072-build`, after it merged origin/main `f0b12ee6` (T-0042's landing) with a merge commit. `git diff --name-only 53f5482c d3a1c77e` over the cited paths returns only T-0072's changes and the version files. T-0072 edited in place, with no line added or removed, `crew_state.py` (`:1084-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (the autopilot Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`, now 18,612 lines across 121 files), `plugin/PLUGINS.md` (`:14` 1.0.44, the `/crew:autopilot` row), `.claude-plugin/marketplace.json` (`:218` 1.0.44), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It added lines to `crew_autopilot.py` (the `deploy-allowed` docstring section and functions, 694 -> 837 lines), `CONFIG.md` (+1 at the leaf paragraph, +1 in the key table, +1 in §20's table, a closing §20 section), `CHANGELOG.md` (+32 at the top) and the autopilot tests. (The previous section anchored this note at `28893380` on T-0072's branch before the merge; main's T-0042 landing changed nothing this note cites.) Of the paths this note cites, only `crew_state.py` changed, line-neutral at `:1084-1090`; `DEV_PROVIDERS`/`QA_PROVIDERS` `:1432-1433` and `:1503-1504` hold. `localgpu` is still `0.1.20`. Nothing under `plugin/localgpu/` changed.

**Re-anchored `d3a1c77e` -> `e30af7f9` on 2026-09-27 (T-0072 review round 1).** `e30af7f9` is T-0072's review-round-1 fix commit on `T-0072-build`. `git diff --name-only d3a1c77e e30af7f9` returns `.crew/verify.json` (rule 27's `why` re-measured in place, still `:293-300`), `CHANGELOG.md` (the 1.0.44 entry, four lines reworded, cited without a line), `plugin/crew/BUDGETS.md` (`:11`, now 18,615 lines across 121 files; `check-marketplace.py` prints `all checks passed`), `plugin/crew/CONFIG.md` (+3 lines in §20's closing section, at `:2317`; nothing cited above it moved, `:2251-2258` holds), `plugin/crew/hooks/scripts/crew_autopilot.py` (+24 lines: the docstring gains a line at `:88`, `_deploy_verdict` moves its `cloud_guard` import below the incident check, `_safe_text` and `_crash_reason` are new), `plugin/crew/tests/sabotage_autopilot.py` (+32: `CLOUD` at `:18`, six mutations) and `plugin/crew/tests/test_crew_autopilot_deploy.py`, plus the refresh artifacts of the previous pass. No crew version change (1.0.44). Of the paths this note cites, only `.crew/verify.json` changed, in place inside rule 27's `why`; every line it cites holds. Nothing else this note cites changed.

**Re-anchored `e463ca53` -> `715a8c2f` on 2026-09-27 (T-0072 merged onto `bebbb97f`, crew 1.0.47).** `715a8c2f` is T-0072's crew 1.0.47 version commit on `T-0072-build`, on top of `e658bb04`, its merge of origin/main `bebbb97f` (T-0021 and T-0023 landed; this note was anchored at T-0023's `e463ca53`). `git diff --name-only e463ca53 715a8c2f` over the cited paths returns only T-0072's changes, the neighbour test T-0072 added after the merge, and the version files. Against main, T-0072 edits in place, with no line added or removed, `crew_state.py` (`:1086-1090`, the `AUTOPILOT_DEFAULTS` comment and value), `plugin/crew/README.md` (`:843`, the autopilot Settings paragraph), `plugin/crew/commands/autopilot.md` (`:19-20`), `plugin/crew/BUDGETS.md` (`:11`, now 18,910 lines across 126 files), `plugin/PLUGINS.md` (`:14` 1.0.47, `:128` the `/crew:autopilot` row), `plugin/crew/skills/crew-setup/SKILL.md` (`:170`), `.claude-plugin/marketplace.json` (`:218` 1.0.47), `plugin/crew/.claude-plugin/plugin.json` (`:3`) and `.crew/verify.json` (rule 27 `:293-300`, same lines). It adds lines to `crew_autopilot.py` (694 -> 861), `CONFIG.md` (+3 at the leaf paragraph `:130`, +1 at `:803`, +1 at `:2282`, and the closing §20 section at `:2297`, 41 lines, with T-0023's §21 after it), `CHANGELOG.md` (+31 at `:7`, T-0072's entry above T-0023's), `config.template.json` (+1 at `:205`), `test_crew_config.py` (+3; the count assertion is `:282`, 123), `test_crew_autopilot.py` (+2), `sabotage_autopilot.py` (+140) and the new `test_crew_autopilot_deploy.py`. Of the paths this note cites, only `crew_state.py` changed, line-neutral at `:1086-1090`; `DEV_PROVIDERS`/`QA_PROVIDERS` `:1432-1433` and `:1503-1504` hold (`sed -n`). `.claude-plugin/marketplace.json` changed at crew's version only (1.0.47); `localgpu` is still `0.1.20`. Nothing under `plugin/localgpu/` changed. Nothing was executed.

**Re-anchored `65bb3330` -> `21429244` on 2026-09-27 (T-0072 merged onto `67caa4b8`, crew 1.0.48).** `21429244` is T-0072's crew 1.0.48 version commit on `T-0072-build`, on top of `80d4073b`, its merge of origin/main `67caa4b8` (T-0018 landed; this note was anchored at T-0018's `65bb3330`, and nothing outside the refresh artifacts changed between `65bb3330` and `67caa4b8`). Main's side of this note was taken in the merge and T-0072's earlier refresh replayed on top (`git apply --3way` of `bebbb97f..b1ec6877`); every citation into a file either side changed was mapped with a line diff (main -> merged for main's text, `b1ec6877` -> merged for T-0072's) and each one that moved was re-read with `sed -n`. `git diff --name-only 65bb3330 21429244`, outside the refresh artifacts, returns only T-0072's files: `crew_autopilot.py` (1063 -> 1230 lines: the `deploy-allowed` docstring section and functions, and its parser at `:1140`), `CONFIG.md` (+56), `CHANGELOG.md` (+31 at the top), `commands/autopilot.md` (the settings sentence rewrapped at `:44-47`, still 100 lines), `crew_state.py` (line-neutral at `:1086-1090`), `config.template.json`, `crew-setup/SKILL.md` (`:170`), `.crew/verify.json` (rule 27 `:293-301`, same lines: `test_crew_autopilot_deploy.py` joins its paths and run), the version files (1.0.48 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), `plugin/crew/BUDGETS.md:11` (18,905 lines across 126 files, re-measured on the merge), and the autopilot tests. Nothing under `plugin/localgpu/` changed. Of the paths this note cites, only `crew_state.py` changed, line-neutral at `:1086-1090`; `DEV_PROVIDERS`/`QA_PROVIDERS` `:1432-1433` and `:1503-1504` hold (`sed -n`). `localgpu` is still `0.1.20` in `.claude-plugin/marketplace.json`. Nothing was executed for this note.

**Re-anchored `21429244` -> `53855ea5` on 2026-09-27 (T-0072 review round 3).** `53855ea5` is T-0072's review-round-3 fix commit on `T-0072-build`. `git diff --name-only 21429244 53855ea5`, outside the refresh artifacts, returns only T-0072's files: `.crew/verify.json` (rule 27's `seconds` 16 -> 20 and its `why`, in place, still `:293-301`), `CHANGELOG.md` (T-0072's 1.0.48 entry, +4 lines, cited without a line), `plugin/crew/BUDGETS.md` (`:11`, in place: 18,908 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (one §20 table row edited in place at `:2309`, +3 lines after `:2327`), `plugin/crew/hooks/scripts/crew_autopilot.py` (1230 -> 1252 lines: +2 in the docstring at `:90-97`, `_cannot_exclude` and `_incident(root)` at `:702-718`, `_cli_value` at `:1132`, the `deploy-allowed` printing at `:1214-1219`), `plugin/crew/tests/sabotage_autopilot.py` (+36 at `:300-335`: eight `DEPLOY_MUTATIONS`; one re-anchored in place at `:256`) and `plugin/crew/tests/test_crew_autopilot_deploy.py`. No crew version change (1.0.48). None of the paths this note cites changed; nothing under `plugin/localgpu/` changed, and `localgpu` is still `0.1.20`. Nothing was executed for this note.

**Re-anchored `8de3c669` -> `80326b1d` on 2026-09-27 (T-0072 merged onto `d2fbd408`, then review round 4's redesign, crew 1.0.49).** `ba7d5c52` merged origin/main `d2fbd408` (T-0024 landed as crew 1.0.48 at `8de3c669`) into `T-0072-build` and took main's side of every code map; T-0072's earlier refresh (`git diff 67caa4b8 2fa75f79 -- .crew/codemap/`) was replayed on top with `git apply --3way`, conflicting provenance sections keeping both sides, main's first. `80326b1d` is T-0072's crew 1.0.49 version commit, after the redesign `35733d76` (one root per answer, a tri-state path probe, a two-stage CLI fallback), its sabotage `fa4c8397`, its docs `8a40dd2c` and the rule-27 re-price `37fa7c97`. `git diff --name-only 8de3c669 80326b1d`, outside the refresh artifacts, returns only T-0072's files: `.claude-plugin/marketplace.json` (`:218` 1.0.49), `.crew/verify.json` (rule 27 in place, `:293-301`, `seconds` 16), `CHANGELOG.md` (T-0072's entry, +45 at the top), `plugin/PLUGINS.md` (`:14` 1.0.49, `:128` the `/crew:autopilot` row in place), `plugin/crew/.claude-plugin/plugin.json` (`:3`), `plugin/crew/BUDGETS.md` (`:11`, 18,939 lines across 126 files, which `check-marketplace.py` verifies), `plugin/crew/CONFIG.md` (2328 -> 2382 lines: the leaf paragraph `:130`, the key table `:803`, the `prodUnattended` row `:1261`, `:2282`, and section 20's closing "Production without asking" block from `:2297`), `plugin/crew/README.md` (`:866` in place), `plugin/crew/commands/autopilot.md` (`:45-48` in place, 100 lines), `crew_autopilot.py` (1312 lines), `crew_state.py` (line-neutral at `:1086-1090`), `crew-setup/SKILL.md` and `config.template.json` (the leaf), `test_crew_config.py` (`:282` asserts 123), `sabotage_autopilot.py`, `test_crew_autopilot.py` and `test_crew_autopilot_deploy.py`. Nothing under `plugin/localgpu/` changed. Of the paths this note cites, only `crew_state.py` changed, line-neutral at `:1086-1090`; `DEV_PROVIDERS`/`QA_PROVIDERS` `:1432-1433` hold (`sed -n`). `localgpu` is still `0.1.20` in `.claude-plugin/marketplace.json`. Nothing was executed for this note.

**Re-anchored `80326b1d` -> `1b5b6560` on 2026-09-27 (T-0072 test fix).** `git diff --name-only 80326b1d 1b5b6560`, outside the refresh artifacts, returns only `plugin/crew/tests/test_crew_autopilot_deploy.py` (the layer_state repro now patches `crew_config.layer_state`, not `crew_state.read_text`, which `test_module_split.py` forbids) and the three version files, stepped back to 1.0.48 and re-set to 1.0.49 so the version stays the last `plugin/crew/` commit (same content as at `80326b1d`). This note cites that test file by name only. No citation moved. Nothing was executed for this note.

**Re-anchored `1b5b6560` -> `a4eb2f55` on 2026-09-28 (T-0072 merged onto `5050ea3b`, crew 1.0.50).** `a4eb2f55` is T-0072's crew 1.0.50 version commit on top of its merge of origin/main `5050ea3b` (T-0077 landed as crew 1.0.49 at `fc289446`; shipstation 1.1.1). The merge was clean. `git diff --name-only 1b5b6560 a4eb2f55`, outside the refresh artifacts, returns main's T-0077 and shipstation files - `crew_tracker.py` (+123: Windows now holds a vault write's directories by handle, `_hold_dirs` / `_held_check` replace `_parent_check`), `crew_autopilot.py` (`_rel` +6 at `:170`, so every later line moves by 6), `sabotage_autopilot.py` (+5 inside `STATUS_MUTATIONS`; the `+=` append moved `:639` -> `:644`), `sabotage_tracker.py` (87 `TRACKER_MUTATIONS`, was 81), `plugin/crew/README.md` (`:1511-1513` in place), `test_crew_tracker.py`, `test_crew_autopilot.py`, `test_crew_autopilot_status.py`, `skills/shipstation/*` - and the version files (1.0.50 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`) and `CHANGELOG.md` (T-0077's and shipstation's entries under T-0072's). Nothing under `plugin/localgpu/` changed; `crew_state.py` did not change. No citation moved. Nothing was executed for this note.

**Re-anchored `a4eb2f55` -> `0f488706` on 2026-09-28 (T-0072 review round 5).** `0f488706` is T-0072's review-round-5 fix commit. `git diff --name-only a4eb2f55 0f488706`, outside the refresh artifacts (`0282cb5c`, `37fa2322`), returns only T-0072's files: `plugin/crew/hooks/scripts/crew_autopilot.py` (`_resolve_root` +4 at `:729`, refusing a root that is not text, so every line after it moves by 4: `_layer_problem` `:744`, `_decide` `:759`, `deploy_allowed` `:836`, `_failure` `:1170`, `_cli_deploy` `:1194`, `main` `:1225`; `--json` dumps without indent, in place; the module docstring re-worded in place, `:87-104`), `plugin/crew/tests/sabotage_autopilot.py` (+30 inside `DEPLOY_MUTATIONS`, 64 entries by `len()`: the `AUTOPILOT_MUTATIONS + DEPLOY_MUTATIONS` append moved `:443` -> `:473`, `STATUS_MUTATIONS`' `:644` -> `:674`), `plugin/crew/tests/test_crew_autopilot_deploy.py`, `plugin/crew/CONFIG.md` (one sentence in section 20 re-worded in place, `:2331-2333`, no line added) and `CHANGELOG.md`. This note cites those files by name or at lines above the change; no citation moved. No suite was executed for this note.

## Re-anchor provenance - `65bb3330` + `50e67586` -> `c817782f`, 2026-09-27 (T-0010-solo merges `67caa4b8`)

`c817782f` is T-0010's crew 1.0.48 version commit on top of `d1e119d2`, T-0010-solo's merge of
origin/main `67caa4b8` (T-0018 landed as 1.0.47; its code maps anchored `65bb3330`), and
`3e2c9962`, the reconciliation under the owner's approve carve-out. Main's side of this note was
mapped from `65bb3330`, T-0010's side from its own anchor (`50e67586`), to `c817782f` with `difflib`
over every cited file, a bare `:N` taken as the last path named in its section; sections headed
provenance (and localgpu's re-derivation record) were left as written. The two mapped texts were
then merged three-way from `f0b12ee6`. Between `65bb3330` and `c817782f` the cited paths that
changed are T-0010's: `crew_autopilot.py`, `crew_ticket.py`, `scope_guard.py`, `crew_state.py`
(four `AUTOPILOT_DEFAULTS` lines at `:1094`, so every later line moved by 4), `commands/autopilot.md`,
the version files, `BUDGETS.md`, README, CONFIG.md, the tests and sabotage modules, and
`.crew/verify.json` (rule 28 inserted at `:302-308`, so rules 29 and 30 moved down by 7).

The two `crew_state.py` tuples this note cites moved to `:1436-1437` (four lines lower than
main's `65bb3330`, the same as on T-0010's branch), re-read at `c817782f`; the `:1503-1504`
mentions in the re-derivation record are history and were left as written. Nothing under `plugin/localgpu/` changed on either side.

## Re-anchor provenance - `c817782f` -> `926443d8`, 2026-09-27 (T-0010 review round 3 fixes)

`git diff --name-only c817782f 926443d8` is T-0010's round-3 fix (`caabb005`), the BUDGETS.md
count, the version step-back and re-set, and this refresh. Of the paths this note cites, `plugin/crew/README.md`, `plugin/crew/CONFIG.md` and
`plugin/crew/BUDGETS.md` changed: README two lines rewritten in place (`:792`, `:818`),
CONFIG.md's §20 one-writer paragraph grew six lines, and `BUDGETS.md:11`'s count moved
18,917 -> 18,923 on the same line. No citation this note makes moved (checked with `difflib`
over every cited path). Nothing was executed.

## Re-anchor provenance - `926443d8` + `8de3c669` -> `50a275ea`, 2026-09-28 (T-0010's successor merges `f96e9ec9`)

`ab85880b` merges origin/main `f96e9ec9` (T-0024 landed as crew 1.0.48, its code maps anchored
`8de3c669`; T-0077 as 1.0.49) into T-0010-solo `216ee85f`; `a2f4db76` fixes review round 4's
three FIXes; `3438dc9a` merges `5050ea3b` (shipstation only); `48b2820d` re-measures
`plugin/crew/BUDGETS.md` and `50a275ea` sets crew 1.0.50. The merge took main's side of this
note; it was then re-merged three-way from `67caa4b8`, T-0010's side at `216ee85f` (anchor
`926443d8`) and main's at `f96e9ec9` (anchor `8de3c669`), both sides' provenance kept, main's
first. Every body citation into a file changed since its side's own anchor was mapped with
`difflib` (a bare `:N` taken as the last path named in its section) and each one that moved was
re-read at `50a275ea`.

Nothing under `plugin/localgpu/` changed on either side. This note cites `.crew/verify.json`,
`plugin/crew/README.md` and `plugin/crew/CONFIG.md` by name only; the `crew_state.py` tuples it
cites did not move (`crew_state.py` is unchanged since `926443d8`). No citation moved. Nothing
was executed for this note.

## Re-anchor provenance - `8de3c669` -> `a6e81869`, 2026-09-27 (T-0079 on its branch)

`T-0079-read` was cut from `67caa4b8`, merged main `d2fbd408` (T-0024 landed; its refresh `fdc54ce9`
changed refresh artifacts only) in `f034ef5c`, and carries T-0079's commits through `a6e81869`
(crew 1.0.49). `git diff --name-only 8de3c669 a6e81869`, refresh artifacts aside, returns T-0079's
files only: `review_verdict.py`, `review_prompt.py`, `review_run.py`, their tests and
`sabotage_review.py`, `agents/reviewer.md`, `plugin/crew/README.md` (line-neutral), `CHANGELOG.md`
and the three version files. Every body citation into those files was compared by script between
`8de3c669` and `a6e81869` at the same line.
Nothing under `plugin/localgpu/` changed. This note cites `plugin/crew/README.md` by name
only; the refresh check named it because T-0079 reworded the README's review-verdict row in place.
No citation moved. Nothing was executed for this note.

## Re-anchor provenance - `a6e81869` -> `81685adf`, 2026-09-27 (T-0079 merges main, Step 7, re-bump)

`T-0079-read` gained T-0079's Step 7 (`8f7c62dd`, one `find` string in
`plugin/crew/tests/sabotage_webtest.py`), merged main `f96e9ec9` (T-0077 landed, crew 1.0.49) in
`548ee44e`, and re-bumped crew to 1.0.50 in `81685adf`. `git diff --name-only a6e81869 81685adf`,
refresh artifacts aside, returns that `sabotage_webtest.py`, T-0077's files (`crew_tracker.py`,
`crew_autopilot.py`, `sabotage_tracker.py`, `sabotage_autopilot.py`, `test_crew_tracker.py`,
`test_crew_autopilot.py`, `test_crew_autopilot_status.py`), `plugin/crew/README.md` (line-neutral
on both sides), `CHANGELOG.md` and the three version files. Every body citation of the form
`path:line` into those files was compared by script between `a6e81869` and `81685adf`.
Nothing under `plugin/localgpu/` changed. This note cites `plugin/crew/README.md` by name only;
no citation moved. Nothing was executed for this note.

**Re-anchored `0f488706` -> `9631c707` on 2026-09-28 (T-0072 landing, crew 1.0.51).** `9631c707` is T-0072's landing bump on `T-0072-land`, after `34af80ef` merged the reviewed `T-0072-build` (`a0978df6`) onto main `e6e10432` (T-0079 landed as crew 1.0.50) and `bf0c513a` re-priced verify rule 27. `git diff --name-only 0f488706 9631c707`, refresh artifacts aside, returns T-0079's files, the three version files, `CHANGELOG.md` and `.crew/verify.json`. The two this note's citations reach changed in place: `.crew/verify.json` `:298` and `:301` (rule 27's `seconds` 16 -> 18 and its `why`, still `:293-301`) and `plugin/crew/README.md` `:738` and `:742` (T-0079's verdict table, line-neutral); no citation moved. The version sentence moves to 1.0.51. No suite was executed for this note.

**Re-anchored `2b18f7ab` -> `d2444be9` on 2026-09-27 (T-0075).** Of the paths this note cites, only
`plugin/crew/hooks/scripts/crew_config.py` changed (`git diff --name-only 2b18f7ab d2444be9`), and
only by T-0075's additions below `_RATCHETED` (`:2548` onward: the enum check, the repo writer, the
`--repo` flag). The re-export is still `crew_config.py:127-128`, byte-identical, and `crew_state.py`
did not change. Nothing under `plugin/localgpu/` changed. Nothing was executed.

## Re-anchor provenance - `e95e5964` + `e463ca53` -> `f7163410`, 2026-09-27 (T-0075 merges T-0023's main)

`96b7e59c` merges origin/main `bebbb97f` (T-0023 landed as crew 1.0.46, PR #244; its notes anchored
`e463ca53`) into T-0075's branch at `0c6b5ecb` (notes anchored `e95e5964`), and `f7163410` bumps
crew to 1.0.47. The source files both sides changed since `db14619c` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/PLUGINS.md`, `plugin/crew/README.md`, `plugin/crew/CONFIG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/hooks/scripts/crew_config.py`,
`plugin/crew/skills/crew-setup/SKILL.md`, `plugin/crew/tests/sabotage.py`,
`plugin/crew/tests/test_crew_config.py` and the version files. The conflicting provenance sections
keep both sides, main's first. Each body line was classified by origin (in T-0075's copy only, in
main's only, or in both), its `path:N` citations - and bare `:N` after a path in the same
paragraph - into files the other side changed were mapped with a line diff (`git show
<side>:<path>` against the merged tree), each moved one re-read with `sed -n`, and hits the diff
attributed to the wrong file (a bare `:N` after an unrelated path, a same-named file elsewhere)
discarded rather than applied. This note cites `plugin/crew/hooks/scripts/crew_config.py` only at the `:127-128`
re-export, which is above both sides' hunks and holds (re-read: `DEV_PROVIDERS =
crew_state.DEV_PROVIDERS` / `QA_PROVIDERS = crew_state.QA_PROVIDERS`); `crew_state.py` changed on
neither side. `.claude-plugin/marketplace.json` moved crew to 1.0.47 in place; `localgpu`'s own
entry is still `0.1.20`. Nothing under `plugin/localgpu/` changed. Nothing was executed.

## Re-anchor provenance - `f7163410` + `65bb3330` -> `23371afb`, 2026-09-27 (T-0075 merges T-0018's main)

`34b5f368` merges origin/main `67caa4b8` (T-0018 landed as crew 1.0.47, PR #245; its notes anchored
`65bb3330`) into T-0075's branch at `b5ef35df` (notes anchored `f7163410`), and `23371afb` bumps crew
to 1.0.48. The source files both sides changed since `bebbb97f` are `CHANGELOG.md`,
`.crew/verify.json`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md` and the version files;
`crew_autopilot.py`, `commands/autopilot.md` and the autopilot tests changed on main's side only,
`crew_config.py`, `crew_config_menu.py`, `CONFIG.md` and `sabotage.py` on T-0075's only. The
conflicting provenance sections keep both sides, main's first; each body citation into a file both
sides changed was mapped from the side its line came from onto the merged tree and re-read with
`sed -n`/`grep -n`. This note cites `.crew/verify.json` and `plugin/crew/README.md` by name only; the refresh check
named it because both changed on both sides. `crew_config.py:127-128` (the provider re-export) and
`crew_state.py` changed on neither side. `localgpu`'s marketplace entry is still `0.1.20`; nothing
under `plugin/localgpu/` changed. Nothing was executed for this note.

## Re-anchor provenance - `23371afb` -> `764f6018`, 2026-09-27 (T-0075 review round 1)

`764f6018` fixes T-0075's review round 1. `git diff --name-only 23371afb 764f6018` is `CHANGELOG.md`,
`plugin/crew/BUDGETS.md`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`,
`plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/hooks/scripts/crew_config_menu.py`,
`plugin/crew/skills/crew-setup/config-menu.md` and three crew test files. Each citation into one
of them was mapped with a line diff from `87627d86` (the tree `23371afb` describes for those
files) and re-read with `sed -n`/`grep -n`. This note's line citations into `crew_config.py` (`:127-128`, the provider
re-export) sit above the only insertion (`:2789`) and hold; the rest are by name. Nothing under
`plugin/localgpu/` changed; its marketplace entry is still `0.1.20`. Nothing was executed for this note.

## Re-anchor provenance - `764f6018` + `8de3c669` -> `7d217751`, 2026-09-27 (T-0075 successor build, merges T-0024's main)

`7d217751` is T-0075's crew 1.0.49 bump. Between `764f6018` (T-0075 review round 1, this note's
last anchor) and it: the successor build's steps 1-9 (`4911b896`..`763eaeff`: `crew_config_files.py`
new, `crew_config.py` and `crew_config_menu.py` redesigned, their tests and sabotage entries, the
menu procedure, `commands/config.md`, `config-setup.md`, `global-config.md`, `plugin/crew/README.md`,
`CONFIG.md`, the troubleshooting guide and `CHANGELOG.md`), `748a823d` merging origin/main `d2fbd408`
(T-0024 landed as 1.0.48, notes anchored `8de3c669`), `af1ee7ef` adding two paths to
`.crew/verify.json` rule 7, `cb67a6ef` rebuilding the troubleshooting guide, `plugin/crew/BUDGETS.md`
re-measured (19,280 lines across 128 files) and the bump. The merge's provenance sections keep both
sides, main's first. Each citation into a path `git diff --name-only 764f6018 7d217751` names was
checked against the tree it was written for (`git blame` on this note gives the commit) and re-read
at `7d217751` with `sed -n`/`grep -n`; the provider re-export `crew_config.py:127-128` -> `:128-129` (one import line
above it); the rest are by name. Nothing under `plugin/localgpu/` changed; its marketplace entry is
still `0.1.20`. Nothing was executed for this note.

## Re-anchor provenance - `7d217751` + `f96e9ec9` -> `8cabe586`, 2026-09-27 (T-0075 post-merge fixes, merges T-0077's main)

`8cabe586` is T-0075's crew 1.0.50 bump. Between `7d217751` and it: `ed7cb36c` (the stray line
step 6 left in `crew_config_menu.py:940`, a restore-line test's assertion, and the widening-warning
mutation re-anchored in `sabotage.py`, each found by the first full suite run after the build), a
1.0.48/1.0.49 step-back and re-set (`b80db8e1`, `81ed193c`), `3ebddc74` merging origin/main
`f96e9ec9` (T-0077 landed as 1.0.49: Windows directory handles in `crew_tracker.py`,
`crew_autopilot._rel`, their tests and mutations, three `plugin/crew/README.md` lines and its
`CHANGELOG.md` entry; main's notes were not refreshed for it) and the bump. Citations into the
paths `git diff --name-only 7d217751 8cabe586` names were mapped with `git diff -U0` and each
moved one checked by content at `8cabe586`; none of this note's citations moved (`crew_config.py` did not change in this
range). Nothing under `plugin/localgpu/` changed. Nothing was executed for this note.

## Re-anchor provenance - `8cabe586` + `81685adf` -> `3724731b`, 2026-09-28 (T-0075 review round 3, merge of `e6e10432`)

`3036dc02` is T-0075's review-round-3 fix (`crew_config.py`, `crew_config_files.py`,
`crew_config_menu.py`, their three test files, `sabotage_config.py`, and `README.md`, `CONFIG.md`,
`commands/config.md`, `config-menu.md`, `global-config.md`, `CHANGELOG.md`); `6d5f0b61` merges
origin/main `e6e10432` (T-0079 landed as crew 1.0.50: `review_prompt.py`, `review_run.py`,
`review_verdict.py`, `agents/reviewer.md`, their tests, `sabotage_review.py`,
`sabotage_webtest.py`, `test_webtest_guard.py`, `README.md`, `CHANGELOG.md`; its notes anchored
`81685adf`); `3724731b` re-bumps crew to 1.0.51 (`plugin.json`, `marketplace.json`,
`plugin/PLUGINS.md`, `plugin/crew/BUDGETS.md`, `CHANGELOG.md`). The merge's conflicting provenance
sections kept both sides, main's first; anchor lines kept T-0075's and are replaced here.

Nothing under `plugin/localgpu/` changed, and the `crew_config.py:128-129` re-export this note
cites sits above the first changed line (`:2567`). No citation moved. Nothing was executed.

## Re-anchor provenance - `3724731b` + `9631c707` -> `938e3b11`, 2026-09-28 (T-0075 review round 4, merge of `f54af3fa`)

`7d473f24` merges origin/main `f54af3fa` (T-0072 landed as crew 1.0.51: `crew_autopilot.py`,
`commands/autopilot.md`, `crew_state.py`'s line-neutral `AUTOPILOT_DEFAULTS` hunk at `:1086-1090`,
`templates/config.template.json`, `skills/crew-setup/SKILL.md`, `CONFIG.md` §20, `README.md`, its
tests, `sabotage_autopilot.py`, `.crew/verify.json` rule 27's `seconds` and `why`; its notes
anchored `9631c707`); `07354a39`, `df419a55`, `7a206c8e`, `4112498e`, `1b31ed2f` and `7ef3c4f1` are
T-0075's review-round-4 steps 11-16 (`crew_config.py`, `crew_config_files.py`,
`crew_config_menu.py`, their three test files, `sabotage_config.py`, `README.md`, `CONFIG.md`,
`skills/crew-setup/config-menu.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`); `938e3b11` re-bumps
crew to 1.0.52 (`plugin.json`, `marketplace.json`, `plugin/PLUGINS.md`, `CHANGELOG.md`). The merge's
conflicting provenance kept both sides; anchor lines kept T-0075's and are replaced here.

Nothing under `plugin/localgpu/` changed, and the `crew_config.py:128-129` re-export this note cites
sits above the first changed line (`:206`). No citation moved.

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N`
carried from the last path named in its paragraph, from both `3724731b` and `9631c707` to the tree
at `938e3b11` (difflib equal blocks); every citation neither base maps to itself was read with `sed
-n` / `grep -n`. The script attributes some bare `:N` to the wrong file (a `crew_autopilot.py`
citation after an `autopilot.md` mention, a `plugin.json:3` in another plugin); those were read and
hold. Nothing else was executed for this note.

**Re-anchored `9631c707` -> `b5c37635` on 2026-09-28 (T-0087, crew 1.0.52).** `b5c37635` is T-0087's crew 1.0.52 bump on `T-0087-build`, after `d05727af` merged main `f54af3fa` (T-0072 landed as crew 1.0.51). `git diff --name-only 9631c707 b5c37635`, refresh artifacts aside, returns T-0087's files (the review/gate harness, its tests, the golden corpus, `scripts/check-tooling-pr.py`, rule 31 in `.crew/verify.json`, `CLAUDE.md`'s tooling-alone bullet, the docs and guides) plus the three version files and `CHANGELOG.md`. This note's body cites none of them at a moved line. Its citations of the three version lines (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`) changed in place and now read 1.0.52. Nothing was executed for this note.

**Re-anchored `b5c37635` -> `1da1233d` on 2026-09-28 (T-0087, crew 1.0.52).** `1da1233d` is T-0087's crew 1.0.52 bump re-set after two reflow commits: `4648581a` rewrapped `plugin/crew/commands/review.md` to its 551-line allowance and `plugin/crew/commands/autopilot.md` to its 100-line budget, and `4304a9da` kept the sabotage anchor "are the human's. Go back" on one line (no rule changed in either). `git diff --name-only b5c37635 1da1233d`, refresh artifacts aside, returns those two command files and the three version files, which read 1.0.52 on both sides. This note cites neither file by line. Nothing was executed for this note.

**Re-anchored `1da1233d` -> `0d331967` on 2026-09-28 (T-0087, crew 1.0.52).** `0d331967` adds `plugin/crew/BUDGETS.md` to `scripts/check-tooling-pr.py`'s `ALONGSIDE` (its line count moves with every crew doc edit, and the checker refused this branch's own re-measure) and the `harness+budgets` must-allow case to `scripts/_test/tooling-pr.py`, red first (7 passed, 1 failed), then 8 passed. `git diff --name-only 1da1233d 0d331967`, refresh artifacts aside, returns those two scripts and `CHANGELOG.md`, plus the 1da1233d..08ed88a5 changes (`plugin/crew/BUDGETS.md`, `plugin/crew/tests/sabotage_refresh.py`, version files unchanged net). This note cites neither script by line. Nothing was executed for this note.

**Re-anchored `0d331967` -> `c8cc69ec` on 2026-09-28 (T-0087, now crew 1.0.53).** Main moved: `c426c018` (T-0076, the crew suite on native Windows) landed as crew 1.0.52, so T-0087 merged it with a merge commit (no conflict) and re-bumped to 1.0.53 at `c8cc69ec`. `git diff --name-only 0d331967 c8cc69ec`, refresh artifacts aside, returns T-0076's files (`plugin/crew/hooks/scripts/crew_context.py` +4 at `:1086`, where `emit` now forces LF stdout; `plugin/crew/tests/crew_fixtures.py`, `review_fixtures.py`, `sabotage_context.py` and nine test files; `scripts/_test/uv-install.sh`; one `plugin/crew/README.md` table cell; its `CHANGELOG.md` entry), the README refund paragraph's version text, and the three version files. Every body `path:N` citation into those files was mapped by script (difflib over the two blobs) and every bare `:N` after one of their names was listed and read: none moved. Nothing was executed for this note.
**Re-anchored `9631c707` -> `22399a9c` on 2026-09-28 (T-0085, crew 1.0.52).** `22399a9c` is T-0085's version commit on `T-0085-build` (the change is `d02fe008`, from origin/main `f54af3fa`). Of the paths this note cites, T-0085 changed `.gitignore` (7 lines added after `:330`, the `!.crew/standards.md` un-ignore, so the `.mcp.json` line moved `:421` -> `:428`, corrected above), `.crew/verify.json` (rule 31 appended), `CLAUDE.md` (the ignore-policy paragraph, line-neutral), `plugin/crew/README.md` (18 lines added from `:712`), `plugin/crew/skills/crew-setup/SKILL.md`, `plugin/crew/tests/sabotage.py`, `plugin/PLUGINS.md`, `plugin/crew/BUDGETS.md`, `CHANGELOG.md` and the version files. Every body citation into those files was compared by script at both commits; only the `.gitignore` line moved. Nothing under `plugin/localgpu/` changed; `localgpu` is still `0.1.20`. Nothing was executed for this note.

**Re-anchored `22399a9c` -> `2aa49bb8` on 2026-09-28 (T-0085 merged onto main `c426c018`, crew 1.0.53).** `c49f3aca` merged origin/main `c426c018` (T-0076 landed as crew 1.0.52) into `T-0085-build`, one mechanical conflict (the crew description's skills count in `.claude-plugin/marketplace.json`, kept at 30), and `2aa49bb8` bumped crew to 1.0.53. `git diff --name-only 22399a9c 2aa49bb8`, refresh artifacts aside, returns T-0076's files (`plugin/crew/hooks/scripts/crew_context.py`, four lines added inside `emit()` at `:1086-1089`; `plugin/crew/README.md`, one line in place; `scripts/_test/uv-install.sh`; eleven test files) and the version files. Every body citation into a changed file was compared by script at both commits; none moved; nothing under `plugin/localgpu/` changed. No suite was executed for this note.

**Re-anchored `9631c707` -> `051f9e85` on 2026-09-28 (T-0091).** `051f9e85` is T-0091's one commit on `T-0091-build`, off main `f54af3fa`. `git diff --name-only 9631c707 f54af3fa -- <every tracked path this note cites>` is empty; `f54af3fa..051f9e85` changes only `CLAUDE.md` (the Landmines truncating-`open` entry's measurement paragraph, now `:185-212`, +28/-18, so every later line moves +10) and `TODO.md` (one entry closed at `:4473`, three lines appended at `:4480-4482`). This note cites `CLAUDE.md` without a line; the rewritten paragraph still names `plugin/localgpu/mcp/store.py:646` as the immune construction (now `CLAUDE.md:190-192`) and `plugin/localgpu/cli/localgpu_cli.py` as serialising before it opens (`:421`), so the `compact()` and `cmd_mcp_init` claims above hold. No claim moved. Nothing was executed.

**Re-anchored `051f9e85` -> `c192b83d` on 2026-09-28 (T-0091 review round 1).** `c192b83d` is T-0091's review-round-1 fix on `T-0091-build`. `git diff --name-only 051f9e85 c192b83d` returns only `CLAUDE.md`: the same Landmines truncating-`open` measurement paragraph, now `:185-219` (+16/-9, so every later line moves +7; lines above `:192` are byte-identical). The paragraph still names `plugin/localgpu/mcp/store.py:646` as the immune construction (`CLAUDE.md:190-192`, unmoved) and `plugin/localgpu/cli/localgpu_cli.py` as serialising before it opens (`:421`), so the `compact()` and `cmd_mcp_init` claims above hold. No claim moved. Nothing was executed.

**Re-anchored `9631c707` -> `c99e31f6` on 2026-09-28 (T-0092, crew 1.0.52).** `c99e31f6` is T-0092's crew 1.0.52 version commit on `T-0092-build`, cut from main `f54af3fa` (T-0072's landing merge, whose only commit past `9631c707` is the refresh `f1f118de`). `git diff --name-only 9631c707 c99e31f6`, refresh artifacts aside, returns T-0092's files: `plugin/crew/hooks/scripts/review_patch.py` (+8: the docstring paragraph on `graphify-out/` and one comment line; `EXCLUDED` / `_EXCLUDE_SPEC` now at `:104-105`), `plugin/crew/hooks/scripts/review_prompt.py` (+4: one docstring line and the `excluded` line at `:89-91`, so `:84` -> `:85` and `:239` -> `:243`), `test_review_patch.py`, `test_review_prompt.py`, `sabotage_review.py`, line-neutral edits to `plugin/crew/README.md` (`:726`, `:860`), `plugin/crew/commands/review.md` (`:328-332` reflowed in place), `crew_autopilot.py` (`:55-56`), `completion_audit.py` (`:74-75`) and `TODO.md` (`:5048`), `CHANGELOG.md` (+26 at the top) and the three version files (1.0.52 at `.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`). Every body citation of the form `path:line` into those files was compared by script between `9631c707` and `c99e31f6`. The only differing citations are the version-file lines, changed in place, which the provenance notes cite with the value at their own commit. No citation moved. Nothing was executed for this note.

**Re-anchored `c99e31f6` -> `3c4f1a68` on 2026-09-28 (T-0092 merged onto `c426c018`, crew 1.0.53).** `95cc12cf` merged origin/main `c426c018` (T-0076 landed as crew 1.0.52 at `e329eb8f`) into `T-0092-build`; the merge was clean (both sides had set the version files to 1.0.52). `3c4f1a68` re-bumps crew to 1.0.53 and moves T-0092's four `1.0.52` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:871`, `TODO.md:5048`, the two test-file comments) to 1.0.53, all in place. `git diff --name-only c99e31f6 3c4f1a68`, refresh artifacts aside, returns T-0076's files - `plugin/crew/hooks/scripts/crew_context.py` (+4 inside `emit`, so `sys.stdout.write` moves `:1086` -> `:1090`), `plugin/crew/README.md` (`:1691` in place), `scripts/_test/uv-install.sh` and twelve test files - plus `CHANGELOG.md` (T-0076's entry merged below T-0092's) and the version files. Every body citation of the form `path:line` into those files was compared by script between `c99e31f6` and `3c4f1a68`: the only differences are version-file lines changed in place and `CHANGELOG.md` lines inside dated provenance notes, left as history; nothing here cites `crew_context.py` at or below `:1104`. Nothing was executed for this note.

**Re-anchored `c192b83d` / `3c4f1a68` -> `25d2de63` on 2026-09-28 (T-0092 merged onto `f8b6c8d7`, T-0091, crew 1.0.53).** `25d2de63` merges origin/main `f8b6c8d7` (T-0091 landed at `c192b83d`: `CLAUDE.md`'s Landmines paragraph and a `TODO.md` entry, no plugin bumped) into `T-0092-build`. The code-map, INDEX, rules, diagram and graph conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the anchor taken from this note. Every body citation of the form `path:line` was compared by script twice: `c192b83d` -> `25d2de63` differs only on T-0092's own lines (the exclusion, the re-pointed `review_prompt.py` lines, `plugin/crew/README.md:871` in place, the version lines), and `3c4f1a68` -> `25d2de63` only on T-0091's `CLAUDE.md` lines, which T-0091's own notes above cite at `c192b83d`, and on `TODO.md:5048`, cited in T-0092's notes above as that commit's line: T-0091's three added lines move the bullet to `:5051`. Nothing was executed for this note.

**Re-anchored `25d2de63` -> `136f4b33` on 2026-09-28 (T-0092 merged onto `ff59160f`, T-0089, crew 1.0.54).** `e2220836` merges origin/main `ff59160f` (T-0089 landed as crew 1.0.53 at `0f526a8c`: `plugin/crew/tests/test_role_write_guard.py` fixtures and a `CHANGELOG.md` entry) into `T-0092-build`; the merge was clean. `136f4b33` re-bumps crew to 1.0.54 and moves T-0092's `1.0.53` mentions (`review_patch.py`'s docstring, `plugin/crew/README.md:871`, `TODO.md:5051`, the two test-file comments, its `CHANGELOG.md` heading) to 1.0.54, all in place. Every body citation of the form `path:line` into a file changed between `25d2de63` and `136f4b33` was compared by script: the only differences are version-file lines changed in place, `plugin/crew/README.md:871` in place, and lines cited inside dated provenance notes (`CHANGELOG.md`, which T-0089's entry shifts by 12 lines below `:80`, and `TODO.md:5048`), left as history at their own commit. No citation into `test_role_write_guard.py` exists here. Nothing was executed for this note.

## Re-anchor provenance - `938e3b11` + `136f4b33` -> `3648f59a`, 2026-09-28 (T-0075 review round 5, merge of `6387ab49`)

`9420bc16` merges origin/main `6387ab49` into `T-0075-build`: T-0076 (crew 1.0.52, `crew_context.py`'s byte-exact LF), T-0091 (`CLAUDE.md`'s Landmines paragraph, a `TODO.md` entry), T-0089 (crew 1.0.53, `test_role_write_guard.py` fixtures), T-0090 (mcp-servers 0.2.1, `SECURITY.md`) and T-0092 (crew 1.0.54: `review_patch.py` / `review_prompt.py` leave `graphify-out/` out of the review bundle), whose notes above are anchored `136f4b33`, `2442d367`, `c192b83d` or `b2553d26`. `faf4b0db`, `e7825a0e`, `04e3a01c`, `517628b9` and `d1460d77` are T-0075's review-round-5 steps 18-22 (`crew_config.py`, `crew_config_files.py`, their three test files, `sabotage_config.py`, `README.md`, `CONFIG.md`, `CHANGELOG.md`, `plugin/crew/BUDGETS.md`); `3648f59a` re-bumps crew to 1.0.55 (`plugin.json`, `marketplace.json`, `plugin/PLUGINS.md`, `CHANGELOG.md`). The merge's conflicting provenance kept both sides, T-0075's `## Re-anchor provenance` sections first and main's `**Re-anchored ...**` paragraphs after them; the anchor line kept T-0075's and is replaced here.

No body citation moved: this note's body cites `plugin/localgpu/` and crew's config reader by section; the `crew_config.py`, `CONFIG.md` and `README.md` lines it names sit inside dated provenance notes and keep their commit's line.

Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from `938e3b11` for a line in T-0075's copy of this note and from `6387ab49` for a line only in main's, to the tree at `3648f59a` (difflib equal blocks); every citation that did not map to itself was read with `sed -n` / `grep -n`. The script attributes some bare `:N` to the wrong file (a `.crew/verify.json` range after a test-file mention, a `check-marketplace.py` range after a `PLUGINS.md` mention, a `SKILL.md` in another skill); those were read and hold. A citation inside a list of per-commit positions keeps its commit's line; only the current position is added. Nothing else was executed for this note.

## Re-anchor provenance - `50a275ea` + `81685adf` -> `360c4029`, 2026-09-28 (T-0010-solo merges T-0079's `e6e10432`)

`c312702b` merges origin/main `e6e10432` (T-0079 landed as crew 1.0.50, its code maps anchored
`81685adf`) into T-0010-solo `ac0b5151`; `360c4029` sets crew 1.0.51. The artifact conflicts were
anchor, version and provenance lines only: T-0010's side kept for anchors and body (its
`crew_autopilot.py` and `commands/autopilot.md` line numbers are this tree's), both sides'
provenance kept. `git diff --name-only 50a275ea 360c4029`, refresh artifacts aside, is T-0079's files
(`review_verdict.py`, `review_prompt.py`, `review_run.py`, `agents/reviewer.md`, their tests and
sabotage modules, identical to origin/main's), `plugin/crew/README.md` (two lines rewritten in
place, `:735` and `:739`, line-neutral), `CHANGELOG.md` and the version files. Every citation into
T-0079's files equals main's note at `81685adf` (compared by script). No test was run by this note.

## Re-anchor provenance - `360c4029` + `136f4b33` -> `d7c7c75c`, 2026-09-28 (T-0010-solo merges `6387ab49`)

`597a62b0` merges origin/main `6387ab49` into T-0010-solo `dbb22712`: T-0072 landed as crew
1.0.51, T-0076 as 1.0.52, T-0089 as 1.0.53 and T-0092 as 1.0.54, with T-0090 (mcp-servers 0.2.1)
and T-0091 (`CLAUDE.md`) beside them; main's code maps were anchored `136f4b33`. After it,
`bd066a97` moves `settings`' two policies to a second text line (T-0072's
`test_settings_line_names_deploy` pins the first line exactly), `ab85fed0` puts `deploy-allowed`
in T-0010's only-writer test, `250c6df7` rewraps one docstring line in place, `130bf67e` re-sets
crew 1.0.55 and `d7c7c75c` re-prices `.crew/verify.json` rule 29 in place (20 -> 21). The merge
took main's side of this note; it was then re-merged three-way from `e6e10432`, T-0010's side at
`dbb22712` (anchor `360c4029`) and main's at `6387ab49`, both sides' provenance kept, main's
first. Every body `path:line` citation into a file changed since its side's commit was mapped to
`d7c7c75c` with `difflib` (a bare `:N` taken as the last file named earlier in its paragraph);
a citation followed by `at <sha>`, `before` or `->`, and every provenance section, was left as
written. A citation inside a changed hunk cannot be mapped that way and was left as written unless
this section names it.

Nothing under `plugin/localgpu/` changed on either side. The `crew_state.py` provider tuples this
note cites sit below both sides' `AUTOPILOT_DEFAULTS` hunks and read `:1437-1438` at `d7c7c75c`
(mapped by the line diff, re-read with `grep -n`). Nothing was executed for this note.

## Re-anchor provenance - `d7c7c75c` + `3648f59a` -> `cd106b8b`, 2026-09-28 (T-0010-solo merges T-0075's `e878cc31`)

`acbb0fb2` merges origin/main `e878cc31` into T-0010-solo `07032fc7`: T-0075 (`/crew:config` menu mode and
`/crew:config-setup`) landed as crew 1.0.59, its code maps anchored `3648f59a`. `92e0717a` re-measures
`plugin/crew/BUDGETS.md` (19,494 lines across 128 files) and rebuilds the troubleshooting guide's DOCX and
PDF; `cd106b8b` re-sets crew 1.0.60, one past main. The code merged without a conflict (T-0010 and T-0075 change
disjoint scripts); the conflicts were this note's anchor, provenance and a few cited lines. Both sides'
provenance was kept, main's first. Every body `path:N` citation was traced to the side whose copy of this
note carries its line (`07032fc7` or `e878cc31`) and mapped to `cd106b8b` through a `difflib` line diff
(`/root/crew-tmp/t-0010/citemap.py`, machine-local); each line that did not map to itself was read with
`sed -n` / `grep -n`. The script takes a bare `:N` as the last path named on its line, so some flags were
that misattribution (a `crew_ticket.py` or `review_ledger.py` line after another file's mention) and hold.

Nothing under `plugin/localgpu/` changed on either side. Nothing was executed for this note.

## Re-anchor provenance - `cd106b8b` -> `bbd9a66d`, 2026-09-29 (T-0010 landing branch)

`T-0010-land` merges T-0010-solo `6b89c1df` into origin/main `2693d0fa` (README re-pin only past `e878cc31`,
so the merged tree is `6b89c1df` plus that README change). `08eeaa3e` adds the ruff fix-at-land lint fixes
(owner standing rule 2026-09-28; owner decision 2026-09-29 "Fix at land"): ISC004 parentheses in
`plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/tests/sabotage_autopilot.py` and
`plugin/crew/tests/test_scope_guard.py`; `# noqa: BLE001` on five fail-closed broad excepts in
`plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/hooks/scripts/crew_ticket.py` and
`plugin/crew/hooks/scripts/scope_guard.py`; an I001/RUF100/C0207 fix in
`plugin/crew/tests/test_crew_autopilot_policy.py`. `bbd9a66d` re-sets crew 1.0.61. Each edited line kept its
number (the parentheses and comments were added in place) except in `test_crew_autopilot_policy.py`, whose
import block lost one line; no note cites that file by line. Re-anchor only; nothing was executed for this note.

**Re-anchored `c8cc69ec` -> `c0768d0e` on 2026-09-28 (T-0087, crew 1.0.53).** `c0768d0e` is T-0087's merge of main `f8b6c8d7` (T-0091, no plugin version change) into `T-0087-build`; crew stays 1.0.53, one past main's 1.0.52, and `c8cc69ec` is still the last `plugin/crew` commit. `git diff --name-only c8cc69ec c0768d0e`, refresh artifacts aside, returns `CLAUDE.md` (T-0091's Landmines truncating-`open` measurement paragraph, +35/-18 at `:189`, so every later line moves +17) and `TODO.md`. Every other body `CLAUDE.md:N` citation here is at or above `:189`, or sits inside a dated re-anchor note that states the coordinates of its own commit, so none moved. Nothing was executed for this note.

**Re-anchored `136f4b33` / `c0768d0e` -> `379ab5e6` on 2026-09-28 (T-0087 merged onto `6387ab49`, crew 1.0.55).** `01dd3854` merges origin/main `6387ab49` into `T-0087-build`: T-0089 (crew 1.0.53, `plugin/crew/tests/test_role_write_guard.py`), T-0090 (mcp-servers 0.2.1: `SECURITY.md`, ten files under `mcp-servers/`) and T-0092 (crew 1.0.54: `graphify-out/` left out of review bundles - `review_patch.py`, `review_prompt.py`, `completion_audit.py`'s comment, `crew_autopilot.py`'s docstring, `commands/review.md`, `plugin/crew/README.md`, `TODO.md`, three test files). `379ab5e6` re-bumps crew to 1.0.55, one past main's 1.0.54, and moves T-0087's `1.0.53` mentions (`plugin/crew/README.md:754`, its `CHANGELOG.md` entry) to 1.0.55 in place. The code-map, INDEX, diagram, rules and graph conflicts were resolved mechanically - both sides' provenance notes kept, main's first; the version sentence, `.claude/rules/` and `graphify-out/` taken from main and then refreshed. Every body citation of the form `path:line` was re-mapped by script (difflib over each cited file, from the anchor of the side `git blame` puts the note line on, both anchors for a line common to both, never guessed): none moved in this map. Citations the script could not map, or where the two sides' anchors disagree on a line common to both, were not re-read here and are unchanged; they predate this merge (for example `CHANGELOG.md`'s "117 -> 119" is cited at `:654-655` on both sides and sits at `:909-910`), and this pass only re-anchors.

**Re-anchored `379ab5e6` -> `17fa035e` on 2026-09-28 (T-0087 review round 1, crew 1.0.55 unchanged - not yet released).** `bbe68e85` fixes review round 1: autopilot lets a refunded round's `/crew:review` rerun past its no-progress stop, rule 31 triggers on its suites and seam consumers, `scripts/check-tooling-pr.py` admits no production code or prompt alongside the harness (a `SEAM` consumer only with a `Tooling-seam:` trailer), `golden_build.redact` bounds both sides of a match, a malformed `successors` loads as corrupt, `review_run.py`'s summary line counts charged rounds, a worktree rename is parsed, and the guides stop calling a post-refund rerun free; `17fa035e` re-prices rule 31. `git diff --name-only 379ab5e6 17fa035e`, refresh artifacts aside, returns those scripts, their tests, one golden fixture, `.crew/verify.json`, `CLAUDE.md`, `CHANGELOG.md`, `plugin/crew/README.md`, `plugin/crew/BUDGETS.md`, `commands/autopilot.md`, `commands/review.md` and the troubleshooting guide. Body citations of the form `path:line` into those files were re-mapped by script (difflib over each cited file from `379ab5e6` to `bbe68e85`, only for note lines committed before this pass, never guessed): none moved in this map.

## Re-anchor provenance - `bbd9a66d` + `17fa035e` -> `9e38a891`, 2026-09-29 (`T-0087-build` merges T-0010's `8ab733d7`)

`0fc7f609` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61, its code maps anchored
`bbd9a66d`) into `T-0087-build` `674bc4e5` (T-0087's Windows-portability successor plan, Steps 1-5
built; its maps anchored `17fa035e`). After it, `ae448309` renames T-0087's harness rule to rule 32
in text and re-measures `plugin/crew/BUDGETS.md` (19,666 lines across 129 files), `167f69a0` says
the refund ships in 1.0.62 (README, CHANGELOG), `e537e4ce` re-sets crew 1.0.62, one past main, and
`9e38a891` rebuilds the daily-workflow and troubleshooting guides from their merged sources. The code
conflicts were `crew_autopilot.next_phase` (main's `policy` argument plus T-0087's refunded-rerun
pop), `sabotage.py`'s `MUTATIONS +=` line and `test_crew_autopilot.py` (both sides kept) and the
README's Stops line (main's text plus T-0087's refunded-review clause). The artifact conflicts took
main's side for body text and kept both sides' provenance, main's first. Every body `path:N`
citation was traced to the side whose copy of this note carries its line (`674bc4e5` or
`8ab733d7`) and mapped to this tree with a `difflib` line diff (`/root/crew-tmp/t-0010/citemap.py`
and `/root/crew-tmp/t-0087/citeapply.py`, machine-local). The script takes a bare `:N` as the last
path on its line; each misattribution it produced (a `crew_autopilot.py` line after a
`review_ledger.py` or `commands/autopilot.md` mention, a `.crew/verify.json` range after a
`sabotage.py` one, a historical `at <sha>` README line) was reverted or re-read by symbol with
`grep -n`. `crew_autopilot.py` is 1751 lines: T-0087's refund hunks add 16 lines from `:522`, so
main's citations at or past `:522` moved by 6 to 16 (`next_phase` `:556`, `settings` `:745`,
`deploy_allowed` `:943`, `main` `:1648`) and nothing above it moved. T-0087's `sabotage_tooling`
import at `plugin/crew/tests/sabotage.py:82` puts the `MUTATIONS +=` statement at `:3054-3057`
(refresh `:3054`; resume, autopilot, tracker and route `:3055`; policy, approval, config and tooling
`:3056`). `.crew/verify.json` is 33 rules and 370 lines: T-0087's harness rule is rule 32 at
`:340-365`, after T-0024's rule 31 at `:332-339`. Nothing was executed for this note; the suites ran
with the build.

Nothing under `plugin/localgpu/` changed on either side. Nothing was executed for this note.

## Re-anchor provenance - `9e38a891` -> `78b7080a`, 2026-09-30 (`T-0087-build` merges T-0088's main `a61a6f38`)

`f702cb24` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68's CI ruff and xdist changes, gate-first review, the steward skill and `crew-qa-standards`) into `T-0087-build`, with a merge commit; its conflicts were mechanical and both sides were kept. `a9bc8877` moves T-0087's version text to 1.0.70 and its harness rule to `.crew/verify.json` rule 35, `90b71bbf` re-sets crew 1.0.70, one past main's 1.0.69, and `78b7080a` rebuilds two guides. Every body citation of the form `path:line` was re-mapped by script (difflib over each cited file, from T-0087's `cb9b79b1` for a note line both parents carry and from `a61a6f38` for a line only main carries, to this tree; a bare `:N` binds to the last path named on its line, with or without a line number): 8 moved in this map and were set to this tree's lines. Citations the script could not attribute to a file that has that line (a bare `:N` after a different file's name, or a short name with no directory) predate this merge and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.

## Re-anchor provenance - `78b7080a` -> `b142d8e3`, 2026-09-30 (T-0087 review round 4 fixes)

`dc412c5c` limits the refunded-rerun marker to the `review` phase in `crew_autopilot._review_phase` (+2 lines, so every `crew_autopilot.py` line from `_toward_review` on moves by 2), with a must-block test and sabotage entry (ac); `b5f87132` re-maps `plugin/crew/docs/external-tool-formats.md`'s citations and adds a test that pins them; `af7eccbe` re-times `.crew/verify.json` rule 35 in place (no line moved); `b142d8e3` corrects a CHANGELOG figure. Every body citation of the form `path:line` was re-mapped by script (difflib from `78b7080a` to `b142d8e3`; a bare `:N` binds to the last path named on its line), and the `crew_autopilot.py` citations whose path is on the line above were re-mapped by hand. Citations the script could not attribute predate this change and were left unchanged. Re-anchor only: no other claim moved and nothing was executed for this note.
**Re-anchored `2aa49bb8` -> `b82035e6` on 2026-09-28 (T-0085 merges main `f8b6c8d7`, T-0091).** `17b70570` merged origin/main `f8b6c8d7` into `T-0085-build` (mechanical conflicts only: anchors, provenance paragraphs, INDEX history cells, generated rules and graph); `b82035e6` moves the crew skills claim at `plugin/README.md:414` and `INSTALLATION.md:252` from 29 to 30 (spec Touch amendment). Of the paths this note cites, `git diff --name-only 2aa49bb8 b82035e6` returns only `CLAUDE.md`. `CLAUDE.md`'s change is T-0091's Landmines truncating-`open` paragraph, whose citations were moved on main's side and merged in, plus T-0085's four-line ignore-policy reflow, which shifts no line. Every `CLAUDE.md:N`, `INSTALLATION.md:N` and `plugin/README.md:N` citation was compared by script against its text at `2aa49bb8`, `c192b83d` and HEAD; none needed moving: every `CLAUDE.md:N` citation here reads the same text at HEAD as at main's `c192b83d`, where T-0091 already moved them. No suite was executed for this note.

**Re-anchored `136f4b33` -> `8a084c6c` on 2026-09-28 (T-0085 merges main `6387ab49`, T-0089, T-0090, T-0092; crew 1.0.55).** `f97219dc` merged origin/main `6387ab49` into `T-0085-build` (mechanical conflicts only: crew version lines, CHANGELOG, anchors, provenance paragraphs, INDEX history cells, diagram headers, generated rules and graph); `8a084c6c` re-bumps crew to 1.0.55, one past main's 1.0.54. Each side had already re-verified its own changes (main's line to `136f4b33`/`2442d367`/`b2553d26`, T-0085's to `b82035e6`), so this pass checks the files BOTH sides changed: the crew version lines (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`, value only, same line), `CHANGELOG.md` (both sections kept; release bookkeeping), `plugin/crew/README.md` and `plugin/crew/commands/review.md` (main's T-0092 edits are in place and line-neutral: 2883 and 551 lines, as on T-0085's side), `plugin/crew/hooks/scripts/review_prompt.py` (main's docstring line split in two at `:6-7` and three `excluded` lines added at `:96-98` shift T-0085's lines below them by 4) and `plugin/crew/tests/test_review_prompt.py`. Every `path:N` citation into those files was compared by script against its text on the side that wrote it (`f3ad630b` or `6387ab49`) and at the merged tree; none moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `8a084c6c` -> `07bcaf3b` on 2026-09-28 (T-0085 review round 1 fixes).** `07bcaf3b` changes `plugin/crew/hooks/scripts/crew_standards.py` (`gate_applies`, `checklist_block`, `stamp`, `_plugin_sets`, the module docstring), its tests and sabotage entries, `.crew/standards.md` (REPO-03's rule text), `.crew/verify.json` (rule 31 gains two test files; its `seconds` and `why`), `CHANGELOG.md` (T-0085's bump bullet, two lines to three), `plugin/crew/BUDGETS.md:10-11` (the count, in place), `plugin/crew/README.md` (three table rows, in place), `plugin/crew/commands/implement.md` (two lines reflowed in place; still 120 lines), `plugin/crew/commands/review.md` (step 6's reviewer-cell line becomes three, so lines below `:530` move by 2), `plugin/crew/skills/crew-standards/SKILL.md`, ADR 0004 and the working-with-codex guide. Every `path:N` citation in this note into those files was compared by script between `8a084c6c` and `07bcaf3b`: every hit is a `plugin/crew/BUDGETS.md:11` citation inside an earlier dated provenance paragraph, left as history; no body claim moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `07bcaf3b` -> `8abf7ffe` on 2026-09-28 (T-0085 provisional re-bump, crew 1.0.56).** `8abf7ffe` moves crew's version 1.0.55 -> 1.0.56 in place (`.claude-plugin/marketplace.json:218`, `plugin/crew/.claude-plugin/plugin.json:3`, `plugin/PLUGINS.md:14`), because the round-1 fixes changed `plugin/crew/` after 1.0.55 was set and `scripts/check-marketplace.py`'s version-drift check failed on it; it also rewords `.crew/standards.md` REPO-03 (the provisional bump) and T-0085's `CHANGELOG.md` heading and bump bullet (three lines to four). Every `path:N` citation in this note into those files was compared by script between `07bcaf3b` and `8abf7ffe`: the version-file citations hold (value changed in place, same line) and every hit sits inside an earlier dated provenance paragraph, left as history; no body claim states the version. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `3648f59a` / `8abf7ffe` -> `e3f5fa49` on 2026-09-29 (T-0085 merges main `2693d0fa`, T-0075 landed as crew 1.0.59, and applies the owner-accepted round-1 standards amendments).** `0fd1bdf8` reverts T-0085's provisional crew 1.0.56 bump (`8abf7ffe`); `0fd92334` merges origin/main `2693d0fa` into `T-0085-build` (mechanical conflicts only: crew version lines take main's 1.0.59, crew counts take main's 36 commands with T-0085's 30 skills, `plugin/crew/tests/sabotage.py` registers both `CONFIG_MENU_MUTATIONS` and `STANDARDS_MUTATIONS`, anchors, provenance paragraphs, INDEX history cells, diagram notes, generated rules and graph); `e3f5fa49` amends GEN-01 and GEN-04 in `plugin/crew/skills/crew-standards/references/generic.md` and REPO-03 in `.crew/standards.md`, drops the version from T-0085's `CHANGELOG.md` heading and re-measures `plugin/crew/BUDGETS.md`. The build branch now declares main's 1.0.59 and carries no bump of its own (REPO-03 as amended). Every `path:N` citation outside provenance was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from the side that wrote it - `3648f59a` for a line in main's copy of this note, `0fd1bdf8` for a line only in T-0085's - to `e3f5fa49`, and every line that did not map to itself was read with `sed -n` / `grep -n`; the script attributes some bare `:N` to the wrong file, and those were read and hold. None moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `e3f5fa49` -> `001f8a78` on 2026-09-29 (T-0085 successor plan, review round 2's fixes).** `bc3602df`..`001f8a78` change `plugin/crew/hooks/scripts/crew_standards.py` (`_scope` gains the merge-base fallback for a kept but unusable scope record, `_has_scope_entry` and `_noted` are new, so every definition from `_scope` down moves by +8 to +30 lines), its tests (`test_crew_standards.py`, `test_review_run_standards.py`, `test_lifecycle_commands.py`) and `plugin/crew/tests/sabotage_standards.py` (nineteen new entries; `STANDARDS_MUTATIONS` moves `:21` -> `:35`), `plugin/crew/skills/crew-standards/SKILL.md` (step 3, +5 lines), `plugin/crew/README.md` (one table row, in place), `CHANGELOG.md` (one bullet in T-0085's section, so every line below it moves +8) and `plugin/crew/BUDGETS.md:11` (the count, in place). Every `path:N` citation in this note into those files was mapped by script (difflib equal blocks; a same-size in-place replacement counts as the same line) from `e3f5fa49` to `001f8a78`; none moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `001f8a78` / `bbd9a66d` -> `a7f9c5e4` on 2026-09-29 (T-0085 merges main `8ab733d7`, T-0010 landed as crew 1.0.61).** `a7f9c5e4` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61) into `T-0085-build` after T-0085's review round 3 fixes (`33521aa4`), with mechanical conflicts only: crew version lines take main's 1.0.61 with T-0085's 30 skills (the build branch carries no bump, REPO-03 as amended), `plugin/crew/tests/sabotage.py` registers `POLICY_MUTATIONS`, `APPROVAL_MUTATIONS`, `CONFIG_MENU_MUTATIONS` and `STANDARDS_MUTATIONS` on `:3056`, anchors, provenance (both sides kept, main's first), INDEX history cells, version sentences, diagram headers, generated rules and graph. Every body `path:N` citation was traced to the side whose copy of this note carries its line (`33521aa4` or `8ab733d7`) and mapped from that side's anchor to `a7f9c5e4` through a difflib line diff (`/root/crew-tmp/t-0085/citemap.py`, machine-local; only cited files that changed; a bare file name resolved when unique in `git ls-files`); each citation that did not map to itself was read with `sed -n` / `grep -n`, and the script's misattributed bare `:N` (a `sabotage_autopilot.py` or `crew_ticket.py` line after another file's name, a history list's earlier positions) were read and hold. Nothing under `plugin/localgpu/` changed on either side (`git diff --name-only 001f8a78 a7f9c5e4 -- plugin/localgpu` is empty); no body citation moved. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `a7f9c5e4` / `b4f39fd3` -> `69c7edbd` on 2026-09-30 (T-0085's landing merge of main `a61a6f38`, crew 1.0.70).** `69c7edbd` merges T-0085's build head `0c6f01e0` (round 4, owner-accepted) onto origin/main `a61a6f38` (crew 1.0.69: #263-#267 and T-0088) on `T-0085-land`, and sets crew 1.0.70. Every body `path:N` citation was mapped by script (`difflib` equal blocks, from the anchor of whichever side's copy of this note carries the line - `a7f9c5e4` for T-0085's, main's own anchor for main's - to `69c7edbd`); each that mapped to one new line was moved, and each that did not map, or mapped differently from the two sides, was read with `sed -n` / `grep -n`. The script attributes a bare `:N` to the last path cited with a line number, so a bare `:N` after a path named without one (`.crew/verify.json` rule ranges, `crew_tfplan.py`, `sabotage_autopilot.py`, `crew_ticket.py`, `crew_standards.py`) was read against its real file and put back where the script moved it wrongly; `.crew/verify.json` lines up to `:339` did not move, and T-0085's rule is now `:361-373`, the last. A bare `review.md` citation is ambiguous since #267 added `crew-qa-standards/references/review.md`, so the script skipped those; `plugin/crew/commands/review.md` moved only below `:543` (+1, +3), and its cited lines above that were re-read. In this note eight citations into `crew_config.py` (+1) and `crew_state.py` (+3) moved; nothing under `plugin/localgpu/` changed. Paragraphs dated before this one describe the tree at their own anchor and were not rewritten. No suite was executed for this note.

**Re-anchored `69c7edbd` -> `7c86bd13` on 2026-09-30 (T-0085 landing: one sabotage anchor re-taken).** `git diff --name-only 69c7edbd 7c86bd13`, refresh artifacts aside, returns only `plugin/crew/tests/sabotage_standards.py`: the find and replace text of "review.md loses the self-check refusal" now end at `rebuild.` / `provider.`, because the merge joined main's exit-5 sentence onto that line. No line was added or removed; no citation moved. No suite was executed for this note.

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

**Re-anchored `5c9a9db2` -> `06cb9b51` on 2026-09-30 (T-0086 slice 1: the Python standards set, on main `301e478a`).** `git diff --name-only 5c9a9db2 06cb9b51` over this note's paths returns T-0086's files - `plugin/crew/skills/crew-standards/references/python.md` (new, set PYTHON), `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/test_crew_standards.py` (four new tests), `plugin/crew/tests/sabotage_standards.py` (three entries), `plugin/crew/README.md`, `plugin/PLUGINS.md` (rows only), `plugin/crew/BUDGETS.md` (count only) and `CHANGELOG.md` (T-0086's entry on top) - plus main's own commits since `5c9a9db2`. Path-qualified citations into changed files were moved by a line diff (`/root/crew-tmp/t-0086/remap.py`, 9 moved); `plugin/crew/BUDGETS.md:10-11` citations stay on the claim line, whose number changed in place. No suite was executed for this note.
**Re-anchored `06cb9b51` -> `35100955` on 2026-09-30 (T-0086's merge of main `9af34e57`, #279: CI triggers, concurrency, PR CI on Python 3.12 only).** `git diff --name-only 06cb9b51 35100955` returns, outside refresh artifacts, only `.github/workflows/*.yml`, `AGENTS.md` and `.crew/verify.json` (one line rewritten in place, line count unchanged). No `AGENTS.md:NN` citation exists in any map, and no claim outside verification-harness.md states the CI trigger shape (checked by grep for `push, pull_request`, `six workflows`, `three Python versions`, `windows-latest`), so no citation moved. No suite was executed for this note.

**Re-anchored `35100955` -> `fb292689` on 2026-09-30 (T-0086 review round 1's FIX: PYTHON-07's finding count).** `git diff --name-only 35100955 fb292689` returns only `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-07's Why, `6` -> `7` in place, line count unchanged), `plugin/crew/tests/test_crew_standards.py` (two tests and a pinned table inserted after `:302`) and `plugin/crew/tests/sabotage_standards.py` (four docstring lines after `:43`, two entries at the end; `STANDARDS_MUTATIONS` `:54` -> `:57`, 49 entries by `len()`). Every `path:N` citation into those files sits inside an earlier dated provenance paragraph, left as history. No suite was executed for this note.

**Re-anchored `fb292689` -> `f2cf0508` on 2026-09-30 (T-0086's merge of main `b601d450`, #280 L-0521: opt-in self-hosted runners).** `git diff --name-only fb292689 f2cf0508` returns, outside refresh artifacts, only `.github/workflows/pytest-crew.yml` (the `test` and `crew-shell-matrix` `runs-on` expressions) and `AGENTS.md` (one inserted paragraph after `:50`). No map cites `AGENTS.md:NN` or `.github/workflows/pytest-crew.yml:NN`; the one claim about those jobs' runner placement is verification-harness.md's, which main's own L-0521 commit already updated and the merge carries. No citation moved. No suite was executed for this note.

**Re-anchored `f2cf0508` -> `38b220cf` on 2026-09-30 (T-0086 review round 2's FIXes, merge of main `a7524aac` (T-0087, crew 1.0.76) as `142421d0`, crew 1.0.77).** `27387d83` fixes round 2: `plugin/crew/skills/crew-standards/references/python.md` (PYTHON-01's EncodingWarning quote whole, +1 line; PYTHON-03's splitlines table escapes U+2028/U+2029), `plugin/crew/tests/test_crew_standards.py` (two tests before `test_python_set_applies_to_python_files_only`), `plugin/crew/tests/sabotage_standards.py` (four docstring lines, two entries; `STANDARDS_MUTATIONS` `:57` -> `:61`, 51 by `len()`), `plugin/crew/BUDGETS.md` and `CHANGELOG.md`. `142421d0` merges main's T-0087 with a merge commit; its map conflicts were mechanical: anchors took T-0086's side, provenance hunks kept both (main's first), and one-line hunks differing only in numbers took theirs plus T-0086's own shift (ours + theirs - base, per number); INDEX rows keep main's history cell plus T-0086's additions; `sabotage.py`'s import `:84` -> `:85` and append `:3061` -> `:3062` were set in the body. `38b220cf` sets crew 1.0.77 (`plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:218`, `plugin/PLUGINS.md:14`). BUDGETS.md re-measured at 21,421 lines across 136 files. No suite was executed for this note.

## Re-anchor provenance - `3648f59a` -> `ea764992`, 2026-09-29 (T-0094)

T-0094 is built on origin/main `2693d0fa`: `3648f59a` plus T-0075's landing branch (crew 1.0.56-1.0.59: `crew_config_files.py`, `crew_config_menu.py`, `test_config_menu.py`, `sabotage_config.py`) and `17d057db`, the README re-pin. T-0094's commits `be023596`..`ea764992` change crew's refresh-artifact admission (`crew_refresh_check.py`, `completion_audit.py`, `scope_guard.py`'s docstring, their tests), `plugin/crew/README.md`, `.crew/verify.json` rule 25 and the version files. This note reaches them only through its citations of `.crew/verify.json` and `plugin/crew/README.md`, neither cited by line outside provenance, and describes `plugin/localgpu/`, which no commit in `3648f59a..ea764992` touches (`git diff --name-only 3648f59a ea764992 -- plugin/localgpu` is empty).

No body citation moved: checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from `3648f59a` to the tree at `ea764992` (difflib equal blocks). Nothing else was executed for this note.

## Re-anchor provenance - `ea764992` -> `f79e9f58`, 2026-09-29 (T-0094 review round 1)

`f79e9f58` ends T-0094's review-round-1 fixes (`abe87bc2`..`f79e9f58`). Of the paths this map cites, `.crew/verify.json` (rule 25's `seconds` and `why`, in place), `plugin/crew/README.md` (one refresh-admission paragraph reworded in place) changed; no citation here moved (checked by script, every `path:N` compared line by line from `ea764992` to `f79e9f58`, then the hits read). No claim changed.

## Re-anchor provenance - `bbd9a66d` + `f79e9f58` -> `6375524b`, 2026-09-29 (T-0094 merges `8ab733d7`; review round 2's successor)

`f050cd47` merges origin/main `8ab733d7` (T-0010 landed as crew 1.0.61, its code maps anchored `bbd9a66d`) into T-0094-build at `ca5b1f35` (T-0094's side anchored `f79e9f58`, plus review round 2's FIX 1 `da1532d6` and FIX 2 `ca5b1f35`). The artifact conflicts were anchor, version, provenance and cited-line text only: both sides' provenance kept, main's first; INDEX history columns joined; body hunks resolved to main's lines except T-0094's own refresh-admission paragraph and refresh-check entry point. After it, `157237c2` splits `.crew/verify.json` rule 25 (the admission suite is rule 32 at `:342-349`, rule 25 `:269-287`, every later rule moves by the merged and split lengths), restates the sabotage counts in `plugin/crew/tests/sabotage_refresh.py`, and edits `plugin/crew/README.md` and `docs/guides/crew/src/daily-workflow-scope.md` in place; `ef5b4c89` re-measures `plugin/crew/BUDGETS.md` (19,500 lines across 128 files); `fc348c89` sets crew 1.0.62; `6375524b` rebuilds the daily-workflow guide. `git diff --name-only bbd9a66d 6375524b`, refresh artifacts aside, is T-0094's files only: `.claude-plugin/marketplace.json`, `.crew/verify.json`, `CHANGELOG.md`, the daily-workflow guide and its source, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `commands/done.md`, `commands/implement.md`, `completion_audit.py`, `crew_refresh_check.py`, `scope_guard.py` and T-0094's five test files. Every body `path:N` citation was traced to the side whose copy of this note carries its line (`8ab733d7` or `ca5b1f35`) and mapped to HEAD with a `difflib` line diff (`/root/crew-tmp/t-0094/cite_map_merge.py`, machine-local); each that did not map to itself was read with `sed -n` / `grep -n`. The script takes a bare `:N` as the last path named on its line, so some flags were that misattribution and hold; a history position ("before", "at <sha>", "since ...") was left as written. Nothing under `plugin/localgpu/` changed on either side; no body citation moved. Nothing was executed for this note.

## Re-anchor provenance - `6375524b` -> `f5d0f1b1`, 2026-09-30 (T-0094 merges `a61a6f38`, crew 1.0.70)

`0cd952b2` merges origin/main `a61a6f38` (T-0088 landed as crew 1.0.69, after #263-#267: crew 1.0.62-1.0.68, the review gate `review_gate.py`, the `crew-qa-standards` skill, parallel CI and `CLAUDE.md`'s evidence moved to `docs/claude-md-evidence.md`) into T-0094-build at `d331c192`. Its conflicts were the version lines, `CHANGELOG.md` (both entries kept, T-0094's first), `.crew/verify.json` (T-0094's rule 32 kept, main's three new rules after it as 33-35), `crew_refresh_check.py`'s imports (both kept) and `plugin/crew/BUDGETS.md` (re-measured, 19,921 lines across 132 files); no code map, diagram or rule file conflicted (main's maps were still at `bbd9a66d`, but for `obsidian-vault.md`). `f5d0f1b1` sets crew 1.0.70, one past main's 1.0.69. Per-path: `git diff --name-only 6375524b f5d0f1b1 -- <the 63 tracked paths this note cites>` returns `.claude-plugin/marketplace.json`, `.crew/codemap/localgpu.md`, `.crew/verify.json`, `CHANGELOG.md`, `CLAUDE.md`, `README.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/CONFIG.md`, `plugin/crew/README.md`, `plugin/crew/commands/review.md`, `plugin/crew/hooks/scripts/crew_autopilot.py`, `plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/hooks/scripts/crew_context.py`, `plugin/crew/hooks/scripts/crew_state.py`, `plugin/crew/hooks/scripts/crew_ticket.py`, `plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_autopilot.py`. Citations were re-mapped by a `difflib` line diff from each cited file's copy at the old anchor to `f5d0f1b1` (`/root/crew-tmp/t-0094/cite_apply2.py`, `cite_ident.py`, `cite_explicit.py`, machine-local): an explicit `path:N`, and a bare `:N` whose file is the one named before it in the paragraph, or the one whose old line carries the identifier beside the citation; every mapped line is text-identical at both ends. History positions ("at <sha>", "before", "on <branch>", "it was") and the provenance sections were left as written; a bare `:N` the scripts attributed to the wrong file was found by that identifier check and put back. Nothing under `plugin/localgpu/` changed. `crew_config.py`'s `DEV_PROVIDERS`/`QA_PROVIDERS` re-export is `:129-130` (re-read with `sed -n`); the QA-round history lists that cite `:126-127` / `:1504-1505` are left as written. Nothing was executed for this note.

**Re-anchored `f5d0f1b1` -> `2255fb4d` on 2026-09-30 (T-0094 review round 3).** `2255fb4d` is T-0094's review-round-3 fix commit (Codex round 3 on `e0ccd3f7`: 0 BLOCK / 4 FIX). `git diff --name-only f5d0f1b1 2255fb4d` returns `.crew/codemap/crew.md`, `CHANGELOG.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/sabotage_refresh.py` and `plugin/crew/tests/test_refresh_admission.py`; the two commits after `f5d0f1b1` before it are refresh artifacts only. This note cites those files by name or in its provenance only; no body citation moved.

**Re-anchored `2255fb4d` -> `0c19512c` on 2026-09-30 (T-0094 crew 1.0.71).** `0c19512c` sets crew 1.0.71 (review round 3's fixes changed `plugin/crew/` after 1.0.70 was set, and origin/main is 1.0.70 too, T-0097 #268). Per-path: `git diff --name-only 2255fb4d 0c19512c` over this note's cited paths returns only `plugin/crew/README.md` (two in-place "since 1.0.70" -> "since 1.0.71" edits, line count unchanged), beside the version files and `CHANGELOG.md` (release bookkeeping). No body citation moved.

**Re-anchored `0c19512c` (T-0094) / `5c9a9db2` (main) -> `1b9e4bfe` on 2026-09-30 (T-0094 merges main `9af34e57`, T-0085 landed as crew 1.0.75; review round 4's successor, crew 1.0.76).** `e1144866` merges origin/main `9af34e57` into T-0094-build at `7c261a19`; this map conflicted on anchor, version, provenance and cited-line text only (both sides' provenance kept, main's first; body hunks resolved to main's lines for files T-0094 does not change, T-0094's for its own). `c815bed8` and `f3fe692f` are the successor's code steps (`crew_refresh_check.py`: `_names_no_commit` new before `_moved_from`, `_rendered_verdict` pairs its source case-folded; `completion_audit.py`: `_default_artifacts` new after `_verdicts`; their tests, fixtures and sabotage entries), and `1b9e4bfe` sets crew 1.0.76 with the README, CHANGELOG and daily-workflow guide text. Per-path, `git diff --name-only 5c9a9db2..1b9e4bfe` over this note's 72 cited, existing paths returns `.claude-plugin/marketplace.json`, `.crew/verify.json`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/commands/implement.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/hooks/scripts/scope_guard.py`, `plugin/crew/tests/sabotage_refresh.py`, `plugin/crew/tests/test_refresh_admission.py`; from T-0094's side, `0c19512c..1b9e4bfe` adds `.crew/standards.md`, `plugin/README.md`, `plugin/crew/commands/review.md`, `plugin/crew/hooks/scripts/crew_standards.py`, `plugin/crew/hooks/scripts/review_prompt.py`, `plugin/crew/skills/crew-setup/SKILL.md`, `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/crew-standards/references/generic.md`, `plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_scope.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_crew_standards.py`, `plugin/crew/tests/test_ps1_python_probe.py`, `plugin/crew/tests/test_review_prompt.py` (main's T-0085, T-0097 and CI changes). Every body `path:N` citation was mapped by `/root/crew-tmp/t-0094/cite_map_merge.py` (difflib equal blocks, from the anchor of whichever side's copy carries the line; `MAIN_REV=origin/main`, `OURS_REV=7c261a19`) and each one it reported was read at HEAD. No body citation moved. No suite was executed for this note.

**Re-anchored `1b9e4bfe` -> `8a15557b` on 2026-09-30 (T-0094: `implement.md` step 6 rewrapped to its 120-line budget).** `git diff --name-only 1b9e4bfe 8a15557b`, refresh artifacts aside, returns `plugin/crew/BUDGETS.md` (the count, in place: 20,711 lines) and `plugin/crew/commands/implement.md`: the merged step-6 paragraph (T-0094's admission sentence beside main's self-check paragraph) was 122 lines, over `test_lifecycle_commands.py`'s 120-line command budget, and is rewrapped to 104 columns with its wording unchanged, so every line from the self-check paragraph down sits where main has it again (tracker `:112`, step 7 `:116`); the refresh check is still `:93`. No other body citation moved. No suite was executed for this note beyond `test_lifecycle_commands.py`.

**Re-anchored `8a15557b` -> `a0c171c7` on 2026-09-30 (T-0094 review round 5).** `git diff --name-only 8a15557b a0c171c7` over this note's cited paths, refresh artifacts and release bookkeeping aside, returns `docs/guides/crew/src/daily-workflow-scope.md` (one could-not-tell sentence extended, +1 line at `:104-106`), `plugin/crew/README.md` (one sentence extended in place, line count unchanged), `plugin/crew/hooks/scripts/crew_refresh_check.py` (`_present` new at `:327`, everything below it +19 to +25 lines), `plugin/crew/tests/sabotage_refresh.py` (+4 docstring lines, five entries appended after the round-5 marker), `plugin/crew/tests/test_refresh_admission.py` (+1 import line, the round-5 tests appended). No body citation of this note names a moved line of those files. Citations checked with `/root/crew-tmp/t-0094/cite_apply3.py` (DRY, machine-local) and `grep -n`. No suite was executed for this note.

**Re-anchored `a0c171c7` (T-0094) / main -> `a0db0703` on 2026-09-30 (T-0094 merges origin/main `a7524aac`, T-0087 landed as crew 1.0.76, #281, and L-0521, #280; crew 1.0.77, before review round 6).** `f6f2c2f0` merges `a7524aac` into T-0094-build at `75565970`; `a0db0703` re-sets the version one past main's 1.0.76 (plugin.json, marketplace.json, `plugin/PLUGINS.md:14`, two README sentences, the CHANGELOG heading). The code maps conflicted on anchor, version, provenance and cited-line text only: both sides' provenance kept, main's first. In body hunks a citation into a file only one side changed takes that side's number (`crew_autopilot.py`, `review_ledger.py`, `sabotage.py` and `CLAUDE.md` main's; `crew_refresh_check.py` T-0094's); positions in files both sides changed (`.crew/verify.json`, `plugin/crew/tests/sabotage_refresh.py`) were re-measured on the merged tree: T-0087's harness rule is rule 37 at `.crew/verify.json:384-409`, after T-0094's rule 32; `REFRESH_MUTATIONS` is at `plugin/crew/tests/sabotage_refresh.py:119`; the CLAUDE.md Lessons line is `:144`. Checked by a script mapping every `path:N` citation outside provenance sections, and every bare `:N` carried from the last path named in its paragraph, from each side's anchor (`a0c171c7` and main's own) to `a0db0703` (difflib equal blocks): no citation outside those re-measured positions fails both mappings. Carried as main has them, not corrected here: main's own `crew_autopilot.py` body citations in `crew.md` that already lag main's tree by a few lines (e.g. `next_phase` `:556`, the def is at `:559`) - outside T-0094's change.

**Re-anchored `a0db0703` (T-0094) / `38b220cf` (main) -> `65abeb8d` on 2026-09-30 (T-0094 merges origin/main `549cda24`, T-0086 landed as crew 1.0.77, #282, as `44407f8e`; the owner's split moves the harness half to L-0540 at `c974f997`; review round 6's successor `6ecb6403`..`b17266ed`; crew 1.0.78 at `65abeb8d`).** Per-path, `git diff --name-only a0db0703 65abeb8d` over this note's 90 cited, tracked paths returns `.claude-plugin/marketplace.json`, `.crew/codemap/crew.md`, `.crew/codemap/localgpu.md`, `CHANGELOG.md`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/hooks/scripts/scope_guard.py`, `plugin/crew/skills/crew-standards/SKILL.md`, `plugin/crew/skills/crew-standards/references/python.md`, `plugin/crew/skills/stack-python/SKILL.md`, `plugin/crew/tests/sabotage_refresh.py`, `plugin/crew/tests/sabotage_standards.py`, `plugin/crew/tests/test_crew_standards.py`, `plugin/crew/tests/test_refresh_admission.py`; from main's side, `git diff --name-only 38b220cf 65abeb8d` over the same paths returns `.claude-plugin/marketplace.json`, `.crew/codemap/crew.md`, `.crew/codemap/localgpu.md`, `.crew/verify.json`, `CHANGELOG.md`, `docs/guides/crew/src/daily-workflow-scope.md`, `plugin/PLUGINS.md`, `plugin/crew/.claude-plugin/plugin.json`, `plugin/crew/BUDGETS.md`, `plugin/crew/README.md`, `plugin/crew/commands/implement.md`, `plugin/crew/hooks/scripts/crew_refresh_check.py`, `plugin/crew/tests/test_refresh_admission.py`. The merge's conflicts in this map were the anchor and provenance only (both kept, main's first). No body citation in this map names a line the successor or the merge moved (checked with `/root/crew-tmp/t-0094/cite_map_merge.py`, `MAIN_REV=origin/main`, `OURS_REV=b4d87187`, machine-local). No suite was executed for this note.

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
same line text. The provider tuples now carry `kimi` (`crew_state.py:1450-1451`), re-read with `grep -n`. T-0028's earlier branch provenance is in git history. Re-anchor
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

**Re-anchored `11f476a2` -> `1390bb23` on 2026-10-01 (L-0516 merges main `52489039` (T-0110 #297 at crew 1.0.97, T-0040 #290 at 1.0.98) without rerere and re-bumps crew to 1.0.100).** Main moved while this lane's suites ran. Conflicts were refresh artifacts, CHANGELOG and BUDGETS.md only; maps, diagram notes and INDEX keep both histories (main's first). A citation re-map that follows each line's origin (this branch's lines from `e9375690`, main's from `52489039`, each to `1390bb23`; history skipped) moved nothing: main's own lines already carry T-0040's moves (`CONFIG.md`, `crew_config.py`, crew README). Re-read by hand: `crew.md`'s W-0116 `_FINAL_PATH` sentence keeps this branch's text (`crew_refresh_check.py:716`); `verification-harness.md`'s verify.json paragraph now reads 42 rules / 443 lines (T-0040's rule 42 at `.crew/verify.json:433-439`, `default` `:441`, `unmapped` `:442`), and rule 39 `:418-431` is unchanged. No suite was executed for this note.

**Re-anchored `1390bb23` -> `0027f794` on 2026-10-01 (L-0516 merges main `05a679bf` (L-0558 #293 at crew 1.0.102) without rerere and re-bumps crew to 1.0.103).** Main moved while this lane's required checks ran. Conflicts were refresh artifacts, CHANGELOG and the version files only; maps, diagram notes and INDEX keep both histories (main's first). Main's change outside refresh artifacts is `crew_train.py`, `test_crew_train.py`, crew README, the daily-workflow and troubleshooting guides, CHANGELOG, the version files and `.crew/verify.json` rule 37's line rewritten in place (443 lines at both `1390bb23` and `0027f794`, so no `.crew/verify.json:N` citation moves). Main's own lines already carry L-0558's `crew_train.py` moves; no line this branch added cites `crew_train.py`, `test_crew_train.py`, the crew README or either guide by line. `crew.md`'s version sentence names 1.0.103 in place. No suite was executed for this note.

**Re-anchored `9580571e` (main's side of the merge) and `4a48f594` (L-0513's side) -> `de32cb87` on 2026-10-01 (L-0513 merges origin/main `44d3dbc6` at `293b78a1` with `git -c rerere.enabled=false`, bringing T-0110 #297 and crew 1.0.97, then review round 4's five fixes; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept above. `git diff --name-only 9580571e de32cb87` outside refresh artifacts returns L-0513's `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`, `.crew/verify.json` (rules 22 and 40: `seconds` 55 -> 57 and their `why`, in place, line count unchanged), `CLAUDE.md` (L-0513's two-line pointer in Commands) and `CHANGELOG.md`, and main's T-0110 files: `.github/workflows/pytest-crew.yml`, `AGENTS.md`, eight files under `plugin/crew/tests/` (`crew_fixtures.py`, `test_msys_tmp_pin.py` and six others) and the version files `.claude-plugin/marketplace.json`, `plugin/PLUGINS.md:14` and `plugin/crew/.claude-plugin/plugin.json:3` (crew 1.0.97, in place). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `de32cb87`, found every one mapping onto itself from at least one parent, except the in-place version lines and `CHANGELOG.md:N` figures inside history notes, left as written; `crew.md`'s version sentence now reads 1.0.97. No suite was executed for this note.

**Re-anchored `de32cb87` -> `f23b01b4` on 2026-10-01 (L-0513 Fix phase: review round 5's two FIX findings; repository tooling, no plugin version of its own, crew is main's 1.0.97).** `git diff --name-only de32cb87 f23b01b4` outside refresh artifacts returns `scripts/gate-runner.py` (`_valid_result` now takes the table step, requires phase/group/argv/cwd/timeout, and refuses a FAIL whose rc `classify()` would not call FAIL), `scripts/_test/gate-runner.py` (two new cases, `part_row`), `.crew/verify.json` (rules 22 and 40: `seconds` 57 -> 58 and their `why`, in place, line count unchanged) and `CHANGELOG.md` (+3 lines inside L-0513's entry, at :30-36). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped) from `de32cb87` found every one mapping onto itself except nine `CHANGELOG.md:N` citations in `crew.md`, shifted +3 to the lines they cited, and the in-place `.crew/verify.json:260`/`:430` lines. No suite was executed for this note.

**Re-anchored `f23b01b4` (L-0513's side) and main's side -> `71038cb9` on 2026-10-01 (L-0513 owner amendment for review round 6's BLOCK at `fbd48532`, then `git -c rerere.enabled=false merge origin/main` `52489039` (T-0040 #290, crew 1.0.98) at `74130bbd`, then rules 22 and 40 repriced at `71038cb9`; repository tooling, no plugin version of its own).** `git diff --name-only f23b01b4 71038cb9` outside refresh artifacts returns L-0513's `scripts/gate-runner.py` and `scripts/_test/gate-runner.py` (the BLOCK fix: no process-group signal once the leader is reaped, and its two cases), `CHANGELOG.md` (L-0513's entry +3 lines; T-0040's 1.0.98 entry now sits below it) and `.crew/verify.json` (rules 22 and 40 `seconds` 58 -> 60 and `why`, in place; T-0040's shell-route rule appended as rule 41 at `:432-437`), and T-0040's own paths, which main's side of this map already describes. Where the merge conflicted here it was the anchor header and these provenance notes: both sides kept, main's first. The `CHANGELOG.md:N` citations in older provenance notes name lines at the commits those notes name and were not shifted. Refresh artifacts per owner rule 2026-09-28; no test suite was executed for this note.

**Re-anchored `71038cb9` (L-0513's side) and `89ebda03` (main's side) -> `0d159692` on 2026-10-01 (L-0513 merges origin/main `05a679bf` - L-0558 #293, crew 1.0.102 - at `0d159692` with `git -c rerere.enabled=false`; repository tooling, no plugin version of its own).** The merge's conflicts in this map were the anchor header and these history notes only; both sides' notes are kept, main's first. `git diff --name-only 71038cb9 0d159692` outside refresh artifacts is main's L-0558 change only: `plugin/crew/hooks/scripts/crew_train.py`, `plugin/crew/tests/test_crew_train.py`, `plugin/crew/README.md`, the daily-workflow and troubleshooting guide sources and their six builds, `.crew/verify.json`, `CHANGELOG.md` and the three version files (crew 1.0.102). A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor to `0d159692`, found every one mapping onto itself from at least one parent except three `CHANGELOG.md:N` citations in `crew.md` from L-0513's side, moved to the lines they cited (`:485-486` -> `:519-520`, `:645-646` -> `:679-680`, `:274` -> `:308`); `crew.md`'s version sentence now reads 1.0.102. No suite was executed for this note.

**Re-anchored `0027f794` (L-0516's side) and `0d159692` (main's side) -> `ec95c8aa` on 2026-10-01 (L-0516 merges origin/main `cacf7ff0` - L-0513 #301, the gate runner; crew stays 1.0.102 on main - with `git -c rerere.enabled=false`; crew 1.0.104, re-bumped at `1f2114bc` past 1.0.103, which L-0510's worktree claimed first).** Conflicts were refresh artifacts and CHANGELOG only; each map keeps both re-anchor histories. `git diff --name-only 0027f794 ec95c8aa` outside refresh artifacts returns main's L-0513 paths (`.crew/verify.json` rule 22 rewritten in place at `:262-266` and its gate-runner rule appended at `:432-436`, `CLAUDE.md`, `scripts/gate-runner.py`, `scripts/_test/gate-runner.py`) and the three version files plus CHANGELOG; `git diff --name-only 0d159692 ec95c8aa` returns L-0516's own paths. A difflib re-map of every path-qualified `path:line` citation in the eight maps and two diagrams (history notes skipped), from each merge parent's anchor, found every one mapping onto itself from at least one parent except the version lines (changed in place) and nine `CHANGELOG.md:N` citations in `crew.md` from main's side, which L-0516's CHANGELOG entry above them moved by 35 (`:519-520` -> `:554-555`, `:679-680` -> `:714-715`, `:308` -> `:343`, `:676-677` -> `:711-712`, `:887-888` -> `:922-923`, `:898-899` -> `:933-934`, `:1114-1115` -> `:1149-1150`, `:1238` -> `:1273`, `:1134` -> `:1169`). `verification-harness.md`'s verify.json section now reads the merged tree (448 lines, 43 rules). No suite was executed for this note.

**Re-anchored `ec95c8aa` -> `5ffffbe3` on 2026-10-01 (L-0516 merges origin/main `ddcbf90d` - W-0115 #299, T-0040's shell-route sabotage mutations, crew 1.0.106 - with `git -c rerere.enabled=false` and re-bumps crew to 1.0.110, skipping 1.0.105 (L-0557), 1.0.107 (T-0504), 1.0.108 (L-0510) and 1.0.109 (T-0501)).** Conflicts were the three version files and CHANGELOG only. `git diff --name-only ec95c8aa 5ffffbe3` outside refresh artifacts returns W-0115's paths (`plugin/crew/tests/sabotage.py`, `plugin/crew/tests/sabotage_shell.py`, `.crew/verify.json`'s last rule gaining one path line) plus the version files and CHANGELOG. A difflib re-map of every path-qualified citation (history notes skipped) moved two `plugin/crew/tests/sabotage.py` citations in `crew.md` by +2 (`:3055` -> `:3057`, `:3056` -> `:3058`; W-0115 adds an import at `:86` and a comment line at `:3055`), the nine main-side `CHANGELOG.md` citations in `crew.md` by +15 for W-0115's entry, and `verification-harness.md`'s verify.json header to 449 lines; every other citation maps onto itself. No suite was executed for this note.

**Re-anchored `0c3508e9` -> `b1d8a4e8` on 2026-09-30 (L-0557: per-test XDG_CACHE_HOME for every pwsh the suites spawn, crew 1.0.89, obsidian-vault 0.4.16).** `git diff --name-only 0c3508e9 b1d8a4e8` returns, outside refresh artifacts, L-0557's test-only files (`plugin/crew/tests/conftest.py`, `plugin/crew/tests/crew_fixtures.py`, new `plugin/crew/tests/test_pwsh_cache_isolation.py`, both `test_flavour_guard.py` copies, the obsidian-vault `_test` suites, six `scripts/_test/*.sh`), `.crew/verify.json` (one new rule, appended after the Kimi rule), `plugin/crew/README.md` (one paragraph after the test-layer table), the harness reference's H4 table (one row), `CHANGELOG.md`, `plugin/crew/BUDGETS.md` and the version files. Body `path:line` citations into those files were moved by difflib from `0c3508e9` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local): 25 moved, in crew.md (CHANGELOG), obsidian-vault.md (its `_test` suites) and verification-harness.md (verify.json range unchanged). No hook or production script changed. No suite was executed for this note.

**Re-anchored `b1d8a4e8` -> `d9ccfd5a` on 2026-10-01 (L-0557 merges main 0c0275e8 (W-0116 #292, crew 1.0.89) and re-sets crew 1.0.95).** `git diff --name-only b1d8a4e8 d9ccfd5a` returns, outside refresh artifacts, W-0116's `plugin/crew/hooks/scripts/crew_refresh_check.py` (a final-path check in `_read_regular`'s no-dir_fd branch, hunks from :684) and `plugin/crew/tests/test_refresh_admission.py`, `CHANGELOG.md` (both sides' Unreleased entries kept) and the version files (crew 1.0.95). Body `path:line` citations into those files were moved by difflib from `b1d8a4e8` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local), each onto the same line text. No suite was executed for this note.

**Re-anchored `d9ccfd5a` -> `97ace923` on 2026-10-01 (L-0557 review round 1 fixes, crew 1.0.96).** `git diff --name-only d9ccfd5a 97ace923` returns, outside refresh artifacts, L-0557's test-only `plugin/crew/tests/conftest.py` (the per-test cache dir is now `tmp_path_factory.mktemp("xdg-cache")`), `plugin/crew/tests/crew_fixtures.py` (one comment), `plugin/crew/tests/test_pwsh_cache_isolation.py` (the static guard judges values and returned environments, reports unreadable suites), `CHANGELOG.md` (L-0557's entry, five lines longer) and the version files (crew 1.0.96: 1.0.95 is also claimed by L-0558, #293). Body `path:line` citations into those files were moved by difflib from `d9ccfd5a` (`/root/crew-tmp/l-0557/tools/remap.py`, machine-local): none in this map (all 10 are `CHANGELOG.md` in crew.md). No hook or production script changed. No suite was executed for this note.

**Re-anchored `97ace923` / `9580571e` -> `550c39cd` on 2026-10-01 (L-0557 merges main 6fe0e0db: T-0505 #296 crew 1.0.92, runner auto-start #294; crew stays 1.0.96).** `550c39cd` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were refresh artifacts, version files and CHANGELOG only. This side's notes were anchored `97ace923` and main's `9580571e`; `git diff --name-only 9580571e 6fe0e0db` outside the refresh artifacts returns only the 1.0.92 version files and CHANGELOG, so main's notes already describe every non-artifact change it brings, and this side's notes describe L-0557's. Body `path:line` citations were moved by difflib, each from the anchor of the side whose copy of this map carries the line (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 17 moved - 10 `CHANGELOG.md` in crew.md (T-0505's 1.0.92 entry now sits below L-0557's) and 7 `plugin/crew/CONFIG.md` in verification-harness.md (T-0505's CONFIG.md edit), every one an exact-text match. No suite was executed for this note.

**Re-anchored `550c39cd` -> `038d5d10` on 2026-10-01 (L-0557 merges main 44d3dbc6: T-0110 #297, crew 1.0.97; L-0557 re-sets crew 1.0.99 at `4fc11923`).** `038d5d10` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were version files, CHANGELOG and one generated rules file. `git diff --name-only 6fe0e0db 44d3dbc6` outside the refresh artifacts returns T-0110's `.github/workflows/pytest-crew.yml`, `AGENTS.md`, `plugin/crew/tests/crew_fixtures.py` (new helpers below L-0557's, auto-merged), seven crew test files, CHANGELOG and the 1.0.97 version files. T-0110 updated verification-harness.md's `pytest-crew.yml` sentence itself; the other files are cited by name only. Body `path:line` citations were moved by difflib (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 10 moved, all `CHANGELOG.md` in crew.md (T-0110's 1.0.97 entry now sits below L-0557's), every one an exact-text match. No suite was executed for this note.

**Re-anchored `038d5d10` / `44d3dbc6` -> `90186613` on 2026-10-01 (L-0557 merges main 52489039 at `327e6ec1`: T-0040 #290, crew 1.0.98; L-0557 re-sets crew 1.0.101 at `90186613`).** `327e6ec1` is a two-parent merge made with `git -c rerere.enabled=false merge origin/main`; its conflicts were refresh artifacts, version files, CHANGELOG, BUDGETS.md's count and `.crew/verify.json` (both sides appended one rule; both kept). Main's notes (anchor line `44d3dbc6`) were re-taken by T-0040 on its own merged tree `52489039`, so a line only in main's copy of a map is measured from `52489039`; a line in this side's copy is measured from `038d5d10`. Body `path:line` citations were moved by difflib (`/root/crew-tmp/l-0557/tools/remap2.py`, machine-local): 73 moved, all from this side's lines - `plugin/crew/README.md` (+11 lines from T-0040 above :743), `plugin/crew/CONFIG.md` (+11 from T-0040), `CHANGELOG.md` (T-0040's 1.0.98 entry, then this side's below it), `plugin/crew/tests/test_crew_config.py` and `plugin/crew/hooks/scripts/crew_config.py` (T-0040); every one an exact-text match, none on a changed line. T-0040's own claims about crew_shell.py, crew_status.py and the shell-route config are main's notes above and were not re-derived here. No suite was executed for this note.

**Re-anchored `89ebda03` (main) and `90186613` (L-0557) -> `773ce841` on 2026-10-01 (L-0557 merges main `05a679bf`, L-0558 #293, crew 1.0.102, at `2169bd11` with rerere disabled; L-0557 re-sets crew 1.0.105 at `773ce841`).** Both provenance histories are kept above, main's first. Body citations were re-checked by mapping each one from the tree its line came from (`89ebda03` for main's lines, `74dd1aa5` for L-0557's) to this tree with difflib: no citation moved. Citations into the version lines of `plugin/crew/.claude-plugin/plugin.json`, `plugin/PLUGINS.md` and `.claude-plugin/marketplace.json` keep their line numbers (the value changed in place). No suite was executed for this note.

**Re-anchored `0d159692` (main, L-0513 #301) and `773ce841` (L-0557) -> `a9608aa5` on 2026-10-01 (L-0557 merges main `cacf7ff0`, L-0513 #301: `scripts/gate-runner.py`, no plugin version; rerere disabled; crew stays 1.0.105).** Both provenance histories are kept, main's first. Where both sides had re-mapped the same citation, main's line was taken, and each citation was then mapped with difflib from the tree its line came from (`cacf7ff0` for main's lines, `95036b4c` for L-0557's) to this tree: no citation moved. No suite was executed for this note.

**Re-anchored `a9608aa5` -> `c43a9ce3` on 2026-10-01 (L-0557 merges main `ddcbf90d`, W-0115 #299, crew 1.0.106, at `0597e5c6` with rerere disabled, and re-sets crew 1.0.111 at `c43a9ce3`).** The merge touched no code map. `git diff --name-only a9608aa5 c43a9ce3` outside refresh artifacts is W-0115's `plugin/crew/tests/sabotage.py`, `sabotage_shell.py` and `.crew/verify.json` plus the version files and CHANGELOG; each citation into a changed file was mapped with difflib from `92448f1a` to this tree: no citation moved. No suite was executed for this note.

**Re-anchored `5ffffbe3` (main, L-0516 #298) and `c43a9ce3` (L-0557) -> `6053b65d` on 2026-10-01 (L-0557 merges main `2906dcbd`, L-0516 #298, crew 1.0.110, at `2f3fb34c` with rerere disabled, and re-sets crew 1.0.114 at `6053b65d`).** Both provenance histories are kept, main's first, and main's body citations were taken where both sides had re-mapped the same one. Each citation into a changed file was then mapped with difflib from the tree its line came from (`2906dcbd` for main's lines, `a54ff87b` for L-0557's) to this tree: no body citation moved; the `.crew/verify.json:433-439` range in L-0516's provenance note was kept, because it describes that tree. No suite was executed for this note.

**Re-anchored `6053b65d` -> `f5cab1f9` on 2026-10-01 (T-0503 merges origin/main `ffd11270`, L-0557 #300, crew 1.0.114, at `f5cab1f9` with rerere disabled; bitbucket 1.2.3).** The merge took main's side of every code map. `git diff --name-only ffd11270 f5cab1f9` is T-0503's own change only: `.claude-plugin/marketplace.json` (bitbucket version), `CHANGELOG.md` (its entry, 33 lines at the top), the `bitbucket` catalog row in `README.md` and `skills/README.md` (edited in place, no line count changed), `docs/handoff/cloud/T-0503.md`, and `skills/bitbucket/` (`SKILL.md`, `references/api.md`, `scripts/_test/merge_gate.sh`). Every citation into those files was compared by script against `ffd11270` (158 checked across the eight maps); no other cited line moved. Re-anchor only, under the refresh-artifact standing rule (owner 2026-09-28); no suite was executed for this note.

**Re-anchored `f5cab1f9` -> `b4f04e23` on 2026-10-02 (L-0578 merges origin/main `8d84786d`, W-0117 #302, crew 1.0.115, at `b4f04e23` with rerere disabled; crew 1.0.119).** L-0578's own change is `review_metrics.py` (new), `review_run.py`, `review_patch.py`, `commands/review.md`, the README, BUDGETS.md, external-tool-formats.md, `.crew/verify.json` rule 38, its tests and sabotage entries, and the version files and CHANGELOG. Every full `path:line` citation into a changed file was compared by script (difflib) against the old anchor: none moved; the only citations whose line text changed are the version and count lines (`plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:224`, `plugin/PLUGINS.md:14`, `plugin/crew/BUDGETS.md:10-11`), which still sit on the lines they cite. No suite was executed for this note.

**Re-anchored `6053b65d` -> `3a33161c` on 2026-10-01 (L-0555 PR 1: the diagnostic CI verify-gate receipt - `plugin/crew/hooks/scripts/ci_receipt.py`, `.github/workflows/verify-gate.yml` (mmdc pinned at 12.0.0), `plugin/crew/tests/test_ci_receipt.py` - merging origin/main `ffd11270` (L-0557 #300, crew 1.0.114) at `751d6d2a` with rerere disabled, crew 1.0.116, skipping 1.0.115 claimed by another lane).** Refresh-artifact conflicts were resolved by taking main's side and redoing this pass. `git diff --name-only 6053b65d 3a33161c` outside refresh artifacts returns L-0555's paths only: the three new files, `.crew/verify.json` (one rule appended last, at `.crew/verify.json:454`), `CHANGELOG.md` (+16 lines at the top), `plugin/crew/README.md` (+23 lines in section 17), `scripts/gate-runner.py` (+2 lines in EXCLUDED_WORKFLOWS), `plugin/crew/BUDGETS.md` (count only) and the version files. A difflib re-map of every path-qualified citation into those files (history notes skipped) moved nine `CHANGELOG.md` citations in `crew.md` by +16 and six `plugin/crew/README.md` citations in `repo-docs.md` by +23; every other citation maps onto itself. No suite was executed for this note.

**Re-anchored `3a33161c` -> `79c116b4` on 2026-10-01 (L-0555 gate fix: `ci_receipt.py` asks `review_gate.gate_state` for NO_GATE instead of reading `.crew/config.json` itself; `plugin/crew/BUDGETS.md` count corrected; crew 1.0.116 re-set at `79c116b4`).** `git diff --name-only 3a33161c 79c116b4` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py` and `plugin/crew/BUDGETS.md` (the count line only, changed in place, so the `plugin/crew/BUDGETS.md:10` and `:11` citations keep their lines; the version files net to no change). No note cites `ci_receipt.py` at a line, so every citation maps onto itself. No suite was executed for this note.

**Re-anchored `79c116b4` -> `8b21ecc3` on 2026-10-01 (L-0555 pre-review fix: `ci_receipt.py` resolves gh with shutil.which and folds the check reason onto one line; crew 1.0.116 re-set).** `git diff --name-only 79c116b4 8b21ecc3` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py` and `plugin/crew/tests/test_ci_receipt.py` (the version files net to no change). No note cites either at a line, so every citation maps onto itself. No suite was executed for this note.

**Re-anchored `8b21ecc3` -> `1e2762a0` on 2026-10-02 (L-0555 review round 1 fixes: `ci_receipt.py` requires the receipt's gate_impl to match HEAD's and its docstring says diagnostic; the verify.json rule is priced 10s from measured runs; crew 1.0.116 re-set).** `git diff --name-only 8b21ecc3 1e2762a0` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py`, `plugin/crew/tests/test_ci_receipt.py` and `.crew/verify.json` (the last rule's line edited in place, no line moved); the version files net to no change. Every citation maps onto itself. No suite was executed for this note.

**Re-anchored `1e2762a0` -> `b10e3895` on 2026-10-02 (L-0555 review round 2 fixes: `ci_receipt.py` treats an unreadable stand-down as UNKNOWN, re-reads the stand-down at the last look, and anchors the origin host to github.com; crew 1.0.116 re-set).** `git diff --name-only 1e2762a0 b10e3895` outside refresh artifacts returns `plugin/crew/hooks/scripts/ci_receipt.py` and `plugin/crew/tests/test_ci_receipt.py`; the version files net to no change. No code map cites a line of either file, so every citation maps onto itself. No suite was executed for this note.

**Re-anchored `b4f04e23` -> `fa63852d` on 2026-10-02 (L-0555 merges origin/main `dd95135a`, L-0578 #304, crew 1.0.119, at `fa63852d` with rerere disabled; crew 1.0.120).** The merge took main's anchor and INDEX rows and kept both lanes' re-anchor notes. L-0555's own change against main is `ci_receipt.py`, `test_ci_receipt.py`, `.github/workflows/verify-gate.yml`, `scripts/gate-runner.py`, one `.crew/verify.json` rule (line 454 edited in place, 455 appended), `plugin/crew/README.md` (+23 lines after `:2167`), `CHANGELOG.md` (+17 lines at the top) and the version and count lines. Citations moved by difflib: `CHANGELOG.md` +17 in `crew.md`'s current-citation lines, `plugin/crew/README.md` +23 past `:2167` in `repo-docs.md` (nine). No suite was executed for this note.
