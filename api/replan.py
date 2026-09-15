"""
Graph mutation: "I already know this — replan what comes after it."

    START -> split -> [delta?] -> restructure -> merge -> END

Design constraint that makes this a workspace edit and not a regeneration:
everything UPSTREAM of the anchor is frozen — nodes, edges, statuses, cached
deep-dives, hand-dragged positions. Only the downstream subgraph is rebuilt, and
a downstream node that survives the rebuild (same id) keeps its status and its
already-researched detail. You never pay twice for work you've already done.
"""
import json, os, sqlite3
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

import llm, store

S_ = {"type": "STRING"}

REPLAN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "rationale": S_,
        "completed_ids": {"type": "ARRAY", "items": S_},
        "nodes": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {
                "id": S_, "title": S_,
                "kind":  {"type": "STRING", "enum": ["milestone", "skill", "resource", "practice"]},
                "track": {"type": "STRING", "enum": ["core", "alternative", "optional"]},
                "summary": S_,
                "status": {"type": "STRING", "enum": ["todo", "known"]},
                "whyKnown": S_, "parent": S_,
            },
            "required": ["id", "title", "kind", "track", "summary", "status", "whyKnown", "parent"]}},
        "edges": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"src": S_, "dst": S_,
                           "kind": {"type": "STRING", "enum": ["main", "branch"]}},
            "required": ["src", "dst", "kind"]}},
    },
    "required": ["rationale", "completed_ids", "nodes", "edges"],
}


class RS(TypedDict, total=False):
    roadmap_id: str
    anchor_id: str
    instruction: str
    upstream: list
    downstream: list
    delta: str
    data: dict


# ------------------------------------------------------------------ helpers

def descendants(nodes, edges, anchor_id):
    """Everything reachable from the anchor along main edges, plus the branch
    children hanging off those core nodes. The anchor itself is NOT included."""
    by = {n["id"]: n for n in nodes}
    anchor = by.get(anchor_id)
    if not anchor:
        return set()

    # a branch node can't anchor a resequence — use the core node it hangs off
    if anchor["track"] != "core" and anchor.get("parent_id") in by:
        anchor_id = anchor["parent_id"]

    main = {}
    for e in edges:
        if e["kind"] == "main":
            main.setdefault(e["src"], []).append(e["dst"])

    down, stack, seen = set(), [anchor_id], {anchor_id}
    while stack:
        for nxt in main.get(stack.pop(), []):
            if nxt not in seen:
                seen.add(nxt); down.add(nxt); stack.append(nxt)

    # pull in each downstream core node's branch children
    for n in nodes:
        if n["id"] in down:
            continue
        if n.get("parent_id") in down:
            down.add(n["id"])
    for e in edges:
        if e["kind"] == "branch" and e["src"] in down:
            down.add(e["dst"])
    down.discard(anchor_id)
    return down


def _fmt(nodes):
    return "\n".join(
        f"  [{n['track']}/{n['status']}] {n['id']}: {n['title']} — {n['summary']}"
        for n in nodes) or "  (none)"


# ------------------------------------------------------------------ nodes

def split(s: RS) -> dict:
    r = store.get(s["roadmap_id"])
    down = descendants(r["nodes"], r["edges"], s["anchor_id"])
    return {
        "downstream": sorted(down),
        "upstream": [n["id"] for n in r["nodes"] if n["id"] not in down],
    }


def needs_delta(s: RS) -> str:
    """A bare 'I already know this' is answerable from the brief we already paid
    for. A substantive instruction ('switch me to the EASA route') may introduce
    facts the brief never covered — that earns a fresh search."""
    return "delta" if len((s.get("instruction") or "").strip()) > 15 else "restructure"


def delta(s: RS) -> dict:
    r = store.get(s["roadmap_id"])
    anchor = store.node(s["anchor_id"])
    text, cited = llm.grounded(f"""A learner is partway through a roadmap and has told us something
that changes the rest of their path. Search the web for what specifically changes.

GOAL: {r['goal']}
BACKGROUND: {r['background']}
THEY JUST TOLD US: {s['instruction']}
AT THIS STEP: {anchor['title']} — {anchor['summary']}

Research only what this changes about the REMAINING path: steps that become
unnecessary, steps that become newly required, changed sequencing, changed costs or
timelines. Cite official bodies. Be brief and specific — this is input to another
model, not a human.""")
    # fold new citations into the roadmap's source list
    have = {c["url"] for c in r["sources"]}
    store.patch(s["roadmap_id"],
                sources=json.dumps(r["sources"] + [c for c in cited if c["url"] not in have]))
    return {"delta": text}


