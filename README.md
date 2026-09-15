# ShowMeTheWay

roadmap.sh for any field — researched live from the web, and shaped around what the
user already knows.

## Run

    printf 'GEMINI_API_KEY=%s\n' "your-key" > .env.local
    cd api && ../.venv/bin/uvicorn main:app --port 8000 --reload    # LLM backend
    npm run dev                                                      # UI on :3077

## Shape

    api/graph.py    LangGraph state machine — generation pipeline
    api/replan.py   LangGraph state machine — graph mutation ("I already know this")
    api/ask.py      LangGraph state machine — per-node Q&A
    api/llm.py      Gemini calls (grounded search / structured JSON)
    api/sources.py  pluggable source adapters (web, paste, urls, files, drive)
    api/store.py    roadmap/node/edge sqlite
    lib/layout.js   hybrid spine layout (roadmap.sh look, arbitrary-DAG safe)

## The two constraints that shaped it

1. **Gemini forbids Google Search grounding and `responseSchema` in one call.**
   Hence two passes: grounded research -> prose + citations, then ungrounded
   structuring -> strict graph JSON. `api/llm.py` keeps them as separate functions
   so this can't be accidentally violated.

2. **The clarify step is a genuine pause, not a UI state.** It's LangGraph's
   `interrupt()`, checkpointed to sqlite with `thread_id == roadmap_id`. A roadmap
   is a resumable thread, so a refresh mid-generation loses nothing and a failed
   structuring retries without paying for the web search again.

## Graph mutation

Mark a node cleared, hit **Replan everything after this**, optionally say what else
changed ("I already hold a Class 1 medical"). `api/replan.py` runs:

    START -> split -> [delta?] -> restructure -> merge -> END

* `split` computes the downstream frontier from the anchor (pure, no LLM).
* `needs_delta` is a conditional edge: a bare "I already know this" is answerable
  from the brief we already paid for, so it skips straight to restructuring. A
  substantive instruction may introduce facts the brief never covered — that earns
  a fresh grounded search.
* `merge` splices the result in under one transaction.

What makes it an edit rather than a regeneration:

* Everything upstream of the anchor is frozen — nodes, edges, statuses, cached
  deep-dives, hand-dragged positions.
* A downstream node that survives keeps its id, and therefore its status and its
  already-researched detail. Measured: 13/15 ids reused on a real replan, a 10k-char
  deep-dive carried through untouched.
* Steps you say you've finished are retained and marked cleared, never deleted —
  a completed step vanishing from the map is disorienting.
* "Which steps did they just claim?" comes back as its own schema field
  (`completed_ids`) and is applied in code. Relying on the model to set a per-node
  status field for this was measurably unreliable.

Known limits: a server restart kills in-flight worker threads. A boot sweep unsticks
any roadmap left mid-flight, but the run itself isn't resumed — the LangGraph
checkpoint is there to do it, that just isn't wired up.

## Per-node Q&A

Every node has an ask box. `api/ask.py`:

    START -> route -> (answer | search) -> save -> END

`route` exists because the two kinds of question cost very different amounts.
"Can I skip this given my background?" is answerable from the node's researched
notes plus the roadmap we're already holding — ~8s, no search. "What does it cost
in 2026?" is not, and earns a grounded lookup — ~15s.

The answer is given the goal, the background, the clarifying answers, this node's
researched detail, the whole core spine, and the last few turns of this node's own
thread — so it can say "you can skip this" and mean it.

Threads persist per node. A question you asked is still there when you come back,
which is the point of it not being a chat.

The "searched the web" badge is driven by whether citations actually came back, not
by which branch the router picked — the model can decline to call the tool, and
labelling that answer web-backed would be a lie.

## Concurrency

`store.py` opens one sqlite connection **per thread**. A single shared connection
meant one request's `commit()` cleared another's implicit transaction, and the
second `commit()` died with "cannot commit - no transaction is active" — reproduced
by opening a node (30s deep-dive) and asking a question at the same time. WAL is on
so reads don't block on writes.

## Google Workspace shell (`/workspace`)

A prototype Gemini skin over the same engine. Not affiliated with Google; built for
presentation, kept local, never hosted.

    /            the standalone app (unchanged)
    /workspace   Gemini chat clone -> roadmap opens as a Canvas-style artifact

The chat needed no new pipeline. `clarify` is already a LangGraph `interrupt()` —
the graph pauses and waits for the user, which *is* a chat turn. Moving from a form
to one-question-per-turn was a rendering change, not a redesign.

### The Drive picker is a facade over a real path

The connection is fake; the effect is not. `lib/drive.js` holds five documents with
real text, and attaching one sends it through the same source adapter as a paste.
Measured on a live run with a CV, an internal Trust RNDA policy, and a route
comparison sheet attached — every private fact reached the roadmap:

  * Annex 21 trainee pay banding      (only in the Trust policy)
  * substantive-contract eligibility  (only in the Trust policy)
  * DipHE is not a degree             (only in the CV)
  * MSc route ruled out               (only in the route sheet)
  * NHS Learning Support Fund         (only in the route sheet)
  * cannot relocate                   (only in the career notes)

`POST /api/profile` reads the attachments and returns both a first-person
`background` for the pipeline and a one-line `summary` shown in chat, so the
attachment visibly does something before the roadmap even generates.

## Artifact as the primary object

The roadmap is the durable thing; chats attach to it, not the reverse.

    /workspace              Gemini chat — creates a roadmap, or talks to an existing one
    /workspace/drive        Drive grid — artifacts alongside the same canned documents
    /workspace/a/<id>       the artifact's own page, with the chats attached to it

Rail order is New chat -> Recent (chats) -> Artifacts (roadmaps).

`api/converse.py` is what makes an attached chat worth having:

    START -> route -> (answer | search | mutate) -> save -> END

A message is one of three things, costing very different amounts:
  * answerable from the roadmap we already hold          (~6s)
  * needs current world facts                            (~15s, grounded)
  * news that changes the plan -> hands to REPLAN        (~25s, async)

The third is the point. "I passed the numeracy exam and finished my theory hours"
routes to mutate, picks the anchor node, and edits the roadmap — verified end to
end: both claimed steps were retained and marked cleared, and everything upstream
was untouched.

Chats and messages persist (`chat`, `message` tables), so Recent is real and a
roadmap can carry several conversations.

## Per-step research happens at creation, not on click

`api/enrich.py` fills in every step's deep dive as part of the pipeline:

    creation: clarify -> research -> structure -> persist -> enrich
    replan:   split -> [delta] -> restructure -> merge -> enrich

Timing is the design constraint. A deep dive is a grounded call (~30s) and a roadmap
has 20-30 nodes, so sequentially this is ten minutes. Therefore:

  * `persist` marks the roadmap ready BEFORE `enrich` runs, so the canvas still
    appears at the same ~65s it always did;
  * enrichment then runs on a 5-worker pool behind it, core spine first, since
    those are the nodes anyone actually clicks;
  * a node clicked before its turn still generates on demand — one lock per node id
    means the eager pass and a click can never pay for the same generation twice.

Measured on a fresh 23-node roadmap: ready at 65s, fully researched at 196s,
211,366 chars of detail across 296 citations. Opening a node went from ~30s to 10ms.

`enriched` / `enrich_total` on the roadmap drive a progress line in both artifact
views; the UI keeps polling while they differ.
