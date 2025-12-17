# Prompt 3 Response – Factory + Adapter Refactor Plan

## Objective
Concrete, step-by-step refactoring plan to adopt Factory + Adapter patterns for multi-platform posters without breaking existing Instagram posting.

---

## Current Call Site Analysis

**File:** `parallel_worker.py`
**Function:** `execute_posting_job()` (lines 162-275)

```python
# Line 189: Import
from post_reel_smart import SmartInstagramPoster

# Lines 213-217: Instantiation
poster = SmartInstagramPoster(
    phone_name=account,
    system_port=worker_config.system_port,
    appium_url=worker_config.appium_url
)

# Lines 221-225: Usage
poster.connect()
success = poster.post(video_path, caption, humanize=True)

# Lines 267-269: Cleanup
poster.cleanup()
```

**Key Observation:** The worker uses a simple 3-method contract:
1. `connect()` → bool
2. `post(video_path, caption, humanize=True)` → bool
3. `cleanup()` → void

This is exactly what `BasePoster` will define.

---

## Step-by-Step Refactor Plan

### Step 1: Create `posters/` Package with Base Interface (Zero Risk)

**Files to create:**
- `posters/__init__.py`
- `posters/base_poster.py`

**`posters/base_poster.py`:**
```python
"""Base poster interface and shared types for multi-platform posting."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class PostResult:
    """Standardized result from a posting attempt."""
    success: bool
    error: Optional[str] = None
    error_type: Optional[str] = None       # e.g., 'suspended', 'adb_timeout', 'terminated'
    error_category: Optional[str] = None   # 'account', 'infrastructure', 'unknown'
    retryable: bool = True
    platform: str = ""
    account: str = ""
    duration_seconds: float = 0.0
    screenshot_path: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class BasePoster(ABC):
    """Abstract base class for platform-specific posters."""

    @property
    @abstractmethod
    def platform(self) -> str:
        """Return platform identifier (e.g., 'instagram', 'tiktok')."""
        pass

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to device.

        Returns:
            True if connection successful, False otherwise.
        """
        pass

    @abstractmethod
    def post(self, video_path: str, caption: str, humanize: bool = False) -> PostResult:
        """
        Execute the posting flow.

        Args:
            video_path: Path to video file on local machine.
            caption: Caption text for the post.
            humanize: If True, perform human-like delays and actions.

        Returns:
            PostResult with success status and error details if failed.
        """
        pass

    @abstractmethod
    def cleanup(self):
        """Release resources and disconnect from device."""
        pass
```

**`posters/__init__.py`:**
```python
"""Platform poster factory and exports."""
from .base_poster import BasePoster, PostResult

__all__ = ['BasePoster', 'PostResult', 'get_poster']


def get_poster(platform: str, phone_name: str, **kwargs) -> BasePoster:
    """
    Factory function to get platform-specific poster.

    Args:
        platform: Platform identifier ('instagram', 'tiktok', etc.)
        phone_name: Geelark phone name to post from.
        **kwargs: Additional args passed to poster constructor
                  (system_port, appium_url, etc.)

    Returns:
        BasePoster implementation for the specified platform.

    Raises:
        ValueError: If platform is not supported.
    """
    if platform == "instagram":
        from .instagram_poster import InstagramPoster
        return InstagramPoster(phone_name, **kwargs)
    elif platform == "tiktok":
        from .tiktok_poster import TikTokPoster
        return TikTokPoster(phone_name, **kwargs)
    else:
        raise ValueError(f"Unsupported platform: {platform}")
```

**Test after step:**
```bash
python -c "from posters import BasePoster, PostResult; print('OK')"
```

---

### Step 2: Create Instagram Adapter (Wraps SmartInstagramPoster)

**File to create:** `posters/instagram_poster.py`

