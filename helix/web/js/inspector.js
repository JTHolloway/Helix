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
        placeholder="12 March 1841 — or just 1841"><small class="echo" id="eB"></small></label>
      <label>Died <input id="fDeath" value="${esc(d.death)}"
        placeholder="3 Feb 1900 — or just 1900"><small class="echo" id="eD"></small></label>
      <label>Born in <input id="fPlace" value="${esc(d.birth_place)}"></label>
      <button class="primary wide" id="saveBtn">Save</button>
    </form>
    <div id="warnBox" class="warnBox" hidden></div>

    <h4>Family</h4>

    <div class="group">
      <h5>Parents</h5>
      ${d.parents.length ? parentList(d.parents)
                         : '<p class="none">Nobody recorded yet.</p>'}
      ${room > 0 && !parentSexes.has('M') ? btn('father', '+ Add father') : ''}
      ${room > 0 && !parentSexes.has('F') ? btn('mother', '+ Add mother') : ''}
      ${room > 0 && parentSexes.has('M') && parentSexes.has('F')
        ? btn('mother', '+ Add another parent') : ''}
    </div>

    <div class="group">
      <h5>Partners</h5>
      ${d.families.filter(f => f.partner).map(f => `
        <div class="famrow">
          <div class="kinrow">
            <button data-kin="${esc(f.partner.id)}">${esc(f.partner.name)}</button>
            <small>${esc(f.partner.life || '')} · ${kids(f.children.length)}</small>
            <button class="x" data-unpartner="${esc(f.union_id)}"
              data-who="${esc(f.partner.id)}" data-name="${esc(f.partner.name)}"
              title="They were not a couple — take this off">×</button>
          </div>
          <label class="kindpick">Were they married?
            <select data-kind="${esc(f.union_id)}">
              ${kindOptions(f.kind)}
            </select>
          </label>
        </div>`
      ).join('') || '<p class="none">Nobody recorded yet.</p>'}
      ${btn('partner', '+ Add a partner')}
    </div>

    <div class="group">
      <h5>Children</h5>
      ${d.families.length ? d.families.map(f => `
        <div class="family">
          <h6>${f.partner ? 'with ' + esc(f.partner.name) : 'with someone not recorded'}</h6>
          ${f.children.length ? list(f.children, f.union_id) : '<p class="none">No children recorded.</p>'}
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

  // ---- married, or not ----------------------------------------------------
  //
  // Two people with a child between them are a family whether or not they
  // ever married, and until this the program could only say "married". It is
  // recorded on the FAMILY rather than on either person, because it is a
  // fact about the two of them.
  host.querySelectorAll('[data-kind]').forEach(sel =>
    sel.addEventListener('change', async () => {
      const r = await post('union', { action: 'set_kind',
                                      union_id: sel.dataset.kind,
                                      kind: sel.value });
      if (r.error) return onToast(r.error, 'warn');
      onToast(sel.value === 'unmarried'
        ? 'Recorded as a couple who never married. The chart marks the tie '
          + 'between them, and nothing will say they were married.'
        : 'Saved.');
      onChanged();
    }));

  // ---- taking things off again -------------------------------------------
  host.querySelectorAll('[data-unpartner]').forEach(b =>
    b.addEventListener('click', async () => {
      if (!confirm(`Take ${b.dataset.name} off this family?\n\n`
                 + `They stay in your file with everything you know about `
                 + `them — this only says the two were not a couple. `
                 + `Ctrl-Z puts it back.`)) return;
      const r = await post('union', { action: 'remove_partner',
                                      union_id: b.dataset.unpartner,
                                      person_id: b.dataset.who });
      if (r.error) return onToast(r.error, 'warn');
      onToast(`${b.dataset.name} is no longer recorded as a partner. Ctrl-Z undoes it.`);
      onChanged(); onSelect(pid);
    }));
  host.querySelectorAll('[data-unchild]').forEach(b =>
    b.addEventListener('click', async () => {
      if (!confirm(`Take ${b.dataset.name} out of this family?\n\n`
                 + `They stay in your file — this only says these are not `
                 + `their parents. Ctrl-Z puts it back.`)) return;
      const r = await post('union/child', { action: 'detach',
                                            union_id: b.dataset.unchild,
                                            person_id: b.dataset.who });
      if (r.error) return onToast(r.error, 'warn');
      onToast(`${b.dataset.name} is no longer in this family. Ctrl-Z undoes it.`);
      onChanged(); onSelect(pid);
    }));
}

// A PARENT HUNG ON THE WRONG PERSON is the commonest thing to want back,
// and until this there was no way to say so short of deleting them.
const parentList = rows => '<div class="kin">' + rows.map(r =>
  `<div class="kinrow"><button data-kin="${esc(r.id)}">${esc(r.name)}</button>
    <small>${esc(r.life || '')}</small>${r.union_id ? `
    <button class="x" data-unpartner="${esc(r.union_id)}" data-who="${esc(r.id)}"
      data-name="${esc(r.name)}" title="Not their parent — take this off">×</button>`
    : ''}</div>`).join('') + '</div>';

// EVERYTHING THAT CAN BE ADDED CAN BE TAKEN OFF AGAIN, and taking a child
// off a family does not delete the person — it unhooks them, and Ctrl-Z
// hooks them back. Deleting somebody is a separate, deliberate act with its
// own button and its own wording.
const list = (rows, union) => '<div class="kin">' + rows.map(r =>
  `<div class="kinrow"><button data-kin="${esc(r.id)}">${esc(r.name)}</button>
    <small>${esc(r.life || '')}</small>${union ? `
    <button class="x" data-unchild="${esc(union)}" data-who="${esc(r.id)}"
      data-name="${esc(r.name)}"
      title="Not a child of this family — take them off">×</button>` : ''}
  </div>`).join('') + '</div>';

// The kinds of couple, straight from the schema by way of /api/meta, so a
// kind added there appears here without any further wiring.
let KINDS = [{ key: 'marriage', label: 'Married' },
             { key: 'unmarried', label: 'Together, never married' }];
export function setKinds(list) { if (list && list.length) KINDS = list; }
const kindOptions = now => KINDS.map(k =>
  `<option value="${esc(k.key)}"${k.key === (now || 'marriage') ? ' selected' : ''}
    >${esc(k.label)}</option>`).join('')
  + (KINDS.some(k => k.key === now) ? ''
     : `<option value="${esc(now)}" selected>not recorded</option>`);

const btn = (as, label, union) =>
  `<button class="addlink" data-add="${as}"${union ? ` data-union="${esc(union)}"` : ''}>${label}</button>`;

const kids = n => n === 0 ? 'no children' : n === 1 ? '1 child' : `${n} children`;

function debounce(fn, ms) {
  let t = null;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
