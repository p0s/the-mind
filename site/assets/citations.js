/* Progressive enhancement only: generated citations remain ordinary links. */
(() => {
  const refs = [...document.querySelectorAll('.reading-body .cite_ref[data-source]')];
  const control = document.getElementById('sourceLayoutControl');
  if (!refs.length || !control) return;

  const blocks = new Map();
  for (const ref of refs) {
    const passage = ref.closest('p, li');
    const details = ref.querySelector('.cite-details');
    if (!passage || !details) continue;
    if (!blocks.has(passage)) blocks.set(passage, []);
    blocks.get(passage).push(details);
  }
  for (const [passage, details] of blocks) {
    const wrapper = document.createElement('div');
    wrapper.className = 'citation-block';
    passage.before(wrapper);
    // Keep <li> directly inside its list and preserve all of its content.
    if (passage.tagName === 'LI') {
      const prose = document.createElement('div');
      prose.className = 'citation-prose';
      prose.append(...passage.childNodes);
      wrapper.append(prose);
      passage.append(wrapper);
    } else {
      wrapper.append(passage);
    }
    const margin = document.createElement('aside');
    margin.className = 'citation-margin';
    margin.setAttribute('aria-label', 'Passage sources');
    for (const detail of details) {
      const note = detail.cloneNode(true);
      note.className = 'source-note';
      note.hidden = false;
      margin.append(note);
    }
    wrapper.append(margin);
  }

  const popover = document.createElement('div');
  popover.id = 'sourcePopover';
  popover.className = 'source-popover';
  popover.setAttribute('popover', 'auto');
  popover.setAttribute('role', 'dialog');
  popover.setAttribute('aria-label', 'Source details');
  const closeButton = document.createElement('button');
  closeButton.type = 'button';
  closeButton.className = 'source-popover-close';
  closeButton.setAttribute('aria-label', 'Close source details');
  closeButton.textContent = '×';
  const content = document.createElement('div');
  popover.append(closeButton, content);
  let active = null;
  const supportsPopover = typeof popover.showPopover === 'function';

  function close(restoreFocus = false) {
    if (supportsPopover && popover.matches(':popover-open')) popover.hidePopover();
    if (active) {
      active.setAttribute('aria-expanded', 'false');
      if (restoreFocus) active.focus({ preventScroll: true });
    }
  }
  function position() {
    if (!active || !popover.matches(':popover-open')) return;
    const rect = active.getBoundingClientRect();
    const width = popover.offsetWidth;
    const height = popover.offsetHeight;
    popover.style.left = Math.max(14, Math.min(rect.left, innerWidth - width - 14)) + 'px';
    const below = rect.bottom + 8;
    popover.style.top = Math.max(14, Math.min(below + height < innerHeight - 14 ? below : rect.top - height - 8, innerHeight - height - 14)) + 'px';
  }

  // Older browsers retain direct links and all additional locator destinations.
  if (supportsPopover) {
    document.body.append(popover);
    for (const ref of refs) {
      const link = ref.querySelector('a.cite');
      const detail = ref.querySelector('.cite-details');
      if (!link || !detail) continue;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = link.className;
      button.append(...link.childNodes);
      button.title = link.title;
      button.setAttribute('aria-label', 'Show source — ' + link.getAttribute('aria-label'));
      button.setAttribute('aria-haspopup', 'dialog');
      button.setAttribute('aria-expanded', 'false');
      button.setAttribute('aria-controls', popover.id);
      link.replaceWith(button);
      button.addEventListener('click', () => {
        if (active === button && popover.matches(':popover-open')) { close(true); return; }
        close();
        active = button;
        const note = detail.cloneNode(true);
        note.className = 'source-note';
        note.hidden = false;
        content.replaceChildren(note);
        popover.showPopover();
        button.setAttribute('aria-expanded', 'true');
        position();
        closeButton.focus({ preventScroll: true });
      });
    }
    document.documentElement.classList.add('citation-enhanced');
    closeButton.addEventListener('click', () => close(true));
    popover.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); close(true); }
    });
    popover.addEventListener('toggle', event => {
      if (event.newState === 'closed' && active) active.setAttribute('aria-expanded', 'false');
    });
    window.addEventListener('resize', position, { passive: true });
    window.addEventListener('scroll', () => close(), { passive: true });
  }

  function apply(layout) {
    close();
    document.documentElement.dataset.sourceLayout = layout;
    control.querySelectorAll('button').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.sourceLayout === layout));
    });
  }
  let layout = 'inline';
  try { if (localStorage.getItem('source-layout') === 'margin') layout = 'margin'; } catch (_) {}
  apply(layout);
  control.hidden = blocks.size === 0;
  control.addEventListener('click', event => {
    const button = event.target.closest('button[data-source-layout]');
    if (!button) return;
    const next = button.dataset.sourceLayout;
    apply(next);
    try { localStorage.setItem('source-layout', next); } catch (_) {}
  });
})();
