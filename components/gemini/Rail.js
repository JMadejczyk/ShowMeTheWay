'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

/** Shared left rail: New chat -> Recent (chats) -> Artifacts (roadmaps). */
export default function Rail({ activeChat, activeArtifact }) {
  const r = useRouter();
  const [chats, setChats] = useState([]);
  const [arts, setArts] = useState([]);

  useEffect(() => {
    api('/api/chats').then(d => Array.isArray(d) && setChats(d.filter(c => c.n > 0)));
    api('/api/roadmaps').then(d => Array.isArray(d) && setArts(d.filter(x => x.status !== 'clarifying')));
  }, [activeChat, activeArtifact]);

  return (
    <div className="grail">
      <button className="gburger" onClick={() => r.push('/workspace/drive')} title="Drive">☰</button>
      <button className="gnew" onClick={() => r.push('/workspace')}>✏️ New chat</button>

      <div className="gsec">Recent</div>
      {chats.slice(0, 6).map(c => (
        <button key={c.id} className={'gitem' + (activeChat === c.id ? ' on' : '')}
          title={c.preview || c.title}
          onClick={() => r.push('/workspace?chat=' + c.id)}>
          {c.title === 'New chat' ? (c.preview || 'New chat') : c.title}
        </button>
      ))}
      {!chats.length && <div className="gitem" style={{ opacity: .5 }}>No chats yet</div>}

      <div className="gsec" style={{ marginTop: 12 }}>Artifacts</div>
      {arts.map(a => (
        <button key={a.id} className={'gitem' + (activeArtifact === a.id ? ' on' : '')}
          title={a.title} onClick={() => r.push('/workspace/a/' + a.id)}>
          <span style={{ color: '#0b57d0' }}>◈</span> {a.title}
        </button>
      ))}
      {!arts.length && <div className="gitem" style={{ opacity: .5 }}>No artifacts yet</div>}

      <button className="gitem" style={{ marginTop: 14, color: '#5f6368' }}
        onClick={() => r.push('/workspace/drive')}>▦ Open Drive</button>
    </div>
  );
}
