import tweepy
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class TwitterClient:
    def __init__(self):
        self.client = None
        self.setup_client()
    
    def setup_client(self):
        try:
            bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
            if bearer_token and bearer_token != 'your_twitter_bearer_token':
                self.client = tweepy.Client(bearer_token=bearer_token)
                logger.info("Twitter client initialized")
            else:
                logger.warning("Twitter bearer token not configured")
        except Exception as e:
            logger.error(f"Failed to initialize Twitter client: {e}")
    
    def post_tweet(self, text):
        """Post a tweet if client is configured"""
        if not self.client:
            logger.warning("Twitter client not configured, skipping tweet")
            return None
        
        try:
            # For now just log what would be posted
            logger.info(f"Would post tweet: {text[:50]}...")
            # response = self.client.create_tweet(text=text)
            # return response
            return {"id": "test", "text": text}
        except Exception as e:
            logger.error(f"Error posting tweet: {e}")
            return None