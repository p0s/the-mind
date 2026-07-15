import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import check_site_links  # noqa: E402


class TestCheckSiteLinks(unittest.TestCase):
    def test_accepts_local_targets_fragments_assets_and_external_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "guide").mkdir()
            (dist / "assets").mkdir()
            (dist / "assets" / "app.js").write_text("", encoding="utf-8")
            (dist / "index.html").write_text(
                '<a href="/guide/#part-one">Guide</a>'
                '<script src="assets/app.js"></script>'
                '<a href="https://example.com/missing#remote">External</a>'
                '<a href="http://example.com/">HTTP</a>'
                '<a href="mailto:reader@example.com">Email</a>'
                '<a href="tel:+12025550123">Telephone</a>'
                '<a href="//example.com/path">Scheme-relative HTTPS</a>',
                encoding="utf-8",
            )
            (dist / "guide" / "index.html").write_text('<h2 id="part-one">Part one</h2>', encoding="utf-8")

            self.assertEqual(check_site_links.check_site_links(dist), [])

    def test_rejects_dangerous_and_unknown_uri_schemes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "index.html").write_text(
                '<a href="file:///tmp/private.txt">File</a>'
                '<a href="javascript:alert(1)">Script</a>'
                '<a href="htps://example.com">Typo</a>'
                '<img src="custom:payload">Unknown</a>',
                encoding="utf-8",
            )

            errors = check_site_links.check_site_links(dist)
            self.assertEqual(len(errors), 4)
            self.assertTrue(any("disallowed URI scheme 'file'" in error for error in errors))
            self.assertTrue(any("disallowed URI scheme 'javascript'" in error for error in errors))
            self.assertTrue(any("disallowed URI scheme 'htps'" in error for error in errors))
            self.assertTrue(any("disallowed URI scheme 'custom'" in error for error in errors))

    def test_reports_missing_target_and_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "index.html").write_text(
                '<a href="missing/">Missing</a><a href="#unknown">Unknown section</a>',
                encoding="utf-8",
            )

            errors = check_site_links.check_site_links(dist)
            self.assertEqual(len(errors), 2)
            self.assertTrue(any("missing local target" in error for error in errors))
            self.assertTrue(any("missing fragment #unknown" in error for error in errors))

    def test_rejects_reference_that_escapes_dist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            dist.mkdir()
            (dist / "index.html").write_text('<img src="../outside.png">', encoding="utf-8")

            errors = check_site_links.check_site_links(dist)
            self.assertEqual(len(errors), 1)
            self.assertIn("escapes dist", errors[0])

    def test_checks_fragment_in_htm_target_without_mutating_iteration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "index.html").write_text('<a href="legacy.htm#answer">Legacy</a>', encoding="utf-8")
            (dist / "legacy.htm").write_text('<h2 id="answer">Answer</h2>', encoding="utf-8")

            self.assertEqual(check_site_links.check_site_links(dist), [])


if __name__ == "__main__":
    unittest.main()
