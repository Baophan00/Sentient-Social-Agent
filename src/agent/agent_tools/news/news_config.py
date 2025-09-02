#!/usr/bin/env python3
# src/agent/agent_tools/news/news_config.py
from typing import Dict
from datetime import datetime

class NewsConfig:
    def __init__(self):
        # Update frequency
        self.update_interval = 3600  # 1 hour in seconds
        self.breaking_news_interval = 300  # 5 minutes for breaking news
        
        # Categories to monitor
        self.categories = ['tech', 'crypto', 'ai']
        
        # RSS Feeds configuration
        self.rss_feeds = {
            'tech': [
                'https://techcrunch.com/feed/',
                'https://www.theverge.com/rss/index.xml',
                'https://feeds.arstechnica.com/arstechnica/index',
                'https://www.wired.com/feed/rss'
            ],
            'crypto': [
                'https://www.coindesk.com/arc/outboundfeeds/rss/',
                'https://cointelegraph.com/rss',
                'https://cryptonews.com/feed/',
                'https://decrypt.co/feed'
            ],
            'ai': [
                'https://venturebeat.com/ai/feed/',
                'https://www.artificialintelligence-news.com/feed/',
                'https://hai.stanford.edu/news/rss.xml'
            ]
        }
        
        # Content limits
        self.max_articles_per_digest = 5
        self.max_articles_per_category = 3
        self.max_summary_length = 300
        
        # Breaking news detection
        self.breaking_keywords = [
            'breaking', 'urgent', 'alert', 'major announcement',
            'significant', 'crash', 'surge', 'record high', 
            'record low', 'first time', 'unprecedented', 
            'massive', 'huge', 'emergency', 'critical'
        ]
        
        # Crypto specific breaking keywords
        self.crypto_breaking_keywords = [
            'bitcoin', 'btc', 'ethereum', 'eth', 'crash',
            'surge', 'all-time high', 'ath', 'moon', 'dump'
        ]
        
        # Source reliability and priority (1-5 scale)
        self.source_priorities = {
            # Tier 1 - Most reliable
            'Reuters': 5,
            'BBC': 5,
            'Associated Press': 5,
            
            # Tier 2 - Tech focused
            'TechCrunch': 4,
            'The Verge': 4,
            'Ars Technica': 4,
            'Wired': 4,
            
            # Tier 3 - Crypto focused
            'CoinDesk': 4,
            'Cointelegraph': 3,
            'Decrypt': 3,
            'CryptoNews': 3,
            
            # Tier 4 - AI focused
            'VentureBeat': 3,
            'AI News': 3,
            
            # Default
            'Unknown': 1
        }
        
        # Platform specific settings
        self.platform_settings = {
            'twitter': {
                'max_char_limit': 250,  # Leave room for link
                'hashtags': True,
                'thread_threshold': 3,  # Create thread if >3 articles
            },
            'discord': {
                'use_embeds': True,
                'max_embed_fields': 5,
                'mention_roles': []  # Add role IDs to mention
            },
            'sentient': {
                'rich_format': True,
                'interactive_elements': True,
                'max_articles_display': 10
            }
        }
        
        # Scheduling settings
        self.schedule_settings = {
            'daily_digest_time': '09:00',  # UTC
            'breaking_news_threshold': 2,  # Minimum breaking score
            'quiet_hours': ['22:00', '06:00'],  # UTC quiet period
            'weekend_reduced_frequency': True
        }
        
        # Content filtering
        self.content_filters = {
            'min_article_length': 50,  # Minimum characters
            'exclude_keywords': [
                'sponsored', 'advertisement', 'promo'
            ],
            'required_keywords_crypto': [
                'bitcoin', 'ethereum', 'crypto', 'blockchain', 
                'defi', 'nft', 'web3', 'token'
            ]
        }
        
        # Rate limiting
        self.rate_limits = {
            'requests_per_minute': 60,
            'articles_per_hour': 20,
            'breaking_news_per_day': 5
        }

    def get_platform_config(self, platform: str) -> Dict:
        """Get configuration for specific platform"""
        return self.platform_settings.get(platform, self.platform_settings['twitter'])
        
    def is_quiet_hour(self) -> bool:
        """Check if current time is in quiet hours"""
        current_hour = datetime.now().strftime('%H:%M')
        quiet_start, quiet_end = self.schedule_settings['quiet_hours']
        
        return quiet_start <= current_hour or current_hour <= quiet_end
        
    def should_reduce_frequency(self) -> bool:
        """Check if should reduce posting frequency (weekends)"""
        if not self.schedule_settings['weekend_reduced_frequency']:
            return False
            
        return datetime.now().weekday() >= 5  # Saturday = 5, Sunday = 6