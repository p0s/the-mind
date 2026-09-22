const SITE_HOSTNAME = "the-mind.xyz";
const OPT_OUT_COOKIE = "p0s_analytics_optout";
const INGEST_TIMEOUT_MS = 1500;
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
  return BOT_PATTERN.test(request.headers.get("User-Agent") || "");
}

function trustedIp(request) {
  if (!request.cf) return "";
  const value = request.headers.get("CF-Connecting-IP") || "";
  if (!value || value.length > 64 || /[,\s]/.test(value)) return "";
  return value;
}

function country(request) {
  const value = String(request.cf?.country || "").toUpperCase();
  return /^[A-Z]{2}$/.test(value) ? value : "";
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
  if (pathname !== "/" && (!pathname.endsWith("/") || /\.[^/]+\/$/.test(pathname))) return false;
  if (pathname.includes(".") || /(?:token|secret|password|auth|account|private|job|preview|login|logout|dashboard|settings|api|admin)/i.test(pathname)) return false;
  return true;
}

function eligibleResponse(request, response) {
  const url = new URL(request.url);
  if (url.hostname.toLowerCase() !== SITE_HOSTNAME || request.method !== "GET" || response.status !== 200) return false;
  if (!eligiblePath(url.pathname) || isOptedOut(request) || isPrefetch(request) || isRecognizableBot(request)) return false;
  if (!/\btext\/html\b/i.test(response.headers.get("Content-Type") || "")) return false;
  return Boolean(trustedIp(request));
}

function payloadFor(request) {
  const url = new URL(request.url);
  const payload = {
    hostname: SITE_HOSTNAME,
    path: url.pathname,
    referrer: referrerOrigin(request),
    ip: trustedIp(request),
    userAgent: (request.headers.get("User-Agent") || "").slice(0, MAX_USER_AGENT),
  };
  const visitorCountry = country(request);
  if (visitorCountry) payload.country = visitorCountry;
  return payload;
}

async function ingest(request, env) {
  const url = String(env?.ANALYTICS_INGEST_URL || "");
  const token = String(env?.ANALYTICS_INGEST_TOKEN || "");
  if (!url || !token) return;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), INGEST_TIMEOUT_MS);
  try {
    await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payloadFor(request)),
      signal: controller.signal,
    });
  } catch {
    // Collection must never affect the document response and must not log
    // visitor details. There is intentionally no retry.
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchAssets(request, env) {
  if (!env?.ASSETS || typeof env.ASSETS.fetch !== "function") {
    throw new Error("ASSETS binding is required");
  }
  return env.ASSETS.fetch(request);
}

async function handle(request, env, executionCtx) {
  const url = new URL(request.url);
  if (url.hostname.toLowerCase() !== SITE_HOSTNAME) return new Response("Not Found", { status: 404 });
  if (url.pathname === "/analytics/opt-out") return preferenceResponse(request, "opt-out");
  if (url.pathname === "/analytics/opt-in") return preferenceResponse(request, "opt-in");

  let response;
  try {
    response = await fetchAssets(request, env);
  } catch {
    return new Response("Site assets unavailable", { status: 503, headers: responseHeaders() });
  }
  if (eligibleResponse(request, response)) {
    const work = ingest(request, env);
    if (executionCtx && typeof executionCtx.waitUntil === "function") executionCtx.waitUntil(work);
    else await work;
  }
  return response;
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
  payloadFor,
};
