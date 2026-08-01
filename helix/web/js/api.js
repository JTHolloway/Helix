// Thin wrapper over the local API. Every call surfaces a readable message
// rather than a stack trace: the user should never see the plumbing.
export async function get(path, params = {}) {
  const q = new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) =>
      v !== undefined && v !== null && v !== ''))).toString();
  const r = await fetch(`/api/${path}${q ? '?' + q : ''}`);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  return r.json();
}
export async function post(path, body) {
  const r = await fetch(`/api/${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  return r.json();
}
export function svgUrl(params) {
  const q = new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v != null)));
  return `/api/svg?${q}`;
}
