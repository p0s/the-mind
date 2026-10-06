import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_site

class Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}
        self.title = ""
        self.in_title = False
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta":
            key = values.get("name") or values.get("property")
            if key: self.values.setdefault(key, []).append(values.get("content"))
        if tag == "title": self.in_title = True
    def handle_endtag(self, tag):
        if tag == "title": self.in_title = False
    def handle_data(self, data):
        if self.in_title: self.title += data

class TestPageMetadata(unittest.TestCase):
    def test_all_rendered_pages_have_explicit_distinct_metadata(self):
        with tempfile.TemporaryDirectory(prefix="mind-metadata-") as temporary:
            output = Path(temporary) / "site"
            self.assertEqual(build_site.main(["--out", str(output)]), 0)
            descriptions = []
            pages = sorted(output.rglob("index.html"))
            self.assertEqual(len(pages), 18)
            for page in pages:
                metadata = Metadata()
                metadata.feed(page.read_text())
                href = page.relative_to(output).as_posix()
                expected = build_site.page_description(href)
                self.assertEqual(metadata.values["description"], [expected], href)
                self.assertEqual(metadata.values["og:description"], [expected], href)
                self.assertEqual(metadata.values["og:title"], [metadata.title], href)
                self.assertNotIn("{{", page.read_text(), href)
                descriptions.append(expected)
            self.assertEqual(len(set(descriptions)), len(pages))
            home = (output / "index.html").read_text()
            self.assertIn("Mind, consciousness, and AI", home)
            self.assertIn("Hikari Sorensen", home)
            self.assertIn("Not affiliated with or endorsed", home)

    def test_new_public_route_requires_a_description(self):
        with self.assertRaisesRegex(ValueError, "Missing explicit page description"):
            build_site.page_description("questions/unregistered/index.html")

    def test_metadata_escapes_attribute_text(self):
        description = 'A "quoted" proposal & <script>unsupported</script>'
        output = build_site.render_page(build_site.read_template(), title='A <title> & "test"', description=description, nav="", content="<h1>Test</h1>", root="./", page_id="test", page_url="https://the-mind.xyz/test/", og_image_url="https://the-mind.xyz/og.png")
        metadata = Metadata()
        metadata.feed(output)
        self.assertEqual(metadata.values["description"], [description])
        self.assertEqual(metadata.values["og:description"], [description])
        self.assertNotIn("<script>unsupported", output)
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            build_site.render_page("", title="Test", description=" ", nav="", content="", root="./", page_id="test", page_url="", og_image_url="")

if __name__ == "__main__":
    unittest.main()
