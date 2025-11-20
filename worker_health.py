#!/usr/bin/env python3
"""
Simple HTTP health check server for Celery worker on Railway.
This keeps the worker container alive by providing an HTTP endpoint.
"""
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

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
        # Suppress default logging
        pass

def start_health_server():
    """Start a simple HTTP server for health checks"""
    port = int(os.getenv('PORT', '8080'))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"✅ Health check server started on port {port}")
    server.serve_forever()

if __name__ == '__main__':
    # Start health server in a separate thread
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Import and start Celery worker
    from celery_config import celery
    celery.worker_main(['worker', '--loglevel=info', '--concurrency=10', '--queues=email_sync', '--max-tasks-per-child=1000'])

