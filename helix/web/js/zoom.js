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
// ON A TOUCH SCREEN there is no wheel and no cursor, and a chart a metre
// across is the one thing you cannot read at 380 pixels without pinching.
// Both gestures come off the same pointer events: one finger down is a
// drag, two is a pinch about the point between them — which is what makes
// it feel right, because the thing under your fingers stays under them.
export function attach(wrap, target, { min = 0.05, max = 40 } = {}) {
  let k = 1, x = 0, y = 0, dragging = false, sx = 0, sy = 0;
  let touched = false;
  const live = new Map();                 // pointerId -> {x, y}
  let pinch = null;                       // {d, cx, cy} at the last frame
  const apply = () => target.style.transform = `translate(${x}px,${y}px) scale(${k})`;

  // Scale about a point in the wrapper's own coordinates, so whatever is
  // under the cursor or between the fingers does not move.
  const scaleAbout = (mx, my, f) => {
    const nk = Math.min(max, Math.max(min, k * f));
    x = mx - (mx - x) * (nk / k); y = my - (my - y) * (nk / k); k = nk;
    touched = true;
  };

  wrap.addEventListener('wheel', ev => {
    ev.preventDefault();
    const r = wrap.getBoundingClientRect();
    scaleAbout(ev.clientX - r.left, ev.clientY - r.top,
               Math.exp(-ev.deltaY * 0.0015));
    apply();
  }, { passive: false });

  const twoFinger = () => {
    const [a, b] = [...live.values()];
    return { d: Math.hypot(a.x - b.x, a.y - b.y),
             cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2 };
  };

  wrap.addEventListener('pointerdown', ev => {
    if (ev.pointerType === 'mouse' && ev.button !== 0) return;
    live.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    wrap.setPointerCapture(ev.pointerId);
    if (live.size === 2) { pinch = twoFinger(); dragging = false; wrap.classList.remove('drag'); }
    else if (live.size === 1) {
      dragging = true; sx = ev.clientX - x; sy = ev.clientY - y;
      wrap.classList.add('drag');
    }
  });

  wrap.addEventListener('pointermove', ev => {
    if (!live.has(ev.pointerId)) return;
    live.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (live.size >= 2 && pinch) {
      const now = twoFinger(), r = wrap.getBoundingClientRect();
      if (pinch.d > 0) scaleAbout(now.cx - r.left, now.cy - r.top, now.d / pinch.d);
      // Two fingers moving together pan as well as pinch: that is one
      // gesture to a hand, and splitting it makes the chart feel stuck.
      x += now.cx - pinch.cx; y += now.cy - pinch.cy;
      pinch = now; touched = true; apply();
      return;
    }
    if (!dragging) return;
    x = ev.clientX - sx; y = ev.clientY - sy; touched = true; apply();
  });

  const stop = ev => {
    if (ev) live.delete(ev.pointerId);
    if (live.size < 2) pinch = null;
    // Lifting one of two fingers must not jump the chart: carry on the
    // drag from wherever the finger that is left actually is.
    if (live.size === 1) {
      const [p] = [...live.values()];
      dragging = true; sx = p.x - x; sy = p.y - y; wrap.classList.add('drag');
    } else if (!live.size) { dragging = false; wrap.classList.remove('drag'); }
  };
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
