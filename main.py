from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import sqlite3
import os
import shutil
from datetime import datetime
import uuid
import json

app = Flask(__name__)
CORS(app)

# Upload folders create karenge
UPLOAD_DIR = "uploads"
BOOKS_DIR = os.path.join(UPLOAD_DIR, "books")
THUMBNAILS_DIR = os.path.join(UPLOAD_DIR, "thumbnails")

# Ensure upload directories exist
os.makedirs(BOOKS_DIR, exist_ok=True)
os.makedirs(THUMBNAILS_DIR, exist_ok=True)

# Database initialization
def init_db():
    conn = sqlite3.connect('books.db')
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
    
    # Admin credentials table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    
    # Default admin insert karenge
    cursor.execute('''
        INSERT OR IGNORE INTO admin (id, username, password_hash) 
        VALUES (1, 'admin', 'admin123')
    ''')
    
    conn.commit()
    conn.close()

# Database initialize karo
init_db()

# Helper functions
def get_db_connection():
    conn = sqlite3.connect('books.db')
    conn.row_factory = sqlite3.Row
    return conn

def format_file_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names)-1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f} {size_names[i]}"

# Routes shuru karte hain

@app.route('/')
def root():
    return send_file('index.html')

@app.route('/api/books', methods=['GET'])
def get_all_books():
    """Get all books from database"""
    conn = get_db_connection()
    books = conn.execute('SELECT * FROM books ORDER BY upload_date DESC').fetchall()
    conn.close()
    
    books_list = []
    for book in books:
        thumbnail_filename = os.path.basename(book["thumbnail_path"])
        thumbnail_url = f"/api/thumbnails/{thumbnail_filename}"
        
        books_list.append({
            "id": book["id"],
            "title": book["title"],
            "author": book["author"],
            "category": book["category"],
            "description": book["description"],
            "file_name": book["file_name"],
            "file_size": format_file_size(book["file_size"]),
            "downloads": book["downloads"],
            "upload_date": book["upload_date"],
            "thumbnail_path": thumbnail_url
        })
    
    return jsonify(books_list)

@app.route('/api/books', methods=['POST'])
def upload_book():
    """Upload new book with thumbnail"""
    allowed_book_extensions = ['.pdf', '.epub', '.doc', '.docx']
    allowed_image_extensions = ['.jpg', '.jpeg', '.png', '.webp']
    
    try:
        title = request.form.get('title')
        author = request.form.get('author')
        category = request.form.get('category')
        description = request.form.get('description', '')
        book_file = request.files.get('book_file')
        thumbnail = request.files.get('thumbnail')
        
        if not all([title, author, category, book_file, thumbnail]):
            return jsonify({"error": "All fields are required"}), 400
        
        book_ext = os.path.splitext(book_file.filename)[1].lower()
        thumb_ext = os.path.splitext(thumbnail.filename)[1].lower()
        
        if book_ext not in allowed_book_extensions:
            return jsonify({"error": "Invalid book file format"}), 400
        
        if thumb_ext not in allowed_image_extensions:
            return jsonify({"error": "Invalid thumbnail image format"}), 400
        
        # Unique filenames generate karenge
        book_filename = f"{uuid.uuid4()}{book_ext}"
        thumb_filename = f"{uuid.uuid4()}{thumb_ext}"
        
        book_path = os.path.join(BOOKS_DIR, book_filename)
        thumb_path = os.path.join(THUMBNAILS_DIR, thumb_filename)
        
        # Files save karenge
        book_file.save(book_path)
        thumbnail.save(thumb_path)
        
        # File size get karenge
        file_size = os.path.getsize(book_path)
        
        # Database mein entry create karenge
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO books (title, author, category, description, file_name, file_path, thumbnail_name, thumbnail_path, file_size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (title, author, category, description, book_file.filename, book_path, thumbnail.filename, thumb_path, file_size))
        
        book_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            "message": "Book uploaded successfully!",
            "book_id": book_id,
            "title": title
        })
        
    except Exception as e:
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


