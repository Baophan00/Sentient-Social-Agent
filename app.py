# from flask import Flask, render_template, jsonify, request
# from src.agent.agent_tools.news import News
# from dotenv import load_dotenv
# import logging
# import os

# # Load environment variables
# load_dotenv()

# # Setup Flask app
# app = Flask(__name__)

# # Setup basic logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# def get_news_agent():
#     """Initialize and return news agent"""
#     try:
#         # Initialize without Twitter client for web interface
#         return News({}, None)
#     except Exception as e:
#         logger.error(f"Error initializing news agent: {e}")
#         return None

# class ChatAgent:
#     def __init__(self):
#         self.api_key = os.getenv('FIREWORKS_API_KEY')
    
#     def chat(self, message, conversation_history=[]):
#         """Xử lý tin nhắn chat với AI"""
#         try:
#             import fireworks.client
#             from dotenv import load_dotenv
#             import os
            
#             load_dotenv()
#             api_key = os.getenv('FIREWORKS_API_KEY')
            
#             if not api_key or api_key == 'your_fireworks_api_key_here':
#                 return "Lỗi: Chưa cấu hình API key. Kiểm tra file .env"
            
#             fireworks.client.api_key = api_key
            
#             response = fireworks.client.ChatCompletion.create(
#                 model="accounts/fireworks/models/llama-v3-70b-instruct",
#                 messages=[
#                     {
#                         "role": "system", 
#                         "content": "Bạn là NewsBot - trợ lý ảo chuyên về tin tức công nghệ, tiền điện tử và AI."
#                     },
#                     *conversation_history,
#                     {"role": "user", "content": message}
#                 ],
#                 max_tokens=500,
#                 temperature=0.7,
#                 timeout=10
#             )
#             return response.choices[0].message.content
            
#         except ImportError:
#             return "Lỗi: Thư viện fireworks chưa được cài đặt. Chạy: 'pip install fireworks'"
#         except Exception as e:
#             return f"Lỗi kết nối AI: {str(e)}"

# @app.route('/')
# def index():
#     """Home page - display news articles"""
#     try:
#         news_agent = get_news_agent()
#         if news_agent:
#             articles = news_agent.get_latest_news()
#             logger.info(f"Found {len(articles)} articles for web display")
#             return render_template('index.html', 
#                                  articles=articles, 
#                                  total_articles=len(articles))
#         else:
#             return render_template('error.html', 
#                                  message="Failed to initialize news agent")
#     except Exception as e:
#         logger.error(f"Error in index route: {e}")
#         return render_template('error.html', 
#                              message=f"Error loading news: {str(e)}")

# @app.route('/api/news')
# def api_news():
#     """API endpoint for news data (JSON)"""
#     try:
#         news_agent = get_news_agent()
#         if news_agent:
#             articles = news_agent.get_latest_news()
#             return jsonify({
#                 'status': 'success',
#                 'count': len(articles),
#                 'articles': articles
#             })
#         else:
#             return jsonify({
#                 'status': 'error',
#                 'message': 'News agent not available'
#             }), 500
#     except Exception as e:
#         return jsonify({
#             'status': 'error',
#             'message': str(e)
#         }), 500

# @app.route('/api/breaking')
# def api_breaking():
#     """API endpoint for breaking news only"""
#     try:
#         news_agent = get_news_agent()
#         if news_agent:
#             articles = news_agent.get_latest_news()
#             breaking_news = [article for article in articles 
#                            if 'breaking' in article.get('title', '').lower()]
#             return jsonify({
#                 'status': 'success',
#                 'count': len(breaking_news),
#                 'breaking_news': breaking_news
#             })
#         else:
#             return jsonify({
#                 'status': 'error',
#                 'message': 'News agent not available'
#             }), 500
#     except Exception as e:
#         return jsonify({
#             'status': 'error',
#             'message': str(e)
#         }), 500

# @app.route('/api/chat', methods=['POST'])
# def api_chat():
#     """API endpoint for chat with AI"""
#     try:
#         data = request.get_json()
#         message = data.get('message', '')
        
#         if not message:
#             return jsonify({
#                 'status': 'error',
#                 'message': 'No message provided'
#             }), 400
        
#         chat_agent = ChatAgent()
#         response = chat_agent.chat(message)
        
#         return jsonify({
#             'status': 'success',
#             'response': response
#         })
#     except Exception as e:
#         return jsonify({
#             'status': 'error',
#             'message': str(e)
#         }), 500

# @app.route('/chat')
# def chat_interface():
#     """Chat interface page"""
#     return render_template('chat.html')

# @app.route('/health')
# def health_check():
#     """Health check endpoint"""
#     return jsonify({
#         'status': 'healthy', 
#         'service': 'news_agent_web',
#         'features': ['news', 'chat', 'api']
#     })

# if __name__ == '__main__':
#     logger.info("Starting Sentient News Agent Web Interface...")
#     app.run(debug=True, host='0.0.0.0', port=3000)