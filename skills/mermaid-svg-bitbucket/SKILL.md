---
name: mermaid-svg-bitbucket
description: Pre-render Mermaid diagrams to committed SVG so they display in Bitbucket Cloud, which has never supported ```mermaid fenced blocks natively. Use this skill whenever someone mentions Mermaid, .mmd or .mermaid files, or diagrams-as-code in the context of Bitbucket — including "my diagram shows as raw code in Bitbucket", "the README renders on GitHub but not Bitbucket", "our diagram labels are invisible/blank", "add a docs diagram check to Pipelines", or any migration of docs from GitHub/GitLab to Bitbucket. Also use it when converting a single .mmd file to SVG, since the naive `mmdc -i x.mmd -o x.svg` produces an SVG whose text disappears in Bitbucket.
---

# Mermaid → SVG for Bitbucket Cloud

## The problem this solves

Bitbucket Cloud does not render Mermaid in Markdown. GitHub and GitLab do; Bitbucket
does not, and the request has sat open as [BCLOUD-21675](https://jira.atlassian.com/browse/BCLOUD-21675)
for years. A ```mermaid block in a Bitbucket README shows as raw source.

The workaround is to pre-render each diagram to an SVG, commit it, and reference it as
a normal Markdown image. The `.mmd` source stays in the repo as the thing you edit and
review; the SVG is a build product that happens to be committed.