# ✅ New route added (Update book info)
@app.route('/api/books/<int:book_id>', methods=['PUT'])
def update_book(book_id):
    """Update book details (title, author, category)"""
    try:
        data = request.get_json()
        title = data.get('title')
        author = data.get('author')
        category = data.get('category')

        if not all([title, author, category]):
            return jsonify({"error": "All fields are required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE books 
            SET title = ?, author = ?, category = ? 
            WHERE id = ?
        ''', (title, author, category, book_id))
        conn.commit()
        conn.close()

        return jsonify({"success": True, "message": "Book updated successfully"})
    except Exception as e:
        return jsonify({"error": f"Update failed: {str(e)}"}), 500


@app.route('/api/books/<int:book_id>/download')
def download_book(book_id):
    """Download book file"""
    conn = get_db_connection()
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    conn.close()
    
    if not book:
        return jsonify({"error": "Book not found"}), 404
    
    # Download count increment karenge
    conn = get_db_connection()
    conn.execute('UPDATE books SET downloads = downloads + 1 WHERE id = ?', (book_id,))
    conn.commit()
    conn.close()
    
    return send_file(book["file_path"], as_attachment=True, download_name=book["file_name"])

@app.route('/api/books/<int:book_id>', methods=['DELETE'])
def delete_book(book_id):
    """Delete book from database and filesystem"""
    conn = get_db_connection()
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    
    if not book:
        conn.close()
        return jsonify({"error": "Book not found"}), 404
    
    try:
        # Files delete karenge
        if os.path.exists(book["file_path"]):
            os.remove(book["file_path"])
        if os.path.exists(book["thumbnail_path"]):
            os.remove(book["thumbnail_path"])
        
        # Database entry delete karenge
        conn.execute('DELETE FROM books WHERE id = ?', (book_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Book deleted successfully"})
        
    except Exception as e:
        conn.close()
        return jsonify({"error": f"Delete failed: {str(e)}"}), 500


@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    """Admin login endpoint"""
    username = request.form.get('username')
    password = request.form.get('password')
    
    conn = get_db_connection()
    admin = conn.execute(
        'SELECT * FROM admin WHERE username = ?', 
        (username,)
    ).fetchone()
    conn.close()
    
    if admin:
        if admin["password_hash"] == password:
            return jsonify({"message": "Login successful", "success": True})
        else:
            return jsonify({"error": "Invalid password"}), 401
    else:
        return jsonify({"error": "Invalid username"}), 401


@app.route('/api/admin/stats')
def get_admin_stats():
    """Get dashboard statistics"""
    conn = get_db_connection()
    total_books = conn.execute('SELECT COUNT(*) as count FROM books').fetchone()["count"]
    total_downloads = conn.execute('SELECT SUM(downloads) as total FROM books').fetchone()["total"] or 0
    total_size = conn.execute('SELECT SUM(file_size) as size FROM books').fetchone()["size"] or 0
    conn.close()
    
    return jsonify({
        "total_books": total_books,
        "total_downloads": total_downloads,
        "total_size": format_file_size(total_size)
    })


# Thumbnail serve karne ke liye routes
@app.route('/api/thumbnails/<filename>')
def get_thumbnail(filename):
    """Serve thumbnail images"""
    thumbnail_path = os.path.join(THUMBNAILS_DIR, filename)
    if os.path.exists(thumbnail_path):
        return send_file(thumbnail_path)
    else:
        return jsonify({"error": "Thumbnail not found"}), 404


@app.route('/api/books/files/<filename>')
def get_book_file(filename):
    """Serve book files"""
    book_path = os.path.join(BOOKS_DIR, filename)
    if os.path.exists(book_path):
        return send_file(book_path)
    else:
        return jsonify({"error": "Book file not found"}), 404


# Static files serve karna
@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

@app.route('/admin/<path:path>')
def serve_admin(path):
    return send_from_directory('admin', path)


if __name__ == "__main__":
    print("Flask server starting...")
    print("Open: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)