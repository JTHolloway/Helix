// The same interface, on a screen you hold in one hand.
//
// A family history gets looked at in places a laptop does not go: a
// churchyard, a record office, an aunt's front room with the photograph you
// have been after for a year. So the interface has to work at 380 pixels.
//
// NOTHING HERE IS A SECOND INTERFACE. The CSS folds the two sidebars into
// drawers and the nine header buttons into one menu; this file is only the
// twenty lines of behaviour that folding needs — open, close, and close
// again once you have chosen somebody, because a drawer that stays open
// over the answer is worse than no drawer.
const $ = s => document.querySelector(s);

// One number, in one place. It is the same 900px the stylesheet switches
// at, and the two drifting apart is how a drawer ends up open on a desktop.
const NARROW = '(max-width:900px)';
export const isNarrow = () => window.matchMedia(NARROW).matches;

export function drawer(open) {
  document.body.dataset.drawer = open ? 'open' : 'shut';
  $('#menuBtn')?.setAttribute('aria-expanded', String(!!open));
  $('#scrim').hidden = !open;
}

export function tools(open) {
  document.body.dataset.tools = open ? 'open' : 'shut';
  $('#toolsBtn')?.setAttribute('aria-expanded', String(!!open));
}

/**
 * @param {object} hooks
 * @param {() => void} hooks.onClose  run when the drawer shuts, so the chart
 *                                    can re-fit into the width it just got back
 */
export function wire({ onClose = () => {} } = {}) {
  const shut = () => { drawer(false); onClose(); };

  $('#menuBtn').addEventListener('click', () => {
    const open = document.body.dataset.drawer !== 'open';
    tools(false);
    open ? drawer(true) : shut();
  });
  $('#toolsBtn').addEventListener('click', () => {
    const open = document.body.dataset.tools !== 'open';
    if (open) drawer(false);
    tools(open);
  });
  $('#scrim').addEventListener('click', shut);
  document.querySelectorAll('.drawerclose').forEach(b =>
    b.addEventListener('click', shut));

  // A tool chosen from the folded menu closes it. Otherwise the menu sits
  // over the dialogue it just opened.
  $('#tools').addEventListener('click', e => {
    if (e.target.closest('button') && isNarrow()) tools(false);
  });
  document.addEventListener('click', e => {
    if (document.body.dataset.tools !== 'open') return;
    if (e.target.closest('#tools') || e.target.closest('#toolsBtn')) return;
    tools(false);
  });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (document.body.dataset.tools === 'open') { tools(false); return; }
    if (document.body.dataset.drawer === 'open') shut();
  });

  // Growing the window past the fold leaves the drawer state stale: the
  // scrim would stay over a layout that no longer has anything behind it.
  window.matchMedia(NARROW).addEventListener?.('change', ev => {
    if (!ev.matches) { drawer(false); tools(false); }
  });

  drawer(false);
  tools(false);
}

/** Chose somebody from the drawer: get out of the way of the answer. */
export function chose() {
  if (isNarrow()) drawer(false);
}
