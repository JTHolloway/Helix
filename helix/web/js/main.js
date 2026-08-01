// Helix front end.
//
// Design rule for this file: the person using it should never have to know
// what a "render plan" is. Controls are named for what they do, the preview
// updates as you move them, and nothing is ever lost by experimenting.
import { get, post, svgUrl } from './api.js';
import { draw } from './canvas.js';
import { attach } from './zoom.js';
import * as inspector from './inspector.js';
import * as profile from './profile.js';
import * as relatives from './relatives.js';
import { addPerson as addFirstPerson } from './edit.js';
import * as insight from './insight.js';
import * as librarypanel from './librarypanel.js';
import * as narrow from './narrow.js';

const $ = s => document.querySelector(s);
const wrap = $('#canvasWrap'), host = $('#canvas');
const view = attach(wrap, host);

let META = null, PLAN = null, SEL = null, WHATIF = false, TIMER = null;

// EXPLORE or BUILD. Two windows onto the same family, and the split is not
// cosmetic: reading a family and building one ask different questions, and
// the reading half has to be safe to hand to somebody who is not going to be
// careful with it. Explore is the default because most of the time, most
// people are reading.
let MODE = 'explore';

const S = {                       // everything the preview depends on
  // THE FLAGSHIP, and the default everywhere else in the program: one cell
  // per couple, one ring per generation, founders at the centre. The window
  // opened on `radial_rings` -- the older one-slot-per-person layout -- so
  // the design every other part of this program is written around was one
  // the person had to go and find.
  design: 'radial_family', style: '', gens: '5', focus: 'bloodline',
  tpl: '{given_first} {surname}', cmode: 'none', redact: false,
  threadOn: true, w: 1000, h: 1000, inner: 110, gamma: 50, timeScale: true,
  rings: true, fsize: 34, lw: 45, conn: 'orthogonal', start: -90, sweep: 360,
  pitch: 25, entrygap: 0, cluster: 0, orient: 'tangential', marr: true,
  sibgap: 10, famgap: 60, cellcap: 12,
  leaf: 'auto', wedges: true, wedgeop: 13, clock: false,
  // HOW FAR THE TREE SPREADS, by relation. Sent with every plan request, so
  // narrowing re-runs the whole layout rather than hiding branches -- see
  // `LayoutSettings.kin`.
  kin: { married_in: true }
};

// ─────────────────────────────────────────────────────────────── boot ────
init().catch(fail);

async function init() {
  META = await get('meta');
  $('#proj').textContent = META.title || '';
  inspector.setKinds(META.union_kinds);
  inspector.setVocab(META.fact_kinds, META.confidence);
  buildGallery();
  wireControls();
  wireSearch();
  wireExport();
  wireKeys();
  wirePeopleList();
  wireMode();
  wireScope();
  wirePrint();
  wireGaps();
  wireImport();
  wireInsight();
  wireLibrary();
  wireRelate();
  wireSources();
  wireTools();
  narrow.wire({ onClose: () => view.refit() });
  undoLabels();
  await Promise.all([refresh(), loadRelatives(), loadGaps()]);
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
  // An empty file has nobody to stand on, so there is nothing to click and
  // no chart to draw. Offer the one thing that can happen next.
  if (!META.stats.people) { showEmptyState(); return; }
  $('#empty').hidden = true;
  $('#loading').hidden = false;
  try {
    PLAN = await get('plan', params());
    draw(host, PLAN);
    host.querySelectorAll('[data-p]').forEach(n => {
      n.addEventListener('click', ev => { ev.stopPropagation(); select(n.dataset.p); });
      n.addEventListener('pointerenter', () => WHATIF && whatIf(n.dataset.p));
    });
    if (SEL) markSelected();
    if (MODE === 'explore' && SEL) showProfile(SEL);
    // The chart that has just been drawn is a different size from the one
    // it replaced -- narrowing takes a third of the family off it. Refit,
    // unless the person has chosen a view of their own.
    view.refit();
    readout();
  } catch (e) { fail(e); } finally { $('#loading').hidden = true; }
}

function showEmptyState() {
  $('#loading').hidden = true;
  $('#empty').hidden = false;
  host.innerHTML = '';
  $('#readout').textContent = '';
  const b = $('#firstPerson');
  if (b.dataset.wired) return;
  b.dataset.wired = '1';
  b.addEventListener('click', () => addFirstPerson({
    to: null, as: null, toName: '', toSurname: '', toSex: 'U',
  }, async (id) => {
    await post('subject', { id });          // the first person is you
    META = await get('meta');
    await refresh();
    select(id);
    undoLabels();
  }));
}

