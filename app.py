from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import database
import sqlite3
from github_sync import sync_db_from_github, sync_db_to_github
import atexit
from functools import wraps
from datetime import datetime
import time
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production-2024')
CORS(app)

# ============ SIMPLE CACHE ============
cache = {}
cache_timeout = 30  # 30 seconds

def get_cached(key, fetch_func):
    """Get data from cache or fetch if expired"""
    if key in cache:
        data, timestamp = cache[key]
        if time.time() - timestamp < cache_timeout:
            return data
    data = fetch_func()
    cache[key] = (data, time.time())
    return data

def invalidate_cache():
    """Clear all cache"""
    cache.clear()
    print("🔄 Cache invalidated")

# ============ AUTH DECORATORS ============
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Login required'}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# ============ INITIALIZATION ============
print("=" * 50)
print("🚀 Starting Stock Management System...")

# FIRST: Initialize local database (creates if doesn't exist)
try:
    database.init_db()
    print("✅ Local database initialized/verified")
except Exception as e:
    print(f"❌ Database initialization error: {e}")
    # Try to recover from backup if exists
    if os.path.exists('stock_data.db.backup'):
        import shutil
        shutil.copy('stock_data.db.backup', 'stock_data.db')
        print("🔄 Restored from backup")
        try:
            database.init_db()
        except Exception as backup_error:
            print(f"❌ Backup recovery failed: {backup_error}")

# SECOND: Sync with GitHub (download if GitHub has newer valid data)
print("=" * 50)
print("🔄 Syncing with GitHub...")
try:
    # This will download from GitHub ONLY if GitHub has valid data
    # and won't overwrite if local is newer/bigger
    sync_db_from_github()
except Exception as e:
    print(f"⚠️ GitHub sync error (non-critical): {e}")

# THIRD: Register auto-sync on exit
atexit.register(sync_db_to_github)
print("=" * 50)
print("✅ System ready!")
print("=" * 50)

# ============ ROUTES ============
@app.route('/')
def index():
    if 'user_id' in session:
        return render_template('index.html')
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        user = database.authenticate_user(username, password)
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return jsonify({'success': True, 'message': 'Login successful', 'role': user['role']})
        else:
            return jsonify({'success': False, 'error': 'Invalid username or password'}), 401
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    invalidate_cache()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    if 'user_id' in session:
        return jsonify({'authenticated': True, 'username': session['username'], 'role': session['role']})
    return jsonify({'authenticated': False})

@app.route('/api/categories', methods=['GET'])
@login_required
def get_categories():
    def fetch():
        return database.get_categories()
    return jsonify(get_cached('categories', fetch))

@app.route('/api/categories', methods=['POST'])
@login_required
def add_category():
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Category name is required'}), 400
    
    if database.add_category(name):
        invalidate_cache()
        # Sync to GitHub after changes
        sync_db_to_github()
        return jsonify({'message': 'Category added successfully'})
    else:
        return jsonify({'error': 'Category already exists'}), 400

@app.route('/api/items', methods=['GET'])
@login_required
def get_items():
    def fetch():
        return database.get_items()
    return jsonify(get_cached('items', fetch))

@app.route('/api/items', methods=['POST'])
@login_required
def add_item():
    data = request.json
    description = data.get('description', '').strip()
    unit = data.get('unit', '').strip()
    stock_in = int(data.get('stock_in', 0))
    category_id = data.get('category_id')
    item_type = data.get('type', 'accessory')
    
    if not description or not unit or not category_id:
        return jsonify({'error': 'Missing required fields'}), 400
    
    item_id = database.add_item(description, unit, stock_in, category_id, item_type)
    database.add_activity(item_id, description, 'create', stock_in, 'Item created')
    invalidate_cache()
    
    # Sync to GitHub after changes
    sync_db_to_github()
    
    return jsonify({'message': 'Item added successfully', 'id': item_id})

