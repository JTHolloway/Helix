// Facts, and where they came from.
//
// The panel has boxes for five things — born, died, born in, occupation,
// education — because those are what somebody types on their first evening.
// This is the other half: ANY fact, with a date, a place, a note and a
// confidence, and a source under it.
//
// WHY THE KIND IS A SUGGESTION AND NOT A RULE. `event.type` is a free string
// in the schema and stays one: somebody researching a family of watermen
// needs "apprenticed to the Company of Watermen" and is not going to wait
// for a release. The list is what the panel offers first, in the order a
// life happens; anything else typed in is kept.
//
// WHY THE SOURCE MATTERS MORE THAN THE FACT. A date with no source is a
// rumour somebody typed carefully. The record book asks every person "where
// did this come from?", and until this the program had no way of being told.
import { get, post } from './api.js';

const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

let KINDS = [{ key: 'other', label: 'Something else' }];
let LEVELS = [{ level: 2, label: 'Recorded' }];
export function setVocab(kinds, levels) {
  if (kinds && kinds.length) KINDS = kinds;
  if (levels && levels.length) LEVELS = levels;
}

const kindLabel = k => (KINDS.find(x => x.key === k) || {}).label
  || String(k || '').replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());

// A dot per confidence, the same four the schema has. Shown as a word, not
// a number: a number invites somebody to average them, which is exactly
// what a confidence is not for.
const confWord = n => (LEVELS.find(x => x.level === n) || {}).label || '';

/** The read-only list of facts, with an edit button on each. */
export function factList(events, { unionId = '' } = {}) {
  if (!events || !events.length) {
    return `<p class="none">No facts recorded beyond the boxes above.</p>`;
  }
  return `<ul class="factlist">${events.map(e => `
    <li data-fact="${esc(e.id)}">
      <div class="frow">
        <b>${esc(kindLabel(e.type))}</b>
        <span>${esc([e.date, e.place, e.desc].filter(Boolean).join(' · ')
                    || 'nothing recorded')}</span>
        <button class="link facted" data-edit="${esc(e.id)}"
          data-union="${esc(unionId)}" title="Change this fact">edit</button>
      </div>
      <div class="fmeta">
        <i class="conf c${e.confidence}" title="${esc(confWord(e.confidence))}"></i>
        <span>${esc(confWord(e.confidence))}</span>
        <button class="link cites" data-cite="${esc(e.id)}">${
          e.citations ? `${e.citations} source${e.citations === 1 ? '' : 's'}`
                      : 'no source — add one'}</button>
      </div>
    </li>`).join('')}</ul>`;
}

/** The form for one fact. `ev` is null for a new one. */
export function factForm(ev, { personId = '', unionId = '' } = {}) {
  const v = ev || { type: 'residence', date: '', place: '', desc: '',
                    confidence: 2 };
  const known = KINDS.some(k => k.key === v.type);
  return `<form class="factform" data-person="${esc(personId)}"
      data-union="${esc(unionId)}" data-event="${esc(v.id || '')}">
    <label>What happened
      <select id="fkType">
        ${KINDS.map(k => `<option value="${esc(k.key)}"${
          k.key === v.type ? ' selected' : ''}>${esc(k.label)}</option>`).join('')}
        ${known ? '' : `<option value="${esc(v.type)}" selected>${
          esc(kindLabel(v.type))}</option>`}
      </select>
    </label>
    <label>Or say it in your own words
      <input id="fkOwn" placeholder="apprenticed to a waterman"
        value="${known ? '' : esc(v.type.replace(/_/g, ' '))}">
    </label>
    <label>When <input id="fkDate" value="${esc(v.raw || v.date)}"
      placeholder="12 March 1841 — or just 1841"></label>
    <label>Where <input id="fkPlace" value="${esc(v.place)}"
      placeholder="Frome, Somerset"></label>
    <label>What the record says
      <input id="fkNote" value="${esc(v.desc)}"
        placeholder="Head, cloth weaver, 49"></label>
    <label>How well is it proved
      <select id="fkConf">
        ${LEVELS.map(l => `<option value="${l.level}"${
          l.level === v.confidence ? ' selected' : ''}>${esc(l.label)}</option>`
        ).join('')}
      </select>
    </label>
    <div class="row">
      <button class="primary" id="fkSave">Save this fact</button>
      ${v.id ? '<button class="ghost" id="fkDrop">Take it off</button>' : ''}
      <button class="ghost" id="fkCancel">Cancel</button>
    </div>
  </form>`;
}

