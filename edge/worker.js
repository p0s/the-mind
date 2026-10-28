import { deliver, SIGNALS, stageBody } from "./ingest-client.mjs";

const SITE_HOSTNAME = "the-mind.xyz";
const WWW_HOSTNAME = "www.the-mind.xyz";
const INDEXNOW_RELEASE_PATH = "/.well-known/indexnow-release.json";
const OPT_OUT_COOKIE = "p0s_analytics_optout";
const MAX_USER_AGENT = 512;
const MAX_PATH = 500;
const MAX_REFERRER = 255;

const BOT_PATTERN =
  /bot|crawler|spider|slurp|headless|lighthouse|pagespeed|facebookexternalhit|pingdom|uptimerobot|curl|wget|python-requests|postmanruntime/i;

function requestOrigin(request) {
  return new URL(request.url).origin;
}

function isSameOriginPost(request) {
  const origin = request.headers.get("Origin");
  if (origin) return origin === requestOrigin(request);
  const referrer = request.headers.get("Referer");
  if (!referrer) return false;
  try {
    return new URL(referrer).origin === requestOrigin(request);
  } catch {
    return false;
  }
}

function responseHeaders() {
  return {
    "Cache-Control": "no-store",
    "Content-Type": "text/html; charset=UTF-8",
    "Referrer-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
  };
}

function canonicalRedirect(request) {
  const target = new URL(request.url);
  target.hostname = SITE_HOSTNAME;
  const status = request.method === "GET" || request.method === "HEAD" ? 301 : 308;
  return new Response(null, {
    status,
    headers: {
      ...responseHeaders(),
      "Cache-Control": "public, max-age=300",
      Location: target.toString(),
    },
  });
}

function preferencePage(action, title, description) {
  return `<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${title}</title></head>
  <body>
    <main>
      <h1>${title}</h1>
      <p>${description}</p>
      <form method="post" action="${action}">
        <button type="submit">Confirm</button>
      </form>
      <p><a href="/privacy/">Back to website privacy</a></p>
    </main>
  </body>
</html>`;
}

function preferenceResponse(request, mode) {
  const action = mode === "opt-out" ? "/analytics/opt-out" : "/analytics/opt-in";
  const title = mode === "opt-out" ? "Opt out of website request counting" : "Opt in to website request counting";
  const description = mode === "opt-out"
    ? "Confirm to set a host-only preference cookie. Do Not Track and Global Privacy Control are always honored too."
    : "Confirm to clear the host-only opt-out preference cookie. Do Not Track and Global Privacy Control remain honored.";

  if (request.method === "GET") {
    return new Response(preferencePage(action, title, description), { status: 200, headers: responseHeaders() });
  }
  if (request.method !== "POST") {
    return new Response("Method Not Allowed", {
      status: 405,
      headers: { ...responseHeaders(), Allow: "GET, POST" },
    });
  }
  if (!isSameOriginPost(request)) {
    return new Response("Forbidden", { status: 403, headers: responseHeaders() });
  }

  const headers = responseHeaders();
  if (mode === "opt-out") {
    headers["Set-Cookie"] = `${OPT_OUT_COOKIE}=1; Max-Age=31536000; Path=/; Secure; HttpOnly; SameSite=Lax`;
    return new Response(
      preferencePage("/analytics/opt-in", "Website request counting is off", "This host will skip eligible requests while the preference cookie remains set."),
      { status: 200, headers },
    );
  }

  headers["Set-Cookie"] = `${OPT_OUT_COOKIE}=; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/; Secure; HttpOnly; SameSite=Lax`;
  return new Response(
    preferencePage("/analytics/opt-out", "Website request counting is available", "Do Not Track and Global Privacy Control are still honored when present."),
    { status: 200, headers },
  );
}

function hasOptOutCookie(request) {
  return request.headers.get("Cookie")?.split(";").some((part) => part.trim() === `${OPT_OUT_COOKIE}=1`) === true;
}

