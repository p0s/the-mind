import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import build_site  # noqa: E402


class TestLocatorsAndUrls(unittest.TestCase):
    def test_located_url_uses_pdf_page_fragment(self) -> None:
        url = build_site.located_url("https://example.com/paper.pdf", "p16")
        self.assertEqual(url, "https://example.com/paper.pdf#page=16")

    def test_located_url_uses_first_page_for_range(self) -> None:
        url = build_site.located_url("https://example.com/paper.pdf", "p19-20")
        self.assertEqual(url, "https://example.com/paper.pdf#page=19")

    def test_located_url_keeps_timecoded_youtube_behavior(self) -> None:
        url = build_site.located_url("https://www.youtube.com/watch?v=abc", "00:01:05")
        self.assertEqual(url, "https://www.youtube.com/watch?v=abc&t=65s")


if __name__ == "__main__":
    unittest.main()
