export const API = process.env.NEXT_PUBLIC_API ?? 'http://localhost:8000';
export const api = (path, body) =>
  fetch(API + path, body
    ? { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }
    : undefined
  ).then(r => r.json());
