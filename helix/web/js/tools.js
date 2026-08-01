// The screens that read the whole file and are not about one person.
//
//   Find        one box that takes the filters that were spread over four
//               screens: "whitcombe born:<1850", "no:death", "no:parents"
//   Households  who was in the same place at the same time — how the
//               records are organised, and not a shape the chart can draw
//   Contacts    the living, and how to reach them. A genealogy program is
//               full of the dead and the people using it are surrounded by
//               the living; there was nowhere to put a telephone number
//   History     what has been done to this file, and stepping back to any
//               point in it
//   Compare     a cousin's GEDCOM against yours, fact by fact
//
// All five are one dialogue with a tab bar, because five more buttons in the
// header is how a toolbar becomes a wall.
import { get, post } from './api.js';

const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export const TABS = [
  ['find', 'Find'], ['households', 'Households'], ['contacts', 'Contacts'],
  ['history', 'History'], ['compare', 'Compare'],
];

export async function show(host, which, hooks) {
  host.innerHTML = '<p class="hint">…</p>';
  try {
    if (which === 'find') return findScreen(host, hooks);
    if (which === 'households') return householdScreen(host, hooks);
    if (which === 'contacts') return contactScreen(host, hooks);
    if (which === 'history') return historyScreen(host, hooks);
    if (which === 'compare') return compareScreen(host, hooks);
  } catch (e) {
    host.innerHTML = `<p class="warn">${esc(e.message)}</p>`;
  }
}

// ───────────────────────────────────────────────────────────────── find ───
async function findScreen(host, { onSelect }) {
  const d = await get('find', { q: '' });
  host.innerHTML = `
    <input id="fdQ" type="search" autocomplete="off"
      placeholder="whitcombe born:&lt;1850   ·   no:death   ·   place:somerset">
    <div id="fdOut"></div>
    <details class="fdhelp"><summary>What it understands</summary>
      <table class="fdtable">${d.help.map(h => `<tr>
        <td><code>${esc(h.q)}</code></td><td>${esc(h.what)}</td></tr>`).join('')}
      </table>
      <p class="hint">Everything you put in has to be true at once. There is
        no “or”, on purpose — a query language nobody can remember is one
        nobody uses.</p>
    </details>`;
  const q = host.querySelector('#fdQ'), out = host.querySelector('#fdOut');
  let t = null;
  const run = async () => {
    const r = await get('find', { q: q.value });
    if (!r.terms.length) { out.innerHTML = ''; return; }
    out.innerHTML = `<p class="hint">${r.total} ${
      r.total === 1 ? 'person' : 'people'}${
      r.total > r.people.length ? ` — first ${r.people.length} shown` : ''}</p>
      <ul class="fdlist">${r.people.map(p => `<li>
        <button data-go="${esc(p.id)}"><b>${esc(p.name)}</b>
          <span>${esc(p.life || 'dates unknown')}</span></button>
        <em>${p.why.map(esc).join(' · ')}</em></li>`).join('')}</ul>`;
    out.querySelectorAll('[data-go]').forEach(b =>
      b.addEventListener('click', () => onSelect(b.dataset.go)));
  };
  q.addEventListener('input', () => { clearTimeout(t); t = setTimeout(run, 220); });
  q.focus();
}

// ──────────────────────────────────────────────────────── households ──────
async function householdScreen(host, { onSelect }) {
  const { households } = await get('households');
  host.innerHTML = `
    <p class="hint">Everybody with a record at the same place within a few
      years of each other. Approximate on purpose — it points at “these six
      were in Frome in the 1860s, look at them together”, which is how the
      records are arranged and not how a tree is.</p>
    ${households.length ? households.map(h => `
      <div class="hhold">
        <h4>${esc(h.place)} <span>${esc(h.span)}</span></h4>
        <p class="hint">${h.count} people · ${esc(h.surnames.join(', ')
          || 'no surnames')}</p>
        <div class="kin">${h.people.map(p => `
          <div class="kinrow"><button data-go="${esc(p.id)}">${esc(p.name)}</button>
            <small>${esc(p.life || '')} · ${esc(p.why)}</small></div>`).join('')}
        </div>
      </div>`).join('')
      : '<p class="none">No place is recorded against a dated event yet.</p>'}`;
  host.querySelectorAll('[data-go]').forEach(b =>
    b.addEventListener('click', () => onSelect(b.dataset.go)));
}

