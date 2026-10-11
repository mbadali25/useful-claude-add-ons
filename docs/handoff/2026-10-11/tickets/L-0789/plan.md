# L-0789 plan

## Step 1 - re-anchor both diagrams, regenerate what carries them, bump crew
- Files: docs/diagrams/data-flow-crew-config.mmd, docs/diagrams/data-flow-crew-config-ratchet.mmd, docs/diagrams/README.md, docs/diagrams/index.html, plugin/crew/README.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md, CHANGELOG.md, README.md
- Change: move both provenance headers to 987ea4fb with a re-anchor note; re-take every Note line's count and line number with grep -n and by import; correct node E2's line number; render, diagram_check, diagram_doc.py --write, crew_diagrams.py embed; bump crew to the next free version with a CHANGELOG line and sync-updates.
- Test: crew_refresh_check.py, diagram_check.py, crew_diagrams.py check, scripts/check-marketplace.py, scripts/check-crew-docs.py, scripts/check-tooling-pr.py, sync-updates.py --check.
- Risk: a version race with another lane; re-check origin/main right before the merge.
