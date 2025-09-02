# news_agent.py
# English-only code. Provides:
# - SummarizerService: Fireworks-first summary; ODS deep analysis fallback.
# - Output formatting without markdown headers (#/##/###). Clean "card" layout.

from __future__ import annotations

import os
import re
import json
import logging
import requests
from typing import List, Optional

log = logging.getLogger("ssa.news")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# -----------------------------------------------------------------------------
# ENV (do NOT print secrets)
# -----------------------------------------------------------------------------
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "").strip()
FIREWORKS_MODEL = os.getenv(
    "FIREWORKS_MODEL",
    "accounts/sentientfoundation/models/dobby-unhinged-llama-3-3-70b-new"
).strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
SEARXNG_INSTANCE_URL = os.getenv("SEARXNG_INSTANCE_URL", "").strip()
SEARXNG_API_KEY = os.getenv("SEARXNG_API_KEY", "").strip()
JINA_API_KEY = os.getenv("JINA_API_KEY", "").strip()

# Optional override for ODS model via LiteLLM provider naming
ODS_MODEL = os.getenv("ODS_MODEL", os.getenv("LITELLM_MODEL_ID", "openrouter/google/gemini-2.0-flash-001")).strip()

# -----------------------------------------------------------------------------
# Formatting helpers (no #/##/###)
# -----------------------------------------------------------------------------
DIV = "────────────────────────────────"
BUL = "•"

def _clean_text(s: str) -> str:
    if not s:
        return ""
    # Remove accidental markdown headers
    s = re.sub(r"^\s*#{1,6}\s*", "", s, flags=re.MULTILINE)
    # Normalize double newlines
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def _wrap_section(title: str, body: str) -> str:
    body = _clean_text(body)
    if not body:
        return ""
    return f"**{title}**\n{body.strip()}"

def _ensure_card(summary_block: str, analysis_block: str, link: str = "") -> str:
    parts: List[str] = []
    if summary_block:
        parts.append(_wrap_section("Summary", summary_block))
        # Try to ensure a 1-line Impact at the end of summary if missing
        if "Impact:" not in summary_block and "Impact —" not in summary_block:
            parts.append("**Impact**\n(impact not provided)")
    if analysis_block:
        # Attempt to split common ODS headings and re-label into nice sections
        text = _clean_text(analysis_block)
        # Heuristic remap for nicer sections
        # Replace common headings with bold section titles
        text = re.sub(r"(?i)^summary\s*:?\s*$", "**Summary**", text, flags=re.MULTILINE)
        text = re.sub(r"(?i)^deep analysis\s*:?\s*$", "**Deep Analysis**", text, flags=re.MULTILINE)
        text = re.sub(r"(?i)^(why it matters|why-this-matters)\s*:?\s*$", "**Why it matters**", text, flags=re.MULTILINE)
        text = re.sub(r"(?i)^risks?\s*:?\s*$", "**Risks**", text, flags=re.MULTILINE)
        text = re.sub(r"(?i)^opportunit(y|ies)\s*:?\s*$", "**Opportunities**", text, flags=re.MULTILINE)
        text = re.sub(r"(?i)^(market (impact|view))\s*:?\s*$", "**Market view**", text, flags=re.MULTILINE)
        text = re.sub(r"(?i)^sources?\s*:?\s*$", "**Sources**", text, flags=re.MULTILINE)

        # Guarantee minimal structure if the model returned a blob
        if "**Deep Analysis**" not in text:
            text = f"**Deep Analysis**\n{text}"

        parts.append(text)

    card = f"{DIV}\n" + ("\n\n".join([p for p in parts if p.strip()])) + f"\n\n{DIV}"
    if link:
        card += f"\nLink: {link}"
    return card.strip()

# -----------------------------------------------------------------------------
# Base prompts
# -----------------------------------------------------------------------------
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
    "- Deep Analysis: 3–5 bullets (start with '• '), focus on causes, context, second-order effects.\n"
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

# -----------------------------------------------------------------------------
# Fireworks non-stream Chat Completion (summary)
# -----------------------------------------------------------------------------
def _fireworks_complete(prompt: str, model: Optional[str] = None) -> str:
    if not FIREWORKS_API_KEY:
        raise RuntimeError("FIREWORKS_API_KEY is missing")

    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": (model or FIREWORKS_MODEL),
        "messages": [
            {"role": "system", "content": SYSTEM_SUMMARY},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.25,
        "max_tokens": 700,
        "stream": False,
    }

    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content", "") or ""
    return _clean_text(text)

