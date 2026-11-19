"""Convert a plain d2 class, use case or activity diagram into the StarUML-styled d2 that `d2` renders.

Input is ordinary d2: classes are `shape: class` blocks, stereotypes are comments
(`# <<entity>>`) above a class or at the end of its first line, and relationship
kinds are comments on edges (`A -> B  # <<dep>>`). A top-level `# <<usecase diagram>>`
switches to use case diagrams: actors, use cases (ovals), system boxes and
«include»/«extend» edges; `# <<activity diagram>>` to activity diagrams: actions,
initial/final nodes, decisions, fork/join bars and guarded flows. Everything the
converter does not recognise is copied through unchanged.

The scanner below only understands as much d2 as it needs: strings, block strings,
comments, `{}` nesting, and statements separated by newlines or `;`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from . import style

STEREO_RE = re.compile(r"<<\s*([^<>]+?)\s*>>|«\s*([^«»]+?)\s*»")

# Keys whose blocks are d2 configuration, never containers of shapes.
NO_RECURSE = {"vars", "classes", "style", "label", "icon", "near", "tooltip", "link"}
# Lines inside a class that are d2 keywords rather than members.
CLASS_KEYWORDS = {"shape", "label", "icon", "tooltip", "link", "near", "class"}
# Reserved d2 keys: in a use case diagram, statements with these keys are never shapes.
D2_KEYWORDS = CLASS_KEYWORDS | NO_RECURSE | {
    "direction", "width", "height", "top", "left", "grid-rows", "grid-columns", "grid-gap",
    "vertical-gap", "horizontal-gap", "layers", "scenarios", "steps", "constraint",
    "source-arrowhead", "target-arrowhead",
}  # fmt: skip

# `# <<usecase diagram>>` anywhere at the top level picks the diagram type.
DIAGRAM_TYPES = {"classdiagram": "class", "usecasediagram": "usecase", "activitydiagram": "activity"}
ACTOR, USE_CASE, SYSTEM = "actor", "usecase", "system"
UC_STEREOTYPES = {"actor": ACTOR, "usecase": USE_CASE, "system": SYSTEM, "subject": SYSTEM}

# Activity diagram node kinds, by stereotype (normalized: `flow final` -> `flowfinal`).
ACTION, INITIAL, FINAL, FLOW_FINAL, DECISION, BAR, TIME, GROUP = (
    "action", "initial", "final", "flowfinal", "decision", "bar", "time", "group",
)  # fmt: skip
AD_STEREOTYPES = {
    "action": ACTION,
    "initial": INITIAL, "initialnode": INITIAL, "start": INITIAL,
    "final": FINAL, "activityfinal": FINAL, "finalnode": FINAL, "end": FINAL,
    "flowfinal": FLOW_FINAL,
    "decision": DECISION, "merge": DECISION,
    "fork": BAR, "join": BAR,
    "time": TIME, "timeevent": TIME, "accepttimeevent": TIME, "wait": TIME,
    "group": GROUP, "region": GROUP,
}  # fmt: skip


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


def _normalize(name: str) -> str:
    """`Use Case`, `use-case`, `use_case` -> `usecase`."""
    return re.sub(r"[\s_-]+", "", name.lower())


def diagram_type_of(comment: str) -> str | None:
    """"class"/"usecase"/"activity" if the comment is a diagram-type annotation."""
    stereo = find_stereotype(comment)
    return DIAGRAM_TYPES.get(_normalize(stereo)) if stereo else None


def diagram_type(src: str) -> str:
    for item in scan(src):
        if item.kind == "comment" and (kind := diagram_type_of(item.text)):
            return kind
    return "class"


def _without_strings(s: str) -> str:
    """`s` with its quoted parts removed (to look for `.` or arrows outside them)."""
    out, i = [], 0
    while i < len(s):
        if s[i] in "\"'":
            i = _skip_string(s, i)
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


EDGE_OP_RE = re.compile(r"<->|<-|->|--")


def edge_endpoints(key: str) -> list[str]:
    """`A -> "B c" -> D` -> ['A', '"B c"', 'D']."""
    parts, start, i = [], 0, 0
    while i < len(key):
        if key[i] in "\"'":
            i = _skip_string(key, i)
            continue
        m = EDGE_OP_RE.match(key, i)
        if m:
            parts.append(key[start:i].strip())
            start = i = m.end()
            continue
        i += 1
    parts.append(key[start:].strip())
    return parts


def _simple_key(key: str) -> str | None:
    """Lower-cased, unquoted key if it names a shape in this scope (no `.`, not a keyword)."""
    if not key or "." in _without_strings(key) or key.startswith(("_", "(", "...")):
        return None
    name = unquote(key).lower()
    return None if name in D2_KEYWORDS else name


# ---------------------------------------------------------------- converting


@dataclass
class Converter:
    warnings: list[str] = field(default_factory=list)
    diagram: str = "class"  # "class", "usecase" or "activity"
    text_width: Callable[[str], float] | None = None  # px width of a bold name
    vertical: bool = False  # flow runs left/right: fork/join bars stand upright
    # activity diagrams: edge segments to write the other way round, by (scope, edge number)
    rewrites: dict[tuple[str, int], set[int]] = field(default_factory=dict)
    _scope: str = ""  # path of the container being converted ("" at the top level)
    _edge_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def usecase(self) -> bool:
        return self.diagram == "usecase"

    @property
    def activity(self) -> bool:
        return self.diagram == "activity"

    def convert(self, src: str, indent: str = "") -> str:
        out: list[str] = []
        pending: list[str] = []  # comment lines directly above the next statement
        items = scan(src)
        for item in items:
            if item.kind == "blank":
                out.append("")
                pending = []
            elif item.kind == "comment":
                out.append(f"{indent}# {item.text}")
                if not diagram_type_of(item.text):
                    pending.append(item.text)
            else:
                stereo = find_stereotype(item.trailing, *reversed(pending))
                out.append(self._statement(item, stereo, indent))
                pending = []
        if self.usecase or self.activity:
            out = self._undeclared_nodes(items, indent) + out
        return "\n".join(out)

    def _child(self, key: str, body: str, indent: str) -> str:
        """Convert the body of container `key`."""
        outer, self._scope = self._scope, _join(self._scope, key)
        try:
            return self.convert(body, indent)
        finally:
            self._scope = outer

    def _statement(self, item: Item, stereo: str | None, indent: str) -> str:
        head, body, tail = split_block(item.text)
        if is_edge(head):
            return self._edge(head, body, tail, stereo, indent)
        if self.usecase or self.activity:
            make = self._uc_node if self.usecase else self._ad_node
            node = make(head, body, tail, stereo, indent)
            if node is not None:
                return node
        key, _ = split_colon(head)
        if self._is_class(body, stereo) and key.lower() not in NO_RECURSE:
            return self._class(head, body or "", stereo, indent)
        if body is not None and key.split(".")[0].lower() not in NO_RECURSE:
            inner = self._child(key, body, indent + "  ")
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
        key, label = split_colon(head)
        number = self._edge_counts[self._scope]
        self._edge_counts[self._scope] += 1
        rewrite = self.rewrites.get((self._scope, number))
        if not rewrite:
            return self._edge_line(key, label, body, tail, stereo, indent)
        # written the other way round (see `_rewrites`); a chain is split into its segments
        ends, ops = edge_endpoints(key), EDGE_OP_RE.findall(_without_strings(key))
        lines = []
        for i, op in enumerate(ops):
            last = i == len(ops) - 1
            if i in rewrite:
                seg_body = _swap_arrowheads(body) if body is not None else None
                lines.append(self._edge_line(f"{ends[i + 1]} {MIRROR[op]} {ends[i]}", label, seg_body, tail if last else "", stereo, indent))
            else:
                lines.append(self._edge_line(f"{ends[i]} {op} {ends[i + 1]}", label, body, tail if last else "", stereo, indent))
        return "\n".join(lines)

    def _edge_line(self, key: str, label: str | None, body: str | None, tail: str, stereo: str | None, indent: str) -> str:
        head = f"{key}: {label}" if label else key
        fields = [style.EDGE_BASE]
        uc_kind = style.uc_edge_kind(stereo) if self.usecase and stereo is not None else None
        if uc_kind is not None:
            name, kind_fields = uc_kind
            fields += kind_fields
            label = label or d2_string(f"«{name}»")
        elif stereo is not None:
            kind_fields = style.edge_kind(stereo)
            if kind_fields is None:
                self.warnings.append(f"unknown relationship <<{stereo}>> on: {head.strip()}")
            else:
                fields += kind_fields
        elif self.usecase or self.activity:  # association / control flow: open arrow(s) where d2 would draw a head
            ops = _without_strings(key)
            if "->" in ops:
                fields.append("target-arrowhead.shape: arrow")
            if "<-" in ops:
                fields.append("source-arrowhead.shape: arrow")
            if self.activity and label:  # a control flow's label is its guard
                guard = unquote(label)
                label = d2_string(guard if guard.startswith("[") else f"[{guard}]")
        inner = "; ".join(fields)
        head = f"{key}: {label}" if label else f"{key}:"
        if body is not None:
            return f"{indent}{head} {{{inner}\n{body}\n}}{tail}"
        return f"{indent}{head} {{{inner}}}"

    # -- use case diagrams

    def _uc_node(self, head: str, body: str | None, tail: str, stereo: str | None, indent: str) -> str | None:
        """Actor, use case or system boundary; None for anything else (keywords, classes)."""
        key, label = split_colon(head)
        if _simple_key(key) is None:
            return None
        statements = [item.text for item in scan(body or "") if item.kind == "stmt"]
        shape, has_children = None, False
        for text in statements:
            s_head = split_block(text)[0]
            s_key, s_value = split_colon(s_head)
            if s_key.lower() == "shape":
                shape = unquote(s_value or "").lower()
            elif is_edge(s_head) or s_key.split(".")[0].lower() not in D2_KEYWORDS:
                has_children = True

        kind = UC_STEREOTYPES.get(_normalize(stereo)) if stereo else None
        if (stereo is not None and kind is None) or shape == "class":
            return None  # a class (with its own stereotype) inside the use case diagram
        if shape == "person":
            kind = ACTOR
        kind = kind or (SYSTEM if has_children else USE_CASE)

        pad = indent + "  "
        lines = [f"{indent}{key}: {label} {{" if label else f"{indent}{key}: {{"]
        if kind == SYSTEM:
            lines += [pad + f for f in style.SYSTEM]
            if body is not None:
                lines.append(self._child(key, body, pad))
        else:
            name = unquote(label) if label else unquote(key)
            for text in statements:
                s_key, s_value = split_colon(split_block(text)[0])
                if s_key.lower() == "label" and s_value:
                    name = unquote(s_value)
            lines += [pad + f for f in (style.ACTOR if kind == ACTOR else self._use_case(name))]
            lines += [pad + t for t in statements if split_colon(split_block(t)[0])[0].lower() != "shape"]
        lines.append(f"{indent}}}{tail}")
        return "\n".join(lines)

    def _undeclared_nodes(self, items: list[Item], indent: str) -> list[str]:
        """Edge ends never declared in this scope (`Operator -> Drive robot`) are use cases
        (or actions, in an activity diagram).

        They go at the top of the scope, so anything the user sets later still wins."""
        declared: set[str] = set()
        ends: list[str] = []
        for item in items:
            if item.kind != "stmt":
                continue
            head = split_block(item.text)[0]
            key, _ = split_colon(head)
            if is_edge(head):
                ends += [e for e in edge_endpoints(key) if _simple_key(e)]
            elif name := _simple_key(key):
                declared.add(name)
        lines = []
        for end in ends:
            name = _simple_key(end)
            if name not in declared:
                declared.add(name)
                fields = self._use_case(unquote(end)) if self.usecase else self._action(unquote(end))
                lines.append(f"{indent}{end}: {{{'; '.join(fields)}}}")
        return lines

    def _measure(self, name: str) -> tuple[float, int]:
        """Width of the widest line of a bold name, and its number of lines."""
        rows = name.replace("\\n", "\n").split("\n")
        measure = self.text_width or (lambda text: len(text) * style.APPROX_CHAR_WIDTH)
        return max(measure(row) for row in rows), len(rows)

    def _use_case(self, name: str) -> list[str]:
        return style.use_case(*self._measure(name))

    def _action(self, name: str) -> list[str]:
        return style.action(*self._measure(name), name_on_top=not self.vertical)

    # -- activity diagrams

    def _ad_node(self, head: str, body: str | None, tail: str, stereo: str | None, indent: str) -> str | None:
        """Action, initial/final node, decision/merge, fork/join, time event or a group
        of nodes; None for anything else (keywords, classes)."""
        key, label = split_colon(head)
        if _simple_key(key) is None:
            return None
        statements = [item.text for item in scan(body or "") if item.kind == "stmt"]
        shape, has_children, name = None, False, unquote(label) if label else unquote(key)
        for text in statements:
            s_head = split_block(text)[0]
            s_key, s_value = split_colon(s_head)
            if s_key.lower() == "shape":
                shape = unquote(s_value or "").lower()
            elif s_key.lower() == "label" and s_value:
                name, label = unquote(s_value), s_value
            elif is_edge(s_head) or s_key.split(".")[0].lower() not in D2_KEYWORDS:
                has_children = True

        kind = AD_STEREOTYPES.get(_normalize(stereo)) if stereo else None
        if (stereo is not None and kind is None) or shape == "class":
            return None  # a class (with its own stereotype) inside the activity diagram
        if kind is None and shape == "diamond":
            kind = DECISION
        kind = kind or (GROUP if has_children else ACTION)

        pad = indent + "  "
        lines = [f"{indent}{key}: {label} {{" if label else f"{indent}{key}: {{"]
        if kind == GROUP:
            lines += [pad + f for f in style.ACTIVITY_GROUP]
            if body is not None:
                lines.append(self._child(key, body, pad))
            lines.append(f"{indent}}}{tail}")
            return "\n".join(lines)

        fields = {
            ACTION: lambda: self._action(name),
            INITIAL: lambda: style.INITIAL,
            FINAL: lambda: style.FINAL,
            FLOW_FINAL: lambda: style.FLOW_FINAL,
            DECISION: lambda: style.DECISION + [style.DECISION_LABEL if label else 'label: ""'],
            BAR: lambda: style.bar(self.vertical),
            TIME: lambda: style.TIME_EVENT,
        }[kind]()
        lines += [pad + f for f in fields]
        lines += [pad + t for t in statements if split_colon(split_block(t)[0])[0].lower() != "shape"]
        lines.append(f"{indent}}}{tail}")
        return "\n".join(lines)


# ---------------------------------------------------------------- loops in activity diagrams
# Layout engines lay a graph out in layers, along its edges, so a loop (`error -> retry`
# back to a merge node higher up) has to be turned round first. ELK picks the edges to
# turn round itself and often picks the wrong ones, which puts the start of the activity
# at the bottom. So the converter finds the edges that close a loop, walking the flow
# from the initial node in the order the edges are written, and writes them the other
# way round: `retry <- error` is drawn exactly like `error -> retry` (arrow at `retry`),
# but the engine sees an edge from `retry` down to `error`.

MIRROR = {"->": "<-", "<-": "->"}


def _path(key: str) -> list[str]:
    """`a."B c".d` -> ['a', 'b c', 'd'] (d2 keys are case-insensitive)."""
    parts, start, i = [], 0, 0
    while i < len(key):
        if key[i] in "\"'":
            i = _skip_string(key, i)
            continue
        if key[i] == ".":
            parts.append(key[start:i])
            start = i + 1
        i += 1
    parts.append(key[start:])
    return [unquote(p).lower() for p in parts]


def _join(scope: str, key: str) -> str:
    return ".".join(([scope] if scope else []) + _path(key))


def _swap_arrowheads(body: str) -> str:
    return re.sub(r"\b(source|target)-arrowhead\b", lambda m: ("target" if m.group(1) == "source" else "source") + "-arrowhead", body)


@dataclass
class _Flows:
    nodes: list[str] = field(default_factory=list)  # in the order they appear
    initial: list[str] = field(default_factory=list)
    # (from, to, (scope, edge number), segment) for each `->`/`<-` segment, in order
    edges: list[tuple[str, str, tuple[str, int], int]] = field(default_factory=list)
    # every `->`/`<-` segment: (scope, edge number) -> {segment: operator}
    ops: dict[tuple[str, int], dict[int, str]] = field(default_factory=lambda: defaultdict(dict))
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, node: str) -> None:
        if node not in self.nodes:
            self.nodes.append(node)

    def walk(self, src: str, scope: str = "") -> None:
        """Collect nodes and flows, numbering edges per scope like `Converter._edge` does."""
        pending: list[str] = []
        for item in scan(src):
            if item.kind == "blank":
                pending = []
            elif item.kind == "comment":
                if not diagram_type_of(item.text):
                    pending.append(item.text)
            else:
                stereo = find_stereotype(item.trailing, *reversed(pending))
                pending = []
                head, body, _ = split_block(item.text)
                key, _ = split_colon(head)
                if is_edge(head):
                    self._edge(key, scope)
                    continue
                if _simple_key(key) is None or (stereo and _normalize(stereo) not in AD_STEREOTYPES):
                    continue  # a keyword, or a class
                node = _join(scope, key)
                self.add(node)
                if stereo and AD_STEREOTYPES[_normalize(stereo)] == INITIAL:
                    self.initial.append(node)
                if body is not None and not Converter._is_class(body, None):
                    self.walk(body, node)

    def _edge(self, key: str, scope: str) -> None:
        stmt = (scope, self.counts[scope])
        self.counts[scope] += 1
        ends = [_join(scope, e) for e in edge_endpoints(key)]
        for i, op in enumerate(EDGE_OP_RE.findall(_without_strings(key))):
            a, b = ends[i], ends[i + 1]
            self.add(a)
            self.add(b)
            if op in MIRROR:
                self.ops[stmt][i] = op
                self.edges.append((a, b, stmt, i) if op == "->" else (b, a, stmt, i))

    def loops(self) -> set[tuple[tuple[str, int], int]]:
        """Segments that close a loop: depth-first from the initial nodes (then from any
        node not reached yet), an edge back to a node still being walked."""
        out: dict[str, list[tuple[str, tuple[str, int], int]]] = defaultdict(list)
        for a, b, stmt, seg in self.edges:
            out[a].append((b, stmt, seg))
        state: dict[str, int] = {}  # 1: being walked, 2: done
        back = set()
        for root in self.initial + self.nodes:
            if root in state:
                continue
            state[root] = 1
            stack = [(root, iter(out[root]))]
            while stack:
                node, todo = stack[-1]
                step = next(todo, None)
                if step is None:
                    state[node] = 2
                    stack.pop()
                    continue
                target, stmt, seg = step
                if target not in state:
                    state[target] = 1
                    stack.append((target, iter(out[target])))
                elif state[target] == 1 and target != node:
                    back.add((stmt, seg))
        return back


def _rewrites(src: str) -> dict[tuple[str, int], set[int]]:
    """Edge segments to write the other way round, so that the engine sees every flow
    going forward and every loop going back up. `a -> b` is written `b <- a` when it
    closes a loop; `a <- b`, which the engine already sees as `a` to `b`, is written
    `b -> a` when it doesn't."""
    flows = _Flows()
    flows.walk(src)
    back = flows.loops()
    rewrites: dict[tuple[str, int], set[int]] = defaultdict(set)
    for stmt, segments in flows.ops.items():
        for seg, op in segments.items():
            if (op == "->") == ((stmt, seg) in back):
                rewrites[stmt].add(seg)
    return dict(rewrites)


def convert(src: str, text_width: Callable[[str], float] | None = None) -> tuple[str, list[str]]:
    """Plain d2 -> styled d2. Returns the d2 text and a list of warnings.
    `text_width` measures a bold name in px (to fit use case ovals and actions to it)."""
    kind = diagram_type(src)
    converter = Converter(
        diagram=kind,
        text_width=text_width,
        vertical=_direction(src) in ("left", "right"),
        rewrites=_rewrites(src) if kind == "activity" else {},
    )
    return converter.convert(src) + "\n", converter.warnings


def _direction(src: str) -> str:
    """The top-level `direction:` (d2's default is down)."""
    direction = "down"
    for item in scan(src):
        if item.kind == "stmt":
            key, value = split_colon(split_block(item.text)[0])
            if key.lower() == "direction" and value:
                direction = unquote(value).lower()
    return direction
