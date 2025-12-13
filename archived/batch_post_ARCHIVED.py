"""
Batch post videos to Instagram Reels across multiple phones (round-robin).

Usage:
    python batch_post.py <chunk_folder> <phone1> <phone2> ... [--limit N]

Example:
    python batch_post.py va_chunk_05 miccliparchive reelwisdompod_ podmindstudio --limit 3
"""
import sys
import os

# Fix Windows console encoding for emojis BEFORE any other imports
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import csv
import time
import glob
import argparse
from datetime import datetime
from post_reel_smart import SmartInstagramPoster


def get_already_posted():
    """Load all successfully posted shortcodes from batch_results_*.csv files"""
    posted = set()
    for filepath in glob.glob("batch_results_*.csv"):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'success':
                        posted.add(row.get('shortcode'))
        except Exception as e:
            print(f"Warning: Could not read {filepath}: {e}")
    return posted


def load_posts_from_csv(chunk_folder, csv_name=None):
    """Load video/caption pairs from chunk CSV

    Supports multiple CSV formats:
    - Old format: 'Shortcode' column with video path, 'Text' for caption
    - New format: 'Image/Video link 1...' column with shortcode, 'Text' for caption
    """
    # Find CSV file
    if csv_name:
        csv_path = os.path.join(chunk_folder, csv_name)
    else:
        csv_files = [f for f in os.listdir(chunk_folder) if f.endswith('.csv')]
        if not csv_files:
            raise Exception(f"No CSV file found in {chunk_folder}")
        csv_path = os.path.join(chunk_folder, csv_files[0])

    print(f"Loading CSV: {csv_path}")

    # Build video map from subfolders
    videos = {}
    for item in os.listdir(chunk_folder):
        item_path = os.path.join(chunk_folder, item)
        if os.path.isdir(item_path):
            for f in os.listdir(item_path):
                if f.endswith('.mp4'):
                    shortcode = f.replace('.mp4', '')
                    videos[shortcode] = os.path.join(item_path, f)

    print(f"Found {len(videos)} videos in subfolders")

    posts = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames

        # Detect video column (supports multiple formats)
        video_col = None
        for col in columns:
            if 'Video' in col or 'Image' in col:
                video_col = col
                break
            if col == 'Shortcode':
                video_col = col
                break

        if not video_col:
            raise Exception(f"No video column found. Columns: {columns}")

        for row in reader:
            caption = row.get('Text', '').strip()
            video_ref = row.get(video_col, '').strip()

            if not video_ref or not caption:
                continue

            # Handle different formats
            if video_ref in videos:
                # New format: shortcode directly maps to video
                video_path = videos[video_ref]
                shortcode = video_ref
            elif 'spoofed' in video_ref or 'chunk_01' in video_ref:
                # Old format: full path, replace spoofed with chunk folder
                video_path = video_ref.replace('spoofed', os.path.basename(chunk_folder))
                video_path = video_path.replace('chunk_01a', os.path.basename(chunk_folder))
                shortcode = os.path.basename(video_path).replace('.mp4', '')
            else:
                # Try as shortcode with .mp4 extension
                shortcode = video_ref
                if shortcode in videos:
                    video_path = videos[shortcode]
                else:
                    continue

            if os.path.exists(video_path):
                posts.append({
                    'shortcode': shortcode,
                    'video_path': video_path,
                    'caption': caption
                })

    return posts


def batch_post(chunk_folder, phones, limit=None, delay=10, humanize=False, csv_name=None):
    """Post videos round-robin across phones

    Args:
        chunk_folder: Folder containing CSV and video files
        phones: List of phone names to post to (round-robin)
        limit: Maximum number of posts
        delay: Delay between posts in seconds
        humanize: If True, perform random human-like actions before/after posting
        csv_name: Specific CSV filename to use (default: first .csv found)
    """

    # Load posts from CSV
    posts = load_posts_from_csv(chunk_folder, csv_name)
    print(f"Found {len(posts)} videos in {chunk_folder}")

    # Filter out already posted
    already_posted = get_already_posted()
    if already_posted:
        original_count = len(posts)
        posts = [p for p in posts if p['shortcode'] not in already_posted]
        skipped = original_count - len(posts)
        print(f"Skipping {skipped} already-posted videos ({len(already_posted)} total in history)")
        print(f"Remaining: {len(posts)} videos to post")

    if limit:
        posts = posts[:limit]
        print(f"Limited to {limit} posts")

    if not posts:
        print("No posts to process")
        return []

    print(f"Posting to {len(phones)} phones: {', '.join(phones)}")
    print("-" * 50)

    # Results log
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"batch_results_{timestamp}.csv"

    results = []

    for i, post in enumerate(posts):
        # Round-robin phone selection
        phone = phones[i % len(phones)]

        print(f"\n[{i+1}/{len(posts)}] {post['shortcode']} -> {phone}")
        print(f"  Caption: {post['caption'][:60]}...")

        try:
            poster = SmartInstagramPoster(phone)
            poster.connect()
            success = poster.post(post['video_path'], post['caption'], humanize=humanize)
            poster.cleanup()

            results.append({
                'shortcode': post['shortcode'],
                'phone': phone,
                'status': 'success' if success else 'failed',
                'timestamp': datetime.now().isoformat()
            })

            if success:
                print(f"  [OK] Posted successfully")
            else:
                print(f"  [FAIL] Post failed")

        except Exception as e:
            print(f"  [ERROR] {e}")
            results.append({
                'shortcode': post['shortcode'],
                'phone': phone,
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })

        # Save results after each post
        with open(log_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['shortcode', 'phone', 'status', 'error', 'timestamp'])
            writer.writeheader()
            writer.writerows(results)

        # Delay between posts
        if i < len(posts) - 1:
            print(f"  Waiting {delay}s before next post...")
            time.sleep(delay)

    # Summary
    print("\n" + "=" * 50)
    print("BATCH COMPLETE")
    print("=" * 50)

    success_count = sum(1 for r in results if r['status'] == 'success')
    print(f"Success: {success_count}/{len(results)}")
    print(f"Results saved to: {log_path}")

    if success_count < len(results):
        print("\nFailed posts:")
        for r in results:
            if r['status'] != 'success':
                print(f"  - {r['shortcode']} on {r['phone']}: {r.get('error', 'Unknown')}")

    return results


def main():
    parser = argparse.ArgumentParser(description='Batch post videos to Instagram')
    parser.add_argument('chunk_folder', help='Folder containing CSV and videos')
    parser.add_argument('phones', nargs='+', help='Phone names to post to (round-robin)')
    parser.add_argument('--limit', type=int, help='Limit number of posts')
    parser.add_argument('--delay', type=int, default=10, help='Delay between posts in seconds (default: 10)')
    parser.add_argument('--humanize', action='store_true', help='Perform random human-like actions before/after posting')
    parser.add_argument('--csv', type=str, help='Specific CSV filename to use (default: first .csv found)')

    args = parser.parse_args()

    if not os.path.isdir(args.chunk_folder):
        print(f"Folder not found: {args.chunk_folder}")
        sys.exit(1)

    batch_post(args.chunk_folder, args.phones, args.limit, args.delay, args.humanize, args.csv)


if __name__ == "__main__":
    main()
