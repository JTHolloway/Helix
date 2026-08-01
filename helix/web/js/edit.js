// Adding people, and removing them.
//
// One dialogue does every relationship. It already knows who it is attaching
// to and how, so it never asks — you stand on somebody and add the next
// person relative to them.
//
// The word "union" must never appear here. The screen says partner, married,
// together; the schema's word stays behind the API.
import { get, post } from './api.js';

const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// What the dialogue calls itself, and whether a surname is worth guessing.
// Pre-filled where it is the sensible guess and blank where it is not: a
// father and a brother usually share a surname, a mother and a wife usually
// do not. Always editable either way.
const KIND = {
  father:  { title: n => `Add ${poss(n)} father`,             surname: 'same' },
  mother:  { title: n => `Add ${poss(n)} mother`,             surname: 'none' },
  partner: { title: n => `Add ${poss(n)} partner`,            surname: 'none' },
  child:   { title: n => `Add ${poss(n)} child`,              surname: 'if-man' },
  sibling: { title: n => `Add ${poss(n)} brother or sister`,  surname: 'same' },
};

const poss = n => /s$/i.test(n) ? `${n}'` : `${n}'s`;

/** Open the add dialogue. `ctx` is { to, as, toName, toSurname, toSex, union }. */
export function addPerson(ctx, onDone) {
  const kind = KIND[ctx.as] || KIND.child;
  const guess = kind.surname === 'same' ? ctx.toSurname
    : kind.surname === 'if-man' && ctx.toSex === 'M' ? ctx.toSurname : '';

  const dlg = document.createElement('dialog');
  dlg.className = 'addDlg';
  dlg.innerHTML = `
    <h2>${esc(kind.title(ctx.toName || 'this person'))}</h2>
    <label>Given names <input id="aGiven" autocomplete="off" autofocus></label>
    <label>Surname <input id="aSur" autocomplete="off" value="${esc(guess)}"></label>
    <div id="dupe" class="dupe" hidden></div>
    <label>Born <input id="aBirth" autocomplete="off"
      placeholder="12 March 1841 — or just 1841"><small id="eBirth" class="echo"></small></label>
    <label>Died <input id="aDeath" autocomplete="off"
      placeholder="3 Feb 1900 — or just 1900"><small id="eDeath" class="echo"></small></label>
    <label>Born in <input id="aPlace" autocomplete="off"></label>
    <fieldset class="sexes">
      <label><input type="radio" name="sex" value="M"> Man</label>
      <label><input type="radio" name="sex" value="F"> Woman</label>
      <label><input type="radio" name="sex" value="U" checked> Not recorded</label>
    </fieldset>
    <p class="hint">Only a name is needed. Put the whole date in if you have
      it — <b>12 March 1841</b>, <b>1st Mar 1841</b>, <b>12/03/1841</b> are all
      read the same way. Where only part is known, say only that much:
      <b>Mar 1841</b>, <b>abt 1834</b>, <b>bef 1900</b>,
      <b>bet 1820 and 1825</b>, <b>Q3 1871</b>.</p>
    <p class="hint keys">Without the mouse: <kbd>Enter</kbd> adds,
      <kbd>Shift</kbd>+<kbd>Enter</kbd> adds and starts the next one,
      <kbd>Alt</kbd>+<kbd>M</kbd> / <kbd>F</kbd> / <kbd>U</kbd> sets who they
      were, <kbd>Esc</kbd> closes.</p>
    <div class="row">
      <button class="primary" id="aAdd">Add <kbd>↵</kbd></button>
      <button class="ghost" id="aAgain">Add and add another
        <kbd>⇧↵</kbd></button>
      <button class="ghost" id="aCancel">Cancel</button>
    </div>`;
  document.body.appendChild(dlg);
  dlg.showModal();

  const $ = s => dlg.querySelector(s);
  const close = () => { dlg.close(); dlg.remove(); };

  // ---- the live echo: typing `abt 1834` shows "about 1834" ---------------
  for (const [field, out] of [['#aBirth', '#eBirth'], ['#aDeath', '#eDeath']]) {
    $(field).addEventListener('input', debounce(async e => {
      const v = e.target.value.trim();
      if (!v) { $(out).textContent = ''; return; }
      try { $(out).textContent = (await get('date', { q: v })).text; }
      catch { $(out).textContent = ''; }
    }, 180));
  }

  // ---- the duplicate check ----------------------------------------------
  // Duplicate people are the commonest way a tree goes wrong, so this runs
  // while you type rather than complaining after you have saved.
  const checkDupes = debounce(async () => {
    const q = `${$('#aGiven').value} ${$('#aSur').value}`.trim();
    const box = $('#dupe');
    if (q.length < 3) { box.hidden = true; return; }
    let hits = [];
    try { hits = await get('person/search', { q }); } catch { /* offline */ }
    if (!hits.length) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML = `<p>Did you mean somebody already in your file?</p>` +
      hits.slice(0, 3).map(h => `<button class="ghost linkBtn" data-id="${esc(h.id)}">
        ${esc(h.name)} <small>${esc(h.life || 'dates unknown')}</small>
        — link to them instead</button>`).join('');
    box.querySelectorAll('.linkBtn').forEach(b =>
      b.addEventListener('click', async () => {
        await post('person/link', {
          id: b.dataset.id,
          attach: { to: ctx.to, as: ctx.as, union: ctx.union || null }
        });
        close();
        onDone(b.dataset.id);
      }));
  }, 220);
  $('#aGiven').addEventListener('input', checkDupes);
  $('#aSur').addEventListener('input', checkDupes);

  // ---- saving ------------------------------------------------------------
  async function save(again) {
    const body = {
      given: $('#aGiven').value.trim(),
      surname: $('#aSur').value.trim(),
      sex: dlg.querySelector('input[name=sex]:checked').value,
      birth: $('#aBirth').value.trim(),
      death: $('#aDeath').value.trim(),
      birth_place: $('#aPlace').value.trim(),
      attach: { to: ctx.to, as: ctx.as, union: ctx.union || null },
    };
    if (!body.given && !body.surname) { $('#aGiven').focus(); return; }
    const r = await post('person/new', body);
    if (again) {
      // Siblings and children come in runs, so keep the dialogue open with
      // the same relationship and clear only what changes person to person.
      for (const f of ['#aGiven', '#aBirth', '#aDeath', '#aPlace']) $(f).value = '';
      $('#eBirth').textContent = $('#eDeath').textContent = '';
      $('#dupe').hidden = true;
      $('#aGiven').focus();
      onDone(r.id, { keepOpen: true, warnings: r.warnings });
      return;
    }
    close();
    onDone(r.id, { warnings: r.warnings });
  }

  $('#aAdd').addEventListener('click', e => { e.preventDefault(); save(false); });
  $('#aAgain').addEventListener('click', e => { e.preventDefault(); save(true); });
  $('#aCancel').addEventListener('click', e => { e.preventDefault(); close(); });

  // ---- entering a family without touching the mouse ----------------------
  //
  // WHY THIS MATTERS MORE THAN IT LOOKS. Somebody typing in a census page
  // adds nine children in a row, and reaching for the mouse between each one
  // is where data entry stops. Enter alone saved and closed, so a run of
  // siblings meant nine trips to a button eleven inches away.
  //
  //   Enter          add and close
  //   Shift+Enter    add and start the next one, same relationship
  //   Alt+M/F/U      who they were, without leaving the name field
  //   Escape         close (the dialog element's own behaviour)
  dlg.addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT'
        && e.target.type !== 'radio') {
      e.preventDefault();
      save(e.shiftKey || e.ctrlKey || e.metaKey);
      return;
    }
    if (e.altKey && !e.ctrlKey && !e.metaKey) {
      const sex = { m: 'M', f: 'F', u: 'U' }[e.key.toLowerCase()];
      if (sex) {
        e.preventDefault();
        const r = dlg.querySelector(`input[name=sex][value=${sex}]`);
        if (r) {
          r.checked = true;
          // Say so where the eye already is. A radio changing three inches
          // below the caret is a change nobody sees.
          flash(dlg, { M: 'man', F: 'woman', U: 'not recorded' }[sex]);
        }
      }
    }
  });
  dlg.addEventListener('cancel', () => dlg.remove());
}

/** "Remove from tree" — marks inactive, never deletes. */
export async function retire(pid, name, onDone) {
  const ok = confirm(
    `Take ${name} off the chart?\n\n` +
    `Nothing is deleted — the record stays in your file and Ctrl-Z puts ` +
    `them back.`);
  if (!ok) return;
  const r = await post('person/retire', { id: pid });
  onDone(r.message);
}

function debounce(fn, ms) {
  let t = null;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

/** A word that appears by the caret for a moment and goes. */
function flash(dlg, text) {
  let el = dlg.querySelector('.kbdflash');
  if (!el) {
    el = document.createElement('b');
    el.className = 'kbdflash';
    dlg.querySelector('.sexes').appendChild(el);
  }
  el.textContent = text;
  el.classList.remove('go');
  void el.offsetWidth;            // restart the animation
  el.classList.add('go');
}
