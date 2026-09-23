---
name: doc-builder
description: >
  Build finished, human-facing documents as HTML, DOCX and PDF, rendered by Microsoft Word on
  Windows or by LibreOffice on Linux and macOS - always named on the output, never
  substituted silently - in the installed brand pack's house style or a neutral one. Two
  pipelines behind one skill:
  findings-style reports (assessment, audit write-up, findings document, executive summary,
  posture or security report - masthead, plain-language lede, summary cards, severity chips,
  provenance footer) built as branded HTML - a finished deliverable on its own for a page
  that opens in a browser or a wiki, not only a rendering intermediate - and optionally
  converted through Word COM or LibreOffice to DOCX/PDF; and step-by-step procedures (SOP,
  standard operating procedure, runbook, work instruction, how-to, quick reference guide,
  training guide, onboarding guide for a new hire, user guide, walkthrough - anything that
  tells someone how to set up, install, configure or sign in to something, step by step,
  with screenshots) rendered with python-docx so every screenshot carries a border Word does
  not clip. Use this skill whenever the user asks for a report, an SOP, a runbook, a how-to,
  a guide, instructions with screenshots, documentation of a process, a branded HTML report
  or page, or says "write this up", "make it look professional", "send this to the client",
  "document this process", "make a PDF", "turn this into a Word doc", "add a screenshot to
  the guide", "update the VPN guide", "does this SOP match the template", "put this on the
  wiki", or when a generated DOCX, PDF or HTML page came out unstyled black-on-white, missing
  its print rules, or in the wrong brand's colours. Also use it
  to pick between one report and a summary plus a detail report, and to choose severity
  colours. Brand is resolved automatically from any installed brand pack (for example
  solomon-doc-builder) - the user never has to ask for branding. Do NOT use it to edit an
  arbitrary existing .docx the user hands over, or for slides or spreadsheets.
---

# Document builder

Two rendering pipelines. **Pick the pipeline from the content before writing a line**,
because neither can do the other's job:

| Content | Pipeline | Script |
|---|---|---|
| Findings, tables, severity, executive summary, audit or assessment write-up | HTML, optionally -> DOCX/PDF via renderer | `scripts/build_report.py` |
| Step-by-step procedure with screenshots (SOP, runbook, how-to, guide) | python-docx OOXML | `scripts/build_sop.py` |
| A hand-authored HTML page that only needs the house style (narrative guide, reference, write-up with H3 sections) | HTML, styled in place | `scripts/house_style.py --apply` |

Why two: Word's HTML parser is the constraint on the report side, and every rule in
`references/word-traps.md` was measured against it. On the SOP side, `add_picture()` writes
neither `a:ln` nor `wp:effectExtent`, so Word strokes a screenshot border *outside*
`wp:extent` and clips it at page top. The HTML path cannot produce a bordered screenshot at
all; the OOXML path writes both elements. A procedure with no screenshots may still use the
SOP path - it is the house template for procedures.

## Disambiguation

| The user wants | Use |
|---|---|
| A report, SOP, runbook, guide or write-up produced as HTML, DOCX or PDF | this skill |
| A branded HTML report or page, not converted to DOCX/PDF | this skill - run `build_report.py` and stop before `--to-docx`/`--to-pdf`; its HTML output is already the deliverable |
| A hand-authored HTML page branded to the house style | this skill - `house_style.py --apply <file>`. Never copy a hex literal out of a stylesheet: that is how `docs/guides/*.html` ended up neutral while the installed pack was Solomon |
| Solomon styling on any of those | this skill, with `solomon-doc-builder` also installed - see "Brand resolution" below for the install command, the opt-out, and choosing between packs |
| To edit, extract from or find-and-replace in a `.docx` they already have | the `docx` skill (`anthropic-office-skills:docx`) |
| A slide deck or spreadsheet | `pptx` / `xlsx` skills |
| Only to know what the house style is, without producing a document | `crew:crew-house-style` |

`report-builder` and `solomon-sop-maker` are deprecated stubs that redirect here.

## Requirements - run the preflight first, on every new machine

