"""Native google-genai calls. LangGraph owns orchestration; this owns the model."""
import os, json, re, threading
from google import genai
from google.genai import types

# Lazy init must be locked. The enrichment pool starts five workers at once; each
# saw _client as None, each built a Client, and the orphans were garbage-collected
# and closed while threads were still using them — "Cannot send a request, as the
# client has been closed", losing ~4 steps per roadmap.
_client = None
_init = threading.Lock()

def client():
    global _client
    if _client is None:
        with _init:
            if _client is None:
                key = os.environ.get("GEMINI_API_KEY")
                if not key:
                    raise RuntimeError("GEMINI_API_KEY missing in .env.local")
                _client = genai.Client(api_key=key)
    return _client

# Model selection.
#   GEMINI_MODEL            — global override
#   GEMINI_MODEL_RESEARCH   — override for the grounded research pass
#   GEMINI_MODEL_STRUCTURE  — override for the structured graph pass
# An override is checked against the key's own model list. If it doesn't exist we
# fall back to the closest available match and say so, rather than 404ing mid-demo.
_RANK = [(r"gemini-3\.\d+.*flash", 110), (r"gemini-3.*flash", 100), (r"gemini-3.*pro", 95),
         (r"gemini-2\.5-pro", 80), (r"pro", 60), (r"gemini-2\.5-flash", 40), (r"flash", 30)]
_avail: list[str] | None = None
_resolved: dict[str, str] = {}
FALLBACK = "gemini-2.5-flash"


_mlock = threading.Lock()

def available() -> list[str]:
    global _avail
    if _avail is not None:
        return _avail
    with _mlock:
        if _avail is None:
            try:
                _avail = [m.name.replace("models/", "") for m in client().models.list()
                          if "generateContent" in (m.supported_actions or [])
                          and not re.search(
                              r"embedding|imagen|veo|tts|image|live|native-audio", m.name)]
            except Exception as e:
                print("[model] list failed:", e)
                _avail = []
    return _avail


def _rank(names: list[str]) -> list[str]:
    def score(n):
        s = max([v for p, v in _RANK if re.search(p, n, re.I)] or [0])
        return s - (5 if re.search(r"preview|exp", n, re.I) else 0)
    return sorted(names, key=score, reverse=True)


def best_model(role: str | None = None) -> str:
    key = role or "_"
    if key in _resolved:
        return _resolved[key]

    want = (os.environ.get(f"GEMINI_MODEL_{role.upper()}") if role else None) \
        or os.environ.get("GEMINI_MODEL")
    names = available()

    if want:
        if not names:
            pick = want                                   # can't verify; trust the operator
        elif want in names:
            pick = want
        else:
            # closest match on the version/family stem, e.g. "gemini-3.8-flash"
            stem = re.sub(r"[^a-z0-9.]", "", want.lower())
            near = [n for n in names if stem[:13] in re.sub(r"[^a-z0-9.]", "", n.lower())] \
                or [n for n in names if re.search(r"flash" if "flash" in want else r"pro", n, re.I)]
            pick = (_rank(near) or _rank(names) or [FALLBACK])[0]
            print(f"[model] !! '{want}' is not in this key's model list. Using '{pick}'.")
            print(f"[model]    available: {', '.join(_rank(names)[:8])}")
    else:
        pick = (_rank(names) or [FALLBACK])[0]

    _resolved[key] = pick
    print(f"[model] {role or 'default'} -> {pick}")
    return pick


# The model treats google_search as optional and frequently answers from memory
# instead — measured 0 citations and 0 searches on two consecutive baseline runs of
# the same prompt. Saying so explicitly produced 29 and 19 citations on the same
# prompt. There is no SDK switch for this: GoogleSearch exposes no force flag, and
# google_search_retrieval's dynamic threshold 400s on current models. So the mandate
# lives here, in the one function every grounded call goes through, rather than in
# each call site where it could be forgotten.
SEARCH_MANDATE = """

MANDATORY: search before you answer. Verify every provider name, cost, exam code,
body and date against current search results rather than recalling them. An answer
written from memory is not acceptable here."""


def grounded(prompt: str, urls: list[str] | None = None,
             mandate: bool = True) -> tuple[str, list[dict]]:
    """Google Search grounding. Cannot be combined with response_schema — API forbids it."""
    urls = urls or []
    if mandate:
        prompt += SEARCH_MANDATE
    tools = [types.Tool(google_search=types.GoogleSearch())]
    if urls:
        tools.append(types.Tool(url_context=types.UrlContext()))
        prompt += "\n\nAlso read these URLs:\n" + "\n".join(urls)
    r = client().models.generate_content(
        model=best_model("research"), contents=prompt,
        config=types.GenerateContentConfig(tools=tools, temperature=0.4),
    )
    seen, out = set(), []
    for c in (r.candidates or []):
        for ch in ((c.grounding_metadata.grounding_chunks if c.grounding_metadata else None) or []):
            if ch.web and ch.web.uri and ch.web.uri not in seen:
                seen.add(ch.web.uri)
                out.append({"title": ch.web.title or ch.web.uri, "url": ch.web.uri})
    return (r.text or ""), out


def structured(prompt: str, schema: dict, temperature: float = 0.3) -> dict:
    """Strict JSON out. No tools — that's the tradeoff for schema support."""
    r = client().models.generate_content(
        model=best_model("structure"), contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema, temperature=temperature),
    )
    return json.loads(r.text)
