#!/usr/bin/env python3
"""
Main entry point for the Sentient News Agent
"""
import os
import sys
import logging
import time
from dotenv import load_dotenv

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("news_agent.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Main function to run the news agent"""
    # Load environment variables
    load_dotenv()
    
    logger.info("🚀 Starting Sentient News Agent...")
    
    try:
        # Import and initialize components
        from src.agent.agent_tools.news import News
        from src.agent.social.twitter import TwitterClient
        
        logger.info("Initializing components...")
        twitter_client = TwitterClient()
        news_tool = News({}, twitter_client)
        
        logger.info("Starting main loop...")
        while True:
            try:
                # Cách 1: Sử dụng phương thức run() nếu có
                logger.info("Running news processing...")
                result = news_tool.run()
                logger.info(f"Processing result: {result}")
                
                # Hoặc cách 2: Sử dụng get_latest_news()
                # logger.info("Fetching latest news...")
                # articles = news_tool.get_latest_news()
                # if articles:
                #     logger.info(f"Found {len(articles)} articles")
                #     for i, article in enumerate(articles[:3]):
                #         logger.info(f"  {i+1}. {article['title'][:50]}...")
                # else:
                #     logger.info("No articles found")
                
                # Sleep for 30 minutes before next check
                logger.info("Sleeping for 30 minutes...")
                time.sleep(10)  # Tạm thời sleep 10 giây để test
                # time.sleep(1800)  # 30 minutes
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(300)  # Wait 5 minutes before retry
                
    except KeyboardInterrupt:
        logger.info("Agent stopped by user")
    except Exception as e:
        logger.error(f"Agent crashed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()