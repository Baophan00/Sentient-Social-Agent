# src/agent/agent_config.py

class AgentConfig:
    """
    Global Agent Configuration (class-based)
    """

    def __init__(self):
        # --- Core tool flags ---
        self.TWITTER_ENABLED = True
        self.DISCORD_ENABLED = False
        self.NEWS_ENABLED = True

        # --- News Tool Overrides (optional; fallback: news_config.py) ---
        # Tần suất quét tin (giây)
        self.NEWS_UPDATE_INTERVAL = 3600  # 1 hour

        # Danh mục theo dõi
        self.NEWS_CATEGORIES = ['tech', 'crypto', 'ai']

        # Độ nhạy với breaking news (càng nhỏ càng nhạy)
        self.NEWS_BREAKING_THRESHOLD = 2

        # Bật/tắt các chế độ đăng tin
        self.NEWS_AUTO_POST = True           # tự động đăng
        self.NEWS_BREAKING_ALERTS = True     # cảnh báo tức thời
        self.NEWS_DAILY_DIGEST = True        # tổng hợp hằng ngày

        # Giới hạn nâng cao
        self.NEWS_MAX_ARTICLES_PER_UPDATE = 10
        self.NEWS_CONTENT_FILTER_ENABLED = True
