"""
Roadmap-level chat. A chat attached to an artifact, as opposed to ask.py which is
scoped to one node.

    START -> route -> (answer | search | mutate) -> save -> END

Three things a message can be, and they cost very different amounts:
  * a question answerable from the roadmap we're holding      (~6s)
  * a question needing current world facts                     (~15s, grounded)
  * news that changes the plan -> hand off to the replan graph  (~25s, async)

The third is the point of attaching a chat to an artifact: "I got accepted onto
the apprenticeship" should edit the roadmap, not just be acknowledged.
"""
import os, json, sqlite3, threading, time
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

import llm, store
from replan import REPLAN

S_ = {"type": "STRING"}

ROUTE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "intent": {"type": "STRING", "enum": ["answer", "search", "mutate"]},
        "anchor_id": S_,
        "instruction": S_,
        "reason": S_,
    },
    "required": ["intent", "anchor_id", "instruction", "reason"],
}


class CS(TypedDict, total=False):
    chat_id: str
    roadmap_id: str
    message: str
    intent: str
    anchor_id: str
    instruction: str
    answer: str
    sources: list
    replanning: bool


def _ctx(rid):
    r = store.get(rid)
    spine = "\n".join(
        f"  {x['id']} | {'[cleared] ' if x['status'] in ('done','known') else ''}{x['title']}"
        for x in r["nodes"] if x["track"] == "core")
    side = "\n".join(f"  {x['id']} | ({x['track']}) {x['title']}"
                     for x in r["nodes"] if x["track"] != "core")
    return r, spine, side


def _history(cid, n=6):
    c = store.chat_get(cid) or {"messages": []}
    return "\n".join(f"  {'User' if m['role']=='u' else 'Assistant'}: {m['text'][:300]}"
                     for m in c["messages"][-n:])


def route(s: CS) -> dict:
    r, spine, side = _ctx(s["roadmap_id"])
    out = llm.structured(f"""Classify one message in a conversation about someone's roadmap.

THEIR GOAL: {r['goal']}
THEIR BACKGROUND: {r['background']}

ROADMAP — core sequence (id | title):
{spine}
BRANCHES:
{side}

CONVERSATION SO FAR:
{_history(s['chat_id'])}

THEIR MESSAGE: {s['message']}

intent:
  "mutate"  — they are telling us something that changes the remaining plan: a step
              is now done, their circumstances changed, they want a different route,
              they want more or less detail somewhere. Anything that should edit the
              roadmap.
  "search"  — a question needing current external facts (prices, dates, providers,
              recent rule changes).
  "answer"  — anything else: reasoning about the plan, sequencing, what something
              means, what to do next. Answerable from the roadmap itself.

For "mutate" only:
  anchor_id — the id of the node their news attaches to. Everything AFTER this node
              gets replanned, so pick the LAST node that is unaffected or completed,
              never the first node that must change.
  instruction — restate what they told us, in one or two sentences, as input to the
              replanner. Empty for other intents.""", ROUTE_SCHEMA, temperature=0.0)
    ids = {n["id"] for n in store.get(s["roadmap_id"])["nodes"]}
    if out.get("intent") == "mutate" and out.get("anchor_id") not in ids:
        out["intent"] = "answer"          # unusable anchor — answer rather than guess
    return {"intent": out["intent"], "anchor_id": out.get("anchor_id", ""),
            "instruction": out.get("instruction", "")}


def _prompt(s, grounded):
    r, spine, side = _ctx(s["roadmap_id"])
    return f"""Answer one message in a conversation about this person's roadmap.

THEIR GOAL: {r['goal']}
THEIR BACKGROUND: {r['background'] or '(not given)'}
WHAT THEY TOLD US: {json.dumps(r['clarifications'])}

THEIR ROADMAP — core sequence:
{spine}
BRANCHES:
{side}

{('RESEARCH BEHIND THIS ROADMAP:' + chr(10) + r['brief'][:6000]) if not grounded
  else 'Search the web for current, authoritative specifics before answering.'}

CONVERSATION SO FAR:
{_history(s['chat_id'])}

THEIR MESSAGE: {s['message']}

Answer directly. Rules:
- Short. 2-5 sentences unless a list is genuinely needed.
- Answer for THIS person, using their background and where they are in this plan.
  If the honest answer is "you can skip that", say it.
- Take their background literally — never credit them with a qualification they
  did not claim.
- Refer to steps by their real names.
- If you don't know, say so.
- Markdown, no headings."""


def answer(s: CS) -> dict:
    out = llm.structured(_prompt(s, False) + '\n\nReturn JSON: {"answer": "..."}',
                         {"type": "OBJECT", "properties": {"answer": S_},
                          "required": ["answer"]}, temperature=0.3)
    return {"answer": out["answer"], "sources": []}


def search(s: CS) -> dict:
    text, cited = llm.grounded(_prompt(s, True))
    return {"answer": text, "sources": cited}


def mutate(s: CS) -> dict:
    """Hand off to the replan graph on a worker thread; the UI polls the roadmap."""
    rid, anchor, instr = s["roadmap_id"], s["anchor_id"], s["instruction"]
    node = store.node(anchor)
    store.patch(rid, status="replanning", error=None)

    def work():
        try:
            REPLAN.invoke({"roadmap_id": rid, "anchor_id": anchor, "instruction": instr},
                          {"configurable": {"thread_id": f"{rid}:replan:{int(time.time()*1000)}"},
                           "recursion_limit": 50})
        except Exception as e:
            store.patch(rid, status="error", error=str(e))

    threading.Thread(target=work, daemon=True).start()
    return {"answer": f"Updating your roadmap from **{node['title']}** onwards. "
                      f"Everything before it, and your progress on steps that survive, is kept.",
            "sources": [], "replanning": True}


def save(s: CS) -> dict:
    store.msg_add(s["chat_id"], "a", s.get("answer") or "",
                  {"sources": s.get("sources") or [],
                   "replanning": bool(s.get("replanning")),
                   "intent": s.get("intent")})
    return {}


def build():
    g = StateGraph(CS)
    for fn in (route, answer, search, mutate, save):
        g.add_node(fn.__name__, fn)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", lambda s: s.get("intent") or "answer",
                            {"answer": "answer", "search": "search", "mutate": "mutate"})
    for n in ("answer", "search", "mutate"):
        g.add_edge(n, "save")
    g.add_edge("save", END)
    cp = SqliteSaver(sqlite3.connect(
        os.path.join(os.path.dirname(__file__), "..", "checkpoints.db"),
        check_same_thread=False))
    cp.setup()
    return g.compile(checkpointer=cp)

CONVERSE = build()
