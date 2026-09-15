'use client';
import { useState, useEffect, useRef } from 'react';
import './gemini.css';
import { api } from '@/lib/api';
import { ICON } from '@/lib/drive';
import DrivePicker from '@/components/gemini/DrivePicker';
import Artifact from '@/components/gemini/Artifact';

const uid = () => Math.random().toString(36).slice(2);
const SUGGEST = [
  'I want to become a registered nurse in the UK',
  'I want to move from paramedic into emergency nursing',
  'I want to become a commercial airline pilot',
  'I want to qualify as a sommelier at my restaurant',
];
const STAGE = {
  researching: 'Searching the web and reading your documents',
  structuring: 'Shaping the roadmap around what you already know',
};

export default function Workspace() {
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState('');
  const [att, setAtt] = useState([]);
  const [picker, setPicker] = useState(false);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(null);      // artifact roadmap id
  const [saved, setSaved] = useState([]);
  const end = useRef(null);

  // flow state
  const st = useRef({ phase: 'goal', goal: '', background: '', qs: [], qi: 0, answers: [], rid: null });

  const push = m => setMsgs(x => [...x, { id: uid(), ...m }]);
  const patch = (id, f) => setMsgs(x => x.map(m => m.id === id ? { ...m, ...f } : m));
  const refresh = () => api('/api/roadmaps').then(d => Array.isArray(d) && setSaved(d));

  useEffect(() => { refresh(); }, []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs]);

  async function startClarify() {
    const s = st.current;
    const tid = uid();
    setMsgs(x => [...x, { id: tid, role: 'a', thinking: true, text: 'Understanding your goal…' }]);
    const d = await api('/api/roadmaps', {
      goal: s.goal, background: s.background,
      sources: { web: true, files: att.map(a => ({ name: a.name, text: a.text })) },
    });
    if (d.error) { patch(tid, { thinking: false, text: 'Something went wrong: ' + d.error }); setBusy(false); return; }
    s.rid = d.id; s.qs = d.questions || []; s.qi = 0; s.answers = []; s.phase = 'clarify';
    const q = s.qs[0];
    patch(tid, {
      thinking: false,
      text: `Before I build this, a few things that genuinely change the shape of the plan.`,
      q: q?.q, why: q?.why, options: q?.suggestions,
    });
    setBusy(false);
  }

  async function build() {
    const s = st.current;
    s.phase = 'building';
    setBusy(true);
    const tid = uid();
    setMsgs(x => [...x, { id: tid, role: 'a', thinking: true, text: 'Researching', stage: 'researching' }]);
    await api(`/api/roadmaps/${s.rid}/resume`, { answers: s.answers });
    const poll = setInterval(async () => {
      const d = await api('/api/roadmaps/' + s.rid);
      if (d.status === 'researching' || d.status === 'structuring') {
        patch(tid, { stage: d.status });
        return;
      }
      clearInterval(poll);
      if (d.status === 'error') {
        patch(tid, { thinking: false, stage: null, text: 'Generation failed: ' + d.error });
      } else {
        const known = d.nodes.filter(n => n.status === 'known').length;
        patch(tid, {
          thinking: false, stage: null,
          text: `Done — ${d.nodes.length} steps.` + (known
            ? ` ${known} of them you already have from your background, so I've marked those cleared.`
            : ''),
          artifact: { id: d.id, title: d.title, n: d.nodes.length },
        });
        setOpen(d.id);
        refresh();
      }
      s.phase = 'done';
      setBusy(false);
    }, 2500);
  }

  async function send(raw) {
    const body = (raw ?? text).trim();
    if ((!body && !att.length) || busy) return;
    const s = st.current;
    push({ role: 'u', text: body, attachments: att });
    setText(''); setBusy(true);
    const used = att; setAtt([]);

    if (s.phase === 'goal') {
      s.goal = body;
      if (used.length) {
        const tid = uid();
        setMsgs(x => [...x, { id: tid, role: 'a', thinking: true, text: 'Reading your files…' }]);
        const p = await api('/api/profile', {
          goal: body, docs: used.map(a => ({ name: a.name, text: a.text })),
        });
        s.background = p.background || '';
        patch(tid, { thinking: false, text: p.summary || 'Read your files.' });
        return startClarify();
      }
      s.phase = 'background';
      push({ role: 'a', text: "Tell me where you're starting from — what you do now, what you've already got, what you haven't. The more honest, the more this is actually yours." });
      setBusy(false);
      return;
    }

    if (s.phase === 'background') {
      s.background = body;
      return startClarify();
    }

    if (s.phase === 'clarify') return answer(body);
    setBusy(false);
  }

  async function answer(a) {
    const s = st.current;
    const q = s.qs[s.qi];
    s.answers = [...s.answers, { q: q.q, a }];
    s.qi += 1;
    if (s.qi < s.qs.length) {
      const n = s.qs[s.qi];
      push({ role: 'a', text: '', q: n.q, why: n.why, options: n.suggestions });
      setBusy(false);
    } else {
      push({ role: 'a', text: "That's everything I need. Building your roadmap now." });
      build();
    }
  }

  function pickOption(mid, opt) {
    patch(mid, { options: null });
    push({ role: 'u', text: opt });
    answer(opt);
  }

  const fresh = msgs.length === 0;

  return (
    <div className={"g" + (open ? " split" : "")}>
      <div className="grail">
        <button className="gburger">☰</button>
        <button className="gnew" onClick={() => {
          st.current = { phase: 'goal', goal: '', background: '', qs: [], qi: 0, answers: [], rid: null };
          setMsgs([]); setOpen(null); setAtt([]);
        }}>✏️ New chat</button>
        <div className="gsec">Roadmaps</div>
        {saved.map(r => (
          <button key={r.id} className={'gitem' + (open === r.id ? ' on' : '')}
            onClick={() => setOpen(r.id)} title={r.title}>◈ {r.title}</button>
        ))}
        {!saved.length && <div className="gitem" style={{ opacity: .55 }}>No roadmaps yet</div>}
        <div className="gsec" style={{ marginTop: 10 }}>Recent</div>
        <button className="gitem">Q1 planning notes</button>
        <button className="gitem">Holiday itinerary</button>
      </div>

      <div className="gmain">
        <div className="gcol">
          <div className="ghead">
            <b>Gemini</b>
            <span style={{ fontSize: 11.5, color: '#5f6368', background: '#f0f4f9',
              borderRadius: 6, padding: '3px 8px' }}>Roadmaps</span>
            <div className="gavatar">J</div>
          </div>

          <div className="gthread">
            <div className="ginner">
              {fresh && <>
                <div className="ghello">Hello, Jakub</div>
                <div className="gsub">What do you want to get to?</div>
                <div className="gsugg">
                  {SUGGEST.map(s => (
                    <button key={s} className="gcard" onClick={() => send(s)}>{s}</button>
                  ))}
                </div>
              </>}

              {msgs.map(m => m.role === 'u' ? (
                <div className="gmsg u" key={m.id}>
                  <div className="guser">
                    {m.text}
                    {!!m.attachments?.length && <div className="gatt">
                      {m.attachments.map(a => (
                        <span className="gpill" key={a.id}>
                          <span className="gdot" style={{ background: ICON[a.kind] }} />{a.name}
                        </span>
                      ))}
                    </div>}
                  </div>
                </div>
              ) : (
                <div className="gmsg" key={m.id}>
                  <div className={'gspark' + (m.thinking ? ' think' : '')}>✦</div>
                  <div className="gbody">
                    {m.stage ? (
                      <>
                        {Object.entries(STAGE).map(([k, label]) => {
                          const order = ['researching', 'structuring'];
                          const done = order.indexOf(m.stage) > order.indexOf(k);
                          const now = m.stage === k;
                          return <div className="gstep" key={k} style={{ opacity: done || now ? 1 : .45 }}>
                            <span className={done ? 'gtick' : ''}>{done ? '✓' : now ? '◐' : '○'}</span>{label}
                          </div>;
                        })}
                      </>
                    ) : <p>{m.text}</p>}

                    {m.q && <>
                      <p className="gq" style={{ marginBottom: 2 }}>{m.q}</p>
                      {m.why && <p style={{ color: '#5f6368', fontSize: 13.5, marginBottom: 4 }}>{m.why}</p>}
                      {m.options && <div className="gopts">
                        {m.options.map(o => (
                          <button className="gopt" key={o} onClick={() => pickOption(m.id, o)}>{o}</button>
                        ))}
                      </div>}
                    </>}

                    {m.artifact && (
                      <div className="gart" onClick={() => setOpen(m.artifact.id)}>
                        <div className="gi">◈</div>
                        <div style={{ minWidth: 0 }}>
                          <b>{m.artifact.title}</b>
                          <span>Roadmap · {m.artifact.n} steps · saved to Drive</span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={end} />
            </div>
          </div>

          <div className="gcomp">
            <div className="gbox">
              <button className="gicon" onClick={() => setPicker(true)} title="Add from Drive">＋</button>
              <input value={text} onChange={e => setText(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && send()}
                placeholder={busy ? 'Working…' : 'Ask Gemini'} disabled={busy} />
              <button className="gicon send" disabled={busy || (!text.trim() && !att.length)}
                onClick={() => send()}>➤</button>
            </div>
            {!!att.length && <div className="gatt" style={{ maxWidth: 760, margin: '9px auto 0' }}>
              {att.map(a => (
                <span className="gpill" key={a.id}>
                  <span className="gdot" style={{ background: ICON[a.kind] }} />{a.name}
                  <button onClick={() => setAtt(s => s.filter(x => x.id !== a.id))}
                    style={{ color: '#5f6368' }}>✕</button>
                </span>
              ))}
            </div>}
            <div className="gfoot">Prototype — not affiliated with Google. Gemini can make mistakes.</div>
          </div>
        </div>

        {open && <Artifact id={open} onClose={() => setOpen(null)} />}
      </div>

      {picker && <DrivePicker onClose={() => setPicker(false)}
        onPick={f => setAtt(a => [...a, ...f.filter(x => !a.some(y => y.id === x.id))])} />}
    </div>
  );
}
