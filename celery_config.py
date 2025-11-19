"""
Celery configuration for background email processing
"""
import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# Create Celery instance
celery = Celery('gmail_sync')

# Redis URL from environment (Railway provides REDIS_URL)
redis_url = os.getenv('REDIS_URL', os.getenv('REDISCLOUD_URL', 'redis://localhost:6379/0'))

# Configure Celery
celery.conf.broker_url = redis_url
celery.conf.result_backend = redis_url
celery.conf.task_serializer = 'json'
celery.conf.accept_content = ['json']
celery.conf.result_serializer = 'json'
celery.conf.timezone = 'UTC'
celery.conf.enable_utc = True

# Task settings
celery.conf.task_acks_late = True  # Acknowledge after task completes
celery.conf.worker_prefetch_multiplier = 1  # Process one task at a time per worker (prevents rate limit conflicts)
celery.conf.task_reject_on_worker_lost = True  # Re-queue if worker dies

# Rate limiting: Max 10 concurrent tasks across all workers
celery.conf.worker_concurrency = 10

# Task routing: All email sync tasks go to 'email_sync' queue
celery.conf.task_routes = {
    'tasks.sync_user_emails': {'queue': 'email_sync'},
    'tasks.classify_email_task': {'queue': 'email_sync'},
}

# Task time limits
celery.conf.task_time_limit = 600  # 10 minutes max per task
celery.conf.task_soft_time_limit = 540  # 9 minutes soft limit

# Result expiration (clean up old results)
celery.conf.result_expires = 3600  # 1 hour

print(f"✅ Celery configured with broker: {redis_url.split('@')[-1] if '@' in redis_url else redis_url}")