// ────────────────────────────────────────────────────────── contacts ──────
async function contactScreen(host, { onSelect, onToast }) {
  const d = await get('contacts');
  host.innerHTML = `
    <p class="hint">The aunt with the photographs, the cousin who has the
      family Bible. Kept as ordinary facts, so they back up, export and undo
      with everything else.</p>
    ${d.people.length ? `<ul class="cbook">${d.people.map(p => `<li>
      <button data-go="${esc(p.id)}"><b>${esc(p.name)}</b>
        <span>${esc(p.life || '')}</span></button>
      ${p.contacts.length
        ? `<div class="cways">${p.contacts.map(c =>
            `<span><i>${esc(c.label)}</i> ${esc(c.value)}</span>`).join('')}</div>`
        : '<em>no way of reaching them recorded</em>'}
    </li>`).join('')}</ul>`
      : '<p class="none">Nobody in this file is recorded as living.</p>'}
    <p class="hint">To add one, open somebody and record a fact of kind
      <b>phone</b>, <b>email</b>, <b>address</b> or <b>website</b>.</p>`;
  host.querySelectorAll('[data-go]').forEach(b =>
    b.addEventListener('click', () => onSelect(b.dataset.go)));
}

// ─────────────────────────────────────────────────────────── history ──────
async function historyScreen(host, hooks) {
  const { onChanged, onToast, onSelect } = hooks;
  const { changes } = await get('history/list');
  host.innerHTML = `
    <p class="hint">Everything that has been done to this file, newest
      first. Ctrl-Z takes back one; this takes back everything down to a
      point, one step at a time, and Ctrl-Y walks it forward again.</p>
    ${changes.length ? `<ol class="hist">${changes.map(c => `<li class="${
      c.undone ? 'undone' : ''}">
      <b>${esc(c.label)}</b>
      <span>${esc((c.at || '').replace('T', ' '))} · ${c.rows} ${
        c.rows === 1 ? 'row' : 'rows'}${c.undone ? ' · taken back' : ''}</span>
      <button class="link" data-what="${esc(c.batch)}">who it changed</button>
      ${c.undone ? '' : `<button class="link" data-back="${esc(c.batch)}"
        >take everything back to here</button>`}
    </li>`).join('')}</ol>`
      : '<p class="none">Nothing has been changed yet.</p>'}`;
  host.querySelectorAll('[data-what]').forEach(b =>
    b.addEventListener('click', () => whatScreen(host, b.dataset.what, hooks)));
  host.querySelectorAll('[data-back]').forEach(b =>
    b.addEventListener('click', async () => {
      if (!confirm('Take back every change made since then?\n\n'
                 + 'Nothing is deleted — Ctrl-Y walks them forward again.')) return;
      try {
        const r = await post('history/revert', { batch: b.dataset.back });
        onToast(r.message);
        onChanged();
        historyScreen(host, hooks);
      } catch (e) { onToast(e.message); }
    }));
}

