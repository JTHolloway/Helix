// Helix front end.
//
// Design rule for this file: the person using it should never have to know
// what a "render plan" is. Controls are named for what they do, the preview
// updates as you move them, and nothing is ever lost by experimenting.
import { get, post, svgUrl } from './api.js';
import { draw } from './canvas.js';
import { attach } from './zoom.js';
import * as inspector from './inspector.js';

const $ = s => document.querySelector(s);
const wrap = $('#canvasWrap'), host = $('#canvas');
const view = attach(wrap, host);

let META = null, PLAN = null, SEL = null, WHATIF = false, TIMER = null;

const S = {                       // everything the preview depends on
  design: 'radial_rings', style: 'rings', gens: '5', focus: 'bloodline',
  tpl: '{given_first} {surname}', cmode: 'none', redact: false,
  threadOn: true, w: 1000, h: 1000, inner: 110, gamma: 50, timeScale: true,
  rings: true, fsize: 34, lw: 45, conn: 'orthogonal', start: -90, sweep: 360,
  pitch: 25, entrygap: 0, cluster: 0, orient: 'radial', marr: true
};

// ─────────────────────────────────────────────────────────────── boot ────
init().catch(fail);

async function init() {
  META = await get('meta');
  $('#proj').textContent = META.title || '';
  buildGallery();
  wireControls();
  wireSearch();
  wireExport();
  wireKeys();
  await refresh();
  view.fit();
  status();
  setInterval(status, 30000);
}

// ───────────────────────────────────────────────────────── the preview ───
function refresh() {
  clearTimeout(TIMER);
  return new Promise(res => { TIMER = setTimeout(() => res(_refresh()), 120); });
}

async function _refresh() {
  $('#loading').hidden = false;
  try {
    PLAN = await get('plan', params());
    draw(host, PLAN);
    host.querySelectorAll('[data-p]').forEach(n => {
      n.addEventListener('click', ev => { ev.stopPropagation(); select(n.dataset.p); });
      n.addEventListener('pointerenter', () => WHATIF && whatIf(n.dataset.p));
    });
    if (SEL) markSelected();
    readout();
  } catch (e) { fail(e); } finally { $('#loading').hidden = true; }
}

function params() {
  return {
    design: S.design, style: S.style, gens: S.gens, focus: S.focus,
    redact: S.redact ? 1 : 0,
    's.canvas.width_mm': S.w, 's.canvas.height_mm': S.h,
    's.layout.inner_radius_mm': S.inner,
    's.layout.radius_gamma': (S.gamma / 100).toFixed(2),
    's.layout.time_scale': S.timeScale, 's.layout.start_angle_deg': S.start,
    's.layout.sweep_deg': S.sweep,
    's.ornament.time_rings': S.rings,
    's.layout.min_ring_pitch_mm': S.pitch,
    's.layout.min_entry_gap_mm': S.entrygap,
    's.layout.sibling_gap_frac': (S.cluster / 100).toFixed(2),
    's.labels.orientation': S.orient,
    's.marriage.show': S.marr,
    's.labels.lines': JSON.stringify(S.tpl.split('|').filter(Boolean)),
    's.labels.show': S.tpl ? true : false,
    's.type.size_mm': (S.fsize / 10).toFixed(2),
    's.connectors.width_mm': (S.lw / 100).toFixed(2),
    's.connectors.style': S.conn,
    's.colour.mode': S.cmode,
    's.thread.enabled': S.threadOn
  };
}

function readout() {
  const m = PLAN.meta, n = m.extra?.labels_hidden || 0;
  showFit(m.extra?.fit, n);
  $('#readout').innerHTML =
    `<b>${m.people}</b> people · ${m.generations} generations · ` +
    `${m.year_min}–${m.year_max} · ${S.w}×${S.h} mm` +
    (n ? `<br><span class="warn">${n} names did not fit.</span>`
       : `<br><span class="ok">Every name fits.</span>`);
}

// ───────────────────────────────────────────────────────────── gallery ───
function buildGallery() {
  const g = $('#gallery');
  g.innerHTML = '';
  for (const d of META.designs) {
    const b = document.createElement('button');
    b.innerHTML = thumb(d.key) + `<span>${d.name}</span>`;
    b.setAttribute('aria-pressed', d.key === S.design);
    b.title = `${d.blurb}\n\nGood for: ${d.good_for}\nLaser: ${d.laser}`;
    b.addEventListener('click', () => {
      S.design = d.key;
      g.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', false));
      b.setAttribute('aria-pressed', true);
      $('#designBlurb').textContent = `${d.blurb} — good for ${d.good_for.toLowerCase()}`;
      const sq = d.family === 'radial' || d.key === 'circle_pack';
      if (sq && S.w !== S.h) { S.w = S.h = 1000; $('#w').value = 1000; $('#h').value = 1000; }
      if (!sq && S.w === S.h) { S.w = 1189; S.h = 594; $('#w').value = 1189; $('#h').value = 594; }
      refresh().then(() => view.fit());
    });
    g.appendChild(b);
  }
  $('#designBlurb').textContent = META.designs.find(d => d.key === S.design)?.blurb || '';
}

