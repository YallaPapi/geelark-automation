"""
Master Ledger for All Posted Videos.

This module tracks EVERY successful post across ALL campaigns and runs.
It is the source of truth for "has this video been posted to this account?"

The ledger is:
- Append-only: NEVER deleted, only added to
- Immediate: Updated the moment a post succeeds
- Checked before posting: Prevents duplicates

Format: account|video_filename|timestamp
Example: podclipcrafters|DM6m1Econ4x-2.mp4|2025-12-17T10:30:00
"""

import os
import logging
from datetime import datetime
from typing import Set, Tuple
from threading import Lock

# Try to import portalocker for file locking
try:
    import portalocker
    HAS_PORTALOCKER = True
except ImportError:
    HAS_PORTALOCKER = False

logger = logging.getLogger(__name__)

# Default ledger path
DEFAULT_LEDGER_PATH = "all_posted_videos.txt"

# In-memory cache for fast duplicate checking
_ledger_cache: Set[Tuple[str, str]] = set()
_cache_loaded = False
_cache_lock = Lock()


def _get_ledger_path() -> str:
    """Get the path to the master ledger file."""
    # Use the project root directory
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        DEFAULT_LEDGER_PATH
    )


def load_ledger_cache(ledger_path: str = None) -> Set[Tuple[str, str]]:
    """
    Load the entire ledger into memory for fast duplicate checking.

    Returns:
        Set of (account, video_filename) tuples that have been posted
    """
    global _ledger_cache, _cache_loaded

    path = ledger_path or _get_ledger_path()

    with _cache_lock:
        if _cache_loaded and not ledger_path:
            return _ledger_cache

        _ledger_cache = set()

        if not os.path.exists(path):
            logger.info(f"Master ledger not found at {path}, starting fresh")
            _cache_loaded = True
            return _ledger_cache

        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('|')
                    if len(parts) >= 2:
                        account = parts[0].strip()
                        video_filename = parts[1].strip()
                        _ledger_cache.add((account, video_filename))

            logger.info(f"Loaded {len(_ledger_cache)} posted entries from master ledger")
            _cache_loaded = True

        except Exception as e:
            logger.error(f"Error loading master ledger: {e}")
            _cache_loaded = True  # Mark as loaded even on error to avoid infinite retries

    return _ledger_cache


def is_already_posted(account: str, video_path: str, ledger_path: str = None) -> bool:
    """
    Check if a video has already been posted to an account.

    Args:
        account: Account name
        video_path: Full path to video file (will extract filename)
        ledger_path: Optional override for ledger path

    Returns:
        True if this video was already posted to this account
    """
    # Load cache if needed
    cache = load_ledger_cache(ledger_path)

    # Extract just the filename from the path
    video_filename = os.path.basename(video_path)

    return (account, video_filename) in cache


def record_successful_post(
    account: str,
    video_path: str,
    ledger_path: str = None
) -> bool:
    """
    Record a successful post to the master ledger.

    THIS MUST BE CALLED IMMEDIATELY AFTER A POST SUCCEEDS.
    Uses file locking to ensure thread/process safety.

    Args:
        account: Account that posted
        video_path: Full path to video file
        ledger_path: Optional override for ledger path

    Returns:
        True if recorded successfully
    """
    global _ledger_cache

    path = ledger_path or _get_ledger_path()
    video_filename = os.path.basename(video_path)
    timestamp = datetime.now().isoformat()

    entry = f"{account}|{video_filename}|{timestamp}\n"

    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)

        # Append to file with locking
        with open(path, 'a', encoding='utf-8') as f:
            if HAS_PORTALOCKER:
                portalocker.lock(f, portalocker.LOCK_EX)
            try:
                f.write(entry)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
            finally:
                if HAS_PORTALOCKER:
                    portalocker.unlock(f)

        # Update cache
        with _cache_lock:
            _ledger_cache.add((account, video_filename))

        logger.info(f"MASTER LEDGER: Recorded {account}|{video_filename}")
        return True

    except Exception as e:
        logger.error(f"CRITICAL: Failed to record to master ledger: {e}")
        logger.error(f"  Entry was: {entry.strip()}")
        # Still update cache to prevent immediate duplicate
        with _cache_lock:
            _ledger_cache.add((account, video_filename))
        return False


def get_posted_videos_for_account(account: str, ledger_path: str = None) -> Set[str]:
    """
    Get all video filenames that have been posted to a specific account.

    Args:
        account: Account name
        ledger_path: Optional override for ledger path

    Returns:
        Set of video filenames posted to this account
    """
    cache = load_ledger_cache(ledger_path)
    return {video for acc, video in cache if acc == account}


def get_accounts_for_video(video_path: str, ledger_path: str = None) -> Set[str]:
    """
    Get all accounts that have posted a specific video.

    Args:
        video_path: Full path to video file
        ledger_path: Optional override for ledger path

    Returns:
        Set of account names that have posted this video
    """
    cache = load_ledger_cache(ledger_path)
    video_filename = os.path.basename(video_path)
    return {acc for acc, video in cache if video == video_filename}


def get_stats(ledger_path: str = None) -> dict:
    """
    Get statistics about the master ledger.

    Returns:
        Dict with counts and stats
    """
    cache = load_ledger_cache(ledger_path)

    accounts = set(acc for acc, _ in cache)
    videos = set(video for _, video in cache)

    return {
        'total_posts': len(cache),
        'unique_accounts': len(accounts),
        'unique_videos': len(videos),
    }


def clear_cache():
    """Clear the in-memory cache. Use after modifying ledger externally."""
    global _ledger_cache, _cache_loaded
    with _cache_lock:
        _ledger_cache = set()
        _cache_loaded = False


if __name__ == "__main__":
    # Demo/test
    logging.basicConfig(level=logging.INFO)

    print("Master Ledger Stats:")
    stats = get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
