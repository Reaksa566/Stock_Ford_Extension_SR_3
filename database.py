from github_sync import sync_db_to_github, sync_db_from_github
import sqlite3
import os
from datetime import datetime
import hashlib
import base64
import requests

DB_PATH = 'stock_data.db'
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
REPO_NAME = "Reaksa566/Stock_Ford_Extension_SR_3"
GITHUB_API_URL = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_PATH}"

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def is_valid_database(filepath):
    """Check if file is a valid SQLite database"""
    if not os.path.exists(filepath):
        return False
    
    try:
        # Check magic bytes
        with open(filepath, 'rb') as f:
            header = f.read(16)
            if header[:16] != b'SQLite format 3\x00':
                print(f"⚠️ Invalid database header: {header[:16]}")
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

def download_valid_db_from_github():
    """Download database only if it's valid and non-zero"""
    if not GITHUB_TOKEN:
        print("⚠️ No GitHub token found, skipping download")
        return False
    
    try:
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        response = requests.get(GITHUB_API_URL, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            content = base64.b64decode(data['content'])
            
            if len(content) == 0:
                print("⚠️ GitHub database is empty (0 bytes), ignoring")
                return False
            
            # Save to temp file for validation
            temp_path = DB_PATH + '.temp'
            with open(temp_path, 'wb') as f:
                f.write(content)
            
            if is_valid_database(temp_path):
                # Replace current database with valid one
                if os.path.exists(DB_PATH):
                    # Backup current database
                    backup_path = f"{DB_PATH}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    os.rename(DB_PATH, backup_path)
                    print(f"📦 Backed up current database to {backup_path}")
                
                os.rename(temp_path, DB_PATH)
                print(f"✅ Valid database downloaded: {len(content)} bytes")
                return True
            else:
                print("⚠️ Downloaded database is corrupted, keeping current")
                os.remove(temp_path)
                return False
        elif response.status_code == 404:
            print("ℹ️ No database file on GitHub yet")
            return False
        else:
            print(f"❌ GitHub API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error downloading from GitHub: {e}")
        return False

def upload_db_to_github_with_sha():
    """Upload database with proper SHA handling"""
    if not GITHUB_TOKEN:
        print("⚠️ No GitHub token found, skipping sync")
        return False
    
    if not os.path.exists(DB_PATH):
        print("⚠️ Database file not found, skipping sync")
        return False
    
    if not is_valid_database(DB_PATH):
        print("⚠️ Local database is corrupted, skipping sync")
        return False
    
    try:
        with open(DB_PATH, 'rb') as f:
            content = f.read()
        
        if len(content) == 0:
            print("⚠️ Database is empty, skipping sync")
            return False
        
        encoded_content = base64.b64encode(content).decode('utf-8')
        
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # First, check if file exists to get SHA
        response = requests.get(GITHUB_API_URL, headers=headers)
        
        payload = {
            'message': f'Auto-sync database from Render - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            'content': encoded_content,
            'branch': 'main'
        }
        
        if response.status_code == 200:
            # File exists, update with SHA
            current_data = response.json()
            payload['sha'] = current_data['sha']
            print("📝 Updating existing database file on GitHub")
            
            # Make sure we don't overwrite with older data
            if current_data.get('size', 0) > len(content):
                print(f"⚠️ GitHub database ({current_data['size']} bytes) is larger than local ({len(content)} bytes)")
                print("⚠️ This might indicate data loss! Skipping sync to preserve GitHub data.")
                return False
            
        else:
            print("📝 Creating new database file on GitHub")
        
        # Upload
        if payload.get('sha') or response.status_code == 404:
            response = requests.put(GITHUB_API_URL, headers=headers, json=payload)
            
            if response.status_code in [200, 201]:
                print(f"✅ Database synced to GitHub successfully! ({len(content)} bytes)")
                return True
            else:
                print(f"❌ GitHub API error: {response.status_code} - {response.text}")
                return False
        else:
            return False
            
    except Exception as e:
        print(f"❌ Error syncing to GitHub: {e}")
        return False

def init_db():
    """Initialize database with proper validation and backup"""
    print("=" * 50)
    print("🔄 Initializing Database...")
    
    # Check if local database exists and is valid
    if os.path.exists(DB_PATH):
        if is_valid_database(DB_PATH):
            print("✅ Existing valid database found")
            
            # Get database info
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM items")
            item_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            conn.close()
            
            print(f"📊 Database contains: {item_count} items, {user_count} users")
            
            # Ask if we should sync with GitHub (optional)
            if GITHUB_TOKEN:
                print("🔄 Syncing with GitHub...")
                download_valid_db_from_github()
            
            return
    
    # If no valid local database, try to download from GitHub
    print("📥 No valid local database found, checking GitHub...")
    if download_valid_db_from_github():
        print("✅ Database restored from GitHub")
        return
    
    # Create new database as last resort
    print("🆕 Creating new database...")
    create_fresh_database()

def create_fresh_database():
    """Create a brand new database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Enable WAL mode for better concurrent performance
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA synchronous=NORMAL')
    cursor.execute('PRAGMA cache_size=-20000')  # 20MB cache
    cursor.execute('PRAGMA temp_store=MEMORY')
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Create items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            unit TEXT NOT NULL,
            stock_in INTEGER DEFAULT 0,
            stock_out INTEGER DEFAULT 0,
            category_id INTEGER,
            type TEXT DEFAULT 'accessory',
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')
    
    # Create activities table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            item_name TEXT,
            action TEXT,
            quantity INTEGER,
            notes TEXT,
            date TEXT,
            time TEXT,
            FOREIGN KEY (item_id) REFERENCES items (id)
        )
    ''')
    
    # Create indexes for faster queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_category ON items(category_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_type ON items(type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_description ON items(description)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_category_type ON items(category_id, type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_items_stock ON items(stock_in, stock_out)')
    
    # Create default admin user
    cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('admin',))
    admin_exists = cursor.fetchone()[0]
    
    if admin_exists == 0:
        default_password = hash_password('admin123')
        cursor.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', 
                      ('admin', default_password, 'admin'))
        print("✅ Default admin user created: username='admin', password='admin123'")
    
    # Create default categories
    cursor.execute('SELECT COUNT(*) FROM categories')
    count = cursor.fetchone()[0]
    
    if count == 0:
        default_categories = ['LV', 'ELV', 'MVAC', 'Plumbing', 'Fire Fighting', 'Air Compressor']
        for cat in default_categories:
            try:
                cursor.execute('INSERT INTO categories (name) VALUES (?)', (cat,))
            except sqlite3.IntegrityError:
                pass
        print(f"✅ Created {len(default_categories)} default categories")
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")

# Replace old sync functions with new ones
def sync_db_to_github():
    """Wrapper for the new upload function"""
    return upload_db_to_github_with_sha()

def sync_db_from_github():
    """Wrapper for the new download function"""
    return download_valid_db_from_github()

# Rest of your existing functions remain the same
def authenticate_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    hashed_password = hash_password(password)
    cursor.execute('SELECT id, username, role FROM users WHERE username = ? AND password = ?', 
                  (username, hashed_password))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {'id': user[0], 'username': user[1], 'role': user[2]}
    return None

def add_user(username, password, role='user'):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        hashed_password = hash_password(password)
        cursor.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', 
                      (username, hashed_password, role))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def get_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, role, created_at FROM users')
    users = cursor.fetchall()
    conn.close()
    return [{'id': u[0], 'username': u[1], 'role': u[2], 'created_at': u[3]} for u in users]

def delete_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE id = ? AND username != ?', (user_id, 'admin'))
    conn.commit()
    conn.close()

def get_categories():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM categories ORDER BY name')
    categories = cursor.fetchall()
    conn.close()
    return [{'id': cat[0], 'name': cat[1]} for cat in categories]

def add_category(name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO categories (name) VALUES (?)', (name,))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def get_items():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT items.id, items.description, items.unit, items.stock_in, items.stock_out,
               categories.name as category_name, categories.id as category_id, items.type
        FROM items 
        LEFT JOIN categories ON items.category_id = categories.id
        ORDER BY items.id
    ''')
    items = cursor.fetchall()
    conn.close()
    result = []
    for item in items:
        result.append({
            'id': item[0],
            'description': item[1],
            'unit': item[2],
            'stock_in': item[3],
            'stock_out': item[4] if item[4] else 0,
            'total_stock': (item[3] - (item[4] if item[4] else 0)),
            'category': item[5],
            'category_id': item[6],
            'type': item[7] if item[7] else 'accessory'
        })
    return result

def add_item(description, unit, stock_in, category_id, item_type='accessory'):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO items (description, unit, stock_in, stock_out, category_id, type)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (description, unit, stock_in, 0, category_id, item_type))
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return item_id

def update_item(item_id, description, unit, category_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE items 
        SET description = ?, unit = ?, category_id = ?
        WHERE id = ?
    ''', (description, unit, category_id, item_id))
    conn.commit()
    conn.close()

def update_stock(item_id, quantity_change):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if quantity_change > 0:
        cursor.execute('UPDATE items SET stock_in = stock_in + ? WHERE id = ?', (quantity_change, item_id))
    else:
        cursor.execute('UPDATE items SET stock_out = stock_out + ? WHERE id = ?', (abs(quantity_change), item_id))
    
    conn.commit()
    conn.close()

def delete_item(item_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM activities WHERE item_id = ?', (item_id,))
    cursor.execute('DELETE FROM items WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

def get_item_stock(item_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT stock_in, stock_out FROM items WHERE id = ?', (item_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0] - result[1]
    return 0

def add_activity(item_id, item_name, action, quantity, notes=''):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now()
    cursor.execute('''
        INSERT INTO activities (item_id, item_name, action, quantity, notes, date, time)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (item_id, item_name, action, quantity, notes, now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S')))
    conn.commit()
    conn.close()

def get_activities(start_date=None, end_date=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if start_date and end_date:
        cursor.execute('''
            SELECT * FROM activities 
            WHERE date BETWEEN ? AND ? 
            ORDER BY date DESC, time DESC
        ''', (start_date, end_date))
    else:
        cursor.execute('SELECT * FROM activities ORDER BY date DESC, time DESC')
    
    activities = cursor.fetchall()
    conn.close()
    
    result = []
    for act in activities:
        result.append({
            'id': act[0],
            'item_id': act[1],
            'item_name': act[2],
            'action': act[3],
            'quantity': act[4],
            'notes': act[5],
            'date': act[6],
            'time': act[7]
        })
    return result

def get_items_by_type(item_type):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT items.id, items.description, items.unit, items.stock_in, items.stock_out,
               categories.name as category_name, categories.id as category_id
        FROM items 
        LEFT JOIN categories ON items.category_id = categories.id
        WHERE items.type = ?
        ORDER BY items.id
    ''', (item_type,))
    items = cursor.fetchall()
    conn.close()
    result = []
    for item in items:
        result.append({
            'id': item[0],
            'description': item[1],
            'unit': item[2],
            'stock_in': item[3],
            'stock_out': item[4] if item[4] else 0,
            'total_stock': (item[3] - (item[4] if item[4] else 0)),
            'category': item[5],
            'category_id': item[6]
        })
    return result

def get_items_by_category(category_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT items.id, items.description, items.unit, items.stock_in, items.stock_out,
               categories.name as category_name, categories.id as category_id, items.type
        FROM items 
        LEFT JOIN categories ON items.category_id = categories.id
        WHERE categories.name = ?
        ORDER BY items.id
    ''', (category_name,))
    items = cursor.fetchall()
    conn.close()
    result = []
    for item in items:
        result.append({
            'id': item[0],
            'description': item[1],
            'unit': item[2],
            'stock_in': item[3],
            'stock_out': item[4] if item[4] else 0,
            'total_stock': (item[3] - (item[4] if item[4] else 0)),
            'category': item[5],
            'category_id': item[6],
            'type': item[7] if item[7] else 'accessory'
        })
    return result

def get_risk_items(threshold=10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT items.id, items.description, items.unit, items.stock_in, items.stock_out,
               categories.name as category_name, (items.stock_in - items.stock_out) as total_stock
        FROM items 
        LEFT JOIN categories ON items.category_id = categories.id
        WHERE (items.stock_in - items.stock_out) <= ?
        ORDER BY total_stock ASC
    ''', (threshold,))
    items = cursor.fetchall()
    conn.close()
    result = []
    for item in items:
        result.append({
            'id': item[0],
            'description': item[1],
            'unit': item[2],
            'stock_in': item[3],
            'stock_out': item[4] if item[4] else 0,
            'total_stock': item[6],
            'category': item[5]
        })
    return result

def get_dashboard_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM items')
    total_items = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(stock_in - stock_out) FROM items')
    total_stock_result = cursor.fetchone()[0]
    total_stock = total_stock_result if total_stock_result else 0
    
    cursor.execute('SELECT COUNT(*) FROM items WHERE (stock_in - stock_out) < 10 AND (stock_in - stock_out) > 0')
    low_stock = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM items WHERE (stock_in - stock_out) = 0')
    out_stock = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM categories')
    total_categories = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_items': total_items,
        'total_stock': total_stock,
        'low_stock': low_stock,
        'out_stock': out_stock,
        'total_categories': total_categories
    }

def update_item_type(item_id, item_type):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE items SET type = ? WHERE id = ?', (item_type, item_id))
    conn.commit()
    conn.close()