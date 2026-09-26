const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const fixture = JSON.parse(fs.readFileSync(0, 'utf8'));
const script = fs.readFileSync(path.join(__dirname, '../site/assets/citations.js'), 'utf8');
const controls = '<div id="sourceLayoutControl" hidden><button data-source-layout="inline">Inline</button><button data-source-layout="margin">Margin</button></div>';

function page({ saved, blocked = false, empty = false } = {}) {
  const dom = new JSDOM(controls + '<article><div class="reading-body">' + (empty ? '<p>No references.</p>' : fixture.html) + '</div></article>', {
    runScripts: 'outside-only', url: 'https://example.test/guide/',
  });
  const { window } = dom;
  window.HTMLElement.prototype.showPopover = undefined;
  if (saved) window.localStorage.setItem('source-layout', saved);
  if (blocked) Object.defineProperty(window, 'localStorage', { get() { throw new Error('Storage blocked'); } });
  window.eval(script);
  return dom;
}

const initial = page();
let doc = initial.window.document;
assert.equal(doc.documentElement.dataset.sourceLayout, 'inline');
assert.equal(doc.querySelector('#sourceLayoutControl').hidden, false);
assert.equal(doc.querySelectorAll('.citation-margin').length, 2);
assert.equal(doc.querySelectorAll('ul > li').length, 1);
assert.equal(doc.querySelectorAll('ul > div').length, 0);
assert.equal(doc.querySelectorAll('a.cite').length, 2, 'unsupported popovers keep original links');
assert.ok(doc.querySelector('.cite-fallback a').href.endsWith('#page=13'));
assert.equal(doc.documentElement.classList.contains('citation-enhanced'), false);
doc.querySelector('button[data-source-layout="margin"]').click();
assert.equal(doc.documentElement.dataset.sourceLayout, 'margin');
assert.equal(doc.querySelector('button[data-source-layout="margin"]').getAttribute('aria-pressed'), 'true');
assert.equal(initial.window.localStorage.getItem('source-layout'), 'margin');
const saved = initial.window.localStorage.getItem('source-layout');
doc.querySelector('button[data-source-layout="inline"]').click();
assert.equal(doc.querySelector('button[data-source-layout="margin"]').getAttribute('aria-pressed'), 'false');
assert.equal(doc.querySelectorAll('.citation-margin a').length, 3, 'switching never discards a destination');
initial.window.close();

const restored = page({ saved });
assert.equal(restored.window.document.documentElement.dataset.sourceLayout, 'margin');
restored.window.close();
const invalid = page({ saved: 'unexpected' });
assert.equal(invalid.window.document.documentElement.dataset.sourceLayout, 'inline');
invalid.window.close();
const blocked = page({ blocked: true });
blocked.window.document.querySelector('button[data-source-layout="margin"]').click();
assert.equal(blocked.window.document.documentElement.dataset.sourceLayout, 'margin');
blocked.window.close();
const empty = page({ empty: true });
assert.equal(empty.window.document.querySelector('#sourceLayoutControl').hidden, true);
empty.window.close();
process.stdout.write(JSON.stringify({ passed: 5 }));
