
#!/usr/bin/env python3
import os
import sys
import time
import argparse
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from src.agent.agent_tools.news.news import News

def build_llm():
    load_dotenv()
    try:
        from openai import OpenAI
    except Exception:
        OpenAI = None

    fw_key = os.getenv("FIREWORKS_API_KEY")
    if fw_key and OpenAI:
        base_url = os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
        model = os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/llama-v3p1-8b-instruct")
        class FireworksWrapper:
            def __init__(self):
                self.client = OpenAI(api_key=fw_key, base_url=base_url)
                self.model = model
            def query(self, prompt: str) -> str:
                r = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role":"user","content":prompt}],
                    temperature=0.5, max_tokens=120
                )
                return (r.choices[0].message.content or "").strip()
        logging.info("[LLM] Fireworks via OpenAI-compatible")
        return FireworksWrapper()

    oa_key = os.getenv("OPENAI_API_KEY")
    if oa_key and OpenAI:
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        class OpenAIWrapper:
            def __init__(self):
                self.client = OpenAI(api_key=oa_key)
                self.model = model
            def query(self, prompt: str) -> str:
                r = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role":"user","content":prompt}],
                    temperature=0.7, max_tokens=120
                )
                return (r.choices[0].message.content or "").strip()
        logging.info("[LLM] OpenAI")
        return OpenAIWrapper()

    logging.info("[LLM] No API key -> fallback title+link")
    return None

def run_once(max_posts: int, fetch_total: int):
    model = build_llm()
    news = News(model=model)
    ranked = news.get_latest_news(max_total=fetch_total)
    posted = news._post_batch(ranked, max_posts=max_posts)
    print(f"INFO: Done. Posted {posted} tweet(s) at {datetime.now(timezone.utc).isoformat()}.")

def run_loop(max_posts: int, fetch_total: int):
    # loop logic nằm trong News.run (đọc NEWS_UPDATE_INTERVAL)
    model = build_llm()
    news = News(model=model)
    # ép lại max mỗi vòng nếu muốn
    os.environ["NEWS_MAX_ARTICLES_PER_UPDATE"] = str(max_posts)
    # fetch_total được dùng nội bộ trong run qua _fetch_all (max_total tính toán)
    news.run()

def main():
    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    load_dotenv()

    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true", help="Chạy 1 vòng rồi thoát")
    p.add_argument("--loop", action="store_true", help="Chạy liên tục theo interval")
    p.add_argument("--max-posts", type=int, default=int(os.getenv("NEWS_MAX_ARTICLES_PER_UPDATE", "1")))
    p.add_argument("--fetch-total", type=int, default=int(os.getenv("NEWS_FETCH_MAX_TOTAL", "40")))
    args = p.parse_args()

    if args.once:
        run_once(max_posts=args.max_posts, fetch_total=args.fetch_total)
    elif args.loop:
        run_loop(max_posts=args.max_posts, fetch_total=args.fetch_total)
    else:
        p.print_help()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logging.exception("ERROR: %s", e)
        sys.exit(1)