function params() {
  return {
    design: S.design, style: S.style, gens: S.gens, focus: S.focus,
    kin: JSON.stringify(S.kin),
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
    's.layout.sibling_gap_cells': (S.sibgap / 100).toFixed(2),
    's.layout.family_gap_cells': (S.famgap / 100).toFixed(2),
    's.layout.max_cell_deg': S.cellcap,
    's.couple.leaf': S.leaf,
    's.family.wedges': S.wedges,
    's.family.wedge_opacity': (S.wedgeop / 100).toFixed(2),
    's.labels.orientation': S.orient,
    's.marriage.show': S.marr,
    's.labels.lines': JSON.stringify(S.tpl.split('|').filter(Boolean)),
    's.labels.show': S.tpl ? true : false,
    's.type.size_mm': (S.fsize / 10).toFixed(2),
    's.connectors.width_mm': (S.lw / 100).toFixed(2),
    's.connectors.style': S.conn,
    's.colour.mode': S.cmode,
    's.thread.enabled': S.threadOn,
    's.fab.clock': S.clock
  };
}

// Both of these were CALLED but never defined, so the fit report never
// appeared and the saved indicator never updated — every refresh threw a
// ReferenceError before it got as far as drawing the readout.
function showFit(fit, hidden) {
  const box = $('#fit');
  if (!fit) { box.innerHTML = ''; return; }
  const ok = fit.fits !== false;
  box.innerHTML =
    `<b class="${ok ? 'ok' : 'warn'}">${ok ? 'Fits the panel' : 'Too big for the panel'}</b>` +
    (fit.required_mm ? `<br>needs ${Math.round(fit.required_mm)} mm across` : '') +
    (fit.panel_mm ? ` of ${Math.round(fit.panel_mm)} mm` : '') +
    (fit.ring_pitch_mm ? `<br>rings ${fit.ring_pitch_mm} mm apart` : '') +
    (fit.pitch_ok === false ? `<br><span class="warn">the rings are tighter
       than the text needs</span>` : '') +
    (hidden ? `<br><span class="warn">${hidden} names left off — make it bigger,
       show fewer generations, or shorten the label.</span>` : '');
}

async function status() {
  try {
    const st = await get('status');
    const el = $('#saved');
    el.textContent = 'Saved';
    el.title = `${st.people} people · ${st.size_kb} KB · last written ` +
      `${st.modified.replace('T', ' ')} · ${st.backups} backups` +
      (st.problems && st.problems.length ? ` · ${st.problems.length} problems` : '');
  } catch { /* an empty file has no status worth showing */ }
}

function readout() {
  const m = PLAN.meta, n = m.extra?.labels_hidden || 0;
  showFit(m.extra?.fit, n);
  const el = m.extra?.elided;
  $('#readout').innerHTML =
    `<b>${m.people}</b> people · ${m.generations} generations · ` +
    `${m.year_min}–${m.year_max} · ${S.w}×${S.h} mm` +
    (el && el.marriages
      ? `<br><span class="warn">${el.people} more not shown on
         ${el.marriages} ${el.marriages === 1 ? 'family' : 'families'}</span>
         <button class="link" id="findPruned">show me where</button>` : '') +
    (n ? `<br><span class="warn">${n} names did not fit.</span>`
       : `<br><span class="ok">Every name fits.</span>`);
  // "LOOK FOR THE ⊥ MARKS" IS NOT AN INSTRUCTION ANYBODY CAN FOLLOW. At the
  // zoom where a whole chart fits on a screen the marks are two pixels
  // long, and the sentence was asking somebody to hunt for them. This makes
  // the chart point at them instead.
  const find = $('#findPruned');
  if (find) find.addEventListener('click', () => {
    const marks = host.querySelectorAll('[data-role="elided"]');
    if (!marks.length) return;
    view.fit();
    marks.forEach(x => x.classList.add('findme'));
    setTimeout(() => marks.forEach(x => x.classList.remove('findme')), 4000);
    toast(`${marks.length} ${marks.length === 1 ? 'family has' : 'families have'}
      children left off — each one is marked with a ⊥ on the chart.`);
  });
}

