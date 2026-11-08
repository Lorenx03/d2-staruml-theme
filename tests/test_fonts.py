import tempfile
import unittest
from pathlib import Path

from src.fonts import FONTS_DIR, FontError, available_fonts, find_font, fontconfig_env


def make_family(root: Path, name: str, files: list[str]) -> Path:
    folder = root / name
    for file in files:
        (folder / file).parent.mkdir(parents=True, exist_ok=True)
        (folder / file).write_bytes(b"")
    return folder


class FindFontTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_google_fonts_layout_picks_static_text_cut(self):
        make_family(self.root, "Inter", [
            "Inter-VariableFont_opsz,wght.ttf",
            "static/Inter_28pt-Regular.ttf", "static/Inter_28pt-Bold.ttf",
            "static/Inter_18pt-SemiBold.ttf", "static/Inter_18pt-BoldItalic.ttf",
            "static/Inter_18pt-Regular.ttf", "static/Inter_18pt-Bold.ttf",
        ])  # fmt: skip
        font = find_font("inter", self.root)
        self.assertEqual(font.regular.name, "Inter_18pt-Regular.ttf")
        self.assertEqual(font.bold.name, "Inter_18pt-Bold.ttf")

    def test_family_name_file_counts_as_regular(self):
        folder = make_family(self.root, "Arial", ["Arial.ttf", "Arial Bold.ttf", "Arial Bold Italic.ttf"])
        font = find_font(str(folder), self.root / "elsewhere")
        self.assertEqual((font.regular.name, font.bold.name), ("Arial.ttf", "Arial Bold.ttf"))

    def test_missing_bold(self):
        make_family(self.root, "Thin", ["Thin-Regular.ttf", "Thin-SemiBold.ttf"])
        with self.assertRaisesRegex(FontError, "no Bold"):
            find_font("Thin", self.root)
        self.assertEqual(available_fonts(self.root), [])

    def test_unknown_font_lists_available(self):
        make_family(self.root, "Outfit", ["static/Outfit-Regular.ttf", "static/Outfit-Bold.ttf"])
        with self.assertRaisesRegex(FontError, r"available: Outfit"):
            find_font("Nope", self.root)

    def test_fontconfig_env(self):
        make_family(self.root, "Outfit", ["Outfit-Regular.ttf", "Outfit-Bold.ttf"])
        tmp = self.root / "tmp"
        tmp.mkdir()
        env = fontconfig_env(find_font("Outfit", self.root), tmp)
        self.assertEqual(env["PANGOCAIRO_BACKEND"], "fc")
        self.assertIn("<string>StarUML Text</string>", Path(env["FONTCONFIG_FILE"]).read_text())
        self.assertEqual(sorted(p.name for p in (tmp / "fonts").iterdir()), ["Outfit-Bold.ttf", "Outfit-Regular.ttf"])


class BundledFontTests(unittest.TestCase):
    def test_bundled_fonts_resolve(self):
        for name in available_fonts():
            font = find_font(name)
            self.assertTrue(font.regular.is_file() and font.bold.is_file(), name)
        self.assertIn("Inter", available_fonts(FONTS_DIR))


if __name__ == "__main__":
    unittest.main()
