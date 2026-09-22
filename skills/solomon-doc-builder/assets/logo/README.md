# Solomon logo assets

Committed here so a document build depends on this style pack and nothing else.
Before this directory existed the only copy lived in a separate checkout
(`.../infra-management-tool/frontend/public/solomon-logo.png`), which meant a
build on any other machine silently had no logo.

## Which file

| File | Put it on |
|---|---|
| `solomon-logo-on-light.png` | white or pale pages — body, report covers, DOCX headers |
| `solomon-logo-on-dark.png` | navy `#0E2841` or any dark band |
| `solomon-icon-on-light.png` | the mark alone, pale background — favicons, bullets, small marks |
| `solomon-icon-on-dark.png` | the mark alone, dark background |
| `solomon-logo-source.png` | the original as received. Not for use — kept as the provenance record |

There is no single "transparent logo". The wordmark is white in the original,
so one cutout cannot serve both: dropped onto a white page it disappears
completely, and the failure is invisible in any viewer that renders PNG
transparency as white. That is why the wordmark is recoloured to the brand
navy in the `-on-light` pair rather than a single file being shipped.

## How they were made

The source is a flat composite: wordmark `#FFFFFF` and mark `#F0483E` over a
solid `#28282E` panel, with no alpha channel at all (`alpha 255-255` across
every pixel). So the background could not be *revealed*; it had to be solved
for. Each pixel was classified as mark or wordmark, then `C = a*F + (1-a)*B`
solved for `a` against that class's known foreground, which reconstructs the
anti-aliased edges instead of key-colour matting them into a dark fringe.

The mark keeps its measured `#F0483E`. Note this is one step off the
`report.accent` in `../brand.json`, which is `#EF483D`: the difference is real,
not a typo in either place, and the logo was left at its measured value rather
than nudged to match a palette entry it was never generated from.

Re-check rather than trusting this paragraph:

```
python3 -c "
from PIL import Image
im=Image.open('solomon-logo-on-light.png').convert('RGBA')
a=[p[3] for p in im.get_flattened_data()]
print('alpha', min(a), max(a))   # must be 0-255, not 255-255
"
```

An `alpha 255-255` result means the cutout was lost — most likely a tool
re-saved the file and flattened it onto a background.

## Not yet wired

Nothing reads these. `resolve_brand.py` has no logo concept, so a build cannot
ask the brand pack where its logo is; a document that wants one still has to
name the path. Wiring it is tracked as "Expose the committed Solomon logo to
the report/HTML pipeline".
