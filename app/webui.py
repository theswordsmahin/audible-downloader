import os
import sqlite3
import threading
import time
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from datetime import datetime
import audiobookDownloader

app = Flask(__name__)
app.secret_key = os.urandom(24)

config = "/config"
db_path = config + "/audiobooks.db"

# Global download status tracking
download_status = {
    'is_downloading': False,
    'is_refreshing': False,
    'current_book': None,
    'total_to_download': 0,
    'downloaded_count': 0,
    'current_asin': None,
    'last_update': None,
    'error': None
}
status_lock = threading.Lock()

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def update_download_status(asin, book_title):
    """Update the current download status"""
    with status_lock:
        download_status['current_asin'] = asin
        download_status['current_book'] = book_title
        download_status['last_update'] = datetime.now().isoformat()

def increment_download_count():
    """Increment the downloaded count"""
    with status_lock:
        download_status['downloaded_count'] += 1
        download_status['last_update'] = datetime.now().isoformat()

def create_audiobook_folder_thread_safe(asin, cursor):
    """Thread-safe version of create_audiobook_folder that uses provided cursor"""
    book = cursor.execute('SELECT authors, title, series_title, subtitle, narrators, series_sequence, release_date FROM audiobooks WHERE asin=?', [asin]).fetchone()

    authors = book['authors']
    title = book['title']
    series_title = book['series_title']
    subtitle = book['subtitle']
    narrators = book['narrators']
    series_sequence = book['series_sequence']
    release_date = book['release_date']

    directory = audiobookDownloader.audiobook_directory + "/" + authors + "/"
    if series_title:  # if series title exists the sequence also exists
        directory = directory + series_title + "/" + str(series_sequence) + " - "
    directory = directory + release_date.split("-")[0] + " - " + title
    if subtitle:
        directory = directory + " - " + subtitle
    directory = directory + " {" + narrators + "}" + "/"

    os.makedirs(os.path.dirname(directory), exist_ok=True)

    return directory

def download_new_titles_with_status():
    """Download new titles with status tracking"""
    import subprocess
    import shutil
    import json

    # Create a new connection for this thread
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    to_download = cur.execute('SELECT asin, title FROM audiobooks WHERE downloaded=?', [0]).fetchall()

    for row in to_download:
        asin = row['asin']
        title = row['title']

        # Update status
        update_download_status(asin, title)

        try:
            # Download using audible CLI
            subprocess.run(["audible", "-v", "error", "download", "-a", asin, "--aax-fallback",
                          "--timeout", "0", "-f", "asin_ascii", "--ignore-podcasts",
                          "-o", audiobookDownloader.audiobook_download_directory])

            # Process downloaded files
            audiobooks = [each for each in os.listdir(audiobookDownloader.audiobook_download_directory)
                         if each.endswith(('.aax', '.aaxc'))]

            for audiobook in audiobooks:
                new_asin = audiobook.split("_")[0]
                asin_check = cur.execute("SELECT title FROM audiobooks WHERE asin=?", [new_asin]).fetchone()

                if asin_check is None:
                    new_name = audiobook.replace(new_asin, asin)
                    shutil.move(os.path.join(audiobookDownloader.audiobook_download_directory, audiobook),
                              os.path.join(audiobookDownloader.audiobook_download_directory, new_name))
                    audiobook = new_name

                current_asin = audiobook.split("_")[0]

                # Mark as downloaded
                cur.execute('UPDATE audiobooks SET downloaded = 1 WHERE asin = ?', [current_asin])
                con.commit()

                src = os.path.join(audiobookDownloader.audiobook_download_directory, audiobook)
                aax_book = audiobook.endswith('.aax')
                audiobook_base = audiobook[:-3] if aax_book else audiobook[:-4]

                # Convert to processing directory first (fast local storage)
                os.makedirs(audiobookDownloader.audiobook_processing_directory, exist_ok=True)
                processing_file = os.path.join(audiobookDownloader.audiobook_processing_directory, audiobook_base + "m4b")

                # Convert file
                if aax_book:
                    subprocess.run(["ffmpeg", "-activation_bytes", audiobookDownloader.activation_bytes,
                                  "-i", src, "-c", "copy", processing_file])
                    os.remove(src)
                else:
                    vouchers = [each for each in os.listdir(audiobookDownloader.audiobook_download_directory)
                              if each.endswith('.voucher')]
                    for voucher in vouchers:
                        voucher_path = os.path.join(audiobookDownloader.audiobook_download_directory, voucher)
                        json_voucher = json.load(open(voucher_path))["content_license"]["license_response"]
                        subprocess.run(["ffmpeg", "-audible_key", json_voucher["key"],
                                      "-audible_iv", json_voucher["iv"], "-i", src, "-c", "copy", processing_file])
                        os.remove(src)
                        os.remove(src[:-4] + "voucher")

                # Move converted file to final destination
                final_destination = (create_audiobook_folder_thread_safe(current_asin, cur) + audiobook_base + "m4b"
                                   if audiobookDownloader.use_folders
                                   else os.path.join(audiobookDownloader.audiobook_directory, audiobook_base + "m4b"))
                shutil.move(processing_file, final_destination)

                increment_download_count()

        except Exception as e:
            print(f"Error downloading {asin}: {e}")
            with status_lock:
                download_status['error'] = f"Error downloading {title}: {str(e)}"

    # Cleanup any remaining vouchers
    vouchers = [each for each in os.listdir(audiobookDownloader.audiobook_download_directory)
               if each.endswith('.voucher')]
    for voucher in vouchers:
        os.remove(os.path.join(audiobookDownloader.audiobook_download_directory, voucher))

    con.close()

