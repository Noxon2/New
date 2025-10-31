from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import sqlite3
import os
import uuid

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# ✅ Database aur upload paths
DB_PATH = '/tmp/books.db'
UPLOAD_DIR = '/tmp/uploads'
BOOKS_DIR = os.path.join(UPLOAD_DIR, 'books')
THUMBNAILS_DIR = os.path.join(UPLOAD_DIR, 'thumbnails')
os.makedirs(BOOKS_DIR, exist_ok=True)
os.makedirs(THUMBNAILS_DIR, exist_ok=True)

# ✅ DB initialize
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

# 🌐 Routes
@app.route('/')
def home():
    return send_from_directory('.', 'index.html')


# ✅ Upload API (thumbnail + book save)
@app.route('/api/books', methods=['POST'])
def upload_book():
    title = request.form.get('title')
    author = request.form.get('author')
    category = request.form.get('category')
    description = request.form.get('description')
    book_file = request.files.get('book_file')
    thumbnail = request.files.get('thumbnail')

    if not all([title, author, category, book_file, thumbnail]):
        return jsonify({"error": "Missing required field"}), 400

    # unique file names
    book_id = str(uuid.uuid4())
    book_filename = f"{book_id}_{book_file.filename}"
    thumb_filename = f"{book_id}_{thumbnail.filename}"

    book_path = os.path.join(BOOKS_DIR, book_filename)
    thumb_path = os.path.join(THUMBNAILS_DIR, thumb_filename)

    book_file.save(book_path)
    thumbnail.save(thumb_path)

    file_size = os.path.getsize(book_path)

    conn = get_db_connection()
    conn.execute('''
        INSERT INTO books (title, author, category, description, file_name, file_path, thumbnail_name, thumbnail_path, file_size)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (title, author, category, description, book_filename, book_path, thumb_filename, thumb_path, file_size))
    conn.commit()
    conn.close()

    return jsonify({"message": "Book uploaded successfully"})


# ✅ Serve books list
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
            "upload_date": b["upload_date"],
            "thumbnail_url": f"/thumbnails/{b['thumbnail_name']}"
        })
    return jsonify(books_list)


# ✅ Serve single thumbnail image
@app.route('/thumbnails/<filename>')
def serve_thumbnail(filename):
    return send_from_directory(THUMBNAILS_DIR, filename)


# ✅ Serve book file (for download)
@app.route('/books/<filename>')
def serve_book(filename):
    return send_from_directory(BOOKS_DIR, filename, as_attachment=True)


# ✅ Admin login
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


# ✅ Serve admin panel
@app.route('/admin/<path:path>')
def serve_admin(path):
    return send_from_directory('admin', path)


# ✅ Serve other static files
@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
