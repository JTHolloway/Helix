// Pan and zoom without a library: 70 lines beats a 90 kB dependency.
export function attach(wrap, target, { min = 0.05, max = 40 } = {}) {
  let k = 1, x = 0, y = 0, dragging = false, sx = 0, sy = 0;
  const apply = () => target.style.transform = `translate(${x}px,${y}px) scale(${k})`;

  wrap.addEventListener('wheel', ev => {
    ev.preventDefault();
    const r = wrap.getBoundingClientRect();
    const mx = ev.clientX - r.left, my = ev.clientY - r.top;
    const f = Math.exp(-ev.deltaY * 0.0015);
    const nk = Math.min(max, Math.max(min, k * f));
    x = mx - (mx - x) * (nk / k); y = my - (my - y) * (nk / k); k = nk; apply();
  }, { passive: false });

  wrap.addEventListener('pointerdown', ev => {
    if (ev.button !== 0) return;
    dragging = true; sx = ev.clientX - x; sy = ev.clientY - y;
    wrap.setPointerCapture(ev.pointerId); wrap.classList.add('drag');
  });
  wrap.addEventListener('pointermove', ev => {
    if (!dragging) return;
    x = ev.clientX - sx; y = ev.clientY - sy; apply();
  });
  const stop = () => { dragging = false; wrap.classList.remove('drag'); };
  wrap.addEventListener('pointerup', stop);
  wrap.addEventListener('pointercancel', stop);

  return {
    fit() {
      const svg = target.querySelector('svg'); if (!svg) return;
      const w = +svg.getAttribute('width'), h = +svg.getAttribute('height');
      const r = wrap.getBoundingClientRect();
      k = Math.min(r.width / w, r.height / h) * 0.92;
      x = (r.width - w * k) / 2; y = (r.height - h * k) / 2; apply();
    },
    zoom(f) {
      const r = wrap.getBoundingClientRect(), mx = r.width / 2, my = r.height / 2;
      const nk = Math.min(max, Math.max(min, k * f));
      x = mx - (mx - x) * (nk / k); y = my - (my - y) * (nk / k); k = nk; apply();
    },
    centreOn(px, py, scale) {
      const svg = target.querySelector('svg'); if (!svg) return;
      const w = +svg.getAttribute('width');
      const r = wrap.getBoundingClientRect();
      k = scale ?? Math.max(k, Math.min(r.width / w, 4));
      x = r.width / 2 - px * k; y = r.height / 2 - py * k; apply();
    }
  };
}
