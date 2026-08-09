"""
vsdx_writer.py - Build native Microsoft Visio .vsdx files from scratch.

Why this exists: the PyPI `vsdx` package can only OPEN an existing .vsdx.
There is no library that creates one. This module writes the OOXML package
(MS-VSDX) directly, so no Visio install and no template file is required.

Units are INCHES. Origin is BOTTOM-LEFT (Visio convention, not screen convention).

Usage:
    from vsdx_writer import VisioDocument
    doc = VisioDocument()
    p = doc.add_page("Network", width=11, height=8.5)
    a = p.add_shape("Firewall", 2, 6, kind="box", fill="#C00000")
    b = p.add_shape("Core Switch", 6, 6, kind="box")
    p.connect(a, b, label="10Gb")
    doc.save("out.vsdx")
"""
from __future__ import annotations

import math
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape

NS = "http://schemas.microsoft.com/office/visio/2012/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
VREL = "http://schemas.microsoft.com/visio/2010/relationships"

# ---------------------------------------------------------------------------
# Geometry definitions. Coordinates are fractions of Width/Height so the shape
# stays correct when the user drags a handle in Visio.
# ---------------------------------------------------------------------------
GEOMETRY = {
    "box":      [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)],
    "diamond":  [(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5), (0.5, 0)],
    "hexagon":  [(0.25, 0), (0.75, 0), (1, 0.5), (0.75, 1), (0.25, 1), (0, 0.5), (0.25, 0)],
    "parallelogram": [(0.2, 0), (1, 0), (0.8, 1), (0, 1), (0.2, 0)],
    "triangle": [(0.5, 1), (1, 0), (0, 0), (0.5, 1)],
}
ROUND_KINDS = {"ellipse", "cylinder", "cloud", "rounded"}
VALID_KINDS = set(GEOMETRY) | ROUND_KINDS

DEFAULT_FILL = "#DAE3F3"
DEFAULT_LINE = "#2F5496"
DEFAULT_TEXT = "#000000"


def _cell(n, v, f=None):
    if f:
        return f'<Cell N="{n}" V="{v}" F="{escape(f)}"/>'
    return f'<Cell N="{n}" V="{v}"/>'


class Shape:
    __slots__ = ("id", "text", "x", "y", "w", "h", "kind", "fill", "line",
                 "text_color", "font_size", "line_weight")

    def __init__(self, sid, text, x, y, w, h, kind, fill, line, text_color,
                 font_size, line_weight):
        self.id = sid
        self.text = text
        self.x, self.y, self.w, self.h = x, y, w, h
        self.kind = kind
        self.fill, self.line, self.text_color = fill, line, text_color
        self.font_size, self.line_weight = font_size, line_weight

    # centre-based bounds
    @property
    def left(self):   return self.x - self.w / 2
    @property
    def right(self):  return self.x + self.w / 2
    @property
    def bottom(self): return self.y - self.h / 2
    @property
    def top(self):    return self.y + self.h / 2

    def _char_section(self):
        return (
            '<Section N="Character">'
            f'<Row IX="0">{_cell("Color", self.text_color)}'
            f'{_cell("Size", f"{self.font_size / 72:.6f}")}</Row>'
            '</Section>'
        )

    def _geometry(self):
        if self.kind in ROUND_KINDS:
            # Ellipse primitive; cylinder/cloud degrade to ellipse rather than
            # silently producing nothing.
            return (
                '<Section N="Geometry" IX="0">'
                f'{_cell("NoFill", 0)}{_cell("NoLine", 0)}'
                '<Row T="Ellipse" IX="1">'
                f'{_cell("X", self.w / 2, "Width*0.5")}'
                f'{_cell("Y", self.h / 2, "Height*0.5")}'
                f'{_cell("A", self.w, "Width*1")}'
                f'{_cell("B", self.h / 2, "Height*0.5")}'
                f'{_cell("C", self.w / 2, "Width*0.5")}'
                f'{_cell("D", self.h, "Height*1")}'
                '</Row></Section>'
            )
        pts = GEOMETRY[self.kind]
        rows = [f'<Section N="Geometry" IX="0">{_cell("NoFill", 0)}{_cell("NoLine", 0)}']
        for i, (fx, fy) in enumerate(pts):
            tag = "MoveTo" if i == 0 else "LineTo"
            rows.append(
                f'<Row T="{tag}" IX="{i + 1}">'
                f'{_cell("X", round(fx * self.w, 6), f"Width*{fx}")}'
                f'{_cell("Y", round(fy * self.h, 6), f"Height*{fy}")}</Row>'
            )
        rows.append("</Section>")
        return "".join(rows)

    def to_xml(self):
        return (
            f'<Shape ID="{self.id}" NameU="Shape{self.id}" Name="Shape{self.id}" '
            'Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">'
            f'{_cell("PinX", round(self.x, 6))}{_cell("PinY", round(self.y, 6))}'
            f'{_cell("Width", round(self.w, 6))}{_cell("Height", round(self.h, 6))}'
            f'{_cell("LocPinX", round(self.w / 2, 6), "Width*0.5")}'
            f'{_cell("LocPinY", round(self.h / 2, 6), "Height*0.5")}'
            f'{_cell("Angle", 0)}{_cell("FlipX", 0)}{_cell("FlipY", 0)}'
            f'{_cell("FillForegnd", self.fill)}{_cell("FillPattern", 1)}'
            f'{_cell("LineColor", self.line)}{_cell("LineWeight", self.line_weight)}'
            f'{_cell("LinePattern", 1)}{_cell("Rounding", 0.0625 if self.kind == "rounded" else 0)}'
            f'{_cell("VerticalAlign", 1)}{_cell("TextBkgnd", 0)}'
            f'{self._char_section()}{self._geometry()}'
            f'<Text>{escape(self.text)}</Text>'
            '</Shape>'
        )


