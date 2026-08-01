// The three screens that read the whole file rather than one person.
//
//   Numbers   what the family looks like in aggregate — lifespans by
//             decade, where it lived, how much of your own ancestry is
//             actually written down.
//   Duplicates the same person entered twice, which is rare while you type
//             and ordinary the moment you import somebody else's tree.
//   Timeline  one life with the family's events beside it. A birth date on
//             its own is a number; "his father died when he was fifteen" is
//             somebody you can picture.
import { get, post } from './api.js';

const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// ─────────────────────────────────────────────────────────────── numbers ──
export async function showStats(host, onSelect) {
  host.innerHTML = '<p class="hint">Working it out…</p>';
  const d = await get('stats');
  const s = d.summary;
  const dec = d.by_decade.filter(x => x.known_lifespans > 0);
  const maxBorn = Math.max(1, ...d.by_decade.map(x => x.born));

  host.innerHTML = `
    <div class="figs">
      ${fig(s.count, 'people', s.living ? `${s.living} living` : '')}
      ${fig(s.median_lifespan ?? '—', 'median years lived',
            s.with_both_dates ? `of the ${s.with_both_dates} with both dates`
                              : 'nobody has both dates yet')}
      ${fig(s.marriages, 'marriages')}
      ${s.endogamy_cases ? fig(s.endogamy_cases, 'cousins who married cousins')
                         : ''}
    </div>

    ${d.records.length ? `<h4>Records</h4>
      <ul class="records">${d.records.map(x => `<li>
        <b>${esc(x.what)}</b>
        <em>${esc(x.value)}</em>
        <span>${x.ids.length
          ? esc(x.who).split(' and ').map((n, i) =>
              x.ids[i] ? `<button class="link" data-go="${esc(x.ids[i])}"
                >${n}</button>` : n).join(' and ')
          : esc(x.who)}</span>
        ${x.detail ? `<small>${esc(x.detail)}</small>` : ''}
      </li>`).join('')}</ul>` : ''}

    ${d.by_decade.length > 1 ? `<h4>Born, by decade</h4>
      <div class="bars">${d.by_decade.map(x => `
        <div class="bar" title="${x.born} born in the ${x.decade}s${
          x.median_lifespan != null
            ? `, median ${x.median_lifespan} years` : ''}">
          <i style="height:${Math.round(100 * x.born / maxBorn)}%"></i>
          <span>${decadeLabel(x.decade, d.by_decade.length)}</span>
        </div>`).join('')}</div>
      <p class="hint">Each column is a decade of birth, ${
        d.by_decade[0].decade}s to ${
        d.by_decade[d.by_decade.length - 1].decade}s. Hover for the
        numbers.</p>` : ''}

    ${dec.length > 1 ? `<h4>How long people lived</h4>
      <table class="tbl"><thead><tr><th>Born</th><th>Lived to</th>
        <th>Known</th></tr></thead><tbody>
        ${dec.map(x => `<tr><td>${x.decade}s</td>
          <td>${x.median_lifespan ?? '—'}</td>
          <td class="sub">${x.known_lifespans}</td></tr>`).join('')}
      </tbody></table>` : ''}

    ${d.collapse.length ? `<h4>How much of your own ancestry is written down</h4>
      <table class="tbl"><thead><tr><th>Generation back</th><th>Known</th>
        <th>Possible</th><th></th></tr></thead><tbody>
        ${d.collapse.map(x => `<tr><td>${x.generation}</td>
          <td>${x.known}</td><td>${x.possible}</td>
          <td class="meter"><i style="width:${Math.round(x.share * 100)}%"></i></td>
        </tr>`).join('')}
      </tbody></table>
      <p class="hint">Fewer than the maximum means either research still to
        do, or cousins who married cousins.</p>` : ''}

    ${d.surnames.length ? `<h4>The names it is made of</h4>
      <ul class="chips">${d.surnames.map(x => `<li><b>${esc(x.surname)}</b>
        ${x.count}${x.first ? ` <span class="sub">${x.first}–${x.last}</span>`
                            : ''}</li>`).join('')}</ul>` : ''}

    <h4>Related lines</h4>
    <div id="statsConsang"></div>

    ${d.places.length ? `<h4>Where they were</h4>
      <ul class="chips">${d.places.map(x => `<li><b>${esc(x.place)}</b>
        ${x.born + x.died}${x.first ? ` <span class="sub">${x.first}–${x.last}</span>`
                                    : ''}</li>`).join('')}</ul>`
      : `<p class="none">No birthplaces recorded yet — they are what tells
         you which parish to search.</p>`}`;

  host.querySelectorAll('[data-go]').forEach(b =>
    b.addEventListener('click', () => onSelect(b.dataset.go)));
  showConsanguinity(host.querySelector('#statsConsang'), onSelect)
    .catch(() => {});
}

