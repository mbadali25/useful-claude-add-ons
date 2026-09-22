# Toolchain usage

Every script lives in `scripts/` and imports its siblings by plain module name
(`import resolve_brand`, `import build_sop as S`), not as a package. **Run them from inside
`scripts/`**, or put that directory on `PYTHONPATH`. Paths to documents, specs and images
outside it should be absolute.

| File | What it is | Needs |
|---|---|---|
| `preflight.py` | Detects missing packages, installs them `--user` (or into `../.venv`) after one confirmation, verifies by re-import in a fresh interpreter; reports which RENDERERS exist, which one this machine will use, whether Gate 2 is available, and locked output files. **Run first on any new machine.** | stdlib |
| `../requirements.txt` | The same package set, declared. `python -m pip install --user -r requirements.txt` | |
| `resolve_brand.py` | Decides the brand pack and every path derived from it. Everything else imports it. | stdlib |
| `render_engine.py` | Which program converts, and the words that say so. `--renderer`, the platform branch, the LibreOffice conversion, and the PDF-`Producer` read that gives Gate 2 its third value. | stdlib |
| `build_report.py` | Report path: JSON → HTML that survives Word's parser → `.docx`/`.pdf` via Word COM **or** LibreOffice. | stdlib; `pywin32` only for `--renderer word` |
| `build_sop.py` | SOP path: JSON spec (or `SopBuilder` API) → house-template `.docx`, optional `.pdf`. | `python-docx`; a renderer for `--to-pdf` (`pywin32`+Word, or `soffice`) |
| `check_conformance.py` | **Gate 1** — structural validator, the executable form of `template-spec.md`, against the active brand. Non-zero exit on failure. | `python-docx` |
| `verify_borders.py` | **Gate 2** — renders each PDF at 300 dpi and measures whether every screenshot border actually painted. Three outcomes: PASS / FAIL / **UNAVAILABLE** when Word did not render the PDF. | `PyMuPDF`, `numpy`, `Pillow`, `python-docx` |
| `fix_effect_extent.py` | Repair: patches `wp:effectExtent` into masters that predate the generator. Backs up first; `--dry-run`. | `python-docx` |
| `extract_spec.py` | Reverse-engineers a JSON spec (and pulls the screenshots) from an existing master so it can be rebuilt. Logs everything it cannot express. | `python-docx` |
| `make_template.py` | Regenerates a brand pack's `sop_template.docx` from a conforming master. Rarely. | `python-docx` |
| `_test/checklist.sh` | Runs the greppable half of `word-traps.md`'s checklist against a report the builder actually emitted. | bash, python |
| `_test/test_render_engine.py` | The renderer is chosen, never fallen back into; Gate 2 reports UNAVAILABLE rather than PASS on a PDF Word did not render. Stubs `pymupdf`, so it runs on a host with no PDF library. | pytest |
| `../assets/brands/neutral/brand.json` | The neutral pack and the full schema. | |
| `../assets/fixtures/selftest.json` + `.png` | One-page spec exercising every SOP block type, portable to any brand. | |

## Preflight

```powershell
python preflight.py                      # report; asks once before any install
python preflight.py --install            # install missing packages, pip --user, no prompt
python preflight.py --venv               # ...into <skill>\.venv; then run scripts with that interpreter
python preflight.py --target "C:\masters\My SOP.pdf" --target "C:\masters\My SOP.docx"
```

Exit 0 = **the toolchain is provisioned**. 3 = packages missing and not installed (the exact
`pip install --user` command is printed). 2 = an install or post-install import failed (pip's
own output is above it, verbatim; nothing is retried). 1 = the chosen renderer is
unavailable, or a target is locked.

**Exit 0 does not mean Gate 2 passed, and on Linux and macOS it never can.** Word over COM
exists only on Windows, so `word_installed()` is permanently False elsewhere; a fully
provisioned Linux host with LibreOffice and every package installed exits 0 and prints a
closing line that says Gate 2 is UNAVAILABLE in words the exit code cannot carry. Until
2026-09-22 that host exited **1** and printed "Not ready", which made exit 0 unreachable on
the platform this skill's LibreOffice path was written for — an exit code no run can produce
carries no information. Word absent on *Windows* is a different thing: it is fixable, so it
is still exit 1.

Gate 2 needs **Word and the packages `verify_borders.py` imports** — PyMuPDF, numpy and
Pillow, without any one of which it dies at its own import line, and python-docx, without
which its `.docx` cross-check cannot run. The preflight reports `AVAILABLE` only when all of
them are present; it used to report it on the strength of Word alone, while the section six
lines above printed `MISSING PyMuPDF`.

