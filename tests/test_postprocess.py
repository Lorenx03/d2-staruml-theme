import base64
import re
import unittest

from src.postprocess import postprocess_svg


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


class ArrowheadTests(unittest.TestCase):
    def test_end_arrowhead_is_opened(self):
        head = '<polygon points="0,0 12,6 0,12 9,6" fill="#000000" class="connection" stroke-width="1" />'
        out = postprocess_svg(f"<svg>{head}</svg>")
        self.assertIn('<polyline points="0.5,0.5 12,6 0.5,11.5" fill="none"', out)

    def test_start_arrowhead_is_opened(self):
        head = '<polygon points="0,6 12,0 9,6 12,12" fill="#000000" class="connection" stroke-width="1" />'
        out = postprocess_svg(f"<svg>{head}</svg>")
        self.assertIn('<polyline points="11.5,0.5 0,6 11.5,11.5" fill="none"', out)

    def test_diamonds_are_left_alone(self):
        filled = '<polygon points="0,7 11,0 22,7 11,14" fill="#000000" class="connection" stroke-width="1" />'
        hollow = '<polygon points="0,9 11,2.25 22,9 11,16.2" stroke="#000000" fill="#FFFFFF" class="connection fill-N7" stroke-width="1" />'
        for head in (filled, hollow):
            self.assertEqual(postprocess_svg(f"<svg>{head}</svg>"), f"<svg>{head}</svg>")


class ActivityTests(unittest.TestCase):
    BAR = f'<g class="{b64("fork")} staruml-bar"><g class="shape" ><rect x="100" y="100" width="60" height="5" /></g></g>'

    def edge(self, ident: str, d: str) -> str:
        return f'<g class="{b64(ident)}"><path d="{d}" class="connection" /></g>'

    def test_flows_run_straight_into_the_stretched_bar(self):
        out_left = self.edge("(fork -&gt; a)[0]", "M 130 105 C 100 130 20 150 20 200")
        out_right = self.edge("(fork -&gt; b)[0]", "M 130 105 C 160 130 240 150 240 200")
        into = self.edge("(m -&gt; fork)[0]", "M 128 40 C 128 60 130 80 130 96")
        out = postprocess_svg(f"<svg>{self.BAR}{out_left}{out_right}{into}</svg>")
        self.assertIn('d="M 20 105 L 20 200"', out)
        self.assertIn('d="M 240 105 L 240 200"', out)
        self.assertIn('d="M 128 40 L 128 96"', out)  # keeps the gap left for the arrowhead
        self.assertIn('<rect x="-10" y="100" width="280" height="5" />', out)  # 20 - 30 .. 240 + 30

    def test_bar_stops_short_of_a_shape_beside_it(self):
        beside = f'<g class="{b64("box")}"><g class="shape" ><rect x="-100" y="90" width="105" height="30" /></g></g>'
        flow = self.edge("(fork -&gt; a)[0]", "M 130 105 C 100 130 20 150 20 200")
        out = postprocess_svg(f"<svg>{beside}{self.BAR}{flow}</svg>")
        self.assertIn('<rect x="15" y="100" width="145" height="5" />', out)  # 5 + 10 .. 160

    def test_flows_inside_a_container(self):
        bar = self.BAR.replace(b64("fork"), b64("pkg.fork"))
        flow = self.edge("pkg.(fork -&gt; a)[0]", "M 130 105 C 100 130 20 150 20 200")
        self.assertIn('d="M 20 105 L 20 200"', postprocess_svg(f"<svg>{bar}{flow}</svg>"))

    def test_other_edges_are_left_alone(self):
        flow = self.edge("(a -&gt; b)[0]", "M 1 2 C 3 4 5 6 7 8")
        self.assertIn('d="M 1 2 C 3 4 5 6 7 8"', postprocess_svg(f"<svg>{self.BAR}{flow}</svg>"))

    def test_final_marks(self):
        ring = '<g class="{}"><g class="shape" ><ellipse rx="14" ry="14" cx="50" cy="60" /></g></g>'
        out = postprocess_svg("<svg>" + ring.format(f"{b64('e')} staruml-final") + "</svg>")
        self.assertIn('<circle cx="50" cy="60" r="7.7" fill="#000000" />', out)
        out = postprocess_svg("<svg>" + ring.format(f"{b64('x')} staruml-flow-final") + "</svg>")
        self.assertEqual(len(re.findall(r" L ", out)), 2)


if __name__ == "__main__":
    unittest.main()
