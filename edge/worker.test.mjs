import assert from "node:assert/strict";
import { FixtureRewriter } from "./test-fixtures.mjs";
import worker, {
  canonicalRedirect,
  eligiblePath,
  eligibleResponse,
  fetchAssets,
  payloadFor,
  prefersMarkdown,
} from "./worker.js";
globalThis.HTMLRewriter = FixtureRewriter;

function request(path = "/", headers = {}) {
  const value = new Request(`https://the-mind.xyz${path}`, {
    method: "GET",
    headers: {
      "CF-Connecting-IP": "203.0.113.9",
      "User-Agent": "Mozilla/5.0",
      ...headers,
    },
  });
  Object.defineProperty(value, "cf", { value: { country: "sg" } });
  return value;
}

const document = new Response("<!doctype html>", {
  status: 200,
  headers: { "Content-Type": "text/html; charset=UTF-8", "CF-Cache-Status": "HIT" },
});
const page = request("/questions/what-is-a-mind/", { Referer: "https://search.example/path?q=redacted" });
assert.equal(eligiblePath("/questions/what-is-a-mind/"), true);
assert.equal(eligiblePath("/assets/style.css"), false);
assert.equal(eligibleResponse(page, document), true);
assert.deepEqual(payloadFor(page), {
  hostname: "the-mind.xyz",
  path: "/questions/what-is-a-mind/",
  referrer: "https://search.example",
  ip: "203.0.113.9",
  userAgent: "Mozilla/5.0",
  country: "SG",
});
assert.equal(eligibleResponse(request("/questions/what-is-a-mind/", { DNT: "1" }), document), false);
assert.equal(eligibleResponse(request("/questions/what-is-a-mind/", { Purpose: "prefetch" }), document), false);
assert.equal(eligibleResponse(request("/questions/what-is-a-mind/", { "User-Agent": "ExampleBot" }), document), false);

const assetRequests = [];
const assets = {
  fetch: async (input) => {
    assetRequests.push(input);
    return document;
  },
};
assert.equal(await fetchAssets(page, { ASSETS: assets }), document);

const releaseIdentity = await worker.fetch(new Request("https://the-mind.xyz/.well-known/indexnow-release.json"), {
  ASSETS: {
    fetch: async () => new Response('{"version":1}', { status: 200, headers: { "Cache-Control": "public, max-age=3600" } }),
  },
}, {});
assert.equal(releaseIdentity.status, 200);
assert.equal(releaseIdentity.headers.get("Cache-Control"), "no-store");
assert.equal(releaseIdentity.headers.get("X-Robots-Tag"), "noindex");
assert.equal(await releaseIdentity.text(), '{"version":1}');

const originalFetch = globalThis.fetch;
const seen = [];
globalThis.fetch = async (input, options) => {
  const url = typeof input === "string" ? input : input.url;
  seen.push({ input: url, options });
  if (url.startsWith("https://stats.p0s.eu/")) return new Response(null, { status: 204 });
  return document;
};
const waits = [];
const response = await worker.fetch(page, {
  ASSETS: assets,
  ANALYTICS_INGEST_URL: "https://stats.p0s.eu/ingest/v1",
  ANALYTICS_INGEST_TOKEN: "test-token",
}, { waitUntil: (promise) => waits.push(promise) });
assert.equal(response.status, 200);
assert.equal(response.headers.get("Cache-Control"), "private, no-store");
assert.equal(await response.text(), "<!doctype html>");
assert.equal(assetRequests[0].url, page.url);
assert.equal(seen.length, 1);
assert.equal(waits.length, 1);
await waits[0];
assert.equal(seen[0].options.headers.authorization, "Bearer test-token");
assert.match(JSON.parse(seen[0].options.body).eventId, /^[0-9a-f]{32}$/);

const unavailable = await worker.fetch(page, {}, {});
assert.equal(unavailable.status, 503);

const wwwPage = new Request("https://www.the-mind.xyz/questions/what-is-a-mind/");
const wwwRedirect = await worker.fetch(wwwPage, { ASSETS: assets }, {});
assert.equal(wwwRedirect.status, 301);
assert.equal(wwwRedirect.headers.get("Location"), "https://the-mind.xyz/questions/what-is-a-mind/");
assert.equal(wwwRedirect.headers.get("Referrer-Policy"), "same-origin");

const wwwPost = new Request("https://www.the-mind.xyz/analytics/opt-out", { method: "POST" });
const wwwPostRedirect = await worker.fetch(wwwPost, { ASSETS: assets }, {});
assert.equal(wwwPostRedirect.status, 308);
assert.equal(wwwPostRedirect.headers.get("Location"), "https://the-mind.xyz/analytics/opt-out");
assert.equal(canonicalRedirect(wwwPage).status, 301);

const form = await worker.fetch(new Request("https://the-mind.xyz/analytics/opt-out"), {}, {});
assert.equal(form.status, 200);
assert.match(await form.text(), /method="post"/);
const crossOrigin = await worker.fetch(new Request("https://the-mind.xyz/analytics/opt-out", {
  method: "POST",
  headers: { Origin: "https://evil.example" },
}), {}, {});
assert.equal(crossOrigin.status, 403);

