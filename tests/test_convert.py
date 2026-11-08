import re
import unittest

from src.convert import convert


def labels(d2: str, cls: str) -> list[str]:
    """Cell labels of a converted class, top to bottom."""
    block = re.search(rf"(?ms)^{re.escape(cls)}: \{{\n(.*?)^\}}", d2).group(1)
    return [m.group(1) for m in re.finditer(r'^\s+\w+: "((?:[^"\\]|\\.)*)" \{', block, re.M)]


def cells(d2: str, cls: str) -> list[str]:
    block = re.search(rf"(?ms)^{re.escape(cls)}: \{{\n(.*?)^\}}", d2).group(1)
    return re.findall(r"^\s+(\w+):", block, re.M)  # skips grid-columns/grid-gap


class ClassTests(unittest.TestCase):
    def test_stereotype_above(self):
        out, _ = convert("# <<entity>>\nA: {\n  shape: class\n  -x: int\n  +f(): void\n}\n")
        self.assertEqual(labels(out, "A"), ["«entity»", "A", "-x: int", "+f(): void"])
        self.assertIn("entity.svg", out)
        self.assertIn('fill: "#FFFFDB"', out)

    def test_stereotype_trailing(self):
        out, _ = convert("A: {  # <<control>>\n  shape: class\n  +f()\n}\n")
        self.assertEqual(labels(out, "A")[:2], ["«control»", "A"])

    def test_blank_line_breaks_stereotype_comment(self):
        out, _ = convert("# <<entity>>\n\nA: {\n  shape: class\n  -x: int\n}\n")
        self.assertEqual(labels(out, "A"), ["A", "-x: int"])

    def test_unknown_stereotype_gets_white_box(self):
        out, _ = convert("# <<service>>\nA: {\n  shape: class\n}\n")
        self.assertEqual(labels(out, "A"), ["«service»", "A"])
        self.assertIn('fill: "#FFFFFF"', out)

    def test_no_stereotype(self):
        out, _ = convert("A: {\n  shape: class\n  -x: int\n}\n")
        self.assertEqual(labels(out, "A"), ["A", "-x: int"])

    def test_stereotype_without_shape_class(self):
        out, _ = convert("# <<bean>>\nB: {\n  -x: int\n}\n")
        self.assertEqual(labels(out, "B"), ["«bean»", "B", "-x: int"])

    def test_enum_literals_do_not_collide_with_internal_keys(self):
        out, _ = convert("# <<enumeration>>\nE: {\n  shape: class\n  END\n  NAME\n  LABEL\n  A\n  A\n}\n")
        self.assertEqual(labels(out, "E"), ["«enumeration»", "E", "END", "NAME", "LABEL", "A", "A"])

    def test_duplicate_members_are_kept(self):
        out, _ = convert("A: {\n  shape: class\n  +f(): void\n  +f(): void\n}\n")
        self.assertEqual(labels(out, "A"), ["A", "+f(): void", "+f(): void"])

    def test_member_text(self):
        src = (
            "A: {\n  shape: class\n"
            "  +start(plate\\: PlateBean): void\n"
            "  +raw(a: int): void\n"
            '  "+quoted(x: int)": Bool\n'
            '  -price: "$5 \\"net\\""\n'
            "}\n"
        )
        out, _ = convert(src)
        self.assertEqual(
            labels(out, "A"),
            ["A", '-price: \\$5 \\"net\\"', "+start(plate: PlateBean): void", "+raw(a: int): void", "+quoted(x: int): Bool"],
        )

    def test_class_label_and_fill(self):
        out, _ = convert('A: "Nice Name" {\n  shape: class\n  style.fill: "#ABCDEF"\n  -x: int\n}\n')
        self.assertEqual(labels(out, "A"), ["Nice Name", "-x: int"])
        self.assertIn('fill: "#ABCDEF"', out)

    def test_compartments(self):
        both, _ = convert("A: {\n  shape: class\n  -x: int\n  +f()\n}\n")
        self.assertEqual(cells(both, "A"), ["label", "style", "pad", "nm", "s1", "m1", "s2", "m2", "endpad"])
        attrs_only, _ = convert("A: {\n  shape: class\n  -x: int\n}\n")
        self.assertEqual(cells(attrs_only, "A")[-3:], ["s1", "m1", "s2"])
        ops_only, _ = convert("A: {\n  shape: class\n  +f()\n}\n")
        self.assertEqual(cells(ops_only, "A")[-3:], ["s1", "m1", "endpad"])

    def test_class_inside_container(self):
        out, _ = convert("pkg: {\n  # <<entity>>\n  A: {\n    shape: class\n    -x: int\n  }\n  A -> B\n}\n")
        self.assertIn('"«entity»"', out)
        self.assertIn("A -> B: {style:", out)


class EdgeTests(unittest.TestCase):
    def test_kind_comment(self):
        out, warnings = convert("A -> B  # <<dep>>\n")
        self.assertIn("A -> B: {style: {", out)
        self.assertIn("style.stroke-dash: 4", out)
        self.assertEqual(warnings, [])

    def test_kind_keeps_label_and_map(self):
        out, _ = convert('A -> B: owns {source-arrowhead.label: 1; target-arrowhead.label: "0..*"}  # <<comp>>\n')
        self.assertIn("A -> B: owns {", out)
        self.assertIn("shape: diamond; style.filled: true", out)
        self.assertIn('target-arrowhead.label: "0..*"', out)

    def test_alias_and_label_without_map(self):
        out, _ = convert("A -> B: is a  # <<generalization>>\n")
        self.assertIn("A -> B: is a {", out)
        self.assertIn("shape: triangle", out)

    def test_plain_edge_keeps_user_styling(self):
        out, _ = convert("A -> B: {\n  target-arrowhead.shape: diamond\n}\n")
        self.assertIn("target-arrowhead.shape: diamond", out)
        self.assertNotIn("stroke-dash", out)

    def test_unknown_kind_warns(self):
        _, warnings = convert("A -> B  # <<friends>>\n")
        self.assertEqual(len(warnings), 1)

    def test_edge_reference_untouched(self):
        out, _ = convert("(A -> B)[0].style.stroke: red\n")
        self.assertEqual(out.strip(), "(A -> B)[0].style.stroke: red")


class PassThroughTests(unittest.TestCase):
    def test_config_and_other_shapes(self):
        src = 'vars: {\n  d2-config: {\n    layout-engine: elk\n  }\n}\ndirection: right\nnote: "hi" {shape: text}\n'
        out, _ = convert(src)
        self.assertIn("layout-engine: elk", out)
        self.assertIn("direction: right", out)
        self.assertIn('note: "hi" {', out)  # non-class blocks are re-indented, not changed
        self.assertIn("shape: text", out)


if __name__ == "__main__":
    unittest.main()