// ───────────────────────────────────────────────────────────── gallery ───
function buildGallery() {
  const g = $('#gallery');
  GALLERY_V = (META.stats.people || 0) + ':' + (META.subject || '');
  g.innerHTML = '';
  // TWENTY DESIGNS, ALL OF WHICH DRAW. Six of them were registered and
  // never implemented: they sat in the gallery indistinguishable from the
  // rest and threw an error when clicked, and `built` is what stopped that.
  // It is kept — a design that is added and not finished should fall into
  // the plan list rather than into the user's hands — but the list below is
  // empty now, so the panel hides itself.
  const ready = META.designs.filter(d => d.built !== false);
  const planned = META.designs.filter(d => d.built === false);
  for (const d of ready) {
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
  $('#designBlurb').textContent =
    META.designs.find(d => d.key === S.design)?.blurb || '';

  const box = $('#planned');
  if (box) {
    box.hidden = !planned.length;
    box.innerHTML = planned.length
      ? `<summary>${planned.length} more designs are specified, not built
           yet</summary><ul>${planned.map(d =>
          `<li><b>${d.name}</b> ${d.blurb}</li>`).join('')}</ul>` : '';
  }
}

// THE THUMBNAIL IS THE DESIGN, run on YOUR family, at 120 pixels.
//
// It used to be a hand-drawn icon per design, and there were eleven of them
// for twenty designs — so nine showed a sunburst whatever they actually
// drew, and two more had drifted from the geometry they were meant to
// illustrate. A picture of a chart cannot go out of date.
//
// Lazily loaded, so opening Build does not render twenty layouts at once,
// and re-fetched when the family changes.
function thumb(key) {
  return `<img loading="lazy" alt="" src="/api/thumb?design=${
    encodeURIComponent(key)}&v=${GALLERY_V}">`;
}

let GALLERY_V = 0;

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
  bind('sibgap', 'sibgap', v => v <= 15 ? 'close together'
    : v <= 40 ? 'a little apart' : 'well spread');
  bind('famgap', 'famgap', v => (v / 100).toFixed(2) + ' of a cell');
  bind('cellcap', 'cellcap', v => v + '\u00b0 — a sparse family draws as a fan');
  bind('leaf', 'leaf'); bind('wedges', 'wedges');
  bind('clock', 'clock');
  $('#material').addEventListener('change', () => {
    if ($('#preflight').innerHTML.trim()) preflight();
  });
  bind('wedgeop', 'wedgeop',
    v => v == 0 ? 'off' : (v / 100).toFixed(2)
      + (v > 20 ? ' — muddy where families overlap' : ''));
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
  narrow.chose();          // on a phone the drawer is over the answer
  relatives.mark($('#kinList'), pid);
  if (MODE === 'explore') return showProfile(pid);
  await inspector.show($('#inspector'), pid, {
    onSelect: select,
    onSubject: async () => { META = await get('meta'); refresh(); },
    onChanged: async () => {
      META = await get('meta'); await loadRelatives(); refresh(); undoLabels();
    },
    onToast: toast,
  });
}

async function showProfile(pid) {
  await profile.show($('#inspector'), pid, {
    onSelect: select,
    onToast: toast,
    onHighlight: paintHalo,
    onEdit: p => { setMode('build'); select(p); },
    onRelate: p => { $('#relateDlg').showModal(); RELATE.open(p, ''); },
    onChanged: async () => {
      META = await get('meta'); await loadRelatives(); refresh();
    },
  });
}

// ─────────────────────────────────────────────── explore vs build ────────
function setMode(next) {
  MODE = next;
  document.body.dataset.mode2 = next;
  $('#exploreBtn').classList.toggle('on', next === 'explore');
  $('#buildBtn').classList.toggle('on', next === 'build');
  $('#exploreBtn').setAttribute('aria-pressed', next === 'explore');
  $('#buildBtn').setAttribute('aria-pressed', next === 'build');
  $('#kin').hidden = next !== 'explore';
  $('#left').hidden = next !== 'build';
  if (next === 'build') clearHalo();
  if (SEL) select(SEL);
}

function wireMode() {
  $('#exploreBtn').addEventListener('click', () => setMode('explore'));
  $('#buildBtn').addEventListener('click', () => setMode('build'));
  setMode('explore');
}

// ───────────────────────────────────── who is lit up on the chart ────────
//
// A halo, not a repaint. Everything keeps its own colour and gains a ring,
// so the chart still reads as the chart while it is answering a question.
function paintHalo(sets, centre) {
  clearHalo();
  host.querySelectorAll(`[data-p="${CSS.escape(centre)}"]`)
      .forEach(n => n.classList.add('kin-centre'));
  for (const [group, ids] of Object.entries(sets || {})) {
    if (!profile.HALO.some(([k]) => k === group)) continue;
    for (const id of ids) {
      host.querySelectorAll(`[data-p="${CSS.escape(id)}"]`)
          .forEach(n => { n.classList.add('kin-lit'); n.dataset.kinGroup = group; });
    }
  }
}

