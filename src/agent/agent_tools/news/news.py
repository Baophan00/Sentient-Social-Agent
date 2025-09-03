# src/agent/agent_tools/news/news.py
import os
import re
import json
import time
import math
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from time import mktime
from typing import Any, Dict, List, Tuple, Optional

import feedparser

from .news_config import NewsConfig
from ..twitter.twitter import Twitter

log = logging.getLogger("ssa.news")
logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
PROCESSED_PATH = DATA_DIR / "news_processed.json"


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _normalize_published(entry) -> Tuple[str, float]:
    try:
        if getattr(entry, "published_parsed", None):
            dt = datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
        elif getattr(entry, "updated_parsed", None):
            dt = datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
        else:
            dt = datetime.now(tz=timezone.utc)
    except Exception:
        dt = datetime.now(tz=timezone.utc)
    return dt.isoformat(), dt.timestamp()


def _truncate_tweet(text: str, limit: int = 280) -> str:
    return text if len(text) <= limit else text[:limit]


def _clean_source_name(feed) -> str:
    name = ""
    try:
        name = (feed.feed.get("title", "") or "").strip()
    except Exception:
        pass
    repl = {
        "The Verge": "The Verge",
        "Reuters": "Reuters",
        "BBC": "BBC",
        "Ars Technica": "Ars Technica",
        "Wired": "Wired",
        "TechCrunch": "TechCrunch",
        "CoinDesk": "CoinDesk",
        "Cointelegraph": "Cointelegraph",
        "CryptoNews": "CryptoNews",
        "VentureBeat": "VentureBeat",
        "AI News": "AI News",
    }
    for k, v in repl.items():
        if k.lower() in name.lower():
            return v
    return name or "Unknown"


def _safe_get(e, attr, default=""):
    try:
        v = getattr(e, attr, default) or default
        return v.strip() if isinstance(v, str) else v
    except Exception:
        return default


def _csv_env(name: str) -> List[str]:
    raw = os.getenv(name, "")
    return [x.strip() for x in raw.split(",") if x.strip()]


