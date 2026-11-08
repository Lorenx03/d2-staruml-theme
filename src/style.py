"""Everything that defines the StarUML look: colours, stereotypes, sizes, edge kinds."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ICON_DIR = Path(__file__).resolve().parent / "icons"

BLACK = '"#000000"'
FONT_SIZE = 13


@dataclass(frozen=True)
class Kind:
    stereotype: str | None  # text between « » (None: no stereotype line)
    fill: str = "#FFFFFF"
    icon: str | None = None  # file name in icons/
    enum: bool = False  # members are literals in a single compartment


# Keys are what you write in the comment: # <<entity>>
KINDS: dict[str, Kind] = {
    "class": Kind(None),
    "boundary": Kind("boundary", "#DAEDF8", "boundary.svg"),
    "control": Kind("control", "#F8D9DC", "control.svg"),
    "entity": Kind("entity", "#FFFFDB", "entity.svg"),
    "bean": Kind("bean"),
    "enumeration": Kind("enumeration", enum=True),
    "interface": Kind("interface"),
}
KIND_ALIASES = {"enum": "enumeration"}


def kind_for(stereotype: str | None) -> Kind:
    """Kind for a stereotype comment; unknown stereotypes get a plain white box."""
    if stereotype is None:
        return KINDS["class"]
    key = stereotype.strip().lower()
    key = KIND_ALIASES.get(key, key)
    return KINDS.get(key, Kind(stereotype.strip()))


# ---------------------------------------------------------------- cell styles
# Text cells. `bold` is measured wrongly by d2 0.9, so the CLI maps fonts as:
# regular -> Arial, "bold" -> Arial (exact measuring), "italic" -> Arial Bold.
# Class names therefore use italic to come out bold.
_TEXT = f'stroke: transparent; fill: transparent; font-size: {FONT_SIZE}; font-color: {BLACK}'

BOX_STYLE = 'stroke: "#000000"; stroke-width: 1; fill: "{fill}"; shadow: true'
MEMBER = f'height: 17; label.near: center-left; style: {{{_TEXT}; bold: false; italic: false}}'
NAME = f'height: 18; label.near: center-center; style: {{{_TEXT}; bold: false; italic: true}}'
STEREO = f'height: 16; label.near: center-center; style: {{{_TEXT}; bold: false; italic: false}}'
def stereo_icon(icon: Path) -> str:
    return (
        f'height: 26; label.near: bottom-center; icon: "{icon}"; icon.near: top-right; '
        f"style: {{{_TEXT}; bold: false; italic: false}}"
    )


def _pad(height: int) -> str:
    return f'label: ""; height: {height}; style: {{stroke: transparent; fill: transparent}}'


def _gradient(height: int, *lines_at: int) -> str:
    """A cell whose fill draws 1px black lines at the given y offsets.

    d2 cells have no padding, so compartment lines are gradient-filled cells:
    transparent except for 1px bands, which leaves space above and below.
    """
    clear = "#00000000"
    stops = [f"{clear} 0%"]
    for y in lines_at:
        a, b = 100 * y / height, 100 * (y + 1) / height
        stops += [f"{clear} {a:.3f}%", f"#000000 {a:.3f}%", f"#000000 {b:.3f}%", f"{clear} {b:.3f}%"]
    stops.append(f"{clear} 100%")
    fill = "linear-gradient(" + ", ".join(stops) + ")"
    return f'label: ""; height: {height}; style: {{stroke: transparent; fill: "{fill}"}}'


PAD_TOP_PLAIN = _pad(4)  # above the name of a box without a stereotype
PAD_TOP_STEREO = _pad(3)  # above a stereotype line without an icon
PAD_BOTTOM = _pad(4)  # after the last member
SEP = _gradient(7, 3)  # 3px space, line, 3px space
EMPTY = _gradient(16, 3, 12)  # an empty compartment between two others
EMPTY_LAST = _gradient(12, 3)  # an empty compartment at the bottom of a box
EMPTY_BOTH = _gradient(21, 3, 12)  # no attributes and no operations: two empty compartments

# ---------------------------------------------------------------- edges
EDGE_BASE = f'style: {{stroke: {BLACK}; stroke-width: 1; font-size: {FONT_SIZE}; font-color: {BLACK}; italic: false}}'

EDGE_KINDS: dict[str, list[str]] = {
    "assoc": ["target-arrowhead.shape: arrow"],
    "dep": ["style.stroke-dash: 4", "target-arrowhead.shape: arrow"],
    "gen": ["target-arrowhead: {shape: triangle; style.filled: false}"],
    "real": ["style.stroke-dash: 4", "target-arrowhead: {shape: triangle; style.filled: false}"],
    "comp": ["target-arrowhead: {shape: diamond; style.filled: true}"],
    "aggr": ["target-arrowhead: {shape: diamond; style.filled: false}"],
}
EDGE_ALIASES = {
    "association": "assoc",
    "dependency": "dep",
    "generalization": "gen",
    "inheritance": "gen",
    "realization": "real",
    "implementation": "real",
    "composition": "comp",
    "aggregation": "aggr",
}


def edge_kind(name: str) -> list[str] | None:
    key = name.strip().lower()
    return EDGE_KINDS.get(EDGE_ALIASES.get(key, key))
