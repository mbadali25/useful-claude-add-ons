---
name: report-builder
description: Build professional, human-facing reports as HTML that convert cleanly to DOCX and PDF through Microsoft Word - a branded masthead, a plain-language lede, summary cards, findings tables with severity chips, and a footer that says where every number came from. Encodes the exact CSS Word's HTML parser silently drops (CSS variables, :nth-child, two class names on one element, flex/grid), which is what makes a report arrive as unstyled black-on-white text with no error. Use this skill whenever the user asks for a report, an assessment, an audit write-up, a findings document, a security or posture report, an executive summary, or says "make this a PDF", "send this to the client", "write this up for management", "make it look professional", or hands over data that a person rather than a machine has to read. Also use it when styling an existing report, when a generated DOCX or PDF came out unstyled, when choosing severity colours, or when deciding whether something should be one report or a summary plus a detail report.
---

# Report Builder

Human-facing reports, authored as HTML and converted to `.docx` and `.pdf` by
Word (`Word.Application` COM).

**The browser is not the target. Word's HTML parser is the target**, and it is
far more limited. A stylesheet that is perfect in Chrome can arrive in the PDF
as flat black-on-white text — with no error, no console warning, nothing that
tells you it happened. Every rule in `references/word-traps.md` was measured
against the Word object model, not assumed.

## Start here

1. **Decide the tier.** Concise summary, or summary plus a separate detail
   report — see "Two tiers" below. This decision comes first because it
   determines what goes in the document, and the commonest failure is one
   sprawling report nobody finishes.
2. **Read `references/word-traps.md`** before writing any CSS. Five traps, each
   of which fails silently and completely.
3. **Take the palette from `references/palette.md` verbatim.** Literal hex.
4. **Assemble the furniture** in the order under "Page furniture".
5. **Convert and inspect the result**, do not preview it in a browser. The
   verification snippet is in `references/word-traps.md`.
6. **Run the checklist** at the end of that file before shipping.

`scripts/build_report.py` emits a conforming skeleton — masthead, meta table,
lede, cards, findings table, footer — with every trap already avoided. Start
from it rather than from a blank file, and read `references/word-traps.md` to
understand what it is protecting you from before you change it.

## Two tiers: concise by default, detail on request

**Default to the concise report.** A report is read by someone deciding what to
do, and they decide from the lede, the cards and the findings table. Length is
not thoroughness; it is the main reason a report goes unread.

The concise report:

- One-line title block, one-paragraph lede stating the single most important
  finding in plain language. **If the reader stops after the lede they still
  have the headline.**
- At most five summary cards. More than five and none of them register.
- One findings table: ID, title, status, severity, count. Nothing else.
- No methodology section, no per-item evidence, no raw output.

**When the detail genuinely matters, write a second document** rather than
inflating the first: `<Name>-Detail-<timestamp>`. The summary references it by
name. Per-finding evidence, the commands or queries that produced each number,
full result sets, and the methodology all live there.

This is the shape to reach for whenever you notice a report growing past two
pages. Splitting is the fix; shrinking the font is not.

## Page furniture, in order

| Element | Rule |
|---|---|
| **Masthead** | Four stacked table rows: accent strip, navy band (organisation, title, subtitle), darker rule, classification bar. Tables with cell shading — a coloured `<div>` renders as a bare paragraph in the DOCX. |
| **Meta table** | Label/value pairs, two per row. Report name, generated-at, scope, who ran it, headline counts. Answers "what am I looking at, can I trust it" before any finding. |
| **Lede** | One short panel. The single most important finding, in plain language. |
| **Handling notice** | Required on any report naming accounts, hosts or weaknesses. Says plainly that the document is a target list if it leaks. |
| **Summary cards** | Table-based, five maximum. |
| **Findings table** | ID, title, status, severity, count. **IDs stable across runs** so they can be quoted in tickets. |
| **Footer** | Script name, version, host, account, UTC timestamp. Someone will ask where a number came from in six months. |

The organisation name comes from the system being assessed — the Entra tenant
display name, the AD domain — **never hard-coded**, so the report identifies its
own subject.

**The classification bar is not decoration.** These documents name compromised
accounts and weak configuration. The bar states the handling requirement where
nobody can miss it, including on a page printed and left on a desk.

## Colour never carries meaning alone

A red cell means nothing to a reader with colour-vision deficiency and nothing
at all on a mono office printer — which is exactly where security reports end
up. Always pair the colour with the word:

```html
<span class="chip-critical">CRITICAL</span>   <!-- right -->
<td style="background:#b3261e"></td>          <!-- wrong -->
```

`Unverified` is its own severity, never folded into `Pass`. **A check that could
not run is not a check that passed**, and a report rendering the two alike is
lying by omission.

## Where the output goes

**Generated reports go to `reports/` at the repository root** — one directory,
so someone collecting evidence looks in one place instead of hunting the tree by
script author. Name them `<ReportName>-<yyyyMMddHHmm>.<ext>`, which sorts and
cannot collide between runs on the same day.

**`reports/` is gitignored.** These documents read as an attack plan and must
never reach the remote. Add the ignore rule in the same change that adds the
first report script.

Do not confuse this with `docs/`. `docs/` holds documentation that describes the
system and is meant to live in the repo; `reports/` holds dated, generated
output about a point in time and stays out of git. A report is not documentation
and does not belong in `docs/`.

## Re-render without re-collecting

A report script that talks to a live system **writes its full state to JSON**
alongside the HTML, and the builder consumes that JSON. That is what makes it
possible to restyle the document later without contacting the system again.

Without it, restyling a report that needed a live tenant, a domain-joined host,
or credentials nobody has today means the old document simply stays unstyled.

**A re-render must say it is one.** Carry a notice naming the date the findings
were actually collected. A restyled report that looks freshly generated, with
today's date on top and month-old findings underneath, is worse than the ugly
one it replaced.

## References

- `references/word-traps.md` — the five silent-failure rules, column-width
  sizing, print rules, the Word object-model verification snippet, and the
  pre-ship checklist. **Read before writing CSS.**
- `references/palette.md` — structure and severity colours as literal hex,
  chosen for contrast on white and for staying distinguishable in greyscale.
- `scripts/build_report.py` — a conforming HTML skeleton generator, and
  `--to-docx` / `--to-pdf` conversion through Word COM on Windows.