function clearHalo() {
  host.querySelectorAll('.kin-lit,.kin-centre').forEach(n => {
    n.classList.remove('kin-lit', 'kin-centre');
    delete n.dataset.kinGroup;
  });
}

// ───────────────────────────────────────────── the relatives sidebar ─────
async function loadRelatives() {
  try {
    await relatives.load();
    drawRelatives();
  } catch { /* an empty file has no relatives to list */ }
}

function drawRelatives() {
  loadGaps();
  relatives.draw($('#kinList'), {
    selected: SEL,
    onSelect: pid => { setMode('explore'); select(pid); },
    onScope: (total, shown) => {
      const on = PLAN ? PLAN.meta.people : shown;
      const el = PLAN?.meta?.extra?.elided;
      $('#kinCount').innerHTML =
        `<b>${on}</b> of ${total} people on the chart` +
        (el && el.marriages
          ? `<br><span class="warn">${el.people} left off, marked on
             ${el.marriages} ${el.marriages === 1 ? 'family' : 'families'}</span>`
          : '');
    },
  });
}

// ────────────────────────────────────────────── where to look next ──────
//
// THE SAME PEOPLE AS THE CHART. Ask for the gaps while looking at a chart
// narrowed to first cousins and you get the gaps on that chart; a research
// list about somebody who is not on screen is a list nobody acts on.
let GAPN = 6, GAPKIND = '';

async function loadGaps() {
  const box = $('#gapList'), head = $('#gapHead');
  if (!box) return;
  try {
    const d = await get('gaps', {
      focus: S.focus, kin: JSON.stringify(S.kin), limit: GAPN,
      kind: GAPKIND,
    });
    head.textContent = d.summary.headline + '.';
    // ONE KIND OF JOB AT A TIME. Ranked purely by score a blood ancestor's
    // missing birth year always beats a whole in-law family nobody has
    // begun, so that job would never be seen. These pick it out.
    $('#gapKinds').innerHTML = [{ key: '', label: 'Everything', n: d.all_total }]
      .concat(d.groups).map(g => `<button class="chip${
        g.key === d.kind ? ' on' : ''}" data-kind="${escAttr(g.key)}"
        >${escAttr(g.label)} <b>${g.n}</b></button>`).join('');
    $('#gapKinds').querySelectorAll('[data-kind]').forEach(b =>
      b.addEventListener('click', () => {
        GAPKIND = b.dataset.kind; GAPN = 6; loadGaps();
      }));
    box.innerHTML = d.gaps.map(g => `<li>
      <button class="gapq" data-p="${escAttr(g.pid)}">${escAttr(g.question)}</button>
      <p class="who">${[g.relation, g.life].filter(Boolean).map(escAttr).join(' · ')}</p>
      <p class="why">${escAttr(g.why)}</p>
      ${g.where.length ? `<ul class="where"><li>${escAttr(g.where[0])}</li></ul>` : ''}
    </li>`).join('') || '<li class="none">Nothing of that kind left.</li>';
    box.querySelectorAll('.gapq').forEach(b =>
      b.addEventListener('click', () => { setMode('explore'); select(b.dataset.p); }));
    const more = $('#gapMore');
    more.hidden = d.total <= d.shown;
    more.textContent = `Show more (${d.total - d.shown} left)`;
  } catch { head.textContent = 'Nothing to look up yet.'; }
}

function wireGaps() {
  const more = $('#gapMore');
  if (!more) return;
  more.addEventListener('click', () => { GAPN += 12; loadGaps(); });
}

