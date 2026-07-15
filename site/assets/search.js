/* Pure search ranking helpers, shared by the browser and unit tests. */

const MindSearch = (() => {
  function normalize(s) {
    return (s || "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  function countOccurrences(hay, needle) {
    if (!hay || !needle) return 0;
    let n = 0;
    let i = 0;
    while (true) {
      const j = hay.indexOf(needle, i);
      if (j < 0) break;
      n += 1;
      i = j + Math.max(1, needle.length);
    }
    return n;
  }

  function snippet(text, q) {
    const t = text || "";
    const i = t.toLowerCase().indexOf(q);
    if (i < 0) return t.slice(0, 140);
    const start = Math.max(0, i - 60);
    const end = Math.min(t.length, i + 120);
    return (start > 0 ? "…" : "") + t.slice(start, end) + (end < t.length ? "…" : "");
  }

  function finitePriority(value) {
    const priority = Number(value);
    return Number.isFinite(priority) ? priority : 0;
  }

  function rankSearchIndex(index, query) {
    const q = normalize(query);
    if (!q) return [];

    const hits = [];
    for (const item of index || []) {
      const titleNorm = normalize(item.title);
      const textNorm = normalize(item.text);
      const inTitle = titleNorm.includes(q);
      const inText = textNorm.includes(q);
      if (!inTitle && !inText) continue;

      hits.push({
        href: item.href,
        title: item.title,
        snippet: snippet(item.text, q),
        search_priority: finitePriority(item.search_priority),
        score: (inTitle ? 100 : 0) + 10 * countOccurrences(titleNorm, q) + countOccurrences(textNorm, q),
      });
    }

    hits.sort(
      (a, b) =>
        b.search_priority - a.search_priority ||
        b.score - a.score ||
        String(a.title || "").localeCompare(String(b.title || "")) ||
        String(a.href || "").localeCompare(String(b.href || "")),
    );
    return hits;
  }

  return { normalize, rankSearchIndex };
})();

if (typeof window !== "undefined") window.MindSearch = MindSearch;
if (typeof module !== "undefined" && module.exports) module.exports = MindSearch;