/** Wire a form that is already in the DOM. */
export function wireForm(host, { onDone, onToast }) {
  const f = host.querySelector('.factform');
  if (!f) return;
  const $ = s => f.querySelector(s);
  f.addEventListener('submit', e => e.preventDefault());
  $('#fkCancel').addEventListener('click', ev => { ev.preventDefault(); onDone(); });
  $('#fkSave').addEventListener('click', async ev => {
    ev.preventDefault();
    // Their own words win. Somebody who types "apprenticed to a waterman"
    // has said something the list cannot, and dropping it for whatever the
    // select happened to be showing would be the program overruling them.
    const own = $('#fkOwn').value.trim();
    try {
      await post('event', {
        action: 'save',
        id: f.dataset.person || null,
        union_id: f.dataset.union || null,
        event_id: f.dataset.event || null,
        type: own || $('#fkType').value,
        date: $('#fkDate').value.trim(),
        place: $('#fkPlace').value.trim(),
        note: $('#fkNote').value.trim(),
        confidence: +$('#fkConf').value,
      });
      onDone(true);
    } catch (e) { onToast(e.message); }
  });
  if ($('#fkDrop')) $('#fkDrop').addEventListener('click', async ev => {
    ev.preventDefault();
    if (!confirm('Take this fact off?\n\nCtrl-Z puts it back.')) return;
    try {
      await post('event', { action: 'remove', id: f.dataset.person || null,
                            event_id: f.dataset.event });
      onDone(true);
    } catch (e) { onToast(e.message); }
  });
}

// ─────────────────────────── where it came from ───────────────────────────
//
// A SOURCE IS THE THING ITSELF and is written down once: the 1861 census, a
// parish register, a headstone, an aunt. A CITATION is one use of it, with
// the page. Kept apart because the alternative is typing "1861 Census of
// England and Wales" forty times and spelling it four ways.
export async function citeScreen(host, eventId, { onDone, onToast }) {
  const [{ sources }, { citations }] = await Promise.all([
    get('sources'), get('citations', { event_id: eventId })]);

  host.innerHTML = `
    <h4>Where this came from</h4>
    ${citations.length ? `<ul class="citelist">${citations.map(c => `
      <li><b>${esc(c.title)}</b>
        ${[c.repository, c.ref, c.page].filter(Boolean)
            .map(x => `<span>${esc(x)}</span>`).join('')}
        <button class="x" data-drop="${esc(c.id)}" title="Not this one">×</button>
      </li>`).join('')}</ul>`
      : '<p class="none">Nothing yet. A fact with no source cannot be checked.</p>'}

    <form class="citeform">
      <label>Use a source you have already
        <select id="ciPick">
          <option value="">— choose —</option>
          ${sources.map(s => `<option value="${esc(s.id)}">${esc(s.title)}${
            s.uses ? ` (${s.uses})` : ''}</option>`).join('')}
        </select>
      </label>
      <label>Page or reference for this fact
        <input id="ciPage" placeholder="f.71 p.12, entry 96"></label>
      <button class="primary wide" id="ciAdd">Cite it</button>
    </form>

    <details class="newsrc"><summary>Or record a source Helix has not got</summary>
      <form class="srcform">
        <label>What the record is
          <input id="srTitle" placeholder="1861 Census of England and Wales"></label>
        <label>Who holds it
          <input id="srRepo" placeholder="The National Archives"></label>
        <label>Its reference
          <input id="srRef" placeholder="RG 9/1652"></label>
        <label>Web address, if it has one
          <input id="srUrl" placeholder="https://…"></label>
        <button class="primary wide" id="srAdd">Add this source</button>
      </form>
    </details>
    <button class="ghost wide" id="ciDone">Done</button>`;

  const $ = s => host.querySelector(s);
  host.querySelectorAll('[data-drop]').forEach(b =>
    b.addEventListener('click', async () => {
      await post('cite', { action: 'remove', citation_id: b.dataset.drop });
      citeScreen(host, eventId, { onDone, onToast });
    }));
  $('#ciAdd').addEventListener('click', async ev => {
    ev.preventDefault();
    if (!$('#ciPick').value) return onToast('Choose a source first.');
    try {
      await post('cite', { action: 'add', source_id: $('#ciPick').value,
                           event_id: eventId, page: $('#ciPage').value.trim() });
      citeScreen(host, eventId, { onDone, onToast });
      onDone(true);
    } catch (e) { onToast(e.message); }
  });
  $('#srAdd').addEventListener('click', async ev => {
    ev.preventDefault();
    try {
      const r = await post('source', {
        action: 'save', title: $('#srTitle').value.trim(),
        repository: $('#srRepo').value.trim(), ref: $('#srRef').value.trim(),
        url: $('#srUrl').value.trim(),
      });
      // Straight onto the fact that prompted it — nobody records a source
      // for its own sake.
      await post('cite', { action: 'add', source_id: r.source_id,
                           event_id: eventId, page: $('#ciPage').value.trim() });
      citeScreen(host, eventId, { onDone, onToast });
      onDone(true);
    } catch (e) { onToast(e.message); }
  });
  $('#ciDone').addEventListener('click', () => onDone());
}

