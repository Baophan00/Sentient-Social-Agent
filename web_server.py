# web_server.py
import os, sys, json, logging
from typing import List, Any
from datetime import datetime, timezone
from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("ssa.web")

load_dotenv()
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "").strip()
FIREWORKS_MODEL   = os.getenv("FIREWORKS_MODEL", "accounts/sentientfoundation/models/dobby-unhinged-llama-3-3-70b-new").strip()
NEWS_API_KEY      = os.getenv("NEWS_API_KEY", "").strip()

# ODS / search stack env
SERPER_API_KEY        = os.getenv("SERPER_API_KEY", "").strip()
SEARXNG_INSTANCE_URL  = os.getenv("SEARXNG_INSTANCE_URL", "").strip()
SEARXNG_API_KEY       = os.getenv("SEARXNG_API_KEY", "").strip()
JINA_API_KEY          = os.getenv("JINA_API_KEY", "").strip()
ODS_MODEL             = os.getenv("ODS_MODEL", os.getenv("LITELLM_MODEL_ID", "openrouter/google/gemini-2.0-flash-001")).strip()

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

# ---- Summarizer service (ours) ----
SummarizerService = None
try:
    from news_agent import SummarizerService  # type: ignore
    log.info("SummarizerService ready.")
except Exception as e:
    log.error("Failed to import SummarizerService: %s", e)

# ODS probe
ODS_AVAILABLE = False
try:
    import opendeepsearch  # type: ignore
    ODS_AVAILABLE = True
except Exception:
    ODS_AVAILABLE = False

app = Flask(__name__, static_url_path="", static_folder=".")
CORS(app)

# Init news agent
news_agent = None
news_mode = "none"
if SSA_News is not None and FIREWORKS_API_KEY:
    try:
        secrets = {"NEWS_API_KEY": NEWS_API_KEY, "FIREWORKS_API_KEY": FIREWORKS_API_KEY}
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

# ---------------- Utils ----------------
def _now_iso():
    return datetime.now(timezone.utc).isoformat()

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
            "published": str(a.get("published", _now_iso())).strip(),
            "priority": str(a.get("priority", "normal")).strip(),
        })
    return out

def _sse(payload: Any) -> str:
    try:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    except Exception as e:
        log.error("SSE JSON error: %s", e)
        return "data: {\"type\":\"error\",\"name\":\"SERIALIZATION\"}\n\n"

# --------------- Routes ----------------
@app.route("/")
def root():
    return send_from_directory(".", "news_dashboard.html")

# ---------- News ----------
def _normalize_category(cat: str) -> str:
    m = {
        "": "", "all": "",
        "technology": "tech", "tech": "tech",
        "crypto": "crypto",
        "business": "finance", "finance": "finance",
        "ai": "ai",
        "general": "general"
    }
    return m.get((cat or "").lower(), (cat or "").lower())

@app.route("/api/news")
def api_news():
    if not news_agent:
        return jsonify({"status":"error","message":"News service unavailable"}), 503
    raw_cat = request.args.get("category","").strip()
    category = _normalize_category(raw_cat)
    limit = min(int(request.args.get("limit", 50)), 100)
    try:
        if category:
            arts = news_agent.fetch_rss_news(category, max_articles=limit)  # type: ignore
        else:
            arts = news_agent.get_latest_news(max_total=limit)  # type: ignore
        return jsonify({"status":"success","source":"ssa","articles": _serialize_articles(arts)})
    except Exception as e:
        log.error("/api/news error: %s", e, exc_info=True)
        return jsonify({"status":"error","message":str(e)}), 500

# ---------- Summarize (Fireworks only) ----------
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
        # ✅ chỉ tóm tắt (Fireworks/OpenAI)
        md = summarizer.summarize_only(title, desc, link)
        return jsonify({"status":"success","summary": md})
    except Exception as e:
        log.error("Summarize failed: %s", e, exc_info=True)
        return jsonify({"status":"error","message": f"Summarization failed: {e}"}), 500

# ---------- Deep Analysis (SSE, ODS on-demand) ----------
@app.route("/api/deep_analyze_sse")
def api_deep_analyze_sse():
    title = str(request.args.get("title","")).strip()
    desc  = str(request.args.get("description","")).strip()
    link  = str(request.args.get("url","")).strip()

    def stream():
        # Stage 1: init
        yield _sse({"type":"stage","stage":"init","detail":"Preparing…"})

        # ODS availability check
        if not ODS_AVAILABLE:
            yield _sse({"type":"error","message":"ODS not installed (torch missing)."})
            return

        # Stage 2: searching…
        if SEARXNG_INSTANCE_URL:
            yield _sse({"type":"stage","stage":"search_provider","detail":"Searching…"})
        else:
            # serper hoặc default-serp
            _prov = "Searching…"  # nhãn ngắn, frontend sẽ tự hiển thị “Searching…”
            yield _sse({"type":"stage","stage":"search_provider","detail":_prov})

        # Stage 3: reranking…
        _rer = "Reranking…"
        yield _sse({"type":"stage","stage":"reranker","detail":_rer})

        # Stage 4: synthesizing (LLM)
        _llm = "Synthesizing analysis…"
        yield _sse({"type":"stage","stage":"llm_provider","detail":_llm})

        # Run deep analysis
        try:
            if summarizer is None:
                raise RuntimeError("Analyzer unavailable")
            result = summarizer.deep_analyze_only(title, desc, link)
            yield _sse({"type":"done","analysis": result})
        except Exception as e:
            yield _sse({"type":"error","message": f"Deep analysis failed: {e}"})

    return Response(stream(), mimetype="text/event-stream", headers={
        "Cache-Control":"no-cache",
        "X-Accel-Buffering":"no"
    })

# ---------- Status ----------
@app.route("/api/status")
def api_status():
    return jsonify({
        "status": "ok",
        "timestamp": _now_iso(),
        "version": "2.3",
        "components": {
            "fireworks_model": FIREWORKS_MODEL,
            "model_configured": bool(FIREWORKS_API_KEY),
            "news_agent": {"available": bool(news_agent), "mode": news_mode},
            "summarization": {
                "available": bool(summarizer) and (bool(FIREWORKS_API_KEY) or ODS_AVAILABLE),
                "service": "Fireworks summary + ODS on-demand (SSE)",
                "ods_available": bool(ODS_AVAILABLE)
            }
        }
    })

@app.errorhandler(404)
def nf(_): return jsonify({"status":"error","message":"Endpoint not found"}), 404

@app.errorhandler(500)
def ie(_): return jsonify({"status":"error","message":"Internal server error"}), 500

if __name__ == "__main__":
    log.info("Starting server at http://localhost:3000 | model=%s", FIREWORKS_MODEL)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","3000")), debug=False, threaded=True)

