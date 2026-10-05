---
description: Removed - use /crew:migrate, which upgrades a pre-0.20 config itself
allowed-tools: Read
---

`/crew:upgrade` was removed. It is not an alias and does nothing.
`/crew:migrate` now brings a pre-0.20 `.crew/config.json` (no `schema`, or 1-6)
up to the current schema and migrates it in the same run, with one backup and
one rollback. Graph facts for the code map come from `/crew:onboard --refresh
<subsystem>`. Tell the user that, and stop.