// Agent-readable responses: Markdown negotiation and discovery headers.
const browserAccept = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8";
function agentRequest(path, accept, method = "GET") {
  const value = new Request(`https://the-mind.xyz${path}`, {
    method,
    headers: { "CF-Connecting-IP": "203.0.113.9", "User-Agent": "Mozilla/5.0", ...(accept ? { Accept: accept } : {}) },
  });
  Object.defineProperty(value, "cf", { value: { country: "sg" } });
  return value;
}
for (const [accept, expected] of [
  ["text/markdown", true],
  ["text/markdown, text/html;q=0.9", true],
  ["text/markdown, */*", true],
  ["text/html, text/markdown;q=0.5", false],
  ["text/markdown;q=0, text/html", false],
  ["text/*", false],
  ["*/*", false],
  [browserAccept, false],
  [undefined, false],
]) {
  assert.equal(prefersMarkdown(agentRequest("/", accept)), expected, accept);
}

const siteFiles = new Map([
  ["/", ["text/html", "<!doctype html><body>home</body>"]],
  ["/index.md", ["text/markdown", "# Home\n"]],
  ["/guide/", ["text/html", "<!doctype html><body>guide</body>"]],
  ["/guide/index.md", ["text/markdown", "# Guide\n"]],
  ["/llms.txt", ["text/plain", "# the-mind\n"]],
]);
const siteAssets = {
  fetch: async (input) => {
    const file = siteFiles.get(new URL(input.url).pathname);
    if (!file) return new Response(null, { status: 404 });
    return new Response(input.method === "HEAD" ? null : file[1], {
      status: 200,
      headers: { "Content-Type": file[0], "Cache-Control": "public, max-age=0, must-revalidate" },
    });
  },
};
const agentWaits = [];
const agentEnv = {
  ASSETS: siteAssets,
  ANALYTICS_INGEST_URL: "https://stats.p0s.eu/ingest/v1",
  ANALYTICS_INGEST_TOKEN: "test-token",
};
const agentCtx = { waitUntil: (promise) => agentWaits.push(promise) };

const markdownHome = await worker.fetch(agentRequest("/", "text/markdown"), agentEnv, agentCtx);
assert.equal(markdownHome.status, 200);
assert.equal(markdownHome.headers.get("Content-Type"), "text/markdown; charset=utf-8");
assert.equal(markdownHome.headers.get("Content-Location"), "/index.md");
assert.equal(markdownHome.headers.get("Link"), '<https://the-mind.xyz/>; rel="canonical"');
assert.equal(markdownHome.headers.get("Vary"), "Accept");
assert.equal(markdownHome.headers.get("X-Content-Type-Options"), "nosniff");
assert.equal(markdownHome.headers.get("Cache-Control"), "public, max-age=0, must-revalidate");
assert.equal(await markdownHome.text(), "# Home\n");

const markdownHead = await worker.fetch(agentRequest("/guide/", "text/markdown, text/html;q=0.9", "HEAD"), agentEnv, agentCtx);
assert.equal(markdownHead.status, 200);
assert.equal(markdownHead.headers.get("Content-Type"), "text/markdown; charset=utf-8");
assert.equal(markdownHead.headers.get("Content-Location"), "/guide/index.md");
assert.equal(await markdownHead.text(), "");

const htmlHome = await worker.fetch(agentRequest("/", browserAccept), agentEnv, agentCtx);
assert.equal(htmlHome.headers.get("Content-Type"), "text/html");
assert.equal(
  htmlHome.headers.get("Link"),
  '<https://the-mind.xyz/index.md>; rel="alternate"; type="text/markdown", '
    + '<https://the-mind.xyz/llms.txt>; rel="describedby"; type="text/plain"',
);
assert.equal(htmlHome.headers.get("Vary"), "Accept");
assert.equal(htmlHome.headers.get("Cache-Control"), "private, no-store");
assert.match(await htmlHome.text(), /<body data-site-measurement="allowed">home/);

const htmlGuide = await worker.fetch(agentRequest("/guide/", "text/html, text/markdown;q=0.5"), agentEnv, agentCtx);
assert.equal(htmlGuide.headers.get("Content-Type"), "text/html");
assert.equal(htmlGuide.headers.get("Link"), '<https://the-mind.xyz/guide/index.md>; rel="alternate"; type="text/markdown"');
assert.match(await htmlGuide.text(), /guide/);

const missingMarkdown = await worker.fetch(agentRequest("/missing/", "text/markdown"), agentEnv, agentCtx);
assert.equal(missingMarkdown.status, 404);
assert.equal(missingMarkdown.headers.get("Link"), null);
assert.equal(missingMarkdown.headers.get("Content-Type"), null);

const directMarkdown = await worker.fetch(agentRequest("/guide/index.md"), agentEnv, agentCtx);
assert.equal(directMarkdown.headers.get("Content-Type"), "text/markdown; charset=utf-8");
assert.equal(directMarkdown.headers.get("Link"), '<https://the-mind.xyz/guide/>; rel="canonical"');
assert.equal(directMarkdown.headers.get("Content-Location"), null);
assert.equal(await directMarkdown.text(), "# Guide\n");

const llmsIndex = await worker.fetch(agentRequest("/llms.txt"), agentEnv, agentCtx);
assert.equal(llmsIndex.headers.get("Content-Type"), "text/plain; charset=utf-8");
assert.equal(llmsIndex.headers.get("Link"), null);

// Only the two ordinary HTML page views are eligible for counting.
assert.equal(agentWaits.length, 2);
await Promise.all(agentWaits);
const unavailableMarkdown = await worker.fetch(agentRequest("/", "text/markdown"), {}, {});
assert.equal(unavailableMarkdown.status, 503);

globalThis.fetch = originalFetch;
console.log("the-mind analytics edge contract: ok");
