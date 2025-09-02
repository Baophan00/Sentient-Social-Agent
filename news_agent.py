# news_agent.py
# English-only code. Provides:
# - SummarizerService: Fireworks-first summary; ODS deep analysis fallback.
# - (Optional) NewsAgent.get_news(...) kept minimal for compatibility.

from __future__ import annotations

import os
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

SYSTEM_SUMMARY = (
    "You are a concise news summarizer. Output clear English with short bullets and a one-line impact."
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
        "temperature": 0.3,
        "max_tokens": 700,
        "stream": False,
    }

    r = requests.post(url, headers=headers, json=payload, timeout=60)
    # If Fireworks returns any non-200 (incl. 404), this will raise and let us fallback.
    r.raise_for_status()
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content", "") or ""
    return text.strip()

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
        "temperature": 0.4,
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
    return txt.strip()

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

    # Prefer Serper; otherwise use SearXNG if provided
    kwargs = {"model_name": model_name, "reranker": reranker}
    if SEARXNG_INSTANCE_URL:
        kwargs.update({"search_provider": "searxng", "searxng_instance_url": SEARXNG_INSTANCE_URL})
        if SEARXNG_API_KEY:
            kwargs["searxng_api_key"] = SEARXNG_API_KEY

    tool = OpenDeepSearchTool(**kwargs)
    # Some builds expose is_initialized flag
    if getattr(tool, "is_initialized", True) is False:
        try:
            tool.setup()
        except Exception as e:
            log.warning("ODS setup failed: %s", e)
            return ""

    query = (
        "Deeply analyze this news item. If a link is provided, use it and corroborate with search; "
        "otherwise rely on known context. Output:\n"
        "• 3–5 key takeaways\n"
        "• 1 risk, 1 opportunity\n"
        "• 1-sentence market impact\n\n"
        f"Title: {title}\n"
        f"Description: {description}\n"
        f"Link: {link}\n"
    )

    try:
        res = tool.forward(query)
        return (str(res) if res is not None else "").strip()
    except Exception as e:
        log.warning("ODS forward failed: %s", e)
        return ""

# -----------------------------------------------------------------------------
# Public service
# -----------------------------------------------------------------------------
class SummarizerService:
    """
    Fireworks-first short summary; ODS deep analysis added or used as fallback.
    """

    def __init__(self, fireworks_model: Optional[str] = None):
        self.fireworks_model = (fireworks_model or FIREWORKS_MODEL).strip()

    def summarize_and_analyze(self, title: str, description: str, link: str) -> str:
        # 1) Summary with Fireworks
        summary_prompt = (
            "Summarize in English using exactly 3 bullets, then a one-line Impact.\n\n"
            f"Title: {title}\n"
            f"Description: {description}\n"
            f"Link: {link}\n"
        )
        summary_md = ""
        try:
            txt = _fireworks_complete(summary_prompt, model=self.fireworks_model)
            if txt:
                summary_md = "### Summary\n" + txt.strip()
        except requests.HTTPError as e:
            # This is the case you hit: 404 must not kill the flow.
            log.warning("Fireworks HTTP error (summary): %s", e)
        except Exception as e:
            log.warning("Fireworks error (summary): %s", e)

        # 2) Deep analysis with ODS (if available)
        deep_md = ""
        try:
            ods_text = _ods_deep_analysis(title, description, link)
            if ods_text:
                deep_md = "### Deep Analysis\n" + ods_text
        except Exception as e:
            log.warning("Deep analysis (ODS) error: %s", e)

        # 3) If no summary at all, try OpenAI fallback for the summary
        if not summary_md:
            oa = _openai_complete(summary_prompt)
            if oa:
                summary_md = "### Summary\n" + oa

        # 4) Final assembly
        if not summary_md and not deep_md:
            # Nothing worked
            raise RuntimeError("No summarizer/analyzer available")

        parts = []
        if summary_md:
            parts.append(summary_md)
        if deep_md:
            parts.append(deep_md)

        return "\n\n".join(parts)


# (Optional) Keep a minimal NewsAgent stub for compatibility (not used by SSA fetch)
class NewsAgent:
    def __init__(self, model: Optional[str] = None):
        self.model = (model or FIREWORKS_MODEL).strip()
        self.summarizer = SummarizerService(fireworks_model=self.model)

    # Placeholder to keep old imports happy if used
    def get_news(self, feeds: List[str], limit: int = 20) -> List[dict]:
        # You are using SSA for fetching; this is not needed. Kept as stub.
        return []

    def summarize(self, title: str, description: str, link: str) -> str:
        return self.summarizer.summarize_and_analyze(title, description, link)
