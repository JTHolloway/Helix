// The person panel. Read, then edit in place; no separate "edit mode".
import { get, post } from './api.js';

export async function show(host, pid, { onSelect, onSubject, onChanged }) {
  const d = await get('person', { id: pid });
  host.innerHTML = `
    <h3>${esc(d.name)}</h3>
    <p class="life">${esc(d.life || 'dates unknown')}${d.age ? ' · lived ' + esc(d.age) : ''}</p>
    ${d.relationship ? `<span class="rel">${esc(d.relationship)}</span>` : ''}
    ${d.on_thread ? '<span class="rel">on your bloodline</span>' : ''}

    <h4>Facts</h4>
    <table>${d.events.map(e => `<tr>
      <td>${esc(e.type.replace(/_/g, ' '))}</td>
      <td><span class="conf c${e.confidence}" title="confidence ${e.confidence}"></span>
        ${esc(e.date || '—')}${e.place ? '<br><small>' + esc(e.place) + '</small>' : ''}
        ${e.desc ? '<br>' + esc(e.desc) : ''}
        ${e.citations ? '' : '<br><small>no source recorded</small>'}
      </td></tr>`).join('') || '<tr><td colspan=2>Nothing recorded yet.</td></tr>'}
    </table>

    <h4>Edit</h4>
    <input class="field" id="fGiven" placeholder="Given names" value="${esc(d.name.split(' ').slice(0,-1).join(' '))}">
    <input class="field" id="fSur" placeholder="Surname" value="${esc(d.name.split(' ').slice(-1)[0] || '')}">
    <input class="field" id="fBirth" placeholder="Born — e.g. 1834, abt 1834, 12 Mar 1841" value="${esc(d.birth)}">
    <input class="field" id="fDeath" placeholder="Died" value="${esc(d.death)}">
    <button class="primary wide" id="saveBtn">Save</button>
    <p class="hint">Dates can be vague: <b>abt 1834</b>, <b>bef 1900</b>,
      <b>bet 1820 and 1825</b>, <b>Q3 1871</b> all work.</p>

    ${kin('Parents', d.parents)}${kin('Partners', d.partners)}${kin('Children', d.children)}
    <h4>Centre the bloodline on</h4>
    <button class="ghost wide" id="subjBtn">Make this person “me”</button>`;

  host.querySelectorAll('[data-kin]').forEach(b =>
    b.addEventListener('click', () => onSelect(b.dataset.kin)));
  host.querySelector('#subjBtn').addEventListener('click', async () => {
    await post('subject', { id: pid }); onSubject(pid);
  });
  host.querySelector('#saveBtn').addEventListener('click', async (ev) => {
    ev.target.textContent = 'Saving…';
    await post('person', {
      id: pid,
      given: host.querySelector('#fGiven').value.trim(),
      surname: host.querySelector('#fSur').value.trim(),
      birth: host.querySelector('#fBirth').value.trim(),
      death: host.querySelector('#fDeath').value.trim()
    });
    ev.target.textContent = 'Saved';
    setTimeout(() => ev.target.textContent = 'Save', 1200);
    onChanged();
  });
}

const kin = (title, rows) => rows.length ? `<h4>${title}</h4><div class="kin">` +
  rows.map(r => `<button data-kin="${r.id}">${esc(r.name)}</button>`).join('') + '</div>' : '';

const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
