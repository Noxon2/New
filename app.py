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
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")  # anon or service_role (service_role gives more privileges)
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "uploads")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set as environment variables.")

# create supabase client
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
# Upload route (Supabase storage + DB)
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
        return jsonify({'error': 'Missing required field (title, author, category, book_file, thumbnail)'}), 400

    # unique names to avoid collisions
    uid = str(uuid.uuid4())
    book_name = f"books/{uid}_{book_file.filename}"
    thumb_name = f"thumbnails/{uid}_{thumbnail.filename}"

    # Read bytes
    book_bytes = book_file.read()
    thumbnail_bytes = thumbnail.read()

    # Upload to Supabase storage
    try:
        # If upload accepts bytes directly (supabase-py), we can pass bytes
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

    # Insert metadata into Supabase DB (table: books)
    try:
        insert_data = {
            "title": title,
            "author": author,
            "category": category,
            "description": desc,
            "file_url": book_url,
            "thumbnail_url": thumb_url,
            "file_size": file_size_mb,
            "downloads": 0,
            # upload_date column has default now() on DB, but we can also pass
            "upload_date": datetime.utcnow().isoformat()
        }
        res = supabase.table("books").insert(insert_data).execute()
        if res.error:
            # res.error may hold info depending on client version
            return jsonify({'error': 'Failed to insert record into database', 'detail': str(res.error)}), 500
    except Exception as e:
        return jsonify({'error': f"Insert to database failed: {e}"}), 500

    return jsonify({'message': 'Book uploaded successfully!', 'file_url': book_url, 'thumbnail_url': thumb_url}), 200

# -----------------------
# Get all books
# -----------------------
@app.route('/api/books', methods=['GET'])
def get_books():
    try:
        # select all, order by upload_date descending
        res = supabase.table("books").select("*").order("upload_date", {"ascending": False}).execute()
        if res.error:
            return jsonify({'error': 'Failed to fetch books', 'detail': str(res.error)}), 500
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
                'file_name': None,
                'file_size': b.get('file_size'),
                'file_size_str': readable_mb(b.get('file_size')),
                'thumbnail_url': b.get('thumbnail_url'),
                'file_url': b.get('file_url')
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Failed to fetch books: {e}'}), 500

# -----------------------
# Download route (increments count, then redirect to Supabase URL)
# -----------------------
@app.route('/api/books/<int:book_id>/download', methods=['GET'])
def download_book(book_id):
    try:
        # fetch book
        res = supabase.table("books").select("*").eq("id", book_id).single().execute()
        if res.error or not res.data:
            return jsonify({'error': 'Book not found'}), 404
        book = res.data

        # increment downloads
        updates = {"downloads": (book.get("downloads") or 0) + 1}
        upd = supabase.table("books").update(updates).eq("id", book_id).execute()
        # ignore upd.error for now, still proceed to redirect

        file_url = book.get('file_url')
        if not file_url:
            return jsonify({'error': 'File URL missing for this book'}), 500

        return redirect(file_url, code=302)
    except Exception as e:
        return jsonify({'error': f'Error during download: {e}'}), 500

# -----------------------
# Update book metadata
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
        if res.error:
            return jsonify({'error': 'Failed to update book', 'detail': str(res.error)}), 500
        return jsonify({'success': True, 'message': 'Book updated successfully!'})
    except Exception as e:
        return jsonify({'error': f'Update failed: {e}'}), 500

# -----------------------
# Delete book (DB record + optional storage delete)
# -----------------------
@app.route('/api/books/<int:book_id>', methods=['DELETE'])
def delete_book(book_id):
    try:
        # find record
        res = supabase.table("books").select("*").eq("id", book_id).single().execute()
        if res.error or not res.data:
            return jsonify({'error': 'Book not found'}), 404
        book = res.data

        # attempt to remove files from storage (optional)
        # We expect file_url like: {SUPABASE_URL}/storage/v1/object/public/<bucket>/<path>
        # Extract path after bucket/
        try:
            file_url = book.get('file_url', '')
            thumb_url = book.get('thumbnail_url', '')
            def extract_path(url):
                # safe parsing: find "/object/public/<bucket>/" and get rest
                marker = f"/object/public/{SUPABASE_BUCKET}/"
                idx = url.find(marker)
                if idx != -1:
                    return url[idx + len(marker):]
                return None
            file_path = extract_path(file_url)
            thumb_path = extract_path(thumb_url)

            to_remove = []
            if file_path:
                to_remove.append(file_path)
            if thumb_path:
                to_remove.append(thumb_path)
            if to_remove:
                try:
                    supabase.storage.from_(SUPABASE_BUCKET).remove(to_remove)
                except Exception:
                    # ignore storage delete errors (we still delete DB record)
                    pass
        except Exception:
            pass

        # delete DB record
        delr = supabase.table("books").delete().eq("id", book_id).execute()
        if delr.error:
            return jsonify({'error': 'Failed to delete record', 'detail': str(delr.error)}), 500

        return jsonify({'success': True, 'message': 'Book deleted successfully!'})
    except Exception as e:
        return jsonify({'error': f'Delete failed: {e}'}), 500

# -----------------------
# Admin stats for dashboard
# -----------------------
@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    try:
        total_books = supabase.table("books").select("id", count="exact").execute()
        # fallback approach: fetch and count
        res = supabase.table("books").select("id, downloads, file_size").execute()
        if res.error:
            return jsonify({'error': 'Failed to fetch stats', 'detail': str(res.error)}), 500
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