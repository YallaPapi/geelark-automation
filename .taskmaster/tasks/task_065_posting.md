# Task ID: 65

**Title:** Refactor Posting System for Multi-Platform Support (Instagram + TikTok)

**Status:** pending

**Dependencies:** 25 ✓, 47 ✓, 50 ✓, 61 ✓

**Priority:** medium

**Description:** Create a modular posters/ directory architecture with isolated platform-specific posters (Instagram, TikTok) that implement a common interface `post_video(video_path, caption) -> (success, error_message, error_type)`, enabling the shared orchestration infrastructure to support multiple social platforms.

**Details:**

## Implementation Overview

This refactor transforms the current Instagram-only posting system into a multi-platform architecture. The key principle is 100% isolation between platform posters - they share NO code except the common interface.

## Phase 1: Create Directory Structure and Common Interface

### 1.1 Create posters/ Directory
```
posters/
├── __init__.py           # Exports BasePoster, InstagramPoster, TikTokPoster
├── base_poster.py        # Abstract base class defining the interface
├── instagram_poster.py   # Instagram-specific implementation (migrated from post_reel_smart.py)
└── tiktok_poster.py      # TikTok-specific implementation with new Claude prompts
```

### 1.2 Define Common Interface (base_poster.py)
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass
class PostResult:
    """Standard result from any poster."""
    success: bool
    error_message: Optional[str] = None
    error_type: Optional[str] = None  # e.g., 'suspended', 'adb_timeout'
    error_category: Optional[str] = None  # 'account' or 'infrastructure'

class BasePoster(ABC):
    """Abstract base class for all platform posters."""
    
    PLATFORM: str  # Must be set by subclass: 'instagram', 'tiktok', etc.
    
    def __init__(self, phone_name: str, system_port: int = 8200, appium_url: str = None):
        """Initialize poster with phone connection details."""
        self.phone_name = phone_name
        self.system_port = system_port
        self.appium_url = appium_url
    
    @abstractmethod
    def connect(self) -> bool:
        """Connect to the device. Returns True on success."""
        pass
    
    @abstractmethod
    def post_video(self, video_path: str, caption: str) -> PostResult:
        """
        Post a video with caption.
        
        This is the main entry point. Implementations handle:
        - Video upload to device
        - App navigation
        - Caption entry
        - Share/publish action
        
        Args:
            video_path: Local path to video file
            caption: Caption text for the post
            
        Returns:
            PostResult with success status and error details if failed
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources (disconnect, stop phone, etc.)."""
        pass
```

## Phase 2: Migrate Instagram Poster

### 2.1 Move post_reel_smart.py to posters/instagram_poster.py
- Move entire SmartInstagramPoster class
- Rename class to `InstagramPoster`
- Implement BasePoster interface
- Update imports to use relative paths for claude_analyzer.py
- Set `PLATFORM = 'instagram'`

### 2.2 Update post_video() Method
```python
def post_video(self, video_path: str, caption: str) -> PostResult:
    """Instagram-specific posting implementation."""
    try:
        # Existing post() method logic
        success = self._execute_instagram_flow(video_path, caption)
        
        if success:
            return PostResult(success=True)
        else:
            return PostResult(
                success=False,
                error_message=self.last_error_message,
                error_type=self.last_error_type,
                error_category=self._classify_error_category(self.last_error_type)
            )
    except Exception as e:
        return PostResult(
            success=False,
            error_message=str(e),
            error_type='exception',
            error_category='infrastructure'
        )
```

### 2.3 Keep Instagram-Specific Components
- `claude_analyzer.py` - Instagram UI prompts (rename to `instagram_analyzer.py` or move into poster)
- All humanize methods (_humanize_scroll_feed, etc.)
- Instagram error detection patterns
- Instagram-specific UI navigation logic

## Phase 3: Create TikTok Poster

### 3.1 Create posters/tiktok_poster.py
```python
class TikTokPoster(BasePoster):
    """TikTok-specific video posting implementation."""
    
    PLATFORM = 'tiktok'
    
    def __init__(self, phone_name: str, system_port: int = 8200, appium_url: str = None):
        super().__init__(phone_name, system_port, appium_url)
        self._conn = DeviceConnectionManager(phone_name, system_port, appium_url)
        self._analyzer = TikTokUIAnalyzer()  # TikTok-specific Claude prompts
        # ... similar structure to Instagram but TikTok-specific
