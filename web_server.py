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

# Fix PYTHONPATH
paths_to_add = [
    ROOT,
    SRC_PATH,
    os.path.join(ROOT, "src", "agent"),
    os.path.join(ROOT, "src", "agent", "agent_tools")
]
for path in paths_to_add:
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

# ---- SSA News tool ----
SSA_News = None
try:
    try:
        from src.agent.agent_tools.news import News as SSA_News
    except ImportError:
        from agent.agent_tools.news import News as SSA_News
    except ImportError:
        from agent_tools.news import News as SSA_News
    log.info("SSA News available.")
except Exception as e:
    log.warning("SSA News not found: %s", e)

# ---- Summarizer service ----
SummarizerService = None
try:
    try:
        from news_agent import SummarizerService
    except ImportError:
        from src.news_agent import SummarizerService
    log.info("SummarizerService ready.")
except Exception as e:
    log.error("Failed to import SummarizerService: %s", e)

# ---- Cache dirs ----
CACHE_DIR = Path("data/cache_analysis")
try:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    test_file = CACHE_DIR / "test.txt"
    test_file.write_text("test")
    test_file.unlink()
    log.info(f"Cache directory ready: {CACHE_DIR}")
except Exception as e:
    log.error(f"Cannot create cache directory: {e}")
    import tempfile
    CACHE_DIR = Path(tempfile.gettempdir()) / "ssa_cache"
    CACHE_DIR.mkdir(exist_ok=True)
    log.info(f"Using fallback cache: {CACHE_DIR}")

def _hash_key(*parts: str) -> str:
    raw = "||".join([p.strip() for p in parts if p])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

def _check_torch_status():
    try:
        import torch
        return f"installed_v{torch.__version__}"
    except ImportError:
        return "not_installed"
    except Exception as e:
        return f"error: {e}"

def _check_ods_availability():
    """Check ODS presence WITHOUT requiring torch."""
    try:
        import opendeepsearch  # noqa
        from opendeepsearch import OpenDeepSearchTool  # noqa
        return True
    except Exception as e:
        log.debug(f"ODS not available: {e}")
        return False

app = Flask(__name__, static_url_path="", static_folder=".")
CORS(app)

# Init news agent (optional)
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
            arts = news_agent.get_latest_news(max_total=limit, category=raw_cat)
        else:
            arts = news_agent.fetch_rss_news(raw_cat, max_articles=limit)
        return jsonify({"status":"success","source":"ssa","articles": _serialize_articles(arts)})
    except Exception as e:
        log.error("/api/news error: %s", e, exc_info=True)
        return jsonify({"status":"error","message":str(e)}), 500

# ---------- Summarize ----------
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

# ---------- Deep Analysis (SSE) ----------
@app.route("/api/deep_analyze_sse")
def api_deep_analyze_sse():
    title = str(request.args.get("title","")).strip()
    desc  = str(request.args.get("description","")).strip()
    link  = str(request.args.get("url","")).strip()

    key = _hash_key("deep", title, desc, link)
    cache_path = CACHE_DIR / f"{key}.json"

    def stream():
        if cache_path.exists():
            cached = json.loads(cache_path.read_text())
            yield _sse({"type":"done", "analysis": cached.get("analysis", "")})
            return

        yield _sse({"type":"stage","stage":"init","detail":"Preparing analysis…"})
        if summarizer is None:
            yield _sse({"type":"error","message":"Analyzer unavailable"})
            return

        ods_available = _check_ods_availability()

        try:
            if ods_available:
                yield _sse({"type":"stage","stage":"search_provider","detail":"Running deep analysis with ODS…"})
                yield _sse({"type":"stage","stage":"reranker","detail":"Searching and reranking…"})
                yield _sse({"type":"stage","stage":"llm_provider","detail":"Synthesizing analysis…"})
                try:
                    result = summarizer.deep_analyze_only(title, desc, link)
                    cache_path.write_text(json.dumps({"analysis": result}, ensure_ascii=False))
                    yield _sse({"type":"done","analysis": result})
                    return
                except Exception as e:
                    log.warning("Deep analysis failed, falling back to summary: %s", e)
                    yield _sse({"type":"stage","stage":"fallback","detail":"Deep analysis failed, using enhanced summarization…"})
            else:
                yield _sse({"type":"stage","stage":"fallback","detail":"ODS unavailable, using enhanced summarization…"})

            result = summarizer.summarize_only(title, desc, link)
            fallback_note = "**Note:** Deep analysis unavailable, using enhanced summarization.\n\n"
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
    torch_status = _check_torch_status()
    ods_available = _check_ods_availability()
    return jsonify({
        "status": "ok",
        "timestamp": _now_iso(),
        "version": "2.5-cache-fallback",
        "components": {
            "fireworks_model": FIREWORKS_MODEL,
            "model_configured": bool(FIREWORKS_API_KEY),
            "news_agent": {"available": bool(news_agent), "mode": news_mode},
            "summarization": {
                "available": bool(summarizer) and (bool(FIREWORKS_API_KEY) or ods_available),
                "service": "Fireworks summary + ODS on-demand (SSE) with fallback",
                "ods_available": bool(ods_available),
                "torch_status": torch_status
            },
            "ods": {
                "available": bool(ods_available),
                "model": ODS_MODEL
            }
        }
    })

# ---------- Debug ----------
@app.route("/api/debug")
def api_debug():
    return jsonify({
        "ROOT": ROOT,
        "SRC_PATH": SRC_PATH,
        "sys_path": sys.path[:5],
        "cache_dir": str(CACHE_DIR),
        "cache_exists": CACHE_DIR.exists(),
        "env_vars": {
            "PORT": os.getenv("PORT"),
            "PYTHONPATH": os.getenv("PYTHONPATH"),
            "FIREWORKS_KEY_SET": bool(FIREWORKS_API_KEY)
        }
    })

@app.route("/api/debug/torch")
def debug_torch():
    result = {}
    try:
        import torch
        result["torch"] = {
            "available": True,
            "version": torch.__version__,
            "cuda_available": torch.cuda.is_available() if hasattr(torch, 'cuda') else False
        }
    except Exception as e:
        result["torch"] = {"available": False, "error": str(e)}
    try:
        import opendeepsearch
        result["opendeepsearch"] = {"available": True, "version": getattr(opendeepsearch, "__version__", "unknown")}
    except Exception as e:
        result["opendeepsearch"] = {"available": False, "error": str(e)}
    try:
        from opendeepsearch import OpenDeepSearchTool
        _ = OpenDeepSearchTool(model_name="openrouter/google/gemini-2.0-flash-001")
        result["ods_tool"] = {"available": True}
    except Exception as e:
        result["ods_tool"] = {"available": False, "error": str(e)}
    return jsonify(result)

@app.errorhandler(404)
def nf(_): return jsonify({"status":"error","message":"Endpoint not found"}), 404

@app.errorhandler(500)
def ie(_): return jsonify({"status":"error","message":"Internal server error"}), 500

if __name__ == "__main__":
    log.info("Starting server at http://localhost:3000 | model=%s", FIREWORKS_MODEL)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","3000")), debug=False, threaded=True)