```python
"""Instagram poster adapter - wraps SmartInstagramPoster with BasePoster interface."""
import time
from typing import Optional

from .base_poster import BasePoster, PostResult


class InstagramPoster(BasePoster):
    """Instagram poster implementation using SmartInstagramPoster."""

    def __init__(self, phone_name: str, system_port: int = 8200, appium_url: str = None):
        """
        Initialize Instagram poster.

        Args:
            phone_name: Geelark phone name.
            system_port: UiAutomator2 systemPort.
            appium_url: Appium server URL.
        """
        self._phone_name = phone_name
        self._system_port = system_port
        self._appium_url = appium_url
        self._poster = None  # Lazy init
        self._connected = False
        self._start_time = None

    @property
    def platform(self) -> str:
        return "instagram"

    def _ensure_poster(self):
        """Lazy-initialize the underlying SmartInstagramPoster."""
        if self._poster is None:
            # Import here to avoid circular imports
            from post_reel_smart import SmartInstagramPoster
            self._poster = SmartInstagramPoster(
                phone_name=self._phone_name,
                system_port=self._system_port,
                appium_url=self._appium_url
            )

    def connect(self) -> bool:
        """Connect to device via SmartInstagramPoster."""
        self._ensure_poster()
        self._start_time = time.time()
        try:
            self._poster.connect()
            self._connected = True
            return True
        except Exception as e:
            print(f"[InstagramPoster] Connect failed: {e}")
            return False

    def post(self, video_path: str, caption: str, humanize: bool = False) -> PostResult:
        """Post to Instagram via SmartInstagramPoster."""
        if not self._connected:
            return PostResult(
                success=False,
                error="Not connected",
                error_type="connection_error",
                error_category="infrastructure",
                retryable=True,
                platform=self.platform,
                account=self._phone_name
            )

        try:
            success = self._poster.post(video_path, caption, humanize=humanize)

            duration = time.time() - self._start_time if self._start_time else 0

            if success:
                return PostResult(
                    success=True,
                    platform=self.platform,
                    account=self._phone_name,
                    duration_seconds=duration
                )
            else:
                # Extract error info from SmartInstagramPoster
                error_msg = self._poster.last_error_message or "Post failed"
                error_type = self._poster.last_error_type or "unknown"
                screenshot = self._poster.last_screenshot_path

                # Determine if retryable based on error type
                non_retryable = {'suspended', 'terminated', 'id_verification', 'logged_out'}
                retryable = error_type not in non_retryable

                # Map to category
                category = 'account' if error_type in non_retryable else 'infrastructure'

                return PostResult(
                    success=False,
                    error=error_msg,
                    error_type=error_type,
                    error_category=category,
                    retryable=retryable,
                    platform=self.platform,
                    account=self._phone_name,
                    duration_seconds=duration,
                    screenshot_path=screenshot
                )

        except Exception as e:
            duration = time.time() - self._start_time if self._start_time else 0
            return PostResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                error_type="exception",
                error_category="infrastructure",
                retryable=True,
                platform=self.platform,
                account=self._phone_name,
                duration_seconds=duration
            )

    def cleanup(self):
        """Cleanup via SmartInstagramPoster."""
        if self._poster:
            try:
                self._poster.cleanup()
            except Exception as e:
                print(f"[InstagramPoster] Cleanup warning: {e}")
            finally:
                self._poster = None
                self._connected = False
```

**Test after step:**
```bash
python -c "
from posters import get_poster
poster = get_poster('instagram', 'test_phone', system_port=8200)
print(f'Platform: {poster.platform}')
print('OK - adapter created')
"
```

---

### Step 3: Add Platform to Campaign Config

**File to modify:** `campaigns/viral/campaign.json` and `campaigns/podcast/campaign.json`

**Add `platform` field:**
```json
{
  "name": "viral",
  "platform": "instagram",
  "videos_dir": "videos",
  "captions_file": "captions.csv",
  ...
}
```

**Backwards compatibility:** If `platform` is missing, default to `"instagram"`.

