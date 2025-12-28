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

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

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
    pending_count = total_count - downloaded_count
    conn.close()

    return render_template('index.html',
                         audiobooks=audiobooks,
                         status_filter=status_filter,
                         search_query=search_query,
                         total_count=total_count,
                         downloaded_count=downloaded_count,
                         pending_count=pending_count)

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
    try:
        audiobookDownloader.update_titles()
        flash('Library refresh completed successfully', 'success')
    except Exception as e:
        flash(f'Error refreshing library: {e}', 'error')

    return redirect(url_for('index'))

@app.route('/trigger/download', methods=['POST'])
def trigger_download():
    """Trigger download of pending audiobooks"""
    asin_list = request.form.getlist('asin')

    if not asin_list:
        flash('No audiobooks selected', 'warning')
        return redirect(url_for('index'))

    # Reset download status for selected books
    conn = get_db()
    cur = conn.cursor()

    try:
        for asin in asin_list:
            cur.execute('UPDATE audiobooks SET downloaded = 0 WHERE asin = ?', [asin])
        conn.commit()

        # Trigger immediate download
        audiobookDownloader.download_new_titles()
        flash(f'Download triggered for {len(asin_list)} audiobook(s)', 'success')
    except Exception as e:
        flash(f'Error triggering download: {e}', 'error')
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