// ─────────────────────────────────────────────── somebody else's tree ────
//
// REPORTED BEFORE ANYTHING IS WRITTEN. Nobody's first import is the one
// they meant, and four hundred people added by mistake is not a thing to
// discover afterwards. The dry run reads the file, says what is in it, and
// writes nothing; only the second button touches the family file.
function wireImport() {
  const dlg = $('#importDlg'), input = $('#impFile'), drop = $('#impDrop');
  const report = $('#impReport'), actions = $('#impActions');
  if (!dlg) return;
  let pending = null;

  $('#importBtn').addEventListener('click', () => {
    report.hidden = true; actions.hidden = true; pending = null;
    input.value = '';
    dlg.showModal();
  });
  input.addEventListener('change', () => look(input.files[0]));
  drop.addEventListener('dragover', ev => {
    ev.preventDefault(); drop.classList.add('over');
  });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', ev => {
    ev.preventDefault(); drop.classList.remove('over');
    look(ev.dataTransfer.files[0]);
  });

  async function look(file) {
    if (!file) return;
    report.hidden = false;
    report.innerHTML = `<p>Reading ${escAttr(file.name)}…</p>`;
    actions.hidden = true;
    let data;
    try {
      data = await new Promise((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(r.result);
        r.onerror = () => rej(new Error('That file could not be read.'));
        r.readAsDataURL(file);
      });
    } catch (e) { report.innerHTML = `<p class="warn">${escAttr(e.message)}</p>`; return; }
    pending = { filename: file.name, data };
    try {
      const r = await post('import', { ...pending, dry_run: true });
      report.innerHTML = summarise(r, file);
      actions.hidden = false;
    } catch (e) {
      report.innerHTML = `<p class="warn">${escAttr(e.message)}</p>`;
      pending = null;
    }
  }

  function summarise(r, file) {
    const bits = [`<p><b>${escAttr(file.name)}</b> — ${
      r.kind === 'gedcom' ? `GEDCOM, read as ${escAttr(r.encoding)}`
                          : 'a spreadsheet'}</p>`];
    bits.push(`<ul>
      <li><b>${r.people || 0}</b> people</li>
      ${r.families ? `<li><b>${r.families}</b> families</li>` : ''}
      ${r.sources ? `<li><b>${r.sources}</b> sources</li>` : ''}
      ${r.placeholders ? `<li><b>${r.placeholders}</b> mentioned but not
        listed — they will be added as people to fill in later</li>` : ''}
    </ul>`);
    if (r.unmapped && r.unmapped.length) {
      bits.push(`<p class="hint">Columns with nowhere to go, kept in each
        person's notes: ${r.unmapped.map(escAttr).join(', ')}</p>`);
    }
    for (const x of (r.problems || []).slice(0, 6)) {
      bits.push(`<p class="warn">${escAttr(x)}</p>`);
    }
    return bits.join('');
  }

  $('#impGo').addEventListener('click', async () => {
    if (!pending) return;
    $('#impGo').disabled = true;
    $('#impGo').textContent = 'Adding…';
    try {
      const r = await post('import', { ...pending, dry_run: false });
      dlg.close();
      toast(`Added ${r.people} people. Press Ctrl-Z if that was not what you wanted.`);
      META = await get('meta');
      await Promise.all([refresh(), loadRelatives()]);
      undoLabels();
      // THE MOMENT DUPLICATES MATTER. Four hundred people just arrived in
      // one step and nothing was checked against what was already there.
      const dup = await get('duplicates', { limit: 40 });
      if (dup.pairs.length) reviewDuplicates();
    } catch (e) {
      report.innerHTML += `<p class="warn">${escAttr(e.message)}</p>`;
    } finally {
      $('#impGo').disabled = false;
      $('#impGo').textContent = 'Add these people to my file';
    }
  });
}

// ───────────────────────────────────────── the whole file, not one person ──
function wireInsight() {
  $('#timelineBtn').addEventListener('click', async () => {
    $('#tlDlg').showModal();
    try {
      await insight.showFamilyTimeline($('#tlBody'), {
        onSelect: pid => { $('#tlDlg').close(); setMode('explore'); select(pid); },
        scope: { focus: S.focus, kin: JSON.stringify(S.kin) },
      });
    } catch (e) { $('#tlBody').innerHTML = `<p class="warn">${escAttr(e.message)}</p>`; }
  });
  $('#statsBtn').addEventListener('click', async () => {
    $('#statsDlg').showModal();
    try {
      await insight.showStats($('#statsBody'), pid => {
        $('#statsDlg').close(); setMode('explore'); select(pid);
      });
    } catch (e) { $('#statsBody').innerHTML = `<p class="warn">${escAttr(e.message)}</p>`; }
  });
}

// HOW ARE THESE TWO RELATED? Built once and reopened, so the two names stay
// where you left them -- comparing a run of people against the same one is
// the ordinary way this gets used.
let RELATE = null;
function wireRelate() {
  RELATE = insight.relateScreen($('#relBody'), {
    people: () => (META ? META.people : []),
    onSelect: pid => { $('#relateDlg').close(); setMode('explore'); select(pid); },
  });
  $('#relateBtn').addEventListener('click', () => {
    $('#relateDlg').showModal();
    // Whoever is on screen is nearly always one of the two.
    RELATE.open(SEL || META?.subject || '', '');
  });
}

