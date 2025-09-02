# src/agent_tools/news/news.py
import feedparser
import logging

log = logging.getLogger("ssa.news")

RSS_FEEDS = {
    "tech": [
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "https://www.theverge.com/rss/index.xml",
    ],
    "crypto": [
        "https://cointelegraph.com/rss",
        "https://news.bitcoin.com/feed/",
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

class News:
    def __init__(self, secrets: dict = None, *_):
        log.info("News agent initialized")

    def _parse_feed(self, url, max_articles=20, category="general"):
        try:
            feed = feedparser.parse(url)
            articles = []
            for entry in feed.entries[:max_articles]:
                articles.append({
                    "id": getattr(entry, "id", getattr(entry, "link", None)),
                    "title": getattr(entry, "title", ""),
                    "summary": getattr(entry, "summary", ""),
                    "link": getattr(entry, "link", ""),
                    "source": feed.feed.get("title", ""),
                    "published": getattr(entry, "published", ""),
                    "category": category,
                    "priority": "normal",
                })
            return articles
        except Exception as e:
            log.error("Failed to parse feed %s: %s", url, e)
            return []

    def fetch_rss_news(self, category: str, max_articles=20):
        feeds = RSS_FEEDS.get(category, [])
        out = []
        for f in feeds:
            out.extend(self._parse_feed(f, max_articles, category))
        return out

    def get_latest_news(self, max_total=30):
        out = []
        for cat, feeds in RSS_FEEDS.items():
            for f in feeds:
                out.extend(self._parse_feed(f, max_total // len(feeds), cat))
        return out

    def filter_breaking_news(self, articles):
        return [a for a in articles if "breaking" in (a.get("title") or "").lower()]
