---
name: solomon-doc-builder
description: >
  Brand pack only - the Solomon Associates house style for doc-builder: palette
  (0E2841 navy, EF483D accent), Franklin Gothic Book / Georgia, the Proprietary and
  Confidential footer, the onboarding SOP template and the OnboardingSOPs masters
  location. Contains no scripts and builds nothing; `doc-builder` does all the work and
  applies this pack automatically whenever it is installed. Use this skill only when the
  user asks what the Solomon brand values are, wants to change them, or asks where the
  Solomon SOP masters and specs live. For writing any report, SOP, runbook or guide -
  Solomon-branded or not - use `doc-builder`.
---

# Solomon brand pack

A data directory with a marker file. `doc-builder/scripts/resolve_brand.py` finds
`assets/brand.json` here and applies it to every document without being asked, so an
operator at Solomon never has to remember to request Solomon styling.

**Install this alongside `doc-builder`, not instead of it** - this pack has no builder
of its own. `claude plugin install doc-builder@useful-claude-add-ons` then
`claude plugin install solomon-doc-builder@useful-claude-add-ons` (either order); once
both are on the machine, branding is automatic from then on.

**Not at Solomon, or don't want this pack's styling on a shared machine?** It never has
to be uninstalled to turn it off: `doc-builder`'s scripts take `--brand neutral` (or
`DOC_BUILDER_BRAND=neutral` in the environment) and that always wins over this pack, no
matter how many brand packs are installed. See `doc-builder/SKILL.md`'s "Brand
resolution" section for the full precedence order and how a machine with several packs
installed picks between them.

| File | What it is |
|---|---|
| `assets/brand.json` | Palette, fonts, footer text, template and directory locations. Keys omitted here inherit from `doc-builder/assets/brands/neutral/brand.json`. |
| `assets/sop_template.docx` | Blank house template (34 KB): `Normal` = Franklin Gothic Book, margins 0.8/0.6/0.5/0.5, the three-cell footer. Generated from the canonical master by `make_template.py`, not hand-made. |
| `assets/specs/qrg-archiving.json` | The one production SOP that has a build spec. Its `output` and image paths are relative to the spec file and assume `OnboardingSOPs` is checked out two levels up. |

## Where the Solomon documents live

| Thing | Location |
|---|---|
| SOP masters (`.docx` + `.pdf`) | `C:\repos\OnboardingSOPs\sops_new` - `sop.masters_dir`, override with `DOC_BUILDER_MASTERS_DIR` |
| Source screenshots | `C:\repos\OnboardingSOPs\assets\<sop-slug>\` - `sop.assets_dir` |
| Canonical reference master | `How to access LinkedIn Learning.docx` - the file the set was standardised against |
| Brand reference | `Onboarding Presentation IT Operations 2026.pptx` in `OnboardingSOPs` |

Scope of the SOP template: **end-user onboarding guides** - sign in, install, configure,
get help. Technical or infrastructure runbooks are a different genre; say so and ask
which the user wants before building.

## Changing a brand value

Edit `assets/brand.json`, then re-run `check_conformance.py` over the whole set - the gate
reads its expected values from this file, so a palette change that is not reflected in
the masters shows up as failures, which is the point. Regenerate `sop_template.docx` with
`make_template.py --reference "<canonical master>"` only if the footer, margins or base
font change.

## Known state of the Solomon set (measured 2026-08-25, captions 2026-09-08)

- Eight masters still have a 0.5" top margin (LogMeIn, both mobile e-mail SOPs, Phishing
  button, Outlook archive 3d, KnowBe4, Teams, Remote Desktop). House-consistency warning
  only; it does **not** affect borders.
- Only one of the 19 masters (`qrg-archiving`) has a spec. Editing any other means
  `extract_spec.py` first, one master at a time, when that master is next actually edited.
- `3d. How to create an archive in MS Outlook` and `QRG - Archiving Emails within Outlook`
  cover the same procedure. Worth deciding whether both should ship.
- `OnboardingSOPs\HANDOFF.md`'s older entries carried false claims for months (the
  top-margin "fix", keep-with-next). Where it disagrees with
  `doc-builder/references/template-spec.md`, the spec wins.
- Stand-ins for anonymised screenshots: `firstname.lastname@solomoninsight.com`, `user`.
  Service desk contact in the `Need help?` section: `ithelpdesk@solomoninsight.com`.