```

### 3.2 Create TikTok UI Analyzer (tiktok_analyzer.py)
Create new Claude prompts for TikTok's UI:
```python
class TikTokUIAnalyzer:
    """TikTok-specific UI analysis using Claude AI."""
    
    def build_prompt(self, elements, caption, ...):
        prompt = """You are controlling an Android phone to post a video to TikTok.

TikTok posting flow:
1. Find and tap the "+" (Create) button at bottom center
2. Select "Upload" from the options
3. Select video from gallery (most recent first)
4. Add music (optional) or skip
5. Tap "Next" to proceed to caption
6. Enter caption in the "Describe your video" field
7. Tap "Post" to publish
8. Done when you see confirmation or back on feed

TikTok-specific UI elements:
- Bottom nav: Home, Friends, +, Inbox, Profile
- Create options: Camera, Templates, Upload
- ...
"""
```

### 3.3 TikTok Error Detection
Add TikTok-specific error patterns:
```python
TIKTOK_ERROR_PATTERNS = {
    'account': {
        'banned': ['account banned', 'permanently banned'],
        'suspended': ['account suspended', 'restricted'],
        'logged_out': ['log in', 'sign up'],
        'age_restricted': ['age-restricted', 'violates community guidelines'],
    },
    'infrastructure': {
        'upload_failed': ['upload failed', 'video processing'],
        'connection_error': ['network error', 'connection failed'],
    }
}
```

## Phase 4: Update Campaign Config for Platform Selection

### 4.1 Add Platform Field to CampaignConfig
In `config.py`, add platform field:
```python
@dataclass
class CampaignConfig:
    # ... existing fields ...
    platform: str = 'instagram'  # 'instagram' or 'tiktok'
    
    @classmethod
    def from_folder(cls, campaign_path: str) -> 'CampaignConfig':
        # ... existing loading code ...
        # Read platform from campaign.json
        platform = settings.get('platform', 'instagram')
        
        return cls(
            # ... existing fields ...
            platform=platform,
        )
```

### 4.2 Update campaign.json Schema
```json
{
    "name": "viral_tiktok",
    "platform": "tiktok",
    "enabled": true,
    "max_posts_per_account_per_day": 2
}
```

## Phase 5: Update Orchestration Layer

### 5.1 Create Poster Factory (posters/__init__.py)
```python
from .base_poster import BasePoster, PostResult
from .instagram_poster import InstagramPoster
from .tiktok_poster import TikTokPoster

def get_poster(platform: str, phone_name: str, **kwargs) -> BasePoster:
    """Factory function to get the appropriate poster for a platform."""
    posters = {
        'instagram': InstagramPoster,
        'tiktok': TikTokPoster,
    }
    
    poster_class = posters.get(platform.lower())
    if not poster_class:
        raise ValueError(f"Unknown platform: {platform}. Supported: {list(posters.keys())}")
    
    return poster_class(phone_name, **kwargs)
```

### 5.2 Update parallel_worker.py
```python
from posters import get_poster, PostResult

def execute_posting_job(job, worker_config, config, logger, tracker=None, worker_id=None):
    """Execute a single posting job (platform-agnostic)."""
    # Get platform from job (set during seeding from campaign config)
    platform = job.get('platform', 'instagram')
    
    poster = get_poster(
        platform=platform,
        phone_name=job['account'],
        system_port=worker_config.system_port,
        appium_url=worker_config.appium_url
    )
    
    try:
        poster.connect()
        result = poster.post_video(job['video_path'], job['caption'])
        
        if result.success:
            return True, "", None, None
        else:
            return False, result.error_message, result.error_category, result.error_type
    finally:
        poster.cleanup()
