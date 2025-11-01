# app.py
import os
import uuid
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from supabase import create_client, Client
from datetime import datetime

app = Flask(__name__)
CORS(app)

# -----------------------
# Config (from env)
# -----------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "uploads")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set as environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------
# Helpers
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
# Admin login
# -----------------------
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    username = request.form.get('username')
    password = request.form.get('password')
    if username == 'admin' and password == 'admin123':
        return jsonify({'success': True, 'message': 'Login successful!'}), 200
    return jsonify({'success': False, 'error': 'Invalid username or password'}), 401

# -----------------------
# Upload book
# -----------------------
@app.route('/api/books', methods=['POST'])
def upload_book():
    title = request.form.get('title')
    author = request.form.get('author')
    category = request.form.get('category')
    desc = request.form.get('description')
    book_file = request.files.get('book_file') or request.files.get('file')
    thumbnail = request.files.get('thumbnail')

    if not all([title, author, category, book_file, thumbnail]):
        return jsonify({'error': 'Missing required field (title, author, category, book_file, thumbnail)'}), 400

    uid = str(uuid.uuid4())
    book_name = f"books/{uid}_{book_file.filename}"
    thumb_name = f"thumbnails/{uid}_{thumbnail.filename}"

    book_bytes = book_file.read()
    thumbnail_bytes = thumbnail.read()

    try:
        supabase.storage.from_(SUPABASE_BUCKET).upload(book_name, book_bytes)
        supabase.storage.from_(SUPABASE_BUCKET).upload(thumb_name, thumbnail_bytes)
    except Exception as e:
        return jsonify({'error': f"Upload to storage failed: {e}"}), 500

    book_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{book_name}"
    thumb_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{thumb_name}"

    file_size_mb = round(len(book_bytes) / (1024 * 1024), 2)

    insert_data = {
        "title": title,
        "author": author,
        "category": category,
        "description": desc,
        "file_url": book_url,
        "thumbnail_url": thumb_url,
        "file_size": file_size_mb,
        "downloads": 0,
        "upload_date": datetime.utcnow().isoformat()
    }

    try:
        res = supabase.table("books").insert(insert_data).execute()
        # fix: check data, not error
        if not res.data:
            return jsonify({'error': 'Failed to insert record into database', 'detail': str(res)}), 500
    except Exception as e:
        return jsonify({'error': f"Insert to database failed: {e}"}), 500

    return jsonify({'message': 'Book uploaded successfully!', 'file_url': book_url, 'thumbnail_url': thumb_url}), 200

# -----------------------
# Get all books
# -----------------------
@app.route('/api/books', methods=['GET'])
def get_books():
    try:
        res = supabase.table("books").select("*").order("upload_date", desc=True).execute()
        rows = res.data or []
        result = []
        for b in rows:
            result.append({
                'id': b.get('id'),
                'title': b.get('title'),
                'author': b.get('author'),
                'category': b.get('category'),
                'description': b.get('description'),
                'downloads': b.get('downloads', 0),
                'upload_date': b.get('upload_date') or b.get('created_at'),
                'file_size': b.get('file_size'),
                'file_size_str': readable_mb(b.get('file_size')),
                'thumbnail_url': b.get('thumbnail_url'),
                'file_url': b.get('file_url')
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Failed to fetch books: {e}'}), 500

# -----------------------
# Download
# -----------------------
@app.route('/api/books/<int:book_id>/download', methods=['GET'])
def download_book(book_id):
    try:
        res = supabase.table("books").select("*").eq("id", book_id).single().execute()
        book = res.data
        if not book:
            return jsonify({'error': 'Book not found'}), 404

        new_downloads = (book.get("downloads") or 0) + 1
        supabase.table("books").update({"downloads": new_downloads}).eq("id", book_id).execute()

        return redirect(book.get('file_url'), code=302)
    except Exception as e:
        return jsonify({'error': f'Error during download: {e}'}), 500

# -----------------------
# Update
# -----------------------
@app.route('/api/books/<int:book_id>', methods=['PUT'])
def update_book(book_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Missing JSON body'}), 400
        allowed = {k: data[k] for k in ('title', 'author', 'category', 'description') if k in data}
        if not allowed:
            return jsonify({'error': 'No updatable fields provided'}), 400

        res = supabase.table("books").update(allowed).eq("id", book_id).execute()
        if not res.data:
            return jsonify({'error': 'Failed to update book'}), 500
        return jsonify({'success': True, 'message': 'Book updated successfully!'})
    except Exception as e:
        return jsonify({'error': f'Update failed: {e}'}), 500

# -----------------------
# Delete
# -----------------------
@app.route('/api/books/<int:book_id>', methods=['DELETE'])
def delete_book(book_id):
    try:
        res = supabase.table("books").select("*").eq("id", book_id).single().execute()
        book = res.data
        if not book:
            return jsonify({'error': 'Book not found'}), 404

        file_url = book.get('file_url', '')
        thumb_url = book.get('thumbnail_url', '')

        def extract_path(url):
            marker = f"/object/public/{SUPABASE_BUCKET}/"
            idx = url.find(marker)
            if idx != -1:
                return url[idx + len(marker):]
            return None

        paths_to_remove = [p for p in [extract_path(file_url), extract_path(thumb_url)] if p]
        if paths_to_remove:
            try:
                supabase.storage.from_(SUPABASE_BUCKET).remove(paths_to_remove)
            except Exception:
                pass

        supabase.table("books").delete().eq("id", book_id).execute()
        return jsonify({'success': True, 'message': 'Book deleted successfully!'})
    except Exception as e:
        return jsonify({'error': f'Delete failed: {e}'}), 500

# -----------------------
# Stats
# -----------------------
@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    try:
        res = supabase.table("books").select("id,downloads,file_size").execute()
        rows = res.data or []
        total_books = len(rows)
        total_downloads = sum((r.get('downloads') or 0) for r in rows)
        total_size_mb = sum((r.get('file_size') or 0) for r in rows)
        return jsonify({
            "total_books": total_books,
            "total_downloads": total_downloads,
            "total_size": f"{round(total_size_mb, 2)} MB"
        })
    except Exception as e:
        return jsonify({'error': f'Stats failed: {e}'}), 500

# -----------------------
# Root
# -----------------------
@app.route('/')
def home():
    return "✅ OceanBooks backend (Supabase storage + DB) is live!"

# -----------------------
# Run
# -----------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)