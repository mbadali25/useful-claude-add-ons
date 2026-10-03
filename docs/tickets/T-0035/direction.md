# T-0035 direction - diagrams are organised by kind and embedded where people and agents read

Status: direction APPROVED by the owner 2026-09-26 ("approve 1-3").

## Ask (owner, Matthew Badali, 2026-09-26, verbatim)
"I do also want to make a another ticket for when the crew makes diagrams, I would like them to attach
them to README.md files and orgranize them proprerly (architecutre, design, data flow, process) and sub
items if you find is necessary or makes sense but becuase you make the diagrams I want them to easily be
able to be ready by you and humans"

## Facts (origin/main 3c1f94a9, 2026-09-26)
- Seven diagrams sit flat in `docs/diagrams/` as Mermaid source, with the kind only in the filename prefix:
  `architecture.mmd`, `data-flow.mmd`, `data-flow-crew-config.mmd`, `process.mmd`,
  `process-crew-brief.mmd`, `process-crew-lifecycle.mmd`, `process-bitbucket-svg.mmd`.
- Rendered SVG/PNG are not tracked. `/crew:diagram` (`plugin/crew/commands/diagram.md`) writes
  `docs/diagrams/<name>.mmd` with a provenance header and anchor list, then renders with
  `skills/crew-diagrams/scripts/render.sh`.
- No README embeds a diagram. `README.md` and `plugin/crew/README.md` mention "mermaid" 1 and 2 times, as
  prose, and `plugin/crew/README.md:1762` only says where the source goes.
- T-0008 keeps diagrams current: `crew_refresh_check.py` judges each `.mmd` by its anchors, and the
  refresh step re-verifies it. The diagrams dir comes from `docs.diagramsDir` (default `docs/diagrams`).
- GitHub renders fenced ```mermaid blocks inline in markdown. Bitbucket does not (hence the existing
  `mermaid-svg-bitbucket` skill), so a repo hosted there needs an SVG beside the source.

## Options
- A. Embed rendered SVG images in READMEs. Readable by humans, but an agent reading the README gets an
  image link, not the structure.
- B. Embed the Mermaid source as fenced ```mermaid blocks in READMEs. GitHub renders it for humans, and
  agents read the same text. But a copy in the README drifts from the `.mmd` unless something keeps them in step.
- C. The `.mmd` stays the single source, and a script writes generated, marker-delimited ```mermaid blocks
  into the READMEs, with a check that fails when a README block differs from its `.mmd`. Humans see a
  rendered diagram on GitHub, agents read text, and there is one source of truth. For Bitbucket-hosted
  repos the same generator adds the rendered SVG next to the block (the `mermaid-svg-bitbucket` path).

## Recommendation (to be confirmed)
C, with this layout:
1. **Organised by kind, then subject:** `docs/diagrams/architecture/`, `design/`, `data-flow/`,
   `process/`, and a subfolder per subject when a kind holds more than a few, e.g.
   `process/crew/lifecycle.mmd`. The existing 7 move there, and history is kept with `git mv`.
2. **An index:** `docs/diagrams/README.md` lists every diagram by kind, with its one-line purpose, its
   anchors, and the embedded block, so there is one page to browse.
3. **Attached where relevant:** each plugin or skill README gets a generated "Diagrams" section embedding
   the diagrams whose anchors fall inside that plugin. Nothing is hand-copied.
4. **Kept in step:** a generator (`crew_diagrams_embed.py`) plus a check wired into `.crew/verify.json` and
   `check-marketplace.py`. `/crew:diagram` and the T-0008 refresh run the generator after every render,
   so a refreshed diagram updates its README embeds in the same commit.
5. **Readable by both:** each block carries a short text summary above it (what it shows, what it
   deliberately leaves out), so an agent or a screen reader gets the point without parsing Mermaid.

## Open questions
- Which kinds count as "design" versus "architecture"? Proposal: architecture = components and
  deployment; design = module/class/sequence-level detail inside one component.
- Should the generator also run inside consumer repos that install crew, or only this repo? It is a crew
  feature, so it should likely be both, with `docs.diagramsDir` honoured.
- Does `docs.diagramsDir` move to the per-kind layout, or become a root with kinds under it (preferred)?
- Moving the 7 files changes the paths T-0008's refresh check and the codemaps cite, so re-anchor them
  in the same change.

## Added on approval (owner, 2026-09-26: "approve 1-3", including the readability rules)
Owner: "I'm unsure what to do to make good diagrams that are easy to read and contrast as well becuase the
earlier versions someo of them were messy, overlapped, and etc". Evidence: crew-diagrams SKILL.md:86 says
"over roughly 12 nodes, split", yet docs/diagrams/process-crew-lifecycle.mmd has 51 edges - the rule is prose
nothing checks. So these become checked, not advisory:
- Size: at most ~12 nodes / ~15 edges per diagram; larger subjects split into an overview plus linked detail
  diagrams. A lint fails the render.
- Layout: Mermaid's ELK layout (`layout: elk`) and subgraphs for related nodes, set by a shared header.
- Contrast: one shared theme, tested for WCAG AA contrast in light and dark mode; a fixed colour per node role
  (service, datastore, external system, person); colour never the only signal.
- Labels wrapped at ~30 characters; detail goes in the text table, not the box.
- Direction by kind: LR for flows and data, TB for hierarchies and decisions.
- Every edge in a flow or sequence labelled (already a rule; now linted).
- Render-and-inspect before commit: render to PNG/SVG, an automated overlap check on the SVG element boxes,
  and the agent reads the rendered image; anything cramped is split.
- The 7 existing diagrams are redrawn under these rules as part of the move.

## Added 2026-09-26 (owner, verbatim): automatic in crew's routines
"for T-0035 /36 this should be a part of the crew routines automatically when running"
So this is not only a command someone remembers to run. It runs as part of crew's normal flow:
- `/crew:implement` step 6 (the docs + refresh step, before review) runs it for the paths a ticket changed:
  T-0035 regenerates diagram embeds and runs the readability lint on any diagram the change reaches;
  T-0036 updates the integration and flow docs whose anchors the change reaches, and proposes a new
  flow doc when a change adds an outbound call or a new multi-step flow.
- `/crew:done` check 4 (via `crew_refresh_check.py`) refuses when a reached diagram or reference doc is
  stale, the same way it already refuses stale codemaps - so skipping it cannot pass the gate.
- `/crew:onboard` (first run and `--refresh`) builds them for a repo that has none yet.
- Autopilot (T-0004/T-0022 docs phase) runs the same step unattended; anything needing judgement (naming a
  new flow, splitting an oversized diagram) becomes a needs-owner question, not a silent guess.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
Owner Matthew Badali, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
Owner Matthew Badali, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); /root/crew-tmp/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.

## Split 2026-09-30 (owner 2026-09-30 "Triage pass now")

Owner decision 2026-09-30 ~11:30: oldest tickets first, 1-2 deliverables per ticket, extras split into new tickets.

Kept in T-0035: plan Step 1 (nested discovery, kind by directory) and Step 3 (the generator: embed, check, index, Bitbucket mode), with Step 4's refresh-check and completion-audit wiring for embeds, Step 5's docs and Step 7's gate/version work for those.

Moved:
- L-0547: plan Step 2, the readability lint and shared theme (and its lint lines in the refresh check).
- L-0548: plan Step 6, migrating this repo's diagrams (git mv, redraw, overviews, embed, re-anchor).

spec.md and plan.md are APPROVED and were not edited. Before implement, they need a successor amendment narrowed to the kept scope, and a re-approval.
