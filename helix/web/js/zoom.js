// Pan and zoom without a library: 70 lines beats a 90 kB dependency.
//
// THE VIEW HAS TO SURVIVE THE PANEL OPENING. The stage loses 330px the
// moment a profile appears, and gains it back when the profile closes;
// narrowing the tree changes the chart's size; dragging the window smaller
// changes both. Fitted once at start-up and never again, the chart spent
// most of the session with a third of the family off the right-hand edge —
// under the very panel that had just opened to tell you about somebody.
//
// So the fit is re-run whenever the stage changes size or the drawing is
// replaced — but ONLY while the person has not chosen a view of their own.
// One wheel click or one drag and the view is theirs; re-centring it under
// them every time a sidebar moved would be worse than the bug.
export function attach(wrap, target, { min = 0.05, max = 40 } = {}) {
  let k = 1, x = 0, y = 0, dragging = false, sx = 0, sy = 0;
  let touched = false;
  const apply = () => target.style.transform = `translate(${x}px,${y}px) scale(${k})`;

  wrap.addEventListener('wheel', ev => {
    ev.preventDefault();
    const r = wrap.getBoundingClientRect();
    const mx = ev.clientX - r.left, my = ev.clientY - r.top;
    const f = Math.exp(-ev.deltaY * 0.0015);
    const nk = Math.min(max, Math.max(min, k * f));
    x = mx - (mx - x) * (nk / k); y = my - (my - y) * (nk / k); k = nk;
    touched = true; apply();
  }, { passive: false });

  wrap.addEventListener('pointerdown', ev => {
    if (ev.button !== 0) return;
    dragging = true; sx = ev.clientX - x; sy = ev.clientY - y;
    wrap.setPointerCapture(ev.pointerId); wrap.classList.add('drag');
  });
  wrap.addEventListener('pointermove', ev => {
    if (!dragging) return;
    x = ev.clientX - sx; y = ev.clientY - sy; touched = true; apply();
  });
  const stop = () => { dragging = false; wrap.classList.remove('drag'); };
  wrap.addEventListener('pointerup', stop);
  wrap.addEventListener('pointercancel', stop);

  const api = {
    fit() {
      const svg = target.querySelector('svg'); if (!svg) return;
      const w = +svg.getAttribute('width'), h = +svg.getAttribute('height');
      if (!w || !h) return;
      const r = wrap.getBoundingClientRect();
      if (!r.width || !r.height) return;
      k = Math.min(r.width / w, r.height / h) * 0.92;
      x = (r.width - w * k) / 2; y = (r.height - h * k) / 2;
      touched = false; apply();
    },
    // Fit again, unless the person has chosen their own view. Called after
    // every redraw and whenever the stage changes size.
    refit() { if (!touched) api.fit(); },
    chosen() { return touched; },
    zoom(f) {
      const r = wrap.getBoundingClientRect(), mx = r.width / 2, my = r.height / 2;
      const nk = Math.min(max, Math.max(min, k * f));
      x = mx - (mx - x) * (nk / k); y = my - (my - y) * (nk / k); k = nk;
      touched = true; apply();
    },
    centreOn(px, py, scale) {
      const svg = target.querySelector('svg'); if (!svg) return;
      const w = +svg.getAttribute('width');
      const r = wrap.getBoundingClientRect();
      k = scale ?? Math.max(k, Math.min(r.width / w, 4));
      x = r.width / 2 - px * k; y = r.height / 2 - py * k;
      touched = true; apply();
    }
  };

  // The stage changes size for three different reasons and none of them
  // fires a window resize: the profile panel opening, the profile panel
  // closing, and the browser window itself being dragged. One observer
  // covers all three.
  if (typeof ResizeObserver !== 'undefined') {
    let t = null;
    new ResizeObserver(() => {
      clearTimeout(t);
      t = setTimeout(() => api.refit(), 60);
    }).observe(wrap);
  }
  return api;
}