// Tiny hand-drawn icons so the gallery is choosable at a glance, before any
// real render exists. Cheaper and clearer than 11 live previews.
function thumb(key) {
  const P = { radial_sunburst: 'M50 50m-30 0a30 30 0 1 0 60 0a30 30 0 1 0-60 0M50 50m-18 0a18 18 0 1 0 36 0a18 18 0 1 0-36 0M50 20V32M74 36 63 43M74 64 63 57M50 80V68M26 64 37 57M26 36 37 43',
    radial_rings: 'M20 50a30 30 0 0 1 34 -29M32 50a18 18 0 0 1 30 -12M42 50a8 8 0 0 1 14 -4M50 50V21M56 34l14 -9M62 22V12M76 32l7 -5',
    radial_organic: 'M50 50C50 36 40 30 30 22M50 50C50 36 60 30 70 22M50 50C50 64 40 70 30 78M50 50C50 64 60 70 70 78M50 50v0',
    radial_lifeline: 'M50 20v22M65 26l-9 20M35 26l9 20M72 42l-20 8M28 42l20 8M50 80V58M66 74l-9-20M34 74l9-20',
    radial_spiral: 'M50 50c0-4 4-8 8-8s10 5 10 12-7 14-16 14-20-9-20-20 11-24 24-24 28 12 28 28',
    metro_map: 'M12 30h20l14 14h30M12 60h30l14-14h32M32 30v30M60 44v26M76 30h12',
    timeline_lanes: 'M14 26h40M14 42h58M14 58h30M14 74h50M14 18v62',
    dendrogram: 'M14 50h14v-24h20M28 50h14M28 50v24h20M62 26h14M62 74h14M48 26v0',
    icicle: 'M12 22h76M12 40h44M58 40h30M12 58h24M38 58h18M60 58h28M12 76h14M28 76h20',
    arc_diagram: 'M14 74h72M22 74a14 14 0 0 1 28 0M36 74a22 22 0 0 1 44 0M50 74a10 10 0 0 1 20 0',
    circle_pack: 'M50 50m-34 0a34 34 0 1 0 68 0a34 34 0 1 0-68 0M36 40m-11 0a11 11 0 1 0 22 0a11 11 0 1 0-22 0M64 58m-13 0a13 13 0 1 0 26 0a13 13 0 1 0-26 0' };
  return `<svg viewBox="0 0 100 100"><path d="${P[key] || P.radial_sunburst}"
    fill="none" stroke="#26241F" stroke-width="2.4" stroke-linecap="round"/></svg>`;
}

