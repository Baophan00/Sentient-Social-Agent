#!/usr/bin/env python3
# news_runner.py
import os
import time
import logging
import argparse
from datetime import datetime, timezone

from dotenv import load_dotenv

# ---- Logging ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger("ssa.news_runner")

# ---- Load .env (local). Trên Render bạn set ENV trong dashboard nên không cần .env ----
load_dotenv()

# ---- Optional LLM: Fireworks (OpenAI-compatible) / OpenAI ----
def build_model():
    """
    Trả về client OpenAI-compatible nếu có key, ngược lại trả về None.
    - Ưu tiên FIREWORKS_API_KEY với BASE_URL fireworks.
    - Nếu không, dùng OPENAI_API_KEY (OpenAI chuẩn).
    """
    try:
        from openai import OpenAI
    except Exception:
        log.warning("[LLM] openai package not available. Proceeding without LLM.")
        return None

    fw_key = os.getenv("FIREWORKS_API_KEY", "").strip()
    oa_key = os.getenv("OPENAI_API_KEY", "").strip()

    if fw_key:
        base_url = os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1").strip()
        log.info("[LLM] Fireworks via OpenAI-compatible")
        return OpenAI(api_key=fw_key, base_url=base_url)

    if oa_key:
        log.info("[LLM] OpenAI client")
        return OpenAI(api_key=oa_key)

    log.info("[LLM] No API key found. Running without LLM summarization.")
    return None


def build_news(model):
    """
    Tạo instance News tool theo khung Sentient-Social-Agent.
    """
    # Import động để tránh lỗi đường dẫn khi chạy từ root
    try:
        # Nếu __init__.py đã export News
        from src.agent.agent_tools.news import News
    except Exception:
        # Fallback import trực tiếp module
        from src.agent.agent_tools.news.news import News  # type: ignore

    secrets = {
        "FIREWORKS_API_KEY": os.getenv("FIREWORKS_API_KEY", "").strip(),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "").strip(),
    }

    news = News(secrets=secrets, model=model)
    # Log cấu hình chính để dễ debug
    try:
        cats = getattr(news, "categories", None)
        interval = getattr(news, "update_interval", None)
        auto_post = getattr(news, "auto_post", None)
        max_per_update = getattr(news, "max_per_update", None)
        logging.info(
            "[NEWS] Initialized. Categories=%s, interval=%ss, auto_post=%s, max_per_update=%s",
            cats, interval, auto_post, max_per_update
        )
    except Exception:
        pass
    return news


def run_once(max_posts: int, fetch_total: int):
    """
    Chạy một vòng:
    - fetch tất cả bài theo cấu hình trong News
    - chấm điểm / xếp hạng
    - đăng tối đa 'max_posts' bài
    """
    model = build_model()
    news = build_news(model=model)

    # Dùng các API nội bộ của News mà bạn đang có
    raw = news._fetch_all(max_total=fetch_total)
    if not raw:
        log.info("No articles fetched.")
        return 0

    ranked = news._score_items(raw)
    posted = news._post_batch(ranked, max_posts=max_posts)
    log.info("Done. Posted %d tweet(s) at %s.", posted, datetime.now(timezone.utc).isoformat())
    return posted


def main():
    parser = argparse.ArgumentParser(description="Run news poster (one-shot or loop).")
    parser.add_argument("--once", action="store_true", help="Run exactly one cycle and exit.")
    parser.add_argument("--loop", action="store_true", help="Run forever with sleep between cycles.")
    parser.add_argument("--max-posts", type=int, default=int(os.getenv("NEWS_MAX_ARTICLES_PER_UPDATE", "1")),
                        help="Max number of tweets per cycle.")
    parser.add_argument("--fetch-total", type=int, default=int(os.getenv("NEWS_FETCH_MAX_TOTAL", "40")),
                        help="Max number of articles to fetch per cycle before ranking.")
    parser.add_argument("--interval", type=int, default=int(os.getenv("NEWS_UPDATE_INTERVAL", "600")),
                        help="Sleep seconds between cycles when --loop (default from NEWS_UPDATE_INTERVAL).")
    args = parser.parse_args()

    if not (args.once or args.loop):
        # Mặc định chạy một lần cho đơn giản
        args.once = True

    if args.once:
        try:
            run_once(max_posts=args.max_posts, fetch_total=args.fetch_total)
        except Exception as e:
            log.exception("ERROR: %s", e)
        return

    # --loop
    log.info("Start loop: interval=%ss, max_posts=%s, fetch_total=%s", args.interval, args.max_posts, args.fetch_total)
    while True:
        try:
            run_once(max_posts=args.max_posts, fetch_total=args.fetch_total)
        except Exception as e:
            log.exception("ERROR (loop iteration): %s", e)
        # Ngủ giữa các vòng
        sleep_s = max(30, int(args.interval))
        time.sleep(sleep_s)


if __name__ == "__main__":
    main()
