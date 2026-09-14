# CLAUDE.md

A Claude Code **marketplace**. Each directory under `skills/` is an installable plugin holding one
`SKILL.md`; each under `plugin/` is a full plugin that may also bundle subagents, commands and
hooks. Both register in `.claude-plugin/marketplace.json` — the root's is the **only** one here.

## Commands - build, test, verify, regression, promote

No build. `python3 scripts/check-marketplace.py` is the gate: every registration rule, both install
scripts being a matched pair, hook quoting and exit codes, and version drift. Run it before pushing.
Per-path commands and promotion steps live in `.crew/verify.json` — that file is the mechanism, this
one is the judgment. Do not restate its commands here.

## Where things are - entrypoints, logic, DO NOT TOUCH

- `scripts/install-prerequisites.{sh,ps1}` — a matched pair. Change one, change the other.
- `scripts/_test/`, `plugin/crew/hooks/scripts/_test/` — the suites. Each builds throwaway fixtures
  and must never touch real config or install anything.
- `graphify-out/`, `node_modules/` — generated. Do not hand-edit.

## Scope discipline - fix the ticket, not what you notice nearby

Registering an entry means updating **every** place in the same commit — marketplace entry, catalog
row, `plugin/PLUGINS.md` for plugins, and both install scripts in the same order with the same text.
A partial registration is worse than none: the checker fails and nobody can tell which half was
intended. Renaming or removing means the same places, in reverse.

**A number this repo states about itself gets a marker, or it is not checked.** Write
`<!-- claim: skills-count -->` or `<!-- claim: plugin-version:<name> -->` beside it and
`check_self_claims` in `scripts/check-marketplace.py` verifies it against `marketplace.json` or that
plugin's `plugin.json`. The marker binds to the first matching line within 12, so a claim inside a
fenced code block is marked from the line above the fence. Unmarked numbers are deliberately not
checked: `17 skills` is true of crew's bundle and false of the marketplace, and a checker that
guesses which is which fails correct lines. That silence is asserted by
`scripts/_test/self-claims.py`, so do not "improve" the check into inferring claims.

## Stop and ask - the conditions that should halt work

- **Content change with no `version` bump.** `claude plugin update` compares the *declared version*,
  not contents. Ship without the bump and every machine that already installed it keeps the old copy
  forever, reporting "already at the latest version". Nothing in the repo looks wrong; the bug
  exists only on other people's machines. A plugin with its own `plugin.json` bumps in both.
- **Adding a hook.** It runs whether or not Claude agrees with it, so a plugin registering one
  **defaults to OFF in the menu**. One that can *block* needs a committed regression suite with
  must-block and must-allow cases, sabotage-tested: reintroduce a bug it should catch and confirm
  the suite goes red. Two of `crew`'s guard bugs shipped past review and were caught only by that.
- **A `marketplace.json` inside a plugin directory** (makes it look like a second marketplace), or
  **deleting or renaming a registered entry.** Ask first.

## Promotion: development -> qa -> production

Nothing is deployed; "production" means merged to `main` and installable. Two steps no script
enforces: `scripts/_test/drift-detection.sh` drives the real `claude` CLI so CI cannot run it — run
it by hand before pushing a change to the plugin update path; and the README's install URLs are
**pinned to a commit SHA** — after merging a change to either install script, `git rev-parse HEAD`
and re-pin both.

## Reporting - errors verbatim, say what you did NOT verify

Quote failures exactly; never summarise a stack trace. Name which suites ran and which did not.
`drift-detection.sh` is skipped by default — say so rather than implying the gate is green.

## Memory - where the code map and runbooks live

Two maps, both **in this repo**, both tracked. No Obsidian vault — the graph used to be exported to
one, which meant the map lived on one machine and reached nobody who cloned.

