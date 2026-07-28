// The person panel: who they are, who they are connected to, what you know.
//
// The layout is docs/DATA_ENTRY_UI.md, Screen 1. The part that matters most
// is that CHILDREN ARE GROUPED UNDER THE PARTNER THEY BELONG TO — that is
// where somebody discovers, without being taught anything, that they have
// half-brothers and sisters.
//
// Read then edit in place; no separate edit mode, and no Save button beyond
// the one that writes immediately. There is no unsaved state to protect.
import { get, post } from './api.js';
import { addPerson, retire } from './edit.js';

export async function show(host, pid, hooks) {
  const d = await get('person', { id: pid });
  const { onSelect, onSubject, onChanged, onToast } = hooks;

  const parentSexes = new Set(d.parents.map(p => p.sex));
  const room = 2 - d.parents.length;

  host.innerHTML = `
    <div class="who">
      <h3>${esc(d.name) || '<em>no name yet</em>'}
        <button class="icon" id="editBtn" title="Edit name and dates">✎</button></h3>
      <p class="life">${esc(d.life || 'dates unknown')}${d.age ? ' · lived ' + esc(d.age) : ''}</p>
      ${d.relationship ? `<span class="rel">${esc(d.relationship)}</span>` : ''}
      ${d.is_subject ? '<span class="rel me">this is you</span>' : ''}
      ${d.on_thread && !d.is_subject ? '<span class="rel">on your bloodline</span>' : ''}
    </div>

    <form class="details" id="details" hidden>
      <label>Given names <input id="fGiven" value="${esc(d.given)}"></label>
      <label>Surname <input id="fSur" value="${esc(d.surname)}"></label>
      <label>Born <input id="fBirth" value="${esc(d.birth)}"
        placeholder="1834, abt 1834, 12 Mar 1841…"><small class="echo" id="eB"></small></label>
      <label>Died <input id="fDeath" value="${esc(d.death)}"><small class="echo" id="eD"></small></label>
      <label>Born in <input id="fPlace" value="${esc(d.birth_place)}"></label>
      <button class="primary wide" id="saveBtn">Save</button>
    </form>
    <div id="warnBox" class="warnBox" hidden></div>

    <h4>Family</h4>

    <div class="group">
      <h5>Parents</h5>
      ${d.parents.length ? list(d.parents) : '<p class="none">Nobody recorded yet.</p>'}
      ${room > 0 && !parentSexes.has('M') ? btn('father', '+ Add father') : ''}
      ${room > 0 && !parentSexes.has('F') ? btn('mother', '+ Add mother') : ''}
      ${room > 0 && parentSexes.has('M') && parentSexes.has('F')
        ? btn('mother', '+ Add another parent') : ''}
    </div>

    <div class="group">
      <h5>Partners</h5>
      ${d.families.filter(f => f.partner).map(f =>
        `<div class="kinrow"><button data-kin="${esc(f.partner.id)}">${esc(f.partner.name)}</button>
          <small>${esc(f.partner.life || '')} · ${kids(f.children.length)}</small></div>`
      ).join('') || '<p class="none">Nobody recorded yet.</p>'}
      ${btn('partner', '+ Add a partner')}
    </div>

    <div class="group">
      <h5>Children</h5>
      ${d.families.length ? d.families.map(f => `
        <div class="family">
          <h6>${f.partner ? 'with ' + esc(f.partner.name) : 'with someone not recorded'}</h6>
          ${f.children.length ? list(f.children) : '<p class="none">No children recorded.</p>'}
          ${btn('child', '+ Add a child', f.union_id)}
          ${f.partner ? '' : btn('partner', '+ Add the other parent', f.union_id)}
        </div>`).join('')
        : `<p class="none">No children recorded.</p>${btn('child', '+ Add a child')}`}
    </div>

    <div class="group">
      <h5>Brothers and sisters</h5>
      ${d.siblings.length ? d.siblings.map(s =>
        `<div class="kinrow"><button data-kin="${esc(s.id)}">${esc(s.name)}</button>
          <small>${esc(s.life || '')}${s.kind === 'half-sibling' ? ' · half' : ''}</small></div>`
      ).join('') : '<p class="none">Nobody recorded yet.</p>'}
      ${btn('sibling', '+ Add a brother or sister')}
    </div>

    <h4>Facts</h4>
    <table class="facts">${d.events.map(e => `<tr>
      <td>${esc(e.type.replace(/_/g, ' '))}</td>
      <td><span class="conf c${e.confidence}" title="confidence ${e.confidence}"></span>
        ${esc(e.date || '—')}${e.place ? '<br><small>' + esc(e.place) + '</small>' : ''}
        ${e.desc ? '<br>' + esc(e.desc) : ''}
        ${e.citations ? '' : '<br><small class="none">no source recorded</small>'}
      </td></tr>`).join('') || '<tr><td colspan=2 class="none">Nothing recorded yet.</td></tr>'}
    </table>

    <div class="group actions">
      ${d.is_subject ? '' : '<button class="ghost wide" id="subjBtn">Make this person “me”</button>'}
      <button class="ghost wide danger" id="retireBtn">Remove from tree</button>
    </div>`;

  // ---- walking around ----------------------------------------------------
  host.querySelectorAll('[data-kin]').forEach(b =>
    b.addEventListener('click', () => onSelect(b.dataset.kin)));

  // ---- every + Add button opens the one dialogue --------------------------
  host.querySelectorAll('[data-add]').forEach(b =>
    b.addEventListener('click', () => addPerson({
      to: pid, as: b.dataset.add, union: b.dataset.union || null,
      toName: d.given || d.name, toSurname: d.surname, toSex: d.sex,
    }, (newId, info = {}) => {
      if (info.warnings && info.warnings.length) onToast(info.warnings.join(' '), 'warn');
      onChanged();
      if (!info.keepOpen) onSelect(pid);
    })));

  // ---- editing in place ---------------------------------------------------
  const $ = s => host.querySelector(s);
  $('#editBtn').addEventListener('click', () => {
    const f = $('#details');
    f.hidden = !f.hidden;
    if (!f.hidden) $('#fGiven').focus();
  });
  if (!d.name.trim()) $('#details').hidden = false;

  for (const [field, out] of [['#fBirth', '#eB'], ['#fDeath', '#eD']]) {
    $(field).addEventListener('input', debounce(async e => {
      const v = e.target.value.trim();
      $(out).textContent = v ? (await get('date', { q: v })).text : '';
    }, 180));
  }

  $('#details').addEventListener('submit', e => e.preventDefault());
  $('#saveBtn').addEventListener('click', async ev => {
    ev.preventDefault();
    ev.target.textContent = 'Saving…';
    const r = await post('person', {
      id: pid,
      given: $('#fGiven').value.trim(), surname: $('#fSur').value.trim(),
      birth: $('#fBirth').value.trim(), death: $('#fDeath').value.trim(),
      birth_place: $('#fPlace').value.trim(),
    });
    ev.target.textContent = 'Saved';
    // Soft validation: say it, do not refuse it. People enter what the
    // record says and correct it later.
    if (r.warnings && r.warnings.length) {
      const w = $('#warnBox');
      w.hidden = false;
      w.innerHTML = r.warnings.map(x => `<p>${esc(x)}</p>`).join('');
    }
    onChanged();
    setTimeout(() => onSelect(pid), 400);
  });

  if ($('#subjBtn')) $('#subjBtn').addEventListener('click', async () => {
    await post('subject', { id: pid });
    onSubject(pid);
  });
  $('#retireBtn').addEventListener('click', () =>
    retire(pid, d.name, msg => { onToast(msg); onChanged(); onSelect(pid); }));
}

const list = rows => '<div class="kin">' + rows.map(r =>
  `<div class="kinrow"><button data-kin="${esc(r.id)}">${esc(r.name)}</button>
    <small>${esc(r.life || '')}</small></div>`).join('') + '</div>';

const btn = (as, label, union) =>
  `<button class="addlink" data-add="${as}"${union ? ` data-union="${esc(union)}"` : ''}>${label}</button>`;

const kids = n => n === 0 ? 'no children' : n === 1 ? '1 child' : `${n} children`;

function debounce(fn, ms) {
  let t = null;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