function isOptedOut(request) {
  return request.headers.get("DNT") === "1" || request.headers.get("Sec-GPC") === "1" || hasOptOutCookie(request);
}

function isPrefetch(request) {
  return ["Purpose", "Sec-Purpose", "X-Moz", "X-Purpose"].some((name) =>
    /prefetch|prerender/i.test(request.headers.get(name) || ""),
  );
}

function isRecognizableBot(request) {
  return request.cf?.botManagement?.verifiedBot === true
    || BOT_PATTERN.test(request.headers.get("User-Agent") || "");
}

function trustedIp(request) {
  if (!request.cf) return "";
  const value = request.headers.get("CF-Connecting-IP") || "";
  if (!value || value.length > 64 || /[,\s]/.test(value)) return "";
  return value;
}

function country(request) {
  const value = String(request.cf?.country || "").toUpperCase();
  return /^[A-Z]{2}$/.test(value) && !["XX", "T1"].includes(value) ? value : "";
}

function referrerOrigin(request) {
  const value = request.headers.get("Referer") || "";
  if (!value || value.length > 2048) return "";
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return "";
    return parsed.origin.slice(0, MAX_REFERRER);
  } catch {
    return "";
  }
}

function eligiblePath(pathname) {
  if (pathname.length > MAX_PATH || pathname.includes("\u0000")) return false;
  if (!/^\/(?:[a-z0-9][a-z0-9_-]*\/)*$/i.test(pathname)) return false;
  if (pathname.split("/").some(segment => /^[a-f0-9]{32,}$/i.test(segment)
      || /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(segment))) return false;
  if (pathname !== "/" && (!pathname.endsWith("/") || /\.[^/]+\/$/.test(pathname))) return false;
  if (pathname.includes(".") || /(?:token|secret|password|auth|account|private|job|preview|login|logout|dashboard|settings|api|admin)/i.test(pathname)) return false;
  return true;
}

function eligibleResponse(request, response) {
  const url = new URL(request.url);
  if (url.hostname.toLowerCase() !== SITE_HOSTNAME || request.method !== "GET" || response.status !== 200) return false;
  if (!eligiblePath(url.pathname) || isOptedOut(request) || isPrefetch(request) || isRecognizableBot(request)) return false;
  if (/(?:^|[&;])(?:code|email|id|key|password|secret|session|token|user)=/i.test(url.search.slice(1))) return false;
  if (!/\btext\/html\b/i.test(response.headers.get("Content-Type") || "")) return false;
  return Boolean(trustedIp(request));
}

function payloadFor(request, path = new URL(request.url).pathname) {
  const url = new URL(request.url);
  const payload = {
    hostname: SITE_HOSTNAME,
    path,
    referrer: referrerOrigin(request),
    ip: trustedIp(request),
    userAgent: (request.headers.get("User-Agent") || "").slice(0, MAX_USER_AGENT),
  };
  const visitorCountry = country(request);
  if (visitorCountry) payload.country = visitorCountry;
  if (url.searchParams.get("measurement_qa") === "1") payload.qa = true;
  return payload;
}

function configured(env) {
  const url = String(env?.ANALYTICS_INGEST_URL || "");
  const token = String(env?.ANALYTICS_INGEST_TOKEN || "");
  try { if (new URL(url).protocol !== "https:" || !token) return null; }
  catch { return null; }
  return { url, token };
}

function collect(env, route, payload) {
  const target = configured(env);
  return target ? deliver(target.url, route, target.token, payload) : Promise.resolve();
}

function background(work, ctx) {
  if (typeof ctx?.waitUntil === "function") ctx.waitUntil(work);
  else void work;
}

