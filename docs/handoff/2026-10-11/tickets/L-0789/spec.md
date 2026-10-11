# L-0789 re-anchor data-flow-crew-config and its ratchet part after L-0710 and L-0772          status: spec   risk: low
## Intent
Re-anchor `docs/diagrams/data-flow-crew-config.mmd` and `docs/diagrams/data-flow-crew-config-ratchet.mmd` to 987ea4fb (PR #582's merge), re-measuring every count and line number their Note lines cite, and regenerate the page and README embed that carry them.
## Exclusions
- No crew code, test, hook, command or prompt changes. No other diagram is redrawn.
- `process-crew-lifecycle-implement` reads FAIL in the readability check on main already; not this ticket.
## Evidence
- `git diff --stat a7fb104b..987ea4fb` over the overview's Anchors: CONFIG.md, crew_config.py, crew_guards.py, crew_state.py. The direction expected CONFIG.md only; L-0772 (f4d98abc) also moved the three code anchors.
- By import at 987ea4fb: ALL_GUARD_NAMES 12, RATCHETED_KEYS 15, _RATCHETED 16, difference {'pm.authority'}.
- The ratchet part's node E2 cites `effective_ratcheted :564`; it is `crew_guards.py:593` now. That label is embedded in `plugin/crew/README.md`, so the plugin's content changes and crew needs a version bump.
## Unknowns
none - light path
## Touch
- `docs/diagrams/data-flow-crew-config.mmd`
- `docs/diagrams/data-flow-crew-config-ratchet.mmd`
- `docs/diagrams/README.md`
- `docs/diagrams/index.html`
- `plugin/crew/README.md` landmine: only the embedded ratchet diagram block may change
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `README.md` landmine: only the version claim and the generated What's new block
## Acceptance checks
- [ ] `crew_refresh_check.py --ticket L-0789` reads both diagrams fresh
- [ ] `diagram_check.py` PASS for both diagrams
- [ ] `python3 scripts/check-marketplace.py` clean after the commit
