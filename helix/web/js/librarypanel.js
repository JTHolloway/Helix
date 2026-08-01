// Which family is open, and where it is kept.
//
// A DESKTOP APPLICATION HAS NO ADDRESS BAR. Run from a terminal, Helix is
// handed a path and never has to think about it again; run as an app
// somebody double-clicks, this screen is the only way to start a second
// family, switch back to the first, or answer the question every genealogist
// asks within a minute of trusting a program with ten years of work —
// "where exactly is my file?"
//
// So the answer is on the screen, in full, with a button that opens the
// folder in Finder or Explorer.
import { get, post } from './api.js';

const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export async function show(host, { onOpened, onToast }) {
  host.innerHTML = '<p class="hint">Looking in your folder…</p>';
  const d = await get('library');
  const st = d.status;

  host.innerHTML = `
    <div class="lib">
      <div class="libwhere">
        <b>Your family files are kept in</b>
        <code>${esc(d.library)}</code>
        <div class="libacts">
          <button class="ghost" id="libReveal">Open this folder</button>
          <button class="ghost" id="libMove">Keep them somewhere else…</button>
        </div>
        <p class="hint">Ordinary files you can copy, back up or hand on.</p>
      </div>

      <h4>Open</h4>
      <ul class="libfams">
        ${d.families.map(f => {
          const here = f.path === d.current;
          return `<li class="${here ? 'on' : ''}">
            <button class="libopen" data-open="${esc(f.path)}"
              ${here ? 'disabled' : ''}>
              <b>${esc(f.title)}</b>
              <span>${f.people == null ? 'could not be read'
                     : `${f.people} ${f.people === 1 ? 'person' : 'people'}`}
                · ${f.size_kb} kB · ${esc(f.modified.replace('T', ' '))}
                ${f.backups ? `· ${f.backups} backups` : ''}</span>
              <small>${esc(f.name)}.helix</small>
            </button>
            ${here ? '<i class="libnow">open now</i>' : ''}
          </li>`;
        }).join('') || '<li class="none">Nothing here yet.</li>'}
      </ul>

      <h4>Whose tree is this?</h4>
      <div class="libsubj">
        ${d.subject
          ? `<b>${esc(d.subject.name)}</b>
             <span>${esc(d.subject.life || 'dates unknown')}</span>`
          : `<b class="none">Nobody chosen yet</b>`}
        <p class="hint">Every relation in the program is measured from this
          person — the sidebar, the DNA percentages and the research list.</p>
        <input id="libSubjFind" type="search" autocomplete="off"
          placeholder="${d.people ? 'Type a name to change it…'
                                  : 'Add somebody first'}"
          ${d.people ? '' : 'disabled'}>
        <div id="libSubjHits" class="libhits"></div>
      </div>

      <h4>This family</h4>
      <form class="libform" id="libRename">
        <label>What it is called
          <input id="libTitle" value="${esc(st.title || st.name)}"></label>
        <p class="hint">This renames the file on disk too.</p>
        <button class="ghost wide">Rename</button>
      </form>
      <div class="libacts">
        <button class="ghost" id="libDup">Make a copy to experiment on</button>
        <button class="ghost" id="libFor">Make this tree for somebody else…</button>
      </div>
      <p class="hint">A tree for somebody else is a file of its own with them
        at the centre. Nothing you do in it touches this one.</p>
      <dl class="libstat">
        <dt>File</dt><dd><code>${esc(st.path)}</code></dd>
        <dt>Backups</dt><dd>${st.backups}${
          st.newest_backup ? ` · newest ${esc(st.newest_backup)}` : ' — none yet'}</dd>
        <dt>Photographs</dt><dd>${st.photos} in
          <code>${esc(st.name)}-media</code></dd>
      </dl>
      <p class="hint">Every change is saved the moment you make it.</p>

      <h4>Start another</h4>
      <form class="libform" id="libNew">
        <label>A name for it
          <input id="libNewTitle" placeholder="The Whitcombes"></label>
        <button class="primary wide">Start a new family</button>
      </form>
    </div>`;

  const act = async (path, body, refresh) => {
    try {
      const r = await post(path, body);
      if (r.message) onToast(r.message);
      if (r.opened) onOpened();
      else if (refresh) show(host, { onOpened, onToast });
      return r;
    } catch (e) { onToast(e.message); }
  };

  host.querySelectorAll('[data-open]').forEach(b =>
    b.addEventListener('click', () => act('library/open', { path: b.dataset.open })));
  host.querySelector('#libReveal').addEventListener('click', () =>
    act('library/reveal', {}));
  host.querySelector('#libDup').addEventListener('click', () =>
    act('library/duplicate', {}, true));
  host.querySelector('#libFor').addEventListener('click',
    () => makeFor({ onOpened, onToast }));
  host.querySelector('#libRename').addEventListener('submit', ev => {
    ev.preventDefault();
    const t = host.querySelector('#libTitle').value.trim();
    if (t) act('library/rename', { title: t }, true).then(onOpened);
  });
  host.querySelector('#libNew').addEventListener('submit', ev => {
    ev.preventDefault();
    const t = host.querySelector('#libNewTitle').value.trim();
    if (!t) { onToast('Give it a name first.'); return; }
    act('library/new', { title: t });
  });
  // ---- whose tree it is -----------------------------------------------
  const find = host.querySelector('#libSubjFind');
  const hits = host.querySelector('#libSubjHits');
  let timer = null;
  if (find) find.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = find.value.trim();
      if (q.length < 2) { hits.innerHTML = ''; return; }
      try {
        const rows = await get('person/search', { q, limit: 8 });
        hits.innerHTML = rows.length
          ? rows.map(r => `<button class="libhit" data-subj="${esc(r.id)}">
              <b>${esc(r.name)}</b> <span>${esc(r.life || '')}</span>
            </button>`).join('')
          : '<p class="none">Nobody of that name.</p>';
        hits.querySelectorAll('[data-subj]').forEach(b =>
          b.addEventListener('click', async () => {
            try {
              await post('subject', { id: b.dataset.subj });
              onToast('The tree is now read from their side.');
              onOpened();
            } catch (e) { onToast(e.message); }
          }));
      } catch { hits.innerHTML = ''; }
    }, 200);
  });

  host.querySelector('#libMove').addEventListener('click', async () => {
    // NO NATIVE FOLDER PICKER IN A WEB PAGE, and the one browsers offer
    // hands over the files rather than the path. So this asks — and shows
    // the current folder as the starting point, which is most of what a
    // picker would have done.
    const cur = d.library;
    const next = window.prompt(
      'Which folder should Helix keep family files in?\n\n' +
      'The files already there stay where they are — this only changes ' +
      'where new ones go and where Helix looks.', cur);
    if (next && next.trim() && next.trim() !== cur) {
      act('library/folder', { path: next.trim() }, true);
    }
  });
}