def restructure(s: RS) -> dict:
    r = store.get(s["roadmap_id"])
    by = {n["id"]: n for n in r["nodes"]}
    anchor = by[s["anchor_id"]]
    up = [by[i] for i in s["upstream"] if i in by]
    dn = [by[i] for i in s["downstream"] if i in by]

    data = llm.structured(f"""Replan the remaining part of someone's roadmap.

GOAL: {r['goal']}
BACKGROUND: {r['background']}
THEIR ANSWERS: {json.dumps(r['clarifications'])}

WHAT CHANGED — they have just told us about this step:
  {anchor['title']} — {anchor['summary']}
  Their status for it: {anchor['status']}
  {('Their words: ' + s['instruction']) if s.get('instruction') else ''}

{('WHAT THAT CHANGES (fresh research):' + chr(10) + s['delta']) if s.get('delta') else
 'RESEARCH BRIEF:' + chr(10) + r['brief'][:9000]}

LOCKED — already done or in progress, do NOT reproduce these:
{_fmt(up)}

REPLAN — replace this set entirely:
{_fmt(dn)}

Return the NEW downstream portion only. Rules:
- Reuse an existing id verbatim when that step still applies and means the same
  thing. The user's progress and researched notes are keyed to ids, so a reused id
  preserves their work and a renamed one throws it away. Reuse aggressively.
- If they tell you they have ALREADY DONE or ALREADY KNOW a step, KEEP that step
  (same id) with status "known" — do not delete it. A completed step vanishing from
  the map is disorienting; they need to see it sitting there, cleared.
- Only drop a step that has become genuinely redundant or inapplicable — i.e. it is
  no longer part of their path at all, not merely already finished.
- Add steps that are now newly relevant, newly unlocked, or newly required.
- Never emit a node whose id appears in the LOCKED list.
- track/parent rules as before: "core" is the spine (parent ""), "alternative" and
  "optional" hang off a core node id (which may be a LOCKED id or a new one).
- edges: chain the new core nodes with "main"; connect "{anchor['id']}" to the first
  new core node with a "main" edge; hang children off their parent with "branch".
- completed_ids: the ids of any steps their words say they have ALREADY DONE or
  ALREADY KNOW. List every one you can identify, from your output or the LOCKED set.
  Leave empty only if they claimed nothing.
- rationale: one sentence on what you changed and why.""", REPLAN_SCHEMA, temperature=0.35)
    return {"data": data}


def merge(s: RS) -> dict:
    """Splice the new subgraph in, preserving everything the user has invested."""
    rid = s["roadmap_id"]
    r = store.get(rid)
    c = store.conn()
    c.execute("BEGIN")
    try:
        return _splice(s, rid, r, c)
    except Exception:
        c.rollback()                     # never leave a half-replanned graph
        raise


def _splice(s, rid, r, c):
    down = set(s["downstream"])
    up = set(s["upstream"])
    old = {n["id"]: n for n in r["nodes"] if n["id"] in down}
    data = s.get("data") or {}

    # never let the model shadow a locked node
    new_nodes = [n for n in data.get("nodes", []) if n["id"] not in up]

    # the user's "I've already done X" is applied in code, not left to a per-node
    # field the model sets inconsistently.
    done_ids = set(data.get("completed_ids") or [])
    for i in done_ids & up:                      # a locked node they just claimed
        c.execute("UPDATE node SET status='known' WHERE id=? AND roadmap_id=? "
                  "AND status NOT IN ('done','doing')", (i, rid))

    c.execute("DELETE FROM node WHERE roadmap_id=? AND id IN (%s)" %
              ",".join("?" * len(down)), (rid, *down)) if down else None
    if down:
        c.execute("DELETE FROM edge WHERE roadmap_id=? AND (src IN (%s) OR dst IN (%s))" %
                  (",".join("?" * len(down)), ",".join("?" * len(down))), (rid, *down, *down))

    base = max([n["ord"] for n in r["nodes"] if n["id"] in up] or [0]) + 1
    kept = 0
    for i, n in enumerate(new_nodes):
        o = old.get(n["id"])
        if o:
            kept += 1
        c.execute("INSERT OR REPLACE INTO node VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            n["id"], rid, n["title"], n.get("kind", "skill"), n.get("track", "core"),
            n.get("summary", ""),
            o["detail"] if o else None,                       # keep researched detail
            json.dumps(o["sources"]) if o else "[]",
            ("known" if n["id"] in done_ids
             else o["status"] if o and o["status"] in ("done", "doing", "known")
             else ("known" if n.get("status") == "known" else "todo")),
            n.get("whyKnown", ""), n.get("parent", ""),
            base + i,
            None, None))                                      # re-layout: sequence changed

    live = up | {n["id"] for n in new_nodes}
    for e in data.get("edges", []):
        if e["src"] in live and e["dst"] in live and not (e["src"] in up and e["dst"] in up):
            c.execute("INSERT INTO edge VALUES (?,?,?,?)",
                      (rid, e["src"], e["dst"], e.get("kind", "main")))

    # guarantee the spine reconnects even if the model forgot the joining edge
    anchor = s["anchor_id"]
    joined = c.execute("SELECT 1 FROM edge WHERE roadmap_id=? AND src=? AND kind='main'",
                       (rid, anchor)).fetchone()
    if not joined:
        first = next((n["id"] for n in new_nodes if n.get("track") == "core"), None)
        if first:
            c.execute("INSERT INTO edge VALUES (?,?,?,?)", (rid, anchor, first, "main"))
    c.commit()

    store.patch(rid, status="ready",
                error=None)
    print(f"[replan] {rid}: {len(down)} replaced by {len(new_nodes)} "
          f"({kept} ids reused, {len(done_ids)} marked cleared) — {data.get('rationale','')}")
    return {}


def build():
    g = StateGraph(RS)
    for fn in (split, delta, restructure, merge):
        g.add_node(fn.__name__, fn)
    g.add_edge(START, "split")
    g.add_conditional_edges("split", needs_delta,
                            {"delta": "delta", "restructure": "restructure"})
    g.add_edge("delta", "restructure")
    g.add_edge("restructure", "merge")
    g.add_edge("merge", END)
    path = os.path.join(os.path.dirname(__file__), "..", "checkpoints.db")
    cp = SqliteSaver(sqlite3.connect(path, check_same_thread=False))
    cp.setup()
    return g.compile(checkpointer=cp)

REPLAN = build()