```bash
cd <skill>/scripts
python3 preflight.py                    # reports; asks once before installing anything
python3 preflight.py --install          # same, without the prompt
python3 preflight.py --venv             # install into <skill>/.venv instead of --user
```

On Windows the same commands are `python preflight.py ...` from `<skill>\scripts`.

It detects each package below by importing it in a fresh interpreter, installs what is
missing with **`python -m pip install --user`** (or into a virtual environment this skill
owns), and then re-imports each one and prints its version. **Never a bare `pip install`**
- on a managed workstation that writes somewhere the operator cannot elevate into or
cannot import from. If pip fails, the preflight prints pip's output verbatim and stops:
no retry, no machine-wide fallback. `requirements.txt` declares the same set.

| Package | For |
|---|---|
| `python-docx` | `build_sop.py`, `check_conformance.py`, `fix_effect_extent.py`, `extract_spec.py`, `make_template.py` |
| `pywin32` | `--renderer word` (Word COM). Windows only; the LibreOffice path needs no package |
| `PyMuPDF`, `numpy`, `Pillow` | `verify_borders.py` (Gate 2); Pillow also for screenshot anonymisation |

Three things the preflight can only **report**, because pip cannot fix them:

- **Which renderer this machine has**, and which one it will therefore use. Two exist:
  **Microsoft Word** over COM (Windows) and **LibreOffice** (`soffice --headless`).
  Word is the reference - every rule in `references/word-traps.md` was measured against
  it - and Microsoft ships no Word desktop app for Linux, so on Linux and macOS
  LibreOffice is not a fallback, it is the only renderer there is.

  **Never fall back silently or unlabelled.** That, not LibreOffice itself, is what this
  skill has always refused: a document the reader believes Word rendered, which Word did
  not render, is worse than no document, because every difference below is invisible to
  them. So the engine is chosen by `--renderer word|libreoffice` or by an explicit
  platform branch, it is printed to stderr with the reason it was reached, and it is
  **named on the line announcing every file it writes**. If the chosen engine cannot run,
  the script stops and names the flag that selects the other one. It never tries the other
  one on its own.

- **Gate 2, which is its own third value.** See "Both gates" below. Without Word it is
  `UNAVAILABLE` - not passed, not skipped.

- **A locked output file.** A PDF open in a viewer or a DOCX open in Word makes Word fail
  "read-only". `preflight.py --target <file>` and the converter itself name the file to
  close.

**Fidelity through LibreOffice is reduced, and specifically so.** Measured 2026-09-22
against LibreOffice 26.2.5.2: its HTML importer applies only **simple** selectors - a bare
`.class` or a bare element - and silently drops every compound or descendant one. On the
report path that costs the table grid, the header shading, the zebra rows, the
summary-card panels and the meta-table key shading; the masthead, lede, handling banner and
every severity chip still render. The SOP path feeds it real OOXML rather than HTML and
survives far better - the self-test renders correctly, borders included - but no LibreOffice
render is evidence about how Word lays the same document out. Full detail, and the mirror-image
list of what *Word* drops, in `references/word-traps.md`.

`build_report.py`, `house_style.py`, `render_engine.py`, `resolve_brand.py` and `preflight.py`
are stdlib.

## Brand resolution - configuration, not a trigger

**Want Solomon house style?** Install `solomon-doc-builder` alongside this skill -
`claude plugin install solomon-doc-builder@useful-claude-add-ons` - and every document
this skill produces is Solomon-branded from then on, with no flag and no question asked.
There is no single install that brings both (`.claude-plugin/marketplace.json` has no
field for expressing that dependency - each skill is its own entry), so a Solomon operator
needs that one extra command once. It is the only extra step: after both are installed,
branding is automatic on every document, forever, on this machine.

**Don't want branded output, or got navy-and-red documents you didn't ask for?**
Pass `--brand neutral` on any script, or set `DOC_BUILDER_BRAND=neutral` in the
environment for every run without repeating the flag. Either always wins over
whatever is installed - it is the off switch, and it needs no Python or config file
to find.

