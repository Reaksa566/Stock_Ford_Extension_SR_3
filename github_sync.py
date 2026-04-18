import os
import base64
from github import Github, GithubException

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
REPO_NAME = "Reaksa566/Stock_Ford_Extension_SR_3"
DB_PATH = "stock_data.db"

def sync_db_to_github():
    if not GITHUB_TOKEN:
        print("⚠️ No GitHub token found, skipping sync")
        return False
    
    if not os.path.exists(DB_PATH):
        print("⚠️ Database file not found, skipping sync")
        return False
    
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        
        with open(DB_PATH, 'rb') as f:
            content = f.read()
        
        encoded_content = base64.b64encode(content).decode('utf-8')
        
        try:
            contents = repo.get_contents(DB_PATH)
            repo.update_file(DB_PATH, "Auto-sync database from Render", encoded_content, contents.sha, branch="main")
            print(f"✅ Database updated on GitHub successfully! ({len(content)} bytes)")
        except GithubException:
            repo.create_file(DB_PATH, "Auto-sync database from Render", encoded_content, branch="main")
            print(f"✅ Database created on GitHub successfully! ({len(content)} bytes)")
        
        return True
    except Exception as e:
        print(f"❌ Error syncing to GitHub: {e}")
        return False

def sync_db_from_github():
    if not GITHUB_TOKEN:
        print("⚠️ No GitHub token found, using local database")
        return False
    
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        
        try:
            contents = repo.get_contents(DB_PATH)
            decoded_content = base64.b64decode(contents.content)
            
            with open(DB_PATH, 'wb') as f:
                f.write(decoded_content)
            
            print(f"✅ Database downloaded from GitHub successfully! ({len(decoded_content)} bytes)")
            return True
        except GithubException:
            print("ℹ️ No database file found on GitHub, will create new one")
            return False
    except Exception as e:
        print(f"❌ Error downloading from GitHub: {e}")
        return False