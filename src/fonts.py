"""The bundled fonts: fonts/<Family>/ holds one family, as downloaded from
Google Fonts. d2 can't use variable fonts, so we pick the static Regular and
Bold files (from the folder itself or its static/ sub-folder).

For PNG output, `rsvg-convert` can't read the fonts d2 embeds in the SVG; it
looks fonts up with fontconfig instead. `fontconfig_env` sets up a fontconfig
that knows only the two picked files, under the fixed family name
`PNG_FAMILY`, so the fonts don't have to be installed.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"
DEFAULT_FONT = "Inter"
PNG_FAMILY = "StarUML Text"

FONT_SUFFIXES = {".ttf", ".otf"}
# "Inter_18pt-Regular", "Outfit-Regular", "Arial Regular"; not "SemiBold" or "BoldItalic"
REGULAR = re.compile(r"[-_ ]Regular$", re.IGNORECASE)
BOLD = re.compile(r"[-_ ]Bold$", re.IGNORECASE)


class FontError(Exception):
    """The font can't be found or has no Regular/Bold files."""


@dataclass(frozen=True)
class Font:
    name: str
    regular: Path
    bold: Path


def _prefix(stem: str) -> str:
    """'Inter_18pt-Regular' -> 'Inter_18pt-', 'Arial' -> 'Arial ' (to pair it with 'Arial Bold')."""
    match = REGULAR.search(stem)
    return stem[: match.start() + 1] if match else stem + " "


def _font_files(folder: Path) -> list[Path]:
    # Shallow files first, then by name: Inter_18pt (text sizes) before Inter_24pt/28pt.
    files = (p for p in folder.rglob("*") if p.suffix.lower() in FONT_SUFFIXES and p.is_file())
    return sorted(files, key=lambda p: (len(p.relative_to(folder).parts), p.name.lower()))


def load_font(folder: Path) -> Font:
    files = _font_files(folder)
    regulars = [p for p in files if REGULAR.search(p.stem) or p.stem.lower() == folder.name.lower()]
    if not regulars:
        raise FontError(f"no Regular font file (like Name-Regular.ttf) in {folder}")
    regular = regulars[0]
    bolds = [p for p in files if BOLD.search(p.stem)]
    if not bolds:
        raise FontError(f"no Bold font file (like Name-Bold.ttf) in {folder}")
    # Prefer the Bold of the same cut: Inter_18pt-Regular goes with Inter_18pt-Bold.
    prefix = _prefix(regular.stem).lower()
    bold = next((p for p in bolds if p.stem.lower().startswith(prefix)), bolds[0])
    return Font(folder.name, regular, bold)


def available_fonts(fonts_dir: Path = FONTS_DIR) -> list[str]:
    if not fonts_dir.is_dir():
        return []
    names = []
    for folder in sorted(p for p in fonts_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
        try:
            load_font(folder)
        except FontError:
            continue
        names.append(folder.name)
    return names


def find_font(name: str, fonts_dir: Path = FONTS_DIR) -> Font:
    """A family in `fonts_dir` by folder name (any case), or a path to a font folder."""
    if fonts_dir.is_dir():
        for folder in fonts_dir.iterdir():
            if folder.is_dir() and folder.name.lower() == name.lower():
                return load_font(folder)
    path = Path(name).expanduser()
    if path.is_dir():
        return load_font(path)
    known = ", ".join(available_fonts(fonts_dir)) or "none"
    raise FontError(f"no font {name!r} in {fonts_dir}/ (available: {known}), and no folder by that name")


def fontconfig_env(font: Font, tmp: Path) -> dict[str, str]:
    """Environment for `rsvg-convert`: a fontconfig with just `font`, named `PNG_FAMILY`.
    PANGOCAIRO_BACKEND=fc makes pango use fontconfig on macOS too (not CoreText)."""
    font_dir = tmp / "fonts"
    font_dir.mkdir()
    for file in (font.regular, font.bold):
        shutil.copyfile(file, font_dir / file.name)
    config = tmp / "fonts.conf"
    config.write_text(
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n'
        "<fontconfig>\n"
        f"  <dir>{escape(str(font_dir))}</dir>\n"
        f"  <cachedir>{escape(str(tmp / 'cache'))}</cachedir>\n"
        '  <match target="scan">\n'
        f'    <edit name="family" mode="assign" binding="same"><string>{PNG_FAMILY}</string></edit>\n'
        "  </match>\n"
        "</fontconfig>\n",
        encoding="utf-8",
    )
    return {**os.environ, "FONTCONFIG_FILE": str(config), "PANGOCAIRO_BACKEND": "fc"}


# ---------------------------------------------------------------- measuring text
# Use case ovals are sized to their name, so the converter needs text widths.
# Only advance widths are read (cmap + hmtx), no kerning: a hair wide, never narrow.


@lru_cache(maxsize=None)
def _metrics(path: Path) -> tuple[dict[int, int], tuple[int, ...], int]:
    """(code point -> glyph id, advance width per glyph, units per em) of a .ttf/.otf."""
    data = path.read_bytes()
    u16 = lambda at: struct.unpack_from(">H", data, at)[0]  # noqa: E731
    u32 = lambda at: struct.unpack_from(">I", data, at)[0]  # noqa: E731
    tables = {data[12 + 16 * i : 16 + 16 * i].decode("latin-1"): u32(20 + 16 * i) for i in range(u16(4))}
    units_per_em = u16(tables["head"] + 18)
    n_metrics = u16(tables["hhea"] + 34)
    advances = tuple(u16(tables["hmtx"] + 4 * i) for i in range(n_metrics))

    cmap, subtables = tables["cmap"], {}
    for i in range(u16(tables["cmap"] + 2)):
        record = cmap + 4 + 8 * i
        subtables[(u16(record), u16(record + 2))] = cmap + u32(record + 4)
    glyphs: dict[int, int] = {}
    for key in ((3, 10), (0, 4), (0, 6), (3, 1), (0, 3)):
        at = subtables.get(key)
        if at is None:
            continue
        if u16(at) == 12:
            for g in range(u32(at + 12)):
                start, end, glyph = struct.unpack_from(">III", data, at + 16 + 12 * g)
                glyphs.update((c, glyph + c - start) for c in range(start, end + 1))
            break
        if u16(at) == 4:
            segs = u16(at + 6) // 2
            ends, starts = at + 14, at + 16 + 2 * segs
            deltas, offsets = starts + 2 * segs, starts + 4 * segs
            for s in range(segs):
                start, end = u16(starts + 2 * s), u16(ends + 2 * s)
                delta, offset = u16(deltas + 2 * s), u16(offsets + 2 * s)
                for c in range(start, min(end, 0xFFFE) + 1):
                    if offset == 0:
                        glyphs[c] = (c + delta) & 0xFFFF
                    else:
                        g = u16(offsets + 2 * s + offset + 2 * (c - start))
                        glyphs[c] = (g + delta) & 0xFFFF if g else 0
            break
    return glyphs, advances, units_per_em


def text_width(path: Path, text: str, size: float) -> float:
    """Width in px of one line of `text` set in the font file at `path`."""
    glyphs, advances, units_per_em = _metrics(path)
    units = sum(advances[min(glyphs.get(ord(c), 0), len(advances) - 1)] for c in text)
    return units * size / units_per_em
