#!/usr/bin/env python3
"""
diagram_from_spec.py - Turn a YAML/JSON diagram spec into a native .vsdx,
plus an .svg preview so the diagram can be checked without opening Visio.

    python diagram_from_spec.py spec.yaml -o out.vsdx [--no-preview]

Spec format (YAML or JSON):

    title: Prod Network
    page: {width: 17, height: 11, direction: LR}   # LR or TB
    defaults: {width: 1.9, height: 0.9}
    styles:
      db:  {kind: ellipse, fill: "#C5E0B4"}
      gate:{kind: diamond, fill: "#FFE699"}
    nodes:
      - {id: fw,  label: Perimeter FW, fill: "#F4B183"}
      - {id: sw,  label: Core Switch}
      - {id: sql, label: SQL AG, style: db}
      - {id: cab, label: CAB approved?, style: gate}
    edges:
      - {from: fw, to: sw, label: 10Gb}
      - {from: sw, to: sql, label: "TDS 1433"}
      - {from: sw, to: cab, dashed: true}

Layout is layered: rank by longest path from the roots, then spread evenly
within each rank. Explicit `x`/`y` on a node (inches) overrides layout.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# sys.path is set up immediately above, so these cannot move to the top.
# pylint: disable=wrong-import-position
from vsdx_writer import VisioDocument, GEOMETRY, ROUND_KINDS  # noqa: E402


def load_spec(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError:
            sys.exit("PyYAML not installed. Either run:\n"
                     "    python scripts/ensure_deps.py pyyaml\n"
                     "or write the spec as JSON instead (same schema).")
        return yaml.safe_load(text)
    return json.loads(text)


def rank_nodes(node_ids, edges):
    """Longest-path ranking. Cycles are tolerated: back-edges are ignored for
    ranking so a loop in the topology never hangs the layout."""
    indeg = {n: 0 for n in node_ids}
    out = defaultdict(list)
    for e in edges:
        a, b = e["from"], e["to"]
        if a in indeg and b in indeg and a != b:
            out[a].append(b)
            indeg[b] += 1

    rank = {n: 0 for n in node_ids}
    q = deque([n for n in node_ids if indeg[n] == 0]) or deque([node_ids[0]])
    seen = set(q)
    while q:
        n = q.popleft()
        for m in out[n]:
            rank[m] = max(rank[m], rank[n] + 1)
            indeg[m] -= 1
            if indeg[m] <= 0 and m not in seen:
                seen.add(m)
                q.append(m)
    # Any node stranded by a cycle: park it one rank past its highest predecessor.
    for n in node_ids:
        if n not in seen:
            preds = [rank[a] for e in edges if e["to"] == n
                     for a in [e["from"]] if a in rank]
            rank[n] = max(preds, default=0) + 1
    return rank


def build(spec: dict):
    page_cfg = spec.get("page") or {}
    direction = str(page_cfg.get("direction", "TB")).upper()
    defaults = spec.get("defaults") or {}
    styles = spec.get("styles") or {}
    nodes = spec.get("nodes") or []
    edges = spec.get("edges") or []
    if not nodes:
        sys.exit("spec has no nodes")

    ids = [n["id"] for n in nodes]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        sys.exit(f"duplicate node ids: {sorted(dupes)}")

    dw = float(defaults.get("width", 1.9))
    dh = float(defaults.get("height", 0.9))
    rank = rank_nodes(ids, edges)

    buckets = defaultdict(list)
    for n in nodes:
        buckets[rank[n["id"]]].append(n)
    n_ranks = max(buckets) + 1
    widest = max(len(v) for v in buckets.values())

    # Size the page to the content unless explicitly given.
    gap_along, gap_across = 1.5, 0.6
    if direction == "LR":
        need_w = n_ranks * dw + (n_ranks + 1) * gap_along
        need_h = widest * dh + (widest + 1) * gap_across
    else:
        need_w = widest * dw + (widest + 1) * gap_across
        need_h = n_ranks * dh + (n_ranks + 1) * gap_along
    pw = float(page_cfg.get("width", max(11.0, round(need_w + 0.5, 2))))
    ph = float(page_cfg.get("height", max(8.5, round(need_h + 0.5, 2))))

    doc = VisioDocument()
    page = doc.add_page(spec.get("title", "Page-1"), pw, ph)

    handles = {}
    for r in sorted(buckets):
        row = buckets[r]
        for i, n in enumerate(row):
            style = dict(styles.get(n.get("style", ""), {}))
            style.update({k: v for k, v in n.items()
                          if k in {"kind", "fill", "line", "text_color",
                                   "font_size", "width", "height"}})
            w = float(style.pop("width", dw))
            h = float(style.pop("height", dh))
            kind = style.pop("kind", "box")
            if kind not in set(GEOMETRY) | ROUND_KINDS:
                sys.exit(f"node {n['id']!r}: unknown kind {kind!r}")

            # Spread this rank across the axis; ranks march down (TB) or right (LR).
            frac = (i + 1) / (len(row) + 1)
            if direction == "LR":
                x = gap_along + dw / 2 + r * (dw + gap_along)
                y = ph * frac
            else:
                x = pw * frac
                y = ph - (gap_along + dh / 2 + r * (dh + gap_along))
            x = float(n.get("x", x))
            y = float(n.get("y", y))

            handles[n["id"]] = page.add_shape(
                str(n.get("label", n["id"])), x, y, w=w, h=h, kind=kind, **style
            )

    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a not in handles or b not in handles:
            sys.exit(f"edge references unknown node: {a} -> {b}")
        page.connect(
            handles[a], handles[b],
            label=str(e.get("label", "")),
            color=e.get("color", "#404040"),
            dashed=bool(e.get("dashed", False)),
            arrow=bool(e.get("arrow", True)),
        )
    return doc, page


def svg_preview(page, path):
    """Flip Y (Visio origin is bottom-left, SVG is top-left) and draw at 72dpi."""
    S = 72.0
    W, H = page.width * S, page.height * S
    def fy(y):
        return (page.height - y) * S
    arrows = {c.color for c in page.connectors if c.arrow}
    defs = "".join(
        f'<marker id="a{i}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{col}"/></marker>'
        for i, col in enumerate(sorted(arrows))
    )
    marker_id = {col: f"a{i}" for i, col in enumerate(sorted(arrows))}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
           f'viewBox="0 0 {W:.0f} {H:.0f}"><defs>{defs}</defs>'
           '<rect width="100%" height="100%" fill="#fff"/>']

    for c in page.connectors:
        bx, by, ex, ey = c._endpoints()
        dash = ' stroke-dasharray="6,4"' if c.dashed else ""
        head = f' marker-end="url(#{marker_id[c.color]})"' if c.arrow else ""
        out.append(f'<line x1="{bx*S:.1f}" y1="{fy(by):.1f}" x2="{ex*S:.1f}" '
                   f'y2="{fy(ey):.1f}" stroke="{c.color}" stroke-width="1.5"{dash}{head}/>')
        if c.label:
            out.append(f'<text x="{(bx+ex)/2*S:.1f}" y="{fy((by+ey)/2)-4:.1f}" '
                       'font-family="Calibri,sans-serif" font-size="9" fill="#404040" '
                       f'text-anchor="middle">{_esc(c.label)}</text>')

    for s in page.shapes:
        cx, cy = s.x * S, fy(s.y)
        w, h = s.w * S, s.h * S
        if s.kind in ROUND_KINDS:
            out.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{w/2:.1f}" '
                       f'ry="{h/2:.1f}" fill="{s.fill}" stroke="{s.line}" stroke-width="1.2"/>')
        else:
            pts = " ".join(
                f"{(s.left + fx * s.w) * S:.1f},{fy(s.bottom + fyy * s.h):.1f}"
                for fx, fyy in GEOMETRY[s.kind]
            )
            out.append(f'<polygon points="{pts}" fill="{s.fill}" stroke="{s.line}" '
                       'stroke-width="1.2"/>')
        for j, ln in enumerate(_wrap(s.text, s.w)):
            dy = cy + (j - (len(_wrap(s.text, s.w)) - 1) / 2) * (s.font_size + 2) + s.font_size / 3
            out.append(f'<text x="{cx:.1f}" y="{dy:.1f}" font-family="Calibri,sans-serif" '
                       f'font-size="{s.font_size}" fill="{s.text_color}" '
                       f'text-anchor="middle">{_esc(ln)}</text>')

    out.append("</svg>")
    Path(path).write_text("".join(out), encoding="utf-8")


def _esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _wrap(text, width_in, cpi=11):
    limit = max(6, int(width_in * cpi))
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= limit:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def main():
    ap = argparse.ArgumentParser(description="Build a .vsdx from a YAML/JSON spec")
    ap.add_argument("spec")
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--no-preview", action="store_true")
    a = ap.parse_args()

    sp = Path(a.spec)
    doc, page = build(load_spec(sp))
    out = Path(a.output) if a.output else sp.with_suffix(".vsdx")
    doc.save(out)
    print(f"vsdx    : {out}  ({len(page.shapes)} shapes, {len(page.connectors)} connectors)")
    if not a.no_preview:
        prev = out.with_suffix(".svg")
        svg_preview(page, prev)
        print(f"preview : {prev}")


if __name__ == "__main__":
    main()
