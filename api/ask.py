"""
Per-node Q&A — the "ask about this step" box.

    START -> route -> (answer | search) -> save -> END

The router exists because the two kinds of question have very different costs.
"Why is this step before the exam?" is already answerable from the node's
researched detail plus the roadmap we're holding — ~3s, no search. "What does
the exam cost in 2026?" is not, and earns a grounded lookup — ~20s. Routing
first means the common question stays fast.

Answers are persisted per node: a question you asked in this workspace is still
there when you come back, which is the whole point of it not being a chat.
"""
import os, sqlite3, json
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

import llm, store

S_ = {"type": "STRING"}

ROUTE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "needs_search": {"type": "BOOLEAN"},
        "reason": S_,
    },
    "required": ["needs_search", "reason"],
}


class QS(TypedDict, total=False):
    roadmap_id: str
    node_id: str
    question: str
    needs_search: bool
    answer: str
    sources: list


def _ctx(s: QS):
    """Everything the answer should be grounded in: their goal, their background,
    this step, and where it sits in the roadmap."""
    n = store.node(s["node_id"])
    r = store.get(n["roadmap_id"])
    spine = "\n".join(
        f"  {'[done] ' if x['status'] in ('done','known') else ''}{x['title']}"
        for x in r["nodes"] if x["track"] == "core")
    thread = "\n".join(f"  Q: {x['q']}\n  A: {x['a'][:400]}"
                       for x in store.qa_for_node(s["node_id"])[-4:])
    return n, r, spine, thread


def route(s: QS) -> dict:
    n = store.node(s["node_id"])
    out = llm.structured(f"""Decide whether answering this question needs a live web search.

THE STEP: {n['title']} — {n['summary']}
WE ALREADY HOLD researched notes on this step: {'yes, ' + str(len(n['detail'] or '')) + ' chars' if n['detail'] else 'no'}
THE QUESTION: {s['question']}

needs_search = true only if the question asks for facts we would not already hold:
current prices, current dates or deadlines, specific named providers, recent rule
changes, availability, or anything time-sensitive.

needs_search = false for questions about reasoning, sequencing, relevance to this
person, what something means, whether they can skip it, or how it connects to the
rest of their roadmap — those are answerable from the notes and the roadmap.""",
        ROUTE_SCHEMA, temperature=0.0)
    return {"needs_search": bool(out.get("needs_search"))}


def _prompt(s, n, r, spine, thread, grounded):
    return f"""Answer one question about a single step of this person's roadmap.

THEIR GOAL: {r['goal']}
THEIR BACKGROUND: {r['background'] or '(not given)'}
WHAT THEY TOLD US: {json.dumps(r['clarifications'])}

THE STEP THEY'RE ASKING ABOUT: {n['title']}
  {n['summary']}
  Their status for it: {n['status']}{(' — ' + n['why_known']) if n['why_known'] else ''}

THEIR FULL ROADMAP (core sequence):
{spine}

{('RESEARCHED NOTES ON THIS STEP:' + chr(10) + (n['detail'] or '')[:7000]) if not grounded else 'Search the web for current, authoritative specifics before answering.'}

{('EARLIER IN THIS THREAD:' + chr(10) + thread) if thread else ''}

THEIR QUESTION: {s['question']}

Answer it directly. Rules:
- Short. This renders in a side panel, not a document. 2-5 sentences unless the
  question genuinely needs a list.
- Answer for THIS person. Use their background and where they are in this roadmap.
  If their experience means the honest answer is "you can skip this", say that.
- Take their stated background literally — never credit them with a qualification
  they did not claim.
- If you don't know, say so plainly rather than guessing.
- Markdown, no headings."""


def answer(s: QS) -> dict:
    n, r, spine, thread = _ctx(s)
    res = llm.structured(
        _prompt(s, n, r, spine, thread, False) + "\n\nReturn JSON: {\"answer\": \"...\"}",
        {"type": "OBJECT", "properties": {"answer": S_}, "required": ["answer"]},
        temperature=0.3)
    return {"answer": res["answer"], "sources": []}


def search(s: QS) -> dict:
    n, r, spine, thread = _ctx(s)
    text, cited = llm.grounded(_prompt(s, n, r, spine, thread, True))
    return {"answer": text, "sources": cited}


def save(s: QS) -> dict:
    # "grounded" means search actually returned citations — not merely that the
    # router sent us down the search branch. The model can decline to call the
    # tool, and labelling that answer as web-backed would be a lie.
    srcs = s.get("sources") or []
    store.qa_add(s["roadmap_id"], s["node_id"], s["question"],
                 s.get("answer") or "", srcs, bool(srcs))
    return {}


def build():
    g = StateGraph(QS)
    for fn in (route, answer, search, save):
        g.add_node(fn.__name__, fn)
    g.add_edge(START, "route")
    g.add_conditional_edges("route", lambda s: "search" if s.get("needs_search") else "answer",
                            {"search": "search", "answer": "answer"})
    g.add_edge("answer", "save")
    g.add_edge("search", "save")
    g.add_edge("save", END)
    cp = SqliteSaver(sqlite3.connect(
        os.path.join(os.path.dirname(__file__), "..", "checkpoints.db"),
        check_same_thread=False))
    cp.setup()
    return g.compile(checkpointer=cp)

ASK = build()
