'use client';
import { useEffect, useState } from 'react';
import Canvas from '@/components/Canvas';
import Drawer from '@/components/Drawer';
import { api } from '@/lib/api';

/** The roadmap as a Canvas-style artifact panel beside the chat. */
export default function Artifact({ id, onClose }) {
  const [rm, setRm] = useState(null);
  const [sel, setSel] = useState(null);

  const load = () => api('/api/roadmaps/' + id).then(setRm);
  useEffect(() => { setRm(null); setSel(null); load(); }, [id]);
  useEffect(() => {
    const enriching = rm && rm.enrich_total > 0 && rm.enriched < rm.enrich_total;
    if (!rm || (!enriching && (rm.status === 'ready' || rm.status === 'error'))) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [rm?.status, id]);

  if (!rm) return <div className="gcanvas"><div className="gchead"><b>Opening…</b></div></div>;

  const patch = (nid, f) => setRm(r => ({ ...r, nodes: r.nodes.map(n => n.id === nid ? { ...n, ...f } : n) }));
  const post = b => api('/api/node', b);
  const cleared = rm.nodes.filter(n => n.status === 'done' || n.status === 'known').length;
  const known = rm.nodes.filter(n => n.status === 'known').length;

  return (
    <div className="gcanvas">
      <div className="gchead">
        <span style={{ color: '#0b57d0', fontSize: 17 }}>◈</span>
        <b>{rm.title}</b>
        <span className="gtagline">{cleared}/{rm.nodes.length} cleared{known ? ` · ${known} you already had` : ''}</span>
        {rm.enrich_total > 0 && rm.enriched < rm.enrich_total &&
          <span className="gtagline">researching {rm.enriched}/{rm.enrich_total}</span>}
        <span className="gsaved">✓ Saved to Drive</span>
        <button className="gicon" onClick={onClose}>✕</button>
      </div>
      <div className="gcbody">
        {rm.status === 'replanning' && <div className="banner">
          <div className="spin" /> Replanning — your progress is kept
        </div>}
        <Canvas nodes={rm.nodes} edges={rm.edges} selected={sel} onSelect={setSel}
          onMove={(nid, p) => { patch(nid, { x: p.x, y: p.y }); post({ action: 'move', id: nid, ...p }); }} />
        <Drawer node={rm.nodes.find(n => n.id === sel) ?? null}
          onClose={() => setSel(null)}
          onStatus={(nid, status) => { patch(nid, { status }); post({ action: 'status', id: nid, status }); }}
          onReplan={(anchor_id, instruction) => {
            setRm(r => ({ ...r, status: 'replanning' }));
            api(`/api/roadmaps/${id}/replan`, { anchor_id, instruction });
          }}
          replanning={rm.status === 'replanning'} />
      </div>
    </div>
  );
}