**Test after step:**
```bash
python -c "
import json
with open('campaigns/viral/campaign.json', 'r') as f:
    config = json.load(f)
print(f'Platform: {config.get(\"platform\", \"instagram\")}')
"
```

---

### Step 4: Modify Worker to Use Factory

**File to modify:** `parallel_worker.py`

**Change in `execute_posting_job()` (lines 162-275):**

```python
# OLD (line 189):
from post_reel_smart import SmartInstagramPoster

# NEW:
from posters import get_poster, PostResult


# OLD (lines 213-217):
poster = SmartInstagramPoster(
    phone_name=account,
    system_port=worker_config.system_port,
    appium_url=worker_config.appium_url
)

# NEW:
platform = job.get('platform', 'instagram')  # Default for backwards compat
poster = get_poster(
    platform=platform,
    phone_name=account,
    system_port=worker_config.system_port,
    appium_url=worker_config.appium_url
)


# OLD (lines 224-225):
success = poster.post(video_path, caption, humanize=True)
if success:
    ...
else:
    error = poster.last_error_message or "Post returned False"
    ...

# NEW:
result = poster.post(video_path, caption, humanize=True)
if result.success:
    ...
else:
    error = result.error
    error_category = result.error_category
    error_type = result.error_type
    ...
```

**Full updated function:**
```python
def execute_posting_job(
    job: dict,
    worker_config: WorkerConfig,
    config: ParallelConfig,
    logger: logging.Logger,
    tracker=None,
    worker_id: int = None
) -> tuple:
    """Execute a single posting job using platform-specific poster."""
    from posters import get_poster, PostResult

    account = job['account']
    video_path = job['video_path']
    caption = job['caption']
    job_id = job['job_id']
    platform = job.get('platform', 'instagram')  # Backwards compat

    # Kill any orphaned Appium sessions
    kill_appium_sessions(worker_config.appium_url, logger)

    # Pre-post verification
    if tracker and worker_id is not None:
        is_valid, error = tracker.verify_job_before_post(job_id, worker_id)
        if not is_valid:
            logger.warning(f"Job {job_id} failed pre-post verification: {error}")
            return False, f"Pre-post verification failed: {error}", 'infrastructure', 'verification_failed'

    logger.info(f"Starting job {job_id}: posting to {account} ({platform})")
    logger.info(f"  Video: {video_path}")
    logger.info(f"  Caption: {caption[:50]}...")

    poster = None
    try:
        # Use factory to get platform-specific poster
        poster = get_poster(
            platform=platform,
            phone_name=account,
            system_port=worker_config.system_port,
            appium_url=worker_config.appium_url
        )

        # Connect to device
        logger.info(f"Connecting to device via {worker_config.appium_url}...")
        if not poster.connect():
            return False, "Connection failed", 'infrastructure', 'connection_failed'

        # Post the video
        logger.info("Posting video...")
        result = poster.post(video_path, caption, humanize=True)

        if result.success:
            logger.info(f"Job {job_id} completed successfully!")
            return True, "", None, None
        else:
            logger.error(f"Job {job_id} failed: {result.error}")
            return False, result.error, result.error_category, result.error_type

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Job {job_id} exception: {error_msg}")
        logger.debug(traceback.format_exc())
        if tracker:
            category, error_type = tracker._classify_error(error_msg)
        else:
            category, error_type = 'unknown', ''
        return False, error_msg, category, error_type

    finally:
        try:
            if poster:
                poster.cleanup()
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
        stop_phone_by_name(account, logger)
```

**Test after step:**
```bash
# Dry run - verify factory is called correctly
python -c "
from parallel_worker import execute_posting_job
from parallel_config import WorkerConfig
# Just verify import works
print('Worker imports OK')
"
```

---

### Step 5: Update Progress Tracker to Store Platform

**File to modify:** `progress_tracker.py`

**In `seed_from_campaign()`:** Add platform to job dict.

```python
# When creating job records:
job = {
    'job_id': job_id,
    'account': account,
    'video_path': video_path,
    'caption': caption,
    'platform': campaign_config.get('platform', 'instagram'),  # NEW
    'status': 'pending',
    ...
}
```

