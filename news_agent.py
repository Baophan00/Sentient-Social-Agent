# news_agent.py
# 2-step: summarize_only (Fireworks) & deep_analyze_only (ODS)
from __future__ import annotations
import os, re, logging, requests
from typing import List, Optional

log = logging.getLogger("ssa.news")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "").strip()
FIREWORKS_MODEL = os.getenv("FIREWORKS_MODEL","accounts/sentientfoundation/models/dobby-unhinged-llama-3-3-70b-new").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
SEARXNG_INSTANCE_URL = os.getenv("SEARXNG_INSTANCE_URL", "").strip()
SEARXNG_API_KEY = os.getenv("SEARXNG_API_KEY", "").strip()
JINA_API_KEY = os.getenv("JINA_API_KEY", "").strip()
ODS_MODEL = os.getenv("ODS_MODEL", os.getenv("LITELLM_MODEL_ID", "openrouter/google/gemini-2.0-flash-001")).strip()

DIV = "────────────────────────────────"

def _clean(s:str)->str:
    if not s: return ""
    s = re.sub(r"^\s*#{1,6}\s*","", s, flags=re.MULTILINE)  # bỏ #/##/###
    s = re.sub(r"\n{3,}", "\n\n", s)                        # chuẩn hoá xuống dòng
    return s.strip()

def _wrap(title:str, body:str)->str:
    body = _clean(body)
    return f"**{title}**\n{body}" if body else ""

def _card(summary_block:str="", analysis_block:str="", link:str="")->str:
    parts=[]
    if summary_block:
        parts.append(_wrap("Summary", summary_block))
        if "Impact" not in summary_block:
            parts.append("**Impact**\n(impact not provided)")
    if analysis_block:
        t=_clean(analysis_block)
        # gán heading nếu model không trả heading
        if not re.search(r"(?i)\bDeep Analysis\b", t):
            t = f"**Deep Analysis**\n{t}"
        parts.append(t)
    card = f"{DIV}\n" + "\n\n".join([p for p in parts if p.strip()]) + f"\n\n{DIV}"
    if link: card += f"\nLink: {link}"
    return card.strip()

SYSTEM_SUMMARY = (
    "You are a concise news summarizer. Output clean English in a card layout without markdown headers (#). "
    "Use short bullets and always include a one-line Impact."
)
SUMMARY_PROMPT = (
    "Create a compact news card in English. Do NOT use '#', '##', or '###' headers.\n\n"
    "Sections and rules:\n"
    "1) Summary: exactly 3 bullets. Start each bullet with '• '. Keep lines short.\n"
    "2) Impact: one line starting with 'Impact — '.\n"
    "No extra commentary, no code fences.\n\n"
    "Title: {title}\nDescription: {description}\nLink: {link}\n"
)
ODS_PROMPT = (
    "Deeply analyze this news item. If a link is provided, consult it and corroborate with search. "
    "Return a single clean card with these sections. Do NOT use '#', '##', or '###' headers.\n\n"
    "- Deep Analysis: 3–5 bullets (start with '• '), focus on causes, context, second-order effects.\n"
    "- Why it matters: 2 bullets (start with '• ').\n"
    "- Risks: one bullet (start with '• ').\n"
    "- Opportunities: one bullet (start with '• ').\n"
    "- Market view: one line starting with 'Market — '.\n"
    "- Sources: list 1–3 relevant URLs.\n\n"
    "Title: {title}\nDescription: {description}\nLink: {link}\n"
)

def _fireworks_complete(prompt:str, model:Optional[str]=None)->str:
    if not FIREWORKS_API_KEY:
        raise RuntimeError("FIREWORKS_API_KEY is missing")
    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    headers = {"Authorization": f"Bearer {FIREWORKS_API_KEY}","Content-Type":"application/json"}
    payload = {
        "model": (model or FIREWORKS_MODEL),
        "messages":[{"role":"system","content":SYSTEM_SUMMARY},{"role":"user","content":prompt}],
        "temperature":0.25,"max_tokens":700,"stream":False,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content","") or ""
    return _clean(text)

def _openai_complete(prompt:str)->str:
    if not OPENAI_API_KEY: return ""
    url="https://api.openai.com/v1/chat/completions"
    headers={"Authorization":f"Bearer {OPENAI_API_KEY}","Content-Type":"application/json"}
    payload={
        "model":OPENAI_MODEL,
        "messages":[{"role":"system","content":SYSTEM_SUMMARY},{"role":"user","content":prompt}],
        "temperature":0.3,"max_tokens":700,"stream":False,
    }
    r=requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code!=200:
        log.warning("OpenAI non-200: %s %s", r.status_code, r.text[:200]); return ""
    data=r.json()
    text=((data.get("choices") or [{}])[0].get("message") or {}).get("content","") or ""
    return _clean(text)

def _ods_deep(title:str, desc:str, link:str)->str:
    try:
        from opendeepsearch import OpenDeepSearchTool
    except Exception as e:
        log.warning("ODS import failed: %s", e); return ""
    reranker = "jina" if JINA_API_KEY else "infinity"
    kwargs = {"model_name": ODS_MODEL or "openrouter/google/gemini-2.0-flash-001", "reranker": reranker}
    if SEARXNG_INSTANCE_URL:
        kwargs.update({"search_provider":"searxng","searxng_instance_url":SEARXNG_INSTANCE_URL})
        if SEARXNG_API_KEY: kwargs["searxng_api_key"]=SEARXNG_API_KEY
    tool = OpenDeepSearchTool(**kwargs)
    if getattr(tool,"is_initialized",True) is False:
        try: tool.setup()
        except Exception as e: log.warning("ODS setup failed: %s", e); return ""
    q = ODS_PROMPT.format(title=title, description=desc, link=link)
    try:
        res = tool.forward(q)  # bạn có thể bật pro_mode/top_k/max_docs ở đây nếu muốn
        return _clean(str(res) if res is not None else "")
    except Exception as e:
        log.warning("ODS forward failed: %s", e); return ""

class SummarizerService:
    def __init__(self, fireworks_model: Optional[str]=None):
        self.fireworks_model = (fireworks_model or FIREWORKS_MODEL).strip()

    def summarize_only(self, title:str, description:str, link:str)->str:
        prompt = SUMMARY_PROMPT.format(title=title, description=description, link=link)
        out = ""
        try: out = _fireworks_complete(prompt, model=self.fireworks_model)
        except requests.HTTPError as e: log.warning("Fireworks HTTP error: %s", e)
        except Exception as e: log.warning("Fireworks error: %s", e)
        if not out:
            oa = _openai_complete(prompt)
            if oa: out = oa
        if not out: raise RuntimeError("No summarizer available")
        return _card(summary_block=out, link=link)

    def deep_analyze_only(self, title:str, description:str, link:str)->str:
        text = _ods_deep(title, description, link)
        if not text: raise RuntimeError("ODS unavailable or failed")
        return _card(analysis_block=text, link=link)