// TWO DIGITS IS AMBIGUOUS ACROSS A CENTURY, and a genealogy file always
// crosses one: "90" appeared twice on the same axis, once for 1890 and once
// for 1990. Every column carries its full year where there is room, and a
// century boundary always does.
function decadeLabel(decade, n) {
  if (n <= 16 || decade % 100 === 0) return String(decade);
  return String(decade).slice(-2);
}

function fig(n, label, sub) {
  return `<div class="f"><b>${esc(n)}</b><span>${esc(label)}</span>${
    sub ? `<small>${esc(sub)}</small>` : ''}</div>`;
}
const pct = x => x == null ? '—' : Math.round(x * 100) + '%';

// ──────────────────────────────────────────────────────────── duplicates ──
export async function showDuplicates(host, head, { onSelect, onToast, onChanged }) {
  host.innerHTML = '<p class="hint">Looking…</p>';
  const d = await get('duplicates', { limit: 40 });
  if (!d.pairs.length) {
    head.textContent = `Checked all ${d.checked} people.`;
    host.innerHTML = `<p class="none">Nothing looks like the same person
      twice. This is worth running again after importing somebody else's
      tree.</p>`;
    return;
  }
  head.textContent = `${d.pairs.length} pair${d.pairs.length === 1 ? '' : 's'}
    out of ${d.checked} people. Nothing is merged until you say so — which
    record is right is a judgement about your research, not arithmetic.`;

  host.innerHTML = d.pairs.map((p, i) => `
    <div class="dupe-pair" data-i="${i}">
      <div class="dupe-score" title="How sure, from the evidence below">
        ${Math.round(p.score * 100)}%</div>
      <div class="dupe-cards">
        ${p.people.map((x, side) => card(x, side)).join('')}
      </div>
      <ul class="dupe-why">
        ${p.why.map(w => `<li class="for">${esc(w)}</li>`).join('')}
        ${p.against.map(w => `<li class="agin">${esc(w)}</li>`).join('')}
      </ul>
      <div class="dupe-acts">
        <button class="ghost" data-merge="${esc(p.a)}|${esc(p.b)}"
          >Keep ${esc(first(p.people[0].name))} on the left, fold the other in</button>
        <button class="ghost" data-merge="${esc(p.b)}|${esc(p.a)}"
          >Keep the right one</button>
        <button class="ghost" data-skip="${i}">Not the same person</button>
      </div>
    </div>`).join('');

  host.querySelectorAll('[data-open]').forEach(b =>
    b.addEventListener('click', () => onSelect(b.dataset.open)));
  host.querySelectorAll('[data-skip]').forEach(b =>
    b.addEventListener('click', () =>
      b.closest('.dupe-pair').remove()));
  host.querySelectorAll('[data-merge]').forEach(b =>
    b.addEventListener('click', async () => {
      const [keep, gone] = b.dataset.merge.split('|');
      b.disabled = true;
      try {
        const r = await post('person/merge', { keep, gone });
        onToast(r.message);
        b.closest('.dupe-pair').remove();
        onChanged && onChanged();
        if (!host.querySelector('.dupe-pair')) {
          host.innerHTML = `<p class="none">That was the last one. Close
            this and look at the chart.</p>`;
        }
      } catch (e) { onToast(e.message); b.disabled = false; }
    }));
}