class Connector:
    """1-D shape with dynamic glue, so Visio reroutes it when shapes move."""
    __slots__ = ("id", "src", "dst", "label", "color", "weight", "arrow", "dashed")

    def __init__(self, cid, src, dst, label, color, weight, arrow, dashed):
        self.id, self.src, self.dst = cid, src, dst
        self.label, self.color, self.weight = label, color, weight
        self.arrow, self.dashed = arrow, dashed

    def _endpoints(self):
        """Trim the line to each shape's bounding box so arrowheads land on the edge."""
        sx, sy, dx, dy = self.src.x, self.src.y, self.dst.x, self.dst.y
        vx, vy = dx - sx, dy - sy
        if vx == 0 and vy == 0:
            return sx, sy, dx, dy

        def trim(shape, ox, oy, ux, uy):
            hw, hh = shape.w / 2, shape.h / 2
            ts = []
            if ux:
                ts.append(hw / abs(ux))
            if uy:
                ts.append(hh / abs(uy))
            t = min(ts)
            return ox + ux * t, oy + uy * t

        n = math.hypot(vx, vy)
        ux, uy = vx / n, vy / n
        bx, by = trim(self.src, sx, sy, ux, uy)
        ex, ey = trim(self.dst, dx, dy, -ux, -uy)
        return bx, by, ex, ey

    def to_xml(self):
        bx, by, ex, ey = self._endpoints()
        length = math.hypot(ex - bx, ey - by) or 0.001
        angle = math.atan2(ey - by, ex - bx)
        return (
            f'<Shape ID="{self.id}" NameU="Conn{self.id}" Name="Conn{self.id}" '
            'Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">'
            f'{_cell("PinX", round((bx + ex) / 2, 6))}{_cell("PinY", round((by + ey) / 2, 6))}'
            f'{_cell("Width", round(length, 6))}{_cell("Height", 0)}'
            f'{_cell("LocPinX", round(length / 2, 6), "Width*0.5")}'
            f'{_cell("LocPinY", 0, "Height*0.5")}'
            f'{_cell("Angle", round(angle, 6))}'
            f'{_cell("BeginX", round(bx, 6))}{_cell("BeginY", round(by, 6))}'
            f'{_cell("EndX", round(ex, 6))}{_cell("EndY", round(ey, 6))}'
            f'{_cell("ObjType", 2)}{_cell("NoFill", 1)}'
            f'{_cell("LineColor", self.color)}{_cell("LineWeight", self.weight)}'
            f'{_cell("LinePattern", 2 if self.dashed else 1)}'
            f'{_cell("EndArrow", 4 if self.arrow else 0)}{_cell("BeginArrow", 0)}'
            f'{_cell("ShapeRouteStyle", 16)}{_cell("ConLineRouteExt", 0)}'
            f'{_cell("TextBkgnd", 1)}'
            '<Section N="Geometry" IX="0">'
            f'{_cell("NoFill", 1)}{_cell("NoLine", 0)}'
            f'<Row T="MoveTo" IX="1">{_cell("X", 0)}{_cell("Y", 0)}</Row>'
            f'<Row T="LineTo" IX="2">{_cell("X", round(length, 6), "Width")}{_cell("Y", 0)}</Row>'
            '</Section>'
            f'<Text>{escape(self.label)}</Text>'
            '</Shape>'
        )

    def connects_xml(self):
        # FromPart 9 = begin point, 12 = end point. ToPart 3 = dynamic glue to
        # the whole shape, which is what lets Visio re-route on drag.
        return (
            f'<Connect FromSheet="{self.id}" FromCell="BeginX" FromPart="9" '
            f'ToSheet="{self.src.id}" ToCell="PinX" ToPart="3"/>'
            f'<Connect FromSheet="{self.id}" FromCell="EndX" FromPart="12" '
            f'ToSheet="{self.dst.id}" ToCell="PinX" ToPart="3"/>'
        )


