web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 300 --worker-class sync --threads 2
worker: celery -A celery_config worker --loglevel=info --concurrency=10 --queues=email_sync --max-tasks-per-child=1000 --without-gossip --without-mingle --without-heartbeat

