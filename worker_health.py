#!/usr/bin/env python3
"""
Simple HTTP health check server for Celery worker on Railway.
This keeps the worker container alive by providing an HTTP endpoint.
Railway stops containers that don't have HTTP activity, so this prevents that.
"""
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import subprocess
import multiprocessing

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "healthy", "service": "celery-worker"}')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress default logging to reduce noise
        pass

def start_health_server():
    """Start a simple HTTP server for health checks"""
    port = int(os.getenv('PORT', '8080'))
    try:
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        print(f"✅ Health check server started on port {port}")
        server.serve_forever()
    except Exception as e:
        print(f"❌ Health server error: {e}")
        sys.exit(1)

def run_celery_worker():
    """Run Celery worker in a separate process"""
    print("🚀 Starting Celery worker...")
    try:
        from celery_config import celery
        celery.worker_main([
            'worker',
            '--loglevel=info',
            '--concurrency=10',
            '--queues=email_sync',
            '--max-tasks-per-child=1000'
        ])
    except Exception as e:
        print(f"❌ Celery worker error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    # Start Celery worker in a separate process
    celery_process = multiprocessing.Process(target=run_celery_worker, daemon=False)
    celery_process.start()
    
    # Give Celery a moment to start
    import time
    time.sleep(2)
    
    # Run health server in main thread (this blocks and keeps container alive)
    print("✅ Health check server will run in main thread to keep container alive")
    start_health_server()  # This blocks forever