// ─────────────────────────────────────────────────── what changed ─────────
//
// "IMPORTED 463 PEOPLE" IS NOT A REPORT. It is a number, and it could
// equally be the wrong file. What somebody wants to know afterwards is
// which surnames arrived, what years they cover, and — the only part that
// needs a decision — which of them have nobody above them, because those
// are where the two trees have to be joined by hand.
//
// Read back out of the change log, so it says what happened rather than
// what the importer thought it was doing.
export async function whatScreen(host, batch, hooks, opts = {}) {
  const { onSelect, onToast, onChanged } = hooks;
  host.innerHTML = '<p class="hint">…</p>';
  let d;
  try { d = await get('history/what', { batch }); }
  catch (e) { host.innerHTML = `<p class="warn">${esc(e.message)}</p>`; return; }

  const list = (people, cls) => `<ul class="whatlist ${cls}">${people.map(p =>
    `<li><button data-go="${esc(p.id)}"><b>${esc(p.name)}</b>
      <span>${esc(p.life || 'dates unknown')}</span></button></li>`).join('')}</ul>`;

  // IMPORTING 139 PEOPLE INTO AN EMPTY FILE DREW AN EMPTY CHART. Every
  // relation in this program is measured from one person, so with nobody at
  // the centre there is no tree to draw — and the screen said nothing about
  // why. Asked here rather than guessed at: who the root is is not a
  // preference, it is which document this is.
  const rootAsk = opts.needRoot && d.people.length ? `
    <div class="rootask">
      <h4>Whose tree is this?</h4>
      <p class="hint">Every relation on the chart is measured from one
        person — “my grandmother”, “my second cousin”. Nothing is drawn
        until you say who that is. You can change it later, and doing so
        does not alter anything you have recorded.</p>
      <select id="whRoot">${[...d.people]
        .sort((a, b) => a.name.localeCompare(b.name))
        .map(p => `<option value="${esc(p.id)}">${esc(p.name)}${
          p.life ? ' · ' + esc(p.life) : ''}</option>`).join('')}</select>
      <button class="primary" id="whRootGo">This is the person</button>
    </div>` : '';

  host.innerHTML = `
    <p class="cmphead"><b>${esc(d.label)}</b>
      <span>${esc((d.at || '').replace('T', ' '))}</span></p>
    ${rootAsk}
    <div class="figs">
      <div><b>${d.added}</b><span>added</span></div>
      <div><b>${d.edited}</b><span>changed</span></div>
      <div><b>${d.loose_total}</b><span>with no parents yet</span></div>
      <div><b>${d.rows}</b><span>rows written</span></div>
    </div>
    ${d.years ? `<p class="hint">Born between <b>${d.years[0]}</b> and
      <b>${d.years[1]}</b>.</p>` : ''}
    ${d.surnames.length ? `<h4>Surnames</h4><p class="surnames">${
      d.surnames.slice(0, 14).map(([n, c]) =>
        `<span>${esc(n)} <i>${c}</i></span>`).join('')}</p>` : ''}
    ${d.loose.length ? `<h4>Nobody above them yet</h4>
      <p class="hint">These are where your tree and theirs have to be
        joined. Open one, find who their parents should be, and use
        <b>Link to somebody already here</b>.</p>${list(d.loose, 'loose')}`
      : ''}
    ${d.people.length ? `<h4>Everybody added</h4>${list(d.people, '')}
      ${d.truncated ? `<p class="hint">First ${d.people.length} of
        ${d.added}.</p>` : ''}` : ''}
    ${d.changed && d.changed.length ? `<h4>Already in your file, changed</h4>
      ${list(d.changed, '')}` : ''}
    <div class="row">
      <button class="ghost" id="whBack">Back to the history</button>
      <button class="ghost" id="whUndo">Take this change back</button>
    </div>`;
  host.querySelectorAll('[data-go]').forEach(b =>
    b.addEventListener('click', () => onSelect(b.dataset.go)));
  const rootGo = host.querySelector('#whRootGo');
  if (rootGo) rootGo.addEventListener('click', async () => {
    const id = host.querySelector('#whRoot').value;
    try {
      await post('subject', { id });
      onToast('The chart is now drawn from them. Everything on it is a '
            + 'relation to that person.');
      onChanged();
      whatScreen(host, batch, hooks, {});
    } catch (e) { onToast(e.message); }
  });
  host.querySelector('#whBack').addEventListener('click',
    () => historyScreen(host, hooks));
  host.querySelector('#whUndo').addEventListener('click', async () => {
    if (!confirm(`Take back "${d.label}"?\n\n`
               + 'Nothing is deleted — Ctrl-Y walks it forward again.')) return;
    try {
      const r = await post('history/revert', { batch });
      onToast(r.message);
      onChanged();
      historyScreen(host, hooks);
    } catch (e) { onToast(e.message); }
  });
}

