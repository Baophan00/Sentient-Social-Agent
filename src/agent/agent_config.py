# src/agent/agent_config.py
# Add this to your existing agent_config.py file

# Existing tool configurations
TWITTER_ENABLED = True
DISCORD_ENABLED = True

# Add News Tool Configuration
NEWS_ENABLED = True

# News-specific settings (optional - defaults in news_config.py)
NEWS_UPDATE_INTERVAL = 3600  # 1 hour
NEWS_CATEGORIES = ['tech', 'crypto', 'ai']  # Default categories
NEWS_BREAKING_THRESHOLD = 2  # Breaking news sensitivity

# If you want to enable/disable specific news features
NEWS_AUTO_POST = True  # Automatically post to social media
NEWS_BREAKING_ALERTS = True  # Send immediate breaking news alerts
NEWS_DAILY_DIGEST = True  # Send daily digest

# Advanced settings
NEWS_MAX_ARTICLES_PER_UPDATE = 10
NEWS_CONTENT_FILTER_ENABLED = True