def run_downloader_loop():
    """Background thread to run the downloader loop"""
    while True:
        try:
            print(f"[{datetime.now()}] Running update and download...")
            audiobookDownloader.update_titles()
            audiobookDownloader.download_new_titles()
            print(f"[{datetime.now()}] Update and download complete. Sleeping for 6 hours...")
        except Exception as e:
            print(f"[{datetime.now()}] Error in downloader loop: {e}")
        time.sleep(6 * 60 * 60)  # 6 hours

# On startup, mark all existing pending books as skipped if env variable is set
def initialize_skip_existing():
    """Mark all pending books as skipped on first run if SKIP_EXISTING_ON_STARTUP is set"""
    if os.getenv('SKIP_EXISTING_ON_STARTUP', 'False').lower() == 'true':
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            # Mark all books with downloaded=0 as skipped (-1)
            result = cur.execute('UPDATE audiobooks SET downloaded = -1 WHERE downloaded = 0')
            skipped_count = result.rowcount
            conn.commit()
            conn.close()
            if skipped_count > 0:
                print(f"[{datetime.now()}] Marked {skipped_count} existing books as skipped")
        except Exception as e:
            print(f"[{datetime.now()}] Error during skip initialization: {e}")

# Run skip initialization before starting threads
initialize_skip_existing()

# Start background downloader thread
downloader_thread = threading.Thread(target=run_downloader_loop, daemon=True)
downloader_thread.start()

