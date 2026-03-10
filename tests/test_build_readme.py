import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import build_readme  # noqa: E402


class TestBuildReadme(unittest.TestCase):
    def test_rewrites_leading_slash_links_under_pages_base(self) -> None:
        md = "- [Guide](/guide/)\n- [Questions](/questions/)\n"
        out = build_readme.rewrite_links_for_readme(md, "https://p0s.github.io/the-mind/")
        self.assertIn("(https://p0s.github.io/the-mind/guide/)", out)
        self.assertIn("(https://p0s.github.io/the-mind/questions/)", out)


if __name__ == "__main__":
    unittest.main()