## Renderer resolution - chosen, never fallen back into

Two programs can turn a source document into `.docx`/`.pdf`:

| Engine | What it is | Where |
|---|---|---|
| `word` | Microsoft Word over COM (`pywin32`). The **reference** renderer; every rule in `word-traps.md` was measured against it. | Windows, with Word installed |
| `libreoffice` | `soffice --headless --convert-to`, no Python package needed. | Anywhere LibreOffice is installed - and the **only** engine on Linux or macOS, because Microsoft ships no Word desktop app for Linux |

Order, on `build_report.py` and `build_sop.py` alike:

1. `--renderer word|libreoffice` always wins.
2. Otherwise an **explicit platform branch**: Word on Windows, LibreOffice elsewhere.

Both scripts print `renderer : <engine> -- <why>` to stderr before converting anything, and
append `  [renderer: ...]` to the line announcing every file written. If the chosen engine
cannot run, the script **stops and names the flag that selects the other one**. It does not
try the other one. The earlier rule - "never fall back to pandoc or LibreOffice" - was about
the *silent, unlabelled* substitution, and that part still holds exactly as written: a
document the reader believes Word made, which Word did not make, is the failure. Labelling
is what makes the other engine usable at all.

```bash
python3 render_engine.py                     # which engine this machine would use, and why
python3 render_engine.py some.pdf            # what actually rendered an existing PDF
python3 build_report.py --data r.json --to-pdf --renderer libreoffice
```

The second form's exit code is an answer, not a formality: **0** every named PDF was read and
its producer determined, **2** a named PDF could not be read, **3** a named PDF was read and
its producer could not be determined. It returned 0 unconditionally until 2026-09-22, so
`render_engine.py /nonexistent.pdf && something` ran `something`.

**LibreOffice is run restricted.** `to_soffice` seeds its throwaway user profile before
soffice starts — macro execution off, macro security Very High, active content off, untrusted
referer links blocked — because the HTML and OOXML importers resolve external references by
design. Measured 2026-09-22 on LibreOffice 26.2.5.2: an HTML carrying
`<img src="http://127.0.0.1:PORT/beacon.png">` hits that server on an unseeded profile and
does not on a seeded one. `--safe-mode` is deliberately not passed; it discards the profile
the settings live in. This restricts the network, not the local filesystem.

`render_engine.pdf_producer` reads a PDF's `/Producer` with the stdlib alone (literal and
UTF-16 hex strings both), so the question "what rendered this?" can be answered on a machine
with no PDF library. When it cannot be read the answer is `unknown`, which is **not** `word`
- see Gate 2's third outcome below. A `.docx` cannot answer it at all: `python-docx` writes
`<Application>Microsoft Office Word</Application>` into `docProps/app.xml` whatever built the
file.

Fidelity through LibreOffice is reduced and measured - see "What LibreOffice silently drops"
in `word-traps.md`.

## Brand resolution

```powershell
python resolve_brand.py                  # which pack, and why
python resolve_brand.py --list           # every pack visible from skills/
python resolve_brand.py --brand neutral --json
```

Order: `--brand` → `DOC_BUILDER_BRAND` → sibling skill directories (a git checkout) → the
plugin cache (a marketplace install puts each plugin in its own versioned directory, so
siblings find nothing there; the search climbs from doc-builder's own location and also
looks under `~/.claude/skills` and `~/.claude/plugins/cache`) → neutral, **announced with
every location searched**. Several different packs at one location → the scripts stop and
name them. The same pack in several versions → the most recently modified copy, printed.
Every script prints `brand: <name> -- <reason> (<path>)` to stderr; `--list` shows every
location and what it holds.

Environment overrides:

| Variable | Effect |
|---|---|
| `DOC_BUILDER_BRAND` | Same as `--brand` |
| `DOC_BUILDER_MASTERS_DIR` | Replaces the pack's `sop.masters_dir` (e.g. the masters are checked out somewhere else on this machine) |
| `DOC_BUILDER_SKILLS_DIR` | Where to scan for packs. Testing only. |

## brand.json schema

Any key may be omitted; it inherits from the neutral pack. Relative paths are relative to
the pack's `assets/` directory.