/** Every source in the file, with how much rests on each. */
export async function sourcesScreen(host, { onToast }) {
  const { sources } = await get('sources');
  host.innerHTML = `
    <p class="hint">A source is the record itself — written down once and
      cited wherever it is used. One cited forty times is the spine of your
      research; one cited never is a note.</p>
    ${sources.length ? `<ul class="srclist">${sources.map(s => `
      <li>
        <b>${esc(s.title)}</b>
        <span>${[s.author, s.repository, s.ref].filter(Boolean)
                 .map(esc).join(' · ') || 'no repository recorded'}</span>
        ${s.url ? `<a href="${esc(s.url)}" target="_blank">${esc(s.url)}</a>` : ''}
        <em>${s.uses} ${s.uses === 1 ? 'fact rests on it' : 'facts rest on it'}</em>
        <button class="x" data-drop="${esc(s.id)}"
          title="Remove this source and every citation of it">×</button>
      </li>`).join('')}</ul>`
      : '<p class="none">No sources recorded yet.</p>'}
    <form class="srcform">
      <h4>Add a source</h4>
      <label>What the record is
        <input id="nsTitle" placeholder="Parish register, St Mary, Frome"></label>
      <label>Who holds it
        <input id="nsRepo" placeholder="Somerset Heritage Centre"></label>
      <label>Its reference <input id="nsRef" placeholder="D\\P\\fr.j/2/1/8"></label>
      <label>Web address <input id="nsUrl" placeholder="https://…"></label>
      <button class="primary wide" id="nsAdd">Add it</button>
    </form>`;
  const $ = s => host.querySelector(s);
  host.querySelectorAll('[data-drop]').forEach(b =>
    b.addEventListener('click', async () => {
      if (!confirm('Remove this source, and every citation of it?\n\n'
                 + 'Ctrl-Z puts it back.')) return;
      await post('source', { action: 'remove', source_id: b.dataset.drop });
      sourcesScreen(host, { onToast });
    }));
  $('#nsAdd').addEventListener('click', async ev => {
    ev.preventDefault();
    try {
      await post('source', { action: 'save', title: $('#nsTitle').value.trim(),
        repository: $('#nsRepo').value.trim(), ref: $('#nsRef').value.trim(),
        url: $('#nsUrl').value.trim() });
      sourcesScreen(host, { onToast });
    } catch (e) { onToast(e.message); }
  });
}
