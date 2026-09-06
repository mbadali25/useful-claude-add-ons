# repo-docs
anchor: useful-claude-add-ons@a02331ee
verified: 2026-09-06

## Does
Holds the repo's hand-written documentation - the three Mermaid diagrams, planning artifacts under
`docs/superpowers/`, operational runbooks, handoff notes, and the top-level `CHANGELOG.md`. Nothing
here is generated except the rendered diagram images, and that is deliberate: this repo's rule is
that prose documents are never auto-refreshed.

## Entry points
- `docs/diagrams/architecture.mmd:1-2` - and `data-flow.mmd`, `process.mmd` alongside it. Each
  carries its own `%% anchor:` and `%% Anchors:` headers, read by the `crew-diagrams` skill.
- `docs/HANDOFF.md:1-9` - rolling handoff notes, newest first; read by a human or by
  `/crew:handoff`.
- `docs/remaining-setup.md:1-9` - the ordered manual checklist for credential and consent steps no
  script can perform.
- `docs/runbooks/rollback.md:1-20` - read when `check-marketplace.py` fails on `main` or a bad
  version ships.
- `CHANGELOG.md:5` - the `## [Unreleased]` section, appended to per plugin-version bump.

## Owns data
- `docs/diagrams/out/*.svg` and `*.png`, generated from the `.mmd` sources by
  `plugin/crew/skills/crew-diagrams/scripts/render.sh:1`. Never hand-edit anything under `out/`.
- Everything else under `docs/` is hand-written, `docs/superpowers/` included - those are plans and
  design specs recording decisions already made, and nothing in the repo reads them back at runtime.

## Calls out to
- `mmdc` (mermaid-cli), invoked at `plugin/crew/skills/crew-diagrams/scripts/render.sh:45`.

## Landmines
- **`docs/adr/` does not exist.** `CLAUDE.md` states "Decisions in `docs/adr/`" and
  `CHANGELOG.md:1195-1196` assigns ADR ownership to the `scribe` agent, but the directory is absent
  from the working tree at this anchor. No ADR has ever been written. Two documents describe a
  location that is not there.
- **`TODO.md:361-391` is stale about `render.sh`.** It records the script as failing 6/6 on Windows
  by handing `mmdc` a Git Bash `/tmp` path. That is fixed in source:
  `plugin/crew/skills/crew-diagrams/scripts/render.sh:33-36` resolves the path through `cygpath -w`
  when it is available. The comment above it names the real trigger - a caller with
  `MSYS_NO_PATHCONV=1` set, which turns off MSYS's own rewrite - and that same variable has already
  caused one false regression report in this repo. The Mermaid sources were never the problem.
- **The `%% Anchors:` header is the only thing making a diagram falsifiable.** All three carry one
  (`docs/diagrams/architecture.mmd:2`, `data-flow.mmd:2`, `process.mmd:2`) - confirmed present, not
  assumed. A diagram that loses its header becomes permanently stale-by-default, because the
  question "does this still describe the code" stops having an answer.
- **A count written into a file under `docs/` changes that count.** Recording "N diagrams" or
  "N ADRs" here is self-referential. State the invariant and how to re-measure - walk
  `docs/diagrams/*.mmd` and read the headers - rather than a total that looks measured and is wrong
  by one.

## Unverified
- Whether the `cygpath -w` fix actually resolves the Windows failure end to end: the script was
  read, not executed. Re-verify by running `render.sh` on Windows before trusting either the fix or
  the TODO entry it contradicts.
- Whether `CHANGELOG.md` entries are strictly one per plugin-version bump throughout. Confirmed
  only for the opening entries of `[Unreleased]`; the history was not read back to its first dated
  section.
- Whether anything besides a human or an agent invoking `crew-docs` / `scribe` writes to
  `CHANGELOG.md`. A grep found no automation, but not every hook and script in the repo was traced.
- The contents of `docs/runbooks/` beyond `rollback.md`.
