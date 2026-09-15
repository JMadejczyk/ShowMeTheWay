"""
Source adapters. Each turns intake payload into (context, urls):
  context -> spliced into the research prompt
  urls    -> handed to Gemini's url_context tool
Adding a source type = adding one entry. Nothing else changes.
"""
import re

def _web(v):   return "", []                      # the grounded call does its own searching
def _paste(v): return (f"\n--- USER DOCUMENT ---\n{str(v)[:40000]}\n--- END ---\n" if str(v or "").strip() else ""), []
def _urls(v):  return "", [u for u in re.split(r"[\s,]+", str(v or "")) if u.startswith("http")][:8]
def _files(v): return "".join(f"\n--- FILE: {f['name']} ---\n{str(f['text'])[:20000]}\n--- END ---\n" for f in (v or [])), []
def _drive(v): return "", []                      # interface ready; needs OAuth

ADAPTERS = {
    "web":   {"label": "Web search",    "ready": True,  "run": _web},
    "paste": {"label": "Pasted text",   "ready": True,  "run": _paste},
    "urls":  {"label": "URLs",          "ready": True,  "run": _urls},
    "files": {"label": "Local files",   "ready": True,  "run": _files},
    "drive": {"label": "Google Drive",  "ready": False, "run": _drive},
}

def collect(sources: dict):
    ctx, urls = "", []
    for k, v in (sources or {}).items():
        a = ADAPTERS.get(k)
        if not a or not a["ready"]:
            continue
        c, u = a["run"](v)
        ctx += c
        urls += u
    return ctx, urls
