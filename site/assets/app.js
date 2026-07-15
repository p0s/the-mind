/* Minimal client-side helpers:
 * - search across a prebuilt index
 * - toggle showing internal annotation tags
 *
 * No external deps; keeps the site static.
 */

async function loadSearchIndex(root) {
  const res = await fetch(root + "search_index.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`Search index request failed: ${res.status}`);
  return await res.json();
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

  const getSearchIndex = window.MindSearch.createCachedLoader(() => loadSearchIndex(root));
  let lastQ = "";
  let inputRevision = 0;

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

  input.addEventListener("input", async () => {
    const revision = ++inputRevision;
    let q = window.MindSearch.normalize(input.value);
    if (!q) {
      hide();
      lastQ = "";
      return;
    }

    try {
      const index = await getSearchIndex();
      q = window.MindSearch.normalize(input.value);
      if (revision !== inputRevision) return;
      if (!q) {
        hide();
        lastQ = "";
        return;
      }
      if (q === lastQ && !results.hidden) return;
      lastQ = q;
      const hits = window.MindSearch.rankSearchIndex(index || [], q);
      show();
      renderHits(results, hits);
    } catch (error) {
      q = window.MindSearch.normalize(input.value);
      if (revision !== inputRevision || !q) return;
      lastQ = "";
      show();
      results.innerHTML = '<div class="hit"><div class="hit__title">Search unavailable.</div></div>';
    }
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

function setupNavToggle() {
  const btn = document.getElementById("toggleNav");
  const nav = document.getElementById("siteNav");
  if (!btn || !nav) return;

  function setOpen(open) {
    document.body.classList.toggle("nav-open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    btn.title = open ? "Close menu" : "Open menu";
  }

  setOpen(false);

  btn.addEventListener("click", () => {
    const open = !document.body.classList.contains("nav-open");
    setOpen(open);
  });

  nav.addEventListener("click", (ev) => {
    if (ev.defaultPrevented) return;
    const t = ev.target;
    if (t && t.closest && t.closest("a")) {
      setOpen(false);
    }
  });

  const mq = window.matchMedia ? window.matchMedia("(max-width: 920px)") : null;
  if (mq) {
    const onChange = (ev) => {
      if (!ev.matches) setOpen(false);
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") setOpen(false);
  });
}

function setupLinkedNavSummaries() {
  const pageId = String(window.__PAGE_ID__ || "");
  const isQuestionsPage = pageId === "questions" || pageId.startsWith("questions-");

  document.querySelectorAll(".navsummary--linked > a").forEach((link) => {
    link.addEventListener("click", (ev) => {
      if (ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;

      const details = link.closest("details");
      if (!details) return;

      if (details.open) {
        ev.preventDefault();
        details.open = false;
        return;
      }

      if (isQuestionsPage) {
        ev.preventDefault();
        details.open = true;
      }
    });
  });
}

function setupDesktopNavDefaults() {
  const questions = document.querySelector(".navsummary--linked");
  const details = questions ? questions.closest("details") : null;
  if (!details) return;

  const mq = window.matchMedia ? window.matchMedia("(min-width: 921px)") : null;
  if (!mq) return;

  function sync(open) {
    if (open) details.open = true;
  }

  sync(mq.matches);

  const onChange = (ev) => {
    sync(ev.matches);
  };

  if (mq.addEventListener) mq.addEventListener("change", onChange);
  else if (mq.addListener) mq.addListener(onChange);
}

function setupChooserCards() {
  const cards = document.querySelectorAll("#choose-your-next-step + ul li");
  cards.forEach((card) => {
    const link = card.querySelector("a");
    if (!link) return;

    card.addEventListener("click", (ev) => {
      const target = ev.target;
      if (target && target.closest && target.closest("a")) return;
      const href = link.getAttribute("href");
      if (!href) return;
      window.location.href = href;
    });
  });
}

function setupNavMetrics() {
  const topbar = document.querySelector(".topbar");
  if (!topbar) return;

  function sync() {
    const height = Math.max(56, Math.ceil(topbar.getBoundingClientRect().height));
    document.documentElement.style.setProperty("--topbar-h", `${height}px`);
  }

  sync();
  window.addEventListener("resize", sync, { passive: true });
  window.addEventListener("orientationchange", sync, { passive: true });
  window.addEventListener("load", sync, { passive: true });
}

const ROOT = window.__SITE_ROOT__ || "./";
setupNavMetrics();
setupNavToggle();
setupLinkedNavSummaries();
setupDesktopNavDefaults();
setupChooserCards();
setupSearch(ROOT);
setupTagToggle();
setupThemeToggle();