// Offered rather than forced. Duplicates are rare while you type and
// ordinary after an import, so this is where it is put in front of you --
// but merging is never automatic, because which of two records is right is
// a judgement about somebody's research.
async function reviewDuplicates() {
  $('#dupeDlg').showModal();
  $('#dupeHead').textContent = '';
  try {
    await insight.showDuplicates($('#dupeBody'), $('#dupeHead'), {
      onSelect: pid => { $('#dupeDlg').close(); setMode('explore'); select(pid); },
      onToast: toast,
      onChanged: async () => {
        META = await get('meta');
        await Promise.all([refresh(), loadRelatives()]);
        undoLabels();
      },
    });
  } catch (e) {
    $('#dupeBody').innerHTML = `<p class="warn">${escAttr(e.message)}</p>`;
  }
}

// ────────────────────────────────────────── which family, and where ──────
function wireLibrary() {
  const dlg = $('#libDlg');
  if (!dlg) return;
  $('#libBtn').addEventListener('click', () => {
    dlg.showModal();
    librarypanel.show($('#libBody'), {
      onToast: toast,
      // OPENING ANOTHER FAMILY REBUILDS EVERYTHING. The chart, the sidebar,
      // the research list and the selection all describe one file; left as
      // they were, half the window would still be showing the family you
      // just closed.
      onOpened: async () => {
        dlg.close();
        SEL = null;
        $('#right').hidden = true;
        META = await get('meta');
        $('#proj').textContent = META.title || '';
        await Promise.all([refresh(), loadRelatives()]);
        view.fit();
        status();
        undoLabels();
      },
    }).catch(e => {
      $('#libBody').innerHTML = `<p class="warn">${escAttr(e.message)}</p>`;
    });
  });
}

function wireScope() {
  const push = () => { refresh().then(drawRelatives); };
  const num = (el, key) => $(el).addEventListener('change', () => {
    const v = $(el).value;
    if (v === '') delete S.kin[key]; else S.kin[key] = Number(v);
    push();
  });
  num('#kinCousins', 'max_cousin_degree');
  num('#kinRemoved', 'max_removal');
  num('#kinSteps', 'max_steps');
  $('#kinMarried').addEventListener('change', () => {
    S.kin.married_in = $('#kinMarried').checked; push();
  });
  $('#kinFind').addEventListener('input', () => {
    relatives.filter($('#kinFind').value); drawRelatives();
  });
  get('groups').then(gs => {
    const box = $('#kinGroups');
    box.innerHTML = gs.filter(g => g.key !== 'self').map(g =>
      `<label class="check" title="${escAttr(g.blurb)}">
        <input type="checkbox" data-g="${g.key}" checked> ${escAttr(g.title)}</label>`
    ).join('');
    const sync = () => {
      const on = [...box.querySelectorAll('input:checked')].map(i => i.dataset.g);
      const all = box.querySelectorAll('input').length;
      // ALL ON MEANS NO FILTER, not a filter that happens to allow
      // everything: a chart that has never been near this screen must ask
      // for the chart it always was.
      if (on.length === all) delete S.kin.groups;
      else S.kin.groups = ['self', ...on];
      push();
    };
    box.querySelectorAll('input').forEach(i => i.addEventListener('change', sync));
    $('#kinAll').addEventListener('click', () => {
      box.querySelectorAll('input').forEach(i => { i.checked = true; });
      sync();
    });
  }).catch(() => {});
}

// PRINTING, and the difference between the two kinds of paper.
//
// An OFFICIAL RECORD is filed and read in thirty years: it states what is
// known and marks what is not, and nothing on it is arithmetic over today's
// file. A PROFILE is everything on screen — the DNA percentages, where the
// family came from, the little bloodline tree, what is still to find out —
// which is working material and goes stale the week after it is printed.
//
// Both are wanted and they are not the same document, so both are offered
// and the buttons say which is which.
function wirePrint() {
  const dlg = $('#printDlg');
  $('#printBtn').addEventListener('click', () => {
    // The person half only appears when there is a person.
    const who = SEL && META.people.find(p => p.id === SEL);
    $('#prPerson').hidden = !who;
    if (who) $('#prWho').textContent = who.name;
    dlg.showModal();
  });
  dlg.querySelectorAll('[data-pr]').forEach(b =>
    b.addEventListener('click', () => {
      const q = new URLSearchParams({ focus: S.focus, kin: JSON.stringify(S.kin) });
      const what = b.dataset.pr;
      let url;
      if (what === 'record' || what === 'profile') {
        if (!SEL) { toast('Choose somebody first.'); return; }
        url = `/print/${what}?id=${encodeURIComponent(SEL)}`;
      } else if (what === 'profiles-all') {
        url = '/print/profiles?all=1';
      } else if (what === 'records-all') {
        url = '/print/records?all=1';
      } else if (what === 'chart') {
        // The chart exactly as it is on screen — same design, same
        // narrowing, same size — so the sheet matches the preview.
        url = `/print/chart?${new URLSearchParams(params())}`;
      } else {
        url = `/print/${what}?${q}`;
      }
      dlg.close();
      window.open(url, '_blank');
    }));
}

