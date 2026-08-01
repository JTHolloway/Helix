// Everybody in the file, in tabs, closest relation first.
//
// The order is the one people name their family in — you, immediate family,
// grandparents, aunts and uncles, first cousins — and not the alphabet and
// not the raw arithmetic. By path length a grandparent ties with a brother
// and a great-grandparent ties with an aunt: true, and not how anybody
// thinks about their family. `helix/graph/kinship.py` owns that ordering;
// this file only draws it.
//
// Tabs rather than one long list because a real family file is hundreds of
// people and the useful question is almost always "who are my first
// cousins", never "who is person 214".
import { get } from './api.js';

let DATA = null;          // the last /api/relatives payload
let OPEN = new Set();     // which tabs the person has opened, kept across refreshes
let FILTER = '';

export async function load() {
  DATA = await get('relatives');
  return DATA;
}

export function draw(host, { onSelect, selected, onScope }) {
  if (!DATA) return;
  const q = FILTER.trim().toLowerCase();
  host.innerHTML = '';

  // The first tab starts open, because a panel of closed drawers with
  // nothing showing does not read as a list of your family.
  if (!OPEN.size && DATA.groups.length) OPEN.add(DATA.groups[1]?.key || DATA.groups[0].key);

  let shown = 0;
  for (const g of DATA.groups) {
    const people = q
      ? g.people.filter(p => p.name.toLowerCase().includes(q)
                          || (p.relation || '').toLowerCase().includes(q))
      : g.people;
    if (!people.length) continue;
    shown += people.length;

    const box = document.createElement('details');
    box.className = 'kingroup';
    box.open = q ? true : OPEN.has(g.key);   // a filter opens everything it matched
    box.addEventListener('toggle', () => {
      if (q) return;
      box.open ? OPEN.add(g.key) : OPEN.delete(g.key);
    });

    const sum = document.createElement('summary');
    const need = people.filter(p => p.needs).length;
    sum.innerHTML = `<span class="t">${esc(g.title)}</span>` +
                    (need ? `<i class="dot" title="${need} ${
                      need === 1 ? 'record needs' : 'records need'
                      } something">${need}</i>` : '') +
                    `<span class="n">${people.length}</span>`;
    sum.title = g.blurb || '';
    box.appendChild(sum);

    const ul = document.createElement('div');
    ul.className = 'kinpeople';
    for (const p of people) {
      const b = document.createElement('button');
      b.className = 'kinperson' + (p.id === selected ? ' on' : '');
      b.dataset.p = p.id;
      b.innerHTML =
        (p.portrait
          ? `<img class="av" src="/api/media?name=${encodeURIComponent(p.portrait)}" alt="">`
          : `<span class="av blank">${esc(initials(p.name))}</span>`) +
        `<span class="who"><b>${esc(p.name)}</b>` +
        `<small>${esc(p.life || '')}${p.life && p.relation ? ' · ' : ''}` +
        `${esc(p.relation || '')}</small></span>` +
        // ONE DOT, NOT A LIST. A red mark beside four hundred names is
        // decoration; this is only shown for the things that stop somebody
        // being findable at all, and the reason is in the tooltip.
        (p.needs ? `<i class="dot" title="${esc(p.needs)}"></i>` : '');
      b.addEventListener('click', () => onSelect(p.id));
      ul.appendChild(b);
    }
    box.appendChild(ul);
    host.appendChild(box);
  }

  if (!shown) {
    host.innerHTML = `<p class="none">Nobody here matches “${esc(FILTER)}”.</p>`;
  }
  if (onScope) onScope(DATA.total, shown);
}

export function filter(text) { FILTER = text || ''; }

export function openFor(pid, host) {
  // Opening somebody's tab when they are selected elsewhere is what makes
  // the sidebar and the chart feel like one thing rather than two lists.
  if (!DATA) return;
  for (const g of DATA.groups) {
    if (g.people.some(p => p.id === pid)) { OPEN.add(g.key); break; }
  }
  const row = host.querySelector(`.kinperson[data-p="${CSS.escape(pid)}"]`);
  if (row) row.scrollIntoView({ block: 'nearest' });
}

export function mark(host, pid) {
  host.querySelectorAll('.kinperson.on').forEach(n => n.classList.remove('on'));
  const row = host.querySelector(`.kinperson[data-p="${CSS.escape(pid)}"]`);
  if (row) { row.classList.add('on'); row.scrollIntoView({ block: 'nearest' }); }
}

function initials(name) {
  return (name || '?').split(/\s+/).filter(Boolean)
    .map(w => w[0]).slice(0, 2).join('').toUpperCase();
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
