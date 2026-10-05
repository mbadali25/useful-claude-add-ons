---
paths:
  - "skills/notify/**"
  - "skills/infra-work-ticketing/**"
  - "plugin/gizmoduck/**"
---
<!-- crew:generated source=.crew/codemap/skills-itsm.md sha256=4a41c75e6687b3e8 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# skills-itsm
Code map anchor `5be137d8`; if it is behind HEAD, re-check with `git diff --name-only 5be137d8..HEAD -- <cited paths>`.
Covers: infra-work-ticketing + notify. Records that SKILL.md:209-211 still instructs an unconfirmed ticket creation by default against a live service desk; a scanner-batch carve-out at :213-231 narrows that, and the missing-fact list moved to :233.; T-0107 re-anchored it f2bb919b -> 0da787d3 -> 53ba2fd7 -> 40292eca -> 91b793fa -> 7773abb2 (routine CLI, its review fixes; this row restored after the merge of main 04dde5a2); L-0599 re-anchored it to 5be137d8 (a pylint pragma, no line moved)
## Landmines
- Ticket creation is ungated by default, and gated for exactly one class of caller.
- MCP writes bypass the secret scrubber.
- A failed MCP write is lost; a failed `ticketctl.py` write is not.
- The Telegram token is env-only, and the code enforces it - DERIVED `skills/notify/scripts/notify.py:88` and `:193` read `os.environ.get(tgc.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))` and nothing reads a literal toke...
- A `question` event blocks.
- DERIVED Config resolution is global `~/.config/notify/config.json` merged with per-project `./.notify.json` via `deep_merge` at `skills/notify/scripts/notify.py:63`, project keys winning - JUDGEMENT the same two-layer...
Full note: `.crew/codemap/skills-itsm.md`.