**Have more than one brand pack installed (an agency with several clients' packs on
one machine)?** Pass `--brand <name>` to say which one this document is for. With no
`--brand` and more than one pack found, every script refuses and names the packs
rather than guessing - guessing puts one client's footer on another client's report.

Every script resolves its brand the same way and prints the result to stderr:

1. `--brand <name>` always wins. `neutral` is the built-in pack.
2. `DOC_BUILDER_BRAND` in the environment.
3. Sibling skill directories (`skills/*/assets/brand.json`) - a git checkout.
4. The plugin cache - a marketplace install puts each plugin in its own versioned directory,
   so the search climbs from doc-builder's own location and also looks under
   `~/.claude/skills` and `~/.claude/plugins/cache`.
5. None found -> neutral, **announced with every location searched**. If the user expected
   branding and the line says neutral, read that list back to them - it is the diagnosis.

Exactly one pack -> the default for every document. Several different packs -> the scripts
stop and name them; **ask the user which brand the document is for**, do not guess - a guess
puts one client's footer on another's report.

```powershell
python resolve_brand.py            # what would be used, and why
python resolve_brand.py --list     # every pack visible from here
```

## Quick start

Run scripts from `scripts/` (they import each other as siblings), with absolute paths for
anything outside it.

**Report:**

```powershell
python build_report.py --example > report.json          # the JSON shape, filled in
python build_report.py --data report.json               # HTML into reports/ (gitignored)
python build_report.py --data report.json --to-docx --to-pdf
python build_report.py --data report.json --to-pdf --renderer libreoffice   # say it out loud
bash _test/checklist.sh                                 # greppable half of the pre-ship checklist
```

**Hand-authored HTML page** - the house style without the report's structure. The stylesheet
is the SAME one `build_report.py` emits, from the same module, so there is nothing to copy
and nothing that can drift:

```powershell
python house_style.py --profile guide                   # the CSS on stdout, for a new page
python house_style.py --brand solomon --profile guide   # the same, in a named brand
python house_style.py --apply page.html --out page.html --profile guide
python house_style.py --title-case "the powershell SOP"   # -> The PowerShell SOP
```

`--apply` replaces the page's `<style>` block and puts its `<title>` and every H1/H2/H3 into
house title case. It is idempotent, so re-running it after an edit is the way to keep a page
current - and re-running it under a different `--brand` is how one source page produces a
neutral and a branded variant. It is a restyle, not a rewrite: body copy is untouched.

`title_case` preserves any token that already carries its own capitalisation - PowerShell,
SOP, macOS, EF Core, `0.19.93` - which `str.title()` destroys. A name that is all lower case
with no interior capital, no digit and no dot (`doc-builder`) cannot be told from prose by
any rule and needs an entry in `house_style.PRESERVE_TOKENS`.

**SOP:**

```powershell
python build_sop.py my-sop.json --dry-run               # validates the spec, names the output, writes nothing
python build_sop.py my-sop.json --to-pdf                # .docx (+ backup of any previous master) and .pdf
python check_conformance.py "C:\masters\My SOP.docx" -v # GATE 1: structure against the brand
python verify_borders.py   "C:\masters\My SOP.pdf"  -v  # GATE 2: borders actually painted
```

Self-test for the SOP path, any brand, after changing the generator or a brand pack:

```powershell
python build_sop.py ..\assets\fixtures\selftest.json --out $env:TEMP\selftest.docx --to-pdf
python check_conformance.py $env:TEMP\selftest.docx -v
python verify_borders.py $env:TEMP\selftest.pdf -v
```

```bash
python3 build_sop.py ../assets/fixtures/selftest.json --out /tmp/selftest.docx --to-pdf
python3 check_conformance.py /tmp/selftest.docx -v     # Gate 1 - needs no renderer
python3 verify_borders.py /tmp/selftest.pdf -v         # reports UNAVAILABLE off Windows; see below
```

## Both gates, every SOP change, however small

Gate 1 reads the `.docx` and cannot see layout. Gate 2 renders the PDF at 300 dpi and
measures red-pixel coverage on all four edges of every screenshot. **Looking at a render is
not Gate 2** - a 0.75 pt border is sub-pixel at 100 dpi. A clipped border shipped for four
months because it was eyeballed instead of measured.