class News:
    """
    - Quét RSS, chấm điểm nổi bật, LLM tóm tắt, đăng X (lazy init Twitter)
    - Hỗ trợ lọc theo category cho web_server
    """

    def __init__(self, secrets: Dict[str, Any] = None, model: Any = None) -> None:
        self.secrets = secrets or {}
        self.model = model
        self.cfg = NewsConfig()
        self.processed: set[str] = self._load_processed()

        self._apply_overrides()

        # Twitter client: lazy
        self.twitter: Optional[Twitter] = None

        self.tw_cfg = self.cfg.get_platform_config("twitter")
        self.max_char = int(self.tw_cfg.get("max_char_limit", 250))

        log.info(
            "[NEWS] Initialized. Categories=%s, interval=%ss, auto_post=%s, max_per_update=%s",
            self.categories, self.update_interval, self.auto_post, self.max_per_update
        )

    # ---------------- Overrides ----------------
    def _apply_overrides(self):
        self.update_interval = int(getattr(self.cfg, "update_interval", 1800))
        self.categories = list(getattr(self.cfg, "categories", []))
        self.max_per_update = int(getattr(self.cfg, "max_articles_per_digest", 5))
        self.breaking_threshold = int(getattr(self.cfg, "schedule_settings", {}).get("breaking_news_threshold", 2))
        self.auto_post = True
        self._rss_feeds = dict(getattr(self.cfg, "rss_feeds", {}))

        try:
            import src.agent.agent_config as agent_config
        except Exception:
            agent_config = None

        def _get_from_agent(name, default):
            if agent_config and hasattr(agent_config, name):
                return getattr(agent_config, name)
            return default

        self.update_interval = int(os.getenv(
            "NEWS_UPDATE_INTERVAL",
            _get_from_agent("NEWS_UPDATE_INTERVAL", self.update_interval)
        ))

        env_cats = _csv_env("NEWS_CATEGORIES")
        self.categories = env_cats or _get_from_agent("NEWS_CATEGORIES", self.categories)

        self.breaking_threshold = int(os.getenv(
            "NEWS_BREAKING_THRESHOLD",
            _get_from_agent("NEWS_BREAKING_THRESHOLD", self.breaking_threshold)
        ))

        self.auto_post = (os.getenv("NEWS_AUTO_POST", str(_get_from_agent("NEWS_AUTO_POST", True))).lower() != "false")

        self.max_per_update = int(os.getenv(
            "NEWS_MAX_ARTICLES_PER_UPDATE",
            _get_from_agent("NEWS_MAX_ARTICLES_PER_UPDATE", self.max_per_update)
        ))

        # Merge thêm nguồn từ ENV vào category 'general'
        extra_sources = _csv_env("NEWS_SOURCES")
        if extra_sources:
            feeds = list(self._rss_feeds.get("general", []))
            feeds.extend(extra_sources)
            seen, merged = set(), []
            for u in feeds:
                if u not in seen:
                    merged.append(u); seen.add(u)
            self._rss_feeds["general"] = merged
            if "general" not in self.categories:
                self.categories.append("general")

    # ---------------- State ----------------
    def _load_processed(self) -> set:
        if PROCESSED_PATH.exists():
            try:
                return set(json.loads(PROCESSED_PATH.read_text()))
            except Exception:
                log.warning("[NEWS] processed file broken. Starting fresh.")
        return set()

    def _save_processed(self):
        PROCESSED_PATH.write_text(json.dumps(sorted(self.processed)))

    # ---------------- Twitter (lazy init) ----------------
    def _ensure_twitter(self):
        if self.twitter is not None:
            return
        consumer_key = os.getenv("TWITTER_CONSUMER_KEY")
        consumer_secret = os.getenv("TWITTER_CONSUMER_SECRET")
        access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
        bearer_token = os.getenv("TWITTER_BEARER_TOKEN")

        tw = Twitter(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            bearer_token=bearer_token,
            model=self.model,
        )
        if not getattr(tw, "config", None) or not getattr(tw.config, "KEY_USERS", None):
            tw.config.KEY_USERS = [getattr(tw, "username", "newsbot")]
        self.twitter = tw

    # ---------------- Fetch ----------------
    def _parse_feed(self, url: str, category: str, per_feed_limit: int) -> List[Dict]:
        try:
            feed = feedparser.parse(url)
            src_name = _clean_source_name(feed)
            out = []
            for e in feed.entries[:per_feed_limit]:
                published_iso, published_ts = _normalize_published(e)
                link = _safe_get(e, "link", "")
                title = _safe_get(e, "title", "")
                summary = _safe_get(e, "summary", "")
                eid = _safe_get(e, "id", "") or link or title
                if not (title and link and eid):
                    continue
                out.append({
                    "id": eid,
                    "hid": _hash(eid),
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "source": src_name,
                    "category": category,
                    "published": published_iso,
                    "published_ts": published_ts,
                })
            return out
        except Exception as ex:
            log.warning("[NEWS] RSS error %s -> %s", url, ex)
            return []

    def _fetch_categories(self, cats: List[str], max_total: int) -> List[Dict]:
        items: List[Dict] = []
        for cat in cats:
            feeds = self._rss_feeds.get(cat, [])
            per_feed = max(1, max_total // max(1, len(feeds) or 1))
            for url in feeds:
                items.extend(self._parse_feed(url, cat, per_feed))
        # dedupe + sort
        seen, out = set(), []
        for a in items:
            if a["hid"] in seen:
                continue
            seen.add(a["hid"])
            out.append(a)
        out.sort(key=lambda x: x["published_ts"], reverse=True)
        return out

    def _fetch_all(self, max_total: int = 60) -> List[Dict]:
        return self._fetch_categories(self.categories, max_total)

    def fetch_by_category(self, category: str, max_total: int = 30) -> List[Dict]:
        """Dùng cho web_server: chỉ lấy đúng 1 category"""
        if category and category in self._rss_feeds:
            return self._fetch_categories([category], max_total)
        return self._fetch_all(max_total)

    # ---------------- Ranking ----------------
    def _score_items(self, items: List[Dict]) -> List[Dict]:
        def norm_title(t: str) -> str:
            t = t.lower()
            t = re.sub(r"[^a-z0-9\s]+", " ", t)
            t = re.sub(r"\s+", " ", t).strip()
            return t

        counts: Dict[str, int] = {}
        for a in items:
            key = norm_title(a["title"])
            counts[key] = counts.get(key, 0) + 1

        now = datetime.now(tz=timezone.utc).timestamp()
        scored = []
        for a in items:
            src_priority = self.cfg.source_priorities.get(a["source"], self.cfg.source_priorities.get("Unknown", 1))
            w_src = 1.2

            c = counts.get(norm_title(a["title"]), 1)
            w_multi = 1.0
            multi_score = (c - 1)

            is_breaking = any(kw in a["title"].lower() for kw in self.cfg.breaking_keywords)
            if a["category"] == "crypto":
                is_breaking = is_breaking or any(kw in a["title"].lower() for kw in self.cfg.crypto_breaking_keywords)
            w_kw = 1.0

            age_hours = max(0.0, (now - a["published_ts"]) / 3600.0)
            half_life = 6.0
            recency = math.exp(-age_hours / half_life)
            w_recency = 2.0

            score = (
                w_src * float(src_priority)
                + w_multi * float(multi_score)
                + w_kw * (1.0 if is_breaking else 0.0)
                + w_recency * recency
            )

            a2 = dict(a)
            a2["score"] = round(score, 4)
            a2["age_hours"] = round(age_hours, 2)
            a2["multi_appear"] = c
            a2["is_breaking"] = bool(is_breaking)
            scored.append(a2)

        scored.sort(key=lambda x: (x["score"], x["published_ts"]), reverse=True)
        return scored

    # ---------------- Compose tweet ----------------
    def _llm_summarize(self, title: str, link: str, source: str, summary: str = "") -> str:
        if not self.model or not hasattr(self.model, "query"):
            return title
        prompt = (
            "You are a news assistant for Twitter/X. "
            "Write one engaging sentence under 240 characters (no hashtags, no emojis). "
            "Be factual, neutral about the publisher, and highlight the impact. "
            f"Title: {title}\n"
            f"Source: {source}\n"
            f"Summary: {summary}\n"
            "Return only the sentence."
        )
        try:
            text = str(self.model.query(prompt)).strip().replace("\n", " ")
            return text or title
        except Exception as ex:
            log.warning("[NEWS] LLM summarize failed: %s", ex)
            return title

    def _compose_tweet(self, a: Dict) -> str:
        base = self._llm_summarize(a["title"], a["link"], a["source"], a.get("summary", ""))
        link = a["link"].strip()
        tags = ""
        if self.tw_cfg.get("hashtags", True):
            default_tags = {
                "ai": ["#AI"],
                "tech": ["#tech"],
                "crypto": ["#crypto"],
                "finance": ["#finance"],
            }
            taglist = default_tags.get(a["category"], [])
            if taglist:
                tags = " " + " ".join(taglist)
        text = f"{base}{tags} {link}".strip()
        return _truncate_tweet(text, 280)

    # ---------------- Posting ----------------
    def _post_batch(self, items: List[Dict], max_posts: int) -> int:
        posted = 0
        for a in items:
            if posted >= max_posts:
                break
            if a["hid"] in self.processed:
                continue

            tweet = self._compose_tweet(a)

            if not self.auto_post:
                log.info("(dry-run) %s", tweet)
                self.processed.add(a["hid"])
                continue

            self._ensure_twitter()

            ok, tweet_id, retry_after = self.twitter.post_tweet(tweet)  # type: ignore
            if ok:
                posted += 1
                self.processed.add(a["hid"])
                log.info("[NEWS] Tweeted (%s): %s", tweet_id, tweet)
                time.sleep(3)
            else:
                if retry_after is not None:
                    log.warning("[NEWS] Hit rate limit. Stopping this cycle. Suggested wait ~%ss", retry_after)
                    break
                else:
                    log.warning("[NEWS] Post failed (non-429). Skipping this item.")
                    self.processed.add(a["hid"])

        self._save_processed()
        return posted

    # ---------------- For web_server ----------------
    def get_latest_news(self, max_total: int = 30, category: Optional[str] = None):
        if category:
            raw = self.fetch_by_category(category, max_total=max_total)
        else:
            raw = self._fetch_all(max_total=max_total)
        ranked = self._score_items(raw)
        return ranked[:max_total]

    # ---------------- Loop ----------------
    def run(self):
        interval = int(self.update_interval or 1800)
        max_per_run = int(self.max_per_update or 5)
        log.info("[NEWS] Starting loop. interval=%ss, max_per_run=%s", interval, max_per_run)

        while True:
            try:
                if getattr(self.cfg, "is_quiet_hour", None) and self.cfg.is_quiet_hour():
                    log.info("[NEWS] Quiet hours. Skipping this cycle.")
                else:
                    raw = self._fetch_all(max_total=max(60, max_per_run * 10))
                    if not raw:
                        log.info("[NEWS] No articles fetched.")
                    else:
                        ranked = self._score_items(raw)
                        if getattr(self.cfg, "should_reduce_frequency", None) and self.cfg.should_reduce_frequency():
                            max_run_now = max(1, max_per_run // 2)
                        else:
                            max_run_now = max_per_run
                        posted = self._post_batch(ranked, max_run_now)
                        log.info("[NEWS] Cycle done. Posted %d item(s).", posted)
            except Exception as ex:
                log.exception("[NEWS] Cycle error: %s", ex)
            time.sleep(max(30, interval))
