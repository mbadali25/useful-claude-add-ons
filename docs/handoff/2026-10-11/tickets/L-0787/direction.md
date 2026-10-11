# L-0787: L-0777 review round 4 follow-ups

Source ticket: L-0777, round 4 (Codex gpt-6-sol, final, owner grant past the 3-round cap), bundle 941c8b78a4c0d93111a627fe60c858ea7da7f6878c3c4ede6578b15fa5bb84e3, head ee19528bf.
Accepted as edge-case-only (0 BLOCK) by the owner rule; every line below verbatim:

```
FIX|plugin/crew/hooks/scripts/crew_kimi_agent.py:218|An unresolved linked-worktree config source is treated as an absent pin, so a Kimi-pinned role reports `not-routed`|Use a linked worktree with no local config and a Kimi pin in the main checkout, then make the main-checkout lookup fail; `repo_config_dir` returns `unknown`, but `route` continues with defaults.
FIX|plugin/crew/hooks/scripts/crew_kimi_agent.py:310|A wrong-typed Kimi model can raise `TypeError` without the required exit-2 contract line|Set `dev.roles.explorer` to `{"provider":"kimi","model":["k3"]}`; provider validation accepts it, then the probe uses the list as a dictionary key.
FIX|plugin/crew/agents/security.md:63|When the caller supplies neither a base nor a full diff, the dispatcher cannot determine the instructed merge-base while keeping its first and only Bash call as the dispatch|Ask security to review a change without naming a base; it must run Git first, guess a base, or dispatch without the required change bundle.
FIX|plugin/crew/hooks/scripts/crew_kimi_agent.py:140|Reading an agent path that is a FIFO can hang indefinitely instead of returning a usage error|Pass an `--agents-dir` whose `explorer.md` is a FIFO with no writer; the script blocks in `open()` before printing a contract line.
```
