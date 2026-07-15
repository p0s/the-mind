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

    def test_search_ui_shares_pending_load_and_does_not_flicker_when_warm(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required to test the browser search UI")
        search_path = json.dumps(str(ROOT / "site" / "assets" / "search.js"))
        app_path = json.dumps(str(ROOT / "site" / "assets" / "app.js"))
        script = f"""
const fs = require("fs");
const {{ JSDOM }} = require("jsdom");

(async () => {{
  const dom = new JSDOM(
    '<input id="searchInput"><div id="searchStatus" role="status"></div><div id="searchResults" aria-busy="false" hidden></div>',
    {{ runScripts: "outside-only", url: "https://example.test/" }},
  );
  const {{ window }} = dom;
  let fetchCalls = 0;
  let resolveFetch;
  window.fetch = () => {{
    fetchCalls += 1;
    return new Promise((resolve) => {{
      resolveFetch = resolve;
    }});
  }};
  window.eval(fs.readFileSync({search_path}, "utf8"));
  window.eval(fs.readFileSync({app_path}, "utf8"));

  const input = window.document.getElementById("searchInput");
  const liveStatus = window.document.getElementById("searchStatus");
  const results = window.document.getElementById("searchResults");
  input.value = "alpha";
  input.dispatchEvent(new window.Event("input", {{ bubbles: true }}));
  const firstPending = {{
    busy: results.getAttribute("aria-busy"),
    hidden: results.hidden,
    text: results.textContent.trim(),
    visualStatusHidden: results.firstElementChild && results.firstElementChild.getAttribute("aria-hidden"),
    liveText: liveStatus.textContent,
    liveRole: liveStatus.getAttribute("role"),
    liveInsideResults: results.contains(liveStatus),
  }};

  input.value = "beta";
  input.dispatchEvent(new window.Event("input", {{ bubbles: true }}));
  const sharedPending = {{
    busy: results.getAttribute("aria-busy"),
    hidden: results.hidden,
    text: results.textContent.trim(),
    liveText: liveStatus.textContent,
  }};

  await Promise.resolve();
  resolveFetch({{
    ok: true,
    json: async () => [
      {{ href: "alpha/index.html", title: "Alpha result", text: "alpha", search_priority: 1 }},
      {{ href: "beta/index.html", title: "Beta result", text: "beta", search_priority: 1 }},
    ],
  }});
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  const settled = {{
    busy: results.getAttribute("aria-busy"),
    hidden: results.hidden,
    text: results.textContent.trim(),
    liveText: liveStatus.textContent,
  }};

  input.value = "alpha";
  input.dispatchEvent(new window.Event("input", {{ bubbles: true }}));
  const warmImmediate = {{
    busy: results.getAttribute("aria-busy"),
    hidden: results.hidden,
    text: results.textContent.trim(),
    hasPendingStatus: Boolean(results.querySelector(".search__status")),
  }};
  await new Promise((resolve) => window.setTimeout(resolve, 0));

  process.stdout.write(JSON.stringify({{
    fetchCalls,
    firstPending,
    sharedPending,
    settled,
    warmImmediate,
    warmSettledText: results.textContent.trim(),
    warmSettledBusy: results.getAttribute("aria-busy"),
    warmSettledLiveText: liveStatus.textContent,
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

        self.assertEqual(result["fetchCalls"], 1)
        self.assertEqual(
            result["firstPending"],
            {
                "busy": "true",
                "hidden": False,
                "text": "Searching…",
                "visualStatusHidden": "true",
                "liveText": "Searching…",
                "liveRole": "status",
                "liveInsideResults": False,
            },
        )
        self.assertEqual(
            result["sharedPending"],
            {"busy": "true", "hidden": False, "text": "Searching…", "liveText": "Searching…"},
        )
        self.assertEqual(result["settled"]["busy"], "false")
        self.assertFalse(result["settled"]["hidden"])
        self.assertIn("Beta result", result["settled"]["text"])
        self.assertNotIn("Alpha result", result["settled"]["text"])
        self.assertEqual(result["settled"]["liveText"], "Search complete.")
        self.assertEqual(result["warmImmediate"]["busy"], "false")
        self.assertFalse(result["warmImmediate"]["hidden"])
        self.assertFalse(result["warmImmediate"]["hasPendingStatus"])
        self.assertIn("Beta result", result["warmImmediate"]["text"])
        self.assertEqual(result["warmSettledBusy"], "false")
        self.assertIn("Alpha result", result["warmSettledText"])
        self.assertEqual(result["warmSettledLiveText"], "Search complete.")

    def test_search_ui_empty_query_invalidates_pending_render(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required to test the browser search UI")
        search_path = json.dumps(str(ROOT / "site" / "assets" / "search.js"))
        app_path = json.dumps(str(ROOT / "site" / "assets" / "app.js"))
        script = f"""
const fs = require("fs");
const {{ JSDOM }} = require("jsdom");

(async () => {{
  const dom = new JSDOM(
    '<input id="searchInput"><div id="searchStatus" role="status"></div><div id="searchResults" aria-busy="false" hidden></div>',
    {{ runScripts: "outside-only", url: "https://example.test/" }},
  );
  const {{ window }} = dom;
  let fetchCalls = 0;
  let resolveFetch;
  window.fetch = () => {{
    fetchCalls += 1;
    return new Promise((resolve) => {{
      resolveFetch = resolve;
    }});
  }};
  window.eval(fs.readFileSync({search_path}, "utf8"));
  window.eval(fs.readFileSync({app_path}, "utf8"));

  const input = window.document.getElementById("searchInput");
  const liveStatus = window.document.getElementById("searchStatus");
  const results = window.document.getElementById("searchResults");
  input.value = "alpha";
  input.dispatchEvent(new window.Event("input", {{ bubbles: true }}));
  await Promise.resolve();

  input.value = "";
  input.dispatchEvent(new window.Event("input", {{ bubbles: true }}));
  const cleared = {{
    busy: results.getAttribute("aria-busy"),
    hidden: results.hidden,
    liveText: liveStatus.textContent,
  }};

  resolveFetch({{
    ok: true,
    json: async () => [
      {{ href: "alpha/index.html", title: "Alpha result", text: "alpha", search_priority: 1 }},
      {{ href: "beta/index.html", title: "Beta result", text: "beta", search_priority: 1 }},
    ],
  }});
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  const staleSettled = {{
    busy: results.getAttribute("aria-busy"),
    hidden: results.hidden,
    liveText: liveStatus.textContent,
  }};

  input.value = "beta";
  input.dispatchEvent(new window.Event("input", {{ bubbles: true }}));
  const warmImmediate = {{
    busy: results.getAttribute("aria-busy"),
    visiblePending: !results.hidden && Boolean(results.querySelector(".search__status")),
  }};
  await new Promise((resolve) => window.setTimeout(resolve, 0));

  process.stdout.write(JSON.stringify({{
    fetchCalls,
    cleared,
    staleSettled,
    warmImmediate,
    warmSettledBusy: results.getAttribute("aria-busy"),
    warmSettledHidden: results.hidden,
    warmSettledText: results.textContent.trim(),
    warmSettledLiveText: liveStatus.textContent,
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

        self.assertEqual(result["fetchCalls"], 1)
        self.assertEqual(result["cleared"], {"busy": "false", "hidden": True, "liveText": ""})
        self.assertEqual(result["staleSettled"], {"busy": "false", "hidden": True, "liveText": ""})
        self.assertEqual(result["warmImmediate"]["busy"], "false")
        self.assertFalse(result["warmImmediate"]["visiblePending"])
        self.assertEqual(result["warmSettledBusy"], "false")
        self.assertFalse(result["warmSettledHidden"])
        self.assertIn("Beta result", result["warmSettledText"])
        self.assertEqual(result["warmSettledLiveText"], "Search complete.")

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
    '<input id="searchInput"><div id="searchStatus" role="status"></div><div id="searchResults" aria-busy="false" hidden></div>',
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
  const liveStatus = window.document.getElementById("searchStatus");
  const results = window.document.getElementById("searchResults");
  input.value = "mind";
  input.dispatchEvent(new window.Event("input", {{ bubbles: true }}));
  const firstPending = {{
    busy: results.getAttribute("aria-busy"),
    hidden: results.hidden,
    text: results.textContent.trim(),
    liveText: liveStatus.textContent,
  }};
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  const failed = {{
    busy: results.getAttribute("aria-busy"),
    hidden: results.hidden,
    text: results.textContent.trim(),
    liveText: liveStatus.textContent,
  }};

  input.dispatchEvent(new window.Event("input", {{ bubbles: true }}));
  const retryPending = {{
    busy: results.getAttribute("aria-busy"),
    hidden: results.hidden,
    text: results.textContent.trim(),
    liveText: liveStatus.textContent,
  }};
  await new Promise((resolve) => window.setTimeout(resolve, 0));

  process.stdout.write(JSON.stringify({{
    fetchCalls,
    firstPending,
    failed,
    retryPending,
    recovered: {{
      busy: results.getAttribute("aria-busy"),
      hidden: results.hidden,
      text: results.textContent.trim(),
      liveText: liveStatus.textContent,
    }},
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
        self.assertEqual(
            result["firstPending"],
            {"busy": "true", "hidden": False, "text": "Searching…", "liveText": "Searching…"},
        )
        self.assertEqual(
            result["failed"],
            {
                "busy": "false",
                "hidden": False,
                "text": "Search unavailable.",
                "liveText": "Search unavailable.",
            },
        )
        self.assertEqual(
            result["retryPending"],
            {"busy": "true", "hidden": False, "text": "Searching…", "liveText": "Searching…"},
        )
        self.assertEqual(result["recovered"]["busy"], "false")
        self.assertIn("The mind", result["recovered"]["text"])
        self.assertFalse(result["recovered"]["hidden"])
        self.assertEqual(result["recovered"]["liveText"], "Search complete.")


if __name__ == "__main__":
    unittest.main()
