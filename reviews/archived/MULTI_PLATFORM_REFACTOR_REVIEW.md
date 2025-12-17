# Code Review Request: Multi-Platform Posting System Refactor

## Overview

We have a working Instagram Reels automation system that posts videos to cloud phones via Appium + Claude AI vision. We want to extend this to support TikTok (and potentially other platforms in the future) without risking breaking the existing Instagram functionality.

## Current Architecture

```
parallel_orchestrator.py    # Spawns N workers, manages campaigns
    └── parallel_worker.py  # Claims jobs, manages phone lifecycle
        └── post_reel_smart.py  # Instagram-specific UI navigation using Claude AI
```

**Key files:**
- `post_reel_smart.py` - Contains `SmartInstagramPoster` class with all Instagram logic
- `parallel_worker.py` - Executes posting jobs, calls the poster
- `parallel_orchestrator.py` - Coordinates workers, manages progress
- `progress_tracker.py` - CSV-based job tracking with file locking
- `geelark_client.py` - Cloud phone API (start/stop phones, upload files)
- `appium_server_manager.py` - Manages Appium server lifecycle

## Goal

Add TikTok posting capability while:
1. **Zero risk to Instagram** - Changes to TikTok code cannot break Instagram
2. **Shared infrastructure** - Reuse orchestrator, workers, progress tracking
3. **Easy to add more platforms** - Clean pattern for YouTube Shorts, etc.

## Proposed Architecture

```
parallel_orchestrator.py        # Unchanged - platform agnostic
    └── parallel_worker.py      # Minor change - calls poster factory
        └── posters/
            ├── __init__.py           # Factory: get_poster(platform) -> BasePoster
            ├── base_poster.py        # Abstract interface
            ├── instagram_poster.py   # Current post_reel_smart.py (moved)
            └── tiktok_poster.py      # New TikTok implementation
```

## The Interface Contract

All platform posters implement this interface:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class PostResult:
    success: bool
    error_message: Optional[str] = None
    error_type: Optional[str] = None      # e.g., 'suspended', 'adb_timeout'
    error_category: Optional[str] = None  # 'account' or 'infrastructure'

class BasePoster(ABC):
    PLATFORM: str  # 'instagram', 'tiktok', etc.

    @abstractmethod
    def connect(self) -> bool:
        """Connect to device via Appium."""
        pass

    @abstractmethod
    def post_video(self, video_path: str, caption: str) -> PostResult:
        """Post video with caption. Returns standardized result."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Disconnect, stop phone, release resources."""
        pass
```

## Key Design Decisions

### 1. Complete Isolation Between Posters

Each poster is a **black box**. They do NOT share:
- Claude AI prompts (each platform has different UI)
- Error detection patterns (different error messages)
- UI navigation logic (completely different apps)
- Any helper functions

They ONLY share:
- The interface (method signatures)
- The return type (PostResult)

**Why:** If someone modifies TikTok-specific code, it literally cannot affect Instagram because the files never import each other.

### 2. Platform Selection via Campaign Config

Each campaign specifies its platform:

```
campaigns/
├── podcast/              # Instagram campaign
│   ├── config.json       # {"platform": "instagram", ...}
│   ├── accounts.txt
│   └── videos/
├── viral/                # Instagram campaign
│   └── config.json       # {"platform": "instagram", ...}
└── tiktok_viral/         # TikTok campaign
    └── config.json       # {"platform": "tiktok", ...}
```

### 3. Factory Pattern for Poster Selection

```python
# posters/__init__.py
def get_poster(platform: str, phone_name: str, **kwargs) -> BasePoster:
    posters = {
        'instagram': InstagramPoster,
        'tiktok': TikTokPoster,
    }
    return posters[platform](phone_name, **kwargs)
```

### 4. Minimal Changes to Worker

```python
# parallel_worker.py (the only change needed)
from posters import get_poster

def execute_job(job, config):
    platform = job.get('platform', 'instagram')
    poster = get_poster(platform, job['account'], ...)

    poster.connect()
    result = poster.post_video(job['video_path'], job['caption'])
    poster.cleanup()

    return result.success, result.error_message, ...
```

## Migration Plan

1. **Create `posters/` directory** with base interface
2. **Move** `post_reel_smart.py` → `posters/instagram_poster.py` (rename class)
3. **Create** `posters/tiktok_poster.py` with TikTok Claude prompts
4. **Add** platform field to campaign config
5. **Update** `parallel_worker.py` to use factory
6. **Test** both platforms work independently

## What We Need Reviewed

1. **Interface design** - Is `PostResult` sufficient? Missing fields?
2. **Isolation approach** - Any hidden coupling we're missing?
3. **Migration risk** - Safe way to move `post_reel_smart.py` without breaking existing?
4. **Error handling** - Should error classification stay in poster or move to worker?
5. **Future extensibility** - Anything that would make adding YouTube Shorts harder?

## Files to Review

Current implementation (to understand what we're refactoring):
- `post_reel_smart.py` - The Instagram poster being migrated
- `parallel_worker.py` - Where poster is called
- `config.py` - Campaign configuration

## Questions for Reviewer

1. Should we keep a backwards-compatible `post_reel_smart.py` that imports from `posters/` during transition?
2. Should platform-specific error patterns be in the poster or a separate file?
3. Is the factory pattern overkill, or should we just use a simple if/else in the worker?
4. Any concerns about the Claude AI prompts being duplicated between platforms vs shared?

---

**Context:** This system posts ~100 videos/day across 100+ accounts. Reliability is critical - we cannot afford regressions to the working Instagram flow while adding TikTok.