```

### 5.3 Update Progress Tracker CSV Schema
Add 'platform' column to track which platform each job is for:
```python
COLUMNS = [
    'job_id', 'account', 'video_path', 'caption', 'status',
    'worker_id', 'claimed_at', 'completed_at', 'error',
    'attempts', 'max_attempts', 'retry_at', 'error_type',
    'error_category', 'pass_number', 'platform'  # NEW
]
```

## Phase 6: Backward Compatibility

### 6.1 Keep post_reel_smart.py as Thin Wrapper
For backward compatibility with CLI usage:
```python
# post_reel_smart.py (wrapper)
from posters import InstagramPoster

# Re-export for backward compatibility
SmartInstagramPoster = InstagramPoster

def main():
    # Same CLI interface
    poster = InstagramPoster(phone_name)
    poster.connect()
    result = poster.post_video(video_path, caption)
    return result.success

if __name__ == "__main__":
    main()
```

## Key Design Principles

1. **100% Isolation**: Instagram and TikTok posters share NO code except the interface
2. **Platform-Specific Analyzers**: Each platform has its own Claude prompts and UI patterns
3. **Single Interface**: All platforms implement `post_video(video_path, caption) -> PostResult`
4. **Factory Pattern**: Workers use factory to get correct poster based on campaign platform
5. **Backward Compatible**: Existing Instagram-only usage continues to work

## Files to Create/Modify

**New Files:**
- `posters/__init__.py`
- `posters/base_poster.py`
- `posters/instagram_poster.py` (migrated from post_reel_smart.py)
- `posters/tiktok_poster.py`
- `posters/tiktok_analyzer.py`

**Modified Files:**
- `config.py` - Add platform field to CampaignConfig
- `progress_tracker.py` - Add platform column
- `parallel_worker.py` - Use poster factory
- `post_reel_smart.py` - Thin wrapper for backward compatibility

**Test Strategy:**

## Test Strategy

### 1. Unit Tests - Interface Compliance
```bash
# Verify all posters implement BasePoster
python -c "
from posters import BasePoster, InstagramPoster, TikTokPoster

# Check inheritance
assert issubclass(InstagramPoster, BasePoster)
assert issubclass(TikTokPoster, BasePoster)

# Check required methods exist
for Poster in [InstagramPoster, TikTokPoster]:
    assert hasattr(Poster, 'connect')
    assert hasattr(Poster, 'post_video')
    assert hasattr(Poster, 'cleanup')
    assert hasattr(Poster, 'PLATFORM')
print('Interface compliance: PASS')
"
```

### 2. Unit Tests - Factory Function
```bash
python -c "
from posters import get_poster, InstagramPoster, TikTokPoster

# Instagram factory
ig_poster = get_poster('instagram', 'test_phone')
assert isinstance(ig_poster, InstagramPoster)
assert ig_poster.PLATFORM == 'instagram'

# TikTok factory
tt_poster = get_poster('tiktok', 'test_phone')
assert isinstance(tt_poster, TikTokPoster)
assert tt_poster.PLATFORM == 'tiktok'

# Case insensitive
assert isinstance(get_poster('Instagram', 'test'), InstagramPoster)
assert isinstance(get_poster('TIKTOK', 'test'), TikTokPoster)

# Invalid platform
try:
    get_poster('twitter', 'test')
    assert False, 'Should raise ValueError'
except ValueError as e:
    assert 'Unknown platform' in str(e)
print('Factory function: PASS')
"
```

### 3. Unit Tests - PostResult Dataclass
```bash
python -c "
from posters import PostResult

# Success result
r1 = PostResult(success=True)
assert r1.success == True
assert r1.error_message is None

