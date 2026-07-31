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
        <p class="hint">Ordinary files in an ordinary folder — copy them to a
          memory stick, put them in Dropbox, hand them to somebody. Nothing
          here is locked inside Helix.</p>
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

      <h4>This family</h4>
      <form class="libform" id="libRename">
        <label>What it is called
          <input id="libTitle" value="${esc(st.title || st.name)}"></label>
        <p class="hint">Changing this renames the file on disk too, so the
          folder never fills up with <code>family2.helix</code>.</p>
        <button class="ghost wide">Rename</button>
      </form>
      <div class="libacts">
        <button class="ghost" id="libDup">Make a copy to experiment on</button>
      </div>
      <dl class="libstat">
        <dt>File</dt><dd><code>${esc(st.path)}</code></dd>
        <dt>Backups</dt><dd>${st.backups}${
          st.newest_backup ? ` · newest ${esc(st.newest_backup)}` : ' — none yet'}</dd>
        <dt>Photographs</dt><dd>${st.photos} in
          <code>${esc(st.name)}-media</code></dd>
      </dl>
      <p class="hint">Every change is written the moment you make it. There is
        no Save button because there is never anything unsaved.</p>

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
