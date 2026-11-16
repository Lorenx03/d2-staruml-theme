"""Touch up a d2 SVG so it looks more like StarUML.

d2 has no options for these, so they are patched in the SVG text:
  - open "V" arrowheads instead of d2's filled `arrow` heads (at either end)
  - a soft grey drop shadow instead of d2's blue-grey one
  - optionally (for PNG via rsvg-convert, which can't read the fonts d2 embeds)
    point the text at the font family that `fonts.fontconfig_env` sets up
"""

from __future__ import annotations

import re
from pathlib import Path

from .fonts import PNG_FAMILY

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


def postprocess_svg(svg: str, png_fonts: bool = False) -> str:
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