// ──────────────────────────────────────────────────────────── compare ─────
//
// A cousin sends a GEDCOM. Imported blind it doubles the file and buries
// your own research under somebody else's; left unopened it is four hundred
// people you will never look at. THE DISAGREEMENTS ARE THE VALUABLE PART:
// two dates for one birth mean one of you has seen a record the other has
// not.
async function compareScreen(host, { onToast }) {
  host.innerHTML = `
    <p class="hint">Read a cousin's GEDCOM against yours. Nothing is
      changed — this only says what the two files disagree about.</p>
    <label class="drop wide" id="cmpDrop">
      <span>Choose a .ged file, or drop one here</span>
      <input type="file" id="cmpFile" accept=".ged,.gedcom,.helix" hidden>
    </label>
    <div id="cmpOut"></div>`;
  const inp = host.querySelector('#cmpFile');
  const zone = host.querySelector('#cmpDrop');
  const out = host.querySelector('#cmpOut');
  const take = async file => {
    if (!file) return;
    out.innerHTML = '<p class="hint">Reading both files…</p>';
    const data = await new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(r.result); r.onerror = rej;
      r.readAsDataURL(file);
    });
    try {
      draw(await post('compare', { data, filename: file.name }));
    } catch (e) { out.innerHTML = `<p class="warn">${esc(e.message)}</p>`; }
  };
  inp.addEventListener('change', () => take(inp.files[0]));
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('over'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); zone.classList.remove('over'); take(e.dataTransfer.files[0]);
  });

  function draw(d) {
    const c = d.counts;
    const rows = x => `<table class="cmprows">${x.rows.map(r => `<tr>
        <td class="lab">${esc(r.label)}</td>
        <td class="${r.kind === 'gain' ? 'was' : ''}">${esc(r.mine) || '—'}</td>
        <td class="${r.kind === 'loss' ? 'was' : ''}">${esc(r.theirs) || '—'}</td>
      </tr>`).join('')}</table>`;
    out.innerHTML = `
      <p class="cmphead"><b>${esc(d.headline)}</b></p>
      <div class="figs">
        <div><b>${c.matched}</b><span>the same people</span></div>
        <div><b>${c.conflicts}</b><span>you disagree</span></div>
        <div><b>${c.gains}</b><span>one knows more</span></div>
        <div><b>${c.only_theirs}</b><span>you have not got</span></div>
      </div>
      ${c.conflicts ? `<h4>Where you disagree</h4>
        <p class="hint">The valuable part: one of you has seen a record the
          other has not.</p>
        <div class="cmpcols"><span>yours</span><span>${esc(d.theirs_name)}</span></div>
        ${d.conflicts.map(x => `<div class="cmpp"><b>${esc(x.mine.name)}</b>
          <span>${esc(x.mine.life || '')}</span>${rows(x)}</div>`).join('')}` : ''}
      ${c.gains ? `<h4>Where one of you knows more</h4>
        ${d.gains.map(x => `<div class="cmpp"><b>${esc(x.mine.name)}</b>
          <span>${esc(x.mine.life || '')}</span>${rows(x)}</div>`).join('')}` : ''}
      ${c.only_theirs ? `<h4>In theirs and not in yours</h4>
        <ul class="cmpnew">${d.only_theirs.map(p => `<li><b>${esc(p.name)}</b>
          <span>${esc(p.life || '')}${p.parents.length
            ? ' · child of ' + p.parents.map(esc).join(' and ') : ''}</span>
        </li>`).join('')}</ul>
        <p class="hint">To bring them in, close this and use Import — it
          reports before it writes and one Ctrl-Z takes the whole import
          back.</p>` : ''}`;
  }
}
