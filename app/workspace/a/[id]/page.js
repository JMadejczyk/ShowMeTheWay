'use client';
import { useEffect, useState, use } from 'react';
import { useRouter } from 'next/navigation';
import '../../gemini.css';
import './artifact.css';
import Canvas from '@/components/Canvas';
import Drawer from '@/components/Drawer';
import { api } from '@/lib/api';

/** The roadmap as a first-class Workspace file. Chats attach to it, not the reverse. */
export default function ArtifactPage({ params }) {
  const { id } = use(params);
  const r = useRouter();
  const [rm, setRm] = useState(null);
  const [sel, setSel] = useState(null);
  const [chats, setChats] = useState([]);

  const load = () => api('/api/roadmaps/' + id).then(setRm);
  const loadChats = () => api('/api/chats?roadmap_id=' + id).then(d => Array.isArray(d) && setChats(d));
  useEffect(() => { load(); loadChats(); }, [id]);
  useEffect(() => {
    if (!rm || rm.status === 'ready' || rm.status === 'error') return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [rm?.status, id]);

  async function newChat() {
    const c = await api('/api/chats', { roadmap_id: id, title: 'About this roadmap' });
    r.push('/workspace?chat=' + c.id);
  }

  if (!rm) return <div className="af"><div className="aftop"><b>Opening…</b></div></div>;

  const patch = (nid, f) => setRm(x => ({ ...x, nodes: x.nodes.map(n => n.id === nid ? { ...n, ...f } : n) }));
  const post = b => api('/api/node', b);
  const cleared = rm.nodes.filter(n => n.status === 'done' || n.status === 'known').length;
  const known = rm.nodes.filter(n => n.status === 'known').length;

  return (
    <div className="af">
      <div className="aftop">
        <span className="aficon" onClick={() => r.push('/workspace/drive')} title="Back to Drive">◈</span>
        <div className="aftitle">
          <b>{rm.title}</b>
          <div className="afmenu"><span>File</span><span>Edit</span><span>View</span><span>Share</span></div>
        </div>
        <span className="afsaved">✓ Saved to Drive</span>
        <button className="afshare">🔒 Share</button>
        <div className="gavatar">J</div>
      </div>

      <div className="afbody">
        <div className="afcanvas">
          {rm.status === 'replanning' && <div className="banner">
            <div className="spin" /> Replanning — your progress is kept
          </div>}
          <Canvas nodes={rm.nodes} edges={rm.edges} selected={sel} onSelect={setSel}
            onMove={(nid, p) => { patch(nid, { x: p.x, y: p.y }); post({ action: 'move', id: nid, ...p }); }} />
          <Drawer node={rm.nodes.find(n => n.id === sel) ?? null}
            onClose={() => setSel(null)}
            onStatus={(nid, status) => { patch(nid, { status }); post({ action: 'status', id: nid, status }); }}
            onReplan={(anchor_id, instruction) => {
              setRm(x => ({ ...x, status: 'replanning' }));
              api(`/api/roadmaps/${id}/replan`, { anchor_id, instruction });
            }}
            replanning={rm.status === 'replanning'} />
        </div>

        <div className="afside">
          <div className="afstat">
            <b>{cleared}/{rm.nodes.length}</b> cleared
            {known ? <span> · {known} you already had</span> : null}
          </div>

          <div className="afsec">Chats about this</div>
          {chats.map(c => (
            <button key={c.id} className="afchat" onClick={() => r.push('/workspace?chat=' + c.id)}>
              <b>{c.title}</b>
              <span>{c.preview || 'No messages yet'}</span>
              <span className="afn">{c.n} messages</span>
            </button>
          ))}
          {!chats.length && <div className="afempty">
            No conversations yet. Start one to ask about this plan or tell Gemini
            what's changed — it can update the roadmap from here.
          </div>}
          <button className="afnew" onClick={newChat}>✦ New chat about this</button>

          {!!rm.sources?.length && <>
            <div className="afsec" style={{ marginTop: 20 }}>Researched from</div>
            {rm.sources.slice(0, 8).map((s, i) => (
              <a className="afsrc" key={i} href={s.url} target="_blank" rel="noreferrer">{s.title}</a>
            ))}
          </>}
        </div>
      </div>
    </div>
  );
}
