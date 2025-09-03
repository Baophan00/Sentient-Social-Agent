web: gunicorn web_server:app --workers 2 --threads 4 --bind 0.0.0.0:$PORT
worker: python news_runner.py --loop --max-posts 1
