# Bitbucket Cloud: Markdown + SVG gotchas

Read this when a diagram looks right locally but wrong in Bitbucket, or when a README
won't render at all.

## Contents

1. Invisible labels (`<foreignObject>`)
2. Broken/blank images (`<image>` references)
3. README won't render at all (encoding)
4. Image paths
5. Sizing
6. Fonts
7. Dark mode, the harder way
8. Why not just use an extension

---

## 1. Invisible labels — `<foreignObject>`

**Symptom:** boxes and arrows render; every label is blank. Fine in a local viewer,
fine when you open the `.svg` in a browser tab directly, blank in the README.

**Cause:** Markdown images become `<img src="...svg">`. Browsers render SVG in an
`<img>` in a restricted mode — no scripts, no external fetches, and no foreign
content. Mermaid's default `htmlLabels: true` puts label text in `<foreignObject>`,
which holds HTML. It isn't painted, so the text is simply absent.

**Fix:** `htmlLabels: false` in the config, which produces `<text>` elements. Verify
with `grep -c foreignObject file.svg` — expect `0`.

**Caveat:** `<text>` has no line wrapping. Long labels that wrapped nicely with HTML
labels will run out of their box. Insert `<br/>` in the Mermaid source to break lines
manually — Mermaid honors it in `<text>` mode by emitting `<tspan>`s.

---

## 2. Broken/blank images — `<image>` references

**Symptom:** part of the diagram is a placeholder icon or empty box.

**Cause:** same sandbox. An `<img>`-loaded SVG cannot fetch anything external, so
`<image href="...">` pointing at a URL or a sibling file resolves to nothing. This is
the documented reason draw.io exports fail to render in Bitbucket unless "Embed
images" is checked — the export otherwise emits `<image>` elements with no content.

Mermaid doesn't normally emit these, but `imageAspectRatio`/icon features and
architecture diagrams with custom icons can. If you need an image inside a diagram,
base64-inline it as a data URI.

---

## 3. README won't render at all

**Symptom:** Bitbucket shows an error or nothing where the README should be. Nothing
to do with diagrams.

**Cause:** file encoding. Bitbucket returns HTTP 400 with "We cannot detect the file's
encoding; unable to render file" if the Markdown isn't something it recognizes —
typically latin-1 crept in via a smart quote or an accented name.

**Check and fix:**

```bash
file -I README.md          # want: charset=utf-8 (or us-ascii)
iconv -f iso-8859-1 -t utf-8 README.md > README.utf8 && mv README.utf8 README.md
```

Worth knowing because it looks like an image problem when you've just changed images.

---

## 4. Image paths

- Relative paths from the Markdown file's own directory work: `![x](docs/diagrams/x.svg)`
  in a root README, `![x](../diagrams/x.svg)` from `docs/runbooks/`.
- Do **not** use a leading `/`. Some renderers accept it; Bitbucket resolves it
  against the site root and 404s.
- Don't link the human-facing file page (`.../src/main/x.svg`) — that's an HTML page,
  not an image. Relative repo paths get rewritten to the raw URL automatically; typing
  a `src/` URL by hand does not.
- Private repos: relative paths are fine (the reader is already authenticated).
  Hotlinking raw URLs across repos is not — the `<img>` request may not carry
  credentials.
- Bitbucket has had intermittent outages where *all* README images stop rendering
  (e.g. March 2025). If images vanish repo-wide with no commit to explain it, check
  Bitbucket status before debugging your files.

---

## 5. Sizing

Bitbucket's Markdown gives you no way to set image dimensions — no width attribute, no
raw HTML `<img>` (it's stripped). The SVG's own intrinsic size is what you get.

So the SVG must carry `width` and `height` attributes. `mmdc` emits them; the render
script backfills them from the `viewBox` if they're missing, and strips Mermaid's
`style="max-width:..."`, which interacts badly with `<img>` layout.

Practical limit: keep diagrams under ~1200px wide. Wider ones get squeezed into the
README column and become unreadable. Split a sprawling diagram into several rather
than shrinking it — `flowchart LR` for pipelines, `TD` for hierarchies, and cut at
subgraph boundaries.

---

## 6. Fonts

Mermaid measures text in Chromium at render time to size nodes, but the reader's
browser paints it. Different font on either side → text overflows its box.

- Use a websafe stack: `Helvetica Neue, Helvetica, Arial, sans-serif`.
- In CI, install `fonts-liberation`. A slim container has no fonts at all, and
  Chromium falling back to a last-resort font produces mis-measured, overlapping
  nodes. Liberation Sans is metric-compatible with Arial.
- Belt-and-braces: convert text to paths (`mmdc` can't; needs `inkscape
  --export-text-to-path` or `svgo` plugins). Bulletproof, but the SVG grows, text is
  no longer selectable or searchable, and it's inaccessible to screen readers. Only
  worth it for a logo-grade diagram.

---

## 7. Dark mode, the harder way

The default (opaque white background, fixed light palette) always works. If someone
insists on theme-aware diagrams, the options in descending order of sanity:

1. **Two SVGs, one link.** Not possible — Bitbucket Markdown has no
   `<picture>`/`prefers-color-scheme` support and no HTML. GitHub's
   `#gh-dark-mode-only` trick has no Bitbucket equivalent. Dead end.

2. **CSS media query inside the SVG.** Embed
   `@media (prefers-color-scheme: dark) { ... }` in the SVG's `<style>`. This *does*
   evaluate in an `<img>` context in current browsers — but against the **OS**
   setting, not Bitbucket's theme preference. Light Bitbucket on a dark laptop → dark
   diagram on a white page. Only acceptable if the whole team runs OS and Bitbucket
   themes in lockstep.

3. **A neutral palette that reads on both.** Mid-tone strokes (`#6b778c`), no fill or
   a light fill with a strong border, text at a value that survives both backgrounds.
   Genuinely hard to get right and usually ends up looking washed out on both.

Recommend #3 only if they reject the white card, and set expectations.

---

## 8. Why not just use an extension

Browser extensions and Marketplace apps ("Mermaid Diagrams for Bitbucket", "File
Renderers for Bitbucket") render Mermaid client-side in the Bitbucket UI, with no
build step and no committed artifacts.

They're a real option, and cheaper than this whole pipeline. The catch:

- Every reader must install it. A README is often read by people outside the team —
  auditors, new hires, someone linked from a ticket. They see raw code.
- Marketplace apps need workspace-admin install and go through procurement/security
  review at most enterprises.
- Nothing renders in the raw file view or anything that consumes the repo
  programmatically.

Pre-rendered SVG works for everyone, forever, with no client state. That's usually why
someone reached for this skill. If their audience is genuinely just their own team and
an admin can install the app, say so — it's less machinery to maintain.
