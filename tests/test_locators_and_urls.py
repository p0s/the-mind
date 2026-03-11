import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import build_site  # noqa: E402
from _core.locators import normalize_locator, parse_pdf_page, valid_locator  # noqa: E402
from _core.sources import located_url  # noqa: E402


class TestLocatorsAndUrls(unittest.TestCase):
    def test_normalizes_pdf_page_locators(self) -> None:
        self.assertEqual(normalize_locator("P.016"), "p16")
        self.assertEqual(normalize_locator("p19–20"), "p19-20")
        self.assertTrue(valid_locator("p16"))
        self.assertTrue(valid_locator("00:00:05.100"))

    def test_parse_pdf_page(self) -> None:
        self.assertEqual(parse_pdf_page("p16"), (16, 16))
        self.assertEqual(parse_pdf_page("p7-9"), (7, 9))
        self.assertIsNone(parse_pdf_page("p0"))
        self.assertIsNone(parse_pdf_page("p9-7"))

    def test_located_url_uses_pdf_page_fragment(self) -> None:
        url = build_site.located_url("https://example.com/paper.pdf", "p16")
        self.assertEqual(url, "https://example.com/paper.pdf#page=16")

    def test_located_url_uses_first_page_for_range(self) -> None:
        url = build_site.located_url("https://example.com/paper.pdf", "p19-20")
        self.assertEqual(url, "https://example.com/paper.pdf#page=19")

    def test_located_url_keeps_timecoded_youtube_behavior(self) -> None:
        url = build_site.located_url("https://www.youtube.com/watch?v=abc", "00:01:05")
        self.assertEqual(url, "https://www.youtube.com/watch?v=abc&t=65s")

    def test_core_located_url_pdf_page(self) -> None:
        u = "https://cimc.ai/cimcHypothesis.pdf"
        self.assertEqual(located_url(u, "p16"), "https://cimc.ai/cimcHypothesis.pdf#page=16")
        self.assertEqual(located_url(u, "p7-9"), "https://cimc.ai/cimcHypothesis.pdf#page=7")

    def test_core_located_url_timecode_unchanged_semantics(self) -> None:
        u = "https://www.youtube.com/watch?v=abc"
        self.assertEqual(located_url(u, "00:00:05"), "https://www.youtube.com/watch?v=abc&t=5s")
        u2 = "https://youtu.be/abc"
        self.assertEqual(located_url(u2, "00:00:05"), "https://youtu.be/abc?t=5")


if __name__ == "__main__":
    unittest.main()
