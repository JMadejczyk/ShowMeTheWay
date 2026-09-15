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
  const [qa, setQa] = useState([]);
  const [q, setQ] = useState('');
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    setDetail(null); setSources(node?.sources ?? []); setNote(''); setOpen(false);
    setQa([]); setQ(''); setAsking(false);
    if (!node) return;
    let dead = false;
    api('/api/node', { action: 'qa', id: node.id })
      .then(d => { if (!dead && d.qa?.length) setQa(d.qa); });
    setBusy(true);
    api('/api/node', { action: 'detail', id: node.id }).then(d => {
      if (dead) return;
      setDetail(d.detail ?? ('_' + (d.error ?? 'failed') + '_'));
      if (d.sources?.length) setSources(d.sources);
      setBusy(false);
    }).catch(e => { if (!dead) { setDetail('_' + e.message + '_'); setBusy(false); } });
    return () => { dead = true; };
  }, [node?.id]);

  async function ask(text) {
    const question = (text ?? q).trim();
    if (!question || asking) return;
    setAsking(true); setQ('');
    setQa(t => [...t, { id: 'pending', q: question, a: null }]);
    const d = await api('/api/node', { action: 'ask', id: node.id, question });
    setQa(t => t.filter(x => x.id !== 'pending').concat({
      id: Math.random().toString(36).slice(2), q: question,
      a: d.a ?? ('_' + (d.error ?? 'failed') + '_'),
      sources: d.sources ?? [], grounded: d.grounded,
    }));
    setAsking(false);
  }

  if (!node) return null;
  const cleared = node.status === 'known' || node.status === 'done';
  const STARTERS = ['Why do I need this?', 'Can I skip it?', 'How long will this take me?'];

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

        {qa.length > 0 && <div className="thread">
          {qa.map(x => (
            <div key={x.id} className="qa">
              <div className="qq">{x.q}</div>
              {x.a === null
                ? <div className="dim">Thinking…</div>
                : <>
                    <div className="aa" dangerouslySetInnerHTML={{ __html: marked.parse(x.a) }} />
                    {(x.sources ?? []).length > 0 &&
                      <div className="tag">searched the web · {x.sources.length} sources</div>}
                    {(x.sources ?? []).slice(0, 4).map((s, i) => (
                      <a className="src" key={i} href={s.url} target="_blank" rel="noreferrer">
                        {s.title || s.url}<span>{s.url}</span>
                      </a>
                    ))}
                  </>}
            </div>
          ))}
        </div>}
      </div>

      <div className="askbar">
        {qa.length === 0 && !asking && <div className="starters">
          {STARTERS.map(t => (
            <button key={t} className="chip" onClick={() => ask(t)}>{t}</button>
          ))}
        </div>}
        <form className="askrow" onSubmit={e => { e.preventDefault(); ask(); }}>
          <input type="text" value={q} disabled={asking}
            onChange={e => setQ(e.target.value)}
            placeholder={asking ? 'Thinking…' : 'Ask about this step…'} />
          <button className="btn" type="submit" disabled={asking || !q.trim()}>
            {asking ? '…' : 'Ask'}
          </button>
        </form>
      </div>
    </div>
  );
}
