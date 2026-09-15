"""App data (roadmaps/nodes/edges). LangGraph checkpoints live in their own db."""
import sqlite3, json, os, secrets, time

DB = os.path.join(os.path.dirname(__file__), "..", "data.db")
_c = None

def conn():
    global _c
    if _c is None:
        _c = sqlite3.connect(DB, check_same_thread=False)
        _c.row_factory = sqlite3.Row
        _c.executescript("""
        CREATE TABLE IF NOT EXISTS roadmap(
          id TEXT PRIMARY KEY, title TEXT, goal TEXT, background TEXT,
          clarifications TEXT, questions TEXT, brief TEXT, sources TEXT,
          status TEXT, error TEXT, created INTEGER);
        CREATE TABLE IF NOT EXISTS node(
          id TEXT PRIMARY KEY, roadmap_id TEXT, title TEXT, kind TEXT, track TEXT,
          summary TEXT, detail TEXT, sources TEXT, status TEXT, why_known TEXT,
          parent_id TEXT, ord INTEGER, x REAL, y REAL);
        CREATE TABLE IF NOT EXISTS edge(roadmap_id TEXT, src TEXT, dst TEXT, kind TEXT);
        """)
        _c.commit()
    return _c

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
