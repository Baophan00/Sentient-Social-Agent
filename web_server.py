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
OPENROUTER_API_KEY    = os.getenv("OPENROUTER_API_KEY", "").strip()
ODS_MODEL             = os.getenv("ODS_MODEL", os.getenv("LITELLM_MODEL_ID", "openrouter/google/gemini-2.0-flash-001")).strip()

ROOT = os.path.abspath(os.path.dirname(__file__))
SRC_PATH = os.path.join(ROOT, "src")

# Extend sys.path for both local & Render
paths_to_add = [
    ROOT,
    SRC_PATH,
    os.path.join(ROOT, "src", "agent"),
    os.path.join(ROOT, "src", "agent", "agent_tools"),
]
for path in paths_to_add:
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

# ---- SSA News tool (optional) ----
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
    (CACHE_DIR / ".__w").write_text("ok")
    (CACHE_DIR / ".__w").unlink(missing_ok=True)
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

# ===== Diagnostics =====
def _check_ods_modules():
    info = {"import": False, "tool": False, "version": "unknown", "error": ""}
    try:
        import opendeepsearch as ods
        info["import"] = True
        info["version"] = getattr(ods, "__version__", "unknown")
        try:
            from opendeepsearch import OpenDeepSearchTool  # noqa
            info["tool"] = True
        except Exception as e:
            info["error"] = f"tool import: {e}"
    except Exception as e:
        info["error"] = f"module import: {e}"
    return info

def _ods_env_ready():
    # Đồng bộ với news_agent._ensure_ods_env_or_raise
    llm_provider = ("openrouter" if "openrouter" in (ODS_MODEL.split("/",1)[0] if "/" in ODS_MODEL else ODS_MODEL).lower() else "other")
    missing = []
    if llm_provider == "openrouter" and not OPENROUTER_API_KEY:
        missing.append("OPENROUTER_API_KEY")
    if SEARXNG_INSTANCE_URL:
        # searxng: OK nếu có URL (API key optional)
        pass
    else:
        # serper default
        if not SERPER_API_KEY:
            missing.append("SERPER_API_KEY")
    return (len(missing) == 0, missing)

app = Flask(__name__, static_url_path="", static_folder=".")
CORS(app)

# Init news agent
news_agent = None
news_mode = "none"
if SSA_News is not None and FIREWORKS_API_KEY:
    try:
        secrets = {"NEWS_API_KEY": NEWS_API_KEY, "FIREWORKS_API_KEY": FIREWORKS_API_KEY}
        news_agent = SSA_News(secrets, None)
        news_agent.update_interval = int(os.getenv("NEWS_MIN_INTERVAL_SEC", "3600"))
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

# ===== Helpers =====
def _now_iso(): return datetime.now(timezone.utc).isoformat()

def _serialize_articles(articles: List[dict]) -> List[dict]:
    if not articles: return []
    uniq, out = set(), []
    for a in articles:
        if not isinstance(a, dict): continue
        aid = a.get("id") or a.get("link") or a.get("title")
        if not aid or aid in uniq: continue
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

# ===== Routes =====
@app.route("/")
def root():
    return send_from_directory(".", "news_dashboard.html")

# News API
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

# Summarize (cache)
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

# Deep Analysis (SSE) — **KHÔNG FALLBACK**
@app.route("/api/deep_analyze_sse")
def api_deep_analyze_sse():
    title = str(request.args.get("title","")).strip()
    desc  = str(request.args.get("description","")).strip()
    link  = str(request.args.get("url","")).strip()

    key = _hash_key("deep", title, desc, link)
    cache_path = CACHE_DIR / f"{key}.json"

    def stream():
        # Cache trước
        if cache_path.exists():
            cached = json.loads(cache_path.read_text())
            yield _sse({"type":"done", "analysis": cached.get("analysis", "")})
            return

        # Diagnostics ODS
        modules = _check_ods_modules()
        ready, missing = _ods_env_ready()

        yield _sse({"type":"stage","stage":"init","detail":"Preparing deep analysis…"})
        yield _sse({"type":"stage","stage":"diag","detail":f"ods_import={modules['import']} tool={modules['tool']} v={modules['version']} ready={ready} missing={','.join(missing)}"})

        if summarizer is None:
            yield _sse({"type":"error","message":"Analyzer unavailable"})
            return

        if not modules["import"] or not modules["tool"] or not ready:
            yield _sse({"type":"error","message": f"ODS not ready: missing={','.join(missing)} err={modules['error']}"})
            return

        # Stages
        yield _sse({"type":"stage","stage":"search_provider","detail":"Searching…"})
        yield _sse({"type":"stage","stage":"reranker","detail":"Reranking…"})
        yield _sse({"type":"stage","stage":"llm_provider","detail":"Synthesizing…"})

        try:
            result = summarizer.deep_analyze_only(title, desc, link)
            cache_path.write_text(json.dumps({"analysis": result}, ensure_ascii=False))
            yield _sse({"type":"done","analysis": result})
        except Exception as e:
            yield _sse({"type":"error","message": f"Deep analysis failed: {e}"})

    return Response(stream(), mimetype="text/event-stream", headers={
        "Cache-Control":"no-cache",
        "X-Accel-Buffering":"no"
    })

# Status
@app.route("/api/status")
def api_status():
    modules = _check_ods_modules()
    ready, missing = _ods_env_ready()
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "no-fallback-deep-v1",
        "components": {
            "fireworks_model": FIREWORKS_MODEL,
            "news_agent": {"available": bool(SSA_News is not None)},
            "summarizer_loaded": bool(SummarizerService is not None),
            "ods": {
                "import": modules["import"],
                "tool": modules["tool"],
                "version": modules["version"],
                "ready": ready,
                "missing_env": missing,
                "model": ODS_MODEL,
                "searxng": bool(SEARXNG_INSTANCE_URL),
            }
        }
    })

# Clear cache (tiện test trên Render)
@app.route("/api/clear_cache", methods=["POST"])
def api_clear_cache():
    n = 0
    for p in CACHE_DIR.glob("*.json"):
        try:
            p.unlink(); n += 1
        except: pass
    return jsonify({"status":"ok","cleared":n})

@app.errorhandler(404)
def nf(_): return jsonify({"status":"error","message":"Endpoint not found"}), 404

@app.errorhandler(500)
def ie(_): return jsonify({"status":"error","message":"Internal server error"}), 500

if __name__ == "__main__":
    log.info("Starting server at http://localhost:3000 | model=%s", FIREWORKS_MODEL)
    from waitress import serve  # optional local; if not installed, fallback
    try:
        serve(app, host="0.0.0.0", port=int(os.getenv("PORT","3000")))
    except Exception:
        app.run(host="0.0.0.0", port=int(os.getenv("PORT","3000")), debug=False, threaded=True)
