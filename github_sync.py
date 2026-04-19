import os
import base64
import requests
import sqlite3
from datetime import datetime

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
REPO_NAME = "Reaksa566/Stock_Ford_Extension_SR_3"
DB_PATH = "stock_data.db"
GITHUB_API_URL = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_PATH}"

def is_valid_database(filepath):
    """Check if file is a valid SQLite database"""
    if not os.path.exists(filepath):
        return False
    
    try:
        # Check SQLite magic header
        with open(filepath, 'rb') as f:
            header = f.read(16)
            if header[:16] != b'SQLite format 3\x00':
                print(f"⚠️ Invalid database header")
                return False
        
        # Try to open and query
        conn = sqlite3.connect(filepath)
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM sqlite_master WHERE type="table" LIMIT 1')
        cursor.fetchone()
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️ Database validation failed: {e}")
        return False

def sync_db_to_github():
    """Upload database to GitHub with proper SHA handling"""
    if not GITHUB_TOKEN:
        print("⚠️ No GitHub token found, skipping sync")
        return False
    
    if not os.path.exists(DB_PATH):
        print("⚠️ Database file not found, skipping sync")
        return False
    
    # Validate database before uploading
    if not is_valid_database(DB_PATH):
        print("⚠️ Local database is corrupted, skipping sync")
        return False
    
    try:
        with open(DB_PATH, 'rb') as f:
            content = f.read()
        
        if len(content) == 0:
            print("⚠️ Database is empty (0 bytes), skipping sync")
            return False
        
        encoded_content = base64.b64encode(content).decode('utf-8')
        
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # First, check if file exists to get the current SHA
        print("🔍 Checking existing file on GitHub...")
        response = requests.get(GITHUB_API_URL, headers=headers)
        
        payload = {
            'message': f'Auto-sync database from Render - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            'content': encoded_content,
            'branch': 'main'
        }
        
        if response.status_code == 200:
            # File exists, get SHA for update
            current_data = response.json()
            payload['sha'] = current_data['sha']
            print(f"📝 Updating existing database (SHA: {current_data['sha'][:7]}...)")
            
            # Optional: Prevent data loss by comparing sizes
            if current_data.get('size', 0) > len(content):
                print(f"⚠️ Warning: GitHub version ({current_data['size']} bytes) is larger than local ({len(content)} bytes)")
                print("⚠️ This might indicate data loss. Set force=True to override.")
                # Comment the next line if you want to allow overwriting
                return False
                
        elif response.status_code == 404:
            print("📝 Creating new database file on GitHub")
        else:
            print(f"❌ Error checking file: {response.status_code}")
            return False
        
        # Upload the file
        print("📤 Uploading to GitHub...")
        response = requests.put(GITHUB_API_URL, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            print(f"✅ Database synced to GitHub successfully! ({len(content)} bytes)")
            return True
        else:
            print(f"❌ GitHub API error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error syncing to GitHub: {e}")
        return False

def sync_db_from_github():
    """Download database from GitHub only if valid"""
    if not GITHUB_TOKEN:
        print("⚠️ No GitHub token found, using local database")
        return False
    
    try:
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        print("🔍 Checking for existing database on GitHub...")
        response = requests.get(GITHUB_API_URL, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            content = base64.b64decode(data['content'])
            
            if len(content) == 0:
                print("⚠️ GitHub database is empty (0 bytes), ignoring")
                return False
            
            print(f"📥 Downloaded {len(content)} bytes from GitHub")
            
            # Save to temp file for validation
            temp_path = DB_PATH + '.temp'
            with open(temp_path, 'wb') as f:
                f.write(content)
            
            # Validate the downloaded database
            if is_valid_database(temp_path):
                # Backup current database if it exists and is valid
                if os.path.exists(DB_PATH) and is_valid_database(DB_PATH):
                    backup_path = f"{DB_PATH}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    os.rename(DB_PATH, backup_path)
                    print(f"📦 Backed up current database to {backup_path}")
                elif os.path.exists(DB_PATH):
                    # Current is corrupted, just remove it
                    os.remove(DB_PATH)
                    print("🗑️ Removed corrupted local database")
                
                # Replace with downloaded version
                os.rename(temp_path, DB_PATH)
                print(f"✅ Valid database downloaded from GitHub! ({len(content)} bytes)")
                return True
            else:
                print("⚠️ Downloaded database is corrupted, keeping current database")
                os.remove(temp_path)
                return False
                
        elif response.status_code == 404:
            print("ℹ️ No database file found on GitHub, will create new one")
            return False
        else:
            print(f"❌ GitHub API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error downloading from GitHub: {e}")
        return False

def get_github_db_info():
    """Get information about database on GitHub without downloading"""
    if not GITHUB_TOKEN:
        return None
    
    try:
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        response = requests.get(GITHUB_API_URL, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            return {
                'size': data['size'],
                'sha': data['sha'][:7],
                'last_modified': data.get('last_modified', 'Unknown'),
                'download_url': data.get('download_url')
            }
        else:
            return None
    except Exception as e:
        print(f"❌ Error getting GitHub info: {e}")
        return None