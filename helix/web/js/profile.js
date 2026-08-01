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
import { lifeline } from './insight.js';

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
  const { onSelect, onEdit, onToast, onChanged, onHighlight, onRelate } = hooks;
  const [d, k] = await Promise.all([get('person', { id: pid }),
                                    get('kin', { id: pid })]);
  const port = (d.photos || []).find(p => p.portrait);
  const c = d.counts || {};

  host.innerHTML = `
    <div class="pro">
      <div class="prohead">
        <label class="drop" id="dropZone" title="Add a photograph, a scan or a recording">
          ${port
            ? `<span class="framed" style="${cropStyle(port)}"></span>`
            : `<span class="ph">${esc(initials(d.name))}<em>add a photo or a scan</em></span>`}
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
          ${d.kin && d.kin.how
            ? `<p class="relhow">${esc(d.kin.how)}</p>` : ''}
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
        ${field('fFirst', 'First name', firstOf(d.given), 'Harriet')}
        ${field('fMiddle', 'Middle names', middleOf(d.given), 'Florence Ann')}
        ${field('fSurname', 'Surname', d.surname)}
        <label>Sex
          <select id="fSex">
            ${['U:not recorded', 'F:female', 'M:male', 'X:other'].map(o => {
              const [v, t] = o.split(':');
              return `<option value="${v}"${d.sex === v ? ' selected' : ''}
                >${t}</option>`;
            }).join('')}
          </select>
        </label>
        ${field('fBirth', 'Born', d.birth, '12 March 1841 — or just 1841')}
        ${field('fBPlace', 'Born in', d.birth_place)}
        ${field('fDeath', 'Died', d.death, '3 Feb 1900 — or just 1900')}
        ${field('fOcc', 'Occupation', d.occupation)}
        ${field('fEdu', 'Education', d.education)}
        <label class="wide">What you know about them
          <textarea id="fNotes" rows="4" placeholder="Anything at all — the
stories, who remembers what, why a date is uncertain.">${esc(d.notes)}</textarea>
        </label>
        <button class="primary wide" id="saveFacts">Save</button>
        <p class="hint wide">Saving updates the chart and the sidebar too.</p>
      </form>

      ${heritageBlock(d)}
      ${dnaBlock(d)}

      ${inbreedingBlock(d)}

      <div id="lifeline"></div>

      ${filesBlock(d)}

      ${gapsBlock(d)}

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
        <button class="ghost" id="goRelate"
          title="How are they related to somebody else in the file?">Relate
          to…</button>
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

  // JavaScript has no extended-regex flag and no multi-line literal: written
  // across two lines with an /x on the end, this threw "Invalid regular
  // expression" at parse time and took the WHOLE front end down with it —
  // no chart, no sidebar, no dialogs, because one bad module stops them all.
  const OK = /^(image\/|application\/pdf|text\/(plain|markdown|rtf)|application\/rtf|audio\/)/;

  async function sendPhoto(file) {
    if (!file) return;
    if (!OK.test(file.type || '') &&
        !/\.(jpe?g|png|webp|gif|heic|tiff?|pdf|txt|md|rtf|mp3|m4a|wav)$/i
          .test(file.name || '')) {
      onToast('Helix keeps pictures, PDFs, text and recordings. ' +
              'Scan a certificate as a PDF or a JPEG and try that.');
      return;
    }
    const data = await new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(r.result);
      r.onerror = () => rej(new Error('That file could not be read.'));
      r.readAsDataURL(file);
    });
    try {
      const r = await post('person/photo', { id: pid, filename: file.name,
                                             data, caption: file.name });
      onToast(r.kind === 'photo' ? 'Photograph added.'
              : `Added ${file.name}. Say what it is so you know in ten years.`);
      show(host, pid, hooks);
      onChanged && onChanged();
    } catch (e) { onToast(e.message); }
  }

  host.querySelectorAll('[data-drop]').forEach(b =>
    b.addEventListener('click', async () => {
      await post('person/photo/remove', { id: pid, media_id: b.dataset.drop });
      onToast('Taken off this person. The file is still in your album.');
      show(host, pid, hooks);
    }));
  host.querySelectorAll('[data-port]').forEach(b =>
    b.addEventListener('click', async () => {
      await post('person/photo/portrait', { id: pid, media_id: b.dataset.port });
      // The one it replaces is DEMOTED, not deleted: `album.attach` clears
      // the old flag and leaves the row. A face at twenty is not made
      // worthless by a face at eighty.
      onToast('Now the one shown. The one it replaces is kept below — '
            + 'Ctrl-Z puts it back.');
      show(host, pid, hooks);
      onChanged && onChanged();
    }));
  host.querySelectorAll('[data-crop]').forEach(b =>
    b.addEventListener('click', () => {
      const p = (d.photos || []).find(x => x.media_id === b.dataset.crop);
      if (p) cropDialog(p, pid, { onToast, onChanged,
                                  onDone: () => show(host, pid, hooks) });
    }));
  // WHEN IT WAS TAKEN, or how old they were. Both, because both are things
  // a family knows about a photograph and neither is worth refusing.
  host.querySelectorAll('[data-when]').forEach(el => {
    let t = null;
    const save = () => post('person/photo/taken',
      { id: pid, media_id: el.dataset.when, taken: el.value })
      .then(() => show(host, pid, hooks))
      .catch(e => onToast(e.message));
    el.addEventListener('change', save);
    el.addEventListener('input', () => { clearTimeout(t); t = setTimeout(save, 1200); });
  });
  host.querySelectorAll('[data-cap]').forEach(el => {
    let t = null;
    el.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => post('person/photo/caption',
        { id: pid, media_id: el.dataset.cap, caption: el.value })
        .catch(e => onToast(e.message)), 600);
    });
  });

  // ---- the facts -------------------------------------------------------
  host.querySelector('#facts').addEventListener('submit', async ev => {
    ev.preventDefault();
    // ONLY WHAT CHANGED. A field this form never touched must not be sent:
    // the server reads an absent key as "leave it alone" and an empty one
    // as "clear it", and that distinction is what stops saving a birthplace
    // from wiping a birth date.
    const body = { id: pid };
    // FIRST AND MIDDLE ARE TWO BOXES AND ONE FIELD. `given` holds the whole
    // string -- that is what a certificate says and what GEDCOM writes --
    // but nobody thinks of "Harriet Florence" as one thing to type, and a
    // middle name was the commonest thing left out because there was
    // nowhere obvious to put it.
    const given = [host.querySelector('#fFirst').value.trim(),
                   host.querySelector('#fMiddle').value.trim()]
                  .filter(Boolean).join(' ');
    if (given !== (d.given || '')) body.given = given;
    const map = { fSurname: ['surname', d.surname],
                  fSex: ['sex', d.sex],
                  fBirth: ['birth', d.birth], fBPlace: ['birth_place', d.birth_place],
                  fDeath: ['death', d.death], fOcc: ['occupation', d.occupation],
                  fEdu: ['education', d.education], fNotes: ['notes', d.notes] };
    for (const [el, [key, was]] of Object.entries(map)) {
      const now = host.querySelector('#' + el).value;
      if (now !== (was || '')) body[key] = now;
    }
    if (Object.keys(body).length === 1) { onToast('Nothing had changed.'); return; }
    try {
      await post('person', body);
      // EVERYWHERE, not just here. A name corrected in the profile has to
      // reach the chart, the sidebar list and the label under the picture,
      // or the file quietly holds two versions of the same person.
      onToast('Saved. The chart and the sidebar have been updated too.');
      show(host, pid, hooks);
      onChanged && onChanged();
    } catch (e) { onToast(e.message); }
  });

  // ---- their life, in order -------------------------------------------
  // Fetched after the panel is on screen rather than held up for: the
  // profile is what somebody clicked for and a second request must not
  // delay it.
  lifeline(pid).then(html => {
    const box = host.querySelector('#lifeline');
    if (box) box.innerHTML = html;
  }).catch(() => {});

  // ---- one more generation of the bloodline ----------------------------
  // Redrawn in place rather than reloading the profile: the whole pedigree
  // already came down with it, and a round trip to fetch what is on the
  // page loses the scroll position for nothing.
  function wireTree() {
    const b = host.querySelector('#btMore');
    if (!b) return;
    b.addEventListener('click', () => {
      const box = host.querySelector('#dnaBox');
      const keep = box.querySelector('.dnashare, .none');
      box.innerHTML = (keep ? keep.outerHTML : '') +
        bloodTree(d.dna.bloodline || [], d.name,
                  Number(b.dataset.gens) <= 3 ? 4 : 3);
      wireTree();
      box.querySelectorAll('[data-kin]').forEach(g =>
        g.addEventListener('click', () => onSelect(g.dataset.kin)));
    });
  }
  wireTree();

  // ---- where they came from -------------------------------------------
  host.querySelectorAll('[data-herit]').forEach(b =>
    b.addEventListener('click', () => {
      const box = host.querySelector('#fHerit');
      const have = box.value.split(',').map(s => s.trim()).filter(Boolean);
      if (!have.some(s => s.replace(/\s+[\d.]+%?$/, '') === b.dataset.herit))
        have.push(b.dataset.herit);
      box.value = have.join(', ');
    }));
  host.querySelector('#heritForm').addEventListener('submit', async ev => {
    ev.preventDefault();
    const { rows, given } = parseHeritage(host.querySelector('#fHerit').value);
    try {
      await post('person/heritage', { id: pid, heritage: rows,
                                      shares_given: given });
      onToast(rows.length
        ? 'Saved. Everybody below them inherits a share of it.'
        : 'Cleared.');
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
  host.querySelector('#goRelate').addEventListener('click', () =>
    onRelate && onRelate(pid));
  host.querySelector('#goPrint').addEventListener('click', () =>
    window.open(`/print/profile?id=${encodeURIComponent(pid)}`, '_blank'));
  host.querySelectorAll('[data-kin]').forEach(b =>
    b.addEventListener('click', () => onSelect(b.dataset.kin)));
}

// ---------------------------------------------------------------- heritage
//
// WHERE THEIR FAMILY CAME FROM. Typed as a sentence rather than built out of
// repeating rows, because that is how anybody says it: "half Irish, half
// Scottish" is one statement. Shares are optional and only wanted when
// somebody actually knows them.
function heritageBlock(d) {
  const h = d.heritage || {};
  const own = h.declared || [];
  const mix = h.mix || [];
  const known = (h.known_labels || []).filter(x => !own.some(o => o.label === x));
  return `
    <h4>Where they came from</h4>
    <div class="herit">
      ${mix.length && !(mix.length === 1 && mix[0].gap) ? `
        <div class="hbar" title="Worked out from everybody above them">
          ${mix.map(m => `<span class="hseg${m.gap ? ' gap' : ''}"
            style="flex:${Math.max(m.share, 0.02)}"
            title="${esc(m.label)} ${m.pct}%"></span>`).join('')}
        </div>
        <ul class="hlist">
          ${mix.map(m => `<li${m.gap ? ' class="gap"' : ''}>
            <b>${m.pct}%</b> ${esc(m.label)}</li>`).join('')}
        </ul>
        <p class="hint">${h.inherited
          ? 'Worked out from what is recorded further up — a generalisation, not a test result.'
          : 'Recorded for them directly.'}</p>` : ''}
      <form class="hform" id="heritForm">
        <label class="wide">${own.length ? 'Recorded for them' :
          'Record it for them'}
          <input id="fHerit" placeholder="Irish — or Irish 75, Scottish 25"
            value="${esc(own.map(o => o.share > 0.999 ? o.label
              : `${o.label} ${o.pct}`).join(', '))}">
        </label>
        ${known.length ? `<p class="hint">Already used in this file:
          ${known.map(l => `<button type="button" class="chip"
            data-herit="${esc(l)}">${esc(l)}</button>`).join(' ')}</p>` : ''}
        <button class="ghost wide">Save where they came from</button>
      </form>
    </div>`;
}

// -------------------------------------------------------------------- DNA
//
// HOW MUCH BLOOD, and where it came from. The number is an expectation and
// the panel says so: two brothers share 50% on average and rather more or
// less than that in fact. Beyond second cousins it stops being a prediction
// about anybody's genome at all, which is why the note is not optional.
function dnaBlock(d) {
  const dna = d.dna || {};
  // ZERO IS AN ANSWER. A husband or a step-parent shares no ancestor, and
  // 0% is the honest figure -- a blank reads as "could not be worked out".
  const line = (d.is_subject || !dna.display) ? '' : `
    <div class="dnashare${dna.share ? '' : ' zero'}">
      <b>${esc(dna.display)}</b>
      <span>expected shared DNA with ${esc(dna.with_name || 'you')}</span>
      <small>${esc(dna.share ? dna.note : dna.why || '')}</small>
    </div>`;
  return `<h4>Bloodline</h4><div class="dna" id="dnaBox">${line}
    ${bloodTree(dna.bloodline || [], d.name, 3)}</div>`;
}

// A pedigree drawn small. Half from each parent, a quarter from each
// grandparent, an eighth from each great-grandparent -- the shape people
// already carry in their heads, which is the whole reason it is worth
// drawing rather than listing.
//
// THREE GENERATIONS BY DEFAULT, and not because four is uninteresting.
// Four columns of legible names do not fit a 330px panel: drawn anyway they
// either ran off the edge, so the great-grandparents could not be seen at
// all, or shrank the type until nothing could be read. Three fits exactly;
// the fourth is one click away and shrinks the boxes to earn its column.
//
// EMPTY SEATS ARE DRAWN, not skipped. A hole with an address is a research
// gap; a tree that quietly closes up around it says the line ended when it
// has only stopped.
function bloodTree(rows, who, gens) {
  if (!rows.length) return '';
  rows = rows.filter(r => r.gen < gens);
  const wide = gens <= 3;
  // ROW is the spacing between the deepest generation's seats and must
  // clear BH, or the boxes in the last column overlap each other -- which
  // they did, by three pixels, and read as one box with two names in it.
  const BW = wide ? 92 : 74, GAP = wide ? 10 : 8, BH = wide ? 26 : 24;
  const ROW = wide ? 32 : 29, CLIP = wide ? 15 : 12;
  const H = ROW * (1 << (gens - 1)), W = gens * (BW + GAP) - GAP;
  const at = {};
  for (const r of rows) {
    const n = 1 << r.gen, i = r.slot - n;
    at[r.slot] = { x: r.gen * (BW + GAP), y: (i + 0.5) * (H / n), r };
  }
  const links = [], boxes = [];
  for (const r of rows) {
    const a = at[r.slot];
    for (const s of [r.slot * 2, r.slot * 2 + 1]) {
      const b = at[s];
      if (!b) continue;
      const mx = a.x + BW + GAP / 2;
      links.push(`<path d="M${a.x + BW} ${a.y}H${mx}V${b.y}H${b.x}"/>`);
    }
    const pct = r.share >= 0.01 ? +(r.share * 100).toFixed(1)
                                : +(r.share * 100).toFixed(2);
    boxes.push(r.id
      ? `<g class="bt${r.gen === 0 ? ' me' : ''}" data-kin="${esc(r.id)}">
           <rect x="${a.x}" y="${a.y - BH / 2}" width="${BW}" height="${BH}"
                 rx="4"/>
           <text x="${a.x + 6}" y="${a.y - 1}">${esc(clip(r.name, CLIP))}</text>
           <text x="${a.x + 6}" y="${a.y + 9}" class="sub">${pct}%${
             r.life && CLIP > 12 ? ' · ' + esc(clip(r.life, CLIP - 4)) : ''}</text>
           <title>${esc(r.name)}${r.life ? ' (' + esc(r.life) + ')' : ''} — ${
             pct}% expected shared DNA</title>
         </g>`
      : `<g class="bt none">
           <rect x="${a.x}" y="${a.y - BH / 2}" width="${BW}" height="${BH}"
                 rx="4"/>
           <text x="${a.x + 6}" y="${a.y - 1}" class="sub">not known</text>
           <text x="${a.x + 6}" y="${a.y + 9}" class="sub">${pct}%</text>
           <title>${pct}% of ${esc(who || 'their')} DNA came from somebody
             not yet recorded here.</title>
         </g>`);
  }
  // ONLY THE FRONTIER COUNTS. An empty seat behind another empty seat is
  // the same missing quarter counted twice: four unknown great-grandparents
  // under two unknown grandparents added up to 100% of an ancestry that was
  // half recorded.
  const filled = new Set(rows.filter(r => r.id).map(r => r.slot));
  const holes = rows.filter(r => !r.id);
  const lost = +(holes.filter(r => filled.has(r.slot >> 1))
                      .reduce((t, r) => t + r.share, 0) * 100).toFixed(1);
  const back = ['themselves', 'their parents', 'their grandparents',
                'their great-grandparents'][gens - 1];
  return `<div class="btwrap">
    <svg class="btree" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}"
         preserveAspectRatio="xMinYMin meet">
      <g class="btlink">${links.join('')}</g>${boxes.join('')}
    </svg></div>
    <p class="hint">${holes.length
      ? `${holes.length} of ${rows.length} seats are empty${lost
          ? ` — ${lost}% of their ancestry with nobody's name on it yet` : ''}.`
      : `Every seat filled back to ${back}.`}</p>
    <button class="ghost wide" id="btMore" data-gens="${gens}">${
      gens <= 3 ? 'Add the great-grandparents'
                : 'Back to three generations'}</button>`;
}

// ------------------------------------------------ related before marrying
//
// F IS A STATEMENT ABOUT A PEDIGREE, NOT ABOUT ANYBODY'S HEALTH, and the
// panel says so. It is also only as deep as the file: a tree that stops at
// four generations cannot see the shared great-great-grandparents that
// would raise it, so a zero is "none found here" and never "none".
function inbreedingBlock(d) {
  const f = d.inbreeding || {};
  const mine = f.married_a_relative || [];
  if (f.coefficient == null && !mine.length) return '';
  return `<h4>Related lines</h4>
    ${f.coefficient == null ? '' : `
      <div class="inbreed${f.coefficient ? ' some' : ''}">
        <b>${esc(f.percent)}</b>
        <span>of their ancestry doubles back</span>
        <small>${esc(f.why)} Worked out from this file only — a tree that
          stops four generations back cannot see further.</small>
      </div>`}
    ${mine.length ? `<ul class="relmarried">${mine.map(m => `<li>
      ${esc(m.word || 'Married')} <b>${esc(m.name)}</b>, their ${esc(m.label)}${
        m.ancestor_names.length
          ? ` — both descend from ${esc(m.ancestor_names.join(' and '))}` : ''}.
      </li>`).join('')}</ul>` : ''}`;
}

// ------------------------------------------------------- where to look next
function gapsBlock(d) {
  const gs = d.gaps || [];
  if (!gs.length) {
    return (d.missing || []).length ? `
      <div class="missing"><b>Still to find out</b>
        <p>${d.missing.map(esc).join(' · ')}</p></div>` : '';
  }
  return `<h4>Where to look next</h4>
    <ol class="gaps">
      ${gs.map(g => `<li>
        <b>${esc(g.question)}</b>
        <p class="why">${esc(g.why)}</p>
        ${g.where.length ? `<ul class="where">${
          g.where.map(w => `<li>${esc(w)}</li>`).join('')}</ul>` : ''}
      </li>`).join('')}
    </ol>`;
}

// "Irish" -> all of it. "Irish, Scottish" -> half each, worked out by the
// server. "Irish 75, Scottish 25" -> as typed. `given` is what tells the
// two apart: without it, one label typed alone would be quietly halved.
function parseHeritage(text) {
  const rows = [];
  let given = false;
  for (const part of String(text || '').split(',')) {
    const s = part.trim();
    if (!s) continue;
    const m = s.match(/^(.*?)[\s:]+([\d.]+)\s*%?$/);
    if (m && m[1].trim()) {
      given = true;
      rows.push({ label: m[1].trim(), share: parseFloat(m[2]) / 100 });
    } else {
      rows.push({ label: s });
    }
  }
  return { rows, given };
}

function clip(s, n) {
  s = String(s || '');
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
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

// PICTURES AND PAPERS. The things people actually have in a shoebox are the
// order of service from a funeral, a scanned certificate, a letter, a will —
// the evidence behind everything else in the file. They belong next to the
// person, so they are stored the same way as a photograph and listed here.
// A FACE OVER A LIFETIME, and the papers behind it.
//
// Somebody at twenty and the same person at eighty are two photographs of
// one person, and replacing the first with the second throws away half of
// what a family album is for. So the newest is the portrait -- the one on
// the chart, the profile and the printed record -- and every earlier one
// stays, in order, with the age they were in it.
//
// The age is the whole point of keeping them. A shoebox of undated faces is
// what a family history is trying to stop being.
function filesBlock(d) {
  const all = d.photos || [];
  const pics = all.filter(x => x.kind === 'photo');
  const papers = all.filter(x => x.kind !== 'photo');
  const earlier = pics.filter(p => !p.portrait);
  if (!all.length) return `<h4>Pictures and papers</h4>
    <p class="none">Nothing attached yet. Drop a photograph, a scanned
      certificate or an order of service on the frame above.</p>`;
  const pic = p => `
      <figure>
        <img src="/api/media?name=${encodeURIComponent(p.name)}" alt="">
        ${p.portrait ? '<i class="isport">shown now</i>'
          : `<button class="mkport" data-port="${esc(p.media_id)}"
               title="Show this one instead. The one it replaces is kept."
               >show this one</button>`}
        <button class="crop" data-crop="${esc(p.media_id)}"
          title="Choose which part of this picture goes in the frame. The
