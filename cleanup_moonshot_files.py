#!/usr/bin/env python3
"""
Cleanup script to delete old files from Moonshot API to stay under 1000 file limit.
Run this periodically or add to cron job.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

MOONSHOT_API_KEY = os.getenv('MOONSHOT_API_KEY')
MOONSHOT_BASE_URL = "https://api.moonshot.cn/v1"

def list_files():
    """List all uploaded files"""
    headers = {
        "Authorization": f"Bearer {MOONSHOT_API_KEY}"
    }
    
    response = requests.get(
        f"{MOONSHOT_BASE_URL}/files",
        headers=headers
    )
    
    if response.status_code == 200:
        files = response.json().get('data', [])
        print(f"📁 Found {len(files)} files in Moonshot")
        return files
    else:
        print(f"❌ Error listing files: {response.text}")
        return []

def delete_file(file_id):
    """Delete a specific file"""
    headers = {
        "Authorization": f"Bearer {MOONSHOT_API_KEY}"
    }
    
    response = requests.delete(
        f"{MOONSHOT_BASE_URL}/files/{file_id}",
        headers=headers
    )
    
    return response.status_code == 200

def cleanup_old_files(keep_count=100):
    """Keep only the most recent files, delete the rest"""
    files = list_files()
    
    if len(files) <= keep_count:
        print(f"✅ Only {len(files)} files exist, no cleanup needed")
        return
    
    # Sort by creation time (oldest first)
    files.sort(key=lambda x: x.get('created_at', 0))
    
    # Delete oldest files
    files_to_delete = files[:-keep_count]  # Keep last 'keep_count' files
    
    print(f"🗑️  Deleting {len(files_to_delete)} old files...")
    
    deleted_count = 0
    for file in files_to_delete:
        file_id = file.get('id')
        filename = file.get('filename', 'unknown')
        
        if delete_file(file_id):
            deleted_count += 1
            if deleted_count % 10 == 0:
                print(f"  Deleted {deleted_count}/{len(files_to_delete)} files...")
        else:
            print(f"  ❌ Failed to delete: {filename}")
    
    print(f"✅ Cleanup complete! Deleted {deleted_count} files, kept {keep_count}")

if __name__ == "__main__":
    print("🧹 Starting Moonshot file cleanup...")
    cleanup_old_files(keep_count=100)  # Keep only 100 most recent files

