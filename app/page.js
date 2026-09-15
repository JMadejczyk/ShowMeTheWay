'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

const SRC = [
  ['web', 'Web search', 'always on'],
  ['paste', 'Paste text', ''],
  ['urls', 'URLs', ''],
  ['files', 'Local files', ''],
  ['drive', 'Google Drive', 'soon'],
];

export default function Home() {
  const r = useRouter();
  const [goal, setGoal] = useState('');
  const [bg, setBg] = useState('');
  const [on, setOn] = useState({ web: true });
  const [paste, setPaste] = useState('');
  const [urls, setUrls] = useState('');
  const [files, setFiles] = useState([]);
  const [qs, setQs] = useState(null);
  const [ans, setAns] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [mine, setMine] = useState([]);

  const [rid, setRid] = useState(null);
  useEffect(() => { api('/api/roadmaps').then(d => Array.isArray(d) && setMine(d)); }, []);

  const toggle = k => setOn(o => ({ ...o, [k]: !o[k] }));

  async function readFiles(list) {
    const out = [];
    for (const f of [...list].slice(0, 10)) out.push({ name: f.name, text: await f.text() });
    setFiles(out);
  }

  const payloadSources = () => ({
    ...(on.web ? { web: true } : {}),
    ...(on.paste ? { paste } : {}),
    ...(on.urls ? { urls } : {}),
    ...(on.files ? { files } : {}),
  });

  async function ask() {
    setBusy(true); setErr('');
    try {
      // Runs the LangGraph up to the clarify interrupt; the roadmap row exists from here on.
      const d = await api('/api/roadmaps', { goal, background: bg, sources: payloadSources() });
      if (d.error) throw new Error(d.error);
      setRid(d.id);
      setQs({ title: d.title, questions: d.questions });
    } catch (e) { setErr(e.message); }
    setBusy(false);
  }

  async function build() {
    setBusy(true); setErr('');
    try {
      const answers = (qs?.questions ?? []).map(q => ({ q: q.q, a: ans[q.q] || 'no preference' }));
      // Resumes the interrupted graph; research + structure run server-side.
      const d = await api(`/api/roadmaps/${rid}/resume`, { answers });
      if (d.error) throw new Error(d.error);
      r.push('/r/' + rid);
    } catch (e) { setErr(e.message); setBusy(false); }
  }

  return (
    <div className="wrap">
      <div className="hero">
        <h1>ShowMeTheWay</h1>
        <p>roadmap.sh for any field — researched live, and shaped around what you already know.</p>
      </div>

      {err && <div className="err">{err}</div>}

      {!qs && <>
        <div className="field">
          <label>What do you want to get to?</label>
          <textarea rows={2} value={goal} onChange={e => setGoal(e.target.value)}
            placeholder="I want to become a registered nurse in the UK" />
        </div>
        <div className="field">
          <label>What's your background? <span className="hint">— this is what makes the roadmap yours; the more honest, the better</span></label>
          <textarea rows={4} value={bg} onChange={e => setBg(e.target.value)}
            placeholder="8 years as a paramedic. Biology A-level. No degree. Comfortable with patient assessment and emergency care, never worked on a ward." />
        </div>

        <div className="field">
          <label>Sources <span className="hint">— web search is the backbone; add your own for context</span></label>
          <div className="srcbar">
            {SRC.map(([k, label, note]) => (
              <button key={k} type="button" disabled={k === 'drive'}
                className={'chip' + (on[k] ? ' on' : '')} onClick={() => toggle(k)}>
                {label}{note && <span style={{ opacity: .6 }}> · {note}</span>}
              </button>
            ))}
          </div>
          {on.paste && <textarea rows={4} value={paste} onChange={e => setPaste(e.target.value)}
            placeholder="Paste a syllabus, job spec, course outline…" style={{ marginBottom: 8 }} />}
          {on.urls && <input type="text" value={urls} onChange={e => setUrls(e.target.value)}
            placeholder="https://… (space or comma separated)" style={{ marginBottom: 8 }} />}
          {on.files && <input type="file" multiple onChange={e => readFiles(e.target.files)}
            style={{ marginBottom: 8 }} />}
          {on.files && files.length > 0 && <div className="dim">{files.length} file(s) loaded</div>}
        </div>

        <button className="btn" disabled={!goal.trim() || busy} onClick={ask}>
          {busy ? 'Thinking…' : 'Next →'}
        </button>
      </>}

      {qs && <>
        <p className="dim" style={{ marginTop: 0 }}>A few things that change the shape of the roadmap:</p>
        {qs.questions.map((q, i) => (
          <div className="q" key={i}>
            <strong>{q.q}</strong>
            <div className="why">{q.why}</div>
            <div>{(q.suggestions ?? []).map(s => (
              <button key={s} type="button"
                className={'chip' + (ans[q.q] === s ? ' on' : '')}
                onClick={() => setAns(a => ({ ...a, [q.q]: s }))}>{s}</button>
            ))}</div>
            <input type="text" style={{ marginTop: 6 }} placeholder="or type your own"
              value={ans[q.q] ?? ''} onChange={e => setAns(a => ({ ...a, [q.q]: e.target.value }))} />
          </div>
        ))}
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" disabled={busy} onClick={build}>
            {busy ? 'Starting…' : 'Build my roadmap'}
          </button>
          <button className="btn ghost" disabled={busy} onClick={() => setQs(null)}>Back</button>
        </div>
      </>}

      {mine.length > 0 && <div style={{ marginTop: 44 }}>
        <div className="dim" style={{ marginBottom: 8 }}>Your roadmaps</div>
        <div className="list">
          {mine.map(m => <a key={m.id} href={'/r/' + m.id}>
            <span>{m.title}</span>
            <span className="dim">{m.status === 'ready' ? '' : m.status}</span>
          </a>)}
        </div>
      </div>}
    </div>
  );
}
