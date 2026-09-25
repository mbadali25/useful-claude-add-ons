---
paths:
  - "skills/wazuh-onprem/**"
  - "skills/cisco-meraki/**"
---
<!-- crew:generated source=.crew/codemap/skills-security-ops.md sha256=65047ddc0c96e988 -- do not hand-edit; regenerate with crew_instructions.py rules -->
# skills-security-ops
Code map anchor `f2bb919b`; if it is behind HEAD, re-check with `git diff --name-only f2bb919b..HEAD -- <cited paths>`.
Covers: cisco-meraki + wazuh-onprem. Records that Wazuh's generic post/put/delete have no gate in code — only prose — and that the skill with the ungated verbs is the one with no tests.
## Landmines
- Wazuh's generic `post` / `put` / `delete` have no gate in code.
- `manager_config.py apply` has no confirmation either, and this note previously missed it.
- Nothing in `skills/wazuh-onprem/scripts/` redacts anything.
- `--yes` on the Meraki write path auto-confirms.
- `meraki_client.py` is not read-only, despite reading like it.
- Rate limiting is handled on one side only.
- An unset `WAZUH_CA_BUNDLE` disables TLS verification for every call.
- `cmd_rollback` interpolates an operator-supplied path into a remote shell string.
- Test coverage is asymmetric: `skills/cisco-meraki/tests/` holds eight `test_*.py` modules; `skills/wazuh-onprem/` ships no `tests/` directory at all (DERIVED: it contains only `SKILL.md`, `references/`, `scripts/`).
Full note: `.crew/codemap/skills-security-ops.md`.
