import unittest

from src.postprocess import postprocess_svg


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


if __name__ == "__main__":
    unittest.main()
