---
name: doc-builder
description: >
  Build finished, human-facing documents as DOCX and PDF through Microsoft Word, in the
  installed brand pack's house style or a neutral one. Two pipelines behind one skill:
  findings-style reports (assessment, audit write-up, findings document, executive summary,
  posture or security report - masthead, plain-language lede, summary cards, severity chips,
  provenance footer) rendered from HTML through Word COM; and step-by-step procedures (SOP,
  standard operating procedure, runbook, work instruction, how-to, quick reference guide,
  training guide, onboarding guide for a new hire, user guide, walkthrough - anything that
  tells someone how to set up, install, configure or sign in to something, step by step,
  with screenshots) rendered with python-docx so every screenshot carries a border Word does
  not clip. Use this skill whenever the user asks for a report, an SOP, a runbook, a how-to,
  a guide, instructions with screenshots, documentation of a process, or says "write this
  up", "make it look professional", "send this to the client", "document this process",
  "make a PDF", "turn this into a Word doc", "add a screenshot to the guide", "update the
  VPN guide", "does this SOP match the template", or when a generated DOCX or PDF came out
  unstyled black-on-white. Also use it
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
| Findings, tables, severity, executive summary, audit or assessment write-up | HTML -> Word COM | `scripts/build_report.py` |
| Step-by-step procedure with screenshots (SOP, runbook, how-to, guide) | python-docx OOXML | `scripts/build_sop.py` |

Why two: Word's HTML parser is the constraint on the report side, and every rule in
`references/word-traps.md` was measured against it. On the SOP side, `add_picture()` writes
neither `a:ln` nor `wp:effectExtent`, so Word strokes a screenshot border *outside*
`wp:extent` and clips it at page top. The HTML path cannot produce a bordered screenshot at
all; the OOXML path writes both elements. A procedure with no screenshots may still use the
SOP path - it is the house template for procedures.

## Disambiguation

| The user wants | Use |
|---|---|
| A report, SOP, runbook, guide or write-up produced as DOCX/PDF | this skill |
| Solomon styling on any of those | this skill, with `solomon-doc-builder` also installed - see "Brand resolution" below for the install command, the opt-out, and choosing between packs |
| To edit, extract from or find-and-replace in a `.docx` they already have | the `docx` skill (`anthropic-office-skills:docx`) |
| A slide deck or spreadsheet | `pptx` / `xlsx` skills |
| Only to know what the house style is, without producing a document | `crew:crew-house-style` |

`report-builder` and `solomon-sop-maker` are deprecated stubs that redirect here.

## Requirements - run the preflight first, on every new machine

```powershell
cd <skill>\scripts
python preflight.py                     # reports; asks once before installing anything
python preflight.py --install           # same, without the prompt
python preflight.py --venv              # install into <skill>\.venv instead of --user
```

It detects each package below by importing it in a fresh interpreter, installs what is
missing with **`python -m pip install --user`** (or into a virtual environment this skill
owns), and then re-imports each one and prints its version. **Never a bare `pip install`**
- on a managed workstation that writes somewhere the operator cannot elevate into or
cannot import from. If pip fails, the preflight prints pip's output verbatim and stops:
no retry, no machine-wide fallback. `requirements.txt` declares the same set.

| Package | For |
|---|---|
| `python-docx` | `build_sop.py`, `check_conformance.py`, `fix_effect_extent.py`, `extract_spec.py`, `make_template.py` |
| `pywin32` | `--to-docx` / `--to-pdf` through Word COM |
| `PyMuPDF`, `numpy`, `Pillow` | `verify_borders.py` (Gate 2); Pillow also for screenshot anonymisation |

Two things the preflight can only **report**, because pip cannot fix them:

- **Microsoft Word** (Windows, COM). Absent means no `--to-docx`/`--to-pdf` and therefore
  no Gate 2. HTML and `.docx` are still produced. **Say which pipeline is unavailable;
  never fall back** to pandoc or LibreOffice, which are not assumed to exist.
- **A locked output file.** A PDF open in a viewer or a DOCX open in Word makes Word fail
  "read-only". `preflight.py --target <file>` and the converter itself name the file to
  close.

`build_report.py`, `resolve_brand.py` and `preflight.py` are stdlib.

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
bash _test/checklist.sh                                 # greppable half of the pre-ship checklist
```

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

## Both gates, every SOP change, however small

Gate 1 reads the `.docx` and cannot see layout. Gate 2 renders the PDF at 300 dpi and
measures red-pixel coverage on all four edges of every screenshot. **Looking at a render is
not Gate 2** - a 0.75 pt border is sub-pixel at 100 dpi. A clipped border shipped for four
months because it was eyeballed instead of measured. Then open the PDF and check
pagination: an orphaned heading or a stranded closing section is invisible to both gates;
fix it by adjusting `width_in` and tightening wording.

Small edits are where this fails. A one-word caption fix reflows the page, and reflow is
what clips a border. Run the gates anyway.

## Reference map

| For | Read |
|---|---|
| CSS Word silently drops, column sizing, print rules, the Word-object-model verification snippet, pre-ship checklist | `references/word-traps.md` - **before writing any report CSS** |
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
