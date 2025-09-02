import fireworks.client
import os
from dotenv import load_dotenv

load_dotenv()

class ChatAgent:
    def __init__(self):
        fireworks.client.api_key = os.getenv('FIREWORKS_API_KEY')
    
    def chat(self, message, conversation_history=[]):
        """Xử lý tin nhắn chat"""
        try:
            response = fireworks.client.ChatCompletion.create(
                model="accounts/fireworks/models/llama-v3-70b-instruct",
                messages=[
                    {"role": "system", "content": "Bạn là trợ lý ảo chuyên về tin tức công nghệ, tiền điện tử và AI."},
                    *conversation_history,
                    {"role": "user", "content": message}
                ],
                max_tokens=500,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Xin lỗi, tôi gặp lỗi: {str(e)}"