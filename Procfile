web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 300 --worker-class sync --threads 2
worker: python worker_health.py
beat: celery -A celery_config beat --loglevel=info

