# news_agent.py
from __future__ import annotations
import os, re, json, logging, requests, time, hashlib
from pathlib import Path
from typing import List, Optional, Callable

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

# ---------- Cache settings ----------
CACHE_DIR = Path("data/cache_analysis")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_CACHE_TTL = int(os.getenv("SUMMARY_CACHE_TTL", "86400"))   # 24h
DEEP_CACHE_TTL    = int(os.getenv("DEEP_CACHE_TTL",    "604800"))  # 7d

DIV = "────────────────────────────────"
BUL = "•"

def _clean_text(s: str) -> str:
    if not s: return ""
    s = re.sub(r"^\s*#{1,6}\s*", "", s, flags=re.MULTILINE)   # bỏ heading markdown
    s = re.sub(r"\n{3,}", "\n\n", s)                          # chuẩn hoá xuống dòng
    return s.strip()

def _wrap_section(title: str, body: str) -> str:
    body = _clean_text(body)
    if not body: return ""
    return f"**{title}**\n{body.strip()}"

def _ensure_card(summary_block: str, analysis_block: str, link: str = "") -> str:
    parts: List[str] = []
    if summary_block:
        parts.append(_wrap_section("Summary", summary_block))
        if "Impact:" not in summary_block and "Impact —" not in summary_block:
            parts.append("**Impact**\n(impact not provided)")
    if analysis_block:
        text = _clean_text(analysis_block)
        text = re.sub(r"(?i)^summary\s*:?\s*$", "**Summary**", text, flags=re.MULTILINE)
        text = re.sub(r"(?i)^deep analysis\s*:?\s*$", "**Summary**", text, flags=re.MULTILINE)
        text = re.sub(r"(?i)^(why it matters|why-this-matters)\s*:?\s*$", "**Why it matters**", text, flags=re.MULTILINE)
        text = re.sub(r"(?i)^risks?\s*:?\s*$", "**Risks**", text, flags=re.MULTILINE)
        text = re.sub(r"(?i)^opportunit(y|ies)\s*:?\s*$", "**Opportunities**", text, flags=re.MULTILINE)
        text = re.sub(r"(?i)^(market (impact|view))\s*:?\s*$", "**Market view**", text, flags=re.MULTILINE)
        text = re.sub(r"(?i)^sources?\s*:?\s*$", "**Sources**", text, flags=re.MULTILINE)
        parts.append(text)

    card_body = "\n\n".join([p for p in parts if p.strip()])
    card = f"{DIV}\n{card_body}\n\n{DIV}"

    if link:
        whole = card_body.lower()
        if link.lower() not in whole:
            card += f"\nLink: {link}"

    return card.strip()

SYSTEM_SUMMARY = (
    "You are a concise news summarizer. Output clean English in a card layout without markdown headers (#). "
    "Use short bullets and always include a one-line Impact."
)

SUMMARY_PROMPT_TEMPLATE = (
    "Create a compact news card in English. Do NOT use '#', '##', or '###' headers.\n\n"
    "Sections and rules:\n"
    "1) Summary: exactly 3 bullets. Start each bullet with '• '. Keep lines short.\n"
    "2) Impact: one line starting with 'Impact — '.\n"
    "No extra commentary, no code fences.\n\n"
    "Title: {title}\n"
    "Description: {description}\n"
    "Link: {link}\n"
)

ODS_ANALYSIS_PROMPT = (
    "Deeply analyze this news item. If a link is provided, consult it and corroborate with search. "
    "Return a single clean card with these sections. Do NOT use '#', '##', or '###' headers.\n\n"
    "Sections and rules:\n"
    "- Summary: 3–5 bullets (start with '• '), focus on causes, context, second-order effects.\n"
    "- Why it matters: 2 bullets (start with '• '), relevance for users/investors/builders.\n"
    "- Risks: one bullet (start with '• ').\n"
    "- Opportunities: one bullet (start with '• ').\n"
    "- Market view: one line starting with 'Market — '.\n"
    "- Sources: list 1–3 most relevant URLs used or corroborated.\n\n"
    "Keep it factual, neutral, and compact. No code fences.\n\n"
    "Title: {title}\n"
    "Description: {description}\n"
    "Link: {link}\n"
)

