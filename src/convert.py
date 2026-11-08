"""Convert a plain d2 class diagram into the StarUML-styled d2 that `d2` renders.

Input is ordinary d2: classes are `shape: class` blocks, stereotypes are comments
(`# <<entity>>`) above a class or at the end of its first line, and relationship
kinds are comments on edges (`A -> B  # <<dep>>`). Everything the converter does
not recognise is copied through unchanged.

The scanner below only understands as much d2 as it needs: strings, block strings,
comments, `{}` nesting, and statements separated by newlines or `;`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import style

STEREO_RE = re.compile(r"<<\s*([^<>]+?)\s*>>|«\s*([^«»]+?)\s*»")

# Keys whose blocks are d2 configuration, never containers of shapes.
NO_RECURSE = {"vars", "classes", "style", "label", "icon", "near", "tooltip", "link"}
# Lines inside a class that are d2 keywords rather than members.
CLASS_KEYWORDS = {"shape", "label", "icon", "tooltip", "link", "near", "class"}


# ---------------------------------------------------------------- scanning


@dataclass
class Item:
    kind: str  # "stmt", "comment" or "blank"
    text: str  # statement text (no trailing comment) or comment text (no '#')
    trailing: str | None = None  # comment at the end of the statement's first line


def _skip_string(src: str, i: int) -> int:
    """Index just past the quoted string starting at src[i]."""
    quote, i, n = src[i], i + 1, len(src)
    while i < n:
        if src[i] == "\\":
            i += 2
            continue
        if src[i] == quote:
            return i + 1
        i += 1
    return n


def _skip_block_string(src: str, i: int) -> int:
    """Index just past a d2 block string (|md ...|, |||...|||) starting at src[i]."""
    j = i
    while j < len(src) and src[j] == "|":
        j += 1
    end = src.find(src[i:j], j)
    return len(src) if end < 0 else end + (j - i)


def _statement_end(src: str, i: int) -> tuple[int, str | None]:
    """End of the statement starting at src[i], and the comment on its first line
    if that comment sits inside the statement's block (e.g. `A: {  # <<entity>>`)."""
    depth, n = 0, len(src)
    first_line, first_comment = True, None
    while i < n:
        c = src[i]
        if c == "\n":
            if depth <= 0:
                return i, first_comment
            first_line = False
        elif c in "\"'":
            i = _skip_string(src, i)
            continue
        elif c == "|":
            i = _skip_block_string(src, i)
            continue
        elif c == "#":
            if depth <= 0:
                return i, first_comment
            j = src.find("\n", i)
            j = n if j < 0 else j
            if first_line and first_comment is None:
                first_comment = src[i + 1 : j].strip()
            i = j
            continue
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == ";" and depth <= 0:
            return i, first_comment
        i += 1
    return n, first_comment


def scan(src: str) -> list[Item]:
    """Split a d2 map body into statements, comment lines and blank lines."""
    items: list[Item] = []
    i, n = 0, len(src)
    line_has_content = False
    while i < n:
        c = src[i]
        if c in " \t\r":
            i += 1
        elif c == "\n":
            if not line_has_content:
                items.append(Item("blank", ""))
            line_has_content = False
            i += 1
        elif c == ";":
            line_has_content = True
            i += 1
        elif c == "#":
            j = src.find("\n", i)
            j = n if j < 0 else j
            items.append(Item("comment", src[i + 1 : j].strip()))
            line_has_content = True
            i = j
        else:
            j, inner_comment = _statement_end(src, i)
            text = src[i:j].rstrip()
            trailing = inner_comment
            if j < n and src[j] == "#":
                k = src.find("\n", j)
                k = n if k < 0 else k
                trailing = trailing or src[j + 1 : k].strip()
                j = k
            items.append(Item("stmt", text, trailing))
            line_has_content = True
            i = j
    return items


