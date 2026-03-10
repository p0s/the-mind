import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import lint_provenance  # noqa: E402


class TestProvenance(unittest.TestCase):
    def test_accepts_timecode_locator(self) -> None:
        self.assertTrue(lint_provenance.valid_locator("00:01:02"))

    def test_accepts_pdf_page_locators(self) -> None:
        self.assertTrue(lint_provenance.valid_locator("p16"))
        self.assertTrue(lint_provenance.valid_locator("p19-20"))

    def test_rejects_invalid_pdf_page_locators(self) -> None:
        self.assertFalse(lint_provenance.valid_locator("p0"))
        self.assertFalse(lint_provenance.valid_locator("p20-19"))

    def test_src_comment_regex_matches_pdf_page_locator(self) -> None:
        line = "Hello <!-- src: web_x @ p16 -->"
        m = lint_provenance.SRC_COMMENT_CANON_RX.search(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "web_x")
        self.assertEqual(m.group(2), "p16")


if __name__ == "__main__":
    unittest.main()