// EVERY SOURCE IN THE FILE, in one place. A source is the record itself,
// written down once and cited wherever it is used; one cited forty times is
// the spine of the research and worth getting right.
function wireSources() {
  $('#srcBtn').addEventListener('click', async () => {
    $('#srcDlg').showModal();
    try {
      const { sourcesScreen } = await import('./facts.js');
      await sourcesScreen($('#srcBody'), { onToast: toast });
    } catch (e) { $('#srcBody').innerHTML = `<p class="warn">${escAttr(e.message)}</p>`; }
  });
}

// FIND, HOUSEHOLDS, CONTACTS, HISTORY, COMPARE — one dialogue, five tabs.
let TOOLTAB = 'find';
function wireTools() {
  const dlg = $('#toolDlg');
  const open = async (which) => {
    TOOLTAB = which || TOOLTAB;
    const tools = await import('./tools.js');
    $('#toolTabs').innerHTML = tools.TABS.map(([k, label]) =>
      `<button class="tab${k === TOOLTAB ? ' on' : ''}" data-tab="${k}"
        >${label}</button>`).join('');
    $('#toolTitle').textContent =
      (tools.TABS.find(t => t[0] === TOOLTAB) || [])[1] || 'Find';
    $('#toolTabs').querySelectorAll('[data-tab]').forEach(b =>
      b.addEventListener('click', () => open(b.dataset.tab)));
    await tools.show($('#toolBody'), TOOLTAB, {
      onSelect: pid => { dlg.close(); setMode('explore'); select(pid); },
      onToast: toast,
      onChanged: async () => {
        META = await get('meta');
        await Promise.all([refresh(), loadRelatives()]);
        undoLabels();
      },
    });
  };
  $('#toolBtn').addEventListener('click', () => { dlg.showModal(); open(); });
}