@app.route('/')
def index():
    """Main page - list all audiobooks"""
    conn = get_db()
    cur = conn.cursor()

    # Get filter parameters
    status_filter = request.args.get('status', 'all')
    search_query = request.args.get('search', '')

    # Build query
    query = 'SELECT * FROM audiobooks WHERE 1=1'
    params = []

    if status_filter == 'downloaded':
        query += ' AND downloaded = 1'
    elif status_filter == 'pending':
        query += ' AND downloaded = 0'
    elif status_filter == 'skipped':
        query += ' AND downloaded = -1'

    if search_query:
        query += ' AND (title LIKE ? OR authors LIKE ? OR series_title LIKE ?)'
        search_pattern = f'%{search_query}%'
        params.extend([search_pattern, search_pattern, search_pattern])

    query += ' ORDER BY authors, series_title, series_sequence, title'

    audiobooks = cur.execute(query, params).fetchall()
    conn.close()

    # Get stats
    conn = get_db()
    cur = conn.cursor()
    total_count = cur.execute('SELECT COUNT(*) FROM audiobooks').fetchone()[0]
    downloaded_count = cur.execute('SELECT COUNT(*) FROM audiobooks WHERE downloaded = 1').fetchone()[0]
    pending_count = cur.execute('SELECT COUNT(*) FROM audiobooks WHERE downloaded = 0').fetchone()[0]
    skipped_count = cur.execute('SELECT COUNT(*) FROM audiobooks WHERE downloaded = -1').fetchone()[0]
    conn.close()

    return render_template('index.html',
                         audiobooks=audiobooks,
                         status_filter=status_filter,
                         search_query=search_query,
                         total_count=total_count,
                         downloaded_count=downloaded_count,
                         pending_count=pending_count,
                         skipped_count=skipped_count)

@app.route('/book/<asin>')
def book_detail(asin):
    """View details of a single audiobook"""
    conn = get_db()
    cur = conn.cursor()
    book = cur.execute('SELECT * FROM audiobooks WHERE asin = ?', [asin]).fetchone()
    conn.close()

    if book is None:
        flash('Audiobook not found', 'error')
        return redirect(url_for('index'))

    return render_template('book_detail.html', book=book)

@app.route('/book/<asin>/edit', methods=['GET', 'POST'])
def edit_book(asin):
    """Edit audiobook metadata"""
    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        # Update the book
        title = request.form.get('title')
        subtitle = request.form.get('subtitle')
        authors = request.form.get('authors')
        series_title = request.form.get('series_title')
        narrators = request.form.get('narrators')
        series_sequence = request.form.get('series_sequence')
        release_date = request.form.get('release_date')

        try:
            cur.execute('''UPDATE audiobooks
                          SET title = ?, subtitle = ?, authors = ?,
                              series_title = ?, narrators = ?,
                              series_sequence = ?, release_date = ?
                          WHERE asin = ?''',
                       [title, subtitle, authors, series_title, narrators,
                        series_sequence if series_sequence else None,
                        release_date, asin])
            conn.commit()
            flash('Audiobook updated successfully', 'success')
            return redirect(url_for('book_detail', asin=asin))
        except Exception as e:
            flash(f'Error updating audiobook: {e}', 'error')
        finally:
            conn.close()

    # GET request - show form
    book = cur.execute('SELECT * FROM audiobooks WHERE asin = ?', [asin]).fetchone()
    conn.close()

    if book is None:
        flash('Audiobook not found', 'error')
        return redirect(url_for('index'))

    return render_template('edit_book.html', book=book)

@app.route('/book/<asin>/delete', methods=['POST'])
def delete_book(asin):
    """Delete an audiobook from the database"""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute('DELETE FROM audiobooks WHERE asin = ?', [asin])
        conn.commit()
        flash('Audiobook deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting audiobook: {e}', 'error')
    finally:
        conn.close()

    return redirect(url_for('index'))

@app.route('/book/<asin>/reset', methods=['POST'])
def reset_book(asin):
    """Reset download status to trigger re-download"""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute('UPDATE audiobooks SET downloaded = 0 WHERE asin = ?', [asin])
        conn.commit()
        flash('Download status reset. Book will be re-downloaded in the next cycle.', 'success')
    except Exception as e:
        flash(f'Error resetting download status: {e}', 'error')
    finally:
        conn.close()

    return redirect(url_for('book_detail', asin=asin))

