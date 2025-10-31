# main.py
from flask import Flask, request, jsonify, redirect, send_from_directory
from flask_cors import CORS
import sqlite3, os, uuid
from supabase import create_client, Client

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# -----------------------
# CONFIG (use env vars)
# -----------------------
# Set these env vars in your host (Render / Heroku / local)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://xmsykiasnebfqzqdfjyo.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhtc3lraWFzbmViZnF6cWRmanlvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE4MzY4ODgsImV4cCI6MjA3NzQxMjg4OH0.rxvCCgDh9tQ1Uu2JY1_SIdPYwHmZjDNqhbVNxtUsKgc")  # set in env

# local DB file (keeps metadata). Change path if you want different location.
DB_PATH = os.path.join(os.getcwd(), "books.db")

# Supabase bucket name (you said 'uploads')
SUPABASE_BUCKET = "uploads"

# create client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------
# DB + folders setup
# -----------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS books(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        author TEXT,
        category TEXT,
        description TEXT,
        file_name TEXT,
        file_url TEXT,
        thumbnail_name TEXT,
        thumbnail_url TEXT,
        file_size REAL,
        downloads INTEGER DEFAULT 0,
        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# -----------------------
# Helper: readable size
# -----------------------
def readable_mb(mb_float):
    try:
        if mb_float is None:
            return "Unknown"
        if mb_float >= 1024:
            return f"{round(mb_float/1024, 2)} GB"
        return f"{round(mb_float, 2)} MB"
    except:
        return "Unknown"

# -----------------------
# Admin login (unchanged)
# -----------------------
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    username = request.form.get('username')
    password = request.form.get('password')
    if username == 'admin' and password == 'admin123':
        return jsonify({'success': True, 'message': 'Login successful!'}), 200
    return jsonify({'success': False, 'error': 'Invalid username or password'}), 401

# -----------------------
# Upload route (Supabase)
# -----------------------
@app.route('/api/books', methods=['POST'])
def upload_book():
    title = request.form.get('title')
    author = request.form.get('author')
    category = request.form.get('category')
    desc = request.form.get('description')
    # accept either field name 'book_file' or 'file' for compatibility
    book_file = request.files.get('book_file') or request.files.get('file')
    thumbnail = request.files.get('thumbnail')

    if not all([title, author, category, book_file, thumbnail]):
        return jsonify({'error': 'Missing required field'}), 400

    # unique names to avoid collisions
    uid = str(uuid.uuid4())
    book_name = f"books/{uid}_{book_file.filename}"
    thumb_name = f"thumbnails/{uid}_{thumbnail.filename}"

    # Read bytes (we must read file-like into bytes to upload)
    book_bytes = book_file.read()
    thumbnail_bytes = thumbnail.read()

    # Upload to Supabase bucket (public bucket)
    try:
        # upload returns dict on success or raises
        supabase.storage.from_(SUPABASE_BUCKET).upload(book_name, book_bytes)
        supabase.storage.from_(SUPABASE_BUCKET).upload(thumb_name, thumbnail_bytes)
    except Exception as e:
        return jsonify({'error': f"Upload to storage failed: {e}"}), 500

    # build public URLs (public bucket)
    book_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{book_name}"
    thumb_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{thumb_name}"

    # file size in MB
    try:
        file_size_mb = round(len(book_bytes) / (1024 * 1024), 2)
    except:
        file_size_mb = 0.0

    # save metadata in sqlite
    conn = get_db()
    conn.execute('''INSERT INTO books
        (title, author, category, description, file_name, file_url, thumbnail_name, thumbnail_url, file_size)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (title, author, category, desc, book_file.filename, book_url, thumbnail.filename, thumb_url, file_size_mb))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Book uploaded successfully!', 'file_url': book_url, 'thumbnail_url': thumb_url}), 200

# -----------------------
# Get all books
# -----------------------
@app.route('/api/books', methods=['GET'])
def get_books():
    conn = get_db()
    rows = conn.execute('SELECT * FROM books ORDER BY upload_date DESC').fetchall()
    conn.close()
    result = []
    for b in rows:
        result.append({
            'id': b['id'],
            'title': b['title'],
            'author': b['author'],
            'category': b['category'],
            'description': b['description'],
            'downloads': b['downloads'],
            'upload_date': b['upload_date'],
            'file_name': b['file_name'],
            'file_size': b['file_size'],              # float MB (for JS to format if needed)
            'file_size_str': readable_mb(b['file_size']),
            'thumbnail_url': b['thumbnail_url'],
            'file_url': b['file_url']
        })
    return jsonify(result)

# -----------------------
# Download route (increments count, then redirect to Supabase URL)
# -----------------------
@app.route('/api/books/<int:book_id>/download', methods=['GET'])
def download_book(book_id):
    conn = get_db()
    book = conn.execute('SELECT * FROM books WHERE id=?', (book_id,)).fetchone()
    if not book:
        conn.close()
        return jsonify({'error': 'Book not found'}), 404

    # increment count
    conn.execute('UPDATE books SET downloads = downloads + 1 WHERE id=?', (book_id,))
    conn.commit()
    conn.close()

    # redirect to Supabase public URL so browser downloads from Supabase
    file_url = book['file_url']
    return redirect(file_url, code=302)

# -----------------------
# Update / Delete routes (same behaviour)
# -----------------------
@app.route('/api/books/<int:book_id>', methods=['PUT'])
def update_book(book_id):
    data = request.get_json()
    title = data.get('title')
    author = data.get('author')
    category = data.get('category')
    conn = get_db()
    conn.execute('UPDATE books SET title=?, author=?, category=? WHERE id=?',
                 (title, author, category, book_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Book updated successfully!'})

@app.route('/api/books/<int:book_id>', methods=['DELETE'])
def delete_book(book_id):
    # Note: This deletes DB record only. If you also want to remove from Supabase storage,
    # you can call supabase.storage.from_(SUPABASE_BUCKET).remove([path]) here.
    conn = get_db()
    conn.execute('DELETE FROM books WHERE id=?', (book_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Book deleted successfully!'})

# -----------------------
# Admin stats for dashboard
# -----------------------
@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM books')
    total_books = cur.fetchone()[0] or 0
    cur.execute('SELECT SUM(downloads) FROM books')
    total_downloads = cur.fetchone()[0] or 0
    cur.execute('SELECT SUM(file_size) FROM books')
    total_size_mb = cur.fetchone()[0] or 0.0
    conn.close()
    return jsonify({
        "total_books": total_books,
        "total_downloads": total_downloads,
        "total_size": f"{round(total_size_mb, 2)} MB"
    })

# -----------------------
# Fallback frontends + root
# -----------------------
@app.route('/')
def home():
    return "✅ OceanBooks backend (Supabase storage) is live!"

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

# -----------------------
# Run
# -----------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)