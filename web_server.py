import os, sys, json, logging, hashlib, time
from typing import List, Any, Callable
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify, request, Response, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import importlib
from functools import wraps

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("ssa.web")

load_dotenv()
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "").strip()
FIREWORKS_MODEL   = os.getenv("FIREWORKS_MODEL", "accounts/sentientfoundation/models/dobby-unhinged-llama-3-3-70b-new").strip()
NEWS_API_KEY      = os.getenv("NEWS_API_KEY", "").strip()
SERPER_API_KEY        = os.getenv("SERPER_API_KEY", "").strip()
SEARXNG_INSTANCE_URL  = os.getenv("SEARXNG_INSTANCE_URL", "").strip()
SEARXNG_API_KEY       = os.getenv("SEARXNG_API_KEY", "").strip()
JINA_API_KEY          = os.getenv("JINA_API_KEY", "").strip()
OPENROUTER_API_KEY    = os.getenv("OPENROUTER_API_KEY", "").strip()
ODS_MODEL             = os.getenv("ODS_MODEL", os.getenv("LITELLM_MODEL_ID", "openrouter/google/gemini-2.0-flash-001")).strip()
ADMIN_TOKEN           = os.getenv("ADMIN_TOKEN", "").strip()

ROOT = os.path.abspath(os.path.dirname(__file__))
SRC_PATH = os.path.join(ROOT, "src")

paths_to_add = [ROOT, SRC_PATH, os.path.join(ROOT, "src", "agent"), os.path.join(ROOT, "src", "agent", "agent_tools")]
for path in paths_to_add:
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

def _try_import_news():
    for mod in ["src.agent.agent_tools.news", "agent.agent_tools.news", "agent_tools.news"]:
        try:
            m = importlib.import_module(mod)
            return getattr(m, "News")
        except ImportError:
            continue
        except Exception as e:
            log.warning("Unexpected error importing %s: %s", mod, e)
    return None

SSA_News = _try_import_news()
if SSA_News:
    log.info("SSA News available.")
else:
    log.warning("SSA News not found")

SummarizerService = None
ods_runtime_snapshot_fn = None
try:
    try:
        from news_agent import SummarizerService, ods_runtime_snapshot as _ods_snap
    except ImportError:
        from src.news_agent import SummarizerService, ods_runtime_snapshot as _ods_snap
    log.info("SummarizerService ready.")
    ods_runtime_snapshot_fn = _ods_snap
except Exception as e:
    log.error("Failed to import SummarizerService: %s", e)

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
    llm_provider = ("openrouter" if "openrouter" in (ODS_MODEL.split("/",1)[0] if "/" in ODS_MODEL else ODS_MODEL).lower() else "other")
    missing = []
    if llm_provider == "openrouter" and not OPENROUTER_API_KEY:
        missing.append("OPENROUTER_API_KEY")
    if SEARXNG_INSTANCE_URL:
        pass
    else:
        if not SERPER_API_KEY:
            missing.append("SERPER_API_KEY")
    return (len(missing) == 0, missing)

# -------- Token helper: only enforce if ADMIN_TOKEN is set --------
def _extract_token() -> str:
    return (request.headers.get("X-Admin-Token", "") or request.args.get("token", "")).strip()

def require_token_if_configured(fn: Callable):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if ADMIN_TOKEN:  # only enforce when configured
            token = _extract_token()
            if token != ADMIN_TOKEN:
                return jsonify({"status": "error", "message": "unauthorized"}), 403
        return fn(*args, **kwargs)
    return wrapper

app = Flask(__name__)
CORS(app)

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

summarizer = None
if SummarizerService is not None:
    try:
        summarizer = SummarizerService(fireworks_model=FIREWORKS_MODEL)
    except Exception as e:
        log.error("Summarizer init failed: %s", e)

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

@app.route("/")
def root():
    return send_from_directory(ROOT, "news_dashboard.html")

@app.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(os.path.join(ROOT, "assets"), filename)

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

