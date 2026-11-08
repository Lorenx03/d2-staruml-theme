"""Touch up a d2 SVG so it looks more like StarUML.

d2 has no options for these, so they are patched in the SVG text:
  - open "V" arrowheads instead of d2's filled `arrow` heads
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


def _open_arrow(m: re.Match[str]) -> str:
    tip_x, mid_y, h, color = m.group(1), m.group(2), m.group(3), m.group(4)
    return (
        f'<polyline points="0.5,0.5 {tip_x},{mid_y} 0.5,{float(h) - 0.5:g}" '
        f'fill="none" stroke="{color}" stroke-width="1" stroke-linejoin="miter" />'
    )


def postprocess_svg(svg: str, png_fonts: bool = False) -> str:
    svg = ARROW.sub(_open_arrow, svg)
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
