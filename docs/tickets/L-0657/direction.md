# L-0657: CI fails when a built crew guide is stale          status: direction   risk: low

Split from T-0055 on 2026-10-04. Filed as L-0657.

## Ask
The owner's rule (2026-09-26) is that a crew change updates every document that describes it, including the rebuilt guides. T-0055 makes CI check that a narrative doc was touched or a reason given. This child makes CI check that the committed guide HTML matches its Markdown sources.

## What exists at origin/main 155fe6d8
- `docs/guides/crew/src/build.py` builds five guides. It has no `--check` mode (`:245-262`).
- T-0048 (state: spec) adds `build.py --check`: rebuild each guide's HTML in memory, exit 1 naming a guide whose committed HTML differs, exit 2 when `markdown` cannot be imported. It also adds `config_reference.py --check`. T-0048 runs both from `.crew/verify.json` only, and says the check does not run in CI.
- CI does not install `markdown`: `.github/workflows/marketplace.yml:39-40` installs pyyaml only, and `.pylintrc:59-64` records that the pylint job has no `markdown` on purpose.
- DOCX and PDF are not byte-reproducible (LibreOffice), so only HTML can be compared.

## Options
1. **A step in `marketplace.yml` that installs `markdown` and runs T-0048's two `--check` commands (recommended).** Small, blocks in CI, no new workflow.
2. A separate workflow with a `paths:` filter on `docs/guides/crew/**`. Cheaper per run, but a path-filtered workflow cannot be a required check without also reporting on PRs it skips.
3. Leave it to `.crew/verify.json` as T-0048 does. Autopilot merges on green CI checks, so a stale guide would still merge.

## Recommendation
Option 1.

## Depends on
T-0048 (spec) must be merged: it provides both `--check` commands. T-0055 (this ticket's parent slice) should land first so the two CI edits do not conflict.

## Open questions for the owner (default taken)
- Pin the `markdown` version in CI? Default: yes, to the version the committed HTML was built with, because a different version can change the HTML and fail every PR. The implementer reads the version from the environment that built the committed guides.

## Approval
Covered by the T-0055 direction approval (owner's standing authorization, 2026-09-26); this child narrows it and adds nothing.
