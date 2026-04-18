from github_sync import sync_db_to_github
import sqlite3
import os
from datetime import datetime

DB_PATH = 'stock_data.db'

def init_db():
    """Initialize the database with tables if they don't exist"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create categories table (if not exists)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    
    # Create items table (if not exists)
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
    
    # Create activities table (if not exists)
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
    
    # Check if categories table is empty before inserting default categories
    cursor.execute('SELECT COUNT(*) FROM categories')
    count = cursor.fetchone()[0]
    
    if count == 0:
        # Insert default categories only if no categories exist
        default_categories = ['LV', 'ELV', 'MVAC', 'Plumbing', 'Fire Fighting', 'Air Compressor']
        for cat in default_categories:
            try:
                cursor.execute('INSERT INTO categories (name) VALUES (?)', (cat,))
            except sqlite3.IntegrityError:
                pass
    
    conn.commit()
    conn.close()
    print("Database initialized successfully!")

def get_categories():
    """Get all categories"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM categories ORDER BY name')
    categories = cursor.fetchall()
    conn.close()
    return [{'id': cat[0], 'name': cat[1]} for cat in categories]

def add_category(name):
    """Add a new category"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO categories (name) VALUES (?)', (name,))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    
    # Sync to GitHub if successful
    if success:
        sync_db_to_github()
    
    return success

def get_items():
    """Get all items with category names and total stock"""
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
    """Add a new item with type specification"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO items (description, unit, stock_in, stock_out, category_id, type)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (description, unit, stock_in, 0, category_id, item_type))
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    
    # Sync to GitHub after adding item
    sync_db_to_github()
    
    return item_id

def update_item(item_id, description, unit, category_id):
    """Update item details"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE items 
        SET description = ?, unit = ?, category_id = ?
        WHERE id = ?
    ''', (description, unit, category_id, item_id))
    conn.commit()
    conn.close()
    
    # Sync to GitHub after updating item
    sync_db_to_github()

def update_stock(item_id, quantity_change):
    """Update stock (positive for stock in, negative for stock out)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if quantity_change > 0:
        # Stock IN
        cursor.execute('UPDATE items SET stock_in = stock_in + ? WHERE id = ?', (quantity_change, item_id))
    else:
        # Stock OUT
        cursor.execute('UPDATE items SET stock_out = stock_out + ? WHERE id = ?', (abs(quantity_change), item_id))
    
    conn.commit()
    conn.close()
    
    # Sync to GitHub after updating stock
    sync_db_to_github()

def delete_item(item_id):
    """Delete an item"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM activities WHERE item_id = ?', (item_id,))
    cursor.execute('DELETE FROM items WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    
    # Sync to GitHub after deleting item
    sync_db_to_github()

def get_item_stock(item_id):
    """Get current total stock of an item"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT stock_in, stock_out FROM items WHERE id = ?', (item_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return result[0] - result[1]
    return 0

def add_activity(item_id, item_name, action, quantity, notes=''):
    """Log stock activity"""
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
    """Get activities with optional date filter"""
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
    """Get items filtered by type (accessory or tool)"""
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
    """Get items filtered by category"""
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
    """Get items with stock below threshold"""
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
    """Get statistics for dashboard"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Total items
    cursor.execute('SELECT COUNT(*) FROM items')
    total_items = cursor.fetchone()[0]
    
    # Total stock units
    cursor.execute('SELECT SUM(stock_in - stock_out) FROM items')
    total_stock_result = cursor.fetchone()[0]
    total_stock = total_stock_result if total_stock_result else 0
    
    # Low stock items (less than 10)
    cursor.execute('SELECT COUNT(*) FROM items WHERE (stock_in - stock_out) < 10 AND (stock_in - stock_out) > 0')
    low_stock = cursor.fetchone()[0]
    
    # Out of stock items
    cursor.execute('SELECT COUNT(*) FROM items WHERE (stock_in - stock_out) = 0')
    out_stock = cursor.fetchone()[0]
    
    # Total categories
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
    """Update item type (accessory/tool)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE items SET type = ? WHERE id = ?', (item_type, item_id))
    conn.commit()
    conn.close()
    
    # Sync to GitHub after updating item type
    sync_db_to_github()