@app.route('/trigger/refresh')
def trigger_refresh():
    """Trigger library refresh from Audible"""
    with status_lock:
        if download_status['is_refreshing'] or download_status['is_downloading']:
            flash('A refresh or download is already in progress', 'warning')
            return redirect(url_for('index'))

    def refresh_task():
        with status_lock:
            download_status['is_refreshing'] = True
            download_status['last_update'] = datetime.now().isoformat()
            download_status['error'] = None

        try:
            audiobookDownloader.update_titles()
        except Exception as e:
            with status_lock:
                download_status['error'] = str(e)
        finally:
            with status_lock:
                download_status['is_refreshing'] = False
                download_status['last_update'] = datetime.now().isoformat()

    thread = threading.Thread(target=refresh_task, daemon=True)
    thread.start()
    flash('Library refresh started in background', 'success')

    return redirect(url_for('index'))

@app.route('/trigger/download', methods=['POST'])
def trigger_download():
    """Trigger download of all pending audiobooks"""
    with status_lock:
        if download_status['is_downloading'] or download_status['is_refreshing']:
            flash('A download or refresh is already in progress', 'warning')
            return redirect(url_for('index'))

    # Get count of pending books
    conn = get_db()
    cur = conn.cursor()
    pending_count = cur.execute('SELECT COUNT(*) FROM audiobooks WHERE downloaded = 0').fetchone()[0]
    conn.close()

    if pending_count == 0:
        flash('No pending audiobooks to download', 'warning')
        return redirect(url_for('index'))

    def download_task():
        with status_lock:
            download_status['is_downloading'] = True
            download_status['total_to_download'] = pending_count
            download_status['downloaded_count'] = 0
            download_status['last_update'] = datetime.now().isoformat()
            download_status['error'] = None

        try:
            # Use the modified download function with status tracking
            download_new_titles_with_status()
        except Exception as e:
            with status_lock:
                download_status['error'] = str(e)
        finally:
            with status_lock:
                download_status['is_downloading'] = False
                download_status['current_book'] = None
                download_status['current_asin'] = None
                download_status['last_update'] = datetime.now().isoformat()

    thread = threading.Thread(target=download_task, daemon=True)
    thread.start()
    flash(f'Download started for {pending_count} pending audiobook(s)', 'success')

    return redirect(url_for('index'))

@app.route('/mark-pending', methods=['POST'])
def mark_pending():
    """Mark selected audiobooks as pending"""
    asin_list = request.form.getlist('asin')

    if not asin_list:
        flash('No audiobooks selected', 'warning')
        return redirect(url_for('index'))

    conn = get_db()
    cur = conn.cursor()

    try:
        for asin in asin_list:
            cur.execute('UPDATE audiobooks SET downloaded = 0 WHERE asin = ?', [asin])
        conn.commit()
        flash(f'Marked {len(asin_list)} book(s) as pending for download', 'success')
    except Exception as e:
        flash(f'Error marking books as pending: {e}', 'error')
    finally:
        conn.close()

    return redirect(url_for('index'))

@app.route('/api/stats')
def api_stats():
    """API endpoint for statistics"""
    conn = get_db()
    cur = conn.cursor()

    total_count = cur.execute('SELECT COUNT(*) FROM audiobooks').fetchone()[0]
    downloaded_count = cur.execute('SELECT COUNT(*) FROM audiobooks WHERE downloaded = 1').fetchone()[0]
    pending_count = total_count - downloaded_count

    conn.close()

    return jsonify({
        'total': total_count,
        'downloaded': downloaded_count,
        'pending': pending_count
    })

@app.route('/api/download-status')
def api_download_status():
    """API endpoint for current download status"""
    with status_lock:
        status = download_status.copy()

    # Get book details if currently downloading
    if status['current_asin']:
        conn = get_db()
        cur = conn.cursor()
        book = cur.execute('SELECT title, authors FROM audiobooks WHERE asin = ?',
                          [status['current_asin']]).fetchone()
        conn.close()

        if book:
            status['current_book_details'] = {
                'title': book['title'],
                'authors': book['authors']
            }

    return jsonify(status)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