async function emptyBody(request) {
  const length = request.headers.get("Content-Length");
  if (length !== null && (!/^\d+$/.test(length) || Number(length) !== 0)) return false;
  if (!request.body) return true;
  const reader = request.body.getReader();
  try {
    const { done } = await reader.read();
    if (!done) await reader.cancel();
    return done;
  } catch { return false; }
  finally { reader.releaseLock(); }
}

async function signalResponse(request, env, ctx) {
  const reply = (status = 204) => new Response(null, { status, headers: { "Cache-Control": "no-store" } });
  const url = new URL(request.url);
  if (url.search || url.protocol !== "https:" || url.port) return reply(404);
  if (request.method !== "POST") return reply(405);
  if (request.headers.get("Origin") !== url.origin
      || ![null, "same-origin"].includes(request.headers.get("Sec-Fetch-Site"))) return reply(403);
  if (isOptedOut(request) || isPrefetch(request) || isRecognizableBot(request)) return reply();
  const path = request.headers.get("X-Analytics-Path");
  const signal = request.headers.get("X-Analytics-Signal");
  if (!path || !path.startsWith("/") || !eligiblePath(path) || /[?#]/.test(path)
      || !trustedIp(request) || (signal !== "bootstrap" && !Object.hasOwn(SIGNALS, signal))
      || !await emptyBody(request)) return reply(400);
  const qa = request.headers.get("X-Measurement-QA") === "1";
  const payload = signal === "bootstrap" ? stageBody("bootstrap", { qa }) : payloadFor(request, path);
  if (signal !== "bootstrap") {
    payload.eventName = SIGNALS[signal];
    if (qa) payload.qa = true;
  }
  background(collect(env, signal === "bootstrap" ? "stage" : "page", payload), ctx);
  return reply();
}

function permissionResponse(response, allowed) {
  if (!/\btext\/html\b/i.test(response.headers.get("Content-Type") || "")) return response;
  const headers = new Headers(response.headers);
  headers.set("Cache-Control", "private, no-store");
  headers.delete("Content-Length");
  headers.delete("ETag");
  const rewritten = new Response(response.body, { status: response.status, statusText: response.statusText, headers });
  return new HTMLRewriter().on("body", { element(element) {
    element.setAttribute("data-site-measurement", allowed ? "allowed" : "denied");
  } }).transform(rewritten);
}

async function fetchAssets(request, env) {
  if (!env?.ASSETS || typeof env.ASSETS.fetch !== "function") {
    throw new Error("ASSETS binding is required");
  }
  return env.ASSETS.fetch(request);
}

async function handle(request, env, executionCtx) {
  const url = new URL(request.url);
  const hostname = url.hostname.toLowerCase();
  if (hostname === WWW_HOSTNAME) return canonicalRedirect(request);
  if (hostname !== SITE_HOSTNAME) return new Response("Not Found", { status: 404 });
  if (url.pathname === "/analytics/opt-out") return preferenceResponse(request, "opt-out");
  if (url.pathname === "/analytics/opt-in") return preferenceResponse(request, "opt-in");
  if (url.pathname === "/analytics/signal") return signalResponse(request, env, executionCtx);

  let response;
  try {
    response = await fetchAssets(request, env);
  } catch {
    return new Response("Site assets unavailable", { status: 503, headers: responseHeaders() });
  }
  if (url.pathname === INDEXNOW_RELEASE_PATH && response.ok) {
    const headers = new Headers(response.headers);
    headers.set("Cache-Control", "no-store");
    headers.set("X-Robots-Tag", "noindex");
    response = new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  }
  const allowed = Boolean(configured(env)) && eligibleResponse(request, response);
  if (allowed) background(collect(env, "page", payloadFor(request)), executionCtx);
  return permissionResponse(response, allowed);
}

export default { fetch: handle };
export {
  eligiblePath,
  eligibleResponse,
  fetchAssets,
  hasOptOutCookie,
  isOptedOut,
  isPrefetch,
  isRecognizableBot,
  canonicalRedirect,
  payloadFor,
};