**In `_get_csv_columns()`:** Add 'platform' column.

**Test after step:**
```bash
python -c "
from progress_tracker import ProgressTracker
pt = ProgressTracker('test_progress.csv')
print('Columns:', pt._get_csv_columns())
"
rm test_progress.csv
```

---

### Step 6: Keep Legacy Path (Feature Flag)

For safe rollback, add environment variable to disable factory:

```python
# parallel_worker.py
USE_LEGACY_POSTER = os.environ.get('USE_LEGACY_POSTER', '').lower() == 'true'

if USE_LEGACY_POSTER:
    from post_reel_smart import SmartInstagramPoster
    poster = SmartInstagramPoster(...)
else:
    from posters import get_poster
    poster = get_poster(...)
```

**Rollback:** `USE_LEGACY_POSTER=true python parallel_orchestrator.py --run`

---

### Step 7: Implement TikTokPoster (After Instagram Works)

**File to create:** `posters/tiktok_poster.py`

```python
"""TikTok poster implementation."""
from .base_poster import BasePoster, PostResult


class TikTokPoster(BasePoster):
    """TikTok poster implementation."""

    APP_PACKAGE = "com.zhiliaoapp.musically"  # or com.ss.android.ugc.trill

    def __init__(self, phone_name: str, system_port: int = 8200, appium_url: str = None):
        self._phone_name = phone_name
        self._system_port = system_port
        self._appium_url = appium_url
        # ... similar to InstagramPoster

    @property
    def platform(self) -> str:
        return "tiktok"

    def connect(self) -> bool:
        # TikTok-specific connection logic
        pass

    def post(self, video_path: str, caption: str, humanize: bool = False) -> PostResult:
        # TikTok-specific posting logic with TikTok Claude prompts
        pass

    def cleanup(self):
        # TikTok-specific cleanup
        pass
```

**Add to factory:**
```python
# posters/__init__.py
elif platform == "tiktok":
    from .tiktok_poster import TikTokPoster
    return TikTokPoster(phone_name, **kwargs)
```

---

## Summary: File Changes by Step

| Step | Files Modified | Files Created | Risk Level |
|------|---------------|---------------|------------|
| 1 | None | `posters/__init__.py`, `posters/base_poster.py` | Zero |
| 2 | None | `posters/instagram_poster.py` | Zero |
| 3 | `campaigns/*/campaign.json` | None | Low |
| 4 | `parallel_worker.py` | None | Medium |
| 5 | `progress_tracker.py` | None | Low |
| 6 | `parallel_worker.py` | None | Zero (adds fallback) |
| 7 | `posters/__init__.py` | `posters/tiktok_poster.py` | Low |

---

## Rollback Plan

1. **Before Step 4:** No changes to core system, delete `posters/` directory.
2. **After Step 4:** Set `USE_LEGACY_POSTER=true` environment variable.
3. **After Step 5:** Revert progress_tracker.py changes, old CSV format still works.

---

## Test Plan After Each Step

| Step | Test Command | Expected Result |
|------|--------------|-----------------|
| 1 | `python -c "from posters import BasePoster, PostResult; print('OK')"` | OK printed |
| 2 | `python -c "from posters import get_poster; p = get_poster('instagram', 'test'); print(p.platform)"` | "instagram" |
| 3 | Check campaign.json has platform field | JSON valid |
| 4 | `python parallel_orchestrator.py --status` | No import errors |
| 4 | `python parallel_orchestrator.py --workers 1 --run` | Instagram posts work |
| 5 | Check CSV has platform column | Column present |
| 6 | `USE_LEGACY_POSTER=true python parallel_worker.py --worker-id 0 --num-workers 1` | Legacy path works |
| 7 | `python -c "from posters import get_poster; p = get_poster('tiktok', 'test'); print(p.platform)"` | "tiktok" |