# Failure result
r2 = PostResult(success=False, error_message='test', error_type='suspended', error_category='account')
assert r2.success == False
assert r2.error_category == 'account'
print('PostResult: PASS')
"
```

### 4. Unit Tests - CampaignConfig Platform Field
```bash
python -c "
from config import CampaignConfig
import os

# Create test campaign folder
os.makedirs('test_campaign/videos', exist_ok=True)
with open('test_campaign/accounts.txt', 'w') as f: f.write('test_account\n')
with open('test_campaign/captions.csv', 'w') as f: f.write('filename,post_caption\nvideo1.mp4,test caption\n')
with open('test_campaign/videos/video1.mp4', 'wb') as f: f.write(b'fake')

# Test default platform
config = CampaignConfig.from_folder('test_campaign')
assert config.platform == 'instagram', f'Expected instagram, got {config.platform}'

# Test with campaign.json specifying TikTok
import json
with open('test_campaign/campaign.json', 'w') as f:
    json.dump({'platform': 'tiktok'}, f)

config = CampaignConfig.from_folder('test_campaign')
assert config.platform == 'tiktok', f'Expected tiktok, got {config.platform}'

# Cleanup
import shutil
shutil.rmtree('test_campaign')
print('CampaignConfig platform field: PASS')
"
```

### 5. Backward Compatibility - CLI Usage
```bash
# Test that post_reel_smart.py still works as entry point
python -c "
from post_reel_smart import SmartInstagramPoster
# Should import without error and be an alias for InstagramPoster
print('SmartInstagramPoster import: PASS')
"

# Test CLI help still works
python post_reel_smart.py --help
```

### 6. Integration Test - Instagram Poster (Dry Run)
```bash
python -c "
from posters import InstagramPoster

# Create poster (no actual connection)
poster = InstagramPoster(phone_name='test_account', system_port=8200)
assert poster.PLATFORM == 'instagram'
assert poster.phone_name == 'test_account'
print('Instagram poster instantiation: PASS')
"
```

### 7. Integration Test - TikTok Poster (Dry Run)
```bash
python -c "
from posters import TikTokPoster

# Create poster (no actual connection)
poster = TikTokPoster(phone_name='test_account', system_port=8200)
assert poster.PLATFORM == 'tiktok'
assert poster.phone_name == 'test_account'
print('TikTok poster instantiation: PASS')
"
```

### 8. Live Test - Instagram Campaign (Existing Behavior)
```bash
# Run existing podcast campaign - should work identically
python parallel_orchestrator.py --campaign podcast --workers 1 --run

# Verify logs show Instagram-specific messages
grep -i "instagram" logs/worker_0.log
```

### 9. Live Test - TikTok Campaign (New Behavior)
```bash
# Create TikTok test campaign
mkdir -p test_campaigns/tiktok_test/videos
echo "tiktok_test_account" > test_campaigns/tiktok_test/accounts.txt
echo '{"platform": "tiktok", "enabled": true}' > test_campaigns/tiktok_test/campaign.json
echo "filename,post_caption" > test_campaigns/tiktok_test/captions.csv
echo "test.mp4,Test TikTok post" >> test_campaigns/tiktok_test/captions.csv
# Copy a test video to test_campaigns/tiktok_test/videos/test.mp4

# Run TikTok campaign
python parallel_orchestrator.py --campaign tiktok_test --workers 1 --run

# Verify logs show TikTok-specific messages
grep -i "tiktok" logs/worker_0.log
```

### 10. Platform Isolation Test
```bash
# Verify Instagram and TikTok posters don't share code
python -c "
import ast
import os

# Check instagram_poster.py doesn't import from tiktok_poster.py
with open('posters/instagram_poster.py') as f:
    tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            module = getattr(node, 'module', '') or ''
            for alias in getattr(node, 'names', []):
                name = alias.name
                assert 'tiktok' not in name.lower(), f'Instagram imports TikTok: {name}'
                assert 'tiktok' not in module.lower(), f'Instagram imports from TikTok module: {module}'
print('Platform isolation: PASS')
"
```

### 11. Progress Tracker Platform Column
```bash
python -c "
from progress_tracker import ProgressTracker