function escAttr(s) {
  return String(s ?? '').replace(/[&<>"]/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
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
// THE REAL CHECK, run on the server by `fab/preflight.py` — the module this
// program holds its error messages to, and the one that runs the island
// check. This used to reimplement four rules in JavaScript from the
// on-screen settings, so a chart could pass here and fall apart on the bed.
async function preflight() {
  const rep = $('#preflight');
  rep.innerHTML = '<div>Checking…</div>';
  try {
    const d = await get('preflight',
      { ...params(), material: $('#material').value });
    rep.innerHTML =
      d.findings.map(f => `<div class="${f.level}"><b>${escAttr(f.title)}</b>`
        + (f.detail ? `<br>${escAttr(f.detail)}` : '')
        + (f.fix ? `<br><i>${escAttr(f.fix)}</i>` : '') + '</div>').join('')
      + `<div class="matnote"><b>${escAttr(d.material)}</b><br>${
          escAttr(d.material_note)}</div>`;
  } catch (e) { rep.innerHTML = `<div class="fail">${escAttr(e.message)}</div>`; }
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
      if (kind === 'gedcom') { window.location = '/api/gedcom'; return; }
      // SHARING A TREE THAT NAMES LIVING CHILDREN AND THEIR BIRTHDAYS is
      // the one mistake a genealogy program should not help somebody make
      // silently. Off by default — the export is also how somebody moves
      // their own file — and one click away here.
      if (kind === 'gedcom-safe') {
        window.location = '/api/gedcom?redact=1'; return;
      }
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
    if (k === 't') { $('#threadOn').click(); }
    if (k === 'c') { $('#whatif').click(); }
    if (k === 'z' && !e.ctrlKey && !e.metaKey) view.fit();
    if (k === 'escape') {
      if (document.querySelector('dialog[open]')) return;   // the dialog first
      clearWhatIf(); clearHalo();
      $('#right').hidden = true; SEL = null; markSelected();
    }
    if (k === 'e') setMode('explore');
    if (k === 'b') setMode('build');
    if (k === 'p') { e.preventDefault(); $('#printDlg').showModal(); }
    if (k === '+' || k === '=') view.zoom(1.35);
    if (k === '-') view.zoom(1 / 1.35);
    if (k === 'l') { e.preventDefault(); showPeople(); }
    if (k === 'n') { e.preventDefault(); $('#statsBtn').click(); }
    if (k === 'o') { e.preventDefault(); $('#libBtn').click(); }
    if (k === 't' && !e.shiftKey) { /* thread toggle keeps t */ }
    if (k === 'y') { e.preventDefault(); $('#timelineBtn').click(); }
    if (k === 'i') { e.preventDefault(); $('#importBtn').click(); }
    if (k === 'r') { e.preventDefault(); $('#relateBtn').click(); }
    if (k === 's') { e.preventDefault(); $('#srcBtn').click(); }
    if (k === 'f') { e.preventDefault(); $('#toolBtn').click(); }
  });

  // Undo and redo work while typing too, which is where mistakes happen.
  document.addEventListener('keydown', e => {
    if (!(e.ctrlKey || e.metaKey)) return;
    const k = e.key.toLowerCase();
    if (k === 'z' && !e.shiftKey) { e.preventDefault(); step('undo'); }
    else if (k === 'y' || (k === 'z' && e.shiftKey)) { e.preventDefault(); step('redo'); }
  });
}

// ────────────────────────────────────────────────────── undo and redo ────
async function step(which) {
  const r = await post(which, {});
  toast(r.message || (which === 'undo' ? 'Nothing to undo.' : 'Nothing to redo.'),
        r.ok ? '' : 'warn');
  if (!r.ok) return;
  META = await get('meta');
  await refresh();
  undoLabels();
  if (SEL && META.people.some(p => p.id === SEL)) select(SEL);
  else { $('#right').hidden = true; SEL = null; }
}

async function undoLabels() {
  try {
    const h = await get('history');
    const u = $('#undoBtn'), r = $('#redoBtn');
    if (!u) return;
    u.disabled = !h.undo; r.disabled = !h.redo;
    u.title = h.undo ? `Undo: ${h.undo}  (Ctrl-Z)` : 'Nothing to undo';
    r.title = h.redo ? `Redo: ${h.redo}  (Ctrl-Y)` : 'Nothing to redo';
  } catch { /* an empty file has no history yet */ }
}

let toastTimer = null;
function toast(msg, kind = '') {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast ' + kind;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 5200);
}

// ──────────────────────────────────────────────────── the plain list ─────
let listSort = 'surname';
function wirePeopleList() {
  $('#peopleBtn').addEventListener('click', showPeople);
  $('#undoBtn').addEventListener('click', () => step('undo'));
  $('#redoBtn').addEventListener('click', () => step('redo'));
}

async function showPeople() {
  const rows = await get('people');
  const dlg = $('#listDlg');
  $('#listTitle').textContent = `Everyone in the file — ${rows.length}`;
  const render = () => {
    const key = {
      surname: (a, b) => (a.surname || '~').localeCompare(b.surname || '~') ||
                         (a.given || '').localeCompare(b.given || ''),
      born: (a, b) => (a.born ?? 9e9) - (b.born ?? 9e9),
      complete: (a, b) => a.complete - b.complete,
    }[listSort];
    const sorted = [...rows].sort(key);
    $('#listBody').innerHTML = `
      <table class="people">
        <thead><tr>
          <th><button data-sort="surname">Name</button></th>
          <th><button data-sort="born">Born</button></th>
          <th><button data-sort="complete">How complete</button></th>
        </tr></thead>
        <tbody>${sorted.map(p => `<tr>
          <td><button class="link" data-p="${p.id}">${escape2(p.name) || '—'}</button>
            ${p.is_subject ? '<small> · you</small>' : ''}</td>
          <td>${p.born ?? '<span class="none">—</span>'}</td>
          <td><span class="meter" style="--v:${p.complete}%"
            title="${p.complete}% of the basics filled in"></span></td>
        </tr>`).join('')}</tbody></table>
      <p class="hint">Sorted by ${ {surname:'surname', born:'birth year',
        complete:'how complete the record is'}[listSort] }.</p>`;
    $('#listBody').querySelectorAll('[data-sort]').forEach(b =>
      b.addEventListener('click', () => { listSort = b.dataset.sort; render(); }));
    $('#listBody').querySelectorAll('[data-p]').forEach(b =>
      b.addEventListener('click', () => {
        dlg.close(); select(b.dataset.p); focusOn(b.dataset.p);
      }));
  };
  render();
  dlg.showModal();
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