// ───────────────────────────────────────────────────────────── controls ──
function wireControls() {
  const bind = (id, key, fmt) => {
    const el = $('#' + id); if (!el) return;
    const out = $('#' + id + 'V');
    const read = () => el.type === 'checkbox' ? el.checked
      : (el.type === 'number' || el.type === 'range') ? +el.value : el.value;
    const upd = () => { S[key] = read(); if (out && fmt) out.textContent = fmt(read()); refresh(); };
    el.addEventListener(el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input', upd);
    if (out && fmt) out.textContent = fmt(read());
  };
  bind('focus', 'focus'); bind('gens', 'gens'); bind('tpl', 'tpl');
  bind('cmode', 'cmode');
  bind('redact', 'redact'); bind('threadOn', 'threadOn'); bind('marr', 'marr');
  bind('w', 'w'); bind('h', 'h'); bind('conn', 'conn');
  bind('timeScale', 'timeScale'); bind('rings', 'rings');
  bind('inner', 'inner', v => v + ' mm');
  bind('pitch', 'pitch', v => `${v} mm (${(v / 25.4).toFixed(1)}")`);
  bind('orient', 'orient');
  bind('entrygap', 'entrygap',
    v => v == 0 ? 'as tight as the text allows' : `at least ${v} mm apart`);
  bind('cluster', 'cluster',
    v => v == 0 ? 'off' : `families pulled ${v}% closer together`);
  $('#preset').addEventListener('change', e => {
    if (e.target.value === 'custom') return;
    const [w, h] = e.target.value.split('x').map(Number);
    S.w = w; S.h = h; $('#w').value = w; $('#h').value = h;
    refresh().then(() => view.fit());
  });
  bind('gamma', 'gamma', v => v == 50 ? 'equal area (recommended)'
    : v == 100 ? 'linear in time' : `${v / 100} — between the two`);
  bind('fsize', 'fsize', v => (v / 10).toFixed(1) + ' mm');
  bind('lw', 'lw', v => (v / 100).toFixed(2) + ' mm');
  bind('start', 'start', v => v == -90 ? "12 o'clock" : v + '°');
  bind('sweep', 'sweep', v => v == 360 ? 'full circle' : v == 180 ? 'half fan' : v + '°');

  $('#modeBtn').addEventListener('click', () => {
    const simple = document.body.dataset.mode === 'simple';
    document.body.dataset.mode = simple ? 'advanced' : 'simple';
    $('#modeBtn').textContent = simple ? 'Simple' : 'Advanced';
  });
  $('#whatif').addEventListener('change', e => {
    WHATIF = e.target.checked;
    if (!WHATIF) clearWhatIf();
  });
  $('#criticalBtn').addEventListener('click', showCritical);
  $('#preflightBtn').addEventListener('click', preflight);
  $('#closeInsp').addEventListener('click', () => { $('#right').hidden = true; SEL = null; markSelected(); });
  document.querySelectorAll('.zoomers button').forEach(b =>
    b.addEventListener('click', () => ({
      in: () => view.zoom(1.35), out: () => view.zoom(1 / 1.35), fit: () => view.fit()
    }[b.dataset.z]())));
  wrap.addEventListener('click', () => { if (WHATIF) clearWhatIf(); });
}

// ────────────────────────────────────────────────────────── selection ────
async function select(pid) {
  SEL = pid;
  markSelected();
  $('#right').hidden = false;
  await inspector.show($('#inspector'), pid, {
    onSelect: select,
    onSubject: async () => { META = await get('meta'); refresh(); },
    onChanged: () => refresh()
  });
}

function markSelected() {
  host.querySelectorAll('.sel').forEach(n => n.classList.remove('sel'));
  if (SEL) host.querySelectorAll(`[data-p="${CSS.escape(SEL)}"]`)
    .forEach(n => n.classList.add('sel'));
}

// ────────────────────────────────────────────── what-if contingency ──────
let whatifTimer = null;
async function whatIf(pid) {
  clearTimeout(whatifTimer);
  whatifTimer = setTimeout(async () => {
    try {
      const r = await get('contingency', { id: pid });
      const gone = new Set(r.removed);
      host.querySelectorAll('[data-p]').forEach(n =>
        n.classList.toggle('dim', !gone.has(n.dataset.p)));
      $('#whatifCard').hidden = false;
      $('#whatifCard').innerHTML =
        `Without <b>${r.name}</b><br>` +
        `<b>${r.removed_count.toLocaleString()}</b> people vanish from this chart` +
        (r.surnames_lost.length ? ` — ${r.surnames_lost.length} surnames` : '') +
        (r.subject_removed ? ' — <b>including you</b>' : '') +
        `<small>Move away to clear. Click anywhere to unlock.</small>`;
    } catch (e) { /* hovering faster than the server: harmless */ }
  }, 90);
}

function clearWhatIf() {
  clearTimeout(whatifTimer);
  host.querySelectorAll('.dim').forEach(n => n.classList.remove('dim'));
  $('#whatifCard').hidden = true;
}

async function showCritical() {
  const rows = await get('critical', { n: 20 });
  $('#listTitle').textContent = 'Most important ancestors';
  $('#listBody').innerHTML = rows.map(r =>
    `<button data-p="${r.id}"><b>${r.n}</b> ${escape2(r.name)}
      <small>${escape2(r.life)}</small></button>`).join('')
    || '<p class="hint">Not enough of a tree yet to rank anyone.</p>';
  $('#listBody').querySelectorAll('button').forEach(b =>
    b.addEventListener('click', () => { $('#listDlg').close(); select(b.dataset.p); }));
  $('#listDlg').showModal();
}

// ─────────────────────────────────────────────────────────── preflight ───
async function preflight() {
  const rep = $('#preflight');
  const m = PLAN.meta, hidden = m.extra?.labels_hidden || 0;
  const minText = (S.fsize / 10);
  const rows = [
    [hidden === 0 ? 'pass' : 'warn',
      hidden === 0 ? 'Every name fits' : `${hidden} names could not be shown`],
    [minText >= 2.2 ? 'pass' : 'fail',
      `Smallest text ${minText.toFixed(1)} mm ` +
      (minText >= 2.2 ? '(fine for wood)' : '— below 2.2 mm it will not read on wood')],
    [(S.lw / 100) >= 0.2 ? 'pass' : 'warn',
      `Line weight ${(S.lw / 100).toFixed(2)} mm`],
    [S.w <= 600 && S.h <= 400 ? 'pass' : 'warn',
      `${S.w}×${S.h} mm ` + (S.w <= 600 && S.h <= 400 ? 'fits a common 600×400 bed'
        : '— larger than a 600×400 bed, so it will need tiling')],
    ['warn', 'Cut a half-scale proof on card before committing to good material'],
    ['warn', 'Convert text to outlines on export (production SVG does this)']
  ];
  rep.innerHTML = rows.map(([c, t]) => `<div class="${c}">${t}</div>`).join('');
}

// ────────────────────────────────────────────────────────────── search ───
function wireSearch() {
  const box = $('#search'), out = $('#results');
  box.addEventListener('input', () => {
    const q = box.value.trim().toLowerCase();
    if (q.length < 2) { out.hidden = true; return; }
    const hits = META.people.filter(p => p.name.toLowerCase().includes(q)).slice(0, 40);
    out.innerHTML = hits.map(p =>
      `<button data-p="${p.id}">${escape2(p.name)}<small>${escape2(p.life)}</small></button>`)
      .join('') || '<button disabled>No one by that name</button>';
    out.querySelectorAll('button[data-p]').forEach(b =>
      b.addEventListener('click', () => {
        out.hidden = true; box.value = ''; select(b.dataset.p); focusOn(b.dataset.p);
      }));
    out.hidden = false;
  });
  document.addEventListener('click', e => {
    if (!out.contains(e.target) && e.target !== box) out.hidden = true;
  });
}

function focusOn(pid) {
  const el = PLAN.elements.find(e => e.person_id === pid && e.x != null);
  if (el) view.centreOn(el.x, el.y, 3);
}

// ────────────────────────────────────────────────────────────── export ───
function wireExport() {
  $('#exportBtn').addEventListener('click', () => {
    $('#exportSize').textContent =
      `Finished size ${S.w} × ${S.h} mm. Files come out at true scale, so a ` +
      `laser or printer will not resize them.`;
    $('#exportDlg').showModal();
  });
  $('#exportDlg').querySelectorAll('[data-x]').forEach(b =>
    b.addEventListener('click', () => {
      const kind = b.dataset.x;
      if (kind === 'png') return exportPng();
      const p = { ...params(), name: (META.title || 'family').replace(/\W+/g, '-') };
      if (kind === 'svgprod') p.production = 1;
      if (kind === 'json') { downloadText(JSON.stringify(PLAN, null, 2), 'plan.json'); return; }
      if (kind === 'backup' || kind === 'archive') {
        post(kind, {}).then(r => {
          $('#exportSize').textContent = `Written to ${r.path}`;
          status();
        }).catch(e => { $('#exportSize').textContent = e.message; });
        return;
      }
      window.location = svgUrl(p);
    }));
}

function exportPng() {
  const svg = host.querySelector('svg');
  const blob = new Blob([new XMLSerializer().serializeToString(svg)],
    { type: 'image/svg+xml' });
  const url = URL.createObjectURL(blob), img = new Image();
  img.onload = () => {
    const c = document.createElement('canvas');
    const scale = Math.min(4, 4000 / Math.max(S.w, S.h));
    c.width = S.w * scale; c.height = S.h * scale;
    const g = c.getContext('2d');
    g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height);
    g.drawImage(img, 0, 0, c.width, c.height);
    c.toBlob(b => download(b, 'family-tree.png'));
    URL.revokeObjectURL(url);
  };
  img.src = url;
}

const download = (blob, name) => {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
};
const downloadText = (t, n) => download(new Blob([t], { type: 'application/json' }), n);

// ───────────────────────────────────────────────────────────── keyboard ──
function wireKeys() {
  document.addEventListener('keydown', e => {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    const k = e.key.toLowerCase();
    if (k === '/') { e.preventDefault(); $('#search').focus(); }
    if (k === 'f') view.fit();
    if (k === 't') { $('#threadOn').click(); }
    if (k === 'c') { $('#whatif').click(); }
    if (k === 'escape') { clearWhatIf(); $('#right').hidden = true; SEL = null; markSelected(); }
    if (k === '+' || k === '=') view.zoom(1.35);
    if (k === '-') view.zoom(1 / 1.35);
  });
}

// ────────────────────────────────────────────────────────────── errors ───
function fail(e) {
  console.error(e);
  $('#readout').innerHTML =
    `<span class="warn">Something went wrong: ${escape2(e.message || e)}.</span>` +
    `<br>Your data is safe — nothing has been changed. Try a different design, ` +
    `or reload the page.`;
}
const escape2 = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
