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

# Task routing: 
# - Pub/Sub notifications go to 'pubsub_notifications' queue (high priority, instant processing)
# - Regular email sync tasks go to 'email_sync' queue
celery.conf.task_routes = {
    'tasks.sync_user_emails': {'queue': 'email_sync'},
    'tasks.classify_email_task': {'queue': 'email_sync'},
    'tasks.send_whatsapp_followups': {'queue': 'email_sync'},
    'tasks.generate_scheduled_email': {'queue': 'email_sync'},
    'tasks.send_scheduled_emails': {'queue': 'email_sync'},
    'tasks.process_pubsub_notification': {'queue': 'pubsub_notifications'},
}

# Periodic tasks (Celery Beat schedule)
from celery.schedules import crontab
celery.conf.beat_schedule = {
    # Note: Email sync is handled by Pub/Sub push notifications, not periodic polling
    # 'periodic-email-sync' removed - using Pub/Sub webhook instead
    'send-whatsapp-followups': {
        'task': 'tasks.send_whatsapp_followups',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes (checks if 6 hours passed)
    },
    'send-scheduled-emails': {
        'task': 'tasks.send_scheduled_emails',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes (sends scheduled emails that are due)
    },
}
celery.conf.timezone = 'UTC'

# Task time limits
celery.conf.task_time_limit = 600  # 10 minutes max per task
celery.conf.task_soft_time_limit = 540  # 9 minutes soft limit

# Result expiration (clean up old results)
celery.conf.result_expires = 3600  # 1 hour

# Keep worker alive and prevent premature shutdowns
celery.conf.worker_max_tasks_per_child = 1000  # Restart worker after 1000 tasks (prevents memory leaks)
celery.conf.broker_connection_retry = True  # Retry broker connections
celery.conf.broker_connection_retry_on_startup = True  # Retry on startup (for Railway)
celery.conf.broker_connection_max_retries = 10  # Max retries
celery.conf.worker_disable_rate_limits = False  # Keep rate limiting enabled
celery.conf.worker_send_task_events = True  # Send task events for monitoring

# Railway-specific: Keep worker alive even when idle
celery.conf.worker_pool_restarts = True  # Allow pool restarts
celery.conf.worker_hijack_root_logger = False  # Don't hijack root logger (prevents Railway from thinking worker is dead)
celery.conf.worker_log_format = '[%(asctime)s: %(levelname)s/%(processName)s] %(message)s'
celery.conf.worker_task_log_format = '[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s'

# Import tasks to register them with Celery
# This ensures tasks are available when the worker starts
try:
    import tasks  # noqa: F401
    print("✅ Tasks module imported successfully")
except ImportError as e:
    print(f"⚠️  Warning: Could not import tasks module: {e}")
    import traceback
    traceback.print_exc()

# Validate Redis connection on startup (optional - won't fail if redis not installed)
try:
    import redis
    from urllib.parse import urlparse
    parsed = urlparse(redis_url)
    redis_client = redis.from_url(redis_url, socket_connect_timeout=5)
    redis_client.ping()
    print(f"✅ Redis connection validated: {parsed.hostname}:{parsed.port}")
except ImportError:
    # Redis library not installed - that's okay, Celery will handle it
    pass
except Exception as e:
    print(f"⚠️  Warning: Could not connect to Redis: {e}")
    print(f"   Redis URL: {redis_url.split('@')[-1] if '@' in redis_url else redis_url}")
    print(f"   This may cause the worker to fail. Check REDIS_URL environment variable.")

print(f"✅ Celery configured with broker: {redis_url.split('@')[-1] if '@' in redis_url else redis_url}")

