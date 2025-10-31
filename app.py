from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3, os, uuid

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# ======== CONFIG ==========
DB_PATH = '/tmp/books.db'
UPLOAD_DIR = '/tmp/uploads'
BOOKS_DIR = os.path.join(UPLOAD_DIR, 'books')
THUMB_DIR = os.path.join(UPLOAD_DIR, 'thumbnails')

os.makedirs(BOOKS_DIR, exist_ok=True)
os.makedirs(THUMB_DIR, exist_ok=True)
# ==========================

# ✅ DB init
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
        file_path TEXT,
        thumbnail_name TEXT,
        thumbnail_path TEXT,
        file_size INTEGER,
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


# ✅ Admin Login Route
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    # Static credentials — change if needed
    if username == 'admin' and password == 'admin123':
        return jsonify({'message': 'Login successful'}), 200
    else:
        return jsonify({'error': 'Invalid credentials'}), 401


# ✅ Upload book route
@app.route('/api/books', methods=['POST'])
def upload_book():
    title = request.form.get('title')
    author = request.form.get('author')
    category = request.form.get('category')
    desc = request.form.get('description')
    book_file = request.files.get('book_file') or request.files.get('file')
    thumbnail = request.files.get('thumbnail')

    if not all([title, author, category, book_file, thumbnail]):
        return jsonify({'error': 'Missing required field'}), 400

    book_id = str(uuid.uuid4())
    book_name = f"{book_id}_{book_file.filename}"
    thumb_name = f"{book_id}_{thumbnail.filename}"

    book_path = os.path.join(BOOKS_DIR, book_name)
    thumb_path = os.path.join(THUMB_DIR, thumb_name)

    book_file.save(book_path)
    thumbnail.save(thumb_path)

    file_size = os.path.getsize(book_path)

    conn = get_db()
    conn.execute('''INSERT INTO books (title, author, category, description, file_name, file_path, thumbnail_name, thumbnail_path, file_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (title, author, category, desc, book_name, book_path, thumb_name, thumb_path, file_size))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Book uploaded successfully!'}), 200


# ✅ Serve all books
@app.route('/api/books', methods=['GET'])
def get_books():
    conn = get_db()
    rows = conn.execute('SELECT * FROM books ORDER BY upload_date DESC').fetchall()
    conn.close()
    books = []
    for b in rows:
        base_url = f"https://{request.host}"
        books.append({
            'id': b['id'],
            'title': b['title'],
            'author': b['author'],
            'category': b['category'],
            'description': b['description'],
            'downloads': b['downloads'],
            'upload_date': b['upload_date'],
            'thumbnail_url': f"{base_url}/uploads/thumbnails/{b['thumbnail_name']}",
            'file_url': f"{base_url}/uploads/books/{b['file_name']}"
        })
    return jsonify(books)


# ✅ Serve uploaded book files (for download)
@app.route('/uploads/books/<path:filename>')
def serve_uploaded_book(filename):
    file_path = os.path.join(BOOKS_DIR, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    return send_from_directory(BOOKS_DIR, filename, as_attachment=True)


# ✅ Serve uploaded thumbnails (for preview)
@app.route('/uploads/thumbnails/<path:filename>')
def serve_uploaded_thumbnail(filename):
    file_path = os.path.join(THUMB_DIR, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "Thumbnail not found"}), 404
    return send_from_directory(THUMB_DIR, filename)


# ✅ Root test route
@app.route('/')
def home():
    return "✅ OceanBooks backend is live!"


# ✅ Fallback static files
@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
