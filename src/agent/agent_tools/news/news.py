# src/agent_tools/news/news.py
import feedparser
import logging
from datetime import datetime
from time import mktime

log = logging.getLogger("ssa.news")

RSS_FEEDS = {
    "tech": [
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "https://www.theverge.com/rss/index.xml",
        # ✅ Reuters Technology
        "https://feeds.reuters.com/reuters/technologyNews",
    ],
    "crypto": [
        "https://cointelegraph.com/rss",
        "https://news.bitcoin.com/feed/",
        # ✅ Decrypt
        "https://decrypt.co/feed",
    ],
    "ai": [
        "https://venturebeat.com/category/ai/feed/",
        "https://spectrum.ieee.org/ai.rss",
    ],
    "finance": [
        "https://www.investing.com/rss/news_301.rss",
    ],
    "general": [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://rss.cnn.com/rss/edition.rss",
    ],
}

def _normalize_published(entry) -> tuple[str, float]:
    """
    Trả về (ISO8601 string, epoch_seconds) từ entry RSS.
    Nếu thiếu ngày, dùng now() để vẫn sắp xếp được.
    """
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            dt = datetime.fromtimestamp(mktime(entry.published_parsed))
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            dt = datetime.fromtimestamp(mktime(entry.updated_parsed))
        else:
            # fallback: cố gắng parse published / updated dạng string
            text = getattr(entry, "published", "") or getattr(entry, "updated", "")
            if text:
                try:
                    # feedparser không có dateutil, nên chỉ fallback now nếu không parse được
                    raise ValueError("no structured time")
                except Exception:
                    dt = datetime.utcnow()
            else:
                dt = datetime.utcnow()
    except Exception:
        dt = datetime.utcnow()
    # return dt.isoformat() + "Z", dt.timestamp()
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC"), dt.timestamp()


class News:
    def __init__(self, secrets: dict = None, *_):
        log.info("News agent initialized")

    def _parse_feed(self, url, max_articles=20, category="general"):
        try:
            feed = feedparser.parse(url)
            articles = []
            for entry in feed.entries[:max_articles]:
                published_iso, published_ts = _normalize_published(entry)
                aid = getattr(entry, "id", None) or getattr(entry, "link", None) or getattr(entry, "title", None)
                if not aid:
                    continue
                articles.append({
                    "id": aid,
                    "title": getattr(entry, "title", "") or "",
                    "summary": getattr(entry, "summary", "") or "",
                    "link": getattr(entry, "link", "") or "",
                    "source": (feed.feed.get("title", "") or "").strip(),
                    "published": published_iso,        # ISO8601 để hiển thị
                    "published_ts": published_ts,      # số để sắp xếp
                    "category": category,
                    "priority": "normal",
                })
            return articles
        except Exception as e:
            log.error("Failed to parse feed %s: %s", url, e)
            return []

    def _dedupe_and_sort(self, items):
        # Khử trùng lặp theo id/link/title
        seen, out = set(), []
        for a in items:
            key = a.get("id") or a.get("link") or a.get("title")
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(a)
        # Sắp xếp mới nhất lên đầu
        out.sort(key=lambda x: x.get("published_ts", 0), reverse=True)
        return out

    def fetch_rss_news(self, category: str, max_articles=20):
        feeds = RSS_FEEDS.get(category, [])
        out = []
        for f in feeds:
            out.extend(self._parse_feed(f, max_articles, category))
        return self._dedupe_and_sort(out)

    def get_latest_news(self, max_total=30):
        out = []
        for cat, feeds in RSS_FEEDS.items():
            # chia quota tương đối đều theo từng feed
            per_feed = max(1, max_total // max(len(feeds), 1))
            for f in feeds:
                out.extend(self._parse_feed(f, per_feed, cat))
        return self._dedupe_and_sort(out)

    def filter_breaking_news(self, articles):
        # vẫn giữ logic cũ; dữ liệu đầu vào đã sort mới nhất ở trên
        return [a for a in articles if "breaking" in (a.get("title") or "").lower()]
