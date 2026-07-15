import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import build_readme  # noqa: E402


class TestBuildReadme(unittest.TestCase):
    def test_uses_canonical_site_base_by_default(self) -> None:
        with patch.dict(os.environ, {"THE_MIND_SITE_BASE_URL": ""}):
            self.assertEqual(build_readme.site_base_url(), "https://the-mind.xyz/")

    def test_honors_site_base_override_and_normalizes_slash(self) -> None:
        with patch.dict(os.environ, {"THE_MIND_SITE_BASE_URL": "https://preview.example/site"}):
            self.assertEqual(build_readme.site_base_url(), "https://preview.example/site/")

    def test_rewrites_leading_slash_links_under_site_base(self) -> None:
        md = "- [Guide](/guide/)\n- [Questions](/questions/)\n"
        out = build_readme.rewrite_links_for_readme(md, "https://the-mind.xyz/")
        self.assertIn("(https://the-mind.xyz/guide/)", out)
        self.assertIn("(https://the-mind.xyz/questions/)", out)

    def test_appends_repo_non_affiliation_note_when_home_omits_it(self) -> None:
        out = build_readme.ensure_repo_non_affiliation_note("# Home\n")
        self.assertTrue(out.endswith("Not affiliated with or endorsed by Joscha Bach.\n"))
        self.assertEqual(out.count(build_readme.NON_AFFILIATION_NOTE), 1)

    def test_does_not_duplicate_existing_non_affiliation_note(self) -> None:
        md = f"# Home\n\n{build_readme.NON_AFFILIATION_NOTE}\n"
        out = build_readme.ensure_repo_non_affiliation_note(md)
        self.assertEqual(out.count(build_readme.NON_AFFILIATION_NOTE), 1)


if __name__ == "__main__":
    unittest.main()
