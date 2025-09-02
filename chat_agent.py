# chat_agent.py — Streaming chat (Fireworks primary, OpenAI fallback). English-only.
from __future__ import annotations

import os
import json
import logging
import requests
from typing import Generator

log = logging.getLogger("ssa.chat")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "").strip()
FIREWORKS_MODEL = os.getenv(
    "FIREWORKS_MODEL",
    "accounts/SentientAGI/models/Dobby-Mini-Unhinged-Plus-Llama-3.1-8B",
).strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

SYSTEM_PROMPT = (
    "You are the assistant for a news dashboard. "
    "Answer in clear, professional English, avoid slang or profanity, keep responses concise. "
    "If real-time data is uncertain, say so."
)

def _stream_fireworks(user_msg: str) -> Generator[str, None, None]:
    if not FIREWORKS_API_KEY:
        raise RuntimeError("FIREWORKS_API_KEY is missing")

    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    headers = {"Authorization": f"Bearer {FIREWORKS_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": FIREWORKS_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.5,
        "max_tokens": 900,
        "stream": True,
    }
    with requests.post(url, headers=headers, json=payload, stream=True, timeout=90) as r:
        r.raise_for_status()
        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue
            if not raw.startswith("data:"):
                continue
            data = raw[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
                choice = (obj.get("choices") or [{}])[0]
                piece = (
                    (choice.get("delta") or {}).get("content")
                    or (choice.get("message") or {}).get("content")
                    or ""
                )
                if piece:
                    yield piece
            except Exception:
                # Ignore malformed frame quietly
                continue

def _stream_openai(user_msg: str) -> Generator[str, None, None]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.5,
        "max_tokens": 600,
        "stream": True,
    }
    with requests.post(url, headers=headers, json=payload, stream=True, timeout=90) as r:
        r.raise_for_status()
        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue
            if not raw.startswith("data:"):
                continue
            data = raw[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
                for ch in obj.get("choices", []):
                    piece = (ch.get("delta") or {}).get("content") or ""
                    if piece:
                        yield piece
            except Exception:
                continue

class ChatAgent:
    """Primary chat agent with streaming. Fireworks → OpenAI fallback."""

    def __init__(self, model: str | None = None):
        self.model = (model or FIREWORKS_MODEL).strip()
        if FIREWORKS_API_KEY:
            log.info("ChatAgent: Fireworks enabled (model=%s).", self.model)
        else:
            log.warning("ChatAgent: Fireworks key missing; will try OpenAI fallback.")
        if OPENAI_API_KEY:
            log.info("ChatAgent: OpenAI fallback enabled (model=%s).", OPENAI_MODEL)

    def stream_chat(self, user_msg: str) -> Generator[str, None, None]:
        user_msg = (user_msg or "").strip()
        if not user_msg:
            yield "Empty message."
            return

        any_chunk = False
        # Fireworks
        try:
            for piece in _stream_fireworks(user_msg):
                any_chunk = True
                yield piece
        except Exception as e:
            log.error("Fireworks streaming error: %s", e)

        # OpenAI fallback
        if not any_chunk and OPENAI_API_KEY:
            try:
                for piece in _stream_openai(user_msg):
                    any_chunk = True
                    yield piece
            except Exception as e:
                log.error("OpenAI streaming error: %s", e)

        if not any_chunk:
            yield "I couldn't generate a response. Please try again with a shorter prompt or another model."