# -----------------------------------------------------------------------------
# OpenAI fallback (optional)
# -----------------------------------------------------------------------------
def _openai_complete(prompt: str) -> str:
    if not OPENAI_API_KEY:
        return ""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role":"system","content": SYSTEM_SUMMARY},
            {"role":"user",  "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 700,
        "stream": False,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        log.warning("OpenAI fallback non-200: %s %s", r.status_code, r.text[:200])
        return ""
    obj = r.json()
    ch = (obj.get("choices") or [{}])[0]
    txt = (ch.get("message") or {}).get("content", "") or ""
    return _clean_text(txt)

# -----------------------------------------------------------------------------
# ODS deep analysis (and can provide summary if Fireworks fails completely)
# -----------------------------------------------------------------------------
def _ods_deep_analysis(title: str, description: str, link: str) -> str:
    """
    Uses OpenDeepSearchTool to fetch/search & return a synthesized analysis.
    Requires SERPER_API_KEY or SEARXNG_* set; JINA_API_KEY recommended for rerank.
    """
    try:
        from opendeepsearch import OpenDeepSearchTool
    except Exception as e:
        log.warning("ODS import failed: %s", e)
        return ""

    # Pick reranker
    reranker = "jina" if JINA_API_KEY else "infinity"

    # Choose provider model for ODS internal LLM via LiteLLM naming
    model_name = ODS_MODEL or "openrouter/google/gemini-2.0-flash-001"

    kwargs = {"model_name": model_name, "reranker": reranker}
    if SEARXNG_INSTANCE_URL:
        kwargs.update({"search_provider": "searxng", "searxng_instance_url": SEARXNG_INSTANCE_URL})
        if SEARXNG_API_KEY:
            kwargs["searxng_api_key"] = SEARXNG_API_KEY

    tool = OpenDeepSearchTool(**kwargs)
    if getattr(tool, "is_initialized", True) is False:
        try:
            tool.setup()
        except Exception as e:
            log.warning("ODS setup failed: %s", e)
            return ""

    query = ODS_ANALYSIS_PROMPT.format(title=title, description=description, link=link)

    try:
        # You can expose depth knobs by adding kwargs like: pro_mode=True, top_k=8, max_docs=12
        res = tool.forward(query)
#         res = tool.forward(
#             query,
#             pro_mode=True,   # bật phân tích chuyên sâu
#             top_k=2,         # lấy 8 nguồn quan trọng nhất
#             max_docs=3     # đọc tối đa 12 tài liệu
# )

        return _clean_text(str(res) if res is not None else "")
    except Exception as e:
        log.warning("ODS forward failed: %s", e)
        return ""

# -----------------------------------------------------------------------------
# Public service
# -----------------------------------------------------------------------------
class SummarizerService:
    """
    Fireworks-first short summary; ODS deep analysis added or used as fallback.
    Output is a single card layout without markdown headers.
    """

    def __init__(self, fireworks_model: Optional[str] = None):
        self.fireworks_model = (fireworks_model or FIREWORKS_MODEL).strip()

    def summarize_and_analyze(self, title: str, description: str, link: str) -> str:
        # 1) Summary (Fireworks first)
        summary_prompt = SUMMARY_PROMPT_TEMPLATE.format(title=title, description=description, link=link)
        summary_block = ""
        try:
            txt = _fireworks_complete(summary_prompt, model=self.fireworks_model)
            if txt:
                # Ensure bullets and single Impact line
                summary_block = _clean_text(txt)
        except requests.HTTPError as e:
            log.warning("Fireworks HTTP error (summary): %s", e)
        except Exception as e:
            log.warning("Fireworks error (summary): %s", e)

        # 2) Deep analysis with ODS (if available)
        analysis_block = ""
        try:
            ods_text = _ods_deep_analysis(title, description, link)
            if ods_text:
                analysis_block = ods_text
        except Exception as e:
            log.warning("Deep analysis (ODS) error: %s", e)

        # 3) If no summary at all, try OpenAI fallback for the summary
        if not summary_block:
            oa = _openai_complete(summary_prompt)
            if oa:
                summary_block = oa

        # 4) Assemble into a single card
        if not summary_block and not analysis_block:
            # Nothing worked
            raise RuntimeError("No summarizer/analyzer available")

        return _ensure_card(summary_block, analysis_block, link=link)


# (Optional) Keep a minimal NewsAgent stub for compatibility (not used by SSA fetch)
class NewsAgent:
    def __init__(self, model: Optional[str] = None):
        self.model = (model or FIREWORKS_MODEL).strip()
        self.summarizer = SummarizerService(fireworks_model=self.model)

    # Placeholder to keep old imports happy if used
    def get_news(self, feeds: List[str], limit: int = 20) -> List[dict]:
        return []

    def summarize(self, title: str, description: str, link: str) -> str:
        return self.summarizer.summarize_and_analyze(title, description, link)
