# test_news_agent.py
"""
Test script for News Agent - Run this to verify everything works
"""

import os
import sys
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_news_agent():
    """Test the news agent functionality"""
    
    print("🧪 Testing Sentient News Agent")
    print("=" * 50)
    
    # Load environment variables
    load_dotenv()
    
    # Check required environment variables
    required_vars = ['FIREWORKS_API_KEY']
    optional_vars = ['NEWS_API_KEY', 'TWITTER_CONSUMER_KEY']
    
    print("\n1. Checking environment variables...")
    for var in required_vars:
        if os.getenv(var):
            print(f"   ✅ {var}: Found")
        else:
            print(f"   ❌ {var}: Missing (required)")
            return False
            
    for var in optional_vars:
        if os.getenv(var):
            print(f"   ✅ {var}: Found")
        else:
            print(f"   ⚠️  {var}: Missing (optional)")
    
    # Test imports
    print("\n2. Testing imports...")
    try:
        from src.agent.agent_tools.news import News, NewsConfig
        print("   ✅ News tool imports successful")
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
        return False
    
    # Test news tool initialization
    print("\n3. Testing News tool initialization...")
    try:
        secrets = {
            'NEWS_API_KEY': os.getenv('NEWS_API_KEY'),
            'FIREWORKS_API_KEY': os.getenv('FIREWORKS_API_KEY')
        }
        news_tool = News(secrets, None)
        print("   ✅ News tool initialized successfully")
    except Exception as e:
        print(f"   ❌ Initialization error: {e}")
        return False
    
    # Test RSS feed parsing
    print("\n4. Testing RSS feed parsing...")
    try:
        articles = news_tool.fetch_rss_news('tech', max_articles=3)
        if articles:
            print(f"   ✅ Fetched {len(articles)} tech articles")
            print(f"   📰 Sample: {articles[0]['title'][:60]}...")
        else:
            print("   ⚠️  No articles fetched (might be normal)")
    except Exception as e:
        print(f"   ❌ RSS parsing error: {e}")
        return False
    
    # Test NewsAPI (if key provided)
    print("\n5. Testing NewsAPI...")
    if os.getenv('NEWS_API_KEY'):
        try:
            newsapi_articles = news_tool.fetch_newsapi_news('technology', max_articles=2)
            if newsapi_articles:
                print(f"   ✅ NewsAPI fetched {len(newsapi_articles)} articles")
            else:
                print("   ⚠️  NewsAPI returned no articles")
        except Exception as e:
            print(f"   ❌ NewsAPI error: {e}")
    else:
        print("   ⏭️  Skipped (no API key)")
    
    # Test content processing
    print("\n6. Testing content processing...")
    try:
        if articles:
            # Test breaking news detection
            breaking = news_tool.filter_breaking_news(articles)
            print(f"   ✅ Breaking news filter: {len(breaking)} breaking articles")
            
            # Test digest creation
            digest = news_tool.create_news_digest(articles[:2], 'discord')
            print(f"   ✅ Digest creation: {len(digest)} characters")
            
            # Test social post creation
            if articles:
                post = news_tool.create_social_post(articles[0], 'twitter')
                print(f"   ✅ Social post: {len(post)} characters")
        else:
            print("   ⏭️  Skipped (no articles to process)")
    except Exception as e:
        print(f"   ❌ Content processing error: {e}")
        return False
    
    # Test main run method
    print("\n7. Testing main run method...")
    try:
        result = news_tool.run()
        print(f"   ✅ Run method executed")
        print(f"   📄 Result preview: {result[:100]}...")
    except Exception as e:
        print(f"   ❌ Run method error: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("🎉 All tests passed! Your News Agent is ready to go!")
    print("\n📋 Next steps:")
    print("   1. Run: python3 -m src.agent")
    print("   2. Your agent will start posting news automatically")
    print("   3. Check Twitter/Discord for posts")
    print("   4. Monitor logs for any issues")
    
    return True

def test_individual_components():
    """Test individual components separately"""
    
    print("\n🔧 Individual Component Tests")
    print("-" * 30)
    
    # Load environment
    load_dotenv()
    
    # Test RSS feeds individually
    print("\n📡 Testing RSS feeds...")
    import feedparser
    
    test_feeds = {
        'TechCrunch': 'https://techcrunch.com/feed/',
        'CoinDesk': 'https://coindesk.com/arc/outboundfeeds/rss/',
        'The Verge': 'https://www.theverge.com/rss/index.xml'
    }
    
    for name, url in test_feeds.items():
        try:
            feed = feedparser.parse(url)
            if hasattr(feed, 'entries') and len(feed.entries) > 0:
                print(f"   ✅ {name}: {len(feed.entries)} articles")
            else:
                print(f"   ⚠️  {name}: No articles found")
        except Exception as e:
            print(f"   ❌ {name}: Error - {e}")
    
    # Test NewsAPI
    if os.getenv('NEWS_API_KEY'):
        print("\n🔑 Testing NewsAPI...")
        try:
            import requests
            url = 'https://newsapi.org/v2/top-headlines'
            params = {
                'apiKey': os.getenv('NEWS_API_KEY'),
                'category': 'technology',
                'language': 'en',
                'pageSize': 5
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get('status') == 'ok':
                articles = data.get('articles', [])
                print(f"   ✅ NewsAPI: {len(articles)} articles")
            else:
                print(f"   ❌ NewsAPI error: {data.get('message', 'Unknown')}")
        except Exception as e:
            print(f"   ❌ NewsAPI test failed: {e}")
    else:
        print("\n🔑 NewsAPI: Skipped (no key)")

if __name__ == "__main__":
    print("🤖 Sentient News Agent Test Suite")
    print("=" * 50)
    
    # Run main test
    success = test_news_agent()
    
    if not success:
        print("\n💥 Some tests failed. Check the errors above.")
        test_individual_components()
        sys.exit(1)
    
    # Offer to run component tests
    response = input("\n🔍 Run individual component tests? (y/n): ")
    if response.lower().startswith('y'):
        test_individual_components()
    
    print("\n✨ Testing complete! Your News Agent is ready for deployment.")