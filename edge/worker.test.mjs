import assert from "node:assert/strict";
import worker, {
  eligiblePath,
  eligibleResponse,
  fetchAssets,
  payloadFor,
} from "./worker.js";

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

const originalFetch = globalThis.fetch;
const seen = [];
globalThis.fetch = async (input, options) => {
  const url = typeof input === "string" ? input : input.url;
  seen.push({ input: url, options });
  if (url.startsWith("https://stats.p0s.eu/")) return new Response("ok", { status: 204 });
  return document;
};
const waits = [];
const response = await worker.fetch(page, {
  ASSETS: assets,
  ANALYTICS_INGEST_URL: "https://stats.p0s.eu/ingest/v1",
  ANALYTICS_INGEST_TOKEN: "test-token",
}, { waitUntil: (promise) => waits.push(promise) });
assert.equal(response, document);
assert.equal(assetRequests[0].url, page.url);
assert.equal(seen.length, 1);
assert.equal(waits.length, 1);
await waits[0];
assert.equal(seen[0].options.headers.Authorization, "Bearer test-token");

const unavailable = await worker.fetch(page, {}, {});
assert.equal(unavailable.status, 503);

const form = await worker.fetch(new Request("https://the-mind.xyz/analytics/opt-out"), {}, {});
assert.equal(form.status, 200);
assert.match(await form.text(), /method="post"/);
const crossOrigin = await worker.fetch(new Request("https://the-mind.xyz/analytics/opt-out", {
  method: "POST",
  headers: { Origin: "https://evil.example" },
}), {}, {});
assert.equal(crossOrigin.status, 403);

globalThis.fetch = originalFetch;
console.log("the-mind analytics edge contract: ok");
