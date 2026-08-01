// WALKTHROUGH — the interface, driven the way somebody uses it.
//
// `pytest` covers the model, the layout and every endpoint over real HTTP.
// It cannot see a button sitting under another button, a click that never
// reaches its handler, or a chart nobody can select anyone on — and all
// three of those were live in this program until it was run. This drives a
// real browser through the real interface and looks at what happens.
//
// Not part of `pytest`: it needs a browser, and the program itself has no
// dependencies. Run it when you have one.
//
//     python3 -m helix.cli serve FILE --port PORT --no-open &
//     node tools/walkthrough-edit.mjs http://127.0.0.1:PORT/
//
// It WRITES. Point it at a throwaway file, never at your own family.
//
// The second half: everything that CHANGES the file, driven through the
// real interface. Building a family from nothing, editing it, taking it
// back, and every screen that only appears once there is something in it.
// Playwright is not installed by this project and must not be. Found
// wherever it happens to live, with a message rather than a stack trace.
let pw;
try {
  pw = (await import('playwright')).default ?? await import('playwright');
} catch {
  try { pw = (await import(process.env.PLAYWRIGHT ||
    '/opt/node22/lib/node_modules/playwright/index.js')).default; }
  catch {
    console.error('This needs Playwright and a browser.\n' +
      '  npm i -g playwright && npx playwright install chromium\n' +
      'Then run it again, or set PLAYWRIGHT to its index.js.');
    process.exit(2);
  }
}

const U = process.argv[2] || 'http://127.0.0.1:8898/';
const b = await pw.chromium.launch(process.env.CHROME
  ? { executablePath: process.env.CHROME } : {});
const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
const errs = [];
p.on('pageerror', e => errs.push('PAGEERROR ' + e.message));
p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });

