import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  SITES,
  buildLocalManifest,
  canonicalPageUrl,
  compareState,
  initialState,
  prepareDelivery,
  recordDeliveryResult,
  revisionFor,
  submitPrepared,
  verifyLivePublication,
  writeReleaseIdentity,
} from "../scripts/indexnow-publisher.mjs";

const host = "the-mind.xyz";
const sourceSha = "cf581a3a991229139f9fd60d3a8ee9605a137f05";
const key = SITES[host].keyFile.slice(0, -4);
const at = new Date("2026-10-12T00:00:00.000Z");

function manifest(pages, sha = sourceSha) {
  return { host, sourceSha: sha, revision: revisionFor(host, sha), key, keyFile: SITES[host].keyFile, pages };
}

function page(digest) {
  return { digest: digest.repeat(64).slice(0, 64) };
}

function fixture(t) {
  const root = mkdtempSync(path.join(os.tmpdir(), "p0s-indexnow-publisher-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  writeFileSync(path.join(root, SITES[host].keyFile), `${key}\n`);
  writeFileSync(path.join(root, "sitemap.xml"), '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://the-mind.xyz/</loc></url></urlset>');
  writeFileSync(path.join(root, "index.html"), '<html><head><link rel="stylesheet" href="/site.css"><script type="module" src="/app.js"></script></head><body></body></html>');
  writeFileSync(path.join(root, "site.css"), '@import url("/theme.css");');
  writeFileSync(path.join(root, "theme.css"), "body { background-image: url('/image.png'); }");
  writeFileSync(path.join(root, "app.js"), 'import "./module.js";');
  writeFileSync(path.join(root, "module.js"), "export const version = 1;");
  writeFileSync(path.join(root, "image.png"), "image-v1");
  return root;
}

function fakeLive(current, calls = [], status = 202) {
  return async (url, init = {}) => {
    if (url === `https://${host}/.well-known/indexnow-release.json`) {
      return new Response(JSON.stringify({ version: 1, host, revision: current.revision }), { status: 200 });
    }
    if (url === `https://${host}/${current.keyFile}`) return new Response(`${current.key}\n`, { status: 200 });
    if (url === `https://${host}/sitemap.xml`) {
      const records = Object.keys(current.pages).map((pageUrl) => `<url><loc>${pageUrl}</loc></url>`).join("");
      return new Response(`<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${records}</urlset>`, { status: 200 });
    }
    if (url === "https://www.bing.com/indexnow" && init.method === "POST") {
      assert.equal(init.redirect, "error");
      calls.push(JSON.parse(init.body));
      return new Response("", { status });
    }
    throw new Error(`Unexpected fake transport request: ${url}`);
  };
}

test("build manifest fingerprints page content and recursively referenced local assets", async (t) => {
  const root = fixture(t);
  const first = await buildLocalManifest({ host, directory: root, sourceSha });
  writeFileSync(path.join(root, "image.png"), "image-v2");
  const second = await buildLocalManifest({ host, directory: root, sourceSha });
  assert.notEqual(first.pages["https://the-mind.xyz/"].digest, second.pages["https://the-mind.xyz/"].digest);
});

test("release identity is opaque, tied to the host and source, and never overwrites", async (t) => {
  const root = fixture(t);
  const target = await writeReleaseIdentity({ host, directory: root, sourceSha });
  const identity = JSON.parse(await (await import("node:fs/promises")).readFile(target, "utf8"));
  assert.deepEqual(identity, { version: 1, host, revision: revisionFor(host, sourceSha) });
  assert.equal(Object.hasOwn(identity, "sourceSha"), false);
  assert.throws(() => canonicalPageUrl("https://the-mind.xyz/.well-known/indexnow-release.json", host), /private or internal/u);
  assert.throws(() => canonicalPageUrl("https://the-mind.xyz:8443/public/", host), /canonical HTTPS/u);
  assert.throws(() => canonicalPageUrl("https://the-mind.xyz/public/?preview=1", host), /canonical HTTPS/u);
  await assert.rejects(writeReleaseIdentity({ host, directory: root, sourceSha }), /Refusing to overwrite/u);
  const updatedSha = "a".repeat(40);
  await writeReleaseIdentity({ host, directory: root, sourceSha: updatedSha, replaceExisting: true });
  const updated = JSON.parse(await (await import("node:fs/promises")).readFile(target, "utf8"));
  assert.equal(updated.revision, revisionFor(host, updatedSha));
});

test("a no-op verifies production but makes no IndexNow request", async () => {
  const current = manifest({ "https://the-mind.xyz/": page("a") });
  const state = initialState(host, current);
  const prepared = prepareDelivery(state, current, at);
  const calls = [];
  await verifyLivePublication({ host, current, state, fetchImpl: fakeLive(current, calls) });
  const result = await submitPrepared({ host, current, preparedState: prepared.state, urls: prepared.urls, fetchImpl: fakeLive(current, calls), now: at });
  assert.equal(prepared.status, "no_changes");
  assert.equal(result.status, "no_changes");
  assert.equal(calls.length, 0);
});

test("live release, key, and sitemap mismatches fail closed before delivery", async () => {
  const current = manifest({ "https://the-mind.xyz/": page("a") });
  const state = initialState(host, current);
  const invalid = [
    ["release", `https://${host}/.well-known/indexnow-release.json`, new Response(JSON.stringify({ version: 1, host, revision: "0".repeat(64) }), { status: 200 })],
    ["key", `https://${host}/${current.keyFile}`, new Response("wrong-key\n", { status: 200 })],
    ["sitemap", `https://${host}/sitemap.xml`, new Response('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://the-mind.xyz/extra/</loc></url></urlset>', { status: 200 })],
  ];
  for (const [label, rejectedUrl, rejectedResponse] of invalid) {
    const validFetch = fakeLive(current);
    const fetchImpl = async (url, init) => url === rejectedUrl ? rejectedResponse : validFetch(url, init);
    await assert.rejects(verifyLivePublication({ host, current, state, fetchImpl }), new RegExp(label === "release" ? "Live production release" : label === "key" ? "Live IndexNow key" : "Live sitemap", "u"));
  }
});

test("a 202 receipt records pending key validation and does not replay unchanged URLs", async () => {
  const oldUrl = "https://the-mind.xyz/old/";
  const newUrl = "https://the-mind.xyz/new/";
  const previous = manifest({ [oldUrl]: page("a") });
  const current = manifest({ [newUrl]: page("b") }, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
  const state = initialState(host, previous);
  const prepared = prepareDelivery(state, current, at);
  assert.deepEqual(prepared.urls, [newUrl, oldUrl].sort());
  assert.deepEqual(compareState(state, current).deleted, [oldUrl]);
  const calls = [];
  await verifyLivePublication({ host, current, state, fetchImpl: fakeLive(current, calls, 202) });
  const result = await submitPrepared({ host, current, preparedState: prepared.state, urls: prepared.urls, fetchImpl: fakeLive(current, calls, 202), now: at });
  assert.equal(result.status, "received_key_validation_pending");
  assert.equal(result.state.receipts.at(-1).state, "received_key_validation_pending");
  assert.equal(result.state.receipts.at(-1).httpStatus, 202);
  assert.deepEqual(Object.keys(result.state.acceptedPages), [newUrl]);
  assert.deepEqual(result.state.pending, {});
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].urlList, prepared.urls);
  const next = prepareDelivery(result.state, current, new Date(at.getTime() + 60_000));
  assert.equal(next.status, "no_changes");
  assert.deepEqual(next.urls, []);
});

test("a transient failure remains pending, honors its delay, and holds permanent client errors", async () => {
  const url = "https://the-mind.xyz/";
  const previous = manifest({ [url]: page("a") });
  const current = manifest({ [url]: page("b") }, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
  const first = prepareDelivery(initialState(host, previous), current, at);
  const failed = recordDeliveryResult(first.state, current, first.urls, { status: 503 }, at);
  assert.equal(failed.pending[url].attempts, 1);
  assert.equal(Date.parse(failed.pending[url].nextAttemptAt), at.getTime() + 60_000);
  const beforeDelay = prepareDelivery(failed, current, new Date(at.getTime() + 30_000));
  assert.equal(beforeDelay.status, "pending");
  assert.deepEqual(beforeDelay.urls, []);
  await verifyLivePublication({ host, current, state: failed, fetchImpl: fakeLive(current) });
  const retry = prepareDelivery(failed, current, new Date(at.getTime() + 60_000));
  assert.equal(retry.state.pending[url].attempts, 2);
  const held = recordDeliveryResult(retry.state, current, retry.urls, { status: 403 }, new Date(at.getTime() + 60_000));
  assert.equal(held.pending[url].held, "permanent_http_403");
  assert.equal(prepareDelivery(held, current, new Date(at.getTime() + 86_400_000)).urls.length, 0);
});

test("IndexNow validation responses are held as permanent failures", () => {
  const url = "https://the-mind.xyz/";
  const previous = manifest({ [url]: page("a") });
  const current = manifest({ [url]: page("b") }, "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee");
  for (const status of [400, 403, 422]) {
    const prepared = prepareDelivery(initialState(host, previous), current, at);
    const held = recordDeliveryResult(prepared.state, current, prepared.urls, { status }, at);
    assert.equal(held.pending[url].held, `permanent_http_${status}`);
    assert.equal(prepareDelivery(held, current, new Date(at.getTime() + 86_400_000)).urls.length, 0);
  }
});

test("a transport failure retains its in-flight URL for bounded retry", async () => {
  const url = "https://the-mind.xyz/";
  const previous = manifest({ [url]: page("a") });
  const current = manifest({ [url]: page("b") }, "dddddddddddddddddddddddddddddddddddddddd");
  const prepared = prepareDelivery(initialState(host, previous), current, at);
  const result = await submitPrepared({
    host,
    current,
    preparedState: prepared.state,
    urls: prepared.urls,
    fetchImpl: async () => { throw new Error("offline"); },
    now: at,
  });
  assert.equal(result.status, "pending");
  assert.match(result.error, /offline/u);
  assert.equal(result.state.pending[url].attempts, 1);
  assert.equal(result.state.pending[url].status, "pending");
  assert.equal(Date.parse(result.state.pending[url].nextAttemptAt), at.getTime() + 60_000);
});

test("a 429 Retry-After survives serialized state and excessive delays fail closed", () => {
  const url = "https://the-mind.xyz/";
  const previous = manifest({ [url]: page("a") });
  const current = manifest({ [url]: page("b") }, "cccccccccccccccccccccccccccccccccccccccc");
  const prepared = prepareDelivery(initialState(host, previous), current, at);
  const delayed = recordDeliveryResult(prepared.state, current, prepared.urls, { status: 429, retryAfter: "3600" }, at);
  const restored = JSON.parse(JSON.stringify(delayed));
  assert.equal(Date.parse(restored.pending[url].nextAttemptAt), at.getTime() + 3_600_000);
  assert.equal(prepareDelivery(restored, current, new Date(at.getTime() + 3_599_000)).urls.length, 0);
  const excessive = recordDeliveryResult(prepared.state, current, prepared.urls, { status: 429, retryAfter: "999999" }, at);
  assert.equal(excessive.pending[url].held, "retry_after_exceeds_7_days");
});
