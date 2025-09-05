# web_server.py
import os, sys, json, logging, hashlib
from typing import List, Any
from datetime import datetime, timezone
from pathlib import Path
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

# ---- SSA News tool ----
SSA_News = None
try:
    from src.agent.agent_tools.news import News as SSA_News  # type: ignore
    log.info("SSA News available.")
except Exception as e:
    log.warning("SSA News not found: %s", e)

# ---- Summarizer service ----
SummarizerService = None
try:
    from news_agent import SummarizerService  # type: ignore
    log.info("SummarizerService ready.")
except Exception as e:
    log.error("Failed to import SummarizerService: %s", e)

# ODS availability
ODS_AVAILABLE = False
try:
    import opendeepsearch  # type: ignore
    ODS_AVAILABLE = True
except Exception:
    ODS_AVAILABLE = False

# ---- Cache dirs ----
CACHE_DIR = Path("data/cache_analysis")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _hash_key(*parts: str) -> str:
    raw = "||".join([p.strip() for p in parts if p])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

app = Flask(__name__, static_url_path="", static_folder=".")
CORS(app)

# Init news agent
news_agent = None
news_mode = "none"
if SSA_News is not None and FIREWORKS_API_KEY:
    try:
        secrets = {"NEWS_API_KEY": NEWS_API_KEY, "FIREWORKS_API_KEY": FIREWORKS_API_KEY}
        interval = int(os.getenv("NEWS_MIN_INTERVAL_SEC", "3600"))
        news_agent = SSA_News(secrets, None)
        news_agent.update_interval = interval
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
@app.route("/api/news")
def api_news():
    if not news_agent:
        return jsonify({"status":"error","message":"News service unavailable"}), 503
    raw_cat = request.args.get("category","").strip().lower()
    limit = min(max(int(request.args.get("limit", 50)), 1), 100)
    try:
        if hasattr(news_agent, "get_latest_news"):
            arts = news_agent.get_latest_news(max_total=limit, category=raw_cat)  # type: ignore
        else:
            arts = news_agent.fetch_rss_news(raw_cat, max_articles=limit)  # type: ignore
        return jsonify({"status":"success","source":"ssa","articles": _serialize_articles(arts)})
    except Exception as e:
        log.error("/api/news error: %s", e, exc_info=True)
        return jsonify({"status":"error","message":str(e)}), 500

# ---------- Summarize (with cache) ----------
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

    key = _hash_key("summarize", title, desc, link)
    cache_path = CACHE_DIR / f"{key}.json"

    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        return jsonify({"status":"success","summary": cached.get("summary", "")})

    try:
        md = summarizer.summarize_only(title, desc, link)
        cache_path.write_text(json.dumps({"summary": md}, ensure_ascii=False))
        return jsonify({"status":"success","summary": md})
    except Exception as e:
        log.error("Summarize failed: %s", e, exc_info=True)
        return jsonify({"status":"error","message": f"Summarization failed: {e}"}), 500

# ---------- Deep Analysis (with cache, SSE) ----------
# Thay thế hoàn toàn route /api/deep_analyze_sse
@app.route("/api/deep_analyze_sse")
def api_deep_analyze_sse():
    title = str(request.args.get("title","")).strip()
    desc  = str(request.args.get("description","")).strip()
    link  = str(request.args.get("url","")).strip()

    key = _hash_key("deep", title, desc, link)
    cache_path = CACHE_DIR / f"{key}.json"

    def stream():
        # Check cache first
        if cache_path.exists():
            cached = json.loads(cache_path.read_text())
            yield _sse({"type":"done", "analysis": cached.get("analysis", "")})
            return

        yield _sse({"type":"stage","stage":"init","detail":"Preparing analysis…"})
        
        try:
            if summarizer is None:
                raise RuntimeError("Analyzer unavailable")
            
            # Thử deep analysis trước
            if ODS_AVAILABLE:
                yield _sse({"type":"stage","stage":"deep","detail":"Running deep analysis with ODS…"})
                try:
                    result = summarizer.deep_analyze_only(title, desc, link)
                    cache_path.write_text(json.dumps({"analysis": result}, ensure_ascii=False))
                    yield _sse({"type":"done","analysis": result})
                    return
                except Exception as e:
                    log.warning("Deep analysis failed, falling back to summary: %s", e)
                    yield _sse({"type":"stage","stage":"fallback","detail":"Deep analysis failed, using summarization…"})
            else:
                yield _sse({"type":"stage","stage":"fallback","detail":"ODS unavailable, using summarization…"})
            
            # Fallback to basic summarization
            result = summarizer.summarize_only(title, desc, link)
            
            # Add fallback note
            fallback_note = "**Note:** Deep analysis unavailable (using summarization instead).\n\n"
            result = fallback_note + result
            
            cache_path.write_text(json.dumps({"analysis": result}, ensure_ascii=False))
            yield _sse({"type":"done","analysis": result})
            
        except Exception as e:
            log.error("All analysis methods failed: %s", e, exc_info=True)
            yield _sse({"type":"error","message": f"Analysis failed: {e}"})

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
        "version": "2.5-cache",
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