```json
{
  "name": "acme",
  "organisation": "Acme Corporation",
  "fonts": { "body": "Calibri", "heading": "Calibri", "report_stack": "'Segoe UI',Calibri,Arial,sans-serif" },
  "report": { "navy": "#1F4E79", "accent": "#4A90C2", "...": "see palette.md", "output_dir": "reports" },
  "sop": {
    "accent": "1F4E79", "image_border": "FF0000", "heading": "1F4E79", "title": "404040",
    "caption": "7F7F7F", "body": "000000", "link": "0563C1",
    "title_pt": 20.0, "subtitle_pt": 12.0, "heading_pt": 13.5, "caption_pt": 9.5,
    "margins_in": { "top": 0.8, "bottom": 0.6, "left": 0.5, "right": 0.5 },
    "template": "sop_template.docx",
    "masters_dir": "C:\\path\\to\\masters",
    "assets_dir": "C:\\path\\to\\screenshots",
    "specs_dir": "specs",
    "footer": { "left": "...", "centre": "...", "required_text": ["..."], "optional_text": ["..."] },
    "help_contact": "servicedesk@example.com"
  },
  "screenshots": { "stand_in_email": "firstname.lastname@example.com", "stand_in_user": "user" }
}
```

`template: null` makes `build_sop.py` synthesise a blank document from `margins_in`,
`fonts.body` and `footer` — the neutral pack works this way. `masters_dir: null` means
every SOP build needs `--out` or a spec `output`.

## Build a report

```powershell
cd <skill>\scripts
python build_report.py --example > report.json          # fill this in; it is the whole input
python build_report.py --data report.json               # -> reports/<Title>-<stamp>.html
python build_report.py --data report.json --to-docx --to-pdf
python build_report.py --data report.json --brand neutral --out C:\tmp\r
bash _test/checklist.sh                                 # 16 checks; exit 0 = pass
```

The JSON carries `organisation` (the assessed subject), `title`, `subtitle`,
`classification`, `meta` (label/value pairs), `lede`, `handling`, `cards` (≤5),
`findings.columns` + `findings.rows`, `footer`, and optionally `collected_at`. A report
that talked to a live system writes this JSON alongside the HTML so it can be restyled
later without contacting the system again; when it is, `collected_at` makes the rendered
document say so.

## Build a SOP

```powershell
cd <skill>\scripts

# 1. author or edit a spec (format below)
# 2. see what would happen
python build_sop.py C:\specs\my-sop.json --dry-run
# 3. build the .docx (previous master backed up to _backup_<yyyymmdd>\) and the .pdf
python build_sop.py C:\specs\my-sop.json --to-pdf
# 4. GATE 1
python check_conformance.py "C:\masters\My SOP.docx" -v
# 5. GATE 2
python verify_borders.py "C:\masters\My SOP.pdf" -v
```

**Both gates are required.** Gate 1 reads the `.docx` and cannot see layout; Gate 2 reads
the rendered PDF and catches what the eye misses. A SOP that passes only one is not
finished. Check a whole set at once with no arguments: both gates default to every file in
the brand's `masters_dir`.

**Gate 2 has a third outcome.** It asks whether *Word* clips the screenshot border, so it
can only answer on a Word-rendered PDF. Given anything else — a LibreOffice render, or a PDF
whose `Producer` cannot be read — it prints `UNAVL`, a one-line explanation, an `ADVISORY`
measurement of the render it was handed, and `Gate 2 result: UNAVAILABLE`, then exits 3.
That advisory number is about the renderer that made the file; it is not a Gate 2 result and
must not be reported as one. **The second way it can fail to run** is the `.docx` cross-check:
without the matching `.docx` — absent, corrupt, or python-docx not installed — nothing can
tell a screenshot that lost all four edges from a decorative image that never had a border,
so that is `UNAVAILABLE` too, not `PASS`.

Every outcome a run produced prints its own `Gate 2 result:` line, and the exit code carries
the sharpest: **1** FAIL, then **2** a PDF that could not be read, then **3** at least one
UNAVAILABLE, else **0**. A genuine border failure alongside one unreadable PDF exits 1, not 2
— it was 2 briefly, and any run that errored at all used to suppress the UNAVAILABLE line
entirely.

**What Gate 2 does not enforce:** which program rendered the PDF is read from the PDF's own
`/Producer`, one byte from saying anything. The check defeats *accident*, not an operator
routing around their own gate.

### Self-test

```powershell
python build_sop.py ..\assets\fixtures\selftest.json --out $env:TEMP\selftest.docx --to-pdf
python check_conformance.py $env:TEMP\selftest.docx -v
python verify_borders.py $env:TEMP\selftest.pdf -v
```

