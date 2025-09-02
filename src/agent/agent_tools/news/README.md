# News Tool for Sentient Social Agent

A comprehensive news aggregation and distribution tool that fetches, processes, and shares news across multiple platforms.

## 🚀 Features

- **Multi-source aggregation**: RSS feeds + NewsAPI integration
- **Smart deduplication**: Prevents duplicate news posts
- **Breaking news detection**: Automatic priority scoring
- **AI-powered summarization**: Engaging social media posts
- **Multi-platform support**: Twitter, Discord, Sentient Chat
- **Category filtering**: Tech, Crypto, AI, Finance, General
- **Persistent state**: Remembers processed articles

## 📋 Requirements

### Python Dependencies

```bash
pip install feedparser requests beautifulsoup4 python-dateutil
```

### API Keys Required

- **NewsAPI** (optional): Free tier at [newsapi.org](https://newsapi.org)
- **Fireworks AI** (for summarization): Get from [fireworks.ai](https://fireworks.ai)

### Social Platform Credentials

- **Twitter Developer Account**: [developer.twitter.com](https://developer.twitter.com)
- **Discord Bot** (optional): [discord.com/developers](https://discord.com/developers)

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# News Sources
NEWS_API_KEY=your_newsapi_key_here

# AI Model
FIREWORKS_API_KEY=your_fireworks_key

# Enable news tool
NEWS_ENABLED=True

# Twitter (required for posting)
TWITTER_CONSUMER_KEY=your_consumer_key
TWITTER_CONSUMER_SECRET=your_consumer_secret
TWITTER_ACCESS_TOKEN=your_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret
TWITTER_BEARER_TOKEN=your_bearer_token

# Discord (optional)
DISCORD_TOKEN=your_discord_bot_token
```

### Agent Configuration

Add to `src/agent/agent_config.py`:

```python
NEWS_ENABLED = True
```

## 🔧 Customization

### Adding News Categories

Edit `news_config.py`:

```python
self.categories = ['tech', 'crypto', 'ai', 'your_category']

# Add RSS feeds for your category
self.rss_feeds['your_category'] = [
    'https://example.com/feed.xml'
]
```

### Adjusting Update Frequency

```python
self.update_interval = 1800  # 30 minutes
```

### Customizing Breaking News Detection

```python
self.breaking_keywords = [
    'your_keywords', 'important_terms'
]

# Adjust breaking news threshold
self.breaking_news_threshold = 2  # Minimum score to qualify
```

### Adding Custom RSS Feeds

```python
# In news_config.py
self.rss_feeds['your_topic'] = [
    'https://your-source.com/rss',
    'https://another-source.com/feed.xml'
]
```

## 🏃‍♂️ Quick Start

### 1. Setup Environment

```bash
# Clone Sentient Social Agent
git clone https://github.com/sentient-agi/Sentient-Social-Agent
cd Sentient-Social-Agent

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install feedparser beautifulsoup4 python-dateutil
```

### 2. Add News Tool Files

Create the news tool directory and copy these files:

```bash
mkdir -p src/agent/agent_tools/news
# Copy news.py, news_config.py, __init__.py to this directory
```

### 3. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your API keys
nano .env
```

### 4. Enable News Tool

Edit `src/agent/agent_config.py`:

```python
NEWS_ENABLED = True
```

### 5. Test News Tool

```bash
# Test news fetching
python3 -m src.agent.agent_tools.news

# Test full agent
python3 -m src.agent
```

## 📊 Usage Examples

### Manual Testing

```python
from src.agent.agent_tools.news import News

# Initialize
secrets = {'NEWS_API_KEY': 'your_key'}
news_agent = News(secrets, None)

# Fetch latest tech news
articles = news_agent.fetch_rss_news('tech')
print(f"Found {len(articles)} articles")

# Create digest
digest = news_agent.create_news_digest(articles, 'discord')
print(digest)
```

### Integration with Sentient Chat

The news tool automatically integrates with the Sentient framework. Users can:

- Ask for latest news: "What's the latest tech news?"
- Request specific topics: "Show me crypto news"
- Get breaking news alerts automatically

## 📱 Platform-Specific Features

### Twitter Integration

- **Auto-posting**: Scheduled news tweets
- **Breaking alerts**: Immediate breaking news
- **Thread creation**: Long news summaries
- **Hashtag inclusion**: Relevant category hashtags

### Discord Integration

- **Rich embeds**: Formatted news cards
- **Channel targeting**: Different channels for different categories
- **Role mentions**: Alert specific user groups
- **Slash commands**: `/news tech`, `/news crypto`

### Sentient Chat Integration

- **Interactive format**: Clickable elements
- **Real-time updates**: Live news feed
- **User preferences**: Personalized news filtering
- **Context sharing**: Works with other agents

## 🔍 Advanced Features

### Breaking News Algorithm

1. **Keyword scoring**: Points for breaking news terms
2. **Source weighting**: Trusted sources get higher priority
3. **Recency bonus**: Newer articles score higher
4. **Engagement prediction**: Estimate user interest

### Content Quality Filters

- **Duplicate detection**: Title similarity matching
- **Spam filtering**: Remove promotional content
- **Relevance scoring**: Category-specific relevance
- **Length validation**: Minimum content requirements

### Performance Optimizations

- **Caching**: Store processed articles locally
- **Rate limiting**: Respect API limits
- **Async processing**: Non-blocking news fetching
- **Error recovery**: Graceful handling of failed sources

## 🐛 Troubleshooting

### Common Issues

**"No articles found"**

- Check RSS feed URLs are working
- Verify NewsAPI key if using
- Check internet connection

**"Rate limit exceeded"**

- Reduce update frequency in config
- Check API key quotas
- Implement exponential backoff

**"Articles not posting to Twitter"**

- Verify Twitter API credentials
- Check Twitter app permissions
- Ensure TWITTER_ENABLED=True in config

### Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📈 Analytics & Monitoring

### Built-in Metrics

- Articles processed per hour
- Breaking news detection rate
- Source success/failure rates
- User engagement metrics

### Monitoring Commands

```bash
# Check processed articles
cat processed_articles.json

# View logs
tail -f agent.log

# Test specific category
python3 -c "from src.agent.agent_tools.news import News; n=News({}, None); print(len(n.fetch_rss_news('crypto')))"
```

## 🔄 Maintenance

### Daily Tasks

- Monitor error logs
- Check API quotas
- Verify RSS feed health

### Weekly Tasks

- Clean processed articles file
- Update source priorities
- Review breaking news accuracy

### Monthly Tasks

- Add new RSS sources
- Update breaking keywords
- Performance optimization

## 🎯 Roadmap

### Phase 1 (Current)

- [x] Basic RSS aggregation
- [x] Twitter integration
- [x] Breaking news detection
- [x] Multi-category support

### Phase 2 (Next)

- [ ] AI-powered summarization
- [ ] User preference learning
- [ ] Real-time WebSocket updates
- [ ] Advanced analytics dashboard

### Phase 3 (Future)

- [ ] Multi-language support
- [ ] Custom source suggestions
- [ ] Sentiment-based filtering
- [ ] Integration with Sentient marketplace

## 💰 Monetization Opportunities

1. **Premium Subscriptions**

   - Faster updates (every 15 minutes)
   - Custom categories
   - Priority breaking news
   - Advanced filtering

2. **Enterprise Features**

   - Custom RSS sources
   - White-label deployment
   - Advanced analytics
   - API access

3. **Sponsored Content**
   - Clearly marked paid placements
   - Relevant industry partnerships
   - Native advertising integration

## 🤝 Contributing

This news tool follows Sentient's open-source philosophy. Contributions welcome:

1. **Fork the repository**
2. **Create feature branch**
3. **Add your improvements**
4. **Submit pull request**

Areas for contribution:

- New news sources
- Better summarization algorithms
- Additional platforms (Telegram, LinkedIn)
- Performance optimizations
- UI improvements

## 📞 Support

For issues or questions:

- Create GitHub issue
- Contact: [Sentient Support](mailto:contact@sentient.xyz)
- Join Discord community

---

**Ready to build the future of AI-powered news?** 🚀
