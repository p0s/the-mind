// Render a Mermaid diagram to SVG in Node (no browser, no external network).
//
// Usage:
//   cat diagram.mmd | node scripts/render_mermaid_svg.mjs > diagram.svg
//
// Notes:
// - This is used at build-time to keep the published site self-contained:
//   we do not ship Mermaid JS to the browser.
// - Requires npm deps: mermaid + jsdom (see package.json).

import { JSDOM } from "jsdom";

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
  });
}

function installDomGlobals(dom) {
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.HTMLElement = dom.window.HTMLElement;
  globalThis.SVGElement = dom.window.SVGElement;
  globalThis.Element = dom.window.Element;
  globalThis.DOMParser = dom.window.DOMParser;

  const parseNum = (v) => {
    const n = Number.parseFloat(String(v || "").trim());
    return Number.isFinite(n) ? n : null;
  };

  // Minimal SVG transform parsing. Mermaid heavily relies on translate()
  // transforms for layout. Support translate/scale/matrix and best-effort
  // rotate so getBBox() returns values in the parent's coordinate system.
  function parseTransformMatrix(transform) {
    const t = String(transform || "").trim();
    if (!t) return [1, 0, 0, 1, 0, 0]; // identity

    // Matrix form: [a,b,c,d,e,f] => x' = a*x + c*y + e, y' = b*x + d*y + f
    let m = [1, 0, 0, 1, 0, 0];

    const mul = (m1, m2) => {
      const [a1, b1, c1, d1, e1, f1] = m1;
      const [a2, b2, c2, d2, e2, f2] = m2;
      return [
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
      ];
    };

    const rx = /([a-zA-Z]+)\(([^)]*)\)/g;
    let match;
    while ((match = rx.exec(t))) {
      const name = match[1].toLowerCase();
      const args = match[2]
        .split(/[\s,]+/)
        .map((s) => s.trim())
        .filter(Boolean)
        .map(parseNum)
        .filter((n) => n !== null);

      if (name === "translate") {
        const tx = args[0] ?? 0;
        const ty = args[1] ?? 0;
        m = mul(m, [1, 0, 0, 1, tx, ty]);
        continue;
      }

      if (name === "scale") {
        const sx = args[0] ?? 1;
        const sy = args[1] ?? sx;
        m = mul(m, [sx, 0, 0, sy, 0, 0]);
        continue;
      }

      if (name === "matrix" && args.length >= 6) {
        m = mul(m, [args[0], args[1], args[2], args[3], args[4], args[5]]);
        continue;
      }

      if (name === "rotate" && args.length >= 1) {
        const ang = (args[0] * Math.PI) / 180;
        const cos = Math.cos(ang);
        const sin = Math.sin(ang);
        const cx = args[1] ?? 0;
        const cy = args[2] ?? 0;
        // rotate around (cx,cy): T(cx,cy) R T(-cx,-cy)
        m = mul(m, [1, 0, 0, 1, cx, cy]);
        m = mul(m, [cos, sin, -sin, cos, 0, 0]);
        m = mul(m, [1, 0, 0, 1, -cx, -cy]);
        continue;
      }
    }

    return m;
  }

  function applyMatrixToBBox(bbox, m) {
    const x = bbox.x ?? 0;
    const y = bbox.y ?? 0;
    const w = bbox.width ?? 0;
    const h = bbox.height ?? 0;
    const [a, b, c, d, e, f] = m;

    const pts = [
      [x, y],
      [x + w, y],
      [x, y + h],
      [x + w, y + h],
    ].map(([px, py]) => [a * px + c * py + e, b * px + d * py + f]);

    let minX = Infinity,
      minY = Infinity,
      maxX = -Infinity,
      maxY = -Infinity;
    for (const [px, py] of pts) {
      if (!Number.isFinite(px) || !Number.isFinite(py)) continue;
      minX = Math.min(minX, px);
      minY = Math.min(minY, py);
      maxX = Math.max(maxX, px);
      maxY = Math.max(maxY, py);
    }
    if (minX === Infinity) return { x: 0, y: 0, width: 1, height: 1 };
    return { x: minX, y: minY, width: Math.max(0, maxX - minX), height: Math.max(0, maxY - minY) };
  }

  // JSDOM does not implement SVG layout APIs such as getBBox(), but Mermaid's
  // render pipeline expects them for sizing. Provide a coarse approximation.
  const proto = dom.window.SVGElement?.prototype;
  if (proto && typeof proto.getBBox !== "function") {
    proto.getBBox = function getBBox() {
      const tag = String(this.tagName || "").toLowerCase();
      const m = parseTransformMatrix(this.getAttribute?.("transform"));
      if (tag === "text" || tag.endsWith(":text")) {
        const text = (this.textContent || "").trim();
        const w = Math.max(1, text.length) * 8;
        const h = 16;
        return applyMatrixToBBox({ x: 0, y: 0, width: w, height: h }, m);
      }

      // Attribute-based fallbacks for common shapes.
      const wAttr = parseNum(this.getAttribute?.("width"));
      const hAttr = parseNum(this.getAttribute?.("height"));
      if (wAttr !== null && hAttr !== null) {
        const xAttr = parseNum(this.getAttribute?.("x")) ?? 0;
        const yAttr = parseNum(this.getAttribute?.("y")) ?? 0;
        return applyMatrixToBBox({ x: xAttr, y: yAttr, width: wAttr, height: hAttr }, m);
      }

      const r = parseNum(this.getAttribute?.("r"));
      if (r !== null) {
        const cx = parseNum(this.getAttribute?.("cx")) ?? 0;
        const cy = parseNum(this.getAttribute?.("cy")) ?? 0;
        const d = 2 * r;
        return applyMatrixToBBox({ x: cx - r, y: cy - r, width: d, height: d }, m);
      }

      const rx = parseNum(this.getAttribute?.("rx"));
      const ry = parseNum(this.getAttribute?.("ry"));
      if (rx !== null && ry !== null) {
        const cx = parseNum(this.getAttribute?.("cx")) ?? 0;
        const cy = parseNum(this.getAttribute?.("cy")) ?? 0;
        return applyMatrixToBBox({ x: cx - rx, y: cy - ry, width: 2 * rx, height: 2 * ry }, m);
      }

      // Container elements: union child boxes (best-effort).
      const kids = Array.from(this.children || []);
      if (kids.length) {
        let minX = Infinity,
          minY = Infinity,
          maxX = -Infinity,
          maxY = -Infinity;
        for (const k of kids) {
          if (typeof k.getBBox !== "function") continue;
          const b = k.getBBox();
          if (!b || !Number.isFinite(b.x) || !Number.isFinite(b.y) || !Number.isFinite(b.width) || !Number.isFinite(b.height)) continue;
          minX = Math.min(minX, b.x);
          minY = Math.min(minY, b.y);
          maxX = Math.max(maxX, b.x + b.width);
          maxY = Math.max(maxY, b.y + b.height);
        }
        if (minX !== Infinity) {
          return applyMatrixToBBox(
            { x: minX, y: minY, width: Math.max(0, maxX - minX), height: Math.max(0, maxY - minY) },
            m,
          );
        }
      }

      return applyMatrixToBBox({ x: 0, y: 0, width: 1, height: 1 }, m);
    };
  }
}

async function main() {
  const code = (await readStdin()).trim();
  if (!code) {
    process.stderr.write("render_mermaid_svg: empty input\n");
    process.exit(2);
  }

  const dom = new JSDOM("<!doctype html><html><body></body></html>");
  installDomGlobals(dom);

  // Import after installing a browser-like DOM so Mermaid's dependencies
  // (notably DOMPurify) initialize in "browser mode".
  const mermaid = (await import("mermaid")).default;
  mermaid.initialize({
    startOnLoad: false,
    theme: "neutral",
  });

  try {
    const out = await mermaid.render("m", code);
    const svg = out?.svg || "";
    if (!svg.includes("<svg")) {
      process.stderr.write("render_mermaid_svg: no svg produced\n");
      process.exit(3);
    }
    process.stdout.write(svg);
  } catch (e) {
    process.stderr.write("render_mermaid_svg: render failed\n");
    process.stderr.write(String(e) + "\n");
    process.exit(1);
  }
}

await main();
