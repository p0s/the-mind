import { createHash } from "node:crypto";
import { link, lstat, mkdir, readFile, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";

export const INDEXNOW_ENDPOINT = "https://www.bing.com/indexnow";
export const RELEASE_PATH = "/.well-known/indexnow-release.json";
export const MAX_URLS_PER_REQUEST = 10_000;
export const MAX_DELIVERY_ATTEMPTS = 3;
export const MAX_RETRY_AFTER_MS = 7 * 24 * 60 * 60 * 1_000;
export const MAX_BACKOFF_MS = 24 * 60 * 60 * 1_000;

export const SITES = Object.freeze({
  "the-mind.xyz": Object.freeze({
    baselineSha: "cf581a3a991229139f9fd60d3a8ee9605a137f05",
    keyFile: "798d36a12f68186b6de12145d4719caf.txt",
    projectName: "Workers Builds: the-mind-edge",
    artifactSlug: "the-mind-xyz",
    sitemapUrl: "https://the-mind.xyz/sitemap.xml",
  }),
});

const MAX_SITEMAPS = 64;
const MAX_PAGES = 20_000;
const PRIVATE_PATH_SEGMENTS = new Set([
  "admin",
  "api",
  "draft",
  "internal",
  "login",
  "logout",
  "private",
  "preview",
  "settings",
]);

function requireSite(host) {
  const site = SITES[host];
  if (!site) throw new Error(`Unsupported IndexNow host: ${host}`);
  return site;
}

function decodeXml(value) {
  return value.replace(/&(#x[\da-f]+|#\d+|amp|apos|gt|lt|quot);/giu, (_match, entity) => {
    const normalized = entity.toLowerCase();
    if (normalized === "amp") return "&";
    if (normalized === "apos") return "'";
    if (normalized === "gt") return ">";
    if (normalized === "lt") return "<";
    if (normalized === "quot") return '"';
    if (normalized.startsWith("#x")) return String.fromCodePoint(Number.parseInt(normalized.slice(2), 16));
    return String.fromCodePoint(Number.parseInt(normalized.slice(1), 10));
  });
}

function textElement(block, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
  const match = block.match(new RegExp(`<(?:(?:[\\w.-]+):)?${escaped}\\b[^>]*>([\\s\\S]*?)<\\/(?:(?:[\\w.-]+):)?${escaped}\\s*>`, "iu"));
  return match ? decodeXml(match[1].trim()) : "";
}

export function parseSitemap(xml) {
  const root = xml.match(/<(?:(?:[\w.-]+):)?(urlset|sitemapindex)\b/iu)?.[1]?.toLowerCase();
  if (!root) throw new Error("Sitemap has no urlset or sitemapindex root");
  const recordName = root === "urlset" ? "url" : "sitemap";
  const escaped = recordName.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
  const recordPattern = new RegExp(`<(?:(?:[\\w.-]+):)?${escaped}\\b[^>]*>([\\s\\S]*?)<\\/(?:(?:[\\w.-]+):)?${escaped}\\s*>`, "giu");
  const records = [...xml.matchAll(recordPattern)].map((match) => ({
    loc: textElement(match[1], "loc"),
    lastmod: textElement(match[1], "lastmod") || null,
  }));
  if (!records.length || records.some((record) => !record.loc)) {
    throw new Error("Sitemap must contain at least one complete location record");
  }
  return { kind: root, records };
}

export function canonicalPageUrl(value, host) {
  requireSite(host);
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`Invalid sitemap URL for ${host}`);
  }
  if (
    url.protocol !== "https:" ||
    url.hostname.toLowerCase() !== host ||
    url.port !== "" ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new Error(`IndexNow URL must be a canonical HTTPS URL on ${host}`);
  }
  let decodedPath;
  try {
    decodedPath = decodeURIComponent(url.pathname);
  } catch {
    throw new Error(`IndexNow URL has an invalid path on ${host}`);
  }
  const segments = decodedPath.split("/").filter(Boolean).map((part) => part.toLowerCase());
  if (segments.some((part) => PRIVATE_PATH_SEGMENTS.has(part) || part === ".well-known")) {
    throw new Error(`IndexNow sitemap contains a private or internal path on ${host}`);
  }
  return url.href;
}