# Verify platform column exists
assert 'platform' in ProgressTracker.COLUMNS, 'platform column missing'
print('Progress tracker schema: PASS')
"
```

## Subtasks

### 65.1. Create posters/ directory structure with BasePoster abstract interface and PostResult dataclass

**Status:** pending  
**Dependencies:** None  

Create the posters/ directory with __init__.py, base_poster.py defining the BasePoster abstract base class and PostResult dataclass that all platform posters must implement.

**Details:**

Create posters/ directory with:

1. **posters/base_poster.py**:
   - Import ABC, abstractmethod from abc
   - Import dataclass, Optional from typing
   - Define PostResult dataclass with fields: success (bool), error_message (Optional[str]=None), error_type (Optional[str]=None), error_category (Optional[str]=None)
   - Define BasePoster(ABC) abstract class with:
     - Class attribute PLATFORM: str (must be overridden by subclasses)
     - __init__(self, phone_name: str, system_port: int = 8200, appium_url: str = None)
     - @abstractmethod connect(self) -> bool
     - @abstractmethod post_video(self, video_path: str, caption: str) -> PostResult
     - @abstractmethod cleanup(self) -> None

2. **posters/__init__.py**:
   - Import and export BasePoster, PostResult from base_poster
   - Create placeholder imports for InstagramPoster, TikTokPoster (to be implemented in subsequent subtasks)
   - Define get_poster(platform: str, phone_name: str, **kwargs) -> BasePoster factory function that maps platform names to poster classes

### 65.2. Migrate SmartInstagramPoster to posters/instagram_poster.py implementing BasePoster interface

**Status:** pending  
**Dependencies:** 65.1  

Move the existing SmartInstagramPoster from post_reel_smart.py to posters/instagram_poster.py, rename to InstagramPoster, and implement the BasePoster interface while preserving all existing functionality.

**Details:**

1. Create **posters/instagram_poster.py**:
   - Copy SmartInstagramPoster class from post_reel_smart.py
   - Rename class to InstagramPoster
   - Add PLATFORM = 'instagram' class attribute
   - Inherit from BasePoster
   - Keep __init__ signature compatible with BasePoster: (phone_name, system_port=8200, appium_url=None)
   - Wrap existing post() method in new post_video() method that returns PostResult:
     ```python
     def post_video(self, video_path: str, caption: str) -> PostResult:
         try:
             success = self.post(video_path, caption, humanize=True)
             if success:
                 return PostResult(success=True)
             else:
                 return PostResult(
                     success=False,
                     error_message=self.last_error_message,
                     error_type=self.last_error_type,
                     error_category=self._classify_error_category(self.last_error_type)
                 )
         except Exception as e:
             return PostResult(success=False, error_message=str(e), error_type='exception', error_category='infrastructure')
     ```
   - Add _classify_error_category() helper method mapping error_type to 'account' or 'infrastructure'
   - Keep all existing methods: connect(), cleanup(), humanize_*, dump_ui(), analyze_ui(), etc.

2. Update **posters/__init__.py** to import InstagramPoster and register it in get_poster()

3. Move/copy claude_analyzer.py to posters/instagram_analyzer.py (optional, can keep in root for backward compatibility)

### 65.3. Create TikTok poster skeleton with TikTokPoster class and TikTok-specific Claude analyzer

**Status:** pending  
**Dependencies:** 65.1  

Create posters/tiktok_poster.py with TikTokPoster class implementing BasePoster interface, and posters/tiktok_analyzer.py with TikTok-specific Claude UI prompts for navigation.

**Details:**

1. Create **posters/tiktok_analyzer.py**:
   - Model after claude_analyzer.py structure
   - Define TikTokUIAnalyzer class with:
     - Same interface as ClaudeUIAnalyzer: format_ui_elements(), build_prompt(), parse_response(), analyze()
     - TikTok-specific build_prompt() with navigation flow:
       - Find and tap '+' Create button at bottom center
       - Select 'Upload' from create options
       - Select video from gallery (most recent first)
       - Optional: Add music or skip
       - Tap 'Next' to proceed to caption
       - Enter caption in 'Describe your video' field
       - Tap 'Post' to publish
       - Done when confirmation appears or back on feed
     - TikTok-specific UI element hints (bottom nav: Home, Friends, +, Inbox, Profile)

2. Create **posters/tiktok_poster.py**:
   - Import BasePoster, PostResult from .base_poster
   - Import DeviceConnectionManager from device_connection
   - Import TikTokUIAnalyzer from .tiktok_analyzer
   - Define TikTokPoster(BasePoster) with PLATFORM = 'tiktok'
   - Implement connect() using DeviceConnectionManager pattern
   - Implement post_video() with TikTok app navigation (am start com.zhiliaoapp.musically or com.ss.android.ugc.trill)
   - Implement cleanup() to stop phone
   - Add TikTok-specific error detection patterns

3. Update **posters/__init__.py** to import TikTokPoster and register in get_poster()

### 65.4. Add platform field to CampaignConfig and PostingContext for multi-platform campaign support

**Status:** pending  
**Dependencies:** 65.1  

Extend config.py to add platform field ('instagram' or 'tiktok') to CampaignConfig and PostingContext, with backward-compatible default of 'instagram'.

**Details:**

1. Update **CampaignConfig** in config.py:
   - Add field: platform: str = 'instagram'  # 'instagram' or 'tiktok'
   - Update from_folder() to read platform from campaign.json settings:
     ```python
     platform = settings.get('platform', 'instagram')
     ```
   - Add platform to return cls() call
   - Add validation: if platform not in ('instagram', 'tiktok'): raise ValueError

2. Update **PostingContext** in config.py:
   - Add field: platform: str = 'instagram'
   - Update from_campaign() to copy platform from campaign:
     ```python
     platform=campaign.platform,
     ```
   - Update legacy() to accept platform parameter with default 'instagram'

3. Update campaign.json schema documentation:
   - Add 'platform' key documentation: "'instagram' or 'tiktok'"

4. Update progress_tracker.py COLUMNS to include 'platform' column (after 'pass_number'):
   - Add 'platform' to COLUMNS list
   - Update seed_from_campaign() to include platform in job dict
   - Update seed_from_jobs() to accept platform parameter

### 65.5. Update parallel_worker.py to use platform-aware poster factory and maintain backward compatibility

**Status:** pending  
**Dependencies:** 65.2, 65.3, 65.4  

Refactor parallel_worker.py execute_posting_job() to use the get_poster() factory function based on job platform, while preserving backward compatibility with existing Instagram-only jobs.

**Details:**

1. Update imports in **parallel_worker.py**:
   - Replace `from post_reel_smart import SmartInstagramPoster` with `from posters import get_poster, PostResult`

2. Update **execute_posting_job()** function:
   - Extract platform from job dict with default: `platform = job.get('platform', 'instagram')`
   - Replace direct SmartInstagramPoster instantiation with factory:
     ```python
     poster = get_poster(
         platform=platform,
         phone_name=job['account'],
         system_port=worker_config.system_port,
         appium_url=worker_config.appium_url
     )
     ```
   - Update result handling to use PostResult:
     ```python
     result = poster.post_video(job['video_path'], job['caption'])
     if result.success:
         return True, '', None, None
     else:
         return False, result.error_message, result.error_category, result.error_type
     ```

3. Update **post_reel_smart.py** for backward compatibility:
   - Keep as thin wrapper importing from posters:
     ```python
     from posters import InstagramPoster
     SmartInstagramPoster = InstagramPoster  # Backward compatibility alias
     ```
   - Keep main() function for CLI usage: `python post_reel_smart.py <phone> <video> <caption>`

4. Add logging in execute_posting_job() to show platform:
   - `logger.info(f"Starting job {job_id} ({platform}): posting to {account}")`