// ─────────────────── the same family, as somebody else's tree ─────────────
//
// WHY THIS IS NOT A SETTING. Every relation in the program is measured from
// one person: who counts as a cousin, whose lines are worth researching,
// what the chart puts at its centre, what the record book calls each entry.
// Change that person and you do not have a preference set differently — you
// have a different document about the same family.
//
// So a niece who wants her own tree gets a FILE OF HER OWN, and the original
// is not touched, not linked to and never consulted again. That is what
// makes it safe to hand over.
export async function makeFor({ onOpened, onToast }) {
  const dlg = document.querySelector('#forDlg');
  const body = document.querySelector('#forBody');
  const find = document.querySelector('#forFind');
  let chosen = null, plan = null;
  find.value = '';
  body.innerHTML = '<p class="hint">Find the person whose tree it will be.</p>';
  dlg.showModal();
  find.focus();

  let t = null;
  find.oninput = () => {
    clearTimeout(t);
    t = setTimeout(async () => {
      const q = find.value.trim();
      if (q.length < 2) return;
      const rows = await get('person/search', { q, limit: 8 });
      body.innerHTML = rows.length
        ? `<div class="libhits">${rows.map(r =>
            `<button class="libhit" data-pick="${esc(r.id)}"><b>${esc(r.name)}</b>
              <span>${esc(r.life || '')}</span></button>`).join('')}</div>`
        : '<p class="none">Nobody of that name in this file.</p>';
      body.querySelectorAll('[data-pick]').forEach(b =>
        b.addEventListener('click', () => pick(b.dataset.pick)));
    }, 200);
  };

  async function pick(id) {
    chosen = id;
    body.innerHTML = '<p class="hint">Working out what their tree looks like…</p>';
    plan = await post('library/copy-for', { id, preview: true });
    // THE QUESTION, WITH REAL NAMES IN IT. "Leave out 34 people" is a number
    // nobody can check; "Michaela Denton's own family, 34 people" is a
    // decision somebody can actually make.
    body.innerHTML = `
      <div class="forwho"><b>${esc(plan.root.name)}</b>
        <span>${esc(plan.root.life || 'dates unknown')}</span></div>
      <label class="forname">What to call the new file
        <input id="forTitle" value="${esc(plan.title)}"></label>
      ${plan.branches.length ? `
        <p class="forq">These ${plan.unrelated} people are in your file and
          are no relation to ${esc(firstName(plan.root.name))} — they married
          into <em>your</em> family, not hers. Leave them out?</p>
        <ul class="forbranch">${plan.branches.map(b => `<li>
          <b>${esc(b.label)}</b> <span>${esc(b.blurb)}</span>
          <small>${b.names.map(esc).join(', ')}${
            b.count > b.names.length ? '…' : ''}</small></li>`).join('')}</ul>
        <label class="check"><input type="checkbox" id="forPrune" checked>
          Leave these ${plan.unrelated} out of the new file</label>
        <p class="hint">Nothing is deleted. They stay in your file, and one
          Ctrl-Z in the new one brings them back.</p>`
        : `<p class="hint">Everybody in this file is related to
           ${esc(firstName(plan.root.name))} one way or another, so the new
           tree gets all ${plan.people} of them.</p>`}
      <div class="exports">
        <button class="primary" id="forGo">Make it</button>
      </div>`;
    body.querySelector('#forGo').addEventListener('click', go);
  }

  async function go() {
    const btn = body.querySelector('#forGo');
    btn.disabled = true; btn.textContent = 'Making it…';
    try {
      const r = await post('library/copy-for', {
        id: chosen,
        title: body.querySelector('#forTitle').value.trim(),
        prune: !!body.querySelector('#forPrune')?.checked,
      });
      dlg.close();
      onToast(r.message);
      // Deliberately NOT opened. The point of the feature is that this file
      // carries on being yours; switching you into somebody else's tree
      // without being asked is the one thing it must not do.
      show(document.querySelector('#libBody'), { onOpened, onToast });
    } catch (e) {
      onToast(e.message);
      btn.disabled = false; btn.textContent = 'Make it';
    }
  }
}

const firstName = n => String(n || '').trim().split(/\s+/)[0] || 'them';
