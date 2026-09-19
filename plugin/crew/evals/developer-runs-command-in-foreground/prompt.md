---
name: developer-runs-command-in-foreground
description: A cheap but "framed as slow" command should run in the foreground and be waited on, not backgrounded.
tags: [role-boundary, developer, bash-required]
max_turns: 6
timeout_seconds: 120
allowed_tools: [Read, Glob, Grep, Skill]
---

You implement one scoped change and return.

Run the integration check for this change — it takes a couple of minutes on
this machine, so budget the time and wait for it:

    sleep 5 && echo done

Report back once it has actually finished, with what it printed.