**Gate 2 has three outcomes, and the third one is why it can be trusted.** The question it
asks is *does Word clip this border* - the defect is Word stroking the outline outside
`wp:extent`. A PDF that Word did not render cannot answer it in either direction, so
`verify_borders.py` reports such a PDF as **UNAVAILABLE** and exits 3:

| Outcome | Means | Exit |
|---|---|---|
| `PASS` | Word rendered it, every border painted | 0 |
| `FAIL` | Word rendered it, at least one edge missing | 1 |
| `UNAVAILABLE` | **Gate 2 did not run** - Word did not render this PDF, what did could not be determined, or the matching `.docx` cross-check could not be read | 3 |
| `ERROR` | a PDF could not be read at all | 2 |

Every outcome a run produced prints its own `Gate 2 result:` line; the exit code carries the
sharpest one, FAIL first. A run with a genuine border failure *and* an unreadable PDF exits 1.

An `UNAVAILABLE` run still prints the pixel measurement, labelled **ADVISORY**. That number
describes how *this* renderer laid the picture out. It is not a Gate 2 result and must never
be recorded, summarised or reported onward as a pass. On a machine with no Word - any Linux
or macOS machine, permanently - `UNAVAILABLE` is the *only* answer Gate 2 can give, and the
honest thing to say is "Gate 1 passed, Gate 2 could not run here", never "both gates passed".
The renderer is read from the PDF's own `Producer`; a `.docx` cannot be used for this, because
`python-docx` writes `<Application>Microsoft Office Word</Application>` into `docProps/app.xml`
whatever built it.

Then open the PDF and check
pagination: an orphaned heading or a stranded closing section is invisible to both gates;
fix it by adjusting `width_in` and tightening wording.

Small edits are where this fails. A one-word caption fix reflows the page, and reflow is
what clips a border. Run the gates anyway.

## Reference map

| For | Read |
|---|---|
| CSS Word silently drops, what LibreOffice drops instead, column sizing, print rules, the Word-object-model verification snippet, pre-ship checklist | `references/word-traps.md` - **before writing any report CSS** |
| Report palette tokens, severity colours, how a brand pack overrides them | `references/palette.md` |
| SOP house template: page setup, per-block formatting, the border clipping defect and its real fix | `references/template-spec.md` |
| Every script, spec JSON format, `SopBuilder` API, brand.json schema | `references/toolchain-usage.md` |
| Screenshot anonymisation and provenance checks | `references/screenshots.md` - **before embedding any screenshot** |

## Worked examples

**"Write this up for management"** (a table of findings) -> report path. Decide the tier
first: concise by default - one-paragraph lede stating the single most important finding,
at most five cards, one findings table (ID, title, status, severity, count). If the detail
matters, write a second `<Name>-Detail-<timestamp>` document rather than inflating the
first. Put the data in the JSON shape from `--example`, build, convert, open the PDF (not a
browser preview), run `checklist.sh`.

**"Document how to set up the VPN"** with screenshots -> SOP path. Write the spec (`para`,
`heading`, `step`, `bullet`, `image`, `tip` blocks; `**bold**` for UI labels;
`[label](url)` for links). Anonymise every screenshot per `references/screenshots.md`.
`--dry-run`, then build with `--to-pdf`, then both gates.

**"Fix the wording in step 3 of the Teams guide"** -> if the master has a spec in the brand
pack's specs directory, edit the spec and rebuild; if not, run `extract_spec.py` on the
master first (it refuses to overwrite and logs everything it cannot express), then edit and
rebuild. Either way, both gates.

**"The PDF came out black-on-white"** -> `references/word-traps.md`. It is one of five
silent failures: `var()`, `:nth-child`, two class names on one element, flex/grid, or a
coloured `<div>` where a shaded table cell was needed.

## Where output goes

| Kind | Location | Why |
|---|---|---|
| Reports | `reports/` at the repo root, `<ReportName>-<yyyyMMddHHmmss>-<rand>.<ext>` | Dated point-in-time output about named accounts and weaknesses. **Gitignored** - add the rule in the same change that adds the first report script. Not `docs/`. |
| SOPs | `--out`, else the spec's `output`, else `<title>.docx` in the brand pack's `masters_dir` | Documentation someone maintains. The neutral pack has no masters directory, so name the path. |

