# L-0667: /crew:graph - one command for graph status, the sanctioned refresh and queries

Split from T-0067 on 2026-10-04. Status: direction, recommended option taken (owner not available). Risk: med.

## Ask
Owner, 2026-09-27: "isn't there a crew command for graphify". There is a `crew-graph` skill and no command, so anything that wants the graph refreshed can only name a raw tool line, and the raw line it names is not always the one the repo sanctions.

## Measured (origin/main `155fe6d8`, crew 1.0.322)
- `plugin/crew/commands/` holds 36 commands, none for the graph. `plugin/crew/skills/crew-graph/SKILL.md:41-45` documents `graphify . --no-viz --code-only` as "the default, always".
- The refresh check already picks per repo: `graphify update .` when `GRAPH_REPORT.md` is tracked beside the graph, else the code-only build (`plugin/crew/hooks/scripts/crew_refresh_check.py:1226-1227`). The skill and the check disagree for a repo that tracks the pair, which this repo does.
- Nothing verifies the pair after a refresh. This repo's CLAUDE.md asks for it by hand: compare the report's `## Summary` with the graph's `nodes` and `links`. The report line is `- 23840 nodes · 50994 edges · ...` (`graphify-out/GRAPH_REPORT.md:9`); the JSON key is `links`.
- T-0064 (approved; draft PR open) adds `crew_graph_ignore.py` with `coverage(root)` answering `covered`, `uncovered` or `unknown`, and makes the refresh check refuse to name a build while a denylisted file is uncovered.
- A sabotage mutation anchors the line that picks the command (`plugin/crew/tests/sabotage_refresh.py:151-154`), so that line must stay byte-identical in a feature PR.

## Options
1. **A `/crew:graph` command over a small script, after T-0064 (recommended).** `--status` (read-only), `--refresh` (denylist check, the sanctioned command, pair verification, no commit), `--query` (the skill's query, with a stale warning). The refresh check's graph hint names `/crew:graph --refresh` and keeps the raw command in a second field.
2. **Command prose only, no script.** The pair verification and the refusal order would live in prose a model follows; the parent ticket's rule is that mechanical checks are code.
3. **Ship before T-0064 with a refusal that names T-0064.** The original direction's shim. Dropped: T-0064 has a PR open, and a shim is code written to be deleted.

## Recommendation
Option 1.

## Open questions for the owner (recommendation applies)
- `/crew:graph --refresh` never commits; the phase that called it commits, like every other refresh (recommended), or it commits the pair itself.
- The refresh hint names `/crew:graph --refresh` (recommended), or keeps naming the raw command and the command is only an entry point for people.

## Depends on
T-0064 (must merge first). Independent of T-0067 and L-0666, except that all three edit `commands/autopilot.md`.