@app.route("/api/summarize", methods=["POST"])
@require_token_if_configured
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

_MAX_T = int(os.getenv("SSE_MAX_TITLE", "200"))
_MAX_D = int(os.getenv("SSE_MAX_DESC",  "2000"))
_MAX_U = int(os.getenv("SSE_MAX_URL",   "1024"))
_last_sse = {}

def _client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "0.0.0.0").split(",")[0].strip()

@app.route("/api/deep_analyze_sse")
@require_token_if_configured
def api_deep_analyze_sse():
    title = str(request.args.get("title",""))[:_MAX_T]
    desc  = str(request.args.get("description",""))[:_MAX_D]
    link  = str(request.args.get("url",""))[:_MAX_U]
    key = _hash_key("deep", title, desc, link)
    cache_path = CACHE_DIR / f"{key}.json"
    ip = _client_ip()
    now = time.time()
    if now - _last_sse.get((ip, key), 0) < 4:
        return Response(_sse({"type": "error", "message": "Too many requests; please wait."}),
                        mimetype="text/event-stream",
                        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
    _last_sse[(ip, key)] = now
    def stream():
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            yield _sse({"type":"done", "analysis": cached.get("analysis", "")})
            return
        modules = _check_ods_modules()
        ready, missing = _ods_env_ready()
        yield _sse({"type":"stage","stage":"init","detail":"Preparing deep analysis…"})
        yield _sse({"type":"stage","stage":"diag","detail":f"ods_import={modules['import']} tool={modules['tool']} v={modules['version']} ready={ready} missing={','.join(missing)}"})
        try:
            if ods_runtime_snapshot_fn:
                snap = ods_runtime_snapshot_fn()
                yield _sse({"type":"stage","stage":"config","detail": f"search={snap.get('search_provider')}, reranker={snap.get('reranker')}, llm={snap.get('llm_provider')}, model={ODS_MODEL}"})
        except Exception as _e:
            log.warning("Emit config stage failed: %s", _e)
        if summarizer is None:
            yield _sse({"type":"error","message":"Analyzer unavailable"})
            return
        if not modules["import"] or not modules["tool"] or not ready:
            yield _sse({"type":"error","message": f"ODS not ready: missing={','.join(missing)} err={modules['error']}"})
            return
        yield _sse({"type":"stage","stage":"search_provider","detail":"Searching…"})
        yield _sse({"type":"stage","stage":"reranker","detail":"Reranking…"})
        yield _sse({"type":"stage","stage":"llm_provider","detail":"Synthesizing…"})
        try:
            result = summarizer.deep_analyze_only(title, desc, link)
            cache_path.write_text(json.dumps({"analysis": result}, ensure_ascii=False), encoding="utf-8")
            yield _sse({"type":"done","analysis": result})
        except Exception as e:
            yield _sse({"type":"error","message": f"Deep analysis failed: {e}"})
    return Response(stream(), mimetype="text/event-stream", headers={
        "Cache-Control":"no-cache",
        "X-Accel-Buffering":"no"
    })

@app.route("/api/status")
def api_status():
    # status mở, không yêu cầu token
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

@app.route("/api/clear_cache", methods=["POST"])
@require_token_if_configured
def api_clear_cache():
    n = 0
    for p in CACHE_DIR.glob("*.json"):
        try:
            p.unlink(); n += 1
        except:
            pass
    return jsonify({"status":"ok","cleared":n})

@app.errorhandler(404)
def nf(_): return jsonify({"status":"error","message":"Endpoint not found"}), 404

@app.errorhandler(500)
def ie(_): return jsonify({"status":"error","message":"Internal server error"}), 500

if __name__ == "__main__":
    log.info("Starting server at http://localhost:3000 | model=%s", FIREWORKS_MODEL)
    from waitress import serve
    try:
        serve(app, host="0.0.0.0", port=int(os.getenv("PORT","3000")))
    except Exception:
        app.run(host="0.0.0.0", port=int(os.getenv("PORT","3000")), debug=False, threaded=True)