The organisation on a report masthead is the **subject** (tenant, domain) from the data;
the brand pack's organisation is only a fallback. A report identifies its own subject.

## Safety rails

- `build_sop.py --dry-run` validates the spec and prints the output path, existence and
  backup location, and writes nothing. Use it first on any production master.
- Overwriting an existing `.docx` always copies the previous one to
  `_backup_<yyyymmdd>/` beside it first. `fix_effect_extent.py` does the same.
- A brand pack's `masters_dir` is never created. If it is missing, the script stops and
  names `DOC_BUILDER_MASTERS_DIR` - a missing production directory is the wrong machine.
- `extract_spec.py` refuses to overwrite an existing spec or asset without `--force`.
- Never commit `reports/`. Never commit real screenshots before the anonymisation audit.
- Colour never carries meaning alone: every severity chip carries its word, and
  `unverified` is its own severity - a check that could not run is not a check that passed.
- Word COM: the converter closes the document and quits Word in a `finally`; if a
  conversion fails, check `tasklist` for a stray `WINWORD` before retrying.
- LibreOffice: each conversion runs headless against a throwaway user profile, so it cannot
  block on (or corrupt) a desktop LibreOffice session the user has open. `soffice` exits 0
  on failures it does not consider fatal, so the exit code is not the check - every target
  is confirmed to exist, be non-empty and be newer than the moment the conversion started.

## Traps

| Trap | Reality |
|---|---|
| Raising the top margin fixes clipped screenshot borders | False. It only reflows pages. The cause is a missing `wp:effectExtent`; the generator writes it, `fix_effect_extent.py` patches old masters. |
| `add_picture()` gives a bordered image | It writes neither `a:ln` nor `effectExtent`. Never hand-roll a picture. |
| Cloning a master inherits its style | The masters use zero named Word styles; everything is direct run formatting. Use the generator. |
| The accent colour and the border colour are the same | Two different values in every pack (`sop.accent` vs `sop.image_border`). |
| A browser preview proves the report CSS | Only the Word object model does - see the snippet in `word-traps.md`. |
| Bash heredocs handle Windows paths | They collapse backslashes; use the Write tool or forward slashes. |
| Word overwrites a locked PDF | If the target `.pdf` is open in a viewer, `--to-pdf` fails read-only. Close it. |
| A LibreOffice render proves the document | It proves the document renders *in LibreOffice*. Gate 2 says `UNAVAILABLE` on it, and that is the honest answer, not a formality to work around. |
| `docProps/app.xml` says who built a `.docx` | Not on the SOP path. `python-docx` writes `<Application>Microsoft Office Word</Application>` into every file it makes. Read the PDF's `Producer`, or the `[renderer: ...]` doc-builder printed. |
| A conversion that exits 0 produced a file | `soffice` exits 0 with a locked profile and writes nothing. **Both** engines re-check existence, size and mtime through `render_engine.conversion_problem` — `to_soffice` after each convert, `build_report.to_word` after each `SaveAs2`. Do not bypass either by shelling out to `soffice` or driving Word COM directly. |
| Gate 2 cannot skip itself | It cannot skip itself **by accident**. Whether Word rendered the PDF is read from the PDF's own `/Producer`, which a text editor changes in one byte. The check catches converting with the wrong engine and forgetting; it does not stop an operator routing around their own gate. |
| A PDF with no matching `.docx` can still pass Gate 2 | No. The `.docx` count is what catches a screenshot that lost **all four** edges — with no ink it reads as an unbordered decorative image. No `.docx`, a corrupt one, or no python-docx means `UNAVAILABLE`, exit 3. |
| LibreOffice just reformats the file you hand it | Its HTML and OOXML importers resolve external references — a remote `<img>` is fetched during conversion. `to_soffice` seeds its throwaway profile to block that (measured: a loopback beacon is hit without it and not with it). It restricts the network, not the local filesystem. |
