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
import json, os, threading, time
from concurrent.futures import ThreadPoolExecutor

import llm, store

# 20 measured clean: 23 nodes in 49s (vs 131s at 5), and two roadmaps enriching at
# once — 46 nodes, 40 simultaneous grounded calls — also finished in 50s with zero
# failures. Wall clock barely moved between 23 and 46 nodes, so the limit here is
# per-call latency, not throughput. Tune with ENRICH_WORKERS if a key is rate-limited.
WORKERS = int(os.environ.get("ENRICH_WORKERS", "20"))
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
        if not srcs:
            # the mandate makes this rare, but on the eager path nobody is watching,
            # so an uncited step would just quietly ship without sources
            print(f"[enrich] {nid}: no citations, retrying once")
            text2, srcs2 = deep_dive(n, r)
            if srcs2:
                text, srcs = text2, srcs2
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
    fails = []
    lock = threading.Lock()
    t0 = time.time()

    def one(n):
        nonlocal done
        err = None
        try:
            ensure(n["id"])
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print(f"[enrich] FAIL {n['id']}: {err}")
        with lock:
            done += 1
            if err:
                fails.append((n["id"], err))
            store.patch(rid, enriched=done)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(one, todo))

    ok = len(todo) - len(fails)
    print(f"[enrich] {rid}: {ok}/{len(todo)} researched in {time.time()-t0:.0f}s "
          f"({WORKERS} workers)" + (f" — {len(fails)} FAILED" if fails else ""))
    return {"ok": ok, "failed": len(fails), "errors": fails,
            "seconds": round(time.time() - t0)}
