# L-0764 - /crew:done check 4 is stale on every ticket that touches README.md

Source: owner decision 2026-10-10, relayed by the coordinator, after L-0759 (PR #595) was merged with /crew:done checks 2 and 4 waived.

## Problem
`crew_refresh_check.py --ticket <id>` (/crew:done check 4) reads all 8 code maps (crew, install-scripts,
localgpu, marketplace-registration, mcp-servers, obsidian-vault, repo-docs, verification-harness) and
`graphify-out` stale whenever README.md changes. Every CHANGELOG entry forces a README.md change
(`scripts/sync-updates.py` regenerates "What's new"), so check 4 refuses /crew:done on practically every
ticket, and lanes merge on owner waivers instead.

Verbatim, L-0759 at 8937b726 (fallback scope base d8de3dafb70f):
```
codemap crew: stale - README.md, plugin/crew/tests/test_promote_gate_review.py changed since its anchor 5307a80e [fallback base]; refresh with /crew:onboard --refresh crew
graph graphify-out: stale - README.md, plugin/crew/tests/test_promote_gate_review.py changed since its anchor cedbf6ed21b9; graphify's manifest.json is missing or unreadable, so not usable [fallback base]; refresh with /crew:graph --refresh
```
(the same line repeats for the other 7 maps)

## Hits
- L-0759 (PR #595): merged with checks 2 and 4 waived.
- L-0753 (PR #593): check 4 refused on the ticket's own stale artifacts.
- L-0709 (PR #584): hit.
- L-0760 (PR #596): /crew:done refused checks 2/3/4/5.

## Open questions for spec
- Should the generated "What's new" block in README.md count as a change any code map documents?
- Why does one test file reach all 8 maps?
- The graph's missing manifest.json.
