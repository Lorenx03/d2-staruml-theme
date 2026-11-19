"""Touch up a d2 SVG so it looks more like StarUML.

d2 has no options for these, so they are patched in the SVG text:
  - open "V" arrowheads instead of d2's filled `arrow` heads (at either end)
  - a soft grey drop shadow instead of d2's blue-grey one
  - activity diagrams: fork/join bars stretched to span their flows, which run
    straight into them; the dot of final nodes and the cross of flow-final nodes
  - optionally (for PNG via rsvg-convert, which can't read the fonts d2 embeds)
    point the text at the font family that `fonts.fontconfig_env` sets up
"""

from __future__ import annotations

import base64
import binascii
import html
import math
import re
from pathlib import Path

from .fonts import PNG_FAMILY
from .style import BAR_CLASS, FINAL_CLASS, FLOW_FINAL_CLASS

PNG_FONTS_CSS = (
    "<style>"
    f".text,.text-bold{{font-family:'{PNG_FAMILY}',sans-serif!important;font-weight:normal!important}}"
    f".text-italic{{font-family:'{PNG_FAMILY}',sans-serif!important;font-weight:bold!important;font-style:normal!important}}"
    "</style>"
)

SHADOW_COLOR = "#000000"
SHADOW_OPACITY = "0.22"
SHADOW_BLUR = "1.2"
SHADOW_DX, SHADOW_DY = "4", "4"

# d2's `arrow` head: polygon "0,0 L,H/2 0,H N,H/2" (tip at L, notch at N), filled.
ARROW = re.compile(r'<polygon points="0,0 ([\d.]+),([\d.]+) 0,([\d.]+) [\d.]+,\2" fill="([^"]+)"[^>]*/>')


# The same head at the start of a line (`A <- B`): "0,H/2 L,0 N,H/2 L,H", tip at 0,
# notch N inside the head (N < L). A filled diamond has the same shape of points
# ("0,H/2 W/2,0 W,H/2 W/2,H") but with its third point beyond L: it must be left alone.
ARROW_START = re.compile(r'<polygon points="0,([\d.]+) ([\d.]+),0 ([\d.]+),\1 \2,([\d.]+)" fill="([^"]+)"[^>]*/>')


def _open_arrow_start(m: re.Match[str]) -> str:
    mid_y, length, notch, h, color = m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4)), m.group(5)
    if notch >= length:  # a diamond, not an arrowhead
        return m.group(0)
    return (
        f'<polyline points="{length - 0.5:g},0.5 0,{mid_y} {length - 0.5:g},{h - 0.5:g}" '
        f'fill="none" stroke="{color}" stroke-width="1" stroke-linejoin="miter" />'
    )


def _open_arrow(m: re.Match[str]) -> str:
    tip_x, mid_y, h, color = m.group(1), m.group(2), m.group(3), m.group(4)
    return (
        f'<polyline points="0.5,0.5 {tip_x},{mid_y} 0.5,{float(h) - 0.5:g}" '
        f'fill="none" stroke="{color}" stroke-width="1" stroke-linejoin="miter" />'
    )


# ---------------------------------------------------------------- activity diagrams
# d2 names each shape's and edge's <g> by its base64 id, followed by its d2 classes.
SHAPE_GROUP = re.compile(r'<g class="([A-Za-z0-9+/=]+)((?: [^"]*)?)"><g class="shape"[^>]*>(<rect [^>]*/>|<ellipse [^>]*/>)</g>')
EDGE_GROUP = re.compile(r'(<g class="([A-Za-z0-9+/=]+)">(?:<marker .*?</marker>)?\s*<path d=")([^"]*)(")', re.S)
EDGE_ID = re.compile(r"^(?:(?P<scope>.+?)\.)?\((?P<a>.+?) (?:<->|->|<-|--) (?P<b>.+?)\)\[\d+\]$")
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
BAR_MARGIN = 30  # how far a fork/join bar reaches past its outermost flow
BAR_CLEARANCE = 10  # ... unless a shape beside it is closer than that: then it stops this far from it
BAR_MIN_MARGIN = 5  # but it always reaches at least this far past its outermost flow
FINAL_DOT = 0.55  # radius of a final node's dot, relative to its ring