class Page:
    def __init__(self, doc, name, width, height):
        self.doc, self.name = doc, name
        self.width, self.height = width, height
        self.shapes: list[Shape] = []
        self.connectors: list[Connector] = []

    def add_shape(self, text, x, y, w=1.75, h=0.85, kind="box",
                  fill=DEFAULT_FILL, line=DEFAULT_LINE, text_color=DEFAULT_TEXT,
                  font_size=10, line_weight=0.01):
        if kind not in VALID_KINDS:
            raise ValueError(f"kind must be one of {sorted(VALID_KINDS)}, got {kind!r}")
        s = Shape(self.doc._next_id(), text, x, y, w, h, kind, fill, line,
                  text_color, font_size, line_weight)
        self.shapes.append(s)
        return s

    def connect(self, src, dst, label="", color="#404040", weight=0.01,
                arrow=True, dashed=False):
        c = Connector(self.doc._next_id(), src, dst, label, color, weight,
                      arrow, dashed)
        self.connectors.append(c)
        return c

    def contents_xml(self):
        body = "".join(s.to_xml() for s in self.shapes)
        body += "".join(c.to_xml() for c in self.connectors)
        conn = "".join(c.connects_xml() for c in self.connectors)
        conn_block = f"<Connects>{conn}</Connects>" if conn else ""
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<PageContents xmlns="{NS}" xmlns:r="{R_NS}" xml:space="preserve">'
            f'<Shapes>{body}</Shapes>{conn_block}</PageContents>'
        )


