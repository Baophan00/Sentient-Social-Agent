#!/bin/bash

echo "🔍 Checking dependencies..."

# 1. Kiểm tra Python packages
echo "📦 Python packages:"
python -c "import flask; print('✅ Flask installed')" 2>/dev/null || echo "❌ Flask missing - run: pip install flask"
python -c "import flask_cors; print('✅ Flask-CORS installed')" 2>/dev/null || echo "❌ Flask-CORS missing - run: pip install flask-cors"
python -c "import feedparser; print('✅ feedparser installed')" 2>/dev/null || echo "❌ feedparser missing - run: pip install feedparser"
python -c "import dotenv; print('✅ python-dotenv installed')" 2>/dev/null || echo "❌ python-dotenv missing - run: pip install python-dotenv"

# 2. Kiểm tra OpenDeepSearch
echo ""
echo "🧠 AI packages:"
python -c "import opendeepsearch; print('✅ OpenDeepSearch installed')" 2>/dev/null || echo "❌ OpenDeepSearch missing - run: pip install git+https://github.com/sentient-agi/OpenDeepSearch.git"

# 3. Kiểm tra Sentient Agent Framework
python -c "import sentient_agent_framework; print('✅ Sentient-Agent-Framework installed')" 2>/dev/null || echo "❌ Sentient-Agent-Framework missing - run: pip install git+https://github.com/sentient-agi/Sentient-Agent-Framework.git"

# 4. Kiểm tra .env file
echo ""
echo "⚙️ Configuration:"
if [ -f ".env" ]; then
    if grep -q "FIREWORKS_API_KEY=" .env && [ "$(grep FIREWORKS_API_KEY= .env | cut -d'=' -f2)" != "" ]; then
        echo "✅ FIREWORKS_API_KEY configured"
    else
        echo "❌ FIREWORKS_API_KEY missing or empty in .env"
    fi
else
    echo "❌ .env file missing"
fi

echo ""
echo "🏁 Check complete!"
