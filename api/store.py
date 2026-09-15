"""App data (roadmaps/nodes/edges). LangGraph checkpoints live in their own db."""
import sqlite3, json, os, secrets, time, threading

DB = os.path.join(os.path.dirname(__file__), "..", "data.db")

# One connection PER THREAD. Sharing a single connection across the request
# threadpool meant one request's commit() cleared another's implicit transaction,
# and the second commit() then died with "no transaction is active". SQLite does
# its own cross-connection locking; WAL lets reads proceed during a write.
_local = threading.local()

def conn():
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(DB, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=30000")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS roadmap(
          id TEXT PRIMARY KEY, title TEXT, goal TEXT, background TEXT,
          clarifications TEXT, questions TEXT, brief TEXT, sources TEXT,
          status TEXT, error TEXT, created INTEGER);
        CREATE TABLE IF NOT EXISTS node(
          id TEXT PRIMARY KEY, roadmap_id TEXT, title TEXT, kind TEXT, track TEXT,
          summary TEXT, detail TEXT, sources TEXT, status TEXT, why_known TEXT,
          parent_id TEXT, ord INTEGER, x REAL, y REAL);
        CREATE TABLE IF NOT EXISTS edge(roadmap_id TEXT, src TEXT, dst TEXT, kind TEXT);
        CREATE TABLE IF NOT EXISTS chat(
          id TEXT PRIMARY KEY, roadmap_id TEXT, title TEXT, created INTEGER);
        CREATE TABLE IF NOT EXISTS message(
          id TEXT PRIMARY KEY, chat_id TEXT, role TEXT, text TEXT, meta TEXT,
          created INTEGER);
        CREATE TABLE IF NOT EXISTS qa(
          id TEXT PRIMARY KEY, roadmap_id TEXT, node_id TEXT, q TEXT, a TEXT,
          sources TEXT, grounded INTEGER, created INTEGER);
        """)
        c.commit()
        _local.c = c
    return c

uid = lambda: secrets.token_hex(4)
jl  = lambda s, fb: (json.loads(s) if s else fb) or fb

def create(goal, background, sources):
    rid = uid()
    conn().execute(
        "INSERT INTO roadmap VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (rid, "Untitled roadmap", goal, background or "", "[]", "[]", "", "[]",
         "clarifying", None, int(time.time() * 1000)))
    conn().commit()
    return rid

def patch(rid, **f):
    if not f: return
    conn().execute(f"UPDATE roadmap SET {','.join(k+'=?' for k in f)} WHERE id=?",
                   (*f.values(), rid))
    conn().commit()

def save_graph(rid, data):
    c = conn()
    c.execute("DELETE FROM node WHERE roadmap_id=?", (rid,))
    c.execute("DELETE FROM edge WHERE roadmap_id=?", (rid,))
    ids = set()
    for i, n in enumerate(data.get("nodes", [])):
        ids.add(n["id"])
        c.execute("INSERT OR REPLACE INTO node VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (n["id"], rid, n["title"], n.get("kind", "skill"), n.get("track", "core"),
                   n.get("summary", ""), None, "[]",
                   "known" if n.get("status") == "known" else "todo",
                   n.get("whyKnown", ""), n.get("parent", ""), i, None, None))
    for e in data.get("edges", []):
        if e["src"] in ids and e["dst"] in ids:
            c.execute("INSERT INTO edge VALUES (?,?,?,?)",
                      (rid, e["src"], e["dst"], e.get("kind", "main")))
    c.commit()

def get(rid):
    r = conn().execute("SELECT * FROM roadmap WHERE id=?", (rid,)).fetchone()
    if not r: return None
    d = dict(r)
    d["clarifications"] = jl(d["clarifications"], [])
    d["questions"] = jl(d["questions"], [])
    d["sources"] = jl(d["sources"], [])
    d["nodes"] = [{**dict(n), "sources": jl(n["sources"], [])} for n in
                  conn().execute("SELECT * FROM node WHERE roadmap_id=? ORDER BY ord", (rid,))]
    d["edges"] = [dict(e) for e in
                  conn().execute("SELECT * FROM edge WHERE roadmap_id=?", (rid,))]
    return d

def listing():
    return [dict(r) for r in conn().execute(
        "SELECT id,title,goal,status,created FROM roadmap ORDER BY created DESC")]

def node(nid):
    r = conn().execute("SELECT * FROM node WHERE id=?", (nid,)).fetchone()
    return dict(r) if r else None

def node_patch(nid, **f):
    conn().execute(f"UPDATE node SET {','.join(k+'=?' for k in f)} WHERE id=?",
                   (*f.values(), nid))
    conn().commit()


def qa_for_node(nid):
    return [{**dict(r), "sources": jl(r["sources"], [])} for r in conn().execute(
        "SELECT * FROM qa WHERE node_id=? ORDER BY created", (nid,))]

def qa_add(rid, nid, q, a, sources, grounded):
    i = uid()
    conn().execute("INSERT INTO qa VALUES (?,?,?,?,?,?,?,?)",
                   (i, rid, nid, q, a, json.dumps(sources), int(grounded),
                    int(time.time() * 1000)))
    conn().commit()
    return i


# ---- chats. A chat may exist before its roadmap (the one that creates it) or be
# attached to an existing artifact afterwards. Artifact is the durable object.

def chat_create(title="New chat", roadmap_id=None):
    i = uid()
    conn().execute("INSERT INTO chat VALUES (?,?,?,?)",
                   (i, roadmap_id, title, int(time.time() * 1000)))
    conn().commit()
    return i

def chat_patch(cid, **f):
    if not f: return
    conn().execute(f"UPDATE chat SET {','.join(k+'=?' for k in f)} WHERE id=?",
                   (*f.values(), cid))
    conn().commit()

def chat_list(roadmap_id=None):
    q = "SELECT * FROM chat"
    a = ()
    if roadmap_id:
        q += " WHERE roadmap_id=?"
        a = (roadmap_id,)
    return [dict(r) for r in conn().execute(q + " ORDER BY created DESC", a)]

def chat_get(cid):
    r = conn().execute("SELECT * FROM chat WHERE id=?", (cid,)).fetchone()
    if not r: return None
    d = dict(r)
    d["messages"] = [{**dict(m), "meta": jl(m["meta"], {})} for m in conn().execute(
        "SELECT * FROM message WHERE chat_id=? ORDER BY created", (cid,))]
    return d

def msg_add(cid, role, text, meta=None):
    i = uid()
    conn().execute("INSERT INTO message VALUES (?,?,?,?,?,?)",
                   (i, cid, role, text, json.dumps(meta or {}), int(time.time() * 1000)))
    conn().commit()
    return i