class VisioDocument:
    def __init__(self):
        self.pages: list[Page] = []
        self._id = 0

    def _next_id(self):
        self._id += 1
        return self._id

    def add_page(self, name="Page-1", width=11.0, height=8.5):
        p = Page(self, name, width, height)
        self.pages.append(p)
        return p

    # -- package parts ------------------------------------------------------
    def _content_types(self):
        ov = "".join(
            f'<Override PartName="/visio/pages/page{i + 1}.xml" '
            'ContentType="application/vnd.ms-visio.page+xml"/>'
            for i in range(len(self.pages))
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>'
            '<Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>'
            f'{ov}'
            '<Override PartName="/visio/windows.xml" ContentType="application/vnd.ms-visio.windows+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType='
            '"application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            '</Types>'
        )

    def _root_rels(self):
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{VREL}/document" Target="visio/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org'
            '/package/2006/relationships/metadata/core-properties"'
            ' Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org'
            '/officeDocument/2006/relationships/extended-properties"'
            ' Target="docProps/app.xml"/>'
            '</Relationships>'
        )

    def _document(self):
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<VisioDocument xmlns="{NS}" xmlns:r="{R_NS}" xml:space="preserve">'
            '<DocumentSettings TopPage="0" DefaultTextStyle="0" DefaultLineStyle="0" '
            'DefaultFillStyle="0" DefaultGuideStyle="0">'
            '<GlueSettings>9</GlueSettings><SnapSettings>65847</SnapSettings>'
            '<SnapExtensions>34</SnapExtensions><DynamicGridEnabled>1</DynamicGridEnabled>'
            '<ProtectStyles>0</ProtectStyles><ProtectShapes>0</ProtectShapes>'
            '<ProtectMasters>0</ProtectMasters><ProtectBkgnds>0</ProtectBkgnds>'
            '</DocumentSettings>'
            '<Colors/>'
            '<FaceNames>'
            '<FaceName NameU="Calibri" UnicodeRanges="-536859905 -1073732485 9 0" '
            'CharSets="536871423 0" Panos="2 15 5 2 2 2 4 3 2 4" Flags="325"/>'
            '</FaceNames>'
            '<StyleSheets>'
            '<StyleSheet ID="0" NameU="No Style" Name="No Style">'
            '<Cell N="EnableLineProps" V="1"/><Cell N="EnableFillProps" V="1"/>'
            '<Cell N="EnableTextProps" V="1"/><Cell N="LineWeight" V="0.01"/>'
            '<Cell N="LineColor" V="#000000"/><Cell N="LinePattern" V="1"/>'
            '<Cell N="FillForegnd" V="#ffffff"/><Cell N="FillPattern" V="1"/>'
            '<Section N="Character"><Row IX="0">'
            '<Cell N="Font" V="Calibri"/><Cell N="Color" V="#000000"/>'
            '<Cell N="Size" V="0.1666666666666667"/></Row></Section>'
            '<Section N="Paragraph"><Row IX="0"><Cell N="HorzAlign" V="1"/></Row></Section>'
            '</StyleSheet>'
            '</StyleSheets>'
            '<DocumentSheet NameU="TheDoc" Name="TheDoc" LineStyle="0" FillStyle="0" TextStyle="0"/>'
            '</VisioDocument>'
        )

    def _document_rels(self):
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{VREL}/pages" Target="pages/pages.xml"/>'
            f'<Relationship Id="rId2" Type="{VREL}/windows" Target="windows.xml"/>'
            '</Relationships>'
        )

    def _pages(self):
        out = []
        for i, p in enumerate(self.pages):
            out.append(
                f'<Page ID="{i}" NameU="{escape(p.name)}" Name="{escape(p.name)}" '
                f'ViewScale="-1" ViewCenterX="{p.width / 2}" ViewCenterY="{p.height / 2}">'
                '<PageSheet LineStyle="0" FillStyle="0" TextStyle="0">'
                f'{_cell("PageWidth", p.width)}{_cell("PageHeight", p.height)}'
                f'{_cell("ShdwOffsetX", 0.125)}{_cell("ShdwOffsetY", -0.125)}'
                f'{_cell("PageScale", 1)}{_cell("DrawingScale", 1)}'
                f'{_cell("DrawingSizeType", 3)}{_cell("DrawingScaleType", 0)}'
                f'{_cell("InhibitSnap", 0)}{_cell("UIVisibility", 0)}'
                '</PageSheet>'
                f'<Rel r:id="rId{i + 1}"/></Page>'
            )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Pages xmlns="{NS}" xmlns:r="{R_NS}" xml:space="preserve">'
            f'{"".join(out)}</Pages>'
        )

    def _pages_rels(self):
        rels = "".join(
            f'<Relationship Id="rId{i + 1}" Type="{VREL}/page" Target="page{i + 1}.xml"/>'
            for i in range(len(self.pages))
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{rels}</Relationships>'
        )

    def _windows(self):
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Windows xmlns="{NS}" xmlns:r="{R_NS}" ClientWidth="1920" ClientHeight="1080">'
            '<Window ID="0" WindowType="Drawing" WindowState="1073741824" Page="0" '
            'ViewScale="-1" ViewCenterX="5.5" ViewCenterY="4.25"/></Windows>'
        )

    def _core(self):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{ts}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{ts}</dcterms:modified>'
            '</cp:coreProperties>'
        )

    def _app(self):
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            '<Application>Microsoft Visio</Application><AppVersion>16.0000</AppVersion>'
            '</Properties>'
        )

    def save(self, path):
        if not self.pages:
            raise ValueError("document has no pages")
        parts = {
            "[Content_Types].xml": self._content_types(),
            "_rels/.rels": self._root_rels(),
            "docProps/core.xml": self._core(),
            "docProps/app.xml": self._app(),
            "visio/document.xml": self._document(),
            "visio/_rels/document.xml.rels": self._document_rels(),
            "visio/windows.xml": self._windows(),
            "visio/pages/pages.xml": self._pages(),
            "visio/pages/_rels/pages.xml.rels": self._pages_rels(),
        }
        for i, p in enumerate(self.pages):
            parts[f"visio/pages/page{i + 1}.xml"] = p.contents_xml()

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            # [Content_Types].xml must be the first entry in an OPC package.
            z.writestr("[Content_Types].xml", parts.pop("[Content_Types].xml"))
            for name, data in parts.items():
                z.writestr(name, data)
        return path
