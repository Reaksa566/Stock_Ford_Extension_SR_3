from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
import database
import sqlite3
from github_sync import sync_db_from_github, sync_db_to_github
import atexit
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production-2024'
CORS(app)

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

print("=" * 50)
print("🔄 Checking for existing database on GitHub...")
sync_db_from_github()
print("=" * 50)

atexit.register(sync_db_to_github)
database.init_db()

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
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    if 'user_id' in session:
        return jsonify({'authenticated': True, 'username': session['username'], 'role': session['role']})
    return jsonify({'authenticated': False})

@app.route('/api/users', methods=['GET'])
@login_required
@admin_required
def get_users():
    users = database.get_users()
    return jsonify(users)

@app.route('/api/users', methods=['POST'])
@login_required
@admin_required
def add_user():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'user')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    if database.add_user(username, password, role):
        return jsonify({'message': 'User added successfully'})
    else:
        return jsonify({'error': 'Username already exists'}), 400

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    database.delete_user(user_id)
    return jsonify({'message': 'User deleted successfully'})

@app.route('/api/categories', methods=['GET'])
@login_required
def get_categories():
    categories = database.get_categories()
    return jsonify(categories)

@app.route('/api/categories', methods=['POST'])
@login_required
def add_category():
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Category name is required'}), 400
    
    if database.add_category(name):
        return jsonify({'message': 'Category added successfully'})
    else:
        return jsonify({'error': 'Category already exists'}), 400

@app.route('/api/categories/<int:category_id>', methods=['PUT'])
@login_required
def update_category(category_id):
    data = request.json
    new_name = data.get('name', '').strip()
    
    if not new_name:
        return jsonify({'error': 'Category name is required'}), 400
    
    conn = sqlite3.connect(database.DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE categories SET name = ? WHERE id = ?', (new_name, category_id))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()
    
    if success:
        database.sync_db_to_github()
        return jsonify({'message': 'Category updated successfully'})
    else:
        return jsonify({'error': 'Category name already exists'}), 400

@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
@login_required
def delete_category(category_id):
    conn = sqlite3.connect(database.DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('UPDATE items SET category_id = NULL WHERE category_id = ?', (category_id,))
        cursor.execute('DELETE FROM categories WHERE id = ?', (category_id,))
        conn.commit()
        success = True
    except Exception as e:
        success = False
    finally:
        conn.close()
    
    if success:
        database.sync_db_to_github()
        return jsonify({'message': 'Category deleted successfully'})
    else:
        return jsonify({'error': 'Error deleting category'}), 400

@app.route('/api/items', methods=['GET'])
@login_required
def get_items():
    items = database.get_items()
    return jsonify(items)

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
    
    return jsonify({'message': 'Item added successfully', 'id': item_id})

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
    
    if old_item:
        database.add_activity(item_id, description, 'update', 0, f'Updated from {old_item["description"]}')
    
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
    
    return jsonify({'message': message, 'new_stock': new_stock})

@app.route('/api/items/<int:item_id>', methods=['DELETE'])
@login_required
def delete_item(item_id):
    items = database.get_items()
    item = next((i for i in items if i['id'] == item_id), None)
    
    database.delete_item(item_id)
    
    if item:
        database.add_activity(item_id, item['description'], 'delete', 0, 'Item deleted')
    
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
    
    if item:
        database.add_activity(item_id, item['description'], 'update_type', 0, f'Type changed to {item_type}')
    
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
    app.run(debug=True, port=5000)