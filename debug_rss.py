import feedparser
import requests
from datetime import datetime, timedelta

def quick_test():
    print("🔍 Quick RSS Test")
    print("=" * 40)
    
    # Test TechCrunch
    print("\n📡 Testing TechCrunch...")
    try:
        feed = feedparser.parse('https://techcrunch.com/feed/')
        print(f"   Entries found: {len(feed.entries) if hasattr(feed, 'entries') else 0}")
        
        if hasattr(feed, 'entries') and feed.entries:
            print("   Recent articles:")
            for i, entry in enumerate(feed.entries[:3]):
                print(f"   {i+1}. {entry.title}")
                print(f"      Date: {getattr(entry, 'published', 'No date')}")
                print(f"      Summary: {getattr(entry, 'summary', 'No summary')[:100]}...")
                print()
        else:
            print("   ❌ No entries found")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test BBC (usually reliable)
    print("\n📡 Testing BBC News...")
    try:
        feed2 = feedparser.parse('https://feeds.bbci.co.uk/news/rss.xml')
        print(f"   Entries found: {len(feed2.entries) if hasattr(feed2, 'entries') else 0}")
        
        if hasattr(feed2, 'entries') and feed2.entries:
            print("   Recent articles:")
            for i, entry in enumerate(feed2.entries[:2]):
                print(f"   {i+1}. {entry.title}")
                print(f"      Date: {getattr(entry, 'published', 'No date')}")
                print()
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test CoinDesk
    print("\n📡 Testing CoinDesk...")
    try:
        feed3 = feedparser.parse('https://coindesk.com/arc/outboundfeeds/rss/')
        print(f"   Entries found: {len(feed3.entries) if hasattr(feed3, 'entries') else 0}")
        
        if hasattr(feed3, 'entries') and feed3.entries:
            print("   Recent crypto articles:")
            for i, entry in enumerate(feed3.entries[:2]):
                print(f"   {i+1}. {entry.title}")
                print(f"      Date: {getattr(entry, 'published', 'No date')}")
                print()
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print(f"\n📅 Current time: {datetime.now()}")
    print(f"📅 24h ago: {datetime.now() - timedelta(hours=24)}")
    print(f"📅 72h ago: {datetime.now() - timedelta(hours=72)}")
    
    print("\n" + "=" * 40)
    print("🎯 Debug complete!")

if __name__ == "__main__":
    quick_test()