- **`.crew/codemap/`** — the prose map: one file per subsystem, every claim marked DERIVED (with a
  `path:line` to re-check) or JUDGEMENT, each carrying an `anchor:` commit. `INDEX.md` is the table
  of contents. Refresh with `/crew:onboard --refresh <subsystem>`. Anchor length does not matter:
  `_ANCHOR_RE` accepts 7-40 and `plugin/crew/hooks/scripts/crew_freshness.py:430` compares
  `sha[:7] == head[:7]`, truncating **both** sides, so 8 and 40-char anchors match
  exactly as well as 7. The same comparison appears again at `:513` for diagrams — grep the
  expression rather than trusting either number, both moved when `crew_state.py` was split, and
  moved file as well as line on 2026-09-14 when the anchor-freshness slice left it for
  `crew_freshness.py`. Grepping `[:7] == head[:7]` returns a **third** hit, `:333`: that is
  `_read_graph`'s fast path against graphify's `built_at_commit`, the same comparison on a third
  artefact, and it is not the codemap one.
  (This line previously warned that an 8-char anchor "parses fine and then never matches". It was
  wrong, and wrong in the expensive direction — it sends you rewriting correct anchors and
  distrusting working ones. Corrected 2026-09-05 by reading the comparison.)
- **`graphify-out/graph.json`** — the mechanical graph. Refresh with `graphify update .`; a
  post-commit hook does it automatically. **`graphify . --no-viz --code-only` is not
  interchangeable with either, and the difference lands in a tracked file.**

  `git ls-files graphify-out/` returns **two** tracked files, `graph.json` and `GRAPH_REPORT.md`.
  The hook rebuilds both — `.git/hooks/post-commit:178` calls `graphify.watch._rebuild_code`, and
  the log it writes says `graph.json, graph.html and GRAPH_REPORT.md updated`. The
  `--no-viz --code-only` form does not: `--no-viz` writes the graph and skips the report, so
  running that by hand leaves the two tracked files describing different builds of the same
  repository, with
  nothing in either one saying so. It happened twice on 2026-09-12, in this repo, to this agent.
  Follow it with `graphify cluster-only .`, which regenerates the report from the graph that was
  actually built, and read the counts out of both before committing — the report states them on
  its `## Summary` line and `graph.json` carries them as `nodes` and `links` (**`links`, not
  `edges`**; the report prints the word "edges" for the same number).
  Those two hook citations are **machine-local**: `.git/` is not tracked, so unlike every other
  anchor in this file they cannot be re-checked with `git diff` and are absent entirely on a
  clone that never ran `graphify hook install`.

  The rebuild runs in the **background, and a commit is not the only thing that starts one.** Two
  hooks launch it: `.git/hooks/post-commit:163` and `.git/hooks/post-checkout:165`, which prints
  "Branch switched - launching background rebuild". Both name the same log,
  `~/.cache/graphify-rebuild.log`. So `git checkout -b`, `git pull` and `git commit` each start a
  rebuild that keeps running while you do the next thing.

  **This will overwrite a build you are in the middle of measuring.** It did, here, on 2026-09-12:
  a `git checkout -b` launched a rebuild, a hand-run `graphify . --no-viz --code-only` wrote 9455
  nodes, and the background job then replaced both files with its own 9570-node build — after which
  a node-set diff of "the build I just made" against `HEAD` compared the hook's output with itself
  and reported zero difference. That zero was an artifact of the clobber, not a result. Wait for
  the log to stop growing before you build, and read the files before anything can switch a branch
  under you.

  **The committed artifacts are not built by the command above, and the counts prove it.** Measured
  at `57604a62` on a quiescent tree: `graphify . --no-viz --code-only` gives 9455 nodes / 14414
  links and leaves `GRAPH_REPORT.md` untouched, while `graphify update .` gives 9570 / 14476 and
  writes both files consistently — the same figures the hooks produce, and the ones committed here.

  That gap is most likely `--code-only` doing exactly what its name says rather than a defect, so
  do not read it as one. **What the 115 extra nodes are has not been measured** (the diff that would
  have said was the one the clobber invalidated, above). What *is* settled is the practical part: a
  hand refresh with `--no-viz --code-only` does not reproduce what is in git, so expect the
  next hook run to revert it.

  **Decided 2026-09-12: `graphify update .` owns the tracked pair in this repo.** It is the
  command that writes both files consistently, and `graphify-out/GRAPH_REPORT.md:15` — a line
  graphify generates itself — already instructs its own reader to run it ("Run `graphify update .`
  after code changes (no API cost)"). So the committed artifact and this file now agree.

  **The user's global `~/.claude/CLAUDE.md` names `graphify . --no-viz --code-only` instead, and
  that difference is deliberate.** It is not a standing instruction being overridden by accident:
  that same global file carries a `## Per-project` clause reading "Project `CLAUDE.md` overrides",
  so naming a different command here is the mechanism that clause provides, used on purpose. **Do
  not "reconcile" the two files by editing either to match the other.** A reader who finds them
  disagreeing and has not seen that clause will helpfully make them agree, the hand-refresh path
  goes back to writing only one of the two tracked files, and the pair goes inconsistent again —
  which is exactly how this started, twice, in one day.

An `anchor:` behind HEAD means *re-check the claims*, not that they are wrong. Do the per-path check
first — `git diff --name-only <anchor>..HEAD -- <paths the map documents>` — because a repo-wide
version bump moves every anchor without invalidating a word. Empty output means current despite the
lag. The same comparison for `graphify-out/` and `docs/diagrams/` can never come out current: they
are tracked, so committing one advances HEAD past the sha it records.

Decisions in `docs/adr/`; the rest of `.crew/` is machine-local and stays ignored.

## Landmines - every one of these has already shipped broken

- **`pwsh` is not on Git Bash's PATH here.** Name it absolutely. A bare `pwsh` fails as "command
  not found" and the gate reports that as a *failed check*, not a missing tool.
- **Git Bash ships without `python3`.** Resolve `python3`/`python`/`py` and fail loudly on stderr
  rather than suppressing the error and exiting 0.
- **A bare hook `command` goes to Git Bash on Windows**, not PowerShell — set `shell: "powershell"`
  and register each event once per flavour. `crew` shipped a release where the guard stood down on
  Windows instead, so it blocked nothing there.
- **Branch on the tool, not the OS.** A `Bash` call is bash syntax even on Windows; PowerShell rules
  get it wrong both ways. A `.ps1` that `hooks.json` never references is dead code.
- **Nothing may bypass `pick_fit` / `Format-PickerLine`.** Clipping is degradation; a line that
  *wraps* throws off the cursor-up redraw count and smears the menu over what was above it.
- **Both install scripts are idempotent** — a new step needs a detection branch reporting "already
  installed".
- **`open(p, "w")` truncates at open time, before the payload exists.** So a
  write whose *argument expression* raises leaves a zero-byte file where the
  original was. It happened here: a script ran
  `open(scan, "w").write(parts[0] + ... + parts[1] + ...)`, `parts[1]` raised
  `IndexError`, and `plugin/gizmoduck/commands/scan.md` was already empty. The
  second-order failure is the expensive one — the next script read the emptied
  file as its baseline and reported "restored byte-identical: True" against
  nothing, so the *check* said the file was fine. Only the test suite caught
  it, with `commands/scan.md invokes gizmoduck.py tickets nowhere`. Compute the
  full text into a variable, then open. `pathlib.write_text(expr)` is not this
  trap — `expr` is evaluated before the call — but the `with open(...) as fh:`
  form is, and that is the form in this repo. Repair with `git checkout --`.

  Measured across every tracked `*.py`, by AST rather than by grep — a write
  inside a truncating `open` whose first argument is neither a bare name nor a
  constant. Eight carry that shape. Three are test fixtures. One
  (`plugin/localgpu/mcp/store.py:646`) writes a temp file that is then
  `os.replace`d, so a raising argument costs the temp and nothing else — that
  is the immune construction, and it is one file here, not the general case.
  `plugin/localgpu/cli/localgpu_cli.py` was reordered in this change because
  its target is a repo's whole `.mcp.json`; nothing reaching that line can
  raise today, and the ordering is what keeps that a fact about today.
  Three remain, unfixed and each in a different marketplace entry that would
  need its own bump: `plugin/gizmoduck/scripts/gizmoduck.py:90` (a `str.join`
  over a list of `str` — no reachable raise),
  `skills/aws-opensearch/scripts/opensearch_client.py:405` (`resp.text`, already
  materialised on the line above), and
  `skills/intune-graph/scripts/export_report.py:90` — which is the live one:
  `dst.write(src.read())` on a zip member, and `src.read()` raises `BadZipFile`
  on a corrupt archive, leaving a zero-byte extract behind. Re-run the scan
  rather than trusting this count; it is a fact about one commit.

- **`pathlib.write_text` converts a `.sh` to CRLF on Windows** — it is text mode, so every `\n`
  becomes `\r\n` and the script dies on its shebang as `bad interpreter: ...^M`. Pass
  `newline="\n"`. `.gitattributes`' `*.sh text eol=lf` does *not* save you: it governs what git
  stores and what a checkout produces, and the damage lands after checkout, in the working tree
  bash actually executes. Worse, the obvious check lies — with `core.autocrlf=true`,
  `git show <rev>:<path>` renders CRLF whatever the blob holds, so grepping its output reports the
  same count for a clean file and a broken one. Measure the worktree with `od -c` or `file`(1).
  Repair with `git checkout -- <path>`, then confirm the same way.

Skills follow `Skill-Authoring-Standard.md`; changes follow `Skill-Pipeline.md`.

## Lessons - each one cost real time here, more than once

Recovered 2026-09-05. These existed only as an uncommitted local edit that a CLAUDE.md rewrite
overwrote, so they survived in nothing tracked and were then cited twice, at two other sessions, as
this file's policy — while living in no commit at all. Every one below carries the evidence that
earned it, precisely so nobody has to take it on faith the way those citations asked people to.

It took repeated review to stop overclaiming, which is the most useful thing in it. The first draft
said a guard is "usually" wrong again after a fix — a frequency drawn from one guard — and that an
exit-code-only check "would have passed" a run that exited 1. The second draft replaced "usually"
with "the normal outcome", which is the same claim reworded rather than narrowed, and asserted that
an exit code "never" tells you what failed, a universal that is false wherever a tool encodes
categories in its status. The two failed differently, and the difference is the useful part: the
first fix reworded the claim without shrinking it, while the second swapped one unsupported claim
for a different unsupported claim. Neither moved toward the evidence. If a section arguing that
claims outrun their evidence did exactly that twice, assume yours does too, and get a reader who
did not write it.

- **The recurring bug is an unknown collapsing into the safe-looking value.** Not a wrong answer —
  a *missing* answer wearing the label of a check that happened. `crew_config.py --models` derives
  "author family" from config describing the NEXT run, and on a Claude-authored diff barred Codex,
  the only independent reviewer, while clearing Claude. It declares that uncertainty once in prose
  and then prints `BARRED` / `ELIGIBLE` with no caveat on any row drawn from it. Where a probe can
  fail, "could not tell" has to be its own value that survives into every line derived from it, or
  the guard fails open while looking like it checked.

- **Re-review the fix to a guard as hard as the guard.** The measured case is one guard over one
  day: seven consecutive review rounds on `vault_guard.py`, every fix right about the case it aimed
  at and one rung short of its neighbour — frontmatter, then ASCII, then the three config defaults,
  then the comment justifying the interpreter stand-down, then a count corrected in one of the two
  places that stated it. Seven for seven, no exception — on one guard, over one day. No rate across
  this repo has been measured, and none is claimed. The heuristic that follows is cheap regardless:
  when a guard fix lands, check the neighbouring case before closing it, because in the one run
  anyone has measured that is where the next defect was, every time.

- **Put the check where the evidence is dropped.** `read_metrics` averaged BLOCK+FIX per *row* and
  returned that row count under the key `tickets`, so one ticket reviewed twice read as two.
  `cells[1]` — the ticket column, filled in by every row — was never referenced. A correction
  written in prose beneath the table fixed nothing, because the parser never reads prose.

  This entry previously said the miscount made the health signal recommend "cut ticket scope" on a
  90-line docs diff. That is backwards, and worth keeping visible rather than quietly deleting: the
  extra row is a **divisor**, so the bug *understates* the rate. On the real file that exposed it,
  three rows carrying nine findings across two tickets read as 9/3 = 3.0 where the truth is
  9/2 = 4.5 — the direction that hides a ticket-scope problem rather than inventing one. A wrong
  claim about which way a metric errs sends the next reader hunting the opposite bug. Fixed in
  `crew_state.py`'s `read_metrics`, which now groups by `cells[1]`; a blank cell gets a per-row
  tuple key, so two unknown identities can never pool into one known ticket.

- **A failing gate names the failure, not the cause.** `render.sh` exited 1 and printed six `FAIL`
  lines — correctly, so an exit-code check would have caught it. The trap was the next inference:
  the cause was a `/tmp` path a Windows `mmdc` cannot open, not broken Mermaid, and the same three
  sources rendered cleanly when invoked directly. Acting on that log alone would have sent someone
  editing correct diagrams. Some tools do encode categories in the status — `pylint` uses a
  bitmask — so read the status before assuming it is a bare pass/fail; here it was bare, and the
  distinction that decided what to fix ("the input is bad" versus "the tool could not run") was in
  neither the status nor the log. `render.sh` also printed a summary line and created
  its output directory while producing nothing, so check the artifact, not the summary.

  Narrowed since: `render.sh` fails this way only when `MSYS_NO_PATHCONV=1` is set in the calling
  environment, which is what stopped Git Bash rewriting the puppeteer config path into a form the
  native `mmdc` could open. Without that variable the same command renders. So the reproduction
  requires the variable, and a report of "render.sh is broken" that does not name the environment
  it ran in is not yet a bug report. `render.sh` now converts that path with `cygpath` itself and
  carries a regression check for it in
  `plugin/crew/skills/crew-diagrams/scripts/_test/render.sh` (79 lines; the
  `MSYS_NO_PATHCONV=1` case is `:74`, asserting the render produces a non-empty
  SVG with that variable set). Until 2026-09-12 this line named a repo-root
  path under `scripts/` that does not exist and never has - written out here it
  would be indistinguishable, to any checker walking these citations, from a
  citation that broke. The claim was true and the path was wrong, which is the
  more expensive shape: a reader who goes looking finds nothing and concludes
  the regression check was never written, so the next person to hit the bug
  re-derives it from scratch.

- **Run the states; do not reason about them.** A guard suite reported 24 passed / 33 failed, and
  the cause was `MSYS_NO_PATHCONV=1` in the *runner's* environment mangling `/c/repos/...` into
  `C:\c\repos\...`. Settled tree, same commit: 65/0. Check what you changed about the measurement
  before reporting a regression.

- **Attach the ref and the layer to every measurement.** "The suite passes 65/0 on main" was false
  — the shared worktree was on another session's branch and `main` ran 57. Two agents disagreed
  about `dev.provider` for an hour because one read `.crew/config.json` and the other
  `~/.claude/crew/config.json`, and neither named which. A number without its ref can only be
  believed, not checked.

- **Check `ListAgents` before assuming a diff, a branch, or a dirty tree is yours.** Three sessions
  worked this repo in one night; the checkout was switched under a running measurement, and commits
  appeared on `main` from elsewhere mid-task.

- **Write anchors repo-relative.** Write `plugin/localgpu/mcp/config.py:99`, never a bare
  `config.py` with a line number after it. The bare form resolves by eye and cannot be pasted into
  `git diff --name-only <anchor>..HEAD -- <paths>`, which is the entire re-verification mechanism.
  60 were in that shape — 30 in the codemap, 30 more inside the diagrams. The bad form is described
  rather than shown here on purpose: a checker walking these citations cannot tell a counter-example
  from a broken one, and would report this section as containing an unresolvable anchor forever.

- **A self-referential count changes itself.** Recording "87 anchors" in a note took the total to
  88, and the commit correcting the figure took it to 89. State the invariant and how to
  re-measure instead; a number wrong by one is worse than no number, because it looks measured.
