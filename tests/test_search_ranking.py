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

    def test_cached_loader_shares_success_and_retries_failure(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required to test the browser search loader")
        module_path = json.dumps(str(ROOT / "site" / "assets" / "search.js"))
        script = f"""
const search = require({module_path});

(async () => {{
  let successCalls = 0;
  const successfulLoad = search.createCachedLoader(async () => {{
    successCalls += 1;
    await Promise.resolve();
    return ["ready"];
  }});
  const first = successfulLoad();
  const second = successfulLoad();
  const concurrent = await Promise.all([first, second]);
  const cached = await successfulLoad();

  let retryCalls = 0;
  const retryingLoad = search.createCachedLoader(async () => {{
    retryCalls += 1;
    if (retryCalls === 1) throw new Error("temporary failure");
    return ["recovered"];
  }});
  let firstError = "";
  try {{
    await retryingLoad();
  }} catch (error) {{
    firstError = error.message;
  }}
  const retried = await retryingLoad();

  process.stdout.write(JSON.stringify({{
    successCalls,
    concurrent,
    cached,
    retryCalls,
    firstError,
    retried,
  }}));
}})().catch((error) => {{
  console.error(error);
  process.exit(1);
}});
"""
        completed = subprocess.run(
            [node, "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)

        self.assertEqual(result["successCalls"], 1)
        self.assertEqual(result["concurrent"], [["ready"], ["ready"]])
        self.assertEqual(result["cached"], ["ready"])
        self.assertEqual(result["retryCalls"], 2)
        self.assertEqual(result["firstError"], "temporary failure")
        self.assertEqual(result["retried"], ["recovered"])

    def test_search_ui_retries_the_same_query_after_load_failure(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required to test the browser search UI")
        search_path = json.dumps(str(ROOT / "site" / "assets" / "search.js"))
        app_path = json.dumps(str(ROOT / "site" / "assets" / "app.js"))
        script = f"""
const fs = require("fs");
const {{ JSDOM }} = require("jsdom");

(async () => {{
  const dom = new JSDOM(
    '<input id="searchInput"><div id="searchResults" hidden></div>',
    {{ runScripts: "outside-only", url: "https://example.test/" }},
  );
  const {{ window }} = dom;
  let fetchCalls = 0;
  window.fetch = async () => {{
    fetchCalls += 1;
    if (fetchCalls === 1) return {{ ok: false, status: 503 }};
    return {{
      ok: true,
      json: async () => [{{
        href: "questions/what-is-consciousness/index.html",
        title: "The mind",
        text: "A search result about the mind.",
        search_priority: 1,
      }}],
    }};
  }};
  window.eval(fs.readFileSync({search_path}, "utf8"));
  window.eval(fs.readFileSync({app_path}, "utf8"));

  const input = window.document.getElementById("searchInput");
  const results = window.document.getElementById("searchResults");
  input.value = "mind";
  input.dispatchEvent(new window.Event("input", {{ bubbles: true }}));
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  const failedText = results.textContent.trim();

  input.dispatchEvent(new window.Event("input", {{ bubbles: true }}));
  await new Promise((resolve) => window.setTimeout(resolve, 0));

  process.stdout.write(JSON.stringify({{
    fetchCalls,
    failedText,
    recoveredText: results.textContent.trim(),
    hidden: results.hidden,
  }}));
  window.close();
}})().catch((error) => {{
  console.error(error);
  process.exit(1);
}});
"""
        completed = subprocess.run(
            [node, "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)

        self.assertEqual(result["fetchCalls"], 2)
        self.assertEqual(result["failedText"], "Search unavailable.")
        self.assertIn("The mind", result["recoveredText"])
        self.assertFalse(result["hidden"])


if __name__ == "__main__":
    unittest.main()
