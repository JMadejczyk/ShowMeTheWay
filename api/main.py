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
from converse import CONVERSE
import enrich

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


class NewChat(BaseModel):
    roadmap_id: str | None = None
    title: str = "New chat"

class Say(BaseModel):
    message: str
    role: str = "u"
    meta: dict = {}

class Link(BaseModel):
    roadmap_id: str
    title: str | None = None


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


# ---- chats. The artifact is the durable object; chats attach to it.

@app.get("/api/chats")
def chats(roadmap_id: str | None = None):
    out = []
    for c in store.chat_list(roadmap_id):
        full = store.chat_get(c["id"])
        out.append({**c, "n": len(full["messages"]),
                    "preview": next((m["text"] for m in full["messages"] if m["role"] == "u"), "")})
    return out

@app.get("/api/chats/{cid}")
def chat_one(cid: str):
    return store.chat_get(cid) or {"error": "not found"}

@app.post("/api/chats")
def chat_new(b: NewChat):
    return {"id": store.chat_create(b.title, b.roadmap_id)}

@app.post("/api/chats/{cid}/link")
def chat_link(cid: str, b: Link):
    """Called once the creation chat has produced its roadmap."""
    f = {"roadmap_id": b.roadmap_id}
    if b.title:
        f["title"] = b.title
    store.chat_patch(cid, **f)
    return {"ok": True}

@app.post("/api/chats/{cid}/msg")
def chat_msg(cid: str, b: Say):
    """Persist a user message verbatim (used by the creation flow, which drives the
    pipeline endpoints directly rather than going through the converse graph)."""
    store.msg_add(cid, b.role, b.message, b.meta)
    return {"ok": True}

@app.post("/api/chats/{cid}/say")
def chat_say(cid: str, b: Say):
    """A message in a chat attached to an existing artifact."""
    c = store.chat_get(cid)
    if not c:
        return {"error": "no chat"}
    if not c["roadmap_id"]:
        return {"error": "chat is not attached to a roadmap"}
    store.msg_add(cid, "u", b.message)
    try:
        out = CONVERSE.invoke(
            {"chat_id": cid, "roadmap_id": c["roadmap_id"], "message": b.message},
            {"configurable": {"thread_id": f"{cid}:{int(time.time()*1000)}"}})
    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}
    return {"a": out.get("answer", ""), "sources": out.get("sources", []),
            "intent": out.get("intent"), "replanning": bool(out.get("replanning"))}


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
        try:
            out = enrich.ensure(b.id, force=b.force)
        except Exception as e:
            traceback.print_exc()
            return {"error": str(e)}
        return {**out, "qa": store.qa_for_node(b.id)}

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
