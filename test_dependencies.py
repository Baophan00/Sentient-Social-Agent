#!/usr/bin/env python3
"""
Test script to verify all dependencies for the news dashboard
"""
import os
from dotenv import load_dotenv

load_dotenv()

def test_basic_imports():
    """Test basic Python packages"""
    print("🧪 Testing Basic Imports")
    print("-" * 40)
    
    try:
        import torch
        print(f"✅ PyTorch: {torch.__version__}")
    except ImportError as e:
        print(f"❌ PyTorch: {e}")
        return False
    
    try:
        import transformers
        print(f"✅ Transformers: {transformers.__version__}")
    except ImportError as e:
        print(f"❌ Transformers: {e}")
    
    try:
        from opendeepsearch.agent import ReasoningAgent
        print("✅ OpenDeepSearch")
    except ImportError as e:
        print(f"❌ OpenDeepSearch: {e}")
        return False
    
    try:
        from sentient_agent_framework import AbstractAgent
        print("✅ Sentient Agent Framework")
    except ImportError as e:
        print(f"❌ Sentient Agent Framework: {e}")
        return False
        
    return True

def test_api_key():
    """Test API key configuration"""
    print("\n🔑 Testing API Configuration")
    print("-" * 40)
    
    api_key = os.getenv("FIREWORKS_API_KEY", "")
    if api_key and api_key != "your_fireworks_api_key_here":
        print("✅ FIREWORKS_API_KEY configured")
        return True
    else:
        print("❌ FIREWORKS_API_KEY not configured")
        return False

def test_opendeepsearch():
    """Test OpenDeepSearch functionality"""
    print("\n🤖 Testing OpenDeepSearch")
    print("-" * 40)
    
    api_key = os.getenv("FIREWORKS_API_KEY", "")
    if not api_key or api_key == "your_fireworks_api_key_here":
        print("❌ Cannot test - API key not configured")
        return False
    
    try:
        from opendeepsearch.agent import ReasoningAgent
        
        model = "accounts/sentientfoundation/models/dobby-unhinged-llama-3-3-70b-new"
        agent = ReasoningAgent(model=model)
        
        # Simple test
        response = agent.run("Say 'Hello World' in exactly two words.")
        print(f"✅ OpenDeepSearch Test Response: {response[:50]}...")
        return True
        
    except Exception as e:
        print(f"❌ OpenDeepSearch Test Failed: {e}")
        return False

def test_chat_agent():
    """Test ChatAgent"""
    print("\n💬 Testing ChatAgent")
    print("-" * 40)
    
    try:
        from chat_agent import ChatAgent
        
        agent = ChatAgent()
        response = agent.simple_chat("Hello, test message")
        print(f"✅ ChatAgent: {response[:50]}...")
        return True
        
    except Exception as e:
        print(f"❌ ChatAgent Failed: {e}")
        return False

def test_news_agent():
    """Test NewsAgent"""
    print("\n📰 Testing NewsAgent")  
    print("-" * 40)
    
    try:
        from news_agent import NewsAgent
        
        agent = NewsAgent(model="accounts/sentientfoundation/models/dobby-unhinged-llama-3-3-70b-new")
        feeds = ["https://www.coindesk.com/arc/outboundfeeds/rss/"]
        articles = agent.get_news(feeds, limit=2)
        
        print(f"✅ NewsAgent: Fetched {len(articles)} articles")
        return True
        
    except Exception as e:
        print(f"❌ NewsAgent Failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🔬 COMPREHENSIVE DEPENDENCY TEST")
    print("=" * 50)
    
    # Test sequence
    tests = [
        ("Basic Imports", test_basic_imports),
        ("API Key", test_api_key), 
        ("OpenDeepSearch", test_opendeepsearch),
        ("ChatAgent", test_chat_agent),
        ("NewsAgent", test_news_agent),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST SUMMARY")
    print("=" * 50)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:20} {status}")
    
    all_passed = all(results.values())
    print(f"\n🏁 Overall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    if not all_passed:
        print("\n💡 Next steps:")
        if not results.get("Basic Imports", False):
            print("   1. Install PyTorch: pip install torch")
            print("   2. Install OpenDeepSearch: pip install git+https://github.com/sentient-agi/OpenDeepSearch.git")
        if not results.get("API Key", False):
            print("   3. Configure FIREWORKS_API_KEY in .env file")

if __name__ == "__main__":
    main()
