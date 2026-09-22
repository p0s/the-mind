from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_site  # noqa: E402


class TestWebsitePrivacy(unittest.TestCase):
    def test_build_emits_edge_preference_page_and_footer_link(self) -> None:
        with tempfile.TemporaryDirectory(prefix="the-mind-privacy-") as temporary:
            dist = Path(temporary) / "dist"
            self.assertEqual(build_site.main(["--out", str(dist)]), 0)
            privacy = (dist / "privacy/index.html").read_text(encoding="utf-8")
            home = (dist / "index.html").read_text(encoding="utf-8")
            sitemap = (dist / "sitemap.xml").read_text(encoding="utf-8")

        self.assertIn('method="post" action="/analytics/opt-out"', privacy)
        self.assertIn('method="post" action="/analytics/opt-in"', privacy)
        self.assertIn("retains live analytics for 13 months", privacy)
        self.assertIn("Encrypted operational backup copies expire within 30 days", privacy)
        self.assertIn('href="./privacy/index.html"', home)
        self.assertIn("https://the-mind.xyz/privacy/", sitemap)


if __name__ == "__main__":
    unittest.main()
