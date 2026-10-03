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

A diagram PASSes only with at least one measured node box, zero of the first
three and a size within the limit. A flowchart is the only kind measured: a
sequence, state or ER diagram is reported NOT CHECKED, never PASS. An SVG that
cannot be parsed, has no measurable node, has a line outside the nodes that is
not a recognised edge (or a non-empty edgePaths group and no edge), or whose
geometry the checker cannot read (a scale/rotate/matrix/skew transform above a
measured element, path data it cannot parse) is UNKNOWN -- "could not tell" is
never a PASS. Each subpath of an edge is its own line: a moveto is a gap.

Geometry: every `translate()` from the root down is accumulated, curves and
arcs are sampled into polylines, and an intersection inside (or within EDGE_SLACK of)
an edge's own end nodes does not count -- arrows converging on one node meet
there by design.

Usage: diagram_check.py [--json] SVG_OR_DIR...
Exit: 0 every measured diagram PASSes; 1 any FAIL or UNKNOWN; 2 usage.
"""
import argparse
import json
import math
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
_NUM = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_TRANSFORM = re.compile(r"\s*([A-Za-z]+)\s*\(([^)]*)\)\s*,?")


def _offset(el, base):
    """`base` moved by this element's transform. Only translate() is a plain
    offset; scale, rotate, matrix or skew would move every point differently,
    so they raise ValueError (the caller's verdict becomes UNKNOWN) rather
    than being ignored."""
    text = el.get("transform") or ""
    dx = dy = 0.0
    pos = 0
    while pos < len(text.rstrip()):
        m = _TRANSFORM.match(text, pos)
        if not m:
            raise ValueError(f"unreadable transform {text!r}")
        name, args = m.group(1), [float(a) for a in re.findall(_NUM, m.group(2))]
        if name != "translate" or len(args) not in (1, 2):
            raise ValueError(f"transform {name}({m.group(2).strip()}) is not measured")
        dx += args[0]
        dy += args[1] if len(args) == 2 else 0.0
        pos = m.end()
    return base[0] + dx, base[1] + dy


def _classes(el):
    return set((el.get("class") or "").split())


def _local(tag):
    return tag.rsplit("}", 1)[-1]


_NOT_DRAWN = ("defs", "marker", "symbol", "clipPath", "mask", "pattern")
_PATH_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}
_SEP = re.compile(r"\s*,?\s*")
_NUM_AT = re.compile(_NUM)
_CMD_AT = re.compile(r"[MLHVCSQTAZmlhvcsqtaz]")


class _PathScanner:
    """SVG path data read the way the grammar reads it: a number where a
    number belongs, a one-character 0/1 flag where an arc flag belongs (so
    `a10 10 0 0110 10` is flags 0 and 1, then 10 10). Anything else raises
    ValueError."""

    def __init__(self, d):
        self.d, self.pos = (d or "").strip(), 0

    def _skip(self):
        self.pos = _SEP.match(self.d, self.pos).end()

    def done(self):
        self._skip()
        return self.pos >= len(self.d)

    def command(self):
        self._skip()
        m = _CMD_AT.match(self.d, self.pos)
        if m:
            self.pos = m.end()
            return m.group(0)
        if self.pos < len(self.d) and self.d[self.pos].isalpha():
            raise ValueError(f"unknown path command {self.d[self.pos]!r}")
        return None

    def number(self):
        self._skip()
        m = _NUM_AT.match(self.d, self.pos)
        if not m:
            raise ValueError(f"expected a number at {self.d[self.pos:self.pos + 12]!r}")
        self.pos = m.end()
        return float(m.group(0))

    def flag(self):
        self._skip()
        if self.pos >= len(self.d) or self.d[self.pos] not in "01":
            raise ValueError(f"arc flag must be 0 or 1 at {self.d[self.pos:self.pos + 12]!r}")
        self.pos += 1
        return self.d[self.pos - 1] == "1"


def _arc(p0, rx, ry, phi_deg, large, sweep, p1):
    """Sample an SVG elliptical arc (endpoint parameterisation, SVG 1.1 F.6.5)."""
    if rx == 0 or ry == 0 or p0 == p1:
        return [p1]
    phi = math.radians(phi_deg % 360)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    hx, hy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1, y1 = cos_p * hx + sin_p * hy, -sin_p * hx + cos_p * hy
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1:  # radii too small to reach: scale them up, as a renderer does
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    coef = math.sqrt(max(num, 0.0) / den) if den else 0.0
    if large == sweep:
        coef = -coef
    cx1, cy1 = coef * rx * y1 / ry, -coef * ry * x1 / rx
    cx = cos_p * cx1 - sin_p * cy1 + (p0[0] + p1[0]) / 2
    cy = sin_p * cx1 + cos_p * cy1 + (p0[1] + p1[1]) / 2

    def angle(ux, uy, vx, vy):
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    t1 = angle(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    dt = angle((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    pts = []
    for k in range(1, CURVE_STEPS + 1):
        t = t1 + dt * k / CURVE_STEPS
        ex, ey = rx * math.cos(t), ry * math.sin(t)
        pts.append((cos_p * ex - sin_p * ey + cx, sin_p * ex + cos_p * ey + cy))
    pts[-1] = p1
    return pts


def path_subpaths(d, origin=(0.0, 0.0)):
    """Path data as sampled polylines, one per subpath: every SVG path command,
    absolute and relative. A moveto starts a new subpath -- no line joins it to
    the last point. Edges use absolute commands, but shapes do not -- a cylinder
    is drawn with relative arcs (`a`) and lines (`l`). Curves and arcs are
    sampled (an arc through its centre parameterisation), S/T reflect the
    previous control point. Path data this cannot read raises ValueError,
    never a guess."""
    sc = _PathScanner(d)
    subs, cmd, cur, start = [], None, (0.0, 0.0), (0.0, 0.0)
    ctrl, prev = (0.0, 0.0), None  # last control point (read only after C/S/Q/T), last command
    while not sc.done():
        letter = sc.command()
        if letter:
            cmd = letter
        elif cmd is None:
            raise ValueError("path data does not start with a command")
        elif cmd in "Zz":
            raise ValueError("numbers after a closepath (Z) with no command")
        up, rel = cmd.upper(), cmd.islower()
        if up != "M" and not subs:
            raise ValueError("path data does not start with a moveto")
        if up == "Z":
            cur, prev = start, "Z"
            subs[-1].append(cur)
            subs.append([cur])  # what follows Z starts again from the subpath start
            continue
        if up == "A":
            vals = [sc.number(), sc.number(), sc.number(), sc.flag(), sc.flag(), sc.number(), sc.number()]
        else:
            vals = [sc.number() for _ in range(_PATH_ARGS[up])]
        ox, oy = cur if rel else (0.0, 0.0)
        p0 = cur
        pts = []
        if up in ("M", "L", "T"):
            end = (vals[0] + ox, vals[1] + oy)
            if up == "T":
                c = (2 * p0[0] - ctrl[0], 2 * p0[1] - ctrl[1]) if prev in ("Q", "T") else p0
                pts = _bezier([p0, c, end])
                ctrl = c
            elif up == "L":
                pts = [end]
            cur = end
            if up == "M":
                start = cur
                subs.append([cur])
                cmd = "l" if rel else "L"  # implicit lineto after a moveto
        elif up == "H":
            cur = (vals[0] + ox, cur[1])
            pts = [cur]
        elif up == "V":
            cur = (cur[0], vals[0] + oy)
            pts = [cur]
        elif up in ("C", "S"):
            if up == "C":
                c1, rest = (vals[0] + ox, vals[1] + oy), vals[2:]
            else:
                c1 = (2 * p0[0] - ctrl[0], 2 * p0[1] - ctrl[1]) if prev in ("C", "S") else p0
                rest = vals
            c2, end = (rest[0] + ox, rest[1] + oy), (rest[2] + ox, rest[3] + oy)
            pts = _bezier([p0, c1, c2, end])
            cur, ctrl = end, c2
        elif up == "Q":
            c, end = (vals[0] + ox, vals[1] + oy), (vals[2] + ox, vals[3] + oy)
            pts = _bezier([p0, c, end])
            cur, ctrl = end, c
        else:  # A: rx ry rotation large-arc sweep x y
            end = (vals[5] + ox, vals[6] + oy)
            pts = _arc(p0, abs(vals[0]), abs(vals[1]), vals[2], vals[3], vals[4], end)
            cur = end
        subs[-1] += pts
        prev = up
    return [[(x + origin[0], y + origin[1]) for x, y in sp] for sp in subs if sp]


def path_points(d, origin=(0.0, 0.0)):
    """Every sampled point of a path, subpaths concatenated: for a bounding box
    only. Segments must come from path_subpaths(), which never joins subpaths."""
    return [p for sp in path_subpaths(d, origin) for p in sp]


def _segments(subs):
    """The drawn segments of a list of subpath polylines."""
    return [(a, b) for sp in subs for a, b in zip(sp, sp[1:])]


def _bezier(ctl):
    """CURVE_STEPS points along a quadratic or cubic Bezier (after its start)."""
    out = []
    for k in range(1, CURVE_STEPS + 1):
        t = k / CURVE_STEPS
        p = list(ctl)
        while len(p) > 1:  # de Casteljau
            p = [((1 - t) * a[0] + t * b[0], (1 - t) * a[1] + t * b[1]) for a, b in zip(p, p[1:])]
        out.append(p[0])
    return out


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


def _descendants(el, base):
    """(descendant, its offset) for everything under `el`, every translate()
    on the way down accumulated; any other transform raises ValueError."""
    for child in el:
        here = _offset(child, base)
        yield child, here
        yield from _descendants(child, here)


def collect(root):
    """(nodes, edges, labels, lines, stray): nodes {id: box}, edges [(id, segments)],
    labels [(x0, y0, x1, y1, owning edge id or None, lines of text)],
    lines {node id: lines of text in its box}."""
    nodes, edges, labels = {}, [], []
    unmeasured, lines, stray, containers = [], {}, [], []

    def walk(el, base, bad=None):
        cls, tag = _classes(el), _local(el.tag)
        if tag in _NOT_DRAWN:  # arrowheads and icons: templates, not lines on the page
            return
        try:
            here = _offset(el, base)
        except ValueError as exc:
            # Only fatal under something measured: a scaled icon in <defs>
            # moves nothing the checker reads.
            here, bad = base, bad or str(exc)
        measured = (tag == "g" and ("node" in cls or "edgeLabel" in cls)) or (
            tag == "path" and "flowchart-link" in cls)
        if measured and bad:
            raise ValueError(f"{_short(el.get('id') or tag)}: {bad}")
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
            eid = el.get("id") or f"edge{len(edges)}"
            try:
                segs = _segments(path_subpaths(el.get("d"), here))
            except ValueError as exc:
                raise ValueError(f"edge {_short(eid)}: {exc}") from exc
            if not segs:
                raise ValueError(f"edge {_short(eid)} has no line to measure")
            edges.append((eid, segs))
            return
        if tag == "g" and "edgeLabel" in cls:
            owner = next((g.get("data-id") for g in el.iter() if g.get("data-id")), None)
            for fo, inner in _descendants(el, here):
                if _local(fo.tag) == "foreignObject":
                    w, h = float(fo.get("width") or 0), float(fo.get("height") or 0)
                    if w > 0 and h > 0:
                        labels.append((inner[0], inner[1], inner[0] + w, inner[1] + h, owner,
                                       round(h / LINE_HEIGHT)))
            return
        if tag == "g" and "edgePaths" in cls and len(el):
            containers.append(el)
        if "edge-thickness-invisible" in cls:  # a `~~~` layout link: never drawn
            return
        if tag in ("path", "line", "polyline"):
            # A line outside every node that is not a recognised edge: if
            # Mermaid renames its edge class, the edges must not vanish into
            # a PASS with 0 edges.
            stray.append(el.get("id") or el.get("class") or tag)
            return
        for child in el:
            walk(child, here, bad)

    walk(root, (0.0, 0.0))
    if unmeasured:
        # A box the checker cannot see is a box no line is tested against:
        # that is "could not tell", never a quiet PASS.
        raise ValueError(f"{len(unmeasured)} node shape(s) not measurable: "
                         + ", ".join(_short(n) for n in unmeasured[:4]))
    if containers and not edges:
        stray.append("an edgePaths group with content")
    return nodes, edges, labels, lines, stray


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


def _ends(segs, nodes):
    """The node boxes nearest each end of an edge: its source and target."""
    def nearest(p):
        return min(nodes, key=lambda n: _box_dist(p, nodes[n])) if nodes else None
    return {nearest(segs[0][0]), nearest(segs[-1][1])} - {None}


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
        return _judge(*collect(root))
    except ValueError as exc:
        return {"status": UNKNOWN, "why": f"could not read the geometry: {exc}"}
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # A checker bug is "could not tell" too: never a crash, never a PASS.
        return {"status": UNKNOWN, "why": f"checker error: {type(exc).__name__}: {exc}"}


def _judge(nodes, edges, labels, lines, stray):  # pylint: disable=too-many-locals
    """The verdict on collected geometry. No measured node is no measurement,
    and a line outside the nodes that is not a recognised edge is a line no
    crossing was tested against."""
    if not nodes:
        return {"status": UNKNOWN, "nodes": 0, "edges": len(edges),
                "why": (f"{len(edges)} edge(s) but no node box measured" if edges
                        else "no node boxes found: nothing was measured")}
    if stray:
        return {"status": UNKNOWN, "nodes": len(nodes), "edges": len(edges),
                "why": (f"{len(stray)} line(s) outside the nodes not recognised as an edge "
                        f"({', '.join(_short(x) for x in stray[:3])}); {len(edges)} edge(s) measured")}
    ends = [(eid, poly, _ends(poly, nodes)) for eid, poly in edges]
    crossings = []
    for i, (ida, pa, ea) in enumerate(ends):
        for idb, pb, eb in ends[i + 1:]:
            near = [nodes[n] for n in ea | eb]
            for sa in pa:
                hit = None
                for sb in pb:
                    x = _seg_cross(sa[0], sa[1], sb[0], sb[1])
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
            if any(_seg_hits_box(a, b, inner) for a, b in poly):
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
                         and any(_seg_hits_box(a, b, inner) for a, b in poly)]
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
