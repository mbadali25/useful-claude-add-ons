# crew guides - Markdown sources

The Markdown sources for crew's user guides. `doc-builder` renders each one to
HTML, DOCX and PDF; the rendered files are not kept here. A feature is not done
until its guide section exists (`docs/review/04-redesign.md`, "Guides").

| # | Guide | Source | Produced by |
|---|---|---|---|
| 1 | Quickstart - install to first ticket in ten minutes, Windows and Linux | `quickstart.md` | T2 (this build), completed by T4 and T8 |
| 2 | Daily workflow - one ticket worked end to end, full and light paths | `daily-workflow.md` | T4 |
| 2a | Daily workflow: scope and approval - the ticket contract, linked from guide 2 | `daily-workflow-scope.md` | T4 |
| 3 | Memory and Obsidian - setup, capture, the gardener, upkeep | `memory-and-obsidian.md` | T7 |
| 3a | Memory and Obsidian: confirming recall reaches your sessions | `memory-recall-proof.md` | T7 |
| 4 | Working with Codex - `AGENTS.md`, profiles, review and hooks | `working-with-codex.md` | T6 |
| 5 | Troubleshooting - stale installs, hook noise, review loops, turning things off | `troubleshooting.md` | T10 |
| 5a | Auto wrap-up, clear and resume - the automatic context cycle, linked from guide 5 | `auto-cycle.md` | crew 1.0 autocycle |

Ticket numbers follow the merged order in `docs/review/04-redesign.md`
("Ticket order"). That order and `04a`'s table number two tickets differently
(Codex parity is T6 in the merged order, T5 in `04a`); the merged order wins.

The four existing HTML families in `docs/guides/crew/` (overview,
capabilities, technical reference, the dated progress report) are replaced or
archived by T10, not by this directory. This build does not touch or remove
them — that decision is still the owner's.

## Built artifacts

T10 built the five guides with `doc-builder` (theme `midnight`, brand
`neutral`, rendered by LibreOffice on Linux), each as HTML, DOCX and PDF in
`docs/guides/crew/`, named `crew-1.0-<guide>.{html,docx,pdf}`. The three
appendix sources (`daily-workflow-scope.md`, `memory-recall-proof.md`,
`auto-cycle.md`) have no `doc-builder` include mechanism to fold into their
parent at build time, so they are folded by concatenating Markdown before
conversion — each appendix's headings demoted one level and appended after
its parent's own content, as a trailing section in the same document, rather
than shipped as separate linked files:

| Artifact | Built from |
|---|---|
| `crew-1.0-quickstart.{html,docx,pdf}` | `quickstart.md` |
| `crew-1.0-daily-workflow.{html,docx,pdf}` | `daily-workflow.md` + `daily-workflow-scope.md` |
| `crew-1.0-memory-and-obsidian.{html,docx,pdf}` | `memory-and-obsidian.md` + `memory-recall-proof.md` |
| `crew-1.0-working-with-codex.{html,docx,pdf}` | `working-with-codex.md` |
| `crew-1.0-troubleshooting.{html,docx,pdf}` | `troubleshooting.md` + `auto-cycle.md` |