picture itself is not changed.">crop</button>
        <button class="x" data-drop="${esc(p.media_id)}"
          title="Take this off this person">×</button>
        <figcaption>
          <input class="whenbox" data-when="${esc(p.media_id)}"
            value="${esc(p.taken)}" placeholder="when? e.g. 1974, or 12">
          ${p.when ? `<span>${esc(p.when)}</span>` : ''}
        </figcaption>
      </figure>`;
  return `<h4>Pictures and papers</h4>
    ${pics.length ? `
      ${pics.length > 1 ? `<p class="hint">The one marked <b>shown now</b> is
        the one on the chart and on printed records. The others are how they
        looked before — put a year or an age under each.</p>` : ''}
      <!-- SHOWN FOR ONE PICTURE TOO. It used to appear only when there were
           two or more, which meant somebody with a single photograph could
           not date it and could not crop it — and one photograph is what
           most people have. -->
      <div class="progal">${pics.filter(p => p.portrait).map(pic).join('')}
        ${earlier.map(pic).join('')}</div>` : ''}
    ${papers.length ? `<ul class="papers">${papers.map(p => `<li>
      <a href="/api/media?name=${encodeURIComponent(p.name)}&as=${
        encodeURIComponent(p.caption || p.name)}" target="_blank"
        class="paperlink">
        <b>${esc(p.caption || 'Untitled')}</b>
        <span>${esc(p.kind === 'sound' ? 'recording' : 'document')} ·
          ${esc(p.name.split('.').pop())}</span>
      </a>
      <input class="papercap" data-cap="${esc(p.media_id)}"
        value="${esc(p.caption)}" placeholder="What is it?">
      <button class="x" data-drop="${esc(p.media_id)}"
        title="Take this off this person">×</button>
    </li>`).join('')}</ul>` : ''}`;
}

// "Harriet Florence Ann" -> "Harriet" and "Florence Ann".
function firstOf(given) {
  return String(given || '').trim().split(/\s+/)[0] || '';
}
function middleOf(given) {
  return String(given || '').trim().split(/\s+/).slice(1).join(' ');
}

// ────────────────────────────────────────────────────── cropping a face ───
//
// WHAT THIS DOES NOT DO. It does not make a new picture. A family
// photograph is very often the only copy of a group at a wedding, and
// cropping to one face by re-encoding destroys everybody else in it — a
// loss nothing undoes, because the bytes are gone. Four fractions are
// stored on the row instead: the frame shows the face, the file still
// holds the wedding, and taking the crop off puts the whole picture back.
//
// It also means no image library, which the program does not have and is
// not going to grow for this.
function cropDialog(photo, pid, { onToast, onChanged, onDone }) {
  const dlg = document.createElement('dialog');
  dlg.className = 'addDlg cropDlg';
  dlg.innerHTML = `
    <h2>Which part is the face?</h2>
    <p class="hint">Drag a square over the picture. Nothing is cut — the
      whole photograph stays in your album, and “the whole picture” puts it
      back.</p>
    <div class="cropwrap" id="cw">
      <img id="ci" src="/api/media?name=${encodeURIComponent(photo.name)}" alt="">
      <div class="cropbox" id="cb" hidden></div>
    </div>
    <p class="hint" id="cnote">Drag across the picture to choose.</p>
    <div class="row">
      <button class="primary" id="cgo" disabled>Use this square</button>
      <button class="ghost" id="cwhole">The whole picture</button>
      <button class="ghost" id="cno">Cancel</button>
    </div>`;
  document.body.appendChild(dlg);
  dlg.showModal();
  const q = s => dlg.querySelector(s);
  const wrap = q('#cw'), box = q('#cb'), img = q('#ci');
  let sq = null;                       // {x,y,w,h} in fractions

  // A SQUARE, because the frame it goes into is one. Dragging a rectangle
  // into a round frame means the program picks which half to throw away,
  // and it will pick wrong.
  const draw = () => {
    if (!sq) { box.hidden = true; q('#cgo').disabled = true; return; }
    const r = img.getBoundingClientRect(), w = wrap.getBoundingClientRect();
    box.hidden = false;
    box.style.left = (r.left - w.left + sq.x * r.width) + 'px';
    box.style.top = (r.top - w.top + sq.y * r.height) + 'px';
    box.style.width = (sq.w * r.width) + 'px';
    box.style.height = (sq.h * r.height) + 'px';
    q('#cgo').disabled = false;
    q('#cnote').textContent =
      `A square ${Math.round(sq.w * 100)}% of the width across. Drag again to
       change it.`;
  };

  let from = null;
  const at = ev => {
    const r = img.getBoundingClientRect();
    return { x: (ev.clientX - r.left) / r.width,
             y: (ev.clientY - r.top) / r.height, r };
  };
  img.addEventListener('pointerdown', ev => {
    ev.preventDefault();
    img.setPointerCapture(ev.pointerId);
    from = at(ev);
  });
  img.addEventListener('pointermove', ev => {
    if (!from) return;
    const to = at(ev), r = from.r;
    // The drag sets the side in PIXELS and it is turned into fractions of
    // each axis separately — the image is not square, so one fraction
    // cannot mean the same distance both ways.
    const side = Math.max(Math.abs(to.x - from.x) * r.width,
                          Math.abs(to.y - from.y) * r.height);
    const w = Math.min(side / r.width, 1), h = Math.min(side / r.height, 1);
    const x = Math.min(Math.max(to.x < from.x ? from.x - w : from.x, 0), 1 - w);
    const y = Math.min(Math.max(to.y < from.y ? from.y - h : from.y, 0), 1 - h);
    sq = { x, y, w, h };
    draw();
  });
  const stop = () => { from = null; };
  img.addEventListener('pointerup', stop);
  img.addEventListener('pointercancel', stop);
  img.addEventListener('load', draw);
  window.addEventListener('resize', draw);

  // What is already set, so opening this shows the crop rather than
  // starting from nothing every time.
  const had = (photo.crop || '').split(',').map(Number);
  if (had.length === 4 && had.every(n => isFinite(n)) && had[2] > 0) {
    sq = { x: had[0], y: had[1], w: had[2], h: had[3] };
    if (img.complete) draw();
  }

  const close = () => { dlg.close(); dlg.remove(); };
  const save = async crop => {
    try {
      await post('person/photo/crop',
                 { id: pid, media_id: photo.media_id, crop });
      close();
      onToast(crop ? 'Cropped. The whole photograph is still in your album, '
                   + 'and Ctrl-Z puts the frame back.'
                   : 'Showing the whole picture again.');
      onDone && onDone();
      onChanged && onChanged();
    } catch (e) { onToast(e.message); }
  };
  q('#cgo').addEventListener('click', e => {
    e.preventDefault();
    if (sq) save(`${sq.x},${sq.y},${sq.w},${sq.h}`);
  });
  q('#cwhole').addEventListener('click', e => { e.preventDefault(); save(''); });
  q('#cno').addEventListener('click', e => { e.preventDefault(); close(); });
  dlg.addEventListener('cancel', () => dlg.remove());
}

function firstName(name) {
  return (name || 'their').split(/\s+/)[0];
}

function initials(name) {
  return (name || '?').split(/\s+/).filter(Boolean)
    .map(w => w[0]).slice(0, 2).join('').toUpperCase();
}

/** Show a rectangle of a photograph in a fixed frame, without touching it.
 *
 *  NOTHING IS RE-ENCODED. The one photograph of somebody's grandmother is
 *  usually a group at a wedding, and cropping it to her face by writing new
 *  pixels destroys the only copy of everybody else at it. The crop is four
 *  fractions stored on the row; this turns them into a background so the
 *  frame shows the face and the file still holds the wedding.
 *
 *  The two percentages are the standard background-position identity: to
 *  show the rectangle starting at x with width w, the image is scaled by
 *  1/w and slid to x/(1-w) of the overflow. Zero width is guarded because
 *  x/(1-w) divides by nothing when w is 1.
 */
export function cropStyle(p) {
  // SINGLE QUOTES INSIDE THE url(). This is interpolated into a
  // style="..." attribute, and a double quote closed it — the browser read
  // `background-image:url(` and stopped, so the frame came out blank while
  // the printed sheet, which builds the same style with single quotes, was
  // right. The two disagreeing about somebody's face is exactly the kind of
  // difference nobody thinks to check.
  const url = `/api/media?name=${encodeURIComponent(p.name)}`;
  const bg = `background-image:url('${url}');background-repeat:no-repeat;`;
  const c = (p.crop || '').split(',').map(Number);
  if (c.length !== 4 || c.some(n => !isFinite(n)) || c[2] <= 0 || c[3] <= 0) {
    return bg + 'background-size:cover;background-position:center';
  }
  const [x, y, w, h] = c;
  const px = w >= 1 ? 50 : (x / (1 - w)) * 100;
  const py = h >= 1 ? 50 : (y / (1 - h)) * 100;
  return bg + `background-size:${(100 / w).toFixed(3)}% ${(100 / h).toFixed(3)}%;`
            + `background-position:${px.toFixed(2)}% ${py.toFixed(2)}%`;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
