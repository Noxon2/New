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
    username = request.form.get('username')
    password = request.form.get('password')

    # Static credentials
    if username == 'admin' and password == 'admin123':
        return jsonify({'success': True, 'message': 'Login successful!'}), 200
    else:
        return jsonify({'success': False, 'error': 'Invalid username or password'}), 401


# ✅ Upload book
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
    conn.execute('''INSERT INTO books (title, author, category, description, file_name, file_path,
                    thumbnail_name, thumbnail_path, file_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (title, author, category, desc, book_name, book_path, thumb_name, thumb_path, file_size))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Book uploaded successfully!'}), 200


# ✅ Get all books
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
            'file_name': b['file_name'],
            'file_size': f"{round(b['file_size']/1024, 2)} KB" if b['file_size'] else "Unknown",
            'thumbnail_url': f"{base_url}/uploads/thumbnails/{b['thumbnail_name']}",
            'file_url': f"{base_url}/uploads/books/{b['file_name']}"
        })
    return jsonify(books)


# ✅ Update Book (PUT)
@app.route('/api/books/<int:book_id>', methods=['PUT'])
def update_book(book_id):
    data = request.get_json()
    title = data.get('title')
    author = data.get('author')
    category = data.get('category')

    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE books SET title=?, author=?, category=? WHERE id=?',
                (title, author, category, book_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Book updated successfully!'})


# ✅ Delete Book (DELETE)
@app.route('/api/books/<int:book_id>', methods=['DELETE'])
def delete_book(book_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM books WHERE id=?', (book_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Book deleted successfully!'})


# ✅ Download Book (also increase count)
@app.route('/api/books/<int:book_id>/download', methods=['GET'])
def download_book(book_id):
    conn = get_db()
    book = conn.execute('SELECT * FROM books WHERE id=?', (book_id,)).fetchone()
    if not book:
        conn.close()
        return jsonify({'error': 'Book not found'}), 404

    file_path = book['file_path']
    if not os.path.exists(file_path):
        conn.close()
        return jsonify({'error': 'File not found'}), 404

    # Update download count
    conn.execute('UPDATE books SET downloads = downloads + 1 WHERE id=?', (book_id,))
    conn.commit()
    conn.close()

    return send_from_directory(BOOKS_DIR, os.path.basename(file_path), as_attachment=True)


# ✅ Serve uploaded files
@app.route('/uploads/books/<path:filename>')
def serve_uploaded_book(filename):
    return send_from_directory(BOOKS_DIR, filename, as_attachment=True)


@app.route('/uploads/thumbnails/<path:filename>')
def serve_uploaded_thumbnail(filename):
    return send_from_directory(THUMB_DIR, filename)


# ✅ Root test
@app.route('/')
def home():
    return "✅ OceanBooks backend is live!"


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