def _decode(group_class: str) -> str | None:
    try:
        return html.unescape(base64.b64decode(group_class, validate=True).decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError):
        return None


def _attr(tag: str, name: str) -> float:
    return float(re.search(rf'\b{name}="([-\d.]+)"', tag).group(1))


def _box(shape: str) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) of a <rect> or <ellipse>."""
    if shape.startswith("<rect"):
        x, y = _attr(shape, "x"), _attr(shape, "y")
        return x, y, x + _attr(shape, "width"), y + _attr(shape, "height")
    cx, cy, rx, ry = (_attr(shape, a) for a in ("cx", "cy", "rx", "ry"))
    return cx - rx, cy - ry, cx + rx, cy + ry


class _Bar:
    def __init__(self, rect: str) -> None:
        self.x, self.y = _attr(rect, "x"), _attr(rect, "y")
        self.w, self.h = _attr(rect, "width"), _attr(rect, "height")
        self.horizontal = self.w >= self.h
        self.reach: list[float] = []  # where the flows meet it, along its length

    def distance(self, px: float, py: float) -> float:
        dx = max(self.x - px, 0, px - self.x - self.w)
        dy = max(self.y - py, 0, py - self.y - self.h)
        return math.hypot(dx, dy)

    def straighten(self, at_bar: tuple[float, float], other: tuple[float, float]) -> tuple[float, float] | None:
        """The point on the bar where a straight flow from `other` meets it (keeping the
        gap d2 left for an arrowhead), or None when `other` is beside the bar."""
        gap = self.distance(*at_bar)
        if self.horizontal:
            ox, oy = other
            if self.y <= oy <= self.y + self.h:
                return None
            self.reach.append(ox)
            return ox, (self.y - gap if oy < self.y else self.y + self.h + gap)
        ox, oy = other
        if self.x <= ox <= self.x + self.w:
            return None
        self.reach.append(oy)
        return (self.x - gap if ox < self.x else self.x + self.w + gap), oy

    def rect(self, tag: str, others: list[tuple[float, float, float, float]]) -> str:
        """The bar's <rect>, stretched along its length to span its flows, without
        running into the shapes beside it (`others`: their boxes)."""
        if not self.reach:
            return tag
        if self.horizontal:
            pos, length, across, x_or_y, size = self.x, self.w, (self.y, self.y + self.h), "x", "width"
            spans = [(x0, x1) for x0, y0, x1, y1 in others if y0 < across[1] and y1 > across[0]]
        else:
            pos, length, across, x_or_y, size = self.y, self.h, (self.x, self.x + self.w), "y", "height"
            spans = [(y0, y1) for x0, y0, x1, y1 in others if x0 < across[1] and x1 > across[0]]
        lo, hi = min(self.reach), max(self.reach)
        start, end = min(pos, lo - BAR_MARGIN), max(pos + length, hi + BAR_MARGIN)
        for a, b in spans:
            if b <= lo:  # a shape before the first flow
                start = max(start, min(b + BAR_CLEARANCE, lo - BAR_MIN_MARGIN))
            elif a >= hi:  # after the last one
                end = min(end, max(a - BAR_CLEARANCE, hi + BAR_MIN_MARGIN))
        tag = re.sub(rf'\b{x_or_y}="[-\d.]+"', f'{x_or_y}="{start:g}"', tag, count=1)
        return re.sub(rf'\b{size}="[-\d.]+"', f'{size}="{end - start:g}"', tag, count=1)


def _activity(svg: str) -> str:
    bars: dict[str, _Bar] = {}
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for m in SHAPE_GROUP.finditer(svg):
        key = _decode(m.group(1))
        if key is None:
            continue
        boxes[key] = _box(m.group(3))
        if BAR_CLASS in m.group(2).split() and m.group(3).startswith("<rect"):
            bars[key] = _Bar(m.group(3))
    if bars:
        svg = EDGE_GROUP.sub(lambda m: _straighten_flow(m, bars), svg)
        svg = SHAPE_GROUP.sub(lambda m: _stretch_bar(m, bars, boxes), svg)
    return SHAPE_GROUP.sub(_final_marks, svg)


def _straighten_flow(m: re.Match[str], bars: dict[str, _Bar]) -> str:
    """A flow into or out of a fork/join bar becomes a straight line, square to the bar."""
    ident = _decode(m.group(2))
    parsed = EDGE_ID.match(ident) if ident else None
    numbers = [float(n) for n in NUMBER.findall(m.group(3))]
    if not parsed or len(numbers) < 4:
        return m.group(0)
    scope = parsed.group("scope")
    ends = [f"{scope}.{parsed.group(e)}" if scope else parsed.group(e) for e in ("a", "b")]
    touching = [bars[e] for e in ends if e in bars]
    if len(touching) != 1:  # no bar, or a flow from one bar straight into another
        return m.group(0)
    bar = touching[0]
    first, last = (numbers[0], numbers[1]), (numbers[-2], numbers[-1])
    if bar.distance(*first) <= bar.distance(*last):  # the flow leaves the bar
        point = bar.straighten(first, last)
        start, end = point, last
    else:  # it enters the bar
        point = bar.straighten(last, first)
        start, end = first, point
    if point is None:
        return m.group(0)
    d = f"M {start[0]:g} {start[1]:g} L {end[0]:g} {end[1]:g}"
    return m.group(1) + d + m.group(4)


def _stretch_bar(m: re.Match[str], bars: dict[str, _Bar], boxes: dict[str, tuple[float, float, float, float]]) -> str:
    key = _decode(m.group(1))
    if key not in bars or BAR_CLASS not in m.group(2).split():
        return m.group(0)
    # shapes containing the bar (groups around it) are not in its way
    bar = _box(m.group(3))
    others = [
        b for k, b in boxes.items()
        if k != key and not (b[0] <= bar[0] and b[1] <= bar[1] and b[2] >= bar[2] and b[3] >= bar[3])
    ]  # fmt: skip
    return m.group(0).replace(m.group(3), bars[key].rect(m.group(3), others))


def _final_marks(m: re.Match[str]) -> str:
    """The dot inside a final node, the cross inside a flow-final node."""
    classes, shape = m.group(2).split(), m.group(3)
    if not shape.startswith("<ellipse") or not ({FINAL_CLASS, FLOW_FINAL_CLASS} & set(classes)):
        return m.group(0)
    r, cx, cy = _attr(shape, "rx"), _attr(shape, "cx"), _attr(shape, "cy")
    if FINAL_CLASS in classes:
        mark = f'<circle cx="{cx:g}" cy="{cy:g}" r="{r * FINAL_DOT:g}" fill="#000000" />'
    else:
        k = r / math.sqrt(2)
        mark = (
            f'<path d="M {cx - k:g} {cy - k:g} L {cx + k:g} {cy + k:g} M {cx + k:g} {cy - k:g} L {cx - k:g} {cy + k:g}" '
            f'stroke="#000000" stroke-width="1" fill="none" />'
        )
    return m.group(0) + mark


def postprocess_svg(svg: str, png_fonts: bool = False) -> str:
    svg = _activity(svg)
    svg = ARROW.sub(_open_arrow, svg)
    svg = ARROW_START.sub(_open_arrow_start, svg)
    if png_fonts:
        head, _, _ = svg.rpartition("</svg>")
        svg = head + PNG_FONTS_CSS + "</svg>"
    svg = re.sub(
        r'flood-color="[^"]*" flood-opacity="[^"]*"',
        f'flood-color="{SHADOW_COLOR}" flood-opacity="{SHADOW_OPACITY}"',
        svg,
    )
    svg = re.sub(r'(<feGaussianBlur stdDeviation=")[^"]*(")', rf"\g<1>{SHADOW_BLUR}\g<2>", svg)
    svg = re.sub(r'(<feOffset dx=")[^"]*(" dy=")[^"]*(")', rf"\g<1>{SHADOW_DX}\g<2>{SHADOW_DY}\g<3>", svg)
    return svg


def postprocess_file(path: Path, png_fonts: bool = False) -> None:
    path.write_text(postprocess_svg(path.read_text(encoding="utf-8"), png_fonts), encoding="utf-8")
