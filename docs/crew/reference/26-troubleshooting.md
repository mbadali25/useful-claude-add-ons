<!-- Moved verbatim from plugin/crew/README.md (26. Troubleshooting) by L-0726; the README keeps an index entry. -->

## 26. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Commands do not appear | Plugin not installed, or needs `/reload-plugins`. Check `/help`. |
| Agents ignore `CLAUDE.md` rules | The built-in Explore and Plan agents skip `CLAUDE.md` by design. Restate critical constraints in the delegation prompt. |
| Smoke gate never fires | `_verify/smoke.sh` has no checks, or `verifyGate` is `false` in `.crew/config.json`. |
| Gate blocks on a file it edited | A `run` command writes to the tree - almost always `terraform-docs .` without `--output-check`. Use the checking form. |
| Promotion says qa passed but prod broke | Compare the shas in `.work/PROMOTIONS.md`. A rebuild between environments means qa proved nothing about what prod got. |
| Review always returns CLEAN | Empty diff, wrong base branch, or `codex` silently missing. Check which reviewer the command reported. |
| Jira connection fails | Using the retired `/v1/sse` endpoint, or the server was never approved via `/mcp`. |
| Context fills fast anyway | `CLAUDE.md` has grown. Every line is multiplied across every delegation. Cut it back to a routing table. |
| Gate says "unmapped changes" | Working as intended. Add a rule to `.crew/verify.json` for that path, or mark it deliberately unchecked. |
| Visual tests fail after an unrelated change | Baselines are stale or a dynamic region is unmasked. Regenerate deliberately with `--update-snapshots`, never automatically. |
| A secret read is blocked | Capture it into an env var rather than printing it: `export X=$(aws secretsmanager get-secret-value ... --output text)`. |
| Teams webhook returns 404 or 410 | An old Office 365 Connector URL. Those were disabled in May 2026 — recreate it via Workflows. |
| Telegram `getUpdates` returns nothing | You have not messaged the bot yet. A bot cannot open the conversation. |
| Notifications stopped with no error | The Teams Workflow runs under its creator's account. Check whether they left or lost the licence. |
| Runbook commands fail when needed | It was never verified. `--verify` it in dev; check `last verified`. |
| crew skills stop triggering | A broadly-scoped skill is competing. `find-skills` is the first to test — see its BUNDLING-NOTE.md. |
| README keeps reverting | You edited inside `BEGIN_TF_DOCS`. Edit the `/** */` header in `main.tf`, `footer.md`, or the variable descriptions instead. |
| `tflint` fails with a plugin error | Run `tflint --init` once per machine and in CI. |
| terraform-docs template error | Needs >= 0.16.0 for `footer-from` and `.Module`. |
| A test exists but never runs | No rule invokes it. Run `/crew:verify --sync`. |
| Migration passed, production broke | The rule covered apply but not the round trip. Add all three DB checks. |
| `_verify` checks never run | Nothing maps to them. Add a rule in `.crew/verify.json` naming the directory. |
| Handoff prompt fires every turn | The marker file is not being cleared. Check that the `SessionStart` hook is registered. |
| Warning arrives too late | `budgetTokens` is set too high for the real window, or `reserveTokens` is larger than the headroom you actually want. Calibrate against `/context`. |
| Warning still fires early on a 1M model | The `Threshold:` line in the warning says which rule fired. `warnAt 80%` on a 1M window is 800k; set `context.reserveTokens` (default 100000) to the headroom you want kept and the later rule wins. |
| Gates stopped blocking and nobody said why | An emergency lane is open - the session brief names it at every session start. `/crew:emergency status`, then `end`. It also expires on its own; see 24. |
| An incident will not stand the gates down | `emergency.standDown` is `false` in `.crew/config.json`, or the incident has expired. Both are reported by `/crew:emergency status`. |
| Warning fires far too early on a 1M model | `.crew/config.json` still carries `"budgetTokens": 200000` from an older `/crew:init`. Set it to `null`; the warning's `Budget source:` line says `configured` when this is the cause. |
| Old handoff keeps reappearing | It was never deleted. Remove `.work/HANDOFF.md` when the work is done, rather than waiting on the staleness check — it only fires on clear/compact/resume/fork, and only once age or reality drift gives it a reason to distrust the note. |
| Handoff vanished but the ticket isn't done | Check `.crew/handoffs/` — a note the staleness check judged stale is archived there, timestamped, never deleted. If the judgment was wrong (age or commit thresholds too tight for this repo's pace), move it back and loosen `context.staleHandoff` in `.crew/config.json`. |
| `mmdc` fails in a container | Headless Chromium needs `--no-sandbox`. The render script passes it; a direct `mmdc` call will not, and as root it fails with "Running as root without --no-sandbox is not supported". In `_verify/`, use crew-setup's ready case `templates/cases/diagrams-render.sh`, which passes it (T-0502). |
| Rendered PNG unreadable in Teams | Transparent background on dark mode. Render with `-b white` for chat and print. |
| Azure MCP tools fail oddly | You are not authenticated. `az login` before starting the server. |
| MCP snippet copied from VS Code does nothing | VS Code uses the `servers` key; Claude Code uses `mcpServers`. |
| Plan command hangs | The Gemini CLI dropped into interactive mode. Confirm the non-interactive flag with `gemini --help`. |
| Provider call fails with model-not-found | Free catalogs churn. Update `secondOpinion.model` rather than debugging the request. |
| Survey returns generic advice | Explorer could not anchor its findings. Give it a narrower area and make sure the code map exists. |
| `bad interpreter: ...^M` | CRLF line endings. Add `.gitattributes` with `* text=auto eol=lf` and `git add --renormalize .`. |
| Tests connect fine on Windows, time out in WSL | WSL2 — the service is on the Windows host, not `localhost`. Use the gateway IP from `.crew/config.json`. |
| Smoke suite takes minutes instead of seconds | Repo is on `/mnt/c`. Re-clone inside WSL. |
| A hook refuses with `crew-hook: ... failing closed (armed repo)` | The launcher or dispatcher could not reach a decision (a python error, a hook script missing or past its timeout, a stdin that never closed) in a repo crew governs, so `PreToolUse`, `UserPromptSubmit` and `Stop` refuse rather than let the call through unjudged. The line names the cause. In a repo with no `.crew/` config and no `~/.claude/crew/config.json` the same fault is only a note on stderr. |
| On Windows a guard reads git differently from your shell | crew runs the tool `shutil.which` finds (PATHEXT order, the same as bash and pwsh), never a bare name. `where git` (cmd) or `Get-Command git -All` (pwsh) shows the order; the first hit is the git crew judges. A failing `git.cmd` shim first on PATH now makes guards say "could not tell". |
| No hook fires at all on Windows, or every call is refused naming Git for Windows | The dispatcher runs the `.sh` hooks through a strictly resolved Git Bash (`bin/bash.exe` from `git --exec-path` or the default install) and never a PATH `bash`. Install Git for Windows; with python missing an armed repo is refused on `PreToolUse`, `UserPromptSubmit` and `Stop` too. |
| On Windows a hook fails with `can't open file 'D:\tmp\...\crew_*.py'` | `MSYS_NO_PATHCONV` is set (even empty) in the environment Git Bash starts from, so a POSIX script path reaches `python.exe` unconverted. Non-harness `.sh` hooks now pass their script path and their path arguments (`--root "$PWD"`, `sys.path` and config data paths) through `crew_native_path` (`cygpath -m`) and no longer depend on it, except the PreCompact `crew_resume.py` record in `handoff-write.sh`; for that and the review-harness hooks, unset it (`env -u MSYS_NO_PATHCONV claude`). |
| Code map contradicts the code | The map is stale. Code wins. Re-run `/crew:onboard --refresh <area>` and delete what cannot be verified. |
