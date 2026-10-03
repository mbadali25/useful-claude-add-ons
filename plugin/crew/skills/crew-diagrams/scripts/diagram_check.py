"""Measure whether a rendered Mermaid flowchart is readable.

Reads the SVG Mermaid produced (`render.sh` writes `out/*.svg`; any Mermaid 10+
SVG works) and measures the drawing itself rather than trusting the source:

  crossings      two edges cross outside any node
  through-node   an edge passes through a node that is neither of its ends
  label-overlap  an edge label covers a node or another label, or another
                 edge's line runs through it
  size           more nodes than one screen holds (MAX_NODES)
  wordy          a box or edge label holding more than MAX_BOX_LINES lines of text -- a
                 WARNING, not a FAIL: the detail is content, and moving it to
                 the page's prose is an editorial call

A diagram PASSes only with zero of the first three and a size within the
limit. A flowchart is the only kind measured: a sequence, state or ER diagram
is reported NOT CHECKED, never PASS. An SVG that cannot be parsed is UNKNOWN.

Geometry: every `translate()` from the root down is accumulated, curves are
sampled into polylines, and an intersection inside (or within EDGE_SLACK of)
an edge's own end nodes does not count -- arrows converging on one node meet
there by design.

Usage: diagram_check.py [--json] SVG_OR_DIR...
Exit: 0 every measured diagram PASSes; 1 any FAIL or UNKNOWN; 2 usage.
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

MAX_NODES = 15
MAX_BOX_LINES = 6    # a box with more lines of text than this is reported as wordy (a warning)
LINE_HEIGHT = 24.0   # px per text line in Mermaid's default label (16px font, line-height 1.5)
EDGE_SLACK = 6.0     # px around an end node where edges may meet
NODE_SHRINK = 2.0    # px a node box is shrunk by before an edge "passes through" it
CURVE_STEPS = 12

PASS, FAIL, UNKNOWN, NOT_CHECKED = "PASS", "FAIL", "UNKNOWN", "NOT CHECKED"
_NUM = r"-?\d*\.?\d+(?:e-?\d+)?"
_TRANSLATE = re.compile(rf"translate\(\s*({_NUM})[\s,]+({_NUM})?\s*\)")


def _offset(el, base):
    dx = dy = 0.0
    for m in _TRANSLATE.finditer(el.get("transform") or ""):
        dx += float(m.group(1))
        dy += float(m.group(2) or 0)
    return base[0] + dx, base[1] + dy


def _classes(el):
    return set((el.get("class") or "").split())


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def path_points(d, origin=(0.0, 0.0)):
    """Path data as a sampled polyline. Absolute and relative M/L/H/V/C/Q/A/Z:
    edges use absolute commands, but shapes do not -- a cylinder is drawn with
    relative arcs (`a`) and lines (`l`). An arc contributes its endpoint plus
    its radii either side, enough for the bounding box a shape needs."""
    tokens = re.findall(rf"[MLCQHVZAmlcqhvza]|{_NUM}", d or "")
    sizes = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "Q": 4, "A": 7}
    pts, i, cmd, cur, start = [], 0, None, (0.0, 0.0), (0.0, 0.0)
    while i < len(tokens):
        if re.fullmatch(r"[A-Za-z]", tokens[i]):
            cmd = tokens[i]
            i += 1
            if cmd in "Zz":
                cur = start
                continue
        if cmd is None:
            raise ValueError("path data does not start with a command")
        up, rel = cmd.upper(), cmd.islower()
        vals = [float(t) for t in tokens[i:i + sizes[up]]]
        if len(vals) < sizes[up]:
            raise ValueError(f"truncated {cmd!r} in path data")
        i += sizes[up]
        ox, oy = cur if rel else (0.0, 0.0)
        if up in ("M", "L"):
            cur = (vals[0] + ox, vals[1] + oy)
            pts.append(cur)
            if up == "M":
                start = cur
                cmd = "l" if rel else "L"  # implicit lineto after a moveto
        elif up == "H":
            cur = (vals[0] + ox, cur[1])
            pts.append(cur)
        elif up == "V":
            cur = (cur[0], vals[0] + oy)
            pts.append(cur)
        elif up == "C":
            x1, y1, x2, y2, x, y = vals[0] + ox, vals[1] + oy, vals[2] + ox, vals[3] + oy, vals[4] + ox, vals[5] + oy
            p0 = cur
            for k in range(1, CURVE_STEPS + 1):
                t = k / CURVE_STEPS
                a, b, c, e = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
                pts.append((a * p0[0] + b * x1 + c * x2 + e * x, a * p0[1] + b * y1 + c * y2 + e * y))
            cur = (x, y)
        elif up == "Q":
            x1, y1, x, y = vals[0] + ox, vals[1] + oy, vals[2] + ox, vals[3] + oy
            p0 = cur
            for k in range(1, CURVE_STEPS + 1):
                t = k / CURVE_STEPS
                pts.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * x1 + t * t * x,
                            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * y1 + t * t * y))
            cur = (x, y)
        else:  # A: rx ry rotation large-arc sweep x y
            rx, ry = abs(vals[0]), abs(vals[1])
            end = (vals[5] + ox, vals[6] + oy)
            for px, py in (cur, end):
                pts += [(px, py - ry), (px, py + ry), (px - rx, py), (px + rx, py)]
            cur = end
            pts.append(cur)
    return [(x + origin[0], y + origin[1]) for x, y in pts]


def _shape_box(el, base):
    """Bounding box of one shape element, in diagram coordinates, or None."""
    tag, off = _local(el.tag), _offset(el, base)
    try:
        if tag == "rect":
            x, y = float(el.get("x") or 0), float(el.get("y") or 0)
            w, h = float(el.get("width") or 0), float(el.get("height") or 0)
            if w <= 0 or h <= 0:
                return None
            pts = [(x, y), (x + w, y + h)]
        elif tag == "polygon":
            nums = [float(n) for n in re.findall(_NUM, el.get("points") or "")]
            pts = list(zip(nums[::2], nums[1::2]))
        elif tag in ("circle", "ellipse"):
            cx, cy = float(el.get("cx") or 0), float(el.get("cy") or 0)
            rx = float(el.get("r") or el.get("rx") or 0)
            ry = float(el.get("r") or el.get("ry") or 0)
            pts = [(cx - rx, cy - ry), (cx + rx, cy + ry)]
        elif tag == "path":
            pts = path_points(el.get("d"))
        else:
            return None
    except ValueError:
        return None
    if not pts:
        return None
    xs, ys = [p[0] + off[0] for p in pts], [p[1] + off[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _union(boxes):
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def collect(root):
    """(nodes, edges, labels, lines): nodes {id: box}, edges [(id, polyline)],
    labels [(x0, y0, x1, y1, owning edge id or None, lines of text)],
    lines {node id: lines of text in its box}."""
    nodes, edges, labels = {}, [], []
    unmeasured, lines = [], {}

    def walk(el, base):
        cls, here = _classes(el), _offset(el, base)
        tag = _local(el.tag)
        if tag == "g" and "node" in cls:
            shapes = [_shape_box(child, here) for child in el
                      if _local(child.tag) in ("rect", "polygon", "circle", "ellipse", "path")]
            for child in el:  # Mermaid wraps some shapes one group down
                if _local(child.tag) == "g" and "label" not in _classes(child):
                    inner = _offset(child, here)
                    shapes += [_shape_box(s, inner) for s in child
                               if _local(s.tag) in ("rect", "polygon", "circle", "ellipse", "path")]
            box = _union(shapes)
            heights = [float(fo.get("height") or 0) for fo in el.iter() if _local(fo.tag) == "foreignObject"]
            if box:
                nodes[el.get("id") or f"node{len(nodes)}"] = box
                lines[el.get("id") or f"node{len(nodes) - 1}"] = round(max(heights, default=0) / LINE_HEIGHT)
            else:
                unmeasured.append(el.get("id") or "?")
            return
        if tag == "path" and "flowchart-link" in cls:
            edges.append((el.get("id") or f"edge{len(edges)}", path_points(el.get("d"), here)))
            return
        if tag == "g" and "edgeLabel" in cls:
            owner = next((g.get("data-id") for g in el.iter() if g.get("data-id")), None)
            for fo in el.iter():
                if _local(fo.tag) == "foreignObject":
                    w, h = float(fo.get("width") or 0), float(fo.get("height") or 0)
                    if w > 0 and h > 0:
                        inner = here
                        for g in el:
                            if _local(g.tag) == "g":
                                inner = _offset(g, here)
                        labels.append((inner[0], inner[1], inner[0] + w, inner[1] + h, owner,
                                       round(h / LINE_HEIGHT)))
            return
        for child in el:
            walk(child, here)

    walk(root, (0.0, 0.0))
    if unmeasured:
        # A box the checker cannot see is a box no line is tested against:
        # that is "could not tell", never a quiet PASS.
        raise ValueError(f"{len(unmeasured)} node shape(s) not measurable: "
                         + ", ".join(_short(n) for n in unmeasured[:4]))
    return nodes, edges, labels, lines


def _inside(p, box, pad=0.0):
    return box[0] - pad <= p[0] <= box[2] + pad and box[1] - pad <= p[1] <= box[3] + pad


def _seg_cross(a, b, c, d):
    """Proper intersection point of segments ab and cd, or None."""
    den = (b[0] - a[0]) * (d[1] - c[1]) - (b[1] - a[1]) * (d[0] - c[0])
    if abs(den) < 1e-9:
        return None
    t = ((c[0] - a[0]) * (d[1] - c[1]) - (c[1] - a[1]) * (d[0] - c[0])) / den
    u = ((c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])) / den
    if 0 < t < 1 and 0 < u < 1:
        return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    return None


def _seg_hits_box(a, b, box):
    if _inside(a, box) or _inside(b, box):
        return True
    corners = [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]
    return any(_seg_cross(a, b, corners[k], corners[(k + 1) % 4]) for k in range(4))


def _ends(poly, nodes):
    """The node boxes nearest each end of an edge: its source and target."""
    def nearest(p):
        return min(nodes, key=lambda n: _box_dist(p, nodes[n])) if nodes else None
    return {nearest(poly[0]), nearest(poly[-1])} - {None}


def _box_dist(p, box):
    dx = max(box[0] - p[0], 0, p[0] - box[2])
    dy = max(box[1] - p[1], 0, p[1] - box[3])
    return (dx * dx + dy * dy) ** 0.5


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _shrink(box, by):
    return (box[0] + by, box[1] + by, box[2] - by, box[3] - by)


def measure(svg_text):
    """The four measurements for one SVG, plus its verdict."""
    # Mermaid's labels are HTML inside <foreignObject>; a browser-serialised SVG
    # can carry HTML void tags that are not XML. Close them before parsing.
    svg_text = re.sub(r"<(br|hr|img|wbr)(\b[^>]*?)(?<!/)>", r"<\1\2/>", svg_text)
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as exc:
        return {"status": UNKNOWN, "why": f"SVG did not parse: {exc}"}
    if "flowchart-link" not in svg_text and "flowchart" not in (root.get("aria-roledescription") or ""):
        kind = root.get("aria-roledescription") or "not a flowchart"
        return {"status": NOT_CHECKED, "why": f"{kind}: only flowcharts are measured"}
    try:
        nodes, edges, labels, lines = collect(root)
    except ValueError as exc:
        return {"status": UNKNOWN, "why": f"could not read the geometry: {exc}"}
    ends = [(eid, poly, _ends(poly, nodes)) for eid, poly in edges if len(poly) >= 2]
    crossings = []
    for i, (ida, pa, ea) in enumerate(ends):
        for idb, pb, eb in ends[i + 1:]:
            near = [nodes[n] for n in ea | eb]
            for s in range(len(pa) - 1):
                hit = None
                for t in range(len(pb) - 1):
                    x = _seg_cross(pa[s], pa[s + 1], pb[t], pb[t + 1])
                    if x and not any(_inside(x, box, EDGE_SLACK) for box in near):
                        hit = x
                        break
                if hit:
                    crossings.append(f"{_short(ida)} x {_short(idb)} at ({hit[0]:.0f},{hit[1]:.0f})")
                    break
    through = []
    for eid, poly, own in ends:
        for nid, box in nodes.items():
            if nid in own:
                continue
            inner = _shrink(box, NODE_SHRINK)
            if inner[0] >= inner[2] or inner[1] >= inner[3]:
                continue
            if any(_seg_hits_box(poly[k], poly[k + 1], inner) for k in range(len(poly) - 1)):
                through.append(f"{_short(eid)} through {_short(nid)}")
    overlaps = []
    for k, lab in enumerate(labels):
        box, owner = lab[:4], lab[4]
        name = f"label of {_short(owner)}" if owner else f"label {k}"
        overlaps += [f"{name} on {_short(nid)}" for nid, nbox in nodes.items()
                     if _overlap(box, _shrink(nbox, NODE_SHRINK))]
        overlaps += [f"{name} on label {j}" for j, other in enumerate(labels[k + 1:], k + 1)
                     if _overlap(box, other[:4])]
        inner = _shrink(box, NODE_SHRINK)
        if inner[0] < inner[2] and inner[1] < inner[3]:
            overlaps += [f"{_short(eid)} through {name}" for eid, poly, _ in ends
                         if not (owner and eid.endswith(owner))
                         and any(_seg_hits_box(poly[i], poly[i + 1], inner) for i in range(len(poly) - 1))]
    wordy = [f"{_short(n)} ({k} lines)" for n, k in lines.items() if k > MAX_BOX_LINES]
    wordy += [f"label of {_short(lab[4]) if lab[4] else '?'} ({lab[5]} lines)"
              for lab in labels if lab[5] > MAX_BOX_LINES]
    problems = len(crossings) + len(through) + len(overlaps)
    big = len(nodes) > MAX_NODES
    return {
        "status": PASS if not problems and not big else FAIL,
        "nodes": len(nodes), "edges": len(edges),
        "crossings": crossings, "through": through, "overlaps": overlaps, "wordy": wordy,
        "why": (f"{len(nodes)} nodes, over the {MAX_NODES}-node limit: split it" if big else ""),
    }


def _short(svg_id):
    """`abc123-flowchart-review-4` -> `review`; `abc-L_ci_merge_0` -> `ci->merge`."""
    m = re.search(r"flowchart-(.+)-\d+$", svg_id or "")
    if m:
        return m.group(1)
    m = re.search(r"L_(.+)_\d+$", svg_id or "")
    return m.group(1).replace("_", "->", 1) if m else svg_id


def targets(paths):
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                if name.endswith(".svg"):
                    yield os.path.join(p, name)
        else:
            yield p


def _cell(result, key):
    v = result.get(key)
    return "" if v is None else str(len(v)) if isinstance(v, list) else str(v)


def render(results):
    lines = ["| Diagram | Verdict | Nodes | Crossings | Through a node | Label overlaps "
             "| Wordy boxes (warning) | Note |",
             "|---|---|---|---|---|---|---|---|"]
    for path, r in results:
        note = r.get("why") or "; ".join((r.get("crossings") or [])[:2] + (r.get("through") or [])[:2])
        lines.append(f"| {os.path.basename(path)} | {r['status']} | {_cell(r, 'nodes')} | {_cell(r, 'crossings')} | "
                     f"{_cell(r, 'through')} | {_cell(r, 'overlaps')} | {_cell(r, 'wordy')} | "
                     f"{note.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", help="SVG files, or directories of them")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    results = []
    for path in targets(args.paths):
        try:
            with open(path, encoding="utf-8") as fh:
                results.append((path, measure(fh.read())))
        except OSError as exc:
            results.append((path, {"status": UNKNOWN, "why": f"cannot read: {exc}"}))
    if not results:
        print("diagram-check: no SVG found; render first (render.sh)", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(dict(results), indent=2))
    else:
        sys.stdout.write(render(results))
    return 0 if all(r["status"] in (PASS, NOT_CHECKED) for _, r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
