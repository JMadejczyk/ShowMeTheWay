"""
Roadmap generation as a LangGraph state machine.

    START -> clarify -*interrupt*-> research -> structure -> persist -> END
                                                    ^__retry__|

Why a graph and not a script:
  * clarify uses interrupt() — the human-in-the-loop pause IS a first-class state,
    so the run survives a page refresh instead of living in React state.
  * the SqliteSaver checkpoints every step, so a failed structure retries from the
    research result instead of paying for the search again.
  * thread_id == roadmap_id, so a roadmap is literally a resumable thread.
"""
import os, sqlite3
from typing import TypedDict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from langgraph.checkpoint.sqlite import SqliteSaver

import llm, store
from sources import collect

S_ = {"type": "STRING"}

CLARIFY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": S_,
        "questions": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"q": S_, "why": S_,
                           "suggestions": {"type": "ARRAY", "items": S_}},
            "required": ["q", "why", "suggestions"]}},
    },
    "required": ["title", "questions"],
}

ROADMAP_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": S_,
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
    "required": ["title", "nodes", "edges"],
}


class S(TypedDict, total=False):
    roadmap_id: str
    goal: str
    background: str
    sources: dict
    questions: list
    clarifications: list
    brief: str
    cited: list
    data: dict
    attempts: int


# ---------------------------------------------------------------- nodes

def clarify(s: S) -> dict:
    out = llm.structured(f"""A user wants a personalised learning roadmap.

GOAL: {s['goal']}
THEIR BACKGROUND: {s.get('background') or '(not given)'}

Ask 3-5 short questions whose answers would MATERIALLY change the roadmap's shape —
things you genuinely cannot infer. Good targets: jurisdiction/country (licensing and
accreditation differ enormously outside tech), time budget, target timeline, whether
they need a formal credential or just competence, budget, which sub-specialism.

Do NOT ask what you can already infer from their background. For each question give
2-4 concrete tappable suggestions so they can answer in one click.
Also propose a short roadmap title.""", CLARIFY_SCHEMA)

    store.patch(s["roadmap_id"], title=out.get("title") or "Untitled roadmap",
                questions=__import__("json").dumps(out["questions"]), status="clarifying")

    # Pause the graph here. Resumes via Command(resume=[{q,a},...]).
    answers = interrupt({"questions": out["questions"], "title": out.get("title")})
    return {"questions": out["questions"], "clarifications": answers or []}


def research(s: S) -> dict:
    store.patch(s["roadmap_id"], status="researching")
    ctx, urls = collect(s.get("sources") or {})
    qa = "\n".join(f"- {c['q']} -> {c['a']}" for c in (s.get("clarifications") or []))
    text, cited = llm.grounded(f"""Research what it actually takes to achieve this goal. Use web search
aggressively — prefer official/authoritative sources (regulators, licensing bodies,
accredited institutions, professional associations, standards bodies) over listicles.

GOAL: {s['goal']}
BACKGROUND: {s.get('background') or '(not given)'}
{('CLARIFICATIONS:\n' + qa) if qa else ''}
{ctx}

Produce a research brief covering:
1. The real end-to-end path, in the order things must happen.
2. Hard gates: licences, exams, registrations, accreditation, supervised hours,
   background checks, mandatory training — with actual names and issuing bodies,
   specific to their jurisdiction if known.
3. Prerequisites and how long each realistically takes.
4. Legitimate alternative routes (apprenticeship vs degree vs conversion course).
5. Optional / specialisation branches that come after the core path.
6. Concrete named resources: courses, textbooks, exam syllabi, official handbooks.
7. Explicitly: given THIS person's background, what can they skip or fast-track,
   and what transfers across? Be specific and honest.

Write densely. This is input to another model, not to a human.""", urls)

    store.patch(s["roadmap_id"], brief=text,
                sources=__import__("json").dumps(cited))
    return {"brief": text, "cited": cited}


def structure(s: S) -> dict:
    store.patch(s["roadmap_id"], status="structuring")
    srcs = "\n".join(f"- {c['title']} :: {c['url']}" for c in (s.get("cited") or []))
    data = llm.structured(f"""Turn this research brief into a roadmap graph, in the style of
roadmap.sh but for any field.

GOAL: {s['goal']}
BACKGROUND: {s.get('background') or '(not given)'}

RESEARCH BRIEF:
{s['brief']}

AVAILABLE SOURCES:
{srcs}

Rules:
- 18-30 nodes. Fewer is better than padded.
- track "core": the spine, the must-do sequence, in order. 8-14 of these.
- track "alternative": a genuinely different route to the same milestone
  (e.g. "Degree route" vs "Apprenticeship route"). parent = the core node id.
- track "optional": specialisations / nice-to-have. parent = a core node id.
- id: lowercase-kebab, stable, unique.
- parent: "" for core spine nodes, else the id of the core node it hangs off.
- summary: 1-2 sentences, concrete. Name real bodies/exams/courses, never vague advice.
- status: "known" ONLY where their stated background genuinely already covers it.
  This is the most important field — be decisive, not generous. A paramedic moving to
  nursing already has anatomy and patient contact; they do NOT have pharmacology.
- A competency they ALREADY HAVE that is a real prerequisite stays on the "core"
  spine with status "known". Do NOT demote it to "optional" — the user needs to see
  what they can skip sitting in the main sequence, not tucked into a side branch.
  Expect several core nodes to come back "known" for an experienced career-changer.
- Never assert a qualification they did not state. If they said "no degree", they
  have no degree; do not infer a diploma from their job title.
- whyKnown: one clause justifying a "known" call, "" otherwise.
- edges: "main" edges chain core nodes in order; "branch" edges connect a core node
  to each of its alternative/optional children.""", ROADMAP_SCHEMA,
        temperature=0.3 + 0.2 * s.get("attempts", 0))
    return {"data": data, "attempts": s.get("attempts", 0) + 1}


def valid(s: S) -> str:
    """Conditional edge: a roadmap with no core spine is unusable — retry once."""
    d = s.get("data") or {}
    core = [n for n in d.get("nodes", []) if n.get("track") == "core"]
    if len(d.get("nodes", [])) >= 6 and len(core) >= 3:
        return "persist"
    return "structure" if s.get("attempts", 0) < 2 else "persist"


def persist(s: S) -> dict:
    store.save_graph(s["roadmap_id"], s.get("data") or {})
    store.patch(s["roadmap_id"], status="ready",
                title=(s.get("data") or {}).get("title") or "Untitled roadmap")
    return {}


# ---------------------------------------------------------------- build

def build():
    g = StateGraph(S)
    for fn in (clarify, research, structure, persist):
        g.add_node(fn.__name__, fn)
    g.add_edge(START, "clarify")
    g.add_edge("clarify", "research")
    g.add_edge("research", "structure")
    g.add_conditional_edges("structure", valid, {"structure": "structure", "persist": "persist"})
    g.add_edge("persist", END)

    path = os.path.join(os.path.dirname(__file__), "..", "checkpoints.db")
    cp = SqliteSaver(sqlite3.connect(path, check_same_thread=False))
    cp.setup()
    return g.compile(checkpointer=cp)

GRAPH = build()
