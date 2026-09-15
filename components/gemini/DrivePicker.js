'use client';
import { useState } from 'react';
import { DRIVE, ICON } from '@/lib/drive';

const LABEL = { pdf: 'PDF', doc: 'Google Docs', sheet: 'Google Sheets' };

export default function DrivePicker({ onClose, onPick }) {
  const [sel, setSel] = useState([]);
  const [tab, setTab] = useState('recent');
  const list = tab === 'mine' ? DRIVE.filter(d => d.owner === 'me') : DRIVE;
  const toggle = id => setSel(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);

  return (
    <div className="gscrim" onClick={onClose}>
      <div className="gdlg" onClick={e => e.stopPropagation()}>
        <h4>Select a file</h4>
        <div className="gtabs">
          {[['recent', 'Recent'], ['mine', 'My Drive'], ['shared', 'Shared with me']].map(([k, l]) => (
            <button key={k} className={'gtab' + (tab === k ? ' on' : '')} onClick={() => setTab(k)}>{l}</button>
          ))}
        </div>
        <div className="gfiles">
          {list.map(f => (
            <button key={f.id} className={'gfile' + (sel.includes(f.id) ? ' sel' : '')}
              onClick={() => toggle(f.id)}>
              <span className="gdot" style={{ background: ICON[f.kind] }} />
              <span style={{ flex: 1, minWidth: 0 }}>
                <b>{f.name}</b>
                <span>{LABEL[f.kind]} · {f.owner === 'me' ? 'me' : f.owner} · {f.modified}</span>
              </span>
            </button>
          ))}
        </div>
        <div className="gdact">
          <button className="gbtn" onClick={onClose}>Cancel</button>
          <button className="gbtn p" disabled={!sel.length}
            onClick={() => { onPick(DRIVE.filter(d => sel.includes(d.id))); onClose(); }}>
            Insert
          </button>
        </div>
      </div>
    </div>
  );
}
