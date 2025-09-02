# web_server.py — Backend for News (SSA fetch) + Summarize/Analyze (Fireworks-first, ODS fallback)
import os
import sys
import json
import logging
import asyncio
import threading
from queue import Queue, Empty
from datetime import datetime
from typing import List, Any

from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("ssa.web")

load_dotenv()
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "").strip()
FIREWORKS_MODEL   = os.getenv("FIREWORKS_MODEL", "accounts/SentientAGI/models/Dobby-Mini-Unhinged-Plus-Llama-3.1-8B").strip()
NEWS_API_KEY      = os.getenv("NEWS_API_KEY", "").strip()

ROOT = os.path.abspath(os.path.dirname(__file__))
SRC_PATH = os.path.join(ROOT, "src")
if os.path.isdir(SRC_PATH) and SRC_PATH not in sys.path:
    sys.path.append(SRC_PATH)

# ---- SSA News (optional) ----
SSA_News = None
try:
    from src.agent.agent_tools.news import News as SSA_News  # type: ignore
    log.info("SSA News available.")
except Exception as e:
    log.warning("SSA News not found: %s", e)

# ---- Our summarizer service (in news_agent.py) ----
SummarizerService = None
try:
    from news_agent import SummarizerService  # type: ignore
    log.info("SummarizerService ready.")
except Exception as e:
    log.error("Failed to import SummarizerService: %s", e)

# Optional ODS probe (for status only)
ODS_AVAILABLE = False
try:
    import opendeepsearch  # type: ignore
    ODS_AVAILABLE = True
except Exception:
    ODS_AVAILABLE = False

app = Flask(__name__, static_url_path="", static_folder=".")
CORS(app)

# ---- Init SSA news agent if present ----
news_agent = None
news_mode = "none"
if SSA_News is not None and FIREWORKS_API_KEY:
    try:
        secrets = {
            "NEWS_API_KEY": NEWS_API_KEY,
            "FIREWORKS_API_KEY": FIREWORKS_API_KEY,
        }
        news_agent = SSA_News(secrets, None)
        news_mode = "ssa"
        log.info("News agent initialized (SSA).")
    except Exception as e:
        log.error("Init SSA News failed: %s", e)

# Summarizer
summarizer = None
if SummarizerService is not None:
    try:
        summarizer = SummarizerService(fireworks_model=FIREWORKS_MODEL)
    except Exception as e:
        log.error("Summarizer init failed: %s", e)

def _serialize_articles(articles: List[dict]) -> List[dict]:
    if not articles:
        return []
    uniq, out = set(), []
    for a in articles:
        if not isinstance(a, dict):
            continue
        aid = a.get("id") or a.get("link") or a.get("title")
        if not aid or aid in uniq:
            continue
        uniq.add(aid)
        out.append({
            "id": str(aid),
            "title": str(a.get("title", "Untitled")).strip(),
            "summary": str(a.get("summary", "") or a.get("description", "")).strip(),
            "category": str(a.get("category", "general")).strip(),
            "source": str(a.get("source", "Unknown")).strip(),
            "link": str(a.get("link", "")).strip(),
            "published": str(a.get("published", datetime.utcnow().isoformat()+"Z")).strip(),
            "priority": str(a.get("priority", "normal")).strip(),
        })
    return out

def _sse_json(data: Any) -> str:
    try:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    except Exception as e:
        log.error("SSE JSON error: %s", e)
        return "data: {\"type\":\"error\",\"name\":\"SERIALIZATION\"}\n\n"

@app.route("/")
def root():
    return send_from_directory(".", "news_dashboard.html")

# ---------- News ----------
@app.route("/api/news")
def api_news():
    if not news_agent:
        return jsonify({"status":"error","message":"News service unavailable"}), 503
    category = request.args.get("category","").strip()
    limit = min(int(request.args.get("limit", 20)), 100)
    try:
        if category:
            arts = news_agent.fetch_rss_news(category, max_articles=limit)  # type: ignore
        else:
            arts = news_agent.get_latest_news(max_total=limit)  # type: ignore
        return jsonify({"status":"success","source":"ssa","articles": _serialize_articles(arts)})
    except Exception as e:
        log.error("/api/news error: %s", e, exc_info=True)
        return jsonify({"status":"error","message":str(e)}), 500

# ---------- Summarize + Analyze ----------
@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    if summarizer is None:
        return jsonify({"status":"error","message":"Analyzer unavailable"}), 503

    try:
        data = request.get_json(force=True) or {}
    except Exception as e:
        return jsonify({"status":"error","message":f"Invalid JSON: {e}"}), 400

    title = str(data.get("title","")).strip()
    desc  = str(data.get("description","") or data.get("summary","")).strip()
    link  = str(data.get("url","") or data.get("link","")).strip()

    if not title and not desc and not link:
        return jsonify({"status":"error","message":"title/description/link required"}), 400

    try:
        md = summarizer.summarize_and_analyze(title, desc, link)
        return jsonify({"status":"success","summary": md})
    except Exception as e:
        # Important: DO NOT leak API keys; just message
        log.error("Summarize failed: %s", e, exc_info=True)
        return jsonify({"status":"error","message": f"Summarization failed: {e}"}), 500

# ---------- Status ----------
@app.route("/api/status")
def api_status():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat()+"Z",
        "version": "2.1",
        "components": {
            "fireworks_model": FIREWORKS_MODEL,
            "model_configured": bool(FIREWORKS_API_KEY),
            "news_agent": {"available": bool(news_agent), "mode": news_mode},
            "summarization": {
                # available if we have SummarizerService and (Fireworks or ODS)
                "available": bool(summarizer) and (bool(FIREWORKS_API_KEY) or ODS_AVAILABLE),
                "service": "Fireworks-first + ODS fallback",
                "ods_available": bool(ODS_AVAILABLE)
            }
        }
    })

# (Chat endpoints removed from UI usage; you can keep them if needed)
@app.errorhandler(404)
def nf(_):
    return jsonify({"status":"error","message":"Endpoint not found"}), 404

@app.errorhandler(500)
def ie(_):
    return jsonify({"status":"error","message":"Internal server error"}), 500

if __name__ == "__main__":
    log.info("Starting server at http://localhost:3000 | model=%s", FIREWORKS_MODEL)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","3000")), debug=False, threaded=True)