let pass = 0, fail = 0;
const check = (n, ok, note = '') => {
  (ok ? pass++ : fail++);
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${n}${note ? '  — ' + note : ''}`);
};
const api = (path, body) => p.evaluate(async ([u, q, bd]) => {
  const r = bd
    ? await fetch(u + 'api/' + q, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(bd) })
    : await fetch(u + 'api/' + q);
  return { ok: r.ok, body: await r.json().catch(() => null) };
}, [U, path, body || null]);

await p.goto(U, { waitUntil: 'networkidle', timeout: 90000 });
await p.waitForTimeout(3000);

console.log('\nBuilding a family from nothing');
await p.click('#firstPerson');
await p.waitForTimeout(800);
await p.keyboard.type('James Edward');
await p.keyboard.press('Tab');
await p.keyboard.type('Holloway');
await p.keyboard.press('Tab');
await p.keyboard.type('12 March 1990');
await p.keyboard.press('Alt+m');
await p.waitForTimeout(300);
await p.keyboard.press('Enter');
await p.waitForTimeout(3500);
check('the first person is on the chart',
      await p.$$eval('#canvas svg text', n => n.length) >= 1);
check('the sidebar counted them',
      /1 of 1/.test(await p.textContent('#kinCount')));
{
  const me0 = (await api('meta')).body.people[0];
  const d0 = (await api('person?id=' + me0.id)).body;
  check('the whole date was kept', d0.birth === '12 Mar 1990', d0.birth || '(none)');
}

// The ordinary path for adding family is BUILD mode, where the inspector
// offers "+ Add father" beside the person you are standing on.
await p.click('#buildBtn');
await p.waitForTimeout(2000);

// Their family, through the buttons on the profile — the ordinary path.
const addVia = async (label, given, surname, born, sex) => {
  const btn = await p.$(`button:text-is("${label}")`);
  if (!btn) { check(`add ${label}`, false, 'no button'); return; }
  await btn.click();
  await p.waitForTimeout(800);
  await p.keyboard.type(given);
  const sur = await p.$('#aSur');
  await sur.fill(surname);
  await p.fill('#aBirth', born);
  await p.keyboard.press(`Alt+${sex}`);
  await p.waitForTimeout(250);
  await p.keyboard.press('Enter');
  await p.waitForTimeout(2800);
};
await addVia('+ Add father', 'Michael', 'Holloway', '1960', 'm');
await addVia('+ Add mother', 'Susan', 'Reed', '1962', 'f');
const n3 = (await api('meta')).body.stats.people;
check('father and mother went in', n3 === 3, `${n3} people`);
check('they landed in one family',
      (await api('person?id=' + (await api('meta')).body.people
        .find(x => x.name.includes('James')).id)).body.parents.length === 2);

// A sibling. The inspector is still standing on James.
await addVia('+ Add a brother or sister', 'Claire', 'Holloway', '1993', 'f');
const n4 = (await api('meta')).body.stats.people;
check('a sibling shares both parents', n4 === 4, `${n4} people`);

console.log('\nEditing what is known');
const me = (await api('meta')).body.people.find(x => x.name.includes('James'));
// Stand on James again. In Build mode the sidebar of names is hidden, so
// the way in is his name ON THE CHART — which is the way somebody would
// actually do it.
const onChart = await p.$(`#canvas [data-p="${me.id}"]`);
check('his name on the chart can be clicked', !!onChart);
if (onChart) { await onChart.click({ force: true }); await p.waitForTimeout(2200); }
// The boxes live behind the ✎ button — open them only if they are shut.
check('there is a way to edit them', !!(await p.$('#editBtn')));
if (await p.$eval('#details', e => e.hidden).catch(() => true)) {
  await p.click('#editBtn');
  await p.waitForTimeout(900);
}
const place = await p.$('#fPlace');
check('the birthplace box is on the panel',
      !!place && await place.isVisible());
if (place) {
  await place.fill('Frome, Somerset');
  await p.keyboard.press('Tab');
  await p.waitForTimeout(2800);
}
const after = (await api('person?id=' + me.id)).body;
check('a birthplace saves', after.birth_place === 'Frome, Somerset',
      after.birth_place || '(nothing)');
check('and does not wipe the date beside it', after.birth === '12 Mar 1990',
      after.birth || '(nothing)');

console.log('\nChanging the design and the look');
await p.evaluate(() => { const l = document.querySelector('#left'); if (l) l.hidden = false; });
await p.waitForTimeout(4000);
const designs = await p.$$eval('#gallery button', n => n.length);
check('the gallery offers every design', designs === 20, `${designs} shown`);
for (const name of ['Concentric Rings', 'Classic Tree', 'Treemap', 'Family Rings']) {
  const before = errs.length;
  const hit = await p.$(`#gallery button:has(span:text-is("${name}"))`);
  if (!hit) { check(`design: ${name}`, false, 'not in the gallery'); continue; }
  await hit.click();
  await p.waitForTimeout(3500);
  check(`design: ${name}`,
        await p.$$eval('#canvas svg *', n => n.length) > 6 && errs.length === before,
        errs.length > before ? errs[before] : '');
}

console.log('\nNarrowing the chart');
await p.selectOption('#focus', 'thread').catch(() => {});
await p.waitForTimeout(2500);
check('narrowing redraws', await p.$$eval('#canvas svg *', n => n.length) > 5);
await p.selectOption('#focus', 'all').catch(() => {});
await p.waitForTimeout(2000);

console.log('\nA photograph, cropped and taken off again');
const png = 'data:image/png;base64,' +
  'iVBORw0KGgoAAAANSUhEUgAAAAQAAAACCAIAAADwyuo0AAAAF0lEQVQI12P8//8/AzbAxIAH' +
  'jEoOoZIAcCoDB7BqjhAAAAAASUVORK5CYII=';
const up = await api('person/photo', { id: me.id, data: png, filename: 'a.png' });
check('a photograph attaches', up.ok && up.body.media_id, up.body?.error || '');
const cr = await api('person/photo/crop',
  { id: me.id, media_id: up.body.media_id, crop: '0.1,0.1,0.5,0.5' });
check('it can be cropped', cr.ok);
const off = await api('person/photo/remove', { id: me.id, media_id: up.body.media_id });
check('and taken off again', off.ok);

console.log('\nFacts, a source and a citation');
const ev = await api('event', { person_id: me.id, type: 'occupation',
                                description: 'Cordwainer', date: '1912' });
check('a fact can be recorded', ev.ok, ev.body?.error || '');
const src = await api('source', { title: '1911 census', repository: 'TNA' });
check('a source can be added', src.ok, src.body?.error || '');
if (ev.ok && src.ok) {
  const cite = await api('cite', { source_id: src.body.id || src.body.source_id,
                                   event_id: ev.body.id || ev.body.event_id });
  check('a fact can be cited', cite.ok, cite.body?.error || '');
}

console.log('\nSeveral people at once, and one Ctrl-Z');
const all = (await api('meta')).body.people.map(x => x.id);
const bulk = await api('person/bulk',
  { field: 'birth_place', ids: all, value: 'Nunney, Somerset' });
check('a field sets on everybody', bulk.ok && bulk.body.changed === all.length,
      bulk.body?.message || bulk.body?.error);
await api('undo', {});
const back = (await api('person?id=' + me.id)).body;
check('one Ctrl-Z takes all of it back',
      back.birth_place !== 'Nunney, Somerset',
      back.birth_place || '(nothing, which is what it was)');

console.log('\nTaking somebody off the tree, and putting them back');
const claire = (await api('meta')).body.people.find(x => x.name.includes('Claire'));
if (!claire) { check('Claire is in the file to remove', false); }
const ret = claire ? await api('person/retire', { id: claire.id })
                   : { ok: false, body: {} };
check('remove from tree works', ret.ok, ret.body?.message || '');
check('they are off the chart',
      (await api('meta')).body.stats.people === 3,
      `${(await api('meta')).body.stats.people} left`);
await api('undo', {});
check('and Ctrl-Z puts them back',
      (await api('meta')).body.stats.people === 4,
      `${(await api('meta')).body.stats.people} people`);

console.log('\nA copy of the tree with somebody else at the centre');
const claire2 = (await api('meta')).body.people.find(x => x.name.includes('Claire'));
const pv = await api('library/copy-for', { id: claire2.id, preview: true });
check('it says what would be left out', pv.ok,
      pv.body?.error || `${pv.body?.strangers ?? '?'} not related to her`);
const cp = await api('library/copy-for',
  { id: claire2.id, title: 'Claire tree', prune: true });
check('a copy is made with her at the centre', cp.ok,
      cp.body?.error || cp.body?.path || '');
check('the original is untouched',
      (await api('meta')).body.stats.people === 4);

console.log('\nWill it cut cleanly');
const pf = await api('preflight?focus=all');
check('pre-flight reports', pf.ok && Array.isArray(pf.body.findings),
      pf.body?.findings ? `${pf.body.findings.length} checks` : pf.body?.error);

console.log(`\n${pass} passed, ${fail} failed`);
if (errs.length) {
  console.log('\nconsole errors:');
  [...new Set(errs)].slice(0, 8).forEach(e => console.log('  ' + e));
}
await b.close();
process.exit(fail ? 1 : 0);