# ============ BATCH API FOR FAST IMPORT ============
@app.route('/api/items/batch', methods=['POST'])
@login_required
def add_items_batch():
    """Add multiple items in one request - MUCH FASTER for large imports"""
    data = request.json
    items = data.get('items', [])
    
    if not items:
        return jsonify({'error': 'No items provided'}), 400
    
    conn = sqlite3.connect(database.DB_PATH)
    cursor = conn.cursor()
    
    success_count = 0
    error_count = 0
    item_ids = []
    
    for item_data in items:
        try:
            description = item_data.get('description', '').strip()
            unit = item_data.get('unit', '').strip()
            stock_in = int(item_data.get('stock_in', 0))
            category_id = item_data.get('category_id')
            item_type = item_data.get('type', 'accessory')
            
            if not description or not unit or not category_id:
                error_count += 1
                continue
            
            cursor.execute('''
                INSERT INTO items (description, unit, stock_in, stock_out, category_id, type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (description, unit, stock_in, 0, category_id, item_type))
            
            item_ids.append(cursor.lastrowid)
            success_count += 1
            
        except Exception as e:
            error_count += 1
            print(f"Error adding item: {e}")
    
    conn.commit()
    
    # Add activities for each item
    now = datetime.now()
    for idx, item_id in enumerate(item_ids):
        item_data = items[idx]
        cursor.execute('''
            INSERT INTO activities (item_id, item_name, action, quantity, notes, date, time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (item_id, item_data.get('description'), 'create', item_data.get('stock_in', 0), 
              'Batch import', now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S')))
    
    conn.commit()
    conn.close()
    
    invalidate_cache()
    
    # Sync to GitHub after batch import
    sync_db_to_github()
    
    return jsonify({
        'success': success_count,
        'error': error_count,
        'message': f'Added {success_count} items, {error_count} failed'
    })

@app.route('/api/items/<int:item_id>', methods=['PUT'])
@login_required
def update_item(item_id):
    data = request.json
    description = data.get('description', '').strip()
    unit = data.get('unit', '').strip()
    category_id = data.get('category_id')
    
    if not description or not unit or not category_id:
        return jsonify({'error': 'Missing required fields'}), 400
    
    old_items = database.get_items()
    old_item = next((item for item in old_items if item['id'] == item_id), None)
    
    database.update_item(item_id, description, unit, category_id)
    invalidate_cache()
    
    if old_item:
        database.add_activity(item_id, description, 'update', 0, f'Updated from {old_item["description"]}')
    
    # Sync to GitHub after changes
    sync_db_to_github()
    
    return jsonify({'message': 'Item updated successfully'})

@app.route('/api/items/<int:item_id>/stock', methods=['PATCH'])
@login_required
def update_stock(item_id):
    data = request.json
    action = data.get('action')
    quantity = int(data.get('quantity', 0))
    notes = data.get('notes', '')
    
    if action not in ['in', 'out'] or quantity <= 0:
        return jsonify({'error': 'Invalid action or quantity'}), 400
    
    current_stock = database.get_item_stock(item_id)
    items = database.get_items()
    item = next((i for i in items if i['id'] == item_id), None)
    
    if action == 'in':
        database.update_stock(item_id, quantity)
        new_stock = current_stock + quantity
        message = f'Added {quantity} items to stock'
        if item:
            database.add_activity(item_id, item['description'], 'in', quantity, notes)
    else:
        if current_stock < quantity:
            return jsonify({'error': f'Insufficient stock. Current stock: {current_stock}'}), 400
        database.update_stock(item_id, -quantity)
        new_stock = current_stock - quantity
        message = f'Removed {quantity} items from stock'
        if item:
            database.add_activity(item_id, item['description'], 'out', quantity, notes)
    
    invalidate_cache()
    
    # Sync to GitHub after changes
    sync_db_to_github()
    
    return jsonify({'message': message, 'new_stock': new_stock})

@app.route('/api/items/<int:item_id>', methods=['DELETE'])
@login_required
def delete_item(item_id):
    items = database.get_items()
    item = next((i for i in items if i['id'] == item_id), None)
    
    database.delete_item(item_id)
    invalidate_cache()
    
    if item:
        database.add_activity(item_id, item['description'], 'delete', 0, 'Item deleted')
    
    # Sync to GitHub after changes
    sync_db_to_github()
    
    return jsonify({'message': 'Item deleted successfully'})

@app.route('/api/activities', methods=['GET'])
@login_required
def get_activities():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    activities = database.get_activities(start_date, end_date)
    return jsonify(activities)

@app.route('/api/items/type/<string:item_type>', methods=['GET'])
@login_required
def get_items_by_type(item_type):
    items = database.get_items_by_type(item_type)
    return jsonify(items)

@app.route('/api/items/category/<string:category_name>', methods=['GET'])
@login_required
def get_items_by_category(category_name):
    items = database.get_items_by_category(category_name)
    return jsonify(items)

@app.route('/api/risk-items', methods=['GET'])
@login_required
def get_risk_items():
    threshold = request.args.get('threshold', 10, type=int)
    items = database.get_risk_items(threshold)
    return jsonify(items)

@app.route('/api/dashboard-stats', methods=['GET'])
@login_required
def get_dashboard_stats():
    stats = database.get_dashboard_stats()
    return jsonify(stats)

@app.route('/api/items/<int:item_id>/type', methods=['PATCH'])
@login_required
def update_item_type(item_id):
    data = request.json
    item_type = data.get('type')
    
    if item_type not in ['accessory', 'tool']:
        return jsonify({'error': 'Invalid type'}), 400
    
    items = database.get_items()
    item = next((i for i in items if i['id'] == item_id), None)
    
    database.update_item_type(item_id, item_type)
    invalidate_cache()
    
    if item:
        database.add_activity(item_id, item['description'], 'update_type', 0, f'Type changed to {item_type}')
    
    # Sync to GitHub after changes
    sync_db_to_github()
    
    return jsonify({'message': 'Item type updated successfully'})

@app.route('/api/export/items', methods=['GET'])
@login_required
def export_items():
    items = database.get_items()
    return jsonify(items)

@app.route('/api/search', methods=['GET'])
@login_required
def search_items():
    query = request.args.get('q', '').lower()
    items = database.get_items()
    filtered = [item for item in items if query in item['description'].lower()]
    return jsonify(filtered)

@app.route('/api/stats/category', methods=['GET'])
@login_required
def get_category_stats():
    items = database.get_items()
    category_stats = {}
    
    for item in items:
        cat = item['category'] if item['category'] else 'Uncategorized'
        if cat not in category_stats:
            category_stats[cat] = {
                'total_items': 0,
                'total_stock': 0,
                'low_stock_count': 0
            }
        category_stats[cat]['total_items'] += 1
        category_stats[cat]['total_stock'] += item['total_stock']
        if item['total_stock'] < 10:
            category_stats[cat]['low_stock_count'] += 1
    
    return jsonify(category_stats)

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))