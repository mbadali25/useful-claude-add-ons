---
name: solomon-sop-maker
description: >
  Do NOT use this skill - use `doc-builder` instead. Deprecated 2026-09-10: solomon-sop-maker
  was split into `doc-builder` (the python-docx SOP pipeline, both conformance gates, the
  template spec, screenshot rules) and `solomon-doc-builder` (the Solomon brand pack:
  palette, fonts, footer, template, masters location). This stub exists only so old
  references to the name resolve; it contains no scripts.
---

# solomon-sop-maker (deprecated)

Split on 2026-09-10 into [`doc-builder`](../doc-builder/SKILL.md) (all logic) and
[`solomon-doc-builder`](../solomon-doc-builder/SKILL.md) (brand values only). The
Solomon brand is applied automatically by `doc-builder` when the pack is installed.

| Was here | Now |
|---|---|
| `scripts/solomon_sop.py` | `doc-builder/scripts/build_sop.py` (`--dry-run`, `--to-pdf`, backups) |
| `scripts/check_sop_conformance.py` | `doc-builder/scripts/check_conformance.py` (Gate 1, brand-parameterised) |
| `scripts/verify_borders.py`, `fix_effect_extent.py`, `extract_spec.py`, `make_template.py` | same names under `doc-builder/scripts/` |
| `scripts/sop_paths.py` | replaced by `doc-builder/scripts/resolve_brand.py` |
| `references/TEMPLATE-SPEC.md`, `toolchain-usage.md` | `doc-builder/references/template-spec.md`, `toolchain-usage.md` |
| `assets/sop_template.docx`, `specs/qrg-archiving.json` | `solomon-doc-builder/assets/` |
| `Build-SopPdfs.ps1` (never present in this repo) | `build_sop.py --to-pdf` |

Git history of the original standalone repo is preserved at
`docs/archive/solomon-sop-maker-history.bundle`.

Nothing else to do here. Invoke `doc-builder`.
