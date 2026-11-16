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


if __name__ == "__main__":
    unittest.main()
