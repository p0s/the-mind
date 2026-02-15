/* Minimal client-side helpers:
 * - search across a prebuilt index
 * - toggle showing internal annotation tags
 *
 * No external deps; keeps the site static.
 */

async function loadSearchIndex(root) {
  const res = await fetch(root + "search_index.json", { cache: "no-store" });
  if (!res.ok) return [];
  return await res.json();
}

function normalize(s) {
  return (s || "").toLowerCase().replace(/\s+/g, " ").trim();
}

function snippet(text, q) {
  const t = text || "";
  const i = t.toLowerCase().indexOf(q);
  if (i < 0) return t.slice(0, 140);
  const start = Math.max(0, i - 60);
  const end = Math.min(t.length, i + 120);
  return (start > 0 ? "…" : "") + t.slice(start, end) + (end < t.length ? "…" : "");
}

function renderHits(container, hits) {
  const root = window.__SITE_ROOT__ || "./";
  if (!hits.length) {
    container.innerHTML = '<div class="hit"><div class="hit__title">No results</div></div>';
    return;
  }
  container.innerHTML = hits
    .slice(0, 20)
    .map((h) => {
      const title = (h.title || "").replace(/</g, "&lt;");
      const snip = (h.snippet || "").replace(/</g, "&lt;");
      return (
        `<a class="hit" href="${root}${h.href}">` +
        `<div class="hit__title">${title}</div>` +
        `<div class="hit__snippet">${snip}</div>` +
        `</a>`
      );
    })
    .join("");
}

function setupSearch(root) {
  const input = document.getElementById("searchInput");
  const results = document.getElementById("searchResults");
  if (!input || !results) return;

  let index = null;
  let lastQ = "";

  function hide() {
    results.hidden = true;
  }

  function show() {
    results.hidden = false;
  }

  document.addEventListener("click", (ev) => {
    const t = ev.target;
    if (t === input || results.contains(t)) return;
    hide();
  });

  input.addEventListener("focus", async () => {
    if (!index) index = await loadSearchIndex(root);
  });

  input.addEventListener("input", async () => {
    const q = normalize(input.value);
    if (!index) index = await loadSearchIndex(root);
    if (!q) {
      hide();
      lastQ = "";
      return;
    }
    if (q === lastQ) return;
    lastQ = q;
    const hits = [];
    for (const item of index || []) {
      const hay = normalize(item.text);
      if (hay.includes(q) || normalize(item.title).includes(q)) {
        hits.push({
          href: item.href,
          title: item.title,
          snippet: snippet(item.text, q),
        });
      }
    }
    show();
    renderHits(results, hits);
  });

  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      input.value = "";
      hide();
      input.blur();
    }
  });
}

function setupTagToggle() {
  const btn = document.getElementById("toggleTags");
  if (!btn) return;
  btn.addEventListener("click", () => {
    document.body.classList.toggle("show-tags");
  });
}

function setupThemeToggle() {
  const btn = document.getElementById("toggleTheme");
  if (!btn) return;

  function getStoredTheme() {
    try {
      const t = localStorage.getItem("theme");
      if (t === "dark" || t === "light") return t;
    } catch (e) {}
    return null;
  }

  function setStoredTheme(theme) {
    try {
      localStorage.setItem("theme", theme);
    } catch (e) {}
  }

  function currentTheme() {
    return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  }

  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    const label = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
    btn.title = label;
    btn.setAttribute("aria-label", label);
  }

  apply(currentTheme());

  btn.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    setStoredTheme(next);
    apply(next);
  });

  const mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  if (mq && !getStoredTheme()) {
    const handler = (ev) => {
      apply(ev.matches ? "dark" : "light");
    };
    if (mq.addEventListener) mq.addEventListener("change", handler);
    else if (mq.addListener) mq.addListener(handler);
  }
}

const ROOT = window.__SITE_ROOT__ || "./";
setupSearch(ROOT);
setupTagToggle();
setupThemeToggle();