There are browser extensions and Marketplace apps that render Mermaid in Bitbucket
client-side. Mention them as an option if it fits (they're less work), but they only
help people who install them — the diagram stays broken for everyone else, which is
usually why someone is asking for this in the first place.

## The one thing that will bite you

By default Mermaid puts label text inside `<foreignObject>` elements, which hold real
HTML. That works when Mermaid runs as JavaScript in a page. It does **not** work when
a browser loads the SVG through an `<img>` tag — which is exactly how Markdown embeds
images. Foreign content isn't painted in that context, so you get a diagram with
correct boxes and arrows and **no text in any of them**.

This is the single most common failure, and it is silent: `mmdc` reports success, the
SVG opens fine in a local viewer and in a browser tab, and it is blank-labelled only
in the README. Anyone who converts diagrams by hand hits it and concludes SVG doesn't
work in Bitbucket.

The fix is `htmlLabels: false`, which makes Mermaid emit real `<text>` elements.
`assets/mermaid-config.json` sets it. `scripts/render_mermaid.py` also greps the
output and hard-fails if a `<foreignObject>` survives — a diagram can re-enable
htmlLabels with an inline `%%{init}%%` directive.

## Workflow

### 1. Check the tooling

Rendering needs `mmdc` (@mermaid-js/mermaid-cli), which drives headless Chromium:

```bash
npm install -g @mermaid-js/mermaid-cli
```

The script falls back to `npx --yes @mermaid-js/mermaid-cli` if `mmdc` isn't on PATH.
Only rendering needs it — `--check` is a hash comparison and runs on bare Python.

### 2. Vendor the script into the repo

Copy these into the target repo and commit them, so the pipeline and every developer
run the same renderer:

```
scripts/render_mermaid.py
scripts/puppeteer-config.json
assets/mermaid-config.json
```

The config is what makes the output Bitbucket-safe, so it has to travel with the
script. The script finds it automatically in `assets/`, `.mermaid/`, or the repo root;
anywhere else needs `--config`.

### 3. Render

From the repo root:

```bash
python3 scripts/render_mermaid.py .
```

This walks the tree and:

- renders standalone `.mmd` / `.mermaid` files in place (`docs/topology.mmd` → `docs/topology.svg`)
- finds ```mermaid blocks in `.md` files, writes each block out to a sidecar `.mmd`
  under `docs/diagrams/`, and replaces the block with `![Alt text](docs/diagrams/....svg)`
- records a hash of every source in `.mermaid-svg.json` so re-runs skip unchanged
  diagrams

Useful flags: `--out-dir` (where extracted sources land), `--no-rewrite` (render only,
never touch Markdown), `--force` (ignore hashes), `--check` (verify, write nothing),
`--background` (defaults to `#ffffff`).

Point it at specific files instead of `.` when working incrementally:

```bash
python3 scripts/render_mermaid.py README.md docs/runbooks/
```

### 4. Explain the Markdown rewrite before running it on someone's repo

The rewrite is lossy in one specific way that matters, so say it out loud rather than
letting them discover it in a diff: **the fenced block is removed from the `.md` and
the source of truth moves to the sidecar `.mmd` file.** Editing the diagram means
editing the `.mmd` and re-running the script.

This is deliberate. The alternative — keeping the fenced block and adding an image
next to it — makes Bitbucket display the raw source *and* the picture, which is worse
than what they started with. Bitbucket also strips raw HTML in Markdown, so the usual
`<details>` collapse trick isn't available.

Consequence worth flagging: it's a one-way move for that file. If the repo is mirrored
to GitHub, or might migrate back, the diagrams will no longer be live Mermaid there —
they'll be images. If that's a real concern, `--no-rewrite` plus keeping the sidecar
`.mmd` files as the only diagram home is the cleaner shape.

The rewrite is idempotent: after the first pass there are no fenced blocks left to
match, so re-runs only re-render changed sources.

### 5. Wire up Pipelines

`assets/bitbucket-pipelines.snippet.yml` has two strategies. Default to **verify**
(`--check` on PRs, fails if a committed SVG is stale) unless they specifically want
auto-commit. Verify needs no credentials, can't loop, and puts the rendered diff in
front of a reviewer. Auto-commit needs a write-capable access key and a `[skip ci]`
guard, and hides diagram changes from review.

### 6. Verify in Bitbucket, not locally

A local SVG viewer will not reproduce the `<img>` sandbox. The only real check is
pushing to a branch and looking at the file in Bitbucket's UI. Tell them to confirm
label text is visible before closing this out.

## Dark mode

Bitbucket has a dark UI. An SVG loaded via `<img>` can't see the page theme, and a
transparent background with dark text renders as dark-on-dark — invisible.

So the default is an opaque white background (`--background '#ffffff'`) with the fixed
light palette in `assets/mermaid-config.json`. On a dark Bitbucket the diagram reads
as a white card. That's slightly less elegant than a theme-aware diagram and it is
reliably legible for everyone, which is the tradeoff worth making for docs.

Don't reach for `@media (prefers-color-scheme: dark)` inside the SVG. It does
evaluate in modern browsers, but against the *OS* setting, not Bitbucket's theme
setting — so anyone running a light Bitbucket on a dark OS gets a dark diagram on a
white page. `references/bitbucket-gotchas.md` covers the dual-render alternative if
they insist.

## Editing the palette

`assets/mermaid-config.json` uses `theme: base` with explicit `themeVariables`, tuned
to Atlassian's palette so diagrams don't clash with Bitbucket's chrome. Roughly six
variables carry the look: `primaryColor`, `primaryTextColor`, `primaryBorderColor`,
`lineColor`, `fontFamily`, `fontSize`. Change those first.

Keep `fontFamily` to a websafe stack. Mermaid measures text in Chromium at render
time to size the boxes, but the *viewer's* browser paints it — if the font isn't
present on both sides, text overflows its box. The default
`Helvetica Neue, Helvetica, Arial, sans-serif` is near-universal and matches
Liberation Sans metrics in CI containers.

Any config edit changes the fingerprint in the manifest, so the next run re-renders
everything. That's intended.

## Reference

`references/bitbucket-gotchas.md` — the full list of Bitbucket Cloud Markdown/SVG
quirks: image path rules, `<image>` href stripping, encoding failures that break
README rendering entirely, sizing, and the dual-render dark mode option. Read it when
a diagram renders wrong in Bitbucket but looks fine locally, or when the README won't
render at all.
