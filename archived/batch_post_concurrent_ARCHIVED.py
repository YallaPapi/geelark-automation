"""
Concurrent batch post videos to Instagram Reels across multiple phones.
Posts to multiple phones simultaneously using threading.

Usage:
    python batch_post_concurrent.py <chunk_folder> <phone1> <phone2> ... [--limit N] [--workers N]

Example:
    python batch_post_concurrent.py va_chunk_05 miccliparchive reelwisdompod_ podmindstudio --limit 6 --workers 3
"""
import sys
import os

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import csv
import time
import argparse
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from post_reel_smart import SmartInstagramPoster


# Thread-safe print with phone prefix
print_lock = threading.Lock()

def safe_print(phone, message):
    """Thread-safe print with phone prefix"""
    with print_lock:
        print(f"[{phone}] {message}")


def load_posts_from_csv(chunk_folder):
    """Load video/caption pairs from chunk CSV"""
    csv_files = [f for f in os.listdir(chunk_folder) if f.endswith('.csv')]
    if not csv_files:
        raise Exception(f"No CSV file found in {chunk_folder}")

    csv_path = os.path.join(chunk_folder, csv_files[0])
    posts = []

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            shortcode = row.get('Shortcode', '').strip()
            caption = row.get('Text', '').strip()

            if not shortcode or not caption:
                continue

            # Find the video file
            video_filename = f"{shortcode}-1.mp4"
            video_path = os.path.join(chunk_folder, video_filename)

            if os.path.exists(video_path):
                posts.append({
                    'shortcode': shortcode,
                    'video_path': video_path,
                    'caption': caption
                })
            else:
                print(f"Warning: Video not found: {video_filename}")

    return posts


def post_single(phone, post, humanize=False):
    """Post a single video to a phone. Returns result dict."""
    shortcode = post['shortcode']
    safe_print(phone, f"Starting: {shortcode}")
    safe_print(phone, f"Caption: {post['caption'][:50]}...")

    result = {
        'shortcode': shortcode,
        'phone': phone,
        'status': 'pending',
        'error': None,
        'timestamp': datetime.now().isoformat()
    }

    try:
        poster = SmartInstagramPoster(phone)
        poster.connect()
        success = poster.post(post['video_path'], post['caption'], humanize=humanize)
        poster.cleanup()

        result['status'] = 'success' if success else 'failed'
        if success:
            safe_print(phone, f"SUCCESS: {shortcode}")
        else:
            safe_print(phone, f"FAILED: {shortcode}")

    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
        safe_print(phone, f"ERROR on {shortcode}: {e}")

    result['timestamp'] = datetime.now().isoformat()
    return result


def batch_post_concurrent(chunk_folder, phones, limit=None, workers=2, humanize=False):
    """Post videos concurrently across phones

    Args:
        chunk_folder: Folder containing CSV and video files
        phones: List of phone names to post to (round-robin assignment)
        limit: Maximum number of posts
        workers: Number of concurrent workers (phones posting at once)
        humanize: If True, perform random human-like actions before/after posting
    """

    # Load posts from CSV
    posts = load_posts_from_csv(chunk_folder)
    print(f"Found {len(posts)} videos in {chunk_folder}")

    if limit:
        posts = posts[:limit]
        print(f"Limited to {limit} posts")

    if not posts:
        print("No posts to process")
        return []

    print(f"Posting to {len(phones)} phones: {', '.join(phones)}")
    print(f"Concurrent workers: {workers}")
    print("-" * 50)

    # Assign posts to phones (round-robin)
    phone_assignments = []
    for i, post in enumerate(posts):
        phone = phones[i % len(phones)]
        phone_assignments.append((phone, post))

    # Results log
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"batch_concurrent_results_{timestamp}.csv"

    results = []
    results_lock = threading.Lock()

    def save_results():
        """Save current results to CSV"""
        with results_lock:
            with open(log_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['shortcode', 'phone', 'status', 'error', 'timestamp'])
                writer.writeheader()
                writer.writerows(results)

    start_time = time.time()

    # Run concurrent posts
    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Submit all tasks
        future_to_assignment = {}
        for phone, post in phone_assignments:
            future = executor.submit(post_single, phone, post, humanize)
            future_to_assignment[future] = (phone, post)

        # Collect results as they complete
        for future in as_completed(future_to_assignment):
            phone, post = future_to_assignment[future]
            try:
                result = future.result()
                with results_lock:
                    results.append(result)
                save_results()
            except Exception as e:
                safe_print(phone, f"Unexpected error: {e}")
                with results_lock:
                    results.append({
                        'shortcode': post['shortcode'],
                        'phone': phone,
                        'status': 'error',
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    })
                save_results()

    elapsed = time.time() - start_time

    # Summary
    print("\n" + "=" * 50)
    print("CONCURRENT BATCH COMPLETE")
    print("=" * 50)

    success_count = sum(1 for r in results if r['status'] == 'success')
    print(f"Success: {success_count}/{len(results)}")
    print(f"Elapsed time: {elapsed:.1f}s")
    print(f"Results saved to: {log_path}")

    if success_count < len(results):
        print("\nFailed posts:")
        for r in results:
            if r['status'] != 'success':
                print(f"  - {r['shortcode']} on {r['phone']}: {r.get('error', 'Unknown')}")

    return results


def main():
    parser = argparse.ArgumentParser(description='Concurrent batch post videos to Instagram')
    parser.add_argument('chunk_folder', help='Folder containing CSV and videos')
    parser.add_argument('phones', nargs='+', help='Phone names to post to (round-robin assignment)')
    parser.add_argument('--limit', type=int, help='Limit number of posts')
    parser.add_argument('--workers', type=int, default=2, help='Number of concurrent workers (default: 2)')
    parser.add_argument('--humanize', action='store_true', help='Perform random human-like actions before/after posting')

    args = parser.parse_args()

    if not os.path.isdir(args.chunk_folder):
        print(f"Folder not found: {args.chunk_folder}")
        sys.exit(1)

    # Limit workers to number of phones
    workers = min(args.workers, len(args.phones))

    batch_post_concurrent(args.chunk_folder, args.phones, args.limit, workers, args.humanize)


if __name__ == "__main__":
    main()
