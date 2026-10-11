# L-0789 - re-anchor two config data-flow diagrams after L-0710

Source: L-0710 (PR #582, merged 987ea4fb, crew 1.2.30), /crew:done check 4, 2026-10-11 lane E.

```
diagram data-flow-crew-config-ratchet: stale - plugin/crew/CONFIG.md changed since its anchor 5307a80e [fallback base]; refresh with /crew:diagram refresh
diagram data-flow-crew-config: stale - plugin/crew/CONFIG.md changed since its anchor a7fb104b [fallback base]; refresh with /crew:diagram refresh
```

L-0710 appended 17 lines to plugin/crew/CONFIG.md at :2961 (chronic rules go to CI; a turn where zero rules ran
records nothing). No heading, no earlier line moved. Expected: a re-anchor with no node or edge change, as the L-0733
follow-up refresh did. Verify before re-anchoring.

## Acceptance Criteria
- Both diagrams re-anchored to a commit containing 987ea4fb, with a re-anchor note; `crew_refresh_check.py` reads them fresh.
- Refresh PR only: no behaviour change.
