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
      ${fig(s.count, 'people in the file')}
      ${fig(s.median_lifespan_excl_infants ?? '—', 'median years lived',
            s.with_both_dates ? `of the ${s.with_both_dates} with both dates`
                              : 'nobody has both dates yet')}
      ${s.infant_deaths ? fig(pct(s.infant_rate), 'died before five',
                              `${s.infant_deaths} of ${s.with_both_dates}`) : ''}
      ${s.endogamy_cases ? fig(s.endogamy_cases, 'cousins who married cousins')
                         : ''}
    </div>

    ${d.extremes.length ? `<h4>The ones people remember</h4>
      <ul class="extremes">${d.extremes.map(x => `<li>
        <b>${esc(x.what)}</b>
        <button class="link" data-go="${esc(x.id)}">${esc(x.who)}</button>
        — ${esc(x.value)}${x.detail ? ` <span class="sub">${esc(x.detail)}</span>` : ''}
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
        <th>Reaching five</th><th>Known</th></tr></thead><tbody>
        ${dec.map(x => `<tr><td>${x.decade}s</td>
          <td>${x.median_lifespan ?? '—'}</td>
          <td>${x.median_reaching_five ?? '—'}</td>
          <td class="sub">${x.known_lifespans}</td></tr>`).join('')}
      </tbody></table>
      <p class="hint">Two columns because they are two different facts. A
        raw median is dragged down by infant deaths and tells you nobody
        reached fifty; that is not what the records say, it is what dying at
        two does to an average.</p>` : ''}

    ${d.collapse.length ? `<h4>How much of your own ancestry is written down</h4>
      <table class="tbl"><thead><tr><th>Generation back</th><th>Known</th>
        <th>Possible</th><th></th></tr></thead><tbody>
        ${d.collapse.map(x => `<tr><td>${x.generation}</td>
          <td>${x.known}</td><td>${x.possible}</td>
          <td class="meter"><i style="width:${Math.round(x.share * 100)}%"></i></td>
        </tr>`).join('')}
      </tbody></table>
      <p class="hint">Everybody has 1024 ten-generation ancestors on paper
        and fewer in fact, because cousins married cousins. The gap between
        the columns is partly research still to do and partly the shape of a
        real family.</p>` : ''}

    ${d.surnames.length ? `<h4>The names it is made of</h4>
      <ul class="chips">${d.surnames.map(x => `<li><b>${esc(x.surname)}</b>
        ${x.count}${x.first ? ` <span class="sub">${x.first}–${x.last}</span>`
                            : ''}</li>`).join('')}</ul>` : ''}

    ${d.places.length ? `<h4>Where they were</h4>
      <ul class="chips">${d.places.map(x => `<li><b>${esc(x.place)}</b>
        ${x.born + x.died}${x.first ? ` <span class="sub">${x.first}–${x.last}</span>`
                                    : ''}</li>`).join('')}</ul>`
      : `<p class="none">No birthplaces recorded yet — they are what tells
         you which parish to search.</p>`}`;

  host.querySelectorAll('[data-go]').forEach(b =>
    b.addEventListener('click', () => onSelect(b.dataset.go)));
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
    <p class="hint">Everything the file knows, in order. A date on its own is
      a number; a life is what the dates are for.</p>`;
}
