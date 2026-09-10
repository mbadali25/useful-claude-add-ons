---
name: report-builder
description: >
  Do NOT use this skill - use `doc-builder` instead. Deprecated 2026-09-10: report-builder
  was merged into `doc-builder`, which owns the HTML -> Word COM report pipeline, the
  Word-traps reference and the palette, plus the SOP pipeline and brand packs. This stub
  exists only so old references to the name resolve; it contains no scripts.
---

# report-builder (deprecated)

Merged into [`doc-builder`](../doc-builder/SKILL.md) on 2026-09-10.

| Was here | Now |
|---|---|
| `scripts/build_report.py` | `doc-builder/scripts/build_report.py` (now brand-aware, `--brand`) |
| `references/word-traps.md` | `doc-builder/references/word-traps.md` |
| `references/palette.md` | `doc-builder/references/palette.md` (neutral tokens; a brand pack overrides) |
| `scripts/_test/checklist.sh` | `doc-builder/scripts/_test/checklist.sh` |

Nothing else to do here. Invoke `doc-builder`.