# ---------------- Cache helpers ----------------
def _cache_key(kind: str, title: str, description: str, link: str) -> str:
    raw = f"{kind}||{(title or '').strip()}||{(description or '').strip()}||{(link or '').strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"

def _cache_load(key: str, ttl: int) -> Optional[str]:
    p = _cache_path(key)
    if not p.exists(): return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        ts = int(obj.get("ts", 0))
        if ttl > 0 and (time.time() - ts) > ttl:
            return None
        return str(obj.get("content", "")).strip() or None
    except Exception:
        return None

def _cache_save(key: str, content: str) -> None:
    try:
        p = _cache_path(key)
        data = {"ts": int(time.time()), "content": content}
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.warning("Cache write failed: %s", e)

# ---------------- Fireworks / OpenAI ----------------
def _fireworks_complete(prompt: str, model: Optional[str] = None) -> str:
    if not FIREWORKS_API_KEY:
        raise RuntimeError("FIREWORKS_API_KEY is missing")
    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    headers = {"Authorization": f"Bearer {FIREWORKS_API_KEY}","Content-Type": "application/json"}
    payload = {
        "model": (model or FIREWORKS_MODEL),
        "messages": [{"role": "system", "content": SYSTEM_SUMMARY},{"role": "user", "content": prompt}],
        "temperature": 0.25, "max_tokens": 700, "stream": False,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content", "") or ""
    return _clean_text(text)

def _openai_complete(prompt: str) -> str:
    if not OPENAI_API_KEY: return ""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}","Content-Type": "application/json"}
    payload = {
        "model": OPENAI_MODEL,
        "messages": [{"role":"system","content": SYSTEM_SUMMARY},{"role":"user","content": prompt}],
        "temperature": 0.3, "max_tokens": 700, "stream": False,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        log.warning("OpenAI fallback non-200: %s %s", r.status_code, r.text[:200]); return ""
    obj = r.json()
    ch = (obj.get("choices") or [{}])[0]
    txt = (ch.get("message") or {}).get("content", "") or ""
    return _clean_text(txt)

# ---------------- ODS helpers ----------------
def ods_runtime_snapshot() -> dict:
    if SEARXNG_INSTANCE_URL:
        search_provider = "searxng"
    else:
        search_provider = "serper"
    reranker = "jina" if JINA_API_KEY else "infinity"
    prefix = (ODS_MODEL.split("/", 1)[0] if "/" in ODS_MODEL else ODS_MODEL).lower()
    if "openrouter" in prefix: llm_provider = "openrouter"
    elif "fireworks" in prefix or "fireworks_ai" in prefix: llm_provider = "fireworks"
    elif "openai" in prefix: llm_provider = "openai"
    elif "anthropic" in prefix: llm_provider = "anthropic"
    elif "google" in prefix: llm_provider = "google"
    else: llm_provider = prefix or "unknown"
    return {"search_provider": search_provider, "reranker": reranker, "llm_provider": llm_provider}

def _ods_deep_analysis(title: str, description: str, link: str, on_stage: Optional[Callable[[str], None]] = None) -> str:
    try:
        from opendeepsearch import OpenDeepSearchTool
    except Exception as e:
        log.warning("ODS import failed: %s", e)
        return ""

    snap = ods_runtime_snapshot()
    try:
        if on_stage: on_stage("init")
        if on_stage: on_stage("search_provider")
        if on_stage: on_stage("reranker")
        if on_stage: on_stage("llm_provider")
    except Exception:
        pass

    kwargs = {"model_name": (ODS_MODEL or "openrouter/google/gemini-2.0-flash-001"),
              "reranker": snap["reranker"]}
    if snap["search_provider"] == "searxng" and SEARXNG_INSTANCE_URL:
        kwargs.update({"search_provider": "searxng", "searxng_instance_url": SEARXNG_INSTANCE_URL})
        if SEARXNG_API_KEY: kwargs["searxng_api_key"] = SEARXNG_API_KEY

    tool = OpenDeepSearchTool(**kwargs)
    if getattr(tool, "is_initialized", True) is False:
        try: tool.setup()
        except Exception as e:
            log.warning("ODS setup failed: %s", e)
            return ""

    query = ODS_ANALYSIS_PROMPT.format(title=title, description=description, link=link)
    try:
        res = tool.forward(query)
        return _clean_text(str(res) if res is not None else "")
    except Exception as e:
        log.warning("ODS forward failed: %s", e)
        return ""

# ---------------- Service ----------------
class SummarizerService:
    def __init__(self, fireworks_model: Optional[str] = None):
        self.fireworks_model = (fireworks_model or FIREWORKS_MODEL).strip()

    # ✅ Chỉ tóm tắt (được /api/summarize gọi) — có cache
    def summarize_only(self, title: str, description: str, link: str) -> str:
        key = _cache_key("summary", title, description, link)
        hit = _cache_load(key, SUMMARY_CACHE_TTL)
        if hit:
            log.info("[CACHE] summary hit")
            return hit

        prompt = SUMMARY_PROMPT_TEMPLATE.format(title=title, description=description, link=link)
        txt = ""
        try:
            txt = _fireworks_complete(prompt, model=self.fireworks_model)
        except Exception as e:
            log.warning("Fireworks summary error: %s", e)
        if not txt:
            try:
                txt = _openai_complete(prompt)
            except Exception as e:
                log.warning("OpenAI summary error: %s", e)
        if not txt:
            raise RuntimeError("No summary available")

        card = _ensure_card(summary_block=txt, analysis_block="", link=link)
        _cache_save(key, card)
        return card

    # ✅ Chỉ phân tích sâu (được /api/deep_analyze_sse gọi) — có cache
    def deep_analyze_only(self, title: str, description: str, link: str) -> str:
        key = _cache_key("analysis", title, description, link)
        hit = _cache_load(key, DEEP_CACHE_TTL)
        if hit:
            log.info("[CACHE] analysis hit")
            return hit

        txt = _ods_deep_analysis(title, description, link)
        if not txt:
            raise RuntimeError("No deep analysis available")

        card = _ensure_card(summary_block="", analysis_block=txt, link=link)
        _cache_save(key, card)
        return card

    # (Giữ để tương thích chỗ cũ nếu nơi nào đó còn gọi)
    def summarize_and_analyze(self, title: str, description: str, link: str) -> str:
        # summary (cache riêng)
        s_key = _cache_key("summary", title, description, link)
        summary_block = _cache_load(s_key, SUMMARY_CACHE_TTL) or ""
        if not summary_block:
            prompt = SUMMARY_PROMPT_TEMPLATE.format(title=title, description=description, link=link)
            try:
                s = _fireworks_complete(prompt, model=self.fireworks_model)
                if s: summary_block = _ensure_card(s, "", link=link)
            except Exception as e:
                log.warning("Fireworks error (summary): %s", e)
            if not summary_block:
                try:
                    s = _openai_complete(prompt)
                    if s: summary_block = _ensure_card(s, "", link=link)
                except Exception as e:
                    log.warning("OpenAI error (summary): %s", e)
            if summary_block:
                _cache_save(s_key, summary_block)

        # deep (cache riêng)
        a_key = _cache_key("analysis", title, description, link)
        analysis_block = _cache_load(a_key, DEEP_CACHE_TTL) or ""
        if not analysis_block:
            try:
                a = _ods_deep_analysis(title, description, link)
                if a: analysis_block = _ensure_card("", a, link=link)
            except Exception as e:
                log.warning("ODS error (analysis): %s", e)
            if analysis_block:
                _cache_save(a_key, analysis_block)

        if not summary_block and not analysis_block:
            raise RuntimeError("No summarizer/analyzer available")
        # Ở đây 2 block đã là card; ghép gọn
        return "\n\n".join([b for b in [summary_block, analysis_block] if b.strip()])

# Kept for compatibility
class NewsAgent:
    def __init__(self, model: Optional[str] = None):
        self.model = (model or FIREWORKS_MODEL).strip()
        self.summarizer = SummarizerService(fireworks_model=self.model)
    def get_news(self, feeds: List[str], limit: int = 20) -> List[dict]:
        return []
    def summarize(self, title: str, description: str, link: str) -> str:
        return self.summarizer.summarize_and_analyze(title, description, link)
