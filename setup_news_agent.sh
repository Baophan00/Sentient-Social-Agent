#!/bin/bash

# setup_news_agent.sh
# Automated setup script for Sentient News Agent

echo "🤖 Sentient News Agent Setup Script"
echo "===================================="

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo "❌ Git is not installed. Please install git first."
    exit 1
fi

# Check if python3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed. Please install Python 3.8+ first."
    exit 1
fi

echo "✅ Prerequisites check passed"

# Step 1: Clone Sentient Social Agent
echo "📥 Step 1: Cloning Sentient Social Agent..."
if [ -d "Sentient-Social-Agent" ]; then
    echo "⚠️  Directory already exists. Removing old version..."
    rm -rf Sentient-Social-Agent
fi

git clone https://github.com/sentient-agi/Sentient-Social-Agent.git
cd Sentient-Social-Agent

echo "✅ Repository cloned successfully"

# Step 2: Setup Python environment
echo "🐍 Step 2: Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate

# Install base requirements
pip install -r requirements.txt

# Install news tool requirements
pip install feedparser beautifulsoup4 python-dateutil schedule

echo "✅ Python environment setup complete"

# Step 3: Create news tool directory structure
echo "📁 Step 3: Creating news tool structure..."
mkdir -p src/agent/agent_tools/news

# Create __init__.py
cat > src/agent/agent_tools/news/__init__.py << 'EOF'
from .news import News
from .news_config import NewsConfig

__all__ = ['News', 'NewsConfig']
EOF

echo "✅ Directory structure created"

# Step 4: Create configuration files
echo "⚙️  Step 4: Setting up configuration..."

# Create .env from template
if [ ! -f .env ]; then
    cp .env.example .env
    echo "📝 .env file created from template"
else
    echo "⚠️  .env file already exists, skipping..."
fi

# Update agent_config.py
echo "📝 Updating agent_config.py..."
if ! grep -q "NEWS_ENABLED" src/agent/agent_config.py; then
    cat >> src/agent/agent_config.py << 'EOF'

# News Tool Configuration
NEWS_ENABLED = True
EOF
    echo "✅ agent_config.py updated"
else
    echo "⚠️  NEWS_ENABLED already exists in agent_config.py"
fi

# Step 5: Create test script
echo "🧪 Step 5: Creating test script..."
cat > test_news_agent.py << 'EOF'
# Copy the test script content from the artifact above
# This is a placeholder - you'll need to copy the actual test script
print("Test script created - please copy the test script code from the artifacts")
EOF

echo "✅ Test script created"

# Step 6: Setup instructions
echo ""
echo "🎉 Setup Complete!"
echo "=================="
echo ""
echo "📋 Next Steps:"
echo "1. Copy the news tool code files from the artifacts to:"
echo "   - src/agent/agent_tools/news/news.py"
echo "   - src/agent/agent_tools/news/news_config.py"
echo ""
echo "2. Edit your .env file with your API keys:"
echo "   nano .env"
echo ""
echo "3. Required API keys:"
echo "   - FIREWORKS_API_KEY (required for AI features)"
echo "   - NEWS_API_KEY (optional, get from newsapi.org)"
echo "   - Twitter API credentials (for posting)"
echo ""
echo "4. Test your setup:"
echo "   python3 test_news_agent.py"
echo ""
echo "5. Run the agent:"
echo "   python3 -m src.agent"
echo ""
echo "🔗 Useful links:"
echo "   - NewsAPI: https://newsapi.org"
echo "   - Fireworks AI: https://fireworks.ai"
echo "   - Twitter Developer: https://developer.twitter.com"
echo ""
echo "💬 Need help? Check the README.md in the news tool directory"

# Make script executable
chmod +x setup_news_agent.sh

echo ""
echo "✨ Ready to build your News Agent! ✨"