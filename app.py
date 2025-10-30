from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
import uuid

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})  # ✅ Allow all origins

# 🔧 Safe database path (Render par likhne ki permission hoti hai /tmp folder me)
DB_PATH = '/tmp/books.db'

UPLOAD_DIR = '/tmp/uploads'
BOOKS_DIR = os.path.join(UPLOAD_DIR, 'books')
THUMBNAILS_DIR = os.path.join(UPLOAD_DIR, 'thumbnails')
os.makedirs(BOOKS_DIR, exist_ok=True)
os.makedirs(THUMBNAILS_DIR, exist_ok=True)


# 🗄️ Initialize database
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            thumbnail_name TEXT NOT NULL,
            thumbnail_path TEXT NOT NULL,
            file_size INTEGER,
            downloads INTEGER DEFAULT 0,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        INSERT OR IGNORE INTO admin (id, username, password_hash)
        VALUES (1, 'admin', 'admin123')
    ''')

    conn.commit()
    conn.close()


init_db()


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# 🌐 Home route
@app.route('/')
def home():
    return send_from_directory('.', 'index.html')


# 📚 Get all books
@app.route('/api/books', methods=['GET'])
def get_books():
    conn = get_db_connection()
    books = conn.execute('SELECT * FROM books ORDER BY upload_date DESC').fetchall()
    conn.close()

    books_list = []
    for b in books:
        books_list.append({
            "id": b["id"],
            "title": b["title"],
            "author": b["author"],
            "category": b["category"],
            "description": b["description"],
            "downloads": b["downloads"],
            "upload_date": b["upload_date"]
        })
    return jsonify(books_list)


# 🆕 📤 Upload new book
@app.route('/api/books', methods=['POST'])
def upload_book():
    try:
        title = request.form.get('title')
        author = request.form.get('author')
        category = request.form.get('category')
        description = request.form.get('description')
        file = request.files.get('file')
        thumbnail = request.files.get('thumbnail')

        if not all([title, author, category, file, thumbnail]):
            return jsonify({'error': 'Missing required fields'}), 400

        file_name = str(uuid.uuid4()) + "_" + file.filename
        thumb_name = str(uuid.uuid4()) + "_" + thumbnail.filename

        file_path = os.path.join(BOOKS_DIR, file_name)
        thumb_path = os.path.join(THUMBNAILS_DIR, thumb_name)

        file.save(file_path)
        thumbnail.save(thumb_path)

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO books (title, author, category, description, file_name, file_path, thumbnail_name, thumbnail_path, file_size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (title, author, category, description, file_name, file_path, thumb_name, thumb_path, os.path.getsize(file_path)))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Book uploaded successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 🔐 Admin login
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    username = request.form.get('username')
    password = request.form.get('password')

    conn = get_db_connection()
    admin = conn.execute('SELECT * FROM admin WHERE username=?', (username,)).fetchone()
    conn.close()

    if admin and admin["password_hash"] == password:
        return jsonify({"success": True, "message": "Login successful"})
    else:
        return jsonify({"error": "Invalid username or password"}), 401


# 🧩 Serve admin folder
@app.route('/admin/<path:path>')
def serve_admin(path):
    return send_from_directory('admin', path)


# 🧩 Serve other static files
@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)


# 🚀 Run app (Render auto port fix)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
