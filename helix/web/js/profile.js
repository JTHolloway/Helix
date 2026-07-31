// One person, read rather than edited.
//
// The panel `inspector.js` shows is for BUILDING a family: add a father, add
// a partner, fix a date. This one is for reading it — who they are, how they
// are related to you, how many brothers and sisters they had, what anybody
// wrote down, and their photograph. The two are deliberately separate
// screens rather than one screen with a mode, because the questions are
// different and the reading one has to be safe to hand to somebody else.
//
// It is also where the chart gets lit up. Clicking a person highlights THEIR
// relatives — their brothers and sisters, their cousins — which is a second
// measurement from a different origin, not a re-reading of yours.
import { get, post } from './api.js';

// Which relations get a colour when somebody is selected. Everything else is
// left alone: a chart where forty groups all light up says nothing.
export const HALO = [
  ['immediate', 'Immediate family'],
  ['cousins_1', 'First cousins'],
  ['cousins_2', 'Second cousins'],
  ['aunts_uncles', 'Aunts and uncles'],
  ['nieces_nephews', 'Nieces and nephews'],
  ['grandparents', 'Grandparents'],
  ['grandchildren', 'Grandchildren'],
];

export async function show(host, pid, hooks) {
  const { onSelect, onEdit, onToast, onChanged, onHighlight } = hooks;
  const [d, k] = await Promise.all([get('person', { id: pid }),
                                    get('kin', { id: pid })]);
  const port = (d.photos || []).find(p => p.portrait);
  const c = d.counts || {};

  host.innerHTML = `
    <div class="pro">
      <div class="prohead">
        <label class="drop" id="dropZone" title="Add a photograph">
          ${port
            ? `<img src="/api/media?name=${encodeURIComponent(port.name)}" alt="">`
            : `<span class="ph">${esc(initials(d.name))}<em>add a photo</em></span>`}
          <input type="file" id="photoIn" accept="image/*" hidden>
        </label>
        <div class="protxt">
          <h3>${esc(d.name) || '<em>no name yet</em>'}</h3>
          <p class="life">${esc(d.life || 'dates unknown')}${
            d.age ? ' · lived ' + esc(d.age) : ''}</p>
          ${d.kin && d.kin.group !== 'self'
            ? `<span class="rel">${esc(d.kin.label)}</span>` : ''}
          ${d.is_subject ? '<span class="rel me">this is you</span>' : ''}
          ${d.on_thread && !d.is_subject
            ? '<span class="rel">on your bloodline</span>' : ''}
        </div>
      </div>

      <div class="metrics">
        ${metric(c.siblings, 'brothers and sisters',
                 c.half_siblings ? `${c.half_siblings} of them half` : '')}
        ${metric(c.children, 'children')}
        ${metric(c.ancestors_known, 'ancestors recorded',
                 c.generations_back ? `${c.generations_back} generations back` : '')}
        ${metric(c.descendants_known, 'descendants recorded',
                 c.generations_forward ? `${c.generations_forward} generations on` : '')}
        ${d.kin && d.kin.steps < 99 && !d.is_subject
          ? metric(d.kin.steps, 'steps from you',
                   d.kin.blood ? 'by blood' : 'through a marriage') : ''}
      </div>

      <h4>What is known</h4>
      <form class="facts" id="facts">
        ${field('fBirth', 'Born', d.birth, '1834, abt 1834, 12 Mar 1841…')}
        ${field('fBPlace', 'Born in', d.birth_place)}
        ${field('fDeath', 'Died', d.death)}
        ${field('fOcc', 'Occupation', d.occupation)}
        ${field('fEdu', 'Education', d.education)}
        <label class="wide">What you know about them
          <textarea id="fNotes" rows="4" placeholder="Anything at all — the
stories, who remembers what, why a date is uncertain.">${esc(d.notes)}</textarea>
        </label>
        <button class="primary wide" id="saveFacts">Save</button>
      </form>

      ${(d.photos || []).length > 1 ? gallery(d.photos) : ''}

      ${(d.missing || []).length ? `
        <div class="missing">
          <b>Still to find out</b>
          <p>${d.missing.map(esc).join(' · ')}</p>
        </div>` : ''}

      <h4>Who is around them</h4>
      <div id="halo" class="halo"></div>

      <div class="proacts">
        ${d.is_subject ? '' :
          `<button class="ghost wide" id="goSubject"
            title="Redraw the whole chart with them at the centre, and read
            every relation from where they stood">See the family from
            ${esc(firstName(d.name))}'s side</button>`}
      </div>
      <div class="proacts">
        <button class="ghost" id="goEdit">Edit this person</button>
        <button class="ghost" id="goPrint">Print this profile</button>
      </div>
    </div>`;

  // ---- highlighting the chart -----------------------------------------
  const halo = host.querySelector('#halo');
  const bits = [];
  for (const [key, title] of HALO) {
    const ids = k.highlight[key];
    if (!ids || !ids.length) continue;
    bits.push(`<button class="halobtn" data-h="${key}">
      <i class="sw sw-${key}"></i>${esc(title)} <b>${ids.length}</b></button>`);
  }
  halo.innerHTML = bits.length
    ? bits.join('') + `<p class="hint">Shown on the chart. Click one to keep
        only that group lit.</p>`
    : '<p class="none">Nobody else on this chart is related to them.</p>';
  if (onHighlight) onHighlight(k.highlight, pid);
  halo.querySelectorAll('.halobtn').forEach(b => {
    b.addEventListener('click', () => {
      const only = b.classList.toggle('on');
      halo.querySelectorAll('.halobtn').forEach(x => {
        if (x !== b) x.classList.remove('on');
      });
      onHighlight(only ? { [b.dataset.h]: k.highlight[b.dataset.h] }
                       : k.highlight, pid);
    });
  });

  // ---- a photograph ----------------------------------------------------
  const input = host.querySelector('#photoIn');
  const zone = host.querySelector('#dropZone');
  input.addEventListener('change', () => sendPhoto(input.files[0]));
  zone.addEventListener('dragover', ev => {
    ev.preventDefault(); zone.classList.add('over');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('over'));
  zone.addEventListener('drop', ev => {
    ev.preventDefault(); zone.classList.remove('over');
    sendPhoto(ev.dataTransfer.files[0]);
  });

  async function sendPhoto(file) {
    if (!file) return;
    if (!/^image\//.test(file.type)) {
      onToast('That is not a picture. Choose a JPEG or a PNG.'); return;
    }
    const data = await new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(r.result);
      r.onerror = () => rej(new Error('That file could not be read.'));
      r.readAsDataURL(file);
    });
    try {
      await post('person/photo', { id: pid, filename: file.name, data });
      onToast('Photograph added.');
      show(host, pid, hooks);
      onChanged && onChanged();
    } catch (e) { onToast(e.message); }
  }

  host.querySelectorAll('[data-drop]').forEach(b =>
    b.addEventListener('click', async () => {
      await post('person/photo/remove', { id: pid, media_id: b.dataset.drop });
      onToast('Photograph removed from this person. The file is still in your album.');
      show(host, pid, hooks);
    }));

  // ---- the facts -------------------------------------------------------
  host.querySelector('#facts').addEventListener('submit', async ev => {
    ev.preventDefault();
    // ONLY WHAT CHANGED. A field this form never touched must not be sent:
    // the server reads an absent key as "leave it alone" and an empty one
    // as "clear it", and that distinction is what stops saving a birthplace
    // from wiping a birth date.
    const body = { id: pid };
    const map = { fBirth: ['birth', d.birth], fBPlace: ['birth_place', d.birth_place],
                  fDeath: ['death', d.death], fOcc: ['occupation', d.occupation],
                  fEdu: ['education', d.education], fNotes: ['notes', d.notes] };
    for (const [el, [key, was]] of Object.entries(map)) {
      const now = host.querySelector('#' + el).value;
      if (now !== (was || '')) body[key] = now;
    }
    if (Object.keys(body).length === 1) { onToast('Nothing had changed.'); return; }
    try {
      await post('person', body);
      onToast('Saved.');
      show(host, pid, hooks);
      onChanged && onChanged();
    } catch (e) { onToast(e.message); }
  });

  const sub = host.querySelector('#goSubject');
  if (sub) sub.addEventListener('click', async () => {
    // WHOSE CHART IT IS, changed. Every relation on the screen is measured
    // from one person, so this is not a camera move -- it re-reads the
    // whole family from where somebody else stood. It is also the thing
    // that makes a shared file useful to more than one person in it.
    await post('subject', { id: pid });
    onToast(`Now reading the family from ${firstName(d.name)}'s side.`);
    onChanged && onChanged();
  });
  host.querySelector('#goEdit').addEventListener('click', () => onEdit(pid));
  host.querySelector('#goPrint').addEventListener('click', () =>
    window.open(`/print/profile?id=${encodeURIComponent(pid)}`, '_blank'));
  host.querySelectorAll('[data-kin]').forEach(b =>
    b.addEventListener('click', () => onSelect(b.dataset.kin)));
}

function metric(n, label, sub) {
  if (n === undefined || n === null) return '';
  return `<div class="m"><b>${n}</b><span>${esc(label)}</span>${
    sub ? `<small>${esc(sub)}</small>` : ''}</div>`;
}

function field(id, label, value, ph) {
  return `<label>${esc(label)}<input id="${id}" value="${esc(value)}"${
    ph ? ` placeholder="${esc(ph)}"` : ''}></label>`;
}

function gallery(photos) {
  return '<h4>Photographs</h4><div class="progal">' + photos.map(p =>
    `<figure><img src="/api/media?name=${encodeURIComponent(p.name)}" alt="">
      <button class="x" data-drop="${esc(p.media_id)}" title="Take this off
      this person">×</button></figure>`).join('') + '</div>';
}

function firstName(name) {
  return (name || 'their').split(/\s+/)[0];
}

function initials(name) {
  return (name || '?').split(/\s+/).filter(Boolean)
    .map(w => w[0]).slice(0, 2).join('').toUpperCase();
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
