import os, json, time, threading, traceback
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langgraph.types import Command

import store, llm
from graph import GRAPH
from replan import REPLAN
from ask import ASK

app = FastAPI(title="ShowMeTheWay")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

cfg = lambda rid: {"configurable": {"thread_id": rid}, "recursion_limit": 50}


@app.on_event("startup")
def unstick():
    """A server restart kills in-flight worker threads, stranding roadmaps in a
    transient status forever. Sweep them on boot: anything with nodes goes back to
    ready, anything without is marked failed so the UI can say so."""
    for r in store.listing():
        if r["status"] in ("researching", "structuring", "replanning"):
            has = store.get(r["id"])["nodes"]
            store.patch(r["id"], status="ready" if has else "error",
                        error=None if has else "generation was interrupted by a server restart")
            print(f"[boot] unstuck {r['id']} ({r['status']} -> {'ready' if has else 'error'})")


class Start(BaseModel):
    goal: str
    background: str = ""
    sources: dict = {}

class Resume(BaseModel):
    answers: list = []

class Replan(BaseModel):
    anchor_id: str
    instruction: str = ""


class NodeAct(BaseModel):
    action: str
    id: str
    question: str | None = None
    status: str | None = None
    x: float | None = None
    y: float | None = None
    force: bool = False


@app.get("/api/health")
def health():
    """Re-reads .env.local and drops the model cache, so adding a key or changing
    GEMINI_MODEL takes effect without restarting the server."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env.local", override=True)
    llm._avail = None
    llm._resolved = {}
    llm._client = None
    has = bool(os.environ.get("GEMINI_API_KEY"))
    return {
        "ok": has,
        "key": has,
        "requested": os.environ.get("GEMINI_MODEL"),
        "research": llm.best_model("research"),
        "structure": llm.best_model("structure"),
        "available": llm.available(),
    }


class Profile(BaseModel):
    docs: list = []          # [{name, text}]
    goal: str = ""


@app.post("/api/profile")
def profile(b: Profile):
    """Read attached documents and state, in the first person, what they say about
    this person's starting point. Shown in chat the moment they attach a file, so
    the attachment visibly does something before the roadmap even generates — and
    the result is what we hand the pipeline as `background`."""
    if not b.docs:
        return {"background": "", "summary": ""}
    blob = "\n\n".join(f"--- {d.get('name','doc')} ---\n{str(d.get('text',''))[:20000]}"
                         for d in b.docs)
    out = llm.structured(f"""These documents belong to someone working toward this goal:
{b.goal or '(not yet stated)'}

DOCUMENTS:
{blob}

Return:
- background: a dense factual paragraph of what these documents establish about
  their experience, qualifications and current position. Write it as the person
  ("8 years as a paramedic, holds..."). State only what the documents support —
  never infer a qualification that is not there. This is fed to a planner.
- summary: one short friendly sentence acknowledging what you just read, addressed
  to them ("I've read your CV — 8 years as a paramedic, ..."). Max 30 words.""",
        {"type": "OBJECT",
         "properties": {"background": {"type": "STRING"}, "summary": {"type": "STRING"}},
         "required": ["background", "summary"]}, temperature=0.2)
    return out


@app.get("/api/roadmaps")
def listing():
    return store.listing()


@app.get("/api/roadmaps/{rid}")
def one(rid: str):
    return store.get(rid) or {"error": "not found"}


@app.post("/api/roadmaps")
def start(b: Start):
    """Runs the graph up to the clarify interrupt and returns the questions."""
    rid = store.create(b.goal, b.background, b.sources)
    try:
        GRAPH.invoke({"roadmap_id": rid, "goal": b.goal, "background": b.background,
                      "sources": b.sources, "attempts": 0}, cfg(rid))
    except Exception as e:
        traceback.print_exc()
        store.patch(rid, status="error", error=str(e))
        return {"id": rid, "error": str(e)}
    r = store.get(rid)
    return {"id": rid, "questions": r["questions"], "title": r["title"]}


@app.post("/api/roadmaps/{rid}/resume")
def resume(rid: str, b: Resume):
    """Resumes past the interrupt; research + structure run on a worker thread."""
    store.patch(rid, clarifications=json.dumps(b.answers), status="researching")

    def work():
        try:
            GRAPH.invoke(Command(resume=b.answers), cfg(rid))
        except Exception as e:
            traceback.print_exc()
            store.patch(rid, status="error", error=str(e))

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True}


@app.post("/api/roadmaps/{rid}/replan")
def replan(rid: str, b: Replan):
    """Rebuilds everything downstream of one node. Upstream is frozen; surviving
    downstream nodes keep their status and already-researched detail."""
    if not store.node(b.anchor_id):
        return {"error": "no such node"}
    store.patch(rid, status="replanning", error=None)

    def work():
        try:
            # fresh thread id per replan so the checkpointer doesn't resume a finished run
            REPLAN.invoke(
                {"roadmap_id": rid, "anchor_id": b.anchor_id, "instruction": b.instruction},
                {"configurable": {"thread_id": f"{rid}:replan:{int(time.time()*1000)}"},
                 "recursion_limit": 50})
        except Exception as e:
            traceback.print_exc()
            store.patch(rid, status="error", error=str(e))

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True}


@app.post("/api/node")
def node_act(b: NodeAct):
    if b.action == "status":
        store.node_patch(b.id, status=b.status)
        return {"ok": True}

    if b.action == "move":
        store.node_patch(b.id, x=b.x, y=b.y)
        return {"ok": True}

    if b.action == "qa":
        return {"qa": store.qa_for_node(b.id)}

    if b.action == "detail":
        n = store.node(b.id)
        if not n:
            return {"error": "no node"}
        if n["detail"] and not b.force:
            return {"detail": n["detail"], "sources": json.loads(n["sources"] or "[]"),
                    "qa": store.qa_for_node(b.id)}

        r = store.get(n["roadmap_id"])
        text, srcs = llm.grounded(f"""Write a practical deep-dive for one step of someone's roadmap.
Search the web for current, authoritative specifics.

THEIR GOAL: {r['goal']}
THEIR BACKGROUND: {r['background'] or '(not given)'}
THIS STEP: {n['title']}
CONTEXT: {n['summary']}

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
        store.node_patch(b.id, detail=text, sources=json.dumps(srcs))
        return {"detail": text, "sources": srcs, "qa": store.qa_for_node(b.id)}

    if b.action == "ask":
        n = store.node(b.id)
        if not n:
            return {"error": "no node"}
        q = (b.question or "").strip()
        if not q:
            return {"error": "empty question"}
        try:
            out = ASK.invoke(
                {"roadmap_id": n["roadmap_id"], "node_id": b.id, "question": q},
                {"configurable": {"thread_id": f"{b.id}:ask:{int(time.time()*1000)}"}})
        except Exception as e:
            traceback.print_exc()
            return {"error": str(e)}
        srcs = out.get("sources", [])
        return {"q": q, "a": out.get("answer", ""), "sources": srcs,
                "grounded": bool(srcs)}

    return {"error": "unknown action"}
