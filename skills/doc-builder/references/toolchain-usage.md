# Toolchain usage

Every script lives in `scripts/` and imports its siblings by plain module name
(`import resolve_brand`, `import build_sop as S`), not as a package. **Run them from inside
`scripts/`**, or put that directory on `PYTHONPATH`. Paths to documents, specs and images
outside it should be absolute.

| File | What it is | Needs |
|---|---|---|
| `preflight.py` | Detects missing packages, installs them `--user` (or into `../.venv`) after one confirmation, verifies by re-import in a fresh interpreter; reports Word presence and locked output files. **Run first on any new machine.** | stdlib |
| `../requirements.txt` | The same package set, declared. `python -m pip install --user -r requirements.txt` | |
| `resolve_brand.py` | Decides the brand pack and every path derived from it. Everything else imports it. | stdlib |
| `build_report.py` | Report path: JSON → HTML that survives Word's parser → `.docx`/`.pdf` via Word COM. | stdlib; `pywin32` for conversion |
| `build_sop.py` | SOP path: JSON spec (or `SopBuilder` API) → house-template `.docx`, optional `.pdf`. | `python-docx`; `pywin32` for `--to-pdf` |
| `check_conformance.py` | **Gate 1** — structural validator, the executable form of `template-spec.md`, against the active brand. Non-zero exit on failure. | `python-docx` |
| `verify_borders.py` | **Gate 2** — renders each PDF at 300 dpi and measures whether every screenshot border actually painted. | `PyMuPDF`, `numpy`, `Pillow`, `python-docx` |
| `fix_effect_extent.py` | Repair: patches `wp:effectExtent` into masters that predate the generator. Backs up first; `--dry-run`. | `python-docx` |
| `extract_spec.py` | Reverse-engineers a JSON spec (and pulls the screenshots) from an existing master so it can be rebuilt. Logs everything it cannot express. | `python-docx` |
| `make_template.py` | Regenerates a brand pack's `sop_template.docx` from a conforming master. Rarely. | `python-docx` |
| `_test/checklist.sh` | Runs the greppable half of `word-traps.md`'s checklist against a report the builder actually emitted. | bash, python |
| `../assets/brands/neutral/brand.json` | The neutral pack and the full schema. | |
| `../assets/fixtures/selftest.json` + `.png` | One-page spec exercising every SOP block type, portable to any brand. | |

## Preflight

```powershell
python preflight.py                      # report; asks once before any install
python preflight.py --install            # install missing packages, pip --user, no prompt
python preflight.py --venv               # ...into <skill>\.venv; then run scripts with that interpreter
python preflight.py --target "C:\masters\My SOP.pdf" --target "C:\masters\My SOP.docx"
```

Exit 0 = ready. 3 = packages missing and not installed (the exact `pip install --user`
command is printed). 2 = an install or post-install import failed (pip's own output is
above it, verbatim; nothing is retried). 1 = Word absent or a target locked. Word absent
means `--to-docx`/`--to-pdf` and Gate 2 are unavailable on that machine; the HTML and
`.docx` still build and can be converted elsewhere.

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

### Self-test

```powershell
python build_sop.py ..\assets\fixtures\selftest.json --out $env:TEMP\selftest.docx --to-pdf
python check_conformance.py $env:TEMP\selftest.docx -v
python verify_borders.py $env:TEMP\selftest.pdf -v
```

One page, every block type, should PASS both gates under any brand
(`--brand neutral` on all three to test the synthesised template). Run it after changing
the generator, the checker or a brand pack.

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