def split_block(text: str) -> tuple[str, str | None, str]:
    """`head { body } tail` -> (head, body, tail); body is None without a block."""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            i = _skip_string(text, i)
            continue
        if c == "|":
            i = _skip_block_string(text, i)
            continue
        if c == "{":
            depth, j = 0, i
            while j < n:
                d = text[j]
                if d in "\"'":
                    j = _skip_string(text, j)
                    continue
                if d == "|":
                    j = _skip_block_string(text, j)
                    continue
                if d == "#":
                    k = text.find("\n", j)
                    j = n if k < 0 else k
                    continue
                if d == "{":
                    depth += 1
                elif d == "}":
                    depth -= 1
                    if depth == 0:
                        return text[:i], text[i + 1 : j], text[j + 1 :]
                j += 1
            return text[:i], text[i + 1 :], ""
        i += 1
    return text, None, ""


def split_colon(head: str) -> tuple[str, str | None]:
    """`key: value` -> (key, value) at the first colon outside quotes."""
    i, n = 0, len(head)
    while i < n:
        c = head[i]
        if c in "\"'":
            i = _skip_string(head, i)
            continue
        if c == "\\":
            i += 2
            continue
        if c == ":":
            return head[:i].strip(), head[i + 1 :].strip()
        i += 1
    return head.strip(), None


def unquote(s: str) -> str:
    """Remove quotes from quoted parts and unescape `\\:`; keep everything else."""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in "\"'":
            j = _skip_string(s, i)
            inner = s[i + 1 : j - 1] if j - 1 > i else s[i + 1 :]
            out.append(re.sub(r"\\(.)", r"\1", inner))
            i = j
        elif c == "\\" and i + 1 < n:
            out.append(s[i + 1])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out).strip()


