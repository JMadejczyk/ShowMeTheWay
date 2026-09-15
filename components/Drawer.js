'use client';
import { useEffect, useState } from 'react';
import { marked } from 'marked';
import { api } from '@/lib/api';

const STATES = [['todo', 'To do'], ['doing', 'In progress'], ['done', 'Done'], ['known', 'Already know this']];

export default function Drawer({ node, onClose, onStatus, onReplan, replanning }) {
  const [detail, setDetail] = useState(null);
  const [sources, setSources] = useState([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setDetail(null); setSources(node?.sources ?? []); setNote(''); setOpen(false);
    if (!node) return;
    let dead = false;
    setBusy(true);
    api('/api/node', { action: 'detail', id: node.id }).then(d => {
      if (dead) return;
      setDetail(d.detail ?? ('_' + (d.error ?? 'failed') + '_'));
      if (d.sources?.length) setSources(d.sources);
      setBusy(false);
    }).catch(e => { if (!dead) { setDetail('_' + e.message + '_'); setBusy(false); } });
    return () => { dead = true; };
  }, [node?.id]);

  if (!node) return null;
  const cleared = node.status === 'known' || node.status === 'done';

  return (
    <div className="drawer">
      <div className="dhead">
        <button className="x" onClick={onClose}>×</button>
        <h3 style={{ paddingRight: 28 }}>{node.title}</h3>
        <div className="statusrow">
          {STATES.map(([k, label]) => (
            <button key={k} className={'chip' + (node.status === k ? ' on' : '')}
              onClick={() => onStatus(node.id, k)}>{label}</button>
          ))}
        </div>

        {cleared && <div className="replan">
          {!open ? (
            <button className="btn ghost small" disabled={replanning} onClick={() => setOpen(true)}>
              ↻ Replan everything after this
            </button>
          ) : (
            <>
              <div className="dim" style={{ marginBottom: 6 }}>
                Rebuilds the steps after this one. Everything before it — and your
                progress and notes on steps that survive — is kept.
              </div>
              <input type="text" value={note} onChange={e => setNote(e.target.value)}
                placeholder="Anything else that changed? (optional, e.g. 'I already hold a Class 1 medical')" />
              <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                <button className="btn small" disabled={replanning}
                  onClick={() => { onReplan(node.id, note); setOpen(false); }}>
                  {replanning ? 'Replanning…' : 'Replan downstream'}
                </button>
                <button className="btn ghost small" onClick={() => setOpen(false)}>Cancel</button>
              </div>
            </>
          )}
        </div>}
      </div>

      <div className="dbody">
        {node.status === 'known' && node.why_known &&
          <div className="known-note"><strong>Pre-marked as known.</strong> {node.why_known}</div>}
        <p style={{ marginTop: 0, fontSize: 14 }}>{node.summary}</p>
        {busy && <p className="dim">Researching this step…</p>}
        {detail && <div dangerouslySetInnerHTML={{ __html: marked.parse(detail) }} />}
        {sources.length > 0 && <>
          <h3>Sources</h3>
          {sources.map((s, i) => (
            <a className="src" key={i} href={s.url} target="_blank" rel="noreferrer">
              {s.title || s.url}<span>{s.url}</span>
            </a>
          ))}
        </>}
      </div>
    </div>
  );
}
