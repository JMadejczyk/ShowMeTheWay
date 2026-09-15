'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import '../gemini.css';
import './drive.css';
import { api } from '@/lib/api';
import { DRIVE, ICON } from '@/lib/drive';

const NAV = [['my', 'My Drive', '▤'], ['shared', 'Shared with me', '👥'],
             ['recent', 'Recent', '🕘'], ['starred', 'Starred', '☆'], ['bin', 'Bin', '🗑']];
const TYPE = { pdf: 'PDF', doc: 'Google Docs', sheet: 'Google Sheets' };
const when = ms => {
  const d = Math.floor((Date.now() - ms) / 86400000);
  return d <= 0 ? 'Today' : d === 1 ? 'Yesterday'
    : new Date(ms).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
};

export default function Drive() {
  const r = useRouter();
  const [arts, setArts] = useState([]);
  const [nav, setNav] = useState('my');
  const [view, setView] = useState('grid');

  useEffect(() => {
    api('/api/roadmaps').then(d => Array.isArray(d) &&
      setArts(d.filter(x => x.status !== 'clarifying')));
  }, []);

  // roadmap artifacts and the same canned documents the Gemini picker offers
  const files = [
    ...arts.map(a => ({ id: a.id, name: a.title, kind: 'roadmap', owner: 'me',
                        modified: when(a.created), artifact: true })),
    ...DRIVE.map(d => ({ ...d, artifact: false })),
  ].filter(f => nav === 'shared' ? f.owner === 'shared with me'
             : nav === 'starred' ? f.artifact
             : nav === 'bin' ? false : true);

  const openFile = f => f.artifact && r.push('/workspace/a/' + f.id);

  return (
    <div className="dr">
      <div className="drtop">
        <span className="drburger" onClick={() => r.push('/workspace')}>☰</span>
        <span className="drlogo"><b style={{ color: '#4285f4' }}>▲</b> Drive</span>
        <div className="drsearch">🔍 <input placeholder="Search in Drive" readOnly /></div>
        <div className="drapps" onClick={() => r.push('/workspace')} title="Gemini">⋮⋮⋮</div>
        <div className="gavatar">J</div>
      </div>

      <div className="drbody">
        <div className="drnav">
          <button className="drnew">＋ New</button>
          {NAV.map(([k, label, icon]) => (
            <button key={k} className={'drnavi' + (nav === k ? ' on' : '')} onClick={() => setNav(k)}>
              <span>{icon}</span>{label}
            </button>
          ))}
          <div className="drquota">
            <div className="drbar"><i style={{ width: '38%' }} /></div>
            5.7 GB of 15 GB used
          </div>
        </div>

        <div className="drmain">
          <div className="drhead">
            <h1>{NAV.find(n => n[0] === nav)[1]}</h1>
            <div className="drviews">
              <button className={view === 'list' ? 'on' : ''} onClick={() => setView('list')}>☰</button>
              <button className={view === 'grid' ? 'on' : ''} onClick={() => setView('grid')}>▦</button>
            </div>
          </div>

          {!!arts.length && nav === 'my' && <>
            <div className="drsec">Suggested</div>
            <div className="drsugg">
              {arts.slice(0, 3).map(a => (
                <button className="drcard" key={a.id} onClick={() => r.push('/workspace/a/' + a.id)}>
                  <div className="drthumb">◈</div>
                  <div className="drmeta">
                    <b>{a.title}</b>
                    <span>Gemini artifact · you opened recently</span>
                  </div>
                </button>
              ))}
            </div>
          </>}

          <div className="drsec">Files</div>
          {view === 'grid' ? (
            <div className="drgrid">
              {files.map(f => (
                <button key={f.id} className={'drtile' + (f.artifact ? ' art' : '')}
                  onDoubleClick={() => openFile(f)} onClick={() => openFile(f)}>
                  <div className="drtname">
                    <span className="gdot" style={{ background: f.artifact ? '#0b57d0' : ICON[f.kind] }} />
                    <b>{f.name}</b>
                  </div>
                  <div className="drprev">{f.artifact ? '◈' : f.kind === 'sheet' ? '▦' : '▤'}</div>
                  <div className="drtfoot">{f.artifact ? 'Roadmap' : TYPE[f.kind]} · {f.modified}</div>
                </button>
              ))}
            </div>
          ) : (
            <div className="drlist">
              <div className="drrow drh"><span>Name</span><span>Owner</span><span>Last modified</span></div>
              {files.map(f => (
                <button key={f.id} className="drrow" onClick={() => openFile(f)}>
                  <span className="drn">
                    <span className="gdot" style={{ background: f.artifact ? '#0b57d0' : ICON[f.kind] }} />
                    {f.name}
                  </span>
                  <span>{f.owner === 'me' ? 'me' : f.owner}</span>
                  <span>{f.modified}</span>
                </button>
              ))}
            </div>
          )}
          <div className="drfoot">Prototype — not affiliated with Google.</div>
        </div>
      </div>
    </div>
  );
}
