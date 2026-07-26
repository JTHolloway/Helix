// RenderPlan -> SVG DOM. Deliberately a mirror of render/svg.py so that what
// you see on screen is exactly what lands in the exported file.
const NS = 'http://www.w3.org/2000/svg';
const ORDER = ['PRINT_ONLY', 'GUIDE', 'ENGRAVE', 'ENGRAVE_DEEP', 'SCORE', 'CUT'];

export function draw(host, plan) {
  host.innerHTML = '';
  const c = plan.canvas;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${c.width_mm} ${c.height_mm}`);
  svg.setAttribute('width', c.width_mm);
  svg.setAttribute('height', c.height_mm);
  const bg = el('rect', { x: 0, y: 0, width: c.width_mm, height: c.height_mm, fill: c.background });
  svg.appendChild(bg);

  const groups = {};
  for (const e of plan.elements) (groups[e.layer] ||= []).push(e);
  for (const layer of ORDER) {
    if (!groups[layer]) continue;
    const g = el('g', { id: layer });
    for (const e of groups[layer]) g.appendChild(node(e));
    svg.appendChild(g);
  }
  host.appendChild(svg);
  return svg;
}

function node(e) {
  let n;
  if (e.kind === 'text') {
    n = el('text', {
      x: e.x, y: e.y, 'font-size': e.font?.size_mm ?? 3,
      'font-family': e.font?.family ?? 'sans-serif',
      'font-weight': e.font?.weight ?? 400,
      'letter-spacing': e.font?.letter_spacing || null,
      'text-anchor': e.font?.anchor ?? 'middle',
      'dominant-baseline': 'central', fill: e.fill || '#000',
      transform: e.rotate ? `rotate(${e.rotate},${e.x},${e.y})` : null,
      'pointer-events': 'none'
    });
    n.textContent = e.text || '';
  } else if (e.kind === 'circle') {
    n = el('circle', { cx: e.x, cy: e.y, r: e.r });
  } else if (e.kind === 'rect') {
    n = el('rect', { x: e.x, y: e.y, width: e.w, height: e.h, rx: e.rx || null });
  } else {
    n = el('path', { d: e.d });
  }
  if (e.kind !== 'text') {
    n.setAttribute('fill', e.fill || 'none');
    if (e.stroke && e.stroke !== 'none') {
      n.setAttribute('stroke', e.stroke);
      n.setAttribute('stroke-width', e.stroke_width ?? 0.3);
      n.setAttribute('stroke-linecap', 'round');
      n.setAttribute('stroke-linejoin', 'round');
    }
    if (e.dash) n.setAttribute('stroke-dasharray', e.dash);
  }
  if (e.opacity != null && e.opacity < 1) n.setAttribute('opacity', e.opacity);
  if (e.person_id) { n.dataset.p = e.person_id; n.dataset.role = e.role; }
  if (e.line_id) n.dataset.line = e.line_id;
  return n;
}

function el(tag, attrs) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  return n;
}
