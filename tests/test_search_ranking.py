import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import build_site  # noqa: E402


class TestSearchRanking(unittest.TestCase):
    def test_generated_index_marks_active_and_archive_tiers(self) -> None:
        self.assertEqual(build_site.search_priority_for_href("questions/what-is-consciousness/index.html"), 1)
        self.assertEqual(build_site.search_priority_for_href("archive/index.html"), 0)
        self.assertEqual(build_site.search_priority_for_href("reader/index.html"), 0)
        self.assertEqual(build_site.search_priority_for_href("reader/index.html#chapter-10-consciousness"), 0)

    def test_active_v2_result_ranks_before_archive_matches(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required to test the browser search ranking")
        module_path = json.dumps(str(ROOT / "site" / "assets" / "search.js"))
        script = f"""
const search = require({module_path});
const ranked = search.rankSearchIndex([
  {{ href: "reader/index.html#chapter", title: "Consciousness", text: "consciousness ".repeat(200), search_priority: 0 }},
  {{ href: "archive/index.html", title: "Archive", text: "consciousness ".repeat(300), search_priority: 0 }},
  {{ href: "questions/what-is-consciousness/index.html", title: "What is consciousness?", text: "A concise guide.", search_priority: 1 }}
], "consciousness");
process.stdout.write(JSON.stringify(ranked.map((item) => item.href)));
"""
        completed = subprocess.run(
            [node, "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        ranked_hrefs = json.loads(completed.stdout)

        self.assertEqual(ranked_hrefs[0], "questions/what-is-consciousness/index.html")
        self.assertCountEqual(
            ranked_hrefs[1:],
            ["reader/index.html#chapter", "archive/index.html"],
        )


if __name__ == "__main__":
    unittest.main()