```bash
python3 build_sop.py ../assets/fixtures/selftest.json --out /tmp/selftest.docx --to-pdf
python3 check_conformance.py /tmp/selftest.docx -v
python3 verify_borders.py /tmp/selftest.pdf -v
```

One page, every block type, should PASS both gates under any brand
(`--brand neutral` on all three to test the synthesised template). Run it after changing
the generator, the checker or a brand pack.

On a machine with no Word the expected result is **Gate 1 PASS, Gate 2 UNAVAILABLE (exit
3)** — that is the self-test passing as far as it can here, not a failure to investigate
and not a pass to report.

### Spec format

```json
{
  "title": "Quick Reference Guide for Archiving Emails",
  "subtitle": "M365 Outlook archiving",
  "output": "../masters/My SOP.docx",
  "body": [
    { "type": "para",    "text": "Intro. **Bold** spans and [links](https://example.com)." },
    { "type": "heading", "text": "Section heading" },
    { "type": "step",    "text": "Click **File**." },
    { "type": "bullet",  "text": "A bullet." },
    { "type": "image",   "path": "../assets/slug/shot.png",
                         "width_in": 6.28,
                         "caption": "What the reader should notice." },
    { "type": "tip",     "text": "Tip: a bold call-out line." }
  ]
}
```

- Paths are relative to the spec file. `output` is optional: without it and without
  `--out`, the document goes to `<masters_dir>\<title>.docx`.
- `step` numbers auto-increment and **reset at each `heading`**; override with `"number": 3`.
- `"keep_with_next": true` on a `heading` emits `w:keepNext` so it cannot land alone at the foot
  of a page. **Opt-in, off by default** - the measured masters carry no keepNext, so it is for
  text-only documents that have no `width_in` to reflow with. Both gates are blind to
  pagination; render and look.
- `width_in` is optional — images otherwise scale down to fit 7.5" × 6.5", never up.
- Screenshot borders, the accent bar, indents and spacing are applied automatically.
- A malformed `[label](url` is reported on stderr and rendered as literal text; the build
  still succeeds so one typo cannot block a whole document.

### `SopBuilder` API

```python
import resolve_brand
from build_sop import SopBuilder
b = SopBuilder("Title", "Subtitle", brand=resolve_brand.resolve())
b.para("..."); b.heading("..."); b.step("..."); b.bullet("..."); b.tip("...")
b.image(r"C:\shots\one.png", caption="...", width_in=5.5)
b.save(r"C:\masters\Title.docx")
```

## Editing an existing SOP

If the master has a spec in the brand's `specs_dir`, edit the spec and rebuild — Gate 1
also diffs master against spec and fails when they disagree, so a hand-edit that leaves the
spec lying is caught. If it has no spec, extract one first:

```powershell
python extract_spec.py "C:\masters\Some SOP.docx"                 # -> <specs_dir>\some-sop.json + <assets_dir>\some-sop\
python extract_spec.py "C:\masters\Some SOP.docx" --out C:\tmp\s.json --assets-out C:\tmp\s-assets
python extract_spec.py --report                                     # extractability of the whole set
```

It refuses to overwrite without `--force`, and records everything the spec format cannot
express (italic runs, floating images, crops, unresolved links) in the spec's own
`_warnings` array rather than dropping it silently. Read that array before trusting the
rebuild.

Small wording fixes are still faster in Word directly. **Then run both gates anyway.** A
one-word caption fix reflows the page, and reflow is what clips a screenshot border.

## Repairing old masters

```powershell
python fix_effect_extent.py --dry-run               # what would change, in the brand's masters_dir
python fix_effect_extent.py                         # patch; originals to _backup_effectextent_<yyyymmdd>\
python fix_effect_extent.py --dir C:\other\masters --name "*VPN*"
```

Additive only: it adds or widens `wp:effectExtent` on inline shapes that carry an outline
and touches nothing else. Rebuild the PDFs and run Gate 2 afterwards.

## Regenerating a brand template

```powershell
python make_template.py --reference "C:\masters\Canonical SOP.docx"            # -> the active pack's sop.template
python make_template.py --reference "..." --output "C:\repos\x\skills\acme-doc-builder\assets\sop_template.docx"
```

Only when the footer, margins or base font change. It strips the body and the image parts
from the reference and keeps the section properties, `Normal` style and footer.
