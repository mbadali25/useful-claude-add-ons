---
paths:
  - "skills/notify/**"
  - "skills/infra-work-ticketing/**"
  - "plugin/gizmoduck/**"
---
<!-- crew:generated source=.crew/codemap/skills-itsm.md sha256=e7eb6074b379bf19 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# skills-itsm
Code map anchor `40292eca`; if it is behind HEAD, re-check with `git diff --name-only 40292eca..HEAD -- <cited paths>`.
Covers: infra-work-ticketing + notify. Records that SKILL.md:209-211 still instructs an unconfirmed ticket creation by default against a live service desk; a scanner-batch carve-out at :213-231 narrows that, and the missing-fact list moved to :233.; re-anchored to 40292eca (T-0107 round-1 fixes and its merge of main ffd11270)
## Landmines
- Ticket creation is ungated by default, and gated for exactly one class of caller.
- MCP writes bypass the secret scrubber.
- A failed MCP write is lost; a failed `ticketctl.py` write is not.
- The Telegram token is env-only, and the code enforces it - DERIVED `skills/notify/scripts/notify.py:88` and `:193` read `os.environ.get(tgc.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))` and nothing reads a literal toke...
- A `question` event blocks.
- DERIVED Config resolution is global `~/.config/notify/config.json` merged with per-project `./.notify.json` via `deep_merge` at `skills/notify/scripts/notify.py:63`, project keys winning - JUDGEMENT the same two-layer...
Full note: `.crew/codemap/skills-itsm.md`.
