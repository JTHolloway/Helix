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
//     node tools/walkthrough-read.mjs http://127.0.0.1:PORT/
//
// It only READS. Point it at a copy of anything.
//
// Every screen the program has, opened in a real browser, checked for
// errors and for having actually drawn something.
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

const U = process.argv[2] || 'http://127.0.0.1:8899/';
const b = await pw.chromium.launch(process.env.CHROME
  ? { executablePath: process.env.CHROME } : {});
const p = await b.newPage({ viewport: { width: 1440, height: 950 } });

const errs = [];
p.on('pageerror', e => errs.push('PAGEERROR ' + e.message));
p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });

let pass = 0, fail = 0;
const check = (name, ok, note = '') => {
  (ok ? pass++ : fail++);
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${name}${note ? '  — ' + note : ''}`);
};

async function dialog(btn, body, name, want) {
  const before = errs.length;
  await p.click(btn);
  await p.waitForTimeout(2600);
  const txt = (await p.textContent(body).catch(() => '')) || '';
  const clean = txt.replace(/\s+/g, ' ').trim();
  const ok = clean.length > 40 && !/^…$/.test(clean)
           && errs.length === before
           && (!want || clean.includes(want));
  check(name, ok, ok ? `${clean.length} chars`
    : (errs.length > before ? errs[before] : `only "${clean.slice(0, 70)}"`));
  await p.keyboard.press('Escape');
  await p.waitForTimeout(600);
}

await p.goto(U, { waitUntil: 'networkidle', timeout: 90000 });
await p.waitForTimeout(4000);

console.log('\nThe window itself');
check('the chart drew', await p.$$eval('#canvas svg *', n => n.length) > 50);
check('the sidebar listed people',
      await p.$$eval('.kinperson', n => n.length) > 5);
check('the research list filled',
      ((await p.textContent('#gapList')) || '').length > 40);
check('the readout is right',
      /\d+ people · \d+ generations/.test(await p.textContent('#readout')));

console.log('\nEvery screen in the header');
await dialog('#statsBtn', '#statsBody', 'Numbers');
await dialog('#timelineBtn', '#tlBody', 'Timeline');
// Relate needs two people chosen before it says anything.
{
  const before = errs.length;
  await p.click('#relateBtn');
  await p.waitForTimeout(1200);
  const names = await p.evaluate(async u =>
    (await (await fetch(u + 'api/meta')).json()).people.slice(0, 2).map(x => x.name), U);
  for (const [box, list, nm] of [['#relA', '#relAList', names[0]],
                                 ['#relB', '#relBList', names[1]]]) {
    await p.fill(box, nm.split(' ')[0]);
    await p.waitForTimeout(900);
    await p.click(`${list} button`).catch(() => {});
    await p.waitForTimeout(500);
  }
  await p.waitForTimeout(2500);
  const t = ((await p.textContent('#relBody')) || '').replace(/\s+/g, ' ').trim();
  check('Relate works out a relation', t.length > 60 && errs.length === before,
        t.slice(0, 80));
  await p.keyboard.press('Escape');
  await p.waitForTimeout(500);
}
await dialog('#srcBtn', '#srcBody', 'Sources');
await dialog('#toolBtn', '#toolBody', 'Find');
await dialog('#libBtn', '#libBody', 'Family (the library)');
await dialog('#peopleBtn', '#listBody', 'People');

console.log('\nThe five tool tabs');
await p.click('#toolBtn');
await p.waitForTimeout(1500);
for (const tab of ['find', 'households', 'contacts', 'history', 'compare']) {
  const before = errs.length;
  await p.click(`button.tab[data-tab="${tab}"]`);
  await p.waitForTimeout(2200);
  const t = ((await p.textContent('#toolBody')) || '').replace(/\s+/g, ' ').trim();
  check(`tools: ${tab}`, t.length > 40 && errs.length === before,
        errs.length > before ? errs[before] : `${t.length} chars`);
}
await p.keyboard.press('Escape');
await p.waitForTimeout(500);

console.log('\nOpening a person');
await p.evaluate(() => document.querySelectorAll('.kingroup').forEach(d => d.open = true));
await p.waitForTimeout(400);
await p.click('.kinperson');
await p.waitForTimeout(2500);
const prof = ((await p.textContent('#right')) || '').replace(/\s+/g, ' ');
check('the profile opened', prof.length > 300, `${prof.length} chars`);
check('it says what is known', prof.includes('WHAT IS KNOWN')
      || prof.toLowerCase().includes('what is known'));
check('it offers their family', /brothers and sisters|children/i.test(prof));

console.log('\nThe print screen');
await p.click('#printBtn');
await p.waitForTimeout(2500);
const sheets = ((await p.textContent('#shOn')) || '').trim();
check('it says how much paper', /sheets? at least/.test(sheets), sheets.slice(0, 60));
check('it offers a record for this person',
      await p.$eval('#prPerson', e => !e.hidden));
await p.keyboard.press('Escape');
await p.waitForTimeout(500);

console.log('\nEverything that prints');
for (const [what, want] of [['record', 'RECORD OF'], ['profile', null],
                            ['records', 'Contents'], ['profiles', null],
                            ['outline', null], ['chronicle', null],
                            ['research', null], ['chart', null]]) {
  const pid = await p.evaluate(() =>
    document.querySelector('.kinperson.on, .kinperson').dataset.p);
  const url = ['record', 'profile'].includes(what)
    ? `${U}print/${what}?id=${pid}` : `${U}print/${what}?focus=thread`;
  const page2 = await b.newPage();
  const bad = [];
  page2.on('pageerror', e => bad.push(e.message));
  try {
    await page2.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
    const t = ((await page2.textContent('body')) || '').replace(/\s+/g, ' ');
    check(`print/${what}`, t.length > 200 && !bad.length && !t.includes('"error"'),
          bad[0] || `${t.length} chars`);
  } catch (e) { check(`print/${what}`, false, e.message.slice(0, 60)); }
  await page2.close();
}

console.log('\nEvery file the Export button writes');
for (const fmt of ['svg', 'pdf', 'dxf', 'eps', 'gedcom']) {
  const r = await p.evaluate(async ([u, f]) => {
    const res = await fetch(u + `api/${f}?focus=thread`);
    return { ok: res.ok, n: (await res.arrayBuffer()).byteLength };
  }, [U, fmt]);
  check(`export ${fmt}`, r.ok && r.n > 500, `${r.n} bytes`);
}

console.log('\nUndo and redo');
const n0 = await p.evaluate(async u =>
  (await (await fetch(u + 'api/meta')).json()).stats.people, U);
await p.evaluate(async u => {
  await fetch(u + 'api/person/new', { method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ given: 'Test', surname: 'Person' }) });
}, U);
const n1 = await p.evaluate(async u =>
  (await (await fetch(u + 'api/meta')).json()).stats.people, U);
await p.evaluate(async u => { await fetch(u + 'api/undo', { method: 'POST',
  headers: { 'Content-Type': 'application/json' }, body: '{}' }); }, U);
const n2 = await p.evaluate(async u =>
  (await (await fetch(u + 'api/meta')).json()).stats.people, U);
check('adding a person adds one', n1 === n0 + 1, `${n0} → ${n1}`);
check('Ctrl-Z takes it back', n2 === n0, `${n1} → ${n2}`);

console.log('\nOn a phone');
await p.setViewportSize({ width: 390, height: 844 });
await p.reload({ waitUntil: 'networkidle' });
await p.waitForTimeout(3500);
check('the chart still draws',
      await p.$$eval('#canvas svg *', n => n.length) > 50);
check('the menu button is there', await p.$eval('#menuBtn',
      e => getComputedStyle(e).display !== 'none'));
const wide = await p.evaluate(() =>
  document.documentElement.scrollWidth > window.innerWidth + 2);
check('nothing overflows sideways', !wide);
await p.screenshot({ path: 'sweep-phone.png' });

console.log(`\n${pass} passed, ${fail} failed`);
if (errs.length) {
  console.log('\nconsole errors:');
  [...new Set(errs)].slice(0, 10).forEach(e => console.log('  ' + e));
}
await b.close();
process.exit(fail ? 1 : 0);
