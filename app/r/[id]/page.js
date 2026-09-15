'use client';
import { useEffect, useState, use } from 'react';
import Canvas from '@/components/Canvas';
import Drawer from '@/components/Drawer';
import { api } from '@/lib/api';

const STAGE = {
  clarifying:  'Waiting on your answers…',
  replanning:  'Replanning…',
  researching: 'Searching the web and reading sources…',
  structuring: 'Shaping the roadmap around your background…',
};
const RUNNING = ['clarifying', 'researching', 'structuring'];
const STEPS = ['clarify', 'research', 'structure', 'persist'];

export default function Roadmap({ params }) {
  const { id } = use(params);
  const [rm, setRm] = useState(null);
  const [sel, setSel] = useState(null);

  const load = () => api('/api/roadmaps/' + id).then(setRm);
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    if (!rm || rm.status === 'ready' || rm.status === 'error') return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [rm?.status]);

  if (!rm) return <div className="shell"><div className="prog"><div className="spin" /></div></div>;

  const patch = (nid, fields) => setRm(r => ({
    ...r, nodes: r.nodes.map(n => n.id === nid ? { ...n, ...fields } : n),
  }));
  const post = body => api('/api/node', body);
  const setStatus = (nid, status) => { patch(nid, { status }); post({ action: 'status', id: nid, status }); };
  const replan = (anchor_id, instruction) => {
    setRm(r => ({ ...r, status: 'replanning' }));
    api(`/api/roadmaps/${id}/replan`, { anchor_id, instruction });
  };
  const move = (nid, p) => { patch(nid, { x: p.x, y: p.y }); post({ action: 'move', id: nid, ...p }); };

  const done = rm.nodes.filter(n => n.status === 'done' || n.status === 'known').length;
  const known = rm.nodes.filter(n => n.status === 'known').length;

  return (
    <div className="shell">
      <div className="top">
        <a href="/" style={{ textDecoration: 'none', color: 'var(--muted)' }}>←</a>
        <h2>{rm.title}</h2>
        {rm.status === 'ready' && <span className="dim">
          {done}/{rm.nodes.length} cleared{known ? ` · ${known} you already had` : ''}
        </span>}
        <div className="legend">
          <span><i className="sw" style={{ background: 'var(--core)' }} />Core</span>
          <span><i className="sw" style={{ background: 'var(--alt)' }} />Alternative</span>
          <span><i className="sw" style={{ background: 'var(--opt)' }} />Optional</span>
          <span><i className="sw" style={{ background: '#d9f7e0', borderStyle: 'dashed' }} />You already know</span>
        </div>
      </div>

      {rm.status === 'error' && <div className="prog">
        <div className="err" style={{ maxWidth: 520 }}>Generation failed: {rm.error}</div>
      </div>}

      {RUNNING.includes(rm.status) && <div className="prog">
        <div className="spin" />
        <div><strong>{STAGE[rm.status]}</strong><br />
          <span className="dim">{rm.goal}</span>
          <div className="dim" style={{ marginTop: 10, fontSize: 11.5 }}>
            {['clarify', 'research', 'structure', 'persist'].map(st => {
              const order = { clarifying: 0, researching: 1, structuring: 2, ready: 4 }[rm.status] ?? 0;
              const i = ['clarify', 'research', 'structure', 'persist'].indexOf(st);
              return <span key={st} style={{ marginRight: 10, opacity: i <= order ? 1 : .35 }}>
                {i < order ? '●' : i === order ? '◐' : '○'} {st}
              </span>;
            })}
          </div>
        </div>
      </div>}

      {(rm.status === 'ready' || rm.status === 'replanning') && <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        {rm.status === 'replanning' && <div className="banner">
          <div className="spin" /> Replanning what comes next — your progress is kept
        </div>}
        <Canvas nodes={rm.nodes} edges={rm.edges} selected={sel}
          onSelect={setSel} onMove={move} />
      </div>}

      <Drawer node={rm.nodes.find(n => n.id === sel) ?? null}
        onClose={() => setSel(null)} onStatus={setStatus}
        onReplan={replan} replanning={rm.status === 'replanning'} />
    </div>
  );
}
