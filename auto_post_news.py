# news_runner.py
import argparse
import logging
import os
from src.agent.agent_tools.news.news import News

# Fireworks/OpenAI client wrapper
from src.agent.llm_client import LLMClient  

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
log = logging.getLogger("ssa.news_runner")


def main_once(max_posts: int = 3):
    """Fetch + rank + post tối đa N bài"""
    model = LLMClient()
    news_agent = News(model=model)

    log.info("Fetching articles...")
    raw = news_agent._fetch_all(max_total=80)
    if not raw:
        log.info("No articles fetched.")
        return

    ranked = news_agent._score_items(raw)
    posted = news_agent._post_batch(ranked, max_posts)
    log.info("Done. Posted %d tweet(s).", posted)


def main_loop():
    """Chạy loop vĩnh viễn (theo interval trong config/env)"""
    model = LLMClient()
    news_agent = News(model=model)
    news_agent.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Fetch + post một lần rồi thoát")
    parser.add_argument("--loop", action="store_true", help="Chạy vòng lặp tự động")
    parser.add_argument("--max-posts", type=int, default=3, help="Số bài tối đa cho mỗi lần chạy")
    args = parser.parse_args()

    if args.once:
        main_once(max_posts=args.max_posts)
    elif args.loop:
        main_loop()
    else:
        parser.print_help()