function canonicalSitemapUrl(value, host) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`Invalid sitemap location for ${host}`);
  }
  if (
    url.protocol !== "https:" ||
    url.hostname.toLowerCase() !== host ||
    url.port !== "" ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new Error(`Sitemap locations must remain on https://${host}`);
  }
  return url.href;
}

function sitemapFilePath(root, sitemapUrl, host) {
  const parsed = new URL(canonicalSitemapUrl(sitemapUrl, host));
  const relative = decodeURIComponent(parsed.pathname).replace(/^\/+/, "") || "sitemap.xml";
  const fullPath = path.resolve(root, relative);
  if (fullPath !== root && !fullPath.startsWith(`${root}${path.sep}`)) {
    throw new Error("Sitemap path escapes the build directory");
  }
  return fullPath;
}

async function regularFile(filePath, label) {
  const info = await lstat(filePath);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error(`${label} must be a regular file`);
  return readFile(filePath);
}

function htmlAttributes(tag) {
  const body = tag.replace(/^<[\w:-]+/u, "").replace(/\s*\/?\s*>$/u, "");
  const attributes = new Map();
  const pattern = /([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/gu;
  for (const match of body.matchAll(pattern)) {
    attributes.set(match[1].toLowerCase(), match[2] ?? match[3] ?? match[4] ?? "");
  }
  return attributes;
}

function localAssetReferences(html, pageUrl) {
  const references = [];
  const tags = [...html.matchAll(/<(script|img|source|video|audio|link)\b[^>]*>/giu)];
  for (const [tag] of tags) {
    const name = tag.match(/^<(\w+)/u)?.[1]?.toLowerCase();
    const attrs = htmlAttributes(tag);
    const values = [];
    if (name === "script" || name === "img" || name === "source" || name === "audio" || name === "track") values.push(attrs.get("src"));
    if (name === "video") values.push(attrs.get("src"), attrs.get("poster"));
    if (name === "link") {
      const rel = (attrs.get("rel") || "").toLowerCase().split(/\s+/u);
      if (rel.some((value) => ["stylesheet", "icon", "manifest", "preload", "modulepreload"].includes(value))) values.push(attrs.get("href"));
    }
    if (name === "img" || name === "source") {
      for (const candidate of (attrs.get("srcset") || "").split(",")) values.push(candidate.trim().split(/\s+/u)[0]);
    }
    for (const value of values) {
      if (!value || value.startsWith("data:") || value.startsWith("blob:")) continue;
      let parsed;
      try { parsed = new URL(value, pageUrl); } catch { throw new Error(`Invalid asset URL in ${pageUrl}`); }
      if (parsed.origin === new URL(pageUrl).origin && parsed.protocol === "https:") references.push(parsed.href);
    }
  }
  const metadataAssets = new Set(["og:image", "og:image:url", "og:video", "og:audio", "twitter:image", "twitter:image:src"]);
  for (const [tag] of html.matchAll(/<meta\b[^>]*>/giu)) {
    const attrs = htmlAttributes(tag);
    const name = (attrs.get("property") || attrs.get("name") || "").toLowerCase();
    if (metadataAssets.has(name) && attrs.get("content")) references.push(attrs.get("content"));
  }
  return [...new Set(references)].sort();
}

function cssAssetReferences(css, baseUrl) {
  const references = [];
  const pattern = /(?:url\(\s*|@import\s+(?:url\()?\s*)(?:["']?)([^"')\s;]+)(?:["']?)/giu;
  for (const [, value] of css.matchAll(pattern)) {
    if (value.startsWith("data:") || value.startsWith("blob:")) continue;
    let parsed;
    try { parsed = new URL(value, baseUrl); } catch { throw new Error(`Invalid CSS asset URL in ${baseUrl}`); }
    if (parsed.origin === new URL(baseUrl).origin && parsed.protocol === "https:") references.push(parsed.href);
  }
  return [...new Set(references)].sort();
}

function jsAssetReferences(source, baseUrl) {
  const references = [];
  const pattern = /\b(?:import|export)\s+(?:[^"'()]*?\s+from\s*)?["']([^"']+)["']|\bimport\(\s*["']([^"']+)["']\s*\)/gu;
  for (const match of source.matchAll(pattern)) {
    const value = match[1] || match[2];
    if (!value.startsWith("/") && !value.startsWith("./") && !value.startsWith("../")) continue;
    let parsed;
    try { parsed = new URL(value, baseUrl); } catch { throw new Error(`Invalid JavaScript dependency URL in ${baseUrl}`); }
    if (parsed.origin === new URL(baseUrl).origin && parsed.protocol === "https:") references.push(parsed.href);
  }
  return [...new Set(references)].sort();
}

function localAssetPath(root, assetUrl) {
  const url = new URL(assetUrl);
  let relative;
  try { relative = decodeURIComponent(url.pathname).replace(/^\/+/, ""); }
  catch { throw new Error(`Cannot map asset URL to a build file: ${assetUrl}`); }
  const fullPath = path.resolve(root, relative);
  if (fullPath === root || !fullPath.startsWith(`${root}${path.sep}`)) throw new Error(`Asset URL escapes the build directory: ${assetUrl}`);
  return fullPath;
}

async function assetFingerprints(root, pageUrl, references) {
  const found = new Map();
  const pending = [...references];
  while (pending.length) {
    const assetUrl = pending.shift();
    if (found.has(assetUrl)) continue;
    if (found.size >= 256) throw new Error(`Page references more than 256 local assets: ${pageUrl}`);
    const filePath = localAssetPath(root, assetUrl);
    let bytes;
    try { bytes = await regularFile(filePath, `Referenced asset ${assetUrl}`); }
    catch (error) {
      if (error.code === "ENOENT") throw new Error(`Referenced asset is missing: ${assetUrl}`);
      throw error;
    }
    const digest = createHash("sha256").update(bytes).digest("hex");
    found.set(assetUrl, digest);
    if (new URL(assetUrl).pathname.toLowerCase().endsWith(".css")) {
      pending.push(...cssAssetReferences(bytes.toString("utf8"), assetUrl));
    }
    if (/\.(?:m?js)$/iu.test(new URL(assetUrl).pathname)) {
      pending.push(...jsAssetReferences(bytes.toString("utf8"), assetUrl));
    }
  }
  return [...found.entries()].sort(([left], [right]) => left.localeCompare(right));
}

async function readLocalSitemaps(root, host) {
  const queue = [`https://${host}/sitemap.xml`];
  const seen = new Set();
  const pages = new Map();
  while (queue.length) {
    const sitemapUrl = queue.shift();
    if (seen.has(sitemapUrl)) throw new Error(`Sitemap repeats or cycles through ${sitemapUrl}`);
    seen.add(sitemapUrl);
    if (seen.size > MAX_SITEMAPS) throw new Error(`Sitemap exceeds the ${MAX_SITEMAPS}-file limit`);
    const filePath = sitemapFilePath(root, sitemapUrl, host);
    const xml = (await regularFile(filePath, `Sitemap ${sitemapUrl}`)).toString("utf8");
    const parsed = parseSitemap(xml);
    for (const record of parsed.records) {
      const location = canonicalSitemapUrl(record.loc, host);
      if (parsed.kind === "sitemapindex") {
        queue.push(location);
        continue;
      }
      const pageUrl = canonicalPageUrl(location, host);
      if (pages.has(pageUrl)) throw new Error(`Sitemap repeats page URL ${pageUrl}`);
      pages.set(pageUrl, record.lastmod);
      if (pages.size > MAX_PAGES) throw new Error(`Sitemap exceeds the ${MAX_PAGES}-page limit`);
    }
  }
  return pages;
}

function pageFilePath(root, pageUrl) {
  const url = new URL(pageUrl);
  let relative;
  try {
    relative = decodeURIComponent(url.pathname).replace(/^\/+/, "");
  } catch {
    throw new Error(`Cannot map sitemap URL to a build file: ${pageUrl}`);
  }
  if (!relative) relative = "index.html";
  else if (relative.endsWith("/")) relative = path.join(relative, "index.html");
  const fullPath = path.resolve(root, relative);
  if (fullPath !== root && !fullPath.startsWith(`${root}${path.sep}`)) {
    throw new Error(`Page URL escapes the build directory: ${pageUrl}`);
  }
  return fullPath;
}

export function revisionFor(host, sourceSha) {
  requireSite(host);
  if (!/^[a-f0-9]{40}$/u.test(sourceSha)) throw new Error("IndexNow source SHA must be a full lowercase commit SHA");
  return createHash("sha256").update(`indexnow-release-v1\0${host}\0${sourceSha}`).digest("hex");
}

export async function writeReleaseIdentity({ host, directory, sourceSha, replaceExisting = false }) {
  const site = requireSite(host);
  const key = site.keyFile.slice(0, -4);
  if (!/^[a-f0-9]{32}$/u.test(key)) throw new Error(`Invalid configured IndexNow key for ${host}`);
  const outputRoot = path.resolve(directory);
  const outputInfo = await lstat(outputRoot);
  if (!outputInfo.isDirectory() || outputInfo.isSymbolicLink()) throw new Error("IndexNow output must be a regular directory");
  if ((await regularFile(path.join(outputRoot, site.keyFile), `IndexNow key for ${host}`)).toString("utf8") !== `${key}\n`) {
    throw new Error(`Built IndexNow key file does not match the configured host key for ${host}`);
  }
  const target = path.join(outputRoot, RELEASE_PATH.slice(1));
  await mkdir(path.dirname(target), { recursive: true });
  const parentInfo = await lstat(path.dirname(target));
  if (!parentInfo.isDirectory() || parentInfo.isSymbolicLink()) throw new Error("IndexNow release directory must be a regular directory");
  let existingTarget = false;
  try {
    const targetInfo = await lstat(target);
    if (!replaceExisting) throw new Error(`Refusing to overwrite an existing release identity at ${target}`);
    if (!targetInfo.isFile() || targetInfo.isSymbolicLink()) throw new Error("Existing IndexNow release identity must be a regular file");
    existingTarget = true;
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  const payload = `${JSON.stringify({ version: 1, host, revision: revisionFor(host, sourceSha) }, null, 2)}\n`;

  const temporary = `${target}.${process.pid}.tmp`;
  await writeFile(temporary, payload, { flag: "wx", mode: 0o644 });
  try {
    if (existingTarget) await rename(temporary, target);
    else {
      await link(temporary, target);
      await unlink(temporary);
    }
  } catch (error) {
    await unlink(temporary).catch(() => {});
    if (error.code === "EEXIST" && !replaceExisting) throw new Error(`Refusing to overwrite an existing release identity at ${target}`);
    throw error;
  }
  return target;
}

export async function buildLocalManifest({ host, directory, sourceSha }) {
  const site = requireSite(host);
  const root = path.resolve(directory);
  const key = site.keyFile.slice(0, -4);
  if ((await regularFile(path.join(root, site.keyFile), `IndexNow key for ${host}`)).toString("utf8") !== `${key}\n`) {
    throw new Error(`Built IndexNow key file does not match the configured host key for ${host}`);
  }
  const sitemapPages = await readLocalSitemaps(root, host);
  const pages = {};
  for (const [url] of [...sitemapPages.entries()].sort(([left], [right]) => left.localeCompare(right))) {
    const bytes = await regularFile(pageFilePath(root, url), `Sitemap page ${url}`);
    const assets = await assetFingerprints(root, url, localAssetReferences(bytes.toString("utf8"), url));
    const digest = createHash("sha256").update(bytes).update("\0").update(JSON.stringify(assets)).digest("hex");
    pages[url] = { digest };
  }
  return { host, sourceSha, revision: revisionFor(host, sourceSha), key, keyFile: site.keyFile, pages };
}

export function compareManifests(previous, current) {
  if (!previous || !current || previous.host !== current.host) {
    throw new Error("IndexNow manifests must use the same host");
  }
  const oldPages = previous.pages || {};
  const newPages = current.pages || {};
  const added = [];
  const changed = [];
  const deleted = [];
  for (const [url, value] of Object.entries(newPages)) {
    if (!Object.hasOwn(oldPages, url)) added.push(url);
    else if (oldPages[url].digest !== value.digest) changed.push(url);
  }
  for (const url of Object.keys(oldPages)) {
    if (!Object.hasOwn(newPages, url)) deleted.push(url);
  }
  added.sort();
  changed.sort();
  deleted.sort();
  return { added, changed, deleted, urls: [...new Set([...added, ...changed, ...deleted])].sort() };
}

async function request(fetchImpl, url, init, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetchImpl(url, { redirect: "error", ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function readLiveSitemap({ host, fetchImpl, timeoutMs }) {
  const queue = [`https://${host}/sitemap.xml`];
  const seen = new Set();
  const pages = new Set();
  while (queue.length) {
    const sitemapUrl = queue.shift();
    if (seen.has(sitemapUrl)) throw new Error(`Live sitemap repeats or cycles through ${sitemapUrl}`);
    seen.add(sitemapUrl);
    if (seen.size > MAX_SITEMAPS) throw new Error(`Live sitemap exceeds the ${MAX_SITEMAPS}-file limit`);
    const response = await request(fetchImpl, sitemapUrl, { headers: { Accept: "application/xml,text/xml" }, cache: "no-store" }, timeoutMs);
    if (!response.ok) throw new Error(`Live sitemap returned HTTP ${response.status}`);
    const parsed = parseSitemap(await response.text());
    for (const record of parsed.records) {
      const location = canonicalSitemapUrl(record.loc, host);
      if (parsed.kind === "sitemapindex") queue.push(location);
      else {
        const pageUrl = canonicalPageUrl(location, host);
        if (pages.has(pageUrl)) throw new Error(`Live sitemap repeats page URL ${pageUrl}`);
        pages.add(pageUrl);
        if (pages.size > MAX_PAGES) throw new Error(`Live sitemap exceeds the ${MAX_PAGES}-page limit`);
      }
    }
  }
  return pages;
}

function validateManifest(host, manifest) {
  const site = requireSite(host);
  if (!manifest || manifest.host !== host || manifest.key !== site.keyFile.slice(0, -4) || manifest.keyFile !== site.keyFile) {
    throw new Error(`IndexNow manifest host or key does not match ${host}`);
  }
  if (!/^[a-f0-9]{40}$/u.test(manifest.sourceSha) || manifest.revision !== revisionFor(host, manifest.sourceSha)) {
    throw new Error(`IndexNow manifest release identity is invalid for ${host}`);
  }
  if (!manifest.pages || typeof manifest.pages !== "object" || Array.isArray(manifest.pages)) throw new Error("IndexNow manifest pages must be an object");
  for (const [url, value] of Object.entries(manifest.pages)) {
    canonicalPageUrl(url, host);
    if (!value || !/^[a-f0-9]{64}$/u.test(value.digest)) throw new Error(`Invalid page fingerprint for ${url}`);
  }
}

export function initialState(host, baseline) {
  validateManifest(host, baseline);
  return {
    version: 1,
    host,
    initialized: true,
    acceptedPages: structuredClone(baseline.pages),
    pending: {},
    receipts: [],
    lastAcceptedSourceSha: baseline.sourceSha,
    updatedAt: null,
  };
}

function validateState(host, state) {
  if (!state || state.version !== 1 || state.host !== host || state.initialized !== true) {
    throw new Error(`IndexNow delivery state is missing or belongs to another host: ${host}`);
  }
  if (!state.acceptedPages || typeof state.acceptedPages !== "object" || Array.isArray(state.acceptedPages)) throw new Error("IndexNow accepted-page state is invalid");
  if (!state.pending || typeof state.pending !== "object" || Array.isArray(state.pending)) throw new Error("IndexNow pending state is invalid");
  for (const [url, value] of Object.entries(state.acceptedPages)) {
    canonicalPageUrl(url, host);
    if (!value || !/^[a-f0-9]{64}$/u.test(value.digest)) throw new Error(`Invalid accepted-page fingerprint for ${url}`);
  }
  for (const [url, entry] of Object.entries(state.pending)) {
    canonicalPageUrl(url, host);
    if (!entry || !Number.isInteger(entry.attempts) || entry.attempts < 0 || entry.attempts > MAX_DELIVERY_ATTEMPTS) {
      throw new Error(`Invalid pending-attempt count for ${url}`);
    }
    if (!["pending", "in_flight", "held"].includes(entry.status)) throw new Error(`Invalid pending state for ${url}`);
    if (entry.nextAttemptAt && !Number.isFinite(Date.parse(entry.nextAttemptAt))) throw new Error(`Invalid retry time for ${url}`);
    if (entry.status === "in_flight" && !Number.isFinite(Date.parse(entry.lastAttemptAt))) throw new Error(`Missing in-flight timestamp for ${url}`);
  }
}

function needsDelivery(acceptedPages, currentPages, url) {
  const accepted = acceptedPages[url]?.digest;
  const current = currentPages[url]?.digest;
  return accepted !== current;
}

export function compareState(state, current) {
  validateState(current.host, state);
  validateManifest(current.host, current);
  const added = [];
  const changed = [];
  const deleted = [];
  for (const [url, value] of Object.entries(current.pages)) {
    if (!Object.hasOwn(state.acceptedPages, url)) added.push(url);
    else if (state.acceptedPages[url].digest !== value.digest) changed.push(url);
  }
  for (const url of Object.keys(state.acceptedPages)) if (!Object.hasOwn(current.pages, url)) deleted.push(url);
  added.sort(); changed.sort(); deleted.sort();
  return { added, changed, deleted, urls: [...new Set([...added, ...changed, ...deleted])].sort() };
}

export function prepareDelivery(stateInput, current, now = new Date()) {
  validateManifest(current.host, current);
  validateState(current.host, stateInput);
  const state = structuredClone(stateInput);
  const delta = compareState(state, current);
  const candidates = new Set([...delta.urls, ...Object.keys(state.pending)]);
  for (const url of candidates) {
    canonicalPageUrl(url, current.host);
    if (!needsDelivery(state.acceptedPages, current.pages, url)) {
      delete state.pending[url];
      continue;
    }
    state.pending[url] ||= { attempts: 0, status: "pending", nextAttemptAt: null, held: null };
    const entry = state.pending[url];
    if (entry.status === "in_flight") {
      entry.status = "pending";
      entry.nextAttemptAt ||= backoffDate(entry.attempts, new Date(entry.lastAttemptAt || now.toISOString())).toISOString();
    }
    if (entry.attempts >= MAX_DELIVERY_ATTEMPTS && !entry.held) {
      entry.held = "attempts_exhausted";
      entry.status = "held";
    }
  }
  const nowMs = now.getTime();
  const eligible = Object.entries(state.pending)
    .filter(([, entry]) => !entry.held && entry.attempts < MAX_DELIVERY_ATTEMPTS && (!entry.nextAttemptAt || Date.parse(entry.nextAttemptAt) <= nowMs))
    .map(([url]) => url)
    .sort()
    .slice(0, MAX_URLS_PER_REQUEST);
  for (const url of eligible) {
    const entry = state.pending[url];
    entry.attempts += 1;
    entry.status = "in_flight";
    entry.lastAttemptAt = now.toISOString();
    entry.nextAttemptAt = null;
  }
  state.updatedAt = now.toISOString();
  return { state, urls: eligible, delta, status: eligible.length ? "ready" : (Object.keys(state.pending).length ? "pending" : "no_changes") };
}

function retryAfterDate(value, now) {
  if (!value) return null;
  const seconds = Number(value.trim());
  if (Number.isFinite(seconds) && seconds >= 0) return new Date(now.getTime() + seconds * 1_000);
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(Math.max(parsed, now.getTime())) : null;
}

function backoffDate(attempt, now) {
  const seconds = Math.min(60 * (2 ** Math.max(0, attempt - 1)), MAX_BACKOFF_MS / 1_000);
  return new Date(now.getTime() + seconds * 1_000);
}

export function recordDeliveryResult(stateInput, current, urls, { status, retryAfter, error } = {}, now = new Date()) {
  validateManifest(current.host, current);
  validateState(current.host, stateInput);
  const state = structuredClone(stateInput);
  for (const url of urls) {
    canonicalPageUrl(url, current.host);
    const entry = state.pending[url];
    if (!entry || entry.status !== "in_flight") throw new Error(`No persisted in-flight attempt exists for ${url}`);
    if (status === 200 || status === 202) {
      if (current.pages[url]) state.acceptedPages[url] = structuredClone(current.pages[url]);
      else delete state.acceptedPages[url];
      delete state.pending[url];
      continue;
    }
    entry.status = "pending";
    entry.lastError = error || (status ? `http_${status}` : "network_error");
    if (status === 429) {
      const requested = retryAfterDate(retryAfter, now) || backoffDate(entry.attempts, now);
      if (requested.getTime() - now.getTime() > MAX_RETRY_AFTER_MS) {
        entry.held = "retry_after_exceeds_7_days";
        entry.status = "held";
      } else entry.nextAttemptAt = requested.toISOString();
    } else if (Number.isInteger(status) && status >= 400 && status < 500) {
      entry.held = `permanent_http_${status}`;
      entry.status = "held";
    } else if (entry.attempts >= MAX_DELIVERY_ATTEMPTS) {
      entry.held = "attempts_exhausted";
      entry.status = "held";
    } else entry.nextAttemptAt = backoffDate(entry.attempts, now).toISOString();
  }
  if (status === 200 || status === 202) {
    const digest = createHash("sha256").update([...urls].sort().join("\n")).digest("hex");
    state.receipts = [...(state.receipts || []), {
      at: now.toISOString(),
      sourceSha: current.sourceSha,
      httpStatus: status,
      state: status === 202 ? "received_key_validation_pending" : "received",
      urlCount: urls.length,
      urlsDigest: digest,
    }].slice(-20);
    state.lastAcceptedSourceSha = current.sourceSha;
  }
  state.updatedAt = now.toISOString();
  return state;
}

export async function verifyLivePublication({ host, current, state, fetchImpl = fetch, timeoutMs = 8_000 }) {
  const site = requireSite(host);
  validateManifest(host, current);
  validateState(host, state);
  const releaseUrl = `https://${host}${RELEASE_PATH}`;
  const keyUrl = `https://${host}/${site.keyFile}`;
  const [releaseResponse, keyResponse] = await Promise.all([
    request(fetchImpl, releaseUrl, { cache: "no-store" }, timeoutMs),
    request(fetchImpl, keyUrl, { cache: "no-store" }, timeoutMs),
  ]);
  if (!releaseResponse.ok) throw new Error(`Live release identity returned HTTP ${releaseResponse.status}`);
  const release = await releaseResponse.json();
  if (release.version !== 1 || release.host !== host || release.revision !== current.revision) throw new Error(`Live production release does not match ${current.sourceSha}`);
  if (!keyResponse.ok || (await keyResponse.text()) !== `${current.key}\n`) throw new Error(`Live IndexNow key does not match ${host}`);
  const livePages = await readLiveSitemap({ host, fetchImpl, timeoutMs });
  const expectedPages = new Set(Object.keys(current.pages));
  if (livePages.size !== expectedPages.size || [...livePages].some((url) => !expectedPages.has(url))) {
    throw new Error(`Live sitemap does not match the successful ${host} build`);
  }
  const pendingUnion = new Set([...Object.keys(state.pending), ...compareState(state, current).urls]);
  for (const url of pendingUnion) {
    canonicalPageUrl(url, host);
    if (livePages.has(url) !== Object.hasOwn(current.pages, url)) throw new Error(`Live sitemap membership does not match the retained delta for ${url}`);
  }
}

export async function submitPrepared({ host, current, preparedState, urls, fetchImpl = fetch, timeoutMs = 8_000, now = new Date() }) {
  const site = requireSite(host);
  validateManifest(host, current);
  validateState(host, preparedState);
  if (!urls.length) return { state: preparedState, status: "no_changes", httpStatus: null };
  if (urls.length > MAX_URLS_PER_REQUEST) throw new Error(`IndexNow requests are limited to ${MAX_URLS_PER_REQUEST} URLs`);
  if (current.keyFile !== site.keyFile || current.key !== site.keyFile.slice(0, -4)) throw new Error(`IndexNow build used the wrong host key for ${host}`);
  for (const url of urls) {
    canonicalPageUrl(url, host);
    if (preparedState.pending[url]?.status !== "in_flight") throw new Error(`IndexNow URL was not persisted in-flight before sending: ${url}`);
  }
  let response;
  let requestError;
  try {
    response = await request(fetchImpl, INDEXNOW_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ host, key: current.key, keyLocation: `https://${host}/${current.keyFile}`, urlList: urls }),
    }, timeoutMs);
  } catch (error) {
    requestError = error;
  }
  const status = response?.status;
  const accepted = status === 200 || status === 202;
  const state = recordDeliveryResult(preparedState, current, urls, {
    status,
    retryAfter: response?.headers?.get?.("retry-after"),
    error: requestError?.message,
  }, now);
  return {
    state,
    status: accepted ? (status === 202 ? "received_key_validation_pending" : "received") : "pending",
    httpStatus: status || null,
    error: requestError?.message || (accepted ? null : `IndexNow returned HTTP ${status || "network error"}`),
  };
}