def d2_string(text: str) -> str:
    """A double-quoted d2 string that shows `text` literally."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def is_edge(head: str) -> bool:
    """True for edge declarations like `A -> B`, `A -- B: label` (not `(A -> B)[0]`)."""
    if head.lstrip().startswith("("):
        return False
    key, _ = split_colon(head)
    i, n = 0, len(key)
    while i < n:
        c = key[i]
        if c in "\"'":
            i = _skip_string(key, i)
            continue
        if key.startswith(("->", "<-", "--"), i):
            return True
        i += 1
    return False


def find_stereotype(*comments: str | None) -> str | None:
    for comment in comments:
        if comment:
            m = STEREO_RE.search(comment)
            if m:
                return (m.group(1) or m.group(2)).strip()
    return None


# ---------------------------------------------------------------- converting


@dataclass
class Converter:
    warnings: list[str] = field(default_factory=list)

    def convert(self, src: str, indent: str = "") -> str:
        out: list[str] = []
        pending: list[str] = []  # comment lines directly above the next statement
        for item in scan(src):
            if item.kind == "blank":
                out.append("")
                pending = []
            elif item.kind == "comment":
                out.append(f"{indent}# {item.text}")
                pending.append(item.text)
            else:
                stereo = find_stereotype(item.trailing, *reversed(pending))
                out.append(self._statement(item, stereo, indent))
                pending = []
        return "\n".join(out)

    def _statement(self, item: Item, stereo: str | None, indent: str) -> str:
        head, body, tail = split_block(item.text)
        if is_edge(head):
            return self._edge(head, body, tail, stereo, indent)
        key, _ = split_colon(head)
        if self._is_class(body, stereo) and key.lower() not in NO_RECURSE:
            return self._class(head, body or "", stereo, indent)
        if body is not None and key.split(".")[0].lower() not in NO_RECURSE:
            inner = self.convert(body, indent + "  ")
            return f"{indent}{head.rstrip()} {{\n{inner}\n{indent}}}{tail}"
        verbatim = indent + item.text
        return f"{verbatim}  # {item.trailing}" if item.trailing and body is None else verbatim

    @staticmethod
    def _is_class(body: str | None, stereo: str | None) -> bool:
        if stereo is not None:
            return True
        if body is None:
            return False
        for item in scan(body):
            if item.kind == "stmt":
                key, value = split_colon(split_block(item.text)[0])
                if key.lower() == "shape" and (value or "").strip().lower() == "class":
                    return True
        return False

    # -- classes

    def _class(self, head: str, body: str, stereo: str | None, indent: str) -> str:
        key, label = split_colon(head)
        name = unquote(label) if label else unquote(key)
        kind = style.kind_for(stereo)
        fill = kind.fill
        members: list[str] = []

        for item in scan(body):
            if item.kind != "stmt":
                continue
            m_head, m_body, _ = split_block(item.text)
            m_key, m_value = split_colon(m_head)
            k = m_key.lower()
            if k == "style" or k.startswith("style."):
                fill = self._fill(k, m_value, m_body) or fill
                continue
            if not kind.enum and k in CLASS_KEYWORDS:
                if k == "label" and m_value:
                    name = unquote(m_value)
                continue
            if kind.enum and k == "shape":
                continue
            if k in ("width", "height") and (m_value or "").isdigit():
                continue
            members.append(unquote(m_head if m_body is not None else item.text))

        cells = self._cells(kind, name, members)
        pad = indent + "  "
        lines = [
            f"{indent}{key}: {{",
            f'{pad}label: ""',
            f"{pad}grid-columns: 1",
            f"{pad}grid-gap: 0",
            f"{pad}style: {{{style.BOX_STYLE.format(fill=fill)}}}",
        ]
        for cell_key, cell_label, cell_style in cells:
            label_part = f" {d2_string(cell_label)}" if cell_label is not None else ""
            lines.append(f"{pad}{cell_key}:{label_part} {{{cell_style}}}")
        lines.append(f"{indent}}}")
        return "\n".join(lines)

    @staticmethod
    def _fill(key: str, value: str | None, body: str | None) -> str | None:
        if key == "style.fill" and value:
            return unquote(value)
        if key == "style" and body:
            for item in scan(body):
                k, v = split_colon(item.text) if item.kind == "stmt" else ("", None)
                if k.lower() == "fill" and v:
                    return unquote(v)
        return None

    @staticmethod
    def _cells(kind: style.Kind, name: str, members: list[str]) -> list[tuple[str, str | None, str]]:
        cells: list[tuple[str, str | None, str]] = []
        if kind.stereotype is None:
            cells.append(("pad", None, style.PAD_TOP_PLAIN))
        elif kind.icon:
            cells.append(("st", f"«{kind.stereotype}»", style.stereo_icon(style.ICON_DIR / kind.icon)))
        else:
            cells.append(("pad", None, style.PAD_TOP_STEREO))
            cells.append(("st", f"«{kind.stereotype}»", style.STEREO))
        cells.append(("nm", name, style.NAME))

        counter = iter(range(1, 10_000))

        def add_members(texts: list[str]) -> None:
            for text in texts:
                cells.append((f"m{next(counter)}", text, style.MEMBER))

        if kind.enum:
            if members:
                cells.append(("s1", None, style.SEP))
                add_members(members)
                cells.append(("endpad", None, style.PAD_BOTTOM))
            else:
                cells.append(("s1", None, style.EMPTY_LAST))
            return cells

        attrs = [m for m in members if "(" not in m]
        ops = [m for m in members if "(" in m]
        if attrs and ops:
            cells.append(("s1", None, style.SEP))
            add_members(attrs)
            cells.append(("s2", None, style.SEP))
            add_members(ops)
            cells.append(("endpad", None, style.PAD_BOTTOM))
        elif attrs:
            cells.append(("s1", None, style.SEP))
            add_members(attrs)
            cells.append(("s2", None, style.EMPTY_LAST))
        elif ops:
            cells.append(("s1", None, style.EMPTY))
            add_members(ops)
            cells.append(("endpad", None, style.PAD_BOTTOM))
        else:
            cells.append(("s1", None, style.EMPTY_BOTH))
        return cells

    # -- edges

    def _edge(self, head: str, body: str | None, tail: str, stereo: str | None, indent: str) -> str:
        fields = [style.EDGE_BASE]
        if stereo is not None:
            kind_fields = style.edge_kind(stereo)
            if kind_fields is None:
                self.warnings.append(f"unknown relationship <<{stereo}>> on: {head.strip()}")
            else:
                fields += kind_fields
        inner = "; ".join(fields)
        head = head.rstrip()
        if body is not None:
            return f"{indent}{head} {{{inner}\n{body}\n}}{tail}"
        _, label = split_colon(head)
        if label is None:
            return f"{indent}{head}: {{{inner}}}"
        return f"{indent}{head} {{{inner}}}"


def convert(src: str) -> tuple[str, list[str]]:
    """Plain d2 -> styled d2. Returns the d2 text and a list of warnings."""
    converter = Converter()
    return converter.convert(src) + "\n", converter.warnings