function card(x, side) {
  const rows = [
    ['Born', [x.birth, x.birth_place].filter(Boolean).join(' · ')],
    ['Died', x.death],
    ['Trade', x.occupation],
    ['Parents', x.parents.join(', ')],
    ['Married', x.partners.join(', ')],
    ['Children', x.children ? String(x.children) : ''],
    ['To you', x.relation],
  ].filter(([, v]) => v);
  return `<div class="dupe-card">
    <button class="link who" data-open="${esc(x.id)}">${esc(x.name)}</button>
    <div class="sub">${esc(x.life || 'dates unknown')} · ${x.facts}% filled in</div>
    <dl>${rows.map(([k, v]) =>
      `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    ${x.notes ? `<p class="sub">${esc(x.notes)}</p>` : ''}
  </div>`;
}
const first = n => String(n || '').split(/\s+/)[0];

// ────────────────────────────────────────────────────────────── a life ────
export async function lifeline(pid) {
  const d = await get('timeline', { id: pid });
  if (!d.events || d.events.length < 2) return '';
  return `<h4>Their life</h4>
    <ol class="life">
      ${d.events.map(e => `<li class="ev-${e.kind}">
        <b>${e.year}</b>
        <span>${esc(e.what)}</span>
        ${e.age != null && e.kind !== 'self'
          ? `<i>at ${e.age}</i>` : ''}
      </li>`).join('')}
    </ol>
    <p class="hint">Everything the file knows about them, in order.</p>`;
}

// ───────────────────────────────────────── the family as one story ───────
//
// A chart says who was related to whom and nothing about when; a person's
// timeline shows one life. This is the third view — 1841 a marriage, 1843 a
// birth, 1849 a death — the shape of a household changing, and the years
// where nothing at all is recorded.
export async function showFamilyTimeline(host, { onSelect, scope }) {
  host.innerHTML = '<p class="hint">Putting it in order…</p>';
  const d = await get('family-timeline', scope || {});
  if (!d.events.length) {
    host.innerHTML = `<p class="none">No dated events yet. Births, marriages
      and deaths appear here as soon as they have a year on them.</p>`;
    return;
  }
  const c = d.counts;
  const quiet = new Map(d.quiet.map(g => [g.from, g]));

  host.innerHTML = `
    ${d.anniversaries.length ? `<h4>Coming up</h4>
      <ul class="anniv">${d.anniversaries.slice(0, 6).map(a => `<li>
        <b>${a.in_days === 0 ? 'today' : `in ${a.in_days} days`}</b>
        <button class="link" data-go="${esc(a.id)}">${esc(a.what)}</button>
        ${a.kind === 'birthday'
          ? `${a.living ? 'turns' : 'would have been'} ${a.years}`
          : `${a.years} years married`}
      </li>`).join('')}</ul>` : ''}

    <h4>${d.span[0]}–${d.span[1]}</h4>
    <p class="hint">${c.birth} births · ${c.marriage} marriages ·
      ${c.death} deaths, across ${d.scope}.</p>
    <ol class="ftl">
      ${d.events.map(e => `
        ${quiet.has(e.year) ? `<li class="quiet">nothing recorded for
          ${quiet.get(e.year).years} years</li>` : ''}
        <li class="ev-${e.kind}">
          <b>${e.year}</b>
          <span><button class="link" data-go="${esc(e.id)}"
            >${esc(e.what)}</button>${
            e.detail ? ` <i>${esc(e.detail)}</i>` : ''}</span>
          <small>${esc(e.date)}${e.relation && e.relation !== 'no known relationship'
            ? ` · ${esc(e.relation)}` : ''}</small>
        </li>`).join('')}
    </ol>`;
  host.querySelectorAll('[data-go]').forEach(b =>
    b.addEventListener('click', () => onSelect(b.dataset.go)));
}

// ────────────────────────────────────── who married a relative ───────────
export async function showConsanguinity(host, onSelect) {
  host.innerHTML = '<p class="hint">Looking…</p>';
  const d = await get('consanguinity');
  if (!d.couples.length) {
    host.innerHTML = `<p class="none">No two people who married were already
      related, as far as this file goes. It only sees the ancestors you have
      recorded — a shared great-great-grandparent four generations back
      cannot be seen from a tree three deep.</p>`;
    return;
  }
  host.innerHTML = `
    <p class="hint">${d.related_couples} of ${d.marriages} marriages were
      between people who already shared an ancestor.</p>
    <ul class="consang">${d.couples.map(c => `<li>
      <b>${esc(c.names.join(' and '))}</b>
      <span>${esc(c.label)}${c.married ? `, married ${esc(c.married)}` : ''}</span>
      <small>Both descend from ${esc(c.ancestor_names.join(' and '))}.
        A child of theirs carries <b>${esc(c.percent)}</b> doubled ancestry.</small>
      <button class="link" data-go="${esc(c.a)}">open</button>
    </li>`).join('')}</ul>`;
  host.querySelectorAll('[data-go]').forEach(b =>
    b.addEventListener('click', () => onSelect(b.dataset.go)));
}

// ───────────────────────────────────── how are these two related? ─────────
//
// The question a family history is asked more often than any other, and
// until this the program could only answer it about one person — whoever
// the chart happened to be centred on.
//
// THE PATH IS THE ANSWER. "Second cousins once removed" is a label nobody
// repeats; "up to William Whitcombe, who was her great-grandfather and his
// great-great-grandfather" is what actually gets said, and it is the only
// form somebody can check against their own research. So the path is the
// biggest thing on the screen and the label sits above it.
export function relateScreen(host, { onSelect, people }) {
  const A = document.querySelector('#relA'), B = document.querySelector('#relB');
  const state = { a: '', b: '' };

  // Typing a name and picking one from the list. The same two lines as the
  // header search, kept here so the dialogue works with the header closed.
  const picker = (input, listEl, key) => {
    const close = () => { listEl.hidden = true; input.setAttribute('aria-expanded', 'false'); };
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      state[key] = '';
      if (q.length < 2) return close();
      const hits = people().filter(p => p.name.toLowerCase().includes(q)).slice(0, 8);
      if (!hits.length) return close();
      listEl.innerHTML = hits.map(p =>
        `<button type="button" data-id="${esc(p.id)}" data-name="${esc(p.name)}"
           >${esc(p.name)} <small>${esc(p.life || '')}</small></button>`).join('');
      listEl.hidden = false;
      input.setAttribute('aria-expanded', 'true');
      listEl.querySelectorAll('button').forEach(b =>
        b.addEventListener('click', () => {
          state[key] = b.dataset.id;
          // The NAME, not the button's text — that carries the lifespan in
          // a <small>, and the box came back reading "Heather Whitcombe 198".
          input.value = b.dataset.name;
          close(); run();
        }));
    });
    input.addEventListener('blur', () => setTimeout(close, 160));
  };
  picker(A, document.querySelector('#relAList'), 'a');
  picker(B, document.querySelector('#relBList'), 'b');

  document.querySelector('#relSwap').addEventListener('click', () => {
    [state.a, state.b] = [state.b, state.a];
    [A.value, B.value] = [B.value, A.value];
    run();
  });

  async function run() {
    if (!state.a || !state.b) {
      host.innerHTML = '<p class="hint">Pick two people and Helix will work '
        + 'out how they are related.</p>';
      return;
    }
    if (state.a === state.b) {
      host.innerHTML = '<div class="verdict nowt"><b>The same person</b></div>';
      return;
    }
    host.innerHTML = '<p class="hint">Working it out…</p>';
    const d = await get('relate', { a: state.a, b: state.b });
    if (!d.ok) { host.innerHTML = `<p class="hint">${esc(d.error)}</p>`; return; }
    draw(d);
  }

  function draw(d) {
    const a = d.people.a, b = d.people.b;
    // Said in both directions, because half the time the person asking
    // wants the other one: "he is her second cousin" and "she is his".
    const verdict = d.related
      ? `<div class="verdict"><b>${esc(b.name)} is ${esc(a.name)}'s ${
           esc(d.label)}</b><span>${esc(a.name)} is ${esc(b.name)}'s ${
           esc(d.a_of_b)}</span></div>`
      : `<div class="verdict nowt"><b>No relation has been recorded</b>
           <span>They may still be related — nobody has entered the link
           yet.</span></div>`;

    const path = d.path.length ? `<h4>The way through</h4>
      <ol class="relpath">${d.path.map(s => `<li class="${
        s.move === 'top' ? 'top' : ''}">
        <button data-go="${esc(s.id)}">${esc(s.name)}</button>
        <small>${esc(s.life || '')}</small>
        ${s.note ? `<small>${esc(s.note)}</small>` : ''}
      </li>`).join('')}</ol>` : '';

    const facts = `<div class="relfacts">
      <div><b>${esc(d.dna_display || '0%')}</b>
        <span>DNA expected in common</span></div>
      ${d.married ? `<div><b>${esc(d.inbreeding
          ? d.inbreeding.percent : '0%')}</b>
        <span>a child of theirs would carry</span></div>`
        : `<div><b>${d.kin && d.kin.steps < 99 ? d.kin.steps : '—'}</b>
        <span>steps apart in the tree</span></div>`}
    </div>`;

    host.innerHTML = verdict + path + facts
      + `<p class="hint">${esc(d.note)} DNA is an expected average — real
         sharing varies either side of it.</p>`;
    host.querySelectorAll('[data-go]').forEach(el =>
      el.addEventListener('click', () => onSelect(el.dataset.go)));
  }

  // Somebody is usually asking about the person already on screen.
  return {
    open(seedA, seedB) {
      const find = id => (people().find(p => p.id === id) || {});
      if (seedA) { state.a = seedA; A.value = find(seedA).name || ''; }
      if (seedB) { state.b = seedB; B.value = find(seedB).name || ''; }
      run();
    }
  };
}
