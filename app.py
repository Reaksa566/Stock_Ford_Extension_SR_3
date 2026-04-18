from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import database
import sqlite3
from github_sync import sync_db_from_github, sync_db_to_github
import atexit

app = Flask(__name__)
CORS(app)

# Download database from GitHub when app starts
print("=" * 50)
print("🔄 Checking for existing database on GitHub...")
sync_db_from_github()
print("=" * 50)

# Upload database to GitHub when app shuts down
atexit.register(sync_db_to_github)

# Initialize database (this will create tables if they don't exist)
database.init_db()

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/api/categories', methods=['GET'])
def get_categories():
    """Get all categories"""
    categories = database.get_categories()
    return jsonify(categories)

@app.route('/api/categories', methods=['POST'])
def add_category():
    """Add a new category"""
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Category name is required'}), 400
    
    if database.add_category(name):
        return jsonify({'message': 'Category added successfully'})
    else:
        return jsonify({'error': 'Category already exists'}), 400

@app.route('/api/categories/<int:category_id>', methods=['PUT'])
def update_category(category_id):
    """Update category name"""
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
        return jsonify({'message': 'Category updated successfully'})
    else:
        return jsonify({'error': 'Category name already exists'}), 400

@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    """Delete category (items will have category_id set to NULL)"""
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
        return jsonify({'message': 'Category deleted successfully'})
    else:
        return jsonify({'error': 'Error deleting category'}), 400

@app.route('/api/items', methods=['GET'])
def get_items():
    """Get all items"""
    items = database.get_items()
    return jsonify(items)

@app.route('/api/items', methods=['POST'])
def add_item():
    """Add a new item with type"""
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
def update_item(item_id):
    """Update an item"""
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
def update_stock(item_id):
    """Update stock (in/out) with activity logging"""
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
def delete_item(item_id):
    """Delete an item with logging"""
    items = database.get_items()
    item = next((i for i in items if i['id'] == item_id), None)
    
    database.delete_item(item_id)
    
    if item:
        database.add_activity(item_id, item['description'], 'delete', 0, 'Item deleted')
    
    return jsonify({'message': 'Item deleted successfully'})

@app.route('/api/activities', methods=['GET'])
def get_activities():
    """Get all activities with date filter"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    activities = database.get_activities(start_date, end_date)
    return jsonify(activities)

@app.route('/api/items/type/<string:item_type>', methods=['GET'])
def get_items_by_type(item_type):
    """Get items by type"""
    items = database.get_items_by_type(item_type)
    return jsonify(items)

@app.route('/api/items/category/<string:category_name>', methods=['GET'])
def get_items_by_category(category_name):
    """Get items by category name"""
    items = database.get_items_by_category(category_name)
    return jsonify(items)

@app.route('/api/risk-items', methods=['GET'])
def get_risk_items():
    """Get risk items below threshold"""
    threshold = request.args.get('threshold', 10, type=int)
    items = database.get_risk_items(threshold)
    return jsonify(items)

@app.route('/api/dashboard-stats', methods=['GET'])
def get_dashboard_stats():
    """Get dashboard statistics"""
    stats = database.get_dashboard_stats()
    return jsonify(stats)

@app.route('/api/items/<int:item_id>/type', methods=['PATCH'])
def update_item_type(item_id):
    """Update item type"""
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
def export_items():
    """Export all items as JSON"""
    items = database.get_items()
    return jsonify(items)

@app.route('/api/search', methods=['GET'])
def search_items():
    """Search items by description"""
    query = request.args.get('q', '').lower()
    items = database.get_items()
    filtered = [item for item in items if query in item['description'].lower()]
    return jsonify(filtered)

@app.route('/api/stats/category', methods=['GET'])
def get_category_stats():
    """Get stock statistics by category"""
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