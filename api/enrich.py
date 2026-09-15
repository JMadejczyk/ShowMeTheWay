"""
Per-step deep dives, generated as part of roadmap creation rather than on click.

Timing is the whole design constraint. A deep dive is a grounded call, ~30s, and a
roadmap has 20-30 nodes — sequentially that is ten minutes. So:

  * the roadmap is marked ready BEFORE enrichment starts, so the canvas appears at
    the same ~60s it always did;
  * enrichment then runs on a bounded pool behind it, core spine first, because
    those are the nodes anyone clicks;
  * a node clicked before its turn still generates on demand, so there is no dead
    state — just the old behaviour for that one node.

One lock per node id means the eager pass and a click on the same node cannot both
pay for the same generation.
"""
import json, threading
from concurrent.futures import ThreadPoolExecutor

import llm, store

WORKERS = 5                       # concurrent grounded calls; above this we hit rate limits
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def _lock(nid):
    with _guard:
        return _locks.setdefault(nid, threading.Lock())


def deep_dive(node, roadmap):
    """The single definition of a step's deep dive — used by both paths."""
    return llm.grounded(f"""Write a practical deep-dive for one step of someone's roadmap.
Search the web for current, authoritative specifics.

THEIR GOAL: {roadmap['goal']}
THEIR BACKGROUND: {roadmap['background'] or '(not given)'}
THIS STEP: {node['title']}
CONTEXT: {node['summary']}

Markdown, no H1. Cover, with headings:
- What this actually is, and why it's on the path to their goal
- What "done" looks like — the concrete bar they must clear
- How to do it: named courses, providers, exams, books, official handbooks, with real
  costs and realistic durations where you can find them
- Pitfalls people hit at this step

Given their background, calibrate the depth — skip what they'd obviously know.
Take their stated background literally: do not credit them with any qualification,
degree or diploma they did not claim, and do not infer one from their job title.
Be concrete and specific. No filler, no motivational padding.""")


def ensure(nid, force=False):
    """Generate this node's detail unless it already has one. Safe to call from the
    eager pass and from a click at the same time."""
    with _lock(nid):
        n = store.node(nid)
        if not n:
            return None
        if n["detail"] and not force:
            return {"detail": n["detail"], "sources": json.loads(n["sources"] or "[]")}
        r = store.get(n["roadmap_id"])
        text, srcs = deep_dive(n, r)
        store.node_patch(nid, detail=text, sources=json.dumps(srcs))
        return {"detail": text, "sources": srcs}


def enrich_all(rid):
    """Fill in every step's detail. Core spine first — those get clicked."""
    r = store.get(rid)
    if not r:
        return
    todo = [n for n in r["nodes"] if not n["detail"]]
    todo.sort(key=lambda n: (n["track"] != "core", n["ord"]))
    store.patch(rid, enriched=0, enrich_total=len(todo))
    if not todo:
        return

    done = 0
    lock = threading.Lock()

    def one(n):
        nonlocal done
        try:
            ensure(n["id"])
        except Exception as e:
            print(f"[enrich] {n['id']}: {e}")
        with lock:
            done += 1
            store.patch(rid, enriched=done)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(one, todo))
    print(f"[enrich] {rid}: {done}/{len(todo)} steps researched")
